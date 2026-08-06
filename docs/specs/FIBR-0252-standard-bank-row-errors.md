# FIBR-0252 — Propagate Standard Bank per-row errors to the import preview

**Status:** spec draft (2026-08-06).
**Kind:** fix.
**Source:** ROADMAP FIBR-0252 (code-quality-review-2026-08-06, FIBR-0085 close, service lane).

**Pairs with:** FIBR-0085 (the batch review step, whose Errors column this makes truthful).

*Layman: when a line on a Standard Bank statement cannot be read, the app currently
throws that fact away and tells you "53 added" with no hint that anything was
skipped. After this, the skipped line is counted and shown.*

## 1. Goal

`StandardBankImporter.parse` returns the per-row errors its family parser produced,
instead of an empty list. A Standard Bank statement carrying an unimportable row
reports that row — in the single-file preview's row table and summary line, in the
batch review step's **Errors** column, and in the batch per-file report line, which
appends *", N rows couldn't be read"* — the same way a CSV or OFX statement already
does.

**No draft, balance-check or coverage-span behaviour changes**: the same rows
import, against the same gates, with the same span. Three consequences do follow,
and §4.3 accounts for each rather than claiming nothing moves — the batch report
line above; `ImportResult.error_count`, which stops being a constant zero for
Standard Bank files; and one pre-existing banner that becomes newly reachable on
Family A and E (§6, tracked as FIBR-0253).

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
   appends *", N rows couldn't be read"* in `report_line`. All six read an empty list
   for every Standard Bank statement.

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
$ PYTHONPATH=src python - "$SCRATCH/family_a_zero_fee.pdf" <<'PY'
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

- **The user asked for this as its own item**, rather than as a fix in passing
  during the FIBR-0085 close, precisely because it changes what the single-file
  preview shows (2026-08-06). That is honoured: the preview change is specified and
  tested here, not left as a side effect.
- Everything else below follows from §2.

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

**The whole page, not just the rows** — the sibling suite commits no generator
script, so the recipe has to be here or the fixture cannot be regenerated. Every
line below is load-bearing: without the `Statement from … to …` line `_parse_period`
returns `None` and Family A raises `_MISPARSE` before any row is read, and without
the legal marker `detect_standard_bank` returns `None` and `parse` never reaches a
family at all.

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
no-real-data rule binds fixtures absolutely.

Observed on an equivalent scratchpad build of this page: 2 drafts (rows 1 and 3),
the zero-amount line as row 2, `period_start`/`period_end` `2026-05-01` /
`2026-05-31`, and a reconciling `1,000.00 − 100.00 + 250.00 = 1,150.00` so the
completeness gate passes. That last part matters for INV-1: the test must fail
pre-fix for the reason under test, not because the statement was rejected outright.

Family A is chosen because it is the layout whose real-world corpus carries waived
fees, and because its checksum path is the one that stays green with a row missing.

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
- **The row cap.** `_MAX_PDF_ROWS` keeps bounding `len(result.drafts)`. Error rows
  are bounded upstream instead, by the `len(region_lines) > _MAX_PDF_ROWS` gate —
  not by the cap itself but by a small constant multiple of it, since `parse`'s own
  comment notes a region line can yield "at most a couple of drafts" (Family C
  de-interleaving). Either way the input is bounded before any per-row work, so
  propagation opens no new unbounded-input surface.
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
existing defences (`_MAX_PDF_PAGES`, `_MAX_PDF_ROWS`, the pdfplumber boundary catch,
the in-memory decrypt) are all upstream of it and are listed as unchanged in §4.3.

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
  `continue`s, and an unmatched line raises `_MISPARSE` rather than degrading. They
  are in neither channel by design, and widening INV-2 to cover them would state a
  contract the code does not implement.

- **INV-3** — propagating errors changes no draft, no span, no closing balance and
  no checksum outcome. A statement that imported before **commits** identically —
  the same rows, the same span, the same stored closing balance. What changes is
  what the import *reports*.
  *Test:* the existing Standard Bank corpus legs in
  `tests/features/standard_bank_pdf/test_standard_bank.py`, unmodified, still pass —
  they assert draft counts, amounts and reconciliation across all five families.
  Measured for this spec: of the 22 committed fixtures, the 11 that parse return
  `errors=0`, 10 raise by design, and `non_sb.pdf` returns `None`. So no existing
  leg's preview or draft list moves.
  *Breaks when:* someone widens `_verify_checksum` to include error rows, or makes
  the row cap count them.

- **INV-4** — a Standard Bank file with an unimportable row carries a non-zero
  `BatchFile.error_count`, and the review table renders it in the Errors column.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_FIBR0252_error_count_is_set_for_a_standard_bank_file`
  — scans `family_a_zero_fee.pdf`, asserts the record's `error_count == 1`, and
  asserts the rendered `COL_ERRORS` cell reads `"1"`. Both legs are needed:
  `BatchReviewWidget._number` blanks a zero, so the field and its rendering are
  separate claims and only the second is what the user sees.
  *Breaks when:* `BatchImportService._settle_parse` stops setting `error_count` from
  `len(parsed.errors)`, the scan path stops reaching the preview, or `_number`
  stops rendering a non-zero count.

- **INV-5** — the single-file preview interleaves the error row into the row table
  in file order, and counts it in the summary line.
  *Test:* `tests/features/standard_bank_pdf/test_standard_bank.py::test_FIBR0252_preview_shows_the_error_row`
  — drives the wizard over the fixture with `qtbot` and asserts the preview table
  holds 3 rows with row 2 labelled "Error", and that the summary line ends "· 1
  error".
  *Breaks when:* `_fill_preview_table` stops interleaving, or
  `_apply_preview_counts` stops counting `preview.errors`.

## 6. Failure modes

- **Every row of a statement errors.** This reaches the preview as *0 new · 0
  duplicate · N error* on **every family**, not just the closing-less ones — and the
  reasoning that says otherwise is the trap worth recording, because it is the one
  this spec's own error class defeats.

  `_verify_checksum` compares `abs(opening ± Σ drafts)` against `abs(closing)`. With
  every row errored, `Σ drafts` is `0`, so the comparison is `abs(opening) !=
  abs(closing)` — and the only reachable `RowError` is "amount must be non-zero",
  which means the errored rows moved no money and the printed opening and closing
  are *equal by construction*. A fee-only month on Family B/C/D therefore
  reconciles and is previewed, not rejected. Family A likewise (its closing may be
  absent, taking the early return).

  Family E is the one genuine exception, and only partly: `_verify_e_totals` raises
  `_E_TOTALS_MISMATCH` when a printed `Payments`/`Deposits` total does not match the
  drafts, and zero drafts match no non-zero total. So an all-errored E statement is
  rejected **when either total prints**, and previewed only when neither does (the
  `family_e_no_totals.pdf` shape).

  Whichever family it arrives on, that preview trips the FIBR-0146 D7 banner, whose
  text names the CSV column-mapping step no PDF import visits. Pre-existing (already
  reachable via OFX, which collects per-row errors today) and **out of scope** — §9.
- **A statement with many error rows.** Bounded upstream: `len(region_lines) >
  _MAX_PDF_ROWS` rejects before any per-row work, so the errors list is bounded by a
  small constant multiple of that cap (§4.3). No new memory or render bound is
  needed.
- **The fixture stops producing an error** — e.g. `parse_transaction` is one day
  changed to accept zero amounts. The risk that INV-1's test then goes green for the
  wrong reason is covered by INV-2's row-number assertion in the same test: if the
  zero row became a draft, `[d.row_number for d in r.drafts]` would be `[1, 2, 3]`
  and the test fails, rather than silently passing on an empty comparison.

## 7. Tests

Three new tests plus the unmodified corpus. Each new test must be seen red against
pre-fix code before the fix lands; the INV-1 red state is already recorded in §2.

| Test | Lives in | Locks |
|---|---|---|
| `test_FIBR0252_parse_propagates_row_errors` | `tests/features/standard_bank_pdf/test_standard_bank.py` | INV-1, INV-2 |
| `test_FIBR0252_error_count_is_set_for_a_standard_bank_file` | `tests/features/batch_import/test_batch_import.py` | INV-4 |
| `test_FIBR0252_preview_shows_the_error_row` | `tests/features/standard_bank_pdf/test_standard_bank.py` (qtbot) | INV-5 |
| existing corpus legs, unmodified | `tests/features/standard_bank_pdf/test_standard_bank.py` | INV-3 |

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
design (the `*_fail`, `*_no_opening`, `*_no_closing`, `*_corrupt` fixtures); and
`non_sb.pdf` returns `None`. Nothing in the corpus carries a `RowError` today, so no
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

- The FIBR-0146 D7 preview banner's CSV-only advice on a PDF or OFX import —
  tracked by **FIBR-0253**. This is the single home for that deferral; §6 and §8
  point here.
- Every other importer's error handling — `csv_importer` and `ofx_importer` already
  propagate correctly, so there is nothing to change.

## 10. Resource cost

None — no new state, no new build target, no new dependency (§4.2 covers
reportlab's probe-only status). The errors list is already constructed by the family
parser on every parse and is currently discarded; propagating it retains a list
bounded as §4.3 describes.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors` |
| INV-2 | `test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors` (row-number assertions) |
| INV-3 | the existing `test_standard_bank.py` corpus legs across families A–E |
| INV-4 | `test_batch_import.py::test_FIBR0252_error_count_is_set_for_a_standard_bank_file` (field + rendered cell) |
| INV-5 | `test_standard_bank.py::test_FIBR0252_preview_shows_the_error_row` |
| §4.3's row-cap claim (`_MAX_PDF_ROWS` bounds drafts, not errors) | **nothing** — no test asserts the cap's operand; the existing `_MAX_PDF_ROWS` monkeypatch legs pass either way. Left as a limit, not a defect: the upstream `region_lines` gate is the real bound |
| §4.3's `ImportResult.error_count` becoming non-zero for SB | **nothing** — knowingly unguarded. Nothing on the single-file path reads the field (verified: only `BatchReviewWidget` reads `error_count`, and off `BatchFile`), so there is no observable behaviour to assert. A test would pin a value no user can see |

## 12. Cross-doc impact

- `tests/features/standard_bank_pdf/spec.md` — gains a per-row-error **channel**
  clause and the new fixture. It already documents the *raising* gates (the per-row
  and completeness gates and their distinct messages); what it has never documented
  is the degrade-per-row `RowError` channel, which is how the boundary gap went
  unnoticed.
- `tests/features/batch_import/spec.md` — its Fixtures paragraph says "Synthetic
  strings only … a **fake** decrypt function in place of any locked PDF", which
  INV-4's test makes untrue. Amend it to admit the cross-suite SB fixture, and note
  that the sentence its INV-12 rationale rests on ("No `.pdf` file is committed
  under this directory at all") still holds. Its invariants are otherwise all
  restatements of FIBR-0085's; the new leg is the first that is not, so label it as
  a FIBR-0252 invariant rather than renumbering into that suite's sequence.
- `CHANGELOG.md` — one **Fixed** entry.
- `ROADMAP.md` — FIBR-0252 → 🚧 at implementation start, → ✅ at close; correct that
  bullet's "all six SB families" to five (§2); FIBR-0253 filed (done).
- No change to `docs/specs/FIBR-0085-batch-statement-import.md`: its §4.2
  `error_count` contract was always correct, and this makes it true on the Standard
  Bank path rather than amending it.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-08-06 | 3 (cold, shared packet, no prior-loop briefing) | 0 | 3 | 6 | 12 | 21 verified, 2 dismissed. All 21 fixed. Dimensions: dim 2×7, dim 5×5, dim 6×4, dim 15×3, dim 7×3, dim 13×2, dim 1×2, dim 4×2, dim 11×1. The three HIGHs were all §-level accuracy, and all three lanes ranked the same one first: §4.3's "errors have never reached `commit_import`" is **false** — `ImportService.commit_import` derives `ImportResult.error_count` from `len(preview.errors)`, so that field stops being a constant zero for SB files (verified as observable-by-nobody: no single-file surface reads it, now a `nothing` row in §11). Second, INV-4's test breaks `tests/features/batch_import/spec.md`'s "synthetic strings only" fixture policy, which §12 had not budgeted for. Third, §1's "no other behaviour changes" understated the tail (the batch report line gains ", N rows couldn't be read"). Two MEDIUMs were the same factual error found independently by all three lanes: §6 claimed Family B/C/D reject an all-errored statement, but with zero drafts `_verify_checksum` compares `abs(opening)` to `abs(closing)` and a fee-only month reconciles **by construction** — the very error class this spec is about. Family E qualified too (`_verify_e_totals` raises only when a total prints). Also: §2's consumer count was five, not six (`report_line` omitted); INV-2 over-claimed over unmatched region lines; the wizard class is `ImportWizardWidget`. **Dismissed:** the missing TOC (2 of 3 recent siblings carry none — not this corpus's convention) and "everything else follows from §2" (the skeleton's own prescribed wording). Phase 4c caught two errors in the loop's *own* fixes before commit: the fixture count is 22, not 21, and both re-stated tallies were corrected. Doc 296 → 406 lines. |
