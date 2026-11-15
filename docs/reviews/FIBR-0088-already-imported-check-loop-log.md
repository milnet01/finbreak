# FIBR-0088 — review-contract loop log

The review record for `docs/specs/FIBR-0088-already-imported-check.md`.
`review-contract` writes one row per loop as it closes.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-11-15 | 2 (neutral-lane, every lane held every question) | 0 | 2 | 1 | 3 | Verified 6, fixed 6, dismissed 0. Q2: `add` now upserts `imported_at` so the question names the latest import (INV-8 test extended); the question is shown with `show_modal` (FIBR-0065 D1), not a blocking `QMessageBox`. Q3: OFX fan-out records carry `source_sha256`. Q4: INV-1 runs through the wizard and the batch, INV-2 uses a second distinct file, INV-9 drops the table before setting v16. Both lanes found the INV-2, INV-1, upsert, modal and migration-fixture defects; 1b found the modal one too. Two open questions resolved clean: `format_timestamp` parses `datetime.now(UTC).isoformat()` (measured), and where the question sits among `_select_file`'s resets is the builder's call. |
