"""HomeView — the Home **dashboard** (FIBR-0012 D6, superseding the FIBR-0051 table).

An internal ``QStackedWidget`` toggling between the **getting-started** page (shown
when the vault holds zero transactions) and the **dashboard** (shown once there is
data). The toggle is observable via ``current_page().objectName()``
(``home_page_empty`` / ``home_page_dashboard``, INV-7).

The dashboard shows, for a chosen period (defaulting to last month, persisted): a
period + account selector, three summary tiles (income / expenditure / net), a
category **donut**, and a 12-month income-vs-expenditure **trend** bar chart —
all with confirmed transfers excluded (the ``ReportingService`` does the
exclusion). Money moved between the user's own accounts never counts. The raw
transaction table moved to the Transactions tab (``ui/transactions.py``).
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import VaultLockedError
from finbreak.models import CategorySpend, MonthlyTotal, Summary
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AmountPrefs, AuthService
from finbreak.services.reporting import (
    MODE_CURRENT_MONTH,
    MODE_PREVIOUS_MONTH,
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    MODE_YEAR_TO_DATE,
    ReportingService,
    ReportPrefs,
)
from finbreak.ui._amount import _NEGATIVE_TEXT, _POSITIVE_TEXT, _format_amount

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


class HomeView(QWidget):
    add_account_requested = Signal()
    import_requested = Signal()
    add_transaction_requested = Signal()

    def __init__(
        self,
        reporting: ReportingService,
        accounts: AccountService,
        auth: AuthService,
        amount_prefs: AmountPrefs | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._reporting = reporting
        self._accounts = accounts
        self._auth = auth
        self._amount_prefs = amount_prefs or AmountPrefs("minus", True)
        # Guards the programmatic selector loads from re-triggering a persist.
        self._loading = False

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_getting_started())
        self._stack.addWidget(self._build_dashboard())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._load_prefs_into_selectors(self._auth.report_prefs())
        self.refresh()

    # --- construction ------------------------------------------------------ #
    def _build_getting_started(self) -> QWidget:
        page = QWidget()
        page.setObjectName("home_page_empty")

        add_account = QPushButton(self.tr("Add an account"))
        import_statement = QPushButton(self.tr("Import a statement"))
        add_transaction = QPushButton(self.tr("Add a transaction"))
        add_account.clicked.connect(self.add_account_requested)
        import_statement.clicked.connect(self.import_requested)
        add_transaction.clicked.connect(self.add_transaction_requested)

        layout = QVBoxLayout(page)
        layout.addStretch()
        layout.addWidget(QLabel(self.tr("Welcome to finbreak. To get started:")))
        layout.addWidget(add_account)
        layout.addWidget(import_statement)
        layout.addWidget(add_transaction)
        layout.addStretch()
        return page

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        page.setObjectName("home_page_dashboard")
        layout = QVBoxLayout(page)

        layout.addLayout(self._build_selectors())
        layout.addLayout(self._build_tiles())

        # Category donut + its empty-state placeholder (only one is visible).
        self._category_chart = QChartView()
        self._category_chart.setObjectName("dashboard_category_chart")
        self._category_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._category_empty = QLabel(self.tr("No spending in this period"))
        self._category_empty.setObjectName("dashboard_category_empty")
        self._category_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._category_chart)
        layout.addWidget(self._category_empty)

        self._trend_chart = QChartView()
        self._trend_chart.setObjectName("dashboard_trend_chart")
        self._trend_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self._trend_chart)
        return page

    def _build_selectors(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._period_selector = QComboBox()
        self._period_selector.setObjectName("period_selector")
        for label, mode in (
            (self.tr("Previous month"), MODE_PREVIOUS_MONTH),
            (self.tr("Current month"), MODE_CURRENT_MONTH),
            (self.tr("Specific month"), MODE_SPECIFIC_MONTH),
            (self.tr("Year to date"), MODE_YEAR_TO_DATE),
            (self.tr("Specific year"), MODE_SPECIFIC_YEAR),
        ):
            self._period_selector.addItem(label, mode)
        self._period_selector.currentIndexChanged.connect(self._on_period_changed)

        self._month_picker = QComboBox()
        self._month_picker.setObjectName("period_month")
        for month in range(1, 13):
            self._month_picker.addItem(f"{month:02d}", month)
        self._month_picker.currentIndexChanged.connect(self._on_period_changed)

        self._year_picker = QSpinBox()
        self._year_picker.setObjectName("period_year")
        self._year_picker.setRange(1970, 9999)
        self._year_picker.valueChanged.connect(self._on_period_changed)

        self._account_selector = QComboBox()
        self._account_selector.setObjectName("account_selector")
        self._account_selector.currentIndexChanged.connect(self._on_account_changed)

        row.addWidget(self._period_selector)
        row.addWidget(self._month_picker)
        row.addWidget(self._year_picker)
        row.addStretch()
        row.addWidget(self._account_selector)
        return row

    def _build_tiles(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._income_value = self._make_tile(row, self.tr("Income"), "dashboard_income")
        self._expenditure_value = self._make_tile(
            row, self.tr("Spending"), "dashboard_expenditure"
        )
        self._net_value = self._make_tile(row, self.tr("Net"), "dashboard_net")
        return row

    def _make_tile(self, row: QHBoxLayout, title: str, object_name: str) -> QLabel:
        tile = QWidget()
        tile_layout = QVBoxLayout(tile)
        tile_layout.addWidget(QLabel(title))
        value = QLabel("")
        value.setObjectName(object_name)
        tile_layout.addWidget(value)
        row.addWidget(tile)
        return value

    # --- selector state ---------------------------------------------------- #
    def _load_prefs_into_selectors(self, prefs: ReportPrefs) -> None:
        """Set the period + secondary pickers from a stored ``ReportPrefs`` without
        re-triggering a persist. Specific pickers default to the stored value, else
        the current calendar month / year."""
        from datetime import date

        self._loading = True
        try:
            index = self._period_selector.findData(prefs.mode)
            self._period_selector.setCurrentIndex(max(0, index))
            today = date.today()
            self._year_picker.setValue(prefs.year or today.year)
            month_index = self._month_picker.findData(prefs.month or today.month)
            self._month_picker.setCurrentIndex(max(0, month_index))
            self._sync_picker_visibility()
        finally:
            self._loading = False

    def _sync_picker_visibility(self) -> None:
        mode = self._period_selector.currentData()
        self._month_picker.setVisible(mode == MODE_SPECIFIC_MONTH)
        self._year_picker.setVisible(mode in (MODE_SPECIFIC_MONTH, MODE_SPECIFIC_YEAR))

    def _current_prefs(self) -> ReportPrefs:
        mode = self._period_selector.currentData()
        if mode == MODE_SPECIFIC_MONTH:
            return ReportPrefs(
                mode,
                year=self._year_picker.value(),
                month=self._month_picker.currentData(),
            )
        if mode == MODE_SPECIFIC_YEAR:
            return ReportPrefs(mode, year=self._year_picker.value())
        return ReportPrefs(mode)

    def _selected_account_id(self) -> int | None:
        return self._account_selector.currentData()

    # --- signals ----------------------------------------------------------- #
    def _on_period_changed(self) -> None:
        if self._loading:
            return
        self._sync_picker_visibility()
        # Persist the new period (the account is NOT persisted, D6), then re-render.
        # An auto-lock mid-interaction surfaces as VaultLockedError from the write or
        # a subsequent vault read — caught (specifically, not a bare except) so the UI
        # never crashes, matching the other tabs' slot guards (coding.md § 2).
        try:
            self._auth.set_report_prefs(self._current_prefs())
            self.refresh()
        except VaultLockedError:
            return

    def _on_account_changed(self) -> None:
        if self._loading:
            return
        try:
            self.refresh()  # account is session-only, not persisted (D6)
        except VaultLockedError:
            return

    # --- shell / test accessors -------------------------------------------- #
    def current_page(self) -> QWidget:
        return self._stack.currentWidget()

    def transaction_count(self) -> int:
        """Live whole-vault count — the shell's status-bar source (D6/D11)."""
        return self._reporting.transaction_count()

    def set_amount_prefs(self, prefs: AmountPrefs) -> None:
        """Adopt new amount-display prefs and re-render (the tiles reformat)."""
        self._amount_prefs = prefs
        self.refresh()

    # --- render ------------------------------------------------------------ #
    def refresh(self) -> None:
        # Getting-started iff the vault holds zero transactions (INV-7).
        if self._reporting.transaction_count() == 0:
            self._stack.setCurrentIndex(0)
            return
        self._rebuild_account_selector()
        prefs = self._current_prefs()
        account_id = self._selected_account_id()
        symbol = self._reporting.base_currency()

        self._render_tiles(self._reporting.summary(prefs, account_id), symbol)
        self._render_donut(self._reporting.spending_by_category(prefs, account_id))
        self._render_trend(self._reporting.monthly_trend(prefs, account_id))
        self._stack.setCurrentIndex(1)

    def _rebuild_account_selector(self) -> None:
        """Rebuild the account combo preserving the current in-session selection —
        re-select the held account id if it still exists, else "All accounts"."""
        held = self._selected_account_id()
        self._loading = True
        try:
            self._account_selector.clear()
            self._account_selector.addItem(self.tr("All accounts"), None)
            for account in self._accounts.list_accounts():
                self._account_selector.addItem(account.name, account.id)
            index = self._account_selector.findData(held)
            self._account_selector.setCurrentIndex(max(0, index))
        finally:
            self._loading = False

    def _render_tiles(self, summary: Summary, symbol: str) -> None:
        style = self._amount_prefs.negative_style
        self._income_value.setText(_format_amount(summary.income, symbol, style))
        self._expenditure_value.setText(
            _format_amount(summary.expenditure, symbol, style)
        )
        self._net_value.setText(_format_amount(summary.net, symbol, style))
        if self._amount_prefs.colour:
            self._income_value.setStyleSheet(f"color: {_POSITIVE_TEXT.name()}")
            self._expenditure_value.setStyleSheet(f"color: {_NEGATIVE_TEXT.name()}")
            net_colour = _POSITIVE_TEXT if summary.net >= 0 else _NEGATIVE_TEXT
            self._net_value.setStyleSheet(f"color: {net_colour.name()}")
        else:
            for value in (self._income_value, self._expenditure_value, self._net_value):
                value.setStyleSheet("")

    def _render_donut(self, spending: list[CategorySpend]) -> None:
        wedges = _donut_wedges(spending, self.tr("Uncategorised"), self.tr("Other"))
        if not wedges:
            # No spending in the period — hide the chart, show the placeholder (D9).
            self._category_chart.setVisible(False)
            self._category_empty.setVisible(True)
            self._category_chart.setChart(QChart())  # release the old series
            return
        self._category_empty.setVisible(False)
        self._category_chart.setVisible(True)
        series = QPieSeries()
        series.setHoleSize(0.4)  # a non-zero hole makes it a donut
        for label, amount, colour in wedges:
            slice_ = series.append(label, float(amount))
            slice_.setColor(colour)
        self._category_chart.setChart(self._themed_chart(series))

    def _render_trend(self, trend: list[MonthlyTotal]) -> None:
        income_set = QBarSet(self.tr("Income"))
        income_set.setColor(_POSITIVE_TEXT)
        expenditure_set = QBarSet(self.tr("Spending"))
        expenditure_set.setColor(_NEGATIVE_TEXT)
        for month in trend:
            income_set.append(float(month.income))
            expenditure_set.append(float(month.expenditure))
        series = QBarSeries()
        series.append(income_set)
        series.append(expenditure_set)
        chart = self._themed_chart(series)
        axis_x = QBarCategoryAxis()
        axis_x.append([month.label for month in trend])
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        axis_y = QValueAxis()
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        self._trend_chart.setChart(chart)

    def _themed_chart(self, series: QPieSeries | QBarSeries) -> QChart:
        """A chart with a transparent background (the app panel shows through) and
        palette-driven text (ADR-0002 dark default, D9)."""
        chart = QChart()
        chart.addSeries(series)
        chart.setBackgroundVisible(False)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        text_colour = self.palette().text().color()
        chart.legend().setLabelColor(text_colour)
        chart.setTitleBrush(text_colour)
        return chart
