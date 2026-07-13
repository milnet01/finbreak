"""FIBR-0014 — encrypted backup export/restore. Enforces tests/features/backup/spec.md.

Slice 1 covers the Deliverable-2 reuse helpers on ``Vault`` (``export_to`` /
``rekey`` / ``open(in_memory_temp, cipher_compat)``) — the D2 SQLCipher mechanics
the spike proved, now wrapped and unit-tested against a real temp vault. Higher
slices add ``BackupService`` export/restore and the UI. Every vault lives under
``tmp_path``; no network, no real financial data (testing.md § 6).
"""

import json
import os
import secrets
import zipfile
from pathlib import Path

import pytest
from sqlcipher3.dbapi2 import DatabaseError

import finbreak
from conftest import _PW
from finbreak.crypto import SALT_LEN, derive_key
from finbreak.errors import VaultLockedError
from finbreak.models import FORMAT_VERSION, KdfParams
from finbreak.services.auth import (
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    AuthService,
)
from finbreak.services.backup import (
    MANIFEST_FORMAT_VERSION,
    MIN_BACKUP_PASSWORD_LEN,
    BackupService,
)
from finbreak.vault import SQLCIPHER_COMPAT, Vault

pytestmark = pytest.mark.features

KEY_LEN = 32
_SENTINEL = "SENTINEL-" + secrets.token_hex(6)
_BACKUP_PW = "backup-pass-1234"


def _seeded_auth(paths) -> AuthService:
    """A first-run, unlocked ``AuthService`` with a sentinel transaction seeded, so a
    backup's fidelity + no-plaintext can be checked. Locked by the caller/teardown."""
    auth = AuthService(*paths)
    auth.first_run(bytearray(_PW), "ZAR")
    conn = auth.vault.connection
    acct = conn.execute("SELECT id FROM accounts LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT INTO transactions"
        "(account_id, occurred_on, amount_minor, description, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (acct, "2026-07-01", -1234, _SENTINEL, "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    return auth


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


# --------------------------------------------------------------------------- #
# Slice 2 — BackupService.export_backup (INV-1 / INV-1b / INV-7)
# --------------------------------------------------------------------------- #
def test_INV1_fbk_is_three_entry_zip_with_no_plaintext(paths, tmp_path):
    auth = _seeded_auth(paths)
    try:
        dest = tmp_path / "my.fbk"
        BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW)

        assert zipfile.is_zipfile(dest)
        with zipfile.ZipFile(dest) as zf:
            assert set(zf.namelist()) == {"manifest.json", "params.json", "vault.db"}
            vault_bytes = zf.read("vault.db")
        assert vault_bytes[:16] != b"SQLite format 3\x00", "backup DB is ciphertext"
        assert _SENTINEL.encode() not in dest.read_bytes(), (
            "no seeded plaintext sentinel anywhere in the .fbk"
        )
    finally:
        auth.lock()


def test_INV1_manifest_records_schema_app_and_compat(paths, tmp_path):
    auth = _seeded_auth(paths)
    try:
        dest = tmp_path / "my.fbk"
        BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW)
        with zipfile.ZipFile(dest) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            params = json.loads(zf.read("params.json"))
        assert manifest["format_version"] == MANIFEST_FORMAT_VERSION
        assert manifest["app_version"] == finbreak.__version__
        assert manifest["schema_version"] == 8  # LATEST_SCHEMA_VERSION today
        assert manifest["sqlcipher_compat"] == SQLCIPHER_COMPAT
        # params.json carries a fresh per-backup salt, not the master sidecar's.
        assert set(params) == {
            "format_version",
            "memory_kib",
            "time_cost",
            "parallelism",
            "key_len",
            "salt_len",
            "salt_hex",
        }
        assert params["salt_hex"] != auth.load_params().salt.hex(), (
            "the backup salt is freshly minted (INV-3), not the master salt"
        )
    finally:
        auth.lock()


def test_INV7_export_enforces_min_backup_password(paths, tmp_path):
    auth = _seeded_auth(paths)
    try:
        dest = tmp_path / "my.fbk"
        short = "x" * (MIN_BACKUP_PASSWORD_LEN - 1)
        with pytest.raises(ValueError):
            BackupService(auth.vault, auth).export_backup(dest, short)
        assert not dest.exists(), "a rejected export writes no file"
    finally:
        auth.lock()


def test_INV7_export_wipes_backup_key_via_on_key_seam(paths, tmp_path):
    auth = _seeded_auth(paths)
    try:
        captured: list[tuple[str, bytearray]] = []
        dest = tmp_path / "my.fbk"
        BackupService(auth.vault, auth).export_backup(
            dest, _BACKUP_PW, on_key=lambda role, buf: captured.append((role, buf))
        )
        roles = [role for role, _ in captured]
        assert roles == ["backup"], "export derives only the backup key (no master)"
        _, key_buf = captured[0]
        assert bytes(key_buf) == bytes(len(key_buf)), (
            "the backup key buffer is zeroed after export returns"
        )
    finally:
        auth.lock()


def test_INV7_export_is_atomic_no_partial_on_failure(paths, tmp_path):
    auth = _seeded_auth(paths)
    try:
        dest = tmp_path / "my.fbk"

        def boom(role: str, buf: bytearray) -> None:
            raise RuntimeError("injected mid-export failure")

        with pytest.raises(RuntimeError):
            BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW, on_key=boom)
        assert not dest.exists(), "no partial .fbk on failure"
        leftovers = list(tmp_path.glob("*.tmp")) + list(tmp_path.glob("*.fbk*"))
        assert leftovers == [], f"no leftover temp files: {leftovers}"
    finally:
        auth.lock()


def test_INV8_export_requires_unlocked_vault(paths, tmp_path):
    auth = _seeded_auth(paths)
    service = BackupService(auth.vault, auth)
    auth.lock()  # now locked
    with pytest.raises(VaultLockedError):
        service.export_backup(tmp_path / "my.fbk", _BACKUP_PW)


# --------------------------------------------------------------------------- #
# Slice 3 — BackupService.restore_backup happy path (INV-2 / INV-3 / INV-5)
# --------------------------------------------------------------------------- #
_M2 = "new-master-pass-9876"


def _snapshot_tables(conn) -> dict[str, list]:
    """Every application table's full, order-independent row-set — the dynamic
    enumeration INV-2 compares (excludes sqlite_% internal tables)."""
    names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    return {
        n: sorted(map(str, conn.execute(f"SELECT * FROM {n}").fetchall()))
        for n in names
    }


def _export_from_seed(tmp_path) -> tuple[Path, dict[str, list]]:
    """First-run + seed a source vault under tmp_path/src, export a `.fbk`, snapshot
    its tables, and lock it. Returns (fbk_path, source-table-snapshot)."""
    src = tmp_path / "src"
    src.mkdir()
    src_paths = (src / "vault.db", src / "vault.kdf.json")
    auth = _seeded_auth(src_paths)
    snapshot = _snapshot_tables(auth.vault.connection)
    fbk = tmp_path / "backup.fbk"
    BackupService(auth.vault, auth).export_backup(fbk, _BACKUP_PW)
    auth.lock()
    return fbk, snapshot


def _dest_auth(tmp_path, name="dest") -> AuthService:
    d = tmp_path / name
    d.mkdir()
    return AuthService(d / "vault.db", d / "vault.kdf.json")


def test_INV2_restore_reproduces_every_table(tmp_path):
    fbk, snapshot = _export_from_seed(tmp_path)
    dest = _dest_auth(tmp_path)  # empty location, no vault yet
    BackupService(dest.vault, dest).restore_backup(fbk, _BACKUP_PW, _M2)

    assert dest.unlock(bytearray(_M2, "utf-8")) is True
    try:
        assert _snapshot_tables(dest.vault.connection) == snapshot, (
            "every table's row-set is reproduced exactly"
        )
    finally:
        dest.lock()


def test_INV3_separate_password_recovers_without_old_master(tmp_path):
    fbk, _snapshot = _export_from_seed(tmp_path)
    dest = _dest_auth(tmp_path)
    BackupService(dest.vault, dest).restore_backup(fbk, _BACKUP_PW, _M2)

    # The restored vault opens under the NEW master, and the OLD master fails.
    assert dest.unlock(bytearray(_M2, "utf-8")) is True
    dest.lock()
    assert dest.unlock(bytearray(_PW)) is False, (
        "the old master never opens the restore"
    )
    assert dest._key is None


def test_INV5_existing_vault_moved_aside_not_destroyed(tmp_path):
    fbk, _snapshot = _export_from_seed(tmp_path)
    dest = _dest_auth(tmp_path)
    # Give dest its OWN pre-existing vault first (a different master), then restore.
    dest.first_run(bytearray(b"the original dest master"), "USD")
    dest.lock()

    BackupService(dest.vault, dest).restore_backup(fbk, _BACKUP_PW, _M2)

    olds = list((tmp_path / "dest").glob("*.old"))
    assert len(olds) == 2, f"the old vault.db + sidecar are kept as *.old: {olds}"
    # The active vault is the RESTORED one: opens under M2, the old dest master fails.
    assert dest.unlock(bytearray(_M2, "utf-8")) is True
    dest.lock()
    assert dest.unlock(bytearray(b"the original dest master")) is False


def test_INV5_failure_after_move_aside_leaves_recoverable_old_pair(tmp_path):
    fbk, _snapshot = _export_from_seed(tmp_path)
    dest = _dest_auth(tmp_path)
    dest.first_run(bytearray(b"the original dest master"), "USD")
    dest.lock()

    def boom(role: str, buf: bytearray) -> None:
        if role == "post_move_aside":
            raise RuntimeError("injected failure right after the move-aside")

    with pytest.raises(RuntimeError):
        BackupService(dest.vault, dest).restore_backup(
            fbk, _BACKUP_PW, _M2, on_key=boom
        )

    olds = sorted((tmp_path / "dest").glob("*.old"))
    assert len(olds) == 2, "the old vault is recoverable from the *.old pair"
    assert all(p.stat().st_size > 0 for p in olds), "the *.old copies are intact"
    # The failure fired after move-aside, before install, so the live vault.db was
    # renamed to *.old and no new one installed — nothing silently lost (INV-5).
    assert not (tmp_path / "dest" / "vault.db").exists(), (
        "the original vault.db is safely moved aside, not overwritten in place"
    )
