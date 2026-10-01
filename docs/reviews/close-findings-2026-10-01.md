# close-findings ledger — 2026-10-01

The queued findings of the 2026-09-27 full audit, one group per roadmap item
(FIBR-0388 … FIBR-0398). Evidence lives in
`docs/reviews/2026-09-27-full-audit/`. One commit per finding; the commit
carries the red run and the mutation check.

## FIBR-0388 — delivery group A

Closed before this ledger was opened (the skill was loaded after it), so its
rows were written up afterwards rather than before each edit. Dispositions
are in the roadmap note and the commits named there.

| finding | verified | disposition | was → now |
|---|---|---|---|
| A5 damaged file read as wrong password | yes — a flipped salt hex digit charges the throttle | fixed (user decision: correct the claim, no checksum) | CHANGELOG [0.1.23] over-claimed → names the limit (2df60bd) |
| A5 test | yes | fixed | service level only → UnlockDialog, six damages, zero count (2df60bd) |
| A1 hand-copied recovery code | yes | fixed | exact code only → lower case, O/l/I, spaces (5741faf) |
| A7 apostrophe path | yes | fixed | export_to only → export+verify, v1 upgrade (a861512) |
| A10 parallelism over the ceiling | yes | fixed | 0 only → ceiling + 1 (a6882ee) |
| A11 screen-reader names | yes | fixed | five fields via accessibleName → eighteen via QAccessible + module guard (c2e10dd) |

- **swept:** CHANGELOG.md A5 bullet — fixed; metainfo and debian/changelog
  0.1.23 entries — frozen (neither repeats the A5 claim).
- **collateral, surfaced, out_of_scope, falsified:** none.

## FIBR-0389 — delivery group B

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| B6 unnamed layout re-asked per file | yes — wizard repro: asked a-odd0, a-odd1, a-odd2, b-other | fixed | unnamed answer re-asked per file → applied to every identical header in the batch; red: asked all four | batch_import `_retry_blocked_on_mapping` docstring (rewritten); CHANGELOG [Unreleased] (added) |
| B6 test (wizard level) | yes — service level only | fixed | none → wizard test, named and unnamed, asserts asked == [a-odd0, b-other] | |
| B11 doubled inner space passes | yes — `fold_name` strips, does not collapse | fixed | inner runs kept → collapsed in the key only; red: 4 × DID NOT RAISE (space, NBSP; accounts, categories) | `fold_name` docstring (rewritten); FIBR-0328 tests (agree); CHANGELOG [Unreleased] (added) |
| B1 debit/credit guess leaves single style | yes — `_guess_mapping_combos` sets combos only | fixed | style left single → split style on a whole pair with no Amount; red: 'single' == 'debit_credit' | import_column_detect spec.md Out of scope (rewritten, test contract); CHANGELOG [Unreleased] (added) |
| B2 auto-lock test misses map-step legs | yes — seven legs, none on the map step or Back | fixed | + map Next named and unnamed, date-format change, preview Back; mutations: narrowing the save_profile or preview catch reddens its leg. Date change and Back read no vault today (regression legs, nothing to mutate); an amount-style change fires no slot | |
| B3 picker text unasserted | yes — test checks id and OK only | fixed | no text check → asserts combo reads "— pick one —"; mutation: blank placeholder reddens it | |
| B5 cancel test emits done() | yes — `widget.done.emit()` | fixed | emitted done → clicks the real Cancel on Preview and Map, account with and without its own password; mutations: map Cancel inert, restore skipping None, restore unwired each red the matching cases | |
| B8 huge exponent at parse only | yes — parse_transaction only | fixed | row-level only → CsvImporter.parse: one RowError, neighbours import; mutation: dropping the Overflow catch aborts the file with decimal.Overflow | |
| B10 private checksum with hand-built drafts | yes — calls `_verify_checksum` only | fixed | private call → whole A and D statements through `parse` (text layer replaced): complete imports both rows, truncated refused; Family D negative balance is `R50.00-`, which settles the audit's unparsed D control; mutation: magnitude compare reddens both | |

User decisions 2026-10-01: B6 reuse an answer within the batch for an
identical header, named or not; B11 fold runs of inner whitespace in the
uniqueness key.

- **cited_by:** `workspace_search` casefold / "Save this layout" / amount
  style / same layout / column guess over docs and packaging: 15 files; the
  password-hint containment (security-model, FIBR-0029) and the import dedup
  key (FIBR-0010, FIBR-0142) are different functions, not targets.
- **swept:** FIBR-0085-batch-import-service and -statement-import INVs (B6)
  — agrees, none states whether an answer is reused; FIBR-0085
  decision 1 — agrees (re-asking is babysitting); FIBR-0146-wizard-date-step
  "resets invert and amount style" (B1) — agrees, the reset still runs before
  the guess; FIBR-0085-batch-statement-import "five column combos, amount
  style" — agrees; metainfo and debian/changelog 0.1.23 wording on names and
  same-layout imports — frozen, the promises now hold more widely;
  CHANGELOG [0.1.23] B6 and B11 bullets — frozen, new [Unreleased] entries
  added instead. Code→code: no pair list (`.claude/code-pairs.json` absent).
- **collateral:** none.
- **surfaced:** B11 — a vault already holding two names that now share a
  key refuses any edit to either until one is renamed (the same held for
  accented names after FIBR-0328). Accepted as rare; not fixed.
- **out_of_scope:** docs/specs/FIBR-0193.md verification table says the
  account check "compares only `existing.name.casefold()`" — stale since
  FIBR-0328 added NFC, before this run; a dated verification record, left.
- **falsified:** none.

## FIBR-0390 — delivery group C

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| C17 CHANGELOG promises a dark PDF | yes — pdf_export `_PDF_THEME` is always light (FIBR-0217) | fixed | no correction → [Unreleased] note; no red run: nothing observable changes | CHANGELOG [0.1.23] (frozen) |
| C2 refresh test calls `_refresh()` | yes | fixed | direct `_refresh()` → real Add and Delete clicks (confirm answered Yes); mutation: dropping the re-gate in `_refresh` reddens both | |
| C4 startup-error test calls the hook by hand | yes | fixed | hook called by hand → `run()` fails building the window, the exception goes to `sys.excepthook` as the interpreter would; dialog names the fault, console hook still runs; mutation: removing `_install_excepthook()` from `run()` reddens it | |
| C6 Windows apostrophe: command text only | yes — both tests read the command text | queued as FIBR-0432 | needs a real run on `ssh wintest`, which was off (no route to host); rides with the Windows self-update test after FIBR-0346 | |
| C10 month name read from HTML, not the PDF | yes | fixed | `_build_html` → text of the rendered PDF under fr_FR; mutation: an English-only month name reddens it | |
| C12 failed install: no test | yes — no test drove `apply()` raising | fixed | none → installer raising UpdateError: one warning with the reason, verified file removed; mutations: dropping the unlink or the reason each redden it | |
| C13 check for updates twice: no test | yes | fixed | none → a blocking service; the second click while the first runs keeps the same worker and one forced call; mutation: removing the running-worker guard reddens it | |
| C14 Quit / Ctrl+Q save layout: no test | yes | fixed | none → menu Quit and Ctrl+Q with a check running: window closes, size in window.ini, check finished when close returns; mutations: Quit not closing, no save, no drain each redden both | |
| C15 auto-lock during reassign / move-under | yes — the one test forces the apply step; move-under untested | fixed | + real `service.lock()` then Reassign click (no picker, no slot error) and category selection (move-under disabled); mutations: removing either guard reddens its test | |
| C16 PDF row dates follow the date format: no test | yes | fixed | none → rendered PDF under dd/MM/yyyy and yyyy/MM/dd, rows carry that spelling, no ISO date; mutation: ISO row dates redden both | |

- **cited_by:** "dark PDF" across docs and packaging — CHANGELOG [0.1.23]
  and docs/specs/FIBR-0127.md; no other file.
- **swept:** CHANGELOG [0.1.23] trend-chart bullet — frozen, corrected by
  an [Unreleased] entry. No source file changed in this group (tests and
  the changelog only), so no code→docs target moved; the test contracts
  (spec.md) of the touched suites state nothing the new tests contradict.
- **collateral:** none.
- **surfaced:** none.
- **out_of_scope:** docs/specs/FIBR-0127.md cites "`services/pdf_export.py:99` (dark PDF
  theme)" — stale since FIBR-0217, before this run; left. Ctrl+Q does
  nothing on the locked and first-run screens (modal dialogs block the
  application shortcut), found while testing C14 — queued as FIBR-0431.
- **falsified:** none.

## FIBR-0391 — code lane 11, reporting

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| R1 root-assigned row double-counts a branch | yes — `category_node(root)` walks every child subtree, each also a top item; remedy checked: "treat a root like None" would disagree with the donut, which names the root's wedge | fixed | root node walked its children → holds its own rows only, named after the root; red: drill 500.00 vs tile 400.00; mutation: dropping the root guard reddens it | FIBR-0138 INV-1, D4a (amended: a root node holds only its own rows) |
| R2 transfer drill label bypasses tr() | yes — `_transfers_branch` builds `f"{from_account} → {to_account}"` | fixed | fixed arrow → `DrillLabels.transfer_pair`, `tr("{source} → {target}")` from HomeView; red: sentinel template ignored; mutations: the fixed arrow in the service, a bad placeholder and a swapped order in home.py each redden | FIBR-0138 INV-9, D2, D4b, symbols table; test contract INV-9 (all amended) |
| R3 `today` falls back to the OS clock | yes — four `today or date.today()` fallbacks; every src caller passes `today` (mypy clean after removal) | fixed | optional `today` + OS-clock fallback → required, in `ReportingService` and (same root cause) `PdfExportService.render_pdf_bytes`/`export`; red: a call without `today` ran; mutations: a default on any one of the six reddens it; two tests that leaned on the OS clock now pass a fixed date | callers of the four methods; FIBR-0013, 0138, 0143, 0231; month_summary docstring; pdf_export + datetime_display test text (all amended) |
| R4 FIBR-0139 D2/D5 stale against the code | yes — `_match_inputs` returns folded tuples (FIBR-0213); seeded duplicate names resolve under the seed root (FIBR-0204); INV-6a lives in the category_library test contract, not FIBR-0139 | fixed | spec described list returns, re-folding per row and plain first-wins → D2, D5 and the symbols table describe the folded inputs and the seed-root tie-break; the code's two INV-6a citations name where that clause lives; no red run: nothing observable changes | FIBR-0139 D2, D5, symbols table |

- **cited_by:** `DrillLabels`, `transfer_pair`, `render_pdf_bytes`,
  `_match_inputs`, `_leaf_name_to_id`, `top_of_chain`, `INV-6a` and the
  optional-`today` spellings across docs, src, tests and packaging. Most
  `transfer_pair` hits are the unrelated database table of that name — no
  verdict owed.
- **swept:** FIBR-0013, 0138, 0139, 0143 and 0231 — fixed (amended in the
  commit that changed the code). Test contracts dashboard_drilldown and
  pdf_export — fixed. month_summary.py docstring and datetime_display test
  text — fixed. FIBR-0143 INV-7 / D-sections and FIBR-0231 §4 on
  `DrillLabels` — agree (no label count). docs/security-model.md
  `render_pdf_bytes` — agrees (no path, unchanged). Test fakes accepting
  `today=None` (month_summary_home, app_shell) — agree (stand-ins).
  docs/journal/*, ROADMAP shipped notes, the audit report — frozen.
  No `.claude/code-pairs.json` exists, so no pair list to walk.
- **collateral:** `drill_down`'s docstring said four `tr()` strings after R2
  added a fifth — fixed in the R3 commit.
- **surfaced:** none.
- **out_of_scope:** docs/specs/FIBR-0013.md names the reporting methods'
  second argument `account_id`; the code takes `account_ids` — stale before
  this run, left. ui/transfers.py builds its "From → To" cell with a fixed
  arrow — already FIBR-0396, which prescribes the same `{source} → {target}`
  template, so one translation serves both. scripts/seed_demo_vault.py keeps
  a `today or date.today()` fallback — a demo seeder, no report path; left.
- **falsified:** none.

## FIBR-0393 — code lane 13, PDF export

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| P1 hidden Month/Year pickers leave bare labels | yes — `_sync_period_pickers` hid the field only; remedy checked: Home hides its pickers too, so hide the row rather than disable | fixed | field hidden, label left → `QFormLayout.setRowVisible` per row; red: bare "Month" label in Previous month; mutations: field-only hiding for either picker reddens it | FIBR-0013 mock-up note (amended: shown, not enabled) |
| P2 no flush + fsync before os.replace | yes — write then `os.replace`, no sync | fixed | no sync → `flush()` + `os.fsync` before the rename; no red run of the symptom (a power loss — the symptom is the harm), the order is locked instead; red: `replace` ran with no `fsync` before it; mutations: dropping the fsync, or the flush (with a sub-buffer PDF), each redden it | FIBR-0013 D1 (agrees) |
| P3 temp cleanup deletes a user's `<name>.part` | yes — `tmp.unlink` on `<name>.part` before the open | fixed | derived `<name>.part`, pre-deleted → `tempfile.mkstemp` (`.<name>.*.part`, O_EXCL\|O_NOFOLLOW, 0600); red: the user's `report.pdf.part` was deleted; mutations: the old pre-delete and dropping the failure cleanup each redden a test; four leftover-temp assertions repointed at the real name (they had gone vacuous), + a failed-replace test | FIBR-0013 D1 (agrees); security-model.md INV-7 note (amended) |
| P4 empty render written and reported as exported | yes — no check on `buffer.open` or the bytes | fixed | unchecked bytes → `PdfRenderError` unless they start with `%PDF`, raised before encryption and the write; it propagates past the save-error handler as a fault (cursor restored in `finally`, no "Report exported"); a separate `buffer.open` check was dropped as redundant — an unopened buffer yields no bytes; red: an empty render was exported; mutation: dropping the check reddens it | FIBR-0013 INV-2, INV-12 (agree) |
| P5 ASCII year beside a QLocale month; chart axes not localised | yes — `str(end.year)` / `year=end.year`; no `setLocalizeNumbers` | fixed | ASCII year → `datetime_format.format_year` (locale digits, no group separator) in the PDF period line and, as its stated pair, the month-summary strip; value axes → `setLocalizeNumbers(True)`; red: "يناير 2026", "2026" in the strip, `localizeNumbers()` False; mutations: each year site, the separator option, and each chart separately redden a test | ui/month_summary.py "same spelling" pair (both changed) |
| P6 slice and legend labels may render rich text | yes, by probe — `<b>x</b>` drew as wide as `x` (markup honoured), its escaped form as wide as the literal text | fixed | raw labels → `html.escape` in `build_donut_chart` and `build_breakdown_donut` (the "Other" label too, untested: a translated string, not user data); `label()` now returns the escaped text, read back only by tests; red: the marked-up name drew as narrow as "x" in both builders; mutations: either site unescaped reddens it | |
| P7 comments cite the withdrawn Dark theme and an unrun exec() | yes — charts.py module docstring and trend comment; `options()` docstring | fixed | "Light or Dark", "the Dark PDF export", "after an accepted exec()" → the one light theme (FIBR-0217), the dark-default reason alone, "in the accepted slot"; no red run: nothing observable changes | |
| P8 FIBR-0013 D1 describes `sections` + `today` fields | no — D1 already lists the three booleans and no `today` field (7cc7fe4, FIBR-0343); its `today` signatures were settled by FIBR-0391 R3 | dismissed | fixed before this run; nothing to do | FIBR-0013 D1 (agrees) |

- **cited_by:** `.pdf.part`, "Dark PDF", "Light or Dark", "accepted
  `exec()`", `str(end.year)`, `setLocalizeNumbers`, `_sync_period_pickers`,
  `standaloneMonthName` across docs, src, tests and packaging.
- **swept:** FIBR-0013 D1 write step ("a sibling temp file") — agrees; mock-up
  picker note — fixed (P1). docs/security-model.md INV-7 temp note — fixed
  (P3). FIBR-0013 INV-2 / INV-12 against the `PdfRenderError` refusal —
  agree. FIBR-0231 §4 `{month}` passage (says how the month is composed, not
  how the year is spelled) — agrees. `period_filename_slug`'s
  `str(end.year)` — agrees (a file name stays ASCII by design).
  ui/month_summary.py "same spelling" pair with the PDF period line — fixed
  together (P5). main_window.py's export handler — agrees (`finally`
  restores the cursor; a propagated `PdfRenderError` skips "Report
  exported"). Test readers of a slice's `label()` — agree (none uses a name
  with `&` or `<`; the lock-wipe walk only collects texts). The audit
  report and earlier ledgers — frozen. No `.claude/code-pairs.json` exists.
- **collateral:** two FIBR-0013 lines my own R3 and P1 amendments left
  unwrapped — rewrapped in the group-close commit.
- **surfaced:** none.
- **out_of_scope:** tests/features/dashboard/test_charts.py docstring still
  said unthemed axes were "invisible in the Dark PDF export" — the P7
  class, stale since FIBR-0217; fixed (deterministic). The audit's other
  two lane-13 findings are not in FIBR-0393: the `O_BINARY` Critical was
  refuted on the Windows box and the bracket-negatives Medium fixed, both
  in the 2026-09-27 ledger. Amounts mix digit systems under ar_EG — the
  strip test rendered "R ٢٬٣٤٠٫00" — already FIBR-0398's Medium, which the
  audit marked not executed; this is the execution.
- **falsified:** none.

## FIBR-0394 — code lane 14, main window

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| M1 Help > Check for updates while locked drops its answer | yes, measured — with the unlock dialog up a window-system click on Help is blocked (setModal), but Cancel leaves the app locked with no dialog ("stay locked") and Help then opens | fixed | `if not self._unlocked` → silenced only if a lock fired after the click (`_manual_check_started_unlocked`, recorded at the click); red: no box for up-to-date or error from a check started while locked; mutations: the old gate, no gate, and not recording at the click each redden a test; a test comment claiming the menu is unreachable while locked corrected | FIBR-0054 (says nothing on this); FIBR-0216 test (still green) |
| M2 auto-lock inside the save picker shows a wrong error | yes — neither handler checks the lock after `getSaveFileName` returns | fixed | export ran on a locked vault and warned "choose another location" → `_locked_during_picker(dialog)` stops both exports quietly; red: the warning appeared over the unlock dialog for PDF and backup; mutations: the helper never true, and each call site removed, each redden a test | FIBR-0013 INV-12, FIBR-0014 (agree: no partial file either way) |
| M3 last-used tab read once at launch | yes — `_initial_tab` set only by `_restore_geometry` in `__init__` | fixed | launch-time tab on every unlock → `_on_tab_changed` updates `_initial_tab` (signal connected after the tabs are added, so the build cannot overwrite it); remedy simpler than re-reading the INI, same effect; red: unlock landed on tab 0, not 3; mutation: not remembering reddens it | |
| M4 restore keeps the replaced vault's hint and throttle | yes — the restore path enters unlocked with no `clear_hint()` / throttle reset; the audit's open question ("does a contract require it?") answered from FIBR-0014 INV-3: a restore always sets a NEW master password, so both keys belong to a password that no longer opens the vault | fixed | kept → cleared after a successful restore, as Start over does; my call, recorded rather than put to the user (a bug fix, no spec owed — rule 14b); red: the old hint survived; mutations: keeping either reddens it | FIBR-0029 (lists no exhaustive clear set; agrees); FIBR-0014 INV-3 |
| M5 untranslated UpdateError inside a translated sentence | yes — `.format(reason=str(exc))` on the install-failure path; the installer's messages are English f-strings around the OS error | fixed | English reason in a `tr()` sentence → `_install_failure_text`: translated text chosen by the OS error under the UpdateError (disk full; not allowed / read-only; otherwise generic), raw message to the log; the FIBR-0390 C12 test, which asserted the raw reason, now asserts the mapped text per errno; red: the raw text was shown; mutations: the raw reason back, and dropping either mapped branch, each redden it | FIBR-0054 INV-11, FIBR-0131 INV-4 (an error dialog; agree) |
| M6 FIBR-0159, FIBR-0155, FIBR-0231 §4.9 cite stale line numbers | yes — every `main_window.py:NNN` (and its `:NNN` shorthand) in the three specs pointed elsewhere | fixed | line numbers → the symbol each pointed at (`_open_url`, `_update_supported()`, the two export handlers, `_center_kwin`, `MainWindow.__init__`…), each confirmed to exist; FIBR-0231's guard table converted whole, its `home.py` rows included; loop-log rows citing old lines left (frozen); no red run: nothing observable changes | |

- **cited_by:** "blocks the menu", "only reachable", `reason=str(exc)`,
  "cannot fire mid-export", `_initial_tab`, `last_tab`, `clear_hint`,
  `UnlockThrottle().reset()` across docs, src and tests.
- **swept:** FIBR-0014 and tests/features/backup/spec.md "cannot fire
  mid-export" — agree (true once the picker returns, which M2 now checks).
  FIBR-0030's coupled-keys list (throttle + hint "described the old
  password") — agrees with M4. FIBR-0029 hint clears — agree (no exhaustive
  list). FIBR-0052 "`setCurrentIndex(last_tab)` applied when the workspace
  is built" and FIBR-0192's `last_tab` passages — agree with M3.
  FIBR-0029 / FIBR-0055 "only reachable unlocked" — about Set hint and
  Settings, not Help; agree. FIBR-0054 INV-11 / FIBR-0131 INV-4 (an
  install failure shows a dialog) — agree with M5. tests/conftest.py
  `_initial_tab` note — agrees. Audit reports and loop-log rows — frozen.
  No `.claude/code-pairs.json` exists.
- **collateral:** none.
- **surfaced:** none.
- **out_of_scope:** FIBR-0159's other line citations (update_installer,
  update, import_wizard, pdf_export, backup) resolve in range but no
  longer hold what the spec describes — queued as FIBR-0433. Lane 14's two
  Mediums not in FIBR-0394 (first-run Cancel using `quit()`; lock wipe
  missing in four widgets) were fixed on 2026-09-27 (rows 29 and 30 of
  that ledger).
- **falsified:** none.

## FIBR-0395 — code lane 15, security screens

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| S1 English exception text in first_run and recovery_key dialogs | yes, and wider than cited — seven sites: first-run validation (`str(exc)`), creation, derivation and prefs failures, and the recovery-code save, keep and new-password failures (`{error}` into `tr()`) | fixed | raw text → translated words at all seven; validation names its refusal by type (`PasswordEmptyError`, `PasswordMismatchError`, both `ValueError`s), mapped to the sibling dialogs' wording; failures log the raw text; the two FIBR-0367 prefs tests, which asserted "disk full" was shown, now assert the translated sentence and its absence; red: every site showed the marker text; mutations at all nine points redden a test | first_run test contract (amended); design.md § i18n |
| S2 Settings Save catches only VaultLockedError | yes — `_on_save` catches `VaultLockedError` alone around four `set_*` writes | fixed | a SQLCipher error escaped the slot → caught as `DatabaseError` (as the backup handler does): a translated warning, Settings stays open, raw text logged; red: `OperationalError` escaped `_on_save`; mutations: not catching it, and emitting `saved` anyway, each redden it | |
| S3 FIBR-0054 INV-7 calls Windows updates un-wired | yes — INV-7 says an AppImage only and names "a future un-wired Windows build"; `detect_installer()` returns a `WindowsInstaller` for a frozen `.exe` (FIBR-0131) and requires `$APPDIR` for an AppImage (row 39) | fixed | INV-7 amended to state both installers and the `$APPDIR` check as the code does; no red run: nothing observable changes | FIBR-0054 INV-7 (amended); settings.py tooltip (agrees) |

- **cited_by:** "un-wired", "Off an AppImage", `validate_first_run`,
  "passwords do not match", `{error}`, `prefs_not_saved` across specs,
  design, security model, tests and src.
- **swept:** FIBR-0004 "a mismatch is caught in `validate_first_run`" —
  agrees (now a typed `ValueError`). FIBR-0019 / 0029 / 0051 / 0083 and the
  vault, password-hint and password-strength test contracts on
  `validate_first_run` — agree (they rely on it raising `ValueError`, which
  both new types are). tests/features/auto_update/spec.md INV-7 ("off an
  AppImage … `$APPIMAGE` unset → None") — agrees, it describes the Linux
  case. main_window's `prefs_not_saved` handler — agrees (shows whatever
  text it is handed). app.py's crash dialog `{error}` — agrees: it names
  the fault on purpose so it can be reported (FIBR-0390 C4 locks it). No
  `.claude/code-pairs.json` exists.
- **collateral:** none.
- **surfaced:** none.
- **out_of_scope:** none.
- **falsified:** none.

## FIBR-0396 — code lane 16, data views

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| D1 transfer cell arrow is a fixed literal | yes — `f"{item.from_account} {_ARROW} {item.to_account}"` | fixed | f-string → `tr("{source} → {target}")`, the same source text as the dashboard's transfer label (FIBR-0391 R2); `_ARROW` removed (no other user); red: a stub catalog's reordered template was ignored; mutation: the untranslated literal reddens it | FIBR-0391 R2 template (agrees); only audit reports quoted the old literal (frozen) |
| D2 display strings joined by +, join or f-string | yes — transfers `text += " " + tr(...)`, accounts `" · ".join(...)`, statements `f"{start} – {end}"` | fixed | glued → one `tr()` template each: `{confirmed} {skipped}` (each sentence keeps its own `%n`), `{reconciliation} · {password}` (a single part shown alone), `{start} – {end}`; tests use a new shared `translate_one` fixture (stub catalog), which D1's test now uses too; red: each reordered template was ignored (real text shown); mutations: each site's old join reddens its test | FIBR-0201 §4.8 (two translated sentences; agrees) |
| D3 service error text shown via str(exc) | yes — manual_entry and three accounts handlers render `str(exc)` from Qt-free services; FIBR-0219 §4.1 relies on it, design.md § i18n forbids it | queued as FIBR-0434 | needs a decision, not an edit: typed rejections across three services (one message embeds two values) plus a FIBR-0219 amendment; recommended alongside FIBR-0017, since finbreak ships English only and no user sees it before then | FIBR-0219 §4.1; design.md § i18n |
| D4 `_on_set_category` has no VaultLockedError guard | yes — two category reads before the picker, unguarded; reached from `menu.exec`, a nested loop the auto-lock can fire in | fixed | unguarded → returns quietly on `VaultLockedError`, no picker; red: the lock error escaped the slot; mutation: dropping the guard reddens it | |

- **cited_by:** "From → To", `_ARROW`, "suggestion(s) were skipped",
  "balances reconcile · ", `leaf_categories_grouped`, `_on_set_category`
  across specs, design, tests and src.
- **swept:** FIBR-0011 and tests/features/transfers/spec.md ("From → To
  reads debit-account → credit-account") — agree (English output
  unchanged). FIBR-0201 §4.8 (the second, translated sentence) — agrees.
  The accounts status test's exact English cell — agrees (still passes).
  FIBR-0065 / 0012 / 0032 / 0123 / 0154 on `_on_set_category` — agree
  (describe the picker flow, not a lock rule). ui/rules.py `_on_add`
  carries the same guard (FIBR-0211) — agrees; D4 now matches it. Audit
  reports quoting old code — frozen. No `.claude/code-pairs.json` exists.
- **collateral:** the first `translate_one` returned "" for unmatched
  strings, which Qt takes as a translation and blanks other labels; caught
  before commit (the accounts test saw an empty cell) and fixed to return
  None.
- **surfaced:** none.
- **out_of_scope:** tests/features/recovery_key/test_recovery_code.py's
  local `_Catalog` returns "" the same way; harmless there (the test reads
  only its one string), left. The Statements count column prints
  `str(transaction_count)`, not a locale number — noted for FIBR-0434's
  i18n pass rather than fixed blind.
- **falsified:** none.

## FIBR-0397 — code lane 17, category views

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| C1 recurring `refresh()` unguarded after a write | no, measured — the auto-lock is a QTimer (`AuthService._on_idle_timeout`), so it fires only from the event loop; each write and its `refresh()` run in one synchronous slot with no nested loop between; probe: with the idle timer already due, a write then re-read ran on an OPEN vault and the lock landed only once events ran; every other `refresh()` caller runs unlocked | dismissed | unreachable; no change | rules.py's FIBR-0211 guard rests on the same reasoning — harmless, left |
| C2 categories `_refresh` / `_add_children` unguarded | no, measured — same probe on `CategoriesWidget._on_add`: the re-read ran on an open vault with the lock already due; delete's confirm box (a nested loop) sits BEFORE its guarded write | dismissed | unreachable; no change | |
| C3 service exception text, type name included, in AutoText labels | yes — the duplicate-name refusal quotes the user's text into a rich-text label; rules.py's messages carry no user text | fixed (markup half); i18n half queued on FIBR-0434 | categories error label AutoText → PlainText; red: "<b>Rent</b>" drew 247 px against 291 px as literal text; mutation: back to rich text reddens it; the untranslated text in categories and rules annotated onto FIBR-0434 | FIBR-0434 (annotated) |
| C4 `setChart` may leak the old QChart | yes, measured — five Forecast refreshes replaced five charts and destroyed none | fixed | `setChart` at four sites (Forecast, the dashboard pies twice, the trend) → `charts.replace_chart`, which deletes the released chart; red: no replaced chart was destroyed (Forecast and the dashboard); mutation: dropping the delete reddens both | |
| C5 Level-2 subject with grandchildren: empty Move-under combo | no, measured — such a subject gets no authorable target, and row 17's fallback then offers its current parent first; the case added to row 17's parametrised test passes, and removing the fallback reddens it | dismissed | already fixed by 2026-09-27 row 17; the Level-2 case added to its test so it stays covered | 2026-09-27 ledger row 17 (agrees) |
| C6 forecast sign by concatenation, ", " separator | yes — `"+" + amount`, four `", ".join` name lists, and the two exclusion sentences and the later-transactions clause appended with `" " +` (the cited lines) | fixed | → `tr("+{amount}")`, `_join_names` (a translated separator), `_then` (`tr("{text} {more}")`); English output unchanged; red: the reordered sign and the separator/sentence templates were ignored; mutations: each of the three reddens a test | FIBR-0171 D9 (`+R X` in English; agrees) |
| C7 alerts `_render` reparents a row mid-signal | yes, measured — the audit said "probably safe"; the clicked Dismiss button was already destroyed when its own `click()` returned (`setParent(None)` left Python the only owner) | fixed | freed inside its own signal → `deleteLater()` after the detach, freed from the event loop; a held reference was tried and removed as dead (PySide's `deleteLater` hands ownership back to Qt; its mutation survived); red: the button was invalid when `click()` returned; mutation: dropping `deleteLater` reddens it | |

- **cited_by:** `setChart`, `setParent(None)`, "later transaction(s)",
  "Excluded (no recorded balance yet)", "a category named", "Rebuilt rather
  than refreshed" across specs, design, the three suites' contracts and
  src. "only)" matched noise across the specs and owes no verdict.
- **swept:** every `setChart` now goes through `charts.replace_chart` —
  agrees. main_window's `worker.setParent(None)` — agrees (deliberate:
  workers outlive the window on a Python reference, FIBR-0327). FIBR-0171's
  "+ N later transaction(s)" example — agrees (English output unchanged).
  FIBR-0032's `clipboard.setParent(self)` — agrees (a different object).
  rules.py's FIBR-0211 refresh guard — rests on the reasoning C1/C2's
  measurement refutes; harmless, left. No `.claude/code-pairs.json`
  exists.
- **collateral:** none.
- **surfaced:** none.
- **out_of_scope:** none new; the translation half of C3 is on FIBR-0434.
- **falsified:** none.

## FIBR-0398 — code lane 18, UI infrastructure

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| U1 amounts mix locale digits with an ASCII fraction | yes, executed — the FIBR-0393 strip test rendered "R ٢٬٣٤٠٫00"; the ungrouped fallback for a huge whole part is ASCII too | fixed | Python's ASCII digits → `_locale_digits`, through QLocale's own 0-9, for the fraction and the fallback (a helper, not `str.translate`, which the i18n guard reads as Qt's `translate()`); red: ar_EG and fa_IR each showed two digit systems; mutations: either part left ASCII reddens it; round-trip parse tests still green | FIBR-0153 (agrees) |
| U2 a mistyped timezone is silently saved as system | yes — `_read_timezone` returns "system" for text naming no zone; that is FIBR-0083 Deliverables 3–4's specified persist rule | queued as FIBR-0435 | a direction change to a spec (owes its gate), so not an edit here; recommended: refuse Save / first-run submit with a translated message, then amend FIBR-0083 D3/D4 | FIBR-0083 D3/D4 |
| U3 FIBR-0153 / FIBR-0219 describe the removed float route | yes — both specs (and FIBR-0219's ambiguity-message rendering) name `QLocale().toString(float(...))`; the code uses `_grouped` everywhere | fixed | five passages amended to `_grouped`, exact and never `float` (FIBR-0327, FIBR-0398); FIBR-0219's scientific-notation rationale replaced by the exact-path reason; no red run: nothing observable changes | FIBR-0153 §3.2, INV-3; FIBR-0219 §2, §4.5, §9 (amended) |
| U4 FIBR-0127 INV-3/INV-4 and theme.py token counts | yes — INV-3 and the symbols list omit `attention` and say 8 colours; INV-4 maps Link to `accent_soft` where the code (and INV-4b) uses `accent`; theme.py's module docstring says eight | fixed | FIBR-0127 INV-3, INV-4 and the symbols list amended to the code (attention named, FIBR-0185/0186; Link←accent, FIBR-0214); the docstring's count replaced by "a set of"; no red run: nothing observable changes | FIBR-0127 INV-3, INV-4, symbols (amended) |
| U5 the ambiguity refusal is an untranslated f-string | yes — `_ambiguous` builds English text; FIBR-0219 §9 says plain English, design.md § i18n says tr() | queued as FIBR-0434 | the same decision as FIBR-0434's service messages (it already names the ambiguous-amount message); annotated there | FIBR-0434 (annotated) |
| U6 a 4300+-digit amount shows an interpreter message | yes, measured — `"1"*4400 + ".500"` under en_US and de_DE showed "Exceeds the limit (4300 digits) for integer string conversion…"; the `int()` is `_grouped`'s, reached while the ambiguous readings render | fixed | remedy checked and changed: the audit's input-length cap breaks FIBR-0219 INV-9 (a 400-digit input must parse; the service bound stays the one bound — its test went red), so `_grouped` compares the length before `int()` instead; red: the interpreter text was the refusal; mutation: `int()` first reddens it | FIBR-0219 INV-9 (agrees) |

- **cited_by:** `toString(float`, "eight semantic", "8 colours", Link ←
  `accent_soft`, `_grouped`, `_read_timezone` across docs, tests and src
  (audit reports excluded).
- **swept:** tests/features/theme/spec.md "eight semantic colour tokens" —
  fixed (count dropped, as in theme.py). test_amount_input's FIBR-0327
  docstring — agrees (describes the old bug in the past tense). `_grouped`'s
  own docstring — agrees (fraction from the exact Decimal digits; fallback
  ungrouped). FIBR-0219 INV-9 — agrees, and decided U6's remedy.
  docs/journal/FIBR-0127.md and ROADMAP's FIBR-0214 notes — frozen. No
  `.claude/code-pairs.json` exists.
- **collateral:** none.
- **surfaced:** none.
- **out_of_scope:** none new.
- **falsified:** none.

## FIBR-0404 — code lane 4, backup

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| B1 the live vault as destination reads "too large to back up" | yes — the destination guard raises a plain `BackupError`, which the window's handler (written when INV-14 was the only export raise) always calls the size refusal | fixed | plain `BackupError` → `BackupDestinationError` (a subclass, so existing catchers still hold), caught first with its own message; red: "too large to back up" shown for the vault file; mutation: a plain `BackupError` reddens it | FIBR-0014 INV-14 (agrees) |
| B2 export stages up to 512 MiB in the system temp dir | yes — `TemporaryDirectory()` with no `dir`, holding a copy up to the restore cap | fixed | system temp → a hidden `.finbreak-backup-*` dir beside the destination, removed on exit (the temp zip was already there); red: an unwritable system temp dir failed the export; mutation: no `dir=` reddens it | FIBR-0014 (names no staging place; agrees) |
| B3 disk-full while verify migrates its copy reads wrong_password | yes — SQLITE_FULL arrives as `OperationalError`, a `DatabaseError`, caught as wrong_password | fixed | → io_error when SQLite's primary code is SQLITE_FULL (13) or SQLITE_IOERR (10), read from `sqlite_errorcode`, never the message; red: a genuine SQLITE_FULL (a one-page-capped scratch DB) read as wrong_password; mutations: no storage branch, and no SQLITE_FULL code, each redden it; SQLITE_IOERR is not driven by a test (no cheap genuine source) | FIBR-0033 D7 io_error (agrees) |
| B4 post-install temp cleanup inside the normalising try | yes, executed — with the assembly dir's removal failing, the vault WAS installed and restore still raised BackupError ("unchanged"); the two prunes were already best-effort | fixed | `TemporaryDirectory` → `_assembly_dir`, whose removal is best-effort and logged (a leftover is swept by prefix, FIBR-0337 M4); the M4 crash test's stand-in repointed at it; + a test that an ordinary restore leaves no assembly dir (the "never removed" mutation had survived); red: BackupError over an installed vault; mutations: the removal error escaping, and no removal, each redden a test | FIBR-0014 INV-4 (a failure changes nothing; agrees) |
| B5 destination guard misses the WAL siblings | yes — `live` held only `vault.db` and the sidecar | fixed | + `vault.db-wal`, `vault.db-shm` via `_WAL_SIBLINGS`, the same `BackupDestinationError` (so B1's message covers them); red: an export to either was not refused; mutation: dropping the siblings reddens both | FIBR-0014 (agrees) |
| B6 "{n} transactions." has no plural | yes — `tr("{n} transactions.")` | fixed | → `tr("%n transaction(s).", "", n)`, the project's plural idiom; red: a catalog's singular form could not apply ("1 transactions."); mutation: the old string reddens it | |
| B7 FIBR-0014 says .old pruning is manual; code prunes (INV-17) | yes — INV-5 "always recoverable" and Out of scope "manual for now"; `_prune_superseded_old_copies` prunes (FIBR-0318, test contract INV-17) | fixed | INV-5 amended to the kept-set rule; the out-of-scope bullet removed; no red run: nothing observable changes | FIBR-0014 INV-5 (amended); backup test contract INV-17 (agrees) |
| B8 FIBR-0030 §3.2 says DELETE sits inside the tr() string | yes — the spec's example keeps `DELETE` inside the `tr()` literal; the code interpolates `CONFIRM_WORD` (FIBR-0216), which a translator cannot change | fixed | §3.2 amended to the interpolated form and why; no red run: nothing observable changes | FIBR-0030 §3.2 (amended) |

- **cited_by:** `BackupError` export handling, "vault itself",
  `_WAL_SIBLINGS`, `TemporaryDirectory`, `wrong_password`, `io_error`,
  "always recoverable", "manual for now", the DELETE prompt, across
  docs, src and tests.
- **swept:** FIBR-0014 INV-4 / INV-14 / INV-5 — agree (INV-5 amended, B7).
  FIBR-0033 D7 io_error — agrees with B3. FIBR-0030 §3.2 — amended (B8).
  The FIBR-0337 M4 crash test — repointed at `_assembly_dir` (B4), still
  red without the prefix sweep. main_window's export handler comment —
  updated with B1. docs/security-model.md — names neither staging place
  nor the destination guard; agrees. No `.claude/code-pairs.json` exists.
- **collateral:** B4's first test called `monkeypatch.undo()`, which the
  suite's isolation guard forbids; caught by the pre-push gate, fixed in
  the unpushed commit (`monkeypatch.context()`).
- **surfaced:** none.
- **out_of_scope:** queued as FIBR-0436 — restore still reads SQLITE_FULL
  as a password problem; verify stages in the system temp dir (FIBR-0033
  D6 specifies it, so a spec change); export's `<dest>.tmp` is unlinked
  before its O_EXCL open (P3's class).
- **falsified:** none.

## FIBR-0406 — code lane 6, CSV and OFX import

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| I1 `_resolve_zone` trusts the system zone; `date(0,0,0)` crashes "today" | yes, executed — TZ=Nowhere/Nope and TZ=:/etc/missing both crashed `today_in("system")` with "year 0 is out of range" | fixed | invalid system zone → `QTimeZone(LocalTime)` (the OS fallback); timestamps display again too; red: ValueError with a faked invalid system zone; mutation: trusting the system zone reddens it; the real TZ=Nowhere/Nope run now gives today's date | FIBR-0083 INV-6 (fail-safe on a bad zone; agrees) |
| I2 `_validate_span` does not canonicalise span dates | yes — `fromisoformat` accepts "20260105" and "2026-W02-2", and `commit_import` stored the raw strings (latent: the wizard passes canonical dates) | fixed | `_validate_span` returns `isoformat()` endpoints and `commit_import` uses them; red: the raw forms were stored; mutation: discarding the canonical pair reddens it | FIBR-0216 (transaction dates canonical; agrees) |
| I3 a non-UTF-8 file shows the raw codec error | yes — `read_file`'s `.decode("utf-8-sig")` raised `UnicodeDecodeError`, shown as-is | fixed | → `ValueError("the file is not UTF-8 text; save it as UTF-8 and try again")` (still English service text — FIBR-0434's decision — but readable); red: the codec text and byte offset were shown; mutation: not catching it reddens it | FIBR-0434 |
| I4 importer errors are English f-strings, one a list repr | yes — csv_importer and ImportService refusals shown with `setText(str(exc))` | queued on FIBR-0434 | the same decision (typed service rejections, with FIBR-0017); annotated there | FIBR-0434 (annotated) |
| I5 `qdate.toString(pref)` renders English month names | yes — `QDate.toString(pattern)` is C-locale; its mirror `QTime.toString` did the same for AM/PM | queued as FIBR-0437 | a fix was built and verified (96f0fa6: red under fr_FR / zh_CN, both mutations killed), then withdrawn: the sweep found FIBR-0083 specifies `dt.date().toString(token)`, so localising is a direction change that owes the spec gate BEFORE the build; reverted, queued with the amendment + gate and the Settings sample labels | FIBR-0083 three-way rule |

- **cited_by:** `_resolve_zone`, `systemTimeZoneId`, `_validate_span`,
  `read_file`, `DATE_PRESETS`, `toString(token)` across docs, src and tests.
- **swept:** FIBR-0083 INV-6 (fail safe on a bad zone) — agrees with I1.
  FIBR-0083's three-way rendering rule (`dt.date().toString(token)`) —
  DISAGREED with the I5 fix, which was then withdrawn (bc2cf71) and queued
  as FIBR-0437; agrees again. Settings' fixed English sample labels —
  agree with the C-locale rendering now restored; their rework rides with
  FIBR-0437. FIBR-0216's canonical transaction dates — agree with I2. No
  `.claude/code-pairs.json` exists.
- **collateral:** the I5 fix itself (96f0fa6), reverted in bc2cf71.
- **surfaced:** the same reasoning reaches FIBR-0391 R2 and R3: both
  amended spec signatures (a new `DrillLabels` field; `today` required)
  under the "records existing code" exception, which does not cover a
  direction the run itself set. Raised with the user rather than undone.
  **User decision 2026-10-01: accept and record** — R2 and R3 stand as
  committed, with no gate run on FIBR-0138, FIBR-0013, FIBR-0143 or
  FIBR-0231: they change internal call shapes of shipped features, nothing
  a user sees. FIBR-0437 (user-visible) still owes FIBR-0083's gate.
- **out_of_scope:** none new.
- **falsified:** none.

## FIBR-0408 — code lane 8, import wizard

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| W1 after "Create it" the match label is hidden | yes — the combo change runs `_on_confirm_account_changed`, which hides the label, before the text is set; spec checked first: FIBR-0086 §4.6 says the message shows | fixed | text in a hidden label → `show()` after it is set, both branches; red: hidden with the right text, with and without a number; mutation: no `show()` reddens both | FIBR-0086 §4.6 (agrees) |
| W2 a wrong PDF password re-prompts with an identical dialog | yes — wizard `_on_pdf_password` and batch `_ask_password` built the same dialog again; spec checked: FIBR-0009 INV-3 says "re-shows" the dialog — a note leaves that intact (grey zone, no gate) | fixed | `PasswordDialog(retry=...)` adds "That password didn't work. Try again."; wizard passes it on the re-prompt, batch on any second prompt for a file; three test fakes widened to accept `retry`; red: the re-prompt was not marked; mutations: the dialog note, the wizard flag and the batch flag each redden a test | FIBR-0009 INV-3 (agrees) |
| W3 tr(...) + " " + text joins display strings | yes — the date nudge was glued to the sample line | fixed | → `tr("{warning} {dates}")`; red: a reordered catalog template was ignored; mutation: the untranslated template reddens it | |
| W4 the OFX statement label is an f-string with a raw type | yes — `f"{account_id} · {account_type}"`, the bank's code shown raw; spec checked: FIBR-0008 D8 gives the shape `"<account_id> · <type>"` (kept) without saying raw code or name — grey zone, no gate | fixed | → `tr("{number} · {type}")` with translated names for the standard OFX types, an unknown code as written; English now reads "Savings", not "SAVINGS" (changelog: Changed); red: a catalog's type name and order were ignored; mutations: raw code, fixed order each redden it | FIBR-0008 D8 (shape agrees) |
| W5 design.md quotes preview wording the app never shows | yes — "12 of 240 rows couldn't be parsed" vs the built `{new} new · {dup} duplicate · {err} error` | fixed | the example now quotes the built counts line; no red run: nothing observable changes | docs/design.md § Error handling (amended) |
| W6 `_on_confirm_account_changed` catches only VaultLockedError | no — `retarget` → `_build_preview` → `_dedup` (vault reads) raises `VaultLockedError` (caught) or a storage `DatabaseError`; coding.md §2 routes unexpected faults to propagate loudly (the crash reporter), as main_window's handlers state | dismissed | by design: nothing else is raised, and catching a storage fault here would swallow it; no change | coding.md §2 (agrees) |
| W7 `_ask_mapping` calls `read_header` unguarded | no — a record reaches `needs_mapping` only after SCAN's `read_header(record.source_text)` succeeded (batch_import `_scan_text`), and `_ask_mapping` re-reads that same text; `read_header` is deterministic | dismissed | a guard would be a path that cannot happen (coding.md §2); no change | coding.md §2 (agrees) |

- **cited_by:** `_account_match_label`, `PasswordDialog(`, `" " +` joins,
  the OFX chooser label, "couldn't be parsed", `read_header`, `retarget`
  across specs, design, src and tests.
- **swept:** FIBR-0086 §4.6 — agrees (W1 restores it). FIBR-0009 INV-3 —
  agrees (the dialog is still re-shown, W2). FIBR-0008 D8's label shape —
  kept (W4). docs/design.md § Error handling — amended (W5). coding.md §2
  — decided W6 and W7. Every other `PasswordDialog(` caller is one of the
  two changed sites; all three test fakes widened. No
  `.claude/code-pairs.json` exists.
- **collateral:** test_create_dialog_prefills_from_the_statement had no
  QApplication fixture and aborted once tests were added beside it; it
  takes `qapp` now (in W1's commit).
- **surfaced:** none.
- **out_of_scope:** the Categories delete confirmation was the last
  `" " +` join of display sentences in the UI — fixed (3b344a9), the
  D2 / W3 class with the same template fix.
- **falsified:** none.

## FIBR-0409 — code lane 10, money services

| finding | verified | disposition | was → now | must_agree |
|---|---|---|---|---|
| M1 service errors are English strings spliced into setText | | | | FIBR-0434 |
| M2 bulk confirm / reject skip the database checks | | | | FIBR-0011 INV-4; FIBR-0201 |
| M3 reassign can leave a confirmed transfer inside one account | | | | FIBR-0011; FIBR-0059 |

- **cited_by:**
- **swept:**
- **collateral:**
- **surfaced:**
- **out_of_scope:**
- **falsified:**
