"""FIBR-0012 INV-8/9 — the Transactions tab.

The set-category → learn-a-rule chain moved verbatim from the old HomeView (those
tests relocated here from the categorisation suite, retargeted to
``TransactionsView``). The four-filter bar (search / date range / account /
category) is new — each filter alone, all combined, "Uncategorised", and
re-sort-then-act (INV-9).
"""

import pytest
from PySide6.QtCore import QDate

from conftest import _PW, spy_learning, stub_picker
from finbreak.errors import VaultLockedError
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService

pytestmark = pytest.mark.features

_COL_AMOUNT = 1


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _view(service):
    from finbreak.ui.transactions import TransactionsView

    return TransactionsView(
        TransactionService(service.vault), CategorizationService(service.vault)
    )


def _first_account(service):
    return AccountRepository(service.vault.connection).list_all()[0].id


def _leaf_id(service, name):
    """The id of an existing leaf category by name (reuses the migration-seeded
    tree; 'Groceries' / 'Fast food' are pre-seeded leaves)."""
    for c in CategoryService(service.vault).list_all():
        if c.parent_id is not None and c.name == name:
            return c.id
    raise AssertionError(f"no leaf category named {name!r}")


def _add_leaf(service, name):
    """Create a NEW leaf under the Expenditure root (a name not in the seed tree)."""
    roots = CategoryRepository(service.vault.connection).children_of(None)
    exp = next(r for r in roots if r.kind == "expenditure")
    return CategoryService(service.vault).add_category(exp.id, name).id


def _add_txn(
    service, description, account_id=None, amount=-1000, occurred_on="2026-01-05"
):
    account_id = account_id or _first_account(service)
    return TransactionRepository(service.vault.connection).add(
        account_id, occurred_on, amount, description
    )


def _txn_cat(service, txn_id):
    row = service.vault.connection.execute(
        "SELECT category_id, category_source FROM transactions WHERE id = ?", (txn_id,)
    ).fetchone()
    return (row[0], row[1])


def _cat_cell(view, description):
    for r in range(view._table.rowCount()):
        if view._table.item(r, 2).text() == description:
            return view._table.item(r, 4).text()
    raise AssertionError(f"no visible row for {description!r}")


# --------------------------------------------------------------------------- #
# INV-8 — relocated set-category + learn-a-rule chain (moved from categorisation)
# --------------------------------------------------------------------------- #
def test_INV8_renders_category_and_context_set(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as txn_mod

    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    txn = _add_txn(service, "PICK N PAY")
    cs.add_rule("pick n pay", g)
    cs.apply_rules()

    view = _view(service)
    qtbot.addWidget(view)
    assert _cat_cell(view, "PICK N PAY") == "Groceries"

    stub_picker(monkeypatch, txn_mod, f)  # correct it to Fast food
    spy_learning(monkeypatch, txn_mod, accept=False)  # dismiss the learning offer
    view._select_txn(txn)
    view._on_set_category()

    assert _txn_cat(service, txn) == (f, "manual")
    assert _cat_cell(view, "PICK N PAY") == "Fast food"


def test_INV8_offer_shown_correcting_a_rule_row(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as txn_mod

    cs = CategorizationService(service.vault)
    g, f = _leaf_id(service, "Groceries"), _leaf_id(service, "Fast food")
    txn = _add_txn(service, "PICK N PAY")
    cs.add_rule("pick n pay", g)
    cs.apply_rules()

    view = _view(service)
    qtbot.addWidget(view)
    stub_picker(monkeypatch, txn_mod, f)
    calls = spy_learning(monkeypatch, txn_mod, accept=False)
    view._select_txn(txn)
    view._on_set_category()
    assert calls == [True]


def test_INV8_no_offer_when_choice_matches_rules(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as txn_mod

    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    txn = _add_txn(service, "PICK N PAY")
    cs.add_rule("pick n pay", g)
    cs.apply_rules()

    view = _view(service)
    qtbot.addWidget(view)
    stub_picker(monkeypatch, txn_mod, g)  # same leaf the rules already produce
    calls = spy_learning(monkeypatch, txn_mod, accept=False)
    view._select_txn(txn)
    view._on_set_category()
    assert calls == []


def test_INV8_no_offer_on_a_manual_clear(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as txn_mod

    txn = _add_txn(service, "PICK N PAY")
    view = _view(service)
    qtbot.addWidget(view)
    stub_picker(monkeypatch, txn_mod, None)  # Uncategorised (a clear)
    calls = spy_learning(monkeypatch, txn_mod, accept=False)
    view._select_txn(txn)
    view._on_set_category()
    assert calls == []


def test_INV8_accepting_offer_creates_rule_and_refiles(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as txn_mod

    cs = CategorizationService(service.vault)
    g = _leaf_id(service, "Groceries")
    t1 = _add_txn(service, "PICK N PAY 1")
    t2 = _add_txn(service, "PICK N PAY 2")

    view = _view(service)
    qtbot.addWidget(view)
    stub_picker(monkeypatch, txn_mod, g)
    spy_learning(monkeypatch, txn_mod, accept=True, ret_pattern="pick n pay", ret_cat=g)
    view._select_txn(t1)
    view._on_set_category()

    assert len(cs.list_rules()) == 1
    assert _txn_cat(service, t1) == (g, "manual")
    assert _txn_cat(service, t2) == (g, "rule")


def test_INV8_set_category_catches_vault_locked(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as txn_mod

    txn = _add_txn(service, "PICK N PAY")
    view = _view(service)
    qtbot.addWidget(view)

    def _boom(*a, **k):
        raise VaultLockedError("locked mid-dialog")

    monkeypatch.setattr(view._categorization, "set_manual_category", _boom)
    stub_picker(monkeypatch, txn_mod, _leaf_id(service, "Groceries"))
    view._select_txn(txn)
    view._on_set_category()  # must not raise


def test_INV8_learning_path_refresh_catches_vault_locked(qtbot, service, monkeypatch):
    """The learn-a-rule accept slot (_apply_learned_rule) ends with refresh(); an
    auto-lock that fired while the offer was open makes that refresh read a locked
    vault. Drive _apply_learned_rule directly (moved verbatim from the Home path)."""
    from conftest import RuleStub

    g = _leaf_id(service, "Groceries")
    view = _view(service)
    qtbot.addWidget(view)
    dialog = RuleStub(view, "pick n pay", g, accept=True)

    def _raise():
        raise VaultLockedError("auto-lock fired while the learning offer was open")

    monkeypatch.setattr(view._transactions, "list_transactions", _raise)
    view._apply_learned_rule(dialog)  # must not raise — refresh() is inside the guard
    assert CategorizationService(service.vault).would_categorize("pick n pay") == g


# --------------------------------------------------------------------------- #
# FIBR-0123 INV-1/INV-3/INV-7 — CategoryPickerDialog now takes grouped data
# --------------------------------------------------------------------------- #
def test_FIBR0123_picker_rests_on_uncategorised(qtbot, service):
    from finbreak.ui.category_picker import CategoryPickerDialog

    grouped = CategorizationService(service.vault).leaf_categories_grouped()
    dialog = CategoryPickerDialog(grouped, None)
    qtbot.addWidget(dialog)
    assert dialog._combo.currentIndex() == 0
    assert dialog.selected_category_id() is None, "the default rests on Uncategorised"


def test_FIBR0123_picker_prefills_stored_category(qtbot, service):
    from finbreak.ui.category_picker import CategoryPickerDialog

    grouped = CategorizationService(service.vault).leaf_categories_grouped()
    leaf_id = grouped[0][1][0].id
    dialog = CategoryPickerDialog(grouped, leaf_id)
    qtbot.addWidget(dialog)
    assert dialog.selected_category_id() == leaf_id, "prefill selects the stored id"


def test_FIBR0123_picker_groups_under_headers(qtbot, service):
    from finbreak.ui.category_picker import CategoryPickerDialog

    grouped = CategorizationService(service.vault).leaf_categories_grouped()
    dialog = CategoryPickerDialog(grouped, None)
    qtbot.addWidget(dialog)
    combo = dialog._combo
    texts = [combo.itemText(i) for i in range(combo.count())]
    assert texts[0] == "Uncategorised", "the special row stays at index 0"
    assert "Income" in texts and "Expenditure" in texts, "section headers present"
    assert any(t.endswith("(Income)") for t in texts), "rows carry the Type tag"


# --------------------------------------------------------------------------- #
# INV-9 — the four filters, alone and combined
# --------------------------------------------------------------------------- #
def _seed_mixed(service):
    """Two accounts; a few dated/categorised rows for the filter matrix."""
    a = _first_account(service)
    b = AccountService(service.vault).add_account("Savings", "savings").id
    groceries = _add_leaf(service, "Ztest Groceries")
    coffee_a = _add_txn(service, "Coffee shop", a, -3000, "2026-01-10")
    _add_txn(service, "Rent payment", a, -800000, "2026-02-15")
    _add_txn(service, "Coffee beans", b, -5000, "2026-03-20")  # account B
    _set = CategorizationService(service.vault).set_manual_category
    _set(coffee_a, groceries)
    return a, b, groceries


def test_INV9_search_filters_by_description_substring(qtbot, service):
    _seed_mixed(service)
    view = _view(service)
    qtbot.addWidget(view)
    view._search.setText("coffee")  # case-insensitive
    descriptions = {
        view._table.item(r, 2).text() for r in range(view._table.rowCount())
    }
    assert descriptions == {"Coffee shop", "Coffee beans"}


def test_INV9_date_range_filter(qtbot, service):
    _seed_mixed(service)
    view = _view(service)
    qtbot.addWidget(view)
    view._date_enable.setChecked(True)
    view._date_from.setDate(QDate(2026, 1, 1))
    view._date_to.setDate(QDate(2026, 1, 31))
    descriptions = {
        view._table.item(r, 2).text() for r in range(view._table.rowCount())
    }
    assert descriptions == {"Coffee shop"}  # only the January row


def test_INV9_account_filter(qtbot, service):
    _a, b, _g = _seed_mixed(service)
    view = _view(service)
    qtbot.addWidget(view)
    view._account.setCurrentIndex(view._account.findData(b))
    descriptions = {
        view._table.item(r, 2).text() for r in range(view._table.rowCount())
    }
    assert descriptions == {"Coffee beans"}  # only account B


def test_INV9_category_filter_and_uncategorised(qtbot, service):
    _a, _b, groceries = _seed_mixed(service)
    view = _view(service)
    qtbot.addWidget(view)
    # A specific category.
    view._category.setCurrentIndex(view._category.findData(groceries))
    descriptions = {
        view._table.item(r, 2).text() for r in range(view._table.rowCount())
    }
    assert descriptions == {"Coffee shop"}
    # "Uncategorised" selects category_id is None.
    view._category.setCurrentIndex(view._category.findData(None))
    descriptions = {
        view._table.item(r, 2).text() for r in range(view._table.rowCount())
    }
    assert descriptions == {"Rent payment", "Coffee beans"}


def test_INV9_all_filters_combine_AND(qtbot, service):
    a, _b, groceries = _seed_mixed(service)
    view = _view(service)
    qtbot.addWidget(view)
    view._search.setText("coffee")
    view._date_enable.setChecked(True)
    view._date_from.setDate(QDate(2026, 1, 1))
    view._date_to.setDate(QDate(2026, 1, 31))
    view._account.setCurrentIndex(view._account.findData(a))
    view._category.setCurrentIndex(view._category.findData(groceries))
    # Only "Coffee shop" satisfies all four at once.
    descriptions = [
        view._table.item(r, 2).text() for r in range(view._table.rowCount())
    ]
    assert descriptions == ["Coffee shop"]
    # Clearing the search widens the set back (still AND of the other three).
    view._search.setText("")
    descriptions = {
        view._table.item(r, 2).text() for r in range(view._table.rowCount())
    }
    assert descriptions == {"Coffee shop"}


def test_INV9_resort_then_context_acts_on_correct_txn(qtbot, service):
    a, _b, _g = _seed_mixed(service)
    coffee = _add_txn(service, "Zzz late coffee", a, -99999, "2026-01-11")
    view = _view(service)
    qtbot.addWidget(view)
    view._search.setText("coffee")  # narrow to the two coffee rows
    # Sort by Amount ascending — the biggest magnitude (-99999) goes first/last.
    view._table.sortItems(_COL_AMOUNT)
    view._select_txn(coffee)
    # The tag is over the FILTERED list, so the selection resolves to the right txn.
    assert view._selected_txn().id == coffee


# --------------------------------------------------------------------------- #
# FIBR-0105 amount colour/direction — moved with the table from the Home path
# --------------------------------------------------------------------------- #
def _stub_view(service, monkeypatch, displays, amount_prefs):
    """A TransactionsView over controlled display Decimals — the only way to render
    a zero-amount row (the service rejects zero amounts), so all three colour
    branches (neg/pos/zero) are exercised deterministically (FIBR-0105 INV-4)."""
    from finbreak.models import Transaction
    from finbreak.ui.transactions import TransactionsView

    txn = TransactionService(service.vault)
    rows = [
        (
            Transaction(
                i + 1, 1, "2026-07-01", 0, f"row{i}", "2026-07-01T00:00:00", None, None
            ),
            display,
            "Account",
            "",
        )
        for i, display in enumerate(displays)
    ]
    monkeypatch.setattr(txn, "list_transactions", lambda: rows)
    monkeypatch.setattr(txn, "base_currency", lambda: "ZAR")
    return TransactionsView(
        txn, CategorizationService(service.vault), amount_prefs=amount_prefs
    )


def test_FIBR0105_amount_colour_marks_direction_when_on(qtbot, service, monkeypatch):
    from decimal import Decimal

    from PySide6.QtCore import Qt

    from finbreak.services.auth import AmountPrefs
    from finbreak.ui._amount import _NEGATIVE_TEXT, _POSITIVE_TEXT

    _COL_DATE = 0
    view = _stub_view(
        service,
        monkeypatch,
        [Decimal("-25000.00"), Decimal("100.00"), Decimal("0.00")],
        AmountPrefs("minus", True),
    )
    qtbot.addWidget(view)
    table = view._table
    assert table.item(0, _COL_AMOUNT).foreground().color() == _NEGATIVE_TEXT
    assert table.item(1, _COL_AMOUNT).foreground().color() == _POSITIVE_TEXT
    assert table.item(2, _COL_AMOUNT).data(Qt.ItemDataRole.ForegroundRole) is None
    assert table.item(0, _COL_DATE).data(Qt.ItemDataRole.ForegroundRole) is None


def test_FIBR0105_amount_colour_off_sets_no_foreground(qtbot, service, monkeypatch):
    from decimal import Decimal

    from PySide6.QtCore import Qt

    from finbreak.services.auth import AmountPrefs
    from finbreak.ui._amount import _NEGATIVE_TEXT

    view = _stub_view(
        service,
        monkeypatch,
        [Decimal("-25000.00"), Decimal("100.00")],
        AmountPrefs("minus", True),
    )
    qtbot.addWidget(view)
    table = view._table
    assert table.item(0, _COL_AMOUNT).foreground().color() == _NEGATIVE_TEXT
    view.set_amount_prefs(AmountPrefs("minus", False))
    assert table.item(0, _COL_AMOUNT).data(Qt.ItemDataRole.ForegroundRole) is None
    assert table.item(1, _COL_AMOUNT).data(Qt.ItemDataRole.ForegroundRole) is None
