"""Per-OS-user data locations (design.md "Persistence").

The vault and its KDF sidecar live in ``QStandardPaths.AppDataLocation``, which
resolves per OS user — giving multi-profile separation for free (ADR-0003).
Tests inject explicit ``tmp_path`` locations instead of calling these.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths

APP_NAME = "finbreak"

VAULT_FILENAME = "vault.db"
SIDECAR_FILENAME = "vault.kdf.json"
WINDOW_SETTINGS_FILENAME = "window.ini"


def data_dir() -> Path:
    """The app's per-user data directory, created if absent."""
    QCoreApplication.setApplicationName(APP_NAME)
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    directory = Path(location)
    # Create the leaf owner-only from the outset (mode applies to the final
    # component only, so shared parents keep their default perms), then chmod to
    # enforce 0o700 even under a permissive umask that would loosen mkdir's mode.
    # The vault + sidecar files are 0o600, but the containing dir otherwise
    # defaults to the umask (commonly 0o755), leaking file existence/size/mtime
    # metadata to other local users. POSIX-only (mirrors the owner-only INV-7).
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if hasattr(os, "getuid"):
        os.chmod(directory, 0o700)
    return directory


def vault_path() -> Path:
    return data_dir() / VAULT_FILENAME


def sidecar_path() -> Path:
    return data_dir() / SIDECAR_FILENAME


def window_settings_path() -> Path:
    """The window-geometry INI — a plain, **unencrypted** sibling of the vault
    (FIBR-0052 INV-5/D7). It holds only window size/position, toolbar state, and
    the last-active tab index — non-sensitive, and must load *before* unlock — so
    it deliberately lives outside the encrypted vault. Tests monkeypatch this."""
    return data_dir() / WINDOW_SETTINGS_FILENAME
