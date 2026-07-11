"""FIBR-0055 — Settings screen (configurable auto-lock timeout).

Enforces tests/features/settings/spec.md. Service-level legs (INV-1..5, INV-7
defence-in-depth, D6) run headless against ``AuthService`` + ``SettingsRepository``;
the UI legs (INV-6..9) drive the shell + ``SettingsDialog`` via ``qtbot``. Every
vault lives under ``tmp_path``; no network, no real data.
"""

from dataclasses import FrozenInstanceError

import pytest
import shiboken6
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
)

from conftest import _PW
from finbreak.errors import VaultLockedError
from finbreak.repositories.settings import SettingsRepository
from finbreak.services.auth import (
    ALLOWED_AUTO_LOCK_MINUTES,
    DEFAULT_AUTO_LOCK_MINUTES,
    AmountPrefs,
    AuthService,
    DateTimePrefs,
)
from finbreak.services.transactions import TransactionService
from finbreak.ui.main_window import MainWindow
from finbreak.ui.settings import SettingsDialog

pytestmark = pytest.mark.features


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
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
    # Pinned to the auto-lock combo by objectName — the dialog now holds several
    # combos (FIBR-0083 added timezone/date/time), so a bare findChild is ambiguous.
    combo = dialog.findChild(QComboBox, "settings_auto_lock")
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
    # Currency stays a read-only QLabel; the only edit field in the dialog is the
    # FIBR-0083 editable timezone combo's internal search box (type-to-search).
    timezone = dialog.findChild(QComboBox, "settings_timezone")
    assert dialog.findChildren(QLineEdit) == [timezone.lineEdit()], (
        "currency is read-only, no edit field of its own"
    )


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


def test_on_save_swallows_vault_locked_silently(qtbot, service, monkeypatch):
    """An auto-lock while Settings is open must not crash Save. (UI-dialogs H1)"""
    from finbreak.errors import VaultLockedError
    from finbreak.ui.settings import SettingsDialog

    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    saved = []
    dialog.saved.connect(lambda: saved.append(True))

    def locked(*a, **k):
        raise VaultLockedError("the vault is locked")

    monkeypatch.setattr(dialog._service, "set_auto_lock_minutes", locked)
    dialog._on_save()  # must not raise
    assert saved == [], "saved is not emitted on a locked vault"


# --------------------------------------------------------------------------- #
# FIBR-0083 — datetime prefs round-trip (INV-5): timezone/date_format/time_format
# --------------------------------------------------------------------------- #
def test_datetime_prefs_default_to_system_when_absent(service):
    assert service.datetime_prefs() == DateTimePrefs("system", "system", "system")


def test_datetime_prefs_round_trip(service):
    prefs = DateTimePrefs("Africa/Johannesburg", "yyyy/MM/dd", "HH:mm")
    service.set_datetime_prefs(prefs)
    assert service.datetime_prefs() == prefs


def test_datetime_prefs_each_key_defaults_independently(service):
    # Only the timezone key present -> the other two still resolve to "system".
    SettingsRepository(service.vault.connection).set("timezone", "Europe/Paris")
    assert service.datetime_prefs() == DateTimePrefs("Europe/Paris", "system", "system")


def test_set_datetime_prefs_writes_the_three_named_keys(service):
    service.set_datetime_prefs(DateTimePrefs("UTC", "dd/MM/yyyy", "h:mm AP"))
    repo = SettingsRepository(service.vault.connection)
    assert repo.get("timezone") == "UTC"
    assert repo.get("date_format") == "dd/MM/yyyy"
    assert repo.get("time_format") == "h:mm AP"


def test_datetime_prefs_is_frozen(service):
    prefs = service.datetime_prefs()
    with pytest.raises(FrozenInstanceError):
        prefs.timezone = "UTC"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# FIBR-0105 — amount display prefs round-trip (INV-2/5): sign style + colour
# --------------------------------------------------------------------------- #
def test_amount_prefs_default_when_absent(service):
    # Fresh / pre-FIBR-0105 vault -> friendly default: minus + colour ON.
    assert service.amount_prefs() == AmountPrefs("minus", True)


def test_amount_prefs_round_trip(service):
    prefs = AmountPrefs("brackets", False)
    service.set_amount_prefs(prefs)
    assert service.amount_prefs() == prefs


def test_set_amount_prefs_writes_the_named_keys(service):
    service.set_amount_prefs(AmountPrefs("brackets", False))
    repo = SettingsRepository(service.vault.connection)
    assert repo.get("amount_negative_style") == "brackets"
    assert repo.get("amount_colour") == "false"  # bool -> "true"/"false" token


def test_amount_prefs_bad_negative_style_falls_back_to_minus(service):
    # INV-5: an unknown stored sign style resolves to the default, never crashes.
    SettingsRepository(service.vault.connection).set(
        "amount_negative_style", "octagons"
    )
    assert service.amount_prefs().negative_style == "minus"


def test_amount_prefs_bad_colour_falls_back_to_true(service):
    # INV-5: an unknown stored colour token resolves to ON (True), independently.
    SettingsRepository(service.vault.connection).set("amount_colour", "maybe")
    assert service.amount_prefs().colour is True


def test_amount_prefs_is_frozen(service):
    prefs = service.amount_prefs()
    with pytest.raises(FrozenInstanceError):
        prefs.colour = False  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# FIBR-0105 — the Settings amount sign combo + colour checkbox (qtbot)
# --------------------------------------------------------------------------- #
def _amount_controls(dialog):
    return (
        dialog.findChild(QComboBox, "settings_amount_negative"),
        dialog.findChild(QCheckBox, "settings_amount_colour"),
    )


def test_amount_controls_present_and_default(qtbot, service):
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    negative, colour = _amount_controls(dialog)
    assert negative is not None and colour is not None
    # Fresh vault -> the friendly default: minus preselected, colour ON.
    assert negative.currentData() == "minus"
    assert colour.isChecked()
    # Both styles are offered as data-carrying items.
    assert {negative.itemData(i) for i in range(negative.count())} == {
        "minus",
        "brackets",
    }


def test_amount_controls_preselect_current_prefs(qtbot, service):
    service.set_amount_prefs(AmountPrefs("brackets", False))
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    negative, colour = _amount_controls(dialog)
    assert negative.currentData() == "brackets"
    assert not colour.isChecked()


def test_amount_controls_persist_on_save(qtbot, service):
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    negative, colour = _amount_controls(dialog)
    negative.setCurrentIndex(negative.findData("brackets"))
    colour.setChecked(False)
    dialog._on_save()
    assert service.amount_prefs() == AmountPrefs("brackets", False)


# --------------------------------------------------------------------------- #
# FIBR-0083 — the Settings timezone/date/time combos (qtbot)
# --------------------------------------------------------------------------- #
def _dt_combos(dialog):
    return (
        dialog.findChild(QComboBox, "settings_timezone"),
        dialog.findChild(QComboBox, "settings_date_format"),
        dialog.findChild(QComboBox, "settings_time_format"),
    )


def test_datetime_combos_present_and_default_to_system(qtbot, service):
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    tz, date, time = _dt_combos(dialog)
    assert tz is not None and date is not None and time is not None
    # each combo's first item is the System sentinel, preselected on a fresh vault
    for combo in (tz, date, time):
        assert combo.itemData(0) == "system"
        assert combo.currentData() == "system"
    # only the timezone combo is editable (type-to-search over 643 ids)
    assert tz.isEditable()
    assert not date.isEditable() and not time.isEditable()


def test_datetime_combos_preselect_current_prefs(qtbot, service):
    service.set_datetime_prefs(
        DateTimePrefs("Africa/Johannesburg", "yyyy/MM/dd", "HH:mm")
    )
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    tz, date, time = _dt_combos(dialog)
    assert tz.currentData() == "Africa/Johannesburg"
    assert date.currentData() == "yyyy/MM/dd"
    assert time.currentData() == "HH:mm"


def test_datetime_combos_persist_selection_on_save(qtbot, service):
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    tz, date, time = _dt_combos(dialog)
    tz.setCurrentIndex(tz.findData("Africa/Johannesburg"))
    date.setCurrentIndex(date.findData("yyyy/MM/dd"))
    time.setCurrentIndex(time.findData("HH:mm"))
    dialog._on_save()
    assert service.datetime_prefs() == DateTimePrefs(
        "Africa/Johannesburg", "yyyy/MM/dd", "HH:mm"
    )


def test_datetime_freetyped_valid_zone_recovered_on_save(qtbot, service):
    # A real id typed into the editable combo without clicking the list (D4
    # "override to pin") leaves currentData() non-str -> recover via currentText().
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    tz, _date, _time = _dt_combos(dialog)
    tz.setCurrentIndex(-1)
    tz.setEditText("Europe/Paris")
    dialog._on_save()
    assert service.datetime_prefs().timezone == "Europe/Paris"


def test_datetime_freetyped_garbage_zone_falls_back_to_system(qtbot, service):
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    tz, _date, _time = _dt_combos(dialog)
    tz.setCurrentIndex(-1)
    tz.setEditText("Not A Zone")
    dialog._on_save()
    assert service.datetime_prefs().timezone == "system"
