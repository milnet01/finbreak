# FIBR-0252 — Propagate Standard Bank per-row errors to the import preview

**Status:** accepted (2026-08-06) — cleared for code; /cold-eyes converged at loop 5.
**Kind:** fix.
**Source:** ROADMAP FIBR-0252 (code-quality-review-2026-08-06, FIBR-0085 close, service lane).

**Pairs with:** FIBR-0085 (the batch review step, whose Errors column this makes truthful).

*Layman: when a line on a Standard Bank statement cannot be read, the app currently
throws that fact away and tells you "53 added" with no hint that anything was
skipped. After this, the skipped line is counted and shown.*

[1. Goal](#1-goal) · [2. Problem](#2-problem) · [3. Scope decisions](#3-scope-decisions-agreed-with-the-user) ·
[4. Design](#4-design) · [5. Invariants](#5-invariants) · [6. Failure modes](#6-failure-modes) ·
[7. Tests](#7-tests) · [8. Alternatives](#8-alternatives-considered-and-rejected) ·
[9. Out of scope](#9-out-of-scope) · [10. Resource cost](#10-resource-cost) ·
[11. What checks this](#11-what-checks-this) · [12. Cross-doc impact](#12-cross-doc-impact) ·
[13. Cold-eyes loop log](#13-cold-eyes-loop-log)

## 1. Goal

`StandardBankImporter.parse` returns the per-row errors its family parser produced,
instead of an empty list. A Standard Bank statement carrying an unimportable row
reports that row — in the single-file preview's row table and summary line, in the
batch review step's **Errors** column, and — once the file commits — in the batch
per-file report line, which appends *", N rows couldn't be read"* (that clause lives
on `report_line`'s `committed` branch only; §6 says what the other outcomes show) —
the same way a CSV or OFX statement already does, **wherever the statement survives
its balance gates at all.** That proviso is
not a hedge: §6 shows a money-moving unreadable row makes the gate reject the whole
statement, and a rejected statement reports nothing because there is nothing to
report.

**No draft, balance-check or coverage-span behaviour changes**: the same rows
import, against the same gates, with the same span. Three consequences do follow,
and each is accounted for rather than waved past:

- the batch report line named above; §11 records that **nothing** checks it;
- `ImportResult.error_count`, which stops being a constant zero for Standard Bank
  files — §4.3;
- two pre-existing reporting defects that become newly reachable on Standard Bank
  files: the FIBR-0146 preview banner (FIBR-0253) and `report_line`'s Status/Errors
  contradiction and mis-pluralisation (FIBR-0254) — §6, deferred in §9.

The banner's reach is wider than FIBR-0253's own bullet claims — §6 has the argument,
§12 the correction.

## 2. Problem

`importers/standard_bank.py::StandardBankImporter.parse` ends with

```python
return ParseResult(result.drafts, [], start, end, closing_minor, hint)
```

The literal `[]` discards `result.errors` — the errors `_split` had just separated
out of the family parse. Three facts make this a money-app defect rather than a
cosmetic one.

1. **The errors are real and reachable.** `_draft` returns a `RowError` instead of a
   `TransactionDraft` when `parse_transaction` rejects the row, and its docstring
   names the reachable case: a legitimate printed `0.00` line (a waived fee,
   "interest capitalised 0.00"), which fails "amount must be non-zero". That
   degrade-per-row behaviour is deliberate — it is FIBR-0216, which exists so one
   such line does not abort the whole statement.
2. **The balance gate does not catch the loss.** A dropped zero-amount row
   contributes 0 to every running balance, so `_verify_checksum` reconciles happily
   and `parse` returns normally. The row is gone and nothing anywhere says so.
3. **Every consumer downstream is already wired and is being starved.**
   `ImportService._preview_from_result` carries `result.errors` into
   `ImportPreview.errors`; `ImportWizardWidget._fill_preview_table` interleaves error
   rows into the preview by `row_number`; `_apply_preview_counts` renders "· N
   error"; `ImportService.commit_import` derives `ImportResult.error_count` from
   them; `BatchImportService._settle_parse` sets `BatchFile.error_count =
   len(parsed.errors)`; and `BatchReviewWidget` renders that in the Errors column and
   appends *", N rows couldn't be read"* in `report_line`. All six are starved by
   the same empty list on every Standard Bank statement — the last two by way of the
   `int` derived from it rather than the list itself.

   One of the six is wired but not *correct*: the FIBR-0146 D7 banner inside
   `_apply_preview_counts` gives CSV-only advice on a PDF (§6, FIBR-0253).

FIBR-0085 §4.2 introduced `error_count` on exactly this reasoning — "a file where 40
of 50 rows failed commits 10 and would report '10 added' with no hint that 40
vanished; in a money app a silently dropped row is the defect". That argument is
defeated on the Standard Bank path, which is the path this user's own corpus is made
of.

**Reproduced, end to end, before writing this spec.** A synthetic Family A statement
carrying `SERVICE FEE WAIVED 0.00 05 03 900.00` between two ordinary rows:

```
$ PYTHONPATH=src python - /tmp/probe/family_a_zero_fee.pdf <<'PY'
import sys
from finbreak.importers.standard_bank import StandardBankImporter
r = StandardBankImporter().parse(open(sys.argv[1], "rb").read(), 2)
print("drafts:", [(d.row_number, d.amount_minor) for d in r.drafts])
print("errors:", [(e.row_number, e.reason) for e in r.errors])
PY
drafts: [(1, -10000), (3, 25000)]
errors: []
```

Row 2 is absent from `drafts` and absent from `errors` — silently gone. Driving the
same fixture through the module's own front half as far as `_parse_family_a` shows
what `parse` is throwing away:

```
family-level errors: [(2, 'amount must be non-zero')]
```

**Scale.** The discard is in the shared public boundary, so it applies to every
Standard Bank layout family: 5, from `grep -c "^def _parse_family_"
src/finbreak/importers/standard_bank.py` → `5` (A–E, per the `Family` enum). The
roadmap bullet's "all six SB families" is a miscount; nothing else depends on the
figure.

**Not introduced by FIBR-0085.** The `[]` predates it — FIBR-0085 only made the
consequence visible by adding a column that reads the channel.

## 3. Scope decisions (agreed with the user)

- **The user asked for this as its own item** rather than as a fix in passing during
  the FIBR-0085 close (2026-08-06). §8 carries the reasoning; what it means here is
  that the preview change is specified and tested, not left as a side effect.

No other preference calls were made — every remaining choice follows from §2.

## 4. Design

### 4.1 The change

One line in `importers/standard_bank.py::StandardBankImporter.parse`:

```python
return ParseResult(result.drafts, result.errors, start, end, closing_minor, hint)
```

No new function, no new field, no signature change. The channel exists, the
consumers exist, and only the producer was empty.

### 4.2 The fixture

A new committed synthetic fixture,
`tests/features/standard_bank_pdf/fixtures/family_a_zero_fee.pdf`, following the
suite's established pattern: reportlab-generated fake data plus the Standard Bank
legal marker, with the generated PDF committed and reportlab left probe-only (it is
in no dependency group).

**The whole page, not just the rows** — this suite commits no generator script, so
this recipe is the only way to regenerate the fixture. Generate it with reportlab
(5.0.0 was used; the acceptance test is INV-6's text extraction, **not** byte
equality, so a different reportlab is fine if the extracted layer matches):

```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
c = canvas.Canvas(path, pagesize=A4)
c.setFont("Helvetica", 9)
y = 800
for line in LINES:            # the thirteen lines below, in order
    c.drawString(40, y, line) # left-aligned at x=40, top-down
    y -= 14                   # 14pt leading
c.showPage()
c.save()
```

Those parameters are part of the recipe, not decoration — the extracted text layer
is what `parse` reads.

```
Standard Bank
BANK STATEMENT / TAX INVOICE
PRESTIGE CURRENT ACCOUNT Account Number 00 000 000 0
Month-end Balance R1,000.00
Statement from 1 May 2026 to 31 May 2026
Details Service Fee Debits Credits Date Balance
BALANCE BROUGHT FORWARD 05 01 1,000.00
FAKE SHOP PURCHASE 100.00- 05 02 900.00
SERVICE FEE WAIVED 0.00 05 03 900.00
FAKE SALARY DEPOSIT 250.00 05 04 1,150.00
Balance at date of statement 1,150.00
Please verify all transactions reflected on this statement.
The Standard Bank of South Africa Limited (Reg. No. 1962/000738/06)
```

Fake account number and fake payees throughout — the repo is public, and the
no-real-data rule binds fixtures absolutely. INV-6 is what checks that, because the
guard that covers the rest of the repo cannot read inside a `.pdf`.

The fixture is **unencrypted** — §12 depends on that, since the batch suite's fake
decrypt function stays untouched.

**Which lines are load-bearing, measured by ablation** — each of the thirteen lines
dropped in turn from this exact page, the result re-parsed. Written down because
"every line matters" was the easy claim and it is false: four are decoration, one is
the fixture's whole reason to exist, and a regenerator needs to tell them apart.

| Line | Dropping it |
|---|---|
| `Statement from 1 May 2026 to 31 May 2026` | `ValueError` — `_parse_period` returns `None`, Family A raises `_MISPARSE` |
| `Details Service Fee Debits Credits Date Balance` | returns `None` — not detected as SB at all |
| `The Standard Bank of South Africa Limited (Reg. No. …)` | returns `None` — the legal marker is half of detection |
| `BALANCE BROUGHT FORWARD 05 01 1,000.00` | `ValueError` — no opening balance. It is an anchor, not a transaction: it consumes no `row_number`, which is why the two money rows are 1 and 3 |
| either money-**moving** row | `ValueError` — the running balance no longer reconciles |
| `SERVICE FEE WAIVED 0.00 05 03 900.00` | **parses cleanly and still reconciles** — and the fixture stops testing anything. This is the line the whole fixture exists for; without it INV-1, INV-2, INV-5 and INV-6 all pass while proving nothing. It is in neither bucket below, which is exactly why it needs its own row |
| `PRESTIGE CURRENT ACCOUNT Account Number 00 000 000 0` | parses, but `source_account` becomes `None` (the FIBR-0086 hint) |
| `Balance at date of statement 1,150.00` | parses, but `closing_balance_minor` becomes `None` (legal on Family A) |
| `Standard Bank`, `BANK STATEMENT / TAX INVOICE`, `Month-end Balance R1,000.00`, `Please verify all transactions…` | **no effect** — decoration, kept only so the page reads like a real statement |

`Month-end Balance R1,000.00` is worth calling out as decoration specifically: it is
the page's only other money token above the column header, so it *looks* like it
feeds `_table_region`'s header guard or `_capture_opening`. Dropping it changes
nothing.

Baseline for the whole page, measured: 2 drafts (rows 1 and 3), the zero-amount line
as row 2, `period_start`/`period_end` `2026-05-01` / `2026-05-31`,
`closing_balance_minor` `115000`, `source_account.number` `00 000 000 0`, and a
reconciling `1,000.00 − 100.00 + 250.00 = 1,150.00`. That last part matters for
INV-1: the test must fail pre-fix for the reason under test, not because the
statement was rejected outright.

Family A is chosen because it is the layout whose real-world corpus carries the
waived-fee lines this bug is about. Not for its checksum path: §6 establishes that a
dropped zero-amount row reconciles on **every** family, so there is nothing
distinctive about A there — and this fixture prints a closing balance anyway, so it
never takes A's `closing is None` early return.

**The fixture lives in the `standard_bank_pdf` suite and INV-4's test reaches across
to it**, the way `tests/features/forecast/test_importer_capture.py` already reaches
into the same directory. That crosses a stated policy in
`tests/features/batch_import/spec.md` — "Synthetic strings only … a **fake** decrypt
function in place of any locked PDF" — so §12 carries the amendment. The literal
half of that policy ("No `.pdf` file is committed under this directory at all", the
premise of its INV-12 rationale) is **preserved**: nothing new is committed under
`tests/features/batch_import/`.

### 4.3 What does not change

Stated because a reviewer of the diff will reasonably ask, and because two of these
would be tempting "improvements" that would break the contract:

- **The completeness gate.** `_verify_checksum` and `_verify_e_totals` keep summing
  `result.drafts` only. Error rows carry no money; folding them in would make a
  waived fee look like a truncated statement.
- **The row cap.** `_MAX_PDF_ROWS` (100,000, defined in `importers/pdf_importer.py`)
  keeps bounding `len(result.drafts)`. Error rows are bounded upstream instead, by
  the `len(region_lines) > _MAX_PDF_ROWS` gate, which rejects before any per-row
  work. No exact multiple is claimed: `parse`'s comment says a region line yields
  "at most a couple of drafts", and "a couple" is prose, not an enforced factor —
  deriving `2 ×` from it would be inventing precision. What matters is that the
  input is bounded before the work, so propagation opens no new unbounded-input
  surface.
- **What commit *writes*.** `commit_import` inserts drafts only; no error row has
  ever become a transaction and none does now. **But errors do reach it**, and this
  is the one consequence a reader of this section would otherwise miss:
  `commit_import` already derives `ImportResult.error_count` from
  `len(preview.errors)`, so that field stops being a constant zero for Standard Bank
  imports the moment this lands. Verified as invisible today rather than assumed:
  `error_count` is read by `BatchReviewWidget` off `BatchFile`, and **nothing on the
  single-file path reads `ImportResult.error_count` at all** — no label, no toast.
  So the change is real, correct, and currently unobserved; §11 records it as
  knowingly unguarded rather than pretending it does not happen.
- **The dedup delta, the coverage span, the closing balance and the
  `SourceAccountHint`** — all computed from drafts and the document, untouched here.

## 5. Invariants

No trust boundary moves: the change is inside an already-untrusted-input path whose
existing defences — `_MAX_PDF_PAGES`, `_MAX_PDF_ROWS`, the pdfplumber boundary
catch, the in-memory decrypt — all sit upstream of the returned value and are
untouched by a change to one argument. §4.3 discusses only the one this edit sits
beside (`_MAX_PDF_ROWS`); the other three are not re-litigated there and need not
be.

- **INV-1** — `StandardBankImporter.parse` returns every `RowError` its family
  parser produced.
  *Test:* `tests/features/standard_bank_pdf/test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors`
  — parses `family_a_zero_fee.pdf` and asserts
  `[(e.row_number, e.reason) for e in r.errors] == [(2, "amount must be non-zero")]`.
  An equivalent call on an equivalent scratchpad fixture returns `errors: []` today
  (§2), so the red run is expected — but it is still run, not assumed.
  *Breaks when:* any `ParseResult` construction in `parse` passes a literal in the
  errors position (the present defect), or filters `result.errors`.

- **INV-2** — drafts and errors partition the rows the family grammar **matched and
  handed to `_draft`**: such a row is in exactly one of the two channels, never both
  and never neither.
  *Test:* the same test asserts `[d.row_number for d in r.drafts] == [1, 3]`
  alongside the error at row 2, so the three allocated row numbers partition
  cleanly. The general property rests on `_split`, which is a two-comprehension
  partition over one list.
  *Breaks when:* `_split`'s partition changes, or a future caller appends an error
  row to `drafts` to "keep the numbering contiguous".
  *Deliberately not claimed:* region lines the grammar never matched. Those are
  handled upstream of `_draft` and carry no `row_number` — an anchor-balance line
  `continue`s, a Family C section header or zero-date continuation line is skipped
  or folded into the preceding description, and any other unmatched line raises
  `_MISPARSE` rather than degrading. They are in neither channel by design, and
  widening INV-2 to cover them would state a contract the code does not implement.

- **INV-3** — propagating errors changes nothing else `parse` returns: the same
  drafts, the same span, the same `closing_balance_minor`, the same checksum
  outcome. What changes is only what the parse *reports* alongside them.
  *Test:* `test_FIBR0252_parse_propagates_row_errors` asserts the full return on the
  one fixture that exercises the changed path — `[d.amount_minor for d in r.drafts]
  == [-10000, 25000]`, `r.period_start == "2026-05-01"`, `r.period_end ==
  "2026-05-31"`, `r.closing_balance_minor == 115000` — so a fix that disturbed any
  of them fails here.
  *Breaks when:* someone widens `_verify_checksum` to include error rows, or makes
  the row cap count them.
  *Why the corpus is not the guard.* The obvious test surface — "the existing 22
  fixtures still pass" — is **vacuous for this invariant**, and saying so is more
  useful than claiming it. Measured: of the 22, the 11 that parse return `errors=0`,
  10 raise by design, and `non_sb.pdf` returns `None`. Nothing in the corpus carries
  a `RowError`, so nothing in it can regress on a change to the error channel; those
  legs stay green either way. They remain a real regression sweep for the *parser*,
  and no leg needs modifying — they are simply not what pins INV-3.

- **INV-4** — a Standard Bank file with an unimportable row carries a non-zero
  `BatchFile.error_count`, and the review table renders that count in the Errors
  column.
  *Test:* **two legs, in two files**, because the batch suite is split by whether a
  test needs Qt — `test_batch_import.py` has no `qtbot` at all and every
  `BatchReviewWidget` test lives in `test_batch_import_ui.py`. Putting a
  rendered-cell assertion in the headless file would import Qt into the one file
  that deliberately has none.
  - `tests/features/batch_import/test_batch_import.py::test_FIBR0252_error_count_is_set_for_a_standard_bank_file`
    — scans `family_a_zero_fee.pdf` and asserts the record's `error_count == 1`.
  - `tests/features/batch_import/test_batch_import_ui.py::test_FIBR0252_errors_column_shows_the_count`
    — asserts the rendered `COL_ERRORS` cell reads `"1"`.

  Both are needed because `BatchReviewWidget._number` returns `""` for a zero: the
  field and its rendering are separate claims, and only the second is what the user
  sees. The headless leg goes through the **real** `PdfImporter.decrypt_to_plaintext`
  via `BatchImportService._scan_pdf`; the fixture is unencrypted, so the
  `password=None` rung returns usable plaintext. The batch suite's fake decrypt function
  stays where it is, serving only the existing locked-PDF legs.
  *Breaks when:* `BatchImportService._settle_parse` stops setting `error_count` from
  `len(parsed.errors)`, the scan path stops reaching the preview, or `_number`
  stops rendering a non-zero count.

- **INV-5** — the single-file preview interleaves the error row into the row table
  in file order, and counts it in the summary line.
  *Test:* `tests/features/standard_bank_pdf/test_standard_bank.py::test_FIBR0252_preview_shows_the_error_row`
  — drives the wizard over the fixture with `qtbot` and asserts the preview table
  holds 3 rows; that the row whose **first cell reads `2`** carries "Error" in the
  status column; and that the summary line ends "· 1 error". Stated by cell content,
  not by table index, because `_fill_preview_table` sorts the interleaved entries by
  `row_number` — statement row 2 does land at table index 1 here, but a test written
  against the index would silently follow a re-ordering rather than catch it.
  *Breaks when:* `_fill_preview_table` stops interleaving, or
  `_apply_preview_counts` stops counting `preview.errors`.

- **INV-6** — the committed fixture contains no real **customer or account** data:
  no real account number, no real payee, no real balance.
  *The deliberate exception*, named because the obvious wording "no real bank data"
  is falsified by the fixture's own required content: the detection marker
  `The Standard Bank of South Africa Limited (Reg. No. 1962/000738/06)` is a real
  published company registration number, the ablation table records it as required
  for `detect_standard_bank` to fire at all, and every existing fixture in the suite
  carries it. It is public corporate identity, not anybody's banking data — which is
  precisely the line this invariant draws.
  *Test:* `tests/features/standard_bank_pdf/test_standard_bank.py::test_FIBR0252_fixture_is_synthetic`
  — extracts the fixture's text (a repo grep cannot read a PDF's text stream, so
  this must be an extraction leg, exactly as the suite's FIBR-0190 D6 leg is) and
  asserts the account number is the suite's fake `00 000 000 0` and that **every
  extracted line is one of the thirteen in §4.2's page** — an explicit allow-list,
  not a `FAKE`-prefix rule. Compare each line `.strip()`ed with internal whitespace
  runs collapsed to one space: `pdfplumber`'s `extract_text` does not promise to
  reproduce authored spacing, and an exact-equality assertion would go red on a
  correct fixture — the same trap as the prefix rule, one layer down. The prefix rule would be wrong on this very fixture:
  `SERVICE FEE WAIVED`, `BALANCE BROUGHT FORWARD` and `Balance at date of statement`
  carry no `FAKE`, and an implementer writing the prefix version gets a red test on
  a correct fixture.
  *Breaks when:* someone regenerates the fixture from a real statement.
  *Why it needs its own invariant:* the repo is public and the repo-wide corpus
  guard **skips binary `.pdf` bytes** (`tests/features/batch_import/spec.md` records
  this as INV-12's weakest link). So for a committed PDF there is no ambient check —
  the one guard that would catch a mistake here is the one this file is invisible
  to.

## 6. Failure modes

- **A row errors — what happens next.** The outcome splits three ways: on whether
  the errored row moved money, and if so on whether any balance gate is in a
  position to fire. All three cover the ordinary **one-bad-row** case — §4.2's
  fixture is exactly that, one waived-fee line among three. Only the *0 new · 0
  duplicate · N error* preview sub-case inside the first branch needs every row to
  have errored. Worth being precise about, because the worst of the three reads like
  an exotic edge case and is not. `_draft`
  returns a `RowError` for **any** `ValueError` out of `parse_transaction`, and that
  function has seven rejection classes, not one: blank description, non-ISO date,
  non-numeric amount, non-finite amount, more fractional digits than the currency
  allows, `to_minor_storable`'s 64-bit storage bound (which raises `ValueError` too,
  by contract), and — last — zero amount.

  **Zero-amount rows (the common case, and the one `_draft`'s docstring names).**
  The errored rows moved no money, so `Σ drafts` loses nothing and the arithmetic
  still closes. Where *every* row is such a row, `Σ drafts` is `0`, the printed
  opening and closing are equal by construction, `_verify_checksum` reconciles, and
  the file is **previewed** as *0 new · 0 duplicate · N error* — on **every** family,
  not just the closing-less ones. Family E included, and measured rather than
  argued: `_parse_family_e` on a zero-delta row returns
  `errors: [(2, 'amount must be non-zero')]` like Family A does, and its own gate
  compares each printed total against the drafts, so a fee-only month printing
  `Payments 0.00` matches `abs(0)`. Only a **non-zero** printed total rejects such a
  statement on E.

  On the **batch** path the outcome depends on whether this file has been imported
  before, and the distinction is easy to get wrong: `BatchImportService.review`
  derives the span from `StatementPeriodRepository.id_for_span(...)`, which is a
  `statement_periods` row **already in the vault** — not the span this parse just
  produced.

  - **First import.** No such row exists, so `span is None` and the record is
    `ready`. It commits, and `report_line`'s `committed` branch appends the clause:
    *"0 added, 0 duplicates, N rows couldn't be read"*. The batch path reports the
    errors correctly here.
  - **Re-import of the same file.** The span now exists and the cumulative new count
    is zero, so INV-10 re-derives `already_imported` and the row reads "Already
    imported — nothing new in this file" beside an Errors cell showing N. That
    Status/Errors contradiction is what FIBR-0254 owns, and it is **re-import only**
    — stated here because §9 defers the fix and nothing else says what the defect
    actually is.

  **Money-moving rows, where a balance gate can fire.** The row's money is missing
  from `Σ drafts` while the printed closing still counts it, so the gate **raises**
  and the whole statement is refused with the friendly all-or-nothing message. No
  preview, no banner, no `error_count`. Verified end-to-end on §4.2's page with its
  middle row replaced by `FAKE UTILITY BILL 100.00- 05 32 800.00` — a **debit** of
  100.00 under the invalid date `05 32`, the balances adjusted to stay consistent:
  it raises "this statement didn't add up — its running balance…". The reachable
  class here is the **garbled
  date**, not a blank description: the family grammar requires a description to
  match at all, so a blank one raises `_MISPARSE` upstream of `_draft` and never
  becomes a `RowError` through `parse`. (It does at the `_parse_family_a` level, on
  a hand-built line — which is why this had to be checked through the real path.)

  **Money-moving rows, where no gate can fire — the silent under-import.** This is
  the case that matters most, and it is why this fix is worth making. When the
  statement prints **no closing balance**, `_verify_checksum` takes its
  `closing is None` early return for Family A and E; Family E's own gate degrades to
  nothing when neither printed total is present. A Savings statement (closing-less
  Family A) whose row is dropped therefore reconciles against nothing:

  ```
  # same three rows both times; only the closing line differs
  #   FAKE SHOP PURCHASE  100.00-  05 02   900.00
  #   FAKE UTILITY BILL   100.00-  05 32   800.00   <- debit, invalid day
  #   FAKE SALARY DEPOSIT 250.00   05 04 1,050.00
  bad date, NO closing (Savings)   drafts=2 sum=15000 errors=[]
  bad date, WITH closing           RAISES this statement didn't add up …
  ```

  The page really moves `−100 − 100 + 250 = +50`; the import takes `+150`. A
  transaction worth 100.00 vanishes, the totals are wrong by exactly that, **and no
  gate fires**. Note the `errors=[]`: today the one remaining trace is discarded too,
  which is this spec's defect. So the fix does not create this case — it converts it
  from *silent* to *reported*, which is the strongest single argument for it.
  Closing the gap itself is a parser question, not an error-channel one, and stays
  out of scope (§9).

  Where the first case does reach the preview, it trips the FIBR-0146 D7 banner,
  whose text names the CSV column-mapping step no PDF import visits. Pre-existing
  (already reachable via OFX, which collects per-row errors today) and **out of
  scope** — §9. On the batch path the same file is reported by `report_line`, which
  has its own two defects — also pre-existing, also newly reachable here — filed as
  FIBR-0254 (§9).
- **A statement with many error rows.** Parse-side this is bounded upstream (§4.3).
  Render-side it is a genuine, if small, widening worth stating rather than waving
  past: `_fill_preview_table` builds `len(drafts) + len(errors)` rows × 5 items, and
  for Standard Bank that second term was previously always zero. The new ceiling is
  the same one the CSV and OFX paths have carried since FIBR-0146 — error rows
  bounded by the same upstream gate as drafts — so this adds no cap that those paths
  do not already need. No new bound is introduced; the exposure is now shared rather
  than novel.
- **The fixture stops producing an error** — e.g. `parse_transaction` is one day
  changed to accept zero amounts. The risk that INV-1's test then goes green for the
  wrong reason is covered by INV-2's row-number assertion in the same test: if the
  zero row became a draft, `[d.row_number for d in r.drafts]` would be `[1, 2, 3]`
  and the test fails, rather than silently passing on an empty comparison.

## 7. Tests

Five new tests, and **one existing assertion that must change** — see below. Each
new test must be seen red against pre-fix code before the fix lands, with one
honest exception noted after the table; the INV-1 red state is already recorded in
§2.

| Test | Lives in | Locks |
|---|---|---|
| `test_FIBR0252_parse_propagates_row_errors` | `standard_bank_pdf/test_standard_bank.py` | INV-1, INV-2, INV-3 |
| `test_FIBR0252_error_count_is_set_for_a_standard_bank_file` | `batch_import/test_batch_import.py` (headless) | INV-4 (service half) |
| `test_FIBR0252_errors_column_shows_the_count` | `batch_import/test_batch_import_ui.py` (qtbot) | INV-4 (render half) |
| `test_FIBR0252_preview_shows_the_error_row` | `standard_bank_pdf/test_standard_bank.py` (qtbot) | INV-5 |
| `test_FIBR0252_fixture_is_synthetic` | `standard_bank_pdf/test_standard_bank.py` | INV-6 |

**Committing the fixture changes an existing test, and it will go red if this is
missed.** The SB suite builds `_PRE_E_FIXTURES` by **globbing** the fixtures
directory (`_FIXTURES.glob("*.pdf")`, excluding `family_e_*`), and asserts its
size:

```
$ grep -n "_PRE_E_FIXTURES) ==" tests/features/standard_bank_pdf/test_standard_bank.py
576:    assert len(_PRE_E_FIXTURES) == 14
```

Adding `family_a_zero_fee.pdf` makes that 15. Update the literal — and note what
that assertion is *for*: its own comment says it "guards the leg above against a new
fixture landing uncovered (its list is hand-written, so a glob mismatch is the
failure mode)". It is doing exactly its job here.

`_PRE_E_FIXTURES` has three references in that file and they must not be treated
alike:

| Reference | Effect of the new fixture |
|---|---|
| the `glob` definition | picks it up automatically |
| `assert len(_PRE_E_FIXTURES) == 14` | **goes red** — change to 15 |
| the FIBR-0190 D6 extraction leg (`@parametrize`) | gains a case, passes — it asserts the text lacks "statement opening balance", which §4.2's page does |

The **detection** leg is *not* in that list: it is parametrised over a hand-written
list of `(filename, expected_family)` pairs. Add `("family_a_zero_fee.pdf",
Family.A)` to it — cheap, and the ablation table shows detection is exactly what
breaks if the fixture's column header or legal marker is ever disturbed.

**The exception: INV-6's test cannot be seen red**, because it asserts a property of
a fixture this change introduces — there is no pre-fix state in which it fails
meaningfully. That is a guard against a future mistake, not a regression test, and
pretending otherwise would be the vacuous-red-run this project has been bitten by
before. It is written and run green, deliberately.

The existing `test_FIBR0216_zero_amount_row_degrades_instead_of_aborting_the_statement`
stays as it is. It calls `_parse_family_a` directly, which is why it has passed for
the whole life of this defect — it proves the family parser produces the error and
says nothing about whether `parse` returns it. INV-1's test is the boundary leg it
never had.

`error_count` currently has **no** test at all — `grep -rn "error_count" tests/ | wc
-l` → `0` — so INV-4 is net-new coverage of a FIBR-0085 deliverable, not a
duplicate. It is also the first invariant in the batch suite that is not a
restatement of FIBR-0085's, which is why §12 amends that suite's contract rather
than quietly adding a leg to it.

The INV-3 row claims no change to the corpus legs, and that is measured rather than
hoped. Parsing all 22 committed fixtures:

```
$ ls tests/features/standard_bank_pdf/fixtures/*.pdf | wc -l
22
```

11 parse and every one returns `errors=0`; 10 raise their friendly `ValueError` by
design; and `non_sb.pdf` returns `None`. No filename-pattern shorthand is given for
the ten, because the obvious one is wrong — `savings_no_closing.pdf` reads like a
raiser and is not (a closing-less Savings imports on the per-row gate alone, which
is §6's third case). Nothing in the corpus carries a `RowError` today, so no
existing draft list, preview row count or reconciliation moves.

## 8. Alternatives considered (and rejected)

- **Fix it during the FIBR-0085 close, in passing.** Rejected by the user: the
  preview ripple is a visible behaviour change and deserves its own test surface. A
  one-line diff with no test would also have left `error_count` untested, which is
  half of why the defect survived.
- **Make `_verify_checksum` count error rows, so a dropped row fails the import.**
  Rejected: a zero-amount row is *correct* to drop, and FIBR-0216 exists specifically
  to stop such a row aborting an otherwise perfect statement. Reporting it is the
  fix; refusing the statement is a regression.
- **Surface the errors as a warning dialog instead of preview rows.** Rejected: the
  preview already has a row-level error affordance built for CSV (interleaved rows,
  highlighted, with the reason in the description column) and a count in the summary.
  A second mechanism for the same fact is two things to keep in agreement.
- **Fix the misleading all-rows-failed banner in the same change.** Rejected as
  scope — it is a pre-existing defect on a different code path with its own remedy
  decision to make (§9).

## 9. Out of scope

Two pre-existing reporting defects that this fix makes newly reachable on Standard
Bank files, plus the parser gap §6 uncovered. This section is where each one's
deferral is decided; §6 states what the defects *are*, and §1 and §8 point here:

- The FIBR-0146 D7 preview banner's CSV-only advice on a PDF or OFX import —
  **FIBR-0253**.
- `report_line`'s Status/Errors contradiction on an `already_imported` file, and its
  "1 rows couldn't be read" pluralisation — **FIBR-0254**.

Also out of scope:

- **Closing the silent under-import §6's third case describes** — **FIBR-0255**. A
  money-moving error row on a statement that prints no closing balance passes every
  gate, because on those layouts there is no gate to pass. Fixing it means giving
  the parser a completeness check it does not have, which is a parser change with
  its own design questions (Savings *legitimately* prints no closing, so this cannot
  just become an all-or-nothing refusal). This spec ships the visibility half, which
  is what belongs to the error channel. **Filed rather than left to a future
  reader's judgement**: it is the most consequential thing this review surfaced, and
  a verified money-losing path with no tracked owner is worse than the two cosmetic
  reporting defects that did get bullets.
- The other importers' error handling — `csv_importer` and `ofx_importer` are the
  only other **importer entry points** producing a `ParseResult`, and both already
  propagate correctly. (Constructions of the type are more numerous: `standard_bank`
  builds five more inside its family parsers, and those are the ones whose errors
  §4.1 finally forwards.)

## 10. Resource cost

No new state, no new build target, no new dependency (§4.2 covers reportlab's
probe-only status). The errors list is already constructed by the family parser on
every parse and is currently discarded; propagating it retains a list bounded as
§4.3 describes.

One new artefact: the committed fixture, **~1.8 KB** — the page is thirteen lines of
Helvetica text with no images or embedded fonts beyond the base set.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors` |
| INV-2 | `test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors` (row-number assertions) |
| INV-3 | `test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors` — its span / closing / amount assertions. **Not** the corpus legs: they carry no `RowError`, so they cannot regress on this change (INV-3's own note) |
| INV-4 | `test_batch_import.py::test_FIBR0252_error_count_is_set_for_a_standard_bank_file` (field) + `test_batch_import_ui.py::test_FIBR0252_errors_column_shows_the_count` (rendered cell) |
| INV-5 | `test_standard_bank.py::test_FIBR0252_preview_shows_the_error_row` |
| INV-6 | `test_standard_bank.py::test_FIBR0252_fixture_is_synthetic` — the repo-wide corpus guard cannot read `.pdf` bytes, so this is the only check on the new fixture |
| The batch report line's ", N rows couldn't be read" clause | **nothing** — and it is worth being exact about why, because "transitively covered by INV-4" is the tempting answer and it is false. `report_line` appends the clause only on its `committed` branch; INV-4's tests *scan*, and never commit, so that branch is unexecuted. Its wording defects are deferred as FIBR-0254 |
| §6's silent under-import (a money-moving error row on a statement with no printed closing) | **nothing**, deliberately — no gate exists to assert. This spec makes the row *visible*; closing the gap is FIBR-0255 (§9) |
| INV-2's **general** partition claim (beyond the fixture's three rows) | **nothing** — it rests on reading `_split`, a two-comprehension partition over one list. Listed rather than left implicit, since INV-2's row above cites only the fixture's row-number assertions |
| §4.3's row-cap claim (`_MAX_PDF_ROWS` bounds drafts, not errors) | **nothing** — no test asserts the cap's operand; the existing `_MAX_PDF_ROWS` monkeypatch legs pass either way. Left as a limit, not a defect: the upstream `region_lines` gate is the real bound |
| §4.3's `ImportResult.error_count` becoming non-zero for SB | **nothing** — knowingly unguarded. Nothing on the single-file path reads the field (verified: only `BatchReviewWidget` reads `error_count`, and off `BatchFile`), so there is no observable behaviour to assert. A test would pin a value no user can see |

## 12. Cross-doc impact

- `tests/features/standard_bank_pdf/spec.md` — an enumerated list rather than a
  stated count, so it can be worked as a checklist without the count and the items
  drifting apart:

  1. **The "Enforces" header** names `FIBR-0050` and `FIBR-0190`; add
     `FIBR-0252-standard-bank-row-errors.md` — in the `<ID>-<topic>.md` form this
     project now uses. The two existing names predate that rule; do not copy them.
  2. **The "Two specs, two `INV-N` numberings" note.** A bare `INV-N` there means
     FIBR-0050's, whose INV-1…INV-14 collide with all six of this spec's. Update it
     to three specs and three numberings, and qualify this spec's citations as
     `FIBR-0252 INV-N` — the same treatment the batch bullet below gets.
  3. **The `RowError` channel.** That file documents the *raising* gates and their
     distinct messages but never the degrade-per-row channel; add that clause.
  4. **The fixture pointer**, in the form it already uses for Family E ("the recipe
     is `docs/specs/FIBR-0190.md` § 4.6"): `family_a_zero_fee.pdf`'s recipe is §4.2
     of this spec.
  5. **The two prose occurrences of "14 pre-E fixtures" get *different* treatment**,
     because the two legs they describe read different lists. Do not bulk-replace.
     The file holds the figure as prose twice and contains no `_PRE_E_FIXTURES`
     symbol at all, so grepping for the constant finds nothing.
     - The **FIBR-0190 D6 extraction** occurrence describes the leg parametrised
       over `_PRE_E_FIXTURES`, which is a glob. It gains this fixture: **14 → 15**.
     - The **detection** occurrence ("every one of the 14 pre-E fixtures still
       detects as the family it detected as before") describes a leg parametrised
       over a **hand-written list of `(filename, expected_family)` pairs**, which no
       glob touches. Leave its number at 14 and its "as before" clause intact — both
       are true of those 14, and a fixture created now has no "before". Add a
       sentence naming `family_a_zero_fee.pdf` as a post-E addition expected to
       detect as Family A.

     Note the term itself: "pre-E" now names a glob containing a post-E fixture. The
     constant keeps its name (renaming it is churn across two files for no
     behavioural gain) — say so explicitly in the contract rather than leaving a
     reader to wonder.
- `tests/features/batch_import/spec.md` — its Fixtures paragraph opens "Synthetic
  strings only", which INV-4's test makes untrue; amend **that clause specifically**.
  The rest of the paragraph still holds and must not be swept away with it: the fake
  decrypt function is untouched (the new fixture is unencrypted), and "No `.pdf`
  file is committed under this directory at all" — the premise of its INV-12
  rationale — stays literally true, since the fixture lives in the sibling suite.
  That file also states every invariant in it is a restatement of FIBR-0085's, and
  it already numbers INV-1…INV-15; INV-4 here would collide with a different INV-4
  there. Adopt the convention the SB suite already uses for exactly this ("**Two
  specs, two `INV-N` numberings.** A bare `INV-N` below means FIBR-0085's; this
  spec's are qualified at the citation site as `FIBR-0252 INV-4`").
- `CHANGELOG.md` — one **Fixed** entry.
- `ROADMAP.md` — FIBR-0252 → 🚧 at implementation start, → ✅ at close; correct that
  bullet's "all six SB families" to five (§2); FIBR-0253 and FIBR-0254 filed (done).
  **Also correct FIBR-0253's own rationale**, which says the banner is reachable
  because "a Family A or E statement prints no closing balance, so
  `_verify_checksum` returns early" — §6 shows that is the wrong reason and
  understates the reach: it is reachable on every family.
- **No change needed to the four specs that own the code being touched**, assessed
  rather than left silent:
  - `FIBR-0085-batch-statement-import.md` — its §4.2 `error_count` contract was
    always correct; this makes it true on the Standard Bank path rather than
    amending it.
  - `FIBR-0050.md` and `FIBR-0190.md` — they specify the parser's grammars and
    gates, none of which move. The errors channel they already describe simply
    reaches its caller.
  - `FIBR-0216.md` — it introduced `_draft`'s degrade-per-row `RowError` and is the
    reason the errors exist at all. Its contract is unchanged; this spec is what
    finally delivers its output to a user. Worth noting for a future reader: that
    spec's "the reachable case is a printed `0.00` line" is narrower than the seven
    classes §6 enumerates, but it says *reachable case*, not *only case*, so it is
    imprecise rather than wrong — left alone deliberately.
  - `FIBR-0146` — its D7 banner's **trigger** is unchanged (still count-based); only
    its reach widens, to PDF sources. Amending that spec belongs to FIBR-0253, which
    owns the remedy decision, not here.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-08-06 | 3 (cold, shared packet, no prior-loop briefing) | 0 | 3 | 6 | 12 | 21 verified, 2 dismissed. All 21 fixed. Dimensions: dim 2×7, dim 5×5, dim 6×4, dim 15×3, dim 7×3, dim 13×2, dim 1×2, dim 4×2, dim 11×1. The three HIGHs were all §-level accuracy, and all three lanes ranked the same one first: §4.3's "errors have never reached `commit_import`" is **false** — `ImportService.commit_import` derives `ImportResult.error_count` from `len(preview.errors)`, so that field stops being a constant zero for SB files (verified as observable-by-nobody: no single-file surface reads it, now a `nothing` row in §11). Second, INV-4's test breaks `tests/features/batch_import/spec.md`'s "synthetic strings only" fixture policy, which §12 had not budgeted for. Third, §1's "no other behaviour changes" understated the tail (the batch report line gains ", N rows couldn't be read"). Two MEDIUMs were the same factual error found independently by all three lanes: §6 claimed Family B/C/D reject an all-errored statement, but with zero drafts `_verify_checksum` compares `abs(opening)` to `abs(closing)` and a fee-only month reconciles **by construction** — the very error class this spec is about. Family E qualified too (`_verify_e_totals` raises only when a total prints). Also: §2's consumer count was five, not six (`report_line` omitted); INV-2 over-claimed over unmatched region lines; the wizard class is `ImportWizardWidget`. **Dismissed:** the missing TOC (2 of 3 recent siblings carry none — not this corpus's convention) and "everything else follows from §2" (the skeleton's own prescribed wording). Phase 4c caught two errors in the loop's *own* fixes before commit: the fixture count is 22, not 21, and both re-stated tallies were corrected. Doc 296 → 406 lines. |
| 2 | 2026-08-06 | 3 (cold, shared packet, no prior-loop briefing) | 0 | 4 | 8 | 14 | 26 verified, 1 dismissed. All 26 fixed. **No loop-1 finding resurfaced** — those fixes held. Dimensions: dim 2×6, dim 5×6, dim 6×5, dim 4×4, dim 15×3, dim 7×2, dim 1×2, dim 10×2, dim 9×1, dim 11×1. **Origin split: ~8 collateral vs ~3 draft defects — collateral dominates, so the response was 4b + consolidation, not a reflex loop 3.** The worst finding was collateral of loop 1's own fix: §6's "the only reachable `RowError` is 'amount must be non-zero'" is false — `parse_transaction` has **seven** rejection classes, so a money-moving row (blank description, garbled date, unstorable amount) can error, and then the surviving drafts no longer reconcile and `parse` **raises** instead of previewing. Verified by running it: a Family A page whose middle row moves 100.00 under a blank description gives `errors: [(2, 'description must not be empty')]` and a 15000-vs-105000 mismatch. §6 is now split by whether the errored rows moved money. Loop 1's Family E carve-out was wrong for the same reason in reverse: a fee-only month prints `Payments 0.00`, which **matches** zero drafts, so E previews too — only a non-zero printed total rejects. §1 contradicted §6 on family reach (all 3 lanes) and mis-routed two of three consequences to §4.3. Draft defects: **INV-3's test surface was vacuous** — the 22 corpus fixtures carry no `RowError`, so they pass identically before and after and cannot pin the invariant; INV-3 now rests on the new fixture's span/closing/amount assertions, and says why the corpus is not the guard. New **INV-6**: nothing checked the committed binary fixture is synthetic, because the repo-wide corpus guard skips `.pdf` bytes — on a public money-app repo that gap earns its own invariant. §4.2's "every line is load-bearing" was false and is now a **measured ablation table** (each of the 13 lines dropped in turn and re-parsed; 4 are decoration, including the `Month-end Balance` line all three lanes guessed was structural). Filed **FIBR-0254** (batch report line contradicts the Errors column on `already_imported`, and mis-pluralises "1 rows"). **Dismissed:** "everything else follows from §2" (skeleton wording, reworded anyway). The thrice-raised TOC finding was **conceded rather than dismissed a third time** — a section index costs 6 lines and ends a recurring non-finding. Phase 4b again caught drift from this loop's own fixes: §11's INV-3 row still named the corpus the same edit had just demoted. Doc 406 → 495 lines. |
| 3 | 2026-08-06 | 3 (cold, shared packet, no prior-loop briefing) | 1 | 7 | 6 | 12 | 26 verified, 0 dismissed. All 26 fixed. **No loop-1 or loop-2 finding resurfaced.** Dimensions: dim 5×8, dim 2×5, dim 4×4, dim 6×4, dim 15×3, dim 7×3, dim 10×2, dim 1×2, dim 9×2. **The CRITICAL is the run's most valuable finding and it is a draft defect, not collateral.** §6's money-moving case claimed the balance gate always raises; `_verify_checksum` takes a `closing is None` early return on Family A and E, so a **closing-less Savings statement** with a money-moving error row raises nothing. Reproduced end-to-end: `bad date, NO closing → drafts=2 sum=15000 errors=[]` against a page that really moves `+50` — a 100.00 transaction vanishing with wrong totals and **no gate firing**, versus `bad date, WITH closing → RAISES`. That case is now §6's third branch, and it is the strongest argument for the fix: FIBR-0252 converts it from silent to reported. The same probe **corrected loop 2's own example**: a blank description is NOT reachable through `parse` (the grammar needs a description, so `_MISPARSE` fires upstream of `_draft`) — it is only reachable on a hand-built line at the `_parse_family_a` level, which is how loop 2 came to believe it. The reachable money-moving class is a garbled date. **Verified doc-vs-code placement error** (lane C): INV-4's test was filed in `test_batch_import.py`, which has zero `qtbot`; all 43 Qt legs live in `test_batch_import_ui.py` — INV-4 is now two legs in two files. **A ripple all three lanes only suspected and the orchestrator confirmed**: the SB suite *globs* its fixtures directory and asserts `len(_PRE_E_FIXTURES) == 14`, so committing the fixture makes it 15 and turns an existing test red — "no existing test is modified" was false, and §7 now names the literal to change. All three lanes independently caught the ablation table omitting `SERVICE FEE WAIVED` (the fixture's whole reason to exist, and a regenerator dropping it would make four invariants vacuous) and INV-6's `FAKE …` prefix rule, which cannot pass against §4.2's own page. Also: §11's "covered transitively by INV-4" was false (`report_line`'s clause is on the `committed` branch; INV-4 only scans) → now a `nothing` row; §12 was silent on the SB suite's INV-numbering collision while solving the identical one next door; the `2 × _MAX_PDF_ROWS` figure was derived from the word "couple" in a comment and is withdrawn rather than invented. Doc 495 → 575 lines. |
| 4 | 2026-08-06 | 3 (cold, shared packet, no prior-loop briefing) | 0 | 2 | 10 | 14 | 26 verified, 0 dismissed. All 26 fixed. **No finding from loops 1–3 resurfaced.** Dimensions: dim 4×7, dim 5×6, dim 2×5, dim 6×5, dim 15×3, dim 1×2, dim 10×2, dim 7×1, dim 12×1. **The signal that matters: zero findings about code behaviour.** Every prior loop produced at least one claim about the code that was wrong (loop 1 `commit_import`; loop 2 the `RowError` classes and Family E; loop 3 the CRITICAL silent under-import); this loop produced none, and the two HIGHs were the same §12 checklist defect found by all three lanes. The document's claims about the code have stopped being wrong, which is the property the loop exists to establish. Best judgement call of the loop, and it was against a standing project rule of mine: §6's verified money-losing path was left with "raise it if the reported errors show it happening" while two *cosmetic* defects got roadmap bullets — the most consequential finding in the run had no owner. **Filed as FIBR-0255.** §12's SB bullet said "four changes" and gave five, and pointed at a `_PRE_E_FIXTURES` symbol that does not exist in the file it names (verified: 0 occurrences; the count lives there as prose **twice**, at lines 66 and 100). Rewritten as an enumerated 5-item checklist so a count and its items cannot drift apart again. Also: §5's security preamble cited four defences as "listed in §4.3" where only one is; §4.2's Family A justification contradicted §6; §6's bullet title said "every row errors" while two of its three branches are the ordinary one-bad-row case — the branch carrying the spec's strongest argument. Two open questions resolved by measurement rather than argument: `spec_query` parses **6** invariants (an earlier packet's "5" was a stale pre-loop-1 reading), and `_parse_family_e` on a zero-delta row does return `errors: [(2, 'amount must be non-zero')]`, so §6's Family E claim is now measured. Doc 575 → 638 lines. |
| 5 | 2026-08-06 | 3 (cold, shared packet, no prior-loop briefing) | 1 | 3 | 6 | 12 | 22 verified, 0 dismissed. All 22 fixed. **Nothing from loops 1–4 resurfaced.** Dimensions: dim 6×6, dim 2×5, dim 4×4, dim 5×4, dim 7×2, dim 1×2, dim 15×2, dim 10×2, dim 9×1, dim 13×1, dim 12×1. **Origin split: ~7 collateral vs ~2 draft defects — the CRITICAL and both §12 HIGHs were all loop 4's own fixes, and that is why this is the last loop.** The CRITICAL: loop 4's new batch-path sentence misread FIBR-0085 INV-10's "span exists" as the *parse's* span. Verified against `BatchImportService.review` — it reads `StatementPeriodRepository.id_for_span`, a `statement_periods` row **already in the vault** — so a FIRST import lands `ready` → `committed` and the report line *does* append the clause; the Status/Errors contradiction is **re-import only**. §6 now splits the two, and FIBR-0254's bullet was annotated with the precondition. Loop 4's §12 item 5 was self-contradicting ("→ 15" *and* "scope to the 14"), and the orchestrator's check found why both lanes were right to distrust it: `_PRE_E_FIXTURES` has three references and the **detection** leg is not among them — it is parametrised over a hand-written `(filename, expected_family)` list a glob never touches. Item 5 is now two instructions for two legs, and §7 gained a reference table plus a new detection-list entry. Draft defect worth the loop on its own: **INV-6 said "no real bank data" while the fixture's required detection marker is a real company registration number** — an invariant falsified by content the ablation table proves cannot be removed; scoped to customer/account data with the marker as a named exception. Also: §9's "only other producers of a `ParseResult`" was false (`standard_bank` builds five more internally) → "importer entry points"; the recipe gained its reportlab API and version; the preview-table render widening is now stated rather than dismissed in four words. **Converged** — not because a loop came back clean, but because the findings are now overwhelmingly self-generated: each loop's prose produces the next loop's findings, while the document's claims about the *code* have been stable and verified since loop 4. Doc 638 → 714 lines — large for a one-line fix, and the size is evidence rather than padding (the ablation table, three measured transcripts, the cross-doc checklist). |
