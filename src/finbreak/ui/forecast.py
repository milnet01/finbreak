"""Forecast tab — the cash-flow projection surface (FIBR-0171 D9/D10/D11).

A ``ForecastWidget`` mirroring the Recurring tab: it takes the ``AuthService`` and
builds a ``ForecastService`` over the same vault internally. It shows a headline
figure (projected balance, or an honest net change when no balance is known), an
anchor-provenance line naming each contributing statement (D10), a horizon picker
(End of this month / 30 / 60 / 90 days), a themed projected-balance line chart, and
an upcoming-events table (date · merchant · signed amount · running balance).
Detection is clock-driven off ``date.today()`` at refresh; the ``ForecastService``
stays clock-injected (the widget supplies the clock). Every slot catches
``VaultLockedError`` and returns, like the sibling tabs. All strings go through
``tr()`` and every widget sits in a layout manager (coding.md § 5.2).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from PySide6.QtCharts import QChartView
from PySide6.QtCore import Slot
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import VaultLockedError
from finbreak.models import Forecast, ForecastMode
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.forecast import CASH_TYPES, ForecastService
from finbreak.services.transactions import (
    TransactionService,
    read_minor_unit_exponent,
    to_display_decimal,
)
from finbreak.ui._amount import _NEGATIVE_TEXT, _POSITIVE_TEXT, _format_amount
from finbreak.ui._table_state import remember_columns
from finbreak.ui.charts import ChartTheme, build_forecast_chart

# Column order is fixed so the qtbot cells are deterministically assertable (D9).
_COL_DATE = 0
_COL_MERCHANT = 1
_COL_AMOUNT = 2
_COL_BALANCE = 3


class ForecastWidget(QWidget):
    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tab_forecast")
        self._service = service
        self._forecast_service = ForecastService(service.vault)

        self.setWindowTitle(self.tr("Forecast"))

        self._headline = QLabel()
        self._headline.setObjectName("forecast_headline")
        self._provenance = QLabel()
        self._provenance.setObjectName("forecast_provenance")
        self._provenance.setWordWrap(True)

        self._horizon = QComboBox()
        self._horizon.setObjectName("forecast_horizon")
        # userData: "eom" = end of this month; an int = today + N days (D8).
        self._horizon.addItem(self.tr("End of this month"), "eom")
        self._horizon.addItem(self.tr("30 days"), 30)
        self._horizon.addItem(self.tr("60 days"), 60)
        self._horizon.addItem(self.tr("90 days"), 90)
        self._horizon.currentIndexChanged.connect(self._on_horizon_changed)

        self._chart_view = QChartView()
        self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._chart_view.setMinimumHeight(220)

        self._events_table = self._make_table()
        self._status = QLabel()

        horizon_row = QHBoxLayout()
        horizon_row.addWidget(QLabel(self.tr("Project to:")))
        horizon_row.addWidget(self._horizon)
        horizon_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._headline)
        layout.addWidget(self._provenance)
        layout.addLayout(horizon_row)
        layout.addWidget(self._chart_view)
        layout.addWidget(QLabel(self.tr("Upcoming recurring items")))
        layout.addWidget(self._events_table)
        layout.addWidget(self._status)

        self.refresh()

    def _make_table(self) -> QTableWidget:
        table = QTableWidget(0, 4)
        table.setObjectName("forecast_events")
        table.setHorizontalHeaderLabels(
            [
                self.tr("Date"),
                self.tr("Merchant"),
                self.tr("Amount"),
                self.tr("Balance after"),
            ]
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Widths + drag-reorder, persisted (FIBR-0192). Deliberately NO
        # enable_sorting: `_fill_events` writes each row's running balance beside
        # its own date and has no fill_guard, so a click-sort would pair a balance
        # with another event's date. The rows are already date-ascending — the
        # order `project_forecast` produces (§3 decision 1).
        remember_columns(table)
        return table

    # -- horizon --------------------------------------------------------------
    def _horizon_date(self, today: date) -> date:
        """The concrete horizon date from the picked preset (D8); ``today <=``
        horizon always. End-of-month on the last day of a month yields
        ``horizon == today`` — an honest zero-width forecast, not an error."""
        key = self._horizon.currentData()
        if key == "eom":
            last_day = calendar.monthrange(today.year, today.month)[1]
            return date(today.year, today.month, last_day)
        return today + timedelta(days=int(key))

    @Slot()
    def _on_horizon_changed(self) -> None:
        self.refresh()

    # -- refresh --------------------------------------------------------------
    def refresh(self) -> None:
        """Re-read the vault + re-project on view / horizon change (D9). Catches a
        mid-teardown ``VaultLockedError`` like the sibling tabs."""
        try:
            today = date.today()
            fc = self._forecast_service.forecast(today, self._horizon_date(today))
            exponent = read_minor_unit_exponent(self._service.vault.connection)
            symbol = TransactionService(self._service.vault).base_currency()
        except VaultLockedError:
            return  # auto-lock fired; the workspace is being torn down

        self._headline.setText(self._headline_text(fc, exponent, symbol))
        self._provenance.setText(self._provenance_text(fc, exponent, symbol))
        self._chart_view.setChart(build_forecast_chart(fc.points, self._chart_theme()))
        self._fill_events(fc, exponent, symbol)
        if not fc.events:
            self._status.setText(
                self.tr(
                    "No confirmed recurring items yet — "
                    "confirm some on the Recurring tab."
                )
            )
        else:
            self._status.setText("")

    # -- text builders --------------------------------------------------------
    def _headline_text(self, fc: Forecast, exponent: int, symbol: str) -> str:
        horizon = fc.horizon.isoformat()
        end_display = to_display_decimal(fc.end_minor, exponent)
        if fc.mode is ForecastMode.ANCHORED:
            amount = _format_amount(end_display, symbol)
            coverage = self._coverage_suffix(fc)
            return self.tr(
                "Projected balance{coverage}: ~{amount} by {horizon}"
            ).format(coverage=coverage, amount=amount, horizon=horizon)
        # NET_FLOW — an explicit projected change (double-empty reads "R0").
        amount = self._signed_change(fc.end_minor, end_display, symbol)
        return self.tr("Projected net change: {amount} by {horizon}").format(
            amount=amount, horizon=horizon
        )

    def _coverage_suffix(self, fc: Forecast) -> str:
        """ " (<accounts> only)" when not every account contributed to the anchor
        (D2/D9), else "" — so a partial total is never mistaken for a whole-vault
        balance."""
        total = len(AccountService(self._service.vault).list_accounts())
        if len(fc.anchor_sources) >= total:
            return ""
        names = ", ".join(src.account_name for src in fc.anchor_sources)
        return self.tr(" ({names} only)").format(names=names)

    def _signed_change(self, minor: int, display, symbol: str) -> str:
        """A sign-explicit net-change string: ``+R X`` / ``-R X`` / ``R0`` (D9)."""
        if minor > 0:
            return "+" + _format_amount(display, symbol)
        return _format_amount(display, symbol)  # negative carries its own "-"; 0 -> R0

    def _provenance_text(self, fc: Forecast, exponent: int, symbol: str) -> str:
        # The reason split is built BEFORE the mode branch, because NET_FLOW is
        # exactly the mode a debt-only vault lands in: `_anchor` contributes no
        # cash source, so a credit card holding a real statement balance would
        # otherwise be told "no known balance yet" and never named at all. That
        # is the case INV-14 was written for (FIBR-0179).
        no_balance, not_cash = self._excluded_names(fc)
        if fc.mode is ForecastMode.NET_FLOW:
            text = self.tr(
                "No spendable-cash balance yet — the chart shows the projected "
                "change only."
            )
        else:
            start = _format_amount(to_display_decimal(fc.start_minor, exponent), symbol)
            clauses = [self._source_clause(src) for src in fc.anchor_sources]
            text = self.tr(
                "Starting balance {start} as of today — from {sources}."
            ).format(start=start, sources=", ".join(clauses))
        if no_balance:
            text += " " + self.tr(
                "Excluded (no recorded balance yet): {names}."
            ).format(names=", ".join(no_balance))
        if not_cash:
            text += " " + self.tr(
                "Excluded (only current and savings balances are spendable "
                "cash): {names}."
            ).format(names=", ".join(not_cash))
        return text

    def _source_clause(self, src) -> str:
        clause = self.tr("{name}'s statement of {as_of}").format(
            name=src.account_name, as_of=src.as_of.isoformat()
        )
        if src.since_txn_count > 0:
            # Correctly pluralised; omitted entirely when the count is 0 (D10).
            clause += " " + self.tr(
                "+ %n later transaction(s)", "", src.since_txn_count
            )
        return clause

    def _excluded_names(self, fc: Forecast) -> tuple[list[str], list[str]]:
        """The non-contributing accounts split by *why* (FIBR-0179): cash accounts
        with no recorded balance yet (they join once a balance-bearing statement is
        imported), and non-cash accounts, whose balance is never part of the anchor
        whatever they record. ``account.type`` is the stored STR token."""
        contributing = {src.account_id for src in fc.anchor_sources}
        cash_tokens = {t.value for t in CASH_TYPES}
        no_balance: list[str] = []
        not_cash: list[str] = []
        for account in AccountService(self._service.vault).list_accounts():
            if account.id in contributing:
                continue
            target = no_balance if account.type in cash_tokens else not_cash
            target.append(account.name)
        return no_balance, not_cash

    # -- events table ---------------------------------------------------------
    def _fill_events(self, fc: Forecast, exponent: int, symbol: str) -> None:
        table = self._events_table
        table.setRowCount(len(fc.events))
        for row, event in enumerate(fc.events):
            amount = _format_amount(
                to_display_decimal(event.amount_minor, exponent), symbol
            )
            balance = _format_amount(
                to_display_decimal(event.running_after_minor, exponent), symbol
            )
            table.setItem(row, _COL_DATE, QTableWidgetItem(event.on.isoformat()))
            table.setItem(row, _COL_MERCHANT, QTableWidgetItem(event.merchant))
            table.setItem(row, _COL_AMOUNT, QTableWidgetItem(amount))
            table.setItem(row, _COL_BALANCE, QTableWidgetItem(balance))

    # -- chart theme ----------------------------------------------------------
    def _chart_theme(self) -> ChartTheme:
        """On-screen theme: text from the live palette (ADR-0010 dark default), the
        fixed FIBR-0105 positive/negative colours, transparent background — matching
        the dashboard charts (D11)."""
        return ChartTheme(
            text=self.palette().text().color(),
            positive=_POSITIVE_TEXT,
            negative=_NEGATIVE_TEXT,
        )
