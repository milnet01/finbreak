# Feature test contract — CSV import (FIBR-0007, P05)

Enforces `docs/specs/FIBR-0007.md`. The first importer: a pure
`CsvImporter` (text + `ColumnMapping` → `ParseResult`), an `ImportService`
orchestrator (match/save mapping profiles, multiset-delta dedup, the
atomic write, the coverage-period record), two small repositories
(`import_profiles`, `statement_periods`), the extended
`TransactionRepository` (bucket read + commit-free batch insert), the
**v3→v4** forward migration (two new tables), and the non-modal
import-wizard screen.

Every on-disk vault uses `tmp_path`; CSV fixtures are tiny in-repo
strings — no real statements, no network (testing.md § 6, security-model).
Headless layers are tested directly; the wizard round-trips (INV-10) use
the pytest-qt `qtbot` fixture.

| INV | Assertion |
|-----|-----------|
| INV-1 | Profile CRUD round-trips (repo → service); `match_profile` returns the saved profile for an exact-signature header, `None` for an unknown one, and raises `ValueError` for a duplicate-named header; `save_profile` **upserts** by signature (a second save under the same signature updates in place — one row, name + mapping overwritten). |
| INV-2 | The signature is the **exact** header fingerprint — case, spacing, and order all significant; a header with two equal names is refused (`ValueError`). |
| INV-3 | `CsvImporter.parse` → one `TransactionDraft(row_number, occurred_on ISO, amount_minor signed int, stripped description)` per valid row, reusing `parse_transaction`. 3a signed column keeps its sign (`invert_amount` negates); 3b debit→negative, credit→positive; 3c the profile `date_format` re-emits ISO-8601; 3d an over-precise amount is a `RowError`, never silently rounded. `period_start`/`period_end` are the min/max draft date (or `None` for zero drafts). |
| INV-4 | Per-row failures are **collected** `RowError(row_number, reason)`, never raised, never silent: bad date, non-numeric/non-finite/zero/over-precise amount, blank description, short (ragged) row, or a malformed debit/credit pair (both empty, both populated, or a negative magnitude). Valid rows in the same file still parse; `row_number` is 1-based over the data rows. A header-only or all-error file yields zero drafts; a truly empty file (no header) → `read_header` raises `ValueError`. |
| INV-5 | Dedup is multiset-delta on `(account_id, occurred_on, amount_minor, _normalise(description))`: `inserted = max(0, incoming − existing)` per key. Re-import adds **zero**; overlap adds only the new rows; genuine same-tuple repeats are all kept on first import; a row equal to a manually-entered one is deduped; case/whitespace-only description differences share one key (the raw description is stored). |
| INV-6 | Each successful import records one `statement_periods` row (start/end defaulting to the parsed min/max, the picked file's **basename**, an ISO `imported_at`); the same `(account_id, period_start, period_end)` span is not duplicated; if the span exists but the batch has new rows, those commit while the period insert is skipped (`period_recorded = False`); zero drafts write no period; an inverted or malformed span raises `ValueError`; a fresh span with zero delta still records the period. |
| INV-7 | The write phase is atomic (`BEGIN … COMMIT`/`ROLLBACK`, service-owned): a forced failure on the first `statement_periods` INSERT leaves — on the same connection before reopen — **neither** the batch's transactions **nor** a period row, and the vault re-imports cleanly on retry. |
| INV-8 | The v3→v4 migration is forward-only, atomic (a failure on the second `CREATE` rolls back to v3 with neither import table), idempotent (re-run no-op at v4), baseline-complete (a first-run vault ends at v4 with both import tables empty), and leaves `transactions`/`accounts`/`categories`/`settings` untouched. (`LATEST_SCHEMA_VERSION` is now 5 — the FIBR-0009 v4→v5 column — but the v3→v4 step still creates both import tables.) |
| INV-9 | A profile is applied only on an exact signature match, so a file whose header differs in any column → `match_profile` returns `None` (the wizard maps fresh); no stale profile mis-maps a changed export. |
| INV-10 | Import-wizard UI (`qtbot`): 10a a matching profile skips the mapping step and lands on the preview auto-applied; 10b no match shows the mapping step, and completing it (with a name) previews the rows and persists a new profile; 10c the preview lists every data row in file order with the new/duplicate/error summary + period fields defaulted to the parsed min/max; 10d **Import** inserts exactly the new rows, records a period, and returns to the main window; 10e a second import of the same file previews as all-duplicate and adds zero. Import is disabled iff there are zero drafts. |
| INV-11 | No network import under `src/finbreak/` (the existing vault-suite static scan covers the new modules); a match → preview → import cycle logs no password/key bytes. |
