**Subject line count as read:** `src/finbreak/ui/main_window.py` has 2154 lines. I read all of it with `Read`, in four chunks aligned to symbol boundaries: `read_region` and `read_spill` both spilled on a 111 KB file, so I switched to `Read`. One boundary fell on the blank line after `_on_tab_changed` (900/901), so that method was split across two chunks, but nothing was skipped.

**Context I arrived with (disclosed before reading):** the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, finbreak's `CLAUDE.md`, the finbreak memory index `MEMORY.md`, and a git snapshot (main, clean, recent FIBR-0331 commits). The shared-context packet was also in hand.

**Tool notes:**
- `workspace_search` was rate-limited once. After that I used `Grep` for the security-model and spec searches, scoped only to `docs/` and `src/`.
- I made one malformed tool call by mistake; it did nothing.
- I did not open or search the test tree.

**Contract read:**
- design.md § Architecture, § Components, § Error handling through § Concurrency.
- security-model § 5 header and INV-3.
- The main_window passages in FIBR-0198, 0201, 0192, 0159, 0231 (§4.9) and 0171.
- Cross-checked in code: `recovery_key._confirm_master_password` / `remove_recovery_key`, `auth.reset_vault` / `unlock`, the `backup.restore_backup` except-tuple, `vault.old_copy_sets`, `_update_worker` signals, and `app.py` 118–173.

## Critical (0)

## High (0)

## Medium (3)

- **[dim 8] `main_window.py:931`** — `QApplication.quit()  # no vault can be created — nothing to show`
  - This is the same exit that lines 495–499 fixed for the Quit action. The comment there says `quit()` "exits the event loop without delivering a QCloseEvent, so neither the FIBR-0204 worker drain nor the … geometry save in closeEvent ran".
  - The first-run Cancel path still uses `quit()`. If the startup update check is running, the window is destroyed with it still active. That is the "QThread: Destroyed while thread is still running" abort (exit 134) that `_drain_update_workers` (1940–1993) exists to prevent.
  - When it happens: the update check is armed at line 434 on every launch where `window.ini` has updates opted in. That includes a first-run screen reached with an existing INI: after Start over, a deleted vault, or a reinstall that kept config. The user presses Cancel within the network timeout, then `run()` returns and drops `window` (`app.py:155–157`).
  - Unexecuted — needs: opt-in on, no vault, slow network, Cancel within ~30 s.
  - Fix: call `self.close()` here, as the Quit action does.

- **[dim 3] `main_window.py:252–259`** — `for child in (widget, *widget.findChildren(QWidget)): clear_rows = getattr(child, "clear_rows", None)`
  - The docstring promises that a lock wipes decrypted data at lock time, not when the widget is finally deleted (FIBR-0216/FIBR-0322). That wipe only covers widgets that define `clear_rows`. Grep finds it only in `rules.py:166`, `transactions.py:203`, `accounts.py:468` and `statements.py:132`.
  - These workspace/wizard widgets keep parallel Python lists and have no `clear_rows`:
    - `transfers.py:70–71` — `self._candidates: list[TransferCandidate]`, `self._confirmed`
    - `recurring.py:73–74` — `_suggested_items`, `_confirmed_items`
    - `import_wizard.py:151/155/189` — `_ofx_statements` (ParseResults), `_pdf_candidates` (raw decrypted PDF table cells), `_batch_files`
    - `import_batch.py:128` — `_files`
  - Result: an auto-lock that fires inside a nested modal (the scenario the docstring itself describes) leaves those decrypted rows alive until the modal is dismissed. The mechanism is here; the missing method belongs to those widgets.
  - Fix: add `clear_rows` to each of them.

- **[dim 2] `main_window.py:1679–1680` and `1701–1702`** — `if not self._unlocked: return`
  - Help stays enabled while locked (2137–2138), so Help → Check for updates can be started from the locked screen.
  - Started there, an "up to date" or "error" result is silently dropped: the error is logged, the success shows nothing. That contradicts the promise at 1648–1649: "gives feedback on EVERY outcome". The guard was written for a lock that happens while a check is in flight, but it also swallows checks that began while locked.
  - Fix: record `self._unlocked` at click time, and suppress the result only if the lock state changed since the click.

## Low / Info

- **[dim 7] `main_window.py:1110–1126`, `1166–1199`** — `except (VaultLockedError, OSError, pikepdf.PdfError):` and the backup-export equivalent.
  - `QFileDialog.getSaveFileName` runs a nested event loop, and the auto-lock timer can fire inside it. The export then raises `VaultLockedError`, and the user sees "couldn't be saved there. Please choose another location" over the lock screen, after the export dialog was already torn down.
  - The comment at 1149–1151 ("the auto-lock timer cannot fire mid-export") is only true after the file picker returns.
  - The update handlers guard exactly this case on `_unlocked` (1695–1702); these two do not.
  - Fix: after the picker returns, `if not self._unlocked or self._dialog is not dialog: return`.

- **[dim 2] `main_window.py:414` / `759`** — `self._initial_tab = self._restore_geometry()` is read once, at construction.
  - `_on_tab_changed` saves the last tab on every switch (899), but the next unlock in the same session still uses the value read at launch. After a lock and unlock, the user lands on the launch-time tab, not the last one they used.
  - Fix: re-read `_KEY_LAST_TAB` in `_enter_unlocked`.

- **[dim 2] `main_window.py:1567–1569`** — a successful restore calls `_enter_unlocked()` without the `clear_hint()` / `UnlockThrottle().reset()` that Start over runs (1422–1423). Start over's own comment (1420–1421) calls those "the vault-coupled window.ini keys".
  - After a restore under a new master password, the unlock screen keeps showing a hint written for the replaced vault's password.
  - Whether a contract requires clearing them is under Open questions.

- **[dim 13] `main_window.py:1792–1795`** — `.format(reason=str(exc))` puts an untranslated `UpdateError` message inside a translated sentence. design.md § i18n requires every user-facing string to go through `tr()`.
  - Fix: map known failure kinds to `tr()` strings.

- **[dim 2, doc side is wrong]** Several specs cite line numbers in `main_window.py` that no longer match the code. The code is not wrong here; the fix belongs to `review-contract`/`check-doc-facts`.
  - FIBR-0159:268/310/313/318/354/367/375 (e.g. `main_window.py:1346` for `_open_url`, now 1871)
  - FIBR-0155:139/142/894 (`:787`, `:210-211`)
  - FIBR-0231 §4.9 table (`:799` `_refresh_tab`, now 902; `:1499`, `:1508`)

- **Dimensions with nothing found:**
  - dim 4 — the `_by_stamp` copy (1451–1457) versus `vault.old_copy_sets` names `.old` sets the same way as `backup._install`; no behavioural drift found.
  - dim 5 — nothing found.
  - dim 9 — nothing found. `_reconcile_interrupted_restore` uses `os.replace` plus `fsync_dir`.
  - dim 10 — nothing found; the log calls hold no secrets.
  - dim 11 — nothing found. `_center_kwin` uses a 0600 temp file and unlinks it.
  - dim 12 — N/A.
  - dim 15 — nothing found; the only egress is `_open_url` via the OS browser.
  - dim 16 — nothing beyond the findings above.
  - dim 17 — nothing found; the stored tab index is clamped (759).
  - dim 2b — nothing found. `set_single_instance_guard` has a caller (`app.py:155`); the menu and toolbar actions are all wired.

- **INFO:** I did not read HomeView's rendering. So I cannot say whether its QLabel tiles or charts (not item views, so not cleared by `_clear_decrypted_rows`) hold figures past a deferred-delete lock.

## Covered by spec and looks correct

These are paths I opened and checked:
- **Single-dialog slot** (2108–2134): enforced in `_open_dialog`; the deferred show is guarded by `shiboken6.isValid`.
- **`_lock` sequence** (774–788): matches its INV-3/INV-4b/INV-7 steps.
- **FIBR-0198 §4.1:** the reveal checkbox is reset because `_clear_live` drops the tab refs and `_build_workspace` rebuilds.
- **FIBR-0201 INV-18:** `_on_statement_changed(int)` handles the batch count.
- **FIBR-0192:** `_reset_layout` resizes first and clears `"columns"` last.
- **FIBR-0159 INV-8:** `_in_flatpak` gates `_kde_wayland`, which both center paths consult.
- **FIBR-0171:** the Forecast tab is built after Recurring and refreshed on activation.
- **FIBR-0231 §4.9:** `MonthSummaryService` is passed in and `amount_prefs` is passed by keyword (816–824).
- **Update prompt:** `self._dialog is prompt` plus `isValid` guard it (1743–1813).
- **Worker drain and detach:** `blockSignals` and the `_DETACHED_WORKERS` reference.
- **Second manual-check click:** guarded (1667–1669).
- **Recovery-offer idle-lock:** suspended and resumed (1293–1294, 1328–1329).
- **Auto-lock inside the recovery password gate:** fails closed (`recovery_key.py:493–500`).
- **`_restore_geometry`:** fail-safe on corrupt INI values.
- **Interrupted-restore reconciliation:** WAL-sibling naming matches `backup.py:624–634`; the OSError path is logged, not swallowed.
- **Start over:** `reset_vault` removes the `*.old` sets (`auth.py:741–747`), so reconciliation cannot bring back an erased vault.

## Open questions

- **Wipe order in `_lock`.** Line 779 closes the vault before line 781's `_clear_live` empties the tables. `setRowCount(0)` and `tree.clear()` emit selection and current-item signals. If any tab's handler for those reads the vault, it raises `VaultLockedError` out of `_lock`, which is called from the auto-lock callback. The rest of the lock sequence would then not run: the placeholder, disabling the chrome, and reopening the unlock dialog. I did not read the tabs' handlers. Check each tab's `itemSelectionChanged`/`currentItemChanged` slots.
- **In-progress import destroyed silently.** With the wizard live, every toolbar/View action stays enabled. `_ensure_workspace` (887–896) or a Manual-entry commit (984) rebuilds the workspace and destroys the wizard with no confirmation. Is losing an in-progress import intended? No contract I read addresses it.
- **Hint after restore.** Does FIBR-0014 or FIBR-0029 require the password hint and unlock throttle to be cleared after a restore, as they are after Start over?
- **Amount prefs to the tabs.** `_on_settings_saved` pushes amount prefs only to Home and Transactions. Transfers, Recurring, Forecast and Statements get date prefs only. If they show amounts (not read), an amount-style change would not reach them until they are rebuilt.

## 3 items to fix first

1. **The first-run `QApplication.quit()` (931).** It is a one-line change, and it can abort the app with a core dump on a reachable path.
2. **The missing `clear_rows` in Transfers, Recurring and the import wizard.** Decrypted statement and transaction data outlive a lock, which contradicts the promise in `_clear_decrypted_rows`' own docstring.
3. **The locked-screen manual update check.** Two of its three outcomes give no feedback at all, against the feature's stated contract; the fix is to record the lock state at click time.