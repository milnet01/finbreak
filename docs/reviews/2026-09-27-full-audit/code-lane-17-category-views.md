**Lane 17 — categories, rules, recurring, forecast, month summary, alerts, category picker**

Subject files, with the line count of each as read:
- `ui/categories.py` 385
- `ui/rules.py` 320
- `ui/recurring.py` 272
- `ui/forecast.py` 342
- `ui/month_summary.py` 213
- `ui/alerts_dialog.py` 166
- `ui/category_picker.py` 59

All paths are under `/mnt/Games/Scripts/Linux/finbreak/src/finbreak/`.

**What I arrived holding, before reading anything:**
- the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md` and the finbreak `CLAUDE.md`;
- the finbreak memory index;
- a git snapshot at HEAD 52e5162 naming the FIBR-0331 commits.

None of it concerns this lane's code. I read the subject from disk.

**Tools:** one `workspace_search` was rate-limited, and I ran that search with `Grep` instead, limited to `services/{categorization,categories}.py`. No test file was opened or searched.

## Critical (0)

## High (0)

## Medium (5)

- **[dim 2]** `ui/categories.py:304` — `select_combo_data(self._move_under, item.data(0, _PARENT_ROLE))`
  - **What happens:** when the subject's current parent is not among the offered targets, `select_combo_data` leaves the combo on index 0, the first Type (`ui/_widgets.py:32-37`). I confirmed that. `_on_update` (`:175-179`) then passes that Type to `update_category`, so a rename with "Move under" untouched silently moves the category to the first Type.
  - **When:** any subject at Level 4 or deeper, whose parent is a Level-3 node and never offered; or a Level-3 subject that has children, which is offered Types only. FIBR-0154 § 4.4 says such pre-existing deep data is tolerated.
  - **Which side is wrong:** the code. FIBR-0154 § 4.2 says "leaving it untouched is a pure rename … no wrong-parent risk", and "not to retro-fix tolerated deep data".
  - **Fix:** when the preselect misses, add the current parent as the first entry, or disable re-parent for that subject.
- **[dim 3]** `ui/alerts_dialog.py:106` — `row_layout.addWidget(QLabel(self._summary(alert)))`
  - The label keeps the default `AutoText`. `alert.label` is a merchant name taken from bank text, or a category name.
  - This is the rich-text injection that `month_summary.py:58` and `forecast.py:83/87` were fixed for (FIBR-0327; FIBR-0231 § 4.6 states the threat). The same text goes to `setToolTip` at `:118`, and a tooltip sniffs for rich text too.
  - **Fix:** `setTextFormat(Qt.TextFormat.PlainText)` on the label. For the tooltip, escape the text (`html.escape`), or wrap it so Qt treats it as plain.
- **[dim 7]** `ui/recurring.py:145` — `suggested, confirmed, _summary = self._recurring.snapshot(app_today())`
  - `refresh()` has no `VaultLockedError` guard. `_on_confirm`, `_on_dismiss` and `_on_unconfirm` (`:240/253/266`) call it right after their own guarded write, so an auto-lock between the write and the re-read raises out of a slot.
  - `rules.py:176-180` and `forecast.py:168-184` guard exactly this case, citing FIBR-0211. The module docstring (`:8-9`) claims the widget handles the lock "exactly like `TransfersWidget`".
  - **Fix:** wrap the snapshot and `base_currency()` reads in `try/except VaultLockedError: return`.
- **[dim 7]** `ui/categories.py:357` — `for root in self._categories.children_of(None):`
  - `_refresh()` has the same missing guard. `_on_add`, `_on_update` and `_on_delete` call it after guarded writes (`:164/185/236`), and `_add_children` (`:374`) is a vault read as well.
  - This is a diverged copy of the `rules.py:171-180` pattern.
  - **Fix:** the same guard as `rules.py`.
- **[dim 13]** `ui/categories.py:161`, `:183`, `:234`; `ui/rules.py:240`, `:270` — `self._error.setText(str(exc))`
  - Untranslated English exception text from the services is shown to the user, for example `services/categories.py:159`: `raise ValueError(f"a category named {name!r} already exists here")` and `:113`: `"a category must have a parent Type"`.
  - This breaks design.md § i18n ("every user-facing string through tr()") on a common path: typing a duplicate name.
  - The same text also reaches an `AutoText` label with the user-typed name interpolated.
  - **Fix:** map the exception types to `tr()`'d messages in the UI, and set the error labels to PlainText.

## Low / Info

- **[dim 5]** `ui/forecast.py:188` — `self._chart_view.setChart(build_forecast_chart(...))`
  - Qt's `QChartView::setChart` releases ownership of the previous chart without deleting it. Every refresh (each tab view, each horizon change) may therefore leak a `QChart` and its series.
  - `home.py:510/517/620` uses the same pattern, so the two copies have not diverged.
  - **Unexecuted.** Checking it needs a loop of `refresh()` while counting live `QChart` objects. The fix, if confirmed, is `old = view.chart(); view.setChart(new); old.deleteLater()`.
- **[dim 2]** `ui/categories.py:292/300` — a Level-2 subject with grandchildren (subtree height 2) gets an empty "Move under" combo.
  - `currentData()` is then `None`, and `update_category` raises "a category must have a parent Type" (`services/categories.py:113`), so that node cannot even be renamed.
  - **Fix:** offer the current parent for rename-only.
- **[dim 13]** `ui/forecast.py:248` — `return "+" + _format_amount(display, symbol)`
  - This builds the sign by concatenation, which the design.md § i18n commitment rules out ("no concatenation of display strings"). The same goes for the `", ".join` name lists at `:242`, `:268`, `:272` and `:277`, which hardcode the list separator.
  - **Fix:** use a `tr("+{amount}")` template and a translatable separator.
- **[dim 7]** `ui/rules.py:281` — `delete_rule` / `move_rule` handlers catch only `VaultLockedError`. The service raises nothing else here (`categorization.py:335-341`), so this is nothing found, not a defect.
- **INFO:** `ui/alerts_dialog.py:97` — `_render` calls `setParent(None)` on the row holding the button whose `clicked` is still being delivered (`_on_dismiss` → `_render`). With no other Python reference, PySide deletes that row, and the button with it, inside the button's own signal.
  - Qt's `QAbstractButtonPrivate::click` guards with a `QPointer`, so this is probably safe, but I could not confirm it without running it.
  - `deleteLater()` would remove the question.

## Covered by spec and looks correct

- **`month_summary.py`** against FIBR-0231 § 4.6/4.7:
  - the `abs` magnitude, the 40-character truncation (39 characters plus U+2026), PlainText, one joined label;
  - the partial/tense variants in every slot, the residual-sign selection, `standaloneMonthName` with templates for the year.
- **`categories.py`** against FIBR-0154 § 4.2 for UI-authored trees (height ≤ 1):
  - the Add anchor and the depth cap, root Update/Delete disabled, subject and descendants excluded, childed Level-2 offered Types only;
  - the delete blast-radius prompt uses two `%n` sentences.
- **`rules.py`:** the OK gate requires both a pattern and a leaf; `fill_guard` refill; re-select by id after a move.
- **`recurring.py`:** the tagged sort-safe index; the ISO sort key under a display-formatted date.
- **`forecast.py`:** refresh guard; cash-only denominator; no sorting on the running-balance table.
- **`category_picker.py`:** clean.
- **Zombie features (dim 2b):** every entry point has a non-test constructor or caller in `src` — `main_window.py:861/864/997`, `home.py:174`, `transactions.py:454/476`.

**Dimensions with nothing to report:**
- 4: nothing beyond the diverged guards above.
- 8: nothing, apart from the INFO item.
- 9, 11, 15, 16, 17: nothing found.
- 10 and 12: N/A (no observability surface; no accessibility standard named).

## Open questions

- Can `MonthSummary.cause` be non-`None` when the verdict is `LOWER` or `NORMAL`? `_cause_text` (`month_summary.py:159-179`) compares the positive `excess_minor` with the signed `movement_minor`. A negative movement would always pick "All of it and more". I read only § 4.6–4.7, and the rule that decides this is earlier in the spec.
- `main_window.py:906-923` — `_refresh_tab` calls these refreshes unguarded. Whether a tab change can arrive after a lock is outside this lane.

## 3 items to fix first

1. **The silent re-parent on rename** (`categories.py:304`). It moves a user's data with no warning, on a path the spec explicitly promises is safe.
2. **The AutoText alert label and tooltip** (`alerts_dialog.py:106/118`). Bank-derived text is rendered as rich text, which is the injection class already fixed in the sibling files.
3. **The unguarded `refresh()` / `_refresh()`** in `recurring.py:145` and `categories.py:357`. An auto-lock right after a write crashes the slot, and the fix already exists in `rules.py`.