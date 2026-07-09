# finbreak — Workflow state

## §1. Status header

| Field | Value |
|-------|-------|
| **Project phase** | P07.6 — Tabbed main window (shell v2) (FIBR-0052) |
| **Active item ID** | FIBR-0052 (P07.6 tabbed main window — **design brainstormed + APPROVED by the user 2026-07-09**, spec not yet written). Round 1 of a tabbed-workspace evolution: content area → QTabWidget with FIXED tabs **Home · Statements · Accounts · Categories** (mirrored under View); **Home button added to the toolbar** (Home · Manual entry · Import · Accounts · Categories · Lock); **Statements tab read-only** this round (lists imports from `statement_periods`; SPEC-TIME VERIFY all importers write it); Home = advice + txn table (optional money-in/out line); **window geometry** (size/position + last tab) via QSettings OUTSIDE the vault + **Center-window** + **Reset-layout** actions; lock still tears down the whole workspace (FIBR-0051 INV-3 holds). Retire the now-redundant Accounts/Categories `done` "back to Home" button in tab mode. **Staging (separate later items):** Round 2 = Statements first-class (per-txn import-provenance stamp = schema change → per-statement drill-down + undo-import); Round 3 = Home dashboard (income/expenditure summary + category breakdown, = FIBR-0012, BLOCKED on P08 category-link + P09 transfer-detection for correct totals). Deps: FIBR-0051 (shell); independent of P08/P09, runs before them. **P08/FIBR-0010 rules now follows FIBR-0052.** |
| **Active step** | 1 (design APPROVED — next: write `docs/specs/FIBR-0052.md` from the approved Round-1 design above, then `/cold-eyes` to convergence before code — global rule § 14. NOTE: the HARD-GATE is cleared — user approved the design 2026-07-09; go straight to spec-writing.) |
| **Blocked on** | — |
| **Last update** | 2026-07-09 (**FIBR-0052 opened + design APPROVED** — after FIBR-0051 shipped, the user asked to evolve the shell: (1) tabs for the main window (Home/Statements/Accounts/Categories), (2) Home = advice + income/expenditure summary + breakdown, (3) everything under View as tabs (+ keep the menu), (4) remember window geometry + a Center-window action; plus a follow-up: (5) add a Home button to the toolbar. Ran the brainstorming skill. Surfaced the non-obvious costs: transactions carry NO statement-provenance today (verified — `transactions` has no statement link, only `statement_periods` for dedup), so per-statement drill-down needs a schema stamp; and the Home income/expenditure summary is the dashboard (FIBR-0012), BLOCKED on P08 category-link + P09 transfer-detection for correct totals (self-transfers double-count otherwise). User deferred sequencing to me. **Staged into 3 rounds** — filed **FIBR-0052** (P07.6) as Round 1 (tabbed shell + Home toolbar button + window geometry, Statements tab read-only); Round 2 = Statements first-class (provenance stamp + undo-import); Round 3 = Home dashboard (after P08/P09). Design APPROVED by the user; next session writes `docs/specs/FIBR-0052.md` → `/cold-eyes`. **P08/FIBR-0010 now follows FIBR-0052.** User is relaunching the terminal + compacting before continuing.) — prior: 2026-07-09 (**FIBR-0051 CLOSED** by `/close-phase` — P07.5 app-shell shipped. TDD: 22-test `tests/features/app_shell/` (INV-1..10 + subs) → the 10 Deliverables to green: the `MainWindow(QMainWindow)` shell + state machine (destroy-on-lock content hygiene, INV-3), `HomeView` (empty/table toggle), `ManualEntryDialog`, the first-run/unlock `QWidget → QDialog` re-home (mid-derivation dismissal no-ops, INV-2f), the SVG toolbar glyphs + loader (package-data + PyInstaller `--add-data`; `_selftest` icon-render leg, DoD #2), the Donate menu. D10 ripple re-homed `test_vault.py` + `test_accounts.py` assertions to the split widgets. Gate green **299 passed/1 skipped**, mypy 0; FIBR-0003 build smoke **PASS** (icons travel). Close: `/audit` (ruff/bandit/semgrep/shellcheck/gitleaks) **0**; `/indie-review` **2 cold lanes** (shell+dialogs security/lifetime; home+tests+packaging) — **no CRIT/HIGH/MED**, security spine INV-3/4/4a/4b/5 verified correct; **2 LOW** (status-bar Ready restore off `messageChanged`; locale-hermetic `_format_amount` test) + **1 INFO** (`QIcon`-absent rationale — verified false, corrected comment + spec §13) folded inline. One gitleaks false positive (`shiboken6.isValid` in spec prose) handled in `.gitleaks.toml`, allowlist unchanged. ROADMAP FIBR-0051 → ✅, **FIBR-0040 → ✅** (donate links delivered), FIBR-0049 stays open (field hints remain). Journal `docs/journal/FIBR-0051.md`; tag `FIBR-0051-complete`.) — prior: 2026-07-09 (**FIBR-0051 spec cold-eyes CONVERGED** after 11 loops (6–11 run this session post usage-reset). Loops 6–11 fixed: M1 unreachable zero-accounts branch (dropped `AccountService` from `HomeView`); INV-9 empty-picker reframed defensive-untested; D2 inverted worker/dialog lifetime; `HomeView.current_page()` accessor + inner-page objectNames; a self-inflicted CRIT in loop 9 (INV-4b `self._dialog is None` unsatisfiable — step 5 re-opens the tracked `UnlockDialog`); INV-8a FUNDING.yml stdlib flow-sequence parse; `coding.md § 1.1` + FIBR-0023 gloss cross-doc fixes; `design.md` "dark theme" relabel; ROADMAP FIBR-0039/0040/0049 reconciliation (FIBR-0051 closes FIBR-0040, partially delivers FIBR-0049). Accuracy + cross-doc lanes ended fully clean. Signed off under the user's polish-only rule. Next: TDD → `/close-phase`.) — prior: 2026-07-05 (**NEW ACTIVE ITEM FIBR-0051** — app-shell UX redesign. User delegated "what's next"; chose the queued app-shell redesign → brainstormed (7 Qs: scope=full-dashboard-eventually, sequenced as 4 pieces, shell-first, locked-view=full-window+popup, manual-entry=popup dialog, +status bar, +Donate menu). Filed FIBR-0051 as new phase P07.5 (roadmap `features-ux` section, no downstream renumber). Verified all reshaped interfaces + PySide6 6.11.1 APIs empirically (§13). Wrote the spec (INV-1..10, D1..10, test-ripple named). Next: `/cold-eyes` → TDD → `/close-phase`.) — prior FIBR-0050 open: 2026-07-05 (FIBR-0050 **CLOSED** by `/close-phase` — one Standard Bank text-layer reader for all six account types shipped. Spec cold-eyes-converged (9 loops); TDD (36 tests); validated end-to-end on all 6 real statements. Close: `/audit` clean; `/indie-review` 2 cold rounds — round 1 fixed the code findings, a confirming re-review fixed 1 HIGH (corrupt-PDF Qt-slot crash) + 2 MED (region-scoped number detect, INV-12 test correction) + 2 LOW (Family-C fold, `_cc_opening` sign), final cold pair clean. Gate green 277 passed/1 skipped, mypy 0. Fixtures 100% synthetic. Journal `docs/journal/FIBR-0050.md`; tag `FIBR-0050-complete`.) — prior FIBR-0050 open: 2026-07-04 (FIBR-0009 **CLOSED** by `/close-phase` — P07 PDF import shipped. TDD: 41-test `tests/features/pdf_import/` + the extract-then-CSV-adapter `PdfImporter` (in-memory `pikepdf` decrypt, D8 grouping / D13 uniquify), the v5 migration, accounts credential accessors, the D10 rename, the wizard PDF branch + `password_dialog`, the `_selftest` pdfplumber leg. Schema ripple `==4`→`==5` across 5 suites. Gate green 240 passed/1 skipped, mypy 0; FIBR-0003 build smoke PASS. Close: `/audit` 0, `/indie-review` 3 cold lanes (2 clean, 1 LOW coverage-gap fixed inline). Also: repointed stale `.venv` shebangs (dir-rename fallout); created + pinned a `finbreak.desktop` launcher (runs current `src/`); Ants-MCP feedback re-verified (ANTS-3438 still reproduces; 3439 moot for this project). Tag `FIBR-0009-complete`) |
| **Next gate** | FIBR-0052 step 1 — write `docs/specs/FIBR-0052.md` from the APPROVED Round-1 design (tabbed shell + Home toolbar button + window geometry; Statements tab read-only), then `/cold-eyes` to convergence (global rule § 14) before code. Then TDD → `/close-phase`. (After FIBR-0052: P08/FIBR-0010 rules, Round 2 Statements-first-class, P09/FIBR-0011 transfers, Round 3 Home dashboard/FIBR-0012.) |
| **Convergence checkpoint** | 5 (consecutive `FP##` items immediately preceding any ✅-`implement`-Kind close in the active release block — see `~/.claude/commands/close-phase.md § 5a-6`) |
| **Debt-sweep phase threshold** | 5 (auto-prompt for `/debt-sweep` after this many phases without one) |
| **Last debt sweep** | (none yet) |
| **Repo visibility** | PUBLIC (cached 2026-06-30; push freely per global rule § 6) |

### Step progress

While an item is active, Claude marks the current step 🚧;
completed steps flip to ✅. Resets to all ⬜ when a new item
becomes active.

1. 🚧 Write + cold-eyes spec (`docs/specs/FIBR-0052.md` — design APPROVED 2026-07-09; write it, then `/cold-eyes` to convergence)
2. ⬜ Verify dependencies on the roadmap DAG (FIBR-0051 ✅; independent of P08/P09)
3. ⬜ Write failing tests
4. ⬜ Implement until tests pass
5. ⬜ Run `/audit`
6. ⬜ Run `/indie-review`
7. ⬜ Fold / fix actionable findings
8. ⬜ Update CHANGELOG / ROADMAP / journal
9. ⬜ Commit, tag `<ID>-complete` (clean close only), push

### FIBR-0009 close record (P07, closed 2026-07-04)

TDD: 41-test `tests/features/pdf_import/` red → the 9 Deliverables to green
(the extract-then-CSV-adapter `PdfImporter`, in-memory `pikepdf` decrypt, v5
migration, credential accessors, D10 rename, wizard PDF branch +
`password_dialog`, `_selftest` pdfplumber leg). Schema ripple `==4`→`==5` across
vault/accounts/categories/import_/ofx_import. Gate green **240 passed / 1
skipped**, mypy 0; FIBR-0003 build smoke **PASS** (native PDF tree travels).
Close (steps 5–9): `/audit` **0**; `/indie-review` 3 cold lanes — 2 CLEAN, 1
actionable LOW (INV-4 unencrypted-PDF-ignores-stored-password coverage gap)
**fixed inline**, informational notes accepted. Allowlist unchanged. Fixture
`Description`-column deviation surfaced in the spec (§14). Tag
`FIBR-0009-complete`.

### FIBR-0004 close record (P02, closed 2026-07-02)

Steps 1–4 (spec cold-eyed + signed off; TDD; implement) then 5–9:
`/audit` (Ants `audit_run`, full scope) + `/indie-review` (4 cold lanes)
run **three rounds**; every actionable finding fixed inline per the user's
standing directive (no FP## deferral). Round 1: 10 findings (2 HIGH). Round 2:
new HIGH (idle-lock UI crash) + MEDIUMs. Round 3: doc/defensive/test hardening,
converged. Live language switching deferred → FIBR-0017. Final: gate green
74 passed / 1 skipped, mypy 0, audit 0. Tagged `FIBR-0004-complete`.

### Active item details

(filled in once Phase A → P01 hands over an active item)

```
Item: FIBR-0004 (P02 Vertical slice — master password → Argon2id → SQLCipher
      vault → one manual transaction → table → lock)
Spec: docs/specs/FIBR-0004.md (not yet written — Step 1 drafts it)
Depends: FIBR-0001 (✅ closed 2026-07-01). Phase-ordering also puts FIBR-0002
         (✅) and FIBR-0003 (✅) ahead, but they are not code prerequisites.
Branch: implement-Kind item — PR-based flow may apply (see global rule § 7);
        confirm branch at Step 1.
Next: Step 1 — write/expand the FIBR-0004 spec (security spine; cite
      security-model.md INV-2 Argon2id params), /cold-eyes it, then TDD loop
Tests: (harness green; 27 passing, 1 skipped after FIBR-0003 close)
```

## §2. Workflow rules

The canonical rules — phases A–D, the per-phase 9-step loop,
ID scheme, triage table, fold-into-roadmap pattern,
false-positive learning loop, drift handling, Definition of
Done — live in
`~/.claude/skills/app-workflow/SKILL.md`.
Skills don't auto-load from filesystem presence — they fire
on description-match against your message. To engage the
workflow in a session, mention any of: phase / audit / drift
/ fix-pass / "where were we" / "resume" / "continue work" /
this `workflow.md` file by name. The project's `CLAUDE.md`
(loaded automatically on session start) reminds you of this
on every resume.

**Hard rule kept inline (most-load-bearing):** never silently
drift. If code being written diverges from the spec, stop and
surface. Either the spec was wrong (update spec → re-audit
affected sections → resume) or the code was wrong (fix code,
no spec change). Never both papered-over.

To refresh this file from the (upgraded) skill template, copy
`~/.claude/skills/app-workflow/templates/.claude/workflow.md`
over this file — preserve §1 (status header) and §3 (session
journal); §2 is the only part that changes.

## §3. Session journal

Append-only. Newest at the top.

### 2026-07-05 — FIBR-0051 opened: app-shell UX redesign brainstormed + spec drafted

User delegated "what to tackle next"; I surfaced the two candidates (the queued
app-shell redesign vs the phase-ordered P08 rules engine) and the user chose the
**app-shell redesign**. Ran the brainstorming skill (design-approval gate applies).
Seven decisions, one at a time: scope = *eventually the full dashboard* → but I
**flagged the hard dependency** (the "spending by category" pie needs the
transaction→category link deferred to P08, and correct totals need P09 transfer
detection — neither built), so the user chose **"everything now, in order"** →
**decomposed into 4 pieces** built as separate spec→cold-eyes→TDD cycles:
**shell (FIBR-0051)** → P08 rules+category-link (FIBR-0010) → P09 transfers
(FIBR-0011) → P10 dashboard (FIBR-0012). User confirmed **shell-first** (later
features plug into the finished frame, no rewiring). Design: `QMainWindow` with
menubar (File/View/Help/**Donate**) + icon toolbar + **status bar** (user-added
request) + central content stack; first-run & unlock become **popup dialogs over
the window** (locked view = full window, chrome greyed, 🔒 Locked placeholder +
unlock popup); manual entry = **popup dialog**; Donate menu → the three
`.github/FUNDING.yml` links via `QDesktopServices`. All design sections approved.

Filed **FIBR-0051** as a new phase **P07.5** (roadmap `features-ux` section,
inserted between P07 and P08 with a distinct sub-heading so the existing
`features-N` slugs did **not** renumber; no downstream churn). Verified every
reshaped interface (AuthService, FirstRun/Unlock widgets' signals,
`presence_state` states, the content widgets' `done` signal, the routing
test-ripple sites) **and** the PySide6 6.11.1 shell APIs (QAction in QtGui,
QMainWindow/QStatusBar methods, QDesktopServices.openUrl, ToolButtonTextUnderIcon)
empirically (§13). Wrote `docs/specs/FIBR-0051.md` — INV-1..10 (structure, 3-state
routing, **no-data-while-locked** security, auto-lock returns to locked shell,
key-lifetime untouched, content routing, status bar, Donate no-network,
manual-entry round-trip, i18n/RTL), D1..10, Deliverables (incl. the named
routing/`MainWindow` test ripple), **no schema change / no new dependency**.

Next: `/cold-eyes` the spec to convergence (global rule § 14, loop 2+ cold), then
TDD → `/close-phase`. Committed the roadmap item + spec draft as the checkpoint.

### 2026-07-05 — FIBR-0050 CLOSED by /close-phase (Standard Bank text-parser)

Standard Bank text-parser (FIBR-0050) shipped: one text-layer reader for all six
account types, validated end-to-end on all **six real statements** (checksums pass)
+ 13 synthetic fixtures. Spec cold-eyes-converged (9 loops); TDD (36 tests).

**Close (steps 5–9):** `/audit` **clean**; `/indie-review` ran **two cold rounds**.
Round 1 fixed the code findings (credit-card de-interleave crash/mis-split HIGH,
`_decrypt_pdf` crash net, INV-7b sign-agreement gate, row-like-but-unmatched →
raise). A **confirming cold re-review** (2 independent reviewers, briefed cold)
then found + fixed **1 HIGH** — a corrupt file passing the `%PDF-` sniff raises
`pikepdf.PdfError` (NOT a `ValueError`/`OSError`, and NOT a `PasswordError`
subclass), which escaped `_decrypt_pdf`'s net and crashed the Qt slot; reproduced,
then added `PdfError` to the net — plus **2 MED** (`_detect_number_format` scoped to
`full_text` not the region per D9; a vacuous INV-12 no-leak assertion checking the
document password instead of the attempted one) and **2 LOW** (Family-C zero-date
continuation now folds per INV-10; `_cc_opening` now honours the printed sign). One
accepted fail-safe limitation documented (`_capture_closing` substring match —
money-guarded, rejects-not-under-imports, not on real data). Final cold pair
**clean, no actionable**. Gate green **277 passed / 1 skipped**, mypy 0. ROADMAP
✅, CHANGELOG, `docs/journal/FIBR-0050.md`, tag `FIBR-0050-complete`. Allowlist
unchanged. Commits: `f49d726` (round-1 code fixes) → test-coverage fold →
`4f30e01` (re-review fixes) → close.

**NEW user request (do AFTER FIBR-0050 close; user is compacting first, do NOT start
building yet):** app-shell / dashboard UX redesign — replace the current bare
first-run (tiny password box → manual-entry form) with a **full app window** (title
bar, menubar, a toolbar of icon shortcuts: import statement / manual entry / etc.,
and a main content area showing next-steps or loaded statements/transactions +
analysis). First run: show the whole app window, THEN a **first-run popup wizard**
for password creation. This is a proper feature → file as a roadmap item, brainstorm
+ design with the user (design-approval gate applies), then spec → cold-eyes → TDD.
Touches `ui/main_window.py`, `ui/first_run.py`, `ui/unlock.py`, `app.py`.

### 2026-07-04 — FIBR-0009 steps 3–4 (TDD + implement, gate + build smoke green)

Built the P07 PDF-import stack test-first against the 8-loop cold-eyes-converged
spec. Wrote `tests/features/pdf_import/{spec.md,test_pdf_import.py}` (40 tests,
INV-1..11 + INV-1a + INV-7a–f) **red**, then implemented the 9 Deliverables to
green: the pure-ish `importers/pdf_importer.py` (`candidate_tables` +
`group_tables_by_header` D8 grouping / D13 uniquify + `table_to_text`, in-memory
`pikepdf` normalise, page/row caps); `_migrate_to_v5` (nullable
`accounts.statement_pdf_password`, atomic; `LATEST` 4→5); accounts repo+service
`get/set_pdf_password` (kept off the `Account` object, D6); the D10 rename
(`_MAX_OFX_BYTES`→`_MAX_IMPORT_BYTES`, format-neutral read + OFX call-sites);
`ui/password_dialog.py`; the wizard PDF branch (`_select_pdf` +
`_extract_pdf_tables` prompt/re-prompt loop, chooser-reset **hoisted** before the
format dispatch, table chooser on the map step, profile pre-fill); and the
`_selftest.py` pdfplumber leg (embedded gridded blob).

**Fixture deviation surfaced (§14, not silent):** regenerated the three committed
fixture blobs with a **`Description`** column (header `Date, Description, Money
Out, Money In`) — the draft's `Date, Money Out, Money In` can't feed the reused
CSV pipeline (a blank description is a `parse_transaction` `ValueError`), so
INV-1/INV-7e would be untestable. Kept 3 data rows (cap tests intact). Annotated
the FIBR-0009 spec Deliverable 8 + the pdf_import test spec with the correction.

**Schema ripple:** the `== 4`/`LATEST_SCHEMA_VERSION == 4` "lands-at-latest"
asserts across vault/accounts/categories/import_/ofx_import bumped to `== 5`; the
`is_v4`/`at_v4` "current-latest" test names → `v5`; `test_INV8_v3_upgrades_to_v4`
kept its name (the v4 table-creation still happens) but its assert+comment bumped;
the OFX `no_schema_change` message re-expressed.

Verify: `./scripts/ci-local.sh` green — **239 passed / 1 skipped**, ruff + format
+ bandit + pip-audit + gitleaks clean, **mypy 0**. FIBR-0003 build smoke
(`build-smoke.sh`) **PASS** — both the onefile + AppImage print
`FINBREAK_SELFTEST_OK` in the Python-free clean-room, proving the native PDF tree
(Pillow, PDFium via `pypdfium2_raw`, cryptography) travels (`--collect-all` added).
Also repointed the stale `.venv` console-script shebangs (the venv predated the
Fin_Break→finbreak dir rename, so `ci-local.sh`'s bare tool calls hit "bad
interpreter"). Logged an Ants-MCP re-verification (ANTS-3438 still reproduces via
session_orient's codebase_index; ANTS-3439's Fin_Break repro now moot — dir
renamed).

Next: steps 5–9 — `/close-phase` (`/audit` + `/indie-review`, allowlist read
first, fold findings, then close: ROADMAP→✅, CHANGELOG, journal, tag).

### 2026-07-04 — FIBR-0009 spec drafted + `/cold-eyes` CONVERGED (P07 PDF import, 8 loops)

Opened P07. Brainstormed the core fork with the user (how to turn varied per-bank
PDF layouts into mappable columns) → **user approved the table-extraction
approach**: lift the transaction table via `pdfplumber.extract_tables()`, serialise
it to CSV text (`table_to_text`), and feed the **existing** CSV
mapping→parse→preview→dedup→commit pipeline verbatim (max reuse — the new importer
is an *extractor*, not a second parser). Locked PDFs decrypted **in memory only**
via `pikepdf` (never to disk, INV-2); opt-in remembered password stored inside the
already-encrypted vault (v5 nullable `accounts.statement_pdf_password`); wrong
password re-prompts. Empirically verified the whole chain before drafting (§13):
`pdfplumber 0.11.10` / `pikepdf 10.9.1`, extract_tables shape, `pikepdf.PasswordError`,
in-memory save-strip, owner-only behaviour, and the native transitive surface
(Pillow + pypdfium2/`pypdfium2_raw` + cryptography — a FIBR-0003 bundle obligation).

**Cold-eyes (global rule §14): 8 loops, 3 cold lanes/loop** (accuracy vs live
libs+reused code · implementability/testability · cross-doc). Trajectory:
**loop 2 = 1 CRITICAL self-correction** (my loop-1 "pdfplumber can't extract
owner-only" was a probe artifact — the sample table lacked grid lines, so
line-based detection returned `[]`; re-verified owner-only extracts fine + pikepdf
save-strips it; D3 re-justified on the clean `PasswordError` signal, not
"required"). Loops 3–5: test-completeness + testability precision (the 5-suite
schema-version ripple, the `$TMPDIR`+`tempfile.tempdir` filesystem sentinel, the
D13 header-uniquify, the credential service seam). **Loops 6–8: lanes 1+3 clean;
the residual HIGH/MED were all self-introduced doc-wording nits in the wizard
chooser-reset + test-ripple instructions** (fixed the OFX→PDF chooser leak by
hoisting both resets before the format dispatch). The **design was stable+clean
since loop 2**. User chose "one more pass then build" at the loop-5 guard; loop 8's
sole finding (1 MED wording self-consistency) was fixed + self-verified → **signed
off, cleared for code**. Committed + pushed each loop (`2fafb31` draft →
`53f5737`… → loop-8 sign-off).

Next: step 3 — write `tests/features/pdf_import/` red, then the 9 Deliverables to
green → `/close-phase`.

### 2026-07-04 — FIBR-0008 closed (P06 OFX import)

Cold-eyes loops 6–8 converged the spec (loop 6: 1 HIGH INV-1c contradiction +
1 MED `_show_preview` stash + 2 LOW; loop 7: 2 self-introduced doc nits; **loop
8 clean** across all 3 lanes) → signed off. TDD: wrote `tests/features/ofx_import/`
(33 tests) red, then implemented the pure `OfxImporter` (base.py move + D2
`_preview_from_result`/`preview_ofx`/`read_file_bytes` seam + wizard OFX branch +
`ofxparse==0.21`; **no schema change**, D9) to green. Fixed a **pre-existing
FIBR-0007 mypy error** the full-tree run surfaced (`_do_import` str|None).

Close (steps 5–9, autonomous): `/audit` (Ants) **0**; `/indie-review` 3 cold
lanes — 1 MED + 3 LOW test/coverage gaps + 1 INFO spec-drift **fixed inline**,
1 LOW (tz-`<DTPOSTED>` UTC day-shift) **deferred → FIBR-0042** (out of contract +
blocked by ofxparse's API). Gate green **199 passed / 1 skipped**, mypy 0.

**FIBR-0003 build smoke re-run (DoD #2 — native lxml must travel):** it caught a
**latent bug** — the clean-room bundle failed at `argon2`
(`ModuleNotFoundError`). Root cause: `_build-smoke-in-container.sh` installed a
hand-maintained dep list that never got `argon2-cffi` (added FIBR-0004; its slow
opt-in smoke wasn't re-run in the pure-Python P05–P07 phases since). Fixed at
root (no workaround): install runtime deps read straight from `pyproject`
(can't drift) + `--collect-all` the native packages, and added a fifth self-test
leg (`_check_ofxparse`) since `--self-test` never imports the app. Both onefile +
AppImage now print `FINBREAK_SELFTEST_OK` Python-free. Flipped ROADMAP
FIBR-0008 → ✅, wrote `docs/journal/FIBR-0008.md`, tag `FIBR-0008-complete`.
Allowlist unchanged (no false positives). Commits: `936171b` (spec converged),
`36589f0` (impl), `f8d3592` (close-review + build fix).

Next: FIBR-0009 (P07 PDF statement import) step 1 — draft/expand the spec
(`pdfplumber` + `pikepdf` for locked-PDF AES-decrypt, ADR-0004; feeds the same
ImportService pipeline), then `/cold-eyes` to convergence.

### 2026-07-03 — FIBR-0008 spec drafted + `/cold-eyes` (loops 1–3; loop 4 pending)

Opened P06 (OFX import). Verified the `ofxparse` 0.21 API **empirically** before
drafting (§13): `OfxParser.parse(BytesIO)` → signed-`Decimal` `.amount`, `.date`
datetime, `.payee`/`.memo`/`.id`/`.type`, `statement.start_date`/`.end_date`
(embedded span; **`''`** when absent), `ofx.accounts` list (incl. credit-card
`<CCSTMTRS>` with empty `account_type`), and the malformed-input exception
surface. Drafted `docs/specs/FIBR-0008.md` — a pure `OfxImporter` feeding the
**same** FIBR-0007 `ImportService` pipeline (D2 `_preview_from_result` split;
**no schema change**, D9 — reuses the v4 tables); period from embedded
DTSTART/DTEND (D4); no mapping profile (OFX self-describing); wizard OFX branch
that skips the mapping step (D10).

**Cold-eyes (global rule §14):** 3 cold lanes/loop (accuracy vs code+live
ofxparse · implementability · consistency), briefed identically each loop.
**Loop 1** 4 HIGH (multi-account flow + INV-7e; **D14** quiet-month period
predicate; the `''` missing-span sentinel; **D13**/INV-10 resource bounds +
security-model INV-5b binding). **Loop 2** 1 HIGH (`ofxparse` is NOT
pure-Python — pulls native `lxml`; corrected + documented the transitive/native
surface + FIBR-0003 bundling; filed **FIBR-0041** for the CSV resource-cap
back-fill). **Loop 3** **1 CRITICAL** — the error model wrongly assumed CSV-style
per-row tolerance; verified ofxparse parses **all-or-nothing per statement**
(a present-but-empty `<NAME>`/bad date/empty `<TRNAMT>` aborts the whole
statement). Added **D15** splitting the model (structural malformation →
whole-statement `ValueError`; post-parse `parse_transaction` rejection → per-row
`RowError`), rewrote INV-1c/INV-3/INV-4 + fixtures to use **absent** (not empty)
tags, pinned INV-1a's sign to `<TRNAMT>`. ~35 verified findings fixed over 3
loops; design converging (HIGH count 4→1→0, but loop 3 surfaced the CRITICAL).

**Loops 1–5 done; loop 6 pending.** Loop 4 was 0 CRIT/0 HIGH (polish). Loop 5
caught 2 more **subtle empirical** issues (a CRITICAL + HIGH, both localized
accuracy fixes, not design changes): an empty `<NAME>` does **not** abort a
statement in natural one-tag-per-line SGML (only the pathological no-whitespace
`<NAME><MEMO>` does) → re-pointed the canonical structural-abort fixture to a bad
`<DTPOSTED>` / empty `<TRNAMT>`; and `lxml` **is** loaded at runtime via
beautifulsoup4 (reworded "never imported" → "not used as the parser"). Totals
across 5 loops: **2 CRITICAL + 2 HIGH + ~50 findings** fixed; design + error
model stable and empirically verified since loop 3's D15 rewrite. Spec status:
`/cold-eyes` in progress, NOT yet cleared for code. FIBR-0041 (CSV size-cap
back-fill) filed under the security backlog. Committed + pushed each loop
(spec draft `a3f55bb`; loop 4 `cf6b276`; loop 5 `0fbee24`).

**Next session:** run loop 6 (confirming pass — likely clean or near-clean given
the trajectory); if clean, sign off `docs/specs/FIBR-0008.md` → TDD-implement
(step 3): write `tests/features/ofx_import/`, then `importers/base.py` +
`ofx_importer.py`, the `ImportService` `_preview_from_result`/`preview_ofx`/
`read_file_bytes` refactor, the wizard OFX branch, `pyproject` `ofxparse==0.21`,
to green → `/close-phase`.

### 2026-07-03 — FIBR-0007 closed (P05 CSV import)

Steps 5–9 of the loop, run autonomously (user out for the evening, standing
"do as much as you can" + fix-findings-inline rules). `/audit` (Ants
`audit_run`, scope since-tag:FIBR-0006-complete — ruff/bandit/semgrep) **0
findings**; `/indie-review` **3 cold lanes** (importer+service core, data
layer+migration, UI+wiring+tests), each briefed against the spec with no author
intent. Two lanes returned CLEAN; the UI lane found **one LOW** (preview showed
raw minor units `-1000` instead of `-10.00` — a real UX defect for the
non-technical target user) + **one INFO** (mapping form shows amount+debit+credit
combos regardless of style). Fixed the LOW inline — reused `to_display_decimal`
(public, no float) via the vault exponent, strengthened INV-10c to assert the
Amount cells render `-10.00`/`1000.00` — then a **cold re-audit** confirmed a
clean pair (0). INFO surfaced in the journal (optional show/hide polish, not
blocked). Gate green **165 passed / 1 skipped**, mypy 0. Flipped ROADMAP
FIBR-0007 → ✅ (resolution note), wrote `docs/journal/FIBR-0007.md`, tag
`FIBR-0007-complete`. Allowlist unchanged (no false positives).

Next: FIBR-0008 (P06 OFX import) step 1 — draft/expand the spec (OfxImporter via
`ofxparse` feeding the same ImportService pipeline; period from OFX's embedded
DTSTART/DTEND; no mapping profile — OFX is self-describing), then `/cold-eyes`
to convergence.

### 2026-07-03 — FIBR-0007 steps 3–4 (TDD + implement, gate green)

Built the P05 CSV-import stack test-first against the 9-loop cold-eyes-converged
spec (signed off; user's standing rule — no wait). **D12 conftest lift:**
`_build_v2_vault` moved from the categories suite to `tests/conftest.py` as
`build_v2_vault`, added `build_v3_vault` beside it (the v3→v4 fixture); categories
suite imports from conftest (22 tests still green). **Ripple:** the seven
"lands-at-latest" `==3`→`==4` schema-version assertions (vault ×1, accounts ×3,
categories ×3) + the two `…_is_v3_…`→`…_is_v4_…` renames; the `==1`/`==2` rollback
legs and the symbolic `LATEST+1` refusals untouched. Wrote
`tests/features/import_/{spec.md,test_import.py}` (43 tests, INV-1..11 incl.
INV-3a–d / INV-10a–e / INV-8's four legs), confirmed red, then implemented to
green: `models` (ImportProfile/StatementPeriod/ColumnMapping/TransactionDraft),
`_migrate_to_v4` (two tables, `LATEST` 3→4), `repositories/{import_profiles,
statement_periods}`, extended `repositories/transactions` (`existing_for` +
commit-free `add_batch`), extracted `read_minor_unit_exponent` (D5 reuse),
the pure `importers/csv_importer`, `services/import_` (match/upsert profiles,
multiset-delta dedup, atomic write + span-dedup), `ui/import_wizard`
(non-modal `QStackedLayout`, D9), and the `main_window`/`app` wiring.

Gate green: **165 passed / 1 skipped**, ruff + format + bandit + pip-audit +
gitleaks clean, mypy 0. Two bandit hits **root-caused, not suppressed** (global
rule § 1): B608 on f-string SQL → inlined the literal column lists (the
Account/Category repo convention, no `# nosec`); B101 asserts → `cast` (the
`AccountService` convention). One mypy mixed-list nit fixed by filtering the
`None` amount-style columns in a comprehension.

Next: steps 5–9 — `/close-phase` (`/audit` + `/indie-review` in parallel,
allowlist read first, then close or fix-pass).

### 2026-07-02 — FIBR-0006 closed (P04 Type → Category tree)

Steps 3–9 of the 9-step loop, run autonomously (user's standing rule: a
cold-eyes-converged spec I'm confident in is signed off — no wait). TDD:
lifted the raw-v1-vault builder to `tests/conftest.py`, rippled the four
schema-version assertions `== 2`→`== 3` + two accounts test renames, wrote
`tests/features/categories/` (22 tests) and saw them red, then implemented
`models`/`errors`/`migrations`/`repositories/categories`/`services/categories`/
`ui/categories` + the `main_window`/`app` wiring to green. `/audit` (Ants
`audit_run`, scope=files — ruff/bandit/semgrep/mypy) **0 findings**;
`/indie-review` (2 cold lanes over the data layer and the UI+tests) **0
actionable** — INFO-only (the cycle-guard deferral is spec-documented, the
`lastrowid` typing is `AccountRepository` parity). Folded one INFO inline
(INV-7f now asserts the actions re-enable when a category is re-selected).
One bandit B608 on an f-string SQL was root-caused (inlined the literal column
list, matching the codebase convention — no `# nosec`). Clean pair on the
closing pass. Gate green: 122 passed / 1 skipped, mypy 0. Flipped ROADMAP
FIBR-0006 → ✅, wrote `docs/journal/FIBR-0006.md`, tag `FIBR-0006-complete`.
Transaction→category link deferred to P08 (FIBR-0010) by design (D10).

Next: FIBR-0007 (P05 CSV import + per-bank mapping profiles + dedup + import
wizard) step 1 — draft/expand the spec, then `/cold-eyes` to convergence.

### 2026-07-02 — FIBR-0006 spec drafted + `/cold-eyes` (7 loops, converged)

Opened P04 (Type → Category tree). Verified the codebase seams before drafting
(§13): the FIBR-0005 migration runner (`run_migrations`/`_MIGRATIONS`/
`LATEST_SCHEMA_VERSION`, the runner-owned `BEGIN…COMMIT`/`ROLLBACK`), the
`PRAGMA foreign_keys = ON` seam that makes the self-referential FK real, the
`AccountRepository`/`AccountService`/`AccountsWidget` pattern this phase mirrors,
and the exact schema-version assertions in the vault + accounts suites. Drafted
`docs/specs/FIBR-0006.md` — the categories aggregate (repo → service →
`QTreeWidget` manager) + a v2→v3 migration step. Key design calls flagged for
sign-off: **Income/Expenditure are two seeded, protected root rows** in a pure
self-referential tree (kind token on roots only; D3–D5); **the transaction→
category link is deferred to P08/FIBR-0010** (D10 — keeps P04 surgical: a new
table + screen, transactions untouched); rich 16-category seed (D8); block-not-
cascade delete guards (D6).

**Cold-eyes (global rule §14):** 3 cold lanes/loop (accuracy · implementability ·
consistency), **7 loops**, 21 independent reviewers, ~30 verified findings fixed,
**0 CRITICAL throughout**, design stable since loop 2. Notable catches: loop 1 —
the "only vault-suite ripple" claim was wrong (the accounts suite has **three
more** schema assertions that flip `==2`→`==3` + two stale `_v2` test names), and
the seed enumeration dropped the `NOT NULL created_at` column; loop 2 — a `None`
parent could mint a **third root** (FK-exempt), and the INV-7 cite pointed at a
non-existent design.md section (added a "Category manager" component); loops 3–6
— test-mechanics precision (the atomic-rollback wedge, the conftest lift's hidden
`_params`/`_PW`/`derive_key` deps, the FK-ON-connection requirement) and two
wording nits my own fixes introduced. Loop 7 clean (0 CRIT/HIGH/MED/LOW, all
lanes). Also fixed two cross-doc items: added the design.md "Category manager"
component, and used `roadmap_log op:amend_body` to add FIBR-0005 to the ROADMAP
FIBR-0006 `Dependencies:` line.

Next: **user signs off `docs/specs/FIBR-0006.md`**, then Step 2 (deps FIBR-0004/
0005 ✅) → Step 3 (write failing tests, TDD) → Step 4 (implement).

### 2026-07-02 — FIBR-0005 closed (P03 accounts + forward-migration runner)

Steps 5–9 of the 9-step loop. `/audit` (Ants `audit_run`, scoped to the
FIBR-0005 diff) was clean every run (ruff/bandit/semgrep 0; one mypy
`annotation-unchecked` INFO note, later root-caused). `/indie-review` ran **two
rounds** — round 1: 4 cold reviewers (migration+vault, data layer, service+UI,
tests); round 2: 2 focused cold re-reviewers over exactly the changed files, to
catch fix-introduced defects. Every verified finding fixed inline (no FP##):

- MED (auth): opening a newer-than-supported vault raised `SchemaVersionError`,
  which `complete_unlock`'s `except DatabaseError` missed — leaked the un-wiped
  derived key (INV-3) + opaque crash. Now wipe on any `open()` failure +
  re-raise; unlock screen shows a distinct "newer version" message.
- MED (ui): the spec's "add/edit form" deliverable was unwired
  (`update_account` built+tested but unreachable → a mistyped name permanent).
  Wired an Update-selected edit path + INV-7f; added it to the spec's INV-7.
- HIGH (test): the INV-4 rollback test proved recoverability, not rollback —
  now asserts, on the same connection before reopen, `schema_version == 1`,
  accounts absent, rows intact (a true atomicity test).
- LOWs: symmetric `(ValueError, FinbreakError)` catch; `_FailAtRename`
  `__getattr__` passthrough; dropped a dead test line; a durability comment.

Clean pair on the closing round (audit 0, review 0 actionable — the one
residual MEDIUM is spec-conformant D8 shared-form UX, accepted for MVP). User
asked whether to allowlist the mypy note; root-caused it instead (two test fns
got `-> None`, which also type-checks their bodies) — allowlist stays empty.
Gate green: 100 passed / 1 skipped, mypy 0. Flipped ROADMAP FIBR-0005 → ✅,
wrote `docs/journal/FIBR-0005.md`, tag `FIBR-0005-complete`.

Next: FIBR-0006 (P04 Type→Category tree) step 1 — draft/expand the spec, then
`/cold-eyes` to convergence before code.

### 2026-07-01 — FIBR-0004 steps 3–4 (TDD + implement, gate green)

Built the P02 security spine TDD-first. Re-verified the crypto APIs empirically
in the venv before citing them (§13): argon2-cffi 25.1.0 `hash_secret_raw` → 32
deterministic bytes; sqlcipher3 raw-key open reports `cipher_use_hmac=1` /
`HMAC_SHA512` / page 4096, `isolation_level=""` (manual-commit), wrong-key →
`DatabaseError`, on-disk header not SQLite magic. Wrote
`tests/features/vault/{spec.md,test_vault.py}` (INV-1..8, incl. two `qtbot` UI
round-trips), confirmed failing on absent modules, then implemented:
`errors`, `models`, `crypto`, `paths`, `vault`, `repositories/transactions`,
`services/{auth,transactions}`, `ui/{_worker,first_run,unlock,main_window}`,
`app`; extended `_selftest` with the argon2 leg; `__main__` no-args now launches
the GUI (retired `FINBREAK_NOT_BUILT`, with the FIBR-0003 spec + bundling-spec
cross-refs updated); added `argon2-cffi==25.1.0`, removed the `-p no:pytest-qt`
line. `./scripts/ci-local.sh` exits 0 — **67 passed / 1 skipped**, bandit clean
(the raw-key f-string pragma did not trip B608 — DoD #2), pip-audit clean.

One structural call surfaced to the user (not a silent drift): added
`services/transactions.py` (`TransactionService` + pure `parse_transaction` /
`to_display_decimal`) to honour the spec's INV-4a "the service layer
reconstructs the display Decimal" under design.md's UI→Service→Repository layering.
One test-mechanism fix: INV-1's tamper leg flips a byte in **page 1** (the page
the schema read checks), per INV-1's stated first-read mechanism.

Next: steps 5–6 — `/audit` + `/indie-review` in parallel (allowlist read first).

### 2026-07-01 — FIBR-0004 spec drafted + `/cold-eyes` (6 loops)

Opened P02. Confirmed no PR-workflow opt-in (no marker/CODEOWNERS, all
direct `<ID>:` commits) → FIBR-0004 lands directly on `main`. Researched +
pinned the crypto-stack idioms (argon2-cffi 25.1.0 `hash_secret_raw` raw-key
API; sqlcipher3-binary 0.6.0 raw-key pragma + HMAC-SHA512 defaults + wrong-key
`DatabaseError`; `bytearray` wipe limits) before drafting, so the contract
cites real APIs (global rule §13). Drafted `docs/specs/FIBR-0004.md` — the
security-spine vertical slice (CryptoService→AuthService→Vault→one repo→3 UI
screens; 8 INVs mapping to security-model INV-1/2/3/8/9).

**Cold-eyes (global rule §14):** 2 lanes (accuracy; implementability), **6
loops**, 12 independent cold reviewers, ~75 verified findings fixed, **zero
CRITICAL** throughout, no regression survived past one loop. Notable catches:
the coding.md §7 gaps (`0o600` perms, atomic sidecar write, key-wipe-on-exit
leg of INV-3) at loop 3; the loop caught **3 defects I introduced while
fixing loop 4** (loop 5) and **2 more from loop-5 edits** (loop 6, the
"confirming pass" the user authorised at the max-loops cap) — including a
fabricated FIBR-0003 quote and an INV-2c `len(key)` over-reach. Design
defaults baked in + flagged for sign-off: money as exact integer minor units
(reject sub-unit, never round); plaintext KDF sidecar; auto-lock 10 min
placeholder; tamper-and-wrong-password deliberately indistinguishable at
unlock. Two cross-doc follow-ups surfaced for the user: a one-line ADR-0003
raw-key note, and tightening security-model INV-2's "in the vault" → "with
the vault".

Next: **user signs off the spec**, then Step 2 (deps: FIBR-0001 ✅) → Step 3
(write failing tests) → Step 4 (implement).

### 2026-07-01 — FIBR-0003 closed by /close-phase (P01 Bootstrap complete)

Steps 3–4 (TDD + implement) landed in commit `49e87b6`; the bundling
smoke-test is proven green (both the onefile and AppImage print
`FINBREAK_SELFTEST_OK` in the Python-free `debian:13-slim` clean-room).

**Close (steps 5–9):** ran `/audit` + `/indie-review` in parallel over the
FIBR-0003-authored files. Audit (incl. `shellcheck` on all three shell
scripts): zero actionable. Indie-review: 3 actionable, **all doc/comment
drift, no code/security defect** — a stale "manylinux_2_34 container"
mislabel (the build image is `python:3.12-slim-bookworm`; manylinux is ruled
out because it ships a static Python) in `pyproject.toml` + `build-smoke.sh`,
a stale test-function name in `tests/features/bundling/spec.md`, and a
missing `pip install .` in CLAUDE.md's dev-setup. User authorised the
**fix-inline** path (deviation from the rigid FP## route, per the skill's
"deviations require explicit user instruction"). Fixed all three, then a
**cold re-audit + re-review pair** caught one straggler instance of the same
manylinux mislabel (`CLAUDE.md:143`, module map) the first review missed —
fixed, exhaustively `grep`-verified across the tree, then a final confirming
cold review returned **CLEAN, zero actionable**. Clean pair on the same
closing round → DoD #5 met.

Updated CHANGELOG (Added), flipped ROADMAP FIBR-0003 → ✅ with resolution
note, wrote `docs/journal/FIBR-0003.md`. Tag `FIBR-0003-complete`.

**P01 Bootstrap is now complete** (FIBR-0001/0002/0003 all ✅). Next: P02
FIBR-0004 — the encrypted security spine (the deliberate vertical slice).

### 2026-07-01 — FIBR-0003 spec drafted + /cold-eyes (6 loops)

Drafted `docs/specs/FIBR-0003.md` (P01 bundling smoke-test). Scope decided
with the user: de-risk **all three** native stacks (Qt + SQLCipher + qpdf),
and keep the bundle-build a **separate opt-in command** so the everyday
`ci-local.sh` gate stays fast. Pinned toolchain from parallel research:
`PySide6==6.11.1`, `sqlcipher3-binary==0.6.0` (bundles the native lib),
`pikepdf==10.9.1`, `pyinstaller==6.21.0`; clean-room = Python-free
`debian:13-slim` via podman `--env-clear`.

**Cold-eyes (global rule §14):** 2 lanes (accuracy + implementability), 6
loops, 12 independent cold reviewers, ~40 findings fixed — including one real
CRITICAL I introduced in loop 3 (a `debian:stable-slim` left in the DoD after
pinning the image) that both lanes caught in loop 4, plus two loop-2 citation
corrections (INV-9→INV-6 for the fake-key justification; testing §3.4→§3.3 for
the integration marker). Converged to polish + build-time-verification items
(PyPI pin resolution, PySide6 wheel tag, Debian glibc) which are folded into
the spec as explicit build steps. Both lanes verified all citations/contracts
clean twice. Also reconciled the ROADMAP FIBR-0003 bullet to name all three
native stacks (was "SQLCipher/Qt" only).

Next: step 3 — write failing tests (the `--self-test` guard + the
`integration`-marked build+clean-room test), then implement to green.

### 2026-07-01 — Phase D deferred items resolved (Argon2id pin + finbreak rename)

Closed the two items deferred at the end of the Phase D doc audit, before P01
sign-off.

1. **Argon2id parameters pinned.** Researched the current OWASP Password Storage
   Cheat Sheet (retrieved 2026-06-30) and pinned the highest-memory of its five
   equal-strength Argon2id configs — **memory 47104 KiB (46 MiB), iterations 1,
   parallelism 1**, plus a 16-byte per-vault salt and 32-byte (256-bit) raw-key
   output (the last two are finbreak choices; OWASP is silent on them). Values
   now live in **one place** — `security-model.md` INV-2 — with an explicit,
   testable open-path refusal rule (memory ≥ floor; output and salt exact-format;
   iterations/parallelism uncheckable since 1 is Argon2id's own minimum).
   ADR-0003, T9, T2 and the ROADMAP FIBR-0004 bullet now reference INV-2 instead
   of restating numbers or promising a future just-in-time pin.

2. **Naming unified to `finbreak`.** Per user decision, dropped the deliberate
   Fin_Break / FinBreak / finbreak three-way split; brand, repo, on-disk data
   dir, and Python package are now all `finbreak` (byte-for-byte). Swept 15
   doc/config files; historical journal lines left intact. Data-dir path is now
   `~/.local/share/finbreak/` etc. **GitHub repo renamed** milnet01/Fin_Break →
   milnet01/finbreak (old URL auto-redirects; local remote updated). **Local
   checkout dir not yet renamed** — still `…/Fin_Break`; recommend
   `mv Fin_Break finbreak` from a fresh session to match (deferred to avoid
   breaking this session's absolute paths).

**Cold-eyes (global rule §14):** the edited security/ADR/design docs ran through
`/cold-eyes` — 2 lanes (crypto-accuracy, naming). Naming clean on loop 1. Crypto
lane looped 5 passes: loop 1 MED+LOW (params not concrete / single-source) →
loop 2 HIGH ("top-recommended" mischaracterised OWASP's equal-strength configs)
+ MEDs → loops 3–4 (floor-predicate prose-vs-predicate precision) → **loop 5
clean** (zero verified findings, all dimensions). Every value independently
re-verified against the live OWASP page each loop.

Next: still awaiting user sign-off "docs ready to code from" → P01 (FIBR-0001).

### 2026-06-30 — Phase D `/cold-eyes` doc-audit loop (5 loops)

Ran the `/cold-eyes` skill over the full Phase A–C doc set (discovery, design,
7 ADRs + README, security-model, the 4 standards + roadmap-format sub-spec,
FIBR-0001 spec, ROADMAP) partitioned into 8 topic lanes. Each loop dispatched
independent cold reviewers; every finding was verified against the files before
fixing (several agent claims were dismissed as false positives on verification —
e.g. a hallucinated CONTRIBUTING clone URL, a "discovery has no Tech-stack
section" claim, a "§5.2 doesn't show Signal/@Slot" claim).

Convergence: ~50 → ~39 → ~20 → ~18 verified findings → loop 5 (fine precision
only). **Zero CRITICAL across all loops.** Loop 1 fixed the big template residue
(coding.md/testing.md/commits.md C++→Python conversion, PROJ→FIBR IDs, stale
Claude-4.7→4.8 trailer) + security-model testability gaps (T9 AES-vs-HMAC
crypto fix, INV-5 split into 5a/5b/5c, INV-2 dangling-spec ref, INV-8 enforcement
honesty). Loops 2–5 fixed second-order issues (4 wrong §-anchors in ROADMAP, a
dashboard→transfer-detection DAG edge for correct SC1 totals, INV citation
precision, str-wipe / raw-key / export-temp-file security gotchas captured for
the P02/P11 specs). Lanes 2/6/7/8 reached cosmetic-clean at loop 4.

Two items deliberately deferred (not doc defects): the exact Argon2id parameters
(pinned in the FIBR-0004/P02 spec with researched OWASP values, per no-guessing
rule) and the data-dir naming (documented the deliberate Fin_Break / FinBreak /
finbreak split rather than renaming).

Awaiting user sign-off "docs ready to code from" before P01 (FIBR-0001).

### 2026-06-30 — Phase C signed off; entering Phase D

User approved the Phase C doc set: `ROADMAP.md` build order (P01–P13,
FIBR-NNNN IDs, counter=16), `docs/security-model.md` (threat model + 9
enforceable invariants), the Python/pytest conversion of
`docs/standards/testing.md`, the `docs/specs/FIBR-0001.md` bootstrap spec,
and the empty `CHANGELOG.md`. Committed `a5162d3`, pushed to public origin.

Next: Phase D — `/cold-eyes` doc-audit loop over the full Phase A–C doc set
until a pass returns zero verified actionable findings (global rule § 14).
Loop 2+ runs cold (no briefing on prior findings). Then user signs off
"docs ready to code from" and P01 (FIBR-0001) implementation begins.

### 2026-06-30 — Phase B design approved

`docs/design.md` (layered UI→Services→Repos→SQLCipher architecture, components,
import→insight data flow, cross-cutting concerns incl. the Security and
Packaging/self-contained-delivery sections) approved by the user, together with
ADRs 0002–0007. ADR-0007 (self-contained bundled releases — bundle the CPython
runtime + all native deps; clean-machine no-Python launch gates every release)
was the last addition before sign-off.

Next: Phase C — write/tweak the four `docs/standards/*.md`, populate `ROADMAP.md`
with the build order (P01 Bootstrap → P02 vertical slice → features →
packaging/release), keep CHANGELOG `[Unreleased]` empty, and write specs for the
first 1–3 roadmap items. Then Phase D — `/cold-eyes` doc-audit loop until clean.

### 2026-06-30 — Phase A discovery approved

`docs/discovery.md` written from the brainstorming conversation and approved by
the user. Public repo created + pushed (`milnet01/Fin_Break`); layout declared
in `.ants/project.json`; public-GitHub optionals activated.

Key decisions: PySide6 (LGPL) GUI; SQLCipher encrypted-at-rest storage; Qt-native
PDF engine (WeasyPrint dropped for cross-platform bundling); local-only/no-network;
per-OS-user data. Cross-platform delivery: Windows `.exe`, unsigned macOS
`.app`/`.dmg`, Linux AppImage + Flathub Flatpak, driven by a specced
`scripts/publish-release.sh`. Local CI emulation (`scripts/ci-local.sh`) +
`.github/workflows/ci.yml` are P01 deliverables.

Next: Phase B — Design (`docs/design.md` + ADRs).

### 2026-06-30 — P00 scaffold

Project scaffolded from `~/.claude/skills/app-workflow/templates/`
via `/start-app`. Initial commit `chore: scaffold project from
template (P00)`.

Next: Phase A — Discovery. User says "let's start discovery"
in a fresh Claude Code session in this directory.
