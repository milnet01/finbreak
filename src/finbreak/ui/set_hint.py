"""SetHintDialog — set/edit the optional password hint behind a confirm
(FIBR-0029 § 3.2).

Opened from Settings (the only place "Set password hint…" lives). Modelled on
``ui/backup_export.py``'s validation-gated dialog: it only collects the hint text
and the **current** master password; the shell (``main_window.py``) owns the work —
``verify_password`` → ``validate_hint`` → ``write_hint`` / ``clear_hint`` — so this
dialog holds no ``AuthService`` reference. Save is gated on a non-empty password
field (you must confirm to change anything); the hint may be blank (that clears it).
A visible plaintext-storage warning makes the trade-off explicit.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.services.password_hint import MAX_HINT_LEN


class SetHintDialog(QDialog):
    save_requested = Signal()

    def __init__(self, current_hint: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Set password hint"))

        # Plain text field, pre-filled with the current hint so "set" and "edit"
        # are one flow. setMaxLength counts UTF-16 code units while validate_hint /
        # MAX_HINT_LEN count code points — they diverge only for astral chars; the
        # service check is the authoritative gate, this cap is a convenience.
        self._hint = QLineEdit()
        self._hint.setObjectName("set_hint_text")
        self._hint.setMaxLength(MAX_HINT_LEN)
        self._hint.setText(current_hint)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setObjectName("set_hint_password")

        self._error = QLabel()

        warning = QLabel(
            self.tr(
                "This hint is saved unencrypted and can be read by anyone with "
                "access to this device. Never put your password in it."
            )
        )
        warning.setObjectName("set_hint_warning")
        warning.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self.tr("Hint"), self._hint)
        form.addRow(self.tr("Current password"), self._password)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok: QPushButton = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(self.tr("Save"))
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                self.tr(
                    "Add an optional reminder shown on the unlock screen if you "
                    "forget your password. Leave it blank to remove the hint."
                )
            )
        )
        layout.addLayout(form)
        layout.addWidget(warning)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

        self._password.textChanged.connect(self._sync_ok)
        self._sync_ok()

    def hint(self) -> str:
        """The entered hint text — read by the shell to validate + persist."""
        return self._hint.text()

    def password(self) -> str:
        """The entered current password — read by the shell to verify the change."""
        return self._password.text()

    def show_error(self, message: str) -> None:
        """Surface an inline rejection (wrong password / policy violation)."""
        self._error.setText(message)

    def _is_valid(self) -> bool:
        # A confirm is mandatory; the hint itself may be blank (blank ⇒ clear).
        return bool(self._password.text())

    @Slot()
    def _sync_ok(self) -> None:
        self._ok.setEnabled(self._is_valid())

    @Slot()
    def _on_ok(self) -> None:
        if self._is_valid():
            self.save_requested.emit()
