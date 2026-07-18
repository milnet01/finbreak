"""``QSettings`` adapter for the failed-unlock backoff state (FIBR-0095).

Persists the two throttle facts in the plaintext ``window.ini`` — the same
pre-unlock store ``ui/_table_state.py`` / ``theme.py`` use — under
``unlock/fail_count`` (int) and ``unlock/last_fail`` (ISO-8601 UTC string).
Persisting (rather than an in-memory counter) is what stops the trivial
"just close and reopen the app" bypass: a relaunch reads the same file and still
owes the remaining delay.

Values are coerced **defensively in our own code** (not by trusting QSettings'
type-coercion): a missing/non-integer ``fail_count`` → ``0``, and a missing or
malformed ``last_fail`` (e.g. truncated by an interrupted write) → ``None``. Both
default fail-safe — the pure core turns a positive count with an unknown
``last_fail`` into the full delay. ``.sync()`` after every write so a same-process
read-back sees it (matching the existing ``ui/_table_state.py`` usage).
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSettings

from finbreak import paths
from finbreak.services.unlock_throttle import ThrottleState, remaining_lockout_seconds

_FAIL_COUNT_KEY = "unlock/fail_count"
_LAST_FAIL_KEY = "unlock/last_fail"


class UnlockThrottle:
    """Reads/writes the backoff state in ``window.ini``. Stateless beyond the file:
    every method opens a fresh ``QSettings`` on the current
    ``paths.window_settings_path()`` (monkeypatched in tests), so a new instance —
    i.e. a relaunched app — always sees the latest persisted state."""

    @staticmethod
    def _settings() -> QSettings:
        return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)

    def load(self) -> ThrottleState:
        settings = self._settings()
        try:
            fail_count = int(settings.value(_FAIL_COUNT_KEY))
        except (TypeError, ValueError):
            fail_count = 0  # missing or non-integer → fail-safe 0
        try:
            last_fail: datetime | None = datetime.fromisoformat(
                settings.value(_LAST_FAIL_KEY)
            )
        except (TypeError, ValueError):
            last_fail = None  # missing or malformed → fail-safe None (full delay)
        return ThrottleState(fail_count=fail_count, last_fail=last_fail)

    def remaining(self, now: datetime) -> float:
        """Seconds still owed before the next attempt is accepted, recomputed from
        persisted wall-clock state (the authoritative gate — spec D4)."""
        state = self.load()
        return remaining_lockout_seconds(state.fail_count, state.last_fail, now)

    def record_failure(self, now: datetime) -> None:
        """Increment ``fail_count`` by one and stamp ``last_fail = now``."""
        state = self.load()
        settings = self._settings()
        settings.setValue(_FAIL_COUNT_KEY, state.fail_count + 1)
        settings.setValue(_LAST_FAIL_KEY, now.isoformat())
        settings.sync()

    def reset(self) -> None:
        """Clear both keys — called on a successful unlock, so a correct password
        never leaves the owner locked out (spec INV-5)."""
        settings = self._settings()
        settings.remove(_FAIL_COUNT_KEY)
        settings.remove(_LAST_FAIL_KEY)
        settings.sync()
