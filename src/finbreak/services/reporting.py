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
from typing import NamedTuple

from sqlcipher3 import dbapi2

from finbreak.models import (
    Category,
    CategorySpend,
    ConfirmedTransfer,
    DrillLabels,
    DrillNode,
    MonthlyTotal,
    Summary,
)
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.reporting import ReportingRepository
from finbreak.repositories.settings import SettingsRepository
from finbreak.services.transactions import read_minor_unit_exponent, to_display_decimal
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.text import merchant_name, normalise_text
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


class _DrillRow(NamedTuple):
    """One sign-filtered row carried through the drill build (FIBR-0138 D4).
    ``magnitude_minor`` is the **positive** magnitude — Income keeps ``amount_minor``,
    Spending negates it (exactly as ``summary`` does at line 161) — so every
    downstream sum is a positive integer, and the scaled total equals the tile
    (INV-1)."""

    id: int
    occurred_on: str
    magnitude_minor: int
    category_id: int | None
    description: str


def _sorted_nodes(items: list[tuple[DrillNode, str]]) -> tuple[DrillNode, ...]:
    """INV-7 order: descending magnitude, then label ascending, then a per-node
    **uniform string** key — so a mixed category+merchant sibling list (D4a) never
    compares an ``int`` against a ``str`` (a ``TypeError``). ``items`` is
    ``(node, key)``; returns just the ordered nodes."""
    items.sort(key=lambda item: (-item[0].amount, item[0].label, item[1]))
    return tuple(node for node, _key in items)


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
        self,
        prefs: ReportPrefs,
        account_ids: frozenset[int] | None,
        today: date | None = None,
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
        ).rows_in_range(start.isoformat(), end.isoformat(), account_ids):
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
        self,
        prefs: ReportPrefs,
        account_ids: frozenset[int] | None,
        today: date | None = None,
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
        ).rows_in_range(start.isoformat(), end.isoformat(), account_ids):
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
        self,
        prefs: ReportPrefs,
        account_ids: frozenset[int] | None,
        today: date | None = None,
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
        ).rows_in_range(start.isoformat(), end.isoformat(), account_ids):
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

    def drill_down(
        self,
        prefs: ReportPrefs,
        account_ids: frozenset[int] | None,
        today: date | None = None,
        *,
        labels: DrillLabels,
    ) -> list[DrillNode]:
        """The expandable dashboard tree — exactly ``[Income, Spending, Transfers]``
        (FIBR-0138 D4). Reuses every ``summary`` primitive (``resolve_period``,
        ``_excluded``, the minor→Decimal scaling) so the Income/Spending branch
        totals **equal** the tiles (INV-1). Confirmed transfers drop out of the two
        category branches and appear only under Transfers (INV-2). Read-only; a fresh
        tree per call so a change elsewhere shows on next view (INV-3). ``labels``
        carries the four ``tr()``-ed fixed strings (this service is not a
        ``QObject``, D2/INV-9)."""
        today = today or date.today()
        start, end = resolve_period(prefs, today)
        excluded = self._excluded()
        exponent = read_minor_unit_exponent(self._conn)
        income_rows: list[_DrillRow] = []
        spending_rows: list[_DrillRow] = []
        for (
            txn_id,
            occurred_on,
            amount_minor,
            category_id,
            description,
        ) in ReportingRepository(self._conn).drill_rows_in_range(
            start.isoformat(), end.isoformat(), account_ids
        ):
            if txn_id in excluded:
                continue  # a confirmed transfer shows only under Transfers (INV-2)
            if amount_minor > 0:
                income_rows.append(
                    _DrillRow(
                        txn_id, occurred_on, amount_minor, category_id, description
                    )
                )
            else:
                spending_rows.append(
                    _DrillRow(
                        txn_id, occurred_on, -amount_minor, category_id, description
                    )
                )
        categories = CategoryRepository(self._conn).list_all()
        return [
            self._category_branch(
                labels.income, income_rows, categories, labels, exponent
            ),
            self._category_branch(
                labels.spending, spending_rows, categories, labels, exponent
            ),
            self._transfers_branch(
                labels.transfers,
                start.isoformat(),
                end.isoformat(),
                account_ids,
                exponent,
            ),
        ]

    def _category_branch(
        self,
        label: str,
        rows: list[_DrillRow],
        categories: list[Category],
        labels: DrillLabels,
        exponent: int,
    ) -> DrillNode:
        """One sign branch's category subtree (FIBR-0138 D4a) — a single "group by
        **top-of-chain**" rule so no row is ever dropped, and the branch total equals
        its tile (INV-1/INV-4). Each category node sums its own bucket plus every
        descendant's; its children are the non-empty child-category nodes **and** the
        merchant nodes for its own directly-assigned rows."""
        zero = to_display_decimal(0, exponent)
        roots = {c.id for c in categories if c.parent_id is None}
        by_id = {c.id: c for c in categories}
        children_by_parent: dict[int, list[Category]] = {}
        for cat in categories:
            if cat.parent_id is not None:
                children_by_parent.setdefault(cat.parent_id, []).append(cat)
        own_rows: dict[int | None, list[_DrillRow]] = {}
        for row in rows:
            own_rows.setdefault(row.category_id, []).append(row)

        def top_of_chain(category_id: int) -> int:
            """Climb ``parent_id`` until the parent is a root; that direct-child-of-a-
            root is the top-of-chain. Defensively total: a root (or an unknown id) is
            its own top-of-chain, and a broken chain stops — the loop never spins."""
            cat = by_id.get(category_id)
            if cat is None or cat.parent_id is None:
                return category_id
            while cat.parent_id not in roots:
                parent = by_id.get(cat.parent_id)
                if parent is None or parent.parent_id is None:
                    return cat.id
                cat = parent
            return cat.id

        def merchant_nodes(bucket: list[_DrillRow]) -> list[tuple[DrillNode, str]]:
            """The merchant nodes (D3) for one category's own rows — grouped by the
            ``normalise_text(merchant_name(...))`` key, each drilling to its individual
            transactions. The display label is the lexicographically smallest
            ``merchant_name`` in the group (deterministic, the read has no ORDER BY)."""
            groups: dict[str, list[_DrillRow]] = {}
            for row in bucket:
                groups.setdefault(
                    normalise_text(merchant_name(row.description)), []
                ).append(row)
            built: list[tuple[DrillNode, str]] = []
            for key, group in groups.items():
                display = min(merchant_name(r.description) for r in group)
                leaves = [
                    (
                        DrillNode(
                            r.occurred_on,
                            to_display_decimal(r.magnitude_minor, exponent),
                            1,
                            (),
                        ),
                        f"txn:{r.id}",
                    )
                    for r in group
                ]
                amount = sum(
                    (to_display_decimal(r.magnitude_minor, exponent) for r in group),
                    zero,
                )
                node = DrillNode(display, amount, len(group), _sorted_nodes(leaves))
                built.append((node, f"mer:{key}"))
            return built

        def category_node(category: Category) -> DrillNode | None:
            """This category's node — its children are the non-empty child-category
            nodes plus the merchant nodes for its own bucket; ``None`` if it and its
            descendants hold no rows (an empty category is omitted, INV-4/D8)."""
            child_items: list[tuple[DrillNode, str]] = []
            for child in children_by_parent.get(category.id, []):
                node = category_node(child)
                if node is not None:
                    child_items.append((node, f"cat:{child.id}"))
            child_items.extend(merchant_nodes(own_rows.get(category.id, [])))
            if not child_items:
                return None
            children = _sorted_nodes(child_items)
            amount = sum((c.amount for c in children), zero)
            count = sum(c.count for c in children)
            return DrillNode(category.name, amount, count, children)

        top_items: list[tuple[DrillNode, str]] = []
        for top_id in {top_of_chain(cid) for cid in own_rows if cid is not None}:
            top_category = by_id.get(top_id)
            if top_category is None:
                continue  # no live category_id is ever an orphan, but stay total
            node = category_node(top_category)
            if node is not None:
                top_items.append((node, f"cat:{top_id}"))
        if own_rows.get(None):
            uncat_children = _sorted_nodes(merchant_nodes(own_rows[None]))
            top_items.append(
                (
                    DrillNode(
                        labels.uncategorised,
                        sum((c.amount for c in uncat_children), zero),
                        sum(c.count for c in uncat_children),
                        uncat_children,
                    ),
                    "cat:none",
                )
            )
        branch_children = _sorted_nodes(top_items)
        return DrillNode(
            label,
            sum((c.amount for c in branch_children), zero),
            sum(c.count for c in branch_children),
            branch_children,
        )

    def _transfers_branch(
        self,
        label: str,
        start_iso: str,
        end_iso: str,
        account_ids: frozenset[int] | None,
        exponent: int,
    ) -> DrillNode:
        """The Transfers subtree (FIBR-0138 D4b): confirmed transfers whose **debit**
        leg is in the period and whose scope matches (either leg's account, or all),
        grouped by the ``from → to`` account-name pair, each drilling to its moves. A
        transfer belongs to exactly its debit-leg period (INV-6); ``display_amount`` is
        already the display-scaled positive ``Decimal``, so it presents identically to
        the Income/Spending figures (INV-8)."""
        zero = to_display_decimal(0, exponent)
        groups: dict[tuple[str, str], list[ConfirmedTransfer]] = {}
        for transfer in TransferDetectionService(self._vault).confirmed_transfers():
            if not (start_iso <= transfer.debit.occurred_on <= end_iso):
                continue
            if account_ids is not None and (
                transfer.debit.account_id not in account_ids
                and transfer.credit.account_id not in account_ids
            ):
                continue
            groups.setdefault((transfer.from_account, transfer.to_account), []).append(
                transfer
            )
        pair_items: list[tuple[DrillNode, str]] = []
        for (from_account, to_account), transfers in groups.items():
            moves = [
                (
                    DrillNode(t.debit.occurred_on, t.display_amount, 1, ()),
                    f"move:{t.pair_id}",
                )
                for t in transfers
            ]
            node = DrillNode(
                f"{from_account} → {to_account}",
                sum((t.display_amount for t in transfers), zero),
                len(transfers),
                _sorted_nodes(moves),
            )
            pair_items.append((node, f"pairgrp:{min(t.pair_id for t in transfers)}"))
        children = _sorted_nodes(pair_items)
        return DrillNode(
            label,
            sum((c.amount for c in children), zero),
            sum(c.count for c in children),
            children,
        )
