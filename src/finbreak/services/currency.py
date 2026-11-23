"""Each account's currency, and the rule that no figure mixes currencies
(FIBR-0087, docs/specs/FIBR-0087-per-account-currency.md § 4.3).

Qt-free, so every rule here is testable headless.
"""

from __future__ import annotations

from sqlcipher3 import dbapi2

from finbreak.errors import QT_TRANSLATE_NOOP, MixedCurrencyError, UserMessage
from finbreak.models import Account
from finbreak.repositories.accounts import AccountRepository
from finbreak.services.transactions import (
    read_base_currency,
    read_minor_unit_exponent,
)


def account_currency(account: Account, base: str) -> str:
    """``account.currency``, or ``base`` when it is NULL or blank.

    Nothing in the app writes NULL; this covers a value written outside it and
    a hand-built ``Account`` in a test."""
    return (account.currency or "").strip() or base


def account_currencies(conn: dbapi2.Connection) -> dict[int, str]:
    """Every account id -> its currency, read through ``account_currency``."""
    base = read_base_currency(conn)
    return {
        account.id: account_currency(account, base)
        for account in AccountRepository(conn).list_all()
    }


def vault_currencies(conn: dbapi2.Connection) -> list[str]:
    """Each currency an account holds, once: the base currency first if any
    account holds it, then the rest in code order."""
    held = set(account_currencies(conn).values())
    base = read_base_currency(conn)
    return [c for c in [base] if c in held] + sorted(held - {base})


def accounts_in(conn: dbapi2.Connection, currency: str) -> frozenset[int]:
    """The ids of the accounts in ``currency``."""
    return frozenset(i for i, c in account_currencies(conn).items() if c == currency)


def scope_currency(conn: dbapi2.Connection, account_ids: frozenset[int] | None) -> str:
    """The one currency of the scope; ``None`` means every account.

    An empty scope, or ``None`` in a vault with no accounts, is the base
    currency. Two or more currencies raise ``MixedCurrencyError``: every
    service that adds amounts across accounts calls this before reading rows,
    so a screen that forgets to scope gets a refusal, not a wrong total."""
    by_id = account_currencies(conn)
    if account_ids is not None:
        by_id = {i: c for i, c in by_id.items() if i in account_ids}
    held = set(by_id.values())
    if len(held) > 1:
        raise MixedCurrencyError(
            UserMessage(
                QT_TRANSLATE_NOOP("Refusal", "choose accounts that share one currency")
            )
        )
    return held.pop() if held else read_base_currency(conn)


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
