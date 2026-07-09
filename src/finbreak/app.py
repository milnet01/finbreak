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

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication, QMessageBox

from finbreak import paths
from finbreak.errors import VaultStateError
from finbreak.services.auth import AuthService
from finbreak.ui.icons import app_icon
from finbreak.ui.main_window import MainWindow


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setWindowIcon(app_icon())  # branded icon on every window + the taskbar
    app.setLayoutDirection(QLocale().textDirection())

    service = AuthService(paths.vault_path(), paths.sidecar_path())
    app.aboutToQuit.connect(service.on_about_to_quit)

    try:
        window = MainWindow(service)
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
