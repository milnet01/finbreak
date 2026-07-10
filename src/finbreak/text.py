"""Shared text-matching normaliser (FIBR-0010 D2).

``normalise_text`` collapses runs of whitespace to single spaces and casefolds —
the one primitive both the import dedup (``ImportService._normalise``) and the
rule matcher (``services.categorization.categorize``) compare against, so a rule
pattern matches a description the same way the importer dedups it. Extracted here
(coding.md § 1.3, reuse-before-rewrite) once the concept reached a second
call-site; a tiny pure function, no vault, trivially testable.
"""

from __future__ import annotations


def normalise_text(text: str) -> str:
    """Fold whitespace to single spaces, then casefold."""
    return " ".join(text.split()).casefold()
