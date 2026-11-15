"""ImportedFileRepository — which files each statement was imported from
(FIBR-0088).

A file is identified by the SHA-256 of its bytes on disk, never its name. Rows
hang off ``statement_periods`` with ``ON DELETE CASCADE``, so deleting a
statement forgets its files and moving it to another account moves them too.
``add`` is **commit-free**: it runs inside ``ImportService.commit_import``'s
transaction, which owns the commit. The SQL is literal (bandit B608).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import PriorImport


class ImportedFileRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def add(self, statement_period_id: int, file_sha256: str) -> None:
        """Record that ``file_sha256`` was imported into the statement, stamping
        ``imported_at`` (UTC ISO). A repeat import of the same file into the same
        statement restamps the existing row, so the latest import is the one
        recorded. Commit-free."""
        self._conn.execute(
            "INSERT INTO imported_files(statement_period_id, file_sha256, imported_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(statement_period_id, file_sha256) "
            "DO UPDATE SET imported_at = excluded.imported_at",
            (statement_period_id, file_sha256, datetime.now(UTC).isoformat()),
        )

    def latest(self, file_sha256: str) -> PriorImport | None:
        """The most recent import of ``file_sha256``, or ``None`` if it was never
        imported (or every statement it went into has since been deleted)."""
        row = self._conn.execute(
            "SELECT a.name, p.period_start, p.period_end, f.imported_at "
            "FROM imported_files f "
            "JOIN statement_periods p ON p.id = f.statement_period_id "
            "JOIN accounts a ON a.id = p.account_id "
            "WHERE f.file_sha256 = ? "
            "ORDER BY f.imported_at DESC, f.id DESC LIMIT 1",
            (file_sha256,),
        ).fetchone()
        return PriorImport(*row) if row is not None else None
