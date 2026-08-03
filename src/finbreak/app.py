"""Application entry — build the QApplication and show the shell window.

The ``MainWindow`` (a ``QMainWindow``) owns the startup routing (FIBR-0051):
first-run vs unlock is decided from ``presence_state()`` and driven by popup
dialogs over the window. A mixed vault/sidecar pair raises ``VaultStateError`` out
of the shell's construction — a corrupt install surfaced to the user, not a
silent re-first-run — so the window is never shown. The key is wiped on quit via
``aboutToQuit`` (FIBR-0004 INV-3).
"""

from __future__ import annotations

import sys
from typing import cast

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from finbreak import paths, single_instance
from finbreak.errors import VaultStateError
from finbreak.services.auth import AuthService
from finbreak.ui.icons import app_icon
from finbreak.ui.main_window import MainWindow
from finbreak.ui.theme import ThemeController, load_theme_pref


def run(argv: list[str] | None = None) -> int:
    # Reuse a live QApplication when one already exists (e.g. the pytest-qt session
    # app) — a second QApplication(sys.argv) would raise (FIBR-0127 INV-1).
    # instance() is typed QCoreApplication|None; in this GUI entry point it is always
    # a QApplication (or we construct one), so the cast is sound.
    app = cast(
        QApplication,
        QApplication.instance() or QApplication(argv if argv is not None else sys.argv),
    )
    # Window→launcher association differs by display server, so the two Qt calls
    # below deliberately carry DIFFERENT strings (FIBR-0155 § 3.3):
    #  - X11 WM_CLASS is derived by Qt's xcb backend from applicationName() and
    #    used verbatim when non-empty, so it stays the bare "finbreak" — matching
    #    the .desktop's StartupWMClass=finbreak.
    #  - Wayland app_id is QGuiApplication::desktopFileName(), which must equal the
    #    installed .desktop basename. The OBS/distro package ships the reverse-DNS
    #    io.github.milnet01.finbreak.desktop, so the app_id must be that app-ID or
    #    the taskbar shows a second, generic icon. The AppImage ships a .desktop of
    #    the same basename via APP_ID in scripts/build-smoke.sh — it did NOT until
    #    FIBR-0188 (it wrote finbreak-<version>.desktop), which is precisely why the
    #    AppImage showed the duplicate icon this comment used to claim it wouldn't.
    app.setApplicationName("finbreak")
    QGuiApplication.setDesktopFileName("io.github.milnet01.finbreak")
    app.setWindowIcon(app_icon())  # branded icon on every window + the taskbar
    app.setLayoutDirection(QLocale().textDirection())

    # Apply the stored theme BEFORE the main window, so the very first, still-locked
    # window is themed (FIBR-0127 INV-1). The controller parents to the app and
    # follows the OS scheme live while in "system" mode.
    theme_controller = ThemeController(app)
    theme_controller.set_theme(load_theme_pref(), persist=False)

    # One finbreak per OS user (FIBR-0189). Probed BEFORE any window is built, so a
    # second launch costs a socket round-trip rather than a flash of UI. The running
    # instance is nudged to the front by the probe itself.
    guard_name = single_instance.socket_name()
    if single_instance.another_instance_is_running(guard_name):
        return 0

    service = AuthService(paths.vault_path(), paths.sidecar_path())
    app.aboutToQuit.connect(service.on_about_to_quit)

    try:
        window = MainWindow(service, theme_controller=theme_controller)
    except VaultStateError as exc:
        QMessageBox.critical(
            None,
            "finbreak",
            f"The vault install is incomplete or corrupt:\n{exc}\n\n"
            "Remove the partial data files to start over.",
        )
        return 1

    window.show()

    # Claim the socket only once there is a window to raise. Fails OPEN: if the
    # probe found nobody but we still cannot listen, run unguarded rather than
    # refuse to start.
    guard = single_instance.listen(guard_name)
    if guard is None and single_instance.another_instance_is_running(guard_name):
        # Not a fail-open case — the guard WORKED. Another launch claimed the
        # socket during the window build above, so this process lost the startup
        # race; the owner has been nudged to the front. Running unguarded here
        # would put two writers on one SQLCipher file, which is the whole reason
        # the guard exists (INV-3a). Stand down instead.
        return 0
    if guard is not None:
        window.set_single_instance_guard(guard)
        guard.newConnection.connect(lambda: _raise_existing(guard, window))
    return app.exec()


def _raise_existing(guard: QLocalServer, window: QWidget) -> None:
    """A second launch knocked: drain it and bring this window to the front.

    Un-minimising needs the state cleared explicitly — ``show()`` on a minimised
    window restores it to the taskbar, not to the foreground.
    """
    connection = guard.nextPendingConnection()
    if connection is not None:
        connection.disconnectFromServer()
        connection.deleteLater()
    window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
    window.show()
    window.raise_()
    window.activateWindow()
