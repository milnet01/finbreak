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
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import FinbreakError, VaultLockedError
from finbreak.services import batch_import as batch
from finbreak.services.accounts import AccountService
from finbreak.services.batch_import import (
    TERMINAL_OUTCOMES,
    BatchFile,
    BatchImportService,
)
from finbreak.ui._table_state import remember_columns
from finbreak.ui.account_create import CreateAccountDialog
from finbreak.ui.account_picker import AccountPickerDialog
from finbreak.ui.modal import show_modal

COL_FILE, COL_ACCOUNT, COL_NEW, COL_DUPLICATE, COL_ERRORS, COL_STATUS = range(6)


def _with_parent(path: str) -> str:
    """``path``'s basename prefixed with its own parent directory's name."""
    return str(Path(Path(path).parent.name) / Path(path).name)


def file_labels(files: Sequence[BatchFile]) -> list[str]:
    """What each row's File cell reads, in order (§ 4.6).

    Rows can share a basename two ways: ``statement.pdf`` from two folders (§ 8
    rejects filename-based duplicate detection for exactly this reason), and the
    several statements fanned out of one OFX file, which share a path outright.
    So the label escalates — basename, then the basename prefixed with its
    parent directory when that disambiguates, else the full path — and a
    fanned-out OFX statement always appends its index, since no path prefix can
    separate siblings from the same file.

    Every row is labelled in ONE call because each label is a question about the
    whole set. Answering it per row re-tallied all three counters per row, so a
    batch cost O(N^2) on every refresh — and the chain this renders "can be
    hundreds of files long", by ``refresh``'s own account (FIBR-0327).
    """
    same_path = Counter(other.path for other in files)
    basenames = Counter(Path(other.path).name for other in files)
    parented = Counter(_with_parent(other.path) for other in files)

    labels: list[str] = []
    for record in files:
        path = Path(record.path)
        siblings = same_path[record.path]
        if siblings > 1 and record.statement_index is not None:
            labels.append(self_index_label(path.name, record.statement_index, siblings))
        elif basenames[path.name] == 1:
            labels.append(path.name)
        elif parented[_with_parent(record.path)] == 1:
            labels.append(_with_parent(record.path))
        else:
            labels.append(record.path)
    return labels


def self_index_label(name: str, index: int, total: int) -> str:
    return f"{name} [{index + 1} of {total}]"


class BatchReviewWidget(QWidget):
    """The review step. Owns the table and its three controls; the wizard owns
    the scan/ask/run chain that fills it (§ 4.7)."""

    import_requested = Signal()
    cancelled = Signal()
    closed = Signal()
    # A batch can CREATE an account (§ 3 decision 6), and the wizard's own two
    # account combos are filled once in its __init__ — so without this they
    # would still be listing a stale set if a pre-RUN Cancel returned the user
    # to the pick step. The single-file Create path already refreshes them.
    accounts_changed = Signal()

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
        # True from the moment RUN starts until it stops. Distinct from
        # `_finished`: during the run the table is neither a form (rows are
        # landing in the vault) nor yet the report.
        self._running = False
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
        # This widget owns two dialogs of its own (the picker and Create), so it
        # needs somewhere to show a rejection — it is not a child of the
        # wizard's error label.
        self._error = QLabel()
        self._error.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self._cancel_button)
        buttons.addStretch()
        buttons.addWidget(self._import_button)
        buttons.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addWidget(self._error)
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
        self._running = False
        self._error.clear()
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
        labels = file_labels(self._files)
        self._table.setRowCount(len(self._files))
        for row, record in enumerate(self._files):
            self._set(row, COL_FILE, labels[row], record.path)
            self._set(row, COL_ACCOUNT, self._account_name(record), record.path)
            self._set(row, COL_NEW, self._number(record.new_count), record.path)
            self._set(
                row, COL_DUPLICATE, self._number(record.duplicate_count), record.path
            )
            # Blank when zero, so it draws the eye only when it matters.
            self._set(row, COL_ERRORS, self._number(record.error_count), record.path)
            self._set(row, COL_STATUS, self.report_line(record), record.path)
        # Off during the run as well as after it. `can_import` stays true while
        # any `ready` record remains, so without this the button is live for the
        # whole run — and a second press rewinds the index and arms a SECOND
        # chain alongside the first.
        self._import_button.setEnabled(
            not self._finished
            and not self._running
            and BatchImportService.can_import(self._files)
        )

    def set_running(self, running: bool) -> None:
        """RUN has started (or stopped): the table is no longer a form."""
        self._running = running
        self.refresh()

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
        # The literal must sit INSIDE tr(): `lupdate` scans source text, so a
        # module constant passed through tr() is never extracted and can never
        # be translated (coding.md § 5.2).
        unplaced = self.tr("— pick one —")
        if record.account_id is None:
            return unplaced
        return self._account_names.get(record.account_id, unplaced)

    def _with_unreadable_rows(self, line: str, record: BatchFile) -> str:
        """Append the unreadable-row clause to any outcome that can carry one.

        ``error_count`` is set during SCAN, before the outcome is known, and the
        Errors column renders it whatever that outcome turns out to be. Appending
        the clause on the ``committed`` branch alone let an ``already_imported``
        row read *"nothing new in this file"* beside a cell reading 4 — one row
        contradicting itself (FIBR-0254).

        The two counts are separate strings rather than Qt's ``%n`` plural: no
        translation is loaded yet (FIBR-0017 is unshipped), and an untranslated
        ``%n`` string renders its source text verbatim, so the user would read
        *"1 row(s)"*. A translator still gets both forms.
        """
        if not record.error_count:
            return line
        if record.error_count == 1:
            return line + self.tr(", 1 row couldn't be read")
        return line + self.tr(", {n} rows couldn't be read").format(
            n=record.error_count
        )

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
            return self._with_unreadable_rows(
                self.tr("{new} added, {dup} duplicates").format(
                    new=record.result.inserted_count, dup=record.result.duplicate_count
                ),
                record,
            )
        if outcome == "already_imported":
            return self._with_unreadable_rows(
                self.tr("Already imported — nothing new in this file"), record
            )
        if outcome == "failed":
            template = (
                self.tr("Couldn't import this file — {why}")
                if record.preview is not None
                else self.tr("Couldn't read this file — {why}")
            )
            return template.format(why=self._translated(record.reason))
        if outcome in ("skipped", "not_attempted"):
            return self._translated(record.reason)
        return {
            "waiting": self.tr("Waiting…"),
            "ready": self.tr("Ready to import"),
            "needs_password": self.tr("Locked — we'll ask for the password"),
            "needs_mapping": self.tr("Needs its columns matched up"),
            "needs_account": self.tr("Pick an account"),
        }.get(outcome, "")

    def _translated(self, reason: str) -> str:
        """Translate a reason the SERVICE authored; pass anything else through.

        `services/batch_import.py` is Qt-free by design (§ 4.1), so its six fixed
        report sentences cannot call `tr()` where they are written. They are
        translated here, at the one place they reach a screen. A reason that is
        NOT one of them is an exception's own message — dynamic text, untranslated
        by the same established convention every other rejection in this app
        follows (`ManualEntryDialog._on_add` renders `str(exc)` verbatim).
        """
        return {
            batch.CANCELLED: self.tr("Not imported — the batch was cancelled"),
            batch.CAP_REACHED: self.tr(
                "Not imported — the batch reached its size limit"
            ),
            batch.PDF_UNREADABLE: self.tr(
                "Couldn't read this PDF — try your bank's CSV or OFX export."
            ),
            batch.UNDATED: self.tr("No dated transactions found in this file"),
            batch.SKIPPED_LOCKED: self.tr("Skipped — we couldn't unlock this file"),
            batch.SKIPPED_UNMAPPED: self.tr("Skipped — no column mapping was set"),
        }.get(reason, reason)

    # -- setting an account ---------------------------------------------------
    @Slot(int, int)
    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column == COL_ACCOUNT:
            self._choose_account(row)

    def _choose_account(self, row: int) -> None:
        """Open the destination picker for one row (§ 4.6).

        Clickable exactly on rows whose ``parsed`` is not ``None`` and whose
        outcome is not terminal. ``waiting`` is excluded by the parse test
        (nothing is parsed yet, so a picker would hand ``preview_result`` a
        ``None``); ``committed``, ``failed``, ``skipped`` and ``not_attempted``
        are excluded by outcome, NOT by that test — see the comment below, which
        is the half this docstring used to get wrong.
        """
        # Not while the run is in flight either: retargeting a row the chain is
        # about to reach would re-dedup it against a vault that is changing
        # underneath, and retargeting one it has already committed is the
        # silently-re-imported case § 4.6 excludes `committed` rows for.
        if self._finished or self._running or not 0 <= row < len(self._files):
            return
        record = self._files[row]
        # `parsed` alone is not enough. `_settle_parse` stores the parse BEFORE
        # the undated check fails the record, so a `failed` row carries one; so
        # does a `not_attempted` row that was `ready` when a cap or a cancel
        # stopped the batch. The picker would open, the user would choose, and
        # `set_account`'s own terminal guard would silently discard it — a dead
        # control on the one screen the user is asked to trust.
        if record.parsed is None or record.outcome in TERMINAL_OUTCOMES:
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
        self._error.clear()
        try:
            account = self._accounts.add_account(
                dialog.entered_name(),
                dialog.entered_type(),
                account_number=dialog.entered_number(),
            )
        except VaultLockedError:
            return  # auto-lock fired mid-edit — silent, like the other handlers
        except (ValueError, FinbreakError) as exc:
            # SAY SO. Swallowing this made the dialog vanish with the row still
            # reading "— pick one —" and no hint that a duplicate name was the
            # reason — the single-file twin (`_create_account_from`) has always
            # shown the message.
            self._error.setText(str(exc))
            return
        self.accounts_changed.emit()
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
