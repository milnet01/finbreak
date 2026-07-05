"""FIBR-0050 — Standard Bank statement text-parser. Enforces
tests/features/standard_bank_pdf/spec.md.

Pure line-grammar helpers are unit-tested on synthetic text strings (no PDF); the
end-to-end + security + wizard legs use committed SYNTHETIC reportlab fixtures
(fake data + the SB legal marker). Encrypted variants are made in-test with pikepdf.
"""

import io
import logging
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pikepdf
import pytest

from conftest import _PW
from finbreak.importers.standard_bank import (
    Family,
    StandardBankImporter,
    _detect_number_format,
    _infer_years,
    _parse_amount,
    _parse_family_a,
    _parse_family_c,
    _split_credit_card_line,
    detect_standard_bank,
)
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService
from finbreak.services.transactions import read_minor_unit_exponent

pytestmark = pytest.mark.features

_FIXTURES = Path(__file__).parent / "fixtures"


def _fx(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


def _parse(name: str, password: str | None = None):
    return StandardBankImporter().parse(_fx(name), 2, password)


def _encrypt(raw: bytes, *, user: str, owner: str = "owner-pw") -> bytes:
    out = io.BytesIO()
    with pikepdf.open(io.BytesIO(raw)) as pdf:
        pdf.save(out, encryption=pikepdf.Encryption(owner=owner, user=user, R=6))
    return out.getvalue()


# --------------------------------------------------------------------------- #
# Pure helpers (no PDF)
# --------------------------------------------------------------------------- #
def test_INV8_number_format_us_and_eu():
    assert _detect_number_format("1,427.41 730.55- 12.10") == "us"
    assert _detect_number_format("239.206,04- 1.910,76-") == "eu"


def test_INV8_mixed_number_format_refused():
    with pytest.raises(ValueError, match="mixes number formats"):
        _detect_number_format("1,234.56 and 1.234,56")


def test_INV8a_euro_and_us_same_value_same_minor():
    assert _parse_amount("1.910,76-", "eu") == _parse_amount("1,910.76-", "us")
    assert _parse_amount("-R4,200.00", "us") == Decimal("4200.00")


def test_INV9a_year_rollover_dec_to_jan():
    years = _infer_years([(12, 30), (1, 3)], ("2023-08-19", "2024-02-17"))
    assert years == [2023, 2024]


def test_INV9a_year_rollover_nov_to_feb_gap():
    # A dormant account: Nov then Feb, no Dec/Jan — a strict 12->1 test would miss it.
    years = _infer_years([(11, 20), (2, 15)], ("2023-08-19", "2024-02-17"))
    assert years == [2023, 2024]


def test_split_credit_card_line_two_segments():
    segs = _split_credit_card_line("21 Apr 26 Shop 350.00 9 May 26 Cafe 415.94")
    assert segs == ["21 Apr 26 Shop 350.00", "9 May 26 Cafe 415.94"]


def test_INV2a_detect_family_and_none():
    assert (
        detect_standard_bank(
            "BANK STATEMENT / TAX INVOICE\n"
            "Details Service Fee Debits Credits Date Balance\n"
            "The Standard Bank of South Africa Limited"
        )
        is Family.A
    )
    # legal marker present but no recognised header -> None (generic fallback).
    marked = "The Standard Bank of South Africa\nrandom prose"
    assert detect_standard_bank(marked) is None
    # no legal marker -> None.
    assert detect_standard_bank("Some Other Bank\nDate Description Amount") is None


def test_INV3a_family_a_keeps_embedded_mm_dd_in_description():
    lines = [
        "BALANCE BROUGHT FORWARD 08 19 1.000,00-",
        "INTEREST ON OVERDRAFT UP TO 08 24 100,00- 08 25 1.100,00-",
    ]
    r = _parse_family_a(lines, 2, "eu", ("2023-08-19", "2024-02-17"))
    assert r.drafts[0].description == "INTEREST ON OVERDRAFT UP TO 08 24"
    assert r.drafts[0].amount_minor == -10000  # -100,00


def test_INV6a_family_c_keeps_embedded_price_amount_is_last_token():
    r = _parse_family_c(["24 Apr 26 Patreon Membership 5.75 95.41"], 2, "us")
    assert r.drafts[0].description == "Patreon Membership 5.75"
    assert r.drafts[0].amount_minor == -9541  # 95.41 purchase -> budget negative


# --------------------------------------------------------------------------- #
# parse() per family (INV-1/3/4/5/6)
# --------------------------------------------------------------------------- #
def test_INV3_family_a_current():
    r = _parse("family_a_current.pdf")
    assert [d.amount_minor for d in r.drafts] == [-10000, 25000, -5000]
    assert (r.period_start, r.period_end) == ("2026-05-01", "2026-05-31")


def test_INV3_family_a_rcp_european_with_rollover():
    r = _parse("family_a_rcp_euro.pdf")
    assert [d.amount_minor for d in r.drafts] == [-10000, 500000]
    # Dec 2023 then Jan 2024 via the month-decrease rollover.
    assert [d.occurred_on for d in r.drafts] == ["2023-12-25", "2024-01-15"]


def test_INV4_family_b_homeloan_unsigned_balance_signed_closing():
    r = _parse("family_b_homeloan.pdf")
    assert [d.amount_minor for d in r.drafts] == [5000, -30000]


def test_INV5_family_d_moneymarket_page2_schedule_excluded():
    r = _parse("family_d_moneymarket.pdf")
    assert [d.amount_minor for d in r.drafts] == [-20000, 5000]  # withdrawal, interest


def test_INV6_family_c_creditcard_deinterleave_and_flip():
    r = _parse("family_c_creditcard.pdf")
    # credit -100 -> budget +100; purchases 50/30 -> budget -50/-30.
    assert [d.amount_minor for d in r.drafts] == [10000, -5000, -3000]


# --------------------------------------------------------------------------- #
# Integrity (INV-7b / INV-11 / D13)
# --------------------------------------------------------------------------- #
def test_INV11_checksum_failure_raises_and_imports_nothing():
    with pytest.raises(ValueError, match="didn't add up"):
        _parse("checksum_fail_a.pdf")


def test_INV11_savings_no_closing_imports_on_per_row_gate():
    r = _parse("savings_no_closing.pdf")  # no closing line -> per-row gate only
    assert [d.amount_minor for d in r.drafts] == [200]  # +2.00 interest


def test_D13_quiet_month_returns_empty_draft_with_period():
    r = _parse("quiet_month_a.pdf")
    assert r.drafts == []
    assert (r.period_start, r.period_end) == ("2026-05-01", "2026-05-31")


def test_INV2_non_sb_pdf_returns_none():
    assert _parse("non_sb.pdf") is None


# --------------------------------------------------------------------------- #
# Bounds (INV-14)
# --------------------------------------------------------------------------- #
def test_INV14_row_cap_refuses(monkeypatch):
    monkeypatch.setattr("finbreak.importers.standard_bank._MAX_PDF_ROWS", 1)
    with pytest.raises(ValueError, match="too many transactions"):
        _parse("family_a_current.pdf")  # 3 drafts > 1


def test_INV14_page_cap_refuses(monkeypatch):
    monkeypatch.setattr("finbreak.importers.standard_bank._MAX_PDF_PAGES", 1)
    with pytest.raises(ValueError, match="too many pages"):
        _parse("family_d_moneymarket.pdf")  # 2 pages > 1


# --------------------------------------------------------------------------- #
# Security (INV-12) — in-memory decrypt, no secret logged
# --------------------------------------------------------------------------- #
def test_INV12_encrypted_statement_decrypts_with_password():
    enc = _encrypt(_fx("family_a_current.pdf"), user="sentinel-pw-42")
    r = StandardBankImporter().parse(enc, 2, "sentinel-pw-42")
    assert r is not None and len(r.drafts) == 3


def test_INV12_wrong_password_raises_passworderror_without_leaking_secret(caplog):
    enc = _encrypt(_fx("family_a_current.pdf"), user="sentinel-pw-42")
    with caplog.at_level(logging.DEBUG, logger="finbreak"):
        with pytest.raises(pikepdf.PasswordError) as exc:
            StandardBankImporter().parse(enc, 2, "wrong-password")
    assert "sentinel-pw-42" not in str(exc.value)
    assert not any("sentinel-pw-42" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------- #
# Wizard round-trip (INV-13, qtbot) — skips mapping like OFX
# --------------------------------------------------------------------------- #
@pytest.fixture
def paths(tmp_path) -> tuple[Path, Path]:
    return tmp_path / "vault.db", tmp_path / "vault.kdf.json"


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _acct(service: AuthService) -> int:
    return AccountService(service.vault).list_accounts()[0].id


def _wizard(qtbot, service, acct):
    from finbreak.ui.import_wizard import ImportWizardWidget

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    return widget


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_INV1_end_to_end_preview_result_pipeline(service):
    exponent = read_minor_unit_exponent(service.vault.connection)
    acct = _acct(service)
    result = StandardBankImporter().parse(_fx("family_a_current.pdf"), exponent)
    imp = ImportService(service.vault)
    preview = imp.preview_result(result, acct)
    assert preview.new_count == 3
    imp.commit_import(preview, preview.period_start, preview.period_end, "stmt.pdf")
    # re-import the same statement -> all duplicate.
    again = imp.preview_result(
        StandardBankImporter().parse(_fx("family_a_current.pdf"), exponent), acct
    )
    assert again.new_count == 0


def test_INV13_wizard_sb_pick_skips_mapping_lands_on_preview(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import _STEP_PREVIEW

    acct = _acct(service)
    path = _write(tmp_path, "current.pdf", _fx("family_a_current.pdf"))
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == _STEP_PREVIEW, "SB skips the map step"
    assert widget._import_button.isEnabled()
    widget._import_button.click()
    from finbreak.repositories.transactions import TransactionRepository

    assert TransactionRepository(service.vault.connection).count_for_account(acct) == 3


def test_INV13_wizard_reimport_adds_zero(qtbot, service, tmp_path):
    from finbreak.repositories.transactions import TransactionRepository

    acct, conn = _acct(service), service.vault.connection
    path = _write(tmp_path, "current.pdf", _fx("family_a_current.pdf"))
    w = _wizard(qtbot, service, acct)
    w._select_file(str(path))
    w._import_button.click()  # first import
    assert TransactionRepository(conn).count_for_account(acct) == 3
    w2 = _wizard(qtbot, service, acct)
    w2._select_file(str(path))
    assert w2._preview.new_count == 0
    w2._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 3, "no new rows"
