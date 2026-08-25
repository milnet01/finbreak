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

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import shiboken6
from _recovery_helpers import MASTER_PASSWORD, create_vault
from PySide6.QtWidgets import QMessageBox

from conftest import _pump_deferred_delete
from finbreak.services.auth import AuthService
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
