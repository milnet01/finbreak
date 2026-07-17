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
        assert manifest["schema_version"] == 10  # LATEST_SCHEMA_VERSION today
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
    # nosec B608: `n` is a table name read from sqlite_master (never user input) —
    # the dynamic enumeration INV-2 mandates; not an injectable interpolation.
    return {
        n: sorted(map(str, conn.execute(f"SELECT * FROM {n}").fetchall()))  # nosec B608
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


# --------------------------------------------------------------------------- #
# Slice 4 — restore fail-closed + safe-zip + INV-11 / INV-13
#
# The guards these pin (safe-zip read, manifest version/compat gates, KDF-floor
# re-validation) landed on the restore critical path in slice 3; slice 4 locks in
# the fail-closed + no-disk-change behaviour explicitly (money/crypto surface).
# --------------------------------------------------------------------------- #
def _rebuild_fbk(src: Path, dest: Path, *, manifest=None, params=None, extra=None):
    """Copy ``src`` into ``dest`` with optional manifest/params field overrides and
    optional extra entries, to synthesise a tampered `.fbk`."""
    with zipfile.ZipFile(src) as zf:
        m = json.loads(zf.read("manifest.json"))
        p = json.loads(zf.read("params.json"))
        db = zf.read("vault.db")
    if manifest:
        m.update(manifest)
    if params:
        p.update(params)
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps(m))
        zf.writestr("params.json", json.dumps(p))
        zf.writestr("vault.db", db, compress_type=zipfile.ZIP_STORED)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)


def _dest_with_vault(tmp_path, name="dest"):
    """A dest location holding a pre-existing first-run vault. Returns
    (auth, dest_dir, vault_bytes, sidecar_bytes) for byte-identity assertions."""
    d = tmp_path / name
    d.mkdir()
    auth = AuthService(d / "vault.db", d / "vault.kdf.json")
    auth.first_run(bytearray(b"the original dest master"), "USD")
    auth.lock()
    return (
        auth,
        d,
        (d / "vault.db").read_bytes(),
        (d / "vault.kdf.json").read_bytes(),
    )


def _assert_unchanged(dest_dir, vault_bytes, sidecar_bytes):
    assert (dest_dir / "vault.db").read_bytes() == vault_bytes, (
        "vault.db is byte-identical"
    )
    assert (dest_dir / "vault.kdf.json").read_bytes() == sidecar_bytes, (
        "sidecar unchanged"
    )
    assert list(dest_dir.glob("*.old")) == [], "no move-aside on a failed restore"


def test_INV4_wrong_backup_password_fails_closed(tmp_path):
    from finbreak.errors import BackupError

    fbk, _snap = _export_from_seed(tmp_path)
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(fbk, "wrong-backup-pw!!", _M2)
    _assert_unchanged(d, vb, sb)


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda p: p.write_bytes(b"not a zip at all"),
        lambda p: p.write_bytes(p.read_bytes()[: len(p.read_bytes()) // 2]),  # truncate
    ],
    ids=["non-zip", "truncated"],
)
def test_INV4_corrupt_or_truncated_fails_closed(tmp_path, corrupt):
    from finbreak.errors import BackupError

    fbk, _snap = _export_from_seed(tmp_path)
    corrupt(fbk)
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(fbk, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)


def test_INV4_bad_format_version_fails_closed(tmp_path):
    from finbreak.errors import BackupError

    fbk, _snap = _export_from_seed(tmp_path)
    bad = tmp_path / "bad.fbk"
    _rebuild_fbk(fbk, bad, manifest={"format_version": MANIFEST_FORMAT_VERSION + 1})
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(bad, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)


def test_INV6a_newer_schema_manifest_refused_before_disk_change(tmp_path):
    from finbreak.errors import BackupError
    from finbreak.migrations import LATEST_SCHEMA_VERSION

    fbk, _snap = _export_from_seed(tmp_path)
    newer = tmp_path / "newer.fbk"
    _rebuild_fbk(fbk, newer, manifest={"schema_version": LATEST_SCHEMA_VERSION + 1})
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(newer, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)


def test_INV11_below_floor_params_refused_before_any_key(tmp_path):
    from finbreak.errors import BackupError
    from finbreak.services.auth import ARGON2_MEMORY_KIB

    fbk, _snap = _export_from_seed(tmp_path)
    weak = tmp_path / "weak.fbk"
    _rebuild_fbk(fbk, weak, params={"memory_kib": ARGON2_MEMORY_KIB - 1})
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    captured: list[str] = []
    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(
            weak, _BACKUP_PW, _M2, on_key=lambda role, buf: captured.append(role)
        )
    assert captured == [], "no key is derived when the params are below the floor"
    _assert_unchanged(d, vb, sb)


@pytest.mark.parametrize(
    "extra",
    [
        {"../evil.txt": b"traversal"},
        {"extra.txt": b"an unexpected fourth entry"},
    ],
    ids=["traversal", "extra-entry"],
)
def test_INV12_unsafe_zip_refused(tmp_path, extra):
    from finbreak.errors import BackupError

    fbk, _snap = _export_from_seed(tmp_path)
    bad = tmp_path / "bad.fbk"
    _rebuild_fbk(fbk, bad, extra=extra)
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(bad, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)


def test_INV12_oversized_manifest_entry_refused(tmp_path):
    from finbreak.errors import BackupError
    from finbreak.services.backup import MAX_MANIFEST_BYTES

    fbk, _snap = _export_from_seed(tmp_path)
    bad = tmp_path / "bomb.fbk"
    # A params.json padded past the tight manifest cap (the real bomb vector).
    _rebuild_fbk(fbk, bad, params={"pad": "A" * (MAX_MANIFEST_BYTES + 1)})
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(bad, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)


def test_INV12_large_legit_db_restores(tmp_path):
    from finbreak.services.backup import MAX_MANIFEST_BYTES

    # Seed a vault whose DB exceeds the TIGHT manifest cap, proving vault.db is read
    # under the generous MAX_BACKUP_DB_BYTES, not the manifest cap.
    src = tmp_path / "src"
    src.mkdir()
    auth = _seeded_auth((src / "vault.db", src / "vault.kdf.json"))
    conn = auth.vault.connection
    acct = conn.execute("SELECT id FROM accounts LIMIT 1").fetchone()[0]
    for i in range(400):
        conn.execute(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (acct, "2026-07-01", i, "x" * 400, "2026-01-01T00:00:00+00:00"),
        )
    conn.commit()
    fbk = tmp_path / "big.fbk"
    BackupService(auth.vault, auth).export_backup(fbk, _BACKUP_PW)
    auth.lock()
    with zipfile.ZipFile(fbk) as zf:
        assert zf.getinfo("vault.db").file_size > MAX_MANIFEST_BYTES, (
            "DB exceeds tight cap"
        )

    dest = _dest_auth(tmp_path, "big-dest")
    BackupService(dest.vault, dest).restore_backup(fbk, _BACKUP_PW, _M2)
    assert dest.unlock(bytearray(_M2, "utf-8")) is True
    dest.lock()


def test_INV13_wrong_cipher_compat_refused(tmp_path):
    from finbreak.errors import BackupError

    fbk, _snap = _export_from_seed(tmp_path)
    bad = tmp_path / "compat3.fbk"
    _rebuild_fbk(
        fbk, bad, manifest={"sqlcipher_compat": 3}
    )  # a lower level resets HMAC
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(bad, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)


def test_INV13_restore_under_forced_different_process_default(tmp_path):
    import sqlcipher3

    fbk, _snap = _export_from_seed(tmp_path)
    dest = _dest_auth(tmp_path)
    # Force the process-wide default cipher_compatibility to a DIFFERENT level; the
    # restore must still open the compat-4 backup because it applies the recorded
    # level explicitly (INV-13). Reset the default afterwards for test isolation.
    sqlcipher3.dbapi2.connect(":memory:").execute(
        "PRAGMA cipher_default_compatibility = 3"
    )
    try:
        # The INV-13 exercise: the compat-4 backup restores even though the process
        # default is now 3 — restore reads it by applying the recorded level
        # explicitly. (If it relied on the default it would HMAC-fail here.)
        BackupService(dest.vault, dest).restore_backup(fbk, _BACKUP_PW, _M2)
    finally:
        # Restore the normal-app default before the verification unlock (a real
        # unlock never runs under a forced-different default).
        sqlcipher3.dbapi2.connect(":memory:").execute(
            "PRAGMA cipher_default_compatibility = 4"
        )
    assert dest.unlock(bytearray(_M2, "utf-8")) is True, "restored data is intact"
    dest.lock()


# --------------------------------------------------------------------------- #
# Review fixes — restore fail-closed normalises non-UTF-8 / corrupt-DEFLATE
# entries too (INV-4: no raw traceback escapes on crafted input)
# --------------------------------------------------------------------------- #
def test_INV4_non_utf8_manifest_fails_closed(tmp_path):
    from finbreak.errors import BackupError

    fbk, _snap = _export_from_seed(tmp_path)
    with zipfile.ZipFile(fbk) as zf:
        params, db = zf.read("params.json"), zf.read("vault.db")
    bad = tmp_path / "bad.fbk"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr(
            "manifest.json", b"\xff\xfe not valid utf-8"
        )  # -> UnicodeDecodeError
        zf.writestr("params.json", params)
        zf.writestr("vault.db", db, compress_type=zipfile.ZIP_STORED)
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):  # not a raw UnicodeDecodeError
        BackupService(auth.vault, auth).restore_backup(bad, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)


def test_INV4_corrupt_deflate_entry_fails_closed(tmp_path):
    from finbreak.errors import BackupError

    fbk, _snap = _export_from_seed(tmp_path)
    with zipfile.ZipFile(fbk) as zf:
        params, db = zf.read("params.json"), zf.read("vault.db")
    bad = tmp_path / "bad.fbk"
    # manifest.json DEFLATED (the first entry), then corrupt its deflate stream.
    with zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"format_version": 1}) + " " * 200)
        zf.writestr("params.json", params)
        zf.writestr("vault.db", db, compress_type=zipfile.ZIP_STORED)
    raw = bytearray(bad.read_bytes())
    namelen = int.from_bytes(raw[26:28], "little")
    extralen = int.from_bytes(raw[28:30], "little")
    raw[30 + namelen + extralen] = 0xFF  # invalid deflate block type -> zlib.error
    bad.write_bytes(raw)
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    with pytest.raises(BackupError):  # not a raw zlib.error
        BackupService(auth.vault, auth).restore_backup(bad, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)
