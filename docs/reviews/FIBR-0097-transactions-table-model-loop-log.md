# FIBR-0097 — review-contract loop log

The review record for `docs/specs/FIBR-0097-transactions-table-model.md`.
`review-contract` writes one row per loop as it closes.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 2026-10-19 | 2 | 0 | 2 | 2 | 2 | 6 findings, 6 verified / 0 dismissed, all 6 fixed. Both lanes held every question. Both found: § 4.2's `sorted()` against § 4.3's shared list sorted in place; "ties keep the service's order", where a stable sort keeps the current order (Qt probe); INV-3 and INV-4 cannot be seen red; the perf test's 20,000/2,000 ratio under 4 is unreachable (measured: about 11 with the fill removed). Lane a alone: `setModel`'s place before the header calls. Lane b alone: `_sort_keys` has no sort-key role to read. Two open questions resolved clean (`_Render` is covered by INV-5's scan; other suites are covered by § 7's migration rule). No unrunnable region. Gated span: the whole document, created in a6aa76c. Loop 2 dispatched. |
| 2 | 2026-10-19 | 2 | 0 | 1 | 0 | 2 | 3 findings, 2 verified / 1 dismissed, both verified fixed. Both lanes held every question. Both found: INV-5's red check (a `clear_rows` that empties `_master` alone, or skips the model) is already caught by today's scan, so it cannot show the widening works. Lane d alone: INV-3's amounts had no unit, and in the minor units the test helper takes their text order matches their key order. Dismissed [Q2]: § 4.3 does not contradict INV-5 on `_Render`; INV-5 and its scan already require it dropped. Measured: the gate does run `-m "not perf"` (`scripts/ci-local.sh`), and a 5-section header blob restores into a 6-column `QTableView` with 6 sections, none hidden. Six open questions resolved clean. Previous-loop share: 1 of 2 (the § 7 half of the INV-5 finding sits in a sentence loop 1 rewrote; the defect predates it). Loop 3 dispatched. |
