# Feature test contract — statements (FIBR-0052 P07.6)

Enforces the FIBR-0052 spec: the tabbed workspace shell, window geometry, and the
Statements tab (statement provenance stamp v5→v6 + delete). The design doc is
[`docs/specs/FIBR-0052.md`](../../../docs/specs/FIBR-0052.md); this file is the
per-feature test contract (the small companion the app-workflow keeps beside the
tests, not a design doc).

## What is covered here

`tests/features/statements/test_statements.py` — the FIBR-0052 invariants whose
subject is new in this phase:

- **INV-1 / INV-2 / INV-2a** — the workspace `QTabWidget` has four fixed tabs
  (`tab_home` · `tab_statements` · `tab_accounts` · `tab_categories`) in order;
  the View/toolbar nav actions switch the *same* tab instance (never rebuild).
- **INV-3a** — a lock while the import wizard occupies the content slot destroys
  the wizard (no live import survives a lock).
- **INV-5 / INV-5a** — window geometry + last tab round-trip through a plain INI
  at `paths.window_settings_path()`, outside the vault, holding no transaction
  data.
- **INV-6 / INV-6a / INV-6b / INV-6c** — the `Window` menu: Center window, Reset
  layout (to `_DEFAULT_WINDOW_SIZE`), both enabled while locked.
- **INV-7 / INV-7a / INV-7b** — the Statements tab lists imports with an exact
  linked-transaction count; a zero-linked statement still lists (count `0`).
- **INV-8 / INV-8a / INV-8b / INV-8c** — `commit_import` stamps every imported
  row with its statement; manual entry stays `NULL`; a span-reuse import stamps
  with the existing period id.
- **INV-9 / INV-9a / INV-9b / INV-9c / INV-9d** — `delete_statement` atomically
  removes the target's **orphaned** stamped rows + its record (rows a remaining
  overlapping statement also covers are handed off, not deleted — see the
  FIBR-0148 block below, which supersedes the "removes only the target's stamped
  rows" wording); the FK blocks an unsafe direct period delete; the v5→v6
  backfill links unambiguous rows only. The INV-9a/b/c/d fixtures use
  **non-overlapping** statements, so they are unchanged by FIBR-0148.

FIBR-0148 (deleting a statement must not lose transactions a remaining
overlapping statement also covers) adds its own block to
`tests/features/statements/test_statements.py`:

- **INV-1** — an overlap delete (A Jan, B Jan–Feb, B covers all of A) hands off
  A's January rows to B instead of losing them; returns 0 (nothing orphaned).
- **INV-2** — a row no remaining statement covers is still deleted; a
  zero-linked (all-deduped) statement delete removes only its period row,
  returns 0, and disturbs no row another statement owns.
- **INV-3** — a delete never turns a row into a manual (`NULL`-stamped) row.
- **INV-4** — a forced failure **after** the hand-off rolls back the re-stamp
  too (full atomic rollback across all three steps).
- **INV-5** — with ≥2 remaining covering statements, the row is handed to the
  one ordered first by `(period_start, id)`.
- **INV-6** — hand-off is account-scoped: an overlapping period on another
  account never adopts a row.
- **INV-7** — hand-off changes `statement_period_id` alone; every other column
  is unchanged.
- **INV-8** — partial overlap splits: covered rows handed off, uncovered rows
  deleted, in one call.
- **INV-9** — money-safety: the vault total drops by exactly the orphaned rows'
  summed `amount_minor` (0 under full overlap).
- **INV-10 / INV-10a / INV-10b** — the Delete action confirms (naming the count)
  then deletes + refreshes; Cancel does nothing.
- **INV-10c** (FIBR-0149) — an **overlap** delete confirms with the *actual*
  removed count (via `StatementService.delete_preview` → `(removed, kept)`), not
  the full linked count, and reassures that the shared rows stay. Under full
  overlap (`removed == 0`) the dialog says "0 of its transaction(s) will be
  permanently removed — the rest are shared with an overlapping statement and
  will stay", never "its N transactions... cannot be undone".
- **INV-11 / INV-11a** — a mutation reflects on the Home tab on next activation.
- **INV-12 / INV-12a** — Accounts/Categories built with `show_done=False` have no
  Done button; a default-constructed one still does.

The v5→v6 schema-version ripple (INV-13/INV-13a) and the v4-through-v6 upgrade
test live with the migration suites (`pdf_import`, `import_`, etc.); the FIBR-0051
`app_shell` test ripple (D14) is edited in `tests/features/app_shell/`.

## Fixtures

100 % synthetic: tiny in-repo CSV strings imported through the real
`ImportService.commit_import` on a `tmp_path` vault (real Argon2id on the vault
fixture, as the FIBR-0007 import tests do). No network, no real financial data;
the user's real credit-card PDF is for manual end-to-end validation only — never
committed, its password never written. Backfill tests build a raw v5 vault via
`conftest.build_v5_vault` and run the real `_migrate_to_v6`.

**FIBR-0201 / FIBR-0202 — multi-select bulk delete + Delete all.**

- **INV-2 / INV-7 (bulk)** — `statements_table` is `MultiSelection` and *Delete
  selected* acts on every selected row; *Change account* stays single-row and is
  disabled on a plural selection (the two shared one `has_selection` flag, and
  relaxing both would leave it clickable and silently no-op).
- **INV-8 (the measured trap)** — the reproduce-first regression. On the §2.1
  seed the shipped per-statement previews are `(0, 2)` and `(0, 1)`, so summing
  them claims **nothing** is permanently removed; the batch-aware
  `delete_preview_many` reports `(2, 1)` — the truth — and the confirm message is
  built from it.
- **INV-9** — one coverage predicate, interpolated at **four** sites. Asserted on
  the *emitted* SQL (the fragment appears twice in each of `_hand_off_sql` and
  `_split_counts_sql`), because a name-reference grep would not prove them
  identical. Plus: `hand_off_covered` refuses an id absent from `deleting`, and
  no row is ever handed to a statement inside the batch.
- **INV-10 / INV-12 / INV-17** — the batch is one owned transaction (a wedged
  delete leaves nothing deleted and the vault re-openable); `delete_statement` /
  `delete_preview` are the batch-of-one with signatures and results unchanged;
  the return is the batch **total**, and an empty batch short-circuits before the
  repository (an empty exclusion list would emit `NOT IN ()`, a syntax error).
- **INV-13** — batch equals a per-call loop, **in either order**, over three
  seeds: the §2.1 seed, a cross-account batch (the predicate is per-account), and
  a chain where the lowest-`(period_start, id)` covering statement is itself in
  the batch. Each seed is built twice in two independent vaults and the surviving
  rows *and their statement stamps* compared.
- **INV-11 / INV-14 / INV-16** — the confirm wording, via the pure
  `_confirm_text(removed, kept, statements)` helper (`_on_delete` uses a blocking
  `QMessageBox.question`, so no leg could observe a string built inside it). One
  statement uses today's two strings byte-for-byte; the four branches are
  **ordered**, and INV-16 passes counts that **differ** so a two-`%n` string —
  which Qt silently binds to one numerus — fails.
- **INV-18** — `changed` carries the batch size and fires **once** per batch; the
  shell names the number deleted, keeping "Statement deleted" at n == 1.
