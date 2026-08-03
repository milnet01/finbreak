"""App-wide theme system — six finance themes + follow-system (FIBR-0127, ADR-0010).

A theme is eight semantic colour **tokens** (+ an ``is_dark`` flag) that expand,
with no per-theme hardcoding, into a full Qt ``QPalette`` (``build_palette``) **and**
a polish stylesheet (``build_stylesheet`` — gradient/glow accents, grid
row-highlighting). ``THEMES`` registers the six ids (three light, three dark).

``ThemeController`` owns the current **mode** (a theme id or ``"system"``), applies
a theme (Fusion style + palette + stylesheet, then emits ``themeChanged``), and —
while in ``"system"`` mode — tracks the OS light/dark scheme **live** via
``styleHints().colorSchemeChanged`` (Qt 6.5+). The chosen mode is stored **outside
the encrypted vault**, in the plaintext window INI (``load_theme_pref`` /
``save_theme_pref``), so it applies to the very first, still-locked window — before
any key exists to open the vault (D2). The system is presentation-only: it takes
no vault / ``AuthService`` reference and issues no vault query (INV-12).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from PySide6.QtCore import QObject, QSettings, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractItemView, QApplication, QWidget

from finbreak import paths


@dataclass(frozen=True)
class ThemeTokens:
    """The nine semantic colours a theme is built from, plus ``is_dark``. Every
    field has a consumer this cut (INV-3): eight feed ``build_palette``'s roles
    (INV-4) and ``build_stylesheet`` (D7); ``attention`` is stylesheet-only — the
    per-theme warning colour the Home Alerts button fills with (FIBR-0185), so no
    hard-coded red leaks past the theme. ``is_dark`` drives the picker's Light/Dark
    grouping (INV-9) and the stylesheet gradient direction (D7). No ``positive`` /
    ``negative`` amount tokens — amounts keep their fixed mid-tones (D9)."""

    window: QColor
    base: QColor
    alt_base: QColor
    text: QColor
    muted_text: QColor
    accent: QColor
    accent_soft: QColor
    attention: QColor
    border: QColor
    is_dark: bool


@dataclass(frozen=True)
class ThemeDef:
    """A registered theme: a display ``name`` (data, not ``tr()``-wrapped — INV-13)
    and its ``tokens``."""

    name: str
    tokens: ThemeTokens


def _c(value: str) -> QColor:
    return QColor(value)


# The six finance-flavoured themes (ADR-0010). Three light (window lightness
# >= 0.5, is_dark=False), three dark (< 0.5, is_dark=True) — INV-3 pins the
# agreement so _is_dark_theme (which reads the live palette's window lightness)
# always tracks the flag.
THEMES: dict[str, ThemeDef] = {
    "ledger": ThemeDef(
        "Ledger",
        ThemeTokens(
            window=_c("#f5f4ef"),
            base=_c("#ffffff"),
            alt_base=_c("#efece2"),
            text=_c("#1b2a44"),
            muted_text=_c("#6b7280"),
            accent=_c("#b8892b"),
            accent_soft=_c("#e6d5a3"),
            attention=_c("#a53a24"),
            border=_c("#d8d3c4"),
            is_dark=False,
        ),
    ),
    "parchment": ThemeDef(
        "Parchment",
        ThemeTokens(
            window=_c("#efe6d3"),
            base=_c("#f9f2e2"),
            alt_base=_c("#e6dac2"),
            text=_c("#4a3b2a"),
            muted_text=_c("#8a7a63"),
            accent=_c("#b06d1f"),
            accent_soft=_c("#e0c48f"),
            attention=_c("#96331d"),
            border=_c("#d0c2a4"),
            is_dark=False,
        ),
    ),
    "mint": ThemeDef(
        "Mint",
        ThemeTokens(
            window=_c("#f1f7f3"),
            base=_c("#ffffff"),
            alt_base=_c("#e6f1ea"),
            text=_c("#16302a"),
            muted_text=_c("#5f7a6f"),
            accent=_c("#1f9d55"),
            accent_soft=_c("#bce7cd"),
            attention=_c("#b03a1e"),
            border=_c("#cde0d4"),
            is_dark=False,
        ),
    ),
    "midnight": ThemeDef(
        "Midnight",
        ThemeTokens(
            window=_c("#131a2b"),
            base=_c("#0d1320"),
            alt_base=_c("#1b2336"),
            text=_c("#e6e9f0"),
            muted_text=_c("#8b93a7"),
            accent=_c("#d4af37"),
            accent_soft=_c("#6b5d2e"),
            attention=_c("#e0654f"),
            border=_c("#2a3450"),
            is_dark=True,
        ),
    ),
    "graphite": ThemeDef(
        "Graphite",
        ThemeTokens(
            window=_c("#23262b"),
            base=_c("#1a1c20"),
            alt_base=_c("#2b2f35"),
            text=_c("#dfe2e6"),
            muted_text=_c("#8a9099"),
            accent=_c("#5b7fb5"),
            accent_soft=_c("#34435c"),
            attention=_c("#e2775c"),
            border=_c("#3a3f47"),
            is_dark=True,
        ),
    ),
    "emerald": ThemeDef(
        "Emerald",
        ThemeTokens(
            window=_c("#102019"),
            base=_c("#0a1712"),
            alt_base=_c("#172b22"),
            text=_c("#dcece4"),
            muted_text=_c("#7d9a8c"),
            accent=_c("#1fae6a"),
            accent_soft=_c("#2a5a44"),
            attention=_c("#e8836a"),
            border=_c("#234636"),
            is_dark=True,
        ),
    ),
}

DEFAULT_LIGHT = "ledger"
DEFAULT_DARK = "midnight"

# The non-vault window-INI key the pref lives under (INV-2, D2).
THEME_PREF_KEY = "theme"


# --------------------------------------------------------------------------- #
# The non-vault preference (INV-2)
# --------------------------------------------------------------------------- #
def _settings() -> QSettings:
    return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)


def load_theme_pref() -> str:
    """The stored theme mode from the non-vault window INI, guarded: a value is
    returned **only** if it names a known theme id or ``"system"``; an absent key or
    any unknown/garbage value returns ``"system"`` (the safe default, INV-2). Never
    reads the vault."""
    value = _settings().value(THEME_PREF_KEY)
    if isinstance(value, str) and (value in THEMES or value == "system"):
        return value
    return "system"


def save_theme_pref(theme_id: str) -> None:
    """UPSERT the theme mode into the non-vault window INI (INV-2). Does **not**
    ``sync()`` / inspect ``status()`` — a UI look-pref does not warrant surfacing a
    disk error (D4); ``ThemeController.set_theme`` wraps this best-effort."""
    _settings().setValue(THEME_PREF_KEY, theme_id)


# --------------------------------------------------------------------------- #
# Token -> palette / stylesheet (INV-4, INV-5)
# --------------------------------------------------------------------------- #
def _relative_luminance(colour: QColor) -> float:
    """WCAG 2.2 relative luminance of an sRGB colour — channels linearised, then
    combined by the standard coefficients."""

    def channel(value: int) -> float:
        f = value / 255.0
        return f / 12.92 if f <= 0.03928 else ((f + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(colour.red())
        + 0.7152 * channel(colour.green())
        + 0.0722 * channel(colour.blue())
    )


def _contrast_ratio(a: QColor, b: QColor) -> float:
    """WCAG 2.2 contrast ratio between two colours (1.0 … 21.0)."""
    la, lb = _relative_luminance(a), _relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _highlighted_text(accent: QColor) -> QColor:
    """The selected-row text colour: whichever of near-white / near-black actually
    contrasts the accent fill better (INV-4/INV-4a).

    This used to branch on ``accent.lightnessF() < 0.5``. HSL lightness is not
    perceptual luminance, and the two disagree exactly where it matters — a
    saturated mid-hue accent scores under 0.5, so it was classed "dark" and given
    near-white text it does not contrast. Measured on the shipped palettes, four
    of six themes landed under WCAG 2.2 SC 1.4.3's 4.5:1 on the most-read string
    in the app (emerald worst, 2.63:1), while the *other* candidate this same
    function already returns cleared the bar on all six. Choosing by the real
    contrast ratio fixes every failing theme and is a no-op on the two that
    passed, so no palette had to be redesigned.
    """
    light, dark = QColor("#f5f5f7"), QColor("#111119")
    return (
        light
        if _contrast_ratio(light, accent) > _contrast_ratio(dark, accent)
        else dark
    )


def build_palette(tokens: ThemeTokens) -> QPalette:
    """A full ``QPalette`` mapped from the tokens (INV-4). Every colour token is
    some role's source; ``HighlightedText`` is computed from the accent."""
    palette = QPalette()
    role = QPalette.ColorRole
    palette.setColor(role.Window, tokens.window)
    palette.setColor(role.Button, tokens.window)
    for text_role in (role.WindowText, role.Text, role.ButtonText, role.ToolTipText):
        palette.setColor(text_role, tokens.text)
    palette.setColor(role.Base, tokens.base)
    palette.setColor(role.ToolTipBase, tokens.base)
    palette.setColor(role.AlternateBase, tokens.alt_base)
    palette.setColor(role.PlaceholderText, tokens.muted_text)
    palette.setColor(QPalette.ColorGroup.Disabled, role.Text, tokens.muted_text)
    palette.setColor(QPalette.ColorGroup.Disabled, role.WindowText, tokens.muted_text)
    palette.setColor(role.Highlight, tokens.accent)
    palette.setColor(role.HighlightedText, _highlighted_text(tokens.accent))
    palette.setColor(role.Link, tokens.accent_soft)
    palette.setColor(role.Mid, tokens.border)
    palette.setColor(role.Dark, tokens.border)
    return palette


def _companion(colour: QColor, is_dark: bool) -> QColor:
    """The second gradient stop beside a base token: lightened on a dark theme,
    darkened on a light one (D7 — ``is_dark``'s stylesheet consumer)."""
    return colour.lighter(132) if is_dark else colour.darker(122)


def build_stylesheet(tokens: ThemeTokens) -> str:
    """The polish stylesheet for a theme (INV-5, D7): gradient/glow accent borders
    on inputs/buttons/tabs and hover + selection row gradients with alternating
    stripes in the item views. Scoped to specific widget classes so the chart
    ``QGraphicsView`` is never wrapped in an unwanted border. Each gradient emits its
    base token's hex **verbatim** as one stop (so ``accent`` / ``accent_soft``
    ``.name()`` appear literally — what INV-5/INV-11 assert), with a
    lightened/darkened companion as the other."""
    window = tokens.window.name()
    base = tokens.base.name()
    alt_base = tokens.alt_base.name()
    text = tokens.text.name()
    muted = tokens.muted_text.name()
    accent = tokens.accent.name()
    accent_soft = tokens.accent_soft.name()
    attention = tokens.attention.name()
    border = tokens.border.name()
    hover_2 = _companion(tokens.accent_soft, tokens.is_dark).name()
    selected_2 = _companion(tokens.accent, tokens.is_dark).name()
    hi_text = _highlighted_text(tokens.accent).name()
    attention_text = _highlighted_text(tokens.attention).name()
    return f"""
/* FIBR-0127 polish stylesheet — generated from the theme tokens (ADR-0010). */
QToolBar {{
    border: 0px;
    border-bottom: 1px solid {border};
    background: {window};
    spacing: 4px;
    padding: 3px;
}}
QToolButton {{
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 6px;
}}
QToolButton:hover {{
    border: 1px solid {accent_soft};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {accent_soft}, stop:1 {hover_2});
}}
QLineEdit, QComboBox, QSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
    background: {base};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 3px 6px;
    selection-background-color: {accent};
    selection-color: {hi_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {accent};
}}
QPushButton {{
    background: {base};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 14px;
}}
QPushButton:hover {{
    border: 1px solid {accent};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {accent_soft}, stop:1 {hover_2});
}}
QPushButton:default {{
    border: 1px solid {accent};
}}
/* FIBR-0185 — Home's Alerts button. Filled with the theme's attention colour while
   alerts are outstanding; disabled (none outstanding) it sits quietly, like any
   other inert control. The ID selector outranks the plain QPushButton rules above,
   so the fill survives hover. */
QPushButton#alerts_button {{
    background: {attention};
    color: {attention_text};
    border: 1px solid {attention};
}}
QPushButton#alerts_button:disabled {{
    background: {base};
    color: {muted};
    border: 1px solid {border};
}}
QGroupBox {{
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 8px;
}}
QAbstractItemView {{
    background: {base};
    alternate-background-color: {alt_base};
    border: 1px solid {border};
    border-radius: 6px;
    gridline-color: {border};
    selection-background-color: {accent};
    selection-color: {hi_text};
}}
QAbstractItemView::item {{
    padding: 2px 4px;
}}
QAbstractItemView::item:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {accent_soft}, stop:1 {hover_2});
    color: {text};
}}
QAbstractItemView::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {accent}, stop:1 {selected_2});
    color: {hi_text};
}}
QHeaderView::section {{
    background: {window};
    color: {muted};
    border: 0px;
    border-bottom: 1px solid {border};
    padding: 4px 6px;
}}
QTabBar::tab {{
    background: {window};
    color: {muted};
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 12px;
}}
QTabBar::tab:selected {{
    color: {text};
    border-bottom: 2px solid {accent};
}}
QTabBar::tab:hover {{
    color: {text};
}}
"""


def polish_item_views(root: QWidget) -> None:
    """Enable ``setAlternatingRowColors(True)`` on every ``QAbstractItemView``
    descendant of ``root`` (INV-11) — the one call that turns the QSS
    ``alternate-background-color`` into visible stripes across all the tab views. A
    ``root`` with no item-view descendants is a defined no-op."""
    for view in root.findChildren(QAbstractItemView):
        view.setAlternatingRowColors(True)


# --------------------------------------------------------------------------- #
# The controller (INV-6/7, D3)
# --------------------------------------------------------------------------- #
class ThemeController(QObject):
    """Owns the theme mode, applies themes, and follows the OS scheme live while in
    ``"system"`` mode (D3). Parented to the ``QApplication`` so it (and its
    ``colorSchemeChanged`` connection) live for the app's lifetime."""

    themeChanged = Signal()

    def __init__(self, app: QApplication):
        super().__init__(app)  # parent to app for lifetime (D3)
        self._app = app
        self._mode = "system"
        app.styleHints().colorSchemeChanged.connect(self._on_color_scheme_changed)

    def current_mode(self) -> str:
        """The active mode — a theme id or ``"system"``. Its consumer is INV-7's
        post-slot ``== "system"`` assertion, which falsifies a mode-pinning bug."""
        return self._mode

    def _current_scheme(self) -> Qt.ColorScheme:
        """The OS colour scheme — the single monkeypatchable forcing point the
        follow-system resolution reads (INV-7)."""
        return self._app.styleHints().colorScheme()

    def _resolve(self, mode: str) -> str:
        """A concrete theme id for ``mode``: ``"system"`` resolves to the default
        light/dark theme by the OS scheme (``Unknown`` -> dark, preserving the app's
        historical dark default, D5); a pinned id resolves to itself."""
        if mode == "system":
            if self._current_scheme() == Qt.ColorScheme.Light:
                return DEFAULT_LIGHT
            return DEFAULT_DARK
        return mode

    def set_theme(self, theme_id: str, *, persist: bool = True) -> None:
        """Apply ``theme_id`` (a theme id or ``"system"``): install Fusion + the
        resolved theme's palette + its stylesheet, then emit ``themeChanged``. An
        unknown id (not a theme, not ``"system"``) normalises the **mode** to
        ``"system"`` (D3), so a bad value can't leave the app on a resolved theme
        that stops tracking OS flips. Persist is best-effort (D4)."""
        if theme_id != "system" and theme_id not in THEMES:
            theme_id = "system"
        self._mode = theme_id
        tokens = THEMES[self._resolve(theme_id)].tokens
        self._app.setStyle("Fusion")
        self._app.setPalette(build_palette(tokens))
        self._app.setStyleSheet(build_stylesheet(tokens))
        self.themeChanged.emit()
        if persist:
            # Best-effort (D4): the look already applied; a pref that can't be
            # written (unwritable INI, etc.) must never crash the caller — e.g. the
            # Settings currentIndexChanged slot. It reverts to the last-saved value
            # next launch. Presentation-only (INV-12), not a global-rule-§1 swallow.
            with contextlib.suppress(Exception):
                save_theme_pref(theme_id)

    @Slot()
    def _on_color_scheme_changed(self) -> None:
        """Live follow-system: re-resolve + re-apply on an OS light/dark flip, but
        **only** while in ``"system"`` mode — a pinned theme ignores OS flips. The
        re-apply is mode-preserving (``set_theme("system", ...)`` re-resolves via
        ``_current_scheme()`` and leaves ``_mode == "system"``), so live-follow keeps
        tracking after the first flip (INV-7). Declared ``@Slot()`` with no params —
        PySide6 drops the signal's ``Qt.ColorScheme`` argument, so both the live
        signal and a zero-arg test call fire it."""
        if self._mode == "system":
            self.set_theme("system", persist=False)
