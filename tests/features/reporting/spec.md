# tests/features/reporting — FIBR-0012 reporting engine

Contract for the **headless** half of the P10 dashboard (the UI halves live in
`tests/features/dashboard` + `tests/features/transactions_tab`).

Covers:

- **INV-3 — pure period model.** `resolve_period(prefs, today)` maps each of the
  five modes to an inclusive `[start, end]` date range, deterministically from an
  injected `today`; `resolve_trend_months(prefs, today)` returns the 12
  `(year, month)` pairs ending at the period's end month, oldest first. Hermetic
  (fixed `today`), incl. the January previous-month year-boundary and the Feb-29
  leap edge.
- **INV-1 — transfers never counted.** A confirmed transfer pair drops out of
  `summary` / `spending_by_category` / `monthly_trend`, consolidated and
  single-account; an unconfirmed same pair is still counted.
- **INV-4 — income / expenditure / net** over the period's non-transfer rows.
- **INV-5 — category donut** grouped by `category_id` (name for the label only;
  two same-named leaves stay distinct; Uncategorised = the `None` bucket, sorted
  last).
- **INV-6 — trend span** = 12 points, oldest first, ending at the period, empty
  month = a zero point.
- **INV-13 — money exact** (integer `amount_minor` throughout; the only float is
  the display string).

`ReportPrefs` + `AuthService.report_prefs` / `set_report_prefs` (INV-2) live in
the settings suite.
