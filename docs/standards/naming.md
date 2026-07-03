<!-- ants-naming-standards: 1 -->
# File & Directory Naming Standards — v1

A shareable contract for **what to call a file or directory** in this
project. Pairs with the other standards in this folder
([coding](coding.md), [dependencies](dependencies.md),
[documentation](documentation.md), [testing](testing.md),
[commits](commits.md)) — see the [index](README.md) for the full set.

Unlike the Kind-scoped standards, this one governs **every** file,
whatever the work: a new module (`Kind: implement`), a spec
(`Kind: doc`), a test (`Kind: test`), a script, a workflow. When you
create a file and wonder what to call it, this is the one place to look
(**screenshot** filenames defer to [documentation.md § 6](documentation.md)
— other image/icon assets are governed by the table below; in-code
identifier names defer to [coding.md § 4](coding.md) — both cross-linked
below).

The rules below **codify the conventions already in the tree** — they
describe what the project does, not a new scheme to migrate to. Every
**real-file** example in the table exists at the time of writing; a few
rows for file kinds the project hasn't produced yet are marked
*(none yet)* / *hypothetical* rather than pointing at a real file.


## 1. The one rule that decides most cases

**Does the name become a Python identifier — i.e. is the file a
`.py`, or a package directory Python imports?**

- **Yes → `snake_case`.** A Python module or package name becomes an
  identifier in an `import` statement, and identifiers cannot contain
  hyphens. `main_window.py`, `repositories/`. This is not a preference —
  `import main-window` is a syntax error. The `.py` extension forces
  `snake_case` **even for a script that is run, not imported** (e.g. a
  hypothetical `scripts/seed_data.py`), because `python -m` and `import`
  must both be able to name it.
- **No → `kebab-case`.** Docs, shell scripts, and CI workflows are never
  imported, read better with hyphens, and match URL / CLI conventions.
  `ci-local.sh`, `0005-csv-mapping-profiles.md`, `build-smoke.yml`.

Everything else is a refinement of this split. When a file's name is
**dictated by a tool or ecosystem** (§6) or **is a stable ID** (§5),
that wins over both.


## 2. Universal rules (all files)

- **Lowercase**, except the well-known root / ecosystem-mandated names
  (§6) and the uppercase project prefix inside an ID (`FIBR-0006.md`).
- **ASCII only. No spaces.** A space in a filename breaks shell globs,
  `Makefile` rules, and half the tools that touch it.
- **One separator style per name** — `snake_case` **or** `kebab-case`,
  never mixed (`csv_importer.py`, not `csv-importer_v2.py`). Tool-mandated
  names (§6) are the only exception.
- **No version / date / author suffixes** — `report.md`, never
  `report-final-v2-2026.md`. Git holds the history; the working name is
  always the current one.
- **A leading `_`** marks a **private / internal** file that other code
  or people should not reach for directly — `_selftest.py`,
  `ui/_worker.py`, `scripts/_build-smoke-in-container.sh`.
- **The name states the file's single concern** — if you can't name it
  in one or two words, the file is probably doing two things (coding.md
  § 1.1).


## 3. Reference table

Every Example below is a real file in this repo, **except** the rows whose
Example is a *(parenthesised, future-tense placeholder)* — file kinds the
project hasn't produced yet. (The two illustrations in the note *beneath*
the table are hypothetical too.)

| Artifact | Pattern | Examples |
|----------|---------|----------|
| **Python module** | `snake_case.py` | `models.py`, `main_window.py`, `migrations.py` |
| **Python package dir** | `snake_case/` | `repositories/`, `services/`, `ui/` |
| **Python dunder file** | as Python requires | `__init__.py`, `__main__.py` |
| **Private module** | `_snake_case.py` | `_selftest.py`, `ui/_worker.py` |
| **Type stub** | `<module>.pyi` (mirrors its module) | *(none yet)* |
| **Test module** | `test_<subject>.py` | `test_smoke.py`, `test_vault.py` |
| **Feature-test dir** | `<feature>/` (lowercase; snake_case if multiword) | `tests/features/vault/`, `tests/features/categories/` |
| **Test contract** | `spec.md` (fixed name inside the feature dir) | `tests/features/vault/spec.md` |
| **Fixture data file** | `kebab-case.<ext>` (not imported) | *(under `tests/fixtures/<rule>/` when added)* |
| **Spec doc** | `<ID>.md` (the stable roadmap ID) | `docs/specs/FIBR-0006.md` |
| **Journal entry** | `<ID>.md` | `docs/journal/FIBR-0006.md` |
| **ADR** | `NNNN-kebab-title.md` (4-digit sequential + slug) | `docs/decisions/0005-csv-mapping-profiles.md` |
| **Standard** | `<lowercase-word>.md` | `coding.md`, `roadmap-format.md`, `naming.md` |
| **Other design doc** | `docs/<kebab-case>.md` | `security-model.md`, `known-issues.md`, `audit-allowlist.md` |
| **Shell script** | `scripts/<kebab-case>.sh` | `ci-local.sh`, `ci-setup.sh`, `build-smoke.sh` |
| **CI workflow** | `.github/workflows/<kebab-case>.yml` | `ci.yml`, `build-smoke.yml` |
| **Image / icon asset** | `kebab-case.<png\|svg>` (screenshots: see [documentation.md § 6](documentation.md)) | *(none yet)* |
| **Qt translation** | `finbreak_<locale>.ts` / `.qm` (Qt-mandated, §6) | *(added at the i18n packaging step)* |
| **Well-known root doc** | conventional UPPERCASE (§6) | `README.md`, `CHANGELOG.md`, `ROADMAP.md` |
| **Tool-mandated file** | exactly what the tool expects (§6) | `pyproject.toml`, `.gitignore`, `.gitleaks.toml` |
| **Packaging / build-recipe file** | tool/platform-mandated (§6): reverse-DNS app-ID, or app-named `.spec` | *(at the ADR-0007 packaging step: `io.github.<owner>.finbreak.desktop`, `finbreak.spec`)* |

*Hypothetical illustrations:* a Python module for CSV import would be
`csv_importer.py` (snake_case, multiword); a feature package whose natural
name is a Python keyword takes a trailing underscore — an `import`
feature becomes `tests/features/import_/` with `test_import.py` inside
(§4).


## 4. Python code, in detail

- Modules and packages: `snake_case` (PEP 8). A trailing underscore is
  used **only** to avoid shadowing a keyword or builtin — a feature
  package that would naturally be called `import` takes the name
  `import_` instead, because a bare `import/` collides with the `import`
  keyword. Use this sparingly and only when the natural name is a
  reserved word.
- Test files mirror their subject: a feature test dir is named for the
  domain concept it exercises (`accounts`, `categories`, `vault` — and
  `snake_case` if the concept is two words), and its test module is
  `test_<feature>.py`. Shared fixtures live in `conftest.py` (pytest's
  fixed name). Fixture **data** lives under `tests/fixtures/<rule>/` and,
  being data rather than imported code, is kebab-case.
- Schema migrations in this project are **in-code** — `snake_case`
  functions (`_migrate_to_v3`) in `migrations.py`, not separate
  per-migration files — so no migration-file naming scheme is needed.
- **In-code identifiers** are governed by PEP 8, not this file:
  `PascalCase` for classes, `snake_case` for functions / methods /
  variables, `UPPER_SNAKE_CASE` for module-level constants, a leading
  `_` for private members. Qt-specific idioms are in
  [coding.md § 5](coding.md). This standard is about the **file** the
  identifiers live in.


## 5. Docs, in detail

- **Kebab-case** for the words in a doc's name; the extension is `.md`.
- **ID-named docs** (specs, journals) are named for the roadmap item they
  belong to, using the **stable ID verbatim** — `FIBR-0006.md`. The
  project prefix is uppercase, the number is zero-padded to **four
  digits** (`FIBR-0006`, not `FIBR-6`), matching
  [roadmap-format.md § 3.5.1](roadmap-format.md).
- **ADRs** are `NNNN-kebab-title.md`: a **sequential** four-digit number
  (independent of the `FIBR-NNNN` roadmap counter — ADRs have their own
  0001-based sequence) plus a short kebab slug of the decision. First ADR
  is `0001-record-architecture-decisions.md`.
- **Standards** are a single lowercase word (or a hyphenated compound
  like `roadmap-format.md`) — the concern they govern.


## 6. When the name is not yours to choose

The categories below override §1's snake-vs-kebab **choice** — do **not**
rename these to fit the standard. (§1's first rule — a `.py` file or
imported package is `snake_case` because the name becomes a Python
identifier — is a language law and is *never* overridden; the overrides
here only apply to **non-`.py`** names.)

- **Conventional UPPERCASE documents** keep their ecosystem-wide spelling
  **in any directory** (not just the repo root — so `docs/standards/README.md`
  stays `README.md`, not `readme.md`). The core set: `README.md`,
  `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE` (or `COPYING`), `NOTICE`,
  `ROADMAP.md`, `CLAUDE.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`. Other
  long-standing all-caps convention files (`AUTHORS`, `INSTALL`, …) keep
  their ecosystem spelling too; anything **not** conventionally uppercase
  follows §1–§5.
- **Tool- / ecosystem-mandated files** are spelled exactly as the tool
  looks them up, whatever their case or separators:
  `pyproject.toml`, `.gitignore`, `.gitleaks.toml`, `.editorconfig`,
  `conftest.py`, `.github/workflows/`, `.github/FUNDING.yml`,
  `.github/dependabot.yml`, `.github/ISSUE_TEMPLATE/`,
  `PULL_REQUEST_TEMPLATE.md`. Renaming them silently disables the tool.
  The **PyInstaller** build recipe is an app-named `.spec` file
  (`finbreak.spec`) — Python *syntax* but never imported and often
  hand-edited, so it is tool-named, not `snake_case`d; if the project
  keeps it generated-and-gitignored instead, it falls under "generated
  files" below.
- **Packaging / desktop-integration files** use the platform's
  **reverse-DNS application ID** (dots, mixed case — mandated by
  freedesktop / Flatpak / AppStream), which deliberately overrides §2's
  lowercase + one-separator rules: `io.github.<owner>.finbreak.desktop`,
  `io.github.<owner>.finbreak.metainfo.xml`, the Flatpak manifest
  `io.github.<owner>.finbreak.yml`. The exact app-ID **and** the directory
  they live in are fixed when the packaging phase (ADR-0007) lands; until
  then, follow the reverse-DNS convention, not §1/§2. **Qt translation
  catalogs** likewise take Qt's `<app>_<locale>` form (`finbreak_de.ts` →
  `finbreak_de.qm`) — the `_<locale>` suffix is Qt-mandated.

If you're unsure whether a name is mandated, check the tool's docs before
inventing a variant. **Generated files** (e.g. `*.egg-info/`, a
gitignored PyInstaller `.spec`) keep whatever their tool emits — never
hand-rename them. A **`.gitkeep`** (the empty tracked file that keeps an
otherwise-empty directory in git) keeps that exact conventional name.


## 7. Directories

- Python package directories: `snake_case` (§4).
- Doc / infrastructure directories: lowercase, single word where possible
  (`docs/decisions/`, `docs/journal/`, `docs/specs/`, `docs/standards/`,
  `scripts/`), kebab-case if multiword.
- No trailing slashes, version numbers, or spaces in directory names —
  the same universal rules (§2) apply.


## 8. Anti-patterns (what NOT to do)

- ❌ `CsvImporter.py` / `csvImporter.py` — Python modules are never
  PascalCase or camelCase; that casing is for the **class inside**
  (the module is `csv_importer.py`, the class is `CsvImporter`).
- ❌ `csv-importer.py` — a hyphen makes the module unimportable.
- ❌ `docs/specs/fibr6.md` / `FIBR-6.md` — specs are the exact stable ID,
  zero-padded (`FIBR-0006.md`).
- ❌ `ci_local.sh` — shell scripts are kebab-case (`ci-local.sh`);
  reserve snake_case for `.py` files.
- ❌ `Design Doc (final).md` — spaces, parentheses, and "final" all
  forbidden; it's `design.md`.
- ❌ `readme.md` / `Readme.md` — `README.md` keeps its uppercase spelling
  in **any** directory, not just the repo root (§6).
- ❌ renaming `pyproject.toml`, `.gitignore`, a workflow, or a
  reverse-DNS packaging file to "match the standard" — those names are
  mandated (§6).


## 9. Project overrides

Project-specific tweaks go here, appended as a new subsection, per the
[standards README](README.md) convention. (None yet.)
