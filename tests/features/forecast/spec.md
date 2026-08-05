# Feature test contract — forecast (FIBR-0171)

Enforces `docs/specs/FIBR-0171.md`. The **cash-flow forecast** projects the
account balance forward from **confirmed** recurring items (FIBR-0142). Its
starting number is a **real, current balance**: each bank statement's persisted
closing balance (new schema **v10 → v11** `statement_periods.closing_balance_minor`
column) brought current to today by adding the account's actual transactions in the
half-open window `(period_end, today]`. When no account has a recorded balance the
forecast runs in **NET_FLOW** mode — a line from 0 framed as a projected *change*.

The projection core `project_forecast(anchor_minor, items, today, horizon,
anchor_sources)` is **pure** (clock-free, no I/O, **no Decimal** — integer minor
units only), reusing FIBR-0142's `_add_cadence` stepper. `ForecastService`
composes the anchor + `AnchorSource`s and prepares the `ForecastInput`s.

Every on-disk vault uses `tmp_path`; no test touches the network or real financial
data (testing.md § 6). The pure projector is tested directly with synthetic inputs
(no vault); the service + migration + repository use a real vault; the Forecast tab
uses the pytest-qt `qtbot` fixture.

| INV | Assertion | Test |
|-----|-----------|------|
| INV-1 | **Sum consistency.** `end_minor == start_minor + Σ event.amount_minor` (signed, exact integer), both modes. | `test_forecast.py` |
| INV-2 | **Mode switch.** `mode == NET_FLOW` ⟺ `anchor_minor is None`; in NET_FLOW `start_minor == 0` and `anchor_sources == []`. A vault with no recorded balance → NET_FLOW. | `test_forecast.py`, `test_forecast_service.py` |
| INV-3 | **Confirmed-only.** Only `RecurringService.confirmed(today)` items are projected; a suggested/dismissed item never produces an event. | `test_forecast_service.py` |
| INV-4 | **Projection window `(today, horizon]`.** Each item's first occurrence is `next_expected` rolled forward with `_add_cadence` while `<= today`; every event date is strictly `> today` and `<= horizon`; a monthly item clamps Jan 31 → Feb 28. | `test_forecast.py` |
| INV-4a | **The month-end clamp does not ratchet.** Occurrences are the *n*-th step from the anchor (`_add_cadence_n`), not a chain of single steps — chaining re-feeds the clamped day back in, so a Jan-31 item stayed on the 28th (29th in a leap year) for the rest of the projection instead of returning to month-end. A Jan-31 monthly item projects 01-31 → 02-28 → 03-31 → 04-30, and differs between a common and a leap year *only* in the February date. Weekly/fortnightly never clamp and are unchanged. | `test_forecast.py` |
| INV-5 | **Signs.** An IN item raises the running balance, an OUT item lowers it; each `ForecastEvent.amount_minor` sign matches its `direction`. | `test_forecast.py` |
| INV-6 | **Latest balance per account.** `latest_closing_balances` picks the greatest `period_end` (tie: greatest id) non-NULL row per account; NULL-only accounts contribute nothing. | `test_migration_v11.py` |
| INV-7 | **Exact round-trip.** A persisted closing balance round-trips Decimal ↔ minor; a Savings statement with no closing stores NULL and imports fine; the amount→minor prep recovers the exact `median_low` minor. | `test_migration_v11.py`, `test_importer_capture.py` |
| INV-7a (FIBR-0223) | **An unstorable `<BALAMT>` is a `ValueError`, not a crash.** The OFX closing balance is the one amount that bypasses `parse_transaction`, so it inherited none of its money contract: an exponent large enough to overflow the scaling (`1e999999` → `decimal.Overflow` at parse) and a value past SQLite's 64-bit INTEGER (`±1e30` → `OverflowError` at the INSERT) each escaped the `except ValueError` the import wizard renders with. Both are rejected as one, in the importer's INV-4 voice. | `test_importer_capture.py` |
| INV-8 | **Existing paths unaffected.** `ParseResult`'s new field defaults `None`; CSV/manual stores NULL; a pre-v11 `StatementPeriod` round-trips with `closing_balance_minor is None`. | `test_migration_v11.py`, `test_importer_capture.py` |
| INV-9 | **Migration v10 → v11.** Additive nullable `ALTER TABLE ADD COLUMN`, version-gated, old rows NULL; the v11 step adds the column and `run_migrations` then walks the vault on to the current latest (v13, added by FIBR-0193), idempotent, atomic rollback on a wedged ALTER. | `test_migration_v11.py` |
| INV-10 | **Forecast tab.** Present after Recurring (`objectName "tab_forecast"`); renders with zero recurring / zero statements without crashing; headline + provenance reflect the mode. | `test_forecast_tab.py` |
| INV-11 | **Horizon.** Presets compute correct dates (end-of-month; `today + N days`) with `today <= horizon`; the core is clock-free; `horizon == today` is a zero-width forecast, not an error. | `test_forecast.py` |
| INV-12 | **Fill-only balance write.** `update_closing_balance` writes iff the stored value is NULL and the incoming non-None; a stored non-NULL is never overwritten, even by a different value (logs a warning). | `test_migration_v11.py`, `test_preview_threading.py` |
| INV-13 | **Brought-current anchor + step-line.** Anchor = Σ over contributing accounts of (`statement_balance_minor` + `sum_after(account_id, period_end, today)[0]`); `sum_after` sums the half-open `(period_end, today]` window; `len(points) == 2 + len(events)`, `points[0] == (today, start)`, `points[-1] == (horizon, end)`, dates non-decreasing, each interior point equals its event's running total. | `test_forecast.py`, `test_forecast_service.py`, `test_migration_v11.py` |
| INV-14 | **Cash-only anchor (FIBR-0179).** Only `current` / `savings` accounts contribute to the anchor — a debt product prints its closing balance in the *owed* convention (positive = debt, the opposite sign to `amount_minor`), so it can be neither rolled forward by adding transactions nor summed into a cash total. A credit-card balance appears in neither `anchor_sources` nor `start_minor`; a vault whose only balance-bearing account is a debt account runs in `NET_FLOW`. The provenance line names it as excluded *because it isn't cash*, not as "no recorded balance yet". | `test_forecast_service.py`, `test_forecast_tab.py` |
