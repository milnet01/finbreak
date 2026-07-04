"""PasswordDialog — the locked-PDF password prompt (FIBR-0009 D11).

A small purpose-built ``QDialog`` (a bare ``QInputDialog.getText`` cannot carry
the "remember" checkbox): a masked field + a "Remember this password for
<account>" checkbox (unchecked by default) + OK/Cancel. Re-shown by the wizard on
a wrong password (INV-3); Cancel abandons the import cleanly.

It lives in its **own** module (not ``import_wizard``) so the password only ever
sits on this dialog's field, never on an ``ImportWizardWidget`` attribute
(INV-11). All strings go through ``tr()`` (coding.md § 5.2).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class PasswordDialog(QDialog):
    def __init__(self, account_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("PDF password"))

        self._field = QLineEdit()
        self._field.setEchoMode(QLineEdit.EchoMode.Password)
        self._remember = QCheckBox(
            self.tr("Remember this password for {account}").format(account=account_name)
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(self.tr("Password"), self._field)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._remember)
        layout.addWidget(buttons)

    def password(self) -> str:
        """The entered password (read only after an ``Accepted`` ``exec()``)."""
        return self._field.text()

    def remember(self) -> bool:
        """Whether "remember for this account" is checked (default ``False``)."""
        return self._remember.isChecked()
