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


def test_INV3b_two_launches_recovering_one_stale_socket_do_not_both_win(
    qapp, name, monkeypatch
):
    """Two launches clearing ONE stale socket must not both become the owner.

    INV-3a shut the door where a speculative clear evicts a LIVE owner. This is
    the door it left open, and it needs no timing fluke at all: with a genuine
    crash leftover at the path, BOTH launches get ``AddressInUseError``, BOTH
    probe a socket nobody is behind, BOTH conclude "stale, safe to clear" — and
    the second one's ``removeServer`` unlinks the FIRST one's freshly-bound,
    live socket. Two writers on one SQLCipher file, reached from the other side.

    Driven by INTERPOSING the second launch at the moment the first decides the
    path is stale, rather than by starting two processes and hoping they
    collide. A race proved by repetition is a race that passes on a fast
    machine.
    """
    probe_server = QLocalServer()
    assert probe_server.listen(name)
    stale_path = probe_server.fullServerName()
    probe_server.close()  # tidy removal, so the bind below owns the path

    orphan = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    orphan.bind(stale_path)  # the file exists...
    orphan.close()  # ...but nothing is listening on it
    assert os.path.exists(stale_path), "the fixture did not leave a stale socket"

    real_probe = single_instance.another_instance_is_running
    interposed: list[bool] = []
    racer: list[QLocalServer | None] = []

    def _probe_then_race(server_name: str) -> bool:
        answer = real_probe(server_name)
        # The first launch has just been told nobody is home. A second launch
        # reaching the same point reaches the same conclusion on the same
        # evidence — so let it run, right here, before the first one acts on it.
        if not interposed and answer is False:
            interposed.append(True)  # set BEFORE recursing
            racer.append(single_instance.listen(server_name))
        return answer

    monkeypatch.setattr(
        single_instance, "another_instance_is_running", _probe_then_race
    )
    first = single_instance.listen(name)
    monkeypatch.undo()

    assert interposed, (
        "the second launch was never interposed, so this test proves nothing "
        "about the race it is named for"
    )
    owners = [server for server in [first, *racer] if server is not None]
    try:
        assert len(owners) == 1, (
            "two launches recovering one stale socket both became the owner, so "
            "one of them is bound to an unlinked inode and unreachable forever "
            "— two processes on one vault"
        )
        assert single_instance.another_instance_is_running(name) is True, (
            "the surviving owner must still be REACHABLE: an unlinked socket "
            "still reports isListening() while no probe can ever connect to it"
        )
    finally:
        for server in owners:
            server.close()


# --------------------------------------------------------------------------- #
# INV-4 — the socket is per-user
# --------------------------------------------------------------------------- #
def test_INV4_socket_name_is_scoped_to_the_user(monkeypatch, tmp_path):
    """QLocalServer's socket lives in a SHARED temp dir on Unix, so an unqualified
    name would let one user's launch bounce off another's session — and that second
    user could never open the app at all.

    Two branches. With ``$XDG_RUNTIME_DIR`` set the name is an absolute path under
    it: that directory is specified user-owned and 0700, which also closes the
    FIBR-0204 denial of service — in world-writable /tmp any local account can
    pre-bind the predictable name, and finbreak's probe then reads it as "already
    running" and exits 0 with no window and no message. Without the variable we
    fall back to the uid-suffixed bare name, because refusing to start would be
    worse than a guard a hostile local user can block.
    """
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert single_instance.socket_name() == str(tmp_path / "finbreak.sock")

    # An overlong runtime dir must fall back to the short name rather than
    # return a path AF_UNIX cannot bind: past ~107 bytes every listen() fails and
    # the guard would silently disable itself, letting two instances open one
    # vault with nothing shown to the user. Switching to an absolute path is what
    # introduced this mode — a bare name was always short enough (FIBR-0204).
    long_dir = tmp_path / ("d" * 120)
    long_dir.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(long_dir))
    fallback = single_instance.socket_name()
    assert not fallback.startswith(str(long_dir)), (
        f"an unbindable {len(str(long_dir)) + 14}-byte path was returned instead "
        "of falling back to the short name"
    )

    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
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
