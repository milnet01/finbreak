"""ReportingRepository — the single range read the dashboard aggregates over
(FIBR-0012 D4).

A read, no commit. ``occurred_on`` is an ISO-8601 ``TEXT`` date, so a date range
is a plain lexicographic ``BETWEEN`` (ISO dates sort as text). The ``account_ids``
argument (FIBR-0013 D4) is ``None`` for the consolidated (all-accounts) view, a
**non-empty** ``frozenset`` for a chosen subset (an ``account_id IN (…)`` clause of
integer placeholders only), or an **empty** ``frozenset`` for *no* accounts — which
short-circuits to an empty result rather than emitting invalid ``IN ()`` SQL, so a
stray empty set never silently means "all". Returns raw ``(id, occurred_on,
amount_minor, category_id)`` tuples; the service owns the transfer-exclusion, the
sign split, and the minor→Decimal scaling.
"""

from __future__ import annotations

from sqlcipher3 import dbapi2


class ReportingRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def rows_in_range(
        self, start_iso: str, end_iso: str, account_ids: frozenset[int] | None
    ) -> list[tuple[int, str, int, int | None]]:
        """``(id, occurred_on, amount_minor, category_id)`` for rows whose
        ``occurred_on`` is in ``[start_iso, end_iso]`` (inclusive), scoped to
        ``account_ids`` (``None`` ⇒ all; a non-empty set ⇒ those accounts;
        an empty set ⇒ no rows — FIBR-0013 D4)."""
        if account_ids is not None and not account_ids:
            return []  # empty selection ⇒ empty result (never invalid IN ())
        sql = (
            "SELECT id, occurred_on, amount_minor, category_id "
            "FROM transactions "
            "WHERE occurred_on BETWEEN ? AND ?"
        )
        params: list[str | int] = [start_iso, end_iso]
        if account_ids is not None:
            placeholders = ",".join("?" * len(account_ids))
            sql += f" AND account_id IN ({placeholders})"
            params.extend(sorted(account_ids))  # sorted ⇒ deterministic binding
        rows = self._conn.execute(sql, params).fetchall()
        return [(row[0], row[1], row[2], row[3]) for row in rows]

    def drill_rows_in_range(
        self, start_iso: str, end_iso: str, account_ids: frozenset[int] | None
    ) -> list[tuple[int, str, int, int | None, str]]:
        """``(id, occurred_on, amount_minor, category_id, description)`` — the
        drill-down's richer read (FIBR-0138 D5). Identical window + ``account_ids``
        semantics to ``rows_in_range`` (incl. the empty-set short-circuit); it adds
        exactly the one ``description`` column the merchant cleanup needs, and no
        ``account_id`` (the scope is already in the ``IN (…)`` clause). A deliberate
        sibling, not an extension — the three hot aggregations keep their lean
        4-tuple with no strings in the loop."""
        if account_ids is not None and not account_ids:
            return []  # empty selection ⇒ empty result (never invalid IN ())
        sql = (
            "SELECT id, occurred_on, amount_minor, category_id, description "
            "FROM transactions "
            "WHERE occurred_on BETWEEN ? AND ?"
        )
        params: list[str | int] = [start_iso, end_iso]
        if account_ids is not None:
            placeholders = ",".join("?" * len(account_ids))
            sql += f" AND account_id IN ({placeholders})"
            params.extend(sorted(account_ids))  # sorted ⇒ deterministic binding
        rows = self._conn.execute(sql, params).fetchall()
        return [(row[0], row[1], row[2], row[3], row[4]) for row in rows]
