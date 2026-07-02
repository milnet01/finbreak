"""Shared pytest setup + cross-suite vault fixtures.

Force Qt's offscreen platform before any QApplication is created, so the
GUI-touching tests run on a headless CI runner with no display. Set at import
time — pytest imports conftest before collecting tests or creating the
pytest-qt `qapp`.

Also hosts the raw **v1-vault** builder + keyed-reopen helper shared by the
accounts (FIBR-0005) and categories (FIBR-0006) migration suites: a v1 vault is
the upgrade-path fixture, and `Vault.create()` can no longer produce one (it now
migrates a fresh vault straight to the latest schema). Kept here as the single
copy (coding.md § 1.3 — a second call-site is the trigger).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from sqlcipher3 import dbapi2  # noqa: E402

from finbreak.crypto import KEY_LEN, SALT_LEN, derive_key  # noqa: E402
from finbreak.models import FORMAT_VERSION, KdfParams  # noqa: E402
from finbreak.services.auth import (  # noqa: E402
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
)

# The test master password, shared by every migration/vault fixture.
_PW = b"correct horse battery staple"


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


def keyed_connection(vault_path: Path, salt: bytes) -> dbapi2.Connection:
    """Reopen a raw keyed SQLCipher connection on an existing vault file (the
    reopen a migration test needs after ``build_v1_vault`` closes its own)."""
    key = derive_key(bytearray(_PW), salt, _params(salt))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")
    return conn


def build_v1_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """Write a raw FIBR-0004-shape v1 vault (schema_version=1, account-less
    transactions) + its sidecar, WITHOUT Vault.create() (which now migrates to
    the latest schema). The migration-suite upgrade-path fixture. Closes its own
    connection — a caller needing one reopens via ``keyed_connection``."""
    params = _params(salt)
    key = derive_key(bytearray(_PW), salt, params)
    os.close(os.open(vault_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")
    conn.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version(version) VALUES (1)")
    conn.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO settings(key, value) VALUES ('base_currency', 'ZAR')")
    conn.execute("INSERT INTO settings(key, value) VALUES ('minor_unit_exponent', '2')")
    conn.execute(
        "CREATE TABLE transactions(id INTEGER PRIMARY KEY, occurred_on TEXT NOT "
        "NULL, amount_minor INTEGER NOT NULL, description TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    for occurred_on, amount_minor, description in rows:
        conn.execute(
            "INSERT INTO transactions(occurred_on, amount_minor, description, "
            "created_at) VALUES (?, ?, ?, ?)",
            (occurred_on, amount_minor, description, "2026-01-01T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()
    payload = json.dumps(params.to_sidecar_dict(), indent=2)
    fd = os.open(sidecar_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(payload)
