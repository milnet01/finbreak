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
    assert "no spendable-cash balance" in w._provenance.text().lower()
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


def test_refresh_swallows_a_vault_lock_from_the_text_builders(
    qtbot, vault_service, monkeypatch
) -> None:
    """FIBR-0211 — ``refresh``'s ``except VaultLockedError`` closed *before* the two
    setText calls, and both text builders read the vault again:
    ``_headline_text`` -> ``_coverage_suffix`` and ``_provenance_text`` ->
    ``_excluded_names`` each construct an ``AccountService`` and call
    ``list_accounts()``. The module docstring claims "every slot catches
    VaultLockedError and returns"; these two escaped it, and no ``sys.excepthook``
    is installed anywhere in ``src/``, so the escape reaches Qt.

    Widened by FIBR-0204: ``_excluded_names`` now runs in BOTH forecast modes, not
    only ANCHORED. Seeded anchored so ``_coverage_suffix`` runs as well."""
    from finbreak.errors import VaultLockedError

    _seed_anchored(vault_service)
    w = ForecastWidget(vault_service)
    qtbot.addWidget(w)
    w.refresh()
    assert w._headline.text(), "the fixture renders before the lock is simulated"

    def locked(*a, **k):
        raise VaultLockedError("the vault is locked")

    # The reads the guard was written to cover, and nothing else — patched on the
    # class, since both builders construct their own AccountService.
    monkeypatch.setattr(AccountService, "list_accounts", locked)
    w.refresh()  # must not raise


def test_INV14_debt_account_named_as_excluded_for_the_right_reason(
    qtbot, vault_service
) -> None:
    """A credit card with a recorded balance is excluded because it isn't cash —
    the provenance line must say so, not claim it has no balance yet (FIBR-0179)."""
    _seed_anchored(vault_service)
    today = date.today()
    card = AccountService(vault_service.vault).add_account("Visa", "credit_card").id
    StatementPeriodRepository(vault_service.vault.connection).add(
        card,
        (today - timedelta(days=200)).isoformat(),
        (today - timedelta(days=40)).isoformat(),
        "card.pdf",
        120_000,
    )
    vault_service.vault.connection.commit()

    w = ForecastWidget(vault_service)
    qtbot.addWidget(w)
    w.refresh()

    provenance = w._provenance.text().lower()
    # The card must be named under the NOT-CASH clause (which states the rule
    # positively — only current/savings are spendable cash — so it stays true for
    # `other`-type accounts too), never under the no-balance clause.
    assert "spendable cash): visa" in provenance
    assert "no recorded balance yet" not in provenance


def test_INV14_debt_only_vault_still_names_the_reason_in_net_flow(
    qtbot, vault_service
) -> None:
    """The NET_FLOW half of INV-14 — the case the invariant was written for.

    INV-14 says "a vault whose only balance-bearing account is a debt account
    runs in NET_FLOW. The provenance line names it as excluded *because it isn't
    cash*, not as 'no recorded balance yet'." The sibling test above seeds a cash
    anchor first, so it only ever exercised the ANCHORED branch — where the
    reason split is built. In NET_FLOW the branch returned early, so a
    credit-card user holding a statement was told there was no balance yet and
    the account was never named at all.
    """
    today = date.today()
    card = AccountService(vault_service.vault).add_account("Visa", "credit_card").id
    StatementPeriodRepository(vault_service.vault.connection).add(
        card,
        (today - timedelta(days=200)).isoformat(),
        (today - timedelta(days=40)).isoformat(),
        "card.pdf",
        120_000,
    )
    vault_service.vault.connection.commit()

    w = ForecastWidget(vault_service)
    qtbot.addWidget(w)
    w.refresh()

    provenance = w._provenance.text().lower()
    assert "spendable cash): visa" in provenance, (
        "the card holds a balance and is excluded for NOT BEING CASH — the "
        f"reason must survive into NET_FLOW mode. Got: {w._provenance.text()!r}"
    )
