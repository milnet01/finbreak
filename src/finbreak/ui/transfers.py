"""Transfers tab — the suggest-then-confirm review surface (FIBR-0011 D9).

A ``TransfersWidget`` (mirroring ``RulesWidget``): two ``QTableWidget``s — suggested
pairs (Confirm / Reject / Confirm all) above confirmed transfers (Unlink) — over one
``TransferDetectionService``. Actions apply **directly** (no modal: each is reversible
or low-harm, D8) and every slot catches ``VaultLockedError`` and returns, exactly like
``RulesWidget``. Each table row is a single-valued view of a two-row pair: Date +
Description are the debit row's, Amount is the shared display magnitude, From → To is
one ``"{from} → {to}"`` cell (debit account → credit account). All strings go through
``tr()`` and every widget sits in a layout manager (coding.md § 5.2).
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.datetime_format import format_date
from finbreak.errors import VaultLockedError
from finbreak.models import ConfirmedTransfer, TransferCandidate
from finbreak.services.auth import DATETIME_SYSTEM, AuthService, DateTimePrefs
from finbreak.services.transactions import TransactionService
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.ui._amount import _format_amount
from finbreak.ui._table_state import (
    SortableItem,
    enable_sorting,
    fill_guard,
    remember_columns,
    selected_index,
    selected_indexes,
    tag_row,
)

# Column order is fixed so the qtbot cells are deterministically assertable (D9).
_COL_DATE = 0
_COL_AMOUNT = 1
_COL_FROM_TO = 2
_COL_DESCRIPTION = 3
_ARROW = "→"  # → : the From/To separator (D9)


class TransfersWidget(QWidget):
    def __init__(
        self,
        service: AuthService,
        prefs: DateTimePrefs | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("tab_transfers")
        self._service = service
        self._detection = TransferDetectionService(service.vault)
        # Display-only formatting input, as StatementsWidget takes it (FIBR-0083).
        # Absent -> the zero-config all-"system" default.
        self._prefs = prefs or DateTimePrefs(
            DATETIME_SYSTEM, DATETIME_SYSTEM, DATETIME_SYSTEM
        )
        self._candidates: list[TransferCandidate] = []  # parallel to _suggested rows
        self._confirmed: list[
            ConfirmedTransfer
        ] = []  # parallel to _confirmed_table rows

        self.setWindowTitle(self.tr("Transfers"))

        # Only the SUGGESTED table takes a plural selection (FIBR-0201 D2/INV-1) —
        # bulk Unlink is out of scope, and both tables share this builder, so this
        # is a parameter rather than an edited line.
        self._suggested = self._make_table("transfers_suggested", multi_select=True)
        self._confirmed_table = self._make_table("transfers_confirmed")

        self._confirm_button = QPushButton(self.tr("Confirm"))
        self._confirm_button.setObjectName("transfers_confirm")
        self._reject_button = QPushButton(self.tr("Reject"))
        self._reject_button.setObjectName("transfers_reject")
        self._confirm_all_button = QPushButton(self.tr("Confirm all"))
        self._confirm_all_button.setObjectName("transfers_confirm_all")
        self._unlink_button = QPushButton(self.tr("Unlink"))
        self._unlink_button.setObjectName("transfers_unlink")
        self._status = QLabel()

        suggested_actions = QHBoxLayout()
        suggested_actions.addWidget(self._confirm_button)
        suggested_actions.addWidget(self._reject_button)
        suggested_actions.addStretch()
        suggested_actions.addWidget(self._confirm_all_button)

        confirmed_actions = QHBoxLayout()
        confirmed_actions.addWidget(self._unlink_button)
        confirmed_actions.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Suggested transfers")))
        layout.addWidget(self._suggested)
        layout.addLayout(suggested_actions)
        layout.addWidget(QLabel(self.tr("Confirmed transfers")))
        layout.addWidget(self._confirmed_table)
        layout.addLayout(confirmed_actions)
        layout.addWidget(self._status)

        self._confirm_button.clicked.connect(self._on_confirm)
        self._reject_button.clicked.connect(self._on_reject)
        self._confirm_all_button.clicked.connect(self._on_confirm_all)
        self._unlink_button.clicked.connect(self._on_unlink)
        self._suggested.itemSelectionChanged.connect(self._on_selection_changed)
        self._confirmed_table.itemSelectionChanged.connect(self._on_selection_changed)

        self._refresh()

    def _make_table(
        self, object_name: str, *, multi_select: bool = False
    ) -> QTableWidget:
        table = QTableWidget(0, 4)
        table.setObjectName(object_name)
        table.setHorizontalHeaderLabels(
            [
                self.tr("Date"),
                self.tr("Amount"),
                self.tr("From → To"),
                self.tr("Description"),
            ]
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # MultiSelection, not ExtendedSelection (D8): a plain click toggles a row in
        # or out, with no Ctrl/Shift knowledge required of a non-technical audience.
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
            if multi_select
            else QAbstractItemView.SelectionMode.SingleSelection
        )
        enable_sorting(table)  # click a header to sort; second click toggles order
        remember_columns(table)  # persist column widths across sessions (FIBR-0117)
        return table

    def set_datetime_prefs(self, prefs: DateTimePrefs) -> None:
        """Adopt new display prefs and re-render, so a Settings change takes
        effect without a relaunch (FIBR-0083 D7)."""
        self._prefs = prefs
        self._refresh()

    def _refresh(self) -> None:
        self._candidates = self._detection.candidates()
        self._confirmed = self._detection.confirmed_transfers()
        # The base-currency code, read fresh like the Transactions/Home tabs, so the
        # magnitude renders with the currency glyph + locale grouping (FIBR-0153).
        symbol = TransactionService(self._service.vault).base_currency()
        self._fill(self._suggested, self._candidates, symbol)
        self._fill(self._confirmed_table, self._confirmed, symbol)
        self._on_selection_changed()

    def _fill(
        self,
        table: QTableWidget,
        rows: Sequence[TransferCandidate | ConfirmedTransfer],
        symbol: str,
    ) -> None:
        with fill_guard(table):
            table.setRowCount(len(rows))
            for row, item in enumerate(rows):
                from_to = f"{item.from_account} {_ARROW} {item.to_account}"
                table.setItem(
                    row,
                    _COL_DATE,
                    # The cell now READS in the user's date format, so it can no
                    # longer double as its own sort key: this table sorts, and
                    # DD/MM/YYYY sorts by day-of-month. The stored ISO string
                    # stays as the key, which is what kept it chronological.
                    SortableItem(
                        format_date(item.debit.occurred_on, self._prefs.date_format),
                        item.debit.occurred_on,
                    ),
                )
                table.setItem(
                    row,
                    _COL_AMOUNT,
                    # display_amount is a positive magnitude; the SortableItem keeps
                    # the Decimal as the numeric sort key (D9), unchanged.
                    SortableItem(
                        _format_amount(item.display_amount, symbol),
                        item.display_amount,
                    ),
                )
                table.setItem(row, _COL_FROM_TO, QTableWidgetItem(from_to))
                table.setItem(
                    row, _COL_DESCRIPTION, QTableWidgetItem(item.debit.description)
                )
                tag_row(table, row, row)  # col-0 tag = insertion index (sort-safe)

    @Slot()
    def _on_selection_changed(self) -> None:
        suggested = bool(self._selected_rows())
        self._confirm_button.setEnabled(suggested)
        self._reject_button.setEnabled(suggested)
        self._confirm_all_button.setEnabled(bool(self._candidates))
        self._unlink_button.setEnabled(
            self._selected_row(self._confirmed_table) is not None
        )

    def _selected_pairs(self) -> list[tuple[int, int]]:
        """The selected suggestions as ``(debit_id, credit_id)`` domain ids,
        resolved **before** any mutation (INV-3). Never dereference
        ``self._candidates[i]`` mid-loop: ``_refresh()`` rebuilds and re-sorts it,
        so an index resolved before the mutation and used after it can name a
        different pair (FIBR-0113)."""
        return [
            (self._candidates[i].debit.id, self._candidates[i].credit.id)
            for i in self._selected_rows()
        ]

    @Slot()
    def _on_confirm(self) -> None:
        pairs = self._selected_pairs()
        if not pairs:
            return
        try:
            count = self._detection.confirm_many(pairs)
        except VaultLockedError:
            return  # auto-lock fired mid-click; the workspace is being torn down
        self._status.setText(self._confirmed_status(len(pairs), count))
        self._refresh()

    def _confirmed_status(self, asked: int, confirmed: int) -> str:
        """The Confirmed status line, naming any pair the consumed-set skipped.
        A user who deliberately selected five rows and got three is owed the
        reason; under ``Confirm all`` the same drop is invisible by design, which
        is why it never needed saying before (§4.8)."""
        text = self.tr("Confirmed %n transfer(s).", "", confirmed)
        skipped = asked - confirmed
        if skipped > 0:
            text += " " + self.tr(
                "%n suggestion(s) were skipped — they share a transaction with a "
                "transfer you just confirmed.",
                "",
                skipped,
            )
        return text

    @Slot()
    def _on_reject(self) -> None:
        pairs = self._selected_pairs()
        if not pairs:
            return
        try:
            count = self._detection.reject_many(pairs)
        except VaultLockedError:
            return
        # n == 1 keeps today's string byte-for-byte: "Rejected 1 transfer(s)." is
        # the same regression D9 forbids on the Statements tab (INV-14).
        self._status.setText(
            self.tr("Rejected.")
            if count == 1
            else self.tr("Rejected %n transfer(s).", "", count)
        )
        self._refresh()

    @Slot()
    def _on_confirm_all(self) -> None:
        try:
            count = self._detection.confirm_all()
        except VaultLockedError:
            return
        self._status.setText(self.tr("Confirmed %n transfer(s).", "", count))
        self._refresh()

    @Slot()
    def _on_unlink(self) -> None:
        index = self._selected_row(self._confirmed_table)
        if index is None:
            return
        try:
            self._detection.unlink(self._confirmed[index].pair_id)
        except VaultLockedError:
            return
        self._status.setText(self.tr("Unlinked."))
        self._refresh()

    # --- test / shell accessors -------------------------------------------- #
    def _selected_rows(self) -> list[int]:
        # The tagged parallel-list indexes of every selected suggestion, in
        # insertion order — which is candidate order, so it decides which of two
        # conflicting pairs confirm_many keeps (INV-4).
        return selected_indexes(self._suggested)

    def _selected_row(self, table: QTableWidget) -> int | None:
        # The tagged parallel-list index of the selection — correct after a re-sort
        # (the visual row order can differ from _candidates/_confirmed order).
        return selected_index(table)
