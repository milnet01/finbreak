"""FIBR-0278 — CLAUDE.md's prose-check suite list is bound to the tree.

See spec.md. Two invariants:

  INV-1 — the fenced ``pytest`` command under CLAUDE.md's "### Doc-only pushes
  skip the FULL gate, never the prose checks" section names exactly the
  suites this module's ``_READS_PROSE`` ledger names. Whichever side gains a
  suite without the other is a stale list — the exact failure FIBR-0278 was
  filed over (the section named two suites where the real answer was four).

  INV-2 — every directory under ``tests/features/`` is classified into
  ``_READS_PROSE`` or ``_NO_PROSE``. A new suite that reads a tracked doc's
  contents, or requires one to exist, and is sorted into neither, turns this
  red rather than passing uncovered — the same "hand-maintained set, nothing
  binds it" shape as ``tests/features/dialog_lifecycle/``'s ``_FILES`` guard
  against FIBR-0277.

CLAUDE.md itself forbids re-deriving ``_READS_PROSE`` by grep ("No grep
re-derives this list, so do not try to"): ``account_detect`` walks
``git ls-files`` and names no path literal, so no search-based audit can see
it. This module does not shell out to git or the network — it only parses
CLAUDE.md's own fenced command and walks the local ``tests/features/``
directory.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.features

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_FEATURES_DIR = _REPO_ROOT / "tests" / "features"

_SECTION_HEADING = "### Doc-only pushes skip the FULL gate, never the prose checks"

# A suite name is a `tests/features/<name>/` path segment referenced on the
# fenced `pytest` command line(s) in CLAUDE.md § Doc-only pushes.
_SUITE_PATH = re.compile(r"tests/features/(\w+)/")


# -- INV-1: the ledger, hand-maintained, checked against CLAUDE.md's fence -- #

# Five suites read a tracked doc's contents, or require one to exist, and so
# must run on a doc-only push. Each reason is the one CLAUDE.md § Doc-only
# pushes gives for that suite; this module does not invent its own.
_READS_PROSE = frozenset(
    {
        # Walks `git ls-files` and reads every tracked TEXT file looking for a
        # leaked real account number (FIBR-0086 INV-8) -- binds prose, not
        # just fixtures, because a real number reached a spec once (FIBR-0244).
        "account_detect",
        # Reads docs/specs/FIBR-0001.md and diffs its stage table against
        # scripts/ci-local.sh (FIBR-0001 INV-1) -- a doc-only edit to that one
        # spec can turn this suite red.
        "harness",
        # Reads docs/security-model.md and asserts the signed-SHA256SUMS note,
        # the INV-13 definition, and the 800 chars after it (INV-7) --
        # reflowing that section is enough to turn it red.
        "release_integrity",
        # Asserts packaging/flatpak/README.md EXISTS (contents not read) --
        # moving or deleting that file is a red doc-only push.
        "flatpak_packaging",
        # This suite: INV-1 below parses CLAUDE.md's own fenced command, so it
        # reads a tracked doc's contents and is a member of its own ledger.
        "prose_checks",
    }
)

# Every other suite directory. Two are near-misses CLAUDE.md calls out by
# name -- each mentions a doc path but is excluded, and the comment says why.
_NO_PROSE = frozenset(
    {
        "accounts",
        "amount_input",
        "app_shell",
        "auto_update",
        "backup",
        "batch_import",
        # Cites docs/specs/FIBR-0003.md and docs/specs/FIBR-0155.md in
        # docstrings/comments only -- never read at runtime.
        "bundling",
        "categories",
        "categorisation",
        "category_library",
        "clipboard",
        "dashboard",
        "dashboard_drilldown",
        "dashboard_focus",
        "datetime_display",
        "datetime_format",
        "db_performance",
        "dialog_lifecycle",
        "first_run",
        "forecast",
        # Names docs/design.md as a FIXTURE PATH STRING, tested for
        # ignore-status inside a throwaway git repo seeded with only a copy of
        # the project's top-level .gitignore -- the real file's presence or
        # contents never affects the result.
        "gitignore",
        "import_",
        "import_back_step",
        "import_column_detect",
        "import_date_detect",
        "month_summary",
        "obs_packaging",
        "ofx_import",
        "password_hint",
        "pdf_export",
        "pdf_import",
        "reconciliation",
        # FIBR-0019 recovery key -- reads no tracked document: its fixtures
        # are vaults built under tmp_path and its only file scan is of that
        # tmp data directory (INV-5), never the repository.
        "recovery_key",
        "recurring",
        "reporting",
        "settings",
        "single_instance",
        "spending_alerts",
        "standard_bank_pdf",
        "statements",
        "table_state",
        "theme",
        "transactions_tab",
        "transfers",
        "unlock_throttle",
        "vault",
        "vault_reset",
        "windows_build",
    }
)

_MEMBERSHIP_RULE = (
    "a suite belongs here if it reads a tracked doc's CONTENTS or requires "
    "one to EXIST."
)


def _fenced_pytest_block(claude_md_text: str) -> str:
    """The ```bash fence directly under § Doc-only pushes, backslashes joined.

    Raises with a diagnosable message if the section or its fence has moved
    or been renamed, rather than silently matching the wrong block.
    """
    heading_at = claude_md_text.find(_SECTION_HEADING)
    assert heading_at != -1, (
        "CLAUDE.md no longer has the heading "
        f"{_SECTION_HEADING!r} -- INV-1 cannot locate the fenced pytest "
        "command it is supposed to check. If the section was renamed, "
        "update _SECTION_HEADING to match."
    )
    after_heading = claude_md_text[heading_at:]

    fence_open = after_heading.find("```bash\n")
    assert fence_open != -1, (
        "no ```bash fence found under CLAUDE.md's "
        f"{_SECTION_HEADING!r} section -- INV-1 has nothing to parse."
    )
    body_start = fence_open + len("```bash\n")
    fence_close = after_heading.find("```", body_start)
    assert fence_close != -1, (
        "the ```bash fence under CLAUDE.md's "
        f"{_SECTION_HEADING!r} section is never closed."
    )
    return after_heading[body_start:fence_close]


def _suites_named_in_claude_md() -> frozenset[str]:
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    block = _fenced_pytest_block(text)
    # The pytest invocation is line-continued with trailing backslashes
    # across multiple lines; join them before scanning for suite paths.
    joined = block.replace("\\\n", " ")
    return frozenset(_SUITE_PATH.findall(joined))


def test_INV1_claude_md_prose_list_matches_the_ledger() -> None:
    claimed = _suites_named_in_claude_md()

    only_in_claude_md = claimed - _READS_PROSE
    only_in_ledger = _READS_PROSE - claimed

    assert not only_in_claude_md and not only_in_ledger, (
        "CLAUDE.md's § Doc-only pushes fenced pytest command and this "
        "module's _READS_PROSE ledger disagree.\n"
        f"  named in CLAUDE.md but missing from _READS_PROSE: "
        f"{sorted(only_in_claude_md) or '(none)'}\n"
        f"  in _READS_PROSE but missing from CLAUDE.md's command: "
        f"{sorted(only_in_ledger) or '(none)'}\n"
        "Fix: update CLAUDE.md's fenced pytest command AND this module's "
        "_READS_PROSE ledger together -- updating only one leaves the "
        "other stale again."
    )


def test_INV2_every_suite_directory_is_classified() -> None:
    on_disk = {
        p.name
        for p in _FEATURES_DIR.iterdir()
        if p.is_dir() and p.name != "__pycache__"
    }
    ledgered = _READS_PROSE | _NO_PROSE

    overlap = _READS_PROSE & _NO_PROSE
    assert not overlap, (
        f"{sorted(overlap)} appear in BOTH _READS_PROSE and _NO_PROSE -- a "
        "suite is either one or the other, never both."
    )

    unclassified = on_disk - ledgered
    stale_entries = ledgered - on_disk

    assert not unclassified and not stale_entries, (
        "every suite under tests/features/ must be sorted into exactly one "
        f"of _READS_PROSE or _NO_PROSE. The membership rule: {_MEMBERSHIP_RULE}\n"
        f"  on disk but classified nowhere: {sorted(unclassified) or '(none)'}\n"
        f"  ledgered but no longer on disk: {sorted(stale_entries) or '(none)'}\n"
        "If a new suite reads a tracked doc's contents or requires one to "
        "exist, add it to _READS_PROSE (with a one-line reason) AND to "
        "CLAUDE.md's fenced pytest command. Otherwise add it to _NO_PROSE."
    )
