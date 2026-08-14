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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

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
    # >=2 formats tie for the max parse-count (> 0) AND read some row to a
    # different date. A tie that reads identically (May's %b/%B) is not
    # ambiguous to the user and does not set this (FIBR-0264).
    ambiguous: bool


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
    best_dates: dict[int, datetime] = {}
    tie = False
    for _example, fmt in KNOWN_DATE_FORMATS:
        dates: dict[int, datetime] = {}
        for index, sample in enumerate(cleaned):
            try:
                dates[index] = datetime.strptime(sample, fmt)
            except ValueError:
                continue
        count = len(dates)
        if count == 0:
            continue
        if count > best_count:
            best_fmt, best_count, best_dates, tie = fmt, count, dates, False
        elif count == best_count and _reads_differently(best_dates, dates):
            tie = True

    if best_fmt is None:
        return DateFormatGuess(None, False)
    return DateFormatGuess(best_fmt, tie)


def _reads_differently(best: dict[int, datetime], other: dict[int, datetime]) -> bool:
    """True if two tied candidates disagree about what date some row is.

    A tie on parse-count is not by itself something to warn about (FIBR-0264).
    English spells the abbreviated and full month name identically for May, so
    ``%d %b %Y`` and ``%d %B %Y`` both parse every row of a May statement and
    tie — but they read every row to the *same* date, so the D6 nudge ("the day
    and month might be the other way around") describes a problem that is not
    there. A monthly statement is normal input, not a corner case.

    Only a tie whose candidates produce a *different* date is ambiguous to the
    user, and over one column of numeric dates the only way that happens is a
    day/month transposition — which is exactly what the nudge says. Compared on
    the rows both parsed; a disjoint pair agrees about nothing and is left
    un-flagged, since it cannot be shown to disagree.
    """
    return any(other[i] != date for i, date in best.items() if i in other)
