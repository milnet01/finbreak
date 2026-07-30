# /cold-eyes run state — FIBR-0193 (and the FIBR-0113 gate still owed)

Written 2026-07-28 so this run survives a context compaction. Delete it on the
run that finally converges — a stale resume file is worse than none.

## Where the run stopped

- **FIBR-0193** (`docs/specs/FIBR-0193.md`) — **GATE CLOSED. All seven loops
  run**, dispatched, verified, fixed, logged and committed (`4f7a669`,
  `35d93e8`, `af4dbcc`, `bcfbfd8`, `bafa4fd`, `76d3d95`, `b5107c5`). Loop 7 hit
  the project cap (`--max-loops 7`), and the run ends there per global rule 14 —
  file the tail and ship rather than loop further. **Nothing is owed on this
  spec.** Its §13 carries the full seven-row log; the fix ledger with all 85
  rows and every per-loop sweep is at `/tmp/cold-eyes-9ddde0cc/fix-ledger.json`
  (session-local — not durable).

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
| 4 | 0 | 4 | 9 | 9 | 24 | 23 (+1 deferred, 1 dismissed) |
| 5 | 0 | 4 | 8 | 8 | 20 | 20 (+1 INFO folded in, 3 dismissed) |
| 6 | 0 | 2 | 7 | 8 | 17 | 17 (+1 sweep fix) |
| 7 | 0 | 1 | 10 | 10 | 21 | 21 — **cap; gate closed** |

Full per-loop detail is in the spec's own §13 rows. **Not converged.**

**The signal to carry into loop 6 — loop 5 answered loop 4's question.** Loop 4's
prediction was that another §11/§12 loop would prove those sections structurally
unsound. Loop 5 returned 4 HIGH again, and **two of them were caused by loop 4's
own fixes**: §12's bullets are written as *instructions*, loop 4 carried three of
them out as collateral, and an instruction that has been carried out is a false
statement about the tree. That is a mechanism, not a wording problem, and it is
why §12 was wrong in five consecutive loops.

**It is now fixed at the mechanism:** §12 carries a rule making every bullet a
*state claim* about the tree, marked applied or pending and checkable by opening
the named file. Moving the per-sibling instructions into the sibling specs — loop
4's suggested fix — was **rejected**: a sibling spec should not carry another
item's pending TODO, and the state-claim framing removes the rot without moving
anything.

**Loop 6 is the test of that prediction, and it is also the decision point.** Two
figures to weigh when it returns:

- The **build contract** (§4.1, §4.2, §5, §7's legs) has now been stable for
  **five** loops. Nothing since loop 3 has changed what an implementer builds.
- The document is **growing** — 963 → 1041 lines in loop 5 alone — while the
  findings move further into the meta-layer. That is global rule 14's
  oversized-document signal, and it argues for filing the tail rather than
  spending loop 7.

If loop 6 returns no finding that changes the build contract, **stop there**:
file whatever remains as roadmap items and ship the spec, rather than using the
last loop. Convergence is not literal zero.

**Loop 4's own fix-induced defects, caught by the post-fix sweep rather than by
the next loop** (the first time in this run that happened): the §12 fix
contradicted §6 over whether anything in FIBR-0172 INV-14a's guard "advances",
and an added §4.1 docstring note duplicated replay-safety prose §4.1 already
carried. Both were fixed before the commit. The sweep also caught `979` going
stale here because the collateral edit grew FIBR-0113 to 981.

## Why loop 4 was judged necessary (user asked; this is the answer given, and loop 4 vindicated it)

> Loop 4 outcome against the stopping rule stated below: the rule was "no HIGH and
> no contract-changing MEDIUM → sign off". It produced **4 HIGH**, so the rule did
> not fire and loop 5 is owed. The prediction that drove the loop — that
> unreviewed loop-3 fixes carried defects — held: §11's `SCHEMA_VERSION` row,
> which loop 3 *split*, asserted a `nothing` that was false in both halves.


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

**Materials must be RE-STAGED before this gate runs — the previously staged copies
are gone and their figures are stale.** Two independent causes, both after the
figures below were measured:

1. The session scratchpad was wiped on restart, destroying
   `<scratchpad>/ce-0113/shared-context.md` and the redacted lane copy.
2. FIBR-0193's cold-eyes **loop 4** amended FIBR-0113 itself (§4.2 and its §11
   row: the `_ACCOUNT_*_ROLE` deletion set went four → **six**, `amended by
   FIBR-0193`), so the document under review is not the one that was measured.

The superseded pre-pass reading was: `spec_lint` 0 findings, `doc_integrity` 0,
`doc_citations` 0 citations, INV-1..22 contiguous, 979 lines. **Re-derive every
figure** — the doc is now 981 lines and `spec_query` still reports 22 invariants,
but the rest must be re-measured rather than carried, per the fix-ledger rule
that a figure measured against edited bytes is not a figure.

Lane partition for that run:

| Lane | Scope |
|---|---|
| A — masking/reveal/form | §4.1, §4.3, INV-5/6/11/12/16/19/20 |
| B — table/sort/identity | §4.2, §8, INV-7/8/9/15/17/18/21/22 |
| C — cross-doc/format | header, §1, §2, §3, §9, §10, §11, §12, withdrawn stubs |

**Known open question for the user:** FIBR-0113 is still 981 lines — the size
that triggered the split. The decision taken was to gate it once as-is and let
the loop produce evidence, rather than splitting again on a guess.

## Commit

Docs are at `af4dbcc` on `main`. Nothing pushed.
