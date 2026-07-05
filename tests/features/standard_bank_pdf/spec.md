# tests/features/standard_bank_pdf — test contract

Enforces `docs/specs/FIBR-0050.md` (cold-eyes converged, 9 loops). The Standard
Bank text-layer reader: detection, the four family line-grammars, budget-view
signs, US/European numbers, year inference, region bounding, the all-or-nothing
integrity checksum, and the wizard round-trip (skips mapping like OFX).

**Fixtures are 100% SYNTHETIC** — `tests/features/standard_bank_pdf/fixtures/*.pdf`
are `reportlab`-generated blobs with invented merchants/amounts and a fake account
number (`00 000 000 0`); `reportlab` stays a probe/authoring tool, never a project
or test dependency. Encrypted variants are produced in-test with `pikepdf`. No real
statement, account number, or ID number appears anywhere.

Coverage map:

- **Pure helpers (no PDF):** `_detect_number_format` US/EU (INV-8/8a); `_parse_amount`
  trailing/leading/`R` signs; `_infer_years` Dec→Jan + Nov→Feb-gap rollover (INV-9a);
  `_split_credit_card_line`; `detect_standard_bank` → family / `None` (INV-2/2a);
  `_parse_family_a` keeps an embedded `MM DD` in the description (INV-3a);
  `_parse_family_c` keeps an embedded price, amount = last token (INV-6a).
- **`parse()` per family** (INV-1/3/4/5/6): Current (US, closing), RCP (European +
  rollover), Home Loan (ISO, unsigned balance vs signed closing), Money Market
  (`R`-prefixed, page-2 interest schedule region-excluded), credit card
  (de-interleave + section flip).
- **Integrity (INV-7b/11):** a corrupted-amount fixture raises the friendly
  `ValueError`; a closing-less Savings statement imports on the per-row gate alone;
  a reconciling quiet month returns an empty-draft `ParseResult` with the period.
- **Security (INV-12):** an encrypted fixture decrypts in memory with the password;
  a wrong password raises `PasswordError`; the password appears in no log record
  (`caplog`) and no exception message.
- **Bounds (INV-14):** monkeypatching `standard_bank._MAX_PDF_ROWS` /
  `_MAX_PDF_PAGES` small refuses an over-large statement.
- **Wizard round-trip (INV-13, qtbot):** picking a recognised SB PDF lands on
  **preview** (no map step / table chooser); Import inserts the rows + period; a
  second import previews all-duplicate and adds zero.
