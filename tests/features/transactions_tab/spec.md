# tests/features/transactions_tab — FIBR-0012 Transactions tab

Contract for the relocated, filterable transaction table (INV-8/9 / D7/D8):

- **INV-8 — relocated table + set-category chain.** The table lives on the
  `tab_transactions` widget; right-click **Set category…** sets a row manual and
  offers to learn a rule exactly as the old Home path did (the chain moved
  verbatim), with the auto-lock guard intact. (These tests moved here from the
  categorisation suite, retargeted to `TransactionsView`.)
- **INV-9 — filters combine (AND).** Search ∧ date-range ∧ account ∧ category,
  each inactive when unset; the visible rows are the AND of the active predicates;
  "Uncategorised" selects `category_id is None`; after a header re-sort the
  right-click still acts on the correct transaction.
- **FIBR-0097 — the table is a model.** The table is a `QTableView` over
  `TransactionsModel`; its contract is
  `docs/specs/FIBR-0097-transactions-table-model.md`, whose INV-2 to INV-4
  and perf test live in this suite.
