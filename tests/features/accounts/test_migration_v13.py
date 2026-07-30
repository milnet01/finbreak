"""FIBR-0193 — schema v13 (the nullable ``accounts.account_number`` and
``accounts.note`` columns).

Enforces docs/specs/FIBR-0193.md INV-1 (a v12 vault upgrades in place, gaining
exactly those two nullable columns, every pre-existing row intact) and INV-2
(``LATEST_SCHEMA_VERSION == 13`` and ``13 in _MIGRATIONS``), plus the § 6
atomicity and § 4.1 idempotency claims. Mirrors
``tests/features/forecast/test_migration_v11.py`` — the nearest precedent, same
nullable-``ADD COLUMN`` shape. Every on-disk vault uses tmp_path; no test
touches the network or real financial data (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import (
    _PW,
    build_v9_vault,
    keyed_connection,
    raising_conn,
)
from finbreak.crypto import SALT_LEN
from finbreak.migrations import (
    _MIGRATIONS,
    LATEST_SCHEMA_VERSION,
    _migrate_to_v10,
    _migrate_to_v11,
    _migrate_to_v12,
    run_migrations,
)
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features


def _cols(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _notnull(conn, table: str) -> dict[str, int]:
    """Column name -> its ``PRAGMA table_info`` ``notnull`` flag.

    The v11 precedent's ``_cols()`` returns names only, which cannot see
    INV-1's nullability clause: ``ADD COLUMN … NOT NULL DEFAULT ''`` is accepted
    by SQLite and silently backfills every pre-existing row with ``""`` where
    the design says ``NULL``. This reader asserts the schema property directly
    rather than inferring it from whichever row happens to be present.
    """
    return {r[1]: r[3] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _build_v12_vault(paths) -> tuple:
    """A vault at exactly v12, plus the salt — the upgrade-path starting point
    for legs 2 and 4. ``build_v9_vault`` closes its own connection, so the
    chain and everything after it run on a handle reopened with
    ``keyed_connection`` (as both precedents do).
    """
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    # A non-empty rows list: PRAGMA foreign_key_check over a database with no
    # FK-bearing rows cannot fail, and seven of build_v9_vault's ten call sites
    # pass [].
    build_v9_vault(vault_path, sidecar, salt, [("2026-01-01", -12_345, "opening buy")])
    conn = keyed_connection(vault_path, salt)
    _migrate_to_v10(conn)  # v9  -> v10
    _migrate_to_v11(conn)  # v10 -> v11
    _migrate_to_v12(conn)  # v11 -> v12 — a hand-built v12 vault
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 12
    return conn, salt


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# INV-1 — the v12 -> v13 migration (additive, nullable, version-gated, atomic)
# --------------------------------------------------------------------------- #
def test_INV1_first_run_vault_carries_both_columns_nullable(service) -> None:
    """Leg 1 — the fresh first-run path. Also the catcher for a mis-bumped
    ``vault.py::SCHEMA_VERSION``: stamped at 13 the runner iterates an empty
    range and the columns never appear; stamped anywhere in 2-12 the skipped
    ``_migrate_to_v2`` leaves no ``accounts`` table at all."""
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 13
    assert {"account_number", "note"} <= _cols(conn, "accounts")
    notnull = _notnull(conn, "accounts")
    assert notnull["account_number"] == 0
    assert notnull["note"] == 0


def test_INV1_v12_vault_upgrades_to_v13_in_place(paths) -> None:
    """Leg 2 — the upgrade path, the only observable for INV-1's central clause
    (leg 1 covers first-run instead)."""
    conn, _salt = _build_v12_vault(paths)
    assert "account_number" not in _cols(conn, "accounts")
    assert "note" not in _cols(conn, "accounts")

    # Seed values a table rebuild would not preserve. The only accounts row in a
    # build_v9_vault chain is the one _migrate_to_v2 inserts, whose INSERT names
    # just name/type/created_at — so statement_pdf_password is NULL before AND
    # after the step, and (iii) would compare NULL to NULL without this.
    conn.execute(
        "UPDATE accounts SET name = ?, type = ?, statement_pdf_password = ? "
        "WHERE id = 1",
        ("Cheque (renamed)", "savings", "seeded-pdf-password"),
    )
    # Nothing in the build_v9_vault -> build_v1_vault chain ever writes
    # statement_periods, and INV-1 names it as an FK target.
    conn.execute(
        "INSERT INTO statement_periods"
        "(account_id, period_start, period_end, source_filename, imported_at) "
        "VALUES (1, '2026-01-01', '2026-01-31', 'jan.csv', '2026-02-01T00:00:00+00:00')"
    )
    # Commit before run_migrations: connections are isolation_level="", so an
    # uncommitted write leaves a transaction open and owned_transaction's BEGIN
    # raises "cannot start a transaction within a transaction".
    conn.commit()

    before_cols = _cols(conn, "accounts")
    before_account = conn.execute(
        "SELECT name, type, created_at, statement_pdf_password "
        "FROM accounts WHERE id = 1"
    ).fetchone()
    before_txns = conn.execute(
        "SELECT id, account_id, occurred_on, amount_minor, description "
        "FROM transactions ORDER BY id"
    ).fetchall()
    assert before_txns, "the FK half of INV-1 is vacuous without transactions rows"

    run_migrations(conn)  # v12 -> latest (v13)

    # (i) the version stamp advanced
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 13
    # (ii) gaining EXACTLY those two columns, both nullable
    assert _cols(conn, "accounts") == before_cols | {"account_number", "note"}
    notnull = _notnull(conn, "accounts")
    assert notnull["account_number"] == 0
    assert notnull["note"] == 0
    # (iii) the pre-existing accounts row survives with its other columns intact
    assert (
        conn.execute(
            "SELECT name, type, created_at, statement_pdf_password "
            "FROM accounts WHERE id = 1"
        ).fetchone()
        == before_account
    )
    # ...and the two new columns are NULL on it, not "" (INV-5's contract at the
    # schema level: a NOT NULL DEFAULT '' add would backfill silently here).
    assert conn.execute(
        "SELECT account_number, note FROM accounts WHERE id = 1"
    ).fetchone() == (None, None)
    # (iv) the FK-bearing rows survive and no reference is broken
    assert (
        conn.execute(
            "SELECT id, account_id, occurred_on, amount_minor, description "
            "FROM transactions ORDER BY id"
        ).fetchall()
        == before_txns
    )
    assert conn.execute("SELECT count(*) FROM statement_periods").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_INV1_migration_is_atomic(paths) -> None:
    """Leg 4 — a wedged *second* ALTER leaves a re-openable v12 with neither
    column added. ``raising_conn`` raises RuntimeError and
    ``owned_transaction`` re-raises it after rolling back, so the call must be
    wrapped or the leg errors out before it can assert anything."""
    conn, _salt = _build_v12_vault(paths)

    with pytest.raises(RuntimeError):
        # "ADD COLUMN note" is unambiguous: no other statement in the step
        # contains that substring.
        run_migrations(raising_conn(conn, "ADD COLUMN note", "injected ALTER failure"))

    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 12
    cols = _cols(conn, "accounts")
    assert "account_number" not in cols, "the first ALTER must roll back too"
    assert "note" not in cols
    conn.close()


def test_INV1_migration_is_idempotent_at_latest(paths) -> None:
    """Leg 5 — idempotency is version-gating, so the bare ALTERs never replay."""
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v9 -> latest (v13)
    run_migrations(conn)  # no-op at latest — never replays the two ADD COLUMNs
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 13
    conn.close()


# --------------------------------------------------------------------------- #
# INV-2 — the constant and the dispatch table agree
# --------------------------------------------------------------------------- #
def test_INV2_latest_schema_version_is_13() -> None:
    """Leg 3. The membership half is not in the v11 precedent, which asserts the
    constant only; it is taken from ``spending_alerts/test_migration_v12.py``."""
    assert LATEST_SCHEMA_VERSION == 13
    assert 13 in _MIGRATIONS
