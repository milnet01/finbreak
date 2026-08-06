"""BatchReviewWidget — the import wizard's fourth step (FIBR-0085 § 4.6).

One table listing every selected file: where it is going, what it will add, and
— once the run finishes — what it did. It is the progress indicator during SCAN
(§ 6: rows fill in as each file is classified), the approval screen during
REVIEW, and the report afterwards. There is no separate progress dialog, which
is § 4.7's whole point: Qt's documented modal-progress pattern pumps the event
queue from inside the loop, and re-entering the event loop is exactly the
FIBR-0065 crash class.

``tests/features/dialog_lifecycle/`` greps this file for BOTH forbidden tokens —
the blocking-dialog one and the event-pumping one (INV-6). A new UI module is
outside that guard until it is named in its ``_FILES`` tuple, and a guard that
silently does not cover new code is worse than no guard. (Neither token is
spelled out here, because the guard reads comments too — deliberately, since a
comment becomes code the moment someone uncomments it.)

All strings go through ``tr()`` and every widget sits in a layout manager
(coding.md § 5.2).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import FinbreakError, VaultLockedError
from finbreak.services.accounts import AccountService
from finbreak.services.batch_import import BatchFile, BatchImportService
from finbreak.ui._table_state import remember_columns
from finbreak.ui.account_create import CreateAccountDialog
from finbreak.ui.account_picker import AccountPickerDialog
from finbreak.ui.modal import show_modal

COL_FILE, COL_ACCOUNT, COL_NEW, COL_DUPLICATE, COL_ERRORS, COL_STATUS = range(6)

_UNPLACED = "— pick one —"


def file_label(record: BatchFile, files: Sequence[BatchFile]) -> str:
    """What the File cell reads (§ 4.6).

    Rows can share a basename two ways: ``statement.pdf`` from two folders (§ 8
    rejects filename-based duplicate detection for exactly this reason), and the
    several statements fanned out of one OFX file, which share a path outright.
    So the label escalates — basename, then the basename prefixed with its
    parent directory when that disambiguates, else the full path — and a
    fanned-out OFX statement always appends its index, since no path prefix can
    separate siblings from the same file.
    """
    path = Path(record.path)
    siblings = [other for other in files if other.path == record.path]
    if len(siblings) > 1 and record.statement_index is not None:
        return self_index_label(path.name, record.statement_index, len(siblings))

    basenames = Counter(Path(other.path).name for other in files)
    if basenames[path.name] == 1:
        return path.name
    with_parent = str(Path(path.parent.name) / path.name)
    parented = Counter(
        str(Path(Path(o.path).parent.name) / Path(o.path).name) for o in files
    )
    if parented[with_parent] == 1:
        return with_parent
    return record.path


def self_index_label(name: str, index: int, total: int) -> str:
    return f"{name} [{index + 1} of {total}]"


class BatchReviewWidget(QWidget):
    """The review step. Owns the table and its three controls; the wizard owns
    the scan/ask/run chain that fills it (§ 4.7)."""

    import_requested = Signal()
    cancelled = Signal()
    closed = Signal()

    def __init__(
        self,
        batch: BatchImportService,
        accounts: AccountService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._batch = batch
        self._accounts = accounts
        self._files: list[BatchFile] = []
        self._finished = False
        self._account_names: dict[int, str] = {}

        self._table = QTableWidget(0, 6)
        # Named so remember_columns has a settings key of its own
        # ("columns/import_batch_table") — an unnamed table shares the empty key
        # with every other unnamed one and cross-corrupts their widths
        # (the FIBR-0012 lesson).
        self._table.setObjectName("import_batch_table")
        self._table.setHorizontalHeaderLabels(
            [
                self.tr("File"),
                self.tr("Account"),
                self.tr("New"),
                self.tr("Duplicate"),
                self.tr("Errors"),
                self.tr("Status"),
            ]
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            COL_STATUS, QHeaderView.ResizeMode.Stretch
        )
        remember_columns(self._table)
        self._table.cellClicked.connect(self._on_cell_clicked)

        self._import_button = QPushButton(self.tr("Import all"))
        self._import_button.setEnabled(False)
        self._cancel_button = QPushButton(self.tr("Cancel"))
        self._close_button = QPushButton(self.tr("Close"))
        self._close_button.hide()  # appears only once RUN has finished

        buttons = QHBoxLayout()
        buttons.addWidget(self._cancel_button)
        buttons.addStretch()
        buttons.addWidget(self._import_button)
        buttons.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(buttons)

        self._import_button.clicked.connect(self.import_requested)
        self._cancel_button.clicked.connect(self.cancelled)
        self._close_button.clicked.connect(self.closed)

    # -- population -----------------------------------------------------------
    def set_files(self, files: list[BatchFile]) -> None:
        """Adopt a fresh batch. The table is on screen before SCAN starts, so it
        fills in row by row rather than hiding behind a progress dialog (§ 6)."""
        self._files = files
        self._finished = False
        self._close_button.hide()
        self._cancel_button.show()
        self._import_button.show()
        self.refresh()

    def refresh(self) -> None:
        """Re-render every row from the records. Called after each scan and run
        turn, and after every account change.

        The account names are snapshotted ONCE per call, not read per row: this
        runs on every turn of a chain that can be hundreds of files long, and a
        per-row query would put a vault read behind every cell. The snapshot is
        also what makes the method lock-safe — an idle auto-lock between turns
        leaves the last names on screen rather than raising out of a repaint.
        """
        try:
            self._account_names = {a.id: a.name for a in self._accounts.list_accounts()}
        except VaultLockedError:
            pass  # keep the previous snapshot; the shell is tearing this down
        self._table.setRowCount(len(self._files))
        for row, record in enumerate(self._files):
            self._set(row, COL_FILE, file_label(record, self._files), record.path)
            self._set(row, COL_ACCOUNT, self._account_name(record), record.path)
            self._set(row, COL_NEW, self._number(record.new_count), record.path)
            self._set(
                row, COL_DUPLICATE, self._number(record.duplicate_count), record.path
            )
            # Blank when zero, so it draws the eye only when it matters.
            self._set(row, COL_ERRORS, self._number(record.error_count), record.path)
            self._set(row, COL_STATUS, self.report_line(record), record.path)
        self._import_button.setEnabled(
            not self._finished and BatchImportService.can_import(self._files)
        )

    def finish(self) -> None:
        """RUN is over: the table is the report now, not a form (§ 4.6), and
        Close — the one control that emits ``done`` — appears."""
        self._finished = True
        self._cancel_button.hide()
        self._import_button.hide()
        self._close_button.show()
        self.refresh()

    def _set(self, row: int, column: int, text: str, tooltip: str) -> None:
        item = QTableWidgetItem(text)
        item.setToolTip(tooltip)  # the full path, on every row regardless
        self._table.setItem(row, column, item)

    @staticmethod
    def _number(value: int) -> str:
        return str(value) if value else ""

    def _account_name(self, record: BatchFile) -> str:
        if record.account_id is None:
            return self.tr(_UNPLACED)
        return self._account_names.get(record.account_id, self.tr(_UNPLACED))

    def report_line(self, record: BatchFile) -> str:
        """What each outcome tells the user (§ 4.8).

        Two outcomes carry two wordings, for the same reason: each is reachable
        from two passes, and one sentence cannot serve both. A SCAN ``failed``
        genuinely could not read the file, whereas INV-1's failure is a
        ``ValueError`` out of ``commit_import`` on a file that read perfectly —
        telling a user their file was unreadable when the commit rejected its
        span sends them to fix the wrong thing. The two are told apart by
        whether a preview was ever built. ``not_attempted``'s pair is carried in
        ``reason``, because "the batch was cancelled" is simply false for a user
        who selected 201 files and cancelled nothing.
        """
        outcome = record.outcome
        if outcome == "committed" and record.result is not None:
            line = self.tr("{new} added, {dup} duplicates").format(
                new=record.result.inserted_count, dup=record.result.duplicate_count
            )
            if record.error_count:
                line += self.tr(", {n} rows couldn't be read").format(
                    n=record.error_count
                )
            return line
        if outcome == "already_imported":
            return self.tr("Already imported — nothing new in this file")
        if outcome == "failed":
            template = (
                self.tr("Couldn't import this file — {why}")
                if record.preview is not None
                else self.tr("Couldn't read this file — {why}")
            )
            return template.format(why=record.reason)
        if outcome in ("skipped", "not_attempted"):
            return record.reason
        return {
            "waiting": self.tr("Waiting…"),
            "ready": self.tr("Ready to import"),
            "needs_password": self.tr("Locked — we'll ask for the password"),
            "needs_mapping": self.tr("Needs its columns matched up"),
            "needs_account": self.tr("Pick an account"),
        }.get(outcome, "")

    # -- setting an account ---------------------------------------------------
    @Slot(int, int)
    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column == COL_ACCOUNT:
            self._choose_account(row)

    def _choose_account(self, row: int) -> None:
        """Open the destination picker for one row (§ 4.6).

        Clickable exactly on rows whose ``parsed`` is not ``None`` and whose
        outcome is not ``committed`` — which excludes ``failed``, ``skipped``,
        ``not_attempted`` and any row still ``waiting`` (all of which reach the
        table with nothing parsed, so a picker would hand ``preview_result`` a
        ``None``), and excludes a row already written to the vault (retargeting
        it would silently re-dedup against rows that are already there).
        """
        if self._finished or not 0 <= row < len(self._files):
            return
        record = self._files[row]
        if record.parsed is None or record.outcome == "committed":
            return
        try:
            accounts = self._accounts.list_accounts()
        except VaultLockedError:
            return  # auto-lock fired — silent, like the other handlers
        dialog = AccountPickerDialog(
            accounts,
            record.account_id if record.account_id is not None else -1,
            parent=self,
            # § 3 decision 6: the batch never creates an account without being
            # asked, but it does offer — prefilled from the statement.
            hint=record.hint,
        )
        dialog.create_requested.connect(lambda: self._create_account(record))
        show_modal(dialog, lambda: self._apply_account(record, dialog))

    def _apply_account(self, record: BatchFile, dialog: AccountPickerDialog) -> None:
        account_id = dialog.selected_account_id()
        if account_id is None:
            return
        self._settle(record, account_id)

    def _create_account(self, record: BatchFile) -> None:
        """The Create affordance, prefilled from the statement (§ 3 decision 6).
        Nothing is written until the user accepts the dialog."""
        if record.hint is None:
            return
        create = CreateAccountDialog(
            number=record.hint.number,
            name=record.hint.name,
            family=record.hint.family,
            parent=self,
        )
        show_modal(create, lambda: self._created(record, create))

    def _created(self, record: BatchFile, dialog: CreateAccountDialog) -> None:
        try:
            account = self._accounts.add_account(
                dialog.entered_name(),
                dialog.entered_type(),
                account_number=dialog.entered_number(),
            )
        except VaultLockedError:
            return
        except (ValueError, FinbreakError):
            return
        self._settle(record, account.id)

    def _settle(self, record: BatchFile, account_id: int) -> None:
        """Point the record at ``account_id`` and re-evaluate the WHOLE batch —
        one row's destination changes which rows every *other* row in that
        account may claim (§ 4.5), and it can move a record back out of
        ``already_imported`` (INV-10)."""
        try:
            self._batch.set_account(record, account_id)
            self._batch.review(self._files)
        except VaultLockedError:
            return
        self.refresh()
