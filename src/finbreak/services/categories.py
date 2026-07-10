"""CategoryService — validation + the root / children guards around
CategoryRepository.

Owns name validation + sibling-uniqueness (FIBR-0006 INV-3), the root-count
guards (INV-5: ``add``/``update`` reject a ``None`` parent; ``update`` refuses
editing a root), and the delete guard (INV-6: a root or a category with children
is blocked). The two Type roots are seeded only by the migration; the service
only ever creates / edits **children** (``kind = NULL``).
"""

from __future__ import annotations

import logging
from typing import cast

from finbreak.errors import CategoryHasChildrenError, ProtectedCategoryError
from finbreak.models import Category
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.categorization_rules import CategorizationRuleRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.categorization import recategorize_auto_rows
from finbreak.vault import Vault

log = logging.getLogger(__name__)


class CategoryService:
    def __init__(self, vault: Vault):
        self._vault = vault

    def _categories(self) -> CategoryRepository:
        return CategoryRepository(self._vault.connection)

    def list_all(self) -> list[Category]:
        return self._categories().list_all()

    def children_of(self, parent_id: int | None) -> list[Category]:
        return self._categories().children_of(parent_id)

    def add_category(self, parent_id: int | None, name: str) -> Category:
        repo = self._categories()
        parent = self._require_parent(parent_id, repo)
        name = self._validate(name, parent.id, repo)
        category_id = repo.add(parent.id, name)
        log.info("category created")
        # get() is Optional; the row was just inserted, so it is present.
        return cast(Category, repo.get(category_id))

    def update_category(
        self, category_id: int, name: str, parent_id: int | None
    ) -> None:
        repo = self._categories()
        target = repo.get(category_id)
        # A root subject can't be renamed or re-parented — checked first, so
        # editing a root raises even when the destination parent is also bad.
        if target is not None and target.parent_id is None:
            raise ProtectedCategoryError(
                "a Type (Income / Expenditure) cannot be edited"
            )
        parent = self._require_parent(parent_id, repo)
        name = self._validate(name, parent.id, repo, exclude_id=category_id)
        repo.update(category_id, name, parent.id)
        log.info("category updated")

    def delete_category(self, category_id: int) -> None:
        """Delete a leaf category and cleanly unwind everything that pointed at it,
        in **one** owned transaction (FIBR-0010 INV-7): (1) clear + reset its
        transactions to auto, (2) delete its rules, (3) delete the category, (4)
        re-apply so the freed auto rows are re-filed (or blanked). ``ROLLBACK`` on
        any failure leaves a re-openable vault. Order matters — the references are
        cleared before the category row is deleted, so ``foreign_keys = ON`` permits
        it."""
        repo = self._categories()
        target = repo.get(category_id)
        if target is not None and target.parent_id is None:
            raise ProtectedCategoryError(
                "a Type (Income / Expenditure) cannot be deleted"
            )
        if repo.children_of(category_id):
            raise CategoryHasChildrenError(
                "this category still has sub-categories — remove them first"
            )
        conn = self._vault.connection
        conn.execute("BEGIN")  # first statement — own the whole cascade
        try:
            TransactionRepository(conn).clear_category_for(category_id)
            CategorizationRuleRepository(conn).delete_for_category(category_id)
            # repo.delete() commits, which would end this transaction early; issue
            # the delete in-line (commit-free) so all four steps are one atomic unit.
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            recategorize_auto_rows(conn)
            conn.commit()
        except Exception:
            conn.rollback()  # nothing changed — a re-openable vault (INV-7)
            raise
        log.info("category deleted")

    def delete_blast_radius(self, category_id: int) -> tuple[int, int]:
        """The ``(transaction_count, rule_count)`` a delete would touch (INV-8) —
        read pre-delete via the two repos so the confirmation can name both counts.
        The UI calls this, never a repository (the codebase's layering)."""
        conn = self._vault.connection
        txn_count = TransactionRepository(conn).count_for_category(category_id)
        rule_count = CategorizationRuleRepository(conn).count_for_category(category_id)
        return (txn_count, rule_count)

    def _require_parent(
        self, parent_id: int | None, repo: CategoryRepository
    ) -> Category:
        """A category hangs under an existing parent; a ``None`` parent would
        mint a third root (roots are migration-only, INV-5)."""
        if parent_id is None:
            raise ValueError("a category must have a parent Type")
        parent = repo.get(parent_id)
        if parent is None:
            raise ValueError(f"no category with id {parent_id}")
        return parent

    def _validate(
        self,
        name: str,
        parent_id: int,
        repo: CategoryRepository,
        exclude_id: int | None = None,
    ) -> str:
        """Return the trimmed name, or raise ``ValueError`` (INV-3): non-empty +
        unique among siblings (same parent, case-insensitive)."""
        name = name.strip()
        if not name:
            raise ValueError("category name must not be empty")
        lowered = name.casefold()
        for sibling in repo.children_of(parent_id):
            if sibling.id == exclude_id:
                continue
            if sibling.name.casefold() == lowered:
                raise ValueError(f"a category named {name!r} already exists here")
        return name
