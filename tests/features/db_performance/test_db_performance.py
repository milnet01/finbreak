"""FIBR-0098 / FIBR-0071 / FIBR-0026 (hot-column indexes, schema v10) +
FIBR-0025 (SQLite WAL journal mode on the live vault).

Enforces tests/features/db_performance/spec.md. Every on-disk vault uses
tmp_path; no test touches the network or real financial data (testing.md § 6).
"""

import pytest

from conftest import (
    _PW,
    _params,
    build_v9_vault,
    keyed_connection,
    raising_conn,
)
from finbreak.crypto import SALT_LEN, derive_key
from finbreak.migrations import LATEST_SCHEMA_VERSION, run_migrations
from finbreak.repositories.transactions import TransactionRepository
from finbreak.repositories.transfers import (
    CANDIDATE_PAIRS_SQL,
    TRANSFER_WINDOW_DAYS,
)
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.vault import Vault

pytestmark = pytest.mark.features

# The perf indexes a vault carries once it has walked to LATEST: the five the
# v9->v10 migration creates (FIBR-0098/0071/0026), plus the transfer-candidate
# index added at v13->v14 (FIBR-0327).
_V10_INDEXES = {
    "idx_transactions_account_date_amount",
    "idx_transactions_occurred_on",
    "idx_transactions_category_id",
    "idx_transactions_statement_period_id",
    "idx_categorization_rules_category_id",
}
_EXPECTED_INDEXES = _V10_INDEXES | {"idx_transactions_amount_date"}


def _index_names(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
    }


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# INV-1 — schema v10 + the v9->v10 migration
# --------------------------------------------------------------------------- #
def test_INV1_latest_schema_version_is_14() -> None:
    assert LATEST_SCHEMA_VERSION == 14


def test_INV1_v9_upgrades_to_v10_adding_indexes(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [("2026-01-01", -100, "a")])

    conn = keyed_connection(vault_path, salt)
    assert _index_names(conn) == set(), "v9 ships no indexes"
    run_migrations(conn)  # v9 -> v10 (walks to LATEST)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 14
    assert _index_names(conn) == _EXPECTED_INDEXES
    # Pure-DDL step: the row survives untouched (no backfill).
    assert conn.execute("SELECT count(*) FROM transactions").fetchone()[0] == 1
    conn.close()


def test_INV1_migration_is_atomic(paths) -> None:
    """A wedged v10 step leaves a re-openable v9 with no partial indexes — the five
    CREATE INDEXes + UPDATE schema_version share one owned transaction."""
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)

    with pytest.raises(RuntimeError):
        run_migrations(
            raising_conn(
                conn,
                "idx_categorization_rules_category_id",  # the last CREATE INDEX
                "injected failure mid-index-build",
            )
        )
    # Rolled back: still v9, and not one index left behind.
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 9
    assert _index_names(conn) == set()
    conn.close()


def test_INV1_idempotent_at_latest(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v9 -> v10
    run_migrations(conn)  # no-op at latest — no duplicate indexes
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 14
    assert _index_names(conn) == _EXPECTED_INDEXES
    conn.close()


# --------------------------------------------------------------------------- #
# INV-2 — the indexes exist on a fresh vault and are actually used
# --------------------------------------------------------------------------- #
def test_INV2_first_run_vault_carries_all_perf_indexes(service) -> None:
    assert _index_names(service.vault.connection) == _EXPECTED_INDEXES


def test_INV2_dedup_lookup_uses_the_composite_index(service) -> None:
    plan = service.vault.connection.execute(
        "EXPLAIN QUERY PLAN SELECT description FROM transactions "
        "WHERE account_id = 1 AND occurred_on = '2026-01-01' AND amount_minor = -100"
    ).fetchall()
    detail = " ".join(str(row[-1]) for row in plan)
    assert "idx_transactions_account_date_amount" in detail
    assert "SCAN" not in detail.upper()  # a search via the index, not a table scan


# --------------------------------------------------------------------------- #
# INV-3 — WAL on the live connection, rollback on the transient one
# --------------------------------------------------------------------------- #
def test_INV3_created_vault_is_wal(service) -> None:
    mode = service.vault.connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_INV3_live_open_converts_pre_wal_vault(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [])  # built raw -> rollback journal
    vault = Vault(vault_path, sidecar)
    vault.open(derive_key(bytearray(_PW), salt, _params(salt)))
    mode = vault.connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    vault.close()


def test_INV3_transient_restore_connection_stays_rollback(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [])  # rollback journal, never WAL
    vault = Vault(vault_path, sidecar)
    vault.open(derive_key(bytearray(_PW), salt, _params(salt)), in_memory_temp=True)
    mode = vault.connection.execute("PRAGMA journal_mode").fetchone()[0]
    # The backup/restore-assembly connection keeps the self-contained rollback
    # journal — backup._install moves vault.db without its -wal sidecar (INV-3).
    assert mode.lower() != "wal"
    vault.close()


# --------------------------------------------------------------------------- #
# INV-4 — WAL data durability across a graceful close/reopen
# --------------------------------------------------------------------------- #
def test_INV4_wal_vault_data_survives_close_reopen(paths) -> None:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    account_id = AccountService(svc.vault).list_accounts()[0].id
    TransactionRepository(svc.vault.connection).add(
        account_id, "2026-01-01", -12345, "coffee"
    )
    svc.lock()  # graceful close -> SQLite checkpoints the WAL into vault.db

    svc.unlock(bytearray(_PW))
    rows = TransactionRepository(svc.vault.connection).list_all()
    assert [r.amount_minor for r in rows] == [-12345]
    svc.lock()


# --------------------------------------------------------------------------- #
# INV-5 — the transfer-candidate self-join seeks an index (FIBR-0327)
# --------------------------------------------------------------------------- #
def _plan(conn, sql: str, params) -> list[str]:
    return [row[-1] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


def test_INV5_candidate_pairs_seeks_the_amount_date_index(service) -> None:
    """FIBR-0327 — the candidate self-join matches equal-magnitude opposite-sign
    rows across accounts inside a day window, on a tab the user opens routinely.

    No index served it: the v10 composite leads with ``account_id``, so an
    equality on ``amount_minor`` alone cannot seek it. SQLite's fallback is to
    build an AUTOMATIC index over the whole table on every call -- which is why
    the assertion is on the PLAN and not on a wall-clock time, and why the
    absence of "AUTOMATIC" is asserted as well as the presence of the index. A
    plan can name the right index for one arm and still build a transient one for
    the other.
    """
    plan = _plan(
        service.vault.connection,
        CANDIDATE_PAIRS_SQL,
        {"window": TRANSFER_WINDOW_DAYS},
    )
    joined = "\n".join(plan)

    assert "idx_transactions_amount_date" in joined, (
        "the candidate self-join must seek the v14 amount/date index.\n"
        f"  actual plan:\n{joined}"
    )
    assert "AUTOMATIC" not in joined, (
        "SQLite is still building a transient index for this join, which is the "
        "whole-table cost FIBR-0327 removed. Either the index is missing or a "
        "predicate has been wrapped in a function again.\n"
        f"  actual plan:\n{joined}"
    )
    assert "amount_minor=? AND occurred_on>?" in joined, (
        "the day window must narrow the seek, not just filter after it. "
        "Wrapping occurred_on in julianday() hides the column from the index: "
        "the plan still names the index and still says amount_minor=?, so the "
        "two assertions above BOTH pass while every same-amount row in the vault "
        "is read. Only the range terms tell the two apart.\n"
        f"  actual plan:\n{joined}"
    )
