<!-- ants-roadmap-format-spec: 1 -->
# ROADMAP.md & CHANGELOG.md format spec (v1)

> Detailed format spec for the two files the Ants Terminal Roadmap
> dialog parses deterministically. Extracted from
> [`documentation.md`](documentation.md) so the documentation standard
> can stay short for projects that don't use the Ants viewer.
>
> Read this file when authoring a `ROADMAP.md` bullet, a `CHANGELOG.md`
> entry, or any tooling that consumes either format. Skip otherwise.
>
> **Section numbers** start at § 3: this sub-spec was extracted from
> `documentation.md` (§ 1–2 live there) and keeps its original
> numbering so existing `documentation.md § 3 / § 4` cross-references
> stay valid.

## 3. ROADMAP.md format spec

A shareable contract for `ROADMAP.md` files. Following this
sub-spec is **required** for any roadmap intended to render
correctly in the Ants Terminal Roadmap dialog or be parsed
deterministically by LLM agents.

The roadmap is the single place to track unshipped work. A
shipped bullet is **not deleted** — it stays where it is as ✅
under a block retitled `shipped (YYYY-MM-DD)` (§3.7), and it is
the *user-facing* record of the work that moves to the
CHANGELOG.

### 3.1 File header

A conforming file declares the format version with an HTML
comment in the **first five lines**:

```markdown
<!-- ants-roadmap-format: 1 -->
# MyProject — Roadmap
```

Parsers look for the marker; if absent, they fall back to
best-effort parsing. Conforming files render with a `(format v1)`
badge in the Roadmap dialog footer.

### 3.2 Heading hierarchy

| Level | Use | Example |
|-------|-----|---------|
| `#` | File title (one per file) | `# MyProject — Roadmap` |
| `##` | Release block (post-1.0) **or** phase block (pre-1.0) | `## 0.7.0 — shell integration` / `## P01 — Bootstrap` |
| `###` | Theme group within a release/phase | `### 🎨 Features` |
| `####` | Optional subgroup | `#### Tier 1 — ship-this-week` |

The Roadmap dialog treats `##` as a top-level boundary (release
or phase), `###` as the theme filter, `####` as a fold-out.
Pre-1.0 projects use phase blocks (`## P01 — Bootstrap`) since
there's no real version to anchor to yet; phase blocks promote
naturally to release blocks once the project ships 1.0 (the work
under `P01` becomes the body of `## 1.0.0 — initial release`).

**Headings are addressable.** The viewer auto-generates anchor
names of the form `roadmap-toc-N` based on heading position. For
stable cross-references, embed an explicit anchor:

```markdown
<a name="release-0-7-0"></a>
## 0.7.0 — shell integration (target: 2026-06)
```

Explicit anchors take precedence and survive heading edits.

### 3.3 Status emojis

Every actionable bullet starts with one of four status emojis:

| Emoji | Meaning |
|-------|---------|
| ✅ | Done / shipped |
| 🚧 | In progress (being tackled now) |
| 📋 | Planned (next up) |
| 💭 | Considered (research phase; scope or feasibility uncertain) |

Plain narration bullets without a status emoji are allowed but
won't match any status filter — they render as context-only.

**Status transitions** follow `💭 → 📋 → 🚧 → ✅`. A bullet can
skip 🚧 if the work is small enough to ship in one commit, but
the expectation is "💭 means we don't know yet, 📋 means it's
queued, 🚧 means I'm doing it right now, ✅ means it's shipped."

### 3.4 Theme emojis

Theme emoji prefixes the level-3 (`###`) section heading:

| Emoji | Theme |
|-------|-------|
| 🎨 | Features (user-visible capabilities) |
| ⚡ | Performance |
| 🔌 | Plugins / extensibility |
| 🖥 | Platform (ports, accessibility, OS-specific) |
| 🔒 | Security |
| 🧰 | Dev experience (tooling, tests, build, CI) |
| 📚 | Documentation (user docs, dev docs, READMEs, contracts) |
| 📦 | Packaging & distribution |
| 🐛 | Bug fixes / regressions |
| 🔍 | Audit / review findings fold-in |
| 🧹 | Cleanup / debt — dead code, stale comments, drift, deferred housekeeping |

Projects MAY introduce additional theme emojis; the viewer's
filter panel surfaces any emoji it sees in any `###` heading.

### 3.5 Bullet structure

```markdown
- 📋 [PROJ-0123] **One-line headline ending with a period.** Body
  spanning as many lines as needed; lines wrapped to roughly 70
  columns. Cite `file:line` in backticks when relevant. End with
  a `Lanes:` line declaring which subsystems own the work.
  Kind: implement.
  Lanes: SubsystemA, SubsystemB.
```

Required pieces:

- **Status emoji** — first character after `- `.
- **Stable ID** — `[PROJ-NNNN]` immediately after the emoji.
- **Bold headline ending in a period** — stands alone as a
  one-line summary; this is what the dialog filters and the LLM
  agent reads first. **It must occupy a single source line.** A
  wrapped headline renders its continuation at column 0, which
  markdown reads as a new list item, so the bullet splits and the
  parser harvests a truncated headline plus an orphan.
- **`Kind: <kind>.`** — declares the type of work. One of the
  ten values in §3.5.3. **Required on every bullet, with no
  exception and no section-level default**, so the Roadmap
  viewer (and any tooling that consumes the file
  deterministically) can categorise in one pass without
  inferring from the surrounding section heading.

Optional pieces:

- **Body prose** — free-form, after the bold headline.
- **`Lanes: X, Y, Z`** — declares ownership; helps subagents
  find test files.
- **`Source: <source>`** — declares where the item came from,
  when the section heading doesn't already make that clear. See
  §3.5.3.
- **Sub-bullets** — for parametrised work (e.g. "implement for X
  / Y / Z").

#### 3.5.1 Stable IDs — `[PROJ-NNNN]`

The ID is a project-prefixed monotonic integer:

- **Prefix** — 2–6 ASCII characters, all caps, first character
  a letter; digits allowed after it. One per project. Pick
  something short and grep-friendly. Examples: `ANTS`, `MYPRJ`,
  `ENGINE`, `OBS`, `R5`.
- **Number** — zero-padded to 4 digits minimum (`0001`, `0042`,
  `1234`). Pad wider once a project crosses 9999.
- **Append-only** — once assigned, an ID never changes. It
  survives rewording, moving, status flips, and even being
  deleted (a deleted ID is *retired*; the next new bullet uses
  the next free number, not the deleted one).

**Who allocates an ID depends on whether the roadmap is
store-backed.** On this project it is: `ROADMAP.md` is *rendered*
from the Ants roadmap DB, and `roadmap_log` allocates the next ID
from that store and returns it in the write envelope. **That is
the only sanctioned allocator here.** Never read a number out of
a file and write it into a bullet by hand.

`.roadmap-counter` at the project root is a **cache of the
high-water mark, not the allocator**, and three things follow:

- **It is not checked in here.** `.gitignore` has excluded it
  since 2026-07-14 (commit `0b5c995`) on the grounds that it is
  re-derived from `ROADMAP.md` when absent, so a fresh clone has
  no counter at all and nothing is lost.
- **It lags.** `roadmap_log op:"append"` reconciles it and says
  so in its envelope (`counter_advanced_to`); `op:"append_batch"`
  allocates the same way and does not reconcile it at all. Measured 2026-08-19: the
  file read `288` while `FIBR-0291` was already on the roadmap.
- **So counter arithmetic is not a way to allocate an ID.** A
  session that reads the counter and adds one names an ID that
  already belongs to another bullet — permanently, because IDs
  are append-only and a pushed commit cannot be rewritten.

A project whose `ROADMAP.md` is a plain hand-maintained file with
no store behind it has no other carrier, and there the counter
*is* the high-water mark. Check which kind of project you are in
before reaching for the recipe below — on a store-backed one it
allocates a collision:

```bash
# FALLBACK ONLY, for a project with no roadmap store behind
# ROADMAP.md. Not this project — use roadmap_log here.
echo $(($(cat .roadmap-counter) + 1)) > .roadmap-counter
printf "PROJ-%04d\n" $(cat .roadmap-counter)
```

#### 3.5.2 Insertion order vs numbering

This is the rule that everything else hangs on:

> **Execution order is positional. Numbering is identity.**

Items in a section are executed **top-to-bottom**, regardless of
their IDs. The ID identifies the bullet permanently; the
position in the file declares its priority. When new items are
inserted (e.g. a `check-code` finding):

1. **Insert at the position they should be tackled.** A
   CRITICAL audit finding goes near the top of the active
   release block (under the Tier-1 heading if one exists). A LOW
   finding goes lower. The author *chooses* the position based
   on priority.

   **This step applies only where `ROADMAP.md` is
   hand-maintained.** On a store-backed project (§3.5.1) it is
   not available: `roadmap_log` appends to the end of the named
   section and takes no positional locator, and a hand edit that
   moves a bullet is reverted by the next render. There, step 3
   below is not decoration — the `Priority:` line is the only
   carrier of priority the file has.
2. **Assign the next free ID.** Don't shuffle existing IDs to
   keep the section monotonic — that's the anti-pattern this
   sub-spec prevents.
3. **Document the priority in the bullet body.** A line like
   `Priority: CRITICAL — security blocker` makes the position
   choice auditable.

This means a section's IDs may be **non-monotonic** in document
order (e.g. `0003, 0017, 0004, 0012`). That is correct and
expected. The agent reads the file top-to-bottom and works the
items in that order.

#### 3.5.3 Kinds and Sources

The numbering system itself is uniform — every actionable bullet
gets exactly one ID, regardless of what kind of work it
represents. But different kinds of work have different
follow-through (a documentation fix doesn't need a regression
test; an audit-fix does), and different sources need
traceability (a finding from a user report should remain
attributable years later). Two metadata fields cover this without adding
complexity to the bullet's surface form: `Kind:` on every
bullet, `Source:` wherever it is not `planned`.

**Recognised `Kind:` values:**

| Kind | Meaning | Follow-through |
|------|---------|----------------|
| `implement` | New code for a planned feature | tests + changelog + docs |
| `fix` | Code change to repair a bug | regression test + changelog |
| `audit-fix` | Code change in response to an audit finding | regression test + changelog (cite finding source) |
| `review-fix` | Code change in response to an indie-review or peer review | regression test + changelog (cite reviewer source) |
| `doc` | New / updated documentation, no code | changelog if user-facing |
| `doc-fix` | Documentation correction (typo, stale ref, drift) | no test, changelog optional |
| `refactor` | Code reshape with no behavior change | tests must still pass; usually no changelog |
| `test` | Test-only change (new spec, new fixture, harness improvement) | no changelog |
| `chore` | Housekeeping (deps, build flags, generated files) | no test, changelog optional |
| `release` | Version bump, packaging files, tag | drives the release skill |

**Required** — every actionable bullet declares its
`Kind:` explicitly, even when the surrounding section makes the
default obvious. Section context is a hint for human readers;
machine consumers (the Roadmap dialog, the App-Build runner,
any tooling that filters / counts / reports by Kind) need the
field on every bullet so the parser stays simple and one-pass.
A backfill pass over the active roadmap is a `Kind: doc-fix`
item.

**Recognised `Source:` values.** Unlike `Kind:`, this list is
**open**: a project MAY add a value of its own on the same
`<origin>-YYYY-MM-DD` shape, so a filter over `Source:` must be
written to pass an unrecognised value through rather than reject
it. (This project already carries `Source: in-session-YYYY-MM-DD`,
which is not in the table below.)

| Source | Meaning |
|--------|---------|
| `planned` | On the roadmap from project design (default; usually omitted) |
| `user-YYYY-MM-DD` | User report on date YYYY-MM-DD |
| `audit-YYYY-MM-DD` | `check-code` skill output on date YYYY-MM-DD |
| `indie-review-YYYY-MM-DD` | `review-code` skill output on date YYYY-MM-DD |
| `debt-sweep-YYYY-MM-DD` | `debt-sweep` skill output on date YYYY-MM-DD |
| `doc-review-YYYY-MM-DD` | Documentation review on date YYYY-MM-DD |
| `static-analysis` | ruff / bandit / semgrep ad-hoc (or other language-appropriate analysers) |
| `regression` | Item was previously ✅ but a later change broke it |
| `external-CVE-NNNN-NNNN` | Public CVE / advisory triggering this work |
| `upstream-<dep>` | Driven by a dep / library upstream change |

Most `debt-sweep` findings get fixed inline during the sweep
itself (the skill's "trivial" bucket goes straight into a
`chore: post-X.Y.Z debt sweep` commit) and never reach the
roadmap. Only items the user must rule on (the "behavioural"
bucket) or items deferred as out-of-scope land here. Use
`🧹 Debt-sweep fold-in (YYYY-MM-DD)` as the section heading and
`Source: debt-sweep-YYYY-MM-DD` if declared explicitly.

A bullet with no `Source:` is `planned` — the overwhelming
majority case, so the format stays terse for it. **`Kind:` has no
matching default.** It is written on every bullet, because a
parser that infers it from the section heading is no longer
one-pass, and two readers of the same file would disagree about
what a Kind-less bullet counts as.

#### 3.5.4 LLM-agent execution contract

When an LLM agent (Claude Code, Codex, etc.) is told *"work the
roadmap"*, it MUST:

1. Read the file top-to-bottom.
2. Find the **active block** — the first `##` in document
   order containing any 📋 or 🚧 item. This is stated in
   document order rather than by version because §3.2 sanctions
   phase blocks (`## P01 — Bootstrap`) for pre-1.0 projects, and
   those cannot be ordered by version; a `##` section holding no
   status bullets at all (`## How to add an item`) is not a
   block and is skipped.
3. Within the active block, find the first 🚧 or 📋 bullet under
   each `###` theme section, prioritising 🚧. **Never start a 💭
   item** — that status means scope or feasibility is still
   uncertain (§3.3), so it is flipped to 📋 by a human before
   anyone builds it.
4. Tackle bullets in document order — *not* in ID order.
5. When inserting new bullets (e.g. from an audit), follow
   §3.5.2.

Do **not** "jump around" by ID. Do **not** reorder existing
items to fit a perceived priority — let the human author make
priority decisions through positioning.

### 3.6 Current-work signaling

The Roadmap dialog marks a bullet as "currently being tackled"
using three signals OR'd together:

#### 3.6.1 Primary — 🚧 status emoji

Author flips the bullet's emoji from 📋 to 🚧 when starting, and
from 🚧 to ✅ when shipping. This is the **canonical,
author-controlled** signal — every other mechanism is an
augmenter.

**One bullet, one author.** A repository should have at most a
small handful of 🚧 bullets at any time (typical: 1–3). Many 🚧
bullets is a smell — either work is fragmented or the author has
stopped shipping.

#### 3.6.2 Secondary — `CHANGELOG.md` `[Unreleased]` block

The viewer reads the project's `CHANGELOG.md` for an
`[Unreleased]` section (Keep-a-Changelog convention; see §4).
Bullets in `[Unreleased]` are fuzzy-matched against ROADMAP
bullet headlines (lowercase, hyphens as spaces, punctuation
stripped). Matches get the highlight even if their emoji hasn't
been flipped to 🚧.

This catches the case where the author writes the changelog
entry before updating the roadmap.

#### 3.6.3 Tertiary — recent commit subjects

The last 5 non-merge / non-revert / non-release-bump commit
subjects on the current branch are fuzzy-matched against bullet
headlines. A match adds the highlight.

Useful for "I just committed this; mark it as in-progress before
I write the changelog" workflows.

### 3.7 Release blocks

A release block is a `##` heading naming a version + theme +
target date:

```markdown
## 0.7.0 — shell integration (target: 2026-06)

**Theme:** OSC 133 + trigger system + project-audit dashboard.
```

The `**Theme:**` line is optional but recommended — it gives
the filter dialog one-line context per release.

Released versions move from `(target: YYYY-MM)` to
`shipped (YYYY-MM-DD)`. The viewer treats released blocks as
read-only: items under them are expected to be ✅ and don't
appear in the 📋/🚧/💭 filters.

### 3.8 Findings fold-in subsections

When an external review produces new items — `check-code`,
`review-code`, a documentation review, a user bug report,
static-analysis run, an upstream advisory — fold them into a
dedicated `###` subsection inside the active release block, with
date and source stamped on the heading. The pattern is the same
regardless of where the finding came from; only the theme emoji
and heading wording change.

```markdown
### 🐛 Regressions reported post-0.7.55 (user, 2026-04-28)

- 📋 [ANTS-0512] **HIGH — Background-tasks button no longer shows up.**
  …

### 🔍 Audit fold-in (2026-04-28)

- 📋 [ANTS-0518] **CRITICAL — SARIF export not atomic.** …

### 🔍 Indie-review fold-in (2026-04-23)

- 📋 [ANTS-0521] **HIGH — TerminalGrid / TerminalWidget cohesion smell.**
  …

### 📚 Documentation review fold-in (2026-04-15)

- 📋 [ANTS-0530] **PLUGINS.md OSC 8 surface mismatches code.**
  Doc says `osc-8-handler`, code uses `osc8-handler`.
  Kind: doc-fix.
  Lanes: docs.

### 🐛 Static-analysis fold-in (2026-04-12)

- 📋 [ANTS-0535] **MEDIUM — bandit `B608` possible SQL injection.** …

### 🧹 Debt-sweep fold-in (2026-04-28)

Trivial findings were fixed inline during the sweep — see
`chore: post-0.7.55 debt sweep` commit. The bullets below are
the "behavioural" findings the user opted to defer.

- 📋 [ANTS-0540] **Invariant list grew but spec.md unchanged.**
  `tests/features/vt_throughput/`. Kind: test. Lanes: tests.
- 📋 [ANTS-0541] **`README.md § Plugins` cites a removed verb.**
  It names `ants.fs.read`. Kind: doc-fix. Lanes: docs.
```

Conventions for any findings fold-in:

- **Choose the theme emoji from §3.4.** 🐛 for bug-shaped
  findings, 🔍 for audit/review fold-ins as a whole, 📚 for doc
  reviews, 🔒 if security-only, 📦 if packaging.
- **Date-stamp the heading** — `(YYYY-MM-DD)`.
- **Source-stamp the heading** — `(user, …)`, `(audit, …)`,
  `(indie-review, …)`, `(static-analysis, …)`,
  `(doc-review, …)`, `(bandit, …)`, etc.
- **Severity in the headline** — `**CRITICAL — …**`,
  `**HIGH — …**`, `**MEDIUM — …**`, `**LOW — …**`.
- **Position by priority** — Tier-1 / CRITICAL items go above
  existing Tier-2 / HIGH items.
- **`Source:` may be left to the fold-in heading, which already
  names it. `Kind:` may not — write it on every bullet (§3.5.3).**

### 3.9 ROADMAP anti-patterns

- ❌ Status emoji other than ✅ 🚧 📋 💭. Tools won't recognise
  them.
- ❌ Renumbering items when inserting. The whole point of stable
  IDs is to defeat this temptation.
- ❌ Multiple status emojis on one bullet (`✅ 📋 …`).
- ❌ Reordering bullets by ID. Position is priority; numerical
  order is not.
- ❌ More than ~3 🚧 bullets simultaneously.
- ❌ Mixing `[ ]` / `[x]` task-list syntax with the emoji
  status system.


## 4. CHANGELOG.md format spec

A conforming project keeps a Keep-a-Changelog-style
`CHANGELOG.md` at the repo root. The format is defined at
<https://keepachangelog.com/> and pinned here as a sub-spec.

### 4.1 Structure

```markdown
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New feature.

### Fixed
- Bug fix.

## [X.Y.Z] — YYYY-MM-DD

**Theme:** one-line summary of the release.

### Added
…

### Changed
…

### Fixed
…

### Removed
…

### Security
…

## [X.Y.Z-1] — YYYY-MM-DD
…
```

### 4.2 Conventions

- `[Unreleased]` block at the top, **always** — even if empty.
  The ROADMAP viewer reads it for current-work signaling per
  §3.6.2.
- Dated sections in **reverse chronological order**.
- `**Theme:**` line is one sentence; sets the release's
  character.
- Bullets categorical: Added / Changed / Deprecated / Removed /
  Fixed / Security — the six Keep a Changelog 1.1.0 defines, and
  the six `changelog_log` accepts. Don't invent new categories.
- Bullets terse — one line each. Body paragraphs go in commits.
- **Cite ROADMAP IDs** in bullets when applicable: `Added: live
  search filter (ANTS-1042).`. The bidirectional link helps
  readers move between the changelog and the roadmap.

### 4.3 Release flow with ROADMAP integration

When a release ships:

1. `[Unreleased]` block contents move to a new dated section
   `## [X.Y.Z] — YYYY-MM-DD`.
2. Empty `[Unreleased]` section is left at the top (with an
   empty-state hint or just the heading).
3. ROADMAP bullets that were 🚧 flip to ✅.
4. Released ROADMAP block changes from `(target: YYYY-MM)` to
   `shipped (YYYY-MM-DD)`.

The `cut-release` skill automates steps 1–4 where a project
uses it.



## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Outcome |
|---|---|---|---|---|---|---|
| 1 | 2026-08-19 | 3 × `review-lane`, cold, genre pinned `standard`; packet carried the live counter/store measurements, the skill and command inventory, and the quoted `documentation.md` and `CLAUDE.md` windows | 1 | 8 | 1 | **Ten verified, ten fixed; none dismissed.** First gate ever run on this file (FIBR-0288). **Three defects were found independently by all three lanes**, the strongest signal in the run. **The most consequential is § 3.5.4 step 2**, which told an agent to work "the lowest version `##`" — while § 3.2 sanctions phase blocks for pre-1.0 projects and *every* `##` in this project's roadmap is `## P01`…`## P13`. So the execution contract had no defined starting block on exactly the projects § 3.2 says will use phase blocks: one runner stops, another picks arbitrarily. Restated as the first `##` in document order carrying a 📋 or 🚧, with non-work sections skipped (`## How to add an item` holds 0 status bullets, measured). **The `Kind:` contradiction was four-way and had been live since extraction**: § 3.5 and § 3.5.3 said **Required**, § 3.5.3's own opening called both fields "optional", a paragraph four lines later gave Kind-less bullets a silent `implement` default, § 3.9 said the lines are "usually inherited from the section", and the canonical example at § 3.5 carried no `Kind:` line at all. A validator built from one branch rejects what the other mandates; live data shows the split is real (256 `Kind:` lines against 284 rendered items). Settled toward Required — the store-backed writer demands `kind` on append — by deleting the default and the inheritance line and adding `Kind:` to the canonical bullet. The `Source: planned` default is true and was kept. **The prefix rule breached itself in the same sentence**: "4–6 ASCII letters, all caps" beside the examples `OBS` (3 letters) and `R5` (a letter and a digit), so a validator built from the rule rejects two IDs the standard offers as valid. Rule widened rather than examples dropped. **Two lanes found that this run's own § 3.5.1 fix had orphaned its neighbours** — § 3.5.2 and § 3.5.4 still taught hand-editing `ROADMAP.md` to place a bullet by priority, which on a store-backed project is reverted by the next render; `roadmap_log` appends to the end of a section and takes no positional locator, so position is not authorable there and the `Priority:` line is the only carrier. **One lane alone found step 3 admitted 💭** ("the first non-✅ bullet"), which starts research-phase work whose feasibility the author flagged as unknown; and **one alone found § 3.8's own example carries a wrapped bold headline**, the exact shape user decision FIBR-0281 forbids because the continuation renders at column 0 and splits the bullet. **Three found by the orchestrator:** § 3 said released work "moves out of the roadmap", while § 3.7 and § 4.3 retitle the block and keep the ✅ bullets in place (284 items rendered, ✅ included) — a release runner built from § 3 deletes them; § 4.2 closed the changelog categories to five while § 4 pins Keep a Changelog **1.1.0**, which defines six — `Deprecated` had no sanctioned home although this project's own `CHANGELOG.md` header and the `changelog_log` verb both carry it (verified against the 1.1.0 spec, not from recall); and the document named `/audit` ×3, `/indie-review` ×2 and `/release`, none of which can be invoked since the 2026-08-13/15 promotions. **The one Q3:** the `Kind:` list is explicitly closed and the theme list explicitly open, and `Source:` said neither — while this project already carries 71 bullets with an unlisted `Source: in-session-…`, so a Source filter gets written strict or permissive by guess. Stated open. **Settled as non-findings:** three lanes checked the rewritten § 3.5.1 counter paragraph against the live tree and none found anything false in it. **One packet defect, reported by a lane and accepted:** fact F5's rendered-bullet quote was cut short of the trailing `Kind:` / `Source:` lines, which made "the renderer drops `Kind:`" a reading the packet invited; the lane checked the file rather than trusting it. |
