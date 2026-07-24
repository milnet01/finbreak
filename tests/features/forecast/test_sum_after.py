"""FIBR-0171 — `TransactionRepository.sum_after` (the anchor roll-forward read).

The forecast brings each account's statement balance current to today by adding
its actual transactions in the half-open window `(period_end, today]`
(spec D1/INV-13): strictly after `after_date`, no later than `up_to`.

Enforces tests/features/forecast/spec.md INV-13. tmp_path only; no network.
"""

import pytest

from conftest import _PW
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def test_INV13_sum_after_is_a_half_open_window(service) -> None:
    conn = service.vault.connection
    a = AccountService(service.vault).list_accounts()[0].id
    b = AccountService(service.vault).add_account("Other", "current").id
    repo = TransactionRepository(conn)
    repo.add(a, "2026-06-30", 5_000, "on period_end — EXCLUDED (already in balance)")
    repo.add(a, "2026-07-01", 10_000, "in window")
    repo.add(a, "2026-07-15", -2_000, "in window")
    repo.add(a, "2026-07-24", 700, "on up_to — INCLUDED")
    repo.add(a, "2026-07-25", 999, "after up_to — EXCLUDED")
    repo.add(b, "2026-07-10", 4_000, "other account — EXCLUDED")

    total, count = repo.sum_after(a, "2026-06-30", "2026-07-24")
    assert total == 10_000 - 2_000 + 700
    assert count == 3


def test_INV13_sum_after_zero_rows_is_zero_zero(service) -> None:
    conn = service.vault.connection
    a = AccountService(service.vault).list_accounts()[0].id
    repo = TransactionRepository(conn)
    # A freshly-imported statement: nothing dated after its period_end yet.
    assert repo.sum_after(a, "2026-07-31", "2026-08-15") == (0, 0)
