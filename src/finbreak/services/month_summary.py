"""Plain-English monthly summary (FIBR-0231).

A **pure** detector ``summarise_month`` plus a thin vault-scoped
``MonthSummaryService`` that prepares its inputs — the same pure-core / service
split as ``alerts.py`` (FIBR-0172) and ``reconcile_account`` (FIBR-0177).

The detector returns **facts** — an enum verdict and integer minor units — and
never a user-facing string (INV-12). Every sentence is assembled in
``ui.month_summary``, which is a ``QObject`` and can therefore translate; this
module is deliberately translation-free, which is also what makes it testable
with no Qt context at all.

**Integer minor units only, everywhere (INV-1).** No Decimal, no float, and no
true division on money: a percentage gate is written as a cross-multiplication
(``_MATERIAL_DEN * abs(movement) >= _MATERIAL_NUM * baseline``), because the
natural ``movement / baseline`` spelling silently returns a float and defeats
the whole minor-unit discipline. The only divisions here are ``//``.

The service does everything impure: it resolves the period, builds the four
like-for-like windows (§ 4.4), reads them, drops confirmed transfers, groups the
spend rows into merchant families and chooses the cause candidate. The detector
is handed all of that already computed.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlcipher3 import dbapi2

from finbreak.models import MonthCause, MonthSummary, MonthVerdict
from finbreak.repositories.reporting import ReportingRepository
from finbreak.services.reporting import (
    MODE_CURRENT_MONTH,
    MODE_PREVIOUS_MONTH,
    MODE_SPECIFIC_MONTH,
    ReportPrefs,
    _month_bounds,
    _prev_month,
    resolve_period,
)
from finbreak.services.transactions import read_minor_unit_exponent
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.text import merchant_name, normalise_text
from finbreak.vault import Vault

# Documented default thresholds (§ 3 decision 6) — one home, so v2 can lift them
# into Settings. Each is read by the tests rather than duplicated there, so these
# are tuning values, not contract: changing one moves its test with it.
_BASELINE_MONTHS = 3  # complete prior months averaged into "your usual month"
_MATERIAL_NUM, _MATERIAL_DEN = 10, 100  # a move must be >= 10% of baseline...
_MIN_MOVE_MAJOR = 100  # ...and >= 100 major units in absolute terms
_CAUSE_NUM, _CAUSE_DEN = 60, 100  # one family "explains" a move at >= 60% of it
_MIN_ELAPSED_DAYS = 7  # a partial month says nothing until day 7

# DERIVED, not chosen: the baseline floor is exactly where the two materiality
# gates cross. Below it the absolute gate binds alone, so the relative gate is
# dead and a NORMAL verdict can absorb an arbitrarily large proportional swing.
_MIN_MONTH_BASELINE_MAJOR = _MIN_MOVE_MAJOR * _MATERIAL_DEN // _MATERIAL_NUM

# The mode gate is an ALLOW-list (§ 3 decision 1). A deny-list ("not a year
# mode") would summarise an unrecognised token, which ``resolve_period`` silently
# treats as previous-month — defensible for a tile, not for a sentence.
_MONTH_MODES = (MODE_PREVIOUS_MONTH, MODE_CURRENT_MONTH, MODE_SPECIFIC_MONTH)

# _BASELINE_MONTHS and _MIN_MONTH_BASELINE_MAJOR are deliberately NOT imported
# from alerts.py, which defines a _SPIKE_WINDOW of 3 and its own
# _MIN_BASELINE_MAJOR. The floors are not the same quantity — alerts.py floors
# ONE category's three-month average, this one floors a whole month's spend — so
# they must not share a symbol even while they happen to share a value.


def _minor(major: int, exponent: int) -> int:
    """Scale a major-unit threshold to minor units. Not named ``floor``: it
    scales, it does not round. ``services.transactions.to_minor`` does this job
    for a Decimal and is deliberately not reused — INV-1 forbids Decimal here."""
    return major * 10**exponent


def _baseline_mean(total: int) -> int:
    """The integer round-half-up mean over ``_BASELINE_MONTHS``, the same idiom
    ``detect_category_spikes`` uses so the two features round identically.

    **The divisor is always ``_BASELINE_MONTHS``** — for a whole month's spend
    (which § 4.8 condition 1 has already guaranteed is three real months) and for
    a merchant family alike. A baseline window in which a family did not appear
    contributes 0 to its own mean: the user genuinely did not pay that merchant.
    Dividing by the number of windows the family *appeared* in would give a
    family seen once at R900 a mean of 900 rather than 300."""
    return (total + _BASELINE_MONTHS // 2) // _BASELINE_MONTHS


@dataclass(frozen=True)
class MonthSummaryInput:
    """One month's prepared figures — an intra-service detector input, exactly
    like ``alerts.py``'s ``CategorySpikeInput``.

    ``prior_minor`` carries one entry per baseline month that held **at least one
    non-transfer spend row in its own window**, so ``len(prior_minor) <
    _BASELINE_MONTHS`` *is* the has-data test, and every entry is strictly
    positive. A month with no spend rows is **missing data, not a zero-spend
    month** (§ 4.8 condition 1). ``candidate`` is the greatest-excess merchant
    family, already chosen — the detector cannot choose it, which is why INV-7
    is a service-level invariant."""

    month: str
    partial: bool
    days: int
    show_year: bool
    spend_minor: int
    prior_minor: tuple[int, ...]
    started: bool
    candidate: MonthCause | None


def summarise_month(item: MonthSummaryInput, exponent: int) -> MonthSummary | None:
    """The month's verdict, cause and correction — or ``None`` for silence.

    Silence is a valid and frequently correct output: the five § 4.8 conditions
    below are each a case where the vault cannot support a comparison, and the
    strip is then **absent, not vague**. They are evaluated in the spec's order.
    """
    if len(item.prior_minor) < _BASELINE_MONTHS:
        return None  # (1) "your usual month" is a claim about three months
    baseline = _baseline_mean(sum(item.prior_minor))
    if baseline < _minor(_MIN_MONTH_BASELINE_MAJOR, exponent):
        return None  # (2) too little money moving to characterise
    if item.partial and item.days < _MIN_ELAPSED_DAYS:
        return None  # (3) six days against six days is epistemically worthless
    if not item.started:
        return None  # (4) M's first day is after today — a post-dated row
    if item.spend_minor == 0:
        return None  # (5) M held no non-transfer spend row in its window

    movement = item.spend_minor - baseline
    move_floor = _minor(_MIN_MOVE_MAJOR, exponent)
    # Written as a conjunction even though the relative gate is the one that
    # binds above the § 4.8 floor (relative-pass implies absolute-pass at every
    # exponent), so that lowering the floor cannot silently re-open the dead zone
    # the floor was derived to close.
    material = (
        _MATERIAL_DEN * abs(movement) >= _MATERIAL_NUM * baseline
        and abs(movement) >= move_floor
    )
    if not material:
        verdict = MonthVerdict.NORMAL
    elif movement > 0:
        verdict = MonthVerdict.HIGHER
    else:
        verdict = MonthVerdict.LOWER

    # A single large EXPENSE cannot explain spending less, and the transaction
    # that would explain a LOWER month is the one that is absent — unobservable
    # by construction (INV-8).
    cause: MonthCause | None = None
    if verdict is MonthVerdict.HIGHER and item.candidate is not None:
        excess = item.candidate.excess_minor
        if excess > 0 and _CAUSE_DEN * excess >= _CAUSE_NUM * movement:
            cause = item.candidate

    # The DETECTOR owns slot 3's materiality floor, exactly as it owns slot 2's
    # gate: ``residual_minor is not None`` is the strip's whole render condition,
    # so the strip never evaluates a threshold (§ 4.6).
    residual_minor: int | None = None
    if cause is not None:
        residual = movement - cause.excess_minor
        if abs(residual) >= move_floor:
            residual_minor = residual

    return MonthSummary(
        month=item.month,
        partial=item.partial,
        days=item.days,
        exponent=exponent,
        show_year=item.show_year,
        verdict=verdict,
        spend_minor=item.spend_minor,
        baseline_minor=baseline,
        movement_minor=movement,
        cause=cause,
        residual_minor=residual_minor,
    )


class _Family:
    """One merchant family's running totals inside a single window. ``anchor`` is
    the ``(occurred_on, id)`` of its earliest row, which supplies the display
    name — a fixed rule, so the label cannot change between two refreshes of the
    same data (§ 4.6)."""

    __slots__ = ("total", "anchor", "name")

    def __init__(self, total: int, anchor: tuple[str, int], name: str) -> None:
        self.total = total
        self.anchor = anchor
        self.name = name


# One window's spend rows: (id, occurred_on, positive magnitude, description).
_SpendRow = tuple[int, str, int, str]


class MonthSummaryService:
    """Vault-scoped preparer for ``summarise_month``. Mirrors ``AlertService`` /
    ``ReportingService``: a ``_conn`` property, all reads, no commit.

    ``VaultLockedError`` is **not** caught here (INV-13): catching it would
    produce a summary computed from the rows this managed to read — a sentence
    about a fraction of the month, presented as the month."""

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    @property
    def _conn(self) -> dbapi2.Connection:
        return self._vault.connection

    def summary(
        self,
        prefs: ReportPrefs,
        account_ids: frozenset[int] | None,
        today: date,
    ) -> MonthSummary | None:
        """The summarised month, or ``None`` when the strip must stay silent.

        ``today`` is required rather than defaulted — unlike ``ReportingService``,
        whose ``today: date | None = None`` predates this contract — because the
        strip and the tiles must not straddle midnight (INV-10)."""
        if prefs.mode not in _MONTH_MODES:
            return None
        if prefs.mode == MODE_SPECIFIC_MONTH and (
            prefs.year is None or prefs.month is None
        ):
            # ``resolve_period`` would silently resolve this to previous-month
            # while the selector still reads "Specific month".
            return None

        _start, end = resolve_period(prefs, today)
        year, month = end.year, end.month
        first, last = _month_bounds(year, month)
        started = first <= today
        partial = started and today <= last

        # M first, then its three baseline months (newest first).
        months = [(year, month)]
        cursor = (year, month)
        for _ in range(_BASELINE_MONTHS):
            cursor = _prev_month(*cursor)
            months.append(cursor)

        lengths = [calendar.monthrange(y, m)[1] for y, m in months]
        if partial:
            # The head is capped below EVERY window month's final day, so a fixed
            # monthly payment is either inside all four windows or outside all
            # four — the bank pulls a day-30 debit order back to February's 28th
            # (§ 4.4). The consequence is that the window stops advancing near
            # month end, which the "so far" phrasing reports honestly.
            days = min(today.day, min(lengths) - 1)
            head: int | None = days
        else:
            # A COMPLETE month is compared whole against whole months: the four
            # windows are deliberately of unequal length. Truncating them to a
            # common day count manufactures a false verdict AND a false named
            # cause every February for any user with a month-end debit order
            # (§ 4.4, § 8 alternative 6).
            days = lengths[0]
            head = None

        excluded = TransferDetectionService(self._vault).confirmed_transfer_txn_ids()
        repo = ReportingRepository(self._conn)
        windows = [
            self._spend_rows(repo, y, m, head, account_ids, excluded) for y, m in months
        ]

        spend_minor = sum(magnitude for _id, _on, magnitude, _desc in windows[0])
        # Only baseline months that HELD a spend row; a month with none is a gap.
        prior_minor = tuple(
            sum(magnitude for _id, _on, magnitude, _desc in window)
            for window in windows[1:]
            if window
        )

        item = MonthSummaryInput(
            month=f"{year:04d}-{month:02d}",
            partial=partial,
            days=days,
            show_year=year != today.year,
            spend_minor=spend_minor,
            prior_minor=prior_minor,
            started=started,
            candidate=self._candidate(windows[0], windows[1:]),
        )
        return summarise_month(item, read_minor_unit_exponent(self._conn))

    def _spend_rows(
        self,
        repo: ReportingRepository,
        year: int,
        month: int,
        head: int | None,
        account_ids: frozenset[int] | None,
        excluded: set[int],
    ) -> list[_SpendRow]:
        """One window's non-transfer **spend** rows, as positive magnitudes.

        ``drill_rows_in_range`` — not ``rows_in_range`` — for **every** window,
        M's and each baseline's alike: the cause needs per-family sums on both
        sides of the subtraction, and ``rows_in_range`` carries no
        ``description``. Reading the baselines without it would make every
        family's baseline zero, collapsing ``excess`` to gross spend and silently
        restoring the largest-row rule § 2.2 exists to reject (§ 4.5).

        A row that is not spend is not a family member either: positive rows are
        never netted against a family, so a refund does not cancel a charge and
        the strip's total stays equal to the Net tile's (INV-10)."""
        start, end = _month_bounds(year, month)
        if head is not None:
            end = date(year, month, head)
        return [
            (row_id, occurred_on, -amount_minor, description)
            for row_id, occurred_on, amount_minor, _category, description in (
                repo.drill_rows_in_range(
                    start.isoformat(), end.isoformat(), account_ids
                )
            )
            if row_id not in excluded and amount_minor < 0
        ]

    def _candidate(
        self, current: list[_SpendRow], baselines: list[list[_SpendRow]]
    ) -> MonthCause | None:
        """The merchant family with the greatest **excess over its own baseline**
        — never the largest single row (INV-7).

        Ties resolve to the lexicographically smaller ``merchant_key``, so the
        sentence is stable across refreshes; iterating the keys in sorted order
        with a strict ``>`` is what delivers that."""
        families = self._group(current)
        prior: dict[str, int] = {}
        for window in baselines:
            for _id, _on, magnitude, description in window:
                prior[self._key(description)] = (
                    prior.get(self._key(description), 0) + magnitude
                )

        best: MonthCause | None = None
        best_excess = 0
        for key in sorted(families):
            family = families[key]
            excess = family.total - _baseline_mean(prior.get(key, 0))
            if excess > best_excess:
                best_excess = excess
                best = MonthCause(
                    merchant_key=key, name=family.name, excess_minor=excess
                )
        return best

    @staticmethod
    def _key(description: str) -> str:
        """The grouping key ``RecurringService`` already uses. That service keys
        on ``(direction, merchant_key)`` because it groups inflows and outflows
        alike; every row here is an outflow, so the direction component is
        constant and the key reduces to the merchant half (§ 4.5)."""
        return normalise_text(merchant_name(description))

    def _group(self, rows: list[_SpendRow]) -> dict[str, _Family]:
        families: dict[str, _Family] = {}
        for row_id, occurred_on, magnitude, description in rows:
            key = self._key(description)
            anchor = (occurred_on, row_id)
            family = families.get(key)
            if family is None:
                families[key] = _Family(magnitude, anchor, merchant_name(description))
                continue
            family.total += magnitude
            if anchor < family.anchor:
                family.anchor = anchor
                family.name = merchant_name(description)
        return families
