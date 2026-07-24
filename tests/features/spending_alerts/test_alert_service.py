"""FIBR-0172 — AlertService.alerts(today) over a real in-memory SQLCipher vault.

Enforces spec INV-1/2/4/5/9/11/13/15/16/19. A real (tmp_path) v12 vault; the
service prepares each detector's inputs (incl. the single Decimal->minor conversion
+ transfer/None-bucket exclusion), calls the detectors, orders per D1, and filters
dismissed keys. No network, no real financial data (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest

from conftest import _PW
from finbreak.models import AlertKind
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.alerts import AlertService
from finbreak.services.auth import AuthService
from finbreak.services.categorization import CategorizationService
from finbreak.services.recurring import RecurringService
from finbreak.services.transfer_detection import TransferDetectionService

pytestmark = pytest.mark.features

# Today = mid-July 2026, so the last COMPLETE month is June (priors Mar/Apr/May).
_TODAY = date(2026, 7, 15)


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # v12
    yield svc
    svc.lock()


def _acct(svc: AuthService, name: str = "Cheque", typ: str = "current") -> int:
    accounts = AccountService(svc.vault)
    existing = accounts.list_accounts()
    return existing[0].id if name == "Cheque" else accounts.add_account(name, typ).id


def _add(svc, account_id, day, minor, desc, cat_id=None) -> int:
    txn_id = TransactionRepository(svc.vault.connection).add(
        account_id, day, minor, desc
    )
    if cat_id is not None:
        CategorizationService(svc.vault).set_manual_category(txn_id, cat_id)
    return txn_id


def _groceries(svc) -> int:
    # "Groceries" is a default expenditure leaf seeded by the v2->v3 migration; reuse
    # it rather than adding a duplicate (the category service rejects same-name kin).
    from finbreak.repositories.categories import CategoryRepository

    repo = CategoryRepository(svc.vault.connection)
    exp = next(r for r in repo.children_of(None) if r.kind == "expenditure")
    return next(c for c in repo.children_of(exp.id) if c.name == "Groceries").id


def _seed_all_kinds(svc: AuthService) -> None:
    """Seed one vault that produces all three alert kinds (INV-19):
    - Spotify: a recent SUGGESTED monthly OUT stream (3 occurrences) -> new-recurring.
    - Insurance: a CONFIRMED monthly OUT stream, overdue past grace -> missed-debit.
    - Groceries: a categorised spike (June = 2.5x the Mar/Apr/May average of R1000).
    Plus an excluded confirmed transfer (Groceries category) + a None-bucket OUT row
    in June, neither of which may inflate the spike (INV-5).
    """
    a = _acct(svc)
    b = _acct(svc, "Savings", "savings")
    groceries = _groceries(svc)

    # (a) new-recurring — 3 monthly Spotify charges, uncategorised (None bucket).
    for day in ("2026-05-05", "2026-06-05", "2026-07-05"):
        _add(svc, a, day, -9_999, "Spotify")

    # (c) missed-debit — 3 monthly Insurance charges; next_expected 2026-07-10 is
    # overdue by 07-15 (+3 grace = 07-13 < 07-15). Confirmed below.
    for day in ("2026-04-10", "2026-05-10", "2026-06-10"):
        _add(svc, a, day, -45_000, "Insurance")

    # (b) category spike — Groceries, distinct descriptions so no month groups into a
    # recurring stream. Mar/Apr/May = 100000 each (avg 100000); June = 250000 (2.5x);
    # July (in-progress) = 999999 must NOT affect June's evaluation.
    _add(svc, a, "2026-03-20", -100_000, "Groceries Mar", groceries)
    _add(svc, a, "2026-04-20", -100_000, "Groceries Apr", groceries)
    _add(svc, a, "2026-05-20", -100_000, "Groceries May", groceries)
    _add(svc, a, "2026-06-20", -250_000, "Groceries Jun", groceries)
    _add(svc, a, "2026-07-20", -999_999, "Groceries Jul", groceries)

    # (INV-5) an EXCLUDED confirmed transfer carrying the Groceries category in June —
    # must not inflate June's spike; and a None-bucket June OUT row (excluded).
    debit = _add(svc, a, "2026-06-25", -500_000, "Move out", groceries)
    credit = _add(svc, b, "2026-06-25", 500_000, "Move in")
    TransferDetectionService(svc.vault).confirm(debit, credit)
    _add(svc, a, "2026-06-26", -70_000, "Uncategorised misc")  # None bucket

    # Confirm the Insurance stream so it becomes a missed-debit candidate.
    rec = RecurringService(svc.vault)
    ins = next(it for it in rec.candidates(_TODAY) if it.merchant_key == "insurance")
    rec.confirm(ins.direction, ins.merchant_key)


def _by_kind(alerts, kind):
    return [a for a in alerts if a.kind is kind]


# --------------------------------------------------------------------------- #
# INV-1 / INV-2 — new recurring
# --------------------------------------------------------------------------- #
def test_INV1_recent_suggested_out_stream_yields_new_recurring(service) -> None:
    _seed_all_kinds(service)
    alerts = AlertService(service.vault).alerts(_TODAY)
    new = _by_kind(alerts, AlertKind.NEW_RECURRING)
    assert [a.key for a in new] == ["new_recurring:spotify"]
    assert new[0].amount_minor == 9_999


def test_INV2_confirmed_and_in_streams_do_not_yield_new_recurring(service) -> None:
    svc = service
    a = _acct(svc)
    # An IN suggested stream (salary) must never fire — new-recurring is OUT-only.
    for day in ("2026-05-25", "2026-06-25", "2026-07-05"):
        _add(svc, a, day, 300_000, "Salary")
    # A confirmed OUT stream is already known -> not "new".
    for day in ("2026-05-01", "2026-06-01", "2026-07-01"):
        _add(svc, a, day, -12_000, "Gym")
    rec = RecurringService(svc.vault)
    gym = next(it for it in rec.candidates(_TODAY) if it.merchant_key == "gym")
    rec.confirm(gym.direction, gym.merchant_key)

    alerts = AlertService(svc.vault).alerts(_TODAY)
    assert _by_kind(alerts, AlertKind.NEW_RECURRING) == []


def test_INV1_established_suggested_stream_over_threshold_does_not_fire(service) -> None:
    # A suggested OUT stream with 5 occurrences (> _NEW_MAX_OCCURRENCES=4) is no
    # longer "new": the service must thread `occurrences` through the real snapshot
    # so the detector skips it (the occurrences>threshold boundary, service-level).
    svc = service
    a = _acct(svc)
    for day in ("2026-03-08", "2026-04-08", "2026-05-08", "2026-06-08", "2026-07-08"):
        _add(svc, a, day, -5_000, "Netflix")
    # Sanity: it IS a suggested OUT stream with 5 occurrences (so the null result is
    # the occurrences gate, not a detection miss).
    spotify_like = next(
        it for it in RecurringService(svc.vault).candidates(_TODAY)
        if it.merchant_key == "netflix"
    )
    assert spotify_like.occurrences == 5
    alerts = AlertService(svc.vault).alerts(_TODAY)
    assert _by_kind(alerts, AlertKind.NEW_RECURRING) == []


# --------------------------------------------------------------------------- #
# INV-4 / INV-5 — category spike (window + exclusions)
# --------------------------------------------------------------------------- #
def test_INV4_spike_is_last_complete_month_vs_prior_three(service) -> None:
    _seed_all_kinds(service)
    alerts = AlertService(service.vault).alerts(_TODAY)
    spikes = _by_kind(alerts, AlertKind.CATEGORY_SPIKE)
    assert len(spikes) == 1
    spike = spikes[0]
    assert spike.key.endswith(":2026-06")  # last complete month, never in-progress July
    assert spike.label == "Groceries"
    assert spike.amount_minor == 250_000  # June (999999 July is ignored)
    assert spike.baseline_minor == 100_000  # (100000*3 + 1)//3


def test_INV5_transfer_and_none_bucket_excluded_from_spike(service) -> None:
    _seed_all_kinds(service)
    alerts = AlertService(service.vault).alerts(_TODAY)
    spikes = _by_kind(alerts, AlertKind.CATEGORY_SPIKE)
    # The excluded transfer (-500000, Groceries) did NOT inflate June past 250000.
    assert spikes[0].amount_minor == 250_000
    # The None/uncategorised bucket never produces a spike alert.
    assert all(":None" not in a.key for a in alerts)


# --------------------------------------------------------------------------- #
# INV-9 — missed debit (confirmed OUT only)
# --------------------------------------------------------------------------- #
def test_INV9_confirmed_overdue_out_yields_missed_debit(service) -> None:
    _seed_all_kinds(service)
    alerts = AlertService(service.vault).alerts(_TODAY)
    missed = _by_kind(alerts, AlertKind.MISSED_DEBIT)
    assert len(missed) == 1
    assert missed[0].label == "Insurance"
    assert missed[0].amount_minor == 45_000
    assert missed[0].on == date(2026, 7, 10)
    assert missed[0].key == "missed_debit:insurance:2026-07-10"


def test_INV9_suggested_overdue_out_yields_no_missed_debit(service) -> None:
    svc = service
    a = _acct(svc)
    # A monthly OUT stream, overdue, but NEVER confirmed -> no missed-debit alert.
    for day in ("2026-04-10", "2026-05-10", "2026-06-10"):
        _add(svc, a, day, -45_000, "Insurance")
    alerts = AlertService(svc.vault).alerts(_TODAY)
    assert _by_kind(alerts, AlertKind.MISSED_DEBIT) == []


# --------------------------------------------------------------------------- #
# INV-11 / INV-13 — dismissal + per-kind scope
# --------------------------------------------------------------------------- #
def test_INV11_dismissed_alert_is_excluded(service) -> None:
    _seed_all_kinds(service)
    svc = AlertService(service.vault)
    before = svc.alerts(_TODAY)
    assert len(before) == 3
    # Dismiss each kind's key in turn; that alert vanishes, the others remain.
    for kind in (
        AlertKind.MISSED_DEBIT,
        AlertKind.NEW_RECURRING,
        AlertKind.CATEGORY_SPIKE,
    ):
        key = _by_kind(before, kind)[0].key
        svc.dismiss(key)
        after = svc.alerts(_TODAY)
        assert key not in {a.key for a in after}
    assert svc.alerts(_TODAY) == []


def test_INV13_spike_dismissal_is_per_month(service) -> None:
    _seed_all_kinds(service)
    svc = AlertService(service.vault)
    spike_key = _by_kind(svc.alerts(_TODAY), AlertKind.CATEGORY_SPIKE)[0].key
    cid = spike_key.split(":")[1]
    # A dismissal keyed to a DIFFERENT month leaves June's spike alerting.
    svc.dismiss(f"category_spike:{cid}:2026-05")
    assert spike_key in {a.key for a in svc.alerts(_TODAY)}
    # Dismissing June's own key suppresses it.
    svc.dismiss(spike_key)
    assert spike_key not in {a.key for a in svc.alerts(_TODAY)}


# --------------------------------------------------------------------------- #
# INV-16 / INV-19 / INV-15 — determinism, order, money-safety
# --------------------------------------------------------------------------- #
def test_INV16_same_today_yields_equal_lists(service) -> None:
    _seed_all_kinds(service)
    svc = AlertService(service.vault)
    assert svc.alerts(_TODAY) == svc.alerts(_TODAY)


def test_INV19_fixed_kind_then_size_order(service) -> None:
    _seed_all_kinds(service)
    alerts = AlertService(service.vault).alerts(_TODAY)
    assert [a.kind for a in alerts] == [
        AlertKind.MISSED_DEBIT,
        AlertKind.NEW_RECURRING,
        AlertKind.CATEGORY_SPIKE,
    ]


def test_INV15_service_amounts_are_exact_minor_and_decimal_free(service) -> None:
    _seed_all_kinds(service)
    alerts = AlertService(service.vault).alerts(_TODAY)
    exp = 2  # ZAR cents
    spotify = next(a for a in alerts if a.key == "new_recurring:spotify")
    insurance = next(a for a in alerts if a.kind is AlertKind.MISSED_DEBIT)
    assert spotify.amount_minor == int((Decimal("99.99") * 10**exp).to_integral_value())
    assert insurance.amount_minor == int(
        (Decimal("450.00") * 10**exp).to_integral_value()
    )
    # No Decimal escapes into the returned alerts (every money field a plain int).
    for a in alerts:
        assert type(a.amount_minor) is int
        assert type(a.baseline_minor) is int
        assert a.on is None or isinstance(a.on, date)
