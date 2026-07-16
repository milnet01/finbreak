"""FIBR-0012 INV-7 — HomeView as the dashboard.

The pure donut-collapse logic is tested directly (cheap); the widget shape,
tiles, placeholder, and selector persistence use the pytest-qt `qtbot`. Period is
pinned to a specific month via stored prefs so renders are deterministic.
"""

from decimal import Decimal

import pytest

from conftest import _PW
from finbreak.models import CategorySpend
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import CategorizationService
from finbreak.services.reporting import (
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    ReportingService,
    ReportPrefs,
)

pytestmark = pytest.mark.features

_JAN = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=1)


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _first_account(service):
    from finbreak.repositories.accounts import AccountRepository

    return AccountRepository(service.vault.connection).list_all()[0].id


def _add(service, account_id, amount_minor, occurred_on="2026-01-05"):
    return TransactionRepository(service.vault.connection).add(
        account_id, occurred_on, amount_minor, "x"
    )


def _leaf(service, name):
    roots = CategoryRepository(service.vault.connection).children_of(None)
    exp = next(r for r in roots if r.kind == "expenditure")
    return CategoryService(service.vault).add_category(exp.id, name).id


def _set_cat(service, txn_id, cat_id):
    CategorizationService(service.vault).set_manual_category(txn_id, cat_id)


def _home(service):
    from finbreak.services.recurring import RecurringService
    from finbreak.ui.home import HomeView

    return HomeView(
        ReportingService(service.vault),
        AccountService(service.vault),
        service,
        recurring=RecurringService(service.vault),
    )


# --------------------------------------------------------------------------- #
# Pure donut-collapse logic (D9)
# --------------------------------------------------------------------------- #
def _spend(cat_id, amount):
    return CategorySpend(category_id=cat_id, name=f"c{cat_id}", amount=Decimal(amount))


def test_donut_wedges_all_shown_when_within_cap():
    from finbreak.ui.charts import _donut_wedges

    spending = [_spend(i, 100 - i) for i in range(1, 6)]  # 5 categorised
    wedges = _donut_wedges(spending, "Uncategorised", "Other")
    assert [w[0] for w in wedges] == ["c1", "c2", "c3", "c4", "c5"]


def test_donut_wedges_collapse_ten_plus_uncategorised():
    """10 categorised + Uncategorised -> 6 coloured + Uncategorised + Other,
    in that order (D9 >8 collapse; Uncategorised before Other, both pinned last)."""
    from finbreak.ui.charts import _OTHER_COLOUR, _UNCAT_COLOUR, _donut_wedges

    spending = [_spend(i, 1000 - i) for i in range(1, 11)]  # 10 categorised, desc
    spending.append(CategorySpend(None, "", Decimal("5")))  # Uncategorised bucket
    wedges = _donut_wedges(spending, "Uncategorised", "Other")
    assert len(wedges) == 8
    labels = [w[0] for w in wedges]
    assert labels[:6] == ["c1", "c2", "c3", "c4", "c5", "c6"]  # top-6 coloured
    assert labels[6] == "Uncategorised"
    assert labels[7] == "Other"
    assert wedges[6][2] == _UNCAT_COLOUR
    assert wedges[7][2] == _OTHER_COLOUR
    # Other sums the collapsed tail (c7..c10 magnitudes).
    assert wedges[7][1] == Decimal(sum(1000 - i for i in range(7, 11)))


def test_donut_wedges_empty_spending_is_no_wedges():
    from finbreak.ui.charts import _donut_wedges

    assert _donut_wedges([], "Uncategorised", "Other") == []


# --------------------------------------------------------------------------- #
# INV-7 — widget shape
# --------------------------------------------------------------------------- #
def test_INV7_empty_vault_shows_getting_started(qtbot, service):
    home = _home(service)
    qtbot.addWidget(home)
    assert home.current_page().objectName() == "home_page_empty"


def test_INV7_with_data_shows_dashboard_and_no_table(qtbot, service):
    from PySide6.QtWidgets import QTableWidget

    a = _first_account(service)
    _add(service, a, 100000, "2026-01-03")
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    assert home.current_page().objectName() == "home_page_dashboard"
    assert home.findChild(QTableWidget) is None  # no transaction table on Home
    # Selectors + both charts present.
    from PySide6.QtCharts import QChartView
    from PySide6.QtWidgets import QComboBox

    assert home.findChild(QComboBox, "period_selector") is not None
    assert home.findChild(QComboBox, "account_selector") is not None
    assert home.findChild(QChartView, "dashboard_pie_expenditure") is not None
    assert home.findChild(QChartView, "dashboard_trend_chart") is not None


def test_INV7_tiles_show_income_expenditure_net(qtbot, service):
    """FIBR-0143: the income/expenditure figures moved into the column-header totals
    and the Net figure into the slim Net strip."""
    from PySide6.QtWidgets import QLabel

    a = _first_account(service)
    _add(service, a, 300000, "2026-01-03")  # income 3000
    _add(service, a, -50000, "2026-01-05")  # spend 500
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    income = home.findChild(QLabel, "dashboard_total_income")
    expenditure = home.findChild(QLabel, "dashboard_total_expenditure")
    net = home.findChild(QLabel, "dashboard_net")
    assert "3" in income.text() and "000" in income.text()
    assert "500" in expenditure.text()
    assert "2" in net.text() and "500" in net.text()  # net 2500


def test_INV7_donut_has_a_slice_per_category(qtbot, service):
    """FIBR-0143: the spending pie is now the Expenditure column's pie."""
    from PySide6.QtCharts import QChartView

    a = _first_account(service)
    fuel = _leaf(service, "Ztest Fuel")
    groceries = _leaf(service, "Ztest Groceries")
    _set_cat(service, _add(service, a, -70000, "2026-01-05"), fuel)
    _set_cat(service, _add(service, a, -30000, "2026-01-06"), groceries)
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    view = home.findChild(QChartView, "dashboard_pie_expenditure")
    assert view.isVisible() or not view.isHidden()
    slices = view.chart().series()[0].slices()
    labels = {s.label() for s in slices}
    assert labels == {"Ztest Fuel", "Ztest Groceries"}


def test_INV7_empty_donut_hides_chart_shows_placeholder(qtbot, service):
    """FIBR-0143: the empty-state toggle now lives on each column's pie."""
    from PySide6.QtCharts import QChartView
    from PySide6.QtWidgets import QLabel

    a = _first_account(service)
    _add(service, a, 300000, "2026-01-03")  # income only -> no spending
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    home.show()  # visibility is only meaningful once shown
    qtbot.waitExposed(home)
    view = home.findChild(QChartView, "dashboard_pie_expenditure")
    placeholder = home.findChild(QLabel, "dashboard_pie_empty_expenditure")
    assert not view.isVisible()
    assert placeholder.isVisible()


def test_INV7_trend_has_twelve_categories(qtbot, service):
    from PySide6.QtCharts import QBarCategoryAxis, QChartView

    a = _first_account(service)
    _add(service, a, 100000, "2026-01-15")
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    view = home.findChild(QChartView, "dashboard_trend_chart")
    cat_axis = next(
        ax for ax in view.chart().axes() if isinstance(ax, QBarCategoryAxis)
    )
    assert len(cat_axis.categories()) == 12


# --------------------------------------------------------------------------- #
# INV-7 / D6 — selector persistence
# --------------------------------------------------------------------------- #
def test_INV7_period_selector_change_persists_and_rerenders(qtbot, service):
    from PySide6.QtWidgets import QComboBox

    a = _first_account(service)
    _add(service, a, 100000, "2026-01-03")
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    selector = home.findChild(QComboBox, "period_selector")
    # Switch to "Specific year" — the year picker's value drives it.
    year_index = selector.findData(MODE_SPECIFIC_YEAR)
    selector.setCurrentIndex(year_index)
    stored = service.report_prefs()
    assert stored.mode == MODE_SPECIFIC_YEAR


def test_INV7_account_selector_lists_all_accounts_first(qtbot, service):
    from PySide6.QtWidgets import QComboBox

    a = _first_account(service)
    AccountService(service.vault).add_account("Savings", "savings")
    _add(service, a, 100000, "2026-01-03")
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    combo = home.findChild(QComboBox, "account_selector")
    assert combo.itemData(0) is None  # "All accounts" first, id None
    assert combo.count() == 3  # All + Default + Savings
