"""FIBR-0010 — P08 rules engine + manual override + learning.

Enforces tests/features/categorisation/spec.md. The pure matcher
(`categorize`), the commit-free apply routine (`recategorize_auto_rows`), the
`CategorizationService` (rules CRUD + reorder + manual set + would/apply), the
`CategorizationRuleRepository`, the extended `TransactionRepository`, the atomic
delete-category cascade + blast-radius on `CategoryService`, the shared text
normaliser, and the v6->v7 migration. Headless layers are tested directly; the
Home category column / context set, the learning offer, the Rules tab, and the
blast-radius confirm use the pytest-qt `qtbot` fixture. Every on-disk vault uses
`tmp_path`; no test touches the network or real financial data (testing.md § 6).
"""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from conftest import _PW, RuleStub, build_v6_vault, keyed_connection, raising_conn
from finbreak.crypto import SALT_LEN
from finbreak.errors import VaultLockedError
from finbreak.migrations import LATEST_SCHEMA_VERSION, run_migrations
from finbreak.models import CategorizationRule, ColumnMapping
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import (
    CategorizationService,
    categorize,
)
from finbreak.services.import_ import ImportService
from finbreak.text import normalise_text

pytestmark = pytest.mark.features

HEADER = ["Date", "Details", "Amount"]
SINGLE = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to v8
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _roots(conn) -> dict[str, object]:
    roots = CategoryRepository(conn).children_of(None)
    return {r.kind: r for r in roots if r.kind is not None}


def _leaf_id(service: AuthService, name: str) -> int:
    """The id of a seeded leaf category by name (e.g. 'Groceries')."""
    for c in CategoryService(service.vault).list_all():
        if c.parent_id is not None and c.name == name:
            return c.id
    raise AssertionError(f"no leaf category named {name!r}")


def _account_id(service: AuthService) -> int:
    return AccountRepository(service.vault.connection).list_all()[0].id


def _add_txn(
    service: AuthService,
    description: str,
    amount: int = -100,
    occurred: str = "2026-01-05",
) -> int:
    """Insert one raw transaction (auto / uncategorised) and return its id. Uses
    the repo directly so a whitespace-only description can be seeded (the service
    validator would reject it) — the engine must still leave it uncategorised."""
    conn = service.vault.connection
    return TransactionRepository(conn).add(
        _account_id(service), occurred, amount, description
    )


def _txn_cat(service: AuthService, txn_id: int) -> tuple[int | None, str | None]:
    row = service.vault.connection.execute(
        "SELECT category_id, category_source FROM transactions WHERE id = ?", (txn_id,)
    ).fetchone()
    return (row[0], row[1])


def _csv(header: list[str], rows: list[list[str]]) -> str:
    return "\n".join([",".join(header)] + [",".join(r) for r in rows]) + "\n"


def _do_import(imp: ImportService, text: str, account_id: int):
    preview = imp.preview(text, SINGLE, account_id)
    assert preview.period_start is not None and preview.period_end is not None
    return imp.commit_import(
        preview, preview.period_start, preview.period_end, "stmt.csv"
    )


# --------------------------------------------------------------------------- #
# INV-15 — schema v6 -> v7
# --------------------------------------------------------------------------- #
def test_INV15_latest_schema_version_is_8():
    assert LATEST_SCHEMA_VERSION == 8


def test_INV15_v6_upgrades_to_v8(paths):
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v6_vault(vault_path, sidecar, salt, [("2026-01-01", -100, "a")])

    conn = keyed_connection(vault_path, salt)
    before = conn.execute(
        "SELECT id, amount_minor, description FROM transactions"
    ).fetchall()

    run_migrations(conn)  # v6 -> v8 (walks to LATEST)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8

    cols = {r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()}
    assert {"category_id", "category_source"} <= cols
    assert (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='categorization_rules'"
        ).fetchone()
        is not None
    )
    # transactions preserved; pre-v7 rows are auto/uncategorised (NULL/NULL).
    assert (
        conn.execute(
            "SELECT id, amount_minor, description FROM transactions"
        ).fetchall()
        == before
    )
    assert conn.execute(
        "SELECT category_id, category_source FROM transactions"
    ).fetchall() == [(None, None)]
    conn.close()


def test_INV15_atomic_rollback_leaves_v6(paths):
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v6_vault(vault_path, sidecar, salt, [])

    conn = keyed_connection(vault_path, salt)

    with pytest.raises(RuntimeError):
        run_migrations(
            raising_conn(
                conn,
                "CREATE TABLE categorization_rules",
                "injected failure at the rules-table CREATE",
            )
        )

    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 6
    cols = {r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()}
    assert "category_id" not in cols, "the ADD COLUMN was rolled back"
    conn.close()


def test_INV15_idempotent_at_v8(paths):
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v6_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)
    run_migrations(conn)  # re-run: no-op at v8
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
    conn.close()


def test_INV15_first_run_vault_is_v8(service):
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
    cols = {r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()}
    assert {"category_id", "category_source"} <= cols


# --------------------------------------------------------------------------- #
# shared text normaliser (D2)
# --------------------------------------------------------------------------- #
def test_normalise_text_collapses_whitespace_and_casefolds():
    assert normalise_text("  Foo   BAR ") == "foo bar"


def test_import_normalise_delegates_to_text():
    # ImportService._normalise must become a byte-identical delegator (D2), so the
    # dedup behaviour is unchanged.
    sample = "  Pick   N Pay  123 "
    assert ImportService._normalise(sample) == normalise_text(sample)


# --------------------------------------------------------------------------- #
# INV-2 — the pure matcher: first-match by priority, substring, normalised
# --------------------------------------------------------------------------- #
def test_INV2_first_match_in_priority_order():
    # The matcher walks the rules in the order given — which is `list_all`'s
    # ascending-priority order (the repo owns the sort, D3). Two both match; the
    # first (higher-priority) one wins.
    rules = [
        CategorizationRule(2, "coffee shop", 10, 3, "t"),  # priority 3 — first
        CategorizationRule(1, "coffee", 20, 5, "t"),  # priority 5 — also matches
    ]
    assert categorize("THE COFFEE SHOP", rules) == 10, "the first match in order wins"


def test_INV2_no_match_and_empty_rule_set_return_none():
    assert categorize("anything at all", []) is None
    assert categorize("anything", [CategorizationRule(1, "zzz", 9, 0, "t")]) is None


def test_INV2_normalises_both_pattern_and_description():
    rules = [CategorizationRule(1, "  Pick   N Pay ", 7, 0, "t")]
    assert categorize("EFT PICK N PAY  555", rules) == 7


def test_INV2_id_breaks_priority_ties(service):
    # Equal priorities are ordered by id (D7), so the list order is deterministic.
    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    r1 = cs.add_rule("x", g)
    r2 = cs.add_rule("x", f)
    # Force the two priorities equal to exercise the id tiebreak.
    conn = service.vault.connection
    conn.execute("UPDATE categorization_rules SET priority = 0")
    conn.commit()
    ordered = cs.list_rules()
    assert [r.id for r in ordered] == sorted([r1.id, r2.id])


# --------------------------------------------------------------------------- #
# INV-6 — new rules insert at the top (highest priority) and win
# --------------------------------------------------------------------------- #
def test_INV6_new_rule_inserts_at_top_and_wins(service):
    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    cs.add_rule("shop", g)  # a broad rule that also matches "coffee shop"
    specific = cs.add_rule("coffee shop", f)  # added later -> sorts first
    rules = cs.list_rules()
    assert rules[0].id == specific.id, "the newest rule is highest priority"
    assert categorize("COFFEE SHOP", rules) == f, "the new specific rule wins"


# --------------------------------------------------------------------------- #
# INV-1 — the golden rule
# --------------------------------------------------------------------------- #
def test_INV1_apply_leaves_a_manual_row_untouched(service):
    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    txn = _add_txn(service, "COFFEE SHOP")
    cs.set_manual_category(txn, g)  # manual -> Groceries (frozen)
    cs.add_rule("coffee", f)  # a rule that WOULD match it -> Fast food
    cs.apply_rules()
    assert _txn_cat(service, txn) == (g, "manual"), "a manual row is never touched"


def test_INV1_apply_refiles_auto_rows(service):
    cs = CategorizationService(service.vault)
    f = _leaf_id(service, "Fast food")
    txn = _add_txn(service, "COFFEE SHOP")  # auto (NULL/NULL)
    cs.add_rule("coffee", f)
    assert cs.apply_rules() == 1
    assert _txn_cat(service, txn) == (f, "rule")


# --------------------------------------------------------------------------- #
# INV-3 — manual survives everything (incl. a deliberate clear)
# --------------------------------------------------------------------------- #
def test_INV3_manual_clear_stays_clear_after_apply(service):
    cs = CategorizationService(service.vault)
    f = _leaf_id(service, "Fast food")
    txn = _add_txn(service, "COFFEE SHOP")
    cs.set_manual_category(txn, None)  # a deliberate clear -> NULL / 'manual'
    assert _txn_cat(service, txn) == (None, "manual")
    cs.add_rule("coffee", f)
    cs.apply_rules()
    assert _txn_cat(service, txn) == (None, "manual"), "a cleared row is not re-filled"


def test_INV3_manual_survives_a_reimport(service):
    # The import-path half of INV-3 (distinct from apply): a manual row must
    # survive a re-import of the same file (dedup keeps the row; commit_import's
    # recategorize_auto_rows excludes manual rows, D9).
    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    imp = ImportService(service.vault)
    acct = _account_id(service)
    csv = _csv(HEADER, [["2026-01-05", "PICK N PAY", "-50.00"]])
    _do_import(imp, csv, acct)  # no rules yet -> the row lands auto/uncategorised

    tid = service.vault.connection.execute(
        "SELECT id FROM transactions WHERE description = 'PICK N PAY'"
    ).fetchone()[0]
    cs.set_manual_category(tid, g)  # freeze it under Groceries by hand
    cs.add_rule("pick n pay", f)  # a rule that WOULD file it under Fast food

    result = _do_import(imp, csv, acct)  # re-import the SAME file
    assert result.inserted_count == 0, "the re-import inserts nothing (dedup keeps it)"
    assert _txn_cat(service, tid) == (g, "manual"), "the manual row survives re-import"


# --------------------------------------------------------------------------- #
# INV-4 — when rules run: on import, and on explicit apply (not on edit)
# --------------------------------------------------------------------------- #
def test_INV4_import_categorises_new_rows(service):
    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    cs.add_rule("pick n pay", g)
    imp = ImportService(service.vault)
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "PICK N PAY 123", "-50.00"]]),
        _account_id(service),
    )
    row = service.vault.connection.execute(
        "SELECT category_id, category_source FROM transactions "
        "WHERE description = 'PICK N PAY 123'"
    ).fetchone()
    assert (row[0], row[1]) == (g, "rule"), "import categorises new rows in one go"


def test_INV4_add_rule_does_not_refile_until_apply(service):
    cs = CategorizationService(service.vault)
    f = _leaf_id(service, "Fast food")
    txn = _add_txn(service, "COFFEE SHOP")
    cs.add_rule("coffee", f)
    assert _txn_cat(service, txn) == (None, None), "add_rule does not silently re-file"
    cs.apply_rules()
    assert _txn_cat(service, txn) == (f, "rule"), "the explicit apply re-files"


# --------------------------------------------------------------------------- #
# INV-5 — the learning "differs" signal (service half; UI offer below)
# --------------------------------------------------------------------------- #
def test_INV5_would_categorize_reflects_current_rules(service):
    cs = CategorizationService(service.vault)
    f = _leaf_id(service, "Fast food")
    assert cs.would_categorize("COFFEE SHOP") is None
    cs.add_rule("coffee", f)
    assert cs.would_categorize("COFFEE SHOP") == f


# --------------------------------------------------------------------------- #
# INV-7 — the atomic delete-category cascade
# --------------------------------------------------------------------------- #
def test_INV7_delete_cascade_refiles_and_removes_rules(service):
    cs = CategorizationService(service.vault)
    catsvc = CategoryService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")

    t_rule = _add_txn(service, "PICK N PAY")
    t_manual = _add_txn(service, "MANUAL ONE")
    cs.add_rule("pick", f)  # a *remaining* rule (bottom) that reclaims t_rule later
    cs.add_rule("pick n pay", g)  # targets Groceries (top) -> t_rule files here now
    cs.apply_rules()
    assert _txn_cat(service, t_rule) == (g, "rule")
    cs.set_manual_category(t_manual, g)
    assert _txn_cat(service, t_manual) == (g, "manual")

    assert catsvc.delete_blast_radius(g) == (2, 1), "both txns + the one rule count"
    catsvc.delete_category(g)

    assert CategoryRepository(service.vault.connection).get(g) is None, "category gone"
    assert [r.category_id for r in cs.list_rules()] == [f], "the Groceries rule is gone"
    assert _txn_cat(service, t_rule) == (f, "rule"), "reclaimed by the remaining rule"
    assert _txn_cat(service, t_manual) == (None, None), "manual->auto, matches nothing"


def test_INV7_delete_cascade_rolls_back_on_failure(service, monkeypatch):
    import finbreak.services.categories as cats_mod

    cs = CategorizationService(service.vault)
    catsvc = CategoryService(service.vault)
    g = _leaf_id(service, "Groceries")
    t = _add_txn(service, "PICK N PAY")
    cs.add_rule("pick n pay", g)
    cs.apply_rules()
    assert _txn_cat(service, t) == (g, "rule")

    def _boom(_conn):
        raise RuntimeError("wedged re-apply")

    monkeypatch.setattr(cats_mod, "recategorize_auto_rows", _boom)
    with pytest.raises(RuntimeError):
        catsvc.delete_category(g)

    # Nothing changed — the whole cascade rolled back.
    assert CategoryRepository(service.vault.connection).get(g) is not None
    assert len(cs.list_rules()) == 1
    assert _txn_cat(service, t) == (g, "rule")
    # The vault is still writable (the rollback left it re-openable).
    _add_txn(service, "AFTER ROLLBACK")


# --------------------------------------------------------------------------- #
# INV-8 — blast-radius (service + the net-new UI confirm)
# --------------------------------------------------------------------------- #
def test_INV8_confirm_names_both_counts_and_deletes_on_yes(qtbot, service, monkeypatch):
    from finbreak.ui.categories import CategoriesWidget

    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    # DISTINCT counts (3 transactions, 1 rule) so the assertion is sensitive to a
    # mutation that drops EITHER sentence — "1" alone (as with 1 txn + 1 rule)
    # would pass even if the rule-count sentence were removed.
    for i in range(3):
        _add_txn(service, f"PICK N PAY {i}")
    cs.add_rule("pick n pay", g)
    cs.apply_rules()

    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(g)

    captured: dict[str, str] = {}

    def _confirm_yes(parent, title, text, *a, **k):
        captured["text"] = text
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", _confirm_yes)
    widget._delete_button.click()

    # blast radius here is (3 transactions, 1 rule) — the text must name BOTH.
    assert "3" in captured["text"], "the confirmation names the transaction count"
    assert "1" in captured["text"], "the confirmation names the rule count"
    assert CategoryRepository(service.vault.connection).get(g) is None, "deleted on Yes"


def test_INV8_cancel_deletes_nothing(qtbot, service, monkeypatch):
    from finbreak.ui.categories import CategoriesWidget

    g = _leaf_id(service, "Groceries")
    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(g)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    widget._delete_button.click()
    assert CategoryRepository(service.vault.connection).get(g) is not None, "No: kept"


# --------------------------------------------------------------------------- #
# INV-9 — rules target leaves only
# --------------------------------------------------------------------------- #
def test_INV9_add_and_update_reject_a_root(service):
    cs = CategorizationService(service.vault)
    income = _roots(service.vault.connection)["income"]
    g = _leaf_id(service, "Groceries")
    with pytest.raises(ValueError):
        cs.add_rule("x", income.id)
    rule = cs.add_rule("x", g)
    with pytest.raises(ValueError):
        cs.update_rule(rule.id, "x", income.id)


def test_INV9_add_rule_rejects_empty_pattern(service):
    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    with pytest.raises(ValueError):
        cs.add_rule("   ", g)


def test_INV9_leaf_categories_excludes_the_roots(service):
    cs = CategorizationService(service.vault)
    leaves = cs.leaf_categories()
    assert leaves and all(c.parent_id is not None for c in leaves)
    root_ids = {
        r.id for r in CategoryRepository(service.vault.connection).children_of(None)
    }
    assert not (root_ids & {c.id for c in leaves}), "no Type root is offered"


# --------------------------------------------------------------------------- #
# INV-12 / INV-13 — no re-dedup; idempotent apply
# --------------------------------------------------------------------------- #
def test_INV12_apply_only_updates_never_changes_row_count(service):
    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    for i in range(3):
        _add_txn(service, f"PICK N PAY {i}")
    cs.add_rule("pick n pay", g)
    conn = service.vault.connection
    before = conn.execute("SELECT count(*) FROM transactions").fetchone()[0]
    cs.apply_rules()
    after = conn.execute("SELECT count(*) FROM transactions").fetchone()[0]
    assert before == after == 3, "re-categorising inserts/deletes nothing"


def test_INV13_second_apply_with_unchanged_rules_returns_zero(service):
    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    _add_txn(service, "PICK N PAY")
    cs.add_rule("pick n pay", g)
    assert cs.apply_rules() == 1
    assert cs.apply_rules() == 0, "a second apply with unchanged rules is a no-op"


# --------------------------------------------------------------------------- #
# Edges — empty rule set, delete-all-rules, empty description
# --------------------------------------------------------------------------- #
def test_edge_delete_all_rules_then_apply_blanks_auto_rows_only(service):
    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    t_auto = _add_txn(service, "PICK N PAY")
    rule = cs.add_rule("pick n pay", g)
    cs.apply_rules()
    assert _txn_cat(service, t_auto) == (g, "rule")
    t_manual = _add_txn(service, "MANUAL")
    cs.set_manual_category(t_manual, g)

    cs.delete_rule(rule.id)
    assert cs.apply_rules() == 1, "one auto row went blank"
    assert _txn_cat(service, t_auto) == (None, None), "the rule row is blanked"
    assert _txn_cat(service, t_manual) == (g, "manual"), "the manual row stays"


def test_edge_empty_description_row_stays_uncategorised(service):
    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    tid = _add_txn(service, "   ")  # whitespace-only description
    cs.add_rule("pick n pay", g)
    cs.apply_rules()
    assert _txn_cat(service, tid) == (None, None)


# --------------------------------------------------------------------------- #
# INV-11 — the Rules tab (qtbot)
# --------------------------------------------------------------------------- #
def _stub_rule_dialog(monkeypatch, rules_mod, *, pattern, category_id, accept=True):
    def factory(leaves, pat="", cat=None, parent=None):
        return RuleStub(parent, pattern, category_id, accept)

    monkeypatch.setattr(rules_mod, "RuleEditDialog", factory)


def test_INV11_add_lists_and_apply_reports_count(qtbot, service, monkeypatch):
    import finbreak.ui.rules as rules_mod
    from finbreak.ui.rules import RulesWidget

    g = _leaf_id(service, "Groceries")
    t = _add_txn(service, "PICK N PAY")
    widget = RulesWidget(service)
    qtbot.addWidget(widget)

    _stub_rule_dialog(monkeypatch, rules_mod, pattern="pick n pay", category_id=g)
    widget._add_button.click()
    rules = CategorizationService(service.vault).list_rules()
    assert len(rules) == 1 and rules[0].pattern == "pick n pay"
    assert widget._table.rowCount() == 1, "the new rule is listed"

    widget._apply_button.click()
    assert _txn_cat(service, t) == (g, "rule"), "Apply re-files the matching row"
    assert "1" in widget._status.text(), "Apply reports the re-filed count"
    widget._apply_button.click()
    assert "0" in widget._status.text(), "a second Apply reports 0 (idempotent)"


def test_INV11_move_up_reorders_the_list(qtbot, service):
    from finbreak.ui.rules import RulesWidget

    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    a = cs.add_rule("aaa", g)
    b = cs.add_rule("bbb", f)  # added last -> top; order is [b, a]
    assert [r.id for r in cs.list_rules()] == [b.id, a.id]

    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    widget._select_rule(a.id)
    widget._move_up_button.click()
    assert [r.id for r in cs.list_rules()] == [a.id, b.id], "a moved above b"


def test_INV11_move_down_and_ends_are_noops(service):
    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    a = cs.add_rule("aaa", g)
    b = cs.add_rule("bbb", f)  # order [b, a]
    cs.move_rule(b.id, "up")  # already at top -> no-op
    assert [r.id for r in cs.list_rules()] == [b.id, a.id]
    cs.move_rule(a.id, "down")  # already at bottom -> no-op
    assert [r.id for r in cs.list_rules()] == [b.id, a.id]
    cs.move_rule(b.id, "down")  # swap -> [a, b]
    assert [r.id for r in cs.list_rules()] == [a.id, b.id]


def test_INV11_delete_removes_the_rule(qtbot, service):
    from finbreak.ui.rules import RulesWidget

    cs = CategorizationService(service.vault)
    r = cs.add_rule("x", _leaf_id(service, "Groceries"))
    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    widget._select_rule(r.id)
    widget._delete_button.click()
    assert cs.list_rules() == [], "the rule is gone"


def test_INV11_edit_updates_pattern_without_reprioritising(qtbot, service, monkeypatch):
    import finbreak.ui.rules as rules_mod
    from finbreak.ui.rules import RulesWidget

    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    a = cs.add_rule("aaa", g)
    b = cs.add_rule("bbb", f)  # order [b, a]

    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    widget._select_rule(a.id)
    _stub_rule_dialog(monkeypatch, rules_mod, pattern="aaa-edited", category_id=g)
    widget._edit_button.click()

    ordered = cs.list_rules()
    assert [r.id for r in ordered] == [b.id, a.id], "an edit does not re-prioritise"
    assert next(r for r in ordered if r.id == a.id).pattern == "aaa-edited"


# --------------------------------------------------------------------------- #
# INV-14 — auto-lock safety (the new slots swallow VaultLockedError)
# --------------------------------------------------------------------------- #


def test_INV14_apply_catches_vault_locked(qtbot, service, monkeypatch):
    from finbreak.ui.rules import RulesWidget

    widget = RulesWidget(service)
    qtbot.addWidget(widget)

    def _raise(*a, **k):
        raise VaultLockedError("auto-lock fired mid-apply")

    monkeypatch.setattr(widget._categorization, "apply_rules", _raise)
    widget._apply_button.click()  # must not raise
    assert widget._error.text() == "", "VaultLockedError swallowed silently"


def test_INV14_category_delete_catches_vault_locked(qtbot, service, monkeypatch):
    from finbreak.ui.categories import CategoriesWidget

    g = _leaf_id(service, "Groceries")
    widget = CategoriesWidget(service)
    qtbot.addWidget(widget)
    widget._select_category(g)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    def _raise(*a, **k):
        raise VaultLockedError("auto-lock fired mid-delete")

    monkeypatch.setattr(widget._categories, "delete_category", _raise)
    widget._delete_button.click()  # must not raise
    assert widget._error.text() == "", "VaultLockedError swallowed silently"


def test_set_manual_category_rejects_a_root(service):
    """A manual pick, like a rule, must target a leaf — never a Type root; the
    service enforces INV-9 at its boundary, not just the picker UI. A root id is
    a valid FK, so only this guard catches it. (indie-review M-core1)"""
    cs = CategorizationService(service.vault)
    income = _roots(service.vault.connection)["income"]
    t = _add_txn(service, "SOMETHING")
    with pytest.raises(ValueError):
        cs.set_manual_category(t, income.id)
    # a leaf still works, and None (a deliberate clear) still works
    cs.set_manual_category(t, _leaf_id(service, "Groceries"))
    cs.set_manual_category(t, None)


def test_move_rule_swap_is_atomic_on_failure(service, monkeypatch):
    """If the second priority write fails mid-swap, the first is rolled back —
    the reorder is one atomic transaction, not two separate commits.
    (indie-review M-C1)"""
    from finbreak.repositories.categorization_rules import (
        CategorizationRuleRepository,
    )

    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    r1 = cs.add_rule("aaa", g)
    cs.add_rule("bbb", g)  # inserted on top (new rules win)
    before = {r.id: r.priority for r in cs.list_rules()}

    real = CategorizationRuleRepository.set_priority
    calls = {"n": 0}

    def flaky(self, rule_id, priority):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated mid-swap failure")
        return real(self, rule_id, priority)

    monkeypatch.setattr(CategorizationRuleRepository, "set_priority", flaky)
    with pytest.raises(RuntimeError):
        cs.move_rule(r1.id, "up")

    after = {r.id: r.priority for r in cs.list_rules()}
    assert after == before, "a failed swap must roll back, not half-apply"


def test_add_rule_swallows_vault_locked_silently(qtbot, service, monkeypatch):
    """If an idle auto-lock fires while the rule dialog was open, _on_add returns
    silently — matching Delete/Move/Apply in the same widget — not a raw
    'the vault is locked' error label. (indie-review M-C4)"""
    import finbreak.ui.rules as rules_mod
    from finbreak.ui.rules import RulesWidget

    g = _leaf_id(service, "Groceries")
    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    _stub_rule_dialog(monkeypatch, rules_mod, pattern="x", category_id=g)

    def locked(*a, **k):
        raise VaultLockedError("the vault is locked")

    monkeypatch.setattr(widget._categorization, "add_rule", locked)
    widget._add_button.click()  # must not raise, must not show an error label
    assert widget._error.text() == "", "a VaultLockedError is swallowed silently"


def test_edit_rule_swallows_vault_locked_silently(qtbot, service, monkeypatch):
    """FIBR-0065: an auto-lock while the edit dialog was open → _apply_edit returns
    silently (parity with _apply_add). Edit had no guard test before FIBR-0065."""
    import finbreak.ui.rules as rules_mod
    from finbreak.ui.rules import RulesWidget

    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    r = cs.add_rule("aaa", g)
    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    widget._select_rule(r.id)
    _stub_rule_dialog(monkeypatch, rules_mod, pattern="aaa-edited", category_id=g)

    def locked(*a, **k):
        raise VaultLockedError("the vault is locked")

    monkeypatch.setattr(widget._categorization, "update_rule", locked)
    widget._edit_button.click()  # must not raise, must not show an error label
    assert widget._error.text() == "", "a VaultLockedError is swallowed silently"


# --------------------------------------------------------------------------- #
# FIBR-0079 — RuleEditDialog handles the zero-leaf-categories edge
# --------------------------------------------------------------------------- #
def test_rule_dialog_ok_disabled_without_leaf_categories(qtbot):
    """RuleEditDialog with no leaf categories keeps OK disabled even with a
    non-empty pattern — its combo is empty so there is nothing to file the rule
    as, and selected_category_id() would be None (FIBR-0079)."""
    from PySide6.QtWidgets import QDialogButtonBox

    from finbreak.ui.rules import RuleEditDialog

    dialog = RuleEditDialog([], pattern="rent")
    qtbot.addWidget(dialog)
    ok = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    assert ok is not None and not ok.isEnabled()
    assert dialog.selected_category_id() is None


def test_add_rule_blocked_when_no_leaf_categories(qtbot, service, monkeypatch):
    """With every leaf category deleted, Add shows a 'create a category first'
    message and opens no dialog — instead of a submittable dialog whose empty
    combo makes add_rule reject with the confusing leaf error (FIBR-0079)."""
    import finbreak.ui.rules as rules_mod
    from finbreak.ui.rules import RulesWidget

    cats = CategoryService(service.vault)
    for leaf in CategorizationService(service.vault).leaf_categories():
        cats.delete_category(leaf.id)

    opened: list[int] = []

    def factory(*a, **k):
        opened.append(1)
        d = QDialog()
        qtbot.addWidget(d)
        return d

    monkeypatch.setattr(rules_mod, "RuleEditDialog", factory)

    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    widget._on_add()

    assert opened == [], "no dialog opens when there are no leaf categories"
    assert "category" in widget._error.text().lower()


def test_move_rule_unknown_id_is_noop(service):
    """move_rule on a non-existent rule id returns cleanly (no raise) and leaves
    the order untouched — the early-return branch (FIBR-0064)."""
    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    cs.add_rule("a", g)
    cs.add_rule("b", g)
    before = [r.id for r in cs.list_rules()]
    cs.move_rule(999999, "up")  # unknown id — no-op
    assert [r.id for r in cs.list_rules()] == before
