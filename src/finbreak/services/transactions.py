"""TransactionService — money validation + scaling around the repository.

Money is stored as an exact integer number of minor units, never a binary
float (FIBR-0004 D1). ``parse_transaction`` is the single form-boundary
validator (raises ``ValueError``); ``to_display_decimal`` inverts the scaling
for display. The base currency's minor-unit exponent is read from ``settings``,
so the scale lives in one place.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast

from finbreak.models import Transaction
from finbreak.repositories.transactions import TransactionRepository
from finbreak.vault import Vault


def parse_transaction(
    occurred_on: str, raw_amount: str | Decimal, description: str, exponent: int
) -> tuple[str, int, str]:
    """Validate one transaction's fields → ``(occurred_on, amount_minor, description)``.

    Raises ``ValueError`` when the description is blank, the date is not ISO-8601,
    or the amount is non-numeric, non-finite, zero, or has more fractional digits
    than the currency allows (rounding money would silently mutate it — INV-4b).
    """
    description = description.strip()
    if not description:
        raise ValueError("description must not be empty")
    try:
        date.fromisoformat(occurred_on)
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
    # is_finite() above guarantees the exponent is an int (never 'n'/'N'/'F').
    if -cast(int, amount.as_tuple().exponent) > exponent:
        raise ValueError("amount has more fractional digits than the currency allows")

    amount_minor = int(amount.scaleb(exponent).to_integral_value())
    if amount_minor == 0:
        raise ValueError("amount must be non-zero")
    return occurred_on, amount_minor, description


def to_display_decimal(amount_minor: int, exponent: int) -> Decimal:
    """Reconstruct the display amount from stored minor units (no float)."""
    return Decimal(amount_minor).scaleb(-exponent)


class TransactionService:
    def __init__(self, vault: Vault):
        self._vault = vault

    def _exponent(self) -> int:
        row = self._vault.connection.execute(
            "SELECT value FROM settings WHERE key = 'minor_unit_exponent'"
        ).fetchone()
        return int(row[0])

    def base_currency(self) -> str:
        row = self._vault.connection.execute(
            "SELECT value FROM settings WHERE key = 'base_currency'"
        ).fetchone()
        return str(row[0])

    def add_transaction(
        self, occurred_on: str, raw_amount: str | Decimal, description: str
    ) -> None:
        occurred_on, amount_minor, description = parse_transaction(
            occurred_on, raw_amount, description, self._exponent()
        )
        TransactionRepository(self._vault.connection).add(
            occurred_on, amount_minor, description
        )

    def list_transactions(self) -> list[tuple[Transaction, Decimal]]:
        exponent = self._exponent()
        rows = TransactionRepository(self._vault.connection).list_all()
        return [(row, to_display_decimal(row.amount_minor, exponent)) for row in rows]
