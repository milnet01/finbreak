"""FIBR-0095 — failed-unlock throttling. Enforces this suite's spec.md.

Three layers, tested bottom-up: the Qt-free pure core (schedule math + fail-safe
corners, INV-1..3), the ``QSettings`` adapter (persistence + defensive coercion,
INV-4/5/7), and the ``UnlockDialog`` wiring (entry gate + reset-on-success, INV-6).
The pure legs need no vault and no Qt; the adapter/UI legs ride the autouse
``window_ini`` fixture (conftest) that redirects ``window_settings_path`` to tmp.
"""

from __future__ import annotations

import configparser
import inspect
from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from finbreak.services.auth import AuthService
from finbreak.services.unlock_throttle import (
    BASE_DELAY_SECONDS,
    CAP_N,
    MAX_DELAY_SECONDS,
    ThrottleState,
    backoff_delay_seconds,
    remaining_lockout_seconds,
)
from finbreak.ui._unlock_throttle import UnlockThrottle

pytestmark = pytest.mark.features


# --------------------------------------------------------------------------- #
# INV-1 — the pure schedule
# --------------------------------------------------------------------------- #
def test_INV1_schedule_ramp_and_cap() -> None:
    assert backoff_delay_seconds(0) == 0.0
    assert backoff_delay_seconds(-5) == 0.0
    assert backoff_delay_seconds(1) == BASE_DELAY_SECONDS
    ramp = [backoff_delay_seconds(n) for n in range(1, 7)]
    assert ramp == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
    # n=6 is where 2**5=32 is already clamped to the 30 s cap (CAP_N).
    assert backoff_delay_seconds(CAP_N) == MAX_DELAY_SECONDS
    assert backoff_delay_seconds(50) == MAX_DELAY_SECONDS


def test_INV1_monotonic_and_never_exceeds_cap() -> None:
    delays = [backoff_delay_seconds(n) for n in range(0, 40)]
    assert delays == sorted(delays), "delay must be non-decreasing in n"
    assert max(delays) <= MAX_DELAY_SECONDS


def test_INV1_exponent_clamp_handles_tampered_huge_count() -> None:
    # An attacker-writable window.ini could carry a billion. Without the exponent
    # clamp, 2**(10**9 - 1) builds a ~300-million-digit int and hangs the app.
    # The clamp makes this return the cap *fast* (this test would otherwise never
    # complete).
    assert backoff_delay_seconds(10**9) == MAX_DELAY_SECONDS


# --------------------------------------------------------------------------- #
# INV-2 — remaining() boundary legs
# --------------------------------------------------------------------------- #
_LAST = datetime(2026, 7, 18, 12, 0, 0, tzinfo=UTC)  # n=3 → delay(3) == 4 s


def test_INV2_zero_when_no_failures() -> None:
    assert remaining_lockout_seconds(0, _LAST, _LAST) == 0.0
    assert remaining_lockout_seconds(-1, _LAST, _LAST) == 0.0


def test_INV2_just_under_delay_returns_positive_remainder() -> None:
    now = _LAST + timedelta(seconds=3.9)
    remaining = remaining_lockout_seconds(3, _LAST, now)
    assert remaining == pytest.approx(0.1)


def test_INV2_at_and_just_over_delay_returns_zero() -> None:
    assert remaining_lockout_seconds(3, _LAST, _LAST + timedelta(seconds=4)) == 0.0
    assert remaining_lockout_seconds(3, _LAST, _LAST + timedelta(seconds=4.1)) == 0.0


# --------------------------------------------------------------------------- #
# INV-3 — fail-safe corners (err toward more delay, never less)
# --------------------------------------------------------------------------- #
def test_INV3_missing_last_fail_owes_full_delay() -> None:
    assert remaining_lockout_seconds(3, None, _LAST) == backoff_delay_seconds(3)


def test_INV3_future_last_fail_owes_more_than_full_delay() -> None:
    now = _LAST - timedelta(seconds=5)  # clock moved back / tampered stamp
    remaining = remaining_lockout_seconds(3, _LAST, now)
    assert remaining > backoff_delay_seconds(3)
    assert remaining == pytest.approx(9.0)  # 4 s delay + 5 s of negative elapsed


def test_ThrottleState_is_frozen() -> None:
    state = ThrottleState(fail_count=2, last_fail=_LAST)
    with pytest.raises(FrozenInstanceError):
        state.fail_count = 9  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# INV-4 — persistence + defensive coercion (adapter)
# --------------------------------------------------------------------------- #
def test_INV4_record_failure_increments_and_stamps_persisted(window_ini: Path) -> None:
    now = datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC)
    throttle = UnlockThrottle()
    assert throttle.load() == ThrottleState(fail_count=0, last_fail=None)

    throttle.record_failure(now)
    later = now + timedelta(seconds=1)
    throttle.record_failure(later)

    state = throttle.load()
    assert state.fail_count == 2
    assert state.last_fail == later


def test_INV4_fresh_adapter_sees_prior_state_after_restart(window_ini: Path) -> None:
    now = datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC)
    UnlockThrottle().record_failure(now)

    # A brand-new adapter (a relaunched app) reads the same window.ini file.
    reopened = UnlockThrottle().load()
    assert reopened == ThrottleState(fail_count=1, last_fail=now)


def test_INV4_load_defaults_on_missing_and_malformed(window_ini: Path) -> None:
    # Nothing written yet → clean defaults.
    assert UnlockThrottle().load() == ThrottleState(fail_count=0, last_fail=None)

    # Seed a non-integer count and a truncated timestamp directly into the INI —
    # the shape a partial/interrupted write leaves behind.
    window_ini.write_text(
        "[unlock]\nfail_count=not-a-number\nlast_fail=2026-07-18T09:00\x00garbage\n"
    )
    state = UnlockThrottle().load()
    assert state.fail_count == 0, "non-integer count coerces to 0 (fail-safe)"
    assert state.last_fail is None, "malformed timestamp coerces to None (fail-safe)"


def test_INV3_naive_last_fail_treated_as_malformed(window_ini: Path) -> None:
    # A partial write that truncates only the trailing "+00:00" offset leaves a
    # fully *parseable* but offset-NAIVE ISO string. datetime.fromisoformat
    # accepts it without raising, so load() must still reject it as tz-naive —
    # otherwise remaining()'s `now - last_fail` (aware minus naive) raises
    # TypeError and crashes the unlock dialog on every launch, which would deny
    # the legitimate owner access (INV-3 fail-safe / FIBR-0031 never-lock-out).
    window_ini.write_text("[unlock]\nfail_count=3\nlast_fail=2026-07-18T09:00:00\n")
    assert UnlockThrottle().load().last_fail is None, (
        "an offset-naive timestamp is treated as malformed → None"
    )
    # The gate must compute the full owed delay, never raise, on that state.
    now = datetime(2026, 7, 18, 9, 0, 30, tzinfo=UTC)
    assert UnlockThrottle().remaining(now) == backoff_delay_seconds(3)


# --------------------------------------------------------------------------- #
# INV-5 — reset() on a successful unlock
# --------------------------------------------------------------------------- #
def test_INV5_reset_clears_count_and_remaining(window_ini: Path) -> None:
    now = datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC)
    throttle = UnlockThrottle()
    throttle.record_failure(now)
    throttle.record_failure(now)
    assert throttle.remaining(now) > 0

    throttle.reset()
    assert throttle.load().fail_count == 0
    assert throttle.remaining(now) == 0.0
    # A fresh adapter agrees the keys are gone (no lone survivor).
    assert UnlockThrottle().load() == ThrottleState(fail_count=0, last_fail=None)


# --------------------------------------------------------------------------- #
# INV-7 — writes only the two window.ini keys; no vault, no secret
# --------------------------------------------------------------------------- #
def test_INV7_writes_only_the_two_ini_keys(window_ini: Path) -> None:
    UnlockThrottle().record_failure(datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC))

    parser = configparser.ConfigParser()
    parser.read(window_ini)
    assert parser.sections() == ["unlock"]
    assert set(parser["unlock"].keys()) == {"fail_count", "last_fail"}
    # An int and an ISO string — nothing else.
    assert int(parser["unlock"]["fail_count"]) == 1
    assert datetime.fromisoformat(parser["unlock"]["last_fail"]).tzinfo is not None


def test_INV7_adapter_never_touches_vault_or_secret() -> None:
    # Clause a (nothing lands in the vault): the adapter's whole write path references
    # only the plaintext window settings — no vault/connection/PRAGMA/derive_key. Grep
    # the source the way security-model INV-9 (log-cleanliness) is verified.
    src = inspect.getsource(UnlockThrottle).lower()
    for token in ("vault", "connection", "execute", "pragma", "derive_key"):
        assert token not in src, f"throttle adapter must not reference {token!r}"

    # Clause b (no password/key material can reach either store) is structural: the
    # two writing methods take no secret parameter, so none can be persisted.
    assert list(inspect.signature(UnlockThrottle.record_failure).parameters) == [
        "self",
        "now",
    ]
    assert list(inspect.signature(UnlockThrottle.reset).parameters) == ["self"]


# --------------------------------------------------------------------------- #
# INV-6 — UnlockDialog wiring (qtbot)
# --------------------------------------------------------------------------- #
@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def test_INV6_worker_not_spawned_during_lockout(qtbot, service: AuthService) -> None:
    from finbreak.ui.unlock import UnlockDialog

    # Owe a delay: three recent failures → delay(3) == 4 s, elapsed ~0 → remaining > 0.
    now = datetime.now(UTC)
    seed = UnlockThrottle()
    for _ in range(3):
        seed.record_failure(now)

    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    dialog._password.setText("whatever")
    dialog._on_unlock()

    assert dialog._worker is None, "the derive worker must NOT spawn while locked out"
    assert dialog._error.text() != "", "a countdown message is shown"
    assert "try again" in dialog._error.text().lower()


def test_INV6_success_resets_the_counter(
    qtbot, service: AuthService, monkeypatch
) -> None:
    from finbreak.ui.unlock import UnlockDialog

    UnlockThrottle().record_failure(datetime.now(UTC))
    assert UnlockThrottle().load().fail_count == 1

    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    # Skip the real Argon2 worker: a stub complete_unlock that "succeeds".
    monkeypatch.setattr(service, "complete_unlock", lambda _raw: True)
    unlocked: list[int] = []
    dialog.unlocked.connect(lambda: unlocked.append(1))

    dialog._on_derived(b"\x00" * 32)

    assert unlocked == [1], "unlocked emitted on success"
    assert UnlockThrottle().load().fail_count == 0, "a correct password clears it"


def test_INV6_failure_records_and_starts_countdown(qtbot, service: AuthService) -> None:
    from finbreak.ui.unlock import UnlockDialog

    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    failed: list[int] = []
    dialog.unlock_failed.connect(lambda: failed.append(1))

    dialog._show_failure()

    assert failed == [1], "unlock_failed emitted"
    assert UnlockThrottle().load().fail_count == 1, "the failure was recorded"
    assert "try again" in dialog._error.text().lower(), "countdown message shown"
