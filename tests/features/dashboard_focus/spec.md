# tests/features/dashboard_focus — FIBR-0143 dashboard-focus rework

The Home dashboard is reworked so the **breakdown is the hero**: three side-by-side
columns (Expenditure / Income / Transfers), each a pie + a coloured header (name +
total) + an expandable breakdown tree; a slim Net strip above; a recurring-money card
and the demoted monthly-trend strip below. **No money figure changes** — every total,
slice, and row still comes from the existing integer-exact aggregations (`drill_down`,
`summary`, `monthly_trend`, `RecurringService.summary`); this is purely arrangement.
Full contract: [`docs/specs/FIBR-0143.md`](../../../docs/specs/FIBR-0143.md).

## What the tests enforce

- **`build_breakdown_donut` (ui/charts.py, D3).** A column's ≤8-wedge donut from generic
  `(label, amount)` slices, its **own** cap-and-collapse loop (≤ 8 → all kept, no Other;
  > 8 → top 7 + one Other wedge summing the tail), palette-coloured with **no** reserved
  Uncategorised neutral, empty-safe (no raise). The spending donut `_donut_wedges` /
  `build_donut_chart` are **byte-for-byte unchanged** (regression, so the PDF export is
  provably untouched).
- **Column totals reconcile (INV-1).** Each column header total == its branch
  `drill_down` node `.amount`; Income / Spending nodes == `summary().income` /
  `.expenditure`; each pie's slices are exactly that branch node's direct children and
  **sum to** the header. Computed on integers (INV-8).
- **Node → column map (D2, falsifier).** `drill_down` returns `[Income, Spending,
  Transfers]` but columns render Expenditure / Income / Transfers — the Expenditure
  column shows `nodes[1]` (Spending): its total == `summary().expenditure`, **not**
  `.income`, and its heading renders the app's `tr("Spending")`, not "Expenditure".
- **Transfers excluded (INV-2).** A confirmed transfer is absent from the Expenditure /
  Income pies and present in the Transfers column, grouped by the account pair.
- **Empty branch (INV-4/D8).** A branch with no children → its pie is present but hidden
  and the shared `dashboard_pie_empty_{…}` placeholder shown.
- **Header colour (D7).** With `amount_prefs.colour` on, the Expenditure header's name
  **and** total are `_NEGATIVE_TEXT` and Income's are `_POSITIVE_TEXT`; off → default.
- **Net strip (INV-6).** Shows `summary().net`, sign-coloured when the pref is on.
- **Recurring card (INV-5, unscoped INV-3).** With ≥1 confirmed item the
  `dashboard_recurring_{in,out,net}` labels equal `RecurringService.summary(today)`;
  In / Out colours are **forced by role** (Out is `_NEGATIVE_TEXT` though `monthly_out`
  is a positive value); the hint shows only when **both directional totals are zero**
  (a net-zero-but-nonzero-directional case still shows figures); the card is **unscoped**
  — its figures do not change when the period/account selectors change.
- **Structure + read-only (INV-9).** `refresh()` builds three `dashboard_col_*` columns
  each with `dashboard_pie_*`, `dashboard_heading_*`, `dashboard_total_*`, and
  `dashboard_breakdown_*`; the Net strip, recurring card, and trend chart resolve; the
  trees are read-only; the retired single-tree / three-tile objectNames are gone; the
  getting-started page still wins on a zero-transaction vault.
