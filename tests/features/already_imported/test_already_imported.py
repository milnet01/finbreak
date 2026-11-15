"""FIBR-0088 — warn before importing a file that was already imported.

Enforces docs/specs/FIBR-0088-already-imported-check.md INV-1 to INV-8 and
INV-10; INV-9 is ``test_migration_v17.py`` beside this file, and INV-11 is the
batch suite's ``test_INV10_already_imported_is_recomputed_both_ways``.

The wizard legs drive a real ``ImportWizardWidget`` under ``qtbot``; the batch
legs walk ``BatchImportService`` the way the batch suite's headless drivers do.
Every file is synthetic: CSV and OFX built in the body, and a locked PDF made
in-test from the PDF suite's committed ``single_table.pdf`` (testing.md § 6).
"""

from __future__ import annotations

import hashlib
import io
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pikepdf
import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from conftest import _PW, _acct, wait_for_pdf_read
from finbreak.datetime_format import format_date, format_timestamp
from finbreak.models import AccountType, ColumnMapping
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService, DateTimePrefs
from finbreak.services.batch_import import BatchImportService
from finbreak.services.import_ import ImportService
from finbreak.services.statements import StatementService
from finbreak.ui import import_wizard
from finbreak.ui.import_wizard import _STEP_PICK, _STEP_PREVIEW, ImportWizardWidget

pytestmark = pytest.mark.features

_HEADER = ["Date", "Details", "Amount"]
_MAPPING = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)
_PDF_HEADER = ["Date", "Description", "Money Out", "Money In"]
_PDF_MAPPING = ColumnMapping(
    "Date", "Description", None, "Money Out", "Money In", "%d/%m/%Y", False
)
_PDF_PASSWORD = "secret"
_SINGLE_TABLE_PDF = (
    Path(__file__).parents[1] / "pdf_import" / "fixtures" / "single_table.pdf"
)

_OFX_HEADER = (
    "OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
    "ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\n"
    "NEWFILEUID:NONE\r\n\r\n"
)

_ROWS = [
    ("2026-01-03", "Corner shop", "-12.50"),
    ("2026-01-09", "Bakery", "-4.20"),
    ("2026-01-20", "Salary", "1500.00"),
]


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    # Saved profiles let a pick of either layout go straight to the preview.
    imports = ImportService(svc.vault)
    imports.save_profile("csv layout", _HEADER, _MAPPING)
    imports.save_profile("pdf layout", _PDF_HEADER, _PDF_MAPPING)
    yield svc
    svc.lock()


# -- synthetic files ---------------------------------------------------------- #


def _csv_bytes(rows, *, newline: str = "\n") -> bytes:
    """A statement CSV with a UTF-8 BOM. The BOM is the point: decoding as
    ``utf-8-sig`` drops it, so a hash of the decoded text differs from a hash
    of the file (INV-1)."""
    lines = [",".join(_HEADER)] + [",".join(row) for row in rows]
    return b"\xef\xbb\xbf" + (newline.join(lines) + newline).encode("utf-8")


def _ofx_txn(dtposted: str, trnamt: str, name: str, fitid: str) -> str:
    return (
        "<STMTTRN>\n<TRNTYPE>DEBIT\n"
        f"<DTPOSTED>{dtposted}\n<TRNAMT>{trnamt}\n<NAME>{name}\n<FITID>{fitid}\n"
        "</STMTTRN>\n"
    )


def _ofx_stmt(txns: str, acctid: str, start: str, end: str) -> str:
    return (
        "<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
        f"<STMTRS><CURDEF>ZAR<BANKACCTFROM><BANKID>250655<ACCTID>{acctid}"
        "<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
        f"<BANKTRANLIST><DTSTART>{start}\n<DTEND>{end}\n{txns}</BANKTRANLIST>\n"
        f"<LEDGERBAL><BALAMT>0.00<DTASOF>{end}</LEDGERBAL>\n"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1>"
    )


def _ofx_bytes(*statements: str) -> bytes:
    return (_OFX_HEADER + "<OFX>\n" + "\n".join(statements) + "\n</OFX>\n").encode()


_OFX_JAN = _ofx_stmt(
    _ofx_txn("20260105", "-10.00", "shop one", "F1"), "000111222", "20260101", "20260131"
)
_OFX_FEB = _ofx_stmt(
    _ofx_txn("20260206", "-20.00", "shop two", "F2"), "000333444", "20260201", "20260228"
)


def _locked_pdf_bytes() -> bytes:
    """``single_table.pdf`` behind a user password, so opening it would prompt."""
    out = io.BytesIO()
    with pikepdf.open(io.BytesIO(_SINGLE_TABLE_PDF.read_bytes())) as pdf:
        pdf.save(
            out,
            encryption=pikepdf.Encryption(owner="owner-pw", user=_PDF_PASSWORD, R=6),
        )
    return out.getvalue()


def _write(directory: Path, name: str, data: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# -- vault reads -------------------------------------------------------------- #


def _fingerprints(svc: AuthService) -> list[tuple[int, str]]:
    return svc.vault.connection.execute(
        "SELECT statement_period_id, file_sha256 FROM imported_files ORDER BY id"
    ).fetchall()


def _shas(svc: AuthService) -> set[str]:
    return {sha for _period, sha in _fingerprints(svc)}


def _txn_count(svc: AuthService) -> int:
    return svc.vault.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[
        0
    ]


# -- wizard drivers ----------------------------------------------------------- #


def _wizard(qtbot, svc, acct: int, prefs: DateTimePrefs | None = None):
    widget = ImportWizardWidget(svc, datetime_prefs=prefs)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    return widget


def _question(widget) -> QMessageBox | None:
    """The already-imported question, if the wizard is showing it."""
    for box in widget.findChildren(QMessageBox):
        if box.isVisible():
            return box
    return None


def _click(box: QMessageBox, label: str) -> None:
    for button in box.buttons():
        if button.text() == label:
            button.click()
            return
    raise AssertionError(f"no {label!r} button on the question")


def _patch_password_dialog(monkeypatch, password: str | None) -> list[str]:
    """Replace the wizard's PasswordDialog. ``password`` set: a fake that accepts
    with it. ``None``: a fake that records being built and then cancels.
    Returns the list each construction appends to."""
    built: list[str] = []

    class _Fake(QDialog):
        def __init__(self, account_name, parent=None, retry=False):
            super().__init__(parent)
            built.append(account_name)

        def show(self):
            super().show()
            if password is None:
                self.reject()
            else:
                self.accept()

        def password(self):
            return password or ""

        def remember(self):
            return False

    monkeypatch.setattr(import_wizard, "PasswordDialog", _Fake)
    return built


def _pick(qtbot, widget, path: Path) -> None:
    widget._select_file(str(path))
    wait_for_pdf_read(qtbot, widget)


def _wizard_import(qtbot, svc, acct: int, path: Path) -> None:
    """Pick ``path`` in a fresh wizard and import it, answering Import again if
    the file was imported before."""
    widget = _wizard(qtbot, svc, acct)
    _pick(qtbot, widget, path)
    box = _question(widget)
    if box is not None:
        _click(box, "Import again")
        wait_for_pdf_read(qtbot, widget)
    assert widget._stack.currentIndex() == _STEP_PREVIEW, widget._error.text()
    with qtbot.waitSignal(widget.done, timeout=5_000):
        widget._import_button.click()


# -- batch drivers ------------------------------------------------------------ #


def _batch_import(svc, acct: int, path: Path) -> None:
    batch = BatchImportService(svc.vault)
    files = batch.build([str(path)])
    index = 0
    while index < len(files):
        index = batch.scan_step(files, index)
    for record in files:
        if record.outcome == "needs_account":
            batch.set_account(record, acct)
    batch.review(files)
    index = 0
    while index < len(files):
        index = batch.run_step(files, index)
    assert [f.outcome for f in files] == ["committed"] * len(files), [
        (f.outcome, f.reason) for f in files
    ]


def _service_import(svc, acct: int, path: Path, sha: str | None):
    imports = ImportService(svc.vault)
    text = imports.decode_csv(path.read_bytes())
    preview = imports.preview(text, _MAPPING, acct)
    assert preview.period_start is not None and preview.period_end is not None
    return imports.commit_import(
        preview, preview.period_start, preview.period_end, str(path), sha
    )


# --------------------------------------------------------------------------- #
# INV-1 — the fingerprint is the SHA-256 of the bytes on disk, every format
# --------------------------------------------------------------------------- #
def test_INV1_fingerprint_is_the_raw_file_bytes(
    qtbot, service, tmp_path, monkeypatch
) -> None:
    acct = _acct(service)
    _patch_password_dialog(monkeypatch, _PDF_PASSWORD)

    wizard_files = [
        _write(tmp_path / "wizard", "jan.csv", _csv_bytes(_ROWS)),
        _write(tmp_path / "wizard", "jan.ofx", _ofx_bytes(_OFX_JAN)),
        _write(tmp_path / "wizard", "locked.pdf", _locked_pdf_bytes()),
    ]
    for path in wizard_files:
        _wizard_import(qtbot, service, acct, path)
    for path in wizard_files:
        assert _sha(path) in _shas(service), f"wizard: {path.name}"

    # The batch reads a locked PDF through the stored-password ladder.
    AccountService(service.vault).set_pdf_password(acct, _PDF_PASSWORD)
    other = AccountService(service.vault).add_account(
        "Batch", AccountType.CURRENT.value
    ).id
    batch_files = [
        _write(
            tmp_path / "batch",
            "feb.csv",
            _csv_bytes([("2026-02-03", "Hardware", "-99.00")], newline="\r\n"),
        ),
        # Two statements: the OFX fan-out's extra record carries the hash too.
        _write(tmp_path / "batch", "two.ofx", _ofx_bytes(_OFX_JAN, _OFX_FEB)),
        _write(tmp_path / "batch", "locked.pdf", _locked_pdf_bytes()),
    ]
    for path in batch_files:
        _batch_import(service, other, path)

    rows = _fingerprints(service)
    for path in batch_files:
        assert _sha(path) in _shas(service), f"batch: {path.name}"
    ofx_periods = {period for period, sha in rows if sha == _sha(batch_files[1])}
    assert len(ofx_periods) == 2, "each OFX statement's period records the file"
    # Nothing but raw-byte hashes was recorded.
    expected = {_sha(p) for p in wizard_files + batch_files}
    assert _shas(service) == expected


# --------------------------------------------------------------------------- #
# INV-2 — recorded in the commit's own transaction, reused span included
# --------------------------------------------------------------------------- #
def test_INV2_fingerprint_is_recorded_with_the_commit(
    service, tmp_path, monkeypatch
) -> None:
    acct = _acct(service)
    first = _write(tmp_path, "a.csv", _csv_bytes(_ROWS))
    second = _write(tmp_path, "b.csv", _csv_bytes(_ROWS, newline="\r\n"))
    assert _sha(first) != _sha(second)

    _service_import(service, acct, first, _sha(first))
    reused = _service_import(service, acct, second, _sha(second))
    assert reused.inserted_count == 0 and not reused.period_recorded

    rows = _fingerprints(service)
    assert {sha for _p, sha in rows} == {_sha(first), _sha(second)}
    assert len({period for period, _sha_ in rows}) == 1, "both on the one period"

    # A commit that rolls back records nothing.
    def boom(self, *args, **kwargs):
        raise RuntimeError("injected add_batch failure")

    monkeypatch.setattr(TransactionRepository, "add_batch", boom)
    third = _write(
        tmp_path, "c.csv", _csv_bytes([("2026-03-04", "New row", "-1.00")])
    )
    with pytest.raises(RuntimeError, match="injected"):
        _service_import(service, acct, third, _sha(third))
    assert _sha(third) not in _shas(service)
    assert len(_fingerprints(service)) == 2


# --------------------------------------------------------------------------- #
# INV-3 — both production callers record it
# --------------------------------------------------------------------------- #
def test_INV3_wizard_and_batch_both_record_the_fingerprint(
    qtbot, service, tmp_path
) -> None:
    acct = _acct(service)
    by_wizard = _write(tmp_path, "w.csv", _csv_bytes(_ROWS))
    by_batch = _write(
        tmp_path, "b.csv", _csv_bytes([("2026-04-01", "Rates", "-300.00")])
    )

    _wizard_import(qtbot, service, acct, by_wizard)
    _batch_import(service, acct, by_batch)

    assert _shas(service) == {_sha(by_wizard), _sha(by_batch)}


# --------------------------------------------------------------------------- #
# INV-4 — deleting the statement forgets the file
# --------------------------------------------------------------------------- #
def test_INV4_deleting_the_statement_forgets_the_file(service, tmp_path) -> None:
    acct = _acct(service)
    path = _write(tmp_path, "a.csv", _csv_bytes(_ROWS))
    sha = _sha(path)
    imports = ImportService(service.vault)
    _service_import(service, acct, path, sha)
    assert imports.prior_import(sha) is not None

    (period_id,) = {period for period, _s in _fingerprints(service)}
    StatementService(service.vault).delete_statements([period_id])

    assert imports.prior_import(sha) is None
    assert _fingerprints(service) == []


# --------------------------------------------------------------------------- #
# INV-5 — the question comes first; Cancel changes nothing
# --------------------------------------------------------------------------- #
def test_INV5_question_comes_first_and_cancel_changes_nothing(
    qtbot, service, tmp_path, monkeypatch
) -> None:
    acct = _acct(service)
    path = _write(tmp_path, "locked.pdf", _locked_pdf_bytes())
    _patch_password_dialog(monkeypatch, _PDF_PASSWORD)
    _wizard_import(qtbot, service, acct, path)
    before = (_txn_count(service), _fingerprints(service))

    prompts = _patch_password_dialog(monkeypatch, None)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    box = _question(widget)

    assert box is not None, "no already-imported question"
    assert prompts == [], "the password was asked for before the question"
    assert widget._pdf_worker is None, "the PDF was read before the question"
    _click(box, "Cancel")
    wait_for_pdf_read(qtbot, widget)

    assert prompts == []
    assert widget._preview is None
    assert widget._stack.currentIndex() == _STEP_PICK
    assert (_txn_count(service), _fingerprints(service)) == before


# --------------------------------------------------------------------------- #
# INV-6 — Import again behaves exactly as a first pick
# --------------------------------------------------------------------------- #
def test_INV6_import_again_dedups_as_before(
    qtbot, service, tmp_path, monkeypatch
) -> None:
    acct = _acct(service)
    path = _write(tmp_path, "a.csv", _csv_bytes(_ROWS))
    _wizard_import(qtbot, service, acct, path)
    rows_before = _txn_count(service)

    results = []
    real_commit = ImportService.commit_import

    def spy(self, *args, **kwargs):
        result = real_commit(self, *args, **kwargs)
        results.append(result)
        return result

    monkeypatch.setattr(ImportService, "commit_import", spy)
    widget = _wizard(qtbot, service, acct)
    _pick(qtbot, widget, path)
    box = _question(widget)
    assert box is not None, "no already-imported question"
    _click(box, "Import again")

    assert widget._stack.currentIndex() == _STEP_PREVIEW
    assert widget._preview is not None
    assert widget._preview.new_count == 0
    assert widget._preview.duplicate_count == len(_ROWS)
    with qtbot.waitSignal(widget.done, timeout=5_000):
        widget._import_button.click()
    assert [r.inserted_count for r in results] == [0]
    assert _txn_count(service) == rows_before


# --------------------------------------------------------------------------- #
# INV-7 — the match is on content, never the name
# --------------------------------------------------------------------------- #
def test_INV7_same_name_different_content_is_not_warned(
    qtbot, service, tmp_path
) -> None:
    acct = _acct(service)
    original = _write(tmp_path / "one", "statement.csv", _csv_bytes(_ROWS))
    _wizard_import(qtbot, service, acct, original)

    same_name = _write(
        tmp_path / "two",
        "statement.csv",
        _csv_bytes([("2026-05-02", "Garage", "-80.00")]),
    )
    widget = _wizard(qtbot, service, acct)
    _pick(qtbot, widget, same_name)
    assert _question(widget) is None, "a different file was taken for the old one"
    assert widget._stack.currentIndex() == _STEP_PREVIEW

    # The control: the old content under a new name IS recognised.
    renamed = _write(tmp_path / "three", "renamed.csv", original.read_bytes())
    widget = _wizard(qtbot, service, acct)
    _pick(qtbot, widget, renamed)
    assert _question(widget) is not None, "a renamed copy was not recognised"


# --------------------------------------------------------------------------- #
# INV-8 — the question names the latest import, in the user's formats
# --------------------------------------------------------------------------- #
def test_INV8_question_names_the_latest_import(
    qtbot, service, tmp_path, monkeypatch
) -> None:
    accounts = AccountService(service.vault)
    alpha = accounts.add_account("Alpha cheque", AccountType.CURRENT.value).id
    bravo = accounts.add_account("Bravo savings", AccountType.SAVINGS.value).id
    path = _write(tmp_path, "a.csv", _csv_bytes(_ROWS))
    sha = _sha(path)

    stamps = iter(
        [
            datetime(2026, 2, 1, 8, 0, tzinfo=UTC),
            datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            datetime(2026, 4, 1, 10, 30, tzinfo=UTC),
        ]
    )

    class _Clock:
        @staticmethod
        def now(tz=None):
            return next(stamps)

    monkeypatch.setattr("finbreak.repositories.imported_files.datetime", _Clock)
    for acct in (alpha, bravo, alpha):
        _service_import(service, acct, path, sha)

    prefs = DateTimePrefs("UTC", "dd MMMM yyyy", "HH:mm")
    widget = _wizard(qtbot, service, alpha, prefs)
    _pick(qtbot, widget, path)
    box = _question(widget)
    assert box is not None, "no already-imported question"
    text = box.text()

    third = "2026-04-01T10:30:00+00:00"
    assert "Alpha cheque" in text and "Bravo savings" not in text, text
    assert format_timestamp(third, "UTC", "dd MMMM yyyy", "HH:mm") in text, text
    assert format_date("2026-01-03", "dd MMMM yyyy") in text, text
    assert format_date("2026-01-20", "dd MMMM yyyy") in text, text
    assert "2026-01-03" not in text, "an ISO date reached the question"


# --------------------------------------------------------------------------- #
# INV-10 — no fingerprint reaches the log
# --------------------------------------------------------------------------- #
def test_INV10_fingerprint_is_never_logged(qtbot, service, tmp_path, caplog) -> None:
    acct = _acct(service)
    path = _write(tmp_path, "a.csv", _csv_bytes(_ROWS))
    sha = _sha(path)
    caplog.set_level(logging.DEBUG)

    _wizard_import(qtbot, service, acct, path)
    widget = _wizard(qtbot, service, acct)
    _pick(qtbot, widget, path)
    assert _question(widget) is not None

    assert caplog.records, "nothing was logged, so nothing was checked"
    for record in caplog.records:
        assert sha not in record.getMessage(), record.name
