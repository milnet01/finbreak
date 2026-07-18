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
from typing import cast

from finbreak.db import owned_transaction
from finbreak.models import StatementPeriod, StatementRow
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
            "SELECT p.id, a.name, p.account_id, p.period_start, p.period_end, "
            "p.source_filename, p.imported_at, COUNT(t.id) "
            "FROM statement_periods p "
            "JOIN accounts a ON a.id = p.account_id "
            "LEFT JOIN transactions t ON t.statement_period_id = p.id "
            "GROUP BY p.id, a.name, p.account_id, p.period_start, p.period_end, "
            "p.source_filename, p.imported_at "
            "ORDER BY p.imported_at, p.id"
        ).fetchall()
        return [StatementRow(*row) for row in rows]

    def delete_statement(self, period_id: int) -> int:
        """Atomically remove the statement ``period_id``, returning the number of
        transactions actually **deleted** (FIBR-0148; supersedes FIBR-0052 INV-9's
        "removes every stamped row" clause — the atomicity + ``NULL``-untouched +
        return-value clauses are retained). One owned ``BEGIN``, three ordered
        steps: (1) **hand off** each stamped row a *remaining* same-account
        statement also covers to that statement (``hand_off_covered`` — so shared
        transactions are preserved, not lost, INV-1); (2) delete the rows still
        stamped ``period_id`` (nothing else covers them); (3) delete the period
        row. Hand-off precedes the delete, and both precede the period delete, so
        the plain (non-cascade) FK never trips. Any failure ``ROLLBACK``s all
        three to a re-openable vault. Manual (``NULL``) and other statements'
        rows untouched."""
        conn = self._conn
        tx_repo = TransactionRepository(conn)
        period_repo = StatementPeriodRepository(conn)
        # Hand off covered rows, THEN delete the orphans, THEN the period row —
        # one owned unit; any failure rolls all three back (FIBR-0148 INV-4).
        with owned_transaction(conn):
            handed_off = tx_repo.hand_off_covered(period_id)
            deleted = tx_repo.delete_for_statement(period_id)
            period_repo.delete(period_id)
        log.info("statement deleted (%d handed off, %d removed)", handed_off, deleted)
        return deleted

    def delete_preview(self, period_id: int) -> tuple[int, int]:
        """A read-only preview of a ``delete_statement`` — ``(removed, kept)``
        (FIBR-0149). ``removed`` is how many transactions the delete would really
        destroy; ``kept`` is how many survive because a *remaining* overlapping
        statement of the same account also covers them (handed off, not lost).
        The confirm dialog reads this so it can name the true count instead of the
        full linked count (which over-states the loss in an overlap delete). The
        UI calls this, never a repository (the codebase's layering)."""
        return TransactionRepository(self._conn).delete_split_counts(period_id)

    def reassign_account(self, period_id: int, new_account_id: int) -> int:
        """Atomically re-point statement ``period_id`` **and** every transaction
        stamped with it to ``new_account_id``, returning the number of transactions
        moved (FIBR-0059 INV-1/INV-4). The span guard runs first — a pure read +
        refuse, **before** ``BEGIN`` (so a refusal opens no transaction) — then one
        owned ``BEGIN … COMMIT``; any failure ``ROLLBACK``s both ``UPDATE``s to a
        re-openable vault. Refuses with ``ValueError`` when the target account
        already has a **different** statement for the same span (INV-3), which
        would otherwise duplicate rows on a later import. Re-pointing to the
        statement's current account is a no-op (the self-exclusion below), returning
        the matched-row count (INV-5)."""
        conn = self._conn
        period_repo = StatementPeriodRepository(conn)
        tx_repo = TransactionRepository(conn)
        # The UI selection guarantees the period exists (cast, not a None-branch —
        # the AccountService convention for a guaranteed-present row).
        period = cast(StatementPeriod, period_repo.get(period_id))
        existing = period_repo.id_for_span(
            new_account_id, period.period_start, period.period_end
        )
        if existing not in (None, period_id):  # a DIFFERENT statement holds the span
            raise ValueError(
                "that account already has a statement for this period — "
                "delete or move it first"
            )
        # Both UPDATEs are one owned unit; any failure rolls both back to a
        # re-openable vault (FIBR-0059 INV-1).
        with owned_transaction(conn):
            period_repo.set_account(period_id, new_account_id)
            moved = tx_repo.reassign_account(period_id, new_account_id)
        log.info("statement account reassigned")
        return moved
