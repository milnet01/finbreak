GROUP B verify-delivery report (finbreak, CHANGELOG [0.1.23]). No project file was edited, and `git status` is clean. All repro scripts are in /tmp/claude-1000/-mnt-Games-Scripts-Linux-finbreak/6301e83f-835e-4e80-9606-ad46d1c3780f/scratchpad/verify-delivery/B/. Every repro ran through `_boot.py`, which points HOME, XDG_* and QSettings at a fresh temp dir, uses a fresh tmp vault, runs offscreen with no network, and asserts `finbreak.__file__` is under src/. The temp vaults were deleted afterwards. HEAD is v0.1.23-85-g52e5162. The pytest runs used `pythonpath=src`, and a bare python with `PYTHONPATH=src` resolved to the same src path.

## B1 CSV column-mapping guess from headers — delivered
Promised: "CSV import now guesses the column mapping from the file's own headers" (CHANGELOG [0.1.23])
Evidence: ran test tests/features/import_column_detect/test_import_column_detect.py (21 passed) + ran repro repro_b1_b7_b8_b9_b11.py.
- Header `Amount,Narrative,Transaction Date` (column 0 is the wrong default for every role) pre-selects Transaction Date / Narrative / Amount: PASS.
- `posting date,DETAILS,Withdrawal,Deposit` pre-selects the Debit/Credit combos: PASS.
- Unrecognised `Foo,Bar,Baz` stays on index 0: PASS.
Against: /mnt/Games/Scripts/Linux/finbreak/src/finbreak/__init__.py 0.1.23 + synthetic CSVs
Path: ImportWizardWidget._select_file → map step → _guess_mapping_combos → combo currentText
Note (outside the spec, not a breach): for a Withdrawal/Deposit file the "Amount style" stays on "Single amount column". The spec excludes the style on purpose. Pressing Preview without switching it gives the user "each field must map to a different column — a column is mapped to more than one role".

## B2 Wizard survives an auto-lock mid-flow — delivered
Promised: "The import wizard no longer crashes if the vault locks itself while you are partway through." (CHANGELOG [0.1.23])
Evidence: ran test tests/features/import_/test_import.py::test_FIBR0327_an_auto_lock_never_escapes_a_wizard_slot (7 params, all PASSED) + ran repro repro_b2.py.
- The repro locks the vault for real, then drives each leg below by clicking or changing the real widgets.
- A sys.excepthook detector recorded anything that escaped a slot. sanity_excepthook.py confirms the detector does catch a VaultLockedError from a slot.
- Legs covered: map Preview (with and without a profile name), date-column change, amount-style change, preview Import, preview Back, destination retarget.
- Result: 7/7 raised nothing.
Against: src/finbreak/__init__.py 0.1.23 + synthetic CSV
Path: wizard step → service.lock() → button/combo slot → no exception out of the slot

## B3 Picker has nothing chosen for an unplaced statement — delivered
Promised: "The account picker no longer arrives with an account already chosen for a statement that has none." (CHANGELOG [0.1.23])
Evidence: ran test test_batch_import_ui.py::test_unplaced_row_opens_a_picker_that_has_chosen_nothing (PASSED) + ran repro repro_b3_b4_b6.py, driving the real AccountPickerDialog. On an unplaced row:
- The picker shows "— pick one —", `selected_account_id()` is None and OK is disabled.
- Pressing Return on the untouched picker leaves the row unplaced.
- OK enables after a real pick.
- Control: a placed row preselects its own account.
Against: src/finbreak/__init__.py 0.1.23 + synthetic CSVs
Path: batch review Account cell → _choose_account → AccountPickerDialog → OK gated

## B4 Batch review Account column works without a mouse — delivered
Promised: "The batch import review's Account column can be used without a mouse." (CHANGELOG [0.1.23]; the body says "Press Return")
Evidence: ran test test_batch_import_ui.py::test_account_cell_is_reachable_without_a_mouse (PASSED) + ran repro repro_b3_b4_b6.py.
- Key_Return and Key_Enter on the Account cell open the real picker.
- Picking an account and pressing OK puts it on the row.
- F2 and Space open nothing. Only Return is promised, so this is not a breach. The event filter handles Return/Enter only (src/finbreak/ui/import_batch.py:431).
Against: src/finbreak/__init__.py 0.1.23
Path: table focus → keyClick Return → eventFilter → _choose_account → picker → cell text

## B5 Cancelling a locked-PDF import leaves no password behind (FIBR-0321) — delivered
Promised: "Cancelling a locked-PDF import no longer leaves the password on the wrong account" (CHANGELOG [0.1.23])
Evidence: ran test test_pdf_import.py::test_FIBR0321_cancelling_restores_the_provisional_accounts_own_password (PASSED) + ran repro repro_b5.py. The repro uses the real PasswordDialog (typed "secret", ticked Remember) and clicks the page's real Cancel button. 4/4 PASS:
- An account with its own password gets it back after Cancel on the preview step.
- An account with no password has none after Cancel on the preview step, and none after Cancel on the map step.
- Retarget-then-Cancel strands nothing on either account.
Against: src/finbreak/__init__.py 0.1.23 + fixture tests/features/pdf_import/fixtures/single_table.pdf, encrypted in memory
Path: _select_file(locked.pdf) → PasswordDialog OK (eager write) → Cancel button → done → _release_stored_pw → AccountService.get_pdf_password

## B6 Same-layout batch asks about columns once (FIBR-0319) — delivered
Promised: "Importing several statements with the same layout now asks about the columns once" (CHANGELOG [0.1.23])
Evidence: ran test test_batch_import.py::test_FIBR0319_an_answered_mapping_settles_the_rest_of_the_batch (PASSED) + ran repro repro_b6_fresh_vaults.py, which drives the real wizard with a fresh vault per variant.
- Input: 3 CSVs sharing the header `When,What,How much`, plus 1 CSV with a different header.
- The map step was shown exactly once for the shared layout (oddn0 only), then once for the different file. All 3 odd files ended `needs_account`.
Against: src/finbreak/__init__.py 0.1.23 + synthetic CSVs
Path: _select_files → scan → _ask_mapping → fill combos + profile name → Preview → answer → next_question
Note: the promise only holds if the user names the layout. With the "Save this layout as… (optional)" field left blank, the same batch asked 3 times (oddu0, oddu1, oddu2). This matches the CHANGELOG's wording ("once you have … given it a name"). But the field is labelled optional, so a user who skips it still gets one question per file.

## B7 Import preview formats amounts like the rest of the app — delivered
Promised: "The import preview shows amounts the way the rest of the app does" (CHANGELOG [0.1.23])
Evidence: ran test test_import.py::test_FIBR0327_preview_honours_the_negative_style_preference (PASSED) + ran repro repro_b7_detail.py.
- Preview cells read '-R 12,345.67' in minus style and '(R 12,345.67)' in brackets style, plus 'R 1,234,567.89'. Each equals `_format_amount(value, "ZAR", style)`.
- The Transactions tab uses the same call: `_format_amount(display, symbol, self._amount_prefs.negative_style)` (src/finbreak/ui/transactions.py:339).
- A 0.00 row is an error row ("amount must be non-zero"), not an amount mis-render.
Against: src/finbreak/__init__.py 0.1.23 + synthetic CSV
Path: wizard → preview table column 2 → _format_amount with the chosen AmountPrefs

## B8 Enormous amount is one bad row, not an aborted import — delivered
Promised: "An enormous amount in a spreadsheet cell is reported as one bad row instead of aborting the import." (CHANGELOG [0.1.23])
Evidence: ran test test_amount_input.py::test_FIBR0222_huge_exponent_is_a_ValueError_not_a_decimal_Overflow (PASSED) + ran repro repro_b1_b7_b8_b9_b11.py.
- `ImportService.preview` on a CSV carrying a 40-digit amount, `1e1000000` and `1e-1000000` gives 3 RowErrors ("amount is too large to store" ×2, fractional-digits ×1) and 2 good drafts.
- A single-huge-row CSV gives 0 drafts and 1 RowError, with no raise.
- The wizard reaches the preview with the 2 good rows.
Against: src/finbreak/__init__.py 0.1.23 + synthetic CSVs
Path: ImportService.preview / wizard._select_file → parse_transaction → RowError

## B9 OFX transaction with no date no longer closes the app — delivered
Promised: "An OFX statement carrying a transaction with no date no longer closes the app." (CHANGELOG [0.1.23])
Evidence: ran test test_ofx_import.py::test_INV4_null_dtposted_is_a_row_error_not_a_crash (PASSED) + ran repro repro_b1_b7_b8_b9_b11.py.
- A mixed statement (valid row + `DTPOSTED 00000000`) gives drafts ['Valid'] plus RowError row 2 "this row has no usable date".
- An all-null statement gives 0 drafts plus 1 RowError.
- The wizard `_select_file` raised nothing in both cases.
Against: src/finbreak/__init__.py 0.1.23 + synthetic OFX
Path: OfxImporter.parse / wizard._select_file → RowError → preview

## B10 Standard Bank: truncated overdrawn statement is refused — delivered
Promised: "Standard Bank import: a truncated statement on an overdrawn account is now refused instead of silently importing short." (CHANGELOG [0.1.23])
Evidence: ran test test_standard_bank.py::test_FIBR0050_INV11_gate_is_signed_for_families_that_print_a_sign (PASSED; it calls the private `_verify_checksum` only) + ran repro repro_b10.py through the public `StandardBankImporter().parse`.
- The repro replaces only the PDF text layer, with text shaped on the synthetic fixtures family_a_current.pdf and family_d_moneymarket.pdf. Everything from family detection onwards is the real code.
- Family A: the complete overdrawn statement (100 → -50 → -100, closing 50.00-) imports both rows. Truncated so the sign flips, it is refused with "this statement didn't add up". The no-rows control is also refused.
- Family D: the truncated sign-flip statement is refused with "didn't add up".
Against: src/finbreak/__init__.py 0.1.23 + synthetic text modelled on the repo fixtures
Path: StandardBankImporter.parse → per-family parse → _capture_closing → _verify_checksum (signed) → ValueError
Caveats:
- The complete Family-D control was refused as "didn't parse cleanly". I guessed D's negative-balance spelling ("-R50.00") for the row, so the D control is unverified. The D refusal still comes from the completeness gate, not the parser.
- Family B (home loan) still compares magnitudes, so a sign-flipping truncation passes there. This exemption is documented (src/finbreak/importers/standard_bank.py `_verify_checksum`, FIBR-0323/0335).

## B11 No two categories/accounts with identical-looking names (FIBR-0328) — delivered
Promised: "You can no longer end up with two categories or accounts whose names look identical." (CHANGELOG [0.1.23]; the body is about accented characters typed two ways)
Evidence: ran tests test_accounts.py::test_FIBR0328_visually_identical_account_names_are_refused + test_categories.py::test_FIBR0328_visually_identical_sibling_names_are_refused (both PASSED) + ran repro repro_b1_b7_b8_b9_b11.py.
- Refused for both accounts and categories: the NFD spelling of "Café float", an upper-case copy, and a copy with surrounding spaces.
- Control: "Cafe float" (no accent) is accepted.
Against: src/finbreak/__init__.py 0.1.23
Path: AccountService.add_account / CategoryService.add_category → name key = NFC(strip).casefold (src/finbreak/text.py:68) → ValueError
Note (outside the CHANGELOG sentence): "Café  float" with a doubled inner space is accepted for both, because the key strips but does not collapse inner whitespace (text.py:68). The import dedup key does collapse it (text.py:52).

Tests that pass but do not check the promise's own sentence:
- **B2** test_FIBR0327_an_auto_lock_never_escapes_a_wizard_slot calls slot methods directly for 7 entry points. It does not cover the map-step Preview/date/style changes or the preview Back button; the repro covered those.
- **B5** test_FIBR0321_cancelling_restores_the_provisional_accounts_own_password emits `widget.done` directly ("what every Cancel reaches") instead of clicking a Cancel button, and never covers the map-step Cancel or an account with no password of its own; the repro did.
- **B6** test_FIBR0319_an_answered_mapping_settles_the_rest_of_the_batch runs at the BatchImportService level (save_profile, then answer), not through the wizard. The repro confirmed the wizard behaves the same.
- **B8** test_FIBR0222_huge_exponent_is_a_ValueError_not_a_decimal_Overflow checks `parse_transaction` raises ValueError. It never checks that a CSV import produces one RowError while the other rows still preview.
- **B10** test_FIBR0050_INV11_gate_is_signed_for_families_that_print_a_sign calls the private `_verify_checksum` with hand-built drafts. No test runs a truncated overdrawn statement through `StandardBankImporter.parse`.
- **B3** test_unplaced_row_opens_a_picker_that_has_chosen_nothing checks `selected_account_id() is None` and OK disabled. It does not check the picker shows "— pick one —"; the repro did.