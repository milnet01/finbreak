**Subject files, line counts as read:** `services/batch_import.py` 726 · `ui/import_batch.py` 481 · `ui/account_picker.py` 103 · `ui/account_create.py` 100 (all under `/mnt/Games/Scripts/Linux/finbreak/src/finbreak/`).

**Context I already had before reading the subject:** the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, the finbreak `CLAUDE.md` (its module map includes the FIBR-0085 paragraph), the finbreak memory index, and a git snapshot (HEAD 52e5162, clean tree).

**Specs I read against:**
- `FIBR-0085-batch-import-service.md` and `FIBR-0085-batch-import-review-step.md`, both in full.
- `FIBR-0085-batch-statement-import.md`: §3–§6, §10 and §14.
- `FIBR-0086` §4.6.

**Cross-checks I made in other files:**
- `services/import_.py`: `read_file`, `preview_result`, `retarget`, `commit_import`, `_dedup`, `_key` and `_validate_mapping`.
- The exception types each importer raises (grep only).
- The wizard's call sites into this lane (grep, plus `_create_account_from`).
- `app.py`'s excepthook.
- `AccountService.add_account`.

**Disagreements and tool fallbacks:**
- No disagreement between the brief and my standing rules came up.
- `workspace_search` hit a rate limit once. I used `Grep` scoped to `src/` instead, so no test file was searched.
- I opened no test files.

## Critical (0)

## High (0)

## Medium (3)

**1. The draft cap can be bypassed through the retry route.** [dim 11]
- `services/batch_import.py:546`/`:576` — `` ``scan`` re-checks the draft cap per record, so this cannot walk past it. `` — this docstring is false.
- `scan()` (`:322–343`) has no cap check. Only `scan_step` (`:315`) and `answer` (`:494`) check the cap.
- `_retry_blocked_on_password` (`:548–552`) and `_retry_blocked_on_mapping` (`:578–582`) call `self.scan(other)` directly for every blocked record.
- Result: one answered password can unlock and parse every remaining locked PDF with no cap check at all. At 200 files × 100,000 PDF rows, that is far past INV-11's 200,000-draft bound.
- It also breaks § 4.3: *"an answered file … runs the rest of the ladder, INCLUDING the draft-cap check"*.
- Fix: in both retry loops, check `self.draft_total(files) >= _MAX_BATCH_DRAFTS` before each `scan(other)` and mark the record `not_attempted`/`CAP_REACHED`, or move the cap check into `scan()`.

**2. The retry breaks the one-file-per-turn rule and INV-9.** [dim 2]
- `services/batch_import.py:548–552` — `for other in files: … other.outcome = "waiting"; self.scan(other)`.
- § 4.7 requires a *"one-file-per-event-loop-turn chain"*, so Cancel stays live and the UI repaints. Here, one `answer()` call re-runs the full decrypt ladder for every still-locked file, all inside one Qt slot. Each newly unlocked file also gets its pdfplumber extraction in that same slot.
- Every answer repeats this over every remaining locked file. So each file's stored passwords are tried again after every prompt. That breaks INV-9 (*"Each distinct remembered password is tried at most once per file"*).
- § 10's bound becomes O(prompts × files × passwords) instead of O(files × passwords).
- Worked example: 30 locked PDFs with distinct passwords ≈ 30 × 29 / 2 × (1 + stored + typed) pikepdf opens. The GUI thread freezes between prompts, and nothing yields to the event loop (unexecuted — needs timing on a locked-PDF folder).
- Fix: have the retry only mark the blocked records for re-scan (e.g. back to `waiting`), and let the wizard's chain re-scan them one per turn. Try only the newly added password against each record, not the whole ladder.

**3. Passwords typed during a batch outlive the batch.** [dim 3]
- `services/batch_import.py:270` — `self._run_passwords: list[str] = []`. This is set only in `__init__` and never cleared (grep: the only other uses are `:413` and `:516–517`).
- The service is built once per wizard (`import_wizard.py:188` `self._batch = BatchImportService(service.vault)`) and reused by every `_select_files` → `build`.
- So a pre-RUN Cancel keeps every password typed during the batch in plaintext memory. Those passwords are then silently tried against the next batch's files.
- This contradicts § 4.4 (*"held in memory for the run only"*) and § 4.6 (*"before RUN it drops the whole batch (every held password discarded unwritten)"*).
- Fix: clear `_run_passwords` in `build()` (the start of a new batch), and give the service a `discard()` for the wizard's cancel path to call.

## Low / Info

- **[dim 2] OFX fan-out labels skip the escalation.** `ui/import_batch.py:86–87` — `if siblings > 1 and record.statement_index is not None: labels.append(self_index_label(path.name, …))`.
  - Fan-out rows always use the bare basename. So `/a/bank.ofx` and `/c/bank.ofx`, each with two statements, both render `bank.ofx [1 of 2]`.
  - § 4.6 says the index is appended to the *escalated* label.
  - Fix: run the basename → parent → full-path escalation first, then append the index.
- **[dim 9] Stored passwords get written early and repeatedly.** `services/batch_import.py:605` — `self._settle_password(record)` runs on every `set_account`.
  - A retarget writes the remembered password to each account the user passes through, and the first (wrong) account keeps it.
  - For a matched file, the write happens at SCAN, during `answer()`, before the user has approved anything. A pre-RUN Cancel does not undo it.
  - This conflicts with § 4.6's "discarded unwritten" — see Open questions for which document is right.
  - Fix: defer `_settle_password` to `_commit`'s success path.
- **[dim 4] The batch's account-create copy has drifted from the single-file one.** `ui/import_batch.py:468–469` — `self.accounts_changed.emit(); self._settle(record, account.id)`.
  - The single-file twin (`import_wizard.py` `_create_account_from`) reports the number *actually stored*. It also warns *"It has no account number, so future statements will not file themselves"* when the box was cleared (FIBR-0086 §4.6, as built). The batch copy says nothing.
  - So FIBR-0085 §6's promise that one Create makes the batch "self-curing" silently fails when the number is cleared.
  - Fix: show the same stored-number line in `self._error` (or a status label).
- **[dim 3] Rich text renders in a tooltip and an error label.** `ui/import_batch.py:259` — `item.setToolTip(tooltip)` with the raw file path; `:466` — `self._error.setText(str(exc))`.
  - Qt auto-detects rich text in both, so a directory or file name containing markup renders as HTML.
  - Blast radius is small: local rendering only, and no script runs.
  - Fix: `html.escape` the path, and `setTextFormat(Qt.PlainText)` on the label. [tool: semgrep?]
- **[dim 10] Exceptions are discarded without logging.** `services/batch_import.py:346` — `def _fail(record, reason, _exc)` drops the exception, and `_commit` (`:703–708`) logs nothing either.
  - design.md § Observability commits to logging errors, not contents. A batch SCAN or RUN failure leaves no log line.
  - Fix: `log.warning("batch import file failed: %s", type(exc).__name__)`, with no message text, since messages can carry statement tokens.
- **[dim 16] An unexpected error stops the chain for good.** `services/batch_import.py:703` — `except (ValueError, FinbreakError)`.
  - A `sqlite3` error (disk full, I/O) out of `commit_import`, or out of `preview_result`/`set_pdf_password` during SCAN, escapes the slot.
  - `app.py`'s excepthook reports it, but the chain is never re-armed. Rows stay "Ready to import"/"Waiting…", and a `waiting` row keeps `Import all` off for good; only Cancel exits.
  - The narrow net itself is deliberate (spec § 4.3). This is noted as a failure mode, not a policy breach.
- **[dim 2] The account id is set before its preview is built.** `services/batch_import.py:599` — `record.account_id = account_id` is assigned before `preview_result`/`retarget`.
  - If either raises, the displayed account and the preview's target diverge — INV-5's wrong-account shape.
  - I found no reachable raising path other than `VaultLockedError`, after which the widget is torn down.
  - Fix: assign after the preview is built.
- **[dim 13] Counts use Western digits.** `ui/import_batch.py:264` — `return str(value) if value else ""`. The counts and the `{new}`/`{dup}` values render in Western digits whatever the locale. Fix: `QLocale().toString(value)`.
- Dims 5, 7, 8, 12, 15 and 17: nothing beyond the above.
  - Dim 12 is N/A: no standard is named.
  - Dim 17 is N/A: the batch persists no state of its own beyond the column-width key.
- **[dim 2b] No zombie features.** Every contract-promised entry point has a live caller: `stored_passwords`, `next_question`, `answer`, `cumulative_counts`, `review`, `can_import`, `stop_from`, `scan_step`/`run_step`, `create_requested`, `accounts_changed`, `import_requested`/`cancelled`/`closed`.
- **INFO — what I did not cover:** I did not review the wizard's driver half (`_scan_next`, `_resume_ask`, the INV-8 prompt counter) beyond the call sites. That is another lane's file.

## Covered by spec and looks correct

These are things I opened and checked against source:

- **Records and caps (`batch_import.py`):**
  - The `Outcome` members and writers match § 4.2 (plus the two § 14 fields).
  - `sort_key` coalescing.
  - The `build` file cap happens before any read, and `scan_step` skips terminal records.
  - The draft cap in `scan_step` and `answer` uses `>=` before each file.
- **Parsing:**
  - The OFX fan-out and splice (an empty statement list raises `ValueError` in `ofx_importer.py:91`, so nothing is stranded in `waiting`).
  - The PDF ladder order.
  - `candidate_tables` raises `ValueError`, not `PdfError`, so its own message survives.
  - Standard Bank refusals are `ValueError`.
  - The INV-13 check on both period endpoints.
- **Dedup, review and commit:**
  - `cumulative_counts` matches § 4.5: vault half from `duplicate_row_numbers`, per-account `claimed`, terminal records skipped, `_key` identical to `_dedup`'s.
  - `review` re-derives outcomes in both directions.
  - `can_import` matches § 14.
  - `_commit`'s arguments and caught set match § 4.3.
  - `stop_from` preserves outcomes that already say something truer.
- **Wording (`import_batch.py`):**
  - All ten § 4.8 lines are present, and both `failed` wordings are told apart by whether a preview exists.
  - The unreadable-row clause appears only on `committed`/`already_imported`.
  - The `_translated` strings match the service constants byte-for-byte (checked all six).
- **Controls and dialogs:**
  - The Account-cell gating uses all three § 4.6 tests.
  - The keyboard route, and the Import button off during RUN.
  - `account_picker.py`: the placeholder and OK gating, and the Create button only when there is a hint.
  - `account_create.py`: prefill as printed; B → home loan, D → investment.

## Open questions

- **When is a Remember-ticked password written?** § 4.4 writes it *"at SCAN for a matched file"*. § 4.6 says a pre-RUN Cancel discards *"every held password … unwritten"*. The two spec passages contradict each other, and the code follows § 4.4. I cannot tell which is intended.
- **FIBR-0086 §4.6 vs `account_create.py`.** The spec says family A *"yields no type and the user picks"*. The dialog pre-selects the first entry, "Current" (`account_create.py:64–76`, no placeholder), so a savings or revolving-credit statement becomes a Current account unless the user notices. Either the code is wrong (it needs a placeholder that blocks OK) or the spec means "defaults, editable". I cannot tell which.
- **`scan_step`'s idempotency claim** (`:311–312`, *"makes a re-entered chain idempotent rather than … re-fanning-out an OFX"*) holds only for terminal records. A `ready` OFX record is not terminal. I found no re-entry path, so I am not filing it.

## 3 items to fix first

1. **The draft-cap bypass (Medium 1).** A documented resource cap (INV-11) is simply missing on a common route: one password unlocking a folder of same-bank PDFs. The docstrings also claim the opposite, which will mislead the next reader.
2. **The retry scanning every file in one slot (Medium 2).** It freezes the GUI thread across the exact "30 locked PDFs" case the feature exists for, and it breaks INV-9. The fix also removes the need for most of item 1's extra check.
3. **Typed passwords outliving the batch (Medium 3).** A secret held past the lifetime the spec states. The fix is one line in `build()`, so it is cheap to close.