"""ReportingService + the pure period model (FIBR-0012).

The dashboard reads and aggregates the already-encrypted vault — it never writes
a transaction. Three parts:

* `ReportPrefs` + the five `MODE_*` tokens — the persisted period selection (D2).
  Co-located with the period resolver that consumes it (unlike the flat
  `AmountPrefs` / `DateTimePrefs` in `auth.py`, this drives a non-trivial period
  model that belongs beside `resolve_period`). `AuthService` imports `ReportPrefs`
  from here (acyclic: this module never imports `auth.py`).
* `resolve_period` / `resolve_trend_months` — **pure**, with `today` injected so
  the tests are hermetic (the `datetime_format.py` precedent). Month arithmetic is
  stdlib `calendar.monthrange` only — no new dependency (D3).
* `ReportingService` — the vault-scoped aggregator (D4): `summary`,
  `spending_by_category`, `monthly_trend`, `base_currency`, `transaction_count`.
  It builds the transfer-exclusion set once per call and drops those ids from
  every figure (INV-1). All arithmetic is on integer `amount_minor`; the only
  crossing to `Decimal` is the display scaling reused from `TransactionService`.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlcipher3 import dbapi2

from finbreak.models import CategorySpend, MonthlyTotal, Summary
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.reporting import ReportingRepository
from finbreak.repositories.settings import SettingsRepository
from finbreak.services.transactions import read_minor_unit_exponent, to_display_decimal
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.vault import Vault

# The five period modes. The token is the stored, non-translated value (D2).
MODE_PREVIOUS_MONTH = "previous_month"
MODE_CURRENT_MONTH = "current_month"
MODE_SPECIFIC_MONTH = "specific_month"
MODE_YEAR_TO_DATE = "year_to_date"
MODE_SPECIFIC_YEAR = "specific_year"


@dataclass(frozen=True)
class ReportPrefs:
    """The persisted dashboard period selection (D2). ``year`` / ``month`` are set
    only for the two *specific* modes; ``None`` for the three relative modes.
    Frozen: the resolver reads but never mutates it. Persisted by ``AuthService``
    across three ``settings`` keys, each parsed defensively (INV-2)."""

    mode: str
    year: int | None = None
    month: int | None = None


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """The first and last calendar day of ``year``-``month`` (leap-aware via
    ``calendar.monthrange``, so Feb is 28 or 29 correctly)."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _prev_month(year: int, month: int) -> tuple[int, int]:
    """The calendar month before ``year``-``month`` (crosses the year boundary)."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


def resolve_period(prefs: ReportPrefs, today: date) -> tuple[date, date]:
    """Map a ``ReportPrefs`` to its inclusive ``[start, end]`` range (INV-3).

    Total over every mode, so it never raises: an unknown mode — **or** a specific
    mode whose required ``year`` / ``month`` is missing — falls through to the
    previous-month default (the last line of defence behind the D2 pref-parse
    downgrade, which already guarantees ``report_prefs`` won't yield a specific mode
    with a missing field). The per-branch ``is not None`` checks also narrow the
    optionals for the type checker.
    """
    if prefs.mode == MODE_CURRENT_MONTH:
        return _month_bounds(today.year, today.month)
    if (
        prefs.mode == MODE_SPECIFIC_MONTH
        and prefs.year is not None
        and prefs.month is not None
    ):
        return _month_bounds(prefs.year, prefs.month)
    if prefs.mode == MODE_YEAR_TO_DATE:
        return date(today.year, 1, 1), today
    if prefs.mode == MODE_SPECIFIC_YEAR and prefs.year is not None:
        return date(prefs.year, 1, 1), date(prefs.year, 12, 31)
    # MODE_PREVIOUS_MONTH, an unrecognised mode, or a specific mode missing a field.
    year, month = _prev_month(today.year, today.month)
    return _month_bounds(year, month)


def resolve_trend_months(prefs: ReportPrefs, today: date) -> list[tuple[int, int]]:
    """The 12 ``(year, month)`` pairs ending at the period's end month, oldest
    first (INV-6). specific-year → that year's Jan..Dec; year-to-date in July →
    Aug(prev)..July; previous-month in January → the prior calendar year."""
    _, end = resolve_period(prefs, today)
    months: list[tuple[int, int]] = []
    year, month = end.year, end.month
    for _ in range(12):
        months.append((year, month))
        year, month = _prev_month(year, month)
    months.reverse()
    return months


class ReportingService:
    """Vault-scoped read-only aggregator (D4). Mirrors ``CategorizationService`` /
    ``TransferDetectionService``: a ``_conn`` property, all reads, no commit."""

    def __init__(self, vault: Vault):
        self._vault = vault

    @property
    def _conn(self) -> dbapi2.Connection:
        return self._vault.connection

    def base_currency(self) -> str:
        """The display symbol the tiles format with (the same ``settings`` seam
        ``TransactionService.base_currency`` reads)."""
        from typing import cast

        value = SettingsRepository(self._conn).get("base_currency")
        return cast(str, value)

    def transaction_count(self) -> int:
        """A live, whole-vault ``count(*)`` (unfiltered). The getting-started toggle
        (INV-7) and the status-bar figure (INV-14) both read it, so the count is
        never a cached list gone stale."""
        return self._conn.execute("SELECT count(*) FROM transactions").fetchone()[0]

    def _excluded(self) -> set[int]:
        """The confirmed-transfer txn ids to drop from every figure (INV-1)."""
        return TransferDetectionService(self._vault).confirmed_transfer_txn_ids()

    def summary(
        self, prefs: ReportPrefs, account_id: int | None, today: date | None = None
    ) -> Summary:
        """Income / expenditure / net over the period's non-transfer rows (INV-4).
        All arithmetic on integer ``amount_minor``; only the returned ``Decimal``s
        cross to display scaling (INV-13)."""
        today = today or date.today()
        start, end = resolve_period(prefs, today)
        excluded = self._excluded()
        income_minor = 0
        expenditure_minor = 0
        for txn_id, _occurred, amount_minor, _cat in ReportingRepository(
            self._conn
        ).rows_in_range(start.isoformat(), end.isoformat(), account_id):
            if txn_id in excluded:
                continue
            if amount_minor > 0:
                income_minor += amount_minor
            else:
                expenditure_minor += -amount_minor
        exponent = read_minor_unit_exponent(self._conn)
        income = to_display_decimal(income_minor, exponent)
        expenditure = to_display_decimal(expenditure_minor, exponent)
        net = to_display_decimal(income_minor - expenditure_minor, exponent)
        return Summary(income=income, expenditure=expenditure, net=net)

    def spending_by_category(
        self, prefs: ReportPrefs, account_id: int | None, today: date | None = None
    ) -> list[CategorySpend]:
        """The category donut feed: expenditure (negative, non-transfer) rows
        grouped by ``category_id`` (INV-5). Categorised buckets sorted
        ``(magnitude desc, category_id asc)``; the ``None`` (Uncategorised) bucket
        is **appended last**, so the sort key never compares ``None``. Returns the
        full uncapped list — the ≤8-wedge cap + Other collapse is a UI-render step
        (D9)."""
        today = today or date.today()
        start, end = resolve_period(prefs, today)
        excluded = self._excluded()
        by_id: dict[int | None, int] = {}
        for txn_id, _occurred, amount_minor, category_id in ReportingRepository(
            self._conn
        ).rows_in_range(start.isoformat(), end.isoformat(), account_id):
            if txn_id in excluded or amount_minor >= 0:
                continue
            by_id[category_id] = by_id.get(category_id, 0) + -amount_minor
        # Resolve leaf names once (grouping is by id, so two same-named leaves under
        # different parents stay distinct). A deleted category resets its rows to
        # NULL (FIBR-0010 INV-7), so no live category_id is ever an orphan here.
        names = {c.id: c.name for c in CategoryRepository(self._conn).list_all()}
        exponent = read_minor_unit_exponent(self._conn)
        categorised = sorted(
            ((cat_id, minor) for cat_id, minor in by_id.items() if cat_id is not None),
            key=lambda pair: (-pair[1], pair[0]),
        )
        result = [
            CategorySpend(
                category_id=cat_id,
                name=names.get(cat_id, ""),
                amount=to_display_decimal(minor, exponent),
            )
            for cat_id, minor in categorised
        ]
        if None in by_id:
            # The Uncategorised bucket: name is the "" sentinel (the UI renders
            # tr("Uncategorised") — a non-QObject service can't translate), id None.
            result.append(
                CategorySpend(
                    category_id=None,
                    name="",
                    amount=to_display_decimal(by_id[None], exponent),
                )
            )
        return result

    def monthly_trend(
        self, prefs: ReportPrefs, account_id: int | None, today: date | None = None
    ) -> list[MonthlyTotal]:
        """Exactly 12 ``(month, income, expenditure)`` points, oldest first, ending
        at the period's end month; an empty month is a **zero** point, not omitted
        (INV-6). Buckets whole calendar months by ``occurred_on[:7]``."""
        today = today or date.today()
        months = resolve_trend_months(prefs, today)
        start, _ = _month_bounds(*months[0])
        _, end = _month_bounds(*months[-1])
        excluded = self._excluded()
        income_by_month: dict[str, int] = {}
        expenditure_by_month: dict[str, int] = {}
        for txn_id, occurred_on, amount_minor, _cat in ReportingRepository(
            self._conn
        ).rows_in_range(start.isoformat(), end.isoformat(), account_id):
            if txn_id in excluded:
                continue
            key = occurred_on[:7]
            if amount_minor > 0:
                income_by_month[key] = income_by_month.get(key, 0) + amount_minor
            else:
                expenditure_by_month[key] = (
                    expenditure_by_month.get(key, 0) + -amount_minor
                )
        exponent = read_minor_unit_exponent(self._conn)
        result: list[MonthlyTotal] = []
        for year, month in months:
            key = f"{year:04d}-{month:02d}"
            result.append(
                MonthlyTotal(
                    label=key,
                    income=to_display_decimal(income_by_month.get(key, 0), exponent),
                    expenditure=to_display_decimal(
                        expenditure_by_month.get(key, 0), exponent
                    ),
                )
            )
        return result
