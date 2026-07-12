"""FIBR-0051 — app-shell UX redesign. Enforces tests/features/app_shell/spec.md.

The shell (`MainWindow(QMainWindow)`) + its dialogs are driven headless via the
pytest-qt `qtbot`. Happy paths run a real ~47 MiB Argon2id derivation on a worker
thread (the FIBR-0004 `qtbot.waitSignal` pattern); only INV-2f monkeypatches a
`DeriveWorker` stub to catch the mid-flight state the real derivation is too fast
to hold. Every vault lives under `tmp_path`; no network, no real data.
"""

import re
from decimal import Decimal
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QLocale, Qt, QThread
from PySide6.QtGui import QAction, QDesktopServices, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QStackedWidget,
    QToolBar,
)

from conftest import _PW, _pump_deferred_delete
from finbreak.errors import VaultStateError
from finbreak.migrations import DEFAULT_ACCOUNT_NAME
from finbreak.models import Transaction
from finbreak.repositories.accounts import AccountRepository
from finbreak.services.auth import AmountPrefs, AuthService
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService
from finbreak.ui import main_window
from finbreak.ui._worker import DeriveWorker
from finbreak.ui.first_run import FirstRunDialog
from finbreak.ui.home import (
    _COL_AMOUNT,
    _COL_DATE,
    _NEGATIVE_TEXT,
    _POSITIVE_TEXT,
    HomeView,
    _format_amount,
)
from finbreak.ui.main_window import MainWindow
from finbreak.ui.manual_entry import ManualEntryDialog
from finbreak.ui.unlock import UnlockDialog

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def _default_id(service: AuthService) -> int:
    accounts = AccountRepository(service.vault.connection).list_all()
    return next(a.id for a in accounts if a.name == DEFAULT_ACCOUNT_NAME)


def _unlocked_home_shell(qtbot, service) -> MainWindow:
    """A shell driven past routing to a live Home (test-setup note (a): a headless
    first_run leaves both files present, so __init__ routes to the locked shell;
    _enter_unlocked drives to Home exactly as a real unlock success does)."""
    service.first_run(bytearray(_PW), "ZAR")
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    return window


class _StubWorker(DeriveWorker):
    """A DeriveWorker whose start() never completes — holds the dialog in the
    'derivation in flight' state the real ~1–2 s Argon2id can't be caught in
    (INV-2f). failed() is forced by the test to drive the completion path."""

    def start(  # noqa: D401 — never runs; stays pending
        self, priority: QThread.Priority = QThread.Priority.InheritPriority
    ) -> None:
        pass


def test_FIBR0114_user_input_resets_idle_timer(qtbot, service, monkeypatch):
    # The shell must treat user activity as "still using the app": a key/mouse event
    # anywhere re-arms the idle-lock countdown via AuthService.notify_activity, so the
    # timeout is measured from the last interaction, not from unlock (FIBR-0114).
    window = _unlocked_home_shell(qtbot, service)
    calls: list[bool] = []
    monkeypatch.setattr(service, "notify_activity", lambda: calls.append(True))
    key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, key)
    assert calls, "a user-input event must reset the idle-lock countdown"


# --------------------------------------------------------------------------- #
# INV-1 — chrome parts + canonical action set
# --------------------------------------------------------------------------- #
def test_INV1_chrome_parts_and_action_set(qtbot, service):
    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    window = MainWindow(service)
    qtbot.addWidget(window)

    assert window.menuBar() is not None
    assert window.findChildren(QToolBar), "a toolbar exists"
    assert isinstance(window.centralWidget(), QStackedWidget)
    assert window.statusBar() is not None

    for name in (
        "action_manual_entry",
        "action_import",
        "action_settings",  # FIBR-0055: File → Settings…
        "action_accounts",
        "action_categories",
        "action_lock",
        "action_quit",
        "action_home",
        # FIBR-0052: Statements nav + the vault-independent Window menu actions.
        "action_statements",
        "action_center_window",
        "action_reset_layout",
        "action_about",
        "action_check_updates",  # FIBR-0054: Help → Check for updates…
        "action_donate_github",
        "action_donate_patreon",
        "action_donate_paybru",
    ):
        assert window.findChild(QAction, name) is not None, name


# --------------------------------------------------------------------------- #
# INV-2 — startup routing (window first, popup over it)
# --------------------------------------------------------------------------- #
def test_INV2a_first_run_happy_path(qtbot, service):
    window = MainWindow(service)
    qtbot.addWidget(window)

    assert window.centralWidget().currentWidget().objectName() == "placeholder_welcome"
    assert isinstance(window._dialog, FirstRunDialog)
    assert not window._toolbar.isEnabled(), "chrome disabled until the vault exists"

    dlg = window._dialog
    dlg._password.setText(_PW.decode())
    dlg._confirm.setText(_PW.decode())
    with qtbot.waitSignal(dlg.completed, timeout=15000):
        dlg._submit.click()

    assert window._toolbar.isEnabled()
    workspace = window.centralWidget().currentWidget()
    assert workspace.objectName() == "workspace"
    assert workspace.currentWidget().objectName() == "tab_home"


def test_INV2b_unlock_happy_path(qtbot, service):
    service.first_run(bytearray(_PW), "ZAR")
    TransactionService(service.vault).add_transaction(
        _default_id(service), "2026-07-01", "-12.34", "coffee"
    )
    service.lock()

    window = MainWindow(service)
    qtbot.addWidget(window)
    assert window.centralWidget().currentWidget().objectName() == "placeholder_locked"
    assert isinstance(window._dialog, UnlockDialog)

    dlg = window._dialog
    dlg._password.setText("the wrong password")
    with qtbot.waitSignal(dlg.unlock_failed, timeout=15000):
        dlg._unlock_button.click()
    assert not window._toolbar.isEnabled()
    assert isinstance(window._dialog, UnlockDialog), "the dialog stays for a retry"

    dlg._password.setText(_PW.decode())
    with qtbot.waitSignal(dlg.unlocked, timeout=15000):
        dlg._unlock_button.click()
    assert window._toolbar.isEnabled()
    workspace = window.centralWidget().currentWidget()
    assert workspace.objectName() == "workspace"
    assert workspace.currentWidget().objectName() == "tab_home"


def test_INV2c_mixed_pair_raises_at_construction(qtbot, paths):
    vault_path, sidecar_path = paths
    vault_path.write_bytes(b"partial vault, no sidecar")  # a mixed pair
    service = AuthService(vault_path, sidecar_path)
    with pytest.raises(VaultStateError):
        MainWindow(service)


def test_INV2d_first_run_cancel_quits(qtbot, service, monkeypatch, paths):
    window = MainWindow(service)
    qtbot.addWidget(window)
    dlg = window._dialog
    assert isinstance(dlg, FirstRunDialog)

    calls = []
    monkeypatch.setattr(QApplication, "quit", lambda *a: calls.append(1))
    dlg.reject()
    assert calls == [1], "dismissing first-run quits the app"
    vault_path, _ = paths
    assert not vault_path.exists(), "no vault was created"


def test_INV2e_unlock_cancel_leaves_locked_shell(qtbot, service, monkeypatch):
    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    window = MainWindow(service)
    qtbot.addWidget(window)
    dlg = window._dialog
    assert isinstance(dlg, UnlockDialog)

    calls = []
    monkeypatch.setattr(QApplication, "quit", lambda *a: calls.append(1))
    dlg.reject()
    assert calls == [], "dismissing unlock does NOT quit"
    assert window.centralWidget().currentWidget().objectName() == "placeholder_locked"
    assert window._dialog is None

    button = window.findChild(QPushButton, "button_unlock")
    assert button is not None
    button.click()
    assert isinstance(window._dialog, UnlockDialog), "Unlock button re-opens the dialog"


@pytest.mark.parametrize("kind", ["unlock", "first_run"])
def test_INV2f_no_cancel_during_derivation_crash(qtbot, service, monkeypatch, kind):
    if kind == "unlock":
        service.first_run(bytearray(_PW), "ZAR")
        service.lock()
        import finbreak.ui.unlock as module

        monkeypatch.setattr(module, "DeriveWorker", _StubWorker)
        dlg = UnlockDialog(service)
        dlg._password.setText(_PW.decode())
        submit = dlg._unlock_button
    else:
        import finbreak.ui.first_run as module

        monkeypatch.setattr(module, "DeriveWorker", _StubWorker)
        dlg = FirstRunDialog(service)
        dlg._password.setText(_PW.decode())
        dlg._confirm.setText(_PW.decode())
        submit = dlg._submit
    qtbot.addWidget(dlg)

    submit.click()
    assert dlg._worker is not None, "a derivation is in flight"

    dlg.reject()
    dlg.close()
    assert shiboken6.isValid(dlg), "reject()/close is a no-op mid-derivation"
    assert dlg._worker is not None, "the worker is not torn down"
    assert not dlg._cancel.isEnabled(), "Cancel is disabled while deriving"

    dlg._worker.failed.emit(RuntimeError("boom"))
    assert dlg._worker is None
    assert dlg._cancel.isEnabled(), "Cancel re-enabled once the worker clears"


# --------------------------------------------------------------------------- #
# INV-3 — no transaction data while locked (security)
# --------------------------------------------------------------------------- #
def test_INV3_no_transaction_data_while_locked(qtbot, service):
    service.first_run(bytearray(_PW), "ZAR")
    TransactionService(service.vault).add_transaction(
        _default_id(service), "2026-07-01", "-12.34", "coffee"
    )
    service.lock()

    window = MainWindow(service)
    qtbot.addWidget(window)
    current = window.centralWidget().currentWidget()
    assert current.objectName() == "placeholder_locked"
    assert not isinstance(current, HomeView)
    assert window._live is None, "no content widget holds decrypted rows while locked"


# --------------------------------------------------------------------------- #
# INV-4 — lock/auto-lock returns to the locked shell, window intact
# --------------------------------------------------------------------------- #
def test_INV4a_autolock_destroys_content_same_window(qtbot, service):
    # FIBR-0052 reshape: the destroyed object is now the whole tabbed workspace
    # (all four data tabs), not a single HomeView (INV-3).
    window = _unlocked_home_shell(qtbot, service)
    workspace = window.centralWidget().currentWidget()
    assert workspace.objectName() == "workspace"

    service._on_idle_timeout()  # production entry: lock() then on_auto_lock()
    assert service._key is None, "auto-lock wipes the key"
    _pump_deferred_delete()

    assert not shiboken6.isValid(workspace), (
        "the workspace (decrypted rows) is destroyed"
    )
    assert window.centralWidget().currentWidget().objectName() == "placeholder_locked"
    assert not window._toolbar.isEnabled()
    count = window.findChild(QLabel, "status_txn_count")
    assert count.isHidden(), "the transaction count is hidden while locked"
    assert isinstance(window._dialog, UnlockDialog), "the UnlockDialog re-opened"


def test_INV4b_autolock_closes_open_manual_dialog(qtbot, service):
    window = _unlocked_home_shell(qtbot, service)
    window._action_manual_entry.trigger()
    manual = window._dialog
    assert isinstance(manual, ManualEntryDialog)

    service._on_idle_timeout()
    _pump_deferred_delete()

    assert not shiboken6.isValid(manual), "the entry dialog is destroyed on auto-lock"
    assert isinstance(window._dialog, UnlockDialog), "the re-opened dialog is Unlock"


# --------------------------------------------------------------------------- #
# INV-5 — FIBR-0004 key lifetime untouched
# --------------------------------------------------------------------------- #
def test_INV5_key_lifetime_untouched(qtbot, service):
    window = _unlocked_home_shell(qtbot, service)
    assert service.on_auto_lock is not None, "the shell wires the auto-lock callback"
    assert service._key is not None

    window._action_lock.trigger()
    assert service._key is None, "a manual lock wipes the key"


# --------------------------------------------------------------------------- #
# INV-6 — content routing, done returns Home
# --------------------------------------------------------------------------- #
def test_INV6a_content_routing_switches_tabs_stable_instances(qtbot, service):
    # FIBR-0052 reshape (INV-2/INV-2a): the nav actions SWITCH the workspace's
    # current tab (never rebuild it); the tab widget instances are stable across
    # switches, unlike the old build-a-fresh-widget-then-done-returns-Home model.
    window = _unlocked_home_shell(qtbot, service)
    workspace = window.centralWidget().currentWidget()
    assert workspace.objectName() == "workspace"

    for attr, object_name in (
        ("_action_accounts", "tab_accounts"),
        ("_action_categories", "tab_categories"),
        ("_action_statements", "tab_statements"),
        ("_action_home", "tab_home"),
    ):
        getattr(window, attr).trigger()
        assert workspace.currentWidget().objectName() == object_name, attr

    # INV-2a: re-triggering returns the SAME instance (a switch, not a rebuild).
    window._action_accounts.trigger()
    first = workspace.currentWidget()
    window._action_home.trigger()
    window._action_accounts.trigger()
    assert workspace.currentWidget() is first, (
        "the Accounts tab is switched, not rebuilt"
    )


# --------------------------------------------------------------------------- #
# INV-7 — status bar narrates activity
# --------------------------------------------------------------------------- #
def test_INV7_status_bar_count_and_messages(qtbot, service):
    service.first_run(bytearray(_PW), "ZAR")
    TransactionService(service.vault).add_transaction(
        _default_id(service), "2026-07-01", "-12.34", "coffee"
    )
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()

    count = window.findChild(QLabel, "status_txn_count")
    assert count is not None
    assert not count.isHidden()
    assert "1" in count.text(), "the count reflects the one transaction"

    window._status("Working…")  # a transient message (a tr()-wrapped literal)
    assert window.statusBar().currentMessage() == "Working…"
    # When the transient expires (simulated by clearing it), the bar settles back
    # to the resting "Ready" rather than going blank (INV-7).
    window.statusBar().clearMessage()
    assert window.statusBar().currentMessage() == "Ready"

    window._action_lock.trigger()
    assert count.isHidden(), "the count is hidden while locked"


# --------------------------------------------------------------------------- #
# INV-8 — Donate hands funding pages to the OS browser (no app fetch)
# --------------------------------------------------------------------------- #
def test_INV8a_donate_opens_exact_urls(qtbot, service, monkeypatch):
    window = _unlocked_home_shell(qtbot, service)
    calls = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: calls.append(url.toString()) or True
    )

    window._action_donate_github.trigger()
    window._action_donate_patreon.trigger()
    window._action_donate_paybru.trigger()

    assert calls == [
        main_window.DONATE_GITHUB,
        main_window.DONATE_PATREON,
        main_window.DONATE_PAYBRU,
    ]
    assert len(calls) == 3, "the three Donate items are the sole openUrl callers"


def test_INV8a_funding_yml_in_sync():
    funding = Path(__file__).resolve().parents[3] / ".github" / "FUNDING.yml"
    values = {}
    for raw in funding.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        # The real file uses YAML flow-sequences: strip [ ] brackets and quotes.
        value = value.strip().strip("[]").strip().strip('"').strip("'")
        values[key.strip()] = value

    assert (
        main_window.DONATE_GITHUB == f"https://github.com/sponsors/{values['github']}"
    )
    assert main_window.DONATE_PATREON == f"https://www.patreon.com/{values['patreon']}"
    assert main_window.DONATE_PAYBRU == values["custom"]


# --------------------------------------------------------------------------- #
# INV-9 — manual-entry round-trip
# --------------------------------------------------------------------------- #
def test_INV9_manual_entry_roundtrip_from_home(qtbot, service):
    window = _unlocked_home_shell(qtbot, service)
    txn = TransactionService(service.vault)
    before = len(txn.list_transactions())

    window._action_manual_entry.trigger()
    dlg = window._dialog
    assert isinstance(dlg, ManualEntryDialog)
    dlg._amount.setText("-12.34")
    dlg._description.setText("coffee")
    with qtbot.waitSignal(dlg.committed):
        dlg._add_button.click()

    assert len(txn.list_transactions()) == before + 1
    workspace = window.centralWidget().currentWidget()
    assert workspace.currentWidget().objectName() == "tab_home", (
        "committing shows the refreshed Home tab"
    )


def test_INV9_manual_entry_roundtrip_from_non_home(qtbot, service):
    window = _unlocked_home_shell(qtbot, service)
    workspace = window.centralWidget().currentWidget()
    window._action_accounts.trigger()
    assert workspace.currentWidget().objectName() == "tab_accounts"

    window._action_manual_entry.trigger()
    dlg = window._dialog
    dlg._amount.setText("100.00")
    dlg._description.setText("salary")
    with qtbot.waitSignal(dlg.committed):
        dlg._add_button.click()

    assert workspace.currentWidget().objectName() == "tab_home", (
        "committing from a non-Home tab shows the refreshed Home tab"
    )


def test_INV9_manual_entry_cancel_and_invalid(qtbot, service):
    window = _unlocked_home_shell(qtbot, service)
    txn = TransactionService(service.vault)
    before = len(txn.list_transactions())

    window._action_manual_entry.trigger()
    dlg = window._dialog
    dlg._amount.setText("not-a-number")
    dlg._description.setText("x")
    dlg._add_button.click()
    assert dlg._error.text() != "", "an invalid amount shows an in-dialog error"
    assert len(txn.list_transactions()) == before, "nothing was inserted"
    assert window._dialog is dlg, "the dialog stays open"

    dlg.reject()  # Cancel
    assert window._dialog is None
    assert len(txn.list_transactions()) == before, "Cancel inserts nothing"


def test_INV9a_home_toggles_empty_and_table(qtbot, service):
    service.first_run(bytearray(_PW), "ZAR")
    txn = TransactionService(service.vault)
    home = HomeView(txn, CategorizationService(service.vault))
    qtbot.addWidget(home)

    assert home.current_page().objectName() == "home_page_empty"
    assert home.transaction_count() == 0

    txn.add_transaction(_default_id(service), "2026-07-01", "-12.34", "coffee")
    home.refresh()
    assert home.current_page().objectName() == "home_page_table"
    assert home.transaction_count() == 1


# --------------------------------------------------------------------------- #
# INV-10 — every new widget is translation- and RTL-ready
# --------------------------------------------------------------------------- #
def test_INV10_no_fixed_geometry_in_new_ui():
    import finbreak.ui as ui_pkg

    ui_dir = Path(ui_pkg.__file__).parent
    pattern = re.compile(r"\.(setGeometry|move|resize)\(\s*\d")
    offenders = []
    for py in sorted(ui_dir.glob("*.py")):
        for lineno, line in enumerate(py.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{py.name}:{lineno}")
    assert not offenders, f"fixed-geometry calls found: {offenders}"


def test_INV10_format_amount_localised(qtbot):
    from PySide6.QtCore import QLocale

    # _format_amount renders via the DEFAULT QLocale, so pin the C locale (a "."
    # decimal separator) for a hermetic assertion — else a comma-decimal system
    # locale (e.g. de_DE → "12,34") would false-fail on the "." below.
    previous = QLocale()
    QLocale.setDefault(QLocale.c())
    try:
        rendered = _format_amount(Decimal("-12.34"), "ZAR")
        assert "12.34" in rendered, "the amount renders via QLocale with 2 decimals"
    finally:
        QLocale.setDefault(previous)


# --------------------------------------------------------------------------- #
# FIBR-0105 — amount display: negative sign style (INV-3) + colour (INV-4/1)
# --------------------------------------------------------------------------- #
def test_FIBR0105_format_amount_sign_styles_are_locale_independent(qtbot):
    # Hermetic under any locale (incl. the CI C locale): the sign notation is
    # built by the formatter, not delegated to QLocale's negative pattern (INV-3).
    previous = QLocale()
    QLocale.setDefault(QLocale.c())
    try:
        minus = _format_amount(Decimal("-25000"), "ZAR", "minus")
        assert minus.startswith("-") and "(" not in minus and ")" not in minus

        brackets = _format_amount(Decimal("-25000"), "ZAR", "brackets")
        assert "(" in brackets and ")" in brackets and not brackets.startswith("-")

        # Positives and zero (incl. -0.00, which is not < 0) are bare under both.
        for style in ("minus", "brackets"):
            for value in (Decimal("69"), Decimal("0.00"), Decimal("-0.00")):
                bare = _format_amount(value, "ZAR", style)
                assert not bare.startswith("-")
                assert "(" not in bare and ")" not in bare
    finally:
        QLocale.setDefault(previous)


def test_FIBR0105_format_amount_defaults_to_minus(qtbot):
    # The 2-arg default keeps the existing caller valid AND is the minus style.
    previous = QLocale()
    QLocale.setDefault(QLocale.c())
    try:
        assert _format_amount(Decimal("-5"), "ZAR").startswith("-")
    finally:
        QLocale.setDefault(previous)


def _stub_home(service, monkeypatch, displays, amount_prefs):
    """A HomeView over controlled display Decimals — the only way to render a
    zero-amount row (the service rejects zero amounts), so all three colour
    branches (neg/pos/zero) are exercised deterministically (INV-4)."""
    txn = TransactionService(service.vault)
    rows = [
        (
            Transaction(
                i + 1, 1, "2026-07-01", 0, f"row{i}", "2026-07-01T00:00:00", None, None
            ),
            display,
            "Account",
            "",
        )
        for i, display in enumerate(displays)
    ]
    monkeypatch.setattr(txn, "list_transactions", lambda: rows)
    monkeypatch.setattr(txn, "base_currency", lambda: "ZAR")
    home = HomeView(
        txn, CategorizationService(service.vault), amount_prefs=amount_prefs
    )
    return home


def test_FIBR0105_amount_colour_marks_direction_when_on(qtbot, service, monkeypatch):
    service.first_run(bytearray(_PW), "ZAR")
    home = _stub_home(
        service,
        monkeypatch,
        [Decimal("-25000.00"), Decimal("100.00"), Decimal("0.00")],
        AmountPrefs("minus", True),
    )
    qtbot.addWidget(home)
    table = home._table

    # negative -> red, positive -> green (unwrap the QBrush to its QColor).
    assert table.item(0, _COL_AMOUNT).foreground().color() == _NEGATIVE_TEXT
    assert table.item(1, _COL_AMOUNT).foreground().color() == _POSITIVE_TEXT
    # zero -> no per-cell foreground override.
    assert table.item(2, _COL_AMOUNT).data(Qt.ItemDataRole.ForegroundRole) is None
    # Amount cell only: the negative row's Date cell stays default even with colour on.
    assert table.item(0, _COL_DATE).data(Qt.ItemDataRole.ForegroundRole) is None


def test_FIBR0105_amount_colour_off_sets_no_foreground(qtbot, service, monkeypatch):
    service.first_run(bytearray(_PW), "ZAR")
    home = _stub_home(
        service,
        monkeypatch,
        [Decimal("-25000.00"), Decimal("100.00")],
        AmountPrefs("minus", True),
    )
    qtbot.addWidget(home)
    table = home._table
    assert table.item(0, _COL_AMOUNT).foreground().color() == _NEGATIVE_TEXT

    # Toggle colour OFF + re-render: a fresh item per row leaves no stale colour.
    home.set_amount_prefs(AmountPrefs("minus", False))
    assert table.item(0, _COL_AMOUNT).data(Qt.ItemDataRole.ForegroundRole) is None
    assert table.item(1, _COL_AMOUNT).data(Qt.ItemDataRole.ForegroundRole) is None


def test_FIBR0105_display_does_not_mutate_stored_amount(qtbot, service):
    # INV-1: sign/colour are display-only; the stored amount is untouched.
    service.first_run(bytearray(_PW), "ZAR")
    txn = TransactionService(service.vault)
    txn.add_transaction(_default_id(service), "2026-07-01", "-25000.00", "rent")
    home = HomeView(
        txn,
        CategorizationService(service.vault),
        amount_prefs=AmountPrefs("brackets", True),
    )
    qtbot.addWidget(home)
    (_, display, _, _) = txn.list_transactions()[0]
    assert display == Decimal("-25000.00")


# --------------------------------------------------------------------------- #
# FIBR-0037 — branded application/window icon
# --------------------------------------------------------------------------- #
def test_FIBR0037_app_icon_renders(qtbot):
    from PySide6.QtCore import QSize

    from finbreak.ui import icons
    from finbreak.ui.icons import app_icon

    # The raster app icon travels as package data in ui/icons/ beside the glyphs.
    assert icons._APP_ICON.is_file()
    # A non-null rendered pixmap proves the PNG actually loads (a broken/absent
    # file yields a null pixmap even though QIcon(path) is non-null).
    pixmap = app_icon().pixmap(QSize(64, 64))
    assert not pixmap.isNull() and not pixmap.size().isEmpty()


def test_rules_toolbar_action_has_a_rendering_icon(qtbot, service):
    """The Rules action sits on the toolbar (text-under-icon), so it needs a
    glyph like its neighbours — it shipped text-only (no icon_name, no rules.svg),
    surfaced dogfooding v0.1.0. A non-null rendered pixmap proves the SVG loads."""
    from PySide6.QtCore import QSize

    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    window = MainWindow(service)
    qtbot.addWidget(window)

    action = window.findChild(QAction, "action_rules")
    assert action is not None
    assert not action.icon().pixmap(QSize(24, 24)).isNull(), "Rules needs an icon"


def test_about_text_shows_version(qtbot, service):
    """The About box states the running version so a user can tell which build
    they're on (surfaced dogfooding v0.1.0 — the About box showed no version)."""
    from finbreak import __version__

    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    window = MainWindow(service)
    qtbot.addWidget(window)

    text = window._about_text()
    assert __version__ in text, f"About text {text!r} omits version {__version__}"
    assert "finbreak" in text
