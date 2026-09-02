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
import stat
import tempfile
import zipfile
from pathlib import Path

import pytest
import sqlcipher3
from sqlcipher3.dbapi2 import DatabaseError

import finbreak
from conftest import _PW
from finbreak.crypto import (
    SALT_LEN,
    derive_key,
    load_and_validate_params,
    read_sidecar_v2,
)
from finbreak.errors import VaultLockedError
from finbreak.keywrap import SLOT_MASTER, unwrap_dek
from finbreak.migrations import LATEST_SCHEMA_VERSION
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
    VerifyResult,
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
        assert manifest["schema_version"] == 13  # LATEST_SCHEMA_VERSION today
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


def test_INV14_export_refuses_intermediate_db_over_cap(tmp_path, monkeypatch):
    """FIBR-0313 M1 — export_backup applies no size cap at all on the intermediate
    ``vault.db`` it re-keys and zips: restore's ``_read_capped`` refuses anything
    over ``MAX_BACKUP_DB_BYTES``, but nothing on the export side stops a vault over
    that same cap from being written, reported "Backup saved", and then being
    unrestorable on any machine. Learns the real intermediate-DB size from an
    unconstrained export first (no size assumption baked in), then lowers the cap
    one byte below it so the SAME export must now be refused."""
    import finbreak.services.backup as backup_mod
    from finbreak.errors import BackupError

    src = tmp_path / "src"
    src.mkdir()
    auth = _seeded_auth((src / "vault.db", src / "vault.kdf.json"))
    try:
        dest = tmp_path / "over.fbk"
        BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW)
        with zipfile.ZipFile(dest) as zf:
            db_size = zf.getinfo("vault.db").file_size
        dest.unlink()

        monkeypatch.setattr(backup_mod, "MAX_BACKUP_DB_BYTES", db_size - 1)
        with pytest.raises(BackupError):
            BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW)
        assert not dest.exists(), "a refused export writes no .fbk"
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == [], f"no leftover <dest>.tmp on refusal: {leftovers}"
    finally:
        auth.lock()


def test_INV14_export_allows_intermediate_db_exactly_at_cap(tmp_path, monkeypatch):
    """FIBR-0313 M1 — the boundary is symmetric with restore's ``_read_capped``
    (``file_size > cap`` is the refusal edge, never ``==``): an intermediate DB
    exactly at ``MAX_BACKUP_DB_BYTES`` still exports."""
    import finbreak.services.backup as backup_mod

    src = tmp_path / "src"
    src.mkdir()
    auth = _seeded_auth((src / "vault.db", src / "vault.kdf.json"))
    try:
        dest = tmp_path / "atcap.fbk"
        BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW)
        with zipfile.ZipFile(dest) as zf:
            db_size = zf.getinfo("vault.db").file_size
        dest.unlink()

        monkeypatch.setattr(backup_mod, "MAX_BACKUP_DB_BYTES", db_size)
        BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW)
        assert dest.exists(), "exactly-at-cap is allowed, symmetric with restore"
    finally:
        auth.lock()


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
    # B608: `n` is a table name read from sqlite_master (never user input) —
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


def test_INV15_install_fsyncs_files_and_each_distinct_parent_dir(tmp_path, monkeypatch):
    """FIBR-0313 M2 — ``_install``'s final ``os.replace(new_db, real_db)`` /
    ``os.replace(new_sidecar, real_sidecar)`` fsync NEITHER the source files nor
    their containing directories, though ``export_backup`` does both
    (``_fsync_dir(dest.parent)`` after its own ``os.replace``) and
    ``vault_migration._fsync`` exists for the file half. ``vault_path`` and
    ``sidecar_path`` are injected independently on ``Vault``, so this dest
    deliberately does NOT share a parent between them — a fix that fsyncs only
    "the" directory once would leave one of the two undone. Identifies the
    installed files by INODE (stable across the os.replace rename, whichever
    side of it the fsync lands on) and the directories by their resolved path."""
    import finbreak.services.backup as backup_mod

    fbk, _snapshot = _export_from_seed(tmp_path)

    db_dir = tmp_path / "dest_db"
    sidecar_dir = tmp_path / "dest_sidecar"
    db_dir.mkdir()
    sidecar_dir.mkdir()
    dest = AuthService(db_dir / "vault.db", sidecar_dir / "vault.kdf.json")

    dir_fsyncs: list[Path] = []
    file_fsync_ids: list[tuple[int, int]] = []
    real_fsync = os.fsync

    def recording_fsync(fd):
        st = os.fstat(fd)
        if stat.S_ISDIR(st.st_mode):
            dir_fsyncs.append(Path(os.readlink(f"/proc/self/fd/{fd}")).resolve())
        else:
            file_fsync_ids.append((st.st_dev, st.st_ino))
        return real_fsync(fd)

    monkeypatch.setattr(backup_mod.os, "fsync", recording_fsync)
    BackupService(dest.vault, dest).restore_backup(fbk, _BACKUP_PW, _M2)
    dest.lock()

    installed_db = db_dir / "vault.db"
    installed_sidecar = sidecar_dir / "vault.kdf.json"
    installed_db_id = (installed_db.stat().st_dev, installed_db.stat().st_ino)
    installed_sidecar_id = (
        installed_sidecar.stat().st_dev,
        installed_sidecar.stat().st_ino,
    )

    assert installed_db_id in file_fsync_ids, (
        "the installed vault.db must be fsynced as a FILE at some point during "
        "_install (before or after the rename — the inode is the same either "
        "side of it).\n"
        f"  expected: {installed_db_id} (the installed vault.db's (dev, ino)) "
        "among the fsync'd files\n"
        f"  actual:   {file_fsync_ids}"
    )
    assert installed_sidecar_id in file_fsync_ids, (
        "the installed sidecar must be fsynced as a FILE too.\n"
        f"  expected: {installed_sidecar_id} among the fsync'd files\n"
        f"  actual:   {file_fsync_ids}"
    )
    assert db_dir.resolve() in dir_fsyncs, (
        "the database's own parent directory must be fsynced after install.\n"
        f"  expected: {db_dir.resolve()} among the fsync'd directories\n"
        f"  actual:   {dir_fsyncs}"
    )
    assert sidecar_dir.resolve() in dir_fsyncs, (
        "the sidecar's own parent directory must ALSO be fsynced — it is a "
        "DIFFERENT directory from the database's here, and a fix that fsyncs "
        "only one shared 'the' directory leaves this one durable-blind.\n"
        f"  expected: {sidecar_dir.resolve()} among the fsync'd directories\n"
        f"  actual:   {dir_fsyncs}"
    )


def test_INV15_move_aside_dir_fsynced_before_post_move_aside_seam(
    tmp_path, monkeypatch
):
    """FIBR-0313 M2 — the ``*.old`` move-aside pair created just above the
    ``on_key("post_move_aside", ...)`` seam is never directory-fsynced before
    that seam fires. The seam's whole purpose (INV-5) is that the old pair is
    "already safely aside" at that point, so a crash between the move-aside and
    its own directory fsync can still lose the recoverable ``*.old`` pair even
    though the seam already promised it survived. Asserts ORDER: a directory
    fsync of the aside pair's parent must appear in the recorded event list
    before the seam fires, not merely that both eventually happen."""
    import finbreak.services.backup as backup_mod

    fbk, _snapshot = _export_from_seed(tmp_path)
    auth, d, _vb, _sb = _dest_with_vault(tmp_path)

    events: list[str] = []
    real_fsync = os.fsync
    aside_dir = d.resolve()

    def recording_fsync(fd):
        st = os.fstat(fd)
        if stat.S_ISDIR(st.st_mode):
            path = Path(os.readlink(f"/proc/self/fd/{fd}")).resolve()
            if path == aside_dir:
                events.append("fsync_dir:aside_parent")
        return real_fsync(fd)

    def seam(role: str, buf: bytearray) -> None:
        if role == "post_move_aside":
            events.append("seam:post_move_aside")
            raise RuntimeError("stop right at the seam")

    monkeypatch.setattr(backup_mod.os, "fsync", recording_fsync)

    with pytest.raises(RuntimeError):
        BackupService(auth.vault, auth).restore_backup(
            fbk, _BACKUP_PW, _M2, on_key=seam
        )

    dir_events = [e for e in events if e == "fsync_dir:aside_parent"]
    assert dir_events, (
        "expected the *.old pair's directory to be fsynced before the "
        "post_move_aside seam fires; no such directory fsync was recorded "
        "before the restore stopped at the seam.\n"
        f"  expected: at least one 'fsync_dir:aside_parent' entry\n"
        f"  actual:   {events}"
    )
    assert events.index(dir_events[0]) < events.index("seam:post_move_aside"), (
        "the *.old pair's directory fsync must happen BEFORE the "
        "post_move_aside seam fires — INV-5's premise is that the old pair is "
        "already safely aside at that seam, which a fsync landing after it "
        "would falsify.\n"
        "  expected: 'fsync_dir:aside_parent' before 'seam:post_move_aside'\n"
        f"  actual order: {events}"
    )


def test_INV16_restore_refuses_while_live_vault_is_open(tmp_path):
    """FIBR-0014 INV-8 says restore is pre-login only, and ``_install``'s final
    ``os.replace(new_db, real_db)`` assumes ``self._vault``'s files are not the
    backing store of an open connection: on Windows that assumption failing
    raises loudly (``PermissionError``), but on POSIX the rename SUCCEEDS while
    the still-open connection goes on reading/writing the now-detached inode —
    silent divergence, no error at all. ``restore_backup`` today has no
    precondition that catches this itself; it currently relies entirely on its
    one caller (the pre-login screen) never calling it with a vault open.

    Locks the OUTCOME, not the mechanism: called against an OPEN live vault,
    ``restore_backup`` must refuse with ``BackupError`` *before* touching disk.
    A fix that raises only *after* already moving the live vault aside (or
    after installing the restored one) must still fail this test — the
    move-aside / byte-identity assertions below exist so that a "raises, but
    too late" fix does not pass it."""
    from finbreak.errors import BackupError

    fbk, _snap = _export_from_seed(tmp_path)
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    # _dest_with_vault leaves the vault LOCKED; re-open it so the live vault is
    # OPEN at the moment restore is attempted -- the one state no existing test
    # in this suite covers (measured: every restore_backup call elsewhere in
    # this file, and the sole production caller, enters with the vault closed).
    assert auth.unlock(bytearray(b"the original dest master")) is True
    own_snapshot = _snapshot_tables(auth.vault.connection)

    with pytest.raises(BackupError):
        BackupService(auth.vault, auth).restore_backup(fbk, _BACKUP_PW, _M2)

    # Nothing on disk moved or changed -- not the *.old move-aside, not the
    # live vault.db/sidecar bytes themselves.
    _assert_unchanged(d, vb, sb)

    # And the live vault is still functionally what it was: whatever state the
    # refusal leaves the connection in, it must still open under its ORIGINAL
    # password and hold its ORIGINAL rows -- never any part of the restore.
    if auth._key is not None:
        auth.lock()
    assert auth.unlock(bytearray(b"the original dest master")) is True, (
        "the live vault must still open under its original password"
    )
    assert _snapshot_tables(auth.vault.connection) == own_snapshot, (
        "the live vault's rows must be exactly what they were before the "
        "refused restore attempt"
    )
    auth.lock()


def test_INV17_second_restore_prunes_older_old_set_keeps_newest(tmp_path):
    """FIBR-0318 Q4 -- nothing in ``src/`` ever unlinks a ``*.old`` set
    (``BackupService._install`` only ever MOVES one into place), so repeated
    restores accumulate full encrypted vault copies indefinitely. FIBR-0014
    INV-5 requires the set to exist; no document says for how long. The
    decision this locks: a SUCCESSFUL restore prunes OLDER ``*.old`` sets,
    keeping only the most recent one -- and does NOT prune the set it just
    created, which is the user's own "I restored the wrong backup" undo
    window (the same crash window INV-5's prose already protects, stretched
    to human timescale).

    Two restores into the same dest, back to back. The first leaves the
    ORIGINAL vault's ``*.old`` set (set A) on disk -- confirmed as a
    precondition, not assumed. The second restore must remove set A and
    leave only the set it just created (set B, the just-superseded M1
    vault) -- identified by a straight before/after directory diff, so the
    check does not depend on the stamp format or any glob a fix might
    choose (`*.old*` is the pre-existing naming from `_install`, unchanged
    by this decision; only which sets SURVIVE is what Q4 decides).

    Asserting "exactly one set remains" is not enough -- a fix that deletes
    the WRONG set (drops what it just created and keeps the stale one, or
    prunes both) would still pass a bare count. So the surviving set is
    also proven to be the right one: intact and still openable under M1,
    the password that was in force immediately before the second restore
    -- not M2 (the brand new master the second restore just installed), and
    not the ORIGINAL dest master (set A's password, which must be gone).
    """
    fbk1, _snap1 = _export_from_seed(tmp_path)
    # _dest_with_vault's master password is "the original dest master".
    auth, d, _vb0, _sb0 = _dest_with_vault(tmp_path)

    M1 = "restore-one-new-master"
    BackupService(auth.vault, auth).restore_backup(fbk1, _BACKUP_PW, M1)
    old_after_r1 = {p.name for p in d.glob("*.old*")}
    assert old_after_r1, "precondition: restore #1 must leave an *.old set behind"

    # A second, independent backup -- _export_from_seed hardcodes tmp_path/"src"
    # for the source vault, already used above, so build this one by hand under
    # its own directory rather than colliding with it.
    src2 = tmp_path / "src2"
    src2.mkdir()
    src2_auth = _seeded_auth((src2 / "vault.db", src2 / "vault.kdf.json"))
    fbk2 = tmp_path / "backup2.fbk"
    BackupService(src2_auth.vault, src2_auth).export_backup(fbk2, _BACKUP_PW)
    src2_auth.lock()
    M2 = "restore-two-new-master"
    BackupService(auth.vault, auth).restore_backup(fbk2, _BACKUP_PW, M2)
    old_after_r2 = {p.name for p in d.glob("*.old*")}

    stale_from_set_a = old_after_r1 & old_after_r2
    assert not stale_from_set_a, (
        "a second successful restore must prune the OLDER *.old set (from "
        "the original vault M1's restore just superseded), not just add to "
        "it -- repeated restores must not accumulate indefinitely\n"
        f"  still present from the first restore's *.old set: "
        f"{sorted(stale_from_set_a)}"
    )
    set_b = old_after_r2 - old_after_r1
    assert set_b, (
        "the *.old set THIS restore just created must survive -- it is the "
        "user's own undo window for 'I restored the wrong backup', not "
        "something a restore prunes about itself"
    )

    # set_b is proven to be the RIGHT survivor, not merely A survivor: it must
    # be the moved-aside M1 vault, still openable under M1.
    db_names = [n for n in set_b if n.startswith("vault.db.") and n.endswith(".old")]
    sidecar_names = [
        n for n in set_b if n.startswith("vault.kdf.json.") and n.endswith(".old")
    ]
    assert len(db_names) == 1 and len(sidecar_names) == 1, (
        "expected exactly one surviving *.old vault.db + one sidecar in the "
        f"newly-created set, got db={db_names} sidecar={sidecar_names}"
    )
    recovery = tmp_path / "recovered_from_old"
    recovery.mkdir()
    recovered_db = recovery / "vault.db"
    recovered_sidecar = recovery / "vault.kdf.json"
    recovered_db.write_bytes((d / db_names[0]).read_bytes())
    recovered_sidecar.write_bytes((d / sidecar_names[0]).read_bytes())

    recovered_auth = AuthService(recovered_db, recovered_sidecar)
    assert recovered_auth.unlock(bytearray(M1, "utf-8")) is True, (
        "the surviving *.old set must be the M1 vault the second restore "
        "just moved aside -- it did not open under M1, the password in "
        "force immediately before that restore"
    )
    assert _snapshot_tables(recovered_auth.vault.connection) == _snap1, (
        "the surviving *.old set's rows must be exactly M1's vault's rows"
    )
    recovered_auth.lock()


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


def test_INV12_deflate_bomb_refused_on_the_ratio(tmp_path):
    """FIBR-0212 — INV-12 requires "a suspicious ``file_size / compress_size`` ratio"
    to be rejected, and it was not implemented. The ZIP_STORED note in the code
    covers files finbreak WRITES; a restore reads an untrusted file, and
    ``_read_capped`` never inspected ``compress_type``. MEASURED here: a small
    hostile ``.fbk`` whose ``vault.db`` is deflated zeros inflates to the 512 MiB
    cap in RAM, pre-login. The declared size is honest, so only the ratio catches
    it."""
    from finbreak.errors import BackupError
    from finbreak.services.backup import MAX_BACKUP_DB_BYTES

    fbk, _snap = _export_from_seed(tmp_path)
    bomb = tmp_path / "bomb.fbk"
    with zipfile.ZipFile(fbk) as zf:
        m, p = zf.read("manifest.json"), zf.read("params.json")
    with zipfile.ZipFile(bomb, "w") as zf:
        zf.writestr("manifest.json", m)
        zf.writestr("params.json", p)
        # Zeros deflate ~1000:1, so this is a few hundred KB on disk.
        zf.writestr(
            "vault.db", b"\0" * MAX_BACKUP_DB_BYTES, compress_type=zipfile.ZIP_DEFLATED
        )
    assert bomb.stat().st_size < 2 * 1024 * 1024, "the bomb file itself is small"

    auth, d, vb, sb = _dest_with_vault(tmp_path)
    # `match=` is load-bearing: the declared file_size is exactly the cap, so the
    # `file_size > cap` gate does NOT fire, and without the ratio check the restore
    # inflates all 512 MiB and *still* raises BackupError from the downstream
    # "this isn't a vault" failure — a green that proves nothing (measured).
    with pytest.raises(BackupError, match="compression ratio"):
        BackupService(auth.vault, auth).restore_backup(bomb, _BACKUP_PW, _M2)
    _assert_unchanged(d, vb, sb)


def test_INV7_export_temp_refuses_a_pre_planted_file(tmp_path):
    """FIBR-0212 — ``_write_fbk`` opened its temp O_TRUNC, so an attacker who
    pre-creates ``dest.fbk.tmp`` (mode 0666) in a shared export dir has it filled
    and renamed into place: the user's backup is then attacker-owned and
    world-readable. O_NOFOLLOW stops only the symlink case. Its sibling
    ``_write_owner_only`` in the same file already used O_EXCL, as does
    ``pdf_export`` since FIBR-0204; the export writer is now the same shape —
    unlink the stale temp, then create with O_EXCL so a re-plant loses the race."""
    src = tmp_path / "src"
    src.mkdir()
    auth = _seeded_auth((src / "vault.db", src / "vault.kdf.json"))
    dest = tmp_path / "out.fbk"

    planted = dest.with_name(dest.name + ".tmp")
    planted.touch(mode=0o666)
    planted.chmod(0o666)  # touch() honours the umask; force the hostile mode

    BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW)
    auth.lock()

    mode = dest.stat().st_mode & 0o777
    assert mode == 0o600, f"the backup is owner-only, not {oct(mode)}"


def test_INV7_export_fsyncs_the_destination_directory(tmp_path, monkeypatch):
    """FIBR-0212 — ``_write_fbk`` fsyncs the FILE, then ``os.replace``s it. POSIX
    does not guarantee the directory ENTRY reaches stable storage, so a power loss
    after "Backup saved" can leave no dest at all — on the one artifact whose whole
    purpose is surviving a disaster. Asserts the directory fd is fsynced after the
    rename."""
    import finbreak.services.backup as backup_mod

    src = tmp_path / "src"
    src.mkdir()
    auth = _seeded_auth((src / "vault.db", src / "vault.kdf.json"))
    dest = tmp_path / "out.fbk"

    synced: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(fd):
        synced.append(os.fstat(fd).st_mode)
        return real_fsync(fd)

    monkeypatch.setattr(backup_mod.os, "fsync", recording_fsync)
    BackupService(auth.vault, auth).export_backup(dest, _BACKUP_PW)
    auth.lock()

    assert any(stat.S_ISDIR(mode) for mode in synced), (
        "the destination DIRECTORY is fsynced, not only the file"
    )


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


# --------------------------------------------------------------------------- #
# FIBR-0033 — read-only verify_backup (INV-1..7, local numbering; the reason
# codes of the spec's mapping table). Reuses _export_from_seed / _rebuild_fbk.
# --------------------------------------------------------------------------- #
def _verify_service(tmp_path, name="vsvc") -> BackupService:
    """A BackupService over an empty dest location. Verify never touches this live
    vault (D3), so any location — locked or absent — is fine."""
    a = _dest_auth(tmp_path, name)
    return BackupService(a.vault, a)


def _open_embedded_db(fbk: Path, work: Path):
    """Open the `.fbk`'s ciphertext ``vault.db`` with its backup key (derived from
    the embedded params.json) so a fixture can mutate the DB below the manifest —
    beyond what ``_rebuild_fbk`` (which copies vault.db verbatim) can do."""
    with zipfile.ZipFile(fbk) as zf:
        params_bytes, db = zf.read("params.json"), zf.read("vault.db")
    dbp = work / "vault.db"
    dbp.write_bytes(db)
    pp = work / "params.json"
    pp.write_bytes(params_bytes)
    params = load_and_validate_params(pp)
    key = derive_key(bytearray(_BACKUP_PW, "utf-8"), params.salt, params)
    conn = sqlcipher3.dbapi2.connect(str(dbp))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")
    conn.execute(f"PRAGMA cipher_compatibility = {SQLCIPHER_COMPAT}")
    conn.execute("PRAGMA cipher_use_hmac = ON")
    return conn, dbp


def _write_fbk_with_db(fbk: Path, out: Path, db_bytes: bytes) -> None:
    """Rebuild ``out`` from ``fbk`` swapping in ``db_bytes`` for vault.db, manifest
    + params byte-identical."""
    with zipfile.ZipFile(fbk) as zf:
        m, p = zf.read("manifest.json"), zf.read("params.json")
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("manifest.json", m)
        zf.writestr("params.json", p)
        zf.writestr("vault.db", db_bytes, compress_type=zipfile.ZIP_STORED)


def test_INV2_verify_valid_backup_ok_with_counts(tmp_path):
    fbk, snapshot = _export_from_seed(tmp_path)
    res = _verify_service(tmp_path).verify_backup(fbk, _BACKUP_PW)
    assert res.ok is True
    assert res.reason is None
    assert res.schema_version == LATEST_SCHEMA_VERSION  # as-migrated (INV-2)
    assert res.table_counts == {n: len(rows) for n, rows in snapshot.items()}
    assert res.table_counts["transactions"] == 1, "the seeded sentinel is counted"


def test_INV3_verify_wrong_password_reason(tmp_path):
    fbk, _snap = _export_from_seed(tmp_path)
    res = _verify_service(tmp_path).verify_backup(fbk, "wrong-backup-pw!!")
    assert res == VerifyResult(False, None, None, "wrong_password")


def test_INV4_verify_corrupt_overflow_page_reason(tmp_path):
    # A latest-schema backup with a long transaction description forces overflow
    # pages count(*) never reads; flip a byte in the tail overflow region so page-1
    # + count(*) still pass but cipher_integrity_check catches it (INV-4 corrupt).
    src = tmp_path / "srcbig"
    src.mkdir()
    auth = _seeded_auth((src / "vault.db", src / "vault.kdf.json"))
    conn = auth.vault.connection
    acct = conn.execute("SELECT id FROM accounts LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT INTO transactions"
        "(account_id, occurred_on, amount_minor, description, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (acct, "2026-07-02", -99, "Q" * 60000, "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    fbk = tmp_path / "big.fbk"
    BackupService(auth.vault, auth).export_backup(fbk, _BACKUP_PW)
    auth.lock()

    with zipfile.ZipFile(fbk) as zf:
        db = bytearray(zf.read("vault.db"))
    db[len(db) - 100] ^= 0xFF  # tail overflow page — a count(*)-invisible byte
    bad = tmp_path / "corrupt.fbk"
    _write_fbk_with_db(fbk, bad, bytes(db))

    res = _verify_service(tmp_path).verify_backup(bad, _BACKUP_PW)
    assert res == VerifyResult(False, None, None, "corrupt")


def test_INV4_verify_too_new_embedded_schema_reason(tmp_path):
    # manifest-under-states: the manifest's schema stays at the gate-passing LATEST
    # while the EMBEDDED vault.db's schema_version is bumped above LATEST, so it
    # slips _guard_manifest and trips run_migrations -> SchemaVersionError -> too_new.
    fbk, _snap = _export_from_seed(tmp_path)
    with tempfile.TemporaryDirectory() as td:
        conn, dbp = _open_embedded_db(fbk, Path(td))
        conn.execute(
            "UPDATE schema_version SET version = ?", (LATEST_SCHEMA_VERSION + 1,)
        )
        conn.commit()
        conn.close()
        db2 = dbp.read_bytes()
    bad = tmp_path / "too_new.fbk"
    _write_fbk_with_db(fbk, bad, db2)  # manifest schema unchanged (== LATEST)

    res = _verify_service(tmp_path).verify_backup(bad, _BACKUP_PW)
    assert res == VerifyResult(False, None, None, "too_new")


def test_INV4_verify_bad_kdf_params_reason(tmp_path):
    fbk, _snap = _export_from_seed(tmp_path)
    weak = tmp_path / "weak.fbk"
    _rebuild_fbk(fbk, weak, params={"memory_kib": ARGON2_MEMORY_KIB - 1})
    res = _verify_service(tmp_path).verify_backup(weak, _BACKUP_PW)
    assert res == VerifyResult(False, None, None, "bad_kdf_params")


def test_INV4_verify_invalid_non_zip_reason(tmp_path):
    fbk, _snap = _export_from_seed(tmp_path)
    fbk.write_bytes(b"not a zip at all")
    res = _verify_service(tmp_path).verify_backup(fbk, _BACKUP_PW)
    assert res == VerifyResult(False, None, None, "invalid")


def test_INV4_verify_io_error_reason(tmp_path, monkeypatch):
    # A temp-write failure surfaces raw as OSError from the helper (D7) — verify
    # must catch it, not crash, and map it to io_error.
    fbk, _snap = _export_from_seed(tmp_path)

    def boom(path, data):
        raise OSError("read-only temp")

    monkeypatch.setattr(BackupService, "_write_owner_only", staticmethod(boom))
    res = _verify_service(tmp_path).verify_backup(fbk, _BACKUP_PW)
    assert res == VerifyResult(False, None, None, "io_error")


def test_verify_memory_error_reason(tmp_path, monkeypatch):
    # `_read_fbk` normalises its OWN MemoryError to BackupError, so this covers
    # the rest of the sequence the two callers share -- the temp writes, the
    # open, the migration. `restore_backup` caught it there and `verify_backup`
    # did not, so the same bomb on the same small machine was a refused restore
    # and an unhandled exception out of a Qt slot on verify (FIBR-0310 P12).
    # "invalid" is deliberately the answer restore's BackupError maps to here.
    fbk, _snap = _export_from_seed(tmp_path)

    def boom(path, data):
        raise MemoryError("no room for the inflated database")

    monkeypatch.setattr(BackupService, "_write_owner_only", staticmethod(boom))
    res = _verify_service(tmp_path).verify_backup(fbk, _BACKUP_PW)
    assert res == VerifyResult(False, None, None, "invalid")


def test_INV1_verify_leaves_live_vault_untouched(tmp_path):
    # Verify never opens or writes the live vault; its dir is byte-identical and
    # gains no files across every outcome (here: a valid verify over a live vault).
    fbk, _snap = _export_from_seed(tmp_path)
    auth, d, vb, sb = _dest_with_vault(tmp_path)
    before = sorted(p.name for p in d.iterdir())
    res = BackupService(auth.vault, auth).verify_backup(fbk, _BACKUP_PW)
    assert res.ok is True
    _assert_unchanged(d, vb, sb)
    assert sorted(p.name for p in d.iterdir()) == before, "no new files in vault dir"


def test_INV5_verify_leaves_no_temp(tmp_path, monkeypatch):
    fbk, _snap = _export_from_seed(tmp_path)
    created: list[str] = []
    real = tempfile.TemporaryDirectory

    def spy(*a, **k):
        td = real(*a, **k)
        created.append(td.name)
        return td

    monkeypatch.setattr(tempfile, "TemporaryDirectory", spy)
    _verify_service(tmp_path).verify_backup(fbk, _BACKUP_PW)
    assert created, "verify allocated a temp dir"
    assert not os.path.exists(created[0]), "the temp dir is removed after verify"


def test_INV7_verify_wipes_backup_key_via_on_key_seam(tmp_path):
    fbk, _snap = _export_from_seed(tmp_path)
    captured: list[tuple[str, bytearray]] = []
    _verify_service(tmp_path).verify_backup(
        fbk, _BACKUP_PW, on_key=lambda role, buf: captured.append((role, buf))
    )
    roles = [role for role, _ in captured]
    assert roles == ["backup"], "verify derives only the backup key (no master)"
    _, key_buf = captured[0]
    assert bytes(key_buf) == bytes(len(key_buf)), (
        "the backup key buffer is zeroed after verify returns (INV-7)"
    )


def test_INV13_restore_records_the_cipher_level_it_wrote_at(tmp_path):
    """A restored database is written at an EXPLICIT cipher level, so the
    sidecar has to record it.

    ``export_to`` sets ``PRAGMA backup.cipher_compatibility`` explicitly and the
    restore installs that database, rekeyed. A ``create``d vault takes the
    library default instead. The two agree today and stop agreeing the moment a
    sqlcipher3-wheels bump moves the default -- at which point every restored
    vault is unopenable by the build that restored it, because ``_open_with``
    passes the sidecar's ``cipher_compatibility`` and there was none to pass.

    The migration records the level for exactly this reason (FIBR-0019 § 13.2,
    whose own comment spells it out). Restore wrote no ``cipher_compatibility``
    at all -- the same database provenance, the same hazard, one of the two
    writers covered (FIBR-0307 finding 11).
    """
    fbk, _snapshot = _export_from_seed(tmp_path)
    dest = _dest_auth(tmp_path)
    BackupService(dest.vault, dest).restore_backup(fbk, _BACKUP_PW, _M2)

    sidecar = read_sidecar_v2(dest.vault.sidecar_path)
    assert sidecar.cipher_compatibility == SQLCIPHER_COMPAT, (
        "the restored sidecar must record the level its database was written "
        "at, so every later open passes it. Without it the vault opens only "
        "while the library default happens to match.\n"
        f"  expected: cipher_compatibility == {SQLCIPHER_COMPAT}\n"
        f"  actual:   {sidecar.cipher_compatibility!r}"
    )

    # Precondition: the recorded level is load-bearing rather than decorative.
    # With the CORRECT key, opening the restored database at a different level
    # fails -- which is what a moved library default would amount to.
    params = sidecar.params_for(SLOT_MASTER)
    kek = derive_key(bytearray(_M2, "utf-8"), params.salt, params)
    dek = unwrap_dek(
        bytes(kek), sidecar.slots[SLOT_MASTER].wrapped, SLOT_MASTER, params
    )
    probe = Vault(dest.vault.vault_path, dest.vault.sidecar_path)
    with pytest.raises(DatabaseError):
        probe.open(bytearray(dek), cipher_compat=SQLCIPHER_COMPAT - 1)


# --------------------------------------------------------------------------- #
# FIBR-0310 P5 — a vault is FOUR files, and the incumbent's WAL moves with it
# --------------------------------------------------------------------------- #
def test_the_incumbent_wal_moves_aside_with_its_database(tmp_path):
    """``_install`` moved ``vault.db`` and the sidecar aside and left the
    incumbent's ``-wal`` / ``-shm`` exactly where they were.

    That cost both halves of what the move-aside is for. The restored database
    was installed BESIDE a WAL belonging to a different database under a
    different key -- the § 6 hazard ``vault_migration`` names and handles twice.
    And the ``.old`` copy, whose whole purpose is being recoverable, was left
    without its journal (FIBR-0310 P5).

    A leftover ``-wal`` means the app did not close cleanly, which is one of
    the reasons someone reaches for a restore in the first place -- so this is
    the state the feature exists for, not an exotic one. The WAL planted here
    is a REAL one, taken from the incumbent before its clean close.
    """
    fbk, _snapshot = _export_from_seed(tmp_path)
    dest = _dest_auth(tmp_path)
    dest.first_run(bytearray(b"the original dest master"), "USD")

    # A genuine WAL for the incumbent: write, capture the -wal bytes, then let
    # the clean close remove it and put those bytes back. That is what a crash
    # would have left.
    dest.vault.connection.execute(
        "INSERT INTO accounts(name, type, created_at) VALUES (?, ?, ?)",
        ("incumbent", "current", "2026-01-01T00:00:00+00:00"),
    )
    dest.vault.connection.commit()
    live_db = dest.vault.vault_path
    live_wal = live_db.with_name(live_db.name + "-wal")
    assert live_wal.exists(), (
        "precondition: the incumbent must be in WAL mode with an outstanding "
        "journal, or there is no sibling for this leg to be about."
    )
    wal_bytes = live_wal.read_bytes()
    dest.lock()
    live_wal.write_bytes(wal_bytes)  # what an unclean shutdown leaves behind

    BackupService(dest.vault, dest).restore_backup(fbk, _BACKUP_PW, _M2)

    assert not live_wal.exists(), (
        "the restored database was installed beside the INCUMBENT's WAL -- a "
        "journal for a different database under a different key.\n"
        f"  expected: no {live_wal.name}\n  actual:   still there"
    )
    moved = live_db.parent.glob(f"{live_db.name}.*.old-wal")
    assert [p for p in moved], (
        "the incumbent's WAL was not moved aside with its database, so the "
        "*.old copy that exists to be recoverable has no journal.\n"
        f"  expected: a {live_db.name}.<stamp>.old-wal\n"
        f"  actual:   {sorted(p.name for p in live_db.parent.iterdir())}"
    )
    assert dest.unlock(bytearray(_M2, "utf-8")) is True, (
        "the restored vault does not open. A foreign WAL beside it is exactly "
        "what stops it."
    )
    dest.lock()
