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

    run_migrations(conn)  # v2 -> v3 -> ... -> v8 (run_migrations walks to LATEST)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8

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
    run_migrations(conn)  # v2 -> v3 -> ... -> v8 (walks to LATEST)
    roots_before = len(CategoryRepository(conn).children_of(None))
    total_before = len(CategoryRepository(conn).list_all())

    run_migrations(conn)  # re-run: no-op at v8
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
    assert len(CategoryRepository(conn).children_of(None)) == roots_before == 2
    assert len(CategoryRepository(conn).list_all()) == total_before, "no duplicate seed"
    conn.close()


def test_INV4_first_run_vault_is_v8_with_seeded_tree(service):
    # Baseline-complete: a fresh first-run vault ends at v8 (v5->v6 added the
    # FIBR-0052 statement-provenance column, v6->v7 the FIBR-0010 category link);
    # the category tree is still seeded at v2->v3.
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
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


def test_INV7b_add_under_a_type_appears_in_that_branch(qtbot, service):
    from finbreak.ui.categories import CategoriesWidget

    income = _roots(service.vault.connection)["income"]
    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._name.setText("Consulting")
    widget._type.setCurrentIndex(widget._type.findData(income.id))
    widget._add_button.click()
    assert widget._error.text() == ""
    kids = {c.name for c in CategoryService(service.vault).children_of(income.id)}
    assert "Consulting" in kids


def test_INV7cd_select_loads_form_and_update_reparents(qtbot, service):
    from finbreak.ui.categories import CategoriesWidget

    svc = CategoryService(service.vault)
    roots = _roots(service.vault.connection)
    income, expenditure = roots["income"], roots["expenditure"]
    cat = svc.add_category(income.id, "Sundry")  # will be renamed + re-parented

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(cat.id)
    assert widget._name.text() == "Sundry", "selection loads the name into the form"

    widget._name.setText("Sundries")
    widget._type.setCurrentIndex(widget._type.findData(expenditure.id))
    widget._update_button.click()
    assert widget._error.text() == ""
    edited = CategoryRepository(service.vault.connection).get(cat.id)
    assert edited.name == "Sundries" and edited.parent_id == expenditure.id


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
    (indie-review UI-dialogs M1)"""
    from finbreak.errors import VaultLockedError
    from finbreak.ui.categories import CategoriesWidget

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
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
