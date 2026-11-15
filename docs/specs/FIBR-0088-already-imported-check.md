<!-- ants-spec-format: 1 -->
# FIBR-0088 — Warn before importing a file that was already imported

**Status:** spec draft (2026-11-15).
**Kind:** implement.
**Source:** ROADMAP FIBR-0088 (user-request-2026-07-11, dogfooding v0.1.0).

**Pairs with:** FIBR-0085 (batch import; its `already_imported` outcome is
unchanged, § 3 decision 4), FIBR-0052 (statement provenance and delete; a
fingerprint is deleted with its statement, § 4.2).

*Layman: when you pick a statement file you have already imported, finbreak
says so straight away — which account, which period, and when — and asks
whether to import it again, instead of quietly re-reading it and finding
nothing new.*

## 1. Goal

Picking a file in the single-file import wizard whose exact contents were
imported before shows a question first: before the file is parsed, before a
CSV mapping is asked for and before a PDF password is asked for. The user
either stops there or imports it again exactly as today. Every import, single
or batch, records the file's fingerprint so a later pick can be recognised.

## 2. Problem

1. **The single-file wizard never warns.** `ImportWizardWidget._on_import`
   calls `ImportService.commit_import`, which reuses an existing span through
   `StatementPeriodRepository.id_for_span` without saying so. The only cue a
   user gets is the preview's `"{new} new · {dup} duplicate · {err} error"`
   counts reading zero new — after any CSV mapping and PDF password prompt.
2. **Nothing identifies a file.** `statement_periods.source_filename` holds a
   basename only (`commit_import` stores `Path(source_filename).name`). A
   renamed copy carries a different name, and two different files can both be
   `statement.pdf`. No import path hashes file content: `hashlib` appears in
   `src/` only in `services/update.py`.
3. **The batch already handles its half.** `BatchImportService.review` sets
   `already_imported` when the span exists and `record.new_count == 0`
   (FIBR-0085 INV-10). That outcome is derived from the data, so it stays
   right when the user deletes rows; it is not this item's to change.

## 3. Scope decisions (agreed with the user)

The user delegated these calls (memory: specs are the developer's domain).
Each was made by the developer on 2026-11-15.

1. **Fingerprint the raw bytes as read from disk**, before any CSV decode or
   PDF decrypt. A locked PDF is then recognised before its password prompt,
   and the hash does not depend on what `pikepdf` writes into its plaintext.
2. **Warn and ask; never skip silently.** A corrected re-issue of a
   statement is a legitimate re-import, and transaction dedup (FIBR-0007
   INV-5) still protects the vault when the user imports again.
3. **No backfill.** Files imported before this ships were never kept, so
   their fingerprints cannot be computed. Those imports are not recognised.
4. **The batch's outcomes are unchanged.** A batch commit records
   fingerprints; it does not use them to decide an outcome. A fingerprint
   match is account-independent, and FIBR-0085 INV-10 requires outcomes to be
   re-derived both ways on every account change.
5. **Name the most recent prior import only.** One account, one period and
   one date is enough to decide; a full history is the Statements tab's job.

## 4. Design

### 4.1 Schema — migration v16 → v17

`migrations.py` gains `_migrate_to_v17`, and `LATEST_SCHEMA_VERSION` becomes
17. One `owned_transaction`, like every sibling step:

```sql
CREATE TABLE imported_files(
    id INTEGER PRIMARY KEY,
    statement_period_id INTEGER NOT NULL
        REFERENCES statement_periods(id) ON DELETE CASCADE,
    file_sha256 TEXT NOT NULL,          -- 64 lowercase hex characters
    imported_at TEXT NOT NULL,          -- UTC ISO-8601, latest import here
    UNIQUE(statement_period_id, file_sha256)
);
CREATE INDEX idx_imported_files_sha256 ON imported_files(file_sha256);
UPDATE schema_version SET version = 17;
```

A table rather than a column on `statement_periods`: `commit_import` reuses an
existing span's row, so one period can carry several files (a CSV and the PDF
of the same month; a re-issue). Pure DDL, no backfill (§ 3 decision 3).

### 4.2 Repository — `repositories/imported_files.py`

```python
@dataclass(frozen=True)
class PriorImport:            # models.py
    account_name: str
    period_start: str         # ISO date
    period_end: str           # ISO date
    imported_at: str          # UTC ISO timestamp of THIS file's latest import

class ImportedFileRepository:
    def add(self, statement_period_id: int, file_sha256: str) -> None:
        """INSERT, stamping imported_at; on a (statement_period_id,
        file_sha256) conflict, UPDATE imported_at instead, so a repeat
        import is the latest. Commit-free: the caller's import
        transaction owns the commit."""
    def latest(self, file_sha256: str) -> PriorImport | None:
        """JOIN statement_periods and accounts; ORDER BY
        imported_files.imported_at DESC, imported_files.id DESC; LIMIT 1."""
```

Deleting a statement (`StatementService.delete_statements`) deletes its
`statement_periods` row, and `ON DELETE CASCADE` removes its fingerprints —
`foreign_keys = ON` is set at vault open (`vault.py`). Moving a statement to
another account (`StatementService.reassign_account`) moves its fingerprints
with it, because they hang off the period, so `latest` names the new account.

### 4.3 Service — `services/import_.py`

```python
@dataclass(frozen=True)
class ImportSource:
    data: bytes               # exactly what _read_capped returned
    sha256: str               # hashlib.sha256(data).hexdigest()

def read_source(self, path: str) -> ImportSource: ...
def decode_csv(self, data: bytes) -> str: ...        # read_file's decode, lifted
def prior_import(self, sha256: str) -> PriorImport | None: ...
def commit_import(self, preview, period_start, period_end, source_filename,
                  source_sha256: str | None = None) -> ImportResult: ...
```

- `read_file(path)` becomes `decode_csv(_read_capped(path))`, its refusals
  unchanged. `read_file_bytes` is unchanged.
- `commit_import`, when `source_sha256` is not `None`, calls
  `ImportedFileRepository.add(period_id, source_sha256)` inside its existing
  `owned_transaction`, after the period id is resolved — on a new span and on
  a reused one alike, and whether or not any row was inserted.
- The default `None` keeps the existing test callers working. Both production
  callers pass it (INV-3).

### 4.4 Single-file wizard — `ui/import_wizard.py`

- `_select_file(path)` reads once with `read_source`, before it dispatches by
  format. `_select_ofx` and `_select_pdf` take the bytes instead of reading
  again; the CSV branch decodes them with `decode_csv`. The wizard keeps
  `source.sha256` for the commit. **The bytes hashed are the bytes parsed.**
- Immediately after the read, `prior_import(sha256)`. On a match, a parented
  `QMessageBox`, shown with `show_modal` (FIBR-0065 D1) as the wizard's PDF
  password prompt is, reads through `self.tr`:

  > You already imported this file on {imported}, into {account}, for
  > {start} – {end}. Import it again? Transactions already in finbreak are
  > skipped either way.

  Buttons **Import again** and **Cancel**; Cancel is the default and the
  Escape button. Cancel leaves the wizard on the pick step with no file
  selected and nothing written. Import again continues exactly as today, from
  the dialog's `on_accept`.
- Dates use the user's display settings: `format_timestamp` for
  `{imported}`, `format_date` for the period. The wizard takes
  `datetime_prefs` the way it already takes `amount_prefs`, and
  `MainWindow` passes `self._prefs` where it constructs the wizard.
- `_on_import` passes `source_sha256` to `commit_import`.

### 4.5 Batch — `services/batch_import.py`

`BatchFile` gains `source_sha256: str | None`, set at SCAN from
`read_source` (the CSV branch decodes with `decode_csv`). Each extra record an
OFX fan-out creates carries its file's `source_sha256` too. `_commit` passes it
to `commit_import`. No outcome, reason string or review rule changes.

## 5. Invariants

- **INV-1** — The fingerprint recorded for an import is the SHA-256 of the
  file's bytes on disk, for every format, including a password-locked PDF.
  *Test:* `tests/features/already_imported/test_already_imported.py::test_INV1_fingerprint_is_the_raw_file_bytes`
  — import a CSV, an OFX and a locked PDF fixture through the wizard and
  through `BatchImportService`, then compare each `imported_files.file_sha256` with
  `hashlib.sha256(path.read_bytes()).hexdigest()`.
  *Breaks when:* the hash is taken of the decoded CSV text or of the decrypted
  PDF plaintext — the locked PDF's case fails.

- **INV-2** — A `commit_import` given `source_sha256` records it in the same
  transaction as the rows, on a new span and on a reused span with zero new
  rows; a commit that rolls back records nothing.
  *Test:* `test_INV2_fingerprint_is_recorded_with_the_commit` — import a file,
  then a second file with different bytes but the same rows and span (it
  inserts nothing), and assert two rows on the one period; then make `add_batch` raise
  and assert no `imported_files` row was written.
  *Breaks when:* the fingerprint is written only when `period_recorded` is
  true, or outside `owned_transaction`.

- **INV-3** — Both production callers record the fingerprint: an import
  through the single-file wizard and one through the batch each leave a row
  matching the file.
  *Test:* `test_INV3_wizard_and_batch_both_record_the_fingerprint` (wizard via
  `qtbot`, batch via `BatchImportService`).
  *Breaks when:* either caller omits `source_sha256`, which the default
  `None` would otherwise allow silently.

- **INV-4** — Deleting a statement deletes its fingerprints, so picking the
  same file afterwards shows no question.
  *Test:* `test_INV4_deleting_the_statement_forgets_the_file` — import, then
  `StatementService.delete_statements`, then `prior_import(sha256) is None`.
  *Breaks when:* the foreign key lacks `ON DELETE CASCADE`.

- **INV-5** — Picking a file whose fingerprint matches shows the question
  before any parse, CSV mapping step or PDF password prompt. Cancel leaves the
  pick step showing, no preview built, and the vault unchanged.
  *Test:* `test_INV5_question_comes_first_and_cancel_changes_nothing` —
  import a locked PDF fixture, pick it again with the question answered
  Cancel, and assert no password dialog opened, `_preview is None`, the
  current step is `_STEP_PICK`, and the transaction count is unchanged.
  *Breaks when:* the check runs after `_begin_decrypt` or after parsing.

- **INV-6** — **Import again** behaves exactly as a first pick: the same
  preview, and transaction dedup still drops every duplicate row.
  *Test:* `test_INV6_import_again_dedups_as_before` — re-import with Import
  again chosen; `ImportResult.inserted_count == 0`.
  *Breaks when:* Import again bypasses `_dedup`, or skips the steps the
  format needs.

- **INV-7** — A file never imported before shows no question, even when it
  has the same name as an imported one.
  *Test:* `test_INV7_same_name_different_content_is_not_warned`.
  *Breaks when:* the match is made on `source_filename`.

- **INV-8** — The question names the most recent prior import's account,
  period and date, formatted with the user's display settings.
  *Test:* `test_INV8_question_names_the_latest_import` — import the same file
  into account A, then account B, then A again; set a non-default date
  format; assert the text names A and the third import's formatted dates.
  *Breaks when:* `latest` orders ascending, `add` keeps the first stamp on a
  repeat, or the wizard formats ISO dates itself.

- **INV-9** — Migration v16 → v17 creates the table and index in one atomic
  unit and leaves every existing row unchanged.
  *Test:* `test_migration_v17.py` — the v15-fixture pattern of
  `tests/features/loan_sign/test_migration_v16.py`, whose fixture works only
  because v16 is data-only, so this one also drops `imported_files` and its
  index before setting the version back to 16: a v16 vault opens at v17
  with its rows intact; a failure injected after the `CREATE TABLE` leaves a
  re-openable v16; a second run at v17 is a no-op.
  *Breaks when:* the steps run outside `owned_transaction`.

- **INV-10** — No fingerprint reaches the log file (security-model INV-9).
  *Test:* `test_INV10_fingerprint_is_never_logged` — `caplog` at DEBUG across
  an import and a repeat pick; the hex digest is in no record.
  *Breaks when:* a log line formats the hash or the `PriorImport`.

- **INV-11** — A batch's outcomes are unchanged by a fingerprint match.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV10_already_imported_is_recomputed_both_ways`
  passes unchanged.
  *Breaks when:* a fingerprint match sets `already_imported`, or freezes it.

## 6. Failure modes

- **The file changes between pick and commit.** It is read once (§ 4.4), so
  the recorded fingerprint is of the bytes imported, whatever is on disk later.
- **A different file with the same bytes.** That is the same statement, so
  the question is correct.
- **The prior import's account was renamed.** `latest` joins `accounts` at
  read time, so the question shows the current name.
- **The user picks the file while its first import's statement is gone.** The
  cascade removed its fingerprint (INV-4); no question.
- **A file imported before v17.** Not recognised (§ 3 decision 3). The
  preview's zero-new count still shows, as today.
- **An oversized or unreadable file.** `_read_capped` refuses it before any
  hash is computed, with today's message.
- **A restored older backup.** It migrates to v17 on open like any vault and
  holds no fingerprints.

## 7. Tests

A new suite, `tests/features/already_imported/`, holds INV-1 to INV-8 and
INV-10, with `test_migration_v17.py` for INV-9. INV-11 is the existing batch
test. Each new test is seen failing against the code before the change.

A locked PDF is made in-test, the way
`tests/features/pdf_import/test_pdf_import.py::_encrypt` makes one, with a
non-empty user password so a pick would otherwise prompt.

The new suite directory must be sorted into `tests/features/prose_checks/`'s
`_NO_PROSE` ledger, or that guard fails.
`tests/features/reconciliation/test_no_schema_change.py::test_INV8_schema_version_at_current_latest_v16`
is a deliberate tripwire on `LATEST_SCHEMA_VERSION == 16`: it fails on this
change, and its pin moves to 17 with a note that v17 is not reconciliation's.

## 8. Alternatives considered (and rejected)

- **A `file_sha256` column on `statement_periods`.** A reused span keeps only
  its first file, so the second file of a span is never recognised.
- **Match on filename.** Misses a renamed copy and warns on two different
  files both named `statement.pdf` (§ 2 item 2).
- **Hash the decrypted PDF.** The question would come after the password
  prompt it exists to save, and the plaintext depends on `pikepdf`'s output.
- **Skip a matching file silently.** Blocks a corrected re-issue with no way
  through (§ 3 decision 2).
- **Use the match in the batch.** It would make an account-independent fact
  decide an outcome that FIBR-0085 INV-10 re-derives per account (§ 3
  decision 4).
- **Warn on account and period instead.** That needs a full parse first, which
  is the work this item avoids, and the batch already covers it.

## 9. Out of scope

- Skipping parse and password prompts for a matching file inside a batch —
  deferred; not yet queued.
- Recognising files imported before v17 — not possible (§ 3 decision 3).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_already_imported.py::test_INV1_fingerprint_is_the_raw_file_bytes` |
| INV-2 | `test_already_imported.py::test_INV2_fingerprint_is_recorded_with_the_commit` |
| INV-3 | `test_already_imported.py::test_INV3_wizard_and_batch_both_record_the_fingerprint` |
| INV-4 | `test_already_imported.py::test_INV4_deleting_the_statement_forgets_the_file` |
| INV-5 | `test_already_imported.py::test_INV5_question_comes_first_and_cancel_changes_nothing` |
| INV-6 | `test_already_imported.py::test_INV6_import_again_dedups_as_before` |
| INV-7 | `test_already_imported.py::test_INV7_same_name_different_content_is_not_warned` |
| INV-8 | `test_already_imported.py::test_INV8_question_names_the_latest_import` |
| INV-9 | `test_migration_v17.py` |
| INV-10 | Partial: `test_INV10_fingerprint_is_never_logged` covers the import and pick paths; a log line added elsewhere later is caught by nothing |
| INV-11 | `test_batch_import.py::test_INV10_already_imported_is_recomputed_both_ways` |
| § 3 decision 5 (latest only) | **nothing** — a preference; INV-8 checks which import is named, not that others are left out |

## 11. Cross-doc impact

- `docs/design.md` — the **Tables (high-level)** list gains `imported_files`.
- `CHANGELOG.md` — an Unreleased entry.
- `tests/features/reconciliation/test_no_schema_change.py` — its version pin
  and docstring move to v17 (§ 7).
- `docs/specs/FIBR-0085-batch-import-service.md` — none: no outcome changes.
- `README.md` — none unless its feature list names import safeguards; checked
  at implementation.

## 12. Cold-eyes loop log

Rows live in `../reviews/FIBR-0088-already-imported-check-loop-log.md`.
