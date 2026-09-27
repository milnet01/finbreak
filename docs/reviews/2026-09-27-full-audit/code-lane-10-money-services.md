## Lane 10: transaction, account and statement services, transfer detection, reconciliation, category tree

**Line counts as read from disk:** `services/transactions.py` 219, `services/accounts.py` 153, `services/statements.py` 166, `services/transfer_detection.py` 215, `services/reconciliation.py` 125, `services/categories.py` 160.

**Already in my context on arrival:** global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, finbreak `CLAUDE.md`, the finbreak memory index, and a git snapshot (HEAD 52e5162, FIBR-0331 commits). I read the shared-context packet once.

**Search notes:**
- `workspace_search` hit its rate limit once, so I fell back to `Grep`, confined to `src/` or to single spec files.
- The only grep that touched `tests/` was a caller **count** for dimension 2b (the authorised case). I opened no test file.
- I found no disagreement between the brief and the lane rules.
- This was a depth pass.

## Critical (0)

## High (0)

## Medium (1)

- **[dim 13]** Service error messages are hard-coded English that the UI shows word-for-word.
  - Examples: `accounts.py:152` — `raise ValueError(f"an account named {name!r} already exists")`; `transactions.py:110` — `raise ValueError("amount has more fractional digits than the currency allows")`.
  - Every `raise` in this lane builds an English string. The UI prints it unchanged with `self._error.setText(str(exc))` at `ui/manual_entry.py:114`, `ui/accounts.py:337/366/451`, `ui/categories.py:161/183/234`, `ui/import_wizard.py` (several sites) and `ui/first_run.py:196`.
  - That breaks design.md's rule that every user-facing string goes through `tr()` with no concatenation. The f-strings that splice in names (`accounts.py:143,152`, `categories.py:116,159`) also concatenate display text.
  - Sites in this lane:
    - `transactions.py:60,71,87,89,108,110,114,161,163`
    - `accounts.py:97,108,113,143,146,152`
    - `categories.py:60,80,84,113,116,133,153,159`
  - The code itself shows the fix: `ui/statements.py:225` catches `reassign_account`'s `ValueError` and shows a `tr()`-composed message instead of `str(exc)`, as FIBR-0059 requires.
  - I did not open design.md to look for a carve-out covering exception text.
  - Fix: raise typed errors or error codes and build the message with `tr()` in the widget.

## Low / Info

- **[dim 2] `transactions.py:106`** — `significant_exponent = cast(int, amount.normalize().as_tuple().exponent)`
  - `normalize()` rounds to the default context precision of 28 digits. The file's own comment says it "APPLIES CONTEXT".
  - So `"1.0000000000000000000000000001"` (29 significant digits) should normalise to `1` and be accepted as 100 minor units.
  - That silently drops a sub-cent fraction the docstring promises to reject ("rounding money would silently mutate it — INV-4b").
  - The cent value itself cannot change: that would need 27+ integer digits, which the 2^63 bound rejects anyway. The code, not the spec, is wrong here.
  - Unexecuted; confirm with `python -c "from decimal import Decimal; print(Decimal('1.0000000000000000000000000001').normalize())"`.
  - Fix: count fractional digits from `amount.as_tuple()` after stripping trailing zeros without context, or normalise under a local `Context(prec=len(digits))`.
- **[dim 7] `transfer_detection.py:141`** — `repo.add_decision(debit_id, credit_id, TransferStatus.CONFIRMED.value)`. The same applies to `:160` in `reject_many`.
  - The bulk paths skip every database-state check. The only database-level guard for INV-4 (a transaction in at most one confirmed pair) is `_record`'s `is_confirmed` call.
  - `.confirm(` / `.reject(` have zero `src/` callers (the grep hits are dialog `reject()` and `RecurringService.confirm`), so the shipped app never runs that guard.
  - The schema has only `UNIQUE(txn_a_id, txn_b_id)` (no `CREATE UNIQUE INDEX` anywhere in `src/`). So correctness rests on `self._candidates` in `ui/transfers.py` matching the database.
  - FIBR-0201 §4.3 argues this from "the live candidate list", and §6 covers only the gap between resolving ids and writing them. It never covers the list going stale between refreshes.
  - The stale case: a statement deleted, or a statement reassigned to another account, in another tab since the Transfers tab last refreshed.
    - A deleted transaction id should fail the foreign-key check, and `IntegrityError` is not a `ValueError`. It escapes `_on_confirm`, which catches only `VaultLockedError` (`ui/transfers.py:229`), after the earlier decisions have already committed.
    - A reassigned statement can let a pair whose two legs are now in the same account be confirmed.
  - I have not verified whether the Transfers tab refreshes when shown. Fix: have `add_decision` re-check candidacy (`is_confirmed`, `pair_decided`) and skip rather than raise, or refresh before resolving.
- **[dim 2b] INFO, dead symbols rather than zombie features:** `TransferDetectionService.confirm`/`reject`/`_record` and `StatementService.delete_statement`/`delete_preview` have no `src/` caller; the features run through the `_many` paths. A tool decides dead symbols, so this is noted, not filed.
- **INFO: reconciliation contract missing.** `reconciliation.py`'s own spec (FIBR-0177) is not in the lane contract. I reviewed it only against its docstring and the repository methods it calls (`sum_after`, `closing_balances_for_account`), which are consistent with each other.
- **INFO: spec coverage.** Of the contract specs I read only FIBR-0201 §4.3 and §6, plus grep hits in FIBR-0059. The other contract specs (ADR-0006, FIBR-0011/0052/0010/0138/0113/0051/0012) I did not open beyond heading outlines, so I cannot certify conformance against their invariant tables.
- **Nothing found** on dimension 3 (every SQL statement uses bound parameters and logs carry no content), 5, 8, 11, 15, 16 and 17. Dimensions 10 and 12 are N/A for this lane.

## Covered by spec and looks correct

- **Money handling:** integers in minor units throughout, `Decimal` only for display, no float anywhere in the lane. `reconcile_account` compares integers exactly.
- **Atomicity (dim 9):** `delete_statements`, `reassign_account` and `delete_category` each run inside `owned_transaction`, and every repository call inside them is commit-free.
  - Checked against `db.py`, `StatementPeriodRepository.delete`/`set_account`, `TransactionRepository.hand_off_covered`/`delete_for_statement`/`reassign_account`/`clear_category_for`/`set_category`, and `recategorize_auto_rows`.
  - `TransactionRepository._commit` is called only from `add` (line 116).
- **Batch delete:** the whole batch is the exclusion set, and an empty batch returns early, as FIBR-0201 §4.4 requires.
- **Transfer pairs:** they cascade when a transaction is deleted (`migrations.py:282-283`), so `candidates`/`confirmed_transfers` cannot hit a `KeyError` on a missing transaction.
- **Unicode digits and underscores:** `Decimal` accepting Unicode Nd digits and PEP 515 underscores is documented as deliberate (FIBR-0328). Not a finding.

## Open questions

1. After a statement is reassigned, a confirmed transfer can have both legs in one account. FIBR-0011's matching rule requires `c.account_id <> d.account_id`, but FIBR-0059 is silent on transfers. Should `reassign_account` unlink those pairs or refuse?
2. Does the Transfers tab refresh on tab-show or after changes in the Statements tab? That decides whether the `IntegrityError` above can actually happen.
3. Is there a design.md carve-out letting exception text skip `tr()`? If so, the Medium finding is a documentation defect, not a code one.

## 3 items to fix first

1. **The untranslated error messages (Medium, dim 13).** They reach users on every validation path and break the stated localisation rule; `ui/statements.py:225` already shows the pattern to copy.
2. **Bulk confirm/reject skipping the database checks (dim 7).** A stale list can crash the slot mid-batch with decisions half-committed, or confirm a same-account pair, and nothing in the database backs INV-4.
3. **Silent rounding in `parse_transaction` (dim 2).** The blast radius is tiny, but it breaks the "never round money" contract in a correctness-critical app, and the fix is local.