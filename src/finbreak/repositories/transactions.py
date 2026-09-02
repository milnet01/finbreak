"""TransactionRepository — insert and list transaction rows (raw minor units).

Each write is one explicit DB transaction: the INSERT and its ``commit()`` are
separated so a failure between them rolls back on connection close (FIBR-0004
INV-4a). Money crosses this layer as the signed integer ``amount_minor``; the
service layer owns the Decimal ↔ minor-units scaling.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import Transaction
from finbreak.repositories import last_insert_id

# How many ids one ``IN (...)`` binding may carry. SQLite's host-parameter cap is
# 999 on builds older than 3.32, so this stays well under the lowest of them --
# the query is issued per chunk, and the cost of an extra round trip is nothing
# beside the full-table read this replaces.
_IN_CHUNK = 500


def _coverage_where_sql(ids: Sequence[int]) -> tuple[str, dict[str, int]]:
    """The shared "same account, covers this row, and NOT one of the statements
    being deleted" ``WHERE`` fragment, plus the parameter dict that binds it.

    The single source of the predicate: all **four** sites interpolate this SQL
    element — ``hand_off_covered``'s ``SET`` picker and ``EXISTS`` guard, and both
    of ``delete_split_counts``' counting arms — so the preview cannot describe a
    delete that does not match it, and no row is ever handed to a statement inside
    the batch (FIBR-0201 INV-9). Returning the params with the SQL keeps the
    ``:del0 … :del{n-1}`` naming in ONE place; built separately they drift.

    Placeholder style is pinned to **named** parameters: ``sqlite3`` refuses mixed
    named and qmark binding in one statement, and ``hand_off_covered`` keeps a
    scalar ``:pid`` in its outer ``WHERE``.

    ``n == 0`` is a precondition failure, not an edge case to render — an empty
    exclusion list would emit ``q.id NOT IN ()``, which SQLite rejects as a syntax
    error. Both batch service methods return early before reaching here."""
    if not ids:
        raise ValueError("the coverage predicate needs at least one excluded id")
    names = [f"del{i}" for i in range(len(ids))]
    placeholders = ", ".join(f":{name}" for name in names)
    sql = (
        f"q.account_id = transactions.account_id AND q.id NOT IN ({placeholders}) "
        "AND transactions.occurred_on BETWEEN q.period_start AND q.period_end"
    )
    return sql, dict(zip(names, ids, strict=True))


def _hand_off_sql(ids: Sequence[int]) -> str:
    """``hand_off_covered``'s statement, built at module level so a test can obtain
    the *emitted* SQL and compare its predicates (INV-9). The ``SET`` sub-query is
    the correlated **picker** (which statement a row is handed to) and the
    ``EXISTS`` is the **guard** (whether it is handed off at all) — both share the
    fragment byte-for-byte, so a row no survivor covers is never re-stamped to
    ``NULL`` (the money-critical NULL trap)."""
    coverage, _ = _coverage_where_sql(ids)
    # The suppression below is deliberate, not a silenced warning: the only
    # interpolated text is `coverage`, itself generated SQL whose variable part is
    # generated `:delN` placeholder NAMES. No caller value reaches the statement
    # text — the ids bind as named parameters. The underlying constraint is that a
    # variable-length IN list cannot be written as a fixed parameter string.
    return (
        "UPDATE transactions SET statement_period_id = ("  # nosec B608
        f"  SELECT q.id FROM statement_periods q WHERE {coverage} "
        "  ORDER BY q.period_start, q.id LIMIT 1) "
        "WHERE statement_period_id = :pid "
        "AND EXISTS ("
        f"  SELECT 1 FROM statement_periods q WHERE {coverage})"
    )


def _split_counts_sql(ids: Sequence[int]) -> str:
    """``delete_split_counts``' statement (see ``_hand_off_sql`` for why it is
    module-level). Its two counting arms share the same coverage fragment, so the
    preview can never disagree with the delete it describes."""
    coverage, _ = _coverage_where_sql(ids)
    outer = ", ".join(f":del{i}" for i in range(len(ids)))
    # Same reasoning as _hand_off_sql: the interpolated text is placeholder names.
    return (
        "SELECT "  # nosec B608
        "  COALESCE(SUM(CASE WHEN NOT EXISTS ("
        f"    SELECT 1 FROM statement_periods q WHERE {coverage}"
        "  ) THEN 1 ELSE 0 END), 0), "
        "  COALESCE(SUM(CASE WHEN EXISTS ("
        f"    SELECT 1 FROM statement_periods q WHERE {coverage}"
        "  ) THEN 1 ELSE 0 END), 0) "
        f"FROM transactions WHERE statement_period_id IN ({outer})"
    )


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

    def by_ids(self, txn_ids: Collection[int]) -> list[Transaction]:
        """The rows for a KNOWN set of ids, in ``list_all``'s order.

        For a caller resolving a handful of ids rather than surveying the table.
        The transfer service resolves both legs of each decided pair, and had no
        route but ``list_all`` -- so every Home refresh read every transaction in
        the vault to answer a question about a few of them (FIBR-0327).

        Bound in chunks: an ``IN`` list is one host parameter per id, and SQLite
        caps those, so a vault with enough decided pairs would raise rather than
        run. Placeholders are ``?`` marks and never values, the same posture as
        ``reporting.py``'s account scope; an empty set short-circuits rather than
        emitting the ``IN ()`` SQLite rejects.
        """
        ids = list(txn_ids)
        found: list[Transaction] = []
        for offset in range(0, len(ids), _IN_CHUNK):
            chunk = ids[offset : offset + _IN_CHUNK]
            placeholders = ",".join("?" * len(chunk))
            # nosec B608: the only interpolated text is a run of "?" marks whose
            # length comes from the chunk. No caller value reaches the SQL --
            # every id is bound. Same shape as reporting.py's account scope.
            rows = self._conn.execute(
                "SELECT id, account_id, occurred_on, amount_minor, description, "  # nosec B608
                "created_at, category_id, category_source "
                f"FROM transactions WHERE id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
            found.extend(Transaction(*row) for row in rows)
        found.sort(key=lambda t: (t.occurred_on, t.id))
        return found

    def auto_rows(self, *, min_txn_id: int = 0) -> list[tuple[int, str]]:
        """The ``(id, description)`` of every **auto** row above ``min_txn_id`` — one
        the engine may recompute (FIBR-0010 D4). The NULL-safe predicate
        ``category_source IS NULL OR category_source <> 'manual'`` is load-bearing: a
        bare ``<> 'manual'`` drops every never-touched ``NULL`` row (SQL three-valued
        logic — ``NULL <> 'manual'`` is unknown, not true), i.e. the dominant auto
        state right after an import. Manual rows are excluded here, so they are never
        read or written.

        ``min_txn_id`` defaults to 0, i.e. every auto row. ``commit_import`` passes
        ``max_id()`` taken inside its transaction just before the inserts, which
        scopes the recompute to exactly the rows it added (FIBR-0213)."""
        rows = self._conn.execute(
            "SELECT id, description FROM transactions "
            "WHERE (category_source IS NULL OR category_source <> 'manual') "
            "AND id > ?",
            (min_txn_id,),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def max_id(self) -> int:
        """The largest transaction id, or 0 on an empty table.

        Read inside ``commit_import``'s transaction immediately before its inserts:
        SQLite assigns a new ``INTEGER PRIMARY KEY`` row ``max(rowid) + 1``, so every
        row inserted after this read has a strictly greater id — an exact "the rows
        this import added" boundary, with no per-row id round-trip (FIBR-0213)."""
        return self._conn.execute(
            "SELECT coalesce(max(id), 0) FROM transactions"
        ).fetchone()[0]

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

    def hand_off_covered(
        self, statement_period_id: int, deleting: Sequence[int]
    ) -> int:
        """Re-stamp every transaction of the statement being deleted whose date a
        **surviving** statement of the **same account** also covers, to that
        statement — returning the rowcount handed off (FIBR-0148 INV-1). The
        mirror of the ``_migrate_to_v6`` backfill with the polarity flipped:
        ``NOT EXISTS`` → ``EXISTS`` (hand-off-if-covered), the outer ``WHERE``
        keyed on ``= :pid`` instead of ``IS NULL``, and the ``SET`` sub-query a
        correlated pick (``ORDER BY period_start, id LIMIT 1`` — INV-5) rather
        than a constant. **Commit-free** — invoked inside
        ``StatementService.delete_statements``' owned transaction, **before**
        ``delete_for_statement``. ``NULL``-stamped (manual) rows are untouched.

        The outer ``WHERE`` stays scalar: this hands off **one** statement's rows,
        while ``deleting`` excludes **the whole batch** from the coverage test, so
        no row is handed to a statement the same batch is about to delete
        (FIBR-0201 §4.4). ``deleting`` is required with no default — after
        FIBR-0201 no caller omits it, and a default nothing exercises is a path no
        test covers and a future reader trusts.

        ``statement_period_id`` must itself be a member of ``deleting``: with the
        statement absent from its own exclusion list the ``SET`` picker can
        re-stamp a row straight back onto the statement being deleted, which the
        period delete then orphans or FK-trips (INV-9)."""
        if statement_period_id not in deleting:
            raise ValueError(
                "the statement being handed off must itself be in the deleting set"
            )
        sql, params = _hand_off_sql(deleting), _coverage_where_sql(deleting)[1]
        return self._conn.execute(sql, {**params, "pid": statement_period_id}).rowcount

    def delete_split_counts(
        self, statement_period_ids: Sequence[int]
    ) -> tuple[int, int]:
        """A read-only preview of what deleting **this whole batch** would do to
        the rows stamped to it — ``(removed, kept)`` (FIBR-0149, widened to a set
        by FIBR-0201). ``kept`` are the rows a *surviving* same-account statement
        also covers (handed off, so they survive); ``removed`` are the true
        orphans, deleted. Commit-free; never mutates. ``NULL``-stamped (manual)
        rows are neither counted.

        The ids **are** the exclusion set — there is no second parameter, because
        in every use the previewed set and the excluded set are the same list and a
        pair with undefined divergent behaviour is an API a caller has to guess at
        (§8). Summing per-statement previews instead of calling this once is the
        measured defect FIBR-0201 §2.1 exists to prevent: it reports 0 removed for
        a delete that destroys two transactions irreversibly."""
        removed, kept = self._conn.execute(
            _split_counts_sql(statement_period_ids),
            _coverage_where_sql(statement_period_ids)[1],
        ).fetchone()
        return removed, kept

    def reassign_account(self, statement_period_id: int, account_id: int) -> int:
        """Re-point every transaction stamped with ``statement_period_id`` to
        ``account_id``, returning the rowcount. **Commit-free** — invoked inside
        ``StatementService.reassign_account``'s owned transaction (FIBR-0059 INV-1).
        ``NULL``-stamped (manual) and other statements' rows are untouched."""
        return self._conn.execute(
            "UPDATE transactions SET account_id = ? WHERE statement_period_id = ?",
            (account_id, statement_period_id),
        ).rowcount

    def sum_after(
        self, account_id: int, after_date: str, up_to: str
    ) -> tuple[int, int]:
        """The ``(sum(amount_minor), count)`` of ``account_id``'s transactions in
        the half-open window ``(after_date, up_to]`` — strictly after ``after_date``,
        no later than ``up_to`` (FIBR-0171 D1/INV-13). This is the roll-forward the
        forecast adds to a statement's closing balance to bring it current: rows on
        ``after_date`` (== the statement's ``period_end``) are already in the closing
        balance, and rows after ``up_to`` (== today) are future-dated. ``COALESCE``
        makes the zero-later-transactions case (a fresh statement) return ``(0, 0)``,
        not ``(NULL, 0)``; the count feeds ``AnchorSource.since_txn_count`` + the
        provenance line."""
        total, count = self._conn.execute(
            "SELECT COALESCE(SUM(amount_minor), 0), COUNT(*) FROM transactions "
            "WHERE account_id = ? AND occurred_on > ? AND occurred_on <= ?",
            (account_id, after_date, up_to),
        ).fetchone()
        return total, count

    def count_for_account(self, account_id: int) -> int:
        return self._conn.execute(
            "SELECT count(*) FROM transactions WHERE account_id = ?",
            (account_id,),
        ).fetchone()[0]

    def _commit(self) -> None:
        self._conn.commit()
