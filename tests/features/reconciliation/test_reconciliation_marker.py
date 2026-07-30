"""FIBR-0177 — the Accounts-tab reconciliation marker (INV-9, qtbot).

Each status renders the right per-row suffix (or none): a RECONCILED account shows
`✓ balances reconcile`, a 1-gap OFF shows `⚠ off by …` with the magnitude, a >1-gap
OFF shows `⚠ {n} periods don't reconcile`, and NOT_ENOUGH_DATA / NOT_SUPPORTED rows
carry no reconciliation marker. A real (tmp_path) vault; no network, no real
financial data (testing.md § 6). The marker is asserted on the **Status cell** of
the FIBR-0113 accounts table: name and status are separate cells now, so the row
is found by its Name cell and the marker read from column 4 (FIBR-0113 § 6 — a
mechanical `_list` -> `_table` swap would not compile into anything meaningful).
"""

from collections.abc import Iterator

import pytest

from conftest import _PW
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.ui.accounts import AccountsWidget

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # ZAR: exponent 2, symbol "R"
    yield svc
    svc.lock()


def _statement(svc, account_id, start, end, name, closing) -> None:
    StatementPeriodRepository(svc.vault.connection).add(
        account_id, start, end, name, closing
    )
    svc.vault.connection.commit()


def _txn(svc, account_id, day, minor, desc) -> None:
    TransactionRepository(svc.vault.connection).add(account_id, day, minor, desc)


_COL_NAME, _COL_STATUS = 0, 4


def _row_text(widget: AccountsWidget, name: str) -> str:
    """The Status-cell text of the row whose NAME cell is `name`. Re-derived
    for the table: the old helper matched the account name and read the marker
    out of the same row-wide string, which no longer exists."""
    for row in range(widget._table.rowCount()):
        item = widget._table.item(row, _COL_NAME)
        if item is not None and item.text() == name:
            status = widget._table.item(row, _COL_STATUS)
            return "" if status is None else status.text()
    raise AssertionError(f"no account row named {name!r}")


def test_INV9_marker_per_status(qtbot, service) -> None:
    svc = service
    accounts = AccountService(svc.vault)

    # RECONCILED — two statements bridged exactly by a 50_000 txn.
    good = accounts.add_account("GoodCurrent", "current").id
    _statement(svc, good, "2026-01-01", "2026-04-30", "apr.pdf", 100_000)
    _statement(svc, good, "2026-05-01", "2026-05-31", "may.pdf", 150_000)
    _txn(svc, good, "2026-05-15", 50_000, "bridge")

    # OFF, 1 gap — two statements, no bridging txns → off by 500_00 minor (R 500.00).
    one = accounts.add_account("OneGap", "current").id
    _statement(svc, one, "2026-01-01", "2026-04-30", "apr.pdf", 100_000)
    _statement(svc, one, "2026-05-01", "2026-05-31", "may.pdf", 150_000)

    # OFF, >1 gap — three statements, no bridging txns → two off pairs.
    two = accounts.add_account("TwoGap", "current").id
    _statement(svc, two, "2026-01-01", "2026-03-31", "q1.pdf", 100_000)
    _statement(svc, two, "2026-04-01", "2026-04-30", "apr.pdf", 150_000)
    _statement(svc, two, "2026-05-01", "2026-05-31", "may.pdf", 200_000)

    # NOT_SUPPORTED — a debt product with data.
    card = accounts.add_account("Card", "credit_card").id
    _statement(svc, card, "2026-01-01", "2026-04-30", "cc.pdf", 100_000)
    _statement(svc, card, "2026-05-01", "2026-05-31", "cc2.pdf", 150_000)

    # NOT_ENOUGH_DATA — savings with a single balance-bearing statement.
    thin = accounts.add_account("ThinSavings", "savings").id
    _statement(svc, thin, "2026-01-01", "2026-04-30", "s.ofx", 100_000)

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)

    good_text = _row_text(widget, "GoodCurrent")
    assert "✓" in good_text and "balances reconcile" in good_text

    one_text = _row_text(widget, "OneGap")
    assert "⚠" in one_text and "off by" in one_text
    assert "500" in one_text, "the discrepancy magnitude (R 500.00) is rendered"

    two_text = _row_text(widget, "TwoGap")
    assert "⚠" in two_text and "2 periods" in two_text
    assert "off by" not in two_text, "the >1-gap wording is used, not 'off by'"

    # Quiet statuses carry no reconciliation marker (neither tick nor warning).
    for quiet in ("Card", "ThinSavings"):
        text = _row_text(widget, quiet)
        assert "✓" not in text and "⚠" not in text, f"{quiet} must show no marker"
