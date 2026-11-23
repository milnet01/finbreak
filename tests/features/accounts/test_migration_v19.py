"""FIBR-0087 — schema v19 (the backfilled ``accounts.currency`` column).

Enforces docs/specs/FIBR-0087-per-account-currency.md INV-1 (a v18 vault
upgrades in place, gaining exactly that one column, every existing row reading
the vault's base currency with its other values unchanged; a new vault's
Default account reads the first-run currency) and INV-2 (a failure inside the
step leaves v18, and a re-run upgrades). Modelled on ``test_migration_v18.py``.
A "v18 vault" is a fresh vault with ``currency`` dropped and its version set
back to 18. Every vault uses tmp_path; every row is synthetic (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import _PW, _acct, raising_conn
from finbreak.migrations import _MIGRATIONS, LATEST_SCHEMA_VERSION, run_migrations
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features

_ROW = (
    "SELECT id, name, type, created_at, account_number, note, bank, "
    "statement_pdf_password FROM accounts"
)


def _cols(conn) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}


def _version(conn) -> int:
    return conn.execute("SELECT version FROM schema_version").fetchone()[0]


def _service(paths, currency: str) -> AuthService:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), currency)
    return svc


@pytest.fixture
def usd_service(paths) -> Iterator[AuthService]:
    """A USD vault: a backfill that writes a constant "ZAR" fails it."""
    svc = _service(paths, "USD")
    yield svc
    svc.lock()


@pytest.fixture
def v18(usd_service):
    """A USD vault holding an account with every optional field filled, plus a
    second account, set back to v18. Distinct values in each column are what
    show a row was left alone."""
    conn = usd_service.vault.connection
    acct = _acct(usd_service)
    conn.execute(
        "UPDATE accounts SET account_number = ?, note = ?, bank = ?, "
        "statement_pdf_password = ? WHERE id = ?",
        ("000111", "a synthetic note", "Synthetic Bank", "synthetic-pdf-pw", acct),
    )
    conn.execute(
        "INSERT INTO accounts (name, type, created_at) "
        "VALUES ('Second', 'savings', '2026-01-02T00:00:00')"
    )
    conn.commit()
    if "currency" in _cols(conn):
        conn.execute("ALTER TABLE accounts DROP COLUMN currency")
    conn.execute("UPDATE schema_version SET version = 18")
    conn.commit()
    return conn


def test_INV1_new_vault_default_account_reads_first_run_currency(usd_service) -> None:
    conn = usd_service.vault.connection
    rows = conn.execute("SELECT currency FROM accounts").fetchall()
    assert rows == [("USD",)]


def test_INV1_v18_vault_gains_exactly_a_backfilled_currency(v18) -> None:
    before_cols = _cols(v18)
    before_rows = v18.execute(_ROW + " ORDER BY id").fetchall()
    assert "currency" not in before_cols

    run_migrations(v18)

    assert _version(v18) == LATEST_SCHEMA_VERSION
    assert _cols(v18) == before_cols | {"currency"}
    assert v18.execute(_ROW + " ORDER BY id").fetchall() == before_rows
    currencies = v18.execute("SELECT currency FROM accounts ORDER BY id").fetchall()
    assert currencies == [("USD",), ("USD",)]


def test_INV1_v19_is_registered() -> None:
    """``>=``, not ``==``: a later step is not a breach of this one."""
    assert 19 in _MIGRATIONS
    assert LATEST_SCHEMA_VERSION >= 19


def test_INV2_failed_step_leaves_v18_and_a_rerun_upgrades(v18) -> None:
    """The failure is injected on the version stamp, the step's LAST statement,
    after the ALTER and the backfill, so only the transaction can undo them."""
    with pytest.raises(RuntimeError):
        run_migrations(raising_conn(v18, "SET version = 19", "injected stamp failure"))

    assert _version(v18) == 18
    assert "currency" not in _cols(v18)

    run_migrations(v18)

    assert _version(v18) == LATEST_SCHEMA_VERSION
    assert v18.execute("SELECT DISTINCT currency FROM accounts").fetchall() == [
        ("USD",)
    ]
