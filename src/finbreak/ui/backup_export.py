"""BackupExportDialog — collect a backup password to export an encrypted ``.fbk``
(FIBR-0014 D3).

Opened from Settings (the only place "Export backup" lives, INV-8). The dialog
only collects + confirms the backup password (≥ ``MIN_BACKUP_PASSWORD_LEN``, with a
strong-password note for the off-device threat model); the shell owns the
save-file picker and the actual **synchronous** export under a wait cursor (INV-9),
mirroring the FIBR-0013 PDF-export flow.
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

from finbreak.services.backup import MIN_BACKUP_PASSWORD_LEN


class BackupExportDialog(QDialog):
    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export encrypted backup"))

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setObjectName("backup_export_password")
        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm.setObjectName("backup_export_confirm")
        self._error = QLabel()

        note = QLabel(
            self.tr(
                "Choose a strong password and keep it safe. Anyone who has both "
                "the backup file and this password can read your data, so store "
                "the file somewhere secure. This password can be different from "
                "your master password."
            )
        )
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self.tr("Backup password"), self._password)
        form.addRow(self.tr("Confirm password"), self._confirm)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok: QPushButton = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(self.tr("Export…"))
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                self.tr(
                    "Save an encrypted copy of your vault that you can restore "
                    "later with this backup password."
                )
            )
        )
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

        self._password.textChanged.connect(self._sync_ok)
        self._confirm.textChanged.connect(self._sync_ok)
        self._sync_ok()

    def password(self) -> str:
        """The confirmed backup password — read by the shell to run the export."""
        return self._password.text()

    def _is_valid(self) -> bool:
        pw = self._password.text()
        return len(pw) >= MIN_BACKUP_PASSWORD_LEN and pw == self._confirm.text()

    @Slot()
    def _sync_ok(self) -> None:
        # Gate OK on a matching password at/above the floor, and hint why it is
        # disabled — never self.tr(variable) (lupdate can't extract it).
        pw, confirm = self._password.text(), self._confirm.text()
        if pw and len(pw) < MIN_BACKUP_PASSWORD_LEN:
            self._error.setText(
                self.tr("Use at least {n} characters.").format(
                    n=MIN_BACKUP_PASSWORD_LEN
                )
            )
        elif confirm and pw != confirm:
            self._error.setText(self.tr("The passwords do not match."))
        else:
            self._error.clear()
        self._ok.setEnabled(self._is_valid())

    @Slot()
    def _on_ok(self) -> None:
        if self._is_valid():
            self.export_requested.emit()
