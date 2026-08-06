"""FIBR-0231 — the pure detector ``summarise_month``.

Hermetic: no vault, no Qt, no clock. The detector is handed pre-summed windows
and an already-chosen candidate, so everything about *window construction* and
*candidate selection* lives in the service suite instead (spec § 7).

Enforces INV-1, INV-5, INV-6, INV-8, INV-9, plus the § 4.5 baseline-floor
derivation and the § 4.6 slot-3 materiality floor.

All fixtures are at exponent 2 (a two-decimal currency), so ``minor(100)`` is
10_000 and the § 4.8 floor ``minor(1000)`` is 100_000.
"""

from __future__ import annotations

import ast
import re
from dataclasses import replace
from pathlib import Path

import pytest

from finbreak.models import MonthCause, MonthVerdict
from finbreak.services import month_summary as _month_summary_module
from finbreak.services.month_summary import (
    _BASELINE_MONTHS,
    _MATERIAL_DEN,
    _MATERIAL_NUM,
    _MIN_ELAPSED_DAYS,
    _MIN_MONTH_BASELINE_MAJOR,
    _MIN_MOVE_MAJOR,
    MonthSummaryInput,
    summarise_month,
)

pytestmark = pytest.mark.features

_EXP = 2  # a two-decimal currency; minor(n) == n * 100
_BASE = 1_000_000  # R10,000 a month — comfortably over the § 4.8 floor


def minor(major: int) -> int:
    return major * 10**_EXP


# Clears all five § 4.8 silence conditions: three baseline months of R10,000, a
# complete 30-day June, R10,000 spent (so ``movement == 0`` and the verdict is
# NORMAL), no candidate. Each leg varies only the axis it is about.
_DEFAULT = MonthSummaryInput(
    month="2026-06",
    partial=False,
    days=30,
    show_year=False,
    spend_minor=_BASE,
    prior_minor=(_BASE, _BASE, _BASE),
    started=True,
    candidate=None,
)


def _input(**overrides) -> MonthSummaryInput:
    return replace(_DEFAULT, **overrides)


def _cause(excess_minor: int) -> MonthCause:
    return MonthCause(merchant_key="vet", name="Vet", excess_minor=excess_minor)


# --------------------------------------------------------------------------- #
# INV-1 — integer-only arithmetic
# --------------------------------------------------------------------------- #
_MODULE = Path(str(_month_summary_module.__file__))


def test_INV1a_every_returned_money_field_is_a_plain_int() -> None:
    """Leg (a) — a float that *escapes* into a returned field. The list is
    enumerated, not swept: ``partial`` / ``show_year`` are ``bool`` and
    ``type(True) is int`` is False, so a `dataclasses.fields` sweep would go red
    on correct output."""
    summary = summarise_month(
        _input(spend_minor=_BASE + minor(2000), candidate=_cause(minor(1500))), _EXP
    )
    assert summary is not None
    for value in (
        summary.days,
        summary.exponent,
        summary.spend_minor,
        summary.baseline_minor,
        summary.movement_minor,
    ):
        assert type(value) is int
    assert summary.cause is not None
    assert type(summary.cause.excess_minor) is int
    assert summary.residual_minor is None or type(summary.residual_minor) is int


def test_INV1b_module_names_no_decimal_or_float_constructor() -> None:
    """Leg (b) — the cheap tripwire. Matches the *constructor* form deliberately:
    a bare ``\\bDecimal\\b`` also matches the word in the module's own docstring,
    which says why the module holds none."""
    source = _MODULE.read_text(encoding="utf-8")
    assert re.findall(r"\bDecimal\(|\bfloat\(", source) == []


def test_INV1c_module_contains_no_true_division_and_no_float_literal() -> None:
    """Leg (c) — the catcher for the breach INV-1 actually names. An AST walk,
    not a grep: ``//`` is ``ast.FloorDiv`` and unaffected, and a grep for ``/``
    fights docstrings and path literals. The float-literal half is not
    redundant — ``abs(movement) >= baseline * 0.1`` contains no ``ast.Div``,
    no ``float(``, and returns a ``bool``, so it survives legs (a) and (b)."""
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    assert [n for n in ast.walk(tree) if isinstance(n, ast.Div)] == []
    floats = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and type(n.value) is float
    ]
    assert floats == []


# --------------------------------------------------------------------------- #
# INV-5 — the five silence conditions, each with a relaxed counterpart
# --------------------------------------------------------------------------- #
def test_INV5_condition1_fewer_than_three_baseline_months_is_silent() -> None:
    assert summarise_month(_input(prior_minor=(_BASE, _BASE)), _EXP) is None
    assert summarise_month(_input(prior_minor=(_BASE, _BASE, _BASE)), _EXP) is not None


def test_INV5_condition2_baseline_under_the_floor_is_silent() -> None:
    under = minor(_MIN_MONTH_BASELINE_MAJOR) - 1
    at = minor(_MIN_MONTH_BASELINE_MAJOR)
    assert (
        summarise_month(_input(prior_minor=(under,) * 3, spend_minor=under), _EXP)
        is None
    )
    assert (
        summarise_month(_input(prior_minor=(at,) * 3, spend_minor=at), _EXP) is not None
    )


def test_INV5_condition3_a_partial_month_says_nothing_before_day_seven() -> None:
    assert (
        summarise_month(_input(partial=True, days=_MIN_ELAPSED_DAYS - 1), _EXP) is None
    )
    assert (
        summarise_month(_input(partial=True, days=_MIN_ELAPSED_DAYS), _EXP) is not None
    )


def test_INV5_condition4_a_month_that_has_not_started_is_silent() -> None:
    """The fixture keeps ``spend_minor > 0`` — not because condition 5 would
    pre-empt condition 4 (it is *after* it), but because the **relaxed**
    counterpart sets ``started = True`` and must then return non-``None``. A
    future month genuinely can hold post-dated rows (§ 4.7)."""
    shape = {"partial": False, "days": 30, "spend_minor": minor(200)}
    assert summarise_month(_input(started=False, **shape), _EXP) is None
    assert summarise_month(_input(started=True, **shape), _EXP) is not None


def test_INV5_condition5_a_month_with_no_spend_row_is_silent() -> None:
    assert summarise_month(_input(spend_minor=0), _EXP) is None
    assert summarise_month(_input(spend_minor=_BASE), _EXP) is not None


# --------------------------------------------------------------------------- #
# INV-6 — NORMAL unless the movement is material (both gates)
# --------------------------------------------------------------------------- #
def test_INV6_gate_matrix_neither_absolute_only_both() -> None:
    """Three legs, not four: above the § 4.8 floor relative-pass *implies*
    absolute-pass at every exponent (§ 4.5), so the "relative only" cell is
    empty. A fixture written for it would fail the relative gate too and
    silently duplicate the "neither" leg."""
    relative_edge = _BASE * _MATERIAL_NUM // _MATERIAL_DEN  # 100_000
    absolute_edge = minor(_MIN_MOVE_MAJOR)  # 10_000
    assert absolute_edge < relative_edge  # the cell that makes three legs enough

    neither = summarise_month(_input(spend_minor=_BASE + absolute_edge - 1), _EXP)
    absolute_only = summarise_month(_input(spend_minor=_BASE + absolute_edge), _EXP)
    both = summarise_month(_input(spend_minor=_BASE + relative_edge), _EXP)
    assert neither is not None and absolute_only is not None and both is not None
    assert neither.verdict is MonthVerdict.NORMAL
    assert absolute_only.verdict is MonthVerdict.NORMAL
    assert both.verdict is MonthVerdict.HIGHER


def test_INV6_a_material_negative_movement_is_lower() -> None:
    summary = summarise_month(_input(spend_minor=_BASE - minor(2000)), _EXP)
    assert summary is not None
    assert summary.verdict is MonthVerdict.LOWER
    assert summary.movement_minor == -minor(2000)


# --------------------------------------------------------------------------- #
# INV-8 — a cause is attached only to a HIGHER verdict
# --------------------------------------------------------------------------- #
def test_INV8_a_lower_month_carries_no_cause_however_large_the_excess() -> None:
    """A single large *expense* cannot explain spending less, and the
    transaction that would explain a LOWER month is the one that is absent."""
    summary = summarise_month(
        _input(spend_minor=_BASE - minor(1000), candidate=_cause(minor(2000))), _EXP
    )
    assert summary is not None
    assert summary.verdict is MonthVerdict.LOWER
    assert summary.cause is None
    assert summary.residual_minor is None


def test_INV8_a_normal_month_carries_no_cause() -> None:
    summary = summarise_month(_input(candidate=_cause(minor(2000))), _EXP)
    assert summary is not None
    assert summary.verdict is MonthVerdict.NORMAL
    assert summary.cause is None


def test_INV8_a_candidate_below_the_cause_gate_is_not_attached() -> None:
    """movement R1,500 with a greatest excess of R500 — 100 × 50_000 is less
    than 60 × 150_000, so no family "explains" the move."""
    summary = summarise_month(
        _input(spend_minor=_BASE + minor(1500), candidate=_cause(minor(500))), _EXP
    )
    assert summary is not None
    assert summary.verdict is MonthVerdict.HIGHER
    assert summary.cause is None


# --------------------------------------------------------------------------- #
# INV-9 — the correction is signed by the RESIDUAL, not by the movement
# --------------------------------------------------------------------------- #
def test_INV9_residual_sign_is_movement_minus_excess_not_the_movement() -> None:
    """Both months are HIGHER (§ 2.1's error is reachable only there), and both
    clear the materiality gates. The same R1,900 excess leaves the first still
    over normal and the second under it — so a template keyed off ``movement``
    would render "better than normal" for both."""
    over = summarise_month(
        _input(spend_minor=_BASE + 234_000, candidate=_cause(190_000)), _EXP
    )
    under = summarise_month(
        _input(spend_minor=_BASE + 146_000, candidate=_cause(190_000)), _EXP
    )
    assert over is not None and under is not None
    assert over.verdict is MonthVerdict.HIGHER
    assert under.verdict is MonthVerdict.HIGHER
    assert over.movement_minor == 234_000
    assert under.movement_minor == 146_000
    assert over.residual_minor == 44_000  # still above normal
    assert under.residual_minor == -44_000  # genuinely better than normal


def test_INV9_the_under_fixture_is_also_the_excess_greater_than_movement_case() -> None:
    """190_000 is 130% of 146_000 — ``residual < 0`` and ``excess > movement``
    are the same condition, which is why slot 2's "Most of it" wording could not
    be left unconditional."""
    under = summarise_month(
        _input(spend_minor=_BASE + 146_000, candidate=_cause(190_000)), _EXP
    )
    assert under is not None and under.cause is not None
    assert under.cause.excess_minor > under.movement_minor


# --------------------------------------------------------------------------- #
# § 4.5 — the baseline floor is DERIVED, not chosen
# --------------------------------------------------------------------------- #
def test_baseline_floor_is_where_the_two_materiality_gates_cross() -> None:
    """Asserted directly on the constants because the behavioural leg that would
    have covered it does not exist: above the floor relative-pass implies
    absolute-pass, so there is no "relative only" fixture (INV-6)."""
    assert _MIN_MONTH_BASELINE_MAJOR == _MIN_MOVE_MAJOR * _MATERIAL_DEN // _MATERIAL_NUM


def test_baseline_average_is_the_integer_round_half_up_mean() -> None:
    """The same idiom ``detect_category_spikes`` uses, so the two features round
    identically: ``(sum(prior) + K // 2) // K``.

    Two things this leg has to get right, and an earlier version got both wrong.
    The expected value is a **literal**, not the formula re-typed — an expectation
    computed the way the code computes it is an identity, not a test. And the
    fixture's sum must be ``≡ 2 (mod 3)``: for a sum ``≡ 0`` or ``1``, plain
    truncation returns the identical answer, so the one mutation this invariant
    exists to catch survives it.
    """
    prior = (300_001, 300_001, 300_000)
    assert sum(prior) % _BASELINE_MONTHS == 2  # the residue that separates them
    summary = summarise_month(_input(prior_minor=prior, spend_minor=300_001), _EXP)
    assert summary is not None
    # 900_002 / 3 = 300_000.67 → 300_001 rounded half-up, 300_000 truncated.
    assert summary.baseline_minor == 300_001


# --------------------------------------------------------------------------- #
# § 4.6 — the DETECTOR owns slot 3's materiality floor
# --------------------------------------------------------------------------- #
def test_slot3_residual_one_minor_unit_under_the_floor_is_nulled() -> None:
    """Without the floor a residual of 40 minor units renders "Take that out and
    you were R0.40 better than normal.". ``residual_minor is None`` *is* the
    strip's render condition, so the strip evaluates no threshold."""
    summary = summarise_month(
        _input(
            spend_minor=_BASE + minor(2000),
            candidate=_cause(minor(2000) - (minor(_MIN_MOVE_MAJOR) - 1)),
        ),
        _EXP,
    )
    assert summary is not None
    assert summary.cause is not None
    assert summary.residual_minor is None


def test_slot3_residual_at_the_floor_is_carried() -> None:
    summary = summarise_month(
        _input(
            spend_minor=_BASE + minor(2000),
            candidate=_cause(minor(2000) - minor(_MIN_MOVE_MAJOR)),
        ),
        _EXP,
    )
    assert summary is not None
    assert summary.cause is not None
    assert summary.residual_minor == minor(_MIN_MOVE_MAJOR)


def test_no_cause_means_no_residual() -> None:
    summary = summarise_month(_input(spend_minor=_BASE + minor(2000)), _EXP)
    assert summary is not None
    assert summary.cause is None
    assert summary.residual_minor is None


# --------------------------------------------------------------------------- #
# The pass-through fields the strip formats without a vault handle
# --------------------------------------------------------------------------- #
def test_the_summary_carries_the_month_partial_days_exponent_and_show_year() -> None:
    summary = summarise_month(
        _input(month="2025-11", partial=True, days=12, show_year=True), _EXP
    )
    assert summary is not None
    assert (summary.month, summary.partial, summary.days) == ("2025-11", True, 12)
    assert (summary.exponent, summary.show_year) == (_EXP, True)
