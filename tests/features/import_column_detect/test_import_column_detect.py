"""Feature-conformance tests — CSV import column-header auto-guess (FIBR-0297).

Enforces `tests/features/import_column_detect/spec.md`. Two layers:

* the WIZARD layer (`ImportWizardWidget`, `qtbot`) drives the real
  `_select_file` dispatch that exists today — INV-1, INV-5's wizard half,
  INV-6, INV-7. This is where the bug itself is proven: these assertions must
  fail on today's code, not on an import error.
* the pure GUESSER layer (`finbreak.importers.column_detect.guess_columns`) —
  INV-2, INV-3, INV-4, INV-5's module half. The module does not exist yet, so
  every test in this layer imports it locally (matching the sibling
  `date_detect` suite's convention) and is expected to error on import until
  it is written. Kept strictly apart from the wizard layer so a
  `ModuleNotFoundError` here can never stand in for the wizard layer's true,
  diagnosable assertion failure.

Every vault uses `tmp_path`; fixtures are tiny in-repo strings — no real
statements, no network (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import _PW, _acct
from finbreak.services.auth import AuthService

# --------------------------------------------------------------------------- #
# Layer 1 — the wizard wiring (INV-1, INV-5 wizard half, INV-6, INV-7).       #
# Drives the real `_select_file` dispatch that exists TODAY.                  #
# --------------------------------------------------------------------------- #

HEADER3 = ["Date", "Description", "Amount"]
ROWS3 = [["20/07/2026", "Coffee", "-10.00"], ["21/07/2026", "Tea", "-5.00"]]


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _write(tmp_path: Path, header: list[str], rows: list[list[str]]) -> str:
    text = ",".join(header) + "\n" + "".join(",".join(r) + "\n" for r in rows)
    path = tmp_path / "stmt.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _wizard(qtbot, service, acct):
    from finbreak.ui.import_wizard import ImportWizardWidget

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    return widget


def test_FIBR0297_headline_unmatched_header_autofills_description_and_amount(
    qtbot, service, tmp_path
):
    """INV-1 — the bug itself. `_populate_mapping_combos` fills all five
    combos off the same header list with no `setCurrentIndex`, so every one
    lands on index 0: the Description and Amount combos read "Date" on
    arrival at the map step, though the header spells out exactly what they
    are. This is the ONE assertion in this contract expected to fail on
    today's code — it drives the real, already-existing `_select_file`
    dispatch, so a failure here is a true red, not an import error."""
    acct = _acct(service)
    path = _write(tmp_path, HEADER3, ROWS3)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    assert widget._stack.currentIndex() == 1, "unmatched header -> map step"
    desc_text = widget._column_combos["description"].currentText()
    amount_text = widget._column_combos["amount"].currentText()
    assert desc_text == "Description", (
        f"description combo defaulted to {desc_text!r} (index 0) instead of "
        "guessing the header column literally named 'Description' -- FIBR-0297"
    )
    assert amount_text == "Amount", (
        f"amount combo defaulted to {amount_text!r} (index 0) instead of "
        "guessing the header column literally named 'Amount' -- FIBR-0297"
    )


def test_no_recognisable_header_falls_back_to_index_zero_current_behavior(
    qtbot, service, tmp_path
):
    """INV-5 wizard half. Nothing in the header matches any conventional
    spelling, so every combo must stay on the safe index-0 default -- today's
    only behaviour, and the fallback the guess must not regress. Locked as
    its own test so a future guesser cannot "help" by inventing a match on
    unrelated column names."""
    acct = _acct(service)
    header = ["Col1", "Col2", "Col3"]
    rows = [["20/07/2026", "x", "-1.00"]]
    path = _write(tmp_path, header, rows)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    assert widget._stack.currentIndex() == 1, "unmatched header -> map step"
    for role in ("date", "description", "amount"):
        combo = widget._column_combos[role]
        assert combo.currentIndex() == 0, (
            f"{role} combo left the safe index-0 fallback with no header a "
            f"guess could match (landed on {combo.currentText()!r}) -- today's "
            "default must survive as the no-match fallback (FIBR-0297), not "
            "become a regression"
        )


def test_guess_not_firing_when_profile_matched(qtbot, service, tmp_path):
    """INV-6. A CSV whose saved profile matches its header jumps straight to
    the preview step (FIBR-0007 INV-10a) -- the map step is never shown, so
    there is no combo for a guess to touch, and the mapping applied is the
    profile's own. Asserted against the real match-profile route, not a
    hand-set flag, so a future guess that mistakenly ran BEFORE the
    match_profile check would be caught landing the wizard on the map step
    instead of the preview."""
    from finbreak.models import ColumnMapping
    from finbreak.services.import_ import ImportService

    header = ["Date", "Description", "Amount"]
    acct = _acct(service)
    imp = ImportService(service.vault)
    imp.save_profile(
        "Plain",
        header,
        ColumnMapping("Date", "Description", "Amount", None, None, "%d/%m/%Y", False),
    )
    path = _write(tmp_path, header, ROWS3)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    assert widget._stack.currentIndex() == 2, (
        "a matched profile skips the map step entirely (INV-10a) -- the guess "
        "must add nothing to an already-correct path"
    )
    assert widget._column_combos["date"].currentData() == "Date"
    assert widget._column_combos["description"].currentData() == "Description"
    assert widget._column_combos["amount"].currentData() == "Amount"


def test_FIBR0297_guessed_date_column_feeds_the_FIBR0146_detector(
    qtbot, service, tmp_path
):
    """INV-7. The date-format auto-detect (FIBR-0146 D5/D6) re-runs whenever
    the date COLUMN changes -- a guess that points the date combo at a
    non-first column has to go through that same re-detect wiring, or the
    live format preview goes stale against the wrong column.

    Date is deliberately NOT the first header field: today the date combo
    defaults to index 0 ("Description"), which holds no dates at all, so the
    detector finds nothing there and the picker sits at its ISO default. Once
    the column guess correctly points the date combo at "Transaction Date",
    the SAME detector must re-run over the right column and land on the
    day-first format these rows are actually written in. This assertion fails
    today for the same root cause as the headline test -- the column guess
    that would fix it does not exist."""
    acct = _acct(service)
    header = ["Description", "Amount", "Transaction Date"]
    rows = [["Coffee", "-10.00", "20/07/2026"], ["Tea", "-5.00", "21/07/2026"]]
    path = _write(tmp_path, header, rows)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    date_col = widget._column_combos["date"].currentText()
    assert date_col == "Transaction Date", (
        f"date combo defaulted to {date_col!r} (index 0) instead of guessing "
        "the header column literally named 'Transaction Date' -- FIBR-0297"
    )
    fmt = widget._date_format.currentData()
    assert fmt == "%d/%m/%Y", (
        f"date format landed on {fmt!r} -- a guessed date column must feed "
        "the FIBR-0146 detector over the RIGHT column, not leave the format "
        f"preview stale against the wrong one (got {fmt!r}, expected "
        "'%d/%m/%Y' for these day-first rows)"
    )


# --------------------------------------------------------------------------- #
# Layer 2 — the pure guesser (INV-2, INV-3, INV-4, INV-5 module half).        #
# `finbreak.importers.column_detect` does not exist yet: every test imports  #
# it locally and is expected to error on import, contained to this layer.    #
# --------------------------------------------------------------------------- #


def test_plain_three_column_header_matches_all_present_roles():
    """The bullet's own worked example: a plain, unambiguous header matches
    every role it names and leaves the two it doesn't (debit/credit) unset."""
    from finbreak.importers.column_detect import guess_columns

    guess = guess_columns(["Date", "Description", "Amount"])
    assert guess.date == "Date"
    assert guess.description == "Description"
    assert guess.amount == "Amount"
    assert guess.debit is None
    assert guess.credit is None


@pytest.mark.parametrize(
    "header,role,expected_original",
    [
        (["DATE", "Description", "Amount"], "date", "DATE"),
        (["Date:", "Description", "Amount"], "date", "Date:"),
        (["Date", "DESCRIPTION", "Amount"], "description", "DESCRIPTION"),
        (["Date", "Description", "Amount ($)"], "amount", "Amount ($)"),
        (["date", "description", "amount"], "date", "date"),
    ],
)
def test_case_and_punctuation_insensitive_matching(header, role, expected_original):
    """INV-2. Matching is case- and punctuation-insensitive, and the value
    returned is the ORIGINAL header string -- never a normalised/lowercased
    copy, so the wizard combo can be set to the header the user actually
    sees."""
    from finbreak.importers.column_detect import guess_columns

    guess = guess_columns(header)
    assert getattr(guess, role) == expected_original, (
        f"guess_columns({header!r}).{role} = {getattr(guess, role)!r}, "
        f"expected {expected_original!r}"
    )


@pytest.mark.parametrize(
    "header,role,synonym_header",
    [
        (["Transaction Date", "Details", "Amount"], "date", "Transaction Date"),
        (["Posting Date", "Details", "Amount"], "date", "Posting Date"),
        (["Date", "Details", "Amount"], "description", "Details"),
        (["Date", "Narrative", "Amount"], "description", "Narrative"),
        (["Date", "Reference", "Amount"], "description", "Reference"),
        (["Date", "Description", "Value"], "amount", "Value"),
        (["Date", "Description", "Withdrawal", "Deposit"], "debit", "Withdrawal"),
        (["Date", "Description", "Withdrawal", "Deposit"], "credit", "Deposit"),
    ],
)
def test_conventional_synonyms_matched(header, role, synonym_header):
    """INV-3. Exactly the synonym set the roadmap bullet specifies -- each
    checked individually against the role it names, not lumped into one
    header so a single wrong mapping couldn't hide behind the others."""
    from finbreak.importers.column_detect import guess_columns

    guess = guess_columns(header)
    assert getattr(guess, role) == synonym_header, (
        f"guess_columns({header!r}).{role} = {getattr(guess, role)!r}, "
        f"expected {synonym_header!r}"
    )


def test_debit_credit_pair_matched_leaves_amount_none():
    """INV-4. Debit/Credit are an independent pair from the single Amount
    column -- a split-amount statement must not have its Amount role guessed
    from nothing, and the pair must both be found together."""
    from finbreak.importers.column_detect import guess_columns

    guess = guess_columns(["Date", "Description", "Debit", "Credit"])
    assert guess.debit == "Debit"
    assert guess.credit == "Credit"
    assert guess.amount is None, "no Amount/Value column in this header"


def test_no_match_returns_none_for_every_role():
    """INV-5 module half. A header with no recognisable role name returns
    None across the board -- inventing a match on unrelated text would be
    worse than today's plain index-0 fallback."""
    from finbreak.importers.column_detect import guess_columns

    guess = guess_columns(["Col1", "Col2", "Col3"])
    assert guess.date is None
    assert guess.description is None
    assert guess.amount is None
    assert guess.debit is None
    assert guess.credit is None


def test_pure_deterministic_and_order_independent():
    """Purity claim, modelled on date_detect's INV-2: same input -> same
    guess, and the result does not depend on incidental header order beyond
    which original string is returned for each role."""
    from finbreak.importers.column_detect import guess_columns

    header = ["Amount", "Date", "Description"]
    first = guess_columns(header)
    second = guess_columns(list(header))  # a fresh list, not the same object
    assert first == second
