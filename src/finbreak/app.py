"""Application entry — build the QApplication and show the shell window.

The ``MainWindow`` (a ``QMainWindow``) owns the startup routing (FIBR-0051):
first-run vs unlock is decided from ``presence_state()`` and driven by popup
dialogs over the window. A mixed vault/sidecar pair raises ``VaultStateError`` out
of the shell's construction — a corrupt install surfaced to the user, not a
silent re-first-run — so the window is never shown. The key is wiped on quit via
``aboutToQuit`` (FIBR-0004 INV-3).
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import suppress
from typing import cast

from PySide6.QtCore import QCoreApplication, QLocale, Qt, QThread, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from finbreak import paths, single_instance
from finbreak.errors import FinbreakError, InterruptedRestoreError, VaultStateError
from finbreak.loader_env import restore_system_loader_env
from finbreak.log_file import install_log_file
from finbreak.services.auth import AuthService
from finbreak.services.update import remove_stale_staged_updates
from finbreak.services.update_installer import detect_installer
from finbreak.ui.icons import app_icon
from finbreak.ui.main_window import MainWindow, settle_detached_workers
from finbreak.ui.theme import ThemeController, load_theme_pref

# Translation outside a QObject (this module is not one) calls
# QCoreApplication.translate with the LITERAL at each site, never through a
# _tr(text) wrapper: lupdate reads the argument statically, so a wrapper extracts
# an empty catalogue entry while reading at the call site as though it were
# handled. tests/features/i18n enforces that, with pdf_export.py the one named
# exception (FIBR-0311).


def _install_excepthook() -> None:
    """Show an unhandled exception instead of vanishing.

    Only ``VaultStateError`` was ever caught, and a windowed build has no console
    -- PyInstaller's ``--noconsole`` on Windows, and the AppImage launched from a
    menu. So the default hook wrote a traceback to a stderr nobody sees, and any
    other startup failure produced an app that does nothing when double-clicked,
    with nothing the user could report (FIBR-0327).

    Chains the previous hook rather than replacing it, so a run WITH a console
    still gets the traceback; the dialog is the addition. Its own failure is
    swallowed, because a broken dialog must not replace the fault it is reporting.
    """
    previous = sys.excepthook

    def hook(exc_type: type[BaseException], exc: BaseException, tb: object) -> None:
        previous(exc_type, exc, tb)  # type: ignore[arg-type]

        def show() -> None:
            with suppress(Exception):
                QMessageBox.critical(
                    None,
                    "finbreak",
                    QCoreApplication.translate(
                        "App",
                        "finbreak hit an unexpected error and cannot continue:"
                        "\n{error}",
                    ).format(error=f"{exc_type.__name__}: {exc}"),
                )

        # PySide6 runs this hook on the thread that raised, and a QThread's
        # run() is one: a widget may only be built on the GUI thread, so the
        # dialog is posted there (FIBR-0392).
        app = QCoreApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            QTimer.singleShot(0, app, show)
        else:
            show()

    sys.excepthook = hook


def _restore_loader_env_if_frozen() -> None:
    """Give every child the SYSTEM loader path, not the bundle's (FIBR-0364).

    The frozen app's own loader has already read ``LD_LIBRARY_PATH``, so changing
    ``os.environ`` now reaches only the processes it starts — ``xdg-open`` behind
    ``QDesktopServices.openUrl`` among them. Windows has no such variables.
    """
    if getattr(sys, "frozen", False) and sys.platform != "win32":
        restore_system_loader_env(os.environ)


def run(argv: list[str] | None = None) -> int:
    _restore_loader_env_if_frozen()
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

    # After the QApplication, because the hook shows a dialog; before anything
    # that can fail, because that is what it is for.
    _install_excepthook()

    # The local log file design.md § Observability promises (FIBR-0410). A data
    # folder that cannot be found is reported later by the vault's own path
    # lookup, so it is not reported twice here.
    with suppress(FinbreakError):
        install_log_file(paths.data_dir())

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
    except InterruptedRestoreError as exc:
        QMessageBox.critical(
            None,
            "finbreak",
            QCoreApplication.translate(
                "App",
                "finbreak was interrupted while restoring a backup, and could not "
                "put your previous data back.\n\n"
                "Your previous data is safe. It is kept in files ending in "
                "“.old” in this folder:\n{folder}\n\n"
                "Do not delete those files. If the folder is read-only or the disk "
                "is full, fix that and start finbreak again: it will finish putting "
                "your data back by itself.",
            ).format(folder=exc.directory),
        )
        return 1
    except VaultStateError as exc:
        QMessageBox.critical(
            None,
            "finbreak",
            QCoreApplication.translate(
                "App",
                "The vault install is incomplete or corrupt:\n{error}\n\n"
                "Remove the partial data files to start over.",
            ).format(error=exc),
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
    return _finish(app.exec())


# How long, after the event loop ends, a detached update worker may still take to
# finish before the process ends without it.
_EXIT_GRACE_MS = 3000


def _finish(code: int) -> int:
    """End the run without destroying a thread that is still running.

    A launch update check blocked on a slow network (its socket timeout is 30 s)
    outlasts the window's drain and is detached so the WINDOW can close. Python's
    own shutdown would then destroy that running QThread, which Qt answers with
    abort() and a core dump (full audit 2026-09-27, row 28). So give it a grace;
    if it is still blocked, end the process before interpreter teardown. The
    vault was already locked on ``aboutToQuit``, and the worker's signals were
    blocked when it was detached, so nothing it could still do is lost.
    """
    if settle_detached_workers(_EXIT_GRACE_MS):
        return code
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


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
