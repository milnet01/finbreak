"""FIBR-0019 INV-9/INV-10 — the recovery unlock route. Enforces spec.md.

Needs ``qtbot`` (§ 7): both invariants are about ``UnlockDialog``'s second
route. § 4.6 fixes that route's BEHAVIOUR and not its attribute names, so the
seams this module binds to are recorded in spec.md § Seams; ``require_seam``
reports a miss as a missing seam rather than as wrong behaviour.

Why this exists: a user arriving by the recovery route has, by construction, no
working password (D6), and a recovery route outside the shared backoff would be
a way around FIBR-0095's throttle -- the kind of thing a later refactor quietly
drops.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    code_secret,
    create_vault,
    forge_wrong_code_with_a_valid_check_symbol,
    keep_recovery_key,
    opens_with,
    read_v2_sidecar,
    require_seam,
    unwrap_slot,
)

from finbreak.errors import KeyUnwrapError
from finbreak.keywrap import SLOT_MASTER
from finbreak.services.auth import AuthService
from finbreak.ui._unlock_throttle import UnlockThrottle

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def _dialog(qtbot: Any, service: AuthService) -> Any:
    from finbreak.ui.unlock import UnlockDialog

    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    return dialog


def _recovery_seams(dialog: Any) -> tuple[Any, Any, Any]:
    field = require_seam(
        dialog,
        "_recovery_code",
        "§ 4.6: UnlockDialog gains a second route -- 'I've forgotten my "
        "password' -- which takes the recovery code as its input.",
    )
    submit = require_seam(
        dialog,
        "_on_recovery_unlock",
        "§ 4.6: the recovery route's submit handler, the counterpart of "
        "_on_unlock, and the place the shared throttle must be consulted.",
    )
    pending = require_seam(
        dialog,
        "recovery_unlocked",
        "§ 4.6 step 4 / D6: a recovery unlock must NOT reach the main window. "
        "It needs a signal distinct from `unlocked` so the shell routes to the "
        "forced new-password step instead.",
    )
    return field, submit, pending


# --------------------------------------------------------------------------- #
# INV-9 — a recovery unlock leaves a working master password behind
# --------------------------------------------------------------------------- #
def test_recovery_unlock_forces_a_new_master_password(
    qtbot: Any, paths: tuple[Path, Path], service: AuthService
) -> None:
    vault_path, sidecar_path = paths

    dialog = _dialog(qtbot, service)
    field, submit, pending = _recovery_seams(dialog)

    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    unlocked: list[int] = []
    awaiting_password: list[int] = []
    dialog.unlocked.connect(lambda: unlocked.append(1))
    pending.connect(lambda: awaiting_password.append(1))

    field.setText(code)
    submit()

    qtbot.waitUntil(lambda: bool(awaiting_password), timeout=10_000)

    assert unlocked == [], (
        "INV-9: the recovery route emitted `unlocked`, so the shell shows the "
        "main window. A user arriving this way has, by construction, no working "
        "password -- leaving them unlocked with no way back in tomorrow "
        "reproduces the problem one day later (D6).\n"
        "  expected: `unlocked` not emitted until a new master password is set\n"
        f"  actual:   emitted {len(unlocked)} time(s)"
    )

    # The forced reset. The DEK does not change -- this re-derives KEK-master
    # against a FRESH salt and re-wraps the same 32 bytes (§ 4.6 step 4).
    service.set_master_password(bytearray(NEW_MASTER_PASSWORD))
    service.lock()

    data = read_v2_sidecar(sidecar_path)
    reopened = bytes(unwrap_slot(NEW_MASTER_PASSWORD, data, SLOT_MASTER))
    assert opens_with(vault_path, sidecar_path, bytearray(reopened)), (
        "INV-9: the new master password does not open the vault, so the "
        "recovery route left the user with no working credential at all.\n"
        "  expected: the new password unwraps slots.master and opens vault.db\n"
        "  actual:   SQLCipher refused the resulting key"
    )

    with pytest.raises(KeyUnwrapError):
        unwrap_slot(MASTER_PASSWORD, data, SLOT_MASTER)


# --------------------------------------------------------------------------- #
# INV-10 — the recovery route shares the password route's backoff counter
# --------------------------------------------------------------------------- #
def test_recovery_attempts_share_the_password_backoff(
    qtbot: Any, paths: tuple[Path, Path], service: AuthService
) -> None:
    _vault_path, sidecar_path = paths

    dialog = _dialog(qtbot, service)
    field, submit, _pending = _recovery_seams(dialog)

    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    # Leg 1 -- the password allowance is already exhausted. Three recent
    # failures owe delay(3) == 4 s, so a recovery attempt must be refused before
    # anything is derived. A recovery route that skipped the gate would be a way
    # around FIBR-0095 entirely.
    now = datetime.now(UTC)
    seed = UnlockThrottle()
    for _ in range(3):
        seed.record_failure(now)

    field.setText(code)
    submit()

    assert dialog._worker is None, (
        "INV-10: the recovery route spawned a derive worker while the shared "
        "backoff still owed a delay.\n"
        "  expected: no worker, and a countdown message shown\n"
        f"  actual:   worker={dialog._worker!r}"
    )
    assert dialog._error.text().strip(), (
        "INV-10: the refusal must be visible.\n"
        "  expected: a non-empty countdown message\n"
        f"  actual:   {dialog._error.text()!r}"
    )

    # Leg 2, the reverse -- a FAILED recovery attempt advances the counter the
    # password route reads. Not an assertion about instance identity:
    # UnlockThrottle is stateless beyond window.ini and opens a fresh QSettings
    # per method, so two instances share the counter by construction and an
    # invariant written against identity would test nothing.
    UnlockThrottle().reset()
    assert UnlockThrottle().load().fail_count == 0, "precondition: counter cleared"

    forged = forge_wrong_code_with_a_valid_check_symbol(code)
    data = read_v2_sidecar(sidecar_path)
    with pytest.raises(KeyUnwrapError):
        unwrap_slot(code_secret(forged), data, "recovery")

    field.setText(forged)
    submit()

    qtbot.waitUntil(
        lambda: UnlockThrottle().load().fail_count >= 1,
        timeout=10_000,
    )
    assert UnlockThrottle().load().fail_count == 1, (
        "INV-10: a failed recovery attempt must be recorded as a failed unlock "
        "attempt, in the same counter the password route reads -- otherwise the "
        "recovery route is an unthrottled guessing oracle.\n"
        "  expected: fail_count == 1 after one failed recovery attempt\n"
        f"  actual:   {UnlockThrottle().load().fail_count}"
    )
