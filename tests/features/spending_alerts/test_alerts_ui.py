"""FIBR-0185 — the Home Alerts button + AlertsDialog (qtbot).

Supersedes the FIBR-0172 inline alerts card. The card's height varied with the
alert count, so the whole dashboard shifted whenever one appeared or was
dismissed; the alerts now sit behind a fixed-height button that carries the count
and opens a dialog. The FIBR-0172 dismiss contract (INV-18: calls
``AlertService.dismiss`` inside a ``VaultLockedError``-silent guard, then rebuilds
in place) is unchanged — it just lives in the dialog now.

The view renders with ``date.today()`` (FIBR-0172 D8), so the fixtures seed
recurring charges relative to today. Offscreen Qt (conftest); no network, no real
financial data (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QPushButton, QWidget

from conftest import _PW
from finbreak.errors import VaultLockedError
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.alerts import AlertService
from finbreak.services.auth import AuthService
from finbreak.services.month_summary import MonthSummaryService
from finbreak.services.recurring import RecurringService
from finbreak.services.reporting import ReportingService
from finbreak.services.transactions import read_minor_unit_exponent
from finbreak.ui.alerts_dialog import AlertsDialog

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _acct(svc: AuthService) -> int:
    return AccountService(svc.vault).list_accounts()[0].id


def _add(svc: AuthService, day: str, minor: int, desc: str) -> None:
    TransactionRepository(svc.vault.connection).add(_acct(svc), day, minor, desc)


def _home(svc: AuthService, alerts: AlertService):
    from finbreak.ui.home import HomeView

    return HomeView(
        ReportingService(svc.vault),
        AccountService(svc.vault),
        svc,
        RecurringService(svc.vault),
        alerts,
        MonthSummaryService(svc.vault),
    )


def _dialog(svc: AuthService, alerts: AlertService) -> AlertsDialog:
    return AlertsDialog(
        alerts,
        ReportingService(svc.vault).base_currency(),
        read_minor_unit_exponent(svc.vault.connection),
    )


def _seed_one_new_recurring(svc: AuthService) -> None:
    """Three monthly OUT charges ending today: a suggested OUT stream (occurrences 3)
    -> exactly one new-recurring alert, regardless of the date the test runs."""
    today = date.today()
    for offset in (60, 30, 0):
        _add(svc, (today - timedelta(days=offset)).isoformat(), -9_999, "Spotify")


def _dismiss_buttons(root) -> list[QPushButton]:
    return [
        b for b in root.findChildren(QPushButton) if b.objectName() == "alert_dismiss"
    ]


def _alerts_button(home) -> QPushButton:
    button = home.findChild(QPushButton, "alerts_button")
    assert button is not None
    return button


# --------------------------------------------------------------------------- #
# The Home button — the dashboard's whole alert surface
# --------------------------------------------------------------------------- #
def test_button_is_quiet_and_disabled_when_no_alerts(qtbot, service) -> None:
    # A lone transaction: the dashboard renders, but nothing raises an alert.
    _add(service, (date.today() - timedelta(days=5)).isoformat(), -5_000, "One-off")
    home = _home(service, AlertService(service.vault))
    qtbot.addWidget(home)

    button = _alerts_button(home)
    assert button.text() == "Alerts"  # no count when there is nothing to count
    assert not button.isEnabled()


def test_button_carries_the_count_and_enables_when_alerts(qtbot, service) -> None:
    _seed_one_new_recurring(service)
    home = _home(service, AlertService(service.vault))
    qtbot.addWidget(home)

    button = _alerts_button(home)
    assert button.text() == "Alerts (1)"
    assert button.isEnabled()


def test_button_click_asks_the_shell_to_open_the_dialog(qtbot, service) -> None:
    _seed_one_new_recurring(service)
    home = _home(service, AlertService(service.vault))
    qtbot.addWidget(home)

    with qtbot.waitSignal(home.alerts_requested, timeout=1000):
        _alerts_button(home).click()


def test_dashboard_no_longer_holds_an_inline_alerts_card(qtbot, service) -> None:
    """The regression this item exists for: nothing on the dashboard grows or
    shrinks with the alert count, so the layout below can't be shoved around."""
    _seed_one_new_recurring(service)
    home = _home(service, AlertService(service.vault))
    qtbot.addWidget(home)

    assert home.findChild(QWidget, "dashboard_alerts") is None
    assert _dismiss_buttons(home) == []


def test_refresh_alerts_re_reads_the_count(qtbot, service) -> None:
    """What the shell calls after a dismiss inside the dialog."""
    _seed_one_new_recurring(service)
    alerts = AlertService(service.vault)
    home = _home(service, alerts)
    qtbot.addWidget(home)
    assert _alerts_button(home).text() == "Alerts (1)"

    alerts.dismiss("new_recurring:spotify")
    home.refresh_alerts()

    assert _alerts_button(home).text() == "Alerts"
    assert not _alerts_button(home).isEnabled()


def test_refresh_alerts_is_vault_locked_silent(qtbot, service, monkeypatch) -> None:
    _seed_one_new_recurring(service)
    alerts = AlertService(service.vault)
    home = _home(service, alerts)
    qtbot.addWidget(home)

    def boom(today: date) -> list:
        raise VaultLockedError("auto-lock fired mid-render")

    monkeypatch.setattr(alerts, "alerts", boom)
    home.refresh_alerts()  # must NOT raise — the dashboard is being torn down

    assert not _alerts_button(home).isEnabled()


# --------------------------------------------------------------------------- #
# The dialog — the FIBR-0172 rows + dismiss contract, rehomed
# --------------------------------------------------------------------------- #
def test_dialog_shows_one_row_per_alert(qtbot, service) -> None:
    _seed_one_new_recurring(service)
    dialog = _dialog(service, AlertService(service.vault))
    qtbot.addWidget(dialog)

    assert len(_dismiss_buttons(dialog)) == 1
    empty = dialog.findChild(QWidget, "alerts_empty")
    assert empty is not None and empty.isHidden()


def test_dialog_dismiss_calls_service_rebuilds_and_announces(
    qtbot, service, monkeypatch
) -> None:
    _seed_one_new_recurring(service)
    alerts = AlertService(service.vault)
    calls: list[str] = []
    real = alerts.dismiss

    def spy(key: str) -> None:
        calls.append(key)
        real(key)

    monkeypatch.setattr(alerts, "dismiss", spy)
    dialog = _dialog(service, alerts)
    qtbot.addWidget(dialog)

    buttons = _dismiss_buttons(dialog)
    assert len(buttons) == 1
    with qtbot.waitSignal(dialog.changed, timeout=1000):
        buttons[0].click()

    assert calls == ["new_recurring:spotify"]
    # Rebuilt in place: the row is gone and the dialog says so rather than closing.
    assert _dismiss_buttons(dialog) == []
    empty = dialog.findChild(QWidget, "alerts_empty")
    assert empty is not None and not empty.isHidden()


def test_FIBR0216_dismiss_buttons_are_individually_named(qtbot, service) -> None:
    """FIBR-0216 — the dismiss control was a bare `tr("✕")` with no accessible name,
    so a screen reader announced N identically-unnamed buttons (WCAG 4.1.2) and a
    translator got a glyph with no context to work from. The glyph is data now; the
    accessible name is the translated part and says WHICH alert it dismisses."""
    _seed_one_new_recurring(service)
    dialog = _dialog(service, AlertService(service.vault))
    qtbot.addWidget(dialog)

    (button,) = _dismiss_buttons(dialog)
    assert button.accessibleName(), "the dismiss control has an accessible name"
    assert "Spotify".lower() in button.accessibleName().lower(), (
        "and it identifies the alert it acts on, not just 'Dismiss'"
    )
    assert button.toolTip() == button.accessibleName()


def test_FIBR0216_dismiss_computes_the_alert_set_once_not_twice(
    qtbot, service, monkeypatch
) -> None:
    """FIBR-0216 — a dismiss re-renders the dialog's rows (computing the alert set)
    and then Home's `refresh_alerts` computed the identical set again for its count:
    two full unfiltered transaction scans plus two recurring-detection passes per
    click. `changed` now carries the count the dialog already holds."""
    _seed_one_new_recurring(service)
    alerts = AlertService(service.vault)
    real = alerts.alerts
    calls: list[object] = []

    def counting(today):
        calls.append(today)
        return real(today)

    monkeypatch.setattr(alerts, "alerts", counting)
    dialog = _dialog(service, alerts)
    qtbot.addWidget(dialog)

    calls.clear()  # ignore the build-time render
    received: list[int] = []
    dialog.changed.connect(received.append)
    with qtbot.waitSignal(dialog.changed, timeout=1000):
        _dismiss_buttons(dialog)[0].click()

    assert len(calls) == 1, (
        f"the alert set is computed once per dismiss, not {len(calls)}"
    )
    assert received == [0], "and `changed` carries the remaining count for Home"


def test_dialog_dismiss_is_vault_locked_silent(qtbot, service, monkeypatch) -> None:
    _seed_one_new_recurring(service)
    alerts = AlertService(service.vault)

    def boom(key: str) -> None:
        raise VaultLockedError("auto-lock fired mid-click")

    monkeypatch.setattr(alerts, "dismiss", boom)
    dialog = _dialog(service, alerts)
    qtbot.addWidget(dialog)

    buttons = _dismiss_buttons(dialog)
    assert len(buttons) == 1
    buttons[0].click()  # must NOT raise — the handler swallows VaultLockedError
    # The dismiss failed, so the row is still present.
    assert len(_dismiss_buttons(dialog)) == 1
