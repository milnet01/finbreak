"""HomeView — the Home content page (FIBR-0051 D3; category column + manual set +
learning added by FIBR-0010 D10/D11).

An internal ``QStackedWidget`` toggling between a **getting-started** page (shown
when the vault holds zero transactions) and the **transaction table** (shown once
there is data). The toggle is observable via ``current_page().objectName()``
(``home_page_empty`` / ``home_page_table``, INV-9a).

The table has a **Category** column and a right-click **Set category…** that sets
a row **manual** (highest-priority, never re-filed) and — when the manual choice
disagrees with the current rules — offers to learn a rule (D11). ``HomeView``
holds a ``TransactionService`` **and** a ``CategorizationService`` (category
assignment genuinely needs category data — the FIBR-0051 "Home holds only
TransactionService" note is superseded here). ``refresh()`` re-reads the vault and
selects the current page; ``transaction_count()`` feeds the status bar (INV-7).
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from PySide6.QtCore import QLocale, QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.datetime_format import format_date
from finbreak.errors import VaultLockedError
from finbreak.models import Transaction
from finbreak.services.auth import (
    DATETIME_SYSTEM,
    AmountPrefs,
    DateTimePrefs,
)
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService
from finbreak.ui.category_picker import CategoryPickerDialog
from finbreak.ui.modal import show_modal
from finbreak.ui.rules import RuleEditDialog

# Fixed column indices (the table's shape; headers are the translated labels).
_COL_DATE = 0
_COL_AMOUNT = 1
_COL_DESCRIPTION = 2
_COL_ACCOUNT = 3
_COL_CATEGORY = 4

# Direction tints for the Amount column when colour is on (FIBR-0105 D3). Fixed
# mid-tones chosen to read on the dark-default theme (ADR-0002) and stay legible
# on light; palette-adaptive re-tinting is FIBR-0014.
_NEGATIVE_TEXT = QColor(224, 108, 117)  # soft red — money out
_POSITIVE_TEXT = QColor(152, 195, 121)  # soft green — money in


class HomeView(QWidget):
    add_account_requested = Signal()
    import_requested = Signal()
    add_transaction_requested = Signal()

    def __init__(
        self,
        transactions: TransactionService,
        categorization: CategorizationService,
        prefs: DateTimePrefs | None = None,
        amount_prefs: AmountPrefs | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._transactions = transactions
        self._categorization = categorization
        # Display-only date formatting input (FIBR-0083 D6); absent -> the
        # zero-config all-"system" default. The shell passes the vault's prefs.
        self._prefs = prefs or DateTimePrefs(
            DATETIME_SYSTEM, DATETIME_SYSTEM, DATETIME_SYSTEM
        )
        # Display-only amount formatting input (FIBR-0105); absent -> the
        # friendly default (minus + colour on). The shell passes the vault's prefs.
        self._amount_prefs = amount_prefs or AmountPrefs("minus", True)
        self._count = 0
        # The rendered rows, parallel to the table rows (the row -> transaction map
        # is the table's row order, same order as list_transactions).
        self._rows: list[tuple[Transaction, Decimal, str, str]] = []

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_getting_started())
        self._stack.addWidget(self._build_table_page())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self.refresh()

    def _build_getting_started(self) -> QWidget:
        page = QWidget()
        page.setObjectName("home_page_empty")

        add_account = QPushButton(self.tr("Add an account"))
        import_statement = QPushButton(self.tr("Import a statement"))
        add_transaction = QPushButton(self.tr("Add a transaction"))
        add_account.clicked.connect(self.add_account_requested)
        import_statement.clicked.connect(self.import_requested)
        add_transaction.clicked.connect(self.add_transaction_requested)

        layout = QVBoxLayout(page)
        layout.addStretch()
        layout.addWidget(QLabel(self.tr("Welcome to finbreak. To get started:")))
        layout.addWidget(add_account)
        layout.addWidget(import_statement)
        layout.addWidget(add_transaction)
        layout.addStretch()
        return page

    def _build_table_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("home_page_table")

        self._table = QTableWidget(0, 5)
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
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Right-click a row to set its category (INV-10).
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._table)
        return page

    def current_page(self) -> QWidget:
        return self._stack.currentWidget()

    def transaction_count(self) -> int:
        return self._count

    def refresh(self) -> None:
        self._rows = self._transactions.list_transactions()
        symbol = self._transactions.base_currency()
        self._count = len(self._rows)
        self._table.setRowCount(len(self._rows))
        for row, (transaction, display, account_name, category_name) in enumerate(
            self._rows
        ):
            self._table.setItem(
                row,
                _COL_DATE,
                QTableWidgetItem(
                    format_date(transaction.occurred_on, self._prefs.date_format)
                ),
            )
            amount_item = QTableWidgetItem(
                _format_amount(display, symbol, self._amount_prefs.negative_style)
            )
            # Colour marks direction only when the pref is on; a fresh item per
            # render means a colour-off pass leaves no stale foreground (INV-4).
            # Zero is left at the default colour (and can't occur via the service,
            # which rejects zero amounts — this is the defensive branch).
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
            self._table.setItem(row, _COL_CATEGORY, QTableWidgetItem(category_name))
        # Getting-started iff zero transactions, else the table (INV-9a).
        self._stack.setCurrentIndex(1 if self._rows else 0)

    # --- category set + learning (INV-10/INV-11) --------------------------- #
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
        leaves = self._categorization.leaf_categories()
        dialog = CategoryPickerDialog(leaves, txn.category_id, self)
        # Non-blocking (FIBR-0065): a lock while the picker is open destroys it
        # before _apply_category can run, so no read hits a deleted C++ object.
        show_modal(dialog, lambda: self._apply_category(dialog, txn))

    def _apply_category(self, dialog: CategoryPickerDialog, txn: Transaction) -> None:
        chosen = dialog.selected_category_id()
        # The VaultLockedError guard is now defense-in-depth: the non-blocking
        # conversion (INV-2) means a lock destroys the picker before this slot runs.
        try:
            self._categorization.set_manual_category(txn.id, chosen)
            self.refresh()  # the manual change is visible immediately
            self._maybe_offer_rule(txn.description, chosen)
        except VaultLockedError:
            return

    def _maybe_offer_rule(self, description: str, chosen: int | None) -> None:
        """Offer to learn a rule iff the manual choice is a leaf that disagrees with
        what the current rules would produce (D11). Accept → create the rule (top
        priority) + re-apply; dismiss → only the one corrected row changed. ``would``
        is read against the rules as they stand, before any new rule is added."""
        if chosen is None:
            return  # a manual clear is not a rule to learn
        if chosen == self._categorization.would_categorize(description):
            return  # the rules already agree — no nag
        dialog = RuleEditDialog(
            self._categorization.leaf_categories(), description, chosen, self
        )
        show_modal(dialog, lambda: self._apply_learned_rule(dialog))

    def _apply_learned_rule(self, dialog: RuleEditDialog) -> None:
        pattern, category_id = dialog.pattern(), dialog.selected_category_id()
        if category_id is None:
            return  # OK is gated on a selectable category; defensive (FIBR-0079)
        try:
            self._categorization.add_rule(pattern, category_id)
            self._categorization.apply_rules()  # propagate to other auto rows
            self.refresh()  # the propagation to other auto rows is now visible
        except VaultLockedError:
            return

    def set_datetime_prefs(self, prefs: DateTimePrefs) -> None:
        """Adopt new display prefs and re-render (FIBR-0083 D7)."""
        self._prefs = prefs
        self.refresh()

    def set_amount_prefs(self, prefs: AmountPrefs) -> None:
        """Adopt new amount-display prefs and re-render (FIBR-0105 D1)."""
        self._amount_prefs = prefs
        self.refresh()

    # --- test / shell accessors -------------------------------------------- #
    def _selected_txn(self) -> Transaction | None:
        rows = {i.row() for i in self._table.selectedItems()}
        if len(rows) != 1:
            return None
        return self._rows[next(iter(rows))][0]

    def _select_txn(self, txn_id: int) -> None:
        for i, row in enumerate(self._rows):
            if row[0].id == txn_id:
                self._table.selectRow(i)
                return


def _format_amount(display: Decimal, symbol: str, negative_style: str = "minus") -> str:
    # Currency → QLocale.toCurrencyString with the base-currency symbol, so the
    # amount carries its currency and isn't reformatted to the locale's own
    # (coding.md § 5.2). A stored amount reconstructs to a finite Decimal, so its
    # exponent is an int. toCurrencyString has no Decimal overload, so the float()
    # is a DISPLAY-ONLY, bounded conversion — storage/computation stay exact
    # Decimal (D1); only the on-screen string crosses to float.
    #
    # Both styles format the MAGNITUDE via QLocale (grouping / decimal separator /
    # symbol placement stay locale-correct), then the sign notation is applied
    # EXPLICITLY for a negative (FIBR-0105 D2) — NOT delegated to QLocale's
    # negative-currency pattern, which is parentheses only on some locales and a
    # minus sign on the C locale + others, making "brackets" non-deterministic.
    decimals = max(0, -cast(int, display.as_tuple().exponent))
    magnitude = QLocale().toCurrencyString(float(abs(display)), symbol, decimals)
    if display < 0:
        return f"({magnitude})" if negative_style == "brackets" else f"-{magnitude}"
    return magnitude
