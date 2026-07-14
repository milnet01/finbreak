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

from PySide6.QtCharts import QChart, QChartView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import VaultLockedError
from finbreak.models import CategorySpend, DrillLabels, DrillNode, MonthlyTotal, Summary
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
from finbreak.ui.charts import ChartTheme, build_donut_chart, build_trend_chart


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
        # The selectors + tiles + charts + drill-down tree make a tall page, so the
        # content scrolls (D1). The page keeps its object name; findChild searches
        # recursively, so the scroll wrap is transparent to the qtbot lookups.
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

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

        # The expandable Income / Spending / Transfers drill-down (FIBR-0138 D1). The
        # service returns every level pre-sorted (INV-7), so the widget's own column
        # sort is off and it inserts in order; read-only (no ItemIsEditable flag).
        self._drilldown = QTreeWidget()
        self._drilldown.setObjectName("dashboard_drilldown")
        self._drilldown.setColumnCount(2)
        self._drilldown.setHeaderLabels([self.tr("Name"), self.tr("Amount")])
        self._drilldown.setSortingEnabled(False)
        layout.addWidget(self._drilldown)

        scroll.setWidget(content)
        outer.addWidget(scroll)
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

    def current_prefs(self) -> ReportPrefs:
        """The dashboard's live period selection — the export dialog's pre-fill
        (D7). Thin public wrapper over the private selector read."""
        return self._current_prefs()

    def selected_account_id(self) -> int | None:
        """The dashboard's selected account (``None`` = All accounts) — the export
        dialog's account pre-fill (D7)."""
        return self._selected_account_id()

    # --- render ------------------------------------------------------------ #
    def refresh(self) -> None:
        # Getting-started iff the vault holds zero transactions (INV-7).
        if self._reporting.transaction_count() == 0:
            self._stack.setCurrentIndex(0)
            return
        self._rebuild_account_selector()
        prefs = self._current_prefs()
        account_id = self._selected_account_id()
        # FIBR-0013 D4: the reporting layer now takes an account *set* (None ⇒ all);
        # Home's single-or-all selection wraps to None or a one-element frozenset.
        account_ids = None if account_id is None else frozenset({account_id})
        symbol = self._reporting.base_currency()

        self._render_tiles(self._reporting.summary(prefs, account_ids), symbol)
        self._render_donut(self._reporting.spending_by_category(prefs, account_ids))
        self._render_trend(self._reporting.monthly_trend(prefs, account_ids))
        # The drill-down tree (FIBR-0138 D6). HomeView (a QObject) owns the tr()-ed
        # fixed strings, keeping the non-QObject ReportingService translation-free —
        # the same pattern _render_donut uses for tr("Uncategorised") / tr("Other").
        labels = DrillLabels(
            income=self.tr("Income"),
            spending=self.tr("Spending"),
            transfers=self.tr("Transfers"),
            uncategorised=self.tr("Uncategorised"),
        )
        self._render_drilldown(
            self._reporting.drill_down(prefs, account_ids, labels=labels)
        )
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

    def _chart_theme(self) -> ChartTheme:
        """The on-screen theme: text from the live palette (ADR-0010 dark default),
        the fixed FIBR-0105 positive/negative colours, transparent background — so
        the shared builders reproduce the FIBR-0012 dashboard exactly (D3)."""
        return ChartTheme(
            text=self.palette().text().color(),
            positive=_POSITIVE_TEXT,
            negative=_NEGATIVE_TEXT,
            background=None,
        )

    def _render_donut(self, spending: list[CategorySpend]) -> None:
        if not spending:
            # No spending in the period — hide the chart, show the placeholder (D9).
            self._category_chart.setVisible(False)
            self._category_empty.setVisible(True)
            self._category_chart.setChart(QChart())  # release the old series
            return
        self._category_empty.setVisible(False)
        self._category_chart.setVisible(True)
        self._category_chart.setChart(
            build_donut_chart(
                spending,
                self.tr("Uncategorised"),
                self.tr("Other"),
                self._chart_theme(),
            )
        )

    def _render_trend(self, trend: list[MonthlyTotal]) -> None:
        self._trend_chart.setChart(
            build_trend_chart(
                trend,
                self.tr("Income"),
                self.tr("Spending"),
                self._chart_theme(),
            )
        )

    def _render_drilldown(self, nodes: list[DrillNode]) -> None:
        """Rebuild the drill-down tree from the three service nodes (FIBR-0138 D7).
        The branch colour (Income positive, Spending negative, Transfers the default
        text colour when ``amount_prefs.colour`` is on) is threaded down the recursion
        so a deep transaction leaf inherits its branch's colour."""
        self._drilldown.clear()
        self._drill_symbol = self._reporting.base_currency()
        coloured = self._amount_prefs.colour
        branch_colours: list[QColor | None] = [
            _POSITIVE_TEXT if coloured else None,  # Income
            _NEGATIVE_TEXT if coloured else None,  # Spending
            None,  # Transfers — neither income nor spending
        ]
        root = self._drilldown.invisibleRootItem()
        # drill_down always returns exactly [Income, Spending, Transfers] (D4), so the
        # lists match length — strict catches a contract break.
        for node, branch_colour in zip(nodes, branch_colours, strict=True):
            self._add_node(root, node, branch_colour)

    def _add_node(
        self,
        parent_item: QTreeWidgetItem,
        node: DrillNode,
        branch_colour: QColor | None = None,
    ) -> QTreeWidgetItem:
        """Insert ``node`` (and its descendants) under ``parent_item``. A merchant or
        account-pair node — one whose children are all individual-transaction leaves —
        with ``count > 1`` shows the ``×N`` suffix (D7); category / top / txn nodes
        show the bare label."""
        item = QTreeWidgetItem(parent_item)
        is_group = (
            node.count > 1
            and bool(node.children)
            and all(not child.children for child in node.children)
        )
        if is_group:
            item.setText(
                0,
                self.tr("{label} ×{count}").format(label=node.label, count=node.count),
            )
        else:
            item.setText(0, node.label)
        item.setText(
            1,
            _format_amount(
                node.amount, self._drill_symbol, self._amount_prefs.negative_style
            ),
        )
        item.setTextAlignment(
            1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        if branch_colour is not None:
            item.setForeground(1, QBrush(branch_colour))
        for child in node.children:
            self._add_node(item, child, branch_colour)
        return item
