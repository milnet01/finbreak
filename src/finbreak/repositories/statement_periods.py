"""StatementPeriodRepository — the per-import coverage-period record (FIBR-0007
D8).

Persistence only; span-uniqueness (INV-6) is a service-layer check, not a DB
``UNIQUE``. ``add`` is **commit-free** — invoked inside ``ImportService``'s
atomic import transaction (D7), which owns the commit. The SELECT column list is
written literally so it shares the ``StatementPeriod`` dataclass's field order.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import StatementPeriod
from finbreak.repositories import last_insert_id

# The SELECT column list is written literally (not interpolated) so it shares the
# ``StatementPeriod`` dataclass's field order — matching the codebase convention
# and keeping the SQL a plain literal, not an f-string (bandit B608).


class StatementPeriodRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def add(
        self,
        account_id: int,
        period_start: str,
        period_end: str,
        source_filename: str | None,
    ) -> int:
        """Insert one coverage-period row, stamping ``imported_at`` (UTC ISO), and
        return its new id (so ``commit_import`` can stamp the batch with it,
        FIBR-0052 INV-8). Commit-free — the caller's import transaction owns the
        commit (D7)."""
        cursor = self._conn.execute(
            "INSERT INTO statement_periods("
            "account_id, period_start, period_end, source_filename, imported_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                account_id,
                period_start,
                period_end,
                source_filename,
                datetime.now(UTC).isoformat(),
            ),
        )
        return last_insert_id(cursor)

    def id_for_span(
        self, account_id: int, period_start: str, period_end: str
    ) -> int | None:
        """The id of the row for this exact ``(account_id, period_start,
        period_end)`` span, or ``None`` if it is not yet recorded — the span-dedup
        check (INV-6) that also yields the id for the reuse path (FIBR-0052 D8): a
        non-``None`` return means the span exists and gives the id to stamp with."""
        row = self._conn.execute(
            "SELECT id FROM statement_periods "
            "WHERE account_id = ? AND period_start = ? AND period_end = ? LIMIT 1",
            (account_id, period_start, period_end),
        ).fetchone()
        return row[0] if row is not None else None

    def list_for_account(self, account_id: int) -> list[StatementPeriod]:
        rows = self._conn.execute(
            "SELECT id, account_id, period_start, period_end, source_filename, "
            "imported_at FROM statement_periods "
            "WHERE account_id = ? ORDER BY period_start, id",
            (account_id,),
        ).fetchall()
        return [StatementPeriod(*row) for row in rows]

    def list_all(self) -> list[StatementPeriod]:
        """Every recorded coverage period across **all** accounts (the Statements
        tab's read, FIBR-0052 INV-7), ordered by import recency then id."""
        rows = self._conn.execute(
            "SELECT id, account_id, period_start, period_end, source_filename, "
            "imported_at FROM statement_periods ORDER BY imported_at, id"
        ).fetchall()
        return [StatementPeriod(*row) for row in rows]

    def get(self, period_id: int) -> StatementPeriod | None:
        """The single coverage-period row for ``period_id``, or ``None`` if absent
        — the span read behind ``reassign_account``'s guard (FIBR-0059 D2)."""
        row = self._conn.execute(
            "SELECT id, account_id, period_start, period_end, source_filename, "
            "imported_at FROM statement_periods WHERE id = ?",
            (period_id,),
        ).fetchone()
        return StatementPeriod(*row) if row is not None else None

    def set_account(self, period_id: int, account_id: int) -> None:
        """Re-point one coverage-period row to another account. **Commit-free** —
        invoked inside ``StatementService.reassign_account``'s owned transaction
        (FIBR-0059 INV-1)."""
        self._conn.execute(
            "UPDATE statement_periods SET account_id = ? WHERE id = ?",
            (account_id, period_id),
        )

    def delete(self, period_id: int) -> None:
        """Remove one coverage-period row. **Commit-free** — invoked inside
        ``StatementService.delete_statement``'s owned transaction, **after** its
        stamped transactions are removed, so the plain FK never trips (FIBR-0052
        INV-9)."""
        self._conn.execute("DELETE FROM statement_periods WHERE id = ?", (period_id,))
