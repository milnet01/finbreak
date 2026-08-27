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
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

from sqlcipher3.dbapi2 import Connection, DatabaseError

from finbreak.crypto import (
    KEY_LEN,
    SIDECAR_VERSION,
    SlotRecord,
    VaultSidecar,
    load_and_validate_params,
    new_sidecar,
    read_sidecar_v2,
    sidecar_version,
    write_sidecar_json,
    write_sidecar_v2,
)
from finbreak.errors import KdfPolicyError, RollbackAvailableError, VaultStateError
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
    """Flush ``path`` to the platter. Raises if it cannot — INV-13 means a copy
    that is not durable is not a copy.

    ``O_RDWR``, not ``O_RDONLY``. POSIX allows fsync on a read-only descriptor;
    Windows maps ``os.fsync`` to ``_commit`` and thence to
    ``FlushFileBuffers``, which wants write access. **Measured on
    windows-latest / CPython 3.12.10, 2026-08-25**: ``O_RDONLY`` raises
    ``OSError(9, 'Bad file descriptor')`` and ``O_RDWR`` succeeds.

    The consequence of the old flag was not a crash the user could see. S0
    calls this on the rollback copy, ``migrate_to_v2`` is wrapped by
    ``AuthService._unlock_v1``'s ``except Exception``, and the sidecar is still
    v1 at that point — so the vault opened, the migration was abandoned, and
    the next unlock did the same. **No Windows vault would ever have reached
    the v2 envelope, and no Windows user would ever have been offered a
    recovery key** (FIBR-0310 P1).

    ``backup.py``'s ``_fsync_directory`` keeps ``O_RDONLY``, and that is not an
    inconsistency: a directory cannot be opened for writing, which is why that
    one degrades instead of raising.
    """
    fd = os.open(path, os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_owner_only(source: Path, dest: Path) -> None:
    """Copy ``source`` over ``dest``, owner-only from the first byte written.

    ``shutil.copyfile`` creates at the process umask and a ``chmod`` afterwards
    closes the mode only once the bytes are already there — so the copy of an
    entire vault sat world-readable for the length of the copy, which on a large
    vault is the length of the exposure. ``vault.py`` mounts the answer twice
    (``create`` and ``export_to``): pre-create the target ``0o600`` before
    anything writes into it (FIBR-0310 P3).

    ``O_EXCL`` and ``O_NOFOLLOW`` close the other half. The old sequence was
    unlink-then-copy, and a symlink planted at ``dest`` in between was followed,
    writing the vault wherever it pointed. ``O_EXCL`` refuses a path that exists
    at all by the time we get there, which includes a symlink;
    ``O_NOFOLLOW`` says so explicitly and is absent on Windows, where
    ``getattr`` makes it a no-op — the same idiom ``crypto.write_sidecar_json``
    uses.
    """
    dest.unlink(missing_ok=True)
    fd = os.open(
        dest,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "wb") as out, open(source, "rb") as handle:
        shutil.copyfileobj(handle, out)


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
    or spilling plaintext to a temp store, and ``migrate=False`` keeps it from
    running the schema migrations — this is a question, not a use.

    That last one was the sentence's claim and not its behaviour.
    ``Vault.open`` runs ``run_migrations``, which COMMITS, so § 13.3 branch 3
    asked "does KEK-master open this?" by writing to the live v1 database —
    before ``_ensure_rollback_copy`` had secured anything. INV-13 says no byte
    of the live pair moves until a verified copy exists (FIBR-0310 P7).
    """
    if not db_path.exists():
        return False
    probe = Vault(db_path, db_path)
    try:
        probe.open(
            bytearray(key),
            in_memory_temp=True,
            cipher_compat=cipher_compat,
            migrate=False,
        )
    except DatabaseError:
        return False
    probe.close()
    return True


def _reads_end_to_end(db_path: Path, key: bytearray, cipher_compat: int | None) -> bool:
    """``True`` iff ``key`` opens ``db_path`` AND every page of it reads back.

    The strong form of :func:`_opens`, and the difference is the one
    :func:`verify_rollback_copy` measured on 2026-08-24: SQLCipher HMACs every
    page independently, so damage in the middle of a file leaves page 1
    perfectly decryptable — it opens, its schema is intact, and every row is
    unreachable.

    S6 on the resume path DELETES the pre-upgrade copy, which is the user's
    only route back, and branches 1 and 2 reached it having asked only
    :func:`_opens` (FIBR-0310 P6). A full read costs a pass over the vault, and
    it is paid only while ``migration_pending`` is set — after an interrupted
    migration, once.
    """
    if not db_path.exists():
        return False
    probe = Vault(db_path, db_path)
    try:
        probe.open(
            bytearray(key),
            in_memory_temp=True,
            cipher_compat=cipher_compat,
            migrate=False,
        )
    except DatabaseError:
        return False
    try:
        return bool(
            probe.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        )
    except (DatabaseError, MemoryError):
        # A page whose HMAC fails surfaces as whatever the deferred error maps
        # to; both were seen in the measurement above. Either way this file does
        # not read end to end.
        return False
    finally:
        probe.close()


def _row_counts_or_none(
    db_path: Path, key: bytearray, cipher_compat: int | None
) -> dict[str, int] | None:
    """Per-table row counts, or ``None`` where the file will not give them up.

    The counting half of S2, as a question rather than an assertion — S2 raises
    because it is mid-migration and owns the abort, while § 13.3's ladder has a
    next branch to fall through to. ``None`` folds "will not open", "is not
    there" and "a page failed on the way through" into the one answer the
    caller can act on, which is that this file cannot be compared.
    """
    if not db_path.exists():
        return None
    probe = Vault(db_path, db_path)
    try:
        probe.open(
            bytearray(key),
            in_memory_temp=True,
            cipher_compat=cipher_compat,
            migrate=False,
        )
    except DatabaseError:
        return None
    try:
        return _row_counts(probe.connection)
    except (DatabaseError, MemoryError):
        return None
    finally:
        probe.close()


def _replacement_is_sound(
    vault_path: Path,
    migrating_db: Path,
    kek_master: bytearray,
    dek: bytearray,
    cipher_compat: int | None,
) -> bool:
    """S2's two checks, asked again before § 13.3 branch 2 swaps.

    Branch 2 swapped on :func:`_opens` alone — the weak check this module
    measured on 2026-08-24, which a file damaged in the middle passes — and
    ``_swap_database`` then replaced the user's INTACT v1 database with it.
    Discovering afterwards that the result does not read is too late: the thing
    it was compared against is gone (FIBR-0313 H1).

    Reaching branch 2 means S4 completed, so S2 passed on this file once
    already. What it cannot have seen is damage AFTER that — a bad sector, a
    partial write — which is why the question is worth asking a second time
    rather than trusted from the first.

    The row compare is available here for the same reason the swap is
    dangerous: S5 has not run, so ``vault.db`` is still the v1 database the
    counts came from, and § 13.1's inheritance means KEK-master opens it. A
    live vault that will not give up its counts returns ``False`` too — there
    is nothing to compare against, and swapping on no evidence is the defect.
    """
    if not _reads_end_to_end(migrating_db, dek, cipher_compat):
        return False
    live_counts = _row_counts_or_none(vault_path, kek_master, None)
    if live_counts is None:
        log.warning(
            "migration resume: the live vault will not give up its row counts, "
            "so the replacement cannot be compared against it"
        )
        return False
    replacement_counts = _row_counts_or_none(migrating_db, dek, cipher_compat)
    if replacement_counts != live_counts:
        log.warning(
            "migration resume: the replacement lost rows: expected %s, got %s",
            live_counts,
            replacement_counts,
        )
        return False
    return True


def write_rollback_copy(
    vault_path: Path,
    sidecar_path: Path,
    *,
    sidecar_payload: Mapping[str, object] | None = None,
) -> tuple[Path, Path]:
    """S0, first half — copy the live pair to ``*.pre-v2`` and fsync both.

    A byte copy of an already-encrypted pair, deliberately NOT a ``.fbk``: it
    needs no new backup password, so nothing is prompted for at the first unlock
    after an update (D8). Any WAL sibling is copied with it, so a caller that
    left a checkpoint outstanding cannot produce a copy missing recent rows.

    A stray pair from a run that aborted before S4 is simply overwritten:
    nothing was ever swapped there, so the live pair it was taken from is the
    same one being copied now (§ 13.3).

    ``sidecar_payload`` REPLACES the sidecar half — the database is still byte
    copied — and exists for exactly one caller, the § 13.3 branch-3 retake,
    where the live sidecar is no longer the pre-upgrade one. Writing it here
    rather than overwriting the copy afterwards is deliberate: the two-step
    version leaves a v2 ``.pre-v2`` on disk between the write and the fix, which
    is the state this whole argument exists to prevent (FIBR-0310 R4).
    """
    copies: list[Path] = []
    for source in (vault_path, sidecar_path):
        dest = _suffixed(source, ROLLBACK_SUFFIX)
        if source is sidecar_path and sidecar_payload is not None:
            dest.unlink(missing_ok=True)
            write_sidecar_json(dest, sidecar_payload)  # already fsynced + 0o600
        else:
            _copy_owner_only(source, dest)
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
            # Owner-only too: a `-wal` holds the same rows as the database it
            # belongs to, so copying it at the umask leaks exactly what copying
            # the database at the umask would (FIBR-0310 P3).
            _copy_owner_only(sibling, _suffixed(copies[0], suffix))
    return copies[0], copies[1]


def verify_rollback_copy(
    copy_vault_path: Path, copy_sidecar_path: Path, key: bytearray
) -> None:
    """S0, second half — OPEN the copy with the key already in hand and read
    from it.

    Verifying it by opening it is the whole of INV-13: a truncated or
    short-written copy that merely *exists* reads as a rollback route, which is
    worse than none — it is the thing the user would be told to fall back on.

    **Opening it is not enough, and ``PRAGMA integrity_check`` is the whole of
    the difference.** SQLCipher HMACs every page independently and checks each
    one as it is read, so damage to the middle of a copy leaves page 1
    perfectly decryptable: ``Vault.open``'s own guard read passes, a
    ``sqlite_master`` count passes, and every row is still unreachable.
    Measured 2026-08-24 on a 93-page vault — one flipped byte in page 11, 41,
    81 and 93 in turn, and all four copies opened with their schema intact
    while ``integrity_check`` caught every one (FIBR-0307 finding 8).

    A copy that is merely SHORT needs none of this: SQLite refuses a file
    smaller than its own header claims, at ``open``. So a truncation is not the
    shape this guards against, however it reads — the shape is a copy of the
    right length whose pages did not all survive the write.

    Row counts are S2's tool and are deliberately not repeated here. There they
    are compared against the live vault, which is what proves INV-8; at S0
    nothing exists to compare them to, so a second full read of the pages
    ``integrity_check`` has just walked would buy nothing.
    """
    if not copy_vault_path.exists() or not copy_sidecar_path.exists():
        raise VaultStateError("the rollback copy was not written")
    # A PRE-upgrade pair is v1 on both halves, by definition: S0 takes it before
    # S4 replaces the sidecar. A v2 sidecar here means the copy was taken from a
    # pair already mid-migration, and restoring it puts the user back in the
    # state they asked to leave — the next unlock re-enters branch 3 and
    # restarts the migration. `load_and_validate_params` accepts BOTH shapes, so
    # nothing below would notice (FIBR-0310 R4).
    if sidecar_version(copy_sidecar_path) == SIDECAR_VERSION:
        raise VaultStateError(
            "the rollback copy's key record is a v2 sidecar, so it is not a "
            "pre-upgrade pair"
        )
    load_and_validate_params(copy_sidecar_path)
    probe = Vault(copy_vault_path, copy_sidecar_path)
    probe.open(bytearray(key), in_memory_temp=True)
    try:
        integrity = probe.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity == "ok":
            # Fold the copy's WAL into the copy itself, so it is ONE file from
            # here on. `restore_rollback_copy` moves the database and its `-wal`
            # with two separate os.replace calls, and a crash between them drops
            # the tail — a rollback quietly missing the user's most recent rows.
            #
            # It never happened, because closing the probe below checkpoints and
            # removes the WAL anyway (measured 2026-08-25: the copy has a `-wal`
            # after write_rollback_copy and none after this function). But that
            # is close-time behaviour nothing here asked for, so the guarantee
            # rested on a side effect of a function whose job is to READ
            # (FIBR-0310 R9). Asking for it makes it a step that can be cited.
            #
            # After integrity_check, never before: a copy that fails is left
            # exactly as it was found rather than written to.
            probe.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except (DatabaseError, MemoryError) as exc:
        # SQLCipher surfaces a page whose HMAC fails as whatever its deferred
        # error maps to; both of these were seen in the measurement above. The
        # caller needs one answer, and it is that this is not a rollback route.
        raise VaultStateError(
            f"the rollback copy could not be read end to end: {exc}"
        ) from exc
    finally:
        probe.close()
    if integrity != "ok":
        raise VaultStateError(f"the rollback copy failed integrity_check: {integrity}")


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

    # The DEK is minted HERE, so this is the only frame that can wipe it:
    # _convert is lent the buffer and cannot know whether its caller still
    # wants it. The finally is what covers an abort inside S1..S6 — which is
    # precisely when a database key would otherwise be left in the heap
    # (security-model INV-3, FIBR-0307 finding 4).
    dek = bytearray(secrets.token_bytes(KEY_LEN))
    try:
        _convert(vault_path, sidecar_path, key, dek, params, step)
    finally:
        dek[:] = bytes(len(dek))


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
    wrapped = wrap_dek(kek_master, bytes(dek), SLOT_MASTER, params)
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
    """S6 — remove the rollback pair, then clear ``migration_pending``.

    S2 verified the replacement row for row before anything was swapped, so past
    this point the copy protects nothing and is one more plaintext-adjacent
    artefact to look after (D8's scope: the conversion window, and nothing
    after it).

    **The removal goes FIRST, and the order is what makes an interrupted S6
    survivable.** ``migration_pending`` is the only thing that brings anything
    back here: clearing it first and then failing to unlink — the disk-full and
    held-file class § 6 names, which :func:`_finish_quietly` absorbs — leaves
    the ``.pre-v2`` pair on disk with no bookkeeping left to remove it, and
    nothing ever tries again. That is an encrypted copy of the user's vault
    that still opens under the master password they had at the time, sitting
    beside the live one and surviving every later password change
    (FIBR-0310 R8).

    Failing the other way costs nothing. The flag stays set, the next unlock
    takes § 13.3 branch 1 — the DEK opens the live database — and lands back
    here, where the unlinks are ``missing_ok`` and the write is idempotent.
    """
    _suffixed(vault_path, ROLLBACK_SUFFIX).unlink(missing_ok=True)
    _drop_wal_siblings(_suffixed(vault_path, ROLLBACK_SUFFIX))
    _suffixed(sidecar_path, ROLLBACK_SUFFIX).unlink(missing_ok=True)
    write_sidecar_v2(sidecar_path, replace(sidecar, migration_pending=False))


def rollback_copy_paths(vault_path: Path, sidecar_path: Path) -> tuple[Path, Path]:
    """Where D8's pre-upgrade pair sits, as a PAIR.

    Both callers are in this module and each needs both paths at once:
    :func:`rollback_copy_is_usable` verifies them together, and
    :func:`restore_rollback_copy` moves them in a fixed order. So this is the
    one place the two suffixes are derived side by side, and the ordering of
    the returned tuple is part of it.

    It said "the UI's offer needs to name it", and the offer shipped naming no
    path — ``ui/unlock.py``'s ``_rollback_offer`` describes the copy in words
    and never shows where it is. Nothing outside this module calls this at all
    (FIBR-0310 R7).
    """
    return (
        _suffixed(vault_path, ROLLBACK_SUFFIX),
        _suffixed(sidecar_path, ROLLBACK_SUFFIX),
    )


def rollback_copy_is_usable(
    vault_path: Path, sidecar_path: Path, key: bytearray
) -> bool:
    """``True`` iff D8's pre-upgrade pair is there AND opens with ``key``.

    The question :func:`verify_rollback_copy` answers, asked where the answer
    is a decision rather than a gate. INV-13's point is that a copy which
    merely EXISTS is worse than none — it is the artefact the user would be
    told to fall back on — so anything short of a full read is a ``False``
    here, and the offer is not made.
    """
    copy_vault, copy_sidecar = rollback_copy_paths(vault_path, sidecar_path)
    try:
        verify_rollback_copy(copy_vault, copy_sidecar, key)
    except (VaultStateError, KdfPolicyError, DatabaseError, OSError) as exc:
        log.info("no usable pre-upgrade copy beside the vault: %s", exc)
        return False
    return True


def restore_rollback_copy(vault_path: Path, sidecar_path: Path) -> None:
    """Put D8's pre-upgrade pair back over the live one — § 13.3's way out.

    The copy is MOVED, not duplicated: it is the live pair afterwards, and
    leaving a second plaintext-adjacent copy of the vault behind is the thing
    S6 exists to prevent.

    **The database goes first and the sidecar second**, and the order is what
    makes an interruption survivable. Crashing between the two leaves the v1
    database under the still-migration-pending v2 sidecar, which is § 13.3
    branch 3 — KEK-master opens it, the ladder restarts from S1, and
    :func:`_ensure_rollback_copy` retakes the copy this call consumed. The
    other order leaves a v1 sidecar over a database no v1 key opens, which
    reads to the user as a wrong password (§ 6).

    The live pair's WAL siblings are dropped: a ``-wal`` written under the OLD
    key beside the restored database would have SQLite recover that database
    from it, which is § 6's hazard and the one S5 handles.

    **The copy is expected to have no WAL of its own**, and that is a
    precondition rather than a hope. Every route here runs
    :func:`verify_rollback_copy` first, which checkpoints the copy into a single
    file precisely so this function moves ONE database rather than a database
    and its tail — two ``os.replace`` calls, with a crash between them leaving a
    rollback silently missing the user's most recent rows (FIBR-0310 R9).

    The loop below is what happens if it is there anyway, and its order is the
    less bad of two. Moving the WAL after the database can lose the tail; moving
    it BEFORE leaves the migrated v2 database under a v1-keyed WAL, where
    nothing opens and § 13.3 has no branch to recover by. Losing the tail leaves
    a vault that opens.
    """
    copy_vault, copy_sidecar = rollback_copy_paths(vault_path, sidecar_path)
    _drop_wal_siblings(vault_path)
    os.replace(copy_vault, vault_path)
    for suffix in _WAL_SIBLINGS:
        sibling = _suffixed(copy_vault, suffix)
        if sibling.exists():
            log.warning(
                "the pre-upgrade copy still has a %s; it was not checkpointed "
                "before the restore",
                suffix,
            )
            os.replace(sibling, _suffixed(vault_path, suffix))
    os.replace(copy_sidecar, sidecar_path)
    log.info("the pre-upgrade copy was restored over the live pair")


def _finish_quietly(
    sidecar_path: Path, sidecar: VaultSidecar, vault_path: Path
) -> None:
    """S6 on the RESUME path, where the vault has just been proven to open.

    Branches 1 and 2 reach S6 having opened the post-migration database with
    the DEK, so INV-7's contract is already met and everything S6 does after
    that is bookkeeping: clearing ``migration_pending`` and removing the
    ``.pre-v2`` pair. § 6 hands a disk-full at S1..S6 to § 13's resume rules,
    and those rules cannot mean "lock the user out of a vault that opens".

    A failure leaves ``migration_pending`` set, so the state stays resumable and
    the next unlock re-enters branch 1 and finishes the job. Only ``OSError`` is
    absorbed — the disk-full and held-file class § 6 names. Any other failure
    here is a defect and still reaches the caller (FIBR-0307 finding 3).

    That sentence used to read "leaves the sidecar exactly as it was", and it
    was false for the case it most needed to cover: :func:`_finish` cleared the
    flag before unlinking, so an ``OSError`` on the unlink left the copy on disk
    with nothing to bring anything back to it. :func:`_finish` now removes the
    copy first, which is what makes the claim true rather than restated
    (FIBR-0310 R8).
    """
    try:
        _finish(sidecar_path, sidecar, vault_path)
    except OSError as exc:
        log.warning("migration resume: S6 bookkeeping did not complete: %s", exc)


def _finish_if_readable(
    sidecar_path: Path,
    sidecar: VaultSidecar,
    vault_path: Path,
    dek: bytearray,
    cipher_compat: int | None,
    kek_master: bytearray,
) -> None:
    """S6, but only once the vault it is about to burn the rollback for READS.

    Branches 1 and 2 established that the DEK opens the post-migration
    database, and S6 then deletes the ``.pre-v2`` pair — the user's only route
    back — on the strength of that. Opening is the weaker check, and this
    module measured how much weaker on 2026-08-24: a file damaged in the middle
    opens with its schema intact and every row unreachable (FIBR-0310 P6).

    A vault that opens but does not read keeps BOTH: the copy stays, and
    ``migration_pending`` stays set. **Keeping them is not the same as offering
    them, and this returned here saying it was** — the sentence read "so the
    rollback is still offered", and nothing raised. ``resume``'s branch 1
    matches on the DEK opening the live database, which is still true at every
    later unlock, so the terminal branch that makes the offer was unreachable:
    the user was let into a vault with unreachable rows, at that unlock and
    every one after it, with a verified pre-upgrade pair beside them and
    nothing saying so (FIBR-0313 C1).

    So the offer is made HERE, on the terminal branch's own terms — the pair is
    on disk and opens with the key the user has just proved. INV-7 is what
    settles it rather than a preference for raising: the contract is that the
    pre- or the post-migration pair opens *with every row intact*, and the
    database in front of us is not that one. The ``.pre-v2`` pair is, and
    raising is how the user reaches it.

    Where no usable copy is beside the vault there is nothing to offer, so the
    caller goes on to open the vault as before. That state is INV-7 already
    broken with no route back, which this cannot mend and does not pretend to.
    """
    if not _reads_end_to_end(vault_path, dek, cipher_compat):
        log.warning(
            "migration resume: the vault opens but does not read end to end; "
            "keeping the pre-upgrade copy and leaving the migration pending"
        )
        if rollback_copy_is_usable(vault_path, sidecar_path, kek_master):
            raise RollbackAvailableError(
                "the vault opens but does not read end to end, and a copy "
                "taken before the upgrade is beside it"
            )
        return
    _finish_quietly(sidecar_path, sidecar, vault_path)


def _ensure_rollback_copy(
    vault_path: Path, sidecar_path: Path, key: bytearray, sidecar: VaultSidecar
) -> None:
    """INV-13's gate for § 13.3's branch 3, which re-enters ``_convert``.

    That restart runs S4, which replaces the live sidecar — a byte of the live
    pair — so the gate applies here exactly as it does at S0: a copy that
    exists, is complete, and opens with the key in hand. § 13.3 says only
    "restart from S1", and INV-13 carries no carve-out for the resume path.

    **The copy S0 already took is REUSED where it still verifies, and that is
    not an optimisation.** It is the genuine pre-upgrade pair — a v1 database
    beside a v1 sidecar — and the live pair here is no longer that: S4 has
    already replaced the sidecar with the migration-pending v2 one. Copying the
    live pair over it would leave a "rollback" that restores the very state the
    user is stuck in. § 13.2's S0 overwrites a stray copy freely because there
    the live pair IS the pre-upgrade pair; past S4 that stops being true
    (D8, FIBR-0307 finding 6).

    Where no usable copy is there, a fresh one is taken and verified, and a
    failure to get one aborts before ``_convert`` — § 6's "never proceed
    without it", which is most needed exactly when the disk is tight.

    **The retake REBUILDS the sidecar half rather than copying it**, which is
    what makes the paragraph above true of this branch rather than only of S0.
    Byte-copying the live pair here writes the migration-pending v2 sidecar as
    the ``.pre-v2`` one, so the "rollback" restores the stalled state and the
    next unlock re-enters branch 3 and restarts the very migration the user
    asked to undo (FIBR-0310 R4). The database needs no such treatment: branch 3
    is reached only because KEK-master opens it, so it IS still the v1 database.
    And the v1 sidecar is recoverable with nothing kept aside, because § 13.1's
    inheritance means ``slots.master`` derives under the v1 record unchanged —
    its params ARE the pre-upgrade sidecar.
    """
    if rollback_copy_is_usable(vault_path, sidecar_path, key):
        return
    log.warning("migration resume: the rollback copy is unusable; retaking it")
    copy_vault, copy_sidecar = write_rollback_copy(
        vault_path,
        sidecar_path,
        sidecar_payload=sidecar.params_for(SLOT_MASTER).to_sidecar_dict(),
    )
    verify_rollback_copy(copy_vault, copy_sidecar, key)


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
        _finish_if_readable(sidecar_path, sidecar, vault_path, dek, compat, kek_master)
        return

    # 2 — a sound replacement is sitting there: the crash was between S4 and S5.
    if migrating_db.exists():
        if _replacement_is_sound(vault_path, migrating_db, kek_master, dek, compat):
            log.info("migration resume: crash was between S4 and S5; swapping")
            # _swap_database moves a byte of the live pair, so INV-13's gate
            # applies here exactly as branch 3 applies it before _convert.
            _ensure_rollback_copy(vault_path, sidecar_path, kek_master, sidecar)
            _swap_database(vault_path, migrating_db)
            _finish_if_readable(
                sidecar_path, sidecar, vault_path, dek, compat, kek_master
            )
            return
        # Not sound, so it is debris rather than a replacement. The live v1
        # database is untouched and branch 3 restarts from S1 with it, which is
        # what § 13.3 prescribes for a crash at or before S4 anyway.
        log.warning(
            "migration resume: the replacement database is not sound; "
            "discarding it and falling through to restart the migration"
        )
        migrating_db.unlink(missing_ok=True)
        _drop_wal_siblings(migrating_db)

    # 3 — KEK-master itself opens it, so the database is still the v1 one and
    # the crash was at or before S4. § 13.1's inheritance is what makes this
    # reachable with no separate legacy salt: KEK-master IS the v1 key.
    if _opens(vault_path, kek_master, None):
        log.info("migration resume: crash was at or before S4; restarting from S1")
        _ensure_rollback_copy(vault_path, sidecar_path, kek_master, sidecar)
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
    # this branch meaningful. Change nothing; the destructive reset is never
    # offered from here.
    #
    # Where D8's pre-upgrade pair is on disk and opens with the key just proven,
    # the caller is told so with its own error type — § 13.3 calls making that
    # offer "the whole return on D8", and the distinction has to be drawn HERE
    # because this is the only frame holding both the key and the paths
    # (FIBR-0307 finding 7).
    if rollback_copy_is_usable(vault_path, sidecar_path, kek_master):
        raise RollbackAvailableError(
            "the vault and its key record disagree, and a copy taken before "
            "the upgrade is beside them"
        )
    raise VaultStateError(
        "the vault and its key record disagree: no database this sidecar names "
        "can be opened with the key it holds"
    )
