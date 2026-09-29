# finbreak — Discovery (Phase A)

> **Status:** Approved 2026-06-30.
> **Phase:** A — Discovery.
> **Output:** problem, users, success criteria, tech stack,
> out of scope, distribution.
> **Gate:** user explicitly approves this document before
> Phase B starts.

Captured from the brainstorming conversation of 2026-06-30.


## Problem

Personal finances are spread across many bank accounts and arrive as
statements that don't add up to a clear picture. People want to see **where
money actually goes** — broken into income (salary, sales…) and expenditure
(fast food/takeaways, bills, medical, lottery…) — without handing a
third-party app live access to their internet/mobile banking, which is a
privacy and security risk they're unwilling to take.

Existing options force a bad trade: aggregator apps (Plaid / Stitch / Mono)
require linking the live bank account; generic spreadsheets don't
auto-categorise, don't de-duplicate re-imported statements, and don't
recognise that money moved *between your own accounts* isn't spending. The
result is either an unacceptable security posture or a manual, error-prone
mess.

finbreak (Finances Break Down) solves this with a **private, offline desktop
app**: the user downloads their own statement files from their bank and feeds
them in; the app never touches the bank and nothing leaves the machine.


## Users

1. **A South African individual** who banks with Standard Bank and Absa, holds
   several account types (current, savings, personal loan, credit card, home
   loan, investment — among others; the full type list lives in the data
   model), and wants to understand their spending **without giving
   any app internet-banking access**.
2. **A friend, family member, or anyone worldwide** on any bank, who is given
   the app and needs to set up *their own* bank's statement layout and *their
   own* currency — so the app must not hard-code any single bank or country.
3. **A person preparing to share finances with an institution** — e.g. a loan
   or bond application — who needs a clean PDF summary (**optionally
   password-protected**) to hand to a bank or financial advisor.


## Success criteria

Each is demonstrable by doing, not just by reading code.

1. **Consolidated breakdown.** A user can import statements from *multiple
   accounts* (via CSV/OFX, PDF, or manual entry) and see a single
   income-vs-expenditure breakdown by category — per account or consolidated —
   for a chosen time period, with pie/donut charts and month-to-month trends.
2. **No duplicates on re-import.** Importing a statement that overlaps a
   previous import creates **zero** duplicate transactions; matches are
   detected and skipped/flagged.
3. **Transfers don't inflate the numbers.** Money moved between the user's own
   accounts (e.g. a credit-card payment from the current account) is detected,
   classified as a **Transfer**, and excluded from income/expenditure totals.
   The app *suggests* transfers and the user *confirms* them.
4. **Private by construction.** The data file is encrypted at rest; opening the
   app requires the master password; the app makes **no network connection**
   except one the user switches on: the opt-in, off-by-default update check
   ([`security-model.md`](security-model.md) INV-8), which sends nothing about
   the user's money. Different OS logins see only their own password-locked
   data. *(Reworded 2026-09-28, user-approved, FIBR-0368: it said "no network
   connection of any kind", which the update check FIBR-0054 added had made
   untrue.)*
5. **Shareable PDF, optionally locked.** A user can export a PDF report,
   choosing which sections to include (summary / charts / transactions) and
   which accounts, that can **optionally** be locked with a password set at
   export time (optional per user directive 2026-07-12 — see FIBR-0013; an
   unprotected export is a first-class supported outcome).
6. **Runs everywhere, fully self-contained.** The same codebase produces a
   working **Windows** executable, an **unsigned macOS** `.app` (in a `.dmg`),
   and a **Linux AppImage**, plus a **Flatpak published on Flathub** — each
   launching to the same dark-themed app. Every artifact **bundles the Python
   runtime and all dependencies**: the user downloads one file and runs it on a
   clean machine with **nothing pre-installed** (no "install Python 3 first").
   Each release will be verified on a clean machine with no Python before it ships.
7. **Works in the user's own currency.** A user who picks any currency at first
   run — not only the rand — sees every amount, total and report in that
   currency's symbol and decimal places, with no code change, and a statement
   in that currency imports with every amount correct to its smallest unit.
   *(Added 2026-09-28, user-approved, FIBR-0368: the Users section required it
   and no criterion measured it.)*
8. **Works with the user's own bank.** A statement from a bank finbreak has
   never seen imports with every row correct, using only the in-app column
   mapping, with no code change. *(Added 2026-09-28, user-approved, FIBR-0375:
   the Users section promises any bank's statement layout and no criterion
   measured it.)*

> **Locked-PDF handling:** when an imported statement PDF is itself
> password-protected, the app prompts for the PDF's open-password, decrypts it
> **in memory** (never writing the decrypted file to disk), and parses it. An
> opt-in "remember this password" stores it **encrypted in the database** (same
> SQLCipher file, locked by the master password) against that account — so
> re-imports are one click. Default is to prompt each time and store nothing.


## Tech stack

Claude recommends; user accepted on 2026-06-30. Domain-specific library rows
are added below the standard layers because parsing and crypto are central to
this project.

| Layer | Choice | Why | Runner-up |
|-------|--------|-----|-----------|
| Language | Python 3.12+ | Matches the user's existing apps; best ecosystem for CSV/OFX/PDF parsing and PDF generation | C++/Qt — heavier for the parsing-centric workload |
| GUI framework | PySide6 (LGPL) | Native, fully offline desktop; sleek dark theme via Qt stylesheets; LGPL keeps publicly-distributed binaries unencumbered under our MIT licence | PyQt6 (GPL — would force distributed binaries to GPL); a local Flask web app (weaker offline/security story) |
| Encrypted storage | SQLCipher (SQLite + AES-256) | Transparent whole-file encryption at rest, unlocked by a derived key | App-level field encryption — more error-prone, leaks metadata |
| Key derivation | Argon2id (`argon2-cffi`) | Modern memory-hard KDF stretching the master password into the DB key | PBKDF2-HMAC-SHA256 — older, weaker against GPUs |
| PDF rendering | Qt PDF engine (`QTextDocument` + `QPdfWriter`, via PySide6) | No extra native dependencies (Qt already shipped) → clean Windows/macOS/Linux bundling; themeable HTML-subset layouts | ReportLab — pure-Python, more control, more imperative. **WeasyPrint rejected**: native GTK/Pango/cairo deps break cross-platform packaging |
| PDF encryption / decryption | `pikepdf` (AES-256) | Battle-tested qpdf binding; password-protects exported reports **and** decrypts password-locked input statements in memory | PyPDF2 — weaker crypto track record |
| OFX import | `ofxparse` | OFX is a worldwide standard; this parses it generically | hand-rolled SGML/XML parsing |
| CSV import | stdlib `csv` + reusable per-bank column-mapping profiles | No dependency; mapping handles any bank's column order | pandas — heavyweight for this need |
| PDF statement import | `pdfplumber` | Strong text + table extraction from statement PDFs | camelot / tabula — pull in a Java dependency |
| Charts | QtCharts ([ADR-0008](decisions/0008-qtcharts-for-reporting.md)) | Need: dark-themeable, render on screen **and** into the PDF | matplotlib / pyqtgraph |
| Dev environment | pip + venv + `pyproject.toml` | Matches the user's other Python projects | Poetry |
| Windows package | PyInstaller → standalone `.exe` | One bundle, no Python install needed on the target machine | Briefcase / cx_Freeze |
| macOS package | PyInstaller → **unsigned** `.app` inside a `.dmg` | Free; one-time right-click → Open bypasses Gatekeeper. Signing/notarisation deferred until an Apple Developer account exists | Briefcase |
| Linux package | **AppImage** (appimagetool), **Flatpak on Flathub**, and native RPM/deb via the openSUSE Build Service (FIBR-0155) | AppImage = portable single file; Flatpak = distro storefronts via Flathub; OBS = distro package managers | — |
| Test runner | pytest (+ pytest-qt for GUI) | Matches Music_Production | unittest |
| Linter / formatter | ruff | Matches the user's other Python projects | flake8 + black |
| CI | GitHub Actions | Free for public repos; matches existing tooling | GitLab CI / Buildkite |
| License | MIT | Permissive; matches scaffold | Apache-2.0 |


## Out of scope

Considered and deliberately excluded from v1:

- **Live bank connections / Open Banking aggregators** (Plaid, Stitch, Mono) —
  the explicit non-goal; the whole point is that the app never touches the
  bank.
- **Multi-currency within one profile, with FX conversion** — v1 uses a single
  base currency per profile, chosen at first run. Cross-currency conversion is
  a later add-on.
- **Budgeting and savings-goal tracking.**
- **Bill reminders** — nothing notifies the user before a payment is due.
- *Forecasting and recurring-money detection were on this list. They shipped:
  the Recurring tab suggests repeating money for the user to confirm, and the
  Forecast tab projects the balance forward from what was confirmed. Removed
  from out-of-scope on 2026-09-28, user-approved (FIBR-0376).*
- **Mobile app, web app, or any cloud sync** — desktop-only, local-only by
  design.
- **Shared multi-user server** — separation comes from per-OS-user local data,
  not a central service.
- **3rd-level category depth in the UI** — the data model is built to support
  it (Type → Category → Sub-category), but v1's screens expose only two levels.
- **Code-signing / notarisation** (macOS *and* Windows) — v1 ships unsigned
  builds; signing is wired in later once developer certificates exist.


## Distribution

- **Distribution:** public GitHub — <https://github.com/milnet01/finbreak>.
- **Reason:** the user requested a public repo; it's a personal-finance tool
  intended to be shared with friends/family and anyone worldwide.

**Platform targets (one codebase):**

- **Windows** — standalone `.exe` (PyInstaller).
- **macOS** — unsigned `.app` in a `.dmg` (PyInstaller); right-click → Open the
  first time. Signing/notarisation deferred until an Apple Developer account
  exists.
- **Linux** — portable **AppImage**, a **Flatpak published on Flathub** to
  reach distro storefronts, and native RPM/deb packages built by the openSUSE
  Build Service (`packaging/obs/`, FIBR-0155).

**Release automation:** `scripts/release-linux.sh` builds and signs the
AppImage and publishes the GitHub Release; `scripts/release-windows.sh` then
builds the Windows `.exe` and attaches it to the same release. The Flatpak
re-pin is a manual step, and macOS has no release script yet (FIBR-0130). One
script covering every artifact is still planned (FIBR-0016).

**Local CI emulation:** `scripts/ci-local.sh` is the gate, and
`.github/workflows/ci.yml` runs that same script, so the gate list has one home
(`FIBR-0001`). Problems are caught **before** pushing to the public repo. The
build smoke-test (`FIBR-0003`) is opt-in (`--build`); CI runs it weekly in
`.github/workflows/build-smoke.yml`, not on every push.

**Licensing:** the project is **MIT**; PySide6 is **LGPL**, which permits
distributing our binaries under MIT without forcing a copyleft licence on the
app. (PyQt6's GPL was the reason it was not chosen — see the tech-stack table.)

Public-GitHub optionals activated (`CONTRIBUTING.md`, `.github/dependabot.yml`,
issue templates, PR template). Public repo → push freely (global rule § 6).

> **Privacy note:** the repository is public, but **no financial data is ever
> committed**. The app stores each user's data in their own OS-user data
> directory, encrypted at rest; the repo contains only source code and docs.


## Sign-off

- [x] Problem captured.
- [x] Users captured (3 personae).
- [x] Success criteria captured (measurable outcomes).
- [x] Tech stack chosen with one-sentence reasoning each.
- [x] Out-of-scope list captured.
- [x] Distribution chosen (public GitHub; optionals activated).
- [x] **User has approved this document.** Date: 2026-06-30.

Once approved, proceed to Phase B — `docs/design.md`.
