"""Account-level balance reconciliation (FIBR-0177).

Generalises the Standard Bank parser's silent import-time checksum into a
bank-agnostic, persisted-data check: for each **cash account** walk its statement
closing balances in date order and confirm the transactions between each
consecutive pair bridge one closing to the next
(``C_prev + Σ amount_minor over (P_prev, P_curr] == C_curr``). Read-only analytics
over already-persisted data — **no schema change** (D7).

Two layers on the pure-vs-service seam (D8), mirroring ``forecast.py``:

* ``reconcile_account`` — a **pure**, clock-free, I/O-free core. It consumes only
  the ordered closing balances + the pre-computed bridge sums; there is **no
  ``Decimal``** and no exponent — money is signed integer minor units throughout,
  compared exactly (no epsilon; INV-6). Having no account-type argument it emits
  only ``RECONCILED`` / ``OFF`` / ``NOT_ENOUGH_DATA`` — never ``NOT_SUPPORTED``.

* ``ReconciliationService`` composes it over a vault: lists accounts, assigns
  ``NOT_SUPPORTED`` to types outside {current, savings} without calling the core
  (D1), and for the reconcilable types fetches the chain
  (``closing_balances_for_account``) + the per-gap bridge sums
  (``sum_after(...)[0]``) and calls the pure core. ``account_statuses()`` returns a
  **total map** — one entry per account (D8).
"""

from __future__ import annotations

from finbreak.models import (
    AccountReconciliation,
    AccountType,
    ReconciliationStatus,
)
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.vault import Vault

# The account types whose printed closing balance follows the canonical
# ``amount_minor`` convention, so ``C_prev + Σ`` holds directly (FIBR-0177 D1).
# Every other type is quietly NOT_SUPPORTED in v1.
_RECONCILABLE_TYPES = {AccountType.CURRENT, AccountType.SAVINGS}


def reconcile_account(
    account_id: int,
    closings: list[tuple[str, int]],
    bridge_sums: list[int],
) -> AccountReconciliation:
    """Reconcile one account's chain of closing balances (FIBR-0177 D5/D8).

    ``closings`` is the ordered ``[(period_end, closing_minor)]`` (ascending by
    ``period_end``); only each tuple's ``closing_minor`` (index ``[1]``) is read —
    the ``period_end`` is carried for symmetry with the repository's return shape.
    ``bridge_sums[i]`` is the ``Σ amount_minor`` over the half-open window between
    node ``i`` and ``i+1`` (so ``len(bridge_sums) == max(0, len(closings) − 1)``).

    Fewer than two nodes → ``NOT_ENOUGH_DATA`` with ``(0, 0, 0)`` (nothing to
    bridge; never raises). Otherwise, for each consecutive pair ``i``,
    ``expected = closings[i][1] + bridge_sums[i]`` and ``actual = closings[i+1][1]``;
    ``diff = actual − expected``. The status is ``RECONCILED`` iff **every** diff is
    exactly 0 (the honesty rule — NOT iff the net is 0; INV-12), else ``OFF``. Pure:
    no clock, no I/O, no ``Decimal`` (INV-6).
    """
    if len(closings) < 2:
        return AccountReconciliation(
            account_id, ReconciliationStatus.NOT_ENOUGH_DATA, 0, 0, 0
        )
    diffs = [
        closings[i + 1][1] - (closings[i][1] + bridge_sums[i])
        for i in range(len(closings) - 1)
    ]
    discrepancy_minor = sum(diffs)
    off_pair_count = sum(1 for diff in diffs if diff != 0)
    checked_pair_count = len(closings) - 1
    status = (
        ReconciliationStatus.RECONCILED
        if off_pair_count == 0
        else ReconciliationStatus.OFF
    )
    return AccountReconciliation(
        account_id, status, discrepancy_minor, off_pair_count, checked_pair_count
    )


class ReconciliationService:
    """Compose per-account reconciliation over a vault (FIBR-0177 Deliverable 3).

    Vault-scoped, mirroring ``ForecastService`` / ``RecurringService``. The public
    read ``account_statuses()`` returns a **total map** — exactly one
    ``AccountReconciliation`` per account in the vault, keyed by ``account.id`` — so
    the Accounts UI can index it directly (D6/D8).
    """

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    @property
    def _conn(self):
        return self._vault.connection

    def account_statuses(self) -> dict[int, AccountReconciliation]:
        """One ``AccountReconciliation`` per account (D8). A type outside
        {current, savings} is assigned ``NOT_SUPPORTED`` directly, without building a
        chain (D1); otherwise the account's balance-bearing chain and its per-gap
        bridge sums feed the pure ``reconcile_account``. An empty vault yields
        ``{}``."""
        conn = self._conn
        period_repo = StatementPeriodRepository(conn)
        txn_repo = TransactionRepository(conn)
        supported = {t.value for t in _RECONCILABLE_TYPES}
        statuses: dict[int, AccountReconciliation] = {}
        for account in AccountRepository(conn).list_all():
            # account.type is the stored STR token — compare to the enum .values.
            if account.type not in supported:
                statuses[account.id] = AccountReconciliation(
                    account.id, ReconciliationStatus.NOT_SUPPORTED, 0, 0, 0
                )
                continue
            closings = period_repo.closing_balances_for_account(account.id)
            bridge_sums = [
                txn_repo.sum_after(account.id, closings[i][0], closings[i + 1][0])[0]
                for i in range(len(closings) - 1)
            ]
            statuses[account.id] = reconcile_account(account.id, closings, bridge_sums)
        return statuses
