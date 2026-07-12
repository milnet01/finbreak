"""FIBR-0003 INV-1 — self-test that loads the bundled native stacks.

Each ``_check_*`` imports its native dependency **lazily** (inside the
function), so this module imports cleanly even when a dep is missing and so a
test can monkeypatch a check. ``run_self_test`` runs them in order and prints
exactly one sentinel line — ``FINBREAK_SELFTEST_OK`` on success, or
``FINBREAK_SELFTEST_FAIL: <stack>`` on the first failing stack.

The whole point is to prove — inside a Python-free bundle — that every native
stack travels with the artifact: Qt, QtCharts (``Qt6Charts``, the dashboard's
donut + trend, FIBR-0012), the SQLCipher native library, and qpdf
(behind ``pikepdf``, FIBR-0003), Argon2 (FIBR-0004), ofxparse's transitive tree
incl. native lxml (FIBR-0008), and pdfplumber's native tree — Pillow, PDFium
(``pypdfium2``/``pypdfium2_raw``), cryptography (FIBR-0009). See
docs/specs/FIBR-0003.md.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import TextIO

# A fixed, obviously-fake passphrase used only to prove SQLCipher's native
# encryption path loads. Not a real key and not a secret (FIBR-0003 /
# security-model.md INV-6): it derives nothing and guards no real data. Kept as
# a whole-statement literal so there is no string-building for a scanner to
# read as SQL injection.
_SMOKE_KEY_PRAGMA = "PRAGMA key = 'finbreak-smoke-test-not-a-real-key'"


def _check_qt() -> None:
    """Construct a headless QApplication (offscreen), proving Qt loads."""
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication([])


def _check_qtcharts() -> None:
    """Import ``PySide6.QtCharts`` and construct a series object, proving the
    ``Qt6Charts`` native library travels into the frozen bundle (FIBR-0012 D12 /
    INV-11). The dashboard's donut + trend are QtCharts, so a bundle missing this
    module must fail the FIBR-0003 build smoke, not a user launch. Uses ``QBarSet``
    (a plain ``QObject``, not a ``QGraphicsWidget`` like ``QChart``) so the check
    needs no ``QApplication`` — the FAIL unit test patches ``_check_qt`` away."""
    from PySide6.QtCharts import QBarSet

    bar_set = QBarSet("smoke")
    bar_set.append(1.0)
    if bar_set.count() != 1:
        raise RuntimeError("QtCharts did not load — Qt6Charts missing from the bundle")


def _check_icons() -> None:
    """Render one bundled toolbar SVG icon, proving the ``ui/icons/`` package data
    **and** the Qt SVG plugins (``imageformats/qsvg`` + ``iconengines/qsvgicon``)
    travel into the frozen bundle (FIBR-0051 Deliverable 9 / DoD #2).

    A *rendered* 16 px pixmap is the right proof: if the SVG travels but the Qt
    SVG plugins are dropped, ``QIcon(path)`` is non-null (the icon object exists)
    yet its pixmap renders **null** — so only a non-null pixmap proves both the
    file **and** its renderer are present. Runs after ``_check_qt`` (needs the
    QApplication).
    """
    from PySide6.QtCore import QSize

    from finbreak.ui.icons import app_icon, icon

    pixmap = icon("lock").pixmap(QSize(16, 16))
    if pixmap.isNull() or pixmap.size().isEmpty():
        raise RuntimeError(
            "bundled icon did not render — ui/icons/ package data or the Qt SVG "
            "plugins did not travel with the bundle"
        )
    # The branded raster app icon (FIBR-0037) travels as ui/icons/app.png; render
    # it too so a dropped PNG (a different package-data glob than the SVGs) is caught.
    app_pixmap = app_icon().pixmap(QSize(32, 32))
    if app_pixmap.isNull() or app_pixmap.size().isEmpty():
        raise RuntimeError(
            "branded app icon did not render — ui/icons/app.png did not travel "
            "with the bundle"
        )


def _check_sqlcipher() -> None:
    """Open a keyed SQLCipher DB and round-trip a row, proving the lib loads."""
    import sqlcipher3

    with tempfile.TemporaryDirectory() as tmp:
        con = sqlcipher3.connect(str(Path(tmp) / "smoke.db"))
        try:
            con.execute(_SMOKE_KEY_PRAGMA)
            con.execute("CREATE TABLE t (v TEXT)")
            con.execute("INSERT INTO t VALUES ('ok')")
            row = con.execute("SELECT v FROM t").fetchone()
        finally:
            con.close()
    if row is None or row[0] != "ok":
        raise RuntimeError("SQLCipher round-trip did not return the written row")


def _check_pikepdf() -> None:
    """Construct an in-memory PDF, proving the qpdf native library loads."""
    import pikepdf

    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page()
    if len(pdf.pages) != 1:
        raise RuntimeError("pikepdf did not create the expected single page")


def _check_argon2() -> None:
    """Derive a throwaway key, proving the native Argon2 library loads (FIBR-0004).

    Tiny cost parameters — this only proves the vendored native lib travels with
    the bundle, not the real (pinned) vault parameters.
    """
    from argon2.low_level import Type, hash_secret_raw

    raw = hash_secret_raw(
        secret=b"finbreak-selftest-not-a-real-secret",
        salt=b"finbreak-16bytes",
        time_cost=1,
        memory_cost=8,
        parallelism=1,
        hash_len=16,
        type=Type.ID,
    )
    if len(raw) != 16:
        raise RuntimeError("argon2 did not return the expected key length")


def _check_ofxparse() -> None:
    """Parse a tiny OFX document, proving ofxparse + its transitive tree
    (beautifulsoup4, native lxml) travel with the bundle (FIBR-0008).

    ``--self-test`` imports only this module — never ``finbreak.app`` — so
    without this leg the bundle smoke-test would freeze ofxparse in but never
    exercise it. ofxparse parses with the stdlib ``html.parser`` (not lxml), so
    this also proves beautifulsoup4's package data travels. The document is a
    minimal single-transaction statement, not real financial data.
    """
    import io

    from ofxparse import OfxParser

    doc = (
        b"OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
        b"ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\n"
        b"NEWFILEUID:NONE\r\n\r\n<OFX><BANKMSGSRSV1><STMTTRNRS><TRNUID>1"
        b"<STATUS><CODE>0<SEVERITY>INFO</STATUS><STMTRS><CURDEF>ZAR"
        b"<BANKACCTFROM><BANKID>1<ACCTID>1<ACCTTYPE>CHECKING</BANKACCTFROM>"
        b"<BANKTRANLIST><DTSTART>20260101<DTEND>20260131<STMTTRN><TRNTYPE>DEBIT"
        b"<DTPOSTED>20260105<TRNAMT>-1.00<FITID>1<NAME>Smoke</STMTTRN>"
        b"</BANKTRANLIST><LEDGERBAL><BALAMT>0.00<DTASOF>20260131</LEDGERBAL>"
        b"</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
    )
    ofx = OfxParser.parse(io.BytesIO(doc))
    if not ofx.accounts or len(ofx.account.statement.transactions) != 1:
        raise RuntimeError("ofxparse did not parse the smoke statement")


# A tiny gridded (ruled) single-table PDF (header A/B, one data row), base64,
# frozen at authoring time. pdfplumber's table detection is line-based, so the
# table MUST be ruled (an un-ruled table extracts as ``[]``). The bundle is
# Python-free, so the blob is embedded — no reportlab generation (reportlab is
# probe-only). Not real financial data (FIBR-0009 DoD #2).
_SMOKE_PDF_B64 = (
    b"JVBERi0xLjQKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3Vy"
    b"Y2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAv"
    b"SGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAv"
    b"VHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9N"
    b"ZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNl"
    b"cyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9J"
    b"bWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRv"
    b"YmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRh"
    b"bG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKFwoYW5vbnltb3VzXCkpIC9DcmVhdGlv"
    b"bkRhdGUgKEQ6MjAyNjA3MDQxOTM1NTcrMDInMDAnKSAvQ3JlYXRvciAoXCh1bnNwZWNpZmllZFwp"
    b"KSAvS2V5d29yZHMgKCkgL01vZERhdGUgKEQ6MjAyNjA3MDQxOTM1NTcrMDInMDAnKSAvUHJvZHVj"
    b"ZXIgKFJlcG9ydExhYiBQREYgTGlicmFyeSAtIFwob3BlbnNvdXJjZVwpKSAKICAvU3ViamVjdCAo"
    b"XCh1bnNwZWNpZmllZFwpKSAvVGl0bGUgKFwoYW5vbnltb3VzXCkpIC9UcmFwcGVkIC9GYWxzZQo+"
    b"PgplbmRvYmoKNiAwIG9iago8PAovQ291bnQgMSAvS2lkcyBbIDMgMCBSIF0gL1R5cGUgL1BhZ2Vz"
    b"Cj4+CmVuZG9iago3IDAgb2JqCjw8Ci9GaWx0ZXIgWyAvQVNDSUk4NURlY29kZSAvRmxhdGVEZWNv"
    b"ZGUgXSAvTGVuZ3RoIDIzNAo+PgpzdHJlYW0KR2FzMkNibXFUNSY7OUw3YD5tRDFaOVdzXkQ1JkFz"
    b"TW9tIStCW1g3N0hMXlkzJE0+ZCtmZyhqa0ReUG9ZS1ZFUlxIX0JuMkQ/cU5IMC1KTHNyI1RZIm1Z"
    b"aW5NWGxIZ28lVFpkJD5qXUM1WVhQaT49Jm9yJThzIjxeVyRUNUUuZWsna2VKdTtXP2k5W3NGKDVV"
    b"LDlKWmxRWktZYDdKQi82SHJhSFs9UyhCZkApN0w/UGxrVVliVFNLZ1hsLkMvPSx1b251cHNSKSIu"
    b"ZV5lO1xQV2gnVFRZNVY3PT07U0lSalk5IV5VJ2c4LH4+ZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAg"
    b"OAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNjEgMDAwMDAgbiAKMDAwMDAwMDA5MiAwMDAw"
    b"MCBuIAowMDAwMDAwMTk5IDAwMDAwIG4gCjAwMDAwMDA0MDIgMDAwMDAgbiAKMDAwMDAwMDQ3MCAw"
    b"MDAwMCBuIAowMDAwMDAwNzUwIDAwMDAwIG4gCjAwMDAwMDA4MDkgMDAwMDAgbiAKdHJhaWxlcgo8"
    b"PAovSUQgCls8MzFjYTY5MTQyOTM4Y2FmY2Q0YjYzYTE0YzdmOTFmM2M+PDMxY2E2OTE0MjkzOGNh"
    b"ZmNkNGI2M2ExNGM3ZjkxZjNjPl0KJSBSZXBvcnRMYWIgZ2VuZXJhdGVkIFBERiBkb2N1bWVudCAt"
    b"LSBkaWdlc3QgKG9wZW5zb3VyY2UpCgovSW5mbyA1IDAgUgovUm9vdCA0IDAgUgovU2l6ZSA4Cj4+"
    b"CnN0YXJ0eHJlZgoxMTMzCiUlRU9GCg=="
)


def _check_pdfplumber() -> None:
    """Normalise a tiny embedded gridded PDF through ``pikepdf`` and extract its
    table with ``pdfplumber`` — the FIBR-0009 native chain (Pillow, PDFium via
    ``pypdfium2_raw``, cryptography). ``--self-test`` imports only this module —
    never ``finbreak.app`` — so without this leg the bundle would freeze the PDF
    stacks in but never exercise them (mirrors the ofxparse leg)."""
    import base64
    import io

    import pdfplumber
    import pikepdf

    raw = base64.b64decode(_SMOKE_PDF_B64)
    with pikepdf.open(io.BytesIO(raw)) as pdf:  # in-memory normalise (D3)
        normalised = io.BytesIO()
        pdf.save(normalised)
    with pdfplumber.open(io.BytesIO(normalised.getvalue())) as pdf:
        tables = pdf.pages[0].extract_tables()
    if not tables or tables[0][0] != ["A", "B"]:
        raise RuntimeError("pdfplumber did not extract the smoke table")


def run_self_test(out: TextIO | None = None) -> int:
    """Run every native-stack check in order; print one sentinel line.

    Returns 0 and prints ``FINBREAK_SELFTEST_OK`` if every stack loads;
    otherwise prints ``FINBREAK_SELFTEST_FAIL: <stack>`` for the first failure
    and returns 1. The check functions are looked up by name at call time, so a
    test can monkeypatch any of them.
    """
    stream = sys.stdout if out is None else out
    checks = (
        ("qt", _check_qt),
        ("qtcharts", _check_qtcharts),
        ("icons", _check_icons),
        ("sqlcipher", _check_sqlcipher),
        ("pikepdf", _check_pikepdf),
        ("argon2", _check_argon2),
        ("ofxparse", _check_ofxparse),
        ("pdfplumber", _check_pdfplumber),
    )
    for name, check in checks:
        try:
            check()
        except Exception:  # noqa: BLE001 — any failure means the stack didn't load
            # FINBREAK_SELFTEST_DEBUG=1 dumps the real exception to stderr (the
            # sentinel line alone can't say *why* a native lib failed to load).
            if os.environ.get("FINBREAK_SELFTEST_DEBUG") == "1":
                traceback.print_exc()
            print(f"FINBREAK_SELFTEST_FAIL: {name}", file=stream)
            return 1
    print("FINBREAK_SELFTEST_OK", file=stream)
    return 0
