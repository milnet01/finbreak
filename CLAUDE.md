# finbreak — Project instructions for Claude Code

Scaffolded from the **Ants App-Build** template; follows the
`app-workflow` skill — a machine-local file at
`~/.claude/skills/app-workflow/SKILL.md`, not part of this repo.

## Where state lives

**Items 1–3 are read on every session start; 4–6 are read when you need
them, not up front.** § Resumption flow at the bottom of this file is the
operative procedure and it governs — it reads 1–3 in one batch, summarises
back, then pulls the *one* standard matching the active item's `Kind`. Do
not read all six standards and the active spec before summarising: that is
six-plus reads to answer a question the ROADMAP already answers.

1. **This file** — stable rules and conventions.
2. **`ROADMAP.md`** — **the authority on current state**: what
   is open, in progress and next. Written by the `roadmap_log`
   MCP verb on every status change, so it does not drift.
   Query it with `roadmap_query` rather than reading 4000 lines.
3. **`.claude/workflow.md` §1** — the small set of facts that
   live nowhere else: repo visibility, convergence checkpoint,
   debt-sweep threshold, active item + step. Deliberately thin
   (FIBR-0229); it is *not* a narrative of recent work. After
   reading both, **summarise back to the user** before doing any
   work.
4. **`docs/standards/{coding,naming,dependencies,documentation,testing,commits}.md`**
   — the six shareable v1 standards. Read the **one** matching the active
   item's `Kind`, after the summarise-back — not all six.
5. **`docs/specs/<active-id>.md`** — the contract for the
   currently-active roadmap item. Read it when you start work on that
   item; not every item has one (see § Spec discipline in the global
   rules — most work needs no spec).
6. **`docs/audit-allowlist.md`** — read **additionally** before
   invoking `check-code` or `/code-quality-review` so already-confirmed
   project-specific false positives aren't re-flagged. The
   allowlist is the closed-loop memory for this project — see
   the "False-positive learning" section of the `app-workflow`
   skill (`~/.claude/skills/app-workflow/audit-fold.md`).
   (`check-code` replaced `/audit` on 2026-08-15; the allowlist
   read is keyed to the job, not the old name.)

## Closing a phase

Run **`/close-phase`** once steps 1–4 of the per-phase loop
are done — see SKILL.md for the full description.

## Cold-eyes review cadence (project override)

finbreak is **correctness-critical** — it handles people's money, and a
wrong-day / wrong-zone / wrong-total bug is exactly the class of error users
won't forgive. So specs get more room to settle before code: run
**`review-contract <path> --max-loops 7`** for this project — i.e. allow up to
**7** convergence loops rather than the skill's default of 2 for a spec or plan
and 3 for a standard or ADR. (User directive 2026-07-11, when the skill was
`/cold-eyes`; that skill was replaced by `review-contract` on 2026-08-12 and
the raised cap carries over unchanged.)

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
Either way the fix is the same. Verified by executing this section in a clean
container 2026-08-11 (FIBR-0260).

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

```bash
printf '%s\n' '1234 567 890 1' '9876543210' > .corpus-numbers   # never `cat` this
```

Without it `tests/features/account_detect/test_no_real_data.py` **skips**, and
a skipping test reads as coverage while providing none — which is exactly what
it did on every run before FIBR-0248. `FINBREAK_CORPUS_NUMBERS`
(comma-separated) overrides the file for a one-off run. **Never print the
values, redirect them to a tracked file, or paste them into a commit message,
spec or ROADMAP entry** — the guard binds prose, not just fixtures. CI cannot
hold them and never will, so this check is local-only by design.

**Pre-push hook — the gate runs automatically before every `git push`.** CI
(`ci.yml`) runs this exact script, so a green local gate means green in CI
**for everything the environment does not decide** — see the container caveat
below for the part it cannot cover. The commonest way a red push slips through
is simply *forgetting to run the gate*, and the version-controlled hook at
`.githooks/pre-push` closes that gap. It is enabled
in this clone; a **fresh clone must enable it once**:

```bash
git config core.hooksPath .githooks
```

(A rare `pip-audit` timeout — against either pypi or osv.dev — can make the
hook flake on a non-finding; retry, or `git push --no-verify` for that one
transient case only. Those two are the gate's only network-dependent stages.)

**Reproduce GitHub CI EXACTLY when the ENVIRONMENT could differ** — the local
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
./scripts/ci-docker.sh                # identical to the GitHub run; needs podman/docker
./scripts/ci-docker.sh --build        # ...plus the FIBR-0003 build smoke-test
```

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
on the closing commit. **Those phase tags** stay local until the
user explicitly authorises a push.

**A release tag `v<X.Y.Z>` is NOT covered by that** — it is pushed
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

**Commits, yes; `<ID>-complete` phase tags, no.** "Push freely" is
about commits and release tags. A phase tag stays local until the
user says otherwise (§ Commit conventions), so **push the branch
alone — `git push origin main`, not `git push --follow-tags`** —
unless you are cutting a release, where the `v<X.Y.Z>` tag goes with
it. `--follow-tags` publishes every annotated tag reachable from what
you are pushing, which is how a phase tag leaves the machine without
anyone deciding to send it.

### Doc-only pushes skip the FULL gate, never the prose checks (user directives 2026-08-05, 2026-08-18)

A push that touches **only** documentation does not run
`./scripts/ci-local.sh`. It runs the prose checks below, then pushes with
`git push --no-verify`. The full gate takes ~1m45s and most of it is aimed
at code, so paying it for a ROADMAP annotation is mostly waiting — but the
prose checks cost about **four seconds** (measured 2026-08-18: 2.0s +
1.8s), which is not a saving worth reasoning about.

```bash
pytest tests/features/account_detect/ tests/features/harness/   # ~2s
gitleaks dir .                                                  # ~2s
git push --no-verify origin main
```

**Three stages read prose, and those two commands are all three of them.**
Do not repeat the old justification for the skip — "no Python stage reads
prose" — which was simply false:

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
- **`gitleaks dir .`** scans prose too, and `.githooks/pre-push` exists
  because of a red **docs-only** commit (`a0cc895`).

**Why this replaced the digit test.** Until 2026-08-18 the rule asked
whether the commit added "digits or key-shaped strings", and demanded the
checks only then. Two things retired it. The judgement falls to the person
least able to make it — you have just written the prose and know what you
meant by it, which is exactly when a pasted number does not read as one.
And the judgement was buying **four seconds**. A branch that trades a
silent, unrecoverable failure against four seconds should not be a branch.

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
Found 2026-08-17 while cutting 0.1.21; the automated guard is
**FIBR-0275**, and until it lands this note is the only thing standing
between the next release and the same hole. (Same class as FIBR-0203,
which was closed as a one-off rather than guarded — that is why it
recurred.)

So the release path is, in order — the bump comes first, and the
**push** is a step rather than a tidy-up:

```bash
cut-release <X.Y.Z>          # bump every version-bearing file, commit, tag, push,
                             #   and create the release — with NO assets on it
. .venv/bin/activate         # both scripts need cryptography
./scripts/release-linux.sh   # AppImage + .sig + SHA256SUMS + linux SBOM
./scripts/release-windows.sh # .exe + .sig + windows SBOM
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
  the two point at the same object, so this is the one step with no
  guard at all.

Finish by reading the result back — the script's own "DONE" line is
printed before anything re-reads the release:

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
- `scripts/ci-docker.sh` — reproduce the GitHub CI run exactly, locally, in the
  same `python:3.12-slim-bookworm` image (`ci-setup.sh` + `ci-local.sh`). Run
  before pushing to catch environment issues a configured desktop masks.
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
  `ci-docker.sh`, so local and CI cannot drift (single source of truth, INV-2).
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
   items. **State comes from the ROADMAP, not from §1** — §1
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
