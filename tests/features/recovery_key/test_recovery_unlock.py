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


# --------------------------------------------------------------------------- #
# INV-20 -- FIBR-0313 M5: a failed recovery attempt must not tell the user to
# check their password
# --------------------------------------------------------------------------- #
def test_recovery_failure_message_does_not_mention_password(
    qtbot: Any,
    paths: tuple[Path, Path],
    service: AuthService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FIBR-0313 M5: ``_show_failure`` is shared between the password and
    recovery routes, and its no-countdown branch hardcodes "Check your password
    and try again" -- reachable when ``UnlockThrottle.remaining()`` reports 0
    immediately after ``record_failure``. On a working install that corner is
    NOT reachable: ``BASE_DELAY_SECONDS == 1.0`` makes ``remaining`` > 0 right
    after any recorded failure, so the countdown branch always fires first. It
    is reachable only if the persisted throttle state fails to survive (e.g. an
    unwritable ``window.ini``), which this test forces directly by
    monkeypatching ``remaining()`` rather than trying to break the file on
    disk.
    """
    _vault_path, sidecar_path = paths

    dialog = _dialog(qtbot, service)
    field, submit, _pending = _recovery_seams(dialog)

    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    monkeypatch.setattr(dialog._throttle, "remaining", lambda _now: 0.0)

    forged = forge_wrong_code_with_a_valid_check_symbol(code)
    data = read_v2_sidecar(sidecar_path)
    with pytest.raises(KeyUnwrapError):
        unwrap_slot(code_secret(forged), data, "recovery")

    field.setText(forged)
    submit()

    qtbot.waitUntil(lambda: dialog._error.text().strip() != "", timeout=10_000)

    message = dialog._error.text()
    assert "password" not in message.lower(), (
        "FIBR-0313 M5 (INV-20): _show_failure is shared between the password "
        "and recovery routes and its no-countdown branch hardcodes 'Check your "
        "password and try again'. A recovery-code user has, by construction, "
        "no working password to check (D6) -- and is reading this on a screen "
        "that also offers a destructive reset.\n"
        "  expected: no mention of 'password' after a failed RECOVERY attempt\n"
        f"  actual:   {message!r}"
    )


# --------------------------------------------------------------------------- #
# INV-20, second route -- the DERIVATION fails rather than the code being wrong
# --------------------------------------------------------------------------- #
def test_recovery_derivation_failure_message_does_not_mention_password(
    qtbot: Any,
    paths: tuple[Path, Path],
    service: AuthService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other way into INV-20's message, and the one a shared slot hides.

    ``_show_failure`` is reached twice on the recovery route: from
    ``_on_recovery_derived`` when the code is simply wrong, and from the
    worker's ``failed`` signal when the DERIVATION itself raises. The sibling
    test above covers the first only -- measured with ``mutation_probe``, which
    is how this gap was found: re-pointing the recovery worker's ``failed``
    connection back at the shared password slot left the suite green.

    The stub worker emits synchronously, so the message is set before
    ``submit()`` returns and there is no state to wait for.
    """
    from PySide6.QtCore import QObject, Signal

    from finbreak.ui import unlock as unlock_mod

    class _FailingWorker(QObject):
        done = Signal(bytes)
        failed = Signal(object)
        finished = Signal()

        def __init__(self, secret: bytearray, _params: Any, parent: Any = None):
            super().__init__(parent)
            # The dialog hands over a live buffer and the real worker owns
            # wiping it; do the same rather than leave key material behind.
            secret[:] = bytes(len(secret))

        def start(self) -> None:
            self.failed.emit(RuntimeError("the KDF could not run"))
            self.finished.emit()

    dialog = _dialog(qtbot, service)
    field, submit, _pending = _recovery_seams(dialog)

    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    # Force the no-countdown corner (see the sibling test), then make the
    # derivation itself fail rather than the code be wrong.
    monkeypatch.setattr(dialog._throttle, "remaining", lambda _now: 0.0)
    monkeypatch.setattr(unlock_mod, "DeriveWorker", _FailingWorker)

    field.setText(code)
    submit()

    message = dialog._error.text()
    assert message.strip(), (
        "precondition: the failed derivation must have produced a message at "
        "all, or the check below passes vacuously.\n"
        "  expected: a non-empty error label\n"
        f"  actual:   {message!r}"
    )
    assert "password" not in message.lower(), (
        "FIBR-0313 M5 (INV-20): the recovery worker's `failed` signal reaches "
        "_show_failure too, and routing it through the shared password slot "
        "tells a recovery-code user to check a password they do not have.\n"
        "  expected: no mention of 'password' when a recovery DERIVATION fails\n"
        f"  actual:   {message!r}"
    )


# --------------------------------------------------------------------------- #
# INV-25 -- FIBR-0313 M10: D5's regeneration offer after a recovery unlock
# --------------------------------------------------------------------------- #
def _wait_or_timeout(qtbot: Any, predicate: Any, *, timeout_ms: int) -> None:
    """Poll ``predicate``, swallowing the raw pytest-qt timeout so the
    caller's own assertion -- with expected and actual -- is what a run
    against the live defect reports, rather than a bare TimeoutError with
    only a line number (``test_settings_flows.py``'s
    ``_wait_for_clipboard_clear`` does the same)."""
    import pytestqt.exceptions

    try:
        qtbot.waitUntil(predicate, timeout=timeout_ms)
    except pytestqt.exceptions.TimeoutError:
        pass


def test_recovery_unlock_offers_recovery_code_regeneration(
    qtbot: Any, paths: tuple[Path, Path], service: AuthService
) -> None:
    """FIBR-0313 M10 -- D5 (spec.md line 139): "The UI offers regeneration
    after a recovery unlock for the user who thinks their copy was exposed;
    it does not impose it." No such prompt exists today:
    ``MainWindow._show_recovery_offer`` (called from the end of
    ``_enter_unlocked``) fires in exactly two cases -- a held
    ``_pending_recovery_code`` (first run) or
    ``_service.consume_migration_notice()`` (D7, a just-converted vault). A
    recovery unlock is neither, so ``_on_recovery_unlocked``'s chain into
    ``_enter_unlocked`` reaches the end of ``_show_recovery_offer`` and
    returns ``False`` every time.

    Drives a REAL ``MainWindow`` rather than a standalone ``UnlockDialog``,
    because D5's offer is wired (or, today, not wired) at the shell level --
    the same class the shell uses to launch it against Settings' Add/Replace
    already exists (``build_add_or_replace_offer``), so the missing piece is
    only the connection from a recovery unlock into it.
    """
    from finbreak.ui.main_window import MainWindow
    from finbreak.ui.recovery_key import NewMasterPasswordDialog, RecoveryCodeDialog

    _vault_path, sidecar_path = paths

    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    # A locked vault at construction routes MainWindow through _show_unlock()
    # itself (see the `else: self._show_unlock()` branch in __init__) -- no
    # need to call it by hand.
    window = MainWindow(service)
    qtbot.addWidget(window)

    dialog = window._dialog
    field, submit, _pending = _recovery_seams(dialog)

    field.setText(code)
    submit()

    _wait_or_timeout(
        qtbot,
        lambda: isinstance(window._dialog, NewMasterPasswordDialog),
        timeout_ms=10_000,
    )
    new_password_dialog = window._dialog
    assert isinstance(new_password_dialog, NewMasterPasswordDialog), (
        "precondition: D6's forced new-master-password step must be up "
        "before this test can drive past it -- if this fails, INV-9 is "
        "broken too and that is a different defect.\n"
        "  expected: NewMasterPasswordDialog in the shell's _dialog slot\n"
        f"  actual:   {dialog!r} unchanged "
        f"({type(window._dialog).__name__})"
    )

    # D6's forced reset -- the DEK does not change, only the master slot's wrap.
    new_password_dialog._password.setText(NEW_MASTER_PASSWORD.decode())
    new_password_dialog._confirm.setText(NEW_MASTER_PASSWORD.decode())
    new_password_dialog._on_submit()

    _wait_or_timeout(
        qtbot,
        lambda: (
            isinstance(window._dialog, RecoveryCodeDialog)
            and not window._dialog.isHidden()
        ),
        timeout_ms=5_000,
    )
    offer = window._dialog
    assert isinstance(offer, RecoveryCodeDialog) and not offer.isHidden(), (
        "FIBR-0313 M10 (D5, spec.md line 139): the UI must offer to replace "
        "the recovery code once a recovery unlock's forced new master "
        "password is set -- 'for the user who thinks their copy was "
        "exposed'. _show_recovery_offer only fires for a held first-run "
        "code or a just-converted vault, never for a recovery unlock, so no "
        "such offer appears and the workspace is reached directly.\n"
        "  expected: a visible RecoveryCodeDialog in the shell's _dialog "
        "slot, offering a new recovery code\n"
        f"  actual:   {type(offer).__name__ if offer is not None else None}"
        + (
            f" (isHidden={offer.isHidden()})"
            if isinstance(offer, RecoveryCodeDialog)
            else ""
        )
    )

    # Leg 3 -- D5's "it does not impose it": declining must leave the
    # EXISTING recovery code working, not merely stop a new one being written.
    offer.reject()

    data = read_v2_sidecar(sidecar_path)
    new_master_dek = bytes(unwrap_slot(NEW_MASTER_PASSWORD, data, SLOT_MASTER))
    original_code_dek = bytes(unwrap_slot(code_secret(code), data, "recovery"))
    outcome = "matches" if original_code_dek == new_master_dek else "does NOT match"
    assert original_code_dek == new_master_dek, (
        "FIBR-0313 M10 (D5): declining the regeneration offer must not "
        "disturb the recovery code the user already has -- the offer is "
        "declinable, and 'does not impose it' means the original code must "
        "still work afterwards.\n"
        "  expected: the ORIGINAL recovery code still unwraps slots.recovery "
        "to the same DEK the new master password unwraps slots.master to\n"
        f"  actual:   original-code DEK {outcome} the vault's real DEK"
    )

    # Leg 4 -- the offer is owed ONCE. The control test cannot reach this: it
    # builds a fresh window that never had a recovery unlock, so an offer left
    # permanently owed would go on firing on every ordinary unlock of THIS
    # window and no other test would notice. mutation_probe found exactly that
    # -- removing the consume-on-read left the suite green until this leg.
    service.lock()
    window._show_unlock()
    from finbreak.ui.unlock import UnlockDialog

    window._unlocked = False
    ordinary = window._dialog
    assert isinstance(ordinary, UnlockDialog), (
        "precondition: locking must put the shell back on the unlock screen "
        "before this leg can drive an ordinary unlock.\n"
        "  expected: UnlockDialog in the shell's _dialog slot\n"
        f"  actual:   {type(ordinary).__name__}"
    )
    ordinary._password.setText(NEW_MASTER_PASSWORD.decode())
    ordinary._on_unlock()
    _wait_or_timeout(qtbot, lambda: window._unlocked, timeout_ms=10_000)
    assert window._unlocked, (
        "precondition for the leg below: the ordinary unlock must actually "
        "have happened. Without this the next assertion passes vacuously -- a "
        "failed unlock leaves the UnlockDialog in the slot, which is also 'not "
        "a RecoveryCodeDialog'.\n"
        "  expected: window._unlocked is True\n"
        f"  actual:   {window._unlocked} ({type(window._dialog).__name__} in the slot)"
    )

    again = window._dialog
    assert not isinstance(again, RecoveryCodeDialog), (
        "FIBR-0313 M10 (D5): the regeneration offer is owed ONCE, by the "
        "recovery unlock that earned it. An ordinary unlock afterwards must "
        "not re-offer -- D5 offers regeneration to the user who thinks their "
        "copy was exposed, not at every login.\n"
        "  expected: no RecoveryCodeDialog after an ordinary password unlock\n"
        f"  actual:   {type(again).__name__}"
    )


def test_ordinary_unlock_does_not_offer_recovery_code_regeneration(
    qtbot: Any, paths: tuple[Path, Path], service: AuthService
) -> None:
    """The control leg for the test above. D5 ties the regeneration offer to
    a RECOVERY unlock specifically -- "for the user who thinks their copy
    was exposed" -- not to unlocking in general. An implementation that
    shows the offer after every unlock, recovery or not, would pass the
    recovery-route test and still be wrong, which is exactly the kind of
    defect a single-leg test cannot catch.
    """
    from finbreak.ui.main_window import MainWindow
    from finbreak.ui.recovery_key import RecoveryCodeDialog
    from finbreak.ui.unlock import UnlockDialog

    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    window = MainWindow(service)
    qtbot.addWidget(window)

    dialog = window._dialog
    assert isinstance(dialog, UnlockDialog), (
        "precondition: a locked vault must route MainWindow through the "
        "real UnlockDialog.\n"
        f"  expected: UnlockDialog\n  actual:   {type(dialog).__name__}"
    )
    dialog._password.setText(MASTER_PASSWORD.decode())
    dialog._on_unlock()

    _wait_or_timeout(qtbot, lambda: window._unlocked, timeout_ms=10_000)
    assert window._unlocked, (
        "precondition: the ordinary password route must actually unlock, "
        "or the leg below passes vacuously.\n"
        "  expected: window._unlocked is True after an ordinary unlock\n"
        f"  actual:   {window._unlocked}"
    )

    offer = window._dialog
    assert not isinstance(offer, RecoveryCodeDialog), (
        "FIBR-0313 M10 (D5): an ORDINARY password unlock must not be "
        "offered recovery-code regeneration -- D5 ties that offer to a "
        "RECOVERY unlock, for a user who just proved their password may be "
        "compromised (D6's forced reset), not to unlocking in general. An "
        "implementation that fires the offer on every unlock passes the "
        "recovery-route test and must fail this one.\n"
        "  expected: no RecoveryCodeDialog after an ordinary password unlock\n"
        f"  actual:   {type(offer).__name__ if offer is not None else None}"
    )


# --------------------------------------------------------------------------- #
# FIBR-0313 L8 — a check-symbol typo is not an unlock attempt
# --------------------------------------------------------------------------- #
def test_a_check_symbol_typo_does_not_emit_unlock_failed(
    qtbot: Any, paths: tuple[Path, Path], service: AuthService
) -> None:
    """``unlock_failed``'s comment claimed it fires on every failure branch,
    and the check-symbol branch returns without it. The COMMENT is what was
    wrong: the signal is the dialog's "that attempt failed" event, and § 4.6
    says a typo is not an attempt -- it is reported at once and deliberately
    not counted, because the check symbol carries no security weight.

    This leg is what stops the other repair being made later. Emitting here
    would hand any future consumer -- the comment names an attempt counter as
    the shape a slot would take -- a failure that never was one.
    """
    from finbreak.services.recovery_code import (
        CHECK_ALPHABET,
        PAYLOAD_SYMBOLS,
        check_symbol,
        format_code,
        normalise,
        verify_check_symbol,
    )

    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    payload = normalise(code)[:PAYLOAD_SYMBOLS]
    wrong = next(s for s in CHECK_ALPHABET if s != check_symbol(payload))
    mistyped = format_code(payload + wrong)
    assert not verify_check_symbol(normalise(mistyped)), (
        "precondition: the code must FAIL the local check, or this leg drives "
        "the unwrap instead of the branch it is about."
    )

    dialog = _dialog(qtbot, service)
    field, submit, _pending = _recovery_seams(dialog)

    fired: list[int] = []
    dialog.unlock_failed.connect(lambda: fired.append(1))

    field.setText(mistyped)
    submit()

    assert dialog._error.text().strip() != "", (
        "precondition: the typo branch must have reported something, or the "
        "silence below is the silence of a branch that never ran."
    )
    assert fired == [], (
        "§ 4.6: a check-symbol typo was reported as a failed unlock attempt. "
        "The check symbol proves a transcription slip, not a guess, and is "
        "not counted -- a consumer of unlock_failed must not see it.\n"
        "  expected: unlock_failed not emitted\n"
        f"  actual:   emitted {len(fired)} time(s)"
    )


def test_FIBR0328_password_and_recovery_fields_have_accessible_names(qtbot, service):
    """Every password-like field on the unlock and recovery path carries an
    accessible name (2026-08-31 audit, LOW/INFO).

    These five are the ones that had none. The rest of the app's password fields
    sit in a ``QFormLayout``, whose label Qt makes their buddy and therefore
    their accessible name; these are laid out directly, so a placeholder was all
    they had — and a placeholder disappears the moment the user types. A screen
    reader announced an unnamed box on the screens nobody gets past, and on the
    one that shows a recovery code exactly once (WCAG 1.3.1/3.3.2).
    """
    from finbreak.ui.recovery_key import NewMasterPasswordDialog, RecoveryCodeDialog

    create_vault(service)

    unlock = _dialog(qtbot, service)
    assert unlock._password.accessibleName() != "", "the master password field"
    assert unlock._recovery_code.accessibleName() != "", "the recovery-code field"

    shown = RecoveryCodeDialog("ABCD-EFGH-JKMN-PQRS")
    qtbot.addWidget(shown)
    assert shown._display.accessibleName() != "", (
        "the recovery code is displayed once and never again — a reader that "
        "cannot name it costs the user the code itself"
    )

    reset = NewMasterPasswordDialog(service)
    qtbot.addWidget(reset)
    assert reset._password.accessibleName() != "", "the new master password field"
    assert reset._confirm.accessibleName() != "", "the confirm field"
