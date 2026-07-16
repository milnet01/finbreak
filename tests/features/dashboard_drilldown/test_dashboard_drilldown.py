"""FIBR-0138 — the expandable dashboard drill-down.

The pure merchant cleanup (``merchant_name``) and the whole ``drill_down`` tree are
tested headless over a seeded two-account vault; the widget shape + the tr()-ed
labels use the pytest-qt ``qtbot``. The period is pinned to a specific month so the
window is deterministic without a clock (the reporting-suite precedent).

Every number in the tree is summed from integer ``amount_minor`` (INV-1/INV-8); the
merchant/category/pair grouping only decides *which node* a row sits under, never the
totals — so the Income/Spending branch totals **equal** their dashboard tiles.
"""

from datetime import date
from decimal import Decimal

import pytest

from conftest import _PW
from finbreak.models import DrillLabels, DrillNode
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.reporting import ReportingRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import CategorizationService
from finbreak.services.recurring import RecurringService
from finbreak.services.reporting import (
    MODE_SPECIFIC_MONTH,
    ReportingService,
    ReportPrefs,
)
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.text import merchant_name, normalise_text

pytestmark = pytest.mark.features

_JAN = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=1)
_TODAY = date(2026, 7, 12)
# The tr()-ed fixed strings the QObject caller injects (D2/INV-9). In a test there is
# no translator, so we pass the plain English the UI would.
_LABELS = DrillLabels(
    income="Income",
    spending="Spending",
    transfers="Transfers",
    uncategorised="Uncategorised",
)


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


# --- seeding helpers ------------------------------------------------------- #
def _two_accounts(service):
    accounts = AccountService(service.vault)
    first = AccountRepository(service.vault.connection).list_all()[0].id
    second = accounts.add_account("Savings", "savings").id
    return first, second


def _add(service, account_id, amount_minor, occurred_on="2026-01-05", description="x"):
    return TransactionRepository(service.vault.connection).add(
        account_id, occurred_on, amount_minor, description
    )


def _root(service, kind):
    roots = CategoryRepository(service.vault.connection).children_of(None)
    return next(r for r in roots if r.kind == kind)


def _expenditure_leaf(service, name="Ztest Groceries"):
    return (
        CategoryService(service.vault)
        .add_category(_root(service, "expenditure").id, name)
        .id
    )


def _income_leaf(service, name="Ztest Salary"):
    return (
        CategoryService(service.vault)
        .add_category(_root(service, "income").id, name)
        .id
    )


def _set_cat(service, txn_id, category_id):
    CategorizationService(service.vault).set_manual_category(txn_id, category_id)


def _force_cat(service, txn_id, category_id):
    """Bind a row to a non-leaf category directly (the service ``_require_leaf``s;
    the D4a "non-leaf with its own rows" case needs the raw write)."""
    conn = service.vault.connection
    conn.execute(
        "UPDATE transactions SET category_id = ? WHERE id = ?", (category_id, txn_id)
    )
    conn.commit()


def _drill(service, account_ids=None, today=_TODAY):
    return ReportingService(service.vault).drill_down(
        _JAN, account_ids, today, labels=_LABELS
    )


def _child(node, label):
    """The single child of ``node`` whose label matches (fails if 0 or >1)."""
    matches = [c for c in node.children if c.label == label]
    assert len(matches) == 1, (
        f"expected one {label!r} under {node.label!r}, got {len(matches)}"
    )
    return matches[0]


def _assert_parent_sums_children(node):
    """INV-1: every non-leaf node's amount/count is the sum of its children's."""
    if node.children:
        assert node.amount == sum((c.amount for c in node.children), Decimal(0))
        assert node.count == sum(c.count for c in node.children)
        for c in node.children:
            _assert_parent_sums_children(c)


# --------------------------------------------------------------------------- #
# INV-5 — merchant_name: pure, total cleanup
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "noisy",
    [
        "POS 1234 WOOLWORTHS 5678",
        "woolworths",
        "WOOLWORTHS 09-08-2026",
        "  Woolworths  ",
        "PURCHASE WOOLWORTHS",
        "CARD 4321 Woolworths",
    ],
)
def test_INV5_noisy_descriptions_fold_to_one_key(noisy):
    """All the D3-foldable Woolworths variants share one grouping key."""
    assert normalise_text(merchant_name(noisy)) == "woolworths"


def test_INV5_blank_or_whitespace_returns_empty_never_raises():
    assert merchant_name("") == ""
    assert merchant_name("   ") == ""
    assert merchant_name("\t\n ") == ""


def test_INV5_digits_only_falls_back_to_trimmed_raw():
    """A description that cleans to empty keeps its raw identity (no blank label)."""
    assert merchant_name("1234567") == "1234567"
    assert merchant_name("  99-99  ") == "99-99"
    assert merchant_name("!!!") == "!!!"  # punctuation-only edges strip to empty → raw


def test_INV5_company_suffix_is_retained_v1():
    """v1 does NOT strip PTY/LTD — so a suffix keys separately (documents the
    behaviour; a future suffix-strip is then a deliberate change, not silent)."""
    assert normalise_text(merchant_name("WOOLWORTHS PTY LTD")) != normalise_text(
        merchant_name("WOOLWORTHS")
    )


def test_INV5_leading_prefixes_stripped_repeatedly_and_as_phrase():
    assert merchant_name("POS CARD WOOLWORTHS") == "Woolworths"
    assert merchant_name("DEBIT ORDER NETFLIX") == "Netflix"
    # A word that merely starts with a prefix is not stripped (whole-word match).
    assert "Cardiff" in merchant_name("CARDIFF STORES")


# --------------------------------------------------------------------------- #
# INV-3 — the richer read (drill_rows_in_range)
# --------------------------------------------------------------------------- #
def test_INV3_drill_rows_returns_five_tuple_with_description(service):
    a, _b = _two_accounts(service)
    _add(service, a, -50000, "2026-01-05", "POS WOOLWORTHS")
    rows = ReportingRepository(service.vault.connection).drill_rows_in_range(
        "2026-01-01", "2026-01-31", None
    )
    assert len(rows) == 1
    txn_id, occurred_on, amount_minor, category_id, description = rows[0]
    assert (occurred_on, amount_minor, category_id, description) == (
        "2026-01-05",
        -50000,
        None,
        "POS WOOLWORTHS",
    )


def test_INV3_drill_rows_account_and_window_semantics(service):
    a, b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-03")
    _add(service, b, 200000, "2026-01-04")
    _add(service, a, 300000, "2026-02-01")  # out of window
    repo = ReportingRepository(service.vault.connection)
    all_jan = repo.drill_rows_in_range("2026-01-01", "2026-01-31", None)
    assert {r[2] for r in all_jan} == {100000, 200000}  # both accounts, Feb excluded
    assert {
        r[2]
        for r in repo.drill_rows_in_range("2026-01-01", "2026-01-31", frozenset({a}))
    } == {100000}
    assert repo.drill_rows_in_range("2026-01-01", "2026-01-31", frozenset()) == []


# --------------------------------------------------------------------------- #
# INV-1 — the headline: branch totals equal the tiles
# --------------------------------------------------------------------------- #
def test_INV1_branch_totals_equal_the_summary_tiles(service):
    a, b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03")  # income 3000
    groceries = _expenditure_leaf(service)
    _set_cat(
        service, _add(service, a, -40000, "2026-01-04", "POS WOOLWORTHS"), groceries
    )
    _add(service, a, -15000, "2026-01-06", "CORNER SHOP")  # uncategorised expense
    debit = _add(service, a, -100000, "2026-01-10", "to savings")
    credit = _add(service, b, 100000, "2026-01-10", "from current")
    TransferDetectionService(service.vault).confirm(debit, credit)

    reporting = ReportingService(service.vault)
    summary = reporting.summary(_JAN, None, _TODAY)
    income, spending, transfers = reporting.drill_down(
        _JAN, None, _TODAY, labels=_LABELS
    )

    assert [n.label for n in (income, spending, transfers)] == [
        "Income",
        "Spending",
        "Transfers",
    ]
    assert income.amount == summary.income == Decimal("3000.00")
    assert spending.amount == summary.expenditure == Decimal("550.00")  # 400 + 150
    assert transfers.amount == Decimal("1000.00")  # only the confirmed transfer
    _assert_parent_sums_children(income)
    _assert_parent_sums_children(spending)
    _assert_parent_sums_children(transfers)


def test_INV1_drill_down_is_a_pure_read(service):
    a, _b = _two_accounts(service)
    _add(service, a, 300000, "2026-01-03")
    reporting = ReportingService(service.vault)
    before = reporting.summary(_JAN, None, _TODAY)
    reporting.drill_down(_JAN, None, _TODAY, labels=_LABELS)
    after = reporting.summary(_JAN, None, _TODAY)
    assert (before.income, before.expenditure, before.net) == (
        after.income,
        after.expenditure,
        after.net,
    )


# --------------------------------------------------------------------------- #
# INV-4 — category branch
# --------------------------------------------------------------------------- #
def test_INV4_nested_category_aggregates_into_parent_and_branch(service):
    a, _b = _two_accounts(service)
    exp_root = _root(service, "expenditure")
    parent = CategoryService(service.vault).add_category(exp_root.id, "Ztest Home")
    leaf = CategoryService(service.vault).add_category(parent.id, "Ztest Rent").id
    _set_cat(service, _add(service, a, -80000, "2026-01-05"), leaf)
    _set_cat(service, _add(service, a, -20000, "2026-01-06"), leaf)  # Rent total 1000

    _, spending, _ = _drill(service)
    home = _child(spending, "Ztest Home")
    assert home.amount == Decimal("1000.00")  # parent aggregates the leaf
    rent = _child(home, "Ztest Rent")
    assert rent.amount == Decimal("1000.00")
    assert rent.count == 2


def test_INV4_same_named_leaves_under_different_parents_stay_distinct(service):
    a, _b = _two_accounts(service)
    exp_root = _root(service, "expenditure")
    p1 = CategoryService(service.vault).add_category(exp_root.id, "Ztest A")
    p2 = CategoryService(service.vault).add_category(exp_root.id, "Ztest B")
    leaf1 = CategoryService(service.vault).add_category(p1.id, "Other").id
    leaf2 = CategoryService(service.vault).add_category(p2.id, "Other").id
    _set_cat(service, _add(service, a, -10000, "2026-01-05"), leaf1)
    _set_cat(service, _add(service, a, -20000, "2026-01-06"), leaf2)
    _, spending, _ = _drill(service)
    # Two distinct top nodes (A, B), each with its own "Other" leaf — not merged.
    assert {_child(spending, "Ztest A").amount, _child(spending, "Ztest B").amount} == {
        Decimal("100.00"),
        Decimal("200.00"),
    }


def test_INV4_uncategorised_is_one_none_node_even_if_a_leaf_is_named_that(service):
    a, _b = _two_accounts(service)
    real = _expenditure_leaf(service, "Uncategorised")  # a real leaf a user named that
    _set_cat(service, _add(service, a, -30000, "2026-01-05"), real)
    _add(service, a, -15000, "2026-01-06")  # genuinely uncategorised (category_id None)
    _, spending, _ = _drill(service)
    uncats = [c for c in spending.children if c.label == "Uncategorised"]
    # The real leaf and the synthetic None node both surface — the None node is
    # identified by its id, not the display name, so they stay distinct nodes.
    assert len(uncats) == 2
    assert {c.amount for c in uncats} == {Decimal("300.00"), Decimal("150.00")}


def test_INV4_empty_category_is_omitted(service):
    a, _b = _two_accounts(service)
    _expenditure_leaf(service, "Ztest Unused")  # a leaf with no rows
    used = _expenditure_leaf(service, "Ztest Used")
    _set_cat(service, _add(service, a, -10000, "2026-01-05"), used)
    _, spending, _ = _drill(service)
    assert [c.label for c in spending.children] == ["Ztest Used"]  # unused omitted


# --------------------------------------------------------------------------- #
# INV-1/INV-4 — the reachable, load-bearing edges
# --------------------------------------------------------------------------- #
def test_INV1_misset_cross_root_negative_row_still_under_spending(service):
    """A negative row filed under an Income-root leaf still surfaces under Spending
    (via its top-of-chain node) and the Spending total still equals the tile — the
    exact case the single "group by top-of-chain" rule protects."""
    a, _b = _two_accounts(service)
    inc_leaf = _income_leaf(service, "Ztest Bonus")
    _set_cat(
        service, _add(service, a, -25000, "2026-01-05"), inc_leaf
    )  # negative under income
    reporting = ReportingService(service.vault)
    _, spending, _ = reporting.drill_down(_JAN, None, _TODAY, labels=_LABELS)
    assert (
        spending.amount
        == reporting.summary(_JAN, None, _TODAY).expenditure
        == Decimal("250.00")
    )
    assert _child(spending, "Ztest Bonus").amount == Decimal("250.00")  # not dropped


def test_INV4_non_leaf_category_with_own_rows_shows_both_and_sorts(service):
    """A category with BOTH a child category AND its own rows renders both a child
    node and merchant nodes; the mixed sibling list sorts without raising (the
    INV-7 uniform-string key, the TypeError falsifier)."""
    a, _b = _two_accounts(service)
    exp_root = _root(service, "expenditure")
    parent = CategoryService(service.vault).add_category(exp_root.id, "Ztest Parent")
    child_leaf = (
        CategoryService(service.vault).add_category(parent.id, "Ztest Child").id
    )
    _set_cat(
        service, _add(service, a, -10000, "2026-01-05"), child_leaf
    )  # child bucket
    _force_cat(
        service, _add(service, a, -30000, "2026-01-06", "POS WOOLWORTHS"), parent.id
    )

    _, spending, _ = _drill(service)  # must not raise sorting the mixed list
    parent_node = _child(spending, "Ztest Parent")
    assert parent_node.amount == Decimal("400.00")  # own 300 + child 100
    child_labels = {c.label for c in parent_node.children}
    assert "Ztest Child" in child_labels  # the sub-category node
    assert "Woolworths" in child_labels  # a merchant node for its own bucket


def test_INV7_mixed_category_and_merchant_tie_reaches_the_string_key(service):
    """The INV-7 falsifier for the uniform-STRING third key: a category node and a
    merchant node that tie on BOTH magnitude AND label force the sort to compare the
    third key. If the category key regressed to an int (`child.id`) while merchants
    stay `f"mer:{k}"`, this int-vs-str compare would raise TypeError — so a clean
    build proves the key is uniformly a string."""
    a, _b = _two_accounts(service)
    exp_root = _root(service, "expenditure")
    parent = CategoryService(service.vault).add_category(exp_root.id, "Ztest Combo")
    # A child category literally named "Shop" holding one -100.00 row...
    shop_cat = CategoryService(service.vault).add_category(parent.id, "Shop").id
    _set_cat(service, _add(service, a, -10000, "2026-01-05", "misc"), shop_cat)
    # ...and the parent's OWN -100.00 row whose description cleans to merchant "Shop".
    _force_cat(service, _add(service, a, -10000, "2026-01-06", "SHOP"), parent.id)

    _, spending, _ = _drill(service)  # a TypeError here would fail the test
    combo = _child(spending, "Ztest Combo")
    # Two siblings, same label "Shop", same magnitude — one category node, one merchant.
    shop_children = [c for c in combo.children if c.label == "Shop"]
    assert len(shop_children) == 2
    assert {c.amount for c in shop_children} == {Decimal("100.00")}


def test_INV4_category_cycle_terminates_and_keeps_the_row(service):
    """Corrupt data — a category parent cycle X→Y→X (reachable by re-parenting X
    under its own child; CategoryService has no descendant guard) — must NOT hang or
    RecursionError the dashboard. Both the top-of-chain climb and the child recursion
    break the cycle with a visited set; the row is still counted (INV-1, no drop)."""
    a, _b = _two_accounts(service)
    exp_root = _root(service, "expenditure")
    x = CategoryService(service.vault).add_category(exp_root.id, "Ztest X")
    y = CategoryService(service.vault).add_category(x.id, "Ztest Y")
    conn = service.vault.connection
    conn.execute("UPDATE categories SET parent_id = ? WHERE id = ?", (y.id, x.id))
    conn.commit()  # X→Y→X: neither is a root now
    _force_cat(service, _add(service, a, -30000, "2026-01-05", "SHOP"), y.id)

    _, spending, _ = _drill(service)  # must return promptly, not spin or overflow
    assert spending.amount == Decimal("300.00")  # the row survives the cycle


def test_INV4_same_id_under_both_branches_no_double_count(service):
    """A leaf holding both a positive and a negative row yields a node under Income
    AND under Spending, each carrying only its own sign bucket."""
    a, _b = _two_accounts(service)
    leaf = _expenditure_leaf(service, "Ztest Mixed")
    _set_cat(service, _add(service, a, 50000, "2026-01-05"), leaf)  # positive
    _set_cat(service, _add(service, a, -20000, "2026-01-06"), leaf)  # negative
    income, spending, _ = _drill(service)
    assert _child(income, "Ztest Mixed").amount == Decimal("500.00")
    assert _child(spending, "Ztest Mixed").amount == Decimal("200.00")


# --------------------------------------------------------------------------- #
# INV-5 — merchant grouping is display-only and total
# --------------------------------------------------------------------------- #
def test_INV5_three_noisy_woolworths_collapse_to_one_merchant(service):
    a, _b = _two_accounts(service)
    leaf = _expenditure_leaf(service, "Ztest Groceries")
    _set_cat(
        service, _add(service, a, -10000, "2026-01-05", "POS 1234 WOOLWORTHS"), leaf
    )
    _set_cat(service, _add(service, a, -20000, "2026-01-06", "woolworths"), leaf)
    _set_cat(service, _add(service, a, -30000, "2026-01-07", "WOOLWORTHS 09-08"), leaf)
    _, spending, _ = _drill(service)
    groceries = _child(spending, "Ztest Groceries")
    merchant = _child(groceries, "Woolworths")
    assert merchant.count == 3
    assert merchant.amount == Decimal("600.00")  # 100 + 200 + 300 magnitude
    assert len(merchant.children) == 3  # three individual-transaction leaves
    assert all(leaf_.count == 1 and leaf_.children == () for leaf_ in merchant.children)


# --------------------------------------------------------------------------- #
# INV-2 / INV-6 — transfers excluded, drilled by account pair
# --------------------------------------------------------------------------- #
def test_INV2_confirmed_transfer_absent_from_categories_present_under_transfers(
    service,
):
    a, b = _two_accounts(service)
    debit = _add(service, a, -100000, "2026-01-10", "to savings")
    credit = _add(service, b, 100000, "2026-01-10", "from current")
    TransferDetectionService(service.vault).confirm(debit, credit)
    income, spending, transfers = _drill(service)
    assert spending.children == ()  # the debit leg is not ordinary spending
    assert income.children == ()  # the credit leg is not ordinary income
    pair = _child(transfers, "Default → Savings")
    assert pair.count == 1
    assert pair.amount == Decimal("1000.00")
    assert pair.children[0].amount == Decimal("1000.00")  # the individual move


def test_INV2_unconfirmed_pair_is_ordinary_income_and_spending(service):
    a, b = _two_accounts(service)
    _add(service, a, -100000, "2026-01-10", "MOVE OUT")
    _add(service, b, 100000, "2026-01-10", "MOVE IN")
    income, spending, transfers = _drill(service)
    assert spending.amount == Decimal("1000.00")  # still counted
    assert income.amount == Decimal("1000.00")
    assert transfers.children == ()  # nothing confirmed


def test_INV6_account_filter_keeps_transfer_when_either_leg_selected(service):
    a, b = _two_accounts(service)
    debit = _add(service, a, -100000, "2026-01-10", "to savings")
    credit = _add(service, b, 100000, "2026-01-10", "from current")
    TransferDetectionService(service.vault).confirm(debit, credit)
    # Selecting only the destination account still shows the transfer (credit leg).
    _, _, transfers = _drill(service, account_ids=frozenset({b}))
    assert transfers.amount == Decimal("1000.00")


def test_INV6_period_filter_keys_on_the_debit_leg_date(service):
    a, b = _two_accounts(service)
    debit = _add(service, a, -100000, "2026-02-10", "to savings")  # debit in Feb
    credit = _add(service, b, 100000, "2026-01-31", "from current")  # credit in Jan
    TransferDetectionService(service.vault).confirm(debit, credit)
    _, _, transfers = _drill(service)  # January period
    assert transfers.children == ()  # attributed to Feb (its debit month), not Jan


# --------------------------------------------------------------------------- #
# INV-7 — biggest-first, total order
# --------------------------------------------------------------------------- #
def test_INV7_siblings_descending_by_magnitude(service):
    a, _b = _two_accounts(service)
    fuel = _expenditure_leaf(service, "Ztest Fuel")
    food = _expenditure_leaf(service, "Ztest Food")
    _set_cat(service, _add(service, a, -70000, "2026-01-05"), fuel)  # 700
    _set_cat(service, _add(service, a, -30000, "2026-01-06"), food)  # 300
    _, spending, _ = _drill(service)
    assert [c.label for c in spending.children] == ["Ztest Fuel", "Ztest Food"]


def test_INV7_equal_magnitude_leaves_order_by_category_id(service):
    """Two same-named leaves with equal magnitude order deterministically — the
    total key falls through label to the per-node string key (category_id)."""
    a, _b = _two_accounts(service)
    exp_root = _root(service, "expenditure")
    p1 = CategoryService(service.vault).add_category(exp_root.id, "Ztest P1")
    p2 = CategoryService(service.vault).add_category(exp_root.id, "Ztest P2")
    o1 = CategoryService(service.vault).add_category(p1.id, "Same").id
    o2 = CategoryService(service.vault).add_category(p2.id, "Same").id
    _set_cat(service, _add(service, a, -10000, "2026-01-05"), o1)
    _set_cat(service, _add(service, a, -10000, "2026-01-06"), o2)  # equal magnitude
    # Deterministic across repeated builds (no ORDER BY in the read).
    first = [c.label for c in _drill(service)[1].children]
    second = [c.label for c in _drill(service)[1].children]
    assert first == second


def test_INV7_same_date_same_amount_txn_leaves_sort_totally(service):
    """Two leaves tying on BOTH magnitude and label (same date, same amount) still
    sort — the third `txn:{id}` key keeps the order total (no TypeError) and the tree
    deterministic build-to-build (the read has no ORDER BY)."""
    a, _b = _two_accounts(service)
    leaf = _expenditure_leaf(service, "Ztest Dup")
    _set_cat(service, _add(service, a, -10000, "2026-01-05", "SHOP"), leaf)
    _set_cat(
        service, _add(service, a, -10000, "2026-01-05", "SHOP"), leaf
    )  # same date+amt

    def snapshot():
        merchant = _child(_child(_drill(service)[1], "Ztest Dup"), "Shop")
        return [(c.label, c.amount, c.count) for c in merchant.children]

    assert len(snapshot()) == 2  # both leaves present, the tie did not collapse them
    assert snapshot() == snapshot()  # deterministic across independent builds


def test_INV7_three_top_nodes_are_always_fixed_order(service):
    _two_accounts(service)  # empty vault-of-data period
    _add(
        service,
        AccountRepository(service.vault.connection).list_all()[0].id,
        100,
        "2026-01-05",
    )
    assert [n.label for n in _drill(service)] == ["Income", "Spending", "Transfers"]


# --------------------------------------------------------------------------- #
# INV-4 / INV-7 / D8 — empty states
# --------------------------------------------------------------------------- #
def test_D8_income_only_period_has_zero_spending_and_transfers_nodes(service):
    a, _b = _two_accounts(service)
    _add(service, a, 500000, "2026-01-03")  # income only
    income, spending, transfers = _drill(service)
    assert income.amount == Decimal("5000.00")
    assert spending.count == 0 and spending.children == ()
    assert transfers.count == 0 and transfers.children == ()


# --------------------------------------------------------------------------- #
# UI (qtbot) — INV-3 / INV-9 wiring
# --------------------------------------------------------------------------- #
def _home(service):
    from finbreak.ui.home import HomeView

    return HomeView(
        ReportingService(service.vault),
        AccountService(service.vault),
        service,
        recurring=RecurringService(service.vault),
    )


def test_INV9_refresh_populates_tree_with_three_translated_tops(qtbot, service):
    """FIBR-0143: the three tops are now the three column HEADINGS; each column's
    tree shows that branch's children. The Expenditure column heading is the app's
    tr("Spending") word and its tree carries the None-bucket's tr("Uncategorised")."""
    from PySide6.QtWidgets import QLabel, QTreeWidget

    a, _b = _two_accounts(service)
    leaf = _expenditure_leaf(service, "Ztest Groceries")
    _set_cat(service, _add(service, a, -40000, "2026-01-05", "POS WOOLWORTHS"), leaf)
    _add(service, a, -15000, "2026-01-06", "CORNER SHOP")  # uncategorised
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)

    headings = [
        home.findChild(QLabel, f"dashboard_heading_{k}").text()
        for k in ("expenditure", "income", "transfers")
    ]
    assert headings == ["Spending", "Income", "Transfers"]
    # The None-category node carries the passed-in tr("Uncategorised") string in the
    # Expenditure column's tree, proving the service emitted no untranslated label.
    exp_tree = home.findChild(QTreeWidget, "dashboard_breakdown_expenditure")
    child_labels = {
        exp_tree.topLevelItem(i).text(0) for i in range(exp_tree.topLevelItemCount())
    }
    assert "Uncategorised" in child_labels


def test_INV9_service_threads_passed_labels_not_hardcoded_english(service):
    """The i18n falsifier: a drill_down that ignored `labels` and hard-coded the
    English strings would pass every other test (they use the English defaults).
    Sentinel labels prove the service actually threads the four passed strings —
    the three top nodes AND the None-bucket node — so it emits no untranslated label."""
    a, _b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-03")  # income, uncategorised
    _add(service, a, -20000, "2026-01-04")  # spending, uncategorised
    sentinels = DrillLabels(
        income="INC~", spending="SPND~", transfers="XFER~", uncategorised="UNCAT~"
    )
    income, spending, transfers = ReportingService(service.vault).drill_down(
        _JAN, None, _TODAY, labels=sentinels
    )
    assert [income.label, spending.label, transfers.label] == ["INC~", "SPND~", "XFER~"]
    assert _child(spending, "UNCAT~").amount == Decimal(
        "200.00"
    )  # None-bucket echoes it


def test_INV9_single_transaction_merchant_shows_bare_label_no_count(qtbot, service):
    """A count==1 merchant shows the bare label — no "×1" suffix (D7)."""
    from PySide6.QtWidgets import QTreeWidget

    a, _b = _two_accounts(service)
    leaf = _expenditure_leaf(service, "Ztest Groceries")
    _set_cat(service, _add(service, a, -10000, "2026-01-05", "POS WOOLWORTHS"), leaf)
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    tree = home.findChild(QTreeWidget, "dashboard_breakdown_expenditure")
    merchant_item = tree.topLevelItem(0).child(0)  # category → merchant (no branch row)
    assert merchant_item.text(0) == "Woolworths"  # bare, no "×1"


def test_INV9_merchant_node_shows_count_suffix_category_stays_bare(qtbot, service):
    from PySide6.QtWidgets import QTreeWidget

    a, _b = _two_accounts(service)
    leaf = _expenditure_leaf(service, "Ztest Groceries")
    _set_cat(service, _add(service, a, -10000, "2026-01-05", "POS WOOLWORTHS"), leaf)
    _set_cat(service, _add(service, a, -20000, "2026-01-06", "woolworths"), leaf)
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    tree = home.findChild(QTreeWidget, "dashboard_breakdown_expenditure")
    cat_item = tree.topLevelItem(0)  # category (no branch top row above it now)
    assert cat_item.text(0) == "Ztest Groceries"  # category: bare label, no ×N
    merchant_item = cat_item.child(0)
    assert "×2" in merchant_item.text(0)  # merchant with count>1: the ×N suffix


def test_INV9_tree_is_read_only(qtbot, service):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidget

    a, _b = _two_accounts(service)
    _add(service, a, -10000, "2026-01-05", "SHOP")
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    tree = home.findChild(QTreeWidget, "dashboard_breakdown_expenditure")
    item = tree.topLevelItem(0)  # the uncategorised SHOP row's category node
    assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)


def test_INV9_empty_vault_still_shows_getting_started(qtbot, service):
    home = _home(service)
    qtbot.addWidget(home)
    assert home.current_page().objectName() == "home_page_empty"


# --------------------------------------------------------------------------- #
# Ripple — the QScrollArea wrap is transparent to findChild
# --------------------------------------------------------------------------- #
def test_ripple_scrollarea_wrap_keeps_charts_and_tiles_resolvable(qtbot, service):
    from PySide6.QtCharts import QChartView
    from PySide6.QtWidgets import QLabel, QTreeWidget

    a, _b = _two_accounts(service)
    _add(service, a, 100000, "2026-01-03")
    service.set_report_prefs(_JAN)
    home = _home(service)
    qtbot.addWidget(home)
    assert home.current_page().objectName() == "home_page_dashboard"
    # A column header + pie + tree + the retained trend chart resolve through scroll.
    assert home.findChild(QLabel, "dashboard_total_income") is not None
    assert home.findChild(QChartView, "dashboard_pie_income") is not None
    assert home.findChild(QChartView, "dashboard_trend_chart") is not None
    assert home.findChild(QTreeWidget, "dashboard_breakdown_income") is not None


def test_ripple_drillnode_and_drilllabels_are_importable():
    """The new models exports don't disturb existing ones."""
    assert DrillNode(label="x", amount=Decimal("1"), count=1, children=()).count == 1
    assert DrillLabels("i", "s", "t", "u").uncategorised == "u"
