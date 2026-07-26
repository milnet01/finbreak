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

* ``ForecastService`` composes the current-balance anchor from the
  persisted statement balances + the post-statement transaction roll-forward, reads
  the confirmed recurring set, does the one exact amount→minor conversion per item,
  and calls ``project_forecast``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from finbreak.models import (
    AccountType,
    AnchorSource,
    Cadence,
    Direction,
    Forecast,
    ForecastEvent,
    ForecastMode,
    ForecastPoint,
    RecurringItem,
)
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.recurring import RecurringService, _add_cadence
from finbreak.services.transactions import read_minor_unit_exponent
from finbreak.vault import Vault

# The account types whose printed closing balance follows the canonical
# ``amount_minor`` convention (money out −, money in +), so bringing it current with
# ``balance + Σ amount_minor`` holds and the result is spendable cash. Everything
# else is excluded from the anchor (FIBR-0179): a debt product (credit card, home /
# personal loan) prints its closing in the **owed** convention — the opposite sign —
# so the roll-forward would move it the wrong way AND fold an owed figure into a cash
# total; an investment balance moves with the market, not with transactions; ``other``
# has no guaranteed convention. ``reconciliation.py`` gates on the same set for the
# same reason (FIBR-0177 D1) — keep the two in step.
CASH_TYPES = frozenset({AccountType.CURRENT, AccountType.SAVINGS})


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


class ForecastService:
    """Compose the cash-flow forecast over a vault (FIBR-0171 Deliverable 9).

    Builds the **brought-current** anchor — for each **cash** account (``CASH_TYPES``,
    FIBR-0179) with a persisted statement balance (its latest non-NULL closing
    balance), add the account's actual transactions in the half-open
    ``(period_end, today]`` window (D1/INV-13) — plus one ``AnchorSource`` per
    contributing account. Reads the **confirmed**
    recurring set (D5), converts each item's ``amount`` (a positive display Decimal)
    back to exact signed minor units once (D7), prepares ``ForecastInput``s, and
    calls the pure ``project_forecast``. The anchor is ``None`` (⇒ NET_FLOW) when no
    **cash** account (``CASH_TYPES``) has a recorded balance — a debt-only vault
    therefore runs in NET_FLOW too (FIBR-0179). Mirrors ``RecurringService`` —
    vault-wide.
    """

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    @property
    def _conn(self):
        return self._vault.connection

    def forecast(self, today: date, horizon: date) -> Forecast:
        anchor_minor, sources = self._anchor(today)
        items = self._inputs(today)
        return project_forecast(anchor_minor, items, today, horizon, sources)

    def _anchor(self, today: date) -> tuple[int | None, list[AnchorSource]]:
        """The vault-wide current-balance anchor + its provenance (D1/D10/INV-6/13),
        or ``(None, [])`` when no **cash** account has a recorded closing balance.
        Only ``CASH_TYPES`` accounts contribute (FIBR-0179); the Forecast tab already
        names the non-contributing accounts, so the exclusion is visible."""
        today_iso = today.isoformat()
        period_repo = StatementPeriodRepository(self._conn)
        txn_repo = TransactionRepository(self._conn)
        # account.type is the stored STR token — compare to the enum .values.
        cash_tokens = {t.value for t in CASH_TYPES}
        cash_names = {
            a.id: a.name
            for a in AccountRepository(self._conn).list_all()
            if a.type in cash_tokens
        }
        sources: list[AnchorSource] = []
        total = 0
        for (
            account_id,
            balance_minor,
            period_end,
        ) in period_repo.latest_closing_balances():
            if account_id not in cash_names:
                continue  # debt / investment / other — not spendable cash (FIBR-0179)
            roll_minor, since_count = txn_repo.sum_after(
                account_id, period_end, today_iso
            )
            current = balance_minor + roll_minor
            total += current
            sources.append(
                AnchorSource(
                    account_id=account_id,
                    account_name=cash_names[account_id],
                    statement_balance_minor=balance_minor,
                    as_of=date.fromisoformat(period_end),
                    since_txn_count=since_count,
                    current_balance_minor=current,
                )
            )
        if not sources:
            return None, []
        return total, sources

    def _inputs(self, today: date) -> list[ForecastInput]:
        """The confirmed recurring items prepared as signed-minor ``ForecastInput``s
        (D5/D7). Each ``RecurringItem.amount`` is a positive display Decimal =
        ``to_display_decimal(median_low_minor, exponent)``; converting it back with
        the same exponent recovers the exact minor integer (INV-7), and the direction
        applies the sign."""
        exponent = read_minor_unit_exponent(self._conn)
        confirmed = RecurringService(self._vault).confirmed(today)
        return [self._to_input(item, exponent) for item in confirmed]

    @staticmethod
    def _to_input(item: RecurringItem, exponent: int) -> ForecastInput:
        magnitude = int((item.amount * (10**exponent)).to_integral_value())
        signed = -magnitude if item.direction is Direction.OUT else magnitude
        return ForecastInput(
            amount_minor=signed,
            next_expected=item.next_expected,
            cadence=item.cadence,
            merchant=item.merchant,
            direction=item.direction,
        )
