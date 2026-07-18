"""FIBR-0008 — P06 OFX import. Enforces tests/features/ofx_import/spec.md.

The pure `OfxImporter` (OFX bytes -> a `ParseResult` per statement, reusing
`parse_transaction`), the `ImportService` reuse seam (`_preview_from_result` /
`preview_result` / `read_file_bytes`), the shared `importers/base.py` value
objects, and the wizard's OFX branch. Headless layers tested directly; the
wizard round-trips (INV-7) use the pytest-qt `qtbot` fixture. Every on-disk
vault uses `tmp_path`; OFX fixtures are tiny in-repo SGML strings — no real
financial data, no network (testing.md § 6). No migration this phase (the
first-run vault is already at v4, D9).
"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from conftest import _PW, _acct
from finbreak.importers.base import ParseResult
from finbreak.importers.ofx_importer import (
    _MAX_OFX_TRANSACTIONS,
    OfxImporter,
)
from finbreak.models import OfxAccountInfo
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService
from finbreak.services.transactions import read_minor_unit_exponent

pytestmark = pytest.mark.features

_OFX_HEADER = (
    "OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
    "ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\n"
    "NEWFILEUID:NONE\r\n\r\n"
)


def _txn(dtposted, trnamt, name=None, memo=None, fitid="X1", trntype="DEBIT"):
    """One <STMTTRN>. A None name/memo omits the tag entirely (absent, not
    empty) — both yield payee/memo == '' in natural per-line SGML (D5/D15)."""
    parts = [f"<TRNTYPE>{trntype}\n", f"<DTPOSTED>{dtposted}\n", f"<TRNAMT>{trnamt}\n"]
    if name is not None:
        parts.append(f"<NAME>{name}\n")
    if memo is not None:
        parts.append(f"<MEMO>{memo}\n")
    parts.append(f"<FITID>{fitid}\n")
    return "<STMTTRN>\n" + "".join(parts) + "</STMTTRN>\n"


def _stmt(
    txns,
    start="20260101",
    end="20260131",
    acctid="000123456",
    acct_type="CHECKING",
    curdef="ZAR",
):
    """A bank <STMTRS>. An empty `start` omits the embedded span (D4)."""
    span = f"<DTSTART>{start}\n<DTEND>{end}\n" if start else ""
    body = "".join(txns)
    return (
        "<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
        f"<STMTRS><CURDEF>{curdef}<BANKACCTFROM><BANKID>250655<ACCTID>{acctid}"
        f"<ACCTTYPE>{acct_type}</BANKACCTFROM>\n"
        f"<BANKTRANLIST>{span}{body}</BANKTRANLIST>\n"
        f"<LEDGERBAL><BALAMT>0.00<DTASOF>{end}</LEDGERBAL>\n"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1>"
    )


def _ccstmt(txns, start="20260101", end="20260131", acctid="CC999", curdef="ZAR"):
    """A credit-card <CCSTMTRS> — parses with an empty account_type (D8)."""
    span = f"<DTSTART>{start}\n<DTEND>{end}\n" if start else ""
    body = "".join(txns)
    return (
        "<CREDITCARDMSGSRSV1><CCSTMTTRNRS><TRNUID>2<STATUS><CODE>0"
        "<SEVERITY>INFO</STATUS>\n"
        f"<CCSTMTRS><CURDEF>{curdef}<CCACCTFROM><ACCTID>{acctid}</CCACCTFROM>\n"
        f"<BANKTRANLIST>{span}{body}</BANKTRANLIST>\n"
        f"<LEDGERBAL><BALAMT>0.00<DTASOF>{end}</LEDGERBAL>\n"
        "</CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1>"
    )


def _ofx(*statements) -> bytes:
    """Wrap one or more statement bodies into a full OFX document (bytes)."""
    return (_OFX_HEADER + "<OFX>\n" + "\n".join(statements) + "\n</OFX>\n").encode()


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to latest
    yield svc
    svc.lock()


def _exp(service: AuthService) -> int:
    return read_minor_unit_exponent(service.vault.connection)


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# --------------------------------------------------------------------------- #
# INV-1 — OFX parsing to transaction drafts
# --------------------------------------------------------------------------- #
def test_INV1_parse_returns_one_result_per_statement_with_drafts(service):
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="Coffee Shop", fitid="a1"),
                _txn(
                    "20260120", "1000.00", name="Salary", fitid="a2", trntype="CREDIT"
                ),
            ]
        )
    )
    results = OfxImporter().parse(data, _exp(service))
    assert len(results) == 1
    info, result = results[0]
    assert isinstance(info, OfxAccountInfo)
    assert info.account_id == "000123456" and info.account_type == "CHECKING"
    assert isinstance(result, ParseResult)
    assert [d.row_number for d in result.drafts] == [1, 2]


def test_INV1a_signed_amount_passthrough(service):
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="Coffee", fitid="a1"),
                _txn(
                    "20260120", "1000.00", name="Salary", fitid="a2", trntype="CREDIT"
                ),
            ]
        )
    )
    _, result = OfxImporter().parse(data, _exp(service))[0]
    # Sign is the TRNAMT field verbatim (exp 2): -10.00 -> -1000, 1000.00 -> 100000.
    assert result.drafts[0].amount_minor == -1000
    assert result.drafts[1].amount_minor == 100000


def test_INV1a_sign_is_trnamt_not_trntype(service):
    # A DEBIT token with a POSITIVE TRNAMT stays positive — ofxparse never inverts.
    data = _ofx(
        _stmt([_txn("20260105", "10.00", name="Odd", fitid="a1", trntype="DEBIT")])
    )
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.drafts[0].amount_minor == 1000


def test_INV1b_date_maps_from_dtposted(service):
    data = _ofx(_stmt([_txn("20260105", "-10.00", name="Coffee", fitid="a1")]))
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.drafts[0].occurred_on == "2026-01-05"


def test_INV1c_description_is_payee_else_memo(service):
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="Coffee Shop", fitid="a1"),
                _txn(
                    "20260107", "-5.00", memo="ATM", fitid="a2"
                ),  # NAME absent -> memo
            ]
        )
    )
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.drafts[0].description == "Coffee Shop"
    assert result.drafts[1].description == "ATM"


def test_INV1d_over_precise_amount_is_a_rowerror_not_rounded(service):
    # Exponent 2, but the amount has 3 fractional digits -> parse_transaction rejects
    # it (never silently rounds). Post-parse rejection -> collected RowError (INV-3).
    data = _ofx(_stmt([_txn("20260105", "-10.123", name="Coffee", fitid="a1")]))
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.drafts == []
    assert len(result.errors) == 1 and result.errors[0].row_number == 1


# --------------------------------------------------------------------------- #
# INV-2 — coverage period is the embedded span
# --------------------------------------------------------------------------- #
def test_INV2_period_is_embedded_span_not_draft_minmax(service):
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="A", fitid="a1"),
                _txn("20260120", "20.00", name="B", fitid="a2", trntype="CREDIT"),
            ],
            start="20260101",
            end="20260131",
        )
    )
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.period_start == "2026-01-01" and result.period_end == "2026-01-31"


def test_INV2_missing_span_falls_back_to_draft_minmax(service):
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="A", fitid="a1"),
                _txn("20260120", "20.00", name="B", fitid="a2", trntype="CREDIT"),
            ],
            start="",  # no DTSTART/DTEND -> ofxparse yields '' -> falsiness fallback
        )
    )
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.period_start == "2026-01-05" and result.period_end == "2026-01-20"


def test_INV2_missing_span_and_zero_drafts_is_none(service):
    data = _ofx(_stmt([], start=""))
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.period_start is None and result.period_end is None


# --------------------------------------------------------------------------- #
# INV-3 — post-parse per-row errors collected, valid rows still import
# --------------------------------------------------------------------------- #
def test_INV3_post_parse_errors_collected_valid_rows_import(service):
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="Valid", fitid="c1"),
                _txn("20260106", "0.00", name="Zero", fitid="c2"),  # zero amount
                _txn("20260107", "-3.00", fitid="c3"),  # NAME+MEMO absent
            ]
        )
    )
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert [d.description for d in result.drafts] == ["Valid"]
    assert [e.row_number for e in result.errors] == [2, 3]


# --------------------------------------------------------------------------- #
# INV-4 — malformed / statement-less / bad-transaction -> one friendly ValueError
# --------------------------------------------------------------------------- #
def test_INV4_bad_transaction_aborts_whole_statement(service):
    # A structurally-malformed transaction (bad DTPOSTED) makes ofxparse abort the
    # WHOLE statement mid-parse (D15) -> a single friendly ValueError, not a
    # RowError. The fixture pairs the bad row with a VALID sibling: a per-row-
    # tolerant importer would return the good draft, so raising (rather than
    # yielding the valid row) is what proves the good sibling is lost too (D15).
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="Valid", fitid="d0"),
                _txn("notadate", "-1.00", name="X", fitid="d1"),
            ]
        )
    )
    with pytest.raises(ValueError):
        OfxImporter().parse(data, _exp(service))


@pytest.mark.parametrize("data", [b"", b"<html><body>no</body></html>", b"not ofx"])
def test_INV4_malformed_input_raises_value_error(service, data):
    with pytest.raises(ValueError):
        OfxImporter().parse(data, _exp(service))


def test_INV4_statement_less_envelope_raises_value_error(service):
    data = (
        _OFX_HEADER + "<OFX><SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO"
        "</STATUS><DTSERVER>20260101</SONRS></SIGNONMSGSRSV1></OFX>"
    ).encode()
    with pytest.raises(ValueError):
        OfxImporter().parse(data, _exp(service))


# --------------------------------------------------------------------------- #
# INV-5 — multi-account OFX surfaces all statements
# --------------------------------------------------------------------------- #
def test_INV5_multi_account_surfaces_all_statements(service):
    data = _ofx(
        _stmt(
            [_txn("20260105", "-10.00", name="Shop", fitid="e1")],
            acctid="BANK111",
            acct_type="SAVINGS",
        ),
        _ccstmt([_txn("20260106", "-25.00", name="Fuel", fitid="e2")], acctid="CC999"),
    )
    results = OfxImporter().parse(data, _exp(service))
    assert len(results) == 2
    ids = {info.account_id: info.account_type for info, _ in results}
    assert ids == {"BANK111": "SAVINGS", "CC999": ""}
    # Neither statement's rows are dropped.
    assert all(len(r.drafts) == 1 for _, r in results)


# --------------------------------------------------------------------------- #
# INV-6 — OFX feeds the same write pipeline (dedup + period + atomic)
# --------------------------------------------------------------------------- #
def test_INV6_preview_result_feeds_pipeline_and_reimport_adds_zero(service):
    acct, conn = _acct(service), service.vault.connection
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="Coffee", fitid="f1"),
                _txn(
                    "20260120", "1000.00", name="Salary", fitid="f2", trntype="CREDIT"
                ),
            ]
        )
    )
    imp = ImportService(service.vault)
    _, result = OfxImporter().parse(data, _exp(service))[0]

    preview = imp.preview_result(result, acct)
    assert preview.new_count == 2
    imp.commit_import(preview, preview.period_start, preview.period_end, "stmt.ofx")
    assert TransactionRepository(conn).count_for_account(acct) == 2
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1

    # Re-import the same statement -> zero new rows, no second period row.
    _, result2 = OfxImporter().parse(data, _exp(service))[0]
    preview2 = imp.preview_result(result2, acct)
    assert preview2.new_count == 0
    imp.commit_import(preview2, preview2.period_start, preview2.period_end, "stmt.ofx")
    assert TransactionRepository(conn).count_for_account(acct) == 2
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1


def test_INV6_ofx_dedups_against_a_manual_transaction(service):
    acct = _acct(service)
    TransactionService = __import__(
        "finbreak.services.transactions", fromlist=["TransactionService"]
    ).TransactionService
    TransactionService(service.vault).add_transaction(
        acct, "2026-01-05", "-10.00", "Coffee"
    )
    data = _ofx(_stmt([_txn("20260105", "-10.00", name="Coffee", fitid="g1")]))
    imp = ImportService(service.vault)
    _, result = OfxImporter().parse(data, _exp(service))[0]
    preview = imp.preview_result(result, acct)
    assert preview.new_count == 0, "content-identical to the manual row -> deduped"


# --------------------------------------------------------------------------- #
# INV-7 — import-wizard OFX round-trip (qtbot)
# --------------------------------------------------------------------------- #
def _wizard(qtbot, service, acct):
    from finbreak.ui.import_wizard import ImportWizardWidget

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    return widget


def test_INV7a_ofx_pick_skips_mapping_lands_on_preview(qtbot, service, tmp_path):
    acct = _acct(service)
    path = _write(
        tmp_path,
        "stmt.ofx",
        _ofx(_stmt([_txn("20260105", "-10.00", name="Coffee", fitid="a1")])),
    )
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 2, "OFX -> preview (mapping skipped)"
    assert widget._preview_table.rowCount() == 1


def test_INV7b_preview_renders_decimal_amount_and_period(qtbot, service, tmp_path):
    acct = _acct(service)
    path = _write(
        tmp_path,
        "stmt.ofx",
        _ofx(
            _stmt(
                [_txn("20260105", "-10.00", name="Coffee", fitid="a1")],
                start="20260101",
                end="20260131",
            )
        ),
    )
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._preview_table.item(0, 2).text() == "-10.00", "decimal, not -1000"
    assert widget._summary_label.text() != ""
    assert widget._period_start.date().toString(Qt.DateFormat.ISODate) == "2026-01-01"
    assert widget._period_end.date().toString(Qt.DateFormat.ISODate) == "2026-01-31"


def test_INV7c_import_inserts_rows_and_records_period(qtbot, service, tmp_path):
    acct, conn = _acct(service), service.vault.connection
    path = _write(
        tmp_path,
        "stmt.ofx",
        _ofx(
            _stmt(
                [
                    _txn("20260105", "-10.00", name="Coffee", fitid="a1"),
                    _txn(
                        "20260120",
                        "1000.00",
                        name="Salary",
                        fitid="a2",
                        trntype="CREDIT",
                    ),
                ]
            )
        ),
    )
    widget = _wizard(qtbot, service, acct)
    returned: list[bool] = []
    widget.done.connect(lambda: returned.append(True))
    widget._select_file(str(path))
    assert widget._import_button.isEnabled()
    widget._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 2
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1
    assert returned == [True]


def test_INV7d_second_import_is_all_duplicate(qtbot, service, tmp_path):
    acct, conn = _acct(service), service.vault.connection
    path = _write(
        tmp_path,
        "stmt.ofx",
        _ofx(_stmt([_txn("20260105", "-10.00", name="Coffee", fitid="a1")])),
    )
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    widget._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 1

    widget2 = _wizard(qtbot, service, acct)
    widget2._select_file(str(path))
    assert widget2._preview.new_count == 0
    assert widget2._import_button.isEnabled(), "all-duplicate stays enabled"
    widget2._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 1, "no new rows"


def test_INV7e_multi_account_chooser(qtbot, service, tmp_path):
    acct, conn = _acct(service), service.vault.connection
    data = _ofx(
        _stmt(
            [_txn("20260105", "-10.00", name="Shop", fitid="e1")],
            acctid="BANK111",
            acct_type="SAVINGS",
        ),
        _ccstmt([_txn("20260106", "-25.00", name="Fuel", fitid="e2")], acctid="CC999"),
    )
    path = _write(tmp_path, "multi.ofx", data)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._ofx_statement_combo.count() == 2
    assert not widget._ofx_statement_combo.isHidden(), "chooser shown for >1 account"
    # Default previews statement 0 (the bank SAVINGS "Shop").
    assert widget._preview_table.item(0, 3).text() == "Shop"
    # Selecting the second entry re-previews the credit-card statement.
    widget._ofx_statement_combo.setCurrentIndex(1)
    assert widget._preview_table.item(0, 3).text() == "Fuel"
    widget._import_button.click()
    # Exactly the CHOSEN statement's row lands — assert its identity, not just
    # the count (a wrong-statement off-by-one would still yield count 1).
    rows = TransactionRepository(conn).list_all()
    assert [(r.description, r.amount_minor) for r in rows] == [("Fuel", -2500)]


def test_INV7e_single_statement_hides_chooser(qtbot, service, tmp_path):
    acct = _acct(service)
    path = _write(
        tmp_path,
        "stmt.ofx",
        _ofx(_stmt([_txn("20260105", "-10.00", name="Coffee", fitid="a1")])),
    )
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._ofx_statement_combo.isHidden(), "single statement -> chooser hidden"


def test_INV7_content_sniff_routes_misnamed_ofx(qtbot, service, tmp_path):
    # A mis-named OFX file (no .ofx/.qfx extension) is still detected by the
    # bounded 512-byte content sniff (D10) and takes the OFX path — the mapping
    # step is skipped. Exercises _looks_like_ofx's non-extension branch.
    acct = _acct(service)
    path = _write(
        tmp_path,
        "statement.txt",
        _ofx(_stmt([_txn("20260105", "-10.00", name="Coffee", fitid="a1")])),
    )
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 2, "sniffed OFX -> preview (mapping skipped)"
    assert widget._preview_table.rowCount() == 1


def test_INV7f_quiet_month_records_period(qtbot, service, tmp_path):
    acct, conn = _acct(service), service.vault.connection
    path = _write(
        tmp_path, "quiet.ofx", _ofx(_stmt([], start="20260201", end="20260228"))
    )  # embedded span, zero txns
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._preview_table.rowCount() == 0
    assert widget._period_start.date().toString(Qt.DateFormat.ISODate) == "2026-02-01"
    assert widget._import_button.isEnabled(), "quiet month stays enabled (D14)"
    widget._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 0
    periods = StatementPeriodRepository(conn).list_for_account(acct)
    assert len(periods) == 1 and periods[0].period_start == "2026-02-01"


# --------------------------------------------------------------------------- #
# INV-8 — no secret / network / schema regression; input treated as data
# --------------------------------------------------------------------------- #
def test_INV8_no_schema_change(service):
    from finbreak.migrations import LATEST_SCHEMA_VERSION

    # OFX itself added no migration (D9); later phases added v5 (FIBR-0009),
    # v6 (FIBR-0052), v7 (FIBR-0010) and v8 (FIBR-0011), so this can no longer
    # prove "OFX added nothing" — it now asserts a first-run vault lands at the
    # latest schema (currently 9).
    assert LATEST_SCHEMA_VERSION == 10
    version = service.vault.connection.execute(
        "SELECT version FROM schema_version"
    ).fetchone()[0]
    assert version == 10


def test_INV8_no_network_import_in_ofx_module():
    src = Path("src/finbreak/importers/ofx_importer.py").read_text()
    for banned in ("import socket", "import http", "urllib", "requests", "ftplib"):
        assert banned not in src, f"no network surface in the importer ({banned})"


def test_INV8_formula_and_path_fields_stored_inert(service, caplog):
    acct, conn = _acct(service), service.vault.connection
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="=cmd|'/c calc'!A1", fitid="h1"),
                _txn("20260106", "-20.00", name="../../etc/passwd", fitid="h2"),
            ]
        )
    )
    imp = ImportService(service.vault)
    with caplog.at_level(logging.DEBUG):
        _, result = OfxImporter().parse(data, _exp(service))[0]
        preview = imp.preview_result(result, acct)
        imp.commit_import(preview, preview.period_start, preview.period_end, "x.ofx")
    stored = {
        r[0] for r in conn.execute("SELECT description FROM transactions").fetchall()
    }
    assert stored == {"=cmd|'/c calc'!A1", "../../etc/passwd"}, "stored verbatim, inert"
    assert _PW.decode() not in caplog.text


# --------------------------------------------------------------------------- #
# FIBR-0042 — a timezone-bearing DTPOSTED/DTEND keeps its AS-POSTED LOCAL date
# --------------------------------------------------------------------------- #
# ofxparse 0.21 normalises a timestamped `<DTPOSTED>YYYYMMDDHHMMSS[offset:tz]` to
# UTC (`local - offset`), which rolls an evening transaction in a negative-offset
# zone to the NEXT calendar day (and can push a month-boundary DTEND into the next
# month, mis-filing the statement period). finbreak files a row under the day the
# bank printed, so `_LocalDateOfxParser` neutralises the offset. The roadmap's
# verified reproducer is `20260105230000[-5:EST]` -> the wrong "2026-01-06".
def test_INV11_dtposted_keeps_asposted_local_date_negative_offset(service):
    # Evening in EST (UTC-5): buggy UTC normalisation would roll to 2026-01-06.
    data = _ofx(_stmt([_txn("20260105230000[-5:EST]", "-10.00", name="C", fitid="z1")]))
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.drafts[0].occurred_on == "2026-01-05"


def test_INV11a_dtend_span_keeps_asposted_local_date_at_month_boundary(service):
    # A tz-bearing DTEND on the last night of the month: UTC normalisation would
    # roll it to 2026-02-01 and wrongly extend the period into February.
    data = _ofx(
        _stmt(
            [_txn("20260115", "-10.00", name="C", fitid="z2")],
            start="20260101",
            end="20260131235959[-5:EST]",
        )
    )
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.period_start == "2026-01-01" and result.period_end == "2026-01-31"


def test_INV11b_dtposted_keeps_local_date_positive_offset(service):
    # Early morning in a positive-offset zone: UTC normalisation would roll it
    # BACKWARD to 2026-01-04 — the fix must hold in both directions.
    data = _ofx(_stmt([_txn("20260105010000[+5:PKT]", "-10.00", name="C", fitid="z3")]))
    _, result = OfxImporter().parse(data, _exp(service))[0]
    assert result.drafts[0].occurred_on == "2026-01-05"


# --------------------------------------------------------------------------- #
# INV-9 — CSV import contracts preserved (relocation didn't fork)
# --------------------------------------------------------------------------- #
def test_INV9_parseresult_rowerror_shared_from_base_and_csv():
    from finbreak.importers import base, csv_importer

    # Both import sites resolve to the SAME class object (a re-export, not a fork).
    assert base.ParseResult is csv_importer.ParseResult
    assert base.RowError is csv_importer.RowError


# --------------------------------------------------------------------------- #
# INV-10 — OFX is resource-bounded (D13)
# --------------------------------------------------------------------------- #
def test_INV10_oversized_file_refused_before_read(service, tmp_path, monkeypatch):
    import finbreak.services.import_ as import_mod

    path = _write(tmp_path, "big.ofx", b"x" * 5000)
    monkeypatch.setattr(import_mod, "_MAX_IMPORT_BYTES", 1000)
    with pytest.raises(ValueError):
        ImportService(service.vault).read_file_bytes(str(path))


def test_INV10_read_file_bytes_returns_bytes_under_cap(service, tmp_path):
    path = _write(tmp_path, "ok.ofx", b"hello")
    assert ImportService(service.vault).read_file_bytes(str(path)) == b"hello"


def test_INV10_too_many_transactions_refused(service, monkeypatch):
    import finbreak.importers.ofx_importer as ofx_mod

    monkeypatch.setattr(ofx_mod, "_MAX_OFX_TRANSACTIONS", 1)
    data = _ofx(
        _stmt(
            [
                _txn("20260105", "-10.00", name="A", fitid="i1"),
                _txn("20260106", "-20.00", name="B", fitid="i2"),
            ]
        )
    )
    with pytest.raises(ValueError):
        OfxImporter().parse(data, _exp(service))
    assert _MAX_OFX_TRANSACTIONS == 100_000, "the real cap constant is exported"


def test_investment_statement_refused_not_crashed(service):
    """An OFX investment/brokerage statement fails with a friendly ValueError,
    not an unhandled AttributeError — InvestmentTransaction has no .payee/.date/
    .amount, and investment import is out of scope. (indie-review H-C)"""
    inv = (
        _OFX_HEADER + "<OFX><INVSTMTMSGSRSV1><INVSTMTTRNRS><INVSTMTRS>"
        "<DTASOF>20260101<CURDEF>USD"
        "<INVACCTFROM><BROKERID>x<ACCTID>123</INVACCTFROM>"
        "<INVTRANLIST><DTSTART>20260101<DTEND>20260131"
        "<BUYSTOCK><INVBUY><INVTRAN><FITID>1<DTTRADE>20260115</INVTRAN>"
        "<SECID><UNIQUEID>us1<UNIQUEIDTYPE>CUSIP</SECID>"
        "<UNITS>10<UNITPRICE>5<TOTAL>-50</INVBUY><BUYTYPE>BUY</BUYSTOCK>"
        "</INVTRANLIST></INVSTMTRS></INVSTMTTRNRS></INVSTMTMSGSRSV1></OFX>"
    ).encode()
    with pytest.raises(ValueError):
        OfxImporter().parse(inv, _exp(service))
