---
paths:
  - "src/**"
  - "tests/**"
---

# Module map

Part of this project's instructions, kept out of `CLAUDE.md` so it loads
only when needed. `CLAUDE.md` says when to read it.

`src` layout; the package is `finbreak`, found by pytest via
`pythonpath = ["src"]` (no editable install needed for the gate).

**`invariant_check` needs the PACKAGE-relative path here, not the
project-relative one — and answers `matched_count: 0` either way for some
modules.** The verb substring-matches the path you pass against spec bodies,
and this project's specs cite modules as `services/auth.py`, never
`src/finbreak/services/auth.py`. Measured 2026-08-24: the project-relative
form returned **0 matched specs over 64 scanned**, the package-relative form
returned **16**. Worse, a spec may name a module only by SYMBOL — FIBR-0019
writes ``vault_migration.resume`` and no path at all — so
`services/vault_migration.py` also returns 0 while § 13 governs every line of
it. **So a zero here is not "nothing governs this file"**: fall back to
`workspace_search` on the module's bare name across `docs/specs/`, which is
what finds the symbol-only citations.

- `src/finbreak/` — the application package. `__init__.py` (`__version__`),
  plus `__main__.py` + `_selftest.py` — the `python -m finbreak --self-test`
  entry point that loads Qt + SQLCipher + qpdf (FIBR-0003). UI / services /
  repositories / crypto modules land from P02 (see
  [`docs/design.md`](../../docs/design.md) for the layered architecture).
  - **The key envelope (FIBR-0019)** is four modules and one rule: the vault is
    encrypted by a random **data key**, and each credential wraps its own copy
    of it. `keywrap.py` is the AES-256-GCM slot primitive (Qt-free);
    `services/recovery_code.py` is Crockford base32 — generate, format,
    normalise, check-symbol, decode — and is pure; `services/vault_migration.py`
    runs § 13's S0..S6 conversion of a v1 vault plus its resume ladder;
    `ui/recovery_key.py` holds the one-time code display and the forced
    new-password step. The v2 sidecar reader/writer lives in `crypto.py` beside
    `load_and_validate_params`, which dispatches on `sidecar_version`.
    **What Argon2id is fed for the recovery route is the DECODED 17-byte
    payload, never the text** — Crockford maps `I`/`L` to `1` and `O` to `0`,
    so deriving from the text would refuse a code the user transcribed
    correctly. And `models.FORMAT_VERSION` stays `1`: it is the `.fbk` params
    record's version, and bumping it breaks every backup restore.
  - **Batch import (FIBR-0085)** spans three of those layers:
    `services/batch_import.py` holds every decision (the scan ladder, the
    stored-password ladder, the cumulative dedup counts, the caps) and is
    Qt-free so all of it is testable headless; `ui/import_batch.py` is the
    review-step table; `importers/sniff.py` is the Qt-free format detection
    lifted off the wizard so the service could call it. `ui/import_wizard.py`
    gained a fourth step and the scan/ask/run chain, and
    `ui/account_picker.py` gained a Create-an-account affordance.
  - **The Standard Bank import contract is stated in
    [`docs/specs/FIBR-0050.md`](../../docs/specs/FIBR-0050.md) INV-11 — amend it in the
    same commit that changes the behaviour.** It is the canonical "all-or-nothing,
    and here is every way a statement can be refused" clause. Why the
    same-commit rule is stated here at all:
    [`docs/history/claude-md.md`](../../docs/history/claude-md.md).
    The trap in the code: `_draft` decides
    degrade-vs-refuse on the **amount**, never on the rejection reason —
    `parse_transaction` checks description and date first, so a printed `0.00`
    line can be rejected for its *date* and must still degrade (FIBR-0255 §4.1).
- `tests/` — pytest suite. `tests/test_smoke.py` asserts the package imports;
  `tests/features/<name>/` (spec.md + test) and `tests/fixtures/<rule>/` arrive
  with the features they cover
  ([`docs/standards/testing.md`](../../docs/standards/testing.md)).
- `scripts/ci-local.sh` — the one-command quality + security gate (`--build`
  adds the FIBR-0003 bundling smoke-test).
- `scripts/ci-setup.sh` — the shared CI **environment** prep (system libs
  PySide6 needs + the pinned non-pip binaries — gitleaks, shellcheck,
  actionlint, zizmor — + Python deps). Called by BOTH `ci.yml` and
  `ci-docker.sh` so the environment has a single definition.
- `scripts/ci-docker.sh` — re-run CI's own image and CI's own two scripts
  locally (`python:3.12-slim-bookworm`, then `ci-setup.sh` + `ci-local.sh`). Run
  before pushing **when the diff could move the environment** — `gate.md`
  lists those triggers and says it is not required before every push. Not the
  whole workflow either — `release.md` § `cut-release` Phase 2b names what it misses.
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
  INV-2). The workflow around that gate is a different thing — `release.md` § `cut-release`
  Phase 2b names what a local run does not reach.
- `.github/workflows/build-smoke.yml` — the dedicated, opt-in build job
  (`workflow_dispatch` + weekly), not run on every push.
- `.github/workflows/windows-build.yml` — the on-demand Windows `.exe` freeze
  (unsigned; Authenticode signing is FIBR-0133, still blocked).
- `pyproject.toml` — metadata, pinned runtime deps + `dev`/`build` groups,
  ruff / pytest / bandit / mypy config.
