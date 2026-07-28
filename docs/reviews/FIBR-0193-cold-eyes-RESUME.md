# /cold-eyes run state — FIBR-0193 (and the FIBR-0113 gate still owed)

Written 2026-07-28 so this run survives a context compaction. Delete it on the
run that finally converges — a stale resume file is worse than none.

## Where the run stopped

- **FIBR-0193** (`docs/specs/FIBR-0193.md`) — **loops 1, 2 and 3 complete**,
  all dispatched, verified, fixed, logged and committed (`4f7a669`, `35d93e8`,
  `af4dbcc`). **Loop 4 is owed and NOT yet dispatched** — the lane copy and
  shared block are already rebuilt for it, so it can go straight out.
- **FIBR-0113** (`docs/specs/FIBR-0113.md`) — **gate not started.** Rewritten as
  the UI half and committed, never reviewed. This is the second half of the
  user's instruction and is still owed. Its materials are already staged (see
  "FIBR-0113 gate — prepared" below), so it can start immediately.

## Tally so far (FIBR-0193)

| Loop | CRIT | HIGH | MED | LOW | Verified | Fixed |
|---|---|---|---|---|---|---|
| 1 | 1 | 3 | 13 | 12 | 29 | 29 |
| 2 | 0 | 2 | 8 | 9 | 20 | 20 |
| 3 | 0 | 2 | 8 | 11 | 21 | 21 |

Full per-loop detail is in the spec's own §13 rows. **Not converged.**

## Why loop 4 was judged necessary (user asked; this is the answer given)

The **contract** is buildable and has been stable since loop 1 — schema v13, the
two nullable columns, the dataclass shape, the four signatures,
`_normalise_optional`, INV-1..INV-7. Loops 2 and 3 did not change what to build.

Loop 4 is owed for one specific, measured reason: **every loop so far has found
defects introduced by the previous loop's fixes.** Both of loop 3's HIGHs were
loop-2 fix damage (§7 still promising a deleted AST scan; §11's rewritten row
blurring a catcher with a `nothing`, the shape spec-format §5.8 forbids). Loop
3's own fixes are the same magnitude of edit — leg 2 rewritten into four
sub-assertions, §7's inventory restructured into a list, §11 split — and they
are **currently unreviewed**. Signing off now ships an edit pass whose two
predecessors each had fix-induced defects.

**Stopping rule committed to the user:** if loop 4 produces no HIGH and no
contract-changing MEDIUM, the spec is signed off regardless of remaining
prose-level polish. Do not spend loop 5 on wording.

**Loop 3 must dispatch every lane at the strong model and must NOT run the cheap
breadth pass** — the skill's rule: on the loop after any loop that produced a
verified CRITICAL or HIGH, a breadth pass may not accept a lane clean. Loop 2
produced 2 HIGH, so it still binds for loop 4. It stops binding only after a
loop that produces neither.

Project cap is `--max-loops 7` (finbreak override, not the skill default of 5).

## Lane partition (reuse verbatim)

| Lane | Scope |
|---|---|
| A — schema/migration | §4.1, INV-1, INV-2, §6 churn + atomicity + backup, §7 legs 1–5, §10 |
| B — model/repo/service | §3, §4.2, INV-3..INV-7, §6 direct-caller, §7 test_accounts legs, §8, §11 |
| C — cross-doc/format | header, §1, §2, §9, §11, §12, spec-format conformance |

All three lanes had findings in both loops, so **no lane may be skipped**.

## Shared block + lane copy

- Brief: `<scratchpad>/ce-0193/shared-context.md`
- Lane copy: `<scratchpad>/ce-0193/FIBR-0193-under-review.md` — byte-identical to
  the spec except §13's body, which is replaced with a placeholder so lanes
  cannot read review history. **Rebuild this after every fix pass**, or lanes
  review stale bytes.

Where `<scratchpad>` is
`/tmp/claude-1000/-mnt-Games-Scripts-Linux-finbreak/9ddde0cc-c57c-41a1-9328-a54409b70019/scratchpad`.

The block's §7 mechanical figures are measured per-loop and go stale on every
fix pass — re-derive before each dispatch. Its §6 "settled source facts" are
still current (no source file has been edited; this run only edits docs).

## Reproductions and measurements from Phase 3

Loop 1's set is unchanged and still holds (nothing in `src/` or `tests/` has
been edited). Loop 2 added:

- The `v12`-as-latest **comment** sweep is **5** files
  (`grep -rln 'v12' tests/ --include='*.py'`), NOT the 14 assertion-churn files.
  `spending_alerts/test_alert_dismissals.py` and
  `spending_alerts/test_alert_service.py` carry stale comments and are outside
  every count in §6 — neither names `LATEST_SCHEMA_VERSION`, reads
  `schema_version`, nor touches the backup manifest.
- `build_v9_vault` seeds **only** `transactions`, and only what the caller passes
  as `rows` (two of three call sites pass `[]`). Nothing in the
  `build_v9_vault` → `build_v1_vault` chain ever writes `statement_periods`, so
  a `foreign_key_check` over that table is vacuous without an explicit INSERT.
- `AccountService` exposes **no by-id getter**: `list_accounts`, `add_account`,
  `update_account`, `delete_account`, `get_pdf_password`, `set_pdf_password`,
  `account_ids_with_pdf_password`. `AccountsWidget._refresh` stashes only
  `_ACCOUNT_ID_ROLE`, `_ACCOUNT_NAME_ROLE`, `_ACCOUNT_TYPE_ROLE`,
  `_ACCOUNT_HAS_PW_ROLE`.
- `docs/specs/` filename shapes: **48 bare-ID, 1 topic-suffixed** before the
  rename; 49 bare-ID after.
- `security-model.md` T13 is a **clipboard** row whose mitigation asserts
  "account numbers are **not** copyable" — so FIBR-0113 falsifies it via the
  editable form field, not via display.

## Open ledger rows / surfaced-not-fixed

- **FIBR-0195** — the project-wide `docs/plans/` gap. Surfaced, filed, not fixed
  (a project-convention decision, not a docs defect).
- **FIBR-0196** — `naming.md` (`<ID>.md`) vs the shared `spec-format.md`
  (`<ID>-<topic>.md`). The *instance* was fixed by renaming this spec; the
  standards conflict is not.
- **FIBR-0194** — latent selection drift in `StatementsWidget.refresh`
  (code-side, surfaced not fixed).

List all three in the shared block as *already surfaced to the user — do not
report or re-confirm*, and do **not** count them as substantive for convergence.

## FIBR-0113 gate — prepared, not started

Materials are already staged under `<scratchpad>/ce-0113/`:

- `shared-context.md` — written, with settled source facts verified 2026-07-28.
- `FIBR-0113-under-review.md` — the redacted lane copy (960 lines).

Mechanical pre-pass already run and clean: `spec_lint` 0 findings,
`doc_integrity` 0, `doc_citations` 0 citations, INV-1..22 contiguous, 979 lines.

Lane partition for that run:

| Lane | Scope |
|---|---|
| A — masking/reveal/form | §4.1, §4.3, INV-5/6/11/12/16/19/20 |
| B — table/sort/identity | §4.2, §8, INV-7/8/9/15/17/18/21/22 |
| C — cross-doc/format | header, §1, §2, §3, §9, §10, §11, §12, withdrawn stubs |

**Known open question for the user:** FIBR-0113 is still 979 lines — the size
that triggered the split. The decision taken was to gate it once as-is and let
the loop produce evidence, rather than splitting again on a guess.

## Commit

Docs are at `af4dbcc` on `main`. Nothing pushed.
