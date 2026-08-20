"""Pure column-role guesser for the import wizard (FIBR-0297).

Given a statement's header row (CSV cells, or a PDF table serialised to CSV
text — FIBR-0009 D1), guess which column fills which role, so the map step
arrives pre-filled instead of leaving all five dropdowns on the first column.
**Pure**: no Qt, no vault, no clock — it reads only its ``header`` argument and
the fixed module constant ``ROLE_SPELLINGS``, so the same input always yields
the same guess.

The guess is best-effort **pre-selection** only — the wizard always shows every
dropdown and the user can override any of them before importing, exactly as the
sibling date-format detector's guess is confirmed through a live preview. A
header this module does not recognise leaves that role unset, so the wizard's
long-standing first-column default remains the fallback and nothing regresses.

Matching is exact on a normalised name: case-folded with every non-alphanumeric
character dropped, so ``DATE``, ``Date:`` and ``Amount ($)`` match while
unrelated prose does not. Substring matching is deliberately not used — it
would let "Date" match a "Last Updated" column, and a confident wrong guess is
worse than the plain default it replaces.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["ROLE_SPELLINGS", "ColumnGuess", "guess_columns"]

# The conventional spellings per role, already normalised (FIBR-0297 INV-3).
# Ordered within each role: the canonical spelling first, so a header carrying
# both "Date" and "Transaction Date" fills the role from the plainer one. Roles
# are matched in key order and a header fills at most one role, so an earlier
# role never has its column stolen by a later one.
ROLE_SPELLINGS: dict[str, tuple[str, ...]] = {
    "date": ("date", "transactiondate", "postingdate"),
    "description": ("description", "details", "narrative", "reference"),
    "amount": ("amount", "value"),
    "debit": ("debit", "withdrawal"),
    "credit": ("credit", "deposit"),
}


@dataclass(frozen=True)
class ColumnGuess:
    """One guessed column per role, as the **original** header string so the
    wizard can select it in a combo populated from that same list. ``None`` is
    "no recognisable header for this role" — never a fallback pick."""

    date: str | None = None
    description: str | None = None
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None


def _normalise(name: str) -> str:
    """Case- and punctuation-insensitive key for one header cell (INV-2)."""
    return "".join(char for char in name.casefold() if char.isalnum())


def guess_columns(header: Sequence[str]) -> ColumnGuess:
    """Guess a column per role from ``header``'s own words.

    Returns the original header strings, never normalised copies. A role with
    no conventional spelling in ``header`` comes back ``None`` (INV-5), and a
    single header column is claimed by at most one role.
    """
    normalised = [_normalise(name) for name in header]
    claimed: set[int] = set()
    found: dict[str, str] = {}
    for role, spellings in ROLE_SPELLINGS.items():
        for spelling in spellings:
            for index, candidate in enumerate(normalised):
                if candidate != spelling or index in claimed:
                    continue
                found[role] = header[index]
                claimed.add(index)
                break
            if role in found:
                break
    return ColumnGuess(**found)
