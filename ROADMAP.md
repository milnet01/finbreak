<!-- ants-roadmap-format: 1 -->
# Fin_Break — Roadmap

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

- 📋 [FIBR-0001] **P01: project skeleton + lint + format
  + test + security-scan harness.** `pyproject.toml` (Python
  3.12+), `pip`+`venv` dev env, `ruff check` and `ruff format
  --check` clean on placeholder source, `pytest` exits 0 on an
  empty suite, **`bandit`, `pip-audit`, and `gitleaks` exit 0**.
  `.github/workflows/ci.yml` runs the same gates, and
  `scripts/ci-local.sh` mirrors them one-for-one (single source
  of truth for the gate list) so issues are caught before
  pushing. Dependencies: none. Lanes: build, ci, tests,
  security. Kind: chore. Source: planned.

- 📋 [FIBR-0002] **P01: `.gitignore` + secret-leak
  guard.** Standard Python ignore set (build artefacts,
  `.venv`, `__pycache__`, dep caches, IDE/OS files) plus
  explicit ignores for any local vault/`*.db`/`*.dmg`/AppImage
  build output, so **no financial data or build secret can ever
  be staged**. `gitleaks` (from FIBR-0001) is the backstop.
  Dependencies: FIBR-0001. Lanes: build, security. Kind: chore.
  Source: planned.

### 📦 Packaging

- 📋 [FIBR-0003] **P01: bundling smoke-test (de-risk
  native libs early).** Freeze the trivial placeholder app into
  a one-file **AppImage** *and* a PyInstaller bundle, then launch
  each on a clean target with **no Python installed**, confirming
  the CPython runtime + a stub SQLCipher/Qt load. This surfaces
  the native-lib collection risk named in ADR-0007 *now*, not
  after ten phases are built on top. Full multi-platform
  packaging + publish pipeline is deferred to P13. Dependencies:
  FIBR-0001. Lanes: build, ci. Kind: chore. Source: planned.

---

## P02 — Vertical slice: the security spine (target: after P01)

**Theme:** the smallest end-to-end feature that touches every
layer — and deliberately the **encrypted-storage spine**, since
security is the load-bearing concern. Proves UI → service →
repository → encrypted vault → output → test before any feature
lands on top.

### 🔒 Security

- 📋 [FIBR-0004] **P02: master password → encrypted vault
  → one manual transaction → table → lock.** First-run sets the
  master password + base currency; `CryptoService` derives the
  key with **Argon2id** (parameters pinned in the spec) and
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

---

## P03 — Accounts

### 🎨 Features

- 📋 [FIBR-0005] **P03: multiple accounts per profile.**
  Account model + CRUD + accounts-manager UI; each account
  tagged with a type (current, savings, credit card, personal
  loan, home loan, investment, other). Transactions belong to an
  account — this must exist before any import. Dependencies:
  FIBR-0004. Lanes: ui, services, repo, tests. Kind: implement.
  Source: planned.

---

## P04 — Category tree

### 🎨 Features

- 📋 [FIBR-0006] **P04: Type → Category tree (3rd level
  ready).** Self-referential `categories` table (`parent_id`),
  seeded Income/Expenditure types with sensible default
  categories (salary, sales / fast food, bills, medical,
  lottery…), and a category-management UI exposing two levels.
  Data model supports a future Sub-category level without
  migration. Dependencies: FIBR-0004. Lanes: services, repo, ui,
  tests. Kind: implement. Source: planned.

---

## P05 — CSV import + mapping profiles

### 🎨 Features

- 📋 [FIBR-0007] **P05: CSV import with per-bank mapping
  profiles + dedup + import wizard.** `ImportService`
  orchestration + `CsvImporter` + saved per-bank column-mapping
  profiles (ADR-0005); de-duplication so re-importing an
  overlapping statement adds **zero** duplicates (success
  criterion 2); import wizard with a preview that shows per-row
  parse errors *before* anything is written. The first real
  import path; establishes the pipeline P06/P07 reuse.
  Dependencies: FIBR-0005, FIBR-0006. Lanes: services, importers, ui,
  repo, tests. Kind: implement. Source: planned.

---

## P06 — OFX import

### 🎨 Features

- 📋 [FIBR-0008] **P06: OFX import.** `OfxImporter` via
  `ofxparse`, feeding the same `ImportService` pipeline (dedup,
  categorisation, transfer detection) built in P05. OFX is a
  worldwide standard needing no mapping profile. Dependencies:
  FIBR-0007. Lanes: importers, services, tests. Kind: implement.
  Source: planned.

---

## P07 — PDF statement import (incl. locked PDFs)

### 🎨 Features · 🔒 Security

- 📋 [FIBR-0009] **P07: PDF statement import with
  in-memory decrypt.** `PdfImporter` (`pdfplumber` text/table
  extraction) on the P05 pipeline; password-protected statements
  are decrypted **in memory only** (`pikepdf`, never written
  decrypted to disk); opt-in "remember this password" stores it
  **encrypted in the vault** against the account (default:
  prompt each time, store nothing). A wrong PDF password
  re-prompts rather than aborting the import. Dependencies: FIBR-0007.
  Lanes: importers, services, security, ui, tests. Kind:
  implement. Source: planned.

---

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

---

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
