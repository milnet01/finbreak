"""FIBR-0086 INV-8 — no real corpus account number is in the tracked tree.

The repository is PUBLIC. A bank account number is not a credential, so
``gitleaks`` does not match it and the security gate passes a leak of exactly this
shape — which is how one sat in a spec for a month (FIBR-0244). Hence a test of
its own.

The numbers this guards against are themselves the secret, so they are **not**
committed. They come from the gitignored ``.corpus-numbers`` file at the repo
root (one per line), or from ``FINBREAK_CORPUS_NUMBERS`` (comma-separated),
which overrides it for a one-off run. The test **skips** when neither is
supplied. CI cannot hold the values, so CI does not catch this — a developer
running the gate before a push does.

**The file route exists because the variable alone did not work** (FIBR-0248):
nothing set it — not ``ci-local.sh``, not ``.githooks/pre-push``, not
CLAUDE.md — so this test skipped on every run for months, and the invariant's
only enforcement was a developer remembering an undocumented environment
variable. A skipping test reads as coverage while providing none. Create the
file once and the pre-push hook enforces it from then on.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from finbreak.services.account_match import normalise_account_number

# Where the corpus numbers live when they are not in the environment (FIBR-0248).
# Gitignored, so the file itself can never be the leak this test looks for.
CORPUS_FILE = ".corpus-numbers"


def corpus_numbers_raw(root: Path) -> str:
    """The corpus account numbers as supplied, or `""` when none are (FIBR-0248).

    ``FINBREAK_CORPUS_NUMBERS`` wins so a one-off run can override the file. The
    variable was the ONLY route until FIBR-0248, and nothing set it — not
    ``ci-local.sh``, not the pre-push hook, not CLAUDE.md — so this test skipped
    on every run and the invariant's only enforcement was a developer
    remembering an undocumented environment variable. A gitignored file is
    checked in by nobody and read by every run.
    """
    from_env = os.environ.get("FINBREAK_CORPUS_NUMBERS", "").strip()
    if from_env:
        return from_env
    try:
        return (root / CORPUS_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def corpus_keys(raw: str) -> set[str]:
    """Normalised account keys from a comma- or newline-separated list.

    Newlines are the natural separator for the file and commas for the
    environment variable, so both are accepted. A ``#`` comment is stripped
    rather than merely tolerated: a label like ``# account 1 of 3`` would
    otherwise contribute the digits ``13`` as a key, and a two-digit key matches
    most of the tree.
    """
    keys: set[str] = set()
    for line in raw.replace(",", "\n").splitlines():
        part = line.split("#", 1)[0].strip()
        if part and (normalised := normalise_account_number(part)):
            keys.add(normalised)
    return keys


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
    root = _repo_root()
    raw = corpus_numbers_raw(root)
    if not raw:
        pytest.skip(
            f"no corpus numbers supplied — set FINBREAK_CORPUS_NUMBERS or create "
            f"{CORPUS_FILE} (gitignored). The real numbers are deliberately not "
            "committed, so this guard only runs where they are supplied."
        )

    keys = corpus_keys(raw)
    assert keys, "the corpus numbers held no usable digits"
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


# --- FIBR-0248: the loader that decides whether the guard above runs at all ---
#
# Every number below is invented. The real ones are never written to a file in
# this repo, never printed, and never passed on a command line.


def test_FIBR0248_reads_the_gitignored_file_when_the_env_var_is_unset(
    tmp_path, monkeypatch
):
    """The bug: the env var was the only route and nothing set it, so the guard
    skipped on every run — a test that never runs is worse than no test, because
    it reads as coverage."""
    monkeypatch.delenv("FINBREAK_CORPUS_NUMBERS", raising=False)
    (tmp_path / CORPUS_FILE).write_text("11 222 333 4\n55667778\n", encoding="utf-8")

    assert corpus_numbers_raw(tmp_path), "the file must be read when env is unset"
    assert corpus_keys(corpus_numbers_raw(tmp_path)) == {"112223334", "55667778"}


def test_FIBR0248_env_var_overrides_the_file(tmp_path, monkeypatch):
    """A one-off run must be able to override a stale file."""
    (tmp_path / CORPUS_FILE).write_text("11223344\n", encoding="utf-8")
    monkeypatch.setenv("FINBREAK_CORPUS_NUMBERS", "99887766")

    assert corpus_keys(corpus_numbers_raw(tmp_path)) == {"99887766"}


def test_FIBR0248_absent_file_and_unset_env_still_skips_cleanly(tmp_path, monkeypatch):
    """Whoever does not hold the corpus must still get a clean skip, not an
    error — CI is exactly this case and always will be."""
    monkeypatch.delenv("FINBREAK_CORPUS_NUMBERS", raising=False)

    assert corpus_numbers_raw(tmp_path) == ""


def test_FIBR0248_comment_digits_do_not_become_a_key():
    """A hand-maintained file invites labels. `# account 1 of 3` would otherwise
    contribute the key `13`, which matches most of the tree and would turn the
    guard into noise until someone switched it off."""
    keys = corpus_keys("# account 1 of 3\n11222333 4  # cheque\n")

    assert keys == {"112223334"}, f"comment digits leaked into the keys: {keys}"


@pytest.mark.parametrize("separator", [",", "\n"])
def test_FIBR0248_both_separators_accepted(separator):
    """Commas suit the env var, newlines suit the file; both routes feed one
    parser, so neither can drift."""
    assert corpus_keys(f"11222333 4{separator}55667778") == {"112223334", "55667778"}
