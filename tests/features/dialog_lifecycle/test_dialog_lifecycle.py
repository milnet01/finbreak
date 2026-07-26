"""FIBR-0065 INV-1 / INV-4 — the crash-class regression guard + the no-leak gate.

No content-widget pop-up may block the event loop via ``dialog.exec()``: the H-B
crash (auto-lock during a nested ``exec()`` loop → deleted-C++-object
``RuntimeError``) can only exist where a blocking ``exec()`` does. A source grep
over the four converted files asserts the only surviving ``.exec(`` is the Home
context ``QMenu`` (a pop-up menu, not a modal dialog — out of scope).

INV-4 locks the other half of the bargain: dropping ``exec()`` means the dialog is
no longer owned by a nested loop, so ``show_modal`` must free it itself on a
*normal* close. Every other ``shiboken6.isValid`` assertion in the suite is
lock-driven; these two cover the accept and reject paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import shiboken6
from PySide6.QtWidgets import QDialog, QWidget

import finbreak.ui as ui_pkg
from conftest import _pump_deferred_delete
from finbreak.ui.modal import show_modal

_UI_DIR = Path(ui_pkg.__file__).parent
_FILES = ("home.py", "rules.py", "statements.py", "import_wizard.py")
_EXEC = re.compile(r"\.exec\(")


def test_INV1_no_blocking_dialog_exec_in_content_widgets() -> None:
    offenders: list[str] = []
    for name in _FILES:
        for lineno, line in enumerate((_UI_DIR / name).read_text().splitlines(), 1):
            if not _EXEC.search(line):
                continue
            # Sole exemption: the Home right-click context menu (a QMenu, not a
            # modal dialog; reads no dialog object after, out of scope).
            if name == "home.py" and "menu.exec(" in line:
                continue
            offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "blocking .exec( found — convert to the non-blocking show_modal pattern "
        "(FIBR-0065 INV-1):\n" + "\n".join(offenders)
    )


# -- INV-4 (no leak) --------------------------------------------------------- #


def test_INV4_accept_runs_slot_on_a_live_dialog_then_frees_it(qtbot) -> None:
    """The accept path: ``on_accept`` still sees a live dialog (``deleteLater`` is
    deferred, which is *why* the helper uses it), and the dialog is gone once the
    DeferredDelete queue is flushed."""
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = QDialog(parent)
    alive_during_slot: list[bool] = []

    show_modal(dialog, lambda: alive_during_slot.append(shiboken6.isValid(dialog)))
    dialog.accept()

    assert alive_during_slot == [True], "on_accept must run, and on a live dialog"
    _pump_deferred_delete()
    assert not shiboken6.isValid(dialog), "the dialog is freed on accept"


def test_INV4_reject_frees_the_dialog_without_running_the_slot(qtbot) -> None:
    """The reject path: ``finished`` fires on reject too, so the dialog is freed —
    but ``accepted`` does not, so ``on_accept`` must not run."""
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = QDialog(parent)
    calls: list[int] = []

    show_modal(dialog, lambda: calls.append(1))
    dialog.reject()

    assert calls == [], "on_accept must not run on reject"
    _pump_deferred_delete()
    assert not shiboken6.isValid(dialog), "the dialog is freed on reject"
