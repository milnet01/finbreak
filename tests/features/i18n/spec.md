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

## Why an AST walk rather than running lupdate

The rule is about the **shape of the call**, which the source answers directly.
A walk needs no tool on `PATH` — `pyside6-lupdate` ships with PySide6, but the
gate would then depend on it — and it names the offending `file:line` rather
than reporting an absence from a generated catalog, which is the harder thing
to act on.

## Out of scope

- **Whether the translation is any good**, or whether a `.qm` exists at all.
  No catalog is shipped yet; that is FIBR-0017.
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
