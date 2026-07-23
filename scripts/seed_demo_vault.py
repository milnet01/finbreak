#!/usr/bin/env python3
"""Seed a THROWAWAY finbreak vault with synthetic demo data (FIBR-0082).

Populates an already-first-run vault with a believable-but-fake picture: three
accounts, just over a year of categorised transactions (a spread of
South-African merchants in ZAR), a few auto-categorisation rules, a confirmed
transfer, and a set of confirmed recurring subscriptions — enough to make every
tab and the Home dashboard look "lived in" for marketing screenshots.

HARD CONSTRAINT (security-model INV-6 / testing.md §6): every name, merchant and
amount here is INVENTED. There is no real financial data, no real statement, and
the seeded vault is a throwaway artifact — never commit it (only the rendered
marketing PNGs are committed, under assets/). See ROADMAP FIBR-0082.

Used two ways:
  * imported by scripts/capture_screenshots.py, which calls ``seed(auth)``;
  * as a CLI to drop a demo vault in a directory for a live look:
        python scripts/capture_screenshots.py         # renders the PNGs
        python scripts/seed_demo_vault.py /tmp/demo    # a throwaway vault to poke at
"""

from __future__ import annotations

import calendar
from datetime import date

from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import CategorizationService
from finbreak.services.recurring import RecurringService
from finbreak.services.transfer_detection import TransferDetectionService

_MONTHS = 13  # months of history — fills the dashboard's 12-month trend chart

# The 3rd-level nesting we add under three default Expenditure leaves, purely to
# show off the three-deep category tree (Type › Category › Sub-category).
_NESTED = {
    "Transport": ["Fuel", "Ride-hailing"],
    "Bills & utilities": ["Electricity", "Mobile", "Internet"],
    "Entertainment": ["Streaming", "Dining out"],
}

# One month's transactions, repeated across the history with a gentle upward
# drift on the variable rows so the trend chart isn't flat.
#   (day, description, rands, leaf, account, rule_filed)
# rule_filed=True rows are left uncategorised so an auto-rule files them (they
# show as "auto" in the app); the rest are set by hand ("manual").
_MONTHLY: list[tuple[int, str, float, str, str, bool]] = [
    (1, "SA Home Loans", -9500, "Rent / Mortgage", "cheque", False),
    (25, "Acme (Pty) Ltd Salary", 32000, "Salary", "cheque", False),
    (28, "FNB Credit Interest", 85, "Interest", "cheque", False),
    (2, "DStv", -459, "Streaming", "credit", False),
    (3, "Netflix", -199, "Streaming", "credit", True),
    (5, "Spotify", -64.99, "Streaming", "credit", False),
    (7, "Vodacom Airtime", -599, "Mobile", "credit", True),
    (4, "Afrihost Fibre", -699, "Internet", "credit", False),
    (6, "City of Cape Town Electricity", -850, "Electricity", "cheque", False),
    (9, "Outsurance", -1180, "Insurance", "cheque", False),
    (8, "Woolworths", -1240, "Groceries", "cheque", True),
    (14, "Checkers", -980, "Groceries", "cheque", True),
    (21, "Pick n Pay", -430, "Groceries", "cheque", False),
    (11, "Engen Garage", -950, "Fuel", "cheque", True),
    (23, "Shell", -1100, "Fuel", "cheque", False),
    (12, "Uber", -120, "Ride-hailing", "cheque", True),
    (19, "Bolt", -95, "Ride-hailing", "cheque", False),
    (13, "Nando's", -180, "Fast food", "cheque", True),
    (18, "KFC", -145, "Fast food", "cheque", False),
    (16, "Dis-Chem Pharmacy", -340, "Medical", "cheque", False),
    (20, "Ocean Basket", -520, "Dining out", "cheque", False),
]
# Categories whose amounts drift month-to-month (cosmetic trend variation).
_VARIABLE = {"Groceries", "Fuel", "Fast food", "Dining out", "Ride-hailing"}

# Rules: substring → leaf. Rows whose description matches (and were flagged
# rule_filed) get auto-filed by apply_rules().
_RULES = [
    ("woolworths", "Groceries"),
    ("checkers", "Groceries"),
    ("engen", "Fuel"),
    ("uber", "Ride-hailing"),
    ("netflix", "Streaming"),
    ("vodacom", "Mobile"),
    ("nando", "Fast food"),
]


def _month_date(anchor: date, months_ago: int, day: int) -> str:
    """ISO date `day` of the month `months_ago` before `anchor` (day-clamped)."""
    total = anchor.year * 12 + (anchor.month - 1) - months_ago
    year, month = divmod(total, 12)
    month += 1
    day = min(day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def _cents(rands: float) -> int:
    return int(round(rands * 100))


def _build_categories(vault) -> dict[str, int]:
    """Return a {leaf-name: id} map, adding the 3-level nesting first. The three
    parents that gain children are dropped from the map so nothing files into a
    non-leaf (the app forbids it)."""
    cats = CategoryService(vault)
    repo = CategoryRepository(vault.connection)
    roots = repo.children_of(None)
    income = next(r for r in roots if r.kind == "income")
    expenditure = next(r for r in roots if r.kind == "expenditure")

    leaves: dict[str, int] = {c.name: c.id for c in repo.children_of(income.id)}
    exp = {c.name: c.id for c in repo.children_of(expenditure.id)}
    leaves.update(exp)
    for parent_name, kids in _NESTED.items():
        for kid in kids:
            leaves[kid] = cats.add_category(exp[parent_name], kid).id
        leaves.pop(parent_name, None)  # now a branch, not a leaf
    return leaves


def seed(auth: AuthService, *, today: date | None = None) -> None:
    """Populate `auth`'s unlocked vault with the synthetic demo picture."""
    anchor = today or date.today()
    vault = auth.vault

    # 1) Accounts — rename the seeded "Default" and add two more.
    accounts = AccountService(vault)
    default = accounts.list_accounts()[0]
    accounts.update_account(default.id, "Cheque account", "current")
    acct = {
        "cheque": default.id,
        "savings": accounts.add_account("Savings", "savings").id,
        "credit": accounts.add_account("Credit card", "current").id,
    }

    # 2) Categories (with 3-level nesting) + auto-rules.
    leaves = _build_categories(vault)
    cat = CategorizationService(vault)
    for pattern, leaf in _RULES:
        cat.add_rule(pattern, leaves[leaf])

    # 3) Transactions across the history. Collect manual (leaf) assignments to
    #    apply after the rule pass; rule_filed rows are left for apply_rules().
    txns = TransactionRepository(vault.connection)
    manual: list[tuple[int, int]] = []
    for months_ago in range(_MONTHS):
        drift = 1.0 + 0.03 * (_MONTHS - 1 - months_ago)  # recent months a touch higher
        for day, desc, rands, leaf, account, rule_filed in _MONTHLY:
            amount = rands * drift if leaf in _VARIABLE else rands
            txn_id = txns.add(
                acct[account],
                _month_date(anchor, months_ago, day),
                _cents(amount),
                desc,
            )
            if not rule_filed:
                manual.append((txn_id, leaves[leaf]))
        # An occasional clothing splurge, and the monthly savings transfer.
        if months_ago % 2 == 0:
            cid = txns.add(
                acct["cheque"],
                _month_date(anchor, months_ago, 17),
                _cents(-760),
                "Mr Price",
            )
            manual.append((cid, leaves["Clothing"]))
        txns.add(
            acct["cheque"],
            _month_date(anchor, months_ago, 26),
            _cents(-3000),
            "Transfer to Savings",
        )
        txns.add(
            acct["savings"],
            _month_date(anchor, months_ago, 26),
            _cents(3000),
            "Transfer from Cheque account",
        )

    # 4) File everything: rules first (auto rows), then the manual picks.
    cat.apply_rules()
    for txn_id, leaf_id in manual:
        cat.set_manual_category(txn_id, leaf_id)

    # 5) Confirm the recurring savings transfers (so they're excluded from
    #    income/spending AND from recurring detection).
    TransferDetectionService(vault).confirm_all()

    # 6) Confirm the obvious recurring money (subscriptions, salary, home loan) so
    #    the Recurring tab's Confirmed list + the dashboard's recurring card are
    #    populated — but leave the rest (groceries, insurance, …) as Suggested so
    #    the suggest-then-confirm workflow is visible in the screenshot too.
    recurring = RecurringService(vault)
    confirm_keys = (
        "netflix",
        "spotify",
        "dstv",
        "vodacom",
        "afrihost",
        "acme",
        "home loans",
    )
    for item in recurring.candidates(anchor):
        if any(key in item.merchant_key.lower() for key in confirm_keys):
            recurring.confirm(item.direction, item.merchant_key)


def _main() -> None:
    import sys
    from pathlib import Path

    if len(sys.argv) != 2:
        print("usage: python scripts/seed_demo_vault.py <dir>", file=sys.stderr)
        raise SystemExit(2)

    # A QApplication is needed only for QStandardPaths in the service layer.
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)
    auth = AuthService(target / "vault.db", target / "vault.kdf.json")
    auth.first_run(bytearray(b"demo-passphrase"), "ZAR")
    seed(auth)
    from finbreak.services.reporting import ReportingService

    count = ReportingService(auth.vault).transaction_count()
    auth.lock()
    print(f"Seeded a throwaway demo vault at {target} ({count} transactions).")
    print("Master password: demo-passphrase")


if __name__ == "__main__":
    _main()
