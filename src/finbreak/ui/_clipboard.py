"""ClipboardAutoClear — copy a value to the system clipboard, then wipe it after a
configurable timeout, but only if the clipboard still holds *our* value (FIBR-0032).

A tiny reusable ``QObject`` seam: it takes its ``QClipboard`` and a live
``seconds_provider`` by injection, so the caller (the transactions list) never has
to know how the timeout is configured, and tests drive the guard deterministically
against a real or fake clipboard. The single-shot timer's ``timeout`` is wired
**directly** to :meth:`clear_if_ours`, so the guard has exactly one implementation.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QClipboard


class ClipboardAutoClear(QObject):
    def __init__(
        self,
        clipboard: QClipboard,
        *,
        seconds_provider: Callable[[], int],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._clipboard = clipboard
        self._seconds_provider = seconds_provider
        self._pending: str | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear_if_ours)

    def copy(self, text: str) -> None:
        """Write ``text`` to the default clipboard and arm the auto-clear timer. The
        timeout is read live (per copy) so a mid-session Settings change takes effect
        on the next copy; ``0`` copies without arming any clear."""
        self._clipboard.setText(text)
        seconds = self._seconds_provider()
        self._timer.stop()
        if seconds > 0:
            self._pending = text
            self._timer.start(seconds * 1000)
        else:
            self._pending = None

    def clear_if_ours(self) -> None:
        """Clear the clipboard **iff** it still holds the exact value we last copied —
        so a value the user copied since (even from another app) is left untouched."""
        if self._pending is not None and self._clipboard.text() == self._pending:
            self._clipboard.clear()
        self._pending = None
