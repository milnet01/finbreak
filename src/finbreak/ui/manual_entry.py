"""ManualEntryDialog — add one transaction (FIBR-0051 D3).

The Account/Date/Amount/Description form lifted out of the old ``MainWindow``,
now a modal ``QDialog`` opened by the ``Manual entry`` action. On **Add** it calls
the unchanged ``TransactionService.add_transaction``; a reused ``parse_transaction``
``ValueError`` (invalid amount/description) is shown in-dialog and the dialog
stays open (INV-9). On a successful Add it emits ``committed`` — the shell shows a
fresh Home + updates the status count — and the shell closes it. Shown
non-blocking (``setModal(True)`` + ``show()``) and tracked by the shell so an
auto-lock closes it before the vault shuts (INV-4b).
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.transactions import TransactionService


class ManualEntryDialog(QDialog):
    committed = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._transactions = TransactionService(service.vault)
        self._accounts = AccountService(service.vault)
        self.setWindowTitle(self.tr("Add transaction"))

        self._account = QComboBox()
        for account in self._accounts.list_accounts():
            self._account.addItem(account.name, account.id)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        # Unambiguous ISO-style YYYY/MM/DD, not the locale's ambiguous M/D/YY
        # (a user-configurable format is a Settings-phase concern, FIBR-0014).
        self._date.setDisplayFormat("yyyy/MM/dd")
        self._amount = QLineEdit()
        self._amount.setPlaceholderText(self.tr("e.g. -12.34"))
        self._description = QLineEdit()
        self._error = QLabel()

        form = QFormLayout()
        form.addRow(self.tr("Account"), self._account)
        form.addRow(self.tr("Date"), self._date)
        form.addRow(self.tr("Amount"), self._amount)
        form.addRow(self.tr("Description"), self._description)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._add_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._add_button.setText(self.tr("Add"))
        # Ok drives _on_add (which keeps the dialog open on error / emits committed
        # on success), NOT accept() — the shell owns the close on committed.
        buttons.accepted.connect(self._on_add)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

    @Slot()
    def _on_add(self) -> None:
        self._error.clear()
        account_id = self._account.currentData()
        if account_id is None:  # no account (empty picker) — a defensive UI guard,
            # unreachable on any open vault (≥1 account always exists, INV-9).
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
        self.committed.emit()
