"""FIBR-0171 — the pure projection core `project_forecast` (spec D6).

Clock-free (``today`` is a parameter), no I/O, **no Decimal** — signed integer
minor units only. Reuses FIBR-0142's `_add_cadence` occurrence stepper.

Enforces tests/features/forecast/spec.md INV-1/2/4/5/11/13.
"""

from datetime import date

import pytest

from finbreak.models import Cadence, Direction, ForecastMode
from finbreak.services.forecast import ForecastInput, project_forecast

pytestmark = pytest.mark.features


def _item(
    amount_minor: int,
    next_expected: str,
    cadence: Cadence = Cadence.MONTHLY,
    merchant: str = "Acme",
    direction: Direction | None = None,
) -> ForecastInput:
    if direction is None:
        direction = Direction.IN if amount_minor >= 0 else Direction.OUT
    return ForecastInput(
        amount_minor=amount_minor,
        next_expected=date.fromisoformat(next_expected),
        cadence=cadence,
        merchant=merchant,
        direction=direction,
    )


# --------------------------------------------------------------------------- #
# INV-1 — end == start + Σ signed event amounts (exact integer), both modes
# --------------------------------------------------------------------------- #
def test_INV1_anchored_end_is_start_plus_sum() -> None:
    items = [
        _item(100_000, "2026-01-10", Cadence.MONTHLY, "Salary", Direction.IN),
        _item(-30_000, "2026-01-05", Cadence.MONTHLY, "Rent", Direction.OUT),
    ]
    fc = project_forecast(50_000, items, date(2026, 1, 1), date(2026, 3, 31))
    assert fc.mode is ForecastMode.ANCHORED
    assert fc.start_minor == 50_000
    assert fc.end_minor == fc.start_minor + sum(e.amount_minor for e in fc.events)


def test_INV1_netflow_end_is_zero_plus_sum() -> None:
    items = [_item(100_000, "2026-01-10", Cadence.MONTHLY, "Salary", Direction.IN)]
    fc = project_forecast(None, items, date(2026, 1, 1), date(2026, 3, 31))
    assert fc.start_minor == 0
    assert fc.end_minor == sum(e.amount_minor for e in fc.events)


# --------------------------------------------------------------------------- #
# INV-2 — mode switch: NET_FLOW ⟺ anchor is None; start 0; anchor_sources []
# --------------------------------------------------------------------------- #
def test_INV2_none_anchor_is_netflow_start_zero_empty_sources() -> None:
    fc = project_forecast(None, [], date(2026, 1, 1), date(2026, 1, 31))
    assert fc.mode is ForecastMode.NET_FLOW
    assert fc.start_minor == 0
    assert fc.anchor_sources == []


def test_INV2_present_anchor_is_anchored() -> None:
    fc = project_forecast(12_345, [], date(2026, 1, 1), date(2026, 1, 31))
    assert fc.mode is ForecastMode.ANCHORED
    assert fc.start_minor == 12_345


def test_INV2_anchor_sources_carried_through() -> None:
    from finbreak.models import AnchorSource

    src = AnchorSource(1, "Cheque", 40_000, date(2026, 1, 1), 2, 42_000)
    fc = project_forecast(
        42_000, [], date(2026, 1, 1), date(2026, 1, 31), anchor_sources=[src]
    )
    assert fc.anchor_sources == [src]


# --------------------------------------------------------------------------- #
# INV-4 — projection window (today, horizon]; _add_cadence stepping + clamp
# --------------------------------------------------------------------------- #
def test_INV4_rolls_forward_past_a_stale_next_expected() -> None:
    # next_expected is months before today: roll with _add_cadence until strictly
    # after today, then emit within the horizon.
    item = _item(-1_000, "2026-01-01", Cadence.MONTHLY)
    fc = project_forecast(0, [item], date(2026, 3, 15), date(2026, 5, 31))
    dates = [e.on for e in fc.events]
    assert dates == [date(2026, 4, 1), date(2026, 5, 1)]
    assert all(e.on > date(2026, 3, 15) for e in fc.events)  # strictly after today


def test_INV4_monthly_clamps_jan31_to_feb28() -> None:
    item = _item(-1_000, "2026-01-31", Cadence.MONTHLY)
    fc = project_forecast(0, [item], date(2026, 1, 20), date(2026, 2, 28))
    assert [e.on for e in fc.events] == [date(2026, 1, 31), date(2026, 2, 28)]


def test_INV4_every_event_is_in_the_half_open_window() -> None:
    item = _item(500, "2026-01-08", Cadence.WEEKLY)
    today, horizon = date(2026, 1, 1), date(2026, 2, 1)
    fc = project_forecast(0, [item], today, horizon)
    assert fc.events, "the weekly item produces events"
    assert all(today < e.on <= horizon for e in fc.events)


def test_INV4_event_on_the_horizon_is_included() -> None:
    item = _item(500, "2026-01-08", Cadence.WEEKLY)
    fc = project_forecast(0, [item], date(2026, 1, 1), date(2026, 1, 8))
    assert [e.on for e in fc.events] == [date(2026, 1, 8)]  # boundary inclusive


def test_INV4_occurrence_on_today_is_excluded_no_double_count() -> None:
    # The disjoint-window money-safety guard: a flow dated exactly today is already
    # owned by the anchor's (period_end, today] window (D1), so projecting it too
    # would count it twice. next_expected == today must roll to the next cadence.
    # (Falsifier: weakening `while when <= today` to `< today` keeps the on-today
    # occurrence and this test goes red.)
    item = _item(500, "2026-01-08", Cadence.WEEKLY)
    today = date(2026, 1, 8)
    fc = project_forecast(0, [item], today, date(2026, 1, 31))
    dates = [e.on for e in fc.events]
    assert today not in dates
    assert dates[0] == date(2026, 1, 15)  # first is strictly after today


# --------------------------------------------------------------------------- #
# INV-5 — signs: IN raises, OUT lowers; event sign matches its direction
# --------------------------------------------------------------------------- #
def test_INV5_in_raises_out_lowers_and_signs_match_direction() -> None:
    items = [
        _item(20_000, "2026-01-05", Cadence.MONTHLY, "Pay", Direction.IN),
        _item(-8_000, "2026-01-06", Cadence.MONTHLY, "Bill", Direction.OUT),
    ]
    fc = project_forecast(0, items, date(2026, 1, 1), date(2026, 1, 31))
    by_dir = {e.direction: e for e in fc.events}
    assert by_dir[Direction.IN].amount_minor > 0
    assert by_dir[Direction.OUT].amount_minor < 0
    # The IN event's running_after is above the start; OUT would be below its input.
    assert fc.end_minor == 20_000 - 8_000


# --------------------------------------------------------------------------- #
# INV-13 — step-line consistency
# --------------------------------------------------------------------------- #
def test_INV13_step_line_shape_and_running_totals() -> None:
    items = [
        _item(10_000, "2026-01-10", Cadence.MONTHLY, "A", Direction.IN),
        _item(-3_000, "2026-01-20", Cadence.MONTHLY, "B", Direction.OUT),
    ]
    today, horizon = date(2026, 1, 1), date(2026, 2, 28)
    fc = project_forecast(5_000, items, today, horizon)

    assert len(fc.points) == 2 + len(fc.events)
    assert (fc.points[0].on, fc.points[0].balance_minor) == (today, 5_000)
    assert (fc.points[-1].on, fc.points[-1].balance_minor) == (horizon, fc.end_minor)
    # dates non-decreasing
    assert all(
        fc.points[i].on <= fc.points[i + 1].on for i in range(len(fc.points) - 1)
    )
    # each interior point equals its event's running total, in event order
    for point, event in zip(fc.points[1:-1], fc.events, strict=True):
        assert point.on == event.on
        assert point.balance_minor == event.running_after_minor


def test_INV13_zero_event_forecast_still_has_two_points() -> None:
    fc = project_forecast(7_000, [], date(2026, 1, 1), date(2026, 1, 31))
    assert len(fc.points) == 2
    assert fc.points[0].balance_minor == 7_000
    assert fc.points[-1].balance_minor == 7_000  # flat line to the horizon


# --------------------------------------------------------------------------- #
# INV-11 — horizon boundaries; the degenerate horizon == today (zero width)
# --------------------------------------------------------------------------- #
def test_INV11_horizon_equal_today_is_zero_width_not_an_error() -> None:
    item = _item(1_000, "2026-01-05", Cadence.MONTHLY)
    same = date(2026, 1, 31)
    fc = project_forecast(9_000, [item], same, same)
    assert fc.events == []  # empty (today, today] window
    assert len(fc.points) == 2
    assert fc.points[0].on == fc.points[-1].on == same
    assert fc.start_minor == fc.end_minor == 9_000


# --------------------------------------------------------------------------- #
# INV-4a — a month-end item keeps its day-of-month; the clamp does not ratchet
# --------------------------------------------------------------------------- #
def test_INV4a_month_end_item_does_not_ratchet_down() -> None:
    """A 31st debit order must project onto 28/29 Feb and then back onto the
    31st — not onto the 28th forever.

    `_occurrences` stepped `when = _add_cadence(when, ...)`, and `_add_months`
    clamps the day to the target month's length. Feeding the clamped date back in
    as the next step's input loses the anchor day permanently, so a Jan-31 item
    emitted 02-28, 03-28, 04-28 in a common year and 02-29, 03-29, 04-29 in a leap
    one — the same standing order landing on a different day depending on
    February. INV-4 only ever pinned the FIRST clamp, which is why this survived.

    Month-end is the most common standing-order date, and the tab exists to
    answer "will I be short before month-end?", so a 3-day drift is a wrong
    answer on exactly the days that matter.
    """
    # Anchor on 2027-01-31, project across a common year.
    fc = project_forecast(
        0, [_item(-12_500_00, "2027-01-31")], date(2027, 1, 30), date(2027, 5, 15)
    )
    assert [e.on.isoformat() for e in fc.events] == [
        "2027-01-31",
        "2027-02-28",
        "2027-03-31",
        "2027-04-30",
    ]

    # The same item in a leap year must differ ONLY in the February date.
    leap = project_forecast(
        0, [_item(-12_500_00, "2028-01-31")], date(2028, 1, 30), date(2028, 5, 15)
    )
    assert [e.on.isoformat() for e in leap.events] == [
        "2028-01-31",
        "2028-02-29",
        "2028-03-31",
        "2028-04-30",
    ]


def test_INV4a_weekly_and_fortnightly_stepping_unchanged() -> None:
    """The fixed-day cadences never clamp, so the anchored stepping must give
    exactly what the old repeated stepping gave."""
    weekly = project_forecast(
        0,
        [_item(-100_00, "2027-01-07", cadence=Cadence.WEEKLY)],
        date(2027, 1, 6),
        date(2027, 2, 4),
    )
    assert [e.on.isoformat() for e in weekly.events] == [
        "2027-01-07",
        "2027-01-14",
        "2027-01-21",
        "2027-01-28",
        "2027-02-04",
    ]
