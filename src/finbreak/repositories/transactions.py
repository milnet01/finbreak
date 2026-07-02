"""TransactionRepository — insert and list transaction rows (raw minor units).

Each write is one explicit DB transaction: the INSERT and its ``commit()`` are
separated so a failure between them rolls back on connection close (FIBR-0004
INV-4a). Money crosses this layer as the signed integer ``amount_minor``; the
service layer owns the Decimal ↔ minor-units scaling.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import Transaction


class TransactionRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def add(self, occurred_on: str, amount_minor: int, description: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO transactions"
            "(occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?)",
            (occurred_on, amount_minor, description, datetime.now(UTC).isoformat()),
        )
        self._commit()
        return cursor.lastrowid

    def list_all(self) -> list[Transaction]:
        rows = self._conn.execute(
            "SELECT id, occurred_on, amount_minor, description, created_at "
            "FROM transactions ORDER BY occurred_on, id"
        ).fetchall()
        return [Transaction(*row) for row in rows]

    def _commit(self) -> None:
        self._conn.commit()
