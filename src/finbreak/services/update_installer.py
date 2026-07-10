"""The platform seam for installing an update (FIBR-0054 D6/D8).

``Installer`` is the protocol the updater talks to; ``AppImageInstaller`` is the
only implementation built here — a Linux AppImage swaps itself in place: the
running binary knows its own path via ``$APPIMAGE``, so "install" is *replace one
file and re-exec*. ``detect_installer()`` returns an installer **only** off a real
AppImage (``$APPIMAGE`` set + present), so a ``python -m finbreak`` run, a Flatpak,
or a future un-wired Windows build is inert (INV-7). A ``WindowsInstaller`` is the
future plug-in point — it registers here with no change to ``UpdateService`` or the
UI (D6); Windows is *designed for*, not built (Out of scope).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, Protocol, runtime_checkable

from finbreak.errors import UpdateError


@runtime_checkable
class Installer(Protocol):
    """How the updater installs a verified download on this platform (D6)."""

    def can_self_update(self) -> bool: ...

    def target_path(self) -> Path:
        """The file to replace. Its ``.parent`` is where the download stages its
        temp, so the final ``os.replace`` is a same-filesystem atomic rename
        (INV-5)."""
        ...

    def apply(self, new_file: Path, on_before_exec: Callable[[], None]) -> NoReturn:
        """Install *new_file* (already signature-verified) and relaunch. Runs
        *on_before_exec* (the key-wipe) **after** the swap and **before** the exec
        (INV-6). Does not return."""
        ...


class AppImageInstaller:
    """Swap ``$APPIMAGE`` for a verified download, then re-exec it (D8)."""

    def __init__(self, appimage_path: Path):
        self._appimage_path = appimage_path

    def can_self_update(self) -> bool:
        return True

    def target_path(self) -> Path:
        return self._appimage_path

    def apply(self, new_file: Path, on_before_exec: Callable[[], None]) -> NoReturn:
        # chmod → os.replace (atomic, same fs) — any failure before the replace
        # completes leaves the original $APPIMAGE byte-for-byte intact; drop the
        # temp and surface it, WITHOUT wiping the key (INV-5/INV-6/INV-11).
        try:
            # 0o755 is the mandatory AppImage mode — the file is unlaunchable
            # without the execute bit, and it replaces a $APPIMAGE that was
            # already 0o755. Not a permissive-mask smell (bandit B103).
            os.chmod(new_file, 0o755)  # nosec B103
            os.replace(new_file, self._appimage_path)
        except OSError as exc:
            new_file.unlink(missing_ok=True)
            raise UpdateError(f"could not install the update: {exc}") from exc
        # The swap succeeded — wipe the derived key before we hand the process
        # over, since os.execv replaces the image and never runs Qt's aboutToQuit
        # (INV-6). Then relaunch the new binary in place.
        on_before_exec()
        # Relaunch the just-swapped AppImage in place. No shell is involved
        # (that is the point — no shell-injection surface); the argv is our own
        # verified path, not user input (bandit B606, D8).
        path = str(self._appimage_path)
        os.execv(path, [path])  # nosec B606


def detect_installer() -> Installer | None:
    """An ``AppImageInstaller`` when running from a real AppImage, else ``None``
    (INV-7). ``$APPIMAGE`` is set by the AppImage runtime to the mounted image's
    own path; we require it to point at an existing file."""
    raw = os.environ.get("APPIMAGE")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        return None
    return AppImageInstaller(path)


def is_update_supported() -> bool:
    """Whether self-update can run on this package (INV-7) — i.e. an installer
    exists. The Settings checkbox is disabled + tooltipped when this is False."""
    return detect_installer() is not None
