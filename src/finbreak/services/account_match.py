"""Match a statement's printed account number to a configured account (FIBR-0086).

Pure functions over value objects — no vault, no Qt, no I/O. The wizard calls
``match_account`` once per parsed statement and uses the outcome to decide whether
to change its destination pre-selection. Where the statement names its bank, an
account recorded at a different bank is never a candidate (FIBR-0284).

The design rule the whole module protects: **ambiguity degrades to manual, never
to a guess.** Only an unambiguous single match ever changes what the user sees
selected; every other outcome leaves the wizard exactly as it is today.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from finbreak.importers.base import SourceAccountHint
from finbreak.models import Account
from finbreak.text import fold_name

# A masked identifier — a statement showing only a tail (``xxxx1234``,
# ``1234 **** **** 5678``). Matching on a masked tail is deliberately not built
# (FIBR-0086 §3 decision 3); this is what enforces that, because normalisation
# strips non-digits and would otherwise turn "xxxx1234" into a clean "1234" that
# matches a real account numbered 1234.
_MASK_CHARS = frozenset("*xX")

# What a real account number is allowed to contain: digits, and the separators the
# measured layouts use for grouping. Anything else means the value is not a plain
# number — a mask, a label, a fragment — and must not be matched on.
_PLAIN_NUMBER = re.compile(r"[\d -]*\Z")


def _is_masked(raw: str) -> bool:
    """Is this a masked / non-plain identifier rather than a full number?

    Checked on the RAW value, before normalisation, because normalisation strips
    non-digits and so destroys the evidence: ``xxxx1234`` becomes ``1234``, which
    matches a real account numbered 1234 — the trailing-digit matching FIBR-0086
    §3 decision 3 declined to build.

    Deliberately a whitelist of what a number may contain, not a denylist of the
    three mask characters the corpus happens to print: ``####1234`` and
    ``ending 1234`` mask just as effectively and a denylist would let both match.
    """
    return bool(raw) and (
        any(ch in _MASK_CHARS for ch in raw) or not _PLAIN_NUMBER.match(raw)
    )


def normalise_account_number(raw: str) -> str:
    """Digits only, leading zeros removed — the comparison key.

    Grouping varies by layout ("11 222 333 4" vs "447556667"), so it must not
    decide identity. Returns "" for a value with no digits, which never matches.

    Stripping leading zeros is defensive rather than observed: no measured header
    varies its padding. It is kept because the two directions are not symmetric —
    stripping can only make two numbers *more* likely to be equal, and an equal
    pair lands in ``ambiguous`` (manual); not stripping can make a statement fail
    to match its own account, which offers to create a duplicate.

    Every decimal digit becomes its ASCII value first. A regex non-digit filter
    alone kept fullwidth and Arabic-Indic digits as they were, so their zeros
    were never stripped and the key never equalled its ASCII twin (FIBR-0250).
    """
    return "".join(str(int(ch)) for ch in raw if ch.isdecimal()).lstrip("0")


@dataclass(frozen=True)
class AccountMatch:
    """Why the wizard selected (or did not select) an account."""

    account_id: int | None  # None unless exactly one candidate matched
    outcome: Literal["matched", "no_number", "no_match", "ambiguous", "wrong_bank"]
    normalised: str  # the MATCH KEY only ("" when no_number). No prefill reads
    # this — creation prefills from hint.number, as printed.
    # The ids left after the bank rule; for wrong_bank, the ids it dropped.
    # len != 1 => no select.
    candidates: tuple[int, ...]


def _at_another_bank(account: Account, bank: str | None) -> bool:
    """Is this account recorded at a bank other than the statement's? (FIBR-0284)

    A bank missing or blank on EITHER side is unknown, never different: an
    account recorded before FIBR-0283 has none, and must keep matching. Banks
    are free text, so they compare folded — "standard  BANK" is Standard Bank.
    """
    statement_bank = fold_name(bank or "")
    account_bank = fold_name(account.bank or "")
    return bool(statement_bank and account_bank) and statement_bank != account_bank


def _at_the_same_bank(account: Account, bank: str | None) -> bool:
    """Is this account recorded at the statement's own bank, folded? (FIBR-0284)"""
    statement_bank = fold_name(bank or "")
    return bool(statement_bank) and fold_name(account.bank or "") == statement_bank


def match_account(
    hint: SourceAccountHint | None, accounts: Sequence[Account]
) -> AccountMatch:
    """Which configured account this statement belongs to, if exactly one does.

    Both sides are normalised at comparison time, so a user who typed
    ``11 222 333 4``, ``112223334`` or ``0112223334`` when creating the account
    gets the same result whatever the statement prints.
    """
    if hint is None:
        return AccountMatch(None, "no_number", "", ())

    if _is_masked(hint.number):
        return AccountMatch(None, "no_number", "", ())

    key = normalise_account_number(hint.number)
    if not key:
        return AccountMatch(None, "no_number", "", ())

    # An account with no stored number matches nothing — otherwise "" == "" files
    # every statement under every unnumbered account.
    numbered = [
        account
        for account in accounts
        if account.account_number
        # A STORED number can be masked too — nothing stops the user typing the
        # PAN spelling a card statement prints ("1234 **** **** 5678"), and
        # normalisation would reduce it to "12345678", which a full statement
        # number can then equal by coincidence. The guard has to be symmetric or
        # it only closes the half the statement controls.
        and not _is_masked(account.account_number)
        and normalise_account_number(account.account_number) == key
    ]
    if not numbered:
        return AccountMatch(None, "no_match", key, ())

    # Another bank's account on the same number is a collision, not a match. Only
    # a contradiction drops a candidate: one at the statement's bank does not
    # outrank one with no bank recorded, since either may be the statement's.
    candidates = tuple(
        account.id for account in numbered if not _at_another_bank(account, hint.bank)
    )
    if not candidates:
        dropped = tuple(account.id for account in numbered)
        return AccountMatch(None, "wrong_bank", key, dropped)
    if len(candidates) == 1:
        (sole,) = (account for account in numbered if account.id == candidates[0])
        # A drop means the number is shared across banks. A survivor with no bank
        # recorded is then a guess: the dropped account may be the real one, its
        # bank merely spelt another way ("SBSA"). Only the statement's own bank
        # turns a drop into a match.
        if len(candidates) == len(numbered) or _at_the_same_bank(sole, hint.bank):
            return AccountMatch(candidates[0], "matched", key, candidates)
    return AccountMatch(None, "ambiguous", key, candidates)
