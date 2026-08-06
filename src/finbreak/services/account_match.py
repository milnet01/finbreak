"""Match a statement's printed account number to a configured account (FIBR-0086).

Pure functions over value objects — no vault, no Qt, no I/O. The wizard calls
``match_account`` once per parsed statement and uses the outcome to decide whether
to change its destination pre-selection.

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

# A masked identifier — a statement showing only a tail (``xxxx1234``,
# ``1234 **** **** 5678``). Matching on a masked tail is deliberately not built
# (FIBR-0086 §3 decision 3); this is what enforces that, because normalisation
# strips non-digits and would otherwise turn "xxxx1234" into a clean "1234" that
# matches a real account numbered 1234.
_MASK_CHARS = frozenset("*xX")


def normalise_account_number(raw: str) -> str:
    """Digits only, leading zeros removed — the comparison key.

    Grouping varies by layout ("11 222 333 4" vs "447556667"), so it must not
    decide identity. Returns "" for a value with no digits, which never matches.

    Stripping leading zeros is defensive rather than observed: no measured header
    varies its padding. It is kept because the two directions are not symmetric —
    stripping can only make two numbers *more* likely to be equal, and an equal
    pair lands in ``ambiguous`` (manual); not stripping can make a statement fail
    to match its own account, which offers to create a duplicate.
    """
    return re.sub(r"\D", "", raw).lstrip("0")


@dataclass(frozen=True)
class AccountMatch:
    """Why the wizard selected (or did not select) an account."""

    account_id: int | None  # None unless exactly one candidate matched
    outcome: Literal["matched", "no_number", "no_match", "ambiguous"]
    normalised: str  # the MATCH KEY only ("" when no_number). No prefill reads
    # this — creation prefills from hint.number, as printed.
    candidates: tuple[int, ...]  # every id that matched; len != 1 => no select


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

    # Before normalisation, deliberately: normalisation destroys the evidence.
    if any(ch in _MASK_CHARS for ch in hint.number):
        return AccountMatch(None, "no_number", "", ())

    key = normalise_account_number(hint.number)
    if not key:
        return AccountMatch(None, "no_number", "", ())

    # An account with no stored number matches nothing — otherwise "" == "" files
    # every statement under every unnumbered account.
    candidates = tuple(
        account.id
        for account in accounts
        if account.account_number
        and normalise_account_number(account.account_number) == key
    )

    if len(candidates) == 1:
        return AccountMatch(candidates[0], "matched", key, candidates)
    if not candidates:
        return AccountMatch(None, "no_match", key, candidates)
    return AccountMatch(None, "ambiguous", key, candidates)
