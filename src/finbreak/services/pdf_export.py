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

import os
from dataclasses import dataclass
from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path

import pikepdf
from PySide6.QtCharts import QChart, QChartView
from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtGui import QColor, QImage, QPageSize, QPdfWriter, QTextDocument

from finbreak.services.reporting import (
    ReportingService,
    ReportPrefs,
    resolve_period,
)
from finbreak.services.transactions import TransactionService
from finbreak.ui._amount import _NEGATIVE_TEXT, _POSITIVE_TEXT, _format_amount
from finbreak.ui.charts import ChartTheme, build_donut_chart, build_trend_chart
from finbreak.vault import Vault


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
        parts = ["<h1>Financial report</h1>"]
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

    def _summary_html(
        self,
        reporting: ReportingService,
        options: ExportOptions,
        today: date,
        symbol: str,
    ) -> str:
        s = reporting.summary(options.prefs, options.account_ids, today)
        inc = _format_amount(s.income, symbol)
        spend = _format_amount(s.expenditure, symbol)
        net = _format_amount(s.net, symbol)
        rows = (
            f"<tr><td>Income</td><td>{inc}</td></tr>"
            f"<tr><td>Spending</td><td>{spend}</td></tr>"
            f"<tr><td>Net</td><td>{net}</td></tr>"
        )
        return f"<h2>Summary</h2><table>{rows}</table>"

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
        donut = build_donut_chart(spending, "Uncategorised", "Other", theme.chart)
        trend_chart = build_trend_chart(trend, "Income", "Spending", theme.chart)
        images = [
            ("finbreak://chart/donut", self._rasterise(donut)),
            ("finbreak://chart/trend", self._rasterise(trend_chart)),
        ]
        html = (
            "<h2>Charts</h2>"
            '<img src="finbreak://chart/donut" width="500">'
            '<img src="finbreak://chart/trend" width="500">'
        )
        return html, images

    def _transactions_html(
        self, options: ExportOptions, today: date, symbol: str
    ) -> str:
        start, end = resolve_period(options.prefs, today)
        start_iso, end_iso = start.isoformat(), end.isoformat()
        rows = TransactionService(self._vault).list_transactions()
        selected = [
            (txn, disp, acct, cat)
            for (txn, disp, acct, cat) in rows
            if start_iso <= txn.occurred_on <= end_iso
            and (options.account_ids is None or txn.account_id in options.account_ids)
        ]
        selected.sort(key=lambda r: r[0].occurred_on)
        body = "".join(
            f"<tr><td>{escape(txn.occurred_on)}</td><td>{escape(txn.description)}</td>"
            f"<td>{escape(cat)}</td><td>{_format_amount(disp, symbol)}</td></tr>"
            for (txn, disp, acct, cat) in selected
        )
        return f"<h2>Transactions</h2><table>{body}</table>"

    @staticmethod
    def _rasterise(chart: QChart, width: int = 500, height: int = 320) -> QImage:
        """A `QChart` → `QImage` offscreen (no shown window). Needs a live
        `QApplication` (QChartView is a QWidget)."""
        view = QChartView(chart)
        view.resize(width, height)
        return view.grab().toImage()
