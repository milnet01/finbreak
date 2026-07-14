# tests/features/dashboard_drilldown — FIBR-0138 drill-down

Contract for the expandable Home dashboard drill-down (the openable
Income / Spending / Transfers tree below the FIBR-0012 donut + trend). Full design
in [`docs/specs/FIBR-0138.md`](../../../docs/specs/FIBR-0138.md).

A seeded two-account vault (income, categorised + uncategorised expense, a nested
category, a confirmed **and** an unconfirmed transfer, merchant-noisy descriptions)
over a fixed `today`. The headless legs run anywhere; the qtbot legs use `pytest-qt`.

Covers:

- **INV-5 — `merchant_name` is pure + total.** Noisy Woolworths variants
  (`"POS 1234 WOOLWORTHS 5678"`, `"woolworths"`, `"WOOLWORTHS 09-08-2026"`, …) fold to
  one grouping key; a blank/whitespace string → `""` (never raises); a digits-only
  string falls back to the trimmed raw (never a blank label); the v1 company suffix is
  **retained** (keys separately); leading noise prefixes strip repeatedly and as a
  phrase (`DEBIT ORDER`), whole-word only (`CARDIFF` is not a `CARD` prefix).
- **INV-3 — `drill_rows_in_range`** returns the 5-tuple `(id, occurred_on,
  amount_minor, category_id, description)` with `rows_in_range`'s window + account-set
  semantics (all / subset / empty-set → `[]`); the extra `description` is populated.
- **INV-1 — the headline: branch totals equal the tiles.** The Income node total ==
  `summary.income`, the Spending node total == `summary.expenditure`; every non-leaf
  node's amount/count == the sum of its children's; `drill_down` is a pure read.
- **INV-4 — category branch.** A nested category aggregates the leaf into the parent
  and the branch; two same-named leaves under different parents stay distinct (grouped
  by id); uncategorised rows form **one** `None`-id node even when a real leaf is named
  "Uncategorised"; an empty category is omitted. The reachable edges: a **mis-set**
  negative row under an Income-root leaf still surfaces under Spending (total holds); a
  **non-leaf category with its own rows** shows both a child node and merchant nodes,
  and the mixed sibling list sorts without raising (the `TypeError` falsifier); a
  category id under **both** sign branches carries only its own bucket in each.
- **INV-5 — merchant grouping** is display-only + total: three noisy Woolworths rows
  collapse to one node (`count == 3`, summed magnitude) drilling to three leaves.
- **INV-2 / INV-6 — transfers.** A confirmed transfer is absent from every
  category/merchant node and present under Transfers grouped by the `from → to` pair
  with `×count`; an unconfirmed pair is ordinary income/spending; the account filter
  keeps a transfer when either leg is selected; the period filter keys on the debit
  leg's date.
- **INV-7 — biggest-first, total order.** Siblings descend by magnitude, then label,
  then the per-node string key; equal-magnitude same-named leaves and same-date
  same-amount txn leaves stay deterministically ordered; the three top nodes are always
  `[Income, Spending, Transfers]`.
- **D8 — empty states.** An income-only period → a zero Spending node (`count == 0`,
  no children) + a zero Transfers node; the three tops are always present.
- **INV-9 — UI wiring (qtbot).** `refresh()` populates `dashboard_drilldown` with three
  tops labelled the passed-in `DrillLabels` and a `None`-node labelled the passed
  `uncategorised` (proving the service emits no untranslated string); a merchant node
  with `count > 1` shows `×N` while a category node stays bare; the tree is read-only;
  the getting-started page still wins on a zero-transaction vault.
- **Ripple.** The `QScrollArea` wrap is transparent to `findChild` (tiles + both charts
  + the tree all still resolve); `DrillNode` / `DrillLabels` import cleanly.

INV-8 (money exact) rides on INV-1 (integer `amount_minor` throughout); the INV-9
no-network + no-schema halves are the existing AST scan + the unchanged
`LATEST_SCHEMA_VERSION`.
