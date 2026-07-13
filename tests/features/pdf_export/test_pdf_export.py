"""FIBR-0013 — PdfExportService: the PDF is real and the lock is real.

The offscreen chart rasteriser builds a `QChartView` (a QWidget), so every test
that renders a PDF takes the pytest-qt `qapp` fixture — a `QApplication` must
exist or `QChart` construction segfaults (widget-backed chart title items).
Period is pinned to a specific month so renders are deterministic (no clock).
"""

import inspect
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pikepdf
import pytest

from conftest import _PW
from finbreak.errors import VaultLockedError
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.pdf_export import ExportOptions, PdfExportService
from finbreak.services.reporting import (
    MODE_SPECIFIC_MONTH,
    ReportingService,
    ReportPrefs,
)
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.ui._amount import _format_amount

_TODAY = date(2026, 1, 15)

pytestmark = pytest.mark.features

_JAN = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=1)


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _accounts(service):
    return AccountService(service.vault).list_accounts()


def _add(service, account_id, amount_minor, occurred_on="2026-01-05", desc="x"):
    return TransactionRepository(service.vault.connection).add(
        account_id, occurred_on, amount_minor, desc
    )


def _options(prefs=_JAN, account_ids=None, password=None, theme="light", **on):
    flags = {
        "include_summary": True,
        "include_charts": True,
        "include_transactions": True,
    }
    flags.update(on)
    return ExportOptions(
        prefs=prefs, account_ids=account_ids, theme=theme, password=password, **flags
    )


def test_render_produces_valid_pdf(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 50_00)
    _add(service, a, -20_00)
    pdf = PdfExportService(service.vault).render_pdf_bytes(_options())
    assert pdf[:5] == b"%PDF-"
    with pikepdf.open(BytesIO(pdf)) as doc:
        assert len(doc.pages) >= 1


def test_blank_password_is_unencrypted(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 50_00)
    pdf = PdfExportService(service.vault).render_pdf_bytes(_options(password=None))
    pikepdf.open(BytesIO(pdf)).close()  # opens with no password


def test_password_encrypts_round_trip(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 50_00)
    pdf = PdfExportService(service.vault).render_pdf_bytes(
        _options(password="secret12")
    )
    pikepdf.open(BytesIO(pdf), password="secret12").close()  # opens WITH
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(BytesIO(pdf))  # refused WITHOUT


def test_render_pdf_bytes_takes_no_path(service):
    # INV-2 (structural): the renderer cannot write plaintext to disk.
    params = set(inspect.signature(PdfExportService.render_pdf_bytes).parameters)
    assert "path" not in params
    assert "out_path" not in params


# --------------------------------------------------------------------------- #
# Content — header / sections / per-account / transfers / theme (D2/D5/D6/D10)
# White-box over `_build_html` (the spec's machine-checkable HTML proxy).
# --------------------------------------------------------------------------- #
def _svc(service):
    return PdfExportService(service.vault)


def _add_account(service, name, kind="current"):
    return AccountService(service.vault).add_account(name, kind).id


def _symbol(service):
    return ReportingService(service.vault).base_currency()


def test_all_accounts_header_says_all_accounts(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(_options(), _TODAY)
    assert "All accounts" in html


def test_named_accounts_header_lists_names(qapp, service):
    a = _accounts(service)[0].id
    b = _add_account(service, "Savings", "savings")
    _add(service, a, 100_00)
    _add(service, b, 50_00)
    html, _ = _svc(service)._build_html(_options(account_ids=frozenset({a, b})), _TODAY)
    assert "Savings" in html


def test_over_three_accounts_collapses_to_count(qapp, service):
    ids = {_accounts(service)[0].id}
    for n in ("Bee", "Cee", "Dee"):
        ids.add(_add_account(service, n))
    html, _ = _svc(service)._build_html(_options(account_ids=frozenset(ids)), _TODAY)
    header = html.split("<h2>", 1)[0]  # the header block, before the first section
    assert "4 accounts" in header
    # The header collapses names; the per-account Summary block still lists each.
    assert "Bee" not in header


def test_specific_month_period_label(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(_options(), _TODAY)
    assert "January 2026" in html


def test_charts_only_omits_other_sections_and_footnote(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, -30_00)
    html, imgs = _svc(service)._build_html(
        _options(include_summary=False, include_transactions=False), _TODAY
    )
    assert "<h2>Charts</h2>" in html
    assert "<h2>Summary</h2>" not in html
    assert "<h2>Transactions</h2>" not in html
    assert "transfer" not in html.lower()  # no footnote without the list
    assert len(imgs) == 2


def test_summary_only_has_no_chart_images(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, imgs = _svc(service)._build_html(
        _options(include_charts=False, include_transactions=False), _TODAY
    )
    assert "<h2>Summary</h2>" in html
    assert "<h2>Transactions</h2>" not in html
    assert imgs == []


def test_transactions_footnote_present_when_list_included(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, -30_00)
    html, _ = _svc(service)._build_html(
        _options(include_summary=False, include_charts=False), _TODAY
    )
    assert "transfer" in html.lower()  # the exclusion footnote


def test_multi_account_per_account_lines_sorted_by_name(qapp, service):
    a = _accounts(service)[0].id  # "Default"
    z = _add_account(service, "Zenith")
    m = _add_account(service, "Middle")
    _add(service, a, 100_00)
    _add(service, z, 10_00)
    _add(service, m, 20_00)
    html, _ = _svc(service)._build_html(
        _options(account_ids=frozenset({a, z, m})), _TODAY
    )
    block = html.split("By account", 1)[1]  # the per-account block
    assert block.index("Default") < block.index("Middle") < block.index("Zenith")


def test_single_account_omits_per_account_block(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(_options(), _TODAY)  # None ⇒ the one account
    assert "By account" not in html


def test_all_accounts_per_account_covers_every_account(qapp, service):
    a = _accounts(service)[0].id
    b = _add_account(service, "Savings", "savings")
    _add(service, a, 100_00)
    _add(service, b, 50_00)
    html, _ = _svc(service)._build_html(_options(account_ids=None), _TODAY)
    block = html.split("By account", 1)[1]
    assert "Savings" in block


def test_account_column_only_when_multi_account(qapp, service):
    a = _accounts(service)[0].id
    b = _add_account(service, "Savings", "savings")
    _add(service, a, -10_00)
    _add(service, b, -20_00)
    multi, _ = _svc(service)._build_html(
        _options(account_ids=None, include_summary=False, include_charts=False), _TODAY
    )
    assert "<th>Account</th>" in multi
    single, _ = _svc(service)._build_html(
        _options(
            account_ids=frozenset({a}), include_summary=False, include_charts=False
        ),
        _TODAY,
    )
    assert "<th>Account</th>" not in single


def test_transfer_excluded_from_summary_but_marked_in_list(qapp, service):
    a = _accounts(service)[0].id
    b = _add_account(service, "Savings", "savings")
    _add(service, a, 100_00, desc="salary")
    debit = _add(service, a, -50_00, desc="to savings")
    credit = _add(service, b, 50_00, desc="from current")
    TransferDetectionService(service.vault).confirm(debit, credit)
    html, _ = _svc(service)._build_html(_options(account_ids=None), _TODAY)
    symbol = _symbol(service)
    # Summary income is the salary only — the +50 transfer leg is excluded.
    assert _format_amount(Decimal("100.00"), symbol) in html
    assert _format_amount(Decimal("150.00"), symbol) not in html
    # The list is complete and marks both transfer legs.
    assert "to savings" in html and "from current" in html
    assert "⇄ Transfer" in html


def test_same_date_rows_sorted_by_id(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, -10_00, occurred_on="2026-01-07", desc="alpha")
    _add(service, a, -20_00, occurred_on="2026-01-07", desc="beta")
    html, _ = _svc(service)._build_html(
        _options(include_summary=False, include_charts=False), _TODAY
    )
    assert html.index("alpha") < html.index("beta")  # ascending id tiebreak


def test_empty_period_still_valid_pdf(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)  # January data; export an empty March 2020
    empty = ReportPrefs(MODE_SPECIFIC_MONTH, year=2020, month=3)
    pdf = _svc(service).render_pdf_bytes(_options(prefs=empty))
    assert pdf[:5] == b"%PDF-"


def test_empty_account_set_is_empty_report_not_all(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(_options(account_ids=frozenset()), _TODAY)
    assert "By account" not in html
    assert _format_amount(Decimal("100.00"), _symbol(service)) not in html  # empty


def test_light_theme_colours_in_html(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(_options(theme="light"), _TODAY)
    assert "#ffffff" in html and "#1a1a1a" in html


def test_dark_theme_colours_in_html(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(_options(theme="dark"), _TODAY)
    assert "#242830" in html and "#e6e6e6" in html


def test_known_total_appears_in_summary(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 123_45)
    _add(service, a, 76_55)  # income 200.00 exactly
    html, _ = _svc(service)._build_html(
        _options(include_charts=False, include_transactions=False), _TODAY
    )
    assert _format_amount(Decimal("200.00"), _symbol(service)) in html


# --------------------------------------------------------------------------- #
# export() atomicity + INV-12 failure modes + INV-2 no-plaintext-to-disk guard.
# --------------------------------------------------------------------------- #
def test_export_writes_valid_pdf_and_cleans_temp(qapp, service, tmp_path):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    out = tmp_path / "report.pdf"
    _svc(service).export(_options(), out)
    with pikepdf.open(str(out)) as doc:
        assert len(doc.pages) >= 1
    assert not (tmp_path / "report.pdf.part").exists()  # temp removed after replace


def test_export_encrypted_file_opens_only_with_password(qapp, service, tmp_path):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    out = tmp_path / "locked.pdf"
    _svc(service).export(_options(password="secret12"), out)
    pikepdf.open(str(out), password="secret12").close()
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(str(out))


def test_export_write_error_leaves_no_file(qapp, service, tmp_path):
    # INV-12(a): an unwritable path — the temp write raises before os.replace.
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    out = tmp_path / "missing_dir" / "report.pdf"  # parent does not exist
    with pytest.raises(OSError):
        _svc(service).export(_options(), out)
    assert not out.exists()
    assert not out.with_name("report.pdf.part").exists()


def test_export_vault_locked_leaves_no_file(qapp, service, tmp_path):
    # INV-12(b): a vault lock mid-export — render raises before any write.
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    out = tmp_path / "report.pdf"
    svc = _svc(service)
    service.lock()
    with pytest.raises(VaultLockedError):
        svc.export(_options(), out)
    assert not out.exists()
    assert not (tmp_path / "report.pdf.part").exists()


def test_export_encryption_error_leaves_no_file(qapp, service, tmp_path, monkeypatch):
    # INV-12(c): a pikepdf encryption failure — render raises before any write, so
    # no partial and (crucially) no UNENCRYPTED fallback file is left (INV-2).
    import finbreak.services.pdf_export as mod

    def _boom(*args, **kwargs):
        raise RuntimeError("encryption boom")

    monkeypatch.setattr(mod.pikepdf, "Encryption", _boom)
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    out = tmp_path / "report.pdf"
    with pytest.raises(RuntimeError):
        _svc(service).export(_options(password="secret12"), out)
    assert not out.exists()
    assert not (tmp_path / "report.pdf.part").exists()


def test_render_with_password_writes_nothing_to_disk(qapp, service, monkeypatch):
    # INV-2 (behavioural): render+encrypt is pure in-memory — no Path.write_bytes.
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    writes: list[str] = []
    monkeypatch.setattr(
        Path, "write_bytes", lambda self, data: writes.append(str(self))
    )
    pdf = _svc(service).render_pdf_bytes(_options(password="secret12"))
    assert writes == []
    pikepdf.open(BytesIO(pdf), password="secret12").close()  # really encrypted


def test_stale_account_id_drops_out_no_crash(qapp, service):
    # D5: an id in account_ids that no longer exists (deleted after the dialog
    # snapshot) simply drops out — it matches no rows and adds no per-account line.
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(
        _options(account_ids=frozenset({a, 424242})), _TODAY
    )
    # Only one live account is in scope ⇒ a single-account export (no By-account
    # block), and no crash from the phantom id.
    assert "By account" not in html


def test_period_filename_slug_per_mode():
    from finbreak.services.pdf_export import period_filename_slug
    from finbreak.services.reporting import MODE_SPECIFIC_YEAR, MODE_YEAR_TO_DATE

    today = date(2026, 7, 13)
    month = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=6)
    assert period_filename_slug(month, today) == "2026-06"
    assert (
        period_filename_slug(ReportPrefs(MODE_SPECIFIC_YEAR, year=2025), today)
        == "2025"
    )
    assert period_filename_slug(ReportPrefs(MODE_YEAR_TO_DATE), today) == "2026-ytd"


def test_rasterise_returns_non_empty_image(qapp):
    # INV-8: the offscreen chart raster is a real, non-null image.
    from PySide6.QtGui import QColor

    from finbreak.models import CategorySpend
    from finbreak.ui.charts import ChartTheme, build_donut_chart

    theme = ChartTheme(QColor("#000000"), QColor("#00ff00"), QColor("#ff0000"), None)
    chart = build_donut_chart(
        [CategorySpend(1, "Food", Decimal("10"))], "Uncat", "Other", theme
    )
    img = PdfExportService._rasterise(chart)
    assert not img.isNull()
    assert img.width() > 0 and img.height() > 0
