"""PdfExportService — render a period's report to a PDF, optionally AES-256 locked.

FIBR-0013. Read-only over the vault. The renderer builds an HTML document
(`QTextDocument`), embeds the donut + trend charts as **offscreen** rasters from
the shared `ui.charts` builders (INV-8), and prints it to an **in-memory**
`QPdfWriter`. When a password is set the plaintext bytes never touch disk:
`pikepdf` encrypts them in memory (AES-256, R=6) and `export()` writes the single
final file **atomically** (temp → `os.replace`), the sole writer (INV-1/INV-2).

`render_pdf_bytes` takes **no path** — a structural guarantee that no plaintext
code path can reach disk. The offscreen rasteriser builds a `QChartView` (a
QWidget), so a `QApplication` must exist when rendering (always true in the app).
"""

from __future__ import annotations

import calendar
import os
from dataclasses import dataclass
from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path

import pikepdf
from PySide6.QtCharts import QChart, QChartView
from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice, QUrl
from PySide6.QtGui import QColor, QImage, QPageSize, QPdfWriter, QTextDocument

from finbreak.datetime_format import format_date
from finbreak.models import Account, Summary
from finbreak.repositories.settings import SettingsRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import DATETIME_SYSTEM
from finbreak.services.reporting import (
    MODE_CURRENT_MONTH,
    MODE_PREVIOUS_MONTH,
    MODE_SPECIFIC_YEAR,
    MODE_YEAR_TO_DATE,
    ReportingService,
    ReportPrefs,
    resolve_period,
)
from finbreak.services.transactions import TransactionService
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.ui._amount import _NEGATIVE_TEXT, _POSITIVE_TEXT, _format_amount
from finbreak.ui.charts import ChartTheme, build_donut_chart, build_trend_chart
from finbreak.vault import Vault


def _tr(text: str) -> str:
    """Translate outside a QObject (the service isn't one). No ``.qm`` is loaded
    yet, so this returns the source string — the `tr()` convention that keeps every
    user-facing string translatable (coding.md § 5.2), the non-widget analogue of
    ``self.tr()``."""
    return QCoreApplication.translate("PdfExport", text)


def period_filename_slug(prefs: ReportPrefs, today: date) -> str:
    """The terse **filename** slug for the default save name (D9): ``YYYY-MM`` for
    the month modes (the period's end month), ``YYYY-ytd`` for year-to-date,
    ``YYYY`` for a specific year. Distinct from D2's human-readable period line."""
    _, end = resolve_period(prefs, today)
    if prefs.mode == MODE_YEAR_TO_DATE:
        return f"{end.year}-ytd"
    if prefs.mode == MODE_SPECIFIC_YEAR:
        return str(end.year)
    return f"{end.year:04d}-{end.month:02d}"


@dataclass(frozen=True)
class ExportOptions:
    """The user's export selection (from the dialog, D7). ``account_ids`` is
    ``None`` ⇒ all accounts, else the chosen subset (D4). ``password`` is ``None``
    or empty ⇒ unencrypted (INV-1). ``theme`` is ``"light"`` (default) or
    ``"dark"`` (INV-9)."""

    prefs: ReportPrefs
    account_ids: frozenset[int] | None
    include_summary: bool
    include_charts: bool
    include_transactions: bool
    theme: str = "light"
    password: str | None = None


@dataclass(frozen=True)
class _PdfTheme:
    """Explicit colours for one export theme (INV-9): the HTML page/text colours
    plus the `ChartTheme` the shared builders paint with. No live-palette read."""

    page: str
    text: str
    chart: ChartTheme


def _pdf_theme(name: str) -> _PdfTheme:
    """Map the ``"light"``/``"dark"`` token to its explicit colour set. Light is
    print-friendly (white page, dark text); Dark mirrors the app panel (ADR-0002).
    The positive/negative money tints are the fixed FIBR-0105 colours in both."""
    if name == "dark":
        return _PdfTheme(
            page="#242830",
            text="#e6e6e6",
            chart=ChartTheme(
                text=QColor("#e6e6e6"),
                positive=_POSITIVE_TEXT,
                negative=_NEGATIVE_TEXT,
                background=QColor("#242830"),
            ),
        )
    return _PdfTheme(
        page="#ffffff",
        text="#1a1a1a",
        chart=ChartTheme(
            text=QColor("#1a1a1a"),
            positive=_POSITIVE_TEXT,
            negative=_NEGATIVE_TEXT,
            background=QColor("#ffffff"),
        ),
    )


class PdfExportService:
    """Vault-scoped, read-only PDF renderer (FIBR-0013)."""

    def __init__(self, vault: Vault):
        self._vault = vault

    def render_pdf_bytes(
        self, options: ExportOptions, today: date | None = None
    ) -> bytes:
        """The report as PDF bytes — encrypted iff ``options.password`` is set.
        Takes **no path**: the (possibly plaintext) bytes live only in memory
        (INV-2)."""
        today = today or date.today()
        html, images = self._build_html(options, today)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        writer = QPdfWriter(buffer)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        doc = QTextDocument()
        for url, image in images:
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(url), image)
        doc.setHtml(html)
        doc.print_(writer)
        buffer.close()
        pdf_bytes = bytes(buffer.data().data())  # QByteArray -> bytes
        if options.password:
            pdf_bytes = self._encrypt(pdf_bytes, options.password)
        return pdf_bytes

    def export(
        self, options: ExportOptions, out_path: str | Path, today: date | None = None
    ) -> None:
        """Render and write the **single** final file atomically (temp →
        `os.replace`). On any failure the temp is unlinked, so no partial or
        accidentally-unencrypted file is ever left (INV-2/INV-12)."""
        out_path = Path(out_path)
        pdf_bytes = self.render_pdf_bytes(options, today)
        tmp = out_path.with_name(out_path.name + ".part")
        try:
            tmp.write_bytes(pdf_bytes)
            os.replace(tmp, out_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    @staticmethod
    def _encrypt(pdf_bytes: bytes, password: str) -> bytes:
        """AES-256 encrypt in memory (R=6, user == owner). No disk I/O (INV-2)."""
        with pikepdf.open(BytesIO(pdf_bytes)) as pdf:
            out = BytesIO()
            pdf.save(
                out,
                encryption=pikepdf.Encryption(user=password, owner=password, R=6),
            )
            return out.getvalue()

    # -- HTML assembly --------------------------------------------------------

    def _build_html(
        self, options: ExportOptions, today: date
    ) -> tuple[str, list[tuple[str, QImage]]]:
        theme = _pdf_theme(options.theme)
        reporting = ReportingService(self._vault)
        symbol = reporting.base_currency()
        images: list[tuple[str, QImage]] = []
        parts = [self._header_html(options, today, symbol)]
        if options.include_summary:
            parts.append(self._summary_html(reporting, options, today, symbol))
        if options.include_charts:
            chart_html, chart_images = self._charts_html(
                reporting, options, today, theme
            )
            parts.append(chart_html)
            images.extend(chart_images)
        if options.include_transactions:
            parts.append(self._transactions_html(options, today, symbol))
        body = "".join(parts)
        html = (
            f'<html><body style="color:{theme.text};background-color:{theme.page};">'
            f"{body}</body></html>"
        )
        return html, images

    # -- header ---------------------------------------------------------------

    def _date_pref(self) -> str:
        return (
            SettingsRepository(self._vault.connection).get("date_format")
            or DATETIME_SYSTEM
        )

    def _accounts_in_scope(self, options: ExportOptions) -> list[Account]:
        """The live accounts the export covers, **sorted by name** (INV-5). ``None``
        ⇒ every account; a subset ⇒ those still-present (a stale id drops out, D5)."""
        accounts = AccountService(self._vault).list_accounts()
        if options.account_ids is not None:
            accounts = [a for a in accounts if a.id in options.account_ids]
        return sorted(accounts, key=lambda a: a.name)

    def _account_names(self, options: ExportOptions) -> str:
        """``All accounts`` for ``None``; the names comma-joined for ≤ 3; ``{n}
        accounts`` beyond 3 (a bounded header string, D2)."""
        if options.account_ids is None:
            return _tr("All accounts")
        names = [a.name for a in self._accounts_in_scope(options)]
        if len(names) > 3:
            return _tr("{n} accounts").format(n=len(names))
        return ", ".join(names)

    def _period_label(self, options: ExportOptions, today: date) -> str:
        """The human-readable period line per mode (D2), distinct from D9's terse
        filename slug."""
        prefs = options.prefs
        start, end = resolve_period(prefs, today)
        if prefs.mode == MODE_SPECIFIC_YEAR:
            return str(end.year)
        if prefs.mode == MODE_YEAR_TO_DATE:
            pref = self._date_pref()
            return _tr("Year to date ({start} – {end})").format(
                start=format_date(start.isoformat(), pref),
                end=format_date(end.isoformat(), pref),
            )
        month = f"{calendar.month_name[end.month]} {end.year}"
        if prefs.mode == MODE_CURRENT_MONTH:
            return _tr("This month ({label})").format(label=month)
        if prefs.mode == MODE_PREVIOUS_MONTH:
            return _tr("Previous month ({label})").format(label=month)
        return month  # SPECIFIC_MONTH — the month alone, no redundant parenthetical

    def _header_html(self, options: ExportOptions, today: date, symbol: str) -> str:
        title = _tr("finbreak — Financial Report")
        generated = _tr("Generated {date} · Accounts: {names} · {currency}").format(
            date=escape(format_date(today.isoformat(), self._date_pref())),
            names=escape(self._account_names(options)),
            currency=escape(symbol),
        )
        period = _tr("Period: {label}").format(
            label=escape(self._period_label(options, today))
        )
        return f"<h1>{escape(title)}</h1><p>{generated}</p><p>{period}</p>"

    # -- sections -------------------------------------------------------------

    def _summary_html(
        self,
        reporting: ReportingService,
        options: ExportOptions,
        today: date,
        symbol: str,
    ) -> str:
        combined = reporting.summary(options.prefs, options.account_ids, today)
        html = f"<h2>{_tr('Summary')}</h2>" + self._summary_table(combined, symbol)
        in_scope = self._accounts_in_scope(options)
        if len(in_scope) > 1:
            # Per-account lines (multi-account only, INV-5): each over its own set,
            # so combined = Σ per-account (accounts disjoint). Sorted by name.
            rows = "".join(
                self._per_account_row(reporting, options.prefs, today, symbol, acct)
                for acct in in_scope
            )
            html += (
                f"<h3>{_tr('By account')}</h3><table>"
                f"<tr><th></th><th>{_tr('Income')}</th>"
                f"<th>{_tr('Spending')}</th><th>{_tr('Net')}</th></tr>"
                f"{rows}</table>"
            )
        return html

    def _summary_table(self, s: Summary, symbol: str) -> str:
        inc = _format_amount(s.income, symbol)
        spend = _format_amount(s.expenditure, symbol)
        net = _format_amount(s.net, symbol)
        return (
            "<table>"
            f"<tr><td>{_tr('Income')}</td><td>{inc}</td></tr>"
            f"<tr><td>{_tr('Spending')}</td><td>{spend}</td></tr>"
            f"<tr><td>{_tr('Net')}</td><td>{net}</td></tr>"
            "</table>"
        )

    def _per_account_row(
        self,
        reporting: ReportingService,
        prefs: ReportPrefs,
        today: date,
        symbol: str,
        acct: Account,
    ) -> str:
        s = reporting.summary(prefs, frozenset({acct.id}), today)
        return (
            f"<tr><td>{escape(acct.name)}</td>"
            f"<td>{_format_amount(s.income, symbol)}</td>"
            f"<td>{_format_amount(s.expenditure, symbol)}</td>"
            f"<td>{_format_amount(s.net, symbol)}</td></tr>"
        )

    def _charts_html(
        self,
        reporting: ReportingService,
        options: ExportOptions,
        today: date,
        theme: _PdfTheme,
    ) -> tuple[str, list[tuple[str, QImage]]]:
        spending = reporting.spending_by_category(
            options.prefs, options.account_ids, today
        )
        trend = reporting.monthly_trend(options.prefs, options.account_ids, today)
        donut = build_donut_chart(
            spending, _tr("Uncategorised"), _tr("Other"), theme.chart
        )
        trend_chart = build_trend_chart(
            trend, _tr("Income"), _tr("Spending"), theme.chart
        )
        images = [
            ("finbreak://chart/donut", self._rasterise(donut)),
            ("finbreak://chart/trend", self._rasterise(trend_chart)),
        ]
        html = (
            f"<h2>{_tr('Charts')}</h2>"
            '<img src="finbreak://chart/donut" width="500">'
            '<img src="finbreak://chart/trend" width="500">'
        )
        return html, images

    def _transactions_html(
        self, options: ExportOptions, today: date, symbol: str
    ) -> str:
        start, end = resolve_period(options.prefs, today)
        start_iso, end_iso = start.isoformat(), end.isoformat()
        transfer_ids = TransferDetectionService(
            self._vault
        ).confirmed_transfer_txn_ids()
        rows = TransactionService(self._vault).list_transactions()
        selected = [
            (txn, disp, acct, cat)
            for (txn, disp, acct, cat) in rows
            if start_iso <= txn.occurred_on <= end_iso
            and (options.account_ids is None or txn.account_id in options.account_ids)
        ]
        # (occurred_on, id) — id tiebreak keeps same-date rows reproducible (INV-6).
        selected.sort(key=lambda r: (r[0].occurred_on, r[0].id))
        show_account = len(self._accounts_in_scope(options)) > 1
        header = f"<tr><th>{_tr('Date')}</th>"
        if show_account:
            header += f"<th>{_tr('Account')}</th>"
        header += (
            f"<th>{_tr('Description')}</th><th>{_tr('Category')}</th>"
            f"<th>{_tr('Amount')}</th></tr>"
        )
        body_rows = []
        for txn, disp, acct, cat in selected:
            # Marker keyed on the transfer-id SET, not a category name, so a real
            # category literally named "Transfer" is unaffected (INV-6).
            category_cell = _tr("⇄ Transfer") if txn.id in transfer_ids else escape(cat)
            cells = [f"<td>{escape(txn.occurred_on)}</td>"]
            if show_account:
                cells.append(f"<td>{escape(acct)}</td>")
            cells.append(f"<td>{escape(txn.description)}</td>")
            cells.append(f"<td>{category_cell}</td>")
            cells.append(f"<td>{_format_amount(disp, symbol)}</td>")
            body_rows.append("<tr>" + "".join(cells) + "</tr>")
        footnote_text = _tr(
            "Summary and charts exclude money moved between your own "
            "accounts (transfers)."
        )
        return (
            f"<h2>{_tr('Transactions')}</h2>"
            f"<table>{header}{''.join(body_rows)}</table>"
            f"<p>{footnote_text}</p>"
        )

    @staticmethod
    def _rasterise(chart: QChart, width: int = 500, height: int = 320) -> QImage:
        """A `QChart` → `QImage` offscreen (no shown window). Needs a live
        `QApplication` (QChartView is a QWidget)."""
        view = QChartView(chart)
        view.resize(width, height)
        return view.grab().toImage()
