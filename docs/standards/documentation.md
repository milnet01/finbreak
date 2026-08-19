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

The **structure** of a spec or ADR is out of scope here; §§ 1–10
below are the whole of this standard. A project that writes specs
gets that shape from its own spec-format contract, wherever it
lives — in `docs/standards/` or supplied by the project's tooling.
Not having one at all is the finding; this omission is not.

| § | Governs |
|---|---|
| [1](#1-principles) | Principles every doc is held to |
| [2](#2-project-level-files) | README.md, CLAUDE.md, LICENSE/COPYING/NOTICE, SECURITY.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md |
| [3](#3-roadmapmd-and-changelogmd-formats) | ROADMAP / CHANGELOG high-level rules |
| [4](#4-api--contract-docs) | API / plugin / machine-readable contracts |
| [5](#5-in-code-documentation) | Comments and docstrings |
| [6](#6-screenshots) | Screenshot paths, filenames, formats |
| [7](#7-markdown-style) | Markdown style, including link targets |
| [8](#8-doc-reviews) | Doc-review cadence and fold-in |
| [9](#9-anti-patterns) | The scannable breach checklist |
| [10](#10-project-overrides) | This project's departures from the above |

**Normative force:** *must* / *required* is a rule — breaching it is a
defect. *Should* is a rule with a stated escape: depart from it and say
why in the doc. *Typical* / *avoid* is guidance, and a reader may weigh
it against the situation. A **bare imperative** or a *never* — "Caption
every screenshot", "never setext" — carries *must* force; most of §§ 4,
6 and 7 is written that way.


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

Three rules below (§ 2.4, § 2.5, § 2.6) apply only to a project **open
to outside participation**. That is two distinct halves, and they are
not the same population — a repo can take issues without taking
patches:

- **accepts issues** — outsiders can report bugs → § 2.4, § 2.6.
- **accepts patches** — outsiders can contribute code → § 2.5,
  § 2.6.

§ 2.6 is triggered by **either** half, because CONTRIBUTING.md
documents both how to file an issue and how to propose a change. A
project open to neither needs none of the three.

### 2.1 README.md

Required content blocks. Additional sections are allowed anywhere; the
blocks below must appear, and in this relative order. Items 1 and 2 are
**not headings** — a masthead block and a single prose line — so a
check that walks H2s starts at item 3:

1. **Masthead** — project name, one-line description, and badges
   *as available* (e.g. license; build once CI exists). The version
   is not a required badge — its canonical home is the
   Current-version line (item 2), per § 1.5.
2. **Current version** — a single line beginning `Current version:`
   followed by the version, with links to CHANGELOG, ROADMAP, and any
   companion docs. Decoration around the version (bold, a
   parenthetical) is fine; the leading text is the requirement.
3. **Features** — bulleted list of headline capabilities. The
   heading may be named for the project's maturity instead
   (`Status`, `What works today`); the bulleted list is the
   requirement, not the word.
4. **Install** — one-line install for each supported platform.
5. **Quickstart** — minimal command sequence to use the project.
6. **Plugin / extension** (if applicable) — link to the plugin
   author contract (`PLUGINS.md`, per § 4).
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

For a project that **accepts issues** (§ 2): disclosure policy,
contact email, GPG key (if used), supported-version table.

### 2.5 CODE_OF_CONDUCT.md

For a project that **accepts patches** (§ 2). Contributor Covenant
2.1 verbatim is the default; don't write your own unless the project
has a specific reason.

### 2.6 CONTRIBUTING.md

For a project open to outside participation, **either half** (§ 2):
build steps, test expectations, how to file issues, how to propose
features. Must point at every `*.md` in this folder **except
`README.md`**, which is the index. That set includes
`roadmap-format.md` — a sub-spec rather than a standard, and still
required. A link to the folder plus the full list by name satisfies
it; a partial list does not. Enumerate from the folder, never from
memory, or the list silently goes stale as files are added.


## 3. ROADMAP.md and CHANGELOG.md formats

The detailed format specs for both files — used by any tooling that
consumes them deterministically — live in
[`roadmap-format.md`](roadmap-format.md) (split out for
token efficiency; only relevant when authoring those files).

The high-level rules:

- `ROADMAP.md` is the single place to track unshipped work;
  shipped work moves to `CHANGELOG.md`.
- `ROADMAP.md` uses status emojis (✅🚧📋💭), theme emojis,
  and stable per-bullet IDs on the generic `PROJ-NNNN` pattern —
  the prefix is the project's, and the number is allocated by
  `roadmap_log` from the roadmap store, **not** read out of
  `.roadmap-counter` (see [roadmap-format § 3.5.1](roadmap-format.md),
  which owns the rule and the reason) — plus phase IDs (`P##`,
  `FP##`, `DS##`, `DOC##`, `R##`).
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
  what they can rely on. Example: `Added in X.Y.Z`.
- **Show input + output examples.** Type signatures alone aren't
  enough.
- **Mark deprecation explicitly.** `Deprecated since X.Y.Z; use
  Foo instead.`
- **Provide a migration path** for any deprecated / removed
  surface.


## 5. In-code documentation

Owned by [coding § 3](coding.md#3-comments) — read it there. In
short: default is no comments, only WHY non-obvious things need
them, and no multi-paragraph docstrings.


## 6. Screenshots

This section owns **screenshot** filenames specifically; general file &
directory naming (including other image / icon assets) is in
[naming.md](naming.md).

- **Path** — `docs/screenshots/` **or** `assets/screenshots/`.
  Pick one per project (record it in § 10) and use it for every
  screenshot (§ 1.5); two homes in one repo is the failure.
- **Filename** — `<feature>-<state>.png`
  (`import-preview-empty.png`, not `Screenshot 2026-04-28.png`).
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
  ❌ a markdown link whose target begins `~/` — resolves for nobody.
  ✅ "the workflow skill at `~/.claude/skills/app-workflow/SKILL.md`
  (machine-local)".
- Lists: `- ` for bullets, `1. ` for numbered. Don't mix `*` and
  `-` in one file.
- Inline code: backticks for filenames, function names, CLI
  flags.


## 8. Doc reviews

Schedule doc reviews independent from code reviews — the two drift
independently. Tie them to a trigger the project already has (a
release, a phase close, a dependency sweep) and record the chosen
trigger in § 10; "periodic" with no named trigger is not a rule
anyone can breach.

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

A scannable checklist of breaches. An entry that **cites a §** is an
index into that rule, which stays canonical (§ 1.5). An entry that
cites none is canonical **here** — this section is its only home.

- ❌ Lorem ipsum or placeholder text in committed docs.
- ❌ Screenshots that show the previous version's UI — § 6.
- ❌ "We" / "I" — use second person ("you") or impersonal third
  person ("the user").
- ❌ Markdown that doesn't render correctly on GitHub — preview the
  file on GitHub before committing.
- ❌ Documentation for a feature that hasn't shipped (goes in
  ROADMAP.md instead) — § 1.4.
- ❌ Stale CLI flag references — sweep every doc when a flag
  changes.
- ❌ Relative dates in committed docs (`recently`, `last week`) —
  § 1.3.
- ❌ A README so long a new contributor bounces off the page.


## 10. Project overrides

This standard is written to be copied verbatim into another project
(see the [standards README](README.md)), so everything above is
generic. Anything true only of **this** project goes here, appended as
a new bullet — mirroring [naming § 9](naming.md).

- **Screenshot home (§ 6)** — this project uses
  `assets/screenshots/`.
- **Roadmap ID prefix (§ 3)** — this project's bullets are
  `FIBR-NNNN`.
- **Doc-review trigger (§ 8)** — this project reviews docs as part
  of every debt sweep, which is itself triggered after five phases
  without one.


## Cold-eyes loop log

| Loop | Date | Lanes | C | H | M | L | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 2026-08-05 | 2 × general-purpose, cold, genre pinned `standard` | 0 | 3 | 7 | 7 | 17 verified, 8 unverified and dropped. All 17 fixed. Dimension tally: dim 2×4, dim 6×5, dim 4×3, dim 7×2, dim 5×2, dim 1×1. The run's own trigger (FIBR-0230's new § 7 link-target bullet) was itself found under-scoped — it bound only `~/…`, so an absolute path or a `file://` URL complied with the letter and broke for the same reader; broadened to any path outside the repository. § 2.6's "all four standards docs" and the masthead's four-peer list both dated from the P00 scaffold (2026-06-30), when four was right; `naming.md` and `dependencies.md` landed 2026-07-03 and neither line followed. `CONTRIBUTING.md` had already been built from the stale rule and listed four — fixed as collateral. § 2.6 now names no count at all, so it cannot rot again. § 8 restated four § 9 anti-patterns; reduced to a pointer plus its three unique items (delete N−1). Dropped as unverified: the README *does* link CHANGELOG + ROADMAP from its version line, its `## Status` *does* carry the capability list (a naming mismatch, not a missing section), and line 81 already says "machine-wide". Surfaced, not fixed: no `SECURITY.md` / `CODE_OF_CONDUCT.md` on a public repo accepting bug reports (project-side, not a doc edit), and the same stale peer-list in `coding.md` / `commits.md` / `testing.md` (three docs this run did not review — each edit would trip its own rule-14 gate). |
| 2 | 2026-08-05 | 2 × general-purpose, cold, genre pinned `standard` | 0 | 2 | 5 | 6 | 13 verified, 0 unverified. All fixed. Dimension tally: dim 6×4, dim 1×3, dim 7×2, dim 2×2, dim 11×2, dim 13×2, dim 4×1. Origin split: **7 fix collateral, 8 draft defects** — the loop earned itself. Both lanes independently led with the same collateral: loop 1 had written project-specific facts (`assets/screenshots/`, `FIBR-NNNN`) into a standard whose own index tells other projects to copy it *verbatim*, so every downstream copy would have shipped two false claims. `naming.md § 9` already had the pattern; § 10 Project overrides now mirrors it and holds both, plus the pre-existing tool-specific "Ants Terminal Roadmap dialog" reference and a product-specific filename example. Loop 1's § 2.5 rewrite asserted "the same trigger as § 2.4" — false, since accepting issues and accepting patches are different populations, and § 2.6 had a third phrasing; § 2 now defines one trigger in two named halves and all three cite it. Loop 1's "enumerate them from the folder" was unimplementable as written (the folder holds the index and a sub-spec too) — now "every `*.md` except `README.md`". Loop 1's scope sentence enumerated 3 of 8 governed sections, implying § 6 was out of scope while § 6 says it owns screenshot filenames; replaced by the § 1–10 table, which doubles as the TOC four lane-votes across both loops asked for. § 9 kept its complete checklist but now cites the owning rule on each entry that restates one, which is § 1.5's shape rather than a breach of it. Added a normative-force key (must / should / typical), the one gap no lane could work around: the doc mixed all three with nothing telling a conformer which bound them. |
| 3 | 2026-08-05 | 2 × general-purpose, cold, genre pinned `standard` | 0 | 1 | 8 | 6 | 15 verified, 0 unverified. All fixed. Dimension tally: dim 6×5, dim 4×5, dim 5×3, dim 13×1, dim 12×1. Origin split: **~8 fix collateral, ~3 draft defects** — a decisive margin, and the stop signal. Every one of loop 2's five structural additions came back defective: the normative-force key classified three registers while §§ 4/6/7 are written in a fourth (bare imperatives), so the key left the doc's dominant rule form unclassified — the exact gap it was added to close; the § 2 trigger gate routed § 2.6 to *accepts patches* only, while § 2.6's own body requires documenting how to file issues, so an issues-only project was told to ship nothing about issues; "every `*.md` except `README.md`" silently reclassified `roadmap-format.md` as a standard, contradicting this doc's own line 10 calling it a sub-spec; the § 9 preamble claimed every entry indexes a rule above, when five of eight (the voice rule, GitHub rendering, lorem ipsum, stale flags, README length) exist nowhere else and are canonical in § 9; and the TOC row omitted `COPYING` / `NOTICE` and used an unexpanded "CoC". § 8 gained a named recording home in § 10 mirroring § 6's, closing a rule that was literally unbreachable — the failure its own last clause names. Also resolved: `coding.md § 3` does own the docstring rule (both lanes queried it), so § 5's deferral was correct and only wanted the anchor. **Stopped here rather than dispatching loop 4** — three loops running, collateral now outnumbers draft defects better than 2:1, so the remaining yield is repair of repair. |
