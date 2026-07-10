"""StatementsWidget — the Statements tab: list imports + delete (FIBR-0052 D11).

A plain read+delete tab (``objectName`` ``tab_statements``): a ``QTableWidget``
of one row per recorded import (account · period · file · imported · linked-
transaction count) + a *Delete selected* button (``button_delete_statement``,
disabled with no selection) + a ``changed`` signal emitted after a successful
delete (the shell refreshes Home + the status count on it, INV-10/INV-11).

No add/edit — statements are created by importing. There is **no money column**
(the count is a count, not an amount), so no ``_format_amount``. Every string
goes through ``tr()`` and every widget sits in a layout manager (coding.md § 5.2).
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import VaultLockedError
from finbreak.models import StatementRow
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.statements import StatementService
from finbreak.ui.account_picker import AccountPickerDialog
from finbreak.ui.modal import show_modal

# Fixed column indices (the table's shape; headers are the translated labels).
_COL_ACCOUNT = 0
_COL_PERIOD = 1
_COL_FILE = 2
_COL_IMPORTED = 3
_COL_COUNT = 4


class StatementsWidget(QWidget):
    changed = Signal()  # a delete succeeded — the shell refreshes Home + the count
    reassigned = Signal()  # a Change-account move succeeded (FIBR-0059) — distinct
    # from `changed` because the shell's `changed` handler reports "Statement
    # deleted"; a move shows its own message.

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tab_statements")
        self._statements = StatementService(service.vault)
        self._accounts = AccountService(service.vault)  # for the Change-account picker
        self._rows: list[StatementRow] = []  # parallel to the table rows

        self.setWindowTitle(self.tr("Statements"))

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            [
                self.tr("Account"),
                self.tr("Period"),
                self.tr("File"),
                self.tr("Imported"),
                self.tr("Transactions"),
            ]
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self._reassign_button = QPushButton(self.tr("Change account"))
        self._reassign_button.setObjectName("button_reassign_statement")
        self._reassign_button.setEnabled(False)  # no selection yet
        self._delete_button = QPushButton(self.tr("Delete selected"))
        self._delete_button.setObjectName("button_delete_statement")
        self._delete_button.setEnabled(False)  # no selection yet

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self._reassign_button)
        actions.addWidget(self._delete_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(actions)

        self._reassign_button.clicked.connect(self._on_reassign)
        self._delete_button.clicked.connect(self._on_delete)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        self.refresh()

    def refresh(self) -> None:
        """Re-list every recorded statement (all accounts) with its live count."""
        self._rows = self._statements.list_statements()
        self._table.setRowCount(len(self._rows))
        for row, statement in enumerate(self._rows):
            period = f"{statement.period_start} – {statement.period_end}"
            values = {
                _COL_ACCOUNT: statement.account_name,
                _COL_PERIOD: period,
                _COL_FILE: statement.source_filename or "",
                _COL_IMPORTED: statement.imported_at,
                _COL_COUNT: str(statement.transaction_count),
            }
            for col, text in values.items():
                self._table.setItem(row, col, QTableWidgetItem(text))
        self._on_selection_changed()

    @Slot()
    def _on_selection_changed(self) -> None:
        has_selection = self._selected_row() is not None
        self._reassign_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    @Slot()
    def _on_reassign(self) -> None:
        """Move the selected statement to another account (FIBR-0059): open the
        account picker (preselected to the current account), and on confirm — if
        the chosen account differs — atomically re-point the period + its
        transactions, then refresh + emit ``reassigned``. A same-account pick is
        skipped (INV-5); a span collision surfaces a warning (INV-3); an idle
        auto-lock mid-move is caught (INV-10, as in ``_on_delete``)."""
        index = self._selected_row()
        if index is None:
            return
        statement = self._rows[index]
        dialog = AccountPickerDialog(
            self._accounts.list_accounts(), statement.account_id, self
        )
        # Non-blocking (FIBR-0065): a lock while the picker is open destroys it
        # before _apply_reassign runs, so no read hits a deleted C++ object.
        show_modal(dialog, lambda: self._apply_reassign(dialog, statement))

    def _apply_reassign(
        self, dialog: AccountPickerDialog, statement: StatementRow
    ) -> None:
        new_account_id = dialog.selected_account_id()
        if new_account_id == statement.account_id:
            return  # same account — nothing to move (INV-5)
        try:
            self._statements.reassign_account(statement.id, new_account_id)
        except VaultLockedError:
            return  # defense-in-depth; INV-2 destroys the dialog before this slot
        except ValueError:  # the target account already has this span (INV-3)
            QMessageBox.warning(
                self,
                self.tr("Change account"),
                self.tr(
                    "That account already has a statement for this period. "
                    "Delete or move it first."
                ),
            )
            return
        self.refresh()
        self.reassigned.emit()

    @Slot()
    def _on_delete(self) -> None:
        index = self._selected_row()
        if index is None:
            return
        statement = self._rows[index]
        confirmed = QMessageBox.question(
            self,
            self.tr("Delete statement"),
            self.tr(
                "Delete this statement and its %n transaction(s)? "
                "This cannot be undone.",
                "",
                statement.transaction_count,
            ),
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self._statements.delete_statement(statement.id)
        except VaultLockedError:
            # An idle auto-lock can fire while this (nested, untracked) confirm box
            # is open — the vault is then closed and this whole workspace is being
            # torn down (INV-3). There is nothing to delete against a locked vault;
            # the next unlock rebuilds a fresh Statements tab. Catching the specific
            # locked-vault error keeps the click from crashing the slot.
            return
        self.refresh()
        self.changed.emit()

    # --- test / shell accessors -------------------------------------------- #
    def statement_count(self) -> int:
        """The number of statements currently listed (0 when none imported)."""
        return len(self._rows)

    def _selected_row(self) -> int | None:
        rows = {i.row() for i in self._table.selectedItems()}
        return next(iter(rows)) if len(rows) == 1 else None

    def selected_period_id(self) -> int | None:
        """The id of the selected statement, or ``None`` with no selection."""
        index = self._selected_row()
        return self._rows[index].id if index is not None else None

    def _select_period(self, period_id: int) -> None:
        """Select the row for ``period_id`` (used by the UI tests)."""
        for i, statement in enumerate(self._rows):
            if statement.id == period_id:
                self._table.selectRow(i)
                return
