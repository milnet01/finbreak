"""FIBR-0171 — `ForecastService` composes the brought-current anchor + the
confirmed recurring set into a `Forecast` (spec D1/D5/D6/D7, Deliverable 9).

Enforces tests/features/forecast/spec.md INV-2/3/6/13. A real (tmp_path) v11 vault;
no network, no real financial data (testing.md § 6).
"""

from collections.abc import Iterator
from datetime import date

import pytest

from conftest import _PW
from finbreak.models import Direction, ForecastMode
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.forecast import ForecastService
from finbreak.services.recurring import RecurringService

pytestmark = pytest.mark.features

_TODAY = date(2026, 5, 20)
_HORIZON = date(2026, 8, 31)

# A monthly Netflix series: Jan–Apr fall inside the statement period (already in the
# closing balance); only the May charge is after period_end (rolled into the anchor).
_NETFLIX_DAYS = ("2026-01-05", "2026-02-05", "2026-03-05", "2026-04-05", "2026-05-05")


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # migrates straight to v11
    yield svc
    svc.lock()


def _acct(svc: AuthService) -> int:
    return AccountService(svc.vault).list_accounts()[0].id


def _add(svc: AuthService, account_id: int, day: str, minor: int, desc: str) -> None:
    TransactionRepository(svc.vault.connection).add(account_id, day, minor, desc)


def _confirm_netflix(svc: AuthService) -> None:
    rec = RecurringService(svc.vault)
    item = next(it for it in rec.candidates(_TODAY) if it.merchant_key == "netflix")
    rec.confirm(item.direction, item.merchant_key)


def test_INV13_anchored_forecast_brought_current(service) -> None:
    svc = service
    a = _acct(svc)
    name = AccountService(svc.vault).list_accounts()[0].name

    # Persist a statement with a real closing balance (R5000.00).
    repo = StatementPeriodRepository(svc.vault.connection)
    repo.add(a, "2026-01-01", "2026-04-30", "apr.pdf", 500_000)
    svc.vault.connection.commit()

    # The recurring series (Jan–Apr in the balance; May after period_end).
    for day in _NETFLIX_DAYS:
        _add(svc, a, day, -19_900, "Netflix")
    # One more post-statement transaction (income), also in (period_end, today].
    _add(svc, a, "2026-05-10", 30_000, "Refund")
    _confirm_netflix(svc)

    fc = ForecastService(svc.vault).forecast(_TODAY, _HORIZON)

    # Anchor = 500000 (statement) + (-19900 May Netflix + 30000 refund) = 510100.
    assert fc.mode is ForecastMode.ANCHORED
    assert fc.start_minor == 510_100
    assert len(fc.anchor_sources) == 1
    src = fc.anchor_sources[0]
    assert src.account_id == a
    assert src.account_name == name
    assert src.statement_balance_minor == 500_000
    assert src.as_of == date(2026, 4, 30)
    assert src.since_txn_count == 2  # May Netflix + refund, in (period_end, today]
    assert src.current_balance_minor == 510_100

    # Confirmed Netflix projects forward: Jun/Jul/Aug 5th, each -19900 (OUT).
    assert [e.on for e in fc.events] == [
        date(2026, 6, 5),
        date(2026, 7, 5),
        date(2026, 8, 5),
    ]
    assert all(
        e.amount_minor == -19_900 and e.direction is Direction.OUT for e in fc.events
    )
    assert fc.end_minor == 510_100 - 3 * 19_900


def test_INV3_only_confirmed_items_project(service) -> None:
    svc = service
    a = _acct(svc)
    repo = StatementPeriodRepository(svc.vault.connection)
    repo.add(a, "2026-01-01", "2026-04-30", "apr.pdf", 500_000)
    svc.vault.connection.commit()

    for day in _NETFLIX_DAYS:
        _add(svc, a, day, -19_900, "Netflix")
    # A second recurring series left UNCONFIRMED (suggested only).
    for day in _NETFLIX_DAYS:
        _add(svc, a, day, -8_000, "Gym")
    _confirm_netflix(svc)  # only Netflix confirmed

    fc = ForecastService(svc.vault).forecast(_TODAY, _HORIZON)
    merchants = {e.merchant for e in fc.events}
    assert merchants == {"Netflix"}, "the unconfirmed Gym item must not project"


def test_INV2_no_recorded_balance_is_net_flow(service) -> None:
    svc = service
    a = _acct(svc)
    # A statement with NO closing balance (CSV-only), plus confirmed recurring.
    repo = StatementPeriodRepository(svc.vault.connection)
    repo.add(a, "2026-01-01", "2026-04-30", "apr.csv")  # NULL balance
    svc.vault.connection.commit()
    for day in _NETFLIX_DAYS:
        _add(svc, a, day, -19_900, "Netflix")
    _confirm_netflix(svc)

    fc = ForecastService(svc.vault).forecast(_TODAY, _HORIZON)
    assert fc.mode is ForecastMode.NET_FLOW
    assert fc.start_minor == 0
    assert fc.anchor_sources == []
    # Still projects the confirmed change from zero.
    assert fc.events and fc.end_minor == -3 * 19_900


def test_INV14_debt_account_balance_is_not_anchored(service) -> None:
    """FIBR-0179: a credit-card statement prints its closing in the *owed*
    convention (positive = debt), the opposite sign to `amount_minor`. It can be
    neither brought current by adding transactions nor summed into a cash total,
    so it must not contribute to the anchor at all."""
    svc = service
    cash = _acct(svc)
    card = AccountService(svc.vault).add_account("Visa", "credit_card").id

    repo = StatementPeriodRepository(svc.vault.connection)
    repo.add(cash, "2026-01-01", "2026-04-30", "apr.pdf", 500_000)
    repo.add(card, "2026-01-01", "2026-04-30", "card-apr.pdf", 120_000)  # R1200 owed
    svc.vault.connection.commit()
    # A post-statement card purchase: canonical sign (-), owed convention (+).
    _add(svc, card, "2026-05-10", -25_000, "Fuel")

    fc = ForecastService(svc.vault).forecast(_TODAY, _HORIZON)

    assert [src.account_id for src in fc.anchor_sources] == [cash]
    assert fc.start_minor == 500_000, "the owed figure must not inflate the cash total"


def test_INV14_debt_only_vault_is_net_flow(service) -> None:
    """With no cash account carrying a balance, there is no honest anchor —
    NET_FLOW, not a forecast anchored on a debt figure (FIBR-0179)."""
    svc = service
    card = AccountService(svc.vault).add_account("Visa", "credit_card").id
    repo = StatementPeriodRepository(svc.vault.connection)
    repo.add(card, "2026-01-01", "2026-04-30", "card-apr.pdf", 120_000)
    svc.vault.connection.commit()

    fc = ForecastService(svc.vault).forecast(_TODAY, _HORIZON)
    assert fc.mode is ForecastMode.NET_FLOW
    assert fc.start_minor == 0
    assert fc.anchor_sources == []


def test_INV2_empty_vault_is_net_flow_zero(service) -> None:
    fc = ForecastService(service.vault).forecast(_TODAY, _HORIZON)
    assert fc.mode is ForecastMode.NET_FLOW
    assert fc.start_minor == 0 == fc.end_minor
    assert fc.events == []
    assert len(fc.points) == 2


def test_a_month_end_debit_order_last_seen_in_a_short_month_stays_on_month_end(
    service,
) -> None:
    """Full audit 2026-09-27, row 12. A debit order for the 31st was last seen on
    Apr 30 -- the bank's own clamp -- and the forecast stepped from that date, so
    it projected the 30th for the rest of the horizon: May 30, Jul 30, Aug 30,
    each a day early. It must follow the day the order really aims at."""
    svc = service
    a = _acct(svc)
    for day in ("2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"):
        _add(svc, a, day, -250_000, "Bond repayment")
    rec = RecurringService(svc.vault)
    today = date(2026, 5, 5)
    item = next(
        it for it in rec.candidates(today) if it.merchant_key == "bond repayment"
    )
    rec.confirm(item.direction, item.merchant_key)

    fc = ForecastService(svc.vault).forecast(today, date(2026, 8, 31))

    assert [e.on for e in fc.events] == [
        date(2026, 5, 31),
        date(2026, 6, 30),
        date(2026, 7, 31),
        date(2026, 8, 31),
    ]
    assert item.next_expected == date(2026, 5, 31), (
        "the missed-debit alert keys on next_expected, which had the same drift"
    )
