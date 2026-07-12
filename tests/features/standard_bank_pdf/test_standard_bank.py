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

from conftest import _PW, _acct
from finbreak.importers.standard_bank import (
    _MONEY,
    Family,
    StandardBankImporter,
    _cc_opening,
    _detect_number_format,
    _infer_years,
    _parse_amount,
    _parse_family_a,
    _parse_family_b,
    _parse_family_c,
    _span,
    _split_credit_card_line,
    _table_region,
    detect_standard_bank,
)
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
@pytest.mark.parametrize(
    "text, expected",
    [
        # Grouped (SB's actual format) — unchanged.
        ("bal 1,234.56 amt 78.90", ["1,234.56", "78.90"]),
        ("12.34", ["12.34"]),
        ("1,234,567.89", ["1,234,567.89"]),
        # FIBR-0067: ungrouped 4+-digit runs are now accepted.
        ("1234.56", ["1234.56"]),
        ("1234567.89", ["1234567.89"]),
        # Still excluded: 3-decimal rates, and — via the tail guard — a
        # dotted-date fragment. ISO/spaced dates carry no two-decimal tail.
        ("interest rate 7.050%", []),
        ("2025.07.21", []),
        ("2025-07-21", []),
    ],
    ids=[
        "grouped_pair",
        "small",
        "grouped_millions",
        "ungrouped_4digit",
        "ungrouped_7digit",
        "reject_3dp_rate",
        "reject_dotted_date",
        "iso_date_no_tail",
    ],
)
def test_FIBR0067_money_regex_accepts_ungrouped_rejects_dates(text, expected):
    """_MONEY now matches ungrouped 4+-digit amounts (FIBR-0067) while still
    excluding 3-decimal rates and dotted-date fragments (the (?![.,]?\\d) guard).
    Validated end-to-end against all six real statement families (throwaway, never
    committed) — they always group, so this widening added zero matches there."""
    assert _MONEY.findall(text) == expected


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


@pytest.mark.parametrize(
    "header, expected",
    [
        ("Posting Effective Cash\nDebit Credit Balance", Family.B),
        (
            "Transaction description Withdrawals Deposits Interest rate Balance",
            Family.D,
        ),
        (
            "Date Description Amount Date Description Amount\nTitanium Credit Card",
            Family.C,
        ),
    ],
    ids=["family_b", "family_d", "family_c"],
)
def test_INV2a_each_family_detected_by_its_own_signature(header, expected):
    # Parametrized (FIBR-0063) so a regression in one family's signature doesn't
    # mask the others behind a single bundled-assert failure.
    marker = "\nThe Standard Bank of South Africa Limited"
    assert detect_standard_bank(header + marker) is expected


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


def test_FIBR0106_cc_opening_ignores_prose_decoy_before_real_anchor():
    # A credit-card statement can print a prose sentence that CONTAINS the phrase
    # "balance brought forward" — narrating the *closing* position — BEFORE the real
    # brought-forward anchor row. The reader must skip the decoy (its amount is
    # separated from the phrase by narrative text) and read the real opening, whose
    # balance sits immediately after the phrase. (FIBR-0106; synthetic figures.)
    text = (
        "You have a credit balance. Balance brought forward on this statement -251.85\n"
        "21 Jul 25 Balance Brought Forward 6,849.68\n"
        "22 Jul 25 Fake Shop 100.00 6,949.68\n"
    )
    assert _cc_opening(text, "us") == Decimal("6849.68")


def test_FIBR0106_cc_opening_honours_printed_negative_sign():
    # A card that opens in credit prints a trailing-minus brought-forward; the
    # anchor fix must still route through _signed_balance so that sign survives.
    text = "21 Jul 25 Balance Brought Forward 4,200.00-\n"
    assert _cc_opening(text, "us") == Decimal("-4200.00")


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


def test_FIBR0112_family_c_continuation_page_without_column_header_is_captured():
    # A real 3-page SBSA credit-card statement carries the transaction table onto a
    # final page that reprints NO "Date Description Amount" column header — it opens
    # straight into a "Debit Debit" section. The region must still be found, else the
    # page's transactions are silently dropped and the completeness checksum fails
    # ("didn't add up" — FIBR-0112). Region ends at the "Closing balance" terminator.
    page = [
        "Titanium Credit Card",
        "MR A SPECIMEN Page 3 of 3",
        "Tax Invoice",
        "Debit Debit",
        "20 Oct 25 Fake Shop 514.21 20 Oct 25 Fake Fee 23.05",
        "20 Oct 25 Fake Shop Tips 10.00",
        "Closing balance 1,968.77",
    ]
    region = page[_table_region(page, Family.C)]
    assert "20 Oct 25 Fake Shop 514.21 20 Oct 25 Fake Fee 23.05" in region
    assert "20 Oct 25 Fake Shop Tips 10.00" in region
    assert "Closing balance 1,968.77" not in region  # terminator ends the region


def test_FIBR0112_family_c_headerless_summary_page_stays_empty():
    # The header-less fallback must NOT fire on the summary page (also header-less):
    # its only date-bearing lines are spans like "Statement Period 20 Sep 25 to 20 Oct
    # 25" whose trailing token has no 2-decimal amount, so they are not transactions
    # and must not be mistaken for a region (which would fabricate bogus drafts).
    page = [
        "Titanium Credit Card",
        "Statement Period 20 Sep 25 to 20 Oct 25",
        "Statement Date 20 Oct 25",
        "Balance brought forward 1,348.95",
        "Total amount outstanding on this statement 1,968.77",
    ]
    assert _table_region(page, Family.C) == slice(0, 0)


# --------------------------------------------------------------------------- #
# parse() per family (INV-1/3/4/5/6)
# --------------------------------------------------------------------------- #
def test_INV3_family_a_current():
    r = _parse("family_a_current.pdf")
    assert [d.amount_minor for d in r.drafts] == [-10000, 25000, -5000]
    # occurred_on asserted alongside amounts (matches every sibling family test):
    # locks year-inference for the most common US-current-account case.
    assert [d.occurred_on for d in r.drafts] == [
        "2026-05-02",
        "2026-05-03",
        "2026-05-04",
    ]
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


def test_family_b_page_break_boilerplate_not_folded_into_description():
    # FIBR-0119: a Home-Loan page break reprints the registered-office letterhead
    # (bare account number, address, contact) + a repeated column header BETWEEN two
    # transactions. None of those lines carries a date+amount, so _fold used to glue
    # the whole block onto the preceding transaction's description. They must be
    # dropped, leaving the transaction description clean. Balances self-reconcile so
    # the per-row gate passes (the bug corrupts only the description, not the money).
    lines = [
        "2025-11-01 BROUGHT FORWARD 1,000.00",
        "2025-11-01 2025-11-01 Service HL 69.00 1,069.00",
        "2025-11-03 2025-11-02 Insurance Premium 855.14 1,924.14",
        "0453155796",
        "Standard Bank Centre 1st Floor 5 Simmonds Street Johannesburg 2001",
        "P O Box 61690 Marshalltown 2107 South Africa www.standardbank.co.za",
        "Tel. Switchboard: +27 (0)11 636-9112 Fax: +27 (0)11 636-6299",
        "Debit Credit Balance",
        "Date Date Fee",
        "2025-11-20 2025-11-20 Debit Order 100.00 1,824.14",
    ]
    r = _parse_family_b(lines, 2, "us")
    assert [d.description for d in r.drafts] == [
        "Service HL",
        "Insurance Premium",
        "Debit Order",
    ]
    assert [d.amount_minor for d in r.drafts] == [6900, 85514, -10000]


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
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


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

    class _Fake(QDialog):
        """Real QDialog stand-in: auto-accepts (with the scripted password/remember)
        or rejects on show(), so the async _on_pdf_password slot runs through
        show_modal's real wiring (FIBR-0065 INV-5)."""

        def __init__(self, account_name, parent=None):
            super().__init__(parent)
            self._r = next(seq)
            shown.append(account_name)

        def show(self):
            super().show()
            if self._r.get("accept", True):
                self.accept()
            else:
                self.reject()

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
    # A locked SB statement: the wizard's `_try_decrypt` password state machine prompts,
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
    # Assert the friendly message itself (FIBR-0064), not merely that it is non-empty
    # — so a regression to a raw exception string would fail here.
    assert "couldn't read this pdf" in widget._error.text().lower()


def test_parse_maps_pdf_parse_error_to_value_error(monkeypatch):
    """A PDF pikepdf can open but pdfplumber can't parse fails as a friendly
    ValueError, not an unhandled non-ValueError crash. (indie-review H-D)"""
    import pdfplumber
    from pdfplumber.utils.exceptions import PdfminerException

    import finbreak.importers.standard_bank as sb_mod

    monkeypatch.setattr(sb_mod, "_normalise_to_plaintext", lambda raw, pw: raw)

    def boom(*args, **kwargs):
        raise PdfminerException("bad content stream")

    monkeypatch.setattr(pdfplumber, "open", boom)
    with pytest.raises(ValueError):
        StandardBankImporter().parse(b"whatever", 2)


def test_parse_period_bad_month_returns_none_not_keyerror():
    """A non-English (Afrikaans "Januarie") or garbled month name in the period
    line yields None, not a bare KeyError that would crash the wizard.
    (indie-review H1)"""
    from finbreak.importers.standard_bank import _parse_period

    assert _parse_period("Statement from 1 January 2026 to 31 January 2026") == (
        "2026-01-01",
        "2026-01-31",
    )
    assert _parse_period("Statement from 1 Januarie 2026 to 31 Januarie 2026") is None
    assert _parse_period("Statement from 1 Bogus 2026 to 2 Bogus 2026") is None
