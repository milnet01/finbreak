"""MainWindow — the QMainWindow app shell + its state machine (FIBR-0051 D1/D2).

The top-level window: a menubar (File · View · Help · Donate), an icon toolbar, a
central ``QStackedWidget`` content area, and a status bar. First-run and unlock
are non-blocking application-modal dialogs shown *over* the window; manual entry
is a modal dialog; the content screens (Accounts / Categories / Import) and Home
live one-at-a-time in the content stack, **destroyed on swap** so no decrypted
rows survive a lock (D4/D5/INV-3). Lock and idle auto-lock both close any open
dialog, wipe the key, destroy the content, disable the vault-dependent chrome,
and re-open the UnlockDialog — window intact (INV-4).
"""

from __future__ import annotations

from collections.abc import Callable

import shiboken6
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from finbreak.services.auth import AuthService
from finbreak.services.transactions import TransactionService
from finbreak.ui.accounts import AccountsWidget
from finbreak.ui.categories import CategoriesWidget
from finbreak.ui.first_run import FirstRunDialog
from finbreak.ui.home import HomeView
from finbreak.ui.icons import icon
from finbreak.ui.import_wizard import ImportWizardWidget
from finbreak.ui.manual_entry import ManualEntryDialog
from finbreak.ui.unlock import UnlockDialog

# The three .github/FUNDING.yml donate URLs (D6/INV-8). Kept in sync with that
# file by hand — the INV-8a test reads FUNDING.yml and fails on any drift.
DONATE_GITHUB = "https://github.com/sponsors/milnet01"
DONATE_PATREON = "https://www.patreon.com/AntsProjectsHub"
DONATE_PAYBRU = "https://paybru.co.za/tip/ants-projects-hub"

_STATUS_TIMEOUT_MS = 4000


class MainWindow(QMainWindow):
    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._dialog: QDialog | None = None  # the current modal dialog, if any
        self._live: QWidget | None = None  # the current content widget, if any
        self.setWindowTitle(self.tr("finbreak"))

        # Read routing FIRST — a mixed vault/sidecar pair raises VaultStateError
        # here and propagates to run()'s guard; the window is never shown (INV-2c).
        state = service.state()

        self._build_chrome()
        self._build_content()
        self._build_status_bar()

        # An idle auto-lock wipes the key + closes the vault; route back to the
        # locked shell so the next action can't hit a closed connection (INV-4).
        service.on_auto_lock = self._lock

        if state == "first_run":
            self._show_first_run()
        else:
            self._show_unlock()

    # --- chrome ------------------------------------------------------------- #
    def _build_chrome(self) -> None:
        self._action_manual_entry = self._make_action(
            "action_manual_entry",
            self.tr("Manual entry"),
            "manual_entry",
            self._open_manual_entry,
        )
        self._action_import = self._make_action(
            "action_import", self.tr("Import statement"), "import", self._open_import
        )
        self._action_accounts = self._make_action(
            "action_accounts", self.tr("Accounts"), "accounts", self._open_accounts
        )
        self._action_categories = self._make_action(
            "action_categories",
            self.tr("Categories"),
            "categories",
            self._open_categories,
        )
        self._action_lock = self._make_action(
            "action_lock", self.tr("Lock"), "lock", self._lock
        )
        self._action_quit = self._make_action(
            "action_quit", self.tr("Quit"), None, QApplication.quit
        )
        self._action_home = self._make_action(
            "action_home", self.tr("Home"), None, self._show_home
        )
        self._action_about = self._make_action(
            "action_about", self.tr("About finbreak"), None, self._show_about
        )
        self._action_donate_github = self._make_action(
            "action_donate_github",
            self.tr("GitHub Sponsors"),
            None,
            lambda: self._open_url(DONATE_GITHUB),
        )
        self._action_donate_patreon = self._make_action(
            "action_donate_patreon",
            self.tr("Patreon"),
            None,
            lambda: self._open_url(DONATE_PATREON),
        )
        self._action_donate_paybru = self._make_action(
            "action_donate_paybru",
            self.tr("PayBru"),
            None,
            lambda: self._open_url(DONATE_PAYBRU),
        )

        menu = self.menuBar()
        self._menu_file = menu.addMenu(self.tr("File"))
        self._menu_file.addAction(self._action_manual_entry)
        self._menu_file.addAction(self._action_import)
        self._menu_file.addSeparator()
        self._menu_file.addAction(self._action_lock)
        self._menu_file.addAction(self._action_quit)

        self._menu_view = menu.addMenu(self.tr("View"))
        self._menu_view.addAction(self._action_home)
        self._menu_view.addAction(self._action_accounts)
        self._menu_view.addAction(self._action_categories)

        menu_help = menu.addMenu(self.tr("Help"))
        menu_help.addAction(self._action_about)

        menu_donate = menu.addMenu(self.tr("Donate"))
        menu_donate.addAction(self._action_donate_github)
        menu_donate.addAction(self._action_donate_patreon)
        menu_donate.addAction(self._action_donate_paybru)

        # An action on both the menu and the toolbar is a SINGLE QAction instance
        # added to both (one objectName, no duplicate key).
        self._toolbar = self.addToolBar(self.tr("Main"))
        self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for action in (
            self._action_manual_entry,
            self._action_import,
            self._action_accounts,
            self._action_categories,
            self._action_lock,
        ):
            self._toolbar.addAction(action)

    def _make_action(
        self,
        object_name: str,
        text: str,
        icon_name: str | None,
        handler: Callable[[], object],
    ) -> QAction:
        action = QAction(text, self)
        action.setObjectName(object_name)
        if icon_name is not None:
            action.setIcon(icon(icon_name))
        # triggered emits a `checked` bool; drop it — every handler is zero-arg.
        action.triggered.connect(lambda *_, h=handler: h())
        return action

    # --- content + status --------------------------------------------------- #
    def _build_content(self) -> None:
        self._content = QStackedWidget()
        self._placeholder_welcome = self._make_placeholder(
            "placeholder_welcome",
            self.tr("Welcome to finbreak — creating your vault…"),
            unlock_button=False,
        )
        self._placeholder_locked = self._make_placeholder(
            "placeholder_locked", self.tr("finbreak is locked."), unlock_button=True
        )
        self._content.addWidget(self._placeholder_welcome)
        self._content.addWidget(self._placeholder_locked)
        self.setCentralWidget(self._content)

    def _make_placeholder(
        self, object_name: str, text: str, *, unlock_button: bool
    ) -> QWidget:
        page = QWidget()
        page.setObjectName(object_name)
        layout = QVBoxLayout(page)
        layout.addStretch()
        layout.addWidget(QLabel(text))
        if unlock_button:
            button = QPushButton(self.tr("Unlock"))
            button.setObjectName("button_unlock")
            button.clicked.connect(lambda *_: self._show_unlock())
            layout.addWidget(button)
        layout.addStretch()
        return page

    def _build_status_bar(self) -> None:
        self._count = QLabel()
        self._count.setObjectName("status_txn_count")
        self._count.setVisible(False)  # transaction metadata — hidden until unlocked
        self.statusBar().addPermanentWidget(self._count)
        # A transient showMessage(text, timeout) clears to EMPTY when it expires,
        # not back to a resting message — so restore "Ready" whenever the message
        # area empties (INV-7 "auto-clearing back to a resting Ready").
        self.statusBar().messageChanged.connect(self._on_status_message_changed)
        self.statusBar().showMessage(self.tr("Ready"))

    def _on_status_message_changed(self, text: str) -> None:
        if not text:  # a transient message just expired — settle back to Ready
            self.statusBar().showMessage(self.tr("Ready"))

    def _status(self, text: str) -> None:
        # Callers pass an already-tr()-wrapped literal; do NOT re-wrap here —
        # self.tr(variable) can't be extracted by lupdate (D8/INV-10).
        self.statusBar().showMessage(text, _STATUS_TIMEOUT_MS)

    # --- state machine ------------------------------------------------------ #
    def _show_first_run(self) -> None:
        self._content.setCurrentWidget(self._placeholder_welcome)
        self._set_vault_chrome_enabled(False)
        dialog = FirstRunDialog(self._service, self)
        dialog.completed.connect(self._enter_unlocked)
        dialog.rejected.connect(self._on_first_run_rejected)
        self._open_dialog(dialog)

    def _show_unlock(self) -> None:
        # The locked shell — from a fresh startup, the Unlock button, or a lock.
        self._clear_live()
        self._content.setCurrentWidget(self._placeholder_locked)
        self._set_vault_chrome_enabled(False)
        self._count.setVisible(False)
        self._open_unlock_dialog()

    def _open_unlock_dialog(self) -> None:
        dialog = UnlockDialog(self._service, self)
        dialog.unlocked.connect(self._enter_unlocked)
        dialog.rejected.connect(self._teardown_dialog)  # cancel: stay locked
        self._open_dialog(dialog)

    def _enter_unlocked(self) -> None:
        self._teardown_dialog()
        self._set_vault_chrome_enabled(True)
        self._show_home()
        self._status(self.tr("Unlocked"))

    def _lock(self) -> None:
        # (1) close any open modal dialog so no post-lock write can fire (INV-4b).
        self._teardown_dialog()
        # (2) close the vault + wipe the key (idempotent after an auto-lock lock()).
        self._service.lock()
        # (3) destroy the current content widget; show the 🔒 Locked placeholder (D5).
        self._clear_live()
        self._content.setCurrentWidget(self._placeholder_locked)
        # (4) disable the vault-dependent chrome + hide the count (INV-7).
        self._set_vault_chrome_enabled(False)
        self._count.setVisible(False)
        self._status(self.tr("Vault locked"))
        # (5) re-open the UnlockDialog — window intact.
        self._open_unlock_dialog()

    def _show_home(self) -> None:
        home = HomeView(TransactionService(self._service.vault), self)
        home.add_account_requested.connect(self._action_accounts.trigger)
        home.import_requested.connect(self._action_import.trigger)
        home.add_transaction_requested.connect(self._action_manual_entry.trigger)
        self._set_live(home)
        self._refresh_count(home.transaction_count())

    def _refresh_count(self, count: int) -> None:
        self._count.setText(self.tr("%n transaction(s)", "", count))
        self._count.setVisible(True)

    def _on_first_run_rejected(self) -> None:
        self._teardown_dialog()
        QApplication.quit()  # no vault can be created — nothing to show

    # --- content actions ---------------------------------------------------- #
    def _open_manual_entry(self) -> None:
        dialog = ManualEntryDialog(self._service, self)
        dialog.committed.connect(self._on_manual_committed)
        dialog.rejected.connect(self._teardown_dialog)  # cancel: no navigation
        self._open_dialog(dialog, defer=False)

    def _on_manual_committed(self) -> None:
        self._teardown_dialog()
        self._status(self.tr("Added transaction"))
        self._show_home()  # a fresh Home, whatever page was current (INV-9)

    def _open_accounts(self) -> None:
        widget = AccountsWidget(self._service)
        widget.done.connect(self._show_home)
        self._set_live(widget)
        self._status(self.tr("Accounts"))

    def _open_categories(self) -> None:
        widget = CategoriesWidget(self._service)
        widget.done.connect(self._show_home)
        self._set_live(widget)
        self._status(self.tr("Categories"))

    def _open_import(self) -> None:
        widget = ImportWizardWidget(self._service)
        widget.done.connect(self._show_home)
        self._set_live(widget)
        self._status(self.tr("Importing statement…"))

    def _open_url(self, url: str) -> None:
        # Hands the funding page to the OS browser — a user-initiated egress, not
        # an app network call (the app opens no socket; INV-8).
        QDesktopServices.openUrl(QUrl(url))

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            self.tr("About finbreak"),
            self.tr("finbreak — a private, offline personal-finance vault."),
        )

    # --- content-stack + dialog helpers ------------------------------------- #
    def _set_live(self, widget: QWidget) -> None:
        # Exactly ONE content widget at a time: destroy the current one, then add
        # the new (the old AppShell._swap pattern) — no hidden HomeView survives.
        self._clear_live()
        self._content.addWidget(widget)
        self._live = widget
        self._content.setCurrentWidget(widget)

    def _clear_live(self) -> None:
        if self._live is not None:
            self._content.removeWidget(self._live)
            self._live.deleteLater()
            self._live = None

    def _open_dialog(self, dialog: QDialog, *, defer: bool = True) -> None:
        self._dialog = dialog
        dialog.setModal(True)
        if defer:
            # Show on the first event-loop turn — after run() paints the window —
            # so the dialog opens over an already-painted window, no blank flash.
            QTimer.singleShot(0, self, lambda: self._show_if_pending(dialog))
        else:
            dialog.show()

    def _show_if_pending(self, dialog: QDialog) -> None:
        if shiboken6.isValid(dialog) and self._dialog is dialog:
            dialog.show()

    def _teardown_dialog(self) -> None:
        dialog = self._dialog
        self._dialog = None
        if dialog is not None:
            dialog.hide()  # hide(), not close() — close() would re-emit rejected
            dialog.deleteLater()

    def _set_vault_chrome_enabled(self, enabled: bool) -> None:
        # Help + Donate need no vault and stay enabled; File/View + the toolbar are
        # vault-dependent (INV-2/INV-4).
        self._toolbar.setEnabled(enabled)
        self._menu_file.setEnabled(enabled)
        self._menu_view.setEnabled(enabled)
