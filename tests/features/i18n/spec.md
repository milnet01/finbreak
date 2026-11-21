# i18n — every translated string is one lupdate can actually see

**Owner:** FIBR-0310 R3. **Standard:** `docs/standards/coding.md`
§ Translatable UI strings.

## What this suite is for

The standard has always said to pass **string literals** to `tr()` /
`translate()`, "because `lupdate` extracts only literal arguments, so a string
built in a variable or helper produces an empty catalog entry". Nothing checked
it, and by 2026-08-25 sixteen user-facing strings across four modules were
built exactly that way — four as module constants, four behind a constant
*context*, eight behind a one-argument `_tr` wrapper.

The failure is silent in both directions. The call site reads as though the
string is handled, and the catalog is simply missing an entry nobody is looking
for. It surfaces at the FIBR-0017 i18n pass as a rewrite instead of a
translate-and-ship — which is the cost the standard says this rule exists to
avoid.

## The shapes, as measured

`pyside6-lupdate` over a probe file holding all five, 2026-08-25:

| Written as | Extracted |
|---|---|
| `self.tr("literal")` | yes |
| `self.tr(MODULE_CONSTANT)` | **no** |
| `QCoreApplication.translate("Ctx", "text")` | yes |
| `QCoreApplication.translate(CTX, "text")` | **no** |
| `helper("text")`, where `helper` calls `translate` | **no** |

A wrapper **function** is still fine and is how a long shared string keeps a
single copy — what matters is that the literal sits inside the `translate()`
call in the wrapper's body, where lupdate reads it. `ui/unlock.py`'s
`_pairing_broken()` is the pattern.

## Invariants

| ID | Test | Assertion |
|---|---|---|
| INV-1 | `test_no_tr_call_takes_a_non_literal_argument` | No `.tr()` first argument, and no `.translate()` first or second argument, in `src/finbreak/` is anything but a string literal — `services/pdf_export.py` excepted, and `user_text`'s one call on a refusal's template |
| INV-2 | `test_the_walk_actually_sees_a_planted_offence` | The walk returns exactly the three dropped shapes from a planted file, and neither of the two good ones — INV-1 asserts an absence, and this is what stops a walk that matches nothing reading as a pass |
| INV-3 | `test_the_known_offender_is_still_one` | `services/pdf_export.py` still holds at least one offence, so the by-name exclusion fails the day the work lands rather than quietly outliving it (FIBR-0311) |

## The translation pipeline

`test_language.py` enforces
[`docs/specs/FIBR-0017-translation-pipeline.md`](../../../docs/specs/FIBR-0017-translation-pipeline.md),
whose invariants it numbers. Its GUI legs run on a pseudo catalog built per
session, not the shipped ones: every extracted source text, translated as
`⟦text⟧`.

| ID | Test | Assertion |
|---|---|---|
| FIBR-0017 INV-1 | `test_INV1_resolution_order`, `test_INV1_corrupt_catalog_falls_back_to_english` | An explicit available token wins; `"system"` takes the first available of the system's display languages (`uiLanguages()`), else a catalog in the language and script of an entry naming its script (`zh_SG` gets `zh_CN`; `zh_TW` does not), else English; a catalog that will not load leaves English with no dialog, and logs a warning |
| FIBR-0017 INV-2 | `test_INV2_*` | The stored choice is kept only when it is `"system"` or an available language |
| FIBR-0017 INV-3 | `test_INV3_first_window_is_translated` | The first-run dialog `run()` opens is already in the stored language |
| FIBR-0017 INV-4 | `test_INV4_*` | After a switch from Settings, no visible text in the main window is in the old language, and back again; a moved toolbar keeps its edge |
| FIBR-0017 INV-5 | `test_INV5_*` | Qt's own *Cancel* follows the language, through a regional qtbase catalog where there is no bare one |
| FIBR-0017 INV-6 | `test_INV6_catalogs_are_current` | `scripts/update-translations.sh` changes no committed catalog, and does change a planted stale one |
| FIBR-0017 INV-7 | `test_INV7_qm_is_package_data` | `pyproject.toml`'s package-data covers every `.qm` |
| FIBR-0017 INV-8 | `test_INV8_*` | The picker lists *System default* then each language under its own name (`pt` and `pt_BR` distinct); saving a new choice writes it and switches, saving the same one does neither |
| FIBR-0017 INV-9 | `test_INV9_month_name_follows_language` | Month names follow the language; amount separators keep the locale's |
| FIBR-0017 INV-10 | `test_INV10_direction_follows` | A right-to-left language mirrors the layout, and switching back restores it |
| FIBR-0017 label | `test_FIBR0017_a_catalog_is_labelled_until_a_native_speaker_reviews_it` | A language not in `REVIEWED` is listed as "<name> (machine-translated)"; a reviewed one plainly |

`test_catalog_placeholders.py` reads every shipped `.ts`. Each finished
translation must name the same `{placeholders}`, format specs, conversions and
Qt `%n` / `%1` markers as its source, and parse as a format string; a planted
offence of each kind must be caught.

## Refusals

`test_user_text.py` enforces
[`docs/specs/FIBR-0425-translatable-refusals.md`](../../../docs/specs/FIBR-0425-translatable-refusals.md).
Its INV-4 is the existing message assertions in other suites, so it has no row
here.

| ID | Test | Assertion |
|---|---|---|
| FIBR-0425 INV-1 | `test_INV1_no_screen_shows_exception_text` | No `str(exc)` of a caught exception in `ui/` outside a logging call; a planted `setText(str(exc))` is seen |
| FIBR-0425 INV-2 | `test_INV2_every_message_is_marked`, `test_INV2_lupdate_extracts_refusals` | Every `UserMessage(…)` in `src/finbreak/` starts with `QT_TRANSLATE_NOOP("Refusal", <literal>)`; lupdate extracts an imported marker under `Refusal` |
| FIBR-0425 INV-3 | `test_INV3_placeholders_match_values` | Each template's placeholder names equal its call's keyword names |
| FIBR-0425 INV-5 | `test_INV5_*` | Under the pseudo catalog the Accounts error label, a batch status cell and a preview reason cell show the refusal translated, values filled in after |
| FIBR-0425 INV-6 | `test_INV6_int_values_use_locale_digits` | An `int` value reads in the locale's digits |
| FIBR-0425 INV-7 | `test_INV7_bad_translation_falls_back`, `test_the_fallback_cannot_raise_on_an_int_format_spec` | A translation whose placeholders do not fit (unknown name, attribute, index, format spec, lone brace) shows the English sentence and logs the template, not the values |
| FIBR-0425 INV-8 | `test_INV8_bare_exception_shows_a_fixed_sentence` | An exception with no `UserMessage` shows a fixed sentence, and its text reaches neither the screen nor the log |
| Review fix | `test_a_vault_lock_keeps_its_sentence`, `test_a_message_is_immutable_and_hashable` | A locked vault's refusal keeps its sentence; a message's values are read-only and it hashes |

## Why an AST walk rather than running lupdate

The rule is about the **shape of the call**, which the source answers directly.
A walk names the offending `file:line` rather
than reporting an absence from a generated catalog, which is the harder thing
to act on.

## Out of scope

- **Whether a translation is any good.** The shipped catalogs are AI drafts
  (user decision 2026-11-18); only their placeholders are checked.
- **Non-display strings** — log lines, DB keys, enum values. The standard says
  not to wrap those, and this suite does not check that they are not wrapped:
  it only checks the arguments of calls that *are* there.
- **`QT_TR_NOOP` / `QT_TRANSLATE_NOOP`.** Neither is used in this codebase
  today; adding one means adding it here.

## Registration

`i18n` is registered in `_NO_PROSE` in
`tests/features/prose_checks/test_prose_checks.py`: this suite reads Python
source under `src/`, never a tracked document, so it need not run on a doc-only
push.
