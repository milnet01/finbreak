"""MainWindow — the QMainWindow app shell + its state machine (FIBR-0051 D1/D2,
reshaped into a tabbed workspace by FIBR-0052 D1).

The top-level window: a menubar (File · View · Window · Help · Donate), an icon
toolbar, a central ``QStackedWidget`` content area, and a status bar. First-run
and unlock are non-blocking application-modal dialogs shown *over* the window;
manual entry is a modal dialog. When unlocked, the content slot holds a single
**workspace** ``QTabWidget`` (Home · Statements · Accounts · Categories as
persistent tabs), built once per session and **destroyed on lock** so no
decrypted rows survive (INV-3). An import temporarily replaces the workspace with
the wizard (also destroyed on lock), rebuilding the workspace on ``done``. Window
size/position/state + the last-active tab are persisted to a plain INI **outside**
the vault (``paths.window_settings_path``, INV-5), restored before unlock. A
``Window`` menu (Center / Reset) needs no vault and stays enabled while locked.
"""

from __future__ import annotations

from collections.abc import Callable

import shiboken6
from PySide6.QtCore import QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from finbreak import paths
from finbreak.services.auth import AuthService
from finbreak.services.transactions import TransactionService
from finbreak.ui.accounts import AccountsWidget
from finbreak.ui.categories import CategoriesWidget
from finbreak.ui.first_run import FirstRunDialog
from finbreak.ui.home import HomeView
from finbreak.ui.icons import icon
from finbreak.ui.import_wizard import ImportWizardWidget
from finbreak.ui.manual_entry import ManualEntryDialog
from finbreak.ui.settings import SettingsDialog
from finbreak.ui.statements import StatementsWidget
from finbreak.ui.unlock import UnlockDialog

# The three .github/FUNDING.yml donate URLs (D6/INV-8). Kept in sync with that
# file by hand — the INV-8a test reads FUNDING.yml and fails on any drift.
DONATE_GITHUB = "https://github.com/sponsors/milnet01"
DONATE_PATREON = "https://www.patreon.com/AntsProjectsHub"
DONATE_PAYBRU = "https://paybru.co.za/tip/ants-projects-hub"

_STATUS_TIMEOUT_MS = 4000

# The workspace tab order (FIBR-0052 INV-1). Fixed; the navigation actions and the
# import-done landing key on these indices.
_TAB_HOME = 0
_TAB_STATEMENTS = 1
_TAB_ACCOUNTS = 2
_TAB_CATEGORIES = 3

# The fallback window size when no geometry is saved, and the size Reset restores
# to (INV-6/INV-6b) — the one numeric window default this shell pins.
_DEFAULT_WINDOW_SIZE = QSize(1000, 700)

# QSettings keys in the window INI (INV-5).
_KEY_GEOMETRY = "geometry"
_KEY_STATE = "window_state"
_KEY_LAST_TAB = "last_tab"


class MainWindow(QMainWindow):
    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._dialog: QDialog | None = None  # the current modal dialog, if any
        self._live: QWidget | None = None  # the current content widget, if any
        self._workspace: QTabWidget | None = None  # the tabbed workspace, when live
        self._home_tab: HomeView | None = None
        self._statements_tab: StatementsWidget | None = None
        self._accounts_tab: AccountsWidget | None = None
        self._categories_tab: CategoriesWidget | None = None
        self.setWindowTitle(self.tr("finbreak"))

        # Read routing FIRST — a mixed vault/sidecar pair raises VaultStateError
        # here and propagates to run()'s guard; the window is never shown (INV-2c).
        state = service.state()

        self._build_chrome()
        self._build_content()
        self._build_status_bar()

        # Geometry loads BEFORE any unlock — it must apply to the first-shown,
        # still-locked window (INV-5). The last-tab index is applied later, when
        # the workspace is built (it is meaningless while locked).
        self._initial_tab = self._restore_geometry()

        # An idle auto-lock wipes the key + closes the vault; route back to the
        # locked shell so the next action can't hit a closed connection (INV-4).
        service.on_auto_lock = self._lock

        if state == "first_run":
            self._show_first_run()
        else:
            self._show_unlock()

    # --- chrome ------------------------------------------------------------- #
    def _build_chrome(self) -> None:
        self._action_home = self._make_action(
            "action_home", self.tr("Home"), "home", self._show_home
        )
        self._action_statements = self._make_action(
            "action_statements", self.tr("Statements"), None, self._open_statements
        )
        self._action_manual_entry = self._make_action(
            "action_manual_entry",
            self.tr("Manual entry"),
            "manual_entry",
            self._open_manual_entry,
        )
        self._action_import = self._make_action(
            "action_import", self.tr("Import statement"), "import", self._open_import
        )
        self._action_settings = self._make_action(
            "action_settings", self.tr("Settings…"), None, self._open_settings
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
        self._action_center_window = self._make_action(
            "action_center_window", self.tr("Center window"), None, self._center_window
        )
        self._action_reset_layout = self._make_action(
            "action_reset_layout", self.tr("Reset layout"), None, self._reset_layout
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
        self._menu_file.addAction(self._action_settings)
        self._menu_file.addSeparator()
        self._menu_file.addAction(self._action_lock)
        self._menu_file.addAction(self._action_quit)

        self._menu_view = menu.addMenu(self.tr("View"))
        self._menu_view.addAction(self._action_home)
        self._menu_view.addAction(self._action_statements)
        self._menu_view.addAction(self._action_accounts)
        self._menu_view.addAction(self._action_categories)

        # Window: geometry actions that need no vault, so they stay enabled while
        # locked (INV-6/INV-6c) — never touched by _set_vault_chrome_enabled.
        self._menu_window = menu.addMenu(self.tr("Window"))
        self._menu_window.addAction(self._action_center_window)
        self._menu_window.addAction(self._action_reset_layout)

        menu_help = menu.addMenu(self.tr("Help"))
        menu_help.addAction(self._action_about)

        menu_donate = menu.addMenu(self.tr("Donate"))
        menu_donate.addAction(self._action_donate_github)
        menu_donate.addAction(self._action_donate_patreon)
        menu_donate.addAction(self._action_donate_paybru)

        # An action on both the menu and the toolbar is a SINGLE QAction instance
        # added to both (one objectName, no duplicate key). Home leads the toolbar.
        self._toolbar = self.addToolBar(self.tr("Main"))
        # objectName is required by saveState/restoreState (INV-5) — without it Qt
        # warns and cannot restore the toolbar's position.
        self._toolbar.setObjectName("main_toolbar")
        self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for action in (
            self._action_home,
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
        workspace = self._build_workspace()
        index = max(_TAB_HOME, min(self._initial_tab, workspace.count() - 1))
        workspace.setCurrentIndex(index)
        if self._home_tab is not None:
            self._refresh_count(self._home_tab.transaction_count())
        self._status(self.tr("Unlocked"))

    def _lock(self) -> None:
        # (1) close any open modal dialog so no post-lock write can fire (INV-4b).
        self._teardown_dialog()
        # (2) close the vault + wipe the key (idempotent after an auto-lock lock()).
        self._service.lock()
        # (3) destroy the workspace (or the import wizard); show 🔒 Locked (INV-3).
        self._clear_live()
        self._content.setCurrentWidget(self._placeholder_locked)
        # (4) disable the vault-dependent chrome + hide the count (INV-7).
        self._set_vault_chrome_enabled(False)
        self._count.setVisible(False)
        self._status(self.tr("Vault locked"))
        # (5) re-open the UnlockDialog — window intact.
        self._open_unlock_dialog()

    # --- workspace ---------------------------------------------------------- #
    def _build_workspace(self) -> QTabWidget:
        """Build the four-tab workspace once and install it as the live content,
        returning it. Each tab page self-refreshes on construction; navigation
        switches the current index (D1), never rebuilds a tab."""
        workspace = QTabWidget()
        workspace.setObjectName("workspace")

        self._home_tab = HomeView(TransactionService(self._service.vault))
        self._home_tab.setObjectName("tab_home")
        self._home_tab.add_account_requested.connect(self._action_accounts.trigger)
        self._home_tab.import_requested.connect(self._action_import.trigger)
        self._home_tab.add_transaction_requested.connect(
            self._action_manual_entry.trigger
        )

        self._statements_tab = StatementsWidget(self._service)  # sets tab_statements
        self._statements_tab.changed.connect(self._on_statement_changed)

        self._accounts_tab = AccountsWidget(self._service, show_done=False)
        self._accounts_tab.setObjectName("tab_accounts")

        self._categories_tab = CategoriesWidget(self._service, show_done=False)
        self._categories_tab.setObjectName("tab_categories")

        workspace.addTab(self._home_tab, self.tr("Home"))
        workspace.addTab(self._statements_tab, self.tr("Statements"))
        workspace.addTab(self._accounts_tab, self.tr("Accounts"))
        workspace.addTab(self._categories_tab, self.tr("Categories"))

        # Connect AFTER the tabs are added, so building fires no spurious refresh.
        workspace.currentChanged.connect(self._on_tab_changed)
        self._workspace = workspace
        self._set_live(workspace)
        return workspace

    def _ensure_workspace(self) -> QTabWidget:
        """The live workspace, rebuilt if it is absent (e.g. after an import
        replaced it with the wizard)."""
        if (
            self._workspace is not None
            and shiboken6.isValid(self._workspace)
            and self._live is self._workspace
        ):
            return self._workspace
        return self._build_workspace()

    def _on_tab_changed(self, index: int) -> None:
        self._save_geometry()  # persist the last tab so it survives a crash (D7)
        self._refresh_tab(index)

    def _refresh_tab(self, index: int) -> None:
        # The activated tab re-reads the vault (D4), so a change made elsewhere is
        # reflected when its tab is next shown — no need to wire every mutation.
        if index == _TAB_HOME and self._home_tab is not None:
            self._home_tab.refresh()
            self._refresh_count(self._home_tab.transaction_count())
        elif index == _TAB_STATEMENTS and self._statements_tab is not None:
            self._statements_tab.refresh()
        elif index == _TAB_ACCOUNTS and self._accounts_tab is not None:
            self._accounts_tab._refresh()
        elif index == _TAB_CATEGORIES and self._categories_tab is not None:
            self._categories_tab._refresh()

    def _refresh_count(self, count: int) -> None:
        self._count.setText(self.tr("%n transaction(s)", "", count))
        self._count.setVisible(True)

    def _on_first_run_rejected(self) -> None:
        self._teardown_dialog()
        QApplication.quit()  # no vault can be created — nothing to show

    # --- content actions ---------------------------------------------------- #
    def _show_home(self) -> None:
        workspace = self._ensure_workspace()
        if self._home_tab is not None:
            self._home_tab.refresh()
            self._refresh_count(self._home_tab.transaction_count())
        workspace.setCurrentIndex(_TAB_HOME)

    def _open_statements(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_STATEMENTS)
        self._status(self.tr("Statements"))

    def _open_accounts(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_ACCOUNTS)
        self._status(self.tr("Accounts"))

    def _open_categories(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_CATEGORIES)
        self._status(self.tr("Categories"))

    def _open_manual_entry(self) -> None:
        dialog = ManualEntryDialog(self._service, self)
        dialog.committed.connect(self._on_manual_committed)
        dialog.rejected.connect(self._teardown_dialog)  # cancel: no navigation
        self._open_dialog(dialog, defer=False)

    def _on_manual_committed(self) -> None:
        self._teardown_dialog()
        self._status(self.tr("Added transaction"))
        self._show_home()  # refresh + show the Home tab, whatever was current (INV-9)

    def _open_settings(self) -> None:
        # Vault-dependent (File menu is disabled while locked, INV-6). The shell
        # reads the currency and hands it to the dialog, which holds no vault ref.
        currency = TransactionService(self._service.vault).base_currency()
        dialog = SettingsDialog(self._service, currency, self)
        dialog.saved.connect(self._on_settings_saved)
        dialog.rejected.connect(self._teardown_dialog)  # cancel: no change
        self._open_dialog(dialog, defer=False)

    def _on_settings_saved(self) -> None:
        self._teardown_dialog()
        self._status(self.tr("Settings saved"))

    def _open_import(self) -> None:
        # Import wants the full content area — it REPLACES the workspace (via
        # _set_live, destroying it: fewer decrypted rows alive, INV-3) and rebuilds
        # it on done (D5). A lock while importing destroys the wizard (it is live).
        widget = ImportWizardWidget(self._service)
        widget.done.connect(self._on_import_done)
        self._set_live(widget)
        self._status(self.tr("Importing statement…"))

    def _on_import_done(self) -> None:
        # Rebuild a fresh workspace and land on Statements so the just-imported
        # statement is visible; refresh Home + the count (D5/INV-11).
        workspace = self._build_workspace()
        workspace.setCurrentIndex(_TAB_STATEMENTS)
        if self._home_tab is not None:
            self._home_tab.refresh()
            self._refresh_count(self._home_tab.transaction_count())

    def _on_statement_changed(self) -> None:
        # A statement delete changed the transaction set — refresh Home + the count
        # even though the Statements tab is current (INV-10/INV-11).
        if self._home_tab is not None:
            self._home_tab.refresh()
            self._refresh_count(self._home_tab.transaction_count())
        self._status(self.tr("Statement deleted"))

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

    # --- window geometry (INV-5/INV-6) -------------------------------------- #
    def _settings(self) -> QSettings:
        return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)

    def _restore_geometry(self) -> int:
        """Apply saved size/position/state; return the saved last-tab index (0 when
        none). Called in __init__, before the window is shown (INV-5)."""
        settings = self._settings()
        geometry = settings.value(_KEY_GEOMETRY)
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(_DEFAULT_WINDOW_SIZE)
        window_state = settings.value(_KEY_STATE)
        if window_state is not None:
            self.restoreState(window_state)
        raw_tab = settings.value(_KEY_LAST_TAB)
        return int(raw_tab) if raw_tab is not None else _TAB_HOME

    def _save_geometry(self) -> None:
        settings = self._settings()
        settings.setValue(_KEY_GEOMETRY, self.saveGeometry())
        settings.setValue(_KEY_STATE, self.saveState())
        if self._workspace is not None and shiboken6.isValid(self._workspace):
            settings.setValue(_KEY_LAST_TAB, self._workspace.currentIndex())
        settings.sync()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()  # persist size/position/state/tab on quit (D7)
        super().closeEvent(event)

    def _center_window(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _reset_layout(self) -> None:
        settings = self._settings()
        settings.remove(_KEY_GEOMETRY)
        settings.remove(_KEY_STATE)
        settings.sync()
        self.resize(_DEFAULT_WINDOW_SIZE)
        self._center_window()

    # --- content-stack + dialog helpers ------------------------------------- #
    def _set_live(self, widget: QWidget) -> None:
        # Exactly ONE content widget at a time: destroy the current one, then add
        # the new (the old destroy-on-swap pattern) — no hidden data widget survives.
        self._clear_live()
        self._content.addWidget(widget)
        self._live = widget
        self._content.setCurrentWidget(widget)

    def _clear_live(self) -> None:
        if self._live is not None:
            # If the live content is the workspace, drop the tab references too so
            # a rebuild is forced and no stale (deleted) tab is touched.
            if self._live is self._workspace:
                self._workspace = None
                self._home_tab = None
                self._statements_tab = None
                self._accounts_tab = None
                self._categories_tab = None
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
        # Window + Help + Donate need no vault and stay enabled; File/View + the
        # toolbar are vault-dependent (INV-2/INV-4/INV-6c).
        self._toolbar.setEnabled(enabled)
        self._menu_file.setEnabled(enabled)
        self._menu_view.setEnabled(enabled)
