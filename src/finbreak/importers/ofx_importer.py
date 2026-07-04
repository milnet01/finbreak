"""OfxImporter — a **pure** OFX parser (no DB, no Qt) for FIBR-0008.

Turns already-read OFX **bytes** + the currency exponent into one
``ParseResult`` per statement (``ofx.accounts``), reusing ``parse_transaction``
per transaction so an OFX amount obeys the identical money contract as a CSV or
hand-typed one (coding.md § 1.3). OFX is self-describing: the amount sign, the
date, the description, and the coverage period all come from the format, so —
unlike CSV — there is no ``ColumnMapping``.

Two error regimes, per the spec's D15 split:

- **Structural malformation** (a bad ``<DTPOSTED>`` or empty ``<TRNAMT>``, an
  empty/HTML/garbage file, or a statement-less envelope) → ``ofxparse`` aborts
  the whole statement / parse. The single boundary catch (D7) re-raises a
  friendly ``ValueError`` (INV-4); ``ofxparse`` offers no per-transaction skip.
- **Post-parse validation** (a transaction ``ofxparse`` parsed but
  ``parse_transaction`` rejects — zero / over-precise amount, or a blank
  description when both ``<NAME>`` and ``<MEMO>`` are absent) → a collected
  ``RowError``, and the sibling rows still import (INV-3).

Untrusted input, so bounded: the whole-file transaction count is capped
(``_MAX_OFX_TRANSACTIONS``, D13/INV-10). The file-size cap lives on the read
path (``ImportService.read_file_bytes``).
"""

from __future__ import annotations

import io

from ofxparse import OfxParser

from finbreak.importers.base import ParseResult, RowError
from finbreak.models import OfxAccountInfo, TransactionDraft
from finbreak.services.transactions import parse_transaction

# Whole-file transaction cap (D13/INV-10) — orders of magnitude above any real
# personal statement. One-line-tunable; the byte cap is _MAX_IMPORT_BYTES (import_).
_MAX_OFX_TRANSACTIONS = 100_000


class OfxImporter:
    def parse(
        self, data: bytes, exponent: int
    ) -> list[tuple[OfxAccountInfo, ParseResult]]:
        """Parse OFX ``data`` into one ``(OfxAccountInfo, ParseResult)`` per
        statement. Raises a friendly ``ValueError`` on any structurally-unusable
        input (INV-4/D15)."""
        # The untrusted-file boundary (D7): ofxparse raises an inconsistent
        # variety (OfxParserException, a bare ValueError, ...) on bad input, so
        # one broad catch maps them all to a friendly message. The original is
        # chained (not swallowed — global rule § 1).
        try:
            ofx = OfxParser.parse(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001 — documented untrusted-input boundary (D7)
            raise ValueError("this file could not be read as OFX") from exc

        # A structurally-valid but statement-less envelope (empty ofx.accounts —
        # e.g. sign-on only) is not an ofxparse exception; guard it explicitly,
        # AFTER the boundary catch so its distinct message isn't collapsed (INV-4).
        accounts = ofx.accounts
        if not accounts:
            raise ValueError("no statements were found in this OFX file")

        # Whole-file transaction-count cap (D13/INV-10) — after the boundary
        # catch, since it needs the parsed accounts to total the count.
        total = sum(len(account.statement.transactions) for account in accounts)
        if total > _MAX_OFX_TRANSACTIONS:
            raise ValueError(
                f"this OFX file has more than {_MAX_OFX_TRANSACTIONS} transactions"
            )

        return [
            (
                OfxAccountInfo(account.account_id or "", account.account_type or ""),
                self._parse_statement(account.statement, exponent),
            )
            for account in accounts
        ]

    @staticmethod
    def _parse_statement(statement, exponent: int) -> ParseResult:
        drafts: list[TransactionDraft] = []
        errors: list[RowError] = []
        # 1-based over this statement's transactions in file order (INV-3).
        for row_number, tx in enumerate(statement.transactions, start=1):
            # Description is payee, falling back to memo (D5); both empty (both
            # tags absent) -> parse_transaction rejects the blank description.
            description = (tx.payee or "").strip() or (tx.memo or "").strip()
            occurred_on = tx.date.date().isoformat()
            try:
                occurred_on, amount_minor, description = parse_transaction(
                    occurred_on, tx.amount, description, exponent
                )
            except ValueError as exc:
                errors.append(RowError(row_number, str(exc)))
                continue
            drafts.append(
                TransactionDraft(row_number, occurred_on, amount_minor, description)
            )

        period_start, period_end = _embedded_span(statement, drafts)
        return ParseResult(drafts, errors, period_start, period_end)


def _embedded_span(
    statement, drafts: list[TransactionDraft]
) -> tuple[str | None, str | None]:
    """The authoritative coverage span (D4): the embedded DTSTART/DTEND. ofxparse
    0.21 sets ``start_date``/``end_date`` to the empty string ``''`` (not
    ``None``) when the span is absent, so "missing" is detected by **falsiness**
    on **both** endpoints (never ``is None``, or ``''.date()`` would raise and the
    boundary catch would turn a valid statement into a total failure). A missing
    span falls back to the drafts' min/max (the CSV rule), or ``None`` when there
    are zero drafts."""
    start, end = statement.start_date, statement.end_date
    if not start or not end:
        dates = [d.occurred_on for d in drafts]
        return (min(dates), max(dates)) if dates else (None, None)
    return start.date().isoformat(), end.date().isoformat()
