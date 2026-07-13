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
import tempfile
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlcipher3.dbapi2 import DatabaseError

import finbreak
from finbreak.crypto import derive_key, load_and_validate_params
from finbreak.errors import BackupError, KdfPolicyError, SchemaVersionError
from finbreak.migrations import LATEST_SCHEMA_VERSION
from finbreak.services.auth import AuthService, _wipe
from finbreak.vault import SQLCIPHER_COMPAT, Vault

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
# (a large multi-year vault, well above the 16 MiB statement-import cap). vault.db
# is ZIP_STORED — AES ciphertext is incompressible, so DEFLATE can't bomb it.
MAX_MANIFEST_BYTES = 64 * 1024
MAX_BACKUP_DB_BYTES = 512 * 1024 * 1024

# The single test seam: invoked with (role, buffer) for each derived key — role in
# {"backup", "master", "post_move_aside"} — so a test captures the buffer to assert
# it is zeroed after the call, and may raise to inject a failure at that point.
OnKey = Callable[[str, bytearray], None]

_MANIFEST_ENTRY = "manifest.json"
_PARAMS_ENTRY = "params.json"
_DB_ENTRY = "vault.db"


def _noop_on_key(role: str, buffer: bytearray) -> None:
    return None


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
        no partial ``.fbk`` and no temp (INV-7)."""
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
                self._write_fbk(tmp_zip, manifest, params.to_sidecar_dict(), tmp_db)
            os.replace(tmp_zip, dest)
            log.info("backup exported")
        except BaseException:
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
        if len(new_master_password) == 0:
            raise ValueError("new master password must not be empty")
        backup_pw = bytearray(backup_password, "utf-8")
        master_pw = bytearray(new_master_password, "utf-8")
        backup_key: bytearray | None = None
        master_key: bytearray | None = None
        install_dir = self._vault.vault_path.parent
        try:
            manifest, params_bytes, db_bytes = self._read_fbk(src)  # INV-12
            self._guard_manifest(manifest)  # INV-4 format, INV-13 compat, INV-6a
            # The whole assembly lives in a temp dir INSIDE AppDataLocation, so the
            # final install os.replace is a same-filesystem rename (D4).
            with tempfile.TemporaryDirectory(dir=install_dir) as td:
                tmp = Path(td)
                tmp_db = tmp / "vault.db"
                tmp_sidecar = tmp / "vault.kdf.json"
                tmp_params = tmp / "params.json"
                # Materialise params.json to a 0o600 temp + re-validate the KDF
                # floor BEFORE any key is derived (INV-11).
                self._write_owner_only(tmp_params, params_bytes)
                backup_params = load_and_validate_params(tmp_params)
                self._write_owner_only(tmp_db, db_bytes)
                backup_key = derive_key(backup_pw, backup_params.salt, backup_params)
                on_key("backup", backup_key)
                # Open + migrate the backup DB (a wrong backup password fails page-1
                # here; a newer embedded schema raises SchemaVersionError, INV-6b).
                backup_vault = Vault(tmp_db, tmp_sidecar)
                backup_vault.open(
                    bytearray(backup_key),
                    in_memory_temp=True,
                    cipher_compat=SQLCIPHER_COMPAT,
                )
                try:
                    # Mint the new master's params FIRST, derive its key from THAT
                    # salt, rekey to it, and persist THAT same params object as the
                    # sidecar — one object, so the sidecar salt and rekey key can't
                    # disagree and brick the vault (D4).
                    master_params = self._auth.new_params()
                    master_key = derive_key(
                        master_pw, master_params.salt, master_params
                    )
                    on_key("master", master_key)
                    backup_vault.rekey(bytearray(master_key))
                    backup_vault._write_sidecar(master_params)
                finally:
                    backup_vault.close()
                self._install(tmp_db, tmp_sidecar, on_key)  # INV-5
            log.info("backup restored")
        except (
            KdfPolicyError,
            SchemaVersionError,
            DatabaseError,
            zipfile.BadZipFile,
            OSError,
        ) as exc:
            # Normalise every underlying failure to BackupError; on-disk state is
            # untouched (nothing installed) or recoverable from *.old (INV-4/5).
            raise BackupError(str(exc)) from exc
        finally:
            _wipe(backup_key)
            _wipe(master_key)
            _wipe(backup_pw)
            _wipe(master_pw)

    def _guard_manifest(self, manifest: dict[str, object]) -> None:
        """The pre-disk manifest guards: container ``format_version`` (INV-4),
        ``sqlcipher_compat`` one-element allowlist (INV-13), and the early schema
        version gate (INV-6a). Each raises ``BackupError`` before any disk change."""
        if manifest.get("format_version") != MANIFEST_FORMAT_VERSION:
            raise BackupError("unrecognised backup format_version")
        if manifest.get("sqlcipher_compat") != SQLCIPHER_COMPAT:
            raise BackupError("unsupported backup cipher-compatibility level")
        schema_version = manifest.get("schema_version")
        if (
            not isinstance(schema_version, int)
            or schema_version > LATEST_SCHEMA_VERSION
        ):
            raise BackupError("backup was made by a newer version of finbreak")

    def _install(self, new_db: Path, new_sidecar: Path, on_key: OnKey) -> None:
        """Move any existing vault + sidecar aside to timestamped ``*.old`` copies,
        then install the restored pair (``vault.db`` first, then the sidecar; D4).
        The ``on_key("post_move_aside", ...)`` seam fires between the two so a test
        can inject a failure with the old pair already safely aside (INV-5)."""
        real_db = self._vault.vault_path
        real_sidecar = self._vault.sidecar_path
        if real_db.exists() or real_sidecar.exists():
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
            if real_db.exists():
                os.replace(real_db, real_db.with_name(f"{real_db.name}.{stamp}.old"))
            if real_sidecar.exists():
                os.replace(
                    real_sidecar,
                    real_sidecar.with_name(f"{real_sidecar.name}.{stamp}.old"),
                )
        on_key("post_move_aside", bytearray())  # INV-5 failure-injection seam
        os.replace(new_db, real_db)
        os.replace(new_sidecar, real_sidecar)

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
        except (zipfile.BadZipFile, OSError, json.JSONDecodeError) as exc:
            raise BackupError(f"unreadable backup: {exc}") from exc
        if not isinstance(manifest, dict):
            raise BackupError("backup manifest is not a JSON object")
        return manifest, params_bytes, db_bytes

    @staticmethod
    def _read_capped(zf: zipfile.ZipFile, info: zipfile.ZipInfo, cap: int) -> bytes:
        """Read one zip entry with a hard byte cap (INV-12). Rejects on the declared
        ``ZipInfo.file_size`` BEFORE inflating, then reads through ``zf.open`` with a
        bounded ``read(cap + 1)`` — never ``zf.read(name)`` (which would inflate the
        whole entry first). The bounded read is the real bomb guard: even a lying
        ``file_size`` can't inflate past ``cap + 1`` bytes."""
        if info.file_size > cap:
            raise BackupError(f"backup entry {info.filename!r} exceeds its size cap")
        with zf.open(info) as handle:
            data = handle.read(cap + 1)
        if len(data) > cap:
            raise BackupError(f"backup entry {info.filename!r} exceeds its size cap")
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
        and ZIP_STORED closes the DEFLATE-bomb vector on the DB entry (INV-12)."""
        fd = os.open(
            tmp_zip,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as handle:
            with zipfile.ZipFile(handle, "w") as zf:
                zf.writestr(_MANIFEST_ENTRY, json.dumps(manifest, indent=2))
                zf.writestr(_PARAMS_ENTRY, json.dumps(params_dict, indent=2))
                zf.write(db_path, _DB_ENTRY, compress_type=zipfile.ZIP_STORED)
            handle.flush()
            os.fsync(handle.fileno())
