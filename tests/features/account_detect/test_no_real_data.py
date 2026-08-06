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

# A digit run allowing ANY single run of separator characters between digits.
#
# Deliberately wider than the extractor's own `[ -]?`, because this is a leak
# guard, not a parser: it has to find a number however it was pasted. The prose in
# this repo is hard-wrapped at ~80 columns, so a grouped number pasted into a spec
# paragraph gets split at a group boundary — and "5566 777\n888 9" under the
# narrow class is two sub-8-digit fragments that both fall under the floor and
# vanish. Tabs, non-breaking spaces and en-dashes fail the same way.
_DIGIT_RUN = re.compile(r"\d(?:[\s .\-‐-―]{0,4}\d)*")

# Below this many digits a run cannot be an account number, and every file is full
# of short ones (line numbers, dates, versions). The real keys are 9-11 digits.
_MIN_DIGITS = 8

# Binary only. `.svg` is deliberately NOT here — it is plain text and gets read.
# `.pdf` is skipped because its bytes are compressed, so a real statement committed
# as a fixture would not be caught by a text scan; that gap is the author's to hold
# and is recorded in the spec's §11 "what checks this" table.
_SKIP_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".gz", ".zip", ".icns", ".woff2"}
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


@pytest.mark.parametrize(
    "spelling",
    [
        "5566 777 888 9",  # grouped, one line — the as-printed form
        "55667778889",  # unspaced
        "5566 777\n  888 9",  # hard-wrapped mid-number, 2-space continuation
        "5566\t777\t888\t9",  # tab-separated
        "5566-777-888-9",  # dash-separated
        "00 5566 777 888 9",  # zero-padded
    ],
)
def test_the_scanner_sees_every_spelling_a_leak_could_take(spelling: str) -> None:
    """Guards the guard.

    The scan is only worth its green result if it finds a number however it was
    pasted. Prose here is hard-wrapped at ~80 columns, so a grouped number in a
    spec paragraph really does get split mid-number — and that is the spelling the
    rest of this feature encourages, since everything is stored and displayed
    as-printed. A narrower separator class turns each fragment into a sub-8-digit
    run that the floor discards, and the guard passes on a live leak.
    """
    hits = {
        normalise_account_number(run)
        for run in _DIGIT_RUN.findall(spelling)
        if sum(ch.isdigit() for ch in run) >= _MIN_DIGITS
    }

    assert "55667778889" in hits


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
