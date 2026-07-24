"""Cash-flow forecast (FIBR-0171).

Two layers, split on the pure-vs-service seam (§7):

* ``project_forecast`` — a **pure**, clock-free projection core. It takes an
  ``anchor_minor`` (``None`` ⇒ NET_FLOW), prepared signed-integer ``ForecastInput``s,
  ``today``, an inclusive ``horizon`` date, and the service-built ``anchor_sources``
  it just carries onto the result. It generates each item's future occurrences by
  **reusing** FIBR-0142's calendar-aware ``_add_cadence`` stepper, merges + stable-
  sorts the events, accumulates the running balance, and builds the step line. There
  is **no ``Decimal`` and no exponent** in this function — money is signed integer
  minor units throughout (money-safe, INV-1/D6/D7).

* ``ForecastService`` (later slice) composes the current-balance anchor from the
  persisted statement balances + the post-statement transaction roll-forward, reads
  the confirmed recurring set, does the one exact amount→minor conversion per item,
  and calls ``project_forecast``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from finbreak.models import (
    AnchorSource,
    Cadence,
    Direction,
    Forecast,
    ForecastEvent,
    ForecastMode,
    ForecastPoint,
)
from finbreak.services.recurring import _add_cadence


@dataclass
class ForecastInput:
    """One confirmed recurring item prepared for projection (FIBR-0171 D6): a
    Decimal-free, exponent-free input. ``amount_minor`` is **signed** (``+`` for IN,
    ``-`` for OUT — the service applies the sign once). Not persisted."""

    amount_minor: int
    next_expected: date
    cadence: Cadence
    merchant: str
    direction: Direction


def _occurrences(item: ForecastInput, today: date, horizon: date) -> list[date]:
    """Every occurrence of ``item`` strictly after ``today`` and no later than
    ``horizon`` (the disjoint ``(today, horizon]`` window, D6). Starts at
    ``next_expected``, rolls forward with ``_add_cadence`` while ``<= today``, then
    emits while ``<= horizon``. Termination is guaranteed — every ``_add_cadence``
    step advances the date by ≥ 7 days."""
    when = item.next_expected
    while when <= today:
        when = _add_cadence(when, item.cadence)
    dates: list[date] = []
    while when <= horizon:
        dates.append(when)
        when = _add_cadence(when, item.cadence)
    return dates


def project_forecast(
    anchor_minor: int | None,
    items: list[ForecastInput],
    today: date,
    horizon: date,
    anchor_sources: list[AnchorSource] | None = None,
) -> Forecast:
    """Project the balance from ``anchor_minor`` over ``items`` to ``horizon`` (D6).

    ``anchor_minor is None`` ⇒ ``NET_FLOW`` (start 0); otherwise ``ANCHORED``. Events
    are the merged occurrences of every item, **stable-sorted** by ``(on, merchant,
    direction)`` before the running balance accumulates. ``points`` is ``(today,
    start)`` + one ``(on, running_after)`` per event + a terminal ``(horizon, end)``,
    so a zero-event forecast still draws a flat two-point line (INV-13). Pure: no
    clock, no I/O, no ``Decimal``.
    """
    mode = ForecastMode.NET_FLOW if anchor_minor is None else ForecastMode.ANCHORED
    start_minor = 0 if anchor_minor is None else anchor_minor
    sources = list(anchor_sources) if anchor_sources is not None else []

    # (on, merchant, direction, signed amount) for every occurrence of every item.
    raw: list[tuple[date, str, Direction, int]] = []
    for item in items:
        for on in _occurrences(item, today, horizon):
            raw.append((on, item.merchant, item.direction, item.amount_minor))
    # Stable sort over (on, merchant, direction.value); ties keep input order (D6).
    raw.sort(key=lambda e: (e[0], e[1], e[2].value))

    events: list[ForecastEvent] = []
    running = start_minor
    for on, merchant, direction, amount_minor in raw:
        running += amount_minor
        events.append(ForecastEvent(on, merchant, direction, amount_minor, running))

    end_minor = running  # == start_minor + Σ amount_minor (INV-1)
    points = [ForecastPoint(today, start_minor)]
    points += [ForecastPoint(e.on, e.running_after_minor) for e in events]
    points.append(ForecastPoint(horizon, end_minor))

    return Forecast(
        mode=mode,
        start_minor=start_minor,
        end_minor=end_minor,
        horizon=horizon,
        points=points,
        events=events,
        anchor_sources=sources,
    )
