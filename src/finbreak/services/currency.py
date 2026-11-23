"""Each account's currency, and the rule that no figure mixes currencies
(FIBR-0087, docs/specs/FIBR-0087-per-account-currency.md § 4.3).

Qt-free, so every rule here is testable headless.
"""

from __future__ import annotations

from sqlcipher3 import dbapi2

from finbreak.models import Account
from finbreak.services.transactions import (
    read_base_currency,
    read_minor_unit_exponent,
)


def account_currency(account: Account, base: str) -> str:
    """``account.currency``, or ``base`` when it is NULL or blank.

    Nothing in the app writes NULL; this covers a value written outside it and
    a hand-built ``Account`` in a test."""
    return (account.currency or "").strip() or base


def account_currency_choices(conn: dbapi2.Connection) -> list[str]:
    """The codes an account may take: those whose exponent equals the vault's
    ``minor_unit_exponent``, base first, then code order.

    Amounts are stored at the vault's one exponent, so a code with another
    would be stored at the wrong scale."""
    # Imported here, not at module level: services.auth imports
    # services.reporting, which imports this module.
    from finbreak.services.auth import CURRENCY_EXPONENTS

    exponent = read_minor_unit_exponent(conn)
    base = read_base_currency(conn)
    codes = sorted(c for c, e in CURRENCY_EXPONENTS.items() if e == exponent)
    return [c for c in codes if c == base] + [c for c in codes if c != base]
