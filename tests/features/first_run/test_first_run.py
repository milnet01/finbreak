"""FIBR-0083 — first-run datetime prefs (INV-8). See spec.md.

Drives ``FirstRunDialog`` to its ``_on_derived`` persist site via a synchronous
``DeriveWorker`` stand-in (the real Argon2 derivation still runs; only the
QThread event-loop wait is skipped). Vault under ``tmp_path``; no network.
"""

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QCheckBox, QComboBox

from conftest import _PW
from finbreak.services.auth import AmountPrefs, AuthService, DateTimePrefs
from finbreak.ui._worker import DeriveWorker
from finbreak.ui.first_run import FirstRunDialog

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    yield svc
    svc.lock()


class _SyncDeriveWorker(DeriveWorker):
    """Runs the derivation inline and emits ``done`` from ``start()`` so the test
    drives ``_on_derived`` without a QThread event-loop wait (INV-8)."""

    def start(
        self, priority: QThread.Priority = QThread.Priority.InheritPriority
    ) -> None:
        self.run()


def _combos(dialog):
    return (
        dialog.findChild(QComboBox, "first_run_timezone"),
        dialog.findChild(QComboBox, "first_run_date_format"),
        dialog.findChild(QComboBox, "first_run_time_format"),
    )


def test_first_run_combos_prefilled_with_system_defaults(qtbot, service):
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    tz, date, time = _combos(dialog)
    assert tz is not None and date is not None and time is not None
    for combo in (tz, date, time):
        assert combo.currentData() == "system"


def test_first_run_persists_selected_datetime_prefs(qtbot, service, monkeypatch):
    import finbreak.ui.first_run as module

    monkeypatch.setattr(module, "DeriveWorker", _SyncDeriveWorker)
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    tz, date, time = _combos(dialog)
    tz.setCurrentIndex(tz.findData("Africa/Johannesburg"))
    date.setCurrentIndex(date.findData("yyyy/MM/dd"))
    time.setCurrentIndex(time.findData("HH:mm"))

    completed = []
    dialog.completed.connect(lambda: completed.append(True))
    dialog._password.setText(_PW.decode())
    dialog._confirm.setText(_PW.decode())
    dialog._submit.click()  # synchronous stub -> _on_derived runs inline

    assert completed == [True], "the vault was created and completed fired"
    assert service.datetime_prefs() == DateTimePrefs(
        "Africa/Johannesburg", "yyyy/MM/dd", "HH:mm"
    )


def test_first_run_cancel_never_persists(qtbot, service, monkeypatch):
    calls = []
    monkeypatch.setattr(
        AuthService, "set_datetime_prefs", lambda self, prefs: calls.append(prefs)
    )
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    dialog.reject()  # cancel with no derivation in flight -> no vault, no persist
    assert calls == [], "a cancelled first-run persists nothing"


# --------------------------------------------------------------------------- #
# FIBR-0105 — first-run amount controls (INV-7): pre-fill + persist-on-create
# --------------------------------------------------------------------------- #
def _amount_controls(dialog):
    return (
        dialog.findChild(QComboBox, "first_run_amount_negative"),
        dialog.findChild(QCheckBox, "first_run_amount_colour"),
    )


def test_first_run_amount_controls_prefilled_with_defaults(qtbot, service):
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    negative, colour = _amount_controls(dialog)
    assert negative is not None and colour is not None
    assert negative.currentData() == "minus"  # friendly default
    assert colour.isChecked()


def test_first_run_persists_selected_amount_prefs(qtbot, service, monkeypatch):
    import finbreak.ui.first_run as module

    monkeypatch.setattr(module, "DeriveWorker", _SyncDeriveWorker)
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    negative, colour = _amount_controls(dialog)
    negative.setCurrentIndex(negative.findData("brackets"))
    colour.setChecked(False)

    dialog._password.setText(_PW.decode())
    dialog._confirm.setText(_PW.decode())
    dialog._submit.click()  # synchronous stub -> _on_derived runs inline

    assert service.amount_prefs() == AmountPrefs("brackets", False)


def test_first_run_cancel_never_persists_amount(qtbot, service, monkeypatch):
    calls = []
    monkeypatch.setattr(
        AuthService, "set_amount_prefs", lambda self, prefs: calls.append(prefs)
    )
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    dialog.reject()
    assert calls == [], "a cancelled first-run persists no amount prefs"


# --------------------------------------------------------------------------- #
# FIBR-0367 audit row 33 — the vault exists before the display prefs are
# written. A prefs write failing after creation must not be reported as a
# failed creation: that drops the recovery code unseen and leaves a dialog
# whose retry refuses ("cannot first-run over an existing vault").
# --------------------------------------------------------------------------- #
def test_FIBR0367_prefs_failure_after_creation_keeps_the_recovery_code(
    qtbot, service, monkeypatch
):
    import finbreak.ui.first_run as module

    monkeypatch.setattr(module, "DeriveWorker", _SyncDeriveWorker)

    def _disk_full(self, prefs):
        raise OSError("disk full")

    monkeypatch.setattr(AuthService, "set_datetime_prefs", _disk_full)
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    codes: list[str] = []
    completed: list[bool] = []
    warnings: list[str] = []
    dialog.recovery_code_ready.connect(codes.append)
    dialog.completed.connect(lambda: completed.append(True))
    dialog.prefs_not_saved.connect(warnings.append)
    negative, _colour = _amount_controls(dialog)
    negative.setCurrentIndex(negative.findData("brackets"))

    dialog._password.setText(_PW.decode())
    dialog._confirm.setText(_PW.decode())
    dialog._submit.click()  # synchronous stub -> _on_derived runs inline

    assert service.vault.is_open, "precondition: the vault was created"
    assert len(codes) == 1 and codes[0], "the recovery code is handed over"
    assert completed == [True], "the shell is told the vault exists"
    assert len(warnings) == 1 and "could not be saved" in warnings[0]
    assert "disk full" not in warnings[0], "untranslated error text (FIBR-0395)"
    assert "could not create the vault" not in dialog._error.text().lower()
    assert service.amount_prefs().negative_style == "brackets", (
        "the amount prefs are still written when the datetime write fails"
    )


def test_FIBR0367_shell_shows_the_prefs_warning_after_first_run(
    qtbot, service, monkeypatch
):
    """End to end through the shell: the real first-run dialog, a failing
    prefs write, and what the user is left looking at."""
    import finbreak.ui.first_run as module
    from finbreak.ui.main_window import MainWindow
    from finbreak.ui.recovery_key import RecoveryCodeDialog

    monkeypatch.setattr(module, "DeriveWorker", _SyncDeriveWorker)

    def _disk_full(self, prefs):
        raise OSError("disk full")

    monkeypatch.setattr(AuthService, "set_datetime_prefs", _disk_full)
    window = MainWindow(service)  # no vault yet, so it opens first run
    qtbot.addWidget(window)
    first_run = window._dialog
    assert isinstance(first_run, FirstRunDialog), "precondition: first run"
    first_run._password.setText(_PW.decode())
    first_run._confirm.setText(_PW.decode())
    first_run._submit.click()  # synchronous stub -> _on_derived runs inline

    display = window._dialog
    assert isinstance(display, RecoveryCodeDialog), "the code is still shown"
    assert "could not be saved" in window.statusBar().currentMessage()
    display.reject()
    assert "could not be saved" in window.statusBar().currentMessage(), (
        "the warning outlives the recovery display"
    )
    window._enter_unlocked()
    assert "could not be saved" not in window.statusBar().currentMessage(), (
        "consumed on show, so a later unlock does not repeat it"
    )


# --------------------------------------------------------------------------- #
# FIBR-0395 — failures and refusals are told in translated words, never in the
# exception's own English text (design.md § i18n).
# --------------------------------------------------------------------------- #
_RAW = "RAW-ENGLISH-EXCEPTION-TEXT"


@pytest.mark.parametrize(
    ("password", "confirm", "expected"),
    [
        ("", "", "The password must not be empty."),
        ("one password", "another password", "The two passwords do not match."),
    ],
)
def test_FIBR0395_a_refused_password_is_told_in_translated_words(
    qtbot, service, password, confirm, expected
):
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    dialog._password.setText(password)
    dialog._confirm.setText(confirm)
    dialog._submit.click()
    assert dialog._error.text() == expected


def test_FIBR0395_the_service_names_each_refusal_by_type(service):
    from finbreak.errors import PasswordEmptyError, PasswordMismatchError

    with pytest.raises(PasswordEmptyError):
        service.validate_first_run(bytearray(), bytearray(), "ZAR")
    with pytest.raises(PasswordMismatchError):
        service.validate_first_run(bytearray(b"a"), bytearray(b"b"), "ZAR")


def test_FIBR0395_a_failed_creation_names_no_raw_error(qtbot, service, monkeypatch):
    import finbreak.ui.first_run as module

    monkeypatch.setattr(module, "DeriveWorker", _SyncDeriveWorker)

    def _fail(self, raw, params, currency):
        raise RuntimeError(_RAW)

    monkeypatch.setattr(AuthService, "complete_first_run", _fail)
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    dialog._password.setText(_PW.decode())
    dialog._confirm.setText(_PW.decode())
    dialog._submit.click()
    shown = dialog._error.text()
    assert "could not create the vault" in shown.lower()
    assert _RAW not in shown


def test_FIBR0395_a_failed_derivation_names_no_raw_error(qtbot, service):
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    dialog._on_failure(RuntimeError(_RAW))
    shown = dialog._error.text()
    assert "could not create the vault" in shown.lower()
    assert _RAW not in shown


def test_INV10_first_run_refuses_a_typed_zone_that_names_no_zone(
    qtbot, service, monkeypatch
):
    """FIBR-0435 — the same refusal on first run, before any key derivation or
    vault creation starts (FIBR-0083 INV-10)."""
    import finbreak.ui.first_run as module

    started: list[bool] = []

    class _Spy(_SyncDeriveWorker):
        def start(self, priority=QThread.Priority.InheritPriority) -> None:
            started.append(True)

    monkeypatch.setattr(module, "DeriveWorker", _Spy)
    writes: list[object] = []
    monkeypatch.setattr(service, "set_datetime_prefs", writes.append)
    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    tz, _date, _time = _combos(dialog)
    tz.setCurrentText("Not/AZone")
    dialog._password.setText(_PW.decode())
    dialog._confirm.setText(_PW.decode())

    dialog._submit.click()

    assert started == [], "no derivation may start"
    assert writes == []
    assert "time zone" in dialog._error.text().lower(), dialog._error.text()
