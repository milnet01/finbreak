"""FIBR-0177 — `StatementPeriodRepository.closing_balances_for_account` (INV-3).

The load-bearing ordering falsifier, mirroring FIBR-0171's `latest_closing_balances`
repo test: only `closing_balance_minor IS NOT NULL` rows are returned, ordered
`(period_end, id)` ascending; a NULL-closing period is excluded; two rows sharing a
`period_end` are ordered by `id`. A real (tmp_path) v11 vault; no network, no real
financial data (testing.md § 6).
"""

from collections.abc import Iterator

import pytest

from conftest import _PW
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # migrates straight to v11
    yield svc
    svc.lock()


def test_INV3_returns_only_nonnull_closings_ordered_ascending(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)

    # Insert deliberately OUT of period_end order so ORDER BY, not insert order,
    # is what fixes the sequence.
    repo.add(acct, "2026-03-01", "2026-03-31", "mar.pdf", 130_000)
    repo.add(acct, "2026-01-01", "2026-01-31", "jan.pdf", 100_000)
    repo.add(acct, "2026-02-01", "2026-02-28", "feb.csv")  # NULL closing — excluded
    repo.add(acct, "2026-02-01", "2026-02-28", "feb.pdf", 115_000)
    conn.commit()

    chain = repo.closing_balances_for_account(acct)
    # NULL-closing Feb CSV excluded; the rest ascending by period_end.
    assert chain == [
        ("2026-01-31", 100_000),
        ("2026-02-28", 115_000),
        ("2026-03-31", 130_000),
    ]


def test_INV3_same_period_end_ordered_by_id(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)

    # Two balance-bearing statements sharing a period_end — the tie breaks on id
    # (insert order), ascending.
    repo.add(acct, "2026-06-01", "2026-06-30", "first.pdf", 111_000)
    repo.add(
        acct, "2026-06-05", "2026-06-30", "second.pdf", 222_000
    )  # same end, later id
    conn.commit()

    chain = repo.closing_balances_for_account(acct)
    assert chain == [("2026-06-30", 111_000), ("2026-06-30", 222_000)]


def test_INV3_account_with_no_balances_is_empty(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)
    repo.add(acct, "2026-06-01", "2026-06-30", "csv-only.csv")  # NULL
    conn.commit()
    assert repo.closing_balances_for_account(acct) == []
