# tests/features/auto_update — FIBR-0054 + FIBR-0131 optional in-app auto-update

Conformance tests for [`docs/specs/FIBR-0054.md`](../../../docs/specs/FIBR-0054.md)
(the updater) and [`docs/specs/FIBR-0131.md`](../../../docs/specs/FIBR-0131.md)
(the Windows plug). An **opt-in, off-by-default** updater: on a newer, signed,
non-skipped release it offers **Later / Skip this version / Update now**; **Update
now** downloads → Ed25519-verifies → installs → relaunches. Install is
platform-specific behind the `Installer` seam: Linux swaps `$APPIMAGE` in place
(`os.replace`); Windows can't overwrite its locked `.exe`, so a detached PowerShell
helper swaps it **out of process** after finbreak exits. The check is the app's
single deliberate network egress, confined to `services/update_fetch.py`.

All tests use `tmp_path` + synthetic bytes and an **injected fake fetcher** — no
network (`testing.md § 6`), no real signing key (a throwaway test key is
monkeypatched in per INV-4/14, `testing.md § 3.5`).

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-1 | Opt-in: `check_for_update()` returns `None` and **never calls the fetcher** when `check_for_updates` is absent / `"false"` / malformed; an explicitly-enabled service *does* call it. |
| INV-2 | The check needs no vault — it runs against a locked `AuthService` and touches no vault-connection accessor (it reads only the plaintext INI + `__version__` + the injected fetcher). |
| INV-3 | An `UpdateInfo` is returned **only** for a strictly-greater, well-formed, non-skipped tag with both AppImage + `.sig` assets present. Newer→offer; equal→None; older→None; malformed tag `"v1.2-rc1"`/`"latest"`→None; `"0.1"` vs `"0.1.0"`→equal (no offer); `"1_0.0"`→None (isdigit guard); missing `.sig`→None; skipped==latest→None. |
| INV-4 | `download_and_verify` installs **only** an Ed25519-signed download: a good signature (test key monkeypatched in) → returns the temp path; a one-byte tamper of the blob **or** the signature → `UpdateVerificationError` and the temp file is gone. |
| INV-5 | The temp stages in `installer.target_path().parent` (same fs as `$APPIMAGE`); after success the target holds the new bytes + is executable; a pre-`os.replace` raise leaves the original `$APPIMAGE` byte-for-byte intact. |
| INV-6 | The key-wipe callback runs **after** `os.replace` and **before** the relaunch on success; a failing `os.replace` leaves the wipe **uncalled**. The relaunch spawns the swapped `$APPIMAGE` **detached** (`subprocess.Popen`, `start_new_session=True`) with `PYINSTALLER_RESET_ENVIRONMENT=1` + the stale `APPDIR`/`APPIMAGE`/`ARGV0` dropped, then `os._exit(0)` — an in-place `os.execv` can't replace the running image's busy FUSE mount and the onefile bootloader mistakes it for a worker subprocess (the 0.1.2→0.1.3 "closed but didn't reopen" bug). |
| INV-7 | Off an AppImage the feature is inert: `$APPIMAGE` unset → `detect_installer() is None`, `is_update_supported()` is `False`; the Settings checkbox is disabled + tooltipped. |
| INV-8 | Skip persists, Later does not: skip `0.1.1` → a re-check advertising `0.1.1` returns `None`; advertising `0.1.2` is offered. Both keys live in `window.ini`, never the vault. |
| INV-9 | Prompt + progress are non-blocking + auto-lock-safe: `ui/update_dialog.py` has no `.exec(`; a `qtbot` prompt is destroyed by `_lock`; a `DownloadWorker.ready` after the prompt was torn down does **not** call `installer.apply` (and unlinks the temp). |
| INV-10 | Resource-bounded: `update_fetch.download` aborts an over-cap stream (temp deleted, `ValueError`); the API read is capped too. |
| INV-11 | Any check/network failure is silent + safe: an injected fetcher that raises → `check_for_update()` returns `None` without propagating; a verify failure on **Update now** raises `UpdateVerificationError` (surfaced, not swallowed) with the version unchanged. |
| INV-12 | Network code confined to one allowlisted module: `_network_offenders` flags a planted `import socket` at `services/update_fetch.py`, a planted `import urllib` at another path, and a planted dynamic `import_module("socket")` — but **not** a `urllib` import at `services/update_fetch.py`. |
| INV-13 | The new dialog is RTL-safe: covered by the existing `test_INV10_no_fixed_geometry_in_new_ui` source-scan (globs `ui/*.py`); `tr()`-wrapping is a review-checklist item per `coding.md § 5.2`. |
| INV-14 | The signature round-trips: a fixture blob signed with a test key verifies against that key; a repo-scan asserts no private-key material (`*.key` / a PEM `PRIVATE KEY` marker) is tracked. |
| D13 | Version grammar: leading `v`/`V` stripped; every segment `isascii() and isdigit()`; comparison zero-pads the shorter tuple. |
| D14 | Asset predicate: the picker takes the suffix as a parameter; the asset ends in it; its signature is that name + `.sig`; absent-or-duplicate either → `None`. |

The FIBR-0054 rows above number INV-1…14; the **FIBR-0131** rows below are
prefixed so the two specs' invariants don't collide (see `docs/specs/FIBR-0131.md`).

| INV | What it pins (FIBR-0131 — Windows in-app auto-update) |
|-----|--------------|
| FIBR-0131 INV-1 | Platform detection: `win32 + sys.frozen` → `WindowsInstaller(sys.executable)`; `win32` not-frozen → `None`; non-Windows unaffected. Off an installer the feature is inert (Settings disabled; Help→Check reports "not available"). |
| FIBR-0131 INV-2 | Installer-driven asset-picker: `_select_assets(assets, suffix)` picks the `.exe` under `WindowsInstaller.asset_suffix()` and the `.AppImage` under `AppImageInstaller`'s, each + `.sig` (a release carrying both picks per-platform); `check_for_update` short-circuits to `None` with **zero** fetcher calls when there's no installer. |
| FIBR-0131 INV-3 | The Windows swap is out-of-process, by **image path**: `_windows_relaunch_command` polls `Get-Process … $_.Path -eq $exe` (no `-Id`/PID), aborts (`Remove-Item` the temp, no relaunch) if the image never frees, else retries `Move-Item` then `Start-Process`; the argv[0] is an absolute `powershell.exe` (not bare `powershell`); paths single-quote-escaped. |
| FIBR-0131 INV-4 | `WindowsInstaller.apply` wipes the key **before** spawning the detached helper and `os._exit`s — no in-process file move; the Windows-only `creationflags` are `getattr`-guarded so `apply` loads + runs on the Linux gate. |
| FIBR-0131 INV-5 | `_windows_relaunch_env` sets `PYINSTALLER_RESET_ENVIRONMENT=1` (+ passes unrelated vars through); no POSIX `LD_*` fixups. |
| FIBR-0131 INV-6 | `download_and_verify` stages the temp with the installer-derived extension (`.exe`), so a Windows download isn't a misnamed `*.AppImage`. |
| FIBR-0131 INV-7 | The `.exe` rides the same byte-agnostic Ed25519 gate (covered transitively by the FIBR-0054 tamper leg; the new coverage is the picker feeding `.exe` bytes through it). |

**Coverage honesty (INV-3/INV-4):** the Linux gate tests the **command/env
construction** and the `apply` **ordering** (spawn→wipe→exit; spawn-failure leaves
the key un-wiped) with a monkeypatched `Popen`/`os._exit`. The PowerShell helper's
**runtime execution** — the image-free poll, the abort branch, the `Move-Item`
retry, the temp `Remove-Item`, the relaunch — is **empirical-only on Windows** (a
manual two-cycle leg, § docs/specs/FIBR-0131.md "To verify empirically"), exactly
as the Linux `/bin/sh` relaunch legs are honest about being AppImage-runtime-only.

INV-13/INV-9 grep legs and the Settings/shell `qtbot` legs live in the Qt section
of `test_auto_update.py`; the pure service/installer/version/asset legs need no
`qtbot`.
