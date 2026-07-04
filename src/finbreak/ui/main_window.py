"""Main window — add one transaction, see the table, lock (FIBR-0004 INV-4/INV-6).

All strings go through ``tr()`` and every widget sits in a Qt layout manager, so
the screen is translation-ready and mirrors for RTL locales with no rework
(coding.md § 5.2). Amounts render via ``QLocale``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from PySide6.QtCore import QDate, QLocale, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.transactions import TransactionService


class MainWindow(QWidget):
    locked = Signal()
    manage_accounts = Signal()
    manage_categories = Signal()
    import_transactions = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._transactions = TransactionService(service.vault)
        self._accounts = AccountService(service.vault)

        self.setWindowTitle(self.tr("finbreak"))

        self._account = QComboBox()
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        # Unambiguous ISO-style YYYY/MM/DD, not the locale's ambiguous M/D/YY
        # (a user-configurable format is a Settings-phase concern, FIBR-0014).
        self._date.setDisplayFormat("yyyy/MM/dd")
        self._amount = QLineEdit()
        self._amount.setPlaceholderText(self.tr("e.g. -12.34"))
        self._description = QLineEdit()
        self._add_button = QPushButton(self.tr("Add"))
        self._error = QLabel()

        form = QFormLayout()
        form.addRow(self.tr("Account"), self._account)
        form.addRow(self.tr("Date"), self._date)
        form.addRow(self.tr("Amount"), self._amount)
        form.addRow(self.tr("Description"), self._description)

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

        self._manage_button = QPushButton(self.tr("Manage accounts…"))
        self._categories_button = QPushButton(self.tr("Manage categories…"))
        self._import_button = QPushButton(self.tr("Import transactions…"))
        self._lock_button = QPushButton(self.tr("Lock"))

        buttons = QHBoxLayout()
        buttons.addWidget(self._add_button)
        buttons.addStretch()
        buttons.addWidget(self._manage_button)
        buttons.addWidget(self._categories_button)
        buttons.addWidget(self._import_button)
        buttons.addWidget(self._lock_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self._error)
        layout.addWidget(self._table)

        self._add_button.clicked.connect(self._on_add)
        self._manage_button.clicked.connect(self.manage_accounts)
        self._categories_button.clicked.connect(self.manage_categories)
        self._import_button.clicked.connect(self.import_transactions)
        self._lock_button.clicked.connect(self._on_lock)

        self._reload_accounts()
        self._refresh()

    def _reload_accounts(self) -> None:
        """(Re)fill the account picker, each item carrying its account_id."""
        self._account.clear()
        for account in self._accounts.list_accounts():
            self._account.addItem(account.name, account.id)

    @Slot()
    def _on_add(self) -> None:
        self._error.clear()
        account_id = self._account.currentData()
        if account_id is None:  # no account selected (empty picker) — nothing to do
            self._error.setText(self.tr("Create an account first."))
            return
        occurred_on = self._date.date().toString(Qt.DateFormat.ISODate)
        try:
            self._transactions.add_transaction(
                account_id, occurred_on, self._amount.text(), self._description.text()
            )
        except ValueError as exc:
            self._error.setText(str(exc))
            return
        self._amount.clear()
        self._description.clear()
        self._refresh()

    @Slot()
    def _on_lock(self) -> None:
        self._service.lock()
        self.locked.emit()

    def _refresh(self) -> None:
        rows = self._transactions.list_transactions()
        symbol = self._transactions.base_currency()
        self._table.setRowCount(len(rows))
        for row, (transaction, display, account_name) in enumerate(rows):
            self._table.setItem(row, 0, QTableWidgetItem(transaction.occurred_on))
            self._table.setItem(
                row, 1, QTableWidgetItem(_format_amount(display, symbol))
            )
            self._table.setItem(row, 2, QTableWidgetItem(transaction.description))
            self._table.setItem(row, 3, QTableWidgetItem(account_name))


def _format_amount(display: Decimal, symbol: str) -> str:
    # Currency → QLocale.toCurrencyString with the base-currency symbol, so the
    # amount carries its currency and isn't reformatted to the locale's own
    # (coding.md § 5.2). A stored amount reconstructs to a finite Decimal, so its
    # exponent is an int. toCurrencyString has no Decimal overload, so the float()
    # is a DISPLAY-ONLY, bounded conversion — storage/computation stay exact
    # Decimal (D1); only the on-screen string crosses to float.
    decimals = max(0, -cast(int, display.as_tuple().exponent))
    return QLocale().toCurrencyString(float(display), symbol, decimals)
