"""FIBR-0117 — table sorting + remembered column widths.

Enforces tests/features/table_state/spec.md. The reusable `ui/_table_state.py`
(SortableItem / enable_sorting / fill_guard / tag_row / selected_index /
remember_columns) plus the correctness guard that a table action targets the
*sorted* row, not insertion order. Every on-disk vault uses `tmp_path`; the
column-state INI is redirected to tmp by the autouse `window_ini` fixture.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from conftest import _PW
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.ui._table_state import (
    SortableItem,
    selected_index,
    tag_row,
)

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# 1 — SortableItem sorts by key, not display text
# --------------------------------------------------------------------------- #
def test_sortable_item_orders_numerically():
    small = SortableItem("69", 69)
    big = SortableItem("112", 112)
    assert small < big  # 69 < 112 numerically (lexically "112" < "69" would be wrong)
    assert not (big < small)


# --------------------------------------------------------------------------- #
# 2 — the row tag survives a reorder; selected_index reads it back
# --------------------------------------------------------------------------- #
def test_selected_index_reads_the_tag(qtbot):
    table = QTableWidget(2, 1)
    table.setItem(0, 0, QTableWidgetItem("A"))
    table.setItem(1, 0, QTableWidgetItem("B"))
    tag_row(table, 0, 10)  # row A -> parallel-list index 10
    tag_row(table, 1, 3)  # row B -> parallel-list index 3
    table.selectRow(0)
    assert selected_index(table) == 10
    table.selectRow(1)
    assert selected_index(table) == 3


# --------------------------------------------------------------------------- #
# helpers for the widget-level cases
# --------------------------------------------------------------------------- #
def _two_accounts(service: AuthService) -> tuple[int, int]:
    first = AccountRepository(service.vault.connection).list_all()[0].id
    second = AccountService(service.vault).add_account("Savings", "savings").id
    return first, second


def _add(service: AuthService, account_id: int, amount: int) -> int:
    return TransactionRepository(service.vault.connection).add(
        account_id, "2026-01-05", amount, "move"
    )


# --------------------------------------------------------------------------- #
# 3 — a table action targets the SORTED row (the money-correctness guard)
# --------------------------------------------------------------------------- #
def test_transfers_confirm_targets_sorted_row_not_insertion_order(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    a, b = _two_accounts(service)
    _add(service, a, -10000)  # pair X = 100.00 (inserted first -> lower ids)
    _add(service, b, 10000)
    _add(service, a, -50000)  # pair Y = 500.00
    _add(service, b, 50000)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    assert len(widget._candidates) == 2

    # Sort Amount DESCENDING: the top visual row is now the 500.00 pair, which is
    # NOT the insertion-order first row (X). Confirming it must confirm Y.
    widget._suggested.sortItems(1, Qt.SortOrder.DescendingOrder)
    widget._suggested.selectRow(0)
    widget._confirm_button.click()
    (confirmed,) = widget._confirmed
    assert str(confirmed.display_amount) == "500.00"


# --------------------------------------------------------------------------- #
# 4 — column widths are remembered across a rebuild
# --------------------------------------------------------------------------- #
def test_column_widths_remembered_across_rebuild(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    first = TransfersWidget(service)
    qtbot.addWidget(first)
    first._suggested.setColumnWidth(0, 217)  # user drags the Date column

    rebuilt = TransfersWidget(service)  # a fresh session / tab rebuild
    qtbot.addWidget(rebuilt)
    assert rebuilt._suggested.columnWidth(0) == 217


# --------------------------------------------------------------------------- #
# 4b — the chosen SORT (column + direction) persists across a rebuild
# --------------------------------------------------------------------------- #
def test_sort_order_persists_across_rebuild(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    a, b = _two_accounts(service)
    _add(service, a, -10000)  # 100.00
    _add(service, b, 10000)
    _add(service, a, -50000)  # 500.00
    _add(service, b, 50000)
    first = TransfersWidget(service)
    qtbot.addWidget(first)
    first._suggested.sortItems(1, Qt.SortOrder.DescendingOrder)  # Amount, descending
    assert first._suggested.item(0, 1).text() == "500.00"

    rebuilt = TransfersWidget(service)  # fresh session
    qtbot.addWidget(rebuilt)
    header = rebuilt._suggested.horizontalHeader()
    assert header.sortIndicatorSection() == 1
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    # ...and the rows are actually re-sorted, not just the arrow restored.
    assert rebuilt._suggested.item(0, 1).text() == "500.00"


# --------------------------------------------------------------------------- #
# 5 — the priority-ordered Rules table is NOT click-sortable (but persists widths)
# --------------------------------------------------------------------------- #
def test_rules_table_is_not_sortable_but_persists_widths(qtbot, service):
    from finbreak.ui.rules import RulesWidget

    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    assert widget._table.isSortingEnabled() is False  # order = priority
    # width persistence still wired: a resize round-trips through a rebuild.
    widget._table.setColumnWidth(0, 199)
    rebuilt = RulesWidget(service)
    qtbot.addWidget(rebuilt)
    assert rebuilt._table.columnWidth(0) == 199
