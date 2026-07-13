"""BackupRestoreDialog — pick a ``.fbk`` + backup password + a new master password
to restore an encrypted backup (FIBR-0014 D4).

Reachable **pre-login** from both the first-run welcome and the Unlock dialog
(INV-8) as a "Forgot password? Restore from a backup" affordance. The dialog only
collects the inputs; the shell owns the actual restore under a wait cursor and,
on success, re-enters the unlocked shell under the new master password (D5). A
restore **replaces** the current vault (the old one is moved aside, not
destroyed), so the copy warns about that.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BackupRestoreDialog(QDialog):
    restore_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Restore from backup"))

        # The chosen file, shown read-only; a Browse… button fills it via a native
        # open dialog. Read-only (not free-typed) so source_path() is always a real
        # picked file; a test sets the field text directly.
        self._source_field = QLineEdit()
        self._source_field.setObjectName("backup_restore_source")
        self._source_field.setReadOnly(True)
        browse = QPushButton(self.tr("Browse…"))
        browse.setObjectName("backup_restore_browse")
        browse.clicked.connect(self._on_browse)
        source_row = QHBoxLayout()
        source_row.addWidget(self._source_field)
        source_row.addWidget(browse)

        self._backup_password = QLineEdit()
        self._backup_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._backup_password.setObjectName("backup_restore_backup_password")
        self._new_master = QLineEdit()
        self._new_master.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_master.setObjectName("backup_restore_new_master")
        self._confirm_master = QLineEdit()
        self._confirm_master.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_master.setObjectName("backup_restore_confirm_master")
        self._error = QLabel()

        form = QFormLayout()
        form.addRow(self.tr("Backup file"), source_row)
        form.addRow(self.tr("Backup password"), self._backup_password)
        form.addRow(self.tr("New master password"), self._new_master)
        form.addRow(self.tr("Confirm new master password"), self._confirm_master)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok: QPushButton = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(self.tr("Restore"))
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                self.tr(
                    "Restore an encrypted backup. This replaces the current vault "
                    "(the old one is moved aside, not deleted) and sets a new "
                    "master password — you will not need the old one."
                )
            )
        )
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

        self._source_field.textChanged.connect(self._sync_ok)
        self._backup_password.textChanged.connect(self._sync_ok)
        self._new_master.textChanged.connect(self._sync_ok)
        self._confirm_master.textChanged.connect(self._sync_ok)
        self._sync_ok()

    def source_path(self) -> Path | None:
        text = self._source_field.text()
        return Path(text) if text else None

    def backup_password(self) -> str:
        return self._backup_password.text()

    def new_master_password(self) -> str:
        return self._new_master.text()

    @Slot()
    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Choose a backup file"),
            "",
            self.tr("finbreak backups (*.fbk)"),
        )
        if path:
            self._source_field.setText(path)

    def _is_valid(self) -> bool:
        return bool(
            self._source_field.text()
            and self._backup_password.text()
            and self._new_master.text()
            and self._new_master.text() == self._confirm_master.text()
        )

    @Slot()
    def _sync_ok(self) -> None:
        if (
            self._confirm_master.text()
            and self._new_master.text() != self._confirm_master.text()
        ):
            self._error.setText(self.tr("The new master passwords do not match."))
        else:
            self._error.clear()
        self._ok.setEnabled(self._is_valid())

    @Slot()
    def _on_ok(self) -> None:
        if self._is_valid():
            self.restore_requested.emit()
