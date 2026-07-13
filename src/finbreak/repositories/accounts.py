"""AccountRepository — CRUD over the ``accounts`` table (FIBR-0005 INV-1).

Persistence only; name/type validation and the delete guard live in
``AccountService``. Each write is one explicit transaction, mirroring
``TransactionRepository``'s commit seam.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import Account
from finbreak.repositories import last_insert_id


class AccountRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def add(self, name: str, type: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO accounts(name, type, created_at) VALUES (?, ?, ?)",
            (name, type, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
        return last_insert_id(cursor)

    def list_all(self) -> list[Account]:
        rows = self._conn.execute(
            "SELECT id, name, type, created_at FROM accounts "
            "ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [Account(*row) for row in rows]

    def get(self, account_id: int) -> Account | None:
        row = self._conn.execute(
            "SELECT id, name, type, created_at FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return Account(*row) if row is not None else None

    def update(self, account_id: int, name: str, type: str) -> None:
        self._conn.execute(
            "UPDATE accounts SET name = ?, type = ? WHERE id = ?",
            (name, type, account_id),
        )
        self._conn.commit()

    def delete(self, account_id: int) -> None:
        self._conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute("SELECT count(*) FROM accounts").fetchone()[0]

    # -- remembered PDF password (v5, FIBR-0009 D6) ---------------------------
    # Read/written by dedicated accessors, NOT selected into the broadly-passed
    # ``Account`` dataclass, so a remembered credential never rides along with an
    # account listing or a log line (credential hygiene, INV-8/INV-11).
    def get_pdf_password(self, account_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT statement_pdf_password FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return row[0] if row is not None else None

    def set_pdf_password(self, account_id: int, value: str | None) -> None:
        self._conn.execute(
            "UPDATE accounts SET statement_pdf_password = ? WHERE id = ?",
            (value, account_id),
        )
        self._conn.commit()
