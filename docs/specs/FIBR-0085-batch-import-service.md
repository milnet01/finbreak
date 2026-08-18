# FIBR-0085 — the batch import service (record, passes, passwords, dedup)

**Status:** accepted (2026-08-06).
**Kind:** feature.
**Source:** ROADMAP FIBR-0085 (user-request-2026-07-11, dogfooding v0.1.0).

**Layman:** This half describes the part of finbreak that does the work with no
window on screen — how it remembers each selected file, the four passes it runs
them through, how it tries the passwords it already knows before asking, and how
it counts what is genuinely new when two statements in the same batch overlap.

> **Split out of**
> [`FIBR-0085-batch-statement-import.md`](FIBR-0085-batch-statement-import.md)
> on 2026-08-18 (ROADMAP **FIBR-0267**) — see that file's § 13 Cold-eyes loop
> log for the review history of all three files, which is kept whole there
> rather than divided.
> **This is a structural move, not an amendment: every line below was verbatim
> from that file at the moment of the cut.** No invariant was re-cut and no id
> renumbered — which is why the sections start at 4.2 and the invariants skip
> INV-3, 5, 6, 7, 8, 12 and 14. Ids are permanent; the gaps are the point.
> **Same id, deliberately**, so existing `FIBR-0085 §4.3` / `INV-4` citations
> resolve untouched.

**This is the Qt-free half.** Everything here lives in
`src/finbreak/services/batch_import.py` (plus `importers/sniff.py`) and is
testable headless; its invariants are the ones whose `*Test:*` names
`tests/features/batch_import/test_batch_import.py`. The widget half — the
review table, the event-loop driver and the outcome vocabulary — is
[`FIBR-0085-batch-import-review-step.md`](FIBR-0085-batch-import-review-step.md).

**Read this with**
[`FIBR-0085-batch-statement-import.md`](FIBR-0085-batch-statement-import.md).
That file owns the goal, the problem, the scope decisions, **§ 4.1 Where the
work lands** (the module table this half is cut along), the failure modes, the
test plan, the canonical invariant → test mapping (§ 11), the resource budget
and every frozen record. One home, one copy: where a rule lives there, this
file cites it rather than restating it.

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

**Contents:** [4.2 The per-file record](#42-the-per-file-record) ·
[4.3 Four passes](#43-four-passes) ·
[4.4 PDF passwords](#44-resolving-a-pdf-password-with-no-pick-step-account) ·
[4.5 Cumulative dedup](#45-cumulative-dedup--the-reviewed-number-is-the-number-that-lands) ·
[5. Invariants](#5-invariants) (INV-1, 2, 4, 9, 10, 11, 13, 15)

## 4. Design
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
    PLUS the drafts claimed by earlier records in this batch. The vault half
    ARRIVES ALREADY APPLIED and is not read again here:
    `preview.duplicate_row_numbers` is exactly the set the vault-only delta
    dropped, so the drafts NOT in it are what this record would insert against
    the vault alone. `imports` is a parameter for one reason only —
    `imports._key(draft)` — so this uses the same equality the commit will.

    Do NOT re-read the vault to build that half. Subtracting a freshly-read
    vault baseline from a preview that has already had it applied subtracts
    the same rows twice and under-reports New, which breaks INV-4.

    Walks in commit order, per destination account. The key is the one
    ImportService._key builds — (occurred_on, amount_minor,
    self._normalise(description)), where _normalise delegates to the shared
    text.normalise_text — so this is the same equality the commit will apply,
    not a second opinion about it.

    A record is skipped when it has no preview OR its outcome is terminal
    (`committed`, `failed`, `skipped`, `not_attempted`) — two independent
    tests, and the second is the one that bites. A `committed` record HAS a
    preview (RUN passes it to `commit_import`), and so does a RUN-`failed` one
    (§4.8: it read perfectly and the commit refused it). Skipping on
    `preview is None` alone would let already-committed drafts enter a later
    record's baseline on any re-run, subtracting the same rows from New twice.
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


## 5. Invariants

The eight this half owns — every one whose `*Test:*` names
`tests/features/batch_import/test_batch_import.py`. **INV-3, 5, 6, 7, 8 and 14**
live in
[the review step](FIBR-0085-batch-import-review-step.md#5-invariants) and
**INV-12** in
[the shared file](FIBR-0085-batch-statement-import.md#5-invariants); none is
restated here.

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
