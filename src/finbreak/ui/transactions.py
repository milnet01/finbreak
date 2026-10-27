"""TransactionsView — the searchable/filterable transaction table (FIBR-0012 D7/D8).

The transaction table and its right-click **Set category…** → learn-a-rule chain
moved here from the old ``HomeView`` (Home is now the dashboard); the table is now
a ``TransactionsModel`` that sorts itself (FIBR-0097). Added on top: a four-filter
bar — search (description substring), date range, account, and category — each
independently active and **AND-combined** (INV-9). ``refresh()`` reloads the master
``list_transactions()`` list (tab activation only); the filters run in memory over
that list and never re-hit the DB.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import (
    QAbstractTableModel,
    QCollator,
    QDate,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    Qt,
)
from PySide6.QtGui import QBrush, QGuiApplication
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
    QTableView,
    QVBoxLayout,
    QWidget,
)

from finbreak.datetime_format import format_date, today_qdate
from finbreak.errors import VaultLockedError
from finbreak.models import CategorySource, NegativeStyle, Transaction
from finbreak.services.auth import (
    DATETIME_SYSTEM,
    DEFAULT_CLIPBOARD_CLEAR_SECONDS,
    AmountPrefs,
    DateTimePrefs,
)
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.ui._amount import _NEGATIVE_TEXT, _POSITIVE_TEXT, _format_amount
from finbreak.ui._clipboard import ClipboardAutoClear
from finbreak.ui._table_state import enable_sorting, remember_columns
from finbreak.ui._widgets import add_grouped_categories
from finbreak.ui.category_picker import CategoryPickerDialog
from finbreak.ui.modal import show_modal
from finbreak.ui.rules import RuleEditDialog

# Fixed column indices (the table's shape; headers are the translated labels).
# Currency sits adjacent to Amount (natural reading: number, then its currency).
_COL_DATE = 0
_COL_AMOUNT = 1
_COL_CURRENCY = 2
_COL_DESCRIPTION = 3
_COL_ACCOUNT = 4
_COL_CATEGORY = 5

# The "All accounts" / "All categories" sentinel — a real object so it can never be
# confused with the ``None`` that marks the Uncategorised category (D8).
_FILTER_ALL = object()

_Row = tuple[Transaction, Decimal, str, str]  # (txn, display amount, account, category)
_Index = QModelIndex | QPersistentModelIndex
_ROOT = QModelIndex()  # the invalid index: a flat table's only parent


@dataclass(frozen=True)
class _Render:
    """What one fill renders with, built by the view once per fill (FIBR-0097
    § 4.1). The translated strings arrive already translated, so they keep the
    ``TransactionsView`` translation context (§ 4.4)."""

    date_format: str
    amount_prefs: AmountPrefs
    currency: str  # the base-currency ISO code (FIBR-0153 INV-6)
    transfer_labels: dict[int, str]  # {txn_id: "Transfer to/from <account>"}
    guess_template: str  # "{category} ~ guess"
    guess_tooltip: str


class TransactionsModel(QAbstractTableModel):
    """The Transactions table's rows (FIBR-0097). Qt asks ``data`` only for the
    cells it paints, so a refill formats a screenful, not every row.

    The row list is the view's own ``_rows`` object, sorted in place, so view row
    ``i`` is ``_rows[i]``."""

    def __init__(self, headers: list[str], parent: QObject | None = None):
        super().__init__(parent)
        self._headers = headers
        self._rows: list[_Row] = []
        self._render: _Render | None = None
        # The last sort Qt asked for; a refill re-applies it. Date, newest first,
        # is the header's own initial indicator.
        self._sort = (_COL_DATE, Qt.SortOrder.DescendingOrder)

    def set_rows(self, rows: list[_Row], render: _Render) -> None:
        self.beginResetModel()
        self._rows = rows
        self._render = render
        self._sort_rows(*self._sort)
        self.endResetModel()

    def clear(self) -> None:
        """Drop the rows AND the render: its transfer labels name accounts
        (FIBR-0097 INV-5)."""
        self.beginResetModel()
        self._rows = []
        self._render = None
        self.endResetModel()

    def row_at(self, row: int) -> _Row:
        return self._rows[row]

    def rowCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._headers)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._headers)
        ):
            return self._headers[section]
        return super().headerData(section, orientation, role)  # row numbers

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        render = self._render
        if render is None or not index.isValid() or index.row() >= len(self._rows):
            return None  # a repaint between a reset and its layout (§ 6)
        row = self._rows[index.row()]
        transaction, display, _account, category = row
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._text(row, column, render)
        if (
            role == Qt.ItemDataRole.ForegroundRole
            and column == _COL_AMOUNT
            and render.amount_prefs.colour
            and display != 0
        ):
            return QBrush(_NEGATIVE_TEXT if display < 0 else _POSITIVE_TEXT)
        if (
            role == Qt.ItemDataRole.ToolTipRole
            and column == _COL_CATEGORY
            and self._is_guess(transaction, category, render)
        ):
            return render.guess_tooltip
        return None

    def sort(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        self._sort = (column, order)
        self.layoutAboutToBeChanged.emit()
        old_rows = list(self._rows)
        self._sort_rows(column, order)
        new_row = {id(row): i for i, row in enumerate(self._rows)}
        # Persistent indexes (the selection) follow their transaction, not their
        # row number, so the next action lands on the row the user picked.
        old = self.persistentIndexList()
        self.changePersistentIndexList(
            old,
            [self.index(new_row[id(old_rows[i.row()])], i.column()) for i in old],
        )
        self.layoutChanged.emit()

    def _sort_rows(self, column: int, order: Qt.SortOrder) -> None:
        render = self._render
        if render is None or not 0 <= column < len(self._headers):
            return
        descending = order == Qt.SortOrder.DescendingOrder
        # list.sort is stable both ways, so tied rows keep their order.
        if column in (_COL_DATE, _COL_AMOUNT, _COL_CATEGORY):
            self._rows.sort(
                key=lambda row: self._key(row, column, render), reverse=descending
            )
            return
        # The text columns sort as the QTableWidget did, by the user's locale, so
        # "apple" sorts before "Banana". QCollator matched its order on 300 random
        # sets (2026-10-22); built per sort, so a changed locale is honoured.
        collator = QCollator()
        self._rows.sort(
            key=lambda row: collator.sortKey(self._text(row, column, render)),
            reverse=descending,
        )

    @staticmethod
    def _is_guess(transaction: Transaction, category: str, render: _Render) -> bool:
        """A ``library`` row (a built-in guess) with a name and no transfer label
        shows the "~ guess" marker and tooltip (FIBR-0139 D7)."""
        return (
            transaction.category_source == CategorySource.LIBRARY.value
            and bool(category)
            and transaction.id not in render.transfer_labels
        )

    def _text(self, row: _Row, column: int, render: _Render) -> str:
        transaction, display, account, category = row
        if column == _COL_DATE:
            return format_date(transaction.occurred_on, render.date_format)
        if column == _COL_AMOUNT:
            return _format_amount(
                display, render.currency, render.amount_prefs.negative_style
            )
        if column == _COL_CURRENCY:
            return render.currency
        if column == _COL_DESCRIPTION:
            return transaction.description
        if column == _COL_ACCOUNT:
            return account
        label = render.transfer_labels.get(transaction.id)
        if label is not None:
            return label  # a confirmed transfer leg's label wins (FIBR-0151)
        if self._is_guess(transaction, category, render):
            return render.guess_template.format(category=category)
        return category

    @staticmethod
    def _key(row: _Row, column: int, render: _Render) -> str | Decimal:
        """What a keyed column sorts by. Date sorts on the ISO date and Amount on
        the ``Decimal``, never their formatted text. Category sorts on the BARE
        name, so a guessed row sorts with its plain-named siblings, or on a
        transfer leg's label, so the two legs group. Category compares as plain
        Python strings, as its ``SortableItem`` keys did. One key type per column,
        so no comparison mixes types."""
        transaction, display, _account, category = row
        if column == _COL_DATE:
            return transaction.occurred_on
        if column == _COL_AMOUNT:
            return display
        return render.transfer_labels.get(transaction.id, category)


class TransactionsView(QWidget):
    def __init__(
        self,
        transactions: TransactionService,
        categorization: CategorizationService,
        prefs: DateTimePrefs | None = None,
        amount_prefs: AmountPrefs | None = None,
        transfers: TransferDetectionService | None = None,
        clipboard: ClipboardAutoClear | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("tab_transactions")
        self._transactions = transactions
        self._categorization = categorization
        # The copy-with-auto-clear helper (FIBR-0032). An INJECTED guard keeps the
        # owner its caller gave it — the shell owns the one it wires. One built
        # here, for standalone / test construction, is owned by our parent, or by
        # the application object where there is none, as recovery_key.py does it.
        # Never by the view: `MainWindow._clear_live` destroys the whole workspace
        # on every lock and rebuild, so a guard parented here dies with its clear
        # timer still pending and the copied value stays on the clipboard for good
        # (FIBR-0316; the FIBR-0310 R1 rule at its third site).
        if clipboard is None:
            owner: QObject | None = parent or QGuiApplication.instance()
            self._clipboard = ClipboardAutoClear(
                QGuiApplication.clipboard(),
                seconds_provider=lambda: DEFAULT_CLIPBOARD_CLEAR_SECONDS,
                parent=owner,
            )
        else:
            self._clipboard = clipboard
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
        self._amount_prefs = amount_prefs or AmountPrefs(NegativeStyle.MINUS, True)
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

    def _build_table(self) -> QTableView:
        self._model = TransactionsModel(
            [
                self.tr("Date"),
                self.tr("Amount"),
                self.tr("Currency"),
                self.tr("Description"),
                self.tr("Account"),
                self.tr("Category"),
            ],
            self,
        )
        self._table = QTableView()
        # Before every header call: a QTableView header has no sections until it
        # has a model, so remember_columns would capture an empty default.
        self._table.setModel(self._model)
        # A distinct objectName so remember_columns keys this table's saved layout
        # uniquely — without it, this table and the (also multi-column) Statements
        # table share the empty "columns/" key and cross-corrupt each other's widths
        # + drag-reorder order (FIBR-0012 indie-review).
        self._table.setObjectName("transactions_table")
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        enable_sorting(self._table)
        remember_columns(self._table)  # widths + drag-reorder, persisted (FIBR-0117)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        return self._table

    # --- data + filtering -------------------------------------------------- #
    def clear_rows(self) -> None:
        """Drop BOTH cached row lists at LOCK time (FIBR-0322).

        ``_master`` is the unfiltered list ``_rows`` is derived from, so it holds
        every decrypted transaction whether or not a filter is showing it —
        clearing the visible half alone would leave the larger one behind.
        """
        self._master = []
        self._rows = []
        self._transfer_labels = {}  # "Transfer to <account>" per row
        self._model.clear()  # its rows and its render (FIBR-0097 INV-5)

    def refresh(self) -> None:
        """Reload the master list from the vault and rebuild the account / category
        filter combos (preserving the current selection), then re-apply filters."""
        self._master = self._transactions.list_transactions()
        self._transfer_labels = self._build_transfer_labels()
        self._rebuild_filter_combos()
        self._seed_date_range()
        self._apply_filters()

    def _seed_date_range(self) -> None:
        """Span the loaded rows, so ticking "Date range" narrows nothing yet.

        A bare ``QDateEdit`` starts at Qt's own minimum, 2000-01-01. Ticking the
        box therefore filtered to a single day nobody banks on and emptied the
        table with no message -- the user's first act with the control made their
        transactions disappear (FIBR-0327).

        Only while the box is UNCHECKED, so a range the user set is never
        overwritten by a later refresh; and under ``_loading``, because assigning
        a date emits ``dateChanged``.
        """
        if self._date_enable.isChecked():
            return
        dates = [row[0].occurred_on for row in self._master]
        first = QDate.fromString(min(dates), "yyyy-MM-dd") if dates else QDate()
        last = QDate.fromString(max(dates), "yyyy-MM-dd") if dates else QDate()
        if not first.isValid() or not last.isValid():
            # No rows, or a stored date this widget cannot read: today spans
            # nothing, which is honest, and the user picks from there.
            first = last = today_qdate()
        self._loading = True
        try:
            self._date_from.setDate(first)
            self._date_to.setDate(last)
        finally:
            self._loading = False

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
            add_grouped_categories(
                self._category,
                filtered,
                self._categorization.sub_category_parent_names(),
            )
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
        matches = self._matches()
        self._rows = [row for row in self._master if matches(row)]
        self._model.set_rows(
            self._rows,
            _Render(
                date_format=self._prefs.date_format,
                amount_prefs=self._amount_prefs,
                currency=self._transactions.base_currency(),
                transfer_labels=self._transfer_labels,
                guess_template=self.tr("{category} ~ guess"),
                guess_tooltip=self.tr(
                    "Guessed from the built-in library — right-click to confirm "
                    "or change."
                ),
            ),
        )

    def _matches(self) -> Callable[[tuple[Transaction, Decimal, str, str]], bool]:
        """The AND of the active filters (each inactive when unset, INV-9), as a
        predicate. The widget state is read once here, not once per row."""
        needle = self._search.text().strip().casefold()
        dated = self._date_enable.isChecked()
        start = self._date_from.date().toString("yyyy-MM-dd")
        end = self._date_to.date().toString("yyyy-MM-dd")
        account_data = self._account.currentData()
        category_data = self._category.currentData()

        def matches(row: tuple[Transaction, Decimal, str, str]) -> bool:
            transaction = row[0]
            return (
                (not needle or needle in transaction.description.casefold())
                and (not dated or start <= transaction.occurred_on <= end)
                and (
                    account_data is _FILTER_ALL
                    or transaction.account_id == account_data
                )
                and (
                    category_data is _FILTER_ALL
                    or transaction.category_id == category_data
                )
            )

        return matches

    # --- category set + learning (moved verbatim from HomeView) ------------ #
    def _show_context_menu(self, pos: QPoint) -> None:
        if self._selected_txn() is None:
            return
        menu = QMenu(self)
        copy_amount = menu.addAction(self.tr("Copy amount"))
        copy_amount.triggered.connect(self._on_copy_amount)
        copy_description = menu.addAction(self.tr("Copy description"))
        copy_description.triggered.connect(self._on_copy_description)
        menu.addSeparator()
        action = menu.addAction(self.tr("Set category…"))
        action.triggered.connect(self._on_set_category)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_copy_amount(self) -> None:
        # The already-rendered Amount cell text (WYSIWYG) — no vault read, so this is
        # lock-safe even if the auto-lock fired while the menu was open (INV-8/D1).
        row = self._selected_row()
        if row is None:
            return
        text = self._model.index(row, _COL_AMOUNT).data()
        self._clipboard.copy(text or "")

    def _on_copy_description(self) -> None:
        txn = self._selected_txn()
        if txn is None:
            return
        self._clipboard.copy(txn.description)  # in-memory description — no vault read

    def _on_set_category(self) -> None:
        txn = self._selected_txn()
        if txn is None:
            return
        try:
            grouped = self._categorization.leaf_categories_grouped()
            parent_names = self._categorization.sub_category_parent_names()
        except VaultLockedError:
            # The right-click menu is a nested event loop, so the idle
            # auto-lock can fire before this runs; return quietly, like the
            # sibling handlers (FIBR-0396).
            return
        dialog = CategoryPickerDialog(
            grouped,
            txn.category_id,
            self,
            parent_names=parent_names,
        )
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
            self._categorization.leaf_categories_grouped(),
            description,
            chosen,
            self,
            parent_names=self._categorization.sub_category_parent_names(),
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
    def _selected_row(self) -> int | None:
        """The single selected view row, or ``None`` unless exactly one is."""
        rows = self._table.selectionModel().selectedRows()
        return rows[0].row() if len(rows) == 1 else None

    def _selected_txn(self) -> Transaction | None:
        row = self._selected_row()
        return None if row is None else self._model.row_at(row)[0]

    def _select_txn(self, txn_id: int) -> None:
        for i, row in enumerate(self._rows):
            if row[0].id == txn_id:
                self._table.clearSelection()
                self._table.selectRow(i)
                return
