"""FIBR-0055 — Settings screen (configurable auto-lock timeout).

Enforces tests/features/settings/spec.md. Service-level legs (INV-1..5, INV-7
defence-in-depth, D6) run headless against ``AuthService`` + ``SettingsRepository``;
the UI legs (INV-6..9) drive the shell + ``SettingsDialog`` via ``qtbot``. Every
vault lives under ``tmp_path``; no network, no real data.
"""

import pytest
import shiboken6
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
)

from finbreak.errors import VaultLockedError
from finbreak.repositories.settings import SettingsRepository
from finbreak.services.auth import (
    ALLOWED_AUTO_LOCK_MINUTES,
    DEFAULT_AUTO_LOCK_MINUTES,
    AuthService,
)
from finbreak.services.transactions import TransactionService
from finbreak.ui.main_window import MainWindow
from finbreak.ui.settings import SettingsDialog

pytestmark = pytest.mark.features

_PW = b"correct horse battery staple"


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def paths(tmp_path):
    return tmp_path / "vault.db", tmp_path / "vault.kdf.json"


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to latest
    yield svc
    svc.lock()


def _shell(qtbot, service) -> MainWindow:
    """An unlocked MainWindow driven past routing, as a real unlock success does."""
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    return window


def _combo(dialog: SettingsDialog) -> QComboBox:
    combo = dialog.findChild(QComboBox)
    assert combo is not None
    return combo


def _click_save(dialog: SettingsDialog) -> None:
    box = dialog.findChild(QDialogButtonBox)
    assert box is not None
    box.button(QDialogButtonBox.StandardButton.Ok).click()


def _click_cancel(dialog: SettingsDialog) -> None:
    box = dialog.findChild(QDialogButtonBox)
    assert box is not None
    box.button(QDialogButtonBox.StandardButton.Cancel).click()


# --------------------------------------------------------------------------- #
# INV-1 — auto_lock_minutes() reads the vault with a guarded default
# --------------------------------------------------------------------------- #
def test_INV1_default_when_absent(service):
    assert service.auto_lock_minutes() == DEFAULT_AUTO_LOCK_MINUTES == 10


def test_INV1_reads_stored_valid(service):
    SettingsRepository(service.vault.connection).set("auto_lock_minutes", "5")
    assert service.auto_lock_minutes() == 5


def test_INV1_non_integer_falls_back(service):
    SettingsRepository(service.vault.connection).set("auto_lock_minutes", "abc")
    assert service.auto_lock_minutes() == 10


def test_INV1_out_of_set_falls_back(service):
    # 7 parses as an int but is not an offered choice -> secure default.
    SettingsRepository(service.vault.connection).set("auto_lock_minutes", "7")
    assert service.auto_lock_minutes() == 10


# --------------------------------------------------------------------------- #
# INV-2 — set_auto_lock_minutes validates, persists, re-arms (in that order)
# --------------------------------------------------------------------------- #
def test_INV2_invalid_rejected(service, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_arm_timer", lambda: calls.append(1))
    before = service.auto_lock_minutes()
    with pytest.raises(ValueError):
        service.set_auto_lock_minutes(7)  # 7 not in ALLOWED
    assert service.auto_lock_minutes() == before, "no write on a rejected value"
    assert calls == [], "the timer is not re-armed on rejection"


def test_INV2_valid_persists_and_rearms(service, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_arm_timer", lambda: calls.append(1))
    service.set_auto_lock_minutes(5)
    assert service.auto_lock_minutes() == 5
    assert calls == [1], "a valid change re-arms the timer once"


# --------------------------------------------------------------------------- #
# INV-3 — the persisted value drives the live idle timer
# --------------------------------------------------------------------------- #
def test_INV3_arm_timer_uses_value(qtbot, service):
    # qtbot guarantees a live QApplication, so _arm_timer actually starts a QTimer.
    service.set_auto_lock_minutes(1)
    assert service._timer is not None
    assert service._timer.interval() == 1 * 60 * 1000


# --------------------------------------------------------------------------- #
# INV-4 — the setting persists across a lock/unlock cycle and a real restart
# --------------------------------------------------------------------------- #
def test_INV4_persists_across_lock_unlock(service):
    service.set_auto_lock_minutes(15)
    service.lock()
    assert service.unlock(bytearray(_PW)) is True
    assert service.auto_lock_minutes() == 15


def test_INV4_persists_across_fresh_authservice(service, paths):
    service.set_auto_lock_minutes(30)
    service.lock()
    fresh = AuthService(*paths)  # a real restart: new service over the same files
    assert fresh.unlock(bytearray(_PW)) is True
    try:
        assert fresh.auto_lock_minutes() == 30
    finally:
        fresh.lock()


# --------------------------------------------------------------------------- #
# INV-5 — a fresh first_run vault has no row and reports the default
# --------------------------------------------------------------------------- #
def test_INV5_fresh_first_run_reports_default(service):
    row = service.vault.connection.execute(
        "SELECT value FROM settings WHERE key = 'auto_lock_minutes'"
    ).fetchone()
    assert row is None, "no auto_lock_minutes row until the user changes it"
    assert service.auto_lock_minutes() == 10


# --------------------------------------------------------------------------- #
# INV-7 (defence in depth) — set on a locked vault raises
# --------------------------------------------------------------------------- #
def test_INV7_set_on_locked_raises(service):
    service.lock()
    with pytest.raises(VaultLockedError):
        service.set_auto_lock_minutes(5)  # valid n, so the closed conn is reached


# --------------------------------------------------------------------------- #
# D6 — the default is itself an offered choice
# --------------------------------------------------------------------------- #
def test_D6_default_in_allowed():
    assert DEFAULT_AUTO_LOCK_MINUTES in ALLOWED_AUTO_LOCK_MINUTES


# --------------------------------------------------------------------------- #
# INV-6 — the Settings action is vault-dependent chrome
# --------------------------------------------------------------------------- #
def test_INV6_settings_action_vault_dependent(qtbot, service):
    window = _shell(qtbot, service)
    assert window._action_settings in window._menu_file.actions()
    assert window._menu_file.isEnabled(), "File menu enabled while unlocked"
    window._action_lock.trigger()
    assert not window._menu_file.isEnabled(), "File menu disabled on lock"


# --------------------------------------------------------------------------- #
# INV-7 — an idle auto-lock tears down an open Settings dialog
# --------------------------------------------------------------------------- #
def test_INV7_autolock_tears_down_settings(qtbot, service):
    window = _shell(qtbot, service)
    window._action_settings.trigger()
    dialog = window._dialog
    assert isinstance(dialog, SettingsDialog)
    service._on_idle_timeout()  # the real auto-lock path (invokes on_auto_lock=_lock)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # The Settings dialog is destroyed on lock; the lock then re-opens an
    # UnlockDialog into _dialog, so the check is on the captured Settings ref.
    assert not shiboken6.isValid(dialog), "the Settings dialog was destroyed on lock"
    assert not isinstance(window._dialog, SettingsDialog)


# --------------------------------------------------------------------------- #
# INV-8 — the dialog reflects current values, offers only allowed choices
# --------------------------------------------------------------------------- #
def test_INV8_preselect_and_readonly_currency(qtbot, service):
    service.set_auto_lock_minutes(15)
    window = _shell(qtbot, service)
    window._action_settings.trigger()
    dialog = window._dialog

    combo = _combo(dialog)
    assert combo.currentData() == 15
    assert [combo.itemData(i) for i in range(combo.count())] == list(
        ALLOWED_AUTO_LOCK_MINUTES
    )

    currency = dialog.findChild(QLabel, "settings_currency")
    assert currency is not None and "ZAR" in currency.text()
    assert dialog.findChild(QLineEdit) is None, "currency is read-only, no edit field"


def test_INV8_out_of_set_preselects_default(qtbot, service):
    SettingsRepository(service.vault.connection).set("auto_lock_minutes", "7")
    window = _shell(qtbot, service)
    window._action_settings.trigger()
    assert _combo(window._dialog).currentData() == 10


# --------------------------------------------------------------------------- #
# INV-9 — Save applies + closes via the service; Cancel changes nothing
# --------------------------------------------------------------------------- #
def test_INV9_save_persists_and_closes(qtbot, service):
    window = _shell(qtbot, service)
    window._action_settings.trigger()
    dialog = window._dialog
    combo = _combo(dialog)
    combo.setCurrentIndex(combo.findData(30))
    with qtbot.waitSignal(dialog.saved):
        _click_save(dialog)
    assert service.auto_lock_minutes() == 30
    assert window._dialog is None, "the shell tears the dialog down on save"


def test_INV9_cancel_changes_nothing(qtbot, service):
    service.set_auto_lock_minutes(5)
    window = _shell(qtbot, service)
    window._action_settings.trigger()
    dialog = window._dialog
    fired = []
    dialog.saved.connect(lambda: fired.append(1))
    combo = _combo(dialog)
    combo.setCurrentIndex(combo.findData(30))
    _click_cancel(dialog)  # drive the real Cancel button (its rejected->reject wiring)
    assert service.auto_lock_minutes() == 5, "cancel writes nothing"
    assert fired == [], "cancel does not emit saved"
    assert window._dialog is None, "cancel tears the dialog down"


def test_INV9_shell_passes_real_currency(qtbot, service):
    # The shell reads TransactionService.base_currency() and hands it to the dialog.
    assert TransactionService(service.vault).base_currency() == "ZAR"
    window = _shell(qtbot, service)
    window._action_settings.trigger()
    currency = window._dialog.findChild(QLabel, "settings_currency")
    assert "ZAR" in currency.text()
