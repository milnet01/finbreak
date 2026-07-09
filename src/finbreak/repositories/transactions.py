"""TransactionRepository — insert and list transaction rows (raw minor units).

Each write is one explicit DB transaction: the INSERT and its ``commit()`` are
separated so a failure between them rolls back on connection close (FIBR-0004
INV-4a). Money crosses this layer as the signed integer ``amount_minor``; the
service layer owns the Decimal ↔ minor-units scaling.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import Transaction


class TransactionRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def add(
        self, account_id: int, occurred_on: str, amount_minor: int, description: str
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                account_id,
                occurred_on,
                amount_minor,
                description,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._commit()
        return cursor.lastrowid

    def list_all(self) -> list[Transaction]:
        rows = self._conn.execute(
            "SELECT id, account_id, occurred_on, amount_minor, description, "
            "created_at FROM transactions ORDER BY occurred_on, id"
        ).fetchall()
        return [Transaction(*row) for row in rows]

    def existing_for(
        self, account_id: int, occurred_on: str, amount_minor: int
    ) -> list[str]:
        """The descriptions of existing rows in the ``(account_id, occurred_on,
        amount_minor)`` bucket — the service normalises + counts them for the
        import dedup delta (SQLite can't ``casefold``, so this returns raw
        descriptions; FIBR-0007 D6/INV-5)."""
        rows = self._conn.execute(
            "SELECT description FROM transactions "
            "WHERE account_id = ? AND occurred_on = ? AND amount_minor = ?",
            (account_id, occurred_on, amount_minor),
        ).fetchall()
        return [row[0] for row in rows]

    def add_batch(
        self, rows: Sequence[tuple[int, str, int, str]], statement_period_id: int
    ) -> None:
        """Insert many ``(account_id, occurred_on, amount_minor, description)``
        rows, stamping ``created_at`` **and** ``statement_period_id`` (all rows of
        one import share the one period id, FIBR-0052 INV-8) — **commit-free**:
        invoked inside ``ImportService``'s atomic import transaction, which owns
        the commit (FIBR-0007 D7). The per-row-committing ``add()`` (manual entry)
        is unchanged and leaves ``statement_period_id`` ``NULL``."""
        now = datetime.now(UTC).isoformat()
        self._conn.executemany(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at, "
            "statement_period_id) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    account_id,
                    occurred_on,
                    amount_minor,
                    description,
                    now,
                    statement_period_id,
                )
                for account_id, occurred_on, amount_minor, description in rows
            ],
        )

    def delete_for_statement(self, statement_period_id: int) -> int:
        """Delete every transaction stamped with ``statement_period_id`` and return
        the rowcount. **Commit-free** — invoked inside ``StatementService``'s owned
        delete transaction, **before** the ``statement_periods`` row is removed, so
        the plain FK is never violated (FIBR-0052 INV-9). ``NULL``-stamped (manual)
        and other statements' rows are untouched."""
        return self._conn.execute(
            "DELETE FROM transactions WHERE statement_period_id = ?",
            (statement_period_id,),
        ).rowcount

    def reassign_account(self, statement_period_id: int, account_id: int) -> int:
        """Re-point every transaction stamped with ``statement_period_id`` to
        ``account_id``, returning the rowcount. **Commit-free** — invoked inside
        ``StatementService.reassign_account``'s owned transaction (FIBR-0059 INV-1).
        ``NULL``-stamped (manual) and other statements' rows are untouched."""
        return self._conn.execute(
            "UPDATE transactions SET account_id = ? WHERE statement_period_id = ?",
            (account_id, statement_period_id),
        ).rowcount

    def count_for_account(self, account_id: int) -> int:
        return self._conn.execute(
            "SELECT count(*) FROM transactions WHERE account_id = ?",
            (account_id,),
        ).fetchone()[0]

    def _commit(self) -> None:
        self._conn.commit()
