"""FIBR-0087 INV-12 — the dashboard's account selector offers one scope per
currency, and every figure shows in the scope's currency.

docs/specs/FIBR-0087-per-account-currency.md § 4.6. Every vault uses
tmp_path; every row is synthetic (testing.md § 6).
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from conftest import _PW
from finbreak.repositories.categories import CategoryRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.alerts import AlertService
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import CategorizationService
from finbreak.services.month_summary import MonthSummaryService
from finbreak.services.recurring import RecurringService
from finbreak.services.reporting import (
    MODE_SPECIFIC_MONTH,
    ReportingService,
    ReportPrefs,
)
from finbreak.services.transactions import read_minor_unit_exponent

pytestmark = pytest.mark.features

_TODAY = date(2026, 7, 15)
_JUN = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=6)


@pytest.fixture(autouse=True)
def _pinned_clock(monkeypatch) -> None:
    for module in ("finbreak.ui.home", "finbreak.ui.alerts_dialog"):
        monkeypatch.setattr(f"{module}.app_today", lambda: _TODAY)


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _home(service):
    from finbreak.ui.home import HomeView

    return HomeView(
        ReportingService(service.vault),
        AccountService(service.vault),
        service,
        recurring=RecurringService(service.vault),
        alerts=AlertService(service.vault),
        month_summary=MonthSummaryService(service.vault),
    )


def _items(home) -> list[str]:
    selector = home._account_selector
    return [selector.itemText(i) for i in range(selector.count())]


def _spiking(service, account_id: int, prior: int, june: int) -> None:
    """A category spike in June over March to May, in one account."""
    roots = CategoryRepository(service.vault.connection).children_of(None)
    expenditure = next(r for r in roots if r.kind == "expenditure")
    leaf = next(
        (
            c
            for c in CategoryRepository(service.vault.connection).children_of(
                expenditure.id
            )
            if c.name == "Ztest Spike"
        ),
        None,
    )
    leaf_id = (
        leaf.id
        if leaf is not None
        else CategoryService(service.vault)
        .add_category(expenditure.id, "Ztest Spike")
        .id
    )
    repo = TransactionRepository(service.vault.connection)
    for month, amount in (("03", prior), ("04", prior), ("05", prior), ("06", june)):
        txn = repo.add(account_id, f"2026-{month}-20", -amount, f"Spend {month}")
        CategorizationService(service.vault).set_manual_category(txn, leaf_id)


@pytest.fixture
def mixed(service):
    """The Default (ZAR) account and a USD one, each with a June spike of a
    different size."""
    zar = AccountService(service.vault).list_accounts()[0].id
    usd = (
        AccountService(service.vault)
        .add_account("Offshore", "savings", currency="USD")
        .id
    )
    _spiking(service, zar, 100_000, 700_000)
    _spiking(service, usd, 100_000, 250_000)
    service.set_report_prefs(_JUN)
    return zar, usd


def test_INV12_single_currency_list_is_unchanged(qtbot, service) -> None:
    zar = AccountService(service.vault).list_accounts()[0]
    TransactionRepository(service.vault.connection).add(
        zar.id, "2026-06-05", -1_000, "x"
    )
    home = _home(service)
    qtbot.addWidget(home)
    assert _items(home) == ["All accounts", zar.name]
    assert home._account_selector.itemData(0) is None
    assert home.scope_account_ids() is None


def test_INV12_mixed_vault_lists_a_scope_per_currency(qtbot, service, mixed) -> None:
    home = _home(service)
    qtbot.addWidget(home)
    assert _items(home)[:2] == ["All ZAR accounts", "All USD accounts"]

    home._account_selector.setCurrentIndex(1)  # All USD accounts
    assert home.scope_currency() == "USD"
    assert home.scope_account_ids() == frozenset({mixed[1]})
    net = home._net_value.text()
    assert "$" in net and "R" not in net
    # Grouping follows the locale (none in CI's container), so drop it.
    ungrouped = re.sub(r"(?<=\d)[,.\u00a0\u202f ](?=\d{3}\b)", "", net)
    assert "2500.00" in ungrouped


def test_INV12_alerts_dialog_from_usd_counts_usd_only(qtbot, service, mixed) -> None:
    from PySide6.QtWidgets import QPushButton

    from finbreak.ui.alerts_dialog import AlertsDialog

    home = _home(service)
    qtbot.addWidget(home)
    home._account_selector.setCurrentIndex(1)  # All USD accounts
    assert home._alerts_button.text() == "Alerts (1)"  # the ZAR spike not counted

    dialog = AlertsDialog(
        AlertService(service.vault),
        home.scope_currency(),
        read_minor_unit_exponent(service.vault.connection),
    )
    qtbot.addWidget(dialog)
    dialog.changed.connect(home.set_alert_count)
    buttons = [
        b for b in dialog.findChildren(QPushButton) if b.objectName() == "alert_dismiss"
    ]
    assert len(buttons) == 1
    from PySide6.QtWidgets import QLabel

    shown = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "$" in shown and "R " not in shown.replace("\u00a0", " ")  # INV-13
    buttons[0].click()
    assert home._alerts_button.text() == "Alerts"  # USD count 0; ZAR still open
    assert len(AlertService(service.vault).alerts(_TODAY)) == 1


def test_INV12_held_scope_falls_back_when_its_currency_goes(
    qtbot, service, mixed
) -> None:
    home = _home(service)
    qtbot.addWidget(home)
    home._account_selector.setCurrentIndex(1)  # All USD accounts
    conn = service.vault.connection
    conn.execute("DELETE FROM transactions WHERE account_id = ?", (mixed[1],))
    conn.execute("DELETE FROM accounts WHERE id = ?", (mixed[1],))
    conn.commit()
    home.refresh()
    assert _items(home)[0] == "All accounts"
    assert home._account_selector.currentIndex() == 0
