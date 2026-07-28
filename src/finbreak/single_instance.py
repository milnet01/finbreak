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

from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

# Long enough for a loopback handshake on a loaded machine, short enough that a
# launch never feels stalled — the probe runs before any window is built.
_PROBE_MS = 500

# Any payload wakes the owner's newConnection; the content is not parsed, so the
# protocol cannot drift between versions of the app talking to each other during
# an update relaunch.
_NUDGE = b"raise"


def socket_name(base: str = "finbreak") -> str:
    """The per-user socket name. ``os.getuid`` is POSIX-only; on Windows the named
    pipe is already per-session, so the bare base name is correct there."""
    uid = os.getuid() if hasattr(os, "getuid") else None
    return base if uid is None else f"{base}-{uid}"


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

    ``removeServer`` first: a process killed with SIGKILL (or an OOM kill, or a
    crash) leaves its socket file behind on Unix, and a stale file makes every
    later ``listen()`` fail — which would render the app permanently unlaunchable.
    Removing it is only safe because the caller has *already* probed and found
    nobody listening; a live owner wins that race, not this cleanup.
    """
    QLocalServer.removeServer(name)
    server = QLocalServer()
    if not server.listen(name):
        log.debug("single-instance: could not listen on %r; running unguarded", name)
        return None
    return server
