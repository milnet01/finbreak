"""Shared importer value objects (FIBR-0008 D12).

``ParseResult`` and ``RowError`` are the uniform output every importer produces —
design.md's ``parse(source) -> ParseResult`` interface. They live here (not in
``csv_importer``) so ``csv_importer`` and ``ofx_importer`` — and the
``ImportService`` that consumes either — share the exact same types with no
importer depending on another. ``csv_importer`` re-exports them, so its public
surface is unchanged (INV-9).
"""

from __future__ import annotations

from dataclasses import dataclass

from finbreak.models import TransactionDraft


@dataclass
class RowError:
    """A per-row parse failure, surfaced (never raised) so valid rows still
    import and every failure shows in the preview (INV-4/INV-3). ``row_number``
    is the 1-based source row, so the preview can flag it in file order."""

    row_number: int
    reason: str


@dataclass
class ParseResult:
    """An importer's output: valid ``drafts`` + collected ``errors`` (both carry
    their ``row_number`` for file-order interleaving) + the coverage span
    (``None``/``None`` when a CSV has zero drafts; the embedded DTSTART/DTEND for
    OFX, D4). Fills design.md's uniform ``parse(source) -> ParseResult`` importer
    interface (CSV and OFX both produce this type)."""

    drafts: list[TransactionDraft]
    errors: list[RowError]
    period_start: str | None
    period_end: str | None
