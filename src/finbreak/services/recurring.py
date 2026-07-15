"""Recurring-money detection (FIBR-0142).

A pure ``detect_recurring`` groups transactions by ``(direction, merchant_key)``,
qualifies each group under the Balanced rule (≥3 members; every magnitude within
±10% of the integer ``median_low``; ≥2 non-zero day-gaps all in one cadence
band), and returns the *active* recurring items sorted biggest-first. It takes no
clock (``today`` is a parameter) and does no I/O. ``RecurringService`` (later
slice) persists confirm/dismiss decisions and partitions the output. No network.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from statistics import median_low
from typing import NamedTuple

from finbreak.models import Cadence, Direction, RecurringItem
from finbreak.services.transactions import to_display_decimal
from finbreak.text import merchant_name, normalise_text

_MIN_OCCURRENCES = 3
# ±10% band as an integer cross-multiply: 100·maxdev ≤ 10·med (no float).
_TOL_NUM = 10
_TOL_DEN = 100
# A group is surfaced only while a charge landed within GRACE × its nominal
# interval of ``today`` (one missed period tolerated).
_ACTIVE_GRACE = 2

_NOMINAL: dict[Cadence, int] = {
    Cadence.WEEKLY: 7,
    Cadence.FORTNIGHTLY: 14,
    Cadence.MONTHLY: 30,
    Cadence.YEARLY: 365,
}
# Non-overlapping accept bands (inclusive day-gap ranges); a gap outside every
# band is a dead zone that disqualifies the group.
_BANDS: tuple[tuple[int, int, Cadence], ...] = (
    (5, 10, Cadence.WEEKLY),
    (11, 18, Cadence.FORTNIGHTLY),
    (25, 35, Cadence.MONTHLY),
    (330, 400, Cadence.YEARLY),
)
_MONTHLY_FACTOR: dict[Cadence, Decimal] = {
    Cadence.WEEKLY: Decimal(52) / Decimal(12),
    Cadence.FORTNIGHTLY: Decimal(26) / Decimal(12),
    Cadence.MONTHLY: Decimal(1),
    Cadence.YEARLY: Decimal(1) / Decimal(12),
}


class _RecurRow(NamedTuple):
    """The lean per-transaction input the detector consumes (FIBR-0142 D2)."""

    id: int
    occurred_on: str
    amount_minor: int
    description: str


def nominal_interval_days(cadence: Cadence) -> int:
    """The nominal cadence length in days (D6 Nominal column); activeness grace."""
    return _NOMINAL[cadence]


def _add_months(d: date, months: int) -> date:
    """``d`` plus ``months`` calendar months, clamping the day to the target
    month's length (Jan 31 + 1 → Feb 28/29)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_cadence(d: date, cadence: Cadence) -> date:
    """The next expected date after ``d`` for ``cadence`` (D7) — calendar-aware for
    month/year (day-clamped), fixed-day for week/fortnight."""
    if cadence is Cadence.WEEKLY:
        return d + timedelta(days=7)
    if cadence is Cadence.FORTNIGHTLY:
        return d + timedelta(days=14)
    if cadence is Cadence.MONTHLY:
        return _add_months(d, 1)
    return _add_months(d, 12)


def _classify(gaps: list[int]) -> Cadence | None:
    """The single cadence every gap shares, or ``None`` — needs ≥2 gaps, each in a
    band, all the **same** band (FIBR-0142 INV-6c)."""
    if len(gaps) < 2:
        return None
    band: Cadence | None = None
    for gap in gaps:
        matched: Cadence | None = None
        for low, high, cadence in _BANDS:
            if low <= gap <= high:
                matched = cadence
                break
        if matched is None:
            return None
        if band is None:
            band = matched
        elif matched is not band:
            return None
    return band


def _monthly_equivalent(amount: Decimal, cadence: Cadence, exponent: int) -> Decimal:
    """``amount`` normalised to per-month by cadence (D8), quantized to the minor
    unit with ``ROUND_HALF_EVEN`` (the one pinned money-rounding op)."""
    unit = Decimal(1).scaleb(-exponent)
    return (amount * _MONTHLY_FACTOR[cadence]).quantize(unit, rounding=ROUND_HALF_EVEN)


def detect_recurring(
    rows: list[_RecurRow],
    today: date,
    exponent: int,
    excluded_ids: frozenset[int],
) -> list[RecurringItem]:
    """All active, qualifying recurring groups (both directions), sorted (D10).

    Decision-agnostic: returns every group that passes the Balanced rule and the
    activeness filter; applying user confirm/dismiss decisions is the service's
    job. ``excluded_ids`` (confirmed-transfer ids) and zero-amount rows are dropped
    before grouping.
    """
    groups: dict[tuple[Direction, str], list[_RecurRow]] = defaultdict(list)
    for row in rows:
        if row.id in excluded_ids or row.amount_minor == 0:
            continue
        direction = Direction.OUT if row.amount_minor < 0 else Direction.IN
        key = normalise_text(merchant_name(row.description))
        groups[(direction, key)].append(row)

    items: list[RecurringItem] = []
    for (direction, key), members in groups.items():
        if len(members) < _MIN_OCCURRENCES:
            continue
        magnitudes = [abs(m.amount_minor) for m in members]
        med = median_low(magnitudes)
        if _TOL_DEN * max(abs(mag - med) for mag in magnitudes) > _TOL_NUM * med:
            continue
        ordered = sorted(
            members, key=lambda m: (date.fromisoformat(m.occurred_on), m.id)
        )
        dates = [date.fromisoformat(m.occurred_on) for m in ordered]
        gaps = [
            (dates[i + 1] - dates[i]).days
            for i in range(len(dates) - 1)
            if (dates[i + 1] - dates[i]).days != 0
        ]
        cadence = _classify(gaps)
        if cadence is None:
            continue
        last_seen = dates[-1]
        if (today - last_seen).days > _ACTIVE_GRACE * nominal_interval_days(cadence):
            continue
        amount = to_display_decimal(med, exponent)
        items.append(
            RecurringItem(
                merchant=merchant_name(ordered[0].description),
                merchant_key=key,
                direction=direction,
                cadence=cadence,
                amount=amount,
                monthly_equivalent=_monthly_equivalent(amount, cadence, exponent),
                occurrences=len(members),
                first_seen=dates[0],
                last_seen=last_seen,
                next_expected=_add_cadence(last_seen, cadence),
                txn_ids=tuple(m.id for m in ordered),
            )
        )
    items.sort(
        key=lambda it: (-it.monthly_equivalent, it.merchant_key, it.direction.value)
    )
    return items
