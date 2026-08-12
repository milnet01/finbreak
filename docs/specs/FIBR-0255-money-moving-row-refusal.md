# FIBR-0255 — Refuse a Standard Bank statement whose unreadable row moved money

**Status:** spec draft (2026-08-12).
**Kind:** fix.
**Source:** ROADMAP FIBR-0255 (in-session-2026-08-06, FIBR-0252 cold-eyes loop 3, reproduced; filed at loop 4).

**Pairs with:** FIBR-0216 (introduced `_draft`'s degrade-per-row channel, whose
safety premise this restores) and FIBR-0252 (made the degraded row visible; §8
records why its rejected alternative is not this one).

*Layman: on a savings statement that prints no closing balance, a line the app
cannot read is thrown away and the totals come out wrong, with nothing to tell
you. After this the app refuses the whole statement and says so.*

[1. Goal](#1-goal) · [2. Problem](#2-problem) · [3. Scope decisions](#3-scope-decisions-agreed-with-the-user) ·
[4. Design](#4-design) · [5. Invariants](#5-invariants) · [6. Failure modes](#6-failure-modes) ·
[7. Tests](#7-tests) · [8. Alternatives](#8-alternatives-considered-and-rejected) ·
[9. Out of scope](#9-out-of-scope) · [10. What checks this](#10-what-checks-this) ·
[11. Cross-doc impact](#11-cross-doc-impact) · [12. Cold-eyes loop log](#12-cold-eyes-loop-log)

## 1. Goal

A Standard Bank statement can no longer import a wrong total silently. When
`standard_bank.py::_draft` cannot turn a row into a `TransactionDraft` **and that
row moved money**, the parse raises the all-or-nothing `ValueError` instead of
degrading the row to a `RowError` — on every family, whether or not the statement
prints a figure any completeness gate can check. The degrade-per-row channel
FIBR-0216 introduced survives intact for the case its own reasoning covers: a row
whose amount is exactly zero.

## 2. Problem

`standard_bank.py::_draft` returns a `RowError` for **every** `parse_transaction`
rejection, and its docstring states why that is safe:

> A zero-amount row verified fine; it just carries no money. Dropping it leaves
> every running balance and the credit-card completeness gate untouched, since it
> contributes 0 to both.

That premise covers exactly one of `parse_transaction`'s seven rejections. The
others — a non-ISO date, a blank description, an over-precise amount, an
unstorable magnitude — can all fire on a row carrying a **non-zero** amount, and
the conclusion was applied to them anyway.

Three facts make the consequence a silent wrong total rather than a caught one:

1. `_verify_row` runs on the row **before** `_draft` sees it, so the running
   balance chain has already advanced past the row. The chain still reconciles;
   only the draft list is short.
2. `_verify_checksum` takes its `closing is None` early return for `Family.A` and
   `Family.E`. Family A Savings legitimately prints no closing figure.
3. `_verify_e_totals` degrades to `None` when neither printed `Payments`/`Deposits`
   total is present.

So on a closing-less Family A statement, and on a Family E statement printing
neither column total, **no gate is left to notice the shortfall**.

Reproduced at the parser level (this session), on a synthetic closing-less Savings
page whose middle row moves 100.00 under the invalid date `05 32`:

```
$ PYTHONPATH=src python -c '
from finbreak.importers.standard_bank import _parse_family_a
lines = ["BALANCE BROUGHT FORWARD 05 01 1,000.00",
         "GROCERIES 100.00- 05 02 900.00",
         "MYSTERY 100.00- 05 32 800.00",
         "SALARY 250.00 05 04 1,050.00"]
r = _parse_family_a(lines, 2, "us", ("2026-05-01", "2026-05-31"))
print(sum(d.amount_minor for d in r.drafts), [(e.row_number, e.reason) for e in r.errors])'
15000 [(2, 'occurred_on must be a valid ISO-8601 date')]
```

The page really moves −100 −100 +250 = **+50**; the import takes **+150**. A
transaction worth 100.00 vanishes and every total downstream — the account
balance, the month summary, the forecast anchor — is wrong by exactly that. The
same page **with** a printed closing raises `"this statement didn't add up …"`, so
the defect is entirely the absence of a gate, not a wrong gate.

This is pre-existing and not introduced by FIBR-0252, which is its mitigation
rather than its cause: FIBR-0252 made the dropped row visible in the preview and
the batch **Errors** column instead of discarding the only trace of it. That helps
a user who reads the preview; it does not stop the import.

## 3. Scope decisions (agreed with the user)

The user delegated the pick and the design for this session ("I defer to you on
what to tackle next … CHOOSE"). Two calls were made under that delegation, and
both are recorded here rather than in a commit message:

1. **Refuse at the row, rather than build a completeness gate for the
   closing-less layouts.** FIBR-0255's bullet offers both. §8 carries the
   reasoning for the one taken.
2. **The refusal message names no row number and no internal reason.** Every
   other refusal in this file is one sentence of plain English ending in *try
   your bank's CSV or OFX export*; `occurred_on must be a valid ISO-8601 date` is
   `parse_transaction`'s wording for a developer, not a statement a user can act
   on. §6 states what the user is left with instead.

## 4. Design

### 4.1 The guard, in `_draft` and nowhere else

`_draft` already owns the degrade decision for all five family parsers. The guard
goes there, keyed on the value the caller already hands it:

```python
def _draft(
    row: int, occurred_on: str, signed: Decimal, description: str, exponent: int
) -> TransactionDraft | RowError:
    try:
        occurred_on, amount_minor, description = parse_transaction(
            occurred_on, signed, description, exponent
        )
    except ValueError as exc:
        if signed != 0:
            raise ValueError(_UNREADABLE_MONEY_ROW) from exc
        return RowError(row, str(exc))
    return TransactionDraft(row, occurred_on, amount_minor, description)
```

`signed` is the money the row moved: the running-balance **delta** for Families
A/B/D/E, and the sign-flipped printed amount for Family C. `signed != 0` is
therefore exactly the negation of FIBR-0216's safety premise — "it contributes 0
to both" — and not an approximation of it.

**The discriminator is the amount, never the rejection reason** — the two are not
interchangeable, and reading them as equivalent is the one way to build this wrong.
`parse_transaction` checks the description and the date **before** the amount, so a
zero-amount row can be rejected for either. Measured against the current tree:

```
SERVICE FEE WAIVED 0.00 05 32 1,000.00   → RowError(1, 'occurred_on must be a valid ISO-8601 date')
## 0.00 05 02 1,000.00                   → RowError(1, 'description must not be empty')
```

Both still degrade, and correctly — the row moved no money, which is the whole of
FIBR-0216's premise. A guard keyed on `"amount must be non-zero"` would refuse the
statement for either, breaking INV-2.

In the other direction a non-zero `signed` cannot scale to a zero `amount_minor`:
`parse_transaction` rejects any amount with more fractional digits than the currency
allows **before** it scales, so no surviving non-zero Decimal can round away.

`_draft`'s docstring is rewritten in the same change. It currently reads
"degrading per row, **never** aborting the statement (FIBR-0216)", which this makes
false, and a docstring stating the opposite of the guard beneath it is what a later
reader would restore the old behaviour on.

### 4.2 The message

```python
_UNREADABLE_MONEY_ROW = (
    "couldn't read one of this statement's transactions, and it moved money — "
    "importing it would give you the wrong totals; try your bank's CSV or OFX export"
)
```

Deliberately **not** any of the four `"this statement didn't add up …"` messages.
The statement adds up — its running balance reconciles row by row, which is how
the row was verified before it was dropped. What failed is storing one row. Reusing
the arithmetic wording would misdiagnose the failure to the one person who has the
document in front of them, the same reasoning FIBR-0190 D8 used when it gave
`_E_TOTALS_MISMATCH` its own sentence rather than reusing `_verify_checksum`'s.

### 4.3 What does not change

- **`parse_transaction` is untouched.** It still raises `ValueError` for every
  rejection; the decision about what a rejection *means* stays in the importer
  that knows whether a running balance corroborated the row.
- **The CSV and OFX importers are untouched.** Neither has a running-balance
  chain, so neither can know a dropped row moved money; collecting `RowError`s is
  their whole contract (`tests/features/import_/spec.md` INV-4,
  `tests/features/ofx_import/spec.md` INV-3).
- **The `ParseResult.errors` channel stays live** for Standard Bank. A printed
  `0.00` row still degrades and still reaches the preview and the batch **Errors**
  column, which is FIBR-0252's whole deliverable.
- **No call site changes.** All five `_draft` call sites keep their bare
  comprehension or `parsed.append(...)` shape, and every caller of
  `StandardBankImporter.parse` already handles a `ValueError` from a balance gate:
  there are exactly two, and both already catch it
  (`grep -rn 'StandardBankImporter' src/ | grep -v standard_bank.py:` → two imports
  and two calls):

  - `services/batch_import.py::_scan_pdf` — the raise leaves it into `scan`'s
    `except (ValueError, OSError, FinbreakError)`, which calls `_fail`, marking the
    file `failed` with the message as its reason and continuing the batch.
  - `ui/import_wizard.py::_continue_after_decrypt` — its own `try` catches
    `(PdfError, ValueError, FinbreakError)` and routes to
    `_show_pdf_read_error(exc)`. **Not `_on_import`**, which wraps `commit_import`
    and is downstream of the parse.

## 5. Invariants

- **INV-1** — A Standard Bank row `parse_transaction` rejects while `signed != 0`
  raises `ValueError` on **every** family, whether or not a completeness gate could
  have fired; the parse yields no drafts at all.
  *Test:* `pytest tests/features/standard_bank_pdf/ -k FIBR0255_money_moving` — the
  §2 four-line Family A page and the §7 Family E page, the two families where no
  gate exists to catch the shortfall, each asserted to raise.
  *Breaks when:* the guard is keyed on the rejection *reason* rather than on the
  amount, so a bad date on a money-moving row degrades again and the drafts sum to
  +150 against a page that moves +50.

- **INV-2** — A row rejected with `signed == 0` still degrades to a `RowError`,
  and its siblings still import (FIBR-0216, unchanged).
  *Test:* the pre-existing
  `test_FIBR0216_zero_amount_row_degrades_instead_of_aborting_the_statement`,
  which must stay green untouched.
  *Breaks when:* the guard is keyed on "was rejected" rather than "moved money",
  turning every printed `0.00` service-fee line back into a whole-statement
  refusal.

- **INV-3** — The refusal carries its own sentence, distinct from all four
  `"this statement didn't add up"` messages, and ends in the file's standard
  *try your bank's CSV or OFX export* tail.
  *Test:* the INV-1 test asserts `"moved money"` in the message and
  `"didn't add up"` **not** in it.
  *Breaks when:* the guard re-raises `parse_transaction`'s own text, which reads
  as an app bug (`occurred_on must be a valid ISO-8601 date`), or reuses
  `_MISPARSE`, which claims a grammar failure that did not happen.

- **INV-4** — The rule is stated once, in `_draft`. No family parser calls
  `parse_transaction` directly.
  *Test:* `grep -c 'parse_transaction(' src/finbreak/importers/standard_bank.py`
  → `1` — the call inside `_draft`. The `from finbreak.services.transactions
  import parse_transaction` line carries no parenthesis and is not counted.
  *Breaks when:* a sixth family is added with its own row loop that reaches
  `parse_transaction` around `_draft`, reintroducing the hole for that family
  alone.

- **INV-5** — No committed fixture changes behaviour: the corpus's only `RowError`
  is `family_a_zero_fee.pdf`'s zero-amount row, which INV-2 preserves.
  *Test:* the §7 fixture sweep, run before and after the fix → identical output both
  times: 12 fixtures parse, 10 raise, `non_sb.pdf` returns `None`, and
  `family_a_zero_fee.pdf` is the only one with `errors=1`.
  *Breaks when:* a future fixture is authored with an unreadable money-moving row
  and is expected to import.

## 6. Failure modes

- **A statement whose only defect is one unreadable money row now imports
  nothing.** That is the intended trade, and it is the trade `INV-11` already
  makes everywhere a closing figure exists — this change only stops the outcome
  depending on whether the bank happened to print one. The user keeps the escape
  route every other refusal offers: the bank's CSV or OFX export, which has no
  balance chain to be short against.
- **The user cannot tell which row was refused.** By §3 decision 2 the message
  names none. Mitigation is the preview, which the user reaches before importing:
  FIBR-0252 already renders unreadable rows there — but only on a statement that
  survives its gates, which by construction this one does not. So on this path the
  preview shows nothing and the message is all there is. Accepted rather than
  fixed: naming a row number in a refusal is a second reporting mechanism for a
  case the corpus has never produced, and §9 tracks it if it ever bites.
- **A batch import marks the file `failed` and continues.** `_fail` sets
  `outcome = "failed"` and `reason = str(exc)`, so the refusal appears in the
  batch report as the message above, and the other files in the batch are
  unaffected (`batch_import.py` INV-1).
- **`signed` is not the money moved.** The guard is only as good as that
  identity. It holds because `_verify_row` has already asserted `|delta| ==` the
  printed amount for A/B/D/E, and Family C derives `signed` from the printed
  amount directly. A future family that passes something else — a fee column, an
  unsigned magnitude — would silently weaken the guard rather than break it
  loudly; INV-4's single call site is what keeps that reviewable.

## 7. Tests

All in `tests/features/standard_bank_pdf/test_standard_bank.py`, beside the
FIBR-0216 test whose premise this repairs. No new PDF fixture: the defect lives in
the family parsers, which take a `list[str]`, and the suite already tests them
directly (`test_INV3a_family_a_keeps_embedded_mm_dd_in_description`,
`test_FIBR0216_zero_amount_row_degrades_instead_of_aborting_the_statement`).
Authoring a `reportlab` PDF for it would test `pdfplumber`, not this rule.

The Family E page, so it need not be invented — `_iso` does not validate the day, so
`32 Feb 26` reaches `parse_transaction` as an ISO-date rejection exactly as Family
A's `05 32` does (measured: `_iso(2026, 2, 32)` → `'2026-02-32'`):

```
STATEMENT OPENING BALANCE 1000.00
02 Feb 26 GROCERIES -100.00 900.00
32 Feb 26 MYSTERY -100.00 800.00
04 Feb 26 SALARY 250.00 1050.00
```

| Test | Locks |
|---|---|
| `test_FIBR0255_money_moving_unreadable_row_refuses_the_statement` | INV-1, INV-3 — the §2 Family A page raises; message asserted both ways |
| `test_FIBR0255_money_moving_row_refuses_family_e_too` | INV-1 on the second gate-less family (E, no printed totals) |
| `test_FIBR0216_zero_fee_row_with_a_bad_date_still_degrades` | §4.1's amount-not-reason rule — the case a reason-keyed guard would refuse |
| `test_FIBR0216_zero_amount_row_degrades_instead_of_aborting_the_statement` | INV-2 — pre-existing, must stay green **unmodified** |
| `test_FIBR0255_the_rule_is_stated_once_in_draft` | INV-4 — source-level count of `parse_transaction(` call sites |
| the fixture sweep below | INV-5 — hand-run, before and after; the two runs must agree |

INV-5's sweep, so it need not be invented. Run it once before the fix and once
after; every line must be identical:

```bash
PYTHONPATH=src python -c '
import glob
from finbreak.importers.standard_bank import StandardBankImporter
imp = StandardBankImporter()
for p in sorted(glob.glob("tests/features/standard_bank_pdf/fixtures/*.pdf")):
    try:
        r = imp.parse(open(p, "rb").read(), 2)
    except ValueError as e:
        print(f"{p.split(chr(47))[-1]:42s} RAISES {str(e)[:40]}"); continue
    print(f"{p.split(chr(47))[-1]:42s} " + ("None" if r is None
          else f"drafts={len(r.drafts)} errors={len(r.errors)}"))'
```

Each new **behavioural** test must be seen to **fail against pre-fix code** before
the fix lands — the §2 repro is that failure for INV-1, already observed. The INV-4
source-count test is exempt and cannot comply: it locks a property that already
holds (verified: the grep returns `1` on the unmodified tree), so it is green before
and after, guarding against a future regression rather than proving this one.

## 8. Alternatives considered (and rejected)

- **Give the closing-less layouts a completeness gate: compare `opening + Σ drafts`
  against the parser's own final running balance.** Rejected on three counts. It
  needs a new channel out of every family parser to carry that balance, where the
  guard needs none. It cannot say *which* row was lost, so its message would be
  the arithmetic one §4.2 argues is a misdiagnosis. And it is strictly weaker: it
  catches a dropped money row on the two gate-less families and nothing else,
  while the guard catches it on all five, including the Family C case where the
  existing gate catches it under the wrong name.
- **Make `_verify_checksum` count error rows, so any dropped row fails the
  import.** This is FIBR-0252 §8's rejected option and it stays rejected, for its
  own reason: a zero-amount row is *correct* to drop, and FIBR-0216 exists to stop
  such a row aborting an otherwise perfect statement. INV-2 keeps that promise;
  this spec narrows the carve-out to the premise FIBR-0216 actually argued, rather
  than removing it.
- **Substitute a placeholder for the unreadable field and import the row anyway** —
  a `1970-01-01` date, a `(unreadable)` description. Rejected: it converts a
  refusal the user can act on into a wrong row they will never notice, which is
  the same class of defect as the one being fixed.
- **Include the row number and `parse_transaction`'s reason in the message.**
  Rejected under §3 decision 2; §6 records what is lost and §9 tracks it.

## 9. Out of scope

- Naming the offending row in the refusal message — filed only if a real statement
  ever produces this refusal; §6 states the trade taken meanwhile. No id yet.
- The `_parse_family_c` dated-segment-with-no-amount `continue`, a second silent
  drop on that family. It is covered by C's mandatory closing gate (C always
  prints one, and `_verify_checksum` raises for a `None` closing on B/D/C), so it
  is not the FIBR-0255 class — but the coverage is by luck of the layout, not by
  construction. Not filed: no reachable defect, and inventing one would be
  speculative.
- The CSV and OFX importers (§4.3) — no running-balance chain, no shortfall to
  detect.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `Partial:` `test_FIBR0255_money_moving_unreadable_row_refuses_the_statement`, `test_FIBR0255_money_moving_row_refuses_family_e_too` — Families **A and E only**, the two with no completeness gate. B/C/D hold by construction (one guard, one `_draft`) and are covered only transitively, by INV-4 |
| INV-2 | `test_FIBR0216_zero_amount_row_degrades_instead_of_aborting_the_statement`, `test_FIBR0216_zero_fee_row_with_a_bad_date_still_degrades` |
| INV-3 | `test_FIBR0255_money_moving_unreadable_row_refuses_the_statement` (asserts both the new phrase and the absence of the old) |
| INV-4 | `test_FIBR0255_the_rule_is_stated_once_in_draft` |
| INV-5 | **nothing automated** — the fixture sweep is a hand-run command recorded in §12; the suite's per-fixture tests catch a *changed* fixture outcome, but nothing asserts the corpus-wide shape |
| §3 decision 2 (no row number in the message) | **nothing** — a preference, not a contract; INV-3 pins only the sentence that ships |
| §6 "`signed` is the money moved" | **nothing** — a future family parser passing something else compiles and passes every test above; INV-4's single call site is a review aid, not a check |

## 11. Cross-doc impact

- `tests/features/standard_bank_pdf/spec.md` — its **Two gates, not one** paragraph
  names "a garbled date" as a `RowError` case, which this change makes false.
  Rewritten in the same commit.
- `CHANGELOG.md` — one `Fixed` line under `[Unreleased]`; user-visible.
- `ROADMAP.md` — FIBR-0255 flips to ✅ with a resolution note.
- `docs/specs/FIBR-0050.md` — **done, in this spec's own commit; no further edit is
  due.** Three of its clauses said the SB reader raises on *any* `parse_transaction`
  rejection — INV-11's, INV-1's `errors`-on-success clause, and the
  `parse_transaction` bullet's. All three were already false when FIBR-0216 shipped
  the zero-amount carve-out, and INV-11 additionally enumerates the refusal wordings
  without this one. Each now reads "of a row that moved money" and names FIBR-0255.
  Nothing else in FIBR-0050 moved; it names no `_draft` carve-out anywhere
  (`grep -c '_draft' docs/specs/FIBR-0050.md` → `0`).
- `docs/specs/FIBR-0252-standard-bank-row-errors.md` — §9 defers "the parser gap
  §6 uncovered" to this id, which is the pointer being honoured; §8's rejected
  alternative is addressed in §8 above. No edit: a converged spec's record of what
  it deferred stays as written.
- `src/finbreak/importers/standard_bank.py` — `_draft`'s docstring, per §4.1. Not a
  doc, listed here because it is the sentence a later reader would act on.
- `CLAUDE.md` — no change; this adds no convention a session must be told about.

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-12 | 3, cold, shared byte-identical packet (`review-contract`, `--genre spec`) | 1 | 3 | 0 | 1 | 5 verified, 0 unverified. All fixed. **The Q1 rewrote §4.1's central argument.** The draft claimed a zero-amount row could only ever be rejected for `"amount must be non-zero"`, making the amount and the rejection reason interchangeable discriminators. `parse_transaction` checks description and date *first*, so a printed `0.00` line with a garbled date returns `RowError(1, 'occurred_on must be a valid ISO-8601 date')` — reproduced. An implementer keying the guard on the reason would have refused whole statements over zero-fee rows, the exact FIBR-0216 regression INV-2 exists to block; §4.1 now states the rule as amount-not-reason and a fifth test locks it. Q2s: INV-1 scoped the refusal to gate-less families while §1 and §8 said all five (a family-conditional guard would have passed the invariant); §11 claimed FIBR-0050 needed no edit when its INV-11 enumerates the refusal wordings and asserts "any `parse_transaction` rejection raises" — false since FIBR-0216 — so three of its clauses were corrected in place; and `_draft`'s own docstring says "never aborting the statement", now listed as part of the change. Q4: the red-first rule was unsatisfiable for INV-4's source-count test, which is green before and after. |
| 2 | 2026-08-12 | 2, cold, packet rebuilt from disk and widened to all five family parsers | 2 | 0 | 1 | 1 | 4 verified, 0 unverified. All fixed. **The Q1 that mattered: §4.3 cited the wrong wizard method.** It named `_on_import` as the caller that already handles a raising `parse`; `_on_import` wraps `commit_import` and is downstream. The real call site is `_continue_after_decrypt`, which catches `(PdfError, ValueError, FinbreakError)` and routes to `_show_pdf_read_error` — so the claim was true of the code and false of the citation, and an implementer checking the cited method would never have looked at the raising one. Both call sites are now named and grepped. Second Q1 was this skill's own loop-1 collateral: §11's FIBR-0050 bullet still read as a to-do after the edit had landed in the same commit. Q3: INV-5's *Test:* pointed at §7, §7 pointed at §12, and the sweep command existed nowhere — now stated in §7 and executed (its pre-fix output is the baseline the post-fix run must match). Q4: §10 claimed INV-1 fully covered while only A and E are tested; now `Partial:`. |
