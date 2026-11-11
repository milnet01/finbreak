<!-- ants-spec-format: 1 -->
# FIBR-0467 — Store a Home Loan repayment as money in, and correct existing vaults once

**Status:** spec draft (2026-11-11).
**Kind:** fix.
**Source:** ROADMAP FIBR-0467 (user-answer-2026-11-11, FIBR-0121's open question).

**Supersedes:** FIBR-0121's display-only approach (approved 2026-07-13, superseded
by the user 2026-11-11). **Pairs with:** FIBR-0050 (INV-7 and INV-11 change, § 11)
and FIBR-0357 (the parked gate tightening, which this leaves parked, § 3).

*Layman: a Standard Bank home-loan statement imports a repayment as a minus, so
the app never offers to link it to the matching payment from your current
account, and counts the payment as spending. After this a repayment imports as
a plus, a fee as a minus, and loan rows already in your vault are corrected once
when you upgrade.*

## 1. Goal

Every Standard Bank Home Loan row is stored in FIBR-0007's sign rule: money
into the loan account positive, money out negative. A repayment is positive, a
fee or interest charge negative. Rows already stored the old way are negated
once, by the schema migration that ships with the fix. After that, a repayment's
two legs are opposite amounts, so transfer detection can pair them.

## 2. Problem

`importers/standard_bank.py::_parse_family_b` signs each row by the change in the
printed running balance (`delta = balance - prev_balance`). That balance is the
amount **owed**, printed unsigned (FIBR-0050 INV-11, settled on real statements
by FIBR-0335). So a repayment lowers it and imports negative, and a fee raises it
and imports positive. FIBR-0050 INV-7 records this as its "documented loan
consequence".

Consequences, each read in code:

1. **Transfers.** `repositories/transfers.py::CANDIDATE_PAIRS_SQL` pairs only
   `c.amount_minor = -d.amount_minor` with `d < 0` and `c > 0`. The current-account
   leg of a repayment is negative and so is the loan leg, so no suggestion is
   ever made.
2. **Totals.** `services/reporting.py` classes a row as income or spending by its
   sign alone and reads no account type. So the repayment counts as spending
   twice, once per leg, and a loan fee counts as income.
3. **Display.** A repayment shows red and a fee green on the loan account. That
   is FIBR-0121's complaint.

No other importer path has this defect. The other Standard Bank families print a
signed balance (the Revolving-Credit loan prints its closing as `302.431,97-`,
FIBR-0050 § Verified basis). CSV keeps the file's or profile's sign
(FIBR-0007 INV-3). OFX keeps the file's `TRNAMT` sign.

## 3. Scope decisions (agreed with the user)

- **Fix it in the importer, not in detection or display.** User, 2026-11-11, on
  FIBR-0467. Pairing same-sign legs for loan accounts and flipping only the
  display (FIBR-0121's plan) were both put to the user and not chosen (§ 8).
- **Correct existing rows once, on upgrade.** User, 2026-11-11, on FIBR-0467.
- **Release number 1.1.0.** User, 2026-11-11, in session. `versioning.md` § 2
  lists "opens with data … altered" as a vault break. The user ruled that a
  deliberate, announced correction of wrongly stored data is the "automatic
  forward migration" § 3.2 makes MINOR, not that break. § 11 records the
  one-line clarification `versioning.md` gets.
- **Keep Family B's magnitude completeness check.** User, 2026-09-26, on
  FIBR-0357: a stricter signed check would refuse an overpaid-loan statement,
  whose printing is unobserved. This item changes which way B's rows are signed,
  not how strict B's check is, so that decision still governs. FIBR-0357 stays
  parked.
- **Which existing rows count as "Family B rows" is the author's call** (§ 4.3),
  because the vault does not record which parser produced a row.

## 4. Design

### 4.1 The parser

`_parse_family_b` negates the delta: a row's amount is
`-(balance[i] - balance[i-1])`. The per-row gate (`_verify_row`, magnitude only,
`check_sign=False` for B) is unchanged, because it compares `|delta|`.

### 4.2 The completeness check

`_verify_checksum` today computes `reconciled = opening_m + total` for every
family except C. With B's rows now negated, `opening + Σ` no longer tracks the
owed balance. B moves to the owed frame, as C already does:

```python
if family in (Family.B, Family.C):
    reconciled = opening_m - total   # B: owed balance; C: printed +purchase convention
else:
    reconciled = opening_m + total
...
if family is Family.B:
    mismatch = abs(reconciled) != abs(closing_m)   # unchanged (§ 3)
```

On a real statement `opening - Σ` equals the closing owed balance, which the
closing row prints negated (FIBR-0335). So the magnitude comparison passes,
exactly as `opening + Σ` passed before. The quiet-month case (`Σ = 0`) is
unchanged.

The stored closing (`ParseResult.closing_balance_minor`, the forecast anchor) is
the printed figure and does not change.

### 4.3 The upgrade: schema v16

`migrations.py` gains `_migrate_to_v16`, and `LATEST_SCHEMA_VERSION` becomes 16.
It is data-only and runs in one `owned_transaction`, with
`UPDATE schema_version SET version = 16` as its last statement, like every
sibling step.

**Which rows.** The vault records no parser per row, so the step selects by what
only a Family B import leaves behind:

```sql
-- the rows to negate
SELECT t.id FROM transactions t
JOIN accounts a          ON a.id = t.account_id
JOIN statement_periods p ON p.id = t.statement_period_id
WHERE a.type = 'home_loan'
  AND lower(p.source_filename) LIKE '%.pdf'
  AND p.closing_balance_minor IS NOT NULL
```

Why each condition:

- `home_loan`: FIBR-0086's create-account dialog presets that type for a
  Family B statement (`ui/account_create.py::_FAMILY_TYPES`). The Revolving-Credit
  loan (Family A, already correct) gets no preset, so its account is not
  selected unless the user typed it a home loan (§ 6).
- `.pdf`: excludes CSV and OFX periods, whose rows took the file's sign.
  `commit_import` stores the basename (`services/import_.py::ImportService.commit_import`).
- `closing_balance_minor IS NOT NULL`: excludes another bank's PDF read by the
  generic table path, which records no closing. Family B always records one;
  `_verify_checksum` refuses a B statement that has none.

**What the step does:**

1. `UPDATE transactions SET amount_minor = -amount_minor` for the selected ids.
2. `DELETE FROM transfer_pairs WHERE status = 'confirmed'` for every pair that
   touches a negated row and whose two legs are no longer exact opposites. Such a
   pair was confirmed between opposite amounts. A negated leg now makes the pair
   same-signed, and `services/transfer_detection.py` picks the "From" leg by sign,
   so it would display wrongly. Deleting it returns both rows to the totals and
   to the suggestion list. Rejected pairs stay: they only suppress one suggestion
   (`CANDIDATE_PAIRS_SQL`'s last `NOT EXISTS`), and a same-signed pair can no
   longer be suggested anyway.

Migrations run on unlock (`Vault`'s unlock path calls `run_migrations`). A
restored pre-v16 backup is therefore corrected the first time it is unlocked.

## 5. Invariants

No clause below can run yet; each names a test that the implementation writes.
Each fixture is chosen so that only the rule under test rejects it.

- **INV-1** — A Family B row's stored amount is the negated running-balance
  delta. The `family_b_homeloan.pdf` fixture (fee 50.00, payment 300.00) imports
  as `[-5000, 30000]`.
  *Test:* `tests/features/standard_bank_pdf/test_standard_bank.py::test_INV4_family_b_homeloan_unsigned_balance_signed_closing`,
  its expected list changed from `[5000, -30000]` to `[-5000, 30000]`.
  *Breaks when:* `_parse_family_b` keeps `delta` as the amount. The per-row gate
  passes either sign, so only this rule decides the list.

- **INV-2** — Family B's completeness check runs in the owed frame and stays a
  magnitude comparison: `|opening − Σ| == |closing|`. A complete B statement
  reconciles. One missing its last row is refused with "didn't add up".
  *Test:* a test in `test_standard_bank.py` calling `_verify_checksum(Family.B, …)`
  with the fixture's opening 1,000.00, drafts `[-5000, 30000]` and closing
  −750.00 (the real printing, FIBR-0335), which passes. The same call with
  drafts `[-5000]` raises.
  *Breaks when:* B keeps `opening + Σ`, which gives 1,250.00 against 750.00 and
  refuses every complete statement with a non-zero sum. Or B is moved to a signed
  comparison, which refuses the complete set's 750.00 against −750.00.

- **INV-3** — No other family and no other importer changes sign. Families A, C,
  D and E, CSV and OFX produce the amounts they do today.
  *Test:* the existing amount assertions in `tests/features/standard_bank_pdf/`,
  `tests/features/import_/` and `tests/features/ofx_import/` pass unchanged.
  *Breaks when:* the negation is applied outside `_parse_family_b`, for example
  in `_draft`, which every family shares.

- **INV-4** — The v16 step negates exactly the rows § 4.3's query selects, and
  leaves every other row's amount unchanged.
  *Test:* a new `tests/features/loan_sign/test_migration_v16.py`. Its v15 vault
  holds one row for each case: a home-loan row on a `.PDF` period with a closing
  (negated), and one on a `.pdf` period with no closing, one on a `.csv` period
  with a closing, a home-loan manual row with no period, and a current-account
  row on a `.pdf` period with a closing (all four unchanged).
  *Breaks when:* any one condition of the selector is dropped, so that a row
  which only that condition excludes is negated. Or the suffix match is
  case-sensitive, so the `.PDF` row is missed.

- **INV-5** — The v16 step is all-or-nothing and runs once. If it fails part-way,
  the vault is left at v15 with every amount unchanged. A v16 vault reopened
  runs no step.
  *Test:* in `test_migration_v16.py`, a failure injected after the `UPDATE`
  leaves version 15 and the original amounts. `run_migrations` on a v16 vault
  leaves the amounts as they are.
  *Breaks when:* the `UPDATE` runs outside `owned_transaction`, or the version
  bump comes before the data change.

- **INV-6** — After the v16 step, every confirmed transfer pair's two amounts are
  exact opposites.
  *Test:* in `test_migration_v16.py`, a confirmed pair between a selected
  home-loan row (+500 before) and a current-account row (−500) is deleted. A
  confirmed pair touching no selected row survives, and so does a rejected pair
  touching a selected row.
  *Breaks when:* the step negates rows and does not delete pairs. The same-signed
  pair survives and displays with the wrong "From" account.

- **INV-7** — Re-importing a Family B statement after the upgrade adds nothing.
  *Test:* in `test_migration_v16.py`, build a v15 vault holding the rows the old
  parser stored for `family_b_homeloan.pdf` (`[5000, -30000]`) on a `home_loan`
  account, under a period with that filename and a closing. Migrate, then preview
  an import of the same fixture into that account. Every row is a duplicate.
  *Breaks when:* the migration's selector misses these rows, or the parser and the
  migration disagree on the sign. Either way the preview shows two new rows,
  because the duplicate key includes the signed amount (`repositories/transactions.py`).

- **INV-8** — A home-loan repayment and its current-account leg become a transfer
  suggestion.
  *Test:* a test in `tests/features/transfers/`: import `family_b_homeloan.pdf`
  into a `home_loan` account, and add a −300.00 current-account row on the
  payment's date. `candidate_pairs` returns that pair.
  *Breaks when:* INV-1 is not implemented. That is the defect FIBR-0467 names.

## 6. Failure modes

- **A Family B statement imported into an account not typed `home_loan`** (the
  user overrode the preset, or used an existing current account). The upgrade
  misses its rows, and a later re-import of that statement shows its rows as new,
  with the opposite sign. Remedy: delete that statement in the Statements view
  and re-import it. The CHANGELOG entry says so.
- **A Family A Revolving-Credit statement in an account the user typed
  `home_loan`.** Its rows were already correct, and the upgrade negates them.
  Same remedy. This is the selector's one wrong-positive case, and it needs the
  user to have chosen an unexpected type.
- **Home-loan rows imported before schema v11** (2026-07-24, FIBR-0171), whose
  period has no stored closing. The upgrade misses them. Same remedy.
- **Recurring decisions.** `services/recurring.py::detect_recurring` keys a
  stream by `(direction, merchant)`, with direction taken from the sign. A
  repayment stream on the loan account moves from "out" to "in". So a decision
  the user made about it no longer matches, and the stream reappears once under
  Suggested. Once the user confirms the repayment pair as a transfer, its rows
  leave recurring detection (`excluded_ids`). Accepted, not migrated: a merchant
  key spans accounts, so moving the decision could move it for unrelated rows.
- **Totals shift.** The dashboard stops counting a repayment as spending on the
  loan leg and counts it as income until the pair is confirmed. Loan fees and
  interest count as spending. Both are the fix, and the CHANGELOG entry
  describes them.
- **An overpaid loan** (balance crossing zero) is still unobserved. The magnitude
  check behaves as it does today (§ 3).

## 7. Tests

| Test | Locks |
|---|---|
| `test_standard_bank.py::test_INV4_family_b_homeloan_unsigned_balance_signed_closing` (changed expectation) | INV-1 |
| new B case(s) beside the `_verify_checksum` truncation test in `test_standard_bank.py` | INV-2 |
| existing amount tests in `standard_bank_pdf/`, `import_/`, `ofx_import/` | INV-3 |
| new `tests/features/loan_sign/test_migration_v16.py` | INV-4, INV-5, INV-6, INV-7 |
| new case in `tests/features/transfers/` | INV-8 |

The existing test in `test_standard_bank.py` that passes a truncated set through
`_verify_checksum(Family.B, …)` uses hand-built drafts in the old sign. It is
rewritten with the new sign and the new arithmetic, and still documents the
magnitude exemption.

Each new or changed test is seen failing against the pre-fix code before the fix
lands. INV-3's tests are expected to stay green throughout.

`tests/features/loan_sign/` reads no tracked doc, so the `prose_checks` guard
files it under the non-prose ledger.

## 8. Alternatives considered (and rejected)

- **Display-only flip for loan accounts** (FIBR-0121, approved 2026-07-13). It
  leaves the stored sign wrong, so transfers still never pair and totals still
  double-count. Superseded by the user, 2026-11-11.
- **Pair same-sign legs in transfer detection when one account is a loan.** It
  fixes pairing only. Totals still count a fee as income, and every consumer of
  the sign would need the same exception. The user chose the importer, 2026-11-11.
- **A signed completeness check for B** (FIBR-0357). Parked by the user,
  2026-09-26 (§ 3).
- **Select upgrade rows by account type alone.** That would negate CSV and OFX
  rows on home-loan accounts, which took the file's sign and may be correct.
- **Select by `.pdf` alone, without the closing condition.** That would also
  negate pre-v11 rows (wanted) and another bank's generic-PDF rows (unwanted).
  The vault cannot tell those apart, and negating a correct row is worse than
  leaving a wrong one with a stated remedy.
- **Ask the user, on first unlock, which statements to correct.** That would
  handle every case in § 6. But it adds a one-time UI to a migration, and the
  user asked for a once-on-upgrade correction.

## 9. Out of scope

- A signed completeness check for Family B — parked as FIBR-0357.
- What is left of FIBR-0121 once this ships — re-checked then, per its body.
- How loan flows count in dashboard totals, beyond the sign fix (for example,
  interest as an expense category) — tracked by FIBR-0121's "possible later
  follow-up"; not yet queued.
- The forecast's `CASH_TYPES` comment says a debt product prints its closing in
  the owed convention; it is not touched here — deferred; not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_standard_bank.py::test_INV4_family_b_homeloan_unsigned_balance_signed_closing` |
| INV-2 | the new B `_verify_checksum` cases in `test_standard_bank.py` |
| INV-3 | existing amount assertions in `standard_bank_pdf/`, `import_/`, `ofx_import/` |
| INV-4 | `loan_sign/test_migration_v16.py` |
| INV-5 | `loan_sign/test_migration_v16.py` |
| INV-6 | `loan_sign/test_migration_v16.py` |
| INV-7 | `loan_sign/test_migration_v16.py` |
| INV-8 | the new case in `tests/features/transfers/` |
| § 6, rows the selector misses or wrongly takes | **nothing** — the vault does not record a row's parser; the CHANGELOG remedy is the mitigation |
| § 6, recurring decisions orphaned | **nothing** — accepted; the stream resurfaces under Suggested |

## 11. Cross-doc impact

In the implementation commit:

- **FIBR-0050** (`docs/specs/FIBR-0050.md`): INV-7's "documented loan consequence"
  is replaced. Family B's sign is the **negated** delta, citing FIBR-0467.
  INV-11's Family B sentence states the gate as `|opening − Σ| == |closing|`. The
  Out of scope "loan-sign toggle" entry is marked resolved by FIBR-0467. This
  follows `module-map.md`'s rule: INV-11 changes in the same commit as the
  behaviour.
- **`tests/features/standard_bank_pdf/spec.md`**: any Family B sign wording.
- **`docs/standards/versioning.md` § 2**: one sentence, saying that an announced
  migration correcting wrongly stored data is the automatic forward migration
  § 3.2 makes MINOR, not a break (user, 2026-11-11).
- **CHANGELOG** (1.1.0): the sign change, the totals shift, and the § 6 remedy.
- **ROADMAP**: FIBR-0121 re-checked; FIBR-0357's body notes that B's arithmetic
  moved to the owed frame.

## 12. Cold-eyes loop log

Rows live in `../reviews/FIBR-0467-home-loan-sign-loop-log.md`.

## 13. Migration / compatibility

§ 4.3 is the migration. A vault at v16 is refused by a pre-1.1.0 build, as every
schema bump is (`run_migrations`' newer-than-this-build check). A pre-v16 backup
restored into 1.1.0 is corrected on its first unlock.
