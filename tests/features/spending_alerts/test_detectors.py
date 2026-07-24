"""FIBR-0172 — the three pure spending-alert detectors (no DB, no Qt).

Enforces tests/features/spending_alerts/spec.md → docs/specs/FIBR-0172.md
INV-1/3/6/7/8/10/15. Money is integer minor units only — no Decimal/float in the
detectors (INV-15). Each detector consumes the § 3 prepared-input dataclasses and
returns ``list[SpendingAlert]`` (INV-15: every field a plain int/str/date).
"""

from __future__ import annotations

from datetime import date

import pytest

from finbreak.models import AlertKind, SpendingAlert
from finbreak.services.alerts import (
    _MISS_GRACE,
    _NEW_MAX_OCCURRENCES,
    _SPIKE_FACTOR,
    CategorySpikeInput,
    MissedDebitInput,
    NewRecurringInput,
    detect_category_spikes,
    detect_missed_debits,
    detect_new_recurring,
)

pytestmark = pytest.mark.features


def _new(
    occurrences: int,
    *,
    merchant: str = "Netflix",
    key: str = "netflix",
    amount_minor: int = 19900,
) -> NewRecurringInput:
    return NewRecurringInput(merchant, key, amount_minor, occurrences)


# --------------------------------------------------------------------------- #
# (a) detect_new_recurring — INV-1 (occurrences gate) + INV-3 (key/payload)
# --------------------------------------------------------------------------- #
def test_INV1_new_recurring_fires_at_min_and_max_occurrences() -> None:
    # 3 (just-detected) and 4 (== _NEW_MAX_OCCURRENCES) both fire; 5 does not.
    assert _NEW_MAX_OCCURRENCES == 4
    fired_3 = detect_new_recurring([_new(3)])
    fired_4 = detect_new_recurring([_new(4)])
    not_fired = detect_new_recurring([_new(5)])
    assert len(fired_3) == 1
    assert len(fired_4) == 1
    assert not_fired == []


def test_INV3_new_recurring_key_and_payload() -> None:
    alerts = detect_new_recurring(
        [_new(3, merchant="Spotify", key="spotify", amount_minor=9999)]
    )
    assert len(alerts) == 1
    alert = alerts[0]
    assert isinstance(alert, SpendingAlert)
    assert alert.kind is AlertKind.NEW_RECURRING
    assert alert.key == "new_recurring:spotify"
    assert alert.label == "Spotify"
    assert alert.amount_minor == 9999
    assert alert.baseline_minor == 0
    assert alert.on is None


# --------------------------------------------------------------------------- #
# (b) detect_category_spikes — INV-6 (threshold), INV-7 (key), INV-15 (int mean)
# --------------------------------------------------------------------------- #
def _spike(
    prior: tuple[int, ...], current: int, *, cid: int = 7, name: str = "Groceries"
) -> CategorySpikeInput:
    return CategorySpikeInput(cid, name, current, prior)


def test_INV6_spike_fires_at_exactly_two_times_average() -> None:
    assert _SPIKE_FACTOR == 2
    # avg = (300 + 1)//3 = 100; current 200 == 2.0x -> fires.
    fired = detect_category_spikes(
        [_spike((100, 100, 100), 200)], "2026-06", min_baseline=100
    )
    assert len(fired) == 1
    assert fired[0].baseline_minor == 100
    assert fired[0].amount_minor == 200


def test_INV6_spike_does_not_fire_below_two_times() -> None:
    # current 190 < 2*100 -> no alert (1.9x).
    assert (
        detect_category_spikes(
            [_spike((100, 100, 100), 190)], "2026-06", min_baseline=100
        )
        == []
    )


def test_INV6_spike_below_min_baseline_never_fires() -> None:
    # 10x the average, but avg 10 < min_baseline 100 -> suppressed.
    assert (
        detect_category_spikes([_spike((10, 10, 10), 100)], "2026-06", min_baseline=100)
        == []
    )


def test_INV6_empty_prior_yields_no_alert() -> None:
    assert detect_category_spikes([_spike((), 500)], "2026-06", min_baseline=1) == []


def test_INV7_spike_key_is_per_category_per_month() -> None:
    alerts = detect_category_spikes(
        [_spike((100, 100, 100), 200, cid=42)], "2026-06", min_baseline=1
    )
    assert alerts[0].kind is AlertKind.CATEGORY_SPIKE
    assert alerts[0].key == "category_spike:42:2026-06"
    assert alerts[0].label == "Groceries"
    assert alerts[0].on is None
    # A different month is a distinct key (dismissing one leaves the other).
    other = detect_category_spikes(
        [_spike((100, 100, 100), 200, cid=42)], "2026-07", min_baseline=1
    )
    assert other[0].key == "category_spike:42:2026-07"


def test_INV15_average_is_integer_round_half_up() -> None:
    # (301 + 1)//3 = 100 (100.33 rounds down); (302 + 1)//3 = 101 (100.67 rounds up).
    down = detect_category_spikes(
        [_spike((100, 100, 101), 500)], "2026-06", min_baseline=1
    )
    up = detect_category_spikes(
        [_spike((100, 101, 101), 500)], "2026-06", min_baseline=1
    )
    assert down[0].baseline_minor == 100
    assert up[0].baseline_minor == 101
    # Money-safe: the baseline is a plain int, never a Decimal/float.
    assert type(down[0].baseline_minor) is int


# --------------------------------------------------------------------------- #
# (c) detect_missed_debits — INV-8 (grace boundary) + INV-10 (per-occurrence key)
# --------------------------------------------------------------------------- #
def _missed(
    next_expected: date,
    *,
    merchant: str = "Gym",
    key: str = "gym",
    amount_minor: int = 45000,
) -> MissedDebitInput:
    return MissedDebitInput(merchant, key, amount_minor, next_expected)


def test_INV8_missed_debit_fires_at_four_days_late_not_three() -> None:
    assert _MISS_GRACE == 3
    today = date(2026, 7, 15)
    # 4 days late: next_expected + 3 = today - 1 < today -> fires.
    four_late = detect_missed_debits([_missed(today - _days(4))], today)
    # 3 days late: next_expected + 3 == today, not < today -> no alert.
    three_late = detect_missed_debits([_missed(today - _days(3))], today)
    assert len(four_late) == 1
    assert three_late == []


def test_INV10_missed_debit_key_is_per_expected_occurrence() -> None:
    today = date(2026, 7, 15)
    due = today - _days(10)
    alerts = detect_missed_debits(
        [_missed(due, merchant="Gym Co", key="gymco", amount_minor=45000)], today
    )
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.kind is AlertKind.MISSED_DEBIT
    assert alert.key == f"missed_debit:gymco:{due.isoformat()}"
    assert alert.label == "Gym Co"
    assert alert.amount_minor == 45000
    assert alert.baseline_minor == 0
    assert alert.on == due
    # A later missed occurrence (new date) is a distinct alert.
    later = today - _days(5)
    other = detect_missed_debits([_missed(later, key="gymco")], today)
    assert other[0].key == f"missed_debit:gymco:{later.isoformat()}"


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)
