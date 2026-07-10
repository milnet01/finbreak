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

- **Auto-categorisation: user-editable rules file transactions into categories by themselves, with a manual per-transaction override that always wins, learning from corrections, and a clean delete-category cascade (FIBR-0010).**
  Rules run on import and on an explicit "Apply rules now". Correct an
  auto-filed transaction and finbreak offers to make a rule. A new Rules
  tab manages the rule list; the Home table gains a Category column and a
  right-click "Set category…". Deleting a category re-files its
  transactions and removes the rules that pointed at it, after a
  confirmation that names the blast radius. Encrypted-vault schema v6 → v7.

- **Change a logged statement's account — the Statements tab can now move a statement (and all its transactions) to the correct account, fixing an import mistake without deleting and re-importing (FIBR-0059).**
  Select a statement, click "Change account", pick the right account, and the
  statement plus every transaction it contains move there together — all-or-
  nothing. If the target account already has a statement for the same period, the
  move is refused with an explanation (rather than silently duplicating rows). This
  is also the tool for fixing anything mis-linked before the import-time fix
  (FIBR-0057) shipped.

- **A proper branded app icon (FIBR-0037).** (FIBR-0037)
  finbreak now has a real app icon — a colourful "spending by category" donut chart with a gold coin in the middle — instead of no icon. You'll see it on the window, in your taskbar, and (once installers are built) as the app's icon on Windows, macOS and Linux.

- **Settings screen — a Settings menu item whose first control is a user-configurable auto-lock timeout, plus core preferences.** (FIBR-0055)
  A new File → Settings… screen. Its first control lets you choose how long finbreak waits before it auto-locks when you step away (1, 5, 10, 15 or 30 minutes — it used to be a fixed 10). The choice takes effect immediately and is remembered (stored inside your encrypted vault). The screen also shows your vault's base currency. No database change.

- ****P07.6: tabbed main window + a Statements tab that lists your imports and lets you delete one with all its transactions.**** (FIBR-0052)
  The main window is now tabs — Home · Statements · Accounts ·
  Categories — with a Home button on the toolbar, and it remembers its
  size, position and last tab between runs (plus Center-window and
  Reset-layout actions). The new Statements tab shows every statement
  you've imported with an exact transaction count, and lets you delete a
  statement and all of its transactions in one step (with a confirmation;
  your manually-added transactions are left untouched). To count and
  delete safely, finbreak now tags each imported transaction with the
  statement it came from — a small automatic database upgrade, including a
  one-time tidy-up for statements imported before this version.

- **P07.5: app-shell UX redesign — real app window (QMainWindow) with menubar / icon toolbar / status bar; first-run & unlock as popups.** (FIBR-0051)
  Turn the bare password-box-then-form startup into a proper app window — menus, a toolbar of shortcuts, a status bar, and a first-run popup wizard — so it looks and feels like a real desktop app.

- ****Import your Standard Bank statements directly — cheque, savings, home loan, personal loan, credit card and money-market.** (FIBR-0050)**
  Standard Bank's real statements don't survive the generic PDF
  table-reader — a cheque statement collapses into a single cell, and
  the credit card's two-columns-per-page layout is unreadable. finbreak
  now recognises a Standard Bank statement and reads the printed lines
  the way you do, so all six of your account types import cleanly and
  skip straight to the preview (no column-mapping needed, like OFX).
  Money out shows negative, money in positive; it copes with both the
  1,427.41 and the 239.206,04 number styles, works out the year from
  the statement period, and every statement is cross-checked against its
  own running balance and printed closing figure — if the numbers don't
  add up it declines the whole import and points you to your bank's CSV
  or OFX export rather than importing something wrong. Locked statements
  are unlocked in memory only (never written to disk), and nothing about
  your statement leaves your computer.

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

- **An oversized Standard Bank PDF is now rejected before the heavy parsing runs, not after, so a deliberately huge file can't burn work before being turned away.** (FIBR-0078)

- **Consolidated the Standard Bank statement signed-balance parsing (repeated 7 times across the account families) into one helper.** (FIBR-0069)

- **Deduplicated the drop-down preselect logic shared across the account, category, and type pickers into one helper.** (FIBR-0068)

- **Consolidated the 13 hand-copied database transaction blocks (BEGIN/COMMIT/ROLLBACK) into one shared `owned_transaction` helper, so a future database write can't accidentally use a subtly-wrong rollback path.** (FIBR-0066)

- **Typed the rules Move up/down handler with a `Literal` (dropping a type-ignore) and corrected the FIBR-0007 INV-7 spec narrative to match the FIBR-0052 period-first insert order.** (FIBR-0081)

- **Settings reads (base currency, minor-unit exponent) now flow through the shared `SettingsRepository` seam instead of hand-rolled SQL, so a mistyped key can't silently read the wrong value.** (FIBR-0080)

- **The quality gate now runs `mypy` as a stage (both `ci-local.sh` and CI), so type errors fail the build instead of relying on ad-hoc manual runs. (FIBR-0061)**
  Also fixed the 4 pre-existing type errors the newly-gated `mypy src
  tests` surfaced in the test tree (None-guards on three `findChild`
  helpers in the settings suite; an aligned `QThread.start` override
  signature in the app-shell suite). Test-only typing, no runtime change.

- **Silenced ~107 noisy third-party deprecation warnings from the OFX importer and pinned its parser dependency to keep OFX import working on future releases (FIBR-0058).**
  The OFX-file importer relies on ofxparse, which uses an old-style call into
  BeautifulSoup that prints a deprecation warning many times per run. The
  warnings are now suppressed (only that specific message), and the underlying
  library is version-capped so a future BeautifulSoup release that removes the
  old call can't silently break OFX import.

- **Date pickers show unambiguous ISO YYYY/MM/DD, not the locale's M/D/YY.** (FIBR-0047)
  Dates now always read year/month/day (e.g. 2026/07/04) so there's no US-vs-rest-of-world confusion.

### Fixed

- **Importing a corrupt or unreadable PDF now shows a clear "couldn't read this PDF — try your bank's CSV or OFX export" message instead of a raw internal error.** (FIBR-0064)

- **Adding a categorisation rule when no categories exist now shows a clear "create a category first" message instead of opening a dialog that dead-ends on a confusing error.** (FIBR-0079)

- **A second app instance or a slow backup holding a brief database lock no longer crashes with a raw error — connections now wait up to 5 seconds for the lock to clear.** (FIBR-0076)

- **Auto-locking while a pop-up is open no longer crashes the app (FIBR-0065).**
  If the app auto-locked itself while a small pop-up was open (pick a
  category, add/edit a rule, change a statement's account, or type a
  PDF password), it could crash instead of locking cleanly. Those
  pop-ups are now non-blocking, so the app always returns to the
  locked screen safely.

- **More import and account-management crash-safety (loop-2 review fold)**
  A Standard Bank statement with a non-English or garbled month name no longer crashes on import; deleting an account that has a quiet-month/all-duplicate imported statement (a period with no transactions) is now blocked with a clear message instead of crashing; and the Settings and Manual-entry dialogs (plus account/category add/edit) no longer error if the app auto-locks while they're open.

- **Categorization and account-management correctness/UX fixes**
  Manual category picks are validated to a leaf category at the service boundary (not just the UI); the rule reorder (Move up/down) is now one atomic transaction; deleting an account now asks for confirmation like the other destructive actions; and the unlock screen gives a malformed KDF sidecar its own message instead of 'check your password'.

- **Import now fails gracefully on malformed/unsupported statement files instead of crashing**
  An OFX investment/brokerage statement, a PDF pdfplumber can't parse, a missing/permission-denied file, and an over-large CSV all now surface a friendly message rather than an unhandled crash. The CSV path gained the same size cap the OFX/PDF paths already had, and a column mapping can no longer assign two roles to one column.

- **The window now remembers its size, and Window → Center window works on Linux Wayland (KDE), not only X11 (FIBR-0060).**
  On modern Linux desktops (Wayland) the system controls window placement, so
  the previous X11-only code silently did nothing: the window size was forgotten
  between runs and Center window had no effect. finbreak now restores the saved
  size on Wayland and centers via KDE's KWin on demand (X11, Windows and macOS
  are unchanged). On a non-KDE Wayland desktop, Center window is greyed out with
  a note that the desktop positions windows itself.

- **Import wizard: the destination account is now shown and correctable on the preview step, so a statement can no longer be silently imported into the wrong account (FIBR-0057).**
  Previously the target account was fixed the moment you chose the file, with
  no way to see or change it before the final Import — so a statement could
  land on the default account (e.g. "Current") instead of the one you meant.
  You can now confirm or change the account on the preview screen; a remembered
  locked-PDF password follows the corrected account.

### Security

- **Vault connections now explicitly pin per-page HMAC integrity ON (defense-in-depth for tamper detection) instead of relying on the encryption library's default.** (FIBR-0077)

- **Bounded file read defeats an endless-source import + complete vault-create cleanup**
  The import size cap is now enforced by a bounded read, so a symlink to an endless source (e.g. /dev/zero) or a file that grows after the size check can't be read unbounded into memory. Vault creation now closes and resets on any failure across the whole build (not just the final steps), and the app-data directory is created owner-only from the outset.

- **Hardened crypto/vault storage after a full-codebase review**
  Vault.create() no longer leaks an open, unlocked SQLCipher connection if a migration or sidecar write fails (it now mirrors open()'s close-and-reset); the app-data directory is created owner-only (0o700), not just the vault/sidecar files; the KDF sidecar's temp write refuses to follow a symlink (O_NOFOLLOW); and a first-run attempted over an existing vault now wipes the derived key on every exit path.

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
