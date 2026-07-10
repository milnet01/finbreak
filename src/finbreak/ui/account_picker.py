"""AccountPickerDialog — pick a target account (FIBR-0059).

A small ``QDialog`` (one dialog per file, like ``ui/{settings,password_dialog}``):
a labelled account ``QComboBox`` preselected to the statement's current account +
OK/Cancel. The Statements tab's *Change account* action opens it and reads
``selected_account_id()``. The dialog is "dumb" — it takes the already-fetched
account list, not a service. All strings go through ``tr()`` and every widget
sits in a layout manager (coding.md § 5.2).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

from finbreak.models import Account
from finbreak.ui._widgets import select_combo_data


class AccountPickerDialog(QDialog):
    def __init__(
        self,
        accounts: list[Account],
        current_account_id: int,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Change account"))

        self._combo = QComboBox()
        for account in accounts:
            self._combo.addItem(account.name, account.id)
        # preselect the current account (a safe default)
        select_combo_data(self._combo, current_account_id)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(self.tr("Move this statement to"), self._combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def selected_account_id(self) -> int:
        return self._combo.currentData()
