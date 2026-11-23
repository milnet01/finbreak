"""FIBR-0087 — no figure mixes currencies.

Enforces docs/specs/FIBR-0087-per-account-currency.md INV-6 (``scope_currency``
returns the one currency of its scope, or refuses) and INV-7 (each service in
§ 4.5's first table refuses a mixed scope and still answers a single-currency
one). Every vault uses tmp_path; every row is synthetic (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from io import BytesIO

import pytest

from conftest import _PW
from finbreak.errors import MixedCurrencyError
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.currency import (
    account_currencies,
    accounts_in,
    scope_currency,
    vault_currencies,
)
from finbreak.services.month_summary import MonthSummaryService
from finbreak.services.pdf_export import ExportOptions, PdfExportService
from finbreak.services.reporting import (
    MODE_SPECIFIC_MONTH,
    DrillLabels,
    ReportingService,
    ReportPrefs,
)

pytestmark = pytest.mark.features

_TODAY = date(2026, 1, 15)
_JAN = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=1)
_LABELS = DrillLabels(
    income="Income",
    spending="Spending",
    transfers="Transfers",
    uncategorised="Uncategorised",
    transfer_pair="{source} → {target}",
)


def _vault(paths, base: str) -> AuthService:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), base)
    return svc


@pytest.fixture
def mixed(paths) -> Iterator[tuple[AuthService, int, int]]:
    """A ZAR vault: the Default (ZAR) account and a USD one, each holding one
    January transaction of a different size."""
    svc = _vault(paths, "ZAR")
    accounts = AccountService(svc.vault)
    zar = accounts.list_accounts()[0].id
    usd = accounts.add_account("Offshore", "savings", currency="USD").id
    repo = TransactionRepository(svc.vault.connection)
    repo.add(zar, "2026-01-05", -10_000, "zar spend")
    repo.add(usd, "2026-01-06", -2_500, "usd spend")
    yield svc, zar, usd
    svc.lock()


# -- INV-6 ------------------------------------------------------------------ #
def test_INV6_scope_currency_in_a_mixed_vault(mixed) -> None:
    svc, zar, usd = mixed
    conn = svc.vault.connection
    assert scope_currency(conn, frozenset({zar})) == "ZAR"
    assert scope_currency(conn, frozenset({usd})) == "USD"
    assert scope_currency(conn, frozenset()) == "ZAR"
    with pytest.raises(MixedCurrencyError):
        scope_currency(conn, None)
    with pytest.raises(MixedCurrencyError):
        scope_currency(conn, frozenset({zar, usd}))


def test_INV6_none_reads_the_accounts_not_the_base(paths) -> None:
    """A ZAR vault whose only account is USD: ``None`` is USD."""
    svc = _vault(paths, "ZAR")
    try:
        accounts = AccountService(svc.vault)
        default = accounts.list_accounts()[0]
        accounts.update_account(
            default.id,
            default.name,
            default.type,
            account_number=None,
            note=None,
            bank=None,
            currency="USD",
        )
        assert scope_currency(svc.vault.connection, None) == "USD"
    finally:
        svc.lock()


def test_INV6_none_with_no_accounts_is_the_base(paths) -> None:
    svc = _vault(paths, "EUR")
    try:
        conn = svc.vault.connection
        conn.execute("DELETE FROM accounts")
        conn.commit()
        assert scope_currency(conn, None) == "EUR"
        assert vault_currencies(conn) == []
    finally:
        svc.lock()


def test_INV6_python_and_sql_read_a_stored_currency_alike(mixed) -> None:
    """``account_currency`` and transfer pairing's SQL read one stored value the
    same way, stray whitespace included (§ 4.3), so pairing and display agree."""
    svc, zar, _usd = mixed
    conn = svc.vault.connection
    for stored in (" USD ", "\tUSD", "USD\n", " \t ", ""):
        conn.execute("UPDATE accounts SET currency = ? WHERE id = ?", (stored, zar))
        sql = conn.execute(
            "SELECT COALESCE(NULLIF(TRIM(currency), ''), 'ZAR') FROM accounts "
            "WHERE id = ?",
            (zar,),
        ).fetchone()[0]
        assert account_currencies(conn)[zar] == sql, repr(stored)


def test_INV6_helpers_read_null_and_blank_as_base(mixed) -> None:
    svc, zar, usd = mixed
    conn = svc.vault.connection
    eur = AccountService(svc.vault).add_account("Euro", "savings", currency="EUR").id
    blank = AccountService(svc.vault).add_account("Blank", "savings").id
    conn.execute("UPDATE accounts SET currency = '  ' WHERE id = ?", (blank,))
    conn.execute("UPDATE accounts SET currency = NULL WHERE id = ?", (zar,))
    conn.commit()
    assert account_currencies(conn) == {
        zar: "ZAR",
        usd: "USD",
        eur: "EUR",
        blank: "ZAR",
    }
    assert vault_currencies(conn) == ["ZAR", "EUR", "USD"]
    assert accounts_in(conn, "ZAR") == frozenset({zar, blank})
    assert accounts_in(conn, "USD") == frozenset({usd})
    assert scope_currency(conn, frozenset({zar, blank})) == "ZAR"


def test_INV6_refusal_carries_a_user_message(mixed) -> None:
    from finbreak.errors import UserMessage

    svc, zar, usd = mixed
    with pytest.raises(MixedCurrencyError) as caught:
        scope_currency(svc.vault.connection, frozenset({zar, usd}))
    assert isinstance(caught.value.args[0], UserMessage)


# -- INV-7 ------------------------------------------------------------------ #
_REPORTING_CALLS = {
    "summary": lambda r, ids: r.summary(_JAN, ids, _TODAY),
    "spending_by_category": lambda r, ids: r.spending_by_category(_JAN, ids, _TODAY),
    "monthly_trend": lambda r, ids: r.monthly_trend(_JAN, ids, _TODAY),
    "drill_down": lambda r, ids: r.drill_down(_JAN, ids, _TODAY, labels=_LABELS),
}


@pytest.mark.parametrize("method", sorted(_REPORTING_CALLS))
def test_INV7_reporting_refuses_a_mixed_scope(mixed, method) -> None:
    svc, zar, usd = mixed
    call = _REPORTING_CALLS[method]
    reporting = ReportingService(svc.vault)
    for scope in (None, frozenset({zar, usd})):
        with pytest.raises(MixedCurrencyError):
            call(reporting, scope)
    assert call(reporting, frozenset({usd})) is not None


def test_INV7_reporting_single_scope_holds_only_its_rows(mixed) -> None:
    svc, zar, usd = mixed
    reporting = ReportingService(svc.vault)
    assert str(reporting.summary(_JAN, frozenset({usd}), _TODAY).expenditure) == "25.00"
    assert (
        str(reporting.summary(_JAN, frozenset({zar}), _TODAY).expenditure) == "100.00"
    )


def test_INV7_month_summary_refuses_a_mixed_scope(mixed) -> None:
    svc, zar, usd = mixed
    months = MonthSummaryService(svc.vault)
    for scope in (None, frozenset({zar, usd})):
        with pytest.raises(MixedCurrencyError):
            months.summary(_JAN, scope, _TODAY)
    months.summary(_JAN, frozenset({usd}), _TODAY)  # no raise


def _options(account_ids) -> ExportOptions:
    return ExportOptions(
        prefs=_JAN,
        account_ids=account_ids,
        include_summary=True,
        include_charts=False,
        include_transactions=True,
    )


def test_INV7_pdf_export_refuses_a_mixed_scope(qapp, mixed, tmp_path) -> None:
    svc, zar, usd = mixed
    pdf = PdfExportService(svc.vault)
    for scope in (None, frozenset({zar, usd})):
        with pytest.raises(MixedCurrencyError):
            pdf.render_pdf_bytes(_options(scope), _TODAY)
        with pytest.raises(MixedCurrencyError):
            pdf.export(_options(scope), tmp_path / "out.pdf", _TODAY)
    assert not (tmp_path / "out.pdf").exists()


def test_INV7_pdf_header_names_the_scope_currency(qapp, mixed) -> None:
    import pdfplumber

    svc, _zar, usd = mixed
    raw = PdfExportService(svc.vault).render_pdf_bytes(
        _options(frozenset({usd})), _TODAY
    )
    with pdfplumber.open(BytesIO(raw)) as doc:
        text = "\n".join(page.extract_text() or "" for page in doc.pages)
    assert "USD" in text
    assert "ZAR" not in text
