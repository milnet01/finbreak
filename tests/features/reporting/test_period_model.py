"""FIBR-0012 INV-3 — the pure period model.

`resolve_period` / `resolve_trend_months` are pure functions with an injected
`today`, so these tests are hermetic (no vault, no clock). Covers each of the
five modes, the January previous-month year-boundary, and the Feb-29 leap edge.
"""

from datetime import date

import pytest

from finbreak.services.reporting import (
    MODE_CURRENT_MONTH,
    MODE_PREVIOUS_MONTH,
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    MODE_YEAR_TO_DATE,
    ReportPrefs,
    resolve_period,
    resolve_trend_months,
)

pytestmark = pytest.mark.features

# A fixed "today" mid-month so previous/current-month and year-to-date all differ.
_TODAY = date(2026, 7, 12)


@pytest.mark.parametrize(
    "prefs, expected",
    [
        # previous-month: June 2026 (the whole month), from a July today.
        (ReportPrefs(MODE_PREVIOUS_MONTH), (date(2026, 6, 1), date(2026, 6, 30))),
        # current-month: July 2026, first..last day.
        (ReportPrefs(MODE_CURRENT_MONTH), (date(2026, 7, 1), date(2026, 7, 31))),
        # specific-month: that month exactly.
        (
            ReportPrefs(MODE_SPECIFIC_MONTH, year=2025, month=3),
            (date(2025, 3, 1), date(2025, 3, 31)),
        ),
        # year-to-date: Jan 1 .. today (inclusive), not end-of-year.
        (ReportPrefs(MODE_YEAR_TO_DATE), (date(2026, 1, 1), date(2026, 7, 12))),
        # specific-year: the whole calendar year.
        (
            ReportPrefs(MODE_SPECIFIC_YEAR, year=2024),
            (date(2024, 1, 1), date(2024, 12, 31)),
        ),
    ],
)
def test_resolve_period_each_mode(prefs, expected):
    assert resolve_period(prefs, _TODAY) == expected


def test_resolve_period_previous_month_crosses_year_boundary_in_january():
    """previous-month in January resolves to the prior December (year - 1)."""
    jan = date(2026, 1, 15)
    assert resolve_period(ReportPrefs(MODE_PREVIOUS_MONTH), jan) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )


def test_resolve_period_specific_month_leap_february_is_29_days():
    """A leap-February specific-month ends on the 29th, not the 28th."""
    assert resolve_period(
        ReportPrefs(MODE_SPECIFIC_MONTH, year=2024, month=2), _TODAY
    ) == (date(2024, 2, 1), date(2024, 2, 29))


def test_resolve_period_specific_month_non_leap_february_is_28_days():
    assert resolve_period(
        ReportPrefs(MODE_SPECIFIC_MONTH, year=2025, month=2), _TODAY
    ) == (date(2025, 2, 1), date(2025, 2, 28))


def test_resolve_period_unknown_mode_falls_back_to_previous_month():
    """A total function: a garbage mode resolves to the previous-month default
    (never raises) — the last line of defence behind the D2 pref fallback."""
    assert resolve_period(ReportPrefs("nonsense"), _TODAY) == (
        date(2026, 6, 1),
        date(2026, 6, 30),
    )


def test_resolve_trend_months_is_twelve_points_ending_at_period_oldest_first():
    """current-month July 2026 -> Aug 2025 .. Jul 2026 (12 pairs, oldest first)."""
    months = resolve_trend_months(ReportPrefs(MODE_CURRENT_MONTH), _TODAY)
    assert len(months) == 12
    assert months[0] == (2025, 8)
    assert months[-1] == (2026, 7)
    # strictly one-month-ascending, no gaps
    assert months == [
        (2025, 8),
        (2025, 9),
        (2025, 10),
        (2025, 11),
        (2025, 12),
        (2026, 1),
        (2026, 2),
        (2026, 3),
        (2026, 4),
        (2026, 5),
        (2026, 6),
        (2026, 7),
    ]


def test_resolve_trend_months_specific_year_is_that_years_jan_to_dec():
    months = resolve_trend_months(ReportPrefs(MODE_SPECIFIC_YEAR, year=2025), _TODAY)
    assert months == [(2025, m) for m in range(1, 13)]


def test_resolve_trend_months_previous_month_january_is_prior_calendar_year():
    """previous-month in January -> period end is prior December -> the trend
    window is exactly that prior calendar year, Jan..Dec."""
    jan = date(2026, 1, 15)
    months = resolve_trend_months(ReportPrefs(MODE_PREVIOUS_MONTH), jan)
    assert months == [(2025, m) for m in range(1, 13)]


def test_resolve_trend_months_year_to_date_ends_at_current_month():
    """year-to-date in July -> the 12-month window ends at July (its period end
    month), i.e. Aug (prev year) .. Jul."""
    months = resolve_trend_months(ReportPrefs(MODE_YEAR_TO_DATE), _TODAY)
    assert months[0] == (2025, 8)
    assert months[-1] == (2026, 7)
