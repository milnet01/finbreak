# already_imported — test contract (FIBR-0088)

The contract is [`docs/specs/FIBR-0088-already-imported-check.md`](../../../docs/specs/FIBR-0088-already-imported-check.md).
This suite locks the file fingerprint and the question it drives:

- **INV-1:** the recorded fingerprint is the SHA-256 of the file's bytes on
  disk — CSV, OFX and a locked PDF, through the wizard and the batch.
- **INV-2:** it is written in the commit's own transaction, on a reused span
  too, and a rolled-back commit writes none.
- **INV-3:** the wizard and the batch both record it.
- **INV-4:** deleting the statement deletes its fingerprints.
- **INV-5:** the question comes before any CSV or PDF parse or password
  prompt, and Cancel changes nothing.
- **INV-6:** Import again imports exactly as a first pick, dedup included.
- **INV-7:** the match is on content, never the file name.
- **INV-8:** the question names the latest import, in the user's formats.
- **INV-9:** `test_migration_v17.py` — the v16 → v17 step is atomic and runs
  once.
- **INV-10:** no fingerprint reaches the log.
- **INV-12:** a partly imported multi-statement OFX says how many of its
  statements were imported.
- **INV-13:** "latest" is the order of imports, not of clock readings.
- **INV-14:** the wizard routes a file by the bytes it read.

INV-11 is `tests/features/batch_import/test_batch_import.py::test_INV10_already_imported_is_recomputed_both_ways`.
