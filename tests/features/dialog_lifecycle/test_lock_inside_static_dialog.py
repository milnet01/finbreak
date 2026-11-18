"""FIBR-0477 — an auto-lock inside the import wizard's two static pop-ups.

``QFileDialog.getOpenFileNames`` and ``QMessageBox.warning`` each run a nested
event loop, and the FIBR-0065 INV-1 grep cannot see them (no ``.exec(``). An
idle auto-lock firing inside one hands the wizard to ``deleteLater``, which Qt
holds until control is back in the outer loop — so the wizard is still alive
when the pop-up returns, and the code after it runs on a live wizard whose
vault is locked. These tests fire the lock inside a real nested loop, as the
app does, and assert the window stays locked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer

import finbreak.ui.import_wizard as wizard_mod
from conftest import _PW
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportResult
from finbreak.ui.import_wizard import ImportWizardWidget
from finbreak.ui.main_window import MainWindow

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def _wizard(qtbot, service) -> tuple[MainWindow, ImportWizardWidget]:
    service.first_run(bytearray(_PW), "ZAR")
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    window._open_import()
    wizard = window._live
    assert isinstance(wizard, ImportWizardWidget)
    return window, wizard


def _lock_inside_a_nested_loop(service: AuthService) -> None:
    """What a static pop-up does while the user is away: spin its own loop,
    during which the idle timer fires."""
    loop = QEventLoop()

    def fire() -> None:
        service._on_idle_timeout()
        loop.quit()

    QTimer.singleShot(0, fire)
    loop.exec()


def _assert_still_locked(window: MainWindow) -> None:
    assert window._workspace is None, "a workspace was built after the lock"
    assert window._content.currentWidget() is window._placeholder_locked


def test_FIBR0477_lock_inside_the_balance_warning_keeps_the_window_locked(
    qtbot, service, monkeypatch
):
    """Closing the warning must not run the wizard's "import finished" step:
    that rebuilds the workspace, over the lock screen, from a locked vault."""
    window, wizard = _wizard(qtbot, service)
    wizard._preview = object()  # type: ignore[assignment]
    monkeypatch.setattr(
        wizard._imports,
        "commit_import",
        lambda *_a, **_k: ImportResult(
            inserted_count=1,
            duplicate_count=0,
            error_count=0,
            period_recorded=False,
            closing_balance_mismatch=True,
        ),
    )
    monkeypatch.setattr(wizard, "_save_remembered_pw", lambda: None)
    monkeypatch.setattr(
        wizard_mod.QMessageBox,
        "warning",
        lambda *_a, **_k: _lock_inside_a_nested_loop(service),
    )

    wizard._on_import()

    _assert_still_locked(window)


def test_FIBR0477_lock_inside_the_file_picker_keeps_the_window_locked(
    qtbot, service, monkeypatch, tmp_path: Path
):
    """The picked file must not be read into a wizard the lock has discarded."""
    window, wizard = _wizard(qtbot, service)
    statement = tmp_path / "a.csv"
    statement.write_text("Date,Details,Amount\n2026-07-01,coffee,-12.50\n")

    def pick(*_a, **_k):
        _lock_inside_a_nested_loop(service)
        return [str(statement)], ""

    monkeypatch.setattr(wizard_mod.QFileDialog, "getOpenFileNames", pick)
    before = wizard._source_path

    wizard._on_pick_file()

    _assert_still_locked(window)
    assert wizard._source_path == before, "the wizard took the file after the lock"
    assert wizard._text is None, "the wizard read the file after the lock"
