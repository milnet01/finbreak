"""FIBR-0013 D3 — the shared, palette-free chart builders (`ui/charts.py`).

`build_donut_chart` / `build_trend_chart` are the single source of chart shape,
reused by both `HomeView` (live palette) and the PDF export (explicit Light/Dark
`ChartTheme`). The builders take a `ChartTheme` of explicit colours, so an
offscreen render never depends on a live widget palette (INV-8/INV-9). Tests
assert the produced `QChart` carries exactly the expected series, values, and
themed colours — the contract both call-sites rely on.
"""

from decimal import Decimal

import pytest
from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QChart, QPieSeries
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from finbreak.models import CategorySpend, MonthlyTotal
from finbreak.ui.charts import (
    ChartTheme,
    build_donut_chart,
    build_trend_chart,
)

pytestmark = pytest.mark.features

_THEME = ChartTheme(
    text=QColor("#ffffff"),
    positive=QColor("#4E9F3D"),
    negative=QColor("#C0504D"),
    background=None,
)


def _spend(cat_id, amount):
    return CategorySpend(category_id=cat_id, name=f"c{cat_id}", amount=Decimal(amount))


def test_build_donut_chart_slices_match_wedges(qapp):
    """One slice per donut wedge, in order, with the wedge's label, float value,
    and fixed palette colour; a non-zero hole makes it a donut."""
    from finbreak.ui.charts import _donut_wedges

    spending = [_spend(i, 100 - i) for i in range(1, 4)]  # 3 categorised, desc
    wedges = _donut_wedges(spending, "Uncategorised", "Other")

    chart = build_donut_chart(spending, "Uncategorised", "Other", _THEME)

    assert isinstance(chart, QChart)
    (series,) = chart.series()
    assert isinstance(series, QPieSeries)
    assert series.holeSize() == pytest.approx(0.4)
    slices = series.slices()
    assert [s.label() for s in slices] == [w[0] for w in wedges]
    assert [s.value() for s in slices] == [float(w[1]) for w in wedges]
    assert [s.color() for s in slices] == [w[2] for w in wedges]


def test_build_donut_chart_applies_theme_text_colour(qapp):
    """Legend + title text come from the theme, not a live palette (INV-9)."""
    chart = build_donut_chart([_spend(1, 50)], "Uncategorised", "Other", _THEME)
    assert chart.legend().labelColor() == _THEME.text
    assert chart.titleBrush().color() == _THEME.text


def test_build_donut_chart_transparent_background_when_none(qapp):
    """`background=None` ⇒ transparent (the on-screen behaviour HomeView keeps)."""
    chart = build_donut_chart([_spend(1, 50)], "Uncategorised", "Other", _THEME)
    assert chart.isBackgroundVisible() is False


def test_build_trend_chart_two_barsets_coloured_by_theme(qapp):
    """Income + Spending bar sets, labelled and coloured from the theme, with the
    per-month values and a category axis of month labels."""
    trend = [
        MonthlyTotal(label="2026-01", income=Decimal(10), expenditure=Decimal(4)),
        MonthlyTotal(label="2026-02", income=Decimal(7), expenditure=Decimal(9)),
    ]

    chart = build_trend_chart(trend, "Income", "Spending", _THEME)

    (series,) = chart.series()
    assert isinstance(series, QBarSeries)
    income_set, expenditure_set = series.barSets()
    assert income_set.label() == "Income"
    assert expenditure_set.label() == "Spending"
    assert income_set.color() == _THEME.positive
    assert expenditure_set.color() == _THEME.negative
    assert [income_set.at(i) for i in range(income_set.count())] == [10.0, 7.0]
    assert [expenditure_set.at(i) for i in range(expenditure_set.count())] == [4.0, 9.0]
    (axis_x,) = chart.axes(Qt.Orientation.Horizontal)
    assert isinstance(axis_x, QBarCategoryAxis)
    assert list(axis_x.categories()) == ["2026-01", "2026-02"]
