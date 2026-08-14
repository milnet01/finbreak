# FIBR-0146 — the import wizard's date step (picker, auto-detect, preview, banner)

> **Status:** ✅ **SHIPPED.** Split out of [`FIBR-0146.md`](FIBR-0146.md) on
> 2026-08-14 (ROADMAP **FIBR-0272**) — see that file's Cold-eyes loop log for the
> review history of both halves, which is kept whole there rather than divided.
> **This is a structural move, not an amendment: every line below is verbatim
> from `FIBR-0146.md`.** No invariant was re-cut, no decision reworded, and no
> id renumbered — **D4–D8** and **INV-1 / INV-4 / INV-5** keep the numbers they
> were reviewed under, which is why they start at D4 and skip INV-2/3/6. Ids are
> permanent (the [`FIBR-0192-qt-facts.md`](FIBR-0192-qt-facts.md) rule); the
> gaps are the point, not an error.
> **Same id, deliberately.** Both files are `FIBR-0146`, so the ~66 existing
> `FIBR-0146 D8`-style citations in code, tests and the ROADMAP stay correct
> without being touched.
> **Kind:** fix. **Roadmap:** [ROADMAP.md → FIBR-0146](../../ROADMAP.md).

**Why the split.** Three `review-contract` loops on the combined 746-line
document each found defects in regions the previous loop never reached — the
shape `spec-format.md` §5.4 calls the size gate, whose remedy is to split along
§3.6's by-concern seams rather than keep looping. The wizard wiring is both the
larger half (~300 lines) and the half that keeps drifting against the code, so
it is the half that moves; the detector and importer contract other specs cite
stays put under the original filename.

**Read this with [`FIBR-0146.md`](FIBR-0146.md).** That file owns the shared
front matter, the **Context** (the three format paths, and why only an unmatched
CSV or a generic non-SB PDF reaches this step), the detector contract
(**D1**, **D2**, **INV-2**), the importer's friendly row errors (**D3**,
**INV-3** — including the banner clause this file's D7 implements), and
**INV-6**. One home, one copy: where a rule lives there, this file cites it
rather than restating it.

**Contents:** Invariants (INV-1, INV-4, INV-5) · Design decisions (D4–D8) ·
New symbols · Deliverables · Test plan · Out of scope.

## At a glance — invariants

The three guarantees this half owns. **INV-2** (pure detector), **INV-3** (no
raw parser internals reach the UI) and **INV-6** (no new dependency; pipeline
untouched) live in [`FIBR-0146.md`](FIBR-0146.md) and are not restated here.

| INV | Guarantee | Upholds |
|-----|-----------|---------|
| **INV-1** | **Never a silent wrong-day.** Auto-detection only ever *pre-selects* a format in a **visible** picker; the resulting dates are shown to the user — the map-step live preview (D6) **and** the existing preview-step Date column (`_fill_preview_table`) — before any row is written. Detection commits nothing and changes no stored value; the irreversible write is still the user's explicit Import press on the preview step. When two or more formats are **equally** consistent with the sampled dates (ambiguous — e.g. every day-number ≤ 12, so day-first and month-first both parse, D2), the picker pre-selects the first by the fixed candidate order **and** the UI flags the ambiguity so the user confirms the reading rather than trusting it. | user decision 2026-07-16; the "money app, wrong-day is unforgivable" project override (`finbreak/CLAUDE.md`) |
| **INV-4** | **Capability preserved; no saved layout lost.** The friendly picker covers every historically-typable layout via the ordered `KNOWN_DATE_FORMATS` list **plus** a **"Custom…"** entry that reveals a raw-pattern field, so an exotic bank is still importable and no capability is removed. A **saved profile** whose stored `date_format` is not in the known list **round-trips unchanged** through "Custom…" — it is shown, editable, and re-saved verbatim, never silently rewritten to a near-match. A **matched** profile's stored `date_format` is authoritative: auto-detect **never** overrides it (it seeds only the *unmatched* case and a user's manual date-column change, D5). | FIBR-0007 (profiles carry `date_format`); coding.md § 1.3 |
| **INV-5** | **i18n-clean.** Every user-facing string this adds — the "Custom…" entry, the live-preview label and its "couldn't read these dates" / ambiguity messages, the banner — is wrapped in `tr()`. The known-format combo entries are **language-neutral example date strings** ("20/07/2026"), data not translated prose; the stored `date_format` values are the fixed `%`-token patterns, never the display text (the FIBR-0142 "labels injected, tokens fixed" lesson). | future FIBR-0017 i18n; coding.md § 5.2 |

## Design decisions

The wizard half, **D4–D8**. **D1–D3** (the detector module, the candidate
list and the importer's friendly date error) are in
[`FIBR-0146.md`](FIBR-0146.md).

- **D4 — The friendly picker (`import_wizard`).** Replace the `QLineEdit("%Y-%m-%d")`
  with `self._date_format` = a `QComboBox` (objectName `import_date_format`) on the
  form row still labelled `tr("Date format")` (the label the D7 banner tells the
  user to "check", so the two must match), populated from `KNOWN_DATE_FORMATS` —
  each entry's **text** is the example string, its **data** the `fmt` — followed by a final **"Custom…"** entry (data
  a sentinel). Selecting "Custom…" reveals a raw-pattern `QLineEdit`
  (`import_date_format_custom`, hidden otherwise), preserving the power-user /
  exotic-bank capability (INV-4). `_mapping_from_form` reads the format via a new
  `_selected_date_format()` (the combo's `currentData()`, or the custom field's
  `.strip()`-ed text when "Custom…" is active — matching today's
  `_mapping_from_form` strip, so a stray-space custom pattern can't slip past
  validation). An **empty/blank** Custom pattern is **rejected** at the
  mapping-validation boundary — `ImportService._validate_mapping` gains a non-empty
  `date_format.strip()` check that raises the friendly `ValueError`
  `"choose a date format"`, surfaced by `_run_preview`'s existing `ValueError`
  catch (reached from `_on_map_next`) so the user can't proceed with no format.
  **The batch ask step has its own seam and it is not this one:** `_on_map_next`
  returns before `_run_preview` (D5(d)), so a batch file's blank format is caught
  by `BatchImportService._scan_csv`, which calls the same validator directly and
  fails **that one file** with the same message in the batch report rather than
  refusing to advance. Both routes close the trap; only the single-file one blocks
  the screen. This is deliberate: an empty format string is
  a **trap**, not merely unparseable — `strptime("", "")` *succeeds* and returns
  **1900-01-01**, so a blank date cell (which PDF-serialised tables produce
  routinely) under an empty format would silently import as a phantom 1900 date
  rather than error. Rejecting the empty format forecloses that; the format is
  never silently defaulted to ISO either. `_apply_profile_to_combos` selects the entry
  whose data equals `mapping.date_format`, or — when the stored format is not in
  the known list — selects "Custom…", fills the raw field with it verbatim, **and
  explicitly makes `import_date_format_custom` visible** (the programmatic select is
  `QSignalBlocker`-wrapped, so `_on_date_format_changed`'s show/hide won't fire —
  the reveal must be explicit, else INV-4's "shown, editable" would be violated and
  the exotic pattern held but hidden). **The blocker suppresses that slot in both
  directions, so the hide must be explicit too**: a programmatic select of a
  *known* entry — a matched profile, or D5(c)'s re-detect after the user changes
  the date column — sets `import_date_format_custom` hidden, or a raw `%`-pattern
  box left over from a prior "Custom…" pick stays on screen holding a pattern the
  mapping no longer uses, against the "never a raw `%`-box for the normal user"
  goal above. The combo's **initial/default** selection is the first entry
  (ISO `%Y-%m-%d` — today's default); it is overridden by auto-detect (D5) or a
  matched profile, and **left untouched** when auto-detect returns `None`
  (an unrecognised date column), so the live-preview "couldn't read" nudge (D6)
  then guides the user to pick. Programmatic combo changes are
  `QSignalBlocker`-wrapped so they fire no re-detect (D5).

- **D5 — Auto-detect wiring (unmatched case + manual date-column change).**
  `_autodetect_date_format()` reads the **currently-selected** date column's
  samples via `_date_samples` (D8 — the guarded `read_rows` read over `self._text`,
  the same text a PDF is serialised into), calls `detect_date_format`, stores
  `self._date_ambiguous = guess.ambiguous`, and — only when `guess.fmt` is
  non-`None` — sets the picker to that format. It does **not** itself refresh the
  preview — **the caller** calls `_update_date_preview` right after (one owner, no
  double refresh), so a `None` result still shows the "couldn't read" nudge. Every
  caller runs that pair through `_refresh_date_ui(detect=True)`, which is the
  guarded owner D8 requires; `_select_file` is the one exception and D8 says why.
  It fires at four points:
  - **(a) unmatched CSV** — in `_select_file`'s no-match branch (before
    `_goto_step(_STEP_MAP)`).
  - **(b) generic (non-SB) PDF** — in `_continue_after_decrypt`'s no-match branch
    (before showing the map step) **and** in `_on_pdf_table_changed`'s no-match
    branch, so switching to a *different unmatched* PDF table re-detects for the new
    table (never a stale format/preview from the previous one).
  - **(c) manual date-column change** — the `_on_date_column_changed` slot re-detects
    for the newly-chosen column (which may hold a different layout), **overriding any
    prior manual format pick** — deliberate, since the column changed, so the old
    pick no longer applies. That override happens **only when the new column
    yields a guess**: on a `None` guess the picker is left exactly as it was
    (`_autodetect_date_format` sets it only for a non-`None` `fmt`), so the user's
    hand-picked format survives a column that detects nothing.
  - **(d) batch ask step** — `_ask_mapping` (FIBR-0085 § 4.1) re-shows this same
    map step for one unfamiliar file in a batch, so that file gets a guess too.
    The route ends there: `_on_map_next` hands a batch answer to
    `_answer_batch_mapping` and returns **before** `_run_preview`, so the batch
    never reaches the preview step, its banner, or `_has_mapping_step`. The step
    is **re-used** per file, so `_ask_mapping` clears the Custom pattern field
    before detecting — for the same reason it resets invert and amount style —
    and this detect then re-seeds the combo. It does **not** reset the combo
    itself, so when the next file detects nothing (`fmt is None`) the previous
    file's selection stands. That is visible rather than silent: the map step is
    shown with its live preview before anything is imported (INV-1).

  Programmatic fills (`_populate_mapping_combos`, `_apply_profile_to_combos`) are
  `QSignalBlocker`-wrapped so only a real user change re-detects. A **matched
  profile short-circuits** auto-detect (its stored format wins, INV-4) — the matched
  branches skip to preview or apply the profile's format; `_apply_profile_to_combos`
  **clears** `self._date_ambiguous` (a matched profile is authoritative, never
  "ambiguous") and its caller refreshes `_update_date_preview`, so switching a PDF
  from an ambiguous *unmatched* table to a *matched* one clears the stale nudge +
  preview. **On-entry detection (a/b) runs over the *currently-selected* date
  column**, which on a fresh map step is the combo default (`header[0]`) — the date
  column is **not** role-guessed (out of scope, like the amount column). So when the
  statement's date isn't the first column, on-entry detection sees a non-date column
  → `fmt = None` → the picker keeps whatever it last held — the ISO default on a
  fresh wizard, and **the previous file's format on a second pick**, since nothing
  in `_select_file` or `_populate_mapping_combos` resets it — and the preview shows
  "couldn't be read" until the user selects the real date column, at which point (c)
  re-detects. The common case (date in the first column) just works; anything else
  self-corrects on the user's column pick, never a wrong-day. The D5 fixture places
  the date **off** column 0 so a green test can't mask this.

- **D6 — Live "how the dates read" preview (the *confirm* affordance).** A read-only
  `QLabel` (`import_date_preview`) under the picker, refreshed by
  `_update_date_preview()` on any format or date-column change — but each signal
  reaches it through **exactly one** slot, never a second direct connection (D5's
  "one owner, no double refresh"): `import_date_format.currentIndexChanged` **and**
  the `import_date_format_custom` field's `textChanged` both go to
  `_on_date_format_changed` (which clears `_date_ambiguous`, shows/hides the custom
  field, **then** calls `_update_date_preview`), and a date-column change goes to
  `_on_date_column_changed` (re-detect → `_update_date_preview`). It takes the first `_PREVIEW_SAMPLES`
  (**up to 3**) values from `_date_samples` (the same non-blank values, D8 — a
  small table may yield only 1–2) and, under the currently-selected format,
  renders them as ISO dates — `tr("Dates read as: {samples}")` — **only when the
  selected format parses all of the shown samples** (a clean, trustworthy preview;
  "all of the shown" so a valid 1- or 2-sample column still gets the clean
  branch, never the fallback). Two distinct fallbacks cover the other
  cases, so the label is never left showing an empty or half-parsed "Dates read
  as:" tail: (i) **no samples** — `_date_samples` returns `[]` (a header-only
  extracted table or an all-blank date column; an empty CSV raises earlier in
  `read_header` and never reaches the map step) → `tr("No dates found in this
  column.")`; (ii) **samples present but the selected format fails any of the shown
  ones** (partial *or* total failure — including a non-date "junk" column, whose
  non-blank cells *are* sampled and simply don't parse) → `tr("These dates couldn't
  be read with this format — pick another.")`. The ambiguity nudge —
  `tr("Check these are right — the day and month might be the other way around.")`
  — is prepended **iff** `self._date_ambiguous` is set **and** the clean "Dates
  read as:" branch is taken; both fallbacks above return before the prepend, so
  neither ever carries the nudge (D5). A **manual** format
  change (`_on_date_format_changed`) clears `self._date_ambiguous` first, so the
  nudge never goes stale against a format the user chose by hand. This is the
  immediate "eyeball before importing" the user asked for; the preview **step**
  remains the full row-by-row confirmation.

- **D7 — Whole-import banner (preview step).** In `_apply_preview_counts`, when
  `preview.new_count == 0 and preview.duplicate_count == 0 and preview.errors`
  (nothing landed, at least one error — the tester's exact 0·0·165 state), show a
  prominent banner (`import_preview_banner`, hidden otherwise):
  `tr("None of the rows could be imported. Go back and check the column mapping and
  the Date format match your statement.")`. The trigger is **count-based** (it never
  inspects error reasons), and several distinct faults all land at 0·0·N — a wrong
  date *format* (the tester's case), a wrong date *column* mapping, an all-blank
  date column, **or** an amount/debit-credit mis-map — with different fixes, so the
  message names the general remedy ("column mapping and the Date format") rather
  than over-claiming one cause; the upstream D6 "No dates found" / "couldn't be
  read" nudges point a layman at the date control specifically when that's the
  fault. Any successful or duplicate row
  hides the banner (partial failures are already flagged per-row); the
  zero-rows/zero-errors case (a header-only extracted table — nothing to import
  and nothing failed) is also banner-less, and Import stays disabled as today. The
  banner is separate from `_summary_label` (the counts line stays).

  **The trigger is source-neutral; the remedy is not** (FIBR-0253). Every source
  collects per-row errors, so every one can reach 0·0·N and raise this banner —
  but "go back and check the column mapping" names the **map step**, and two
  sources never see it: OFX, and a **recognised Standard Bank** PDF, both
  self-describing and both jumping straight to preview. A **generic (non-SB)
  PDF** does see it — Context above extracts it to a CSV-text table and maps it
  exactly like a CSV, and that is this spec's own bug report (a PDF, 165 error
  rows), so keying the remedy on CSV-ness would deny it to the very user it was
  written for. So the sentence above is the **mapped-source** wording, chosen per
  preview by `_banner_text()` from `_has_mapping_step` — cleared on every pick in
  `_select_file`, set on its CSV fall-through and in `_continue_after_decrypt`
  past the SB reader. An unmapped source gets `tr("None of the rows could be
  imported. Each row below says what went wrong with it.")`, pointing at the
  per-row reasons the preview table already renders. The trigger is unchanged.

- **D8 — Sampling bound + reuse.** `_date_samples(column)` returns at most
  `_MAX_DATE_SAMPLES` (50) **stripped, non-blank** values of `column` (each cell
  `.strip()`-ed; a cell that is empty after stripping is skipped and not counted
  toward the 50) — a statement's date column is uniform, so 50 is ample and the
  **sample collection** stops once 50 are in hand. **Stripping here matters:** the importer parses
  `row[...].strip()` (`csv_importer.py:74`) and the detector strips too (D2), so a
  whitespace-padded cell (PDF-serialised tables emit these) must be stripped before
  the *preview* strptimes it as well — otherwise the preview would falsely show
  "couldn't be read" for a format the import would parse fine. Detector, preview,
  and importer thus all operate on the identical stripped string the committed row
  uses. Detection is **format-outer** (loop the 15 candidate formats, each
  re-scanning the ≤ 50 samples — the order `detect_date_format`'s `Sequence`
  requires, and it keeps CPython's small `_strptime` regex cache warm rather than
  thrashing it), bounded at **≤ 50 × 15 = 750 `strptime` calls regardless of file
  size**. **The row read is not bounded, and this is the one cost claim to get
  right:** `read_rows` is `list(csv.DictReader(...))`, so the whole file is
  materialised before the sampling loop can break at 50, and `_date_samples` runs
  again on every detect, column change and format change. Detection cost is
  therefore constant in the row count; **refresh cost is linear in it**. The 750
  bound is self-proving and needs no perf test; the linear read is the thing to
  measure if a large statement ever feels slow. The read is a small private
  `_date_samples` in the wizard, over
  `self._text` and **through the shared guarded reader `read_rows`, never a bare
  `csv.DictReader`**: `csv.Error` is not a `ValueError` subclass, so an
  unguarded reader here escapes this widget's `(ValueError, OSError,
  FinbreakError)` nets, leaves the Qt slot, and terminates the app on a
  malformed body — a file whose header parses fine, so `read_header` does not
  catch it first. `read_rows` translates that `csv.Error` into the friendly
  `ValueError` this module's boundary uses, **and the caller must still catch
  it**. `_autodetect_date_format` (D5) and `_update_date_preview` (D6) both
  consume `_date_samples`, so either can raise, and there are exactly two
  catchers. D5(a)'s CSV pick runs inside `_select_file`'s `try`, which **refuses
  the file** — the message is shown, `_text` is cleared, the map step is not
  reached, and the picker is left untouched. Every other caller — D5(b)
  (`_continue_after_decrypt`, `_on_pdf_table_changed`), D5(c)
  (`_on_date_column_changed`), D6's `_on_date_format_changed`, and the batch ask
  step (`_ask_mapping`, FIBR-0085 § 4.1) — is a Qt slot or a batch step with no
  net of its own, so each calls the pair through **`_refresh_date_ui(detect=)`**,
  which catches the `ValueError`, puts the message on the map-step error label,
  clears the preview label and leaves the picker as it was. That second catcher
  is FIBR-0268; before it, the batch route reached the map step with a broken
  body loaded and the next date-column or format change killed the app.

## New symbols (signatures)

The wizard's. `importers/date_detect.py` and `importers/csv_importer.py`
are in [`FIBR-0146.md`](FIBR-0146.md).

```python
# ui/import_wizard.py (new privates; self._date_format becomes a QComboBox)
_MAX_DATE_SAMPLES = 50      # detector sampling bound (D8)
_PREVIEW_SAMPLES = 3        # how many parsed dates the live preview shows (D6)
_CUSTOM_FORMAT = object()   # sentinel data for the "Custom…" combo entry

self._date_ambiguous: bool  # initialised False in __init__; set by _autodetect
                            # (True => show the day/month nudge); cleared by any
                            # manual format change (D6)
self._has_mapping_step: bool  # False in __init__ AND cleared on every pick; set
                            # on the two MAPPED-SOURCE routes — the whole CSV
                            # fall-through in _select_file (matched or not, since
                            # a matched CSV's remedy is still the mapping) and
                            # _continue_after_decrypt past the SB reader (D7). The
                            # batch ask step reaches the map step and does NOT set
                            # it, correctly: it never reaches the banner (D5(d)).
                            # False is the safe default: it
                            # withholds a remedy, where True would offer an
                            # unreachable screen.

def _banner_text(self) -> str: ...               # the D7 sentence for the source in hand, chosen on _has_mapping_step
def _selected_date_format(self) -> str: ...      # combo data, or the custom field's .strip()ed text
def _date_samples(self, column: str) -> list[str]: ...   # up to _MAX_DATE_SAMPLES stripped, non-blank values of `column`
def _autodetect_date_format(self) -> None: ...   # detect on the selected date column, seed the picker + _date_ambiguous (D5)
def _update_date_preview(self) -> None: ...      # refresh the "Dates read as: …" label (D6)
def _refresh_date_ui(self, *, detect: bool) -> None: ...  # the pair above under ONE ValueError guard — every caller but _select_file (D8)
@Slot(int)
def _on_date_column_changed(self, index: int) -> None: ...   # user date-column change -> re-detect (D5)
@Slot()  # no-arg so BOTH currentIndexChanged(int) and the custom field's textChanged(str) connect here (extra arg dropped) — single owner
def _on_date_format_changed(self) -> None: ...   # user picker/custom edit -> clear _date_ambiguous, show/hide custom, then _refresh_date_ui(detect=False) (D6)

```

## Deliverables

3. **`ui/import_wizard.py`** — the date-format **picker** + "Custom…" reveal (D4),
   the auto-detect wiring (D5), the live-preview label (D6), the whole-import
   banner (D7), and the `_date_samples` reader (D8). Existing map-step tests that
   drove the old `QLineEdit` re-pointed to the combo.
4. **`services/import_.py`** — `_validate_mapping` gains a non-empty
   `date_format.strip()` check (friendly `ValueError "choose a date format"`, D4),
   closing the empty-format `strptime("", "")` → 1900-01-01 trap.

## Test plan

The wizard suite. The pure-detector and importer suites are in
[`FIBR-0146.md`](FIBR-0146.md).

**Wizard (`ImportWizardWidget`, `qtbot`):**
- **Auto-detect seeds the picker:** load an unmatched CSV whose dates are
  day-first (day > 12) → the map step's `import_date_format` combo is pre-selected
  to the `%d/%m/%Y` entry (not the old `%Y-%m-%d` default), and the preview step
  then shows the dates parsed (no error rows). The **regression** for the tester's
  bug: the same fixture imported end-to-end lands rows instead of 165 errors.
- **Live preview (D6):** the `import_date_preview` label shows `Dates read as: …`
  with correctly-parsed ISO samples; switching the picker to a wrong format
  flips it to the "couldn't be read" message; an all-days-≤-12 fixture shows the
  ambiguity nudge, and **manually** switching the picker to another format
  **clears** that nudge (it is not stale against a hand-chosen format).
- **Two preview fallbacks (D6):** an **all-blank** date column (`_date_samples`
  → `[]`) shows `tr("No dates found in this column.")`; a **non-date "junk"**
  column (non-blank cells that don't parse) shows `tr("These dates couldn't be
  read with this format — pick another.")` — **never** an empty or half-parsed
  "Dates read as:" tail; in both, on a **fresh** wizard auto-detect leaves the
  picker at the ISO default
  (D4).
- **Short column clean preview (D6, <3 samples):** a valid column with only **2**
  date rows shows the clean `Dates read as: …` branch (both parsed), **not** a
  fallback — the "all of the shown samples" gate, not a literal count of 3.
- **Preview refreshed once (D5 ownership):** a spy/call-count asserts
  `_update_date_preview` fires **exactly once** per auto-detect fire point (the
  caller owns it; `_autodetect_date_format` does not also refresh — no double
  refresh regresses the "one owner" contract).
- **Custom round-trip (INV-4):** selecting "Custom…" reveals `import_date_format_custom`
  and `_mapping_from_form` reads its text; a **saved profile** whose `date_format`
  is an exotic pattern not in `KNOWN_DATE_FORMATS` (e.g. `"%Y.%m.%d"`) applied via
  `_apply_profile_to_combos` selects "Custom…", fills the field verbatim, **and
  makes `import_date_format_custom` visible** (INV-4 "shown, editable") — the
  mapping the form produces equals the stored format (no silent rewrite).
- **Empty Custom rejected (D4 / the 1900 trap):** selecting "Custom…" and leaving
  the field **blank** → `_on_map_next` surfaces the friendly `"choose a date
  format"` error and does **not** advance to preview; a `CsvImporter.parse` /
  `_validate_mapping` unit assertion locks that an empty `date_format` is rejected
  (so `strptime("", "")` → 1900-01-01 can never reach a committed row).
- **Matched profile wins (INV-4/D5):** applying a profile whose format **is** a
  known entry selects that entry and does **not** re-run auto-detect over the data.
- **Whole-import banner (D7):** a preview with `new_count == 0`,
  `duplicate_count == 0`, and ≥ 1 error shows `import_preview_banner`; a preview
  with ≥ 1 new **or** ≥ 1 duplicate hides it; and a `0 new · 0 dup · 0 error`
  header-only preview also **hides** it (nothing failed — Import stays disabled).
- **Banner remedy follows the map step (D7 / FIBR-0253):** with the same 0·0·N
  preview, three legs. A file picked through the **CSV** path shows a banner
  containing "column mapping"; one picked through a **recognised Standard Bank**
  PDF shows a non-empty banner that does **not**; and a **generic (non-SB) PDF**
  shows one that **does** — asserting `_has_mapping_step is True` as its
  precondition. **That third leg is the one that matters**: the first two pass
  under a CSV-only flag, so without it nothing in this plan can falsify D7's
  central claim, and the generic-PDF regression D7 exists to prevent ships green.
  Two PDFs of the same extension with opposite answers is also why no filename or
  sniff test can stand in for it. Every leg drives the real `_select_file`
  dispatch rather than setting the flag by hand — the flag is only worth anything
  if the dispatch sets it.
- **i18n (INV-5):** the added strings ("Custom…", the preview label templates, the
  banner) are `tr()`-wrapped (grep-style check as prior UI phases did); the combo
  entry **data** values are the fixed `%`-patterns.
- **PDF path (INV-6):** a generic (non-SB) PDF fixture whose extracted table is
  day-first reaches the map step with auto-detect applied (the PDF-serialised-to-
  CSV text is the same `self._text` the detector reads).
- **Date-column change re-detects (D5c):** on an unmatched multi-column file,
  switching `_column_combos["date"]` to a *different* date-bearing column re-seeds
  `import_date_format` for that column and refreshes the preview.
- **Date off column 0 (D5 on-entry dependency):** an unmatched file whose date is
  **not** the first column → on entry the picker stays at ISO (a fresh wizard; it
  is never reset per pick) and the preview shows
  "couldn't be read" (detection saw the non-date default column); selecting the
  real date column then re-detects to the right format (the fixture deliberately
  puts the date off column 0 so this can't be masked).
- **PDF table-switch re-detects (D5b):** a multi-table generic PDF whose two
  tables use different date layouts — switching `_pdf_table_combo` re-detects the
  format and refreshes the preview for the new table (no stale reading); switching
  from an ambiguous unmatched table to a *matched* table clears the nudge + refreshes.
- **INV-6 pipeline-untouched:** the happy-path importer test (a valid row still
  parses unchanged) is tagged `(INV-6)` as the direct no-regression anchor.
- **OFX / Standard-Bank PDF skip the picker (INV-6 suppression):** an OFX import
  and a recognised-SB-PDF import reach the preview step **without** showing
  `import_date_format` and **without** calling `_autodetect_date_format` —
  asserted by monkeypatching `_autodetect_date_format` with a counter and
  requiring zero calls on each pick, plus `_has_mapping_step is False` for both.
  **Named here rather than delegated**: the FIBR-0007/0009 path tests predate
  `_autodetect_date_format` and cannot assert it was not called, so "covered by
  the existing tests" is satisfiable by writing nothing, and a later change that
  wires auto-detect into either path would ship green.
- **Auto-detect writes nothing (INV-1):** after loading an unmatched file and
  auto-detect running (picker seeded, preview shown), the vault holds **zero**
  transactions for the target account — the irreversible write happens only on the
  explicit Import press — falsifying "detection commits nothing" directly.

## Out of scope (v1 — YAGNI)

The one exclusion this half owns; the rest are the detector's and are in
[`FIBR-0146.md`](FIBR-0146.md).

- **No change to OFX or the recognised Standard-Bank PDF path beyond D7's banner
  wording** — both skip the map step (self-describing), never show a date-format
  box and never run auto-detect. They do reach the D7 banner (any source can
  error every row), and FIBR-0253 gives them its unmapped sentence; that is the
  one thing on these paths this spec now changes.
