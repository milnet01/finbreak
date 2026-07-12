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

# Direction tints for money display when colour is on (FIBR-0105 D3). Fixed
# mid-tones chosen to read on the dark-default theme (ADR-0002) and stay legible
# on light; palette-adaptive re-tinting is FIBR-0014.
_NEGATIVE_TEXT = QColor(224, 108, 117)  # soft red — money out
_POSITIVE_TEXT = QColor(152, 195, 121)  # soft green — money in


def _format_amount(display: Decimal, symbol: str, negative_style: str = "minus") -> str:
    # Currency → QLocale.toCurrencyString with the base-currency symbol, so the
    # amount carries its currency and isn't reformatted to the locale's own
    # (coding.md § 5.2). A stored amount reconstructs to a finite Decimal, so its
    # exponent is an int. toCurrencyString has no Decimal overload, so the float()
    # is a DISPLAY-ONLY, bounded conversion — storage/computation stay exact
    # Decimal (D1); only the on-screen string crosses to float.
    #
    # Both styles format the MAGNITUDE via QLocale (grouping / decimal separator /
    # symbol placement stay locale-correct), then the sign notation is applied
    # EXPLICITLY for a negative (FIBR-0105 D2) — NOT delegated to QLocale's
    # negative-currency pattern, which is parentheses only on some locales and a
    # minus sign on the C locale + others, making "brackets" non-deterministic.
    decimals = max(0, -cast(int, display.as_tuple().exponent))
    magnitude = QLocale().toCurrencyString(float(abs(display)), symbol, decimals)
    if display < 0:
        return f"({magnitude})" if negative_style == "brackets" else f"-{magnitude}"
    return magnitude
