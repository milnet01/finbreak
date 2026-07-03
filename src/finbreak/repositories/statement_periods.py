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
    ) -> None:
        """Insert one coverage-period row, stamping ``imported_at`` (UTC ISO).
        Commit-free — the caller's import transaction owns the commit (D7)."""
        self._conn.execute(
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

    def exists(self, account_id: int, period_start: str, period_end: str) -> bool:
        """Whether this exact ``(account_id, period_start, period_end)`` span is
        already recorded (the span-dedup check, INV-6)."""
        row = self._conn.execute(
            "SELECT 1 FROM statement_periods "
            "WHERE account_id = ? AND period_start = ? AND period_end = ? LIMIT 1",
            (account_id, period_start, period_end),
        ).fetchone()
        return row is not None

    def list_for_account(self, account_id: int) -> list[StatementPeriod]:
        rows = self._conn.execute(
            "SELECT id, account_id, period_start, period_end, source_filename, "
            "imported_at FROM statement_periods "
            "WHERE account_id = ? ORDER BY period_start, id",
            (account_id,),
        ).fetchall()
        return [StatementPeriod(*row) for row in rows]
