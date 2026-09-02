# Feature test contract — account-level balance reconciliation (FIBR-0177)

Enforces `docs/specs/FIBR-0177.md`. For each **cash account** (`current` /
`savings`) the feature walks its persisted statement **closing balances** in date
order and confirms the transactions between each consecutive pair bridge one
closing to the next (`C_prev + Σ amount_minor over (P_prev, P_curr] == C_curr`). A
gap (a missed import / missing period) surfaces as a signed discrepancy. The
result shows as a per-account marker on the Accounts tab — mirroring the existing
"🔑 statement password saved" suffix. **No schema change** (reuses FIBR-0171's v11
`closing_balance_minor` + the `sum_after` half-open primitive).

Two layers on the pure-vs-service seam (D8): a pure, I/O-free, `Decimal`-free
`reconcile_account(account_id, closings, bridge_sums)` (integer minor units only),
and a vault-scoped `ReconciliationService` whose `account_statuses()` returns a
**total map** — one entry per account.

Every on-disk vault uses `tmp_path`; no test touches the network or real financial
data (testing.md § 6). The pure core is tested directly with synthetic inputs; the
service + repository use a real vault; the marker uses the pytest-qt `qtbot`
fixture.

| INV | Assertion | Test |
|-----|-----------|------|
| INV-1 | An account `RECONCILED` iff **every** consecutive balance-bearing pair satisfies `C_prev + bridge == C_curr` exactly. | `test_reconcile.py`, `test_reconciliation_service.py` |
| INV-2 | The bridge is the **half-open** `(P_prev, P_curr]` window (`sum_after`): a txn on `P_prev` is excluded, one on `P_curr` included. | `test_reconciliation_service.py` |
| INV-3 | Only `closing_balance_minor IS NOT NULL` statements are chain nodes; ordered `(period_end, id)` asc. A NULL-closing period is not a node but its txns still bridge. | `test_closing_balances_for_account.py`, `test_reconciliation_service.py` |
| INV-4 | Asset account with < 2 balance-bearing statements → `NOT_ENOUGH_DATA`, `(0, 0, 0)`; never raises. | `test_reconcile.py`, `test_reconciliation_service.py` |
| INV-5 | Account type ∉ {current, savings} → `NOT_SUPPORTED`, `(0, 0, 0)`; no chain built, no false "off". | `test_reconciliation_service.py` |
| INV-6 | Money-safe: pure core uses **integer minor units only**, no `Decimal`, exact comparison (a 1-minor-unit gap → `OFF`). | `test_reconcile.py` |
| INV-7 | `discrepancy_minor == Σ(actual − expected)`; `off_pair_count ==` count of non-zero per-pair diffs; `checked_pair_count == max(0, nodes − 1)` (never `−1`); all three `0` for `NOT_ENOUGH_DATA` / `NOT_SUPPORTED`. | `test_reconcile.py`, `test_reconciliation_service.py` |
| INV-8 | **No schema change of its own** — reconciliation registers no migration. The schema has since advanced to `LATEST_SCHEMA_VERSION == 14` (via FIBR-0172's `alert_dismissals` and FIBR-0193's `accounts.account_number` / `note`, both unrelated to reconciliation), so the guard now pins the current latest and that no *unregistered next* version (v15) exists. | `test_no_schema_change.py` |
| INV-9 | Accounts-tab marker: `✓` for RECONCILED, `⚠ off by {money}` for OFF (1 gap) / `⚠ {n} periods don't reconcile` (>1), **nothing** for NOT_ENOUGH_DATA / NOT_SUPPORTED. `account_statuses()` has an entry for every account. | `test_reconciliation_marker.py`, `test_reconciliation_service.py` |
| INV-10 | A missing (un-imported) intervening period → a non-zero bridge diff → `OFF` (catch-gaps guarantee), with exact rollup fields. | `test_reconciliation_service.py` |
| INV-11 | Transactions imported by **any** source (CSV between two SB/OFX statements) count inside the bridge. | `test_reconciliation_service.py` |
| INV-12 | Two offsetting gaps (net 0, `off_pair_count == 2`) → `OFF`, never falsely `RECONCILED`. | `test_reconcile.py` |
