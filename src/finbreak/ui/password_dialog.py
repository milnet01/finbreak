"""PasswordDialog — the locked-PDF password prompt (FIBR-0009 D11).

A small purpose-built ``QDialog`` (a bare ``QInputDialog.getText`` cannot carry
the "remember" checkbox): a masked field + a "Remember this password for
<account>" checkbox (unchecked by default) + OK/Cancel. Re-shown by the wizard on
a wrong password (INV-3); Cancel abandons the import cleanly.

It lives in its **own** module (not ``import_wizard``) so the *entered* password
sits only on this dialog's field while the prompt is open, not smeared across the
wizard. NOTE: the remember-for-this-account flow added later (FIBR-0057) does
briefly hold a **confirmed** password on ``ImportWizardWidget._stored_pw`` after a
successful decrypt — a deliberate, bounded widening of FIBR-0009 INV-11's original
"never on a wizard attribute", so a re-target can carry the password to the
committed account; it is cleared on the next file pick. All strings go through
``tr()`` (coding.md § 5.2).
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
    def __init__(
        self,
        account_name: str,
        parent: QWidget | None = None,
        remember_text: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("PDF password"))

        self._field = QLineEdit()
        self._field.setEchoMode(QLineEdit.EchoMode.Password)
        # `remember_text` overrides the label for a caller whose password is not
        # keyed to the name in the title. The batch import (FIBR-0085 § 4.4)
        # titles the prompt with the FILE — a thirty-file run has to say which
        # one it is asking about — but stores the password against whichever
        # account that file lands on, which may not be settled yet.
        self._remember = QCheckBox(
            remember_text
            or self.tr("Remember this password for {account}").format(
                account=account_name
            )
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
        """The entered password (read from the ``accepted`` slot — the dialog is shown
        non-blocking via ``show_modal``, never ``exec()``-ed; FIBR-0065 INV-1)."""
        return self._field.text()

    def remember(self) -> bool:
        """Whether "remember for this account" is checked (default ``False``)."""
        return self._remember.isChecked()
