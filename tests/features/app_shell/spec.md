# app_shell — feature-conformance test contract (FIBR-0051)

Enforces `docs/specs/FIBR-0051.md` (P07.5 — app-shell UX redesign). This is the
tiny per-feature test contract (not a multi-file design doc); the design doc is
the cold-eyes-gated spec above. Every invariant below maps to a test in
`test_app_shell.py`.

The shell is `MainWindow(QMainWindow)` (rewritten from `AppShell`): a menubar
(File · View · Window · Help · Donate · Report an Issue), an icon toolbar, a central `QStackedWidget`
content area, and a status bar. First-run + unlock are non-blocking
application-modal `QDialog`s shown over the window; manual entry is a modal
`ManualEntryDialog`; Home is a `HomeView` with a getting-started page + a
transaction table.

| INV | Test | Guarantee |
|-----|------|-----------|
| INV-1 | `test_INV1_chrome_parts_and_action_set` | menubar + toolbar + central `QStackedWidget` + status bar all exist; the 11 canonical `action_*` objectNames resolve (locale-independent) |
| INV-2a | `test_INV2a_first_run_happy_path` | first_run state → Welcome placeholder + `FirstRunDialog`; completing it (real Argon2id) enables chrome + shows Home |
| INV-2b | `test_INV2b_unlock_happy_path` | unlock state → 🔒 Locked placeholder + `UnlockDialog`; wrong pw keeps dialog + chrome disabled; correct pw → Home |
| INV-2c | `test_INV2c_mixed_pair_raises_at_construction` | a mixed vault/sidecar pair raises `VaultStateError` out of `MainWindow.__init__` (run() then shows the critical + exits 1) |
| INV-2d | `test_INV2d_first_run_cancel_quits` | `FirstRunDialog.rejected` → `QApplication.quit` called once, no vault created |
| INV-2e | `test_INV2e_unlock_cancel_leaves_locked_shell` | `UnlockDialog.rejected` → app not quit, locked placeholder current, `button_unlock` re-opens the dialog |
| INV-2f | `test_INV2f_no_cancel_during_derivation_crash` | mid-derivation (stubbed worker) reject()/close is a no-op; forcing `failed()` re-enables Cancel — both dialogs |
| INV-3 | `test_INV3_no_transaction_data_while_locked` | while locked the current content widget is the placeholder (not a populated `HomeView`) |
| INV-4a | `test_INV4a_autolock_destroys_content_same_window` | `AuthService._on_idle_timeout()` → same `MainWindow`, `HomeView` destroyed (`shiboken6.isValid` False after DeferredDelete flush), chrome disabled, count hidden, `self._dialog` is an `UnlockDialog` |
| INV-4b | `test_INV4b_autolock_closes_open_manual_dialog` | auto-lock with `ManualEntryDialog` open destroys it (`shiboken6.isValid` False); `self._dialog` is the re-opened `UnlockDialog` |
| INV-5 | `test_INV5_key_lifetime_untouched` | shell sets `on_auto_lock`; a manual lock wipes the key; unlock holds it |
| INV-6a | `test_INV6a_content_routing_returns_home` | Accounts/Categories/Import actions show the reused widget (prior destroyed); each `done` returns a fresh Home |
| INV-7 | `test_INV7_status_bar_count_and_messages` | count widget shows the plural-aware string, hides on lock, re-shows on unlock; `_status` posts a transient message |
| INV-8a | `test_INV8a_donate_opens_exact_urls` + `test_INV8a_funding_yml_in_sync` | each Donate action calls `openUrl` once with the pinned `QUrl`; exactly 3 calls total; constants match `.github/FUNDING.yml` |
| INV-8b | `test_INV8b_report_issue_opens_url` | the top-level Report-an-Issue action (right of Donate) calls `openUrl` once with the pinned `REPORT_ISSUE_URL` (the repo's `issues/new` form); a browser egress, not an app fetch (FIBR-0156) |
| INV-9 | `test_INV9_manual_entry_roundtrip_from_home` / `_from_non_home` / `test_INV9_manual_entry_cancel_and_invalid` | Add inserts one tx + navigates to fresh Home from either context; Cancel/invalid insert nothing |
| INV-9a | `test_INV9a_home_toggles_empty_and_table` | `HomeView.current_page().objectName()` is `home_page_empty` (0 tx) vs `home_page_table` (≥1 tx) |
| INV-10 | `test_INV10_no_fixed_geometry_in_new_ui` + `test_INV10_format_amount_localised` | no numeric-literal `setGeometry/move/resize` in `ui/*.py`; `_format_amount` renders via `QLocale` |

Harness: reuses the FIBR-0004 `qtbot.waitSignal(dialog.completed/.unlocked)` real-Argon2id pattern on the happy paths; a monkeypatched `DeriveWorker` stub only for INV-2f's mid-flight assertion. All on-disk vaults live under `tmp_path`; no network, no real data.
