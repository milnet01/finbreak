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
| C4 startup-error test calls the hook by hand | | | | |
| C6 Windows apostrophe: command text only | | | | |
| C10 month name read from HTML, not the PDF | | | | |
| C12 failed install: no test | | | | |
| C13 check for updates twice: no test | | | | |
| C14 Quit / Ctrl+Q save layout: no test | | | | |
| C15 auto-lock during reassign / move-under | | | | |
| C16 PDF row dates follow the date format: no test | | | | |

- **cited_by:**
- **swept:**
- **collateral:**
- **surfaced:**
- **out_of_scope:** docs/specs/FIBR-0127.md cites "`services/pdf_export.py:99` (dark PDF
  theme)" — stale since FIBR-0217, before this run; left.
- **falsified:**
