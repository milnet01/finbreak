"""Feature-conformance tests — statement date-format auto-detect + confirm.

Enforces `docs/specs/FIBR-0146.md`. Three layers:

* the pure detector `detect_date_format` (no Qt, plain strings — the heart);
* the `CsvImporter.parse` friendly per-row date error (D3/INV-3);
* the `ImportService._validate_mapping` empty-format reject (D4 — the
  `strptime("", "")` -> 1900-01-01 trap);
* the `ImportWizardWidget` picker / auto-detect / live-preview / banner
  (`qtbot`, D4-D8/INV-1/INV-4/INV-5).

Every vault uses `tmp_path`; fixtures are tiny in-repo strings — no real
statements, no network (testing.md § 6).
"""

from __future__ import annotations

import pytest

# --------------------------------------------------------------------------- #
# Layer 1 — the pure detector (detect_date_format). No Qt, plain strings.      #
# --------------------------------------------------------------------------- #


def test_day_first_numeric_disambiguated_by_day_gt_12():
    """The tester's shape: DD-first with a day > 12 rules out month-first."""
    from finbreak.importers.date_detect import detect_date_format

    guess = detect_date_format(["20/07/2026", "21/07/2026", "31/07/2026", "02/08/2026"])
    assert guess.fmt == "%d/%m/%Y"
    assert guess.ambiguous is False


def test_iso_and_slashed_iso():
    from finbreak.importers.date_detect import detect_date_format

    assert detect_date_format(["2026-07-20"]).fmt == "%Y-%m-%d"
    assert detect_date_format(["2026/07/20"]).fmt == "%Y/%m/%d"


def test_month_first_us_disambiguated_by_second_field_gt_12():
    from finbreak.importers.date_detect import detect_date_format

    guess = detect_date_format(["07/20/2026", "07/21/2026"])
    assert guess.fmt == "%m/%d/%Y"
    assert guess.ambiguous is False


def test_dotted_both_directions():
    from finbreak.importers.date_detect import detect_date_format

    assert detect_date_format(["20.07.2026"]).fmt == "%d.%m.%Y"
    assert detect_date_format(["07.20.2026"]).fmt == "%m.%d.%Y"


def test_dotted_all_days_le_12_is_ambiguous():
    """A US-dotted statement must not be read day-first silently — the tie fires."""
    from finbreak.importers.date_detect import detect_date_format

    guess = detect_date_format(["05.06.2026", "07.08.2026"])
    assert guess.fmt == "%d.%m.%Y"  # fixed-order winner
    assert guess.ambiguous is True


def test_two_digit_year_ambiguity_fires_the_nudge():
    from finbreak.importers.date_detect import detect_date_format

    guess = detect_date_format(["05/06/26", "07/08/26"])
    assert guess.fmt == "%d/%m/%y"
    assert guess.ambiguous is True


def test_ambiguous_all_days_le_12_winner_is_fixed_order():
    from finbreak.importers.date_detect import detect_date_format

    guess = detect_date_format(["05/06/2026", "07/08/2026"])
    assert guess.ambiguous is True
    assert guess.fmt == "%d/%m/%Y"  # day-first, ahead of %m/%d/%Y in the list


def test_named_month_variants():
    from finbreak.importers.date_detect import detect_date_format

    assert detect_date_format(["20 Jul 2026"]).fmt == "%d %b %Y"
    assert detect_date_format(["20 July 2026"]).fmt == "%d %B %Y"
    assert detect_date_format(["Jul 20, 2026"]).fmt == "%b %d, %Y"
    assert detect_date_format(["20-Jul-2026"]).fmt == "%d-%b-%Y"


def test_two_and_four_digit_year_cleanly_separated_no_guard():
    """`%Y` needs 4 digits, `%y` 2 — strptime separates them, no year window."""
    from finbreak.importers.date_detect import detect_date_format

    two = detect_date_format(["20/07/26"])
    assert two.fmt == "%d/%m/%y"
    assert two.ambiguous is False

    four = detect_date_format(["20/07/2026"])
    assert four.fmt == "%d/%m/%Y"

    # A dashed 2-digit year is slash-only in the known list -> unmatched.
    assert detect_date_format(["20-07-26"]).fmt is None


def test_no_match_returns_none():
    from finbreak.importers.date_detect import detect_date_format

    guess = detect_date_format(["not a date", "banana"])
    assert guess.fmt is None
    assert guess.ambiguous is False


def test_empty_and_blank_samples_return_none():
    from finbreak.importers.date_detect import detect_date_format

    assert detect_date_format([]).fmt is None
    assert detect_date_format(["", "  "]).fmt is None


def test_one_junk_row_does_not_veto_the_guess():
    """A single garbage cell must not stop the majority format winning."""
    from finbreak.importers.date_detect import detect_date_format

    guess = detect_date_format(["20/07/2026", "21/07/2026", "junk", "31/07/2026"])
    assert guess.fmt == "%d/%m/%Y"


def test_determinism_independent_of_sample_order():
    from finbreak.importers.date_detect import detect_date_format

    samples = ["05/06/2026", "07/08/2026", "09/10/2026"]
    first = detect_date_format(samples)
    second = detect_date_format(list(reversed(samples)))
    assert first == second


def test_clock_free_far_past_and_far_future(monkeypatch):
    """INV-2 falsifier: a hidden year window / date.today() would flip a
    decades-out year. Both a 1998 and a 2099 column must read day-first."""
    from finbreak.importers import date_detect
    from finbreak.importers.date_detect import detect_date_format

    # Poison the clock: any call to date.today() inside the detector explodes.
    class _NoClock:
        @staticmethod
        def today():  # pragma: no cover - must never be called
            raise AssertionError("detector must not read the clock (INV-2)")

    monkeypatch.setattr(date_detect, "date", _NoClock, raising=False)
    assert detect_date_format(["20/07/1998", "21/07/1998"]).fmt == "%d/%m/%Y"
    assert detect_date_format(["20/07/2099", "21/07/2099"]).fmt == "%d/%m/%Y"


def test_known_formats_are_ordered_iso_first_then_day_first():
    """INV-2: the list order is the ambiguity tiebreak, so ISO precedes the
    numeric day/month variants and day-first precedes month-first."""
    from finbreak.importers.date_detect import KNOWN_DATE_FORMATS

    fmts = [fmt for _example, fmt in KNOWN_DATE_FORMATS]
    assert fmts[0] == "%Y-%m-%d"
    assert fmts.index("%d/%m/%Y") < fmts.index("%m/%d/%Y")
    # Every example renders the fixed reference date 2026-07-20 (day 20, month 07).
    for example, fmt in KNOWN_DATE_FORMATS:
        from datetime import datetime

        parsed = datetime.strptime(example, fmt).date()
        assert (parsed.day, parsed.month) == (20, 7)
        assert parsed.year in (2026, 26)


# --------------------------------------------------------------------------- #
# Layer 2 — CsvImporter.parse friendly per-row date error (D3/INV-3).          #
# --------------------------------------------------------------------------- #


def _single_mapping(date_format: str = "%Y-%m-%d"):
    from finbreak.models import ColumnMapping

    return ColumnMapping("Date", "Details", "Amount", None, None, date_format, False)


def _csv(rows: list[list[str]]) -> str:
    header = "Date,Details,Amount\n"
    return header + "".join(",".join(r) + "\n" for r in rows)


def test_csv_bad_date_yields_friendly_rowerror_no_parser_internals():
    """INV-3: a row the format can't read surfaces `could not read the date
    "<raw>"` — the raw value, never the strptime/`%`-format internals."""
    from finbreak.importers.csv_importer import CsvImporter

    result = CsvImporter().parse(
        _csv([["20/07/2026", "Coffee", "-10.00"]]), _single_mapping(), 2
    )
    assert len(result.errors) == 1
    reason = result.errors[0].reason
    assert reason == 'could not read the date "20/07/2026"'
    assert "does not match format" not in reason
    # No parser format token leaks (a junk cell may embed a bare '%', so check
    # for the tokens, not a lone percent sign).
    for token in ("%Y", "%m", "%d", "%y", "%b", "%B"):
        assert token not in reason


def test_csv_percent_in_junk_date_cell_still_no_token_leak():
    """A cell like `50%` embeds a literal '%' in <raw> without a parser leak."""
    from finbreak.importers.csv_importer import CsvImporter

    result = CsvImporter().parse(
        _csv([["50%", "Coffee", "-10.00"]]), _single_mapping(), 2
    )
    assert result.errors[0].reason == 'could not read the date "50%"'
    for token in ("%Y", "%m", "%d"):
        assert token not in result.errors[0].reason


def test_csv_empty_date_cell_says_the_cell_is_empty():
    from finbreak.importers.csv_importer import CsvImporter

    result = CsvImporter().parse(_csv([["", "Coffee", "-10.00"]]), _single_mapping(), 2)
    assert result.errors[0].reason == "the date cell is empty"


def test_csv_amount_error_text_unregressed():
    """The date-parse split must not change the amount-error message (D3)."""
    from finbreak.importers.csv_importer import CsvImporter

    result = CsvImporter().parse(
        _csv([["2026-07-20", "Coffee", "not-a-number"]]), _single_mapping(), 2
    )
    assert len(result.errors) == 1
    assert "date" not in result.errors[0].reason.lower()
    assert result.errors[0].reason  # a human amount message, unchanged


def test_csv_valid_row_still_parses_INV6():
    """INV-6 no-regression anchor: the happy path is unchanged."""
    from finbreak.importers.csv_importer import CsvImporter

    result = CsvImporter().parse(
        _csv([["2026-07-20", "Coffee", "-10.00"]]), _single_mapping(), 2
    )
    assert result.errors == []
    assert len(result.drafts) == 1
    assert result.drafts[0].occurred_on == "2026-07-20"
    assert result.drafts[0].amount_minor == -1000


# --------------------------------------------------------------------------- #
# Layer 3 — _validate_mapping empty-format reject (D4, the 1900-01-01 trap).   #
# --------------------------------------------------------------------------- #


def test_empty_date_format_is_the_1900_trap():
    """Documents WHY the empty format is rejected: strptime('', '') succeeds and
    returns 1900-01-01, so a blank date cell under an empty format would import a
    phantom date rather than error."""
    from datetime import datetime

    assert datetime.strptime("", "").date().isoformat() == "1900-01-01"


@pytest.mark.parametrize("bad_format", ["", "   "])
def test_validate_mapping_rejects_empty_date_format(bad_format):
    from finbreak.models import ColumnMapping
    from finbreak.services.import_ import ImportService

    mapping = ColumnMapping("Date", "Details", "Amount", None, None, bad_format, False)
    with pytest.raises(ValueError, match="choose a date format"):
        ImportService._validate_mapping(mapping, ["Date", "Details", "Amount"])


def test_validate_mapping_accepts_a_real_date_format():
    from finbreak.models import ColumnMapping
    from finbreak.services.import_ import ImportService

    mapping = ColumnMapping("Date", "Details", "Amount", None, None, "%d/%m/%Y", False)
    ImportService._validate_mapping(mapping, ["Date", "Details", "Amount"])  # no raise


# --------------------------------------------------------------------------- #
# Layer 4 — the wizard picker / auto-detect / live preview / banner (qtbot).   #
# --------------------------------------------------------------------------- #
from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

from conftest import _PW, _acct  # noqa: E402
from finbreak.models import ColumnMapping  # noqa: E402
from finbreak.services.auth import AuthService  # noqa: E402

HEADER = ["Date", "Details", "Amount"]
_DAY_FIRST = [["20/07/2026", "Coffee", "-10.00"], ["21/07/2026", "Tea", "-5.00"]]


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _write(tmp_path: Path, header: list[str], rows: list[list[str]]) -> str:
    text = ",".join(header) + "\n" + "".join(",".join(r) + "\n" for r in rows)
    path = tmp_path / "stmt.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _wizard(qtbot, service, acct):
    from finbreak.ui.import_wizard import ImportWizardWidget

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    return widget


def test_autodetect_seeds_picker_day_first(qtbot, service, tmp_path):
    """The tester's bug: day-first dates now pre-select %d/%m/%Y, not the old
    ISO default — so the import lands rows instead of 165 errors."""
    acct = _acct(service)
    path = _write(tmp_path, HEADER, _DAY_FIRST)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    assert widget._stack.currentIndex() == 1, "unmatched -> map step"
    assert widget._date_format.currentData() == "%d/%m/%Y"


def test_regression_end_to_end_day_first_imports_rows(qtbot, service, tmp_path):
    """The whole point: a day-first statement imports cleanly (was all-errors)."""
    from finbreak.repositories.transactions import TransactionRepository

    acct = _acct(service)
    conn = service.vault.connection
    path = _write(tmp_path, HEADER, _DAY_FIRST)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)
    # Map the non-date roles (date column defaults to header[0] = "Date").
    widget._column_combos["description"].setCurrentIndex(
        widget._column_combos["description"].findData("Details")
    )
    widget._amount_style.setCurrentIndex(widget._amount_style.findData("single"))
    widget._column_combos["amount"].setCurrentIndex(
        widget._column_combos["amount"].findData("Amount")
    )
    widget._map_next_button.click()

    assert widget._error.text() == ""
    assert widget._preview.new_count == 2 and len(widget._preview.errors) == 0
    # INV-1: detection + preview commit NOTHING — the vault is still empty until
    # the explicit Import press (the irreversible write is the user's alone).
    assert TransactionRepository(conn).count_for_account(acct) == 0
    widget._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 2


def test_live_preview_reads_dates_and_flips_on_wrong_format(qtbot, service, tmp_path):
    acct = _acct(service)
    path = _write(tmp_path, HEADER, [["20/07/2026", "Coffee", "-10.00"]])
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    assert "2026-07-20" in widget._date_preview.text()
    assert "Dates read as" in widget._date_preview.text()
    # Force a wrong format -> the "couldn't be read" fallback.
    widget._date_format.setCurrentIndex(widget._date_format.findData("%m/%d/%Y"))
    assert "couldn't be read" in widget._date_preview.text()


def test_ambiguity_nudge_shows_then_clears_on_manual_pick(qtbot, service, tmp_path):
    acct = _acct(service)
    path = _write(
        tmp_path, HEADER, [["05/06/2026", "A", "-1.00"], ["07/08/2026", "B", "-2.00"]]
    )
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    assert widget._date_format.currentData() == "%d/%m/%Y"
    assert "the other way around" in widget._date_preview.text(), "ambiguity nudge"
    # A manual pick clears the nudge (never stale against a hand-chosen format).
    widget._date_format.setCurrentIndex(widget._date_format.findData("%m/%d/%Y"))
    assert "the other way around" not in widget._date_preview.text()


def test_two_preview_fallbacks_blank_and_junk(qtbot, service, tmp_path):
    acct = _acct(service)
    # All-blank date column -> "No dates found".
    blank = _write(tmp_path / "" if False else tmp_path, HEADER, [["", "A", "-1.00"]])
    widget = _wizard(qtbot, service, acct)
    widget._select_file(blank)
    assert "No dates found" in widget._date_preview.text()

    # Junk (non-date) column -> "couldn't be read", picker stays at ISO default.
    junk_path = tmp_path / "junk.csv"
    junk_path.write_text("Date,Details,Amount\nbanana,A,-1.00\n", encoding="utf-8")
    widget2 = _wizard(qtbot, service, acct)
    widget2._select_file(str(junk_path))
    assert widget2._date_format.currentData() == "%Y-%m-%d", "None -> ISO default"
    assert "couldn't be read" in widget2._date_preview.text()


def test_short_column_uses_clean_branch(qtbot, service, tmp_path):
    """<3 samples still gets the clean 'Dates read as' branch (all-shown gate)."""
    acct = _acct(service)
    path = _write(
        tmp_path, HEADER, [["20/07/2026", "A", "-1.00"], ["21/07/2026", "B", "-2.00"]]
    )
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)
    assert "Dates read as" in widget._date_preview.text()
    assert "couldn't be read" not in widget._date_preview.text()


def test_preview_refreshed_exactly_once_per_autodetect_fire(qtbot, service, tmp_path):
    acct = _acct(service)
    path = _write(tmp_path, HEADER, [["20/07/2026", "A", "-1.00"]])
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    calls = {"n": 0}
    original = widget._update_date_preview

    def _counting():
        calls["n"] += 1
        original()

    widget._update_date_preview = _counting  # type: ignore[method-assign]
    widget._on_date_column_changed(0)
    assert calls["n"] == 1, "one owner: the fire point refreshes once, not twice"


def test_custom_roundtrip_exotic_saved_format(qtbot, service, tmp_path):
    from finbreak.importers.date_detect import KNOWN_DATE_FORMATS
    from finbreak.services.import_ import ImportService

    acct = _acct(service)
    exotic = "%Y.%m.%d"
    assert exotic not in [fmt for _e, fmt in KNOWN_DATE_FORMATS]
    imp = ImportService(service.vault)
    imp.save_profile(
        "Exotic",
        HEADER,
        ColumnMapping("Date", "Details", "Amount", None, None, exotic, False),
    )
    profile = imp.match_profile(HEADER)

    widget = _wizard(qtbot, service, acct)
    widget._populate_mapping_combos(HEADER)
    widget._apply_profile_to_combos(profile)

    from finbreak.ui.import_wizard import _CUSTOM_FORMAT

    assert widget._date_format.currentData() is _CUSTOM_FORMAT
    assert widget._date_format_custom.text() == exotic
    # isHidden(), not isVisible(): the map page isn't shown in the test, but the
    # explicit-hide flag reflects the reveal regardless of ancestor visibility.
    assert not widget._date_format_custom.isHidden(), "INV-4 shown + editable"
    assert widget._mapping_from_form().date_format == exotic, "no silent rewrite"


def test_empty_custom_format_rejected_on_map_next(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import _CUSTOM_FORMAT

    acct = _acct(service)
    path = _write(tmp_path, HEADER, [["20/07/2026", "Coffee", "-10.00"]])
    widget = _wizard(qtbot, service, acct)
    widget._select_file(path)

    widget._column_combos["description"].setCurrentIndex(
        widget._column_combos["description"].findData("Details")
    )
    widget._column_combos["amount"].setCurrentIndex(
        widget._column_combos["amount"].findData("Amount")
    )
    # Select "Custom…" and leave the field blank.
    widget._date_format.setCurrentIndex(widget._date_format.findData(_CUSTOM_FORMAT))
    widget._date_format_custom.setText("")
    widget._map_next_button.click()

    assert "choose a date format" in widget._error.text()
    assert widget._stack.currentIndex() == 1, "stays on the map step"


def test_matched_profile_is_authoritative(qtbot, service, tmp_path):
    """A matched profile's stored format wins and never re-runs auto-detect over
    the data (INV-4/D5). The date column is deliberately OFF column 0 so the
    programmatic date-combo set actually changes the index — masking it at index 0
    would let an unblocked _on_date_column_changed slip through untested."""
    from finbreak.services.import_ import ImportService

    header = ["Ref", "Date", "Amount"]  # date is NOT column 0
    acct = _acct(service)
    imp = ImportService(service.vault)
    imp.save_profile(
        "US",
        header,
        ColumnMapping("Date", "Ref", "Amount", None, None, "%m/%d/%Y", False),
    )
    profile = imp.match_profile(header)
    widget = _wizard(qtbot, service, acct)
    widget._date_ambiguous = True  # a stale flag a matched profile must clear
    widget._populate_mapping_combos(header)
    # Auto-detect must NOT fire while applying a matched profile (D5).
    calls = {"n": 0}
    widget._autodetect_date_format = lambda: calls.__setitem__("n", calls["n"] + 1)  # type: ignore[method-assign]
    widget._apply_profile_to_combos(profile)

    assert calls["n"] == 0, "matched profile does not re-run auto-detect over the data"
    assert widget._column_combos["date"].currentData() == "Date"
    assert widget._date_format.currentData() == "%m/%d/%Y", "profile format wins"
    assert widget._date_ambiguous is False, "matched profile is never ambiguous"


def test_whole_import_banner_D7(qtbot, service, tmp_path):
    from finbreak.importers.base import RowError
    from finbreak.services.import_ import ImportPreview

    acct = _acct(service)
    widget = _wizard(qtbot, service, acct)

    # isHidden() reflects the setVisible intent without showing the preview page.
    all_error = ImportPreview(acct, [], [RowError(1, "x")], 0, 0, None, None)
    widget._apply_preview_counts(all_error)
    assert not widget._preview_banner.isHidden(), "0 new · 0 dup · N error -> banner"

    from finbreak.models import TransactionDraft

    draft = TransactionDraft(1, "2026-07-20", -1000, "A")
    some_new = ImportPreview(acct, [draft], [], 1, 0, "2026-07-20", "2026-07-20")
    widget._apply_preview_counts(some_new)
    assert widget._preview_banner.isHidden(), "any success hides the banner"

    header_only = ImportPreview(acct, [], [], 0, 0, None, None)
    widget._apply_preview_counts(header_only)
    assert widget._preview_banner.isHidden(), "0·0·0 -> no banner (nothing failed)"


def test_date_column_change_redetects_off_column_0(qtbot, service, tmp_path):
    """D5c + on-entry-column dependency: date is NOT column 0, so on entry the
    picker stays at ISO and the preview can't read the junk col; selecting the
    real date column re-detects."""
    acct = _acct(service)
    path = tmp_path / "off.csv"
    path.write_text(
        "Ref,Posted,Amount\nR1,20/07/2026,-1.00\nR2,21/07/2026,-2.00\n",
        encoding="utf-8",
    )
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))

    assert widget._date_format.currentData() == "%Y-%m-%d", "col0 junk -> ISO default"
    assert "couldn't be read" in widget._date_preview.text()
    # Point the date column at the real date column -> re-detect.
    widget._column_combos["date"].setCurrentIndex(
        widget._column_combos["date"].findData("Posted")
    )
    assert widget._date_format.currentData() == "%d/%m/%Y"
    assert "2026-07-20" in widget._date_preview.text()


_PDF_HEADER = ["Date", "Details", "Amount"]
_PDF_DAY_FIRST = [
    _PDF_HEADER,
    ["20/07/2026", "Coffee", "-10.00"],
    ["21/07/2026", "Tea", "-5.00"],
]
_PDF_ISO = [
    _PDF_HEADER,
    ["2026-07-20", "Coffee", "-10.00"],
    ["2026-07-21", "Tea", "-5.00"],
]


def test_pdf_table_switch_redetects_D5b(qtbot, service, tmp_path):
    """D5(b): a PDF is serialised to the same self._text, so switching to a table
    with a different date layout re-detects the format + refreshes the preview for
    the new table (no stale reading). Exercises the untested _on_pdf_table_changed
    auto-detect fire point on real candidate tables."""
    acct = _acct(service)
    widget = _wizard(qtbot, service, acct)
    widget._pdf_candidates = [_PDF_DAY_FIRST, _PDF_ISO]

    widget._on_pdf_table_changed(0)
    assert widget._date_format.currentData() == "%d/%m/%Y"
    assert "2026-07-20" in widget._date_preview.text()

    widget._on_pdf_table_changed(1)
    assert widget._date_format.currentData() == "%Y-%m-%d", "re-detected for table 2"
    assert "2026-07-20" in widget._date_preview.text()


def test_pdf_matched_table_uses_profile_not_autodetect_D5b(qtbot, service, tmp_path):
    """D5(b) matched branch: a saved profile for the table wins (no auto-detect),
    and the caller still refreshes the preview."""
    from finbreak.services.import_ import ImportService

    acct = _acct(service)
    ImportService(service.vault).save_profile(
        "PdfBank",
        _PDF_HEADER,
        ColumnMapping("Date", "Details", "Amount", None, None, "%m/%d/%Y", False),
    )
    widget = _wizard(qtbot, service, acct)
    widget._pdf_candidates = [_PDF_DAY_FIRST]
    calls = {"n": 0}
    widget._autodetect_date_format = lambda: calls.__setitem__("n", calls["n"] + 1)  # type: ignore[method-assign]

    widget._on_pdf_table_changed(0)
    assert calls["n"] == 0, "a matched table uses the profile, never auto-detect"
    assert widget._date_format.currentData() == "%m/%d/%Y"


def test_added_strings_tr_wrapped_and_data_fixed_tokens(qtbot, service, tmp_path):
    """INV-5: the new user-facing strings go through tr(); the combo DATA values
    are the fixed % patterns (not the display example text)."""
    from finbreak.importers.date_detect import KNOWN_DATE_FORMATS

    src = Path("src/finbreak/ui/import_wizard.py").read_text(encoding="utf-8")
    # Each new user-facing phrase must be present AND reached through self.tr(
    # (the tr( may be on the line above for a wrapped literal, so allow a window).
    for phrase in (
        "Custom…",
        "No dates found in this column.",
        "the day and month might be",
        "None of the rows could be imported.",
    ):
        # SOME occurrence must be reached through self.tr( (a comment may also
        # mention the phrase, so scan every occurrence, not just the first).
        starts = [i for i in range(len(src)) if src.startswith(phrase, i)]
        assert starts, phrase
        assert any("self.tr(" in src[max(0, i - 70) : i] for i in starts), (
            f"{phrase} not tr-wrapped"
        )

    acct = _acct(service)
    widget = _wizard(qtbot, service, acct)  # keep a ref so the C++ combo survives
    combo = widget._date_format
    datas = [combo.itemData(i) for i in range(combo.count())]
    for _example, fmt in KNOWN_DATE_FORMATS:
        assert fmt in datas, "combo item DATA is the fixed % pattern"
