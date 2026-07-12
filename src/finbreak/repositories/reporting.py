"""ReportingRepository — the single range read the dashboard aggregates over
(FIBR-0012 D4).

A read, no commit. ``occurred_on`` is an ISO-8601 ``TEXT`` date, so a date range
is a plain lexicographic ``BETWEEN`` (ISO dates sort as text). The ``account_id``
argument is ``None`` for the consolidated (all-accounts) view or an id for one
account — the ``(? IS NULL OR account_id = ?)`` predicate covers both in one
prepared statement. Returns raw ``(id, occurred_on, amount_minor, category_id)``
tuples; the service owns the transfer-exclusion, the sign split, and the
minor→Decimal scaling.
"""

from __future__ import annotations

from sqlcipher3 import dbapi2


class ReportingRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def rows_in_range(
        self, start_iso: str, end_iso: str, account_id: int | None
    ) -> list[tuple[int, str, int, int | None]]:
        """``(id, occurred_on, amount_minor, category_id)`` for rows whose
        ``occurred_on`` is in ``[start_iso, end_iso]`` (inclusive) and, when
        ``account_id`` is not ``None``, that account only."""
        rows = self._conn.execute(
            "SELECT id, occurred_on, amount_minor, category_id "
            "FROM transactions "
            "WHERE occurred_on BETWEEN ? AND ? "
            "AND (? IS NULL OR account_id = ?)",
            (start_iso, end_iso, account_id, account_id),
        ).fetchall()
        return [(row[0], row[1], row[2], row[3]) for row in rows]
