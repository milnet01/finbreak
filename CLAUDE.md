# finbreak — Project instructions for Claude Code

Scaffolded from the **Ants App-Build** template; follows the
`app-workflow` skill — a machine-local file at
`~/.claude/skills/app-workflow/SKILL.md`, not part of this repo.

## Where state lives

**Items 1–3 are read on every session start; 4–6 are read when you need
them, not up front.** § Resumption flow at the bottom of this file is the
operative procedure and it governs — it reads 1–3 in one batch, then pulls
the *one* standard matching the active item's `Kind`. Do not read all six
standards and the active spec before summarising: that is
six-plus reads to answer a question the roadmap DB already answers.

1. **This file** — stable rules and conventions.
2. **The roadmap DB** — **the source of truth on current state**: what is
   open, in progress and next. `ROADMAP.md` is **generated from it**, and the
   generated file is what gets committed and pushed. **Never hand-edit that
   file** — the next render overwrites you. Query the DB with `roadmap_query`
   rather than reading a 600 KB file: **`status:"active"`** for the open items
   (that is planned + in-progress — the resumption flow's call), `id` / `ids`
   for one item **with its body**, `mode:"headline_only"` for a cheap survey.
   **A filtered call withholds bodies** (the envelope says so, with
   `bodies_omitted: true`) **but still returns `kind` as a field** — so the
   survey answers § Resumption flow step 2 on its own; no second call is
   owed. A targeted `id` / `ids` fetch returns bodies without `include_body`.
   Write through `roadmap_log`, which enforces the format and **re-renders the
   whole file on every write** (`items_rendered: 277` on a one-item annotate)
   — that render is what overwrites a hand edit. Keep a bold headline on **one
   line**: a wrapped one renders its continuation at column 0, which markdown
   reads as a new list item. (User decision 2026-08-18, FIBR-0281.)

   **The freshness check a session owes before writing has two halves, because
   the two verbs read different things.** `roadmap_query` on the id it is about
   to touch, reading the body back — and again after every flip or annotate,
   because a note can land mid-bullet and still report success. Then the
   file-side half: `roadmap_log` locates against the **file** while
   `roadmap_query` reads the **store**, so a store-only item is queryable but
   not writable and refuses `bullet_not_found`. A `dry_run` on the write you
   are about to make is the cheapest test of **that half** — it resolves the
   locator and echoes `from_status`. It returns no body, so the read-back is
   still owed. And there is **no delete verb**, so an `append` cannot be
   undone — reverting the file with git leaves the item orphaned and the
   next render injects it back. Get
   an append right first time.

   **`roadmap_migrate` re-ingests the file into the store, and on this project
   you should almost never need it.** It only reads `ROADMAP.md`, so a byte-
   identical file afterwards is the verb working, not a failure. **Run it only
   when you KNOW something other than `roadmap_log` wrote the file** — an
   external merge, a restore from git. **Never on the strength of its
   counters**, which do not measure staleness: measured 2026-08-19 on a tree
   where every `ROADMAP.md` change had come through `roadmap_log`, a `dry_run`
   still reported **10 items updated** (`body`, `layman`, `source`, `extras`).
   The cause is that the render → parse round trip is not lossless — **a
   property of the round trip, so it applies to EVERY run, the sanctioned ones
   included.** `updated_items[]` is the verb's plan to write those re-parsed
   bodies over correct ones, in a store shared by every project on this
   machine. **So always `dry_run` first and read `updated_items[]` item by
   item**; anything you cannot account for as a real edit to the file is the
   round trip, and a real run would clobber it.

3. **`.claude/workflow.md` §1** — the small set of facts that
   live nowhere else: repo visibility, convergence checkpoint,
   debt-sweep threshold, active item + step. **The DB owns which items
   are in progress; §1 owns which ONE of them is active, and the step
   within it** — the DB can carry several 🚧 at once and does not say
   which is being worked, so neither file answers the other's question.
   Deliberately thin (FIBR-0229); it is *not* a narrative of recent work. After
   reading both, **summarise back to the user** before doing any
   work.
4. **`docs/standards/{coding,naming,dependencies,documentation,testing,commits}.md`**
   — the six shareable v1 standards. Read the **one** matching the active
   item's `Kind` — not all six. (§ Resumption flow step 2 is where that
   read happens, and it governs.)
5. **`docs/specs/<active-id>.md`** — the contract for the
   currently-active roadmap item. Read it when you start work on that
   item; not every item has one (see § Spec discipline in the global
   rules — most work needs no spec).
6. **`docs/audit-allowlist.md`** — read **additionally** before
   invoking `check-code` or `review-code` so already-confirmed
   project-specific false positives aren't re-flagged. The
   allowlist is the closed-loop memory for this project — see
   the "False-positive learning" section of the `app-workflow`
   skill (`~/.claude/skills/app-workflow/audit-fold.md`).
   (`check-code` replaced `/audit` on 2026-08-15 and `review-code`
   replaced `/code-quality-review` on 2026-08-18; the allowlist read is
   keyed to the job, not the old name.)

## Closing a phase

Run **`/close-phase`** once steps 1–4 of the per-phase loop
are done — see SKILL.md for the full description.

## Cold-eyes review cadence (project override)

finbreak is **correctness-critical** — it handles people's money, and a
wrong-day / wrong-zone / wrong-total bug is exactly the class of error users
won't forgive. So a spec gets one loop more than the skill would give it: run
**`review-contract <path> --max-loops 3`** for this project, on **every**
genre. The skill's own default is 2 for a spec or plan and 3 for a standard or
an ADR, so this raises the spec/plan cap by one and leaves a standard's where
it already was.

**The cap was 7 for specs and plans until 2026-08-19** (user directive
2026-07-11, carried over unchanged when `review-contract` replaced
`/cold-eyes`). It came down because the extra loops stopped paying once the
skills and the app-workflow were redesigned. The measurement is this file's own
2026-08-18 gate: three loops, 19 verified findings, and by loop 3 half of them
were the review's own collateral — so a fourth loop mostly repairs the third's
repairs. A spec reaching its cap is a normal exit; the build is the next
reviewer.

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

**Requirements:** Python ≥ 3.12 and the standalone binaries below on `PATH` —
none of them pip packages. Every one carrying a version is pinned by
`scripts/ci-setup.sh` (that script is the list; no count is stated here, so
adding one cannot make this go stale):

| Binary | Pinned | Why the version matters |
|---|---|---|
| [`git`](https://git-scm.com/) | any | **a run-time dependency of the gate, not just of checkout** — the gitignore and bundling feature tests shell out to `git check-ignore` / `git rev-parse` / `git ls-files` |
| [`gitleaks`](https://github.com/gitleaks/gitleaks/releases) | 8.30.1 | a different build runs a different rule engine over the same `.gitleaks.toml` |
| [`shellcheck`](https://github.com/koalaman/shellcheck/releases) | 0.11.0 | rule set differs per release; distro builds lag badly |
| [`actionlint`](https://github.com/rhysd/actionlint/releases) | 1.7.12 | ships its own checks *and* shells out to `shellcheck` |
| [`zizmor`](https://github.com/zizmorcore/zizmor/releases) | 1.29.0 | audit set grows per release; a newer build fails a tree an older one passed |

Each **pinned** one is version-sensitive the same way: an older build runs a
**different rule set over the same files**, so a local gate can pass where CI
fails (or vice versa). Check with `gitleaks version`, `shellcheck --version`,
`actionlint --version`, `zizmor --version`.

**One-time dev setup** — an isolated env, then `scripts/ci-setup.sh`, which
installs *everything else the gate needs and does not itself provide*: the
system libraries PySide6 dlopens, `git`, the pinned binaries above, the dev
toolchain (ruff, bandit, pip-audit, pytest, pytest-qt, mypy + `types-PyYAML`)
**and the runtime deps** (PySide6, SQLCipher, pikepdf), which the FIBR-0003
self-test guard imports. It is the same script `ci.yml` and `ci-docker.sh` call,
so a local environment cannot drift from CI's:

```bash
python3 -m venv .venv
. .venv/bin/activate
./scripts/ci-setup.sh                    # ← the step that makes the gate runnable
```

**Do not skip that third line.** Without it `./scripts/ci-local.sh` below exits
**127** at the first tool it cannot find — the venv is fine, the gate simply has
no tools. *Which* tool depends on what you skipped: skip `ci-setup.sh`
entirely and it dies on `ruff: command not found`, because `ruff` is the
gate's very first stage and the script's Python half is what installs it.
Install the dev group by hand but not the pinned binaries (the openSUSE route
below) and it gets as far as `shellcheck`/`git: command not found` instead.
**The two fixes are NOT the same.** On an apt host, run `ci-setup.sh`. On this
desktop it cannot help you — the script is apt-only — so install the
Requirements binaries, `git` and the Qt libraries by hand per the openSUSE route
below. Verified by executing this section in a clean container 2026-08-11
(FIBR-0260).

`ci-setup.sh` assumes a **Debian/Ubuntu apt** host (the
`python:3.12-slim-bookworm` image CI runs; it falls back to `sudo` when not
root). On any other distro — this desktop is openSUSE — install the
Requirements binaries, `git` and the Qt system libraries `ci-setup.sh` names by
hand, then run its Python half yourself:

```bash
python -m pip install --upgrade pip      # PEP 735 --group needs pip >= 25.1
python -m pip install --group dev
python -m pip install .                  # runtime deps — the self-test test loads them
```

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
no CVE. That second run costs ~28s of the gate's runtime:

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
`.corpus-numbers` in a text editor, one account number per line, exactly as
printed on the statement. Spacing and dashes do not matter: the guard runs
`normalise_account_number` before comparing, and its search pattern allows any
run of separators between digits, so a number split by a line-wrap is still
found.

A `printf … > .corpus-numbers` recipe stood here until 2026-08-18 and was the
defect **FIBR-0276** filed: a shell command line lands in `~/.bash_history` —
and in an agent's transcript — which the never-list below did not name. An
editor writes to no history.

**This is a step the user performs and an agent cannot.** The values are the
user's real account numbers, and an agent must not invent them. It must never
**print, echo, quote or otherwise surface the file's contents** — not to check
the user typed them correctly, not anywhere. That is the rule; *reading the
bytes* is not. The one sanctioned read is the shell substitution below, which
hands the values to `pytest` without them appearing on a command line, in
`~/.bash_history`, or in a transcript. Counting lines is fine; showing one is
not.

Without it `tests/features/account_detect/test_no_real_data.py` **skips**, and
a skipping test reads as coverage while providing none — which is exactly what
it did on every run until the file existed on **2026-08-18**. FIBR-0248 wired
the file route on 2026-08-14; it did not create the file, so the guard went on
skipping for four more days. **Wiring a source is not the same as supplying
one**, and only the second date is when the tree was first actually scanned. `FINBREAK_CORPUS_NUMBERS`
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
below). CI (`ci.yml`) runs this exact script, so a green local gate means green in CI
**for everything the environment does not decide** — see the container caveat
below for the part it cannot cover. The commonest way a red push slips through
is simply *forgetting to run the gate*, and the version-controlled hook at
`.githooks/pre-push` closes that gap. It is enabled
in this clone; a **fresh clone must enable it once**:

```bash
git config core.hooksPath .githooks
```

(A rare `pip-audit` timeout — against either pypi or osv.dev — can make the
hook flake on a non-finding; retry, or `git push --no-verify` for that
transient case. Those two are the gate's only network-dependent stages.)
**That is not the only sanctioned `--no-verify`** — a doc-only push takes it as
its normal route, having run the prose checks by hand instead (§ Doc-only
pushes below). Read this line alone and you run the full gate on every ROADMAP
annotation.

**A tag-only push needs no `--no-verify` and never did: the hook skips it by
itself.** Pushing a branch and then its tag used to run the same ~3-minute gate
twice on one already-gated commit, which is where the habit of reaching for
`--no-verify` on the tag came from — a bypass no project document sanctioned
(FIBR-0290). The hook now reads the ref list git gives it and exits early when
**every** ref is a tag **and** every tagged commit is already reachable from a
remote-tracking branch. Anything else still takes the gate: a branch ref
anywhere in the push, a tag whose commit is not yet on the remote (skipping
that would publish ungated code), or a hand-run hook with no refs on stdin.
Locked by `tests/features/harness/` INV-5, which runs the hook against a real
throwaway repo rather than reading it. **So do not type `--no-verify` for a
tag** — if the gate runs on one, that is the hook telling you the commit is not
on the remote yet.

**Reproduce GitHub CI's ENVIRONMENT when the diff could move it** — the local
gate runs on your desktop, which already has system libraries (Qt's
`libGL`/`libEGL`/fontconfig, `git`) that a clean CI runner lacks, so a green
local gate can still hide a red CI. That is the one gap the pre-push hook
cannot close, because the hook runs the same script in the same environment.

**It is not required before every push** — that would put a multi-minute
container rebuild in front of every commit. Run it when the diff could move
the environment: a dependency added, bumped or removed; a change to
`pyproject.toml`, `scripts/ci-setup.sh`, `ci.yml` or the Dockerfile-ish parts
of the build scripts; a new module that dlopens a system library; or the first
push after any of those. Otherwise `ci-local.sh` (or the hook) is enough. Run
the gate inside the **same container image CI uses**
(`python:3.12-slim-bookworm`, fresh installs):

```bash
./scripts/ci-docker.sh                # CI's own image + both CI scripts; needs podman/docker
```

**It runs CI's image and CI's two scripts — it is not the whole workflow.**
The two `ci.yml` steps it does not execute, and the tree it runs against, are
named in § `cut-release` Phase 2b below; do not report a green run here as a
full pipeline run.

**Do not pass `--build` to it.** The flag reaches `ci-local.sh` and sets
`FINBREAK_BUILD_SMOKE=1`, but `ci-setup.sh` installs no container runtime, so
inside the container the test hits
`pytest.skip("no container runtime (podman/docker) on PATH")`
(`tests/features/bundling/test_bundling.py:299`) and the smoke-test **silently
does not run** — a skip that reads as coverage. Run `./scripts/ci-local.sh
--build` or `./scripts/build-smoke.sh` on the host instead.

`ci.yml` and `ci-docker.sh` both run the same image and both call
`scripts/ci-setup.sh` (environment: system libs + the pinned non-pip binaries —
gitleaks, shellcheck, actionlint, zizmor — + deps) then
`scripts/ci-local.sh` (the gate) — one definition each, so local and CI cannot
drift. If a dependency bump needs a new system library, add it in **one place**
(`ci-setup.sh`).

**Run tests / a single test** (INV-6):

```bash
pytest                                              # whole suite
pytest -k package_imports                           # by keyword
pytest tests/test_smoke.py::test_package_imports    # by node id
```

The gate runs `pytest -m "not perf"` (perf excluded; integration tests run).
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

Every implementation phase ends with `git tag -a <ID>-complete`
on the closing commit. **Those phase tags are public, and that is
fine** (user decision 2026-08-18) — they are build markers on a public
repo and carry nothing private. § Push policy below has the reasoning
and is the one home for it.

**A release tag `v<X.Y.Z>` is a different thing again** — it is pushed
as part of cutting the release, without asking, per global
`~/.claude/CLAUDE.md` § 6 ("a release push goes immediately and
WITHOUT asking, on every repository"). An unpushed release tag is a
half-cut release, and the next session cannot tell a queued one from
a failed one. `scripts/release-linux.sh` assumes this: it creates
the `vX.Y.Z` ref on the **remote** via `gh release create`.

## Push policy

Inherits from the user's global `~/.claude/CLAUDE.md` § 6
(public repos: push freely; private: batch + ask). Detect repo
visibility once per session via
`gh repo view --json visibility -q .visibility` and cache;
the result is recorded in `.claude/workflow.md` § 1 status
header. This repo is **public**, so commits push freely.

**Tags too — `--follow-tags` is fine here** (user decision 2026-08-18). This
repo used to carry a rule that `<ID>-complete` phase tags stay local until you
authorise a push. **That rule is retired, and the reason is worth keeping**: it
was never enforceable. `cut-release` Phase 5 on a public repo is
`git push --follow-tags origin <branch>`
(`~/.claude/skills/cut-release/SKILL.md` § Phase 5), and `/close-phase` Step 6
offers the same command in a prompt that names the `<ID>-complete` tag it is
about to publish (`~/.claude/commands/close-phase.md`). Both take the push path
every time on a public repo, so the tags went up automatically — measured
2026-08-18, `git tag -l '*-complete'` returns 54 and the remote carries the same
54. A rule that the project's own two prescribed procedures break on every run
is a rule that was describing an intention rather than the repository.

**A phase tag is a build marker and carries nothing private**, so publishing it
costs nothing on a public repo. Three earlier drafts of this paragraph tried to
hold the line and each contradicted itself — one banned the flag outright while
`cut-release` ran it, one carved out *unless you are cutting a release* (the
exact command the sentence beside it forbade), and one claimed nothing here ever
needed the flag. **Do not reinstate the ban without changing the tooling first.**

**Still `--follow-tags`, never `--tags`.** Global `~/.claude/CLAUDE.md` § 6
forbids the latter by name: it publishes *every* local tag, including ones never
meant to leave the machine, where `--follow-tags` sends only the annotated tags
reachable from what you are already pushing.

### Doc-only pushes skip the FULL gate, never the prose checks (user directives 2026-08-05, 2026-08-18)

A push that touches **only** documentation does not run
`./scripts/ci-local.sh`. It runs the prose checks below, then pushes with
`git push --no-verify`. **This section is the standing authorisation
[`docs/standards/commits.md` § 2.3](docs/standards/commits.md) requires** —
that standard treats a skipped hook as an anti-pattern unless something
explicitly authorises it, and points back here for the one case where
something does. The full gate takes ~1m45s and most of it is aimed
at code, so paying it for a ROADMAP annotation is mostly waiting — but the
prose checks cost about **two seconds** (measured 2026-08-18: pytest 1.47s,
`gitleaks` 0.3s warm and 1.8s cold), which is not a saving worth reasoning
about.

```bash
pytest tests/features/account_detect/ tests/features/harness/ \
       tests/features/release_integrity/ \
       tests/features/flatpak_packaging/ \
       tests/features/prose_checks/                                # ~1.6s
gitleaks dir . --no-banner --redact --config .gitleaks.toml       # ~0.3s
git push --no-verify origin main
```

**Stop if either check fails — those are three independent commands, not a
chain.** A red `pytest` or a `gitleaks` hit does not stop the `git push` on the
line below it, and this route is the only thing standing in for the hook. Since
the leak guard went live (below) a failure here means pushing a real account
number. Read both results before the third line.

**`gitleaks` is copied verbatim from `ci-local.sh`'s stage — do not shorten
it.** `--config` is auto-discovered on this machine (checked 2026-08-18: bare
`gitleaks dir .` and the full form both return *no leaks found*), so the flag
that earns its place is **`--redact`**: without it a hit prints the secret in
clear, and § Build and test three screens up says never to print those values.
A check whose failure mode is "leak it to the terminal" is worse than the leak
it found.

**Five suites read tracked prose. This list is ENUMERATED, so it can go stale —
and it did.** Do not repeat the old justification for the skip — "no Python
stage reads prose" — which was simply false. Nor the version that replaced it,
"those two commands are all three of them", which was **also** false and is why
the list below is now five:

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
  red** — the paragraph does not have to be wrong, only rearranged. This suite
  was missing from the list until 2026-08-18 and all three review lanes found
  it independently.
- **`tests/features/flatpak_packaging/`** asserts `packaging/flatpak/README.md`
  **exists**, so moving or deleting that doc is a red doc-only push. Existence
  only — it never reads the contents.
- **`tests/features/prose_checks/`** (FIBR-0278) reads **this file** — it
  parses the fenced `pytest` command in this very section and asserts it
  matches its own `_READS_PROSE` ledger, and separately asserts every
  directory under `tests/features/` is sorted into that ledger or into
  `_NO_PROSE`. It is a member of its own list: editing this fenced command
  without editing that ledger (or vice versa) is exactly what turns it red.
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
A recipe here claimed otherwise for one review loop and was deleted for being
unreproducible: the plausible readings of it return 64 files and 4, and the
list was four (now five). **This list used to be maintained by hand with
nothing binding it to the tree** — which is the failure that produced two
wrong lists in one day. `tests/features/prose_checks/` (**FIBR-0278**) is
that guard: it fails if this fenced command and its `_READS_PROSE` ledger
disagree, and it fails if any suite directory is sorted into neither ledger.
Add a suite to **both** places — this fenced command and the ledger it
checks against — whenever you write one that reads a doc; the guard is what
catches you if you only do one.

**The three extra suites cost about a third of a second** — measured
2026-08-18 back to back and both warm, 1.01s (63 tests) for the old two-suite
list against 1.36s (93 tests) for these five. (An earlier draft of this line
claimed the wider list was *faster*, having compared a warm run against a cold
one. It is not; it is 0.35s slower, which is still nothing. Take the warm
number: the same recipe cold measured 3.09s immediately before it.)

**What counts as "only documentation": every path in
`git diff --name-only @{u}..HEAD` ends in `.md`.** That is the whole test, and
two things about it are deliberate.

**The unit is the PUSH, not the last commit** — every commit going up, which is
what that range gives you. Judge it by the commit you just made and an ungated
code commit already queued behind it rides through the gate on a ROADMAP line's
coat-tails, which breaches "a code change never skips the full gate" with
nothing to notice it.

**And the test is POSITIVE.** The deny-list version
of this rule — *no file under `src/`, `tests/`, `scripts/`, `.github/` or
`packaging/`* — lasted one review loop: `.githooks/pre-push` is under none of
those, so a commit touching only that file passed the test word for word. It is
shell, and `ci-local.sh`'s shellcheck stage names it explicitly
(`shellcheck "${SH_FILES[@]}" .githooks/pre-push`), so the "doc-only" route
would have skipped the one stage that reads what you just changed.
`.gitleaks.toml`, `.gitignore` and any stray `.sh`, `.toml` or `.yml` fail a
deny-list the same way. **A closed list of directories cannot express "not
code"; a suffix can.**

**A `.md` anywhere counts** — `tests/features/<name>/spec.md` and
`packaging/flatpak/README.md` included. The five suites and the `gitleaks`
scan above are what cover those. Anything else takes the full gate.

**Why this replaced the digit test.** Until 2026-08-18 the rule asked
whether the commit added "digits or key-shaped strings", and demanded the
checks only then. Two things retired it. The judgement falls to the person
least able to make it — you have just written the prose and know what you
meant by it, which is exactly when a pasted number does not read as one.
And the judgement was buying **under two seconds**. A branch that trades a
silent, unrecoverable failure against two seconds should not be a branch.

**The leak guard went live on 2026-08-18**, when `.corpus-numbers` was
created on this machine: `test_no_real_data.py` now runs instead of
skipping (56 passed, 0 skipped, where it was 55 passed and 1 skipped). It
passed on first run, so no real number is in the tracked tree today.
Before that date the guard was inert and the skip was safer than it
looked; it is not inert now, which is the change that makes this rule earn
its keep. **A machine without `.corpus-numbers` runs the same two
commands** — the guard skips there and `gitleaks` does not match an
account number, so that machine has no cover for this class at all and
should not push prose it has not read.

**A code change never skips the full gate, however small.**

*This file's `review-contract` history lives in
[`docs/reviews/CLAUDE-md-review-log.md`](docs/reviews/CLAUDE-md-review-log.md),
not inline — an always-loaded file should not carry a growing audit table.*

## Cutting a release: `gh release create` is NOT the end

`cut-release` carries the version bump, the tag and the GitHub release
**but not the downloads**. `.claude/bump.json` carries less still — its
`_comment` says "this recipe covers the version bump only -- the signed
AppImage build + publish is a separate manual step". The AppImage and
the Windows `.exe` are built and attached by `scripts/release-linux.sh`
and `scripts/release-windows.sh`, and **nothing invokes those for you**.
(`bump.json` names the lower-level `scripts/build-release-appimage.sh`
and a hand-run `gh release create`; the two wrappers are what to run
today.)

**v0.1.20 published with ZERO assets and it went unnoticed for ten
days.** Both the README's "download the latest release" link and the
in-app updater resolve to that page, so both were dead the whole time.
Found 2026-08-17 while cutting 0.1.21. **The guard LANDED on 2026-08-19**
(FIBR-0275, INV-8): both release scripts now read the published asset
list back and refuse to report success on an incomplete set. What it
still cannot catch is nobody running `release-linux.sh` at all — which
is exactly how v0.1.20 shipped empty — so the eight-asset read-back at
the end of this section is still yours to run by hand. (Same class as FIBR-0203,
which was closed as a one-off rather than guarded — that is why it
recurred.)

So the release path is, in order — the bump comes first, and the
**push** is a step rather than a tidy-up:

```bash
cut-release <X.Y.Z>          # a SKILL — invoke it; it is not on PATH. Bumps every
                             #   version-bearing file, commits, tags, pushes, and
                             #   creates the release — with NO assets on it
. .venv/bin/activate         # both scripts need cryptography
./scripts/release-linux.sh   # AppImage + .sig + SHA256SUMS + SHA256SUMS.sig
                             #   + linux SBOM  -> FIVE assets
./scripts/release-windows.sh # .exe + .sig + windows SBOM, and it RE-UPLOADS
                             #   SHA256SUMS + .sig having merged into them
# then re-pin the Flatpak commit: (below)
```

**`cut-release` is what performs step 1**, including the commit, the tag
and the push, so do not hand-run those as well. If you bump by hand
instead, the bump must be committed **and pushed** before
`release-linux.sh` — see the first bullet below. Either way step 1 must
have happened: run `release-linux.sh` against an unbumped tree and it
reads the *old* `__version__`, finds that release already exists, and
`--clobber`s assets onto the **previous** release.

Four things worth knowing before you run them:

- **The bump must be PUSHED, not merely committed.** `release-linux.sh`
  refuses with "working tree is dirty — **commit + push** the bump
  first", but it only tests `git status --porcelain` — so a
  committed-but-unpushed bump *passes* and the script then creates the
  tag on the **remote**, off the remote's HEAD, i.e. the pre-bump
  commit. Nothing catches that. (`dist/` is gitignored, so a dirty tree
  here is your own ROADMAP or CHANGELOG edit.) Do not pipe either script
  through `grep`/`tail` while debugging — that masks its exit status and
  a refusal reads as success.
- **`release-linux.sh` is safe against a release that already exists** —
  step 7 branches to `gh release upload --clobber`. So a release created
  by hand first (as 0.1.21 was) is repaired rather than duplicated.
- **`release-windows.sh` needs no Windows machine**; it dispatches
  `windows-build.yml` on the tag and waits, so it needs `gh` with
  **workflow + repo** scope but **no container runtime** — the freeze
  happens on a GitHub runner. Public repo, so the minutes are free.
  Only `release-linux.sh` needs `podman`/`docker` (it builds and
  clean-rooms the AppImage locally). **Both** need the Ed25519 key at
  `release/finbreak-signing.key` — gitignored, local-only, and already
  present on this machine. **Do not run `scripts/gen-signing-key.py` to
  "fix" a missing key**: it mints a *new* one, which the hard gate
  against the committed `RELEASE_PUBLIC_KEY_B64` then rejects, and a
  release signed with it would be invisible to every installed copy's
  updater.
- **Re-pin the Flatpak `commit:` afterwards.** `bump.json` bumps the
  manifest's `tag:` mechanically, but its sibling `commit:` cannot be —
  the sha does not exist until the release is tagged. `release-linux.sh`
  prints the sha as its last line; set it in
  `packaging/flatpak/io.github.milnet01.finbreak.yaml`. Nothing verifies
  the two point at the same object — one of the two gaps left in the
  release path, the other being that nothing checks `release-linux.sh`
  was run at all (FIBR-0275).

Finish by reading the result back yourself — **not** because the scripts skip
it. Since 2026-08-19 each one re-reads its own upload and refuses to report
success on an incomplete set, both doing so *before* they print "DONE". The gap
is the one named above: nothing catches a script that was never run.

```bash
gh release view v<NEW> --json assets -q '[.assets[].name]|join(", ")'
```

**A complete release carries EIGHT assets**, and anything less is broken
rather than quiet: the AppImage, the `.exe`, a `.sig` for each,
`SHA256SUMS`, `SHA256SUMS.sig`, and **both** SBOMs
(`finbreak-<V>-linux.cdx.json` *and* `finbreak-<V>-windows.cdx.json`).
Compare against v0.1.18, v0.1.19 and v0.1.21, which all carry exactly
that set. A five-asset read-back means the Windows half has not landed —
still building, or failed — and `release-windows.sh` exits non-zero
*after* the Linux assets are already public, so a red Windows build
leaves a `--latest` release the README and the updater both resolve to
with no Windows download. Re-run it; do not walk away from a short list.

**Expect transient GitHub API failures, and retry before diagnosing.**
Cutting 0.1.21 hit them on four different endpoints — `gh repo view`
(503), `git push origin <tag>` (401), the `windows-build.yml` dispatch
(503, three times from inside the script while `gh release view` and
`gh workflow list` both worked and githubstatus reported Actions
operational), and the asset upload. Every one cleared on a retry.

**The upload failure is the dangerous one, because it half-succeeded.**
`release-windows.sh`'s final `gh release upload --clobber` deletes each
existing asset before replacing it, so a 503 mid-list left v0.1.21
carrying `SHA256SUMS.sig` but **not** `SHA256SUMS`, and `.exe.sig` but
**not** the `.exe` — a signed release whose signed manifest was gone.
Nothing reported an error loudly; the script had already printed its
signing successes.

If you land there, the artifacts in `dist/` are already built, signed
and verified, so re-upload them rather than rebuilding — **one file per
call, so a partial failure is visible**:

```bash
for f in dist/finbreak-<V>-x86_64.exe dist/finbreak-<V>-x86_64.exe.sig \
         dist/SHA256SUMS dist/SHA256SUMS.sig dist/finbreak-<V>-windows.cdx.json; do
    gh release upload v<NEW> "$f" --clobber || echo "FAILED $f"
done
```

Then read the assets back again. A batched upload wrapped in a pipe is
how the half-state goes unnoticed twice.

If the *dispatch* is what is failing, **just re-run
`release-windows.sh` until it gets through** — the 503 is intermittent,
not deterministic, and it took six attempts on 0.1.21. Do **not**
dispatch by hand as a workaround: the script's line 48 is an unguarded
`gh workflow run` under `set -euo pipefail`, so it dispatches its *own*
run and waits for a run newer than the one it recorded on entry. Your
hand-dispatched build is discarded, and you have burned a Windows
freeze for nothing (that happened twice on 0.1.21).

Finish the Windows half through the script, never by hand: the steps
you would be skipping are the Ed25519 signing and its verification
against the committed public key.

### `cut-release` Phase 2b on this project is `scripts/ci-docker.sh` (user decision 2026-08-19, FIBR-0295)

`cut-release` Phase 2b runs the CI pipeline locally *before* the release
commit, and the skill's own rule is to execute `.github/workflows/*.yml` with
`act` and **never** substitute anything — because a hand-written mirror
"returns green for a pipeline that will fail". **On this project the substitute
is sanctioned, and this section is that authorisation.** `act` is installed on
this machine (`/usr/bin/act`) and has never been configured: with no TTY its
first run prints a runner-image menu and dies `level=fatal msg=EOF`, so the
phase cannot run as designed. Filed as **FIBR-0295**; the decision is to adopt
the substitute rather than configure `act`.

**So Phase 2b here is `./scripts/ci-docker.sh`**, and the session's own
Phase 2b report names the three uncovered items below. **Not the published
release notes** — those are `cut-release`'s, lifted from the `CHANGELOG.md`
`[X.Y.Z]` section, and they are what end users read on the download page, so a
CI-coverage caveat does not belong there. (`release-linux.sh` sets notes only
on its `gh release create` branch, which the documented order never reaches:
`cut-release` has already created the release, so the script takes
`gh release upload --clobber` and touches the notes not at all.)

**Why the ban does not bite: `ci-docker.sh` is not a mirror of the pipeline, it
is the pipeline's own two scripts.** `ci.yml` has one job, four steps — install
`git`, `actions/checkout`, `./scripts/ci-setup.sh`, `./scripts/ci-local.sh` —
inside `container: python:3.12-slim-bookworm`. `ci-docker.sh` runs the **same
image** and calls the **same two scripts by name**. There is no second
definition of the gate that could drift from the first, which is exactly the
failure the skill's rule protects against, and FIBR-0001 INV-2 locks the
single definition with `tests/features/harness/` enforcing it.

**Three things it does NOT cover.** State them; do not report a full pipeline
run.

1. **`actions/checkout` running at all** — a bad SHA, a network failure, a
   revoked action. Its *static* properties are still checked here: `zizmor`
   is a `ci-local.sh` stage, so this run does read `ci.yml`'s pin and
   `persist-credentials: false`. Measured 2026-08-19 — `zizmor
   .github/workflows/` exits **0** on the real tree and **14** with the pin
   reverted to `actions/checkout@v7`. So do not list the pin as uncovered;
   what is uncovered is the step executing.
2. **The `apt-get install git ca-certificates` step** before checkout. Its
   *effect* is covered — `ci-setup.sh` installs `git` as well — but the step
   itself never executes.
3. **The tree under test, which is the one worth knowing.** `ci-docker.sh`
   does `cp -a` of your working directory into the container, so gitignored
   and untracked files travel with it; `actions/checkout` hands CI a clean
   clone of **tracked files only**. Verified 2026-08-19 by running that `cp`
   and listing the result: `.corpus-numbers` reaches the container. So a gate
   stage that reads an untracked file passes here without having been tested
   the way CI will run it.

**If `act` is ever configured on this machine this override lapses.**
*Configured* means `~/.config/act/actrc` exists **and**
`act push -W .github/workflows/ci.yml -n </dev/null` exits 0. Check both at
Phase 2b — `act --version` succeeds on an unconfigured install and settles
nothing. Measured 2026-08-19: `actrc` is absent and that dry run exits **1** on
`level=fatal msg=EOF`, so the override stands. When it lapses, Phase 2b goes
back to executing the workflows themselves and this section is deleted rather
than left standing as a second answer.

## Module map

`src` layout; the package is `finbreak`, found by pytest via
`pythonpath = ["src"]` (no editable install needed for the gate).

- `src/finbreak/` — the application package. `__init__.py` (`__version__`),
  plus `__main__.py` + `_selftest.py` — the `python -m finbreak --self-test`
  entry point that loads Qt + SQLCipher + qpdf (FIBR-0003). UI / services /
  repositories / crypto modules land from P02 (see
  [`docs/design.md`](docs/design.md) for the layered architecture).
  - **Batch import (FIBR-0085)** spans three of those layers:
    `services/batch_import.py` holds every decision (the scan ladder, the
    stored-password ladder, the cumulative dedup counts, the caps) and is
    Qt-free so all of it is testable headless; `ui/import_batch.py` is the
    review-step table; `importers/sniff.py` is the Qt-free format detection
    lifted off the wizard so the service could call it. `ui/import_wizard.py`
    gained a fourth step and the scan/ask/run chain, and
    `ui/account_picker.py` gained a Create-an-account affordance.
  - **The Standard Bank import contract is stated in
    [`docs/specs/FIBR-0050.md`](docs/specs/FIBR-0050.md) INV-11 — amend it in the
    same commit that changes the behaviour.** It is the canonical "all-or-nothing,
    and here is every way a statement can be refused" clause, and it had been
    silently falsified twice before FIBR-0255 found it: FIBR-0216 added the
    zero-amount degrade and FIBR-0252 made `parse` return per-row errors, neither
    updating INV-11, which still read "any `parse_transaction` rejection raises …
    no partial import". A session reading it as canonical builds to a contract
    that has drifted. The matching trap in the code: `_draft` decides
    degrade-vs-refuse on the **amount**, never on the rejection reason —
    `parse_transaction` checks description and date first, so a printed `0.00`
    line can be rejected for its *date* and must still degrade (FIBR-0255 §4.1).
- `tests/` — pytest suite. `tests/test_smoke.py` asserts the package imports;
  `tests/features/<name>/` (spec.md + test) and `tests/fixtures/<rule>/` arrive
  with the features they cover
  ([`docs/standards/testing.md`](docs/standards/testing.md)).
- `scripts/ci-local.sh` — the one-command quality + security gate (`--build`
  adds the FIBR-0003 bundling smoke-test).
- `scripts/ci-setup.sh` — the shared CI **environment** prep (system libs
  PySide6 needs + the pinned non-pip binaries — gitleaks, shellcheck,
  actionlint, zizmor — + Python deps). Called by BOTH `ci.yml` and
  `ci-docker.sh` so the environment has a single definition.
- `scripts/ci-docker.sh` — re-run CI's own image and CI's own two scripts
  locally (`python:3.12-slim-bookworm`, then `ci-setup.sh` + `ci-local.sh`). Run
  before pushing **when the diff could move the environment** — § Build and test
  lists those triggers and says it is not required before every push. Not the
  whole workflow either — § `cut-release` Phase 2b names what it misses.
- `scripts/build-smoke.sh` (+ `_build-smoke-in-container.sh`) — freeze the app
  in a `python:3.12-slim-bookworm` container (glibc ~2.36) and launch it in a
  Python-free `debian:13-slim` container (FIBR-0003).
- `scripts/` also holds the release path: `build-release-appimage.sh`,
  `build-windows-exe.py` (+ `windows_freeze_flags.py`), `release-linux.sh`,
  `release-windows.sh`, `gen-signing-key.py`, `sign-release.py`,
  `gen-checksums.sh`, `make-icons.sh`, and the demo/screenshot helpers
  `seed_demo_vault.py` + `capture_screenshots.py`.
- `packaging/` — the distro recipes: `packaging/flatpak/` (Flathub manifest,
  FIBR-0159) and `packaging/obs/` (openSUSE Build Service `.spec`, `debian/`,
  `_service`, metainfo + desktop files, FIBR-0155).
- `assets/` — the app icon set and the README screenshots.
- `.github/workflows/ci.yml` — CI mirror; runs INSIDE `python:3.12-slim-bookworm`
  and calls `ci-setup.sh` then `ci-local.sh` — the same image + scripts as
  `ci-docker.sh`, so the *gate definition* cannot drift (single source of truth,
  INV-2). The workflow around that gate is a different thing — § `cut-release`
  Phase 2b names what a local run does not reach.
- `.github/workflows/build-smoke.yml` — the dedicated, opt-in build job
  (`workflow_dispatch` + weekly), not run on every push.
- `.github/workflows/windows-build.yml` — the on-demand Windows `.exe` freeze
  (unsigned; Authenticode signing is FIBR-0133, still blocked).
- `pyproject.toml` — metadata, pinned runtime deps + `dev`/`build` groups,
  ruff / pytest / bandit / mypy config.

## Resumption flow — MANDATORY summarise-back

Per the app-workflow skill:

1. **Parallel batch (one tool-call batch):** this file +
   `.claude/workflow.md` §1 + `roadmap_query` for the open
   items. **State comes from the roadmap DB, not from §1** — §1
   carries only the settings and the active item (FIBR-0229).
2. Once `Kind` is known from the active item, read the
   matching `docs/standards/<which>.md` (single read).
3. **Summarise back to the user:** "We're on `<ID>` step
   `<N>`, last did `<X>`, next is `<Y>`."
4. Wait for confirm or redirect.

**Never skip step 3.** Catching state-recovery errors before
working is cheaper than corrective rounds later.

## Standards reference

The six standards (`coding`, `naming`, `dependencies`,
`documentation`, `testing`, `commits`) plus `roadmap-format` live in
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

`naming.md` is not amended yet on purpose. Amending *this* rule changes
what a conformer writes — the spec filename — so it trips rule 14's gate
(`review-contract <path> --genre standard`); and back-migrating the 54
existing `FIBR-NNNN.md` specs means repointing 374 inbound citations —
so both halves are tracked as **FIBR-0196** rather than done in passing.

**Not every `docs/standards/` edit owes that gate.** Rule 14's trigger is
a *change of direction*, not an edit: "would someone conforming to this
document now do something different? Name the line." A corrected date, a
fixed count, a dead link or a reworded example changes nothing anyone
writes — record the check in one line of the commit body and move on. In
the grey zone, do **not** gate. This note exists so a session that reads
`naming.md` and not that bullet does not name the next spec wrongly.
