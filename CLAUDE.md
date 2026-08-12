# finbreak — Project instructions for Claude Code

Scaffolded from the **Ants App-Build** template; follows the
`app-workflow` skill — a machine-local file at
`~/.claude/skills/app-workflow/SKILL.md`, not part of this repo.

## Where state lives

Read these in order on every session start:

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
   — the six shareable v1 standards.
5. **`docs/specs/<active-id>.md`** — the contract for the
   currently-active roadmap item.
6. **`docs/audit-allowlist.md`** — read **additionally** before
   invoking `/audit` or `/code-quality-review` so already-confirmed
   project-specific false positives aren't re-flagged. The
   allowlist is the closed-loop memory for this project — see
   the "False-positive learning" section of the `app-workflow`
   skill (`~/.claude/skills/app-workflow/SKILL.md`).

## Closing a phase

Run **`/close-phase`** once steps 1–4 of the per-phase loop
are done — see SKILL.md for the full description.

## Cold-eyes review cadence (project override)

finbreak is **correctness-critical** — it handles people's money, and a
wrong-day / wrong-zone / wrong-total bug is exactly the class of error users
won't forgive. So specs get more room to settle before code: run **`/cold-eyes`
with `--max-loops 7`** for this project (not the skill's default of 5) — i.e.
allow up to **7** convergence loops before pausing to ask how to proceed.
Convergence is unchanged (a pass with no *substantive* structural / mechanical /
architectural findings — polish-only converges); the higher cap simply gives the
loop headroom to settle on this project's specs rather than hitting the ceiling
mid-refinement. (User directive 2026-07-11.)

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
**127** at its first stage (`git: command not found`, `shellcheck: command not
found`) — the venv is fine, the gate simply has no tools. Verified by executing
this section in a clean container 2026-08-11 (FIBR-0260).

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

**Pre-push hook — the gate runs automatically before every `git push`.** CI
(`ci.yml`) runs this exact script, so "green locally" already means "green in
CI"; the only way a red push slips through is *forgetting to run the gate*. The
version-controlled hook at `.githooks/pre-push` closes that gap. It is enabled
in this clone; a **fresh clone must enable it once**:

```bash
git config core.hooksPath .githooks
```

(A rare `pip-audit` timeout — against either pypi or osv.dev — can make the
hook flake on a non-finding; retry, or `git push --no-verify` for that one
transient case only. Those two are the gate's only network-dependent stages.)

**Reproduce GitHub CI EXACTLY before pushing** — the local gate runs on your
desktop, which already has system libraries (Qt's `libGL`/`libEGL`/fontconfig,
`git`) that a clean CI runner lacks, so a green local gate can still hide a red
CI. To catch that *before* pushing, run the gate inside the **same container
image CI uses** (`python:3.12-slim-bookworm`, fresh installs):

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
on the closing commit. Tags are local until the user explicitly
authorises a push.

## Push policy

Inherits from the user's global `~/.claude/CLAUDE.md` § 6
(public repos: push freely; private: batch + ask). Detect repo
visibility once per session via
`gh repo view --json visibility -q .visibility` and cache;
the result is recorded in `.claude/workflow.md` § 1 status
header.

### Doc-only pushes skip the gate (user directive 2026-08-05)

A push that touches **only** documentation does not need
`./scripts/ci-local.sh` — neither run by hand first, nor via the
pre-push hook. Push it with `git push --no-verify`. The gate takes
~1m45s and no Python stage reads prose, so paying it for a ROADMAP
annotation or a CHANGELOG line is pure waiting.

**One exception, and it is easy to miss.** `tests/features/harness/`
(FIBR-0001 INV-1) reads **`docs/specs/FIBR-0001.md`** and compares its
stage table against `scripts/ci-local.sh`. So a "doc-only" edit to
*that one spec* can genuinely turn the suite red. Run the gate — or at
least `pytest tests/features/harness/` (well under a second) — when
the diff touches it.

Rule of thumb: doc-only **and** not `docs/specs/FIBR-0001.md` → skip
the gate. Anything else → gate as usual. A code change never skips,
however small.

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

`naming.md` is not amended yet on purpose. Editing any
`docs/standards/` file trips the rule-14 `/cold-eyes` gate on its own,
and back-migrating the 54 existing `FIBR-NNNN.md` specs means repointing
374 inbound citations — so both halves are tracked as **FIBR-0196**
rather than done in passing. This note exists so a session that reads
`naming.md` and not that bullet does not name the next spec wrongly.
