"""The platform seam for installing an update (FIBR-0054 D6/D8).

``Installer`` is the protocol the updater talks to; ``AppImageInstaller`` is the
only implementation built here — a Linux AppImage swaps itself in place: the
running binary knows its own path via ``$APPIMAGE``, so "install" is *replace one
file, spawn a fresh detached copy, and exit* (a plain in-place re-exec can't
replace a busy FUSE mount — see ``apply``). ``detect_installer()`` returns an
installer **only** off a real
AppImage (``$APPIMAGE`` set + present), so a ``python -m finbreak`` run, a Flatpak,
or a future un-wired Windows build is inert (INV-7). A ``WindowsInstaller`` is the
future plug-in point — it registers here with no change to ``UpdateService`` or the
UI (D6); Windows is *designed for*, not built (Out of scope).
"""

from __future__ import annotations

import os
import shlex
import subprocess  # nosec B404 — fixed-argv /bin/sh waiter, no user input (see apply)
import time
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, Protocol, TextIO, runtime_checkable

from finbreak.errors import UpdateError

# AppImage-runtime markers of the *currently running* image. Dropped so the
# relaunched image's outer runtime re-mounts + re-derives them from scratch,
# rather than short-circuiting on the old (soon-unmounted) values.
_STALE_APPIMAGE_ENV = ("APPDIR", "APPIMAGE", "ARGV0")

# Dynamic-loader vars the PyInstaller onefile bootloader repoints at its private
# ``_MEI`` bundle dir. They must be restored to the SYSTEM values before spawning
# ``/bin/sh`` — see _relaunch_env. AppImage is Linux-only, so only the Linux pair.
_LOADER_ENV = ("LD_LIBRARY_PATH", "LD_PRELOAD")


def _relaunch_env() -> dict[str, str]:
    """The environment for the ``/bin/sh`` relaunch waiter (and the image it execs).

    ``PYINSTALLER_RESET_ENVIRONMENT=1`` is PyInstaller 6.10+'s **official**
    restart signal: it makes the new onefile bootloader reset its own internal
    ``_PYI_*`` state and treat itself as a fresh top-level instance (re-extract),
    instead of assuming it is a worker subprocess of the old one and reusing the
    now-deleted extraction dir. (Per the PyInstaller docs we must NOT hand-edit the
    private ``_PYI_*`` vars; this flag is the supported mechanism.) We additionally
    drop the AppImage runtime's own markers so the outer runtime re-mounts cleanly.

    **Loader-path restoration (the real 0.1.6→0.1.7 "closed but didn't reopen"):**
    the frozen onefile app runs with ``LD_LIBRARY_PATH`` (and possibly
    ``LD_PRELOAD``) pointing at its private ``_MEI`` extraction dir so it finds its
    *bundled* libs. Inherited by the ``/bin/sh`` waiter, the **system** shell then
    loads those bundled libs — e.g. an ``_MEI`` ``libreadline.so.8`` incompatible
    with the system ``/bin/sh`` — and dies on a symbol lookup *before it can
    relaunch* (evidenced in ``update-relaunch.log``). PyInstaller preserves the
    pre-launch value in ``<VAR>_ORIG``; we restore each loader var to that (or drop
    it when there was none), so the waiter runs against the SYSTEM libraries. The
    exec'd AppImage sets up its own loader path via its runtime, so this is safe."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in _STALE_APPIMAGE_ENV:
        env.pop(key, None)
    for var in _LOADER_ENV:
        original = env.pop(f"{var}_ORIG", None)
        if original:  # a real pre-launch value → restore it; empty/absent → drop
            env[var] = original
        else:
            env.pop(var, None)
    return env


def _relaunch_command(appimage: str, pid: int) -> list[str]:
    """A detached ``/bin/sh`` waiter: block until the OLD process (*pid*) has fully
    exited — so the AppImage's FUSE mount is unmounted and its PyInstaller ``_MEI``
    extraction dir is cleaned — THEN ``exec`` the swapped image.

    Launching the new image *before* the old one tears down is the "closed but
    didn't reopen" race (0.1.2→0.1.3, 0.1.4→0.1.5): the fresh onefile bootloader
    collides with the still-mounted old image and dies. Robust self-relaunching
    AppImages (RPCS3, PCSX2) all wait for the old process first — this is that
    wait. A hard ~60s cap (600 × 0.1s) means a wedged old process can never hang
    the relaunch forever. ``/bin/sh`` is universal on Linux (the only AppImage
    platform); the image path is ``shlex.quote``-d so a space can't break the
    script, and the argv is our own verified ``$APPIMAGE`` path — never user input.
    """
    quoted = shlex.quote(appimage)
    script = (
        f'echo "[finbreak] waiting for pid {pid} to exit before relaunch"; '
        f"i=0; "
        f"while kill -0 {pid} 2>/dev/null; do "
        f'i=$((i+1)); [ "$i" -ge 600 ] && break; sleep 0.1; '
        f"done; "
        f'echo "[finbreak] launching {quoted}"; '
        f"exec {quoted}"
    )
    return ["/bin/sh", "-c", script]


def _relaunch_log_path() -> Path | None:
    """The relaunch diagnostics log — a sibling of the vault in the per-user data
    dir. Returns ``None`` (relaunch proceeds without a log) if the location can't
    be resolved; diagnostics must never block the relaunch."""
    try:
        from finbreak.paths import data_dir

        return data_dir() / "update-relaunch.log"
    except Exception:  # noqa: BLE001 — logging must never block the relaunch
        return None


def _relaunch_log_handle() -> TextIO | None:
    """An append handle to the relaunch log, or ``None`` if unavailable. The handle
    is intentionally NOT closed here: it becomes the detached waiter's stdout/stderr
    (via ``apply``), so the waiter's — and the relaunched image's — output is
    captured for post-mortem if a future relaunch fails silently."""
    path = _relaunch_log_path()
    if path is None:
        return None
    try:
        return path.open("a", encoding="utf-8")
    except OSError:  # logging must never block the relaunch
        return None


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
        *on_before_exec* (the key-wipe) **after** the swap and **before** the
        relaunch (INV-6). Does not return."""
        ...


class AppImageInstaller:
    """Swap ``$APPIMAGE`` for a verified download, then relaunch it detached (D8)."""

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
        # over, since the relaunch replaces this process and never runs Qt's
        # aboutToQuit (INV-6). Then relaunch the just-swapped AppImage.
        on_before_exec()
        # Relaunch via a DETACHED WAITER, then hard-exit this one. Spawning the new
        # image and immediately exiting (the 0.1.4→0.1.5 attempt) still raced the
        # old image's teardown: the fresh onefile bootloader collided with the
        # still-mounted FUSE image and died ("closed but didn't reopen"). Instead we
        # spawn a tiny /bin/sh that WAITS for this process to fully exit — FUSE
        # unmounted, _MEI extraction dir cleaned — and only THEN execs the swapped
        # image with a reset environment (see _relaunch_env / _relaunch_command). A
        # NEW SESSION lets the waiter outlive this process's exit. Any output is
        # captured to the relaunch log so a future silent failure leaves evidence.
        pid = os.getpid()
        log = _relaunch_log_handle()
        if log is not None:
            log.write(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} relaunch: swapped in "
                f"{self._appimage_path}; waiting on pid {pid} then exec\n"
            )
            log.flush()
        stdio: TextIO | int = log if log is not None else subprocess.DEVNULL
        subprocess.Popen(  # noqa: S603  # nosec B603 — fixed /bin/sh waiter, our own argv
            _relaunch_command(str(self._appimage_path), pid),
            env=_relaunch_env(),
            stdin=subprocess.DEVNULL,
            stdout=stdio,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        os._exit(0)


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
