# /cold-eyes run state — FIBR-0193 (and the FIBR-0113 gate still owed)

Written 2026-07-28 so this run survives a context compaction. Delete it on the
run that finally converges — a stale resume file is worse than none.

## Where the run stopped

- **FIBR-0193** (`docs/specs/FIBR-0193-account-storage-fields.md`) — **loop 1
  complete**: dispatched, verified, fixed, loop row written, committed at
  `4f7a669`. Loop 2 not yet dispatched.
- **FIBR-0113** (`docs/specs/FIBR-0113.md`) — **gate not started.** Rewritten as
  the UI half and committed, never reviewed. This is the second half of the
  user's instruction and is still owed.

## Loop 1 tally (FIBR-0193)

`CRITICAL 1 · HIGH 3 · MEDIUM 13 · LOW 12 · INFO 2` — verified 29, unverified 0,
all 29 fixed. Full detail is in the spec's own §13 loop-1 row.

**Loop 2 must dispatch every lane at the strong model and must NOT run the cheap
breadth pass** — the skill's rule: on the loop after any loop that produced a
verified CRITICAL or HIGH, a breadth pass may not accept a lane clean.

## Lane partition (reuse verbatim)

| Lane | Scope | Loop-1 verdict |
|---|---|---|
| A — schema/migration | §4.1, INV-1, INV-2, §6 churn + atomicity + backup, §7 legs 1–5, §10 | findings (1 HIGH, 5 MED, 6 LOW) |
| B — model/repo/service | §3, §4.2, INV-3..INV-7, §6 direct-caller, §7 test_accounts legs, §8, §11 | findings (2 HIGH, 5 MED, 4 LOW) |
| C — cross-doc/format | header, §1, §2, §9, §11, §12, §13, spec-format conformance | findings (2 HIGH, 3 MED, 5 LOW) |

All three lanes' bytes changed in loop 1, so **no lane may be skipped** in loop 2.

## Shared block

`/tmp/claude-1000/-mnt-Games-Scripts-Linux-finbreak/9ddde0cc-c57c-41a1-9328-a54409b70019/scratchpad/ce-0193/shared-context.md`

Its §7 "already-logged mechanical issues" figures were measured against loop-1
bytes and are now **stale** — re-derive the §1e counts before loop 2, or strip
the figures. Its §6 "settled source facts" are still current (no source file was
edited; this run only edited docs).

## Reproductions and measurements from Phase 3 (do not rebuild these)

Every one was run against the tree at `4f7a669`:

- `grep -rlE 'LATEST_SCHEMA_VERSION|SELECT version FROM schema_version|manifest\["schema_version"\]' tests/ --include='*.py' | sort -u | wc -l` → **14**
- `grep -rln 'LATEST_SCHEMA_VERSION *== *12' tests/ --include='*.py' | wc -l` → **10** (13 files *mention* the constant; `accounts`, `backup`, `vault` use it symbolically or in a comment)
- `grep -rlE 'SELECT version FROM schema_version' tests/ --include='*.py'` → **12** files
- `manifest["schema_version"] == 12` → **1** file (`backup/test_backup.py`)
- Six test names encode the latest version and churn; two more are genuine
  step-names and stay. `spending_alerts::test_INV14_v11_vault_upgrades_to_v12_cleanly`
  **does** churn — its body calls `run_migrations` (walks to latest) and asserts
  `== 12`.
- Five further names (`categorisation`, `import_`, `pdf_import`, `recurring`,
  `transfers` — all `..._latest_schema_version_is_10`) are **already** stale and
  stay so; pre-existing drift, FIBR-0144's evidence.
- `.venv/bin/python -c "…from finbreak.migrations import LATEST_SCHEMA_VERSION, _MIGRATIONS; print(LATEST_SCHEMA_VERSION, 13 in _MIGRATIONS)"` → `12 False` (INV-2's red evidence).
- `migrations.py` has **11** `_migrate_to_vN` functions, **all 11** with docstrings.
- `conftest.raising_conn`'s `trigger` is matched with `trigger in sql` — on the
  SQL **text** — so `"ADD COLUMN note"` fires on that ALTER and nothing else.
- `build_v9_vault` ends at v9, so reaching v12 needs exactly three chained steps.
- `tests/features/pdf_export/test_export_dialog.py` builds `Account(...)` with
  **four positional args** at module scope — this is why the two new dataclass
  fields need defaults.
- `scripts/seed_demo_vault.py` creates **three** accounts.
- `docs/specs/` holds **49** files; `docs/plans/` does not exist.
- `security-model.md`: A1 (vault contents), A4 (stored statement-PDF passwords),
  INV-9 (logs are clean) all exist as cited; `services/accounts.py` logs no
  field values.

## Open ledger rows / surfaced-not-fixed

- **FIBR-0195** — the project-wide `docs/plans/` gap. Surfaced, filed, **not
  fixed** (it is a project-convention decision, not a docs defect). Per the
  skill, list it in loop 2's shared block as *already surfaced to the user — do
  not report or re-confirm*, and do **not** count it as substantive for
  convergence.

## Collateral from loop 1

- Leaked tool-call closing tags were found at the EOF of `FIBR-0193`'s spec and
  **also** `docs/specs/FIBR-0113.md`; both stripped. Nothing else outside the
  reviewed document needed a change.
- Two new roadmap items were filed during this work and are cited from the
  specs: **FIBR-0194** (latent selection drift in `StatementsWidget.refresh`,
  code-side, surfaced not fixed) and **FIBR-0195** (above).

## Commit

Docs are at `4f7a669` on `main`. Nothing pushed.
