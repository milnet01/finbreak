"""CsvImporter — a **pure** CSV parser (no DB, no Qt) for FIBR-0007.

Turns already-decoded ``text`` + a ``ColumnMapping`` + the currency exponent
into a ``ParseResult`` — the transaction drafts, the per-row errors, and the
min/max date span. Reuses ``parse_transaction`` per row (coding.md § 1.3), so a
CSV-imported amount obeys the identical money contract as a manually-typed one.

Per-row failures are **collected** ``RowError`` values, never raised, so one bad
row never aborts a whole import (INV-4). The importer's own ``Decimal(cell)``
raises ``decimal.InvalidOperation`` (an ``ArithmeticError``, not a
``ValueError``) on a non-numeric cell, so the per-row body catches **both**.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from finbreak.importers.base import ParseResult, RowError
from finbreak.models import ColumnMapping, TransactionDraft
from finbreak.services.transactions import parse_transaction

# ``ParseResult`` / ``RowError`` moved to ``importers/base`` (FIBR-0008 D12) and
# are re-exported here so existing ``from finbreak.importers.csv_importer import
# ParseResult`` call-sites keep working unchanged (INV-9).
__all__ = ["CsvImporter", "ParseResult", "RowError", "read_header"]


def read_header(text: str) -> list[str]:
    """The CSV header fieldnames (for the signature + the mapping UI). Raises
    ``ValueError`` on an **empty** file (no header line — ``DictReader.fieldnames``
    is ``None``); a genuinely headerless file *with* data is indistinguishable
    and out of scope (D11)."""
    fieldnames = csv.DictReader(io.StringIO(text)).fieldnames
    if fieldnames is None:
        raise ValueError("the file has no header row")
    return list(fieldnames)


class CsvImporter:
    def parse(self, text: str, mapping: ColumnMapping, exponent: int) -> ParseResult:
        """Parse ``text`` under ``mapping`` into drafts + row errors + the date
        span. Assumes a mapping the service has already validated (exactly one
        amount style; every mapped column present in the header, D5)."""
        single = mapping.amount_column is not None
        style_cols = (
            [mapping.amount_column]
            if single
            else [mapping.debit_column, mapping.credit_column]
        )
        # The mapped columns whose cells must be present per row (the ragged-row
        # guard). The unused amount-style columns are None; drop them.
        needed = [mapping.date_column, mapping.description_column]
        needed += [col for col in style_cols if col is not None]

        drafts: list[TransactionDraft] = []
        errors: list[RowError] = []
        reader = csv.DictReader(io.StringIO(text))
        # enumerate over the data rows DictReader yields: 1-based, and blank lines
        # (which DictReader skips) never consume a number (INV-4).
        for row_number, row in enumerate(reader, start=1):
            # Ragged-row guard: a short row pads missing mapped cells with None;
            # Decimal(None)/None.strip() raise TypeError/AttributeError (outside
            # the catch below), so turn it into a RowError up-front (D5).
            if any(row.get(col) is None for col in needed):
                errors.append(
                    RowError(row_number, "row has fewer columns than the header")
                )
                continue
            # The date parse gets its own try so a strptime failure surfaces a
            # FRIENDLY RowError naming the offending value (INV-3), never the raw
            # "time data '…' does not match format '…'" text. The amount /
            # parse_transaction failures below keep their existing human messages
            # (D3), so only the date branch is re-worded.
            raw_date = row[mapping.date_column].strip()
            try:
                occurred_on = (
                    datetime.strptime(raw_date, mapping.date_format).date().isoformat()
                )
            except ValueError:
                reason = (
                    "the date cell is empty"
                    if raw_date == ""
                    else f'could not read the date "{raw_date}"'
                )
                errors.append(RowError(row_number, reason))
                continue
            try:
                amount = (
                    self._single_amount(row, mapping)
                    if single
                    else self._debit_credit_amount(row, mapping)
                )
                occurred_on, amount_minor, description = parse_transaction(
                    occurred_on, amount, row[mapping.description_column], exponent
                )
            except (ValueError, InvalidOperation) as exc:
                errors.append(RowError(row_number, str(exc)))
                continue
            drafts.append(
                TransactionDraft(row_number, occurred_on, amount_minor, description)
            )

        dates = [d.occurred_on for d in drafts]
        period_start = min(dates) if dates else None
        period_end = max(dates) if dates else None
        return ParseResult(drafts, errors, period_start, period_end)

    @staticmethod
    def _single_amount(row: dict, mapping: ColumnMapping) -> Decimal:
        amount = Decimal(row[mapping.amount_column].strip())
        return -amount if mapping.invert_amount else amount

    @staticmethod
    def _debit_credit_amount(row: dict, mapping: ColumnMapping) -> Decimal:
        """Debit → money **out** (negative), credit → money **in** (positive);
        exactly one populated. The cells are **unsigned magnitudes**, so a
        negative value is a mis-mapping to surface, not a sign to reinterpret
        (ADR-0005 no-silent-mis-map) — a ``ValueError`` → a RowError (D5)."""
        debit = row[mapping.debit_column].strip()
        credit = row[mapping.credit_column].strip()
        if bool(debit) == bool(credit):
            raise ValueError("exactly one of debit / credit must be populated")
        magnitude = Decimal(debit or credit)
        if magnitude < 0:
            raise ValueError("a debit/credit amount must be an unsigned magnitude")
        return -magnitude if debit else magnitude
