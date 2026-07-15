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

from sqlcipher3 import dbapi2

from finbreak.models import Cadence, Direction, RecurringItem, RecurringSummary
from finbreak.repositories.recurring import RecurringRepository, _RecurRow
from finbreak.services.transactions import read_minor_unit_exponent, to_display_decimal
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.text import merchant_name, normalise_text
from finbreak.vault import Vault

# Stored recurring_decisions statuses (INV-8). The repository takes/returns these
# as plain strings; the service is their one producer.
_CONFIRMED = "confirmed"
_DISMISSED = "dismissed"

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


class RecurringService:
    """The suggest-then-confirm recurring engine (FIBR-0142).

    Wraps the pure ``detect_recurring`` with the vault's minor-unit exponent and the
    confirmed-transfer exclusion set (INV-3), then partitions its already-sorted
    (D10) output by the stored ``recurring_decisions``: **suggested** = detected &
    undecided, **confirmed** = detected & confirmed, **dismissed** = hidden from both
    (INV-8/D9). Decisions key on ``(direction, merchant_key)``, so a confirm/dismiss
    outlives the specific transactions that formed the group (INV-9). Never touches a
    ``transactions`` row.
    """

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    @property
    def _conn(self) -> dbapi2.Connection:
        return self._vault.connection

    def _recurring(self) -> RecurringRepository:
        return RecurringRepository(self._conn)

    # -- reads (each partitions ONE detection pass) ---------------------------
    def snapshot(
        self, today: date
    ) -> tuple[list[RecurringItem], list[RecurringItem], RecurringSummary]:
        """One detection pass → ``(suggested, confirmed, summary)`` (D9 perf) — the
        widget's refresh path. ``candidates``/``confirmed``/``summary`` are thin
        single-value wrappers over this."""
        repo = self._recurring()
        exponent = read_minor_unit_exponent(self._conn)
        excluded = frozenset(
            TransferDetectionService(self._vault).confirmed_transfer_txn_ids()
        )
        detected = detect_recurring(repo.recurring_rows(), today, exponent, excluded)
        decisions = repo.decisions()
        suggested: list[RecurringItem] = []
        confirmed: list[RecurringItem] = []
        for item in detected:  # detector order preserved within each partition
            status = decisions.get((item.direction.value, item.merchant_key))
            if status is None:
                suggested.append(item)
            elif status == _CONFIRMED:
                confirmed.append(item)
            # _DISMISSED → shown in neither list
        return suggested, confirmed, self._summarise(confirmed, exponent)

    def candidates(self, today: date) -> list[RecurringItem]:
        """The Suggested list — detected but undecided."""
        return self.snapshot(today)[0]

    def confirmed(self, today: date) -> list[RecurringItem]:
        """The Confirmed list — a confirmed decision that still detects today."""
        return self.snapshot(today)[1]

    def summary(self, today: date) -> RecurringSummary:
        """The per-month totals over ``confirmed(today)`` (for the FIBR-0143 card)."""
        return self.snapshot(today)[2]

    # -- decisions (each write is one repository commit) ----------------------
    def confirm(self, direction: Direction, merchant_key: str) -> None:
        self._recurring().set_decision(direction.value, merchant_key, _CONFIRMED)

    def dismiss(self, direction: Direction, merchant_key: str) -> None:
        self._recurring().set_decision(direction.value, merchant_key, _DISMISSED)

    def reset(self, direction: Direction, merchant_key: str) -> None:
        self._recurring().clear_decision(direction.value, merchant_key)

    # -- helpers --------------------------------------------------------------
    def _summarise(
        self, confirmed: list[RecurringItem], exponent: int
    ) -> RecurringSummary:
        """Sum the confirmed items' already-quantized ``monthly_equivalent``s by
        direction (INV-1: the rows a user sees add up to the shown total); ``net =
        in − out``. The empty sum is a zero at the currency's scale."""
        zero = Decimal(0).scaleb(-exponent)
        monthly_in = sum(
            (it.monthly_equivalent for it in confirmed if it.direction is Direction.IN),
            zero,
        )
        monthly_out = sum(
            (
                it.monthly_equivalent
                for it in confirmed
                if it.direction is Direction.OUT
            ),
            zero,
        )
        return RecurringSummary(monthly_in, monthly_out, monthly_in - monthly_out)
