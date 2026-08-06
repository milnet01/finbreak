"""Shared text-matching normaliser (FIBR-0010 D2).

``normalise_text`` folds Unicode composition to NFC, collapses runs of whitespace
to single spaces, and casefolds — the one primitive both the import dedup
(``ImportService._normalise``) and the rule matcher
(``services.categorization.categorize``) compare against, so a rule
pattern matches a description the same way the importer dedups it. Extracted here
(coding.md § 1.3, reuse-before-rewrite) once the concept reached a second
call-site; a tiny pure function, no vault, trivially testable.
"""

from __future__ import annotations

import re
import string
import unicodedata

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
    """Fold Unicode composition to NFC, whitespace to single spaces, then casefold.

    The NFC step matters because this is the **import dedup key** as well as the
    rule matcher: "Café" spelled with U+00E9 and the same word spelled "e" +
    U+0301 are visually identical and casefold to *different* strings, so a
    statement period imported once from a PDF (pdfplumber emits whatever the
    font encoding produced, frequently decomposed) and again from the bank's CSV
    (composed) would not recognise its own rows and would double-count them.

    Pure ASCII input is unaffected, which is the overwhelming majority of bank
    descriptions on this project's target market — so in practice this changes
    almost no existing vault's dedup outcome. It is a behaviour change all the
    same, and deliberately made in one place so the dedup key and the merchant
    grouping key cannot drift apart.
    """
    return unicodedata.normalize("NFC", " ".join(text.split())).casefold()


def merchant_name(description: str) -> str:
    """A best-guess shop name from a free-text bank ``description`` (FIBR-0138 D3).

    Pure and **total** — never raises for any ``str``. Fuzzy by design and refined
    per release (like the category library). A mis-grouped shop is cosmetic **in
    the drill-down**, which sums the real stored amounts (INV-1) — but it is *not*
    cosmetic in ``services.recurring``, where the same key is a **filter**: a
    merchant split across two groups can drop each below ``_MIN_OCCURRENCES`` and
    vanish from the recurring list, and so from the forecast that projects it.

    ``services.month_summary`` (FIBR-0231) is the **third** consumer and the
    **second** filter case, and the sharpest of the three: the key groups a
    month's spend rows into merchant families, and the cause clause names the
    family whose spend most exceeds its own baseline. Both directions bite — a
    merchant split across two keys halves its excess and can drop it under the
    60% gate, and two shops folding to one key manufacture an excess and can name
    the wrong payee. So a change here can gain, lose or change a user's cause
    *sentence* with no change to their data.

    Steps: strip; shed leading
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
            # A non-empty prefix always consumes ≥ 1 char, so a match makes progress.
            if match:
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
