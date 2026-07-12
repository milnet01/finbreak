"""Toolbar icon loader — resolve a bundled monochrome SVG glyph to a ``QIcon`` (D7).

Hand-authored glyphs (no third-party icon set → zero licensing, no new
dependency) live in ``icons/`` beside this module, authored with a single neutral
``#808080`` stroke. ``toolbar_icon`` recolours each at load time (FIBR-0116): a
**muted** hue at rest and a **vibrant** one on hover (Qt swaps to the ``QIcon``
``Active`` pixmap when the cursor is over the toolbar button), tuned to the active
light/dark theme. ``icon`` still returns the plain neutral glyph for anywhere the
coloured/hover treatment isn't wanted.

Loading resolves relative to the package via ``__file__``, so it works both from
the source tree and from a frozen PyInstaller bundle (Deliverable 9); the SVGs
travel as package data and the ``imageformats/qsvg`` + ``iconengines/qsvgicon``
Qt plugins render them (DoD #2's non-null-pixmap self-test guards their travel).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

_ICON_DIR = Path(__file__).parent / "icons"
_APP_ICON = _ICON_DIR / "app.png"

# The neutral stroke/fill colour every hand-authored glyph ships with — the token
# ``toolbar_icon`` swaps for a per-icon muted/vibrant colour (FIBR-0116).
_GLYPH_INK = "#808080"

# Per-glyph semantic hue (degrees). Each toolbar icon gets its own calm colour so
# the row reads as one gently-coloured set, and hover brightens whichever the
# cursor is over. Any glyph not listed stays neutral grey.
_ICON_HUES = {
    "home": 210,  # blue
    "manual_entry": 145,  # green
    "import": 172,  # teal
    "accounts": 265,  # indigo
    "categories": 38,  # amber
    "rules": 290,  # purple
    "transfers": 190,  # cyan
    "lock": 25,  # warm ochre
}

# The pixmap sizes toolbar (text-under-icon, ~24-32) and menus (16) request;
# pre-rendered so QIcon has a crisp source at each.
_ICON_SIZES = (16, 24, 32, 48)


def icon(name: str) -> QIcon:
    """The ``QIcon`` for the bundled glyph ``<name>.svg`` (e.g. ``"lock"``), as
    authored (neutral grey). Use ``toolbar_icon`` for the coloured, hover-aware
    variant."""
    return QIcon(str(_ICON_DIR / f"{name}.svg"))


def _is_dark_theme() -> bool:
    """Whether the active Qt palette is dark (window-background lightness < 0.5), so
    the glyph colours can suit the current theme (FIBR-0116). Defaults to dark
    (ADR-0002) when no ``QApplication`` exists yet."""
    if QApplication.instance() is None:
        return True
    # QApplication.palette() is a static accessor for the current app palette.
    return QApplication.palette().color(QPalette.ColorRole.Window).lightnessF() < 0.5


def _muted_vibrant(hue: int, dark: bool) -> tuple[QColor, QColor]:
    """The (rest, hover) colours for a glyph ``hue`` on a dark or light theme: muted
    and subdued at rest, saturated and brighter on hover. On a light theme both are
    darker so they read against a pale background."""
    h = hue / 360.0
    if dark:
        return QColor.fromHslF(h, 0.32, 0.62), QColor.fromHslF(h, 0.85, 0.70)
    return QColor.fromHslF(h, 0.38, 0.46), QColor.fromHslF(h, 0.90, 0.42)


def _render(svg_text: str, size: int) -> QPixmap:
    """Rasterise recoloured SVG text to a transparent ``size``×``size`` pixmap."""
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def toolbar_icon(name: str) -> QIcon:
    """A theme-aware, hover-brightening ``QIcon`` for glyph ``<name>`` (FIBR-0116):
    a muted colour at rest (``QIcon`` ``Normal``) and a vibrant one on hover/focus
    (``Active`` / ``Selected`` — Qt swaps to it when the cursor is over the toolbar
    button). Falls back to the neutral ``icon`` for any glyph without a mapped hue."""
    hue = _ICON_HUES.get(name)
    if hue is None:
        return icon(name)
    base = (_ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
    muted, vibrant = _muted_vibrant(hue, _is_dark_theme())
    result = QIcon()
    for size in _ICON_SIZES:
        result.addPixmap(
            _render(base.replace(_GLYPH_INK, muted.name()), size), QIcon.Mode.Normal
        )
        active = _render(base.replace(_GLYPH_INK, vibrant.name()), size)
        result.addPixmap(active, QIcon.Mode.Active)
        result.addPixmap(active, QIcon.Mode.Selected)  # keyboard focus brightens too
    return result


def app_icon() -> QIcon:
    """The branded application/window icon (FIBR-0037) — a raster app tile,
    package data alongside the toolbar glyphs (regenerated from
    ``assets/icon/finbreak.png`` by ``scripts/make-icons.sh``). Set on the
    ``QApplication`` so every window, dialog, and the OS taskbar entry carry it;
    it travels into a frozen bundle via the same ``ui/icons/`` package data."""
    return QIcon(str(_APP_ICON))
