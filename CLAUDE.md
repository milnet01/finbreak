# finbreak — Project instructions for Claude Code

Scaffolded from the **Ants App-Build** template; follows the
[`app-workflow`](~/.claude/skills/app-workflow/SKILL.md)
skill.

## Where state lives

Read these in order on every session start:

1. **This file** — stable rules and conventions.
2. **`.claude/workflow.md`** — live status header (current
   phase, active item, step number, blockers, last-update
   timestamp). After reading, **summarise back to the user**
   before doing any work.
3. **`docs/standards/{coding,naming,dependencies,documentation,testing,commits}.md`**
   — the six shareable v1 standards.
4. **`docs/specs/<active-id>.md`** — the contract for the
   currently-active roadmap item.
5. **`docs/audit-allowlist.md`** — read **additionally** before
   invoking `/audit` or `/indie-review` so already-confirmed
   project-specific false positives aren't re-flagged. The
   allowlist is the closed-loop memory for this project — see
   the [app-workflow skill](~/.claude/skills/app-workflow/SKILL.md)
   "False-positive learning" section.

## Closing a phase

Run **`/close-phase`** once steps 1–4 of the per-phase loop
are done — see SKILL.md for the full description.

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
- **Tests / lint:** pytest (+ pytest-qt), ruff
- **Security gate:** bandit, pip-audit, gitleaks (see
  [`docs/security-model.md`](docs/security-model.md))
- **Packaging:** PyInstaller (Windows `.exe`, macOS `.app`/`.dmg`),
  AppImage + Flatpak/Flathub (Linux) (ADR-0007)
- **License:** MIT; local-only, no network.

## Build and test

The harness contract is [`docs/specs/FIBR-0001.md`](docs/specs/FIBR-0001.md).

**Requirements:** Python ≥ 3.12 and the `gitleaks` binary on `PATH` (a Go
binary, not a pip package — install from your distro or the
[gitleaks releases](https://github.com/gitleaks/gitleaks/releases)).

**One-time dev setup** — isolated env + the pinned dev toolchain (ruff,
bandit, pip-audit, pytest, pytest-qt) **and the runtime deps** (PySide6,
SQLCipher, pikepdf), which the FIBR-0003 self-test guard imports:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip      # PEP 735 --group needs pip >= 25.1
python -m pip install --group dev
python -m pip install .                  # runtime deps — the self-test test loads them
```

**Run the full gate** — the same stages CI runs (lint, format-check, bandit,
pip-audit, gitleaks, tests; FIBR-0001 INV-1/INV-2):

```bash
./scripts/ci-local.sh
```

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
`scripts/ci-setup.sh` (environment: system libs + gitleaks + deps) then
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

## Module map

`src` layout; the package is `finbreak`, found by pytest via
`pythonpath = ["src"]` (no editable install needed for the gate).

- `src/finbreak/` — the application package. `__init__.py` (`__version__`),
  plus `__main__.py` + `_selftest.py` — the `python -m finbreak --self-test`
  entry point that loads Qt + SQLCipher + qpdf (FIBR-0003). UI / services /
  repositories / crypto modules land from P02 (see
  [`docs/design.md`](docs/design.md) for the layered architecture).
- `tests/` — pytest suite. `tests/test_smoke.py` asserts the package imports;
  `tests/features/<name>/` (spec.md + test) and `tests/fixtures/<rule>/` arrive
  with the features they cover
  ([`docs/standards/testing.md`](docs/standards/testing.md)).
- `scripts/ci-local.sh` — the one-command quality + security gate (`--build`
  adds the FIBR-0003 bundling smoke-test).
- `scripts/ci-setup.sh` — the shared CI **environment** prep (system libs
  PySide6 needs + gitleaks + Python deps). Called by BOTH `ci.yml` and
  `ci-docker.sh` so the environment has a single definition.
- `scripts/ci-docker.sh` — reproduce the GitHub CI run exactly, locally, in the
  same `python:3.12-slim-bookworm` image (`ci-setup.sh` + `ci-local.sh`). Run
  before pushing to catch environment issues a configured desktop masks.
- `scripts/build-smoke.sh` (+ `_build-smoke-in-container.sh`) — freeze the stub
  in a `python:3.12-slim-bookworm` container (glibc ~2.36) and launch it in a
  Python-free `debian:13-slim` container (FIBR-0003).
- `.github/workflows/ci.yml` — CI mirror; runs INSIDE `python:3.12-slim-bookworm`
  and calls `ci-setup.sh` then `ci-local.sh` — the same image + scripts as
  `ci-docker.sh`, so local and CI cannot drift (single source of truth, INV-2).
- `.github/workflows/build-smoke.yml` — the dedicated, opt-in build job
  (`workflow_dispatch` + weekly), not run on every push.
- `pyproject.toml` — metadata, pinned runtime deps + `dev`/`build` groups,
  ruff / pytest / bandit config.

## Resumption flow — MANDATORY summarise-back

Per the app-workflow skill:

1. **Parallel batch:** read this file + `.claude/workflow.md`
   status header + active-item details (one tool-call batch).
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
