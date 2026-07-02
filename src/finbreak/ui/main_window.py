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

from finbreak.services.auth import AuthService
from finbreak.services.transactions import TransactionService


class MainWindow(QWidget):
    locked = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._transactions = TransactionService(service.vault)

        self.setWindowTitle(self.tr("finbreak"))

        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._amount = QLineEdit()
        self._amount.setPlaceholderText(self.tr("e.g. -12.34"))
        self._description = QLineEdit()
        self._add_button = QPushButton(self.tr("Add"))
        self._error = QLabel()

        form = QFormLayout()
        form.addRow(self.tr("Date"), self._date)
        form.addRow(self.tr("Amount"), self._amount)
        form.addRow(self.tr("Description"), self._description)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            [self.tr("Date"), self.tr("Amount"), self.tr("Description")]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._lock_button = QPushButton(self.tr("Lock"))

        buttons = QHBoxLayout()
        buttons.addWidget(self._add_button)
        buttons.addStretch()
        buttons.addWidget(self._lock_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self._error)
        layout.addWidget(self._table)

        self._add_button.clicked.connect(self._on_add)
        self._lock_button.clicked.connect(self._on_lock)

        self._refresh()

    @Slot()
    def _on_add(self) -> None:
        self._error.clear()
        occurred_on = self._date.date().toString(Qt.DateFormat.ISODate)
        try:
            self._transactions.add_transaction(
                occurred_on, self._amount.text(), self._description.text()
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
        for row, (transaction, display) in enumerate(rows):
            self._table.setItem(row, 0, QTableWidgetItem(transaction.occurred_on))
            self._table.setItem(
                row, 1, QTableWidgetItem(_format_amount(display, symbol))
            )
            self._table.setItem(row, 2, QTableWidgetItem(transaction.description))


def _format_amount(display: Decimal, symbol: str) -> str:
    # Currency → QLocale.toCurrencyString with the base-currency symbol, so the
    # amount carries its currency and isn't reformatted to the locale's own
    # (coding.md § 5.2). A stored amount reconstructs to a finite Decimal, so its
    # exponent is an int. toCurrencyString has no Decimal overload, so the float()
    # is a DISPLAY-ONLY, bounded conversion — storage/computation stay exact
    # Decimal (D1); only the on-screen string crosses to float.
    decimals = max(0, -cast(int, display.as_tuple().exponent))
    return QLocale().toCurrencyString(float(display), symbol, decimals)
