"""FIBR-0172 — the Home dashboard AlertsCard (qtbot).

Enforces spec INV-17/INV-18: the card is hidden when ``alerts(today)`` is empty and
shows one row per alert when non-empty; a Dismiss click calls ``AlertService.dismiss``
inside a ``VaultLockedError``-silent guard, then rebuilds only the card (the row is
gone / card hidden if now empty). The view renders with ``date.today()`` (D8), so the
fixtures seed recurring charges relative to today. Offscreen Qt (conftest); no
network, no real financial data (testing.md § 6).
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
from finbreak.services.recurring import RecurringService
from finbreak.services.reporting import ReportingService

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
    )


def _seed_one_new_recurring(svc: AuthService) -> None:
    """Three monthly OUT charges ending today: a suggested OUT stream (occurrences 3)
    -> exactly one new-recurring alert, regardless of the date the test runs."""
    today = date.today()
    for offset in (60, 30, 0):
        _add(svc, (today - timedelta(days=offset)).isoformat(), -9_999, "Spotify")


def _dismiss_buttons(home) -> list[QPushButton]:
    return [
        b for b in home.findChildren(QPushButton) if b.objectName() == "alert_dismiss"
    ]


def test_INV17_card_hidden_when_no_alerts(qtbot, service) -> None:
    # A lone transaction: the dashboard renders, but nothing raises an alert.
    _add(service, (date.today() - timedelta(days=5)).isoformat(), -5_000, "One-off")
    home = _home(service, AlertService(service.vault))
    qtbot.addWidget(home)
    card = home.findChild(QWidget, "dashboard_alerts")
    assert card is not None
    assert card.isHidden()
    assert _dismiss_buttons(home) == []


def test_INV17_card_shows_one_row_per_alert(qtbot, service) -> None:
    _seed_one_new_recurring(service)
    home = _home(service, AlertService(service.vault))
    qtbot.addWidget(home)
    card = home.findChild(QWidget, "dashboard_alerts")
    assert card is not None
    assert not card.isHidden()
    assert len(_dismiss_buttons(home)) == 1


def test_INV18_dismiss_click_calls_service_and_rebuilds(
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
    home = _home(service, alerts)
    qtbot.addWidget(home)

    buttons = _dismiss_buttons(home)
    assert len(buttons) == 1
    buttons[0].click()

    assert calls == ["new_recurring:spotify"]
    # Card-local rebuild: the row is gone and the now-empty card is hidden.
    card = home.findChild(QWidget, "dashboard_alerts")
    assert card is not None
    assert card.isHidden()
    assert _dismiss_buttons(home) == []


def test_INV18_dismiss_is_vault_locked_silent(qtbot, service, monkeypatch) -> None:
    _seed_one_new_recurring(service)
    alerts = AlertService(service.vault)

    def boom(key: str) -> None:
        raise VaultLockedError("auto-lock fired mid-click")

    monkeypatch.setattr(alerts, "dismiss", boom)
    home = _home(service, alerts)
    qtbot.addWidget(home)

    buttons = _dismiss_buttons(home)
    assert len(buttons) == 1
    buttons[0].click()  # must NOT raise — the handler swallows VaultLockedError
    # The dismiss failed, so the row is still present.
    assert len(_dismiss_buttons(home)) == 1
