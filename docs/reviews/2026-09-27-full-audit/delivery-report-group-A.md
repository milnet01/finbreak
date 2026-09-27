GROUP A verify-delivery report — finbreak CHANGELOG [0.1.23]. I edited no project files, and `git status` is clean.
Every run used `finbreak.__file__` = /mnt/Games/Scripts/Linux/finbreak/src/finbreak/__init__.py, `__version__` 0.1.23. pytest runs used pythonpath=src; the repro scripts assert the path at start-up.
Every repro sets HOME and the XDG_* dirs to a fresh `vdA-*` temp dir under scratch, runs offscreen with no network, and patches the single-instance socket name so it never probes the user's real instance. I deleted the fixtures afterwards.
Scripts: /tmp/claude-1000/-mnt-Games-Scripts-Linux-finbreak/6301e83f-835e-4e80-9606-ad46d1c3780f/scratchpad/verify-delivery/A/ (`_env.py` is the isolation prelude).

**Totals: 7 delivered, 4 partial (A2, A3, A5, A12), plus A8 and A9 delivered with an adjacent gap noted.**

## A1 Recovery code — delivered
Promised: "A recovery code — a second way into your vault if you forget your master password" (CHANGELOG [0.1.23])
Evidence:
- Ran test `tests/features/recovery_key/test_recovery_unlock.py` (whole file, pass). `test_recovery_unlock_forces_a_new_master_password` types the exact code and asserts `unlocked` is not emitted, then that the new password opens the vault and the old one fails.
- Ran repro `a1_recovery.py`: 10/10 pass. It covers the exact code; a lowercase form with I/l for 1, extra spaces and hyphens; and no separators. Each opened through `recovery_unlocked`, never `unlocked`.
- A wrong code with a valid check symbol did not open. A typo code and an empty code did not open.
- MainWindow routed to `NewMasterPasswordDialog` with the workspace withheld. After that, the new password unlocked and the old one was refused.
- Ran repro `a1c_fold.py` (2/2): the O-for-0 fold, which the generated code did not contain, passes the check symbol and decodes to the same payload.
Against: src/finbreak/__init__.py 0.1.23 + a scratch vault
Path: `AuthService.first_run` returns the code → `add_recovery_key` → UnlockDialog `_recovery_code` → `_on_recovery_unlock` → `recovery_unlocked` → `MainWindow._on_recovery_unlocked` → NewMasterPasswordDialog → workspace

## A2 Two copies after a crash — partial
Promised: "Two copies of finbreak can no longer open the same vault after a crash." (CHANGELOG [0.1.23])
Evidence:
- Ran test `tests/features/single_instance/test_single_instance.py::test_INV3b_two_launches_recovering_one_stale_socket_do_not_both_win` (pass). It asserts that `listen()` returns only one owner.
- Ran repro `a2_single_instance.py`. It leaves a crash-leftover socket, then interposes launch B while launch A holds the recovery claim. It applies app.py's own post-`listen()` decision to both launches.
- Result: baseline without the race is `('owner', 'stand-down')`, which is correct. The race gives A = owner, B = UNGUARDED.
Against: src/finbreak/__init__.py 0.1.23 + a synthetic stale socket
Path: app.py `listen(guard_name)` → `single_instance.listen` → `_claim` not held → returns None → app.py probes `another_instance_is_running` → False (A has not re-bound yet) → B carries on to `app.exec()`.
Breaks at: src/finbreak/single_instance.py:194-199 (the claim loser returns None) plus src/finbreak/app.py:146-153 (None with no answering owner is treated as "fail open, run unguarded"). A user can still get two windows on one vault. The claim stops two owners, but the loser runs without a guard instead of standing down. It needs the loser to probe inside A's short recovery window, so it is a narrow timing race.

## A3 Blocked recovery explains itself — partial
Promised: "A blocked recovery from an interrupted restore explains itself" (CHANGELOG [0.1.23])
Evidence:
- Ran test `tests/features/backup/test_backup_ui.py::test_FIBR0327_a_failed_recovery_routes_rather_than_crashing_startup` (pass). It asserts only that `VaultStateError` is raised instead of `OSError`, and that the `*.old` copies survive.
- Ran repro `a3_blocked_recovery.py` through the real `finbreak.app.run()`, with `QMessageBox.critical` captured and the read-only filesystem simulated at `os.replace`. Result 3/4:
  - No traceback; run returned 1 and one dialog was shown.
  - The `*.old` copies stayed intact, and a retry once the folder is writable recovers the original.
  - The message is: "The vault install is incomplete or corrupt: mixed install: exactly one of the vault / sidecar is present. Remove the partial data files to start over."
- A mode-read-only data dir cannot be staged as the owner, because `paths.data_dir()` re-chmods it to 0700 on every call. My first attempt was simply recovered.
Against: src/finbreak/__init__.py 0.1.23 + a scratch vault moved to a `*.20260101T000000.old` pair beside a half-installed vault.db
Path: `run()` → `MainWindow.__init__` → `_reconcile_interrupted_restore` → `os.replace` fails (OSError, logged) → `presence_state` raises VaultStateError → app.py:128-137 generic template
Breaks at: src/finbreak/app.py:128-137. The message states the vault state, as the CHANGELOG body says. It does not say why: nothing about an interrupted restore, a folder that cannot be written, or retrying. Its advice, "Remove the partial data files to start over", points the user toward first-run over a recoverable pair.

## A4 Failed first run leaves no open vault — delivered
Promised: "A failed first run no longer leaves the vault open" (CHANGELOG [0.1.23])
Evidence:
- Ran test `tests/features/vault/test_vault.py::test_complete_first_run_closes_the_vault_when_the_sidecar_write_fails` (pass). It asserts `not svc.vault.is_open`.
- Ran repro `a5_damaged_sidecar.py`, A4 section, 3/3. The public `first_run` with `write_sidecar_v2` raising ENOSPC raises OSError, leaves `vault.is_open` False, and `vault.connection` raises VaultLockedError.
Against: src/finbreak/__init__.py 0.1.23 + a scratch dir
Path: `AuthService.first_run` → `complete_first_run` → `Vault.create` (opens) → `write_sidecar_v2` raises → vault closed

## A5 Damaged settings file not reported as wrong password — partial
Promised: "A damaged settings file is now reported as a damaged settings file, not as a wrong password." (CHANGELOG [0.1.23])
Evidence:
- Ran tests `test_vault.py::test_INV6_unlock_distinct_message_for_malformed_sidecar`, `test_FIBR0327_damaged_cipher_level_is_reported_as_a_pairing_problem[*]` and `test_INV2c_malformed_sidecar_raises_kdf_policy_error[*]` (all pass).
- Ran repro `a5_damaged_sidecar.py`, 5/5 structural cases, correct password through the real UnlockDialog. The corruptions were: a JSON syntax byte, the version digit, a memory_kib digit, a kdf key-name typo, and a non-hex salt character.
- Each showed "finbreak can't read this vault's security-settings file…" and left the throttle count at 0. A control run with an intact sidecar unlocked.
- Ran repro `a1b_a5b_extras.py`: one well-formed hex character flipped in `slots.master.salt_hex` produced "Could not unlock. Try again in 1s." and the throttle count went to 1.
Against: src/finbreak/__init__.py 0.1.23 + a scratch vault with a one-byte-mutated vault.kdf.json
Path: UnlockDialog `_on_unlock` → `load_params` raises KdfPolicyError → own message, throttle untouched. A well-formed corruption instead goes to derive → unwrap fails → `_show_failure` → `record_failure`.
Breaks at: src/finbreak/ui/unlock.py `_on_derived` / `_show_failure`. The CHANGELOG body says "A single corrupted byte… made unlocking fail as though you had typed the wrong password — which counts against the lock-out limit". That still happens for any byte that stays valid (a salt or wrapped-key hex digit). Only malformed or out-of-range damage is told apart. The sidecar has no checksum, so this may be inherent, but the sentence claims more than ships.

## A6 Old backups restorable — delivered
Promised: "Backups written by one version stay restorable by later ones." (CHANGELOG [0.1.23])
Evidence:
- Ran test `tests/features/backup/test_backup.py::test_INV20_restores_a_backup_from_an_earlier_release[v0_1_22, v0_1_12]` (pass). The fixtures `v0.1.22-schema13.fbk` and `v0.1.12-schema8.fbk` were written by those releases' own code. The test asserts the restore succeeds and unlocks under the new master, migrates to the latest schema, keeps both sentinel transactions, and writes a v2 sidecar.
- Ran test `test_FIBR0327_widening_the_accepted_set_lets_an_older_fbk_restore` (pass). It restores a real level-3 database in a build that writes level 4, which is the write/accept split the CHANGELOG body describes.
Against: src/finbreak/__init__.py 0.1.23 + tests/fixtures/backup_restore/*.fbk
Path: `BackupService.restore_backup` → accepted-level check → install → unlock → migrations

## A7 Apostrophe in path — delivered
Promised: "Backup export no longer fails for anyone whose home folder contains an apostrophe." (CHANGELOG [0.1.23])
Evidence:
- Ran repro `a7_a10_backup.py`, A7 section, 4/4, all under a scratch dir named `.../O'Brien/it's here`.
- `BackupService.export_backup` to `backup's.fbk` succeeded. `verify_backup` then returned `ok=True` with schema 14.
- A v1 vault under `D'Arcy` upgraded to the v2 sidecar on unlock, which is the "vault upgrade" half of the CHANGELOG sentence.
- The feature test `test_FIBR0327_export_works_from_a_path_containing_an_apostrophe` passes, but it only calls `vault.export_to`. See the list at the end.
Against: src/finbreak/__init__.py 0.1.23 + scratch vaults under directory names containing an apostrophe
Path: `export_backup` → `Vault.export_to` (ATTACH) → zip → `verify_backup` ok. Separately: `AuthService.unlock` (v1) → §13 migration → v2 sidecar.

## A8 Interrupted restore puts back the whole database — delivered (with an adjacent gap)
Promised: "Recovering from an interrupted backup restore now puts back the whole database, and no longer offers to create a new vault over a recoverable one." (CHANGELOG [0.1.23])
Evidence:
- Ran tests `test_backup_ui.py::test_interrupted_restore_recovers_old_pair_at_launch`, `…_recovers_the_wal_siblings_too` and `…_clears_an_orphan_wal_the_original_lacked` (pass). They use fake WAL bytes.
- Ran repro `a8_interrupted_restore.py`, 5/6:
  - (1) A real committed-but-not-yet-written-back row lived only in a 243 KB WAL file. It came back and the vault opened on Unlock.
  - (2) Both live files moved aside, nothing installed: the app shows UnlockDialog, not FirstRun, and the original opens.
  - (4) Control: a truly empty folder gives FirstRun.
Against: src/finbreak/__init__.py 0.1.23 + scratch vaults with a `20260101T000000.old` set
Path: `MainWindow.__init__` → `_reconcile_interrupted_restore` → moves `*.old` (plus -wal/-shm) back → `state()` → UnlockDialog
Breaks at (adjacent, not the promised case): a crash between the two move-aside renames in `services/backup.py` `_install` (lines 624 and 632). That leaves `vault.db.<stamp>.old` with no matching `vault.kdf.json.<stamp>.old`, and the sidecar still live. Reconcile needs a common stamp (`main_window.py:1464-1466`), so it does nothing. The user gets A3's "incomplete or corrupt… remove partial data files to start over" message over a recoverable database.

## A9 Locking clears more of the screen — delivered (with a residue)
Promised: "Locking the vault now clears more of what was on screen" (CHANGELOG [0.1.23]; the body names the per-tab parallel row lists, including account numbers on the Accounts tab)
Evidence:
- Ran tests `test_app_shell.py::test_INV4c_autolock_empties_the_parallel_row_lists_too`, `::test_the_lock_time_wipe_reaches_the_widget_it_is_handed` and `::test_INV4c_autolock_empties_the_rows_before_the_deferred_delete` (pass).
- Ran repro `a9_lock_wipe.py`. It seeds marker strings for an account name, account number, note, transaction and category, visits all 9 tabs, auto-locks without letting the deferred delete run, then deep-scans every widget's Python attributes, item models and label/edit text.
- Before the lock there were 38 hits. After the lock, every table, tree, `_rows`/`_master` list and the account number were cleared.
- 5 survivors remain, all showing the account name: the combo-box models `account_selector` and `txn_account`, two QListView combo popups, and the Forecast tab's `forecast_provenance` label text.
Against: src/finbreak/__init__.py 0.1.23 + a scratch vault with synthetic marker data
Path: `AuthService._on_idle_timeout` → `MainWindow._lock` → `_clear_live` → `_clear_decrypted_rows` (tables, trees, `clear_rows()` duck-type) → `deleteLater`
Note: what the promise names (tables, trees, parallel lists) is delivered. Account names in combo-box models and the forecast provenance label are not wiped at lock time.

## A10 Crafted backup cannot exhaust the machine — delivered
Promised: "A backup file crafted to attack finbreak can no longer exhaust your machine before you have typed a password." (CHANGELOG [0.1.23])
Evidence:
- Ran test `test_backup.py::test_FIBR0327_hostile_kdf_cost_refused_before_any_derivation[*]` (pass). It covers memory above the ceiling, time_cost 0 and above the ceiling, and parallelism 0. It does not cover parallelism above the ceiling.
- Ran repro `a7_a10_backup.py`, A10 section, with `derive_key` replaced by a tripwire. Every case below was refused with BackupError, the tripwire was never hit, each took about 0 s, and peak memory grew by 0 MiB:
  - memory_kib 64 GiB
  - time_cost 10,000,000
  - parallelism 2**24
  - boundaries: parallelism 17, memory_kib ceiling+1
  - a deflate bomb (400 MiB of zeros in a 398 KiB file), refused as "suspicious compression ratio"
- A legitimate .fbk still restores.
- Ran repro `a10b_verify.py` (3/3): `verify_backup` returns `ok=False, reason='bad_kdf_params'` for all three hostile costs, with no key derivation.
- One false fail from my own first check: it expected an exception from `verify_backup`, which reports through its result instead.
Against: src/finbreak/__init__.py 0.1.23 + crafted .fbk files built from a scratch export
Path: `restore_backup` / `verify_backup` → bounded zip read (size/ratio caps) → `validate_untrusted_params` → BackupError before `derive_key`

## A11 Screen reader names every password and recovery-code box — delivered
Promised: "A screen reader can now name every password and recovery-code box." (CHANGELOG [0.1.23])
Evidence:
- Ran tests `test_recovery_unlock.py::test_FIBR0328_password_and_recovery_fields_have_accessible_names` and `test_import.py::test_FIBR0328_custom_date_format_field_has_an_accessible_name` (pass).
- Ran repro `a11_a11y.py`, 17/17. It builds every dialog with a password or recovery field: FirstRun, Unlock, RecoveryCode, NewMasterPassword, the PDF PasswordDialog, BackupRestore, BackupExport, BackupVerify, SetHint and the PDF ExportDialog. Settings has none. For each field it types text, then reads the name the accessibility interface announces (`QAccessible.queryAccessibleInterface().text(Name)`). Every field announces a non-empty name; form-layout fields get it from their label.
Against: src/finbreak/__init__.py 0.1.23 + a scratch vault
Path: each dialog's QLineEdit / `_display` → Qt accessibility interface → Name

## A12 Pinned time zone decides "today" — partial
Promised: "The time zone you pick in Settings now decides what "today" means, not just how dates look." (CHANGELOG [0.1.23])
Evidence:
- Ran `tests/features/datetime_display/test_datetime_display.py` (all FIBR0327 legs pass). `test_FIBR0327_no_ui_module_reads_the_os_clock_directly` greps only for `date.today()`.
- Ran repro `a12_a13_timezone.py`, 1/3 of the A12 checks. The OS day was 2026-09-27; I pinned Pacific/Kiritimati, where it was 2026-09-28.
  - After `_on_settings_saved`, the app clock returns 2026-09-28. That is the source for Home, alerts and forecast.
  - `ManualEntryDialog` still defaults to 2026-09-27.
  - The Transactions date-range default on an empty vault is also 2026-09-27.
Against: src/finbreak/__init__.py 0.1.23 + a scratch vault
Path: Settings save → `MainWindow._on_settings_saved` → `set_app_timezone` → `app_today()` (Home, alerts, forecast follow). Manual entry and the Transactions range instead read `QDate.currentDate()` (the OS zone).
Breaks at:
- src/finbreak/ui/manual_entry.py:47 `QDateEdit(QDate.currentDate())`: a new transaction defaults to the machine's day, not the pinned day.
- The same OS-clock read is at src/finbreak/ui/transactions.py:242 and src/finbreak/ui/import_wizard.py:1493.
- The guard test cannot catch these because it only matches `date.today()`.

## A13 Typed time zone is saved — delivered
Promised: "A typed-in time zone is the one that gets saved" (CHANGELOG [0.1.23])
Evidence:
- Ran tests `test_datetime_display.py::test_FIBR0327_a_free_typed_zone_is_what_gets_saved`, `::test_FIBR0327_free_typed_nonsense_still_degrades_to_system` and `test_settings.py::test_datetime_freetyped_valid_zone_recovered_on_save` (pass).
- Ran repro `a12_a13_timezone.py`, A13 section, 4/4, through the real SettingsDialog save with Johannesburg stored first.
  - Typing Europe/Kyiv or America/Argentina/Ushuaia stored that zone.
  - Typing an empty string or "Narnia/Nowhere" stored "system".
Against: src/finbreak/__init__.py 0.1.23 + a scratch vault
Path: SettingsDialog tz combo edit text → save → `read_datetime_prefs` → `AuthService.set_datetime_prefs` → `datetime_prefs().timezone`

## Feature tests that pass without asserting the promise's own sentence
- A2 `test_INV3b_two_launches_recovering_one_stale_socket_do_not_both_win`: asserts only that `listen()` returns one owner. It never applies app.py's post-listen decision, which is where the loser goes on running unguarded.
- A3 `test_FIBR0327_a_failed_recovery_routes_rather_than_crashing_startup`: asserts that VaultStateError is raised and `*.old` survives. It does not check what the user is told; the actual message is generic and says to start over.
- A5 `test_INV6_unlock_distinct_message_for_malformed_sidecar` and `test_FIBR0327_damaged_cipher_level…`: they use invalid JSON and an out-of-range cipher level, and assert at service level only. Neither checks the throttle, nor a single well-formed corrupted byte.
- A7 `test_FIBR0327_export_works_from_a_path_containing_an_apostrophe`: calls `vault.export_to` directly. It does not run `BackupService.export_backup`, verify the result, or cover the vault-upgrade half.
- A9 `test_INV4c_autolock_empties_the_parallel_row_lists_too`: scans only attributes named `_rows` and `_master`, so combo-box models and label text are unchecked.
- A10 `test_FIBR0327_hostile_kdf_cost_refused_before_any_derivation`: covers parallelism 0 but not an over-ceiling parallelism. Over-ceiling is refused anyway, per my repro.
- A11 `test_FIBR0328_password_and_recovery_fields_have_accessible_names`: covers five fields via `accessibleName()` only, not the whole-app set.
- A12 `test_FIBR0327_no_ui_module_reads_the_os_clock_directly`: matches only `date.today()`, so it misses `QDate.currentDate()` at manual_entry.py:47, transactions.py:242 and import_wizard.py:1493.
- A12 `test_FIBR0327_app_clock_follows_the_pinned_zone`: tests the clock function, not any screen's default date.
- A1 `test_recovery_unlock_forces_a_new_master_password`: types the exact code only. The I/L/O, lowercase and hyphen transcription through the UI was checked only by my repros.