"""The single owned SQLCipher connection (design.md — UI never touches storage).

Reads/writes the plaintext KDF sidecar, opens the encrypted database with the
Argon2id-derived raw key, creates the schema on first-run, and refuses use while
locked. Wrong-key / tamper detection is SQLCipher's (FIBR-0004 INV-1); the
sidecar is written atomically and both files are owner-only (INV-7).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlcipher3 import dbapi2

from finbreak.errors import VaultLockedError, VaultStateError
from finbreak.migrations import run_migrations
from finbreak.models import KdfParams

# The baseline version create() writes; migrations.py brings it to
# LATEST_SCHEMA_VERSION. SCHEMA_VERSION must equal the first migration step's
# from-version (FIBR-0005 INV-4, Baseline-complete).
SCHEMA_VERSION = 1

# The SQLCipher cipher-compatibility level the backup DB is written under
# (FIBR-0014 INV-13). Pinned so a `.fbk` made today still opens after a
# sqlcipher3-wheels bump that changes the page/HMAC/KDF-iter defaults: export
# writes at this level and records it in the manifest; restore re-applies the
# recorded level (validated against this one-element allowlist in
# services/backup.py). Lives HERE — the module that issues the PRAGMA — because
# vault.py cannot import it from services/backup.py without a circular import;
# backup.py imports it from here (spec placed it in backup.py, refined).
SQLCIPHER_COMPAT = 4


class Vault:
    def __init__(self, vault_path: Path, sidecar_path: Path):
        self._vault_path = vault_path
        self._sidecar_path = sidecar_path
        self._conn: dbapi2.Connection | None = None

    @property
    def connection(self) -> dbapi2.Connection:
        if self._conn is None:
            raise VaultLockedError("the vault is locked")
        return self._conn

    @property
    def vault_path(self) -> Path:
        """The on-disk vault DB path — the install target a restore writes to
        (readable while locked, so restore works pre-login; FIBR-0014)."""
        return self._vault_path

    @property
    def sidecar_path(self) -> Path:
        """The on-disk KDF sidecar path — the restore's second install target."""
        return self._sidecar_path

    def presence_state(self) -> str:
        """Route by file presence; a mixed pair raises ``VaultStateError``."""
        vault_there = self._vault_path.exists()
        sidecar_there = self._sidecar_path.exists()
        if vault_there and sidecar_there:
            return "unlock"
        if not vault_there and not sidecar_there:
            return "first_run"
        raise VaultStateError(
            "mixed install: exactly one of the vault / sidecar is present"
        )

    def create(
        self, key: bytearray, params: KdfParams, base_currency: str, exponent: int
    ) -> None:
        """Create the encrypted vault, its settings, and the sidecar (in that order).

        The vault (schema + settings + ``schema_version``) is written first and
        the sidecar last, so a crash mid-first-run leaves at most a
        vault-without-sidecar — caught as a mixed state next launch (INV-5).
        The connection is left open (the caller is now unlocked).
        """
        # Create the vault file owner-only BEFORE SQLCipher writes any ciphertext
        # into it, so there is never a window where the at-rest file sits at the
        # process umask (world-readable), and a failure mid-create can't leave a
        # readable file behind (INV-7). O_EXCL asserts the first-run invariant —
        # presence_state() only routes here when neither file exists.
        os.close(os.open(self._vault_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        conn = self._connect(key)
        # Mirror open()'s close-and-reset over the WHOLE build: any failure — a
        # CREATE/INSERT or the schema commit (e.g. a disk-full OSError from
        # SQLite), a migration bug, or the sidecar write — must close the
        # connection and reset self._conn, never leak an open fd / file-lock or
        # (post-commit) a live unlocked connection that defeats the
        # VaultLockedError guard. self._conn is set only after the schema commit,
        # so it stays locked on any earlier failure either way.
        try:
            conn.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
            conn.execute(
                "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,)
            )
            conn.execute(
                "CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES ('base_currency', ?)",
                (base_currency,),
            )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES ('minor_unit_exponent', ?)",
                (str(exponent),),
            )
            conn.execute(
                "CREATE TABLE transactions("
                "id INTEGER PRIMARY KEY, occurred_on TEXT NOT NULL, "
                "amount_minor INTEGER NOT NULL, description TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )
            conn.commit()
            self._conn = conn
            # Bring the fresh v1 baseline to the latest schema, THEN write the
            # sidecar last — so a migration failure leaves a vault-without-sidecar
            # (the clean mixed-state retry, INV-5), never a sidecar over a
            # half-migrated vault (FIBR-0005 D1/D2). The "DB durable before
            # sidecar" half relies on SQLite's default per-commit fsync
            # (synchronous=FULL); a later switch to WAL / synchronous=NORMAL would
            # need the sidecar write deferred until the DB is durably flushed.
            run_migrations(conn)
            self._write_sidecar(params)
        except Exception:
            self._conn = None
            conn.close()
            raise

    def open(
        self,
        key: bytearray,
        *,
        in_memory_temp: bool = False,
        cipher_compat: int | None = None,
    ) -> None:
        """Open the vault with the raw key; a wrong key / tamper raises here.

        ``in_memory_temp`` sets ``temp_store=MEMORY`` on the connection *before*
        ``run_migrations`` runs, so a restore's migration rebuilds spill no
        plaintext to a temp store (FIBR-0014 INV-1b). ``cipher_compat`` applies a
        recorded ``cipher_compatibility`` level (before ``cipher_use_hmac=ON``) so
        an older `.fbk` opens under a library whose default differs (INV-13)."""
        conn = self._connect(
            key, in_memory_temp=in_memory_temp, cipher_compat=cipher_compat
        )
        try:
            # First read forces SQLCipher to decrypt + HMAC-check page 1: a wrong
            # key or a flipped body byte raises DatabaseError rather than
            # returning corrupt data (INV-1).
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except Exception:
            conn.close()
            raise
        self._conn = conn
        # Migrations run on unlock (design.md "Persistence"). A failure rolls
        # back inside the runner, leaving a re-openable vault at its old
        # version; drop the connection and re-raise so nothing uses a
        # half-open state (FIBR-0005 INV-4).
        try:
            run_migrations(conn)
        except Exception:
            self._conn = None
            conn.close()
            raise

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _connect(
        self,
        key: bytearray,
        *,
        in_memory_temp: bool = False,
        cipher_compat: int | None = None,
    ) -> dbapi2.Connection:
        # Default isolation_level "" → manual-commit (DBAPI), so writes are
        # delimited by an explicit commit() (INV-4a).
        conn = dbapi2.connect(str(self._vault_path))
        # Raw-key pragma MUST be the first statement. key.hex() is exactly 64
        # chars from [0-9a-f] (Argon2 output, never user text), so this
        # interpolation has no injection surface; SQLCipher does not
        # bind-parameterise PRAGMA key. The transient hex `str` is an
        # un-wipeable copy of the key (SQLCipher's PRAGMA takes a string) — an
        # accepted best-effort gap, consistent with the D5 stance on the other
        # immutable key/password intermediates.
        conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
        # Apply a recorded cipher_compatibility level (FIBR-0014 INV-13) right
        # after PRAGMA key and BEFORE cipher_use_hmac — a lower level resets the
        # per-page HMAC off, so setting it first then forcing HMAC ON means HMAC
        # can never be left disabled. cipher_compat is an int the caller has
        # already allowlist-validated (services/backup.py), never user text.
        if cipher_compat is not None:
            conn.execute(f"PRAGMA cipher_compatibility = {int(cipher_compat)}")
        # Pin per-page HMAC integrity ON explicitly (FIBR-0077, revisiting
        # FIBR-0004 D4 which only *asserted* the SQLCipher-4 default). AES gives
        # confidentiality, not integrity; the HMAC is what makes a tampered page
        # fail to open (security-model INV-1/T9). Every vault is created with the
        # default ON, so pinning ON here can never mismatch an existing file — it
        # only removes the reliance on a dep default a future bump could flip
        # (global rule §5). Must be issued right after PRAGMA key, before the
        # first read, as a cipher-configuration statement.
        conn.execute("PRAGMA cipher_use_hmac = ON")
        # Enforce the transactions->accounts foreign key (FIBR-0005 D4). Set on
        # a fresh connection before its first statement: a *change* to
        # foreign_keys is a no-op mid-transaction, but once ON it stays enforced.
        conn.execute("PRAGMA foreign_keys = ON")
        # Wait up to 5s for a held lock instead of raising OperationalError
        # immediately (FIBR-0076): a second app instance or a slow backup/AV
        # holding a transient read lock serialises rather than crashing the UI.
        conn.execute("PRAGMA busy_timeout = 5000")
        # Keep temp tables / migration-rebuild scratch in memory so a restore's
        # v1→v2 transactions rebuild spills no plaintext to a temp file (INV-1b).
        # Set here, before the first read/migration, so it covers run_migrations.
        if in_memory_temp:
            conn.execute("PRAGMA temp_store = MEMORY")
        return conn

    def rekey(self, new_key: bytearray) -> None:
        """Re-key the open vault in place to ``new_key`` (``PRAGMA rekey``, FIBR-0014
        D4). After it the old key no longer opens the file and the new key does,
        with data intact (spike-proven). Raises ``VaultLockedError`` if locked."""
        # new_key.hex() is 64 hex chars from Argon2 output (never user text), so
        # this interpolation has no injection surface — same posture as PRAGMA key.
        self.connection.execute(f"PRAGMA rekey = \"x'{new_key.hex()}'\"")

    def export_to(self, dest_db: Path, backup_key: bytearray) -> None:
        """ATTACH ``dest_db`` (keyed by ``backup_key``) onto the live, master-keyed
        connection and ``sqlcipher_export`` the whole vault into it (FIBR-0014 D2).

        Runs on the already-unlocked connection because only it holds the master
        key that can read the source vault. Pre-creates the target ``0o600`` (so
        SQLite doesn't create it umask-readable), sets ``temp_store=MEMORY`` so no
        plaintext spills (INV-1b), writes the backup at ``SQLCIPHER_COMPAT`` with
        HMAC on (INV-13/INV-4), DETACHes, and restores the connection's prior
        ``temp_store``. Raises ``VaultLockedError`` if locked."""
        conn = self.connection  # VaultLockedError if locked
        # Create the ATTACH target owner-only before SQLCipher writes ciphertext,
        # so it never sits at the process umask (world-readable), mirroring
        # create()'s O_EXCL 0o600 posture (INV-7).
        os.close(os.open(dest_db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        prior_temp_store = conn.execute("PRAGMA temp_store").fetchone()[0]
        attached = False
        try:
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute(
                f"ATTACH DATABASE '{dest_db}' AS backup KEY \"x'{backup_key.hex()}'\""
            )
            attached = True
            # cipher_compatibility BEFORE cipher_use_hmac (INV-13) so HMAC-on can't
            # be reset by the level change; both on the attached `backup` schema.
            conn.execute(f"PRAGMA backup.cipher_compatibility = {SQLCIPHER_COMPAT}")
            conn.execute("PRAGMA backup.cipher_use_hmac = ON")
            conn.execute("SELECT sqlcipher_export('backup')")
        finally:
            # Always DETACH a successful ATTACH and restore temp_store, even on a
            # mid-export failure — else a dangling `backup` schema / changed
            # temp_store would corrupt the still-open live session.
            if attached:
                conn.execute("DETACH DATABASE backup")
            conn.execute(f"PRAGMA temp_store = {prior_temp_store}")

    def _write_sidecar(self, params: KdfParams) -> None:
        """Atomically write the plaintext sidecar as owner-only (coding.md § 7)."""
        payload = json.dumps(params.to_sidecar_dict(), indent=2)
        tmp_path = self._sidecar_path.with_name(self._sidecar_path.name + ".tmp")
        # O_NOFOLLOW refuses to open through a symlink planted at the .tmp path,
        # so the write can't be redirected to truncate/overwrite an attacker's
        # target (0 on Windows, where the flag is absent — a no-op there).
        fd = os.open(
            tmp_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
        os.replace(tmp_path, self._sidecar_path)
