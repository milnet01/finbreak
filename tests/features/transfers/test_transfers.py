"""FIBR-0011 — P09 transfer detection (suggest-then-confirm).

Enforces tests/features/transfers/spec.md. The self-join candidate detector
(`TransferRepository.candidate_pairs`), the `TransferDetectionService`
(candidates / confirm / reject / unlink / confirmed_transfers /
confirmed_transfer_txn_ids / confirm_all), the `transfer_pairs` repository, the
v7->v8 migration, and the Transfers tab. Headless layers are tested directly; the
tab (two tables + Confirm / Reject / Confirm all / Unlink) uses the pytest-qt
`qtbot` fixture. Every on-disk vault uses `tmp_path`; no test touches the network
or real financial data (testing.md § 6).
"""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from conftest import _PW, build_v7_vault, keyed_connection, raising_conn
from finbreak.crypto import SALT_LEN
from finbreak.errors import VaultLockedError
from finbreak.migrations import LATEST_SCHEMA_VERSION, run_migrations
from finbreak.models import TransferStatus
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.repositories.transfers import TransferRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.transfer_detection import TransferDetectionService

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to v8
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _two_accounts(service: AuthService) -> tuple[int, int]:
    """The seeded Default account + a second account, as `(a_id, b_id)`."""
    accounts = AccountService(service.vault)
    first = AccountRepository(service.vault.connection).list_all()[0].id
    second = accounts.add_account("Savings", "savings").id
    return first, second


def _add(
    service: AuthService,
    account_id: int,
    amount_minor: int,
    occurred_on: str = "2026-01-05",
    description: str = "move",
) -> int:
    """Insert one raw transaction (auto row) and return its id."""
    return TransactionRepository(service.vault.connection).add(
        account_id, occurred_on, amount_minor, description
    )


def _svc(service: AuthService) -> TransferDetectionService:
    return TransferDetectionService(service.vault)


def _has_transfer_pairs(conn) -> bool:
    """Whether the ``transfer_pairs`` table exists (the v8 migration's product)."""
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='transfer_pairs'"
        ).fetchone()
        is not None
    )


def _pair(service: AuthService) -> tuple[int, int]:
    """Seed one perfect debit/credit transfer pair across two accounts, returning
    `(debit_id, credit_id)`."""
    a, b = _two_accounts(service)
    debit = _add(service, a, -50000, "2026-01-05", "to savings")
    credit = _add(service, b, 50000, "2026-01-05", "from current")
    return debit, credit


# --------------------------------------------------------------------------- #
# INV-9 — schema v7 -> v8
# --------------------------------------------------------------------------- #
def test_INV9_v8_is_reachable_from_the_latest_schema() -> None:
    """INV-9 is about this feature's own v7 -> v8 step, so it pins that the walk
    reaches v8. The equality this replaces named 10 in its own test name while
    asserting 13 (FIBR-0327)."""
    assert LATEST_SCHEMA_VERSION >= 8


def test_INV9_v7_upgrades_to_v9(paths):
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v7_vault(vault_path, sidecar, salt, [("2026-01-01", -100, "a")])

    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v7 -> v9 (walks to LATEST)
    assert (
        conn.execute("SELECT version FROM schema_version").fetchone()[0]
        == LATEST_SCHEMA_VERSION
    )

    assert _has_transfer_pairs(conn)
    # A fresh table — no rows.
    assert conn.execute("SELECT count(*) FROM transfer_pairs").fetchone()[0] == 0
    conn.close()


def test_INV9_migration_is_atomic(paths):
    """A wedged v8 step leaves a re-openable v7 with no half-built table (the
    CREATE + UPDATE schema_version share one owned transaction, so a failure at the
    CREATE rolls the whole step back)."""
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v7_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)

    with pytest.raises(RuntimeError):
        run_migrations(
            raising_conn(
                conn,
                "CREATE TABLE transfer_pairs",
                "injected failure at the transfer_pairs CREATE",
            )
        )
    # Still v7, and no half-built table left behind.
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 7
    assert not _has_transfer_pairs(conn)
    conn.close()


# --------------------------------------------------------------------------- #
# INV-1 — suggest, never auto-apply
# --------------------------------------------------------------------------- #
def test_INV1_pair_is_suggested_but_not_excluded_until_confirmed(service):
    debit, credit = _pair(service)
    svc = _svc(service)

    candidates = svc.candidates()
    assert len(candidates) == 1
    assert {candidates[0].debit.id, candidates[0].credit.id} == {debit, credit}
    assert svc.confirmed_transfer_txn_ids() == set()  # nothing excluded yet

    svc.confirm(debit, credit)
    assert svc.confirmed_transfer_txn_ids() == {debit, credit}


# --------------------------------------------------------------------------- #
# INV-2 — what matches
# --------------------------------------------------------------------------- #
def test_INV2_matches_at_window_edge_day_offset_3(service):
    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-08")  # +3 days, inclusive
    assert len(_svc(service).candidates()) == 1


def test_INV2_no_match_past_window_day_offset_4(service):
    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-09")  # +4 days
    assert _svc(service).candidates() == []


def test_INV2_no_match_amount_off_by_one_minor(service):
    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, b, 1001, "2026-01-05")
    assert _svc(service).candidates() == []


def test_INV2_no_match_two_debits(service):
    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, b, -1000, "2026-01-05")  # both money-out
    assert _svc(service).candidates() == []


def test_INV2_no_match_same_account(service):
    a, _ = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, a, 1000, "2026-01-05")  # opposite pair, SAME account
    assert _svc(service).candidates() == []


def test_INV2_window_is_the_named_constant_bind(service, monkeypatch):
    """The window is the `TRANSFER_WINDOW_DAYS` bind (read at call time), not a
    literal 3: widening it to 5 makes an offset-4 pair match (testing.md § 2.1)."""
    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-09")  # +4 days — outside the default 3
    assert _svc(service).candidates() == []
    monkeypatch.setattr("finbreak.repositories.transfers.TRANSFER_WINDOW_DAYS", 5)
    assert len(_svc(service).candidates()) == 1


# --------------------------------------------------------------------------- #
# INV-3 — decided pairs don't resurface
# --------------------------------------------------------------------------- #
def test_INV3_rejected_pair_does_not_resurface(service):
    debit, credit = _pair(service)
    svc = _svc(service)
    svc.reject(debit, credit)
    assert svc.candidates() == []
    assert svc.confirmed_transfer_txn_ids() == set()  # a rejection excludes nothing


def test_INV3_confirmed_pair_does_not_resurface(service):
    debit, credit = _pair(service)
    svc = _svc(service)
    svc.confirm(debit, credit)
    assert svc.candidates() == []


def test_INV3_re_reject_raises_value_error(service):
    debit, credit = _pair(service)
    svc = _svc(service)
    svc.reject(debit, credit)
    with pytest.raises(ValueError):
        svc.reject(debit, credit)


def test_INV3_reject_of_confirmed_pair_raises_value_error(service):
    debit, credit = _pair(service)
    svc = _svc(service)
    svc.confirm(debit, credit)
    with pytest.raises(ValueError):
        svc.reject(debit, credit)


# --------------------------------------------------------------------------- #
# INV-4 — one transfer per transaction
# --------------------------------------------------------------------------- #
def test_INV4_confirm_of_consumed_txn_raises_value_error(service):
    a, b = _two_accounts(service)
    debit = _add(service, a, -1000, "2026-01-05")
    credit1 = _add(service, b, 1000, "2026-01-05")
    credit2 = _add(service, b, 1000, "2026-01-06")
    svc = _svc(service)
    svc.confirm(debit, credit1)
    with pytest.raises(ValueError):
        svc.confirm(debit, credit2)  # debit already consumed


def test_INV4_consumed_txn_drops_its_other_candidate(service):
    a, b = _two_accounts(service)
    debit = _add(service, a, -1000, "2026-01-05")
    credit1 = _add(service, b, 1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-06")  # credit2 — the second match
    svc = _svc(service)
    assert len(svc.candidates()) == 2  # debit matches both credits
    svc.confirm(debit, credit1)
    # debit + credit1 consumed; (debit, credit2) is gone.
    assert svc.candidates() == []


def test_INV4_confirm_all_on_ambiguous_debit_confirms_exactly_one(service):
    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")  # one debit
    _add(service, b, 1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-06")
    svc = _svc(service)
    assert svc.confirm_all() == 1  # one debit -> exactly one confirmed pair
    assert len(svc.confirmed_transfers()) == 1


# --------------------------------------------------------------------------- #
# INV-5 — exclusion primitive
# --------------------------------------------------------------------------- #
def test_INV5_only_confirmed_ids_are_excluded(service):
    a, b = _two_accounts(service)
    d1 = _add(service, a, -1000, "2026-01-05")
    c1 = _add(service, b, 1000, "2026-01-05")
    d2 = _add(service, a, -2000, "2026-01-05")
    c2 = _add(service, b, 2000, "2026-01-05")
    svc = _svc(service)
    svc.confirm(d1, c1)
    svc.reject(d2, c2)
    assert svc.confirmed_transfer_txn_ids() == {
        d1,
        c1,
    }  # rejected pair excluded from set


# --------------------------------------------------------------------------- #
# INV-6 — unlink reversible
# --------------------------------------------------------------------------- #
def test_INV6_unlink_returns_pair_to_candidates(service):
    debit, credit = _pair(service)
    svc = _svc(service)
    svc.confirm(debit, credit)
    (confirmed,) = svc.confirmed_transfers()
    svc.unlink(confirmed.pair_id)
    assert svc.confirmed_transfer_txn_ids() == set()
    assert len(svc.candidates()) == 1  # back as a suggestion


def test_INV6_unlink_absent_id_is_a_silent_noop(service):
    debit, credit = _pair(service)
    svc = _svc(service)
    svc.confirm(debit, credit)
    svc.unlink(99999)  # no such pair
    assert svc.confirmed_transfer_txn_ids() == {debit, credit}  # unchanged


def test_INV6_unlink_of_rejected_id_is_a_silent_noop(service):
    """delete_confirmed filters `status='confirmed'`, so an unlink can never delete
    a remembered rejection by id."""
    debit, credit = _pair(service)
    repo = TransferRepository(service.vault.connection)
    repo.add_decision(debit, credit, TransferStatus.REJECTED.value)
    (rejected_id,) = (
        r[0]
        for r in service.vault.connection.execute(
            "SELECT id FROM transfer_pairs WHERE status = 'rejected'"
        ).fetchall()
    )
    _svc(service).unlink(rejected_id)  # not a confirmed row -> no-op
    assert repo.pair_decided(debit, credit)  # the rejection still stands


# --------------------------------------------------------------------------- #
# INV-7 — live detection
# --------------------------------------------------------------------------- #
def test_INV7_new_pair_appears_on_next_call_without_rescan(service):
    a, b = _two_accounts(service)
    svc = _svc(service)
    assert svc.candidates() == []  # empty vault base case
    _add(service, a, -1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-05")
    assert len(svc.candidates()) == 1  # no manual scan needed


# --------------------------------------------------------------------------- #
# INV-8 — statement-delete cascade
# --------------------------------------------------------------------------- #
def test_INV8_statement_delete_cascades_transfer_pairs(service):
    a, b = _two_accounts(service)
    conn = service.vault.connection
    period_id = StatementPeriodRepository(conn).add(
        a, "2026-01-01", "2026-01-31", "s.csv"
    )
    TransactionRepository(conn).add_batch(
        [(a, "2026-01-05", -1000, "out"), (b, "2026-01-05", 1000, "in")], period_id
    )
    conn.commit()
    rows = conn.execute(
        "SELECT id, amount_minor FROM transactions ORDER BY id"
    ).fetchall()
    debit = next(r[0] for r in rows if r[1] < 0)
    credit = next(r[0] for r in rows if r[1] > 0)

    svc = _svc(service)
    svc.confirm(debit, credit)
    assert conn.execute("SELECT count(*) FROM transfer_pairs").fetchone()[0] == 1

    TransactionRepository(conn).delete_for_statement(
        period_id
    )  # fires ON DELETE CASCADE
    conn.commit()
    assert conn.execute("SELECT count(*) FROM transfer_pairs").fetchone()[0] == 0


# --------------------------------------------------------------------------- #
# INV-12 — transactions untouched
# --------------------------------------------------------------------------- #
def test_INV12_transactions_are_byte_identical_across_decisions(service):
    debit, credit = _pair(service)
    conn = service.vault.connection

    def snapshot():
        return conn.execute(
            "SELECT id, account_id, occurred_on, amount_minor, description, "
            "category_id, category_source FROM transactions ORDER BY id"
        ).fetchall()

    before = snapshot()
    svc = _svc(service)
    svc.confirm(debit, credit)
    (confirmed,) = svc.confirmed_transfers()
    svc.unlink(confirmed.pair_id)
    svc.reject(debit, credit)
    assert snapshot() == before  # no INSERT/UPDATE/DELETE against transactions


# --------------------------------------------------------------------------- #
# Edges — canonical order, display columns, Cartesian confirm-all
# --------------------------------------------------------------------------- #
def test_canonical_order_is_direction_independent(service):
    """confirm stores min/max regardless of the argument order."""
    debit, credit = _pair(service)  # debit id < credit id (inserted first)
    repo = TransferRepository(service.vault.connection)
    _svc(service).confirm(credit, debit)  # pass them "backwards"
    (pair,) = repo.list_confirmed()
    assert (pair.txn_a_id, pair.txn_b_id) == (min(debit, credit), max(debit, credit))


def test_candidate_display_columns(service):
    a, b = _two_accounts(service)  # a = Default, b = Savings
    _add(service, a, -50000, "2026-01-05")
    _add(service, b, 50000, "2026-01-06")
    (cand,) = _svc(service).candidates()
    assert cand.display_amount == Decimal("500.00")  # shared positive magnitude
    assert cand.from_account == "Default"  # debit side
    assert cand.to_account == "Savings"  # credit side


def test_cartesian_two_by_two_resolves_to_two_confirmed(service):
    """Two debits x two credits of equal magnitude in-window yield FOUR suggestions;
    confirm_all's consumed-set resolves them to TWO confirmed pairs."""
    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, a, -1000, "2026-01-06")
    _add(service, b, 1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-06")
    svc = _svc(service)
    assert len(svc.candidates()) == 4
    assert svc.confirm_all() == 2
    assert svc.candidates() == []


# --------------------------------------------------------------------------- #
# INV-10 — Transfers tab (GUI)
# --------------------------------------------------------------------------- #
def test_INV10_tab_confirm_moves_pair_to_confirmed(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    debit, credit = _pair(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    assert widget.objectName() == "tab_transfers"
    assert len(widget._candidates) == 1
    assert len(widget._confirmed) == 0

    widget._suggested.selectRow(0)
    widget._confirm_button.click()
    assert len(widget._candidates) == 0
    assert len(widget._confirmed) == 1
    assert _svc(service).confirmed_transfer_txn_ids() == {debit, credit}


def test_INV10_tab_reject_removes_suggestion(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    _pair(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    widget._suggested.selectRow(0)
    widget._reject_button.click()
    assert len(widget._candidates) == 0
    assert len(widget._confirmed) == 0


def test_INV10_tab_confirm_all(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, a, -2000, "2026-01-05")
    _add(service, b, 1000, "2026-01-05")
    _add(service, b, 2000, "2026-01-05")
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    widget._confirm_all_button.click()
    assert len(widget._confirmed) == 2


def test_INV10_tab_unlink_returns_pair_to_suggested(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    _pair(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    widget._suggested.selectRow(0)
    widget._confirm_button.click()
    widget._confirmed_table.selectRow(0)
    widget._unlink_button.click()
    assert len(widget._candidates) == 1
    assert len(widget._confirmed) == 0


def test_INV10_tab_from_to_and_amount_cells(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    a, b = _two_accounts(service)
    _add(service, a, -50000, "2026-01-05", "pay savings")
    _add(service, b, 50000, "2026-01-05", "deposit")
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    # Columns: Date / Amount / From -> To / Description.
    assert widget._suggested.item(0, 2).text() == "Default → Savings"
    assert "500.00" in widget._suggested.item(0, 1).text()


@pytest.mark.parametrize(
    "method, button",
    [
        # The bulk slots call confirm_many / reject_many (FIBR-0201 D3), so those
        # are the methods a lock has to be caught around — patching the old
        # single-pair confirm/reject would leave this leg green while checking
        # nothing.
        ("confirm_many", "_confirm_button"),
        ("reject_many", "_reject_button"),
        ("confirm_all", "_confirm_all_button"),
        ("unlink", "_unlink_button"),
    ],
)
def test_INV10_every_slot_catches_vault_locked(
    qtbot, service, monkeypatch, method, button
):
    """INV-10: every action slot catches a VaultLockedError raised mid-click and
    returns without crashing (an auto-lock can fire at any moment)."""
    from finbreak.ui.transfers import TransfersWidget

    _pair(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    if method == "unlink":
        # Unlink needs a confirmed row selected — confirm one for real first.
        widget._suggested.selectRow(0)
        widget._confirm_button.click()
        widget._confirmed_table.selectRow(0)
    elif method != "confirm_all":  # confirm_all needs no selection
        widget._suggested.selectRow(0)

    def _boom(*a, **k):
        raise VaultLockedError("locked mid-click")

    monkeypatch.setattr(widget._detection, method, _boom)
    getattr(widget, button).click()  # must not raise


def test_INV10_transfers_toolbar_action_has_a_rendering_icon(qtbot, service):
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QAction

    from finbreak.ui.main_window import MainWindow

    service.lock()
    window = MainWindow(service)
    qtbot.addWidget(window)
    action = window.findChild(QAction, "action_transfers")
    assert action is not None
    assert not action.icon().pixmap(QSize(24, 24)).isNull(), "Transfers needs an icon"


def test_INV10_workspace_has_eight_tabs(qtbot, service):
    from finbreak.ui.main_window import MainWindow

    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    assert window._workspace is not None
    assert (
        window._workspace.count() == 9
    )  # + Recurring (FIBR-0142), Forecast (FIBR-0171)
    assert window._transfers_tab is not None


# --------------------------------------------------------------------------- #
# FIBR-0151 — a confirmed transfer renders as a directional label in the
# Transactions tab's Category column, naming the *counterparty* account. This is
# READ-time only: no transactions row is touched (INV-12 still holds — the label
# is resolved from transfer_pairs when the tab is rendered).
# --------------------------------------------------------------------------- #
_COL_DESCRIPTION = 3
_COL_CATEGORY = 5


def _txn_view(service: AuthService):
    """A TransactionsView over the same vault — it default-constructs its own
    TransferDetectionService, so a confirmed pair surfaces without extra wiring."""
    from finbreak.services.categorization import CategorizationService
    from finbreak.services.transactions import TransactionService
    from finbreak.ui.transactions import TransactionsView

    return TransactionsView(
        TransactionService(service.vault), CategorizationService(service.vault)
    )


def _category_text(view, description: str) -> str:
    for r in range(view._table.rowCount()):
        if view._table.item(r, _COL_DESCRIPTION).text() == description:
            return view._table.item(r, _COL_CATEGORY).text()
    raise AssertionError(f"no row for {description!r}")


def test_FIBR0151_confirmed_transfer_shows_directional_counterparty_label(
    qtbot, service
):
    # debit lives in Default (money out), credit in Savings (money in).
    debit, credit = _pair(service)
    _svc(service).confirm(debit, credit)

    view = _txn_view(service)
    qtbot.addWidget(view)

    # Outgoing leg names where the money WENT (the credit's account).
    assert _category_text(view, "to savings") == "Transfer to Savings"
    # Incoming leg names where the money CAME FROM (the debit's account).
    assert _category_text(view, "from current") == "Transfer from Default"


def test_FIBR0151_unconfirmed_pair_renders_as_ordinary_uncategorised_rows(
    qtbot, service
):
    _pair(service)  # a candidate, but the user has NOT confirmed it

    view = _txn_view(service)
    qtbot.addWidget(view)

    # No label until confirmed — the legs are just uncategorised transactions.
    assert _category_text(view, "to savings") == ""
    assert _category_text(view, "from current") == ""


# --------------------------------------------------------------------------- #
# FIBR-0201 — bulk confirm / reject on a multi-select suggested table.
# --------------------------------------------------------------------------- #
def _two_pairs(service: AuthService) -> tuple[tuple[int, int], tuple[int, int]]:
    """Two independent, unambiguous candidate pairs, as ``(debit, credit)`` tuples
    in candidate order (the amounts differ so no cross-match is possible)."""
    a, b = _two_accounts(service)
    d1 = _add(service, a, -1000, "2026-01-05", "one")
    d2 = _add(service, a, -2000, "2026-01-05", "two")
    c1 = _add(service, b, 1000, "2026-01-05", "one")
    c2 = _add(service, b, 2000, "2026-01-05", "two")
    return (d1, c1), (d2, c2)


def test_FIBR0201_INV4_confirm_many_confirms_each_given_pair(service):
    svc = _svc(service)
    p1, p2 = _two_pairs(service)
    assert svc.confirm_many([p1, p2]) == 2
    assert svc.confirmed_transfer_txn_ids() == {*p1, *p2}


def test_FIBR0201_INV4_confirm_many_skips_a_consumed_pair_and_the_earlier_wins(service):
    """The consumption hazard is not specific to "all": a user can select two
    suggestions that share a transaction. Exactly one is confirmed — the EARLIER
    in the given order — the count is 1, and no ValueError reaches the user."""
    a, b = _two_accounts(service)
    debit = _add(service, a, -1000, "2026-01-05")
    credit1 = _add(service, b, 1000, "2026-01-05")
    credit2 = _add(service, b, 1000, "2026-01-06")
    svc = _svc(service)

    assert svc.confirm_many([(debit, credit2), (debit, credit1)]) == 1, (
        "the second pair's debit was consumed by the first — skipped, not raised"
    )
    assert svc.confirmed_transfer_txn_ids() == {debit, credit2}, (
        "the EARLIER pair in the given order wins (credit2 was listed first)"
    )


def test_FIBR0201_INV4_confirm_many_winner_flips_with_the_order(service):
    """The companion of the leg above: reverse the order and the other pair wins.
    Without this an implementation that always picks the lowest id passes."""
    a, b = _two_accounts(service)
    debit = _add(service, a, -1000, "2026-01-05")
    credit1 = _add(service, b, 1000, "2026-01-05")
    credit2 = _add(service, b, 1000, "2026-01-06")
    svc = _svc(service)

    assert svc.confirm_many([(debit, credit1), (debit, credit2)]) == 1
    assert svc.confirmed_transfer_txn_ids() == {debit, credit1}


def test_FIBR0201_INV4_confirm_many_empty_confirms_nothing(service):
    svc = _svc(service)
    _two_pairs(service)
    assert svc.confirm_many([]) == 0
    assert svc.confirmed_transfer_txn_ids() == set()


def test_FIBR0201_INV5_confirm_all_is_confirm_many_over_candidate_pairs(service):
    """The consumed-set logic MOVES into confirm_many rather than being copied, so
    `confirm_all` is literally its caller — two implementations would drift."""
    svc = _svc(service)
    _two_pairs(service)
    pairs = TransferRepository(service.vault.connection).candidate_pairs()
    calls: list[list[tuple[int, int]]] = []
    real = svc.confirm_many

    def _spy(given):
        calls.append(list(given))
        return real(given)

    svc.confirm_many = _spy  # type: ignore[method-assign]
    assert svc.confirm_all() == 2
    assert calls == [list(pairs)], "confirm_all delegates the live candidate order"


def test_FIBR0201_INV5_confirm_all_count_and_effect_unchanged(service):
    """`confirm_all`'s shipped behaviour and count are unchanged — the ambiguous
    debit still resolves to exactly one confirmed pair."""
    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-06")
    svc = _svc(service)
    assert svc.confirm_all() == 1
    assert len(svc.confirmed_transfers()) == 1


def test_FIBR0201_INV6_reject_many_records_each_and_none_resurfaces(service):
    svc = _svc(service)
    p1, p2 = _two_pairs(service)
    assert svc.reject_many([p1, p2]) == 2
    assert svc.candidates() == [], "a rejected pair is never re-offered"
    assert svc.confirmed_transfer_txn_ids() == set(), "rejection confirms nothing"


def test_FIBR0201_INV6_reject_many_takes_two_pairs_sharing_a_transaction(service):
    """The reachable case `reject()` cannot serve: a user selects two suggestions
    that share a transaction and rejects both. Rejection consumes nothing — a
    rejected transaction is still free to pair with another — so BOTH are recorded
    and nothing raises at the user, where a loop through `_record` would raise on
    the second (its `is_confirmed`/`pair_decided` guards raise rather than skip)."""
    a, b = _two_accounts(service)
    debit = _add(service, a, -1000, "2026-01-05")
    credit1 = _add(service, b, 1000, "2026-01-05")
    credit2 = _add(service, b, 1000, "2026-01-06")
    svc = _svc(service)
    assert len(svc.candidates()) == 2, "one debit, two candidate credits"

    assert svc.reject_many([(debit, credit1), (debit, credit2)]) == 2

    assert svc.candidates() == [], "neither pair is re-offered"
    assert svc.confirmed_transfer_txn_ids() == set()


def test_FIBR0201_INV6_reject_many_empty_rejects_nothing(service):
    svc = _svc(service)
    _two_pairs(service)
    assert svc.reject_many([]) == 0
    assert len(svc.candidates()) == 2


def test_FIBR0201_INV1_only_the_suggested_table_is_multi_select(qtbot, service):
    """Both transfer tables are built by ONE `_make_table`, so the naive edit of
    its `setSelectionMode` line silently widens the confirmed table too — and
    Unlink is explicitly out of scope (D2)."""
    from PySide6.QtWidgets import QAbstractItemView

    from finbreak.ui.transfers import TransfersWidget

    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    assert (
        widget._suggested.selectionMode()
        == QAbstractItemView.SelectionMode.MultiSelection
    )
    assert (
        widget._confirmed_table.selectionMode()
        == QAbstractItemView.SelectionMode.SingleSelection
    )


def test_FIBR0201_tab_confirms_every_selected_row(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    p1, p2 = _two_pairs(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    assert len(widget._candidates) == 2

    widget._suggested.selectRow(0)
    widget._suggested.selectRow(1)
    widget._confirm_button.click()

    assert widget._candidates == []
    assert len(widget._confirmed) == 2
    assert _svc(service).confirmed_transfer_txn_ids() == {*p1, *p2}


def test_FIBR0201_tab_rejects_every_selected_row(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    _two_pairs(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    widget._suggested.selectRow(0)
    widget._suggested.selectRow(1)
    widget._reject_button.click()
    assert widget._candidates == [] and widget._confirmed == []


def test_FIBR0201_INV3_bulk_confirm_resolves_ids_before_mutating(qtbot, service):
    """Resolve-before-mutate under an APPLIED SORT that actually reorders the rows
    (§7): `_refresh()` rebuilds and re-sorts `_candidates`, so an index resolved
    before the mutation and dereferenced after it can name a different pair
    (FIBR-0113). Here the visual order is the reverse of the insertion order, so an
    implementation that indexes as it goes confirms the wrong pairs — or raises."""
    a, b = _two_accounts(service)
    d1 = _add(service, a, -10000, "2026-01-05", "small")  # 100.00, inserted first
    c1 = _add(service, b, 10000, "2026-01-05", "small")
    d2 = _add(service, a, -50000, "2026-01-05", "big")  # 500.00
    c2 = _add(service, b, 50000, "2026-01-05", "big")
    from PySide6.QtCore import Qt

    from finbreak.ui.transfers import TransfersWidget

    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    widget._suggested.sortItems(1, Qt.SortOrder.DescendingOrder)  # 500.00 on top
    assert widget._suggested.item(0, 1).text().endswith("500.00")

    widget._suggested.selectRow(0)
    widget._suggested.selectRow(1)
    widget._confirm_button.click()

    assert _svc(service).confirmed_transfer_txn_ids() == {d1, c1, d2, c2}, (
        "both selected pairs confirmed, whatever the visual order"
    )


def test_FIBR0201_buttons_enable_on_a_plural_selection(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    _two_pairs(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    assert not widget._confirm_button.isEnabled(), "nothing selected"
    widget._suggested.selectRow(0)
    widget._suggested.selectRow(1)
    assert widget._confirm_button.isEnabled() and widget._reject_button.isEnabled()


def test_FIBR0201_INV14_single_reject_keeps_todays_status_string(qtbot, service):
    """D9 applied to the Transfers tab: "Rejected 1 transfer(s)." is the same
    regression as "Delete 1 statement(s)?", and §1 promises single-selection
    behaviour is unchanged."""
    from finbreak.ui.transfers import TransfersWidget

    _two_pairs(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    widget._suggested.selectRow(0)
    widget._reject_button.click()
    assert widget._status.text() == "Rejected.", widget._status.text()


def test_FIBR0201_plural_reject_names_the_count(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    _two_pairs(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    widget._suggested.selectRow(0)
    widget._suggested.selectRow(1)
    widget._reject_button.click()
    assert "2" in widget._status.text(), widget._status.text()


def test_FIBR0201_a_skipped_selection_is_named_not_silent(qtbot, service):
    """Under `Confirm all` a consumed-pair skip is invisible by design; under an
    explicit selection the user chose N and got fewer, so the status line owes
    them the reason (§4.8, §6)."""
    from finbreak.ui.transfers import TransfersWidget

    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")  # one debit...
    _add(service, b, 1000, "2026-01-05")  # ...matching two credits
    _add(service, b, 1000, "2026-01-06")
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    assert len(widget._candidates) == 2

    widget._suggested.selectRow(0)
    widget._suggested.selectRow(1)
    widget._confirm_button.click()

    text = widget._status.text()
    assert "1" in text and "skipped" in text.lower(), (
        f"names the skipped suggestion rather than silently reporting 1: {text!r}"
    )


def test_FIBR0201_no_skip_message_when_nothing_was_skipped(qtbot, service):
    from finbreak.ui.transfers import TransfersWidget

    _two_pairs(service)
    widget = TransfersWidget(service)
    qtbot.addWidget(widget)
    widget._suggested.selectRow(0)
    widget._suggested.selectRow(1)
    widget._confirm_button.click()
    assert "skipped" not in widget._status.text().lower()


def test_FIBR0328_date_column_reads_in_the_user_format_and_still_sorts(qtbot, service):
    """The Date column honours the date preference, and sorting stays
    chronological (2026-08-31 audit, LOW/INFO).

    The cell used to be the stored ISO string, which the code leaned on twice:
    it read as a date and it sorted chronologically as text. Formatting it fixes
    the first and breaks the second — under `dd/MM/yyyy` a plain text sort orders
    by day-of-month, so 03 February would come before 05 January. The ISO form
    stays as the SortableItem's key, which is what keeps the two apart.

    Both legs matter: assert the display alone and a plain QTableWidgetItem
    passes; assert the order alone and never formatting at all passes.
    """
    from finbreak.services.auth import DateTimePrefs
    from finbreak.ui.transfers import _COL_DATE, TransfersWidget

    a, b = _two_accounts(service)
    _add(service, a, -1000, "2026-01-05")
    _add(service, b, 1000, "2026-01-05")
    _add(service, a, -2000, "2026-02-03")
    _add(service, b, 2000, "2026-02-03")

    widget = TransfersWidget(service, DateTimePrefs("system", "dd/MM/yyyy", "system"))
    qtbot.addWidget(widget)
    table = widget._suggested
    assert table.rowCount() == 2, "the fixture did not produce two candidates"

    shown = {table.item(row, _COL_DATE).text() for row in range(table.rowCount())}
    assert shown == {"05/01/2026", "03/02/2026"}, (
        f"the Date column ignored the date preference: {sorted(shown)}"
    )

    table.sortItems(_COL_DATE, Qt.SortOrder.AscendingOrder)
    assert table.item(0, _COL_DATE).text() == "05/01/2026", (
        "ascending by date must put January before February. Sorting on the "
        "DISPLAY string orders by day-of-month under dd/MM/yyyy, which is why "
        "the ISO form has to stay as the sort key."
    )
