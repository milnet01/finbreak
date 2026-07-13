"""Shared, palette-free chart builders (FIBR-0013 D3).

The donut + trend charts on the Home dashboard and in the PDF export are built
here, from a single set of functions — so there is one chart shape, not two
(coding.md § 1.3 reuse; INV-8). Each builder takes an explicit ``ChartTheme``
rather than reading a live widget palette, so an **offscreen** render (the PDF
raster) produces the same chart as the on-screen one without depending on any
widget being shown (INV-9).

* ``HomeView`` passes a ``ChartTheme`` built from its live ``palette().text()``
  colour plus the fixed FIBR-0105 positive/negative colours — so on-screen
  behaviour is unchanged from FIBR-0012.
* The export passes an explicit Light or Dark ``ChartTheme`` (D7).

The donut wedge palette is **fixed** regardless of theme (FIBR-0012 D9 — chosen
to read on both light and dark), so it lives here as module constants consumed by
``_donut_wedges``; only the text / positive / negative / background colours vary
by theme and travel on ``ChartTheme``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from finbreak.models import CategorySpend, MonthlyTotal

# The ordered categorical palette for the coloured (categorised) donut wedges
# (FIBR-0012 D9) — accessible on the dark default, the app-icon family extended.
_DONUT_PALETTE = [
    QColor("#4E9F3D"),  # green
    QColor("#3D7EA6"),  # blue
    QColor("#2FA4A0"),  # teal
    QColor("#D98A29"),  # orange
    QColor("#8E6FBE"),  # purple
    QColor("#C0504D"),  # red
    QColor("#C9A227"),  # gold
    QColor("#7FB069"),  # light green
]
# The two synthetic buckets are pinned neutrals, regardless of rank (D9).
_UNCAT_COLOUR = QColor("#9AA6B2")  # light slate — Uncategorised
_OTHER_COLOUR = QColor("#5B6570")  # darker slate — Other
_MAX_WEDGES = 8  # counting Uncategorised and any Other


@dataclass(frozen=True)
class ChartTheme:
    """The explicit colours a chart builder needs (INV-9). ``background=None``
    means a transparent chart (the app panel shows through — HomeView's on-screen
    default); a concrete colour paints a solid background (the PDF render)."""

    text: QColor
    positive: QColor
    negative: QColor
    background: QColor | None = None


def _donut_wedges(
    spending: list[CategorySpend], uncat_label: str, other_label: str
) -> list[tuple[str, Decimal, QColor]]:
    """The ≤8-wedge donut render list (FIBR-0012 D9), from the full sorted
    ``spending_by_category`` output. Splits off the Uncategorised slice
    (``category_id is None``), caps the categorised remainder, and synthesises an
    **Other** wedge locally from the collapsed tail — so Other is a UI construct,
    distinct from Uncategorised by construction. Order: coloured categorised (desc)
    → Uncategorised (if present) → Other (if present)."""
    categorised = [c for c in spending if c.category_id is not None]
    uncat = [c for c in spending if c.category_id is None]  # 0 or 1
    has_uncat = bool(uncat)
    if len(categorised) + (1 if has_uncat else 0) <= _MAX_WEDGES:
        keep, tail = categorised, []
    else:
        # Reserve one wedge for Other, and one for Uncategorised if present.
        n_keep = _MAX_WEDGES - 1 - (1 if has_uncat else 0)
        keep, tail = categorised[:n_keep], categorised[n_keep:]
    wedges: list[tuple[str, Decimal, QColor]] = [
        (c.name, c.amount, _DONUT_PALETTE[i]) for i, c in enumerate(keep)
    ]
    if has_uncat:
        wedges.append((uncat_label, uncat[0].amount, _UNCAT_COLOUR))
    if tail:
        other_amount = sum((c.amount for c in tail), Decimal(0))
        wedges.append((other_label, other_amount, _OTHER_COLOUR))
    return wedges


def _themed_chart(series: QPieSeries | QBarSeries, theme: ChartTheme) -> QChart:
    """A chart carrying ``series`` with the theme's background + text applied.
    ``background=None`` ⇒ transparent (setBackgroundVisible(False)), matching the
    on-screen dashboard; a colour ⇒ a solid background for the PDF raster."""
    chart = QChart()
    chart.addSeries(series)
    if theme.background is None:
        chart.setBackgroundVisible(False)
    else:
        chart.setBackgroundVisible(True)
        chart.setBackgroundBrush(theme.background)
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
    chart.legend().setLabelColor(theme.text)
    chart.setTitleBrush(theme.text)
    return chart


def build_donut_chart(
    spending: list[CategorySpend],
    uncat_label: str,
    other_label: str,
    theme: ChartTheme,
) -> QChart:
    """The category **donut** for ``spending`` (already sorted by the service):
    one slice per ``_donut_wedges`` entry, coloured from the fixed palette, with a
    non-zero hole. Themed legend/title text (INV-8/INV-9)."""
    series = QPieSeries()
    series.setHoleSize(0.4)  # a non-zero hole makes it a donut
    for label, amount, colour in _donut_wedges(spending, uncat_label, other_label):
        slice_ = series.append(label, float(amount))
        slice_.setColor(colour)
    return _themed_chart(series, theme)


def build_trend_chart(
    trend: list[MonthlyTotal],
    income_label: str,
    spending_label: str,
    theme: ChartTheme,
) -> QChart:
    """The 12-month income-vs-spending **trend** bar chart: two themed bar sets
    over a category axis of ``trend`` month labels (INV-8/INV-9)."""
    income_set = QBarSet(income_label)
    income_set.setColor(theme.positive)
    expenditure_set = QBarSet(spending_label)
    expenditure_set.setColor(theme.negative)
    for month in trend:
        income_set.append(float(month.income))
        expenditure_set.append(float(month.expenditure))
    series = QBarSeries()
    series.append(income_set)
    series.append(expenditure_set)
    chart = _themed_chart(series, theme)
    axis_x = QBarCategoryAxis()
    axis_x.append([month.label for month in trend])
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(axis_x)
    axis_y = QValueAxis()
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(axis_y)
    return chart
