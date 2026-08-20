# Versioning Standard — v1

What finbreak's version number **means**. Binding on every release, every
person and every agent cutting one. `CHANGELOG.md` has pledged Semantic
Versioning since the project began and nothing said what that pledge covers
for a desktop application, so the number drifted: thirteen delivered phases
and 196 shipped roadmap items still published as `0.1.22` (measured
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

These five are what a version number promises about. A change that breaks any
of them for an existing user is a MAJOR change, whatever its size.

| Surface | Where it lives | Broken means |
|---|---|---|
| **The encrypted vault** | SQLCipher database; `LATEST_SCHEMA_VERSION` and its migrations | A vault written by the previous version cannot be opened, or opens with data missing or altered |
| **The backup / export file** | `.fbk` archives; the PDF and CSV exports | A backup taken on the previous version cannot be restored |
| **The update path** | the signed release manifest, `RELEASE_PUBLIC_KEY_B64`, `services/update_fetch.py` | An installed copy can no longer see, verify or apply an update — including a signing-key rotation |
| **Saved import profiles** | the per-bank mapping profiles stored in the vault (FIBR-0007) | A saved profile no longer maps its bank's statement, silently or otherwise |
| **The documented command line** | `python -m finbreak --self-test` and any flag the README states | A documented invocation stops working |

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
here — announcing a removal is MINOR, performing it is MAJOR.

**3.3 — PATCH.** Everything else that ships: bug fixes, security fixes,
performance work, refactors, dependency bumps, packaging changes, and any
documentation that ships inside the artifact. No new capability and no § 2
break.

**3.4 — A security fix does not get its own number.** It takes the number its
*change* takes under 3.1 to 3.3, and ships as fast as `commits.md` § 4.1
allows. Severity is communicated in the changelog and in `SECURITY.md`, never
by inflating the version, which would tell every reader the wrong thing about
compatibility.

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

**4.2 — While below 1.0, `0.MINOR.PATCH` shifts down one place.** A break of a
§ 2 surface bumps MINOR — `0.1.22` → `0.2.0`. Everything else bumps PATCH.
This is the one rule the project has been getting wrong by omission rather
than by decision: every release so far has been a PATCH bump because nothing
said when to do otherwise.

**4.3 — Below 1.0, a § 2 break is still announced exactly as § 3.1 requires.**
The leading zero permits the break; it does not excuse shipping one silently.

## 5. The 1.0 gate

**1.0.0 says: the § 2 surface is frozen, and we will not break it without a
MAJOR.** It is a commitment about the future, not a grade awarded for the
past. Cut it when all five hold:

1. **No planned change to the § 2 surface remains open.** Specifically, no
   open roadmap item whose implementation would require an existing vault or
   backup to be re-encrypted, re-imported or rebuilt.
2. **No open defect can lose or corrupt user data.**
3. **No open defect crashes the app on a supported platform's default
   configuration.**
4. **The files a public project accepting reports must carry exist** —
   `SECURITY.md` and `CODE_OF_CONDUCT.md`, per `documentation.md` §§ 2.4 and
   2.5.
5. **Every feature the README advertises works on every platform the README
   offers a download for.**

**A third party's inbox is not a gate.** Neither store acceptance nor a code
signing certificate appears above, deliberately: both are outside the
project's control, and a version number that waits on somebody else's queue
never arrives. Ship 1.0 and let distribution catch up.

**Where the gate cannot be met but the 0.x number understates the project,
`0.9.z` is the honest interim** — "we believe this is it; the format is not
frozen yet". It is a normal `0.MINOR` bump under § 4.2 and commits to nothing.

## 6. Anti-patterns

**6.1 — Bumping PATCH because the change felt small.** Size is not the axis
(§ 1.1). A one-character change to a KDF parameter is a MAJOR.

**6.2 — Bumping MINOR to signal that a lot of work happened.** The number
describes compatibility, not productivity. A large release of pure fixes is a
PATCH and there is nothing wrong with `0.1.23`.

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
| § 2, update path | `tests/features/auto_update/`, and `scripts/release-linux.sh`'s hard gate against the committed `RELEASE_PUBLIC_KEY_B64` |
| § 2, command line | `tests/features/bundling/` (`--self-test`) |
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
