Group C results (C1–C18) for finbreak's CHANGELOG [0.1.23]. I ran every item. Nothing in the project was edited. All repro scripts are in /tmp/claude-1000/-mnt-Games-Scripts-Linux-finbreak/6301e83f-835e-4e80-9606-ad46d1c3780f/scratchpad/verify-delivery/C/.

**Artefact:** under pytest (config pythonpath=src) and in every repro (PYTHONPATH=src), `finbreak.__file__` = `/mnt/Games/Scripts/Linux/finbreak/src/finbreak/__init__.py`, `__version__` 0.1.23. For pytest this was checked with a scratch probe `test_artefact.py` run with `-c pyproject.toml`; every repro prints it and asserts it.

**Fixture:** every repro uses `common.py`. It sets a fresh sandbox (`sandbox-*`, now deleted) for HOME and XDG_DATA/CONFIG/CACHE/RUNTIME, runs Qt offscreen, redirects `window_settings_path` into the sandbox, and makes a new vault with `AuthService.first_run`. No network is used; update fetching is stubbed. The installer is a fake whose target is inside the sandbox.

## C1 Date format on Transfers/Recurring/Forecast/Alerts — delivered
Promised: "Your date format now reaches the Transfers, Recurring, Forecast and Alerts screens." (CHANGELOG [0.1.23])
Evidence: ran tests `forecast/test_forecast_tab.py::test_FIBR0328_dates_read_in_the_users_format`, `spending_alerts/test_alerts_ui.py::test_FIBR0328_missed_payment_due_date_reads_in_the_users_format`, `transfers/test_transfers.py::test_FIBR0328_date_column_reads_in_the_user_format_and_still_sorts`, `recurring/test_recurring.py::test_FIBR0328_next_due_reads_in_the_user_format_and_still_sorts` and `datetime_display/test_datetime_display.py::test_FIBR0328_settings_save_reaches_the_transfers_recurring_forecast_tabs` — all PASS. Between them they check: dd/MM/yyyy text on all four screens, no raw ISO date left, chronological sorting still correct, a Settings Save reaching the three tabs, and the shell handing the prefs to the alerts dialog.
Against: src/finbreak/__init__.py 0.1.23 [pytest fixtures]
Path: Settings Save → `MainWindow` hands prefs to each tab → formatted cells and labels

## C2 Category buttons after add/delete — delivered
Promised: "Adding or deleting a category no longer leaves the buttons active with nothing selected" (CHANGELOG [0.1.23])
Evidence: ran test `categories/test_categories.py::test_a_refresh_leaves_no_button_live_against_a_gone_selection` (PASS) and repro `repro_views.py c2`. The repro clicks the real Add, Delete and Update buttons (confirm box stubbed to Yes). After each, nothing is selected and Add, Update and Delete are all disabled. As a precondition, selecting a category first enabled them.
Against: src/finbreak/__init__.py 0.1.23 + sandbox vault
Path: `_add_button` / `_delete_button` / `_update_button` click → `_refresh` → buttons disabled

## C3 Closing during an update check — partial
Promised: "Closing during an update check is safer" (CHANGELOG [0.1.23])
Evidence: ran tests `auto_update/...::test_FIBR0204_close_drains_an_inflight_update_worker` and `...::test_FIBR0327_a_detached_worker_survives_gc_and_reaches_no_slot` (both PASS). Ran repro `repro_update_shell.py c3exec <delay>` through a real `app.exec()`, with the window closed 200 ms after the launch check starts:
- check takes 1.0 s: exit 0.
- check takes 3.0 s: exit **134**, stderr `QThread: Destroyed while thread '' is still running` (the process aborts). `repro_update_shell.py c3` without the event loop gives the same result.
Against: src/finbreak/__init__.py 0.1.23 + stub update service (sleeps, no network)
Path: close → `_drain_update_workers` waits up to `_WORKER_DRAIN_MS` = 1500 ms → a worker still running is detached into `_DETACHED_WORKERS` → `run()` returns → Python shuts down and destroys the still-running QThread → abort
Breaks at: src/finbreak/ui/main_window.py:1991-1992 (`setParent(None)` / `_DETACHED_WORKERS.append`). Any check or download still running 1.5 s after close gets a crash with a core dump at exit, not the "Qt warning" the docstring promises. The real check's socket timeout is 30 s (`services/update.py:44`), so quitting on a slow network during the launch check reaches this.

## C4 Startup failure message — delivered
Promised: "A startup failure now says what went wrong instead of nothing at all" (CHANGELOG [0.1.23])
Evidence: ran tests `app_shell/...::test_FIBR0327_an_unhandled_startup_error_is_shown_not_swallowed` and `...::test_FIBR0327_run_installs_the_hook_before_anything_can_fail` (PASS). Ran repro `repro_startup_error.py runtime` through the real `__main__.main([])` → `app.run`, with `MainWindow` raising `RuntimeError`, uncaught. Result: exit 1, and the dialog "finbreak hit an unexpected error and cannot continue: RuntimeError: probe: the data dir is read-only". The `vaultstate` control still shows its own "incomplete or corrupt" dialog.
Against: src/finbreak/__init__.py 0.1.23 + sandbox data dir; `QMessageBox.critical` recorded to a file (a real modal would block offscreen)
Path: `run()` → `_install_excepthook` → exception escapes → hook → critical dialog naming the fault

## C5 Dropped download vs tamper alarm — partial
Promised: "A dropped download says so instead of raising the tamper alarm" (CHANGELOG [0.1.23])
Evidence: ran test `auto_update/...::test_FIBR0327_a_truncated_download_is_not_reported_as_a_bad_signature` (PASS). Ran repro `repro_truncated_download.py` through the real `UpdateService.download_and_verify` and `update_fetch`, with `urlopen` stubbed:
- Truncated download: `UpdateError: could not download the update: download ended early: 4 of 8 bytes`. It is not an `UpdateVerificationError`, and no temp files are left.
- Bad-signature control: `UpdateVerificationError`.
- No Content-Length but a complete body: not flagged as ended early.
- But the shell's `_on_download_failed` shows the same text for both cases: "The update could not be installed. You are still on the current version."
Against: src/finbreak/__init__.py 0.1.23 + stubbed urlopen, fake installer in the sandbox
Path: `download_and_verify` → exception class and message correct → `_on_download_failed(_exc, …)` ignores the exception → one generic warning
Breaks at: src/finbreak/ui/main_window.py `_on_download_failed` (~1802). The user sees neither "download dropped" nor a tamper alarm, and v0.1.22 showed the same generic text. The classification is only visible in the exception, which the UI throws away.

## C6 Self-update from a folder with an apostrophe — delivered (Linux); Windows checked at string level only
Promised: "Self-update works from a folder whose name contains an apostrophe" (CHANGELOG [0.1.23])
Evidence: ran test `auto_update/...::test_FIBR0327_relaunch_actually_execs_an_apostrophe_bearing_path` (PASS; runs a real /bin/sh). Ran repro `repro_relaunch_quote.py`: the real `_relaunch_command` argv, run through /bin/sh, reaches the stand-in image under `plain`, `o'brien`, `it's a "test" $HOME \`x\`` and `ends-with-'`. The Windows tests `test_FIBR0131_ps_single_quote_doubles_embedded_quotes` and `test_FIBR0131_relaunch_command_waits_by_image_path_not_pid` PASS, but they check the command text only; the Windows side was not executed.
Against: src/finbreak/__init__.py 0.1.23 + stand-in script images in the sandbox (no real binary)
Path: `_relaunch_command` → /bin/sh → exec of the image

## C7 "Date range" tick on Transactions — delivered
Promised: "Ticking "Date range" on Transactions no longer empties the table" (CHANGELOG [0.1.23])
Evidence: ran test `transactions_tab/...::test_FIBR0327_ticking_date_range_does_not_empty_the_table` (PASS; row count before and after the tick, range equals the data's span). Ran repro `repro_views.py c7`:
- Empty vault: ticking raises nothing.
- Three rows over 2025-12-31..2026-07-01: all three stay after the tick.
- A range the user narrows survives a refresh.
Against: src/finbreak/__init__.py 0.1.23 + sandbox vault
Path: `_date_enable.setChecked(True)` → range seeded to the data's span → rows kept

## C8 Very large amounts show the stored digits — delivered
Promised: "Very large amounts display the digits that are stored" (CHANGELOG [0.1.23])
Evidence: ran test `amount_input/...::test_FIBR0327_a_large_amount_displays_the_digits_that_are_stored` for en_US, en_ZA, de_DE, fr_FR and sv_SE (PASS). Ran repro `repro_views.py c8` through the real Transactions table:
- ±(2**63−1) shows `R 92,233,720,368,547,758.07` and `-R 92,233,720,368,547,758.07` (all digits).
- 1 cent shows `R 0.01`.
Against: src/finbreak/__init__.py 0.1.23 + sandbox vault
Path: `TransactionRepository.add` → `TransactionsView.refresh` → Amount cell

## C9 Deleting a rule clears the selection — delivered
Promised: "Deleting a rule no longer leaves the next one selected" (CHANGELOG [0.1.23])
Evidence: ran test `table_state/...::test_FIBR0327_deleting_a_rule_does_not_leave_its_row_selected` (PASS; deletes row 0 of 3). Ran repro `repro_vary.py c9`: deleting the last row, and then the only remaining rule, leaves nothing selected with Edit and Delete disabled, and no slot errors.
Against: src/finbreak/__init__.py 0.1.23 + sandbox vault
Path: `RulesWidget` Delete → refill → no selection, buttons off

## C10 PDF month names in the app's language — delivered
Promised: "Exported PDFs name the month in the app's language" (CHANGELOG [0.1.23])
Evidence: ran test `pdf_export/...::test_FIBR0327_period_month_name_follows_the_locale` (PASS; checks the HTML under fr_FR). Ran repro `repro_vary.py c10` on the rendered PDF, read with pdfplumber: de_DE gives "Period: März 2026", and the en_US control gives "March 2026". "Period:" stays English because no .qm translation file was loaded.
Against: src/finbreak/__init__.py 0.1.23 + sandbox vault
Path: `render_pdf_bytes` → period line built through QLocale

## C11 Account names as plain text on Forecast — delivered
Promised: "Account names render as text on the Forecast tab" (CHANGELOG [0.1.23])
Evidence: ran test `forecast/...::test_FIBR0327_both_labels_render_account_names_as_plain_text` (PASS). It checks that the headline and provenance labels are PlainText and contain `<b>Cheque</b>` and `<img src=x>Visa` literally.
Against: src/finbreak/__init__.py 0.1.23 [pytest fixture]
Path: account name → `ForecastWidget` headline and provenance labels

## C12 Failed install explains itself — delivered
Promised: "An update that cannot be installed now explains itself instead of failing silently." (CHANGELOG [0.1.23])
Evidence: ran repro `repro_update_shell.py c12`: the offer is open, then `_on_download_ready` runs with a fake installer whose `apply` raises `UpdateError("disk full")`. One warning appears: "The update could not be installed, so finbreak is still on the current version. disk full". The verified temp is removed and no slot error occurs. In the control run, apply succeeds and no message appears.
Against: src/finbreak/__init__.py 0.1.23 + fake installer, stub update service
Path: `_on_download_ready` → `installer.apply` raises → caught → `QMessageBox.warning`

## C13 Check for updates twice — delivered
Promised: "Choosing Check for updates twice in a row no longer risks a crash on exit." (CHANGELOG [0.1.23])
Evidence: ran repro `repro_update_shell.py c13`:
- A second `_check_for_updates_now` while the first runs keeps the same worker; only one check call is made.
- Close drains it, and the process exits 0.
- Control: a click after the first check finishes does run again.
Against: src/finbreak/__init__.py 0.1.23 + stub update service (1 s check)
Path: `_check_for_updates_now` → running-worker guard returns → close drains → clean exit
Note: the check here ends inside the 1.5 s drain. A check lasting longer than that hits the C3 abort; one click is enough for that.

## C14 Quit and Ctrl+Q save layout and stop background work — delivered
Promised: "Quit and Ctrl+Q now save your window layout and shut background work down cleanly." (CHANGELOG [0.1.23])
Evidence: ran repro `repro_update_shell.py c14` and `c14key`:
- `_action_quit.trigger()` with a running download worker: window.ini gets geometry, last_tab, window_size and window_state; the worker reference is drained; the window closes.
- Ctrl+Q typed into the active main window: layout saved and window closed.
- With the app-modal update prompt open, Ctrl+Q does nothing. That is Qt blocking shortcuts behind a modal dialog, not this change.
Against: src/finbreak/__init__.py 0.1.23 + sandbox window.ini
Path: Quit action / Ctrl+Q → `close()` → `closeEvent` → `_save_geometry` + `_drain_update_workers`

## C15 Auto-lock during the reassign picker / move-under list — delivered
Promised: "The app no longer closes when the vault auto-locks while the Statements reassign picker or the Categories move-under list is opening." (CHANGELOG [0.1.23])
Evidence: the test `statements/...::test_FIBR0059_reassign_autolock_caught` passes but does not cover this (see the list below). Ran repro `repro_views.py c15` using the real lock (`svc.lock()`), then:
- Reassign click: no exception out of the slot and no picker opened (control: before the lock, the picker opened).
- Selecting a category, which rebuilds the move-under list: no exception, and the combo is disabled.
- `repro_misc.py c15pre` confirms that after the lock `list_accounts` and `list_all` really raise `VaultLockedError`, so the guard was actually exercised.
Against: src/finbreak/__init__.py 0.1.23 + sandbox vault
Path: `svc.lock()` → `_on_reassign` / `_rebuild_move_under` → VaultLockedError caught → silent return

## C16 PDF transaction dates follow the date format — delivered
Promised: "Dates in an exported PDF's transactions table now follow your chosen date format." (CHANGELOG [0.1.23])
Evidence: ran repro `repro_views.py c16`, reading the rendered PDF with pdfplumber:
- dd/MM/yyyy gives rows `05/01/2026FIRST -R 12.34` and `28/01/2026SECOND -R 56.78`, with no ISO dates.
- yyyy/MM/dd gives `2026/01/05…` and `2026/01/28…`.
No project test covers this (commit 85a8102 added none).
Against: src/finbreak/__init__.py 0.1.23 + sandbox vault (settings `date_format`)
Path: `SettingsRepository.set("date_format")` → `render_pdf_bytes` → `_transactions_html` → PDF text

## C17 Trend chart labels readable on dark — delivered (dark PDF half withdrawn)
Promised: "The trend chart's month and value labels are now readable on the dark theme and in a dark PDF export." (CHANGELOG [0.1.23])
Evidence: ran test `dashboard/test_charts.py::test_build_trend_chart_themes_both_axis_labels` (PASS; both axes use theme.text). Ran repro `repro_misc.py c17`, which computes WCAG contrast. On every dark theme both axes use the palette's Text colour and the chart background is transparent (`isBackgroundVisible` False):
- midnight: 14.28:1 against the window colour
- graphite: 11.68:1
- emerald: 13.81:1
The PDF is always a light page since FIBR-0217: #1a1a1a on #ffffff, 17.40:1. The dark PDF export no longer exists, so that half of the sentence describes a surface that does not ship.
Against: src/finbreak/__init__.py 0.1.23 (computed colours; nothing inspected visually offscreen)
Path: `home._chart_theme` (palette Text) → `build_trend_chart` → `setLabelsColor` on both axes

## C18 Forecast axis in major units — delivered
Promised: "The Forecast chart's value axis now reads in the same units as the figures beside it." (CHANGELOG [0.1.23])
Evidence: ran test `dashboard/test_charts.py::test_forecast_chart_plots_major_units_not_minor` (PASS). Stored amounts of 860000 and 915050 cents are plotted as y = 8600.00 and 9150.50.
Against: src/finbreak/__init__.py 0.1.23
Path: `ForecastPoint.balance_minor` → `build_forecast_chart` → series y values

## Feature tests that pass but do not check the promise's own sentence
- **C3** `test_FIBR0204_close_drains_an_inflight_update_worker` and `test_FIBR0327_a_detached_worker_survives_gc_and_reaches_no_slot`: they check that the worker reference is dropped, the worker is detached, it survives garbage collection and its signals are cut. Then the second test waits for the worker and clears `_DETACHED_WORKERS` itself, so neither checks that the process exits cleanly. That is exactly where the repro aborts (exit 134).
- **C5** `test_FIBR0327_a_truncated_download_is_not_reported_as_a_bad_signature`: it checks that `update_fetch.download` raises ValueError("ended early"). It does not check what the user is shown, which is the same generic text as for a bad signature.
- **C15** `test_FIBR0059_reassign_autolock_caught`: it replaces the picker and forces `reassign_account` to raise, so it tests the older apply-step guard. It never reaches the guarded `list_accounts` read this release added. The move-under guard has no test at all.
- **C4** `test_FIBR0327_an_unhandled_startup_error_is_shown_not_swallowed`: it calls the installed hook by hand. The companion test only checks that `run()` installs a hook. Neither makes startup actually fail; the repro did that.
- **C2** `test_a_refresh_leaves_no_button_live_against_a_gone_selection`: it calls `_refresh()` directly rather than the add or delete buttons the sentence names; the repro covered those.
- **C10** `test_FIBR0327_period_month_name_follows_the_locale`: it checks the intermediate HTML (`_build_html`), not the rendered PDF; the repro checked the PDF.
- **C6** The Windows tests check the command text only; nothing runs the PowerShell command.
- **C12, C13, C14, C16** have no feature test at all. Their fix commits (0a83b0a and 85a8102) added none, so the evidence for these four is the repros alone.