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

    guess = detect_date_format(
        ["20/07/2026", "21/07/2026", "31/07/2026", "02/08/2026"]
    )
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
