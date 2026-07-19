"""BackupVerifyDialog — pick a ``.fbk`` + backup password to check that a backup
actually opens (FIBR-0033 D5).

Opened **post-login** from the Settings "Verify backup…" button, next to Export.
The dialog only collects the inputs; the shell owns the synchronous, read-only
verify under a wait cursor (D7) and hands the ``VerifyResult`` back to
``show_result`` to render. Verify never touches the live vault (D3), so — unlike
restore — it needs no new master password and no auto-lock protection.
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

from finbreak.services.backup import VerifyResult


class BackupVerifyDialog(QDialog):
    verify_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Verify a backup"))

        # The chosen file, shown read-only; a Browse… button fills it (mirroring
        # BackupRestoreDialog) so source_path() is always a real picked file; a test
        # sets the field text directly.
        self._source_field = QLineEdit()
        self._source_field.setObjectName("backup_verify_source")
        self._source_field.setReadOnly(True)
        browse = QPushButton(self.tr("Browse…"))
        browse.setObjectName("backup_verify_browse")
        browse.clicked.connect(self._on_browse)
        source_row = QHBoxLayout()
        source_row.addWidget(self._source_field)
        source_row.addWidget(browse)

        self._backup_password = QLineEdit()
        self._backup_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._backup_password.setObjectName("backup_verify_password")
        # The ok/not-ok answer + friendly reason lands here (populated by show_result).
        self._result = QLabel()
        self._result.setWordWrap(True)
        self._result.setObjectName("backup_verify_result")

        form = QFormLayout()
        form.addRow(self.tr("Backup file"), source_row)
        form.addRow(self.tr("Backup password"), self._backup_password)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok: QPushButton = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(self.tr("Verify"))
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                self.tr(
                    "Check that a backup file opens with its backup password — a "
                    "read-only test that never changes your current vault."
                )
            )
        )
        layout.addLayout(form)
        layout.addWidget(self._result)
        layout.addWidget(buttons)

        self._source_field.textChanged.connect(self._sync_ok)
        self._backup_password.textChanged.connect(self._sync_ok)
        self._sync_ok()

    def source_path(self) -> Path | None:
        text = self._source_field.text()
        return Path(text) if text else None

    def backup_password(self) -> str:
        return self._backup_password.text()

    def show_result(self, result: VerifyResult) -> None:
        """Render a ``VerifyResult`` in the result area (called by the shell after
        the synchronous verify). Success lists the as-migrated schema + a friendly
        transaction count and the raw per-table counts; failure maps the stable
        ``reason`` code to a translated message — never raw exception text (D4)."""
        if result.ok:
            self._result.setText(self._success_text(result))
        else:
            self._result.setText(self._failure_text(result.reason))

    def _success_text(self, result: VerifyResult) -> str:
        # Per-value tr() literals with str.format — never self.tr(variable), which
        # lupdate cannot extract. The raw table:count list is release-data-like
        # (table names read from the DB), so it is shown verbatim, not tr()-wrapped.
        counts = result.table_counts or {}
        lines = [
            self.tr("Backup is readable — schema v{version}.").format(
                version=result.schema_version
            )
        ]
        if "transactions" in counts:
            lines.append(self.tr("{n} transactions.").format(n=counts["transactions"]))
        if counts:
            raw = ", ".join(f"{name}: {n}" for name, n in sorted(counts.items()))
            lines.append(raw)
        return "\n".join(lines)

    def _failure_text(self, reason: str | None) -> str:
        # Each stable reason code (FIBR-0033 mechanism table) maps to one translated
        # message; a couple share plain-English framing where SQLCipher cannot tell
        # the causes apart (INV-3).
        messages = {
            "wrong_password": self.tr(
                "Couldn't open this backup. The backup password may be wrong, or "
                "the file's header is damaged."
            ),
            "corrupt": self.tr(
                "The backup opened but is corrupted — some of its data failed the "
                "integrity check. Use a different backup."
            ),
            "bad_kdf_params": self.tr(
                "This backup's security settings are missing, unreadable, or below "
                "the minimum this app accepts."
            ),
            "too_new": self.tr(
                "This backup was made by a newer version of finbreak. Update the "
                "app, then try again."
            ),
            "invalid": self.tr(
                "That file isn't a valid finbreak backup (it may be the wrong file "
                "or damaged)."
            ),
            "io_error": self.tr(
                "Couldn't write a temporary file to check the backup. Free up some "
                "disk space and try again."
            ),
        }
        return messages.get(reason or "", self.tr("The backup could not be verified."))

    def _is_valid(self) -> bool:
        return bool(self._source_field.text() and self._backup_password.text())

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

    @Slot()
    def _sync_ok(self) -> None:
        self._ok.setEnabled(self._is_valid())

    @Slot()
    def _on_ok(self) -> None:
        # Emit intent and stay open — the shell runs the verify and calls
        # show_result, so the answer lands in this same dialog (never accept()).
        if self._is_valid():
            self.verify_requested.emit()
