"""FIBR-0172 — schema v12 (``alert_dismissals``) migration + drift guards.

Enforces spec INV-14/INV-14a: a fresh vault is v14 with ``alert_dismissals``; a
hand-built v11 vault upgrades to latest cleanly; ``LATEST_SCHEMA_VERSION == 14`` and
``12 in _MIGRATIONS``. The reconciliation rework (version pin -> 12, future guard
-> ``14 not in _MIGRATIONS``) is asserted in its own suite; here we lock the v12
mechanics. Every on-disk vault uses tmp_path (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import _PW, build_v9_vault, keyed_connection
from finbreak.crypto import SALT_LEN
from finbreak.migrations import (
    _MIGRATIONS,
    LATEST_SCHEMA_VERSION,
    _migrate_to_v10,
    _migrate_to_v11,
    run_migrations,
)
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features


def _cols(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _tables(conn) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def test_INV14_latest_schema_version_is_14() -> None:
    assert LATEST_SCHEMA_VERSION == 14
    assert 12 in _MIGRATIONS


def test_INV14_fresh_vault_is_v14_with_alert_dismissals(service) -> None:
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 14
    assert "alert_dismissals" in _tables(conn)
    assert _cols(conn, "alert_dismissals") == {"id", "alert_key", "created_at"}


def test_INV14_v11_vault_upgrades_to_latest_cleanly(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [("2026-01-01", -100, "a")])

    conn = keyed_connection(vault_path, salt)
    _migrate_to_v10(conn)  # v9 -> v10
    _migrate_to_v11(conn)  # v10 -> v11 — a hand-built v11 vault
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 11
    assert "alert_dismissals" not in _tables(conn)

    run_migrations(conn)  # v11 -> latest (v14)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 14
    assert "alert_dismissals" in _tables(conn)
    conn.close()


def test_INV14_migration_is_idempotent_at_latest(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v9_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v9 -> latest (v14)
    run_migrations(conn)  # no-op at latest
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 14
    conn.close()
