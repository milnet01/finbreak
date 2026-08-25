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
