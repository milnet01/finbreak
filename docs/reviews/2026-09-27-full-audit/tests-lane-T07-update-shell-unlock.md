## Chunk T07 — 8 files read

**Line counts as read:** test_auto_update.py 2084 (read in two pages, 1–1240 and 1241–2084) · test_app_shell.py 1162 · test_single_instance.py 312 · test_dialog_lifecycle.py 329 · test_first_run.py 132 · test_unlock_throttle.py 272 · test_password_hint.py 266 · test_password_strength.py 59.

**What was in my context before I read anything:** `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, the finbreak `CLAUDE.md`, the finbreak memory index `MEMORY.md` (it lists the known-trap entries your § D also carries), and a git snapshot at 52e5162.

**Run notes:**
- I ran as the review-lane agent, with no substitute.
- The brief and review-lane.md did not disagree anywhere.
- `mcp__ants__workspace_search` returned `rate_limited` once, and I ran those searches with `Grep` instead.
- One-hop reads: `app.run`, `_install_excepthook`, `_restore_loader_env_if_frozen`, `_relaunch_command`, `gen-signing-key.generate_keypair`, the main_window drain and startup-check sites, `icons._ICON_HUES`/`toolbar_icon`, the `compare_digest` sites in auth.py, `first_run.py`'s persist calls, `update_key`'s constant, and the tests/conftest.py fixtures.

### Findings

**[HIGH] [dim 12] tests/features/auto_update/test_auto_update.py:2054** (runs through :2083)
> self.msleep(_WORKER_DRAIN_MS * 3)
- Consequence: `_WORKER_DRAIN_MS = 1500` (main_window.py:162). The stub thread sleeps 4.5 s. `window.close()` waits the 1.5 s drain, and `worker.wait(_WORKER_DRAIN_MS * 5)` then blocks until the sleep ends. That matches the measured 4.62 s, the slowest test in the suite, and almost all of it is idle.
- Related isolation problem (dim 6): `_DETACHED_WORKERS.clear()` and the final `wait` are not in a `finally`. If any earlier assertion fails, a running thread stays in the module-level `_DETACHED_WORKERS` list and keeps running into later tests.
- Fix: `closeEvent` reads the module global at call time, so monkeypatch `main_window._WORKER_DRAIN_MS` down to about 50 ms. Have the stub block on a `threading.Event` that the test sets before its final wait. Put the set, the wait and the clear in a `finally`.

**[MEDIUM] [dim 6] tests/features/app_shell/test_app_shell.py:1080**
> assert app_mod.run([]) == 0, "a second launch stands down"
- Consequence: `run()` does a lot before the patched guard returns, and none of it is undone:
  - it sets the session QApplication's `setApplicationName("finbreak")`, `setDesktopFileName`, `setWindowIcon` and `setLayoutDirection`;
  - it builds `ThemeController(app)`, parented to the app, and calls `set_theme(load_theme_pref(), persist=False)`. That applies the stored theme to the whole session, and the controller then follows the OS light/dark scheme live.
- Only `sys.excepthook` is restored. Every test that runs after this one runs themed and under the name "finbreak", and the ones before it do not. So anything palette-sensitive is order-dependent — for example `toolbar_icon` colours, which read `_is_dark_theme()`.
- Measured 2.94 s (dim 12). The theme application is the likely cost, but that attribution is my inference and was not run.
- Fix: stub `ThemeController`/`set_theme` and restore the app name and desktop file name in teardown. Or assert the ordering with a spy on `_install_excepthook` and one on the guard.

**[MEDIUM] [dim 1] tests/features/auto_update/test_auto_update.py:1174**
> assert dialog.result() == 0  # neither Accepted nor Rejected
- Consequence: `QDialog.DialogCode.Rejected` is 0, and 0 is also `result()` before the dialog closes. If `_on_update_now` called `reject()`, the prompt would close instead of staying open busy, and the test would still pass. Both "disabled" asserts after it would also still pass. The test's claim ("stays open") is not verified.
- Fix: spy on `dialog.finished` and assert it never fired, or `show()` the dialog and assert `not dialog.isHidden()`.

**[MEDIUM] [dim 1] tests/features/app_shell/test_app_shell.py:802**
> ic = toolbar_icon("lock")  # mapped -> coloured, non-null
- Consequence: the test is named `test_FIBR0116_unmapped_glyph_falls_back_to_neutral`, but `"lock"` is mapped (`icons.py:46 "lock": 25`). The fallback branch (`if hue is None: return icon(name)`) never runs. A crash or a null icon on an unmapped glyph would still pass.
- Fix: use a glyph that has an SVG but no entry in `_ICON_HUES`, and assert the result equals the plain `icon(name)` rendering.

**[MEDIUM] [dim 1] tests/features/dialog_lifecycle/test_dialog_lifecycle.py:165** (the entry runs through :171)
> "transactions.py": ( "TransactionsView: the Transactions tab. It opens CategoryPickerDialog and RuleEditDialog non-blocking via show_modal ...
- Consequence: `transactions.py` is a content widget that opens modal dialogs, which is exactly INV-1's target. It is exempted as a whole file because of its `menu.exec(`, whereas `home.py` sits in `_FILES` with a line-level `menu.exec(` exemption. So a `CategoryPickerDialog(...).exec()` or a `processEvents` loop added to transactions.py passes both INV-1 and INV-7 (the classification check). The test's claim that no content-widget pop-up blocks the event loop does not cover this file.
- Fix: move `transactions.py` into `_FILES` and extend the line-level `menu.exec(` exemption to it.

**[MEDIUM] [dim 1] tests/features/password_hint/test_password_hint.py:178**
> assert "hmac.compare_digest" in source
- Consequence: the grep covers the whole of auth.py, which uses `compare_digest` twice (auth.py:692 and :707). If `verify_password` switched to `==`, the other occurrence keeps this INV-5 test green. The constant-time backstop does not pin the function it names.
- Fix: grep `inspect.getsource(AuthService.verify_password)` instead of the whole file.

**[MEDIUM] [dim 12] tests/features/auto_update/test_auto_update.py:1320** (the `service` fixture, used by :1401, :1425, :1442, :1462, :1487, :1532, :1710, :1726)
> svc.first_run(bytearray(_PW), "ZAR")
- Measured: D15_skip 1.80 s, settings_save 1.26 s, manual_check_error 1.17 s, up_to_date 1.12 s, INV6 1.08 s, the two download_failed tests 1.06 s and 1.03 s, INV9 1.01 s.
- Each one builds a real vault with an Argon2id derivation, and most then build the whole workspace with `_enter_unlocked`, just to reach a slot such as `_on_manual_check_error` that needs neither.
- Support for pinning it on the key derivation: D15_skip, the only one that does a second derivation (`service.unlock`), is the slowest by about 0.6 s. Attribution beyond that is unexecuted.
- Fix: build the vault pair once per module and copy it into `tmp_path`, or use cheap KDF parameters in this fixture.

**[LOW] [dim 1] tests/features/auto_update/test_auto_update.py:285**
> """Until Phase 1's keygen fills the real key, the committed placeholder is all-zero bytes
- Consequence: the committed key is now real (`update_key.py:22`, and INV-15 verifies a real signature against it). The test only proves that a freshly generated key's signature does not verify, which is true of any key, placeholder or not. It checks nothing its name claims.
- Fix: delete it (INV-15 now covers the committed key), or rename it to what it actually proves.

**[LOW] [dim 1] tests/features/auto_update/test_auto_update.py:1128**
> def test_prompt_later_emits_and_does_not_persist(qtbot):
- Consequence: only the signal is asserted, so the "does not persist" half is unchecked. Related: this test and the ones at :1134 and :1169 call `_on_later`, `_on_skip` and `_on_update_now` directly, so a button that is not connected to its slot still passes (the "drive the collaborator" trap).
- Fix: click the buttons, and assert nothing was written to the tmp INI.

**[LOW] [dim 1] tests/features/auto_update/test_auto_update.py:1455** (same pattern at :1496)
> prompt = window._dialog
- Consequence: nothing asserts that `prompt` is an `UpdateDialog`. If `_on_update_found` stopped showing the prompt while unlocked, `prompt` would be `None` and so would `_dialog`. The `_dialog is prompt` guard would pass, the warning would fire, and `not isinstance(window._dialog, UpdateDialog)` would hold. The "closes the busy prompt" claim would pass without a prompt ever existing.
- Fix: add `assert isinstance(prompt, UpdateDialog)` before acting.

**[LOW] [dim 1] tests/features/auto_update/test_auto_update.py:1117**
> assert ".exec(" not in source
- Consequence: INV-9's claim is "never opens a nested event loop", but the test does not search for the `processEvents` pump. `update_dialog.py` is in dialog_lifecycle's exempt list, so that suite's `processEvents` regex never reads it either.
- Fix: reuse the `\.exec\(|processEvents` pattern.

**[LOW] [dim 7] tests/features/unlock_throttle/test_unlock_throttle.py:224**
> now = datetime.now(UTC)
- Consequence: the lockout this test relies on is 4 s against the real clock. If more than 4 s passes between seeding and `_on_unlock` (a loaded runner), `remaining` is 0 and a real Argon2 worker spawns. The test then fails.
- Fix: seed `CAP_N` failures (30 s), or a slightly future `last_fail` (the fail-safe path), or pin the dialog's clock.

**[LOW] [dim 6] tests/features/auto_update/test_auto_update.py:456** (the test at :456–469)
> app._restore_loader_env_if_frozen()
- Consequence: `restore_system_loader_env(os.environ)` edits the real environment directly. Here only `LD_LIBRARY_PATH` and `LD_LIBRARY_PATH_ORIG` are registered with monkeypatch.
- On a host where `LD_PRELOAD` is set with no `_ORIG`, the drop-without-original rule (the behaviour the test at :422 asserts for `_relaunch_env`) removes `LD_PRELOAD` from the environment for the rest of the session, and teardown does not put it back. Example hosts: a CI preload shim, libfaketime, sanitizers.
- The test at :439 registers both variables and is safe.
- Fix: `monkeypatch.delenv("LD_PRELOAD")` / `delenv("LD_PRELOAD_ORIG")` (with `raising=False`) in this test too, or register every variable the restore touches.

### Pre-pass verdicts
- **test_auto_update.py setenv at :307 :315 :386 :387 :415 :416 :425 :427 :445 :446 :447 :476 :571 :591 :603 :801 :802** — false positive. All are `monkeypatch.setenv`, which is undone at teardown. The :445–447 test also registers `LD_PRELOAD` and `LD_PRELOAD_ORIG`, so the direct `os.environ` edit is undone as well.
- **test_auto_update.py :462 :463** — mitigated for the two variables they set. There is a residual `LD_PRELOAD` leak, filed above as the [LOW] dim 6 finding at :456.
- **test_single_instance.py :212, :222** — false positive. They are `monkeypatch.setenv`/`delenv`, and `socket_name()` is re-read after each change, which the three differing asserts show.
- **test_unlock_throttle.py :224** — confirmed (LOW, filed above).
- **test_unlock_throttle.py :244** — false positive. The timestamp reaches no assertion; the test asserts only `fail_count` after the success reset.

### Dimensions scanned
- 1: 8 findings
- 4: settled by the orchestrator; nothing contradicts it in these files
- 5: clean. Every wait is on the asserted state (`waitSignal` on `newConnection`, `waitUntil` on `hasPendingConnections` / `isRunning`). The detached-worker timing has a 3 s margin.
- 6: 3 findings (the `run()` global mutation, the `LD_PRELOAD` leak, and the detached-list cleanup folded into the HIGH dim 12 finding)
- 7: 1 finding
- 8: clean. The one `skipif` (:72) has a reason and a live condition.
- 9: clean. Popen and `os._exit` are stubbed in every `apply()` test, and the relaunch log is set to None. All swap targets are under `tmp_path`. `generate_keypair` writes only to `tmp_path`. Every network test uses an injected fetcher or a monkeypatched `urlopen`; the one real `/bin/sh` run (:1965) runs a tmp script. MainWindow builds without `update_service` get a real UpdateService, but the autouse `window_ini` keeps the opt-in off, so nothing is fetched.
- 11: clean. The placeholder-key test is filed under dim 1.
- 12: 2 findings plus the `run()` measurement (inside the dim 6 entry)
- 14: clean. The only `except ...: pass` (:1961) is in a PID search, not around an assertion.
- 15: N/A — no failing tests in this chunk.

### Noted, not mine
- None.

### Possibly wider
- `run()` sets the session app name to "finbreak". If `paths` resolves directories through `QStandardPaths`/the app name, every later test in the session that calls `paths.*` without a redirect would resolve to the real `~/.local/share/finbreak`. I did not follow `paths` past one hop.
- The `result() == 0` "not closed" idiom may be used in other dialog suites.

### Open questions
- Dim 12 attribution for the `service`-fixture cluster and for `run()`'s 2.94 s: unexecuted. It needs `pytest --durations=0` with a profile of the setup phase versus the call phase.
- `MainWindow.__init__` arms `QTimer.singleShot(0, self._maybe_check_for_update)`. In every `_updater_shell` test built with an installer and the fake set to `enabled=True`, a startup check is therefore pending. It stays dormant only because those test bodies never run the event loop. If a `waitSignal`/`waitUntil` were added, a real `UpdateCheckWorker` would deliver `found` asynchronously while the test drives `_on_update_found` by hand. Settling whether that already happens at teardown needs a run.