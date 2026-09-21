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


def _options(prefs=_JAN, account_ids=None, password=None, **on):
    flags = {
        "include_summary": True,
        "include_charts": True,
        "include_transactions": True,
    }
    flags.update(on)
    return ExportOptions(
        prefs=prefs, account_ids=account_ids, password=password, **flags
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


def test_empty_period_charts_shows_placeholder_not_blank_donut(qapp, service):
    # INV-13: an empty period draws the per-surface empty placeholder (mirroring
    # the on-screen dashboard), not a slice-less blank donut.
    a = _accounts(service)[0].id
    _add(service, a, 100_00)  # January income; export empty March 2020
    empty = ReportPrefs(MODE_SPECIFIC_MONTH, year=2020, month=3)
    html, imgs = _svc(service)._build_html(
        _options(prefs=empty, include_summary=False, include_transactions=False),
        _TODAY,
    )
    assert "No spending in this period" in html
    # Only the trend chart is embedded — no blank-donut image.
    assert [url for url, _ in imgs] == ["finbreak://chart/trend"]


def test_empty_account_set_is_empty_report_not_all(qapp, service):
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(_options(account_ids=frozenset()), _TODAY)
    assert "By account" not in html
    assert _format_amount(Decimal("100.00"), _symbol(service)) not in html  # empty


def test_report_is_always_rendered_on_a_light_page(qapp, service):
    """FIBR-0217. The report has ONE palette and it is the print-friendly one.

    A caller cannot ask for anything else: `ExportOptions` carries no theme
    field, so there is no dark page for Qt to draw its black page number on.
    """
    a = _accounts(service)[0].id
    _add(service, a, 100_00)
    html, _ = _svc(service)._build_html(_options(), _TODAY)
    assert "#ffffff" in html and "#1a1a1a" in html
    # The withdrawn dark palette, so a reintroduction has to delete this line.
    assert "#242830" not in html and "#e6e6e6" not in html


def test_FIBR0217_export_options_offers_no_theme_choice(qapp, service):
    """The other half: the option is gone from the API, not merely unused.

    Left as a field with one accepted value it would read as a working choice
    and invite the dark branch back -- which is what put an unreadable page
    number on a money report.
    """
    assert "theme" not in ExportOptions.__dataclass_fields__
    with pytest.raises(TypeError):
        _options(theme="dark")


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


# --------------------------------------------------------------------------- #
# INV-2 — the export temp is owner-only and never follows a symlink
# --------------------------------------------------------------------------- #
def test_export_temp_is_owner_only_and_final_file_inherits_it(qapp, service, tmp_path):
    """An exported report is a full spending profile — dates, descriptions,
    counterparties, amounts, per-account totals — and a blank password produces it
    in PLAINTEXT by design (FIBR-0013 INV-1). It must not land group/world
    readable just because the user's umask is loose.

    `Path.write_bytes` opens 0o666-and-umask, and `os.replace` preserves the
    inode, so the FINAL pdf carried 0644 (umask 022) or 0664 (umask 002). The
    sibling `services/backup.py` already opens its temp `0o600` explicitly; this
    is the same class of file with the weaker posture.
    """
    out = tmp_path / "report.pdf"
    _svc(service).export(_options(), out)

    mode = out.stat().st_mode & 0o777
    assert mode == 0o600, f"exported report is mode {mode:o}, expected 600"


def test_export_temp_refuses_to_follow_a_symlink(qapp, service, tmp_path):
    """The `.part` name is fully predictable from the output name, so in any
    shared or group-writable directory an attacker can pre-plant it as a symlink
    to a file they want overwritten — `write_bytes` follows it and truncates the
    target, as the user. `O_NOFOLLOW` is the fix, and `backup.py` already uses it.
    """
    target = tmp_path / "precious.txt"
    target.write_text("do not clobber", encoding="utf-8")
    out = tmp_path / "report.pdf"
    (tmp_path / "report.pdf.part").symlink_to(target)

    _svc(service).export(_options(), out)

    # The planted link is cleared rather than written through, so the export still
    # succeeds — what must NOT happen is the target being truncated.
    assert target.read_text(encoding="utf-8") == "do not clobber", (
        "the export followed a symlink and overwrote an unrelated file"
    )
    assert out.exists() and out.read_bytes().startswith(b"%PDF")
    assert out.stat().st_mode & 0o777 == 0o600


def test_FIBR0327_period_month_name_follows_the_locale(qapp, service, monkeypatch):
    """FIBR-0327 — the month in the period line came from
    ``calendar.month_name``, which is C-locale English whatever the app's
    language, in a module where every other string goes through ``_tr()``.

    Asserted through ``QLocale``'s own data rather than through a translation
    catalogue, so the test needs no ``.qm`` file loaded: switching the default
    locale to French must move the month name. ``ui/month_summary.py`` already
    spelled it this way.
    """
    from PySide6.QtCore import QLocale

    a = _accounts(service)[0].id
    _add(service, a, 100_00)

    previous = QLocale()
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))
    try:
        html, _ = _svc(service)._build_html(_options(), _TODAY)
    finally:
        QLocale.setDefault(previous)

    assert "janvier 2026" in html, (
        "the period line must name the month through QLocale, not through "
        "calendar.month_name."
    )
    assert "January 2026" not in html


def test_the_report_and_its_filename_agree_on_the_period(
    qtbot, service, monkeypatch, tmp_path
):
    """FIBR-0013 INV-7 — the report's period resolves exactly as Home's.

    Home (`ui/home.py`) and the export dialog (`ui/export_dialog.py`) both read
    the APP clock, ``datetime_format.today()``, which follows the zone the user
    pinned in Settings. ``_on_export_requested`` built the default FILENAME from
    that clock and then called ``export()`` with no ``today``, so the CONTENTS
    fell back to ``date.today()`` — the machine's zone. Where the two are on
    different calendar days, the filename names one month and the report covers
    another, on a money document.

    Two clocks are patched on purpose, because that IS the condition: a pinned
    zone and a machine zone on different calendar days. After the fix the second
    patch is inert, which is the property being asserted — the output must not
    follow the machine clock.

    Asserts on the PDF's own period line and on the offered filename, never on
    what the service was handed. The defect is that the two artefacts disagree,
    and only the pair shows it.
    """
    import pdfplumber

    from finbreak.services import pdf_export as pdf_export_module
    from finbreak.ui import main_window as shell_module
    from finbreak.ui.main_window import MainWindow

    # The pinned zone says it is already March, so previous-month is February.
    app_clock = date(2026, 3, 1)
    # The machine says it is still February, so previous-month is January.
    system_clock = date(2026, 2, 28)

    monkeypatch.setattr(shell_module, "app_today", lambda: app_clock)

    class _SystemClock(date):
        @classmethod
        def today(cls):
            return system_clock

    monkeypatch.setattr(pdf_export_module, "date", _SystemClock)

    a = _accounts(service)[0].id
    _add(service, a, -50_00, occurred_on="2026-01-10", desc="january row")
    _add(service, a, -70_00, occurred_on="2026-02-10", desc="february row")

    out = tmp_path / "report.pdf"
    offered: list[str] = []

    class _SaveDialog:
        @staticmethod
        def getSaveFileName(parent, caption, default_name, filter_):
            offered.append(default_name)
            return str(out), filter_

    monkeypatch.setattr(shell_module, "QFileDialog", _SaveDialog)

    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    window._open_export()
    window._on_export_requested()

    assert offered, (
        "precondition: the save dialog must have been reached, or nothing was "
        "exported and this leg is vacuous."
    )
    assert "2026-02" in offered[0], (
        "precondition: the offered filename must name February — the app "
        "clock's previous month — or the two clocks were not made to disagree "
        "and the defect is unreachable.\n"
        f"  offered: {offered[0]!r}"
    )
    assert out.exists(), "precondition: the export must have written a file."

    with pdfplumber.open(out) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    assert "February 2026" in text, (
        "the report's period must resolve on the SAME clock as the filename "
        "(FIBR-0013 INV-7: the period resolves exactly as Home's). The "
        "filename offered February; the report was rendered from "
        "`date.today()` instead of the pinned zone, so it covers a different "
        "month.\n"
        f"  expected: 'February 2026' in the period line\n"
        f"  offered filename: {offered[0]!r}"
    )
    assert "January 2026" not in text, (
        "the report covered January — the MACHINE clock's previous month — "
        "while its filename named February. That is the wrong-month split.\n"
        f"  offered filename: {offered[0]!r}"
    )
