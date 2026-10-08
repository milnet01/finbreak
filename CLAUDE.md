# finbreak — Project instructions for Claude Code

Scaffolded from the **Ants App-Build** template. Follows the machine-wide
workflow, `~/.claude/workflow.md` — its five states, its gates, and § 6's six
conditions for finishing an item. The old `app-workflow` phase loop and its
`.claude/workflow.md` were retired on 2026-09-28 (FIBR-0368); that file's
history is [`docs/history/workflow-state.md`](docs/history/workflow-state.md).

## Where state lives

**Items 1–3 are read on every session start; 4–6 are read when you need
them, not up front.** § Resumption flow at the bottom of this file is the
operative procedure and it governs — it reads 1–3 in one batch, then pulls
the standard item 4 maps the active item's `Kind` to. Do not read every
standard and the active spec before summarising: that is
six-plus reads to answer a question the roadmap DB already answers.

1. **This file** — stable rules and conventions.
2. **The roadmap DB** — **the source of truth on current state**: what is
   open, in progress and next. `ROADMAP.md` is **generated from it**, and the
   generated file is what gets committed and pushed. **Never hand-edit that
   file** — the next render overwrites you. Query the DB with `roadmap_query`
   rather than reading a 600 KB file: **`status:"active"`** for the open items
   (that is planned + in-progress — the resumption flow's call), `id` / `ids`
   for one item **with its body**.
   **A filtered call withholds bodies** (the envelope says so, with
   `bodies_omitted: true`). **For the survey, pass
   `bullet_fields: ["id","status","kind","headline_oneline"]`** — it keeps
   the rows small and still carries `kind`, so it answers § Resumption flow
   step 2 on its own. **One call over every open item spills** (measured
   2026-09-29), so narrow WHICH rows come back: `status:"active"` plus
   `section:<slug>` or `kind:<kind>` fits, and
   `mode:"section_index" status:"active" slugs_only:true` lists the sections
   holding open work. **`mode:"headline_only"` cannot**: its rows are fixed
   to `id`, `status`, `headline_oneline` and `section_slug`, with no `kind`
   under any argument (FIBR-0330). A targeted `id` / `ids` fetch returns
   bodies without `include_body`.
   Write through `roadmap_log`, which enforces the format and **re-renders the
   whole file on every write** (`items_rendered: 277` on a one-item annotate)
   — that render is what overwrites a hand edit. Keep a bold headline on **one
   line**: a wrapped one renders its continuation at column 0, which markdown
   reads as a new list item. (User decision 2026-08-18, FIBR-0281.)

   **The freshness check a session owes before writing:** `roadmap_query` on
   the id it is about to touch, reading the body back — and again after every
   flip or annotate, because a note can land mid-bullet and still report
   success. Both verbs locate items in the **store** (ANTS-4485, checked
   2026-09-25), so anything `roadmap_query` shows can be written. A write replies with
   the item's id, status and headline only, not its body, so the read-back is
   still owed. And there is **no delete verb**, so an `append` cannot be
   undone — reverting the file with git leaves the item orphaned and the
   next render injects it back. Get
   an append right first time.

   **Before running `roadmap_migrate`, read
   [`.claude/rules/roadmap-migrate.md`](.claude/rules/roadmap-migrate.md)**:
   on this project it is almost never needed, and a real run can write over
   correct items.

3. **Which item is active.** The roadmap DB says which items are 🚧; it
   does not say which ONE this session is working. Where exactly one is 🚧,
   that is it. Where several are, **ask the user** rather than guessing;
   where none is, say so and ask which planned item to take. **Flip an item
   to 🚧 with `roadmap_log` when you start it** — that status is the only
   record the next session has of what is in progress.
   Nothing else holds this: the file that used to, `.claude/workflow.md`,
   was retired on 2026-09-28 (FIBR-0368). **Summarise back to the user**
   before doing any work.
4. **The one `docs/standards/` file the active item's `Kind` maps to** in
   [`docs/standards/README.md`](docs/standards/README.md)'s Kind→standard
   list — plus `versioning.md` for `Kind: release`, which that README says it
   governs. Not every standard. (§ Resumption flow step 2 is where that read
   happens, and it governs.)
5. **`docs/specs/<active-id>.md`** — the contract for the
   currently-active roadmap item. Read it when you start work on that
   item; not every item has one (see § Spec discipline in the global
   rules — most work needs no spec).
6. **`docs/audit-allowlist.md`** — read **additionally** before
   invoking `check-code` or `review-code` so already-confirmed
   project-specific false positives aren't re-flagged. The
   allowlist is the closed-loop memory for this project;
   `close-findings` is what writes a new entry.
   (`check-code` replaced `/audit` on 2026-08-15 and `review-code`
   replaced `/code-quality-review` on 2026-08-18; the allowlist read is
   keyed to the job, not the old name.)

## Finishing an item

An item is done when `~/.claude/workflow.md` § 6's six conditions hold: a
test that failed for the right reason, the shortest correct code, the `check-`
skills clean, the `review-` skills run, every finding given a disposition, and
the record true. `/close-phase` and its `<ID>-complete` tags belonged to the
retired phase loop and are no longer run here.

## Cold-eyes review cadence (project override)

finbreak is **correctness-critical** — it handles people's money, and a
wrong-day / wrong-zone / wrong-total bug is exactly the class of error users
won't forgive. So a spec gets one loop more than the skill would give it: run
**`review-contract <path> --max-loops 3`** for this project, on **every**
genre. The skill's own default is 2 for a spec or plan and 3 for a standard or
an ADR, so this raises the spec/plan cap by one and leaves a standard's where
it already was.

A spec reaching its cap is a **normal exit**, not a failure — the build is the
next reviewer. The cap was higher until 2026-08-19 and came down on measurement:
[`docs/history/claude-md.md`](docs/history/claude-md.md).

**Convergence is the skill's, not a local definition**: a loop whose verified
findings answer none of its four questions. Do not hold a spec to the older
"no *substantive* structural / mechanical / architectural findings" bar —
`review-contract` retired those dimensions and puts wording, structure and
duplication outside the gate entirely, so looping on them buys nothing. And at
the cap it **files the remaining findings and exits** rather than pausing to
ask how to proceed; reaching the cap on a spec is a normal exit, not a failure.

## Tech stack

Chosen in Phase A (see [`docs/discovery.md`](docs/discovery.md)
for the full table and reasoning):

- **Language:** Python 3.12+
- **GUI:** PySide6 (LGPL) — dark-themed Qt desktop (ADR-0002)
- **Encrypted storage:** SQLCipher (SQLite + AES-256), keyed by an
  **Argon2id**-derived key (`argon2-cffi`) (ADR-0003)
- **PDF:** Qt engine (`QTextDocument` + `QPdfWriter`) for export;
  `pikepdf` for AES-256 export-locking and in-memory decrypt of
  locked input statements (ADR-0004)
- **Import parsers:** stdlib `csv` + per-bank mapping profiles
  (ADR-0005), `ofxparse` (OFX), `pdfplumber` (PDF)
- **Tests / lint / types:** pytest (+ pytest-qt), ruff, mypy
- **Security gate:** bandit, pip-audit, gitleaks (see
  [`docs/security-model.md`](docs/security-model.md))
- **Packaging:** PyInstaller (Windows `.exe`, macOS `.app`/`.dmg`),
  AppImage + Flatpak/Flathub and native RPM/deb via the openSUSE Build
  Service (Linux; `packaging/obs/`, FIBR-0155) (ADR-0007)
- **License:** MIT; local-only apart from an opt-in, off-by-default
  update check (FIBR-0054; stdlib `urllib`, confined to
  `services/update_fetch.py`).

## Build and test

The harness contract is [`docs/specs/FIBR-0001.md`](docs/specs/FIBR-0001.md).

**Requirements and one-time dev setup** — the pinned binaries,
`scripts/ci-setup.sh`, and the route for this openSUSE desktop — are in
[`.claude/rules/gate.md`](.claude/rules/gate.md). Read it before setting up
an environment, or when `./scripts/ci-local.sh` exits 127.

**Run the full gate** — the same stages CI runs (lint, format-check,
**shellcheck**, **actionlint**, **zizmor**, bandit, pip-audit **×2**, gitleaks,
**mypy**, tests; FIBR-0001 INV-1/INV-2). Note the mypy stage: a green `pytest`
alone is **not** a green gate. The shellcheck/actionlint/zizmor stages cover the
gate's own delivery machinery — the shell scripts and workflows that build and
publish releases, which no Python stage reads. `zizmor` is the supply-chain half
of that: it fails the gate if a workflow `uses:` reverts from a commit SHA to a
mutable tag, or a checkout starts persisting its token (FIBR-0226). `pip-audit`
runs **twice** against two different advisory databases — the default PyPI one
and OSV.dev (`-s osv`, FIBR-0227) — because neither is a superset and only
OSV.dev carries the malicious-package feed that catches a hijacked release with
no CVE. Both runs start with the gate and finish alongside the other stages,
so they add little to its runtime (FIBR-0373):

```bash
./scripts/ci-local.sh
```

**One-time: the real-account-number leak guard needs a file only you can
supply (FIBR-0086 INV-8, wired by FIBR-0248).** This repo is **public**, and a
bank account number is not a credential, so `gitleaks` does not match one — a
real number reached a spec once and sat there a month (FIBR-0244). The guard
that catches that class needs the real numbers to search for, and they are the
secret, so they are never committed. Put them in a **gitignored
`.corpus-numbers`** at the repo root, one per line, as printed:

**Create it in an EDITOR, never on a command line** — open
`.corpus-numbers` in a text editor, one number per line, exactly as printed on
the statement. Any real number works, not only account numbers: a card number
or an ID number is caught the same way (FIBR-0246). Enter each number whole:
the guard looks for it inside every run of eight or more digits, so a short
fragment would match unrelated numbers. Spacing and dashes do not matter: the guard runs
`normalise_account_number` before comparing, and its search pattern allows any
run of separators between digits, so a number split by a line-wrap is still
found.

**Never a command line.** That lands in `~/.bash_history` and in an agent's
transcript — the defect **FIBR-0276** filed against the recipe that used to stand
here ([`docs/history/claude-md.md`](docs/history/claude-md.md)). An editor writes
to no history.

**This is a step the user performs and an agent cannot.** The values are the
user's real account numbers, and an agent must not invent them. It must never
**print, echo, quote or otherwise surface the file's contents** — not to check
the user typed them correctly, not anywhere. That is the rule; *reading the
bytes* is not. The one sanctioned read is the shell substitution below, which
hands the values to `pytest` without them appearing on a command line, in
`~/.bash_history`, or in a transcript. Counting lines is fine; showing one is
not.

Without it `tests/features/account_detect/test_no_real_data.py` **skips**, and
a skipping test reads as coverage while providing none. **Wiring a source is not
the same as supplying one** — the route landed days before the file did, and only
the later date is when the tree was first actually scanned
([`docs/history/claude-md.md`](docs/history/claude-md.md)). `FINBREAK_CORPUS_NUMBERS`
(comma-separated) overrides **where the numbers come from** — for a machine
that keeps them elsewhere, or a run against a different set. **Its value comes
from a gitignored file written in an editor and substituted in, never typed**:
`FINBREAK_CORPUS_NUMBERS="$(paste -sd, <that-file>)" pytest …` puts no value on
the command line or into `~/.bash_history`. Substituting from `.corpus-numbers`
itself buys nothing — that is already the default. Typing them out is the very
act the never-list below forbids, and the defect FIBR-0276 filed. **Never print the
values, type them onto a shell command line, redirect them to a tracked file,
or paste them into a commit message, spec or ROADMAP entry** — the guard binds
prose, not just fixtures. CI cannot
hold them and never will, so this check is local-only by design.

**Pre-push hook — the gate runs automatically before a `git push`, unless you
pass `--no-verify` or the push is tag-only** (that second case is the hook's
own doing, and reaching for the flag there is what it exists to stop — see
below). **A push that changes only `.md` files runs the documentation checks
instead of the full gate**, also by the hook's own choice (§ Doc-only pushes).

**It also refuses outright on a tree with uncommitted or untracked files, or
when the commit being pushed is not the one checked out**, rather than running.
The gate reads the files on disk, so its verdict is about the working tree and
not about the commits being pushed — the same thing only after a
commit-then-push of `HEAD`. The dangerous direction is real: a fix present in
the tree but not in the commit, or an untracked module the code imports, makes
the gate green about code that never leaves the machine. Commit, stash or
remove them first; pushing past the refusal with `--no-verify` needs the user's
say-so (`commits.md` § 2.3), like any other skipped hook. **And on every push it
scans each commit being pushed for secrets** (`gitleaks git` over the pushed
range), because the gate's own scan sees only the final files (local-gate.md
§ 2.1).

CI (`ci.yml`) runs this exact script, so a green local gate means green in CI
**for everything the environment does not decide** — see the container caveat
in `gate.md` for the part it cannot cover. The commonest way a red push slips through
is simply *forgetting to run the gate*, and the version-controlled hook at
`.githooks/pre-push` closes that gap. It is enabled
in this clone; a **fresh clone must enable it once**:

```bash
git config core.hooksPath .githooks
```

(A rare `pip-audit` timeout — against either pypi or osv.dev — can make the
hook flake on a non-finding; retry, or `git push --no-verify` for that
transient case. Those two are the gate's only network-dependent stages.)
A doc-only push needs no `--no-verify`: the hook picks the documentation
checks for it (FIBR-0373).

**Tag-only pushes, and reproducing CI's environment with
`./scripts/ci-docker.sh`**, are in [`.claude/rules/gate.md`](.claude/rules/gate.md).
Read it before a tag push, and before pushing a dependency or CI change.

**Run tests / a single test** (INV-6):

```bash
pytest                                              # whole suite
pytest -k package_imports                           # by keyword
pytest tests/test_smoke.py::test_package_imports    # by node id
```

The gate runs `pytest -m "not perf"` (perf excluded; integration tests run) on
several processes — `-n <workers>`, sized from free memory, capped at 6;
`FINBREAK_TEST_WORKERS` overrides it (FIBR-0373). Every test has a 300s limit.
`pytest-qt`'s `qtbot` fixture is **enabled** — P02 (FIBR-0004) shipped the first
real GUI tests and removed the `addopts = "-p no:pytest-qt"` line.

**Bundling smoke-test** (FIBR-0003) — prove the native stacks (Qt, SQLCipher,
qpdf) travel into a Python-free bundle:

```bash
python -m finbreak --self-test        # in-process: loads all three, prints a sentinel
./scripts/build-smoke.sh              # freeze onefile + AppImage, launch each in a container
./scripts/ci-local.sh --build         # the gate PLUS the build+clean-room test (opt-in)
```

The slow build+clean-room test is **off by default** (keeps the gate fast); pass
`--build` or set `FINBREAK_BUILD_SMOKE=1`. It needs `podman`/`docker` on `PATH`.

## Commit conventions

Per [`docs/standards/commits.md § 1.1`](docs/standards/commits.md):
every commit subject is `<ID>: <description>`, where `<ID>` is
either a phase ID (`P##`, `FP##`, `DS##`, `DOC##`, `R##`) or a
stable per-bullet ID for ROADMAP_FORMAT v1 projects
(`FIBR-NNNN`).

Under the retired phase loop every implementation phase ended with
`git tag -a <ID>-complete` on the closing commit; no new ones are made.
**The existing phase tags are public, and that is fine** (user decision
2026-08-18) — they are build markers on a public repo and carry nothing
private. § Push policy below has the reasoning and is the one home for it.

**A release tag `v<X.Y.Z>` is a different thing again** — it is pushed
as part of cutting the release, without asking, per global
`~/.claude/CLAUDE.md` § 6 ("a release push goes immediately and
WITHOUT asking, on every repository"). An unpushed release tag is a
half-cut release, and the next session cannot tell a queued one from
a failed one. `scripts/release-linux.sh` publishes the release on that
pushed tag (it refuses unless HEAD is the tagged commit).

## Push policy

Inherits from the user's global `~/.claude/CLAUDE.md` § 6
(public repos: push freely; private: batch + ask). Detect repo
visibility once per session via
`gh repo view --json visibility -q .visibility` and cache.
This repo is **public**, so commits push freely.

**Tags too — `--follow-tags` is fine here** (user decision 2026-08-18). **A
phase tag is a build marker and carries nothing private**, so publishing it costs
nothing on a public repo.

This repo used to hold that `<ID>-complete` tags stay local until you authorise a
push. **That rule is retired because it was never enforceable**: `cut-release`
Phase 5 on a public repo is `git push --follow-tags origin <branch>`
(`~/.claude/skills/cut-release/SKILL.md` § Phase 5), and `/close-phase` Step 6
offered the same command while this project still ran it. Both took the push
path every time here, so the tags went up regardless.

**Do not reinstate the ban without changing the tooling first.** Three earlier
drafts tried, and each contradicted itself —
[`docs/history/claude-md.md`](docs/history/claude-md.md).

**Still `--follow-tags`, never `--tags`.** Global `~/.claude/CLAUDE.md` § 6
forbids the latter by name: it publishes *every* local tag, including ones never
meant to leave the machine, where `--follow-tags` sends only the annotated tags
reachable from what you are already pushing.

### Doc-only pushes skip the FULL gate, never the prose checks (user directives 2026-08-05, 2026-08-18)

A push that touches **only** documentation does not run the full gate. It runs
the documentation checks — the test suites that read prose, and `gitleaks` —
and nothing else. **`.githooks/pre-push` makes that choice itself** (FIBR-0373):
a plain `git push` is the whole route, with no `--no-verify`. **This section is
the standing authorisation
[`docs/standards/commits.md` § 2.3](docs/standards/commits.md) requires** for
the hook to skip the rest of the gate on such a push. GitHub CI skips it too
(`paths-ignore: ["**.md"]` on `push` in `ci.yml`; a pull request still runs
everything). The documentation checks take a few seconds. To run them by hand:

```bash
./scripts/ci-local.sh --docs     # DOCS_SUITES + gitleaks --redact; the hook runs the same
```

**The suite list lives in `scripts/ci-local.sh`'s `DOCS_SUITES` alone.** Its
`gitleaks` line keeps **`--redact`**: without it a hit prints the secret in
clear, and § Build and test three screens up says never to print those values.

**These suites read tracked prose, and the list is ENUMERATED, so it can go
stale.** It has, twice. **Do not justify the skip by claiming no Python stage
reads prose** — that is the false claim both earlier versions rested on, and it
is why the list is now bound to the tree by a guard rather than kept by hand
([`docs/history/claude-md.md`](docs/history/claude-md.md)):

- **`tests/features/harness/`** (FIBR-0001 INV-1) reads
  **`docs/specs/FIBR-0001.md`** and compares its stage table against
  `scripts/ci-local.sh`, so a "doc-only" edit to *that one spec* can
  genuinely turn the suite red. **This is why the old
  "not `docs/specs/FIBR-0001.md`" carve-out is gone rather than dropped**
  — the check that enforced it now runs on every doc-only push, so the
  exception has nothing left to do.
- **`tests/features/account_detect/test_no_real_data.py`** (FIBR-0086
  INV-8) walks `git ls-files` and reads **every tracked text file** —
  specs, ROADMAP, CHANGELOG included. That is deliberate: the guard binds
  prose, because a real account number reached a spec once and sat there a
  month (FIBR-0244).
- **`tests/features/release_integrity/`** (INV-7) reads
  **`docs/security-model.md`** and asserts the signed-`SHA256SUMS` note, an
  `INV-13` definition, and that the 800 characters after it name `SHA256SUMS`
  and match `sign|Ed25519`. **Reflowing that section is enough to turn it
  red** — the paragraph does not have to be wrong, only rearranged.
- **`tests/features/flatpak_packaging/`** asserts `packaging/flatpak/README.md`
  **exists**, so moving or deleting that doc is a red doc-only push. Existence
  only — it never reads the contents.
- **`tests/features/prose_checks/`** (FIBR-0278) reads **this file** — it
  asserts the fenced command in this section runs `ci-local.sh --docs` and
  names no suites of its own. It also asserts `DOCS_SUITES` matches its
  `_READS_PROSE` ledger, and that every directory under `tests/features/` is
  sorted into that ledger or into `_NO_PROSE`.
- **`gitleaks dir .`** scans prose too, and `.githooks/pre-push` exists
  because of a red **docs-only** commit (`a0cc895`).

**The membership rule: a suite belongs here if it reads a tracked doc's
CONTENTS or requires one to EXIST.** Two near-misses, so the rule is not
theoretical — `bundling` cites specs in its docstring only, and `gitignore`
names `docs/design.md` but tests it inside a fresh tmp repo holding a copy of
`.gitignore` alone, so that file's real presence is irrelevant and deleting it
turns nothing red.

**No grep re-derives this list, so do not try to.** `account_detect` walks
`git ls-files` and reads every tracked text file without naming one, so no path
literal betrays it — any search-based audit misses the broadest member.
`tests/features/prose_checks/` (**FIBR-0278**) is the guard instead: it fails if
`DOCS_SUITES` and its `_READS_PROSE` ledger disagree, and it fails if any
suite directory is sorted into neither ledger. Add a suite to **both** places —
`DOCS_SUITES` and the ledger it checks against — whenever you write one
that reads a doc; the guard is what catches you if you only do one. Why it is a
guard rather than a hand-kept list: [`docs/history/claude-md.md`](docs/history/claude-md.md).

**How the hook decides a push is doc-only, and why it is built that way:**
[`.claude/rules/gate.md`](.claude/rules/gate.md). Read it before changing
`.githooks/pre-push`.

**`.corpus-numbers` is what makes the guard real, and it is per-machine.** Where
it exists `test_no_real_data.py` runs; where it does not that test skips, and
`gitleaks` does not match an account number — so such a machine has no cover for
this class at all and should not push prose it has not read.

**A code change never skips the full gate, however small.**

*This file's `review-contract` history lives in
[`docs/reviews/CLAUDE-md-review-log.md`](docs/reviews/CLAUDE-md-review-log.md),
not inline — an always-loaded file should not carry a growing audit table.*

## Cutting a release: `gh release create` is NOT the end

**Before any release step — `cut-release`, `scripts/release-linux.sh`,
`scripts/release-windows.sh` or a version bump — read
[`.claude/rules/release.md`](.claude/rules/release.md).** It holds the release
path in order, how a release has failed, and this project's `cut-release`
Phase 2b substitute (`scripts/ci-docker.sh`; user decision 2026-08-19,
FIBR-0295).

## Module map

Where each part of the tree lives, and two traps (`invariant_check` paths;
the Standard Bank import contract), are in
[`.claude/rules/module-map.md`](.claude/rules/module-map.md). It loads by
itself when a file under `src/` or `tests/` is read.

## Resumption flow — MANDATORY summarise-back

1. **`roadmap_query` for the open items** (this file is already loaded) —
   narrowed per § Where state lives item 2, since one unnarrowed call spills. State comes from the roadmap DB; § Where state lives
   item 3 says how to tell which open item is active.
2. Once `Kind` is known from the active item, read the standard
   § Where state lives item 4 maps it to — one read, two for `Kind: release`.
3. **Summarise back to the user:** "We're on `<ID>`, last did `<X>`,
   next is `<Y>`." Take `<X>` from `git log --oneline -5` and `<Y>` from the
   latest note in the active item's body (`roadmap_query id`).
4. Wait for confirm or redirect.

**Never skip step 3.** Catching state-recovery errors before
working is cheaper than corrective rounds later.

## Standards reference

The seven standards (`coding`, `naming`, `dependencies`,
`documentation`, `testing`, `commits`, `versioning`) plus
`roadmap-format` live in
[`docs/standards/`](docs/standards/) — see its
[README](docs/standards/README.md) for the index, the
closed-loop diagram, and which kinds each governs.

### One standard is knowingly out of date: spec filenames

`naming.md` line 85 still says a spec is `docs/specs/<ID>.md`, and its
line-207 counter-example says the same. **That rule is superseded** —
the user decided 2026-08-05 that specs are
`docs/specs/<ID>-<topic>.md`, because a filename a human can read
without opening it is worth the suffix. **Name a new spec the new way**;
the first file under the new rule is
`docs/specs/FIBR-0231-plain-english-month-summary.md`.

Why it is not amended yet, and what is tracked:
[`.claude/rules/spec-filenames.md`](.claude/rules/spec-filenames.md).

## Rule history

Pedigree moved out of a rule above — what it replaced, what went wrong to make
it necessary, and the measurement behind it — is in
[`docs/history/claude-md.md`](docs/history/claude-md.md).

**It is not loaded at session start, and that is the point.** This file is read
on every prompt, so a rule's reasoning is paid for on every turn while being
needed almost never: when you are about to change that rule. Read it then.

**Do not move a RULE there.** Only the story behind one. A rule that leaves this
file is a rule some session will not read (FIBR-0296, and the user's 2026-09-21
directive to move the history out).
