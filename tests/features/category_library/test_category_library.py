"""FIBR-0139 — built-in category library.

Enforces tests/features/category_library/spec.md. The pure module
(`parse_library` / `load_library` / `match_library`), the engine composition
(`categorize_with_library` / `_match_inputs` / `_leaf_name_to_id` / the
toggle), the extended `recategorize_auto_rows` + `would_categorize`, the delete
cascade, and the Transactions "~ guess" marker + Settings toggle (qtbot).

The autouse `_neutralise_category_library` fixture (conftest) makes `load_library`
return `[]` for the whole suite; legs that need a library inject a fixture list in
the test body (`_inject`, after the autouse patch — last-write-wins) or carry
`@pytest.mark.real_library` to drive the genuine loader. Every on-disk vault uses
`tmp_path`; no network, no real financial data (testing.md § 6).
"""

from pathlib import Path

import pytest

from conftest import _PW, spy_learning, stub_picker
from finbreak.category_library import (
    LibraryEntry,
    match_library,
    parse_library,
)
from finbreak.migrations import DEFAULT_CATEGORIES
from finbreak.models import CategorizationRule, CategorySource
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import (
    CategorizationService,
    _leaf_name_to_id,
    categorize_with_library,
)
from finbreak.services.transactions import TransactionService

pytestmark = pytest.mark.features

_COL_DESCRIPTION = 2
_COL_CATEGORY = 4


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to v8
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _leaf_id(service, name):
    for c in CategoryService(service.vault).list_all():
        if c.parent_id is not None and c.name == name:
            return c.id
    raise AssertionError(f"no leaf category named {name!r}")


def _account_id(service):
    return AccountRepository(service.vault.connection).list_all()[0].id


def _add_txn(service, description, amount=-1000, occurred="2026-01-05"):
    return TransactionRepository(service.vault.connection).add(
        _account_id(service), occurred, amount, description
    )


def _txn_cat(service, txn_id):
    row = service.vault.connection.execute(
        "SELECT category_id, category_source FROM transactions WHERE id = ?", (txn_id,)
    ).fetchone()
    return (row[0], row[1])


def _inject(monkeypatch, entries):
    """Inject a fixture library — in the TEST BODY, after the autouse neutralise, so
    last-write-wins keeps the injected list (spec Test-ripple ordering note)."""
    monkeypatch.setattr("finbreak.category_library.load_library", lambda: list(entries))


def _seed_library_row(service, txn_id, category_id):
    """Stamp a row `'library'` directly (the autouse-neutralised pipeline never would),
    so the UI legs have a genuine guess row to render (spec D7 setup note)."""
    conn = service.vault.connection
    TransactionRepository(conn).set_category(
        txn_id, category_id, CategorySource.LIBRARY.value
    )
    conn.commit()


def _view(service):
    from finbreak.ui.transactions import TransactionsView

    return TransactionsView(
        TransactionService(service.vault), CategorizationService(service.vault)
    )


def _cat_text(view, description):
    for r in range(view._table.rowCount()):
        if view._table.item(r, _COL_DESCRIPTION).text() == description:
            return view._table.item(r, _COL_CATEGORY).text()
    raise AssertionError(f"no row for {description!r}")


# --------------------------------------------------------------------------- #
# parse_library — pure + total (INV-8)
# --------------------------------------------------------------------------- #
def test_parse_library_valid_array():
    entries = parse_library('[{"pattern": "netflix", "category": "Entertainment"}]')
    assert entries == [LibraryEntry("netflix", "Entertainment")]


def test_parse_library_is_total_never_raises():
    assert parse_library("not json at all") == []  # unparseable → []
    assert parse_library("{}") == []  # non-array → []
    assert parse_library("123") == []  # non-array scalar → []
    # A mixed array drops non-dict + malformed elements, keeps the one valid entry,
    # and never raises AttributeError/TypeError on the junk.
    mixed = (
        '[1, "netflix", {"pattern": "kfc", "category": "Fast food"}, '
        '{"pattern": "   ", "category": "X"}, '  # blank pattern → skipped
        '{"pattern": "y", "category": ""}, {}]'  # blank category / empty dict → skipped
    )
    assert parse_library(mixed) == [LibraryEntry("kfc", "Fast food")]


# --------------------------------------------------------------------------- #
# match_library (INV-6)
# --------------------------------------------------------------------------- #
def test_match_library_first_resolving_entry_wins():
    entries = [LibraryEntry("netflix", "Entertainment"), LibraryEntry("net", "Bills")]
    assert match_library("NETFLIX.COM", entries, {"Entertainment": 5, "Bills": 9}) == 5


def test_match_library_skips_unresolved_category_falls_through():
    # First substring match's category is absent from the map (renamed/deleted) →
    # skip it and keep scanning, never mis-file (INV-6).
    entries = [LibraryEntry("net", "Gone"), LibraryEntry("netflix", "Entertainment")]
    assert match_library("NETFLIX", entries, {"Entertainment": 5}) == 5


def test_match_library_none_cases():
    entries = [LibraryEntry("netflix", "Entertainment")]
    m = {"Entertainment": 5}
    assert match_library("groceries store", entries, m) is None  # no match
    assert match_library("netflix", [], m) is None  # empty library
    assert match_library("", entries, m) is None  # empty description
    assert match_library("   ", entries, m) is None  # whitespace only


# --------------------------------------------------------------------------- #
# categorize_with_library — rule beats library (INV-2)
# --------------------------------------------------------------------------- #
def test_categorize_with_library_rule_beats_library():
    rules = [CategorizationRule(1, "netflix", 7, 0, "t")]
    entries = [LibraryEntry("netflix", "Entertainment")]
    assert categorize_with_library("NETFLIX", rules, entries, {"Entertainment": 5}) == (
        7,
        "rule",
    )


def test_categorize_with_library_library_only():
    entries = [LibraryEntry("netflix", "Entertainment")]
    assert categorize_with_library("NETFLIX", [], entries, {"Entertainment": 5}) == (
        5,
        "library",
    )


def test_categorize_with_library_neither():
    assert categorize_with_library("mystery", [], [], {}) == (None, None)


# --------------------------------------------------------------------------- #
# _leaf_name_to_id duplicate-name first-wins (INV-6/D5)
# --------------------------------------------------------------------------- #
def test_leaf_name_to_id_duplicate_name_first_wins(service):
    conn = service.vault.connection
    roots = {r.kind: r for r in CategoryRepository(conn).children_of(None)}
    income_misc = CategoryService(service.vault).add_category(
        roots["income"].id, "Misc"
    )
    exp_misc = CategoryService(service.vault).add_category(
        roots["expenditure"].id, "Misc"
    )
    # Income seeds before Expenditure (lower parent_id), so list_all yields the Income
    # "Misc" first → setdefault keeps it (deterministic first-wins, not last-wins).
    assert roots["income"].id < roots["expenditure"].id
    name_to_id = _leaf_name_to_id(conn)
    assert name_to_id["Misc"] == income_misc.id
    assert income_misc.id != exp_misc.id


# --------------------------------------------------------------------------- #
# recategorize_auto_rows end-to-end (INV-1/3/4/10)
# --------------------------------------------------------------------------- #
def test_apply_stamps_library_conserves_money_and_is_idempotent(service, monkeypatch):
    _inject(
        monkeypatch,
        [
            LibraryEntry("netflix", "Entertainment"),
            LibraryEntry("pick n pay", "Groceries"),
        ],
    )
    cat = CategorizationService(service.vault)
    ent, groc = _leaf_id(service, "Entertainment"), _leaf_id(service, "Groceries")

    netflix = _add_txn(service, "NETFLIX.COM", -1500)
    pnp = _add_txn(service, "PICK N PAY 42", -5000)
    unknown = _add_txn(service, "ACME MYSTERY CORP", -2000)
    manual = _add_txn(service, "HAND SET ROW", -300)
    cat.set_manual_category(manual, groc)  # frozen manual — never touched

    conn = service.vault.connection
    before = sorted(r[0] for r in conn.execute("SELECT amount_minor FROM transactions"))

    changed = cat.apply_rules()

    assert _txn_cat(service, netflix) == (ent, "library")
    assert _txn_cat(service, pnp) == (groc, "library")
    assert _txn_cat(service, unknown) == (None, None)  # un-guessable stays auto
    assert _txn_cat(service, manual) == (groc, "manual")  # INV-3 untouched
    assert changed == 2  # only the two guesses moved

    after = sorted(r[0] for r in conn.execute("SELECT amount_minor FROM transactions"))
    assert after == before  # INV-1 multiset conserved
    assert sum(after) == sum(before)  # grand total conserved
    assert cat.apply_rules() == 0  # INV-10 idempotent


# --------------------------------------------------------------------------- #
# would_categorize folds in the library (INV-2/INV-5)
# --------------------------------------------------------------------------- #
def test_would_categorize_uses_library_then_rule_wins(service, monkeypatch):
    _inject(monkeypatch, [LibraryEntry("netflix", "Entertainment")])
    cat = CategorizationService(service.vault)
    ent, groc = _leaf_id(service, "Entertainment"), _leaf_id(service, "Groceries")

    assert cat.would_categorize("NETFLIX.COM 123") == ent  # library guess surfaces
    cat.add_rule("netflix", groc)  # a user rule for the same
    assert cat.would_categorize("NETFLIX.COM 123") == groc  # rule beats library (INV-2)


# --------------------------------------------------------------------------- #
# the toggle, full round-trip (INV-7)
# --------------------------------------------------------------------------- #
def test_toggle_off_reverts_guesses_on_symmetric(service, monkeypatch):
    _inject(monkeypatch, [LibraryEntry("netflix", "Entertainment")])
    cat = CategorizationService(service.vault)
    ent, groc = _leaf_id(service, "Entertainment"), _leaf_id(service, "Groceries")

    netflix = _add_txn(service, "NETFLIX.COM", -1500)
    spotify = _add_txn(service, "SPOTIFY PREMIUM", -900)
    manual = _add_txn(service, "HAND ROW", -100)
    cat.add_rule("spotify", groc)  # a user rule (must survive the toggle)
    cat.set_manual_category(manual, ent)  # a manual pick (must survive the toggle)

    assert cat.library_enabled() is True  # default ON (absent key)
    cat.apply_rules()
    assert _txn_cat(service, netflix) == (ent, "library")
    assert _txn_cat(service, spotify) == (groc, "rule")

    cat.set_library_enabled(False)
    assert cat.library_enabled() is False
    cat.apply_rules()
    assert _txn_cat(service, netflix) == (None, None)  # guess reverted (INV-7)
    assert _txn_cat(service, spotify) == (groc, "rule")  # user rule unaffected
    assert _txn_cat(service, manual) == (ent, "manual")  # manual unaffected

    cat.set_library_enabled(True)
    assert cat.library_enabled() is True
    cat.apply_rules()
    assert _txn_cat(service, netflix) == (ent, "library")  # re-filed (off→on symmetric)


# --------------------------------------------------------------------------- #
# the delete cascade re-guesses through the library (INV-5/INV-6)
# --------------------------------------------------------------------------- #
def test_delete_category_cascade_reguesses_through_library(service, monkeypatch):
    _inject(
        monkeypatch,
        [
            LibraryEntry("netflix", "Entertainment"),
            LibraryEntry("pick n pay", "Groceries"),
        ],
    )
    cat = CategorizationService(service.vault)
    ent, groc = _leaf_id(service, "Entertainment"), _leaf_id(service, "Groceries")

    netflix = _add_txn(service, "NETFLIX.COM", -1500)
    pnp = _add_txn(service, "PICK N PAY 42", -5000)
    cat.apply_rules()
    assert _txn_cat(service, netflix) == (ent, "library")
    assert _txn_cat(service, pnp) == (groc, "library")

    CategoryService(service.vault).delete_category(groc)  # cascade + re-apply

    # "pick n pay" → Groceries, now deleted, no longer resolves → Uncategorised
    # (INV-6); "netflix" → Entertainment, still a leaf → re-guessed (rides delete path).
    assert _txn_cat(service, pnp) == (None, None)
    assert _txn_cat(service, netflix) == (ent, "library")


# --------------------------------------------------------------------------- #
# shipped file data guard + file-layer fail-safe (INV-8, real loader)
# --------------------------------------------------------------------------- #
@pytest.mark.real_library
def test_shipped_library_valid_and_maps_known_merchants():
    import finbreak.category_library as cl

    path = Path(cl.__file__).parent / "data" / "category_library.json"
    entries = parse_library(path.read_text(encoding="utf-8"))
    assert entries, "shipped category_library.json parsed empty"

    leaves = set(DEFAULT_CATEGORIES["income"]) | set(DEFAULT_CATEGORIES["expenditure"])
    for entry in entries:
        # A typo like "Entertainmnet" would ship a dead entry INV-6 silently skips —
        # this fails CI instead of failing silently in a user's import.
        assert entry.category in leaves, (
            f"library entry {entry.pattern!r} -> unknown category {entry.category!r}"
        )

    name_to_id = {name: i for i, name in enumerate(sorted(leaves))}

    def cat_of(desc):
        cid = match_library(desc, entries, name_to_id)
        return next((n for n, i in name_to_id.items() if i == cid), None)

    assert cat_of("NETFLIX.COM 12345") == "Entertainment"
    assert cat_of("PICK N PAY CRP 001") == "Groceries"


@pytest.mark.real_library
def test_load_library_file_layer_fail_safe(monkeypatch, tmp_path):
    import finbreak.category_library as cl

    def load_with_path(path):
        monkeypatch.setattr(cl, "_LIBRARY_PATH", path)
        cl.load_library.cache_clear()  # the cache is process-wide — clear each leg
        return cl.load_library()

    assert load_with_path(tmp_path / "nope.json") == []  # missing → OSError → []
    garbage = tmp_path / "garbage.json"
    garbage.write_text("this is not json", encoding="utf-8")
    assert load_with_path(garbage) == []  # unparseable → []
    nonutf8 = tmp_path / "bin.json"
    nonutf8.write_bytes(b"\xff\xfe\x00\x01")
    assert load_with_path(nonutf8) == []  # UnicodeDecodeError → []
    cl.load_library.cache_clear()  # trailing clear — don't poison the cache for later


# --------------------------------------------------------------------------- #
# Transactions "~ guess" marker + sort grouping (INV-9/D7, qtbot)
# --------------------------------------------------------------------------- #
def test_guess_marker_and_tooltip_present(qtbot, service):
    groc = _leaf_id(service, "Groceries")
    guess = _add_txn(service, "NETFLIX")
    plain = _add_txn(service, "WOOLIES")
    _seed_library_row(service, guess, groc)
    CategorizationService(service.vault).set_manual_category(plain, groc)

    view = _view(service)
    qtbot.addWidget(view)

    assert _cat_text(view, "NETFLIX") == "Groceries ~ guess"  # guess marked
    assert _cat_text(view, "WOOLIES") == "Groceries"  # manual plain
    # the marker carries an explanatory tooltip; the plain row does not.
    for r in range(view._table.rowCount()):
        item = view._table.item(r, _COL_CATEGORY)
        if item.text() == "Groceries ~ guess":
            assert item.toolTip()
        elif item.text() == "Groceries":
            assert not item.toolTip()


def test_guess_cell_sorts_with_its_plain_named_siblings(qtbot, service):
    groc = _leaf_id(service, "Groceries")
    # A splitter category whose NAME sorts after "Groceries" but whose display text
    # ("Groceries and more") sorts BETWEEN "Groceries" and "Groceries ~ guess" — so a
    # display-text sort would split the two Groceries cells; the bare-name key groups
    # them (this is why EVERY Category cell is a SortableItem, D7).
    roots = {
        r.kind: r
        for r in CategoryRepository(service.vault.connection).children_of(None)
    }
    splitter = (
        CategoryService(service.vault)
        .add_category(roots["expenditure"].id, "Groceries and more")
        .id
    )
    guess = _add_txn(service, "GUESS ROW")
    plain = _add_txn(service, "PLAIN ROW")
    other = _add_txn(service, "OTHER ROW")
    _seed_library_row(service, guess, groc)
    CategorizationService(service.vault).set_manual_category(plain, groc)
    CategorizationService(service.vault).set_manual_category(other, splitter)

    view = _view(service)
    qtbot.addWidget(view)
    view._table.sortItems(_COL_CATEGORY)

    cats = [
        view._table.item(r, _COL_CATEGORY).text() for r in range(view._table.rowCount())
    ]
    groceries_rows = [
        i for i, t in enumerate(cats) if t in ("Groceries", "Groceries ~ guess")
    ]
    assert len(groceries_rows) == 2
    assert groceries_rows[1] - groceries_rows[0] == 1  # adjacent, not split


def test_override_library_guess_drops_marker(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as tmod

    groc = _leaf_id(service, "Groceries")
    ent = _leaf_id(service, "Entertainment")
    txn = _add_txn(service, "NETFLIX")
    _seed_library_row(service, txn, ent)

    view = _view(service)
    qtbot.addWidget(view)
    assert "~ guess" in _cat_text(view, "NETFLIX")

    # Override via Set category… → pick Groceries; suppress the learn-a-rule offer.
    stub_picker(monkeypatch, tmod, groc, accept=True)
    spy_learning(monkeypatch, tmod, accept=False)
    view._select_txn(txn)
    view._on_set_category()

    assert _txn_cat(service, txn) == (groc, "manual")  # flipped to manual
    assert _cat_text(view, "NETFLIX") == "Groceries"  # marker dropped (INV-9)


# --------------------------------------------------------------------------- #
# Settings toggle round-trip (INV-7, qtbot)
# --------------------------------------------------------------------------- #
def test_settings_checkbox_reflects_and_round_trips(qtbot, service):
    from finbreak.ui.settings import SettingsDialog

    cat = CategorizationService(service.vault)
    assert cat.library_enabled() is True  # default ON

    dlg = SettingsDialog(service, "ZAR", library_enabled=cat.library_enabled())
    qtbot.addWidget(dlg)
    assert dlg.library_enabled() is True

    dlg._library_checkbox.setChecked(False)  # user unticks
    cat.set_library_enabled(dlg.library_enabled())  # shell persists on Save
    assert cat.library_enabled() is False

    reopened = SettingsDialog(service, "ZAR", library_enabled=cat.library_enabled())
    qtbot.addWidget(reopened)
    assert reopened.library_enabled() is False  # reflects the persisted state
