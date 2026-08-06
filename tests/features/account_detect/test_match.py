"""FIBR-0086 — normalisation + the matching ladder (INV-3, INV-4, INV-5, INV-9).

Pure functions over invented numbers; no vault, no Qt. Every value here is a
synthetic stand-in (INV-8) — see spec.md.
"""

import pytest

from finbreak.importers.base import SourceAccountHint
from finbreak.models import Account, AccountType
from finbreak.services.account_match import match_account, normalise_account_number


def _account(account_id: int, number: str | None) -> Account:
    return Account(
        id=account_id,
        name=f"Account {account_id}",
        type=AccountType.CURRENT,
        created_at="2026-01-01T00:00:00",
        account_number=number,
    )


# --- INV-5: normalisation ignores grouping and padding ----------------------


@pytest.mark.parametrize(
    "printed",
    ["11 222 333 4", "112223334", "000112223334", "00-112-223-334"],
)
def test_grouping_and_padding_normalise_alike(printed: str) -> None:
    """Grouping varies between layouts and padding varies (defensively) between
    statements; neither may decide identity."""
    assert normalise_account_number(printed) == "112223334"


def test_a_value_with_no_digits_normalises_to_empty() -> None:
    assert normalise_account_number("no digits") == ""


# --- INV-3: uniqueness is required before anything is selected --------------


def test_two_matches_select_nothing() -> None:
    """Two accounts on the same normalised number is 'ambiguous', not 'pick one'.

    They are stored in two different spellings on purpose: the collision has to
    survive normalisation, which is exactly the case a first-candidate-wins
    implementation would resolve silently and wrongly.
    """
    accounts = [_account(1, "11 222 333 4"), _account(2, "0112223334")]

    match = match_account(SourceAccountHint("112223334"), accounts)

    assert match.outcome == "ambiguous"
    assert match.account_id is None
    assert match.candidates == (1, 2)


def test_exactly_one_match_selects_it() -> None:
    accounts = [_account(1, "11 222 333 4"), _account(2, "22 333 444 5")]

    match = match_account(SourceAccountHint("112223334"), accounts)

    assert match.outcome == "matched"
    assert match.account_id == 1
    assert match.candidates == (1,)


def test_no_candidates_is_no_match() -> None:
    """Zero matches offers creation; it must not fall back to a nearby account."""
    match = match_account(SourceAccountHint("99 888 777 6"), [_account(1, "112223334")])

    assert match.outcome == "no_match"
    assert match.account_id is None
    assert match.candidates == ()


# --- INV-4: empty on either side never matches ------------------------------


def test_null_and_empty_never_match() -> None:
    """The ``"" == ""`` trap: an unnumbered account and an unreadable statement
    number both normalise to empty, and matching them would file every statement
    under every unnumbered account."""
    unnumbered = [_account(1, None), _account(2, "")]

    # A real number against accounts that carry none.
    assert (
        match_account(SourceAccountHint("112223334"), unnumbered).outcome == "no_match"
    )

    # A statement number that normalises to nothing, against the same accounts.
    empty_hint = match_account(SourceAccountHint("no digits"), unnumbered)
    assert empty_hint.outcome == "no_number"
    assert empty_hint.account_id is None
    assert empty_hint.candidates == ()


def test_absent_hint_is_no_number() -> None:
    """CSV carries no account number at all, and must not disturb the wizard."""
    match = match_account(None, [_account(1, "112223334")])

    assert match.outcome == "no_number"
    assert match.account_id is None
    assert match.normalised == ""


# --- INV-9: a masked number never matches -----------------------------------


@pytest.mark.parametrize(
    "masked", ["xxxx1234", "XXXX1234", "**** 1234", "1234 **** **** 5678"]
)
def test_masked_number_never_matches(masked: str) -> None:
    """Masked-tail matching is deferred, and this is what *enforces* the deferral.

    Normalisation strips non-digits, so ``xxxx1234`` becomes ``1234`` and would
    match a real account numbered 1234 — accidentally building the trailing-digit
    matching the spec declined to build deliberately. The check must therefore run
    on the raw value, before normalisation destroys the evidence.
    """
    match = match_account(SourceAccountHint(masked), [_account(1, "1234")])

    assert match.outcome == "no_number"
    assert match.account_id is None
    assert match.candidates == ()


def test_masked_check_precedes_normalisation() -> None:
    """The discriminator for 'the mask check runs first'.

    ``normalise_account_number`` really does reduce the masked spelling to the
    stored one — asserted here so that a future implementation that checks after
    normalising is visibly matching on a tail, not merely failing a unit test.
    """
    assert normalise_account_number("xxxx1234") == normalise_account_number("1234")
