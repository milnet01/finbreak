"""The test session never touches the user's real finbreak data directory.

Full audit 2026-09-27, rows 1-3: a test run rewrote the user's real
``~/.local/share/finbreak/window.ini``. Two routes led there -- a
``monkeypatch.undo()`` that also lifted the autouse ``window_ini`` redirect, and
``app.run()`` calls that resolved ``paths.vault_path()`` for real. conftest now
puts Qt's standard paths in test mode for the whole session; these tests lock
that, and forbid the ``undo()`` call that caused the first route.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths

from finbreak import paths

_TESTS = Path(__file__).resolve().parent


def _real_app_data_location() -> str:
    """Where AppDataLocation points with test mode OFF -- the user's real one."""
    QCoreApplication.setApplicationName(paths.APP_NAME)
    QStandardPaths.setTestModeEnabled(False)
    try:
        return QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    finally:
        QStandardPaths.setTestModeEnabled(True)


def test_the_data_dir_is_not_the_users_real_one() -> None:
    real = Path(_real_app_data_location())
    sandboxed = paths.data_dir()
    assert sandboxed != real, (
        "the session resolves the app's data directory to the user's REAL one, "
        "where the live vault and window.ini are; conftest must enable "
        "QStandardPaths test mode before anything resolves a path.\n"
        f"  resolved: {sandboxed}"
    )
    assert paths.vault_path().parent == sandboxed


def test_no_test_calls_monkeypatch_undo() -> None:
    """``monkeypatch`` is one object per test, shared with every autouse fixture,
    so ``undo()`` also removes the ``window_ini`` redirect and the category-library
    neutraliser mid-test. Use ``with monkeypatch.context() as scoped:`` instead."""
    pattern = re.compile(r"\bmonkeypatch\.undo\(\)")
    offenders = [
        f"{path.relative_to(_TESTS)}:{number}"
        for path in sorted(_TESTS.rglob("*.py"))
        if path.name != Path(__file__).name
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line.split("#", 1)[0])  # code, not a comment naming it
    ]
    assert not offenders, (
        "monkeypatch.undo() lifts the suite-wide redirects too; use "
        f"monkeypatch.context() instead: {offenders}"
    )
