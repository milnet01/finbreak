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

    def add_batch(self, rows: Sequence[tuple[int, str, int, str]]) -> None:
        """Insert many ``(account_id, occurred_on, amount_minor, description)``
        rows, stamping ``created_at`` — **commit-free**: invoked inside
        ``ImportService``'s atomic import transaction, which owns the commit
        (FIBR-0007 D7). The per-row-committing ``add()`` (manual entry) is
        unchanged."""
        now = datetime.now(UTC).isoformat()
        self._conn.executemany(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (account_id, occurred_on, amount_minor, description, now)
                for account_id, occurred_on, amount_minor, description in rows
            ],
        )

    def count_for_account(self, account_id: int) -> int:
        return self._conn.execute(
            "SELECT count(*) FROM transactions WHERE account_id = ?",
            (account_id,),
        ).fetchone()[0]

    def _commit(self) -> None:
        self._conn.commit()
