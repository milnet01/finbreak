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
| Release | `X.Y.Z: theme` | `0.2.0: CSV/OFX import + duplicate detection` |
| Chore (debt sweep, gitignore tweak, dep bump) | `chore: short summary` | `chore: post-0.2.0 debt sweep` |
| Doc-only (typo, README tweak not tracked on roadmap) | `docs: short summary` | `docs: fix typo in security-model.md INV-2 section` |
| Hotfix with no ROADMAP entry yet | `fix: short summary`, no ID trailer | see §1.4 |

**Where a phase ID exists for the category, the phase ID wins.** A
debt sweep run as a `DS##` phase is `DS03: …`, not `chore: …`; a
doc-fix pass run as `DOC##` is `DOC01: …`. The `chore:` / `docs:`
prefixes above are for that same work done *outside* any phase. Both
forms are live in this repo's history, and only the phase-ID form is
findable by an ID grep.

**The back-fill goes the other way** — the ROADMAP bullet cites the
commit sha, because writing an ID into the commit before the item exists
means guessing a number, and a guess cannot be corrected once the commit
is pushed.

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

### 2.2 Which hook failed decides whether you amend

**A pre-commit hook failure means the commit DID NOT happen** — so
`--amend` would modify the *previous* commit, not the failed one. Fix
the issue, re-stage, create a new commit.

**A failed pre-push gate is the opposite case**: the commit exists and
is unpushed, so amending it is right and keeps "fix the gate" noise out
of the history. **That is the only gate this project has** — `.githooks/`
holds `pre-push` alone, and `docs/specs/FIBR-0001.md` scopes pre-commit
hooks out by name.

Otherwise amend only your *own* unpublished commit, and only if you're
certain.

### 2.3 Don't skip hooks

`--no-verify`, `--no-gpg-sign`, etc. bypass project safety nets.
Use only when the user explicitly authorises it. If a hook fails,
investigate and fix the underlying issue (per
[coding § 1.2](coding.md) — no workarounds).

**That authorisation can be standing rather than per-commit.**
[`CLAUDE.md`](../../CLAUDE.md) is where this project's standing
authorisations are enumerated — § *Doc-only pushes* and § *Build and
test* are where they live. Do not restate the list or its length here:
a second copy of either is what goes stale, and it goes stale silently,
because nothing checks two documents against each other.

**No standing authorisation covers a gate that failed on a real
finding.** That is still § 7's anti-pattern, and the hook is telling you
something to fix rather than skip.

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

Release commits use the `X.Y.Z: theme` format (the Release row of
§1.2's table) plus a categorical body drawn from the CHANGELOG entry:

**One line, one theme — there is no ` — summary` half.** Both forms
carried one until 2026-08-19 (FIBR-0291) and neither worked example ever
had it, so a conformer could not tell whether it was required, optional
or dead text. It is dead text: `cut-release` § Phase 3 writes
`<X.Y.Z>: <one-line theme>`, and not one release commit in this repo's
history carries an em-dash segment. What *does* take the em-dash is the
GitHub **release title** (`X.Y.Z — <theme>`, § 6's block) — a different
string on a different object, and the likely source of the confusion.

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

Touched files for a release commit are whatever the recipe's `files[]`
names, plus `CHANGELOG.md`'s new dated section and the implementation
changes themselves. **Read `.claude/bump.json` rather than a list here**
— its `post_check` is what actually gates the set, and a list in a
second place drifts from it. **`ROADMAP.md` is not among them**: it is
rendered from the roadmap DB, so a version hand-edited into it is
reverted by the next render.

`cut-release <X.Y.Z>` owns the version-bearing-file edits, the
release commit, the tag, the push and the `gh release create` (§ 6); `cut-release --bump-only` is the bump on
its own, and `cut-release --check` is a read-only readiness report.
A `.claude/bump.json` recipe is what that skill reads to find the
version-bearing files. Edit them by hand only where no recipe and no
skill exist, and then run whatever drift check the project actually
ships before committing.


## 6. Releases on public hosts

**Where a release skill cuts the release, it creates the GitHub release
too — do not hand-run this step as well.** `cut-release <X.Y.Z>` (§ 5)
commits, tags, pushes *and* runs `gh release create`, so on this project
the release page already exists by the time you reach § 6 and the next
thing owed is the assets, below.

The block below is the hand-cut fallback, for a release no skill
created:

```bash
gh release create vX.Y.Z \
    --title "X.Y.Z — <theme>" \
    --notes-file - <<'NOTES'
<the [X.Y.Z] section of CHANGELOG.md, verbatim>
NOTES
```

The heredoc into `--notes-file -` is what preserves the markdown.

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
- ❌ `git commit --amend` after a failed **pre-commit** hook — that
  commit never happened. (After a failed **pre-push** gate it did, and
  amending is the right move: § 2.2.)
- ❌ `git add .` with no review.
- ❌ Force-pushing to a shared branch.
- ❌ Skipping hooks (`--no-verify`) without explicit authorisation —
  § 2.3 covers the standing authorisations, and `CLAUDE.md` is what
  enumerates them.
- ❌ Committing build artifacts / `.env` / credentials.
- ❌ Lightweight tags for releases (`git tag vX.Y.Z` without
  `-a`).
- ❌ Tagging a commit already known to be red. The tag and its commit
  leave in one `--follow-tags` push (§ 4.2), so there is no prior CI
  run to inspect — the **pre-push gate** is the green signal, and it
  runs the same `scripts/ci-local.sh` that `ci.yml` runs.
- ❌ Force-pushing tags.
- ❌ ROADMAP IDs that don't actually exist (typos in the prefix
  or an ID that was never assigned) — verify against the allocation
  rules in [roadmap-format § 3.5.1](roadmap-format.md).


## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Outcome |
|---|---|---|---|---|---|---|
| 1 | 2026-08-19 | 3 × `review-lane`, cold, genre pinned `standard`; packet carried the workflow triggers, the live skill/command inventory and the quoted cross-references | 6 | 2 | 1 | **Nine verified, nine fixed; two dismissed.** First gate ever run on this file (FIBR-0279). **All three lanes independently found the same five defects**, the strongest signal in the run. **The most dangerous is § 6**, which claimed "CI (if wired up) will fire on the tag push and attach build artifacts (AppImage, MSI, .dmg) to the release automatically. Don't manually upload artifacts that CI will produce." No workflow in this repo has a `tags:` trigger, none attaches a release asset, and the project ships no MSI and no `.dmg` — so a conformer stops after `gh release create` and publishes an empty release. That is exactly the **v0.1.20** failure: `gh release view v0.1.20 --json assets` returns an empty list to this day, and it went unnoticed for ten days with the README download link and the in-app updater both resolving to it. **Two dead tools:** § 5 routed the version bump to the `/bump` skill, which `cut-release` replaced on 2026-08-13, and named `packaging/check-version-drift.sh`, which does not exist anywhere in the tree — so the live branch of that sentence had no route to the bump at all; and § 1.5 keyed the `Reviewed-by:` trailer to a `/indie-review` pass, a command that no longer exists. **§ 4.2 prescribed `git push --tags`**, which the global `~/.claude/CLAUDE.md` § 6 forbids by name and this project's `CLAUDE.md` repeats — while § 4.1 four lines above names that same global file as canonical, so the two halves of § 4 disagreed. **§ 7's "Pushing a release tag whose CI hasn't run / passed"** was unsatisfiable: no CI run is ever attached to a tag here, so one reader blocks the release forever and another tags as soon as `main` is green. **Three found by the orchestrator while verifying lane open questions:** the `chore:` / `docs:` subject forms collide with the `DS##` / `DOC##` phase IDs and both are live in this repo's history (69 category-prefix commits against 9 phase-ID ones), with only the second findable by an ID grep; § 4.1 said a private repo batches "5+ commits/tags", when a release tag can never legitimately queue; and both `Co-Authored-By:` examples froze `Claude Opus 4.8 (1M context)` while every commit in the last 30 carries `Claude Opus 5` — a conformer copies the literal and mis-attributes the commit. Two dismissed as changing no line: § 3.1's PR-or-direct-push parenthetical already covers this repo's direct-push default, and § 2.2 / § 7's "pre-commit hook" reads conditionally in a standard meant to be shared, though this repo ships only `pre-push`. Filed rather than fixed, as neighbouring documents with their own gates: the stale peer count and frozen model literal in `coding.md` / `testing.md`, and four live references to `/bump` under `packaging/`. |
| 2 | 2026-08-19 | 3 × `review-lane`, cold, identical brief, packet rebuilt from disk | 2 | 2 | 1 | **Five verified, five fixed; nothing dismissed.** **Two of the five landed on text loop 1 wrote, and all three lanes found the first** — 4a-min's pattern at its clearest, since both landed in text a fix ADDED. Loop 1's § 2.3 said this project "grants exactly one" standing authorisation to skip a hook, and § 7's bullet said it "covers documentation pushes only"; `CLAUDE.md` grants a second and says so in terms — a `pip-audit` timeout against pypi or osv.dev fails the hook on a non-finding, and `git push --no-verify` is the sanctioned retry. So a conformer whose **code** push died on a network flake read § 2.3 as leaving them one lawful route (stop and ask) while `CLAUDE.md` told them to push. Fixed by deleting the count rather than correcting it: `CLAUDE.md` enumerates, this file does not, and a second copy of a list or its length is what goes stale. Loop 1's other addition — the § 7 bullet rekeying release-tag CI to "the **branch** run" — was unreachable under the tooling this document prescribes, because `cut-release` sends the commit and the tag up in one `--follow-tags` push (§ 4.2), so no prior run exists to inspect; rekeyed again to the pre-push gate, which runs the same `scripts/ci-local.sh` that `ci.yml` runs. **Three pre-existing.** § 6 told you to hand-run `gh release create` after the tag, while § 5 routes the release commit and tag through `cut-release`, which performs that command itself (`cut-release/SKILL.md:434`) — so a conformer following § 5 into § 6 runs it on a release that already exists. § 6's fenced block piped `$(extract-changelog-section X.Y.Z)` into `--notes`; that command exists nowhere in the tree (a whole-repo search returned exactly one hit, the line itself) and without `set -e` publishes a release with **empty notes** — replaced by the heredoc into `--notes-file -` that `scripts/release-linux.sh` itself uses, which also settles the block contradicting the sentence below it. And § 1.2's hotfix row required a `Refs: FIBR-NNNN` trailer for work with no roadmap entry while § 7 forbids citing an ID that was never assigned, saying nothing about when the back-filled ID is allocated — so one conformer guesses a number that will not match. **4a step 3 caught a false claim inside this loop's own fix**: the repair cited `.roadmap-counter` as the allocation route, and executing it showed the file reading `285` with `FIBR-0287` already on the roadmap. It is gitignored and re-derived when absent — a cache, not the allocator — so the fix now routes allocation to the roadmap DB and warns off the counter by name. Filed as **FIBR-0288**, since `roadmap-format.md` § 3.5.1 and `documentation.md:179` both still describe the counter as authoritative and each has its own gate. **Packet defect, not a document defect**: fact 10 still described two frozen `Claude Opus 4.8` literals loop 1 had already removed, and two lanes correctly reported it as evidence against the packet rather than filing a finding. Settled as non-findings: `.roadmap-counter` does exist so § 7's ID-verification route resolves; the scrubbed copy's line offsets are zero past line 300; and § 2.2 / § 7's conditional "pre-commit hook" and § 3.1's PR-or-direct-push parenthetical were each dismissed for a second consecutive loop. |
| 3 | 2026-08-19 | 3 × `review-lane`, cold, identical brief, packet rebuilt from disk and its stale fact 10 repaired | 0 | 5 | 0 | **Five verified, five fixed. Cap reached (3 for a standard); the run files its tail and exits.** **Not one Q1** — every defect this loop was two passages disagreeing. **This is a VIOLENT cap, and that is worth saying plainly: three of the five findings landed on text THIS RUN wrote**, checked against the earlier loops' ledger rows rather than recall. The run was repairing its own repairs, and nothing in it suggested a fourth loop would stop — which is the argument for the two net-deletion fixes below rather than another rewrite. **All three lanes found the same one**, and it is 4a-min's lesson at its most literal: loop 2's § 2.3 fix said "do not restate the list **or its length** here, because a second copy of either is what goes stale" — and then restated the list, dated, in the same sentence. A maintainer adding a third standing authorisation to `CLAUDE.md` obeys the first half and leaves a stale two-item list reading as authoritative. Fixed by deleting the enumeration, which is what the sentence had asked for. **The second self-collision was loop 2's back-filled-ID paragraph**, which told you to allocate the ID before the commit — making the row's own premise ("Hotfix **without prior ROADMAP entry**") false, putting the subject under § 1.1's `<ID>:` mandate rather than the row's `fix:` form, and leaving § 7's pointer to `roadmap-format § 3.5.1` contradicting § 1.2's new warning against the counter that section describes. All three collapsed into one net deletion: the row drops its `Refs: FIBR-NNNN` trailer, and **the back-fill runs the other way** — the ROADMAP bullet cites the commit sha, which is already this project's practice. **Two pre-existing, and one of them had been dismissed twice.** § 2.2 grounded its whole rule on a **pre-commit** hook failing ("the commit DID NOT happen"), and this project has none — `.githooks/` holds `pre-push` alone and `docs/specs/FIBR-0001.md` scopes pre-commit hooks out **by name**, which is the evidence loops 1 and 2 never opened and which reverses their dismissal. For the gate this project actually runs the premise inverts: the commit exists and is unpushed, so amending is right, while § 7's flat bullet — the line a session greps — said the opposite. Both are now keyed to *which* hook failed. And § 5 listed `ROADMAP.md` among the version-bearing files a release commit touches; it is in neither `.claude/bump.json`'s `files[]` nor its `post_check` drift gate, it is rendered from the roadmap DB so a hand-edited version is reverted by the next render, and its own header still reads `0.1.7` on a tree past `0.1.21` — the proof nothing maintains it. The list is replaced by a pointer to the recipe, since a second copy of that set drifts from the one that gates it. **Settled as non-findings:** `cut-release` does read `.claude/bump.json` (`SKILL.md:97`), so § 5's claim holds; and every `--no-verify` in `CLAUDE.md` sits in § *Build and test* or § *Doc-only pushes*, so § 2.3's pointer names them all — a refute-test run against the fix rather than a confirmation of it. **Deferred tail, filed not fixed:** FIBR-0289 (the stale `ROADMAP.md` version header), FIBR-0290 (the tag-push `--no-verify` habit, real practice sanctioned by no document — a `CLAUDE.md`-side gap), FIBR-0291 (the release-subject format disagreeing with both its own examples). |
