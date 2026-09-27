## Chunk T08: 17 files read

**Lane that ran:** review-lane (read-only; no Bash).

**Already in my context before I read anything:**
- `~/.claude/CLAUDE.md`
- `/mnt/Games/CLAUDE.md`
- the finbreak project `CLAUDE.md`
- the finbreak `MEMORY.md` index, whose trap notes overlap shared-context § D
- a git snapshot: HEAD 52e5162, clean tree, the FIBR-0331 batch commits

I read every subject file from disk.

**Line counts as read:**
- `tests/features/month_summary/`
  - `test_month_summary.py` 337
  - `test_month_summary_home.py` 375
  - `test_month_summary_service.py` 581
  - `test_month_summary_strip.py` 413
- `tests/features/forecast/`
  - `test_forecast.py` 305
  - `test_forecast_service.py` 177
  - `test_forecast_tab.py` 346
  - `test_preview_threading.py` 103
  - `test_sum_after.py` 50
  - `test_importer_capture.py` 125
  - `test_migration_v11.py` 224
- `tests/features/recurring/test_recurring.py` 831
- `tests/features/spending_alerts/`
  - `test_alert_service.py` 277
  - `test_alerts_ui.py` 312
  - `test_detectors.py` 188
  - `test_alert_dismissals.py` 60
  - `test_migration_v12.py` 88

None of these directories has its own `conftest.py`.

### Findings

**[HIGH] [dim 1] tests/features/spending_alerts/test_alert_service.py:127**
> for day in ("2026-05-25", "2026-06-25", "2026-07-05"):
>     _add(svc, a, day, 300_000, "Salary")

Consequence: the salary rows are 31 days and then 10 days apart. Under `services/recurring.py` `_BANDS`, 31 falls in the monthly band and 10 in the weekly band (5–10). `_classify` returns `None` when gaps fall in different bands. So Salary is never detected as recurring, and the "an IN suggested stream must never fire" half of `test_INV2_confirmed_and_in_streams_do_not_yield_new_recurring` never reaches the OUT-only gate. Deleting the direction filter from the new-recurring path leaves this test green. The pure detector tests cannot catch that either, because `NewRecurringInput` carries no direction. As a result, INV-2's OUT-only rule has no working test in this chunk.
Fix: seed evenly spaced salary dates (e.g. 05-05, 06-05, 07-05). Then assert, before the alert assertion, that `RecurringService.candidates(_TODAY)` contains an IN item for `salary`.

**[MEDIUM] [dim 1] tests/features/forecast/test_forecast.py:166**
> for point, event in zip(fc.points[1:-1], fc.events, strict=True):
>     assert point.on == event.on
>     assert point.balance_minor == event.running_after_minor

Consequence: `project_forecast` builds every interior point *from* `e.running_after_minor`, so this comparison is an identity. Nothing in the chunk checks that `running_after_minor` really is a running total:
- INV-1 checks only `end_minor`.
- INV-5 only has a comment ("The IN event's running_after is above the start", line 143) with no assertion behind it.
- `test_forecast_service.py` checks event amounts and `end_minor` only.

So a change that stores `amount_minor` in the running-balance slot passes every test here. Yet that slot drives both the chart's interior line and the events table's running-balance column.
Fix: assert the literal sequence for this fixture: `[e.running_after_minor for e in fc.events] == [15_000, 12_000, 22_000, 19_000]`.

**[MEDIUM] [dim 7] tests/features/month_summary/test_month_summary_home.py:222**
> def test_the_strip_shows_exactly_what_the_service_says(qtbot, service, mode) -> None:
> ...
>     expected = MonthSummaryService(service.vault).summary(
>         home.current_prefs(), None, date.today()
>     )

Consequence: on the current-month leg, what the test checks depends on the day it runs:
- Before the 7th it only checks that the strip is hidden.
- From the 7th it only checks that the strip is shown.
- The day-29-to-31 cap case is reached only on those dates.

So a regression in whichever branch the run date does not select passes that day. The other half of the problem: the fixture seeds rows and computes `expected` from `date.today()`, while `HomeView.refresh` reads `finbreak.ui.home.app_today` (the pinned-zone app clock). This is exactly the project's known trap: an unpinned app clock on the wrong-day/wrong-month bug class.
Fix: monkeypatch `finbreak.ui.home.app_today` to fixed dates, as `test_INV10_the_strip_and_the_net_tile_share_ONE_clock_reading` already does. Seed relative to that date and parametrize one day before the 7th, one after it, and one on the 29th–31st.

**[MEDIUM] [dim 1] tests/features/spending_alerts/test_alerts_ui.py:227**
> def test_FIBR0216_dismiss_computes_the_alert_set_once_not_twice(

Consequence: the docstring names the defect: the dialog computed the alert set, and then Home's `refresh_alerts` computed it again. But the test builds only an `AlertsDialog`. No `HomeView` or shell is wired to `changed`, so `len(calls) == 1` counts only the dialog's own call. A shell that still calls `home.refresh_alerts()` on `changed` — the exact double computation named — passes. `received == [0]` shows that the signal carries a count, not that anything uses it instead of recomputing.
Fix: count `alerts.alerts` calls across the real wiring: a dialog connected to a `HomeView` the way `MainWindow` connects them, or `MainWindow` itself.

**[LOW] [dim 1] tests/features/recurring/test_recurring.py:680**
> getattr(w, button).click()  # must not raise

These all share one shape:
- the same line in `test_INV12_slots_catch_vault_locked`
- `test_alerts_ui.py:272` `buttons[0].click()  # must NOT raise`, followed by `assert len(_dismiss_buttons(dialog)) == 1`
- `test_forecast_tab.py:196` `w.refresh()  # must not raise`

Consequence: none of these asserts that the patched raiser was actually called. A disabled button, or a button no longer wired to the patched method, makes `click()` a no-op. The test then passes without ever raising `VaultLockedError`. In the alerts case the "row is still present" assertion also holds when nothing happened. The forecast case currently does reach `list_accounts`, through `_coverage_suffix` and `_excluded_names` — `ForecastService` never calls it. But nothing pins that. Sibling tests prove that the non-locked click reaches the service today, which is why this is LOW.
Fix: have each raiser record a hit, and assert the hit count ≥ 1 after the call.

**[LOW] [dim 1] tests/features/forecast/test_forecast_service.py:106**
> # A second recurring series left UNCONFIRMED (suggested only).
> for day in _NETFLIX_DAYS:
>     _add(svc, a, day, -8_000, "Gym")

Consequence: nothing asserts that Gym is detected as a candidate. If Gym stopped detecting, `merchants == {"Netflix"}` would still pass and the "unconfirmed items do not project" claim would go unexercised. Today the risk is low because Gym copies Netflix's cadence, and Netflix's `next(...)` would fail if detection broke. The same missing precondition is at `test_alert_service.py:204`, `test_INV9_suggested_overdue_out_yields_no_missed_debit`.
Fix: assert that `gym` / `insurance` is in `rec.candidates(_TODAY)` before the negative assertion.

**[LOW] [dim 7] tests/features/forecast/test_forecast_tab.py:40**
> today = date.today()

The same pattern appears at:
- `test_recurring.py:569`
- `test_alerts_ui.py:78`, `:100`
- `test_month_summary_home.py:59`, `:233`, `:238`

Consequence: fixtures are seeded from Python's `date.today()`, while every widget under test reads `datetime_format.today()` (a Qt UTC clock converted to `_app_timezone`) at a separate instant. At the default `"system"` zone the two agree except when a run crosses midnight. Across a midnight or month-end crossing, legs whose outcome depends on the date change result:
- the FIBR-0359 "nothing due by horizon" precondition at `test_forecast_tab.py:107`
- `"Alerts (1)"`
- the current-month strip

When they do fail, that failure cannot be reproduced.
Fix: monkeypatch the module-level `app_today` in `ui.forecast`, `ui.recurring`, `ui.alerts_dialog` and `ui.home` to one fixed date. Seed from that date.

**[LOW] [dim 1] tests/features/recurring/test_recurring.py:296**
> def test_INV10_latest_schema_version_is_10() -> None:
>     assert LATEST_SCHEMA_VERSION == 14

Consequence: the name and the INV-10 label (the v8→v9 `recurring_decisions` table) claim one thing, but the assertion pins an unrelated global. The same pin is at line 307 (`== 14` after a v8→v9 walk) and in `test_migration_v12.py:52,58,75,87`. The next schema migration turns five tests red even though their subjects are unchanged. Meanwhile the test says nothing about v10 or recurring. `test_migration_v11.py:45-48` already removed this pin, with the reason stated (FIBR-0327).
Fix: compare against `LATEST_SCHEMA_VERSION`, or assert `>= 9` / `9 in _MIGRATIONS`, as `test_migration_v11.py` does.

**[LOW] [dim 1] tests/features/recurring/test_recurring.py:645**
> assert w._status.text() != ""  # an empty-state message is shown

Consequence: this passes on any non-empty status text, including an error message or the wrong state's text. The claim, that an empty-state message is shown, is not what gets checked.
Fix: assert a substring of the empty-state wording, as `test_forecast_tab.py:94` does with "no confirmed recurring items".

**[LOW] [dim 1] tests/features/spending_alerts/test_alert_service.py:183**
> assert all(":None" not in a.key for a in alerts)

Consequence: this guesses at a key spelling. A None-bucket spike keyed `category_spike:none:…` or `category_spike::…` passes it. The fixture's None bucket (Insurance, Spotify and the 70_000 "Uncategorised misc" row) would genuinely spike if it were not excluded. It is actually caught only by the sibling `test_INV4`'s `len(spikes) == 1`.
Fix: assert `len(_by_kind(alerts, AlertKind.CATEGORY_SPIKE)) == 1` and that its label is "Groceries" in this test too.

### Pre-pass verdicts
- None for this lane (per the tail).

### Dimensions scanned
- 1: 8 findings (1 HIGH, 2 MEDIUM, 5 LOW)
- 4: clean. The orchestrator settled collection and there are no paired macros. The one fixture under `tests/features/forecast/` was checked for collection and none is shadowed.
- 5: clean. No sleep calls, no network. `qtbot.waitSignal` wraps synchronous clicks.
- 7: 2 findings (1 MEDIUM, 1 LOW)
- 11: clean. No pass-bodied or TODO tests, and no test of a removed function.
- 14: clean. No `try/except: pass`, no `filterwarnings`. The raising stand-ins mock layers the tests do not claim to exercise. `QLocale.setDefault` is restored in `finally` (`test_month_summary_home.py:166-173`).
- 6: nothing found. `_DEFAULT` inputs are rebuilt through `dataclasses.replace`, and vaults live under `tmp_path`. See the open question on `_app_timezone`.
- 8: N/A. No skip or xfail markers in this chunk.
- 9: clean. No production endpoints.
- 12: N/A. No per-test timing; none of these tests is in the slowest 20.
- 15: N/A. Nothing failing in this chunk.

### Noted, not mine
- None.

### Possibly wider
- The pattern of seeding a fixture from `date.today()` while the widget reads `app_today()` probably recurs in other UI suites that drive HomeView, Transactions or Statements.
- The pin `LATEST_SCHEMA_VERSION == 14` probably appears in other migration suites outside this chunk.

### Open questions
- Dim 6, `datetime_format._app_timezone`: `test_forecast_tab.py:63` and `test_recurring.py:683` call `MainWindow._enter_unlocked()`, which calls `set_app_timezone(self._prefs.timezone)` and never restores the old value. If a fresh vault's timezone pref is anything other than empty/"system", later tests in the same worker run against a pinned zone, and the `date.today()` mismatch above becomes routine rather than midnight-only. I did not open the default prefs value (outside the one-hop bound). Worth confirming the default, or adding an autouse reset of `set_app_timezone("")`.
- `test_month_summary_service.py:421-422` (the "café rio" literals): the Read output shows both as the same glyphs, so I cannot confirm from text that one is decomposed. The in-test guard `merchant_name(decomposed) != merchant_name(precomposed)` at line 423 passed in the baseline, which settles it. No action unless someone reformats the file with an NFC-normalising editor. The same guard would catch that.
- Unexecuted, would confirm the HIGH finding: `pytest tests/features/spending_alerts/test_alert_service.py::test_INV2_confirmed_and_in_streams_do_not_yield_new_recurring` with an extra `assert any(it.merchant_key == "salary" for it in rec.candidates(_TODAY))`. I expect it to fail.