# Full audit 2026-09-27 — close-findings ledger

The record of one full audit and of closing its findings. It is the
`close-findings` ledger (`~/.claude/skills/close-findings/SKILL.md` § 1),
kept in the repository because the run spans sessions. Its roadmap item is
FIBR-0367.

## Where the next review starts

- **Audited commit: `52e5162`** (2026-09-26). Everything up to and including
  it was reviewed at full depth.
- The local lightweight tag `review-code-last` points at it. A tag is not
  pushed and does not survive a fresh clone; this line does.
- A later CHANGED-mode review diffs `52e5162..HEAD`. When a later full review
  completes, it replaces this section's commit in its own record.

## What ran

| Sweep | Scope | Result |
|---|---|---|
| `check-code --tree` | whole tree | one real finding (the Flatpak manifest's missing final newline) |
| `review-code` FULL | 20 lanes over `src/`, `scripts/`, `packaging/`, `.githooks/`, `.github/workflows/` | [`code-index.md`](2026-09-27-full-audit/code-index.md) |
| `review-tests` FULL | 12 lanes over `tests/`; baseline 2245 passed, 0 failed, 2 skipped | [`tests-index.md`](2026-09-27-full-audit/tests-index.md) |
| `verify-delivery` | the CHANGELOG `[0.1.23]` section, every promise executed | [`delivery-promises.md`](2026-09-27-full-audit/delivery-promises.md), `delivery-report-group-{A,B,C}.md` |

Every lane's return is kept verbatim in
[`2026-09-27-full-audit/`](2026-09-27-full-audit/). A finding is cited below by
lane and location; its quotation and proposed remedy are in that lane's file.

## Settled during the audit

- **The `O_BINARY` finding (code lane 13) is refuted.** On the Windows test
  box, `os.open` without `O_BINARY` wrote `b'a\nb'` as three bytes.
- **The `@Slot()` finding (code lane 15, `first_run.py:179`) is refuted.**
  PySide6 delivered the `textChanged` argument in a probe.
- **Confirmed by probe:** OFX `Infinity`/`sNaN` balance escapes as
  `OverflowError`/`InvalidOperation`; an unterminated CSV quote swallows the
  rows after it; `parse_transaction` accepts a 29-significant-digit amount by
  rounding; a `.fbk` manifest `sqlcipher_compat: []` raises `TypeError`.
- **Confirmed by timestamp:** a test run modified the user's real
  `~/.local/share/finbreak/window.ini` (test lane T03). The vault and its
  sidecar were not touched.

## Scope decision (user, 2026-09-27)

Fix the **serious tier** now: every HIGH, each partially delivered promise,
data-loss and wrong-amount or wrong-date defects, security gaps, and the test
that writes the real `window.ini`. Every other finding is **queued** as a
roadmap item naming its lane file. Nothing is dropped silently.

## The serious tier — to fix, grouped by subject

Each group is one commit with its own sweep (`close-findings` § 3–4).
`disposition` stays empty until the fix lands.

| # | Group | Finding (lane : location) | disposition |
|---|---|---|---|
| 1 | Test isolation | T03 : `test_backup_ui.py:601,671` — `monkeypatch.undo()` lifts the `window_ini` redirect and writes the real INI | fixed — all seven `monkeypatch.undo()` calls became `monkeypatch.context()`; conftest puts `QStandardPaths` in test mode for the session; `tests/test_test_isolation.py` locks both (red run: both legs failed with the fix removed) |
| 2 | Test isolation | T11 : `test_theme.py:115` — `run()` leaks the excepthook and creates the real data dir | fixed — new `app_run_isolation` fixture restores the excepthook, app name, desktop name, direction and icon, and deletes the controller `run()` made; the stub's `aboutToQuit` connection is cut. The data-dir half is closed by row 1's test mode |
| 3 | Test isolation | T07 : `test_app_shell.py:1080` — `run()` leaks app name, theme and controller | fixed — same `app_run_isolation` fixture |
| 4 | Test isolation | T07 : `test_auto_update.py:2054` — 4.5 s idle sleep; cleanup outside `finally` | fixed — drain budget patched to 50 ms, worker released by an `Event`, release/wait/clear in `finally`; 4.6 s → 0.1 s |
| 5 | Test validity | T05 : `test_no_real_data.py:168,166` — leak guard misses digit-adjacent numbers and skips non-UTF-8 files |  fixed — `_leaks()` matches a key INSIDE a run, files decode with `errors="replace"`; two adjacent-digit spellings added to the guard-the-guard test (red: both failed under exact matching); the real-number scan ran clean |
| 6 | Test validity | T12 : `test_release_integrity.py:270` — anti-laundering check anchored to unrelated text |  fixed — anchored to the `python3 -` verify heredoc that loads the key and calls `.verify(`; with the anti-laundering block deleted, gate 1 now fails on both scripts |
| 7 | Test validity | T06 : `test_statements.py:1879,1852` — total-loss wording passes on the "will survive" branch |  fixed — asserts "every one of" and "Nothing is shared", and that "will survive" is absent; the partial-share text now fails the check |
| 8 | Test validity | T03 : `test_vault.py:1045` — `kek_master` wipe not discriminated |  fixed — the spy records the bytes and the test looks for the key's own bytes; red with `_wipe(kek_master)` removed |
| 9 | Test validity | T08 : `test_alert_service.py:127` — salary never recurring; OUT-only rule untested |  fixed — salary seeded evenly and asserted to be a detected IN stream first; red with the OUT filter removed |
| 10 | Test validity | T05 : `test_batch_import_ui.py:546,717,756` — fixed waits before positive asserts |  fixed — all three waits now wait on the asserted state |
| 11 | Wrong date | code 16 / T11 / delivery A12 : `manual_entry.py:47`, `transactions.py:242`, `import_wizard.py:1493` read the OS clock; the guard test greps `date.today()` only |  fixed — new `datetime_format.today_qdate()` used at all three sites; the guard now bans `QDate.currentDate()`, `QDateTime.currentDateTime()` and naive `datetime.now/today()`; new outcome test on the Add-transaction dialog. Red: both failed on the old code |
| 12 | Wrong date | code 11 : `forecast.py:254` — month-end debit orders ratchet to the 28th |  fixed — the detector's `intended_day` rides `RecurringItem.day_of_month` into the forecast and `next_expected`; FIBR-0171 INV-4 and FIBR-0142 D7 amended to record it; service-level test red on the old code (projected Aug 30) |
| 13 | Wrong amount | code 11 : `alerts.py:279` — missing prior months counted as zero spend (check FIBR-0172 first) |  fixed — a prior month holding no transaction is left out of the average (FIBR-0231 § 4.8's rule); FIBR-0172 D3 amended to record it. Two tests: no false spike on two imported months (red on the old code), and a real spike still fires with baseline = the one month there is |
| 14 | Wrong amount | code 10 : `transactions.py:106` — sub-cent input beyond 28 digits is rounded, not refused |  fixed — significant fractional digits counted from the digit tuple with no context; red test on the 29-digit amount; the existing 1e±1000000 legs still pass through `to_minor_storable` |
| 15 | Wrong amount | code 08 : `import_wizard.py:~599-609` — mapping form not reset after a batch Cancel (stale sign flip) |  fixed — new `_reset_unmatched_mapping_form()` called on every unmatched route into the map step (batch, single CSV, single PDF); red test drives a batch Cancel then a single file |
| 16 | Wrong amount | code 13 : `pdf_export.py:318-320,340-342,417` — PDF ignores the negative-style preference |  fixed — `_negative_style()` read from the vault settings, passed at all four amount sites; red test on a brackets vault with two accounts |
| 17 | Data loss | code 17 : `categories.py:304` — rename silently re-parents a deep category |  fixed — when the current parent is not an offered target, "Move under…" lists it first under its full path, so an untouched Update is a pure rename; FIBR-0154 § 4.2 amended to record it. Parametrised test (a Level-3 node with a child, a Level-4 node) red on the old code: the combo rested on a Type |
| 18 | Import loss | code 06 : `csv_importer.py:77` — unterminated quote swallows rows |  fixed — rows are read `strict=True`, so a quote unclosed at end of file refuses the file; a mapped cell holding a line break (the mid-file case, where the description swallowed the rows) is a `RowError`; FIBR-0007 INV-4 amended to record both. Two tests, both red on the old code (no raise; one merged draft imported) |
| 19 | Import crash | code 06 : `ofx_importer.py:189` / `to_minor_storable` — non-finite balance |  fixed — `to_minor_storable` refuses a non-finite amount as `ValueError` before scaling, which also covers `standard_bank.py`, its other caller; four legs added to the INV-7a test (`Infinity`, `-Infinity`, `sNaN` red on the old code; `NaN` was already a `ValueError` by luck of `int()`); forecast spec INV-7a amended to record it |
| 20 | Import loss | code 05 : `standard_bank.py:899-902` (+3), `:243-245`, `:755-757` — page re-anchor unchecked; terminator and boilerplate drop real rows |  fixed — a brought-forward re-anchor that disagrees with the running balance refuses the statement (`_reanchor`, all four sites); a terminator phrase counts only on a line that is not row-shaped; the row test runs before the boilerplate filter. Every terminator and boilerplate line in the fixtures was checked: none is row-shaped, so none changes behaviour. Three tests, each red on the old code; FIBR-0050 D11, D12 and INV-11 amended in the same commit |
| 21 | Security | code 07 : `batch_import.py:546/576,270` — draft cap bypassed on retry; typed passwords outlive the batch |  fixed — both retry loops now go through `_rescan_blocked`, which checks the draft cap before each re-scan; `build()` starts a batch with no typed passwords, and the wizard calls the new `discard_passwords()` on cancel and when a run ends. Two tests red on the old code (draft total 3 over a cap of 2; the next batch's PDF unlocked silently). The cancel/run-end wiring has no test of its own: its outcome is what `build()` already guarantees. The same lane's one-file-per-turn / INV-9 retry finding is not this row and is queued |
| 22 | Hostile input | code 04 : `backup.py:522,730` — crafted `.fbk` escapes as `TypeError`/`RuntimeError` |  fixed — the compat check tests `isinstance` before the frozenset membership; `_read_fbk` maps `RuntimeError` (and so `NotImplementedError`) to `BackupError`, which also covers verify. Tests: list and object compat levels, and a zip whose entries carry the encryption flag (patched at the archive's own header offsets); all red on the old code |
| 23 | Hostile input | code 03 : `migrations.py:56` — empty `schema_version` raises `TypeError` |  fixed — an empty table reads as `None` and meets the existing `SchemaVersionError` guard; test red on the old code (`None[0]`) |
| 24 | Data loss | code 04 : `backup.py:657-658,550` — retry or backward clock prunes the original vault's copy |  fixed — `_install` returns the stamp it moved the replaced vault aside under, and the prune keeps that set (plus the newest whole set when that one has no sidecar) instead of the lexically newest stamp. Two tests red on the old code (a far-future stale set survived while the new one was deleted; the retry deleted the original pair); INV-17 in the backup feature spec amended |
| 25 | Vault access | code 01 : `crypto.py:594-602` — a damaged optional slot refuses a correct password |  fixed — each slot is parsed on its own (`_parse_slot`); an optional one that fails is kept as a `damaged` `SlotRecord` carrying the record found on disk, with empty bytes so its own route refuses it, and `to_dict` writes it back unchanged. Only `master` still bars the vault. Four-shape test (odd-length hex, non-string, missing field, not an object) red on the old code; FIBR-0019 § 6's damaged-record row amended |
| 26 | Vault location | code 01 : `paths.py:25-28` — empty `writableLocation` puts the vault in the working dir | fixed — `data_dir()` refuses an empty or relative location with a `FinbreakError` naming what the system reported, so the startup error dialog shows it instead of the vault landing in, and chmod'ing, the folder finbreak was started from. Test (empty and relative, both red first) checks the refusal, the untouched folder mode and that nothing was created |
| 27 | Two instances | code 02 / delivery A2 : `single_instance.py:193-199` + `app.py:146` — claim loser runs unguarded | fixed — a launch that finds the recovery claim taken now waits for it (up to 2 s, polling `flock`) instead of returning at once; the holder releases it only once bound, so the loser's probe and `app.py`'s re-probe find the owner and the launch exits. Test simulates the winner on a thread (hold claim, bind 0.3 s later, release), red before the fix; red again with the wait set to 0. `app.py` needed no change. Contract row INV-3b added to `tests/features/single_instance/spec.md` |
| 28 | Exit crash | delivery C3 : `main_window.py:1991-1992` — a worker still running after the drain aborts the process | fixed — `run()` now ends through `app._finish`: `settle_detached_workers` gives detached workers a 3 s grace, and one still running ends the process with `os._exit` before interpreter teardown (logging flushed; vault already locked on `aboutToQuit`; the worker's signals blocked at detach). Child-process test with a 30 s blocked worker: red before (rc −6, `QThread: Destroyed while thread '' is still running`), green after, red again with the early exit removed. The drain docstring's "Qt warning" promise corrected |
| 29 | Exit crash | code 14 : `main_window.py:931` — first-run Cancel uses `QApplication.quit()` | fixed — `_on_first_run_rejected` calls `self.close()`, as the Quit action does, so `closeEvent` drains update workers and saves geometry. `test_INV2d_first_run_cancel_quits` asserted the old mechanism (`quit` called) and was re-fixtured to the contract (close path ran, window hidden, no vault); red before the fix. FIBR-0051 INV-2d's test clause and the app_shell spec row updated to the built behaviour |
| 30 | Lock wipe | code 14 / code 16 / delivery A9 : Transfers, Recurring, Home, import wizard, batch review keep decrypted data after a lock | fixed — `_clear_decrypted_rows` now also empties every combo box, label, text field and chart under the dying widget, with its signals blocked first; `clear_rows` added to Transfers, Recurring, the import wizard (parsed text, OFX statements, PDF cells, batch, typed and stored passwords) and the batch review, and Transactions' one now drops `_transfer_labels`. That also covers A9's residue (account names in combos, the forecast provenance label). New `tests/features/app_shell/test_lock_wipe.py` seeds marker data, visits every tab, auto-locks without the deferred delete, and scans attributes, models, combos, labels and charts for it: red on the old code in all three legs, and red again with each of the seven parts removed on its own. The wizard's OFX/PDF fields and passwords are cleared but only the CSV path is exercised |
| 31 | Unlock | code 15 : `unlock.py:433-470` — password route lacks the `KdfPolicyError` arm | fixed — `_on_derived` gained the arm, showing the same security-settings-file message as the load-time arm (now one helper, `_settings_file_damaged`) and leaving the throttle alone. Test beside FIBR-0337 M7's disk-failure one in `tests/features/vault/test_vault.py`: red on the old code (the `KdfPolicyError` escaped the slot) |
| 32 | Unlock | code 15 : `unlock.py:523-540` — derivation errors reported as a wrong password and throttled | fixed — both failure slots now go to `_derivation_failed`, which logs the exception, says the check itself failed (possibly short of memory) in words naming no credential, and does not charge the throttle. Parametrised test over both routes in `tests/features/vault/test_vault.py`: red on the old code (fail_count 0 → 1). The recovery_key test contract's INV-20 clause and its test docstring updated to the new route |
| 33 | First run | code 15 : `first_run.py:225-244` — a prefs failure after creation loses the recovery code | fixed — `_on_derived` guards `complete_first_run` alone; each prefs write is tried on its own after it, and a failure emits the new `prefs_not_saved` signal before the code and `completed`. The shell holds the warning and shows it in the status bar with no timeout once unlocked. Two tests in `tests/features/first_run/test_first_run.py`, one driving `MainWindow` end to end: red on the old code (vault open, no code handed over); mutation-checked on the shell wiring and on the independent amount write. FIBR-0083 INV-8 is silent on this case and needed no amendment; the first_run test contract gained a row |
| 34 | Recovery code | code 15 : `recovery_key.py:115-117` — code copyable past the clipboard auto-clear | fixed — the display stays a `QLineEdit` (a `QLabel` would lose FIBR-0328's announced code; the audit's `setTextInteractionFlags` does not exist on `QLineEdit`). `RecoveryCodeDialog.eventFilter` swallows every mouse button event and the selecting standard keys, routes Copy/Cut keys to `_copy`, and the context menu is off. Measured on a private Xvfb display (xcb, `supportsSelection` True). Before: drag, Shift+End, Shift+Right and Ctrl+A each put the code in PRIMARY; Ctrl+C put it on CLIPBOARD outside the guard. After: PRIMARY unchanged for all nine gestures plus Copy-then-click and Shift+click, and Ctrl+C goes through the guard. New `tests/features/recovery_key/test_code_display.py`, red on the old code for every gesture; each part of the filter mutation-checked. The release half is invisible offscreen (no PRIMARY) — its mutant was measured leaking on Xvfb instead, recorded as INV-27's limit. T13 needed no change |
| 35 | Recovery code | code 15 : `recovery_key.py:167-203` — Save before Keep can overwrite the live code's file | fixed — remedy checked and extended: a warning alone cannot give back an overwritten file, so a Decline after a Save now ASKS, naming the file — Keep the new code (accepts, so the saved file works) / Decline anyway / Go back. The suggested name carries the app clock's day. `_write_code_file` writes `<name>.part` (0600, `O_EXCL`, `O_NOFOLLOW`, stale one cleared) then `os.replace`, and removes the temp on failure. New `tests/features/recovery_key/test_saving_the_code.py` (INV-28): red on the old code for the question, the name and a part-way write failure (old file emptied); each part mutation-checked — all killed except `fsync`, whose symptom is a power loss (no red run possible; kept, as `crypto.write_sidecar_json` does). `test_saving_the_code_chmods_the_file_it_opened_not_whatever_the_path_holds` removed: the post-open chmod it guarded no longer exists; its hazard's successor (a link planted at the temp name, before or after the stale-clear) has two new tests. This also retires lane 15's dim-7 note (silent `fchmod` failure) and tests-lane T02's note on the removed test — nothing to queue for either |
| 36 | Rich text | code 17 / code 15 : `alerts_dialog.py:106,118`, `unlock.py:217` — bank text and hint rendered as rich text | fixed — verified: the alert summary `QLabel`, the Dismiss tooltip and the unlock hint `QLabel` all used Qt's AutoText guess. Both labels now set `PlainText`; a tooltip has no plain mode, so it gets `convertFromPlainText` (escaped HTML) and the accessible name stays raw. Red first: `test_alerts_ui.py` row-36 test (an `<img>` in the merchant name drew an image placeholder in label and tooltip) and `test_password_hint.py` row-36 test (hint label AutoText). FIBR-0216's `toolTip() == accessibleName()` re-fixtured to compare what the tooltip SHOWS — the contract (hover and screen reader say the same) is unchanged. Each of the three parts mutation-checked, each killed. Sweep: the other `setToolTip` calls in `ui/` carry fixed strings, except `import_batch.py` `_set`, whose tooltip is the statement's file path — same class, pre-existing, queued as FIBR-0382 |
| 37 | Messages | delivery A3 : `app.py:128-137` — blocked restore recovery gives a generic "start over" | fixed — verified through the real `run()`: the message named the mixed pair and said to remove the partial files. A failed move-back now raises `InterruptedRestoreError` (a `VaultStateError` subclass), and `run()` says a restore was interrupted, names the folder and the `.old` files, says not to delete them, and says a restart after fixing a read-only or full folder finishes the repair. It also stops a failed move-back with no live files from routing to first-run. Test: `test_a_blocked_recovery_tells_the_user_why_and_not_to_delete`, red first. The adjacent unpaired-`.old` case is FIBR-0383 |
| 38 | Messages | delivery C5 : `main_window.py` `_on_download_failed` — dropped download shown as a generic failure | fixed — verified: `_on_download_failed` ignored its exception. `download_and_verify` now raises `UpdateDownloadError` (an `UpdateError` subclass) for a failure while fetching, and the shell shows three texts: bad signature → a security-check/tamper warning; dropped download → "did not download completely … try again later"; anything else → the old text. Test: `test_a_dropped_download_and_a_bad_signature_tell_the_user_different_things`, red first, both exceptions from the real service; each part mutation-checked |
| 39 | Updater | code 12 : `update_installer.py:400-406` — inherited `$APPIMAGE` targets another app | fixed — verified, and the remedy checked on a real image first: `dist/finbreak-0.1.9-x86_64.AppImage` launched offscreen under a throwaway HOME showed `APPDIR` = its mount and the frozen binary at `$APPDIR/usr/bin/`. `detect_installer` now also requires `sys.frozen` and `sys.executable` under `$APPDIR`. INV-7 left as written: it states a necessary condition ("only when"), which the stricter check still meets, so no amendment and no gate. Test: `test_an_inherited_appimage_variable_does_not_arm_the_updater` (source run; frozen rpm path), red first; the real-image test re-fixtured to the measured layout; both conditions mutation-checked |
| 40 | Updater | code 12 : `update_dialog.py:118-138` — Esc during download leads to an unannounced relaunch | fixed — verified: `_enter_busy` disabled the buttons only, and Esc / the title-bar close reached `reject()`, which hid the prompt the shell still held. `UpdateDialog.reject()` now does nothing while busy and emits `later` before it (Qt's `closeEvent` calls `reject`, so one override covers both). Tests: `test_esc_and_close_cannot_hide_the_prompt_mid_download`, `test_esc_before_the_download_is_later_not_a_hidden_prompt`, red first; both halves mutation-checked (the first check let a guard-less mutant through until it asserted no signal while busy) |
| 41 | Release | code 19 : `release-linux.sh:69-71,202-212` — AppImage not bound to the tag's commit | fixed — verified (remedy adjusted: the lane's "also require `HEAD == @{u}`" would refuse a detached checkout of the tag, which is the refusal's own fix). `release-linux.sh`: where the tag exists on origin, HEAD must be the commit it names and nothing else is asked; before the tag exists, HEAD must be the pushed tip (not ahead, not behind), and `gh release create` gets `--target "$HEAD_SHA"`. Tests EXECUTE the real script in a throwaway repo with a stub `gh`: tag elsewhere → refused before the build; behind the tip → refused; tag at HEAD → builds; detached checkout of the tag → builds. Red first; each guard mutation-checked. The control test caught a first draft that read the tag object's sha instead of its commit. CLAUDE.md § Cutting a release gains one sentence recording the new refusal |
| 42 | Release | code 19 : `release-linux.sh:126`, `release-windows.sh:137` — repair publishes a one-platform manifest | fixed — verified: both scripts started a fresh `SHA256SUMS` whenever an existing release listed none. New `scripts/_manifest-may-start-fresh.sh` refuses when the release lists `SHA256SUMS.sig` or the other platform's artifact (this platform's own leftovers do not block), pointing at CLAUDE.md's re-upload loop; both scripts call it on that branch. Tests run the helper over five asset lists (empty, orphan sig, each platform seeing the other, own-only) plus a placement check in each script; red first, both refusals mutation-checked. `docs/specs/FIBR-0096.md` step 2 records the rule and its "Residual" paragraph, which said deletion led to a fresh one-platform manifest, is narrowed to what is still true |
| 43 | Release | code 19 : `build-smoke.sh:177-180` — prints a two-asset publish recipe | fixed — verified: the `--release` branch echoed `gh release create` with the AppImage and `.sig` only. It now prints "Next: scripts/release-linux.sh publishes these with SHA256SUMS. Do not publish by hand." Test: `test_build_smoke_prints_no_hand_publish_recipe`, red first. The no-key message beside it (advises minting a new signing key) is filed as FIBR-0384 |
| 44 | Gate | code 20 : `.githooks/pre-push:91,45-71` — untracked imports pass; a non-HEAD ref is gated as HEAD | fixed — already, by `7707a28` (FIBR-0373, after the audited commit): the hook refuses `git status --porcelain --untracked-files=all` output and any pushed tip that is not HEAD. Checked against the current hook; `test_an_untracked_file_is_refused` and `test_a_push_of_a_commit_other_than_head_is_refused` execute it and pass |
| 45 | Gate | code 20 : `ci-setup.sh:42,76-92` — global `safe.directory '*'`; fixed `/tmp` paths before a root install | fixed — verified: both still present. `safe.directory '*'` is now written only as root or under `$CI`; every download and extraction goes to a `mktemp -d` directory removed on exit (b9838da). Tests: `test_ci_setup_trusts_every_repository_only_in_a_throwaway_environment`, `test_ci_setup_downloads_into_a_private_directory` (text-level, red first). Executed by `scripts/ci-docker.sh` in CI's image: all four binaries installed, no dubious-ownership error, 2340 passed |
| 46 | Supply chain | code 20 : `generate-pip-sources.sh:37,59,113` — unpinned, unverified generator | fixed — verified: it fetched `master` with `curl -sSL` (no `-f`) and trusted any cached copy. Now pinned to commit `dda10aa` with a sha256, fetched with `curl -fsSL`, and verified on every run, cached or fresh (a failing cache is re-fetched once, then refused). The pinned bytes equal the cached copy that produced the committed `python3-deps.yaml`, so the closure is unchanged. Tests: a text check, and an executed run of a sandboxed copy with stub `curl`/`python`/`flatpak` that must stop on the checksum; red first, the final gate mutation-checked. An early red run of the executed test ran the REAL script and deleted `packaging/flatpak/python3-deps.yaml`; it was recreated from HEAD (only change: the deletion) and the test now runs a copy |
| 47 | Packaging | code 20 : `packaging/obs/_service:15` — OBS builds `main`, not the tag | fixed — verified: `revision` was `main` while the version came from the latest tag. It is now `v0.1.23`; `.claude/bump.json` moves it with `__version__` and its `post_check` refuses a stale one (mutation-checked: a `v0.1.22` revision fails both the check and the test). Test: `test_obs_builds_the_release_tag_not_main`, red first. `packaging/obs/README.md` updated. The lane's sub-points in `obs-submit.sh` (working-tree recipes, a reused `vendor.tar.gz`) are queued as FIBR-0385 |
| 48 | Packaging | check-code : `packaging/flatpak/io.github.milnet01.finbreak.yaml` — no final newline | |

**Already tracked, to annotate rather than fix:** code 12's signature-binding
finding (FIBR-0169, FIBR-0333); code 20's libxkbcommon finding (FIBR-0346).

## Queued

Every finding not listed above is queued. Filing is by lane: one roadmap item
per lane file, naming each finding it carries. The lane files are the source.

## Sweep (rows 37-48)

Rows 1-36 were closed before this section existed; their sweeps ran per
group and are in their commits. From row 37 on, one sweep runs after the
last row lands, and its run-level lists live here.

**must_agree** (opened before each fix):

- row 37 — `docs/specs/FIBR-0051.md` INV-2c (a mixed pair still ends in
  `QMessageBox.critical` + exit 1); `docs/specs/FIBR-0014.md` § install order
  and INV-5 (recovery from the `*.old` pair); `docs/specs/FIBR-0030.md`'s note
  on `_reconcile_interrupted_restore`'s scope; CHANGELOG `[Unreleased]`.
- row 38 — `docs/specs/FIBR-0054.md` INV-4 ("truncated file" among the
  verification failures) and INV-11 (which failures surface a dialog);
  `ui/_update_worker.py`'s docstring on what `failed` carries; CHANGELOG
  `[Unreleased]`.
- row 39 — every document stating the detection rule: `docs/specs/FIBR-0054.md`
  INV-7 and D6, `FIBR-0131.md` INV-1, `FIBR-0155.md` and `FIBR-0159.md`'s
  inert-updater clauses, `docs/security-model.md`'s distro-launch passage, and
  the OBS/Flatpak/auto_update feature `spec.md` rows; CHANGELOG `[Unreleased]`.
- row 40 — `docs/specs/FIBR-0054.md` D15 and Deliverable 12 (the prompt stays
  open until the install relaunches); the auto_update feature `spec.md` INV-9
  row; CHANGELOG `[Unreleased]`.
- row 41 — CLAUDE.md § Cutting a release (the pushed-bump bullet and the
  documented order); `release-linux.sh`'s header; `release-windows.sh`'s own
  headSha check (the model the lane cited); `.claude/bump.json`'s `_comment`.
- row 42 — both scripts' "never regresses the manifest to a single platform"
  comments; `docs/specs/FIBR-0096.md` § step 2 and its Residual paragraph;
  CLAUDE.md § Cutting a release (the half-state re-upload loop the helper
  points to).
- row 43 — CLAUDE.md § Cutting a release (the documented order, which names
  `release-linux.sh` as the publisher); `build-release-appimage.sh`'s header.
- row 45 — CLAUDE.md § Build and test (what `ci-setup.sh` installs and where it
  runs); `ci.yml` (runs as root in its container, `CI` set); `ci-docker.sh`.
- row 46 — `packaging/flatpak/README.md` and `docs/specs/FIBR-0159.md` § 3.6
  (how the generator is obtained); `ci-setup.sh`'s `fetch_verified` (the model).
- row 47 — `docs/specs/FIBR-0155.md` ("fetches the tagged source tarball");
  `obs-submit.sh`'s "pulls the tagged source" comment; `packaging/obs/README.md`;
  `.claude/bump.json` files and `post_check`.

**swept:** (filled at the sweep)

**collateral / surfaced / out_of_scope / falsified:** (filled at the sweep)
