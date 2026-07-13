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
from pathlib import Path

import finbreak
from finbreak.crypto import derive_key
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
