"""FIBR-0012 INV-1/4/5/6/13 — ReportingService over a seeded vault.

A two-account vault seeded with income, expense, an uncategorised expense, and a
confirmed inter-account transfer. Every figure excludes the confirmed transfer;
money stays exact (integer minor units). Period is pinned to a specific month so
the window is deterministic without a clock.
"""

from datetime import date
from decimal import Decimal

import pytest

from conftest import _PW
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
from finbreak.services.transfer_detection import TransferDetectionService

pytestmark = pytest.mark.features

# A specific-month period so the window needs no clock; the injected `today` is
# irrelevant for specific modes but still passed for signature parity.
_JAN = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=1)
_TODAY = date(2026, 7, 12)


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _two_accounts(service):
    accounts = AccountService(service.vault)
    from finbreak.repositories.accounts import AccountRepository

    first = AccountRepository(service.vault.connection).list_all()[0].id
    second = accounts.add_account("Savings", "savings").id
    return first, second


def _add(service, account_id, amount_minor, occurred_on="2026-01-05", description="x"):
    return TransactionRepository(service.vault.connection).add(
        account_id, occurred_on, amount_minor, description
    )


def _expenditure_leaf(service, name="Ztest Groceries"):
    """Add a leaf under the Expenditure root and return its id."""
    from finbreak.repositories.categories import CategoryRepository

    roots = CategoryRepository(service.vault.connection).children_of(None)
    exp_root = next(r for r in roots if r.kind == "expenditure")
    return CategoryService(service.vault).add_category(exp_root.id, name).id


def _set_category(service, txn_id, category_id):
    CategorizationService(service.vault).set_manual_category(txn_id, category_id)


# --------------------------------------------------------------------------- #
# INV-4 — income / expenditure / net
# --------------------------------------------------------------------------- #
def test_INV4_summary_income_expenditure_net(service):
    a, _b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03")  # income 3000.00
    _add(service, a, -50000, "2026-01-05")  # expense 500.00
    _add(service, a, -25000, "2026-01-07")  # expense 250.00
    summary = ReportingService(service.vault).summary(_JAN, None, _TODAY)
    assert summary.income == Decimal("3000.00")
    assert summary.expenditure == Decimal("750.00")
    assert summary.net == Decimal("2250.00")


def test_INV4_empty_period_is_all_zero(service):
    _two_accounts(service)
    summary = ReportingService(service.vault).summary(_JAN, None, _TODAY)
    assert (summary.income, summary.expenditure, summary.net) == (
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    )


def test_INV4_single_account_view_excludes_the_other_account(service):
    a, b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-03")  # account A income
    _add(service, b, 200000, "2026-01-03")  # account B income
    reporting = ReportingService(service.vault)
    assert reporting.summary(_JAN, frozenset({a}), _TODAY).income == Decimal("1000.00")
    assert reporting.summary(_JAN, frozenset({b}), _TODAY).income == Decimal("2000.00")
    assert reporting.summary(_JAN, None, _TODAY).income == Decimal("3000.00")


def test_INV4_out_of_period_rows_are_excluded(service):
    a, _b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-15")  # in Jan
    _add(service, a, 500000, "2026-02-01")  # out of Jan
    assert ReportingService(service.vault).summary(
        _JAN, None, _TODAY
    ).income == Decimal("1000.00")


# --------------------------------------------------------------------------- #
# FIBR-0013 D4 — account-set widening (account_ids: frozenset[int] | None)
# --------------------------------------------------------------------------- #
def test_D4_account_subset_combines_exactly_those_accounts(service):
    """A frozenset selects exactly its accounts, excluding others (combined)."""
    a, b = _two_accounts(service)
    c = AccountService(service.vault).add_account("Third", "current").id
    _add(service, a, 100000, "2026-01-03")  # 1000.00
    _add(service, b, 200000, "2026-01-03")  # 2000.00
    _add(service, c, 400000, "2026-01-03")  # excluded
    got = ReportingService(service.vault).summary(_JAN, frozenset({a, b}), _TODAY)
    assert got.income == Decimal("3000.00")


def test_D4_none_account_ids_is_all_accounts(service):
    a, b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-03")
    _add(service, b, 200000, "2026-01-03")
    assert ReportingService(service.vault).summary(
        _JAN, None, _TODAY
    ).income == Decimal("3000.00")


def test_D4_empty_account_set_is_empty_not_all(service):
    """An empty frozenset selects NO accounts -> empty report, never 'all'
    (the D4 privacy guard; no invalid ``IN ()`` SQL)."""
    a, _b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-03")
    got = ReportingService(service.vault).summary(_JAN, frozenset(), _TODAY)
    assert got.income == Decimal("0.00")


def test_D4_single_element_set_matches_single_account(service):
    a, b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-03")
    _add(service, b, 200000, "2026-01-03")
    reporting = ReportingService(service.vault)
    assert reporting.summary(_JAN, frozenset({a}), _TODAY).income == Decimal("1000.00")
    assert reporting.summary(_JAN, frozenset({b}), _TODAY).income == Decimal("2000.00")


# --------------------------------------------------------------------------- #
# INV-1 — transfers never counted
# --------------------------------------------------------------------------- #
def test_INV1_confirmed_transfer_excluded_from_every_figure(service):
    a, b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03")  # ordinary income
    exp_leaf = _expenditure_leaf(service)
    spend = _add(service, a, -40000, "2026-01-04")  # ordinary expense
    _set_category(service, spend, exp_leaf)
    debit = _add(service, a, -100000, "2026-01-10", "to savings")
    credit = _add(service, b, 100000, "2026-01-10", "from current")

    reporting = ReportingService(service.vault)
    detection = TransferDetectionService(service.vault)

    # Before confirming: the transfer legs ARE counted.
    before = reporting.summary(_JAN, None, _TODAY)
    assert before.income == Decimal("4000.00")  # 3000 + 1000 transfer credit
    assert before.expenditure == Decimal("1400.00")  # 400 + 1000 transfer debit

    detection.confirm(debit, credit)

    after = reporting.summary(_JAN, None, _TODAY)
    assert after.income == Decimal("3000.00")  # transfer credit dropped
    assert after.expenditure == Decimal("400.00")  # transfer debit dropped
    assert after.net == Decimal("2600.00")

    # The donut + trend also drop the transfer (only the categorised 400 expense).
    donut = reporting.spending_by_category(_JAN, None, _TODAY)
    assert [(c.category_id, c.amount) for c in donut] == [(exp_leaf, Decimal("400.00"))]

    jan_point = next(
        m for m in reporting.monthly_trend(_JAN, None, _TODAY) if m.label == "2026-01"
    )
    assert jan_point.income == Decimal("3000.00")
    assert jan_point.expenditure == Decimal("400.00")


def test_INV1_unconfirmed_pair_is_still_counted(service):
    a, b = _two_accounts(service)
    _add(service, a, -100000, "2026-01-10", "to savings")
    _add(service, b, 100000, "2026-01-10", "from current")
    # A candidate exists but is NOT confirmed, so both legs still count.
    assert TransferDetectionService(service.vault).confirmed_transfer_txn_ids() == set()
    summary = ReportingService(service.vault).summary(_JAN, None, _TODAY)
    assert summary.income == Decimal("1000.00")
    assert summary.expenditure == Decimal("1000.00")


# --------------------------------------------------------------------------- #
# INV-5 — category donut
# --------------------------------------------------------------------------- #
def test_INV5_grouped_by_category_sorted_magnitude_desc(service):
    a, _b = _two_accounts(service)
    groceries = _expenditure_leaf(service, "Ztest Groceries")
    fuel = _expenditure_leaf(service, "Ztest Fuel")
    g1 = _add(service, a, -30000, "2026-01-03")
    g2 = _add(service, a, -20000, "2026-01-04")  # Groceries total 500.00
    f1 = _add(service, a, -70000, "2026-01-05")  # Fuel total 700.00
    _set_category(service, g1, groceries)
    _set_category(service, g2, groceries)
    _set_category(service, f1, fuel)
    donut = ReportingService(service.vault).spending_by_category(_JAN, None, _TODAY)
    # Fuel (700) sorts before Groceries (500).
    assert [(c.category_id, c.name, c.amount) for c in donut] == [
        (fuel, "Ztest Fuel", Decimal("700.00")),
        (groceries, "Ztest Groceries", Decimal("500.00")),
    ]


def test_INV5_same_named_leaves_under_different_parents_stay_distinct(service):
    """FIBR-0006 sibling-unique-only names: two "Other" leaves under Income vs
    Expenditure parents are grouped by id, so they stay separate slices."""
    from finbreak.repositories.categories import CategoryRepository

    a, _b = _two_accounts(service)
    roots = CategoryRepository(service.vault.connection).children_of(None)
    exp_root = next(r for r in roots if r.kind == "expenditure")
    inc_root = next(r for r in roots if r.kind == "income")
    exp_other = CategoryService(service.vault).add_category(exp_root.id, "Other").id
    inc_other = CategoryService(service.vault).add_category(inc_root.id, "Other").id
    # Two expense rows filed under the two same-named leaves.
    t1 = _add(service, a, -10000, "2026-01-03")
    t2 = _add(service, a, -20000, "2026-01-04")
    _set_category(service, t1, exp_other)
    _set_category(service, t2, inc_other)  # nonsensical but proves id-grouping
    donut = ReportingService(service.vault).spending_by_category(_JAN, None, _TODAY)
    ids = {c.category_id for c in donut}
    assert exp_other in ids and inc_other in ids
    assert len(donut) == 2  # two distinct slices, not merged on the name "Other"


def test_INV5_uncategorised_bucket_is_none_appended_last(service):
    a, _b = _two_accounts(service)
    fuel = _expenditure_leaf(service, "Ztest Fuel")
    f1 = _add(service, a, -70000, "2026-01-05")
    _set_category(service, f1, fuel)
    _add(service, a, -15000, "2026-01-06")  # uncategorised expense
    donut = ReportingService(service.vault).spending_by_category(_JAN, None, _TODAY)
    assert donut[-1].category_id is None  # Uncategorised appended last
    assert donut[-1].name == ""  # the "" sentinel; UI supplies tr("Uncategorised")
    assert donut[-1].amount == Decimal("150.00")


def test_INV5_income_rows_are_absent_from_the_donut(service):
    a, _b = _two_accounts(service)
    _add(service, a, 500000, "2026-01-03")  # income only
    assert (
        ReportingService(service.vault).spending_by_category(_JAN, None, _TODAY) == []
    )


# --------------------------------------------------------------------------- #
# INV-6 — trend span
# --------------------------------------------------------------------------- #
def test_INV6_trend_is_twelve_points_with_zero_filled_months(service):
    a, _b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-15")  # income in Jan only
    trend = ReportingService(service.vault).monthly_trend(_JAN, None, _TODAY)
    assert len(trend) == 12
    assert trend[-1].label == "2026-01"  # ends at the period month
    assert trend[0].label == "2025-02"  # 12 months back, oldest first
    jan = trend[-1]
    assert jan.income == Decimal("1000.00")
    # Every other month is a present zero point.
    for point in trend[:-1]:
        assert point.income == Decimal("0.00")
        assert point.expenditure == Decimal("0.00")


def test_INV6_specific_year_trend_is_that_years_jan_to_dec(service):
    a, _b = _two_accounts(service)
    _add(service, a, 100000, "2025-03-15")
    _add(service, a, -40000, "2025-11-20")
    trend = ReportingService(service.vault).monthly_trend(
        ReportPrefs(MODE_SPECIFIC_YEAR, year=2025), None, _TODAY
    )
    assert [m.label for m in trend] == [f"2025-{m:02d}" for m in range(1, 13)]
    assert next(m for m in trend if m.label == "2025-03").income == Decimal("1000.00")
    assert next(m for m in trend if m.label == "2025-11").expenditure == Decimal(
        "400.00"
    )


def test_INV6_row_on_the_last_day_of_the_end_month_is_included(service):
    a, _b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-31")  # last day of the Jan end month
    trend = ReportingService(service.vault).monthly_trend(_JAN, None, _TODAY)
    assert next(m for m in trend if m.label == "2026-01").income == Decimal("1000.00")


# --------------------------------------------------------------------------- #
# INV-13 — money exact
# --------------------------------------------------------------------------- #
def test_INV13_service_sum_matches_a_decimal_reference(service):
    a, _b = _two_accounts(service)
    amounts = [12345, -6789, 100000, -33, 987654, -21000, 4567]
    for i, amt in enumerate(amounts):
        _add(service, a, amt, f"2026-01-{(i % 27) + 1:02d}")
    summary = ReportingService(service.vault).summary(_JAN, None, _TODAY)
    income_ref = Decimal(sum(v for v in amounts if v > 0)).scaleb(-2)
    expenditure_ref = Decimal(-sum(v for v in amounts if v < 0)).scaleb(-2)
    assert summary.income == income_ref
    assert summary.expenditure == expenditure_ref
    assert summary.net == income_ref - expenditure_ref


def test_INV13_transaction_count_is_live_whole_vault(service):
    a, b = _two_accounts(service)
    reporting = ReportingService(service.vault)
    assert reporting.transaction_count() == 0
    _add(service, a, 100, "2026-01-03")
    _add(service, b, 200, "2026-05-03")  # even out of the dashboard period
    assert reporting.transaction_count() == 2  # unfiltered, live


def test_base_currency_symbol(service):
    assert ReportingService(service.vault).base_currency() == "ZAR"
