"""FIBR-0003 INV-1 — self-test that loads the bundled native stacks.

Each ``_check_*`` imports its native dependency **lazily** (inside the
function), so this module imports cleanly even when a dep is missing and so a
test can monkeypatch a check. ``run_self_test`` runs them in order and prints
exactly one sentinel line — ``FINBREAK_SELFTEST_OK`` on success, or
``FINBREAK_SELFTEST_FAIL: <stack>`` on the first failing stack.

The whole point is to prove — inside a Python-free bundle — that every native
stack travels with the artifact: Qt, the SQLCipher native library, and qpdf
(behind ``pikepdf``, FIBR-0003), Argon2 (FIBR-0004), and ofxparse's transitive
tree incl. native lxml (FIBR-0008). See docs/specs/FIBR-0003.md.
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


def run_self_test(out: TextIO | None = None) -> int:
    """Run all three native-stack checks in order; print one sentinel line.

    Returns 0 and prints ``FINBREAK_SELFTEST_OK`` if every stack loads;
    otherwise prints ``FINBREAK_SELFTEST_FAIL: <stack>`` for the first failure
    and returns 1. The check functions are looked up by name at call time, so a
    test can monkeypatch any of them.
    """
    stream = sys.stdout if out is None else out
    checks = (
        ("qt", _check_qt),
        ("sqlcipher", _check_sqlcipher),
        ("pikepdf", _check_pikepdf),
        ("argon2", _check_argon2),
        ("ofxparse", _check_ofxparse),
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
