"""FIBR-0012 INV-8/9 — the Transactions tab.

The set-category → learn-a-rule chain moved verbatim from the old HomeView (those
tests relocated here from the categorisation suite, retargeted to
``TransactionsView``). The four-filter bar (search / date range / account /
category) is new — each filter alone, all combined, "Uncategorised", and
re-sort-then-act (INV-9).
"""

import pytest
from PySide6.QtCore import QDate, Qt

from conftest import _PW, cell_text, spy_learning, stub_picker
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
_COL_DESCRIPTION = 3


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
    for r in range(view._table.model().rowCount()):
        if cell_text(view._table, r, 3) == description:
            return cell_text(view._table, r, 5)
    raise AssertionError(f"no visible row for {description!r}")


# --------------------------------------------------------------------------- #
# FIBR-0153 — dedicated Currency column + 6-column shape
# --------------------------------------------------------------------------- #
def test_FIBR0153_INV6_currency_column_shows_code(qtbot, service):
    """INV-6: every populated Currency cell holds the base-currency ISO code."""
    from finbreak.ui.transactions import _COL_CURRENCY

    _add_txn(service, "Coffee shop")
    _add_txn(service, "Rent payment")
    view = _view(service)
    qtbot.addWidget(view)
    code = TransactionService(service.vault).base_currency()
    rows = view._table.model().rowCount()
    assert rows == 2
    for r in range(rows):
        assert cell_text(view._table, r, _COL_CURRENCY) == code


def test_FIBR0153_INV7_column_shape_is_six_and_category_at_five(qtbot, service):
    """INV-7: 6 columns; a known category lands at _COL_CATEGORY (=5), not 4."""
    from finbreak.ui.transactions import _COL_CATEGORY

    g = _leaf_id(service, "Groceries")
    txn = _add_txn(service, "PICK N PAY")
    CategorizationService(service.vault).set_manual_category(txn, g)
    view = _view(service)
    qtbot.addWidget(view)
    assert view._table.model().columnCount() == 6
    assert _COL_CATEGORY == 5
    for r in range(view._table.model().rowCount()):
        if cell_text(view._table, r, 3) == "PICK N PAY":
            assert cell_text(view._table, r, _COL_CATEGORY) == "Groceries"
            break
    else:
        raise AssertionError("no visible row for PICK N PAY")


def test_FIBR0153_INV9_stale_five_column_layout_is_safe(qtbot, service, window_ini):
    """INV-9: a 5-section saved header blob in the window INI loads into the
    6-column table without crashing; the table stays 6 columns."""
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QTableWidget

    # A genuine 5-column header saveState() blob written under the table's INI key.
    old = QTableWidget(0, 5)
    old.setHorizontalHeaderLabels(
        ["Date", "Amount", "Description", "Account", "Category"]
    )
    blob = old.horizontalHeader().saveState()
    settings = QSettings(str(window_ini), QSettings.Format.IniFormat)
    settings.setValue("columns/transactions_table", blob)
    settings.sync()

    view = _view(service)  # must not raise applying the stale 5-column blob
    qtbot.addWidget(view)
    assert view._table.model().columnCount() == 6


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

    calls: list[int] = []

    def _boom(*a, **k):
        calls.append(1)
        raise VaultLockedError("locked mid-dialog")

    monkeypatch.setattr(view._categorization, "set_manual_category", _boom)
    stub_picker(monkeypatch, txn_mod, _leaf_id(service, "Groceries"))
    view._select_txn(txn)
    view._on_set_category()  # must not raise
    # A slot that never reaches the write would also not raise.
    assert calls == [1], (
        "precondition: the slot must reach set_manual_category, or the guard "
        "this test names was never exercised.\n"
        f"  expected: 1 call\n  actual:   {len(calls)}"
    )


def test_FIBR0396_set_category_after_an_auto_lock_does_nothing(
    qtbot, service, monkeypatch
):
    """The right-click menu runs a nested event loop, so the idle auto-lock can
    fire while it is open. "Set category…" then read the categories from a
    locked vault, and the exception escaped the slot; every sibling handler
    returns quietly instead."""
    import finbreak.ui.transactions as txn_mod

    txn = _add_txn(service, "PICK N PAY")
    view = _view(service)
    qtbot.addWidget(view)
    opened = stub_picker(monkeypatch, txn_mod, _leaf_id(service, "Groceries"))
    view._select_txn(txn)
    service.lock()  # the idle timer fired while the menu was open

    view._on_set_category()  # must not raise
    assert not opened, "no picker over a locked vault"


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
        cell_text(view._table, r, 3) for r in range(view._table.model().rowCount())
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
        cell_text(view._table, r, 3) for r in range(view._table.model().rowCount())
    }
    assert descriptions == {"Coffee shop"}  # only the January row


def test_INV9_account_filter(qtbot, service):
    _a, b, _g = _seed_mixed(service)
    view = _view(service)
    qtbot.addWidget(view)
    view._account.setCurrentIndex(view._account.findData(b))
    descriptions = {
        cell_text(view._table, r, 3) for r in range(view._table.model().rowCount())
    }
    assert descriptions == {"Coffee beans"}  # only account B


def test_INV9_category_filter_and_uncategorised(qtbot, service):
    _a, _b, groceries = _seed_mixed(service)
    view = _view(service)
    qtbot.addWidget(view)
    # A specific category.
    view._category.setCurrentIndex(view._category.findData(groceries))
    descriptions = {
        cell_text(view._table, r, 3) for r in range(view._table.model().rowCount())
    }
    assert descriptions == {"Coffee shop"}
    # "Uncategorised" selects category_id is None.
    view._category.setCurrentIndex(view._category.findData(None))
    descriptions = {
        cell_text(view._table, r, 3) for r in range(view._table.model().rowCount())
    }
    assert descriptions == {"Rent payment", "Coffee beans"}


def test_FIBR0123_filter_groups_present_categories(qtbot, service):
    _seed_mixed(service)  # one Expenditure category present; no income category
    view = _view(service)
    qtbot.addWidget(view)
    combo = view._category
    texts = [combo.itemText(i) for i in range(combo.count())]
    assert texts[0] == "All categories"
    assert texts[1] == "Uncategorised", "the special rows stay above headers (INV-5)"
    assert "Expenditure" in texts, "the present category's section header shows"
    assert any(t.endswith("(Expenditure)") for t in texts), "present rows are tagged"
    assert "Income" not in texts, "no income category present -> its section omitted"


def test_FIBR0123_filter_uncategorised_survives_refresh(qtbot, service):
    _seed_mixed(service)
    view = _view(service)
    qtbot.addWidget(view)
    view._category.setCurrentIndex(view._category.findData(None))
    assert view._category.currentText() == "Uncategorised"
    view.refresh()
    # findData(None) must resolve to Uncategorised, never a header (also data None).
    assert view._category.currentData() is None
    assert view._category.currentText() == "Uncategorised", "not a header after refresh"


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
        cell_text(view._table, r, 3) for r in range(view._table.model().rowCount())
    ]
    assert descriptions == ["Coffee shop"]
    # Clearing the search widens the set back (still AND of the other three).
    view._search.setText("")
    widened = {
        cell_text(view._table, r, 3) for r in range(view._table.model().rowCount())
    }
    assert widened == {"Coffee shop"}


def test_INV9_resort_then_context_acts_on_correct_txn(qtbot, service):
    a, _b, _g = _seed_mixed(service)
    coffee = _add_txn(service, "Zzz late coffee", a, -99999, "2026-01-11")
    view = _view(service)
    qtbot.addWidget(view)
    view._search.setText("coffee")  # narrow to the two coffee rows
    # Sort by Amount ascending — the biggest magnitude (-99999) goes first/last.
    view._table.sortByColumn(_COL_AMOUNT, Qt.SortOrder.AscendingOrder)
    view._select_txn(coffee)
    # The tag is over the FILTERED list, so the selection resolves to the right txn.
    assert view._selected_txn().id == coffee
    # The round trip above reads back through the same tag mapping, so it holds
    # even when the highlighted row shows a different transaction.
    shown = cell_text(view._table, view._table.currentIndex().row(), _COL_DESCRIPTION)
    assert shown == "Zzz late coffee", (
        "the highlighted row is not the transaction Set category acts on.\n"
        "  expected: 'Zzz late coffee'\n"
        f"  actual:   {shown!r}"
    )


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
    model = view._table.model()
    fg = Qt.ItemDataRole.ForegroundRole
    assert model.index(0, _COL_AMOUNT).data(fg).color() == _NEGATIVE_TEXT
    assert model.index(1, _COL_AMOUNT).data(fg).color() == _POSITIVE_TEXT
    assert model.index(2, _COL_AMOUNT).data(fg) is None
    assert model.index(0, _COL_DATE).data(fg) is None


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
    model = view._table.model()
    fg = Qt.ItemDataRole.ForegroundRole
    assert model.index(0, _COL_AMOUNT).data(fg).color() == _NEGATIVE_TEXT
    view.set_amount_prefs(AmountPrefs("minus", False))
    assert model.index(0, _COL_AMOUNT).data(fg) is None
    assert model.index(1, _COL_AMOUNT).data(fg) is None


def test_FIBR0327_ticking_date_range_does_not_empty_the_table(qtbot, service):
    """FIBR-0327 — a bare ``QDateEdit`` starts at Qt's own minimum, 2000-01-01.

    Both pickers were left there, so ticking "Date range" filtered to a single
    day nobody banks on: the table emptied, with no message saying why. The
    user's first act with the control made their transactions disappear.

    The range is seeded to span the loaded rows, so ticking the box narrows
    nothing until the user moves a picker. Asserted as the row count the user
    sees, before and after the tick.
    """
    _add_txn(service, "RENT", occurred_on="2026-01-05")
    _add_txn(service, "FUEL", occurred_on="2026-03-20")
    view = _view(service)
    qtbot.addWidget(view)
    view.refresh()
    before = view._table.model().rowCount()
    assert before == 2

    view._date_enable.setChecked(True)

    assert view._table.model().rowCount() == before, (
        "FIBR-0327: ticking the date range must not hide rows until the user "
        "narrows it.\n"
        f"  before: {before} rows\n"
        f"  after:  {view._table.model().rowCount()} rows\n"
        f"  range:  {view._date_from.date().toString('yyyy-MM-dd')} .. "
        f"{view._date_to.date().toString('yyyy-MM-dd')}"
    )
    # And the seeded range is the data's own span, not an arbitrary default.
    assert view._date_from.date() == QDate(2026, 1, 5)
    assert view._date_to.date() == QDate(2026, 3, 20)


def test_FIBR0327_a_range_the_user_set_survives_a_refresh(qtbot, service):
    """The seeding runs only while the box is unchecked, so a refresh — which a
    non-modal Settings save triggers on every tab — cannot overwrite a range the
    user chose."""
    _add_txn(service, "RENT", occurred_on="2026-01-05")
    _add_txn(service, "FUEL", occurred_on="2026-03-20")
    view = _view(service)
    qtbot.addWidget(view)
    view.refresh()

    view._date_enable.setChecked(True)
    view._date_from.setDate(QDate(2026, 3, 1))
    view._date_to.setDate(QDate(2026, 3, 31))
    assert view._table.model().rowCount() == 1  # FUEL only

    view.refresh()

    assert view._date_from.date() == QDate(2026, 3, 1), "the user's range stands"
    assert view._date_to.date() == QDate(2026, 3, 31)
    assert view._table.model().rowCount() == 1


# --------------------------------------------------------------------------- #
# FIBR-0097 — the table is a model over the filtered rows
# --------------------------------------------------------------------------- #
def _rows_view(service, monkeypatch, specs, **kwargs):
    """A TransactionsView over hand-built rows. Each spec is ``(description,
    occurred_on, display, account_name, category_name, category_source)``; the
    view's own vault holds no transactions, so no transfer label applies."""
    from finbreak.models import Transaction
    from finbreak.ui.transactions import TransactionsView

    txn = TransactionService(service.vault)
    rows = [
        (
            Transaction(
                i + 1,
                1,
                occurred_on,
                0,
                description,
                "2026-07-01T00:00:00",
                None,
                source,
            ),
            display,
            account,
            category,
        )
        for i, (description, occurred_on, display, account, category, source) in (
            enumerate(specs)
        )
    ]
    monkeypatch.setattr(txn, "list_transactions", lambda: rows)
    monkeypatch.setattr(txn, "base_currency", lambda: "ZAR")
    return TransactionsView(txn, CategorizationService(service.vault), **kwargs)


def _shown_descriptions(view):
    """The Description column, top to bottom, as the table shows it."""
    model = view._table.model()
    return [model.index(r, _COL_DESCRIPTION).data() for r in range(model.rowCount())]


def test_FIBR0097_refresh_formats_only_painted_rows(qtbot, service, monkeypatch):
    """INV-2: with 2,000 transactions in a shown 1200x800 view, a refresh formats
    the amounts Qt paints, not one per row."""
    from decimal import Decimal

    from PySide6.QtWidgets import QApplication

    import finbreak.ui.transactions as module

    specs = [
        (f"row{i}", "2026-07-01", Decimal(i), "Account", "", None) for i in range(2000)
    ]
    view = _rows_view(service, monkeypatch, specs)
    qtbot.addWidget(view)
    view.resize(1200, 800)
    view.show()
    qtbot.waitExposed(view)
    QApplication.processEvents()

    calls = 0
    real = module._format_amount

    def counting(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "_format_amount", counting)
    view.refresh()
    QApplication.processEvents()

    assert 0 < calls < 200, (
        "FIBR-0097 INV-2: a refresh must format only the painted Amount cells.\n"
        f"  _format_amount calls: {calls} for 2000 rows"
    )


def test_FIBR0097_each_column_sorts_by_its_key(qtbot, service, monkeypatch):
    """INV-3: a header sort orders by the column's key, not its text, keeps tied
    rows in their current order both ways, and the default is Date, newest
    first. Text order and key order disagree in every keyed column."""
    from decimal import Decimal

    from PySide6.QtCore import Qt

    from finbreak.services.auth import DATETIME_SYSTEM, DateTimePrefs
    from finbreak.ui.transactions import (
        _COL_ACCOUNT,
        _COL_CATEGORY,
        _COL_CURRENCY,
        _COL_DATE,
    )

    library = "library"
    # (description, date, display, account, category, source). dd/MM/yyyy puts
    # "20/12/2025" after "05/01/2026" as text; "-1000.00" sorts before "30.00"
    # as text either way round; "Groceries ~ guess" sorts after "Groceries
    # extra" as text while its key, "Groceries", sorts before it.
    specs = [
        ("a", "2026-01-05", Decimal("200.00"), "Cheque", "Groceries", library),
        ("b", "2025-12-20", Decimal("-1000.00"), "Savings", "Groceries extra", None),
        ("c", "2026-01-05", Decimal("30.00"), "Cheque", "Groceries", None),
        ("d", "2026-02-01", Decimal("30.00"), "Savings", "", None),
    ]
    keys = {
        _COL_DATE: {s[0]: s[1] for s in specs},
        _COL_AMOUNT: {s[0]: s[2] for s in specs},
        _COL_CURRENCY: {s[0]: "ZAR" for s in specs},
        _COL_DESCRIPTION: {s[0]: s[0] for s in specs},
        _COL_ACCOUNT: {s[0]: s[3] for s in specs},
        _COL_CATEGORY: {s[0]: s[4] for s in specs},
    }
    view = _rows_view(
        service,
        monkeypatch,
        specs,
        prefs=DateTimePrefs(DATETIME_SYSTEM, "dd/MM/yyyy", DATETIME_SYSTEM),
    )
    qtbot.addWidget(view)

    assert _shown_descriptions(view) == ["d", "a", "c", "b"], "Date, newest first"

    for column, key in keys.items():
        for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
            before = _shown_descriptions(view)
            view._table.sortByColumn(column, order)
            expected = sorted(
                before,
                key=key.__getitem__,
                reverse=order == Qt.SortOrder.DescendingOrder,
            )
            assert _shown_descriptions(view) == expected, (
                f"FIBR-0097 INV-3: column {column}, {order.name}\n"
                f"  before:   {before}\n"
                f"  expected: {expected}\n"
                f"  actual:   {_shown_descriptions(view)}"
            )


def test_FIBR0097_selection_survives_a_sort_and_not_a_refill(
    qtbot, service, monkeypatch
):
    """INV-4: the selection follows its transaction through a sort on any
    column, and a refill clears it."""
    from decimal import Decimal

    from PySide6.QtCore import Qt

    from finbreak.services.auth import AmountPrefs

    specs = [
        ("a", "2026-01-05", Decimal("200.00"), "Cheque", "Groceries", None),
        ("b", "2025-12-20", Decimal("-1000.00"), "Savings", "Rent", None),
        ("c", "2026-02-01", Decimal("30.00"), "Cheque", "", None),
    ]
    view = _rows_view(service, monkeypatch, specs)
    qtbot.addWidget(view)
    view._select_txn(2)  # "b"

    for column in range(6):
        for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
            view._table.sortByColumn(column, order)
            selected = view._selected_txn()
            assert selected is not None and selected.description == "b", (
                f"FIBR-0097 INV-4: the selection moved off 'b' on column {column}, "
                f"{order.name}: now {selected and selected.description!r}"
            )

    view.set_amount_prefs(AmountPrefs("minus", False))
    assert view._selected_txn() is None, "a refill clears the selection"


@pytest.mark.perf
def test_FIBR0097_refresh_scales_with_painted_rows(qtbot, service):
    """§ 7's perf check: print the refresh time at 2,000 and 20,000 rows, and at
    20,000 hold the refresh under 4x ``list_transactions()`` alone, timed here on
    the same machine (testing.md § 3.4). Measured 2026-10-19 at 20,000: the vault
    read 41 ms, the QTableWidget refresh 1,499 ms."""
    import time
    from datetime import UTC, date, datetime, timedelta

    from PySide6.QtWidgets import QApplication

    def best(fn):
        runs = []
        for _ in range(3):
            start = time.perf_counter()
            fn()
            runs.append(time.perf_counter() - start)
        return min(runs)

    account = _first_account(service)
    conn = service.vault.connection
    created = datetime.now(UTC).isoformat()
    view = _view(service)
    qtbot.addWidget(view)
    view.resize(1200, 800)
    view.show()
    qtbot.waitExposed(view)

    def refresh():
        view.refresh()
        QApplication.processEvents()

    seeded = 0
    for size in (2000, 20000):
        conn.executemany(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    account,
                    (date(2020, 1, 1) + timedelta(days=i % 2000)).isoformat(),
                    -(i % 9973) - 1,
                    f"PURCHASE {i}",
                    created,
                )
                for i in range(seeded, size)
            ],
        )
        conn.commit()
        seeded = size
        refresh_s = best(refresh)
        read_s = best(view._transactions.list_transactions)
        assert view._table.model().rowCount() == size
        print(
            f"\nFIBR-0097 perf: {size} rows — refresh {refresh_s * 1000:.0f} ms, "
            f"list_transactions {read_s * 1000:.0f} ms"
        )
    assert refresh_s < 4 * read_s, (
        f"at 20,000 rows the refresh took {refresh_s * 1000:.0f} ms, "
        f"{refresh_s / read_s:.1f}x the {read_s * 1000:.0f} ms vault read"
    )
