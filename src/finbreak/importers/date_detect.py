"""Pure date-format detector for the import wizard (FIBR-0146).

Given a column of raw date strings lifted off a statement (CSV cells, or a PDF
serialised to CSV text — FIBR-0009 D1), guess the ``strptime`` format the
importer should use. **Pure**: no Qt, no vault, no clock — it reads only its
``samples`` argument and the fixed module constant ``KNOWN_DATE_FORMATS``, so
the same input always yields the same guess (INV-2). It never mutates locale;
the ``%b``/``%B`` named-month entries read the ambient ``LC_TIME`` when matching,
so a month-name in another language is a parse *failure*, never a wrong month.

The guess is best-effort **pre-selection** only — the wizard always shows the
picker and a live preview (INV-1), so a wrong guess is visible before import.
2-digit and 4-digit year layouts are separated by ``strptime`` itself (``%Y``
matches exactly four digits, ``%y`` exactly two), so there is no year-window
guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

__all__ = ["KNOWN_DATE_FORMATS", "DateFormatGuess", "detect_date_format"]

# Ordered (D2): ISO first, then day-first, then month-first, then named-month,
# then the 2-digit-year slash variants. The order is the ambiguity tiebreak
# (INV-2). Each entry is (example rendering of the fixed reference date
# 2026-07-20, strptime pattern) — day 20, month 07 so day-first ("20/07/2026")
# and month-first ("07/20/2026") are visually distinct in the picker.
KNOWN_DATE_FORMATS: list[tuple[str, str]] = [
    ("2026-07-20", "%Y-%m-%d"),
    ("2026/07/20", "%Y/%m/%d"),
    ("20/07/2026", "%d/%m/%Y"),
    ("20-07-2026", "%d-%m-%Y"),
    ("20.07.2026", "%d.%m.%Y"),
    ("07/20/2026", "%m/%d/%Y"),
    ("07-20-2026", "%m-%d-%Y"),
    ("07.20.2026", "%m.%d.%Y"),
    ("20 Jul 2026", "%d %b %Y"),
    ("20 July 2026", "%d %B %Y"),
    ("20-Jul-2026", "%d-%b-%Y"),
    ("Jul 20, 2026", "%b %d, %Y"),
    ("July 20, 2026", "%B %d, %Y"),
    ("20/07/26", "%d/%m/%y"),
    ("07/20/26", "%m/%d/%y"),
]


@dataclass(frozen=True)
class DateFormatGuess:
    fmt: str | None  # best-guess strptime pattern, or None if nothing parsed any sample
    ambiguous: bool  # >=2 formats tie for the max parse-count (> 0)


def detect_date_format(samples: Sequence[str]) -> DateFormatGuess:
    """Pure best-effort guess of the ``strptime`` format for a column of date
    strings. ``samples`` is a ``Sequence`` (NOT a one-shot iterable): the scan is
    format-outer — each candidate re-scans all samples — so a generator would
    exhaust after the first format and corrupt the count. A sample counts for a
    format iff ``strptime`` succeeds (no year window, no clock). ``fmt`` is the
    highest parse-count format; ties break by ``KNOWN_DATE_FORMATS`` order
    (INV-2); ``None`` if nothing parses any sample. Deterministic."""
    cleaned = [s.strip() for s in samples]
    cleaned = [s for s in cleaned if s]
    if not cleaned:
        return DateFormatGuess(None, False)

    best_fmt: str | None = None
    best_count = 0
    tie = False
    for _example, fmt in KNOWN_DATE_FORMATS:
        count = 0
        for sample in cleaned:
            try:
                datetime.strptime(sample, fmt)
            except ValueError:
                continue
            count += 1
        if count == 0:
            continue
        if count > best_count:
            best_fmt, best_count, tie = fmt, count, False
        elif count == best_count:
            tie = True

    if best_fmt is None:
        return DateFormatGuess(None, False)
    return DateFormatGuess(best_fmt, tie)
