<!-- ants-doc-standards: 1 -->
# Documentation Standards — v1

Documentation contract for this project. Pairs with
[coding](coding.md), [naming](naming.md),
[dependencies](dependencies.md), [testing](testing.md),
[commits](commits.md); see the [index](README.md). Governs
`Kind: doc` / `doc-fix` bullets. What to **name** a doc file (specs,
ADRs, journals, design docs) is in [naming.md](naming.md); ROADMAP.md
and CHANGELOG.md format details live in a separate sub-spec at
[`roadmap-format.md`](roadmap-format.md).

The **structure** of a spec or ADR is out of scope here — this
standard governs project-level files (§ 2), API contracts (§ 4) and
markdown style (§ 7). A project that writes specs supplies its own
spec-format contract and names it in `CLAUDE.md`; having none is the
finding, not this omission.


## 1. Principles

### 1.1 Six-month test

A reader six months from now should be able to use the doc
without the author present. If the doc says "see the recent
change", that won't be true in six months — replace with a
durable reference (`src/foo.py::bar()`, or a doc's section
heading).

### 1.2 Show, don't claim

Examples beat prose. A README that *shows* the command + expected
output beats one that *describes* what the command does. Code
blocks should be runnable as-is.

### 1.3 Date format — ISO 8601

`YYYY-MM-DD`. No `Apr 28 2026`, no `28/04/2026`, no relative dates
(`yesterday`, `last week`) in committed docs. Relative dates rot.

### 1.4 Don't reference what isn't shipped

Doc lands when the feature lands. Forward-references to unshipped
features go in `ROADMAP.md`, not `README.md` and not the standards
in this folder.

### 1.5 One source of truth per fact

Don't repeat the install steps in README + INSTALL + CONTRIBUTING
+ SETUP. Pick the canonical home; cross-link from the others.


## 2. Project-level files

### 2.1 README.md

Required sections. Additional sections are allowed anywhere; the
ones below must appear, and in this relative order:

1. **Masthead** — project name, one-line description, and badges
   *as available* (e.g. license; build once CI exists). The version
   is not a required badge — its canonical home is the
   Current-version line (item 2), per § 1.5.
2. **Current version** — single line: `Current version: X.Y.Z`
   with links to CHANGELOG, ROADMAP, and any companion docs.
3. **Features** — bulleted list of headline capabilities. The
   heading may be named for the project's maturity instead
   (`Status`, `What works today`); the bulleted list is the
   requirement, not the word.
4. **Install** — one-line install for each supported platform.
5. **Quickstart** — minimal command sequence to use the project.
6. **Plugin / extension** (if applicable) — link to the plugin
   author contract.
7. **Documentation** — links to `docs/`, including the standards
   folder.
8. **License** — single line + link.

Avoid: a TOC for a short README; "About" / "Why" sections without
content; broken screenshot links.

### 2.2 CLAUDE.md

For projects worked on with Claude Code: the project-specific
instructions Claude should follow. Lives at the repo root.
Typical contents:

- Module map (one line per major subsystem).
- Build instructions.
- Testing instructions.
- Conventions specific to this codebase.
- Key design decisions that aren't obvious from reading the code.

Keep it terse — the global `~/.claude/CLAUDE.md` covers
machine-wide rules; this file only covers project-specific ones.

### 2.3 LICENSE / COPYING / NOTICE

Standard files at the repo root. Use the SPDX-tagged canonical
license text — don't paraphrase.

`LICENSE` is required. `COPYING` is the GNU-convention alias for the
same file — ship one, never both. `NOTICE` only where a bundled
dependency's license requires it.

### 2.4 SECURITY.md

For projects that accept external bug reports: disclosure policy,
contact email, GPG key (if used), supported-version table.

### 2.5 CODE_OF_CONDUCT.md

For projects that accept external contributions — the same trigger
as § 2.4. Contributor Covenant 2.1 verbatim is the default; don't
write your own unless the project has a specific reason. A solo or
private project needs none.

### 2.6 CONTRIBUTING.md (optional)

For projects accepting external contributors: build steps, test
expectations, how to file issues, how to propose features. Should
link to **every** standard in this folder — enumerate them from the
folder, not from memory, or the list silently goes stale as
standards are added.


## 3. ROADMAP.md and CHANGELOG.md formats

The detailed format specs for both files — used by the Ants
Terminal Roadmap dialog and any tooling that consumes them
deterministically — live in
[`roadmap-format.md`](roadmap-format.md) (split out for
token efficiency; only relevant when authoring those files).

The high-level rules:

- `ROADMAP.md` is the single place to track unshipped work;
  shipped work moves to `CHANGELOG.md`.
- `ROADMAP.md` uses status emojis (✅🚧📋💭), theme emojis,
  and stable per-bullet IDs (the generic `PROJ-NNNN` pattern from
  `.roadmap-counter` — `FIBR-NNNN` in this project) plus phase IDs
  (`P##`, `FP##`, `DS##`, `DOC##`, `R##`).
- `CHANGELOG.md` follows
  [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with
  an `[Unreleased]` block at the top.

For details — including the format-version comment, theme
emoji set, current-work signalling rules, bullet contract, and
release flow — read [`roadmap-format.md`](roadmap-format.md).

## 4. API / contract docs

For any project that exposes an API, a plugin contract, or a
machine-readable surface (`PLUGINS.md`, `API.md`,
`openapi.yaml`):

- **Document every public symbol.** If a function is exported,
  it's part of the contract.
- **Include the version it was added in.** Helps consumers know
  what they can rely on. Example: `Added in 0.6.5`.
- **Show input + output examples.** Type signatures alone aren't
  enough.
- **Mark deprecation explicitly.** `Deprecated since X.Y.Z; use
  Foo instead.`
- **Provide a migration path** for any deprecated / removed
  surface.


## 5. In-code documentation

Defer to [coding § 3](coding.md). Default is no comments; only
WHY non-obvious things need them. Don't write multi-paragraph
docstrings.


## 6. Screenshots

This section owns **screenshot** filenames specifically; general file &
directory naming (including other image / icon assets) is in
[naming.md](naming.md).

- **Path** — `docs/screenshots/` **or** `assets/screenshots/`.
  Pick one per project and use it for every screenshot (§ 1.5); two
  homes in one repo is the failure. This project uses
  `assets/screenshots/`.
- **Filename** — `<feature>-<state>.png`
  (`terminal-tabs-active.png`, not `Screenshot 2026-04-28.png`).
- **Format** — PNG for UI, JPG for photographic content.
- **Caption** every screenshot in the surrounding prose.
- **Replace, don't accumulate.** When the feature changes, swap
  the screenshot. Don't pile up `_old` / `_v2` versions.


## 7. Markdown style

- ATX headings (`# `, `## `, `### `) — never setext (`====`).
- At least one blank line before and after headings.
- Tables for structured data, fenced code blocks for code.
- Line wrap at ~70–80 columns for readability in `git diff`.
  Don't force-wrap inside code blocks or tables.
- Links: `[text](url)` not `<url>`, unless the URL itself is
  meant as the visible text.
- Link targets must resolve for a reader who is not on this
  machine — GitHub, a previewer and an editor all follow the same
  target. Any path outside the repository — `~/...`, an absolute
  path, a `file://` URL — goes in inline code, with the prose
  saying where it lives, and never in a link target.
- Lists: `- ` for bullets, `1. ` for numbered. Don't mix `*` and
  `-` in one file.
- Inline code: backticks for filenames, function names, CLI
  flags.


## 8. Doc reviews

Schedule doc reviews independent from code reviews — the two drift
independently. Tie them to a trigger the project already has (a
release, a phase close, a dependency sweep); "periodic" with no
named trigger is not a rule anyone can breach.

Every § 9 anti-pattern is in scope for the sweep — they are stated
there, not restated here. Beyond those, a doc review surfaces:

- Sections that document a feature that was removed.
- Cross-references to renamed files / functions.
- ROADMAP / CHANGELOG bullets whose claims don't match the
  shipped code.

Findings from a doc review fold into the ROADMAP under
`### 📚 Documentation review fold-in (YYYY-MM-DD)` — see
[roadmap-format § 3.8](roadmap-format.md#38-findings-fold-in-subsections).


## 9. Anti-patterns

- ❌ Lorem ipsum or placeholder text in committed docs.
- ❌ Screenshots that show the previous version's UI.
- ❌ "We" / "I" — use second person ("you") or impersonal third
  person ("the user").
- ❌ Markdown that doesn't render correctly on GitHub (test it).
- ❌ Documentation for a feature that hasn't shipped (goes in
  ROADMAP.md instead).
- ❌ Stale CLI flag references — sweep every doc when a flag
  changes.
- ❌ Relative dates in committed docs (`recently`, `last week`).
- ❌ A README so long a new contributor bounces off the page.


## Cold-eyes loop log

| Loop | Date | Lanes | C | H | M | L | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 2026-08-05 | 2 × general-purpose, cold, genre pinned `standard` | 0 | 3 | 7 | 7 | 17 verified, 8 unverified and dropped. All 17 fixed. Dimension tally: dim 2×4, dim 6×5, dim 4×3, dim 7×2, dim 5×2, dim 1×1. The run's own trigger (FIBR-0230's new § 7 link-target bullet) was itself found under-scoped — it bound only `~/…`, so an absolute path or a `file://` URL complied with the letter and broke for the same reader; broadened to any path outside the repository. § 2.6's "all four standards docs" and the masthead's four-peer list both dated from the P00 scaffold (2026-06-30), when four was right; `naming.md` and `dependencies.md` landed 2026-07-03 and neither line followed. `CONTRIBUTING.md` had already been built from the stale rule and listed four — fixed as collateral. § 2.6 now names no count at all, so it cannot rot again. § 8 restated four § 9 anti-patterns; reduced to a pointer plus its three unique items (delete N−1). Dropped as unverified: the README *does* link CHANGELOG + ROADMAP from its version line, its `## Status` *does* carry the capability list (a naming mismatch, not a missing section), and line 81 already says "machine-wide". Surfaced, not fixed: no `SECURITY.md` / `CODE_OF_CONDUCT.md` on a public repo accepting bug reports (project-side, not a doc edit), and the same stale peer-list in `coding.md` / `commits.md` / `testing.md` (three docs this run did not review — each edit would trip its own rule-14 gate). |
