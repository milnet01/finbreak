# tests/features/pdf_import — test contract

Conformance tests for **FIBR-0009 (P07 PDF statement import)**. The authoritative
design contract is [`docs/specs/FIBR-0009.md`](../../../docs/specs/FIBR-0009.md);
this file is the tiny per-feature test contract (global rule § 14 excludes it
from `/cold-eyes`).

The pure-ish `PdfImporter` extractor (PDF bytes → grouped candidate tables →
CSV text feeding the **existing** CSV pipeline verbatim), the in-memory `pikepdf`
decrypt of locked PDFs, the opt-in remembered password (v5 nullable column +
credential accessors), the `password_dialog`, and the wizard's PDF branch.
Headless layers are tested directly; the wizard round-trips (INV-7) use the
pytest-qt `qtbot` fixture with an injected fake `PasswordDialog` (a live modal
would block). Every on-disk vault uses `tmp_path`; the fixture PDFs are committed
gridded blobs (generated once with reportlab, which stays **probe-only** — it
cannot exist in the Python-free self-test bundle); the encrypted variants are
produced **in-test** by `pikepdf`-encrypting a fixture. No real financial data,
no network (testing.md § 6).

**Fixture shape note (deviation from the spec's Deliverable 8 pinned header):**
the committed `single_table.pdf` / `two_table.pdf` / `two_page_repeated_header.pdf`
carry a `Date, Description, Money Out, Money In` header (Money Out=debit, Money
In=credit; dates DD/MM/YYYY), **not** the spec's `Date, Money Out, Money In`. A
`Description` column is required: the reused CSV pipeline rejects a blank
description (`parse_transaction`), so a description-less table cannot produce a
valid draft and INV-1/INV-7e (the money-contract end-to-end) would be untestable.
The three data rows are preserved, so the cap tests still monkeypatch
`_MAX_PDF_ROWS` below 3.

| INV | Guarantee (see the spec for the full text) |
|-----|--------------------------------------------|
| INV-1 | `candidate_tables` extracts a table; `table_to_text` serialises it (None→`""`); the text feeds the **unchanged** CSV path (`read_header`→`match_profile`→`CsvImporter.parse`→`preview`) so a PDF amount obeys the identical money contract. Cross-page tables under a repeated header group into one candidate (D8) |
| INV-1a | A candidate header with **blank + duplicate + a literal `Column 1`** cell serialises to a collision-free unique header (D13) — `signature_for` never raises its duplicate-header `ValueError` |
| INV-2 | Every PDF is normalised **in memory only** through `pikepdf` — an encrypted fixture decrypts+extracts purely from bytes (a), the decrypt+extract writes **no** file to `$TMPDIR`/CWD (b, filesystem sentinel), and the module holds **no** disk-write token (c) |
| INV-3 | A wrong/absent **user** password raises `pikepdf.PasswordError` (the wizard's re-prompt signal) |
| INV-4 | Remembered password is opt-in: the v5 accessor round-trips (`get`/`set_pdf_password`); default is `None` |
| INV-5 | A PDF with no usable table (no ruled table; zero pages → no `IndexError`) → one friendly `ValueError` |
| INV-6 | A multi-table PDF surfaces **all** candidate tables (the summary + the transactions table); header-only (0-data-row) candidates dropped |
| INV-7 | Import-wizard PDF round-trip (7a–f, `qtbot`): pick→map step; encrypted→dialog, wrong-pw re-prompts, Cancel abandons; >1 table→chooser (default largest, switch repopulates combos); profile match auto-fills (single→preview, multi→stay on map); Import inserts + re-import adds zero; remembered pw auto-applies |
| INV-8 | v4→v5 migration adds the **nullable** `accounts.statement_pdf_password` atomically; forward-only; `LATEST_SCHEMA_VERSION == 5`; a first-run vault is v5; the password is **not** on the `Account` object (D6 credential hygiene) |
| INV-9 | PDF is resource-bounded: over-`_MAX_PDF_PAGES` (500) and over-`_MAX_PDF_ROWS` (100 000) each refused with a `ValueError`; a formula-looking cell round-trips as inert `str` |
| INV-10 | PDF feeds the **same** write pipeline as CSV/OFX: import then re-import the same statement adds zero rows |
| INV-11 | No secret logged: a sentinel password appears in **no** log record and **no** exception message; `ImportWizardWidget` defines no `self._*password*` attribute |
