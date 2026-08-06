# batch statement import spec

**Theme:** selecting several statement files imports them in one unattended
run — every question asked up front, one combined review screen, one
transaction per file, and a per-file report that survives until dismissed.

The design contract is
[`docs/specs/FIBR-0085-batch-statement-import.md`](../../../docs/specs/FIBR-0085-batch-statement-import.md).
Every invariant below is that document's, restated as an assertion; the section
reference after each one is where its argument lives. This file is the test's
contract, not a second design.

## Invariants

- **INV-1**: A file that fails does not stop the batch — every later file is
  still attempted, and its own outcome records the reason. Source: FIBR-0085
  § 5 INV-1 / § 4.3 RUN.
- **INV-2**: Each file commits in its own transaction. After a mid-batch
  failure the earlier files' transactions **and** their `statement_periods`
  rows are present, and the failed file has written neither. Source: FIBR-0085
  § 5 INV-2.
- **INV-3**: No file is committed while any file in the batch is
  `needs_password`, `needs_mapping` or `needs_account` — the first two are
  exhausted by ASK, the third disables `Import all` in REVIEW. Source:
  FIBR-0085 § 5 INV-3 / § 4.6.
- **INV-4**: For each `ready` file, the New **and** Duplicate counts shown on
  the review step equal its `ImportResult.inserted_count` and `duplicate_count`
  after the run — given no change to the vault between the two and no earlier
  record failing during RUN. Source: FIBR-0085 § 5 INV-4 / § 4.5.
- **INV-5**: `match_account` runs before the **first** preview is built, and
  the account shown on a review row is the account that row's
  `ImportPreview.account_id` targets — including after the user changes it.
  Source: FIBR-0085 § 5 INV-5 / § 4.6.
- **INV-6**: No batch code path blocks the event loop, by a nested dialog loop
  **or** by pumping events inside one. Enforced by the dialog-lifecycle guard,
  not here — see *Out of scope*. Source: FIBR-0085 § 5 INV-6.
- **INV-7**: An idle auto-lock during a batch stops it. Files already committed
  stay committed; no further file is attempted; nothing is half-written.
  Source: FIBR-0085 § 5 INV-7 / § 4.7.
- **INV-8**: A locked PDF raises at most three **user prompts**, after which the
  file becomes `skipped` and the batch continues. Cancelling a prompt skips
  that file immediately. Source: FIBR-0085 § 5 INV-8.
- **INV-9**: Each distinct remembered password is tried at most once per file,
  and only before the user is prompted. Source: FIBR-0085 § 5 INV-9 / § 4.4.
- **INV-10**: Each record's outcome is re-derived **in both directions** on
  every REVIEW pass: `already_imported` when the span exists **and** the
  cumulative new count is zero, `ready` otherwise. A record never stays
  `already_imported` once either half stops holding. Source: FIBR-0085 § 5
  INV-10 / § 4.3 REVIEW.
- **INV-11**: The batch refuses more than 200 **selected files** before reading
  anything, and stops the scan once 200,000 drafts are held. Neither cap
  raises: the refused or unscanned records are `not_attempted` and say which
  cap stopped them. Source: FIBR-0085 § 5 INV-11.
- **INV-12**: No real statement data enters the repository with this work —
  every fixture under this directory is synthetic. Enforced by the corpus-number
  guard, not here — see *Out of scope*. Source: FIBR-0085 § 5 INV-12.
- **INV-13**: A record whose parse yields **either** period endpoint `None`
  never reaches `commit_import`: it becomes `failed` at SCAN with a reason
  naming the absent dates. Source: FIBR-0085 § 5 INV-13 / § 3 decision 4.
- **INV-14**: The post-run report survives until the user dismisses it —
  `ImportWizardWidget.done` is emitted only by the report's Close, never at the
  end of RUN, never by the batch step's Cancel, and never by the `_STEP_MAP`
  Cancel while the batch is driving that page. Source: FIBR-0085 § 5 INV-14.
- **INV-15**: An OFX file carrying N statements produces N records, each with
  its own account, preview and review row. No statement is discarded. Source:
  FIBR-0085 § 5 INV-15 / § 4.2.

## Fixtures

Synthetic strings only — CSV text built in the test body, OFX assembled from
the same tag builders the `ofx_import` suite uses, and a **fake** decrypt
function in place of any locked PDF. No `.pdf` file is committed under this
directory at all, so INV-12's weakest link (the corpus guard skips binary
`.pdf` bytes) is not exercised because there is nothing for it to miss.

## Out of scope

- **INV-6 and INV-12 are asserted elsewhere**, and deliberately so: both are
  whole-tree source scans, and a per-feature copy would be a second definition
  of a guard that already binds every file. INV-6 lives in
  `tests/features/dialog_lifecycle/test_dialog_lifecycle.py` (which this work
  extends by a fifth file and the `processEvents` token); INV-12 lives in
  `tests/features/account_detect/test_no_real_data.py` (which this work extends
  by this fixture directory).
- **The report wording**, the File-cell escalation rule, the review table
  becoming read-only after RUN, the single-file routing, and the two cap
  *messages* — all listed as unguarded in FIBR-0085 § 11's error budget. Nothing
  here asserts them; they are caught by reading.
- **Whether 200 / 200,000 are the right numbers.** INV-11 proves the caps bind,
  not that either is well chosen.
