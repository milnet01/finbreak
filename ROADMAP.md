<!-- ants-roadmap-format: 1 -->
# finbreak — Roadmap

> **Current version:** 0.1.7 (released 2026-07-12). See
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

- ✅ [FIBR-0053] **Pre-push git hook runs the CI gate locally before every push.**
  Prompted by a CI failure email (commit a0cc895: gitleaks flagged the
  `shiboken6.isValid` false-positive in the FIBR-0051 spec prose; fixed in the
  next commit via `.gitleaks.toml`, so main was already green). Root cause was
  process, not drift: `ci.yml` already calls `scripts/ci-setup.sh` +
  `scripts/ci-local.sh` (the identical gate a dev runs), so green-locally ==
  green-in-CI — but that docs-only cold-eyes commit was pushed without running
  the gate. `.githooks/pre-push` runs `scripts/ci-local.sh` on every push (venv
  auto-activated), enabled via `git config core.hooksPath .githooks` (documented
  in CLAUDE.md; a fresh clone enables it once). Faithful full-gate match; a rare
  pypi timeout can flake pip-audit (retry / `--no-verify` for that transient
  case).
  **Layman:** Automatically checks your work before it leaves your machine, so a broken commit can't reach GitHub and trigger a failure email.
  Kind: chore.
  Lanes: ci, build.
  Source: user-request-2026-07-09 (CI failure email on a0cc895).

- ✅ [FIBR-0055] **Settings screen — a Settings menu item whose first control is a user-configurable auto-lock timeout, plus core preferences.**
  User request 2026-07-09: add a Settings menu item; the first thing to
  include is a user-set timeout for the auto-lock (lockout) feature. Pulls the
  Settings-screen + auto-lock-timeout portion of FIBR-0014 (P12) FORWARD as its
  own near-term item (it only depends on what is already built — the FIBR-0004
  auth/idle-lock spine and the FIBR-0052 shell); FIBR-0014 keeps the heavier
  encrypted-backup export/import + dark-theme polish pass, and hosts the
  FIBR-0017 language switcher.
  Resolved 2026-07-09 (FIBR-0055-complete): Settings screen shipped — File → Settings… opens a modal SettingsDialog with a user-configurable auto-lock timeout (1/5/10/15/30 min, default 10, persisted in the vault settings table, applied live to the idle timer) + a read-only base-currency display. No schema change. Spec /cold-eyes-converged (4 loops); TDD (19-leg tests/features/settings/); /audit 0, /indie-review 3 cold lanes clean (2 test-fidelity LOWs folded). Gate green 343 passed/1 skipped, mypy 0. Theme toggle + stored-PDF-password management remain in FIBR-0014.

  Scope (settle exact list at spec time -> /cold-eyes before TDD):
  - A **Settings** entry in the menubar (and/or a toolbar/Window-menu action)
    opening a Settings screen — a tab or a modal dialog (decide at design;
    a modal keeps it out of the tab rotation, a tab matches the workspace).
  - **Auto-lock timeout (the priority):** the FIBR-0004 idle auto-lock currently
    uses a FIXED inactivity timeout; make it user-configurable (e.g. 1/5/10/15/30
    min, with a sensible floor; a "never" option only behind an explicit warning
    since it defeats the security spine). Applied live to the running idle timer;
    persisted so it survives a restart. Persistence home to settle: the vault
    settings table (it is only needed while unlocked) vs the plaintext settings
    sibling used for window geometry (non-sensitive) — likely the vault settings
    table, read on unlock.
  - **Other settings suggested (cheap, tie into what exists; trim at design):**
    - Base / display currency (already a vault setting from FIBR-0004 — surface it).
    - Theme: dark / light / follow-system toggle (deferred to FIBR-0014 at spec
      time — the toggle needs the theme system that phase's polish pass builds).
    - Manage stored PDF passwords (FIBR-0009 stores per-account PDF passwords) —
      view which accounts have one remembered + a "forget" button.
    - "Confirm before deleting a statement" toggle (for the FIBR-0052 delete).
    - Startup tab preference (which workspace tab opens on launch — ties to the
      FIBR-0052 last-tab persistence).
    - "Check for updates" on/off (the opt-in switch FIBR-0054 auto-update needs;
      off by default — the update check is the one deliberate, consented egress).
    - Number / date format override (deferred at spec time: locale *number*
      formatting → FIBR-0017 i18n; user-chosen *date* format → FIBR-0048).
  - Every new string tr()-wrapped, layouts (no fixed geometry) for RTL, amounts
    via QLocale (coding.md §5.2), consistent with the rest of the UI.

  Dependencies: FIBR-0004 (auth + idle auto-lock), FIBR-0052 (shell). Relates to
  FIBR-0014 (P12 settings — narrowed to backup + theme polish + i18n host),
  FIBR-0009 (stored PDF passwords), FIBR-0054 (update-check opt-in).
  **Layman:** Adds a Settings menu where you can change how the app behaves — first and foremost, how long it waits before locking itself when you step away (right now that time is fixed). Also a home for a few other handy toggles.
  Kind: feature.
  Source: user-request-2026-07-09.

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

- ✅ [FIBR-0054] **Optional in-app auto-update (check → prompt Later/Skip/Update now → download, install, relaunch).**
  User request 2026-07-09: the app must offer (never force) updates. Flow:
  on a new version, prompt the user with three choices — **Later** (re-ask next
  launch), **Skip** (this version, don't re-prompt for it), **Update now**. On
  "Update now": download the latest build, close the app, install the update, and
  relaunch automatically.
  Progress (2026-07-10): brainstormed + design approved. Scope = full in-app auto-update, Linux/AppImage first (Windows seam only, not built). Two phases: (1) real release infra — version 0.1.0, signed release AppImage, published v0.1.0 GitHub Release; (2) the updater — opt-in launch check → Later/Skip/Update-now prompt → download + Ed25519-signature-verify → atomic AppImage swap → relaunch. Integrity gate = Ed25519 signature verified via the already-bundled `cryptography` lib (no new runtime dep/tool). Next: write docs/specs/FIBR-0054.md → /cold-eyes.
  Resolved (2026-07-14) by /close-phase. Code-complete since v0.1.0 and field-proven through v0.1.9; the live auto-relaunch confirmed v0.1.8->v0.1.9 (commit 8e4a298) was the last gate before close. Close ran a full audit (semgrep/ruff/bandit/gitleaks) + 2 cold indie-review lanes over the auto-update surface: 1 MEDIUM (_on_download_failed missing the auto-lock guard its ready-sibling has) + 3 LOW (temp-staging outside the try; 2 test-fidelity) all fixed inline (commit 67132c1); 2 semgrep dynamic-urllib FPs allowlisted (allowlist-001). Gate green 856/1. Tag FIBR-0054-complete. Windows in-app auto-update is FIBR-0131 (separate).

  Design notes (to settle when picked — needs its own brainstorm + spec →
  /cold-eyes):
  - **Per-platform mechanism** (no single cross-platform updater). *FIBR-0054
    has since settled the **Linux AppImage** slice: full-file download + atomic
    replace + Ed25519 verify (D2 rejected zsync/delta; D1 chose Ed25519 via the
    bundled `cryptography`, not AppImageUpdate). The other platforms below remain
    to-settle.* Linux AppImage → AppImageUpdate / zsync + delta; Flatpak/Flathub
    → the platform updates it
    (an in-app updater would be redundant/blocked there — likely just deep-link to
    the store or no-op); Windows .exe → a bundled updater (e.g. WinSparkle) or a
    small helper that swaps the install after exit; macOS .app → Sparkle. The
    "close → install → relaunch" hand-off is the platform-specific hard part.
  - **Update source + integrity:** check GitHub Releases (the repo already
    publishes there); verify a signature / checksum before installing (security —
    never run an unverified downloaded binary). Respect the no-network default
    elsewhere: the update check + signed download are the one deliberate outbound
    flow, opt-in via a setting, off by default until the user consents.
  - **UX:** a non-blocking prompt (not a modal that traps them); "Skip this
    version" persists the skipped version (in the plaintext settings sibling, like
    window geometry — not the vault); works while locked (no vault needed to
    update). Show current vs available version + changelog link.
  - **Depends on** the release pipeline (ADR-0007 / FIBR-0003 bundling) being able
    to publish signed artifacts. Sequence after the core app is feature-complete;
    not blocking FIBR-0052/P08/P09.
  **Layman:** The app checks for a newer version and, if you choose, downloads and installs it for you and reopens — you're always in control (Later, Skip this version, or Update now).
  Kind: feature.
  Lanes: packaging, ui, services.
  Source: user-request-2026-07-09.

- ✅ [FIBR-0132] **Windows `.exe` launches with a console window — build `--windowed` to suppress it.**
  FIBR-0015 froze the .exe with `--onefile` but not `--windowed`, so PyInstaller attaches a console (the black cmd window the user saw before the GUI). Fix: add `--windowed` in build-windows-exe.py. Wrinkle: `--windowed` sets sys.stdout/stderr to None on Windows (PyInstaller docs), so the windows-build.yml `--self-test` sentinel read (FINBREAK_SELFTEST_OK) goes blind — reroute the sentinel to a file via a FINBREAK_SELFTEST_OUT env var (run_self_test already takes an `out` stream) and have the workflow read the file + Start-Process -Wait for the now-GUI process. Regression-lock with a windows_build feature test asserting the driver builds --windowed.
  **Layman:** Stops the black command-prompt window from flashing up before the app opens on Windows.
  Kind: fix.
  Source: user-report-2026-07-14.
  Resolved 2026-07-14: `build-windows-exe.py` now freezes `--windowed`; self-test sentinel rerouted to FINBREAK_SELFTEST_OUT file so the clean-room read survives the None stdout; windows-build.yml reads the file via Start-Process -Wait. Regression-locked (test_driver_freezes_windowed_gui_exe + test_selftest_can_redirect_sentinel_to_a_file). Gate green 853/1. Ships in the next Windows release build.

- 🚧 [FIBR-0133] **Free Windows code signing via SignPath Foundation (OSS program).**
  User applying to SignPath Foundation's free code-signing program for OSS. Prep done this session: PRIVACY.md added (finbreak collects no data; local-only); README gained the required SignPath attribution ("Free code signing provided by SignPath.io, certificate by SignPath Foundation") which the hub site renders onto the download page (antsprojectshub.co.za/p/fin-break.html); Google Search Console verification + indexing done so the app is discoverable (a SignPath requirement — see [[finbreak-public-site-and-signing]]). Also fixed the stale milnet01/Fin_Break->finbreak repo slug in the hub data. REMAINING once approved: wire the SignPath signing step into .github/workflows/windows-build.yml so release .exe artifacts are signed; promote the .exe to a signed release asset. Requirements met: MIT license, public repo, GitHub 2FA (user to confirm), discoverable (in progress). Windows-only (macOS = Apple $99/yr; Linux AppImage GPG-signed already).
  **Layman:** Get finbreak's Windows app officially signed for free so Windows stops showing "unknown publisher" warnings.
  Kind: package.
  Source: user-request-2026-07-14.
  Scope boundary (2026-07-14): "promote the .exe to a signed release asset" above means the AUTHENTICODE/publisher signature only. The Ed25519-signed .exe release asset (the sidecar the in-app updater verifies) is FIBR-0131's D5, not this item. FIBR-0133 adds the Authenticode signature to that already-attached .exe once SignPath approves.
  Progress (2026-07-14): the SignPath "discoverable" requirement is now MET — the Fin Break page (antsprojectshub.co.za/p/fin-break.html) is live and INDEXED on Google (confirmed via a Google search result, ~3h after publish). Requirements now: MIT ✓, public repo ✓, PRIVACY.md + SignPath attribution ✓, discoverable ✓; REMAINING = SignPath's own approval ONLY (external, awaited); GitHub 2FA confirmed ON (2026-07-14, GitHub-mandated). All contributor-side SignPath requirements (MIT, public repo, PRIVACY + attribution, discoverable, 2FA) are now MET. No code work outstanding; FIBR-0131's Windows updater is already merged and waiting for the v0.1.10 release that will bundle both the Authenticode signature (this item) and the Ed25519 .exe.sig.

- ✅ [FIBR-0134] **Embed the finbreak icon in the Windows .exe (was PyInstaller's default console-stub icon).**
  The published v0.1.9 finbreak-0.1.9-x86_64.exe showed PyInstaller's default console-stub icon in Explorer/taskbar because scripts/build-windows-exe.py never passed --icon to the freeze. Fixed by adding `--icon assets/icon/finbreak.ico` (the committed multi-size 16..256 Windows icon from FIBR-0037) to the PyInstaller command, plus a fail-loud guard that the .ico exists and a windows_build regression test asserting the driver passes --icon and the .ico is a real MS icon. Driver flag only (like --windowed/FIBR-0132), so the Linux parity guard is untouched; the Linux AppImage icon travels separately via appimagetool. The icon-bearing .exe appears on the NEXT Windows build/release — the already-published v0.1.9 asset is not rewritten.
  **Layman:** Make the Windows app file show finbreak's donut icon in Explorer instead of a generic black terminal icon.
  Kind: fix.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14): added --icon assets/icon/finbreak.ico to scripts/build-windows-exe.py + a fail-loud .ico-exists guard + a windows_build regression test (test_driver_embeds_the_app_icon). Gate-relevant tests green (windows_build 13 passed). Icon lands on the next Windows build.

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

- ✅ [FIBR-0051] **P07.5: app-shell UX redesign — real app window (QMainWindow) with menubar / icon toolbar / status bar; first-run & unlock as popups.**
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
  user-initiated hand-off to the OS browser; the app itself made no
  network calls at the time of this bullet (FIBR-0054 later added the
  one opt-in, off-by-default update check — your financial data still
  never leaves the machine). Reuses the existing
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
  Resolved (2026-07-09): shipped by /close-phase. QMainWindow shell + popup first-run/unlock/manual-entry dialogs + status bar + Donate menu; content destroyed-on-lock (no decrypted rows survive). TDD: 22 tests/features/app_shell/ + D10 ripple re-home; gate green 299 passed/1 skipped, mypy 0; FIBR-0003 build smoke PASS (icons travel into the frozen bundle, DoD #2). /audit clean; /indie-review 2 cold lanes — no CRIT/HIGH/MED, 2 LOW (status-bar Ready restore, locale-hermetic amount test) + 1 INFO (QIcon-absent rationale) folded inline. Tag FIBR-0051-complete.

- ✅ [FIBR-0052] **P07.6: tabbed main window + statement provenance & delete (shell v2).**
  Tabbed-workspace evolution the user approved 2026-07-09 (design brainstormed + approved this session), EXPANDED the same day by two follow-ups — exact per-statement transaction count + delete-a-statement-and-its-transactions — which pull the statement-provenance data model (planned as "Round 2") into this phase (user chose "all in one phase", 2026-07-09). Builds on the FIBR-0051 shell. Full contract: docs/specs/FIBR-0052.md.
  Resolved (2026-07-09): shipped by /close-phase. Tabbed QTabWidget workspace (Home · Statements · Accounts · Categories) + Home toolbar button + vault-independent Window menu (Center/Reset) + window geometry/last-tab persisted to a plain INI outside the vault; Statements tab (StatementService + StatementsWidget) with an exact linked-transaction count + atomic delete-statement-and-its-transactions; v5→v6 nullable transactions.statement_period_id FK + commit_import stamp (reordered period-first) + one-time ambiguity-guarded backfill; AccountsWidget/CategoriesWidget show_done flag; home.svg. TDD: 27 tests/features/statements/ + the FIBR-0051 app_shell ripple (nav/lock/manual-entry re-homed to the tab model) + the v5→v6 schema ripple across vault/accounts/categories/import_/ofx_import/pdf_import. Gate green 324 passed/1 skipped, mypy 0; home.svg travels via the existing ui/icons/*.svg glob (DoD #2). Real Standard Bank credit-card PDF validated end-to-end in a throwaway vault (53 txns, exact count, clean delete). /audit 0; /indie-review 3 cold lanes — no CRIT/HIGH/MED, security spine verified; 1 production LOW (locked-vault delete guard) + 1 test-fidelity + 4 coverage findings folded inline. Tag FIBR-0052-complete. P08/FIBR-0010 rules follows.

  Scope:
  - Central content area becomes a QTabWidget "workspace" with FIXED tabs: Home · Statements · Accounts · Categories. Mirrored under the View menu (both navigate); the tab widgets are PERSISTENT (a switch, not a rebuild). Reuses AccountsWidget/CategoriesWidget as tab pages via a `show_done` flag that retires their now-redundant "back to Home" button in tab mode.
  - Add a Home QAction to the toolbar (new house SVG glyph). Toolbar order: Home · Manual entry · Import · Accounts · Categories · Lock. Toolbar buttons switch tabs; Manual entry / Import still open their dialog / wizard (Import is a flow that replaces the workspace and returns to it, NOT a tab).
  - **Statement provenance (v5→v6 migration):** add a nullable `transactions.statement_period_id` FK; `commit_import` stamps every imported row with its source statement; manual entries stay NULL. A one-time ambiguity-guarded backfill links statements imported before the column existed (stamp account+in-span rows, skip dates covered by >1 period). Every importer already writes statement_periods via the single commit_import path, so no backfill of the record itself is needed.
  - **Statements tab (read + delete):** lists every imported statement (account · period · source file · imported-at · transaction count = rows linked via statement_period_id — exact for v6 imports, backfill-linked for pre-v6 imports; a statement with no linked rows shows 0, not an em-dash). A Delete action removes the statement record AND its imported transactions in one atomic service transaction (manual/other-statement rows untouched), after a confirmation naming the count; refreshes Home + the status count. New StatementService (services/statements.py) + StatementsWidget (ui/statements.py).
  - Home tab: unchanged from FIBR-0051 (getting-started ↔ table). Full categorised income/expenditure breakdown is still FIBR-0012.
  - Window geometry: remember size + position + toolbar state + last-active tab via QSettings in a plain INI (paths.window_settings_path()) OUTSIDE the encrypted vault (non-sensitive; restored before unlock). Add Center-window + Reset-layout actions in a vault-independent Window menu.
  - Security preserved: lock tears down the whole tabbed workspace (and any open import wizard) and shows the Locked placeholder (rebuilt on unlock) — FIBR-0051 INV-3 (nothing decrypted survives a lock). The delete is a service-owned atomic transaction leaving a re-openable vault on failure; the plain FK (no cascade) blocks an unsafe period-only delete.

  Staging (the rest, approved but separate items):
  - Follow-up (cheap now the stamp exists, not requested yet): a dedicated per-statement transaction VIEW (double-click a statement → its transactions read-only). Undo-of-delete also deferred.
  - Later (post-FIBR-0052): Home dashboard — income/expenditure summary + category breakdown; BLOCKED on P08 (FIBR-0010 category link) + P09 (FIBR-0011 transfer detection) for correct totals (self-transfers must not double-count). This is FIBR-0012's dashboard, pulled onto Home.

  Progress (2026-07-09): spec docs/specs/FIBR-0052.md written from the approved+expanded design; next /cold-eyes to convergence (rule §14) before TDD.

  Dependencies: FIBR-0051 (shell). Independent of P08/P09; runs before them.
  **Layman:** Turn the single content area into tabs (Home · Statements · Accounts · Categories), add a Home button to the toolbar, and make the window remember its size and position (plus a Center-window action). The Statements tab shows what you've imported with an exact transaction count and lets you delete a statement and all its transactions — which needs a small database change to tag each transaction with the statement it came from.
  Kind: implement.
  Lanes: ui, app, tests.
  Source: user-request-2026-07-09.

## P08 — Auto-categorisation rules

### 🎨 Features

- ✅ [FIBR-0010] **P08: rules engine + manual override.**
  `CategorizationService` applies a user-editable rule set to
  auto-assign categories; a manual override is the
  highest-priority signal and is never clobbered by re-import or
  a later rule. Rules-manager UI to view/add/edit. Dependencies:
  FIBR-0005, FIBR-0006, FIBR-0007, FIBR-0051, FIBR-0052. Lanes: services, ui, repo, tests. Kind: implement.
  Source: planned.
  Scope note (2026-07-09, spec drafted): the spec (docs/specs/FIBR-0010.md) grows this bullet's "rules-manager (view/add/edit)" summary to the full P08 slice — the transaction→category link (v6→v7), first-match-by-priority rules run on import + an explicit "Apply rules now", a manual per-transaction override that is frozen (never clobbered by re-import or a rule run), a Home Category column + "Set category…", the rules-manager tab (add/edit/delete/move/apply), an atomic delete-category cascade with a blast-radius confirm, and the learn-from-corrections offer pulled forward from FIBR-0035 (see that bullet). Deps widened to FIBR-0005/0006/0007/0051/0052.
  Resolved (2026-07-10): shipped. Rules engine + manual override + learning + delete-category cascade; schema v6->v7. TDD 45 tests; /audit 0, /indie-review 3 cold lanes + confirming pass (1 HIGH auto-lock + 3 MED test-coverage/naming + 1 LOW dedup-helper folded inline). Gate green 411/1, mypy 0. Tag FIBR-0010-complete; journal docs/journal/FIBR-0010.md.

---

## P09 — Transfer detection

### 🎨 Features

- ✅ [FIBR-0011] **P09: transfer detection
  (suggest-then-confirm).** `TransferDetectionService` matches a
  debit in one account against a credit in another (same amount,
  short date window) and **proposes** the pair; only
  user-confirmed pairs are linked as transfers and excluded from
  income/expenditure totals (success criterion 3, ADR-0006).
  Rejected pairs are remembered so they don't re-surface. Never
  auto-hides a real expense. Dependencies: FIBR-0005, FIBR-0007. Lanes:
  services, ui, repo, tests. Kind: implement. Source: planned.
  Progress (2026-07-12): design brainstormed + approved by user. Chose ±3-day match window, a dedicated Transfers tab (no post-import pop-up), and a single decision table (v7→v8) recording confirmed/rejected pairs (pending candidates recomputed live). Next: write docs/specs/FIBR-0011.md → /cold-eyes (7-loop cap) → TDD.
  Resolved (2026-07-12): shipped by TDD. Schema v7→v8 (transfer_pairs decision table, dual ON DELETE CASCADE, canonical UNIQUE); TransferRepository (candidate self-join — equal-magnitude/opposite-sign/different-account/±TRANSFER_WINDOW_DAYS=3, per-decision commits); TransferDetectionService (candidates/confirm/reject/unlink/confirmed_transfers/confirmed_transfer_txn_ids [the FIBR-0012 exclusion primitive]/confirm_all); the 6th Transfers tab (suggested+confirmed tables, Confirm/Reject/Confirm all/Unlink, VaultLockedError-guarded). tests/features/transfers/ one case per INV-1..12 + edges (window 0/3/4, off-by-one, two-debits, same-account, Cartesian, empty-vault); schema-version + tab-count ripple across 9 suites. Spec /cold-eyes-converged loop 4. Close: /audit 0 in the new code (3 pre-existing FIBR-0054 updater semgrep warnings out of scope); /indie-review 2 cold lanes — data/logic CLEAN, UI/shell 2 LOW (auto-lock test parametrized over all 4 slots; stale tab-count docstrings) folded inline. Gate green 645/1, mypy 0. Unblocks FIBR-0012 (dashboard).

---

## P10 — Reporting + dashboard

### 🎨 Features

- ✅ [FIBR-0012] **P10: dashboard — summary, pie/donut,
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
  UX (user, 2026-07-11, dogfooding v0.1.2): the Home tab currently shows the raw transaction table (interim from FIBR-0051). The user confirms Home should be the income/expenditure SUMMARY (this dashboard), NOT the transaction list. So this item also owns relocating the transaction table off Home into its own view/tab (e.g. a "Transactions" tab) — carrying the full search + filters this item already promises — leaving Home for the summary + charts.
  **Layman:** The Home screen becomes a proper dashboard — a plain income-vs-spending summary, a pie chart of where your money goes, and month-by-month trends — while the transaction list moves to its own searchable, filterable tab.
  Design approved 2026-07-12 (brainstorming). Scope locked: QtCharts (ADR-0008, no new dep); ReportingService (period model default=previous month, persisted ReportPrefs; transfers never counted as income/expenditure anywhere); Home dashboard (period+account selectors, income/expenditure/net tiles, spending-by-category donut, monthly income-vs-expenditure grouped-bar trend); new Transactions tab absorbing FIBR-0109 (search + date-range + account + category filters, all combinable) with the transaction table relocated off Home. Tab order → Home·Transactions·Statements·Accounts·Categories·Rules·Transfers. Next: ADR-0008 + spec → /cold-eyes.
  Resolved 2026-07-13: shipped by TDD across 11 slices. ReportingService (pure period model + summary/spending_by_category/monthly_trend, transfers excluded, integer-exact) + ReportPrefs persistence; Home reworked into the QtCharts dashboard (donut + 12-month trend, ≤8-wedge collapse, empty-state placeholder); new Transactions tab with search+date+account+category filters (absorbs FIBR-0109); 7-tab shell, count live from Home's ReportingService, QtCharts self-test leg. Close: /audit 0 actionable; /indie-review 2 cold lanes → 3 findings all fixed inline (report_prefs year bound INV-2; per-table column-key objectNames; VaultLockedError-specific slot guards) + 2 regression tests. Gate green 712/1, mypy 0. Tag FIBR-0012-complete.

---

## P11 — Password-protected PDF export

### 🎨 Features · 🔒 Security

- ✅ [FIBR-0013] **P11: locked PDF export with section
  selection.** `PdfExportService` renders chosen sections
  (summary / charts / transactions) for a chosen period via the
  Qt PDF engine, then encrypts with a password set at export
  time (`pikepdf`, AES-256). Export dialog ticks sections + picks
  period + sets password (success criterion 5). Dependencies:
  FIBR-0012. Lanes: services, ui, security, tests. Kind: implement.
  Source: planned.
  **Layman:** Save a password-protected PDF report of your finances — pick which parts to include (summary, charts, transactions) and the date range, and set a password so only you can open it.
  UX (user, 2026-07-12): the export password must be OPTIONAL — the user can choose to add one, but an unprotected PDF export is a first-class supported outcome (not forced). So the "locked" in the headline is opt-in: the section-selection export flow offers an optional password field; empty → a normal unencrypted PDF, non-empty → the pikepdf AES-256 export-lock (ADR-0004). Design the dialog around that choice.
  In-progress 2026-07-13: spec docs/specs/FIBR-0013.md drafted (brainstorm-approved) and in /cold-eyes (project cap 7). Export password OPTIONAL per user; SC5 relaxed accordingly (discovery.md updated).
  Resolved 2026-07-13: P11 locked-PDF export SHIPPED by TDD (7 slices). PdfExportService (in-memory render → optional pikepdf AES-256, atomic export); ui/charts.py shared builders; ReportingService widened to an account set; ExportDialog (INV-14 gating + master-toggle state machine); File-menu + toolbar entry; --self-test encrypt leg. Close: /audit 0 in-scope; /indie-review 2 cold lanes → no CRIT/HIGH/MED, 3 LOW fixed inline (empty-donut placeholder, currency-symbol escaping, narrowed export except). Gate green 779/1. Tag FIBR-0013-complete.

---

## P12 — Settings, auto-lock, backup, theme polish

### 🔒 Security · 🎨 Features

- ✅ [FIBR-0014] **P12: settings, inactivity auto-lock,
  encrypted backup.** Settings screen (base currency display,
  auto-lock timeout, manage stored PDF passwords, theme);
  inactivity **auto-lock** drops the key and returns to unlock;
  **encrypted backup export/restore** (the only mitigation for a
  forgotten master password, per ADR-0003); dark-theme polish
  pass. Dependencies: FIBR-0004. Lanes: ui, services, security, tests.
  Kind: implement. Source: planned.
  **Layman:** A full Settings screen plus an encrypted backup you can export and restore — your one safety net if you ever forget your master password — and a light/dark theme choice.
  Note (2026-07-09): the Settings-screen scaffold + the user-configurable auto-lock timeout (+ base-currency read-only display) are pulled FORWARD into FIBR-0055 (near-term, user-requested); FIBR-0055's first cut delivers the scaffold + configurable auto-lock timeout + read-only currency only. This phase narrows to what remains: the encrypted-backup export/import (the only mitigation for a forgotten master password, ADR-0003), the dark-theme polish pass and its dark/light/follow-system theme toggle (a toggle needs the theme system this pass builds), stored-PDF-password management, and hosting the FIBR-0017 language switcher. If FIBR-0055 ships first, this becomes an extension of that Settings screen rather than a fresh one.
  Split (2026-07-13, in-session, user-approved): P12 bundled four independent pieces. Auto-lock is already shipped (mechanism FIBR-0114; user-configurable timeout + Settings scaffold + read-only currency via FIBR-0055). This item is now NARROWED to the encrypted backup export/restore only — the ADR-0003 forgotten-master-password mitigation, keyed by a SEPARATE backup password so it can actually recover a forgotten master password. The other three pieces are split into their own items: app-wide theme system -> FIBR-0127; stored-PDF-password management UI -> FIBR-0128; language-switcher hosting -> FIBR-0129 (note: overlaps FIBR-0017, which already owns the i18n picker — reconcile when either is specced). Build order: backup (this) first, then 0127, 0128, 0129. Spec: docs/specs/FIBR-0014.md (encrypted backup).
  Resolved 2026-07-13 (/close-phase). Shipped by TDD in 7 red→green slices + a fold-in of 6 cold-review findings. D2 SQLCipher mechanics (sqlcipher_export / PRAGMA rekey / cipher_compatibility / HMAC-on / no-plaintext-temp) validated by a throwaway spike on sqlcipher3-binary 0.6.0 (SQLCipher 4.12.0) before any code. BackupService(vault, auth) export/restore over a stdlib-zip .fbk (manifest.json + params.json + vault.db); separate backup password (fresh salt), INV-1..13. UI: Settings Export + pre-login Restore on unlock & first-run; synchronous main-thread export (INV-9); interrupted-restore reconciliation (INV-5). /audit 0 actionable (1 bandit B608 FP suppressed on a test); 2 cold review lanes → 6 findings (2 HIGH crypto/UI, 2 HIGH/MED, LOW) all fixed inline with regression tests. security-model.md T11 hedge dropped + .fbk untrusted surface added (cold-eyes clean). Gate green 841/1, mypy 0. Tag FIBR-0014-complete.

---

- 📋 [FIBR-0017] **P12: multi-language UI (i18n) — 6 bundled locales incl. RTL + language switcher.**
  Qt translation pipeline: every user-facing string is wrapped in `tr()` from the first UI onward (P02), `lupdate` extracts them to `.ts` catalogs, translations are compiled to `.qm` and loaded via `QTranslator` at startup and on live switch. Ships **6 locales**: English (base), Spanish, Simplified Chinese, Hindi, French, and **Arabic** (right-to-left). A language picker in the FIBR-0014 Settings screen switches locale. Numbers, currency, and dates render through `QLocale` (matters for a finance app — ties into the base-currency display), not hardcoded formats. The UI is built **RTL-ready** (layout mirroring) from P02 per design.md "Internationalization (i18n) & localisation", so Arabic is translate-and-ship; further RTL scripts (Hebrew, Urdu) are then a translation-only follow-up. NOTE: this stays cheap only if the string-externalization and RTL-safe-layout conventions are followed from P02 — retrofitting hardcoded English (and left-to-right-only layouts) across the whole feature stack is far more expensive. Dependencies: FIBR-0014 (settings screen hosts the switcher; transitively pulls the feature-complete UI so all strings exist to translate).
  **Layman:** Lets people use finbreak in their own language — ships in 6 languages to start (including Arabic, which reads right-to-left), with more addable later.
  Kind: implement.
  Lanes: ui, i18n, services, tests.
  Source: user-request-2026-07-01.
  Deferred from FIBR-0004 (P02) per user decision 2026-07-02: the three P02 screens (first_run, unlock, main_window) build their strings once in __init__ and do NOT implement live language switching (changeEvent → retranslateUi). coding.md §5.2 asks for this "from P02"; the FIBR-0004 spec deliverable required only tr() strings + RTL layouts + QLocale amounts (all shipped), and there are no translations to switch yet. When this phase lands, add changeEvent/retranslateUi to those three screens (and every screen built between P02 and here) so the language switcher takes effect without a relaunch.

- ✅ [FIBR-0127] **App-wide six-theme (finance-flavoured) + follow-system theme system & modern polish.**
  Split from FIBR-0014 (P12). Nothing exists today: the app rides the system/Qt default palette (dark by convention) with NO stylesheet, no QPalette install, no theme setting key, no toggle (app.py sets no palette). This builds the theme system from scratch (Fusion + token-driven QPalette/QSS — ADR-0010): a non-vault `theme` pref with 7 values (`system` + six named themes Ledger/Parchment/Mint · Midnight/Graphite/Emerald), palette+stylesheet application at the app entry point, and live follow-system detection, plus the sleek modern polish (gradient/glow accents + grid row-highlighting). Widgets already READ the live palette (ui/icons.py _is_dark_theme, home.py ChartTheme from palette().text(), _amount.py fixed mid-tones) so they adapt once a palette is installed. Delivers FIBR-0116's live icon re-tint on theme switch (toolbar glyphs re-tint on the ThemeController themeChanged signal); the _amount.py palette-adaptive re-tinting stays deferred here. Hosted in the FIBR-0055 Settings dialog. (The old note that the code mis-cites ADR-0002 for the dark theme and "write a real theme ADR when specced" is done — ADR-0010 is that theme ADR; the icons.py citation is corrected in the spec.)
  **Layman:** A proper set of light and dark themes (six finance-flavoured looks) you can choose — or have the app follow your operating system's light/dark setting — instead of the app being dark-only.
  Kind: implement.
  Lanes: ui.
  Source: split-from-FIBR-0014-2026-07-13.
  Spec docs/specs/FIBR-0127.md + ADR-0010 written 2026-07-14 from the user-approved brainstorm (designed look, 6 finance themes Ledger/Parchment/Mint + Midnight/Graphite/Emerald, live follow-system, sleek modern polish: gradient/glow accents + grid row-highlighting, theme-aware toolbar icons). Cold-eyes next.
  Resolved (2026-07-14): SHIPPED by /close-phase (code). TDD 30-leg tests/features/theme/ (INV-1..13 + D3/D4) → ui/theme.py (six-theme token registry → build_palette/build_stylesheet, ThemeController with live colorSchemeChanged follow-system, non-vault pref) + app.py/main_window.py/settings.py wiring + D11 ADR-0002→ADR-0010 citation fixes. /audit 0 actionable (semgrep full + ruff/bandit/gitleaks via gate); /indie-review 2 cold lanes → no CRIT/HIGH/MED, 1 LOW (INV-10 pixmap-content re-tint falsifier) folded inline. Gate green 907/1, mypy 0. Tag FIBR-0127-complete; journal docs/journal/FIBR-0127.md.

- ✅ [FIBR-0128] **Forget remembered PDF statement passwords (per-account, Accounts screen).**
  Split from FIBR-0014 (P12). The store already EXISTS (FIBR-0009, schema v5): accounts.statement_pdf_password (nullable, vault-encrypted at rest, deliberately not selected into the Account dataclass for credential hygiene), with AccountsRepository.get_pdf_password / set_pdf_password. It is written implicitly during import and auto-tried; there is NO management UI. This item adds an Accounts-screen, per-account control to list accounts with a remembered statement password and forget (clear) it (placement + forget-only per spec FIBR-0128 D1/D5). (Distinct from the FIBR-0013 export password, which is ephemeral and never stored.)
  **Layman:** A per-account button to see which accounts have a remembered bank-statement password and forget (clear) it — the password itself is never shown.
  Kind: implement.
  Lanes: ui, security.
  Source: split-from-FIBR-0014-2026-07-13.
  Placement decided (spec FIBR-0128 D1, user directive 2026-07-14): the presence/forget controls live on the **Accounts screen** (per-account, selection-driven), NOT Settings — different accounts can have different statement passwords, so the per-account surface is the natural home. Forget-only (no reveal, no manual set); the secret never crosses into the UI. Spec written; /cold-eyes next.
  Resolved (2026-07-14): SHIPPED by /close-phase (code). TDD 8-leg tests/features/accounts/ (INV-1..5) → repo ids_with_pdf_password + service account_ids_with_pdf_password + ui/accounts.py Forget button/marker/handler. Presence is an id-set (never selects the secret column); the plaintext never crosses into the UI (INV-1). Forget-only, per-account, confirm-gated, VaultLockedError-silent; enable/disable recomputed before the None early-return so a post-Forget refresh disables the button. semgrep+bandit 0 on the changed surface; 1 cold review lane → production CLEAN, 2 LOW test-precision folded inline. Gate green 915/1, mypy 0. Tag FIBR-0128-complete; journal docs/journal/FIBR-0128.md.

- 📋 [FIBR-0129] **Host the language switcher in Settings (picker widget + language setting key).**
  Split from FIBR-0014 (P12). Strings are tr()-wrapped throughout and RTL-ready (app.setLayoutDirection), but there is NO QTranslator, no .ts/.qm, no language setting key, no picker. This provides the language-picker widget in the FIBR-0055 Settings dialog + a `language` settings key. The translation pipeline itself (lupdate -> .ts -> .qm -> QTranslator at startup + live retranslateUi) is FIBR-0017; gate the picker's usefulness on that, or ship the widget writing the key now and wire it when FIBR-0017 lands.
  **Layman:** A place in Settings to pick your language. The actual translations arrive with FIBR-0017; this just provides the chooser and remembers your pick.
  Kind: implement.
  Lanes: ui, i18n.
  Source: split-from-FIBR-0014-2026-07-13.

- ✅ [FIBR-0135] **Auto-lock "Never" option — let the user disable the idle timer entirely.**
  User lives alone / rarely has visitors and doesn't want the idle auto-lock. Added 0="Never" to ALLOWED_AUTO_LOCK_MINUTES (listed LAST so a corrupt/absent value still falls back to the 1-minute floor, never to "Never" — the INV-1 safe-fail is preserved). _arm_timer stops the timer instead of starting it when Never; notify_activity gains an isActive() guard so user activity can't silently re-arm a disabled timer. Settings combo gains a "Never" label. Password-on-open and manual Lock button are unchanged; the key is still wiped on lock and exit. security-model.md T3 amended to record the accepted residual risk (an unattended unlocked session stays unlocked — a user choice, not a silent default). Reverses the FIBR-0055 D6 "no never option" decision by explicit user request. Kind: enhancement.
  **Layman:** Add a "Never" choice to the auto-lock setting so the app won't lock itself while you're away — you still type your password when you open it and can lock it any time with the Lock button.
  Kind: enhancement.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14) — commit b915254. Auto-lock "Never" (0) added; _arm_timer stops on it, notify_activity isActive()-guarded, combo label + security-model T3 note. Gate green 862/1.

## P13 — Packaging & release

### 📦 Packaging

- ✅ [FIBR-0015] **P13: Windows self-contained `.exe` build.**
  PyInstaller freezes `finbreak.exe` (bundled CPython + all native
  deps — SQLCipher, the needed Qt plugins, qpdf) on a
  `windows-latest` runner via `.github/workflows/windows-build.yml`
  (`workflow_dispatch`), clean-roomed with Python off `PATH`
  (`--self-test` → `FINBREAK_SELFTEST_OK`) and uploaded as a CI
  artifact for testers. Unsigned, manual-update, no installer.
  Builds on the P01 smoke-test.
  Dependencies: FIBR-0013, FIBR-0014, FIBR-0003 (direct
  predecessors). Walking the dependency edges, FIBR-0013 and
  FIBR-0014 transitively pull in the entire P02–P12 feature stack
  (FIBR-0004 through FIBR-0012), so P13 cannot start until the app
  is feature-complete. Lanes: build, ci, packaging.
  Kind: chore. Source: planned.
  Resolved 2026-07-13 (FIBR-0015-complete): the Windows `.exe` shipped by TDD (fixture-first cross-package regression + the INV-3 parity guard + the freeze driver). The one-time blocker — `sqlcipher3-binary` shipped Linux/macOS wheels only — was dissolved by swapping to `sqlcipher3-wheels` (the cross-platform fork, same SQLCipher 4.12.0 engine; ADR-0009), proven vault-portable both directions before the swap. `/audit` 0 actionable; `/indie-review` 2 cold lanes 0 defects; gate green 851/1. See docs/journal/FIBR-0015.md.
  Scope: this item delivered **only the Windows `.exe`**. The **Linux AppImage** already shipped under FIBR-0054 (`scripts/build-release-appimage.sh`); **macOS `.app`/`.dmg` + Flatpak/Flathub** are split to **FIBR-0130** (packaging-only — the `sqlcipher3-wheels` swap already cleared their SQLCipher blocker too). Superseded: the 2026-07-13 "compile SQLCipher on Windows" readiness-scan blocker and the "Wine + MSVC" local-build note — the Windows wheel makes both moot.

- 📋 [FIBR-0130] **P13: macOS `.dmg` + Flatpak/Flathub packaging.**
  The macOS `.app`-in-`.dmg` and the Flatpak manifest for Flathub — the packaging remainder split out of FIBR-0015 when its Windows `.exe` slice closed (2026-07-13). The SQLCipher crypto blocker is already cleared for both (the `sqlcipher3-wheels` fork ships macOS + Linux wheels of the same 4.12.0 engine, ADR-0009), so this is packaging-only: freeze the macOS app on a `macos-latest` runner (reusing the FIBR-0015 `windows_freeze_flags.py` collection list + `--self-test` clean-room) and author the Flatpak manifest; each artifact still meets ADR-0007's "no Python installed" launch bar. Dependencies: FIBR-0015 (freeze tooling), FIBR-0037 (icon → `.icns` / Flatpak icon). Lanes: build, ci, packaging. Kind: chore. Source: split-from-FIBR-0015-2026-07-13.

- ✅ [FIBR-0131] **Windows in-app auto-update.**
  Extend the FIBR-0054 self-update stack (check GitHub → Ed25519-verify the download → the Later/Skip/Update-now dialog — all already cross-platform) to actually *install* the update on Windows, which `detect_installer()` currently returns `None` for (inert, INV-7). A running Windows `.exe` locks itself, so the Linux "os.replace the file then relaunch" trick can't be copied. **Design (user-approved 2026-07-13): a separate helper process does the swap** — the app writes the verified new `.exe` beside the old one and spawns a detached waiter (cmd/PowerShell) that waits for finbreak to exit, moves the new file over the old one, and relaunches it (the Windows analogue of the FIBR-0122 `/bin/sh` waiter; watch the same PyInstaller-onefile `_MEI`-teardown race). Adds a `WindowsInstaller` + `detect_installer()` returning it on a frozen Windows build, and an asset-picker that selects the `.exe` release asset on Windows. Also promote the Windows `.exe` from a CI artifact to a signed release asset (attach + an Ed25519 `.sig` for the updater to verify; FIBR-0015 D6 deferred this) and evaluate Authenticode code-signing (an unsigned self-swapping-and-relaunching `.exe` is what Defender/SmartScreen distrusts most; free-ish for OSS via Azure Trusted Signing / SignPath). Same two-cycle caveat as Linux — the relaunch only proves out on the update *after* it ships. Dependencies: FIBR-0054 (update infra), FIBR-0015 (Windows build). Lanes: services, ui, ci, security. Kind: feature. Source: user-request-2026-07-13.
  Sequencing (2026-07-14): the "evaluate Authenticode code-signing" clause above is split out to FIBR-0133 (SignPath, blocked on approval). FIBR-0131 ships the Ed25519-signed .exe release asset + the in-app Windows updater ONLY; publisher (Authenticode/SmartScreen) trust is FIBR-0133 and does not block this. Spec: docs/specs/FIBR-0131.md.
  Spec refinements (docs/specs/FIBR-0131.md, cold-eyes-converged): (1) the waiter is PowerShell (the "cmd/" option was dropped); it waits by exe IMAGE PATH, not a PID (tree-agnostic + PID-recycling-proof). (2) The .exe is ALREADY a published release asset (v0.1.9 ships finbreak-0.1.9-x86_64.exe); the only missing piece for the updater is the Ed25519 .exe.sig sidecar, which D5 adds — so "promote from a CI artifact" is really "add the .sig".
  Closed 2026-07-14 by /close-phase (code-complete). Spec cold-eyes-converged (6 loops x 3 lanes); TDD (WindowsInstaller image-path swap+relaunch behind the existing Installer seam; installer-driven asset-picker; UpdateInfo.appimage_url->asset_url). /audit 0 actionable (3 bandit assert-in-tests FPs, out of gate scope). /indie-review 2 cold lanes -> crypto/PowerShell/ordering verified sound, 1 MEDIUM fixed inline (spawn-before-wipe so a Popen failure can't strand a wiped key; Linux twin guarded too). Gate green 877/1; tag FIBR-0131-complete. CAVEAT (like Linux FIBR-0054): the live Windows swap+relaunch is a two-cycle manual verification on the user's Windows box, and needs a release that first attaches the Ed25519 .exe.sig (v0.1.9 shipped the .exe but no .sig). Journal docs/journal/FIBR-0131.md.

- 📋 [FIBR-0016] **P13: `scripts/publish-release.sh` +
  release automation.** One committed script builds every
  artifact above, publishes the GitHub Release, and drives the
  Flathub submission/update — consuming the Flathub manifest
  produced by FIBR-0015. It is itself a specced item (its own
  `docs/specs/`, cold-eyes-reviewed) — a publish script can't
  predate the thing it publishes. Dependencies: FIBR-0015. Lanes:
  build, ci, packaging. Kind: chore. Source: planned.
  Note (2026-07-10): FIBR-0054 pulls a **Linux-only** slice of release automation forward — a thin `scripts/publish-release.sh` (or `gh release create`) that publishes the signed AppImage + `.sig` as GitHub Release `v0.1.0`, so the in-app updater has a real release to check/download. FIBR-0016 remains owner of the full multi-artifact publish + the Flathub submission/update flow; extend the Linux slice rather than replacing it.
  Note (2026-07-12, user request — "automate the release as much as possible"): the version-bump half is now automated — `.claude/bump.json` (added 2026-07-12) drives /bump and /release: source of truth src/finbreak/__init__.py, mechanical edits to pyproject.toml + tests/test_smoke.py + a dated CHANGELOG cut from [Unreleased], a post_check version-lockstep gate, and tag template v{NEW}. What remains MANUAL (the Linux-slice glue this item should close): after the bump, a human still runs scripts/build-release-appimage.sh (freeze + clean-room + sign), verifies the .sig against the committed RELEASE_PUBLIC_KEY_B64, extracts the CHANGELOG [X.Y.Z] section for notes, and runs `gh release create v<NEW> <appimage> <sig> --notes-file … --latest` (non-prerelease). Deliverable: a single `scripts/publish-release.sh` that chains bump (via the recipe) → full gate (ci-local.sh) → build+clean-room+sign → **verify .sig vs RELEASE_PUBLIC_KEY_B64 (hard gate — never publish an unverifiable release the in-app updater would reject)** → gh release create with the AppImage + .sig attached, notes from the changelog, non-prerelease so /releases/latest resolves. Idempotency + preconditions (clean tree, tag not already present, signing key available) checked up front. Keep it the Linux slice under FIBR-0016; the multi-artifact + Flathub publish stays the full-item scope. Spec-first per the item's own note (docs/specs/, cold-eyes) before coding.

- ✅ [FIBR-0037] **P13: a proper branded app icon (not a flat
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
  Resolved 2026-07-09 (FIBR-0037-complete): branded app icon shipped — a "spending by category" donut (green/blue/teal/orange segments) with a gold coin centre on a dark navy tile, chosen with the user after shrink-testing candidates for small-size legibility (holds at 24px). Single 1024 master assets/icon/finbreak.png; scripts/make-icons.sh derives the platform set (Linux PNGs 16-512, 7-size Windows .ico, macOS .iconset) so they can't drift. Runtime window icon travels as ui/icons/app.png package data, set via QApplication.setWindowIcon (every window/dialog + taskbar); --self-test renders it (bundle-travel proof). macOS .icns is a mac-build-time step from the .iconset (FIBR-0015). /audit 0, indie-review clean (1 stale-comment LOW folded). Gate green 344 passed/1 skipped, mypy 0. Unblocks FIBR-0015 (the builds need the icon).

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

- ✅ [FIBR-0056] **Desktop-launcher integration — running window groups under its launcher (single taskbar icon) + branded icon.**
  Shipped 2026-07-09. A down-payment on FIBR-0015 desktop integration, done now at
  the user's request. app.py sets applicationName + QGuiApplication.setDesktopFileName
  = "finbreak", so the running window's Wayland app_id (X11 WM_CLASS) matches
  finbreak.desktop (StartupWMClass=finbreak) — KDE/GNOME then group the window under
  its launcher instead of showing a second, generic icon. On the user's machine: the
  branded PNGs were installed into ~/.local/share/icons/hicolor/*/apps/finbreak.png and
  the pinned finbreak.desktop's Icon= was pointed from wallet-open to finbreak (caches
  rebuilt). Repo change is app.py only; the .desktop + icon-theme install are
  per-machine (the canonical packaged .desktop + hicolor install belong to FIBR-0015).
  Verified: gate green 344 passed/1 skipped, mypy 0; desktop-file-validate clean; app
  launches with app_id/desktopFileName = finbreak.
  **Layman:** Fixes the app showing a second, generic icon in the taskbar when open, and puts the new icon on the panel launcher.
  Kind: implement.
  Source: user-request-2026-07-09.

- 📋 [FIBR-0082] **Generate app screenshots from synthetic dummy data for the GitHub README + antsprojectshub.co.za.**
  A reproducible way to populate a THROWAWAY vault with realistic-but-fake dummy data (a spread of accounts, a month or two of categorised transactions, a couple of imported statements, a few rules) and capture screenshots of the key screens for the GitHub README and https://antsprojectshub.co.za/.

  Scope: a scripted seeder (e.g. scripts/seed-demo-vault.py) that first-runs a vault and inserts synthetic transactions/categories/accounts/rules, plus a documented capture flow for the main views — first-run, unlock, Home, Statements tab, Categories, Rules, the import wizard, and (once P10/FIBR-0012 lands) the spending-by-category dashboard, which is the most compelling shot.

  HARD constraint (security-model INV-6 / testing.md §6): screenshots use ONLY synthetic dummy data — never real financial data, never a real statement, never a committed vault. The seeded vault + captured PNGs are throwaway artifacts (or committed only as marketing PNGs under a docs/ or assets/ path, never the vault/data itself).

  Not blocked: the current shell (Home/Statements/Accounts/Categories/Rules tabs, import wizard) can already be captured now; re-run after the dashboard (FIBR-0012) ships to add the headline dashboard shot. Pairs naturally with a P13 release.
  **Layman:** Create polished screenshots of the app filled with realistic fake sample data — for the GitHub page and the portfolio site — so people can see what it looks like without installing it.
  Kind: marketing.
  Lanes: docs, ui, marketing.
  Source: user-request-2026-07-10.

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
  Merged into FIBR-0014 (2026-07-13): FIBR-0018 and the narrowed FIBR-0014 both describe the encrypted vault backup & restore. FIBR-0014 (docs/specs/FIBR-0014.md) is the IMPLEMENTATION spec; track the work there. The backup safety nudge is FIBR-0089; restore-verification is FIBR-0033. This item stays as the original provenance record — flip it ✅ alongside FIBR-0014 when the backup ships.

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
  Duplicate of FIBR-0095 (2026-07-15): both describe failed-unlock exponential backoff on the master-password unlock screen. FIBR-0095 is the newer, verified record (confirmed 2026-07-11 that services/auth.py applies no backoff) and is the tracking item for the implementation. This bullet stays as the original provenance record — flip it ✅ alongside FIBR-0095 when the throttling ships.

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
  Dependency re-points: FIBR-0018 (the backup mechanism) is merged into and implemented by FIBR-0014, so this restore-verification builds on FIBR-0014's .fbk export/restore (docs/specs/FIBR-0014.md), not a separate FIBR-0018 deliverable.

- ✅ [FIBR-0041] **Back-fill the CSV import path with the INV-5b resource-size cap.**
  security-model.md INV-5b binds an import resource budget (max file size / row count / parse time) to the import specs — naming FIBR-0007 (CSV) and FIBR-0008 (OFX) by id. FIBR-0008 pins the cap for the OFX path (D13: read_file_bytes stat-checks against _MAX_OFX_BYTES before read; a transaction-count cap). But FIBR-0007's CSV path (ImportService.read_file -> str) shipped WITHOUT a size cap, so security-model INV-5b's FIBR-0007 claim is currently unmet. Back-fill: apply the same size stat-check to read_file (or a shared bounded reader), pick a _MAX_CSV_BYTES constant, add a test (monkeypatch the cap down). Surfaced by the FIBR-0008 /cold-eyes (lane C, 2026-07-03).
  **Layman:** Add the same "reject a suspiciously huge file" safety limit to the CSV import that OFX import gets, so no oversized statement file can hog memory.
  Kind: security.
  Lanes: importers, services, tests.
  Source: cold-eyes-2026-07-03 FIBR-0008 lane-C.
  Resolved (2026-07-15): already shipped — verified stale bullet. ImportService.read_file (services/import_.py) routes through the shared _read_capped helper, refusing a file over _MAX_IMPORT_BYTES (16 MiB) BEFORE loading it, so security-model INV-5b's FIBR-0007 (CSV) claim is now met. Hardened beyond the original ask during a later indie-review (H-F/H-G): reads cap+1 bytes rather than trusting stat().st_size, so an endless-symlink (/dev/zero) or a file that grows post-stat can't slip an unbounded read past the cap. Tests: test_read_file_refuses_oversized_csv (monkeypatches the cap to 100) + test_read_capped_bounds_read_against_endless_symlink, both in tests/features/import_/test_import.py. No code change this session — flip only.

- 📋 [FIBR-0095] **Unlock throttling — backoff after repeated failed master-password attempts.**
  Verified 2026-07-11: services/auth.py applies NO delay/backoff on a failed unlock. Add an increasing backoff (and/or a short lockout window) after consecutive failed unlock attempts — defence-in-depth against offline brute-force on a stolen vault, atop Argon2id's already-slow KDF (security-model INV-2). Track the attempt count / last-fail time in the plaintext window.ini (pre-unlock, non-sensitive) or in-memory per session; UX = a friendly 'try again in N seconds'. Deps: FIBR-0004 (unlock path).
  **Layman:** After several wrong master-password tries, finbreak briefly slows further attempts — extra protection if someone gets hold of your vault file.
  Kind: security.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0096] **Per-release SHA256SUMS + generated SBOM alongside the signed AppImage.**
  The release AppImage is already Ed25519-signed (FIBR-0054 INV-14). Add, per release: a SHA256SUMS file (artifact checksums) and a generated SBOM (CycloneDX via cyclonedx-py, or pip-audit output) listing the bundled dependency versions — supply-chain transparency + a second integrity signal for users who verify manually rather than via the in-app updater. Wire into build-release-appimage.sh / the publish step. Deps: FIBR-0054 (release pipeline).
  **Layman:** Each download comes with a checksum file and a parts-list, so anyone can verify what's inside and that it wasn't tampered with.
  Kind: security.
  Source: claude-suggestion-2026-07-11.

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
  Split 2026-07-15: the recurring/subscription-detection half is now FIBR-0142 (active, being built first per user pick). This bullet stays as the budgets tracking item (per-category monthly limits + over-budget dashboard signalling) — the follow-up after FIBR-0142 ships.

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

- ✅ [FIBR-0035] **Auto-categorisation that learns from corrections.**
  Extends the FIBR-0010 rules engine: when the user manually re-files a
  transaction (e.g. "TESCO" → Groceries), offer to create or update a rule
  so similar future transactions self-categorise — the tedious part gets
  quieter the more the app is used. Always a **suggestion** the user
  confirms (never a silent auto-rule), and a manual override still wins
  over any learned rule (FIBR-0010's invariant). Target phase: P08
  (extends the rules engine). Dependencies: FIBR-0010. Lanes: services,
  ui, tests. Kind: feature. Source: user-request-2026-07-01.
  Note (2026-07-09): the core learn-from-corrections behaviour (offer to *create* a rule from a manual correction; suggestion-only; manual override still wins) is pulled forward into FIBR-0010 (spec INV-5 / D11), per the 2026-07-09 user request. FIBR-0035's "*update* an existing rule" variant is subsumed by FIBR-0010 D6 (a learned rule inserts at top priority, beating the rule it corrects — no in-place update needed). Re-evaluate / close this bullet when FIBR-0010 ships.
  Resolved (2026-07-10): fully delivered by FIBR-0010. The create-a-rule-from-a-correction learning is FIBR-0010 INV-5/D11; the update-an-existing-rule variant is subsumed by D6 (a learned correction inserts at top priority, beating the rule it corrects — no in-place update needed). Suggestion-only + manual-override-wins guarantees both hold. No separate work remains.

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
  Note (FIBR-0054): when this disclaimer copy is written, phrase "local-only" as **data-locality** ("your financial data stays on your machine"), not "never connects" — the opt-in updater is a consented outbound exception, so a bare "local-only" shown on-screen would mislead.
  Kind: feature.
  Source: user-request-2026-07-03.
  Coordination note update: FIBR-0051 (P07.5) ships only a minimal About (QMessageBox.about) and puts donate links in their own Donate menu — it does NOT build the shared About/Help screen. So this bullet still owns building that screen (disclaimer + "Report an issue" link); the old "whichever of FIBR-0039/0040 ships first builds the screen" pact no longer applies.

- ✅ [FIBR-0040] **In-app donate / support links.**
  Clickable support links that open each FUNDING.yml sponsor page in the user's browser — GitHub Sponsors (milnet01), Patreon (AntsProjectsHub), and the Paybru tip URL (https://paybru.co.za/tip/ants-projects-hub). Surfaced in the About/Help dialog and a Help-menu entry. Keep the URLs in one place in sync with .github/FUNDING.yml (a small constants module or read at build time) so they never drift. Shares the About/Help screen with the disclaimer item.
  **Layman:** Buttons in the app that open the pages where people can support the project financially.
  Kind: feature.
  Source: user-request-2026-07-03.
  Being delivered by FIBR-0051 (P07.5 app-shell, spec in cold-eyes): its Donate menu ships all three FUNDING.yml links + the sync check (FIBR-0051 INV-8a). Flips ✅ when FIBR-0051 ships (FIBR-0051 DoD #6). Note the placement differs from this bullet's "About/Help dialog + Help menu" — FIBR-0051 uses a dedicated Donate menu.
  Resolved (2026-07-09): delivered by FIBR-0051's Donate menu — the three .github/FUNDING.yml links (GitHub Sponsors/Patreon/PayBru) via QDesktopServices.openUrl + the INV-8a sync check that fails on drift. Placement is a dedicated Donate menu rather than the About/Help dialog; same substance.

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

- ✅ [FIBR-0048] **User-configurable date-display format (Settings).**
  Belongs with FIBR-0014 (P12 Settings). The ISO yyyy/MM/dd default already shipped; this promotes it to a user choice persisted in the vault settings.
  **Layman:** Let the user pick how dates are shown (e.g. DD/MM/YYYY, YYYY-MM-DD) instead of the fixed ISO default.
  Kind: feature.
  Source: user-request-2026-07-04.
  Resolved (2026-07-11): subsumed by FIBR-0083, which shipped the user-configurable date-display format (plus timezone + time format) as its date half. No separate work remains.

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

- ✅ [FIBR-0059] **Edit a logged statement — re-assign its account (and its transactions) to fix an import mistake.**
  User request 2026-07-09: after importing an SBSA credit-card statement that got
  linked to "Current", the user wants to correct an already-logged statement's account
  in place. Scope: a "Change account" action on the Statements tab (FIBR-0052) that
  opens an account picker and atomically re-points BOTH statement_periods.account_id
  AND every linked transactions.account_id (WHERE statement_period_id = id) to the
  chosen account — one service-owned BEGIN…COMMIT (mirrors delete_statement's atomic
  pattern), leaving manual + other statements' rows untouched, ROLLBACK on failure.
  Refreshes the Statements list + Home + the status count (changed signal). The target
  account must exist (the user creates "Credit Card" in the Accounts tab first if
  needed). Also the tool that lets the user fix any statement mis-linked by FIBR-0057
  (the import account-snapshot bug). Deps: FIBR-0052 (Statements tab + provenance
  column). Next: spec -> /cold-eyes -> TDD -> /close-phase.
  **Layman:** Lets you correct a statement you already imported — e.g. change it from Current to Credit Card — without deleting and re-importing. It moves the statement and all of its transactions to the account you pick.
  Kind: feature.
  Source: user-request-2026-07-09.
  Resolved (2026-07-09): a "Change account" action on the Statements tab. StatementService.reassign_account(period_id, new_account_id) atomically re-points statement_periods.account_id AND every transaction stamped with it (one owned BEGIN…COMMIT mirroring delete_statement; ROLLBACK to a re-openable vault). A span-collision guard runs BEFORE BEGIN (pure read + refuse) with a period_id self-exclusion, so a same-account pick is the INV-5 no-op, not a false refusal; a real collision (target already has that span) raises ValueError → a tr() warning. A DISTINCT reassigned signal (the changed handler hard-codes "Statement deleted") drives a "Statement account changed" status via a shared refresh helper. New AccountPickerDialog (preselects the current account, deleteLater'd). StatementRow += account_id; repos get()/set_account()/reassign_account() (commit-free); no schema change (reuses the v6 provenance stamp). Spec /cold-eyes-converged in 6 cold loops (2 lanes = 12 reviews; design stable since loop 2). TDD 14 tests. Close: /audit 0; /indie-review 2 cold lanes — data/service CLEAN, UI/shell 1 LOW (undisposed picker dialog) folded inline. Gate green 366 passed/1 skipped; FIBR-0059 src mypy-clean. Also filed FIBR-0061 (mypy not enforced in the gate + 4 pre-existing test-file type errors, found during this close). Commits 2fc5a42 + review fold.

- 📋 [FIBR-0072] **Warn (or disable chrome) when navigating away from an in-progress import.**
  main_window._open_import() never disables the toolbar/menu, so clicking Home/Statements/Accounts/Categories/Rules mid-import silently rebuilds the workspace and destroys the in-progress wizard (chosen file, column mapping, unsaved preview) with no confirmation. Either confirm before discarding, or disable navigation chrome during an import (as locked states do).
  Kind: ux.
  Source: indie-review-2026-07-10 (M-shell1).

- 📋 [FIBR-0073] **Add keyboard mnemonics to menus + dialog labels (a11y sweep).**
  Menu titles (File/View/Window/Help/Donate) have no '&' Alt-accelerators; no dialog uses label mnemonics. Weakens keyboard-only navigation vs a typical desktop app (WCAG-adjacent). One focused sweep across main_window + the dialogs.
  Kind: accessibility.
  Source: indie-review-2026-07-10 (shell L1 + dialog INFO).

- 📋 [FIBR-0074] **Dedicated per-bank PDF readers for ABSA / Nedbank / FNB (needs real anonymised sample statements).**
  Today ABSA/Nedbank/FNB statements CAN already be imported two ways: (1) their CSV/OFX exports (most reliable), and (2) the generic PDF table-extractor (pdf_importer.py) for any PDF with ruled transaction tables, via the column-mapping step. A DEDICATED zero-config text-layer reader like standard_bank.py (auto-detect + no mapping) needs REAL anonymised sample statements per bank to build and validate — the SB reader (FIBR-0050) required 6 real statements to catch layout edge cases; synthetic dummy PDFs exercise code paths but don't validate real-world layouts. Blocked on the user providing (or the project sourcing) a few real anonymised statements per bank. Until then, the generic extractor + CSV/OFX cover these banks.
  **Layman:** Zero-config PDF import for the other big SA banks, the way Standard Bank statements already import without mapping columns.
  Kind: feature.
  Source: user-request-2026-07-10.

- ✅ [FIBR-0083] **User-configurable timezone + date/time display format (Settings).**
  Motivated by dogfooding v0.1.0: the Statements tab 'Imported' column shows a raw ISO UTC timestamp (e.g. 2026-07-11T06:49:15.506928+00:00). Extends FIBR-0048 (user-chosen DATE-display format) to also cover the user's TIME ZONE and TIME-of-day format, so any timestamp renders in the user's zone + preferred format. Belongs with FIBR-0014 / FIBR-0055 Settings; the prefs persist in the vault settings (like the auto-lock timeout). Render via QDateTime + QTimeZone + QLocale (coding.md 5.2), consistent with FIBR-0017 QLocale formatting. Ships together with / absorbs FIBR-0048 (date half).
  **Layman:** Let a person pick their time zone and how dates and times are shown, so timestamps (like a statement's 'Imported' time) read in their local time and chosen format instead of a raw UTC value.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Resolved (2026-07-11): shipped via TDD in 4 slices — pure datetime_format formatter (format_date/format_timestamp, presets, "system" sentinel + INV-6 fallbacks); DateTimePrefs + AuthService persistence (vault settings, no schema change); Settings + first-run combos (shared ui/_datetime_prefs.py); display wiring (Statements Period/Imported, Home Date) + live push on Settings Save. 8 cold-eyes loops on the spec; full gate green.

- 📋 [FIBR-0084] **User-customisable table columns — resize, reorder, and remember per tab.**
  Motivated by dogfooding v0.1.0. Extends FIBR-0052 (which already remembers window geometry + last-active tab in the plaintext window.ini sibling) to per-table column state. Make each QTableView/QTreeView header user-resizable AND movable (QHeaderView.setSectionsMovable(True)); persist each table's full header state (column widths + order) via QHeaderView.saveState()/restoreState(), keyed per tab, in the plaintext window.ini (non-sensitive UI state, like geometry — FIBR-0052 INV-5; NOT the vault). Covers every relevant table: Statements, Home transactions, Accounts, Categories, Rules. A Reset-layout action (FIBR-0052) should also clear saved column state.
  **Layman:** Let a person drag columns wider or narrower and drag them into a different order on any table (Statements, Home, Accounts, Categories, Rules), and have finbreak remember that layout next time.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).

- 📋 [FIBR-0085] **Batch statement import — import several statement files in one go.**
  Motivated by dogfooding v0.1.0. Today the import wizard handles ONE file per run (FIBR-0007 CSV / FIBR-0008 OFX / FIBR-0009 PDF). Add multi-file selection that runs each file through the existing preview -> dedup -> commit pipeline, with per-file semantics (a bad/duplicate file is reported and skipped, never aborting the batch) and a summary dialog listing each file's outcome (imported N / skipped-duplicate / failed-why) + transaction counts. Mixed formats (CSV/OFX/PDF) allowed in one batch; per-file mapping where the format needs it (CSV mapping profile selection, PDF password prompt). Reuses the existing importers + FIBR-0052 statement provenance; the new work is the multi-file wizard flow + aggregate reporting. Deps: FIBR-0007/0008/0009 (importers), FIBR-0052 (per-statement provenance so each imported file is a distinct statement row).
  **Layman:** Let a person select and import many statement files at once (e.g. a whole folder of monthly PDFs) instead of importing them one at a time.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).

- 📋 [FIBR-0086] **Account numbers + import auto-detect — match a statement to its account (prompt to create if new).**
  Motivated by dogfooding v0.1.0. Store an account number on each account — a new column in the ENCRYPTED vault (sensitive financial data, NOT the plaintext window.ini; schema migration, currently v7 -> v8). On import, extract the statement's account number and match it to a configured account (normalised: strip spaces/dashes; match on TRAILING digits when the statement masks it, e.g. "xxxx1234"), auto-selecting the account instead of today's manual pick. Availability varies by format: OFX <ACCTID> (reliable), PDF printed number (the Standard Bank / generic parsers can surface it), CSV often carries none — so auto-detect is a SMART DEFAULT with a manual fallback whenever the number is absent or matches zero/multiple accounts (never silently import to the wrong account — cf. FIBR-0059). When the detected number matches no account, prompt to create one, pre-filled from statement metadata (number, bank name if printed, type/currency where available) and asking the user for the rest. ENABLER for FIBR-0085 (batch import) — auto-detect is what makes multi-file import usable (you cannot hand-map a folder of files); reduces reliance on FIBR-0059 (change-account fix). Deps: FIBR-0005 (accounts), FIBR-0007/0008/0009 (importers must surface the statement's number), FIBR-0052 (statement provenance).
  **Layman:** Give each account its account number so importing a statement automatically files it under the right account — and if it's an account finbreak hasn't seen, it offers to create it, pre-filled from the statement.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).

- 📋 [FIBR-0087] **Per-account currency — support offshore/foreign-currency accounts in the portfolio (revisits FIBR-0021).**
  The user wants to include an offshore account in their portfolio — the "real multi-currency need" FIBR-0021 deferred to (it chose single base_currency for v1, set at first-run, and said revisit when this arises). Per FIBR-0021's own "if revisited" note: add a currency column on accounts (default = the vault base currency), CHOOSE the currency when ADDING an account (the user's ask), QLocale-format each amount in its account's currency, and enforce that the dashboard NEVER sums across currencies without explicit conversion. Needs its OWN design/spec — the hard decisions: (a) consolidated totals across currencies — NO live FX rates (that would widen the network surface beyond the one FIBR-0054 update egress), so either per-currency subtotals or a user-entered/stored conversion rate; (b) how the dashboard presents mixed currencies (per-currency subtotals vs one converted total). Schema migration (currently v7 -> v8). Deps: FIBR-0005 (accounts), FIBR-0012 (dashboard totals). Kept SEPARATE from FIBR-0083 (date/time formatting).
  **Layman:** Let each account have its own currency (e.g. a USD offshore account alongside your ZAR accounts), chosen when you create the account, so foreign accounts show and total correctly.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Consolidation design (proposed direction, user Q 2026-07-11 "how do mixed-currency statements consolidate into graphs/summaries?"): NO live FX rates (offline posture — only the FIBR-0054 updater egress). Default = per-currency subtotals: the dashboard shows each currency separately (ZAR panel, USD panel), NEVER summing across currencies (upholds FIBR-0021's rule). PLUS an optional USER-ENTERED exchange rate (stored in the vault) that converts everything to the base currency for a single consolidated total + unified graphs, always LABELLED "converted at your rate, entered <date>" so it's never mistaken for a live figure; user updates it at will. Warrants a small ADR ("how finbreak handles FX") when built. Rejected: live-rate fetch (breaks offline).

- 📋 [FIBR-0088] **Detect an already-imported statement up front (content hash) — warn before re-importing.**
  User wants an early 'already imported?' check that short-circuits BEFORE the per-transaction dedup (saving redundant work). Partly plumbed already: statements store source_filename and statement_periods has id_for_span (account+period existence check). Robust key = a CONTENT HASH (SHA-256 of the file bytes): detects a re-import of the IDENTICAL file regardless of filename — filename alone is unreliable (same file renamed; or two different files both named 'statement.pdf'). Add a file_hash column (schema migration, currently v7), compute it at import start, and if it matches a prior import WARN the user with an import-anyway option (a corrected re-issue is a legit re-import) rather than silently skipping. The existing account+period match (id_for_span) is a softer secondary signal. COMPLEMENTS, not replaces, transaction dedup (INV-6), which still catches overlapping-but-different files. Primarily a UX safeguard against accidental re-import; the CPU saving is a bonus. Also gives FIBR-0085 (batch import) its per-file 'already imported -> skipped' outcome. Deps: FIBR-0007/0008/0009 (importers), FIBR-0052 (statement provenance).
  **Layman:** When you import a statement finbreak has already seen, it tells you up front ('looks like you already imported this') instead of silently re-processing it.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).

- 📋 [FIBR-0089] **Backup safety nudge — first-run emphasis + a 'last backup was N days ago' reminder.**
  The encrypted-backup MECHANISM is planned in FIBR-0014; this is the SAFETY UX around it. ADR-0003: no password recovery = permanent data loss, so a backup is the only mitigation. Add (a) first-run copy stressing 'back this up somewhere safe', and (b) a gentle, non-blocking reminder when the last backup (tracked via a vault-settings timestamp) is older than a threshold. Depends on / complements FIBR-0014 (the export itself). Highest-value safety improvement per the 2026-07-11 review.
  **Layman:** Because a forgotten master password means your data is gone for good, finbreak reminds you to keep a backup — stressed at first run and gently nudged if it's been a while.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0090] **Split a transaction across multiple categories.**
  A personal-finance staple. One transaction carries N category allocations summing to its amount. Affects the categorization model (per-transaction allocations, not a single category_id) and the dashboard totals (aggregate by allocation, not whole-transaction). Schema change (an allocations/splits table). Deps: FIBR-0006 (categories), FIBR-0010 (categorization), FIBR-0012 (dashboard totals must respect splits). Own spec.
  **Layman:** Split one purchase across categories — e.g. a R1,200 shop = R900 groceries + R300 household — so your breakdowns are accurate.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0091] **Free-text notes + tags on transactions.**
  A free-text note and/or tags (labels) per transaction, orthogonal to the category tree. Enables richer filtering/reporting in the dashboard's filterable table (FIBR-0012). Schema: a note column + a tags table (many-to-many). Deps: FIBR-0012 (filters), FIBR-0052 (transactions). Own spec.
  **Layman:** Attach a note or tag ('reimbursable', 'holiday 2026') to a transaction for context the category tree can't hold, and to filter/report on.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0092] **Rule preview (what will it match?) + bulk re-categorize selected transactions.**
  Enhances FIBR-0010's rules engine + the categorization UX. (a) Rule preview: on rule create/edit, show the matching transactions (the would_categorize primitive already exists, FIBR-0010) before commit. (b) Bulk action: multi-select rows in the Home/transactions table -> set category (and optionally offer to make a rule). Pairs with FIBR-0084 (column/row UX) and FIBR-0012 (filterable table). Deps: FIBR-0010. Mostly UI + reuse of existing services.
  **Layman:** When you write a categorisation rule, see which transactions it'll catch before saving; and select many rows to set their category at once.
  Kind: enhancement.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0093] **Plain data export — CSV / spreadsheet of your categorised transactions.**
  A 'File -> Export data' that writes the (filtered) transactions — date, amount, description, account, category, notes/tags — to CSV (and optionally XLSX). Complements the report-style PDF export (FIBR-0013): this is RAW DATA for spreadsheets, not a formatted report. Local file write, no network (offline posture holds). Deps: FIBR-0007/0008/0009 (the data), FIBR-0012 (filters define the export scope). Own small spec.
  **Layman:** Export your categorised transactions to a CSV/spreadsheet for your own analysis or your accountant.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0094] **Account balances + net-worth over time (opening balance + running balance).**
  Today finbreak tracks TRANSACTIONS, not balances. Add a per-account opening balance (+ as-of date); derive a running balance per transaction; surface an account-balance and consolidated net-worth trend on the dashboard. Interacts with FIBR-0011 (transfers — moving money between your own accounts must not change net worth) and FIBR-0087 (multi-currency net worth needs the FX decision). Schema: opening_balance on accounts. Deps: FIBR-0011, FIBR-0012, FIBR-0087. Bigger; own spec + likely an ADR on balance derivation.
  **Layman:** Track each account's balance over time — set an opening balance and finbreak shows running balances and your overall net-worth trend, beyond just spending-by-category.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0100] **Undo for destructive actions (delete statement / delete category).**
  Today destructive actions are confirm-only (Statements delete with its transactions, FIBR-0052; category delete-cascade, FIBR-0010). Add a short-lived undo — a status-bar 'Deleted — Undo' for a few seconds, or Edit -> Undo — that restores the deleted rows within the same session. Friendlier than confirm-only; reduces fear of the delete buttons. Design: soft-delete or an in-memory undo stack + a re-insert. Deps: FIBR-0052, FIBR-0010.
  **Layman:** An 'undo' right after deleting a statement or category, so a misclick isn't permanent.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0101] **Keyboard-first categorising — shortcuts for fast triage of a big import.**
  Add keyboard shortcuts to the transaction table: set-category (opens the picker), jump-to-next-uncategorised, and quick-assign recent categories. Speeds triaging a large import. Pairs with FIBR-0092 (bulk re-categorize) and FIBR-0010 (rules); cleaner once FIBR-0097 (model/view) lands. Mostly UI. Deps: FIBR-0010.
  **Layman:** Categorise a large import quickly with the keyboard — set a category and jump to the next one without reaching for the mouse.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- ✅ [FIBR-0105] **User-configurable amount display: negative sign style + colour (Settings).**
  Two independent prefs persisted in the vault settings (mirrors FIBR-0083
  DateTimePrefs / FIBR-0055 auto-lock): (1) negative-amount style — "minus"
  (−ZAR25,000.00) vs "brackets" ((ZAR25,000.00), today's QLocale default); (2)
  colour amounts on/off — money-out red, money-in green. Settings + first-run
  controls; applied at the Home transactions table's Amount column (the only
  amount display today). Default: minus + colour ON. Display-only (never mutates
  stored data). Ships in v0.1.5 alongside the inline update notes.
  **Layman:** Let a person choose how money amounts look — negatives as a minus sign (−R25) or in brackets (R25), and turn on/off colouring money-out red and money-in green — so the transaction list reads the way they prefer.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.4: "why are some values in brackets?" → make it a Settings choice).
  Resolved (2026-07-11): TDD-built in 4 slices — AmountPrefs + AuthService.amount_prefs/set_amount_prefs (INV-2/5); _format_amount explicit sign (- / ()) locale-independent + _NEGATIVE_TEXT/_POSITIVE_TEXT colour in HomeView (INV-1/3/4); Settings combo + colour checkbox and first-run mirror (INV-6/7); shell reads/passes/re-pushes on Save. 19 new tests; full gate green (598 passed). Lands on main; publishes in v0.1.5 (bundled with the inline update notes).

- ✅ [FIBR-0106] **Credit-card (Family C) import: opening balance mis-read from a prose "brought forward" decoy line.**
  Root-caused (verified against a real SBSA CC statement, synthetic fixture to
  follow — real file/password never committed). `_cc_opening` (standard_bank.py
  :812) returns the LAST money token on the FIRST line containing "balance
  brought forward". A credit-in-hand statement prints a prose summary line
  "...has a credit balance. Balance brought forward on this statement -251.85"
  BEFORE the real opening line "21 Jul 25 Balance Brought Forward 6,849.68", so
  it grabs -251.85 (which is actually the CLOSING balance carried to the next
  statement). Checksum then fails: reconciled = opening - Σ = -251.85 - 7101.53
  vs closing -251.85. With the correct opening 6,849.68 it reconciles exactly
  (6849.68 - 7101.53 = -251.85 = closing). Fix: anchor the match so the phrase
  is at line start (optionally after a `DD Mon YY` date) with the amount
  immediately after — the prose sentence won't match. TDD with a synthetic
  fixture carrying the decoy line + a real opening + a reconciling body.
  **Layman:** A real Standard Bank credit-card statement refused to import ("didn't add up") because the importer read the wrong opening balance.
  Kind: fix.
  Source: dogfooding-2026-07-11.
  Resolved (2026-07-11): anchored _cc_opening on a new _CC_BROUGHT_FORWARD regex requiring a money amount to IMMEDIATELY follow the "balance brought forward" phrase (optional -/R sign), and take the first money token in the tail from the phrase onward. The prose decoy ("...credit balance. Balance brought forward on this statement -251.85") has narrative text between phrase and figure, so it no longer matches; the real anchor "21 Jul 25 Balance Brought Forward 6,849.68" does. TDD: 2 pure unit tests (decoy-rejection + printed-negative-sign preservation) in tests/features/standard_bank_pdf; full SB suite (50) green, no regression on the 6 validated real statements. Gate green (600 passed/1 skipped). Synthetic figures only — real file/password never touched disk.

- ✅ [FIBR-0107] **Self-update relaunch: wait for the old AppImage to exit before launching the new one.**
  The 0.1.4→0.1.5 relaunch (detached Popen + PYINSTALLER_RESET_ENVIRONMENT, then immediate os._exit) still raced the old AppImage's teardown: the fresh onefile bootloader started while the old image's FUSE mount + _MEI extraction dir were still live and died ("closed but didn't reopen"). Fix (update_installer.py): spawn a detached /bin/sh WAITER (new session) that polls `kill -0 <old-pid>` until this process has fully exited — FUSE unmounted, _MEI cleaned — and only THEN execs the swapped image with the reset env. Hard ~60s cap (600 × 0.1s) so a wedged old process can never hang the relaunch. Same pattern robust self-relaunching Qt AppImages (RPCS3, PCSX2) use. Added a diagnostic relaunch log (data-dir sibling of the vault) capturing the waiter's + relaunched image's output so a future silent failure leaves evidence. TDD: pure _relaunch_command builder test (waits on pid, quoted exec after the loop), detached-session/env test updated to the waiter contract, log-write test; plus a real-process smoke proving the waiter blocks until the old pid dies then execs. Gate green (602 passed/1 skipped). NOTE (two-cycle trap): this code ships in 0.1.6 but only RUNS on the 0.1.6→next update — 0.1.5→0.1.6 still relaunches via the old 0.1.5 logic, so one manual reopen is still expected for that hop.
  **Layman:** After an update the app closed but didn't reopen; now it reliably restarts itself.
  Kind: fix.
  Source: dogfooding-2026-07-11.

- 📋 [FIBR-0108] **Update download: show real progress instead of a permanently-full indeterminate bar.**
  The "Downloading…" bar in the update dialog is hardcoded to indeterminate (busy) mode — ui/update_dialog.py:79 `self._busy.setRange(0, 0)` — so it shows a moving/striped full bar the entire download rather than actual percent-complete. The fix is feasible without new deps: services/update_fetch.py `download()` already streams the body in 64 KiB chunks (`_DOWNLOAD_CHUNK_BYTES`, line 89), so it can (a) read the total from the response `Content-Length` header and (b) accept an optional progress callback invoked per chunk with (received, total). Then the DownloadWorker (ui/_update_worker.py) emits a progress signal and the dialog switches the bar to determinate (`setRange(0, total)` + `setValue(received)`), falling back to indeterminate only when Content-Length is absent/zero. Keep the byte-cap (max_bytes) guard intact. TDD: unit-test the callback fires with monotonic received ≤ total and a missing-Content-Length fallback; a qtbot test that the bar goes determinate on a known-size download. Kind: enhancement.
  **Layman:** While an update downloads, the progress bar looks full/striped the whole time instead of filling up as it downloads.
  Kind: enhancement.
  Source: dogfooding-2026-07-12.

- 📋 [FIBR-0109] **Move the Home transaction list to a dedicated Transactions tab with account / date-range / amount-range filters.**
  User request 2026-07-12. Today Home is the transaction table (HomeView). Move that table to its own Transactions tab and add filters: by account, by date range (from/to), and/or by amount range (min/max), combinable. This dovetails with FIBR-0012 (the dashboard's "filterable table" + Home-as-summary vision) and complements FIBR-0011 (a confirmed-transfer marker could later show here). Reuses the existing list_transactions read; the filter is a query/where layer. Dates in the filter follow the typed-or-picker rule below.
  **Layman:** Give the transaction list its own tab with filters for account, date range and amount, so the Home tab is freed to become a summary/dashboard.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Absorbed into FIBR-0012 (P10 dashboard) 2026-07-12: the Transactions tab is built there with search + date-range + account + category filters (all combinable). The amount-range (min/max) filter this bullet originally named was NOT chosen in the FIBR-0012 brainstorm and is DEFERRED (recorded in docs/specs/FIBR-0012.md Out-of-scope) — a clean future follow-up. Close this bullet when FIBR-0012 ships; re-open a fresh item only if the amount-range filter is still wanted.

- 📋 [FIBR-0110] **Every date input accepts typed entry (validated) or a date picker.**
  User request 2026-07-12. Cross-cutting UX: wherever a date is entered — the manual-entry dialog, the future Transactions filters (above), any settings/import date field — offer both a typed field (ISO-validated, the existing parse_transaction date check) and a QDateEdit-style calendar picker, so neither typists nor mouse users are forced. A shared date-input widget/helper so the two modes stay consistent (Rule-of-Three: extract on the third site).
  **Layman:** Anywhere you enter a date in the app, you can either type it (with a check that it's a real date) or pick it from a small calendar.
  Kind: ux.
  Lanes: ui.
  Source: user-request-2026-07-12.

- 📋 [FIBR-0111] **Show the currency in its own column, separate from the amount value.**
  User request 2026-07-12 (screenshot): the Home Amount column renders "ZAR69.00" / "-ZAR25,000.00" with the currency crammed against the number, hard to read. Give the currency its own column (or right-align the bare number and show the currency code separately), so the value column holds just the formatted number + sign. Touches HomeView._format_amount / the Amount column layout (FIBR-0105 amount-display work) and should carry through to the future dedicated Transactions tab (FIBR-0109). Keep the negative-style (minus/brackets) + red/green colour prefs (FIBR-0105) working on the value column.
  **Layman:** Put the currency code (e.g. ZAR) in its own column so the number is easy to read, instead of "ZAR69.00" crammed together.
  Kind: ux.
  Lanes: ui.
  Source: user-request-2026-07-12.

- ✅ [FIBR-0112] **Credit-card (Family C) import: continuation page without a column header drops its transactions.**
  Root-caused against a real SBSA CC statement (2025-10-20; real file/password never committed, synthetic fixture/tests to follow). A 3-page statement: page 1 = summary, page 2 = transaction table WITH the "Date Description Amount" column header, page 3 = continuation transactions with NO column header (opens straight into a "Debit Debit" section). _table_region (standard_bank.py:229) locates the Family-C region only by that column header, so page 3's region is empty and its 3 transactions (Checkers 514.21 + Cash Finance Charge 23.05 + Tips 10.00 = 547.26) are silently dropped. The completeness checksum then fails (opening 1348.95 - Σ = 1421.51 vs closing 1968.77; the 547.26 gap is exactly the dropped rows) and the whole statement is refused. Fix: when a Family-C page has no column header, fall back to starting the region at the first real transaction row (a CC segment ending in a 2-decimal amount) — which excludes summary-page date spans like "Statement Period 20 Sep 25 to 20 Oct 25" that carry no 2-decimal tail. TDD: pure _table_region unit tests (header-less continuation page captured; header-less summary page stays empty) + reconciliation; validated end-to-end against the real statement in a throwaway scratchpad.
  **Layman:** Another real Standard Bank credit-card statement refused to import ("didn't add up") because the last page's transactions were being skipped.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): _table_region now falls back, on a Family-C page with no "Date Description Amount" column header, to starting the region at the first real transaction row (a CC segment ending in a 2-decimal amount — which excludes summary-page date spans like "Statement Period 20 Sep 25 to 20 Oct 25"). TDD: 2 pure _table_region unit tests (header-less continuation page captured; header-less summary page stays empty). Validated end-to-end on the real SBSA 2025-10-20 statement in a throwaway scratchpad: now 72 drafts, reconciles exactly (1348.95 - (-619.82) = 1968.77 = closing); the 3 previously-dropped page-3 rows (Checkers 514.21, Cash Finance Charge 23.05, Tips 10.00 = 547.26) are captured. Full SB suite + gate green (604 passed/1 skipped). Real file/password never committed; tests are synthetic. Note: a pre-existing cosmetic issue remains (a "Continued on next page......" line folds into the last page-N transaction's description) — filed separately, not this fix.

- 📋 [FIBR-0113] **Accounts tab: show accounts in columns (Name / Type / Account number / Note) instead of one line.**
  User request 2026-07-12 (screenshot): the Accounts tab lists each account as one line "Credit Card — Credit card" (name — type). Move to a columnar QTableWidget with columns: Name, Type of account, Account number, Note (optional). Requires two NEW nullable account fields — account_number and note (schema bump) — plus the add/edit form growing those inputs and the AccountsWidget becoming a table (mirrors the Rules/Statements tab table shape). Account number is display/reference only (not used for matching). Dovetails with the columnar direction of FIBR-0109 (Transactions tab) and the account credential accessors already on the accounts repo (FIBR-0009).
  **Layman:** Show accounts in a proper table (Name, Type, Account number, and an optional Note) instead of a single cramped "Name — Type" line each.
  Kind: feature.
  Lanes: ui, repo.
  Source: user-request-2026-07-12.

- ✅ [FIBR-0114] **Auto-lock should be an inactivity timer (reset on user activity), not an absolute timer from unlock.**
  User report 2026-07-12. AuthService._arm_timer (auth.py:241) starts a single-shot QTimer at unlock (and only re-arms on a settings change), so the auto-lock fires a fixed duration after UNLOCK regardless of activity — locking mid-use. Fix: make it an inactivity timer. Add AuthService.notify_activity() that restarts the running timer with its existing interval (no settings re-read, since it fires on every input event; no-op when locked/headless), and have MainWindow install an application-level event filter that calls notify_activity() on user-input events (MouseButtonPress/MouseMove/KeyPress/Wheel). TDD: service-level (notify_activity restarts the running timer when unlocked, no-op when locked) + shell-level (eventFilter calls notify_activity on an input event).
  **Layman:** The screen-lock countdown ignored whether you were actively using the app — it locked a fixed time after unlocking even mid-use. It should count from your last interaction.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): added AuthService.notify_activity() — restarts the running idle timer with its armed interval (no settings re-read; no-op when locked/headless) — and MainWindow now installs an application-wide event filter that calls it on MouseButtonPress/MouseMove/KeyPress/Wheel. The auto-lock now counts from the last interaction, not from unlock. TDD: 2 service-level tests (restart-when-unlocked via a spy timer; no-op-when-locked) + 1 shell-level test (a KeyPress through the app filter calls notify_activity). Gate green (607 passed/1 skipped), mypy/ruff/bandit/gitleaks clean.

- 📋 [FIBR-0115] **Credit-card import: strip the "Continued on next page" footer from the last transaction's description.**
  Surfaced while fixing FIBR-0112 (not that bug — amounts/checksum are unaffected). On a multi-page Family-C statement, the in-region "NNNN Continued on next page......" line has no transaction date, so _fold/_parse_family_c folds it into the PRECEDING transaction's description (e.g. "# International Txn Fee 0453155796 Continued on next page......"). Cosmetic data-quality issue affecting one row per page break. Fix: treat a line matching a "Continued on next page" / bare account-number footer as a skip line (like the "Debit"/"Credits" section headers in _is_cc_skip_line), not a description continuation. TDD with a synthetic fixture line.
  **Layman:** On multi-page credit-card statements, one transaction's description gets a stray "Continued on next page..." tacked onto it. Cosmetic only — the amounts are correct.
  Kind: fix.
  Source: dogfooding-2026-07-12.

- ✅ [FIBR-0116] **Toolbar icons: muted theme-aware colour that brightens to vibrant on hover.**
  User request 2026-07-12: the toolbar glyphs are currently a single flat mid-grey (#808080, hand-authored monochrome SVGs loaded by ui/icons.py `icon()`; the toolbar is ToolButtonTextUnderIcon). Wanted: (1) each icon a MUTED colour by default, (2) the icon brightening to a VIBRANT version of that same hue while the mouse hovers, reverting on leave, and (3) colours chosen per the active theme (light/dark). Approach sketch: give each glyph a semantic accent colour, then re-tint at load time — either recolour the SVG per state (parse `stroke="#808080"` → muted/vibrant/theme variants and build a QIcon with Normal/Active pixmaps so Qt swaps to the Active pixmap on hover automatically), or drive it via a QProxyStyle / event-filter on the toolbar buttons. Theme-awareness ties into the theme system FIBR-0014 builds (dark/light/follow-system) — coordinate so the muted/vibrant palettes have a light AND dark variant. Related: FIBR-0014 (palette-adaptive re-tinting / dark-theme polish) — this is the specific hover-brighten behaviour, keep them cross-referenced. Icons live in src/finbreak/ui/icons/*.svg; loader is src/finbreak/ui/icons.py.
  **Layman:** Give the toolbar buttons gentle colour that lights up brightly when you point at one, and dims back when you move away — and pick colours that suit the current light or dark theme.
  Kind: enhancement.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): toolbar_icon() recolours each hand-authored SVG at load — a per-icon muted semantic hue at rest (QIcon Normal) + a vibrant one on hover/focus (QIcon Active/Selected, Qt's built-in hover swap, no event filter), tuned to the active light/dark theme via the app palette. 8 glyphs each get a calm distinct hue; _make_action uses it for toolbar + menus. Tests: Normal≠Active, theme-aware + hover more saturated, unmapped-glyph fallback. Ships in v0.1.7. Live theme-switch re-tint stays with FIBR-0014 (icons read the palette at build time).
  Live theme-switch re-tint is delivered by FIBR-0127 (the theme system): MainWindow re-runs toolbar_icon() for each icon'd action on the ThemeController's themeChanged signal, so the muted/vibrant glyphs re-tint to the new light/dark palette without a relaunch. The FIBR-0116 muted/vibrant seam (v0.1.7) is the mechanism; FIBR-0127 wires the live-on-switch trigger. (2026-07-14)

- ✅ [FIBR-0117] **Data tables: remember column widths + click-header-to-sort (toggle order on re-click).**
  User request 2026-07-12 (screenshot, Statements tab): the QTableWidget-based data tables should (1) REMEMBER column widths across sessions, and (2) allow clicking a column header to sort by that column, with a second click on the same header toggling ascending/descending. Applies to the Statements table and the other list tables (Rules, the FIBR-0011 Transfers tables, the FIBR-0113 Accounts table, Home). Approach: QTableWidget.setSortingEnabled(True) gives click-to-sort with the asc/desc toggle for free (note: with sorting on, populate rows then enable, and key numeric/date columns with a sortable value — e.g. QTableWidgetItem data role or zero-padded/ISO text — so "112" doesn't sort before "69" and dates sort chronologically). Persist column widths via QHeaderView.saveState()/restoreState() into the window INI (paths.window_settings_path, same store as geometry, NOT the vault — it is non-secret view state), keyed per-table by objectName. Requested for inclusion in the v0.1.7 release alongside FIBR-0011. Related: the columnar tables in FIBR-0111/FIBR-0113.
  **Layman:** Let the tables (Statements, and the other lists) remember how wide you've dragged each column, and let you click a column heading to sort by it — click again to flip between ascending and descending.
  Kind: enhancement.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): new ui/_table_state.py — SortableItem (numeric/date sort keys), enable_sorting, remember_columns (header saveState/restoreState → window INI keyed by objectName, not the vault), and a row-tag scheme (tag_row/selected_index/select_by_index) so an action maps to the correct row after a re-sort (the money-critical guard). Applied to Statements, Transfers, Home (click-sort + widths + persisted sort/direction; Home moved off all-Stretch to interactive+stretch-last). Rules keeps priority order (not sortable) but persists widths, per user choice. tests/features/table_state/ covers numeric sort, tag-survives-reorder, action-targets-sorted-row, and width+sort persistence across rebuild. Ships in v0.1.7.

- ✅ [FIBR-0118] **App icon: transparent (rounded) corners instead of a hard square tile.**
  User request 2026-07-12 (About-box screenshot): the app/window icon (the donut-on-dark-navy tile) has hard square corners that read as a solid block against the dialog background. Make the corners transparent — a rounded-rectangle alpha mask so the four corners are see-through. Regenerate the whole icon set from the 1024 master: apply the rounded-corner alpha to assets/icon/finbreak.png (or add the mask step in scripts/make-icons.sh), then re-run make-icons.sh to rebuild the Linux PNGs (16-512), the Windows .ico, the macOS .iconset, and the runtime src/finbreak/ui/icons/app.png. Keep the corner radius modest (~15-20% of the tile) so it matches platform icon conventions. Verify the About box + taskbar show transparent corners (QIcon/PNG alpha travels). Requested alongside the v0.1.7 polish batch. Related: FIBR-0037 (the branded app icon) + FIBR-0116 (toolbar-glyph colour).
  **Layman:** Round off the corners of the app icon so it doesn't show as a solid square block — the corners become see-through and blend into whatever's behind it.
  Kind: ux.
  Lanes: ui, packaging.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): make-icons.sh applies an 18%-radius rounded-rectangle alpha mask to the master once, deriving every size (Linux hicolor PNGs, Windows .ico, macOS .iconset, runtime app.png) from the rounded temp; master stays square. Regenerated the set; regression test asserts transparent corners + opaque centre. Refreshed the dogfood install's hicolor icons so the launcher shows it now; the About-box (embedded app.png) rounds on the v0.1.7 install. Ships in v0.1.7.

- ✅ [FIBR-0119] **Home Loan (Family B) import: page-break footer/letterhead folds into the previous transaction's description.**
  Root-caused against a real SBSA Home Loan statement (2026-02-28; real file/password never committed, synthetic fixture/tests to follow). On a multi-page Family-B statement, a page break prints the registered-office letterhead (bare account number, "Standard Bank Centre …", "P O Box …", "Tel. Switchboard: … Fax: …") plus a repeated column header ("Debit Credit Balance" / "Date Date Fee") BETWEEN two transactions. None of those lines carries a date+amount, so _fold (standard_bank.py:489) — which appends every non-row in-region line to the preceding transaction as a description continuation — glued the whole block onto the last transaction before it (e.g. "Insurance Premium 0453155796 Standard Bank Centre … Debit Credit Balance Date Date Fee"). Amounts/dates/counts are unaffected (54 drafts still reconcile), so it imported "successfully" with a corrupt description; it also makes dedup fragile across statements where the same transaction appears with different page-break pollution. Fix: a shared _is_boilerplate() predicate (bare account/reference number; SB registered-office/contact markers; a repeated column-header line whose tokens are all table-header words) that _fold drops instead of folding — generalising the existing _is_cc_skip_line Family-C rule. TDD: pure synthetic _parse_family_b test (footer+header block between two rows → clean descriptions) + re-validated the two real Home Loan statements (27 / 54 drafts, clean descriptions) and the full synthetic A/B/C/D suite. NOTE: the "27 new · 27 duplicate" the user saw importing the 2026-02 statement after the 2025-08 one is CORRECT — the 2026-02 statement restarts at 2025-03-01 (54 drafts = the 27 overlapping the first statement, deduped, + 27 new); no dedup bug.
  **Layman:** On a multi-page home-loan statement, one transaction's description got the whole page footer (bank address, phone/fax, column headers) glued onto the end — making it a paragraph long instead of a few words.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): added a shared `_is_boilerplate()` predicate (bare account/reference number; SB registered-office/contact markers — "standard bank centre"/"standardbank.co.za"/"P O Box"/"switchboard"/"fax"/registration/FSP; a repeated column-header line whose tokens are ALL table-header words) that `_fold` drops instead of folding into the preceding transaction — generalising the Family-C `_is_cc_skip_line` rule; the header-token set deliberately excludes ambiguous words (service/details/description/amount/reference) so a genuine wrapped description isn't mistaken for a header. TDD: pure synthetic `_parse_family_b` test (footer+letterhead+repeated-header block between two rows → clean descriptions). Re-validated the two real Home Loan statements (27 / 54 drafts, all descriptions clean incl. the formerly-polluted 2025-11-03 "Insurance Premium") + the full synthetic A/B/C/D suite. Gate green 656/1. The "27 new · 27 duplicate" the user saw was CORRECT (the 2026-02 statement restarts at 2025-03-01: 54 drafts = 27 overlapping the first import (deduped) + 27 new) — no dedup change.

- ✅ [FIBR-0120] **Data tables: drag-to-reorder columns, with the order persisted across sessions.**
  Extends the shared _table_state.remember_columns seam (FIBR-0117, which already
  saved/restored full header state incl. section order): enables setSectionsMovable
  on every table that calls it, so drag-reorder + persistence light up across all
  four data tables at once. Reordering is visual-only — the parallel-list row tag
  lives on logical column 0, so selection + sorting stay correct whatever the order.
  **Layman:** You can now drag a table's column headings to rearrange them (e.g. put Amount before Date), and the app remembers your arrangement next time — on the Transactions, Statements, Rules and Transfers tables.
  Kind: enhancement.
  Source: user-request-2026-07-12.

- 📋 [FIBR-0121] **Loan-account sign display: show debt-reducing amounts as positive on loan-type accounts.**
  Approach APPROVED by user (2026-07-13): DISPLAY-ONLY, display-time inversion for
  loan-type accounts (AccountType.HOME_LOAN / PERSONAL_LOAN). Keep amount_minor
  stored canonical (FIBR-0007: debit negative / credit positive) so the exact-money
  math, transfer detection, and the FIBR-0012 dashboard totals are all undisturbed;
  only the on-screen sign + direction colour flip for loan accounts. Scope is
  display-only for now (NOT changing how loan flows count in dashboard totals) — a
  deeper "interest-as-expense / repayment-as-transfer" semantic is a possible later
  follow-up.
    Needs its own spec + the project's 7-loop cold-eyes (correctness-critical money
  display). OPEN QUESTION to verify during that spec (do NOT assume): how the
  importer currently signs loan-statement debit/credit columns, and whether transfers
  INTO a loan are being detected at all (the loan-payment leg and its current-account
  leg may currently share a sign, which opposite-sign transfer matching would miss).
  If a real detection gap exists, split it out as a bug-fix. Touches ui/_amount.py +
  the Transactions table render; the account type is on models.Account.type.
  **Layman:** On home-loan / personal-loan accounts, your payments (which reduce what you owe) will read as positive/green and interest &amp; fees (which increase what you owe) as negative/red — the natural way round, instead of the current back-to-front look.
  Kind: feature.
  Source: user-request-2026-07-12 (approved 2026-07-13).

- ✅ [FIBR-0122] **Auto-update relaunch: stop the /bin/sh waiter inheriting the frozen app's bundled-library path.**
  Root cause (from update-relaunch.log): the relaunch /bin/sh waiter inherited the
  PyInstaller onefile app's LD_LIBRARY_PATH pointing at its private _MEI extraction
  dir, so the SYSTEM /bin/sh loaded the app's bundled libreadline.so.8 and died on a
  symbol lookup (rl_completion_rewrite_hook) BEFORE it could relaunch — the real cause
  of "closed but didn't reopen". Fix: _relaunch_env restores LD_LIBRARY_PATH / LD_PRELOAD
  to the pre-launch value PyInstaller preserves in <VAR>_ORIG (or drops them when there
  was none), so the waiter runs against system libraries; the exec'd AppImage sets up
  its own loader path. TDD: 2 unit tests (restore-from-ORIG + drop-when-absent). Ships
  in the next release. TWO-CYCLE CAVEAT: the *running* (old) version performs each
  relaunch, so 0.1.7→(this release) still needs one manual reopen; the update AFTER it
  is the true auto-relaunch test — same caveat as the earlier relaunch fixes (FIBR-0054).
  **Layman:** After an update the app should reopen itself; it was silently failing to. Fixed so the little helper that reopens it runs with the system's own libraries instead of the app's bundled ones.
  Kind: fix.
  Source: user-report-2026-07-13 (0.1.6→0.1.7 did not auto-relaunch).

- ✅ [FIBR-0123] **Group category pickers by Income/Expenditure type (disambiguate same-named categories).**
  The category pickers (Set-category dialog `ui/category_picker.py`, the Rules editor `ui/rules.py`, and the Transactions category filter) flatten the two-root Income/Expenditure category tree (FIBR-0006) into one flat combo, so: (1) you can't tell an income category from an expenditure one at pick time, and (2) two categories that share a name under different Type roots are indistinguishable — real dogfooding case 2026-07-13: the seeded income "Lottery" plus a user-added expenditure "Lottery" render as two identical rows. Fix: group each combo under non-selectable "Income" / "Expenditure" section headers (or an equivalent grouped/indented presentation) so the Type is obvious and same-named siblings are unambiguous. The category *manager* already shows the tree grouped; this is only the flat picker combos. Known-deferred shortcut, recorded at the FIBR-0010 close ("category selectors are flat combos, grouping deferred").
  **Layman:** When you pick a category, show which options are income and which are expenditure — and make two categories that share a name (e.g. an income "Lottery" for winnings and an expenditure "Lottery" for tickets) tell-apart-able instead of two identical rows.
  Kind: ux.
  Source: dogfooding-2026-07-13.
  Resolved (2026-07-13): shipped by TDD (6 slices) + 1 indie-review LOW fixed inline (parent-cycle guard). Grouped pickers/filter under Income/Expenditure headers, Name (Type) tag; audit 0, gate green. Tag FIBR-0123-complete.

- ✅ [FIBR-0136] **Add the missing Statements toolbar icon + button.**
  Statements shipped (FIBR-0052) text-only and absent from the toolbar — reachable only via the View menu, where it also lacked a glyph unlike its neighbours. Added ui/icons/statements.svg (Feather file-text style matching the icon set), wired it into _action_statements (was icon=None), and added the action to the toolbar after Transactions to mirror the workspace tab order. Reverses the FIBR-0052 "Statements not on the toolbar" test assertion by explicit user request; the statements/app_shell tests were updated (toolbar order now includes action_statements; a rendering-icon + toolbar-membership test added). Kind: fix.
  **Layman:** Give the Statements screen its own button with an icon in the toolbar (it was only reachable from the View menu before, and even there it had no icon).
  Kind: fix.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14) — commit eb52443. statements.svg added, wired into _action_statements + the toolbar after Transactions; tests updated. Gate green 862/1.

- 💭 [FIBR-0137] **Business / Personal account grouping — separate views within one profile.**
  Today the model is one profile per logged-in user with a single, flat account list; every view (Home dashboard, Transactions, Accounts) spans all accounts at once. An external tester runs both business and personal accounts and wants to view each set separately WITHOUT a second profile/login.

  Investigate: (a) an account "group" attribute — fixed Business/Personal, or user-defined groups — as a nullable column on accounts (no migration pain, defaults ungrouped); (b) a group filter/toggle shared across Home, Transactions and Accounts (reuse the existing account-selector pattern in HomeView); (c) whether dashboard totals should roll up per-group; (d) how this interacts with the (planned) expandable dashboard and with transfer-detection across groups. Keep the single-profile design — this is a view/grouping concern, not multi-user.

  Source: user-request-2026-07-14 (friend / external tester).
  **Layman:** Let someone tag each account as Business or Personal (or custom groups) and view the two separately, so a person with both kinds of accounts keeps them apart while still staying under one login.
  Kind: investigate.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0138] **Expandable dashboard drill-down (Income / Spending / Transfers → categories → merchant → transactions).**
  Designed in-session 2026-07-14 (three user-approved brainstorm decisions). Enhances the FIBR-0012 dashboard: keep the donut + 12-month trend charts as the snapshot, add an expanding tree below them that drills the numbers.
  Spec written (docs/specs/FIBR-0138.md) 2026-07-14; /cold-eyes next.
  Spec CLEARED FOR CODE 2026-07-14 — /cold-eyes converged loop 5 (5 loops × 3 cold lanes = 15 reviews; accuracy lane clean from loop 4). Next: TDD tests/features/dashboard_drilldown/ (INV-1..9) → /close-phase.
  Resolved (2026-07-14): SHIPPED (code) via /close-phase. TDD 41-leg tests/features/dashboard_drilldown/ (INV-1..9) → DrillNode/DrillLabels (models), merchant_name (text.py, pure+total), drill_rows_in_range (5-tuple sibling read), ReportingService.drill_down (one "group by top-of-chain" category algorithm + account-pair transfers, INV-7 uniform-string sort; branch totals sum from integer amount_minor so they equal the tiles, INV-1), HomeView QScrollArea+QTreeWidget wiring. Close: /audit semgrep 0 + gate 0; /indie-review 2 cold lanes → production money-correct, folded inline a top_of_chain/category_node corrupt-data cycle guard + 5 test-strength adds (real INV-7 mixed-type sort-key falsifier, INV-9 sentinel-label proof, cycle regression, count==1 bare label, punctuation merchant_name). Gate green 975/1, mypy 0. Commits 810283f (impl) + ebbcced (fold) + close; tag FIBR-0138-complete; journal docs/journal/FIBR-0138.md. README "what works today" refresh deferred to next bump per Deliverable 7.

  D1 Presentation: an expanding tree (QTreeWidget-style), NOT a click-to-drill donut. The three totals (Income / Spending / Transfers) are the top rows.
  D2 Spending/Income drill follows the existing category tree (parent->child, any depth) to a leaf category; at a leaf, group its transactions by merchant with a x count, then expand a merchant to the individual transactions (date + amount).
  D3 Merchant = "smart cleanup" of the free-text description (strip card numbers, branch/ref codes, trailing digits) to a best-guess shop name, grouped + counted. There is NO merchant field today (only transactions.description) - this is a new derivation. Fuzzy by nature; refine rules over time. Candidate reuse: the FIBR-0010 rule-engine description matching.
  D4 Transfers drill by account pair (from->to, x count), then the individual moves. Transfers have no categories (money between own accounts, excluded from income/spend totals).

  INV (correctness-critical): the merchant cleanup only affects DISPLAY GROUPING - every total/subtotal is summed from real amount_minor; cleanup can never change a number, only which line it sits under.

  Details: biggest-amount-first sort at every level (matches the donut); the period + account selectors drive the tree; magnitudes shown like the tiles. Needs a new ReportingService drill API + a merchant-normalisation helper. Spec -> /cold-eyes (--max-loops 7) -> TDD when scheduled; after the v0.1.10 release per the current plan.
  **Layman:** Click a total on the Home dashboard to open it up — Spending breaks into categories, each category into shops (with a count like "McDonald's ×3"), and each shop into the actual purchases; Transfers break down by which accounts the money moved between.
  Kind: enhancement.
  Lanes: reporting, ui.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0139] **Built-in category library — smarter auto-categorise out of the box.**
  Fixes the cold-start: today auto-categorise only matches USER-written rules (FIBR-0010), so a fresh vault imports everything Uncategorised. Design (brainstorm-approved 2026-07-14):
  D1 Ship a bundled, per-release-updateable data file src/finbreak/data/category_library.json — list of {pattern, category} entries, SA-first (Pick n Pay/Checkers/Woolworths/Shoprite/Shell/Engen/Dis-Chem/Vodacom/MTN/Eskom...) + universal (Netflix/Spotify/Uber/Steam/Apple...), mapping to the v3-seeded default categories (Groceries/Transport/Bills & utilities/Entertainment/Medical/Salary/...). Travels like ui/icons (pyproject glob + PyInstaller --add-data). Missing/malformed file => empty library, app runs (fail-safe).
  D2 Matching order: user rules FIRST, then library. categorize() already substring-matches (contains, normalise_text-folded) — no wildcards. Manual pick always wins (golden rule INV-1 untouched).
  D3 New CategorySource.LIBRARY = 'library' — NO schema migration (category_source is free-text TEXT; auto_rows predicate 'IS NULL OR <> manual' already recomputes library rows). categorize/recategorize_auto_rows extended to return WHICH source matched so set_category stamps 'rule' vs 'library'.
  D4 Runs on the EXISTING paths — import auto-categorise + Rules-tab Apply — both now include the library. NO new button.
  D5 Settings toggle (default ON), reuse SettingsRepository (non-schema). Off => library not consulted; next apply/import reverts library rows to uncategorised.
  D6 Small '~ guess' tag beside library-guessed category in the Transactions table (Home is now the FIBR-0012/0138 dashboard with no per-row cell — superseded by spec D7); overridable.
  D7 Library binds category by NAME; a renamed default category => entries fall through to Uncategorised (never mis-filed). Structural binding is a future enhancement (out of scope).
  INV money-safety: only sets category, never reads/alters an amount; grand-book total + amount_minor multiset identical before+after (per-category sums change by design — see spec INV-1). Deps: FIBR-0010. Lanes: services, ui, repo, tests. Next: spec docs/specs/<id>.md -> /cold-eyes (max-loops 7) -> TDD.
  **Layman:** finbreak ships with a built-in list of common shops so imported transactions get sensible categories automatically, without you writing a rule for every merchant.
  Kind: feature.
  Source: user-request-2026-07-14.
  Active 2026-07-14 — brainstorm complete + user-approved (all decisions D1-D7 locked: bundled JSON library, user-rules-first, CategorySource.LIBRARY no-migration, existing import+Apply paths, Settings toggle default-ON, '~ guess' tag, rename falls through safely). NEXT: write spec docs/specs/FIBR-0139.md -> /cold-eyes (max-loops 7) -> TDD.
  Resolved (2026-07-14): SHIPPED by TDD. category_library.py (LibraryEntry, pure+total parse_library, fail-safe cached load_library, match_library) + data/category_library.json seed (every entry bound by name to a v3 DEFAULT_CATEGORIES leaf). CategorySource.LIBRARY (free-text column, no migration); categorize_with_library (rule beats library), _match_inputs (toggle-gated), _leaf_name_to_id (first-wins), library_enabled; recategorize_auto_rows + would_categorize rerouted. Settings toggle (default ON) wired through the shell; Transactions "~ guess" marker with every Category cell a bare-name SortableItem. data/*.json package-data + second --add-data pair in all three freeze sites; parity guard set-checks both targets. tests/features/category_library/ (INV-1..11) + autouse neutralise fixture + real_library marker. /audit (semgrep full) 0 actionable; /indie-review 2 cold lanes 0 CRIT/HIGH/MED, only LOW substring-precision (accepted D2 substring-only tradeoff, marked overridable guesses, money never touched). Gate green 934/1, mypy 0. Commit 24e7a91; tag FIBR-0139-complete; journal docs/journal/FIBR-0139.md. FIBR-0140 (learn-from-history) remains the deferred "later" half.

- 📋 [FIBR-0140] **Auto-categorise learns from your own history (statistical, no hand-written rule).**
  The 'later' half of the 2026-07-14 'both' decision (library now, learning later). Distinct from FIBR-0035 (offer-to-MAKE-a-rule, shipped) and FIBR-0092 (bulk re-categorize + rule preview): this auto-applies a category learned from the user's OWN past manual picks (merchant-keyed), ranked with/near the library, still overridable, manual always wins. Deps: the built-in category library item + FIBR-0010. Design TBD in its own brainstorm.
  **Layman:** Once you've categorised a shop by hand a few times, finbreak remembers and auto-applies that to future transactions from the same shop — without you writing a rule.
  Kind: enhancement.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0142] **Recurring money detection (subscriptions + standing income).**
  Split from FIBR-0022 (the recurring half; budgets stay on FIBR-0022 as the follow-up). Auto-detect repeating money movements — recurring OUT (subscriptions, debit orders, insurance) and recurring IN (salary, standing deposits) — surface for confirm/dismiss. User-chosen scope (2026-07-15 brainstorm): both directions; "Balanced" sensitivity (seen 3+ times, amount within ~10% of the group median, gaps consistently in one cadence bucket — weekly/fortnightly/monthly/yearly with slack). Pure deterministic detect_recurring(rows, today) grouping on normalise_text(merchant_name(description)) x direction (reuses FIBR-0138 cleanup); excludes confirmed transfers; integer amount_minor throughout (INV-13). Persistence: new schema v9 recurring_decisions table keyed on (direction, merchant_key) — not txn ids — mirroring transfer_pairs. RecurringService shaped like TransferDetectionService (candidates/confirmed/confirm/dismiss/reset/summary). SURFACES: dedicated Recurring tab (Suggested/Confirmed tables mirroring Transfers) built now; the read-only Home dashboard card is DEFERRED until the dashboard-focus rework so it isn't added to a layout being decluttered. Deps: FIBR-0138 (merchant_name), FIBR-0011 (transfer exclusion), FIBR-0012 (dashboard).
  **Layman:** finbreak spots your regular payments and deposits — subscriptions, debit orders, salary — so you can see what's on autopilot and what it costs you each month.
  Kind: feature.
  Source: user-request-2026-07-01 (FIBR-0022 split) + brainstorm-2026-07-15.
  Resolved (2026-07-15): shipped by TDD (4 slices) — pure detect_recurring + schema v9 recurring_decisions + RecurringRepository/RecurringService + the Recurring tab (after Transfers). Closed by /close-phase: semgrep+bandit 0; 2 cold code-review lanes → 1 HIGH (fortnightly monthly-equivalent pre-divided factor defeated ROUND_HALF_EVEN) + 1 LOW (created_at reset on flip) + 3 test-strength adds, all folded inline. Gate green. Tag FIBR-0142-complete. Home dashboard card deferred to FIBR-0143.

- 🚧 [FIBR-0143] **Rework the Home dashboard so the income/expenditure/transfers breakdown is the hero, charts secondary.**
  User feedback 2026-07-15 (with a screenshot): the current Home leads visually with the donut and the income-vs-spending BAR graph, while the FIBR-0138 drill-down breakdown (Income / Spending / Transfers -> category -> merchant -> txn) sits at the very bottom. The user's intended hero of the dashboard is that BREAKDOWN, not the graphs -- valuable information but the BIG feature is the breakdown. Especially de-emphasise the bar graph. Invert the layout: promote the expandable breakdown to the primary surface; keep the charts as smaller/secondary supporting detail. BLOCKED pending the user's own HTML mockup of the envisioned layout (they said they'll make one) -- do NOT redesign the layout before that lands. When it does: brainstorm-confirm against the mockup -> spec -> cold-eyes -> TDD. The deferred FIBR-0142 recurring Home-card slots into this reworked layout. Deps: FIBR-0012 (dashboard), FIBR-0138 (drill-down breakdown).
  **Layman:** Redesign the main screen so the plain-language breakdown of where your money went (and came from) is the star, with the pie and bar charts moved to a supporting role.
  Kind: ux.
  Evidence: /home/ants/Pictures/ClaudePaste/paste_20260715_085635_284_5e11f9ac.png
  Source: user-feedback-2026-07-15 (dashboard focus).
  UNBLOCKED 2026-07-15: user delivered the HTML mockup `/home/ants/Documents/dashboard_2.html` (+ annotated screenshot). Envisioned layout: three side-by-side columns — Expenditure / Income / Transfers — each with the existing pie chart on top, a bold coloured header + big total, then the expandable breakdown list (categories → merchant sub-rows, e.g. Groceries → Checkers/Sixty60, Spar); the monthly bar chart demoted to a full-width strip at the bottom ("2026 Monthly Trend Breakdown"). User notes: NO borders (those were alignment guides only), CONSISTENT row heights, reuse the existing pie chart (not the mockup's CSS one), add polish/flair. Next: brainstorm-confirm against the mockup → spec → cold-eyes → TDD. Also lands the deferred FIBR-0142 Home recurring card (consumes RecurringService.summary()). User gated this behind "if my weekly limit hasn't finished yet" (2026-07-15).
  Started 2026-07-16: design brainstormed + user-approved against the mockup (dashboard_2.html). Decisions: pies in all 3 columns (fed from the existing drill_down branch children — pie mirrors each column's breakdown list); keep Net as a slim full-width strip; include the deferred FIBR-0142 recurring Home card now. Layout: 3 side-by-side columns (Expenditure/Income/Transfers) each = pie → coloured header+total → expandable breakdown tree; Net strip; full-width Recurring card; monthly-trend bar demoted to a bottom strip. No schema/service-data change — all reuse (drill_down + summary + monthly_trend + RecurringService.summary). Spec docs/specs/FIBR-0143.md next → /cold-eyes (cap 7) → TDD.
  Spec CLEARED FOR CODE 2026-07-16 — /cold-eyes converged loop 7 (7 loops × 3 cold lanes = 21 reviews; loop 7 all-polish, 0 CRIT/HIGH/MED). Spec docs/specs/FIBR-0143.md written + 7-loop log. Key contract details settled across the loops: build_breakdown_donut does its own cap loop (no _donut_wedges extraction — donut stays byte-for-byte unchanged for the PDF export); each column's header+pie+list all source from the one drill_down branch node (summary feeds only the Net strip); explicit node→column map (Expenditure←nodes[1]/Spending, Income←nodes[0], Transfers←nodes[2]) so a naive zip can't mis-colour; recurring card is UNSCOPED by the Home selectors (summary(today) takes only today — shows all confirmed recurring money vault-wide); branch colour on header+tree only (pie is palette-coloured), gated on amount_prefs.colour; monthly_out is a positive magnitude so In/Out colours are forced-by-role. Commits d132c18→7238685, all pushed, gate green. NEXT: TDD tests/features/dashboard_focus/.

- 📋 [FIBR-0144] **Centralise the schema-version drift guard to remove per-bump test churn.**
  Surfaced during the FIBR-0142 close. Every feature that ever added a migration hard-asserts `LATEST_SCHEMA_VERSION == N` (and encodes the version in test function names + spec.md INV lines), so each schema bump forces ~24 assertion edits + ~15 renames across ~9 feature suites (v8→v9 did exactly this). Replace the scattered per-feature guards with ONE canonical "latest schema version" test (assert the constant + that a fresh vault reaches it) and have each feature's migration test assert only its OWN delta (the intermediate step it introduced), never the moving global latest. Removes the churn and the drift risk. Low priority, no user-facing effect.
  **Layman:** A cleanup: right now every time the database format is upgraded, a bunch of unrelated tests have to be hand-edited. This would make that a one-line change instead.
  Kind: refactor.
  Source: in-session-2026-07-15 (FIBR-0142 review observation).

- 📋 [FIBR-0145] **Transfer detection learns from confirmed/rejected transfer pairs.**
  User feedback 2026-07-16 (general use of the shipped Transfers tab): confirming/rejecting a transfer should TEACH the detector, not just decide the one pair. Today FIBR-0011's `transfer_pairs` records a decision keyed on the two specific transaction ids, so an equivalent pair next month (same two accounts, same kind of description, same equal-magnitude/opposite-sign shape) is presented cold again. Enhancement: derive a reusable signal from each confirm/reject — keyed on something like (account_pair, direction, normalised description/merchant pattern) — so future candidate pairs that match a CONFIRMED pattern are auto-suggested or pre-confirmed, and pairs that match a REJECTED pattern are suppressed. Mirror the FIBR-0010 categorization-rules learning-from-manual-overrides design (a learned-rule table + a manual decision always winning + an overridable marker), applied to the transfer surface. Correctness guard: a learned auto-confirm must never merge money that isn't genuinely a transfer, so the learned pattern should stay conservative (exact account pair + tight amount/description match) and remain user-overridable. Deps: FIBR-0011 (transfer detection), pattern-reuse from FIBR-0010 (rules engine).
  **Layman:** When you confirm or reject that two transactions are the same money moving between your own accounts, the app should remember the pattern and get better at spotting (or ignoring) similar transfers next time — instead of re-asking about the same kind of pair every import.
  Kind: enhancement.
  Source: user-feedback-2026-07-16 (general use).

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

- 📋 [FIBR-0071] **Add DB indexes for the import-dedup + count lookups (full-table scans today).**
  No CREATE INDEX anywhere in migrations.py. TransactionRepository.existing_for() (WHERE account_id, occurred_on, amount_minor) runs once per distinct (date, amount) bucket inside every import — N full scans; same for count_for_account / count_for_category / rules count_for_category. Fine at today's personal scale (design.md accepts it) but a multi-year vault degrades. A composite index on transactions(account_id, occurred_on, amount_minor) plus single-column indexes on account_id/category_id/statement_period_id would flatten it. Overlaps FIBR-0026 (indexed dedup lookup).
  Kind: perf.
  Source: indie-review-2026-07-10 (M-data3).

- 📋 [FIBR-0097] **Virtualize the transaction tables — QTableWidget → QTableView + QAbstractTableModel.**
  Verified 2026-07-11: Home, Statements, and Rules use QTableWidget (ui/home.py, ui/statements.py, ui/rules.py), which builds a widget for EVERY cell — fine at 50 rows, sluggish at thousands. Migrate to QTableView + a QAbstractTableModel so rendering is virtualized (only visible rows built). Also a cleaner data/view separation that FIBR-0012 (sort/filter) and FIBR-0084 (movable/resizable columns) build on naturally. Sizeable refactor; own spec. Deps: FIBR-0051/0052 (the current widgets).
  **Layman:** Keep the transaction lists fast even with thousands of rows by only drawing the rows you can actually see.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0098] **Add database indexes on the hot query columns.**
  Verified 2026-07-11: the schema (migrations.py) declares NO indexes. Add them on the frequently-queried columns — transactions(occurred_on), transactions(account_id), transactions(category_id), transactions(statement_period_id) (+ any dedup/lookup key). A forward migration (current v7 -> v8). Speeds listing, filtering (FIBR-0012), cross-source dedup, and delete-cascade. Cheap, high-value. Deps: FIBR-0005/0006/0010/0052 (the columns).
  **Layman:** Add quick-lookup indexes so finbreak finds and filters transactions fast as your history grows.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0099] **Faster cold start — PyInstaller --onedir inside the AppImage (skip per-launch extraction).**
  Verified 2026-07-11: the release build uses PyInstaller --onefile (scripts/_build-smoke-in-container.sh:85), which re-extracts the whole bundle to /tmp on EVERY launch (adds seconds of cold-start latency). Since the AppImage is ITSELF a self-contained mounted container, freeze with --onedir and place the dir inside the AppDir — the app then runs directly, no per-launch extraction. Transparent to the user; measure before/after start time and confirm the FIBR-0003 clean-room bundling proof still passes. Deps: FIBR-0003/FIBR-0054 (build pipeline).
  **Layman:** Make the app open faster by not unpacking itself every single time you launch it.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0104] **Move slow statement import onto a worker thread (responsive UI + native overlap).**
  User idea (multi-threading for performance). Honest framing: Python's GIL means threading helps RESPONSIVENESS + native-code overlap, NOT pure-Python CPU parallelism. The app already threads its two slow blocking ops correctly (Argon2 key derivation via DeriveWorker; network via UpdateCheck/DownloadWorker — both native/GIL-releasing). Best next win: move IMPORT (pdfplumber text extraction, in-memory pikepdf decrypt, CSV/OFX parse, dedup + commit) onto a QThread worker (reuse the ui/_worker.py DeriveWorker pattern) with a progress indicator — today it runs ON THE UI THREAD (security-model / FIBR-0075 note: pdfplumber extract runs on the UI thread), so a large statement freezes the window. These ops are native-heavy (pdfplumber/pikepdf C++, SQLCipher C) so they RELEASE the GIL → genuine overlap with the GUI. CAVEAT: SQLite/SQLCipher connections are NOT shareable across threads — the worker needs its OWN connection to the vault (or marshal results back via signals). Pure-Python CPU hotspots (rule matching) won't benefit (GIL) — indexes (FIBR-0098) + virtualized tables (FIBR-0097) are the levers there. Deps: FIBR-0007/0008/0009 (import), reuses the QThread worker pattern; pairs with FIBR-0065 (non-blocking dialog discipline)."
  **Layman:** When importing a big statement, do the heavy reading on a background thread with a progress bar so the window stays responsive instead of freezing.
  Kind: perf.
  Source: user-suggestion-2026-07-11.

### 🧹 Warnings & tech debt

Every warning or error found during any work — tests, gate, build, tooling,
dependencies, review — is filed here (or the most fitting section) for later
investigation/resolution, even when third-party or non-blocking. A warning today
is a future error tomorrow.

- ✅ [FIBR-0043] **Silence/resolve ofxparse's bs4 findAll DeprecationWarning noise in the test run.**
  Surfaced by FIBR-0008 (2026-07-04). Running `tests/features/ofx_import/` emits ~100 `DeprecationWarning: Call to deprecated method findAll. (Replaced by find_all)` — raised INSIDE `ofxparse` 0.21 (`ofxparse.py` calling BeautifulSoup's deprecated `findAll`), not our code. Harmless today (tests pass), but: (a) it's log noise that masks real warnings, and (b) a future bs4 major could turn `findAll` into a hard error, breaking OFX import. ofxparse 0.21 is the current latest (lightly maintained), so there's no newer release to bump to. Options: a scoped pytest `filterwarnings` ignore for ofxparse's DeprecationWarning (documented, so it doesn't hide OUR deprecations); upstream a PR to ofxparse (findAll -> find_all); or, if bs4 ever breaks it, migrate to a maintained parser (ofxtools) — the escape hatch already noted in FIBR-0008 § Dependencies. Decide + apply.
  **Layman:** The OFX-import library prints ~100 harmless "this method is old" warnings whenever we run our tests; the app works fine, but the noisy warnings should be quietened or fixed at the source.
  Kind: investigate.
  Source: in-session-2026-07-04 FIBR-0008 build/test warnings.
  Resolved (2026-07-10): already delivered by FIBR-0058 — the scoped pytest `filterwarnings` ignore for "Call to deprecated method findAll.*" plus the `beautifulsoup4>=4.9,<5` pin are both live in pyproject.toml. This was the investigate twin of the FIBR-0058 chore; no additional code needed. Closing as superseded.

- ✅ [FIBR-0057] **Import wizard snapshots the target account at file-select — a later dropdown change is ignored.**
  ui/import_wizard.py `_select_file` (line ~255) does `self._account_id = self._account_combo.currentData()` and bakes it into the preview; the account combo lives on step 0 only and changing it after a file is chosen does not re-read or re-preview. Combined with the combo defaulting to the first account, a user who doesn't set the account BEFORE choosing the file (or wants to change it after) silently imports under the wrong account. Fix options: (a) read the account at commit time (decouple from the snapshot); (b) keep the account picker editable through the flow and re-run dedup/preview on change; (c) at minimum, disable the combo once a file is picked + surface the chosen account on the preview step so it's visible before commit. Prefer (a)+(c). Needs a reproduction test. Related to the FIBR-00xx edit-statement-account feature (which lets a user fix a mis-link post-import).
  **Layman:** When importing a statement, if you change which account it goes into AFTER picking the file, the app ignores the change and uses the first account (e.g. "Current"). This is how a credit-card statement can land on the wrong account.
  Kind: fix.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): the preview step now carries a destination-account picker that is the single source of truth for the committed account — seeded from the pick step at file-select, read live via _target_account_id() by every preview + the per-account PDF-password lookup, and user-correctable before the irreversible Import (changing it re-runs the dedup via ImportService.retarget). Cold-review fold: a remembered PDF password now follows a re-target onto the committed account. Tests: import_ FIBR0057 x3 (retarget re-dedups; preview exposes the destination; changing it re-targets the whole commit) + pdf_import FIBR0057 x1 (remembered password follows the corrected account). Gate green 348 passed/1 skipped, mypy 0, audit 0. Commits 4be777c + ba6d912.

- ✅ [FIBR-0058] **ofxparse emits BeautifulSoup findAll DeprecationWarnings (107 per test run).**
  The gate run shows 107 `DeprecationWarning: Call to deprecated method findAll. (Replaced by find_all) -- Deprecated since version 4.0.0` from ofxparse (ofxparse.py:445/449/454/949), which calls BeautifulSoup's long-deprecated `findAll`. It is inside the ofxparse dependency, not our code, so we can't fix the call directly. Options: (a) pin/track ofxparse for an upstream fix or a maintained fork; (b) filterwarnings in pytest config to quiet the known-3rd-party warning (documented, not a blanket ignore); (c) evaluate replacing ofxparse if it stays unmaintained. BeautifulSoup will eventually remove `findAll`, which would then break OFX import — so this is a latent breakage, not just noise. Investigate + decide.
  **Layman:** A dependency the app uses for one import format prints lots of "deprecated" warnings during tests. Harmless today, but noisy and a sign the dependency is aging.
  Kind: chore.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): investigated — ofxparse 0.21 is the latest PyPI release (unmaintained since 2023; no find_all fix to track), and bs4 4.15 still ships findAll as a deprecated alias (removal slated for bs4 5.0). Two-part root-cause fix, not a blanket silence: (a) scoped pytest filterwarnings ignoring ONLY "Call to deprecated method findAll..." (our own future deprecations still surface); (b) beautifulsoup4>=4.9,<5 pin in [project].dependencies — the latent-breakage guard, since an unpinned bs4 5.0 (findAll removed) would break OFX import; bs4 is only reached transitively via ofxparse. Gate 352 passed, 0 warnings (was 107); pip check clean. Option (c) — replacing ofxparse — deferred (large; FIBR-0008 built OFX import around it); revisit if ofxparse stays unmaintained when bs4 5.0 becomes necessary. Audit 0 (ruff/bandit skipped — pyproject-only). Config-only chore, no multi-agent review warranted. Commit below.

- ✅ [FIBR-0060] **Window geometry restore + Center Window don't work on Wayland (FIBR-0052 was X11-assumed).**
  Reported on KDE Wayland. Root cause: FIBR-0052 (INV-5 geometry persistence, INV-6
  Center window) assumed X11 semantics. On Wayland the compositor owns window
  placement — an app cannot set/restore its own POSITION, and move()/setGeometry-pos
  is a no-op — so Center Window can never work and position-restore is impossible;
  size-restore via restoreGeometry is also unreliable before first map. Verified:
  saving works (~/.local/share/finbreak/window.ini has a geometry key), and
  _restore_geometry calls restoreGeometry before show — but Wayland ignores the
  position, and the FIBR-0052 tests only asserted the QSettings round-trip (offscreen
  platform), never real WM behaviour, so they passed while the feature is broken for
  the user. Fix plan: (a) restore SIZE explicitly via resize() (Wayland allows size
  requests) and confirm it sticks; (b) on Wayland, disable/grey Center window +
  position-restore with a tooltip (or drop them there) since the compositor centres
  windows itself — keep them on X11 where they work; (c) detect the platform
  (QGuiApplication.platformName()); (d) add a test that exercises the real behaviour,
  not just the settings round-trip. My code (FIBR-0052) — own it. Related to the
  sole-author no-Wayland-coverage gap.
  **Layman:** The app doesn't remember its window size/position between runs, and Window → Center Window does nothing. On modern Linux (Wayland), apps aren't allowed to position their own windows, so parts of this can't work the way they were built.
  Kind: fix.
  Source: user-report-2026-07-09.
  Resolved (2026-07-09): platform-aware geometry. _is_wayland()/_kde_wayland()/_center_supported() gate behaviour. On Wayland the SIZE is restored via resize() from a bare window_size key (the compositor honours a size request; restoreGeometry's size is unreliable pre-map) — matching the SystemManager reference. Center window is IMPLEMENTED on KDE Wayland via KWin's scripting D-Bus API (QtDBus loadScript/start/unloadScript of a PID-matched centring script — the SystemManager technique, ported to QtDBus so no dbus-send subprocess); disabled with a tooltip on other Wayland compositors (no app-usable placement API); X11/Windows/macOS keep move(). Position-restore on launch stays compositor-owned on Wayland (as SystemManager also accepts). LIVE-VERIFIED on the user's KDE Wayland: window centres exactly (work-area offset dcx=0 dcy=0). Tests: FIBR0060 x4 (size restore; KWin dispatch on KDE; disabled+no-op on non-KDE; enabled off Wayland) via monkeypatched _is_wayland/XDG_CURRENT_DESKTOP. Cold-review fold: temp-file-leak-on-write-failure + Plasma-version doc accuracy. Gate green 352 passed/1 skipped, mypy 0, audit 0. Commits 36e0ea1 + review fold. Note: the FIBR-0052 INV-5/INV-6 tests only asserted the QSettings round-trip (offscreen), never real WM behaviour — now both platform branches are exercised.

- ✅ [FIBR-0061] **mypy is not enforced by the gate, and `mypy src tests` reports 4 pre-existing type errors in test files.**
  Found while closing FIBR-0059. `scripts/ci-local.sh` (the gate, run by the
  pre-push hook + ci.yml) runs ruff / format / bandit / pip-audit / gitleaks /
  pytest but NOT mypy — so the journal's repeated "mypy 0" claims came from ad-hoc
  manual runs (often `mypy src`, not the config's `files = ["src", "tests"]`), and
  type errors in the test tree were never gated. `mypy src tests` (mypy 2.1.0)
  currently reports 4: tests/features/settings/test_settings.py:70/75/80 (a
  findChild helper returning QComboBox|None / QDialogButtonBox|None dereferenced
  without a None-guard — FIBR-0055 code) and tests/features/app_shell/
  test_app_shell.py:83 (a fake QThread subclass whose start() override signature is
  incompatible). None are runtime bugs (test-only typing), but they hide real
  regressions. Fix: (a) add a mypy stage to ci-local.sh so it's actually enforced;
  (b) fix the 4 (cast/assert the findChild Optionals; align the fake start()
  signature). My code (sole author). NB FIBR-0059's own new src is mypy-clean.
  **Layman:** The type-checker (mypy) that catches whole classes of bugs isn't actually run by the automated quality gate, and running it by hand turns up 4 small type issues in the test code that have gone unnoticed.
  Kind: chore.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): added a `mypy` stage to `scripts/ci-local.sh` (after gitleaks, before pytest — bare `mypy` uses the config's `files = ["src","tests"]`), so CI (which invokes ci-local.sh) now enforces it too; the dev group already pins `mypy==2.1.0`. Fixed the 4 test-tree errors: `assert ... is not None` guards on `_combo`/`_click_save`/`_click_cancel` in `tests/features/settings/test_settings.py`, and aligned `_StubWorker.start` to the `QThread.start(self, priority=...)` signature in `tests/features/app_shell/test_app_shell.py`. Gate green: 366 passed / 1 skipped, mypy clean (59 files), shellcheck 0.

- ✅ [FIBR-0062] **Test-audit: hoist duplicated paths/service/_PW fixtures + connection-proxy helpers to shared conftest.**
  All 4 /test-audit chunks flagged this. The identical `paths` fixture, `_PW` literal, `_FailAt*`/`_StandInVault` connection-proxy classes, and `_acct`/`_wizard`/`_default_id`/`_pump_deferred_delete`/`_two_accounts` helpers are copy-pasted across ~9 tests/features/* files (Rule-of-Three well exceeded). Extract to tests/conftest.py (paths + _PW import + a raising_proxy(real, trigger, message) factory). The window_ini autouse fixture was already hoisted 2026-07-10 as part of the CRITICAL isolation fix.
  **Layman:** Lots of test files copy-paste the same setup code; move it to one shared place so a change only needs editing once.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): hoisted the copy-pasted test infrastructure to tests/conftest.py — the `paths` fixture (was duplicated in 11 feature suites), the `_PW` literal (3 remaining local copies → imported from conftest, joining the 8 that already did), a generic `raising_conn(real, trigger, message, on=)` factory + a `StandInVault` class replacing 7 bespoke `_FailAt*`/`_StandInVault` wedge classes across 5 suites (the migration + service atomicity-rollback tests), and the `_acct` (5 copies) + `_pump_deferred_delete` (3 copies) helpers. Deliberately NOT hoisted (Rule-of-Three not met / not identical): the `service` fixture (varies — some suites first_run, some don't), `_default_id` (varying signature: service vs vault), `_two_accounts` (single-site). Gate green 440 passed/1 skipped, mypy 0 (fresh cache), ruff clean.

- ✅ [FIBR-0063] **Test-audit: parametrize repeated single-assert tests + split multi-claim tests.**
  Convert the four standard_bank INV11 checksum/completeness tests and the three INV2a per-family detection asserts to @pytest.mark.parametrize(ids=...) so one failure doesn't mask siblings; same for the import_ bad-mapping-config loop (test_import.py:263). Consider splitting statements INV5a's 7-claim test (esp. the plaintext-leak security checks).
  **Layman:** Some tests bundle several checks in one; splitting/parametrizing them makes a failure point at the exact broken case.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): parametrized the genuine bundled-assert/loop tests so one failure can't mask siblings — standard_bank test_INV2a_each_family_detected_by_its_own_signature (3 bundled asserts → @pytest.mark.parametrize ids=family_b/d/c) and import_ test_service_rejects_bad_mapping_config (the `for bad in (...)` loop → parametrized test_service_preview_rejects_bad_mapping_config ids=no_amount_style/missing_column/both_styles; the distinct save_profile path split into its own test). Split the statements INV5a omnibus: the plaintext-leak SECURITY checks (no txn description/amount in the geometry INI) now live in a dedicated test_INV5a_no_transaction_data_leaks_to_plaintext_ini so a geometry-persistence regression can't mask a data leak. The four standard_bank INV11 checksum/completeness tests were left as-is — they are already SEPARATE test functions (independent failure points), so parametrizing would only DRY, not fix masking. Gate green, ruff clean.

- ✅ [FIBR-0064] **Test-audit: add tests for untested error branches surfaced by the audit.**
  Untested branches: UnlockDialog SchemaVersionError (HIGH); FirstRunDialog create-failure except; AuthService.unlock() password-wipe-on-failure; CategoryService._require_parent ValueError; categorization.move_rule unknown rule_id; import_wizard _decrypt_pdf/_extract_pdf_tables friendly-error paths (wizard-level); StatementService.list_statements ordering contract; standard_bank corrupt-PDF wizard message (assert substring, not != ''); and the 5 auto-lock 'must not raise' tests should gain a concrete post-click state assertion.
  **Layman:** A few error-handling paths in the app have no test; add regression tests so a future change can't silently break them.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): added regression tests for the untested error branches + strengthened the weak ones. New tests: move_rule unknown-id no-op (categorisation); _require_parent bad-parent-id ValueError (categories — the None-parent branch was already covered); list_statements import-recency ordering (statements); AuthService.unlock password-wipe on load_params failure (vault/security-INV-3); UnlockDialog SchemaVersionError 'newer version' message (vault, driven via _on_derived to skip Argon2); FirstRunDialog 'Could not create the vault' create-failure (vault). Strengthened: the standard_bank corrupt-PDF test now asserts the friendly-message SUBSTRING (not != '') — which REVEALED + FIXED a real UX bug: the wizard caught PdfError but showed str(exc) (raw pikepdf 'unable to find trailer dictionary...') rather than the friendly message; added _show_pdf_read_error() mapping PdfError→friendly at the 3 PDF catch sites (import_wizard). The 5 auto-lock 'must not raise' tests (4 categorisation INV14 + statements reassign) each gained a concrete post-click state assertion (row unchanged / rule-created / error-empty / txn-stayed-on-account). Gate green 452 passed/1 skipped, mypy 0, ruff clean.

- ✅ [FIBR-0065] **Fix the auto-lock-during-modal-dialog crash (reproduced HIGH).**
  REPRODUCED (Qt DeferredDelete is processed inside a nested exec() loop): an idle auto-lock fires while a content-widget dialog is exec()-blocking; MainWindow._lock() -> _clear_live() -> workspace.deleteLater() destroys the dialog's parent chain during that nested loop, so the post-exec() call (home.py CategoryPickerDialog.selected_category_id(); import_wizard.py PasswordDialog.password()/remember(); also statements.py, rules.py) hits a deleted C++ object -> RuntimeError, which the VaultLockedError guards do NOT catch. The existing guards only cover 'dialog closes BEFORE lock', not 'lock DURING exec()'. Needs its own spec+cold-eyes+TDD cycle (lifecycle-critical security code). Proposed approach: either convert content-widget dialogs to the shell's non-blocking setModal(True)+show() pattern (FIBR-0051 D2 rejected exec() for exactly this), OR a MainWindow modal-registry that wipes the key immediately (security preserved) but defers the UI teardown until the nested loop unwinds. Recommend prioritising ABOVE FIBR-0054.
  **Layman:** If the app auto-locks itself while a small pop-up (pick a category, edit a rule, enter a PDF password) is open, it can crash instead of locking cleanly.
  Kind: fix.
  Source: indie-review-2026-07-10 (full-codebase sweep, H-B).
  Started 2026-07-10. Approach chosen with the user: convert the remaining blocking exec() content-dialogs to the shell's non-blocking setModal(True)+show()+signal pattern (matches FIBR-0051 D2). Spec → cold-eyes → TDD next.
  Resolved 2026-07-10. Converted the 6 blocking exec() content-widget pop-ups (home set-category + learning offer, rules add/edit, statements reassign, import-wizard PDF password) to the non-blocking show_modal (setModal+show()+signal) pattern; PDF password loop → the _try_decrypt state machine. Spec /cold-eyes-converged (5 loops); TDD: dialog_lifecycle INV-1 grep + a real _lock()-during-open-PDF-prompt regression (INV-2 guard-less path) + parity ripple. Gate green 437 passed/1 skipped, mypy 0; /audit 0; a cold code-review lane confirmed the D5 semantics faithful (doc-nits only, folded). Tag FIBR-0065-complete.

- ✅ [FIBR-0066] **Refactor the 6x duplicated BEGIN/COMMIT/ROLLBACK transaction boilerplate into one owned-transaction helper.**
  Identical BEGIN / try:...commit() / except: rollback(); raise appears 6x in services (categorization apply_rules/set_manual_category/move_rule, categories delete_category, import_ commit_import, statements delete/reassign) and 6x in migrations.py. A vault.owned_transaction() context manager would collapse both and remove the risk a 7th call site copies it with a subtly wrong exception class. Load-bearing atomicity code — do carefully with tests.
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-C3, corroborated x2: crypto-vault migrations.py + core-services).
  Resolved (2026-07-10): extracted owned_transaction(conn) context manager into new src/finbreak/db.py — the single BEGIN…COMMIT / ROLLBACK-and-reraise boundary. Replaced all 13 hand-rolled sites: 7 services (categorization move_rule/apply_rules/set_manual_category, categories delete_category, import_ commit_import, statements delete_statement/reassign_account) + 6 migrations (v2→v7). Deliberately a free function on a bare Connection, not a Vault method, so migrations.py (which vault.py imports) can use it without an import cycle. No behavior change — all atomicity tests (import INV-7 rollback, migration atomicity, delete-cascade INV-7, move_rule two-row swap) stay green. mypy 0, 248 affected tests pass.

- ✅ [FIBR-0067] **Widen the Standard Bank _MONEY regex to accept ungrouped 4+-digit amounts, then re-validate against the real statements.**
  standard_bank.py _MONEY = r'(?<![\d.,])\d{1,3}(?:[.,]\d{3})*[.,]\d{2}(?!\d)' fails to match an amount >= 1000 printed WITHOUT a thousands separator (e.g. '1500.00' -> no match), so a statement with an ungrouped opening/closing balance fails with the generic mis-parse. Degrades SAFELY (friendly error, no corruption); none of the 6 validated real statements exhibit it. NOT folded in the audit sweep: the naive fix (\d{1,3}->\d+) risks a NEW false positive (a dotted date like 2026.07.15 -> spurious '2026.07' token), and this parser was validated end-to-end on a real-statement corpus not available in-session. Fix + re-validate against all 6 real statements as its own item.
  Kind: fix.
  Source: indie-review-2026-07-10 (M-imp1).
  Blocked (2026-07-10): deliberately NOT fixed in the audit-fix sweep — the SB _MONEY regex is a validated parser and there is no real-statement corpus in-session to re-validate against. A naive widening to accept ungrouped 4+-digit amounts risks a dotted-date false positive (e.g. matching a date fragment as money), which would silently mis-parse. Needs real anonymised sample statements (same blocker as FIBR-0074's dedicated ABSA/Nedbank/FNB readers) to widen + re-run the six-statement checksum corpus. Keep planned; revisit when sample statements are available.
  Resolved (2026-07-10): UNBLOCKED — the user provided the six real Standard Bank statements (one per family: Credit Card/Current/Home Loan/Money Market/RCP/Savings) + the password. Reproduced first: all six PASS with the current regex, and ZERO ungrouped 4+-digit tokens appear (SB always groups thousands). Widened _MONEY to also accept an ungrouped run: `(?:\d{1,3}(?:[.,]\d{3})*|\d{4,})[.,]\d{2}`, with a `(?![.,]?\d)` tail guard against the dotted-date false positive the earlier defer flagged (2025.07.21 rejected; 3-decimal rates still rejected). Re-validated against all six real statements in a throwaway harness — EXACT same txn counts (53/82/27/20/30/3), zero regression. Added a synthetic parametrized _MONEY unit test (grouped/small/ungrouped-4/7-digit/reject-3dp-rate/reject-dotted-date/iso-date). The real statements + password were NEVER committed (validated in scratchpad, since deleted; the committed test uses synthetic strings only — testing.md §6). Gate green 460 passed/1 skipped, mypy 0, ruff clean.

- ✅ [FIBR-0068] **Promote the _set_combo(combo, value) helper to a shared UI util and dedup the 7x findData+setCurrentIndex idiom.**
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-dlg4).
  Resolved (2026-07-10): extracted the guarded combo-preselect idiom (index = combo.findData(v); if index >= 0: combo.setCurrentIndex(index)) into select_combo_data() in new src/finbreak/ui/_widgets.py, and converted the 6 sites (settings/accounts/categories type combos + rules/category_picker/account_picker id combos). IMPORTANT distinction surfaced, not forced: kept DISTINCT from ImportWizardWidget._set_combo, which is UNGUARDED by design — the wizard wants a saved-profile column absent from the current file to CLEAR the combo (force a re-pick), whereas the picker/dialog sites keep the current selection when a value isn't found. Merging them would have been a silent behavior change. mypy 0, 165 UI tests pass.

- ✅ [FIBR-0069] **Extract a _signed_balance_from_tokens helper for the 4x duplicated Standard Bank balance-token parse.**
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-imp3).
  Resolved (2026-07-10): extracted _signed_balance(token, fmt) in standard_bank.py — the single home of the '-parse if _is_negative else parse' idiom. Replaced 7 occurrences (the reviewer's 'x4' undercounted): the brought-forward/opening captures (_capture_opening x2, credit-card opening, _anchor_balance) + the per-row balance in Families A/B/D. Named _signed_balance (a single token) rather than the tentative _signed_balance_from_tokens, since every site passes one token. No behavior change — all family checksums + per-row sign gates stay green (83 SB/PDF tests). ruff/mypy 0.

- ✅ [FIBR-0070] **Decide the fate of the unwired ImportProfileRepository.list_all() (build a manage-saved-profiles screen, or remove it).**
  list_all() has zero callers in src/ — the wizard only auto-matches by signature and saves. Either an intended 'manage saved import profiles' feature was never wired up, or it is dead weight. Decide feature-vs-delete.
  Kind: chore.
  Source: indie-review-2026-07-10 (M-data1).
  Loop-2 review (2026-07-10): ImportProfileRepository.get() is also unwired in src/ (only test callers) — the other half of the never-built manage-profiles screen. Fold get() into this decision (wire both up, or remove both).
  Resolved (2026-07-10): KEEP (user rule: 'if we'll use it later, leave it'). No roadmap item commits to a manage-profiles screen, but the saved-import-profiles feature is shipped (FIBR-0007) and a 'manage saved profiles' view (see/rename/delete accumulated bank layouts) is its natural completion — a plausible later use, not a far-fetched hypothetical. list_all/get (+ update) are the read/edit API that view needs; removing tested working methods only to re-add them is negative-value churn (and would force rewriting a legitimate upsert test's observation). Neutralised the audit's 'dead weight?' concern by DOCUMENTING intent in the ImportProfileRepository module docstring (kept-not-deleted, remove only if the view is dropped from the roadmap). No behavior change.

- ✅ [FIBR-0075] **Bound PDF per-page decompressed content size (decompression-bomb / zip-bomb vector).**
  Caps today are whole-file bytes (16 MiB), page count (500), and extracted row count (100k) — none bound the DECOMPRESSED size of a page's Flate-compressed content stream, so a small in-cap PDF can expand to GBs before extract_tables()/extract_text() returns (on the UI thread). security-model.md §5 explicitly names FIBR-0009 as responsible for THIS vector, but the code doesn't implement it — a real spec-vs-code gap. Non-trivial: pdfplumber/pdfminer don't easily expose a streaming size bound; likely needs a pdfminer-level limit or a subprocess with rlimits. Investigate + implement, or document the residual risk explicitly.
  **Layman:** A small, valid PDF whose page decompresses to gigabytes could hang or OOM the app when imported.
  Kind: security.
  Source: indie-review-2026-07-10 loop-2 (statement H2).
  Resolved (2026-07-10): assessed + documented as accepted residual risk (the roadmap-sanctioned option; user deferred the call to me). security-model.md INV-5b previously implied FIBR-0009 bounds the decompression/zip-bomb vector — the code does NOT (caps are file-size 16 MiB / 500 pages / 100k rows; none bound a page's DECOMPRESSED Flate stream). INV-5b now states this honestly: the decompressed-size residual is ACCEPTED for a local single-user app (threat = the user opening a file they chose, not a server ingesting untrusted uploads); the robust fix (extraction in a memory-capped subprocess — POSIX RLIMIT_AS / Windows Job Objects) is disproportionate + cross-platform-heavy, and pdfplumber/pdfminer expose no cheap in-process streaming bound. T5 row annotated with the residual + pointer. Revisit if PDFs ever arrive from an untrusted channel. No code change — a spec-vs-code gap closed by making the claim honest.

- ✅ [FIBR-0076] **Single-instance / busy_timeout handling so two app copies don't crash with a raw OperationalError.**
  _connect sets PRAGMA key + foreign_keys only; SQLite default busy_timeout is 0. Two instances (or a slow backup/AV holding a read lock) make the second write raise sqlite3.OperationalError uncaught -> unhandled traceback. Add PRAGMA busy_timeout and/or an explicit single-instance guard (QLocalServer / lockfile) at the app layer.
  Kind: fix.
  Source: indie-review-2026-07-10 loop-2 (crypto M2).
  Resolved (2026-07-10): _connect now issues `PRAGMA busy_timeout = 5000` (vault.py) — a second instance or a slow backup/AV holding a transient lock now serialises via SQLite's locking (waiting up to 5s) instead of the second write raising a raw sqlite3.OperationalError. This fixes the reported crash symptom; SQLite's file locking already guarantees no corruption under concurrent access, so the busy_timeout is sufficient. A QLocalServer/lockfile single-instance guard (preventing two windows at all) was considered but is a UX nicety, not required for crash-safety — deliberately NOT built (simplicity-first). Regression test asserts the PRAGMA value.

- ✅ [FIBR-0077] **Explicitly pin PRAGMA cipher_use_hmac = ON in _connect (defense-in-depth for INV-1 tamper-evidence).**
  security-model.md INV-1 states tamper-detection as a code guarantee, but _connect never sets cipher_use_hmac — it rests entirely on sqlcipher3-binary==0.6.0's SQLCipher-4 default. A future dep bump changing the default would silently weaken it (global rule §5). NOTE: FIBR-0004 D4 deliberately chose to ASSERT the default rather than re-configure it (test-covered), so this is a spec-level decision to reconsider, not a drive-by — needs a D4 revisit before changing.
  Kind: security.
  Source: indie-review-2026-07-10 loop-2 (crypto M4, flagged x2).
  Resolved (2026-07-10): D4 revisit conclusion — pin it. _connect now issues `PRAGMA cipher_use_hmac = ON` explicitly right after `PRAGMA key` (vault.py), so INV-1 tamper-evidence is correct-by-construction rather than resting on sqlcipher3-binary's SQLCipher-4 default (which a future dep bump could flip, global rule §5). Every vault is created with the default ON, so pinning ON can never mismatch an existing file. FIBR-0004 D4 spec text updated with the revisit note; the existing INV-1 assert stays as the regression check. New test_connection_pins_hmac_and_busy_timeout covers it. Gate green.

- ✅ [FIBR-0078] **Move the Standard Bank row cap before the per-family parse (bounds computation, not just the result).**
  standard_bank.parse checks len(result.drafts) > _MAX_PDF_ROWS only AFTER _parse_family_* has run full regex + Decimal parsing over every region line — a crafted PDF with millions of transaction-shaped lines does all that work before rejection. pdf_importer.py checks its cap earlier (cheaper). Add a cheap pre-parse region-line count guard. NOTE: the current ordering is spec-consistent (FIBR-0050 Deliverable 1), so changing it needs a FIBR-0050 spec update.
  Kind: perf.
  Source: indie-review-2026-07-10 loop-2 (statement H3).
  Resolved (2026-07-10): standard_bank.parse now rejects len(region_lines) > _MAX_PDF_ROWS immediately after building region_lines — before _detect_number_format and the per-family regex/Decimal pass — so a crafted PDF with millions of transaction-shaped region lines is refused before that expensive work (bounds the computation, not just the result). The exact post-parse len(result.drafts) > _MAX_PDF_ROWS cap (FIBR-0050 Deliverable 1 / INV-14) is retained for precision (Family C de-interleaves ~2 drafts/line). FIBR-0050 spec Deliverable updated. The existing over-cap monkeypatch test (INV-14) now exercises the early guard with the same friendly ValueError; 83 SB/PDF tests green, ruff clean.

- ✅ [FIBR-0079] **Gate RuleEditDialog OK on a selectable category (zero-leaf-categories edge) + honest selected_category_id return type.**
  If a user deletes every leaf category, RuleEditDialog's combo is empty, selected_category_id() returns None (despite its -> int hint), and OK stays enabled -> add_rule(pattern, None) surfaces the confusing 'a category must be a leaf, not a Type' instead of 'create a category first'. Gate OK on combo.count() > 0 (or block Add/Edit when leaf_categories() is empty) and type selected_category_id() as int | None. FIBR-0010 D13's 'no ValueError reaches a caller through the dialog' silently fails to cover zero-leaves.
  Kind: ux.
  Source: indie-review-2026-07-10 loop-2 (core-services + ui-dialogs M2).
  Resolved (2026-07-10): RuleEditDialog._sync_ok now also requires self._category.count() > 0, so OK stays disabled with zero leaf categories; selected_category_id() typed int | None (honest). RulesWidget._on_add blocks up front with a "Create a category first, then add a rule." message when leaf_categories() is empty — the reachable path (the _on_edit + learning paths can't hit zero-leaves, since an existing rule / a manual pick both imply a live category). _apply_add/_apply_edit/_apply_learned_rule add a defensive None guard (narrows for the int-typed add_rule/update_rule). FIBR-0010 D13 spec updated to cover the edge. TDD: 2 red→green tests (dialog OK disabled with empty leaves + selected_category_id None; Add blocked + message shown). mypy 0, 74 tests pass.

- ✅ [FIBR-0080] **Route the two hand-rolled settings reads through SettingsRepository.get.**
  services/transactions.py read_minor_unit_exponent + TransactionService.base_currency hand-roll SELECT value FROM settings WHERE key=... instead of SettingsRepository(conn).get(key) (already used by auth.py). Reuse-before-rewrite (CLAUDE.md §3); a typo'd key in one copy has no lint signal. read_minor_unit_exponent needs None/int-cast handling.
  Kind: refactor.
  Source: indie-review-2026-07-10 loop-2 (data M-1).
  Resolved (2026-07-10): read_minor_unit_exponent + TransactionService.base_currency now route through SettingsRepository(conn).get(key) (services/transactions.py) instead of hand-rolling the SELECT — one seam for the key strings (reuse, CLAUDE.md §3). cast(str, value) preserves the v1-invariant 'always present' assumption per the repo's assert-over-can't-happen convention. mypy 0, 171 affected tests pass.

- ✅ [FIBR-0081] **Small type/doc debt: _on_move Literal typing, _selected_row dedup, FIBR-0007 stale INV-7 insert-order narrative.**
  (1) ui/rules.py _on_move takes direction:str + a type:ignore against move_rule's Literal['up','down'] — type the param as Literal to drop the workaround (global rule §1). (2) _selected_row is byte-identical in rules.py + statements.py (2 sites — extract on the 3rd). (3) FIBR-0007 spec's INV-7 test narrative describes the OLD insert order (transactions-before-period); FIBR-0052's statement_period_id FK reversed it (period-first) — update the spec text (or a FIBR-0052 addendum) so a reader doesn't reason about a stale order.
  Kind: doc-fix.
  Source: indie-review-2026-07-10 loop-2 (misc LOW).
  Resolved (2026-07-10): (1) ui/rules.py _on_move now types direction as Literal['up','down'], dropping the # type: ignore[arg-type] against move_rule. (3) FIBR-0007 spec INV-7 narrative corrected with a FIBR-0052 addendum — commit_import inserts the period row first (statement_period_id FK) then the transactions batch, and the wedge test raises on the transactions INSERT. (2) _selected_row dedup deliberately NOT done — only 2 sites, Rule-of-Three defers extraction to the 3rd (CLAUDE.md §3).

- 📋 [FIBR-0102] **Tighten mypy toward strict.**
  Verified 2026-07-11: [tool.mypy] sets only python_version + per-module stub-ignores — NOT strict. Enable strict (or stage it: disallow_untyped_defs, warn_return_any, disallow_any_generics, no_implicit_optional) to catch a class of bugs at the type layer — valuable for a money app. Incremental: turn flags on one at a time, fix the fallout, keep the gate green each step. Deps: none (gate/CI config).
  **Layman:** Turn on stricter automatic type-checking to catch more bugs before they ship.
  Kind: refactor.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0103] **Consolidate presentation formatting into one module.**
  FIBR-0083 introduces src/finbreak/datetime_format.py (date/time display). Fold the existing amount/currency QLocale formatting (ui/home.py::_format_amount -> QLocale.toCurrencyString) into a shared formatting package alongside it, so all presentation logic is centralised + unit-tested in one place (Rule of Three: date + currency + future). Deps: FIBR-0083 (lands the first formatter). Small refactor; do AFTER FIBR-0083 ships.
  **Layman:** Keep all the 'how numbers and dates look' code in one tidy, tested place.
  Kind: refactor.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0141] **CategoryService.update_category has no descendant-cycle guard — re-parenting a category under its own child creates a cycle.**
  Found during the FIBR-0138 close (indie-review). `update_category`
  (`src/finbreak/services/categories.py`) blocks re-parenting a *root* and
  requires an existing parent, but does NOT reject moving a category under
  one of its own descendants — so X→Y→X cycles are reachable via the UI.
  `categorization.type_of` already fails loud (ValueError) on such a cycle,
  and FIBR-0138's `drill_down` was hardened to stay total against it, but
  the ROOT CAUSE is the missing guard here. Fix: in `update_category`,
  reject a `parent_id` that is the subject itself or any of its
  descendants (ascend the prospective parent's chain; if the subject is
  encountered, raise ValueError). Add a reproduce-first test. Small,
  self-contained.
  **Layman:** You can accidentally make the category tree loop back on itself (put a group inside one of its own sub-groups), which confuses the parts of the app that walk the tree; the app should refuse that move.
  Kind: fix.
  Source: indie-review-2026-07-14 (FIBR-0138 close).

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
