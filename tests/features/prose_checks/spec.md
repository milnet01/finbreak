# Feature test contract — the prose-check suite list is bound to the tree (FIBR-0278)

`CLAUDE.md` § Doc-only pushes prescribes an **enumerated** list of feature
suites that a doc-only push (§ Doc-only pushes, "every path ends in `.md`")
must still run, because they read a tracked doc's contents or require one to
exist — running the full gate is skipped, but these suites are not. Nothing
bound that list to reality: on 2026-08-18 it named two suites and the real
answer was four (`docs/reviews/CLAUDE-md-review-log.md`, FIBR-0278). A suite
that reads a tracked doc and is not on the list is invisible to a doc-only
push — the exact failure mode the section exists to prevent.

CLAUDE.md itself rules out re-deriving the list by grep: `account_detect`
walks `git ls-files` and names no path literal, so no search-based audit can
see it, and a recipe that tried was deleted as unreproducible (two different
readings returned 64 and 4 files). So this suite is a **ledger plus a
classify-everything assertion**, the same shape as `tests/features/
dialog_lifecycle/`'s `_FILES` guard against FIBR-0277: a hand-maintained set
is honest only when something forces every new member to be sorted into it.

| # | INV | Assertion |
|---|-----|-----------|
| 1 | INV-1 | **The CLAUDE.md list is not stale.** Parse the fenced ` ```bash ` block under "### Doc-only pushes skip the FULL gate, never the prose checks", join its backslash line-continuations, and extract every `tests/features/<name>/` path referenced on the `pytest` command line(s). That set must equal this test module's `_READS_PROSE` ledger exactly. A mismatch names which side has what the other doesn't, and says to update CLAUDE.md's fenced command **and** the ledger together — updating only one leaves the other stale again. |
| 2 | INV-2 | **Every suite under `tests/features/` is classified.** Every directory there (barring `__pycache__`) appears in exactly one of `_READS_PROSE` or `_NO_PROSE` — the two are disjoint and their union is the full set of suite directories. A new suite that reads a tracked doc's contents, or requires one to exist, and is filed in neither, turns this test red rather than silently passing uncovered. The failure message states the membership rule verbatim: "a suite belongs here if it reads a tracked doc's CONTENTS or requires one to EXIST." |

## The ledger, as of this writing

`_READS_PROSE` (5, each with the reason inline in the test module):
`account_detect`, `harness`, `release_integrity`, `flatpak_packaging`,
`prose_checks` (this suite reads `CLAUDE.md` itself, so it is its own
member — see INV-1's parse).

`_NO_PROSE` is every other suite directory. Two are near-misses called out by
name in `CLAUDE.md` and carry an inline comment saying why they are excluded
despite mentioning a doc path: `bundling` (cites spec paths in a docstring
only — never read at runtime) and `gitignore` (names `docs/design.md` as a
*test fixture path string*, tested for ignore-status inside a throwaway git
repo seeded with only a copy of `.gitignore` — the real file's presence or
absence never affects the result).

## Scope

In scope: the two ledgers stay truthful against CLAUDE.md's fenced command and
against the suite directories that exist on disk. Out of scope: judging
whether the *membership rule itself* is correctly worded, and re-deriving
`_READS_PROSE` from source (CLAUDE.md says not to, and INV-1 exists precisely
because that can't be done mechanically).

## Regression history

Filed as FIBR-0278 after all three `review-contract-set` lanes independently
found the same staleness on 2026-08-18: the list read two suites
(`account_detect`, `harness`) where the real count was four, missing
`release_integrity` and `flatpak_packaging`. This suite is the fix.
