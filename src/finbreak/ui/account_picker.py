"""AccountPickerDialog — pick a target account (FIBR-0059).

A small ``QDialog`` (one dialog per file, like ``ui/{settings,password_dialog}``):
a labelled account ``QComboBox`` preselected to the statement's current account +
OK/Cancel — or, where the caller has no current account to preselect, a
"— pick one —" placeholder with OK held disabled until something is chosen. The
Statements tab's *Change account* action opens it and reads
``selected_account_id()``, which is ``None`` while nothing has been picked.
The dialog is "dumb" — it takes the already-fetched account list, not a
service. All strings go through ``tr()`` and every widget
sits in a layout manager (coding.md § 5.2).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

from finbreak.importers.base import SourceAccountHint
from finbreak.models import Account
from finbreak.ui._widgets import select_combo_data


class AccountPickerDialog(QDialog):
    # FIBR-0085 § 3 decision 6: the batch never creates an account without being
    # asked, but it does OFFER — a file whose printed number matches nothing
    # reaches the review screen needing a destination that may not exist yet.
    # The dialog stays "dumb" (it takes no service): it reports the ask, and the
    # caller — which holds the services — runs the creation.
    create_requested = Signal()

    def __init__(
        self,
        accounts: list[Account],
        current_account_id: int,
        parent: QWidget | None = None,
        hint: SourceAccountHint | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Change account"))

        self._combo = QComboBox()
        for account in accounts:
            self._combo.addItem(account.name, account.id)
        if self._combo.findData(current_account_id) < 0:
            # No destination yet. The batch review's Account cell says
            # "— pick one —" for such a row and the picker has to agree:
            # `select_combo_data` leaves the selection ALONE when `findData`
            # misses, so this dialog used to open on whichever account came
            # first with OK already live, and a user who believed the row's own
            # wording filed the statement against an account they never picked
            # (FIBR-0327). The placeholder carries no id, so
            # `selected_account_id` reports None and the callers' "nothing
            # chosen" branch — which until now could not run — does.
            self._combo.insertItem(0, self.tr("— pick one —"), None)
            self._combo.setCurrentIndex(0)
        else:
            # preselect the current account (a safe default)
            select_combo_data(self._combo, current_account_id)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._combo.currentIndexChanged.connect(self._gate_ok)
        self._gate_ok()

        form = QFormLayout()
        form.addRow(self.tr("Move this statement to"), self._combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        # Shown only when the caller supplied the statement's own details —
        # there is nothing to prefill a new account from otherwise, and an
        # unprefilled Create here would be a worse Accounts tab.
        if hint is not None:
            self._create_button = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes)
            self._create_button.button(QDialogButtonBox.StandardButton.Yes).setText(
                self.tr("Create a new account…")
            )
            self._create_button.setObjectName("account_picker_create")
            self._create_button.accepted.connect(self.create_requested)
            self._create_button.accepted.connect(self.reject)
            layout.addWidget(self._create_button)
        layout.addWidget(buttons)

    def _gate_ok(self) -> None:
        """OK goes live only once a real account is chosen — the placeholder and
        an empty account list both carry no id."""
        self._ok.setEnabled(self._combo.currentData() is not None)

    def selected_account_id(self) -> int | None:
        """The chosen account, or ``None`` while nothing has been picked."""
        return self._combo.currentData()
