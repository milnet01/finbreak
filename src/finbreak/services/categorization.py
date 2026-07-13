"""CategorizationService — the rules engine, manual override, and learning
(FIBR-0010).

Two module functions carry the pure/commit-free core so both the service's owned
transaction and the import / delete-cascade transactions can reuse them:

- ``categorize(description, rules)`` — the pure first-match matcher (no DB).
- ``recategorize_auto_rows(conn)`` — recompute every **auto** row from the current
  rules, writing only rows that change, returning the changed count. Commit-free;
  the caller owns the transaction.

The golden rule (INV-1): recompute every auto row, never touch a manual row. A
manual row is frozen — the ``auto_rows`` predicate excludes it, so it is never in
the read set.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal, cast

from sqlcipher3 import dbapi2

from finbreak.db import owned_transaction
from finbreak.models import CategorizationRule, Category, CategoryKind, CategorySource
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.categorization_rules import CategorizationRuleRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.text import normalise_text
from finbreak.vault import Vault

log = logging.getLogger(__name__)


def categorize(description: str, rules: Sequence[CategorizationRule]) -> int | None:
    """The first matching rule's ``category_id`` (rules in ascending priority, then
    id — the order ``list_all`` returns), or ``None`` when none matches or the rule
    set is empty. Both sides are ``normalise_text``-folded, then substring-matched."""
    normalised = normalise_text(description)
    for rule in rules:
        if normalise_text(rule.pattern) in normalised:
            return rule.category_id
    return None


def recategorize_auto_rows(conn: dbapi2.Connection) -> int:
    """Recompute every **auto** row from the current rules; write only the rows that
    change; return that changed count (INV-1/INV-4/INV-13). Commit-free — the caller
    (``apply_rules`` / ``commit_import`` / the delete cascade) owns the transaction."""
    rules = CategorizationRuleRepository(conn).list_all()
    tx_repo = TransactionRepository(conn)
    changed = 0
    for txn_id, description in tx_repo.auto_rows():
        match = categorize(description, rules)
        source = CategorySource.RULE.value if match is not None else None
        changed += tx_repo.set_category(txn_id, match, source)
    return changed


class CategorizationService:
    def __init__(self, vault: Vault):
        self._vault = vault

    @property
    def _conn(self) -> dbapi2.Connection:
        return self._vault.connection

    def _rules(self) -> CategorizationRuleRepository:
        return CategorizationRuleRepository(self._conn)

    # -- reads ----------------------------------------------------------------
    def list_rules(self) -> list[CategorizationRule]:
        return self._rules().list_all()

    def leaf_categories(self) -> list[Category]:
        """The assignable (non-root) categories — the leaves a rule / manual pick
        may target (INV-9). The two Type roots (``parent_id IS NULL``) are excluded."""
        return [
            c
            for c in CategoryRepository(self._conn).list_all()
            if c.parent_id is not None
        ]

    def leaf_categories_grouped(self) -> list[tuple[str, list[Category]]]:
        """The assignable categories grouped by Type — income section then
        expenditure, each name-sorted (casefold), an empty section omitted
        (FIBR-0123 INV-1/INV-2). Each category's Type is the ``kind`` of the root
        reached by ascending ``parent_id`` (D3, depth-safe — never a one-hop
        lookup that would drop a deeper node). The tuple's first element is the
        untranslated ``CategoryKind`` token (``"income"`` / ``"expenditure"``),
        never a display label — labelling belongs to the UI layer (INV-4)."""
        all_categories = CategoryRepository(self._conn).list_all()
        by_id = {c.id: c for c in all_categories}
        buckets: dict[str, list[Category]] = {
            CategoryKind.INCOME.value: [],
            CategoryKind.EXPENDITURE.value: [],
        }
        for category in all_categories:
            if category.parent_id is None:
                continue  # a Type root is not itself assignable
            root = category
            seen: set[int] = set()
            while root.parent_id is not None:
                seen.add(root.id)
                root = by_id[root.parent_id]
                if root.id in seen:
                    # A well-formed tree ascends to a root in a few hops; a cycle
                    # (only reachable by a direct reparent, not via the UI) would
                    # otherwise loop forever. Fail loud on corrupt data.
                    raise ValueError(
                        "category parent chain contains a cycle; cannot resolve Type"
                    )
            # The ascent always terminates at a Type root, and the only two roots
            # (FIBR-0006 INV-5) both carry a kind — so root.kind is a real token
            # here (D3). cast narrows str|None -> str without a runtime guard,
            # matching the codebase's known-non-None idiom (no assert in src).
            buckets[cast(str, root.kind)].append(category)
        return [
            (token, sorted(cats, key=lambda c: c.name.casefold()))
            for token, cats in buckets.items()
            if cats
        ]

    def would_categorize(self, description: str) -> int | None:
        """The category the **current** rules would assign to ``description`` (the
        learning "differs" check, D11) — computed against the rules as they stand."""
        return categorize(description, self._rules().list_all())

    # -- rule management (each write is one owned transaction) ----------------
    def add_rule(self, pattern: str, category_id: int) -> CategorizationRule:
        """Validate + insert a rule at the **top** (highest priority, INV-6). Does
        NOT auto-apply (INV-4) — the manager's Apply / the learning re-apply own
        that. Raises ``ValueError`` on an empty pattern or a non-leaf target."""
        pattern = self._validate(pattern, category_id)
        repo = self._rules()
        priority = (repo.min_priority() or 0) - 1  # a genuine 0 min is fine: -1 < 0
        rule_id = repo.add(pattern, category_id, priority)
        log.info("categorization rule created")
        return cast(CategorizationRule, repo.get(rule_id))

    def update_rule(self, rule_id: int, pattern: str, category_id: int) -> None:
        """Edit a rule's pattern + target with the **same** validation as add;
        leaves priority unchanged and does NOT auto-apply (INV-4/INV-9)."""
        pattern = self._validate(pattern, category_id)
        self._rules().update(rule_id, pattern, category_id)
        log.info("categorization rule updated")

    def delete_rule(self, rule_id: int) -> None:
        self._rules().delete(rule_id)
        log.info("categorization rule deleted")

    def move_rule(self, rule_id: int, direction: Literal["up", "down"]) -> None:
        """Swap this rule's priority with its neighbour in the current order (a
        no-op at the ends, D7). "up" = towards the top (smaller priority)."""
        ordered = self._rules().list_all()
        index = next((i for i, r in enumerate(ordered) if r.id == rule_id), None)
        if index is None:
            return
        neighbour = index - 1 if direction == "up" else index + 1
        if neighbour < 0 or neighbour >= len(ordered):
            return  # already at the end
        this, other = ordered[index], ordered[neighbour]
        # One owned transaction so the two-row swap is atomic — a mid-swap
        # failure can't leave two rules sharing a priority (indie-review M-C1).
        conn = self._conn
        repo = CategorizationRuleRepository(conn)
        with owned_transaction(conn):
            repo.set_priority(this.id, other.priority)
            repo.set_priority(other.id, this.priority)

    def apply_rules(self) -> int:
        """Re-file every auto row from the current rules, in one owned transaction,
        and return the changed-row count (INV-4/INV-13)."""
        conn = self._conn
        with owned_transaction(conn):
            changed = recategorize_auto_rows(conn)
        log.info("rules applied")
        return changed

    def set_manual_category(self, txn_id: int, category_id: int | None) -> None:
        """Freeze a transaction's category by hand (INV-1): set ``category_id`` +
        ``'manual'`` in one owned transaction. ``None`` is a deliberate clear
        (``NULL``/``'manual'``), which no rule run re-fills (INV-3)."""
        # INV-9: a manual pick, like a rule target, must be a leaf — never a Type
        # root. The picker UI only offers leaves, but enforce it at the service
        # boundary too so no other caller can pin a root (a root's id is a valid
        # FK, so SQLite won't catch it). None is a deliberate clear. (M-core1)
        if category_id is not None:
            self._require_leaf(category_id)
        conn = self._conn
        tx_repo = TransactionRepository(conn)
        with owned_transaction(conn):
            tx_repo.set_category(txn_id, category_id, CategorySource.MANUAL.value)
        log.info("transaction category set manually")

    # -- helpers --------------------------------------------------------------
    def _validate(self, pattern: str, category_id: int) -> str:
        """The trimmed pattern, or ``ValueError``: non-empty pattern + an existing
        **leaf** (non-root) target (INV-9)."""
        pattern = pattern.strip()
        if not pattern:
            raise ValueError("a rule pattern must not be empty")
        self._require_leaf(category_id)
        return pattern

    def _require_leaf(self, category_id: int) -> None:
        """The shared INV-9 guard for a rule target AND a manual pick: the category
        exists and is a leaf (``parent_id is not None``), never a Type root. Mirrors
        ``CategoryService``'s root check."""
        category = CategoryRepository(self._conn).get(category_id)
        if category is None or category.parent_id is None:
            raise ValueError("a category must be a leaf, not a Type")
