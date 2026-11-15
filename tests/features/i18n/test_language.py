"""FIBR-0017 — the translation pipeline: catalogs, loading, and switching live.

Enforces ``docs/specs/FIBR-0017-translation-pipeline.md`` INV-1 to INV-10. No
real catalog ships, so the GUI legs run on a PSEUDO catalog: every source text
``lupdate`` extracts from the tree, translated as ``⟦text⟧`` and compiled with
``lrelease`` once per session under each language a test needs. Built per
session, it cannot go stale the way a committed fixture would.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QLibraryInfo, QLocale, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTabBar,
    QWidget,
)

from conftest import _PW
from finbreak import paths as finbreak_paths
from finbreak.models import MonthSummary, MonthVerdict
from finbreak.services.auth import AuthService
from finbreak.services.transactions import to_display_decimal
from finbreak.ui import language
from finbreak.ui._amount import _format_amount
from finbreak.ui.main_window import MainWindow
from finbreak.ui.month_summary import MonthSummaryStrip
from finbreak.ui.settings import SettingsDialog

pytestmark = pytest.mark.features

_ROOT = Path(__file__).resolve().parents[3]
_PSEUDO_LANGS = ("fr", "pt", "zh_CN", "ar")
_SCRIPT = "scripts/update-translations.sh"


# --------------------------------------------------------------------------- #
# The pseudo catalog
# --------------------------------------------------------------------------- #
def _qt_tool(name: str) -> str:
    """A PySide6 tool beside the running interpreter, else on PATH."""
    sibling = Path(sys.executable).parent / name
    if sibling.is_file():
        return str(sibling)
    found = shutil.which(name)
    assert found is not None, f"{name} is not installed beside {sys.executable}"
    return found


def _tool_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{Path(_qt_tool('pyside6-lupdate')).parent}{os.pathsep}{env['PATH']}"
    return env


def _tracked(root: Path, *patterns: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", *patterns],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return out.split("\n")[:-1] if out else []


@dataclass(frozen=True)
class Pseudo:
    directory: Path
    sources: frozenset[str]


@pytest.fixture(scope="session")
def pseudo(tmp_path_factory) -> Pseudo:
    work = tmp_path_factory.mktemp("pseudo_i18n")
    ts = work / "source.ts"
    subprocess.run(
        [_qt_tool("pyside6-lupdate"), "-no-obsolete", "-locations", "none"]
        + _tracked(_ROOT, "src/finbreak/*.py")
        + ["-ts", str(ts)],
        cwd=_ROOT,
        check=True,
        capture_output=True,
    )
    tree = ET.parse(ts)
    root = tree.getroot()
    sources: set[str] = set()
    for message in root.iter("message"):
        source = message.findtext("source") or ""
        sources.add(source)
        translation = message.find("translation")
        assert translation is not None
        translation.attrib.pop("type", None)  # lrelease drops "unfinished"
        if message.get("numerus") == "yes":
            translation.text = None
            for child in list(translation):
                translation.remove(child)
            for _ in range(6):  # Arabic's count; lrelease ignores any surplus
                ET.SubElement(translation, "numerusform").text = f"⟦{source}⟧"
        else:
            translation.text = f"⟦{source}⟧"
    catalogs = work / "catalogs"
    catalogs.mkdir()
    for lang in _PSEUDO_LANGS:
        root.set("language", lang)
        lang_ts = work / f"finbreak_{lang}.ts"
        tree.write(lang_ts, encoding="utf-8", xml_declaration=True)
        subprocess.run(
            [
                _qt_tool("pyside6-lrelease"),
                str(lang_ts),
                "-qm",
                str(catalogs / f"finbreak_{lang}.qm"),
            ],
            check=True,
            capture_output=True,
        )
    assert len(sources) > 100, "lupdate found the tree's strings"
    return Pseudo(catalogs, frozenset(sources))


@pytest.fixture
def catalogs(monkeypatch, pseudo) -> Pseudo:
    monkeypatch.setattr(language, "CATALOG_DIR", pseudo.directory)
    return pseudo


@pytest.fixture
def controller(qapp, monkeypatch) -> Iterator[language.LanguageController]:
    """A controller whose translators, active language and layout direction are
    undone after the test, so a pseudo language cannot leak into a sibling."""
    monkeypatch.setattr(language, "_active", language._active)
    direction = qapp.layoutDirection()
    ctrl = language.LanguageController(qapp)
    yield ctrl
    ctrl._uninstall()
    qapp.setLayoutDirection(direction)
    ctrl.setParent(None)
    ctrl.deleteLater()


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _pump_deferred_delete() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _unlocked_window(qtbot, service, controller) -> MainWindow:
    window = MainWindow(service, language_controller=controller)
    qtbot.addWidget(window)
    window._enter_unlocked()
    window.show()
    qtbot.waitExposed(window)
    return window


def _save_language(window: MainWindow, token: str) -> None:
    """Open Settings, pick ``token`` and press Save, as the user does."""
    window._action_settings.trigger()
    dialog = window._dialog
    assert isinstance(dialog, SettingsDialog)
    combo = dialog.findChild(QComboBox, "settings_language")
    assert combo is not None
    combo.setCurrentIndex(combo.findData(token))
    box = dialog.findChild(QDialogButtonBox)
    assert box is not None
    box.button(QDialogButtonBox.StandardButton.Ok).click()
    _pump_deferred_delete()


def _visible_texts(window: MainWindow) -> list[str]:
    """Every text the user can see in the window, and every action's text."""
    texts = [window.windowTitle(), window.statusBar().currentMessage()]
    for widget in window.findChildren(QWidget):
        if not widget.isVisible():
            continue
        texts.append(widget.toolTip())
        if isinstance(widget, (QLabel, QAbstractButton)):
            texts.append(widget.text())
        if isinstance(widget, QGroupBox):
            texts.append(widget.title())
        if isinstance(widget, QLineEdit):
            texts.append(widget.placeholderText())
        if isinstance(widget, QTabBar):
            texts += [widget.tabText(i) for i in range(widget.count())]
        if isinstance(widget, QAbstractItemView) and widget.model() is not None:
            model = widget.model()
            texts += [
                str(model.headerData(c, Qt.Orientation.Horizontal) or "")
                for c in range(model.columnCount())
            ]
    for action in window.findChildren(QAction):
        texts.append(action.text())
    return [t for t in texts if t]


# --------------------------------------------------------------------------- #
# INV-1 — resolution order, never raising, never outside the catalog set
# --------------------------------------------------------------------------- #
@pytest.fixture
def pt_and_zh(tmp_path, monkeypatch, pseudo) -> Path:
    for lang in ("pt", "zh_CN"):
        name = f"finbreak_{lang}.qm"
        shutil.copy(pseudo.directory / name, tmp_path / name)
    monkeypatch.setattr(language, "CATALOG_DIR", tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    ("pref", "system", "expected"),
    [
        ("system", "pt_BR", "pt"),
        ("system", "zh_CN", "zh_CN"),
        ("system", "de_DE", "en"),
        ("system", "C", "en"),
        ("pt", "de_DE", "pt"),
        ("fr", "de_DE", "en"),  # explicit, but its catalog is missing
    ],
)
def test_INV1_resolution_order(pt_and_zh, pref, system, expected):
    got = language.resolve_language(pref, QLocale(system))
    assert got == expected
    assert got in language.available_languages()


def test_INV1_corrupt_catalog_falls_back_to_english(tmp_path, monkeypatch, controller):
    (tmp_path / "finbreak_pt.qm").write_bytes(b"not a catalog")
    monkeypatch.setattr(language, "CATALOG_DIR", tmp_path)
    controller.apply("pt")  # must not raise, and must not show a dialog
    assert controller._translators == []
    assert language.ui_locale().language() == QLocale.Language.English


# --------------------------------------------------------------------------- #
# INV-2 — the stored choice is guarded
# --------------------------------------------------------------------------- #
def _store(value: object) -> None:
    QSettings(
        str(finbreak_paths.window_settings_path()), QSettings.Format.IniFormat
    ).setValue(language.LANGUAGE_PREF_KEY, value)


def test_INV2_absent_key_is_system(pt_and_zh):
    assert language.load_language_pref() == "system"


@pytest.mark.parametrize("value", ["xx", "", 3, "fr"])  # fr: catalog removed
def test_INV2_unknown_or_removed_value_is_system(pt_and_zh, value):
    _store(value)
    assert language.load_language_pref() == "system"


@pytest.mark.parametrize("value", ["system", "pt", "en"])
def test_INV2_valid_value_round_trips(pt_and_zh, value):
    language.save_language_pref(value)
    assert language.load_language_pref() == value


# --------------------------------------------------------------------------- #
# INV-3 — the first window is already in the launch language
# --------------------------------------------------------------------------- #
class _Built(Exception):
    """Raised once the real window is built, so run() never reaches exec()."""


def test_INV3_first_window_is_translated(
    qtbot, monkeypatch, paths, catalogs, app_run_isolation
):
    from finbreak import app as app_mod

    language.save_language_pref("fr")
    built: list[MainWindow] = []

    def _build(*args, **kwargs):
        window = MainWindow(*args, **kwargs)
        qtbot.addWidget(window)
        built.append(window)
        raise _Built

    monkeypatch.setattr(app_mod, "MainWindow", _build)
    service = AuthService(*paths)  # no vault yet: the first-run dialog opens
    monkeypatch.setattr(app_mod, "AuthService", lambda *a, **k: service)
    monkeypatch.setattr(
        app_mod.single_instance, "another_instance_is_running", lambda _name: False
    )
    with pytest.raises(_Built):
        app_mod.run([])
    app = QApplication.instance()
    assert app is not None
    app.aboutToQuit.disconnect(service.on_about_to_quit)

    dialog = built[0]._dialog
    assert isinstance(dialog, QDialog)
    assert dialog.windowTitle() == "⟦Create your vault⟧"
    buttons = [b.text() for b in dialog.findChildren(QAbstractButton) if b.text()]
    assert any(text.startswith("⟦") for text in buttons), buttons
    # Cancel is Qt's own word, from qtbase_fr rather than the pseudo catalog.
    english = [t for t in buttons if t in catalogs.sources or t == "Cancel"]
    assert english == [], english


# --------------------------------------------------------------------------- #
# INV-4 — a switch from Settings leaves no old-language text
# --------------------------------------------------------------------------- #
def test_INV4_switch_leaves_no_old_text(qtbot, service, catalogs, controller):
    window = _unlocked_window(qtbot, service, controller)
    before = [t for t in _visible_texts(window) if t in catalogs.sources]
    assert before, "the walk sees source texts before the switch"

    _save_language(window, "fr")
    stale = [t for t in _visible_texts(window) if t in catalogs.sources]
    assert stale == [], f"still in the old language: {sorted(set(stale))}"
    # A rebuilt part the walk cannot see would pass it blind.
    assert window._toolbar.isVisible() and window.menuBar().isVisible()
    assert window.statusBar().isVisible()
    assert window._workspace is not None and window._workspace.isVisible()

    _save_language(window, "en")
    stale = [t for t in _visible_texts(window) if "⟦" in t]
    assert stale == [], f"still in the pseudo language: {sorted(set(stale))}"


# --------------------------------------------------------------------------- #
# INV-5 — Qt's own words follow the language
# --------------------------------------------------------------------------- #
def test_INV5_qt_strings_follow(qtbot, catalogs, controller):
    qtbase = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    assert (qtbase / "qtbase_fr.qm").is_file(), "the wheel ships qtbase_fr"
    controller.apply("fr")
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    qtbot.addWidget(box)
    text = box.button(QDialogButtonBox.StandardButton.Cancel).text()
    assert text.replace("&", "") == "Annuler"


# --------------------------------------------------------------------------- #
# INV-6 — every shipped catalog is current
# --------------------------------------------------------------------------- #
def _tree_copy(dest: Path) -> Path:
    """The files the script reads, in a fresh git index of their own."""
    for rel in [
        *_tracked(_ROOT, "src/finbreak/*.py", "src/finbreak/data/i18n/*"),
        _SCRIPT,
    ]:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_ROOT / rel, target)
    (dest / "src/finbreak/data/i18n").mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    return dest / "src/finbreak/data/i18n"


def _run_script(tree: Path, *langs: str) -> None:
    subprocess.run(
        ["bash", _SCRIPT, *langs],
        cwd=tree,
        check=True,
        capture_output=True,
        env=_tool_env(),
    )


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def test_INV6_catalogs_are_current(tmp_path):
    shipped = _ROOT / "src/finbreak/data/i18n"
    committed = _snapshot(shipped) if shipped.is_dir() else {}
    i18n = _tree_copy(tmp_path)
    _run_script(tmp_path)
    assert _snapshot(i18n) == committed, "re-run scripts/update-translations.sh"

    # The check itself must see a stale catalog, or an empty set passes blind.
    _run_script(tmp_path, "pt")
    fresh = _snapshot(i18n)
    ts = i18n / "finbreak_pt.ts"
    ts.write_text(
        ts.read_text(encoding="utf-8").replace(
            "<context>",
            "<context>\n    <message>\n        <source>FIBR-0017 planted</source>"
            "\n        <translation>x</translation>\n    </message>",
            1,
        ),
        encoding="utf-8",
    )
    planted = _snapshot(i18n)
    assert planted != fresh
    _run_script(tmp_path)
    assert _snapshot(i18n) != planted, "the stale string was not removed"
    assert _snapshot(i18n) == fresh


# --------------------------------------------------------------------------- #
# INV-7 — every shipped .qm reaches the wheel
# --------------------------------------------------------------------------- #
def test_INV7_qm_is_package_data():
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = pyproject["tool"]["setuptools"]["package-data"]["finbreak"]
    package = _ROOT / "src/finbreak"
    shipped = [
        qm.relative_to(package).as_posix()
        for qm in language.CATALOG_DIR.glob("finbreak_*.qm")
    ]
    for rel in [*shipped, "data/i18n/finbreak_es.qm"]:  # one future catalog too
        assert any(fnmatch(rel, g) for g in globs), f"{rel} is not package-data"


# --------------------------------------------------------------------------- #
# INV-8 — the picker
# --------------------------------------------------------------------------- #
def test_INV8_picker_offers_system_then_each_language(
    qtbot, service, catalogs, controller
):
    dialog = SettingsDialog(service, "ZAR", language_controller=controller)
    qtbot.addWidget(dialog)
    combo = dialog.findChild(QComboBox, "settings_language")
    assert combo is not None
    datas = [combo.itemData(i) for i in range(combo.count())]
    assert datas == ["system", *language.available_languages()]
    assert "fr" in datas
    texts = [combo.itemText(i) for i in range(1, combo.count())]
    labels = dict(zip(datas[1:], texts, strict=True))
    # Each under its own name; English as plain "English", not "American English"
    # (QLocale("en")'s native name), which misnames it for every other region.
    assert labels["en"] == "English"
    assert labels["fr"] == "français"
    assert combo.currentData() == "system"


def test_INV8_picker_saving_a_new_choice_writes_and_switches(
    qtbot, service, catalogs, controller
):
    window = _unlocked_window(qtbot, service, controller)
    fired: list[int] = []
    controller.languageChanged.connect(lambda: fired.append(1))
    _save_language(window, "fr")
    assert language.load_language_pref() == "fr"
    assert fired == [1]
    assert window.windowTitle() == "⟦finbreak⟧"


def test_INV8_picker_saving_the_same_choice_does_neither(
    qtbot, service, catalogs, controller, monkeypatch
):
    window = _unlocked_window(qtbot, service, controller)
    workspace = window._workspace
    writes: list[str] = []
    monkeypatch.setattr(language, "save_language_pref", writes.append)
    fired: list[int] = []
    controller.languageChanged.connect(lambda: fired.append(1))
    _save_language(window, "system")
    assert writes == [] and fired == []
    assert window._workspace is workspace, "the window was not rebuilt"


# --------------------------------------------------------------------------- #
# INV-9 — month names follow the language; separators do not
# --------------------------------------------------------------------------- #
def test_INV9_month_name_follows_language(qtbot, controller):
    previous = QLocale()
    QLocale.setDefault(QLocale("de_DE"))
    try:
        controller.apply("en")
        strip = MonthSummaryStrip()
        qtbot.addWidget(strip)
        summary = MonthSummary(
            month="2026-03",
            partial=False,
            days=31,
            exponent=2,
            show_year=False,
            verdict=MonthVerdict.HIGHER,
            spend_minor=1234000,
            baseline_minor=1000000,
            movement_minor=234000,
            cause=None,
            residual_minor=None,
        )
        strip.set_summary(summary, "ZAR")
        label = strip.findChild(QLabel, "month_summary_text")
        assert label is not None
        text = label.text()
        amount = _format_amount(to_display_decimal(234000, 2), "ZAR")
    finally:
        QLocale.setDefault(previous)
    assert "March" in text and "März" not in text
    assert "2.340,00" in amount and amount in text, "de_DE separators kept"


# --------------------------------------------------------------------------- #
# INV-10 — a right-to-left language mirrors the layout, and back
# --------------------------------------------------------------------------- #
def test_INV10_direction_follows(qapp, catalogs, controller):
    # Set once, as a startup line would. Left at Auto, Qt reads qtbase_ar's own
    # direction entry and flips by itself, hiding an apply() that sets nothing.
    qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    controller.apply("ar")
    assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
    controller.apply("en")
    assert qapp.layoutDirection() == Qt.LayoutDirection.LeftToRight
