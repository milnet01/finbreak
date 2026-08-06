"""FIBR-0231 — ``MonthSummaryStrip``, fed hand-constructed ``MonthSummary`` values.

No service is involved in this file at all: that *is* INV-12's render leg — the
strip owns every template, so the whole feature's prose is testable with no vault
and no translation context.

Enforces INV-12's render leg, INV-14 (the 18 templates + the positive
no-signed-amount leg), INV-9's template-**selection** leg (the detector cannot
select a template, so a strip keying slot 3 off ``movement`` would pass a
detector-only INV-9), the ``residual_minor is None`` omission, ``isHidden()``
after ``clear()`` and on ``None``, § 4.6's ``PlainText`` and the 40-character
truncation.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QLabel

from finbreak.models import MonthCause, MonthSummary, MonthVerdict
from finbreak.services.transactions import to_display_decimal
from finbreak.ui._amount import _format_amount
from finbreak.ui.month_summary import MonthSummaryStrip

pytestmark = pytest.mark.features

_EXP = 2
_SYMBOL = "ZAR"


def minor(major: int) -> int:
    return major * 10**_EXP


def _cause(excess_major: int, name: str = "Vet") -> MonthCause:
    return MonthCause(
        merchant_key=name.casefold(), name=name, excess_minor=minor(excess_major)
    )


# A HIGHER complete June 2026 with no cause and no correction; each leg varies
# only the axes it is about.
_DEFAULT = MonthSummary(
    month="2026-06",
    partial=False,
    days=30,
    exponent=_EXP,
    show_year=False,
    verdict=MonthVerdict.HIGHER,
    spend_minor=minor(12340),
    baseline_minor=minor(10000),
    movement_minor=minor(2340),
    cause=None,
    residual_minor=None,
)


def _summary(**overrides) -> MonthSummary:
    return replace(_DEFAULT, **overrides)


def _strip(qtbot) -> MonthSummaryStrip:
    strip = MonthSummaryStrip()
    qtbot.addWidget(strip)
    return strip


def _text(strip: MonthSummaryStrip) -> str:
    label = strip.findChild(QLabel, "month_summary_text")
    assert label is not None
    return label.text()


def _render(qtbot, summary: MonthSummary) -> str:
    strip = _strip(qtbot)
    strip.set_summary(summary, _SYMBOL)
    return _text(strip)


def _amount(value_minor: int) -> str:
    """What the strip must render for ``value_minor`` — a MAGNITUDE, always."""
    return _format_amount(to_display_decimal(abs(value_minor), _EXP), _SYMBOL)


_JUNE = QLocale().standaloneMonthName(6)


# --------------------------------------------------------------------------- #
# INV-14 (a) — every reachable combination has a template, across ALL THREE slots
#
# The 18 are a UNION of three per-slot sets plus the two month forms, NOT a
# product: slot 2's and slot 3's conditions are the same quantity
# (residual = movement - excess), so a product sweep would construct
# `excess == movement` together with `residual < 0`, which is unreachable.
#
# Each leg asserts the rendered label CONTAINS that template's expected
# substring — not merely that the 18 labels are pairwise distinct. § 4.6 joins
# the slots into ONE QLabel, so a pairwise-distinctness assertion reads only the
# whole block, and an implementation that prefixes the joined block with a single
# "So far, " still produces 18 distinct labels while leaving slots 2 and 3 in
# unqualified past tense — precisely this invariant's *Breaks when*.
# --------------------------------------------------------------------------- #
_SLOT1 = [
    (
        "higher_complete",
        {"verdict": MonthVerdict.HIGHER},
        "more than your usual month.",
    ),
    (
        "higher_partial",
        {"verdict": MonthVerdict.HIGHER, "partial": True, "days": 12},
        "more than usual by this point.",
    ),
    (
        "lower_complete",
        {"verdict": MonthVerdict.LOWER, "movement_minor": -minor(2340)},
        "less than your usual month.",
    ),
    (
        "lower_partial",
        {
            "verdict": MonthVerdict.LOWER,
            "movement_minor": -minor(2340),
            "partial": True,
            "days": 12,
        },
        "less than usual by this point.",
    ),
    (
        "normal_complete",
        {"verdict": MonthVerdict.NORMAL, "movement_minor": 0},
        "looked like a normal month.",
    ),
    (
        "normal_partial",
        {
            "verdict": MonthVerdict.NORMAL,
            "movement_minor": 0,
            "partial": True,
            "days": 12,
        },
        "looks like a normal month.",
    ),
]

# Slot 2 splits THREE ways, not two. The equality case is where § 2.2's own
# flagship vault lands, and folding it into the ">" branch claims "and more"
# about a quantity that is exactly equal.
_SLOT2 = [
    (
        "less_complete",
        {"cause": _cause(1900), "residual_minor": minor(440)},
        "Most of it was one thing",
    ),
    (
        "less_partial",
        {
            "cause": _cause(1900),
            "residual_minor": minor(440),
            "partial": True,
            "days": 12,
        },
        "Most of it has been one thing",
    ),
    # excess == movement pins residual_minor None, so slot 3 is absent by
    # construction (§ 4.6) and the leg cannot be read as covering it.
    (
        "equal_complete",
        {"cause": _cause(2340), "residual_minor": None},
        "All of it was one thing",
    ),
    (
        "equal_partial",
        {"cause": _cause(2340), "residual_minor": None, "partial": True, "days": 12},
        "All of it has been one thing",
    ),
    (
        "more_complete",
        {"cause": _cause(2780), "residual_minor": -minor(440)},
        "All of it and more was one thing",
    ),
    (
        "more_partial",
        {
            "cause": _cause(2780),
            "residual_minor": -minor(440),
            "partial": True,
            "days": 12,
        },
        "All of it and more has been one thing",
    ),
]

_SLOT3 = [
    (
        "better_complete",
        {"cause": _cause(2780), "residual_minor": -minor(440)},
        "better than normal.",
    ),
    (
        "better_partial",
        {
            "cause": _cause(2780),
            "residual_minor": -minor(440),
            "partial": True,
            "days": 12,
        },
        "better than normal so far.",
    ),
    (
        "above_complete",
        {"cause": _cause(1900), "residual_minor": minor(440)},
        "Even without it you were",
    ),
    (
        "above_partial",
        {
            "cause": _cause(1900),
            "residual_minor": minor(440),
            "partial": True,
            "days": 12,
        },
        "Even without it you are",
    ),
]


@pytest.mark.parametrize(
    "overrides,expected",
    [(o, e) for _id, o, e in _SLOT1 + _SLOT2 + _SLOT3],
    ids=[i for i, _o, _e in _SLOT1 + _SLOT2 + _SLOT3],
)
def test_INV14a_each_slot_template_renders_its_own_wording(
    qtbot, overrides, expected
) -> None:
    assert expected in _render(qtbot, _summary(**overrides))


def test_INV14a_month_form_without_year(qtbot) -> None:
    """``show_year`` is computed by the service, which already has ``today`` — so
    this matrix is deterministic instead of depending on the system date."""
    text = _render(qtbot, _summary(show_year=False))
    assert _JUNE in text
    assert "2026" not in text


def test_INV14a_month_form_with_year(qtbot) -> None:
    text = _render(qtbot, _summary(show_year=True))
    assert f"{_JUNE} 2026" in text


def test_INV14a_only_slot_one_carries_the_literal_so_far_prefix(qtbot) -> None:
    """Slots 2 and 3 mark themselves provisional by TENSE, because all three
    render into one joined sentence and three "So far,"s in a row is not prose
    anyone wants to read."""
    text = _render(
        qtbot,
        _summary(partial=True, days=12, cause=_cause(1900), residual_minor=minor(440)),
    )
    assert text.count("So far,") == 1
    assert "has been one thing" in text  # slot 2 marked by tense
    assert "so far." in text  # slot 3 marked by tense


# --------------------------------------------------------------------------- #
# INV-14 (b) — no rendered amount carries a sign
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "overrides,value_minor",
    [
        ({"verdict": MonthVerdict.LOWER, "movement_minor": -minor(2340)}, -minor(2340)),
        ({"cause": _cause(2780), "residual_minor": -minor(440)}, -minor(440)),
        ({"cause": _cause(1900), "residual_minor": minor(440)}, minor(1900)),
    ],
    ids=["lower_movement", "negative_residual", "cause_excess"],
)
def test_INV14b_a_signed_field_renders_as_a_magnitude(
    qtbot, overrides, value_minor
) -> None:
    """Asserted positively rather than by character search: ``_format_amount``
    composes ``body = f"{sym} {magnitude}"`` and returns ``f"-{body}"`` or
    ``f"({body})"``, so a signed amount reads ``-R 500,00`` — whose character
    after the sign is the currency symbol, not a digit."""
    text = _render(qtbot, _summary(**overrides))
    expected = _amount(value_minor)
    assert expected in text
    assert f"-{expected}" not in text
    assert f"({expected})" not in text


# --------------------------------------------------------------------------- #
# INV-9 — the strip SELECTS the template by the sign of the residual
# --------------------------------------------------------------------------- #
def test_INV9_the_two_residual_signs_select_different_slot_three_templates(
    qtbot,
) -> None:
    """Both months are HIGHER with the same R1,900 excess, so a slot 3 keyed off
    ``movement`` renders the same sentence for both — which is exactly § 2.1's
    published error."""
    above = _render(
        qtbot,
        _summary(
            movement_minor=minor(2340), cause=_cause(1900), residual_minor=minor(440)
        ),
    )
    better = _render(
        qtbot,
        _summary(
            movement_minor=minor(1460), cause=_cause(1900), residual_minor=-minor(440)
        ),
    )
    assert "Even without it you were" in above
    assert "better than normal." in better
    assert above != better
    assert "better than normal" not in above


# --------------------------------------------------------------------------- #
# The render conditions — the strip evaluates no threshold of its own
# --------------------------------------------------------------------------- #
def test_a_null_residual_renders_no_third_sentence(qtbot) -> None:
    """``residual_minor is not None`` IS the render condition, precisely as
    ``cause is not None`` is slot 2's."""
    text = _render(qtbot, _summary(cause=_cause(2340), residual_minor=None))
    assert "All of it was one thing" in text
    assert "Take that out" not in text
    assert "Even without it" not in text


def test_no_cause_renders_the_verdict_alone(qtbot) -> None:
    text = _render(qtbot, _summary(cause=None, residual_minor=None))
    assert "more than your usual month." in text
    assert "one thing" not in text


def test_INV12_the_strip_renders_a_full_three_sentence_summary_with_no_service(
    qtbot,
) -> None:
    """The render leg: every template lives here, so the feature's prose is
    exercised from a hand-constructed value with no vault in sight."""
    text = _render(qtbot, _summary(cause=_cause(1900), residual_minor=minor(440)))
    assert _JUNE in text
    assert "more than your usual month." in text  # slot 1
    assert "Most of it was one thing — Vet," in text  # slot 2
    assert "Even without it you were" in text  # slot 3
    # One label, the slots joined by a single space — not three labels stacked.
    assert "month. Most" in text and "usual. Even" in text


# --------------------------------------------------------------------------- #
# Hiding
# --------------------------------------------------------------------------- #
def test_a_none_summary_hides_the_strip(qtbot) -> None:
    strip = _strip(qtbot)
    strip.set_summary(_summary(), _SYMBOL)
    assert strip.isHidden() is False
    strip.set_summary(None, _SYMBOL)
    assert strip.isHidden() is True


def test_clear_hides_the_strip_and_needs_no_symbol(qtbot) -> None:
    """``clear()`` exists because ``HomeView``'s ``except VaultLockedError``
    blocks have no ``symbol`` in scope — ``base_currency()`` is itself a vault
    read that would raise the same exception."""
    strip = _strip(qtbot)
    strip.set_summary(_summary(), _SYMBOL)
    assert strip.isHidden() is False
    strip.clear()
    assert strip.isHidden() is True


# --------------------------------------------------------------------------- #
# § 4.6 — the merchant name is PLAIN text, and it is the STRIP that truncates
# --------------------------------------------------------------------------- #
def test_a_markup_bearing_merchant_name_renders_literally(qtbot) -> None:
    """A description containing ``<b>`` or ``<img src=…>`` would otherwise be
    rendered as rich text by ``QLabel``'s default ``AutoText`` sniffing, showing
    something other than the user's transaction and attempting a resource load."""
    strip = _strip(qtbot)
    strip.set_summary(
        _summary(cause=_cause(1900, "<b>markup</b>"), residual_minor=minor(440)),
        _SYMBOL,
    )
    label = strip.findChild(QLabel, "month_summary_text")
    assert label is not None
    assert label.textFormat() is Qt.TextFormat.PlainText
    assert "<b>markup</b>" in label.text()


def test_a_long_merchant_name_truncates_to_thirty_nine_characters_plus_ellipsis(
    qtbot,
) -> None:
    """Plain CHARACTER truncation, deliberately not ``QFontMetrics.elidedText``,
    which measures pixels and would make the rendered sentence depend on the
    widget's width — and so make these assertions depend on layout."""
    long_name = "A" * 60
    text = _render(
        qtbot,
        _summary(cause=_cause(1900, long_name), residual_minor=minor(440)),
    )
    assert long_name not in text
    assert ("A" * 39) + "…" in text
