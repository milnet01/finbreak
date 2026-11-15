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
| INV-1 | `test_no_tr_call_takes_a_non_literal_argument` | No `.tr()` first argument, and no `.translate()` first or second argument, in `src/finbreak/` is anything but a string literal — `services/pdf_export.py` excepted |
| INV-2 | `test_the_walk_actually_sees_a_planted_offence` | The walk returns exactly the three dropped shapes from a planted file, and neither of the two good ones — INV-1 asserts an absence, and this is what stops a walk that matches nothing reading as a pass |
| INV-3 | `test_the_known_offender_is_still_one` | `services/pdf_export.py` still holds at least one offence, so the by-name exclusion fails the day the work lands rather than quietly outliving it (FIBR-0311) |

## The translation pipeline

`test_language.py` enforces
[`docs/specs/FIBR-0017-translation-pipeline.md`](../../../docs/specs/FIBR-0017-translation-pipeline.md),
whose invariants it numbers. No real catalog ships, so its GUI legs run on a
pseudo catalog built per session: every extracted source text, translated as
`⟦text⟧`.

| ID | Test | Assertion |
|---|---|---|
| FIBR-0017 INV-1 | `test_INV1_resolution_order`, `test_INV1_corrupt_catalog_falls_back_to_english` | An explicit available token wins; `"system"` takes the first available of the system's display languages (`uiLanguages()`), else English; a catalog that will not load leaves English with no dialog, and logs a warning |
| FIBR-0017 INV-2 | `test_INV2_*` | The stored choice is kept only when it is `"system"` or an available language |
| FIBR-0017 INV-3 | `test_INV3_first_window_is_translated` | The first-run dialog `run()` opens is already in the stored language |
| FIBR-0017 INV-4 | `test_INV4_*` | After a switch from Settings, no visible text in the main window is in the old language, and back again; a moved toolbar keeps its edge |
| FIBR-0017 INV-5 | `test_INV5_*` | Qt's own *Cancel* follows the language, through a regional qtbase catalog where there is no bare one |
| FIBR-0017 INV-6 | `test_INV6_catalogs_are_current` | `scripts/update-translations.sh` changes no committed catalog, and does change a planted stale one |
| FIBR-0017 INV-7 | `test_INV7_qm_is_package_data` | `pyproject.toml`'s package-data covers every `.qm` |
| FIBR-0017 INV-8 | `test_INV8_*` | The picker lists *System default* then each language under its own name (`pt` and `pt_BR` distinct); saving a new choice writes it and switches, saving the same one does neither |
| FIBR-0017 INV-9 | `test_INV9_month_name_follows_language` | Month names follow the language; amount separators keep the locale's |
| FIBR-0017 INV-10 | `test_INV10_direction_follows` | A right-to-left language mirrors the layout, and switching back restores it |

## Why an AST walk rather than running lupdate

The rule is about the **shape of the call**, which the source answers directly.
A walk names the offending `file:line` rather
than reporting an absence from a generated catalog, which is the harder thing
to act on.

## Out of scope

- **Whether a translation is any good.** No non-English catalog ships yet
  (FIBR-0017's `Waiting-on: user`).
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
