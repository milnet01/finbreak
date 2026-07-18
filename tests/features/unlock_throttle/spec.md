# tests/features/unlock_throttle — FIBR-0095 failed-unlock throttling

Conformance tests for [`docs/specs/FIBR-0095.md`](../../../docs/specs/FIBR-0095.md).
After a wrong master password in the **interactive** unlock dialog, the next
attempt is delayed on a capped exponential schedule (1s → 2s → 4s … → 30s). The
attempt count + last-failure time live in the plaintext `window.ini` (readable
*before* the vault is unlocked) so an app restart does not reset the delay. Three
layers: a Qt-free pure core (`services/unlock_throttle.py`), a `QSettings` adapter
(`ui/_unlock_throttle.py`), and the `UnlockDialog` wiring (`ui/unlock.py`).

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-1 | `backoff_delay_seconds(n)` — `0` for `n<=0`; `1,2,4,8,16,30` for `n=1..6`; `30` (cap) for `n>=6`; monotonic non-decreasing; never exceeds `MAX_DELAY_SECONDS`. A tampered huge `n` (`10**9`) returns `30` **fast** — the exponent clamp (`min(n, CAP_N)`) runs *before* the power, so no unbounded-integer build (would otherwise hang). |
| INV-2 | `remaining_lockout_seconds` — `0` for `n<=0`; `0` when `elapsed >= delay(n)` (at + just-over the delay); `delay(n) - elapsed` clamped `>= 0` just-under the delay. |
| INV-3 | Fail-safe corners: missing `last_fail` (`None`) with `n>0` → full `delay(n)`; a `last_fail` in the future (`now < last_fail`) → result `> delay(n)` (longer wait, never shorter). |
| INV-4 | `record_failure(now)` increments `fail_count` by exactly 1 and stamps `last_fail=now`, persisted to `window.ini`; a **fresh** `UnlockThrottle` over the same file reads the same state (survives a "restart"). Defensive `load()` coercion: missing → `(0, None)`; non-integer `fail_count` → `0`; malformed `last_fail` → `None`. |
| INV-5 | `reset()` removes both keys; afterwards `load().fail_count == 0` and `remaining(now) == 0` (a correct password never leaves the owner locked out). |
| INV-6 | `UnlockDialog` refuses to spawn the derive worker while `remaining(now) > 0` — the gate is on entry (`_worker` stays `None`), a countdown message is shown, and a successful `_on_derived` calls `reset()`. |
| INV-7 | The throttle writes **only** the two `window.ini` keys (an int + an ISO string) and touches no vault/connection/secret — established by inspecting the adapter's write path (clause a: nothing lands in the vault; clause b: `record_failure(now)`/`reset()` take no secret, so none can reach either store — structural). |
