## Chunk T11 — 11 files read

**Line counts as read (total lines, from disk):** tests/conftest.py 382 · tests/test_smoke.py 12 · tests/features/theme/test_theme.py 666 · tests/features/datetime_display/test_datetime_display.py 486 · tests/features/datetime_format/test_datetime_format.py 160 · tests/features/amount_input/test_amount_input.py 551 · tests/features/i18n/test_translatable_strings.py 142 · tests/features/db_performance/test_db_performance.py 227 · tests/fixtures/windows_build/_generate_fixture.py 129 · tests/fixtures/backup_restore/_generate_fibr0361_fixture.py 114 · tests/fixtures/backup_restore/_generate_fibr0302_fixture.py 151

**What I already had in context when I arrived:** ~/.claude/CLAUDE.md, /mnt/Games/CLAUDE.md, the finbreak CLAUDE.md, the finbreak MEMORY.md index (it includes entries on qtbot traps, the app clock and /tmp), and a git snapshot (HEAD 52e5162, recent FIBR-0331 commits). I read every subject file from disk.

**Where my instructions disagreed, and how I settled it:**
- `dimensions.md` says a conftest is context and "never a subject to fire on". My tail says conftest isolation "matters most". I fired only on tests. Where a test's isolation depends on conftest, I cite conftest as the context.
- One `workspace_search` call was rate-limited, so I used `Grep` for that one search.

**Code I opened for Q1, one hop from what the tests name:**
- src/finbreak/ui/theme.py (pref I/O, ThemeController)
- src/finbreak/app.py (`run`, `_install_excepthook`)
- src/finbreak/ui/_datetime_prefs.py
- src/finbreak/datetime_format.py (clock and formatters)
- a search of src/finbreak/paths.py

### Findings

**[HIGH] [dim 1] tests/features/datetime_display/test_datetime_display.py:306** (the test starts at :288)
> pattern = re.compile(r"\bdate\.today\(\)")

Consequence: the test is named `test_FIBR0327_no_ui_module_reads_the_os_clock_directly`, but it checks one spelling only. Three UI modules read the machine's calendar day another way, and the test passes over all three:
- `src/finbreak/ui/manual_entry.py:47`: `QDateEdit(QDate.currentDate())`
- `src/finbreak/ui/import_wizard.py:1493`: `today = QDate.currentDate()`
- `src/finbreak/ui/transactions.py:242`: `first = last = QDate.currentDate()`

The suite is green while the property it names is false today. The Qt-idiomatic call, the one a UI author is most likely to reach for next, is not guarded at all.

Fix: widen the pattern to the other OS-clock calls (`QDate.currentDate`, `QDateTime.currentDateTime`, naive `datetime.now/today`). Add a named allowlist for the reads that are legitimately UTC, such as the `datetime.now(UTC)` throttle reads in unlock.py.

**[MEDIUM] [dim 1] tests/features/datetime_display/test_datetime_display.py:282**
> assert dtf.today() == today_in("Pacific/Kiritimati")

Consequence: nothing checks that Kiritimati's day differs from the system zone's day at the moment the test runs. If `_on_settings_saved` never pushed the zone, `today()` would read the system zone, and the assert would still pass whenever the two days agree:
- on a UTC+2 host: about 12 hours in every 24 (UTC 22:00–10:00)
- on a UTC runner: about 10 hours in every 24 (UTC 00:00–10:00)

So the wiring this test exists to lock is unverified for roughly half of all runs. The sibling test at :238 asserts exactly this kind of precondition; this one does not.

Fix: assert the precondition `today_in(DATETIME_SYSTEM) != today_in(zone)` first. Better, choose Kiritimati or Niue, whichever currently differs from the system day, so the leg can always fail.

**[MEDIUM] [dim 6] tests/features/theme/test_theme.py:115**
> app_mod.run([])

Consequence: `run()` changes process-wide state before the stubbed `MainWindow` raises, and the test restores none of it:
- **Excepthook.** `_install_excepthook()` replaces `sys.excepthook` for the rest of the session with a hook that opens `QMessageBox.critical`. Only palette, style and stylesheet are restored, by `theme_isolation`. Monkeypatch does not cover `sys.excepthook`.
- **Leaked controller and signal.** A ThemeController stays parented to the app, and a MagicMock stays connected to `app.aboutToQuit`.
- **Real data directory.** `AuthService(paths.vault_path(), paths.sidecar_path())` evaluates its arguments even though `AuthService` is stubbed. `paths.data_dir()` creates the real per-user data directory, "created if absent" (`~/.local/share/finbreak`). That is where the user's live vault lives. The conftest autouse `window_ini` redirects only `window_settings_path`.

Any exception that later reaches `sys.excepthook` outside pytest-qt's per-test capture raises a modal dialog, which blocks an offscreen run with nothing on screen.

Fix: add `monkeypatch.setattr(sys, "excepthook", sys.excepthook)`, or stub `app_mod._install_excepthook`, and monkeypatch `paths.vault_path` / `sidecar_path` to `tmp_path` before calling `run()`.

**[LOW] [dim 1] tests/features/datetime_display/test_datetime_display.py:258** (runs to :262)
> assert today_in("Not/AZone") == system_day

Consequence: an implementation that fell back to UTC, or to any fixed zone, instead of the system zone would pass whenever that zone's day equals the system day:
- every hour of the day on a UTC runner
- 22 hours in 24 on a UTC+2 host

The same holds for the `set_app_timezone("")` leg at :261–262. The claimed fallback target is effectively unchecked.

Fix: compare against a zone chosen so its day differs from the system day now, or assert the resolved zone id rather than the day.

**[LOW] [dim 7] tests/features/datetime_display/test_datetime_display.py:228** (to :248)
> east = today_in("Pacific/Kiritimati")  # UTC+14

Consequence: the test reads the wall clock several separate times: `east` and `west` at :228–229, then `today()` at :246 and :248. If midnight passes in Kiritimati or Niue between those reads, `today() == east` fails.

The same unfrozen-clock gap exists at :258/:262, around local midnight, and at :282. The window is microseconds, so it will fail rarely but not never.

Fix: freeze `QDateTime.currentDateTimeUtc` (the one source `today_in` reads) at an instant with known day values in both zones.

**[LOW] [dim 6] tests/features/theme/test_theme.py:374** (repeated at :397, :411, :421, :444, :460, :472, :487, :501, :518, :537, :566, :602, :643)
> controller = theme.ThemeController(app)

Consequence: each controller is parented to the shared QApplication and connected to `styleHints().colorSchemeChanged` (theme.py `ThemeController.__init__`). None is deleted or disconnected, so about 15 accumulate across the suite. Several are left in "system" mode: the INV-7 tests at :395, :409, :417 and the D3 test at :458.

Any later colour-scheme change reaches every one of them, and each re-applies a palette and stylesheet onto whatever test is running then, outside `theme_isolation`'s window. Two things can cause such a change: a test calling `styleHints().setColorScheme`, or a run on a real platform plugin, since conftest only uses `setdefault` for offscreen.

Fix: build the controller in a fixture that disconnects it and calls `deleteLater()` on teardown, for example inside `theme_isolation`.

**[LOW] [dim 1] tests/features/theme/test_theme.py:490** (to :491)
> assert not hasattr(controller, "vault")

Consequence: the "presentation-only, no vault state" claim is checked against exactly two attribute names, `vault` and `_service`. A controller holding the vault as `_vault`, `_auth` or `_svc` passes.

Fix: assert over `vars(controller)` that no value is an `AuthService` or `Vault` instance.

**[LOW] [dim 12] tests/features/theme/test_theme.py:587**
> def test_INV10_EVERY_toolbar_glyph_retints_not_just_home(

Consequence: measured at 1.25 s, just over the 1 s trigger. The test builds a full `MainWindow`, unlocks it, and renders every toolbar glyph twice. It also uses the `service` fixture, whose `first_run` runs a real Argon2id derivation. Which of those costs dominates is not in the baseline; see Open questions.

Fix: if the KDF dominates, add a module-scoped unlocked `service`. If the window build dominates, accept it as the cost of the claim.

### Pre-pass verdicts
- None supplied.

### Dimensions scanned
- 1: 4 findings (datetime_display:306, :282, :258; theme:490)
- 4: settled by the orchestrator. The three fixture generators are `_generate*.py`, have no `test_` functions, and are not collected, by design.
- 5: clean. No sleeps and no network. `qtbot.waitSignal` at amount_input:262 wraps a synchronous click with the default timeout.
- 6: 2 findings (theme:115, theme:374). Clean elsewhere:
  - amount_input's `pinned()` restores `QLocale.setDefault` in a `finally`.
  - every `set_app_timezone` leg restores in a `finally`.
  - the INV-2 theme prefs land in conftest's autouse tmp `window.ini`.
- 7: 1 finding (datetime_display:228; the clock is unfrozen). datetime_format's "system" legs assert by delegation, and the explicit-zone legs are hermetic.
- 12: 1 finding (theme:587). db_performance is NOT perf-marked (`pytestmark = pytest.mark.features` only), so it runs in the gate. It checks query plans (`EXPLAIN QUERY PLAN`, including the INV-5 range terms), schema version, atomic rollback and WAL mode, never wall-clock time, so nothing in it is timing-dependent.
- 8: N/A, no skip or xfail markers in the chunk.
- 9: clean. No network. The real-tree reads in the i18n and OS-clock guards are read-only. The real data-dir write is filed under dimension 6 above.
- 11: clean.
- 14: clean. `theme.set_theme`'s `contextlib.suppress` is production code, and the D4 test at :470 asserts through it deliberately.
- 15: N/A, nothing failing in this chunk.

### Noted, not mine
- The three `QDate.currentDate()` UI sites (manual_entry.py:47, import_wizard.py:1493, transactions.py:242) may themselves be FIBR-0327-class wrong-day defects. That is review-code's.

### Possibly wider
- Other suites (app_shell, single_instance) probably call `app.run()` or `paths.vault_path()` the same way. If so, they repeat the excepthook chaining and the creation of the real `~/.local/share/finbreak`.
- Other GUI suites probably create `ThemeController` instances that are never deleted, adding to the pile of controllers listening for scheme changes.

### Open questions
- Dimension 12 on theme:587: which cost dominates the 1.25 s, Argon2 in `service` or the MainWindow build? Unexecuted. It needs `pytest --durations=0 --setup-show tests/features/theme/test_theme.py::test_INV10_EVERY_toolbar_glyph_retints_not_just_home`, reading setup and call time separately.
- conftest.py:17 uses `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`. If the gate's environment already sets `QT_QPA_PLATFORM` (for example on this Wayland desktop), the GUI tests run on the real compositor, and real scheme flips reach the leaked controllers. Whether the gate's environment sets that variable is something I could not check.
- theme:115, data dir: confirming the real directory is created needs a run with `HOME` pointed at an empty temp directory, followed by listing `$HOME/.local/share/`. Unexecuted.