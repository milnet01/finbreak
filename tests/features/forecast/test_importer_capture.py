"""FIBR-0171 — importers capture the statement closing balance into
`ParseResult.closing_balance_minor` (spec D3/D4, Deliverables 3/4/5).

The Standard Bank importer already computes the closing balance for its
completeness checksum, then discarded it; this feature persists it. OFX reads the
`<LEDGERBAL>` ledger balance. CSV / manual leave it `None`.

Enforces tests/features/forecast/spec.md INV-7/INV-7a/INV-8. tmp_path only; no
network.
"""

from pathlib import Path

import pytest

from finbreak.importers.base import ParseResult
from finbreak.importers.ofx_importer import OfxImporter
from finbreak.importers.standard_bank import StandardBankImporter

pytestmark = pytest.mark.features

# Reuse the real Standard Bank statement fixtures from the SB suite.
_SB_FIXTURES = Path(__file__).parent.parent / "standard_bank_pdf" / "fixtures"


def _sb(name: str):
    return StandardBankImporter().parse((_SB_FIXTURES / name).read_bytes(), 2)


_OFX_HEADER = (
    "OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nSECURITY:NONE\n"
    "ENCODING:USASCII\nCHARSET:1252\nCOMPRESSION:NONE\n"
    "OLDFILEUID:NONE\nNEWFILEUID:NONE\n\n"
)


def _ofx_stmt(*, ledger: str | None) -> bytes:
    """A minimal one-transaction bank statement. ``ledger=None`` OMITS the
    ``<LEDGERBAL>`` block entirely (ofxparse leaves ``statement.balance`` UNSET —
    a bare attribute access raises AttributeError; the getattr guard must survive
    it)."""
    ledger_block = (
        f"<LEDGERBAL><BALAMT>{ledger}<DTASOF>20260131</LEDGERBAL>\n"
        if ledger is not None
        else ""
    )
    body = (
        "<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
        "<STMTRS><CURDEF>ZAR<BANKACCTFROM><BANKID>250655<ACCTID>000123456"
        "<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
        "<BANKTRANLIST><DTSTART>20260101\n<DTEND>20260131\n"
        "<STMTTRN><TRNTYPE>DEBIT\n<DTPOSTED>20260105\n<TRNAMT>-10.00\n"
        "<NAME>Coffee\n<FITID>a1\n</STMTTRN>\n"
        f"</BANKTRANLIST>\n{ledger_block}"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1>"
    )
    return (_OFX_HEADER + "<OFX>\n" + body + "\n</OFX>\n").encode()


# --------------------------------------------------------------------------- #
# INV-8 — the new field defaults None (existing 4-arg construction unaffected)
# --------------------------------------------------------------------------- #
def test_INV8_parse_result_closing_defaults_none() -> None:
    assert ParseResult([], [], None, None).closing_balance_minor is None


# --------------------------------------------------------------------------- #
# INV-7 — Standard Bank captures the printed closing (else None for Savings)
# --------------------------------------------------------------------------- #
def test_INV7_sb_current_captures_closing_balance() -> None:
    assert _sb("family_a_current.pdf").closing_balance_minor == 110_000


def test_INV7_sb_homeloan_captures_signed_closing() -> None:
    assert _sb("family_b_homeloan.pdf").closing_balance_minor == 75_000


def test_INV7_sb_savings_without_closing_is_none() -> None:
    r = _sb("savings_no_closing.pdf")
    assert r.drafts, "the statement still imports on the per-row gate"
    assert r.closing_balance_minor is None


# --------------------------------------------------------------------------- #
# INV-7 / INV-8 — OFX ledger balance, and the balance-less getattr guard
# --------------------------------------------------------------------------- #
def test_INV7_ofx_captures_ledger_balance() -> None:
    _, result = OfxImporter().parse(_ofx_stmt(ledger="1234.56"), 2)[0]
    assert result.closing_balance_minor == 123_456


def test_INV8_ofx_without_ledger_balance_does_not_crash() -> None:
    _, result = OfxImporter().parse(_ofx_stmt(ledger=None), 2)[0]
    assert result.closing_balance_minor is None
    assert result.drafts, "the sibling transaction still imports"


# --------------------------------------------------------------------------- #
# INV-7a (FIBR-0223) — an unstorable <BALAMT> is a friendly ValueError
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("ledger", "why"),
    [
        # ofxparse's `toDecimal` hands the token straight to `Decimal(...)` and
        # catches only InvalidOperation, so exponent notation survives the parse.
        # Scaling it overflows the Decimal context inside `scaleb` —
        # `decimal.Overflow` is an ArithmeticError, so it walks through
        # `_select_ofx`'s `except ValueError` and kills the slot (FIBR-0222's
        # class, on the one to_minor call site that had no guard).
        ("1e999999", "exponent large enough to overflow the scaling itself"),
        # Scales cleanly to 10**32, so nothing raises here — it dies far away, at
        # the INSERT, as an OverflowError past SQLite's signed 64-bit INTEGER.
        # `_on_import` catches only (ValueError, FinbreakError), so that one is a
        # dead slot at commit time rather than at parse time.
        ("1e30", "past SQLite's 64-bit INTEGER, but scales fine"),
        ("-1e30", "same bound, negative"),
    ],
)
def test_INV7a_ofx_unstorable_ledger_balance_is_a_valueerror(ledger, why) -> None:
    """FIBR-0223 — the closing balance is the ONE amount in an OFX file that does
    not go through `parse_transaction`, so it inherited none of that function's
    money contract. Each spelling above reaches a crash the import wizard cannot
    show; `ValueError` is the class INV-4 promises for unusable input."""
    with pytest.raises(ValueError, match="closing balance"):
        OfxImporter().parse(_ofx_stmt(ledger=ledger), 2)
