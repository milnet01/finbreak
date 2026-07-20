"""Shared money-string formatting + direction tints (FIBR-0012 D10).

Relocated verbatim out of ``ui/home.py`` so the dashboard tiles (``home.py``) and
the relocated Transactions table (``transactions.py``) share the one
implementation (coding.md § 1.3) — this is a relocation, not a new abstraction.
The trend chart's bar-set colours reuse the same direction tints.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from PySide6.QtCore import QLocale
from PySide6.QtGui import QColor

from finbreak.services.auth import CURRENCY_SYMBOLS

# Direction tints for money display when colour is on (FIBR-0105 D3). Fixed
# mid-tones chosen to read on the dark-default theme (ADR-0010) and stay legible
# on light; palette-adaptive re-tinting is FIBR-0014.
_NEGATIVE_TEXT = QColor(224, 108, 117)  # soft red — money out
_POSITIVE_TEXT = QColor(152, 195, 121)  # soft green — money in


def _format_amount(display: Decimal, symbol: str, negative_style: str = "minus") -> str:
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
    # A stored amount reconstructs to a finite Decimal, so its exponent is an int;
    # toString has no Decimal overload, so the float() is a DISPLAY-ONLY, bounded
    # conversion — storage/computation stay exact Decimal (D1). Decimal places follow
    # the display Decimal's own exponent, not the currency's minor unit.
    #
    # The symbol is ALWAYS a one-space prefix (overriding QLocale's per-locale symbol
    # placement) to honour the user's "R 1,234.49" request; only grouping/decimals stay
    # locale-driven. The sign notation then wraps the WHOLE body EXPLICITLY for a
    # negative (FIBR-0105 D2) — NOT delegated to QLocale's negative-currency pattern.
    sym = CURRENCY_SYMBOLS.get(symbol, symbol)
    decimals = max(0, -cast(int, display.as_tuple().exponent))
    magnitude = QLocale().toString(float(abs(display)), "f", decimals)
    body = f"{sym} {magnitude}"
    if display < 0:
        return f"({body})" if negative_style == "brackets" else f"-{body}"
    return body
