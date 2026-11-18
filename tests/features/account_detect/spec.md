# Feature test contract — statement account auto-detect (FIBR-0086)

Enforces `docs/specs/FIBR-0086-account-number-auto-detect.md`: reading the account
number a statement prints about **its own** account, matching it to a configured
account, and pre-selecting that account in the import wizard without ever
committing on its own.

The whole feature exists to stop a statement landing under the wrong account, so
every row below is either "reads the right number" or "declines to guess".

| # | INV | Assertion |
|---|-----|-----------|
| 1 | INV-1 | **Family C yields nothing.** `extract_account_number(lines, Family.C)` returns `None` even when the page carries a well-formed `account number` label. The number a credit-card statement labels is the **debit-order** account that pays the card, not the card (spec §2.3), and it normalises to exactly the current account's — so the obvious implementation files every card statement under the current account. The guard is asserted against a **direct call**, not through `StandardBankImporter.parse`, so moving it to the call site alone goes red. |
| 2 | INV-2 | **Only the header is read.** A family-A page whose transaction rows carry a *foreign* account number extracts the one above the column header, not the one in the rows. Current-account statements really do print the home loan's number inside a transaction row (§2.4), so a whole-page scan misfiles. |
| 2a | INV-2a | **The capture stops at a column gap.** `Account Number 44 555 666 7   2024 03 27` yields `44 555 666 7`, not the date column merged onto it. The regex allows a *single* space between digits, so it ends at a two-space column boundary. |
| 3 | INV-3 | **Two matches select nothing.** `match_account` returns `account_id is None` and `outcome == "ambiguous"` when two accounts normalise to the statement's number, with both ids in `candidates`. Returning the first would silently pick one of two equally valid accounts. |
| 4 | INV-4 | **Empty never matches.** An account with a `NULL` `account_number` matches nothing, and a statement number that normalises to `""` matches nothing — the `"" == ""` trap that would file every statement under every unnumbered account. |
| 5 | INV-5 | **Normalisation ignores grouping and padding.** `11 222 333 4`, `112223334`, `000112223334` and `00-112-223-334` all map to one key; `no digits` maps to `""`. A bank that pads its own header differently between statements still matches its own account. |
| 6 | INV-6 | **The seam is additive.** Covered by the full gate, not a test here: `source_account` is appended **last** on `ParseResult` with a default, so every existing positional construction is untouched. A regression shows up as many unrelated tests failing, which is the point. |
| 7 | INV-7 | **A match pre-selects; it never commits.** Driving a matched import leaves the wizard on the preview step with nothing written — the user still presses Import. Auto-detect changes the default, not the flow. |
| 7a | INV-7a | **The preview is built for the account on screen.** `wizard._preview.account_id == wizard._confirm_account_combo.currentData()` after a matched import. This is the money row: seeding the combo *after* the preview under a `QSignalBlocker` suppresses `currentIndexChanged`, so `retarget` never runs and `commit_import` persists a preview aimed at the previous account — the wizard would read "Matched account number …" over transactions landing somewhere else. Only the §4.5 ordering (match → seed → preview) prevents it. |
| 8 | INV-8 | **No real corpus number is in the tree.** Walks `git ls-files`, normalises each file's digit runs the way `normalise_account_number` does, and fails on any real key. Reads the keys from `FINBREAK_CORPUS_NUMBERS` and **skips** when unset, so the numbers it guards against are never themselves committed. Normalising the *haystack* is the point: everything this feature stores and displays is as-printed, so the likeliest leak spelling is `11 222 333 4`, which does not contain the substring `112223334`. |
| 9 | INV-9 | **A masked number never matches.** `SourceAccountHint("xxxx1234")` against an account numbered `1234` yields `no_number`, not `matched`. The check is on the **raw** value, before normalisation — normalisation strips non-digits, so `xxxx1234` becomes `1234` and would match by accident, implementing the trailing-digit matching the spec deliberately declined to build. |
| 10 | INV-10 | **A hint with no bank ignores stored banks** (FIBR-0284). Two same-number accounts at two banks stay `ambiguous`. Comparing a `None` hint bank would drop every banked account. |
| 11 | INV-11 | **Another bank's account is never selected.** A Standard Bank hint picks the same-number account at Standard Bank over one at another bank; with only the other bank's, the outcome is `wrong_bank` and nothing is selected. |
| 12 | INV-12 | **An unrecorded bank is unknown, not different.** An account with no bank stays a candidate, and an account at the statement's bank does not outrank it — both may be the statement's, so two of them are `ambiguous`. |
| 13 | INV-13 | **Banks compare folded.** A stored `standard  BANK` matches a `Standard Bank` hint (`text.fold_name`). |
| 14 | INV-14 | **The Standard Bank reader names its bank.** Every hint `extract_account_number` returns carries `STANDARD_BANK`, which is in `KNOWN_BANKS`. Without it the bank check never fires. |
| 15 | INV-15 | **`wrong_bank` keeps the pick.** The wizard leaves the destination at the pick step's account and shows the label and the Create button. |
| 16 | INV-16 | **Create pre-fills the bank.** From the wizard and from batch import's review screen, accepting the dialog without touching Bank stores the statement's bank. |
| 17 | INV-17 | **A drop leaves no guess.** Where the bank rule dropped an account, the number is shared across banks; a lone survivor with no bank recorded is `ambiguous`, since the dropped one may be the statement's own, its bank spelt `SBSA`. |
| 18 | INV-18 | **Create claims only a real match.** After Create, "Matched account number …" shows only when this statement's hint matches the new account; an edited bank or number gets "future statements will not file themselves". |

## Fixtures

**Every fixture number is invented** (INV-8). The real corpus lives outside the
repository and is read only in a scratchpad; no test here contains a value from a
real statement. The stand-ins keep the *structural* relationships the design turns
on — notably that the family-C label's number normalises to the family-A one.

Each `test_extract.py` fixture carries a line `_table_region` recognises as its
family's column header. Without one, `_table_region` returns `slice(0, 0)`, the
header slice is empty, and the test would pass or fail for a reason unrelated to
what it claims to lock. Fixture shape: header lines → column-header line →
transaction rows.
