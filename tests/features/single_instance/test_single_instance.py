"""FIBR-0189 — one finbreak per OS user.

Enforces tests/features/single_instance/spec.md. Exercises the real
``QLocalServer``/``QLocalSocket`` pair (no mocks — the whole point is the socket
handshake), each test on a name derived from ``tmp_path`` so concurrent runs and
a developer's own running finbreak can never collide.
"""

from __future__ import annotations

import os
import socket

import pytest
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from finbreak import single_instance

pytestmark = pytest.mark.features


@pytest.fixture
def name(tmp_path) -> str:
    """A socket name unique to this test run."""
    return f"finbreak-test-{abs(hash(str(tmp_path))) % 10_000_000}"


@pytest.fixture(autouse=True)
def _cleanup(name):
    yield
    QLocalServer.removeServer(name)


# --------------------------------------------------------------------------- #
# INV-1 — the second launch detects the first and is told to stand down
# --------------------------------------------------------------------------- #
def test_INV1_second_launch_sees_the_running_instance(qapp, name):
    assert single_instance.another_instance_is_running(name) is False, (
        "nothing is listening yet, so a launch must proceed"
    )
    server = single_instance.listen(name)
    assert server is not None

    assert single_instance.another_instance_is_running(name) is True
    server.close()


def test_INV1_after_the_owner_exits_a_launch_proceeds(qapp, name):
    server = single_instance.listen(name)
    assert server is not None
    server.close()
    assert single_instance.another_instance_is_running(name) is False


# --------------------------------------------------------------------------- #
# INV-2 — the owner is woken, so it can raise its window
# --------------------------------------------------------------------------- #
def test_INV2_the_probe_wakes_the_owner(qtbot, name):
    server = single_instance.listen(name)
    assert server is not None
    with qtbot.waitSignal(server.newConnection, timeout=2000):
        assert single_instance.another_instance_is_running(name) is True
    assert server.nextPendingConnection() is not None
    server.close()


# --------------------------------------------------------------------------- #
# INV-3 — a crash must not make the app permanently unlaunchable
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="stale socket FILES are a Unix concern"
)
def test_INV3_a_stale_socket_does_not_block_a_fresh_start(qapp, name):
    """A SIGKILLed process leaves its socket file behind on Unix. Without the
    removeServer guard, every later listen() fails and the app never opens again.

    Qt's own destructor cleans up, so an orphan cannot be faked by dropping a
    QLocalServer — the file has to be left behind directly, which is what a kill
    -9 actually does: bind (file appears), then vanish with nothing listening.
    """
    probe_server = QLocalServer()
    assert probe_server.listen(name)
    stale_path = probe_server.fullServerName()
    probe_server.close()  # tidy removal, so the bind below owns the path

    orphan = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    orphan.bind(stale_path)  # the file exists...
    orphan.close()  # ...but nothing is listening on it
    assert os.path.exists(stale_path), "the fixture did not leave a stale socket"

    assert single_instance.another_instance_is_running(name) is False, (
        "a stale socket has no listener, so it must not look like a live instance"
    )
    server = single_instance.listen(name)
    assert server is not None, "listen() must clear the stale socket and succeed"
    server.close()


def test_INV3a_a_live_owner_is_never_evicted(qapp, name):
    """The stale-socket clear must not be able to evict a LIVE owner.

    ``listen()`` used to call ``removeServer`` unconditionally, which unlinks
    whatever is at the path — including a running instance's socket. Two
    launches racing between the probe and the listen therefore both ended up
    "listening" on one name, and the first owner's server was left bound to an
    unlinked inode: permanently unreachable. Two processes then write the same
    SQLCipher file, which is the exact hazard this feature exists to prevent.

    This is INV-3's twin: INV-3 says a socket with nobody behind it MUST be
    cleared, this says a socket with somebody behind it must NOT be.
    """
    owner = single_instance.listen(name)
    assert owner is not None, "the first launch must become the owner"

    intruder = single_instance.listen(name)
    assert intruder is None, (
        "a second listen() while the owner is live must fail, not evict it"
    )
    assert owner.isListening(), "the owner must still be listening"
    assert single_instance.another_instance_is_running(name) is True, (
        "the owner must still be REACHABLE — an unlinked socket still reports "
        "isListening() while no probe can ever connect to it again"
    )
    owner.close()


# --------------------------------------------------------------------------- #
# INV-4 — the socket is per-user
# --------------------------------------------------------------------------- #
def test_INV4_socket_name_is_scoped_to_the_user():
    """QLocalServer's socket lives in a SHARED temp dir on Unix, so an unqualified
    name would let one user's launch bounce off another's session — and that second
    user could never open the app at all."""
    resolved = single_instance.socket_name()
    if hasattr(os, "getuid"):
        assert resolved == f"finbreak-{os.getuid()}"
    else:
        assert resolved == "finbreak"


# --------------------------------------------------------------------------- #
# INV-5 — the update relaunch releases the socket before spawning its replacement
# --------------------------------------------------------------------------- #
def test_INV5_relaunch_releases_the_socket_before_wiping_the_key(qapp, name):
    """The replacement process probes this socket as it starts. If the outgoing
    process still held it, the new instance would exit and the update would appear
    to do nothing — the 0.1.2→0.1.3 "closed but didn't reopen" shape."""
    from finbreak.ui.main_window import MainWindow

    order: list[str] = []

    class _Guard:
        def close(self) -> None:
            order.append("released")

    class _Service:
        def on_about_to_quit(self) -> None:
            order.append("key wiped")

    window = MainWindow.__new__(MainWindow)  # no vault needed for this seam
    window._service = _Service()
    window.set_single_instance_guard(_Guard())
    window._release_for_relaunch()

    assert order == ["released", "key wiped"], (
        "the socket must be freed before the key wipe hands off to the relaunch"
    )


def test_INV5_relaunch_without_a_guard_still_wipes_the_key(qapp):
    """Running unguarded (listen() failed) must not break the update path."""
    from finbreak.ui.main_window import MainWindow

    wiped: list[str] = []

    class _Service:
        def on_about_to_quit(self) -> None:
            wiped.append("key wiped")

    window = MainWindow.__new__(MainWindow)
    window._service = _Service()
    window.set_single_instance_guard(None)
    window._release_for_relaunch()

    assert wiped == ["key wiped"]


# --------------------------------------------------------------------------- #
# INV-6 — a knock raises the existing window
# --------------------------------------------------------------------------- #
def test_INV6_a_knock_unminimises_and_raises_the_window(qtbot, name):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    from finbreak.app import _raise_existing

    window = QWidget()
    qtbot.addWidget(window)
    window.show()
    window.setWindowState(Qt.WindowState.WindowMinimized)
    assert window.windowState() & Qt.WindowState.WindowMinimized

    server = single_instance.listen(name)
    assert server is not None
    probe = QLocalSocket()
    probe.connectToServer(name)
    assert probe.waitForConnected(2000)
    qtbot.waitUntil(lambda: server.hasPendingConnections(), timeout=2000)

    _raise_existing(server, window)

    assert not (window.windowState() & Qt.WindowState.WindowMinimized), (
        "a minimised window must be restored, not just re-shown behind others"
    )
    probe.disconnectFromServer()
    server.close()
