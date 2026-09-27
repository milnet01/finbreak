## Chunk T02 — 4 files read

**Line counts as read:** test_failure_modes.py 349 · test_recovery_code.py 744 · test_recovery_unlock.py 627 · test_settings_flows.py 1025.

**Context I already held on arrival:** global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, the finbreak project `CLAUDE.md`, the auto-memory `MEMORY.md` index (it includes the qtbot isHidden and waitUntil-proxy entries that also appear in § D), and a git snapshot (HEAD 52e5162, clean). I read the subject files from disk.

**How I read the bound:** the brief says the conftest chain above my directory is not mine. My tests name the `paths` fixture, which is defined in `tests/conftest.py`, and the framework applies its autouse fixtures (`window_ini`, and the offscreen QPA setting) implicitly. I took these under the brief's "resolved implicitly / named symbol" carve-out and read only those lines: conftest.py:3-17, 49-52, 76-80, 116-130. One `workspace_search` was rate-limited; the retry succeeded, so no check went unrun.

Findings below are ordered by severity. Four sources were opened one hop out to settle Q1: `ui/unlock.py` (`_on_recovery_unlock`, `_on_recovery_derived`, `_show_failure`, `_set_busy`, `_rollback_offer`), `ui/main_window.py` (`_show_unlock`, `_on_recovery_unlocked`, `_enter_unlocked`, `_lock`, `_show_recovery_offer`, `_open_dialog`, `_teardown_dialog`), and `ui/recovery_key.py` (`RecoveryCodeDialog.__init__`, `_save`, `_quit_application`, `build_recovery_offer`).

### Findings

**[MEDIUM] [dim 1] tests/features/recovery_key/test_settings_flows.py:809** (the test starts at line 783)
> alive = [g for g in window.findChildren(ClipboardAutoClear) if shiboken6.isValid(g)]

Consequence: nothing asserts that any guard was ever found under `window` before the two pumps. Today `build_recovery_offer` sets the owner as `parent or QGuiApplication.instance()` (recovery_key.py, `clipboard_owner`). Suppose ownership moved to the application object; the constructor's own default arm already does that. The guards would then pile up on the session `QApplication`, `window.findChildren` would return `[]`, and this test would stay green while it checks nothing. The FIBR-0310 R1 clipboard tests would also stay green, because an app-owned guard still outlives the dialog.
Fix: before the pumps, assert that `window.findChildren(ClipboardAutoClear)` holds three live guards, as a precondition.

**[LOW] [dim 1] tests/features/recovery_key/test_failure_modes.py:237**
> assert ".pre-v2" in asked[0] or "before" in asked[0].lower(), (

Consequence: this passes for any question containing the word "before". That includes a destructive-reset prompt such as "…everything you had before…", which is exactly the confusion the assertion's own message says it guards against ("the user cannot tell it from the destructive reset"). The real text, `_rollback_offer()`, does pass it, but so does the wrong one.
Fix: assert `asked[0] == _rollback_offer()`, the same way the § 6 test in this file compares against `_pairing_broken()`.

**[LOW] [dim 1] tests/features/recovery_key/test_settings_flows.py:771** (the test starts at line 729)
> assert landed == 0o644, (

Consequence: the test is named "chmods the file it opened, not whatever the path holds", but it asserts only the second half. If `os.fchmod(fd, 0o600)` were deleted outright, the pre-existing inode stays 0o644, the swapped-in decoy stays 0o644, and this test passes. Only the sibling test's `overwrite` leg (line 471) catches that mutant.
Fix: hard-link the original target before the swap, and assert that the linked inode ends up 0o600.

### Pre-pass verdicts
- test_recovery_unlock.py:152 `datetime.now(UTC)` (dim 7): **false positive.**
  - The seeded failures and the dialog's gate read the same real UTC clock (`unlock.py` `_on_recovery_unlock`: `self._throttle.remaining(datetime.now(UTC))`).
  - The test asserts the refused state (`_worker is None`, a non-empty countdown), not a timestamp, and that state holds for the whole 4 s owed delay.
  - The only residual risk is a stall of more than 4 s between lines 155 and 158, which contain just `setText` and `submit`.

### Dimensions scanned
- **1:** 3 findings. Every other precondition-guarded negative leg I checked holds:
  - The zero-derivations leg at test_recovery_code.py:326 would be vacuous if its `hash_secret_raw` patch never took effect. The dedup test at :423 shows that patch counting (it asserts exactly `len(one_copy) >= 1` derivations), so it is not vacuous.
- **4:** clean against the orchestrator's count; no shadowed names in these four files.
- **5:** clean.
  - The waits are on the asserted state: the `failed` signal; the error text, where `_set_busy` never writes `_error` and `_error.clear()` runs before the worker starts; `fail_count`; and the offer dialog, checked with `isHidden`.
  - The `window._unlocked` waits at test_recovery_unlock.py:467 and :518 are not proxies. `_enter_unlocked` sets `_unlocked` and opens the offer synchronously in one call (`_open_dialog(..., defer=False)`).
- **7:** clean. The pre-pass candidate is a false positive. Every `generate_code()` or forged code whose outcome matters is guarded by an asserted precondition, or feeds no expected value.
- **11:** clean. No test body is vacuous.
- **14:** clean. The `except Exception as exc: caught = exc` at test_recovery_code.py:568 records the outcome under test and then asserts it. `_wait_or_timeout` and `_wait_for_clipboard_clear` swallow the pytest-qt timeout but always assert the same state afterwards. The patched collaborators (`_confirm_master_password`, `QMessageBox.*`, `read_sidecar`) are layers these tests do not claim to exercise.
- **6:** clean. Per test, `window.ini` (which holds the throttle state) is redirected to `tmp_path` by the autouse `window_ini`. The clipboard is the in-process offscreen one (conftest.py:17). The translator and the clipboard are restored in `finally`.
- **8:** clean. The one `skipif` (POSIX, test_settings_flows.py:470) has a reason and a live condition.
- **9:** N/A. No network or production targets.
- **12:** the 1.18 s test waits for a real 1 s clear timer, which is the point of that test, so it is intentional and not a finding.
- **15:** N/A. Nothing in this chunk fails.

### Noted, not mine
- None.

### Possibly wider
- The shape "negative assertion with no positive precondition that the inspected set was non-empty" (the `findChildren(...) == []` finding) may recur in other chunks' leak and retire tests.

### Open questions
- Thread teardown race, needs a run to settle. I did not open `DeriveWorker`, so this is a hypothesis.
  - **Where:** tests that end right after a recovery-route slot fires, e.g. test_recovery_unlock.py:241-252.
  - **The risk:** they may tear the dialog down while the real `DeriveWorker` thread is still returning from `run()`. If that worker is a `QThread` parented to the dialog, it would be destroyed while still running.
  - **To confirm:** repeat those two tests many times, e.g. `pytest tests/features/recovery_key/test_recovery_unlock.py -k "failure_message" --count=200` with pytest-repeat, and watch for a "QThread: Destroyed while thread is still running" abort.
