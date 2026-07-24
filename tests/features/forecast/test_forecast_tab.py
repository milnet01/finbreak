"""FIBR-0171 — the Forecast tab (spec D9/D10, Deliverables 11/13).

`ForecastWidget(service: AuthService)` mirrors `RecurringWidget`: a headline, an
anchor-provenance line, a horizon picker, a themed line chart, and an
upcoming-events table. Enforces tests/features/forecast/spec.md INV-10 (+ headline
/ provenance reflect the mode). Uses the pytest-qt `qtbot` fixture; tmp_path only.
"""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest

from conftest import _PW
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.recurring import RecurringService
from finbreak.ui.forecast import ForecastWidget

pytestmark = pytest.mark.features


@pytest.fixture
def vault_service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _acct(svc: AuthService) -> int:
    return AccountService(svc.vault).list_accounts()[0].id


def _seed_anchored(svc: AuthService) -> None:
    today = date.today()
    a = _acct(svc)
    repo = StatementPeriodRepository(svc.vault.connection)
    repo.add(
        a,
        (today - timedelta(days=200)).isoformat(),
        (today - timedelta(days=40)).isoformat(),
        "stmt.pdf",
        500_000,
    )
    svc.vault.connection.commit()
    # A recent monthly series (last charge today) -> confirmed -> projects forward.
    txn = TransactionRepository(svc.vault.connection)
    for k in range(5):
        txn.add(a, (today - timedelta(days=30 * k)).isoformat(), -19_900, "Netflix")
    rec = RecurringService(svc.vault)
    item = next(it for it in rec.candidates(today) if it.merchant_key == "netflix")
    rec.confirm(item.direction, item.merchant_key)


# --------------------------------------------------------------------------- #
# INV-10 — the tab exists after Recurring and renders on an empty vault
# --------------------------------------------------------------------------- #
def test_INV10_tab_present_after_recurring(qtbot, vault_service) -> None:
    from finbreak.ui.main_window import MainWindow

    window = MainWindow(vault_service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    workspace = window._workspace
    assert workspace is not None
    tabs = [workspace.widget(i) for i in range(workspace.count())]
    assert all(t is not None for t in tabs)
    names = [t.objectName() for t in tabs if t is not None]
    assert names[-1] == "tab_forecast"
    assert names.index("tab_forecast") == names.index("tab_recurring") + 1


def test_INV10_empty_vault_renders_net_flow_without_crashing(
    qtbot, vault_service
) -> None:
    w = ForecastWidget(vault_service)
    qtbot.addWidget(w)
    assert w.objectName() == "tab_forecast"
    # NET_FLOW headline + provenance, no events, chart present.
    assert "net change" in w._headline.text().lower()
    assert "no known balance" in w._provenance.text().lower()
    assert w._events_table.rowCount() == 0
    assert w._chart_view.chart() is not None


def test_INV10_horizon_picker_has_four_presets_default_end_of_month(
    qtbot, vault_service
) -> None:
    w = ForecastWidget(vault_service)
    qtbot.addWidget(w)
    assert w._horizon.count() == 4
    assert w._horizon.currentIndex() == 0
    assert "end of" in w._horizon.currentText().lower()


def test_INV10_anchored_vault_headline_and_provenance(qtbot, vault_service) -> None:
    _seed_anchored(vault_service)
    w = ForecastWidget(vault_service)
    qtbot.addWidget(w)
    # Project far enough to catch the next monthly occurrence.
    w._horizon.setCurrentIndex(3)  # 90 days
    w.refresh()

    assert "projected balance" in w._headline.text().lower()
    assert "as of today" in w._provenance.text().lower()
    assert w._events_table.rowCount() >= 1, "the confirmed item projects forward"
