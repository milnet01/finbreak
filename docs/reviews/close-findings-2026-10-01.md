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
| P2 no flush + fsync before os.replace | | | | FIBR-0013 D1 |
| P3 temp cleanup deletes a user's `<name>.part` | yes — `tmp.unlink` on `<name>.part` before the open | fixed | derived `<name>.part`, pre-deleted → `tempfile.mkstemp` (`.<name>.*.part`, O_EXCL\|O_NOFOLLOW, 0600); red: the user's `report.pdf.part` was deleted; mutations: the old pre-delete and dropping the failure cleanup each redden a test; four leftover-temp assertions repointed at the real name (they had gone vacuous), + a failed-replace test | FIBR-0013 D1 (agrees); security-model.md INV-7 note (amended) |
| P4 empty render written and reported as exported | | | | FIBR-0013 INV-2 |
| P5 ASCII year beside a QLocale month; chart axes not localised | | | | FIBR-0013, design.md i18n |
| P6 slice and legend labels may render rich text | | | | |
| P7 comments cite the withdrawn Dark theme and an unrun exec() | | | | |
| P8 FIBR-0013 D1 describes `sections` + `today` fields | | | | FIBR-0013 D1 |

- **cited_by:**
- **swept:**
- **collateral:**
- **surfaced:**
- **out_of_scope:**
- **falsified:**
