"""Built-in category library (FIBR-0139) — bundled, per-release merchant guesses.

A JSON array of ``{"pattern": "<substring>", "category": "<default category name>"}``
objects, shipped in the bundle at ``data/category_library.json``. The engine consults
it **after** the user's own rules and only on unclaimed (auto) rows, so a user rule or
a manual pick always wins (INV-2/INV-3); a guessed row is stamped ``'library'`` and
shown with a "~ guess" marker the user can override.

Loading is **fail-safe** (INV-8). ``parse_library`` is pure and **total** — it never
raises for any ``str``, so every content-shape failure (unparseable JSON, a non-array
top level, a malformed entry) is swallowed here into an empty-or-shorter list.
``load_library``'s ``try/except`` covers only the *file read* (a missing/unreadable or
non-UTF-8 file), so the two failure layers are cleanly split and testable.

Callers reach ``load_library`` / ``match_library`` **through this module**
(``category_library.load_library()``, not a ``from … import`` binding) so a test can
monkeypatch them; the ``_LIBRARY_PATH`` module constant is the file-layer test seam.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from finbreak.text import normalise_text

log = logging.getLogger(__name__)

# The bundled data file, resolved package-relative so it works from source AND from a
# PyInstaller freeze (mirrors ui/icons.py's ``Path(__file__).parent / "icons"``). The
# module-level constant is the D8 test seam: the file-layer fail-safe tests point it at
# nonexistent / garbage / non-UTF-8 files and call ``load_library.cache_clear()``.
_LIBRARY_PATH = Path(__file__).parent / "data" / "category_library.json"


@dataclass(frozen=True)
class LibraryEntry:
    """One built-in guess: a substring ``pattern`` → a default ``category`` display
    name (bound to a leaf id at match time, INV-6)."""

    pattern: str
    category: str


def parse_library(text: str) -> list[LibraryEntry]:
    """Parse the library JSON ``text`` into entries. **Pure and total** — never raises
    for ANY ``str`` (INV-8):

    - unparseable / non-JSON text → ``[]`` (``json.JSONDecodeError`` is a
      ``ValueError``);
    - a parsed top-level value that is not a list → ``[]``;
    - an element that is not a ``dict``, or one whose ``pattern`` / ``category`` is not
      a non-blank ``str``, is **skipped** (the rest survive) — so ``[1, "x", {}]`` drops
      cleanly rather than raising ``AttributeError`` / ``TypeError``.

    A whitespace-only ``pattern`` is skipped too: it ``normalise_text``-folds to ``""``,
    which as an empty substring would match **every** description.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    entries: list[LibraryEntry] = []
    for element in data:
        if not isinstance(element, dict):
            continue
        pattern = element.get("pattern")
        category = element.get("category")
        if not isinstance(pattern, str) or not isinstance(category, str):
            continue
        if not normalise_text(pattern) or not category.strip():
            continue
        entries.append(LibraryEntry(pattern, category))
    return entries


@lru_cache(maxsize=1)
def load_library() -> list[LibraryEntry]:
    """The bundled library, parsed and cached (the file is read-only for the process
    lifetime). **File-layer fail-safe** (INV-8): a missing/unreadable file (``OSError``)
    or a corrupt non-UTF-8 file (``UnicodeDecodeError`` from ``read_text`` — a
    ``ValueError``, not an ``OSError``, so ``except OSError`` alone would leak it) →
    ``[]``, logged ``WARNING``. Content-shape failures are handled inside
    ``parse_library`` — this ``try/except`` covers only the read."""
    try:
        text = _LIBRARY_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        log.warning(
            "category library unreadable at %s; running without it", _LIBRARY_PATH
        )
        return []
    return parse_library(text)


def match_library(
    description: str,
    entries: list[LibraryEntry],
    name_to_id: dict[str, int],
) -> int | None:
    """The category id of the **first** entry whose ``normalise_text(pattern)`` is a
    substring of the normalised ``description`` **and** whose ``category`` name
    resolves in ``name_to_id``, else ``None``. An entry whose category no longer
    exists (a renamed or deleted default) is silently skipped, so the row falls
    through to Uncategorised — never mis-filed (INV-6). An empty / whitespace-only
    ``description`` → ``None``. Same substring / ``normalise_text`` primitive as
    ``categorize``."""
    normalised = normalise_text(description)
    if not normalised:
        return None
    for entry in entries:
        if normalise_text(entry.pattern) in normalised:
            category_id = name_to_id.get(entry.category)
            if category_id is not None:
                return category_id
    return None
