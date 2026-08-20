# Feature test contract — CSV import column-header auto-guess (FIBR-0297)

`_populate_mapping_combos` (`src/finbreak/ui/import_wizard.py:1009`, formerly
misfiled in the roadmap bullet as `_set_header`) fills all five mapping combos
— Date, Description, Amount, Debit, Credit — with the same header list and
calls no `setCurrentIndex`, so every one lands on index 0. Observed on a CSV
headed `Date,Description,Amount`: the Date column, Description column and
Amount column dropdowns **all** read "Date" on arrival at the map step —
correct once set by hand, but nothing offers the obvious guess first.

The date-format detector (FIBR-0146) and the saved-profile auto-match
(FIBR-0007 INV-10a) are the only automatic help today, and neither covers
this: a file with no saved profile gets no column guess at all, however
plainly its headers spell out what they are. This contract locks a header-name
guess for that unmatched case only — a small set of conventional spellings,
matched case- and punctuation-insensitively — while leaving the current
index-0 behaviour as the fallback where nothing matches, so today's behaviour
regresses nowhere.

Two layers, split because the wizard-level layer proves the **wiring** exists
against code that runs today, while the module-level layer proves the
**matching rules** of a guesser that does not exist yet. `guess_columns` /
`ColumnGuess` in `finbreak.importers.column_detect` are the intended shape,
modelled on the sibling pure detector `finbreak.importers.date_detect`
(docstring conventions, purity claim, frozen dataclass) — not written as of
this contract. No vault holds real data; fixtures are tiny in-repo strings, no
real statements, no network (testing.md § 6).

| INV | Assertion |
|-----|-----------|
| INV-1 | **The bug itself, proven against code that runs today.** An unmatched CSV headed `Date,Description,Amount` must not leave the Description and Amount combos reading "Date" — they must read the header that names them, the moment the map step is reached (`test_FIBR0297_headline_unmatched_header_autofills_description_and_amount`). This is the wizard-level layer: it drives the real `ImportWizardWidget._select_file` dispatch that exists now, so it is the one test in this contract that is expected to fail until the guess is wired in — not on an import error, on the assertion. |
| INV-2 | **The guesser matches case- and punctuation-insensitively.** `DATE`, `Date:` and `AMOUNT ($)` all match their role the same as the canonical spelling, and the returned value is the **original** header string, never a normalised/lowercased copy (`test_case_and_punctuation_insensitive_matching`). Module-level (`guess_columns`), so this fails on import today rather than on an assertion — the module does not exist yet; that is expected and is why this layer is kept apart from INV-1. |
| INV-3 | **The conventional-spelling set the bullet specifies, and no other.** date: `date` / `transaction date` / `posting date`; description: `description` / `details` / `narrative` / `reference`; amount: `amount` / `value`; debit: `debit` / `withdrawal`; credit: `credit` / `deposit` — each synonym is asserted individually against the role it is supposed to fill (`test_conventional_synonyms_matched`). |
| INV-4 | **Debit and Credit are matched as an independent pair.** A header carrying `Debit`/`Credit` but no `Amount`/`Value` column matches both of the former and leaves `amount` unset — the single-amount and split-amount statement shapes are not conflated (`test_debit_credit_pair_matched_leaves_amount_none`). |
| INV-5 | **No match is `None`, not a wrong guess.** A header with no recognisable role name (`Col1, Col2, Col3`) returns `None` for every field — a guesser that invents a match on unrelated text is worse than the fallback it replaces (`test_no_match_returns_none_for_every_role`, module-level; `test_no_recognisable_header_falls_back_to_index_zero_current_behavior`, wizard-level — the latter locks that today's index-0 default is the correct fallback shape and must survive unchanged). |
| INV-6 | **The guess does not fire on the matched-profile path.** A CSV whose saved profile matches its header jumps straight to the preview step (FIBR-0007 INV-10a) — the map step, and therefore any combo the guess would touch, is never shown, and the mapping applied is the profile's own, not a guess's (`test_guess_not_firing_when_profile_matched`). This path is already correct; the guess must add nothing to it. |
| INV-7 | **A guessed date column feeds the FIBR-0146 detector, not a stale one.** The date-format auto-detect (D5/D6) re-runs whenever the date **column** changes — a guess that points the date combo at a non-first column must go through that same re-detect, or the format preview reads the wrong column and goes stale. Proven with the date column deliberately **not** first in the header (`Description, Amount, Transaction Date`, day-first values): today the date combo defaults to "Description" and the detector finds nothing there, so this assertion fails now for the same underlying reason as INV-1 — the column guess that would fix it does not exist (`test_FIBR0297_guessed_date_column_feeds_the_FIBR0146_detector`). |

## Layers

* **Wizard** (`ImportWizardWidget`, `qtbot`, INV-1/5/6/7): drives the real
  `_select_file` dispatch against fixtures written with `tmp_path`, exactly as
  `import_date_detect`'s Layer 4 does — no combo is set by hand where the
  dispatch is what should have set it. This layer imports nothing from the
  not-yet-written guesser module, so its assertions are true reds against
  today's code, never import errors.
* **Guesser** (`guess_columns`, no Qt, INV-2/3/4/5): the pure matching rules —
  synonym set, case/punctuation insensitivity, original-header-string
  preservation, the debit/credit pair, the no-match case. Every test imports
  `finbreak.importers.column_detect` inside the test body (matching
  `date_detect`'s convention), so a `ModuleNotFoundError` here is expected and
  contained to this layer — it must never stand in for a wizard-level red.

## Out of scope

The `amount_style` radio (single vs. debit/credit) is not touched by the
guess in this contract — the wizard already requires the user to pick that
explicitly, and the roadmap bullet's proposal is a column guess, not a style
guess. Locale / non-English header spellings are not covered — the bullet's
synonym set is English-only, matching the rest of the wizard's `tr()`-wrapped
but not multi-locale-dictionary UI. The saved-profile *matching* logic itself
(FIBR-0007) is exercised only enough to prove the guess does not run on that
path (INV-6); its own contract lives in that feature's suite.

## Regression history

Filed as FIBR-0297 (2026-08-20) after `_populate_mapping_combos` was found to
seed every mapping combo from the same header list with no `setCurrentIndex`,
so all five defaulted to index 0. Not a regression from a prior fix — the
combos have never auto-guessed; the date-format detector (FIBR-0146) and the
saved-profile auto-match (FIBR-0007 INV-10a) were mistaken for full coverage
until this gap was reported.
