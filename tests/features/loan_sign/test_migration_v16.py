"""FIBR-0467 — schema v16 corrects the sign of stored Home Loan rows, once.

Enforces docs/specs/FIBR-0467-home-loan-sign.md INV-4 to INV-7. A "v15 vault"
here is a fresh vault with its version record set back to 15: v16 is data-only,
so the two schemas are the same shape. Every on-disk vault uses tmp_path, and
every row is synthetic (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import _PW, raising_conn
from finbreak.importers.standard_bank import StandardBankImporter
from finbreak.migrations import run_migrations
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.repositories.transfers import TransferRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService

pytestmark = pytest.mark.features

_HOMELOAN_PDF = (
    Path(__file__).parents[1]
    / "standard_bank_pdf"
    / "fixtures"
    / "family_b_homeloan.pdf"
)


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _account(svc: AuthService, name: str, type_: str) -> int:
    return AccountService(svc.vault).add_account(name, type_).id


def _period(svc: AuthService, account: int, filename: str, closing: int | None) -> int:
    conn = svc.vault.connection
    pid = StatementPeriodRepository(conn).add(
        account, "2025-03-01", "2025-03-31", filename, closing
    )
    conn.commit()
    return pid


def _row(svc: AuthService, account: int, amount: int, period: int | None) -> int:
    conn = svc.vault.connection
    txn = TransactionRepository(conn).add(account, "2025-03-05", amount, "Fake row")
    if period is not None:
        conn.execute(
            "UPDATE transactions SET statement_period_id = ? WHERE id = ?",
            (period, txn),
        )
        conn.commit()
    return txn


def _amount(svc: AuthService, txn: int) -> int:
    return svc.vault.connection.execute(
        "SELECT amount_minor FROM transactions WHERE id = ?", (txn,)
    ).fetchone()[0]


def _version(svc: AuthService) -> int:
    return svc.vault.connection.execute(
        "SELECT version FROM schema_version"
    ).fetchone()[0]


def _back_to_v15(svc: AuthService) -> None:
    conn = svc.vault.connection
    conn.execute("UPDATE schema_version SET version = 15")
    conn.commit()


@pytest.fixture
def v15(service):
    """One row per INV-4 case, plus the INV-6 pairs, on a vault at v15."""
    svc = service
    loan = _account(svc, "Home loan", "home_loan")
    current = _account(svc, "Cheque", "current")
    savings = _account(svc, "Savings", "savings")

    loan_pdf = _period(svc, loan, "STATEMENT.PDF", 75_000)  # upper-case suffix
    loan_pdf_no_closing = _period(svc, loan, "other.pdf", None)
    loan_csv = _period(svc, loan, "export.csv", 75_000)
    current_pdf = _period(svc, current, "cheque.pdf", 10_000)

    rows = {
        "selected": _row(svc, loan, 5_000, loan_pdf),
        "no_closing": _row(svc, loan, 5_000, loan_pdf_no_closing),
        "csv": _row(svc, loan, 5_000, loan_csv),
        "manual": _row(svc, loan, 5_000, None),
        "current": _row(svc, current, 5_000, current_pdf),
        # INV-6: a confirmed repayment pair, loan leg +500 before the upgrade.
        "paired_loan": _row(svc, loan, 50_000, loan_pdf),
        "paired_current": _row(svc, current, -50_000, None),
        # INV-6: a confirmed pair touching no selected row.
        "other_out": _row(svc, current, -70_000, None),
        "other_in": _row(svc, savings, 70_000, None),
        # INV-6: a rejected pair touching a selected row.
        "rejected_loan": _row(svc, loan, 20_000, loan_pdf),
        "rejected_current": _row(svc, current, -20_000, None),
    }
    transfers = TransferRepository(svc.vault.connection)
    pairs = {
        "repayment": transfers.add_decision(
            rows["paired_loan"], rows["paired_current"], "confirmed"
        ),
        "unrelated": transfers.add_decision(
            rows["other_out"], rows["other_in"], "confirmed"
        ),
        "rejected": transfers.add_decision(
            rows["rejected_loan"], rows["rejected_current"], "rejected"
        ),
    }
    _back_to_v15(svc)
    return svc, rows, pairs


def _pair_ids(svc: AuthService) -> set[int]:
    return {r[0] for r in svc.vault.connection.execute("SELECT id FROM transfer_pairs")}


# --------------------------------------------------------------------------- #
# INV-4 — exactly the selected rows are negated
# --------------------------------------------------------------------------- #
def test_INV4_v16_negates_exactly_the_family_b_rows(v15) -> None:
    svc, rows, _ = v15
    before = {name: _amount(svc, txn) for name, txn in rows.items()}

    run_migrations(svc.vault.connection)

    negated = {"selected", "paired_loan", "rejected_loan"}
    for name, txn in rows.items():
        expected = -before[name] if name in negated else before[name]
        assert _amount(svc, txn) == expected, name


# --------------------------------------------------------------------------- #
# INV-5 — all-or-nothing, and once
# --------------------------------------------------------------------------- #
def test_INV5_v16_failing_after_the_update_changes_nothing(v15) -> None:
    svc, rows, _ = v15
    before = {txn: _amount(svc, txn) for txn in rows.values()}
    wedged = raising_conn(
        svc.vault.connection, "DELETE FROM transfer_pairs", "injected failure"
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        run_migrations(wedged)

    assert _version(svc) == 15
    assert {txn: _amount(svc, txn) for txn in rows.values()} == before


def test_INV5_v16_runs_once(v15) -> None:
    svc, rows, _ = v15
    run_migrations(svc.vault.connection)
    after_first = _amount(svc, rows["selected"])
    run_migrations(svc.vault.connection)  # at v16: no step runs

    assert after_first == -5_000
    assert _amount(svc, rows["selected"]) == -5_000


# --------------------------------------------------------------------------- #
# INV-6 — every confirmed pair is still a pair of opposites
# --------------------------------------------------------------------------- #
def test_INV6_v16_deletes_confirmed_pairs_it_made_same_signed(v15) -> None:
    svc, _, pairs = v15

    run_migrations(svc.vault.connection)

    assert _pair_ids(svc) == {pairs["unrelated"], pairs["rejected"]}
    same_signed = svc.vault.connection.execute(
        "SELECT count(*) FROM transfer_pairs p "
        "JOIN transactions a ON a.id = p.txn_a_id "
        "JOIN transactions b ON b.id = p.txn_b_id "
        "WHERE p.status = 'confirmed' AND a.amount_minor <> -b.amount_minor"
    ).fetchone()[0]
    assert same_signed == 0


# --------------------------------------------------------------------------- #
# INV-7 — re-importing the statement after the upgrade adds nothing
# --------------------------------------------------------------------------- #
def test_INV7_reimport_after_v16_is_all_duplicates(service) -> None:
    svc = service
    loan = _account(svc, "Home loan", "home_loan")
    parsed = StandardBankImporter().parse(_HOMELOAN_PDF.read_bytes(), 2, None)
    assert parsed is not None and parsed.period_start and parsed.period_end
    # What the pre-FIBR-0467 parser stored for this fixture.
    old_amounts = [5_000, -30_000]
    assert len(parsed.drafts) == len(old_amounts)

    conn = svc.vault.connection
    period = StatementPeriodRepository(conn).add(
        loan,
        parsed.period_start,
        parsed.period_end,
        _HOMELOAN_PDF.name,
        parsed.closing_balance_minor,
    )
    TransactionRepository(conn).add_batch(
        [
            (loan, d.occurred_on, old, d.description)
            for d, old in zip(parsed.drafts, old_amounts, strict=True)
        ],
        period,
    )
    conn.commit()
    _back_to_v15(svc)

    run_migrations(conn)
    preview = ImportService(svc.vault).preview_result(parsed, loan)

    assert preview.new_count == 0
    assert preview.duplicate_count == len(old_amounts)
