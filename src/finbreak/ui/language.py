"""The active UI language: catalogs, the stored choice, and live switching (FIBR-0017).

A translation is a compiled ``finbreak_<lang>.qm`` in ``CATALOG_DIR``; dropping
one there is what makes the language appear in the Settings picker. English is the
source language and has no catalog.

The choice is stored **outside the encrypted vault**, in the plaintext window INI
beside the theme preference, because the unlock screen is shown before the vault
opens. ``"system"`` (FIBR-0129's sentinel) means "follow the operating system",
resolved by FIBR-0209's order in ``resolve_language``; an unknown language falls
back to English silently.

``LanguageController.apply`` swaps finbreak's and Qt's own translators and sets
the layout direction. It does not re-translate anything already built: Qt never
does, so ``MainWindow`` rebuilds itself on ``languageChanged``
(``docs/specs/FIBR-0017-translation-pipeline.md`` § 4.4).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QLibraryInfo,
    QLocale,
    QObject,
    QSettings,
    QTranslator,
    Signal,
)
from PySide6.QtWidgets import QApplication

from finbreak import paths

LANGUAGE_PREF_KEY = "language"
LANGUAGE_SYSTEM = "system"
SOURCE_LANGUAGE = "en"
CATALOG_DIR = Path(__file__).parent.parent / "data" / "i18n"

# The language the installed translators speak. Module state rather than a
# controller attribute so ``ui_locale()`` needs no reference to the controller.
_active = SOURCE_LANGUAGE


def _settings() -> QSettings:
    return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)


def available_languages() -> list[str]:
    """English, then each language with a ``finbreak_<lang>.qm`` in ``CATALOG_DIR``."""
    found = sorted(
        qm.stem.removeprefix("finbreak_")
        for qm in CATALOG_DIR.glob("finbreak_*.qm")
        if qm.is_file()
    )
    return [SOURCE_LANGUAGE, *(lang for lang in found if lang != SOURCE_LANGUAGE)]


def load_language_pref() -> str:
    """The stored choice, only if it is ``"system"`` or an available language;
    anything else, a removed language's token included, is ``"system"``."""
    value = _settings().value(LANGUAGE_PREF_KEY)
    if isinstance(value, str) and (
        value == LANGUAGE_SYSTEM or value in available_languages()
    ):
        return value
    return LANGUAGE_SYSTEM


def save_language_pref(token: str) -> None:
    _settings().setValue(LANGUAGE_PREF_KEY, token)


def resolve_language(pref: str, system: QLocale) -> str:
    """FIBR-0209's order: an explicit available token; then the system locale's
    full name (``pt_BR``); then its bare language (``pt``); then English."""
    available = available_languages()
    if pref != LANGUAGE_SYSTEM:
        return pref if pref in available else SOURCE_LANGUAGE
    full = system.name()
    for candidate in (full, full.split("_")[0]):
        if candidate in available:
            return candidate
    return SOURCE_LANGUAGE


def ui_locale() -> QLocale:
    """The active language with the system's territory, for WORDS only: month
    names and reading direction. Numbers and dates keep ``QLocale()``, whose
    "System default" is the system (spec § 3)."""
    active = QLocale(_active)
    return QLocale(active.language(), active.script(), QLocale().territory())


class LanguageController(QObject):
    """Owns the installed translators; parented to the ``QApplication``."""

    languageChanged = Signal()

    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app
        self._translators: list[QTranslator] = []

    def apply(self, pref: str) -> None:
        """Resolve ``pref``, swap the translators, set the layout direction, emit.
        A catalog that will not load leaves the app in English, with no dialog."""
        global _active
        lang = resolve_language(pref, QLocale.system())
        self._uninstall()
        if lang != SOURCE_LANGUAGE:
            ours = QTranslator(self._app)
            if ours.load(str(CATALOG_DIR / f"finbreak_{lang}.qm")):
                self._install(ours)
                self._install_qtbase(lang)
            else:
                ours.deleteLater()
                lang = SOURCE_LANGUAGE
        _active = lang
        self._app.setLayoutDirection(ui_locale().textDirection())
        self.languageChanged.emit()

    def _install_qtbase(self, lang: str) -> None:
        # Qt's own words (OK, Cancel, the text-edit menus). Not every language
        # has a catalog in the wheel; then they stay English (spec § 6).
        directory = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
        qtbase = directory / f"qtbase_{lang}.qm"
        translator = QTranslator(self._app)
        if qtbase.is_file() and translator.load(str(qtbase)):
            self._install(translator)
        else:
            translator.deleteLater()

    def _install(self, translator: QTranslator) -> None:
        self._app.installTranslator(translator)
        self._translators.append(translator)

    def _uninstall(self) -> None:
        for translator in self._translators:
            self._app.removeTranslator(translator)
            translator.deleteLater()
        self._translators = []
