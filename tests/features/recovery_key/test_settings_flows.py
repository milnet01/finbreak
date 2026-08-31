"""FIBR-0019 § 4.7 — Add / Replace / Remove, driven from Settings.

The shell owns these three because the master-password gate and the re-wrap are
``AuthService`` work, and Settings holding a reference to either would put key
material in a preferences dialog. What the shell owes in return is the
convention every other Settings-launched flow follows: the single ``_dialog``
slot holds one app-modal at a time, so the launcher tears Settings down before
opening anything over it.

Why this exists: the two recovery handlers did not, alone among the Settings
handlers. ``_open_dialog`` overwrites ``_dialog``, so Settings was left shown
and UNTRACKED — a second app-modal an idle auto-lock could no longer close, a
Save from it silently dropped by ``_on_settings_saved``'s ``isinstance`` guard,
and a "No recovery code is set" label still on screen after one had been set
(FIBR-0307 finding 10).
"""

from __future__ import annotations

import gc
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import pytestqt.exceptions
import shiboken6
from _recovery_helpers import MASTER_PASSWORD, NEW_MASTER_PASSWORD, create_vault
from PySide6.QtWidgets import QDialog, QMessageBox

from conftest import _pump_deferred_delete
from finbreak.errors import VaultLockedError
from finbreak.services.auth import AuthService
from finbreak.services.recovery_code import generate_code
from finbreak.ui import main_window as shell_module
from finbreak.ui import recovery_key as recovery_module
from finbreak.ui.main_window import MainWindow
from finbreak.ui.settings import SettingsDialog

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    create_vault(svc, MASTER_PASSWORD)
    yield svc
    svc.lock()


def _shell_with_settings_open(
    qtbot: Any, service: AuthService
) -> tuple[MainWindow, SettingsDialog]:
    """An unlocked shell with the Settings dialog open and tracked."""
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    window._open_settings()
    settings = window._dialog
    assert isinstance(settings, SettingsDialog), (
        "precondition: Settings must be the tracked dialog before a recovery "
        "button is pressed — that is the state these legs are about.\n"
        "  expected: SettingsDialog in the _dialog slot\n"
        f"  actual:   {type(settings).__name__}"
    )
    return window, settings


def _assert_settings_gone(settings: SettingsDialog, action: str) -> None:
    _pump_deferred_delete()
    assert not shiboken6.isValid(settings), (
        f"§ 4.7 {action} left the Settings dialog shown and untracked. "
        "`_open_dialog` overwrites the single `_dialog` slot, so nothing can "
        "reach Settings afterwards: an idle auto-lock cannot close it, a Save "
        "from it is dropped by `_on_settings_saved`'s isinstance guard, and it "
        "keeps showing the recovery state it was built with. Every other "
        "Settings-launched flow tears it down first.\n"
        "  expected: the Settings dialog torn down\n"
        "  actual:   still alive"
    )


def test_replacing_the_recovery_code_tears_settings_down(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """Add / Replace opens a dialog of its own, so Settings must go first."""
    monkeypatch.setattr(
        recovery_module, "_confirm_master_password", lambda *a, **k: True
    )
    window, settings = _shell_with_settings_open(qtbot, service)

    window._on_change_recovery_key()

    _assert_settings_gone(settings, "Replace")


def test_removing_the_recovery_code_tears_settings_down(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """Remove opens no dialog of its own, and owes the teardown for a second
    reason: its confirmation is blocking, and afterwards Settings would still
    offer to remove a code that is gone."""
    monkeypatch.setattr(shell_module, "remove_recovery_key", lambda *a, **k: True)
    window, settings = _shell_with_settings_open(qtbot, service)

    window._on_remove_recovery_key()

    _assert_settings_gone(settings, "Remove")


# --------------------------------------------------------------------------- #
# FP02 finding 12 — an idle auto-lock inside the § 4.7 nested loops
# --------------------------------------------------------------------------- #
def test_an_auto_lock_during_the_password_gate_is_not_a_crash(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """``QInputDialog.getText`` spins a nested event loop, so the auto-lock
    timer can fire inside it -- and ``verify_password`` then reads a locked
    vault and raises out of the Qt slot. Six other UI modules guard exactly
    this; the § 4.7 gate did not (FIBR-0307 finding 12).

    Fail closed and silently: the gate was not passed, and the shell is already
    tearing the dialog down and showing the unlock screen, so a message would
    land on a dying widget. That is the answer settings.py gives.
    """

    def lock_then_answer(*_a: Any, **_k: Any) -> tuple[str, bool]:
        service.lock()  # the idle auto-lock, inside the nested loop
        return (MASTER_PASSWORD.decode(), True)

    monkeypatch.setattr(
        recovery_module.QInputDialog, "getText", staticmethod(lock_then_answer)
    )
    monkeypatch.setattr(
        recovery_module.QMessageBox, "warning", staticmethod(lambda *a, **k: None)
    )

    assert recovery_module._confirm_master_password(service, None) is False, (
        "a vault that locked mid-gate has not authorised anything, so the gate "
        "must refuse rather than raise. Letting VaultLockedError out of a Qt "
        "slot is the crash class FIBR-0065 exists to stop.\n"
        "  expected: False\n"
        "  actual:   True"
    )


def test_an_auto_lock_during_the_remove_confirmation_is_not_a_crash(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """The same loop, one step later: the confirmation is blocking too, and
    ``remove_recovery_key`` reaches the vault after it."""

    def lock_then_confirm(*_a: Any, **_k: Any) -> Any:
        service.lock()
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(
        recovery_module.QMessageBox, "question", staticmethod(lock_then_confirm)
    )
    monkeypatch.setattr(
        recovery_module, "_confirm_master_password", lambda *a, **k: True
    )

    assert recovery_module.remove_recovery_key(service, None) is False, (
        "nothing was removed from a locked vault, so the helper must report "
        "that rather than raise out of the slot.\n"
        "  expected: False\n"
        "  actual:   True"
    )


# --------------------------------------------------------------------------- #
# FP02 finding 13 — the two smaller ones
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("write_succeeds", [True, False], ids=["saved", "failed"])
def test_the_status_line_follows_the_write(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
    service: AuthService,
    write_succeeds: bool,
) -> None:
    """ "Recovery code saved" was hung off ``accepted``, which fires on Keep --
    not on the write. ``keep_recovery_code`` hangs off the same signal and
    returns whether the re-wrap worked, so a failed write warned the user AND
    told them it was saved (FIBR-0307 finding 13).
    """
    from finbreak.ui.recovery_key import RecoveryCodeDialog

    def refuse(_code: str) -> None:
        raise RuntimeError("the re-wrap failed")

    monkeypatch.setattr(
        recovery_module, "_confirm_master_password", lambda *a, **k: True
    )
    monkeypatch.setattr(
        recovery_module.QMessageBox, "warning", staticmethod(lambda *a, **k: None)
    )
    window, _settings = _shell_with_settings_open(qtbot, service)
    if not write_succeeds:
        monkeypatch.setattr(service, "add_recovery_key", refuse)
    said: list[str] = []
    monkeypatch.setattr(window, "_status", said.append)

    window._on_change_recovery_key()
    dialog = window._dialog
    assert isinstance(dialog, RecoveryCodeDialog), (
        "precondition: the offer dialog must be up before Keep is pressed.\n"
        f"  expected: RecoveryCodeDialog\n  actual:   {type(dialog).__name__}"
    )
    dialog.accept()

    reported_saved = "Recovery code saved" in said
    assert reported_saved == write_succeeds, (
        "the status line must report what the WRITE did, not what the button "
        "was. A user told their code was saved when it was not will discard "
        "the only copy they were shown, and INV-5 means there is no second "
        "one.\n"
        f"  expected: reported_saved == {write_succeeds}\n"
        f"  actual:   {said}"
    )


def test_a_copied_recovery_code_is_cleared_from_the_clipboard(
    qtbot: Any, service: AuthService, monkeypatch: Any
) -> None:
    """Copy left the code on the clipboard indefinitely.

    ``ClipboardAutoClear`` already does this for a transaction description --
    the least sensitive thing the app copies. The recovery code is the most:
    it opens the vault on its own (FIBR-0307 finding 13).

    This leg runs the whole caller's chain and lets the TIMER fire, because the
    first version of it did neither: it built the dialog directly and called
    ``clear_if_ours()`` by hand, which is the guard's own implementation rather
    than anything the app arranges. That passed while the feature was inert --
    the guard was re-parented to the dialog, so the pending timer was destroyed
    with it the moment the user answered and the code stayed on the clipboard
    (FIBR-0310 R1). So: the real factory, the real teardown, and a real wait.
    """
    from PySide6.QtGui import QGuiApplication

    from finbreak.ui.recovery_key import build_recovery_offer

    # The shortest timeout the guard can arm; the settings enum's floor is 10s,
    # which is not a wait a test suite can take.
    monkeypatch.setattr(service, "clipboard_clear_seconds", lambda: 1)

    board = QGuiApplication.clipboard()
    board.clear()
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()

    code = "ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345"
    dialog = build_recovery_offer(service, code, window)
    dialog.finished.connect(window._teardown_dialog)  # what the shell wires
    window._open_dialog(dialog, defer=False)
    try:
        dialog._copy()
        assert board.text() == code, (
            "precondition: Copy must put the code on the clipboard, or the "
            "clearing this leg asserts has nothing to clear.\n"
            f"  expected: {code!r}\n  actual:   {board.text()!r}"
        )

        dialog.reject()  # the user answers, and the shell tears the dialog down
        _pump_deferred_delete()
        assert not shiboken6.isValid(dialog), (
            "precondition: the dialog must actually be destroyed before the "
            "clear is due -- that destruction is what killed the timer, so a "
            "leg that leaves the dialog alive cannot see the defect.\n"
            "  expected: a deleted dialog"
        )

        qtbot.waitUntil(lambda: board.text() == "", timeout=5000)
    finally:
        board.clear()


def _wait_for_clipboard_clear(
    qtbot: Any, board: Any, *, timeout_ms: int = 5000
) -> None:
    """Poll the clipboard for up to ``timeout_ms``, then assert with expected
    vs. actual -- a bare ``qtbot.waitUntil`` times out with only a line
    number, and a live-defect run must name the case that failed."""
    try:
        qtbot.waitUntil(lambda: board.text() == "", timeout=timeout_ms)
    except pytestqt.exceptions.TimeoutError:
        pass
    assert board.text() == "", (
        "the constructor's default clipboard guard did not survive the "
        "dialog: its clear timer went with it -- parented to the dialog "
        "(`parent=self`), or owned by nothing that outlasts it -- so the "
        "recovery code, the credential that opens the vault on its own, "
        "is still on the clipboard "
        f"{timeout_ms / 1000:.0f}s after the dialog was torn down "
        "(FIBR-0310 R1 at the constructor's own default; INV-21).\n"
        "  expected: '' (cleared)\n"
        f"  actual:   {board.text()!r}"
    )


def test_the_constructor_default_clipboard_guard_survives_the_dialog(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FP04 finding M6 — the sibling to the leg above, for the branch it
    cannot reach.

    ``build_recovery_offer`` always injects a guard, so the leg above only
    ever drives the ``clipboard is not None`` arm of the constructor. The
    default arm -- ``RecoveryCodeDialog(code)`` with no ``clipboard=``
    argument -- built its own ``ClipboardAutoClear(..., parent=self)``, which
    is FIBR-0310 R1 **verbatim**: the guard's single-shot clear timer was a Qt
    child of the dialog, so the dialog's own teardown destroyed the timer with
    it and a vault-opening code stayed on the clipboard for good. It now owns
    that guard from the dialog's parent, or from the application object where
    there is none (INV-21).
    Nothing routes through the shell here on purpose -- no ``MainWindow``,
    no ``build_recovery_offer`` -- because those are exactly what supplies
    the injected guard the leg above tests; this leg exists to reach the
    caller that supplies none.
    """
    from PySide6.QtGui import QGuiApplication

    from finbreak.ui.recovery_key import RecoveryCodeDialog

    # Read live inside the constructor's own lambda (`seconds_provider=lambda:
    # DEFAULT_CLIPBOARD_CLEAR_SECONDS`), so patching the module attribute is
    # what the shortest reachable timeout looks like for this branch -- there
    # is no `AuthService` in the loop to hand a `clipboard_clear_seconds`
    # override to, unlike the injected-guard leg above.
    monkeypatch.setattr(recovery_module, "DEFAULT_CLIPBOARD_CLEAR_SECONDS", 1)

    board = QGuiApplication.clipboard()
    board.clear()

    code = "ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345"
    dialog = RecoveryCodeDialog(code)  # no clipboard= — the branch under test
    try:
        dialog._copy()
        assert board.text() == code, (
            "precondition: Copy must put the code on the clipboard, or the "
            "clearing this leg asserts has nothing to clear.\n"
            f"  expected: {code!r}\n  actual:   {board.text()!r}"
        )

        dialog.deleteLater()  # the user answers / closes the dialog
        _pump_deferred_delete()
        assert not shiboken6.isValid(dialog), (
            "precondition: the dialog must actually be destroyed before the "
            "clear is due -- that destruction is what kills the timer when "
            "the guard is parented to the dialog, so a leg that leaves the "
            "dialog alive cannot see the defect.\n"
            "  expected: a deleted dialog"
        )

        # Drop the last Python reference too, then collect. Qt destroyed the
        # C++ dialog above, but the wrapper still holds ``_clipboard`` -- so a
        # guard owned by NOTHING stays alive on that reference alone and this
        # leg passes. Production drops the dialog. Measured with
        # mutation_probe: without these two lines the mutant that leaves the
        # guard unparented survives, so the leg would assert only that the
        # owner is not the dialog, rather than that there is one.
        del dialog
        gc.collect()

        _wait_for_clipboard_clear(qtbot, board)
    finally:
        board.clear()


# --------------------------------------------------------------------------- #
# FIBR-0310 R2 — a teardown with no return path
# --------------------------------------------------------------------------- #
def _assert_settings_back(window: MainWindow, action: str) -> None:
    _pump_deferred_delete()
    back = window._dialog
    assert isinstance(back, SettingsDialog), (
        f"§ 4.7 {action} tore Settings down and then opened nothing, so "
        "Settings simply vanished: the user asked for a preferences change and "
        "was dropped on the main window. Every sibling flow that tears Settings "
        "down REPLACES it (FIBR-0310 R2).\n"
        "  expected: a SettingsDialog back in the _dialog slot\n"
        f"  actual:   {type(back).__name__}"
    )
    assert not back.isHidden(), (
        f"§ 4.7 {action} put Settings back in the slot but left it hidden, "
        "which is the same vanishing act with the tracking repaired.\n"
        "  expected: shown\n  actual:   hidden"
    )


def test_cancelling_the_password_gate_puts_settings_back(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """Replace refused at the gate has changed nothing, so the user belongs
    back where they pressed the button."""
    monkeypatch.setattr(
        recovery_module, "_confirm_master_password", lambda *a, **k: False
    )
    window, settings = _shell_with_settings_open(qtbot, service)

    window._on_change_recovery_key()

    _assert_settings_gone(settings, "Replace")  # the old one is still torn down
    _assert_settings_back(window, "Replace, cancelled at the gate")


@pytest.mark.parametrize("confirmed", [False, True], ids=["cancelled", "removed"])
def test_answering_the_remove_confirmation_puts_settings_back(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, service: AuthService, confirmed: bool
) -> None:
    """Remove opens nothing of its own on EITHER branch. Cancelled, nothing
    happened at all; confirmed, Settings comes back rebuilt -- showing the state
    the teardown exists to stop it showing stale."""
    monkeypatch.setattr(shell_module, "remove_recovery_key", lambda *a, **k: confirmed)
    window, settings = _shell_with_settings_open(qtbot, service)

    window._on_remove_recovery_key()

    _assert_settings_gone(settings, "Remove")
    _assert_settings_back(window, f"Remove (confirmed={confirmed})")


def test_an_auto_lock_during_the_gate_does_not_reopen_settings(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """The return path is guarded, and this is what it is guarded against.

    ``_open_settings`` reads the vault for the base currency, and ``_lock``
    has already put the UnlockDialog in the single ``_dialog`` slot. Re-opening
    Settings over a locked vault would raise out of a Qt slot AND bury the
    unlock screen the user now needs (FIBR-0310 R2).
    """

    def lock_then_refuse(*_a: Any, **_k: Any) -> bool:
        # The production entry, inside the blocking gate: lock() and then the
        # shell's own `_lock`, which is what clears `_unlocked` and puts the
        # unlock screen in the slot. `service.lock()` alone reaches neither, and
        # a leg that used it would be asserting against a state the app cannot
        # be in.
        service._on_idle_timeout()
        return False

    monkeypatch.setattr(recovery_module, "_confirm_master_password", lock_then_refuse)
    window, settings = _shell_with_settings_open(qtbot, service)

    window._on_change_recovery_key()  # must not raise

    _assert_settings_gone(settings, "Replace")
    _pump_deferred_delete()
    assert not isinstance(window._dialog, SettingsDialog), (
        "Settings was re-opened over a vault that locked mid-gate. "
        "`_open_settings` reads the vault, and the slot already holds the "
        "unlock screen the user needs next.\n"
        "  expected: not a SettingsDialog\n"
        f"  actual:   {type(window._dialog).__name__}"
    )


# --------------------------------------------------------------------------- #
# FIBR-0310 P4 — the saved recovery code is owner-only
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(os.name != "posix", reason="file modes are a POSIX question")
@pytest.mark.parametrize("pre_exists", [False, True], ids=["new", "overwrite"])
def test_the_saved_recovery_code_is_owner_only(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pre_exists: bool
) -> None:
    """ "Save to a file" writes a credential that opens the vault on its own.

    A plain ``open()`` creates at the process umask -- 0644 on a normal
    desktop, so every account on the machine can read it. Every other
    secret-bearing write in the app is owner-only (coding.md § 7), and this one
    was the exception (FIBR-0310 P4).

    The overwrite leg is the half a mode argument cannot reach: an EXISTING
    file keeps its own permissions through an O_CREAT open, and that is the
    file the code is about to be written into.
    """
    from finbreak.ui.recovery_key import RecoveryCodeDialog

    target = tmp_path / "finbreak-recovery-code.txt"
    if pre_exists:
        target.write_text("an older copy\n", encoding="utf-8")
        target.chmod(0o644)

    monkeypatch.setattr(
        recovery_module.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(target), "")),
    )

    code = "ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345"
    dialog = RecoveryCodeDialog(code)
    qtbot.addWidget(dialog)
    dialog._save()

    assert target.read_text(encoding="utf-8") == code + "\n", (
        "precondition: the file must actually hold the code, or the mode this "
        "leg asserts is the mode of the wrong thing.\n"
        f"  expected: {code + chr(10)!r}\n"
        f"  actual:   {target.read_text(encoding='utf-8')!r}"
    )
    mode = target.stat().st_mode & 0o777
    assert mode == 0o600, (
        "the saved recovery code is readable by other accounts on this "
        "machine. It unlocks the vault on its own, so this is the whole "
        "credential sitting in a world-readable file.\n"
        "  expected: 0o600\n"
        f"  actual:   {mode:#o}"
    )


# --------------------------------------------------------------------------- #
# FIBR-0310 P12 — the two remaining one-modal / auto-lock gaps
# --------------------------------------------------------------------------- #
def test_an_auto_lock_before_keep_is_refused_silently(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """``keep_recovery_code`` was the one § 4.7 route with no ``VaultLockedError``
    arm: its broad ``except Exception`` caught the auto-lock and raised a warning
    box reading "the vault is locked" — an internal exception's words, on a
    window the shell is already swapping for the unlock screen. Its three
    siblings all fail closed and silently here (FIBR-0310 P12).
    """
    warnings: list[Any] = []
    monkeypatch.setattr(
        recovery_module.QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: warnings.append(a)),
    )
    # A WELL-FORMED code: `add_recovery_key` decodes before it reaches the lock
    # check, so a placeholder would raise ValueError and test the broad arm.
    code = generate_code()
    service.lock()
    with pytest.raises(VaultLockedError):
        service.add_recovery_key(code)  # precondition: this is the lock path

    assert recovery_module.keep_recovery_code(service, code, None) is False, (
        "nothing was written to a locked vault, so Keep must report that\n"
        "  expected: False\n  actual:   True"
    )
    assert warnings == [], (
        "a warning box on the auto-lock path lands on a dying widget and "
        "quotes an internal exception; the siblings show none.\n"
        f"  actual: {len(warnings)} warning(s)"
    )

    # And the arm is NARROW: a genuine re-wrap failure must still be visible.
    def refuse(_code: str) -> None:
        raise RuntimeError("the re-wrap failed")

    monkeypatch.setattr(service, "add_recovery_key", refuse)
    assert recovery_module.keep_recovery_code(service, code, None) is False
    assert len(warnings) == 1, (
        "a failed re-wrap must still warn -- the new arm must not swallow it\n"
        f"  actual: {len(warnings)} warning(s)"
    )


# --------------------------------------------------------------------------- #
# FP04 finding M7 -- the fourth D6/§ 4.7 route with no VaultLockedError arm
# --------------------------------------------------------------------------- #
def test_an_auto_lock_before_new_master_password_is_refused_silently(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """``NewMasterPasswordDialog._on_submit`` was the one D6 route with no
    ``VaultLockedError`` arm: its broad ``except Exception`` caught the
    auto-lock and rendered the exception's own wording into the dialog's error
    label -- on a dialog ``MainWindow._lock`` is already tearing down for the
    unlock screen. Its three § 4.7 siblings (``keep_recovery_code``,
    ``_confirm_master_password``, ``remove_recovery_key``) all fail closed and
    silently here (FIBR-0310 P12, FP04 finding M7).
    """
    dialog = recovery_module.NewMasterPasswordDialog(service)
    qtbot.addWidget(dialog)
    dialog._password.setText(NEW_MASTER_PASSWORD.decode())
    dialog._confirm.setText(NEW_MASTER_PASSWORD.decode())

    service.lock()  # the idle auto-lock, between the dialog opening and submit

    dialog._on_submit()

    assert dialog._error.text() == "", (
        "a submit against a locked vault set nothing, so the dialog must stay "
        "silent -- the sibling contract this route is missing. Rendering the "
        "internal exception's own wording onto a dialog already being torn "
        "down is exactly what FP04 finding M7 flags.\n"
        "  expected: ''\n"
        f"  actual:   {dialog._error.text()!r}"
    )
    assert dialog.result() != QDialog.DialogCode.Accepted, (
        "nothing was set on a locked vault, so the dialog must not report "
        "success by closing.\n"
        f"  actual result: {dialog.result()}"
    )

    # And the arm is NARROW: a genuine re-wrap failure must still be visible --
    # the siblings' own "must still warn" leg, for this dialog's inline label.
    def refuse(_password: bytearray) -> None:
        raise RuntimeError("the re-wrap failed")

    monkeypatch.setattr(service, "set_master_password", refuse)
    dialog2 = recovery_module.NewMasterPasswordDialog(service)
    qtbot.addWidget(dialog2)
    dialog2._password.setText(NEW_MASTER_PASSWORD.decode())
    dialog2._confirm.setText(NEW_MASTER_PASSWORD.decode())

    dialog2._on_submit()

    assert dialog2._error.text() != "", (
        "a genuine re-wrap failure must still reach the user -- the new "
        "VaultLockedError arm must not swallow it.\n"
        f"  actual: {dialog2._error.text()!r}"
    )


def test_open_dialog_enforces_the_one_modal_slot_itself(
    qtbot: Any, service: AuthService
) -> None:
    """The invariant was trusted to fifteen callers remembering to tear down
    first; forgetting is FP02 finding 10, and it leaves a live app-modal with
    nothing holding it. ``_open_dialog`` now does the teardown (FIBR-0310 P12).
    """
    window, settings = _shell_with_settings_open(qtbot, service)
    replacement = SettingsDialog(service, "ZAR", window)

    window._open_dialog(replacement, defer=False)  # deliberately no teardown

    _assert_settings_gone(settings, "opening a second dialog")
    assert window._dialog is replacement

    # Re-opening the SAME dialog must not destroy it -- `_show_if_pending`
    # re-checks the slot, and a self-teardown here would delete what it is
    # about to show.
    window._open_dialog(replacement, defer=False)
    _pump_deferred_delete()
    assert shiboken6.isValid(replacement) and window._dialog is replacement


def test_never_clear_does_not_apply_to_the_recovery_code(service, monkeypatch, qtbot):
    """ "Never clear" (0) is overridden for THIS copy, and only for 0.

    The clipboard setting was designed for an amount or a description
    (FIBR-0032) -- the least sensitive things the app copies. A recovery code
    opens the vault exactly as the master password does (security-model asset
    A8), and "Never" leaves it in a clipboard KDE Klipper and GNOME persist to
    disk, which is outside the memory-only carve-out INV-3c is written around.

    Every non-zero choice is a real auto-clear and stays exactly as chosen --
    this must not quietly lengthen a 10s setting.
    """
    import finbreak.ui.recovery_key as rk_mod
    from finbreak.services.auth import DEFAULT_CLIPBOARD_CLEAR_SECONDS
    from finbreak.ui.recovery_key import build_recovery_offer

    providers: list = []
    real = rk_mod.ClipboardAutoClear

    def _capture(clipboard, *, seconds_provider, parent=None):
        providers.append(seconds_provider)
        return real(clipboard, seconds_provider=seconds_provider, parent=parent)

    monkeypatch.setattr(rk_mod, "ClipboardAutoClear", _capture)

    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()

    for chosen, expected in ((0, DEFAULT_CLIPBOARD_CLEAR_SECONDS), (10, 10), (60, 60)):
        providers.clear()
        monkeypatch.setattr(service, "clipboard_clear_seconds", lambda c=chosen: c)
        dialog = build_recovery_offer(service, "ABCD-EFGH", window)
        try:
            assert providers, "the offer must build its own clipboard guard"
            assert providers[0]() == expected, (
                f"clipboard_clear_seconds()=={chosen} should arm for {expected}s"
            )
        finally:
            dialog.deleteLater()


def test_the_one_time_display_holds_off_the_idle_auto_lock(service, qtbot):
    """The idle auto-lock cannot destroy the one-time recovery display.

    `_show_recovery_offer` CONSUMES its source before showing the dialog, and
    the code is never re-offered -- so a teardown here is unrecoverable, and the
    user is left believing they hold a working credential they never wrote down.

    The idle timer measures inactivity from the last INPUT EVENT, and copying 28
    characters onto paper generates none, so `notify_activity` never fires and
    the default 10-minute countdown runs out while the user is plainly present.

    The hold is released when the dialog finishes, so an ordinary close re-arms
    the lock rather than leaving it off.
    """
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    window._pending_recovery_code = "ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345"

    assert service._timer is not None and service._timer.isActive(), (
        "precondition: the idle timer must be running, or this leg proves nothing"
    )

    assert window._show_recovery_offer() is True
    try:
        assert not service._timer.isActive(), "the idle countdown must be held"
        # And activity must not silently re-arm what was deliberately suspended.
        service.notify_activity()
        assert not service._timer.isActive(), "notify_activity must not re-arm it"
    finally:
        dialog = window._dialog
        assert dialog is not None
        dialog.reject()

    assert service._timer.isActive(), "finishing the dialog re-arms the lock"
