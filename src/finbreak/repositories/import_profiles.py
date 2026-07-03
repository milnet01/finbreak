"""ImportProfileRepository — CRUD over the ``import_profiles`` table (FIBR-0007).

Persistence only; the "exactly one amount style" validation and the
upsert-by-signature orchestration live in ``ImportService``. Each write is one
explicit transaction, mirroring ``AccountRepository``'s commit seam. The SELECT
column list is written literally so it shares the ``ImportProfile`` dataclass's
field order — ``ImportProfile(*row)`` stays aligned.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import ColumnMapping, ImportProfile

# The SELECT column list is written literally in each query (not interpolated)
# so it shares the ``ImportProfile`` dataclass's field order — matching the
# AccountRepository / CategoryRepository convention (and keeping the SQL a plain
# literal, not an f-string bandit reads as an injection vector, B608).


class ImportProfileRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def add(self, name: str, signature: str, mapping: ColumnMapping) -> int:
        cursor = self._conn.execute(
            "INSERT INTO import_profiles("
            "name, signature, date_column, description_column, amount_column, "
            "debit_column, credit_column, date_format, invert_amount, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                signature,
                mapping.date_column,
                mapping.description_column,
                mapping.amount_column,
                mapping.debit_column,
                mapping.credit_column,
                mapping.date_format,
                int(mapping.invert_amount),
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def update(self, profile_id: int, name: str, mapping: ColumnMapping) -> None:
        """Overwrite the name + mapping in place; ``signature`` and ``created_at``
        are preserved (a re-mapped bank keeps its identity + first-saved date)."""
        self._conn.execute(
            "UPDATE import_profiles SET name = ?, date_column = ?, "
            "description_column = ?, amount_column = ?, debit_column = ?, "
            "credit_column = ?, date_format = ?, invert_amount = ? WHERE id = ?",
            (
                name,
                mapping.date_column,
                mapping.description_column,
                mapping.amount_column,
                mapping.debit_column,
                mapping.credit_column,
                mapping.date_format,
                int(mapping.invert_amount),
                profile_id,
            ),
        )
        self._conn.commit()

    def get(self, profile_id: int) -> ImportProfile | None:
        row = self._conn.execute(
            "SELECT id, name, signature, date_column, description_column, "
            "amount_column, debit_column, credit_column, date_format, "
            "invert_amount, created_at FROM import_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        return ImportProfile(*row) if row is not None else None

    def get_by_signature(self, signature: str) -> ImportProfile | None:
        row = self._conn.execute(
            "SELECT id, name, signature, date_column, description_column, "
            "amount_column, debit_column, credit_column, date_format, "
            "invert_amount, created_at FROM import_profiles WHERE signature = ?",
            (signature,),
        ).fetchone()
        return ImportProfile(*row) if row is not None else None

    def list_all(self) -> list[ImportProfile]:
        rows = self._conn.execute(
            "SELECT id, name, signature, date_column, description_column, "
            "amount_column, debit_column, credit_column, date_format, "
            "invert_amount, created_at FROM import_profiles "
            "ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [ImportProfile(*row) for row in rows]
