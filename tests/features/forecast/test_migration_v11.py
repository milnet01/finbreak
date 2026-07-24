"""FIBR-0171 — schema v11 (`statement_periods.closing_balance_minor`) + the
`StatementPeriodRepository` reads/writes the forecast anchor rides on.

Enforces tests/features/forecast/spec.md INV-6/7/8/9/12/13 (persistence layer).
Every on-disk vault uses tmp_path; no test touches the network or real financial
data (testing.md § 6).
"""

import pytest

from conftest import (
    _PW,
    build_v9_vault,
    keyed_connection,
    raising_conn,
)
from finbreak.crypto import SALT_LEN
from finbreak.migrations import (
    LATEST_SCHEMA_VERSION,
    _migrate_to_v10,
    run_migrations,
)
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features


def _cols(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# INV-9 — the v10 -> v11 migration (additive, version-gated, atomic)
# --------------------------------------------------------------------------- #
def test_INV9_latest_schema_version_is_11() -> None:
    assert LATEST_SCHEMA_VERSION == 11


def test_INV9_v10_upgrades_to_v11_adding_closing_balance_column(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [("2026-01-01", -100, "a")])

    conn = keyed_connection(vault_path, salt)
    _migrate_to_v10(conn)  # take it to exactly v10
    assert "closing_balance_minor" not in _cols(conn, "statement_periods")
    # A pre-v11 statement_periods row (no closing-balance column yet).
    conn.execute(
        "INSERT INTO statement_periods"
        "(account_id, period_start, period_end, source_filename, imported_at) "
        "VALUES (1, '2026-01-01', '2026-01-31', 'old.csv', '2026-02-01T00:00:00+00:00')"
    )
    conn.commit()

    run_migrations(conn)  # v10 -> v11
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 11
    assert "closing_balance_minor" in _cols(conn, "statement_periods")
    # The old row is backfilled NULL (no historical balance to recover).
    assert (
        conn.execute(
            "SELECT closing_balance_minor FROM statement_periods"
        ).fetchone()[0]
        is None
    )
    conn.close()


def test_INV9_migration_is_idempotent_at_latest(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v9 -> v11
    run_migrations(conn)  # no-op at latest — never replays the ADD COLUMN
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 11
    conn.close()


def test_INV9_migration_is_atomic(paths) -> None:
    """A wedged v11 ALTER leaves a re-openable v10 with no column added."""
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)
    _migrate_to_v10(conn)  # at v10, ready for the wedged v11 step

    with pytest.raises(RuntimeError):
        run_migrations(
            raising_conn(conn, "closing_balance_minor", "injected ALTER failure")
        )
    # Rolled back: still v10, no column.
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    assert "closing_balance_minor" not in _cols(conn, "statement_periods")
    conn.close()


def test_INV2a_first_run_vault_carries_the_column(service) -> None:
    assert "closing_balance_minor" in _cols(
        service.vault.connection, "statement_periods"
    )


# --------------------------------------------------------------------------- #
# INV-7 / INV-8 — repository round-trip (add / get)
# --------------------------------------------------------------------------- #
def test_INV7_add_persists_the_closing_balance_and_get_round_trips(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)
    pid = repo.add(acct, "2026-06-01", "2026-06-30", "june.pdf", 860_000)
    conn.commit()
    got = repo.get(pid)
    assert got is not None
    assert got.closing_balance_minor == 860_000


def test_INV8_add_without_balance_stores_null(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)
    pid = repo.add(acct, "2026-06-01", "2026-06-30", "savings.pdf")
    conn.commit()
    got = repo.get(pid)
    assert got is not None
    assert got.closing_balance_minor is None


# --------------------------------------------------------------------------- #
# INV-12 — update_closing_balance is FILL-ONLY
# --------------------------------------------------------------------------- #
def test_INV12_update_fills_a_null_balance(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)
    pid = repo.add(acct, "2026-06-01", "2026-06-30", "csv-first.csv")  # NULL
    conn.commit()
    repo.update_closing_balance(pid, 500_000)
    conn.commit()
    assert repo.get(pid).closing_balance_minor == 500_000


def test_INV12_update_never_overwrites_a_nonnull_balance(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)
    pid = repo.add(acct, "2026-06-01", "2026-06-30", "pdf.pdf", 860_000)
    conn.commit()
    repo.update_closing_balance(pid, 999_999)  # a different value — must be ignored
    conn.commit()
    assert repo.get(pid).closing_balance_minor == 860_000, "fixed for the span"


# --------------------------------------------------------------------------- #
# INV-6 — latest_closing_balances: latest non-NULL row per account
# --------------------------------------------------------------------------- #
def test_INV6_latest_closing_balances_picks_greatest_period_end_nonnull(
    service,
) -> None:
    conn = service.vault.connection
    accounts = AccountService(service.vault)
    a = accounts.list_accounts()[0].id
    b = accounts.add_account("Savings", "savings").id
    repo = StatementPeriodRepository(conn)

    # Account A: two balance-bearing statements — the later period_end wins.
    repo.add(a, "2026-05-01", "2026-05-31", "may.pdf", 100_000)
    repo.add(a, "2026-06-01", "2026-06-30", "june.pdf", 120_000)
    # A NULL-balance later statement must NOT shadow the June balance.
    repo.add(a, "2026-07-01", "2026-07-31", "july.csv")  # NULL
    # Account B: one balance.
    repo.add(b, "2026-06-15", "2026-07-15", "b.pdf", 30_000)
    conn.commit()

    latest = dict((acct, (bal, end)) for acct, bal, end in repo.latest_closing_balances())
    assert latest[a] == (120_000, "2026-06-30")
    assert latest[b] == (30_000, "2026-07-15")


def test_INV6_account_with_only_null_balances_is_absent(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)
    repo.add(acct, "2026-06-01", "2026-06-30", "csv-only.csv")  # NULL
    conn.commit()
    assert [row for row in repo.latest_closing_balances() if row[0] == acct] == []


def test_INV6_tie_on_period_end_breaks_on_greatest_id(service) -> None:
    conn = service.vault.connection
    acct = AccountService(service.vault).list_accounts()[0].id
    repo = StatementPeriodRepository(conn)
    repo.add(acct, "2026-06-01", "2026-06-30", "first.pdf", 111_000)
    repo.add(acct, "2026-06-05", "2026-06-30", "second.pdf", 222_000)  # same end, later id
    conn.commit()
    latest = dict(
        (a, bal) for a, bal, _end in repo.latest_closing_balances() if a == acct
    )
    assert latest[acct] == 222_000
