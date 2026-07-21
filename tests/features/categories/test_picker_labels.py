"""FIBR-0154 INV-4 — the flat category pickers disambiguate same-named Level-3
sub-categories with a parent breadcrumb, at the real call sites.

At depth 3 the FIBR-0123 ``Name (Type)`` tag is not enough: sibling names are
unique only *per parent*, so *Groceries › Spar* and *Fuel › Spar* both render as
``"Spar (Expenditure)"`` today. FIBR-0154 threads a
``CategorizationService.sub_category_parent_names()`` map (grandchild-or-deeper
id → immediate-parent name) through ``add_grouped_categories`` and every picker
site, so a Level-3 row reads ``"Groceries › Spar (Expenditure)"``.

Mirrors the FIBR-0123 combo-rendering tests in tests/features/categorisation.
Every on-disk vault uses ``tmp_path``; no test touches the network or real
financial data (testing.md § 6).
"""

from collections.abc import Iterator

import pytest

from conftest import _PW, spy_learning, stub_picker
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import CategorizationService

pytestmark = pytest.mark.features

# The exact breadcrumb labels the pickers must render (parent hop + FIBR-0123 tag).
_GROCERIES_SPAR = "Groceries › Spar (Expenditure)"
_FUEL_SPAR = "Fuel › Spar (Expenditure)"


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates to latest (tree seeded)
    yield svc
    svc.lock()


def _roots(conn) -> dict[str, object]:
    roots = CategoryRepository(conn).children_of(None)
    return {r.kind: r for r in roots if r.kind is not None}


def _seed_two_spars(service):
    """Expenditure › Groceries › Spar AND Expenditure › Fuel › Spar — the two
    same-named Level-3 nodes the FIBR-0123 Type-tag alone can't tell apart.
    Returns (groceries, fuel, spar_under_groceries, spar_under_fuel)."""
    svc = CategoryService(service.vault)
    expenditure = _roots(service.vault.connection)["expenditure"]
    groceries = next(
        c for c in svc.children_of(expenditure.id) if c.name == "Groceries"
    )
    fuel = svc.add_category(expenditure.id, "Fuel")
    spar_g = svc.add_category(groceries.id, "Spar")
    spar_f = svc.add_category(fuel.id, "Spar")
    return groceries, fuel, spar_g, spar_f


def _add_txn(service, description):
    acct = AccountRepository(service.vault.connection).list_all()[0].id
    return TransactionRepository(service.vault.connection).add(
        acct, "2026-01-05", -1000, description
    )


def _labels(combo):
    return {combo.itemText(i) for i in range(combo.count())}


def _id_for_label(combo, text):
    for i in range(combo.count()):
        if combo.itemText(i) == text:
            return combo.itemData(i)
    raise AssertionError(f"no combo row {text!r}")


# --------------------------------------------------------------------------- #
# INV-4 accessor contract — sub_category_parent_names()
# --------------------------------------------------------------------------- #
def test_INV4_sub_category_parent_names_is_level3_only(service):
    """The accessor maps each Level-3 (grandchild) id to its immediate parent name
    and OMITS Level-2 ids — an over-inclusive bug (breadcrumbing a Level-2 as
    "Expenditure › Groceries") would be caught here."""
    cs = CategorizationService(service.vault)
    groceries, fuel, spar_g, spar_f = _seed_two_spars(service)

    names = cs.sub_category_parent_names()
    assert names[spar_g.id] == "Groceries"
    assert names[spar_f.id] == "Fuel"
    assert groceries.id not in names, "a Level-2 category is not breadcrumbed"
    assert fuel.id not in names, "a Level-2 category is not breadcrumbed"


# --------------------------------------------------------------------------- #
# INV-4 dialog render — CategoryPickerDialog + RuleEditDialog
# --------------------------------------------------------------------------- #
def test_INV4_picker_dialog_renders_distinct_breadcrumbs(qtbot, service):
    """CategoryPickerDialog(…, parent_names=map) renders the two same-named Spar
    nodes as distinct breadcrumbed rows, each resolving to its own id."""
    from finbreak.ui.category_picker import CategoryPickerDialog

    cs = CategorizationService(service.vault)
    _groc, _fuel, spar_g, spar_f = _seed_two_spars(service)
    grouped = cs.leaf_categories_grouped()
    names = cs.sub_category_parent_names()

    dialog = CategoryPickerDialog(grouped, None, parent_names=names)
    qtbot.addWidget(dialog)
    labels = _labels(dialog._combo)
    assert _GROCERIES_SPAR in labels
    assert _FUEL_SPAR in labels
    assert _id_for_label(dialog._combo, _GROCERIES_SPAR) == spar_g.id
    assert _id_for_label(dialog._combo, _FUEL_SPAR) == spar_f.id


def test_INV4_rule_dialog_renders_distinct_breadcrumbs(qtbot, service):
    """RuleEditDialog(…, parent_names=map) renders + resolves the same distinct
    breadcrumbed rows (the second flat-picker dialog)."""
    from finbreak.ui.rules import RuleEditDialog

    cs = CategorizationService(service.vault)
    _groc, _fuel, spar_g, spar_f = _seed_two_spars(service)
    grouped = cs.leaf_categories_grouped()
    names = cs.sub_category_parent_names()

    dialog = RuleEditDialog(grouped, parent_names=names)
    qtbot.addWidget(dialog)
    labels = _labels(dialog._category)
    assert _GROCERIES_SPAR in labels
    assert _FUEL_SPAR in labels
    assert _id_for_label(dialog._category, _GROCERIES_SPAR) == spar_g.id
    assert _id_for_label(dialog._category, _FUEL_SPAR) == spar_f.id


# --------------------------------------------------------------------------- #
# INV-4 per-site threading (capture-spy) — a site that forgets the map fails
# --------------------------------------------------------------------------- #
def test_INV4_set_category_site_threads_parent_names(qtbot, service, monkeypatch):
    """_on_set_category (transactions.py:403) constructs its CategoryPickerDialog
    with sub_category_parent_names()."""
    import finbreak.ui.transactions as txn_mod
    from finbreak.services.transactions import TransactionService
    from finbreak.ui.transactions import TransactionsView

    cs = CategorizationService(service.vault)
    _groc, _fuel, spar_g, _spar_f = _seed_two_spars(service)
    txn_id = _add_txn(service, "SPAR PURCHASE")

    view = TransactionsView(TransactionService(service.vault), cs)
    qtbot.addWidget(view)
    captured = stub_picker(monkeypatch, txn_mod, spar_g.id)
    spy_learning(monkeypatch, txn_mod, accept=False)  # dismiss the follow-on offer
    view._select_txn(txn_id)
    view._on_set_category()
    assert captured.parent_names == cs.sub_category_parent_names()


def test_INV4_learning_offer_site_threads_parent_names(qtbot, service, monkeypatch):
    """The learn-a-rule offer (transactions.py:420) constructs its RuleEditDialog
    with sub_category_parent_names()."""
    import finbreak.ui.transactions as txn_mod
    from finbreak.services.transactions import TransactionService
    from finbreak.ui.transactions import TransactionsView

    cs = CategorizationService(service.vault)
    _groc, _fuel, spar_g, _spar_f = _seed_two_spars(service)
    txn_id = _add_txn(service, "SPAR PURCHASE")

    view = TransactionsView(TransactionService(service.vault), cs)
    qtbot.addWidget(view)
    stub_picker(monkeypatch, txn_mod, spar_g.id)  # pick Spar (differs from would→None)
    calls = spy_learning(monkeypatch, txn_mod, accept=False)
    view._select_txn(txn_id)
    view._on_set_category()
    assert calls == [True], "the learn-a-rule offer was shown"
    assert calls.parent_names == cs.sub_category_parent_names()


def test_INV4_rules_add_site_threads_parent_names(qtbot, service, monkeypatch):
    """The Rules-editor Add (rules.py:196) constructs its RuleEditDialog with
    sub_category_parent_names()."""
    import finbreak.ui.rules as rules_mod
    from finbreak.ui.rules import RulesWidget

    cs = CategorizationService(service.vault)
    _seed_two_spars(service)

    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    calls = spy_learning(monkeypatch, rules_mod, accept=False)
    widget._add_button.click()
    assert calls == [True], "the rule dialog was constructed"
    assert calls.parent_names == cs.sub_category_parent_names()


def test_INV4_rules_edit_site_threads_parent_names(qtbot, service, monkeypatch):
    """The Rules-editor Edit (rules.py:221) constructs its RuleEditDialog with
    sub_category_parent_names()."""
    import finbreak.ui.rules as rules_mod
    from finbreak.ui.rules import RulesWidget

    cs = CategorizationService(service.vault)
    _groc, _fuel, spar_g, _spar_f = _seed_two_spars(service)
    cs.add_rule("spar", spar_g.id)

    widget = RulesWidget(service)
    qtbot.addWidget(widget)
    calls = spy_learning(monkeypatch, rules_mod, accept=False)
    widget._select_rule(cs.list_rules()[0].id)
    widget._edit_button.click()
    assert calls == [True], "the rule dialog was constructed"
    assert calls.parent_names == cs.sub_category_parent_names()


# --------------------------------------------------------------------------- #
# INV-4 Transactions filter combo (a real widget, no dialog)
# --------------------------------------------------------------------------- #
def test_INV4_filter_combo_renders_distinct_breadcrumbs(qtbot, service):
    """With transactions tagged to both Spar nodes, the Transactions category
    filter combo (transactions.py:255) shows the two distinct breadcrumbed rows."""
    from finbreak.services.transactions import TransactionService
    from finbreak.ui.transactions import TransactionsView

    cs = CategorizationService(service.vault)
    _groc, _fuel, spar_g, spar_f = _seed_two_spars(service)
    t1 = _add_txn(service, "SPAR GROCERIES")
    t2 = _add_txn(service, "SPAR FUEL")
    cs.set_manual_category(t1, spar_g.id)
    cs.set_manual_category(t2, spar_f.id)

    view = TransactionsView(TransactionService(service.vault), cs)
    qtbot.addWidget(view)
    labels = _labels(view._category)
    assert _GROCERIES_SPAR in labels
    assert _FUEL_SPAR in labels
