# Feature test contract — recurring (FIBR-0142)

Enforces `docs/specs/FIBR-0142.md`. Recurring-money detection is
**suggest-then-confirm** (mirroring FIBR-0011 transfers): a pure
`detect_recurring(rows, today, exponent, excluded_ids)` groups transactions by
`(direction, merchant_key)` where `merchant_key =
normalise_text(merchant_name(description))`, qualifies a group as recurring under
the **Balanced** rule (≥3 members; every magnitude within ±10% of the integer
`median_low`; ≥2 non-zero day-gaps all in one cadence band), and returns the
active ones. The user **confirms** or **dismisses** each; decisions persist in a
schema **v8 → v9** `recurring_decisions` table keyed on `(direction,
merchant_key)`. `RecurringService` partitions the detector's output into
Suggested / Confirmed and computes a monthly-equivalent `RecurringSummary`.

Every on-disk vault uses `tmp_path`; no test touches the network or real
financial data (testing.md § 6). The pure detector + helpers are tested directly
with synthetic `_RecurRow`s (no vault); the service + migration use a real vault;
the Recurring tab uses the pytest-qt `qtbot` fixture.

| INV | Assertion |
|-----|-----------|
| INV-1 | **Money-safety.** An item's `amount` == `to_display_decimal(median_low(magnitudes), exponent)` and `monthly_equivalent` == the D8 factor applied to it, computed from the exact integer member magnitudes — grouping/classification never change a total. |
| INV-2 | **Pure + deterministic.** `detect_recurring` takes no clock (`today` is a param), does no I/O; the same `(rows, today, exponent, excluded_ids)` yields the same list in the same order (D10 sort). |
| INV-3 | **Confirmed transfers excluded.** Ids in `excluded_ids` are dropped before grouping; the service passes `frozenset(confirmed_transfer_txn_ids())`. |
| INV-4 | **Direction from sign; zero excluded.** `amount_minor < 0` → out, `> 0` → in, `== 0` excluded; a payee billing **and** paying forms two groups. |
| INV-5 | **Grouping key.** Two noisy descriptions cleaning to one payee group together (key == `normalise_text(merchant_name(desc))`); a distinct payee stays separate; an all-digits description falls back to non-blank raw text. |
| INV-6 | **Balanced qualification.** ≥3 members; ±10% integer-exact (`100·max(abs(m−med)) ≤ 10·med`) — 110 accept / 111 reject, 90 accept / 89 reject; ≥2 non-zero gaps all one band; same-day-duplicate tolerated (zero gap discarded); 2-distinct-dates rejected; mixed valid bands (7,7,30) rejected; dead-zone gaps rejected. |
| INV-7 | **Activeness.** `(today − last_seen).days ≤ 2·nominal_interval_days(cadence)`: a monthly group 100 days stale is dropped, 55 kept. |
| INV-8 | **Decisions persist by key.** `confirm`/`dismiss`/`reset` upsert `recurring_decisions` on `(direction, merchant_key)`; a dismissed key never appears; a confirmed key appears while still detected; reset → back to suggested. |
| INV-9 | **Partition.** `snapshot(today)` == `(candidates, confirmed, summary)`, one detection pass; a confirmed item that stops detecting vanishes and returns if it reappears (decision survives). |
| INV-10 | **Schema v8 → v9.** `LATEST_SCHEMA_VERSION == 10`; a v8 vault upgrades with an empty `recurring_decisions` table, one atomic step (a wedged step leaves a re-openable v8); the `BackupService` version-ceiling gate rejects a v-too-new vault. |
| INV-11 | **Cadence math.** `nominal_interval_days` == 7/14/30/365; `_add_cadence` clamps Jan 31 +monthly → Feb 28/29 and Feb 29 +yearly → Feb 28; monthly-equivalent uses `ROUND_HALF_EVEN` (a yearly `.XX5` half-way locks the mode). |
| INV-12 | **Recurring tab.** The workspace shows the Recurring tab (`objectName "tab_recurring"`) after Transfers, with Suggested + Confirmed tables; Confirm / Dismiss / Un-confirm drive the service and refresh; a `VaultLockedError` mid-slot is caught; enum values are stable ASCII tokens; strings via `tr()`. |
| INV-13 | **All-accounts / full history.** Members of one merchant across ≥2 accounts group into one item (no account or window filter on the detection read). |
