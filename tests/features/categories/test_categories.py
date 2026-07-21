"""FIBR-0006 — P04 category tree. Enforces tests/features/categories/spec.md.

The self-referential `categories` table (two seeded Income/Expenditure roots +
default categories), its repository/service (CRUD, sibling-name validation,
delete + root guards), the category-manager `QTreeWidget` screen, and the
v2->v3 forward migration. Headless layers tested directly; the manager
round-trips (INV-7) use the pytest-qt `qtbot` fixture. Every on-disk vault uses
`tmp_path`; no test touches the network or real financial data (testing.md § 6).
"""

import logging
from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlcipher3.dbapi2 import IntegrityError

from conftest import _PW, build_v2_vault, keyed_connection, raising_conn
from finbreak.crypto import SALT_LEN, derive_key
from finbreak.errors import CategoryHasChildrenError, ProtectedCategoryError
from finbreak.migrations import (
    CATEGORY_ROOT_NAMES,
    DEFAULT_CATEGORIES,
    run_migrations,
)
from finbreak.models import CategoryKind
from finbreak.repositories.categories import CategoryRepository
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates to latest (tree seeded)
    yield svc
    svc.lock()


def _roots(conn) -> dict[str, object]:
    """The two Type roots, keyed by kind token."""
    roots = CategoryRepository(conn).children_of(None)
    return {r.kind: r for r in roots if r.kind is not None}


# --------------------------------------------------------------------------- #
# INV-1 — category model & CRUD round-trip
# --------------------------------------------------------------------------- #
def test_INV1_crud_roundtrip_and_order(service):
    svc = CategoryService(service.vault)
    income = _roots(service.vault.connection)["income"]

    # children_of(None) returns the two roots; a fresh child lands under one.
    bonus = svc.add_category(income.id, "Bonus")
    repo = CategoryRepository(service.vault.connection)
    got = repo.get(bonus.id)
    assert got is not None and got.name == "Bonus" and got.parent_id == income.id
    assert got.kind is None, "a child carries kind = NULL"
    # created_at is a well-formed ISO-8601 timestamp (fromisoformat raises if not).
    datetime.fromisoformat(got.created_at)

    # children_of(parent) is ordered by name, case-insensitive.
    children = svc.children_of(income.id)
    names = [c.name for c in children]
    assert names == sorted(names, key=str.casefold), "children ordered by name, ci"
    assert "Bonus" in names

    # list_all() is globally ordered (INV-1): the two roots (parent_id NULL)
    # sort ahead of every child, and the root tie breaks by name ci — so
    # "Expenditure" precedes "Income".
    ordered = repo.list_all()
    lead = ordered[: len([c for c in ordered if c.parent_id is None])]
    assert all(c.parent_id is None for c in lead), "roots lead the list"
    assert [c.name for c in lead] == ["Expenditure", "Income"], "roots by name, ci"

    svc.update_category(bonus.id, "Year-end bonus", income.id)
    assert repo.get(bonus.id).name == "Year-end bonus"

    svc.delete_category(bonus.id)
    assert repo.get(bonus.id) is None


def test_INV1_missing_id_update_and_delete_are_noops(service):
    repo = CategoryRepository(service.vault.connection)
    income = _roots(service.vault.connection)["income"]
    repo.delete(999_999)  # no row, no raise
    repo.update(999_999, "ghost", income.id)  # no row, no raise
    assert repo.get(999_999) is None


# --------------------------------------------------------------------------- #
# INV-2 — kind is a closed, non-translated set on the roots only
# --------------------------------------------------------------------------- #
def test_INV2_kind_is_closed_set_on_roots_only(service):
    assert [k.value for k in CategoryKind] == ["income", "expenditure"]
    roots = _roots(service.vault.connection)
    assert set(roots) == {"income", "expenditure"}, "both kinds present, verbatim"

    # Every non-root category carries kind = NULL.
    repo = CategoryRepository(service.vault.connection)
    non_roots = [c for c in repo.list_all() if c.parent_id is not None]
    assert non_roots, "the seed created some categories"
    assert all(c.kind is None for c in non_roots), "descendants carry kind = NULL"


# --------------------------------------------------------------------------- #
# INV-3 — name validation & sibling-uniqueness
# --------------------------------------------------------------------------- #
def test_INV3_rejects_empty_and_duplicate_sibling_names(service):
    svc = CategoryService(service.vault)
    roots = _roots(service.vault.connection)
    income, expenditure = roots["income"], roots["expenditure"]

    with pytest.raises(ValueError):
        svc.add_category(income.id, "   ")
    # "Salary" is a seeded Income child — a ci sibling duplicate is refused.
    with pytest.raises(ValueError):
        svc.add_category(income.id, "salary")
    # But the same name under a *different* Type is allowed (own namespace).
    ok = svc.add_category(expenditure.id, "Salary")
    assert ok.parent_id == expenditure.id


def test_INV3_name_stored_trimmed_and_update_allows_own_name(service):
    svc = CategoryService(service.vault)
    income = _roots(service.vault.connection)["income"]
    cat = svc.add_category(income.id, "  Freelance  ")
    assert cat.name == "Freelance", "stored trimmed"
    # Re-saving the same category with its own (unchanged) name is allowed.
    svc.update_category(cat.id, "Freelance", income.id)
    # Colliding with a *sibling's* name is refused.
    with pytest.raises(ValueError):
        svc.update_category(cat.id, "Salary", income.id)


# --------------------------------------------------------------------------- #
# INV-4 — v2->v3 migration: forward-only, atomic, idempotent, seeds the tree
# --------------------------------------------------------------------------- #
def test_INV4_v2_upgrades_to_v3_and_seeds_tree(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v2_vault(vault_path, sidecar_path, salt, [("2026-01-01", -100, "a")])

    conn = keyed_connection(vault_path, salt)
    before_tx = conn.execute(
        "SELECT id, amount_minor, description FROM transactions"
    ).fetchall()
    before_acct = conn.execute("SELECT id, name, type FROM accounts").fetchall()

    run_migrations(conn)  # v2 -> v3 -> ... -> v9 (run_migrations walks to LATEST)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 10

    roots = _roots(conn)
    assert set(roots) == {"income", "expenditure"}
    assert roots["income"].name == CATEGORY_ROOT_NAMES["income"]
    assert roots["expenditure"].name == CATEGORY_ROOT_NAMES["expenditure"]

    repo = CategoryRepository(conn)
    income_children = {c.name for c in repo.children_of(roots["income"].id)}
    exp_children = {c.name for c in repo.children_of(roots["expenditure"].id)}
    assert set(DEFAULT_CATEGORIES["income"]) == income_children
    assert set(DEFAULT_CATEGORIES["expenditure"]) == exp_children

    # transactions + accounts untouched by the v2->v3 step.
    assert (
        conn.execute(
            "SELECT id, amount_minor, description FROM transactions"
        ).fetchall()
        == before_tx
    )
    assert conn.execute("SELECT id, name, type FROM accounts").fetchall() == before_acct
    conn.close()


def test_INV4_atomic_rollback_leaves_v2_no_categories_table(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v2_vault(vault_path, sidecar_path, salt, [])

    conn = keyed_connection(vault_path, salt)

    with pytest.raises(RuntimeError):
        run_migrations(
            raising_conn(
                conn,
                "INSERT INTO categories",
                "injected failure at first category INSERT",
            )
        )

    # On the SAME connection, before any reopen: still v2, no categories table.
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 2
    assert (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='categories'"
        ).fetchone()
        is None
    ), "the categories CREATE was rolled back"
    conn.close()


def test_INV4_idempotent_at_latest(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v2_vault(vault_path, sidecar_path, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v2 -> v3 -> ... -> v9 (walks to LATEST)
    roots_before = len(CategoryRepository(conn).children_of(None))
    total_before = len(CategoryRepository(conn).list_all())

    run_migrations(conn)  # re-run: no-op at v9
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    assert len(CategoryRepository(conn).children_of(None)) == roots_before == 2
    assert len(CategoryRepository(conn).list_all()) == total_before, "no duplicate seed"
    conn.close()


def test_INV4_first_run_vault_is_v9_with_seeded_tree(service):
    # Baseline-complete: a fresh first-run vault ends at v9 (v5->v6 added the
    # FIBR-0052 statement-provenance column, v6->v7 the FIBR-0010 category link);
    # the category tree is still seeded at v2->v3.
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    assert set(_roots(conn)) == {"income", "expenditure"}


# --------------------------------------------------------------------------- #
# INV-5 — the tree is well-formed; root count can't change through the service
# --------------------------------------------------------------------------- #
def test_INV5_exactly_two_roots_and_defaults_parented(service):
    conn = service.vault.connection
    roots = CategoryRepository(conn).children_of(None)
    assert len(roots) == 2
    assert {r.kind for r in roots} == {"income", "expenditure"}
    assert all(r.parent_id is None for r in roots)

    root_ids = {r.id for r in roots}
    non_roots = [
        c for c in CategoryRepository(conn).list_all() if c.parent_id is not None
    ]
    assert non_roots, "seed created default categories"
    assert all(c.parent_id in root_ids for c in non_roots), "every default under a root"


def test_INV5_add_under_missing_parent_raises_integrity_error(service):
    # FK enforcement needs the Vault-opened (foreign_keys = ON) connection.
    repo = CategoryRepository(service.vault.connection)
    with pytest.raises(IntegrityError):
        repo.add(999_999, "orphan")


def test_INV5_service_guards_the_root_count(service):
    svc = CategoryService(service.vault)
    roots = _roots(service.vault.connection)
    income, expenditure = roots["income"], roots["expenditure"]

    # add / update with a None parent would mint a third root -> ValueError.
    with pytest.raises(ValueError):
        svc.add_category(None, "rogue root")
    child = svc.add_category(income.id, "Tips")
    with pytest.raises(ValueError):
        svc.update_category(child.id, "Tips", None)

    # Editing a root itself is refused (rename or re-parent) -> ProtectedCategoryError.
    with pytest.raises(ProtectedCategoryError):
        svc.update_category(income.id, "Earnings", expenditure.id)

    # None of that changed the two-root invariant.
    assert len(CategoryRepository(service.vault.connection).children_of(None)) == 2


def test_INV5_reparent_under_self_is_rejected(service):
    """A category can't be moved under itself — that would make its parent
    chain point at itself (FIBR-0141 cycle guard)."""
    svc = CategoryService(service.vault)
    income = _roots(service.vault.connection)["income"]
    cat = svc.add_category(income.id, "Sundry")
    with pytest.raises(ValueError, match="itself or one of its sub-categories"):
        svc.update_category(cat.id, "Sundry", cat.id)
    # Nothing moved: it still hangs under Income.
    repo = CategoryRepository(service.vault.connection)
    assert repo.get(cat.id).parent_id == income.id


def test_INV5_reparent_under_own_descendant_is_rejected(service):
    """Moving a category under one of its own descendants would create a cycle
    (X→Y→X). The service must refuse it (FIBR-0141)."""
    svc = CategoryService(service.vault)
    repo = CategoryRepository(service.vault.connection)
    income = _roots(service.vault.connection)["income"]
    # Income → A → B → C (a 3-deep chain under the root).
    a = svc.add_category(income.id, "A")
    b = svc.add_category(a.id, "B")
    c = svc.add_category(b.id, "C")

    # Direct child and a deeper descendant are both rejected.
    with pytest.raises(ValueError, match="itself or one of its sub-categories"):
        svc.update_category(a.id, "A", b.id)
    with pytest.raises(ValueError, match="itself or one of its sub-categories"):
        svc.update_category(a.id, "A", c.id)
    # A is untouched — still under Income.
    assert repo.get(a.id).parent_id == income.id


def test_INV5_legitimate_reparent_across_the_tree_still_works(service):
    """The cycle guard only blocks the subject's own subtree — moving a category
    to an unrelated branch (a non-descendant) is still allowed (FIBR-0141)."""
    svc = CategoryService(service.vault)
    repo = CategoryRepository(service.vault.connection)
    roots = _roots(service.vault.connection)
    income, expenditure = roots["income"], roots["expenditure"]
    a = svc.add_category(income.id, "Movable")
    b = svc.add_category(a.id, "Child")

    # Move the child B up under Expenditure (B is not its own descendant).
    svc.update_category(b.id, "Child", expenditure.id)
    assert repo.get(b.id).parent_id == expenditure.id
    # And the parent A can move under B's new sibling namespace too (Expenditure).
    svc.update_category(a.id, "Movable", expenditure.id)
    assert repo.get(a.id).parent_id == expenditure.id


# --------------------------------------------------------------------------- #
# INV-6 — delete guard (protect roots + block-with-children)
# --------------------------------------------------------------------------- #
def test_INV6_cannot_delete_a_root(service):
    svc = CategoryService(service.vault)
    income = _roots(service.vault.connection)["income"]
    with pytest.raises(ProtectedCategoryError):
        svc.delete_category(income.id)
    assert _roots(service.vault.connection).get("income") is not None, "nothing removed"


def test_INV6_cannot_delete_category_with_children(service):
    svc = CategoryService(service.vault)
    income = _roots(service.vault.connection)["income"]
    parent = svc.add_category(income.id, "Investments")
    # A sub-category (3rd level) added via the service to give the parent a child.
    svc.add_category(parent.id, "Dividends")
    with pytest.raises(CategoryHasChildrenError):
        svc.delete_category(parent.id)
    assert CategoryRepository(service.vault.connection).get(parent.id) is not None


def test_INV6_delete_childless_leaf_succeeds(service):
    svc = CategoryService(service.vault)
    income = _roots(service.vault.connection)["income"]
    leaf = svc.add_category(income.id, "Refunds")
    svc.delete_category(leaf.id)
    assert CategoryRepository(service.vault.connection).get(leaf.id) is None


def test_INV6_delete_missing_id_is_noop(service):
    svc = CategoryService(service.vault)
    before = len(CategoryRepository(service.vault.connection).list_all())
    svc.delete_category(999_999)  # neither guard fires, no-op
    assert len(CategoryRepository(service.vault.connection).list_all()) == before


# --------------------------------------------------------------------------- #
# INV-7 — category-manager UI round-trip (qtbot)
# --------------------------------------------------------------------------- #
def test_INV7a_tree_shows_two_types_with_seeded_children(qtbot, service):
    from finbreak.ui.categories import CategoriesWidget

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    tree = widget._tree
    assert tree.topLevelItemCount() == 2, "the two Type roots"
    labels = {tree.topLevelItem(i).text(0) for i in range(2)}
    assert labels == {widget.tr("Income"), widget.tr("Expenditure")}
    # Each Type node maps back to its stored kind token.
    kinds = {widget._kind_of_item(tree.topLevelItem(i)) for i in range(2)}
    assert kinds == {"income", "expenditure"}
    # Seeded defaults appear as children under a Type.
    total_children = sum(tree.topLevelItem(i).childCount() for i in range(2))
    assert total_children == len(DEFAULT_CATEGORIES["income"]) + len(
        DEFAULT_CATEGORIES["expenditure"]
    )


def test_FIBR0123_manager_sources_type_labels_from_shared_helper(
    qtbot, service, monkeypatch
):
    """INV-4: the manager's Type labels come from the shared category_type_labels()
    (one label source, no drift with the pickers) — not an inline dict. Proven by
    monkeypatching the helper and seeing the root labels follow."""
    import finbreak.ui.categories as categories_mod

    monkeypatch.setattr(
        categories_mod,
        "category_type_labels",
        lambda: {"income": "INC!", "expenditure": "EXP!"},
    )
    widget = categories_mod.CategoriesWidget(service)
    qtbot.addWidget(widget)
    tree = widget._tree
    labels = {tree.topLevelItem(i).text(0) for i in range(2)}
    assert labels == {"INC!", "EXP!"}, "root labels follow the shared helper"


# --------------------------------------------------------------------------- #
# FIBR-0154 — a 3rd tier (Type → Category → Sub-category). The redesigned
# CategoriesWidget anchors Add to the tree selection and re-parents via a
# dedicated subject-aware "Move under…" combo used by Update only. These tests
# replace the retired test_INV7b / test_INV7cd, which drove the removed
# roots-only ``_type`` combo (§ 7); their intent lives on in INV-2 / INV-7.
# --------------------------------------------------------------------------- #
def _child_named(svc, parent_id, name):
    """The direct child of ``parent_id`` named ``name`` (e.g. the seeded
    'Groceries' under the Expenditure root)."""
    return next(c for c in svc.children_of(parent_id) if c.name == name)


def _item_by_id(tree, category_id):
    """The QTreeWidgetItem carrying ``category_id`` anywhere in the tree, walked
    recursively — so finding a Level-3 node proves the render reaches depth 3."""
    from finbreak.ui.categories import _ID_ROLE

    def walk(item):
        if item.data(0, _ID_ROLE) == category_id:
            return item
        for i in range(item.childCount()):
            found = walk(item.child(i))
            if found is not None:
                return found
        return None

    for i in range(tree.topLevelItemCount()):
        found = walk(tree.topLevelItem(i))
        if found is not None:
            return found
    return None


def _move_under_ids(widget):
    """The set of category ids offered by the subject-aware 'Move under…' combo."""
    combo = widget._move_under
    return {combo.itemData(i) for i in range(combo.count())}


# INV-1 — the tree renders three levels.
def test_INV1_tree_renders_three_levels(qtbot, service):
    """INV-1: _refresh renders Type → Level-2 → Level-3 as nested items (seed
    Expenditure › Groceries › Spar via the service)."""
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    expenditure = _roots(service.vault.connection)["expenditure"]
    groceries = _child_named(svc, expenditure.id, "Groceries")
    spar = svc.add_category(groceries.id, "Spar")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    spar_item = _item_by_id(widget._tree, spar.id)
    assert spar_item is not None, "the Level-3 sub-category renders"
    assert spar_item.text(0) == "Spar"
    parent = spar_item.parent()
    assert parent is not None and parent.text(0) == "Groceries", "nested under Level-2"
    grandparent = parent.parent()
    assert grandparent is not None, "which is nested under the Type root"
    assert widget._kind_of_item(grandparent) == "expenditure"


# INV-2 — Add creates a child under the SELECTED node.
def test_INV2a_add_under_a_type_creates_a_level2(qtbot, service):
    """INV-2(a): with a Type selected, Add parents the new category onto THAT Type
    (Level-2) — the create-under-a-root path. Income is used (not the ci-first
    default Expenditure) so the assertion pins anchor-to-selection, never the old
    roots-combo default."""
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    income = _roots(service.vault.connection)["income"]

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(income.id)
    assert widget._add_button.isEnabled(), "Add is enabled with a Type selected"
    widget._name.setText("Consulting")
    widget._add_button.click()
    assert widget._error.text() == ""
    kids = {c.name for c in svc.children_of(income.id)}
    assert "Consulting" in kids, "parented onto the SELECTED Type (Income)"
    assert _child_named(svc, income.id, "Consulting").parent_id == income.id


def test_INV2b_add_under_a_category_creates_a_level3(qtbot, service):
    """INV-2(b): with a Level-2 Category selected, Add creates a Level-3
    sub-category under it — a parent the retired roots-only combo could never
    express."""
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    expenditure = _roots(service.vault.connection)["expenditure"]
    groceries = _child_named(svc, expenditure.id, "Groceries")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(groceries.id)
    assert widget._add_button.isEnabled()
    widget._name.setText("Spar")
    widget._add_button.click()
    assert widget._error.text() == ""
    kids = {c.name for c in svc.children_of(groceries.id)}
    assert "Spar" in kids, "the new node is a Level-3 child of Groceries"


# INV-3 — the UI caps depth at 3 (creation AND re-parent).
def test_INV3a_add_disabled_on_level3_and_no_selection(qtbot, service):
    """INV-3(a): Add is disabled when nothing is selected (no parent to add under)
    and on a Level-3 node (a child would be Level 4); enabled again on a Level-2."""
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    expenditure = _roots(service.vault.connection)["expenditure"]
    groceries = _child_named(svc, expenditure.id, "Groceries")
    spar = svc.add_category(groceries.id, "Spar")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    assert not widget._add_button.isEnabled(), "no selection -> Add disabled"
    widget._select_category(spar.id)
    assert not widget._add_button.isEnabled(), "Level-3 selected -> Add disabled (cap)"
    widget._select_category(groceries.id)
    assert widget._add_button.isEnabled(), "Level-2 selected -> Add enabled"


def test_INV3b_childed_level2_reparents_under_types_only(qtbot, service):
    """INV-3(b): a childed Level-2 (Groceries with child Spar) offers ONLY the two
    Types in 'Move under…' — moving it under another Level-2 (which would push its
    child to Level 4) is impossible from the UI."""
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    roots = _roots(service.vault.connection)
    income, expenditure = roots["income"], roots["expenditure"]
    groceries = _child_named(svc, expenditure.id, "Groceries")
    svc.add_category(groceries.id, "Spar")  # makes Groceries a childed Level-2

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(groceries.id)
    assert _move_under_ids(widget) == {income.id, expenditure.id}, "Types only"


def test_INV3c_childless_level2_reparents_under_types_and_categories(qtbot, service):
    """INV-3(c): a childless Level-2 (Fuel) offers {Types + the other Level-2
    Categories} but EXCLUDES itself (self-exclusion, only exercised when Level-2
    candidates are present)."""
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    roots = _roots(service.vault.connection)
    income, expenditure = roots["income"], roots["expenditure"]
    fuel = svc.add_category(expenditure.id, "Fuel")  # childless Level-2
    groceries = _child_named(svc, expenditure.id, "Groceries")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(fuel.id)
    offered = _move_under_ids(widget)
    assert {income.id, expenditure.id} <= offered, "both Types are offered"
    assert groceries.id in offered, "another Level-2 Category is offered"
    assert fuel.id not in offered, "the subject itself is excluded"


# INV-5 — a mid-tier Category stays assignable (a regression guard: the redesign
# leaves the service untouched, so this stays green).
def test_INV5_midtier_category_stays_assignable(service):
    """INV-5: after Groceries gains a Spar child, Groceries is still offered by the
    pickers and still a valid manual target."""
    from finbreak.repositories.accounts import AccountRepository
    from finbreak.repositories.transactions import TransactionRepository
    from finbreak.services.categorization import CategorizationService

    svc = CategoryService(service.vault)
    cs = CategorizationService(service.vault)
    expenditure = _roots(service.vault.connection)["expenditure"]
    groceries = _child_named(svc, expenditure.id, "Groceries")
    svc.add_category(groceries.id, "Spar")

    grouped_ids = {c.id for _t, cats in cs.leaf_categories_grouped() for c in cats}
    assert groceries.id in grouped_ids, "the mid-tier category is still offered"

    acct = AccountRepository(service.vault.connection).list_all()[0].id
    txn = TransactionRepository(service.vault.connection).add(
        acct, "2026-01-05", -1000, "GROCERY RUN"
    )
    cs.set_manual_category(txn, groceries.id)  # must not raise — a mid-tier is a leaf
    row = service.vault.connection.execute(
        "SELECT category_id FROM transactions WHERE id = ?", (txn,)
    ).fetchone()
    assert row[0] == groceries.id


# INV-7 — rename, re-parent & delete at all three levels.
def test_INV7a_rename_level3_keeps_parent(qtbot, service):
    """INV-7(a): rename a Level-3 sub-category via Update — the name changes and
    parent_id is unchanged."""
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    expenditure = _roots(service.vault.connection)["expenditure"]
    groceries = _child_named(svc, expenditure.id, "Groceries")
    spar = svc.add_category(groceries.id, "Spar")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(spar.id)
    widget._name.setText("Pick n Pay")
    widget._update_button.click()
    assert widget._error.text() == ""
    edited = CategoryRepository(service.vault.connection).get(spar.id)
    assert edited.name == "Pick n Pay"
    assert edited.parent_id == groceries.id, "a rename leaves the parent unchanged"


def test_INV7b_pure_reparent_via_move_under_keeps_name(qtbot, service):
    """INV-7(b): a childless Level-2 (Fuel) with an EMPTY name field + a 'Move
    under…' change re-parents (parent_id updates) AND keeps the current name
    (empty ⇒ keep-current-name — the assertion the retired test_INV7cd carried,
    § 7). The name field starts empty; the current name is placeholder only
    (§ 4.2), so a pure re-parent never trips the service's empty-name guard."""
    from finbreak.ui._widgets import select_combo_data
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    roots = _roots(service.vault.connection)
    income, expenditure = roots["income"], roots["expenditure"]
    fuel = svc.add_category(expenditure.id, "Fuel")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(fuel.id)
    assert widget._name.text() == "", "the name field starts empty (placeholder only)"
    select_combo_data(widget._move_under, income.id)
    widget._update_button.click()
    assert widget._error.text() == ""
    edited = CategoryRepository(service.vault.connection).get(fuel.id)
    assert edited.parent_id == income.id, "the re-parent executed"
    assert edited.name == "Fuel", "an empty name field keeps the current name"


def test_INV7c_delete_childed_refused_and_childless_leaf_succeeds(
    qtbot, service, monkeypatch
):
    """INV-7(c): deleting a Level-2 that HAS children is refused (message shown,
    nothing removed); a childless Level-3 leaf deletes. Reaching the Level-3 node
    to delete it also exercises _select_category recursing to depth 3."""
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    expenditure = _roots(service.vault.connection)["expenditure"]
    groceries = _child_named(svc, expenditure.id, "Groceries")
    spar = svc.add_category(groceries.id, "Spar")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    widget._select_category(groceries.id)  # Level-2 with a child
    widget._delete_button.click()
    assert widget._error.text() != "", "deleting a childed category is refused"
    assert CategoryRepository(service.vault.connection).get(groceries.id) is not None

    widget._select_category(spar.id)  # childless Level-3
    widget._delete_button.click()
    assert CategoryRepository(service.vault.connection).get(spar.id) is None


def test_INV7e_delete_childless_removes_from_tree(qtbot, service, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    income = _roots(service.vault.connection)["income"]
    leaf = svc.add_category(income.id, "Rebates")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(leaf.id)
    # A delete now asks for confirmation (the FIBR-0010 blast-radius prompt); accept.
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    widget._delete_button.click()
    assert widget._error.text() == ""
    assert CategoryRepository(service.vault.connection).get(leaf.id) is None


def test_INV7f_root_disables_actions_and_child_reenables(qtbot, service):
    from finbreak.ui.categories import CategoriesWidget

    income = _roots(service.vault.connection)["income"]
    child = CategoryService(service.vault).add_category(income.id, "Tips")

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(income.id)  # select a Type root
    assert not widget._update_button.isEnabled(), "a root can't be edited"
    assert not widget._delete_button.isEnabled(), "a root can't be deleted"

    # The disable is per-selection: re-selecting a category re-enables them.
    widget._select_category(child.id)
    assert widget._update_button.isEnabled(), "a category can be edited"
    assert widget._delete_button.isEnabled(), "a category can be deleted"


# --------------------------------------------------------------------------- #
# INV-8 — no secret logged across a category add->update->delete cycle
# --------------------------------------------------------------------------- #
def test_INV8_category_cycle_logs_no_secret(service, caplog):
    password = _PW.decode()
    income = _roots(service.vault.connection)["income"]
    with caplog.at_level(logging.INFO, logger="finbreak"):
        svc = CategoryService(service.vault)
        cat = svc.add_category(income.id, "Royalties")
        svc.update_category(cat.id, "Royalty income", income.id)
        svc.delete_category(cat.id)

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert password not in joined, "the master password must never be logged"
    params = service.load_params()
    key = derive_key(bytearray(_PW), params.salt, params)
    assert bytes(key).hex() not in joined, "the derived key (hex) must never be logged"


def test_add_category_swallows_vault_locked_silently(qtbot, service, monkeypatch):
    """An auto-lock mid-add returns silently, matching the delete handler.
    (indie-review UI-dialogs M1). Post-FIBR-0154 ``_on_add`` is anchored to the
    tree selection, so a parent Type is selected first — otherwise the
    selection-guard returns early and the monkeypatched ``add_category`` (the
    swallow path under test) never runs (a vacuous green, § 7)."""
    from finbreak.errors import VaultLockedError
    from finbreak.ui.categories import CategoriesWidget

    income = _roots(service.vault.connection)["income"]
    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(income.id)  # anchor Add to a Type parent
    widget._name.setText("New")

    def locked(*a, **k):
        raise VaultLockedError("the vault is locked")

    monkeypatch.setattr(widget._categories, "add_category", locked)
    widget._on_add()  # must not raise
    assert widget._error.text() == "", "VaultLockedError is swallowed silently"


def test_add_category_unknown_parent_raises(service):
    """add_category under a non-existent parent id raises the _require_parent
    'no category with id' ValueError (FIBR-0064) — distinct from the None-parent
    'must have a parent Type' branch already covered."""
    svc = CategoryService(service.vault)
    with pytest.raises(ValueError, match="no category with id"):
        svc.add_category(999999, "Orphan")
