"""FIBR-0231 — ``MonthSummaryService.summary`` over a real SQLCipher vault.

Everything about **window construction** and **candidate selection** lives here
rather than in the detector suite (spec § 7): the detector never performs the
windowing and is handed ``candidate`` already chosen, so a detector-level leg
for either would pass against an engine that windowed anything at all.

Enforces INV-2, INV-3, INV-4, INV-7, INV-10, INV-11, INV-12's grep leg,
INV-13 leg (c), and § 4.6's tie-break. No network, no real financial data
(`testing.md` § 6).
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from conftest import _PW
from finbreak.errors import VaultLockedError
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services import month_summary as _month_summary_module
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.month_summary import MonthSummaryService
from finbreak.services.reporting import (
    MODE_CURRENT_MONTH,
    MODE_PREVIOUS_MONTH,
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    MODE_YEAR_TO_DATE,
    ReportingService,
    ReportPrefs,
)
from finbreak.services.transactions import read_minor_unit_exponent, to_minor
from finbreak.services.transfer_detection import TransferDetectionService

pytestmark = pytest.mark.features

_EXP = 2  # ZAR


def minor(major: int) -> int:
    return major * 10**_EXP


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _acct(svc: AuthService, name: str = "Cheque", typ: str = "current") -> int:
    accounts = AccountService(svc.vault)
    existing = accounts.list_accounts()
    return existing[0].id if name == "Cheque" else accounts.add_account(name, typ).id


def _spend(svc: AuthService, account_id: int, day: str, major: int, desc: str) -> int:
    """One OUT row of ``major`` units (stored negative, as the app stores spend)."""
    return TransactionRepository(svc.vault.connection).add(
        account_id, day, -minor(major), desc
    )


def _month_prefs(year: int, month: int) -> ReportPrefs:
    return ReportPrefs(MODE_SPECIFIC_MONTH, year=year, month=month)


def _summary(svc: AuthService, prefs: ReportPrefs, today: date, accounts=None):
    return MonthSummaryService(svc.vault).summary(prefs, accounts, today)


# --------------------------------------------------------------------------- #
# Seeds
# --------------------------------------------------------------------------- #
def _seed_flow(
    svc: AuthService, account_id: int, months: list[tuple[int, int]]
) -> None:
    """The INV-3 vault: R250 of daily flow on days 1–20 of every month, **plus** a
    R7,000 debit order on each month's LAST day — a payment that recurs on the
    same nominal day of every month, which the bank pulls back to the 28th in
    February. Behaviour never changes across these months."""
    for year, month in months:
        for day in range(1, 21):
            _spend(svc, account_id, f"{year:04d}-{month:02d}-{day:02d}", 250, "Daily")
        last = calendar.monthrange(year, month)[1]
        _spend(svc, account_id, f"{year:04d}-{month:02d}-{last:02d}", 7000, "Landlord")


def _seed_four_months(
    svc: AuthService,
    account_id: int,
    months: list[tuple[int, int]],
    plan: dict[str, list[int]],
) -> None:
    """``plan`` maps a merchant description to its per-month major-unit spend, in
    the same order as ``months``. One row per merchant per month, all on day 5 —
    every window in these fixtures is a whole calendar month, so the day only has
    to be inside it."""
    for index, (year, month) in enumerate(months):
        for desc, amounts in plan.items():
            if amounts[index]:
                _spend(
                    svc, account_id, f"{year:04d}-{month:02d}-05", amounts[index], desc
                )


# The four windows used by every whole-month fixture below: M = April 2026, with
# January / February / March as its baselines; read on 15 May, so M is complete.
_FOUR = [(2026, 1), (2026, 2), (2026, 3), (2026, 4)]
_M_APRIL = _month_prefs(2026, 4)
_MAY = date(2026, 5, 15)


# --------------------------------------------------------------------------- #
# INV-2 — confirmed transfers are excluded from EVERY figure
# --------------------------------------------------------------------------- #
def test_INV2_a_confirmed_transfer_changes_no_figure(service) -> None:
    """The same vault, with and without one confirmed transfer pair, yields the
    identical ``MonthSummary`` — M's spend, every baseline month's spend, and
    the cause candidate set alike."""
    cheque = _acct(service)
    savings = _acct(service, "Savings", "savings")
    _seed_four_months(
        service,
        cheque,
        _FOUR,
        {"Grocer": [5000, 5000, 5000, 6500], "Landlord": [7000] * 4},
    )
    before = _summary(service, _M_APRIL, _MAY)
    assert before is not None

    # A transfer between two of the user's own accounts, inside M's window and
    # large enough to dominate every figure if it were counted as spending.
    debit = _spend(service, cheque, "2026-04-12", 9000, "Move out")
    credit = TransactionRepository(service.vault.connection).add(
        savings, "2026-04-12", minor(9000), "Move in"
    )
    TransferDetectionService(service.vault).confirm(debit, credit)

    assert _summary(service, _M_APRIL, _MAY) == before


# --------------------------------------------------------------------------- #
# INV-3 — a same-nominal-day monthly payment contributes NOTHING to movement
# --------------------------------------------------------------------------- #
def test_INV3_complete_february_compares_whole_months(service) -> None:
    """A common-day-count implementation returns ``+700000`` here: February's
    28th-day rent falls inside a 28-day truncated window and every other
    month's day-30/31 rent falls outside it. Whole calendar months have no
    such hole."""
    cheque = _acct(service)
    _seed_flow(service, cheque, [(2025, 11), (2025, 12), (2026, 1), (2026, 2)])
    summary = _summary(service, _month_prefs(2026, 2), date(2026, 3, 15))
    assert summary is not None
    assert summary.month == "2026-02"  # the month every slot-1 sentence names
    assert summary.partial is False
    assert summary.days == 28
    assert summary.movement_minor == 0


def test_INV3_partial_march_caps_its_head_below_every_windows_last_day(service) -> None:
    """``L_min = min(31, 28, 31, 31) = 28``, so the head is 27 even on the 29th:
    the cap excludes every window month's final day, so the debit order is
    outside all four windows rather than inside one."""
    cheque = _acct(service)
    _seed_flow(service, cheque, [(2025, 12), (2026, 1), (2026, 2), (2026, 3)])
    summary = _summary(service, _month_prefs(2026, 3), date(2026, 3, 29))
    assert summary is not None
    assert summary.month == "2026-03"
    assert summary.partial is True
    assert summary.days == 27  # NOT today.day (29) — capped at L_min - 1
    assert summary.movement_minor == 0


def test_INV3_a_leap_february_carries_twenty_nine_days(service) -> None:
    """Exercises ``calendar.monthrange``; the fixture years are pinned because a
    February's length depends on them."""
    cheque = _acct(service)
    _seed_flow(service, cheque, [(2027, 11), (2027, 12), (2028, 1), (2028, 2)])
    summary = _summary(service, _month_prefs(2028, 2), date(2028, 3, 15))
    assert summary is not None
    assert summary.month == "2028-02"
    assert summary.days == 29
    assert summary.movement_minor == 0


# --------------------------------------------------------------------------- #
# INV-4 — the mode ALLOW-list (not a deny-list)
# --------------------------------------------------------------------------- #
@pytest.fixture
def moded(service) -> AuthService:
    """One vault where all three month modes resolve to a summarisable month at
    ``today = 2026-03-15``: previous month = February (complete, baselines
    Nov/Dec/Jan), current month = March (partial, head 15), specific month =
    February. November is seeded because February's baselines reach back to it."""
    cheque = _acct(service)
    _seed_flow(
        service, cheque, [(2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3)]
    )
    return service


_MID_MARCH = date(2026, 3, 15)


@pytest.mark.parametrize(
    "prefs",
    [
        ReportPrefs(MODE_PREVIOUS_MONTH),
        ReportPrefs(MODE_CURRENT_MONTH),
        ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=2),
    ],
    ids=["previous_month", "current_month", "specific_month"],
)
def test_INV4_the_three_month_modes_are_summarised(moded, prefs) -> None:
    assert _summary(moded, prefs, _MID_MARCH) is not None


@pytest.mark.parametrize(
    "prefs",
    [
        ReportPrefs(MODE_YEAR_TO_DATE),
        ReportPrefs("nonsense"),
        ReportPrefs(MODE_SPECIFIC_MONTH, year=None, month=None),
    ],
    ids=["year_to_date", "unrecognised", "specific_month_unfilled"],
)
def test_INV4_every_other_mode_renders_nothing(moded, prefs) -> None:
    """A deny-list ("not a year mode") would summarise year-to-date and a garbage
    token as previous-month. The unfilled specific month is here for the same
    reason: ``resolve_period`` silently falls back while the selector still reads
    "Specific month"."""
    assert _summary(moded, prefs, _MID_MARCH) is None


def test_INV4_specific_year_is_rejected_by_the_MODE_GATE_not_by_the_ladder(
    service,
) -> None:
    """`MODE_SPECIFIC_YEAR` needs its own fixture, and the obvious one is a trap.
    ``resolve_period`` maps it to ``end = <year>-12-31``, so `M` is **December**
    — and read from inside that year December has not happened, so § 4.8
    condition 4 returns ``None`` whatever the mode gate does. Deleting the
    allow-list entirely would leave such a leg green.

    Reading from the following January makes December a complete, fully-baselined
    month: the ladder now passes end to end, and the only thing that can still
    return ``None`` is the mode gate itself."""
    cheque = _acct(service)
    months = [(2026, 9), (2026, 10), (2026, 11), (2026, 12)]
    _seed_four_months(service, cheque, months, {"Grocer": [5000, 5000, 5000, 6500]})
    after = date(2027, 1, 15)

    # The ladder is satisfied — the same December, asked for by month, speaks.
    assert _summary(service, _month_prefs(2026, 12), after) is not None
    # ...and asked for as a YEAR, it does not.
    assert _summary(service, ReportPrefs(MODE_SPECIFIC_YEAR, year=2026), after) is None


# --------------------------------------------------------------------------- #
# The three fields the SERVICE derives from the clock — month, show_year, started
#
# The detector and the strip are both handed these ready-made, so a leg in either
# of those files asserts only that a hand-supplied value travelled. Only here can
# the derivation itself go wrong.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "today,expected_show_year",
    [(date(2026, 5, 15), False), (date(2027, 1, 15), True)],
    ids=["same_year_as_today", "earlier_year_than_today"],
)
def test_show_year_is_true_exactly_when_M_is_not_this_year(
    service, today, expected_show_year
) -> None:
    """§ 4.6: "Which template applies is decided by ``MonthSummary.show_year``,
    computed by the service, which already has ``today``." Get it wrong and a
    month from a prior year renders as a bare "February cost you…"."""
    cheque = _acct(service)
    _seed_four_months(service, cheque, _FOUR, {"Grocer": [5000, 5000, 5000, 6500]})
    summary = _summary(service, _M_APRIL, today)
    assert summary is not None
    assert summary.month == "2026-04"
    assert summary.show_year is expected_show_year


def test_a_future_month_holding_post_dated_rows_is_silent(service) -> None:
    """§ 4.3's third state, at SERVICE level — INV-5's condition-4 leg is
    detector-level and is handed ``started`` by hand, so nothing else exercises
    the derivation. The month is reachable in two clicks (`home.py`'s year picker
    ranges to 9999) and a mistyped year books a real row into it.

    The relaxed counterpart reads the same vault from *after* September, so the
    leg cannot pass because the fixture was unsummarisable for some other
    reason.

    **`today` is the 15th, not the 5th, and that is load-bearing.** ``partial`` is
    ``started and today <= last``, so forcing ``started`` true also makes the
    month *partial* — and from the 5th the head would be 5 days, under
    ``_MIN_ELAPSED_DAYS``, so condition 3 would silence it and this leg would pass
    against the very mutation it exists to catch. From the 15th no other
    condition can fire and condition 4 is the only thing left."""
    cheque = _acct(service)
    months = [(2026, 6), (2026, 7), (2026, 8), (2026, 9)]
    # Three healthy baselines, and ONE post-dated row in the future month.
    _seed_four_months(service, cheque, months, {"Grocer": [5000, 5000, 5000, 500]})
    september = _month_prefs(2026, 9)

    assert _summary(service, september, date(2026, 8, 15)) is None  # not started
    assert _summary(service, september, date(2026, 10, 5)) is not None  # it has now


# --------------------------------------------------------------------------- #
# INV-7 — the cause is a family's EXCESS, never a raw row
# --------------------------------------------------------------------------- #
def test_INV7a_a_routine_bill_larger_than_the_movement_is_not_the_cause(
    service,
) -> None:
    """§ 2.2's vault. The largest single row is the R7,000 rent, present in all
    four months — its excess is 0, so it is not even a candidate. The grocer's
    R1,500 excess is 100% of the R1,500 movement."""
    cheque = _acct(service)
    _seed_four_months(
        service,
        cheque,
        _FOUR,
        {"Grocer": [5000, 5000, 5000, 6500], "Landlord": [7000] * 4},
    )
    summary = _summary(service, _M_APRIL, _MAY)
    assert summary is not None
    assert summary.movement_minor == minor(1500)
    assert summary.cause is not None
    assert summary.cause.merchant_key == "grocer"
    assert summary.cause.name == "Grocer"  # merchant_name() of the family's row in M
    assert summary.cause.excess_minor == minor(1500)
    # excess == movement, so the residual is 0 — below the slot-3 floor.
    assert summary.residual_minor is None


def test_INV7b_no_family_explaining_sixty_percent_of_the_move_yields_no_cause(
    service,
) -> None:
    """A movement of R1,500 spread across three unrelated merchants at R500
    excess each: the greatest excess is R500 and ``100 × 50_000 < 60 × 150_000``.
    The gate fails honestly rather than because there is no candidate at all."""
    cheque = _acct(service)
    _seed_four_months(
        service,
        cheque,
        _FOUR,
        {
            "Alpha": [5000, 5000, 5000, 5500],
            "Beta": [5000, 5000, 5000, 5500],
            "Gamma": [5000, 5000, 5000, 5500],
        },
    )
    summary = _summary(service, _M_APRIL, _MAY)
    assert summary is not None
    assert summary.verdict.value == "higher"
    assert summary.movement_minor == minor(1500)
    assert summary.cause is None


def test_INV7c_a_cause_family_with_baseline_spend_carries_its_excess_not_its_gross(
    service,
) -> None:
    """The only fixture shape that goes red when the **baseline** windows are read
    with ``rows_in_range`` (no ``description``, so every family's baseline is 0
    and ``excess`` collapses to gross spend). A suite whose cause families all
    have zero baseline spend stays green against exactly that regression."""
    cheque = _acct(service)
    _seed_four_months(
        service,
        cheque,
        _FOUR,
        {"Vet": [400, 400, 400, 1900], "Living": [10000, 10000, 10000, 10840]},
    )
    summary = _summary(service, _M_APRIL, _MAY)
    assert summary is not None
    assert summary.movement_minor == minor(2340)
    assert summary.cause is not None
    assert summary.cause.merchant_key == "vet"
    assert summary.cause.excess_minor == minor(1500)  # NOT minor(1900), the gross


def test_a_family_spread_over_several_rows_sums_before_the_gate(service) -> None:
    """The unit is the family, not the row: two R1,200 vet visits in M make one
    R2,400 excess that clears the gate, where neither row would on its own
    (``100 × 120_000 < 60 × 240_000``)."""
    cheque = _acct(service)
    _seed_four_months(service, cheque, _FOUR, {"Living": [10000, 10000, 10000, 10000]})
    _spend(service, cheque, "2026-04-03", 1200, "VET SURGERY")
    _spend(service, cheque, "2026-04-20", 1200, "vet surgery")
    summary = _summary(service, _M_APRIL, _MAY)
    assert summary is not None
    assert summary.movement_minor == minor(2400)
    assert summary.cause is not None
    assert summary.cause.merchant_key == "vet surgery"
    assert summary.cause.excess_minor == minor(2400)


def test_the_cause_name_comes_from_the_family_EARLIEST_row_in_M(service) -> None:
    """§ 4.6 pins the label to the family's earliest row "so the label cannot
    change between two refreshes of the same data".

    Making that observable takes care, and this is the one fixture shape that
    can: within a family, two rows normally yield the *same* ``merchant_name``,
    so which one supplies the label is invisible. A Unicode-decomposed spelling
    and a precomposed one differ as strings — ``merchant_name`` preserves the
    form — while ``normalise_text``'s NFC fold collapses them to one key. That is
    not a contrived case: `text.py`'s own docstring records it as the real
    PDF-versus-CSV import scenario the fold exists for."""
    from finbreak.text import merchant_name

    decomposed = "café rio"  # e + U+0301 COMBINING ACUTE
    precomposed = "café rio"  # U+00E9 LATIN SMALL LETTER E WITH ACUTE
    assert merchant_name(decomposed) != merchant_name(precomposed)  # else vacuous

    cheque = _acct(service)
    _seed_four_months(service, cheque, _FOUR, {"Living": [10000, 10000, 10000, 10000]})
    _spend(service, cheque, "2026-04-03", 1200, decomposed)  # EARLIEST
    _spend(service, cheque, "2026-04-20", 1200, precomposed)

    summary = _summary(service, _M_APRIL, _MAY)
    assert summary is not None
    assert summary.cause is not None
    assert summary.cause.merchant_key == "café rio"  # one family, not two
    assert summary.cause.name == merchant_name(decomposed)


# --------------------------------------------------------------------------- #
# § 4.6 — the tie-break (equal excesses resolve to the smaller merchant_key)
# --------------------------------------------------------------------------- #
def test_equal_excesses_resolve_to_the_lexicographically_smaller_key(service) -> None:
    """The fixture needs a third, **falling** family or the tie is unreachable:
    two new families at excess E and nothing else changing make ``movement = 2E``,
    and ``100·E >= 60·2E`` is false. Here Grocer falls R1,000, so the movement is
    R1,000 and the two R1,000 excesses each clear the gate.

    It cannot live in the detector file: ``MonthSummaryInput.candidate`` is a
    single, already-chosen ``MonthCause``."""
    cheque = _acct(service)
    _seed_four_months(
        service,
        cheque,
        _FOUR,
        {
            "Grocer": [5000, 5000, 5000, 4000],
            "Fuel": [3000, 3000, 3000, 3000],
            "AAA": [0, 0, 0, 1000],
            "ZZZ": [0, 0, 0, 1000],
        },
    )
    summary = _summary(service, _M_APRIL, _MAY)
    assert summary is not None
    assert summary.movement_minor == minor(1000)
    assert summary.cause is not None
    assert summary.cause.merchant_key == "aaa"
    assert summary.cause.excess_minor == minor(1000)


# --------------------------------------------------------------------------- #
# INV-10 — the strip's spend agrees with the tile below it
# --------------------------------------------------------------------------- #
def _tile_expenditure_minor(svc: AuthService, prefs: ReportPrefs, today: date) -> int:
    exponent = read_minor_unit_exponent(svc.vault.connection)
    tile = ReportingService(svc.vault).summary(prefs, None, today)
    return to_minor(tile.expenditure, exponent)


def test_INV10_a_complete_months_spend_equals_the_net_tiles_expenditure(
    service,
) -> None:
    """Includes one ``amount_minor == 0`` row — the only value § 4.5's rule and
    ``ReportingService.summary`` bucket differently. That row **documents** the
    agreement; it cannot make this leg red, because both definitions contribute
    ``0``.

    It also carries a plain **income** row, and that one can: spend is
    ``amount_minor < 0`` (§ 4.5), so a salary must raise neither side of this
    equality. Without it every row in the suite is an outflow, ``expenditure``
    equals the vault total, and the two definitions cannot be told apart."""
    cheque = _acct(service)
    _seed_four_months(
        service,
        cheque,
        _FOUR,
        {"Grocer": [5000, 5000, 5000, 6500], "Vet": [0, 0, 0, 400]},
    )
    TransactionRepository(service.vault.connection).add(
        cheque, "2026-04-09", 0, "Zero-value adjustment"
    )
    TransactionRepository(service.vault.connection).add(
        cheque,
        "2026-04-25",
        minor(30000),
        "Salary",  # income — never spend
    )
    summary = _summary(service, _M_APRIL, _MAY)
    assert summary is not None
    assert summary.spend_minor == _tile_expenditure_minor(service, _M_APRIL, _MAY)


def test_INV10_march_against_a_february_baseline_reads_the_whole_month(service) -> None:
    """The shape that pins § 4.4's complete-state half: ``L_min = 28 < len(M) =
    31``, and the spend on 29–31 March is inside a whole-month window and outside
    a common-day-count one. **M = February cannot pin it** — with
    ``L_min = min(28, 30, 31, 31) = 28 = len(M)``, February's own window is the
    whole of February under either rule."""
    cheque = _acct(service)
    months = [(2025, 12), (2026, 1), (2026, 2), (2026, 3)]
    _seed_four_months(service, cheque, months, {"Grocer": [5000, 5000, 5000, 5000]})
    for day in (29, 30, 31):
        _spend(service, cheque, f"2026-03-{day}", 400, "Late March")
    prefs = _month_prefs(2026, 3)
    today = date(2026, 4, 15)
    summary = _summary(service, prefs, today)
    assert summary is not None
    assert summary.days == 31
    assert summary.spend_minor == _tile_expenditure_minor(service, prefs, today)
    assert summary.spend_minor == minor(5000 + 3 * 400)


# --------------------------------------------------------------------------- #
# INV-11 — scoped to the same accounts as the tiles
# --------------------------------------------------------------------------- #
def test_INV11_a_single_account_selection_excludes_the_other_account(service) -> None:
    """Asserts *scoping*, not numeric equality with the tile — INV-10 owns that,
    for a complete M."""
    cheque = _acct(service)
    savings = _acct(service, "Savings", "savings")
    _seed_four_months(service, cheque, _FOUR, {"Grocer": [5000, 5000, 5000, 6500]})
    _seed_four_months(service, savings, _FOUR, {"Fuel": [3000, 3000, 3000, 3000]})

    all_accounts = _summary(service, _M_APRIL, _MAY, accounts=None)
    just_cheque = _summary(service, _M_APRIL, _MAY, accounts=frozenset({cheque}))
    assert all_accounts is not None and just_cheque is not None
    assert just_cheque.spend_minor == minor(6500)
    assert all_accounts.spend_minor == minor(6500 + 3000)
    assert just_cheque.spend_minor != all_accounts.spend_minor


# --------------------------------------------------------------------------- #
# INV-12 — the service emits no user-facing string (the grep leg)
# --------------------------------------------------------------------------- #
def test_INV12_the_service_module_holds_no_translation_call() -> None:
    """The optional ``_`` matters: § 8 alternative 1 names a ``_tr`` seam as the
    *precedented* design (``pdf_export.py``), so it is the likeliest breach, and
    ``\\btr\\(`` misses it — ``_`` is a word character, so there is no boundary
    before the ``t``."""
    source = Path(str(_month_summary_module.__file__)).read_text(encoding="utf-8")
    pattern = r"(^|[^A-Za-z0-9])_?tr\(|QCoreApplication"
    assert re.findall(pattern, source, flags=re.MULTILINE) == []


# --------------------------------------------------------------------------- #
# INV-13 leg (c) — a mid-render lock PROPAGATES, it does not degrade
# --------------------------------------------------------------------------- #
class _LockedVault:
    """A vault stand-in that is locked: reading ``connection`` raises, exactly as
    ``Vault.connection`` does after ``lock()``."""

    @property
    def connection(self):
        raise VaultLockedError("the vault is locked")


def test_INV13c_summary_propagates_vault_locked_rather_than_returning_a_partial(
    service,
) -> None:
    """A sentence about a fraction of the month, presented as the month, is
    exactly what catching here would produce."""
    locked = MonthSummaryService(_LockedVault())  # type: ignore[arg-type]
    with pytest.raises(VaultLockedError):
        locked.summary(_M_APRIL, None, _MAY)
