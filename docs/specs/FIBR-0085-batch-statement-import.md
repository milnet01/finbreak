# FIBR-0085 — Import a folder of statements in one unattended run

**Status:** spec draft (2026-08-06).
**Kind:** feature.
**Source:** ROADMAP FIBR-0085 (user-request-2026-07-11, dogfooding v0.1.0).

**Blocked by:** FIBR-0086 (shipped 2026-08-06) — auto-detect is what makes a
multi-file import usable; you cannot hand-map a folder.
**Pairs with:** FIBR-0088 (content-hash re-import detection), which upgrades
this spec's §4.8 `already_imported` signal from a span match to a true file
fingerprint.

**Layman:** Pick a whole folder of bank statements at once — finbreak reads
them all, asks for every password it needs in one go, shows you a single list
of what is about to land in which account, and then imports the lot without
you having to sit there.

## 1. Goal

A user selects many statement files in one dialog. finbreak reads each one,
works out which account it belongs to, and asks — **once, up front** — for
every piece of information it still needs (a PDF password, a column mapping
for an unfamiliar CSV, an account for a file it could not match). It then
shows one review table listing every file, its destination account, and the
number of transactions that will land. On confirmation the whole batch imports
without further interaction, and a per-file report says what happened. Today
the same work is N separate wizard runs.

## 2. Problem

### 2.1 The wizard is one file per run, structurally

`ui/import_wizard.py::ImportWizardWidget` selects a file with
`QFileDialog.getOpenFileName` (singular) and holds each run's state in
instance scalars — `_text`, `_header`, `_source_path`, `_preview`,
`_ofx_statements`, `_pdf_candidates`, `_date_ambiguous`, `_stored_pw`,
`_pending_hint`. One file's worth of everything. `ImportWizardWidget.done` is
a payload-free `Signal()` that `MainWindow._on_import_done` handles by
rebuilding the workspace, so finishing an import tears the screen down.

Three consequences, which the invariants in §5 trace back to:

1. **Importing 30 monthly statements is 30 full round-trips** through
   file-choose → parse → preview → import → workspace rebuild → reopen.
2. **`ImportService` has no list-taking entry point.** `preview`,
   `preview_result`, `retarget` and `commit_import` are all strictly
   one-file-one-preview, unlike the statement-delete side, where
   `services/statements.py::StatementService.delete_statements` already takes
   a sequence.
3. **`ImportService.commit_import` returns an `ImportResult` the wizard
   discards.** `ui/import_wizard.py::_on_import` calls it and ignores the
   return value. That dataclass — `inserted_count`, `duplicate_count`,
   `error_count`, `period_recorded` — is exactly the per-file summary row a
   batch report needs, and it already exists.

### 2.2 "Unattended" is a claim about *when* input is collected, not whether

The wizard's collection points are interleaved with parsing, and the order is
forced by the data, not by preference:

| Input | Must be known | Because |
|---|---|---|
| PDF password | **before** the parse | `importers/pdf_importer.py::_normalise_to_plaintext` opens the file; without it there is nothing to read |
| CSV column mapping | **before** the parse | `ImportService.preview` takes a `ColumnMapping` argument |
| Destination account | **after** the parse | `match_account` reads `ParseResult.source_account`, which the parse produces |

So a run that collects everything before doing any work is impossible: the
account question cannot be asked until the file has been read, and the file
cannot be read until its password is known. What *is* possible — and what §3
decision 1 asks for — is collecting every input before anything is
**committed**. That is the design in §4.3: parse as far as each file allows,
gather every outstanding question, ask them all, then commit.

### 2.3 Three existing behaviours do not survive contact with N files

- **`ui/import_wizard.py::_on_pdf_password` re-prompts without a bound.** A
  wrong password calls `_prompt_pdf_password` again, recursively, with no
  attempt counter. The dialog's Cancel has **no slot at all** — `finished →
  deleteLater` frees it and the wizard simply sits on the pick step. Across 30
  files that is 30 ways to stall a run with no way to say "skip this one".
- **`ui/import_wizard.py::_begin_decrypt` looks up the remembered password
  with `self._accounts.get_pdf_password(self._target_account_id())`** — the
  pick-step account. In a batch there is no pick-step account, because each
  file has its own destination. This is the same defect FIBR-0249 records for
  the single-file path, reached from a different direction.
- **`self._error` is one shared `QLabel` below the stack**, written by every
  failure path with `setText(str(exc))`. Last write wins. N files cannot
  report N distinct failures through one label.

## 3. Scope decisions (agreed with the user)

1. **Every input is collected up front; the run is then unattended to the
   end.** (User, 2026-08-06, recorded on the ROADMAP bullet.) Rejected:
   pausing at each file as it is reached — that forces the user to babysit a
   30-file import, which defeats the purpose; and skipping files that need
   input — a folder of password-locked bank PDFs is the common case, not an
   edge case.

2. **One combined review screen before anything commits.** (User,
   2026-08-06.) The scan pass has already parsed every file, so the review
   table costs no extra work, and it keeps the money-app property that nothing
   lands unseen. Rejected: committing straight through and reporting
   afterwards, which is fewer clicks but makes the Statements tab's delete the
   only undo.

3. **`already imported` is reported from the period-span match, not a content
   hash.** (User, 2026-08-06.) `StatementPeriodRepository.id_for_span` exists
   today and needs no schema change. Its honest limit is recorded in §6 and
   the upgrade is FIBR-0088: a corrected re-issue covering the same dates
   reads as already-imported, and two different files covering the same dates
   are indistinguishable. Rejected for this build: folding FIBR-0088 in, which
   adds a v13 → v14 migration and a backfill decision to a UI feature.

4. **The batch does not ask for per-file coverage periods.** The single-file
   preview step exposes two `QDateEdit`s defaulted from the parsed
   min/max dates. The batch uses those parsed defaults unedited. Asking 30
   times is exactly the babysitting decision 1 rejects, and a statement's own
   dates are the right answer in every case the corpus contains. A file
   needing a hand-set period is imported singly, which still works.

5. **The batch never creates an account without being asked**, but it does
   offer. A file whose number matches nothing reaches the review screen with
   its account cell unset and a Create affordance prefilled from the
   statement, reusing `ui/account_create.py::CreateAccountDialog`.

## 4. Design

### 4.1 Where the work lands

Two new modules and one extended widget. The split follows `docs/design.md`'s
layering: orchestration is a service, and the service is headless so the whole
of §4.3 and §4.5 is testable without Qt.

```
src/finbreak/services/batch_import.py   NEW — the orchestration + the record
src/finbreak/ui/import_batch.py         NEW — the review step widget
src/finbreak/ui/import_wizard.py        EXTENDED — multi-select entry,
                                        the scan/ask/run driver, a 4th step
```

**The wizard is extended rather than duplicated**, per `coding.md` reuse. The
map step (`_STEP_MAP`) is a large form — five column combos, amount style,
invert, the date-format picker with live preview, the profile-name field — and
an unfamiliar CSV in a batch needs exactly that form. Re-showing the existing
stack page for one file at a time during the ask pass costs nothing;
re-implementing it in a second widget would be the largest duplication in the
codebase. `PasswordDialog`, `AccountPickerDialog` and `CreateAccountDialog`
are likewise reused as they stand.

**`ui/import_batch.py` must be added to the `_FILES` tuple in
`tests/features/dialog_lifecycle/test_dialog_lifecycle.py`.** That tuple is
literally `("home.py", "rules.py", "statements.py", "import_wizard.py")` —
a new UI module is outside the FIBR-0065 INV-1 guard until it is named there,
and a guard that silently does not cover new code is worse than no guard
(INV-6).

### 4.2 The per-file record

`ImportPreview` carries no filename, no format and no hint — a batch has to
keep its own association. One frozen-shell dataclass per selected file, in
`services/batch_import.py`:

```python
# --- services/batch_import.py ----------------------------------------------

Outcome = Literal[
    "ready",             # parsed, account known, will commit
    "already_imported",  # span exists and zero new rows (§4.8)
    "needs_password",    # a locked PDF, no working password yet
    "needs_mapping",     # a CSV whose header matches no saved profile
    "needs_account",     # parsed, but match_account did not resolve one
    "failed",            # unreadable / unparseable; carries `reason`
    "skipped",           # the user declined to answer this file's question
]


@dataclass
class BatchFile:
    """One selected file, from selection through to its committed result."""

    path: str                                   # full path; basename for display
    outcome: Outcome
    preview: ImportPreview | None = None        # None until parsed
    hint: SourceAccountHint | None = None       # ParseResult.source_account
    account_id: int | None = None               # the destination, once settled
    reason: str = ""                            # user-facing text for `failed`
    result: ImportResult | None = None          # None until committed
    new_count: int = 0                          # §4.5 cumulative, not preview.new_count
```

`new_count` is deliberately **not** read from `preview.new_count`. §4.5 says
why.

The batch itself is an ordinary list, ordered by the sort order of the paths
as the file dialog returned them, and that order is the commit order (INV-4
depends on there being one).

### 4.3 Three passes

```
SCAN   for each file, in order:
         classify by extension/sniff  (reuse _looks_like_ofx / _looks_like_pdf)
         PDF   -> decrypt (§4.4); locked -> needs_password, stop this file
         CSV   -> match_profile(header); no match -> needs_mapping, stop
         parse -> ParseResult
         match_account(result.source_account, accounts)
             matched   -> account_id set
             otherwise -> needs_account
         preview_result(result, account_id)   [only once account_id is known]

ASK    for each file whose outcome is not `ready`, one at a time:
         needs_password -> PasswordDialog, at most 3 attempts (INV-8)
         needs_mapping  -> the existing _STEP_MAP page for that file
         needs_account  -> AccountPickerDialog, with Create (§3 decision 5)
       an answered file re-enters SCAN from where it stopped;
       a declined file becomes `skipped`

REVIEW recompute the cumulative counts (§4.5) and show the table (§4.6).
       No commit has happened yet.

RUN    for each `ready` file, in order: commit_import(...) -> ImportResult
       record it; continue past any failure (INV-1)
```

The ASK pass runs to exhaustion before REVIEW: there is no path from a
`needs_*` outcome to a commit (INV-3).

### 4.4 Resolving a PDF password with no pick-step account

`_begin_decrypt` cannot be reused as-is, because its stored-password lookup
is keyed on `_target_account_id()` and a batch has no such account (§2.3). The
batch tries the remembered password of **every** account before prompting:

```python
def stored_passwords(accounts: Sequence[Account],
                     get: Callable[[int], str | None]) -> list[str]:
    """Each account's remembered PDF password, de-duplicated, order stable."""
```

Attempt order per file: no password, then each distinct stored password once,
then the user. All of them are the same person's own vault, so trying account
A's password against account B's statement discloses nothing the user does not
already hold — and it is what makes a folder of same-bank PDFs need **zero**
prompts after the first month. Each distinct password is tried at most once
per file, so the cost is bounded by the account count.

A password entered during the ASK pass with *Remember* ticked is stored
against the file's **settled destination account**, which by then is known —
not against a pick-step guess. That is the shape FIBR-0249 asks for on the
single-file path; this spec does not fix the single-file path, it declines to
copy the defect.

### 4.5 Cumulative dedup — the reviewed number is the number that lands

`ImportService._dedup` runs the multiset delta against **committed** rows
only. Two files in one batch that overlap each other (a January statement and
a January–February statement, both freshly downloaded) therefore each preview
their shared rows as new: nothing has been committed yet, so nothing dedups
them against each other. `commit_import` re-runs `_dedup` inside its own
transaction, so the *result* is always correct — file B's commit sees file A's
rows. The defect is confined to the review screen, which would promise more
than lands.

Since the user is being asked to approve those numbers (§3 decision 2), the
batch computes them cumulatively:

```python
def cumulative_counts(files: Sequence[BatchFile]) -> None:
    """Set `new_count` on each `ready` file to what its commit will insert.

    Walks the batch in commit order, keeping the drafts already claimed by
    earlier files, per destination account. The key is ImportService._key's —
    (occurred_on, amount_minor, normalise_text(description)) — so this is the
    same equality the commit will apply, not a second opinion about it.
    """
```

Scoped per `account_id`, because dedup is: two files landing in different
accounts never dedup against each other however identical their rows.

This is one invariant (INV-4) and it is the reason `BatchFile.new_count`
exists as a separate field from `preview.new_count`.

### 4.6 The review step

A fourth stack page, `_STEP_BATCH = 3`, holding an `ui/import_batch.py`
`BatchReviewWidget`. One `QTableWidget`, objectName `"import_batch_table"` so
it gets its own `columns/import_batch_table` key under
`ui/_table_state.py::remember_columns` (the FIBR-0012 lesson: two unnamed
tables share one key and cross-corrupt widths).

| Column | Content |
|---|---|
| File | `Path(path).name` — the basename, matching what `commit_import` stores |
| Account | the destination account's name, or *— pick one —* |
| New | `BatchFile.new_count` (§4.5) |
| Duplicate | `preview.duplicate_count` |
| Status | the `Outcome`, rendered per §4.8 |

The Account cell is clickable on every row and opens `AccountPickerDialog`;
choosing a different account calls `ImportService.retarget(preview, id)`,
re-stores the returned preview, and re-runs `cumulative_counts` over the whole
batch — because one row's destination changes which rows every *other* row in
that account may claim.

`Import all` is enabled iff at least one file is `ready`. Files that are
`failed`, `skipped` or `already_imported` stay listed with their reason and
are not committed — they are the report, not an obstacle.

### 4.7 Driving the passes with no nested event loop

The scan and the run are loops over slow, blocking work — `pikepdf` decrypt,
`pdfplumber` extraction, a write transaction. Two mechanisms are ruled out
before any are chosen:

- **A modal `QProgressDialog` is forbidden.** Qt's documented modal pattern
  calls `processEvents()` to stay responsive, and re-entrancy is exactly the
  FIBR-0065 crash class: an idle auto-lock fires inside the nested loop,
  `MainWindow._lock()` destroys the widget, and the code after the loop reads
  a deleted C++ object. `tests/features/dialog_lifecycle/` INV-1 is a source
  grep that fails on any `.exec(` in the wizard, so this is a mechanical
  refusal and not a preference.
  Source: <https://doc.qt.io/qt-6/qprogressdialog.html>
- **A `QThread` worker is rejected**, though `ui/_worker.py::DeriveWorker` and
  `ui/_update_worker.py::DownloadWorker` are the house pattern. Both do work
  that never touches the vault — an Argon2id derivation and an HTTP download.
  The batch's work is SQLCipher reads and writes on `Vault.connection`, and
  `docs/design.md` § Concurrency puts import on the GUI thread deliberately.
  Moving a write transaction onto a second thread is a concurrency change to
  the storage layer wearing a UI feature's clothes.

The batch is driven by a **one-file-per-event-loop-turn chain**:

```python
QTimer.singleShot(0, self, self._scan_next)   # 3-arg form: `self` is the context
```

The three-argument overload is required, not stylistic. `MainWindow` already
uses it (`QTimer.singleShot(0, self, self._maybe_check_for_update)`), and the
context object is what makes the pending callback drop when the widget is
destroyed — which is precisely what an idle auto-lock does to the wizard via
`MainWindow._set_live`. A two-argument `QTimer.singleShot(0, callable)` would
keep a bound method alive past the widget's death and resume a batch into a
locked vault (INV-7).

Between turns the event loop runs, so the UI repaints and a `Cancel` button is
live. Cancel stops the chain; §4.8 says what the report then shows.

### 4.8 Outcomes, and what each one tells the user

`already_imported` is reported when **both** hold: `id_for_span(account_id,
period_start, period_end)` returns non-`None`, **and** the file's cumulative
`new_count` is zero. The span check alone is not enough — a span can exist and
the file still carry new rows, which is the ordinary "the bank re-issued this
month with three more transactions" case, and reporting that as already
imported would be a lie the user acts on.

Per-file report lines, shown on the same table after the run:

| Outcome | Line |
|---|---|
| committed | *53 added, 0 duplicates* — from `ImportResult` |
| `already_imported` | *Already imported — nothing new in this file* |
| `failed` | *Couldn't read this file — <reason>* |
| `skipped` | *Skipped — you didn't supply a password* (or mapping / account) |
| not attempted | *Not imported — the batch was cancelled* |

Failure text reuses the wizard's existing friendly strings, including
`_show_pdf_read_error`'s *"Couldn't read this PDF — try your bank's CSV or OFX
export."*, rather than a second vocabulary for the same errors.

## 5. Invariants

- **INV-1** — A file that fails does not stop the batch: every later file is
  still attempted, and its own outcome records the reason.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV1_failure_does_not_abort_batch`
  — a three-file batch whose middle `commit_import` raises `ValueError` ends
  with files 1 and 3 committed and file 2 `failed`.
  *Breaks when:* the run step lets an exception out of the per-file call, so
  the `QTimer` chain is never re-armed and files 3..N are silently dropped.

- **INV-2** — Each file commits in its own transaction. After a mid-batch
  failure, the earlier files' transactions **and** their `statement_periods`
  rows are present and the failed file has written neither.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV2_per_file_transaction_boundary`
  — the INV-1 vault, re-opened, queried for both tables.
  *Breaks when:* the run is wrapped in an outer `db.py::owned_transaction`,
  whose bare `BEGIN` would in fact raise on the first inner call — the
  invariant names the boundary so the failure is a caught contract breach
  rather than a puzzling SQLite error.

- **INV-3** — No file is committed while any file in the batch is
  `needs_password`, `needs_mapping` or `needs_account`.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV3_no_commit_before_every_question_answered`
  — a batch containing one locked PDF whose prompt is never answered commits
  nothing at all, including the files that were `ready`.
  *Breaks when:* the review step is reachable with an unanswered record, e.g.
  the ASK pass advances on dialog `finished` rather than on an answer.

- **INV-4** — For each `ready` file, the New count shown on the review step
  equals its `ImportResult.inserted_count` after the run, given no change to
  the vault between the two.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV4_reviewed_count_is_the_committed_count`
  — two overlapping CSVs targeting one account, sharing four rows; the review
  shows the second file's four shared rows as duplicates and the sum of the
  two New counts equals the row count in the vault afterwards.
  *Breaks when:* `cumulative_counts` is skipped and `preview.new_count` is
  displayed, which counts each file against the committed vault alone and so
  reports the four shared rows twice.

- **INV-5** — For every file, `match_account` runs before `preview_result`,
  and the account shown on a review row is the account that row's
  `ImportPreview.account_id` targets.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV5_displayed_account_is_the_targeted_account`
  — after changing one row's account through the review table, that file's
  `preview.account_id` equals the displayed account, and its rows land there.
  *Breaks when:* a review-row account change updates the cell without calling
  `ImportService.retarget` — the FIBR-0086 §4.5 wrong-account commit, reached
  through a new door.

- **INV-6** — No batch code path blocks the event loop with a nested dialog
  loop: no `.exec(` token appears in `ui/import_wizard.py` or
  `ui/import_batch.py`.
  *Test:* `tests/features/dialog_lifecycle/test_dialog_lifecycle.py::test_INV1_no_blocking_dialog_exec_in_content_widgets`,
  with `"import_batch.py"` added to its `_FILES` tuple.
  *Breaks when:* the new module is written with `dialog.exec()`, or is created
  and not added to `_FILES` — in which case the guard passes while covering
  nothing, so the test's own tuple is part of the contract.

- **INV-7** — An idle auto-lock during a batch stops it. Files already
  committed stay committed; no further file is attempted; nothing is
  half-written.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV7_autolock_mid_batch_stops_the_run`
  — `MainWindow._lock()` between two files; the vault re-opens with exactly
  the first file's rows.
  *Breaks when:* the chain is armed as `QTimer.singleShot(0, callable)`
  without the context object, so the pending callback survives the widget and
  resumes against a locked vault.

- **INV-8** — A locked PDF is prompted for at most three times, after which
  the file becomes `needs_password` → `skipped` and the batch continues.
  Cancelling the prompt skips that file immediately.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV8_password_attempts_are_bounded`
  — a locked fixture answered wrongly three times leaves one `skipped` file
  and a completed batch.
  *Breaks when:* the re-prompt recurses without a counter, which is exactly
  what `ui/import_wizard.py::_on_pdf_password` does today (§2.3) and what a
  copy-paste of it into the batch would reproduce.

- **INV-9** — Each distinct remembered password is tried at most once per
  file, and only before the user is prompted.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV9_stored_passwords_tried_once_each`
  — three accounts, two holding the same password string; a counting fake
  records two decrypt attempts, not three, and no prompt when one succeeds.
  *Breaks when:* `stored_passwords` returns duplicates, so a shared password
  is tried once per account holding it — invisible on success and a
  quadratic-looking stall on a large account list.

- **INV-10** — `already_imported` is reported only when the period span
  already exists **and** the file's cumulative new count is zero.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV10_reissued_span_with_new_rows_is_not_already_imported`
  — re-importing a statement re-issued with three extra transactions over the
  same dates reports `ready` with three new rows, not `already_imported`.
  *Breaks when:* the check is `id_for_span(...) is not None` alone, which
  reports a re-issue as already-imported and loses the three rows.

- **INV-11** — The batch refuses more than 200 files up front, and stops the
  scan once 200,000 drafts are held, reporting both in plain English rather
  than failing.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV11_batch_caps`
  — 201 synthetic paths are refused before any file is read; a scan crossing
  the draft cap stops with the files scanned so far marked and the rest not
  attempted.
  *Breaks when:* neither cap is enforced and a folder of large PDFs holds
  every preview in memory at once (§10).

- **INV-12** — No real statement data enters the repository with this work:
  every fixture under `tests/features/batch_import/` is synthetic.
  *Test:* `tests/features/account_detect/test_no_real_data.py` covers the
  tracked tree and is extended to the new fixture directory.
  *Breaks when:* a real statement is copied in as a batch fixture — the
  repository is public and `gitleaks` does not detect account numbers.

## 6. Failure modes

**The scan is slow and looks hung.** Thirty large PDFs at a second each is
half a minute. The one-file-per-turn chain (§4.7) keeps the event loop live,
so the review table fills in row by row as files are scanned and the count
advances. There is no separate progress dialog.

**The vault locks mid-scan rather than mid-run.** Nothing has been committed,
so there is nothing to be consistent about: the wizard is destroyed, the
pending callback drops (INV-7), and the user unlocks and starts again.

**A file is both locked and unmappable.** A PDF whose password is supplied and
which then yields no usable table falls to `failed` with the existing
`candidate_tables` message. Its password attempt is not wasted — the
*Remember* tick still stores it against the destination account if one was
settled, so the retry needs no prompt.

**Two files claim the same span in one batch.** The first to commit creates
the `statement_periods` row; the second reuses it via `id_for_span`, so
`period_recorded` is `False` and its rows are stamped to the same period. That
is `commit_import`'s existing behaviour and it is correct — one coverage
period, both files' rows.

**The span check reports a corrected re-issue as already imported.** Only when
the re-issue adds no rows, by §4.8's two-part test. A re-issue that only
*changes* a description — same date, same amount — dedups to zero new rows and
is reported as already imported, which is wrong and is the honest cost of
decision 3. FIBR-0088's content hash is what distinguishes the two files.

**The user cancels mid-run.** Committed files stay committed; the remainder
report *Not imported — the batch was cancelled*. There is no rollback of the
committed prefix, because each file is its own transaction (INV-2) and undoing
one is the Statements tab's existing delete.

**Every file needs an account.** A fresh vault with no `account_number` set on
any account matches nothing (FIBR-0086 §4.4 rule 3), so a first batch is N
account questions. That is the correct behaviour and it is also self-curing:
answering once via the Create affordance stores the number, and the next
month's batch is silent.

## 7. Tests

New directory `tests/features/batch_import/` — `spec.md` plus
`test_batch_import.py`, per `testing.md`. Fixtures are synthetic strings and
generated PDFs, never real statements (INV-12).

| Locks | Test |
|---|---|
| INV-1, INV-2 | `test_INV1_failure_does_not_abort_batch`, `test_INV2_per_file_transaction_boundary` |
| INV-3 | `test_INV3_no_commit_before_every_question_answered` |
| INV-4 | `test_INV4_reviewed_count_is_the_committed_count` |
| INV-5 | `test_INV5_displayed_account_is_the_targeted_account` (`qtbot`) |
| INV-7 | `test_INV7_autolock_mid_batch_stops_the_run` (`qtbot`) |
| INV-8, INV-9 | `test_INV8_password_attempts_are_bounded`, `test_INV9_stored_passwords_tried_once_each` |
| INV-10, INV-11 | `test_INV10_reissued_span_with_new_rows_is_not_already_imported`, `test_INV11_batch_caps` |

INV-6 and INV-12 extend tests that already exist, in their own suites —
`tests/features/dialog_lifecycle/` and `tests/features/account_detect/`
respectively. Neither gets a copy here; a second home for either check is a
second rule that will disagree with the first.

**Every test is seen red before the fix**, per `testing.md`. Three deserve
explicit mutation, because each is a clause that could pass against an
implementation that does not have the property:

- **INV-4** must be watched failing with `cumulative_counts` removed — that
  is, with `preview.new_count` displayed. If it still passes, the two fixture
  files do not actually overlap and the test proves nothing.
- **INV-7** must be watched failing with the two-argument
  `QTimer.singleShot(0, callable)`. If it still passes, the lock is landing
  between the chain's last turn and the assertion rather than mid-run.
- **INV-9** must be watched failing with the de-duplication removed from
  `stored_passwords`. If it still passes, the two accounts do not in fact
  share a password string.

The ripple: `tests/features/dialog_lifecycle/test_dialog_lifecycle.py`'s
`_FILES` gains `"import_batch.py"`, and any `app_shell` assertion counting the
wizard's stack pages moves from three to four.

## 8. Alternatives considered (and rejected)

**A separate batch widget that does not touch the wizard.** Cleaner
separation, and it avoids growing a 1,235-line file. Rejected because an
unfamiliar CSV in a batch needs the map step's entire form, and the choice
would be between duplicating that form or refusing to map CSVs in a batch —
the first is the largest duplication in the codebase, the second contradicts
§3 decision 1.

**A `QThread` batch worker.** The house pattern for slow work, and it would
keep the UI perfectly smooth. Rejected in §4.7: the existing workers touch no
vault, and moving SQLCipher writes to a second thread is a storage-layer
concurrency change that `docs/design.md` § Concurrency explicitly defers.

**Committing the whole batch in one transaction.** Symmetric with
`StatementService.delete_statements`, which does exactly this for the delete
side. Rejected because the ROADMAP bullet requires per-file semantics — one
bad file must not lose 29 good ones — and because `owned_transaction` does not
nest, so it would mean a new batch-aware `ImportService` method reimplementing
`commit_import`'s body.

**Asking each question as its file is reached.** The obvious implementation
and the smallest diff. Rejected by the user (§3 decision 1) for the reason
that motivates the feature: a 30-file import you have to sit through is not
meaningfully better than 30 imports.

**Deriving `already_imported` from `source_filename`.** Already stored, no new
work. Rejected: the same file renamed reads as new, and two banks' `statement.pdf`
read as each other. FIBR-0088 records the same reasoning.

## 9. Out of scope

- Content-hash re-import detection — tracked by **FIBR-0088** (§3 decision 3).
- Fixing the single-file path's pick-step password keying — tracked by
  **FIBR-0249**. §4.4 declines to copy the defect; it does not repair it.
- Per-file coverage-period editing in a batch — §3 decision 4. No roadmap id:
  importing that file singly already works.
- Recursive folder selection. `QFileDialog` selects files, not trees; a
  "choose a folder and take everything in it" entry point is a separate ask
  and nobody has made it.
- Credit-card statement auto-detect — **FIBR-0240**. Those files reach the
  batch as `needs_account`, which is the correct behaviour, not a gap.

## 10. Resource cost

**No new dependency.** No new build target. No schema change.

The one growth is the previews held between the scan and the run: every
`ready` file's `ImportPreview` is live at once, because the review screen
shows them all before anything commits. A `TransactionDraft` measures 224
bytes including its four field objects — measured 2026-08-06 with
`sys.getsizeof` over a representative draft
(`TransactionDraft(1, "2026-01-15", -125000, "WOOLWORTHS SANDTON CITY 4123")`,
summing the instance and its four attributes). The caps in INV-11 bound this:

- **200 files** — well above the 48-file corpus the user actually has.
- **200,000 drafts** ≈ **42.7 MiB** of drafts held at peak.

Both are named constants in `services/batch_import.py`
(`_MAX_BATCH_FILES`, `_MAX_BATCH_DRAFTS`), matching the existing
`_MAX_IMPORT_BYTES` / `_MAX_PDF_ROWS` convention — both of those are
module-level constants in `services/import_.py` and `importers/pdf_importer.py`
respectively, not class attributes, and the new pair follows suit. The per-file
16 MiB read cap still applies to each file and is not relaxed.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/features/batch_import/test_batch_import.py::test_INV1_failure_does_not_abort_batch` |
| INV-2 | `tests/features/batch_import/test_batch_import.py::test_INV2_per_file_transaction_boundary` |
| INV-3 | `tests/features/batch_import/test_batch_import.py::test_INV3_no_commit_before_every_question_answered` |
| INV-4 | `tests/features/batch_import/test_batch_import.py::test_INV4_reviewed_count_is_the_committed_count` |
| INV-5 | `tests/features/batch_import/test_batch_import.py::test_INV5_displayed_account_is_the_targeted_account` |
| INV-6 | `tests/features/dialog_lifecycle/test_dialog_lifecycle.py::test_INV1_no_blocking_dialog_exec_in_content_widgets` (with `_FILES` extended) |
| INV-7 | `tests/features/batch_import/test_batch_import.py::test_INV7_autolock_mid_batch_stops_the_run` |
| INV-8 | `tests/features/batch_import/test_batch_import.py::test_INV8_password_attempts_are_bounded` |
| INV-9 | `tests/features/batch_import/test_batch_import.py::test_INV9_stored_passwords_tried_once_each` |
| INV-10 | `tests/features/batch_import/test_batch_import.py::test_INV10_reissued_span_with_new_rows_is_not_already_imported` |
| INV-11 | `tests/features/batch_import/test_batch_import.py::test_INV11_batch_caps` |
| INV-12 | `tests/features/account_detect/test_no_real_data.py` — **but only for files git tracks, and only when `FINBREAK_CORPUS_NUMBERS` is set**; the guard skips silently otherwise (FIBR-0248) and cannot see git history (FIBR-0247) |
| §3 decision 4 — no period editing in a batch | **nothing** — an absence of UI, which no test asserts; a cold reader of the review step |
| §4.8 report wording | **nothing** — user-facing strings, checked by reading |
| §10 draft-count cap being the *right* number | **nothing** — INV-11 proves the cap is enforced, not that 200,000 is well chosen; revisit if a real batch approaches it |

Fifteen rows, **three** with a bolded `nothing`, plus one heavily qualified.
That is this spec's honest error budget.

## 12. Cross-doc impact

- **`CLAUDE.md`** — module map gains `services/batch_import.py` and
  `ui/import_batch.py`.
- **`CHANGELOG.md`** — one `Added` entry under `[Unreleased]` citing
  FIBR-0085.
- **`ROADMAP.md`** — FIBR-0085 → 🚧 at implementation start, → ✅ at close.
- **`README.md`** — the "what works today" list gains batch import; per the
  standing release rule the whole section is re-verified, not appended to.
- **`docs/specs/FIBR-0086-account-number-auto-detect.md`** — no change. Its
  §4.5 ordering is consumed, not amended; INV-5 restates the consequence for
  the batch path rather than editing FIBR-0086's contract.
- **`docs/design.md`** — no change. § Concurrency's "import runs on the GUI
  thread" survives this work, which is §4.7's whole argument.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
