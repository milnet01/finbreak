"""TransactionsView — the searchable/filterable transaction table (FIBR-0012 D7/D8).

The transaction table, its right-click **Set category…** → learn-a-rule chain, and
the ``_table_state`` sort / remembered-columns move **verbatim** here from the old
``HomeView`` (Home is now the dashboard). Added on top: a four-filter bar — search
(description substring), date range, account, and category — each independently
active and **AND-combined** (INV-9). ``refresh()`` reloads the master
``list_transactions()`` list (tab activation only); the filters run in memory over
that list and never re-hit the DB.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.datetime_format import format_date
from finbreak.errors import VaultLockedError
from finbreak.models import CategorySource, Transaction
from finbreak.services.auth import DATETIME_SYSTEM, AmountPrefs, DateTimePrefs
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.ui._amount import _NEGATIVE_TEXT, _POSITIVE_TEXT, _format_amount
from finbreak.ui._table_state import (
    SortableItem,
    enable_sorting,
    fill_guard,
    remember_columns,
    select_by_index,
    selected_index,
    tag_row,
)
from finbreak.ui._widgets import add_grouped_categories
from finbreak.ui.category_picker import CategoryPickerDialog
from finbreak.ui.modal import show_modal
from finbreak.ui.rules import RuleEditDialog

# Fixed column indices (the table's shape; headers are the translated labels).
_COL_DATE = 0
_COL_AMOUNT = 1
_COL_DESCRIPTION = 2
_COL_ACCOUNT = 3
_COL_CATEGORY = 4

# The "All accounts" / "All categories" sentinel — a real object so it can never be
# confused with the ``None`` that marks the Uncategorised category (D8).
_FILTER_ALL = object()


class TransactionsView(QWidget):
    def __init__(
        self,
        transactions: TransactionService,
        categorization: CategorizationService,
        prefs: DateTimePrefs | None = None,
        amount_prefs: AmountPrefs | None = None,
        transfers: TransferDetectionService | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("tab_transactions")
        self._transactions = transactions
        self._categorization = categorization
        # A confirmed transfer is surfaced at READ time from transfer_pairs — the
        # transactions rows stay untouched (FIBR-0011 INV-12 / FIBR-0151). Default to
        # a service over the same vault so existing two-arg call sites gain the label
        # without rewiring.
        self._transfers = transfers or TransferDetectionService(transactions.vault)
        # {txn_id: "Transfer to/from <counterparty>"}, rebuilt each refresh().
        self._transfer_labels: dict[int, str] = {}
        self._prefs = prefs or DateTimePrefs(
            DATETIME_SYSTEM, DATETIME_SYSTEM, DATETIME_SYSTEM
        )
        self._amount_prefs = amount_prefs or AmountPrefs("minus", True)
        # The full, unfiltered master list (reloaded only by refresh()).
        self._master: list[tuple[Transaction, Decimal, str, str]] = []
        # The currently-visible (filtered) rows, parallel to the table rows.
        self._rows: list[tuple[Transaction, Decimal, str, str]] = []
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._build_filter_bar())
        layout.addWidget(self._build_table())
        self.refresh()

    # --- construction ------------------------------------------------------ #
    def _build_filter_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._search = QLineEdit()
        self._search.setObjectName("txn_search")
        self._search.setPlaceholderText(self.tr("Search description…"))
        self._search.textChanged.connect(self._apply_filters)

        self._date_enable = QCheckBox(self.tr("Date range"))
        self._date_enable.setObjectName("txn_date_enable")
        self._date_enable.toggled.connect(self._apply_filters)
        self._date_from = QDateEdit()
        self._date_from.setObjectName("txn_date_from")
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_from.dateChanged.connect(self._apply_filters)
        self._date_to = QDateEdit()
        self._date_to.setObjectName("txn_date_to")
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.dateChanged.connect(self._apply_filters)

        self._account = QComboBox()
        self._account.setObjectName("txn_account")
        self._account.currentIndexChanged.connect(self._apply_filters)

        self._category = QComboBox()
        self._category.setObjectName("txn_category")
        self._category.currentIndexChanged.connect(self._apply_filters)

        row.addWidget(self._search)
        row.addWidget(self._date_enable)
        row.addWidget(self._date_from)
        row.addWidget(self._date_to)
        row.addWidget(QLabel(self.tr("Account")))
        row.addWidget(self._account)
        row.addWidget(QLabel(self.tr("Category")))
        row.addWidget(self._category)
        return row

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 5)
        # A distinct objectName so remember_columns keys this table's saved layout
        # uniquely — without it, this 5-column table and the (also 5-column)
        # Statements table share the empty "columns/" key and cross-corrupt each
        # other's widths + drag-reorder order (FIBR-0012 indie-review).
        self._table.setObjectName("transactions_table")
        self._table.setHorizontalHeaderLabels(
            [
                self.tr("Date"),
                self.tr("Amount"),
                self.tr("Description"),
                self.tr("Account"),
                self.tr("Category"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        enable_sorting(self._table)
        remember_columns(self._table)  # widths + drag-reorder, persisted (FIBR-0117)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        return self._table

    # --- data + filtering -------------------------------------------------- #
    def refresh(self) -> None:
        """Reload the master list from the vault and rebuild the account / category
        filter combos (preserving the current selection), then re-apply filters."""
        self._master = self._transactions.list_transactions()
        self._transfer_labels = self._build_transfer_labels()
        self._rebuild_filter_combos()
        self._apply_filters()

    def _build_transfer_labels(self) -> dict[int, str]:
        """Each confirmed-transfer leg's Category-cell label, naming the
        *counterparty* account (FIBR-0151): the debit leg (money out) reads
        "Transfer to <credit account>", the credit leg (money in) reads
        "Transfer from <debit account>". Both names come straight from
        ``confirmed_transfers()`` — no transactions row is read or written (INV-12)."""
        labels: dict[int, str] = {}
        for ct in self._transfers.confirmed_transfers():
            labels[ct.debit.id] = self.tr("Transfer to {account}").format(
                account=ct.to_account
            )
            labels[ct.credit.id] = self.tr("Transfer from {account}").format(
                account=ct.from_account
            )
        return labels

    def _rebuild_filter_combos(self) -> None:
        # On the FIRST build the combos are empty and currentData() is None — which
        # would false-match the Uncategorised item (data None) under findData. Fall
        # back to the "All" sentinel so the initial selection is "All", not
        # "Uncategorised" (D8).
        held_account = (
            self._account.currentData() if self._account.count() else _FILTER_ALL
        )
        held_category = (
            self._category.currentData() if self._category.count() else _FILTER_ALL
        )
        self._loading = True
        try:
            self._account.clear()
            self._account.addItem(self.tr("All accounts"), _FILTER_ALL)
            for account_id, name in self._unique_accounts():
                self._account.addItem(name, account_id)
            self._select_data(self._account, held_account)

            self._category.clear()
            self._category.addItem(self.tr("All categories"), _FILTER_ALL)
            self._category.addItem(self.tr("Uncategorised"), None)
            # The special rows stay ABOVE the grouped section headers: a header
            # also carries userData None, so findData(None) must resolve to
            # Uncategorised, not a header (INV-5). Render only the categories
            # present in the visible rows, grouped/tagged; the helper drops any
            # section left empty by the intersection.
            present = {
                t.category_id
                for t, _d, _a, _c in self._master
                if t.category_id is not None
            }
            grouped = self._categorization.leaf_categories_grouped()
            filtered = [
                (token, [c for c in cats if c.id in present]) for token, cats in grouped
            ]
            add_grouped_categories(self._category, filtered)
            self._select_data(self._category, held_category)
        finally:
            self._loading = False

    def _unique_accounts(self) -> list[tuple[int, str]]:
        """The (account_id, name) pairs present in the master list, name-sorted."""
        seen = {t.account_id: name for t, _d, name, _c in self._master}
        return sorted(seen.items(), key=lambda pair: pair[1].casefold())

    def _select_data(self, combo: QComboBox, data: object) -> None:
        index = combo.findData(data)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _apply_filters(self) -> None:
        if self._loading:
            return
        self._rows = [row for row in self._master if self._matches(row)]
        symbol = self._transactions.base_currency()
        with fill_guard(self._table):
            self._table.setRowCount(len(self._rows))
            for row, (transaction, display, account_name, category_name) in enumerate(
                self._rows
            ):
                self._table.setItem(
                    row,
                    _COL_DATE,
                    SortableItem(
                        format_date(transaction.occurred_on, self._prefs.date_format),
                        transaction.occurred_on,
                    ),
                )
                amount_item = SortableItem(
                    _format_amount(display, symbol, self._amount_prefs.negative_style),
                    display,
                )
                if self._amount_prefs.colour:
                    if display < 0:
                        amount_item.setForeground(_NEGATIVE_TEXT)
                    elif display > 0:
                        amount_item.setForeground(_POSITIVE_TEXT)
                self._table.setItem(row, _COL_AMOUNT, amount_item)
                self._table.setItem(
                    row, _COL_DESCRIPTION, QTableWidgetItem(transaction.description)
                )
                self._table.setItem(row, _COL_ACCOUNT, QTableWidgetItem(account_name))
                self._table.setItem(
                    row, _COL_CATEGORY, self._category_cell(transaction, category_name)
                )
                tag_row(self._table, row, row)  # tag = filtered-list index (sort-safe)

    def _matches(self, row: tuple[Transaction, Decimal, str, str]) -> bool:
        """AND of the active filters (each inactive when unset, INV-9)."""
        transaction = row[0]
        needle = self._search.text().strip().casefold()
        if needle and needle not in transaction.description.casefold():
            return False
        if self._date_enable.isChecked():
            start = self._date_from.date().toString("yyyy-MM-dd")
            end = self._date_to.date().toString("yyyy-MM-dd")
            if not (start <= transaction.occurred_on <= end):
                return False
        account_data = self._account.currentData()
        if account_data is not _FILTER_ALL and transaction.account_id != account_data:
            return False
        category_data = self._category.currentData()
        if (
            category_data is not _FILTER_ALL
            and transaction.category_id != category_data
        ):
            return False
        return True

    def _category_cell(
        self, transaction: Transaction, category_name: str
    ) -> SortableItem:
        """The Category cell (FIBR-0139 D7). **Every** cell is a ``SortableItem`` keyed
        on the **bare** ``category_name`` — so a guessed row sorts *with* its
        plain-named siblings (``SortableItem.__lt__`` uses the sort key only when
        *both* items carry one; a mix of ``SortableItem`` and plain items would fall
        back to a display-text compare and split the group). A ``'library'`` row (a
        built-in guess) shows a "~ guess" marker + tooltip; a rule / manual /
        uncategorised row shows the plain name. Display-only: the sort key (bare name)
        and the id-keyed filter are unaffected (INV-9).

        A confirmed transfer leg overrides the category name with its directional
        "Transfer to/from <account>" label (FIBR-0151); the label is also its sort
        key, so the two legs group together when the column is sorted."""
        label = self._transfer_labels.get(transaction.id)
        if label is not None:
            return SortableItem(label, label)
        is_guess = transaction.category_source == CategorySource.LIBRARY.value and bool(
            category_name
        )
        display = (
            self.tr("{category} ~ guess").format(category=category_name)
            if is_guess
            else category_name
        )
        item = SortableItem(display, category_name)
        if is_guess:
            item.setToolTip(
                self.tr(
                    "Guessed from the built-in library — right-click to confirm "
                    "or change."
                )
            )
        return item

    # --- category set + learning (moved verbatim from HomeView) ------------ #
    def _show_context_menu(self, pos: QPoint) -> None:
        if self._selected_txn() is None:
            return
        menu = QMenu(self)
        action = menu.addAction(self.tr("Set category…"))
        action.triggered.connect(self._on_set_category)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_set_category(self) -> None:
        txn = self._selected_txn()
        if txn is None:
            return
        grouped = self._categorization.leaf_categories_grouped()
        dialog = CategoryPickerDialog(grouped, txn.category_id, self)
        show_modal(dialog, lambda: self._apply_category(dialog, txn))

    def _apply_category(self, dialog: CategoryPickerDialog, txn: Transaction) -> None:
        chosen = dialog.selected_category_id()
        try:
            self._categorization.set_manual_category(txn.id, chosen)
            self.refresh()
            self._maybe_offer_rule(txn.description, chosen)
        except VaultLockedError:
            return

    def _maybe_offer_rule(self, description: str, chosen: int | None) -> None:
        if chosen is None:
            return
        if chosen == self._categorization.would_categorize(description):
            return
        dialog = RuleEditDialog(
            self._categorization.leaf_categories_grouped(), description, chosen, self
        )
        show_modal(dialog, lambda: self._apply_learned_rule(dialog))

    def _apply_learned_rule(self, dialog: RuleEditDialog) -> None:
        pattern, category_id = dialog.pattern(), dialog.selected_category_id()
        if category_id is None:
            return
        try:
            self._categorization.add_rule(pattern, category_id)
            self._categorization.apply_rules()
            self.refresh()
        except VaultLockedError:
            return

    # --- prefs live-update ------------------------------------------------- #
    def set_datetime_prefs(self, prefs: DateTimePrefs) -> None:
        self._prefs = prefs
        self._apply_filters()

    def set_amount_prefs(self, prefs: AmountPrefs) -> None:
        self._amount_prefs = prefs
        self._apply_filters()

    # --- test / shell accessors -------------------------------------------- #
    def _selected_txn(self) -> Transaction | None:
        index = selected_index(self._table)
        return None if index is None else self._rows[index][0]

    def _select_txn(self, txn_id: int) -> None:
        for i, row in enumerate(self._rows):
            if row[0].id == txn_id:
                select_by_index(self._table, i)
                return
