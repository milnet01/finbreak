# Changelog

All notable changes to finbreak are documented in this
file.

The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Sections use the standard categories — **Added** for new
features, **Changed** for changes in existing behavior,
**Deprecated** for soon-to-be-removed features, **Removed**
for now-removed features, **Fixed** for bug fixes, and
**Security** for security-relevant changes.

The `[Unreleased]` block is required at the top, always —
even if empty. The Roadmap dialog reads it for current-work
signaling per
[`docs/standards/roadmap-format.md § 3.6.2`](docs/standards/roadmap-format.md).

## [Unreleased]

### Added

- **The security spine — set a master password, keep encrypted transactions,
  lock it away.** First run sets a master password + base currency and creates
  an encrypted vault; you can add a transaction (kept as exact whole-cent
  amounts, never a lossy decimal) and see it in a table, then Lock to wipe the
  key and return to the unlock screen. A wrong password or a tampered file is
  refused cleanly. Amounts show in your base currency; the slow password-to-key
  work runs off the UI thread so the window never freezes; the vault
  auto-locks after 10 minutes idle. (FIBR-0004)

- Development quality + security gate: a single command,
  `scripts/ci-local.sh`, runs ruff (lint + format-check), bandit,
  pip-audit, gitleaks, and pytest, cheapest-first, failing on the first
  bad stage. `.github/workflows/ci.yml` runs the identical stages by
  invoking that same script (one source of truth), so local and CI runs
  cannot drift. Ships the `pyproject.toml` toolchain (exact-pinned dev
  group), the `.gitleaks.toml` scan config, and a placeholder `finbreak`
  package with a smoke test. (FIBR-0001)

- **Bundling smoke-test — proves the native stacks travel into a
  Python-free download.** A permanent `python -m finbreak --self-test`
  diagnostic loads all three native stacks (Qt via PySide6, the SQLCipher
  encrypted DB, and qpdf behind pikepdf) and prints a sentinel;
  `scripts/build-smoke.sh` freezes it into a PyInstaller onefile **and** an
  AppImage inside a `python:3.12-slim-bookworm` container (glibc floor
  ~2.36) and launches each in a Python-free `debian:13-slim` clean-room,
  proving ADR-0007's clean-machine exit criterion in miniature. Adds the
  first pinned runtime deps (`PySide6`, `sqlcipher3-binary`, `pikepdf`) and
  a `build` group (`pyinstaller`); the slow build is opt-in
  (`ci-local.sh --build`) with a dedicated weekly CI job, so the everyday
  gate stays fast. (FIBR-0003)

### Security

- **Vault encryption, key derivation, and in-memory key wiping (FIBR-0004).**
  The master password is stretched into a 256-bit key with **Argon2id** (pinned
  parameters), which unlocks a **SQLCipher (AES-256)** database — the on-disk
  file is unreadable and integrity-checked (a wrong key or a flipped byte is
  refused, not silently accepted). The plaintext parameters live in a non-secret
  sidecar written owner-only and created owner-only from the start (no
  world-readable window). The derived key lives only while unlocked and is wiped
  from memory on lock, idle auto-lock, and app exit. There is no password
  recovery in this slice (a forgotten password means the data is unrecoverable —
  stated on the first-run screen), and the app makes no network calls
  (enforced by a test). (FIBR-0004)

- **`.gitignore` blocks financial data and build output from the public repo.** (FIBR-0002)
  Extends the ignore set so a local vault (`*.db` / `*.sqlite` /
  `*.sqlite3` and its SQLite `-wal` / `-shm` / `-journal` sidecars) and
  all build/packaging output (PyInstaller `build/` / `dist/`,
  `*.egg-info/`, `*.dmg`, `*.AppImage`, `*.flatpak`, `.flatpak-builder/`,
  and tool caches) can never be staged; `gitleaks` remains the content
  backstop. Regression-locked by `tests/features/gitignore/`. (FIBR-0002)
