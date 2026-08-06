"""CreateAccountDialog — make an account from what a statement printed (FIBR-0086).

A small ``QDialog`` (one dialog per file, like ``ui/account_picker``): name, type
and account number, prefilled from the statement's own header and every field
still editable. The import wizard opens it from the ``no_match`` outcome, where the
statement carries a number no configured account has.

The dialog is "dumb" — it takes prefill strings and hands back the entered values;
the caller owns the ``AccountService`` write. All strings go through ``tr()`` and
every widget sits in a layout manager (coding.md § 5.2).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from finbreak.models import AccountType
from finbreak.ui._widgets import select_combo_data

# The statement layout family, where it determines the account type. ``A`` is
# absent deliberately: it spans current, savings AND revolving credit, so it
# yields no type and the user picks (FIBR-0086 §4.6).
_FAMILY_TYPES = {
    "B": AccountType.HOME_LOAN.value,
    "D": AccountType.INVESTMENT.value,
}


class CreateAccountDialog(QDialog):
    def __init__(
        self,
        *,
        number: str,
        name: str | None = None,
        family: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Create account from statement"))

        # As PRINTED, not the normalised match key — storage keeps what the
        # statement said, and every comparison normalises both sides at match
        # time, so a stored "11 222 333 4" still matches a later statement
        # printing "112223334" (FIBR-0086 §4.6).
        self._number = QLineEdit(number)
        self._number.setAccessibleName(self.tr("Account number"))

        # Only family A prints a product name before the label; B and D print
        # nothing there, so the box is left empty rather than prefilled with a
        # stray fragment.
        self._name = QLineEdit(name or "")
        self._name.setAccessibleName(self.tr("Account name"))

        self._type = QComboBox()
        self._type.setAccessibleName(self.tr("Account type"))
        for token, label in {
            AccountType.CURRENT.value: self.tr("Current"),
            AccountType.SAVINGS.value: self.tr("Savings"),
            AccountType.CREDIT_CARD.value: self.tr("Credit card"),
            AccountType.PERSONAL_LOAN.value: self.tr("Personal loan"),
            AccountType.HOME_LOAN.value: self.tr("Home loan"),
            AccountType.INVESTMENT.value: self.tr("Investment"),
            AccountType.OTHER.value: self.tr("Other"),
        }.items():
            self._type.addItem(label, token)
        inferred = _FAMILY_TYPES.get(family or "")
        if inferred is not None:
            select_combo_data(self._type, inferred)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(self.tr("Name"), self._name)
        form.addRow(self.tr("Type"), self._type)
        form.addRow(self.tr("Account number"), self._number)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def entered_name(self) -> str:
        return self._name.text()

    def entered_type(self) -> str:
        return self._type.currentData()

    def entered_number(self) -> str:
        return self._number.text()
