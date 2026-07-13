"""CategoryRepository — CRUD over the self-referential ``categories`` table
(FIBR-0006 INV-1).

Persistence only; name/sibling validation, the root guard, and the
block-with-children guard live in ``CategoryService``. Each write is one
explicit transaction, mirroring ``AccountRepository``'s commit seam. ``add``
only ever inserts a **child** (``kind = NULL``) — the two Type roots are seeded
solely by the v2->v3 migration.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.models import Category
from finbreak.repositories import last_insert_id

# The SELECT column list is written literally in each query (not interpolated)
# so it shares the ``Category`` dataclass's field order — ``id, parent_id, name,
# kind, created_at`` — keeping ``Category(*row)`` aligned (id/parent_id are
# adjacent ints, so a swap would compile but corrupt).


class CategoryRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def add(self, parent_id: int, name: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO categories(parent_id, name, kind, created_at) "
            "VALUES (?, ?, NULL, ?)",
            (parent_id, name, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
        return last_insert_id(cursor)

    def list_all(self) -> list[Category]:
        # NULL parent_id (the roots) sorts first under SQLite's default ASC.
        rows = self._conn.execute(
            "SELECT id, parent_id, name, kind, created_at FROM categories "
            "ORDER BY parent_id, name COLLATE NOCASE, id"
        ).fetchall()
        return [Category(*row) for row in rows]

    def children_of(self, parent_id: int | None) -> list[Category]:
        """Direct children of ``parent_id``; ``None`` returns the two Type roots
        (``WHERE parent_id IS NULL`` — ``= NULL`` matches no row in SQL)."""
        if parent_id is None:
            rows = self._conn.execute(
                "SELECT id, parent_id, name, kind, created_at "
                "FROM categories WHERE parent_id IS NULL "
                "ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, parent_id, name, kind, created_at "
                "FROM categories WHERE parent_id = ? "
                "ORDER BY name COLLATE NOCASE, id",
                (parent_id,),
            ).fetchall()
        return [Category(*row) for row in rows]

    def get(self, category_id: int) -> Category | None:
        row = self._conn.execute(
            "SELECT id, parent_id, name, kind, created_at FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        return Category(*row) if row is not None else None

    def update(self, category_id: int, name: str, parent_id: int) -> None:
        self._conn.execute(
            "UPDATE categories SET name = ?, parent_id = ? WHERE id = ?",
            (name, parent_id, category_id),
        )
        self._conn.commit()

    def delete(self, category_id: int) -> None:
        self._conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        self._conn.commit()
