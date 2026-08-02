"""FIBR-0117 — table sorting + remembered column widths.

Enforces tests/features/table_state/spec.md. The reusable `ui/_table_state.py`
(SortableItem / enable_sorting / fill_guard / tag_row / selected_index /
remember_columns) plus the correctness guard that a table action targets the
*sorted* row, not insertion order. Every on-disk vault uses `tmp_path`; the
column-state INI is redirected to tmp by the autouse `window_ini` fixture.
"""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from PySide6.QtCore import QPoint, QSettings, QSize, Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QTreeWidget

from conftest import _PW
from finbreak import paths as fb_paths
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
    assert first._suggested.item(0, 1).text() == "R 500.00"

    rebuilt = TransfersWidget(service)  # fresh session
    qtbot.addWidget(rebuilt)
    header = rebuilt._suggested.horizontalHeader()
    assert header.sortIndicatorSection() == 1
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    # ...and the rows are actually re-sorted, not just the arrow restored.
    assert rebuilt._suggested.item(0, 1).text() == "R 500.00"


# --------------------------------------------------------------------------- #
# 4c — columns are drag-reorderable AND the new order persists (FIBR-0012 request)
# --------------------------------------------------------------------------- #
def test_columns_are_movable_and_order_persists_across_rebuild(qtbot, service):
    """remember_columns makes header sections movable, and the moved visual order
    round-trips through a rebuild via the same saveState it restores. Verified on
    the Transactions table (the four data tables share the one helper)."""
    from finbreak.services.categorization import CategorizationService
    from finbreak.services.transactions import TransactionService
    from finbreak.ui.transactions import TransactionsView

    first = TransactionsView(
        TransactionService(service.vault), CategorizationService(service.vault)
    )
    qtbot.addWidget(first)
    header = first._table.horizontalHeader()
    assert header.sectionsMovable(), "columns can be dragged to reorder"
    # Move logical column 0 (Date) to visual position 2 — the user reorders.
    header.moveSection(0, 2)
    assert header.visualIndex(0) == 2

    rebuilt = TransactionsView(  # a fresh session / tab rebuild
        TransactionService(service.vault), CategorizationService(service.vault)
    )
    qtbot.addWidget(rebuilt)
    assert rebuilt._table.horizontalHeader().visualIndex(0) == 2, (
        "the reordered column layout is restored"
    )


def test_transactions_and_statements_tables_have_distinct_column_keys(qtbot, service):
    """Both tables are 5-column; without distinct objectNames they'd share the empty
    "columns/" key and cross-corrupt each other's widths + drag order (FIBR-0012
    indie-review). Reordering one must NOT move the other's columns."""
    from finbreak.services.categorization import CategorizationService
    from finbreak.services.transactions import TransactionService
    from finbreak.ui.statements import StatementsWidget
    from finbreak.ui.transactions import TransactionsView

    txns = TransactionsView(
        TransactionService(service.vault), CategorizationService(service.vault)
    )
    qtbot.addWidget(txns)
    assert txns._table.objectName() == "transactions_table"
    txns._table.horizontalHeader().moveSection(0, 3)  # reorder the Transactions table

    stmts = StatementsWidget(service)
    qtbot.addWidget(stmts)
    assert stmts._table.objectName() == "statements_table"
    # The Statements table keeps its natural order — it did not inherit the move.
    assert stmts._table.horizontalHeader().visualIndex(0) == 0


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


# --------------------------------------------------------------------------- #
# FIBR-0187 — the import preview table remembers its columns too
# --------------------------------------------------------------------------- #
def test_FIBR0187_import_preview_columns_remembered_across_rebuild(qtbot, service):
    """The preview table was the one table built without remember_columns, so a
    column widened while checking an import snapped back on the next import."""
    from finbreak.ui.import_wizard import ImportWizardWidget

    first = ImportWizardWidget(service)
    qtbot.addWidget(first)
    assert first._preview_table.objectName(), (
        "the preview table needs an objectName — remember_columns keys the saved "
        "state on it, so a blank name would collide with every other unnamed table"
    )
    first._preview_table.setColumnWidth(3, 311)  # user widens Description

    rebuilt = ImportWizardWidget(service)  # the next import
    qtbot.addWidget(rebuilt)
    assert rebuilt._preview_table.columnWidth(3) == 311


def test_FIBR0187_import_preview_column_key_is_distinct(qtbot, service):
    """Both the preview and the Statements table are 5-column; sharing a key would
    cross-corrupt their widths and drag order (the FIBR-0012 failure mode)."""
    from finbreak.ui.import_wizard import ImportWizardWidget
    from finbreak.ui.statements import StatementsWidget

    wizard = ImportWizardWidget(service)
    qtbot.addWidget(wizard)
    assert wizard._preview_table.objectName() == "import_preview_table"
    wizard._preview_table.horizontalHeader().moveSection(0, 3)

    stmts = StatementsWidget(service)
    qtbot.addWidget(stmts)
    assert stmts._table.horizontalHeader().visualIndex(0) == 0  # unmoved


# --------------------------------------------------------------------------- #
# FIBR-0113 — the Accounts table joins the shared column scheme
# --------------------------------------------------------------------------- #
def test_INV8_accounts_table_column_key_is_distinct(qtbot, service):
    """The Accounts table's objectName is `accounts_table`, distinct from every
    other table passed to remember_columns (FIBR-0113 INV-8). Left unset, its
    saved header state lands under the shared empty "columns/" key and
    cross-corrupts another unnamed table's layout — the FIBR-0012 defect."""
    from finbreak.ui.accounts import AccountsWidget
    from finbreak.ui.statements import StatementsWidget

    accounts = AccountsWidget(service)
    qtbot.addWidget(accounts)
    assert accounts._table.objectName() == "accounts_table"
    accounts._table.horizontalHeader().moveSection(0, 3)  # reorder Accounts

    stmts = StatementsWidget(service)
    qtbot.addWidget(stmts)
    assert stmts._table.objectName() == "statements_table"
    # The Statements table keeps its natural order — it did not inherit the move.
    assert stmts._table.horizontalHeader().visualIndex(0) == 0


def test_INV17_accounts_columns_are_movable_and_persist_across_rebuild(qtbot, service):
    """The Accounts columns are user-reorderable and resizable, and both survive
    a rebuild (FIBR-0113 INV-17). INV-8 does not catch a table nobody
    registered: the objectName can be right on a table remember_columns was
    never called on."""
    from finbreak.ui.accounts import AccountsWidget

    first = AccountsWidget(service)
    qtbot.addWidget(first)
    header = first._table.horizontalHeader()
    assert header.sectionsMovable(), "columns can be dragged to reorder"
    header.moveSection(0, 2)  # Name to visual position 2
    first._table.setColumnWidth(1, 213)  # the user drags the Type column

    rebuilt = AccountsWidget(service)  # a fresh session / tab rebuild
    qtbot.addWidget(rebuilt)
    assert rebuilt._table.horizontalHeader().visualIndex(0) == 2, (
        "the reordered column layout is restored"
    )
    assert rebuilt._table.columnWidth(1) == 213, "and the width with it"


# --------------------------------------------------------------------------- #
# FIBR-0192 — Reset layout also resets columns, and the two remaining surfaces
# (the Forecast events table, the three Home breakdown trees) join the scheme.
#
# Legs are named test_FIBR0192_INV<n>_… : this file already holds bare
# `test_INV8_…` / `test_INV17_…` names belonging to FIBR-0113, so an unqualified
# name here would be ambiguous across three specs that all touch this one INI.
# --------------------------------------------------------------------------- #
def _txn_view(service: AuthService):
    """A standalone TransactionsView over the same vault — the rebuild shape the
    existing legs use, reading the same `columns/transactions_table` key."""
    from finbreak.services.categorization import CategorizationService
    from finbreak.services.transactions import TransactionService
    from finbreak.ui.transactions import TransactionsView

    return TransactionsView(
        TransactionService(service.vault), CategorizationService(service.vault)
    )


def _home_view(service: AuthService):
    """The five-service HomeView construction, following tests/features/dashboard/."""
    from finbreak.services.alerts import AlertService
    from finbreak.services.recurring import RecurringService
    from finbreak.services.reporting import ReportingService
    from finbreak.ui.home import HomeView

    return HomeView(
        ReportingService(service.vault),
        AccountService(service.vault),
        service,
        recurring=RecurringService(service.vault),
        alerts=AlertService(service.vault),
    )


def _unlocked_shell(qtbot, service: AuthService):
    """A MainWindow driven past routing to a live workspace, as app_shell does."""
    from finbreak.ui.main_window import MainWindow

    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    return window


def _window_ini() -> QSettings:
    return QSettings(str(fb_paths.window_settings_path()), QSettings.Format.IniFormat)


def _sort_keys(table: QTableWidget, col: int) -> list[object]:
    """Each row's sort key in `col` — every Transactions cell is a SortableItem, so
    this is the value Qt actually ordered by (falls back to display text)."""
    out: list[object] = []
    for row in range(table.rowCount()):
        item = table.item(row, col)
        assert item is not None
        key = item.data(Qt.ItemDataRole.UserRole + 1)
        out.append(item.text() if key is None else key)
    return out


# --------------------------------------------------------------------------- #
# INV-1 — the Forecast events table is drag-reorderable and remembers its columns
# --------------------------------------------------------------------------- #
def test_FIBR0192_INV1_forecast_columns_movable_and_remembered(qtbot, service):
    """The Forecast table was built without remember_columns, so its columns were
    neither draggable nor remembered. A fresh QTableWidget header is NOT movable
    (QT-1), so the first clause discriminates a missing call."""
    from finbreak.ui.forecast import ForecastWidget

    first = ForecastWidget(service)
    qtbot.addWidget(first)
    assert first._events_table.objectName() == "forecast_events"
    header = first._events_table.horizontalHeader()
    assert header.sectionsMovable(), "columns can be dragged to reorder"

    first._events_table.setColumnWidth(1, 233)  # user widens Merchant

    rebuilt = ForecastWidget(service)  # a fresh session / tab rebuild
    qtbot.addWidget(rebuilt)
    assert rebuilt._events_table.columnWidth(1) == 233


# --------------------------------------------------------------------------- #
# INV-2 — the Forecast table is NOT click-sortable; its rows stay in date order
# --------------------------------------------------------------------------- #
def test_FIBR0192_INV2_forecast_is_not_click_sortable(qtbot, service):
    """A lock, not a driver: §3 decision 1 deliberately left sorting OFF here
    because `_fill_events` has no fill_guard and pairs each row's running balance
    with its own date — a re-sort would pair a balance with another event's date.

    The seed makes the clause non-vacuous: two confirmed items whose merchant
    order (Acme, Zebra) differs from their date order (Zebra, Acme), so a click
    that DID sort would visibly reorder the Date column.
    """
    from finbreak.models import Direction
    from finbreak.services.recurring import RecurringService
    from finbreak.ui.forecast import ForecastWidget

    account = AccountRepository(service.vault.connection).list_all()[0].id
    today = date.today()
    for k in range(3):  # Zebra's series runs 5 days ahead, so Zebra is due first
        TransactionRepository(service.vault.connection).add(
            account, (today - timedelta(days=30 * k + 5)).isoformat(), -19900, "Zebra"
        )
        TransactionRepository(service.vault.connection).add(
            account, (today - timedelta(days=30 * k)).isoformat(), -29900, "Acme"
        )
    rec = RecurringService(service.vault)
    rec.confirm(Direction.OUT, "zebra")
    rec.confirm(Direction.OUT, "acme")

    widget = ForecastWidget(service)
    qtbot.addWidget(widget)
    widget._horizon.setCurrentIndex(3)  # 90 days — both events inside the horizon
    widget.show()
    qtbot.waitExposed(widget)

    assert widget._events_table.isSortingEnabled() is False
    dates_before = [
        widget._events_table.item(r, 0).text()
        for r in range(widget._events_table.rowCount())
    ]
    assert len(set(dates_before)) >= 2, "the seed must give ≥2 distinct event dates"
    merchants = [
        widget._events_table.item(r, 1).text()
        for r in range(widget._events_table.rowCount())
    ]
    assert merchants != sorted(merchants), (
        "merchant order must differ from date order, or a sort would be invisible"
    )

    # The click must be shown to have landed: an unshown or zero-width header
    # section swallows it, and the leg would pass against a build that DID sort.
    header = widget._events_table.horizontalHeader()
    assert header.sectionSize(1) > 0 and header.isVisible()
    qtbot.mouseClick(
        header.viewport(),
        Qt.MouseButton.LeftButton,
        pos=QPoint(
            header.sectionPosition(1) + header.sectionSize(1) // 2,
            header.height() // 2,
        ),
    )

    assert widget._events_table.isSortingEnabled() is False
    dates_after = [
        widget._events_table.item(r, 0).text()
        for r in range(widget._events_table.rowCount())
    ]
    assert dates_after == dates_before, "a header click must not reorder the rows"


# --------------------------------------------------------------------------- #
# INV-3 — the three Home breakdown trees each remember their own columns
# --------------------------------------------------------------------------- #
def test_FIBR0192_INV3_home_breakdown_trees_remember_distinct_columns(qtbot, service):
    """Deliberately does NOT assert sectionsMovable(): a QTreeWidget header is
    movable by default (QT-2), so that clause would pass with no call at all."""
    widths = {"expenditure": 171, "income": 182, "transfers": 193}

    first = _home_view(service)
    qtbot.addWidget(first)
    for key, width in widths.items():
        tree = first.findChild(QTreeWidget, f"dashboard_breakdown_{key}")
        assert tree is not None, f"the {key} breakdown tree exists"
        tree.setColumnWidth(0, width)

    rebuilt = _home_view(service)  # a fresh session
    qtbot.addWidget(rebuilt)
    for key, width in widths.items():
        tree = rebuilt.findChild(QTreeWidget, f"dashboard_breakdown_{key}")
        assert tree is not None
        assert tree.columnWidth(0) == width, f"{key} restored its own width"

    # ...under three separate keys — sharing one is the FIBR-0012 cross-corruption.
    saved = _window_ini()
    for key in widths:
        assert saved.value(f"columns/dashboard_breakdown_{key}") is not None


# --------------------------------------------------------------------------- #
# INV-5 — Reset layout returns LIVE headers to their build-time defaults
# --------------------------------------------------------------------------- #
def test_FIBR0192_INV5_reset_layout_restores_live_headers(qtbot, service):
    """Column 0 (Date), not the stretched last column: transactions_table sets
    setStretchLastSection(True), so the last section's width is decided by the
    layout pass and differs between the unshown and shown widget."""
    window = _unlocked_shell(qtbot, service)
    table = window.findChild(QTableWidget, "transactions_table")
    assert table is not None
    header = table.horizontalHeader()
    default_width = header.sectionSize(0)
    forecast = window.findChild(QTableWidget, "forecast_events")
    assert forecast is not None
    forecast_default = forecast.horizontalHeader().sectionSize(0)

    table.setColumnWidth(0, default_width + 87)  # the user widens Date...
    header.moveSection(0, 2)  # ...and drags it to visual position 2
    forecast.setColumnWidth(0, forecast_default + 61)
    assert header.visualIndex(0) == 2

    window._reset_layout()

    # clause 1 — width AND visual position back, with no rebuild or restart.
    assert header.sectionSize(0) == default_width
    assert header.visualIndex(0) == 0
    # clause 2 — still drag-reorderable (breaks if the capture predates
    # setSectionsMovable(True): the "default" would then carry movable=False).
    assert header.sectionsMovable()
    # clause 4 — the surface this item ADDS was reached too.
    assert forecast.horizontalHeader().sectionSize(0) == forecast_default

    # clause 3 — persistence still works after the reset (breaks if the restore
    # left the header's signals blocked).
    table.setColumnWidth(1, 176)
    rebuilt = _txn_view(service)
    qtbot.addWidget(rebuilt)
    assert rebuilt._table.columnWidth(1) == 176


# --------------------------------------------------------------------------- #
# INV-6 — a reset survives a rebuild (the clear-LAST discriminator)
# --------------------------------------------------------------------------- #
def test_FIBR0192_INV6_reset_layout_survives_a_rebuild(qtbot, service):
    """All four preconditions, or this passes against the broken ordering:
    (a) transactions_table — the one remembered QTableWidget with
    stretchLastSection, so a window resize re-lays-out its sections at all (QT-7);
    (b) a differing, persisted width for the reset to have to erase;
    (c) a starting window size ≠ _DEFAULT_WINDOW_SIZE, or the reset's resize is a
    no-op that provokes no layout pass — and a fresh MainWindow against an empty
    INI is already at the default size;
    (d) the Transactions tab must be the CURRENT one. A QTabWidget gives no layout
    pass to a page that isn't showing, so on any other tab the resize emits no
    `sectionResized` at all and the leg goes vacuous — measured during the build,
    where it passed against the clear-first ordering until the tab was switched.

    The `fired` counter is the guard: it proves the write that must not survive
    actually happened, so this can never silently become a test that cannot fail.
    """
    from finbreak.ui.main_window import _DEFAULT_WINDOW_SIZE, _TAB_TRANSACTIONS

    window = _unlocked_shell(qtbot, service)
    assert window._workspace is not None
    window._workspace.setCurrentIndex(_TAB_TRANSACTIONS)  # (d)
    table = window.findChild(QTableWidget, "transactions_table")
    assert table is not None
    header = table.horizontalHeader()
    default_width = header.sectionSize(0)

    window.resize(_DEFAULT_WINDOW_SIZE + QSize(140, 110))  # (c)
    window.show()
    qtbot.waitExposed(window)
    # (b) is "a DIFFERING, persisted width". Asserting the key merely exists is
    # too weak twice over: it passes against a key holding the build-time
    # default, and — measured — it also passes with the widening removed
    # entirely, because the `window.resize` above already provokes a save. So
    # snapshot the stored bytes either side of the widening and require THAT to
    # be what moved them.
    stored_before = _window_ini().value("columns/transactions_table")
    table.setColumnWidth(0, default_width + 93)  # (b)
    stored_after = _window_ini().value("columns/transactions_table")
    assert stored_after is not None, "the widened column must have been persisted"
    assert stored_before is None or bytes(stored_after) != bytes(stored_before), (
        "the widening itself must be what changed the persisted state, or the "
        "reset has nothing of the user's to undo and this leg cannot fail"
    )

    fired: list[object] = []
    header.sectionResized.connect(lambda *a: fired.append(a))

    window._reset_layout()

    assert fired, (
        "the reset's resize must re-lay-out the sections — without that emission "
        "there is no pre-reset write for the clear to have to erase, and this leg "
        "would pass under either ordering"
    )

    # NOTE — what this leg actually covers, measured by mutation during the build
    # and NARROWER than FIBR-0192 §5 INV-6 claims. `reset_columns(self)` and
    # `settings.remove("columns")` are redundant in-process: each alone keeps the
    # rebuild on the default, so dropping either one leaves this green and only
    # dropping BOTH turns it red. It therefore does not discriminate clear-first
    # from clear-last either — under that ordering the INI still ends up holding
    # the default. Clear-last is kept because it is correct without depending on
    # which Qt emission timing occurs, not because a test enforces it.
    rebuilt = _txn_view(service)
    qtbot.addWidget(rebuilt)
    assert rebuilt._table.columnWidth(0) == default_width, (
        "the pre-reset layout must not be left behind for the next construction"
    )


# --------------------------------------------------------------------------- #
# INV-7 — Reset layout is safe with no workspace (the Window menu stays enabled)
# --------------------------------------------------------------------------- #
def test_FIBR0192_INV7_reset_layout_before_unlock_does_not_raise(qtbot, service):
    """reset_columns is passed the WINDOW, not self._workspace, which is None
    until a vault is open — the Window menu holding this action needs no vault."""
    from finbreak.ui.main_window import MainWindow

    service.lock()
    window = MainWindow(service)
    qtbot.addWidget(window)
    assert window._workspace is None

    window._reset_layout()  # must not raise


# --------------------------------------------------------------------------- #
# INV-8 — a reset restores the BUILD-TIME default, not the user's saved layout
# --------------------------------------------------------------------------- #
def test_FIBR0192_INV8_reset_restores_build_time_default_not_saved_state(
    qtbot, service
):
    """Every other leg here passes on a first run against an empty INI. A
    returning user is the normal case, and this is the only fixture that
    discriminates a capture taken AFTER the restore."""
    account = AccountRepository(service.vault.connection).list_all()[0].id
    # Descriptions chosen so Description-ascending differs from Date-descending —
    # clause 2 needs the user's sort and the build-time one to order rows apart.
    for day, amount, desc in (
        ("2026-03-09", -1500, "c"),
        ("2026-01-04", -9900, "b"),
        ("2026-02-17", 500, "a"),
    ):
        TransactionRepository(service.vault.connection).add(account, day, amount, desc)

    # Seed a NON-DEFAULT saved layout before the window is built, so construction
    # restores it — recording the build-time default from the same code path.
    probe = _txn_view(service)
    qtbot.addWidget(probe)
    default_width = probe._table.horizontalHeader().sectionSize(0)
    probe._table.setColumnWidth(0, default_width + 111)

    window = _unlocked_shell(qtbot, service)
    table = window.findChild(QTableWidget, "transactions_table")
    assert table is not None
    assert table.horizontalHeader().sectionSize(0) == default_width + 111, (
        "the seeded layout must actually have been restored at construction"
    )

    header = table.horizontalHeader()
    table.sortItems(3, Qt.SortOrder.AscendingOrder)  # Description — a user sort
    assert table.rowCount() >= 3
    before = (header.sortIndicatorSection(), header.sortIndicatorOrder())

    window._reset_layout()

    # clause 1 — the BUILD-TIME default, not the seeded layout.
    assert header.sectionSize(0) == default_width

    # clause 2 — the rows agree with the indicator the reset restored. Read the
    # expectation off the header rather than hard-coding it: what enable_sorting
    # leaves set is not this spec's to fix, and the desynchronisation is what
    # this catches (blocking sortIndicatorChanged flips the arrow, not the rows).
    after = (header.sortIndicatorSection(), header.sortIndicatorOrder())
    assert after != before, (
        "the restored default sort must differ from the user's, or a blocked "
        "restore would leave the rows correct by coincidence and this cannot fail"
    )
    keys = _sort_keys(table, after[0])
    expected = sorted(keys, reverse=after[1] == Qt.SortOrder.DescendingOrder)
    assert keys == expected, "the restored sort arrow must match the row order"
