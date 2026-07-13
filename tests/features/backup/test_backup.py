"""FIBR-0014 — encrypted backup export/restore. Enforces tests/features/backup/spec.md.

Slice 1 covers the Deliverable-2 reuse helpers on ``Vault`` (``export_to`` /
``rekey`` / ``open(in_memory_temp, cipher_compat)``) — the D2 SQLCipher mechanics
the spike proved, now wrapped and unit-tested against a real temp vault. Higher
slices add ``BackupService`` export/restore and the UI. Every vault lives under
``tmp_path``; no network, no real financial data (testing.md § 6).
"""

import os
import secrets

import pytest
from sqlcipher3.dbapi2 import DatabaseError

from conftest import _PW
from finbreak.crypto import SALT_LEN, derive_key
from finbreak.errors import VaultLockedError
from finbreak.models import FORMAT_VERSION, KdfParams
from finbreak.services.auth import (
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
)
from finbreak.vault import SQLCIPHER_COMPAT, Vault

pytestmark = pytest.mark.features

KEY_LEN = 32
_SENTINEL = "SENTINEL-" + secrets.token_hex(6)


def _params(salt: bytes) -> KdfParams:
    return KdfParams(
        format_version=FORMAT_VERSION,
        memory_kib=ARGON2_MEMORY_KIB,
        time_cost=ARGON2_TIME_COST,
        parallelism=ARGON2_PARALLELISM,
        key_len=KEY_LEN,
        salt_len=SALT_LEN,
        salt=salt,
    )


def _make_vault(paths, *, seed: bool = True) -> tuple[Vault, bytearray]:
    """Create a fresh vault, optionally seed a sentinel transaction, and return the
    still-open (unlocked) ``Vault`` plus the raw master key used."""
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    params = _params(salt)
    key = derive_key(bytearray(_PW), salt, params)
    vault = Vault(vault_path, sidecar_path)
    vault.create(bytearray(key), params, "ZAR", 2)
    if seed:
        acct = vault.connection.execute("SELECT id FROM accounts LIMIT 1").fetchone()[0]
        vault.connection.execute(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (acct, "2026-07-01", -1234, _SENTINEL, "2026-01-01T00:00:00+00:00"),
        )
        vault.connection.commit()
    return vault, bytearray(key)


def test_export_to_roundtrips_via_backup_key(paths, tmp_path):
    vault, _key = _make_vault(paths)
    backup_key = bytearray(secrets.token_bytes(KEY_LEN))
    dest = tmp_path / "backup.db"

    vault.export_to(dest, backup_key)
    vault.close()

    # Reopen the exported DB with the backup key + recorded compat level.
    conn = __import__("sqlcipher3").dbapi2.connect(str(dest))
    conn.execute(f"PRAGMA key = \"x'{backup_key.hex()}'\"")
    conn.execute(f"PRAGMA cipher_compatibility = {SQLCIPHER_COMPAT}")
    conn.execute("PRAGMA cipher_use_hmac = ON")
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "schema_version" in tables and "transactions" in tables
    desc = conn.execute("SELECT description FROM transactions").fetchone()[0]
    assert desc == _SENTINEL, "every row travels into the backup DB"
    conn.close()


def test_export_to_wrong_key_fails_page_one(paths, tmp_path):
    vault, _key = _make_vault(paths)
    backup_key = bytearray(secrets.token_bytes(KEY_LEN))
    dest = tmp_path / "backup.db"
    vault.export_to(dest, backup_key)
    vault.close()

    conn = __import__("sqlcipher3").dbapi2.connect(str(dest))
    conn.execute(f"PRAGMA key = \"x'{secrets.token_bytes(KEY_LEN).hex()}'\"")
    conn.execute(f"PRAGMA cipher_compatibility = {SQLCIPHER_COMPAT}")
    conn.execute("PRAGMA cipher_use_hmac = ON")
    with pytest.raises(DatabaseError):
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    conn.close()


def test_export_to_writes_no_plaintext_and_is_owner_only(paths, tmp_path):
    vault, _key = _make_vault(paths)
    backup_key = bytearray(secrets.token_bytes(KEY_LEN))
    dest = tmp_path / "backup.db"
    vault.export_to(dest, backup_key)
    vault.close()

    assert dest.read_bytes()[:16] != b"SQLite format 3\x00", "backup is ciphertext"
    assert _SENTINEL.encode() not in dest.read_bytes(), "no plaintext row in the backup"
    if hasattr(os, "getuid"):
        assert dest.stat().st_mode & 0o777 == 0o600, "backup DB is owner-only"


def test_export_to_restores_prior_temp_store(paths, tmp_path):
    vault, _key = _make_vault(paths)
    before = vault.connection.execute("PRAGMA temp_store").fetchone()[0]
    vault.export_to(tmp_path / "backup.db", bytearray(secrets.token_bytes(KEY_LEN)))
    after = vault.connection.execute("PRAGMA temp_store").fetchone()[0]
    assert after == before, (
        "export must leave the live connection's temp_store as it was"
    )
    vault.close()


def test_export_to_on_locked_vault_raises(paths, tmp_path):
    vault, _key = _make_vault(paths)
    vault.close()  # now locked
    with pytest.raises(VaultLockedError):
        vault.export_to(tmp_path / "backup.db", bytearray(secrets.token_bytes(KEY_LEN)))


def test_rekey_old_key_fails_new_key_opens(paths):
    vault, key = _make_vault(paths)
    new_key = bytearray(secrets.token_bytes(KEY_LEN))
    vault.rekey(new_key)
    vault.close()

    vault_path, sidecar_path = paths
    with pytest.raises(DatabaseError):
        Vault(vault_path, sidecar_path).open(key)  # old key no longer opens

    reopened = Vault(vault_path, sidecar_path)
    reopened.open(bytearray(new_key))
    desc = reopened.connection.execute(
        "SELECT description FROM transactions"
    ).fetchone()[0]
    assert desc == _SENTINEL, "the new key opens the rekeyed vault with data intact"
    reopened.close()


def test_open_in_memory_temp_sets_temp_store_before_migrations(paths):
    vault, key = _make_vault(paths)
    vault.close()
    vault_path, sidecar_path = paths
    reopened = Vault(vault_path, sidecar_path)
    reopened.open(bytearray(key), in_memory_temp=True)
    assert reopened.connection.execute("PRAGMA temp_store").fetchone()[0] == 2  # MEMORY
    reopened.close()
