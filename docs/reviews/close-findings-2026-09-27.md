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
| 24 | Data loss | code 04 : `backup.py:657-658,550` — retry or backward clock prunes the original vault's copy | |
| 25 | Vault access | code 01 : `crypto.py:594-602` — a damaged optional slot refuses a correct password | |
| 26 | Vault location | code 01 : `paths.py:25-28` — empty `writableLocation` puts the vault in the working dir | |
| 27 | Two instances | code 02 / delivery A2 : `single_instance.py:193-199` + `app.py:146` — claim loser runs unguarded | |
| 28 | Exit crash | delivery C3 : `main_window.py:1991-1992` — a worker still running after the drain aborts the process | |
| 29 | Exit crash | code 14 : `main_window.py:931` — first-run Cancel uses `QApplication.quit()` | |
| 30 | Lock wipe | code 14 / code 16 / delivery A9 : Transfers, Recurring, Home, import wizard, batch review keep decrypted data after a lock | |
| 31 | Unlock | code 15 : `unlock.py:433-470` — password route lacks the `KdfPolicyError` arm | |
| 32 | Unlock | code 15 : `unlock.py:523-540` — derivation errors reported as a wrong password and throttled | |
| 33 | First run | code 15 : `first_run.py:225-244` — a prefs failure after creation loses the recovery code | |
| 34 | Recovery code | code 15 : `recovery_key.py:115-117` — code copyable past the clipboard auto-clear | |
| 35 | Recovery code | code 15 : `recovery_key.py:167-203` — Save before Keep can overwrite the live code's file | |
| 36 | Rich text | code 17 / code 15 : `alerts_dialog.py:106,118`, `unlock.py:217` — bank text and hint rendered as rich text | |
| 37 | Messages | delivery A3 : `app.py:128-137` — blocked restore recovery gives a generic "start over" | |
| 38 | Messages | delivery C5 : `main_window.py` `_on_download_failed` — dropped download shown as a generic failure | |
| 39 | Updater | code 12 : `update_installer.py:400-406` — inherited `$APPIMAGE` targets another app | |
| 40 | Updater | code 12 : `update_dialog.py:118-138` — Esc during download leads to an unannounced relaunch | |
| 41 | Release | code 19 : `release-linux.sh:69-71,202-212` — AppImage not bound to the tag's commit | |
| 42 | Release | code 19 : `release-linux.sh:126`, `release-windows.sh:137` — repair publishes a one-platform manifest | |
| 43 | Release | code 19 : `build-smoke.sh:177-180` — prints a two-asset publish recipe | |
| 44 | Gate | code 20 : `.githooks/pre-push:91,45-71` — untracked imports pass; a non-HEAD ref is gated as HEAD | |
| 45 | Gate | code 20 : `ci-setup.sh:42,76-92` — global `safe.directory '*'`; fixed `/tmp` paths before a root install | |
| 46 | Supply chain | code 20 : `generate-pip-sources.sh:37,59,113` — unpinned, unverified generator | |
| 47 | Packaging | code 20 : `packaging/obs/_service:15` — OBS builds `main`, not the tag | |
| 48 | Packaging | check-code : `packaging/flatpak/io.github.milnet01.finbreak.yaml` — no final newline | |

**Already tracked, to annotate rather than fix:** code 12's signature-binding
finding (FIBR-0169, FIBR-0333); code 20's libxkbcommon finding (FIBR-0346).

## Queued

Every finding not listed above is queued. Filing is by lane: one roadmap item
per lane file, naming each finding it carries. The lane files are the source.
