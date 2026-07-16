"""HomeView — the Home **dashboard** (FIBR-0012 D6, superseding the FIBR-0051 table).

An internal ``QStackedWidget`` toggling between the **getting-started** page (shown
when the vault holds zero transactions) and the **dashboard** (shown once there is
data). The toggle is observable via ``current_page().objectName()``
(``home_page_empty`` / ``home_page_dashboard``, INV-7).

The dashboard leads with the breakdown (FIBR-0143): for a chosen period (defaulting
to last month, persisted) — a period + account selector, a slim **Net** strip, then
three side-by-side columns (Expenditure / Income / Transfers), each a **pie** + a
coloured header (name + total) + an expandable **breakdown tree**; below them a
full-width **recurring-money** card and the demoted 12-month **trend** bar strip.
Confirmed transfers are excluded from Income / Spending (the ``ReportingService`` does
the exclusion); money moved between the user's own accounts never counts. The recurring
card is **unscoped** — it sums all confirmed recurring money vault-wide, regardless of
the selectors. The raw transaction table moved to the Transactions tab.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtCharts import QChart, QChartView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
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
from finbreak.models import (
    DrillLabels,
    DrillNode,
    MonthlyTotal,
    RecurringSummary,
    Summary,
)
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AmountPrefs, AuthService
from finbreak.services.recurring import RecurringService
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
from finbreak.ui.charts import ChartTheme, build_breakdown_donut, build_trend_chart


@dataclass
class _Column:
    """The five pinned widgets of one dashboard column (FIBR-0143 D1) — a pie with
    its empty-state placeholder, a two-line header (name + total), and a breakdown
    tree. Held so ``refresh()`` can re-render each column in place."""

    pie: QChartView
    empty: QLabel
    name: QLabel
    total: QLabel
    tree: QTreeWidget


class HomeView(QWidget):
    add_account_requested = Signal()
    import_requested = Signal()
    add_transaction_requested = Signal()

    def __init__(
        self,
        reporting: ReportingService,
        accounts: AccountService,
        auth: AuthService,
        recurring: RecurringService,
        amount_prefs: AmountPrefs | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._reporting = reporting
        self._accounts = accounts
        self._auth = auth
        self._recurring = recurring
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
        # Selectors → Net strip → three columns → recurring card → trend strip make a
        # tall page, so the content scrolls (D1). The page keeps its object name;
        # findChild searches recursively, so the scroll wrap is transparent to lookups.
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

        layout.addLayout(self._build_selectors())

        # The slim Net strip above the columns (D4) — re-homes the old Net tile.
        self._net_value = QLabel("")
        self._net_value.setObjectName("dashboard_net")
        layout.addWidget(self._net_value)

        # The three breakdown columns (D1), rendered left-to-right in the mockup's
        # order Expenditure / Income / Transfers; each an equal-stretch card.
        columns = QHBoxLayout()
        self._columns: dict[str, _Column] = {}
        for key in ("expenditure", "income", "transfers"):
            columns.addWidget(self._build_column(key), 1)
        layout.addLayout(columns)

        # The full-width recurring-money card (D5) and the demoted trend strip (D6).
        layout.addWidget(self._build_recurring_card())
        self._trend_chart = QChartView()
        self._trend_chart.setObjectName("dashboard_trend_chart")
        self._trend_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self._trend_chart)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        return page

    def _build_column(self, key: str) -> QWidget:
        """One breakdown column: a pie + its empty placeholder (only one visible), a
        two-line header (name + total), and a read-only breakdown tree (D1/D7). The
        service pre-sorts every level (INV-7), so the tree's own sort is off."""
        col = QWidget()
        col.setObjectName(f"dashboard_col_{key}")
        v = QVBoxLayout(col)

        pie = QChartView()
        pie.setObjectName(f"dashboard_pie_{key}")
        pie.setRenderHint(QPainter.RenderHint.Antialiasing)
        empty = QLabel(self.tr("No data for this period"))
        empty.setObjectName(f"dashboard_pie_empty_{key}")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(pie)
        v.addWidget(empty)

        name = QLabel("")
        name.setObjectName(f"dashboard_heading_{key}")
        total = QLabel("")
        total.setObjectName(f"dashboard_total_{key}")
        v.addWidget(name)
        v.addWidget(total)

        tree = QTreeWidget()
        tree.setObjectName(f"dashboard_breakdown_{key}")
        tree.setColumnCount(2)
        tree.setHeaderLabels([self.tr("Name"), self.tr("Amount")])
        tree.setSortingEnabled(False)
        v.addWidget(tree)

        self._columns[key] = _Column(pie, empty, name, total, tree)
        return col

    def _build_recurring_card(self) -> QWidget:
        """The recurring-money card shell (D5); its body is rebuilt each refresh into
        either a figures row (In / Out / Net) or a single hint line."""
        card = QWidget()
        card.setObjectName("dashboard_recurring")
        v = QVBoxLayout(card)
        v.addWidget(QLabel(self.tr("Recurring")))
        self._recurring_grid = QGridLayout()
        v.addLayout(self._recurring_grid)
        return card

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
        """Adopt new amount-display prefs and re-render (the column totals, Net strip,
        and recurring figures reformat/recolour)."""
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
        self._drill_symbol = symbol

        # The Net strip (D4) is the one summary()-sourced figure; the column headers
        # come from the drill nodes, which equal Summary by FIBR-0138 INV-1.
        self._render_net(self._reporting.summary(prefs, account_ids), symbol)

        # One drill_down() feeds all three columns (D2). HomeView (a QObject) owns the
        # tr()-ed fixed strings, keeping the non-QObject ReportingService translation-
        # free — the same pattern the pie's tr("Uncategorised") / tr("Other") uses.
        labels = DrillLabels(
            income=self.tr("Income"),
            spending=self.tr("Spending"),
            transfers=self.tr("Transfers"),
            uncategorised=self.tr("Uncategorised"),
        )
        income, spending, transfers = self._reporting.drill_down(
            prefs, account_ids, labels=labels
        )
        # Node → column map (load-bearing: drill_down order ≠ display order, D2). The
        # branch colour is gated on amount_prefs.colour; Transfers has no sign colour.
        coloured = self._amount_prefs.colour
        self._render_column(
            "expenditure", spending, _NEGATIVE_TEXT if coloured else None, symbol
        )
        self._render_column(
            "income", income, _POSITIVE_TEXT if coloured else None, symbol
        )
        self._render_column("transfers", transfers, None, symbol)

        self._render_trend(self._reporting.monthly_trend(prefs, account_ids))
        # The recurring card is unscoped (INV-3/D5): summary(today) takes no prefs.
        self._render_recurring(self._recurring.summary(date.today()), symbol)
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

    def _render_net(self, summary: Summary, symbol: str) -> None:
        """The slim Net strip (D4/INV-6): Summary.net, sign-coloured when the pref is
        on — the identical logic the old Net tile used, moved not rewritten."""
        style = self._amount_prefs.negative_style
        self._net_value.setText(
            f"{self.tr('Net')} {_format_amount(summary.net, symbol, style)}"
        )
        if self._amount_prefs.colour:
            colour = _POSITIVE_TEXT if summary.net >= 0 else _NEGATIVE_TEXT
            self._net_value.setStyleSheet(f"color: {colour.name()}")
        else:
            self._net_value.setStyleSheet("")

    def _render_column(
        self, key: str, node: DrillNode, branch_colour: QColor | None, symbol: str
    ) -> None:
        """Render one column from its branch node (D2/D7): the header (name + total)
        both take the branch colour when the pref is on; the pie mirrors the node's
        direct children (palette-coloured, never the branch sign colour); the tree
        shows the branch's children (not the branch header row, which the header is)."""
        col = self._columns[key]
        style = self._amount_prefs.negative_style
        col.name.setText(node.label)
        col.total.setText(_format_amount(node.amount, symbol, style))
        header_style = f"color: {branch_colour.name()}" if branch_colour else ""
        col.name.setStyleSheet(header_style)
        col.total.setStyleSheet(header_style)

        slices = [(child.label, child.amount) for child in node.children]
        if slices:
            col.empty.setVisible(False)
            col.pie.setVisible(True)
            col.pie.setChart(
                build_breakdown_donut(slices, self.tr("Other"), self._chart_theme())
            )
        else:
            # No children — hide the pie (kept present), show the placeholder (D8).
            col.pie.setVisible(False)
            col.empty.setVisible(True)
            col.pie.setChart(QChart())  # release the old series

        col.tree.clear()
        root = col.tree.invisibleRootItem()
        for child in node.children:
            self._add_node(root, child, branch_colour)

    def _render_recurring(self, summary: RecurringSummary, symbol: str) -> None:
        """The recurring card body (D5/INV-5): a three-figure In / Out / Net row over
        the confirmed monthly totals, or a single hint line when nothing is confirmed.
        In/Out colours are forced by role (Out is an outflow though its value is
        positive); Net follows its sign. Rebuilt each refresh."""
        while self._recurring_grid.count():
            item = self._recurring_grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(
                    None
                )  # detach now so findChild can't see the stale one
        style = self._amount_prefs.negative_style
        coloured = self._amount_prefs.colour
        # Gate on the two DIRECTIONAL totals, not net: equal confirmed in and out
        # cancel to a zero net while still being real recurring money to show (INV-5).
        if summary.monthly_in == 0 and summary.monthly_out == 0:
            self._recurring_grid.addWidget(
                QLabel(
                    self.tr(
                        "Confirm recurring items on the Recurring tab to see them here."
                    )
                ),
                0,
                0,
                1,
                3,
            )
            return
        self._recurring_grid.addWidget(QLabel(self.tr("Per month")), 0, 0, 1, 3)
        net_colour = _POSITIVE_TEXT if summary.net >= 0 else _NEGATIVE_TEXT
        figures = (
            (
                self.tr("In"),
                summary.monthly_in,
                _POSITIVE_TEXT,
                "dashboard_recurring_in",
            ),
            (
                self.tr("Out"),
                summary.monthly_out,
                _NEGATIVE_TEXT,
                "dashboard_recurring_out",
            ),
            (self.tr("Net"), summary.net, net_colour, "dashboard_recurring_net"),
        )
        for column, (caption, value, colour, object_name) in enumerate(figures):
            self._recurring_grid.addWidget(QLabel(caption), 1, column)
            figure = QLabel(_format_amount(value, symbol, style))
            figure.setObjectName(object_name)
            if coloured:
                figure.setStyleSheet(f"color: {colour.name()}")
            self._recurring_grid.addWidget(figure, 2, column)

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

    def _render_trend(self, trend: list[MonthlyTotal]) -> None:
        self._trend_chart.setChart(
            build_trend_chart(
                trend,
                self.tr("Income"),
                self.tr("Spending"),
                self._chart_theme(),
            )
        )

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
