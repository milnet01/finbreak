<!-- ants-versioning-standards: 1 -->

# Versioning Standard — v1

What finbreak's version number **means**. Binding on every release, every
person and every agent cutting one. `CHANGELOG.md` has pledged Semantic
Versioning since the project began and nothing said what that pledge covers
for a desktop application, so the number drifted: 196 shipped roadmap items
across all thirteen planned phases, still published as `0.1.22` (measured
2026-08-20, FIBR-0299).

**This standard owns what the number means. It does not own where the number
lives** — that is `releases.md` § 1 (one version number, everywhere) and this
project's bump recipe at `.claude/bump.json`. Do not restate either here; a
rule stated twice becomes two rules that disagree.

## 1. Principles

**1.1 — The version is a promise to users, not a measure of effort.** A
release that took a month and changes nothing a user can observe is a PATCH. A
one-line change that makes an existing vault unopenable is a MAJOR. Sorting by
how much work happened is the mistake this standard exists to prevent.

**1.2 — finbreak's compatibility surface is user data and the update path, not
a code API.** Nobody imports `finbreak` as a library. What people depend on is
that the app they run tomorrow opens the vault they encrypted today. § 2
enumerates that surface exactly, because a promise whose subject is vague is
not a promise.

**1.3 — The number is decided by what changed, and it is decided before the
release is cut.** `cut-release <X.Y.Z>` takes the number as an argument; by
then the judgement has already been made. Make it against § 2 while the change
is still being written, and record it in the `CHANGELOG.md` entry.

**1.4 — Where two readings are available, take the more conservative one.** A
release that could have been MINOR and was published MAJOR costs a reader a
moment's surprise. A release that should have been MAJOR and was published
PATCH costs somebody their financial records. The two errors are not
comparable, so do not weigh them as though they were.

## 2. The compatibility surface

These six are what a version number promises about. A change that breaks any
of them for an existing user is a MAJOR change, whatever its size.

| Surface | Where it lives | Broken means |
|---|---|---|
| **The encrypted vault** | SQLCipher database; `LATEST_SCHEMA_VERSION` and its migrations | A vault written by **any earlier release** cannot be opened, or opens with data missing or altered |
| **The backup file** | `.fbk` archives | A backup taken on **any earlier release** cannot be restored |
| **The export file** | the PDF export (`services/pdf_export.py`). There is **no CSV export today** — FIBR-0093 is planned, and shipping it joins this surface only when a roadmap item adds it to this table | A field or layout something outside finbreak reads is renamed, reordered or dropped. An export is **output-only and never restored**, so "cannot be restored" is not its test |
| **The update path** | the signed release manifest, `RELEASE_PUBLIC_KEY_B64`, `services/update_fetch.py` | An installed copy can no longer see, verify or apply an update — including a signing-key rotation |
| **Saved import profiles** | the per-bank mapping profiles stored in the vault (FIBR-0007) | A saved profile no longer maps its bank's statement, silently or otherwise |
| **The launcher command** | the `finbreak` console script (`pyproject.toml` `[project.scripts]`), which `packaging/obs/`'s `.desktop` `Exec=` and the Flatpak manifest's `command:` both invoke | It is renamed or removed, so an installed launcher stops working. **Maintainer-only entry points are not on this list** — `python -m finbreak --self-test` is documented in `CLAUDE.md`, which no end user reads |

**The backup and the export are two rows because their failure modes are not
the same one.** A `.fbk` is written to be read back by finbreak; an export is
written to be read by a person or a spreadsheet, and is never restored. One row
covering both defined "broken" for the first and left the second with no test
at all.

**A forward migration that runs automatically and loses nothing is NOT a
break.** Adding a schema version, migrating on open, and leaving the user with
every transaction they had is ordinary MINOR work — that is what the migration
machinery is for. The break is the case with no route forward, or a route that
silently drops data.

**Anything not on this list is not a compatibility promise.** Internal module
layout, function signatures, the database's physical table shape beneath a
migration, log text, and the wording of the UI are all free to change in a
PATCH. Adding to this table is a deliberate act with its own roadmap item; do
not extend it by reading it generously.

## 3. What each number means

Given `MAJOR.MINOR.PATCH`:

**3.1 — MAJOR.** Any break of a § 2 surface. Also any change that requires the
user to *do* something before the app works as it did — re-enter a password,
re-import a statement, reinstall from a new source. A MAJOR release must state
the required action in its `CHANGELOG.md` entry and in the published release
notes; a MAJOR that does not tell the user what to do is not finished.

**3.2 — MINOR.** New user-visible capability that breaks nothing on the § 2
list: a new feature, a new import format, a new report, a new supported
platform, an automatic forward migration. Deprecating something also lands
here. **Announcing** a future removal is MINOR; **performing** it follows
§ 3.1 — MAJOR where it breaks a § 2 surface or forces user action, and § 3.3
otherwise.

**3.3 — PATCH.** Everything else that ships: bug fixes, security fixes,
performance work, refactors, dependency bumps, packaging changes, and any
documentation that ships inside the artifact. No new capability and no § 2
break.

**3.4 — A security fix does not get its own number.** It takes the number its
*change* takes under 3.1 to 3.3. Severity is communicated in the changelog —
and in `SECURITY.md` once that file exists, which it does not today (§ 5
condition 4) — never by inflating the version, which would tell every reader
the wrong thing about compatibility.

**3.5 — Documentation, tests, CI and roadmap work that ships in no artifact
gets no release at all.** It rides along with the next one. Cutting a release
to publish a README edit burns the release path's eight-asset build for
nothing.

## 4. Before 1.0

**4.1 — `0.y.z` means the § 2 surface is not yet frozen.** That is what the
leading zero is for under Semantic Versioning 2.0.0 § 4, and it is an honest
description of finbreak today: FIBR-0019 (master-password recovery) is a
planned change to the vault's key envelope, and its own roadmap bullet says
retrofitting it needs a full re-encrypt migration.

**4.2 — While below 1.0, `0.MINOR.PATCH` shifts down one place.** Anything
MAJOR under § 3.1 — a § 2 break, **or** a change requiring user action — bumps
MINOR, `0.1.22` → `0.2.0`. Everything else bumps PATCH. Stated in terms of
§ 3's classes rather than § 2's surfaces on purpose: § 3.1 has two limbs, and
a rule naming only the first sends a forced reinstall to PATCH.

This is the one rule the project has been getting wrong by omission rather
than by decision: every release since `0.1.0` has been a PATCH bump because
nothing said when to do otherwise.

**4.3 — Below 1.0, a § 2 break is still announced exactly as § 3.1 requires.**
The leading zero permits the break; it does not excuse shipping one silently.

## 5. The 1.0 gate

**1.0.0 says: the § 2 surface is frozen, and we will not break it without a
MAJOR.** It is a commitment about the future, not a grade awarded for the
past. Cut it when all five hold:

1. **No planned change to any § 2 row remains open** — not merely the vault
   and backup rows. It fires on an open item that would require an existing
   vault or backup to be re-encrypted, re-imported or rebuilt **even where
   § 2's automatic-migration carve-out means that item is not a *break***: the
   carve-out decides what number a shipped change takes, never whether the
   surface is settled enough to freeze. FIBR-0019 is the live case, and it
   blocks this condition.
2. **No open defect can lose or corrupt user data.**
3. **No open defect crashes the app on a supported platform's default
   configuration.**
4. **`SECURITY.md` and `CODE_OF_CONDUCT.md` both exist.** finbreak accepts
   issues *and* patches — `CONTRIBUTING.md` documents both — so both of
   `documentation.md`'s triggers fire: § 2.4 on accepting issues, § 2.5 on
   accepting patches. They are separate triggers and this condition does not
   collapse them into one.
5. **Every feature the README advertises works on every platform the README
   offers a download for.**

**A third party's inbox is not a gate.** Neither store acceptance nor a code
signing certificate appears above, deliberately: both are outside the
project's control, and a version number that waits on somebody else's queue
never arrives. Ship 1.0 and let distribution catch up.

**Where the gate cannot be met but the 0.x number understates the project,
`0.9.z` is the honest interim** — "we believe this is it; the format is not
frozen yet". **It is the single named exception to § 4.2 and § 6.2**: one
deliberate signalling bump, taken once, decided by judgement rather than by
what changed, and recorded as such in its changelog entry. It freezes nothing
— § 2 stays unfrozen until 1.0 — and it is the only place in this standard
where a number says something other than what § 3 would assign. **§ 4.2
resumes immediately after it** — the next § 3.1-class change bumps `0.10.0`,
not a second signalling number.

## 6. Anti-patterns

**6.1 — Bumping PATCH because the change felt small.** Size is not the axis
(§ 1.1). A one-character change to a KDF parameter is a MAJOR.

**6.2 — Bumping MINOR to signal that a lot of work happened.** The number
describes compatibility, not productivity. A large release of pure fixes is a
PATCH and there is nothing wrong with `0.1.23`. § 5's one-time `0.9.z` interim
is the single named exception, and it is a decision rather than a habit.

**6.3 — Reaching 1.0 by feeling ready.** § 5 is five checkable conditions
precisely so this decision does not rest on a mood. If they hold, cut it; if
they do not, name the one that fails.

**6.4 — Letting a store, a certificate authority or a review queue set the
version.** See § 5.

**6.5 — Deciding the number while cutting the release.** `cut-release` takes
it as an argument and will not argue (§ 1.3). By then the changelog is
written, and the person best placed to judge the impact — whoever made the
change — has moved on.

**6.6 — Inflating a version to advertise a security fix.** § 3.4. It tells
every reader something false about compatibility in order to say something
true about urgency, and the changelog already says it.

**6.7 — Restating `releases.md` § 1 or `.claude/bump.json` here.** Where the
number is written is owned elsewhere; this file owns only what it means.

## What checks this

| Rule | What catches a breach |
|------|----------------------|
| § 1.3, § 6.5 | **nothing** — the judgement precedes the tooling by design; `cut-release --check` reports readiness, not correctness of the number |
| § 2, vault row | `tests/features/*/test_migration_v*.py` catch a migration that loses data; **nothing** catches a break with no migration written at all |
| § 2, backup row | `tests/features/backup/` covers the `.fbk` round-trip, but same-build — it writes and reads with one version and never crosses a boundary; `services/backup.py` refuses a *newer* schema, which is the other direction. **Nothing** restores a `.fbk` written by an earlier release, so an old-backup break is uncaught |
| § 2, export row | **nothing** — no test pins the PDF export's field set or layout across a version boundary |
| § 2, update path | `tests/features/auto_update/`, and `scripts/release-linux.sh`'s hard gate against the committed `RELEASE_PUBLIC_KEY_B64` |
| § 2, saved import profiles | a profile lives in the vault, so a **schema** migration touching it is caught by the vault row's tests; **nothing** catches a change to how a stored profile is interpreted |
| § 2, launcher command | `tests/features/obs_packaging/` asserts `pyproject`'s `[project.scripts]` maps `finbreak` → `finbreak.__main__:main`, and `tests/features/flatpak_packaging/` asserts the manifest's `command` is the bare `finbreak`. A rename that missed either turns both red |
| § 3.1's required-action note | **nothing** — reviewed by whoever reads the changelog |
| § 3.5 | **nothing** — tracked by whoever cuts the release |
| § 4.2 | **nothing** — tracked by FIBR-0299; no tool reads a diff and proposes a number |
| § 5 conditions 1–3 | **nothing** — a roadmap survey, not a check |
| § 5 condition 4 | file existence; tracked by FIBR-0237 |
| § 5 condition 5 | `/feature-review` run against the README's claims |
| Version lockstep (owned by `releases.md` § 1) | `.claude/bump.json` + `tests/test_smoke.py`'s `__version__` assertion |

**Most rows read "nothing", and that is the honest state rather than an
oversight.** Choosing a version number is a judgement about impact, and no
tool reads a diff and decides whether an existing vault still opens. What
tooling exists enforces *consistency* once the number is chosen. Inventing a
checker for the rest would be worse than recording the gap.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Outcome |
|---|---|---|---|---|---|---|
| 1 | 2026-08-20 | 3 × `review-lane`, cold, genre pinned `standard`; packet carried the quoted cross-references, 14 verified source facts and the standard-skeleton shape | 3 | 2 | 2 | **Seven verified, seven fixed; one dismissed.** First gate on this file (FIBR-0299), written the same day. **All three lanes independently found the same two defects**, the strongest signal in the run, and both were the document arguing with itself about which number to publish. **§ 5's `0.9.z` interim** called itself "a normal `0.MINOR` bump under § 4.2" while § 4.2 made a MINOR bump below 1.0 *mean* a § 2 break, and § 6.2 named bumping MINOR to signal maturity as an anti-pattern by name — so a releaser judging the project near-complete published `0.9.0` on § 5's authority and `0.1.23` on §§ 4.2/6.2's, and under § 4.2 the two paths never reconverge. It is now the single **named** exception to both, which is what it always was in intent. **§ 3.1 has two limbs** — a § 2 break *or* a change requiring user action — and § 4.2's shift-down rule named only the first, sending a forced reinstall to PATCH through "everything else"; § 4.2 is now stated in terms of § 3's classes rather than § 2's surfaces. **The third Q1 was found by all three lanes too:** § 3.4 routed security severity to `SECURITY.md`, a file that does not exist (FIBR-0237) and which § 5 condition 4 lists as a *future* 1.0 gate — so every security release between now and 1.0 was told to use a channel it could not reach. **Two Q1s the orchestrator found**, one in Phase 1b before a lane was spent: § 3.4 cited `commits.md § 4.1` for how fast a security fix ships, and that section is about push cadence and says nothing about security urgency; and, while resolving a lane's open question, that the § 2 command-line row promised "any flag the README states" when the README documents **no** invocation at all — verified by grep, the only two `--` strings in it being a badge colour and a `zypper` argument. **Both Q3s were rules a conformer could not tell they had breached.** The § 2 backup row named `.fbk`, PDF and CSV together and defined "broken" only for the first, leaving someone reordering CSV export columns unable to tell MAJOR from PATCH — split into two rows, since an export is output-only and never restored. And "What checks this" carried rows for three of the (then) five surfaces and omitted the rest entirely, which is unreadable in a table whose own note says most rows read **nothing** on purpose: silence meant neither "checked" nor "uncaught". **Collateral, six items, all from adding one file to `docs/standards/`:** `CONTRIBUTING.md` names each standard individually and `documentation.md` § 2.6 requires it to name them all; `docs/standards/README.md` said "Six" in its intro and "seven … the six standards" in its adoption section; `README.md` and the project `CLAUDE.md` both list the standards by name; and the new file was missing the `<!-- ants-*-standards: 1 -->` first-line marker every other standard in the folder carries. The index row's own summary went stale from this loop's own § 2 split and was corrected with it. **One dismissed as changing no line built:** the opening said "thirteen delivered phases" when P01, P12 and P13 still carry open items — true, inert, and corrected author-side by narrowing rather than fixed as a finding. **Settled as non-findings:** the SemVer 2.0.0 § 4 paraphrase is accurate; every catcher named in the table resolves (three migration tests, `auto_update`, `bundling`, the `release-linux.sh` hard gate at three call sites, `tests/test_smoke.py`); and `backup.py`'s guard is against restoring a *newer* backup, which does not contradict § 2's promise about older ones, since restore opens and migrates forward. |
| 2 | 2026-08-20 | 3 × `review-lane`, cold, identical brief, packet rebuilt from disk | 2 | 6 | 1 | **Nine verified, nine fixed; nothing dismissed. None of loop 1's findings resurfaced**, which is the proof those fixes held. **The run's worst finding is an invented surface**: § 2 listed "the PDF and CSV exports" and there is **no CSV export** — `ui/export_dialog.py` is PDF-only, every `csv` hit under `src/finbreak/` is import-side, and FIBR-0093 (plain data export) is still 📋 planned. A conformer auditing the surface before 1.0 would have gone looking for it, and the "What checks this" gap told them to write a cross-version test for it. **Three of the nine landed on text loop 1 wrote** — checked against loop 1's ledger rather than recall — which is 4a-min's pattern and the reason this loop's fixes lean on deletion. The backup row's catcher cell, added by loop 1, read as covered: `tests/features/backup/`'s round-trip is **same-build** (`test_backup.py:822-828` writes and reads with one version), and the newer-schema refusal is the other direction — so nothing restores a `.fbk` from an earlier release and the cell now says so. Loop 1's command-line row anchored a **user** compatibility promise to `CLAUDE.md`, a maintainer file no end user reads, while the real user-facing entry point — the `finbreak` console script in `pyproject.toml` `[project.scripts]`, invoked by `packaging/obs/`'s `.desktop` `Exec=` and the Flatpak manifest's `command:` — was named nowhere; the row is now the launcher command, with maintainer entry points explicitly off the list. And loop 1's "adds nothing here today" made the surface self-extending, against § 2's own closing rule that adding to the table is a deliberate act. **The sharpest pre-existing finding flips the 1.0 decision itself**: § 2 says an automatic forward migration that loses nothing is NOT a break, and § 5 condition 1 fired only on an open item requiring a re-encrypt — so FIBR-0019, the very item § 4.1 cites as proof the surface is unfrozen, satisfied the condition it was supposed to block. Condition 1 now fires on any § 2 row and says the carve-out decides a shipped change's number, never whether the surface is settled. **Two more scope errors:** the vault and backup rows tested "the previous version" while the § 2 header promises "an existing user" — someone dropping migrations for schema 1-5 would ship a PATCH that breaks anyone still on 0.1.3 — and condition 1's "Specifically" clause narrowed six surfaces to two. **Two citation errors:** § 3.2's "performing it is MAJOR" made removing a non-§ 2 feature MAJOR where §§ 3.1/3.3 make it PATCH; and condition 4 collapsed `documentation.md` § 2.4 (accepts **issues**) and § 2.5 (accepts **patches**) into one "accepting reports" test, letting a conformer exempt `CODE_OF_CONDUCT.md`. **One lane open question closed as a real ambiguity:** after the one-time `0.9.z`, § 4.2 resumes and the next § 3.1-class change bumps `0.10.0` — "taken once" admitted a second reading. **Collateral:** the project `CLAUDE.md` § Where state lives still said "the six shareable v1 standards" (loop 1 fixed the *other* count in § Standards reference and missed this one), and the index row's surface list went stale from this loop's own renaming. |
