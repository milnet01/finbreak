"""Accounts manager screen — add / edit-type / delete accounts (FIBR-0005 INV-7).

All strings go through ``tr()`` and every widget sits in a Qt layout manager, so
the screen is translation-ready and RTL-safe (coding.md § 5.2). The type picker
carries the stored ``AccountType`` token as item data behind a translated label,
so the DB stays language-neutral (D5).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import FinbreakError, VaultLockedError
from finbreak.models import AccountType
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.ui._widgets import select_combo_data

_ACCOUNT_ID_ROLE = Qt.ItemDataRole.UserRole
# The selected account's current name + token, stashed on the row so selecting
# it can populate the form for an in-place edit (the token is language-neutral).
_ACCOUNT_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
_ACCOUNT_TYPE_ROLE = Qt.ItemDataRole.UserRole + 2
# Whether the row's account has a remembered statement PDF password (a bool — the
# secret itself is never stashed on the row). Drives the Forget button (FIBR-0128).
_ACCOUNT_HAS_PW_ROLE = Qt.ItemDataRole.UserRole + 3


class AccountsWidget(QWidget):
    done = Signal()

    def __init__(
        self,
        service: AuthService,
        parent: QWidget | None = None,
        *,
        show_done: bool = True,
    ):
        super().__init__(parent)
        self._accounts = AccountService(service.vault)

        self.setWindowTitle(self.tr("Accounts"))

        # Token -> translated label, in a fixed order; the label is display-only,
        # the token (itemData) is what is stored (D5).
        self._type_labels = {
            AccountType.CURRENT.value: self.tr("Current"),
            AccountType.SAVINGS.value: self.tr("Savings"),
            AccountType.CREDIT_CARD.value: self.tr("Credit card"),
            AccountType.PERSONAL_LOAN.value: self.tr("Personal loan"),
            AccountType.HOME_LOAN.value: self.tr("Home loan"),
            AccountType.INVESTMENT.value: self.tr("Investment"),
            AccountType.OTHER.value: self.tr("Other"),
        }

        self._list = QListWidget()
        self._name = QLineEdit()
        self._name.setPlaceholderText(self.tr("Account name"))
        # A placeholder vanishes once the user types and is not a reliable
        # accessible-name source; set an explicit accessible name so a screen
        # reader announces both fields (WCAG 1.3.1/3.3.2). (indie-review M-dlg3)
        self._name.setAccessibleName(self.tr("Account name"))
        self._type = QComboBox()
        self._type.setAccessibleName(self.tr("Account type"))
        for token, label in self._type_labels.items():
            self._type.addItem(label, token)
        self._add_button = QPushButton(self.tr("Add"))
        self._update_button = QPushButton(self.tr("Update selected"))
        self._delete_button = QPushButton(self.tr("Delete selected"))
        # Clears the selected account's remembered statement PDF password (FIBR-0128).
        # Disabled until a selected account actually has one saved; never reveals it.
        self._forget_pw_button = QPushButton(self.tr("Forget statement password"))
        self._forget_pw_button.setEnabled(False)
        # The "back to Home" Done button is meaningless when this widget is a
        # permanent tab, so it is not built when show_done=False (FIBR-0052
        # INV-12); the `done` signal stays (unfired) so no caller/test breaks.
        self._done_button = QPushButton(self.tr("Done")) if show_done else None
        self._error = QLabel()

        add_row = QHBoxLayout()
        add_row.addWidget(self._name)
        add_row.addWidget(self._type)
        add_row.addWidget(self._add_button)
        add_row.addWidget(self._update_button)

        actions = QHBoxLayout()
        actions.addWidget(self._delete_button)
        actions.addWidget(self._forget_pw_button)
        actions.addStretch()
        if self._done_button is not None:
            actions.addWidget(self._done_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(add_row)
        layout.addWidget(self._error)
        layout.addLayout(actions)

        self._add_button.clicked.connect(self._on_add)
        self._update_button.clicked.connect(self._on_update)
        self._delete_button.clicked.connect(self._on_delete)
        self._forget_pw_button.clicked.connect(self._on_forget_password)
        if self._done_button is not None:
            self._done_button.clicked.connect(self.done)
        # Selecting an account loads its name + type into the form, so the same
        # two fields serve both Add (nothing selected) and Update (D8 — the
        # seeded Default account is renamed / retyped here).
        self._list.currentItemChanged.connect(self._on_selection_changed)

        self._refresh()

    @Slot()
    def _on_add(self) -> None:
        self._error.clear()
        try:
            self._accounts.add_account(self._name.text(), self._type.currentData())
        except VaultLockedError:
            return  # auto-lock fired mid-edit — silent, like the delete handlers
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._name.clear()
        self._refresh()

    @Slot()
    def _on_update(self) -> None:
        self._error.clear()
        item = self._list.currentItem()
        if item is None:
            return
        try:
            self._accounts.update_account(
                item.data(_ACCOUNT_ID_ROLE),
                self._name.text(),
                self._type.currentData(),
            )
        except VaultLockedError:
            return  # auto-lock fired mid-edit — silent, like the delete handlers
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._refresh()

    @Slot()
    def _on_selection_changed(self) -> None:
        item = self._list.currentItem()
        # Recompute the Forget button's state BEFORE the None early-return, so a
        # cleared selection (e.g. the _refresh after a Forget clears the list)
        # actually disables it rather than leaving it stale-enabled (FIBR-0128 D3).
        self._forget_pw_button.setEnabled(
            item is not None and bool(item.data(_ACCOUNT_HAS_PW_ROLE))
        )
        if item is None:
            return
        self._name.setText(item.data(_ACCOUNT_NAME_ROLE))
        select_combo_data(self._type, item.data(_ACCOUNT_TYPE_ROLE))

    @Slot()
    def _on_forget_password(self) -> None:
        self._error.clear()
        item = self._list.currentItem()
        if item is None:  # defensive, like _on_delete — the button gating precludes it
            return
        # Confirm before wiping, mirroring the delete action (FIBR-0128 D3). Forgetting
        # is recoverable (re-learned on the next locked import), but it's still the
        # user's saved credential, so it gets the same guard.
        if (
            QMessageBox.question(
                self,
                self.tr("Forget statement password"),
                self.tr("Forget the saved statement password for “{name}”?").format(
                    name=item.data(_ACCOUNT_NAME_ROLE)
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._accounts.set_pdf_password(item.data(_ACCOUNT_ID_ROLE), None)
        except VaultLockedError:
            # An idle auto-lock can fire while the confirm box is open — silent,
            # like every other handler here (FIBR-0128 INV-5).
            return
        self._refresh()

    @Slot()
    def _on_delete(self) -> None:
        self._error.clear()
        item = self._list.currentItem()
        if item is None:
            return
        # Confirm before deleting — parity with the Categories/Statements delete
        # actions, which all confirm (indie-review H-E). An in-use account is
        # refused by the service anyway (AccountInUseError), so the worst case is
        # losing an empty account; a plain confirm matches what users now expect.
        if (
            QMessageBox.question(
                self,
                self.tr("Delete account"),
                self.tr("Delete the account “{name}”?").format(
                    name=item.data(_ACCOUNT_NAME_ROLE)
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._accounts.delete_account(item.data(_ACCOUNT_ID_ROLE))
        except VaultLockedError:
            # An idle auto-lock can fire while the confirm box is open (INV-14).
            return
        except FinbreakError as exc:
            # AccountInUseError / LastAccountError — show the message, remove
            # nothing (INV-6 reflected through the UI).
            self._error.setText(str(exc))
            return
        self._refresh()

    def _select_account(self, account_id: int) -> None:
        """Select the list row for ``account_id`` (used by the UI tests)."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(_ACCOUNT_ID_ROLE) == account_id:
                self._list.setCurrentItem(item)
                return

    def _refresh(self) -> None:
        self._list.clear()
        # Presence only — the id-set query never pulls the stored password into the
        # UI (FIBR-0128 INV-1). A marked row shows a screen-reader-legible suffix.
        with_pw = self._accounts.account_ids_with_pdf_password()
        for account in self._accounts.list_accounts():
            label = self._type_labels.get(account.type, account.type)
            text = f"{account.name} — {label}"
            has_pw = account.id in with_pw
            if has_pw:
                text += self.tr("  ·  🔑 statement password saved")
            item = QListWidgetItem(text)
            item.setData(_ACCOUNT_ID_ROLE, account.id)
            item.setData(_ACCOUNT_NAME_ROLE, account.name)
            item.setData(_ACCOUNT_TYPE_ROLE, account.type)
            item.setData(_ACCOUNT_HAS_PW_ROLE, has_pw)
            self._list.addItem(item)
