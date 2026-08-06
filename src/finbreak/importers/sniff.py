"""Format detection for a picked statement file (FIBR-0085 §4.1).

``looks_like_ofx`` and ``looks_like_pdf`` were ``@staticmethod``s on
``ImportWizardWidget`` — a ``QWidget`` subclass. Neither touched ``self``, and
the batch import's classify ladder needs both from a **headless** service, so a
call from ``services/batch_import.py`` would have made the service import the UI
layer and inverted the dependency direction ``docs/design.md`` sets. They live
here instead; the wizard calls them from here too, so there is one definition.

Both sniff a **bounded** 512-byte head rather than the whole file, so the
``ImportService`` size cap cannot be bypassed by the sniff, and both map an
unreadable file to ``False`` — the CSV path re-reads it and surfaces the OS
error as a shown message.
"""

from __future__ import annotations

from pathlib import Path

_SNIFF_BYTES = 512


def _head(path: str) -> bytes | None:
    """The first ``_SNIFF_BYTES`` of ``path``, or ``None`` if it cannot be read."""
    try:
        with Path(path).open("rb") as handle:
            return handle.read(_SNIFF_BYTES)
    except OSError:
        return None


def looks_like_ofx(path: str) -> bool:
    """OFX detection (FIBR-0008 D10): by extension (``.ofx``/``.qfx``), with a
    bounded content-sniff fallback for a mis-named file. A ``.csv`` extension is
    always CSV."""
    lower = path.lower()
    if lower.endswith((".ofx", ".qfx")):
        return True
    if lower.endswith(".csv"):
        return False
    head = _head(path)
    if head is None:
        return False
    head = head.lstrip().upper()
    return head.startswith(b"OFXHEADER") or b"<OFX" in head


def looks_like_pdf(path: str) -> bool:
    """PDF detection (FIBR-0009 INV-7a): by ``.pdf`` extension, else a bounded
    content-sniff for the ``%PDF-`` magic (an ASCII literal, case-exact). A
    CSV/OFX extension is never PDF."""
    lower = path.lower()
    if lower.endswith(".pdf"):
        return True
    if lower.endswith((".csv", ".ofx", ".qfx")):
        return False
    head = _head(path)
    if head is None:
        return False
    return head.lstrip().startswith(b"%PDF-")
