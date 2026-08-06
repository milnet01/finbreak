"""FIBR-0186 — the dashboard stops squashing; it scrolls (qtbot).

The dashboard content already lived in a ``QScrollArea`` (FIBR-0012 D1), but with
no floor under it: a narrow window squeezed the three donut columns into
unreadable slivers instead of scrolling. The content widget now carries a MINIMUM
size — not per-widget fixed sizes, which would clip text for anyone running a
larger system font or display scaling. Offscreen Qt (conftest); no network, no
real financial data (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QScrollArea, QWidget

from conftest import _PW
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.alerts import AlertService
from finbreak.services.auth import AuthService
from finbreak.services.month_summary import MonthSummaryService
from finbreak.services.recurring import RecurringService
from finbreak.services.reporting import ReportingService

pytestmark = pytest.mark.features

_MIN_W, _MIN_H = 880, 620


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _home(svc: AuthService):
    from finbreak.ui.home import HomeView

    account = AccountService(svc.vault).list_accounts()[0].id
    TransactionRepository(svc.vault.connection).add(
        account, (date.today() - timedelta(days=5)).isoformat(), -5_000, "Coffee"
    )
    return HomeView(
        ReportingService(svc.vault),
        AccountService(svc.vault),
        svc,
        RecurringService(svc.vault),
        AlertService(svc.vault),
        MonthSummaryService(svc.vault),
    )


def _content(home) -> QWidget:
    content = home.findChild(QWidget, "dashboard_content")
    assert content is not None
    return content


def _scroll(home) -> QScrollArea:
    scroll = home.findChild(QScrollArea)
    assert scroll is not None
    return scroll


def test_content_carries_a_readable_minimum(qtbot, service) -> None:
    home = _home(service)
    qtbot.addWidget(home)
    content = _content(home)

    assert content.minimumWidth() >= _MIN_W
    assert content.minimumHeight() >= _MIN_H
    # A minimum, not a fixed size: the content must still be free to GROW (larger
    # system fonts, a maximised window) rather than clip.
    assert content.maximumWidth() > _MIN_W


def test_a_too_small_window_scrolls_instead_of_squashing(qtbot, service) -> None:
    home = _home(service)
    qtbot.addWidget(home)
    home.resize(400, 300)
    home.show()
    qtbot.waitExposed(home)

    content = _content(home)
    assert content.width() >= _MIN_W  # the columns keep their readable width
    assert content.height() >= _MIN_H
    # ...which is only tolerable because the viewport can be scrolled to the rest.
    scroll = _scroll(home)
    assert scroll.horizontalScrollBar().maximum() > 0
    assert scroll.verticalScrollBar().maximum() > 0


def test_the_minimum_does_not_pin_the_window_open(qtbot, service) -> None:
    """The floor is on the scrolled content, not on HomeView — otherwise it would
    stop the user shrinking the window at all, which is the opposite of the ask."""
    home = _home(service)
    qtbot.addWidget(home)

    assert home.minimumSizeHint().width() < _MIN_W
