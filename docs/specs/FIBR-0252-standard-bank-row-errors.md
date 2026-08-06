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
reports that row — in the single-file preview's row table and summary line, and in
the batch review step's **Errors** column — the same way a CSV or OFX statement
already does. No other behaviour changes: the same drafts import, against the same
balance checks, with the same coverage span.

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
3. **Every consumer downstream is already correct and is being starved.**
   `ImportService._preview_from_result` carries `result.errors` into
   `ImportPreview.errors`; `ImportWizard._fill_preview_table` interleaves error rows
   into the preview by `row_number`; `_apply_preview_counts` renders "· N error";
   `BatchImportService` sets `BatchFile.error_count = len(parsed.errors)` and
   `ui/import_batch.py` renders it in the Errors column. All five read an empty list
   for every Standard Bank statement.

FIBR-0085 §4.2 introduced `error_count` on exactly this reasoning — "a file where 40
of 50 rows failed commits 10 and would report '10 added' with no hint that 40
vanished; in a money app a silently dropped row is the defect". That argument is
defeated on the Standard Bank path, which is the path this user's own corpus is made
of.

**Reproduced, end to end, before writing this spec.** A synthetic Family A statement
carrying `SERVICE FEE WAIVED 0.00 05 03 900.00` between two ordinary rows:

```
$ python - <<'PY'   # PYTHONPATH=src, scratchpad fixture
from finbreak.importers.standard_bank import StandardBankImporter
r = StandardBankImporter().parse(open(FIXTURE,'rb').read(), 2)
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
suite's established pattern (reportlab-generated fake data plus the Standard Bank
legal marker; reportlab stays probe-only and is not added as a dependency — the
generated PDF is what is committed). Its transaction region:

```
BALANCE BROUGHT FORWARD 05 01 1,000.00
FAKE SHOP PURCHASE 100.00- 05 02 900.00
SERVICE FEE WAIVED 0.00 05 03 900.00
FAKE SALARY DEPOSIT 250.00 05 04 1,150.00
Balance at date of statement 1,150.00
```

Verified to parse as 2 drafts (rows 1 and 3) with the zero-amount row as row 2, and
to reconcile — `1,000.00 − 100.00 + 250.00 = 1,150.00`, so the completeness gate
passes and the error is the *only* thing that distinguishes fixed from broken. That
matters for INV-1: the test must fail pre-fix for the reason under test, not because
the statement was rejected outright.

Family A is chosen because it is the layout whose real-world corpus carries waived
fees, and because its checksum path is the one that stays green with a row missing.

### 4.3 What does not change

Stated because a reviewer of the diff will reasonably ask, and because two of these
would be tempting "improvements" that would break the contract:

- **The completeness gate.** `_verify_checksum` and `_verify_e_totals` keep summing
  `result.drafts` only. Error rows carry no money; folding them in would make a
  waived fee look like a truncated statement.
- **The row cap.** `_MAX_PDF_ROWS` keeps bounding `len(result.drafts)`. Error rows
  are already bounded upstream by the `len(region_lines) > _MAX_PDF_ROWS` gate, so
  propagation opens no new unbounded-input surface.
- **Commit.** `commit_import` writes drafts; errors have never reached it and still
  do not.
- **The dedup delta, the coverage span, the closing balance and the
  `SourceAccountHint`** — all computed from drafts and the document, untouched here.

## 5. Invariants

No trust boundary moves: the change is inside an already-untrusted-input path whose
existing defences (`_MAX_PDF_PAGES`, `_MAX_PDF_ROWS`, the pdfplumber boundary catch,
the in-memory decrypt) are all upstream of it and are listed as unchanged in §4.3.

- **INV-1** — `StandardBankImporter.parse` returns every `RowError` its family
  parser produced; the errors channel is never replaced by a literal.
  *Test:* `tests/features/standard_bank_pdf/test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors`
  — parses `family_a_zero_fee.pdf` and asserts
  `[(e.row_number, e.reason) for e in r.errors] == [(2, "amount must be non-zero")]`.
  Its pre-fix result is already observed: the same call returns `errors: []` (§2).
  *Breaks when:* any `ParseResult` construction in `parse` passes a literal in the
  errors position, or filters `result.errors`.

- **INV-2** — drafts and errors partition the statement's parsed rows: a row that
  errored is absent from `drafts` and present in `errors`, and no row is in both or
  in neither.
  *Test:* the same test asserts `[d.row_number for d in r.drafts] == [1, 3]`
  alongside the error at row 2, so the union is `{1, 2, 3}` with no overlap.
  *Breaks when:* `_split`'s partition changes, or a future caller appends an error
  row to `drafts` to "keep the numbering contiguous".

- **INV-3** — propagating errors changes no draft, no span, no closing balance and
  no checksum outcome. A statement that imported before imports identically.
  *Test:* the existing Standard Bank corpus legs in
  `tests/features/standard_bank_pdf/test_standard_bank.py`, unmodified, still pass —
  they assert draft counts, amounts and reconciliation across all five families.
  *Breaks when:* someone widens `_verify_checksum` to include error rows, or makes
  the row cap count them.

- **INV-4** — the batch review step's Errors column shows a non-zero count for a
  Standard Bank file with an unimportable row.
  *Test:* `tests/features/batch_import/test_batch_import.py::test_FIBR0252_error_count_is_set_for_a_standard_bank_file`
  — scans `family_a_zero_fee.pdf` and asserts the record's `error_count == 1`.
  *Breaks when:* `BatchImportService` stops setting `error_count` from
  `len(parsed.errors)`, or the scan path stops reaching the preview.

- **INV-5** — the single-file preview interleaves the error row into the row table
  in file order, and counts it in the summary line.
  *Test:* `tests/features/standard_bank_pdf/test_standard_bank.py::test_FIBR0252_preview_shows_the_error_row`
  — drives the wizard over the fixture with `qtbot` and asserts the preview table
  holds 3 rows with row 2 labelled "Error", and that the summary line ends "· 1
  error".
  *Breaks when:* `_fill_preview_table` stops interleaving, or
  `_apply_preview_counts` stops counting `preview.errors`.

## 6. Failure modes

- **Every row of a statement errors.** On Family B/C/D the statement is rejected
  before the preview, because those layouts always print a closing balance and
  `_verify_checksum` raises when zero drafts cannot reconcile against it. On Family
  A and E the closing may be absent, `_verify_checksum` returns early, and the
  preview is reached as *0 new · 0 duplicate · N error* — which then trips the
  FIBR-0146 D7 banner, whose text names the CSV column-mapping step that no PDF
  import visits. That misleading banner is pre-existing (already reachable via OFX,
  which collects per-row errors today) and is **out of scope** — see §9.
- **A statement with many error rows.** Bounded upstream: `len(region_lines) >
  _MAX_PDF_ROWS` rejects before any per-row work, so the errors list cannot grow
  past that cap. No new memory or render bound is needed.
- **The fixture stops producing an error** — e.g. `parse_transaction` is one day
  changed to accept zero amounts. INV-1's test goes green-for-the-wrong-reason risk
  is covered by INV-2's row-numbers assertion in the same test: if the zero row
  became a draft, `[d.row_number for d in r.drafts]` would be `[1, 2, 3]` and the
  test fails rather than silently passing on an empty comparison.

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

`error_count` currently has **no** test at all — `grep -rn "error_count" tests/`
returns nothing — so INV-4 is net-new coverage of a FIBR-0085 deliverable, not a
duplicate.

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
  scope: it is a pre-existing defect on a different code path, with its own remedy
  decision to make. Filed as FIBR-0253.

## 9. Out of scope

- The FIBR-0146 D7 preview banner's CSV-only advice on a PDF or OFX import —
  tracked by **FIBR-0253**.
- Dedicated ABSA / Nedbank / FNB readers and any other importer's error handling —
  `csv_importer` and `ofx_importer` already propagate correctly.

## 10. Resource cost

None — no new state, no new build target, no new dependency. The errors list is
already constructed by the family parser on every parse and is currently discarded;
propagating it retains a list bounded by `_MAX_PDF_ROWS`. reportlab is used once to
generate the committed fixture and is not added to any dependency group.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors` |
| INV-2 | `test_standard_bank.py::test_FIBR0252_parse_propagates_row_errors` (row-number assertions) |
| INV-3 | the existing `test_standard_bank.py` corpus legs across families A–E |
| INV-4 | `test_batch_import.py::test_FIBR0252_error_count_is_set_for_a_standard_bank_file` |
| INV-5 | `test_standard_bank.py::test_FIBR0252_preview_shows_the_error_row` |
| §4.3 "the row cap keeps bounding drafts only" | **nothing** — no test asserts the cap's operand; the existing `_MAX_PDF_ROWS` monkeypatch legs pass either way. Left as a limit, not a defect: the upstream `region_lines` gate is the real bound |

## 12. Cross-doc impact

- `tests/features/standard_bank_pdf/spec.md` — gains a per-row-errors clause; it
  currently documents no error contract at all, which is how the boundary gap went
  unnoticed.
- `CHANGELOG.md` — one **Fixed** entry.
- `ROADMAP.md` — FIBR-0252 → 🚧 at implementation start, → ✅ at close; FIBR-0253
  filed (done).
- No change to `docs/specs/FIBR-0085-batch-statement-import.md`: its §4.2
  `error_count` contract was always correct, and this makes it true on the Standard
  Bank path rather than amending it.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
