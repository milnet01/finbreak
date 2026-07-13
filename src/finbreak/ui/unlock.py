"""Unlock dialog — password → (worker derives) → open vault (FIBR-0004 INV-6).

A wrong password and a tampered vault are deliberately indistinguishable here:
both surface as a failed unlock, because without the correct key the app cannot
tell them apart (the HMAC that would prove tamper is itself keyed).

Re-homed from a full-screen ``QWidget`` into a non-blocking application-modal
``QDialog`` shown over the window (FIBR-0051 D2). It keeps ``unlocked`` /
``unlock_failed``; the shell connects ``unlocked`` → the unlocked shell, and on
``unlock_failed`` the dialog stays open for a retry. Cancel / window-close fires
``reject()`` (the shell leaves the locked shell on screen). While a derivation is
in flight **all three dismissal routes no-op** (Cancel disabled, ``reject()`` /
``closeEvent`` return early) so the parented ``DeriveWorker`` ``QThread`` is never
deleted mid-run (INV-2f).
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import KdfPolicyError, SchemaVersionError
from finbreak.services.auth import AuthService
from finbreak.ui._worker import DeriveWorker


class UnlockDialog(QDialog):
    unlocked = Signal()
    unlock_failed = Signal()
    # "Forgot password? Restore from a backup" — the shell owns the pre-login
    # restore flow (FIBR-0014 INV-8/D5).
    restore_requested = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._worker: DeriveWorker | None = None
        self.setWindowTitle(self.tr("Unlock finbreak"))

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText(self.tr("Master password"))
        self._unlock_button = QPushButton(self.tr("Unlock"))
        self._error = QLabel()
        self._restore_button = QPushButton(
            self.tr("Forgot password? Restore from a backup…")
        )
        self._restore_button.setObjectName("unlock_restore")
        self._restore_button.setFlat(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Enter your master password to unlock.")))
        layout.addWidget(self._password)
        layout.addWidget(self._unlock_button)
        layout.addWidget(self._error)
        layout.addWidget(self._restore_button)
        layout.addWidget(buttons)

        self._unlock_button.clicked.connect(self._on_unlock)
        self._password.returnPressed.connect(self._on_unlock)
        self._restore_button.clicked.connect(self.restore_requested)

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
    def _on_unlock(self) -> None:
        if self._worker is not None:
            return  # a derivation is already in flight — ignore repeat submits
        self._error.clear()
        try:
            params = self._service.load_params()
        except KdfPolicyError:
            # NOT a wrong password — no password has been checked yet. The KDF
            # sidecar is missing / malformed / below the pinned strength floor.
            # Give it its own message (like SchemaVersionError) so a user with
            # the *correct* password isn't told to re-check it forever. Only the
            # HMAC-tamper case is meant to be indistinguishable from a wrong
            # password (security-model), not this. (indie-review M-auth1)
            self._error.setText(
                self.tr(
                    "finbreak can't read this vault's security-settings file "
                    "(it's missing or damaged), so it can't be unlocked. If you "
                    "have a backup of your vault folder, restore it."
                )
            )
            self.unlock_failed.emit()
            return

        password = bytearray(self._password.text().encode("utf-8"))
        self._password.clear()
        self._set_busy(True)

        worker = DeriveWorker(password, params, self)  # parented — Qt owns it
        worker.done.connect(self._on_derived)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(worker.deleteLater)  # no leaked QThread per attempt
        self._worker = worker
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        # Disable the field + Cancel too (not just the submit button): a second
        # Enter can't re-enter _on_unlock and orphan the running worker, and a
        # dismissal can't delete the parented worker mid-run (INV-2f).
        self._unlock_button.setEnabled(not busy)
        self._password.setEnabled(not busy)
        self._cancel.setEnabled(not busy)
        # Restore is a dismissal-like route (it tears down this dialog); disable it
        # mid-derivation too so the parented worker is never deleted under it.
        self._restore_button.setEnabled(not busy)

    @Slot(bytes)
    def _on_derived(self, raw: bytes) -> None:
        self._worker = None
        self._set_busy(False)
        try:
            unlocked = self._service.complete_unlock(raw)
        except SchemaVersionError:
            # A vault written by a newer build — distinct from a wrong password,
            # so it gets its own message rather than the generic failure.
            self._error.setText(
                self.tr(
                    "This vault was created by a newer version of finbreak. "
                    "Please update finbreak to open it."
                )
            )
            self.unlock_failed.emit()
            return
        if unlocked:
            self.unlocked.emit()
        else:
            self._show_failure()

    @Slot(object)
    def _on_failure(self, _exc: object) -> None:
        self._worker = None
        self._set_busy(False)
        self._show_failure()

    def _show_failure(self) -> None:
        self._error.setText(
            self.tr("Could not unlock. Check your password and try again.")
        )
        self.unlock_failed.emit()
