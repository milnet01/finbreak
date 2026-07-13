"""Regenerate the FIBR-0015 cross-package upgrade-path fixtures.

This is a **skipped-by-default manual helper**, NOT part of the test suite — it
has no ``test_`` functions and is never collected by pytest. It exists so the
opaque encrypted fixture blobs (``vault.db`` / ``vault.kdf.json`` / ``backup.fbk``)
have documented provenance and can be regenerated rather than trusted as an
unauditable binary.

**Why it must run under ``sqlcipher3-binary``.** FIBR-0015 swaps the SQLCipher
binding package ``sqlcipher3-binary==0.6.0`` → ``sqlcipher3-wheels==0.5.7``. INV-1
requires that a vault + backup written by the *old* package still open under the
*new* one (the real upgrade an existing Linux user hits). Once the swap lands,
``-binary`` is gone and CI can no longer *create* an old-package artifact — so the
old-package bytes are captured here, once, **before** the swap, and committed. The
matching regression test (``tests/features/windows_build/test_windows_build.py``)
opens these committed bytes under whatever ``sqlcipher3`` is installed.

To regenerate (only needed if the vault schema or fixture shape changes):

    python -m pip install 'sqlcipher3-binary==0.6.0'   # temporarily, into the .venv
    PYTHONPATH=src python tests/fixtures/windows_build/_generate_fixture.py
    python -m pip install .                              # restore the pinned dep

The data is fully synthetic and the keys below are documented test keys — there is
no real financial data and no real secret here (testing.md § 6).
"""

from __future__ import annotations

import importlib.metadata as im
import shutil
import sys
import tempfile
from pathlib import Path

# --- documented test keys + seeded sentinel (shared with the regression test) ---
# These are NOT secrets: they key a synthetic throwaway vault committed to the repo
# purely so a test can prove the ciphertext still decrypts across the package swap.
MASTER_PASSWORD = "fibr0015-master-pw"
BACKUP_PASSWORD = "fibr0015-backup-pw"
BASE_CURRENCY = "ZAR"
SENTINEL_DESCRIPTION = "FIBR0015-CROSS-PACKAGE-SENTINEL"
SENTINEL_AMOUNT_MINOR = -424242
SENTINEL_OCCURRED_ON = "2026-07-13"

FIXTURE_DIR = Path(__file__).resolve().parent
VAULT_DB = FIXTURE_DIR / "vault.db"
VAULT_SIDECAR = FIXTURE_DIR / "vault.kdf.json"
BACKUP_FBK = FIXTURE_DIR / "backup.fbk"


def _require_binary_package() -> str:
    """Refuse to regenerate under anything but ``sqlcipher3-binary`` — the whole
    point of the fixture is to be *old-package* bytes (see the module docstring)."""
    try:
        installed = {
            name
            for name in ("sqlcipher3-binary", "sqlcipher3-wheels")
            if _is_installed(name)
        }
    except Exception:  # pragma: no cover - defensive
        installed = set()
    if installed != {"sqlcipher3-binary"}:
        raise SystemExit(
            "refusing to regenerate: this helper must run with ONLY "
            f"sqlcipher3-binary installed (found: {installed or 'none'}). "
            "Temporarily `pip install sqlcipher3-binary==0.6.0` first — see the "
            "module docstring."
        )
    return im.version("sqlcipher3-binary")


def _is_installed(dist_name: str) -> bool:
    try:
        im.version(dist_name)
        return True
    except im.PackageNotFoundError:
        return False


def main() -> None:
    binary_version = _require_binary_package()

    from finbreak.services.accounts import AccountService
    from finbreak.services.auth import AuthService
    from finbreak.services.backup import BackupService

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        db = tmp / "vault.db"
        sidecar = tmp / "vault.kdf.json"
        fbk = tmp / "backup.fbk"

        auth = AuthService(db, sidecar)
        auth.first_run(bytearray(MASTER_PASSWORD, "utf-8"), BASE_CURRENCY)
        acct = AccountService(auth.vault).list_accounts()[0].id
        conn = auth.vault.connection
        conn.execute(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                acct,
                SENTINEL_OCCURRED_ON,
                SENTINEL_AMOUNT_MINOR,
                SENTINEL_DESCRIPTION,
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()

        BackupService(auth.vault, auth).export_backup(fbk, BACKUP_PASSWORD)
        auth.lock()

        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(db, VAULT_DB)
        shutil.copyfile(sidecar, VAULT_SIDECAR)
        shutil.copyfile(fbk, BACKUP_FBK)

    print(
        f"regenerated FIBR-0015 fixtures under {FIXTURE_DIR} "
        f"(sqlcipher3-binary {binary_version})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
