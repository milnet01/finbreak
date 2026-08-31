"""StatementPeriodRepository — the per-import coverage-period record (FIBR-0007
D8).

Persistence only; span-uniqueness (INV-6) is a service-layer check, not a DB
``UNIQUE``. ``add`` is **commit-free** — invoked inside ``ImportService``'s
atomic import transaction (D7), which owns the commit. The SELECT column list is
written literally so it shares the ``StatementPeriod`` dataclass's field order.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import StatementPeriod
from finbreak.repositories import last_insert_id

log = logging.getLogger(__name__)

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
        closing_balance_minor: int | None = None,
    ) -> int:
        """Insert one coverage-period row, stamping ``imported_at`` (UTC ISO), and
        return its new id (so ``commit_import`` can stamp the batch with it,
        FIBR-0052 INV-8). ``closing_balance_minor`` (FIBR-0171) is the statement's
        persisted closing balance in signed minor units, or ``None`` when the source
        printed none (Savings / CSV / manual). Commit-free — the caller's import
        transaction owns the commit (D7)."""
        cursor = self._conn.execute(
            "INSERT INTO statement_periods("
            "account_id, period_start, period_end, source_filename, imported_at, "
            "closing_balance_minor) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                account_id,
                period_start,
                period_end,
                source_filename,
                datetime.now(UTC).isoformat(),
                closing_balance_minor,
            ),
        )
        return last_insert_id(cursor)

    def update_closing_balance(self, period_id: int, balance_minor: int) -> None:
        """**Fill-only** write of a span's closing balance (FIBR-0171 D4/INV-12):
        set ``closing_balance_minor`` for ``period_id`` **only when the stored value
        is currently ``NULL``** — filling a gap left by a prior CSV-only import. For
        one span the closing balance is fixed, so a non-``NULL`` stored balance is
        **never** overwritten; an incoming *different* value signals a parse /
        wrong-file error, so keep the stored value but **log a warning** naming the
        span and both values rather than swallowing the disagreement. Commit-free —
        the caller's import transaction owns the commit."""
        stored = self._conn.execute(
            "SELECT closing_balance_minor FROM statement_periods WHERE id = ?",
            (period_id,),
        ).fetchone()
        if stored is None:
            return  # no such span
        current = stored[0]
        if current is None:
            self._conn.execute(
                "UPDATE statement_periods SET closing_balance_minor = ? WHERE id = ?",
                (balance_minor, period_id),
            )
        elif current != balance_minor:
            # The period id ONLY. security-model INV-9 says the log never records
            # decrypted data, and a closing balance is decrypted vault content.
            # No handler is configured anywhere in the app, so this falls through
            # to logging.lastResort -- which emits WARNING and above to stderr,
            # i.e. the terminal or the desktop journal, outside the encryption
            # boundary and outside any rotation INV-9 assumes.
            log.warning(
                "closing balance disagreement for statement period %d — keeping "
                "the stored value (a span's balance is fixed)",
                period_id,
            )

    def latest_closing_balances(self) -> list[tuple[int, int, str]]:
        """One ``(account_id, closing_balance_minor, period_end)`` per account: the
        row with the greatest ``period_end`` (tie: greatest ``id``) whose
        ``closing_balance_minor`` is non-``NULL`` (FIBR-0171 D1/INV-6). Accounts with
        no balance-bearing statement are absent (they contribute nothing to the
        forecast anchor). A window function picks the top row per account partition."""
        rows = self._conn.execute(
            "SELECT account_id, closing_balance_minor, period_end FROM ("
            "  SELECT account_id, closing_balance_minor, period_end, "
            "  ROW_NUMBER() OVER ("
            "    PARTITION BY account_id ORDER BY period_end DESC, id DESC) AS rn "
            "  FROM statement_periods WHERE closing_balance_minor IS NOT NULL"
            ") WHERE rn = 1"
        ).fetchall()
        return [
            (account_id, balance, period_end)
            for account_id, balance, period_end in rows
        ]

    def closing_balances_for_account(self, account_id: int) -> list[tuple[str, int]]:
        """One ``(period_end, closing_balance_minor)`` per balance-bearing statement
        of ``account_id`` — the rows whose ``closing_balance_minor`` is non-``NULL``,
        ordered ``(period_end, id)`` **ascending** (the reconciliation chain,
        FIBR-0177 D3/INV-3). A sibling of ``latest_closing_balances`` — the same
        *columns*, ascending (the balance *date*, tie-broken by insert order) vs its
        latest-row-per-account ``DESC``. Statements with no closing balance (CSV /
        manual) are not chain nodes, but their transactions still count inside a
        bridge window (the service reads them via ``sum_after``). The SELECT column
        list is literal (bandit B608)."""
        rows = self._conn.execute(
            "SELECT period_end, closing_balance_minor FROM statement_periods "
            "WHERE account_id = ? AND closing_balance_minor IS NOT NULL "
            "ORDER BY period_end, id",
            (account_id,),
        ).fetchall()
        return [(period_end, balance) for period_end, balance in rows]

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
            "imported_at, closing_balance_minor FROM statement_periods "
            "WHERE account_id = ? ORDER BY period_start, id",
            (account_id,),
        ).fetchall()
        return [StatementPeriod(*row) for row in rows]

    def list_all(self) -> list[StatementPeriod]:
        """Every recorded coverage period across **all** accounts (the Statements
        tab's read, FIBR-0052 INV-7), ordered by import recency then id."""
        rows = self._conn.execute(
            "SELECT id, account_id, period_start, period_end, source_filename, "
            "imported_at, closing_balance_minor FROM statement_periods "
            "ORDER BY imported_at, id"
        ).fetchall()
        return [StatementPeriod(*row) for row in rows]

    def get(self, period_id: int) -> StatementPeriod | None:
        """The single coverage-period row for ``period_id``, or ``None`` if absent
        — the span read behind ``reassign_account``'s guard (FIBR-0059 D2)."""
        row = self._conn.execute(
            "SELECT id, account_id, period_start, period_end, source_filename, "
            "imported_at, closing_balance_minor FROM statement_periods WHERE id = ?",
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
