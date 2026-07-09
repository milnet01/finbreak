"""Toolbar icon loader — resolve a bundled monochrome SVG glyph to a ``QIcon`` (D7).

Hand-authored glyphs (no third-party icon set → zero licensing, no new
dependency) live in ``icons/`` beside this module. The toolbar shows a text
label under each glyph (``ToolButtonTextUnderIcon``), so the *label*, not the
glyph, carries the meaning (INV-10) and a neutral mid-tone reads acceptably on
the OS light **or** dark palette (palette-adaptive re-tinting is FIBR-0014).

Loading resolves relative to the package via ``__file__``, so it works both from
the source tree and from a frozen PyInstaller bundle (Deliverable 9); the SVGs
travel as package data and the ``imageformats/qsvg`` + ``iconengines/qsvgicon``
Qt plugins render them (DoD #2's non-null-pixmap self-test guards their travel).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

_ICON_DIR = Path(__file__).parent / "icons"
_APP_ICON = _ICON_DIR / "app.png"


def icon(name: str) -> QIcon:
    """The ``QIcon`` for the bundled glyph ``<name>.svg`` (e.g. ``"lock"``)."""
    return QIcon(str(_ICON_DIR / f"{name}.svg"))


def app_icon() -> QIcon:
    """The branded application/window icon (FIBR-0037) — a raster app tile,
    package data alongside the toolbar glyphs (regenerated from
    ``assets/icon/finbreak.png`` by ``scripts/make-icons.sh``). Set on the
    ``QApplication`` so every window, dialog, and the OS taskbar entry carry it;
    it travels into a frozen bundle via the same ``ui/icons/`` package data."""
    return QIcon(str(_APP_ICON))
