**Lane 16 — data views (home, accounts, transactions, statements, transfers, manual entry)**

**Line counts as read from disk:** ui/home.py 665, ui/accounts.py 602, ui/transactions.py 514, ui/statements.py 381, ui/transfers.py 299, ui/manual_entry.py 116.

**What was in my context before I read anything:**
- `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md` and finbreak's `CLAUDE.md`.
- The finbreak memory index. It names a FIBR-0327 "OS clock" guard. I relied on the code for that, not the memory entry.
- A git snapshot: clean `main` at 52e5162.
- `shared-context.md`. My brief and this agent file did not disagree anywhere, so there was nothing to resolve between them.

**Tool incidents:**
- `find_definition` for `today` returned two function bodies from the test tree (`tests/features/import_date_detect/test_import_date_detect.py:191` and `tests/features/pdf_export/test_pdf_export.py:560`). I did not open either file and used nothing from them.
- `workspace_search` was rate-limited once. I fell back to `Grep`, scoped to `src/` and `docs/` only, so the test tree stayed out.

## Critical (0)

## High (0)

## Medium (3)

- **[dim 3] `ui/transfers.py:70-73`** — `self._candidates: list[TransferCandidate] = []` / `self._confirmed: list[ConfirmedTransfer]`
  - **Problem:** the widget has no `clear_rows()`. `main_window.py:230-258` `_clear_decrypted_rows` wipes the item models, then asks each tab for `clear_rows` "by duck type… a tab added later is covered by writing the method". Transfers never wrote it.
  - **Effect:** every suggested and confirmed pair outlives the lock — debit and credit `Transaction`s, descriptions, amounts and account names. That lasts through the deferred-delete window the docstring itself describes (a nested modal loop open at auto-lock). This is FIBR-0322's class, breaching FIBR-0052 INV-3.
  - **Same gap, smaller:** `ui/transactions.py:203-211` `clear_rows` clears `_master` and `_rows` but not `_transfer_labels` (`:114`, holding "Transfer to <account name>").
  - **Fix:** add `TransfersWidget.clear_rows()` emptying both lists, and clear `_transfer_labels` in `TransactionsView.clear_rows`.

- **[dim 3] `ui/home.py:510`, `:480`, `:572`, `:420`** — `col.pie.setChart(build_breakdown_donut(slices, …))`, `self._net_value.setText(…)`, the recurring `QLabel(_format_amount(value, …))`, `self._month_strip.set_summary(…)`
  - **Problem:** at lock, `_clear_decrypted_rows` clears only `QTableWidget` and `QTreeWidget` children plus `clear_rows`. `main_window.py` has no other `QChartView` or `month_strip` handling (grep: only `:230` and `:2104`). HomeView has no `clear_rows`.
  - **Effect:** the donut slices (category names and amounts), the trend chart, the Net label, the column totals, the recurring figures and the month-summary sentence all survive the lock for the same deferral window. FIBR-0052 INV-3 again.
  - **Fix:** a `HomeView.clear_rows()` that sets an empty `QChart()` on the three pies and the trend view, clears the net, total and recurring labels, and calls `_month_strip.clear()`.

- **[dim 13] `ui/manual_entry.py:47`** — `self._date = QDateEdit(QDate.currentDate())`
  - **Problem:** the default date of a new money entry reads the machine's zone. The app clock (`datetime_format.py:66-91`, FIBR-0327) is "the app-wide replacement for `date.today()` on any path that decides what 'now' is". That clock honours the user's pinned zone, and `home.py:305/402` uses it.
  - **Effect:** near midnight, with a pinned zone that differs from the OS zone, the dialog pre-fills the wrong day. That is the wrong-day class on the one hand-entry path.
  - **Same pattern:** `ui/transactions.py:242` (`first = last = QDate.currentDate()`) diverges the same way. Outside this lane, `ui/import_wizard.py:1493` is a sibling.
  - **Fix:** seed the date from `app_today()`, e.g. `QDate(t.year, t.month, t.day)`.

## Low / Info

- **[dim 13] `ui/transfers.py:51,172`** — `_ARROW = "→"` … `f"{item.from_account} {_ARROW} {item.to_account}"`
  - **Problem:** the direction arrow is a hard-coded, untranslated literal assembled by f-string. U+2192 is not mirrored by the bidi algorithm. design.md § i18n says direction-implying arrows "are mirrored explicitly" and bans f-string assembly.
  - **Effect:** with right-to-left account names the cell renders "B → A", with the arrow pointing at the source account. The header `tr("From → To")` is translatable, so it can disagree with the cell.
  - **Fix:** `self.tr("{source} → {target}").format(…)`.
- **[dim 13] Display strings concatenated, against design.md § i18n "never assembled by + / f-string":**
  - `ui/transfers.py:242` — `text += " " + self.tr(...)`
  - `ui/accounts.py:555` — `" · ".join(part for part in (recon_text, key_text) if part)`
  - `ui/statements.py:159` — `f"{start} – {end}"`
  - Transfers is prescribed by FIBR-0201 §4.8 ("gains a second sentence"), so for that site the document may be the side that is wrong.
  - **Fix:** use one tr'd template per combination.
- **[dim 13] Untranslated service text shown in the UI:**
  - `ui/manual_entry.py:114` — `self._error.setText(str(exc))`
  - The same pattern at `ui/accounts.py:337`, `:366` and `:451`.
  - `parse_transaction` and `parse_amount_input` raise English literals ("amount is not a valid number", the `_ambiguous` message). Those become user-facing text that bypasses `tr()`.
  - FIBR-0219 §4.1 designs it this way, so I cannot tell which side is wrong. Also listed under Open questions.
- **[dim 7] `ui/transactions.py:449-460`** — `_on_set_category` calls `self._categorization.leaf_categories_grouped()` with no `VaultLockedError` guard.
  - The sibling actions in the same menu (`:433-447`) are documented as lock-safe "even if the auto-lock fired while the menu was open". That means the authors treat a post-lock click as reachable, and this one would raise out of the slot.
  - Unexecuted. It needs a qtbot run: open the menu, auto-lock, trigger "Set category…".
  - **Fix:** wrap it in `try/except VaultLockedError: return`, as `_apply_category` does.
- **Dimensions with nothing found, one line each:**
  - **[dim 2b]** No zombies. Every promised surface has a caller: HomeView's four signals (`main_window.py:826-831`), `set_alert_count` (`:1013`), `current_prefs` / `selected_account_id` (`:1070-1071`), `changed` / `reassigned` (`:846-847`), `committed` (`:974`), and the prefs setters (`:1593-1607`).
  - **[dim 4]** Nothing found beyond the "today" divergence filed under Medium.
  - **[dim 5]** Nothing confirmed. See the Open question on chart ownership.
  - **[dim 8]** N/A — everything runs on the GUI thread.
  - **[dim 9]** Nothing found. Persistence is owned by the services.
  - **[dim 10]** No logging in these files.
  - **[dim 11]** Nothing found.
  - **[dim 12]** N/A — no accessibility standard is named.
  - **[dim 15]** Nothing found. Copies go through `ClipboardAutoClear`, and account numbers are not copyable.
  - **[dim 16]** Nothing found.
  - **[dim 17]** Nothing found. FIBR-0153 INV-9 covers the stale-layout case.
  - **[dim 3, beyond the two findings]** Nothing found. `QLabel` / `QMessageBox` rich-text auto-detection of user-typed account names is self-input only.

## Covered by spec and looks correct

- **Money trap — manual entry parsing.** The call at `manual_entry.py:105` matches FIBR-0219 §4.6 exactly.
  - `parse_amount_input` returns an exact `Decimal` and never goes through float. It turns every `InvalidOperation` into `ValueError`.
  - `parse_transaction` (`services/transactions.py:45-117`) rejects over-precise input rather than rounding it. It converts `decimal.Overflow` to `ValueError` and rejects zero.
  - So no `ArithmeticError` gets past `_on_add`'s `except ValueError`, and nothing is rounded.
  - FIBR-0051 INV-9 holds: the flow ends in `committed`, and the defensive `None` guard is kept.
- **statements.py against FIBR-0201.**
  - `_confirm_text` follows the ordered §4.5 table and the one-`%n` rule.
  - INV-2, INV-3 (`_selected_ids` resolved before mutating), INV-7 (`len == 1`), INV-11 (Delete all goes through the same path) and INV-18 (a single `changed.emit(len(ids))`) all hold.
  - The FIBR-0083 Period and Imported columns format for display and sort on the stored ISO value.
- **transfers.py against FIBR-0201.**
  - INV-1 holds: the suggested table is multi-select and the confirmed table single-select.
  - INV-3 (`_selected_pairs`) holds.
  - The §4.8 skipped sentence and INV-14's "Rejected." at a count of one hold.
- **transactions.py.**
  - FIBR-0153 INV-6 and INV-7 hold: 6 columns, with the ISO code in `_COL_CURRENCY`.
  - The FIBR-0010 INV-5 learning-offer condition (`:474`) holds.
  - FIBR-0012 INV-9: the filters are AND-combined.
- **home.py.** FIBR-0192 §4.5 holds: `remember_columns(tree)` comes after `setSortingEnabled(False)`.
- **accounts.py.**
  - The account number is masked in the cell and kept raw behind password echo in the form.
  - Reveal restores the selection with signals blocked.
  - `_refresh` guards the whole read block.

## Open questions

- **Category filter vs. transfer label.** The filter (`transactions.py:375-380`) matches on `category_id`. A confirmed transfer leg whose cell reads "Transfer to X" therefore appears under the "Uncategorised" filter. No spec I was given defines the intended behaviour.
- **Chart ownership on every refresh.** `QChartView.setChart` releases ownership of the previous chart. Whether PySide6 then frees it, or it leaks (three donuts and a trend chart per refresh), needs a measurement: count `QChart` instances across repeated `refresh()` calls.
- **Plurals by `.format` instead of `%n`.** `accounts.py:599` ("⚠ {n} periods don't reconcile") and `statements.py:283-299` ("{k} statements") do this. That cannot express plural rules beyond English. FIBR-0201 pins the statements form deliberately. Is that an accepted limit of the localisation commitment?
- **English service errors in the UI.** Is showing them (the Low dim-13 item above) an accepted exception to "every user-facing string through `tr()`", or a defect in FIBR-0219?

## 3 items to fix first

1. **`TransfersWidget.clear_rows`.** It is a one-method fix for decrypted money data surviving a lock, the exact class FIBR-0322 closed for the other tabs. The shell's duck-typed contract makes the omission silent.
2. **A lock-time wipe for HomeView.** Same breach of FIBR-0052 INV-3, and the dashboard holds the most aggregated data.
3. **Seed manual entry's date from `app_today()`.** It is a wrong-day default on the only hand-entry money path. The fix is one line, and it applies equally to `transactions.py:242`.