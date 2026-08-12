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

## Contents

- [1. Goal](#1-goal) · [2. Problem](#2-problem) ·
  [3. Scope decisions](#3-scope-decisions-agreed-with-the-user)
- [4. Design](#4-design) — [4.1 Where the work lands](#41-where-the-work-lands) ·
  [4.2 The per-file record](#42-the-per-file-record) ·
  [4.3 Four passes](#43-four-passes) ·
  [4.4 PDF passwords](#44-resolving-a-pdf-password-with-no-pick-step-account) ·
  [4.5 Cumulative dedup](#45-cumulative-dedup--the-reviewed-number-is-the-number-that-lands) ·
  [4.6 The review step](#46-the-review-step) ·
  [4.7 Driving the passes](#47-driving-the-passes-with-no-nested-event-loop) ·
  [4.8 Outcomes](#48-outcomes-and-what-each-one-tells-the-user)
- [5. Invariants](#5-invariants) · [6. Failure modes](#6-failure-modes) ·
  [7. Tests](#7-tests) · [8. Alternatives](#8-alternatives-considered-and-rejected)
- [9. Out of scope](#9-out-of-scope) · [10. Resource cost](#10-resource-cost) ·
  [11. What checks this](#11-what-checks-this) ·
  [12. Cross-doc impact](#12-cross-doc-impact) ·
  [13. Cold-eyes loop log](#13-cold-eyes-loop-log) ·
  [14. As-built deviations](#14-as-built-deviations)

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
   adds a v13 → v14 migration and a backfill decision to a UI feature.

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

### 4.2 The per-file record

`ImportPreview` carries no filename, no format and no hint — a batch has to
keep its own association. One **mutable** record per selected file (every field
but `path` is written as the passes advance), in `services/batch_import.py`:

```python
# --- services/batch_import.py ----------------------------------------------

Outcome = Literal[
    "waiting",           # selected, not yet reached by SCAN  (initial value)
    "ready",             # parsed, account known, will commit
    "already_imported",  # span exists and zero new rows (§4.8); set in REVIEW
    "needs_password",    # a locked PDF, no working password yet
    "needs_mapping",     # a CSV whose header matches no saved profile
    "needs_account",     # parsed, but match_account did not resolve one
    "failed",            # unreadable / unparseable / no dated rows; see `reason`
    "skipped",           # the user declined, or three prompts were exhausted
    "committed",         # RUN completed it; `result` carries the counts
    "not_attempted",     # a cap stopped SCAN, or cancel stopped RUN, before it
]


@dataclass
class BatchFile:
    """One selected file — or one STATEMENT within a multi-statement OFX —
    from selection through to its committed result."""

    path: str                                   # full path; basename for display
    outcome: Outcome = "waiting"
    statement_index: int | None = None          # OFX fan-out (below); else None
    parsed: ParseResult | None = None           # kept: the account may be set later
    preview: ImportPreview | None = None        # None until an account is known
    hint: SourceAccountHint | None = None       # ParseResult.source_account
    account_id: int | None = None               # the destination, once settled
    reason: str = ""                            # user-facing text for failed/skipped
    pending_password: str | None = None         # §4.4 — held, not yet written
    remember_password: bool = False             # §4.4 — the dialog's tick
    result: ImportResult | None = None          # None until committed
    new_count: int = 0                          # §4.5 cumulative
    duplicate_count: int = 0                    # §4.5 cumulative
    error_count: int = 0                        # unparseable ROWS (below)
```

**All ten `Outcome` members are reachable**, and the Status column (§4.6)
renders exactly this field — there is no second, derived vocabulary anywhere,
including for the pre-scan state. Who writes what, named rather than counted:

| Written by | Outcomes |
|---|---|
| initial value | `waiting` |
| SCAN | `ready`, `needs_password`, `needs_mapping`, `needs_account`, `failed` |
| ASK | `skipped` (declined or three prompts exhausted) |
| REVIEW | `ready` ⇄ `already_imported`, re-derived every pass |
| RUN | `committed`, and `failed` on a raised exception |
| SCAN **or** RUN | `not_attempted` — a cap stopped the scan, or cancel stopped the run |

**Two outcomes have two writers each**, `failed` and `not_attempted`, which is
exactly why §4.8 gives each of them two wordings: the same outcome reached from
two passes means two different things to the user.

**`error_count` is carried because the review table would otherwise hide it.**
`ImportPreview.errors` holds the rows that could not be parsed, and a file
where 40 of 50 rows failed commits 10 and would report *"10 added"* with no
hint that 40 vanished. In a money app a silently dropped row is the defect, so
the count reaches the screen (§4.6) and the report (§4.8).

**One `BatchFile` per statement, not per file.** `OfxImporter.parse` returns
`[(OfxAccountInfo, ParseResult), ...]` — a single OFX file can carry several
statements, each potentially for a *different* account, which is exactly why
the wizard already keeps `_ofx_statements` as a list. SCAN therefore **fans a
multi-statement OFX out into one record per statement**, sharing `path` and
numbering them in `statement_index` (0-based, `None` for every other format).
Consequences, all deliberate: each statement gets its own account, its own
preview and its own review row; the File column disambiguates them (§4.6); and
`_MAX_BATCH_DRAFTS` counts their drafts individually while `_MAX_BATCH_FILES`
still counts *selected files*, because that is the number the user chose.
Taking only the first statement was rejected — it silently discards the rest.

**`OfxAccountInfo` is destructured and discarded; the hint comes from
`parsed.source_account`.** `OfxImporter` already sets
`source_account = SourceAccountHint(account.account_id)` per statement when
that id is non-empty, so each fanned-out `ParseResult` carries its own account
identity and INV-15's "matched to two different accounts" runs through exactly
the same `match_account(parsed.source_account, accounts)` call as CSV and PDF.
Reading `info` instead would be a second seam for a hint that already exists —
the one thing FIBR-0086 §4.1 built `SourceAccountHint` to prevent. (`info`'s
`account_type` is the only field with no home, and prefilling from it is
deferred as FIBR-0243.)

**`parsed` is kept deliberately.** §3 decision 5 settles the account on the
review screen, so a `needs_account` row arrives there with a `ParseResult` and
no `ImportPreview` — and `ImportService.retarget` takes an `ImportPreview`, so
it cannot be the call that first targets one. §4.6 says which call is.

Both counts are **cumulative** and neither is read from the preview: a preview
dedups against committed rows only, which is the whole of §4.5.

The batch is an ordinary list, ordered by **`(path, statement_index)`**, and
that order is the commit order. It is sorted rather than taken as the dialog
returned it because `QFileDialog`'s selection order is not a defined sort, and
INV-4's reproducibility depends on two runs over the same files claiming rows
in the same order. `statement_index` breaks the tie within one OFX file, whose
statements share a path.

### 4.3 Four passes

`exponent` below is the vault's base-currency minor-unit exponent, read **once
per batch** as `read_minor_unit_exponent(vault.connection)`
(`services/transactions.py`). It is a vault-level setting, not per-account, so
it is settled before SCAN starts and is unaffected by §3 decision 5 moving the
account question to REVIEW.

```
SCAN   refuse the batch before reading anything, if
           len(selected_files) > _MAX_BATCH_FILES                  (INV-11)
       every record starts `waiting`; the table is already on screen (§6)
       for each file, in path order:
         if drafts held so far >= _MAX_BATCH_DRAFTS                (INV-11)
             -> this and every later record become `not_attempted`; stop
         classify by extension/sniff  (importers/sniff.py: looks_like_ofx /
                                       looks_like_pdf — §4.1)
         PDF  -> decrypt (§4.4); locked -> needs_password, stop this file
                 StandardBankImporter.parse(pdf_bytes, exponent, password)
                     -> ParseResult, or None if not a recognised SB statement
                 None -> PdfImporter.candidate_tables(...) + table_to_text(...)
                         then the CSV ladder below on that text
         OFX  -> OfxImporter.parse(data, exponent) -> [(info, ParseResult), ...]
                 FAN OUT: one record per statement, statement_index 0..N-1 (§4.2)
                 the hint is `parsed.source_account`, exactly as for every other
                 format — `info` is NOT the seam (below)
         CSV  -> match_profile(header); no match -> needs_mapping, stop this file
                 CsvImporter().parse(text, mapping, exponent) -> ParseResult
         store it as `parsed`; error_count = len(parsed.errors)
         if parsed.period_start is None OR parsed.period_end is None
             -> failed, "No dated transactions found in this file"
                                                          (§3 decision 4)
         match_account(parsed.source_account, accounts)
             matched   -> account_id set; preview_result(parsed, account_id)
                          -> preview; outcome `ready`
             otherwise -> needs_account   (no preview yet — §4.2)

ASK    passwords and mappings ONLY (§3 decision 5), one file at a time:
         needs_password -> PasswordDialog, at most 3 PROMPTS (INV-8)
         needs_mapping  -> the existing _STEP_MAP page for that file
       an answered file re-enters SCAN at the step that stopped it — a
       password resumes at decrypt, a mapping at CsvImporter().parse — and
       runs the rest of the ladder, INCLUDING the draft-cap check;
       a declined or exhausted file becomes `skipped`

REVIEW on entry and after EVERY account change, re-evaluate the whole batch:
         cumulative_counts(files, imports)
                                    sets new_count + duplicate_count on every
                                    record with a preview (NOT only `ready` —
                                    the outcomes below are not set yet)
         for each record with a preview, set outcome in BOTH directions:
             `already_imported`  when id_for_span(account_id, period_start,
                                      period_end) is not None
                                      AND new_count == 0            (§4.8)
             `ready`             otherwise
       records still `needs_account` keep that outcome; Import all stays off
       No commit has happened yet.

RUN    for each `ready` record, in (path, statement_index) order:
         commit_import(preview, preview.period_start, preview.period_end, path)
             -> ImportResult, stored on the record; outcome `committed`
         (ValueError, FinbreakError) -> `failed` + its message; CONTINUE (INV-1)
       on cancel, every record not yet reached -> `not_attempted` (cancelled)
```

**The caught set is `(ValueError, FinbreakError)`** — the same pair the
single-file `_on_import` catches, not a bare `except Exception`. `coding.md`
§2 forbids the broad form, and the narrow one is what makes INV-1 a contract
rather than a swallow: an unexpected exception type still escapes and is a bug,
where "continue past anything" would hide one behind a per-file report line.

**Cancel during SCAN behaves the same way as during RUN**: every record not yet
reached becomes `not_attempted` with the cancelled wording. Without that rule a
cancelled scan would strand rows reading *Waiting…* forever, which §4.8 says is
a state seen only while SCAN is running.

**Ordering is `(path, statement_index or 0)`** — `statement_index` is
`int | None`, and sorting a mixed `None`/`int` column raises `TypeError` in
Python 3. Coalescing to 0 is safe because the only records that share a `path`
are an OFX file's own statements, which all carry an `int`.

**The REVIEW re-evaluation is two-directional, and that is load-bearing.** A
one-way `ready → already_imported` flip looks equivalent and silently loses
data: the user retargets a row that was `already_imported` under the wrong
account, its rows are genuinely new under the right one, but nothing moves it
back to `ready` — and RUN commits only `ready` records, so the file is
dropped without a word. Re-deriving both outcomes from scratch on every pass is
the shortest rule that cannot do that, and it is why the flip is expressed as
*set the outcome* rather than *demote when*.

`commit_import`'s arguments are spelled out because all four are load-bearing:
the period pair is §3 decision 4's parsed default (its `None` case is already
`failed` at SCAN, so the values reaching here are `str`), and `path` is the full
path — `commit_import` stores `Path(source_filename).name` itself.

**Passwords and mappings block the parse; an account does not.** That is the
whole reason ASK carries the first two and REVIEW carries the third: a file
cannot be read at all without its password or mapping, whereas a parsed file is
merely waiting to be told where it goes. **No file is committed while any file
is `needs_password`, `needs_mapping` or `needs_account`** — the first two are
exhausted by ASK, the third gates `Import all` in REVIEW (INV-3).

**The ASK callback**, the one seam between the widget and the headless service:

```python
# services/batch_import.py — the service ASKS; the widget ANSWERS.
Answer = str | ColumnMapping | None          # password | mapping | declined

def next_question(files: Sequence[BatchFile]) -> BatchFile | None:
    """The next record needing a password or a mapping, or None when ASK is
    exhausted. Pure — it reads outcomes, it does not show anything."""

def answer(record: BatchFile, value: Answer) -> None:
    """Apply the user's response: None declines (-> `skipped`), otherwise
    resume SCAN at the step that stopped this record (§4.3)."""
```

The seam is **inverted rather than asynchronous** — the widget pulls a question,
shows the dialog, and pushes the answer back from its slot. An `await`-shaped
callback is what a reader reaches for first and it cannot work here: the
non-blocking dialog contract (§4.7) means `show_modal` returns immediately and
the answer arrives on a signal, so there is nothing to await inside a Qt slot.
This shape keeps every decision in the service and every `QDialog` in the
widget, with no Qt import on the service side.

**A CSV that matches a saved profile but parses ambiguous dates** is *not*
promoted to `needs_mapping`: the profile carries the `date_format` the user
already confirmed for that exact header signature, and `detect_date_format`'s
ambiguity flag (`_date_ambiguous`) exists to pick a default when there is no
profile. Re-asking a question already answered is decision 1's babysitting.
The consequence is stated rather than hidden: a bank that changes its date
convention **without changing its header** would import silently under the old
format — which is a pre-existing property of profile matching (FIBR-0007
INV-9), not something this batch introduces, and the periods on the review
screen are where it would show.

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
already hold.

**A password the user types during this run joins the list for every later
file in the same batch**, before any further prompting. Without that rule a
first batch of thirty same-bank PDFs is thirty prompts — an "unattended"
feature that asks thirty questions — because the stored-password list is empty
until something is remembered, and *Remember* may never be ticked. With it,
the common case is one prompt per distinct password per batch. Run-local
passwords are held in memory for the run only; only a *Remember*-ticked one is
ever written (above). Each distinct password is still tried at most once per
file, so the cost stays bounded by (accounts + distinct passwords typed).

A password entered during the ASK pass with *Remember* ticked is **held on the
record, not written immediately** — in `BatchFile.pending_password` /
`remember_password` (§4.2). At prompt time the file is still unparsed, so its
destination account is not yet known and there is nothing to key the password
to. It is written by `AccountService.set_pdf_password(account_id, value)`
once the destination settles (at SCAN for a matched file, at REVIEW for one the
user places by hand), and **dropped unwritten if the file never settles one** —
`failed`, `skipped`, or left `needs_account` when the user leaves the screen.

**How a decline is detected.** `PasswordDialog` is shown through the
non-blocking `show_modal`, which wires only `accepted`; its Cancel has no slot
at all today (§2.3), so "the user declined" is currently unobservable. The
batch connects `rejected` on the dialog it constructs — `show_modal` sets no
`rejected` handler, so adding one at the call site conflicts with nothing — and
treats it as the decline that makes the record `skipped`. Without that
connection INV-8's "cancelling a prompt skips that file immediately" has no
mechanism, and a cancelled prompt would leave the pass waiting forever on a
dialog that has already been freed.

That is the shape FIBR-0249 asks for on the single-file path, where the
password is keyed to whatever the pick step happened to hold. This spec does
not fix the single-file path; it declines to copy the defect.

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
def cumulative_counts(
    files: Sequence[BatchFile], imports: ImportService
) -> None:
    """Set `new_count` AND `duplicate_count` on every record WITH A PREVIEW.

    Domain is `preview is not None` — NOT `outcome == "ready"`. Two reasons,
    and the second is the one that bites: this runs BEFORE REVIEW sets the
    ready/already_imported outcomes on the same pass, so "the ready records"
    names a set that does not exist yet; and an `already_imported` record must
    keep having its counts recomputed, or a later retarget can never see its
    new_count rise above zero and it can never return to `ready` (INV-10).

    The baseline for each record is the EXISTING VAULT ROWS for its account
    PLUS the drafts claimed by earlier records in this batch. The vault half is
    why `imports` is a parameter: the drafts-per-account baseline is read
    through ImportService (the same reads _dedup performs), and a function
    given only the file list cannot reach it.

    Walks in commit order, per destination account. The key is the one
    ImportService._key builds — (occurred_on, amount_minor,
    self._normalise(description)), where _normalise delegates to the shared
    text.normalise_text — so this is the same equality the commit will apply,
    not a second opinion about it.

    A record whose outcome is `committed`, `failed`, `skipped` or
    `not_attempted` has no preview and is skipped; its drafts never enter any
    other record's baseline.
    """
```

Scoped per `account_id`, because dedup is per-account: two files landing in
different accounts never dedup against each other however identical their rows.

**Both counts move together, and that is not a detail.** Making only
`new_count` cumulative while the Duplicate column kept reading
`preview.duplicate_count` would put two numbers computed under different rules
side by side on the approval screen: the second file's shared rows would be
subtracted from New and never appear under Duplicate, so New + Duplicate would
not account for the file's rows and the user could not reconcile what they were
approving. This is INV-4, and it is why `BatchFile` carries both counts as
fields of its own rather than reading either from the preview.

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
| Errors | `BatchFile.error_count` — blank when zero, so it draws the eye only when it matters |
| Status | the `Outcome`, rendered per §4.8 — including `waiting` before SCAN reaches the row |

**Rows can share a basename**, two ways: `statement.pdf` from two folders (§8
rejects filename-based duplicate detection for exactly this reason), and the
several statements fanned out of one OFX file, which share a path outright.
The File cell therefore renders, in order of escalation: the basename; the
basename prefixed with its parent directory when that disambiguates; otherwise
the **full path**. A fanned-out OFX statement always appends its index —
`bank.ofx [2 of 3]` — since no path prefix can separate siblings from the same
file. The full path is the tooltip on every row regardless.

**Setting an account.** The Account cell is clickable exactly on rows whose
**`parsed` is not `None` and whose outcome is not `committed`** — which
excludes `failed`, `skipped`, `not_attempted` and any row still `waiting` (all
of which reach the table with nothing parsed), and excludes a row already
written to the vault. (An earlier gloss said "every row except `failed`", which
is false and would hand `preview_result` a `None`; and without the `committed`
half a user could retarget a row after the run and silently re-dedup against
rows that are already in the vault.) **The whole table becomes read-only once
RUN finishes** — at that point it is the report, not a form. The cell
opens `AccountPickerDialog` with the Create affordance of §3 decision 6. Which
call follows depends on whether a preview exists yet, and the two are not
interchangeable:

- **No preview** (the row was `needs_account`): `preview_result(parsed,
  account_id)` builds the first one, and the row becomes `ready`.
  `ImportService.retarget` cannot be used here — it takes an `ImportPreview`
  and there is none.
- **A preview exists** (the user is changing an already-settled row):
  `ImportService.retarget(preview, account_id)`, whose returned preview
  replaces the stored one.

Either way `cumulative_counts` then re-runs over the whole batch, because one
row's destination changes which rows every *other* row in that account may
claim.

**The review step's three controls**, so abandonment is defined rather than
implied: **Import all** starts RUN; **Cancel** abandons — before RUN it drops
the whole batch (every held password discarded unwritten, §4.4) and returns to
the pick step *without* emitting `done`, during RUN it stops the chain; and
**Close** appears only once RUN has finished, and is the one control that
emits `done` (INV-14).

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

**The unreadable-row clause belongs to the row, not to `committed`** (FIBR-0254).
`error_count` is set during SCAN, before any outcome is known, and §4.6's Errors
column renders it for every outcome — so a clause appended on `committed` alone
let an `already_imported` row read *"nothing new in this file"* beside a cell
reading 4, one row contradicting itself. It is spelled *", 1 row couldn't be
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

- **INV-4** — For each `ready` file, the New **and** Duplicate counts shown on
  the review step equal its `ImportResult.inserted_count` and
  `duplicate_count` after the run, given no change to the vault between the
  two **and no earlier record in the batch failing during RUN**. The second
  exception is not a hedge: `cumulative_counts` subtracts the drafts an earlier
  overlapping record was going to claim, so if that record raises and never
  commits them, a later record legitimately inserts *more* rows than the
  reviewed figure promised. INV-1 requires the batch to continue past that
  failure, so the two invariants genuinely trade against each other and the
  report — not the review screen — is the truth after a failure.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV4_reviewed_counts_are_the_committed_counts`
  — two overlapping CSVs targeting one account, sharing four rows; the review
  shows the second file's four shared rows under Duplicate and not under New,
  and the sum of the two New counts equals the row count in the vault
  afterwards.
  *Breaks when:* `cumulative_counts` is skipped and the preview's own counts
  are displayed, which count each file against the committed vault alone —
  reporting the four shared rows twice under New. It breaks *asymmetrically*
  if only `new_count` is made cumulative: the four rows then vanish from New
  without appearing under Duplicate, so the row no longer accounts for the
  file's transactions at all.

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
  *Breaks when:* the new module is written with `dialog.exec()`; or is created
  and not added to `_FILES`, in which case the guard passes while covering
  nothing; or a modal `QProgressDialog` is driven by a bare
  `QApplication.processEvents()` loop, which carries no `.exec(` token and so
  passes the unextended grep while re-entering the event loop exactly as
  FIBR-0065 forbids. Both the tuple and the pattern are part of the contract.

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

- **INV-9** — Each distinct remembered password is tried at most once per
  file, and only before the user is prompted.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV9_stored_passwords_tried_once_each`
  — three accounts, two holding the same password string; a counting fake
  records two **password-bearing** decrypt attempts, not three, and no prompt
  when one succeeds. (The no-password attempt that opens the ladder is not
  counted; asserting a bare total of two would fail against conforming code,
  which makes three calls in all.)
  *Breaks when:* `stored_passwords` returns duplicates, so a shared password
  is tried once per account holding it — invisible on success and a
  quadratic-looking stall on a large account list.

- **INV-10** — Each record's outcome is **re-derived in both directions** on
  every REVIEW pass: `already_imported` when the span exists **and** the
  cumulative new count is zero, `ready` otherwise. A record never stays
  `already_imported` once either half stops holding.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV10_already_imported_is_recomputed_both_ways`
  — three legs: re-importing an unchanged statement reports
  `already_imported`; the same statement re-issued with three extra
  transactions over the same dates reports `ready`; and a record sitting at
  `already_imported` that is **retargeted to a different account** returns to
  `ready` and commits its rows.
  *Breaks when:* either half of the test is dropped, or the derivation is made
  one-way — §4.3 carries all three failure modes and why the two-directional
  form is the shortest rule that avoids them.

- **INV-11** — The batch refuses more than 200 **selected files** before
  reading anything, and stops the scan once 200,000 drafts are held. Neither
  cap raises: the refused or unscanned records are `not_attempted` and say
  which cap stopped them.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV11_batch_caps`
  — 201 synthetic paths are refused before any file is read; a scan crossing
  the draft cap stops with the records scanned so far marked and the rest
  `not_attempted`.
  *Breaks when:* neither cap is enforced and a folder of large PDFs holds
  every preview in memory at once (§10). Two boundary notes the test pins:
  the file cap counts **selected files**, not fanned-out OFX statements, so a
  200-file batch cannot be refused by its own fan-out; and the draft check is
  `>=` before each file, matching this clause's "once 200,000 are held" — see
  §10 for the peak that actually implies. The *wording* of the two messages is
  not covered — see §11.

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

- **INV-13** — A record whose parse yields **either** period endpoint `None`
  never reaches `commit_import`: it becomes `failed` at SCAN with a reason
  naming the absent dates.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV13_undated_file_fails_before_commit`
  — two legs, one per endpoint, since `period_start` and `period_end` are
  independently `str | None` on both `ParseResult` and `ImportPreview`: a CSV
  whose every row has an unparseable date, and a synthetic `ParseResult`
  carrying a start but no end. Each is `failed`, its reason mentions dates, and
  `commit_import` is never called for it.
  *Breaks when:* either endpoint is passed through as `None`, which reaches
  `ImportService._validate_span` and surfaces *"period endpoints must be valid
  ISO-8601 dates"* — a message about malformed dates for a file that had none
  at all. Guarding only `period_start`, as an earlier draft did, leaves the
  second leg red.

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

- **INV-15** — An OFX file carrying N statements produces N records, each with
  its own account, preview and review row. No statement is discarded.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_INV15_multi_statement_ofx_fans_out`
  — a synthetic two-statement OFX naming two different account numbers yields
  two records with `statement_index` 0 and 1, matched to two different
  accounts, and both statements' rows land in their own account.
  *Breaks when:* SCAN stores `OfxImporter.parse`'s list into the single
  `parsed` slot and keeps only `[0]` — which reads as natural, because every
  other format returns one `ParseResult` — silently discarding every statement
  after the first. The wizard already models this correctly with its
  `_ofx_statements` list and a chooser; a batch that collapses it would be a
  regression against behaviour that ships today.

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
