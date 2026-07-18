"""Failed-unlock backoff — the Qt-free pure core (FIBR-0095).

After a wrong master password in the interactive unlock dialog, the next attempt
is delayed on a capped exponential schedule (1s → 2s → 4s … → 30s). This module
holds the schedule math and the wall-clock "how much longer must I wait?" gate as
pure functions plus a frozen :class:`ThrottleState` — no Qt, no I/O — so they are
trivially unit-testable (mirroring the project's ``detect_recurring`` pure-core
pattern). The ``QSettings`` persistence lives in :mod:`finbreak.ui._unlock_throttle`.

This is **soft friction** against interactive guessing through the app UI, not a
security boundary: the count lives in the plaintext ``window.ini``, which the
threat model already concedes is attacker-writable (security-model INV-2 / Argon2id
owns the real, offline-cracking defence). See ``docs/specs/FIBR-0095.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# The schedule constants are fixed — no user-facing knob (spec D7).
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0
# The smallest n at which the cap is already reached (2**(6-1) = 32 → 30). The
# exponent is clamped at CAP_N *before* the power so a tampered huge fail_count
# from the plaintext window.ini cannot trigger an unbounded-integer computation
# (spec "The schedule" — this clamp is load-bearing).
CAP_N = 6


@dataclass(frozen=True)
class ThrottleState:
    """The two persisted facts: the consecutive-failure count and the wall-clock
    time of the most recent failure (``None`` when unknown / not yet recorded)."""

    fail_count: int
    last_fail: datetime | None


def backoff_delay_seconds(n: int) -> float:
    """The delay owed before the next attempt is accepted, as a function of the
    consecutive-failure count ``n`` (the count *including* the failure just
    recorded): ``0`` for ``n <= 0``, else ``min(BASE * 2**(min(n, CAP_N) - 1), CAP)``.
    Clamping the exponent at ``CAP_N`` keeps a tampered huge ``n`` from building a
    giant power (spec INV-1)."""
    if n <= 0:
        return 0.0
    exponent = min(n, CAP_N) - 1
    return min(BASE_DELAY_SECONDS * 2**exponent, MAX_DELAY_SECONDS)


def remaining_lockout_seconds(
    fail_count: int, last_fail: datetime | None, now: datetime
) -> float:
    """How much of :func:`backoff_delay_seconds` is still owed at ``now``.

    ``0`` when ``fail_count <= 0`` or the full delay has already elapsed. Fail-safe
    corners (spec INV-3): a missing ``last_fail`` with a positive count yields the
    **full** delay (a partial/corrupt write is treated as if the failure just
    happened); a ``last_fail`` in the future (clock moved back / tampered stamp)
    makes ``elapsed`` negative and so owes a *longer* wait — never a shorter one."""
    if fail_count <= 0:
        return 0.0
    delay = backoff_delay_seconds(fail_count)
    if last_fail is None:
        return delay
    elapsed = (now - last_fail).total_seconds()
    return max(0.0, delay - elapsed)
