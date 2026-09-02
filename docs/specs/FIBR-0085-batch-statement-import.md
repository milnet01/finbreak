# FIBR-0085 — Import many statements in one unattended run

**Status:** accepted (2026-08-06).
**Kind:** feature.
**Source:** ROADMAP FIBR-0085 (user-request-2026-07-11, dogfooding v0.1.0).

**Blocked by:** FIBR-0086 (shipped 2026-08-06) — auto-detect is what makes a
multi-file import usable; you cannot hand-map a folder.
**Pairs with:** FIBR-0088 (content-hash re-import detection), which upgrades
this spec's §4.8 `already_imported` signal from a span match to a true file
fingerprint.

**Layman:** Select many bank statements at once — finbreak reads them all,
asks for every password it needs in one go, shows you a single list of what is
about to land in which account, and then imports the lot without you having to
sit there.


> **Split three ways on 2026-08-18** (ROADMAP **FIBR-0267**). This file keeps
> the shared contract and every frozen record; the design and invariants moved
> to two companions under the **same id**:
> [`FIBR-0085-batch-import-service.md`](FIBR-0085-batch-import-service.md) (the
> Qt-free engine, §§ 4.2–4.5) and
> [`FIBR-0085-batch-import-review-step.md`](FIBR-0085-batch-import-review-step.md)
> (the widget, §§ 4.6–4.8).
> **This move is structural, not an amendment: every line in all three files is
> verbatim from the 1376-line original.** No invariant was re-cut, no section
> renumbered and no id changed — which is why each companion's sections and
> invariants start where they do and skip the numbers the other holds. Ids are
> permanent (the [`FIBR-0192-qt-facts.md`](FIBR-0192-qt-facts.md) rule); the
> gaps are the point, not an error. **Same id, deliberately**, so every
> existing `FIBR-0085 §4.n` / `INV-n` citation in code, tests and the ROADMAP
> resolves without being touched.
> The five doc-vs-code defects FIBR-0267 carried were fixed **after** the move,
> in the parts they landed in — see § 13.

**Why the split.** Two `review-contract` loops on the combined document each
found defects in regions the previous loop had never reached — the shape
`spec-format.md` §5.4 calls the size gate, whose remedy is to split along
§3.6's by-concern seams rather than keep looping. 1376 lines against siblings
of ~400–650. **The seam is the module boundary `docs/design.md` already sets**,
not a judgement call: §§ 4.2–4.5 are the headless `services/batch_import.py`
decisions and §§ 4.6–4.8 are `ui/import_batch.py`, and §5's invariants sort
themselves by the test file each already names — `test_batch_import.py` or
`test_batch_import_ui.py`.

**Three files, not two, and the arithmetic is why.** The service half of § 4 is
352 lines against the review step's 190, so moving only the widget out would
have left this file near 1130 — barely inside the gate it was called for. The
shared framing (§§ 1–3, 4.1), the whole-batch sections (§§ 6, 7, 10, 11) and
the frozen records (§§ 13, 14) are what both halves read, so they stay here as
one home rather than being divided.

**Read this first, then the half you are building.** This file owns the goal,
the problem, the scope decisions agreed with the user, **§ 4.1 Where the work
lands** (the module table both halves are cut along), the failure modes, the
test plan, the canonical invariant → test mapping (§ 11), the resource
budget, and the review history of all three files. One home, one copy: where a
rule lives here, the companions cite it rather than restating it.

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

## Contents

**This file** — [1. Goal](#1-goal) · [2. Problem](#2-problem) ·
[3. Scope decisions](#3-scope-decisions-agreed-with-the-user) ·
[4.1 Where the work lands](#41-where-the-work-lands) ·
[5. Invariants](#5-invariants) (INV-12 only) ·
[6. Failure modes](#6-failure-modes) · [7. Tests](#7-tests) ·
[8. Alternatives](#8-alternatives-considered-and-rejected) ·
[9. Out of scope](#9-out-of-scope) · [10. Resource cost](#10-resource-cost) ·
[11. What checks this](#11-what-checks-this) ·
[12. Cross-doc impact](#12-cross-doc-impact) ·
[13. Cold-eyes loop log](#13-cold-eyes-loop-log) ·
[14. As-built deviations](#14-as-built-deviations)

[**The service**](FIBR-0085-batch-import-service.md) — 4.2 The per-file record ·
4.3 Four passes · 4.4 PDF passwords · 4.5 Cumulative dedup ·
INV-1, 2, 4, 9, 10, 11, 13, 15

[**The review step**](FIBR-0085-batch-import-review-step.md) — 4.6 The review
step · 4.7 Driving the passes · 4.8 Outcomes · INV-3, 5, 6, 7, 8, 14
## 1. Goal

A user selects many statement files in one dialog. finbreak reads each one,
works out which account it belongs to, and asks — **before anything is
committed** — for every piece of information it still needs (a PDF password, a
column mapping for an unfamiliar CSV, an account for a file it could not
match). It then shows one review table listing every file, its destination
account, and the number of transactions that will land. On confirmation the
whole batch imports without further interaction, and a per-file report says
what happened. Today the same work is N separate wizard runs.

"Before anything is committed" is the precise claim, and §2.2 shows why the
stronger-sounding "before any work" is impossible.

## 2. Problem

### 2.1 The wizard is one file per run, structurally

`ui/import_wizard.py::ImportWizardWidget` selects a file with
`QFileDialog.getOpenFileName` (singular) and holds each run's state in
instance scalars — `_text`, `_header`, `_source_path`, `_preview`,
`_ofx_statements`, `_pdf_candidates`, `_date_ambiguous`, `_stored_pw`,
`_pending_hint`. One file's worth of everything. `ImportWizardWidget.done` is
a payload-free `Signal()` that `MainWindow._on_import_done` handles by
rebuilding the workspace, so finishing an import tears the screen down.

Three consequences. The third is what INV-1, INV-2 and INV-4 are built on; the
first two are motivation for the feature and carry no invariant, which is
correct — "this is slow" is not a contract:

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
   adds a schema migration and a backfill decision to a UI feature.

4. **The batch does not ask for per-file coverage periods.** The single-file
   preview step exposes two `QDateEdit`s defaulted from the parsed
   min/max dates. The batch passes `preview.period_start` / `preview.period_end`
   unedited. Asking 30 times is exactly the babysitting decision 1 rejects, and
   a statement's own dates are the right answer in every case the corpus
   contains. A file needing a hand-set period is imported singly, which still
   works.

   **Both fields are `str | None`, and the batch has removed the only UI that
   could supply them, so the `None` case is a defined outcome rather than an
   oversight:** a file whose parse yields no dated row becomes `failed` with
   *"No dated transactions found in this file"* and is never handed to
   `commit_import`. Without that rule the file reaches
   `ImportService._validate_span`, whose `date.fromisoformat(None)` raises
   `TypeError`, which it catches and re-raises as
   `ValueError("period endpoints must be valid ISO-8601 dates")` — verified
   2026-08-06 — telling the user their dates are malformed when the file simply
   had none.

5. **The account question is settled on the review screen, not before it.**
   A file whose number matches nothing, matches several, or carries none
   reaches the review table with its account cell reading *— pick one —*; the
   user sets it there, alongside every other file's destination. This is the
   design the user approved, and seeing all destinations together is the point
   of a batch: a file-by-file account prompt is decision 1's babysitting under
   another name. §4.3 therefore routes only **passwords and mappings** through
   the ASK pass — those two block the parse, so they genuinely cannot wait.

6. **The batch never creates an account without being asked**, but it does
   offer. An unmatched row's picker carries a Create affordance prefilled from
   the statement, reusing `ui/account_create.py::CreateAccountDialog`.

## 4. Design

### 4.1 Where the work lands

Three new modules and two extended widgets. The split follows `docs/design.md`'s
layering: orchestration is a service, and the service is headless — so SCAN's
classify/parse/match ladder, `cumulative_counts` (§4.5) and the RUN step are
testable without Qt. **ASK is not, and is not claimed to be**: it is
`PasswordDialog` and the wizard's `_STEP_MAP` page, so it lives in the widget
and reaches the service through the callback signed in §4.3.

**One code move is required for that headless claim to be true.**
`_looks_like_ofx` and `_looks_like_pdf` are `@staticmethod`s on
`ImportWizardWidget`, a `QWidget` subclass — so a headless
`services/batch_import.py` calling them would import the UI layer, inverting
the dependency direction `docs/design.md` sets and making the "testable
without Qt" claim false. Neither touches `self`, so both **move to
`importers/sniff.py`** (new, Qt-free) and the wizard calls them from there.
That is a lift-and-repoint, not a rewrite, and it is listed in the file table
below.

**`AccountPickerDialog` is extended, not reused as it stands** — §3 decision 6
puts a Create affordance in it, which it does not have today. `PasswordDialog`
and `CreateAccountDialog` *are* reused unchanged.

**`ImportService` itself is unchanged.** The list-taking role §2.1 says it
lacks is deliberately *not* added to it — `services/batch_import.py` holds the
per-file loop and calls the existing one-file methods. That keeps
`commit_import`'s single-file transaction boundary exactly as INV-2 requires.

```
src/finbreak/services/batch_import.py   NEW — the orchestration + the record
src/finbreak/ui/import_batch.py         NEW — the review step widget
src/finbreak/importers/sniff.py         NEW — _looks_like_ofx / _looks_like_pdf,
                                        lifted off the widget (below)
src/finbreak/ui/import_wizard.py        EXTENDED — multi-select entry,
                                        the scan/ask/run driver, a 4th step
src/finbreak/ui/account_picker.py       EXTENDED — a Create affordance
```

**The wizard is extended rather than duplicated**, per `coding.md` reuse. The
map step (`_STEP_MAP`) is a large form — five column combos, amount style,
invert, the date-format picker with live preview, the profile-name field — and
an unfamiliar CSV in a batch needs exactly that form. Re-showing the existing
stack page for one file at a time during the ask pass costs nothing;
re-implementing it in a second widget would be the largest duplication in the
codebase.

**Reusing that page has one sharp edge, and it must be handled or the reuse is
a bug.** `_STEP_MAP`'s Cancel is wired straight to `done` — every one of the
wizard's three Cancel buttons is (§2.1) — and `MainWindow._on_import_done`
answers `done` by rebuilding the workspace. So a user who declines the mapping
for *one* file in a thirty-file batch would destroy the entire batch, losing
every answer already given. While the batch drives `_STEP_MAP`, its Cancel is
therefore **re-wired to "decline this file"**: the record becomes `skipped`,
ASK moves to the next question, and `done` is not emitted. INV-14 covers this
alongside the batch step's own Cancel, because they are the same defect
reached from two buttons.

**The entry point, and what a single file does.** `_on_pick_file` swaps
`QFileDialog.getOpenFileName` for `getOpenFileNames` (same name filter, still
`tr()`-wrapped) and routes on the count:

| Selected | Route |
|---|---|
| 0 (cancelled) | nothing; the wizard stays on the pick step, as today |
| 1 | **the existing single-file flow, entirely unchanged** — `_select_file(path)` |
| ≥ 2 | the batch flow (§4.3), landing on `_STEP_BATCH` |

Routing a single file to the old flow is what makes §7's "no existing wizard
test changes" true: all 24 `_stack.currentIndex()` assertions drive one file,
so they keep exercising the same three steps. It is also the better screen — a
one-row review table is worse than the preview it would replace.

**`ui/import_batch.py` must be added to the `_FILES` tuple in
`tests/features/dialog_lifecycle/test_dialog_lifecycle.py`.** That tuple is
literally `("home.py", "rules.py", "statements.py", "import_wizard.py")` —
a new UI module is outside the FIBR-0065 INV-1 guard until it is named there,
and a guard that silently does not cover new code is worse than no guard
(INV-6).


## 5. Invariants

**Fourteen of the fifteen live in the companions**, sorted by the test
file each names: **INV-1, 2, 4, 9, 10, 11, 13, 15** in
[the service](FIBR-0085-batch-import-service.md#5-invariants) and **INV-3,
5, 6, 7, 8, 14** in
[the review step](FIBR-0085-batch-import-review-step.md#5-invariants).
**§ 11 below is the canonical invariant → test mapping and still covers all
fifteen** — that table was not divided.

Only INV-12 is here, because it is the one invariant that is about neither
module: it binds the fixtures and the prose of all three files.

- **INV-12** — No real statement data enters the repository with this work:
  every fixture under `tests/features/batch_import/` is synthetic.
  *Test:* `tests/features/account_detect/test_no_real_data.py`, extended to
  the new fixture directory. **It covers only files git tracks and only when
  `FINBREAK_CORPUS_NUMBERS` is set, skipping silently otherwise** (FIBR-0248),
  and it cannot see git history (FIBR-0247) — so this invariant is
  substantially weaker than its test name suggests, and §11 records that
  rather than the bare pass.
  *Breaks when:* a real statement is copied in as a batch fixture — the
  repository is public and `gitleaks` does not detect account numbers.


## 6. Failure modes

**The scan is slow and looks hung.** The one-file-per-turn chain (§4.7) keeps
the event loop live, and §4.3 puts the table on screen at the start of SCAN, so
it fills in row by row as each file is classified and parsed. A row not yet
reached is `waiting` — its basename, the other columns blank. `Import all`
stays disabled until REVIEW. There is no separate progress dialog; the table is
the progress indicator.

Concretely: thirty PDFs of the size in the user's corpus take on the order of
tens of seconds to scan. That figure is an **estimate, not a measurement** —
no batch exists to time yet — and §10 records what to measure once one does.

**The vault locks mid-scan rather than mid-run.** Nothing has been committed,
so there is nothing to be consistent about: the wizard is destroyed, the
pending callback drops (INV-7), and the user unlocks and starts again.

**A file is both locked and unmappable.** A PDF whose password is supplied and
which then yields no usable table falls to `failed` with the existing
`candidate_tables` message. Its password is **not** stored, because a `failed`
file never settles a destination account and §4.4 writes the password only
against a settled one — so the retry will prompt again. That is the honest
consequence of keying stored passwords to accounts rather than to files; a
file that never reaches an account has nowhere to put it.

**A file has no dated rows at all.** It becomes `failed` at SCAN before any
preview is built (INV-13), because §3 decision 4 removed the `QDateEdit` pair
that is the single-file path's only way to supply a period by hand.

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

New directory `tests/features/batch_import/` — `spec.md` plus **two** test
files, per `testing.md`: `test_batch_import.py` (the headless invariants
against `services/batch_import.py`) and `test_batch_import_ui.py` (the ones
that drive real widgets). The split is the § 4.1 layering made visible; §11
names which invariant lives in which. Fixtures are synthetic strings, and a
`.pdf`-named file plus a fake decrypt in place of any real locked PDF — no
statement bytes of any kind (INV-12).

**§11 is the canonical invariant → test mapping; this section does not repeat
it.** What lives here is what §11's one-line cells cannot carry: which legs a
test needs, which need `qtbot`, and which must be mutation-checked.

**Qt-driven legs.** INV-5, INV-7 and INV-14 drive real widgets and need
`qtbot`. INV-3's second leg (`Import all` disabled) and INV-8 (three prompts)
also reach dialogs: both use a signal-emitting `QDialog` stand-in rather than
the real `PasswordDialog`, following the pattern
`tests/features/dialog_lifecycle/` established when FIBR-0065 converted the
blocking pop-ups — a fake that emits `accepted` is what makes a non-blocking
flow testable at all. INV-1, INV-2, INV-4, INV-9, INV-10, INV-11 and INV-13
are headless against `services/batch_import.py`.

**Every test is seen red before the fix**, per `testing.md`. Four deserve
explicit mutation, because each is a clause that could pass against an
implementation lacking the property:

- **INV-4** must be watched failing twice — once with `cumulative_counts`
  removed entirely, and once with only `new_count` made cumulative. The second
  is the one that matters: it is the shape the spec had before review, and a
  test asserting only the New column would stay green through it.
- **INV-5**'s no-preview leg must be watched failing with `retarget`
  substituted for `preview_result`. If it passes, the fixture's file already
  had a preview and the leg is testing the wrong route.
- **INV-7** must be watched failing with the two-argument
  `QTimer.singleShot(0, callable)`. If it still passes, the lock is landing
  between the chain's last turn and the assertion rather than mid-run.
- **INV-9** must be watched failing with the de-duplication removed from
  `stored_passwords`. If it still passes, the two accounts do not in fact
  share a password string.

**The ripple, and it is smaller than it looks — smaller, as built, than this
section claimed.** `tests/features/dialog_lifecycle/test_dialog_lifecycle.py`
gains `"import_batch.py"` in `_FILES` and `processEvents` in its pattern
(INV-6), and its `spec.md` states both. `tests/features/account_detect/
test_no_real_data.py` needs **no change at all**: it walks `git ls-files` over
the whole tree, so the new directory was already inside its scope the moment it
existed. The point is moot besides — every fixture here is built in `tmp_path`,
so nothing is committed under the directory for it to scan. Corrected on the
as-built pass (§14); the original claim was written from the assumption that
the guard was directory-scoped, and never checked.

**No existing wizard test changes.** There are **24** `_stack.currentIndex()`
assertions across **six** suites — `pdf_import` (10), `import_` (5),
`standard_bank_pdf` (4), `import_date_detect` (2), `ofx_import` (2),
`account_detect` (1) — and `app_shell` has none. Every one asserts an absolute
index. Twenty of the twenty-four assert a literal:

```console
$ grep -rho "_stack.currentIndex() == [0-9]" tests/ | sort | uniq -c
      1 _stack.currentIndex() == 0
     10 _stack.currentIndex() == 1
      9 _stack.currentIndex() == 2
```

The remaining four (all in `standard_bank_pdf`) compare against the wizard's
own `_STEP_PREVIEW` / `_STEP_PICK` constants rather than literals, so they are
safe by construction whatever the numbering.

`_STEP_BATCH = 3` is **appended** after the existing three, so indices 0–2 keep
their meaning and all 24 assertions stay true. Appending rather than inserting
is what makes that so, and is the reason to append.

## 8. Alternatives considered (and rejected)

**A separate batch widget that does not touch the wizard.** Cleaner
separation, and it avoids growing a 1,235-line file. Rejected for the reason
§4.1 gives: an unfamiliar CSV in a batch needs the map step's entire form, and
the alternatives are duplicating it or refusing to map CSVs in a batch.

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

The one growth is the drafts held between the scan and the run: every record's
`ParseResult` **and** its `ImportPreview` are live at once, because the review
screen shows them all before anything commits. **The two do not double the
footprint** — `ImportService._build_preview` constructs its `ImportPreview`
with `drafts=drafts`, the very list handed to it, so `preview.drafts` **is**
`parsed.drafts`: the same list object, not a copy of it and not a second set of
draft objects (verified against source 2026-08-06; the same method's own
comment records that `_dedup` "returns the very draft objects it kept"). The
second structure costs one reference. A `TransactionDraft` measures 224 bytes including its four
field objects — measured 2026-08-06 with `sys.getsizeof` over a representative
draft (`TransactionDraft(1, "2026-01-15", -125000, "WOOLWORTHS SANDTON CITY
4123")`, summing the instance and its four attributes). The caps in INV-11
bound this:

- **200 selected files** — well above the 48-file corpus the user actually has.
- **200,000 drafts** ≈ **42.7 MiB**.

**The true peak is that plus one file's drafts**, because the cap is checked
*before* each file rather than mid-parse: a file begun at 199,999 held drafts
runs to completion. What bounds that last file differs by format, and **CSV is
the loose one**:

| Format | Row bound | Worst-case drafts in one file |
|---|---|---|
| PDF | `_MAX_PDF_ROWS = 100_000` | 100,000 |
| OFX | `_MAX_OFX_TRANSACTIONS = 100_000` (per file, before fan-out) | 100,000 |
| CSV | **none** — only the 16 MiB byte cap | ~335,000 at ~50 bytes/row |

So the peak is ≈ 300,000 drafts (≈ 64 MiB) for a PDF or OFX tail file, and
≈ 535,000 (≈ 114 MiB) for a pathological CSV one. Verified 2026-08-06: the
only `_MAX_*` constant on the CSV path is `_MAX_IMPORT_BYTES`
(`grep -n "_MAX_" services/import_.py importers/csv_importer.py`), so no row
count is derived for it anywhere.

That CSV figure is a **bound, not an expectation** — a real statement is tens
of rows, and the 16 MiB cap already refuses the file sizes that would approach
it. It is stated because §10's job is the honest ceiling, and quoting 64 MiB
while one format can reach 114 MiB would be a number that reads as measured and
is not. Checking mid-parse instead would mean tearing down a half-built
`ParseResult`; the pre-file check is the right trade, stated rather than hidden.

Both are named constants in `services/batch_import.py`
(`_MAX_BATCH_FILES`, `_MAX_BATCH_DRAFTS`), matching the existing
`_MAX_IMPORT_BYTES` / `_MAX_PDF_ROWS` convention — both of those are
module-level constants in `services/import_.py` and `importers/pdf_importer.py`
respectively, not class attributes, and the new pair follows suit. The per-file
16 MiB read cap still applies to each file and is not relaxed.

**Two time costs are bounded by argument rather than by a measured budget, and
both are stated so the first real batch can check them.**

- **`cumulative_counts` re-runs on every review-row account change** (§4.6),
  walking every held draft once: **O(total drafts)**, so at the
  `_MAX_BATCH_DRAFTS` cap it is a single pass over 200,000 tuples on the GUI
  thread. That is a hash-and-compare per draft, not I/O, and it is bounded by
  the cap rather than by the file count.
- **§4.4 tries each distinct stored password once per locked file**: **O(files
  × distinct passwords)** decrypt attempts, and a decrypt is the expensive
  operation here. Distinct passwords is bounded by the account count, which
  this app's users have in single digits — but nothing enforces that, which is
  what INV-9's *Breaks when* means by "a quadratic-looking stall on a large
  account list".

Neither has a numeric budget because there is nothing to measure yet — the
first implementation is the first batch. **What to measure when it exists:** the
`cumulative_counts` wall time at the draft cap, and the decrypt-attempt count on
a folder of locked PDFs. If either bites, the fix is a cached per-account draft
index and a most-recently-successful password ordering, neither of which changes
this contract.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/features/batch_import/test_batch_import.py::test_INV1_failure_does_not_abort_batch` |
| INV-2 | `tests/features/batch_import/test_batch_import.py::test_INV2_per_file_transaction_boundary` |
| INV-3 | `tests/features/batch_import/test_batch_import_ui.py::test_INV3_no_commit_before_every_question_answered` |
| INV-4 | `tests/features/batch_import/test_batch_import.py::test_INV4_reviewed_counts_are_the_committed_counts` |
| INV-5 | `tests/features/batch_import/test_batch_import_ui.py::test_INV5_displayed_account_is_the_targeted_account` |
| INV-6 | `tests/features/dialog_lifecycle/test_dialog_lifecycle.py::test_INV1_no_blocking_dialog_exec_in_content_widgets` (with `_FILES` **and** the token pattern extended) |
| INV-7 | `tests/features/batch_import/test_batch_import_ui.py::test_INV7_autolock_mid_batch_stops_the_run` |
| INV-8 | `tests/features/batch_import/test_batch_import_ui.py::test_INV8_password_prompts_are_bounded` |
| INV-9 | `tests/features/batch_import/test_batch_import.py::test_INV9_stored_passwords_tried_once_each` |
| INV-10 | `tests/features/batch_import/test_batch_import.py::test_INV10_already_imported_is_recomputed_both_ways` |
| INV-11 | `tests/features/batch_import/test_batch_import.py::test_INV11_batch_caps` — the two caps only |
| INV-12 | `tests/features/account_detect/test_no_real_data.py` — **but only for files git tracks, and only when `FINBREAK_CORPUS_NUMBERS` is set**; the guard skips silently otherwise (FIBR-0248) and cannot see git history (FIBR-0247) |
| INV-13 | `tests/features/batch_import/test_batch_import.py::test_INV13_undated_file_fails_before_commit` |
| INV-14 | `tests/features/batch_import/test_batch_import_ui.py::test_INV14_done_waits_for_the_report` |
| INV-15 | `tests/features/batch_import/test_batch_import.py::test_INV15_multi_statement_ofx_fans_out` |
| §4.1 — one selected file routes to the unchanged single-file flow | **nothing** — no test asserts the routing, and the 24 existing `_stack.currentIndex()` assertions stay green either way, so they cannot catch it; only a cold reader of `_on_pick_file` would |
| §4.3 — the ASK callback shape (`next_question` / `answer`) | **nothing** — an interface sketch, not a contract with a failure mode; the invariants constrain the behaviour, not the seam |
| §4.6 — the review table becomes read-only after RUN | **nothing** — no test asserts it; a cold reader, or a user who clicks a committed row |
| §4.6 — File-cell escalation (basename → parent → full path → OFX index) | **nothing** — a display rule with no assertion; caught by reading |
| §3 decision 4 — no period editing in a batch | **nothing** — an absence of UI, which no test asserts; caught only by a cold reader of the review step |
| §4.8 report wording, incl. the two `failed` and two `not_attempted` phrasings | **nothing** — user-facing strings, checked by reading |
| INV-11's cap *messages* being plain English | **nothing** — the test asserts the caps bind and the files are `not_attempted`, not how either is worded |
| §10's two unbudgeted time costs | **nothing** — stated as complexity arguments with a named thing to measure once a real batch exists; no test bounds either |
| §10 draft-count cap being the *right* number | **nothing** — INV-11 proves the cap is enforced, not that 200,000 is well chosen; revisit if a real batch approaches it |

Twenty-four rows — fifteen invariants plus nine unguarded rules — **nine**
with a bolded `nothing`, plus one heavily qualified (INV-12). Counted
2026-08-06 with
`awk '/^## 11\./,/^## 12\./' <this file> | grep -c '^|.*|$'` → 26, less the
header and separator rows.

That is this spec's honest error budget, and it **grew on every review round**
rather than shrinking — three unguarded rules, then six, then eight, then
nine. Every addition was a rule the spec already relied on and had simply never
written down, so the budget was always this size; review made it visible. A
falling count would be evidence of progress only if the rules were becoming
*covered*, and none of these did. Nine is the number an implementer should
read as "these nine things nothing will catch for you".

## 12. Cross-doc impact

- **`CLAUDE.md`** — module map gains `services/batch_import.py`,
  `ui/import_batch.py` and `importers/sniff.py`, and notes that
  `ui/account_picker.py` grew a Create affordance.
- **`CHANGELOG.md`** — one `Added` entry under `[Unreleased]` citing
  FIBR-0085.
- **`ROADMAP.md`** — FIBR-0085 → 🚧 at implementation start, → ✅ at close.
- **`README.md`** — the "what works today" list gains batch import; per the
  standing release rule the whole section is re-verified, not appended to.
- **`tests/features/dialog_lifecycle/spec.md`** — its INV-1 clause names the
  four files and the `.exec(` token; INV-6 changes both (a fifth file, plus
  `processEvents`), so the feature-test contract changes with the test.
- **`docs/specs/FIBR-0086-account-number-auto-detect.md`** — no change. Its
  §4.5 ordering is consumed, not amended; INV-5 restates the consequence for
  the batch path rather than editing FIBR-0086's contract.
- **FIBR-0088**'s spec (when written) and the **FIBR-0249** bullet — no change
  now, but both are cited from §9 as the owners of what this spec defers;
  neither is edited by this work. No filename is given for FIBR-0088's spec
  because the project names specs `docs/specs/<ID>-<topic>.md` and its topic is
  not yet chosen.
- **`docs/design.md`** — no change. § Concurrency's "import runs on the GUI
  thread" survives this work, which is §4.7's whole argument.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 5-split | 2026-08-18 | **none — no reviewer dispatched** | — | — | — | — | Not a review loop. The response to loop 5's stop (ROADMAP **FIBR-0267**, and `spec-format.md` §5.4, whose remedy for a document a cold read stops reaching all of is to split along §3.6's by-concern seams rather than keep looping). **Split three ways, and the arithmetic decided the number.** The bullet's map anticipated two halves along the module seam; measured, the service half of §4 is 352 lines against the review step's 190, so moving only the widget out would have left this file near 1130 and barely moved the gate cost. So the shared framing (§§ 1–3, 4.1), the whole-batch sections (§§ 6, 7, 10, 11) and the frozen records (§§ 13, 14) stay here as one home; §§ 4.2–4.5 and INV-1, 2, 4, 9, 10, 11, 13, 15 went to **[`FIBR-0085-batch-import-service.md`](FIBR-0085-batch-import-service.md)**; §§ 4.6–4.8 and INV-3, 5, 6, 7, 8, 14 went to **[`FIBR-0085-batch-import-review-step.md`](FIBR-0085-batch-import-review-step.md)**. **The invariant allocation was driven by a signal, not a reading**: every INV in §5 already names its own test file, and the split follows it — `test_batch_import.py` to the service, `test_batch_import_ui.py` to the review step. INV-12 alone stayed here, being about neither module. **Every moved line is verbatim**: a script asserted all 27 section boundaries and all 15 invariant boundaries before writing, and then checked that no substantive line of the 1376 was absent from the union of the three — the only misses were the old table of contents, rewritten by design. Section numbers were **not** renumbered, which is why each companion starts where it does; each file carries a note saying how a bare `§4.n` resolves. **Same id**, so every existing `FIBR-0085 §4.n` / `INV-n` citation resolves untouched. 1376 → 705 + 535 + 375, all three inside or near the ~400–650 sibling range; the total grows because each file carries its own front matter and cross-file note, and because the five fixes below added prose. **Then, and only then, loop 5's five findings were fixed in the parts they landed in** — all five re-verified against the tree first, and all five still live: §4.5's vault baseline, §4.6's third clickability test, Close after a cancelled run, the account-change route's REVIEW re-run, and INV-6's unobservable *Breaks when* clause (whose real gap is now stated and filed as **FIBR-0277**). Rows 1–5 above are frozen records of reviews of the combined document and are left as written. |
| 5 | 2026-08-12 | 1 (`review-contract`, cold, rebuilt packet, no prior-loop briefing) | — | — | — | — | **Stopped here deliberately; the amendment converged, the document did not.** Tally **Q1 ×2 · Q2 ×1 · Q3 ×1 · Q4 ×1** — 5 verified, 0 dismissed, **0 fixed, all 5 filed as FIBR-0267**. The loop first confirmed every loop-4 fix held (`_number` blanking all three count columns; `cumulative_counts`' two independent skip tests; the `report_line` clause on exactly two outcomes) and raised **nothing** against the FIBR-0254 amendment, which is the convergence this run owed. What it found instead were five defects in sections no loop-4 lane had reached: §4.5's claim that the vault baseline is read through `ImportService` (the shipped function performs no vault read — the vault half arrives applied in `preview.duplicate_row_numbers`, so building to the spec subtracts it twice and breaks INV-4); §4.6's "exactly" two clickability tests where `_choose_account` applies a third (`_finished or _running`), so the cell would stay live during RUN; Close's behaviour after a *cancelled* run left undefined though it is INV-14's only `done` emitter; §4.6's account-change route naming only `cumulative_counts` where §4.3 requires outcomes re-derived both ways (INV-10's third leg); and INV-6's *Breaks when* clause naming an omission its own test cannot observe. **A fresh cold read reaching fresh regions each pass is the size signal, not a regressing document** — 1357 lines against siblings of ~400–650. Splitting is the fix; another loop on the whole would sample differently again. |
| 4 | 2026-08-12 | 2 (`review-contract`, cold, shared packet, no prior-loop briefing) | — | — | — | — | Severity columns retired upstream; this loop's tally is **Q1 ×2 · Q2 ×2** — 4 verified, 0 dismissed, all fixed; 2 further verified findings filed rather than fixed (below). Run against the FIBR-0254 amendment; both lanes agreed on all four, and none of them was the amendment. §4.5's quoted docstring claimed a `committed`/`failed`/`skipped`/`not_attempted` record "has no preview and is skipped" — false, and the shipped `cumulative_counts` proves it: it skips on `preview is None` **or** `outcome in _TERMINAL`, two independent tests, because a committed record demonstrably has a preview (RUN hands it to `commit_import`). An implementer following the sentence writes the `preview is None` half alone and double-counts committed drafts into later baselines. §4.6 repeated the same error in its clickability gloss ("all of which reach the table with nothing parsed") — false for a RUN-`failed` row and for a cancelled `not_attempted` one, as `_choose_account`'s own comment says. §4.6's Errors column carried a "blank when zero" note the other two count columns also earn (one `_number` helper serves all three). The FIBR-0254 paragraph over-generalised its own rule ("belongs to the row, not to `committed`") while the table grants the clause to two outcomes — now names the carrying set and why the others are excluded. **Filed, not fixed** (both need a behaviour decision, not a wording repair): Cancel-during-SCAN is prescribed two contradictory ways by §4.3 and §4.6 (**FIBR-0265**), and the draft cap's outcome when it trips during ASK-resume is undefined (**FIBR-0266**). At 1357 lines this doc is over the size where a cold read stops reaching everything; loop 1 of this run found six defects in four sections, none in the amendment under review. |
| 3 | 2026-08-06 | 3 (cold, shared packet, no prior-loop briefing) | 1 | 8 | 14 | 10 | 32 verified, 1 dismissed. All 32 fixed. **No loop-1 or loop-2 finding resurfaced.** Dimensions: dim 5×10, dim 7×8, dim 4×7, dim 6×5, dim 10×4, dim 9×3, dim 15×3, dim 1×2, dim 11×2, dim 2×2. All three lanes independently found the same CRITICAL, and it carried three distinct defects: `cumulative_counts`' signature took only the file list yet its docstring named "existing vault rows" as the baseline (unbuildable); its domain said `ready` while §4.3 said "every record with a preview"; and the `ready` reading is circular, since the function runs *before* the outcomes it would filter on are set — and it silently defeats INV-10's retarget leg. Also: reusing `_STEP_MAP` inherits a Cancel wired to `done`, so declining ONE mapping would have torn down a thirty-file batch; §10's memory bound ignored that CSV has no row cap (16 MiB of ~50-byte rows ≈ 335k drafts, so the true ceiling is ≈114 MiB, not 64); INV-4 and INV-1 genuinely trade against each other when an earlier record fails mid-RUN; four `Outcome` members had no display string; the OFX hint source was unstated. **Origin: essentially all collateral from loops 1–2** — the second consecutive collateral-dominated loop, which is the stop trigger. Consolidated the thrice-stated `already_imported` argument to one home. Run STOPPED here by prior agreement, not converged clean. Doc 1149 → 1280 lines. |
| 2 | 2026-08-06 | 3 (cold, shared packet, no prior-loop briefing) | 2 | 8 | 10 | 8 | 28 verified, 0 dismissed. All 28 fixed. **No loop-1 finding resurfaced** — those fixes held. Dimensions: dim 5×9, dim 7×8, dim 4×5, dim 6×4, dim 10×4, dim 9×3, dim 2×2, dim 1×1, dim 11×1. Both CRITICALs were silent-data-loss: a multi-statement OFX (`OfxImporter.parse` returns a **list**) had no place in a one-record-per-file model, so every statement after the first would be discarded without a word — now INV-15 and a `statement_index` fan-out; and REVIEW's `ready → already_imported` flip was one-directional, so retargeting an `already_imported` row left it permanently unimportable because RUN commits only `ready` — now re-derived in both directions each pass. Also: `BatchFile` had no field for the password §4.4 said it "holds"; `exponent` was passed twice and sourced nowhere (it is vault-level `read_minor_unit_exponent`); the headless claim was false because the sniffers are `QWidget` staticmethods (now lifted to `importers/sniff.py`); single-file selection routing was undefined and §7's "no existing wizard test changes" depended on it; `not_attempted` had one wording for three causes; `error_count` never reached the screen, so 40 unparsed rows could vanish behind "10 added". **Origin split: ~8 collateral vs ~4 draft defects** — collateral now dominates 2:1, and lane C counted the `already_imported` rule stated 4× and the both-counts argument 3×, which is where the new contradictions appeared. Consolidated rather than dispatching loop 3. Doc 955 → 1149 lines. |
| 1 | 2026-08-06 | 3 (cold, shared packet) | 3 | 8 | 13 | 11 | 35 verified, 1 dismissed. All 35 fixed. Dimensions: dim 7×6, dim 5×6, dim 2×4, dim 10×5, dim 4×4, dim 6×5, dim 15×4, dim 9×3, dim 1×3, dim 11×3, dim 12×1. Two CRITICALs were design defects no reading caught: the review table's Duplicate column stayed non-cumulative while New became cumulative, so New + Duplicate would not account for a file's rows on the screen the user approves; and `already_imported` was a declared outcome no pass ever assigned. A third resolved a contradiction between §3 decision 5 and §4.3 over *when* the account question is asked — settled by the user's own approved mock-up, which shows an unresolved row on the review screen. Added INV-13 (undated file never reaches `commit_import`; `_validate_span` would have reported malformed dates for a file that had none) and INV-14 (`done` deferred to report dismissal, else `MainWindow._on_import_done` destroys the report table). Self-inflicted collateral caught by 4b-x/4c and fixed in-loop: a duplicated §7 block, a dead TOC anchor, a missing TOC row, a wrong §11 self-count (18 vs 20), and a false ripple claim — `app_shell` has zero stack assertions; the 24 real ones live in six other suites and all survive appending `_STEP_BATCH = 3`. |

## 14. As-built deviations

Written at close, against the shipped code. Each is a place the build differs
from §§ 1–13 above; the sections themselves are left as written, so the
contract and its deviations stay separable.

- **`BatchFile` carries two fields § 4.2 does not list** — `source_text` and
  `mapping`. § 4.3 requires an answered file to "re-enter SCAN at the step that
  stopped it", and § 4.2's record had nowhere to hold that resume state:
  `pending_password` covers a password, nothing covered the already-read text
  or the mapping ASK supplied. Without them an answered mapping re-reads the
  file and re-extracts a PDF's table.

- **`reason` also carries `not_attempted`'s two wordings.** § 4.2 scopes it to
  "user-facing text for failed/skipped", and § 4.8 gives `not_attempted` two
  sentences with no field to tell them apart. The two `failed` wordings needed
  no field: a SCAN failure has no preview and a RUN failure does, which
  distinguishes them exactly.

- **`can_import` gates on every unsettled outcome, not just `needs_account`.**
  § 4.6 states the rule as "at least one `ready` and no file still
  `needs_account`", on the grounds that ASK exhausts the password and mapping
  questions before REVIEW is reached. That was a property of the *flow*, and
  the flow does not hold it: § 6 puts the table on screen from the first scan
  turn and § 4.7 returns to the event loop between turns, so the button was
  live — and pressable — with files still unread. Review found the resulting
  two-chain interleaving as a CRITICAL. The shipped rule is "at least one
  `ready` and nothing still `waiting`, `needs_password`, `needs_mapping` or
  `needs_account`", plus an explicit phase guard in the widget, since a queued
  click can arrive after the button is correctly disabled.

- **`answer` takes the file list.** § 4.3's sketch is `answer(record, value)`;
  the same section requires an answered file to run the ladder "INCLUDING the
  draft-cap check", which needs the batch. § 11 already recorded this signature
  as an interface sketch rather than a contract.

- **`importers/pdf_importer.py` gained `default_table_index`.** § 4.1 lifts
  only the two format sniffers off the wizard. The batch has no table chooser,
  so its SCAN ladder must apply the same "most data rows" rule the wizard's
  `_default_pdf_index` did — moved rather than duplicated (`coding.md` § 1.3).

- **`PasswordDialog` gained an optional `remember_text`.** § 4.4 stores a
  remembered password against the account the file lands on, but a batch must
  title its prompt with the FILE (a thirty-file run has to say which one it is
  asking about). The default label would then have read "Remember this password
  for statement.pdf", promising something the design does not do.

- **§ 7's `test_no_real_data.py` ripple is a no-op**, and § 7 now says so.

- **Two guards the spec does not mention, both added after review found the
  defect they prevent:** SCAN skips a record whose outcome is already terminal
  (without it the § 4.3 file cap was decorative — `build` refused the batch and
  the scan read all 201 files anyway), and the reused `_STEP_MAP` form is reset
  between records (without it one file's "Amounts are reversed" tick silently
  flipped every sign on the next).
