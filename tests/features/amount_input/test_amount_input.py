"""FIBR-0219 — locale-aware manual-entry amount input. Enforces spec.md here.

The manual-entry Amount field accepts the numeric part of what the app just
displayed, under the user's own locale, and refuses anything two conventions read
as two different numbers rather than guessing (a wrong guess is 100x or 1000x on
a money field). Every leg pins the DEFAULT QLocale — ``ui/_amount.py`` reads
``QLocale()``, not ``QLocale.system()``, so a pinned default is what the parser
actually sees and the suite stays hermetic on any runner.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale

from conftest import _PW
from finbreak.importers.csv_importer import CsvImporter
from finbreak.importers.ofx_importer import OfxImporter
from finbreak.importers.standard_bank import StandardBankImporter
from finbreak.models import ColumnMapping
from finbreak.services.auth import AuthService
from finbreak.services.transactions import TransactionService, parse_transaction
from finbreak.ui._amount import _format_amount, parse_amount_input
from finbreak.ui.manual_entry import ManualEntryDialog

pytestmark = pytest.mark.features

NBSP = " "  # en_ZA / sv_SE groupSeparator()
NNBSP = " "  # fr_FR groupSeparator()
MINUS = "−"  # sv_SE negativeSign() — NOT the ASCII hyphen-minus

LOCALES = ("en_US", "en_ZA", "de_DE", "fr_FR", "sv_SE")

# The ambiguous shape, restated from spec § 4.5 rather than imported from the
# implementation: <digits><separator><exactly 3 digits>, with a head that may
# itself be grouped. Tests anchor to the contract, not to the code.
AMBIGUOUS_SHAPE = re.compile(r"^[+-]?\d+(?:[.,]\d+)*[.,]\d{3}$")


@contextmanager
def pinned(name: str) -> Iterator[None]:
    """Pin the default QLocale for the duration of the block, then restore it —
    the idiom ``tests/features/app_shell`` already uses for the display side."""
    previous = QLocale()
    QLocale.setDefault(QLocale(name))
    try:
        yield
    finally:
        QLocale.setDefault(previous)


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to latest
    yield svc
    svc.lock()


def _magnitude(rendered: str) -> str:
    """The magnitude of a ``_format_amount`` string: strip the ``-`` or ``( )``
    negative wrapper, then the ``«symbol»␣`` prefix. The group separators inside
    the magnitude are NBSP/NNBSP, never the ASCII space the symbol is joined
    with, so partitioning on ``" "`` cannot cut the number."""
    body = rendered[1:-1] if rendered.startswith("(") else rendered.lstrip("-")
    return body.partition(" ")[2]


def _guard_operand(text: str) -> str:
    """The shape guard's operand, per spec § 4.5 step 3 — restated here so the
    leg below tests the contract rather than mirroring the implementation."""
    group = QLocale().groupSeparator()
    operand = text.strip()
    operand = operand.replace(QLocale().negativeSign(), "-")
    operand = operand.replace(QLocale().positiveSign(), "+")
    for dead in (" ", NBSP, NNBSP, "_", *([group] if group not in ".," else [])):
        operand = operand.replace(dead, "")
    return operand


# --------------------------------------------------------------------------- #
# INV-1 — the locale layer sits at the human-input seam ONLY; import is C-locale
# --------------------------------------------------------------------------- #

_CSV_MAPPING = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)
# Row 2 is the DISCRIMINATING one and the reason this fixture is not three
# ordinary rows: "1.234,56" is rejected by the C convention and read as 1234.56
# by de_DE, so a locale layer pushed down into parse_transaction would make this
# one file import to different numbers on two machines. An ordinary "-12.34" row
# yields the same result under both locales whether or not the layer moved.
_CSV = (
    "Date,Details,Amount\n"
    "2026-01-01,Coffee,-12.34\n"
    '2026-01-02,Grouped,"1.234,56"\n'
    "2026-01-03,Salary,2500.00\n"
)

_OFX_HEADER = (
    "OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
    "ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\n"
    "NEWFILEUID:NONE\r\n\r\n"
)


def _ofx(amounts: list[str]) -> bytes:
    txns = "".join(
        f"<STMTTRN>\n<TRNTYPE>DEBIT\n<DTPOSTED>2026010{i + 1}\n"
        f"<TRNAMT>{amount}\n<NAME>row{i}\n<FITID>f{i}\n</STMTTRN>\n"
        for i, amount in enumerate(amounts)
    )
    return (
        _OFX_HEADER + "<OFX>\n"
        "<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO"
        "</STATUS>\n<STMTRS><CURDEF>ZAR<BANKACCTFROM><BANKID>250655"
        "<ACCTID>000123456<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
        f"<BANKTRANLIST><DTSTART>20260101\n<DTEND>20260131\n{txns}"
        "</BANKTRANLIST>\n<LEDGERBAL><BALAMT>0.00<DTASOF>20260131</LEDGERBAL>\n"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1>\n</OFX>\n"
    ).encode()


def test_INV1_csv_import_is_identical_under_c_and_de_DE():
    """A bank file is machine data: its numbers must not move with the desktop."""
    runs = {}
    for name in ("C", "de_DE"):
        with pinned(name):
            runs[name] = CsvImporter().parse(_CSV, _CSV_MAPPING, 2)

    for name, result in runs.items():
        assert [d.amount_minor for d in result.drafts] == [-1234, 250000], (
            f"under {name}: the C-form rows must import to the same minor units"
        )
        assert [e.row_number for e in result.errors] == [2], (
            f"under {name}: the grouped '1.234,56' row is not C-parseable, so it "
            "stays a row error — reading it as 1234.56 means the locale layer "
            "moved down into parse_transaction"
        )


def test_INV1_ofx_and_pdf_import_are_identical_under_c_and_de_DE():
    """The other two importers. No discriminating row is possible here: ofxparse
    converts <TRNAMT> to a Decimal itself and the PDF fixture is fixed, so the
    raw string never reaches parse_transaction — list equality is the whole leg,
    and the CSV leg above carries the discriminating row."""
    pdf = (
        Path(__file__).parent.parent / "standard_bank_pdf" / "fixtures"
    ) / "family_a_current.pdf"
    ofx_runs, pdf_runs = {}, {}
    for name in ("C", "de_DE"):
        with pinned(name):
            results = OfxImporter().parse(_ofx(["-12.34", "2500.00"]), 2)
            ofx_runs[name] = [d.amount_minor for _, r in results for d in r.drafts]
            parsed = StandardBankImporter().parse(pdf.read_bytes(), 2)
            assert parsed is not None
            pdf_runs[name] = [d.amount_minor for d in parsed.drafts]

    assert ofx_runs["C"] == ofx_runs["de_DE"] == [-1234, 250000], ofx_runs
    assert pdf_runs["C"] == pdf_runs["de_DE"] == [-10000, 25000, -5000], pdf_runs


def test_INV1_parse_transaction_stays_c_locale_only_under_de_DE():
    with pinned("de_DE"):
        with pytest.raises(ValueError):
            parse_transaction("2026-07-01", "-12,34", "x", 2)
        assert parse_transaction("2026-07-01", "-12.34", "x", 2)[1] == -1234, (
            "the C parser stays C under every desktop locale"
        )


# --------------------------------------------------------------------------- #
# INV-2 — every _format_amount magnitude round-trips
# --------------------------------------------------------------------------- #

_ROUND_TRIP = (
    Decimal("12.34"),
    Decimal("1234.56"),
    Decimal("1234567.89"),
    Decimal("0.05"),
    Decimal("-1234.56"),
)


@pytest.mark.parametrize("name", LOCALES)
def test_INV2_every_format_amount_magnitude_round_trips(name):
    """Anchored on the shipping _format_amount, never a re-render of its
    toString line: a leg that renders the magnitude itself stays green when
    _format_amount changes and the real round-trip breaks."""
    with pinned(name):
        for value in _ROUND_TRIP:
            magnitude = _magnitude(_format_amount(value, "ZAR"))
            assert parse_amount_input(magnitude) == abs(value), (
                f"{name}: _format_amount({value}) magnitude {magnitude!r} must "
                "parse back to the magnitude it displayed"
            )


# --------------------------------------------------------------------------- #
# INV-3 — the C form is accepted under every locale (keeps FIBR-0216's
#         "-12.34" placeholder honest without touching it)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", LOCALES)
def test_INV3_the_c_form_is_accepted_under_every_locale(name):
    with pinned(name):
        assert parse_amount_input("-12.34") == Decimal("-12.34"), name
        assert parse_amount_input("1234.56") == Decimal("1234.56"), name


# --------------------------------------------------------------------------- #
# INV-4 — the two conventions disagree -> refuse, naming both readings
# --------------------------------------------------------------------------- #


def test_INV4_disagreeing_input_is_refused_naming_both_readings():
    """The DECIMAL rendering is the half that always differs from the echo: the
    disagree row fires only when the locale reads the string as a valid group, so
    re-rendering that reading under the same locale reproduces the input."""
    with pinned("de_DE"):
        for text, decimal_reading in (
            ("1.234", "1,234"),
            ("12.345", "12,345"),
            ("-1.234", "-1,234"),
        ):
            with pytest.raises(ValueError) as excinfo:
                parse_amount_input(text)
            message = str(excinfo.value)
            assert "(grouped)" in message and "(decimal)" in message, message
            assert f"{decimal_reading} (decimal)" in message, (
                f"{text!r}: the decimal reading must be rendered in the user's "
                f"own convention, got {message!r}"
            )


def test_INV4_dialog_refuses_ambiguous_input_and_stores_nothing(qtbot, service):
    with pinned("de_DE"):
        dialog = ManualEntryDialog(service)
        qtbot.addWidget(dialog)
        transactions = TransactionService(service.vault)
        before = len(transactions.list_transactions())
        dialog._amount.setText("1.234")
        dialog._description.setText("mehrdeutig")
        dialog._add_button.click()

        assert dialog._error.text() != "", "the refusal is shown in-dialog"
        assert len(transactions.list_transactions()) == before, "nothing stored"


def test_INV4_dialog_stores_the_locale_form_the_app_displays(qtbot, service):
    """The ONLY leg that fails when § 4.6 is omitted: unwired, "-12,34" reaches
    parse_transaction, is rejected as non-numeric, and nothing is stored."""
    with pinned("de_DE"):
        dialog = ManualEntryDialog(service)
        qtbot.addWidget(dialog)
        transactions = TransactionService(service.vault)
        dialog._amount.setText("-12,34")
        dialog._description.setText("kaffee")
        with qtbot.waitSignal(dialog.committed):
            dialog._add_button.click()

        stored = [
            row
            for row, *_ in transactions.list_transactions()
            if row.description == "kaffee"
        ]
        assert len(stored) == 1, f"exactly one row stored, got {stored}"
        assert stored[0].amount_minor == -1234, stored[0]


# --------------------------------------------------------------------------- #
# INV-5 — group separators come out BEFORE the decimal point is swapped
# --------------------------------------------------------------------------- #


def test_INV5_group_separators_are_removed_before_the_point_is_swapped():
    """All three legs pin de_DE: a test written only against en_ZA or fr_FR
    passes either order, because their group separator is not a '.'."""
    with pinned("de_DE"):
        assert parse_amount_input("1.234,56") == Decimal("1234.56")
        assert parse_amount_input("-12,34") == Decimal("-12.34")
        assert parse_amount_input("1.234.567,89") == Decimal("1234567.89")


# --------------------------------------------------------------------------- #
# INV-6 — exact Decimal, never Qt's float
# --------------------------------------------------------------------------- #


def test_INV6_the_result_is_an_exact_decimal_not_qts_toDouble_float():
    """The 64-bit bound value. Round-tripped through a binary float it becomes
    9.223372036854776E+16, so this is red against any Decimal(str(value)) build."""
    with pinned("en_US"):
        assert parse_amount_input("92233720368547758.07") == Decimal(
            "92233720368547758.07"
        )


# --------------------------------------------------------------------------- #
# INV-7 — the measured QLocale matrix, asserted rather than only recorded
# --------------------------------------------------------------------------- #

REFUSED = object()

# (locale, input, does QLocale().toDouble accept it, what parse_amount_input does)
_MATRIX = (
    ("de_DE", "-12.34", False, Decimal("-12.34")),
    ("de_DE", "-1234.56", False, Decimal("-1234.56")),
    ("de_DE", "-12,34", True, Decimal("-12.34")),
    ("de_DE", "-1.234,56", True, Decimal("-1234.56")),
    ("de_DE", "1.23", False, Decimal("1.23")),
    ("de_DE", "1.2345", False, Decimal("1.2345")),
    ("de_DE", "1.234", True, REFUSED),
    ("de_DE", "12.345", True, REFUSED),
    ("de_DE", "-1.234", True, REFUSED),
    ("en_ZA", "-12,34", True, Decimal("-12.34")),
    ("en_ZA", "1,500", True, REFUSED),
    ("en_US", "-1,234.56", True, Decimal("-1234.56")),
    ("en_US", "1.234", True, Decimal("1.234")),
    ("fr_FR", f"-1{NNBSP}234,56", True, Decimal("-1234.56")),
    ("sv_SE", "1,500", True, REFUSED),
)


@pytest.mark.parametrize(("name", "text", "qt_accepts", "expected"), _MATRIX)
def test_INV7_the_measured_qlocale_matrix_holds(name, text, qt_accepts, expected):
    """Pins QLocale's group-placement STRICTNESS, which the design leans on:
    de_DE must REJECT "-12.34" rather than read it as -1234. A PySide6 upgrade
    that relaxes it would otherwise land as a silent money-parsing change."""
    with pinned(name):
        assert QLocale().toDouble(text)[1] is qt_accepts, (
            f"{name}: QLocale().toDouble({text!r}) acceptance moved"
        )
        if expected is REFUSED:
            with pytest.raises(ValueError):
                parse_amount_input(text)
        else:
            assert parse_amount_input(text) == expected, f"{name} {text!r}"


# --------------------------------------------------------------------------- #
# INV-8 — the shape guard, on the one-surviving-candidate branch
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ("en_ZA", "de_DE", "fr_FR"))
@pytest.mark.parametrize("text", ("1,500", "12,500", "2,000"))
def test_INV8a_locale_candidate_branch_is_guarded(name, text):
    """The locale convention is the survivor: Qt reads "1,500" as one and a half
    where the typist meant one thousand five hundred (1000x, and a regression
    against today's refusal)."""
    with pinned(name):
        with pytest.raises(ValueError, match="ambiguous"):
            parse_amount_input(text)


@pytest.mark.parametrize("name", ("en_ZA", "fr_FR", "sv_SE"))
@pytest.mark.parametrize("text", ("1.500", "1.250", "0.100", "1234.500"))
def test_INV8b_c_candidate_branch_is_guarded(name, text):
    """The C convention is the survivor. Without this group every guarded input
    is comma-separated, so an implementation applying the guard only when the
    locale candidate exists passes the whole invariant while accepting 1.500."""
    with pinned(name):
        with pytest.raises(ValueError, match="ambiguous"):
            parse_amount_input(text)


@pytest.mark.parametrize(
    ("name", "text"),
    (
        ("en_ZA", "1234,500"),
        ("en_ZA", f"1{NBSP}234,500"),
        ("fr_FR", f"1{NNBSP}234,500"),
        ("en_US", "1,234.500"),
    ),
)
def test_INV8c_a_grouped_head_is_still_guarded(name, text):
    """A pattern anchored on a bare-digit head refuses 1234,500 and waves
    1,234.500 through — the same 1000x error wearing a thousands separator."""
    with pinned(name):
        with pytest.raises(ValueError, match="ambiguous"):
            parse_amount_input(text)


def test_INV8c_en_US_1234comma500_is_simply_not_a_number():
    """No candidate survives, so step 3 never runs and the correct message is the
    ordinary one. Asserting an ambiguity message here goes red on a good build."""
    with pinned("en_US"):
        with pytest.raises(ValueError, match="not a valid number"):
            parse_amount_input("1234,500")


@pytest.mark.parametrize("name", LOCALES)
def test_INV8d_no_format_amount_magnitude_matches_the_guard(name):
    """The guard cannot refuse the app's own output: every supported currency has
    exponent 2, so a magnitude carries two decimals and two never match \\d{3}."""
    with pinned(name):
        for value in _ROUND_TRIP:
            magnitude = _magnitude(_format_amount(value, "ZAR"))
            assert AMBIGUOUS_SHAPE.match(_guard_operand(magnitude)) is None, (
                f"{name}: the guard would refuse the app's own {magnitude!r}"
            )


def test_INV8d_en_US_agreed_readings_are_not_guarded():
    """The guard runs AFTER the agreement test, so en_US loses nothing: both
    conventions read 1.500 identically and it resolves before step 3."""
    with pinned("en_US"):
        assert parse_amount_input("1.500") == Decimal("1.500")


def test_INV8d_the_refusal_message_names_both_readings():
    """The only leg covering step 3's compute-the-readings requirement. en_ZA
    groups with NBSP, and the decimal reading uses the SIGNIFICANT fractional
    digit count — 1,5, not the 1,500 the raw exponent would render."""
    with pinned("en_ZA"):
        with pytest.raises(ValueError) as excinfo:
            parse_amount_input("1,500")
        message = str(excinfo.value)
        assert f"1{NBSP}500 (grouped)" in message, message
        assert "1,5 (decimal)" in message, message


# --------------------------------------------------------------------------- #
# INV-9 — ValueError, and ONLY ValueError, for every input
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", ("", "-", "nan", "inf", ".", ","))
def test_INV9_hostile_input_raises_value_error(text):
    """'inf' is the leg that pins step 1: Decimal('inf') == Decimal('inf') is
    True and toDouble('inf') succeeds, so without it the agreement row fires and
    parse_amount_input RETURNS Infinity."""
    with pinned("en_US"):
        with pytest.raises(ValueError):
            parse_amount_input(text)


def test_INV9_hostile_looking_but_valid_input_returns_a_value():
    """Both parse legitimately; a single undifferentiated must-raise table would
    go red against a correct implementation."""
    with pinned("en_US"):
        assert parse_amount_input("1_000") == Decimal("1000"), "PEP 515 underscores"
        digits = "1" * 400
        assert parse_amount_input(digits) == Decimal(digits)


def test_INV9_sv_SE_accepts_a_typed_unicode_minus():
    """U+2212 IS sv_SE's negativeSign(), so this is what sign normalisation buys.
    Not sourced from _format_amount, whose abs() means its output never carries
    a sign at all."""
    with pinned("sv_SE"):
        assert parse_amount_input(f"{MINUS}1234,56") == Decimal("-1234.56")


def test_INV9_en_US_refuses_a_typed_unicode_minus_without_crashing():
    """U+2212 is NOT en_US's sign, so the replacement is a no-op and toDouble
    still accepts the string — the rebuild raises InvalidOperation, which is an
    ArithmeticError and would escape _on_add's handler unguarded."""
    with pinned("en_US"):
        with pytest.raises(ValueError):
            parse_amount_input(f"{MINUS}1234.56")


def test_FIBR0222_huge_exponent_is_a_ValueError_not_a_decimal_Overflow():
    """`parse_transaction` raises ValueError for EVERY rejection — including one
    reached through `normalize()`.

    `Decimal.normalize()` applies context, so an operand whose adjusted exponent
    exceeds Emax signals Overflow. That is an ArithmeticError, not a ValueError,
    so it walked straight through the `except ValueError` that ManualEntryDialog,
    csv_importer and the import wizard each render with — killing the Qt slot on
    manual entry, and aborting a whole CSV import instead of yielding one
    RowError.

    `Decimal("1e1000000")` constructs fine because string construction is
    context-free, so this is reachable from a single spreadsheet cell rather than
    only from typing. `to_minor_storable` already guarded the identical hazard on
    its own scaling call (FIBR-0222); this is the earlier context-applying
    operation, which did not.
    """
    with pytest.raises(ValueError, match="too large to store"):
        parse_transaction("2026-03-02", Decimal("1e1000000"), "Fake Row", 2)
    # The negative-exponent twin: normalize() on 1e-1000000 signals Subnormal /
    # Underflow rather than Overflow, and must also stay a ValueError.
    with pytest.raises(ValueError):
        parse_transaction("2026-03-02", Decimal("1e-1000000"), "Fake Row", 2)
    # An ordinary amount is unaffected.
    assert parse_transaction("2026-03-02", Decimal("12.34"), "Fake Row", 2) == (
        "2026-03-02",
        1234,
        "Fake Row",
    )
