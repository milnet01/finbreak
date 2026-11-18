<!-- ants-spec-format: 1 -->
# FIBR-0425 — every refusal reaches the screen through Qt's translation system

**Status:** accepted (2026-11-18). No contract review: the spec is owed for a
design choice and three subsystems, and nothing it pins is stored or bound
by other tooling (rule 14).
**Kind:** fix.
**Source:** ROADMAP FIBR-0425 (full-audit-2026-09-27 code lanes 5 and 6).
**Pairs with:** FIBR-0434, which is the services half of the same work. It has
no spec of its own; its roadmap body names this file. **Blocker for:**
FIBR-0017's five catalogs.

**Layman:** When finbreak refuses something (an unreadable statement, a
duplicate account name, an ambiguous amount), the message will appear in the
language you chose, not always in English. In English nothing changes.

## 1. Goal

After this ships, a catalog translates every message that explains a refusal.
The importers and services stay free of Qt. Each refusal's English sentence is
written once, at the line that raises it, and the screen translates it. English
users see the same words as today. A number in one now carries the locale's
grouping (`100,000`), as INV-6 requires.

## 2. Problem

1. **Screens show exception text verbatim.** `self._error.setText(str(exc))`
   is the handler in `ui/accounts.py`, `ui/categories.py`, `ui/rules.py`,
   `ui/manual_entry.py`, `ui/import_batch.py` and `ui/import_wizard.py`
   (`grep -rn "setText(str(exc))" src/finbreak/ui`, 2026-11-18). So is
   `dialog.show_error(str(exc))` in `MainWindow`'s password-hint handler.
   The text comes from `ValueError`, `FinbreakError` subclasses and
   `HintPolicyError` raised with English literals in `importers/` and
   `services/`, and from `ui/_amount.py`.
2. **Two reason fields carry English to a cell.** `RowError.reason`
   (`importers/base.py`) fills the preview table's reason column.
   `BatchFile.reason` (`services/batch_import.py`) fills the batch status cell.
   `BatchReviewWidget._translated` translates the seven batch constants by string
   equality and passes any other reason through untranslated. `_fail` and
   the commit pass write `str(exc)` into that field.
3. **No exception carries anything to translate by.** Every message is a
   finished English string, often with a value spliced in (`f"an account named
   {name!r} already exists"`). A translator cannot reach it, and the UI cannot
   look it up.
4. **The one translated refusal is translated at the raise site.**
   `ui/_password_hint.py` raises `HintPolicyError(QCoreApplication.translate(…))`.
   Its three siblings in `services/password_hint.py` cannot, because that module
   is Qt-free.

`docs/design.md` § Internationalization (i18n) & localisation requires `tr()`
for every user-facing string. Nobody sees the gap while finbreak ships English
only. FIBR-0017's catalogs make it visible.

## 3. Scope decisions (agreed with the user)

- **Do this with FIBR-0017, not before** (user, 2026-10-07, on FIBR-0425 and
  FIBR-0434). The catalogs are AI-drafted (user, 2026-11-18), so this lands
  before they are drafted, and every refusal is in the first draft.
- **English wording stays word for word** (finbreak's developer, 2026-11-18).
  Specs FIBR-0050, FIBR-0190 and FIBR-0255 tell refusals apart by their
  wording, and tests assert on it. Keeping the text keeps both true.
- **One spec for FIBR-0425 and FIBR-0434** (finbreak's developer,
  2026-11-18). They share one mechanism and one guard. The guard walks every
  screen, so neither item can satisfy it alone. FIBR-0434's body points here,
  so its id still leads to its contract.

## 4. Design

### 4.1 The message travels in the exception

`src/finbreak/errors.py` gains two Qt-free names:

```python
def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # lupdate extracts the call by name
    return text

@dataclass(frozen=True)
class UserMessage:
    template: str                      # English, with {name} placeholders
    values: Mapping[str, str | int]    # read-only; filled in after translation
    def __init__(self, template: str, /, **values: str | int) -> None: ...
    def __str__(self) -> str:          # template.format(**values): today's English
```

A refusal is raised with a `UserMessage` as its only argument:

```python
raise ValueError(UserMessage(QT_TRANSLATE_NOOP("Refusal", 'could not read the amount "{raw}"'), raw=raw))
```

- `BaseException.__str__` returns `str(args[0])`, so `str(exc)` is the English
  sentence of today. Every `except ValueError`, every type mapping and every
  `pytest.raises(match=…)` keeps working.
- The context is always `"Refusal"`, so one catalog section holds them all.
- A fixed sentence used from several raise sites becomes a module constant
  holding a `UserMessage`. Examples are `_MISPARSE` in `importers/standard_bank.py`
  and the seven batch constants.
- `pyside6-lupdate` extracts `QT_TRANSLATE_NOOP("Refusal", "…")` from a module
  with no Qt import. Measured 2026-11-18: a probe defining the function
  locally and raising through it gave `Found 1 source text(s)` under
  `<name>Refusal</name>`.

### 4.2 Where `UserMessage` replaces text

- Every user-facing raise listed in §2.1, in `importers/csv_importer.py`,
  `ofx_importer.py`, `pdf_importer.py`, `standard_bank.py`,
  `services/accounts.py`, `categories.py`, `categorization.py`,
  `transactions.py`, `import_.py`, `password_hint.py`, and `ui/_amount.py`.
  `ui/_password_hint.py`'s recovery-code refusal moves to the same form.
- `RowError.reason: UserMessage`. A row error built from a caught exception
  uses `message_of(exc)`.
- `BatchFile.reason: UserMessage | None`, default `None`. The seven batch
  constants become `UserMessage`s. `_fail` and the commit pass store
  `message_of(exc)`.
- `errors.message_of(exc) -> UserMessage` returns the exception's own message.
  For an exception without one, it returns one fixed message: `OSError` gets
  *"couldn't read this file"* and anything else *"something unexpected went
  wrong"*.

Raises that never reach a screen keep plain strings. Both reason fields live
in memory only, so nothing on disk changes.

### 4.3 The screen translates

`src/finbreak/ui/user_text.py`:

```python
def user_text(source: BaseException | UserMessage) -> str
```

1. Take `message_of(source)` for an exception, or `source` itself.
2. Translate: `QCoreApplication.translate("Refusal", message.template)`.
   This is the one `translate` call whose text argument is not a literal. The
   i18n guard names this function as its only exception, and §5 INV-2 is
   what keeps every template it can receive a marked literal.
3. Check the translation: every placeholder must be a bare name the message
   carries, with no format spec. A catalog is data, and `{name.attr}` would
   print an object rather than raise. A translation that fails the check
   gives `str(message)`, the English sentence (INV-7).
4. Format values: an `int` through `QLocale().toString`, as the batch report's
   `_digits` does; a `str` as given.
5. Substitute with `str.format`, after translating.

Every sink in §2.1 and §2.2 calls `user_text`. `BatchReviewWidget._translated`
is deleted, and its callers call `user_text`.

## 5. Invariants

- **INV-1** — No screen shows an exception's own text. In `src/finbreak/ui/`,
  no `str(name)` call takes a name bound by an `except … as name` clause,
  unless it is an argument to a logging call.
  *Test:* `tests/features/i18n/test_user_text.py::test_INV1_no_screen_shows_exception_text`.
  It walks the AST and plants `setText(str(exc))` to prove the walk sees it.
  *Breaks when:* a new handler writes `self._error.setText(str(exc))`.

- **INV-2** — Every `UserMessage(…)` call in `src/finbreak/` has a
  `QT_TRANSLATE_NOOP("Refusal", <string literal>)` call as its first argument.
  *Test:* `test_INV2_every_message_is_marked`, an AST walk with a planted
  `UserMessage(f"…")` and a planted `UserMessage(CONSTANT)`. The same file's
  `test_INV2_lupdate_extracts_refusals` runs `pyside6-lupdate` over
  `src/finbreak` and finds the duplicate-account template under `Refusal`.
  That proves that an imported marker is extracted, not only a local one.
  *Breaks when:* a raise builds its template with an f-string, or a module
  constant holds the bare string.

- **INV-3** — Every template's placeholder names equal the keyword names its
  call passes.
  *Test:* `test_INV3_placeholders_match_values`, an AST walk using
  `string.Formatter().parse` on each INV-2 literal, with a planted mismatch.
  *Breaks when:* a raise passes `raw=` to a template that says `{value}`, which
  would raise `KeyError` inside an `except` handler.

- **INV-4** — English text is unchanged: `str(exc)` of each converted refusal
  equals the sentence it raised before this item.
  *Test:* the existing message assertions in
  `tests/features/standard_bank_pdf/`, `pdf_import/`, `ofx_import/`,
  `import_/`, `categories/`, `amount_input/` and `statements/`, unmodified.
  Tests that compared a `RowError.reason` to a string compare `str(reason)`.
  *Breaks when:* a template's wording drifts while it is being marked.

- **INV-5** — Under a catalog, a refusal reaches each kind of sink translated,
  with its values substituted after translation.
  *Test:* `test_INV5_*`, using FIBR-0017's pseudo catalog (`⟦source⟧`). An
  Accounts add with a duplicate name shows `⟦an account named … already
  exists⟧` with the name filled in. A batch file that fails to scan shows a
  `⟦…⟧` reason in its status cell. A CSV row with an empty date shows a `⟦…⟧`
  reason in the preview's reason cell.
  *Breaks when:* `user_text` formats before translating, so the lookup misses,
  or a sink still reads the field directly.

- **INV-6** — An `int` value appears in the locale's digits.
  *Test:* `test_INV6_int_values_use_locale_digits`. On an `ar_EG` default
  locale, the OFX transaction cap reads in Arabic-Indic digits.
  *Breaks when:* values are substituted with `str()`.

- **INV-7** — A translation whose placeholders do not match falls back to the
  English sentence, and logs one warning naming the template, not the values.
  *Test:* `test_INV7_bad_translation_falls_back`. It patches the translation
  to return `"{nope}"`, expects the English sentence, and runs under `caplog`
  with a sentinel value that must not appear.
  *Breaks when:* the `KeyError` escapes into the handler that was showing the
  refusal.

- **INV-8** — A refusal's values never reach the log. An exception with no
  `UserMessage` shows `message_of`'s fixed sentence, and the log gets its type
  only. This is the trust boundary: values and messages can hold statement
  text, which `docs/security-model.md` INV-9 keeps out of the log file.
  *Test:* `test_INV8_*`. It runs `user_text` on an `OSError` and a
  `ValueError`, each carrying a sentinel, under `caplog`. The sentinel appears
  in neither the shown text nor the log.
  *Breaks when:* the fallback returns `str(exc)`, or logs it.

## 6. Failure modes

- **A stdlib error reaches a sink.** `UnicodeDecodeError`, an `OSError` with
  a path: the user now sees one of `message_of`'s two fixed sentences instead
  of Python's wording. Detail is lost. Those messages were never translatable,
  and an `OSError` names a path.
- **Two values stay English under a catalog.** `csv.Error`'s text fills
  *"the file is not valid CSV: {detail}"*, and the missing-columns refusal
  shows a Python list. INV-4 keeps both byte-identical.
- **A row error built from a stdlib `ValueError`.** Its reason cell reads
  *"something unexpected went wrong"* rather than, for example, strptime's
  text. FIBR-0146 already replaced the common date case with its own message.
- **A translator drops or renames a placeholder.** INV-7.
- **A template needs a literal brace.** It must be doubled, as in `str.format`.
  INV-3's parse rejects a single one.
- **A future raise site forgets the marker.** INV-2 fails if it builds a
  `UserMessage` without one. A plain-string raise that reaches a screen
  through a new handler is caught by INV-1, not by INV-2.

## 7. Tests

INV-1, INV-2, INV-3 and INV-5 to INV-8 live in
`tests/features/i18n/test_user_text.py`. INV-4 is the existing suites. INV-5
needs FIBR-0017's `pseudo` fixture, which `test_language.py` defined, so it
moves to `tests/conftest.py` for both files to use. A second `conftest.py`
under `tests/features/i18n/` would shadow the root one, and
`from conftest import _PW` would then fail (measured 2026-11-18). Each
new test is seen to fail before its code exists: INV-1 against today's
`setText(str(exc))` lines, INV-5 against today's English. The AST walks each
carry a planted-offence leg, as `test_translatable_strings.py` does, so a walk
that matches nothing cannot pass. mypy also catches a reason field handed
straight to a widget, because `setText` takes `str` and the field is a
`UserMessage`.

`tests/features/i18n/` is in `DOCS_SUITES` only if a test reads a doc, and none
here does.

## 8. Alternatives considered (and rejected)

- **A stable key per refusal, mapped to a `tr()` sentence in the UI** (the
  roadmap's recommendation). Each sentence would live in two places, the key at
  the raise site and the sentence in a UI table. A key with no sentence would
  be caught only by a completeness test. The marker keeps the sentence at
  the raise site, beside the condition it describes, and gets the same
  extraction.
- **One exception class per refusal, mapped by type** (`ui/unlock.py`'s
  pattern). That works for a handful. Here it would mean a class per message,
  and the mapping is the same two-copy problem.
- **Let the importers and services call `QCoreApplication.translate`.** That
  breaks their Qt-free contract (`FIBR-0085-batch-import-service.md`: "This
  is the Qt-free half"; the importers run headless), and the text would be frozen in the language
  that was active when it was raised.
- **Qt's `%1` placeholders.** finbreak's existing `tr()` templates use
  `{name}` with `str.format` (`BatchReviewWidget`'s `{why}`), and named
  placeholders tell a translator what each value is.

## 9. Out of scope

- The five catalogs and the machine-translated label: FIBR-0017.
- Month-name grammar and sentence spacing: FIBR-0473.
- Backup, unlock, update and first-run messages: already mapped by type to
  fixed `tr()` text.
- The PDF export's document text: the i18n guard's named exception
  (FIBR-0311).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_user_text.py::test_INV1_no_screen_shows_exception_text`. **Partial:** it sees `str(exc)`, not an exception's text reached another way, such as `exc.args[0]` or an f-string |
| INV-2 | `test_user_text.py::test_INV2_*` |
| INV-3 | `test_user_text.py::test_INV3_placeholders_match_values` |
| INV-4 | the existing message assertions named in INV-4. **Partial:** a refusal no test asserts on can drift unseen |
| INV-5 | `test_user_text.py::test_INV5_*`. **Partial:** one sink of each kind, not all of them; INV-1 covers the rest by shape |
| INV-6 | `test_user_text.py::test_INV6_int_values_use_locale_digits` |
| INV-7 | `test_user_text.py::test_INV7_bad_translation_falls_back` |
| INV-8 | `test_user_text.py::test_INV8_*` |
| A reason field shown without `user_text` | mypy, in the gate |
| A refusal raised with a plain string that some handler shows | **Partial:** INV-1 if the handler uses `str(exc)`; **nothing** if it reaches the screen another way |

## 11. Cross-doc impact

- `docs/standards/coding.md` § 5.2: a Qt-free layer raises a `UserMessage`,
  and the UI shows it through `user_text`.
- `docs/design.md` § Internationalization (i18n) & localisation: one sentence
  naming the mechanism.
- `docs/specs/FIBR-0219.md` § 4.1: its `setText(str(exc))` rendering becomes
  `user_text(exc)` (FIBR-0434's amendment).
- `tests/features/i18n/test_translatable_strings.py`: `user_text` is its one
  named exception.
- `CHANGELOG.md`: one *Changed* entry. English reads as before except an
  unreadable file's sentence and a grouped number.

## 12. Cold-eyes loop log

Rows live in `../reviews/FIBR-0425-translatable-refusals-loop-log.md`.
