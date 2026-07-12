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

from finbreak.errors import VaultLockedError
from finbreak.models import ConfirmedTransfer, TransferCandidate
from finbreak.services.auth import AuthService
from finbreak.services.transfer_detection import TransferDetectionService

# Column order is fixed so the qtbot cells are deterministically assertable (D9).
_COL_DATE = 0
_COL_AMOUNT = 1
_COL_FROM_TO = 2
_COL_DESCRIPTION = 3
_ARROW = "→"  # → : the From/To separator (D9)


class TransfersWidget(QWidget):
    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tab_transfers")
        self._detection = TransferDetectionService(service.vault)
        self._candidates: list[TransferCandidate] = []  # parallel to _suggested rows
        self._confirmed: list[
            ConfirmedTransfer
        ] = []  # parallel to _confirmed_table rows

        self.setWindowTitle(self.tr("Transfers"))

        self._suggested = self._make_table("transfers_suggested")
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

    def _make_table(self, object_name: str) -> QTableWidget:
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
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        return table

    def _refresh(self) -> None:
        self._candidates = self._detection.candidates()
        self._confirmed = self._detection.confirmed_transfers()
        self._fill(self._suggested, self._candidates)
        self._fill(self._confirmed_table, self._confirmed)
        self._on_selection_changed()

    def _fill(
        self,
        table: QTableWidget,
        rows: Sequence[TransferCandidate | ConfirmedTransfer],
    ) -> None:
        table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            from_to = f"{item.from_account} {_ARROW} {item.to_account}"
            table.setItem(row, _COL_DATE, QTableWidgetItem(item.debit.occurred_on))
            table.setItem(row, _COL_AMOUNT, QTableWidgetItem(str(item.display_amount)))
            table.setItem(row, _COL_FROM_TO, QTableWidgetItem(from_to))
            table.setItem(
                row, _COL_DESCRIPTION, QTableWidgetItem(item.debit.description)
            )

    @Slot()
    def _on_selection_changed(self) -> None:
        suggested = self._selected_row(self._suggested) is not None
        self._confirm_button.setEnabled(suggested)
        self._reject_button.setEnabled(suggested)
        self._confirm_all_button.setEnabled(bool(self._candidates))
        self._unlink_button.setEnabled(
            self._selected_row(self._confirmed_table) is not None
        )

    @Slot()
    def _on_confirm(self) -> None:
        index = self._selected_row(self._suggested)
        if index is None:
            return
        candidate = self._candidates[index]
        try:
            self._detection.confirm(candidate.debit.id, candidate.credit.id)
        except VaultLockedError:
            return  # auto-lock fired mid-click; the workspace is being torn down
        self._status.setText(self.tr("Confirmed %n transfer(s).", "", 1))
        self._refresh()

    @Slot()
    def _on_reject(self) -> None:
        index = self._selected_row(self._suggested)
        if index is None:
            return
        candidate = self._candidates[index]
        try:
            self._detection.reject(candidate.debit.id, candidate.credit.id)
        except VaultLockedError:
            return
        self._status.setText(self.tr("Rejected."))
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
    def candidate_count(self) -> int:
        return len(self._candidates)

    def _selected_row(self, table: QTableWidget) -> int | None:
        rows = {i.row() for i in table.selectedItems()}
        return next(iter(rows)) if len(rows) == 1 else None
