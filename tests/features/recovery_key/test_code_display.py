"""INV-27 — the recovery code leaves the display only through the Copy guard.

Why this exists: the display is a read-only ``QLineEdit``, and read-only still
lets the user select its text. A mouse drag, Shift+End or Ctrl+A put the code
in the X11 PRIMARY selection, which nothing clears; Ctrl+C and the context
menu's Copy put it on the clipboard through Qt's own copy, outside
``ClipboardAutoClear``. Measured on a private Xvfb display 2026-09-29
(FIBR-0367 row 34, audit lane 15). security-model T13 says the recovery code
IS auto-cleared, so every one of those routes made it false.

These legs run offscreen, where no PRIMARY selection exists, so they assert
the cause instead: no selection ever forms from a user gesture. That is what
Qt copies into PRIMARY, so a display that never holds a user selection has
nothing to put there. The Copy button's own ``selectAll()`` is kept as visual
feedback — measured not to reach PRIMARY — so the legs start from an empty
selection and do not touch that button.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtGui import QContextMenuEvent, QGuiApplication, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from finbreak.ui._clipboard import ClipboardAutoClear
from finbreak.ui.recovery_key import RecoveryCodeDialog

pytestmark = pytest.mark.features

CODE = "ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345"


@pytest.fixture
def display(qtbot: Any) -> Iterator[tuple[RecoveryCodeDialog, QLineEdit]]:
    board = QGuiApplication.clipboard()
    board.clear()
    owner = QObject()  # outlives the dialog, as INV-21 requires
    guard = ClipboardAutoClear(board, seconds_provider=lambda: 1, parent=owner)
    dialog = RecoveryCodeDialog(CODE, clipboard=guard)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    field = dialog._display
    field.deselect()
    assert not field.hasSelectedText(), "precondition: no selection to start"
    try:
        yield dialog, field
    finally:
        board.clear()
        owner.deleteLater()
        # A QTest mouse event carrying Shift leaves the application believing
        # Shift is still held, and the next test on this worker inherits it: a
        # `selectRow` then EXTENDS a selection instead of moving it. That broke
        # table_state on CI, where xdist put the two tests on one worker. One
        # plain click, on a widget with no filter, resets the state.
        QTest.mouseClick(dialog, Qt.MouseButton.LeftButton)


def _mid(field: QLineEdit, x: int) -> QPoint:
    return QPoint(x, field.height() // 2)


def test_a_mouse_drag_selects_nothing(display: Any) -> None:
    dialog, field = display
    copy_button = dialog.findChild(QPushButton, "recovery_code_copy")
    assert copy_button is not None
    copy_button.setFocus()
    assert not field.hasFocus(), "precondition: the click must be what focuses it"
    QTest.mousePress(
        field, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, _mid(field, 3)
    )
    QTest.mouseMove(field, _mid(field, field.width() - 3))
    QTest.mouseRelease(
        field,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        _mid(field, field.width() - 3),
    )
    assert not field.hasSelectedText(), (
        "a mouse drag selected the recovery code, and on X11 a selection is "
        f"copied to PRIMARY, which nothing clears: {field.selectedText()!r}"
    )
    assert field.hasFocus(), "a click must still give the field focus"


def test_a_shift_click_selects_nothing(display: Any) -> None:
    """Shift+click extends a selection on the PRESS alone, with no drag."""
    _dialog, field = display
    field.setFocus()
    field.setCursorPosition(0)
    QTest.mouseClick(
        field,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        _mid(field, field.width() - 3),
    )
    assert not field.hasSelectedText(), field.selectedText()


def test_a_double_click_selects_nothing(display: Any) -> None:
    _dialog, field = display
    QTest.mouseDClick(
        field,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        _mid(field, 10),
    )
    assert not field.hasSelectedText(), field.selectedText()


@pytest.mark.parametrize(
    "gesture",
    [
        pytest.param(
            lambda f: (
                QTest.keyClick(f, Qt.Key.Key_Home),
                QTest.keyClick(f, Qt.Key.Key_End, Qt.KeyboardModifier.ShiftModifier),
            ),
            id="shift+end",
        ),
        pytest.param(
            lambda f: QTest.keyClick(
                f, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
            ),
            id="shift+right",
        ),
        pytest.param(
            lambda f: QTest.keySequence(f, QKeySequence.StandardKey.SelectAll),
            id="select-all",
        ),
        pytest.param(
            lambda f: QTest.keySequence(f, QKeySequence.StandardKey.SelectEndOfLine),
            id="select-end-of-line",
        ),
    ],
)
def test_a_keyboard_selection_selects_nothing(display: Any, gesture: Any) -> None:
    _dialog, field = display
    field.setFocus()
    gesture(field)
    assert not field.hasSelectedText(), (
        "a keyboard selection took the recovery code, and on X11 a selection "
        f"is copied to PRIMARY, which nothing clears: {field.selectedText()!r}"
    )


def test_plain_arrow_keys_still_move_the_caret(display: Any) -> None:
    """A screen reader user reads the code character by character with the
    arrow keys (FIBR-0328). Blocking selection must not block that."""
    _dialog, field = display
    field.setFocus()
    field.setCursorPosition(0)
    QTest.keyClick(field, Qt.Key.Key_Right)
    QTest.keyClick(field, Qt.Key.Key_Right)
    assert field.cursorPosition() == 2
    QTest.keyClick(field, Qt.Key.Key_End)
    assert field.cursorPosition() == len(CODE)


@pytest.mark.parametrize(
    "sequence",
    [QKeySequence.StandardKey.Copy, QKeySequence.StandardKey.Cut],
    ids=["copy", "cut"],
)
def test_the_copy_key_goes_through_the_auto_clear(
    display: Any, qtbot: Any, sequence: Any
) -> None:
    """Ctrl+C is how people copy. It must land on the clipboard AND be cleared,
    exactly as the Copy button is — not bypass the guard through Qt's own copy.
    """
    _dialog, field = display
    board = QGuiApplication.clipboard()
    field.setFocus()
    QTest.keySequence(field, sequence)
    assert board.text() == CODE, (
        "the copy key must still copy the code — blocking it would leave the "
        f"user writing it out by hand. clipboard: {board.text()!r}"
    )
    assert field.text() == CODE, "Cut must not edit a read-only display"
    qtbot.waitUntil(lambda: board.text() == "", timeout=5000)


def test_there_is_no_context_menu(display: Any) -> None:
    """The context menu's Copy is Qt's own and goes around the guard."""
    _dialog, field = display
    at = _mid(field, 10)
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Keyboard,
        at,
        field.mapToGlobal(at),
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(field, event)
    popup = QApplication.activePopupWidget()
    try:
        assert popup is None, f"a context menu opened over the recovery code: {popup!r}"
    finally:
        if popup is not None:
            popup.close()
