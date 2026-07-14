"""The platform seam for installing an update (FIBR-0054 D6/D8; FIBR-0131).

``Installer`` is the protocol the updater talks to. Two implementations:
``AppImageInstaller`` (Linux) swaps ``$APPIMAGE`` in place — "install" is *replace
one file, spawn a fresh detached copy, and exit* (a plain in-place re-exec can't
replace a busy FUSE mount — see ``apply``). ``WindowsInstaller`` (FIBR-0131) can't
replace the running ``.exe`` in place (the OS locks it), so it spawns a detached
PowerShell helper that waits until the ``.exe`` image is free, moves the verified
new ``.exe`` over the old, and relaunches. ``detect_installer()`` returns the right
one — a frozen Windows ``.exe`` → ``WindowsInstaller``, a real AppImage
(``$APPIMAGE`` set + present) → ``AppImageInstaller``, else ``None`` (a
``python -m finbreak`` run, a Flatpak, a future macOS ``.app``), so the feature
stays inert off a supported package (INV-7).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess  # nosec B404 — fixed-argv waiter, our own paths, no user input
import sys
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


# --------------------------------------------------------------------------- #
# Windows relaunch helpers (FIBR-0131) — the out-of-process swap+relaunch.
# --------------------------------------------------------------------------- #
# A running Windows .exe is locked by the OS and (as a PyInstaller onefile build)
# has extracted itself to %TEMP%\_MEIxxxxxx, so it can't be replaced in place. The
# helper below is the Windows twin of the /bin/sh waiter: a detached PowerShell
# process that waits until the .exe IMAGE is free (tree-agnostic + PID-recycling-
# proof — see _windows_relaunch_command), moves the verified new .exe over the old,
# and relaunches it.

# The number of native onefile teardown vars is Windows-specific; only the reset
# flag is needed (no POSIX loader-path fixups — that's the Linux _relaunch_env).


def _windows_relaunch_env() -> dict[str, str]:
    """Environment for the Windows relaunch helper (and, via ``Start-Process``
    inheritance, the relaunched ``.exe``): ``os.environ`` + PyInstaller's official
    restart signal so the fresh onefile bootloader re-extracts instead of colliding
    with the exited parent's ``_MEIxxxxxx`` dir (FIBR-0131 INV-5). No ``LD_*``
    restoration — that's a POSIX-only concern (see ``_relaunch_env``)."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _powershell_path() -> str:
    """An **absolute** ``powershell.exe`` path — resolved from ``%SystemRoot%``
    (else ``shutil.which``), never a bare ``"powershell"``: a ``DETACHED_PROCESS``
    child can run with a stripped ``PATH`` and fail to launch a bare name (FIBR-0131
    D3). Falls back to ``"powershell.exe"`` if nothing resolves (e.g. off Windows)."""
    system_root = os.environ.get("SystemRoot")
    if system_root:
        candidate = (
            Path(system_root)
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        if candidate.is_file():
            return str(candidate)
    return shutil.which("powershell") or "powershell.exe"


def _ps_single_quote(text: str) -> str:
    """A PowerShell single-quoted literal of *text* — the only escape inside single
    quotes is a doubled ``'`` — so a path with a space or apostrophe can't break the
    ``-Command`` script (FIBR-0131 D3)."""
    return "'" + text.replace("'", "''") + "'"


def _windows_relaunch_command(exe: str, new_file: str) -> list[str]:
    """A detached PowerShell waiter that installs *new_file* over *exe* then
    relaunches *exe* (FIBR-0131 D3/INV-3).

    It waits by the exe **image path**, not a PID: a onefile Windows build is a
    parent-bootloader→child-app tree and the on-disk ``.exe`` lock is held while
    either runs, and Windows recycles PIDs — so it polls until **no** process is
    running ``exe`` (``Get-Process ... $_.Path -eq $exe``), which is tree-agnostic
    and recycling-proof. On a ~60 s cap elapsing with the image still busy it
    **aborts** (removes the staged temp, no move, no relaunch) so it can never spawn
    a second instance over a still-running first. Otherwise it retries the move
    (AV/indexer lock-lag), removing the temp if the move ultimately fails, and
    relaunches. ``exe``/``new_file`` are our own paths (``sys.executable`` + the
    verified staged temp), never user input; both are single-quote-escaped."""
    exe_q = _ps_single_quote(exe)
    new_q = _ps_single_quote(new_file)
    # A live process running the target .exe image (single braces — this is a plain
    # string spliced into the f-strings below, not itself an f-string).
    running = (
        "Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }"
    )
    rm_temp = "Remove-Item -LiteralPath $new -Force -ErrorAction SilentlyContinue"
    script = (
        f"$exe = {exe_q}; $new = {new_q}; "
        # Poll until the .exe image is free (~60 s cap = 300 x 200 ms).
        f"for ($i = 0; $i -lt 300; $i++) {{ "
        f"if (-not ({running})) {{ break }}; Start-Sleep -Milliseconds 200 }} "
        # Cap elapsed and still busy -> abort: don't orphan the temp, don't relaunch.
        f"if ({running}) {{ {rm_temp}; exit 1 }} "
        # Image free: retry the move (5 x 500 ms) for AV/indexer lock-lag.
        f"$moved = $false; "
        f"for ($j = 0; $j -lt 5; $j++) {{ try {{ "
        f"Move-Item -LiteralPath $new -Destination $exe -Force -ErrorAction Stop; "
        f"$moved = $true; break }} catch {{ Start-Sleep -Milliseconds 500 }} }} "
        # A move that never took: clean the temp (no accretion), still relaunch old.
        f"if (-not $moved) {{ {rm_temp} }} "
        f"Start-Process -FilePath $exe"
    )
    return [_powershell_path(), "-NoProfile", "-NonInteractive", "-Command", script]


@runtime_checkable
class Installer(Protocol):
    """How the updater installs a verified download on this platform (D6)."""

    def can_self_update(self) -> bool: ...

    def target_path(self) -> Path:
        """The file to replace. Its ``.parent`` is where the download stages its
        temp on the same filesystem, so the swap is a local same-directory move —
        an atomic ``os.replace`` on Linux, an out-of-process ``Move-Item`` on
        Windows (INV-5)."""
        ...

    def asset_suffix(self) -> str:
        """The release-asset filename suffix this platform installs —
        ``-x86_64.AppImage`` on Linux, ``-x86_64.exe`` on Windows. The updater's
        asset-picker matches this + ``.sig`` (FIBR-0131 D2)."""
        ...

    def apply(self, new_file: Path, on_before_exec: Callable[[], None]) -> NoReturn:
        """Install *new_file* (already signature-verified) and relaunch. Runs
        *on_before_exec* (the key-wipe) after this process commits to replacing the
        running binary and before the relaunch — in-process after ``os.replace`` on
        Linux, before spawning the swap helper on Windows (INV-6). Does not
        return."""
        ...


class AppImageInstaller:
    """Swap ``$APPIMAGE`` for a verified download, then relaunch it detached (D8)."""

    def __init__(self, appimage_path: Path):
        self._appimage_path = appimage_path

    def can_self_update(self) -> bool:
        return True

    def target_path(self) -> Path:
        return self._appimage_path

    def asset_suffix(self) -> str:
        return "-x86_64.AppImage"

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


class WindowsInstaller:
    """Swap a frozen Windows ``.exe`` for a verified download out-of-process, then
    relaunch it (FIBR-0131). The running ``.exe`` is locked, so — unlike the AppImage
    — ``apply`` does **not** move the file itself: it wipes the key, spawns a detached
    PowerShell helper that waits for the image to free, moves the new ``.exe`` over
    this one, and relaunches; then hard-exits."""

    def __init__(self, exe_path: Path):
        self._exe_path = exe_path

    def can_self_update(self) -> bool:
        return True

    def target_path(self) -> Path:
        return self._exe_path

    def asset_suffix(self) -> str:
        return "-x86_64.exe"

    def apply(self, new_file: Path, on_before_exec: Callable[[], None]) -> NoReturn:
        # No in-process swap — the running .exe is locked by the OS. Wipe the key
        # now (the relaunch replaces this process and never runs Qt's aboutToQuit,
        # INV-6/INV-4), then hand the physical move to a detached helper that runs
        # AFTER we exit. There is no pre-wipe file op that can fail here (the
        # writability probe already happened at download-stage time, INV-6).
        on_before_exec()
        log = _relaunch_log_handle()
        if log is not None:
            log.write(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} relaunch: staged "
                f"{new_file}; waiting for {self._exe_path} image to free then "
                f"move + relaunch\n"
            )
            log.flush()
        stdio: TextIO | int = log if log is not None else subprocess.DEVNULL
        # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP are Windows-only attributes;
        # getattr(..., 0) keeps this importable + callable off Windows (the Linux CI
        # gate drives apply() through a monkeypatched Popen — FIBR-0131 D3).
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        subprocess.Popen(  # noqa: S603  # nosec B603 — fixed PowerShell waiter, our own argv
            _windows_relaunch_command(str(self._exe_path), str(new_file)),
            env=_windows_relaunch_env(),
            stdin=subprocess.DEVNULL,
            stdout=stdio,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
        )
        os._exit(0)


def detect_installer() -> Installer | None:
    """The platform's installer, or ``None`` when self-update can't run here (INV-7).

    A frozen Windows ``.exe`` → ``WindowsInstaller`` (``sys.executable`` is the
    running ``.exe``). Else a real AppImage (``$APPIMAGE`` set + pointing at an
    existing file) → ``AppImageInstaller``. Else ``None`` — a ``python -m finbreak``
    dev run, a Flatpak, a future macOS ``.app``, so the feature stays inert."""
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return WindowsInstaller(Path(sys.executable))
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
