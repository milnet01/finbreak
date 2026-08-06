"""FIBR-0086 INV-8 — no real corpus account number is in the tracked tree.

The repository is PUBLIC. A bank account number is not a credential, so
``gitleaks`` does not match it and the security gate passes a leak of exactly this
shape — which is how one sat in a spec for a month (FIBR-0244). Hence a test of
its own.

The numbers this guards against are themselves the secret, so they are **not**
committed: they come from ``FINBREAK_CORPUS_NUMBERS`` (comma-separated) and the
test **skips** when it is unset. Run it with the variable set before any push
touching this feature. CI cannot hold the values, so CI does not catch this — a
developer running it before a push does.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from finbreak.services.account_match import normalise_account_number

# A digit run allowing a SINGLE space or dash between digits — the same shape the
# extractor captures, so "11 222 333 4" is found as one run rather than four.
_DIGIT_RUN = re.compile(r"(?:\d[ -]?)*\d")

# Below this many digits a run cannot be an account number, and every file is full
# of short ones (line numbers, dates, versions). The real keys are 9-11 digits.
_MIN_DIGITS = 8

_SKIP_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".gz", ".zip", ".svg", ".icns", ".woff2"}
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _tracked_files(root: Path) -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [root / name for name in listed.split("\0") if name]


def test_no_corpus_numbers_in_tree() -> None:
    """Normalising the HAYSTACK, not just the needles, is the whole point.

    Everything this feature stores and displays is *as printed*, so the likeliest
    leak spelling is ``11 222 333 4`` — which does not contain the substring
    ``112223334``. A needle-only grep would miss exactly the shape the rest of the
    design encourages.
    """
    raw = os.environ.get("FINBREAK_CORPUS_NUMBERS", "").strip()
    if not raw:
        pytest.skip(
            "FINBREAK_CORPUS_NUMBERS unset — the real numbers are deliberately not "
            "committed, so this guard only runs where they are supplied."
        )

    keys = {
        normalised
        for part in raw.split(",")
        if (normalised := normalise_account_number(part.strip()))
    }
    assert keys, "FINBREAK_CORPUS_NUMBERS held no usable digits"

    root = _repo_root()
    offenders: list[str] = []
    for path in _tracked_files(root):
        if path.suffix.lower() in _SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable — no prose to leak
        for run in _DIGIT_RUN.findall(text):
            if sum(ch.isdigit() for ch in run) < _MIN_DIGITS:
                continue
            if normalise_account_number(run) in keys:
                # Report the location only — never the value. A failure message is
                # printed to a terminal and pasted into issues; echoing the number
                # would re-leak what the test exists to catch.
                offenders.append(str(path.relative_to(root)))
                break

    assert not offenders, (
        "A real corpus account number appears in these tracked files: "
        f"{sorted(offenders)}. Replace it with a synthetic stand-in that preserves "
        "the digit length and grouping. Note this binds prose — specs, ROADMAP, "
        "CHANGELOG — as well as fixtures."
    )
