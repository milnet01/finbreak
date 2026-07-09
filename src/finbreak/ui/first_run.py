"""First-run dialog — set the master password + base currency (FIBR-0004 INV-5).

The password is entered twice; a mismatch, an empty password, or an unsupported
currency is a form-boundary error that creates no vault and derives no key. On
success the vault is created, the app is left unlocked, and ``completed`` fires.

Re-homed from a full-screen ``QWidget`` into a non-blocking application-modal
``QDialog`` shown over the window (FIBR-0051 D2). Cancel / window-close fires
``reject()`` (the shell then quits — no vault can exist). While a derivation is in
flight (``self._worker is not None``) **all three dismissal routes no-op** — Cancel
is disabled and ``reject()`` / ``closeEvent`` return early — so the parented
``DeriveWorker`` ``QThread`` is never deleted mid-run (INV-2f).
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
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


class FirstRunDialog(QDialog):
    completed = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._worker: DeriveWorker | None = None
        self._pending_params: KdfParams | None = None
        self._pending_currency = ""
        self.setWindowTitle(self.tr("Create your vault"))

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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)

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
        layout.addWidget(buttons)

        self._submit.clicked.connect(self._on_submit)

    def _set_busy(self, busy: bool) -> None:
        # Disabling Cancel (with the reject()/closeEvent guards below) is what
        # keeps a dismissal from deleting the parented worker mid-run (INV-2f).
        self._submit.setEnabled(not busy)
        self._cancel.setEnabled(not busy)

    def reject(self) -> None:
        if self._worker is not None:
            return  # a derivation is in flight — Escape / Cancel no-op (INV-2f)
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None:
            event.ignore()  # the window [X] mid-derivation is a no-op too (INV-2f)
            return
        super().closeEvent(event)

    @Slot()
    def _on_submit(self) -> None:
        if self._worker is not None:
            return  # a derivation is already in flight — ignore repeat submits
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
        self._set_busy(True)

        worker = DeriveWorker(derive_password, self._pending_params, self)  # Qt owns it
        worker.done.connect(self._on_derived)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(worker.deleteLater)  # no leaked QThread per attempt
        self._worker = worker
        worker.start()

    @Slot(bytes)
    def _on_derived(self, raw: bytes) -> None:
        self._worker = None
        self._set_busy(False)  # every worker-clearing path re-enables Cancel (D2)
        params = self._pending_params
        currency = self._pending_currency
        self._pending_params = None  # consumed — don't leave stale state on a retry
        self._pending_currency = ""
        if params is None:  # _on_submit always sets it before start — defensive
            return
        try:
            self._service.complete_first_run(raw, params, currency)
        except Exception as exc:  # vault creation failed — surface, don't crash
            self._error.setText(
                self.tr("Could not create the vault: {error}").format(error=exc)
            )
            return
        self.completed.emit()

    @Slot(object)
    def _on_failure(self, exc: object) -> None:
        self._worker = None
        self._set_busy(False)
        self._error.setText(
            self.tr("Could not create the vault: {error}").format(error=exc)
        )
