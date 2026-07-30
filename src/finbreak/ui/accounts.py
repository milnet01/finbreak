"""Accounts manager screen — a sortable 5-column table plus an add/edit form
(FIBR-0005 INV-7, FIBR-0113).

All strings go through ``tr()`` and every widget sits in a Qt layout manager, so
the screen is translation-ready and RTL-safe (coding.md § 5.2). The type picker
carries the stored ``AccountType`` token as item data behind a translated label,
so the DB stays language-neutral (D5).

Row identity goes through ``_table_state``: the visual row is **not** an index
into ``self._rows`` once the user sorts, so every handler resolves its target
via ``selected_index`` and the fill tags each row with its insertion index.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import FinbreakError, VaultLockedError
from finbreak.models import (
    Account,
    AccountReconciliation,
    AccountType,
    ReconciliationStatus,
)
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.reconciliation import ReconciliationService
from finbreak.services.transactions import (
    TransactionService,
    read_minor_unit_exponent,
    to_display_decimal,
)
from finbreak.ui._amount import _format_amount
from finbreak.ui._table_state import (
    SortableItem,
    enable_sorting,
    fill_guard,
    remember_columns,
    select_by_index,
    selected_index,
    tag_row,
)
from finbreak.ui._widgets import select_combo_data

_COL_NAME, _COL_TYPE, _COL_NUMBER, _COL_NOTE, _COL_STATUS = range(5)

# Status-column sort key: a severity RANK, so clicking the header groups the
# accounts that need attention rather than ordering marker strings by codepoint
# (which would put an empty cell first and a 🔑-only cell last — both wrong).
_RANK_OFF, _RANK_QUIET, _RANK_RECONCILED = 0, 1, 2

_MASK = "•" * 4


def _mask_account_number(value: str | None) -> str:
    """Display form: a mask plus the last 4 characters for a value longer than
    4; a bare mask for a value of 1-4 characters (its "last 4" would be all of
    it); an empty cell when there is no number at all.

    The exposure defended against is shoulder-surfing and screenshots, not
    storage — the value already sits inside the SQLCipher vault (FIBR-0113 D2).
    This is for the **table cell** only, because a ``QTableWidgetItem`` has no
    echo mode; the form field is masked by ``QLineEdit`` echo mode instead and
    always carries the RAW stored value, or an Update would write ``"•••• 7890"``
    back into the vault as the account number.
    """
    if not value:
        return ""
    return f"{_MASK} {value[-4:]}" if len(value) > 4 else _MASK


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
        # The per-account balance-reconciliation health check (FIBR-0177 D6). The
        # vault is kept so ``_refresh`` can read the money-display exponent (from the
        # connection) + the base-currency symbol to render an "off by" magnitude.
        self._vault = service.vault
        self._reconciliation = ReconciliationService(service.vault)

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

        # Parallel row state, initialised BEFORE the table is built and its
        # selection signal connected, so a signal emitted during construction or
        # the first fill cannot reach an unset attribute. ``_with_pw`` is a
        # separate member because the has-a-saved-password flag deliberately
        # does NOT live on ``Account`` (FIBR-0193 INV-4 keeps the credential out
        # of every listing) — dropping it silently disables the Forget gating.
        self._rows: list[Account] = []
        self._with_pw: set[int] = set()

        self._table = QTableWidget(0, 5)
        # A distinct objectName so remember_columns keys this table uniquely and
        # it cannot cross-corrupt another table's saved layout (FIBR-0012).
        self._table.setObjectName("accounts_table")
        self._table.setHorizontalHeaderLabels(
            [
                self.tr("Name"),
                self.tr("Type"),
                self.tr("Account number"),
                self.tr("Note"),
                self.tr("Status"),
            ]
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        enable_sorting(self._table)  # click a header to sort; second click toggles
        remember_columns(self._table)  # persist column widths/order across sessions

        self._name = QLineEdit()
        self._name.setPlaceholderText(self.tr("Account name"))
        # A placeholder vanishes once the user types and is not a reliable
        # accessible-name source; set an explicit accessible name so a screen
        # reader announces both fields (WCAG 1.3.1/3.3.2). (indie-review M-dlg3)
        self._name.setAccessibleName(self.tr("Account name"))
        self._account_number = QLineEdit()
        self._account_number.setPlaceholderText(self.tr("Account number (optional)"))
        self._account_number.setAccessibleName(self.tr("Account number"))
        # Masked on the form by echo mode, since selecting a row populates it —
        # a plain field would put the number on screen whenever anyone clicks an
        # account, defeating D2 on the same screen that masks the column. Still
        # fully editable, exactly like any password box.
        self._account_number.setEchoMode(QLineEdit.EchoMode.Password)
        self._note = QLineEdit()
        self._note.setPlaceholderText(self.tr("Note (optional)"))
        self._note.setAccessibleName(self.tr("Note"))
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

        # Two rows: Name + Type above, Account number + Note below with the two
        # buttons at the end. Inline on the tab, not a dialog — it preserves the
        # type-a-name-and-hit-Add flow (D3).
        add_row = QGridLayout()
        add_row.addWidget(self._name, 0, 0)
        add_row.addWidget(self._type, 0, 1)
        add_row.addWidget(self._account_number, 1, 0)
        add_row.addWidget(self._note, 1, 1)
        add_row.addWidget(self._add_button, 1, 2)
        add_row.addWidget(self._update_button, 1, 3)

        actions = QHBoxLayout()
        actions.addWidget(self._delete_button)
        actions.addWidget(self._forget_pw_button)
        actions.addStretch()
        if self._done_button is not None:
            actions.addWidget(self._done_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(add_row)
        layout.addWidget(self._error)
        layout.addLayout(actions)

        self._add_button.clicked.connect(self._on_add)
        self._update_button.clicked.connect(self._on_update)
        self._delete_button.clicked.connect(self._on_delete)
        self._forget_pw_button.clicked.connect(self._on_forget_password)
        if self._done_button is not None:
            self._done_button.clicked.connect(self.done)
        # Selecting an account loads all four inputs, so the same form serves
        # both Add (nothing selected) and Update (D8 — the seeded Default
        # account is renamed / retyped here).
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        self._refresh()

    def _selected_account(self) -> Account | None:
        """The selected row's ``Account``, resolved through the row tag rather
        than the visual row — the two diverge the moment the user sorts."""
        index = selected_index(self._table)
        return self._rows[index] if index is not None else None

    def _apply_forget_gating(self) -> None:
        """Enable Forget only for a selected account that has a saved statement
        password (FIBR-0128 D3). Gating ONLY — it never touches the form, so a
        ``_refresh()`` cannot overwrite in-progress input. Called from here and
        from ``_refresh``; FIBR-0198's reveal handler is the third site, and it
        is the one that makes a separate helper necessary rather than tidy,
        because it fires with a selection LIVE."""
        account = self._selected_account()
        self._forget_pw_button.setEnabled(
            account is not None and account.id in self._with_pw
        )

    @Slot()
    def _on_add(self) -> None:
        self._error.clear()
        try:
            self._accounts.add_account(
                self._name.text(),
                self._type.currentData(),
                account_number=self._account_number.text(),
                note=self._note.text(),
            )
        except VaultLockedError:
            return  # auto-lock fired mid-edit — silent, like the delete handlers
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        # Only the three line edits. NOT the Type picker: QComboBox.clear()
        # removes its ITEMS, which would destroy the seven type entries and the
        # token-behind-label contract __init__ builds.
        self._name.clear()
        self._account_number.clear()
        self._note.clear()
        self._refresh()

    @Slot()
    def _on_update(self) -> None:
        self._error.clear()
        account = self._selected_account()
        if account is None:
            return
        try:
            self._accounts.update_account(
                account.id,
                self._name.text(),
                self._type.currentData(),
                # Raw field text — the service normalises. Keyword-only, so a
                # positional call raises TypeError (FIBR-0193 § 4.2).
                account_number=self._account_number.text(),
                note=self._note.text(),
            )
        except VaultLockedError:
            return  # auto-lock fired mid-edit — silent, like the delete handlers
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._refresh()

    @Slot()
    def _on_selection_changed(self) -> None:
        # Gate the Forget button BEFORE the no-selection early-return, so a
        # cleared selection (every _refresh clears it) actually disables the
        # button rather than leaving it stale-enabled (FIBR-0128 D3).
        self._apply_forget_gating()
        account = self._selected_account()
        if account is None:
            # Leave the form untouched — a cleared selection must not wipe
            # in-progress input, and _refresh() now clears the selection every
            # time (INV-22).
            return
        self._name.setText(account.name)
        select_combo_data(self._type, account.type)
        # The RAW stored value, never the mask — the field is masked by echo
        # mode, and writing the mask here would round-trip "•••• 7890" into the
        # vault on the next Update (§ 4.1).
        self._account_number.setText(account.account_number or "")
        self._note.setText(account.note or "")

    @Slot()
    def _on_forget_password(self) -> None:
        self._error.clear()
        # Resolve the target ABOVE the confirm and act on the captured Account
        # below it. Nothing in this item can invalidate a selection mid-confirm;
        # FIBR-0198's auto-hide timer fires inside the confirm's nested event
        # loop, which is why the capture matters (that spec's § 4.5).
        account = self._selected_account()
        if account is None:  # defensive — the button gating precludes it
            return
        # Confirm before wiping, mirroring the delete action (FIBR-0128 D3). Forgetting
        # is recoverable (re-learned on the next locked import), but it's still the
        # user's saved credential, so it gets the same guard.
        if (
            QMessageBox.question(
                self,
                self.tr("Forget statement password"),
                self.tr("Forget the saved statement password for “{name}”?").format(
                    name=account.name
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._accounts.set_pdf_password(account.id, None)
        except VaultLockedError:
            # An idle auto-lock can fire while the confirm box is open — silent,
            # like every other handler here (FIBR-0128 INV-5).
            return
        self._refresh()

    @Slot()
    def _on_delete(self) -> None:
        self._error.clear()
        # Target resolved ABOVE the confirm, acted on below — see
        # _on_forget_password for why the capture matters.
        account = self._selected_account()
        if account is None:
            return
        # Confirm before deleting — parity with the Categories/Statements delete
        # actions, which all confirm (indie-review H-E). An in-use account is
        # refused by the service anyway (AccountInUseError), so the worst case is
        # losing an empty account; a plain confirm matches what users now expect.
        if (
            QMessageBox.question(
                self,
                self.tr("Delete account"),
                self.tr("Delete the account “{name}”?").format(name=account.name),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._accounts.delete_account(account.id)
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
        """Select the row displaying ``account_id``, whatever the sort order.

        The id is mapped to a POSITION first: ``select_by_index`` matches the
        insertion index written by ``tag_row``, and ids are 1-based database
        keys while indices are 0-based positions — the two silently disagree.
        An absent id leaves the current selection unchanged.
        """
        for index, account in enumerate(self._rows):
            if account.id == account_id:
                select_by_index(self._table, index)
                return

    def _refresh(self) -> None:
        # Presence only — the id-set query never pulls the stored password into the
        # UI (FIBR-0128 INV-1). A marked row shows a screen-reader-legible marker.
        self._rows = self._accounts.list_accounts()
        self._with_pw = self._accounts.account_ids_with_pdf_password()
        # The reconciliation health check for every account, read once (FIBR-0177 D6).
        # A total map, so ``statuses[account.id]`` is always present. Money-display
        # bits come from the vault connection + base currency, like the sibling tabs.
        statuses = self._reconciliation.account_statuses()
        exponent = read_minor_unit_exponent(self._vault.connection)
        symbol = TransactionService(self._vault).base_currency()
        with fill_guard(self._table):
            # CLEAR-then-fill (D6). The leading setRowCount(0) is load-bearing:
            # the sibling's reuse-rows shape lets a surviving selection ride its
            # item through a re-sort and land on a DIFFERENT account. Today's
            # QListWidget cleared on every repopulate, so this preserves the
            # existing behaviour rather than changing it (INV-22).
            self._table.setRowCount(0)
            self._table.setRowCount(len(self._rows))
            for row, account in enumerate(self._rows):
                recon_text = self._reconciliation_suffix(
                    statuses[account.id], exponent, symbol
                )
                key_text = (
                    self.tr("🔑 statement password saved")
                    if account.id in self._with_pw
                    else ""
                )
                items = {
                    _COL_NAME: QTableWidgetItem(account.name),
                    # The translated LABEL, not the stored token, or the column
                    # ships `credit_card` where the list showed "Credit card".
                    _COL_TYPE: QTableWidgetItem(
                        self._type_labels.get(account.type, account.type)
                    ),
                    _COL_NUMBER: QTableWidgetItem(
                        _mask_account_number(account.account_number)
                    ),
                    # `Account.note` is `str | None` and QTableWidgetItem(None)
                    # raises TypeError — the seeded Default has no note, so this
                    # is the first fill of almost every vault.
                    _COL_NOTE: QTableWidgetItem(account.note or ""),
                    # Reconciliation text FIRST, key second — a deliberate
                    # reversal of the old list line, because the column sorts by
                    # reconciliation severity.
                    _COL_STATUS: SortableItem(
                        " · ".join(part for part in (recon_text, key_text) if part),
                        self._severity_rank(statuses[account.id]),
                    ),
                }
                for col, item in items.items():
                    self._table.setItem(row, col, item)
                # AFTER the column-0 setItem: tag_row reads table.item(row, 0)
                # and silently no-ops when it is missing, which would leave every
                # selection unresolvable with no error anywhere.
                tag_row(self._table, row, row)
        self._apply_forget_gating()

    @staticmethod
    def _severity_rank(recon: AccountReconciliation) -> int:
        """The Status column's sort key — problems first, reconciled last."""
        if recon.status is ReconciliationStatus.OFF:
            return _RANK_OFF
        if recon.status is ReconciliationStatus.RECONCILED:
            return _RANK_RECONCILED
        return _RANK_QUIET  # NOT_ENOUGH_DATA / NOT_SUPPORTED

    def _reconciliation_suffix(
        self, recon: AccountReconciliation, exponent: int, symbol: str
    ) -> str:
        """The per-row reconciliation marker (FIBR-0177 D6): ``✓`` for a reconciled
        account, ``⚠ off by {money}`` for a single-period discrepancy (the magnitude
        rendered through the shared money formatter, currency-driven — not a
        hard-coded "R"), ``⚠ {n} periods don't reconcile`` for several, and **nothing**
        for NOT_ENOUGH_DATA / NOT_SUPPORTED (quiet, like an account with no saved
        password).

        Keeps its name though the output is now part of a Status **cell** rather
        than a line suffix — renaming it would touch FIBR-0177's citations for no
        behavioural gain. The three literals dropped their leading ``"  ·  "``
        separator when the marker moved into a cell (FIBR-0113 § 4.2).
        """
        if recon.status is ReconciliationStatus.RECONCILED:
            return self.tr("✓ balances reconcile")
        if recon.status is ReconciliationStatus.OFF:
            if recon.off_pair_count == 1:
                money = _format_amount(
                    to_display_decimal(abs(recon.discrepancy_minor), exponent), symbol
                )
                return self.tr("⚠ off by {money}").format(money=money)
            return self.tr("⚠ {n} periods don't reconcile").format(
                n=recon.off_pair_count
            )
        return ""
