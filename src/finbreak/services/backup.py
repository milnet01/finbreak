"""BackupService — encrypted backup export / restore (FIBR-0014).

The ``.fbk`` is a portable, self-contained, encrypted backup: a stdlib **zip** of
three entries — ``manifest.json`` (plaintext version integers), ``params.json``
(the KDF sidecar shape with a **fresh per-backup salt**), and ``vault.db`` (the
vault re-keyed to ``Argon2id(backup password)``, HMAC on). It is keyed by a
**separate** backup password, so a forgotten master password is recoverable with
the backup password + a *new* master password — never the old master (ADR-0003 /
security-model.md T11).

Export is synchronous on the main thread (no worker), so a blocked event loop
means the auto-lock timer cannot fire mid-export (INV-9). Every derived key and
the password buffer are wiped in a ``finally`` on all paths (INV-7).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from sqlcipher3.dbapi2 import DatabaseError

import finbreak
from finbreak.crypto import (
    KEY_LEN,
    SlotRecord,
    derive_key,
    fsync_dir,
    load_and_validate_params,
    new_sidecar,
    validate_untrusted_params,
    write_sidecar_v2,
)
from finbreak.errors import BackupError, KdfPolicyError, SchemaVersionError
from finbreak.keywrap import SLOT_MASTER, wrap_dek
from finbreak.migrations import LATEST_SCHEMA_VERSION
from finbreak.services.auth import AuthService, _wipe
from finbreak.vault import (
    SQLCIPHER_COMPAT,
    SQLCIPHER_COMPAT_ACCEPTED,
    Vault,
    old_copy_sets,
)

log = logging.getLogger(__name__)

# The backup-password floor (mirrors the PDF-export floor, the user's policy).
# Lives here in a NON-UI module so it is not an upward import from ui/.
MIN_BACKUP_PASSWORD_LEN = 8

# The `.fbk` container-shape version — distinct from models.FORMAT_VERSION (the
# sidecar shape, also 1 today); kept separate so the two version checks can't
# conflate (INV-4).
MANIFEST_FORMAT_VERSION = 1

# INV-12 decompression-bomb caps, checked against ZipInfo.file_size BEFORE
# inflating. Tight on the JSON entries (the real bomb vector); generous on the DB
# (a large multi-year vault, well above the 16 MiB statement-import cap).
#
# MAX_BACKUP_DB_BYTES binds BOTH directions (INV-14, FIBR-0313 M1): export refuses
# a vault.db over it as well. Enforced on restore alone, it let an oversized vault
# export, report "Backup saved", and then be unrestorable on every machine.
MAX_MANIFEST_BYTES = 64 * 1024
MAX_BACKUP_DB_BYTES = 512 * 1024 * 1024

# INV-12's second half: reject a suspicious file_size/compress_size ratio. The caps
# alone are not enough, because a bomb sized to land exactly ON a cap passes them —
# measured, a ~500 KB hostile .fbk whose vault.db is deflated zeros inflates to the
# full 512 MiB in RAM, pre-login, on the restore path.
#
# ZIP_STORED closes this for files finbreak WRITES; restore reads an untrusted file
# and must not assume its own writer produced it. An honest stored entry has a ratio
# of exactly 1, and a deflated JSON manifest of a few hundred bytes stays far under
# 100 — so this rejects only what no legitimate `.fbk` looks like.
MAX_COMPRESSION_RATIO = 100

# The single test seam: invoked with (role, buffer) for each derived key — role in
# {"backup", "master", "dek", "post_move_aside"} — so a test captures the buffer
# to assert it is zeroed after the call, and may raise to inject a failure at that
# point. "dek" is FIBR-0019's: a restore mints a random DEK and wraps it under the
# new master password, so the restored vault has a key of its own (FIBR-0310 P11).
OnKey = Callable[[str, bytearray], None]

_MANIFEST_ENTRY = "manifest.json"
_PARAMS_ENTRY = "params.json"
_DB_ENTRY = "vault.db"

# SQLite's WAL siblings — a vault on disk is FOUR files, not two (§ 6). Named
# here for `_install`, which has to carry the INCUMBENT's aside with it; the
# restored database has none of its own, because the assembly connection runs
# with `in_memory_temp` and so keeps a self-contained rollback journal
# (vault.open, FIBR-0014 INV-1). Mirrors vault_migration._WAL_SIBLINGS.
_WAL_SIBLINGS = ("-wal", "-shm")


def _noop_on_key(role: str, buffer: bytearray) -> None:
    return None


def _fsync_file(path: Path) -> None:
    """Flush ``path``'s CONTENTS to stable storage before it is renamed into place.

    ``O_RDWR``, not ``O_RDONLY``: Windows maps ``os.fsync`` to ``_commit`` and
    thence to ``FlushFileBuffers``, which wants write access. Mirrors
    ``vault_migration._fsync``, whose docstring carries the measurement.

    Unlike ``_fsync_dir`` this RAISES rather than degrading. A directory fsync is
    genuinely unportable, so failing an otherwise complete write over it would be
    worse than the gap; a file that cannot be flushed is a vault installed with no
    guarantee it survives the next power loss, and there is no partial credit
    version of that (FIBR-0313 M2)."""
    fd = os.open(path, os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class VerifyResult:
    """The outcome of a read-only ``verify_backup`` probe (FIBR-0033).

    ``ok`` is the headline answer. On success ``schema_version`` is the
    **as-migrated** version (``== LATEST_SCHEMA_VERSION`` — ``open`` upgrades the
    temp copy) and ``table_counts`` maps each application table to its row count;
    ``reason`` is ``None``. On failure both are ``None`` and ``reason`` is a
    **stable code** (never raw exception text) the UI maps to a translated
    message — see the reason table in the FIBR-0033 spec."""

    ok: bool
    schema_version: int | None
    table_counts: dict[str, int] | None
    reason: str | None


class BackupService:
    def __init__(self, vault: Vault, auth: AuthService):
        self._vault = vault
        self._auth = auth  # for new_params() (fresh backup / master salts)

    # -- export ---------------------------------------------------------------
    def export_backup(
        self, dest: Path, backup_password: str, *, on_key: OnKey | None = None
    ) -> None:
        """Write an encrypted ``.fbk`` backup of the unlocked vault to ``dest``.

        Derives a backup key from ``backup_password`` + a fresh salt, re-keys a
        copy of the vault to it (``Vault.export_to``), and frames it with the
        manifest + params into an atomically-written zip. Enforces
        ``MIN_BACKUP_PASSWORD_LEN`` (defence in depth, not only the UI). The backup
        key + password buffer are wiped on every path; a mid-export failure leaves
        no partial ``.fbk`` and no temp (INV-7). Refuses a ``vault.db`` over
        ``MAX_BACKUP_DB_BYTES`` rather than writing a backup restore could never
        take back (INV-14)."""
        on_key = on_key or _noop_on_key
        if len(backup_password) < MIN_BACKUP_PASSWORD_LEN:
            raise ValueError(
                f"backup password must be at least {MIN_BACKUP_PASSWORD_LEN} chars"
            )
        password_buf = bytearray(backup_password, "utf-8")
        backup_key: bytearray | None = None
        # The temp zip sits beside the destination so the os.replace is a
        # same-filesystem rename; unlinked on any failure (no partial .fbk).
        tmp_zip = dest.with_name(dest.name + ".tmp")
        # The temp name is derived from the destination the user picked, so a
        # file of that name may be someone's and not ours. Only the cleanup
        # below is gated on this: `_write_fbk`'s own unlink stays unconditional,
        # because clearing the path is what lets O_EXCL win the race against a
        # planted symlink, and no ownership check ahead of it is not itself one.
        tmp_is_ours = False
        try:
            params = self._auth.new_params()  # fresh per-backup salt (INV-3)
            backup_key = derive_key(password_buf, params.salt, params)
            on_key("backup", backup_key)  # capture / inject-failure seam
            schema_version = self._vault.connection.execute(
                "SELECT version FROM schema_version"
            ).fetchone()[0]
            manifest = {
                "format_version": MANIFEST_FORMAT_VERSION,
                "app_version": finbreak.__version__,
                "schema_version": schema_version,
                "sqlcipher_compat": SQLCIPHER_COMPAT,
            }
            # The intermediate backup DB is already AES-encrypted (backup-keyed),
            # so it may live in the system temp dir; only the final zip needs to
            # land same-filesystem as dest. TemporaryDirectory removes it on exit.
            with tempfile.TemporaryDirectory() as td:
                tmp_db = Path(td) / _DB_ENTRY
                self._vault.export_to(tmp_db, backup_key)
                # Refuse what restore could never take back (INV-14, FIBR-0313 M1).
                # `_read_capped` rejects on `file_size > MAX_BACKUP_DB_BYTES`, and
                # `vault.db` is stored ZIP_STORED, so this file's size IS the
                # `file_size` restore will measure — `>`, never `>=`, keeps the two
                # ends symmetric. Here is the only point where the user still HAS
                # the vault: past it, an over-cap `.fbk` reports success and is
                # unrestorable everywhere.
                db_bytes = tmp_db.stat().st_size
                if db_bytes > MAX_BACKUP_DB_BYTES:
                    raise BackupError(
                        f"vault is too large to back up: {db_bytes} bytes exceeds "
                        f"the {MAX_BACKUP_DB_BYTES}-byte restore cap"
                    )
                tmp_is_ours = True
                self._write_fbk(tmp_zip, manifest, params.to_sidecar_dict(), tmp_db)
            os.replace(tmp_zip, dest)
            fsync_dir(dest.parent)
            log.info("backup exported")
        except BaseException:
            if tmp_is_ours:
                tmp_zip.unlink(missing_ok=True)
            raise
        finally:
            _wipe(backup_key)
            _wipe(password_buf)

    # -- restore --------------------------------------------------------------
    def restore_backup(
        self,
        src: Path,
        backup_password: str,
        new_master_password: str,
        *,
        on_key: OnKey | None = None,
    ) -> None:
        """Restore an encrypted ``.fbk``, replacing the current vault with one keyed
        by ``new_master_password`` — recovering the data with only the backup
        password + a new master, never the old master (INV-3).

        Reads the three fixed entries safely (INV-12), re-validates the backup's
        KDF params against the pinned floor before deriving any key (INV-11),
        guards the version both from the manifest (early) and the embedded table
        (on open, INV-6), assembles the new vault in a temp inside
        ``AppDataLocation`` (so the install ``os.replace`` can't cross-device),
        moves any existing vault aside to ``*.old`` (INV-5), then installs the
        restored pair (``vault.db`` first). Every derived key + password buffer is
        wiped on all paths; any underlying failure changes nothing on disk and is
        normalised to ``BackupError`` (INV-4)."""
        on_key = on_key or _noop_on_key
        if self._vault.is_open:
            # INV-8 makes restore pre-login only, and `_install` depends on it:
            # it moves the LIVE vault.db aside with os.replace. On Windows that
            # raises over an open handle, loudly and before anything changes; on
            # POSIX the rename SUCCEEDS and the still-open connection goes on
            # reading and writing the detached inode, so the user's later edits
            # land in a file nothing will open again. Held by the single
            # pre-login caller until now, which is a guarantee no code states
            # (INV-16).
            raise BackupError("restore requires a locked vault")
        if len(new_master_password) == 0:
            raise ValueError("new master password must not be empty")
        master_pw = bytearray(new_master_password, "utf-8")
        master_key: bytearray | None = None
        dek: bytearray | None = None
        install_dir = self._vault.vault_path.parent
        try:
            # The whole assembly lives in a temp dir INSIDE AppDataLocation, so the
            # final install os.replace is a same-filesystem rename (D4).
            with tempfile.TemporaryDirectory(dir=install_dir) as td:
                # Shared read -> guard -> materialise -> derive -> open sequence
                # (D1); the helper owns + wipes the backup key/password buffers and
                # returns the opened backup Vault (whose vault.db lives in this temp
                # dir, so it outlives the call for the install rename below).
                backup_vault, backup_compat = self._open_backup_vault(
                    src, backup_password, Path(td), on_key=on_key
                )
                try:
                    # Mint the new master's params FIRST, derive its key from THAT
                    # salt, rekey to it, and persist THAT same params object as the
                    # sidecar — one object, so the sidecar salt and rekey key can't
                    # disagree and brick the vault (D4).
                    #
                    # Under FIBR-0019 the derived value is KEK-master and the
                    # database is re-keyed to a fresh random DEK, exactly as
                    # first-run does: a restore that wrote a v1 sidecar would put
                    # a SECOND key schedule back in the field on every restore,
                    # which is the one thing D2 exists to prevent. FIBR-0014 D4
                    # is amended to match. The restored vault has no recovery
                    # slot — Settings' Add is how one is put back (§ 4.7).
                    master_params = self._auth.new_params()
                    master_key = derive_key(
                        master_pw, master_params.salt, master_params
                    )
                    on_key("master", master_key)
                    dek = bytearray(secrets.token_bytes(KEY_LEN))
                    on_key("dek", dek)
                    backup_vault.rekey(dek)  # not a copy — see open() below
                    wrapped = wrap_dek(
                        master_key, bytes(dek), SLOT_MASTER, master_params
                    )
                    # `cipher_compatibility` is recorded for the same reason
                    # the migration records it (FIBR-0019 § 13.2): the database
                    # being installed came from `export_to`, which writes at an
                    # EXPLICIT level, while a `create`d vault takes the library
                    # default. They agree today and stop agreeing the moment a
                    # sqlcipher3-wheels bump moves the default — at which point
                    # every restored vault would be unopenable by the build that
                    # restored it, because `_open_with` passes what the sidecar
                    # holds and there was nothing to pass (FIBR-0307 finding 11).
                    write_sidecar_v2(
                        backup_vault.sidecar_path,
                        replace(
                            new_sidecar(
                                master_params,
                                {
                                    SLOT_MASTER: SlotRecord.from_wrap(
                                        master_params.salt, wrapped
                                    )
                                },
                            ),
                            cipher_compatibility=backup_compat,
                        ),
                    )
                finally:
                    backup_vault.close()
                self._install(
                    backup_vault.vault_path, backup_vault.sidecar_path, on_key
                )  # INV-5
            self._prune_superseded_old_copies()  # INV-17
            log.info("backup restored")
        except (
            KdfPolicyError,
            SchemaVersionError,
            DatabaseError,
            zipfile.BadZipFile,
            OSError,
            MemoryError,  # a bomb's allocation on a small machine (FIBR-0212)
            # A backstop, and no longer the sidecar reader's route: since
            # `crypto._MALFORMED_SIDECAR` the params read normalises both of
            # these to `KdfPolicyError`, which this tuple already catches above.
            # They stay for any other reader on this path that does not
            # normalise — the bytes came out of an imported .fbk, so they are
            # not necessarily the user's own (FIBR-0310 P2).
            UnicodeDecodeError,
            RecursionError,
        ) as exc:
            # Normalise every underlying failure to BackupError; on-disk state is
            # untouched (nothing installed) or recoverable from *.old (INV-4/5).
            raise BackupError(str(exc)) from exc
        finally:
            _wipe(master_key)
            _wipe(dek)
            _wipe(master_pw)

    # -- verify ---------------------------------------------------------------
    def verify_backup(
        self, src: Path, backup_password: str, *, on_key: OnKey | None = None
    ) -> VerifyResult:
        """Read-only "does this backup actually open?" check (FIBR-0033).

        Reuses restore's read -> guard -> open sequence (``_open_backup_vault``)
        but stops after the open: runs ``PRAGMA cipher_integrity_check`` (a
        full-DB per-page HMAC pass — catches the overflow pages ``count(*)`` never
        reads), reads the as-migrated ``schema_version`` and per-table row counts,
        then tears down. Never touches the live vault (D3); the backup key +
        password buffer are wiped on every path (INV-7). Each expected failure
        class maps to a stable ``reason`` code — a friendly answer, not a stack
        trace (D4). A system ``TemporaryDirectory`` (removed on every path, INV-5)
        holds only the backup's own ciphertext + a ``0o600`` params temp (D6)."""
        on_key = on_key or _noop_on_key
        try:
            with tempfile.TemporaryDirectory() as td:
                backup_vault, _compat = self._open_backup_vault(
                    src, backup_password, Path(td), on_key=on_key
                )
                try:
                    conn = backup_vault.connection
                    # 4a — full-DB per-page HMAC; any row => a body/overflow-page
                    # corruption count(*) + the page-1 guard would miss. Return
                    # before 4b/4c.
                    if conn.execute("PRAGMA cipher_integrity_check").fetchall():
                        return VerifyResult(
                            ok=False,
                            schema_version=None,
                            table_counts=None,
                            reason="corrupt",
                        )
                    # 4b — as-migrated schema (== LATEST after a clean open+migrate).
                    schema_version = conn.execute(
                        "SELECT version FROM schema_version"
                    ).fetchone()[0]
                    # 4c — per-table row counts, display only (never a pass gate).
                    names = [
                        r[0]
                        for r in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name NOT LIKE 'sqlite_%'"
                        ).fetchall()
                    ]
                    # B608: `n` is a table name read from sqlite_master (never
                    # user input) — the dynamic enumeration the spec mandates.
                    table_counts = {
                        n: conn.execute(f"SELECT count(*) FROM {n}").fetchone()[0]  # nosec B608
                        for n in names
                    }
                finally:
                    backup_vault.close()  # 4d
            return VerifyResult(
                ok=True,
                schema_version=schema_version,
                table_counts=table_counts,
                reason=None,
            )
        except DatabaseError:
            # Wrong backup password OR a damaged page-1 header OR an older-schema
            # body corruption read during migration — page-1 HMAC can't tell them
            # apart (INV-3).
            return VerifyResult(False, None, None, "wrong_password")
        except KdfPolicyError:
            return VerifyResult(False, None, None, "bad_kdf_params")
        except SchemaVersionError:
            return VerifyResult(False, None, None, "too_new")
        except BackupError:
            return VerifyResult(False, None, None, "invalid")
        except OSError:
            # A temp-write failure (disk-full / read-only temp); the helper raises
            # it raw, so verify must catch it here (D7).
            return VerifyResult(False, None, None, "io_error")
        except MemoryError:
            # `_read_fbk` normalises its own to BackupError, so this is the rest
            # of the sequence the two callers share -- the temp writes, the open
            # and the migration. `restore_backup` catches it there and this did
            # not, so the same bomb on the same small machine was a refused
            # restore and an unhandled exception out of a Qt slot on verify
            # (FIBR-0212, FIBR-0310 P12). "invalid" is deliberately the same
            # answer restore's BackupError maps to here.
            return VerifyResult(False, None, None, "invalid")

    def _open_backup_vault(
        self, src: Path, backup_password: str, work_dir: Path, *, on_key: OnKey
    ) -> tuple[Vault, int]:
        """Shared read -> guard -> materialise-params -> derive -> open sequence
        for restore and verify (D1).

        The **caller owns and cleans up** ``work_dir``: the returned ``Vault``
        holds an open SQLCipher connection to a ``vault.db`` inside it that must
        outlive this call (restore installs it; verify reads counts from it), so
        the helper must not own a ``TemporaryDirectory`` that would delete the dir
        on return. The helper builds the password buffer, derives the backup key,
        and **wipes both in its own finally on every path** (INV-7). Failures
        propagate **raw** — ``_read_fbk`` / ``_guard_manifest`` raise
        ``BackupError``; ``load_and_validate_params`` raises ``KdfPolicyError``;
        ``open`` raises ``DatabaseError`` / ``SchemaVersionError`` — so each caller
        can map a class to its own outcome (the ``BackupError`` normalisation stays
        in ``restore_backup``, D1)."""
        manifest, params_bytes, db_bytes = self._read_fbk(src)  # INV-12
        # INV-4 format, INV-13 compat, INV-6a. Returns the level THIS backup
        # was written at: opening at the module constant instead works only
        # while the accepted set has one member and fails silently the day it
        # does not; the restore caller also records it on the new sidecar.
        compat = self._guard_manifest(manifest)
        password_buf = bytearray(backup_password, "utf-8")
        backup_key: bytearray | None = None
        tmp_db = work_dir / "vault.db"
        tmp_sidecar = work_dir / "vault.kdf.json"
        tmp_params = work_dir / "params.json"
        try:
            # Materialise params.json to a 0o600 temp + re-validate the KDF floor
            # BEFORE any key is derived (INV-11).
            self._write_owner_only(tmp_params, params_bytes)
            backup_params = load_and_validate_params(tmp_params)
            # These numbers came from the file under inspection, so the one-sided
            # floor `validate_params` applies is not enough here (INV-2, T5).
            validate_untrusted_params(backup_params)
            self._write_owner_only(tmp_db, db_bytes)
            backup_key = derive_key(password_buf, backup_params.salt, backup_params)
            on_key("backup", backup_key)
            # Open + migrate the backup DB into the temp copy (a wrong backup
            # password fails page-1 here; a newer embedded schema raises
            # SchemaVersionError). Pass the derived key itself, NOT a copy: open()
            # only reads key.hex() (never mutates), so a copy would be an un-wiped
            # second reference to live key material outside the finally wipe (INV-7).
            backup_vault = Vault(tmp_db, tmp_sidecar)
            backup_vault.open(backup_key, in_memory_temp=True, cipher_compat=compat)
            return backup_vault, compat
        finally:
            _wipe(backup_key)
            _wipe(password_buf)

    def _guard_manifest(self, manifest: dict[str, object]) -> int:
        """The pre-disk manifest guards: container ``format_version`` (INV-4),
        ``sqlcipher_compat`` against the accepted set (INV-13), and the early
        schema version gate (INV-6a). Each raises ``BackupError`` before any disk
        change. Returns the accepted ``sqlcipher_compat``, so the one place that
        validates it is also the one place that narrows it to an ``int``."""
        if manifest.get("format_version") != MANIFEST_FORMAT_VERSION:
            raise BackupError("unrecognised backup format_version")
        compat = manifest.get("sqlcipher_compat")
        if compat not in SQLCIPHER_COMPAT_ACCEPTED or not isinstance(compat, int):
            raise BackupError("unsupported backup cipher-compatibility level")
        schema_version = manifest.get("schema_version")
        if not isinstance(schema_version, int) or schema_version < 1:
            raise BackupError("backup manifest has no usable schema version")
        if schema_version > LATEST_SCHEMA_VERSION:
            raise BackupError("backup was made by a newer version of finbreak")
        return compat

    def _prune_superseded_old_copies(self) -> None:
        """Keep the newest ``*.old`` set and drop the rest (INV-17).

        INV-5's crash window is the interval between the move-aside and the
        second install ``os.replace``; it shuts the moment the restore returns
        without raising, after which no path in the app can reach an older set
        again. Left alone they accumulate a full encrypted vault per restore,
        each still openable under the password in force when it was made.

        The NEWEST is deliberately kept. It is the user's "I restored the wrong
        backup" copy, and whether that has happened is a judgement only they can
        make — FIBR-0014's own prose calls the old vault "the one the user may
        be locked out of".

        Best-effort by design: the restore has already succeeded, so failing to
        tidy must not turn that into a reported failure. The caller normalises
        ``OSError`` to ``BackupError``, which would do exactly that.
        """
        sets = old_copy_sets(self._vault.vault_path, self._vault.sidecar_path)
        for stamp in sorted(sets)[:-1]:
            for path in sets[stamp]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    log.warning("could not remove superseded copy %s", path.name)

    def _install(self, new_db: Path, new_sidecar: Path, on_key: OnKey) -> None:
        """Move any existing vault + sidecar aside to timestamped ``*.old`` copies,
        then install the restored pair (``vault.db`` first, then the sidecar; D4).
        The ``on_key("post_move_aside", ...)`` seam fires between the two so a test
        can inject a failure with the old pair already safely aside (INV-5).

        **A vault is FOUR files, and the incumbent's ``-wal`` / ``-shm`` move with
        it.** They were left where they were, which cost both halves of what this
        method is for (FIBR-0310 P5). The restored database was installed beside
        a WAL belonging to a DIFFERENT database under a DIFFERENT key — the § 6
        hazard ``vault_migration`` names and handles twice. And the ``.old``
        copy, whose whole purpose is being recoverable, was left without its
        journal.

        MOVED rather than unlinked, and the stamp goes before the suffix so the
        ``.old`` set is a coherent SQLite triple: ``vault.db.<stamp>.old`` with
        ``vault.db.<stamp>.old-wal`` beside it is the name SQLite looks for.
        Unlinking would discard an uncommitted tail from exactly the vault the
        user is stepping away from — and a leftover ``-wal`` means the app did
        not close cleanly, which is one of the reasons someone restores.
        """
        real_db = self._vault.vault_path
        real_sidecar = self._vault.sidecar_path
        # `Vault` takes the two paths independently, so they need not share a
        # parent; dedupe rather than assume either way (FIBR-0313 M2).
        install_dirs = {real_db.parent, real_sidecar.parent}
        if real_db.exists() or real_sidecar.exists():
            # Microseconds, not seconds (FIBR-0216): two restores inside the same
            # second produced the same stamp, so the second one's os.replace
            # silently overwrote the first recoverable copy — on the files that
            # exist to be recoverable.
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
            if real_db.exists():
                os.replace(real_db, real_db.with_name(f"{real_db.name}.{stamp}.old"))
            for suffix in _WAL_SIBLINGS:
                sibling = real_db.with_name(real_db.name + suffix)
                if sibling.exists():
                    os.replace(
                        sibling,
                        real_db.with_name(f"{real_db.name}.{stamp}.old{suffix}"),
                    )
            if real_sidecar.exists():
                os.replace(
                    real_sidecar,
                    real_sidecar.with_name(f"{real_sidecar.name}.{stamp}.old"),
                )
            # The *.old pair IS the recovery copy (INV-5), so its directory
            # entries are made durable HERE, before the seam below -- whose whole
            # premise is that the old pair is already safely aside. A fsync
            # landing after the seam would leave that promise false for exactly
            # the crash the seam models.
            for directory in install_dirs:
                fsync_dir(directory)
        on_key("post_move_aside", bytearray())  # INV-5 failure-injection seam
        # Contents, then the rename, then the directory ENTRY the rename created
        # -- the order export_backup already uses, now applied to the install it
        # was missing from entirely (FIBR-0313 M2). Without it a power loss right
        # after a restore had no durability guarantee at all, on the one path
        # whose purpose is recovering a vault.
        #
        # Only the database needs the file half: the sidecar arrives already
        # fsynced by `write_sidecar_json`, which flushes before its own
        # os.replace. Measured rather than assumed -- mutation_probe showed a
        # second fsync of it changed nothing the suite could see. INV-15 still
        # pins the sidecar's durability as an OUTCOME, so if that writer ever
        # stops flushing the test goes red rather than the guarantee going quiet.
        _fsync_file(new_db)
        os.replace(new_db, real_db)
        os.replace(new_sidecar, real_sidecar)
        for directory in install_dirs:
            fsync_dir(directory)

    def _read_fbk(self, src: Path) -> tuple[dict[str, object], bytes, bytes]:
        """Read exactly the three fixed entries of the `.fbk` safely (INV-12): only
        ``manifest.json`` / ``params.json`` / ``vault.db`` (never ``extractall``),
        rejecting extra / duplicate / renamed / traversal names and any entry over
        its cap. Returns ``(manifest, params_bytes, db_bytes)``."""
        expected = sorted([_MANIFEST_ENTRY, _PARAMS_ENTRY, _DB_ENTRY])
        try:
            with zipfile.ZipFile(src) as zf:
                infos = zf.infolist()
                if sorted(i.filename for i in infos) != expected:
                    raise BackupError(
                        "backup has unexpected / missing / duplicate entries"
                    )
                for info in infos:
                    name = info.filename
                    if name != os.path.basename(name) or ".." in Path(name).parts:
                        raise BackupError(f"unsafe entry name in backup: {name!r}")
                by_name = {i.filename: i for i in infos}
                manifest_bytes = self._read_capped(
                    zf, by_name[_MANIFEST_ENTRY], MAX_MANIFEST_BYTES
                )
                params_bytes = self._read_capped(
                    zf, by_name[_PARAMS_ENTRY], MAX_MANIFEST_BYTES
                )
                db_bytes = self._read_capped(
                    zf, by_name[_DB_ENTRY], MAX_BACKUP_DB_BYTES
                )
            manifest = json.loads(manifest_bytes)
        except (
            zipfile.BadZipFile,
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,  # a non-UTF-8 manifest.json (json.loads raises this)
            # A deeply nested manifest. json.loads raises RecursionError, which
            # is NOT a ValueError, so JSONDecodeError above does not cover it —
            # measured 2026-08-25 on 200k nested brackets. Same class of hostile
            # input as the zip bomb below and the same answer: a refused backup
            # (FIBR-0310 P2).
            RecursionError,
            zlib.error,  # a corrupt DEFLATE stream in any entry (zf.open read)
            # A hostile entry that inflates further than this machine has RAM for.
            # The INV-12 caps + ratio bound it, but the bound is still 512 MiB and a
            # small machine can lose that allocation — a refused backup, not an
            # unhandled exception out of a Qt slot (FIBR-0212).
            MemoryError,
        ) as exc:
            raise BackupError(f"unreadable backup: {exc}") from exc
        if not isinstance(manifest, dict):
            raise BackupError("backup manifest is not a JSON object")
        return manifest, params_bytes, db_bytes

    @staticmethod
    def _read_capped(zf: zipfile.ZipFile, info: zipfile.ZipInfo, cap: int) -> bytes:
        """Read one zip entry with a hard byte cap (INV-12). Rejects on the declared
        ``ZipInfo.file_size`` and on a suspicious compression RATIO BEFORE inflating,
        then reads through ``zf.open`` with a bounded read — never ``zf.read(name)``
        (which would inflate the whole entry first).

        The ratio is what bounds the read against the SOURCE file's size rather than
        against the cap alone: a bomb sized to land exactly on ``cap`` passes the
        size gate, and the bounded read then still allocates the whole cap. Both
        gates use the same ``allowed`` figure, so even a lying ``file_size`` cannot
        inflate past what its own compressed bytes could honestly produce."""
        allowed = min(cap, max(info.compress_size, 1) * MAX_COMPRESSION_RATIO)
        too_big = f"backup entry {info.filename!r} exceeds its size cap"
        bad_ratio = f"backup entry {info.filename!r} has a suspicious compression ratio"
        if info.file_size > allowed:
            raise BackupError(too_big if info.file_size > cap else bad_ratio)
        with zf.open(info) as handle:
            data = handle.read(allowed + 1)
        if len(data) > allowed:
            raise BackupError(too_big if len(data) > cap else bad_ratio)
        return data

    @staticmethod
    def _write_owner_only(path: Path, data: bytes) -> None:
        """Write ``data`` to ``path`` owner-only (``0o600``), refusing to follow a
        symlink — the restore-temp analogue of the sidecar's guarded write (INV-7)."""
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)

    @staticmethod
    def _write_fbk(
        tmp_zip: Path,
        manifest: dict[str, object],
        params_dict: dict[str, int | str],
        db_path: Path,
    ) -> None:
        """Assemble the three-entry `.fbk` zip at ``tmp_zip``, owner-only + fsynced.

        ``vault.db`` is stored (not deflated) — AES ciphertext is incompressible,
        and ZIP_STORED closes the DEFLATE-bomb vector on the DB entry (INV-12).

        The temp name is ``<dest>.tmp``, derived from the user-chosen output path and
        so fully predictable. ``O_NOFOLLOW`` stops only the symlink plant; under the
        old ``O_TRUNC`` an attacker who pre-created a plain ``dest.fbk.tmp`` (mode
        0666) in a shared export dir had it filled and renamed into place, leaving
        the user's backup attacker-owned and world-readable. So: unlink any stale
        temp from an earlier crashed export (``unlink`` removes the link, never its
        target), then create with ``O_EXCL`` so a re-plant inside that window loses
        the race. Same shape as ``_write_owner_only`` below and ``pdf_export``
        (FIBR-0212)."""
        tmp_zip.unlink(missing_ok=True)
        fd = os.open(
            tmp_zip,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as handle:
            with zipfile.ZipFile(handle, "w") as zf:
                zf.writestr(_MANIFEST_ENTRY, json.dumps(manifest, indent=2))
                zf.writestr(_PARAMS_ENTRY, json.dumps(params_dict, indent=2))
                zf.write(db_path, _DB_ENTRY, compress_type=zipfile.ZIP_STORED)
            handle.flush()
            os.fsync(handle.fileno())
