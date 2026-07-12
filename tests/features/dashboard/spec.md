# tests/features/dashboard — FIBR-0012 HomeView dashboard

Contract for the dashboard half of P10 (INV-7 / D6 / D9):

- **Empty → getting-started; data → dashboard.** Zero transactions shows
  `home_page_empty`; data shows `home_page_dashboard` (selectors, three tiles,
  both `QChartView`s, no table).
- **Tiles** render income / expenditure / net for the selected period + account,
  transfers excluded.
- **Donut collapse (D9).** The pure `_donut_wedges` caps the ring at 8 wedges:
  10 categorised + Uncategorised → 6 coloured + Uncategorised + Other, in that
  order; the two synthetic buckets are pinned neutral colours.
- **Empty donut placeholder.** No spending in the period → the chart is hidden and
  the `dashboard_category_empty` placeholder shown.
- **Selector persistence.** Changing the period selector persists the new
  `ReportPrefs` (via `AuthService.set_report_prefs`) and re-renders; the account
  selector re-renders only (not persisted).
