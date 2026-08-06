"""FIBR-0086 — header-confined account-number extraction (INV-1, INV-2, INV-2a).

Every number here is invented (INV-8). The fixtures reproduce the *shapes*
measured on the real corpus, not its values.

Each fixture carries a line ``_table_region`` recognises as its family's column
header — for the non-C families, one containing ``balance`` plus one of
``debit``/``debits``/``withdrawals``/``date`` and no money token. Without it
``_table_region`` returns ``slice(0, 0)``, the header slice is empty, and these
tests would pass or fail for a reason unrelated to what they claim to lock.
"""

from finbreak.importers.standard_bank import (
    Family,
    _table_region,
    extract_account_number,
)


def _family_a_page(label_line: str) -> list[str]:
    """A family-A page: header block, column header, then transaction rows.

    The rows deliberately carry a *foreign* account number — real current-account
    statements print the home loan's number inside a transaction row, which is
    what confines extraction to the header (spec §2.4).
    """
    return [
        "THE STANDARD BANK OF SOUTH AFRICA LIMITED",
        "Statement from 1 September 2025 to 30 September 2025",
        "",
        label_line,
        "",
        "Details Service Date Balance",
        "PAYMENT RECEIVED 1,000.00 09 05 1,132.51",
        "SBSA HOMEL 447556667 250920 500.00- 09 20 632.51",
    ]


def test_extracts_the_header_label() -> None:
    """The base case the other two constrain: a family-A header yields its own
    number, the product name printed before the label, and the family."""
    page = _family_a_page("PRESTIGE CURRENT ACCOUNT Account Number 11 222 333 4")

    hint = extract_account_number(page, Family.A)

    assert hint is not None
    assert hint.number == "11 222 333 4"  # as printed — never normalised here
    assert hint.name == "PRESTIGE CURRENT ACCOUNT"
    assert hint.family == "A"


def test_fixture_column_header_is_recognised() -> None:
    """Guards the fixtures themselves.

    If ``_table_region`` stopped recognising these column-header lines it would
    return ``slice(0, 0)``, the header slice would be empty, and every test in
    this file would pass or fail for the wrong reason — the failure mode the
    spec calls out by name.
    """
    page = _family_a_page("Account Number 11 222 333 4")

    region = _table_region(page, Family.A)

    # Not slice(0, 0) — a header was actually found.
    assert region.start > 0
    # The label is above the boundary: the property extraction relies on.
    assert page.index("Account Number 11 222 333 4") < region.start
    # ...and the row carrying a FOREIGN account number is below it, so INV-2's
    # test discriminates rather than passing because the row was out of reach.
    foreign_row = next(i for i, line in enumerate(page) if "447556667" in line)
    assert foreign_row >= region.start


# --- INV-1 -------------------------------------------------------------------


def test_family_c_yields_none() -> None:
    """A credit-card statement's ``account number`` label names the DEBIT-ORDER
    account that pays the card, not the card (spec §2.3) — and it normalises to
    exactly the current account's number, so reading it files every card statement
    under the current account.

    Called **directly**, not through ``StandardBankImporter.parse``: the guard has
    to live in the extractor, or a future caller reintroduces the trap by dropping
    a call-site check.
    """
    page = [
        "Payment due Payment Information",
        "R205.48 will be processed",
        "through your debit order Total amount outstanding on this statement 6,849.68",
        "account number 000112223334 Minimum payment due 205.48",
        "on 20 August 2025. Payment due date 15 Aug 25",
        "Date Description Amount",
        "05 Aug 25 A MERCHANT 123.45",
    ]

    assert extract_account_number(page, Family.C) is None


# --- INV-2 -------------------------------------------------------------------


def test_ignores_number_in_transaction_rows() -> None:
    """Extraction reads only above ``_table_region(...).start``.

    The fixture's rows carry ``447556667`` — a different account's number, in the
    position a real current-account statement prints the home loan's. Widening the
    scan to the whole page picks it up and misfiles the statement.
    """
    page = _family_a_page("PRESTIGE CURRENT ACCOUNT Account Number 11 222 333 4")

    hint = extract_account_number(page, Family.A)

    assert hint is not None
    assert hint.number == "11 222 333 4"
    assert "447556667" not in hint.number


def test_label_below_the_column_header_is_not_read() -> None:
    """The other half of INV-2, stated positively: a label that falls *below* the
    boundary is invisible to extraction.

    This is the §6 failure mode — a layout change that slides the label under the
    column header degrades to manual rather than reading a transaction row.
    """
    page = [
        "THE STANDARD BANK OF SOUTH AFRICA LIMITED",
        "Details Service Date Balance",
        "PAYMENT RECEIVED 1,000.00 09 05 1,132.51",
        "Account Number 11 222 333 4",
    ]

    assert extract_account_number(page, Family.A) is None


# --- INV-2a ------------------------------------------------------------------


def test_capture_stops_at_column_gap() -> None:
    """The captured run allows a SINGLE space between digits, so it ends at a
    two-space column boundary instead of swallowing the next column.

    A greedy ``[\\d\\s-]*`` crosses any whitespace and merges the date column into
    the key, producing a number that matches no account.
    """
    page = _family_a_page("Account Number 44 555 666 7   2024 03 27")

    hint = extract_account_number(page, Family.A)

    assert hint is not None
    assert hint.number == "44 555 666 7"


# --- families that print no name --------------------------------------------


def test_family_b_has_no_name_prefix() -> None:
    """Families B and D print nothing before the label, so ``name`` is None and the
    create form leaves the box empty rather than prefilling a stray fragment."""
    page = [
        "THE STANDARD BANK OF SOUTH AFRICA LIMITED",
        "Account Number 447556667",
        "",
        "Posting Date Effective Date Description Debit Credit Balance",
        "2025-03-01 BROUGHT FORWARD 58,175.07",
    ]

    hint = extract_account_number(page, Family.B)

    assert hint is not None
    assert hint.number == "447556667"
    assert hint.name is None
    assert hint.family == "B"


def test_no_label_yields_none() -> None:
    """No label, no hint — the wizard shows nothing and the user picks, exactly as
    it does today."""
    page = [
        "THE STANDARD BANK OF SOUTH AFRICA LIMITED",
        "Details Service Date Balance",
        "PAYMENT RECEIVED 1,000.00 09 05 1,132.51",
    ]

    assert extract_account_number(page, Family.A) is None
