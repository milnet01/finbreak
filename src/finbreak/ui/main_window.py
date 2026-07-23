"""MainWindow — the QMainWindow app shell + its state machine (FIBR-0051 D1/D2,
reshaped into a tabbed workspace by FIBR-0052 D1).

The top-level window: a menubar (File · View · Window · Help · Donate), an icon
toolbar, a central ``QStackedWidget`` content area, and a status bar. First-run
and unlock are non-blocking application-modal dialogs shown *over* the window;
manual entry is a modal dialog. When unlocked, the content slot holds a single
**workspace** ``QTabWidget`` (Home · Transactions · Statements · Accounts ·
Categories · Rules · Transfers as persistent tabs), built once per session and
**destroyed on lock** so no
decrypted rows survive (INV-3). An import temporarily replaces the workspace with
the wizard (also destroyed on lock), rebuilding the workspace on ``done``. Window
size/position/state + the last-active tab are persisted to a plain INI **outside**
the vault (``paths.window_settings_path``, INV-5), restored before unlock. On
Wayland the compositor owns placement, so only the size is restored (via a
resize the compositor honours) and Center window is driven through KWin's D-Bus
API on KDE (disabled on other Wayland compositors, which expose no placement
API); everything works fully on X11 / Windows / macOS (FIBR-0060). A ``Window``
menu (Center / Reset) needs no vault and stays enabled while locked.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

import pikepdf
import shiboken6
from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlcipher3.dbapi2 import DatabaseError

from finbreak import __version__, paths
from finbreak.errors import BackupError, VaultLockedError, VaultStateError
from finbreak.services.accounts import AccountService
from finbreak.services.auth import (
    DATETIME_SYSTEM,
    AmountPrefs,
    AuthService,
    DateTimePrefs,
)
from finbreak.services.backup import BackupService
from finbreak.services.categorization import CategorizationService
from finbreak.services.password_hint import HintPolicyError, validate_hint
from finbreak.services.pdf_export import PdfExportService, period_filename_slug
from finbreak.services.recurring import RecurringService
from finbreak.services.reporting import ReportingService
from finbreak.services.transactions import TransactionService
from finbreak.services.update import UpdateInfo, UpdateService
from finbreak.services.update_installer import Installer, detect_installer
from finbreak.ui._clipboard import ClipboardAutoClear
from finbreak.ui._password_hint import clear_hint, read_hint, write_hint
from finbreak.ui._unlock_throttle import UnlockThrottle
from finbreak.ui._update_worker import DownloadWorker, UpdateCheckWorker
from finbreak.ui.accounts import AccountsWidget
from finbreak.ui.backup_export import BackupExportDialog
from finbreak.ui.backup_restore import BackupRestoreDialog
from finbreak.ui.backup_verify import BackupVerifyDialog
from finbreak.ui.categories import CategoriesWidget
from finbreak.ui.export_dialog import ExportDialog
from finbreak.ui.first_run import FirstRunDialog
from finbreak.ui.home import HomeView
from finbreak.ui.icons import toolbar_icon
from finbreak.ui.import_wizard import ImportWizardWidget
from finbreak.ui.manual_entry import ManualEntryDialog
from finbreak.ui.recurring import RecurringWidget
from finbreak.ui.rules import RulesWidget
from finbreak.ui.set_hint import SetHintDialog
from finbreak.ui.settings import SettingsDialog
from finbreak.ui.start_over import StartOverDialog
from finbreak.ui.statements import StatementsWidget
from finbreak.ui.theme import ThemeController, polish_item_views
from finbreak.ui.transactions import TransactionsView
from finbreak.ui.transfers import TransfersWidget
from finbreak.ui.unlock import UnlockDialog
from finbreak.ui.update_dialog import UpdateDialog

# The three .github/FUNDING.yml donate URLs (D6/INV-8). Kept in sync with that
# file by hand — the INV-8a test reads FUNDING.yml and fails on any drift.
DONATE_GITHUB = "https://github.com/sponsors/milnet01"
DONATE_PATREON = "https://www.patreon.com/AntsProjectsHub"
DONATE_PAYBRU = "https://paybru.co.za/tip/ants-projects-hub"

# Report an Issue opens the public repo's new-issue form in the OS browser
# (FIBR-0156). Like Donate, this is a user-initiated egress via _open_url, not an
# app network call (security-model INV-8) — no vault data leaves the machine.
REPORT_ISSUE_URL = "https://github.com/milnet01/finbreak/issues/new"

_STATUS_TIMEOUT_MS = 4000

# The workspace tab order (FIBR-0052 INV-1; Transactions inserted 2nd by FIBR-0012).
# Fixed; the navigation actions and the import-done landing key on these indices.
_TAB_HOME = 0
_TAB_TRANSACTIONS = 1
_TAB_STATEMENTS = 2
_TAB_ACCOUNTS = 3
_TAB_CATEGORIES = 4
_TAB_RULES = 5
_TAB_TRANSFERS = 6
_TAB_RECURRING = 7

# User-input event types that count as activity for the idle-lock reset (FIBR-0114).
_ACTIVITY_EVENTS = frozenset(
    {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseMove,
        QEvent.Type.KeyPress,
        QEvent.Type.Wheel,
    }
)

# The fallback window size when no geometry is saved, and the size Reset restores
# to (INV-6/INV-6b) — the one numeric window default this shell pins.
_DEFAULT_WINDOW_SIZE = QSize(1000, 700)

# QSettings keys in the window INI (INV-5).
_KEY_GEOMETRY = "geometry"
_KEY_STATE = "window_state"
_KEY_SIZE = "window_size"  # size alone, for the Wayland resize-only path (FIBR-0060)
_KEY_LAST_TAB = "last_tab"


def _is_wayland() -> bool:
    """True when running under a Wayland compositor (FIBR-0060). Wayland owns
    window placement: an app cannot set or restore its own POSITION — ``move()``
    and ``restoreGeometry``'s position are no-ops — and a size restored via
    ``restoreGeometry`` before the first map is unreliable. So on Wayland we
    restore only the size (via ``resize()``, which the compositor honours) and
    centre via the compositor's own API. A module function so tests can
    monkeypatch it to exercise both platform branches."""
    return QGuiApplication.platformName().startswith("wayland")


def _in_flatpak() -> bool:
    """True when running inside a Flatpak sandbox. Flatpak drops a
    ``/.flatpak-info`` marker into every sandbox, so its presence is the canonical
    probe — a sibling monkeypatchable seam to ``_is_wayland`` (FIBR-0159 INV-8).
    The sandbox's session-bus proxy auto-allows only ``org.freedesktop.portal.*``;
    the KWin window-centering call (``org.kde.KWin``, FIBR-0060) is not reachable,
    and finbreak's finance-app sandbox deliberately does not widen the D-Bus
    surface to reach it (FIBR-0159 § 3.5 / INV-2)."""
    return os.path.exists("/.flatpak-info")


def _kde_wayland() -> bool:
    """True on a KDE Plasma Wayland session — the one Wayland compositor finbreak
    can centre a window on, via KWin's scripting D-Bus API (FIBR-0060). Other
    Wayland compositors expose no app-usable placement API, so Center window is
    disabled there rather than silently doing nothing. Under Flatpak the
    ``org.kde.KWin`` name is outside the sandbox's portal-only bus proxy
    (FIBR-0159 § 3.5), so this returns False there too — the single chokepoint that
    both ``_center_supported()`` (the menu gate) and ``_center_window()`` (the
    Reset-Layout path) consult, disabling the unreachable call at one seam."""
    if _in_flatpak():
        return False
    return _is_wayland() and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def _center_supported() -> bool:
    """Whether Center window can actually place the window: always on X11 /
    Windows / macOS (``move()`` works), and on KDE Wayland (via KWin)."""
    return (not _is_wayland()) or _kde_wayland()


# A KWin script that centres *our* window — matched by PID — in its work area.
# The one way to position a window on Wayland, where the compositor owns placement
# (FIBR-0060; technique from the SystemManager project). Verified on Plasma 6; the
# windowList/clientList branch also handles Plasma 5's enumeration. Best-effort, so
# an API mismatch on an older KWin simply leaves the window where it is.
_KWIN_CENTER_JS = """\
var wins = workspace.windowList ? workspace.windowList() : workspace.clientList();
for (var i = 0; i < wins.length; i++) {
    var c = wins[i];
    if (c.pid === __PID__) {
        var area = workspace.clientArea(workspace.PlacementArea, c);
        c.frameGeometry = {
            x: area.x + Math.round((area.width - c.frameGeometry.width) / 2),
            y: area.y + Math.round((area.height - c.frameGeometry.height) / 2),
            width: c.frameGeometry.width,
            height: c.frameGeometry.height
        };
        break;
    }
}
"""


class MainWindow(QMainWindow):
    def __init__(
        self,
        service: AuthService,
        parent: QWidget | None = None,
        *,
        update_service: UpdateService | None = None,
        installer: Installer | None = None,
        theme_controller: ThemeController | None = None,
    ):
        super().__init__(parent)
        self._service = service
        # The app-wide theme controller (FIBR-0127 D10). Optional: with None the
        # shell shows no theme picker, wires no re-tint, and skips polish_item_views,
        # so every existing MainWindow(service) construction is untouched.
        self._theme = theme_controller
        # name -> icon-bearing action, populated by _make_action, iterated by
        # _retint_toolbar_icons on a theme change (INV-10). Initialised BEFORE
        # _build_chrome (which populates it).
        self._icon_actions: dict[str, QAction] = {}
        # The opt-in updater (FIBR-0054). Resolve the installer ONCE and hand the
        # same instance to the service + use it for apply (D6/Deliverable 9). Tests
        # inject a fake service + installer; production builds the real pair.
        if update_service is None:
            installer = detect_installer()
            update_service = UpdateService(paths.window_settings_path(), installer)
        self._installer = installer
        self._update_service = update_service
        self._pending_update: UpdateInfo | None = None  # a found offer, held (D15)
        self._offered_update: UpdateInfo | None = None  # the one currently prompted
        self._unlocked = False  # gates the pending offer (D15)
        self._update_check_worker: UpdateCheckWorker | None = None
        self._manual_check_worker: UpdateCheckWorker | None = None  # Help→Check
        self._download_worker: DownloadWorker | None = None
        self._dialog: QDialog | None = None  # the current modal dialog, if any
        self._live: QWidget | None = None  # the current content widget, if any
        self._workspace: QTabWidget | None = None  # the tabbed workspace, when live
        self._home_tab: HomeView | None = None
        self._transactions_tab: TransactionsView | None = None
        self._statements_tab: StatementsWidget | None = None
        self._accounts_tab: AccountsWidget | None = None
        self._categories_tab: CategoriesWidget | None = None
        self._rules_tab: RulesWidget | None = None
        self._transfers_tab: TransfersWidget | None = None
        self._recurring_tab: RecurringWidget | None = None
        # The display prefs, read once post-unlock (the vault is locked here) and
        # passed to the display tabs (FIBR-0083 D7). All-"system" until then.
        self._prefs = DateTimePrefs(DATETIME_SYSTEM, DATETIME_SYSTEM, DATETIME_SYSTEM)
        # The amount-display prefs, likewise read once post-unlock (FIBR-0105).
        # The friendly default (minus + colour on) applies until then.
        self._amount_prefs = AmountPrefs("minus", True)
        self.setWindowTitle(self.tr("finbreak"))

        # Recover from a restore interrupted mid-install BEFORE routing: a crash
        # between the two install renames leaves a mixed live pair while the
        # original sits in *.old copies — recover it so the app never dead-ends on
        # the mixed-state error (FIBR-0014 D4/INV-5).
        self._reconcile_interrupted_restore()

        # Read routing FIRST — a mixed vault/sidecar pair raises VaultStateError
        # here and propagates to run()'s guard; the window is never shown (INV-2c).
        state = service.state()

        self._build_chrome()
        # Re-tint the toolbar glyphs on every theme change (delivers FIBR-0116's live
        # re-tint, INV-10). Connected AFTER _build_chrome so _icon_actions is
        # populated; only when a controller is present (D10).
        if self._theme is not None:
            self._theme.themeChanged.connect(self._retint_toolbar_icons)
        self._build_content()
        self._build_status_bar()

        # Geometry loads BEFORE any unlock — it must apply to the first-shown,
        # still-locked window (INV-5). The last-tab index is applied later, when
        # the workspace is built (it is meaningless while locked).
        self._initial_tab = self._restore_geometry()

        # An idle auto-lock wipes the key + closes the vault; route back to the
        # locked shell so the next action can't hit a closed connection (INV-4).
        service.on_auto_lock = self._lock

        # Treat user input anywhere in the app as activity that resets the idle-lock
        # countdown, so the timeout is measured from the last interaction rather than
        # from unlock (FIBR-0114). notify_activity() no-ops while locked.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        if state == "first_run":
            self._show_first_run()
        else:
            self._show_unlock()

        # Arm the opt-in update check once the event loop is up (the window is
        # shown, still locked). Gated inside on support + the opt-in flag (D7).
        QTimer.singleShot(0, self, self._maybe_check_for_update)

    # --- chrome ------------------------------------------------------------- #
    def _build_chrome(self) -> None:
        self._action_home = self._make_action(
            "action_home", self.tr("Home"), "home", self._show_home
        )
        self._action_transactions = self._make_action(
            "action_transactions",
            self.tr("Transactions"),
            "transactions",
            self._open_transactions,
        )
        self._action_statements = self._make_action(
            "action_statements",
            self.tr("Statements"),
            "statements",
            self._open_statements,
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
        self._action_export = self._make_action(
            "action_export",
            self.tr("Export report as PDF…"),
            "export",
            self._open_export,
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
        self._action_rules = self._make_action(
            "action_rules", self.tr("Rules"), "rules", self._open_rules
        )
        self._action_transfers = self._make_action(
            "action_transfers", self.tr("Transfers"), "transfers", self._open_transfers
        )
        self._action_recurring = self._make_action(
            "action_recurring", self.tr("Recurring"), "recurring", self._open_recurring
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
        if not _center_supported():
            # A Wayland compositor with no app-usable placement API (i.e. not KDE):
            # grey the action out with an explaining tooltip rather than offer a
            # button that silently does nothing (FIBR-0060).
            self._action_center_window.setEnabled(False)
            self._action_center_window.setToolTip(
                self.tr("Your desktop positions windows automatically here.")
            )
        self._action_reset_layout = self._make_action(
            "action_reset_layout", self.tr("Reset layout"), None, self._reset_layout
        )
        self._action_check_updates = self._make_action(
            "action_check_updates",
            self.tr("Check for updates…"),
            None,
            self._check_for_updates_now,
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
        self._action_report_issue = self._make_action(
            "action_report_issue",
            self.tr("Report an Issue"),
            None,
            lambda: self._open_url(REPORT_ISSUE_URL),
        )

        menu = self.menuBar()
        self._menu_file = menu.addMenu(self.tr("File"))
        self._menu_file.addAction(self._action_manual_entry)
        self._menu_file.addAction(self._action_import)
        self._menu_file.addAction(self._action_settings)
        self._menu_file.addAction(self._action_export)  # FIBR-0013, after Settings…
        self._menu_file.addSeparator()
        self._menu_file.addAction(self._action_lock)
        self._menu_file.addAction(self._action_quit)

        self._menu_view = menu.addMenu(self.tr("View"))
        self._menu_view.addAction(self._action_home)
        self._menu_view.addAction(self._action_transactions)
        self._menu_view.addAction(self._action_statements)
        self._menu_view.addAction(self._action_accounts)
        self._menu_view.addAction(self._action_categories)
        self._menu_view.addAction(self._action_rules)
        self._menu_view.addAction(self._action_transfers)
        self._menu_view.addAction(self._action_recurring)

        # Window: geometry actions that need no vault, so they stay enabled while
        # locked (INV-6/INV-6c) — never touched by _set_vault_chrome_enabled.
        self._menu_window = menu.addMenu(self.tr("Window"))
        # Show the disabled-Center tooltip on Wayland (FIBR-0060).
        self._menu_window.setToolTipsVisible(True)
        self._menu_window.addAction(self._action_center_window)
        self._menu_window.addAction(self._action_reset_layout)

        menu_help = menu.addMenu(self.tr("Help"))
        menu_help.addAction(self._action_check_updates)
        menu_help.addSeparator()
        menu_help.addAction(self._action_about)

        menu_donate = menu.addMenu(self.tr("Donate"))
        menu_donate.addAction(self._action_donate_github)
        menu_donate.addAction(self._action_donate_patreon)
        menu_donate.addAction(self._action_donate_paybru)

        # A single top-level clickable item to the right of Donate (FIBR-0156) —
        # one click opens the issue form, no submenu.
        menu.addAction(self._action_report_issue)

        # An action on both the menu and the toolbar is a SINGLE QAction instance
        # added to both (one objectName, no duplicate key). Home leads the toolbar.
        self._toolbar = self.addToolBar(self.tr("Main"))
        # objectName is required by saveState/restoreState (INV-5) — without it Qt
        # warns and cannot restore the toolbar's position.
        self._toolbar.setObjectName("main_toolbar")
        self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for action in (
            self._action_home,
            self._action_transactions,
            self._action_statements,  # FIBR-0136 — matches the workspace tab order
            self._action_manual_entry,
            self._action_import,
            self._action_accounts,
            self._action_categories,
            self._action_rules,
            self._action_transfers,
            self._action_recurring,
            self._action_export,  # FIBR-0013, before Lock (Lock stays last)
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
            # Coloured, hover-brightening, theme-aware glyph on the toolbar + menus
            # (FIBR-0116): muted at rest, vibrant under the cursor.
            action.setIcon(toolbar_icon(icon_name))
            # Record it so a theme change can re-tint the glyph (INV-10). Only
            # icon-bearing actions — action_settings etc. (icon_name None) are skipped.
            self._icon_actions[icon_name] = action
        # triggered emits a `checked` bool; drop it — every handler is zero-arg.
        action.triggered.connect(lambda *_, h=handler: h())
        return action

    def _retint_toolbar_icons(self) -> None:
        """Re-render each icon-bearing action's glyph for the now-current theme
        (INV-10). ``toolbar_icon`` re-reads the live palette's light/dark, so the
        glyphs never show stale-theme tones after a live theme switch."""
        for name, action in self._icon_actions.items():
            action.setIcon(toolbar_icon(name))

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
        dialog.restore_requested.connect(self._open_restore)
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
        dialog.restore_requested.connect(self._open_restore)
        dialog.start_over_requested.connect(self._on_start_over)
        dialog.rejected.connect(self._teardown_dialog)  # cancel: stay locked
        self._open_dialog(dialog)

    def _enter_unlocked(self) -> None:
        self._unlocked = True  # set BEFORE the pending-offer call at the end (D15)
        self._teardown_dialog()
        self._set_vault_chrome_enabled(True)
        workspace = self._build_workspace()
        index = max(_TAB_HOME, min(self._initial_tab, workspace.count() - 1))
        workspace.setCurrentIndex(index)
        if self._home_tab is not None:
            self._refresh_count(self._home_tab.transaction_count())
        self._status(self.tr("Unlocked"))
        # Show a held update offer now that we're unlocked + idle — after the
        # teardown + workspace build, so it never tears down the prompt it opens.
        self._maybe_show_pending_offer()

    def _lock(self) -> None:
        self._unlocked = False  # a held offer must wait for the next unlock (D15)
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

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Application-wide input events reset the idle-lock countdown (FIBR-0114); the
        # service call no-ops while locked. Never consume the event — always defer to
        # the base filter so normal delivery is unaffected.
        if event.type() in _ACTIVITY_EVENTS:
            self._service.notify_activity()
        return super().eventFilter(obj, event)

    # --- workspace ---------------------------------------------------------- #
    def _build_workspace(self) -> QTabWidget:
        """Build the seven-tab workspace once and install it as the live content,
        returning it. Each tab page self-refreshes on construction; navigation
        switches the current index (D1), never rebuilds a tab."""
        workspace = QTabWidget()
        workspace.setObjectName("workspace")

        # Read the stored display prefs once, before building the tabs (D7). The
        # "system" sentinels are kept verbatim (expanded only at display time).
        self._prefs = self._service.datetime_prefs()
        self._amount_prefs = self._service.amount_prefs()

        # Home is now the dashboard (FIBR-0012 D6): reporting aggregates, the account
        # list, and the AuthService (for the persisted report-period prefs).
        # amount_prefs passes by keyword: FIBR-0143 inserts the required `recurring`
        # arg before it, so a positional pass would silently bind to `recurring`.
        self._home_tab = HomeView(
            ReportingService(self._service.vault),
            AccountService(self._service.vault),
            self._service,
            RecurringService(self._service.vault),
            amount_prefs=self._amount_prefs,
        )
        self._home_tab.setObjectName("tab_home")
        self._home_tab.add_account_requested.connect(self._action_accounts.trigger)
        self._home_tab.import_requested.connect(self._action_import.trigger)
        self._home_tab.add_transaction_requested.connect(
            self._action_manual_entry.trigger
        )

        # The relocated transaction table + filters (FIBR-0012 D7); sets
        # tab_transactions.
        self._transactions_tab = TransactionsView(
            TransactionService(self._service.vault),
            CategorizationService(self._service.vault),
            self._prefs,
            self._amount_prefs,
            clipboard=ClipboardAutoClear(
                QGuiApplication.clipboard(),
                seconds_provider=self._service.clipboard_clear_seconds,
            ),
        )

        self._statements_tab = StatementsWidget(
            self._service, self._prefs
        )  # sets tab_statements
        self._statements_tab.changed.connect(self._on_statement_changed)
        self._statements_tab.reassigned.connect(self._on_statement_reassigned)

        self._accounts_tab = AccountsWidget(self._service, show_done=False)
        self._accounts_tab.setObjectName("tab_accounts")

        self._categories_tab = CategoriesWidget(self._service, show_done=False)
        self._categories_tab.setObjectName("tab_categories")

        self._rules_tab = RulesWidget(self._service)  # sets tab_rules

        self._transfers_tab = TransfersWidget(self._service)  # sets tab_transfers

        self._recurring_tab = RecurringWidget(self._service)  # sets tab_recurring

        workspace.addTab(self._home_tab, self.tr("Home"))
        workspace.addTab(self._transactions_tab, self.tr("Transactions"))
        workspace.addTab(self._statements_tab, self.tr("Statements"))
        workspace.addTab(self._accounts_tab, self.tr("Accounts"))
        workspace.addTab(self._categories_tab, self.tr("Categories"))
        workspace.addTab(self._rules_tab, self.tr("Rules"))
        workspace.addTab(self._transfers_tab, self.tr("Transfers"))
        workspace.addTab(self._recurring_tab, self.tr("Recurring"))

        # Connect AFTER the tabs are added, so building fires no spurious refresh.
        workspace.currentChanged.connect(self._on_tab_changed)
        self._workspace = workspace
        # Enable alternating row stripes on every grid view so the theme's
        # alternate-background-color renders (INV-11) — only when themed (D10), so
        # the controller-less default path leaves alternatingRowColors untouched.
        if self._theme is not None:
            polish_item_views(workspace)
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
        elif index == _TAB_TRANSACTIONS and self._transactions_tab is not None:
            self._transactions_tab.refresh()
        elif index == _TAB_STATEMENTS and self._statements_tab is not None:
            self._statements_tab.refresh()
        elif index == _TAB_ACCOUNTS and self._accounts_tab is not None:
            self._accounts_tab._refresh()
        elif index == _TAB_CATEGORIES and self._categories_tab is not None:
            self._categories_tab._refresh()
        elif index == _TAB_RULES and self._rules_tab is not None:
            self._rules_tab._refresh()
        elif index == _TAB_TRANSFERS and self._transfers_tab is not None:
            self._transfers_tab._refresh()
        elif index == _TAB_RECURRING and self._recurring_tab is not None:
            self._recurring_tab.refresh()

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

    def _open_transactions(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_TRANSACTIONS)
        self._status(self.tr("Transactions"))

    def _open_statements(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_STATEMENTS)
        self._status(self.tr("Statements"))

    def _open_accounts(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_ACCOUNTS)
        self._status(self.tr("Accounts"))

    def _open_categories(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_CATEGORIES)
        self._status(self.tr("Categories"))

    def _open_rules(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_RULES)
        self._status(self.tr("Rules"))

    def _open_transfers(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_TRANSFERS)
        self._status(self.tr("Transfers"))

    def _open_recurring(self) -> None:
        self._ensure_workspace().setCurrentIndex(_TAB_RECURRING)
        self._status(self.tr("Recurring"))

    def _open_manual_entry(self) -> None:
        dialog = ManualEntryDialog(self._service, self)
        dialog.committed.connect(self._on_manual_committed)
        dialog.rejected.connect(self._teardown_dialog)  # cancel: no navigation
        self._open_dialog(dialog, defer=False)

    def _on_manual_committed(self) -> None:
        # Land on Transactions so the just-added row is visible (FIBR-0012 D11), and
        # refresh the live count from Home's ReportingService (decoupled from tab
        # nav, so an add from any tab keeps the status bar current, INV-14).
        self._teardown_dialog()
        self._status(self.tr("Added transaction"))
        workspace = self._ensure_workspace()
        if self._transactions_tab is not None:
            self._transactions_tab.refresh()
        if self._home_tab is not None:
            self._refresh_count(self._home_tab.transaction_count())
        workspace.setCurrentIndex(_TAB_TRANSACTIONS)

    def _open_settings(self) -> None:
        # Vault-dependent (File menu is disabled while locked, INV-6). The shell
        # reads the currency and hands it to the dialog, which holds no vault ref.
        currency = TransactionService(self._service.vault).base_currency()
        dialog = SettingsDialog(
            self._service,
            currency,
            self,
            update_enabled=self._update_service.is_enabled(),
            update_supported=self._installer is not None,
            library_enabled=CategorizationService(
                self._service.vault
            ).library_enabled(),
            theme_controller=self._theme,
        )
        dialog.saved.connect(self._on_settings_saved)
        dialog.export_backup_requested.connect(self._open_backup_export)
        dialog.verify_backup_requested.connect(self._open_backup_verify)
        dialog.set_hint_requested.connect(self._open_set_hint)
        dialog.rejected.connect(self._teardown_dialog)  # cancel: no change
        self._open_dialog(dialog, defer=False)

    def _open_export(self) -> None:
        # Vault-dependent (File menu disabled while locked, INV-11). The dialog
        # holds no vault ref — it is handed the account list + Home's pre-fill.
        if self._home_tab is None:  # only reachable unlocked, but keep it total
            return
        accounts = AccountService(self._service.vault).list_accounts()
        dialog = ExportDialog(
            accounts,
            self._home_tab.current_prefs(),
            self._home_tab.selected_account_id(),
            self,
        )
        dialog.export_requested.connect(self._on_export_requested)
        dialog.rejected.connect(self._teardown_dialog)  # Cancel: no export
        self._open_dialog(dialog, defer=False)

    def _on_export_requested(self) -> None:
        # Ask where to save, then render+write under a wait cursor. The export
        # dialog stays open throughout (it never accept()s), so a cancelled save or
        # a failed write leaves the user on the dialog to retry (D9/INV-12).
        from datetime import date

        dialog = self._dialog
        if not isinstance(dialog, ExportDialog):
            return
        options = dialog.options()
        default_name = (
            f"finbreak-report-{period_filename_slug(options.prefs, date.today())}.pdf"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export report as PDF"),
            default_name,
            self.tr("PDF files (*.pdf)"),
        )
        if not path:
            return  # Cancelled the save dialog — a clean no-op (dialog stays open).
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            PdfExportService(self._service.vault).export(options, path)
        except (VaultLockedError, OSError, pikepdf.PdfError):
            # The INV-12 failure set: a vault auto-lock mid-export, an unwritable
            # path / disk-full (OSError), or a pikepdf encryption error. export()
            # left no partial/unencrypted file; keep the dialog open so the user can
            # retry or pick another location. Anything else is a genuine bug and is
            # left to propagate (coding.md § 2) rather than mis-reported as a save
            # error.
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(
                self,
                self.tr("Export failed"),
                self.tr(
                    "Sorry, the report couldn't be saved there. Please choose "
                    "another location and try again."
                ),
            )
            return
        QApplication.restoreOverrideCursor()
        self._teardown_dialog()
        self._status(self.tr("Report exported"))

    # --- encrypted backup export / restore (FIBR-0014) ---------------------- #
    def _open_backup_export(self) -> None:
        # Reached from the Settings "Export backup…" button (INV-8). Tear down the
        # Settings dialog FIRST — the single _dialog slot holds one app-modal at a
        # time; leaving Settings shown would trap input over the new dialog.
        self._teardown_dialog()
        dialog = BackupExportDialog(self)
        dialog.export_requested.connect(self._on_backup_export_requested)
        dialog.rejected.connect(self._teardown_dialog)
        self._open_dialog(dialog, defer=False)

    def _on_backup_export_requested(self) -> None:
        # Ask where to save, then export SYNCHRONOUSLY on the main thread under a
        # wait cursor (INV-9): the blocked event loop means the auto-lock timer
        # cannot fire mid-export. The dialog stays open on cancel/failure to retry.
        from datetime import date

        dialog = self._dialog
        if not isinstance(dialog, BackupExportDialog):
            return
        default_name = f"finbreak-backup-{date.today().isoformat()}.fbk"
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save encrypted backup"),
            default_name,
            self.tr("finbreak backups (*.fbk)"),
        )
        if not path:
            return  # cancelled the save dialog — clean no-op, dialog stays open
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            BackupService(self._service.vault, self._service).export_backup(
                Path(path), dialog.password()
            )
        except (VaultLockedError, OSError, ValueError, DatabaseError):
            # A vault auto-lock mid-export (VaultLockedError), an unwritable path /
            # disk-full (OSError), or a SQLCipher engine error while sqlcipher_export
            # writes the intermediate DB (DatabaseError — an OperationalError isn't an
            # OSError). export_backup left no partial .fbk; keep the dialog open.
            QMessageBox.warning(
                self,
                self.tr("Backup failed"),
                self.tr(
                    "Sorry, the backup couldn't be saved there. Please choose "
                    "another location and try again."
                ),
            )
            return
        finally:
            # Restore on EVERY path — success, the caught set, or an uncaught bug —
            # so a stuck wait cursor never survives the export.
            QApplication.restoreOverrideCursor()
        self._teardown_dialog()
        self._status(self.tr("Backup saved"))

    def _open_backup_verify(self) -> None:
        # Reached from the Settings "Verify backup…" button (FIBR-0033 D5). Tear
        # down Settings FIRST — the single _dialog slot holds one app-modal at a
        # time — then open the verify dialog, mirroring _open_backup_export.
        self._teardown_dialog()
        dialog = BackupVerifyDialog(self)
        dialog.verify_requested.connect(self._on_backup_verify_requested)
        dialog.rejected.connect(self._teardown_dialog)
        self._open_dialog(dialog, defer=False)

    def _on_backup_verify_requested(self) -> None:
        # Verify SYNCHRONOUSLY under a wait cursor (D7), mirroring export's one-shot
        # UX. Unlike export/restore it needs no auto-lock protection — verify works
        # on a separate temp Vault and never touches the live vault (D3). The
        # expected "bad backup" outcomes come back as a VerifyResult, not an
        # exception (D4), so there is no warn/catch here; the answer is rendered in
        # the same dialog, which stays open for another try.
        dialog = self._dialog
        if not isinstance(dialog, BackupVerifyDialog):
            return
        source = dialog.source_path()
        if source is None:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = BackupService(self._service.vault, self._service).verify_backup(
                source, dialog.backup_password()
            )
        finally:
            # Restore on every path (incl. an unexpected bug that propagates) so a
            # stuck wait cursor never survives the verify.
            QApplication.restoreOverrideCursor()
        dialog.show_result(result)

    # --- optional password hint (FIBR-0029) -------------------------------- #
    def _open_set_hint(self) -> None:
        # Reached from the Settings "Set password hint…" button (§ 3.2). Tear down
        # Settings FIRST (one app-modal per _dialog slot), mirroring the backup
        # flows; pre-fill the current hint so "set" and "edit" are one flow.
        self._teardown_dialog()
        dialog = SetHintDialog(read_hint(), self)
        dialog.save_requested.connect(self._on_set_hint_requested)
        dialog.rejected.connect(self._teardown_dialog)
        self._open_dialog(dialog, defer=False)

    def _on_set_hint_requested(self) -> None:
        # Verify the current password (authorizes the change), enforce the hint
        # policy, then write / clear — all synchronous (§ 3.2). The KDF bytearray is
        # wiped in a finally (INV-8); the plaintext pw_str the UI already produced is
        # immutable and falls out of scope for GC (§ 3.4, an acknowledged residual).
        dialog = self._dialog
        if not isinstance(dialog, SetHintDialog):
            return
        hint = dialog.hint()
        pw_str = dialog.password()
        pw_bytes = bytearray(pw_str.encode("utf-8"))
        try:
            if not self._service.verify_password(pw_bytes):
                dialog.show_error(self.tr("That password is not correct."))
                return
            try:
                validate_hint(hint, pw_str)
            except HintPolicyError as exc:
                dialog.show_error(str(exc))
                return
            if hint.strip():
                write_hint(hint)
            else:
                clear_hint()  # a blank field clears the hint (INV-7)
        finally:
            pw_bytes[:] = bytes(len(pw_bytes))  # wipe the KDF buffer (INV-8)
        self._teardown_dialog()
        self._status(self.tr("Password hint saved"))

    def _on_start_over(self) -> None:
        # Destructive "start over" from the unlock screen (FIBR-0030). Two gates,
        # either cancel aborts with zero filesystem change.
        # Step 1 — irreversible warning; explicit buttons + a Cancel default so a
        # stray Enter cannot proceed (deliberately unlike statements.py's Yes-default
        # question, whose delete is reversible).
        choice = QMessageBox.warning(
            self,
            self.tr("Start over?"),
            self.tr(
                "This permanently erases your vault and everything in it. "
                "It cannot be undone, and the data cannot be recovered "
                "afterwards. Only do this if you have lost your password and "
                "have no backup."
            ),
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,  # default = the safe choice
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        # Step 2 — type-DELETE gate; a child modal over the still-open UnlockDialog.
        # It lives outside the managed _dialog slot, so dispose it explicitly.
        dialog = StartOverDialog(self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        dialog.deleteLater()
        if not accepted:
            return
        # Only reset_vault() is wrapped: a second concurrent instance holding the DB
        # open makes unlink raise OSError. Surface it and stay on unlock — do NOT
        # promise the vault is intact (a second-unlink failure leaves a mixed state).
        try:
            self._service.reset_vault()
        except OSError:
            QMessageBox.critical(
                self,
                self.tr("Start over failed"),
                self.tr(
                    "finbreak could not erase the vault. The reset failed, so "
                    "nothing has changed for certain — please try again."
                ),
            )
            return
        # Success only: clear the vault-coupled window.ini keys (the old vault's
        # throttle lockout + hint), then route to first-run.
        UnlockThrottle().reset()
        clear_hint()
        self._teardown_dialog()  # the child modal left UnlockDialog as the active slot
        self._route_pre_login()  # both files gone → state() == "first_run"

    def _open_restore(self) -> None:
        # Pre-login restore, reachable from first-run + unlock (INV-8). Tear down the
        # originating first-run/unlock dialog FIRST (one app-modal per _dialog slot);
        # hide()+deleteLater doesn't re-emit rejected, so first-run won't quit. On
        # cancel, route back to whichever pre-login surface the vault state calls for.
        self._teardown_dialog()
        dialog = BackupRestoreDialog(self)
        dialog.restore_requested.connect(self._on_restore_requested)
        dialog.rejected.connect(self._route_pre_login)
        self._open_dialog(dialog)

    def _reconcile_interrupted_restore(self) -> None:
        """If a restore crashed mid-install, recover the original vault from its
        ``*.old`` copies (FIBR-0014 D4/INV-5). A restore moves the existing pair
        aside to timestamped ``*.old`` and installs ``vault.db`` then the sidecar; a
        crash between those two renames leaves a **mixed** live pair. This acts ONLY
        on that exact signature — a mixed live state AND ``*.old`` copies present —
        which never occurs in normal operation, so a healthy or clean-first-run
        vault is untouched. The original is restored into place (the half-installed
        orphan discarded); the user lands on the unlock screen, whose 'Restore from
        a backup' affordance lets them retry if they were locked out."""
        vault_path = self._service.vault.vault_path
        sidecar_path = self._service.vault.sidecar_path

        def _by_stamp(directory: Path, base: str) -> dict[str, Path]:
            # base.<stamp>.old → {stamp: path}; the stamp is the slice between the
            # base filename and the ".old" suffix.
            return {
                p.name[len(base) + 1 : -len(".old")]: p
                for p in directory.glob(f"{base}.*.old")
            }

        db_olds = _by_stamp(vault_path.parent, vault_path.name)
        sidecar_olds = _by_stamp(sidecar_path.parent, sidecar_path.name)
        # A restore moves BOTH files aside under one stamp, so only a shared stamp is
        # a real original pair — pairing db[-1] with sidecar[-1] independently could
        # mismatch a db with an unrelated sidecar (wrong salt → un-openable).
        common = sorted(set(db_olds) & set(sidecar_olds))
        if not common:
            return  # no complete *.old pair — leave routing to state()
        try:
            self._service.state()
            return  # a clean live pair — the *.old are just kept-for-safety leftovers
        except VaultStateError:
            pass  # mixed live pair + a paired *.old present → an interrupted restore
        # Put the most-recent complete original pair back, discarding the
        # half-installed orphan (the *.old kept their 0o600 through the rename).
        stamp = common[-1]
        vault_path.unlink(missing_ok=True)
        sidecar_path.unlink(missing_ok=True)
        os.replace(db_olds[stamp], vault_path)
        os.replace(sidecar_olds[stamp], sidecar_path)

    def _route_pre_login(self) -> None:
        """Return to the correct pre-login surface (first-run when no vault, unlock
        when one exists) — used when a restore is cancelled."""
        if self._service.state() == "first_run":
            self._show_first_run()
        else:
            self._show_unlock()

    def _on_restore_requested(self) -> None:
        # Restore SYNCHRONOUSLY under a wait cursor, then re-enter the unlocked shell
        # under the new master password (D5). A failed restore keeps the dialog open
        # and changes nothing on disk (INV-4).
        dialog = self._dialog
        if not isinstance(dialog, BackupRestoreDialog):
            return
        source = dialog.source_path()
        if source is None:
            return
        new_master = dialog.new_master_password()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            BackupService(self._service.vault, self._service).restore_backup(
                source, dialog.backup_password(), new_master
            )
            # Open the freshly-restored vault under the new master (both derives run
            # under the one wait cursor).
            unlocked = self._service.unlock(bytearray(new_master, "utf-8"))
        except (BackupError, ValueError):
            QMessageBox.warning(
                self,
                self.tr("Restore failed"),
                self.tr(
                    "That backup couldn't be restored. Check the file and the "
                    "backup password, then try again."
                ),
            )
            return  # on-disk vault unchanged; dialog stays open to retry
        finally:
            # Restore on every path (incl. an unlock that raises) — no stuck cursor.
            QApplication.restoreOverrideCursor()
        if unlocked:
            self._status(self.tr("Backup restored"))
            self._enter_unlocked()
        else:  # should not happen — we just re-keyed to this password
            self._route_pre_login()

    def _on_settings_saved(self) -> None:
        # Persist the opt-in update flag from the checkbox (D5) — the auto-lock
        # value + datetime prefs the dialog already wrote to the vault in _on_save.
        dialog = self._dialog
        if isinstance(dialog, SettingsDialog):
            self._update_service.set_enabled(dialog.update_enabled())
            # Persist the built-in category-library toggle (FIBR-0139 D6). Built on
            # demand — cheap, stateless; no new shell member. Takes effect on the next
            # import / Apply, not an immediate re-file (INV-7).
            CategorizationService(self._service.vault).set_library_enabled(
                dialog.library_enabled()
            )
        # Re-read the datetime prefs and push them to the open display tabs, so a
        # format/zone change takes effect live without a relaunch (FIBR-0083 D7).
        self._prefs = self._service.datetime_prefs()
        self._amount_prefs = self._service.amount_prefs()
        # Home is the dashboard now — it shows amounts (tiles) but no dates, so only
        # the amount prefs apply; the Transactions table shows both (FIBR-0012 D6/D7).
        if self._home_tab is not None:
            self._home_tab.set_amount_prefs(self._amount_prefs)
        if self._transactions_tab is not None:
            self._transactions_tab.set_datetime_prefs(self._prefs)
            self._transactions_tab.set_amount_prefs(self._amount_prefs)
        if self._statements_tab is not None:
            self._statements_tab.set_datetime_prefs(self._prefs)
        self._teardown_dialog()
        self._status(self.tr("Settings saved"))

    # --- opt-in auto-update (FIBR-0054 D7/D15) ------------------------------ #
    def _maybe_check_for_update(self) -> None:
        # Off a supported package (no installer), or opted out, the feature is inert
        # (INV-1/INV-7). One bounded check per launch, on a worker so the network
        # never blocks the UI.
        if self._installer is None or not self._update_service.is_enabled():
            return
        worker = UpdateCheckWorker(self._update_service, self)
        worker.found.connect(self._on_update_found)
        # none/failed: stay silent — proceed exactly as if up to date (INV-11).
        worker.none.connect(lambda: None)
        worker.failed.connect(lambda _exc: None)
        worker.finished.connect(worker.deleteLater)
        self._update_check_worker = worker
        worker.start()

    def _on_update_found(self, info: UpdateInfo) -> None:
        # Hold the offer; show it only once unlocked + idle (D15). The network
        # usually returns AFTER the user has unlocked, so this commonly shows now.
        self._pending_update = info
        self._maybe_show_pending_offer()

    def _maybe_show_pending_offer(self) -> None:
        info = self._pending_update
        # Only when we hold an offer, are unlocked, and no other dialog is up —
        # two app-modals cannot share the single self._dialog slot (D15).
        if info is None or not self._unlocked or self._dialog is not None:
            return
        self._pending_update = None  # shown at most once per launch (D15)
        self._offered_update = info
        dialog = UpdateDialog(__version__, info.version, info.notes, self)
        dialog.later.connect(self._on_update_later)
        dialog.skip.connect(self._on_update_skip)
        dialog.update_now.connect(self._on_update_now)
        self._open_dialog(dialog, defer=False)

    def _check_for_updates_now(self) -> None:
        # Help → Check for updates: an explicit, on-demand check that gives
        # feedback on EVERY outcome (unlike the silent startup check, INV-11).
        # The click is its own consent, so it runs even if the startup opt-in is
        # off (force=True). A found offer reuses the D15 prompt via
        # _on_update_found (we're unlocked + idle when the menu is used).
        if self._installer is None:
            QMessageBox.information(
                self,
                self.tr("Check for updates"),
                self.tr(
                    "Automatic updates aren't available for this build of finbreak."
                ),
            )
            return
        worker = UpdateCheckWorker(self._update_service, self, force=True)
        worker.found.connect(self._on_update_found)
        worker.none.connect(self._on_manual_check_up_to_date)
        worker.failed.connect(self._on_manual_check_error)
        worker.finished.connect(worker.deleteLater)
        self._manual_check_worker = worker
        worker.start()

    def _on_manual_check_up_to_date(self) -> None:
        QMessageBox.information(
            self,
            self.tr("Check for updates"),
            self.tr("You're on the latest version ({version}).").format(
                version=__version__
            ),
        )

    def _on_manual_check_error(self, _exc: object) -> None:
        QMessageBox.warning(
            self,
            self.tr("Check for updates"),
            self.tr(
                "Couldn't check for updates. Check your internet connection and "
                "try again."
            ),
        )

    def _on_update_later(self) -> None:
        self._teardown_dialog()  # re-ask next launch; nothing persisted (INV-8)

    def _on_update_skip(self) -> None:
        if self._offered_update is not None:
            self._update_service.skip_version(self._offered_update.version)  # INV-8
        self._teardown_dialog()

    def _on_update_now(self) -> None:
        info = self._offered_update
        if info is None:
            return
        # Capture THIS prompt: if an auto-lock tears it down before the download
        # finishes, the stale result is dropped (INV-9). The dialog is already in
        # its busy state (it entered it on the click).
        prompt = self._dialog
        worker = DownloadWorker(self._update_service, info, self)
        worker.ready.connect(lambda path: self._on_download_ready(path, prompt))
        worker.failed.connect(lambda exc: self._on_download_failed(exc, prompt))
        worker.finished.connect(worker.deleteLater)
        self._download_worker = worker
        worker.start()

    def _on_download_ready(self, path: Path, prompt: QDialog | None) -> None:
        prompt_live = (
            self._dialog is prompt and prompt is not None and shiboken6.isValid(prompt)
        )
        if prompt_live and self._installer is not None:
            # Swap + relaunch; the key is wiped as this process commits to being
            # replaced and before the relaunch (INV-6) — in-process after os.replace
            # on Linux, before the detached swap helper on Windows. apply() does not
            # return.
            self._installer.apply(path, on_before_exec=self._service.on_about_to_quit)
        else:
            # The prompt was torn down (auto-lock) — drop the verified temp so it
            # doesn't orphan next to the running binary (INV-9).
            Path(path).unlink(missing_ok=True)

    def _on_download_failed(self, _exc: object, prompt: QDialog | None) -> None:
        # Any verify/oversize/timeout/disk failure surfaces here and stays on the
        # current version (INV-11). Mirror _on_download_ready's guard: if an
        # auto-lock tore the busy prompt down mid-download (self._dialog is now
        # the re-opened UnlockDialog), stay silent — destroying that dialog and
        # popping a warning over the lock screen would be a jarring glitch, and
        # INV-11 already holds. Only close + explain when our prompt is still up.
        prompt_live = (
            self._dialog is prompt and prompt is not None and shiboken6.isValid(prompt)
        )
        if not prompt_live:
            return
        self._teardown_dialog()
        QMessageBox.warning(
            self,
            self.tr("Update failed"),
            self.tr(
                "The update could not be installed. You are still on the "
                "current version."
            ),
        )

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

    def _refresh_after_statement_change(self) -> None:
        # A statement delete/move changed the transaction set — refresh Home + the
        # count even though the Statements tab is current (INV-10/INV-11). Shared by
        # the delete and Change-account handlers (FIBR-0059); a move leaves the
        # total count unchanged, so this is a no-op for it but kept for symmetry.
        if self._home_tab is not None:
            self._home_tab.refresh()
            self._refresh_count(self._home_tab.transaction_count())

    def _on_statement_changed(self) -> None:
        self._refresh_after_statement_change()
        self._status(self.tr("Statement deleted"))

    def _on_statement_reassigned(self) -> None:
        # A Change-account move (FIBR-0059) — its own status message, NOT the
        # delete handler's "Statement deleted".
        self._refresh_after_statement_change()
        self._status(self.tr("Statement account changed"))

    def _open_url(self, url: str) -> None:
        # Hands a page (a funding link) to the OS browser — a user-initiated
        # egress, not an app network call. The app's
        # ONE app-made call is the opt-in update check (FIBR-0054), confined to
        # services/update_fetch.py; opening the browser here is not that.
        QDesktopServices.openUrl(QUrl(url))

    def _about_text(self) -> str:
        # Includes the running version so a user can tell which build they're on
        # (FIBR-0054 dogfooding: the About box previously showed no version).
        # tr() takes a literal; the version is interpolated (coding.md § 5.2).
        return self.tr(
            "finbreak {version}\nA private, offline personal-finance vault."
        ).format(version=__version__)

    def _show_about(self) -> None:
        QMessageBox.about(self, self.tr("About finbreak"), self._about_text())

    # --- window geometry (INV-5/INV-6) -------------------------------------- #
    def _settings(self) -> QSettings:
        return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)

    def _restore_geometry(self) -> int:
        """Apply saved size/position/state; return the saved last-tab index (0 when
        none). Called in __init__, before the window is shown (INV-5). On Wayland
        (FIBR-0060) restore only the SIZE via ``resize()`` — the compositor owns
        placement, so ``restoreGeometry``'s position is ignored and its size is
        unreliable before the first map."""
        settings = self._settings()
        if _is_wayland():
            size = settings.value(_KEY_SIZE)
            self.resize(size if isinstance(size, QSize) else _DEFAULT_WINDOW_SIZE)
        else:
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
        # Save the bare size too, so the Wayland restore path has a size to apply
        # without decoding the opaque saveGeometry blob (FIBR-0060).
        settings.setValue(_KEY_SIZE, self.size())
        if self._workspace is not None and shiboken6.isValid(self._workspace):
            settings.setValue(_KEY_LAST_TAB, self._workspace.currentIndex())
        settings.sync()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()  # persist size/position/state/tab on quit (D7)
        super().closeEvent(event)

    def _center_window(self) -> None:
        """Center the window on its screen. On X11 / Windows / macOS a plain
        ``move()`` works; on KDE Wayland it dispatches to KWin's scripting API
        (``move()`` is a no-op there). On any other Wayland compositor this is a
        safe no-op — the action is disabled, but ``_reset_layout`` also calls it
        (FIBR-0060)."""
        if _is_wayland():
            if _kde_wayland():
                self._center_kwin()
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _center_kwin(self) -> None:
        """Center under KWin (KDE Plasma) via its scripting D-Bus API — the one
        way to place a window on Wayland (FIBR-0060). Loads a tiny script that
        moves our window (matched by PID) to its work-area centre, then unloads
        it. Best-effort: any failure (no D-Bus / KWin, sandboxed, ImportError)
        leaves the window where it is rather than crashing the slot."""
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface
        except ImportError:
            return
        script = _KWIN_CENTER_JS.replace("__PID__", str(os.getpid()))
        handle: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", prefix="finbreak_center_", delete=False
            ) as fh:
                handle = fh.name  # capture before the write, so a failed write
                fh.write(script)  # still cleans the just-created temp file up
            scripting = QDBusInterface(
                "org.kde.KWin",
                "/Scripting",
                "org.kde.kwin.Scripting",
                QDBusConnection.sessionBus(),
            )
            if scripting.isValid():
                # loadScript reads the file synchronously (returns a script id),
                # start() runs it, unloadScript() disposes it — so the temp file
                # is safe to delete immediately after.
                scripting.call("loadScript", handle, "finbreak_center")
                scripting.call("start")
                scripting.call("unloadScript", "finbreak_center")
        finally:
            if handle is not None:
                try:
                    os.unlink(handle)
                except OSError:
                    pass

    def _reset_layout(self) -> None:
        settings = self._settings()
        settings.remove(_KEY_GEOMETRY)
        settings.remove(_KEY_STATE)
        settings.remove(_KEY_SIZE)
        settings.sync()
        self.resize(_DEFAULT_WINDOW_SIZE)
        self._center_window()  # a no-op on Wayland; the resize above still applies

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
                self._transactions_tab = None
                self._statements_tab = None
                self._accounts_tab = None
                self._categories_tab = None
                self._rules_tab = None
                self._transfers_tab = None
                self._recurring_tab = None
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
