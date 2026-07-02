"""First-run screen — set the master password + base currency (FIBR-0004 INV-5).

The password is entered twice; a mismatch, an empty password, or an unsupported
currency is a form-boundary error that creates no vault and derives no key. On
success the vault is created and the app is left unlocked.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.models import KdfParams
from finbreak.services.auth import CURRENCY_EXPONENTS, AuthService
from finbreak.ui._worker import DeriveWorker


class FirstRunWidget(QWidget):
    completed = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._worker: DeriveWorker | None = None
        self._pending_params: KdfParams | None = None
        self._pending_currency = ""

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._currency = QComboBox()
        self._currency.addItems(list(CURRENCY_EXPONENTS))
        self._submit = QPushButton(self.tr("Create vault"))
        self._error = QLabel()

        form = QFormLayout()
        form.addRow(self.tr("Master password"), self._password)
        form.addRow(self.tr("Confirm password"), self._confirm)
        form.addRow(self.tr("Base currency"), self._currency)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                self.tr(
                    "There is no password recovery — if you forget this password, "
                    "your data cannot be recovered."
                )
            )
        )
        layout.addLayout(form)
        layout.addWidget(self._submit)
        layout.addWidget(self._error)

        self._submit.clicked.connect(self._on_submit)

    @Slot()
    def _on_submit(self) -> None:
        self._error.clear()
        currency = self._currency.currentText()
        password = bytearray(self._password.text().encode("utf-8"))
        confirm = bytearray(self._confirm.text().encode("utf-8"))
        try:
            self._service.validate_first_run(password, confirm, currency)
        except ValueError as exc:
            self._error.setText(str(exc))
            return

        # validate_first_run wiped the buffers above; re-encode a fresh one for
        # the derivation (the QLineEdit str is the unavoidable best-effort leak).
        self._pending_params = self._service.new_params()
        self._pending_currency = currency
        derive_password = bytearray(self._password.text().encode("utf-8"))
        self._password.clear()
        self._confirm.clear()
        self._submit.setEnabled(False)

        self._worker = DeriveWorker(derive_password, self._pending_params)
        self._worker.done.connect(self._on_derived)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    @Slot(bytes)
    def _on_derived(self, raw: bytes) -> None:
        self._service.complete_first_run(
            raw, self._pending_params, self._pending_currency
        )
        self._submit.setEnabled(True)
        self.completed.emit()

    @Slot(object)
    def _on_failure(self, exc: object) -> None:
        self._submit.setEnabled(True)
        self._error.setText(
            self.tr("Could not create the vault: {error}").format(error=exc)
        )
