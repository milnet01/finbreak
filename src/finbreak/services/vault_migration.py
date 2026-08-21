"""v1 → v2 vault migration — the § 13 S0..S6 sequence (FIBR-0019).

``slots.master`` inherits the v1 vault's OWN salt and OWN recorded cost
parameters (§ 13.1), so the key the unlock path has already derived *is*
KEK-master: nothing has to carry the plaintext master password past derivation,
and a later-raised Argon2 pin cannot strand an existing vault. It is also what
makes :func:`resume` work with no separate ``legacy_salt_hex`` field — in the
window between S4 and S5 the old schedule is still fully recorded, because
KEK-master *is* the v1 database key.

There is exactly one acceptable failure mode here: the vault still opens. INV-7
is that contract, INV-13 the rollback copy that backs it, and INV-8 the rows.
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from sqlcipher3.dbapi2 import Connection, DatabaseError

from finbreak.crypto import (
    KEY_LEN,
    SlotRecord,
    VaultSidecar,
    load_and_validate_params,
    new_sidecar,
    read_sidecar_v2,
    write_sidecar_v2,
)
from finbreak.errors import VaultStateError
from finbreak.keywrap import SLOT_MASTER, wrap_dek
from finbreak.models import KdfParams
from finbreak.vault import SQLCIPHER_COMPAT, Vault

log = logging.getLogger(__name__)

# The § 13.2 step names, in order. ``on_step`` is called with each one.
STEPS = ("S0", "S1", "S2", "S3", "S4", "S5", "S6")

# Suffixes § 13.2 fixes: the D8 rollback copy (S0, removed at S6) and the
# replacement database being built (S1, unlinked first so a stale one from an
# interrupted run cannot wedge every retry with FileExistsError).
ROLLBACK_SUFFIX = ".pre-v2"
MIGRATING_SUFFIX = ".migrating"

# SQLite's WAL siblings. A vault is FOUR files, not two (§ 6): a `-wal` written
# under the OLD key surviving the S5 swap would have SQLite recover the NEW
# database from it, so S5 removes any that remain after both connections close.
_WAL_SIBLINGS = ("-wal", "-shm")


def _noop(_step: str) -> None:
    pass


def _suffixed(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _drop_wal_siblings(db_path: Path) -> None:
    for suffix in _WAL_SIBLINGS:
        _suffixed(db_path, suffix).unlink(missing_ok=True)


def _row_counts(conn: Connection) -> dict[str, int]:
    """Per-table row counts for EVERY table, enumerated from ``sqlite_master``.

    Every table, not just the ones anything seeded — S2 has to catch a
    replacement that dropped a table nobody thought to look for (INV-8).
    """
    names = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    # B608: `name` is a table name read from sqlite_master (never user input),
    # and SQLite cannot bind an identifier as a parameter — the same dynamic
    # enumeration, and the same justification, as backup.py's verify counts.
    return {
        name: conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]  # nosec B608
        for name in names
    }


def _opens(db_path: Path, key: bytearray, cipher_compat: int | None) -> bool:
    """``True`` iff ``key`` opens ``db_path``. Closes what it opens.

    ``in_memory_temp`` keeps the probe from converting the file's journal mode
    or spilling plaintext to a temp store — this is a question, not a use.
    """
    if not db_path.exists():
        return False
    probe = Vault(db_path, db_path)
    try:
        probe.open(bytearray(key), in_memory_temp=True, cipher_compat=cipher_compat)
    except DatabaseError:
        return False
    probe.close()
    return True


def write_rollback_copy(vault_path: Path, sidecar_path: Path) -> tuple[Path, Path]:
    """S0, first half — byte-copy the live pair to ``*.pre-v2`` and fsync both.

    A byte copy of an already-encrypted pair, deliberately NOT a ``.fbk``: it
    needs no new backup password, so nothing is prompted for at the first unlock
    after an update (D8). Any WAL sibling is copied with it, so a caller that
    left a checkpoint outstanding cannot produce a copy missing recent rows.

    A stray pair from a run that aborted before S4 is simply overwritten:
    nothing was ever swapped there, so the live pair it was taken from is the
    same one being copied now (§ 13.3).
    """
    copies: list[Path] = []
    for source in (vault_path, sidecar_path):
        dest = _suffixed(source, ROLLBACK_SUFFIX)
        dest.unlink(missing_ok=True)
        shutil.copyfile(source, dest)
        os.chmod(dest, 0o600)
        _fsync(dest)
        copies.append(dest)
    # Clear the copy's OWN stale siblings before copying the live ones, in that
    # order. A `-wal` left beside the copy by an earlier aborted run would
    # otherwise be recovered INTO this fresh copy — a rollback route silently
    # carrying a different vault's tail, which is the class of thing INV-13
    # exists to stop.
    _drop_wal_siblings(copies[0])
    for suffix in _WAL_SIBLINGS:
        sibling = _suffixed(vault_path, suffix)
        if sibling.exists():
            shutil.copyfile(sibling, _suffixed(copies[0], suffix))
    return copies[0], copies[1]


def verify_rollback_copy(
    copy_vault_path: Path, copy_sidecar_path: Path, key: bytearray
) -> None:
    """S0, second half — OPEN the copy with the key already in hand and read
    from it.

    Verifying it by opening it is the whole of INV-13: a truncated or
    short-written copy that merely *exists* reads as a rollback route, which is
    worse than none — it is the thing the user would be told to fall back on.
    """
    if not copy_vault_path.exists() or not copy_sidecar_path.exists():
        raise VaultStateError("the rollback copy was not written")
    load_and_validate_params(copy_sidecar_path)
    probe = Vault(copy_vault_path, copy_sidecar_path)
    probe.open(bytearray(key), in_memory_temp=True)
    try:
        probe.connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
    finally:
        probe.close()


def migrate_to_v2(
    vault_path: Path,
    sidecar_path: Path,
    key: bytearray,
    *,
    on_step: Callable[[str], None] | None = None,
) -> None:
    """Run § 13.2's S0..S6 against a CLOSED, open-able v1 vault.

    ``key`` is the v1 database key the unlock path already derived — which
    § 13.1 makes KEK-master unchanged.

    ``on_step`` is called with each step name **immediately before that step
    runs**, so a caller (or a test) that raises from ``on_step("S2")`` aborts
    the migration with S1 complete and S2 not started.
    """
    step = on_step or _noop
    params = load_and_validate_params(sidecar_path)

    step("S0")
    copy_vault, copy_sidecar = write_rollback_copy(vault_path, sidecar_path)
    verify_rollback_copy(copy_vault, copy_sidecar, key)

    dek = bytearray(secrets.token_bytes(KEY_LEN))
    _convert(vault_path, sidecar_path, key, dek, params, step)


def _convert(
    vault_path: Path,
    sidecar_path: Path,
    kek_master: bytearray,
    dek: bytearray,
    params: KdfParams,
    step: Callable[[str], None],
) -> None:
    """S1..S6 — everything after the rollback copy exists and has been opened.

    Split out because § 13.3's ladder re-enters here: a crash at or before S4
    restarts from S1 with the DEK the pending sidecar already wraps, so the
    sidecar on disk stays true throughout rather than being rebuilt around a
    second DEK.
    """
    migrating_db = _suffixed(vault_path, MIGRATING_SUFFIX)
    migrating_sidecar = _suffixed(sidecar_path, MIGRATING_SUFFIX)

    step("S1")
    # export_to pre-creates its target O_EXCL and unlinks nothing on failure, so
    # debris from an interrupted run would make every retry raise
    # FileExistsError and wedge the migration permanently (§ 6).
    migrating_db.unlink(missing_ok=True)
    _drop_wal_siblings(migrating_db)
    live = Vault(vault_path, sidecar_path)
    live.open(bytearray(kek_master))
    try:
        live.export_to(migrating_db, dek)
        _fsync(migrating_db)
        expected_counts = _row_counts(live.connection)
    finally:
        live.close()

    step("S2")
    replacement = Vault(migrating_db, migrating_sidecar)
    try:
        replacement.open(bytearray(dek), cipher_compat=SQLCIPHER_COMPAT)
        integrity = replacement.connection.execute("PRAGMA integrity_check").fetchone()[
            0
        ]
        if integrity != "ok":
            raise VaultStateError(
                f"the migrated vault failed integrity_check: {integrity}"
            )
        actual_counts = _row_counts(replacement.connection)
        if actual_counts != expected_counts:
            raise VaultStateError(
                f"the migrated vault lost rows: expected {expected_counts}, "
                f"got {actual_counts}"
            )
    except Exception:
        replacement.close()
        migrating_db.unlink(missing_ok=True)
        _drop_wal_siblings(migrating_db)
        raise
    finally:
        replacement.close()

    step("S3")
    wrapped = wrap_dek(bytes(kek_master), bytes(dek), SLOT_MASTER, params)
    pending = replace(
        new_sidecar(params, {SLOT_MASTER: SlotRecord.from_wrap(params.salt, wrapped)}),
        migration_pending=True,
        # export_to writes at an EXPLICIT cipher level while a `create`d vault
        # takes the library default. They agree today and stop agreeing the
        # moment a sqlcipher3-wheels bump moves the default — at which point a
        # migrated vault would be unopenable by the very build that migrated it.
        # So the level is recorded, and every later open passes it (§ 13.2).
        cipher_compatibility=SQLCIPHER_COMPAT,
    )
    write_sidecar_v2(migrating_sidecar, pending)
    _fsync(migrating_sidecar)

    step("S4")
    os.replace(migrating_sidecar, sidecar_path)

    step("S5")
    _swap_database(vault_path, migrating_db)

    step("S6")
    _finish(sidecar_path, pending, vault_path)


def _swap_database(vault_path: Path, migrating_db: Path) -> None:
    """S5 — drop both WAL sibling sets, then replace the database.

    Both connections are already closed by the time this runs, so each has
    checkpointed; what this removes is anything that survived. A `-wal` written
    under the OLD key left beside the NEW database would have SQLite recover
    the new database from it (§ 6).
    """
    _drop_wal_siblings(vault_path)
    _drop_wal_siblings(migrating_db)
    os.replace(migrating_db, vault_path)


def _finish(sidecar_path: Path, sidecar: VaultSidecar, vault_path: Path) -> None:
    """S6 — clear ``migration_pending``, then remove the rollback pair.

    S2 verified the replacement row for row before anything was swapped, so past
    this point the copy protects nothing and is one more plaintext-adjacent
    artefact to look after (D8's scope: the conversion window, and nothing
    after it).
    """
    write_sidecar_v2(sidecar_path, replace(sidecar, migration_pending=False))
    _suffixed(vault_path, ROLLBACK_SUFFIX).unlink(missing_ok=True)
    _drop_wal_siblings(_suffixed(vault_path, ROLLBACK_SUFFIX))
    _suffixed(sidecar_path, ROLLBACK_SUFFIX).unlink(missing_ok=True)


def rollback_copy_paths(vault_path: Path, sidecar_path: Path) -> tuple[Path, Path]:
    """Where D8's pre-upgrade pair sits — the UI's offer needs to name it."""
    return (
        _suffixed(vault_path, ROLLBACK_SUFFIX),
        _suffixed(sidecar_path, ROLLBACK_SUFFIX),
    )


def resume(
    vault_path: Path, sidecar_path: Path, kek_master: bytearray, dek: bytearray
) -> None:
    """§ 13.3 — finish a migration interrupted after S4, leaving a usable pair.

    Entered only with a v2 sidecar carrying ``migration_pending`` **and** an
    unwrapped ``slots.master``, so the password is already known to be right:
    § 13.3 step 0 is the caller's, and without it a single typo would fall
    through every branch here and tell the user their vault is corrupt.
    """
    sidecar = read_sidecar_v2(sidecar_path)
    compat = sidecar.cipher_compatibility
    migrating_db = _suffixed(vault_path, MIGRATING_SUFFIX)

    # 1 — the DEK opens the live database: the crash was after S5.
    if _opens(vault_path, dek, compat):
        log.info("migration resume: crash was after S5; finishing")
        _finish(sidecar_path, sidecar, vault_path)
        return

    # 2 — it opens the replacement instead: the crash was between S4 and S5.
    if migrating_db.exists():
        if _opens(migrating_db, dek, compat):
            log.info("migration resume: crash was between S4 and S5; swapping")
            _swap_database(vault_path, migrating_db)
            _finish(sidecar_path, sidecar, vault_path)
            return
        migrating_db.unlink(missing_ok=True)
        _drop_wal_siblings(migrating_db)

    # 3 — KEK-master itself opens it, so the database is still the v1 one and
    # the crash was at or before S4. § 13.1's inheritance is what makes this
    # reachable with no separate legacy salt: KEK-master IS the v1 key.
    if _opens(vault_path, kek_master, None):
        log.info("migration resume: crash was at or before S4; restarting from S1")
        _convert(
            vault_path,
            sidecar_path,
            kek_master,
            dek,
            sidecar.params_for(SLOT_MASTER),
            _noop,
        )
        return

    # Every route is exhausted AND the password was right, which is what makes
    # this branch meaningful. Change nothing; the caller offers D8's rollback
    # copy if one is there, and the destructive reset is never offered from here.
    raise VaultStateError(
        "the vault and its key record disagree: no database this sidecar names "
        "can be opened with the key it holds"
    )
