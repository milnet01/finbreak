# Feature test contract — transfers (FIBR-0011, P09)

Enforces `docs/specs/FIBR-0011.md`. Transfer detection is **suggest-then-confirm**
(ADR-0006): a self-join proposes candidate debit/credit pairs (equal magnitude,
opposite sign, different accounts, within `TRANSFER_WINDOW_DAYS` days); the user
**confirms** or **rejects** each; only confirmed pairs enter the
`confirmed_transfer_txn_ids()` exclusion set (the FIBR-0012 primitive). Nothing is
auto-hidden; rejected pairs are remembered and never re-offered. Schema **v7 → v8**
(one `transfer_pairs` table).

Every on-disk vault uses `tmp_path`; no test touches the network or real financial
data (testing.md § 6). Headless layers (repository self-join, service, migration)
are tested directly; the Transfers tab (two tables + Confirm / Reject / Confirm all
/ Unlink) uses the pytest-qt `qtbot` fixture.

| INV | Assertion |
|-----|-----------|
| INV-1 | **Suggest, never auto-apply.** A perfect debit/credit pair appears in `candidates()` but `confirmed_transfer_txn_ids()` stays empty until `confirm()`. |
| INV-2 | **What matches.** A debit/credit pair of equal magnitude in different accounts at day offsets 0 and 3 **matches**; offset 4 does **not**; amounts off by one minor unit do **not**; two debits (both negative) do **not**; a same-account opposite pair does **not**. The window is the `TRANSFER_WINDOW_DAYS` **bind** — `monkeypatch`ing it to a different value moves the boundary (behaviour, not the literal). |
| INV-3 | **Decided pairs don't resurface.** After `reject(d, c)` the pair is absent from `candidates()`; after `confirm(d, c)` likewise. A re-reject / reject-of-confirmed raises `ValueError` (not `IntegrityError`). |
| INV-4 | **One transfer per transaction.** `confirm` on a txn already in a confirmed pair raises `ValueError`; after `confirm(d, c1)`, `(d, c2)` no longer appears; `confirm_all` on a debit with two candidate credits confirms exactly one. |
| INV-5 | **Exclusion primitive.** `confirmed_transfer_txn_ids()` == the union of both ids of every `'confirmed'` row (and only confirmed — a rejection excludes nothing). |
| INV-6 | **Unlink reversible.** After `confirm` then `unlink(pair_id)`, the pair is back in `candidates()` and out of `confirmed_transfer_txn_ids()`. Unlinking a rejected / absent id is a silent no-op. |
| INV-7 | **Live detection.** `candidates()` reads live vault state each call (no cache); a newly-inserted matching pair appears on the next call with no other action. |
| INV-8 | **Statement-delete cascade.** Confirm a pair whose txns belong to a statement, then `delete_for_statement` → the `transfer_pairs` row is gone (no FK error, no dangling row). |
| INV-9 | **Schema v7 → v8.** `LATEST_SCHEMA_VERSION == 10`; a v7 vault upgrades to v8 with an empty `transfer_pairs` table, one atomic step (a wedged step leaves a re-openable v7). |
| INV-10 | **Transfers tab.** The workspace has **6** tabs; the Transfers tab (`objectName "tab_transfers"`) shows the suggested + confirmed tables; Confirm / Reject / Confirm all / Unlink drive the service and refresh; a `VaultLockedError` mid-slot is caught (no crash). The toolbar Transfers action has a rendering icon. |
| INV-11 | **No network; i18n.** No network import under the new modules (the vault-suite static scan covers them); user strings via `tr()` (convention/ruff, not a unit test). |
| INV-12 | **Transactions untouched.** No transfer operation issues an `INSERT/UPDATE/DELETE` against `transactions` — rows (count, amounts, categories) are byte-identical before and after confirm / reject / unlink. |

**Edges** (beyond the INV table): empty vault → `candidates()` == `[]`; the
**Cartesian** case — two debits × two credits of equal magnitude in-window yield
**four** suggestions, resolved to **two** confirmed pairs by `confirm_all`'s
consumed-set; `confirm` / `reject` store the pair in canonical order regardless of
which side is passed; the display amount is the shared positive magnitude and
From → To reads debit-account → credit-account.
