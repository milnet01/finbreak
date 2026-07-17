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
from finbreak.repositories import last_insert_id


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
        return last_insert_id(cursor)

    def list_all(self) -> list[Transaction]:
        # The category_id/category_source columns (v7, FIBR-0010) are appended
        # last so Transaction(*row) stays aligned with the dataclass field order.
        rows = self._conn.execute(
            "SELECT id, account_id, occurred_on, amount_minor, description, "
            "created_at, category_id, category_source "
            "FROM transactions ORDER BY occurred_on, id"
        ).fetchall()
        return [Transaction(*row) for row in rows]

    def auto_rows(self) -> list[tuple[int, str]]:
        """The ``(id, description)`` of every **auto** row — one the engine may
        recompute (FIBR-0010 D4). The NULL-safe predicate ``category_source IS NULL
        OR category_source <> 'manual'`` is load-bearing: a bare ``<> 'manual'``
        drops every never-touched ``NULL`` row (SQL three-valued logic — ``NULL <>
        'manual'`` is unknown, not true), i.e. the dominant auto state right after
        an import. Manual rows are excluded here, so they are never read or written."""
        rows = self._conn.execute(
            "SELECT id, description FROM transactions "
            "WHERE category_source IS NULL OR category_source <> 'manual'"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def set_category(
        self, txn_id: int, category_id: int | None, source: str | None
    ) -> int:
        """Set one row's ``(category_id, category_source)``, **only if it actually
        changes**, and return the number of rows written (0 or 1). The NULL-safe
        ``IS NOT`` guard makes a re-apply with unchanged rules a genuine no-op
        (INV-13) and makes the summed rowcount the honest "re-filed" number (D4).
        **Commit-free** — the owning service (``apply_rules`` / ``set_manual_category``
        / ``commit_import`` / the delete cascade) commits."""
        return self._conn.execute(
            "UPDATE transactions SET category_id = ?, category_source = ? "
            "WHERE id = ? AND (category_id IS NOT ? OR category_source IS NOT ?)",
            (category_id, source, txn_id, category_id, source),
        ).rowcount

    def clear_category_for(self, category_id: int) -> int:
        """Reset every row filed under ``category_id`` to auto/uncategorised
        (``NULL``/``NULL``) — including manual rows to that category (the category
        is being deleted, so freezing to it is meaningless, FIBR-0010 INV-7). Returns
        the rowcount. **Commit-free** — the owning ``CategoryService`` transaction
        commits, and this runs before the category row is deleted (order matters)."""
        return self._conn.execute(
            "UPDATE transactions SET category_id = NULL, category_source = NULL "
            "WHERE category_id = ?",
            (category_id,),
        ).rowcount

    def count_for_category(self, category_id: int) -> int:
        """How many rows are filed under ``category_id`` (manual **and** rule) — the
        transaction half of the INV-8 blast radius."""
        return self._conn.execute(
            "SELECT count(*) FROM transactions WHERE category_id = ?",
            (category_id,),
        ).fetchone()[0]

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

    def hand_off_covered(self, statement_period_id: int) -> int:
        """Re-stamp every transaction of the statement being deleted whose date a
        **remaining** statement of the **same account** also covers, to that
        statement — returning the rowcount handed off (FIBR-0148 INV-1). The
        mirror of the ``_migrate_to_v6`` backfill with the polarity flipped:
        ``NOT EXISTS`` → ``EXISTS`` (hand-off-if-covered), the outer ``WHERE``
        keyed on ``= :pid`` instead of ``IS NULL``, and the ``SET`` sub-query a
        correlated pick (``ORDER BY period_start, id LIMIT 1`` — INV-5) rather
        than a constant. The ``EXISTS`` guard shares the sub-query's predicate
        **byte-for-byte**, so a row no remaining statement covers is never
        re-stamped to ``NULL`` (it keeps ``:pid`` and is deleted next) — the
        money-critical NULL trap. **Commit-free** — invoked inside
        ``StatementService.delete_statement``'s owned transaction, **before**
        ``delete_for_statement``. ``NULL``-stamped (manual) rows are untouched."""
        return self._conn.execute(
            "UPDATE transactions SET statement_period_id = ("
            "  SELECT q.id FROM statement_periods q "
            "  WHERE q.account_id = transactions.account_id AND q.id <> :pid "
            "  AND transactions.occurred_on BETWEEN q.period_start AND q.period_end "
            "  ORDER BY q.period_start, q.id LIMIT 1) "
            "WHERE statement_period_id = :pid "
            "AND EXISTS ("
            "  SELECT 1 FROM statement_periods q "
            "  WHERE q.account_id = transactions.account_id AND q.id <> :pid "
            "  AND transactions.occurred_on BETWEEN q.period_start AND q.period_end)",
            {"pid": statement_period_id},
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
