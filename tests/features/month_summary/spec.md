# month_summary — feature test contract (FIBR-0231)

The binding design contract is
[`docs/specs/FIBR-0231-plain-english-month-summary.md`](../../../docs/specs/FIBR-0231-plain-english-month-summary.md)
(cold-eyes converged, CLEARED FOR CODE 2026-08-06). This file is the test-scope
stub the app-workflow requires per feature; the authoritative invariants
(INV-1 … INV-14) live in the spec's § 5. Tests here cite those INV numbers.

**The four-file split is a contract, not a preference** (spec § 7). Two rules
decide where an invariant's legs live: an invariant about *window construction*
or *candidate selection* is a **service** test, because the detector is handed
both already computed; one about *period modes* or *slot rendering* is a **UI**
test. A leg filed in the wrong file is either unwritable or vacuous.

Coverage in this directory:

- `test_month_summary.py` — the pure detector `summarise_month`, hermetic: no
  vault, no Qt. INV-1 (all three legs, including the `ast.Div` walk — the only
  one that catches the invariant's own *Breaks when*), INV-5 (five silence
  conditions × a relaxed counterpart each), INV-6 (the three-cell gate matrix),
  INV-8, INV-9's residual sign, the § 4.5 `_MIN_MONTH_BASELINE_MAJOR`
  derivation, and the § 4.6 slot-3 materiality floor.
- `test_month_summary_service.py` — `MonthSummaryService.summary` against a real
  SQLCipher vault. INV-2, INV-3 (three legs — the complete-February whole-month
  rule, the partial head capped at `L_min − 1`, and a leap February's `days`),
  INV-4, INV-7 (three legs, incl. the non-zero-baseline cause family that alone
  catches a baseline window read without `description`), INV-10 (two legs),
  INV-11, INV-12's grep leg, INV-13 leg (c), and § 4.6's tie-break.
- `test_month_summary_strip.py` — `MonthSummaryStrip` under `qtbot`, fed
  hand-constructed `MonthSummary` values. INV-12's render leg, INV-14's 18
  templates + the positive no-signed-amount leg, INV-9's template-selection
  leg, the `residual_minor is None` omission, `isHidden()` after `clear()` and
  on `None`, `PlainText` markup survival, and the 40-character truncation.
- `test_month_summary_home.py` — `HomeView`-level, seeded vault: the strip
  appears and hides as the period selector moves across all five modes, and
  INV-13 legs (a) and (b) over a **guarded** slot (`_on_period_changed`) and an
  **unguarded** one (`set_amount_prefs`).

No network, no real financial data (`testing.md` § 6): every description and
amount here is synthetic.
