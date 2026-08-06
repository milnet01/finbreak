# tests/features/standard_bank_pdf — test contract

Enforces `docs/specs/FIBR-0050.md` (cold-eyes converged, 9 loops),
`docs/specs/FIBR-0190.md` (Family E, 4 loops) and
`docs/specs/FIBR-0252-standard-bank-row-errors.md` (per-row errors reach the
caller, 5 loops). The Standard Bank text-layer
reader: detection, the five family line-grammars, budget-view signs, US/European
numbers, year inference, region bounding, the all-or-nothing integrity checksum,
and the wizard round-trip (skips mapping like OFX).

**Three specs, three `INV-N` numberings.** A bare `INV-N` below means
**FIBR-0050's**; FIBR-0190's and FIBR-0252's are qualified at the citation site
(`FIBR-0190 INV-3`, `FIBR-0252 INV-1`), the same convention
`tests/features/auto_update/spec.md` uses for `FIBR-0131 INV-1`. The
qualification matters here: FIBR-0050's INV-1…INV-14 collide with every one of
FIBR-0252's six.

**Two gates, not one.** The all-or-nothing checksum above refuses a whole
statement whose running balance does not reconcile. Alongside it runs a
**degrade-per-row** channel (FIBR-0216): a row `parse_transaction` rejects — the
legitimate printed `0.00` line, a garbled date — becomes a `RowError` instead of
aborting the parse, and `parse` returns those errors beside the drafts for the
preview to show (FIBR-0252 INV-1). Only drafts feed the balance gates; an error
row carries no money.

**Fixtures are 100% SYNTHETIC** — `tests/features/standard_bank_pdf/fixtures/*.pdf`
are `reportlab`-generated blobs with invented merchants/amounts and a fake account
number (`00 000 000 0`); `reportlab` stays a probe/authoring tool, never a project
or test dependency. Encrypted variants are produced in-test with `pikepdf`. No real
statement, account number, or ID number appears anywhere.

**No generator script is committed** — an in-tree one would be a `reportlab` entry
point, which the rule above forbids. To author or extend the Family E set, the
recipe is `docs/specs/FIBR-0190.md` **§ 4.6** (page split, which page reprints the
column header, which shapes each row must carry) together with **§ 4.2** — a
transaction page needs a money-bearing line directly *above* its column header, or
`_table_region`'s "header carries no money token" guard picks the wrong line and
the real header folds into the previous row's description. `family_a_zero_fee.pdf`
(the FIBR-0252 error-channel fixture) has its own recipe:
`docs/specs/FIBR-0252-standard-bank-row-errors.md` **§ 4.2**, which prints the
whole thirteen-line page plus an **ablation table** saying which of those lines
are load-bearing — four are decoration, and the waived-fee line is the fixture's
entire reason to exist (drop it and four invariants pass while proving nothing).

Coverage map:

- **Pure helpers (no PDF):** `_detect_number_format` US/EU (INV-8/8a); `_parse_amount`
  trailing/leading/`R` signs; `_infer_years` Dec→Jan + Nov→Feb-gap rollover (INV-9a);
  `_split_credit_card_line`; `detect_standard_bank` → family / `None` (INV-2/2a),
  each family by its own signature + C-wins-over-A detection order
  (D4; C→D→E→B→A since FIBR-0190);
  `_span` B/D quiet-month fallback to the statement "Date" line (D8);
  `_parse_family_a` keeps an embedded `MM DD` in the description (INV-3a);
  `_parse_family_c` keeps an embedded price, amount = last token (INV-6a), and folds
  a zero-date continuation line into the prior segment's description while skipping a
  section header (INV-10).
- **`parse()` per family** (INV-1/3/4/5/6): Current (US, closing), RCP (European +
  rollover), Home Loan (ISO, unsigned balance vs signed closing), Money Market
  (`R`-prefixed, page-2 interest schedule region-excluded), credit card
  (de-interleave + section flip) — dates asserted alongside amounts.
- **Integrity (INV-7b/11):** the per-row gate (a corrupted amount) and the
  completeness gate (rows reconcile but the printed closing disagrees) raise
  **distinct** messages; a Home-Loan with its closing removed is all-or-nothing
  (unlike a closing-less Savings, which imports on the per-row gate alone); a
  credit card that doesn't reconcile rides the completeness gate alone; a
  reconciling quiet month returns an empty-draft `ParseResult` with the period.
- **Unstorable balances (INV-11b, FIBR-0224):** the opening and closing figures are
  the only amounts on a statement that never pass through `parse_transaction`, so
  the 64-bit storage bound has to be applied where they are converted. The
  completeness gate cannot stand in for it — `family_b_unstorable_balances.pdf`
  prints an opening and a closing that both exceed `2**63-1` and **reconcile**, so
  it passes every existing gate and used to surface as an `OverflowError` at the
  INSERT (not a class the wizard catches). Legs: the fixture end-to-end; both
  `_verify_checksum` conversions, on deliberately non-reconciling pairs so the
  bound must win over the "didn't add up" message; and `_verify_e_totals`, the one
  path that derives a stored balance from an opening `_verify_checksum` never saw
  (E prints no closing, so that gate early-returns). Only the magnitude half of
  FIBR-0222 is reachable here — `_MONEY` never matches a token containing `e`.
- **Family E — the "Payments / Deposits" current-account layout (FIBR-0190).**
  Eight synthetic fixtures (`family_e_*.pdf`), all rows internally consistent
  except where a leg needs a red one:
  - **FIBR-0190 INV-1/INV-2:** the header block
    `Date Description Payments Deposits Balance` + the legal marker detects as
    `Family.E`; every one of the **14 pre-E fixtures** still detects as the family
    it detected as before (parametrised, one leg per fixture). That leg reads a
    **hand-written** `(filename, expected_family)` list, which no glob touches —
    so its 14 stays 14, and its "as before" stays true of exactly those. The
    post-E addition `family_a_zero_fee.pdf` (FIBR-0252) is in the list too,
    expected to detect as `Family.A`; it has no "before".
  - **FIBR-0190 INV-4/INV-10/INV-11 (end-to-end):** six drafts from
    `family_e_current.pdf` — amounts (the running-balance **delta**, money-out
    negative despite the column being headed *Payments*), `occurred_on` asserted
    alongside them (`_dmy_iso` re-assembles the date from three capture groups, so
    a day↔year transposition is silent without this), the wrapped description
    folded whole, and the coverage span from min/max parsed date (E prints no
    period line, D7).
  - **FIBR-0190 INV-3 (grammar):** `_E_ROW` accepts a description containing an
    embedded 2-decimal price, a masked card number, and an `R`-prefixed reference;
    accepts a **leading**-minus balance and an unsigned money-in row; and
    **rejects** a trailing-minus balance (D3). A region line the fold accepts under
    `dmy_lead=True` but the grammar rejects **raises** `_MISPARSE` — never a
    `continue`, which is how a mis-parse becomes a silent under-import.
  - **FIBR-0190 INV-9:** `_looks_like_row` is unchanged without the keyword — the
    `dmy_lead` widening is opt-in, so no Family-A continuation line starting
    `12 Jan 25` can be promoted to a row (D5).
  - **FIBR-0190 INV-5:** `family_e_no_opening.pdf` raises `_parse_family_e`'s
    **suffixed** opening-balance message (asserted verbatim — `parse` runs the
    family parser before `_capture_opening`, so the un-suffixed one is reachable
    only on a zero-row statement).
  - **FIBR-0190 INV-6/INV-7 (completeness):** each printed column total is verified
    **independently**, on magnitudes in minor units. Red fixtures for **both**
    halves (`family_e_totals_fail.pdf`, `family_e_deposits_fail.pdf`), each
    printing one mismatched total and untouched rows — so the per-row chain cannot
    be what fails, and an implementation gating on *both* totals being present
    would import them cleanly. The message is **distinct** from the per-row and
    running-balance ones (asserted verbatim). Neither total printing still imports
    (`family_e_no_totals.pdf`, D9).
  - **FIBR-0190 INV-8 (`closing_balance_minor`):** supplied as `opening + Σ` only
    when **both** totals printed and verified; `None` when neither prints, and
    `None` on `family_e_one_total.pdf` — a lone total that *matches*, which imports
    but corroborates only half the sum (D10).
  - **FIBR-0190 D6:** a text-**extraction** leg asserts none of the 15 pre-E
    fixtures contains `statement opening balance` — the premise that makes widening
    `_anchor_balance` / `_capture_opening` globally safe. It must extract, not grep:
    a repo search cannot read a binary PDF's text stream. This leg is parametrised
    over a **glob**, so it picked up `family_a_zero_fee.pdf` on its own: 14 → 15.
    (The constant keeps the name `_PRE_E_FIXTURES` even though it now holds a
    post-E fixture — renaming it is churn across two files for no behavioural
    gain.)
- **Per-row errors reach the caller (FIBR-0252).** `family_a_zero_fee.pdf` — a
  Family A page carrying `SERVICE FEE WAIVED 0.00` between two ordinary rows, so
  it reconciles and previews rather than being refused.
  - **FIBR-0252 INV-1/INV-2/INV-3:** `parse` returns `[(2, "amount must be
    non-zero")]` beside drafts at rows `[1, 3]`, with the span, closing balance
    and amounts unmoved. The **boundary** leg: the existing
    `test_FIBR0216_…degrades_instead_of_aborting_the_statement` calls
    `_parse_family_a` directly, which is why it stayed green for the whole life
    of the defect. The corpus cannot pin INV-3 — none of those fixtures carries
    a `RowError`, so they pass identically either side of the change.
  - **FIBR-0252 INV-5:** the wizard preview interleaves the errored row in file
    order (located by cell content, not table index — `_fill_preview_table`
    sorts) and the summary reads `· 1 error`.
  - **FIBR-0252 INV-6:** a text-**extraction** allow-list leg proves the fixture
    is synthetic. It is the only check there is: the repo-wide corpus guard
    skips binary `.pdf` bytes. Scoped to **customer and account** data, not "bank
    data" — the legal marker is a real published company registration number and
    detection cannot fire without it.
  - **FIBR-0252 INV-4 lives next door**, in `tests/features/batch_import/`.
- **Number format (INV-8):** detection is scoped to the transaction **region** — a
  European-format token in the footer (outside the region) does not trip the
  "mixes number formats" refusal (`mixed_footer_a`).
- **Security (INV-12):** an encrypted fixture decrypts in memory with the password;
  a wrong password raises `PasswordError`; the **attempted** password (the value
  that flows through `parse`) appears in no log record (`caplog`) and no exception
  message.
- **Bounds (INV-14):** monkeypatching `standard_bank._MAX_PDF_ROWS` /
  `_MAX_PDF_PAGES` small refuses an over-large statement.
- **Wizard round-trip (INV-13, qtbot):** picking a recognised SB PDF lands on
  **preview** (no map step / table chooser); Import inserts the rows + period; a
  second import previews all-duplicate and adds zero; a **locked** SB statement
  prompts (fake `PasswordDialog`), decrypts, then previews; a non-reconciling SB
  statement surfaces the friendly `ValueError` as a shown message and stays on the
  pick step (never a crashed Qt slot); a **corrupt** file that passes the `%PDF-`
  sniff (pikepdf raises `PdfError`, not a `ValueError`) also surfaces a message
  rather than crashing the slot.
