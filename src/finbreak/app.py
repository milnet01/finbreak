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

from PySide6.QtCore import QLocale
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from finbreak import paths
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
    # Identify as "finbreak" so the running window's Wayland app_id (and X11
    # WM_CLASS) matches finbreak.desktop (StartupWMClass=finbreak). Without this,
    # a `python -m finbreak` launch reports the interpreter's name, so the desktop
    # task manager can't associate the window with its launcher and shows a second,
    # generic icon. desktopFileName is the app_id source on Wayland (Qt 6).
    app.setApplicationName("finbreak")
    QGuiApplication.setDesktopFileName("finbreak")
    app.setWindowIcon(app_icon())  # branded icon on every window + the taskbar
    app.setLayoutDirection(QLocale().textDirection())

    # Apply the stored theme BEFORE the main window, so the very first, still-locked
    # window is themed (FIBR-0127 INV-1). The controller parents to the app and
    # follows the OS scheme live while in "system" mode.
    theme_controller = ThemeController(app)
    theme_controller.set_theme(load_theme_pref(), persist=False)

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
    return app.exec()
