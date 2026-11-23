# FIBR-0283 — review-contract loop log

The review record for `docs/specs/FIBR-0283-bank-field-on-accounts.md`.
`review-contract` writes one row per loop as it closes.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-11-15 | 2 | 1 | 1 | 0 | 2 | 4 verified (both lanes found the Q1 and the INV-5 Q4), 0 dismissed, 4 fixed. Q1: § 7 omitted `test_migration_v13.py`'s exact `accounts` column-set assert; now a grep finds every such test. Q2: the account picker is also the Statements tab's *Change account*; § 4.3 and § 9 now say so. Q4: INV-5 now tests the repository default too; INV-9 is written after `account_label` exists. Both lanes held every question. Loop 2 dispatched. |
| 2 | 2026-11-15 | 2 | 0 | 0 | 0 | 2 | 2 verified, 0 dismissed, 2 fixed, both on INV-11's test: one lane found no assert names which column is Bank; the orchestrator, verifying it, found no Reset-layout leg. One lane returned no findings; its open questions and the other's, settled by grep, raised nothing. Both lanes held every question. **Cap reached (2 of 2, rule 14)**: these two fixes are read by no lane. Calm cap: 0 of 2 final-loop findings landed on text this run wrote. No second share: the spec is new, so the armed span is the whole document. Status set to accepted. |
| impl | 2026-11-16 | none | — | — | — | — | Not a review loop: no reviewer was dispatched. Fold-back from the build's review-code pass. § 4.3 gains a seventh site, the wizard's `_account_name()`: the PDF-password prompt reads the preview combo, so it already showed the label. INV-7 now covers a blank bank, which the label treats as none. INV-6 and § 4.2 now fix which of two stored spellings wins (the earliest-recorded). Each change has a test. |
| impl | 2026-11-23 | none | — | — | — | — | Not a review loop: no reviewer was dispatched. FIBR-0087 appended an eighth Account field, `currency`; INV-3 gains a pointer to FIBR-0087's INV-3. No rule here changed. |
