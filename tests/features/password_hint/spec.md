# tests/features/password_hint — FIBR-0029 Password hint shown before unlock

Conformance tests for [`docs/specs/FIBR-0029.md`](../../../docs/specs/FIBR-0029.md).
An optional, user-authored plaintext hint stored in `window.ini`: **set** from
Settings behind a current-password confirm, **enforced** never to be/contain the
password (NFC + casefold, unconditional containment), and **shown** on the unlock
screen behind a reveal-on-click "Show hint" button.

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-1 | Off by default: a fresh `window.ini` → `read_hint() == ""`; `UnlockDialog` shows no `unlock_show_hint` button. |
| INV-2 | `validate_hint` rejects a hint equal to / containing the password — NFC-normalized + casefolded, **unconditionally** (case bypass, substring, NFD normal-form copy, and a 3-char password embedded verbatim all raise); a safe hint passes. |
| INV-3 | `read_hint()` returns the stored hint pre-unlock, with no key (reads `window.ini`). |
| INV-4 | The Set-hint shell flow calls `verify_password`: a wrong password writes nothing (stored hint unchanged, dialog stays open); a correct password saves. |
| INV-5 | `AuthService.verify_password` — correct → True, wrong → False; a static source assertion that `hmac.compare_digest` (not `==`) is used; raises `VaultLockedError` when locked. |
| INV-6 | `validate_hint` rejects a 101-char hint; a 100-char hint passes. |
| INV-7 | Saving an empty/whitespace-only hint field clears the hint (`clear_hint()` → `read_hint() == ""`); the show-hint affordance disappears. |
| INV-8 | `verify_password` zeroes the KDF password `bytearray` it consumes (mirrors the `validate_first_run` wipe test). |
| INV-9 | Revealing the hint is display-only: it never mutates the password field or the throttle counters. |

Service-level legs (INV-2/3/5/6/7/8) run headless against
`services/password_hint` + `AuthService` + `ui/_password_hint`; the UI legs
(INV-1/4/9 + the reveal round-trip) drive `UnlockDialog` / `SettingsDialog` /
`MainWindow` via `qtbot`. Every vault lives under `tmp_path`; the `window.ini` is
redirected to tmp by the autouse `window_ini` fixture; no network, no real data.
