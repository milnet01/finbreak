"""Shared money-string presentation — output and input — plus direction tints.

The OUTPUT half (``_format_amount``, FIBR-0012 D10) was relocated verbatim out of
``ui/home.py`` so the dashboard tiles (``home.py``) and the relocated
Transactions table (``transactions.py``) share the one implementation
(coding.md § 1.3) — that half is a relocation, not a new abstraction. The trend
chart's bar-set colours reuse the same direction tints.

The INPUT half (``parse_amount_input``, FIBR-0219) is the mirror of it: the one
seam where a *typed* amount is read under the user's locale, so the field accepts
the number the app itself just displayed. It lives here rather than beside
``parse_transaction`` because that function — and the importers reusing it — must
stay locale-free, or a bank statement would import to different numbers on two
machines (FIBR-0219 INV-1). Not a claim about ``services/`` as a whole:
``services/pdf_export.py`` already imports ``_format_amount`` for display.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import cast

from PySide6.QtCore import QLocale
from PySide6.QtGui import QColor

from finbreak.models import NegativeStyle
from finbreak.services.auth import CURRENCY_SYMBOLS

# Direction tints for money display when colour is on (FIBR-0105 D3). Fixed
# mid-tones chosen to read on the dark-default theme (ADR-0010) and stay legible
# on light; palette-adaptive re-tinting is FIBR-0127.
_NEGATIVE_TEXT = QColor(224, 108, 117)  # soft red — money out
_POSITIVE_TEXT = QColor(152, 195, 121)  # soft green — money in

# The AMBIGUOUS shape (FIBR-0219 § 4.5 step 3): digits, then any number of
# separator-plus-digits groups, then a FINAL separator followed by exactly three
# digits — the one shape whose last separator could be either a thousands group
# or a decimal point. Only the tail is constrained: a run of one, two, four or
# more digits after the separator cannot be a group. The head is deliberately
# unbounded AND may itself carry separators, because "1,234.500" is the same
# 1000x error as "1234,500" wearing a thousands separator (measured).
_AMBIGUOUS_SHAPE = re.compile(r"^[+-]?\d+(?:[.,]\d+)*[.,]\d{3}$")

# Stripped before either convention reads the string. Qt is more lenient than its
# own groupSeparator() suggests — measured, en_ZA (groups with NBSP) and fr_FR
# (NNBSP) both accept a plain ASCII space — so removing only groupSeparator()
# would let Qt validate a string the rebuild then fails on. Stripping all three
# unconditionally is safe: no locale uses a space as a DECIMAL separator.
_SPACES = (" ", " ", " ")


# Above this an int stops fitting QLocale.toString's integer overload. Amounts are
# capped well inside it (services/transactions.py caps the MINOR units at 2**63-1),
# but a typed value reaching _render is not yet capped.
_TOSTRING_MAX = 2**63 - 1


def _grouped(value: Decimal, decimals: int) -> str:
    """``value`` rendered to ``decimals`` places, grouped under the current locale,
    EXACTLY.

    Never through ``float``. Amounts run to ``_MAX_AMOUNT_MINOR`` (2**63-1), far
    past float64's exact-integer range, so a stored ``92233720368547758.07``
    rendered as ``92 233 720 368 547 760,00`` -- wrong digits and wrong cents, on
    the screen a user checks their money against (FIBR-0327).

    The integer overload of ``QLocale.toString`` is exact and still applies the
    locale's own grouping rule, including the non-uniform ones (hi_IN groups
    ``1,23,45,678``), which hand-rolled three-digit chunking would lose. The
    fraction is separator-joined rather than re-formatted: it is already the
    exact digits ``Decimal.__format__`` produced.

    Past the integer overload's range the digits are emitted ungrouped rather
    than wrong.
    """
    locale = QLocale()
    text = f"{value:.{decimals}f}"
    negative = text.startswith("-")
    whole, _, frac = text.lstrip("-").partition(".")
    grouped = locale.toString(int(whole)) if int(whole) <= _TOSTRING_MAX else whole
    body = grouped + locale.decimalPoint() + frac if decimals else grouped
    return locale.negativeSign() + body if negative else body


def _format_amount(
    display: Decimal, symbol: str, negative_style: str = NegativeStyle.MINUS
) -> str:
    # We compose the display string ourselves: «display-symbol»␣«grouped-magnitude»
    # (FIBR-0153). The caller passes the base-currency ISO code as ``symbol``; we map
    # it to a display glyph (R for ZAR) via CURRENCY_SYMBOLS, falling back to the code
    # itself for an unmapped currency (degrade, never crash — INV-5).
    #
    # The magnitude uses QLocale().toString(x, "f", d) — a SYMBOL-FREE grouped number
    # (grouping / decimal separator stay locale-correct). We deliberately do NOT use
    # toCurrencyString(v, "", d): an empty-but-non-null symbol does not suppress the
    # symbol — Qt substitutes the ISO currency code under every non-C locale (e.g.
    # "USD1,234.50" under en_US), leaking a second currency indicator (FIBR-0153 INV-3).
    #
    # A stored amount reconstructs to a finite Decimal, so its exponent is an int.
    # The magnitude goes through `_grouped`, which never touches float — amounts
    # reach 2**63-1 minor units, past float64's exact-integer range (FIBR-0327).
    # Decimal places follow the display Decimal's own exponent, not the currency's
    # minor unit.
    #
    # The symbol is ALWAYS a one-space prefix (overriding QLocale's per-locale symbol
    # placement) to honour the user's "R 1,234.49" request; only grouping/decimals stay
    # locale-driven. The sign notation then wraps the WHOLE body EXPLICITLY for a
    # negative (FIBR-0105 D2) — NOT delegated to QLocale's negative-currency pattern.
    sym = CURRENCY_SYMBOLS.get(symbol, symbol)
    decimals = max(0, -cast(int, display.as_tuple().exponent))
    magnitude = _grouped(abs(display), decimals)
    body = f"{sym} {magnitude}"
    if display < 0:
        return f"({body})" if negative_style == NegativeStyle.BRACKETS else f"-{body}"
    return body


def parse_amount_input(text: str) -> Decimal:
    """A typed amount -> an exact ``Decimal``, read under the user's locale OR
    the C convention, refusing anything the two read as different numbers.

    The refusal is the point (FIBR-0219): a refusal costs a retype, a wrong guess
    costs a factor of 100 or 1000 on somebody's money. Raises ``ValueError`` on
    every rejection — ``parse_transaction``'s contract, which ``_on_add`` already
    catches and renders, so no new branch is needed at the call site.
    """
    stripped = text.strip()
    try:
        c_value: Decimal | None = Decimal(stripped)
    except InvalidOperation:
        c_value = None
    locale_value = _locale_decimal(stripped)

    # Step 1 — discard non-finite candidates. Both conventions parse "nan"/"inf",
    # and Decimal.__eq__ is FALSE for two NaNs, so a typed "nan" would otherwise
    # reach the disagree branch and report "reads as NaN or as NaN". Dropping
    # both leaves the ordinary "not a valid number" message.
    if c_value is not None and not c_value.is_finite():
        c_value = None
    if locale_value is not None and not locale_value.is_finite():
        locale_value = None

    # Step 2 — both conventions read it: agree, or refuse naming both readings.
    # Equality is numeric, so Decimal("1.10") == Decimal("1.1") agrees — which is
    # what we want, and parse_transaction counts SIGNIFICANT fractional digits
    # anyway, so trailing zeros cannot change the outcome downstream either.
    if c_value is not None and locale_value is not None:
        if c_value == locale_value:
            return c_value
        raise ValueError(_ambiguous(stripped, locale_value, c_value))

    survivor = c_value if c_value is not None else locale_value
    if survivor is None:
        raise ValueError("amount is not a valid number")

    # Step 3 — exactly one candidate survived, so the losing convention did not
    # DISAGREE, it REJECTED: the string's shape is the only evidence left of the
    # reading it never produced. Under en_ZA, "1,500" parses only as Qt's 1.5 —
    # stored as 150 minor units where the user meant 150 000.
    #
    # This runs AFTER the agreement test on purpose. Ahead of it, the same guard
    # refuses "1.500" and "1.250" under en_US, which the shipping app accepts and
    # stores today (FIBR-0219 § 8 alternative 7 — measured, not theorised).
    operand = _guard_operand(stripped)
    if _AMBIGUOUS_SHAPE.match(operand):
        # Only one candidate exists, so the two readings are computed here:
        # GROUPED drops every separator, DECIMAL reads the FINAL one as a point.
        cut = max(operand.rfind("."), operand.rfind(","))
        grouped = Decimal(re.sub(r"[.,]", "", operand))
        point = Decimal(re.sub(r"[.,]", "", operand[:cut]) + "." + operand[cut + 1 :])
        raise ValueError(_ambiguous(stripped, grouped, point))
    return survivor


def _locale_decimal(text: str) -> Decimal | None:
    """The locale convention's reading of ``text``, or ``None`` if it has none.

    Qt VALIDATES group placement — under de_DE "-12.34" is *rejected* rather than
    read as -1234 — which is the property the obvious string-munge fix throws
    away by transforming without validating. So toDouble is the validator and its
    float is discarded: the value is rebuilt from the string, exactly (D1).
    """
    locale = QLocale()
    if not locale.toDouble(text)[1]:  # R1 — VALIDATION ONLY. The float is a float.
        return None
    # R2 then R3, and the order does NOT commute: swapping the decimal point first
    # turns it into a "." that the group-removal step then eats, so under de_DE
    # "1.234,56" becomes 123456 instead of 1234.56 — a silent 100x, and it passes
    # any test that only exercises a locale whose group separator is not "."
    # (FIBR-0219 § 4.3, measured).
    rebuilt = text
    for dead in (locale.groupSeparator(), *_SPACES):  # R2
        rebuilt = rebuilt.replace(dead, "")
    rebuilt = (  # R3 — sign entries are not hypothetical: sv_SE, nb_NO and lt_LT
        rebuilt.replace(locale.decimalPoint(), ".")  # all return U+2212 as their
        .replace(locale.negativeSign(), "-")  # negativeSign(), and ar_EG returns
        .replace(locale.positiveSign(), "+")  # a two-CHARACTER string, so these
    )  # replacements must be string-wise, not char-wise.
    try:
        return Decimal(rebuilt)  # R4
    except InvalidOperation:
        # NOT defensive padding: InvalidOperation is an ArithmeticError, so an
        # escape here sails past _on_add's `except ValueError` and takes the Qt
        # slot down. Reachable by a typed U+2212 minus under any locale whose own
        # sign is ASCII — en_US, de_DE, en_ZA, fr_FR — where R3 is a no-op.
        return None


def _guard_operand(text: str) -> str:
    """The string § 4.5 step 3's shape guard inspects — computed here, and
    deliberately NOT from ``_locale_decimal``'s intermediate, which does not
    exist on the branch where the C candidate is the survivor.

    "." and "," are left in place: they are what the pattern reads, and removing
    them when they *are* the group separator would blind the guard entirely. The
    locale's own separator is removed only when it is neither — de_CH groups with
    an apostrophe (11 Qt locales do), and a hardcoded set would make the guard's
    coverage accidental. The "_" is not cosmetic either: Decimal accepts PEP 515
    underscores, so one of them would otherwise disable the whole guard.
    """
    locale = QLocale()
    group = locale.groupSeparator()
    operand = text.replace(locale.negativeSign(), "-")
    operand = operand.replace(locale.positiveSign(), "+")
    for dead in (*_SPACES, "_", *([group] if group not in ".," else [])):
        operand = operand.replace(dead, "")
    return operand


def _ambiguous(text: str, grouped: Decimal, point: Decimal) -> str:
    """The refusal, with both readings rendered in the USER's own convention.

    Rendering them in the C convention would show a de_DE user "reads as 1234 or
    as 1.234", in which the second is how *their* locale spells the first — the
    message would repeat the ambiguity it exists to resolve. One reading always
    renders back to what was typed, which is why the labels are part of it.
    """
    return (
        f'amount is ambiguous: "{text}" reads as {_render(grouped)} (grouped) or '
        f"as {_render(point)} (decimal) — retype it using the format the app "
        "displays"
    )


def _render(value: Decimal) -> str:
    """One reading, in the user's convention. The digit count is the SIGNIFICANT
    one (normalize()), matching parse_transaction — on the raw exponent, en_ZA's
    decimal reading of "1,500" renders as "1,500", indistinguishable from the
    input. Exact via ``_grouped``: the float route was both lossy past 2**53 and,
    on the bare toString(double), 'g' with six significant digits — which would
    put "1,2345e+06" in a money message."""
    digits = max(0, -cast(int, value.normalize().as_tuple().exponent))
    return _grouped(value, digits)
