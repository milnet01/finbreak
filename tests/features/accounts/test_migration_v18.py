"""FIBR-0283 — schema v18 (the nullable ``accounts.bank`` column).

Enforces docs/specs/FIBR-0283-bank-field-on-accounts.md INV-1 (a v17 vault
upgrades in place, gaining exactly that one nullable column, every existing
row unchanged) and INV-2 (a failure inside the step leaves v17, and a re-run
upgrades). Modelled on ``test_migration_v13.py``. A "v17 vault" is a fresh
vault with ``bank`` dropped and its version set back to 17, the pattern of
``tests/features/already_imported/test_migration_v17.py``. Every vault uses
tmp_path; every row is synthetic (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import _PW, _acct, raising_conn
from finbreak.migrations import _MIGRATIONS, LATEST_SCHEMA_VERSION, run_migrations
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features

_ROW = "SELECT id, name, type, created_at, account_number, note FROM accounts"


def _cols(conn) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}


def _notnull(conn) -> dict[str, int]:
    return {r[1]: r[3] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}


def _version(conn) -> int:
    return conn.execute("SELECT version FROM schema_version").fetchone()[0]


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


@pytest.fixture
def v17(service):
    """A vault holding an account with every optional field filled, set back
    to v17. Distinct values in each column are what show a row was left alone.
    """
    conn = service.vault.connection
    acct = _acct(service)
    conn.execute(
        "UPDATE accounts SET account_number = ?, note = ?, "
        "statement_pdf_password = ? WHERE id = ?",
        ("000111", "a synthetic note", "synthetic-pdf-pw", acct),
    )
    conn.commit()
    if "bank" in _cols(conn):
        conn.execute("ALTER TABLE accounts DROP COLUMN bank")
    # v19 (FIBR-0087) adds a column, so the re-run would fail on its ALTER.
    if "currency" in _cols(conn):
        conn.execute("ALTER TABLE accounts DROP COLUMN currency")
    conn.execute("UPDATE schema_version SET version = 17")
    conn.commit()
    return conn


def test_INV1_v17_vault_gains_exactly_a_nullable_bank(v17) -> None:
    before_cols = _cols(v17)
    before_rows = v17.execute(_ROW + " ORDER BY id").fetchall()
    assert "bank" not in before_cols

    run_migrations(v17)

    assert _version(v17) == LATEST_SCHEMA_VERSION
    # The walk runs to latest, so v19's ``currency`` (FIBR-0087) arrives too.
    assert _cols(v17) == before_cols | {"bank", "currency"}
    assert _notnull(v17)["bank"] == 0
    assert v17.execute(_ROW + " ORDER BY id").fetchall() == before_rows
    banks = v17.execute("SELECT bank FROM accounts").fetchall()
    assert banks and all(bank is None for (bank,) in banks)
    assert v17.execute(
        "SELECT statement_pdf_password FROM accounts WHERE account_number = '000111'"
    ).fetchone() == ("synthetic-pdf-pw",)


def test_INV1_v18_is_registered() -> None:
    """``>=``, not ``==``: a later step is not a breach of this one (the
    FIBR-0327 lesson recorded in ``test_migration_v13.py``)."""
    assert 18 in _MIGRATIONS
    assert LATEST_SCHEMA_VERSION >= 18


def test_INV2_failed_step_leaves_v17_and_a_rerun_upgrades(v17) -> None:
    """The failure is injected on the version stamp, the step's LAST statement,
    so only the transaction can undo the ALTER that ran before it."""
    with pytest.raises(RuntimeError):
        run_migrations(raising_conn(v17, "SET version = 18", "injected stamp failure"))

    assert _version(v17) == 17
    assert "bank" not in _cols(v17)

    run_migrations(v17)

    assert _version(v17) == LATEST_SCHEMA_VERSION
    assert "bank" in _cols(v17)
