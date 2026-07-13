"""FIBR-0013 — PdfExportService: the PDF is real and the lock is real.

The offscreen chart rasteriser builds a `QChartView` (a QWidget), so every test
that renders a PDF takes the pytest-qt `qapp` fixture — a `QApplication` must
exist or `QChart` construction segfaults (widget-backed chart title items).
Period is pinned to a specific month so renders are deterministic (no clock).
"""

import inspect
from io import BytesIO

import pikepdf
import pytest

from conftest import _PW
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.pdf_export import ExportOptions, PdfExportService
from finbreak.services.reporting import MODE_SPECIFIC_MONTH, ReportPrefs

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
