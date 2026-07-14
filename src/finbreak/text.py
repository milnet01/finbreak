"""Shared text-matching normaliser (FIBR-0010 D2).

``normalise_text`` collapses runs of whitespace to single spaces and casefolds —
the one primitive both the import dedup (``ImportService._normalise``) and the
rule matcher (``services.categorization.categorize``) compare against, so a rule
pattern matches a description the same way the importer dedups it. Extracted here
(coding.md § 1.3, reuse-before-rewrite) once the concept reached a second
call-site; a tiny pure function, no vault, trivially testable.
"""

from __future__ import annotations

import re
import string

# Leading noise prefixes stripped from a bank description before the shop name
# (FIBR-0138 D3). Ordered **longest-first** so an overlapping future prefix stays
# deterministic; ``DEBIT ORDER`` matches as a two-word phrase. Matched as a whole
# word/phrase at the start (case-insensitive), repeated while any remains — so
# ``POS CARD WOOLWORTHS`` sheds both. A word merely *starting* with a prefix
# (``CARDIFF``) is left alone (the trailing ``\b`` word boundary).
_NOISE_PREFIXES = (
    "DEBIT ORDER",
    "PURCHASE",
    "PAYMENT",
    "CARD",
    "PMT",
    "POS",
    "EFT",
    "DR",
)


def normalise_text(text: str) -> str:
    """Fold whitespace to single spaces, then casefold."""
    return " ".join(text.split()).casefold()


def merchant_name(description: str) -> str:
    """A best-guess shop name from a free-text bank ``description`` (FIBR-0138 D3).

    Pure and **total** — never raises for any ``str``. Fuzzy by design and refined
    per release (like the category library); because the drill sums the real stored
    amounts (INV-1), a mis-grouped shop is only cosmetic. Steps: strip; shed leading
    noise prefixes; drop digit-heavy reference tokens (a run of ≥ 3 digits, or a
    majority-digit token); strip edge punctuation; title-case, else fall back to the
    trimmed raw text (never a blank label — a stored description is non-empty). The
    grouping key callers compare is ``normalise_text(merchant_name(desc))``.
    """
    stripped = description.strip()
    if not stripped:
        return ""
    working = stripped
    shed = True
    while shed:
        shed = False
        for prefix in _NOISE_PREFIXES:
            match = re.match(re.escape(prefix) + r"\b\s*", working, re.IGNORECASE)
            if match and match.end() > 0:
                working = working[match.end() :]
                shed = True
                break
    tokens: list[str] = []
    for token in working.split():
        if re.search(r"\d{3,}", token):  # a ref/card/date fragment
            continue
        if sum(ch.isdigit() for ch in token) * 2 > len(token):  # majority digits
            continue
        token = token.strip(string.punctuation)
        if token:
            tokens.append(token)
    cleaned = " ".join(tokens)
    return cleaned.title() if cleaned else stripped
