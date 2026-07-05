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
from PySide6.QtWidgets import QDialog

from conftest import _PW
from finbreak.importers.standard_bank import (
    Family,
    StandardBankImporter,
    _detect_number_format,
    _infer_years,
    _parse_amount,
    _parse_family_a,
    _parse_family_c,
    _span,
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


def test_INV2a_each_family_detected_by_its_own_signature():
    marker = "\nThe Standard Bank of South Africa Limited"
    assert (
        detect_standard_bank("Posting Effective Cash\nDebit Credit Balance" + marker)
        is Family.B
    )
    assert (
        detect_standard_bank(
            "Transaction description Withdrawals Deposits Interest rate Balance"
            + marker
        )
        is Family.D
    )
    assert (
        detect_standard_bank(
            "Date Description Amount Date Description Amount\nTitanium Credit Card"
            + marker
        )
        is Family.C
    )


def test_INV2a_credit_card_wins_over_family_a_detection_order():
    # A statement carrying BOTH the Family-A header tokens AND the credit-card
    # markers must resolve to C — most-specific-first C->D->B->A (D4).
    text = (
        "Date Description Amount\n"
        "Titanium Credit Card\n"
        "Debits Credits Date Balance\n"
        "The Standard Bank of South Africa Limited"
    )
    assert detect_standard_bank(text) is Family.C


def test_D8_span_quiet_bd_falls_back_to_statement_date():
    # B/D print no "Statement from...to..." period; a quiet month (zero drafts)
    # falls back to the statement "Date" line for the coverage span (both the
    # YYYY MM DD and the D Month YYYY forms).
    assert _span(Family.D, None, [], "Transaction details\nDate 2026 03 31\n") == (
        "2026-03-31",
        "2026-03-31",
    )
    assert _span(Family.B, None, [], "Statement\nDate 31 March 2026\n") == (
        "2026-03-31",
        "2026-03-31",
    )


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


def test_INV10_family_c_folds_zero_date_continuation_skips_section_header():
    r = _parse_family_c(
        [
            "2 Apr 26 Fake Payment -100.00",
            "*****9000740 06H54 ref",  # zero-date -> folds into the prior desc
            "Credits Credits",  # section header -> skipped, NOT folded
            "3 Apr 26 Fake Shop 50.00",
        ],
        2,
        "us",
    )
    assert [d.description for d in r.drafts] == [
        "Fake Payment *****9000740 06H54 ref",
        "Fake Shop",
    ]
    assert [d.amount_minor for d in r.drafts] == [10000, -5000]


# --------------------------------------------------------------------------- #
# parse() per family (INV-1/3/4/5/6)
# --------------------------------------------------------------------------- #
def test_INV3_family_a_current():
    r = _parse("family_a_current.pdf")
    assert [d.amount_minor for d in r.drafts] == [-10000, 25000, -5000]
    assert (r.period_start, r.period_end) == ("2026-05-01", "2026-05-31")


def test_INV8_number_format_detected_from_region_not_footer():
    # A US statement with a European-format token in the FOOTER (outside the
    # transaction region) parses fine — detection is region-scoped (D9), so the
    # footer token can't trip "mixes number formats".
    r = _parse("mixed_footer_a.pdf")
    assert [d.amount_minor for d in r.drafts] == [-10000, 25000]


def test_INV3_family_a_rcp_european_with_rollover():
    r = _parse("family_a_rcp_euro.pdf")
    assert [d.amount_minor for d in r.drafts] == [-10000, 500000]
    # Dec 2023 then Jan 2024 via the month-decrease rollover.
    assert [d.occurred_on for d in r.drafts] == ["2023-12-25", "2024-01-15"]


def test_INV4_family_b_homeloan_unsigned_balance_signed_closing():
    r = _parse("family_b_homeloan.pdf")
    assert [d.amount_minor for d in r.drafts] == [5000, -30000]
    assert [d.occurred_on for d in r.drafts] == ["2025-03-02", "2025-03-05"]


def test_INV5_family_d_moneymarket_page2_schedule_excluded():
    r = _parse("family_d_moneymarket.pdf")
    assert [d.amount_minor for d in r.drafts] == [-20000, 5000]  # withdrawal, interest
    # only the two page-1 transactions — the page-2 interest schedule row (a
    # YYYY MM DD line that is NOT a transaction) must be region-excluded, not a 3rd.
    assert [d.occurred_on for d in r.drafts] == ["2026-03-02", "2026-03-03"]


def test_INV6_family_c_creditcard_deinterleave_and_flip():
    r = _parse("family_c_creditcard.pdf")
    # credit -100 -> budget +100; purchases 50/30 -> budget -50/-30.
    assert [d.amount_minor for d in r.drafts] == [10000, -5000, -3000]
    # de-interleave keeps both columns of the split line, in column order.
    assert [d.occurred_on for d in r.drafts] == [
        "2026-04-02",
        "2026-04-03",
        "2026-04-05",
    ]


# --------------------------------------------------------------------------- #
# Integrity (INV-7b / INV-11 / D13)
# --------------------------------------------------------------------------- #
def test_INV11_checksum_failure_raises_and_imports_nothing():
    # The per-row gate: a printed amount whose magnitude != its balance change.
    with pytest.raises(ValueError, match="amount doesn't match its balance change"):
        _parse("checksum_fail_a.pdf")


def test_INV11a_completeness_gate_distinct_from_per_row():
    # Every row reconciles (per-row gate passes) but the independently-printed
    # closing figure disagrees with the running-balance endpoint — the completeness
    # gate, a DISTINCT message from the per-row gate (a dropped trailing row).
    with pytest.raises(ValueError, match="running balance and transactions disagree"):
        _parse("completeness_fail_a.pdf")


def test_INV11a_family_b_missing_closing_raises():
    # Home Loan always prints a closing; its absence is all-or-nothing (unlike
    # Savings, which legitimately prints none and rides the per-row gate).
    with pytest.raises(ValueError, match="couldn't find the closing balance"):
        _parse("family_b_no_closing.pdf")


def test_INV11a_family_c_non_reconciling_raises():
    # Credit card has no per-row running balance — it rides the completeness gate
    # (opening - Σ signed) alone; a closing mismatch is the only integrity signal.
    with pytest.raises(ValueError, match="running balance and transactions disagree"):
        _parse("family_c_fail.pdf")


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
            StandardBankImporter().parse(enc, 2, "attempted-secret-99")
    # Assert on the ATTEMPTED password — the value that actually flows through
    # parse (the document's own "sentinel-pw-42" never reaches the code, so a
    # test that checked it would be vacuous — pdf_import INV-11 analogue).
    assert "attempted-secret-99" not in str(exc.value)
    assert not any("attempted-secret-99" in r.getMessage() for r in caplog.records)


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


def _patch_dialog(monkeypatch, responses):
    """Replace ``import_wizard.PasswordDialog`` with a scripted fake (the same
    pattern as tests/features/pdf_import). Each construction pops the next response
    dict (``password``/``remember``/``accept``); returns the account-name labels."""
    from finbreak.ui import import_wizard

    seq = iter(responses)
    shown: list[str] = []

    class _Fake:
        def __init__(self, account_name, parent=None):
            self._r = next(seq)
            shown.append(account_name)

        def exec(self):
            accepted = self._r.get("accept", True)
            return (
                QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
            )

        def password(self):
            return self._r.get("password", "")

        def remember(self):
            return self._r.get("remember", False)

    monkeypatch.setattr(import_wizard, "PasswordDialog", _Fake)
    return shown


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


def test_INV13_wizard_encrypted_sb_prompts_then_previews(
    qtbot, service, tmp_path, monkeypatch
):
    # A locked SB statement: the wizard's `_decrypt_pdf` password loop prompts,
    # decrypts in memory, THEN the SB reader parses and lands on preview — proving
    # the FIBR-0050 decrypt-once seam composes with the SB branch (not just the
    # generic PDF path the FIBR-0009 suite covers).
    from finbreak.ui.import_wizard import _STEP_PREVIEW

    acct = _acct(service)
    enc = _encrypt(_fx("family_a_current.pdf"), user="sentinel-pw-42")
    path = _write(tmp_path, "locked.pdf", enc)
    shown = _patch_dialog(monkeypatch, [{"password": "sentinel-pw-42"}])
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert len(shown) == 1, "the locked SB statement prompted once"
    assert widget._stack.currentIndex() == _STEP_PREVIEW, "decrypted SB -> preview"
    assert widget._preview.new_count == 3


def test_INV13_wizard_sb_checksum_failure_shows_friendly_message(
    qtbot, service, tmp_path
):
    # A non-reconciling SB statement surfaces the all-or-nothing ValueError as a
    # shown message (never a crashed Qt slot), and stays on the pick step so nothing
    # is imported.
    from finbreak.ui.import_wizard import _STEP_PICK

    acct = _acct(service)
    path = _write(tmp_path, "bad.pdf", _fx("checksum_fail_a.pdf"))
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == _STEP_PICK, "checksum fail stays on pick"
    assert "didn't add up" in widget._error.text()


def test_INV13_wizard_corrupt_pdf_shows_message_not_crash(qtbot, service, tmp_path):
    # A corrupt file that passes the %PDF- sniff makes pikepdf.open raise PdfError
    # (NOT a ValueError/OSError) — the wizard must surface a shown message, never
    # crash the Qt slot (coding.md § 2).
    from finbreak.ui.import_wizard import _STEP_PICK

    acct = _acct(service)
    corrupt = b"%PDF-1.4\ngarbage not a real pdf trailer\n"
    path = _write(tmp_path, "corrupt.pdf", corrupt)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))  # must not raise
    assert widget._stack.currentIndex() == _STEP_PICK, "stays on pick, no crash"
    assert widget._error.text() != "", "a friendly message is shown"
