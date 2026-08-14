# Feature test contract — the import preview step can go Back (FIBR-0270)

When an import lands nothing, the wizard shows FIBR-0146 D7's banner: *"None of
the rows could be imported. **Go back** and check the column mapping and the Date
format match your statement."* Until FIBR-0270 the wizard had no way back — the
only `_goto_step(_STEP_PICK)` calls were the initial build and the finish/reset,
and no `_goto_step(_STEP_MAP)` was reachable from the preview step. The remedy
named a screen the user could not return to.

FIBR-0270 adds a **Back** control on the preview step rather than rewording the
banner: the sentence is right, it was the wizard that was wrong. Re-picking the
file was never the answer for the case that hurts most — a CSV whose saved
profile *matched* jumps straight back to the same failed preview, because the
saved profile is what is wrong.

No vault holds a real statement; fixtures are tiny in-repo strings, plus the
existing `standard_bank_pdf` fixture for the self-describing leg (testing.md § 6).

| INV | Assertion |
|-----|-----------|
| INV-1 | **A mapped source can go back.** After an unmatched CSV maps and previews, Back is offered and returns the wizard to the map step, with the form still holding the mapping the preview was built from — so a correction is an edit, not a re-entry (`test_INV1_back_returns_an_unmatched_csv_to_the_map_step`). |
| INV-2 | **The banner's remedy is followable.** Whenever D7's all-rows-failed banner is showing on a mapped source, the control its text names is visible on the same screen. This is FIBR-0270's actual defect, so it is asserted against the banner text rather than assumed (`test_INV2_the_go_back_remedy_is_followable`). |
| INV-3 | **A self-describing source offers no Back.** OFX and a *recognised* Standard Bank statement skip mapping entirely (`_has_mapping_step is False`), so there is no map step to return to and Back must be hidden — the same split FIBR-0253 drew for the banner text, keyed on the same flag (`test_INV3_a_self_describing_source_offers_no_back`). |
| INV-4 | **Back unsticks a matched profile.** A CSV whose stored profile matched never sees the map step, so the mapping combos were never filled from that profile. Back must land on a form showing the mapping actually in force — not combo defaults — and editing it must re-preview under the correction (`test_INV4_back_after_a_matched_profile_shows_the_stored_mapping`). The fixture's date column is deliberately **not** the first header field, so a form left at its defaults fails the assertion instead of passing by coincidence. |
| INV-5 | **The banner strings are unchanged.** Rewording D7 would amend `docs/specs/FIBR-0146-wizard-date-step.md` (D7's home since the 2026-08-14 split) and re-arm the rule-14 review gate; the point of adding the control is that the shipped sentence becomes true as written. INV-2 pins the mapped-source wording verbatim. |

## Layers

* **Wizard** (`ImportWizardWidget`, `qtbot`): every leg drives the real
  `_select_file` format dispatch rather than setting `_has_mapping_step` by
  hand — the flag is only worth anything if the dispatch sets it, and the
  dispatch is where the two PDF kinds part (the lesson FIBR-0253 paid for).
