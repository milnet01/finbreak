"""FIBR-0177 — `ReconciliationService.account_statuses` over a real vault.

Enforces tests/features/reconciliation/spec.md INV-1/2/3/4/5/7/10/11 + the total-map
contract (INV-9). A real (tmp_path) v11 vault; no network, no real financial data
(testing.md § 6). The INV-10 gap test is written reproduce-first (RED before the
service exists).
"""

from collections.abc import Iterator

import pytest

from conftest import _PW
from finbreak.models import ReconciliationStatus
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.reconciliation import ReconciliationService

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # migrates straight to v11
    yield svc
    svc.lock()


def _default_id(svc: AuthService) -> int:
    return AccountService(svc.vault).list_accounts()[0].id


def _add_statement(
    svc: AuthService,
    account_id: int,
    period_start: str,
    period_end: str,
    filename: str,
    closing_minor: int | None,
) -> None:
    repo = StatementPeriodRepository(svc.vault.connection)
    repo.add(account_id, period_start, period_end, filename, closing_minor)
    svc.vault.connection.commit()


def _add_txn(
    svc: AuthService, account_id: int, day: str, minor: int, desc: str
) -> None:
    TransactionRepository(svc.vault.connection).add(account_id, day, minor, desc)


# --------------------------------------------------------------------------- #
# INV-1 / INV-2 — reconciled current account; half-open boundary rows
# --------------------------------------------------------------------------- #
def test_INV1_INV2_current_account_reconciles_with_boundary_rows(service) -> None:
    svc = service
    a = _default_id(svc)  # seeded Default is a 'current' account

    # Two balance-bearing statements: C_prev 500_000 @ 2026-04-30, C_curr 550_000
    # @ 2026-05-31. The bridge (2026-04-30, 2026-05-31] must sum to 50_000.
    _add_statement(svc, a, "2026-01-01", "2026-04-30", "apr.pdf", 500_000)
    _add_statement(svc, a, "2026-05-01", "2026-05-31", "may.pdf", 550_000)

    _add_txn(svc, a, "2026-05-15", 30_000, "mid")
    _add_txn(svc, a, "2026-05-31", 20_000, "on P_curr — INCLUDED")  # boundary: counts
    # Boundary falsifier: a row dated ON P_prev is already inside C_prev, so it must
    # be EXCLUDED. If the window were closed-closed this 99_999 would break the bridge.
    _add_txn(svc, a, "2026-04-30", 99_999, "on P_prev — EXCLUDED")

    recon = ReconciliationService(svc.vault).account_statuses()[a]
    assert recon.status is ReconciliationStatus.RECONCILED
    assert recon.discrepancy_minor == 0
    assert recon.off_pair_count == 0
    assert recon.checked_pair_count == 1


# --------------------------------------------------------------------------- #
# INV-5 — non-cash types are NOT_SUPPORTED regardless of data
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("acct_type", ["credit_card", "home_loan"])
def test_INV5_debt_types_are_not_supported(service, acct_type) -> None:
    svc = service
    debt = AccountService(svc.vault).add_account(f"debt-{acct_type}", acct_type).id
    # Give it data that WOULD reconcile if the asset identity were (wrongly) applied.
    _add_statement(svc, debt, "2026-01-01", "2026-04-30", "s1.pdf", 100_000)
    _add_statement(svc, debt, "2026-05-01", "2026-05-31", "s2.pdf", 150_000)
    _add_txn(svc, debt, "2026-05-10", 50_000, "would bridge")

    recon = ReconciliationService(svc.vault).account_statuses()[debt]
    assert recon.status is ReconciliationStatus.NOT_SUPPORTED
    assert recon.discrepancy_minor == 0
    assert recon.off_pair_count == 0
    assert recon.checked_pair_count == 0


# --------------------------------------------------------------------------- #
# INV-3 — a NULL-closing statement is not a node, but its txns still bridge
# --------------------------------------------------------------------------- #
def test_INV3_null_closing_statement_skipped_as_node_txns_still_bridge(service) -> None:
    svc = service
    a = _default_id(svc)

    _add_statement(svc, a, "2026-01-01", "2026-04-30", "apr.pdf", 100_000)
    # A CSV import in the middle with NO closing balance — NOT a chain node.
    _add_statement(svc, a, "2026-05-01", "2026-05-15", "mid.csv", None)
    _add_statement(svc, a, "2026-05-16", "2026-05-31", "may.pdf", 130_000)

    # The CSV's transaction (dated inside its coverage) still bridges the two
    # balance-bearing nodes: (2026-04-30, 2026-05-31] sums to 30_000.
    _add_txn(svc, a, "2026-05-10", 30_000, "csv row")

    recon = ReconciliationService(svc.vault).account_statuses()[a]
    assert recon.status is ReconciliationStatus.RECONCILED
    assert recon.checked_pair_count == 1  # only the two non-NULL nodes make a pair


# --------------------------------------------------------------------------- #
# INV-10 / INV-7 — a dropped intervening period → OFF with exact rollup fields
# --------------------------------------------------------------------------- #
def test_INV10_dropped_period_is_off_with_exact_rollup(service) -> None:
    svc = service
    a = _default_id(svc)

    # Three balance-bearing statements. Pair0 bridges exactly; pair1's period had
    # its transactions never imported (the gap), so it is OFF.
    _add_statement(svc, a, "2026-01-01", "2026-03-31", "q1.pdf", 100_000)
    _add_statement(svc, a, "2026-04-01", "2026-04-30", "apr.pdf", 150_000)
    _add_statement(svc, a, "2026-05-01", "2026-05-31", "may.pdf", 210_000)

    # Pair0 (2026-03-31, 2026-04-30] = 50_000 → reconciles (150_000 == 100_000+50_000).
    _add_txn(svc, a, "2026-04-15", 50_000, "april salary")
    # Pair1 (2026-04-30, 2026-05-31]: NO transactions imported → bridge 0 → expected
    # 150_000, actual 210_000 → diff +60_000.

    recon = ReconciliationService(svc.vault).account_statuses()[a]
    assert recon.status is ReconciliationStatus.OFF
    assert recon.discrepancy_minor == 60_000  # C_curr - (C_prev + bridge), signed
    assert recon.off_pair_count == 1
    assert recon.checked_pair_count == 2


# --------------------------------------------------------------------------- #
# INV-11 — transactions from any source count inside the bridge
# --------------------------------------------------------------------------- #
def test_INV11_mixed_source_transactions_bridge(service) -> None:
    svc = service
    a = _default_id(svc)

    _add_statement(svc, a, "2026-01-01", "2026-04-30", "apr.ofx", 200_000)
    _add_statement(svc, a, "2026-05-01", "2026-05-31", "may.pdf", 275_000)

    # Several transactions in the bridge window from (notionally) different imports;
    # they simply sum: 40_000 + 20_000 + 15_000 = 75_000 == 275_000 - 200_000.
    _add_txn(svc, a, "2026-05-03", 40_000, "csv row")
    _add_txn(svc, a, "2026-05-12", 20_000, "ofx row")
    _add_txn(svc, a, "2026-05-28", 15_000, "manual row")

    recon = ReconciliationService(svc.vault).account_statuses()[a]
    assert recon.status is ReconciliationStatus.RECONCILED


# --------------------------------------------------------------------------- #
# INV-4 — fewer than two balance-bearing statements → NOT_ENOUGH_DATA
# --------------------------------------------------------------------------- #
def test_INV4_savings_with_single_statement_is_not_enough_data(service) -> None:
    svc = service
    savings = AccountService(svc.vault).add_account("Savings", "savings").id
    _add_statement(svc, savings, "2026-01-01", "2026-04-30", "apr.ofx", 100_000)

    recon = ReconciliationService(svc.vault).account_statuses()[savings]
    assert recon.status is ReconciliationStatus.NOT_ENOUGH_DATA
    assert recon.discrepancy_minor == 0
    assert recon.off_pair_count == 0
    assert recon.checked_pair_count == 0


def test_INV4_account_with_zero_statements_is_not_enough_data(service) -> None:
    svc = service
    fresh = AccountService(svc.vault).add_account("Fresh", "current").id
    recon = ReconciliationService(svc.vault).account_statuses()[fresh]
    assert recon == recon.__class__(
        fresh, ReconciliationStatus.NOT_ENOUGH_DATA, 0, 0, 0
    )


# --------------------------------------------------------------------------- #
# INV-9 (contract) — account_statuses is a TOTAL map (one entry per account)
# --------------------------------------------------------------------------- #
def test_INV9_account_statuses_is_a_total_map(service) -> None:
    svc = service
    accounts = AccountService(svc.vault)
    default_id = _default_id(svc)  # current, no statements → NOT_ENOUGH_DATA
    savings_id = accounts.add_account("Savings", "savings").id  # NOT_ENOUGH_DATA
    card_id = accounts.add_account("Card", "credit_card").id  # NOT_SUPPORTED

    statuses = ReconciliationService(svc.vault).account_statuses()
    assert set(statuses) == {default_id, savings_id, card_id}
    assert statuses[card_id].status is ReconciliationStatus.NOT_SUPPORTED
    assert statuses[savings_id].status is ReconciliationStatus.NOT_ENOUGH_DATA
