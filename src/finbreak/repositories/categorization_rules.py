"""CategorizationRuleRepository — CRUD over the ``categorization_rules`` table
(FIBR-0010 D5), mirroring ``CategoryRepository``.

Persistence only; pattern / leaf validation and the top-insert priority live in
``CategorizationService``. The **standalone-manager** writes commit per-write
(like ``CategoryRepository``); the methods the delete-category **cascade** shares
(``delete_for_category``) are **commit-free** — the owning ``CategoryService``
transaction commits (the FIBR-0059 convention).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import CategorizationRule
from finbreak.repositories import last_insert_id

# The SELECT column list is written literally in each query so it shares the
# ``CategorizationRule`` dataclass field order — ``id, pattern, category_id,
# priority, created_at`` — keeping ``CategorizationRule(*row)`` aligned.


class CategorizationRuleRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def list_all(self) -> list[CategorizationRule]:
        """Every rule in first-match order — ascending ``priority``, then ``id``
        as the deterministic tiebreak for equal priorities (D3/D7)."""
        rows = self._conn.execute(
            "SELECT id, pattern, category_id, priority, created_at "
            "FROM categorization_rules ORDER BY priority, id"
        ).fetchall()
        return [CategorizationRule(*row) for row in rows]

    def get(self, rule_id: int) -> CategorizationRule | None:
        row = self._conn.execute(
            "SELECT id, pattern, category_id, priority, created_at "
            "FROM categorization_rules WHERE id = ?",
            (rule_id,),
        ).fetchone()
        return CategorizationRule(*row) if row is not None else None

    def add(self, pattern: str, category_id: int, priority: int) -> int:
        cursor = self._conn.execute(
            "INSERT INTO categorization_rules"
            "(pattern, category_id, priority, created_at) VALUES (?, ?, ?, ?)",
            (pattern, category_id, priority, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
        return last_insert_id(cursor)

    def update(self, rule_id: int, pattern: str, category_id: int) -> None:
        """Edit a rule's pattern + target leaf, leaving ``priority`` untouched (an
        edit is not a re-prioritise — Move up/down owns that, D6/D7)."""
        self._conn.execute(
            "UPDATE categorization_rules SET pattern = ?, category_id = ? WHERE id = ?",
            (pattern, category_id, rule_id),
        )
        self._conn.commit()

    def delete(self, rule_id: int) -> None:
        self._conn.execute("DELETE FROM categorization_rules WHERE id = ?", (rule_id,))
        self._conn.commit()

    def set_priority(self, rule_id: int, priority: int) -> None:
        """Set one rule's priority (the two-row swap behind Move up/down, D7).
        **Commit-free** — the owning ``CategorizationService.move_rule``
        transaction commits, so the two-row swap is one atomic unit and a
        mid-swap failure rolls back cleanly (indie-review M-C1)."""
        self._conn.execute(
            "UPDATE categorization_rules SET priority = ? WHERE id = ?",
            (priority, rule_id),
        )

    def min_priority(self) -> int | None:
        """The smallest (top) priority, or ``None`` when there are no rules — the
        top-insert anchor (D6: a new rule takes ``min_priority() - 1``)."""
        row = self._conn.execute(
            "SELECT min(priority) FROM categorization_rules"
        ).fetchone()
        return row[0]

    def count_for_category(self, category_id: int) -> int:
        """How many rules target ``category_id`` (the INV-8 blast radius; shape-
        mirror of ``TransactionRepository.count_for_account``)."""
        return self._conn.execute(
            "SELECT count(*) FROM categorization_rules WHERE category_id = ?",
            (category_id,),
        ).fetchone()[0]

    def delete_for_category(self, category_id: int) -> int:
        """Delete every rule targeting ``category_id`` and return the rowcount.
        **Commit-free** — invoked inside ``CategoryService``'s owned delete
        transaction, before the category row is removed (INV-7)."""
        return self._conn.execute(
            "DELETE FROM categorization_rules WHERE category_id = ?", (category_id,)
        ).rowcount
