"""FIBR-0127 — app-wide theme system (six finance themes + follow-system).

Enforces tests/features/theme/spec.md. Pure legs (registry / palette / stylesheet /
pref / resolution / presentation-only) run headless against ``ui/theme.py``; the
GUI legs (INV-1/6/8/9/10/11) drive ``run()`` / the shell / ``SettingsDialog`` via
``qtbot``. Every theme test runs under ``theme_isolation`` so an applied palette
can't leak into a sibling suite (D12). No network, no real data.
"""

import dataclasses
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QTableView, QWidget

from conftest import _PW
from finbreak import paths
from finbreak.services.auth import AuthService
from finbreak.ui import theme
from finbreak.ui.main_window import MainWindow
from finbreak.ui.settings import SettingsDialog

pytestmark = pytest.mark.features

_LIGHT = ("ledger", "parchment", "mint")
_DARK = ("midnight", "graphite", "emerald")
_ALL_IDS = {"system", *_LIGHT, *_DARK}


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def theme_isolation():
    """Snapshot & restore the shared qapp's palette / style / stylesheet (D12), so
    an applied theme can't leak into a sibling test. Restore the style by NAME
    (``style()`` is a borrowed pointer ``setStyle`` deletes) — style first (a
    ``setStyle`` re-polish can reset the palette), then palette, then stylesheet."""
    app = QApplication.instance()
    style_name = app.style().objectName()
    palette = QPalette(app.palette())
    stylesheet = app.styleSheet()
    yield
    if style_name:
        app.setStyle(style_name)
    app.setPalette(palette)
    app.setStyleSheet(stylesheet)


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to latest
    yield svc
    svc.lock()


def _window_lightness(app: QApplication) -> float:
    return app.palette().color(QPalette.ColorRole.Window).lightnessF()


_SYNTH_BASE = theme.ThemeTokens(
    window=QColor("#202020"),
    base=QColor("#181818"),
    alt_base=QColor("#242424"),
    text=QColor("#e0e0e0"),
    muted_text=QColor("#808080"),
    accent=QColor("#3366cc"),
    accent_soft=QColor("#5588ee"),
    border=QColor("#333333"),
    is_dark=True,
)


def _synthetic_tokens(**overrides) -> theme.ThemeTokens:
    return dataclasses.replace(_SYNTH_BASE, **overrides)


class _Sentinel(Exception):
    """Raised by the INV-1 recorder so run() never reaches show()/exec()."""


# --------------------------------------------------------------------------- #
# INV-1 — the theme is applied before MainWindow (the locked first window is themed)
# --------------------------------------------------------------------------- #
def test_INV1_theme_applied_before_window(qtbot, monkeypatch, theme_isolation):
    from finbreak import app as app_mod

    theme.save_theme_pref("midnight")  # pinned -> a deterministic expected palette
    recorded: dict[str, object] = {}

    class _Recorder:
        def __init__(self, *a, **k):
            app = QApplication.instance()
            recorded["palette"] = QPalette(app.palette())
            recorded["stylesheet"] = app.styleSheet()
            raise _Sentinel

    monkeypatch.setattr(app_mod, "MainWindow", _Recorder)
    monkeypatch.setattr(app_mod, "AuthService", lambda *a, **k: MagicMock())

    with pytest.raises(_Sentinel):
        app_mod.run([])

    expected = theme.build_palette(theme.THEMES["midnight"].tokens)
    got = recorded["palette"]
    assert isinstance(got, QPalette)
    assert got.color(QPalette.ColorRole.Window) == expected.color(
        QPalette.ColorRole.Window
    )
    assert got.color(QPalette.ColorRole.Highlight) == expected.color(
        QPalette.ColorRole.Highlight
    )
    assert recorded["stylesheet"] != "", "the window is built after the theme applies"


# --------------------------------------------------------------------------- #
# INV-2 — the pref lives in the non-vault INI, read with a guarded fallback
# --------------------------------------------------------------------------- #
def test_INV2_absent_returns_system():
    assert theme.load_theme_pref() == "system"


def test_INV2_known_id_round_trips():
    theme.save_theme_pref("emerald")
    assert theme.load_theme_pref() == "emerald"


def test_INV2_unknown_value_returns_system():
    settings = QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)
    settings.setValue(theme.THEME_PREF_KEY, "nonsense")
    settings.sync()
    assert theme.load_theme_pref() == "system"


def test_INV2_save_load_round_trip():
    theme.save_theme_pref("graphite")
    assert theme.load_theme_pref() == "graphite"


def test_INV2_system_is_a_valid_stored_value():
    theme.save_theme_pref("system")
    assert theme.load_theme_pref() == "system"


# --------------------------------------------------------------------------- #
# INV-3 — a theme is fully defined by its tokens (registry integrity)
# --------------------------------------------------------------------------- #
def test_INV3_exactly_the_six_ids():
    assert set(theme.THEMES) == {*_LIGHT, *_DARK}


def test_INV3_every_token_is_a_valid_colour():
    fields = (
        "window",
        "base",
        "alt_base",
        "text",
        "muted_text",
        "accent",
        "accent_soft",
        "border",
    )
    for tid, tdef in theme.THEMES.items():
        for field in fields:
            colour = getattr(tdef.tokens, field)
            assert isinstance(colour, QColor) and colour.isValid(), f"{tid}.{field}"
        assert isinstance(tdef.tokens.is_dark, bool)


def test_INV3_is_dark_agrees_with_window_lightness():
    for tid in _LIGHT:
        tokens = theme.THEMES[tid].tokens
        assert tokens.is_dark is False
        assert tokens.window.lightnessF() >= 0.5, tid
    for tid in _DARK:
        tokens = theme.THEMES[tid].tokens
        assert tokens.is_dark is True
        assert tokens.window.lightnessF() < 0.5, tid


def test_INV3_defaults_are_in_the_registry():
    assert theme.DEFAULT_LIGHT == "ledger"
    assert theme.DEFAULT_DARK == "midnight"
    assert theme.THEMES[theme.DEFAULT_LIGHT].tokens.is_dark is False
    assert theme.THEMES[theme.DEFAULT_DARK].tokens.is_dark is True


# --------------------------------------------------------------------------- #
# INV-4 — build_palette maps every token to a role; HighlightedText is computed
# --------------------------------------------------------------------------- #
def test_INV4_full_role_map_light_and_dark():
    R = QPalette.ColorRole
    G = QPalette.ColorGroup
    for tid in ("ledger", "midnight"):
        t = theme.THEMES[tid].tokens
        p = theme.build_palette(t)
        assert p.color(R.Window) == t.window
        assert p.color(R.Button) == t.window
        for role in (R.WindowText, R.Text, R.ButtonText, R.ToolTipText):
            assert p.color(role) == t.text, (tid, role)
        assert p.color(R.Base) == t.base
        assert p.color(R.ToolTipBase) == t.base
        assert p.color(R.AlternateBase) == t.alt_base
        assert p.color(R.PlaceholderText) == t.muted_text
        assert p.color(G.Disabled, R.Text) == t.muted_text
        assert p.color(G.Disabled, R.WindowText) == t.muted_text
        assert p.color(R.Highlight) == t.accent
        assert p.color(R.Link) == t.accent_soft
        assert p.color(R.Mid) == t.border
        assert p.color(R.Dark) == t.border


def test_INV4_highlighted_text_computed_both_branches():
    # The branch turns on ACCENT lightness, not theme light/dark — force both.
    dark_accent = _synthetic_tokens(accent=QColor("#0d0d0d"))  # L < 0.5
    light_accent = _synthetic_tokens(accent=QColor("#f2f2f2"))  # L >= 0.5
    hi_on_dark = theme.build_palette(dark_accent).color(
        QPalette.ColorRole.HighlightedText
    )
    hi_on_light = theme.build_palette(light_accent).color(
        QPalette.ColorRole.HighlightedText
    )
    assert hi_on_dark.lightnessF() > 0.5, "dark accent -> near-white text"
    assert hi_on_light.lightnessF() < 0.5, "light accent -> near-black text"


# --------------------------------------------------------------------------- #
# INV-5 — build_stylesheet is parameterised by the tokens
# --------------------------------------------------------------------------- #
def test_INV5_stylesheet_contains_token_hex():
    t = theme.THEMES["ledger"].tokens
    ss = theme.build_stylesheet(t)
    assert isinstance(ss, str) and ss.strip()
    assert t.accent.name() in ss
    assert t.accent_soft.name() in ss
    assert t.alt_base.name() in ss


def test_INV5_different_themes_differ():
    a = theme.build_stylesheet(theme.THEMES["ledger"].tokens)
    b = theme.build_stylesheet(theme.THEMES["emerald"].tokens)
    assert a != b


# --------------------------------------------------------------------------- #
# INV-6 — applying installs Fusion + palette + stylesheet and announces the change
# --------------------------------------------------------------------------- #
def test_INV6_apply_installs_everything_and_emits(qtbot, monkeypatch, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    fired: list[int] = []
    controller.themeChanged.connect(lambda: fired.append(1))

    names: list[object] = []
    orig = app.setStyle
    monkeypatch.setattr(app, "setStyle", lambda n: (names.append(n), orig(n))[1])

    controller.set_theme("ledger")
    assert _window_lightness(app) > 0.5, "ledger is light"
    assert app.styleSheet() != ""
    assert fired == [1], "themeChanged fired once"
    assert any(str(n).lower() == "fusion" for n in names), "Fusion requested"

    controller.set_theme("midnight")
    assert _window_lightness(app) < 0.5, "midnight flips the palette dark"


# --------------------------------------------------------------------------- #
# INV-7 — Follow system resolves + follows OS flips live; a pinned theme does not
# --------------------------------------------------------------------------- #
def test_INV7_system_resolves_by_scheme(qtbot, monkeypatch, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)

    monkeypatch.setattr(controller, "_current_scheme", lambda: Qt.ColorScheme.Dark)
    controller.set_theme("system")
    assert _window_lightness(app) < 0.5, "system + Dark -> Midnight"
    assert controller.current_mode() == "system"

    monkeypatch.setattr(controller, "_current_scheme", lambda: Qt.ColorScheme.Light)
    controller.set_theme("system")
    assert _window_lightness(app) > 0.5, "system + Light -> Ledger"


def test_INV7_unknown_scheme_defaults_dark(qtbot, monkeypatch, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    monkeypatch.setattr(controller, "_current_scheme", lambda: Qt.ColorScheme.Unknown)
    controller.set_theme("system")
    assert _window_lightness(app) < 0.5, "Unknown -> dark default"


def test_INV7_live_follow_flips_and_keeps_system_mode(
    qtbot, monkeypatch, theme_isolation
):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    scheme = {"v": Qt.ColorScheme.Dark}
    monkeypatch.setattr(controller, "_current_scheme", lambda: scheme["v"])

    controller.set_theme("system")
    assert _window_lightness(app) < 0.5
    assert controller.current_mode() == "system"

    # OS flips to light -> the slot re-applies, WITHOUT leaving system mode.
    scheme["v"] = Qt.ColorScheme.Light
    controller._on_color_scheme_changed()
    assert _window_lightness(app) > 0.5, "live follow tracked the flip"
    assert controller.current_mode() == "system", "mode stays system (live-follow on)"

    # A second flip proves tracking continues (not a one-shot).
    scheme["v"] = Qt.ColorScheme.Dark
    controller._on_color_scheme_changed()
    assert _window_lightness(app) < 0.5
    assert controller.current_mode() == "system"


def test_INV7_pinned_theme_slot_is_a_noop(qtbot, monkeypatch, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    monkeypatch.setattr(controller, "_current_scheme", lambda: Qt.ColorScheme.Dark)
    controller.set_theme("emerald")  # a pinned dark theme
    pinned = app.palette().color(QPalette.ColorRole.Window)

    monkeypatch.setattr(controller, "_current_scheme", lambda: Qt.ColorScheme.Light)
    controller._on_color_scheme_changed()  # a no-op while a theme is pinned
    assert app.palette().color(QPalette.ColorRole.Window) == pinned
    assert controller.current_mode() == "emerald"


# --------------------------------------------------------------------------- #
# D3 — an unknown id normalises the MODE to system
# --------------------------------------------------------------------------- #
def test_D3_unknown_id_normalises_mode_to_system(qtbot, monkeypatch, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    monkeypatch.setattr(controller, "_current_scheme", lambda: Qt.ColorScheme.Dark)
    controller.set_theme("bogus-theme")
    assert controller.current_mode() == "system"
    assert _window_lightness(app) < 0.5, "resolved via system (Dark)"


# --------------------------------------------------------------------------- #
# D4 — a failing persist leaves the theme applied and does not raise
# --------------------------------------------------------------------------- #
def test_D4_failed_persist_still_applies(qtbot, monkeypatch, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)

    def boom(_id):
        raise OSError("read-only INI")

    monkeypatch.setattr(theme, "save_theme_pref", boom)
    controller.set_theme("mint")  # must not raise
    assert _window_lightness(app) > 0.5, "mint applied despite the persist failure"


# --------------------------------------------------------------------------- #
# INV-12 — the theme system is presentation-only (no vault state)
# --------------------------------------------------------------------------- #
def test_INV12_no_vault_reference(qtbot, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    controller.set_theme("graphite")  # no AuthService / Vault anywhere in scope
    assert app.styleSheet() != ""
    assert not hasattr(controller, "vault")
    assert not hasattr(controller, "_service")


# --------------------------------------------------------------------------- #
# INV-8 — the Settings picker is immediate-apply; opening it changes nothing
# --------------------------------------------------------------------------- #
def test_INV8_open_with_pinned_pref_makes_zero_saves(
    qtbot, service, monkeypatch, theme_isolation
):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    theme.save_theme_pref("emerald")
    controller.set_theme("emerald")
    before = app.palette().color(QPalette.ColorRole.Window)

    writes: list[str] = []
    monkeypatch.setattr(theme, "save_theme_pref", lambda i: writes.append(i))

    dialog = SettingsDialog(service, "ZAR", theme_controller=controller)
    qtbot.addWidget(dialog)

    assert writes == [], "opening Settings must not persist a theme"
    assert app.palette().color(QPalette.ColorRole.Window) == before


def test_INV8_selecting_applies_and_persists_live(qtbot, service, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    theme.save_theme_pref("ledger")
    controller.set_theme("ledger")

    dialog = SettingsDialog(service, "ZAR", theme_controller=controller)
    qtbot.addWidget(dialog)
    combo = dialog.findChild(QComboBox, "settings_theme")
    assert combo is not None

    combo.setCurrentIndex(combo.findData("midnight"))
    assert _window_lightness(app) < 0.5, "selection applied live, no Save click"
    assert theme.load_theme_pref() == "midnight", "selection persisted immediately"


# --------------------------------------------------------------------------- #
# INV-9 — the picker offers Follow-system + six themes, grouped, preselected
# --------------------------------------------------------------------------- #
def test_INV9_picker_contents_and_grouping(qtbot, service, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    theme.save_theme_pref("graphite")
    controller.set_theme("graphite")

    dialog = SettingsDialog(service, "ZAR", theme_controller=controller)
    qtbot.addWidget(dialog)
    combo = dialog.findChild(QComboBox, "settings_theme")
    assert combo is not None

    datas = [combo.itemData(i) for i in range(combo.count())]
    assert set(datas) == _ALL_IDS
    assert datas[0] == "system", "Follow system leads the list"
    light_positions = [datas.index(x) for x in _LIGHT]
    dark_positions = [datas.index(x) for x in _DARK]
    assert max(light_positions) < min(dark_positions), "light group before dark"
    assert combo.currentData() == "graphite", "preselected to the current pref"


def test_INV9_no_picker_without_controller(qtbot, service):
    dialog = SettingsDialog(service, "ZAR")  # no controller -> no theme row
    qtbot.addWidget(dialog)
    assert dialog.findChild(QComboBox, "settings_theme") is None


# --------------------------------------------------------------------------- #
# INV-10 — toolbar glyphs re-tint on a theme change
# --------------------------------------------------------------------------- #
def test_INV10_toolbar_icons_retint_on_theme_change(qtbot, service, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    controller.set_theme("ledger")  # light

    window = MainWindow(service, theme_controller=controller)
    qtbot.addWidget(window)
    window._enter_unlocked()

    assert "home" in window._icon_actions, "icon-bearing actions are recorded"
    action = window._icon_actions["home"]
    key_light = action.icon().cacheKey()

    controller.set_theme("midnight")  # dark -> a live re-tint
    key_dark = action.icon().cacheKey()
    assert key_light != key_dark, "the glyph re-tinted light -> dark"


# --------------------------------------------------------------------------- #
# INV-11 — grid views show row highlighting (striping + hover/selection QSS)
# --------------------------------------------------------------------------- #
def test_INV11_polish_enables_alternating_rows(qtbot, service, theme_isolation):
    app = QApplication.instance()
    controller = theme.ThemeController(app)
    controller.set_theme("ledger")

    window = MainWindow(service, theme_controller=controller)
    qtbot.addWidget(window)
    window._enter_unlocked()

    tables = window._workspace.findChildren(QTableView)
    assert tables, "the workspace has table views"
    assert all(tv.alternatingRowColors() for tv in tables), "all views striped"


def test_INV11_polish_item_views_is_a_noop_without_views(qtbot, theme_isolation):
    root = QWidget()
    qtbot.addWidget(root)
    theme.polish_item_views(root)  # no item-view descendants -> defined no-op


def test_INV11_stylesheet_has_row_highlight_selectors():
    ss = theme.build_stylesheet(theme.THEMES["midnight"].tokens)
    assert "::item:hover" in ss
    assert "::item:selected" in ss
    assert theme.THEMES["midnight"].tokens.accent_soft.name() in ss
