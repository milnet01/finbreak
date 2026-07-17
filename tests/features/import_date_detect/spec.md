# Feature test contract — statement date-format auto-detect + confirm (FIBR-0146)

Enforces `docs/specs/FIBR-0146.md`. finbreak stops making a person type
programmer date codes: the import wizard reads the actual dates, **guesses** the
layout, offers a plain-English picker with a **live preview**, and shows a
friendly message when a row can't be read — so a bank whose dates aren't
`%Y-%m-%d` imports cleanly instead of failing every row with raw `strptime`
text (the external Windows tester's 0 new · 0 duplicate · 165 error bug).

Four layers, all pure/headless except the wizard round-trips (pytest-qt
`qtbot`). Every vault uses `tmp_path`; fixtures are tiny in-repo strings — no
real statements, no network (testing.md § 6).

| INV | Assertion |
|-----|-----------|
| INV-1 | **Never a silent wrong-day.** Auto-detect only *pre-selects* a format in the visible picker; the live preview (D6) shows the parsed dates before any write, and detection commits nothing (`test_regression_end_to_end…` imports only on the explicit Import press). When two formats are equally consistent (every day ≤ 12), the picker takes the fixed-order winner **and** flags the ambiguity (`test_ambiguity_nudge_shows_then_clears…`). |
| INV-2 | **Pure, deterministic, clock-free detector.** `detect_date_format` reads only `samples` + `KNOWN_DATE_FORMATS`: same input → same guess regardless of order (`test_determinism…`); a poisoned `date.today()` is never called (`test_clock_free_far_past_and_far_future`); ties break by the **fixed list order** (`test_ambiguous_all_days_le_12_winner_is_fixed_order`, `test_known_formats_are_ordered…`). No year window — `%Y`/`%y` widths separate 2- and 4-digit years (`test_two_and_four_digit_year_cleanly_separated_no_guard`). |
| INV-3 | **No raw parser internals reach the UI.** A per-row date failure surfaces `could not read the date "<raw>"` (or `the date cell is empty` for a blank cell), never `does not match format` or a `%`-token — asserted for a normal junk cell and a `50%` cell that embeds a literal `%` (`test_csv_bad_date…`, `test_csv_percent_in_junk…`, `test_csv_empty_date_cell…`). The amount/`parse_transaction` messages are unchanged (`test_csv_amount_error_text_unregressed`). |
| INV-4 | **Capability preserved; no saved layout lost.** The picker covers every known layout plus a **"Custom…"** raw-pattern field; a saved exotic format (`%Y.%m.%d`) round-trips through Custom — selected, filled verbatim, **and revealed** — and the produced mapping equals the stored format, never rewritten (`test_custom_roundtrip…`). A matched profile's format is authoritative and clears the ambiguity flag (`test_matched_profile_is_authoritative`). |
| INV-5 | **i18n-clean.** The added strings ("Custom…", the preview label + fallbacks + ambiguity nudge, the banner) go through `tr()`; the combo entry **data** values are the fixed `%`-patterns, not the display example text (`test_added_strings_are_tr_wrapped_and_data_is_fixed_tokens`). |
| INV-6 | **No new dependency; existing pipeline untouched.** Detection is stdlib `datetime`/`csv` only and feeds the unchanged `ColumnMapping` → `CsvImporter.parse` → `preview` path — a valid row still parses (`test_csv_valid_row_still_parses_INV6`); the whole `import_`/`ofx`/`pdf`/`standard_bank` suites stay green. The empty-format `strptime("", "")` → 1900-01-01 trap is closed at `_validate_mapping` (`test_validate_mapping_rejects_empty_date_format`, `test_empty_date_format_is_the_1900_trap`). |

## Layers

* **Detector** (`detect_date_format`, no Qt): day>12 disambiguation (the tester's
  shape), ISO + slashed-ISO, month-first US, dotted both directions + dotted
  ambiguity, 2-digit ambiguity, named-month variants, no-guard width separation,
  no-match/blank → `None`, one-junk-row tolerance, determinism, clock-free.
* **Importer** (`CsvImporter.parse`): friendly per-row date error, empty-cell
  message, amount-error text unregressed, valid-row anchor.
* **Service** (`ImportService._validate_mapping`): empty/blank date format
  rejected with `choose a date format`; the 1900-01-01 trap documented.
* **Wizard** (`ImportWizardWidget`, `qtbot`): auto-detect seeds the picker;
  end-to-end day-first import lands rows; live preview reads dates + flips on a
  wrong format; ambiguity nudge shows then clears on a manual pick; the two
  preview fallbacks (blank / junk column); short-column clean branch; preview
  refreshed exactly once per fire (single owner); Custom round-trip; empty-Custom
  rejected on Next; matched-profile authoritative; whole-import banner (D7);
  date-column change re-detects off column 0; `tr()` + fixed-token data (INV-5).
