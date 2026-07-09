<!-- ants-roadmap-format: 1 -->
# finbreak — Roadmap

> **Current version:** 0.0.0 (scaffolded 2026-06-30). See
> [CHANGELOG.md](CHANGELOG.md) for what's shipped; this file
> covers what's **planned**.
>
> **Format:** v1 — see
> [docs/standards/roadmap-format.md](docs/standards/roadmap-format.md).
> Every actionable bullet carries a stable
> `FIBR-NNNN` ID alongside its phase ID
> (`P##`, `FP##`, `DS##`, `DOC##`, `R##`); the phase ID
> categorises blocks while the stable ID identifies individual
> bullets within them. ID is identity, position is priority,
> items are tackled top-to-bottom. `Dependencies:` lines list
> **direct** predecessors only; transitive prerequisites are
> implied by walking the chain.
>
> **Build order rationale:** the layers are built bottom-up so
> each phase rests on a tested one below it. The encrypted
> **security spine** (key derivation → vault → unlock) is the
> *vertical slice* (P02), built first and on purpose — it is the
> load-bearing concern (personal financial data), so it is
> proven end-to-end before any feature sits on top of it. Each
> phase is then a thin, demonstrable increment.

**Legend** (per `docs/standards/roadmap-format.md § 3.3`)

- ✅ Done (shipped)
- 🚧 In progress (being tackled now)
- 📋 Planned (next up for this phase)
- 💭 Considered (research phase; scope or feasibility uncertain)

**Themes** (per `docs/standards/roadmap-format.md § 3.4`)

- 🎨 Features · ⚡ Performance · 🔌 Plugins · 🖥 Platform
- 🔒 Security · 🧰 Dev experience · 📚 Documentation
- 📦 Packaging · 🐛 Bug fixes · 🔍 Findings fold-in
- 🧹 Cleanup / debt

> **Security is a standing concern, not a phase.** Every
> `implement`-Kind item below must satisfy
> [docs/security-model.md](docs/security-model.md); the security
> static-analysis gate wired up in P01 (bandit + pip-audit +
> gitleaks) runs on every phase's audit and every push.

---

## P01 — Bootstrap (target: next)

**Theme:** wire up the build, lint, format, test, **security
scan**, and CI plumbing chosen in Phase A. Zero user-facing
features. Forces the audit + security harness to be
known-working before any business code lands, and de-risks the
scariest unknown (native-library bundling) up front.

### 🧰 Dev experience

- ✅ [FIBR-0001] **P01: project skeleton + lint + format
  + test + security-scan harness.** `pyproject.toml` (Python
  3.12+), `pip`+`venv` dev env, `ruff check` and `ruff format
  --check` clean on placeholder source, `pytest` exits 0 on an
  empty suite, **`bandit`, `pip-audit`, and `gitleaks` exit 0**.
  `.github/workflows/ci.yml` runs the same gates, and
  `scripts/ci-local.sh` mirrors them one-for-one (single source
  of truth for the gate list) so issues are caught before
  pushing. Dependencies: none. Lanes: build, ci, tests,
  security. Kind: chore. Source: planned.
  Resolved (2026-07-01): closed by /close-phase. Local gate exits 0; CI green in 23s; INV-1..INV-6 all demonstrated (INV-5 secret-injection demo flipped gitleaks + bandit red, then green on removal). /audit + /indie-review both returned zero actionable findings on the same pass. Impl commit 6b6ac64; tag FIBR-0001-complete.

- ✅ [FIBR-0002] **P01: `.gitignore` + secret-leak
  guard.** Standard Python ignore set (build artefacts,
  `.venv`, `__pycache__`, dep caches, IDE/OS files) plus
  explicit ignores for any local vault/`*.db`/`*.dmg`/AppImage
  build output, so **no financial data or build secret can ever
  be staged**. `gitleaks` (from FIBR-0001) is the backstop.
  Dependencies: FIBR-0001. Lanes: build, security. Kind: chore.
  Source: planned.
  Resolved 2026-07-01: .gitignore extended to block financial data (*.db/*.sqlite/*.sqlite3 + SQLite -wal/-shm/-journal sidecars) and build/packaging/tooling output; regression-locked by tests/features/gitignore/ (INV-1..INV-3 via git check-ignore --no-index). Spec cold-eyes-clean (4 loops); /audit + /indie-review zero actionable on the close pass (one indie-review LOW — global-git-excludes coupling — fixed inline). Full ci-local.sh gate green. Tag FIBR-0002-complete.

### 📦 Packaging

- ✅ [FIBR-0003] **P01: bundling smoke-test (de-risk
  native libs early).** Freeze the trivial placeholder app into
  a one-file **AppImage** *and* a PyInstaller bundle, then launch
  each on a clean target with **no Python installed**, confirming
  the CPython runtime + a stub load of all three native stacks —
  SQLCipher, Qt, and qpdf/`pikepdf` (scope broadened to the third
  stack per the FIBR-0003 spec, 2026-07-01). This surfaces
  the native-lib collection risk named in ADR-0007 *now*, not
  after ten phases are built on top. Full multi-platform
  packaging + publish pipeline is deferred to P13. Dependencies:
  FIBR-0001. Lanes: build, ci. Kind: chore. Source: planned.
  Resolved 2026-07-01: closed by /close-phase. `--self-test` loads all three native stacks; `build-smoke.sh` freezes a PyInstaller onefile + AppImage in a `python:3.12-slim-bookworm` container (glibc floor ~2.36; wheels' own floor 2.34) and both print `FINBREAK_SELFTEST_OK` in the Python-free `debian:13-slim` clean-room — ADR-0007's clean-machine criterion proven at P01. The de-risk empirically caught 5 real portability traps (host-glibc mismatch, static manylinux Python, missing Qt system libs, missing harfbuzz, missing libGL). Toolchain pinned (INV-4); opt-in build stage + weekly CI job keep the everyday gate fast. Impl commit 49e87b6; /audit + /indie-review zero actionable on the close pass (3 doc/comment drifts fixed inline). Tag FIBR-0003-complete.

---

## P02 — Vertical slice: the security spine (target: after P01)

**Theme:** the smallest end-to-end feature that touches every
layer — and deliberately the **encrypted-storage spine**, since
security is the load-bearing concern. Proves UI → service →
repository → encrypted vault → output → test before any feature
lands on top.

### 🔒 Security

- ✅ [FIBR-0004] **P02: master password → encrypted vault
  → one manual transaction → table → lock.** First-run sets the
  master password + base currency; `CryptoService` derives the
  key with **Argon2id** (parameters pinned in security-model.md
  INV-2) and
  opens the **SQLCipher** (AES-256) vault; `AuthService`
  unlocks/locks and wipes the key from memory on lock; the user
  manually enters one transaction (through a repository, in a
  single DB transaction) and sees it in a table; locking returns
  to the unlock screen and the on-disk file is unreadable
  without the password. Verifies the whole security model
  (ADR-0003 + docs/security-model.md) concretely. Dependencies:
  FIBR-0001. (FIBR-0002 and FIBR-0003 also complete P01 first by
  phase-ordering, but are not direct code prerequisites of the
  vault.) Lanes: ui, services, repo, security, tests. Kind:
  implement. Source: planned.
  Shipped 2026-07-02. Security spine implemented TDD-first; audit (ruff/bandit/gitleaks/semgrep/mypy) clean and three cold 4-lane indie-review rounds converged (all findings fixed inline). Gate green 74 passed/1 skipped. Live language switching (retranslateUi) deferred to FIBR-0017 per user decision (spec deliverable shipped: tr() strings + RTL + QLocale amounts).

---

## P03 — Accounts

### 🎨 Features

- ✅ [FIBR-0005] **P03: multiple accounts per profile.**
  Account model + CRUD + accounts-manager UI; each account
  tagged with a type (current, savings, credit card, personal
  loan, home loan, investment, other). Transactions belong to an
  account — this must exist before any import. Dependencies:
  FIBR-0004. Lanes: ui, services, repo, tests. Kind: implement.
  Source: planned.
  Resolved (2026-07-02): shipped P03. Account model + CRUD, AccountService (validation + delete guard), AccountsWidget (add/edit/delete), the account picker + Account column + id→name join, and the first forward-only schema-migration runner (v1→v2: seed Default, backfill, atomic BEGIN…COMMIT/ROLLBACK). Migration transaction mechanism verified empirically vs sqlcipher3 0.6.0. Closed via 2 audit + indie-review rounds (all findings fixed inline — key-wipe on newer-vault open, wired the edit form, strengthened the INV-4 rollback test to a true atomicity test); gate green 100 passed/1 skipped, mypy 0, audit 0.

---

## P04 — Category tree

### 🎨 Features

- ✅ [FIBR-0006] **P04: Type → Category tree (3rd level
  ready).** Self-referential `categories` table (`parent_id`),
  seeded Income/Expenditure types with sensible default
  categories (salary, sales / fast food, bills, medical,
  lottery…), and a category-management UI exposing two levels.
  Data model supports a future Sub-category level without
  migration. Dependencies: FIBR-0004, FIBR-0005. Lanes: services, repo, ui,
  tests. Kind: implement. Source: planned.
  Resolved (2026-07-02): shipped the categories aggregate (self-referential table + 2 seeded Type roots + 16 defaults), the QTreeWidget manager, and the v2→v3 migration. Spec cold-eyes-converged (7 loops); TDD; /audit + /indie-review 0 actionable on the closing pass. Gate green (122 passed/1 skipped, mypy 0). Transaction→category link deferred to P08 (FIBR-0010) by design. Journal: docs/journal/FIBR-0006.md. Tag FIBR-0006-complete.

---

## P05 — CSV import + mapping profiles

### 🎨 Features

- ✅ [FIBR-0007] **P05: CSV import with per-bank mapping
  profiles + dedup + import wizard.** `ImportService`
  orchestration + `CsvImporter` + saved per-bank column-mapping
  profiles (ADR-0005); de-duplication so re-importing an
  overlapping statement adds **zero** duplicates (success
  criterion 2); import wizard with a preview that shows per-row
  parse errors *before* anything is written. The first real
  import path; establishes the pipeline P06/P07 reuse.
  Dependencies: FIBR-0005, FIBR-0006. Lanes: services, importers, ui,
  repo, tests. Kind: implement. Source: planned.
  Design-ahead (user-request-2026-07-02): capture each imported
  statement's coverage period (start/end date) per account as
  first-class data AT IMPORT TIME — the reliable input for statement-gap
  detection (FIBR-0038). Bank PDFs print the period; for CSV (no period
  metadata) confirm it in the wizard. Cheap to add now, expensive to
  retrofit (would need re-import to learn periods). Establish the
  data-model hook here (the first importer) so OFX (FIBR-0008) and PDF
  (FIBR-0009) populate it too.
  Resolved (2026-07-03): shipped via /close-phase. CsvImporter + ImportService (exact-signature profiles, multiset-delta dedup, atomic write + coverage-period), v3->v4 migration (import_profiles + statement_periods), non-modal wizard. 43 tests (INV-1..11); gate green 165 passed/1 skipped, mypy 0; audit 0 + indie-review 0 CRIT/HIGH/MED (one LOW fixed inline: preview renders decimals not minor units). Tag FIBR-0007-complete.

---

## P06 — OFX import

### 🎨 Features

- ✅ [FIBR-0008] **P06: OFX import.** `OfxImporter` via
  `ofxparse`, feeding the same `ImportService` pipeline (dedup,
  categorisation, transfer detection) built in P05. OFX is a
  worldwide standard needing no mapping profile. Dependencies:
  FIBR-0007. Lanes: importers, services, tests. Kind: implement.
  Source: planned.
  Resolved (2026-07-04): P06 OFX import shipped. Pure OfxImporter -> the same ParseResult/ImportService pipeline as CSV (D2 _preview_from_result seam); embedded DTSTART/DTEND period (D4); payee-else-memo (D5); all-or-nothing-per-statement error model (D15); resource caps (D13); wizard OFX branch skips mapping + a multi-account chooser (D8/D10); no schema change (D9). Spec cold-eyes-converged (8 loops). Gate green 199 passed / 1 skipped, mypy 0; /audit 0, /indie-review fixed inline (deferred the tz-DTPOSTED day-shift -> FIBR-0042). FIBR-0003 build smoke re-run green (all five native stacks travel, incl. ofxparse/lxml; fixed a latent argon2 dep-drift in the build script en route). Tag FIBR-0008-complete.

---

## P07 — PDF statement import (incl. locked PDFs)

### 🎨 Features · 🔒 Security

- ✅ [FIBR-0009] **P07: PDF statement import with
  in-memory decrypt.** `PdfImporter` (`pdfplumber` table
  extraction) on the P05 pipeline; password-protected statements
  are decrypted **in memory only** (`pikepdf`, never written
  decrypted to disk); opt-in "remember this password" stores it
  **encrypted in the vault** against the account (default:
  prompt each time, store nothing). A wrong PDF password
  re-prompts rather than aborting the import. Dependencies: FIBR-0007.
  Lanes: importers, services, security, ui, tests. Kind:
  implement. Source: planned.
  Resolved (2026-07-04): PdfImporter (extract-then-CSV-adapter) + in-memory pikepdf decrypt + opt-in remembered password (v5 column) + wizard PDF branch. TDD; gate green 240 passed/1 skipped, mypy 0; FIBR-0003 build smoke PASS (native PDF tree travels). /close-phase: /audit 0, /indie-review 3 lanes (2 clean, 1 LOW coverage gap fixed inline). Free-text/OCR PDFs deferred (§ Out of scope). See docs/journal/FIBR-0009.md.

---

## P07.5 — App shell & first-run wizard (UX redesign)

### 🎨 Features · 🖥️ UX

---

- 📋 [FIBR-0051] **P07.5: app-shell UX redesign — real app window (QMainWindow) with menubar / icon toolbar / status bar; first-run & unlock as popups.**
  Replace the full-screen QStackedWidget swap model with a QMainWindow
  shell: menubar (File / View / Help / Donate), an icon toolbar
  (Manual entry / Import / Accounts / Categories / Lock, icon-above-
  label), a central swappable content stack, and a status bar that
  reports current activity (Ready / Importing… / Added transaction /
  Vault locked) plus a persistent transaction count. First-run and
  unlock become popup dialogs shown OVER the window (chrome greyed,
  content shows a Welcome / 🔒 Locked placeholder); idle auto-lock
  returns to the locked-shell state. Manual entry becomes a popup
  Add-Transaction dialog. Home = getting-started panel when empty,
  transaction table once populated (the P10 dashboard later replaces
  Home's body). Donate menu opens the .github/FUNDING.yml links
  (GitHub Sponsors / Patreon / PayBru) via QDesktopServices — a
  user-initiated hand-off to the OS browser; the app itself still
  makes no network calls (local-only holds). Reuses the existing
  accounts / categories / import screens as content views. Preserves
  FIBR-0004 security invariants: key wiped on quit, auto-lock fires,
  NO transaction data shown while locked, corrupt/incomplete-install
  guard at startup. Build order: this ships FIRST, then P08 rules +
  category link, P09 transfer detection, P10 dashboard drop into the
  ready-made content area. Out of scope (own phases): dashboard
  charts (FIBR-0012), rules screen (FIBR-0010), transfer prompts
  (FIBR-0011), branded app icon (FIBR-0037).
  Dependencies: FIBR-0004, FIBR-0005, FIBR-0006, FIBR-0007, FIBR-0008, FIBR-0009.
  **Layman:** Turn the bare password-box-then-form startup into a proper app window — menus, a toolbar of shortcuts, a status bar, and a first-run popup wizard — so it looks and feels like a real desktop app.
  Kind: implement.
  Lanes: ui, app, tests.
  Source: user-request-2026-07-05.

## P08 — Auto-categorisation rules

### 🎨 Features

- 📋 [FIBR-0010] **P08: rules engine + manual override.**
  `CategorizationService` applies a user-editable rule set to
  auto-assign categories; a manual override is the
  highest-priority signal and is never clobbered by re-import or
  a later rule. Rules-manager UI to view/add/edit. Dependencies:
  FIBR-0006, FIBR-0007. Lanes: services, ui, repo, tests. Kind: implement.
  Source: planned.

---

## P09 — Transfer detection

### 🎨 Features

- 📋 [FIBR-0011] **P09: transfer detection
  (suggest-then-confirm).** `TransferDetectionService` matches a
  debit in one account against a credit in another (same amount,
  short date window) and **proposes** the pair; only
  user-confirmed pairs are linked as transfers and excluded from
  income/expenditure totals (success criterion 3, ADR-0006).
  Rejected pairs are remembered so they don't re-surface. Never
  auto-hides a real expense. Dependencies: FIBR-0005, FIBR-0007. Lanes:
  services, ui, repo, tests. Kind: implement. Source: planned.

---

## P10 — Reporting + dashboard

### 🎨 Features

- 📋 [FIBR-0012] **P10: dashboard — summary, pie/donut,
  trends, filterable table.** `ReportingService` aggregates by
  category / account / period; the dashboard shows the
  income-vs-expenditure summary, a category pie/donut, and
  month-to-month trends, per account or consolidated; the
  transaction table gains full search + filters (success
  criterion 1). **Charts library is chosen at spec time**
  (QtCharts vs matplotlib vs pyqtgraph — must be dark-themeable
  *and* render into the PDF) and recorded as an ADR. Dependencies:
  FIBR-0008, FIBR-0009, FIBR-0010, FIBR-0011 (OFX, PDF, rule-based
  categorisation, and **transfer detection** — so the consolidated
  income/expenditure totals correctly exclude transfers, SC3; CSV via
  FIBR-0007 is pulled in transitively, so all of CSV/OFX/PDF are
  consolidated — SC1 names all three). Lanes: services, ui, tests. Kind: implement.
  Source: planned.

---

## P11 — Password-protected PDF export

### 🎨 Features · 🔒 Security

- 📋 [FIBR-0013] **P11: locked PDF export with section
  selection.** `PdfExportService` renders chosen sections
  (summary / charts / transactions) for a chosen period via the
  Qt PDF engine, then encrypts with a password set at export
  time (`pikepdf`, AES-256). Export dialog ticks sections + picks
  period + sets password (success criterion 5). Dependencies:
  FIBR-0012. Lanes: services, ui, security, tests. Kind: implement.
  Source: planned.

---

## P12 — Settings, auto-lock, backup, theme polish

### 🔒 Security · 🎨 Features

- 📋 [FIBR-0014] **P12: settings, inactivity auto-lock,
  encrypted backup.** Settings screen (base currency display,
  auto-lock timeout, manage stored PDF passwords, theme);
  inactivity **auto-lock** drops the key and returns to unlock;
  **encrypted backup export/import** (the only mitigation for a
  forgotten master password, per ADR-0003); dark-theme polish
  pass. Dependencies: FIBR-0004. Lanes: ui, services, security, tests.
  Kind: implement. Source: planned.

---

- 📋 [FIBR-0017] **P12: multi-language UI (i18n) — 6 bundled locales incl. RTL + language switcher.**
  Qt translation pipeline: every user-facing string is wrapped in `tr()` from the first UI onward (P02), `lupdate` extracts them to `.ts` catalogs, translations are compiled to `.qm` and loaded via `QTranslator` at startup and on live switch. Ships **6 locales**: English (base), Spanish, Simplified Chinese, Hindi, French, and **Arabic** (right-to-left). A language picker in the FIBR-0014 Settings screen switches locale. Numbers, currency, and dates render through `QLocale` (matters for a finance app — ties into the base-currency display), not hardcoded formats. The UI is built **RTL-ready** (layout mirroring) from P02 per design.md "Internationalization (i18n) & localisation", so Arabic is translate-and-ship; further RTL scripts (Hebrew, Urdu) are then a translation-only follow-up. NOTE: this stays cheap only if the string-externalization and RTL-safe-layout conventions are followed from P02 — retrofitting hardcoded English (and left-to-right-only layouts) across the whole feature stack is far more expensive. Dependencies: FIBR-0014 (settings screen hosts the switcher; transitively pulls the feature-complete UI so all strings exist to translate).
  **Layman:** Lets people use finbreak in their own language — ships in 6 languages to start (including Arabic, which reads right-to-left), with more addable later.
  Kind: implement.
  Lanes: ui, i18n, services, tests.
  Source: user-request-2026-07-01.
  Deferred from FIBR-0004 (P02) per user decision 2026-07-02: the three P02 screens (first_run, unlock, main_window) build their strings once in __init__ and do NOT implement live language switching (changeEvent → retranslateUi). coding.md §5.2 asks for this "from P02"; the FIBR-0004 spec deliverable required only tr() strings + RTL layouts + QLocale amounts (all shipped), and there are no translations to switch yet. When this phase lands, add changeEvent/retranslateUi to those three screens (and every screen built between P02 and here) so the language switcher takes effect without a relaunch.

## P13 — Packaging & release

### 📦 Packaging

- 📋 [FIBR-0015] **P13: self-contained multi-platform
  builds.** PyInstaller → Windows `.exe` and unsigned macOS
  `.app` in a `.dmg`; **AppImage** (built on an old base image
  for glibc compatibility); **Flatpak** manifest for Flathub.
  Each artifact bundles the CPython runtime and **all** native
  deps (SQLCipher, the needed Qt plugins, qpdf); the **exit
  criterion** is a launch on a clean VM/container with **no
  Python installed** (ADR-0007). Builds on the P01 smoke-test.
  Dependencies: FIBR-0013, FIBR-0014, FIBR-0003 (direct
  predecessors). Walking the dependency edges, FIBR-0013 and
  FIBR-0014 transitively pull in the entire P02–P12 feature stack
  (FIBR-0004 through FIBR-0012), so P13 cannot start until the app
  is feature-complete. Lanes: build, ci, packaging.
  Kind: chore. Source: planned.

- 📋 [FIBR-0016] **P13: `scripts/publish-release.sh` +
  release automation.** One committed script builds every
  artifact above, publishes the GitHub Release, and drives the
  Flathub submission/update — consuming the Flathub manifest
  produced by FIBR-0015. It is itself a specced item (its own
  `docs/specs/`, cold-eyes-reviewed) — a publish script can't
  predate the thing it publishes. Dependencies: FIBR-0015. Lanes:
  build, ci, packaging. Kind: chore. Source: planned.

- 📋 [FIBR-0037] **P13: a proper branded app icon (not a flat
  glyph).** Design a polished, richly-shaded application icon —
  the working concept is **money + an upward chart** (e.g. a
  banknote or coins fronting a rising line/bar graph), on a
  **transparent** background, reading clearly from a taskbar 16px
  up to a store 1024px. Ship the full asset set every artifact
  needs: master (≥1024px PNG/SVG source), multi-size `.ico`
  (Windows), `.icns` (macOS), the freedesktop hicolor PNG set +
  `.desktop` reference (Linux/AppImage), and the Flathub icon.
  **Licensing is a hard gate, not a nicety:** because the app
  ships on Flathub / GitHub Releases under MIT, every source
  element must be **original or CC0/public-domain** — no scraped
  copyrighted or attribution-encumbered art, even when combining
  pieces (record provenance + license of each source in
  `docs/` alongside the asset). Until this lands, the FIBR-0003
  smoke-test AppImage and dev builds use a throwaway placeholder
  icon. Dependencies: none (asset work); **blocks FIBR-0015**
  (packaging embeds it) and should harmonise with the FIBR-0023
  theme accent colour. Lanes: design, packaging. Kind: ux.
  Source: user-request-2026-07-01.

---

- 📋 [FIBR-0044] **Broaden Linux store reach: Snap Store + AUR + native distro packages.**
  Flathub (FIBR-0015) already surfaces the app in GNOME Software + KDE Discover across most distros, so this item adds the remaining self-publishable Linux channels: (a) Snap Store — a snapcraft.yaml (Ubuntu App Centre's default backend); (b) AUR — a PKGBUILD pointing at the GitHub release/AppImage (community-maintained, low overhead); (c) native RPM + DEB packages for Fedora/openSUSE/Debian/Ubuntu built via the openSUSE Build Service (OBS) and/or Fedora COPR, published to a project repo. (Getting INTO official distro repos is maintainer-driven and slow — tracked separately if pursued.) All free, all self-publish. Depends on FIBR-0015 (the built artifacts) and FIBR-0016 (release automation extends to push each channel).
  **Layman:** Beyond Flathub (which already puts us in most Linux app stores), also publish to Ubuntu's Snap Store and Arch's AUR, plus ready-to-install packages for Fedora/openSUSE/Debian — so almost any Linux user can install us in one click.
  Kind: package.
  Source: user-request-2026-07-04.
  Clarified (2026-07-04): this is the item that delivers the user's "each distro's built-in app store / software centre" request. Those centres (GNOME Software, KDE Discover, Ubuntu App Center, Pop!_Shop, Mint Software Manager, elementary AppCenter) are front-ends that read Flathub / Snap / distro repos — there is no per-store submission. So FIBR-0015 (Flathub → GNOME Software + KDE Discover, the majority of distros) + this item (Snap → Ubuntu App Center; native RPM/DEB → repo-based centres) together cover essentially every distro software centre. No separate work per store.

- 📋 [FIBR-0045] **Free Windows/macOS package managers: winget, Chocolatey, Homebrew Cask.**
  Free, self-publishable manager listings that just reference the GitHub Release artifact: (a) winget — a manifest PR to microsoft/winget-pkgs (`winget install finbreak`); (b) Chocolatey — a community nuspec package; (c) Homebrew Cask — a Ruby cask pointing at the macOS .dmg (`brew install --cask finbreak`). No paid account and no signing rework beyond what FIBR-0015 already does. Reaches the more technical slice of Windows/Mac users and gives them auto-update. Depends on FIBR-0015/FIBR-0016.
  **Layman:** Also list the app in the free 'app installers' many Windows and Mac users already use, so they can install and auto-update it with one command — no store account needed from us.
  Kind: package.
  Source: user-request-2026-07-04.

## Enhancements & performance backlog

Ideas captured 2026-07-01 from a product / performance review
(user-requested). Not yet slotted into the P0x phase order — each
carries a **Target phase** and `Dependencies:`; it is promoted into that
phase when its dependencies land. Two are **foundational** (marked
*Sequencing*) and must be designed at the noted phase, not deferred,
because retrofitting them is a data migration.

### 🔒 Security & account recovery

- 📋 [FIBR-0018] **Encrypted vault backup & restore.**
  Export the whole vault to a single encrypted backup file the user
  keeps off-device (external drive / cloud), and restore from it — the
  mitigation design.md names for the no-recovery-backdoor rule, so a disk
  failure or lost laptop doesn't mean lost data. Target phase: P12 (its
  heading already lists "backup"). Dependencies: FIBR-0004. Lanes:
  crypto, ux. Kind: feature. Source: user-request-2026-07-01.

- 📋 [FIBR-0019] **Master-password recovery via recovery key
  (key-wrapping).** At vault creation, generate a high-entropy recovery
  code the user stores safely; wrap the vault data-key under **both** the
  master password and the recovery code (envelope encryption) so a
  forgotten password is recoverable via the code with **no** backdoor.
  *Sequencing:* foundational — the key envelope must exist at FIBR-0004
  (vault creation); retrofitting needs a full re-encrypt migration.
  Requires an ADR + a security-model.md update at spec time. Target
  phase: P02. Dependencies: FIBR-0004. Lanes: crypto, security.
  Kind: security. Source: user-request-2026-07-01.

- 📋 [FIBR-0020] **Biometric unlock (fingerprint / face) with capability
  detection.** Store a key-wrapped copy of the vault key in the OS secure
  keystore, released by the platform biometric (Windows Hello, macOS
  Touch ID, Linux fprintd where present). **Detect** availability per-OS
  and offer it only when present; always keep the password as fallback. A
  convenience unlock, **not** a recovery method — Linux biometric support
  is uneven, so degrade gracefully. Target phase: P12. Dependencies:
  FIBR-0004, FIBR-0019 (shares the key-wrapping envelope). Lanes: crypto,
  platform, ux. Kind: feature. Source: user-request-2026-07-01.

- 📋 [FIBR-0029] **Password reminder / hint (shown before unlock).**
  An optional user-set hint on the unlock screen to jog memory —
  enforced to **not be the password** (and not to contain it). *Security
  note:* the hint must render **before** the vault is decrypted, so it
  lives **outside** the encrypted DB and is readable by anyone with
  device access — warn the user, keep it short, and record the new
  plaintext artefact in security-model.md at spec time. A memory aid, not
  a recovery method. Target phase: P02. Dependencies: FIBR-0004. Lanes:
  crypto, ux. Kind: feature. Source: user-request-2026-07-01.

- 📋 [FIBR-0030] **"Forgotten password → start over" (destructive vault
  reset, double-confirmed).** Last resort on the unlock screen once the
  hint (FIBR-0029) and recovery key (FIBR-0019) are exhausted:
  irreversibly delete the vault and its sidecars and return to first-run
  setup so the user can begin fresh. **Double confirmation required** — a
  clear "this erases everything, permanently and unrecoverably" warning
  **and** a second explicit step (e.g. type DELETE) before anything is
  removed. By design nothing survives (the old data can't be decrypted
  without the key anyway). Target phase: P02. Dependencies: FIBR-0004.
  Lanes: crypto, ux. Kind: feature. Source: user-request-2026-07-01.

- 📋 [FIBR-0031] **Failed-unlock throttling (exponential backoff).**
  Slow down brute-force guessing of the master password: after each wrong
  attempt on the unlock screen, impose a growing delay (e.g. 1s → 2s → 4s
  …, capped) before the next try is accepted. A one-off typo is barely
  noticeable; bulk guessing becomes infeasible. Pure client-side timing —
  no lockout that could deny the legitimate owner access, and no counter
  that weakens the crypto. Record the backoff schedule in security-model.md
  at spec time. Target phase: P04 (lands with the unlock flow).
  Dependencies: FIBR-0004. Lanes: security, ux. Kind: security.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0032] **Clipboard auto-clear for copied sensitive values.**
  When the user copies a sensitive value (account number, amount, a stored
  PDF password), clear it from the system clipboard after a short timeout
  (~30s, configurable in the FIBR-0014 Settings screen) so it doesn't
  linger for other apps to read. Only clear if the clipboard still holds
  the value we put there (don't wipe something the user copied since).
  Target phase: P12. Dependencies: FIBR-0012, FIBR-0014. Lanes: ui,
  security. Kind: security. Source: user-request-2026-07-01.

- 📋 [FIBR-0033] **Backup restore-verification ("does my backup work?").**
  A one-click check that opens an encrypted backup (FIBR-0018) into a
  throwaway in-memory / temp copy, confirms it decrypts and its schema +
  row counts are intact, then discards it — proving the backup is
  genuinely restorable **without** touching the live vault. A backup never
  test-restored is a guess, not a safety net. Target phase: P12.
  Dependencies: FIBR-0018. Lanes: crypto, ux. Kind: feature.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0041] **Back-fill the CSV import path with the INV-5b resource-size cap.**
  security-model.md INV-5b binds an import resource budget (max file size / row count / parse time) to the import specs — naming FIBR-0007 (CSV) and FIBR-0008 (OFX) by id. FIBR-0008 pins the cap for the OFX path (D13: read_file_bytes stat-checks against _MAX_OFX_BYTES before read; a transaction-count cap). But FIBR-0007's CSV path (ImportService.read_file -> str) shipped WITHOUT a size cap, so security-model INV-5b's FIBR-0007 claim is currently unmet. Back-fill: apply the same size stat-check to read_file (or a shared bounded reader), pick a _MAX_CSV_BYTES constant, add a test (monkeypatch the cap down). Surfaced by the FIBR-0008 /cold-eyes (lane C, 2026-07-03).
  **Layman:** Add the same "reject a suspiciously huge file" safety limit to the CSV import that OFX import gets, so no oversized statement file can hog memory.
  Kind: security.
  Lanes: importers, services, tests.
  Source: cold-eyes-2026-07-03 FIBR-0008 lane-C.

### 🎨 Features & accessibility

- ✅ [FIBR-0021] **Multi-currency decision (ADR).** Decide single- vs
  multi-currency for v1 **before** accounts are built. If multi: a
  currency column on accounts/transactions, QLocale-formatted display,
  and a rule that the dashboard never sums across currencies without
  conversion. *Sequencing:* decide before FIBR-0005 (accounts) — adding a
  currency column afterwards is a schema migration. Target phase: P03
  (the decision precedes it). Dependencies: none. Lanes: data.
  Kind: investigate. Source: user-request-2026-07-01.
  Resolved 2026-07-02 (user decision): SINGLE-currency for v1 — every
  account shares the vault's one base_currency, set at first-run. Rationale:
  matches the shipped FIBR-0004 model, and because FIBR-0005 introduces the
  forward-migration runner, adding per-account/per-transaction currency
  later is a routine forward migration, not a painful retrofit — so the
  "decide before accounts" gate is satisfied by choosing single-currency now
  and revisiting only when a real multi-currency need arises. If revisited:
  currency column on accounts/transactions, QLocale-formatted display, and a
  rule that the dashboard never sums across currencies without conversion.

- 📋 [FIBR-0022] **Budgets + recurring / subscription detection.**
  Per-category monthly spending limits with progress + over-budget
  signalling on the dashboard, plus automatic detection of repeating
  charges (same payee / amount cadence) so subscriptions surface. Target
  phase: P10. Dependencies: FIBR-0006 (category tree), FIBR-0010 (rules).
  Lanes: reporting, ux. Kind: feature. Source: user-request-2026-07-01.

- 📋 [FIBR-0023] **Theming: separate theme sets for normal and
  colourblind vision + picker.** Ship **two families** of themes — a set
  for normal colour vision **and** a set designed for colourblind users
  (protanopia / deuteranopia / tritanopia-friendly palettes) — selectable
  from the FIBR-0014 Settings screen (beside the FIBR-0017 language
  picker). The normal-vision family goes beyond plain light/dark: ship a
  small curated set of named themes — at minimum **Light**, **Dark**,
  **Midnight** (near-black OLED-friendly), **Solarized Light**,
  **Solarized Dark**, **Sepia** (warm, low-eyestrain), and a
  **High-contrast** pairing — plus a **"follow the OS"** option that
  tracks the system light/dark setting. Each theme is a named palette
  (window / surface / text / accent / chart-series roles), defined in one
  place so adding a theme is data, not code — no per-widget hardcoded
  colours (coding.md § 8 bars magic constants without a named source; a
  QSS stylesheet + palette tokens keeps colours in one table). Dashboard
  charts (FIBR-0012) draw series colours from the
  active theme's chart-series role, so whichever theme is chosen keeps the
  chart series distinguishable. Target phase: P12. Dependencies:
  FIBR-0012, FIBR-0014. Lanes: ui, accessibility. Kind: ux.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0024] **Accessibility: keyboard navigation + screen-reader
  support.** Full keyboard control (focus order, shortcuts, no mouse-only
  actions) and screen-reader labels/roles via Qt accessibility
  (`QAccessible`) on widgets and charts. Pairs with the i18n/RTL
  (FIBR-0017) and theming (FIBR-0023) work. Target phase: P12.
  Dependencies: FIBR-0014. Lanes: ui, accessibility. Kind: accessibility.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0034] **Import preview + undo (rollback a whole import batch).**
  Before an import lands, show a preview — "about to add 214 transactions
  from 3 May–2 Jun across 1 account" — so a wrong file can be cancelled
  before it touches the ledger. Each committed import is tagged as a batch
  so it can be undone in one action if it was the wrong statement.
  Preserves manual category overrides on re-import per FIBR-0010's rule.
  Target phase: P06 (lands with the first import UI). Dependencies:
  FIBR-0007. Lanes: services, ui, repo, tests. Kind: feature.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0035] **Auto-categorisation that learns from corrections.**
  Extends the FIBR-0010 rules engine: when the user manually re-files a
  transaction (e.g. "TESCO" → Groceries), offer to create or update a rule
  so similar future transactions self-categorise — the tedious part gets
  quieter the more the app is used. Always a **suggestion** the user
  confirms (never a silent auto-rule), and a manual override still wins
  over any learned rule (FIBR-0010's invariant). Target phase: P08
  (extends the rules engine). Dependencies: FIBR-0010. Lanes: services,
  ui, tests. Kind: feature. Source: user-request-2026-07-01.

- 📋 [FIBR-0036] **Net-worth-over-time trend.** A dashboard line showing
  the running total across all accounts month to month — is the overall
  picture trending up or down — distinct from FIBR-0012's
  income-vs-expenditure bars (this is the cumulative balance, not per-month
  flow). Draws its series colour from the active theme (FIBR-0023) like the
  other charts. Target phase: P10. Dependencies: FIBR-0012. Lanes:
  reporting, ui, tests. Kind: feature. Source: user-request-2026-07-01.

- 📋 [FIBR-0038] **Statement coverage tracking + gap detection.**
  Record each imported statement's coverage period (start/end date) per
  account as first-class data, then a gap-detection pass reports
  uncovered date ranges between covered ranges, per account (e.g.
  Jan–Mar + May-onwards -> flags April missing). Range-based, so it is
  reliable where a transaction-date heuristic is not: a quiet month with
  zero transactions is still "covered" if its statement was imported, and
  it handles non-monthly cycles (quarterly) and overlapping imports
  (merge coverage). "Up to date" (latest statement -> today) is not a
  gap; only holes between covered ranges are. Surfaces as a per-account
  completeness report + a dashboard warning badge. Depends on the
  coverage-period capture hook added at first import (FIBR-0007) — without
  recorded periods, gaps can only be guessed from transaction dates
  (false alarms on quiet months). Dependencies: FIBR-0005 (accounts —
  gaps are per-account), FIBR-0007 (import captures the periods).
  **Layman:** Warns you when you've skipped a statement — e.g. you loaded January–March and then May onwards, and it spots that April is missing for that account.
  Kind: feature.
  Lanes: services, repo, ui, tests.
  Source: user-request-2026-07-02.

- 📋 [FIBR-0039] **In-app liability disclaimer + issue reporting.**
  A plain-language liability disclaimer — the app is provided as-is and is not responsible for incorrect information it may display (mis-parsed amounts, wrong totals); it is local-only and not financial advice. Shown at first run (acknowledged once, persisted) and always available from an About/Help dialog. Alongside it, a "Report an issue" link opening the GitHub Issues page (https://github.com/milnet01/finbreak/issues) so users can log problems for resolution. Complements the MIT LICENSE's warranty disclaimer with a user-facing, plain-English one. Shares the About/Help screen with the donate-links item — whichever ships first builds the screen.
  **Layman:** A clear notice that the app isn't responsible for any incorrect figures it shows, with an easy button to report problems so they get fixed.
  Kind: feature.
  Source: user-request-2026-07-03.
  Coordination note update: FIBR-0051 (P07.5) ships only a minimal About (QMessageBox.about) and puts donate links in their own Donate menu — it does NOT build the shared About/Help screen. So this bullet still owns building that screen (disclaimer + "Report an issue" link); the old "whichever of FIBR-0039/0040 ships first builds the screen" pact no longer applies.

- 📋 [FIBR-0040] **In-app donate / support links.**
  Clickable support links that open each FUNDING.yml sponsor page in the user's browser — GitHub Sponsors (milnet01), Patreon (AntsProjectsHub), and the Paybru tip URL (https://paybru.co.za/tip/ants-projects-hub). Surfaced in the About/Help dialog and a Help-menu entry. Keep the URLs in one place in sync with .github/FUNDING.yml (a small constants module or read at build time) so they never drift. Shares the About/Help screen with the disclaimer item.
  **Layman:** Buttons in the app that open the pages where people can support the project financially.
  Kind: feature.
  Source: user-request-2026-07-03.
  Being delivered by FIBR-0051 (P07.5 app-shell, spec in cold-eyes): its Donate menu ships all three FUNDING.yml links + the sync check (FIBR-0051 INV-8a). Flips ✅ when FIBR-0051 ships (FIBR-0051 DoD #6). Note the placement differs from this bullet's "About/Help dialog + Help menu" — FIBR-0051 uses a dedicated Donate menu.

- 📋 [FIBR-0042] **Preserve the as-posted local date for a timezone-bearing OFX <DTPOSTED>.**
  Surfaced by the FIBR-0008 /indie-review (lane 1, 2026-07-04). `OfxImporter` uses `tx.date.date().isoformat()`; ofxparse normalises a timestamped `<DTPOSTED>` to UTC (`local - offset`), so a transaction posted in the evening of a negative-offset zone rolls to the next calendar day (verified: `20260105230000[-5:EST]` -> "2026-01-06"). Two consequences: (a) mis-assignment to the wrong day and, at a month boundary, the wrong statement period; (b) it can defeat INV-6 cross-source dedup (an OFX row keyed on occurred_on won't match a manually-entered copy if the OFX date shifted). Out of the FIBR-0008 contract (D4/INV-1b specify date-only DTPOSTED, and the fixtures use date-only, so nothing shipped is wrong). Blocked-ish: ofxparse discards the original tz offset, so the fix needs either raw-DTPOSTED reparsing or a product decision on whether local or UTC date is authoritative. Fix: decide the authoritative date, recover the local calendar date (or document UTC), add a tz-bearing DTPOSTED test.
  **Layman:** Some bank OFX files stamp each transaction with a time and timezone; today an evening transaction can be filed under the wrong day, which can also stop it matching a manually-typed copy.
  Kind: fix.
  Source: indie-review-2026-07-04 FIBR-0008 lane-1.

- ✅ [FIBR-0047] **Date pickers show unambiguous ISO YYYY/MM/DD, not the locale's M/D/YY.**
  Shipped 2026-07-04: setDisplayFormat("yyyy/MM/dd") on the main-window date field + the import wizard's period pickers; regression test in the vault suite. A user-CHOSEN format is the separate item below.
  **Layman:** Dates now always read year/month/day (e.g. 2026/07/04) so there's no US-vs-rest-of-world confusion.
  Kind: ux.
  Source: user-request-2026-07-04.

- 📋 [FIBR-0048] **User-configurable date-display format (Settings).**
  Belongs with FIBR-0014 (P12 Settings). The ISO yyyy/MM/dd default already shipped; this promotes it to a user choice persisted in the vault settings.
  **Layman:** Let the user pick how dates are shown (e.g. DD/MM/YYYY, YYYY-MM-DD) instead of the fixed ISO default.
  Kind: feature.
  Source: user-request-2026-07-04.

- 📋 [FIBR-0049] **First-run onboarding / empty-state guidance on the home screen.**
  The home screen opens on the manual add-transaction form with cryptic fields (Amount, Description) and no guidance, which confused a real non-technical tester. Add empty-state help + inline field hints (Amount = money in/out, negative = out; Description = what it was for).
  **Layman:** A friendly welcome for a brand-new user — 'import a statement, or add a transaction by hand' — instead of a bare form.
  Kind: ux.
  Source: user-request-2026-07-04.
  Empty-state half delivered by FIBR-0051 (P07.5): the HomeView getting-started page is this bullet's "friendly welcome — import a statement or add a transaction". Remaining scope: the inline Amount/Description field hints on the manual-entry form (not in FIBR-0051). Stays open for those hints.

- ✅ [FIBR-0050] **Standard Bank (SA) statement text-parser — one reader for all account types.**
  Extends P07 (FIBR-0009). The generic ruled-table extractor
  mangles or misses several real Standard Bank layouts (the
  Current account collapses into one cell; the credit card's
  two-columns-per-line + gridline-less layout is unreadable). Add
  ONE Standard Bank text-layer reader (not per-account-type
  files) that parses the printed transaction lines and feeds the
  existing preview -> dedup -> commit pipeline; a recognised
  statement skips column-mapping (like OFX). Covers current,
  savings, home-loan, revolving-credit-loan, credit-card, and money-market/investment
  statements. Signed amount = the printed figure signed by the running-balance delta
  (unifies the families incl. the home loan, which prints no
  per-amount sign); credit card uses the Debit/Credits section
  rule (flip to purchases-negative budget view). Handles both
  number formats (US 1,427.41 and European 239.206,04 — the RCP
  loan), MM-DD dates with year inferred from the statement
  period, full-ISO dates (home loan), multi-line descriptions,
  per-page brought-forward continuation, and non-transaction row
  skipping. Correctness check: per-row balance-delta == printed amount (primary); additive opening balance + sum of parsed
  amounts == printed closing balance where the statement prints one (Savings has none). Loan-sign note: on a loan a
  fee shows positive (debt up) under the balance-delta rule — a
  user-facing loan-sign toggle is a possible follow-up. Fixtures
  100% SYNTHETIC (no real PII/ID/statements committed).
  Dependencies: FIBR-0009.
  Lanes: importers, ui, tests.
  **Layman:** Makes all your real Standard Bank statements — cheque, savings, home loan, personal loan, credit card and money-market — import cleanly, by teaching the app to read the printed statement lines the way you do.
  Kind: feature.
  Source: user-request-2026-07-05.
  Resolved (2026-07-05): shipped one Standard Bank text-layer reader (StandardBankImporter) for all six account types — current, savings, home loan, revolving-credit, credit card, money-market — family-dispatched inside one module. Validated end-to-end on all six real statements (checksums pass) + 13 synthetic fixtures. Spec cold-eyes-converged (9 loops); TDD (36 tests). Close: /audit clean; /indie-review (2 rounds, cold) — code findings (credit-card de-interleave HIGH, decrypt-crash net, INV-7b sign gate) + a confirming re-review round (1 HIGH corrupt-PDF Qt-slot crash, region-scoped number detection, Family-C continuation fold, _cc_opening sign, INV-12 test correction) all fixed inline; final cold pair clean. Gate green (277 passed/1 skipped, mypy 0). Fixtures 100% synthetic. Journal: docs/journal/FIBR-0050.md. Tag FIBR-0050-complete.</note>

  <invoke name="mcp__ants__changelog_log">
  /mnt/Games/Scripts/Linux/finbreak

### ⚡ Performance

- 📋 [FIBR-0025] **Enable SQLite WAL mode.** Set
  `PRAGMA journal_mode=WAL` on the SQLCipher DB for better write
  throughput and UI responsiveness during import. *Sequencing:* set at DB
  creation (FIBR-0004). WAL adds `-wal` / `-shm` sidecars (already
  ignored by FIBR-0002; SQLCipher encrypts them too). Target phase: P02.
  Dependencies: FIBR-0004. Lanes: persistence, perf. Kind: perf.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0026] **Index the import de-duplication lookup.** Add a DB
  index on `(account_id, date, amount)` (and/or a normalised-description
  hash column) so import dedup (design.md data-flow step 5) is an indexed
  lookup, not an O(n·m) scan of existing rows for every imported row.
  Target phase: post-MVP perf (after P05 — FIBR-0007 ships the un-indexed
  MVP dedup by design; index it when a large account measures slow).
  Dependencies: FIBR-0007. Lanes: data, perf. Kind: perf.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0027] **SQL-side dashboard aggregation + incremental refresh.**
  Compute dashboard summaries / charts with SQL `GROUP BY` rather than
  Python loops, and refresh incrementally on a single-row edit instead of
  a full recompute; add supporting indexes (`date`, `category_id`). Keeps
  the dashboard fast at tens of thousands of transactions. Target phase:
  P10. Dependencies: FIBR-0012. Lanes: reporting, perf. Kind: perf.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0028] **Virtual table model for the transaction list.** Back
  the transaction table with a `QAbstractTableModel` (lazy / virtual
  rows) rather than per-row widgets, so a large history scrolls smoothly.
  Target phase: P10. Dependencies: FIBR-0012. Lanes: ui, perf.
  Kind: perf. Source: user-request-2026-07-01.

---

### 🧹 Warnings & tech debt

Every warning or error found during any work — tests, gate, build, tooling,
dependencies, review — is filed here (or the most fitting section) for later
investigation/resolution, even when third-party or non-blocking. A warning today
is a future error tomorrow.

- 📋 [FIBR-0043] **Silence/resolve ofxparse's bs4 findAll DeprecationWarning noise in the test run.**
  Surfaced by FIBR-0008 (2026-07-04). Running `tests/features/ofx_import/` emits ~100 `DeprecationWarning: Call to deprecated method findAll. (Replaced by find_all)` — raised INSIDE `ofxparse` 0.21 (`ofxparse.py` calling BeautifulSoup's deprecated `findAll`), not our code. Harmless today (tests pass), but: (a) it's log noise that masks real warnings, and (b) a future bs4 major could turn `findAll` into a hard error, breaking OFX import. ofxparse 0.21 is the current latest (lightly maintained), so there's no newer release to bump to. Options: a scoped pytest `filterwarnings` ignore for ofxparse's DeprecationWarning (documented, so it doesn't hide OUR deprecations); upstream a PR to ofxparse (findAll -> find_all); or, if bs4 ever breaks it, migrate to a maintained parser (ofxtools) — the escape hatch already noted in FIBR-0008 § Dependencies. Decide + apply.
  **Layman:** The OFX-import library prints ~100 harmless "this method is old" warnings whenever we run our tests; the app works fine, but the noisy warnings should be quietened or fixed at the source.
  Kind: investigate.
  Source: in-session-2026-07-04 FIBR-0008 build/test warnings.

## How to add an item

1. Allocate the next ID:
   ```bash
   echo $(($(cat .roadmap-counter) + 1)) > .roadmap-counter
   printf "FIBR-%04d\n" $(cat .roadmap-counter)
   ```
2. Insert at the **position** where it should be tackled (not
   blindly at the end).
3. Set the status emoji (📋 Planned, 💭 Considered).
4. Add `Lanes:` line declaring ownership.
5. Add `Kind:` (required on every bullet, per
   `roadmap-format.md § 3.5`) and `Source:` (omit only when it's
   `planned`).

See `docs/standards/roadmap-format.md § 3.5` for the full bullet
contract.

## How findings get folded

After every `/audit` + `/indie-review` (and `/debt-sweep`):

```
Phase closes
  → Run /audit + /indie-review
  → Triage findings
  → If clean: phase fully closed.
  → If actionable: batch into one new fix-pass FP## (next-up),
    add [Unreleased] entry, run that fix-pass through the
    9-step loop; its own closing audits may produce another.
```

See `docs/standards/roadmap-format.md § 3.8` and the
[app-workflow skill](~/.claude/skills/app-workflow/SKILL.md)
for the full pattern.
