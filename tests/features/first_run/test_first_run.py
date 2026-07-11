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
