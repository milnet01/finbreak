# FIBR-0467 — review-contract loop log

The review record for `docs/specs/FIBR-0467-home-loan-sign.md`.
`review-contract` writes one row per loop as it closes.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-11-11 | 2 × `review-lane` via `neutral-lane`, cold, identical brief, every lane held every question | 2 | 0 | 0 | 0 | **Verified 2 / fixed 2; one dismissed.** One Q1 came from building the packet: § 4.3's `.pdf` condition assumed a period's rows all came from its file, but `commit_import` reuses an existing span's period and keeps its first filename. So a CSV or OFX import over a Family B span is negated wrongly, and a B import over a CSV span is missed. § 6 now lists that case, and the "one wrong-positive case" sentence is gone. Both lanes found the second Q1: § 7 said the `prose_checks` guard files `loan_sign/` itself. Measured: with the directory present, `test_INV2_every_suite_directory_is_classified` fails until `_NO_PROSE` lists it, and § 7 now says so. **Dismissed:** INV-5's "or the version bump comes before the data change". Inside one `owned_transaction` a failure rolls back both, so no test can see the order; the clause was false and is deleted, which changes no test. Five lane open questions resolved clean: the selector's column names exist, reporting and alerts read sign only (§ 6 covers the totals shift), the fixture's unsigned closing is not this item's, and the line count differed by a trailing newline. |
