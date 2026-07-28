"""Spending alerts (FIBR-0172).

Three **pure** detectors + a thin composing ``AlertService``, the same pure-core /
service split as FIBR-0171 (``project_forecast``) and FIBR-0177 (``reconcile_account``).

Each detector is clock-free where it can be, **integer minor units only — no
``Decimal``, no float** (INV-15), and takes a list of prepared integer inputs (§ 3),
returning ``list[SpendingAlert]`` — it owns the alert's ``key`` + payload so the keys
are pure and testable without a DB. ``AlertService`` does everything impure: it
prepares each detector's inputs (the single ``Decimal → minor`` step happens here,
via the shared ``to_minor`` helper — D7), calls the detectors, concatenates,
applies the deterministic order (D1),
and filters out dismissed alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlcipher3 import dbapi2

from finbreak.models import AlertKind, Direction, RecurringItem, SpendingAlert
from finbreak.repositories.alert_dismissals import AlertDismissalRepository
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.reporting import ReportingRepository
from finbreak.services.recurring import RecurringService
from finbreak.services.reporting import _month_bounds, _prev_month
from finbreak.services.transactions import read_minor_unit_exponent, to_minor
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.vault import Vault

# Documented default thresholds (D10) — one home so v2 can lift them into Settings.
# Each is cited in the INV tests, so a change is a conscious, test-visible edit.
_NEW_MAX_OCCURRENCES = 4  # a stream with <= this many occurrences is "new" (D2)
_SPIKE_FACTOR = 2  # >= 2x the recent average is a spike (D3)
_SPIKE_WINDOW = 3  # prior complete months averaged (D3)
_MIN_BASELINE_MAJOR = 50  # ~50 major units — a floor suppressing trivial-cat noise
_MISS_GRACE = 3  # days — a debit <= 3 days late isn't flagged; fires at 4+ (D4)

# Deterministic urgency-then-size order (D1/INV-19): a missed payment is the most
# actionable, a spike the most FYI.
_KIND_ORDER = {
    AlertKind.MISSED_DEBIT: 0,
    AlertKind.NEW_RECURRING: 1,
    AlertKind.CATEGORY_SPIKE: 2,
}


@dataclass
class NewRecurringInput:
    """(a) — one detected-but-undecided OUT recurring stream (FIBR-0172 § 3). Decimal-
    free: ``amount_minor`` is the positive charge magnitude; ``occurrences`` gates the
    "just became recurring" test (D2)."""

    merchant: str
    merchant_key: str
    amount_minor: int
    occurrences: int


@dataclass
class CategorySpikeInput:
    """(b) — one spending category's monthly series (FIBR-0172 § 3). ``current_minor``
    is the last-complete-month OUT spend (transfer-excluded); ``prior_minor`` the
    ``_SPIKE_WINDOW`` prior months' spend, integer minor units throughout (D3)."""

    category_id: int
    category_name: str
    current_minor: int
    prior_minor: tuple[int, ...]


@dataclass
class MissedDebitInput:
    """(c) — one confirmed OUT recurring stream (FIBR-0172 § 3). ``amount_minor`` the
    positive expected charge; ``next_expected`` the due date ``detect_missed_debits``
    compares (+ grace) against ``today`` (D4)."""

    merchant: str
    merchant_key: str
    amount_minor: int
    next_expected: date


def detect_new_recurring(items: list[NewRecurringInput]) -> list[SpendingAlert]:
    """(a) A new-recurring alert for each stream that has only recently crossed the
    detection threshold — ``occurrences <= _NEW_MAX_OCCURRENCES`` (D2, cadence-
    agnostic; a just-detected stream has ``occurrences == 3``). Key
    ``new_recurring:{merchant_key}`` (permanent per stream, D5); payload is the
    positive charge magnitude, ``baseline_minor = 0``, ``on = None`` (INV-1/INV-3)."""
    alerts: list[SpendingAlert] = []
    for item in items:
        if item.occurrences <= _NEW_MAX_OCCURRENCES:
            alerts.append(
                SpendingAlert(
                    kind=AlertKind.NEW_RECURRING,
                    key=f"new_recurring:{item.merchant_key}",
                    label=item.merchant,
                    amount_minor=item.amount_minor,
                    baseline_minor=0,
                    on=None,
                )
            )
    return alerts


def detect_category_spikes(
    items: list[CategorySpikeInput], month: str, min_baseline: int
) -> list[SpendingAlert]:
    """(b) A category-spike alert iff ``current_minor >= _SPIKE_FACTOR * average``
    **and** ``average >= min_baseline`` (D3), where ``average`` is the integer round-
    half-up mean of ``prior_minor`` — ``(sum(prior) + K // 2) // K`` — computed with
    integer arithmetic only (no Decimal/float, INV-15). Empty ``prior_minor`` ⇒ no
    alert (nothing to average). Key ``category_spike:{category_id}:{month}`` (per
    category per month, D5); payload carries the average in ``baseline_minor``,
    ``on = None`` (INV-6/INV-7/INV-15)."""
    alerts: list[SpendingAlert] = []
    for item in items:
        k = len(item.prior_minor)
        if k == 0:
            continue
        average = (sum(item.prior_minor) + k // 2) // k
        if item.current_minor >= _SPIKE_FACTOR * average and average >= min_baseline:
            alerts.append(
                SpendingAlert(
                    kind=AlertKind.CATEGORY_SPIKE,
                    key=f"category_spike:{item.category_id}:{month}",
                    label=item.category_name,
                    amount_minor=item.current_minor,
                    baseline_minor=average,
                    on=None,
                )
            )
    return alerts


def detect_missed_debits(
    items: list[MissedDebitInput], today: date
) -> list[SpendingAlert]:
    """(c) A missed-debit alert for each confirmed stream overdue past grace —
    ``next_expected + _MISS_GRACE days < today`` (D4; fires at 4+ days late). Key
    ``missed_debit:{merchant_key}:{next_expected ISO}`` (per expected occurrence, D5);
    payload is the positive charge magnitude, ``baseline_minor = 0``, ``on =
    next_expected`` (INV-8/INV-10)."""
    alerts: list[SpendingAlert] = []
    for item in items:
        if item.next_expected + timedelta(days=_MISS_GRACE) < today:
            alerts.append(
                SpendingAlert(
                    kind=AlertKind.MISSED_DEBIT,
                    key=f"missed_debit:{item.merchant_key}:{item.next_expected.isoformat()}",
                    label=item.merchant,
                    amount_minor=item.amount_minor,
                    baseline_minor=0,
                    on=item.next_expected,
                )
            )
    return alerts


class AlertService:
    """Compose the dashboard spending alerts over a vault (FIBR-0172 D1/Deliverable 4).

    Prepares each pure detector's integer-minor inputs — the FIBR-0142 recurring
    snapshot (one call, D2/D4), the FIBR-0012 per-category monthly series with the
    ``ReportingService`` transfer-exclusion set (D3), and the single Decimal→minor
    conversion (D7, the shared ``to_minor``) — calls the three detectors,
    concatenates, applies the fixed urgency-then-size order (D1/INV-19), and
    filters out dismissed keys (D5). Mirrors
    ``ForecastService`` — vault-wide, ``account_ids=None`` (INV-5)."""

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    @property
    def _conn(self) -> dbapi2.Connection:
        return self._vault.connection

    def alerts(self, today: date) -> list[SpendingAlert]:
        """The ordered, dismissal-filtered alert list for ``today`` (D1/D8/INV-16/19).
        Clock-injected: same inputs + ``today`` → same list."""
        exponent = read_minor_unit_exponent(self._conn)
        # One recurring detection pass drives both (a) and (c) (D2/D4).
        suggested, confirmed, _summary = RecurringService(self._vault).snapshot(today)
        new = detect_new_recurring(self._new_inputs(suggested, exponent))
        month, spike_inputs = self._spike_inputs(today)
        min_baseline = _MIN_BASELINE_MAJOR * (10**exponent)
        spikes = detect_category_spikes(spike_inputs, month, min_baseline)
        missed = detect_missed_debits(self._missed_inputs(confirmed, exponent), today)
        combined = new + spikes + missed
        # Stable sort over the detectors' deterministic order (D1/INV-19).
        combined.sort(key=lambda a: (_KIND_ORDER[a.kind], -a.amount_minor, a.label))
        dismissed = AlertDismissalRepository(self._conn).dismissed_keys()
        return [alert for alert in combined if alert.key not in dismissed]

    def dismiss(self, alert_key: str) -> None:
        """Persist a dismissal (D5) — the repository's idempotent upsert."""
        AlertDismissalRepository(self._conn).dismiss(alert_key)

    # -- input prep (the impure half) ----------------------------------------- #
    @staticmethod
    def _new_inputs(
        suggested: list[RecurringItem], exponent: int
    ) -> list[NewRecurringInput]:
        """(a) one input per SUGGESTED (undecided) OUT stream (D2)."""
        return [
            NewRecurringInput(
                merchant=item.merchant,
                merchant_key=item.merchant_key,
                amount_minor=to_minor(item.amount, exponent),
                occurrences=item.occurrences,
            )
            for item in suggested
            if item.direction is Direction.OUT
        ]

    @staticmethod
    def _missed_inputs(
        confirmed: list[RecurringItem], exponent: int
    ) -> list[MissedDebitInput]:
        """(c) one input per CONFIRMED OUT stream (D4). The recurring activeness
        filter already dropped long-dead streams, bounding the upper end (§ 6)."""
        return [
            MissedDebitInput(
                merchant=item.merchant,
                merchant_key=item.merchant_key,
                amount_minor=to_minor(item.amount, exponent),
                next_expected=item.next_expected,
            )
            for item in confirmed
            if item.direction is Direction.OUT
        ]

    def _spike_inputs(self, today: date) -> tuple[str, list[CategorySpikeInput]]:
        """(b) the per-category OUT-spend series over the 4-month window (D3): the
        last COMPLETE month (``_prev_month(today)`` — reused so the year boundary is
        handled) plus the ``_SPIKE_WINDOW`` complete months before it. Buckets by
        ``category_id`` exactly as ``spending_by_category`` does — summing OUT
        magnitudes, excluding confirmed transfers (the ``_excluded()`` set) and the
        ``None`` (uncategorised) bucket — over the vault-wide (``account_ids=None``)
        rows (INV-4/INV-5). Returns ``(current_month_str, inputs)``."""
        cur_year, cur_month = _prev_month(today.year, today.month)
        month = f"{cur_year:04d}-{cur_month:02d}"
        # months = 3 priors (oldest-first) + the current complete month (last).
        priors: list[tuple[int, int]] = []
        year, mon = cur_year, cur_month
        for _ in range(_SPIKE_WINDOW):
            year, mon = _prev_month(year, mon)
            priors.append((year, mon))
        priors.reverse()
        window = priors + [(cur_year, cur_month)]

        excluded = TransferDetectionService(self._vault).confirmed_transfer_txn_ids()
        repo = ReportingRepository(self._conn)
        # per (year, month) -> {category_id -> summed OUT magnitude}
        totals: dict[tuple[int, int], dict[int, int]] = {}
        for ym in window:
            start, end = _month_bounds(*ym)
            bucket: dict[int, int] = {}
            for txn_id, _occurred, amount_minor, category_id in repo.rows_in_range(
                start.isoformat(), end.isoformat(), None
            ):
                if txn_id in excluded or amount_minor >= 0 or category_id is None:
                    continue
                bucket[category_id] = bucket.get(category_id, 0) + -amount_minor
            totals[ym] = bucket

        names = {c.id: c.name for c in CategoryRepository(self._conn).list_all()}
        current = totals[(cur_year, cur_month)]
        category_ids: set[int] = set()
        for bucket in totals.values():
            category_ids.update(bucket)
        inputs = [
            CategorySpikeInput(
                category_id=cid,
                category_name=names.get(cid, ""),
                current_minor=current.get(cid, 0),
                prior_minor=tuple(totals[ym].get(cid, 0) for ym in priors),
            )
            for cid in sorted(category_ids)
        ]
        return month, inputs
