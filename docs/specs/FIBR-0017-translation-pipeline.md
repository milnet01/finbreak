<!-- ants-spec-format: 1 -->
# FIBR-0017 — the translation pipeline: catalogs, loading, and switching language live

**Status:** accepted (2026-11-15). No contract review: the spec is owed for a
design choice and three subsystems, and what it pins is cheap to change
(rule 14).
**Kind:** implement.
**Source:** ROADMAP FIBR-0017 (user-request-2026-07-01).
**Pairs with:** FIBR-0129 (the `language` setting and the Settings picker),
FIBR-0209 (which language a launch picks). Each keeps its roadmap bullet as its
contract; this spec cites them and builds on them.

**Layman:** This builds everything finbreak needs to show itself in another
language and to switch language without restarting. It ships in English only;
the other languages are added once it is settled who writes them.

## 1. Goal

After this ships, a translation is a file dropped into the app. Adding
`finbreak_es.ts` and its compiled `finbreak_es.qm` is all it takes to make
Spanish appear in the Settings picker. Choosing it changes every screen at once,
with no restart. A launch picks the right language before the first window
shows. No non-English catalog ships with this item.

## 2. Problem

1. **Nothing loads a translation.** Every user-facing string is a literal
   inside `tr()` or `QCoreApplication.translate()`, which `tests/features/i18n/`
   enforces. But no code installs a `QTranslator`, no catalog exists, and no
   script builds one. `pyside6-lupdate` over every tracked `src/finbreak/*.py`
   finds 654 source texts in 38 contexts, 15 of them plural forms (measured
   2026-11-15: `pyside6-lupdate $(git ls-files 'src/finbreak/*.py') -ts
   <scratch>/finbreak_xx.ts`, then `grep -c '<message'`, `grep -c '<context>'`
   and `grep -c 'numerus="yes"'` over the result).
2. **No screen re-translates.** Qt does not re-translate a widget that is
   already built. `docs/standards/coding.md` § 5.2 asks each widget to override
   `changeEvent` and call a `retranslateUi()`. That work was deferred from
   FIBR-0004 (user decision 2026-07-02, recorded on the FIBR-0017 bullet), and
   `grep -rn "changeEvent\|retranslate" src` finds no screen that does it.
3. **Qt's own words would stay English.** The standard buttons (*OK*,
   *Cancel*, *Yes*) and the text-edit context menus come from Qt's catalog,
   `qtbase_<lang>.qm`. That file ships in the PySide6 wheel, under
   `QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)`, and it loads
   only if something installs it.
4. **Two kinds of word come from `QLocale()`, not from `tr()`.** These are month
   names (`services/pdf_export.py`, through `standaloneMonthName`) and the layout direction (`app.py::run`, through
   `textDirection`). `QLocale()` is the system locale, so a user who picks a
   language other than the system's would see month names in the system's
   language.

## 3. Scope decisions (agreed with the user)

- **English only for now** (finbreak's developer, 2026-11-15). The question
  of who writes the five non-English catalogs is the user's. It is recorded on
  FIBR-0017 as `Waiting-on: user`, with the recommendation to ship AI drafts
  labelled as machine-translated. The pipeline does not depend on the answer.
- **Switching rebuilds the window rather than re-translating each widget**
  (finbreak's developer, 2026-11-15). This replaces `coding.md` § 5.2's
  `changeEvent` rule; § 8 says why. It still meets the purpose of the
  2026-07-02 deferral note: the switch takes effect without a relaunch.
- **A language choice changes words, not number or date formats**
  (finbreak's developer, 2026-11-15). Separators and date and time formats keep
  following their own preferences, whose "System default" means the system
  locale. Month names and layout direction follow the chosen language, because
  they are words and reading order rather than formats.
- FIBR-0129 and FIBR-0209 are built by this item, against their own bullets.

## 4. Design

### 4.1 Where catalogs live, and how they are made

```
src/finbreak/data/i18n/finbreak_<lang>.ts   source catalog, committed (translator edits this)
src/finbreak/data/i18n/finbreak_<lang>.qm   compiled, committed beside it
scripts/update-translations.sh [<lang>...]  lupdate into each .ts (or create one per <lang>), then lrelease
```

- `<lang>` follows `naming.md`'s Qt-mandated `finbreak_<locale>` form, for
  example `es`, `pt_BR` or `zh_CN`. English is the source language and has no
  catalog.
- The script runs `pyside6-lupdate` with `-no-obsolete -locations none` over
  `git ls-files 'src/finbreak/*.py'`. Then it runs `pyside6-lrelease` on each
  `.ts` file. `-locations none` keeps a code edit that moves a string from
  rewriting the catalog.
- **`src/finbreak/data/` already reaches every bundle.** All three freeze
  scripts add the whole directory (`scripts/build-windows-exe.py`'s
  `_DATA_SRC`, the `--add-data … finbreak/data` lines in
  `scripts/_build-smoke-in-container.sh` and `packaging/obs/finbreak.spec`).
  So the only packaging edit is `pyproject.toml`'s `package-data`, which gains
  `data/i18n/*.qm`.
- **The `.qm` file is committed, not built at package time.** That way no
  build pipeline needs `lrelease`, and INV-6 checks that the two files agree.

### 4.2 One module owns the active language

`src/finbreak/ui/language.py`, which mirrors `ui/theme.py`'s preference
shape:

```python
LANGUAGE_PREF_KEY = "language"        # window INI (paths.window_settings_path()), like THEME_PREF_KEY
LANGUAGE_SYSTEM = "system"            # FIBR-0129's sentinel; the default
CATALOG_DIR: Path                     # Path(__file__).parent.parent / "data" / "i18n"; tests repoint it

def available_languages() -> list[str]:      # "en" plus each <lang> with a finbreak_<lang>.qm in CATALOG_DIR
def load_language_pref() -> str:             # stored token if it is "system" or in available_languages(), else "system"
def save_language_pref(token: str) -> None:
def resolve_language(pref: str, system: QLocale) -> str:   # FIBR-0209's order; never raises
def ui_locale() -> QLocale:                  # QLocale(active language, system territory), for words only

class LanguageController(QObject):           # parented to the QApplication
    languageChanged = Signal()
    def apply(self, pref: str) -> None:      # resolve, swap translators, set layout direction, emit
```

- The key lives in the window INI, not in the vault, because the unlock
  screen shows before the vault opens. The theme preference sits there for the
  same reason.
- `resolve_language` follows FIBR-0209's order: an explicit available token
  first; then the first available entry of `system.uiLanguages()`, the
  system's display languages in preference order, each read with `_` for `-`
  (`pt-BR` as `pt_BR`, then the list's own bare `pt`); then `"en"`. Not
  `system.name()`: on Windows that is the region format, not the display
  language.
- `apply` removes the translators it installed earlier and installs two new
  ones, both parented to the app. They are `finbreak_<lang>.qm` from
  `CATALOG_DIR`, and Qt's own catalog for the language from Qt's translations
  path, when there is one. `QTranslator.load(QLocale(lang), "qtbase", "_",
  <path>)` finds it, so `pt` also finds `qtbase_pt_BR.qm`. Resolving to `"en"` installs neither. `apply` then calls
  `app.setLayoutDirection(ui_locale().textDirection())`.

### 4.3 Startup

`app.py::run` builds the `LanguageController` beside the `ThemeController`,
**before `MainWindow`**, and calls `apply(load_language_pref())`. The existing
`setLayoutDirection(QLocale().textDirection())` line moves into `apply`, so
there is a single place that decides the direction.

### 4.4 Switching live: rebuild the window

The picker is a combo in `SettingsDialog`, built like the theme combo. Its
first entry is *System default (<detected language>)*, followed by one entry per
available language, under its own name. `language_name` gives English as
"English", because `QLocale("en").nativeLanguageName()` reads "American
English". Any other language gets its native name, with its native territory
when the token names one ("português (Brasil)"), so `pt` and `pt_BR` differ.
A token Qt has no name for shows as itself.

On save, `MainWindow._on_settings_saved` checks whether the token changed. If
it did, it calls `save_language_pref` and then `LanguageController.apply`.
`MainWindow` connects to `languageChanged` and rebuilds:

1. The chrome. The menu bar, toolbar and status bar are cleared, and
   `_build_chrome` and `_build_status_bar` run again. The window title is
   rebuilt too.
2. The live content. The workspace goes through the existing `_clear_live`
   path, and `_ensure_workspace` builds it afresh. The tab that was current is
   selected again.

Settings has already closed, and `_dialog` holds one modal at a time, so
nothing else is open to go stale. A screen therefore keeps building its
strings in `__init__`, as every screen does today. A widget that outlives
the rebuild must re-translate itself, and § 6 names the one case.

### 4.5 Words from the locale

`ui/month_summary.py` and `services/pdf_export.py` read month names from
`ui_locale()` instead of `QLocale()`. Every other `QLocale()` call formats
numbers or dates, and stays as it is (§ 3).

## 5. Invariants

- **INV-1** — `resolve_language` returns an explicit token when that token is
  available. For `"system"` it returns the first available entry of the
  system locale's `uiLanguages()`, else `"en"`. It never
  raises, and it never returns a token outside `available_languages()`.
  *Test:* `tests/features/i18n/test_language.py::test_INV1_*`, with a
  `CATALOG_DIR` holding `finbreak_pt.qm` and `finbreak_zh_CN.qm`. The cases are
  `pt_BR`→`pt`, `zh_CN`→`zh_CN`, `de_DE`→`en`, `C`→`en`, and explicit `pt` on a
  `de_DE` system→`pt`.
  *Breaks when:* the full-name step is skipped (so `zh_CN` resolves `en`), or
  an explicit token is preferred even when its catalog is missing.

- **INV-2** — `load_language_pref` returns the stored value only when it is
  `"system"` or in `available_languages()`. An absent key, an unknown token or
  a non-string value gives `"system"`.
  *Test:* `test_INV2_*`. It writes `"xx"`, `""`, `3` and a removed language's
  token to the window INI.
  *Breaks when:* the language whose catalog was deleted after it was picked is
  returned as is.

- **INV-3** — When a launch resolves to a language other than English, the
  first window the user sees is already in that language.
  *Test:* `test_INV3_first_window_is_translated`. It uses a pseudo catalog:
  every source text from the extracted `.ts`, translated as `⟦text⟧`, through
  `lrelease` into a temporary `CATALOG_DIR`. It runs `app.run`'s order (apply,
  then `MainWindow`) and asserts that the first-run or unlock dialog's title
  and buttons read `⟦…⟧`.
  *Breaks when:* `apply` runs after `MainWindow` is built.

- **INV-4** — After a language switch from Settings, no visible text in the
  main window is still in the old language. That covers window title, menus,
  toolbar, status bar, tab labels and the current tab's widgets.
  *Test:* `test_INV4_switch_leaves_no_old_text`. It unlocks a vault, switches
  to the pseudo catalog, walks every visible `QWidget` and `QAction` under the
  window, and asserts that none shows a source text the pseudo catalog
  translates. It walks again after switching back, this time for `⟦`.
  *Breaks when:* one part of the window (say the toolbar) is not rebuilt, or a
  rebuilt tab is restored from a widget kept from before the switch.

- **INV-5** — Qt's own strings follow the language: when `qtbase_<lang>.qm`
  exists, a `QDialogButtonBox` *Cancel* built after `apply` reads in that
  language.
  *Test:* `test_INV5_qt_strings_follow`. It uses `fr`, whose qtbase catalog
  the PySide6 wheel ships, with a pseudo `finbreak_fr.qm`.
  `test_INV5_qt_strings_find_a_regional_catalog` uses `pt`, whose only qtbase
  catalog is `qtbase_pt_BR.qm`.
  *Breaks when:* only finbreak's translator is installed, or the qtbase lookup
  tries the exact file name only.

- **INV-6** — Every shipped catalog is current: running
  `scripts/update-translations.sh` changes no committed `.ts` or `.qm` file.
  *Test:* `test_INV6_catalogs_are_current`. It runs the script on a copy of
  the tree and compares bytes. It also runs once with a planted stale `.ts`
  (a string removed from the source) and expects a difference, so an empty
  catalog set does not pass without checking anything.
  *Breaks when:* a UI string is added or changed and the script is not re-run.

- **INV-7** — Every shipped `.qm` reaches the wheel: `pyproject.toml`'s
  `package-data` covers `data/i18n/*.qm`.
  *Test:* `test_INV7_qm_is_package_data`. It reads the `package-data` globs
  and matches each `.qm` path in `CATALOG_DIR` against them.
  *Breaks when:* the glob is missing, which leaves a pip-installed finbreak in
  English with no error.

- **INV-8** — The picker offers *System default* and then each available
  language under its own name. Saving a different choice writes the token and
  switches. Saving the same choice does neither.
  *Test:* `test_INV8_picker_*`, with the pseudo catalog dir holding `fr`;
  `test_INV8_language_name` for the names, `pt` against `pt_BR` included.
  *Breaks when:* saving any setting rebuilds the window, which throws away
  the user's place in it for nothing.

- **INV-9** — Month names follow the chosen language; separators do not.
  *Test:* `test_INV9_month_name_follows_language`. On a `de_DE` system with
  `en` chosen, the month summary's title shows *March*, and an amount still
  uses `de_DE` separators.
  *Breaks when:* `month_summary.py` keeps `QLocale()`, or `ui_locale()` is
  installed with `QLocale.setDefault`.

- **INV-10** — Switching to a right-to-left language mirrors the layout, and
  switching back restores it.
  *Test:* `test_INV10_direction_follows`. It uses a pseudo `ar` catalog and
  asserts `QApplication.layoutDirection()` after each `apply`.
  *Breaks when:* the direction is still set once in `run` and not in `apply`.

## 6. Failure modes

- **A catalog that fails to load** (corrupt `.qm`, or unreadable).
  `QTranslator.load` returns false, and `apply` falls back to English, as
  FIBR-0209 says, with no dialog. It writes one warning, naming the file, to
  the log file (FIBR-0410), because the picker still shows the chosen
  language. INV-1's silent rule covers it, and a corrupt-file case is added
  to INV-1's test.
- **A widget kept outside the rebuilt tree.** The one known case is a dialog
  that stays open through a switch, and a switch happens only from Settings,
  which closes first. A future non-modal window must connect to
  `languageChanged` and rebuild itself. `coding.md` § 5.2 says so after this
  item.
- **State lost in the rebuild.** A rebuilt tab loses its scroll position and
  any unsaved filter text. Column widths survive, because `_table_state`
  stores them in the window INI. This is the price of § 8's choice, and it is
  paid only on a language switch.
- **Locked mid-switch.** Auto-lock runs `_lock`, which clears the live content.
  A rebuild that arrives after the lock must build the locked state, not the
  workspace, so the rebuild checks `_unlocked`, as `_reopen_settings_if_idle`
  does.
- **No qtbase catalog for the language.** Hindi has none in the wheel today.
  Qt's own strings then stay English while finbreak's are translated. That
  cannot be avoided without shipping Qt's translation, which is out of scope.

## 7. Tests

All tests live in `tests/features/i18n/test_language.py`, beside the existing
literal-argument guard. Each of INV-1 to INV-10 has its own test, named in its
*Test:* clause and in § 10. The pseudo catalog fixture builds one `.ts` from
`lupdate`, fills every translation with `⟦source⟧`, and compiles it with
`lrelease` into `tmp_path`, under each language code a test needs. Building it
per session keeps it current without a committed fixture. Each test is
seen to fail before its code exists, then pass. INV-4 is also checked by
mutation: leaving the toolbar out of the rebuild must turn it red.

`scripts/update-translations.sh` is a new script, so `ci-local.sh`'s
shellcheck stage covers it.

## 8. Alternatives considered (and rejected)

- **`changeEvent` plus a `retranslateUi()` on every widget**, which is
  `coding.md` § 5.2 as it stands. That means 38 contexts, each needing a
  second copy of its text-setting code that must stay in step with `__init__`.
  Each screen added later needs the same. A string missed in `retranslateUi` stays
  in the old language with nothing to catch it except a walk like INV-4's. The
  rebuild gets the same result from code that already exists (`_clear_live`,
  `_ensure_workspace`), and a screen can only be wrong one way: not rebuilt at
  all, which INV-4 catches.
- **Restart to apply.** This is simpler still, but it breaks the purpose of
  the 2026-07-02 deferral note, which asks for a switch without a relaunch.
  It would also lock the vault for a language change.
- **Build `.qm` at package time.** This would add `lrelease` to three build
  pipelines, OBS's included, for files a few kilobytes in size. Committing them
  with a freshness check (INV-6) costs less.
- **`QLocale.setDefault` to the chosen language.** This is one line, but it
  would also change number separators and date formats. The user picks those
  separately, and their "System default" means the system (§ 3).

## 9. Out of scope

- The five non-English catalogs, and how the picker labels a machine-drafted
  one. These are tracked by FIBR-0017's `Waiting-on: user`.
- Right-to-left layout QA on real screens. That needs a real Arabic catalog,
  and comes with the catalogs.
- FIBR-0434 and FIBR-0425 were deferred to FIBR-0017. This spec does not
  change them; they are re-read when the catalogs land.
- Translating the PDF export's text beyond month names. `services/pdf_export.py`
  is the i18n guard's named exception (FIBR-0311).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/features/i18n/test_language.py::test_INV1_*` |
| INV-2 | `test_language.py::test_INV2_*` |
| INV-3 | `test_language.py::test_INV3_first_window_is_translated` |
| INV-4 | `test_language.py::test_INV4_*`; `test_INV4_toolbar_keeps_its_place` checks a moved toolbar keeps its edge. **Partial:** it walks the main window and its current tab, not every tab |
| INV-5 | `test_language.py::test_INV5_*` |
| INV-6 | `test_language.py::test_INV6_catalogs_are_current` |
| INV-7 | `test_language.py::test_INV7_qm_is_package_data`. **Partial:** the freeze scripts are trusted to keep adding all of `finbreak/data`, as the category library already relies on |
| INV-8 | `test_language.py::test_INV8_*` |
| INV-9 | `test_language.py::test_INV9_month_name_follows_language` |
| INV-10 | `test_language.py::test_INV10_direction_follows` |
| A future non-modal window re-translates itself | **nothing**: `coding.md` § 5.2 states it, and INV-4 sees only what is open during the test |

## 11. Cross-doc impact

- `docs/standards/coding.md` § 5.2: the *Live language switching* bullet
  becomes the rebuild rule from § 4.4, plus § 6's rule for a widget outside
  the rebuild.
- `docs/design.md` § *Internationalization*: the sentence saying live
  switching relies on per-widget re-translation now points at this spec.
- `tests/features/i18n/spec.md`: its *Out of scope* line on catalogs now
  points here.
- `docs/standards/naming.md`: the Qt translation row's *(added at the i18n
  packaging step)* becomes the path from § 4.1.
- `CHANGELOG.md`: a Settings entry for the language picker.

## 12. Cold-eyes loop log

Rows live in `../reviews/FIBR-0017-translation-pipeline-loop-log.md`.
