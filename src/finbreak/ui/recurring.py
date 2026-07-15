"""Recurring tab — the suggest-then-confirm review surface for detected recurring
money (FIBR-0142 D11).

A ``RecurringWidget`` mirroring the Transfers tab: two ``QTableWidget``s — Suggested
items (Confirm / Dismiss) above Confirmed items (Un-confirm) — over one
``RecurringService``. Detection is clock-driven off ``date.today()`` at refresh
(INV-2: the service stays clock-injected; the widget supplies the clock). Each action
applies directly (each is reversible via the opposite decision) and every slot catches
``VaultLockedError`` and returns, exactly like ``TransfersWidget``. The stored/compared
direction & cadence are stable ASCII enum tokens; only their column **text** is a
``tr()``-ed label (INV-11). All strings go through ``tr()`` and every widget sits in a
layout manager (coding.md § 5.2). The **Next due** column may show a *past* date for an
active-but-overdue item (INV-7) — expected. The Home dashboard card is deferred to
FIBR-0143, which consumes ``RecurringService.summary()`` (built + tested here).
"""

from __future__ import annotations

from datetime import date

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
from finbreak.models import Cadence, Direction, RecurringItem
from finbreak.services.auth import AuthService
from finbreak.services.recurring import RecurringService
from finbreak.ui._table_state import (
    SortableItem,
    enable_sorting,
    fill_guard,
    remember_columns,
    selected_index,
    tag_row,
)

# Column order is fixed so the qtbot cells are deterministically assertable (D11).
_COL_MERCHANT = 0
_COL_DIRECTION = 1
_COL_CADENCE = 2
_COL_AMOUNT = 3
_COL_NEXT_DUE = 4
_COL_SEEN = 5


class RecurringWidget(QWidget):
    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tab_recurring")
        self._recurring = RecurringService(service.vault)
        self._suggested_items: list[RecurringItem] = []  # parallel to _suggested rows
        self._confirmed_items: list[RecurringItem] = []  # parallel to _confirmed rows

        self.setWindowTitle(self.tr("Recurring"))

        self._suggested = self._make_table("recurring_suggested")
        self._confirmed_table = self._make_table("recurring_confirmed")

        self._confirm_button = QPushButton(self.tr("Confirm"))
        self._confirm_button.setObjectName("recurring_confirm")
        self._dismiss_button = QPushButton(self.tr("Dismiss"))
        self._dismiss_button.setObjectName("recurring_dismiss")
        self._unconfirm_button = QPushButton(self.tr("Un-confirm"))
        self._unconfirm_button.setObjectName("recurring_unconfirm")
        self._status = QLabel()

        suggested_actions = QHBoxLayout()
        suggested_actions.addWidget(self._confirm_button)
        suggested_actions.addWidget(self._dismiss_button)
        suggested_actions.addStretch()

        confirmed_actions = QHBoxLayout()
        confirmed_actions.addWidget(self._unconfirm_button)
        confirmed_actions.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Suggested recurring items")))
        layout.addWidget(self._suggested)
        layout.addLayout(suggested_actions)
        layout.addWidget(QLabel(self.tr("Confirmed recurring items")))
        layout.addWidget(self._confirmed_table)
        layout.addLayout(confirmed_actions)
        layout.addWidget(self._status)

        self._confirm_button.clicked.connect(self._on_confirm)
        self._dismiss_button.clicked.connect(self._on_dismiss)
        self._unconfirm_button.clicked.connect(self._on_unconfirm)
        self._suggested.itemSelectionChanged.connect(self._on_selection_changed)
        self._confirmed_table.itemSelectionChanged.connect(self._on_selection_changed)

        self.refresh()

    def _make_table(self, object_name: str) -> QTableWidget:
        table = QTableWidget(0, 6)
        table.setObjectName(object_name)
        table.setHorizontalHeaderLabels(
            [
                self.tr("Merchant"),
                self.tr("Direction"),
                self.tr("Cadence"),
                self.tr("Amount"),
                self.tr("Next due"),
                self.tr("Seen"),
            ]
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        enable_sorting(table)  # click a header to sort; second click toggles order
        remember_columns(table)  # persist column widths across sessions (FIBR-0117)
        return table

    def refresh(self) -> None:
        """Re-read the vault on view (INV-2/D9). One ``snapshot`` pass partitions the
        detected items into Suggested / Confirmed; the summary is the FIBR-0143 card's,
        not shown here."""
        suggested, confirmed, _summary = self._recurring.snapshot(date.today())
        self._suggested_items = suggested
        self._confirmed_items = confirmed
        self._fill(self._suggested, suggested)
        self._fill(self._confirmed_table, confirmed)
        if not suggested and not confirmed:
            self._status.setText(
                self.tr(
                    "No recurring items detected yet — "
                    "import a few months of statements."
                )
            )
        else:
            self._status.setText("")
        self._on_selection_changed()

    def _fill(self, table: QTableWidget, items: list[RecurringItem]) -> None:
        with fill_guard(table):
            table.setRowCount(len(items))
            for row, item in enumerate(items):
                table.setItem(row, _COL_MERCHANT, QTableWidgetItem(item.merchant))
                table.setItem(
                    row, _COL_DIRECTION, QTableWidgetItem(self._direction_label(item))
                )
                table.setItem(
                    row, _COL_CADENCE, QTableWidgetItem(self._cadence_label(item))
                )
                table.setItem(
                    row, _COL_AMOUNT, SortableItem(str(item.amount), item.amount)
                )
                table.setItem(
                    # next_expected is ISO (YYYY-MM-DD) — sorts chronologically as text
                    row,
                    _COL_NEXT_DUE,
                    QTableWidgetItem(item.next_expected.isoformat()),
                )
                table.setItem(
                    row,
                    _COL_SEEN,
                    SortableItem(str(item.occurrences), item.occurrences),
                )
                tag_row(table, row, row)  # col-0 tag = insertion index (sort-safe)

    def _direction_label(self, item: RecurringItem) -> str:
        """The ``tr()``-ed display label for an item's direction token (INV-11)."""
        return {
            Direction.IN: self.tr("In"),
            Direction.OUT: self.tr("Out"),
        }[item.direction]

    def _cadence_label(self, item: RecurringItem) -> str:
        """The ``tr()``-ed display label for an item's cadence token (INV-11)."""
        return {
            Cadence.WEEKLY: self.tr("Weekly"),
            Cadence.FORTNIGHTLY: self.tr("Fortnightly"),
            Cadence.MONTHLY: self.tr("Monthly"),
            Cadence.YEARLY: self.tr("Yearly"),
        }[item.cadence]

    @Slot()
    def _on_selection_changed(self) -> None:
        has_suggested = self._selected_row(self._suggested) is not None
        self._confirm_button.setEnabled(has_suggested)
        self._dismiss_button.setEnabled(has_suggested)
        self._unconfirm_button.setEnabled(
            self._selected_row(self._confirmed_table) is not None
        )

    @Slot()
    def _on_confirm(self) -> None:
        index = self._selected_row(self._suggested)
        if index is None:
            return
        item = self._suggested_items[index]
        try:
            self._recurring.confirm(item.direction, item.merchant_key)
        except VaultLockedError:
            return  # auto-lock fired mid-click; the workspace is being torn down
        self.refresh()  # refresh first — it owns the status line's empty-state text
        self._status.setText(self.tr("Confirmed."))

    @Slot()
    def _on_dismiss(self) -> None:
        index = self._selected_row(self._suggested)
        if index is None:
            return
        item = self._suggested_items[index]
        try:
            self._recurring.dismiss(item.direction, item.merchant_key)
        except VaultLockedError:
            return
        self.refresh()
        self._status.setText(self.tr("Dismissed."))

    @Slot()
    def _on_unconfirm(self) -> None:
        index = self._selected_row(self._confirmed_table)
        if index is None:
            return
        item = self._confirmed_items[index]
        try:
            self._recurring.reset(item.direction, item.merchant_key)
        except VaultLockedError:
            return
        self.refresh()
        self._status.setText(self.tr("Un-confirmed."))

    def _selected_row(self, table: QTableWidget) -> int | None:
        # The tagged parallel-list index of the selection — correct after a re-sort
        # (the visual row order can differ from _suggested/_confirmed order).
        return selected_index(table)
