<!-- ants-coding-standards: 1 -->
# Coding Standards — v1

A shareable contract for code in this project. Pairs with the
other three standards in this folder ([documentation](documentation.md),
[testing](testing.md), [commits](commits.md)) — see the
[index](README.md) for the full set.

This standard governs ROADMAP bullets with `Kind: implement`,
`fix`, `refactor`, `audit-fix`, or `review-fix`. The other kinds
(`doc`/`doc-fix`, `test`, `chore`/`release`) defer to their
respective companion documents.


## 1. Principles

### 1.1 Shortest correct implementation

50 lines beats 250. No scaffolding for hypothetical futures, no
abstractions where a direct call works, no error paths for
scenarios that can't happen at the call site. Every line pays rent
in legibility or function.

### 1.2 No workarounds without a root-cause fix

Silencing warnings, `try/except: pass`, `--no-verify`, commenting
out broken code, disabling checks — last resort, not default.
Applies to build, test, runtime, and lint failures alike. When a
workaround is genuinely the only option, leave a comment naming
the underlying constraint so it reads as deliberate, not neglect.

### 1.3 Reuse before rewriting

Before writing new code, look for existing code that does the same
or similar thing, in order of preference:

1. Call it directly.
2. Refactor it to cover the new case, then call it — existing
   call-sites benefit.
3. Only if neither fits, write new code and justify the
   duplication.

**Rule of Three:** extract a helper on the third call-site, not
the first or second. Premature DRY costs more than duplication.

### 1.4 Six-month test

If someone opens this file six months from now, can they read the
change and understand *why* the code looks this way without the
author? If not, it's too clever or too long.

### 1.5 Use latest stable library + current idioms

When pulling in an external library (PySide6, a parsing or crypto
package, …), prefer the latest stable release unless pinned for an
explicit reason. When calling library APIs, use the current
idiomatic syntax for that version — not the one current three years
ago.

This section is about **idioms** (calling the API the current way);
**which version** to be on — latest-by-default, the below-latest-pin
exception, and the break register — is [dependencies.md](dependencies.md).

For Python/PySide6 specifically: modern syntax (`X | None`,
`list[int]`, `match`/`case` — available since 3.10; the project
runs 3.12+) and current PySide6 signal/slot style (see § 5.2). When unsure what's current for a library, read its
current docs before writing. Stale idioms still run but they age the
codebase.

### 1.6 Surface refactoring opportunities by default

Every implementation and review pass actively looks for refactoring
opportunities — dead code, duplication ripe for a Rule-of-Three
extraction (§ 1.3), an over-long function, a simpler shape (§ 1.1) — and
**records** them. *Surfacing* is the default; *acting* is gated: an
opportunity outside the current task becomes a tracked `refactor`-Kind
ROADMAP item (or a `DS##` debt-sweep entry), **not** a drive-by edit in
the current change — global rule § 11 keeps each edit surgical, and the
Rule of Three (§ 1.3) still governs *when* an extraction is worth doing. Silence
about known debt is the failure mode: an unrecorded "I'll remember it" is
the same as not finding it.


## 2. Error handling

- **Validate at boundaries, not internally.** User input, network,
  IPC, deserialisation → validate. Internal calls → trust.
- **Don't write paths that can't happen.** If a function is only
  called with non-null input from internal code, don't add a null
  check.
- **Surface unexpected errors loudly.** Swallowed exceptions are
  loaded guns. Log + propagate, don't `except: pass`.
- **Specific exceptions over generic.** `except FileNotFoundError`
  over `except Exception`.
- **Don't write fallbacks for scenarios that can't occur.** Trust
  framework guarantees; only fall back at real failure points.


## 3. Comments

Default to **no comments**. Only add one when the WHY is
non-obvious:

- A hidden constraint (`# qpdf is single-threaded; serialise here`).
- A subtle invariant (`# must run before the vault key is wiped`).
- A workaround for a specific bug (`# QTBUG-79126: frameless +
  modal drops clicks on Wayland — fall back to an event filter`).
- Behaviour that would surprise a reader.

Don't:

- Explain WHAT the code does — well-named identifiers do that.
- Reference the current task / fix / callers ("used by X", "added
  for Y") — those belong in the commit body.
- Write multi-line block comments or paragraph docstrings.


## 4. Naming

This section covers **in-code identifiers**. For **file & directory**
names (modules, docs, scripts, tests), see [naming.md](naming.md).

- **Functions / methods** — snake_case verb phrases
  (`parse_rgb_color`, `apply_theme`).
- **Variables** — snake_case noun phrases (`current_tab`,
  `grid_size`).
- **Classes** — PascalCase (`CategorizationService`, `CsvImporter`).
- **Booleans** — `is_*` / `has_*` / `can_*` (`is_ready`,
  `has_focus`).
- **Constants** — module-level `UPPER_SNAKE_CASE`.
- **Avoid abbreviations** except universally-known (`url`, `id`,
  `db`). Prefer `temperature` over `temp` when ambiguous.
- **No Hungarian notation.** A leading underscore (`_internal`)
  marks a non-public attribute; type prefixes (`str_name`,
  `i_count`) are not used.


## 5. Language-specific notes

This is a **Python 3.12+ / PySide6** project (ADR-0002). The notes
below cover the two surfaces; there is no C++ in the codebase.

### 5.1 Python

- Type hints on every public function signature; `list[int]` /
  `int | None` over `List[int]` / `Optional[int]` (3.10+ syntax).
- Use `pathlib.Path` over `os.path`.
- `pyproject.toml` for config; no `setup.py`.
- `subprocess.run([cmd, arg])` — never `shell=True` with an
  f-string (see §7).
- `match`/`case` where an `isinstance` ladder would otherwise pile
  up; `dataclasses` for plain record types.
- Context managers (`with`) for anything that owns a resource —
  files, DB connections, locks — over manual open/close.

### 5.2 PySide6 (Qt for Python)

- New-style signal/slot connections only:
  `sender.signal.connect(self.slot)`. Decorate slots with `@Slot()`.
- Define signals with `Signal(...)` as class attributes (PySide6),
  not the PyQt `pyqtSignal` spelling (ADR-0002).
- Parent-child ownership: pass a `parent` to `QObject`/`QWidget`
  constructors; don't hold extra Python references that outlive the
  parent and fight Qt's ownership.
- Keep blocking work (parsing, import, crypto) off the GUI thread —
  use a `QThread` worker, per design.md "Concurrency".
- Restrictive permissions (`0o600`) on any file that holds config or
  secrets (see §7).
- **Translatable UI strings:** every user-facing string goes through
  `self.tr(...)` (or `QCoreApplication.translate("Context", ...)` outside
  a `QObject`) — never a bare display literal. PySide6's `tr()` returns a
  plain `str` (there is no `QString.arg()`), so substitute values with
  Python formatting on **named** placeholders so translators can reorder
  them — `self.tr("Imported {done} of {total}").format(done=done,
  total=total)` — and for counts needing plural forms use Qt's numerus
  argument: `self.tr("Imported %n row(s)", "", count)`. Don't build display
  strings with `+` or bare f-strings, and don't wrap non-display strings
  (log lines, DB keys, enum values). Pass **string literals** to `tr()` /
  `translate()` — `lupdate` extracts only literal arguments, so a string built
  in a variable or helper produces an empty catalog entry. This holds from the
  first UI (P02) — it makes the FIBR-0017 (P12) i18n pass a translate-and-ship
  step instead of a rewrite.
- **Live language switching:** widgets re-translate on `QEvent.LanguageChange`
  (override `changeEvent` to call a `retranslateUi()` that regenerates labels) —
  Qt does **not** re-translate already-built widgets when the translator
  changes. Build this in from P02, or a mid-session switch only takes effect on
  the next launch.
- **RTL-safe layout:** build every screen to mirror for right-to-left
  locales (Arabic) with no per-widget rework. Arrange widgets with Qt
  layout managers (`QHBoxLayout`, `QFormLayout`, `QGridLayout`), never
  fixed x/y positions — layouts mirror automatically from the app's
  `layoutDirection`. Drive direction from the active locale
  (`QApplication.setLayoutDirection(QLocale().textDirection())`); don't pin
  `setLayoutDirection(Qt.LayoutDirection.LeftToRight)` on individual widgets.
  Leave text at its direction-aware default rather than forcing
  `Qt.AlignmentFlag.AlignLeft` / `Qt.AlignmentFlag.AlignRight`, and mirror
  direction-implying icons (back / forward arrows) yourself — supply an RTL
  variant or pick per `layoutDirection`; Qt mirrors layouts, not custom icon
  art.
- **Locale-aware formatting:** render numbers, currency, and dates via
  `QLocale` (`QLocale().toString(value, 'f', 2)` — `'f'` = fixed-point, 2
  decimals), never a hand-rolled `f"{x:,.2f}"` for display. `QLocale` controls the *format* (separators,
  grouping), not the currency: pass the base currency's symbol explicitly —
  `QLocale().toCurrencyString(value, symbol)` — so a fixed base currency isn't
  reformatted to the locale's own. See [design.md "Internationalization (i18n) &
  localisation"](../design.md#internationalization-i18n--localisation).


## 6. Performance

- **Profile before optimising.** "Make it work, make it right,
  make it fast" — in that order.
- Avoid premature `O(n²)` patterns where `O(n)` fits.
- For hot paths: pre-allocate, batch I/O, avoid copies.
- Don't write a cache without measuring the hit rate first.
- Don't pessimise — stream large statement files rather than
  reading them whole, build lists with comprehensions/generators,
  and avoid needless copies of large transaction sets.


## 7. Security

Security is the load-bearing concern here — see
[docs/security-model.md](../security-model.md) for the binding
invariants. Coding-level rules:

- **Never trust user input.** Validate at the boundary. Imported
  CSV/OFX/PDF files are untrusted (security-model INV-5): treat CSV
  cells as data, never as spreadsheet formulas; fail per-row.
- **No `shell=True`.** Use argv arrays: `subprocess.run([cmd, arg])`.
  Never interpolate user data into a shell string.
- **Atomic file writes.** Write to a temp file, then `os.replace()`.
  Don't truncate-and-write — a crash leaves an empty file.
- **Restrictive perms on secret-bearing files.** `0o600` for the
  vault and any config holding secrets.
- **Path traversal** — `Path.resolve()` and check
  `os.path.commonpath` before opening user-supplied paths.
- **Don't log secrets** (security-model INV-9). The master
  password, the derived key, and decrypted statement data never
  reach a `print` / `logging` call.


## 8. Anti-patterns

- ❌ Multi-paragraph docstrings on every function.
- ❌ "Just in case" exception handlers that swallow everything.
- ❌ Half-finished implementations behind feature flags.
- ❌ Renaming a variable to `_unused` instead of removing it.
- ❌ `# TODO: fix later` with no roadmap entry tracking it.
- ❌ Hardcoded paths / magic numbers without a named constant.
- ❌ Dead-code branches kept "just in case".
- ❌ Compatibility shims for callers that don't exist any more.
- ❌ `from foo import *` — it pollutes the namespace and hides
  where names come from.
- ❌ Bare `except:` / `except Exception: pass` that swallows errors.
