# FIBR-0001 — review-contract loop log

The review record for `docs/specs/FIBR-0001.md`, moved here verbatim from
the spec on 2026-11-15.

## Cold-eyes loop log

| Loop | Date | Lanes | Findings (verified/fixed) | Severity | Dimensions | Outcome |
|---|---|---|---|---|---|---|
| 1 | 2026-08-05 | 2 (general-purpose, cold) | 14 / 14 | 3 HIGH · 7 MEDIUM · 4 LOW | dim 2×5, dim 8×4, dim 15×4, dim 5×3, dim 4×3, dim 6×2, dim 1×1, dim 3×1 | Build-changing findings fixed; one required a **code** change (see below). Looping. |
| 2 | 2026-08-05 | 2 (general-purpose, cold) | 12 / 12 | 3 HIGH · 5 MEDIUM · 4 LOW | dim 4×7, dim 15×3, dim 5×2, dim 1×1, dim 2×1, dim 8×1 | 7 of 12 were **collateral from loop 1's own fixes**. Consolidated rather than reconciled; blast radius swept into 2 sibling docs. Looping once to check this loop's edits. |
| 3 | 2026-08-05 | 2 (general-purpose, cold) | 6 / 6 | 1 HIGH · 3 MEDIUM · 2 LOW | dim 4×4, dim 5×3, dim 2×2, dim 15×2, dim 1×1 | Halved again. The recurring class was closed **mechanically** (`tests/features/harness/`) rather than by more prose. **CONVERGED** — stopping at the skill's default cap. |
| amend | 2026-11-15 | 0 — no reviewer dispatched | — | — | — | FIBR-0360 amendment, not a review loop: INV-1 rows 1 and 2 now scope ruff to `src tests scripts`; the scope sentence under the shellcheck stage says ruff and mypy reach `scripts/*.py`; `packaging/flatpak/` dropped from it (removed by FIBR-0452). No review: rule 14 gives an amendment none. Harness test green against the new table. |

**Loop 1 note.** This pass was triggered by an amendment recording the stages
added after P01, and it found that the document had drifted further than the
amendment did. Three of the fixes changed what an implementer would build:
INV-2 described an `actions/setup-python` step and an inline `pip install`
that `ci.yml` has not had since it moved into a container; INV-4's pin list
was a closed enumeration of five tools while eight are pinned, so a
reproducibility check derived from it would pass with `mypy` floating; and
INV-3's "0 collected" green condition is one `pytest` cannot reach (it exits
5, and the gate runs under `set -e`) — verified by running it.

The pass also found a real gap in `FIBR-0225` itself: the new `shellcheck`
stage globbed `scripts/*.sh` and so skipped the seven packaging recipes under
`packaging/obs/` and `packaging/flatpak/` — the publish path it claimed to
cover. Fixed in `scripts/ci-local.sh` by selecting via `git ls-files '*.sh'`,
which cannot go stale; all seven were already clean.

**Loop 2 note — the fixes were the problem this time.** Seven of twelve
findings were collateral from loop 1: having rewritten INV-1 to hold one
authoritative stage table, loop 1 left the *same* six-stage enumeration live in
INV-3, a five-name pin list in INV-4, and a hand-copied file list in Exit
criterion 4. The remedy was consolidation, not reconciliation — those three now
point at their single source (INV-1's table, `pyproject.toml`, the Deliverables
list) rather than restating it, so the class cannot recur.

Two findings were genuine draft defects with teeth. Loop 1's own stage table
had abbreviated the `gitleaks` invocation to `gitleaks dir .`, dropping
`--redact` — on a **public** repo that is the difference between catching a
leaked credential and printing it verbatim into a world-readable CI log. And
`security-model.md § 6` held a second gate-list table, five tools wide, while
asserting it was the single source of truth; it is now marked as threat-mapping
with INV-1 governing, and the three missing tools added.

**Loop 3 note — converged, and the class is closed by a test.** Six findings,
half of them again collateral. The decisive one was not a wording defect at
all: INV-1's "one list" guarantee had **no mechanical enforcement**, so every
drift this review found had been reachable and invisible. `tests/features/`
`harness/` now reads the table and `ci-local.sh` and compares them as an
unordered set, and regression-locks the `--redact` flag and the `git ls-files`
selector. Both guards were confirmed to fire by breaking them and watching the
suite go red. Writing it also caught two bugs in the test itself — a regex
missing `re.MULTILINE` that matched nothing, and a stage count that ignored
`ruff` running twice — both surfaced by the deliberate not-vacuous assertion.

Loop 3's other HIGH was the same shape as loop 2's: a *precondition* copied
into four places, of which INV-1's copy had gone short (it omitted
`pip install .`, describing an environment where the `mypy` and `pytest`
stages are red). Fixed the way the rest were — point at `ci-setup.sh` as the
authority instead of maintaining a fifth copy.
