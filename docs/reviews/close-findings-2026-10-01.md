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
| B2 auto-lock test misses map-step legs | | | | |
| B3 picker text unasserted | yes — test checks id and OK only | fixed | no text check → asserts combo reads "— pick one —"; mutation: blank placeholder reddens it | |
| B5 cancel test emits done() | | | | |
| B8 huge exponent at parse only | yes — parse_transaction only | fixed | row-level only → CsvImporter.parse: one RowError, neighbours import; mutation: dropping the Overflow catch aborts the file with decimal.Overflow | |
| B10 private checksum with hand-built drafts | | | | |

User decisions 2026-10-01: B6 reuse an answer within the batch for an
identical header, named or not; B11 fold runs of inner whitespace in the
uniqueness key.

- **cited_by:**
- **swept:**
- **collateral:**
- **surfaced:** B11 — a vault already holding two names that now share a
  key refuses any edit to either until one is renamed (the same held for
  accented names after FIBR-0328). Accepted as rare; not fixed.
- **out_of_scope:**
- **falsified:**
