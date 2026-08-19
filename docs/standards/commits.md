<!-- ants-commit-standards: 1 -->
# Commit Standards — v1

A shareable contract for git commits in this project. Pairs with
the other standards in this folder — the [index](README.md) is the
full set, and naming no count here is deliberate so this line cannot
go stale as the set grows.

This standard governs every commit, plus the release-orchestration
work under ROADMAP bullets with `Kind: chore` or `release`.


## 1. Commit message format

### 1.1 The `<ID>: <description>` mandate

Every commit subject leads with the ROADMAP item ID it implements,
followed by `:` and a present-tense description:

```
FIBR-1234: implement live-search filter
FIBR-1235: fix config-reload inotify loop
FIBR-1236: extract storeIfChanged helper
```

This connects the commit to the work item end-to-end. A reader of
`git log --oneline` can map every commit back to the ROADMAP entry
that justified it; a reader of the ROADMAP can grep `git log` for
an ID and see exactly which commits implemented it.

The `<ID>` is either a **stable per-bullet ID** (`FIBR-NNNN`) or a
**phase ID** (`P##` bootstrap/feature phases, `FP##` fix-pass,
`DS##` debt-sweep, `DOC##` doc-fix-pass, `R##` research) for
phase-level commits that don't map to a single bullet — e.g.
`P00: scaffold project from template`. The phase-ID scheme is
defined in the app-workflow skill's ID scheme.

The ID prefix replaces the type-based prefix (`feat:`, `fix:`,
`refactor:`) of conventional-commits style — the **kind** is
declared by the ROADMAP item's `Kind:` field, not the commit
subject. This avoids the awkward `FIBR-1234: feat: …` double
prefix.

### 1.2 Exception — commits without a ROADMAP item

A few commit types don't ship a ROADMAP-tracked work item; they
use a category prefix instead:

| Type | Format | Example |
|------|--------|---------|
| Release | `X.Y.Z: theme — short summary` | `0.2.0: CSV/OFX import + duplicate detection` |
| Chore (debt sweep, gitignore tweak, dep bump) | `chore: short summary` | `chore: post-0.2.0 debt sweep` |
| Doc-only (typo, README tweak not tracked on roadmap) | `docs: short summary` | `docs: fix typo in security-model.md INV-2 section` |
| Hotfix without prior ROADMAP entry (will be back-filled) | `fix: short summary` + `Refs: FIBR-NNNN` trailer | see §1.4 |

**Where a phase ID exists for the category, the phase ID wins.** A
debt sweep run as a `DS##` phase is `DS03: …`, not `chore: …`; a
doc-fix pass run as `DOC##` is `DOC01: …`. The `chore:` / `docs:`
prefixes above are for that same work done *outside* any phase. Both
forms are live in this repo's history, and only the phase-ID form is
findable by an ID grep.

If the work was substantive enough to be tracked on the roadmap
(any feature, any non-trivial fix, any refactor), it gets a
ROADMAP item with an ID *first*, then the commit references that
ID. Don't ship code that should have been planned.

### 1.3 Subject line constraints

- Single line, present tense, ≤ 72 chars.
- No trailing period.
- Capitalisation matches the ID's case (`FIBR-1234:`); the
  description starts lowercase unless it begins with a proper
  noun.
- Don't repeat the ID in the description ("FIBR-1234: FIBR-1234
  implement live search").

### 1.4 Body

Optional, but encouraged when the change isn't self-explanatory.
Format:

```
FIBR-1234: implement live-search filter

Optional one-paragraph description of the why.

- Bulleted list of specific changes.
- Bulleted list of files / subsystems touched.
- Note any follow-up needed.

Refs: FIBR-1235  (for related but separate work)
Co-Authored-By: <name> <email>
```

Wrap at 72 columns. Use the body to explain WHY; the diff shows
WHAT.

### 1.5 Trailers

| Trailer | When |
|---------|------|
| `Co-Authored-By:` | Anyone who contributed materially (humans, AI agents) |
| `Reviewed-by:` | After a `review-code` pass |
| `Fixes:` | When the commit closes a tracker issue (Fixes: #42) |
| `Refs:` | Cross-references — e.g. `Refs: FIBR-1235` for related ROADMAP items |
| `Signed-off-by:` | DCO-required projects |

For AI-assisted commits, include the AI's identifier — the one the
session's harness supplies, never a literal copied from this file.
Freezing a model name in an example is how a commit ends up
attributed to a model that did not write it.


## 2. Commit hygiene

### 2.1 One concern per commit

If a single commit touches three unrelated subsystems, split it.
The git log is read by the next contributor — make their life
easier.

Exception: cross-cutting refactors (rename, signature change)
that genuinely span the codebase. Note the cross-cutting nature
in the body. The commit ID is the cross-cutting ROADMAP item.

### 2.2 Always create new commits, don't amend

When a pre-commit hook fails, the commit DID NOT happen — so
`--amend` would modify the *previous* commit, not the failed one.
Fix the issue, re-stage, create a new commit.

Only amend when fixing your *own* unpublished commit before push,
and only if you're certain.

### 2.3 Don't skip hooks

`--no-verify`, `--no-gpg-sign`, etc. bypass project safety nets.
Use only when the user explicitly authorises it. If a hook fails,
investigate and fix the underlying issue (per
[coding § 1.2](coding.md) — no workarounds).

**That authorisation can be standing rather than per-commit, and this
project grants exactly one.** The doc-only push route in
[`CLAUDE.md`](../../CLAUDE.md) § *Doc-only pushes* prescribes
`git push --no-verify` for a push whose every path ends in `.md`, after
running the prose checks by hand — so the pre-push gate is replaced by a
narrower one, not simply dropped. Read that section rather than
restating it here; it owns the prose-check list and the test for what
counts as doc-only.

**A code change never takes that route, however small.** Anything
outside the standing authorisation is still § 7's anti-pattern, and a
failing hook is still something to fix rather than skip.

### 2.4 Commit only files you mean to

`git add -A` and `git add .` are convenient and dangerous — they
pick up `.env`, `credentials.json`, `node_modules/`,
secret-bearing dotfiles. Add files by name, or use `git add -p`
for staged review.

### 2.5 Don't commit half-finished work

If the commit doesn't build or test green, it doesn't go in. Use
`git stash` for in-progress state. The TDD cycle (per
[testing § 1](testing.md)) means each commit ends with green
tests as a matter of course.

### 2.6 Don't commit generated files

Build artifacts (`build/`, `dist/`, `*.o`, `node_modules/`,
`__pycache__/`) belong in `.gitignore`. Generated docs (`/_build/`,
`docs/_static/`) too. Check `git status` before staging.


## 3. Branching

### 3.1 Trunk-based default

`main` is the integration branch. Short-lived feature branches
fork from `main`, ship via PR (or direct push for solo
development), get rebased + merged in days, not weeks.

### 3.2 Branch names

`<author>/<id>-<topic>` for personal branches: `alice/FIBR-1234-live-search`.
`feature/<id>-<topic>` for shared work. The ID lets a reviewer
find the ROADMAP context at a glance.

### 3.3 Don't force-push to shared branches

`git push --force` overwrites remote history. On personal
branches, fine. On `main` / `master` / shared branches, never —
use `git revert` + new commit instead.


## 4. Push policy

### 4.1 Public vs private repos

Push cadence (public: push freely; private: batch + ask once
5+ commits accrue) lives in the user's global
`~/.claude/CLAUDE.md` § 6 — canonical source. **A release push is
exempt there and goes immediately without asking**, so a release tag
never sits in that queue.

### 4.2 Tag format

Annotated tags only:

```bash
git tag -a vX.Y.Z -m "X.Y.Z"
```

Don't create lightweight tags (`git tag vX.Y.Z`) for releases —
they don't carry the release message.

Push tags explicitly: `git push origin vX.Y.Z` for one,
`git push --follow-tags origin <branch>` for a batch — that sends
only the annotated tags reachable from what you are already pushing.
**Never `git push --tags`**: it publishes every local tag, including
ones never meant to leave the machine. The global
`~/.claude/CLAUDE.md` § 6 forbids it by name. **Don't force-push tags
under any circumstance** — if a tag collision happens, stop and ask.

### 4.3 Confirm before destructive operations

`reset --hard`, `branch -D`, `clean -f`, `push --force` to a
shared branch — pause and confirm with the user, unless the user
has explicitly authorised the specific operation in advance.

A user approving an action once does NOT approve it in all
contexts.


## 5. Release commits (`Kind: release`)

Release commits use the `X.Y.Z: theme — summary` format (the
Release row of §1.2's table) plus a categorical body drawn from the
CHANGELOG entry:

```
0.2.0: CSV/OFX import + duplicate detection

Tier-1 fixes:

- FIBR-0009: HIGH — PDF import left decrypted bytes in a temp file.
- FIBR-0011: MEDIUM — transfer detection missed same-day reversals.

Tier-2 hardening:

- ...

Co-Authored-By: <AI identifier, per §1.5>
```

Note that the *bullets* inside the release body still cite
ROADMAP IDs — the release commit aggregates many ID-tracked
items into one shipping point.

Touched files for a release commit are typically: every
version-bearing file (`pyproject.toml`, packaging files,
`README.md`, `ROADMAP.md`), `CHANGELOG.md` (new dated section),
and the implementation changes themselves.

`cut-release <X.Y.Z>` owns the version-bearing-file edits, the
release commit and the tag; `cut-release --bump-only` is the bump on
its own, and `cut-release --check` is a read-only readiness report.
A `.claude/bump.json` recipe is what that skill reads to find the
version-bearing files. Edit them by hand only where no recipe and no
skill exist, and then run whatever drift check the project actually
ships before committing.


## 6. Releases on public hosts

After a release commit + tag on a public GitHub repo:

```bash
gh release create vX.Y.Z \
    --title "X.Y.Z — <theme>" \
    --notes "$(extract-changelog-section X.Y.Z)"
```

The notes body is the corresponding `[X.Y.Z]` section from
`CHANGELOG.md`. Use a heredoc to preserve markdown formatting.

**Do not assume CI attaches the assets.** It does so only where a
workflow actually triggers on the tag *and* uploads them — check
`.github/workflows/` for a `tags:` trigger before relying on it.
**In this repo none does**, so `gh release create` publishes an
*empty* release; the assets are attached by hand-running
`./scripts/release-linux.sh` and then `./scripts/release-windows.sh`.
Skipping that is how v0.1.20 shipped with zero assets and stayed that
way for ten days, with the README download link and the in-app
updater both resolving to it. [`CLAUDE.md`](../../CLAUDE.md)
§ *Cutting a release* owns the full order.


## 7. Anti-patterns

- ❌ Subject without a ROADMAP ID for substantive work.
- ❌ Subject that doesn't fit on one screen.
- ❌ "Update files" / "Various changes" / "WIP" as the only
  description.
- ❌ Bundle 5 unrelated changes into one commit because "they
  were all in the working tree".
- ❌ `git commit --amend` after a failed pre-commit hook.
- ❌ `git add .` with no review.
- ❌ Force-pushing to a shared branch.
- ❌ Skipping hooks (`--no-verify`) without explicit
  authorisation — § 2.3 names the one standing authorisation this
  project grants, and it covers documentation pushes only.
- ❌ Committing build artifacts / `.env` / credentials.
- ❌ Lightweight tags for releases (`git tag vX.Y.Z` without
  `-a`).
- ❌ Pushing a release tag before the tagged commit's CI is green —
  which here means the **branch** run, since no workflow fires on a
  tag (§ 6).
- ❌ Force-pushing tags.
- ❌ ROADMAP IDs that don't actually exist (typos in the prefix
  or an ID that was never assigned) — verify against the allocation
  rules in [roadmap-format § 3.5.1](roadmap-format.md).


## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Outcome |
|---|---|---|---|---|---|---|
| 1 | 2026-08-19 | 3 × `review-lane`, cold, genre pinned `standard`; packet carried the workflow triggers, the live skill/command inventory and the quoted cross-references | 6 | 2 | 1 | **Nine verified, nine fixed; two dismissed.** First gate ever run on this file (FIBR-0279). **All three lanes independently found the same five defects**, the strongest signal in the run. **The most dangerous is § 6**, which claimed "CI (if wired up) will fire on the tag push and attach build artifacts (AppImage, MSI, .dmg) to the release automatically. Don't manually upload artifacts that CI will produce." No workflow in this repo has a `tags:` trigger, none attaches a release asset, and the project ships no MSI and no `.dmg` — so a conformer stops after `gh release create` and publishes an empty release. That is exactly the **v0.1.20** failure: `gh release view v0.1.20 --json assets` returns an empty list to this day, and it went unnoticed for ten days with the README download link and the in-app updater both resolving to it. **Two dead tools:** § 5 routed the version bump to the `/bump` skill, which `cut-release` replaced on 2026-08-13, and named `packaging/check-version-drift.sh`, which does not exist anywhere in the tree — so the live branch of that sentence had no route to the bump at all; and § 1.5 keyed the `Reviewed-by:` trailer to a `/indie-review` pass, a command that no longer exists. **§ 4.2 prescribed `git push --tags`**, which the global `~/.claude/CLAUDE.md` § 6 forbids by name and this project's `CLAUDE.md` repeats — while § 4.1 four lines above names that same global file as canonical, so the two halves of § 4 disagreed. **§ 7's "Pushing a release tag whose CI hasn't run / passed"** was unsatisfiable: no CI run is ever attached to a tag here, so one reader blocks the release forever and another tags as soon as `main` is green. **Three found by the orchestrator while verifying lane open questions:** the `chore:` / `docs:` subject forms collide with the `DS##` / `DOC##` phase IDs and both are live in this repo's history (69 category-prefix commits against 9 phase-ID ones), with only the second findable by an ID grep; § 4.1 said a private repo batches "5+ commits/tags", when a release tag can never legitimately queue; and both `Co-Authored-By:` examples froze `Claude Opus 4.8 (1M context)` while every commit in the last 30 carries `Claude Opus 5` — a conformer copies the literal and mis-attributes the commit. Two dismissed as changing no line: § 3.1's PR-or-direct-push parenthetical already covers this repo's direct-push default, and § 2.2 / § 7's "pre-commit hook" reads conditionally in a standard meant to be shared, though this repo ships only `pre-push`. Filed rather than fixed, as neighbouring documents with their own gates: the stale peer count and frozen model literal in `coding.md` / `testing.md`, and four live references to `/bump` under `packaging/`. |
