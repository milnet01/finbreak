# finbreak — Workflow state

## §1. Status header

| Field | Value |
|-------|-------|
| **Project phase** | **P08 CLOSED** (FIBR-0010 rules engine + manual override + learning shipped 2026-07-10). Next up: **FIBR-0054** (in-app auto-update) — the last near-term user ask; then P09/FIBR-0011 (transfers) → P10/FIBR-0012 (dashboard). |
| **Active item ID** | **FIBR-0146 CLOSED 2026-07-17 by /close-phase — PDF/CSV date-format auto-detect + confirm SHIPPED (code).** The import wizard stops making a person type programmer date codes: new pure `importers/date_detect.py` (`detect_date_format(Sequence[str]) -> DateFormatGuess`, 15 ordered `KNOWN_DATE_FORMATS`, clock-free, **no year guard** — `strptime` separates 2/4-digit widths) guesses the layout; friendly per-row `RowError` in `csv_importer` (D3, no `%`-format leak); wizard `import_date_format` QComboBox + "Custom…" reveal + on-entry/manual-column auto-detect + live "Dates read as: …" preview (2 fallbacks + ambiguity nudge) + whole-import banner (D4-D8, single-owner wiring); `_validate_mapping` rejects the empty-format `strptime("","")`→1900-01-01 trap (D4). TDD `tests/features/import_date_detect/` (spec.md + **39 tests**, 4 layers). Close: `/audit` semgrep **0**; **2 cold review lanes** → Lane A (date/money) **no reachable defects**; Lane B **2 MEDIUM** (`_apply_profile_to_combos` set the date combo UNBLOCKED → spurious matched-profile re-detect + double refresh, contradicting D5/INV-4 — final state corrected so never a wrong-day, fixed with QSignalBlocker; **+** the D5(b) PDF fire points had zero tests) **+ 2 LOW** (masked column-0 matched test; missing INV-1 "0 rows before Import" falsifier) — **all folded inline + re-verified**. Gate green **1080/1**, mypy 0. Commits `c5782a6`→(fold `92…`)+close; tag `FIBR-0146-complete`; journal `docs/journal/FIBR-0146.md`. **NEXT ACTIVE: the v0.1.15 release with the user** (ships FIBR-0146; needs the signing key) **or budgets FIBR-0022** — user's call. — prior: **FIBR-0146 ACTIVE — spec CLEARED FOR CODE, paused for the night 2026-07-16.** PDF/CSV date-format auto-detect + confirm (the external Windows tester's 165-row import failure). `docs/specs/FIBR-0146.md` written + run through `/cold-eyes` to the full project cap (7 loops × 3 cold lanes = 21 reviews); core converged (accuracy lane clean loops 5–7; no remaining silent-wrong-day path loops 5–7); every CRIT/HIGH/MED/LOW fixed in-loop. Roadmap FIBR-0146 🚧 (features-accessibility). Design: pure `importers/date_detect.py` (`detect_date_format(Sequence[str]) -> DateFormatGuess`, 15 `KNOWN_DATE_FORMATS`, no year guard — strptime separates 2/4-digit); friendly `RowError` in `csv_importer`; wizard `import_date_format` QComboBox + "Custom…" + live preview + whole-import banner; `_validate_mapping` rejects empty format (the `strptime("","")`→1900 trap). **NEXT (morning): TDD** `tests/features/import_date_detect/` per the spec's Deliverables + Test plan (RED → GREEN → gate → /close-phase). 8 commits on main, all pushed. — prior: **FIBR-0143 CLOSED 2026-07-16 by /close-phase — dashboard-focus rework SHIPPED (code).** The Home dashboard breakdown is now the hero: three columns (Expenditure/Income/Transfers), each a pie + coloured header/total + expandable drill tree; a slim Net strip; a full-width **unscoped** Recurring card (`RecurringService.summary(today)`); the monthly-trend bar demoted to a bottom strip. New `build_breakdown_donut` (own cap loop; the PDF spending donut is byte-for-byte untouched, D10); explicit node→column map (Expenditure←Spending `nodes[1]`); `RecurringService` wired into `main_window` with `amount_prefs=` by keyword (positional-shift hazard). No schema/service change (all reuse). TDD `tests/features/dashboard_focus/` (INV-1..9, 20 legs) + rippled FIBR-0138 `dashboard_drilldown` + FIBR-0012 `dashboard` onto the new column surfaces. Close: semgrep **0**; **2 cold review lanes** → production **clean** (0 CRIT/HIGH/MED; D1..10 + INV-1..9 verified vs source), **3 LOW test-strength adds folded inline** (dead `or True` seed filter → explicit direction match; In/Out force-by-role colour assertion where both totals are positive; the missing INV-3 confirm-shows-on-next-refresh leg). Gate green **1040/1**, mypy 0. Commits `070cd76`→`6719de5`+close; tag `FIBR-0143-complete`; journal `docs/journal/FIBR-0143.md`. **NEXT ACTIVE: the v0.1.12 release with the user** (bundles FIBR-0143 + the still-unreleased FIBR-0138 drill-down; needs the signing key) **or budgets FIBR-0022** — user's call. — prior: **FIBR-0142 CLOSED 2026-07-15 by /close-phase — recurring-money detection SHIPPED (code).** TDD 4 slices: pure `detect_recurring` (group by `(direction, merchant_key)`, `median_low` integer representative + integer-exact ±10%, cadence bands, activeness, `ROUND_HALF_EVEN` monthly-equivalent) → schema **v9** `recurring_decisions` keyed `(direction, merchant_key)` (drift-guards across every feature bumped 8→9) → `RecurringRepository` + `RecurringService` (one-pass `snapshot` partition suggested/confirmed/dismissed + summary) → the **Recurring tab** after Transfers (8-tab workspace, new `recurring.svg`). Close: semgrep+bandit **0**; **2 cold code-review lanes** → **1 HIGH** (fortnightly monthly-equivalent pre-divided `Decimal(26)/12` factor rounded the factor at 28 sig-figs and defeated `ROUND_HALF_EVEN` — ~2.9% of fortnightly amounts off by a minor unit; fixed to the spec-D8 `amount × N / 12` deferred-division form + reproduce-first test) **+ 1 LOW** (`created_at` reset on a decision flip vs spec's immutable-provenance; fixed) **+ 3 test-strength adds** (≥2-item post-sort widget mapping test, rendered label assertion, stronger tr()-grep), all **folded inline**. Gate green; commits `ba580f9`→`d705937`; tag `FIBR-0142-complete`; journal `docs/journal/FIBR-0142.md`. **NEXT ACTIVE: FIBR-0143** (Home dashboard-focus rework — the income/expenditure/transfers **breakdown** is the hero, charts secondary; **UNBLOCKED** — user delivered the HTML mockup `/home/ants/Documents/dashboard_2.html` this session: 3 columns each with the existing pie chart + coloured header/total + expandable breakdown list, monthly bar chart demoted to a full-width strip; no borders, consistent row heights; also lands the **deferred FIBR-0142 Home card** consuming `RecurringService.summary()`), **if the user's weekly limit allows**; then budgets (**FIBR-0022**). — prior active note: **FIBR-0142 ACTIVE 2026-07-15 — recurring-money-detection spec CLEARED FOR CODE (`/cold-eyes` converged loop 5; 5 loops × 3 cold lanes = 15 reviews; project cap 7).** Split from FIBR-0022 (budgets stay on FIBR-0022 as the follow-up). User brainstorm picks (2026-07-15): detect recurring money BOTH directions (subscriptions OUT + salary/standing IN); "Balanced" sensitivity (≥3 occurrences, ±10% of the group median, gaps consistently one cadence bucket weekly/fortnightly/monthly/yearly); BOTH surfaces (a dedicated Recurring tab now, a Home dashboard card DEFERRED to FIBR-0143). Design: pure `detect_recurring(rows, today, exponent, excluded_ids)` grouping on `normalise_text(merchant_name(description))` × direction (reuses FIBR-0138), `median_low` money-safe integer representative + integer-exact ±10% test, cadence bands with same-day-dupe/zero-gap discard + ≥2 non-zero gaps, `ROUND_HALF_EVEN` monthly-equivalent, schema v9 `recurring_decisions` keyed on `(direction, merchant_key)` mirroring `transfer_pairs`, `RecurringService` (snapshot/candidates/confirmed/summary/confirm/dismiss/reset). Spec `docs/specs/FIBR-0142.md`; 6 commits `ffe51a5`→(loop5). **NEXT: TDD `tests/features/recurring/`** (pure detector red→green first, then migration/models/repo/service, then the Qt tab) → gate green → `/close-phase`. Also this session: logged **FIBR-0143** (Home dashboard-focus rework — breakdown should be the hero, charts secondary; BLOCKED pending the user's HTML mockup); flipped stale-done **FIBR-0041** ✅ (CSV import size cap was already shipped); marked **FIBR-0031** a duplicate of **FIBR-0095** (unlock throttling). — prior: **FIBR-0138 CLOSED 2026-07-14 by /close-phase — expandable dashboard drill-down SHIPPED (code).** An openable `dashboard_drilldown` `QTreeWidget` below the FIBR-0012 donut+trend: three top rows Income/Spending/Transfers drill categories → merchant (×count via `merchant_name` cleanup) → individual txns, and by account pair for transfers. New: `DrillNode`/`DrillLabels` (models), `merchant_name` (text.py, pure+total, stdlib re), `drill_rows_in_range` (5-tuple sibling read = rows_in_range + description), `ReportingService.drill_down` (one "group by top-of-chain" category algorithm + account-pair transfers; INV-7 uniform-STRING sort key; branch totals accumulate integer `amount_minor` — Spending negates — so they **equal** the tiles, INV-1; `scaleb` exact, no drift), HomeView `QScrollArea`+tree wiring with tr()-ed `DrillLabels` injected from the QObject view (`_render_drilldown`/`_add_node`, ×N only on merchant/pair nodes structurally). TDD **41-leg** `tests/features/dashboard_drilldown/` (INV-1..9). Close: `/audit` **semgrep 0** + gate (ruff/bandit/pip-audit/gitleaks/mypy) **0**; `/indie-review` **2 cold lanes** → production **money-correct**, folded inline: a `top_of_chain`+`category_node` **corrupt-data cycle guard** (CategoryService lacks a descendant guard, so X→Y→X is reachable; visited-set stays total, no drop/hang/overflow) + **5 test-strength adds** (the real INV-7 mixed-type sort-key falsifier — a category vs merchant node tying on magnitude AND label forces the third STRING key; an INV-9 sentinel-label proof that the service threads `DrillLabels` not hard-coded English; a cycle-termination regression; a count==1 bare-label; a punctuation-only `merchant_name`). Gate green **975/1**, mypy 0. Commits `810283f` (impl) + `ebbcced` (fold) + close; tag `FIBR-0138-complete`; journal `docs/journal/FIBR-0138.md`. **Deferred:** README "what works today" refresh → next bump (Deliverable 7); a `CategoryService.update_category` descendant-cycle guard (pre-existing latent; small follow-up `fix`). **NEXT: the next release with the user** (v0.1.12 — bundles the drill-down; needs the signing key), or user-directed next feature (FIBR-0140 learn-from-history deferred half; FIBR-0137 Business/Personal grouping 💭). — prior: **FIBR-0139 CLOSED 2026-07-14 by /close-phase — built-in category library SHIPPED (code).** A bundled, per-release `data/category_library.json` auto-categorises common merchants out of the box, running AFTER user rules and only on unclaimed (auto) rows; guessed rows stamped `'library'` + shown with an overridable "~ guess" marker; default-ON Settings toggle. TDD `tests/features/category_library/` (INV-1..11) → new pure `category_library.py` (parse/load/match, fail-safe) + engine (`CategorySource.LIBRARY` no-migration, `categorize_with_library` rule-beats-library, `_match_inputs` toggle-gated, `_leaf_name_to_id` first-wins, `would_categorize`/`recategorize_auto_rows` rerouted) + Settings toggle + Transactions marker (every Category cell a bare-name `SortableItem`) + bundling (`data/*.json` glob + 2nd `--add-data` in all 3 freeze sites + parity guard set-checks both) + autouse neutralise fixture. `/audit` (semgrep full) **0 actionable**; `/indie-review` **2 cold lanes** → **0 CRIT/HIGH/MED**, only LOW substring-precision (accepted D2 substring-only tradeoff — marked overridable guesses, money never touched) + a pre-existing Windows-driver parity note. Gate green **934/1**, mypy 0. Commit `24e7a91` (impl, pushed) + close commit; tag `FIBR-0139-complete`; journal `docs/journal/FIBR-0139.md`. **FIBR-0140** (learn-from-history) is the deferred "later" half. **NEXT ACTIVE: FIBR-0138** (expandable Home dashboard drill-down — designed + roadmapped 📋; spec → cold-eyes → TDD), then the next release with the user. — prior: **FIBR-0128 CLOSED 2026-07-14 by /close-phase — forget remembered statement passwords SHIPPED (code).** TDD 8-leg `tests/features/accounts/` (INV-1..5) → repo `ids_with_pdf_password` + service `account_ids_with_pdf_password` + `ui/accounts.py` **Forget statement password** button/marker/handler. Presence is an **id-set** (the secret column is never selected to list); the plaintext never crosses into the UI (INV-1). Forget-only, per-account, confirm-gated, `VaultLockedError`-silent; enable/disable recomputed **before** `_on_selection_changed`'s `None` early-return so a post-Forget refresh disables the button (cold-eyes loop-1 HIGH). `/cold-eyes` converged loop 3 (9 cold reviews). Close: semgrep+bandit **0** on the changed surface; 1 cold review lane → production **CLEAN**, **2 LOW** test-precision folded inline. Gate green **915/1**, mypy 0. Commits `642b592`(impl)+`37df6ad`(fold)+close; tag `FIBR-0128-complete`; journal `docs/journal/FIBR-0128.md`. Also logged this session: **FIBR-0137** (Business/Personal account grouping — considered 💭, external-tester need). **NEXT: the expandable Home dashboard** (the user's original ask — drill Expenditure/Income/Transfers → categories → merchant; design → roadmap → spec → TDD) **then the v0.1.10 release with the user** (needs signing key; ships FIBR-0131 Windows auto-update + the missing `.exe.sig`). — prior active note: **FIBR-0128 ACTIVE 2026-07-14 — spec written (`docs/specs/FIBR-0128.md`), `/cold-eyes` next.** Forget remembered statement passwords on the **Accounts screen** (spec D1 — a deliberate divergence from the roadmap's original "Settings-hosted" wording; user directive: different accounts can have different statement passwords, so the per-account surface fits). Selection-driven **Forget statement password** button + a presence marker on rows with a saved password; **never reveals** the secret (INV-1 — presence is an id-set via `ids_with_pdf_password`/`account_ids_with_pdf_password`, clearing passes `None`); **forget-only**, no manual set (D5 — re-remembered on next import). Deliverables: repo `ids_with_pdf_password` + service `account_ids_with_pdf_password` + `ui/accounts.py` button/marker/handler; tests mirror the existing delete-confirm `QMessageBox.question` monkeypatch + `VaultLockedError`-silent patterns. ROADMAP FIBR-0128 flipped 🚧. Also this turn: logged **FIBR-0137** (Business/Personal account grouping — separate views in one profile, considered 💭, friend/external-tester request) and started capturing the **expandable dashboard** design (drill Expenditure/Income/Transfers → categories → merchant) for a later spec. **NEXT: `/cold-eyes` (max-loops 7) → TDD `tests/features/accounts/` → `/close-phase`; then the expandable-dashboard design + spec; then the v0.1.10 release with the user.** — prior: **FIBR-0127 CLOSED 2026-07-14 by /close-phase — app-wide theme system SHIPPED (code).** TDD 30-leg `tests/features/theme/` (INV-1..13 + D3/D4) → `ui/theme.py` (six-theme token registry → `build_palette`/`build_stylesheet`; `ThemeController` with live `colorSchemeChanged` follow-system; non-vault `theme` pref via `window_settings_path`, applies pre-unlock) + `app.py`/`main_window.py`/`settings.py` wiring (Fusion style, immediate-apply Settings picker, `_retint_toolbar_icons` on `themeChanged` = FIBR-0116's live re-tint, `polish_item_views` grid striping — all gated on a controller so the default `None` path is untouched, D10) + D11 ADR-0002→ADR-0010 citation fixes (icons/home/_amount/pdf_export) + **ADR-0010** Accepted. **TDD-surfaced spec correction:** a Qt QSS proxy masks `style().objectName()`, so INV-1/6 pin Fusion via a `setStyle` spy (verified in-venv, Qt 6.11.1). `/audit` **0 actionable** (semgrep full + ruff/bandit/gitleaks via gate); `/indie-review` **2 cold lanes** → no CRIT/HIGH/MED, **1 LOW** (INV-10 re-tint test now compares rendered pixmap image, a strict falsifier) **folded inline**. Gate green **907/1**, mypy 0. Commits `34be695` (impl) + `ab28790` (review fold) pushed; tag `FIBR-0127-complete` (this commit); journal `docs/journal/FIBR-0127.md`. **NEXT ACTIVE: FIBR-0128** (manage stored PDF statement passwords — view/clear per-account; brainstorm→spec→cold-eyes→TDD), **then cut the v0.1.10 release with the user** (needs their signing key; ships FIBR-0131 Windows auto-update + the missing `.exe.sig`). — prior active note: **FIBR-0127 ACTIVE — spec CLEARED FOR CODE 2026-07-14 (cold-eyes converged loop 6).** User picked (2026-07-14): do **FIBR-0127** (theme system) → **FIBR-0128** (saved-PDF-password manager) → then cut the **v0.1.10 release** (option 4, needs the user's signing key). Brainstorm ✓ (user-approved: **designed look**, **six finance-flavoured themes** Ledger/Parchment/Mint · Midnight/Graphite/Emerald, **live follow-system**, **sleek modern polish** = gradient/glow accents + grid row-highlighting, **theme-aware toolbar icons**). Spec `docs/specs/FIBR-0127.md` + **ADR-0010** written & committed; `/cold-eyes` ran **6 loops × 3 cold lanes = 18 reviews** → polish-converged (C `0×6`, H `3→1→0→0→0→0`, M `6→0→2→1→1→0`; full log in the spec). Design: `ui/theme.py` (ThemeTokens registry → `build_palette`/`build_stylesheet`, `ThemeController(QObject)` with live `colorSchemeChanged` follow-system, non-vault `theme` pref in `window_settings_path` so it applies pre-unlock); Fusion style; Settings picker (immediate-apply); `_retint_toolbar_icons` on `themeChanged` (delivers FIBR-0116 live re-tint); `polish_item_views` striping. **NEXT: TDD** (`tests/features/theme/` INV-1..13 red→green → implement → gate green → `/close-phase`), then **FIBR-0128**, then the **v0.1.10 release** with the user. Commits `66b7999`→`b039126` (spec + ADR + 6 loop-fix commits + convergence). — prior active item: **FIBR-0131 CLOSED 2026-07-14 by /close-phase** (Windows in-app auto-update — code-complete + gate-green **877/1**, tag `FIBR-0131-complete`, journal `docs/journal/FIBR-0131.md`. TDD delivered a `WindowsInstaller` behind the existing `Installer` seam: a detached PowerShell helper waits by exe **image path** (tree-agnostic + PID-recycling-proof) → moves the Ed25519-verified new `.exe` over the old → relaunches; installer-driven asset-picker; `UpdateInfo.appimage_url`→`asset_url`. `/audit` **0 actionable** (3 bandit assert-in-tests FPs, out of `-r src` gate scope). `/indie-review` **2 cold lanes** → crypto/PowerShell/ordering verified sound; **1 MEDIUM fixed inline** — `apply` now **spawns→wipes→exits** (was wipe→spawn, which stranded a wiped key if `Popen` failed under AV/AppLocker); Linux twin guarded the same way. **CAVEAT (like FIBR-0054):** the live Windows swap+relaunch is a **two-cycle** manual verification on the user's Windows box, and needs a release that first attaches the Ed25519 **`.exe.sig`** (v0.1.9 shipped the `.exe` but no `.sig` — see `bump.json`). **NEXT: user direction** — near-term queue is **FIBR-0133** (SignPath Authenticode signing — 🚧 blocked on external approval), a **v0.1.10 release** to ship FIBR-0131 (+ the `.exe.sig`), plus the P12 backlog (FIBR-0017 i18n, FIBR-0127 theme, FIBR-0128 stored-PDF-password mgmt).) — prior active-item note: **FIBR-0131 spec CLEARED (cold-eyes converged loop 6)** — brainstorm ✓ (user-approved 2026-07-13 + sequencing 2026-07-14: **ship now with the Ed25519 gate alone**; Authenticode→FIBR-0133). **`/cold-eyes` CONVERGED at loop 6** (3 cold lanes/loop × 6 = 18 reviews; polish convergence, 0 CRIT/0 HIGH; C `0→0`, H `3→1→1→0→2→0` — the loop-5 spike was self-inflicted PID residue from loop-4's **image-path swap** redesign, caught + purged). Design: a `WindowsInstaller` behind the existing `Installer` seam; a detached **PowerShell helper waits by exe *image path*** (tree-agnostic + PID-recycling-proof) → moves the Ed25519-verified new `.exe` over the old → relaunches; platform-aware asset-picker; the `.exe` gains an Ed25519 `.exe.sig` release asset. **NEXT: TDD** — the Linux-runnable legs (command/env builders, `detect_installer` matrix, asset-picker, installer-None short-circuit, `apply` ordering, the `_select_assets`/`asset_url` refactor) → implement → gate green → `/close-phase`; the live Windows swap is a manual **two-cycle** leg on the user's Windows box. Six per-loop commits `d1d548c`→(loop6) + this convergence commit.) — prior active-item note: **FIBR-0054 CLOSED 2026-07-14 by /close-phase** (Linux in-app auto-update — code-complete since v0.1.0, field-proven through v0.1.9; the live auto-relaunch **v0.1.8→v0.1.9** confirmed (commit `8e4a298`) was the last gate. Close ran `/audit` (semgrep/ruff/bandit/gitleaks) + 2 cold `/indie-review` lanes over the auto-update surface: **1 MEDIUM** (`_on_download_failed` lacked the auto-lock guard its `_on_download_ready` sibling has → download-fail-after-auto-lock destroyed the re-opened unlock dialog + stray warning over the lock screen) **+ 3 LOW** (temp-staging outside the try; 2 test-fidelity) **all fixed inline** (commit `67132c1`); **2 semgrep dynamic-urllib FPs allowlisted** (allowlist-001, first project allowlist entry). Gate green **856/1**; tag `FIBR-0054-complete`; journal `docs/journal/FIBR-0054.md`. Windows in-app auto-update remains **FIBR-0131**.) Also shipped this session: **FIBR-0134** (Windows `.exe` showed PyInstaller's default console-stub icon — added `--icon assets/icon/finbreak.ico` to `scripts/build-windows-exe.py` + a regression test; icon lands on the next Windows build). **Both 2026-07-14 user requests now SHIPPED** (pushed): **FIBR-0135** (auto-lock "Never"/off option — `AUTO_LOCK_NEVER=0` last in `ALLOWED` so the INV-1 fallback stays aggressive; `_arm_timer` stops on it; `notify_activity` `isActive()`-guarded; combo "Never" label; security-model T3 note; commit `b915254`) and **FIBR-0136** (Statements toolbar icon + button — new `ui/icons/statements.svg`, wired into `_action_statements`, added to the toolbar after Transactions; reverses the FIBR-0052 "no statements button" test; commit `eb52443`). Both TDD, gate green **862/1**. **NEXT: user direction** — the near-term queue is **FIBR-0131** (Windows in-app auto-update, the big feature; deps FIBR-0054+FIBR-0015 both done → brainstorm→spec→cold-eyes→TDD), **FIBR-0133** (SignPath signing — blocked on external approval), plus the P12 backlog (FIBR-0017 i18n, FIBR-0127 theme, FIBR-0128 stored-PDF-password mgmt). — prior active-item note: **FIBR-0015 CLOSED 2026-07-13 by /close-phase** (Windows `.exe` shipped; sqlcipher3-wheels swap ADR-0009; windows-build.yml green + artifact; macOS/Flatpak split to FIBR-0130; tag `FIBR-0015-complete`). **v0.1.9 PUBLISHED 2026-07-13** (Linux AppImage + `.sig` + **Windows `finbreak-0.1.9-x86_64.exe`** — first Windows release; non-prerelease → /releases/latest; sig verified vs committed key; .exe also copied to the drop share `/mnt/Games/Scripts/Apps/finbreak/`). **NEXT ACTIVE ITEM: FIBR-0131** (Windows in-app auto-update — user-approved design: a separate helper process closes the app, downloads + Ed25519-verifies the new .exe, swaps files, relaunches; reuses the FIBR-0054 check/verify/UI stack + adds a `WindowsInstaller`/`detect_installer` + promotes the .exe to a signed release asset; user said build AFTER this release, and to compact/clear first). Brainstorm → spec → `/cold-eyes` → TDD. (**FIBR-0054 Linux auto-update RELAUNCH CONFIRMED 2026-07-13** — the user's live **v0.1.8→v0.1.9** update downloaded, verified, swapped, **and auto-relaunched the new version** — the true post-v0.1.8 two-cycle test passed. FIBR-0054 is now code-complete + live-proven and **ready to close** (steps 5–9: `/audit` + `/indie-review` → fold → tag `FIBR-0054-complete`); user winding down for the day, so close deferred pending their go-ahead. FIBR-0130 macOS/Flatpak + FIBR-0016 release-automation also queued 📋.) — prior active-item note: **ACTIVE ITEM: FIBR-0015** (Windows build — PyInstaller `.exe`; the blocker is SQLCipher-on-Windows: `sqlcipher3-binary` is Linux-only, so it needs a Wine+MSVC local compile per the FIBR-0015 roadmap note; **NEXT: brainstorm/confirm scope → spec → `/cold-eyes` → build harness**). **FIBR-0014 CLOSED 2026-07-13 by /close-phase** — encrypted backup export/restore SHIPPED (7 TDD slices + fold-in of 6 cold-review findings; D2 SQLCipher spike proven first on sqlcipher3-binary 0.6.0 / SQLCipher 4.12.0; `.fbk` = zip of manifest/params/vault.db, separate backup password, INV-1..13; `/audit` 0 with 1 bandit B608 FP suppressed; gate green 841/1, mypy 0; tag `FIBR-0014-complete`; journal `docs/journal/FIBR-0014.md`). **FIBR-0123 CLOSED 2026-07-13 by /close-phase** — category-picker Income/Expenditure grouping SHIPPED (6 TDD slices; `/audit` 0; `/indie-review` 2 cold lanes → 1 LOW parent-cycle guard fixed inline; gate green; tag `FIBR-0123-complete`; journal `docs/journal/FIBR-0123.md`). Locked order continues **FIBR-0014 → FIBR-0015** (Windows build; SQLCipher-on-Windows is the blocker). **FIBR-0013 CLOSED 2026-07-13 by /close-phase** — P11 locked-PDF export SHIPPED (7 TDD slices; `/audit` 0 in-scope; `/indie-review` no CRIT/HIGH/MED, 3 LOW fixed inline; gate 779/1; tag `FIBR-0013-complete`; journal `docs/journal/FIBR-0013.md`). Order continues FIBR-0123 → FIBR-0014 → FIBR-0015 (Windows build). — prior active-item note (FIBR-0013, now closed): **ACTIVE ITEM: FIBR-0013** (P11 — password-protected PDF export). **Spec CLEARED FOR CODE 2026-07-13** — brainstorm ✓ → `docs/specs/FIBR-0013.md` ✓ → `/cold-eyes` ✓ **converged (7 loops × 3 lanes)**; **NEXT: TDD** (`tests/features/pdf_export/` + the D4 reporting `account_ids` ripple + the D3 `ui/charts.py` extraction) → `/close-phase`. See §3 journal 2026-07-13. **After FIBR-0013: FIBR-0123** (category-picker Income/Expenditure grouping — user "one at a time"). — Original flow note kept for reference: **User directives:** the export password must be **OPTIONAL** (user 2026-07-12 — captured on the FIBR-0013 roadmap bullet); the PDF export renders the FIBR-0012 dashboard charts into the locked PDF (QtCharts was chosen partly for this, ADR-0008). **Confirmed phase order (user 2026-07-13): FIBR-0013 → FIBR-0014 → FIBR-0015 (Windows build).** FIBR-0015 has a Wine+MSVC local-build path noted (build+test a Windows .exe locally before CI; SQLCipher is the one Linux-only dep to compile). **FIBR-0054** (auto-update) stays open pending the user's live auto-relaunch test — the FIBR-0122 relaunch fix shipped in **v0.1.8** (2026-07-13) but the two-cycle caveat means it only *runs* on the update AFTER v0.1.8. — Prior active-item history: **FIBR-0065 CLOSED 2026-07-10** (auto-lock-during-modal-dialog crash fix — the reproduced HIGH from the 2026-07-10 sweep). Converted the 6 blocking content-widget `exec()` pop-ups to the non-blocking `show_modal` (setModal+show()+signal) pattern; PDF password loop → the `_try_decrypt` state machine. Spec `/cold-eyes`-converged (5 loops); TDD (dialog_lifecycle INV-1 grep + real `_lock()`-during-open-PDF-prompt INV-2 regression + parity ripple); gate green 437/1; `/audit` 0; a cold code-review confirmed the D5 semantics faithful (doc-nits folded); tag `FIBR-0065-complete`. **Next active item: FIBR-0054** (in-app auto-update — the last near-term user ask; NOT yet started; brainstorm → spec → `/cold-eyes` → TDD). The remaining near-term user ask; order was the session's call, "it all ships anyway". Deps: none blocking. Next: brainstorm → spec → `/cold-eyes` → TDD → `/close-phase`. (After it: P09/FIBR-0011 transfer detection, then P10/FIBR-0012 the Home spending-by-category dashboard, which now has the category link FIBR-0010 created + still awaits FIBR-0011.) |
| **Active step** | **FIBR-0143: CLOSED (all steps done) by /close-phase 2026-07-16 — spec→cold-eyes(7 loops)→TDD(dashboard_focus suite, INV-1..9, 20 legs + build_breakdown_donut; rippled FIBR-0138/0012)→audit(semgrep 0)+review(2 cold lanes; production clean, 3 LOW test-strength folded inline)→tag→push.** NEXT active step: **the v0.1.12 release with the user** (bundles FIBR-0143 + FIBR-0138), or budgets **FIBR-0022** — user's call. Also this session: roadmapped **FIBR-0145** (transfer detection learns from confirmed/rejected pairs — user feedback, planned). — prior: **FIBR-0142: CLOSED (all steps done) by /close-phase 2026-07-15 — spec→cold-eyes(5 loops)→TDD(recurring suite, INV-1..13; detector→migration v9→repo→service→tab)→audit(semgrep+bandit 0)+review(2 cold lanes; 1 HIGH fortnightly-rounding + 1 LOW created_at + 3 test-strength, all folded inline)→tag→push.** NEXT active step: **spec FIBR-0143** (dashboard-focus rework — the user's HTML mockup `dashboard_2.html` arrived this session) → cold-eyes → TDD, if the weekly limit allows. — prior: **FIBR-0142: spec CLEARED FOR CODE 2026-07-15 (cold-eyes converged loop 5). NEXT step: TDD — write the failing pure-detector tests first (`tests/features/recurring/`), then implement migration v9 → models → repo → `detect_recurring` → `RecurringService` → the Qt Recurring tab → gate green → `/close-phase`.** — prior: **FIBR-0138: CLOSED (all 9 steps done) by /close-phase 2026-07-14 — spec→cold-eyes(5 loops)→TDD(dashboard_drilldown suite, INV-1..9, 41 legs)→audit(semgrep 0)+review(2 cold lanes; production money-correct; folded a top_of_chain/category_node cycle guard + 5 test-strength adds inline)→tag→push.** NEXT active step: **the next release with the user** (v0.1.12 — bundles FIBR-0138; drill-down README "what works today" refresh happens at that bump), or a user-directed next feature. — prior: **FIBR-0139: CLOSED (all 9 steps done) by /close-phase 2026-07-14 — spec→cold-eyes(8 loops)→TDD(category_library suite, INV-1..11)→audit(semgrep 0)+review(2 cold lanes, 0 CRIT/HIGH/MED)→tag→push.** NEXT active step: **spec FIBR-0138** (expandable dashboard drill-down) → cold-eyes → TDD. — prior step: **FIBR-0128: CLOSED (all 9 steps done) by /close-phase 2026-07-14 — spec→cold-eyes(loop3)→TDD(8 legs)→audit/review→fold(2 LOW)→tag→push.** **FIBR-0138 (expandable dashboard drill-down) DESIGNED + ROADMAPPED 2026-07-14** — brainstorm complete + user-approved: expanding tree (not click-to-drill donut) · Spending/Income drill the category tree → leaf → merchant (×count via smart description cleanup) → individual txns · Transfers by account pair · correctness INV (cleanup only regroups display, never alters a total). Logged 📋 planned in `features-accessibility`; commit `9cc5fde` pushed, gate 915/1. **v0.1.10 PUBLISHED 2026-07-14** — cut the release end-to-end: bumped 0.1.9→0.1.10, built+signed the AppImage (podman clean-room OK) + the Windows `.exe` (windows-build.yml on the v0.1.10 tag), published `v0.1.10` non-prerelease with **4 signed assets** (AppImage/.sig + .exe/**.exe.sig** — the sig that makes the Windows updater live), drop-share `.exe` refreshed; also shipped the About-box two-line tweak (user request). NEXT active work: **spec FIBR-0138** (dashboard drill-down) → cold-eyes → TDD. — prior: 4 (**FIBR-0054 Phase 2 CODE COMPLETE + gate-green + pushed 2026-07-10**. Steps 1–3 done (spec cold-eyed 5 loops; TDD). **Phase 2 (the updater) is fully built** via 8 TDD slices — `services/update{,_fetch,_installer,_key}.py`, `ui/update_dialog.py` + `ui/_update_worker.py`, shell wiring (D15 pending-offer), Settings checkbox, the `test_INV8` `urllib` allowlist, `cryptography` promoted to explicit dep, `tests/features/auto_update/` (71 legs). Gate green **532 passed/1 skipped**, ruff/mypy/bandit/pip-audit/gitleaks clean. The no-network reconciliation across ~10 docs was cold-eyed **5 loops × 3 lanes** → converged (polish). Commits `ecb331f`→`7b79e2b`, all pushed. **Phase 1 DONE + released 2026-07-11** — user ran `gen-signing-key.py`; public key committed + verified; `v0.1.0` **and** `v0.1.1` published (About box now shows the version); dogfood installed to `~/Applications/`. Also filed **FIBR-0083** (timezone + date/time display format) + **FIBR-0084** (customisable/persisted table columns) from dogfooding. Next: user's live update-test, then `/close-phase`.) |
| **Blocked on** | **Nothing blocking.** Phase 1 DONE — user generated the Ed25519 key (2026-07-11); public key committed + verified end-to-end; `v0.1.0` **published**; dogfood AppImage installed to `~/Applications/` + `.desktop` launcher. `v0.1.1` **published** (About-box version added) so the user can live-test the self-update (`0.1.0`→`0.1.1`). **Awaiting the user's live update-test result**, then run `/close-phase` (steps 5–9: `/audit` + `/indie-review` → fold → tag `FIBR-0054-complete` + `v0.1.x` version tags already pushed via `gh release`). |
| **Last update** | 2026-07-17 (**FIBR-0141 SHIPPED — category-tree descendant-cycle guard (tech-debt fix).** Self-directed pick while the user was out (release needs their signing key; budgets FIBR-0022 needs a brainstorm). `CategoryService.update_category` now rejects re-parenting a category under itself or one of its own descendants via a new `_reject_cycle` helper (ascends from the prospective parent, raises ValueError if the subject appears in the chain; `seen`-set-total against a pre-existing corrupt cycle; mirrors `leaf_categories_grouped`'s idiom). Reachable via a direct service call, not the two-root parent picker. Reproduce-first TDD in `tests/features/categories/` (INV-5: self/child/deep-descendant rejected, legit cross-branch move OK); adapted the `categorisation` corrupt-cycle test to inject at the repo layer (below the guard). Judged a full /indie-review disproportionate for a ~15-line guard; self-reviewed + gate-green **1083/1**, mypy 0. Roadmap FIBR-0141 ✅, CHANGELOG [Unreleased]/Fixed. Commit `54b3545` pushed. Ants-MCP feedback: nothing new to mark — file has no un-triaged tail and all mapped ANTS-* ids are `foreign_repo` (maintainer already compacted shipped items). **NEXT ACTIVE unchanged: the v0.1.15 release with the user** (ships FIBR-0146 + now FIBR-0141) **or budgets FIBR-0022** — user's call. — prior: 2026-07-17 (**FIBR-0146 CLOSED by /close-phase — PDF/CSV date-format auto-detect + confirm SHIPPED (code).** TDD 5 slices (pure `detect_date_format` → friendly `csv_importer` RowError → wizard picker/auto-detect/live-preview/banner → `_validate_mapping` empty-format reject → `tests/features/import_date_detect/` spec.md + 39 tests). Close: semgrep **0**; 2 cold review lanes → Lane A (date/money) no reachable defects, Lane B 2 MEDIUM (unblocked matched-profile date-combo re-detect; missing PDF-path tests) + 2 LOW, **all folded inline + re-verified**. Gate green **1080/1**, mypy 0. Tag `FIBR-0146-complete`; journal `docs/journal/FIBR-0146.md`. **NEXT: the v0.1.15 release with the user** (ships FIBR-0146) **or budgets FIBR-0022** — user's call. — prior: 2026-07-16 (**v0.1.14 PUBLISHED — dashboard-focus rework (FIBR-0143) shipped to users.** Bumped 0.1.13→0.1.14 (version lockstep + CHANGELOG [0.1.14] cut; README dashboard prose already refreshed in the FIBR-0143 commit); gate green. `scripts/release-linux.sh` built+clean-roomed+Ed25519-signed the AppImage (podman) → verified vs RELEASE_PUBLIC_KEY_B64 → `gh release create v0.1.14 --latest`; `scripts/release-windows.sh` dispatched windows-build.yml on the tag → downloaded → signed → attached. Release `v0.1.14` carries **4 signed assets** (AppImage/.sig + .exe/**.exe.sig**), marked Latest. Commits `4d13311`(bump)+`3cc0000`(FIBR-0133 SignPath-declined annotate)+`d80a7bf`(FIBR-0146), pushed. Also this session: **SignPath DECLINED** the free code-signing app (FIBR-0133 annotated — reapply after building public presence; .exe stays un-Authenticode-signed → SmartScreen "unknown publisher"). **NEW BUG FIBR-0146 (planned fix):** an external Windows tester's PDF statement imported with **all 165 rows in Error** — the generic PDF importer parses dates via the shared CSV `strptime(mapping.date_format)` path and the applied format doesn't match this bank's DD-first dates, so every row throws and the **raw strptime message** ("time data '...' does not match format") is shown as the row text. Two fixes planned: parse the bank's real date format + replace raw row-error text with a friendly message/banner. **Awaiting from user:** bank name + exact printed date format + ideally a redacted sample PDF (reproduce-first). **NEXT: FIBR-0146** (the import bug, once the sample arrives) or budgets **FIBR-0022**. — prior: 2026-07-16 (**FIBR-0143 CLOSED by /close-phase — dashboard-focus rework SHIPPED (code).** TDD: new `build_breakdown_donut` (own cap loop, PDF donut untouched) + HomeView reworked into 3 columns (Expenditure/Income/Transfers, each pie+coloured header+drill tree) + slim Net strip + unscoped Recurring card + demoted trend strip; explicit node→column map; RecurringService wired into main_window. New `tests/features/dashboard_focus/` (INV-1..9, 20 legs) + rippled FIBR-0138/0012. Close: semgrep 0; 2 cold review lanes → production clean (0 CRIT/HIGH/MED), 3 LOW test-strength folded inline; gate green 1040/1, mypy 0. Commits `070cd76`→`6719de5`+close, pushed; tag `FIBR-0143-complete`; journal `docs/journal/FIBR-0143.md`. **NEXT: the v0.1.12 release with the user** (bundles FIBR-0143 + FIBR-0138) or budgets FIBR-0022.) — prior: 2026-07-16 (**FIBR-0143 spec CLEARED FOR CODE — dashboard-focus rework (breakdown-as-hero).** Brainstormed + user-approved against the mockup `dashboard_2.html` (3 decisions: pies in all 3 columns, keep a slim Net strip, include the deferred FIBR-0142 recurring card now). Wrote `docs/specs/FIBR-0143.md` (INV-1..9, D1..10) + ran **/cold-eyes to convergence — 7 loops × 3 cold lanes = 21 reviews**, loop 7 all-polish (0 CRIT/HIGH/MED). Each lane briefed with a shared verified-signature card (halved per-lane token cost from loop 2). Design: 3 side-by-side columns (Expenditure/Income/Transfers) each = pie (new `build_breakdown_donut`) → coloured header+total → per-column breakdown tree, all fed from the ONE `drill_down` branch node (pie mirrors the list); slim Net strip (`summary().net`); full-width Recurring card (`RecurringService.summary`, unscoped by the Home selectors); monthly-trend bar demoted to a bottom strip. No schema/service-data change (all reuse). Commits `d132c18`→`7238685`, all pushed, gate green 1021/1. Also logged **FIBR-0145** (transfer-detection learns from confirmed/rejected pairs, planned). **NEXT: TDD `tests/features/dashboard_focus/`.**) — prior: 2026-07-15 (**FIBR-0142 CLOSED by /close-phase — recurring-money detection SHIPPED (code).** TDD 4 slices (pure detector → schema v9 `recurring_decisions` → repo/service → Recurring tab after Transfers). Close: semgrep+bandit 0 + 2 cold code-review lanes → **1 HIGH** fortnightly monthly-equivalent rounding (a pre-divided `Decimal(26)/12` factor defeated `ROUND_HALF_EVEN`; fixed to the spec-D8 `amount × N / 12` deferred-division form) **+ 1 LOW** `created_at`-reset-on-flip **+ 3 test-strength adds**, all folded inline; gate green; tag `FIBR-0142-complete`; journal written. Also this session: built the whole feature after the user handed over the FIBR-0143 **dashboard mockup** (`/home/ants/Documents/dashboard_2.html`) — deferred to next per the user (finish FIBR-0142 first). **NEXT: FIBR-0143** dashboard rework (mockup in hand), then budgets FIBR-0022.) — prior: 2026-07-15 (**FIBR-0142 recurring-money-detection spec CLEARED FOR CODE — cold-eyes converged loop 5** (5 loops × 3 cold lanes = 15 reviews). Split the recurring half out of FIBR-0022 (budgets = the follow-up); brainstormed with the user (both directions, Balanced sensitivity, both surfaces — tab now + Home card deferred to FIBR-0143). Spec `docs/specs/FIBR-0142.md` written + 5-loop cold-eyes (money-safety hardened: `median_low` integer representative + integer-exact ±10%, parsed-date ordering, `ROUND_HALF_EVEN` monthly-equivalent, schema v9 keyed on `(direction, merchant_key)`). 6 commits `ffe51a5`→(loop5 convergence). Also: logged **FIBR-0143** (dashboard-focus rework, BLOCKED on the user's HTML mockup); flipped stale-done **FIBR-0041** ✅; marked **FIBR-0031** a dup of **FIBR-0095**. **NEXT: TDD `tests/features/recurring/`.**) — prior: 2026-07-14 (**FIBR-0138 CLOSED by /close-phase — expandable dashboard drill-down SHIPPED (code).** Openable tree below the donut+trend: Income/Spending/Transfers → categories → merchant (×count) → txns, transfers by account pair; every figure summed from integer `amount_minor` so the branch totals equal the tiles (INV-1). New `DrillNode`/`DrillLabels`, `merchant_name` (pure+total), `drill_rows_in_range` (5-tuple), `ReportingService.drill_down` (top-of-chain category algorithm + INV-7 uniform-string sort), HomeView `QScrollArea`+`QTreeWidget`. TDD 41-leg `dashboard_drilldown` suite; `/audit` semgrep 0; `/indie-review` 2 cold lanes → money-correct, folded inline a `top_of_chain`/`category_node` corrupt-data **cycle guard** + 5 test-strength adds (INV-7 mixed-type key falsifier, INV-9 sentinel, cycle regression, count==1 bare label, punctuation `merchant_name`). Gate green **975/1**, mypy 0. Commits `810283f`+`ebbcced`+close; tag `FIBR-0138-complete`; journal `docs/journal/FIBR-0138.md`. **NEXT: the next release with the user** (v0.1.12; drill-down README refresh at that bump), or user-directed next feature.) — prior: 2026-07-14 (**v0.1.11 PUBLISHED — built-in category library (FIBR-0139) shipped to users.** Bumped 0.1.10→0.1.11 (version lockstep across 5 files + CHANGELOG cut + README prose; drift-gate OK; gate green 934/1). Added **two per-platform release scripts** (`scripts/release-linux.sh` + `scripts/release-windows.sh`, partial FIBR-0016 Linux/Windows slices, shellcheck-clean): Linux builds+clean-rooms+Ed25519-signs the AppImage → **hard-gate verifies the .sig vs the committed RELEASE_PUBLIC_KEY_B64** → `gh release create v0.1.11 --latest`; Windows dispatches windows-build.yml on the tag → downloads → renames to `finbreak-0.1.11-x86_64.exe` (the updater's expected asset name) → signs+verifies → attaches. Release `v0.1.11` carries **4 signed assets** (AppImage/.sig + .exe/**.exe.sig** — the sig that keeps the Windows updater live). Commit `ba56d41` (bump+scripts) pushed; tag `v0.1.11` created via `gh release`. **CAVEAT (FIBR-0131 two-cycle):** the Windows swap+relaunch only *runs* on the update AFTER this one — v0.1.11→next is the first real test on the user's Windows box. Windows `.exe` still un-Authenticode-signed → SmartScreen "unknown publisher" expected (FIBR-0133 pending). Drop-share `.exe` refresh NOT yet done this release (offer to user). **NEXT: spec FIBR-0138** (dashboard drill-down) → cold-eyes → TDD.) — prior: 2026-07-14 (**FIBR-0139 CLOSED by /close-phase — built-in category library SHIPPED (code).** Bundled `data/category_library.json` auto-categorises common merchants out of the box (after user rules, only on auto rows; `'library'`-stamped + "~ guess" marker; default-ON toggle). New pure `category_library.py` + engine composition (`CategorySource.LIBRARY`, no migration) + Settings toggle + Transactions marker + 3-site freeze bundling + parity guard. `/audit` semgrep 0 actionable; `/indie-review` 2 cold lanes → 0 CRIT/HIGH/MED (LOW substring-precision accepted as the D2 substring-only tradeoff). Gate green **934/1**, mypy 0. Commit `24e7a91` + close; tag `FIBR-0139-complete`; journal `docs/journal/FIBR-0139.md`. Also this session: logged the parallel-agent read-cache idea to the Ants-MCP feedback file. **NEXT: spec FIBR-0138** (dashboard drill-down) → cold-eyes → TDD.) — prior: 2026-07-14 (**v0.1.10 PUBLISHED** — themes (FIBR-0127) + Windows in-app auto-update (FIBR-0131) + forget-statement-password (FIBR-0128) + auto-lock "Never" (FIBR-0135) + Statements toolbar button (FIBR-0136) + the About-box two-line tweak (user request). Bumped 0.1.9→0.1.10 (5 files + CHANGELOG cut + README refresh; drift-gate OK); gate green **915/1**; built + **Ed25519-signed** the AppImage (podman clean-room) + the Windows `.exe` (windows-build.yml on the v0.1.10 tag) with the **project's own signing key** (`release/finbreak-signing.key`, the FIBR-0054 update-signature — NOT Authenticode/SignPath, which is still FIBR-0133 pending); `gh release create v0.1.10` non-prerelease with **4 assets** incl. the **`.exe.sig`** that activates the Windows updater; both sigs verified vs the committed public key; drop-share `.exe` refreshed (already `samba_share_t`). Windows `.exe` remains un-Authenticode-signed → SmartScreen "unknown publisher" still expected. Commit `121f69b` + tag `v0.1.10` pushed; post-release CHANGELOG bold-glitch cleanup. **NEXT: spec FIBR-0138** (dashboard drill-down) → cold-eyes → TDD. **CAVEAT (FIBR-0131 two-cycle):** the live Windows swap+relaunch only *runs* on the update AFTER this one — v0.1.10→next is the first real test on the user's Windows box.) — prior: 2026-07-14 (**FIBR-0138 designed + roadmapped — the expandable Home dashboard drill-down.** User-approved via brainstorm (3 decisions): (1) an **expanding tree** below the existing donut+trend charts, not a click-to-drill donut; (2) Spending/Income drill the **category tree** → leaf category → group its transactions **by merchant with a ×count** → expand to the individual txns; merchant derived by **smart cleanup** of the free-text `description` (no merchant field exists today); (3) **Transfers by account pair** (from→to, ×count). Correctness INV baked in: the cleanup only regroups **display**, every total is still summed from real `amount_minor`. Logged 📋 planned **FIBR-0138** in `features-accessibility`; commit `9cc5fde` pushed, gate green **915/1**. **NEXT: the v0.1.10 release with the user** (needs their signing key), then spec FIBR-0138.) — prior: 2026-07-14 (**FIBR-0128 CLOSED by /close-phase — forget remembered statement passwords SHIPPED (code).** TDD 8-leg `tests/features/accounts/` (INV-1..5) → repo `ids_with_pdf_password` + service `account_ids_with_pdf_password` + `ui/accounts.py` Forget button/marker/handler (presence = id-set, secret never in the UI; forget-only; confirm-gated; enable/disable before the None early-return). `/cold-eyes` converged loop 3. Close: semgrep+bandit 0; 1 cold review lane → production CLEAN, 2 LOW test-precision folded inline. Gate green **915/1**, mypy 0. Commits `642b592`+`37df6ad`+close; tag `FIBR-0128-complete`; journal `docs/journal/FIBR-0128.md`. Also logged **FIBR-0137** (Business/Personal grouping, considered). **NEXT: the expandable Home dashboard, then the v0.1.10 release with the user.**) — prior: 2026-07-14 (**FIBR-0128 opened + specced.** Brainstormed the stored-PDF-password manager with the user: **never reveal** the secret, place the controls on the **Accounts screen** (per-account — different accounts can hold different statement passwords), **forget-only** (no manual set). Wrote `docs/specs/FIBR-0128.md` (INV-1..6, D1..5); flipped ROADMAP FIBR-0128 🚧. Logged **FIBR-0137** (Business/Personal grouping, considered 💭) from the user's friend's need, and began the **expandable dashboard** design for a later spec. **NEXT: `/cold-eyes` → TDD → `/close-phase`.**) — prior: 2026-07-14 (**FIBR-0127 CLOSED by /close-phase — app-wide theme system SHIPPED (code).** TDD 30-leg `tests/features/theme/` → `ui/theme.py` (six-theme token registry, `ThemeController` live follow-system, non-vault pref) + app/main_window/settings wiring + D11 ADR-0010 citation fixes + ADR-0010 Accepted. Spec test-mechanics corrected during TDD (QSS proxy masks `style().objectName()` → INV-1/6 pin Fusion via a `setStyle` spy, Qt 6.11.1 in-venv). `/audit` 0 actionable; `/indie-review` 2 cold lanes → no CRIT/HIGH/MED, 1 LOW (INV-10 pixmap-content re-tint falsifier) folded inline. Gate green **907/1**, mypy 0. Commits `34be695`+`ab28790` pushed; tag `FIBR-0127-complete`; journal `docs/journal/FIBR-0127.md`. **NEXT: FIBR-0128** (stored-PDF-password mgmt) → then the **v0.1.10 release** with the user.) — prior: 2026-07-14 (**FIBR-0127 spec CLEARED FOR CODE — cold-eyes converged loop 6.** User's queue: FIBR-0127 theme system → FIBR-0128 saved-PDF-password mgr → v0.1.10 release (together). Brainstormed + specced the app-wide theme system: 6 finance themes (Ledger/Parchment/Mint · Midnight/Graphite/Emerald), live follow-system, gradient/glow + grid row-highlighting polish, theme-aware toolbar icons; new `ui/theme.py` + ADR-0010; non-vault theme pref (applies pre-unlock). 6 cold-eyes loops (18 reviews) polish-converged; ADR-0010 Accepted. **NEXT: TDD `tests/features/theme/` → implement → gate → /close-phase**, then FIBR-0128, then the release. Commits `66b7999`→`b039126`, all pushed? **NO — not yet pushed** (6 local commits queued; public repo, push after this batch).) — prior: 2026-07-14 (**FIBR-0131 CLOSED by /close-phase** — Windows in-app auto-update SHIPPED (code) by TDD: `WindowsInstaller` behind the existing `Installer` seam; detached PowerShell helper waits by exe **image path** → swaps the Ed25519-verified `.exe` → relaunches; installer-driven picker; `appimage_url`→`asset_url`. `/audit` 0 actionable (3 bandit assert-in-tests FPs); `/indie-review` 2 cold lanes → 1 MEDIUM fixed inline (**spawn→wipe→exit** so a `Popen` failure can't strand a wiped key; Linux twin guarded too). Gate **877/1**, mypy 0; tag `FIBR-0131-complete`; journal `docs/journal/FIBR-0131.md`. Live Windows swap = pending two-cycle manual test + needs a release attaching the `.exe.sig`. **NEXT: user direction** — v0.1.10 release to ship it, FIBR-0133 (SignPath), P12 backlog.) — prior: 2026-07-14 (**FIBR-0054 CLOSED by /close-phase** — Linux in-app auto-update; live relaunch **v0.1.8→v0.1.9** proven; `/audit` + 2 cold review lanes → **1 MEDIUM** (`_on_download_failed` auto-lock guard) **+ 3 LOW** fixed inline, **allowlist-001** for the semgrep `urllib` FP; gate **856/1**; tag `FIBR-0054-complete`; journal `docs/journal/FIBR-0054.md`. Also shipped: **FIBR-0134** (Windows `.exe` `--icon` fix). Next: user's auto-lock-"Never" + Statements-toolbar-icon requests (2026-07-14).) — prior: 2026-07-13 (**FIBR-0015 CLOSED by /close-phase** — Windows self-contained `.exe` shipped. Swapped the SQLCipher binding `sqlcipher3-binary`→`sqlcipher3-wheels` project-wide (same 4.12.0 engine, cross-platform wheels; ADR-0009), fixture-first cross-package regression proving old vaults/backups still open. `windows-build.yml` ran green on windows-latest (freeze + Python-off-PATH clean-room + servercore stretch) → finbreak.exe artifact. mypy-ripple fixed at root cause (sqlcipher3-wheels types lastrowid int|None → shared `repositories.last_insert_id`). `/audit` 0 actionable; `/indie-review` 0 defects; ADR-0009 cold-eyes-converged. Gate 851/1; tag `FIBR-0015-complete`. macOS/Flatpak → FIBR-0130.) — prior: 2026-07-13 (**FIBR-0014 CLOSED by /close-phase** — encrypted backup export/restore SHIPPED by TDD (7 slices: Vault export_to/rekey/open helpers; BackupService export + restore; safe-zip/version/param-floor guards; Settings Export + pre-login Restore UI; interrupted-restore reconciliation; security-model.md T11/D8). D2 SQLCipher mechanics proven by a throwaway spike (sqlcipher3-binary 0.6.0 / SQLCipher 4.12.0) before any code. `/audit` **0** (1 bandit B608 FP suppressed on the INV-2 dynamic-table test helper); **2 cold review lanes → 6 findings all fixed inline** (2 HIGH crypto/UI key-copy leak + orphaned-modal; HIGH export DatabaseError/cursor; MED restore normalisation + *.old mis-pair; LOW cursor) with regression tests; security-model.md reviewed cold (1 LOW nit fixed). Gate green **841/1**, mypy 0; tag `FIBR-0014-complete`; journal `docs/journal/FIBR-0014.md`. Next active: **FIBR-0015** (Windows build). See §3 journal.) — prior: 2026-07-13 (**FIBR-0123 CLOSED by /close-phase** — grouped category pickers SHIPPED by TDD (6 slices: `leaf_categories_grouped` service, `_widgets` helpers, both dialogs, the Transactions filter, the manager label-map refactor); `/audit` **0**; `/indie-review` 2 cold lanes → UI/tests clean, logic clean but **1 LOW** (unguarded parent-chain ascent could hang on a corrupt cycle) **fixed inline** with a fail-loud guard + reproduce-first test; gate green; tag `FIBR-0123-complete`; journal `docs/journal/FIBR-0123.md`. Next active: **FIBR-0014** (encrypted backup — spec cleared, TDD next). See §3 journal 2026-07-13.) — prior: 2026-07-13 (**FIBR-0013 CLOSED by /close-phase** — P11 locked-PDF export SHIPPED by TDD (7 slices); `/audit` 0 in-scope, `/indie-review` no CRIT/HIGH/MED + 3 LOW fixed inline; gate 779/1; tag `FIBR-0013-complete`; journal `docs/journal/FIBR-0013.md`. Next active: **FIBR-0123** (category-picker grouping). See §3 journal 2026-07-13.) — prior: 2026-07-13 (**FIBR-0012 CLOSED — P10 reporting dashboard + Transactions tab SHIPPED by TDD** (11 slices). `ReportingService` (pure period model + `summary`/`spending_by_category`/`monthly_trend`, transfers excluded from every figure, integer-`amount_minor`-exact) + `ReportPrefs` persistence on the v1 settings table; **Home reworked into the QtCharts dashboard** (period+account selectors, income/spending/net tiles, ≤8-wedge donut + Other-collapse + empty placeholder, 12-month grouped-bar trend); new **Transactions tab** (search+date-range+account+category filters, absorbing FIBR-0109); **7-tab shell** (Home·Transactions·Statements·Accounts·Categories·Rules·Transfers), count **live from Home's `ReportingService`**, QtCharts `--self-test` leg, **ADR-0008**. Close: `/audit` **0 actionable**; `/indie-review` 2 cold lanes → **3 findings all fixed inline** (report_prefs year-bound INV-2 gap; Transactions↔Statements shared column-key collision → per-table objectNames; bare-`except`→`VaultLockedError` slot guards) + 2 regression tests. Gate green **712/1**, mypy 0. Also shipped this session: **FIBR-0120** (drag-to-reorder table columns, persisted — user request, via the shared `_table_state` seam) and **FIBR-0121** filed (loan-account sign display, display-only, approved — for its own spec). Commits through the FIBR-0012 close; tag `FIBR-0012-complete`. **Next queue:** P11/FIBR-0013 (locked-PDF export — user wants the password **optional**); **FIBR-0054** still open pending the user's live 0.1.6→0.1.7 auto-relaunch test. See §3 journal 2026-07-13.) — prior: 2026-07-12 (**FIBR-0012 spec CLEARED FOR CODE** — P10 reporting dashboard + Transactions tab; `/cold-eyes` **converged (6 loops × 3 lanes)**; **ADR-0008** QtCharts written. **Next step: TDD** (`tests/features/{reporting,transactions_tab,dashboard}/`) → `/close-phase`. Also this session: **FIBR-0119** Home-Loan-import description-pollution fix **SHIPPED** (gate 656/1, pushed); `.claude/bump.json` release recipe now refreshes README. The **NEW ACTIVE ITEM is FIBR-0012** — the older FIBR-0054/step-progress fields below are superseded; FIBR-0054 stays open pending the user's live 0.1.6→0.1.7 relaunch test. See §3 journal 2026-07-12.) — prior: 2026-07-12 (**v0.1.7 PUBLISHED** — bundled FIBR-0011 (transfers) + FIBR-0116/0117/0118 (UI polish, built test-first this session) + FIBR-0112/0114 (dogfooding fixes). Signed AppImage clean-room-proved + .sig verified vs the committed public key; `gh release create v0.1.7` non-prerelease, /releases/latest → v0.1.7. Gate green 655/1, mypy 0. The user's installed **0.1.6→0.1.7** update is now the true FIBR-0054 auto-relaunch test → close FIBR-0054 if it relaunches. See §3 journal.) — prior: 2026-07-12 (**FIBR-0011 CLOSED — P09 transfer detection shipped by TDD** (schema v8 `transfer_pairs` + `TransferDetectionService` + the 6th Transfers tab; `/audit` 0-in-new-code, `/indie-review` data/logic CLEAN + 2 UI LOW folded; gate green 645/1, mypy 0; tag `FIBR-0011-complete`). Unblocks FIBR-0012 (dashboard). **On main, UNRELEASED** with FIBR-0112/0114 — next: a **v0.1.7** release, and the user asked to bundle polish items FIBR-0116/0117/0118 into it. See §3 journal 2026-07-12.) — prior: 2026-07-12 (**v0.1.6 PUBLISHED — two dogfooding fixes bundled**. (1) **FIBR-0106** credit-card import: `_cc_opening` mis-read the opening balance from a *prose* "balance brought forward" decoy line printed before the real anchor row (grabbed the closing figure → "didn't add up"). Fixed by anchoring on a new `_CC_BROUGHT_FORWARD` regex requiring the amount to *immediately* follow the phrase, then taking the first tail token; sign still via `_signed_balance`. TDD: 2 pure unit tests (decoy-reject + negative-sign); SB suite 50 green, no regression on the 6 real statements. (2) **FIBR-0054** self-update relaunch: the 0.1.4→0.1.5 detached-Popen-then-`os._exit` still raced the old AppImage's FUSE/`_MEI` teardown ("closed but didn't reopen"). Fixed with a detached `/bin/sh` **waiter** (new session) that polls `kill -0 <old-pid>` until this process fully exits, *then* execs the swapped image (reset env); ~60s cap; + a diagnostic relaunch log (data-dir sibling). Same wait-for-parent pattern RPCS3/PCSX2 use. TDD: pure `_relaunch_command` builder + updated detached-session/env + log-write tests + a real-process smoke (blocked 0.51s until old pid died, then execed). Gate green **602 passed/1 skipped** throughout. **Two-cycle trap:** the relaunch fix ships in 0.1.6 but only *runs* on 0.1.6→next; the 0.1.5→0.1.6 hop still uses the old 0.1.5 relaunch, so one manual reopen is expected for that update. Release: bumped `__init__`/`pyproject`/smoke-assert to 0.1.6, cut CHANGELOG `[0.1.6] - 2026-07-12`, `build-release-appimage.sh` (freeze + clean-room + sign), **signature verified against the committed `RELEASE_PUBLIC_KEY_B64`**, `gh release create v0.1.6` (non-prerelease, `/releases/latest`→v0.1.6, both assets attached). Commits `595d058`(FIBR-0106)/`f794c95`(FIBR-0054)/`f2c98c0`(bump), all pushed. ROADMAP FIBR-0106 ✅ + FIBR-0107 ✅ (the relaunch fix); CHANGELOG two Fixed entries.) — prior: 2026-07-11 (**FIBR-0105 SHIPPED (code) — user-configurable amount display**. The user asked why some Home amounts show in brackets; built a Settings choice: negative sign as **minus** (`-25,000.00`) or **accounting brackets** (`(25,000.00)`), plus **red/green colouring** on/off — default minus + colour on, brackets kept so an accountant keeps the familiar notation. TDD in **4 slices**: (1) `AmountPrefs` frozen dataclass + `AuthService.amount_prefs`/`set_amount_prefs` over `SettingsRepository`, each key fail-safe to its default (INV-2/5); (2) `_format_amount(display, symbol, negative_style="minus")` formats the **magnitude** via QLocale then applies the sign **explicitly** (locale-independent brackets — the one cold-eyes HIGH), + `_NEGATIVE_TEXT`/`_POSITIVE_TEXT` and per-cell colour in `HomeView.refresh` (fresh item per render → no stale colour; zero/off left default; display-only, stored amount untouched — INV-1/3/4); (3) Settings combo `settings_amount_negative` + checkbox `settings_amount_colour` (ASCII `-` glyph matching the formatter) and the first-run mirror persisted at `_on_derived` (INV-6/7); (4) shell reads `amount_prefs()` post-unlock in `_build_workspace`, passes to Home, re-pushes on Save (live update). **19 new tests**; full gate green **598 passed/1 skipped**, ruff/format/bandit/pip-audit/gitleaks/mypy clean. Spec was `/cold-eyes`-converged at loop 3 last session. Commits (4 slices) `a16412e`→`a09e4fd`, all pushed. ROADMAP FIBR-0105 → ✅; spec Status → SHIPPED. **Lands on main; NOT yet released** — bundles with the inline update-notes change into **v0.1.5** (user gates the publish). Publishing 0.1.4→0.1.5 is also the true auto-relaunch test that closes FIBR-0054.) — prior: 2026-07-10 (**FIBR-0054 Phase 2 SHIPPED (code) + docs cold-eyes CONVERGED**. Built the whole in-app updater by 8 TDD red→green slices: version grammar + asset predicate (D13/D14); `UpdateVerificationError`/`update_key` all-zero placeholder (fail-closed); `AppImageInstaller` chmod→os.replace→key-wipe→execv + `detect_installer` (INV-5/6/7); `update_fetch` (sole `urllib` module, byte caps + https-only, INV-10/12); `UpdateService` check + Ed25519 `download_and_verify` (INV-1/2/3/4/8/11); the amended `test_INV8` `_network_offenders` allowlist; `UpdateDialog` (3 signals + busy, no-exec) + `UpdateCheckWorker`/`DownloadWorker`; shell D15 pending-offer lifecycle + Settings checkbox + `cryptography` promotion. Then reconciled every "no network" statement across security-model/design/CLAUDE/README/ROADMAP/testing/ADR-0003 and ran `/cold-eyes` **5 loops × 3 lanes (15 reviews)** → polish-converged; it caught two mis-citations I'd introduced (consent INV-8→INV-1, signature bare-INV-2→FIBR-0054 INV-4), a testing.md §9-vs-§6 self-contradiction, and drove the design.md architecture diagram to actually draw the egress. Gate green **532 passed/1 skipped** each push; one gitleaks generic-api-key false-positive on a doc-prose phrase (an "API," immediately followed by a signature-scheme token) reworded at the root cause, no allowlist. 16 commits `ecb331f`→`7b79e2b`, all pushed. **Next: Phase 1 (user keygen → 0.1.0 → sign → publish `v0.1.0`) → dogfood install → `/close-phase`.**) — prior: 2026-07-10 (**FIBR-0054 spec CONVERGED** — brainstormed the full auto-update design with the user (they chose **full in-app update, Linux/AppImage first**, Windows behind an `Installer` seam not built; **offer-after-unlock** prompt; **Ed25519** signature gate verified via the already-bundled `cryptography` lib — no new runtime dep). Two phases: (1) real release infra (version 0.1.0 + signed `finbreak-0.1.0-x86_64.AppImage` + published `v0.1.0`), (2) the updater (opt-in launch check → Later/Skip/Update-now → download → verify → atomic AppImage swap → key-wipe → relaunch). Wrote `docs/specs/FIBR-0054.md`; `/cold-eyes` ran **5 cold loops × 3 lanes (15 reviews)**, converged at loop 5 (polish); severity trajectory C1→0→0→0→0, H4→3→3→2→0. Notable catches: incomplete no-network amendment (the rule was stated in ~10 docs — security-model ×4, design.md, CLAUDE.md, README.md, ROADMAP ×1, testing.md, ADR-0003, all reconciled); the launch-check-vs-unlock modal collision (→ D15 offer-after-unlock, user-decided); the download-worker contract; the `apply()` signature + key-wipe ordering. 6 commits `102a95e`→`90e72e4`. **Next: TDD.** Ants-MCP feedback appended (positive spec+cold-eyes datapoint; ANTS-3468 re-verified on build c57e16b6).) — prior: 2026-07-10 (**FIBR-0010 CLOSED** by `/close-phase` — P08 rules engine + manual override + learning shipped. Schema **v6→v7** (`transactions.category_id`/`category_source` + `categorization_rules`, atomic `_migrate_to_v7`). Core: `text.normalise_text` (shared matcher/dedup primitive); pure `categorize` (first-match by priority) + commit-free `recategorize_auto_rows` (golden rule — recompute autos, never touch a manual row, NULL-safe `IS NULL OR <> 'manual'` predicate); `CategorizationService` (rules CRUD + top-insert + adjacent-swap reorder + `set_manual_category` + `would_categorize` + `apply_rules`); import runs the rules inside its own txn; `CategoryService` atomic delete-cascade + `delete_blast_radius`; `list_transactions` 4-tuple. UI: Home Category column + context Set-category + learning offer; Rules tab (`RulesWidget`+`RuleEditDialog`); `CategoryPickerDialog`; net-new category-delete blast-radius confirm; 5th Rules tab. TDD **45-test** `tests/features/categorisation/` (INV-1..16 + edges) + ripple (schema `==6`→`==7` across 6 suites, `list_transactions` 4-tuple unpacks, HomeView 2-arg, 5-tab/toolbar shell-shape, categories delete-confirm). Gate green **411 passed/1 skipped**, mypy 0, ruff/format/bandit/pip-audit/gitleaks clean. Close: `/audit` **0 actionable**; `/indie-review` **3 cold lanes + a confirming pass** — data/core CLEAN, then **1 HIGH** (ui/home.py auto-lock during the learning dialog crashed the trailing `refresh()` — the picker path was guarded but the learning path wasn't; set+learn+refresh now share one `VaultLockedError` guard, regression test added) + **3 MEDIUM** (spec-mandated `_v6`→`_v7` test-name renames skipped; INV-3 re-import half untested; INV-8 confirm test weak on distinct counts) + **1 LOW** (two identical `leaf_categories` impls → centralized on `CategorizationService.leaf_categories()`, removed the ui helper) + **1 INFO** (stale four-tab docstrings) all **folded inline** (commits `9db5d99` TDD, `aff141a` fold); confirming re-review **CLEAN**. Allowlist unchanged (0 FP). Spec annotated for two implementation refinements (cascade deletes the category in-line commit-free — `repo.delete` commits, would break INV-7 atomicity; category selectors are flat combos, grouping deferred). ROADMAP **FIBR-0010 → ✅** and **FIBR-0035 → ✅** (learn-from-corrections fully delivered by FIBR-0010 INV-5/D11; the update-variant subsumed by D6). Journal `docs/journal/FIBR-0010.md`; tag `FIBR-0010-complete`. Next active item **FIBR-0054** (in-app auto-update). This created the transaction→category link P10/FIBR-0012 (dashboard) will consume.) — prior: 2026-07-09 (**FIBR-0037 CLOSED** — branded app icon shipped (pulled forward from P13 when the user brought an icon concept). Designed with the user: a "spending by category" **donut** (green/blue/teal/orange segments) + **gold coin** centre on a dark navy tile — chosen after shrink-testing candidates for small-size legibility (holds at 24px). Single 1024 master `assets/icon/finbreak.png` + reproducible `scripts/make-icons.sh` (Linux PNGs 16-512, 7-size Windows `.ico`, macOS `.iconset`; no drift). Runtime `ui/icons/app.png` travels as package data, set via `QApplication.setWindowIcon` (every window/dialog + taskbar); `--self-test` renders it (bundle-travel proof). `pyproject` glob += `*.png`; PyInstaller `--add-data` is dir-level so it travels. Close: `/audit` **0** (ruff/bandit/semgrep/shellcheck); indie-review CLEAN (1 stale-comment LOW folded). Gate green **344 passed/1 skipped**, mypy 0. macOS `.icns` is a FIBR-0015 mac-build step from the committed `.iconset`. ROADMAP FIBR-0037 → ✅; journal `docs/journal/FIBR-0037.md`; tag `FIBR-0037-complete`. **Unblocks FIBR-0015** (the builds bake in the icon). Active item stays **FIBR-0010** (P08 rules).) — prior: 2026-07-09 (**FIBR-0055 CLOSED** by `/close-phase` — Settings screen + configurable auto-lock timeout shipped. Pulled the Settings-screen scaffold + timeout forward from FIBR-0014 (near-term user ask 2026-07-09). Delivered: `repositories/settings.py` (generic `SettingsRepository` key→value upsert over the v1 `settings` table); `services/auth.py` `AUTO_LOCK_MINUTES`→`DEFAULT_AUTO_LOCK_MINUTES`(=10) + `ALLOWED_AUTO_LOCK_MINUTES`=(1,5,10,15,30), `auto_lock_minutes()` guarded-parse + `set_auto_lock_minutes()` validate→persist→re-arm, `_arm_timer` reads it; `ui/settings.py` `SettingsDialog` (auto-lock combo + read-only currency; Save→service+`saved`, shell owns close, no vault ref); `ui/main_window.py` File→Settings… vault-dependent action + wiring. **No schema change** (settings table is v1; absence→default). Spec `/cold-eyes`-converged in **4 cold loops** (3 lanes/loop, 12 reviewers); TDD **19-leg** `tests/features/settings/` + the app_shell `action_settings` ripple. Close: `/audit` **0** (ruff/bandit/semgrep); `/indie-review` **3 cold lanes** — data/service + UI/shell **CLEAN**, tests **2 LOW** (INV-9 Cancel-leg fidelity) **folded inline** (commit `94b5f35`). Gate green **343 passed/1 skipped**, mypy 0; allowlist unchanged (0 FP). TDD surfaced + fixed a spec inaccuracy (auto-lock re-opens the UnlockDialog into `_dialog`, so INV-7 asserts the captured SettingsDialog is destroyed, not `_dialog is None`). Also **reconciled the ROADMAP** FIBR-0014 note + FIBR-0055 bullet (theme toggle + stored-PDF-password management stay in FIBR-0014, not pulled forward) + split number/date-format deferral (FIBR-0017/FIBR-0048), and fixed a copied dead ADR-0003 link in FIBR-0052. ROADMAP FIBR-0055 → ✅; journal `docs/journal/FIBR-0055.md`; tag `FIBR-0055-complete`. Next active item **FIBR-0010** (P08 rules); **FIBR-0054** auto-update still queued.) — prior: 2026-07-09 (**FIBR-0052 CLOSED** by `/close-phase` — P07.6 tabbed workspace + statement provenance & delete shipped. TDD: 27-test `tests/features/statements/` (INV-1..13 + subs) → the 12 Deliverables to green: the tabbed `QTabWidget` workspace + Home toolbar button + vault-independent Window menu (Center/Reset) + geometry/last-tab INI outside the vault; the Statements tab (`StatementService` LEFT JOIN+COUNT read + atomic delete, `StatementsWidget`); the v5→v6 provenance column + `commit_import` reorder+stamp + ambiguity-guarded backfill; repos (`add`→int / `id_for_span` / `list_all` / `delete` / `add_batch(stamp)` / `delete_for_statement`); `StatementRow`; the `show_done` flag; `home.svg`. FIBR-0051 app_shell ripple + v5→v6 schema ripple across 6 suites. Gate green **324 passed/1 skipped**, mypy 0; `home.svg` travels via the existing icons glob (DoD #2). Real Standard Bank credit-card PDF validated end-to-end in a **throwaway** vault (53 txns, exact count, clean delete) — never committed. Close: `/audit` **0**; `/indie-review` **3 cold lanes** (data/service, shell/security, tests) — **no CRIT/HIGH/MED**, security spine (workspace destroyed+refs nulled on lock, geometry INI outside vault, Window menu vault-independent) verified; **1 production LOW** (auto-lock-during-delete-confirm → `VaultLockedError` guard on `StatementsWidget._on_delete`) + **1 test-fidelity MED** (reorder made `test_INV7_atomic` vacuous → wedge rewired to fail on the batch) + **4 coverage findings** (import-done handler test, count-naming assert, "Statement deleted" status assert, toolbar-order test) folded inline (commit `97a2c70`). Allowlist unchanged (0 false positives). ROADMAP FIBR-0052 → ✅; journal `docs/journal/FIBR-0052.md`; tag `FIBR-0052-complete`. **Also queued from user (2026-07-09): FIBR-0055 Settings screen (configurable auto-lock timeout first).** Next active item **FIBR-0010** (P08 rules).) — prior: 2026-07-09 (**FIBR-0052 opened + design APPROVED** — after FIBR-0051 shipped, the user asked to evolve the shell: (1) tabs for the main window (Home/Statements/Accounts/Categories), (2) Home = advice + income/expenditure summary + breakdown, (3) everything under View as tabs (+ keep the menu), (4) remember window geometry + a Center-window action; plus a follow-up: (5) add a Home button to the toolbar. Ran the brainstorming skill. Surfaced the non-obvious costs: transactions carry NO statement-provenance today (verified — `transactions` has no statement link, only `statement_periods` for dedup), so per-statement drill-down needs a schema stamp; and the Home income/expenditure summary is the dashboard (FIBR-0012), BLOCKED on P08 category-link + P09 transfer-detection for correct totals (self-transfers double-count otherwise). User deferred sequencing to me. **Staged into 3 rounds** — filed **FIBR-0052** (P07.6) as Round 1 (tabbed shell + Home toolbar button + window geometry, Statements tab read-only); Round 2 = Statements first-class (provenance stamp + undo-import); Round 3 = Home dashboard (after P08/P09). Design APPROVED by the user; next session writes `docs/specs/FIBR-0052.md` → `/cold-eyes`. **P08/FIBR-0010 now follows FIBR-0052.** User is relaunching the terminal + compacting before continuing.) — prior: 2026-07-09 (**FIBR-0051 CLOSED** by `/close-phase` — P07.5 app-shell shipped. TDD: 22-test `tests/features/app_shell/` (INV-1..10 + subs) → the 10 Deliverables to green: the `MainWindow(QMainWindow)` shell + state machine (destroy-on-lock content hygiene, INV-3), `HomeView` (empty/table toggle), `ManualEntryDialog`, the first-run/unlock `QWidget → QDialog` re-home (mid-derivation dismissal no-ops, INV-2f), the SVG toolbar glyphs + loader (package-data + PyInstaller `--add-data`; `_selftest` icon-render leg, DoD #2), the Donate menu. D10 ripple re-homed `test_vault.py` + `test_accounts.py` assertions to the split widgets. Gate green **299 passed/1 skipped**, mypy 0; FIBR-0003 build smoke **PASS** (icons travel). Close: `/audit` (ruff/bandit/semgrep/shellcheck/gitleaks) **0**; `/indie-review` **2 cold lanes** (shell+dialogs security/lifetime; home+tests+packaging) — **no CRIT/HIGH/MED**, security spine INV-3/4/4a/4b/5 verified correct; **2 LOW** (status-bar Ready restore off `messageChanged`; locale-hermetic `_format_amount` test) + **1 INFO** (`QIcon`-absent rationale — verified false, corrected comment + spec §13) folded inline. One gitleaks false positive (`shiboken6.isValid` in spec prose) handled in `.gitleaks.toml`, allowlist unchanged. ROADMAP FIBR-0051 → ✅, **FIBR-0040 → ✅** (donate links delivered), FIBR-0049 stays open (field hints remain). Journal `docs/journal/FIBR-0051.md`; tag `FIBR-0051-complete`.) — prior: 2026-07-09 (**FIBR-0051 spec cold-eyes CONVERGED** after 11 loops (6–11 run this session post usage-reset). Loops 6–11 fixed: M1 unreachable zero-accounts branch (dropped `AccountService` from `HomeView`); INV-9 empty-picker reframed defensive-untested; D2 inverted worker/dialog lifetime; `HomeView.current_page()` accessor + inner-page objectNames; a self-inflicted CRIT in loop 9 (INV-4b `self._dialog is None` unsatisfiable — step 5 re-opens the tracked `UnlockDialog`); INV-8a FUNDING.yml stdlib flow-sequence parse; `coding.md § 1.1` + FIBR-0023 gloss cross-doc fixes; `design.md` "dark theme" relabel; ROADMAP FIBR-0039/0040/0049 reconciliation (FIBR-0051 closes FIBR-0040, partially delivers FIBR-0049). Accuracy + cross-doc lanes ended fully clean. Signed off under the user's polish-only rule. Next: TDD → `/close-phase`.) — prior: 2026-07-05 (**NEW ACTIVE ITEM FIBR-0051** — app-shell UX redesign. User delegated "what's next"; chose the queued app-shell redesign → brainstormed (7 Qs: scope=full-dashboard-eventually, sequenced as 4 pieces, shell-first, locked-view=full-window+popup, manual-entry=popup dialog, +status bar, +Donate menu). Filed FIBR-0051 as new phase P07.5 (roadmap `features-ux` section, no downstream renumber). Verified all reshaped interfaces + PySide6 6.11.1 APIs empirically (§13). Wrote the spec (INV-1..10, D1..10, test-ripple named). Next: `/cold-eyes` → TDD → `/close-phase`.) — prior FIBR-0050 open: 2026-07-05 (FIBR-0050 **CLOSED** by `/close-phase` — one Standard Bank text-layer reader for all six account types shipped. Spec cold-eyes-converged (9 loops); TDD (36 tests); validated end-to-end on all 6 real statements. Close: `/audit` clean; `/indie-review` 2 cold rounds — round 1 fixed the code findings, a confirming re-review fixed 1 HIGH (corrupt-PDF Qt-slot crash) + 2 MED (region-scoped number detect, INV-12 test correction) + 2 LOW (Family-C fold, `_cc_opening` sign), final cold pair clean. Gate green 277 passed/1 skipped, mypy 0. Fixtures 100% synthetic. Journal `docs/journal/FIBR-0050.md`; tag `FIBR-0050-complete`.) — prior FIBR-0050 open: 2026-07-04 (FIBR-0009 **CLOSED** by `/close-phase` — P07 PDF import shipped. TDD: 41-test `tests/features/pdf_import/` + the extract-then-CSV-adapter `PdfImporter` (in-memory `pikepdf` decrypt, D8 grouping / D13 uniquify), the v5 migration, accounts credential accessors, the D10 rename, the wizard PDF branch + `password_dialog`, the `_selftest` pdfplumber leg. Schema ripple `==4`→`==5` across 5 suites. Gate green 240 passed/1 skipped, mypy 0; FIBR-0003 build smoke PASS. Close: `/audit` 0, `/indie-review` 3 cold lanes (2 clean, 1 LOW coverage-gap fixed inline). Also: repointed stale `.venv` shebangs (dir-rename fallout); created + pinned a `finbreak.desktop` launcher (runs current `src/`); Ants-MCP feedback re-verified (ANTS-3438 still reproduces; 3439 moot for this project). Tag `FIBR-0009-complete`) |
| **Next gate** | **Tech-debt backlog CLEARED 2026-07-10** — the whole `warnings-tech-debt` section (15 items: FIBR-0043/0080/0081/0076/0077/0066/0068/0069/0079/0078/0075/0070/0062/0063/0064) shipped this session at the user's "all outstanding fixes in first" directive; ~16 gate-green commits (mypy 0, ruff clean, gate 452 passed/1 skipped), pushed through `fb05fa0`. **Only FIBR-0067 left** in the section — blocked on real anonymised sample statements (annotated). Notable: FIBR-0075 (PDF decompression-bomb) resolved by **documenting the accepted residual risk** in security-model.md (user deferred; robust cross-platform fix disproportionate for a local app); FIBR-0070 (unwired profile API) **kept + intent-documented** (user's "if we'll use it later" call); FIBR-0064's strengthened corrupt-PDF assert **found + fixed a real UX bug** (raw pikepdf error → friendly message). Remaining phase-ordered work: **FIBR-0054** (auto-update — the active item, near-term user ask) → P09/FIBR-0011 → P10/FIBR-0012. |
| **Convergence checkpoint** | 5 (consecutive `FP##` items immediately preceding any ✅-`implement`-Kind close in the active release block — see `~/.claude/commands/close-phase.md § 5a-6`) |
| **Debt-sweep phase threshold** | 5 (auto-prompt for `/debt-sweep` after this many phases without one) |
| **Last debt sweep** | (none yet) |
| **Repo visibility** | PUBLIC (cached 2026-06-30; push freely per global rule § 6) |

### Step progress

While an item is active, Claude marks the current step 🚧;
completed steps flip to ✅. Resets to all ⬜ when a new item
becomes active.

**FIBR-0015 (CLOSED 2026-07-13 by /close-phase):** Windows self-contained `.exe`
build. All 9 steps ✅. Blocker dissolved by swapping `sqlcipher3-binary` →
`sqlcipher3-wheels` (same SQLCipher 4.12.0, cross-platform wheels; ADR-0009),
proven vault-portable both directions. TDD (fixture-first cross-package
regression + INV-3 parity guard + freeze driver); `.github/workflows/windows-build.yml`
ran green on `windows-latest` (freeze + Python-off-PATH clean-room
`FINBREAK_SELFTEST_OK` + the optional servercore container stretch, all ✅) →
`finbreak-windows-exe` artifact (~85 MB). `/audit` 0 actionable (5 bandit LOW all
outside the `-r src` gate scope); `/indie-review` 2 cold lanes 0 defects; ADR-0009
cold-eyes-converged (2 loops); gate green 851/1. Tag `FIBR-0015-complete`; journal
`docs/journal/FIBR-0015.md`. macOS `.dmg` + Flatpak/Flathub split to **FIBR-0130**.
Next: user direction — **FIBR-0054** (auto-update) still open awaiting the user's
live post-v0.1.8 relaunch test; **FIBR-0130** (macOS/Flatpak) + **FIBR-0016**
(release automation) queued 📋.

*(FIBR-0014 CLOSED 2026-07-13 by /close-phase — encrypted backup export/restore
shipped by TDD (7 slices) + a fold-in of 6 cold-review findings; D2 SQLCipher
spike proven first; `/audit` 0 (1 bandit B608 FP suppressed); gate green 841/1,
mypy 0; tag `FIBR-0014-complete`; journal `docs/journal/FIBR-0014.md`.)*

*(FIBR-0123 closed 2026-07-13 by /close-phase — grouped category pickers shipped by
TDD (6 slices) + 1 indie-review LOW (parent-cycle guard) fixed inline; `/audit` 0;
gate green; tag `FIBR-0123-complete`; journal `docs/journal/FIBR-0123.md`.)*

*(FIBR-0013 closed 2026-07-13 by /close-phase — P11 locked-PDF export shipped, tag
`FIBR-0013-complete`. FIBR-0054 auto-update remains open, awaiting the user's live
post-v0.1.8 auto-relaunch test — its step-progress history retained below.)*

**FIBR-0054 (open, not active):**
1. ✅ Write + cold-eyes spec (5 loops, converged)
2. ✅ Verify dependencies (`cryptography` bundled; shell reuse points)
3. ✅ Write failing tests (`tests/features/auto_update/`, 71 legs)
4. ✅ Implement until tests pass — **Phase 2 (updater) + Phase 1 (real signed release) BOTH DONE + gate-green + pushed.** Phase 1: user ran `gen-signing-key.py` (2026-07-11); public key committed (`update_key.py`) + verified end-to-end vs the on-disk private key; `build-release-appimage.sh` (`--release` on the build-smoke pair) built + clean-room-proved + signed `finbreak-0.1.{0,1}-x86_64.AppImage`; `v0.1.0` + `v0.1.1` **published** (non-prerelease, D11). Dogfood installed to `~/Applications/` + `.desktop`. About box now shows `__version__`. CHANGELOG cut to `[0.1.0]`/`[0.1.1]`; README refreshed for the release. gate green **535 passed/1 skipped**.
5. ⬜ Run `/audit`
6. ⬜ Run `/indie-review`
7. ⬜ Fold / fix actionable findings
8. ⬜ Update CHANGELOG / ROADMAP / journal
9. ⬜ Commit, tag `FIBR-0054-complete`, push

*(Awaiting the user's live self-update test before `/close-phase`; the feature is
code-complete and released regardless. **Live update proven `0.1.2`→`0.1.3`
2026-07-11** — download + Ed25519-verify + swap + version-bump all worked (About
showed 0.1.3). **One field bug found + fixed:** the app closed but did NOT
auto-relaunch. Root cause — `AppImageInstaller.apply` re-exec'd in place via
`os.execv`, which can't replace a PyInstaller-onefile AppImage's busy FUSE mount
(the onefile bootloader treats the re-exec as a worker subprocess). Fixed to a
detached `subprocess.Popen` + `os._exit`, env `PYINSTALLER_RESET_ENVIRONMENT=1`
(PyInstaller 6.10+ official restart signal) + stale AppImage vars dropped;
spec D8/INV-6 field-corrected, tests reworked. **`v0.1.4` published 2026-07-11**
with the fix (`.sig` verified pre-publish). **Caveat: the fix only proves out on
the NEXT update after 0.1.4** — the *running* (old) version performs each
relaunch, so `0.1.3`→`0.1.4` still needs one manual reopen; `0.1.4`→(next feature
release) is the true auto-relaunch test, which then closes FIBR-0054.)*

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

### 2026-07-13 — FIBR-0013 CLOSED (P11 locked-PDF export) by /close-phase

Took **FIBR-0013** from its cleared spec to closed by TDD in one long delegated
session — **7 red→green slices** (`fa8bcc1`→`bff64c0`), gate green throughout,
final **779 passed / 1 skipped**, ruff/mypy/bandit clean. Delivered the whole P11
password-protected PDF export:

- **`services/pdf_export.py`** — `ExportOptions` + `PdfExportService`:
  `render_pdf_bytes` (HTML→`QTextDocument`→in-memory `QPdfWriter(QBuffer)`;
  offscreen `QChartView.grab()` chart rasters via `addResource`; optional in-memory
  `pikepdf` AES-256 `Encryption(user, owner, R=6)`; **no path** — INV-2 structural);
  `export()` atomic temp→`os.replace`, temp unlinked + re-raise on any failure
  (INV-2/INV-12). Header (title / generated / human period label / `{names}`
  collapse), opt-in Summary (combined + per-account lines, >1 account, name-sorted),
  Charts (Light/Dark), `(occurred_on, id)`-stable transaction list with an Account
  column only when >1 account and confirmed transfers `⇄ Transfer`-marked.
- **`ui/charts.py`** (D3) shared palette-free `ChartTheme` + builders (HomeView +
  export build the same charts, no on-screen change). **`ReportingService`** widened
  to `account_ids: frozenset|None` (D4). **`ui/export_dialog.py`** (D7) INV-14 gating
  + account master-toggle state machine + Light/Dark + Show toggle. **`main_window`**
  (D8/D9) File + toolbar entry (vault-gated by placement), save flow that keeps the
  dialog open on cancel/failure. **`_selftest.py`** `pdf_encrypt` bundle-travel leg
  (D12). **`ui/icons/export.svg`**.

**Close (steps 5–9):** `/audit` (`since-tag:FIBR-0012-complete`) **0 actionable in
FIBR-0013 code** (3 warnings were pre-existing FIBR-0054 auto-update test noise —
out of scope). `/indie-review` two independent cold lanes (data-security-money;
dialog-wiring-UI) → **no CRITICAL/HIGH/MEDIUM**; money math, transfer exclusion,
account-set semantics, atomic-write hygiene, INV-14 gating + state machine, and the
D3 refactor all verified correct. **3 LOW findings, all fixed inline** (`bff64c0`,
no FP## per the standing directive): empty-period Charts placeholder (INV-13 — code
now matches spec), currency-symbol escaping in amount cells (defence in depth vs the
header), narrowed `_on_export_requested`'s `except Exception` to the INV-12 set
(`VaultLockedError`, `OSError`, `pikepdf.PdfError`). ROADMAP FIBR-0013 → ✅; journal
`docs/journal/FIBR-0013.md`; CHANGELOG Added; tag `FIBR-0013-complete`.

**Next active item: FIBR-0123** (category-picker Income/Expenditure grouping — user
"one at a time" after FIBR-0013). Its own brainstorm → spec → `/cold-eyes` → TDD.
Then the locked order continues **FIBR-0014 → FIBR-0015** (Windows build). **FIBR-0054**
(auto-update) still open pending the user's live post-v0.1.8 auto-relaunch test.

### 2026-07-13 — FIBR-0013 spec CLEARED FOR CODE (P11 locked-PDF export, 7-loop cold-eyes) + FIBR-0123 filed

Delegated "what's next" session. **NEW ACTIVE ITEM: FIBR-0013** (P11 —
password-protected PDF report export). Brainstormed the full design with the user
(one question at a time); user decisions captured: **section-selectable**
(Summary/Charts/Transactions, each optional), **multi-account** (all or a chosen
subset — combined totals **+ a per-account summary line**), **OPTIONAL** AES-256
password (blank ⇒ unencrypted; **min 8 when set**; blank-wins), **Light/Dark**
theme (default Light), **File-menu + toolbar** entry, transaction list shows **all**
rows with confirmed transfers **`⇄ Transfer`-marked**. Wrote `docs/specs/FIBR-0013.md`
(INV-1..14, D1..13, deliverables, illustration mock-up, "to verify empirically"
block). Design realises `discovery.md` **SC5** — with SC5's password **relaxed
mandatory→optional** (user directive 2026-07-12) **back-propagated to discovery.md**.

**`/cold-eyes` converged — 7 cold loops × 3 lanes = 21 reviews** (project cap 7).
Polish convergence at loop 7 (zero CRITICAL/HIGH). HIGH trajectory
**H4→1→2→1→1→1→0** — each genuine: the miscited FIBR-0050→**FIBR-0009 INV-2**
disk-hygiene invariant; the **None-vs-empty account** contract (loop-3 fix was a
privacy footgun, reversed in loop 4 to empty⇒empty); the **atomic-write** mechanism
(temp → `os.replace`) backing INV-2/INV-12 + its failure-mode test; the dialog-mock
↔ PDF-header consistency; the **multi-account Account column** + `(occurred_on, id)`
stable sort. Loop log in the spec. 8 commits `a7d38b5`→`e41e77e`, pushed.

**Reporting-layer ripple flagged for TDD (D4):** `ReportingService.summary/
spending_by_category/monthly_trend` + `ReportingRepository.rows_in_range` widen
`account_id: int|None` → `account_ids: frozenset[int]|None` (`None`⇒all, empty⇒empty
short-circuit, non-empty⇒`IN`); Home wraps its single selection; dashboard suite's
`_donut_wedges`/`_UNCAT_COLOUR`/`_OTHER_COLOUR` imports move `ui.home`→`ui.charts`.

Also this session: **FIBR-0123 FILED** (planned, `features-accessibility`) — from
dogfooding, the category pickers flatten the Income/Expenditure tree so income vs
expenditure is invisible and two same-named categories (income "Lottery" +
user-added expenditure "Lottery") are indistinguishable. User: "no quick fixes —
finish FIBR-0013, then resolve the category issue, one at a time." So **FIBR-0123
is the next item after FIBR-0013** (its own brainstorm → spec → cold-eyes → TDD).

**Next: TDD** (`tests/features/pdf_export/` + the reporting/charts ripple) →
`/close-phase`. **FIBR-0054** (auto-update) still open pending the user's live
post-v0.1.8 auto-relaunch test.

### 2026-07-13 — v0.1.8 PUBLISHED + FIBR-0122 relaunch fix + Windows recon + order locked

- **FIBR-0122 SHIPPED** (dogfooding fix, user report "0.1.6→0.1.7 didn't auto-relaunch").
  Root-caused from `~/.local/share/finbreak/update-relaunch.log`: the `/bin/sh` relaunch
  waiter inherited the frozen app's `LD_LIBRARY_PATH` → `_MEI` bundle dir, so the SYSTEM
  `/bin/sh` loaded the app's bundled `libreadline.so.8` and died on a symbol lookup
  (`rl_completion_rewrite_hook`) **before** relaunching. Fix: `_relaunch_env` restores
  `LD_LIBRARY_PATH`/`LD_PRELOAD` from PyInstaller's `<VAR>_ORIG` (or drops them), so the
  waiter runs against system libs. TDD 2 unit tests. **Two-cycle caveat holds:** the fix
  is in v0.1.8 but the *running* old version does the relaunch, so v0.1.8→next still needs
  one manual reopen; the update after is the true test. See [[appimage-update-relaunch-caveat]].
- **v0.1.8 PUBLISHED** — bundles FIBR-0012 (dashboard) + FIBR-0120 (column reorder) +
  FIBR-0122 (relaunch fix). Bump via `.claude/bump.json` recipe (lockstep 0.1.7→0.1.8,
  CHANGELOG cut, README refreshed — dashboard + Transactions now in "what works today").
  Built via `build-release-appimage.sh` (clean-room-proved, signed), **`.sig` verified
  against the committed RELEASE_PUBLIC_KEY_B64** (hard gate), `gh release create v0.1.8`
  non-prerelease → `/releases/latest`. Tag `v0.1.8`. Commits through `a1640bc`, pushed.
- **Windows-build recon (for FIBR-0015)** — user asked how far off + offered a Windows test
  machine + drop share `/mnt/Games/Scripts/Apps/finbreak/`, and noted **Wine + MSVC are
  installed here**. Scan: 6/7 native deps ship Windows wheels; **`sqlcipher3-binary` (the
  SQLCipher vault engine) is Linux-only — THE blocker.** Path (annotated on FIBR-0015):
  build+test the `.exe` LOCALLY via Wine (MSVC-on-Wine to compile SQLCipher, PyInstaller
  freeze, Wine smoke-test) before the free GitHub windows-latest CI. Auto-update on Windows
  not built (manual-update .exe is fine for testing). **Order locked (user): FIBR-0013 →
  FIBR-0014 → FIBR-0015.**
- **Next:** FIBR-0013 (P11 password-protected PDF export; password **optional** per user;
  renders the FIBR-0012 charts into the locked PDF). User is clearing context before we start.

### 2026-07-13 — FIBR-0012 CLOSED (P10 reporting dashboard + Transactions tab) + FIBR-0120/0121

Took **FIBR-0012** from its cleared spec to closed by TDD in one long session (11
slices, each red→green). Delivered the whole P10 dashboard:

- **Reporting engine** — `services/reporting.py` (`ReportPrefs` + 5 `MODE_*`; pure
  `resolve_period`/`resolve_trend_months`, today-injected + **total** so a garbage or
  specific-missing-field mode falls back to previous-month, never raises;
  `ReportingService.summary`/`spending_by_category`/`monthly_trend`/`base_currency`/
  `transaction_count`). Confirmed transfers dropped from **every** figure (INV-1);
  all arithmetic on integer `amount_minor`, only display crosses to `Decimal` (INV-13);
  the `None`/Uncategorised donut bucket appended last so the sort never compares `None`.
  `repositories/reporting.py` `rows_in_range` (inclusive `BETWEEN` + null-or-eq account
  predicate). `models.py` `Summary`/`CategorySpend`/`MonthlyTotal`. `auth.report_prefs`/
  `set_report_prefs` over the v1 settings table (no schema change), defensively parsed.
- **UI** — `ui/_amount.py` (relocated `_format_amount` + colours, shared by tiles +
  table); `HomeView` = the **QtCharts dashboard** (selectors, tiles, ≤8-wedge donut +
  Other-collapse + empty placeholder D9, 12-month grouped-bar trend); `ui/transactions.py`
  `TransactionsView` (relocated table + set-category/learn chain + the four-filter bar
  D8); `ui/icons/transactions.svg`; `main_window.py` 7-tab wiring, count **live from
  Home's `ReportingService`** at every mutation site, manual-commit lands on
  Transactions; `_selftest.py` QtCharts (`QBarSet`) bundle-travel leg. **ADR-0008**
  (QtCharts, no new dep). Tests `tests/features/{reporting,dashboard,transactions_tab}/`;
  Home set-category tests relocated to the Transactions suite; dialog stubs hoisted to
  conftest; 6→7-tab + `_format_amount`-import + count-sourcing ripple across 8 suites.
- **Close (steps 5–9):** `/audit` **0 actionable / 0 raw**; `/indie-review` 2 cold lanes
  → **3 verified findings, all fixed inline** (no FP## per the standing directive):
  (1) `report_prefs` bounded month but not year — a stored year outside 1–9999 would
  make `resolve_period`'s `date(...)` raise; now downgrades to previous-month (INV-2);
  (2) the Transactions + Statements tables (both 5-col, both unnamed) shared the empty
  `"columns/"` `remember_columns` key and cross-corrupted widths + the new drag order —
  gave each data table a distinct objectName; (3) `HomeView._on_period_changed` caught a
  bare `Exception` and guarded only the write → now `VaultLockedError`-specific around
  the full persist+refresh in both slots (coding.md § 2). +2 regression tests. Gate green
  **712/1**, mypy 0. Allowlist unchanged. ROADMAP FIBR-0012 → ✅; journal
  `docs/journal/FIBR-0012.md`; tag `FIBR-0012-complete`.

Also this session (folded into the same push batch):
- **FIBR-0120 SHIPPED** — drag-to-reorder table columns, order persisted across
  sessions, on every data table. A user request; done by enabling `setSectionsMovable`
  in the **shared** `_table_state.remember_columns` seam (FIBR-0117 already saved/restored
  full header state incl. order), so it lit up across Transactions/Statements/Rules/
  Transfers at once — a reuse win, not per-table code.
- **FIBR-0121 FILED** (planned) — loan-account sign display: show debt-reducing amounts
  (loan payments) as positive/green and interest/fees as negative/red on loan-type
  accounts. User-approved **display-only** (storage stays canonical per FIBR-0007, so the
  money/transfer/dashboard machinery is undisturbed). Its own spec + 7-loop cold-eyes
  later; **open question to verify** in that spec: whether transfers INTO a loan are
  currently detected (the loan-payment leg may share a sign with its current-account leg,
  which opposite-sign matching would miss) — split out as a bug-fix if a real gap exists.

**Next queue:** P11/**FIBR-0013** (password-protected PDF export — user directive: the
password is **optional**). **FIBR-0054** (auto-update) still open, awaiting the user's
live 0.1.6→0.1.7 auto-relaunch test.

### 2026-07-12 — FIBR-0012 spec CLEARED (P10 dashboard, 6-loop cold-eyes) + FIBR-0119 shipped + release-README

Long delegated session ("what's next"). Outcomes:

- **NEW ACTIVE ITEM: FIBR-0012** (P10 reporting dashboard + Transactions tab). Brainstormed +
  user-approved the design: period model **default = previous month**, persisted, with
  current-month / specific-month / year-to-date / specific-year options; **QtCharts**;
  **transfers never counted** as income/expenditure; a new **Transactions tab** with
  search + date-range + account + category filters (all combinable), absorbing **FIBR-0109**
  (its amount-range filter deferred). Wrote **ADR-0008** (QtCharts — bundled with PySide6, no
  new dep, shares the `QPainter`/`QPdfWriter` engine for the future FIBR-0013 PDF export) +
  `docs/specs/FIBR-0012.md` (14 INV, 12 D, 12 deliverables; no schema change — `ReportPrefs`
  rides the v1 `settings` table). **`/cold-eyes` ran 6 cold loops × 3 lanes (18 reviews) →
  CONVERGED (polish).** The accuracy-vs-code lane returned **zero findings every loop**; loops
  2–6 resolved implementability / cross-doc findings, most of them ripples of prior-loop fixes
  (donut ≤8-wedge cap + `(magnitude, category_id asc)` sort determinism; count-sourcing settled
  as **live from Home's `ReportingService.transaction_count()`** at every mutation site; the
  Other-vs-Uncategorised representation as a UI-render construct; a `None`-safe sort key + a
  `tr()` label seam). Spec **CLEARED FOR CODE**; commits `778e361`→`a3db902`, pushed. **Next:
  TDD** (`tests/features/{reporting,transactions_tab,dashboard}/` + settings/self-test legs) →
  `/close-phase`.
- **FIBR-0119 SHIPPED** (dogfooding fix, user-reported mid-session) — the Home Loan (Family B)
  PDF import folded a page-break footer/letterhead block ("Insurance Premium 0453155796 Standard
  Bank Centre … Debit Credit Balance Date Date Fee") into the preceding transaction's
  description. Root-caused against the real 2026-02-28 statement (real file/password **never
  committed**): `_fold` appends every non-row in-region line to the preceding txn, and a
  mid-region page footer + repeated column header have no date+amount. Fix: a shared
  `_is_boilerplate()` (bare account/reference number; SB registered-office markers; a
  repeated column-header line) that `_fold` drops — generalising the Family-C `_is_cc_skip_line`
  rule. TDD synthetic `_parse_family_b` test; re-validated both real Home Loan statements (27 /
  54 drafts, clean descriptions incl. the formerly-polluted row) + the full A/B/C/D suite. Gate
  green **656/1**. **The "27 new · 27 duplicate" the user saw is CORRECT** — the 2026-02 statement
  restarts at 2025-03-01 (54 drafts = 27 overlapping the first import, deduped, + 27 new). Commit
  `2f9fe63`, pushed. ROADMAP FIBR-0119 ✅; CHANGELOG Fixed.
- **Release recipe** (user directive) — `.claude/bump.json` now bumps README's "Current version"
  line mechanically (drift-gated in `post_check`) + a new todo prompts a **layman-friendly**
  feature / what's-new README refresh at each bump. Commit `6e62f4c`, pushed.
- **Also:** captured the user's "PDF export password is **optional**" preference on FIBR-0013;
  Ants-MCP feedback re-verified vs build `ada5ebb3` (session_orient's embedded `codebase_index`
  now ships `source_files[]` — substantially addresses ANTS-3468/3503).

**FIBR-0054 still awaits the user's live 0.1.6→0.1.7 auto-relaunch test to close** (steps 5–9).

### 2026-07-12 — v0.1.7 PUBLISHED (transfers + 3 UI polish items + 2 dogfooding fixes)

Cut **v0.1.7** bundling six items: **FIBR-0011** (transfer detection), **FIBR-0112**
(credit-card continuation-page import fix), **FIBR-0114** (auto-lock inactivity
timer), **FIBR-0116** (coloured hover-brightening theme-aware toolbar icons),
**FIBR-0117** (table click-sort + remembered column widths & sort order), **FIBR-0118**
(rounded/transparent app-icon corners). The three UI polish items were built
test-first this session at the user's "build all 3, then release" direction:
- **FIBR-0118** — make-icons.sh rounds the master (18% radius) once + derives every
  size; refreshed the dogfood install's hicolor icons so the launcher shows it now.
- **FIBR-0117** — new ui/_table_state.py (SortableItem + remember_columns + a row-tag
  scheme so an action targets the correct row after a re-sort — the money-critical
  guard). Applied to Statements/Transfers/Home (sort+widths+persisted sort), Rules
  (widths only, stays priority-ordered per user choice).
- **FIBR-0116** — toolbar_icon() recolours each SVG: muted at rest (QIcon Normal),
  vibrant on hover (QIcon Active, Qt's built-in swap), theme-aware via the palette.

Release: bumped 0.1.6→0.1.7 (lockstep across __init__/pyproject/smoke/CHANGELOG;
fixed 6 double-bold CHANGELOG summaries), built the signed AppImage via
build-release-appimage.sh (clean-room-proved — ran with no Python), **verified the
.sig against the committed RELEASE_PUBLIC_KEY_B64**, `gh release create v0.1.7`
(non-prerelease, both assets, /releases/latest → v0.1.7). Gate green **655 passed/1
skipped** throughout, mypy 0. Commits through `5557ebb`, all pushed; tag `v0.1.7`.

**FIBR-0054 close opportunity:** the user's installed **v0.1.6 → v0.1.7** update is
the true auto-relaunch test (0.1.6 carries the relaunch fix; per the two-cycle trap
it only *runs* on 0.1.6→next). If that live update download→verify→swap→**auto-relaunch**
works, FIBR-0054 can finally `/close-phase` (steps 5–9). Awaiting the user's live test.

### 2026-07-12 — FIBR-0011 CLOSED (P09 transfer detection) + 3 more roadmap asks

Took **FIBR-0011** from converged spec to closed by TDD in one session. Schema
**v7→v8** (`transfer_pairs` decision table, dual `ON DELETE CASCADE`, canonical
`UNIQUE`); `TransferRepository` (the D3 candidate self-join — equal-magnitude /
opposite-sign / different-account / ±`TRANSFER_WINDOW_DAYS=3`); `TransferDetectionService`
(candidates / confirm / reject / unlink / confirmed_transfers /
`confirmed_transfer_txn_ids` [the FIBR-0012 exclusion primitive] / `confirm_all`
greedy+consumed-set); the 6th **Transfers** tab (suggested+confirmed tables,
Confirm/Reject/Confirm all/Unlink, `VaultLockedError`-guarded, no modals). Tests
`tests/features/transfers/` one case per INV-1..12 + edges (window 0/3/4,
off-by-one, two-debits, same-account, Cartesian 2×2→2, empty-vault); schema-version
"lands-at-latest" ripple 7→8 across 8 suites (+ version-named test renames),
tab-count 5→6 + toolbar order in the statements suite, `build_v7_vault` conftest
helper. **Close:** `/audit` full-tree — 0 in the new code (3 pre-existing FIBR-0054
updater semgrep warnings out of scope); `/indie-review` 2 cold lanes — **data/logic
CLEAN**, UI/shell **2 LOW** (auto-lock test parametrized over all 4 slots; stale
five-tab docstrings) **folded inline**. Gate green **645 passed/1 skipped**, mypy 0.
ROADMAP FIBR-0011 → ✅; CHANGELOG Added; journal `docs/journal/FIBR-0011.md`; tag
`FIBR-0011-complete`. **Unblocks FIBR-0012** (the Home spending dashboard — the
exclusion primitive is now in place). **FIBR-0112/0114 (dogfooding fixes) + FIBR-0011
are all on main but UNRELEASED** — the user wants FIBR-0011 finished first, then a
**v0.1.7** release bundling them.

Also roadmapped mid-session (user requests, several tagged for the v0.1.7 batch):
**FIBR-0116** (toolbar glyphs: muted theme-aware colour → vibrant on hover),
**FIBR-0117** (data tables: remember column widths + click-header sort, toggle order),
**FIBR-0118** (app-icon transparent/rounded corners). Earlier this session:
FIBR-0109/0110/0111/0113/0115 (see prior entry).

### 2026-07-12 — FIBR-0011 spec CONVERGED + two dogfooding fixes (FIBR-0112/0114)

Long multi-thread session (user delegated "what's next", then dogfingered several
bugs mid-turn). Outcomes:

- **NEW ACTIVE ITEM: FIBR-0011** (P09 transfer detection). Brainstormed + user-approved
  the design (±3-day match window, dedicated Transfers tab, single `transfer_pairs`
  decision table). Wrote `docs/specs/FIBR-0011.md`; `/cold-eyes` ran **4 cold loops ×
  3 lanes (12 reviews)** → **CONVERGED (polish) at loop 4**. Trajectory C0 / H2→0→0→1 /
  M6→3→5→0; loop-4 accuracy+implementability lanes clean, the lone HIGH a self-inflicted
  loop-3 citation typo (FIBR-0107→FIBR-0086 v8-collision note). Notable catches: the
  Context "no transaction-edit surface" claim was false (`reassign_account` edits a
  matching field — documented the benign stale-pair case); a Deliverable-8 ripple that
  cited non-existent app_shell assertions; the `confirm_all` contract; the
  window-constant layer. Spec **CLEARED FOR CODE**. **Next: TDD** (`tests/features/transfers/`)
  → `/close-phase`. Commits `0d20aa5`→`5a2575c`.
- **FIBR-0112 SHIPPED** (code) — credit-card import refused a real SBSA statement
  ("didn't add up"). Root cause: a 3-page statement whose final page carries the
  transaction table with NO repeated "Date Description Amount" column header → its rows
  were dropped → checksum failed. Fix: `_table_region` falls back to the first real
  transaction row on a header-less Family-C page. TDD (2 `_table_region` unit tests);
  **validated all 12 real statements parse + reconcile**. Real file/password never
  committed. Commit `f6426a1`.
- **FIBR-0114 SHIPPED** (code) — auto-lock counted from unlock, not activity. Added
  `AuthService.notify_activity()` (restarts the running timer) + a MainWindow app-level
  event filter on input events → inactivity timer. TDD (2 service + 1 shell test).
  Commit `b1703d4`.
- **Roadmapped (user requests):** FIBR-0109 (Transactions tab + filters), FIBR-0110
  (typed-or-picker dates), FIBR-0111 (currency column), FIBR-0113 (Accounts columns),
  FIBR-0115 ("Continued on next page" description strip — cosmetic).
- **Ants-MCP feedback** re-verified on build 251e1f3d (ANTS-3481 confirmed shipped;
  3468 still open; 3480 deferred).
- Gate green throughout (final **607 passed / 1 skipped**). **FIBR-0112/0114 are on main
  but UNRELEASED** — user chose not to cut a release this session.

### 2026-07-11 — Live self-update proven (0.1.2→0.1.3); relaunch bug fixed → v0.1.4

The user ran the live self-update on their installed AppImage: **download →
Ed25519-verify → swap → version-bump all worked** (About showed 0.1.3) — the whole
FIBR-0054 updater proven end-to-end in the field. **One bug:** the app closed but
didn't auto-relaunch (manual reopen needed).

**Researched (user asked) + root-caused.** In-place `os.execv($APPIMAGE)` can't
relaunch a PyInstaller-onefile AppImage from within itself: the running image's FUSE
mount is busy, and — per PyInstaller 6.10+ docs — the onefile bootloader treats an
in-place re-exec as a *worker subprocess* (reusing the now-deleted `_MEI`
extraction), so it dies. **Fix (official mechanism):** relaunch as a fresh DETACHED
process — `subprocess.Popen([$APPIMAGE], start_new_session=True, stdio=DEVNULL,
env=_relaunch_env())` then `os._exit(0)`. `_relaunch_env()` sets
`PYINSTALLER_RESET_ENVIRONMENT=1` (the supported "restart the frozen app" signal so
the new onefile re-extracts) and drops the stale AppImage `APPDIR`/`APPIMAGE`/`ARGV0`.
Key-wipe still runs after the swap + before the spawn (INV-6). Reworked the INV-5/6
installer tests to the new contract (Popen + `os._exit` monkeypatched) + a leg
asserting detached/new-session/reset-env; field-corrected FIBR-0054 spec **D8 +
INV-6 + deliverable** (execv → detached relaunch) and `auto_update` spec.md; CHANGELOG
Fixed. Gate green 577/1, bandit/mypy/ruff clean. Commit `91f21d7`.

**Published `v0.1.4`** (bump `d12b8a3`; built + clean-room-proved + signed;
`.sig` verified vs the committed public key pre-publish; non-prerelease, latest).
**Key operational caveat (see status header):** the *running* version does each
relaunch, so `0.1.3`→`0.1.4` still needs one manual reopen — `0.1.4`→(next release)
is the real auto-relaunch test. User chose to verify on the next natural feature
release rather than cut a throwaway 0.1.5. That test, once green, closes FIBR-0054.

### 2026-07-11 — FIBR-0083 SHIPPED (timezone + date/time format) + v0.1.3 released

Built **FIBR-0083** (user-configurable timezone + date/time display format) end-to-end
**test-first**, then cut **v0.1.3** — the release the user's installed build
self-updates to (the culminating step of the FIBR-0054 dogfood plan: build an extra
feature → publish → live update test → close FIBR-0054).

Spec was `/cold-eyes`-converged at loop 8 (project `--max-loops 7` + 1 user-chosen
confirming loop) the prior session. TDD in **4 red→green slices**, each committed +
pushed gate-green:
- **Slice 1** — `src/finbreak/datetime_format.py` (pure, Qt-core only): `format_date`
  (reformat, no tz shift, INV-2) / `format_timestamp` (UTC→zone then format the date +
  time halves independently, INV-3/D5) / `DATE_PRESETS`+`TIME_PRESETS` / the `"system"`
  sentinel + INV-6 fallbacks. 16 hermetic tests (`"system"` legs by delegation to
  `QLocale.system()`/`systemTimeZoneId()` so no locale/CI flake; token legs fixed — Qt
  renders MMM/AP names in English regardless of locale, verified).
- **Slice 2** — `DateTimePrefs` (frozen dataclass) + `AuthService.datetime_prefs()`/
  `set_datetime_prefs()` over the vault `settings` table (no schema change), mirroring
  auto-lock. 5 round-trip tests in the settings suite.
- **Slice 3** — the Settings + first-run combos, built by one shared
  `ui/_datetime_prefs.py` (`populate_datetime_combos` + `read_datetime_prefs` with the
  editable-timezone free-text recovery, D3/D4). Settings persists under the same
  `VaultLockedError` guard as auto-lock; first-run persists at its post-create
  `_on_derived` site (D6, INV-8 via a synchronous `DeriveWorker` stand-in). New
  `tests/features/first_run/` + 5 settings-combo legs; narrowed one FIBR-0055
  no-QLineEdit assertion (the editable tz combo legitimately adds a search box).
- **Slice 4** — display wiring: `StatementsWidget` Period/Imported + `HomeView` Date
  render through the formatter under a held `DateTimePrefs` (param before `parent`,
  defaulted all-`"system"` so ~12 direct-construction tests are untouched); shell reads
  prefs once post-unlock, passes to both tabs, and pushes new prefs live on Settings
  Save (D7). New `tests/features/datetime_display/` (D5/D6/D7 + INV-1 no-mutation).
  Docs (Deliverable 9): ROADMAP **FIBR-0048 + FIBR-0083 → ✅** (0048 subsumed);
  FIBR-0014 date-format TODO comments repointed here; CHANGELOG Added; spec → SHIPPED.

Full gate green throughout (final **576 passed / 1 skipped**), mypy 0 across 61 files,
ruff/format clean. Then **v0.1.3**: bumped version (pyproject/`__version__`/smoke/README),
rolled CHANGELOG `[Unreleased]`→`[0.1.3]`, built + clean-room-proved + signed the
AppImage via `build-release-appimage.sh`, **verified the `.sig` against the committed
`RELEASE_PUBLIC_KEY_B64`** before publishing, `gh release create v0.1.3` (non-prerelease,
both assets — `/releases/latest` resolves to it). Commits through `2af2812`, pushed.

**Next: the user runs the live self-update `0.1.2`→`0.1.3` in their installed AppImage;
on success, `/close-phase` FIBR-0054** (steps 5–9: `/audit` + `/indie-review` → fold →
tag `FIBR-0054-complete`).

### 2026-07-10 — FIBR-0054 opened: brainstormed + spec drafted + `/cold-eyes` CONVERGED (5 loops)

Picked up **FIBR-0054** (in-app auto-update), the last near-term user ask. Ran the
**brainstorming** skill (design-approval gate). Surfaced the load-bearing blocker
first (Karpathy — think before coding): auto-update needs a working release pipeline
(published, versioned, **signed** artifacts) and **none existed** — `__version__` was
`0.0.0`, `gh release list` empty, FIBR-0015/0016 still 📋. Presented the sequencing
fork; the user chose **full in-app update, Linux/AppImage first** (then, mid-turn,
"Windows too, but start with Linux" → designed a platform `Installer` **seam**,
Windows not built). Design decided with the user: **Ed25519** signature gate (verified
via the already-bundled `cryptography` — no new runtime dep/tool); **offer-after-unlock**
prompt (resolving a modal-collision with the unlock dialog — the user's call);
simple full-file AppImage swap (`$APPIMAGE` → download → verify → `os.replace` →
key-wipe → `os.execv`), not zsync.

Wrote `docs/specs/FIBR-0054.md` (two phases: real signed release infra → the updater;
15 INVs, 15 design decisions, 21 deliverables). **The central tension:** the app's
`security-model.md` **INV-8 forbids all network code**, enforced by a real
`test_INV8_no_network_imports_under_src` AST scan — so the updater is the deliberate,
**opt-in, off-by-default** breach, confined to one allowlisted `services/update_fetch.py`.

**`/cold-eyes`: 5 cold loops × 3 lanes** (accuracy vs source · implementability ·
cross-doc), each briefed cold. Severity trajectory **C1→0→0→0→0, H4→3→3→2→0,
M7→6→4→5→0**; converged at loop 5 (polish — both remaining lanes independently judged
the spec implementable end-to-end + the no-network reconciliation complete +
internally consistent). Notable: loop 1 fixed a dead ADR link + an incomplete INV-8
amendment plan (the no-network rule turned out to be stated in **~10 docs** — all
reconciled: live docs amended, ADR-0003 superseded-in-place, discovery/closed-specs/
CHANGELOG left historical); loop 2 added **D15 offer-after-unlock** (the modal-collision
fix, user-decided) and the wider no-network sweep; loops 3–4 were mostly **self-inflicted
ripples of the D15 + key-wipe additions** (a `show_modal` contradiction, the
`_pending_update` lifecycle, the download-worker contract, the `apply()` signature) —
exactly what the cold loop is for. Accuracy lane INFO-only from loop 2 on. Signed off
(global rule §14 + the standing spec-is-my-domain rule). 6 commits `102a95e`→`90e72e4`.

**Next: step 3 — TDD.** Phase 2 (the updater) is buildable now against mocks + the
all-zero placeholder public key. **Phase 1 blocks on one user action:** generate the
Ed25519 signing key (a one-time `scripts/gen-signing-key.py` run — the private key
never enters the repo or my context).

### 2026-07-10 — FIBR-0067 CLOSED (real statements arrived) + FIBR-0082 filed (screenshots)

The user supplied the **six real Standard Bank statements** (one per family) + the
password, unblocking **FIBR-0067** (the last tech-debt item). Reproduced first: all
six PASS on the current regex and print **zero** ungrouped 4+-digit amounts (SB always
groups thousands). Widened `_MONEY` to accept an ungrouped run
(`\d{4,}[.,]\d{2}`) with a `(?![.,]?\d)` tail guard that rejects the dotted-date false
positive the earlier defer warned about. **Re-validated in a throwaway scratchpad
harness against all six — identical txn counts (53/82/27/20/30/3), zero regression.**
Added a synthetic parametrized `_MONEY` unit test. **Real statements + password NEVER
committed** (scratchpad deleted; committed test is synthetic strings only,
testing.md §6). Gate green 460 passed/1 skipped. Commit `d97e167`. **The
`warnings-tech-debt` section is now fully empty — 16/16 done.**

Also filed **FIBR-0082** (user request): generate app screenshots from synthetic dummy
data for the GitHub README + antsprojectshub.co.za (packaging-2 / marketing; a scripted
demo-vault seeder + capture flow; synthetic data only; not blocked, but the dashboard
FIBR-0012 will make the headline shot).

### 2026-07-10 — Tech-debt backlog CLEARED (15 audit-fix items, out-of-band)

User directive: **"ensure all outstanding fixes are in first"** (before any new
feature). Worked the entire `warnings-tech-debt` section (deferred from the
2026-07-10 audit sweep + a test-audit) to empty, save the one real-statements-blocked
item. **15 items across ~16 gate-green commits** (each `/audit`-clean, mypy 0, pushed):

- **Small debt:** FIBR-0080 (settings reads → `SettingsRepository.get` seam), FIBR-0081
  (`_on_move` Literal typing + FIBR-0007 INV-7 doc fix; `_selected_row` dedup left per
  Rule-of-Three), FIBR-0043 (closed — superseded by FIBR-0058).
- **DB/crypto safety:** FIBR-0077 (pin `PRAGMA cipher_use_hmac = ON` — a FIBR-0004 D4
  revisit), FIBR-0076 (`PRAGMA busy_timeout = 5000`).
- **Dedup refactors:** FIBR-0066 (`owned_transaction()` ctx-mgr in new `db.py`, 13
  sites), FIBR-0068 (`select_combo_data()` UI helper, 6 sites — kept **distinct** from
  the wizard's intentional unguarded `_set_combo`), FIBR-0069 (`_signed_balance()` SB
  helper, 7 sites).
- **Importer/UX/security:** FIBR-0078 (SB row-cap **before** the per-family parse —
  bounds computation), FIBR-0079 (RuleEditDialog zero-leaf gate, TDD), FIBR-0075 (PDF
  decompression-bomb residual assessed + **documented as accepted** in
  security-model.md — user deferred the call; a robust cross-platform fix is
  disproportionate for a local, user-chooses-the-file app).
- **Decisions (surfaced to user):** FIBR-0070 (KEEP the unwired `ImportProfileRepository`
  read API + document intent, per the user's "if we'll use it later" rule).
- **Test-audit:** FIBR-0062 (hoist `paths`/`_PW`/`raising_conn`/`StandInVault`/`_acct`/
  `_pump_deferred_delete` to conftest), FIBR-0063 (parametrize the 2 bundled-assert/loop
  tests + split the INV5a plaintext-leak security check into its own test), FIBR-0064
  (regression tests for 9 untested error branches — which **revealed + fixed a real UX
  bug**: a corrupt PDF showed the raw pikepdf error instead of the friendly message;
  added `_show_pdf_read_error()`).

Gate green **452 passed / 1 skipped**, mypy 0, ruff clean. Ants-MCP feedback appended
(positive 15-item-sweep datapoint + ANTS-3468 re-verification + 2 minor DX notes).
**Only FIBR-0067 remains** in the section — blocked on real anonymised sample statements
(annotated as such). Active item stays **FIBR-0054** (auto-update). No `-complete` tags
(debt items, not implementation phases).

### 2026-07-10 — Full-codebase /audit + /indie-review sweep (user-requested, out-of-band)

Ran a whole-project audit at the user's request (not a phase close). **Static
layer fully clean**: `audit_run` (ruff/bandit/semgrep/gitleaks/shellcheck, full
tree) 0; deps-installed mypy 0 (65 files); pip-audit 0. `/indie-review` fanned
out **8 cold lanes** (crypto-vault · auth · repositories · CSV-import ·
statement-importers · core-services · UI-shell · UI-dialogs), Sonnet reviewers,
all severities. Corroborations (≥2 lanes): move_rule non-atomic, `_stored_pw`
vs INV-11 docstring, txn boilerplate ×6, RulesWidget lock guard, auto-lock
during nested `exec()`.

**Every actionable finding verified against source before any fix** (two
reproduced empirically). **Folded inline with regression tests (4 commits, gate
green 427 passed/1 skipped):**
- *crypto/vault:* H-A `Vault.create()` conn-leak on post-`_conn` failure →
  close-and-reset like `open()`; M-crypto2 app-data dir → 0o700; M-crypto3
  sidecar `.tmp` → `O_NOFOLLOW`.
- *import pipeline:* H-C OFX **investment** statement `AttributeError` (repro'd)
  → filter + friendly `ValueError`; H-D `pdfplumber` `PdfminerException`
  uncaught → boundary catch in both PDF readers; H-F `read_file*` `OSError` →
  `ValueError`; H-G CSV size cap (closes **FIBR-0041**); M-csv-cols column
  distinctness.
- *services:* M-auth2 `complete_first_run` key-wipe on the guard path; M-core1
  `set_manual_category` leaf guard (INV-9); M-C1 `move_rule` atomic swap.
- *UI/docs:* H-E accounts delete confirmation; M-auth1 distinct `KdfPolicyError`
  message; M-C4 `RulesWidget` lock guards; M-dlg3 accessible names; M-C2
  password-dialog docstring; M-data2 `design.md` phantom `secrets` table.

**H-B (reproduced HIGH) deliberately NOT patched inline** — auto-lock firing
during a content-widget `exec()` dialog destroys the dialog's parent chain
mid-nested-loop → `RuntimeError` the `VaultLockedError` guards miss (empirical
repro in scratchpad). The correct fix is architectural (non-blocking dialogs, or
a modal-registry with deferred teardown that keeps the key-wipe-on-lock
invariant) and needs its own spec+cold-eyes+TDD cycle. Filed as **FIBR-0065**
(top priority, ahead of FIBR-0054) with the repro + proposed approach.

**Deferred → ROADMAP (FIBR-0065–0074):** H-B crash, txn-boilerplate refactor,
`_MONEY` ungrouped-amount fix (deferred: validated parser, no real-statement
corpus in-session; naive fix risks a dotted-date false positive), `_set_combo` +
balance-parse dedup, unwired `list_all()` decision, DB indexes, navigate-away-mid-
import UX, a11y mnemonics sweep, and (user ask) dedicated ABSA/Nedbank/FNB PDF
readers (**FIBR-0074** — blocked on real anonymised sample statements; the
generic extractor + CSV/OFX already cover these banks). One false positive logged
(`CategoryRepository.delete()` "dead code" — actually tested + intentional).
CHANGELOG updated; Ants-MCP feedback appended (new `indie_review_orchestrate`
no-lanes finding + a re-verification datapoint pinned to the **pre-relaunch**
build edbc3163). Active item stays **FIBR-0054** (auto-update) — though FIBR-0065
should arguably go first.

**Loop 2 (cold confirming pass — capped here per the user; `/indie-review` will
run again later).** Re-dispatched the 7 changed lanes with **no fix-briefing**:
**every Loop-1 fix held** (none re-raised). The pass found a fresh batch — mostly
the same themes one layer deeper — folded with tests (gate green **434 passed/1
skipped**): statement H1 (Afrikaans/garbled month `KeyError`, reproduced),
`_read_capped` bounded read (endless-symlink/`/dev/zero` defeats the loop-1 cap),
crypto M1 (pre-commit `create()` block still leaked a conn — completes H-A),
crypto M3 (`mkdir` mode), **data H-1** (deleting an account with a quiet-month
statement crashed on the FK — now blocked, wiring in the dead `list_for_account`),
PasswordDialog leak + `PdfError` catch, and a **`VaultLockedError`-guard
consistency cluster** (settings/manual-entry `exec`-less crashes + accounts/
categories add/edit raw-message). Deferred → **FIBR-0075–0081** (PDF
decompression-bomb bound [security-model gap], single-instance/`busy_timeout`,
explicit `cipher_use_hmac` PRAGMA [vs FIBR-0004 D4], SB pre-parse cap [vs
FIBR-0050], zero-leaf `RuleEditDialog` gate, settings-read reuse, small type/doc
debt); FIBR-0070 annotated to cover the sibling `get()` zombie. CHANGELOG updated.
The deferred H-B (**FIBR-0065**) was re-raised by two lanes — confirming it's real
and correctly parked for its own fix-cycle.

### 2026-07-10 — FIBR-0010 CLOSED (P08 rules engine + manual override + learning)

Built the P08 rules engine **test-first** against the cold-eyes-converged spec.
Wrote `tests/features/categorisation/` (INV-1..16 + edges) red, then the 14
deliverables to green: `text.normalise_text` (the shared matcher/dedup primitive,
extracted so `ImportService._normalise` delegates to it); the schema **v6→v7**
migration (two nullable `transactions` columns + `categorization_rules`); the pure
`categorize` + commit-free `recategorize_auto_rows` engine (the golden rule — every
auto row recomputed, every manual row frozen, via the NULL-safe `category_source IS
NULL OR category_source <> 'manual'` predicate); `CategorizationService`; the
import-time hook; the atomic delete-category cascade + `delete_blast_radius`; the
4-tuple `list_transactions`; and the UI (Home Category column + context set +
learning offer, a Rules tab, `CategoryPickerDialog`, the net-new blast-radius
confirm, the 5th tab). Ripple: schema `==6`→`==7` across 6 suites, the
`list_transactions` unpacks, HomeView's 2-arg construction, the 5-tab/toolbar
shell-shape assertions, the category delete-confirm patch.

**Two implementation refinements surfaced (never silently drifted) + spec-annotated:**
the cascade deletes the category **in-line** commit-free because
`CategoryRepository.delete` commits (which would end the service-owned transaction
early, breaking INV-7 atomicity — the INV-7 rollback test pins this); and the
category selectors are **flat combos** (grouping-by-root deferred as polish).

**Close (steps 5–9):** `/audit` **0 actionable** (ruff/bandit/semgrep 0; the mypy
`annotation-unchecked` notes are informational on pre-existing untyped test helpers;
gated `mypy src tests` clean). `/indie-review` **3 cold lanes** (data/core · UI ·
tests) + a **confirming pass**. Data/core CLEAN. Fixed inline (standing no-FP##
directive): **1 HIGH** — an idle auto-lock firing while the learning-offer dialog
was open crashed the slot, because the trailing `refresh()` (after the loop-pumping
`exec()`) read a locked vault uncaught; the picker-only path returned before
refresh but the learning path didn't. Set + learn + refresh now share one
`VaultLockedError` guard; a regression test patches `list_transactions` (what
`refresh()` calls) to raise, so the guarded path is genuinely exercised and would
fail against the old code. Plus **3 MEDIUM** (the spec-mandated `_v6`→`_v7`
test-name renames I'd skipped; the untested INV-3 re-import path; a weak INV-8
both-counts assertion) and **1 LOW** (two identical `leaf_categories` impls →
centralized on `CategorizationService.leaf_categories()`, ui helper removed) and
**1 INFO** (stale four-tab docstrings). Confirming re-review **CLEAN** (it noted the
HIGH fix also cured a latent old-code variant). Allowlist unchanged (0 FP).

Gate green **411 passed / 1 skipped**, mypy 0. ROADMAP **FIBR-0010 → ✅**; also
**FIBR-0035 → ✅** — its learn-from-corrections ask is fully delivered here
(create-a-rule = INV-5/D11; the update-variant subsumed by D6's top-priority
insert). Journal `docs/journal/FIBR-0010.md`; tag `FIBR-0010-complete`. Commits
`9db5d99` (TDD) → `aff141a` (fold) → close. **This created the transaction→category
link P10/FIBR-0012 (dashboard) consumes.** Next active item **FIBR-0054**
(in-app auto-update) — the last near-term user ask.

### 2026-07-09 — FIBR-0010 (P08) opened: brainstormed + spec drafted + `/cold-eyes` CONVERGED (6 loops)

Picked up P08 (rules engine + manual override) — the standing active item — after
the user delegated "what's next". Ran the **brainstorming** skill (design-approval
gate): the user chose **text-substring rules only** (per-account scope reserved as a
future seam), **learn-from-corrections** = *offer to create a rule* (suggest-then-
confirm), rules run **on import + an explicit "Apply rules now"**, and — from two
sharp follow-up questions — a **delete-category cascade** that un-pins + re-files the
affected transactions (and deletes the rules that targeted the category), with a
**blast-radius confirmation**. Design approved section-by-section.

Verified every seam against source before drafting (§13): `Transaction` is 6 fields
(no category link today), `LATEST_SCHEMA_VERSION == 6`, the exact `list_all` SELECT,
`PRAGMA foreign_keys = ON` (vault.py:142), `delete_category`'s guards, the 4-tab
workspace, `HomeView`'s table, `commit_import`'s owned transaction, `_normalise`.
Wrote `docs/specs/FIBR-0010.md` — schema **v6→v7** (`transactions.category_id` +
`category_source`; new `categorization_rules` table); the **golden rule** (a row is
manual-frozen or auto-derived; the engine never touches a manual row); first-match-
by-priority; new-rules-win; the learning offer; the atomic delete cascade; 16 INVs,
14 deliverables, the full test-ripple. **The learning half pulls FIBR-0035 forward**
(reconciled — both bullets annotated).

**`/cold-eyes`: 6 cold loops × 3 lanes = 18 reviews** (accuracy-vs-code ·
implementability · cross-doc), each briefed cold. Trajectory C0 throughout;
H3→3→0→1→0→0, M6→4→2→0→1→1. Design **stable + correct from loop 2**; loops 3–6
refined accuracy + cross-doc + implementation-detail precision. Notable: loop 1
fixed standards mis-citations (reuse §1.3 not §3; atomicity → design.md not coding.md
§2) + pinned the **NULL-safe** auto-row predicate (`IS NULL OR <> 'manual'`, with a
"what NOT to do" 3-valued-logic warning — the highest-blast-radius latent trap);
loop 2 reconciled the design.md table name + the FIBR-0035 overlap; loop 4 made the
`list_transactions` test-ripple **self-verifying** via grep (it kept being enumerated
incompletely); loop 5 fixed a **layering** violation (INV-8 read repos from the UI →
routed through a new `CategoryService.delete_blast_radius`); loop 6 closed an
empty-pattern error path. **Lane A clean loops 5–6; Lane C INFO-only loops 5–6.**
Signed off (global CLAUDE.md rule §14 + the standing spec-is-my-domain rule). ROADMAP
FIBR-0010 → 🚧. Next: **step 3 — TDD** (`tests/features/categorisation/`).

### 2026-07-09 — FIBR-0061 CLOSED (mypy enforced by the gate + 4 test-tree type errors fixed)

Picked up the near-term chore filed at the end of the previous session (user
delegated "what's next"; a self-contained, autonomous chore was the right pick
over FIBR-0010, which needs a brainstorm/design-approval gate). Verified the
claim first (Karpathy — no silent assumptions): `ci-local.sh` ran ruff / format
/ bandit / pip-audit / gitleaks / pytest but **not** mypy, and `mypy src tests`
reported exactly the 4 errors the bullet named.

Fixes (surgical, test-only): added a `mypy` stage to `scripts/ci-local.sh`
(after gitleaks, before pytest — bare `mypy` uses the config's
`files = ["src","tests"]`, so it gates the test tree too; CI + the pre-push hook
inherit it since both invoke this script). None-guarded the three `findChild`
helpers in `tests/features/settings/test_settings.py` (`assert ... is not None`)
and aligned `_StubWorker.start` to the `QThread.start(self, priority=...)`
supertype signature in `tests/features/app_shell/test_app_shell.py`. No runtime
change; dev group already pins `mypy==2.1.0`, so no new dependency.

Gate green (pre-push hook ran it end-to-end, now including mypy): **366 passed /
1 skipped**, mypy clean (59 files), shellcheck 0. CHANGELOG → Changed; ROADMAP
FIBR-0061 → ✅; committed + pushed `383ee92`. No `-complete` tag (chore, not an
implementation phase). Next active item stays **FIBR-0010** (P08 rules engine).

### 2026-07-09 — four user-facing items shipped (FIBR-0057/0060/0058/0059) + FIBR-0061 filed

Worked the 2026-07-09 user queue in the order the user gave (0057 → 0060 → 0058
→ 0059), each closed via the full loop (audit + cold indie-review, findings
folded inline, CHANGELOG/ROADMAP/journal, tag, push).

- **FIBR-0057** (fix) — the import wizard snapshotted the target account at
  file-select. Fix: the preview step now carries the destination-account picker as
  the single source of truth (seeded from the pick step, read live via
  `_target_account_id()`, user-correctable; changing it re-dedups via
  `ImportService.retarget`). Cold-review fold: a remembered PDF password now
  follows a re-target. Tests: import_ ×3 + pdf_import ×1. Tag `FIBR-0057-complete`.
- **FIBR-0060** (fix) — window size/position + Center Window were X11-only (broken
  on Wayland). **User pointed me at their SystemManager project**, which solved
  Center-on-Wayland via KWin's scripting D-Bus API; I adopted the technique (via
  **QtDBus**, no dbus-send subprocess) + restore size via `resize()` (matching
  SystemManager's `set_default_size`). `_is_wayland`/`_kde_wayland`/`_center_supported`
  gate behaviour; Center is disabled+tooltip on non-KDE Wayland. **Live-verified on
  the user's KDE Wayland: window centres exactly.** Tests ×4. Tag `FIBR-0060-complete`.
- **FIBR-0058** (chore) — ofxparse 0.21 (latest, unmaintained) calls bs4's
  deprecated `findAll` (107 warnings/run). Scoped pytest filterwarnings quiets that
  one message; `beautifulsoup4>=4.9,<5` pin guards the latent breakage (findAll is
  removed in bs4 5.0, which would break OFX import). Gate: 0 warnings (was 107). Tag
  `FIBR-0058-complete`.
- **FIBR-0059** (feature) — "Change account" on the Statements tab: atomically
  re-points the `statement_periods` row + every stamped transaction to a chosen
  account (span-collision guarded with a `period_id` self-exclusion; distinct
  `reassigned` signal since the `changed` handler hard-codes "Statement deleted").
  New `AccountPickerDialog`. Spec `/cold-eyes`-converged in **6 cold loops** (design
  stable from loop 2). TDD ×14. Indie-review 1 LOW (undisposed dialog) folded. No
  schema change. Tag `FIBR-0059-complete`.
- **FIBR-0061** (chore, filed) — found during the FIBR-0059 close: `mypy` is **not**
  in `ci-local.sh`, and `mypy src tests` reports 4 pre-existing type errors in test
  files (FIBR-0055 `test_settings.py` ×3, `test_app_shell.py` ×1). Add mypy to the
  gate + fix them. FIBR-0059's own new src is mypy-clean.

Gate green throughout (final: 366 passed / 1 skipped). Ants-MCP feedback logged
(positive four-close write-path confirmation + re-verification of the amend_body
nested-sub-bullet limitation and the session_orient embedded-codebase_index gap,
build 9373a1bb). Next active item stays **FIBR-0010** (P08 rules engine).

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
