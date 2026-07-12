"""TransferRepository — candidate detection + the ``transfer_pairs`` decision store
(FIBR-0011).

Detection is a single SQL self-join (``candidate_pairs``, the sole home of the
INV-2 match rule); each decision (confirm/reject) is one per-write commit like
``TransactionRepository.add`` (there is no multi-statement unit to wrap, D6).
``add_decision`` stores the pair in canonical order (``min`` as ``txn_a_id``,
``max`` as ``txn_b_id``, D4) so ``UNIQUE(txn_a_id, txn_b_id)`` holds regardless of
which side the caller passes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import TransferPair

# The inclusive ±day window an inter-account debit and credit may differ by and
# still pair (INV-2 / ADR-0006). Its ONE home — ``candidate_pairs`` reads this
# module global **at call time** and binds it as ``:window``, so a test can
# ``monkeypatch.setattr`` it and watch the boundary move; the query and INV-2
# cannot drift because the literal 3 lives nowhere else.
TRANSFER_WINDOW_DAYS = 3

# The "already in a confirmed pair" check (INV-4) is spelled out as a literal
# NOT EXISTS / direct WHERE in each query below rather than factored into a
# constant + f-string: the codebase keeps SQL a plain literal, never an
# interpolated string bandit reads as an injection vector (B608) — same posture
# as statement_periods.py / import_profiles.py.


class TransferRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def candidate_pairs(self) -> list[tuple[int, int]]:
        """Every undecided candidate as ``(debit_id, credit_id)`` (INV-2). A
        self-join: equal magnitude / opposite sign (``c.amount_minor =
        -d.amount_minor``), different accounts, within ``TRANSFER_WINDOW_DAYS``
        inclusive; the sign split fixes ``d`` as the debit and ``c`` as the credit
        so each unordered pair appears once. Excludes any txn already in a confirmed
        pair (INV-4) and any pair already confirmed *or* rejected (INV-3)."""
        rows = self._conn.execute(
            "SELECT d.id, c.id "
            "FROM transactions d "
            "JOIN transactions c "
            "  ON c.amount_minor = -d.amount_minor "
            " AND c.account_id <> d.account_id "
            " AND abs(julianday(c.occurred_on) - julianday(d.occurred_on)) <= :window "
            "WHERE d.amount_minor < 0 AND c.amount_minor > 0 "
            # neither side already consumed by a confirmed pair (INV-4)
            "  AND NOT EXISTS (SELECT 1 FROM transfer_pairs p "
            "                  WHERE p.status = 'confirmed' "
            "                    AND (p.txn_a_id = d.id OR p.txn_b_id = d.id)) "
            "  AND NOT EXISTS (SELECT 1 FROM transfer_pairs p "
            "                  WHERE p.status = 'confirmed' "
            "                    AND (p.txn_a_id = c.id OR p.txn_b_id = c.id)) "
            # this specific pair not already confirmed OR rejected (INV-3)
            "  AND NOT EXISTS (SELECT 1 FROM transfer_pairs p "
            "                  WHERE p.txn_a_id = min(d.id, c.id) "
            "                    AND p.txn_b_id = max(d.id, c.id)) "
            "ORDER BY d.occurred_on, d.id, c.id",
            {"window": TRANSFER_WINDOW_DAYS},
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def add_decision(self, txn_a_id: int, txn_b_id: int, status: str) -> int:
        """Record one decision about a pair, in canonical order, and return its new
        id. One INSERT + commit — atomic on its own (D6). The caller (the service)
        has already checked the pair is undecided, so the ``UNIQUE`` constraint is a
        backstop, not the guard."""
        low, high = min(txn_a_id, txn_b_id), max(txn_a_id, txn_b_id)
        cursor = self._conn.execute(
            "INSERT INTO transfer_pairs(txn_a_id, txn_b_id, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            (low, high, status, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def delete_confirmed(self, pair_id: int) -> int:
        """Delete a **confirmed** pair by id (unlink, INV-6), returning the rowcount.
        The ``AND status = 'confirmed'`` filter means an unlink can never delete a
        remembered ``'rejected'`` row by id — a rejected/absent id is a no-op."""
        rowcount = self._conn.execute(
            "DELETE FROM transfer_pairs WHERE id = ? AND status = 'confirmed'",
            (pair_id,),
        ).rowcount
        self._conn.commit()
        return rowcount

    def list_confirmed(self) -> list[TransferPair]:
        """Every confirmed pair, oldest first (``ORDER BY created_at, id`` — a
        deterministic Confirmed-table order the tests index into)."""
        rows = self._conn.execute(
            "SELECT id, txn_a_id, txn_b_id, status, created_at FROM transfer_pairs "
            "WHERE status = 'confirmed' ORDER BY created_at, id"
        ).fetchall()
        return [TransferPair(*row) for row in rows]

    def confirmed_txn_ids(self) -> set[int]:
        """The union of both ids of every confirmed pair — the INV-5 exclusion set
        (only confirmed; a rejection excludes nothing)."""
        rows = self._conn.execute(
            "SELECT txn_a_id FROM transfer_pairs WHERE status = 'confirmed' "
            "UNION SELECT txn_b_id FROM transfer_pairs WHERE status = 'confirmed'"
        ).fetchall()
        return {row[0] for row in rows}

    def is_confirmed(self, txn_id: int) -> bool:
        """Whether ``txn_id`` already belongs to a confirmed pair (the INV-4 guard)."""
        return (
            self._conn.execute(
                "SELECT 1 FROM transfer_pairs WHERE status = 'confirmed' "
                "AND (txn_a_id = ? OR txn_b_id = ?) LIMIT 1",
                (txn_id, txn_id),
            ).fetchone()
            is not None
        )

    def pair_decided(self, txn_a_id: int, txn_b_id: int) -> bool:
        """Whether this canonical pair already has a row of **any** status — the D5
        undecided-pair guard (``UNIQUE`` spans both statuses, so an insert must be
        preceded by this check to raise ``ValueError`` not ``IntegrityError``)."""
        low, high = min(txn_a_id, txn_b_id), max(txn_a_id, txn_b_id)
        return (
            self._conn.execute(
                "SELECT 1 FROM transfer_pairs WHERE txn_a_id = ? AND txn_b_id = ? "
                "LIMIT 1",
                (low, high),
            ).fetchone()
            is not None
        )
