**Lane 12: update check, signed download, self-install and relaunch, app entry points and self-test (depth pass)**

**Line count of each subject file as I read it:** `services/update.py` 360, `services/update_fetch.py` 198, `services/update_installer.py` 422, `ui/update_dialog.py` 138, `ui/_update_worker.py` 61, `ui/_worker.py` 30, `app.py` 173, `__main__.py` 66, `_selftest.py` 383. All are under `/mnt/Games/Scripts/Linux/finbreak/src/finbreak/`.

**Already in my context before I read anything:**
- `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md` and finbreak's `CLAUDE.md`.
- finbreak's MEMORY.md index. It includes an "AppImage update relaunch caveat" entry, which is this lane's known trap, and a note that review-lane agents have no Bash.
- A git snapshot: clean tree, HEAD 52e5162.

**How I read it:**
- I read the subject files in full from disk.
- Contracts read: FIBR-0054 lines 1–545 and 576–589, FIBR-0131 lines 66–280, and security-model.md § 2.
- Cross-references opened: `main_window.py` 1608–1832, 1960–1993 and 2108–2134, plus `loader_env.py`.
- I never opened a test file. The one test-tree grep was a count (dimension 2b's authorised case).
- `mcp__ants__workspace_search` hit its rate limit, so every later search used `Grep`, with the test ban kept by not searching there.
- My brief and review-lane.md did not disagree anywhere.

## Critical (0)

## High (1)
- **[dim 2b]** `services/update_installer.py:409` — `def is_update_supported() -> bool:` — **This is a promised feature that nothing calls.**
  - FIBR-0054 D7, INV-7 and Deliverables 14 and 15 say the startup check and the Settings checkbox are gated on `is_update_supported()`.
  - It has **zero callers under `src/`**; the tests reference it 15 times.
  - The shell gates on `self._installer is not None` instead (`main_window.py:1024`, `:1616`, `:1653`). `check_for_update` does the same.
  - So `can_self_update()` still has no production caller. The docstring at `:414-420` ("this asks it, which is what makes adding a real precondition … take effect") is false.
  - There is no behaviour change today, because both installers return True.
  - Fix: use `is_update_supported()` (or `self._installer.can_self_update()`) at those three sites and in `check_for_update`, or correct the docstring.

## Medium (4)
- **[dim 2]** `ui/update_dialog.py:118-138` — `def _enter_busy(self)` only disables the three buttons. **Esc and the title-bar close button still work while the download runs.**
  - Esc calls `reject()`, which hides the dialog. `_open_dialog` (`main_window.py:2108-2123`) connects nothing to `finished`, so the hidden dialog stays in `self._dialog`.
  - When the download finishes, `_on_download_ready`'s check `self._dialog is prompt` passes. The app then swaps and relaunches with no visible prompt; on Linux that also wipes the key.
  - A user who pressed Esc meaning "cancel" gets an unannounced restart. This contradicts D15 and Deliverable 12 ("stays open … until the install relaunches").
  - Before the busy state, Esc hides the dialog without emitting `later`, leaving a hidden modal in the dialog slot.
  - Fix: override `reject()` and `closeEvent()`. Ignore them while busy; otherwise emit `later`.

- **[dim 3]** `services/update.py:336` — `update_key.public_key().verify(signature, data)` — **The signature covers only the file's bytes, not its version or platform.**
  - Security-model § 2 names an attacker who can write GitHub releases but has no signing key. That attacker can publish tag `v9.9.9` carrying an **older, genuinely signed** AppImage and its real `.sig`.
  - Verification passes and the user is downgraded to a version with known defects. That version is below 9.9.9, so it is offered again on every launch.
  - The same attacker can rename a signed `.exe` and its `.sig` to the `-x86_64.AppImage` names. `os.replace` then puts a Windows binary at `$APPIMAGE` and the app is bricked until reinstalled.
  - FIBR-0054's "Rollback" out-of-scope item is about reverting after a failed launch, not this. I found nothing in security-model.md covering it (grepped rollback, downgrade and replay).
  - Fix: sign a small manifest (asset name, version, sha256) and require it to match `info.version` and the installer's suffix.

- **[dim 3]** `services/update_installer.py:400-406` — `raw = os.environ.get("APPIMAGE")` … `return AppImageInstaller(path)` — **An inherited `$APPIMAGE` makes the updater target the wrong file.**
  - Any non-AppImage finbreak (the rpm/deb package, or `python -m finbreak`) launched from inside *another* AppImage (a terminal, IDE or launcher) inherits that app's `APPIMAGE`, and the file exists.
  - An opted-in "Update now" then runs `os.replace` over the **other application's** file.
  - The code follows INV-7 to the letter, so the contract's detection rule is the weak side (spec-side gap). Not executed.
  - Fix: also require `getattr(sys, "frozen", False)` and that `sys.executable` resolves under `$APPDIR`.

- **[dim 2]** `_selftest.py:337-352` — `CHECK_NAMES = ("qt", "qtnetwork", …)` — **The self-test has no TLS check, though app startup imports TLS.**
  - The import chain is `app.py` → `main_window.py:102` → `update.py:27` → `update_fetch.py:16,22` (`import ssl`, `import certifi` at module level).
  - A bundle missing `_ssl`/libssl dies at launch while the self-test prints OK. That is the FIBR-0259 shape the comment at `:333-336` warns about.
  - A bundle missing certifi's `cacert.pem` fails every update check silently: the `FileNotFoundError` from `_ssl_context` (`update_fetch.py:48`) is swallowed under INV-11. That is the v0.1.0 no-prompt bug that `_ssl_context`'s own docstring describes.
  - Fix: add a `tls` check that runs `ssl.create_default_context(cafile=certifi.where())`.

## Low / Info
- **[dim 16]** `update_fetch.py:105-108`, `:171-186`: `timeout` is a per-read socket timeout. A server that trickles bytes holds the check or download indefinitely, up to 200 MiB. The docstring at `:7-8` says a server "cannot … hang". Fix: add a wall-clock deadline to the read loop.
- **[dim 16]** `update_fetch.py:147` (`return int(text) …`) and `update_dialog.py:131` (`self._busy.setRange(0, total)`): the advertised `Content-Length` is never bounded. A value above 2³¹ should make `setRange` overflow inside a slot (not executed). Fix: treat `total > max_bytes` as an immediate error.
- **[dim 16]** `_update_worker.py:51-61`: `DownloadWorker.run` never checks `isInterruptionRequested()`.
  - At shutdown, `main_window.py:1982-1992` blocks the worker's signals and detaches it, so the download keeps running and its `ready` signal is never delivered.
  - The verified `finbreak-update-*` temp is then left beside the binary, against Deliverable 13 ("a dropped `ready` unlinks").
  - Fix: abort from the progress callback when interrupted, and unlink in the worker.
- **[dim 2]** `update_installer.py:92-95` (`while kill -0 {pid}`, with `pid = os.getpid()` at `:292`): in a onefile build that PID is the Python child, not the bootloader parent that cleans up `_MEI` and holds the FUSE mount.
  - So the docstring's "FUSE mount is unmounted and … `_MEI` … cleaned" is not guaranteed. FIBR-0131 D3 makes exactly this point for Windows.
  - It may be harmless now that `PYINSTALLER_RESET_ENVIRONMENT` is set (not executed). Fix: also wait on `os.getppid()` when frozen, or correct the docstring.
- **[dim 8]** `app.py:56-64`: the hook calls `QMessageBox.critical(None, …)` from whatever thread runs `sys.excepthook`. I believe PySide6 sends an exception that escapes a `QThread.run` override through `sys.excepthook` on the worker thread, which would build a widget off the GUI thread. `suppress(Exception)` cannot catch a Qt fatal error. Not executed. Fix: marshal to the GUI thread when `QThread.currentThread() is not app.thread()`.
- **[dim 7]** `update_installer.py:282` and `:387` (`on_before_exec()`): an exception from the wipe callback after `os.replace` escapes as a non-`UpdateError`. `main_window.py:1787` catches only `UpdateError`, which leaves a live GUI with the binary already swapped and the key possibly half-wiped. Fix: `try/finally` that still reaches `os._exit`.
- **[dim 2, the documents are wrong]**
  - FIBR-0054 D8 (lines 245-246) and Deliverable 10 still describe `Popen([appimage_path], … stdio=DEVNULL)`. The code uses a `/bin/sh` waiter and a log file.
  - FIBR-0131 D3 asks for `CREATE_NO_WINDOW`, which the code omits (`update_installer.py:364-366`). The omission is harmless: Windows ignores that flag together with `DETACHED_PROCESS`.
- **[dim 3]** `__main__.py:51-54`: a fixed filename in the temp dir, opened with `"w"`, follows a symlink on a shared `/tmp`. It is reached only when `sys.stdout is None`, which normally means Windows with a per-user `%TEMP%`.
- **Other dimensions:**
  - Dim 4: nothing found.
  - Dim 5: the 200 MiB in-memory read plus a second copy on disk stay within the cap, so no finding.
  - Dim 9: the swap is `mkstemp` (0600) then `os.replace` in the same directory; nothing found.
  - Dim 10: the relaunch log and debug logs carry paths, a PID and exception text, and no secrets.
  - Dim 11: nothing beyond the items above.
  - Dim 12: N/A.
  - Dim 13: `tr()` literals with `.format`, notes shown verbatim, layout direction taken from `QLocale`; nothing found.
  - Dim 15: only a User-Agent header, behind an opt-in or an explicit click; nothing found.
  - Dim 17: the two INI keys; nothing found.

## Covered by spec and looks correct
- **Version and asset rules:** the D13 grammar (`isascii` + `isdigit`, zero-padded compare); the D14 / FIBR-0131 INV-2 installer-driven asset picker (exactly one asset plus an exact `.sig`).
- **Check gates:** the no-installer short-circuit comes before the opt-in gate; INV-1 `is_enabled`.
- **Network:** `https://` is enforced on the first URL and on every redirect; TLS uses `create_default_context` with hostname checking; the byte caps and 30 s timeout match INV-10; a Content-Length shortfall raises instead of reaching the signature check.
- **Download:** verification runs over the exact bytes read back, and those same bytes are re-written for the swap. Every failure path deletes the temps.
- **Linux install:** chmod → replace → wipe → spawn → `_exit`. A failure before the replace leaves the key intact.
- **Windows install:** spawn → wipe → exit, and a spawn failure is non-destructive. PowerShell paths are single-quote escaped; the `/bin/sh` path is passed as `"$1"`; both relaunch environments set the reset flag.
- **Dialog:** no `exec()`, link-opening off.
- **Self-test:** the sentinel and first-failure logic; `__main__`'s offscreen default and its fallback when there is no console.

## Open questions
- I arrived holding project context (listed at the top); the brief asked for this to be named.
- I did not open FIBR-0155, 0159, 0004, 0015 or 0051, and FIBR-0003 only through a grep. Only `_selftest.py`'s own stated goal backs the self-test finding.
- I did not assess INV-13 (the signed `SHA256SUMS`): it is enforced in the release scripts, which are outside this lane's files.
- Whether the AppImage wraps a onefile or a onedir build decides whether the `getpid` waiter finding is real.
- Whether the shipped PySide6 version sends `QThread.run` exceptions to `sys.excepthook` decides the excepthook finding.

## 3 items to fix first
1. **The inherited `$APPIMAGE`.** It is the only finding that can overwrite a file belonging to another application, and the fix is two extra checks in `detect_installer`.
2. **The signature binds bytes, not version or platform.** It allows a downgrade or a cross-platform brick by exactly the attacker security-model § 2 names, and it defeats the updater's one security gate.
3. **The busy dialog can be dismissed with Esc.** Pressing Esc is an ordinary action, and it currently leads to an unannounced swap, relaunch and key wipe.

The TLS self-test leg and wiring up `is_update_supported()` are each a few lines and worth doing alongside these.