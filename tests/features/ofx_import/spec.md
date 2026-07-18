# tests/features/ofx_import — test contract

Conformance tests for **FIBR-0008 (P06 OFX import)**. The authoritative
design contract is [`docs/specs/FIBR-0008.md`](../../../docs/specs/FIBR-0008.md);
this file is the tiny per-feature test contract (global rule § 14 excludes it
from `/cold-eyes`).

The pure `OfxImporter` (OFX bytes → the same `ParseResult` a `CsvImporter`
produces, one per statement), the `ImportService` reuse seam
(`_preview_from_result` / `preview_result` / `read_file_bytes`), the shared
`importers/base.py` value objects, and the wizard's OFX branch. Headless layers
are tested directly; the wizard round-trip (INV-7) uses the pytest-qt `qtbot`
fixture. Every on-disk vault uses `tmp_path`; OFX fixtures are tiny in-repo SGML
strings — no real financial data, no network (testing.md § 6). The vault fixture
is the FIBR-0007 first-run vault (already at v4 — no migration this phase, D9).

| INV | Guarantee (see the spec for the full text) |
|-----|--------------------------------------------|
| INV-1 | OFX bytes → `(OfxAccountInfo, ParseResult)` per statement; signed `<TRNAMT>` passthrough (1a), DTPOSTED→ISO (1b), payee-else-memo description (1c), over-precise amount → `RowError` (1d) |
| INV-2 | Coverage period is the embedded DTSTART→DTEND; missing span (`''`) falls back to the drafts' min/max, `None` when zero drafts |
| INV-3 | Post-parse `parse_transaction` rejections (zero amount, blank description) are collected `RowError`s; valid siblings still import |
| INV-4 | Malformed / statement-less / structurally-bad-transaction input → one friendly `ValueError` (D15) |
| INV-5 | A multi-account OFX surfaces **all** statements (id + type), none dropped |
| INV-6 | OFX feeds the same `ImportService` write pipeline: dedup + atomic period record; re-import adds zero |
| INV-7 | Import-wizard OFX round-trip (7a–f, `qtbot`): skip mapping, preview, import, all-duplicate re-import, multi-account chooser, quiet-month |
| INV-8 | No network/secret/schema regression; OFX field text stored inert (INV-5a) |
| INV-9 | The FIBR-0007 CSV import suite stays green (reuse, not fork) — the `ParseResult`/`RowError` relocation preserves both import sites |
| INV-10 | OFX is resource-bounded: over-`_MAX_IMPORT_BYTES` file and over-`_MAX_OFX_TRANSACTIONS` file each refused with a `ValueError` |
| INV-11 (FIBR-0042) | A timezone-bearing `<DTPOSTED>`/`<DTEND>` keeps its **as-posted local calendar date** (`_LocalDateOfxParser` neutralises the printed offset): a negative-offset evening (`20260105230000[-5:EST]`) stays `2026-01-05` (not the UTC-rolled `2026-01-06`), a month-boundary `<DTEND>` stays in-month (period not extended into the next month), and a positive-offset early morning does not roll backward. Date-only values (all other fixtures) are unchanged. |
