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
