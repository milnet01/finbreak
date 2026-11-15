"""FIBR-0088 — schema v17 adds the ``imported_files`` table, once and atomically.

Enforces docs/specs/FIBR-0088-already-imported-check.md INV-9. A "v16 vault"
here is a fresh vault with v17's table and index dropped and its version record
set back to 16 — the pattern of ``tests/features/loan_sign/test_migration_v16.py``,
which also has to drop them now. Every vault uses tmp_path; every row is
synthetic (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import _PW, _acct, raising_conn
from finbreak.migrations import run_migrations
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _version(svc: AuthService) -> int:
    return svc.vault.connection.execute(
        "SELECT version FROM schema_version"
    ).fetchone()[0]


def _objects(svc: AuthService) -> set[str]:
    return {
        row[0]
        for row in svc.vault.connection.execute(
            "SELECT name FROM sqlite_master WHERE name IN "
            "('imported_files', 'idx_imported_files_sha256')"
        )
    }


def _rows(svc: AuthService) -> list[tuple]:
    conn = svc.vault.connection
    return conn.execute(
        "SELECT t.id, t.account_id, t.occurred_on, t.amount_minor, t.description, "
        "p.period_start, p.period_end, p.source_filename "
        "FROM transactions t JOIN statement_periods p ON p.id = t.statement_period_id "
        "ORDER BY t.id"
    ).fetchall()


@pytest.fixture
def v16(service) -> AuthService:
    """A vault holding one statement and its rows, set back to v16."""
    svc = service
    conn = svc.vault.connection
    acct = _acct(svc)
    period = StatementPeriodRepository(conn).add(
        acct, "2026-01-01", "2026-01-31", "jan.csv", 12_345
    )
    TransactionRepository(conn).add_batch(
        [(acct, "2026-01-05", -1_000, "Fake shop"), (acct, "2026-01-06", 500, "Fake")],
        period,
    )
    conn.commit()
    conn.execute("DROP INDEX idx_imported_files_sha256")
    conn.execute("DROP TABLE imported_files")
    conn.execute("UPDATE schema_version SET version = 16")
    conn.commit()
    return svc


def test_INV9_v17_creates_the_table_and_keeps_every_row(v16) -> None:
    before = _rows(v16)
    assert before and _objects(v16) == set()

    run_migrations(v16.vault.connection)

    assert _version(v16) == 17
    assert _objects(v16) == {"imported_files", "idx_imported_files_sha256"}
    assert _rows(v16) == before


def test_INV9_v17_failing_after_the_create_leaves_a_v16_vault(v16) -> None:
    before = _rows(v16)
    wedged = raising_conn(
        v16.vault.connection, "CREATE INDEX idx_imported_files", "injected failure"
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        run_migrations(wedged)

    assert _version(v16) == 16
    assert _objects(v16) == set(), "the CREATE TABLE was not rolled back"
    assert _rows(v16) == before
    run_migrations(v16.vault.connection)  # re-openable: the step runs clean
    assert _version(v16) == 17


def test_INV9_v17_runs_once(v16) -> None:
    run_migrations(v16.vault.connection)
    run_migrations(v16.vault.connection)  # at v17: no step runs

    assert _version(v16) == 17
    assert _objects(v16) == {"imported_files", "idx_imported_files_sha256"}
