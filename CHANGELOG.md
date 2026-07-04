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

- ****Import transactions from a PDF bank statement — including password-locked ones.** (FIBR-0009)**
  Many banks only give you a PDF. finbreak now reads the transaction
  table straight off the page: pick a `.pdf` and it lifts the rows out,
  then hands you the same familiar column-mapping and preview screens as a
  CSV import (so a bank layout you map once is remembered for next time).
  If the statement is **password-protected**, finbreak asks for the
  password and unlocks it **entirely in memory — the unlocked file is
  never written to your disk** — and you can tick "remember this password
  for this account" (off by default) so it's stored, encrypted, inside
  your vault; a wrong password just asks again instead of giving up. If a
  statement holds more than one table (say a summary and the transactions),
  you're shown a small chooser to pick the right one. It flows through the
  exact same machinery as CSV and OFX, so re-importing a statement adds no
  duplicates and the money stays exact to the cent. Statements printed as
  free-flowing text (no ruled table) or scanned images aren't supported yet
  — finbreak tells you to try your bank's CSV or OFX export instead.

- **Import transactions from an OFX bank file.** OFX (Open Financial Exchange)
  is the standard format almost every bank offers as a download. Because it
  describes itself — the dates, amounts, descriptions, and the statement's date
  range are all built into the format — finbreak needs **no column-mapping step**
  for it: pick an `.ofx`/`.qfx` file and you go straight to the same **preview**
  (every row, the "N new · M duplicate · K error" tally, the statement dates
  filled in for you) as a CSV import, then Import. It flows through the exact
  same machinery as CSV, so re-importing a statement you already loaded adds **no
  duplicates**, an OFX row that matches one you typed by hand is recognised as
  the same, and a row it can't read is listed rather than dropped. A file that
  covers **more than one account** (say a bank account plus a credit card) shows
  a small chooser so you pick which one to import; a "quiet month" with a real
  date range but no transactions still records its coverage. Money stays exact
  whole-cent amounts throughout (never a lossy decimal), and an over-large or
  over-long file is refused up front. No change to your existing data — OFX
  reuses the same storage the CSV import added. (FIBR-0008)

- **Import transactions from a bank-statement CSV file.** Instead of typing
  every transaction by hand, point finbreak at a CSV your bank gives you and it
  reads the transactions in. Because every bank lays its CSV out differently,
  you tell finbreak once which columns are the date, the description, and the
  amount (or separate "money out" / "money in" columns) — it remembers that as
  a named layout and recognises the same bank's file automatically next time.
  Before anything is saved you see a **preview**: every row, a
  "N new · M duplicate · K error" tally, and the statement's date range (filled
  in for you). Re-importing a statement you already loaded — even an overlapping
  one — adds **no duplicates**, while genuinely identical repeats (two of the
  same coffee on the same day) are kept the first time. Rows it can't read (a
  bad date, a non-number amount) are listed, not silently dropped, and the good
  rows still import. Opening a vault from before this release upgrades it in one
  all-or-nothing step that adds the import bookkeeping, rolling back cleanly on
  a power-cut. (FIBR-0007)

- **Categories — sort your money into Income and Expenditure buckets.**
  finbreak now has a two-level category list: two fixed types — Income and
  Expenditure — each holding a set of ready-made categories (Salary, Sales,
  Bills & utilities, Groceries, Medical, and more; sixteen come built in). A new
  "Manage categories…" screen lets you add your own, rename them, move one to
  the other type, or delete the ones you don't use. The list is stored so a
  future "sub-category" level can be added later without rebuilding your data.
  (Actually tagging each transaction with a category comes in a later release —
  this release builds the list itself.) Opening a vault from before this release
  upgrades it in one all-or-nothing step that adds the category list, and a
  power-cut mid-upgrade rolls back cleanly to the old shape. (FIBR-0006)

- **Multiple accounts — keep each account's money separate.** Create as many
  accounts as you like, each tagged with a type (current, savings, credit card,
  personal loan, home loan, investment, or other); rename or retype them on a
  new "Manage accounts…" screen; and choose which account each transaction
  belongs to (shown as its own column in the table). Deleting is guarded so you
  can't lose data: an account that still holds transactions can't be removed
  (it asks you to clear them first), and you can never delete your last
  account. Opening a vault from before this release upgrades it in one
  all-or-nothing step — it creates a "Default" account and moves every existing
  transaction into it, and a power-cut mid-upgrade rolls back cleanly to the
  old shape rather than leaving a half-changed file. (FIBR-0005)

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

### Changed

- **Date pickers show unambiguous ISO YYYY/MM/DD, not the locale's M/D/YY.** (FIBR-0047)
  Dates now always read year/month/day (e.g. 2026/07/04) so there's no US-vs-rest-of-world confusion.

### Security

- **Opening a vault from a newer version fails safely (FIBR-0005).** If a
  future build upgrades your vault's format and you then open it with an older
  build, the app refuses cleanly with a clear "created by a newer version"
  message and wipes the derived key from memory — instead of leaving the key in
  memory and surfacing an opaque error.

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
