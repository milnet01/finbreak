"""StatementService — the Statements tab's read + delete (FIBR-0052 D10).

A distinct responsibility from the import pipeline (``ImportService`` is already
large), given its own testable seam. ``list_statements`` assembles the tab rows
with a single ``LEFT JOIN`` of ``accounts`` (for the name) + a grouped ``COUNT``
of linked ``transactions`` — so a zero-linked statement still appears with count
0 (INV-7/INV-7b), and no N+1. ``delete_statement`` runs one service-owned
``BEGIN … COMMIT``: it removes the statement's stamped transactions **then** the
period row (the ordered two-step delete, INV-9), leaving manual (``NULL``) and
other statements' rows untouched, and ``ROLLBACK``s to a re-openable vault on any
failure. Constructed like the other services — takes a ``Vault``.
"""

from __future__ import annotations

import logging

from finbreak.models import StatementRow
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.vault import Vault

log = logging.getLogger(__name__)


class StatementService:
    def __init__(self, vault: Vault):
        self._vault = vault

    @property
    def _conn(self):
        return self._vault.connection

    def list_statements(self) -> list[StatementRow]:
        """Every recorded statement (all accounts) + its linked-transaction count.

        A ``LEFT JOIN`` from ``statement_periods`` keeps a zero-linked statement in
        the result (count 0, INV-7b); the ``COUNT(t.id)`` counts only matched
        transaction rows (0 when none link). Ordered by import recency then id, so
        the newest import sorts last (stable with ``list_all``)."""
        rows = self._conn.execute(
            "SELECT p.id, a.name, p.period_start, p.period_end, p.source_filename, "
            "p.imported_at, COUNT(t.id) "
            "FROM statement_periods p "
            "JOIN accounts a ON a.id = p.account_id "
            "LEFT JOIN transactions t ON t.statement_period_id = p.id "
            "GROUP BY p.id, a.name, p.period_start, p.period_end, p.source_filename, "
            "p.imported_at "
            "ORDER BY p.imported_at, p.id"
        ).fetchall()
        return [StatementRow(*row) for row in rows]

    def delete_statement(self, period_id: int) -> int:
        """Atomically remove the statement ``period_id`` and its stamped
        transactions, returning the number of transactions deleted (INV-9). One
        owned ``BEGIN``: delete the children **then** the parent (so the plain FK
        never trips), ``COMMIT``; any failure ``ROLLBACK``s both tables to a
        re-openable vault. Manual (``NULL``) and other statements' rows untouched."""
        conn = self._conn
        tx_repo = TransactionRepository(conn)
        period_repo = StatementPeriodRepository(conn)
        conn.execute("BEGIN")  # first statement — own the transaction (INV-9)
        try:
            deleted = tx_repo.delete_for_statement(period_id)
            period_repo.delete(period_id)
            conn.commit()
        except Exception:
            conn.rollback()  # both deletes undone — leaves the vault re-openable
            raise
        log.info("statement deleted")
        return deleted
