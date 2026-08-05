"""TransactionService — money validation + scaling around the repository.

Money is stored as an exact integer number of minor units, never a binary
float (FIBR-0004 D1). ``parse_transaction`` is the single form-boundary
validator (raises ``ValueError``); ``to_display_decimal`` inverts the scaling
for display. The base currency's minor-unit exponent is read from ``settings``,
so the scale lives in one place.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, Overflow
from typing import cast

from sqlcipher3 import dbapi2

from finbreak.models import Transaction
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.settings import SettingsRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.vault import Vault

# The largest magnitude an amount can hold, in minor units: SQLite's INTEGER is a
# signed 64-bit value, so anything past this raises OverflowError at the INSERT —
# a class no caller catches, unlike the ValueError every other rejection here
# raises (FIBR-0216).
_MAX_AMOUNT_MINOR = 2**63 - 1


def read_minor_unit_exponent(conn: dbapi2.Connection) -> int:
    """The base currency's minor-unit exponent, from ``settings`` — the single
    source both ``TransactionService`` and ``ImportService`` (FIBR-0007) read,
    so the key string and its cast live in one place (a typo would silently
    read the wrong money scale)."""
    # Route through the SettingsRepository seam (FIBR-0080) so the key string
    # isn't hand-rolled in a second place. The value is a v1 invariant (written
    # at first-run), so ``cast`` mirrors the repo convention of asserting presence
    # over a can't-happen error path (coding.md § 2).
    value = SettingsRepository(conn).get("minor_unit_exponent")
    return int(cast(str, value))


def parse_transaction(
    occurred_on: str, raw_amount: str | Decimal, description: str, exponent: int
) -> tuple[str, int, str]:
    """Validate one transaction's fields → ``(occurred_on, amount_minor, description)``.

    Raises ``ValueError`` when the description is blank, the date is not ISO-8601,
    or the amount is non-numeric, non-finite, zero, past what SQLite's 64-bit
    INTEGER can hold, or has more fractional digits than the currency allows
    (rounding money would silently mutate it — INV-4b).

    ``ValueError`` for **every** rejection is the contract, not an accident: it is
    what `ManualEntryDialog` and `csv_importer` each catch and render (FIBR-0216).
    """
    description = description.strip()
    if not description:
        raise ValueError("description must not be empty")
    try:
        # CANONICALISED, not merely validated (FIBR-0216). `date.fromisoformat`
        # accepts more spellings of the same day than it looks like — "20260715" and
        # the ISO week form "2026-W29-3" both parse — and everything downstream
        # compares occurred_on as a STRING, so storing the input verbatim would make
        # two spellings of one date sort and group apart. Latent today (every caller
        # arrives via strptime().isoformat() or a QDateEdit), which is exactly when
        # it is cheapest to close.
        occurred_on = date.fromisoformat(occurred_on).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("occurred_on must be a valid ISO-8601 date") from exc

    try:
        amount = (
            raw_amount
            if isinstance(raw_amount, Decimal)
            else Decimal(str(raw_amount).strip())
        )
    except InvalidOperation as exc:
        raise ValueError("amount is not a valid number") from exc
    if not amount.is_finite():
        raise ValueError("amount must be a finite decimal")
    # Count SIGNIFICANT fractional digits: normalize() strips trailing zeros, so
    # "12.340" (== 12.34) is accepted while "12.345" is still rejected. is_finite()
    # above guarantees the exponent is an int (never 'n'/'N'/'F'); normalize() can
    # yield a positive exponent for whole numbers (1E+2), which the sign handles.
    if -cast(int, amount.normalize().as_tuple().exponent) > exponent:
        raise ValueError("amount has more fractional digits than the currency allows")

    amount_minor = to_minor_storable(amount, exponent)
    if amount_minor == 0:
        raise ValueError("amount must be non-zero")
    return occurred_on, amount_minor, description


def to_display_decimal(amount_minor: int, exponent: int) -> Decimal:
    """Reconstruct the display amount from stored minor units (no float)."""
    return Decimal(amount_minor).scaleb(-exponent)


def to_minor(amount: Decimal, exponent: int) -> int:
    """Scale a display ``Decimal`` to stored minor units — the exact inverse of
    ``to_display_decimal`` and the ONE forward conversion in the codebase
    (FIBR-0181; it replaced five hand-rolled copies).

    Sub-minor fractions round half-even (``Decimal.to_integral_value``'s default).
    ``parse_transaction`` rejects them upstream, but the other callers scale values
    that already round-tripped through ``to_display_decimal``, so the scaling is
    exact there."""
    return int(amount.scaleb(exponent).to_integral_value())


def to_minor_storable(amount: Decimal, exponent: int) -> int:
    """``to_minor``, plus the two magnitude rejections storing the result forces —
    both raised as ``ValueError``, the class every caller already catches.

    Scaling money is only half the job: an amount can be finite, correctly signed
    and correctly precise and still be unstorable, in two ways that surface as two
    *different* uncaught exception types, at two different distances from here.

    - Too large an **exponent** ("1e999999") overflows the Decimal context inside
      `scaleb` itself, raising `decimal.Overflow` right here (FIBR-0222).
    - Too large a **value** (1e30) scales cleanly and only fails later, at the
      INSERT, as `OverflowError` past SQLite's signed 64-bit INTEGER (FIBR-0216).

    Neither is a `ValueError`, so both walked through the `except ValueError` that
    `ManualEntryDialog`, `csv_importer` and the import wizard each render with, and
    killed the Qt slot silently. Same rejection, so deliberately the same message.

    The `Overflow` catch sits **after** the scaling rather than as a second
    magnitude bound before it, so `_MAX_AMOUNT_MINOR` stays the ONE stated bound
    and cannot drift from a duplicate expressed as an exponent. `Overflow` is
    caught narrowly rather than `DecimalException`: with a finite operand and a
    currency exponent of 0-3 it is the only trapped signal reachable there.
    """
    try:
        amount_minor = to_minor(amount, exponent)
    except Overflow as exc:
        raise ValueError("amount is too large to store") from exc
    if not -_MAX_AMOUNT_MINOR <= amount_minor <= _MAX_AMOUNT_MINOR:
        raise ValueError("amount is too large to store")
    return amount_minor


class TransactionService:
    def __init__(self, vault: Vault):
        self._vault = vault

    @property
    def vault(self) -> Vault:
        """The backing vault — lets a caller compose a sibling service over the same
        connection (e.g. the Transactions tab's TransferDetectionService, FIBR-0151)."""
        return self._vault

    def _exponent(self) -> int:
        return read_minor_unit_exponent(self._vault.connection)

    def base_currency(self) -> str:
        # Same SettingsRepository seam as read_minor_unit_exponent (FIBR-0080);
        # base_currency is a v1 invariant so ``cast`` asserts its presence.
        value = SettingsRepository(self._vault.connection).get("base_currency")
        return cast(str, value)

    def add_transaction(
        self,
        account_id: int,
        occurred_on: str,
        raw_amount: str | Decimal,
        description: str,
    ) -> None:
        occurred_on, amount_minor, description = parse_transaction(
            occurred_on, raw_amount, description, self._exponent()
        )
        TransactionRepository(self._vault.connection).add(
            account_id, occurred_on, amount_minor, description
        )

    def list_transactions(self) -> list[tuple[Transaction, Decimal, str, str]]:
        """Each row + its display amount + its account name + its category name
        (both id->name maps resolved once, not per row; FIBR-0010 D12). The
        category name is the leaf's name, or ``""`` for an uncategorised row."""
        exponent = self._exponent()
        conn = self._vault.connection
        account_names = {a.id: a.name for a in AccountRepository(conn).list_all()}
        category_names = {c.id: c.name for c in CategoryRepository(conn).list_all()}
        rows = TransactionRepository(conn).list_all()
        return [
            (
                row,
                to_display_decimal(row.amount_minor, exponent),
                account_names.get(row.account_id, ""),
                ""
                if row.category_id is None
                else category_names.get(row.category_id, ""),
            )
            for row in rows
        ]
