# FIBR-0085 — the batch review step (the table, the driver, the outcomes)

**Status:** accepted (2026-08-06).
**Kind:** feature.
**Source:** ROADMAP FIBR-0085 (user-request-2026-07-11, dogfooding v0.1.0).

**Layman:** This half describes the screen you actually see — the one list of
every selected statement, what is about to land in which account, which rows you
can still retarget, and what each row's final wording means once the run is over.

> **Split out of**
> [`FIBR-0085-batch-statement-import.md`](FIBR-0085-batch-statement-import.md)
> on 2026-08-18 (ROADMAP **FIBR-0267**) — see that file's § 13 Cold-eyes loop
> log for the review history of all three files, which is kept whole there
> rather than divided.
> **This is a structural move, not an amendment: every line below was verbatim
> from that file at the moment of the cut.** No invariant was re-cut and no id
> renumbered — which is why the sections start at 4.6 and the invariants skip
> INV-1, 2, 4, 9, 10, 11, 12, 13 and 15. Ids are permanent; the gaps are the
> point.
> **Same id, deliberately**, so existing `FIBR-0085 §4.6` / `INV-14` citations
> resolve untouched.

**This is the widget half.** Everything here lives in
`src/finbreak/ui/import_batch.py` and the batch driver added to
`src/finbreak/ui/import_wizard.py`; its invariants are the ones whose `*Test:*`
names `tests/features/batch_import/test_batch_import_ui.py` (INV-6 names the
`dialog_lifecycle` guard, which is the same concern: no blocking dialog in a
content widget). The headless half — the record, the four passes, the password
ladder and the cumulative dedup — is
[`FIBR-0085-batch-import-service.md`](FIBR-0085-batch-import-service.md).

**Read this with**
[`FIBR-0085-batch-statement-import.md`](FIBR-0085-batch-statement-import.md).
That file owns the goal, the problem, the scope decisions, **§ 4.1 Where the
work lands** (including the `_STEP_MAP` Cancel re-wiring this half's INV-14
covers), the failure modes, the test plan, the canonical invariant → test
mapping (§ 11), the resource budget and every frozen record. One home, one
copy: where a rule lives there, this file cites it rather than restating it.

**How a bare `§4.n` resolves.** The moved text is verbatim, so it still cites
sections by number alone. Unless another spec is named in the same breath (a
`FIBR-0086 §4.5` means that spec's), a `§4.n` is FIBR-0085's and lives in:
**§§ 1–3, 4.1, 6–14** →
[`FIBR-0085-batch-statement-import.md`](FIBR-0085-batch-statement-import.md) ·
**§§ 4.2–4.5** →
[`FIBR-0085-batch-import-service.md`](FIBR-0085-batch-import-service.md) ·
**§§ 4.6–4.8** →
[`FIBR-0085-batch-import-review-step.md`](FIBR-0085-batch-import-review-step.md).
Numbers were not rewritten on purpose: renumbering is what would have broken the
existing citations this split was shaped to preserve.

**Contents:** [4.6 The review step](#46-the-review-step) ·
[4.7 Driving the passes](#47-driving-the-passes-with-no-nested-event-loop) ·
[4.8 Outcomes](#48-outcomes-and-what-each-one-tells-the-user) ·
[5. Invariants](#5-invariants) (INV-3, 5, 6, 7, 8, 14)

## 4. Design
### 4.6 The review step

A fourth stack page, `_STEP_BATCH = 3`, holding an `ui/import_batch.py`
`BatchReviewWidget`. One `QTableWidget`, objectName `"import_batch_table"` so
it gets its own `columns/import_batch_table` key under
`ui/_table_state.py::remember_columns` (the FIBR-0012 lesson: two unnamed
tables share one key and cross-corrupt widths).

| Column | Content |
|---|---|
| File | an escalating label — see *Rows can share a basename* below |
| Account | the destination account's name, or *— pick one —* |
| New | `BatchFile.new_count` (§4.5, cumulative) |
| Duplicate | `BatchFile.duplicate_count` (§4.5, cumulative) |
| Errors | `BatchFile.error_count` |
| Status | the `Outcome`, rendered per §4.8 — including `waiting` before SCAN reaches the row |

**All three count columns render blank at zero**, not `0` — one helper serves
New, Duplicate and Errors — so a number in any of them draws the eye only when
it matters.

**Rows can share a basename**, two ways: `statement.pdf` from two folders (§8
rejects filename-based duplicate detection for exactly this reason), and the
several statements fanned out of one OFX file, which share a path outright.
The File cell therefore renders, in order of escalation: the basename; the
basename prefixed with its parent directory when that disambiguates; otherwise
the **full path**. A fanned-out OFX statement always appends its index —
`bank.ofx [2 of 3]` — since no path prefix can separate siblings from the same
file. The full path is the tooltip on every row regardless.

**Setting an account.** Three tests gate the Account cell, and all three are
needed. Two are about the record: its **`parsed` is not `None`** and its
**outcome is not terminal** (`committed`, `failed`, `skipped`,
`not_attempted` — the `TERMINAL_OUTCOMES` set §4.5 skips on, so the rule has
one definition). The third is about the batch, not the row: **the cell is dead
while the batch is running and once it has finished** (`self._running` /
`self._finished`), which is stated here because it is not derivable from the
other two — during RUN a not-yet-reached record is still `ready` with a
preview, so both record tests pass and the cell would be live. Retargeting a
row the chain is about to reach re-dedups it against a vault that is changing
underneath it. The two record tests are independent and both are needed:
`waiting` is excluded by the parse test alone, but `parsed` alone would
leave `failed` and `not_attempted` rows clickable — `_settle_parse` stores the
parse *before* the undated check fails a record, and a `not_attempted` row was
`ready` when a cap or a cancel stopped the batch, so both carry one. (An earlier
gloss said "every row except `failed`", which is false and would hand
`preview_result` a `None`; and without the terminal half a user could retarget a
row after the run and silently re-dedup against
rows that are already in the vault.) **The whole table becomes read-only once
RUN finishes** — at that point it is the report, not a form. The cell
opens `AccountPickerDialog` with the Create affordance of §3 decision 6. Which
call follows depends on whether a preview exists yet, and the two are not
interchangeable:

- **No preview** (the row was `needs_account`): `preview_result(parsed,
  account_id)` builds the first one, and the row leaves `needs_account` — the
  REVIEW re-run below is what decides whether it lands on `ready` or on
  `already_imported`.
  `ImportService.retarget` cannot be used here — it takes an `ImportPreview`
  and there is none.
- **A preview exists** (the user is changing an already-settled row):
  `ImportService.retarget(preview, account_id)`, whose returned preview
  replaces the stored one.

Either way the **whole batch is then re-reviewed** — the §4.3 REVIEW pass,
`BatchImportService.review(files)` — because one row's destination changes
which rows every *other* row in that account may claim.

**Re-running `cumulative_counts` alone is not enough**, and naming only it here
is how that mistake gets built. REVIEW re-derives every record's outcome **in
both directions**: counts change, so a retargeted row must be able to move from
`already_imported` back to `ready` (INV-10's third leg) *and* from `ready` to
`already_imported`. Recomputing the counts without re-deriving the outcomes
leaves a retargeted row displaying fresh numbers under a stale verdict — and a
row stuck at `already_imported` can never be imported, however many new rows it
now has.

**The review step's three controls**, so abandonment is defined rather than
implied: **Import all** starts RUN; **Cancel** abandons — before RUN it drops
the whole batch (every held password discarded unwritten, §4.4) and returns to
the pick step *without* emitting `done`, during RUN it stops the chain; and
**Close** appears only once RUN has finished, and is the one control that
emits `done` (INV-14).

**A cancel during RUN counts as finished, and Close appears.** The remaining
records become `not_attempted`, the report stands with everything already
committed still committed, and the screen ends in exactly the state a run that
reached the last file ends in. That has to be said, because "once RUN has
finished" does not obviously cover a run that was stopped: Close is the only
emitter of `done` (INV-14), so reading it the other way strands the user on a
screen with no exit. A cancel *before* RUN needs no Close — the batch screen
is gone, the wizard having returned to the pick step.

`Import all` is enabled iff at least one file is `ready` **and no file is still
`needs_account`** — the second half is what makes §3 decision 5's
review-screen account question a gate rather than a suggestion (INV-3). Files
that are `failed`, `skipped` or `already_imported` do not block it: they stay
listed with their reason and are simply not committed — they are the report,
not an obstacle.

### 4.7 Driving the passes with no nested event loop

The scan and the run are loops over slow, blocking work — `pikepdf` decrypt,
`pdfplumber` extraction, a write transaction. Two mechanisms are ruled out
before any are chosen:

- **A modal `QProgressDialog` is forbidden.** Qt's documented modal pattern
  calls `processEvents()` to stay responsive, and re-entrancy is exactly the
  FIBR-0065 crash class: an idle auto-lock fires inside the nested loop,
  `MainWindow._lock()` destroys the widget, and the code after the loop reads
  a deleted C++ object.
  Source: <https://doc.qt.io/qt-6/qprogressdialog.html>

  **Only half of that is mechanically enforced today, and the spec should not
  claim otherwise.** `tests/features/dialog_lifecycle/` INV-1 greps for
  `\.exec\(`, which catches `dialog.exec()` and `progress.exec()` — but a
  modal `QProgressDialog` driven by a bare `QApplication.processEvents()` loop
  carries no `.exec(` token and would pass that grep untouched. INV-6
  therefore extends the guard to the `processEvents` token as well, which is
  what turns this bullet into a mechanical refusal rather than a preference.
  `processEvents` appears nowhere under `src/` today, so the extended guard
  starts green.
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

`already_imported` is the two-part outcome §4.3's REVIEW block derives, both
ways, on every pass. The rule and the argument for it live there; this section
only says how each outcome reads on screen.

Per-file report lines, shown on the same table after the run. Every row is one
`Outcome` member (§4.2), so the Status column needs no second vocabulary:

| Outcome | Line |
|---|---|
| `committed` | *53 added, 0 duplicates* — from `ImportResult`; the unreadable-row clause below appended when `error_count > 0` |
| `already_imported` | *Already imported — nothing new in this file*, plus the same unreadable-row clause when `error_count > 0` |
| `failed` (at SCAN) | *Couldn't read this file — <reason>* |
| `failed` (at RUN) | *Couldn't import this file — <reason>* |
| `skipped` | *Skipped — we couldn't unlock this file* (or *…no column mapping was set*) |
| `not_attempted` (cancelled) | *Not imported — the batch was cancelled* |
| `not_attempted` (cap) | *Not imported — the batch reached its size limit* |
| `waiting` | *Waiting…* — before SCAN reaches the row |
| `ready` | *Ready to import* |
| `needs_password` | *Locked — we'll ask for the password* |
| `needs_mapping` | *Needs its columns matched up* |
| `needs_account` | *Pick an account* |

All ten members appear here, because §4.6's Status column renders the outcome
and a row sits in one of the middle four for the whole of ASK and REVIEW. An
outcome with no string is a blank cell on screen.

**The unreadable-row clause is carried by `committed` and `already_imported`,
and by no other outcome** (FIBR-0254). `error_count` is set during SCAN, before
any outcome is known, and §4.6's Errors column renders it for every outcome — so
a clause appended on `committed` alone let an `already_imported` row read
*"nothing new in this file"* beside a cell reading 4, one row contradicting
itself. Those two are exactly the outcomes whose line reports a **result** and
would otherwise say nothing about the rows that were dropped. Every other
outcome carries its `reason` instead, which already explains the row; a
`failed`, `skipped` or `not_attempted` line is not made truer by appending a
count the Errors cell is already showing. It is spelled *", 1 row couldn't be
read"* for a single row and *", N rows couldn't be read"* above one: two strings
rather than a Qt `%n` plural, because no translation is loaded yet (FIBR-0017)
and an untranslated `%n` renders its source text, giving *"1 row(s)"*.

**Two outcomes carry two wordings each, for the same reason: each is reachable
from two passes, and one sentence cannot serve both.**

- `failed` — a SCAN failure genuinely could not read the file, whereas INV-1's
  failure is a `ValueError` out of `commit_import` on a file that read
  perfectly. Telling a user their file was unreadable when the commit rejected
  its span sends them to fix the wrong thing.
- `not_attempted` — a cancelled run and a cap-stopped scan are different
  events, and "the batch was cancelled" is simply false for a user who
  selected 201 files and cancelled nothing.

The record's `reason` carries the underlying message in every case.

**`skipped` never says "you didn't supply a password"**, because INV-8 also
reaches `skipped` after three *wrong* passwords — where the user supplied
three and none worked. *"We couldn't unlock this file"* is true of both routes.

SCAN failure text reuses the wizard's existing friendly strings, including
`_show_pdf_read_error`'s *"Couldn't read this PDF — try your bank's CSV or OFX
export."*, rather than a second vocabulary for the same errors.

**The report is shown before the screen is torn down.** `ImportWizardWidget`
signals completion with a payload-free `done`, which `MainWindow._on_import_done`
handles by rebuilding the workspace — so emitting `done` at the end of RUN would
destroy the very table the report is written into. The batch therefore emits
`done` only when the user dismisses the report (a `Close` button on the review
step), not when the last file commits.


## 5. Invariants

The six this half owns. **INV-1, 2, 4, 9, 10, 11, 13 and 15** live in
[the service](FIBR-0085-batch-import-service.md#5-invariants) and **INV-12** in
[the shared file](FIBR-0085-batch-statement-import.md#5-invariants); none is
restated here.

- **INV-3** — No file is committed while any file in the batch is
  `needs_password`, `needs_mapping` or `needs_account`. The first two are
  exhausted by ASK; the third disables `Import all` in REVIEW (§4.6).
  *Test:* `tests/features/batch_import/test_batch_import_ui.py::test_INV3_no_commit_before_every_question_answered`
  — two legs, because the two halves are enforced by different mechanisms: a
  batch containing one locked PDF whose prompt is **left open** commits nothing
  at all, including the records that were `ready`; and a batch reaching REVIEW
  with one `needs_account` row has `Import all` disabled. ("Left open" is the
  distinction from a *declined* prompt, which becomes `skipped` and does not
  block the batch — §4.6.)
  *Breaks when:* ASK advances on dialog `finished` rather than on an answer;
  or `Import all` is gated on "at least one `ready`" alone, which is true
  while another row still has no destination.

- **INV-5** — For every file, `match_account` runs before the **first** preview
  is built, and the account shown on a review row is the account that row's
  `ImportPreview.account_id` targets — including after the user changes it. (A
  later `retarget` builds a replacement preview with no fresh `match_account`
  call, which is correct: the user's explicit choice outranks the statement.)
  *Test:* `tests/features/batch_import/test_batch_import_ui.py::test_INV5_displayed_account_is_the_targeted_account`
  — three legs, one per route into a destination: a matched file, a
  `needs_account` file given an account on the review screen (which builds its
  first preview via `preview_result`), and an already-`ready` file changed on
  the review screen (which goes through `retarget`). In each, that file's
  `preview.account_id` equals the displayed account and its rows land there.
  *Breaks when:* a review-row account change updates the cell without
  re-pointing the preview — the FIBR-0086 §4.5 wrong-account commit reached
  through a new door — or when the no-preview route calls `retarget`, which
  takes an `ImportPreview` and has none to take.

- **INV-6** — No batch code path blocks the event loop, by a nested dialog
  loop **or** by pumping events inside one: neither a `.exec(` nor a
  `processEvents` token appears in any file of the dialog-lifecycle guard's
  `_FILES` set, which this work extends from four members to five by adding
  `ui/import_batch.py`. (The guard binds the whole set, not just the two
  files this spec touches — extending the pattern tightens it for
  `home.py`, `rules.py` and `statements.py` too, which is free and correct.)
  *Test:* `tests/features/dialog_lifecycle/test_dialog_lifecycle.py::test_INV1_no_blocking_dialog_exec_in_content_widgets`,
  with `"import_batch.py"` added to its `_FILES` tuple and `processEvents`
  added to its `_EXEC` pattern.
  *Breaks when:* the new module is written with `dialog.exec()`; or a modal
  `QProgressDialog` is driven by a bare `QApplication.processEvents()` loop,
  which carries no `.exec(` token and so passes the unextended grep while
  re-entering the event loop exactly as FIBR-0065 forbids. Both the tuple and
  the pattern are part of the contract.
  *Not observable by this test, stated rather than implied:* a UI module
  created and never added to `_FILES`. The test iterates `_FILES`, so an
  omitted file is not a failing case but an absent one — the guard passes
  while covering nothing, and no run reports it. Nothing mechanical catches
  that today, which is why adding `import_batch.py` to the tuple is part of
  this spec's deliverable rather than something a red test will demand of the
  implementer. Filed as **FIBR-0277**.

- **INV-7** — An idle auto-lock during a batch stops it. Files already
  committed stay committed; no further file is attempted; nothing is
  half-written.
  *Test:* `tests/features/batch_import/test_batch_import_ui.py::test_INV7_autolock_mid_batch_stops_the_run`
  — `MainWindow._lock()` between two files; the vault re-opens with exactly
  the first file's rows.
  *Breaks when:* the chain is armed as `QTimer.singleShot(0, callable)`
  without the context object, so the pending callback survives the widget and
  resumes against a locked vault.

- **INV-8** — A locked PDF raises at most three **user prompts**, after which
  the file becomes `skipped` and the batch continues. Cancelling a prompt
  skips that file immediately. ("Prompt" throughout, never "attempt" — §4.4's
  automatic tries against stored passwords are attempts and are bounded
  separately by INV-9.)
  *Test:* `tests/features/batch_import/test_batch_import_ui.py::test_INV8_password_prompts_are_bounded`
  — a locked fixture answered wrongly three times leaves one `skipped` file
  and a completed batch.
  *Breaks when:* the re-prompt recurses without a counter, which is exactly
  what `ui/import_wizard.py::_on_pdf_password` does today (§2.3) and what a
  copy-paste of it into the batch would reproduce.

- **INV-14** — The post-run report survives until the user dismisses it:
  `ImportWizardWidget.done` is emitted only by the report's Close — never at
  the end of RUN, never by the batch step's Cancel, and never by the
  `_STEP_MAP` Cancel while the batch is driving that page.
  *Test:* `tests/features/batch_import/test_batch_import_ui.py::test_INV14_done_waits_for_the_report`
  — a `qtbot` spy on `done` records zero emissions after the last record
  commits, zero after Cancel stops a running batch, and zero after declining a
  mapping mid-batch; then exactly one after Close is clicked.
  *Breaks when:* RUN emits `done` when the last record commits — which is what
  the single-file `_on_import` does, so it is the natural thing to copy — or
  either Cancel stays wired to `done` as all three existing steps' Cancel
  buttons are (§2.1). The `_STEP_MAP` case is the worst of the three, because
  it is reached by *reusing* that page: declining the mapping for one file in a
  thirty-file batch would tear down the whole batch and every answer already
  given. In each case `MainWindow._on_import_done` rebuilds the workspace and
  destroys the table the report was about to be written into, and §6's "the
  remainder report *Not imported — the batch was cancelled*" becomes
  unobservable.
