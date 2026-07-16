"""FIBR-0143 — the dashboard-focus rework (breakdown is the hero).

Two layers, per the spec's test plan:

* the new **`build_breakdown_donut`** builder (`ui/charts.py`) — a column's ≤8-wedge
  pie from generic ``(label, amount)`` slices, its own cap-and-collapse loop, palette
  colours, empty-safe (INV-4/INV-8);
* the reworked **`HomeView`** three-column dashboard (`ui/home.py`) — per-column pie +
  header + breakdown tree, a Net strip, a recurring-money card, the trend strip demoted
  to the bottom (INV-1..INV-9), driven headless + qtbot over a seeded vault.

Every displayed figure still comes from the existing money aggregations (no new service
code); the column totals equal the FIBR-0138 drill nodes, which equal the FIBR-0012
``Summary`` (INV-1). The spending donut / PDF path is untouched (regression, D10).
"""

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCharts import QChart, QPieSeries
from PySide6.QtGui import QColor

from finbreak.ui.charts import ChartTheme

pytestmark = pytest.mark.features

_THEME = ChartTheme(
    text=QColor("#ffffff"),
    positive=QColor("#4E9F3D"),
    negative=QColor("#C0504D"),
    background=None,
)


# --------------------------------------------------------------------------- #
# build_breakdown_donut — the column pie builder (D3, INV-4/INV-8)
# --------------------------------------------------------------------------- #
def _slices(n):
    """``n`` generic slices, descending magnitude (the service pre-sorts)."""
    return [(f"c{i}", Decimal(1000 - i)) for i in range(1, n + 1)]


def test_breakdown_donut_all_shown_when_within_cap(qapp):
    """≤ 8 slices → every slice a wedge, no synthetic Other (D3)."""
    from finbreak.ui.charts import build_breakdown_donut

    chart = build_breakdown_donut(_slices(8), "Other", _THEME)
    assert isinstance(chart, QChart)
    (series,) = chart.series()
    assert isinstance(series, QPieSeries)
    labels = [s.label() for s in series.slices()]
    assert labels == [f"c{i}" for i in range(1, 9)]  # all 8, no Other
    assert "Other" not in labels


def test_breakdown_donut_collapses_tail_into_other_over_cap(qapp):
    """> 8 slices → top 7 kept + one Other wedge summing the tail (D3)."""
    from finbreak.ui.charts import build_breakdown_donut

    slices = _slices(10)  # 10 > 8
    chart = build_breakdown_donut(slices, "Other", _THEME)
    (series,) = chart.series()
    wedges = series.slices()
    assert len(wedges) == 8  # 7 kept + Other
    labels = [w.label() for w in wedges]
    assert labels[:7] == [f"c{i}" for i in range(1, 8)]  # kept order preserved
    assert labels[7] == "Other"
    tail_sum = sum((amt for _, amt in slices[7:]), Decimal(0))
    assert wedges[7].value() == pytest.approx(float(tail_sum))


def test_breakdown_donut_kept_wedges_take_palette_no_neutral_grey(qapp):
    """Every kept wedge (incl. what would be Uncategorised) takes a palette colour —
    ``build_breakdown_donut`` has no reserved neutral-grey slot (D3)."""
    from finbreak.ui.charts import _DONUT_PALETTE, _OTHER_COLOUR, build_breakdown_donut

    chart = build_breakdown_donut(_slices(10), "Other", _THEME)
    (series,) = chart.series()
    wedges = series.slices()
    assert [w.color() for w in wedges[:7]] == _DONUT_PALETTE[:7]  # palette, in order
    assert wedges[7].color() == _OTHER_COLOUR  # the tail wedge is the Other neutral


def test_breakdown_donut_is_a_donut_with_hole(qapp):
    """The column pie is the same donut shape the dashboard already shows (D3)."""
    from finbreak.ui.charts import build_breakdown_donut

    chart = build_breakdown_donut(_slices(3), "Other", _THEME)
    (series,) = chart.series()
    assert series.holeSize() == pytest.approx(0.4)
    assert chart.legend().labelColor() == _THEME.text  # themed, not ambient palette


def test_breakdown_donut_empty_is_no_wedges_never_raises(qapp):
    """An empty branch → a chart with no data slices, no exception (INV-4)."""
    from finbreak.ui.charts import build_breakdown_donut

    chart = build_breakdown_donut([], "Other", _THEME)
    (series,) = chart.series()
    assert series.slices() == []


def test_breakdown_donut_does_not_touch_the_spending_donut(qapp):
    """Regression (D10): the PDF/spending donut builder is byte-for-byte unchanged —
    its Uncategorised-by-id neutral-grey wedge still resolves from the same module."""
    from finbreak.models import CategorySpend
    from finbreak.ui.charts import _UNCAT_COLOUR, _donut_wedges

    spending = [
        CategorySpend(category_id=1, name="c1", amount=Decimal(100)),
        CategorySpend(category_id=None, name="", amount=Decimal(50)),  # Uncategorised
    ]
    wedges = _donut_wedges(spending, "Uncategorised", "Other")
    assert wedges[1] == (
        "Uncategorised",
        Decimal(50),
        _UNCAT_COLOUR,
    )  # neutral-grey kept


# --------------------------------------------------------------------------- #
# HomeView — the three-column dashboard (qtbot). Seeding mirrors the FIBR-0138
# drilldown fixtures; the recurring card is seeded relative to real ``date.today()``
# because the widget calls ``summary(date.today())`` (unscoped, INV-3/D5).
# --------------------------------------------------------------------------- #
from datetime import timedelta  # noqa: E402

from conftest import _PW  # noqa: E402
from finbreak.models import Direction, DrillLabels  # noqa: E402
from finbreak.repositories.accounts import AccountRepository  # noqa: E402
from finbreak.repositories.categories import CategoryRepository  # noqa: E402
from finbreak.repositories.transactions import TransactionRepository  # noqa: E402
from finbreak.services.accounts import AccountService  # noqa: E402
from finbreak.services.auth import AuthService  # noqa: E402
from finbreak.services.categories import CategoryService  # noqa: E402
from finbreak.services.categorization import CategorizationService  # noqa: E402
from finbreak.services.recurring import RecurringService  # noqa: E402
from finbreak.services.reporting import (  # noqa: E402
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    ReportingService,
    ReportPrefs,
)
from finbreak.services.transfer_detection import TransferDetectionService  # noqa: E402
from finbreak.ui._amount import (  # noqa: E402
    _NEGATIVE_TEXT,
    _POSITIVE_TEXT,
    _format_amount,
)

_JAN = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=1)


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _two_accounts(service):
    accounts = AccountService(service.vault)
    first = AccountRepository(service.vault.connection).list_all()[0].id
    second = accounts.add_account("Savings", "savings").id
    return first, second


def _add(service, account_id, amount_minor, occurred_on="2026-01-05", description="x"):
    return TransactionRepository(service.vault.connection).add(
        account_id, occurred_on, amount_minor, description
    )


def _root(service, kind):
    roots = CategoryRepository(service.vault.connection).children_of(None)
    return next(r for r in roots if r.kind == kind)


def _expenditure_leaf(service, name="Ztest Groceries"):
    return (
        CategoryService(service.vault)
        .add_category(_root(service, "expenditure").id, name)
        .id
    )


def _set_cat(service, txn_id, category_id):
    CategorizationService(service.vault).set_manual_category(txn_id, category_id)


def _confirm_recurring(service, account_id, amount_minor, desc):
    """Seed 4 monthly occurrences ending at real today (30-day gaps → the monthly
    band, active as of today) and confirm the detected merchant. Returns the key."""
    today = date.today()
    for k in range(4):
        _add(
            service,
            account_id,
            amount_minor,
            (today - timedelta(days=30 * k)).isoformat(),
            desc,
        )
    rec = RecurringService(service.vault)
    # Confirm the candidate whose direction matches the seeded sign (so the net-zero
    # test can confirm an OUT then an IN of the same merchant without ambiguity).
    want = Direction.OUT if amount_minor < 0 else Direction.IN
    item = next(c for c in rec.candidates(today) if c.direction is want)
    rec.confirm(item.direction, item.merchant_key)
    return rec


def _home(service, amount_prefs=None):
    from finbreak.ui.home import HomeView

    return HomeView(
        ReportingService(service.vault),
        AccountService(service.vault),
        service,
        recurring=RecurringService(service.vault),
        amount_prefs=amount_prefs,
    )


def _seed_full(service):
    """Income + categorised & uncategorised spend + a confirmed transfer, in Jan."""
    a, b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03", "SALARY")  # income 3000
    groceries = _expenditure_leaf(service)
    _set_cat(
        service, _add(service, a, -40000, "2026-01-04", "POS WOOLWORTHS"), groceries
    )
    _add(service, a, -15000, "2026-01-06", "CORNER SHOP")  # uncategorised expense
    debit = _add(service, a, -100000, "2026-01-10", "to savings")
    credit = _add(service, b, 100000, "2026-01-10", "from current")
    TransferDetectionService(service.vault).confirm(debit, credit)
    service.set_report_prefs(_JAN)
    return a, b


def _labels():
    return DrillLabels(
        income="Income",
        spending="Spending",
        transfers="Transfers",
        uncategorised="Uncategorised",
    )


# --- INV-9: structure -------------------------------------------------------- #
def test_INV9_refresh_builds_three_columns_net_recurring_trend(qtbot, service):
    from PySide6.QtCharts import QChartView
    from PySide6.QtWidgets import QLabel, QTreeWidget, QWidget

    _seed_full(service)
    home = _home(service)
    qtbot.addWidget(home)
    assert home.current_page().objectName() == "home_page_dashboard"
    for col in ("expenditure", "income", "transfers"):
        assert home.findChild(QWidget, f"dashboard_col_{col}") is not None
        assert home.findChild(QChartView, f"dashboard_pie_{col}") is not None
        assert home.findChild(QLabel, f"dashboard_heading_{col}") is not None
        assert home.findChild(QLabel, f"dashboard_total_{col}") is not None
        assert home.findChild(QTreeWidget, f"dashboard_breakdown_{col}") is not None
    assert home.findChild(QLabel, "dashboard_net") is not None
    assert home.findChild(QWidget, "dashboard_recurring") is not None
    assert home.findChild(QChartView, "dashboard_trend_chart") is not None
    # The retired single-tree / three-tile objectNames are gone.
    assert home.findChild(QTreeWidget, "dashboard_drilldown") is None
    assert home.findChild(QChartView, "dashboard_category_chart") is None


def test_INV9_node_to_column_map_expenditure_shows_spending_node(qtbot, service):
    """The falsifier for a naive positional zip: the Expenditure column's total is
    ``summary.expenditure`` (nodes[1] Spending), NOT ``.income`` (D2)."""
    from PySide6.QtWidgets import QLabel

    _seed_full(service)
    home = _home(service)
    qtbot.addWidget(home)
    reporting = ReportingService(service.vault)
    summary = reporting.summary(_JAN, None)
    symbol = reporting.base_currency()
    exp_total = home.findChild(QLabel, "dashboard_total_expenditure").text()
    inc_total = home.findChild(QLabel, "dashboard_total_income").text()
    # The Expenditure column shows summary.expenditure (nodes[1]), not .income.
    assert exp_total == _format_amount(summary.expenditure, symbol)  # 550
    assert exp_total != _format_amount(summary.income, symbol)  # not 3000
    assert inc_total == _format_amount(summary.income, symbol)
    heading = home.findChild(QLabel, "dashboard_heading_expenditure").text()
    assert heading == "Spending"  # renders the app's word, not "Expenditure"


def test_INV1_column_totals_equal_drill_nodes_and_pies_mirror_children(qtbot, service):
    from PySide6.QtCharts import QChartView

    _seed_full(service)
    home = _home(service)
    qtbot.addWidget(home)
    reporting = ReportingService(service.vault)
    income, spending, transfers = reporting.drill_down(_JAN, None, labels=_labels())
    col_node = {"expenditure": spending, "income": income, "transfers": transfers}
    for col, node in col_node.items():
        pie = home.findChild(QChartView, f"dashboard_pie_{col}")
        slices = pie.chart().series()[0].slices()
        # Pie mirrors the branch's direct children (label + amount), summing to header.
        assert [s.label() for s in slices] == [c.label for c in node.children]
        assert [round(s.value(), 2) for s in slices] == [
            round(float(c.amount), 2) for c in node.children
        ]
        assert sum(s.value() for s in slices) == pytest.approx(float(node.amount))


def test_INV2_confirmed_transfer_only_in_transfers_column(qtbot, service):
    from PySide6.QtCharts import QChartView
    from PySide6.QtWidgets import QTreeWidget

    _seed_full(service)
    home = _home(service)
    qtbot.addWidget(home)
    xfer_tree = home.findChild(QTreeWidget, "dashboard_breakdown_transfers")
    tops = [
        xfer_tree.topLevelItem(i).text(0) for i in range(xfer_tree.topLevelItemCount())
    ]
    assert any("Default" in t and "Savings" in t for t in tops)  # the pair
    # The transfer legs are absent from Expenditure/Income pies.
    for col in ("expenditure", "income"):
        pie = home.findChild(QChartView, f"dashboard_pie_{col}")
        labels = {s.label() for s in pie.chart().series()[0].slices()}
        assert not any("Savings" in ll or "Default" in ll for ll in labels)


# --- INV-4/D8: empty branch -------------------------------------------------- #
def test_INV4_empty_branch_hides_pie_shows_placeholder(qtbot, service):
    from PySide6.QtCharts import QChartView
    from PySide6.QtWidgets import QLabel

    a, _b = _two_accounts(service)
    _add(service, a, 500000, "2026-01-03", "SALARY")  # income only
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    home.show()
    qtbot.waitExposed(home)
    pie = home.findChild(QChartView, "dashboard_pie_expenditure")
    placeholder = home.findChild(QLabel, "dashboard_pie_empty_expenditure")
    assert pie is not None and not pie.isVisible()  # present but hidden
    assert placeholder is not None and placeholder.isVisible()


# --- D7: header colour, gated on amount_prefs.colour ------------------------- #
def test_D7_header_colour_gated_on_pref(qtbot, service):
    from PySide6.QtWidgets import QLabel

    from finbreak.services.auth import AmountPrefs

    _seed_full(service)
    home = _home(service, amount_prefs=AmountPrefs("minus", True))  # colour on
    qtbot.addWidget(home)
    exp_name = home.findChild(QLabel, "dashboard_heading_expenditure")
    exp_total = home.findChild(QLabel, "dashboard_total_expenditure")
    inc_name = home.findChild(QLabel, "dashboard_heading_income")
    assert _NEGATIVE_TEXT.name() in exp_name.styleSheet()
    assert _NEGATIVE_TEXT.name() in exp_total.styleSheet()
    assert _POSITIVE_TEXT.name() in inc_name.styleSheet()

    home_off = _home(service, amount_prefs=AmountPrefs("minus", False))  # colour off
    qtbot.addWidget(home_off)
    assert (
        home_off.findChild(QLabel, "dashboard_heading_expenditure").styleSheet() == ""
    )
    assert home_off.findChild(QLabel, "dashboard_total_expenditure").styleSheet() == ""


# --- INV-6: Net strip -------------------------------------------------------- #
def test_INV6_net_strip_shows_summary_net_coloured(qtbot, service):
    from PySide6.QtWidgets import QLabel

    from finbreak.services.auth import AmountPrefs

    _seed_full(service)  # income 3000, spend 550 -> net 2450 (transfers excluded)
    home = _home(service, amount_prefs=AmountPrefs("minus", True))
    qtbot.addWidget(home)
    net = home.findChild(QLabel, "dashboard_net")
    assert "2" in net.text() and "450" in net.text()
    assert _POSITIVE_TEXT.name() in net.styleSheet()  # positive net


# --- INV-5: recurring card --------------------------------------------------- #
def test_INV5_recurring_card_sums_confirmed_and_forces_role_colour(qtbot, service):
    from PySide6.QtWidgets import QLabel

    from finbreak.services.auth import AmountPrefs

    a, _b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03", "SALARY")  # some ordinary data
    _confirm_recurring(service, a, -19900, "Netflix REF")  # a confirmed OUT
    service.set_report_prefs(_JAN)
    home = _home(service, amount_prefs=AmountPrefs("minus", True))
    qtbot.addWidget(home)
    summary = RecurringService(service.vault).summary(date.today())
    assert summary.monthly_out > 0  # sanity: the confirmed OUT is summed

    out_label = home.findChild(QLabel, "dashboard_recurring_out")
    net_label = home.findChild(QLabel, "dashboard_recurring_net")
    assert out_label is not None
    assert "199" in out_label.text()
    # Force-by-role: Out is negative-coloured even though monthly_out is positive.
    assert _NEGATIVE_TEXT.name() in out_label.styleSheet()
    # net = in - out is negative here (no confirmed IN) -> negative colour.
    assert _NEGATIVE_TEXT.name() in net_label.styleSheet()


def test_INV5_recurring_card_hint_when_no_confirmed(qtbot, service):
    from PySide6.QtWidgets import QLabel, QWidget

    a, _b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03", "SALARY")  # data, but nothing confirmed
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    card = home.findChild(QWidget, "dashboard_recurring")
    assert card is not None
    # Hint mode: the figure objectNames are absent.
    assert home.findChild(QLabel, "dashboard_recurring_in") is None
    assert home.findChild(QLabel, "dashboard_recurring_out") is None


def test_INV5_recurring_card_shows_figures_when_net_zero(qtbot, service):
    """The gate is the two directional totals, not net: a confirmed IN that cancels a
    confirmed OUT (net == 0, both directionals > 0) shows figures, not the hint."""
    from PySide6.QtWidgets import QLabel

    from finbreak.services.auth import AmountPrefs

    a, _b = _two_accounts(service)
    _confirm_recurring(service, a, -19900, "Netflix REF")  # OUT 199/mo
    _confirm_recurring(
        service, a, 19900, "Netflix REF"
    )  # IN 199/mo (same key, other dir)
    service.set_report_prefs(_JAN)
    home = _home(service, amount_prefs=AmountPrefs("minus", True))  # colour on
    qtbot.addWidget(home)
    summary = RecurringService(service.vault).summary(date.today())
    assert summary.monthly_in > 0 and summary.monthly_out > 0 and summary.net == 0
    in_label = home.findChild(QLabel, "dashboard_recurring_in")
    out_label = home.findChild(QLabel, "dashboard_recurring_out")
    assert in_label is not None  # figures, not hint
    # Force-by-role falsifier: here monthly_in AND monthly_out are both positive
    # (+199), so a sign-derived colour would paint both green — the role rule paints
    # In green and Out red regardless of the (positive) magnitude sign.
    assert _POSITIVE_TEXT.name() in in_label.styleSheet()
    assert _NEGATIVE_TEXT.name() in out_label.styleSheet()


def test_INV3_recurring_card_unscoped_by_period(qtbot, service):
    """The recurring card is unscoped: a period change leaves its figures unchanged."""
    from PySide6.QtWidgets import QComboBox, QLabel

    a, _b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03", "SALARY")
    _confirm_recurring(service, a, -19900, "Netflix REF")
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    before = home.findChild(QLabel, "dashboard_recurring_out").text()
    selector = home.findChild(QComboBox, "period_selector")
    selector.setCurrentIndex(selector.findData(MODE_SPECIFIC_YEAR))  # change scope
    after = home.findChild(QLabel, "dashboard_recurring_out").text()
    assert before == after  # unscoped — the card ignores the selectors


def test_INV3_recurring_card_reflects_a_confirm_on_next_refresh(qtbot, service):
    """The other half of INV-3: the card is rebuilt each refresh, so a Recurring-tab
    confirm shows on the next refresh() (falsifies a card cached at construction)."""
    from PySide6.QtWidgets import QLabel

    a, _b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03", "SALARY")
    # Seed the occurrences but DON'T confirm — the card starts in hint mode.
    today = date.today()
    for k in range(4):
        when = (today - timedelta(days=30 * k)).isoformat()
        _add(service, a, -19900, when, "Netflix REF")
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    assert home.findChild(QLabel, "dashboard_recurring_out") is None  # hint mode

    # Confirm on the (separate) Recurring service, then refresh Home.
    rec = RecurringService(service.vault)
    item = next(c for c in rec.candidates(today) if c.direction is Direction.OUT)
    rec.confirm(item.direction, item.merchant_key)
    home.refresh()
    out_label = home.findChild(QLabel, "dashboard_recurring_out")
    assert out_label is not None and "199" in out_label.text()  # now figures


# --- INV-9: read-only trees + getting-started -------------------------------- #
def test_INV9_column_trees_read_only(qtbot, service):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidget

    _seed_full(service)
    home = _home(service)
    qtbot.addWidget(home)
    tree = home.findChild(QTreeWidget, "dashboard_breakdown_expenditure")
    top = tree.topLevelItem(0)
    assert not (top.flags() & Qt.ItemFlag.ItemIsEditable)


def test_INV3_empty_vault_shows_getting_started_no_columns(qtbot, service):

    home = _home(service)
    qtbot.addWidget(home)
    assert home.current_page().objectName() == "home_page_empty"
