"""HomeView — the Home content page (FIBR-0051 D3).

An internal ``QStackedWidget`` toggling between a **getting-started** page (shown
when the vault holds zero transactions) and the **transaction table** (shown once
there is data). The toggle is observable via ``current_page().objectName()``
(``home_page_empty`` / ``home_page_table``, INV-9a) so the branch is tested by a
stable handle, not by translated button text (INV-10).

``HomeView`` holds **only** a ``TransactionService`` — no ``AccountService``,
because account count can never gate anything (any open vault holds ≥1 account,
INV-9a). ``refresh()`` re-reads the vault and selects the current page;
``transaction_count()`` feeds the status bar (INV-7). The getting-started buttons
are pure navigation affordances — they emit signals the shell routes to its own
actions, so they need no vault data to render.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from PySide6.QtCore import QLocale, Signal
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.services.transactions import TransactionService


class HomeView(QWidget):
    add_account_requested = Signal()
    import_requested = Signal()
    add_transaction_requested = Signal()

    def __init__(self, transactions: TransactionService, parent: QWidget | None = None):
        super().__init__(parent)
        self._transactions = transactions
        self._count = 0

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

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            [
                self.tr("Date"),
                self.tr("Amount"),
                self.tr("Description"),
                self.tr("Account"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._table)
        return page

    def current_page(self) -> QWidget:
        return self._stack.currentWidget()

    def transaction_count(self) -> int:
        return self._count

    def refresh(self) -> None:
        rows = self._transactions.list_transactions()
        symbol = self._transactions.base_currency()
        self._count = len(rows)
        self._table.setRowCount(len(rows))
        for row, (transaction, display, account_name) in enumerate(rows):
            self._table.setItem(row, 0, QTableWidgetItem(transaction.occurred_on))
            self._table.setItem(
                row, 1, QTableWidgetItem(_format_amount(display, symbol))
            )
            self._table.setItem(row, 2, QTableWidgetItem(transaction.description))
            self._table.setItem(row, 3, QTableWidgetItem(account_name))
        # Getting-started iff zero transactions, else the table (INV-9a).
        self._stack.setCurrentIndex(1 if rows else 0)


def _format_amount(display: Decimal, symbol: str) -> str:
    # Currency → QLocale.toCurrencyString with the base-currency symbol, so the
    # amount carries its currency and isn't reformatted to the locale's own
    # (coding.md § 5.2). A stored amount reconstructs to a finite Decimal, so its
    # exponent is an int. toCurrencyString has no Decimal overload, so the float()
    # is a DISPLAY-ONLY, bounded conversion — storage/computation stay exact
    # Decimal (D1); only the on-screen string crosses to float.
    decimals = max(0, -cast(int, display.as_tuple().exponent))
    return QLocale().toCurrencyString(float(display), symbol, decimals)
