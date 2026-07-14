"""FIBR-0015 — Windows build. Enforces tests/features/windows_build/spec.md.

Linux-gate coverage of the Windows-build enablement: the SQLCipher-package swap is
vault-safe (INV-1), the Windows freeze reuses the exact Linux collection flags
(INV-3), and the freeze driver is shaped right (INV-2/5/6). The `.exe` build +
clean-room `--self-test` are proven by `windows-build.yml` on a Windows runner, not
here (PyInstaller can't cross-compile). No network, no real financial data.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest
from sqlcipher3.dbapi2 import DatabaseError

from finbreak.crypto import derive_key, load_and_validate_params
from finbreak.vault import SQLCIPHER_COMPAT, Vault

pytestmark = pytest.mark.features

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "windows_build"
_LINUX_FREEZE = _REPO_ROOT / "scripts" / "_build-smoke-in-container.sh"
_FLAGS_FILE = _REPO_ROOT / "scripts" / "windows_freeze_flags.py"
_DRIVER_FILE = _REPO_ROOT / "scripts" / "build-windows-exe.py"


def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_consts():
    """The documented test keys + sentinel, loaded from the (uncollected) generator
    so the fixture bytes and this test share one source of truth."""
    return _load_by_path("_fibr0015_fixture", _FIXTURE_DIR / "_generate_fixture.py")


def _open_vault(db_src: Path, sidecar_src: Path, password: str, **open_kw) -> Vault:
    """Copy a committed vault pair into a temp (open() migrates in place) and open
    it under the installed sqlcipher3 package with the given password."""
    td = Path(tempfile.mkdtemp())
    db, sidecar = td / "vault.db", td / "vault.kdf.json"
    shutil.copyfile(db_src, db)
    shutil.copyfile(sidecar_src, sidecar)
    params = load_and_validate_params(sidecar)
    key = derive_key(bytearray(password, "utf-8"), params.salt, params)
    vault = Vault(db, sidecar)
    vault.open(bytearray(key), **open_kw)
    return vault


# --- INV-1: engine + same-package round-trip ---------------------------------


def test_sqlcipher3_imports_and_engine_is_4_12_0():
    from sqlcipher3 import dbapi2

    conn = dbapi2.connect(":memory:")
    assert conn.execute("PRAGMA cipher_version").fetchone()[0] == "4.12.0 community"
    conn.close()


def test_raw_hex_keyed_hmac_on_vault_round_trips(paths):
    """A raw-hex-keyed, cipher_compatibility=4, HMAC-on vault created under the
    installed package reads its row back after a close/reopen (INV-1)."""
    from conftest import _PW, _params
    from finbreak.crypto import SALT_LEN

    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    params = _params(salt)
    key = derive_key(bytearray(_PW), salt, params)
    vault = Vault(vault_path, sidecar_path)
    vault.create(bytearray(key), params, "ZAR", 2)
    acct = vault.connection.execute("SELECT id FROM accounts LIMIT 1").fetchone()[0]
    vault.connection.execute(
        "INSERT INTO transactions"
        "(account_id, occurred_on, amount_minor, description, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (acct, "2026-07-01", -999, "ROUNDTRIP", "2026-01-01T00:00:00+00:00"),
    )
    vault.connection.commit()
    vault.close()

    reopened = Vault(vault_path, sidecar_path)
    reopened.open(bytearray(key))
    row = reopened.connection.execute(
        "SELECT amount_minor FROM transactions WHERE description = 'ROUNDTRIP'"
    ).fetchone()
    reopened.close()
    assert row == (-999,)


def test_sqlcipher_export_and_rekey_round_trip(paths, tmp_path):
    """The FIBR-0014 backup binding surface — sqlcipher_export into a separately
    keyed HMAC-on target, and PRAGMA rekey — round-trips under the installed
    package (INV-1)."""
    from conftest import _PW, _params
    from finbreak.crypto import SALT_LEN

    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    params = _params(salt)
    key = derive_key(bytearray(_PW), salt, params)
    vault = Vault(vault_path, sidecar_path)
    vault.create(bytearray(key), params, "ZAR", 2)

    backup_key = bytearray(range(32))
    dest = tmp_path / "backup.db"
    vault.export_to(dest, backup_key)  # sqlcipher_export into an ATTACHed target

    # The exported copy opens with the backup key at the recorded compat level.
    exported = Vault(dest, tmp_path / "unused.kdf.json")
    exported.open(bytearray(backup_key), cipher_compat=SQLCIPHER_COMPAT)
    assert (
        exported.connection.execute("SELECT count(*) FROM accounts").fetchone()[0] >= 1
    )
    exported.close()

    # rekey the live vault; the new key opens, the old key no longer does.
    new_key = bytearray(range(31, -1, -1))
    vault.rekey(new_key)
    vault.close()
    good = Vault(vault_path, sidecar_path)
    good.open(bytearray(new_key))
    good.close()
    with pytest.raises(DatabaseError):
        Vault(vault_path, sidecar_path).open(bytearray(key))


# --- INV-1: cross-package upgrade path (committed -binary fixtures) -----------


def test_binary_created_vault_opens_cross_package():
    c = _fixture_consts()
    vault = _open_vault(c.VAULT_DB, c.VAULT_SIDECAR, c.MASTER_PASSWORD)
    row = vault.connection.execute(
        "SELECT description, amount_minor FROM transactions WHERE description = ?",
        (c.SENTINEL_DESCRIPTION,),
    ).fetchone()
    vault.close()
    assert row == (c.SENTINEL_DESCRIPTION, c.SENTINEL_AMOUNT_MINOR)


def test_binary_created_fbk_backup_opens_cross_package(tmp_path):
    """The .fbk's embedded vault.db (written by -binary's sqlcipher_export) opens
    under the installed package with the backup key at the recorded compat."""
    c = _fixture_consts()
    with zipfile.ZipFile(c.BACKUP_FBK) as zf:
        params_bytes = zf.read("params.json")
        db_bytes = zf.read("vault.db")
    params_path = tmp_path / "params.json"
    params_path.write_bytes(params_bytes)
    db_path = tmp_path / "vault.db"
    db_path.write_bytes(db_bytes)

    params = load_and_validate_params(params_path)
    backup_key = derive_key(bytearray(c.BACKUP_PASSWORD, "utf-8"), params.salt, params)
    vault = Vault(db_path, tmp_path / "unused.kdf.json")
    vault.open(bytearray(backup_key), cipher_compat=SQLCIPHER_COMPAT)
    row = vault.connection.execute(
        "SELECT description, amount_minor FROM transactions WHERE description = ?",
        (c.SENTINEL_DESCRIPTION,),
    ).fetchone()
    vault.close()
    assert row == (c.SENTINEL_DESCRIPTION, c.SENTINEL_AMOUNT_MINOR)


# --- INV-3: parity guard between the Windows canonical flags + Linux freeze ---


def _scrape_linux_freeze():
    """Extract the collection flags actually passed to pyinstaller in the Linux
    freeze, per the D3 contract: scope to the `pyinstaller … \\` invocation block,
    ignore `#` comments, match flags anywhere on a continued line, strip the
    trailing quote off the --add-data target."""
    lines = _LINUX_FREEZE.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("pyinstaller"))
    block: list[str] = []
    i = start
    while True:
        block.append(lines[i])
        if not lines[i].rstrip().endswith("\\"):
            break
        i += 1
    block = [ln for ln in block if not ln.lstrip().startswith("#")]
    text = "\n".join(block)
    hidden = set(re.findall(r"--hidden-import\s+(\S+)", text))
    collect_bin = set(re.findall(r"--collect-binaries\s+(\S+)", text))
    collect_all = set(re.findall(r"--collect-all\s+(\S+)", text))
    # ALL --add-data pairs (icons AND the FIBR-0139 data lib), as a set of the
    # package-relative targets — a second pair must sit INSIDE the parity guard, not
    # slip past a first-match-only scrape (FIBR-0139 Deliverable 9).
    add_data = re.findall(r"--add-data\s+(\S+)", text)
    targets = {pair.rsplit(":", 1)[-1].strip("\"'") for pair in add_data}
    return hidden, collect_bin, collect_all, targets


def test_windows_flags_match_linux_freeze():
    flags = _load_by_path("windows_freeze_flags", _FLAGS_FILE)
    hidden, collect_bin, collect_all, targets = _scrape_linux_freeze()
    assert set(flags.HIDDEN_IMPORTS) == hidden
    assert set(flags.COLLECT_BINARIES) == collect_bin
    assert set(flags.COLLECT_ALL) == collect_all
    assert targets == {flags.ADD_DATA_TARGET, flags.DATA_ADD_DATA_TARGET}


# --- INV-2/5/6: Windows freeze driver shape ----------------------------------


def test_driver_uses_os_pathsep_not_hardcoded_colon():
    src = _DRIVER_FILE.read_text()
    assert "os.pathsep" in src, "--add-data must join with os.pathsep (INV-5)"


def test_driver_reads_deps_from_manifest():
    src = _DRIVER_FILE.read_text()
    # deps must come from pyproject, not a hand-listed set (INV-6)
    assert "tomllib" in src and "dependencies" in src


def test_driver_has_single_qt_binding_guard():
    src = _DRIVER_FILE.read_text()
    assert re.search(r"PySide2|PySide6|PyQt5|PyQt6", src)  # single-Qt guard (INV-2)


def test_driver_uses_canonical_flag_list():
    src = _DRIVER_FILE.read_text()
    # the driver must build its flags from the single canonical list (INV-3)
    assert "windows_freeze_flags" in src


# --- FIBR-0132: the released .exe is a GUI app, not a console app -------------


def test_driver_freezes_windowed_gui_exe():
    """The Windows freeze must pass `--windowed` so PyInstaller builds the
    /SUBSYSTEM:WINDOWS bootloader — otherwise the .exe attaches a console (the
    cmd window a user sees before the GUI). Windows-only: the Linux freeze stays
    console (its clean-room reads stdout; there is no window nuisance on Linux)."""
    src = _DRIVER_FILE.read_text()
    assert "--windowed" in src


def test_selftest_can_redirect_sentinel_to_a_file():
    """`--windowed` sets sys.stdout/stderr to None on Windows, so the CI
    `--self-test` sentinel can't be read from stdout. `__main__` must honour
    FINBREAK_SELFTEST_OUT and write the sentinel to that file instead."""
    src = (_REPO_ROOT / "src" / "finbreak" / "__main__.py").read_text()
    assert "FINBREAK_SELFTEST_OUT" in src


def test_driver_embeds_the_app_icon():
    """The Windows freeze must pass `--icon` pointing at the committed multi-size
    finbreak.ico, so Explorer/taskbar show the branded donut instead of
    PyInstaller's default console-stub icon (FIBR-0037 app icon on Windows). The
    .ico must exist and be a real multi-size Windows icon."""
    src = _DRIVER_FILE.read_text()
    assert "--icon" in src
    ico = _REPO_ROOT / "assets" / "icon" / "finbreak.ico"
    assert ico.is_file(), f"{ico} missing — regenerate via scripts/make-icons.sh"
    # MS Windows .ico magic: reserved(0) + type 1 (icon).
    assert ico.read_bytes()[:4] == b"\x00\x00\x01\x00"
