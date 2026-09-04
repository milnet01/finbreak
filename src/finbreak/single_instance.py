"""Single-instance guard (FIBR-0189) — one finbreak per OS user.

Two small functions over Qt's ``QLocalSocket``/``QLocalServer``, in the canonical
probe-then-listen order:

* :func:`another_instance_is_running` opens a client socket. A connection means a
  live owner is listening, so this launch should hand over and exit — it sends a
  one-byte nudge first so the owner can raise its window.
* :func:`listen` makes *this* process the owner.

The pair **fails open**: if the probe finds nobody but ``listen()`` still fails
(a read-only runtime dir, an exotic sandbox), the caller runs the app anyway,
just unguarded. Refusing to start would be a far worse failure than briefly
allowing two windows.

The socket name carries the uid, because ``QLocalServer`` puts its socket in a
shared temp dir on Unix — an unqualified name would let one user's launch bounce
off another's session, and the second user could never open the app at all.

The vault is one SQLCipher file, so this is data hygiene as much as tidiness: two
processes writing the same database is a race nothing else in the app guards
against.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtNetwork import QAbstractSocket, QLocalServer, QLocalSocket

try:
    import fcntl
except ImportError:  # Windows — see `_claim`
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Long enough for a loopback handshake on a loaded machine, short enough that a
# launch never feels stalled — the probe runs before any window is built.
_PROBE_MS = 500

# Any payload wakes the owner's newConnection; the content is not parsed, so the
# protocol cannot drift between versions of the app talking to each other during
# an update relaunch.
_NUDGE = b"raise"

# Usable bytes for an AF_UNIX socket path. The kernel's sun_path is 108 bytes
# including the NUL (measured: a raw bind fails at 108 chars, succeeds at 107),
# and Qt refuses one byte earlier again. 100 keeps a margin under both.
_MAX_UNIX_SOCKET_PATH = 100


def socket_name(base: str = "finbreak") -> str:
    """The per-user socket name — an absolute path under ``$XDG_RUNTIME_DIR`` when
    that is available, else a uid-suffixed bare name.

    ``QLocalServer`` puts a bare name in a **shared** temp dir on Unix (``/tmp``),
    which is world-writable. Any other local account can pre-create and listen on
    that path; finbreak's probe then connects successfully, ``app.py`` treats it
    as "another instance is already running" and returns 0 — **no window, no
    message, exit status 0**. That is an undiagnosable denial of service, and the
    uid suffix does not prevent it (it only stops two *users* colliding by
    accident, which is the separate INV-4 concern).

    ``$XDG_RUNTIME_DIR`` is specified to be user-owned and mode 0700, so nothing
    can be planted there by another account. Qt honours an absolute name for both
    ``listen`` and ``connectToServer``, so the probe/listen pair is unaffected.

    Falls back to the old shared-dir name when the variable is unset (a bare
    ``su``, some containers, macOS, Windows) — the guard is best-effort, and an
    app that will not start is worse than one that can be blocked by a hostile
    local user. Windows named pipes are already per-session, so the bare base
    name is correct there.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        candidate = os.path.join(runtime_dir, f"{base}.sock")
        # An AF_UNIX socket path is capped at 107 bytes (measured; Qt fails one
        # byte tighter still, reserving room for its lock-file suffix). A bare
        # name was always short enough, so switching to an absolute path
        # introduces a length failure mode that did not exist before: past the
        # cap every `listen()` fails, the guard silently disables itself, and two
        # instances can open one vault with nothing shown to the user. Qt at
        # least fails cleanly rather than truncating — two long paths colliding
        # on one name would be worse — but a disabled guard is not what we want,
        # so fall back to the short name rather than return an unusable path.
        # /run/user/<uid>/finbreak.sock is 28 bytes, so this is headroom, not a
        # case anyone hits on a normal desktop.
        if len(candidate.encode()) <= _MAX_UNIX_SOCKET_PATH:
            return candidate
    uid = os.getuid() if hasattr(os, "getuid") else None
    return base if uid is None else f"{base}-{uid}"


def _claim_path(name: str) -> str:
    """Where the recovery claim for socket *name* lives.

    Deliberately NOT ``<name>.lock``: Qt already creates that file beside its
    own socket, which is why `socket_name` keeps a byte of headroom for it.
    Taking it would be fighting the library for its own bookkeeping.
    """
    if os.path.isabs(name):
        return f"{name}.claim"
    # A bare name is resolved by Qt into a shared temp dir, so the claim goes
    # to the same place, under the same name.
    return os.path.join(tempfile.gettempdir(), f"{name}.claim")


@contextmanager
def _claim(name: str) -> Iterator[bool]:
    """Hold the exclusive right to RECOVER *name*; yields False if someone else
    holds it.

    `removeServer` then `listen` is two syscalls with nothing between them, so
    two launches clearing ONE crash leftover both unlink and both bind — and
    the second unlinks the first's freshly-bound, live socket. That needs no
    timing fluke: both got AddressInUseError from the same stale file and both
    probed the same silence, so both reach the same wrong conclusion (INV-3b).

    An `flock` makes the recovery one-at-a-time. The kernel drops it when the
    holder exits however it exits, so the lock cannot itself become the stale
    thing it exists to clear up.

    Fails OPEN, like everything else here: with nowhere to put the lock we
    recover unserialised, which is what this module did before it existed.
    """
    fd: int | None = None
    held = True
    try:
        if fcntl is not None:
            try:
                fd = os.open(_claim_path(name), os.O_CREAT | os.O_RDWR, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                held = False
            except OSError:
                log.debug("single-instance: no recovery claim for %r", name)
        yield held
    finally:
        if fd is not None:
            os.close(fd)  # releases the flock


def another_instance_is_running(name: str) -> bool:
    """True when a live instance answers on *name* (and has been nudged to raise
    its window). False means this process should carry on and become the owner."""
    probe = QLocalSocket()
    probe.connectToServer(name)
    if not probe.waitForConnected(_PROBE_MS):
        return False
    probe.write(_NUDGE)
    probe.flush()
    probe.waitForBytesWritten(_PROBE_MS)
    probe.disconnectFromServer()
    return True


def listen(name: str) -> QLocalServer | None:
    """Become the single instance on *name*, or ``None`` if that isn't possible.

    **Listen first, clear only a proven-stale socket.** A process killed with
    SIGKILL (or an OOM kill, or a crash) leaves its socket file behind on Unix,
    and a stale file makes every later ``listen()`` fail — which would render the
    app permanently unlaunchable (INV-3). But ``removeServer`` unlinks whatever
    is at the path, *including a live owner's socket*, so it cannot be called
    speculatively: the caller's earlier probe does not settle the question,
    because ``app.py`` builds and shows the whole window between that probe and
    this call. Two launches inside that window both used to end up "listening" on
    one name, with the first owner bound to an unlinked inode and unreachable
    forever — two writers on one SQLCipher file (INV-3a).

    So: try to listen; on ``AddressInUseError`` re-probe, and clear the path only
    when nobody answers. A live owner keeps its socket and this launch returns
    ``None`` — the caller's fail-open path.

    The re-probe alone was not enough. Two launches meeting ONE crash leftover
    both get ``AddressInUseError``, both probe the same silence and both clear
    it — so the second unlinks the FIRST's freshly-bound socket, which is
    INV-3a again through the other door and needs no timing fluke to happen.
    The whole recovery therefore runs under an exclusive claim, and a launch
    that cannot take it stands down (INV-3b) — see :func:`_claim`.
    """
    server = QLocalServer()
    if server.listen(name):
        return server
    if server.serverError() != QAbstractSocket.SocketError.AddressInUseError:
        log.debug("single-instance: could not listen on %r; running unguarded", name)
        return None
    with _claim(name) as claimed:
        if not claimed:
            # Another launch is recovering this very socket. It is about to
            # become the owner or to fail open; joining in is how both of us
            # end up unlinking the other's socket (INV-3b).
            log.debug("single-instance: %r is being recovered elsewhere", name)
            return None
        # No need to re-try `listen` first: whoever held the claim before us
        # either bound their own socket, which the probe below finds, or left
        # the path clear, which makes the removeServer a no-op.
        if another_instance_is_running(name):
            # A live owner holds the name (and has just been nudged to the front).
            log.debug("single-instance: %r is owned by a live instance", name)
            return None
        # Bound but unanswered: a crash leftover. Safe to clear (INV-3).
        QLocalServer.removeServer(name)
        server = QLocalServer()
        if not server.listen(name):
            log.debug(
                "single-instance: could not listen on %r; running unguarded", name
            )
            return None
        return server
