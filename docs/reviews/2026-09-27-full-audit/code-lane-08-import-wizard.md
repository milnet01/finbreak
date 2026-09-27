# Lane 08 — the import wizard (`src/finbreak/ui/import_wizard.py`)

**Subject line count as read: `src/finbreak/ui/import_wizard.py` = 1805 lines.**

**Already in my context before I read anything:** the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, finbreak's `CLAUDE.md` (including its module map, which describes the batch chain in this file), the finbreak memory index, and a git snapshot (HEAD 52e5162, clean tree). The shared context also includes the brief and the false-positive ledger.

**How I read it:**
- I read the whole file in one `read_region` call covering lines 1–1805. It came back as an offloaded handle, so I paged it by rows with `read_spill`.
- That is a full read, not a line-range split of the subject. It departs from the letter of "split by symbol if you read it in parts", and I am naming it so you can see it.
- `workspace_search` was rate-limited, so I used `Grep`. Every search was scoped to `docs/specs`, `docs/design.md` or named `src/` files. No test tree was searched or opened.

## Critical (0)

## High (0)

## Medium (2)

- **[dim 2] Confirmation line after "Create it" is never shown.**
  - Where: `import_wizard.py:~748` — `self._confirm_account_combo.setCurrentIndex(self._confirm_account_combo.findData(account.id))` — together with `:~1422-1423` in `_on_confirm_account_changed` — `self._account_match_label.clear()` / `self._account_match_label.hide()`.
  - What happens: the index change is deliberately not signal-blocked, so it runs `_on_confirm_account_changed` synchronously. That handler hides `_account_match_label`. Control then returns to `_create_account_from`, which calls only `setText(...)` at `:~755-767` and never `show()` or `setVisible(True)`.
  - Result: FIBR-0086 §4.6's confirmation line ("reports the number **actually stored**") is written into a hidden label. That includes the warning *"Created {name}. It has no account number, so future statements will not file themselves."* The user never sees either message.
  - Not yet run. Confirm with a qtbot run asserting `not wizard._account_match_label.isHidden()` after the dialog is accepted.
  - Fix: call `self._account_match_label.setVisible(True)` after the `setText` in both branches.

- **[dim 4] Mapping-form reset exists in the batch path but not the single-file path.**
  - Where: `_ask_mapping` `:~1734-1737` resets `self._invert_amount.setChecked(False)`, `self._amount_style.setCurrentIndex(0)` and the custom-format text. Its own comment calls a stale invert tick "a money bug" that "silently FLIPS EVERY SIGN".
  - The gap: `_select_file`'s unmatched-CSV branch (`:~599-609`) and `_continue_after_decrypt`'s unmatched-PDF branch do none of this. They also leave `_profile_name` uncleared.
  - How it is reached: FIBR-0085 §4.6 has a pre-RUN batch Cancel return to the pick step *without* rebuilding the wizard (`_on_batch_cancel` → `self._goto_step(_STEP_PICK)`, `:1805`). The user answers a batch mapping with "Amounts are reversed" ticked, cancels, then picks one unmatched CSV. The map step opens with the tick, the debit/credit style and the profile name all still set from the batch.
  - Fix: move the reset into one helper and call it on every unmatched route into `_STEP_MAP`.

## Low / Info

- **[dim 2] A wrong PDF password gives no sign it was wrong.**
  - Where: `:~872` — `self._prompt_pdf_password(data)  # wrong password → re-prompt (INV-3)`.
  - The re-prompt is a fresh `PasswordDialog(self._account_name(), self)`. Its signature (`password_dialog.py:32`) takes no error or message argument, so the second dialog looks exactly like the first. The batch re-prompt in `_ask_password` behaves the same way.
  - `design.md` § Error handling says crypto failures "raise a clear dialog (e.g. "wrong password")". It is unclear whether that sentence reaches the PDF prompt (see Open questions).
  - Fix: pass a "That password didn't work" line on a re-prompt.

- **[dim 13] Two display strings are joined in code instead of translated whole.**
  - Where: `:~1253-1259` — `self.tr("Check these are right — …") + " " + text`.
  - This breaks the design.md § i18n rule against joining display strings (word order and RTL depend on a single translatable sentence).
  - Fix: one `tr("… {samples}")` string with a placeholder.

- **[dim 13] OFX statement label bypasses `tr()`.**
  - Where: `:~630` — `f"{info.account_id} · {info.account_type}"`.
  - The raw OFX account-type token (e.g. `CHECKING`) is shown untranslated, in a string built outside `tr()`.
  - Fix: `tr("{id} · {type}")` plus a translated type map.

- **[dim 2, document side] design.md's example summary does not match the preview.**
  - design.md:236 quotes the summary as "12 of 240 rows couldn't be parsed". The preview actually shows `"{new} new · {dup} duplicate · {err} error"` (`:~1378`) plus per-row error rows.
  - The behaviour matches the intent. The quoted wording is the stale side, so this is for `review-contract`, not a code fix.

- **[dim 7] Possible escaping exception in a slot.** `_on_confirm_account_changed` wraps `retarget` in `except VaultLockedError` only (`:~1426`). Any other `ValueError` or `FinbreakError` from `retarget` would escape the slot. I did not open `import_.py:218` to see what it can raise.

- **[dim 7] Unguarded header read in a timer-driven slot.** `_ask_mapping` calls `read_header(record.source_text)` (`:~1725`) with no guard, inside a slot driven by `QTimer`. SCAN has almost certainly parsed the same header already, so this is defensive only.

- **One line per remaining dimension:**
  - **dim 2b:** nothing found. Back, Create, the table chooser, the OFX chooser and every batch control each have a `connect` in this file. I did not verify who calls `ImportWizardWidget` from outside it.
  - **dim 3:** nothing found. No password reaches an error string or log. The `_stored_pw` plaintext is documented. I did not open the CSV `read_file` size cap (`import_.py:161`).
  - **dim 5:** nothing found.
  - **dim 8:** nothing found.
    - Every chain slot checks the batch phase.
    - `_arm` uses the context-object form of `singleShot`.
    - A lock between turns is caught by `scan_step`/`_commit` (`batch_import.py:337,703`), because `VaultLockedError` subclasses `FinbreakError` (`errors.py:46`).
  - **dim 9:** N/A here (commits go through the service).
  - **dim 10:** no logging in this file; the commitment is presumably met in services (not checked).
  - **dim 11:** nothing found.
  - **dim 12:** N/A.
  - **dim 15:** nothing leaves the machine.
  - **dim 16:** nothing found.
  - **dim 17:** N/A.

## Covered by spec and looks correct

- **FIBR-0086 §4.5 / INV-7a:** `_apply_account_match` seeds the destination under a signal blocker *before* `preview_result` on both the OFX and Standard Bank routes. Non-matched outcomes re-seed from the pick step.
- **FIBR-0085:**
  - INV-8: prompts are counted by record identity and capped at 3.
  - INV-14: the map-step Cancel declines one file, and only `closed` emits `done`.
  - The phase guards stop a second chain from starting.
- **FIBR-0146:** date detection is signal-blocked and has one refresh owner. The Custom… field is revealed for a saved exotic format.
- **FIBR-0321/0249:** the stored-password carry, restore and release are consistent across commit, cancel and re-pick.

## Open questions

- Does design.md's "clear dialog (e.g. "wrong password")" cover the PDF re-prompt, or only unlocking the vault? That decides whether the first Low finding is a code or document gap.
- In a batch, a mapping answer that makes `scan` raise marks the file failed with no second chance (`batch_import.py:510-514`). The single-file path lets the user fix the mapping. I cannot tell whether that is an intended difference.
- A double-click on Import: the button stays enabled until the widget is torn down. Whether a queued second click can commit twice depends on how `MainWindow` deletes the wizard and whether `commit_import` re-checks for duplicates. Not checked.

## 3 items to fix first

1. **The stale mapping form after a batch Cancel.** It can silently flip every sign on an import, which is the money-correctness class this project treats as most serious.
2. **The hidden post-create confirmation.** The user loses the only warning that a number-less account will never auto-file, and the §4.6 contract clause is unmet.
3. **The silent wrong-password re-prompt.** It is cheap to fix, and without it a user cannot tell a typo from a dialog that simply reappeared.