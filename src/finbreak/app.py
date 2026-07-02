"""Application entry — build the QApplication and route first-run vs unlock.

Routing (FIBR-0004 INV-5): neither vault nor sidecar → first-run; both → unlock;
a mixed pair is a corrupt install surfaced to the user, not a silent
re-first-run. The key is wiped on quit via ``aboutToQuit`` (INV-3).
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication, QMessageBox, QStackedWidget, QWidget

from finbreak import paths
from finbreak.errors import VaultStateError
from finbreak.services.auth import AuthService
from finbreak.ui.accounts import AccountsWidget
from finbreak.ui.first_run import FirstRunWidget
from finbreak.ui.main_window import MainWindow
from finbreak.ui.unlock import UnlockWidget


class AppShell(QStackedWidget):
    def __init__(self, service: AuthService):
        super().__init__()
        self._service = service
        # An idle auto-lock wipes the key + closes the vault on the service; route
        # the UI back to the unlock screen so the next action can't hit a locked
        # vault (same destination as the manual Lock button).
        service.on_auto_lock = self._show_unlock
        self.setWindowTitle("finbreak")
        if service.state() == "first_run":
            self._show_first_run()
        else:
            self._show_unlock()

    def _show_first_run(self) -> None:
        widget = FirstRunWidget(self._service)
        widget.completed.connect(self._show_main)
        self._swap(widget)

    def _show_unlock(self) -> None:
        widget = UnlockWidget(self._service)
        widget.unlocked.connect(self._show_main)
        self._swap(widget)

    def _show_main(self) -> None:
        widget = MainWindow(self._service)
        widget.locked.connect(self._show_unlock)
        widget.manage_accounts.connect(self._show_accounts)
        self._swap(widget)

    def _show_accounts(self) -> None:
        # A normal stacked view (not a modal), so an idle auto-lock swaps it away
        # like any other screen. On Done, a fresh MainWindow re-reads accounts.
        widget = AccountsWidget(self._service)
        widget.done.connect(self._show_main)
        self._swap(widget)

    def _swap(self, widget: QWidget) -> None:
        for i in reversed(range(self.count())):
            old = self.widget(i)
            if old is not None:
                self.removeWidget(old)
                old.deleteLater()
        self.addWidget(widget)
        self.setCurrentWidget(widget)


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setLayoutDirection(QLocale().textDirection())

    service = AuthService(paths.vault_path(), paths.sidecar_path())
    app.aboutToQuit.connect(service.on_about_to_quit)

    try:
        shell = AppShell(service)
    except VaultStateError as exc:
        QMessageBox.critical(
            None,
            "finbreak",
            f"The vault install is incomplete or corrupt:\n{exc}\n\n"
            "Remove the partial data files to start over.",
        )
        return 1

    shell.show()
    return app.exec()
