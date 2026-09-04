"""FIBR-0171 — the Forecast tab (spec D9/D10, Deliverables 11/13).

`ForecastWidget(service: AuthService)` mirrors `RecurringWidget`: a headline, an
anchor-provenance line, a horizon picker, a themed line chart, and an
upcoming-events table. Enforces tests/features/forecast/spec.md INV-10 (+ headline
/ provenance reflect the mode). Uses the pytest-qt `qtbot` fixture; tmp_path only.
"""

import re
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from PySide6.QtCore import Qt

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


def test_FIBR0216_coverage_suffix_counts_cash_accounts_not_all_accounts(
    qtbot, vault_service
) -> None:
    """FIBR-0216 — the "(X only)" suffix marks a PARTIAL total, and its denominator
    was `len(list_accounts())`: every account in the vault. But only CASH_TYPES
    accounts can ever contribute to the anchor (FIBR-0179), so a vault holding any
    debt or investment account showed "only" forever — even when every cash account
    had contributed and the total was complete.

    The provenance line already names the excluded accounts and says why, so the
    suffix was also redundant with it in exactly that case."""
    _seed_anchored(vault_service)  # one cash account, with a balance -> contributes
    w = ForecastWidget(vault_service)
    qtbot.addWidget(w)
    w.refresh()
    assert "only" not in w._headline.text().lower(), "one cash account, fully covered"

    # A credit card can never contribute; it must not make the cash total look partial.
    AccountService(vault_service.vault).add_account("Visa", "credit_card")
    w.refresh()
    assert "only" not in w._headline.text().lower(), (
        "a non-cash account is not a gap in the CASH total"
    )

    # A second CASH account with no balance IS a real gap — the suffix must return.
    AccountService(vault_service.vault).add_account("Second current", "current")
    w.refresh()
    assert "only" in w._headline.text().lower(), (
        "a cash account that did not contribute still marks the total partial"
    )


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


def test_FIBR0327_both_labels_render_account_names_as_plain_text(
    qtbot, vault_service
) -> None:
    """FIBR-0327 — the headline's "(X only)" suffix and the provenance line both
    interpolate names the user typed into the account editor, and both labels
    were left at the default AutoText.

    Qt's AutoText guesses: a name containing ``<b>`` or ``<img src=...>`` renders
    as rich text, so the label shows something other than the account's real name
    and attempts a local resource load. ``ui/month_summary.py`` had already been
    fixed for exactly this, with the reasoning written down.

    Both halves are asserted -- the format, and that the raw string survives into
    the text. The format alone would pass on a label that never received the name.
    """
    _seed_anchored(vault_service)
    accounts = AccountService(vault_service.vault)
    anchored = accounts.list_accounts()[0]
    accounts.update_account(
        anchored.id, "<b>Cheque</b>", anchored.type, account_number=None, note=None
    )
    # A second cash account with no balance makes the total partial, which is what
    # puts the contributing account's name in the headline's suffix.
    accounts.add_account("Second current", "current")
    # A debt account can never contribute, so provenance names it as excluded.
    accounts.add_account("<img src=x>Visa", "credit_card")

    w = ForecastWidget(vault_service)
    qtbot.addWidget(w)
    w.refresh()

    assert w._headline.textFormat() is Qt.TextFormat.PlainText
    assert w._provenance.textFormat() is Qt.TextFormat.PlainText
    assert "<b>Cheque</b>" in w._headline.text(), (
        "the headline must carry the account name as typed.\n"
        f"  actual: {w._headline.text()}"
    )
    assert "<img src=x>Visa" in w._provenance.text(), (
        "the provenance line must carry the account name as typed.\n"
        f"  actual: {w._provenance.text()}"
    )


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DAY_FIRST = re.compile(r"\d{2}/\d{2}/\d{4}")


def test_FIBR0328_dates_read_in_the_users_format(qtbot, vault_service) -> None:
    """The headline horizon, the provenance clause and the events table all
    honour the date preference (2026-08-31 audit, LOW/INFO).

    This tab rendered every date as a raw ISO string, so a user who had chosen
    a format saw it obeyed on Statements and Transactions and ignored here. The
    tab did not take a ``DateTimePrefs`` at all, so there was nothing to obey.

    Asserted by SHAPE rather than against a computed date: the horizon moves
    with the run date, and pinning it would test the arithmetic rather than the
    formatting.
    """
    from finbreak.services.auth import DateTimePrefs
    from finbreak.ui.forecast import _COL_DATE

    _seed_anchored(vault_service)
    w = ForecastWidget(vault_service, DateTimePrefs("system", "dd/MM/yyyy", "system"))
    qtbot.addWidget(w)
    w._horizon.setCurrentIndex(3)  # 90 days — far enough to project an event
    w.refresh()

    assert w._events_table.rowCount() >= 1, "the fixture projected no events"
    date_item = w._events_table.item(0, _COL_DATE)
    assert date_item is not None, "the events table has no Date cell"
    cell = date_item.text()
    assert _DAY_FIRST.fullmatch(cell), (
        f"the events Date column ignored the date preference: {cell!r}"
    )

    for label, text in (
        ("headline", w._headline.text()),
        ("provenance", w._provenance.text()),
        ("events cell", cell),
    ):
        assert not _ISO_DATE.search(text), (
            f"the {label} still shows a raw ISO date under dd/MM/yyyy: {text!r}"
        )
