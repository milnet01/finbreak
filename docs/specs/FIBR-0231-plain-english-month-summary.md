# FIBR-0231 — Plain-English monthly summary: the app does the reading

**Status:** 🚧 **CLEARED FOR CODE** (2026-08-06) — four `/cold-eyes` loops, the
last returning **zero CRITICAL and no design-level defect**, with its findings
(test legs that could not fail, and stale rationale) all fixed in place. Those
last fixes have not themselves been read cold; TDD is the next reader. Review
history is §13, superseded draft decisions §13.1.
**Kind:** feature.
**Source:** ROADMAP FIBR-0231 (user-request-2026-08-05, layman-comprehension
suggestions).
**Pairs with:** FIBR-0012 (the dashboard this strip sits at the top of),
FIBR-0172 (`AlertService` — whose spike detector this borrows its baseline shape
from without importing it, §4.2), FIBR-0138 (`drill_down`, the sibling pattern
for keeping a non-QObject service translation-free), FIBR-0142 (`RecurringService`
— whose `merchant_key` grouping this reuses to decide what "one thing" means,
§4.6), FIBR-0175 (compare periods side by side — deliberately *not* this item,
§9).

**Layman:** The dashboard shows you numbers and charts, and leaves you to work
out what they mean. This adds one short line at the top that just says it:
"September cost you R2,340 more than your usual month. Most of it was one thing —
a R1,900 vet bill." When the month is ordinary it says so in a few words, and
when there isn't enough history to know what "usual" means, it says nothing at
all rather than guessing.

---

## 1. Goal

One short block of prose at the top of the Home dashboard that states what
happened to the user's money this month, in words, with no chart-reading
required.

Three properties, in priority order. Where they conflict, the earlier wins:

1. **Never invent a narrative.** Every clause **beyond the verdict** is either
   backed by a figure that clears an explicit threshold, or it is not rendered;
   the verdict itself is always one of three, and "unremarkable" is one of them.
   Silence — rendering nothing at all — is a valid and frequently correct output.
2. **Never overclaim on thin data.** The strip is absent, not vague, when the
   vault cannot support a comparison.
3. **Be worth reading when it does speak.** A user who reads only this line
   should not be misled by having skipped the charts below it. In particular, a
   sentence must never be *more reassuring* than the arithmetic supports.

The feature adds no new subsystem: every figure is derived from rows the
reporting repository already serves.

## 2. Problem

The dashboard (FIBR-0012, extended by FIBR-0138) presents tiles, three drill-down
columns, a recurring-money card and a twelve-month trend chart. Every one of them
is a *presentation of numbers*, and every one leaves the interpretation to the
reader. The roadmap bullet's framing is the whole problem statement: many people
can't, don't, or get it wrong — and then conclude they are bad with money.

Nothing in `src/finbreak` currently generates an interpretive sentence. The
closest existing code is descriptive rather than interpretive:

- `ui/alerts_dialog.py::AlertsDialog._summary` renders one translated template
  per `AlertKind` — it restates a single alert, it does not characterise a month.
- `ui/forecast.py` (295 lines; `wc -l src/finbreak/ui/forecast.py`) has the
  repo's richest clause-assembly code — `_headline_text`, `_coverage_suffix`,
  `_provenance_text`, `_source_clause` — and is the structural pattern this
  feature follows. It also describes rather than interprets.

### 2.1 The illustration in the roadmap bullet does not add up

The bullet's worked example reads:

> "September cost you R2,340 more than your usual month. Almost all of it was one
> thing — a R1,900 vet bill. Take that out and you were R440 better than normal."

`2340 − 1900 = 440` **over** normal, not R440 better. To be R440 *better* after
removing the bill, the bill would have to be R2,780. The illustration is
internally inconsistent, and it is inconsistent in the exact direction this
feature must not be: it states a reassuring conclusion the arithmetic does not
support.

This is not a transcription slip to be quietly fixed — it is evidence that the
"take that out and…" clause has **two** cases and that the reassuring one is the
easier to reach for. §4.6 therefore selects the third sentence's template on the
sign of the residual, never on the sign of the movement, and INV-9 pins it.

### 2.2 The same failure, one layer deeper — why the cause is a *family*, not a row

An earlier draft of this spec defined the cause as *the largest single
expenditure row in the month*, gated only at ≥ 60% of the movement. Executed
against this spec's own constants, that rule reproduces §2.1's failure
structurally rather than as a slip:

```
baseline R12,000/mo (rent R7,000 + living R5,000, every month)
this month R13,500  (rent R7,000 + living R6,500)   → movement +R1,500 → HIGHER
largest single row = the R7,000 rent
  cause gate: 100 × 700000 ≥ 60 × 150000  →  passes by 7.8x
  residual  = 150000 − 700000 = −550000   →  the reassuring template
```

> *"July cost you R1,500 more than your usual month. Most of it was one thing —
> a R7,000 rent payment. Take that out and you were R5,500 better than normal."*

Both of the last two sentences are false. The rent explains none of the movement
because it is in the baseline too, and removing it from one side of a comparison
whose other side still contains it makes an over-budget month read as a good one.
Worse, the trigger is not exotic: it fires whenever the largest routine bill
exceeds the movement, which is the *normal* case for a modest overspend.

Two consequences, both load-bearing for §4.6:

- **The gate cannot be one-sided.** Bounding the cause from below only means the
  larger and more routine a payment is, the more easily it is nominated.
- **The candidate is the wrong object.** In the vault above, the vet bill of
  §2.1 would not even be selected — rent is larger. What explains a movement is
  not a big row; it is a row that is big *relative to what that payee normally
  costs*. So the unit is the **merchant family**, and the quantity is its
  **excess over its own baseline**.

## 3. Scope decisions

Recorded with who made them. User decisions were taken 2026-08-05 in response to
a two-question batch.

1. **Month period modes only; the strip is absent for year modes.** *(User.)*
   `MODE_PREVIOUS_MONTH`, `MODE_CURRENT_MONTH` and `MODE_SPECIFIC_MONTH` get a
   summary; `MODE_YEAR_TO_DATE` and `MODE_SPECIFIC_YEAR` render nothing. A year
   needs a year-over-year comparison and 24 months of history; that is FIBR-0175's
   territory, and building it here would double the design for a case almost no
   vault can satisfy.
   **The gate is an allow-list of exactly those three mode tokens.** Any other
   value — including an unrecognised one, which `resolve_period` silently treats
   as previous-month — renders nothing. A deny-list ("not a year mode") would
   summarise a garbage mode as previous-month, which is defensible for a tile and
   not for a sentence.
2. **Up to three short sentences, from fixed slots.** *(User.)* Verdict, then
   optionally cause, then optionally correction. Each slot has its own evidence
   test, so an unremarkable month collapses to one short sentence without a
   separate "brief mode".
3. **The current (incomplete) month is included, and only *it* truncates.**
   *(Author.)* The user's chosen option keeps `MODE_CURRENT_MONTH`, so the strip
   must appear mid-month — which makes a full-month baseline wrong by
   construction. §4.4 truncates the partial case rather than projecting;
   projection is the invention property 1 forbids. A **complete** month is
   compared whole against whole months, for the reason §4.4 works through.
4. **Account-scoped, following the Home account selector.** *(Author.)* The
   recurring card and the alert count are deliberately unscoped (FIBR-0012 D5,
   FIBR-0172 D8), but those sit *beside* figures rather than describing them. This
   strip characterises the very tiles rendered below it, so an unscoped sentence
   above scoped tiles would contradict them on screen. Scope follows the tiles.
5. **The service returns structured facts, not strings.** *(Author.)* See §4.7.
6. **No new dependency, no schema change, no settings key.** *(Author.)* Every
   figure comes from `ReportingRepository`; thresholds are module constants, in
   one home, exactly as `alerts.py` documents its own (D10 there).

## 4. Design

### 4.1 Shape and placement

Two new modules, mirroring the `services/alerts.py` + `ui/alerts_dialog.py` split,
plus three types in `models.py`:

| File | Contents |
|---|---|
| `src/finbreak/models.py` | `MonthVerdict`, `MonthCause`, `MonthSummary` — the cross-layer shapes |
| `src/finbreak/services/month_summary.py` | the pure detector `summarise_month`, `MonthSummaryInput`, the threshold constants, and the vault-scoped `MonthSummaryService` |
| `src/finbreak/ui/month_summary.py` | `MonthSummaryStrip(QWidget)` — the translated templates and the label |

**The three output types go in `models.py`, not the service**, because that is
where every cross-layer shape in this codebase already lives — `Summary`,
`CategorySpend`, `MonthlyTotal`, `SpendingAlert`, `RecurringItem` — along with
every `StrEnum` (`AccountType`, `CategorySource`, `NegativeStyle`, `CategoryKind`,
`TransferStatus`). `models.py:91` states the convention for the enums in as many
words. `MonthSummaryInput` stays in the service: it is an intra-service
detector-input, exactly like `alerts.py`'s `CategorySpikeInput`.

`home.py` is 615 lines — the **third**-largest UI module, after
`main_window.py` (1785) and `import_wizard.py` (1058); measured 2026-08-06 by
`wc -l src/finbreak/ui/*.py`. The strip gets its own module rather than growing
it further, which is also what lets the templates be tested without a
`HomeView`.

Placement in `HomeView._build_dashboard`: between `self._build_selectors()` and
the Net strip. It is the first thing on the page because a reader who stops after
one line must have read the most useful line.

### 4.2 The baseline

The baseline is the `_BASELINE_MONTHS` calendar months immediately preceding the
summarised month, each measured over the same day window (§4.4).

```python
_BASELINE_MONTHS = 3   # complete prior months averaged into "your usual month"
```

Three is the same figure `alerts.py::_SPIKE_WINDOW` uses, for the same reason —
long enough that one unusual month does not become "usual", short enough to track
a real change in circumstances. It is **deliberately a separate constant, not an
import**, and so is `_MIN_MONTH_BASELINE_MAJOR` (§4.5), which is the one an
implementer is most likely to get wrong: `alerts.py` already defines a
`_MIN_BASELINE_MAJOR = 50`, and `alerts.py` itself sets the visible precedent for
importing private names across services (`from finbreak.services.reporting import
_month_bounds, _prev_month`). The two floors are **not** the same quantity —
`alerts.py`'s floors *one category's* three-month average, this one floors a
*whole month's* spend, so they should not share a value by accident and must not
share a symbol. Hence the different name. `alerts.py` documents its thresholds as
living in one home "so v2 can lift them into Settings"; importing either would
silently couple two features' tuning.

The baseline value is the integer round-half-up mean of the per-month spends,
computed with the same idiom `detect_category_spikes` uses so the two features
round identically:

```python
average = (sum(prior) + _BASELINE_MONTHS // 2) // _BASELINE_MONTHS
```

### 4.3 Which month, and when there is no month

Let `M` be the summarised month — `(end.year, end.month)` from
`resolve_period(prefs, today)`, which is well-defined for the three month modes
(§3 decision 1 excludes the year modes, where `end.month` carries no meaning).

`M` falls into exactly one of three states:

| State | Test | Treatment |
|---|---|---|
| **future** | `M`'s first day > `today` | render nothing (§4.8 condition 4) |
| **partial** | `M` contains `today` | truncated windows, "so far" phrasing |
| **complete** | `today` is strictly after `M`'s last day | whole-month windows, plain phrasing |

**`M` stays partial through its own last day**, which is why the partial test is
"contains `today`" and not "contains `today` and `today` is before the last day".
On the morning of 31 August the month is a day from over and its month-end debits
have not landed; classifying it complete renders "August looked like a normal
month" hours before the largest debits of the month post. The window is one day —
arithmetically honest either way — but the *phrasing* is not provisional in
exactly the case that most needs it to be.

**The future state is reachable in two clicks and must be handled explicitly.**
`home.py:270` is `self._year_picker.setRange(1970, 9999)` and `home.py:265` adds
all twelve months, so on 5 August 2026 a user can select "Specific month / 2026 /
09".

**Condition 4 earns its place on the post-dated-row case, not the empty one.** A
future month with no rows at all is already silenced by condition 5
(`spend_minor == 0`), so that case argues nothing. What condition 4 alone catches
is a future `M` that *does* hold rows: nothing in `services/transactions.py`
guards against a post-dated entry and no date editor sets `setMaximumDate`, so a
user who mistypes a year books a row into next September. `M` then has a little
spend, three baseline months of real data, and `movement = spend − baseline` is
large and negative — the strip announces that a month which has not happened was
much cheaper than usual, the most reassuring possible sentence, out of data that
is one typo. §4.7 leaves `spend_minor` computed rather than forced for exactly
this reason, and INV-5's condition-4 leg is built on it.

### 4.4 Like-for-like windows — whole months when complete, a common head when not

`len(x)` is month `x`'s length from `calendar.monthrange`, and
`L_min = min(len(M), len(b₁), len(b₂), len(b₃))`.

```
complete M:  window(x) = the whole of calendar month x, for M and every baseline
             days      = len(M)

partial  M:  window(x) = days [1 .. head] of x, for M and every baseline
             head      = min(today.day, L_min − 1)
             days      = head
```

`days` is the field `MonthSummary` carries: the number of days **of `M`** its
window covers. For a complete `M` the four windows are deliberately *not* the
same length — that is the point of the rule.

**Why a complete month is not truncated.** A common day count sounds like the
neutral choice and is neutral only for **perfectly uniform** spend. Real spend is
a mixture of daily flow and fixed monthly events, and a fixed event lands on a
different *day number* in a short month than in a long one — banks pull a debit
order back to the last available day. Truncation then includes it on one side of
the comparison and excludes it from the other. Worked at exponent 2, rent R7,000
by debit order on the 30th (February: the 28th) and R5,000 of other spend over
days 1–20, **behaviour never changing**:

```
M = February (28d); baselines Nov(30) Dec(31) Jan(31); days = 28
  Nov/Dec/Jan windows [1..28] = R5,000 each   (rent on the 30th — OUTSIDE)
  M window          [1..28]   = R12,000       (rent on the 28th — INSIDE)
  movement = +R7,000 -> HIGHER, and the landlord's own baseline reads 0,
  so the cause clause names it:
  "All of it was one thing — Landlord, R7,000 more than usual."
```

Every clause of that sentence is false, it fires every February for any user with
a month-end debit order, and the March mirror (`days = 28` again, now dropping
March's day-30 rent while keeping February's day-28 rent) renders the reassuring
inverse. §2.2's merchant-family rule does **not** save it: truncation applies to
the family's baseline windows too, so the landlord's baseline is 0 and its excess
is the full R7,000.

**And the artefact it was introduced to remove is not a fabrication.** Comparing
whole months of unequal length does bias February, for uniform daily spend `d`:

```
M = February (28d), baseline Nov(30) Dec(31) Jan(31), mean 30.667d
  100 × |movement| = 8.70 × baseline   ->  8.70%, against a 10% gate
```

February is the worst case in the calendar (March is +3.33%, April 0%). The bias
never clears the relative gate on its own, so it invents no narrative — it is a
**standing bias** that can tip a genuine −1.5% month to `LOWER`, recorded in §6.1.
It is also *true*: a household that buys groceries daily really did spend less in
February, and "February cost you less than your usual month" is what a reader
means by the comparison. Trading a sub-threshold, true bias for a supra-threshold
fabrication with a named payee is the wrong direction, and §1 property 1
(never invent) outranks property 3 (never over-reassure).

**Why the partial head is capped at `L_min − 1`.** A partial `M` must truncate —
there is no whole month to compare — and the same debit-order trap applies. The
cap excludes **every** window month's final day, which is the day a nominally
later debit is pulled back to, so a fixed monthly payment is either inside all
four windows or outside all four. No three consecutive months are all 31 days — Jul–Aug and
Dec–Jan are the only adjacent 31-day pairs — so any four consecutive months
include at least one of February, April, June, September or November. `L_min ≤ 30`
always, and the cap is therefore at most 29; with a February in range it is 27,
or 28 for a leap February. The consequence is that the window **stops advancing** near
month end — on day 30 of a March with February in its baseline the strip still
describes days 1–27 — which is the honest reading, and the "so far" phrasing says
so. The `_MIN_ELAPSED_DAYS` gate (§4.8 condition 3) is unaffected: the cap is
never below 27.

`today.day` **includes the partly-elapsed current day**. The alternative
(`today.day - 1`) is equally defensible; `today.day` is chosen so the strip's
window matches the Transactions tab's notion of "up to today".

What this rule does **not** fix is a bank moving a debit off a weekend by a day or
two, which lands it on a different day number for reasons no window rule can see.
That is stated in §6.1 rather than mitigated.

### 4.5 What counts as spend

Spend is the sum of magnitudes of rows with `amount_minor < 0` in the window,
excluding confirmed transfers — the same exclusion every reporting figure applies
via `TransferDetectionService.confirmed_transfer_txn_ids()`, called from
`reporting.py`, `alerts.py`, `recurring.py` and `pdf_export.py`.

**A row that is not spend is not a family member either.** §4.6's families are
built from the window's spend rows alone, so a positive row never joins a family,
never shifts which row is a family's *earliest* (and so never changes
`MonthCause.name`), and never nets against an excess. This is also the one place
the grouping differs from `RecurringService`'s:
`src/finbreak/services/recurring.py:175-181` keys on
`(direction, merchant_key)` because it groups inflows and outflows alike, whereas
every row here is an outflow, so the direction component is constant and the key
reduces to `merchant_key`. The *derivation* of the key —
`normalise_text(merchant_name(description))` — is identical, which is what §4.6
reuses.

Uncategorised rows **are** included. A spike alert excludes them because it must
name a category; a month total must not, or the sentence would describe a
different number than the tile below it.

**Positive rows are never netted against spend.** A merchant with a R2,000 charge
and a R2,000 refund in the same window contributes R2,000 of spend, not zero.
This keeps the strip's figure equal to the tile's (INV-10), which is the property
§3 decision 4 exists to protect; the cost is that a fully reversed purchase can
still be nominated as a cause, recorded in §6.10.

`ReportingService.summary` buckets `amount_minor == 0` into expenditure (`else:
expenditure_minor += -amount_minor`) where the rule above excludes it. The two
agree, because a zero row contributes zero either way. INV-10's fixture carries
one so the agreement is **documented at the point it matters** — but no assertion
over it can go red, since `-0 == 0` on both sides, and §11 says so rather than
claiming coverage the leg does not have.

**All four windows are read with
`ReportingRepository.drill_rows_in_range(start_iso, end_iso, account_ids)`** —
`M`'s and every baseline month's. `rows_in_range` returns
`(id, occurred_on, amount_minor, category_id)` with **no `description`**, and
§4.6's `excess` needs per-family sums in the *baseline* windows as well as in
`M`. Specifying `rows_in_range` for the baselines would make every family's
baseline zero, which collapses `excess(f)` to `spend_in_M(f)` and silently
restores the largest-row rule §2.2 exists to reject — and every fixture whose
cause family has no baseline spend would still pass.

Thresholds. All arithmetic is integer minor units; `exponent` comes from
`read_minor_unit_exponent`, and `minor(n) = n * 10**exponent` converts a
major-unit constant. (It is *not* named `floor` — it scales, it does not round.
`services/transactions.py::to_minor` does the same job for a `Decimal`; it is not
reused because INV-1 forbids `Decimal` in this module.)

```python
_MATERIAL_NUM, _MATERIAL_DEN = 10, 100   # a move must be >= 10% of baseline
_MIN_MOVE_MAJOR = 100        # ...and >= 100 major units in absolute terms
_CAUSE_NUM, _CAUSE_DEN = 60, 100  # one family "explains" a move at >= 60% of it
_MIN_ELAPSED_DAYS = 7        # a partial month says nothing until day 7

# DERIVED, not chosen: the baseline floor is exactly where the two materiality
# gates cross. Below it the absolute gate binds alone, so the relative gate is
# dead and a NORMAL verdict can absorb an arbitrarily large proportional swing.
_MIN_MONTH_BASELINE_MAJOR = _MIN_MOVE_MAJOR * _MATERIAL_DEN // _MATERIAL_NUM
```

**The floor is derived rather than picked, and it makes the absolute gate
redundant — which is stated here rather than left for an implementer to notice.**
§4.8 condition 2 guarantees `baseline >= minor(_MIN_MONTH_BASELINE_MAJOR)` for
anything that renders at all. The relative gate then requires
`abs(movement) >= baseline / 10 >= minor(_MIN_MOVE_MAJOR)` — which *is* the
absolute threshold. So **relative-pass implies absolute-pass, at every exponent**:
above the floor the relative gate binds everywhere and the absolute gate can never
change an outcome; below the floor nothing renders. The absolute gate is kept as
belt-and-braces and becomes load-bearing only if the floor is ever lowered.
§4.6, INV-6 and §11 are written to that fact rather than around it. The measured
case that produced the value — a R60 baseline reading `NORMAL` on a +165% swing
under the inherited floor of 50 — is recorded in §13.1.

### 4.6 The three slots

Let `spend` be `M`'s window spend, `baseline` the §4.2 average, and
`movement = spend − baseline` (signed; positive means spent more).

**Slot 1 — verdict.** Always present when the strip renders at all.

`movement` is **material** iff *both* gates pass:

```
_MATERIAL_DEN * abs(movement) >= _MATERIAL_NUM * baseline     # relative
abs(movement) >= minor(_MIN_MOVE_MAJOR)                        # absolute
```

**Above the §4.8 floor the relative gate is the one that binds** — the absolute
gate cannot fail while the relative one passes (§4.5). It is written as a
conjunction anyway, so that lowering the floor cannot silently re-open the dead
zone the floor was derived to close. Material and positive → `HIGHER`; material
and negative → `LOWER`; otherwise → `NORMAL`.

**Slot 2 — cause.** The unit is a **merchant family**, not a row (§2.2). For
each family in `M` — keyed by `normalise_text(merchant_name(description))` from
`finbreak.text`, over the window's **spend rows only** (§4.5) — compute

```
excess(f) = spend_in_M(f) − baseline_mean(f)

baseline_mean(f) = (sum(spend_in_each_baseline_window(f)) + _BASELINE_MONTHS // 2)
                   // _BASELINE_MONTHS
```

**The divisor is always `_BASELINE_MONTHS`** — a baseline window in which the
family did not appear contributes `0` to its own mean, and the rounding is §4.2's
idiom so the two means round identically. Both halves must be stated because both
are genuinely ambiguous and each changes every `excess`: dividing instead by the
number of windows the family *appeared* in would give a family seen once at R900
in three windows a mean of 900 rather than 300, a R600 swing in the quantity the
gate and slot 3 are both built on. (This is deliberately **not** the convention
§4.8 condition 1 applies to whole months. A month with no rows was never
imported; a family absent from an imported month is a real zero — the user
genuinely did not pay that merchant.)

The candidate is the family with the greatest `excess`. The clause renders only
when *all* hold:

- the verdict is `HIGHER`. A single large *expense* cannot explain spending
  *less*, and the transaction that would explain a `LOWER` month is the one that
  is absent — unobservable by construction. INV-8 pins it.
- a candidate family exists with `excess > 0`.
- `_CAUSE_DEN * excess >= _CAUSE_NUM * movement`.

`MonthCause` carries the family's **excess** — the quantity the gate tested, the
quantity slot 3 removes, and the quantity slot 2 prints. It does **not** carry
the family's gross spend in `M`: no template, invariant or test consumes it, and
holding both invites the sentence to print the gross figure, which for a family
with real baseline spend is a different and false number ("R1,900 more than
usual" when the excess is R1,500). Ties resolve to the lexicographically smaller
`merchant_key`, so the sentence is stable across refreshes.

`MonthCause.name` is `merchant_name(description)` of the family's **earliest**
row in `M`, ties broken by lowest row id — the convention `recurring.py` already
uses for a group's display name, and a fixed rule so the label cannot change
between two refreshes of the same data.

Re-run against §2.2's vault: rent's `excess` is `7000 − 7000 = 0`, so rent is not
the candidate. The candidate is the living-costs family at `6500 − 5000 = 1500`,
which *does* clear `0.6 × 1500 = 900`. Its excess **equals** the movement exactly,
so slot 2 takes the `excess == movement` template ("All of it was one thing") and
`residual` is 0 — below the slot-3 floor, so `residual_minor` is `None` and slot 3
is correctly omitted. Against §2.1's vault, the vet family's
`excess` is `1900 − 0 = 1900`, clearing `0.6 × 2340 = 1404`. The rule selects the
right object in both, and in neither does it select rent.

**Slot 2 splits three ways, not two.** `excess < movement` → "Most of it";
`excess == movement` → "All of it"; `excess > movement` → "All of it and more".
The equality case is not a corner: it is where §2.2's own flagship vault lands
(excess R1,500, movement R1,500), and folding it into the `>` branch claims "and
more" about a quantity that is exactly equal — a small false clause in the
sentence the whole rejected-design argument rests on.

**Slot 3 — correction.** `residual = movement − excess`, and the template is
chosen by the **sign of `residual`** (§2.1). The materiality floor reuses the
slot-1 constant rather than adding one: every other rendered figure in this
design clears an explicit threshold (§1 property 1), and without it a residual of
40 minor units renders "Take that out and you were R0.40 better than normal."

**The detector owns that floor, exactly as it owns slot 2's gate.** It sets
`residual_minor = None` whenever no correction sentence is warranted — when there
is no cause, or when `abs(residual) < minor(_MIN_MOVE_MAJOR)` — so
`residual_minor is not None` *is* the render condition, precisely as
`cause is not None` is slot 2's. The alternative was to leave a sub-threshold
residual as an integer and have the strip compare it, which would put a private
service threshold (`_MIN_MOVE_MAJOR`, and `minor()` to scale it) inside
`ui/month_summary.py` — against §4.7's facts-out/phrasing-in seam and §3
decision 6's single home for thresholds. The strip renders slot 3 iff
`residual_minor is not None`, and never evaluates a threshold.

**The templates.** These are the feature's actual deliverable; `MonthSummaryStrip`
owns them and calls `tr()` on each. Named placeholders per `coding.md`.

| Slot | State | Template |
|---|---|---|
| 1 | `HIGHER`, complete | `"{month} cost you {amount} more than your usual month."` |
| 1 | `HIGHER`, partial | `"So far, {month} has cost you {amount} more than usual by this point."` |
| 1 | `LOWER`, complete | `"{month} cost you {amount} less than your usual month."` |
| 1 | `LOWER`, partial | `"So far, {month} has cost you {amount} less than usual by this point."` |
| 1 | `NORMAL`, complete | `"{month} looked like a normal month."` |
| 1 | `NORMAL`, partial | `"So far, {month} looks like a normal month."` |
| 2 | `excess < movement`, complete | `"Most of it was one thing — {name}, {amount} more than usual."` |
| 2 | `excess < movement`, partial | `"Most of it has been one thing — {name}, {amount} more than usual."` |
| 2 | `excess == movement`, complete | `"All of it was one thing — {name}, {amount} more than usual."` |
| 2 | `excess == movement`, partial | `"All of it has been one thing — {name}, {amount} more than usual."` |
| 2 | `excess > movement`, complete | `"All of it and more was one thing — {name}, {amount} more than usual."` |
| 2 | `excess > movement`, partial | `"All of it and more has been one thing — {name}, {amount} more than usual."` |
| 3 | `residual < 0`, complete | `"Take that out and you were {amount} better than normal."` |
| 3 | `residual < 0`, partial | `"Take that out and you are {amount} better than normal so far."` |
| 3 | `residual > 0`, complete | `"Even without it you were {amount} above normal."` |
| 3 | `residual > 0`, partial | `"Even without it you are {amount} above normal so far."` |
| month | year == `today`'s | `"{month_name}"` |
| month | year differs | `"{month_name} {year}"` |

**Every slot carries the partial variant, not just slot 1.** §6.2 accepts a
partial month's verdict flipping day to day *on the grounds that* the phrasing
marks the figure provisional; a design where sentences 2 and 3 are unqualified
past tense about a month that is a third over does not deliver that mitigation.
INV-14 pins exhaustiveness across all three slots.

**Only slot 1 carries the literal "So far," prefix.** Slots 2 and 3 mark
themselves provisional by **tense** — present perfect ("has been one thing") and
present ("you are … so far") — because all three slots render into one joined
sentence (below), and three "So far,"s in a row is not prose anyone wants to
read. The mitigation is the provisional *marking*, not the particular word, and
every partial template still carries one.

**`{amount}` is always a magnitude.** The strip renders
`_format_amount(to_display_decimal(abs(v), exponent), symbol)` — the sign is
carried by the chosen template and never by the figure. `movement_minor` and
`residual_minor` are the two signed fields in the design and they are exactly the
two that feed these templates, so without the `abs` the `LOWER` and "better than
normal" rows render "cost you -R500 less than your usual month" and "you were
(R440) better than normal", depending on the user's `NegativeStyle`. Slot 2's
`{amount}` is `cause.excess_minor`.

**`{month}` needs no clock in the strip.** It is
`QLocale().standaloneMonthName(m)` for the month parsed from
`MonthSummary.month`, composed with the year through the two `month` templates
above (whose placeholder is `{month_name}`, distinct from slot 2's `{name}`,
which is a merchant) rather than by concatenation — `coding.md` forbids building display strings
with `+` or f-strings, and month/year order is precisely what some locales
reorder. Which template applies is decided by `MonthSummary.show_year`, computed
by the service, which already has `today`. That also makes INV-14's matrix
deterministic instead of depending on the real system date.

No template needs Qt's `%n` numerus form — every one interpolates an amount, a
name or a year, never a count.

**The rendered slots are one label, joined by a single space.** The strip holds
**one** word-wrapping `QLabel` and sets its text to the rendered slots joined with
`" "`, following `ui/forecast.py`'s clause assembly — not three labels in a
layout. One label is what makes the block wrap as prose rather than breaking at
slot boundaries, and it is what INV-13's "the strip is hidden" and INV-14's
per-combination assertions both read.

`MonthCause.name` is derived from raw bank text (§6.4), so the label sets
`Qt.TextFormat.PlainText` — a description containing `<b>` or `<img src=…>` would
otherwise be rendered as rich text by `QLabel`'s default `AutoText` sniffing,
showing something other than the user's transaction and attempting a local
resource load. `name` is **truncated to 40 characters** before interpolation: if
it is longer, the first 39 characters plus `…` (U+2026). Plain character
truncation, deliberately **not** `QFontMetrics.elidedText`, which measures pixels
and would make the rendered sentence depend on the widget's width — and so make
INV-14's assertions depend on layout. **The truncation is the strip's, not the
service's** — `MonthCause.name` is carried at full length so INV-12's "derived
from the user's own text" stays true of the data and the shortening stays a
display concern.

### 4.7 The seam and the shapes

`summarise_month` returns **facts** — an enum verdict and integer amounts — and
never a user-facing string. `MonthSummaryStrip`, a `QObject`, owns every template.

This is the FIBR-0138 `DrillLabels` pattern taken one step further. `DrillLabels`
injects translated *labels* into the service because drill nodes carry a `label`
field; a sentence has grammar — clause order, sign-selected templates — which
cannot be expressed as injected nouns. So the direction is reversed: facts out,
phrasing in the UI. This keeps `services/month_summary.py` entirely
translation-free and makes the detector testable with no Qt translation context.

```python
# --- models.py -------------------------------------------------------------
class MonthVerdict(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"
    NORMAL = "normal"

@dataclass(frozen=True)
class MonthCause:
    merchant_key: str
    name: str                  # merchant_name() of the family's earliest row in M
    excess_minor: int          # positive; spend in M minus the family's baseline mean

@dataclass(frozen=True)
class MonthSummary:
    month: str                 # "YYYY-MM"
    partial: bool
    days: int                  # days of M its §4.4 window covers
    exponent: int              # so the strip can format without a vault handle
    show_year: bool            # M's year differs from today's (§4.6)
    verdict: MonthVerdict
    spend_minor: int           # positive magnitude
    baseline_minor: int        # positive magnitude
    movement_minor: int        # signed
    cause: MonthCause | None
    residual_minor: int | None # signed; None iff no slot 3 (§4.6) — i.e. no
                               # cause, or abs(residual) below the floor

# --- services/month_summary.py ---------------------------------------------
@dataclass(frozen=True)
class MonthSummaryInput:
    month: str
    partial: bool
    days: int
    show_year: bool
    spend_minor: int
    prior_minor: tuple[int, ...]        # one per baseline month that held >= 1
                                        # non-transfer SPEND row in ITS window
    started: bool                       # False iff M's first day is after today
    candidate: MonthCause | None        # greatest-excess family, excess > 0

def summarise_month(
    item: MonthSummaryInput, exponent: int
) -> MonthSummary | None: ...

class MonthSummaryService:
    def __init__(self, vault: Vault) -> None: ...
    def summary(
        self,
        prefs: ReportPrefs,
        account_ids: frozenset[int] | None,
        today: date,
    ) -> MonthSummary | None: ...

# --- ui/month_summary.py ---------------------------------------------------
class MonthSummaryStrip(QWidget):
    def set_summary(
        self, summary: MonthSummary | None, symbol: str
    ) -> None: ...    # None hides the strip
    def clear(self) -> None: ...    # hides the strip; needs no symbol
```

**`MonthSummaryService.summary` owns the §3 decision 1 mode allow-list** and
returns `None` for any other mode, so INV-4 is testable without Qt and
`HomeView` does nothing but hide the strip on `None`. `today` is required, not
defaulted — unlike `ReportingService`, whose `today: date | None = None` predates
this contract.

**The allow-list tests the whole `ReportPrefs`, not just the mode token.**
`MODE_SPECIFIC_MONTH` is admitted only when `prefs.year` and `prefs.month` are
both non-`None`; otherwise `summary` returns `None`. `resolve_period` silently
falls back to previous-month in that case, which is the same silent substitution
§3 decision 1 refuses for an unrecognised token — defensible for a tile, not for
a sentence that names a month while the selector reads "Specific month".

`summarise_month` takes no clock: `partial`, `days`, `show_year` and `started`
are everything it needs from it, and the service computes them all. **`symbol` is
a parameter of the strip's `set_summary`, not a field** — `HomeView.refresh()`
already holds `symbol = self._reporting.base_currency()` and passes the same
value to `_render_net`, so carrying it through the service would duplicate a fact
the call site has. **`clear()` exists because that is not true everywhere**:
`HomeView`'s `except VaultLockedError` blocks must hide the strip (INV-13) and
have no `symbol` in scope — `base_currency()` is itself a vault read that would
raise the same exception. A hide path must therefore not require one.

`exponent` **is** a field, because the opposite is true of it:
`read_minor_unit_exponent` is not imported in `home.py`, so the strip has no
other source. `negative_style` is not needed at all — every rendered amount is a
magnitude (§4.6).

**Field values for a future `M`.** The service builds a complete input before the
detector can reject it, so §4.3's third state needs values: `started = False`,
`partial = False`, `days = len(M)`. None is consulted — condition 4 fires first —
but every field is non-optional and an implementer must not have to guess.
`partial = False` matters specifically: setting it `True` would let condition 3
fire first, and INV-5's condition-4 leg would then pass without ever exercising
`started`. `spend_minor` and `prior_minor` are **computed normally, not forced** —
nothing in `services/transactions.py` guards against a post-dated row and no date
editor sets `setMaximumDate`, so a future month genuinely can hold rows.

**A month "has data" iff its window holds at least one non-transfer *spend* row**
(`amount_minor < 0`) — for `M` and for each baseline month alike, over that
month's own §4.4 window. `prior_minor` carries only such months, so
`len(prior_minor) < _BASELINE_MONTHS` *is* the has-data test, and every entry in
it is strictly positive.

**There is deliberately no `month_has_rows` field.** Under the spend-row test the
fact it would carry is exactly `spend_minor > 0`, so §4.8 condition 5 tests
`spend_minor == 0` directly. (An earlier draft added the field because a tuple of
totals cannot distinguish "no rows" from "rows summing to zero" — true while the
test was *any* row, and no longer true once it is a spend row, since a negative
amount cannot sum to zero. §4.8 condition 1 carries the ruling that made the
test a spend row.)

### 4.8 The silence ladder

`summarise_month` returns `None` — the strip hides entirely — when any holds, in
this order:

1. `len(prior_minor) < _BASELINE_MONTHS`. "Your usual month" is a claim about
   three months. **A baseline month with no non-transfer *spend* rows in its
   window is missing data, not a zero-spend month**, and the service omits such
   months from `prior_minor` (§4.7). That includes a month holding only income
   rows: in a personal-finance vault a month with a salary and no card spend is
   in practice always a partial import — the salary account imported, the card
   account not — and admitting it as a real `0` deflates both the baseline *and*
   every family's mean. Worked at exponent 2: baselines December R12,000, January
   R12,000, November income-only, unchanged R12,000 of spend in `M` →
   `baseline = R8,000`, `movement = +R4,000` → `HIGHER`, with every family's mean
   cut by a third so the 60% cause gate becomes easy to clear. Treating it as a
   gap costs a month of history and silences the strip instead.
2. `baseline < minor(_MIN_MONTH_BASELINE_MAJOR)`. Too little money moving to
   characterise. **Note this floor is a whole-month-sized figure applied to a
   possibly-truncated baseline** — see condition 3.
3. `partial and days < _MIN_ELAPSED_DAYS`. Six days pro-rated against six days is
   arithmetically fine and epistemically worthless — one grocery run swings it
   past every threshold. The comparison is `<`, so **this condition** stops
   binding on the 7th.

   **It does not follow that the strip speaks on the 7th, and an earlier draft
   said it did.** Condition 2 is evaluated first and against the *same truncated
   windows*, so early in a partial month it compares a few days of spend to a
   whole month's floor, and it is condition 2 — not condition 3 — that is
   actually binding. Worked at exponent 2, a household spending a uniform
   R100/day: on day 7 the baseline is `7 × R100 = R700`, under the R1,000 floor,
   so the strip is silent; it first speaks on **day 10**. At R50/day, day 20. At
   roughly R33/day the head caps at `L_min − 1` before the baseline ever reaches
   the floor, and the **current-month** strip never renders at all — though the
   same vault renders normally for a complete month.

   Left as-is rather than pro-rated: scaling the floor by `days / len(M)` would
   re-open the dead zone §4.5 derived the floor to close, and silence on thin
   data is §1 property 2's intended direction. What was wrong was only the
   sentence claiming otherwise. Measured 2026-08-06 during the implementation
   review.
4. `not started` — `M`'s first day is after `today` (§4.3).
5. `spend_minor == 0` — `M` held no non-transfer spend row in its window, by the
   same test condition 1 applies to the baselines. An un-imported month between
   two imported ones would otherwise report the most reassuring possible sentence
   out of absent data, exactly as a future month would.

The strip is also absent, without consulting the detector, when `HomeView` is
showing its getting-started page (`transaction_count() == 0`, FIBR-0012 INV-7).

**Condition 5 is all-or-nothing, and the gap that leaves is larger than the case
it closes** — a *partly* imported month passes every condition here and renders a
confident false verdict. That is §6.9, stated there in full rather than twice.

### 4.9 Wiring

`HomeView.__init__` gains a `month_summary: MonthSummaryService` parameter.
`main_window._build_workspace` constructs it alongside the other five services.

**The parameter is added last, before `amount_prefs`, and every caller must pass
`amount_prefs` by keyword.** `HomeView.__init__` today is
`(reporting, accounts, auth, recurring, alerts, amount_prefs=None, parent=None)`,
so `amount_prefs` is the sixth positional slot; inserting `month_summary` ahead of
it silently re-binds any positional sixth argument to the new service. The
signature carries no comment warning of this — that is why the rule is stated
here, and why §7's ripple is a list of every file constructing a `HomeView`.

`HomeView.refresh()` calls the service and passes the result to the strip, at the
point where `_render_net` is called today. It computes `today = date.today()`
**once**, at the top, and passes that one value to both
`MonthSummaryService.summary` and the reporting reads — the strip and the tiles
must not straddle midnight, which is precisely the equality INV-10 asserts.

**Error handling.** `HomeView.refresh()` has **8** call sites, of which **6 are
unguarded**:

| Site | Guarded by `except VaultLockedError` |
|---|---|
| `home.py:127` (`__init__`) | no |
| `home.py:350` (`_on_period_changed`) | yes |
| `home.py:358` (`_on_account_changed`) | yes |
| `home.py:374` (`set_amount_prefs`) | no |
| `main_window.py:799` (`_refresh_tab`) | no |
| `main_window.py:830` (`_show_home`) | no |
| `main_window.py:1499` (`_on_import_done`) | no |
| `main_window.py:1508` (`_refresh_after_statement_change`) | no |

(`grep -n "self\.refresh()\|_home_tab\.refresh()" src/finbreak/ui/home.py
src/finbreak/ui/main_window.py` → 8, 2026-08-05.)

The **exception** is pre-existing and unchanged: `refresh()` already issues
`transaction_count()`, `base_currency()` and `summary()` against the vault before
this feature adds a fourth kind of read (six reads in all, §10), so every one of
those six sites can already raise
`VaultLockedError` today. The **harm is not**. Before this item the residue of a
mid-refresh lock is a stale *figure* in a tile, which is ambiguous; after it, the
residue is a stale *sentence naming a month*, which is a positive false claim —
the thing INV-13 exists to prevent.

**So `refresh()`'s first statement is `self._month_strip.clear()`**, before
`transaction_count()`. One line, no new guard, and it closes all eight sites
rather than the two that happen to be wrapped: whatever raises inside `refresh()`,
and wherever it was called from, the strip is already empty.

**One site needs a second clear, and it is the one that is not a `refresh()` call
at all.** `_on_period_changed` **persists** the new period before it re-renders,
and that write is itself a vault operation:

```python
self._auth.set_report_prefs(self._current_prefs())   # can raise
self.refresh()                                       # ...so this never runs
```

A lock landing on the write returns from the `except` without `refresh()` ever
being entered, so `refresh()`'s clear cannot help — while the selector has
already moved, making the standing sentence name the wrong month. That slot
therefore clears **before** the write. Corrected 2026-08-06 after the
implementation review; the earlier claim that one line in `refresh()` closed
every path was true of the eight `refresh()` call sites and false of the
write-then-refresh ordering above it. INV-13 pins all three: a guarded slot, an
unguarded one, and the prefs write.

## 5. Invariants

- **INV-1** — integer-only arithmetic. No `Decimal` or `float` appears in
  `services/month_summary.py`, and no true division is performed on money.
  *Breaks when:* a percentage is computed as `movement / baseline` instead of by
  cross-multiplication — which silently returns a `float` and defeats the whole
  minor-unit discipline.
  *Test:* three legs, because the stated breach is invisible to the first two —
  `movement / baseline` keeps the float inside the comparison, so every returned
  field stays `int`, and it contains neither `Decimal` nor `float(`.
  (a) for a returned `MonthSummary`, each of `days`, `exponent`, `spend_minor`,
  `baseline_minor`, `movement_minor` — plus `cause.excess_minor` when `cause` is
  not `None` — satisfies `type(v) is int`, and `residual_minor` satisfies it or
  is `None`. **The field list is enumerated, not swept**: a
  `dataclasses.fields` sweep asserting `type(v) is int` goes red on correct
  output, because `partial`/`show_year` are `bool` and `type(True) is int` is
  `False` (measured 2026-08-05), and `residual_minor` is legitimately `None`
  whenever `cause` is;
  (b) `grep -nE "\bDecimal\(|\bfloat\(" src/finbreak/services/month_summary.py`
  returns nothing;
  (c) **no true division and no float literal anywhere in the module** — parse it
  with `ast.parse(Path(...).read_text())` and assert `ast.walk` yields no
  `ast.Div` node **and** no `ast.Constant` whose `type(value) is float`. An AST
  walk rather than a `/` grep, because a grep fights docstrings, comments and
  path literals; `//` is `ast.FloorDiv` and is unaffected, and every division in
  this design is integer by construction (§4.2, §4.6). **The float-literal half
  is not redundant**: `abs(movement) >= baseline * 0.1` — the most natural
  non-cross-multiplied gate — contains no `ast.Div`, no `float(` and returns a
  `bool`, so it passes legs (a), (b) and the `ast.Div` half untouched. Executed
  2026-08-06: that expression yields 0 `ast.Div` nodes and one float constant,
  and `type(v) is float` does not match a `bool`.
  **Leg (c) is the catcher for the breach this invariant names**; leg (a)
  catches a float that *escapes* into a returned field; leg (b) is a cheap
  tripwire whose two blind spots (a bare `from decimal import Decimal`, a bare
  `x: Decimal` annotation) are covered by leg (a) plus the gate's `mypy` stage.
  It matches the *constructor* form deliberately: `\bDecimal\b` also matches the
  word "Decimal" in this module's own docstring, which will say why the module
  holds none.

- **INV-2** — confirmed transfers are excluded from every figure. From `M`'s
  spend, from every baseline month's spend, and from the cause candidate set.
  *Breaks when:* a transfer between two of the user's own accounts is counted as
  spending, which would make every month with a transfer look expensive.
  *Test:* a vault with one confirmed transfer pair produces the identical
  `MonthSummary` to the same vault with those two rows deleted.

- **INV-3** — a payment that recurs on the same nominal day of every month
  contributes **nothing** to `movement`. It is inside all four §4.4 windows or
  outside all four, never inside some — in the complete state because each window
  is a whole calendar month, and in the partial state because the head is capped
  below every window month's last day.
  *Breaks when:* the windows are truncated to a common day count. Then a rent
  debit on the 30th falls inside February's truncated window (the bank takes it
  on the 28th) and outside every other month's, and the strip announces a R7,000
  overspend with the landlord named as its cause — every February, on a vault
  whose behaviour never changed. §4.4 works the case.
  *Test:* **at service level** (`test_month_summary_service.py`), because the
  detector never performs the windowing — it is handed pre-summed windows, so a
  detector-level leg passes against an engine that windowed anything at all.
  Seed a vault with R250/day on days 1–20 of every month **plus** R7,000 on each
  month's last day, and assert `movement_minor == 0` for `M` = 2026-02 complete
  (`days == 28`). A common-day-count implementation returns `+700000` here.
  Second leg, same vault, `M` = 2026-03 partial at `today = 2026-03-29`: assert
  `movement_minor == 0` and `days == 27` — the head capped at `L_min − 1 = 27` by
  February, excluding the last-day debit from all four windows. Third leg,
  `M` = 2028-02 complete, asserting `days == 29`, which exercises
  `calendar.monthrange`. The fixture years are pinned because a February's length
  depends on them.

- **INV-4** — the strip is absent for every mode outside the three month modes.
  `MODE_YEAR_TO_DATE`, `MODE_SPECIFIC_YEAR` and any unrecognised token all yield
  `None` from `MonthSummaryService.summary`, which is where the allow-list lives.
  *Breaks when:* a deny-list check ("not a year mode") lets year-to-date or a
  garbage mode through, summarising a 7-month window as though it were a month.
  *Test:* `summary()` returns `None` for both year modes, for the token
  `"nonsense"`, and for `ReportPrefs(MODE_SPECIFIC_MONTH, year=None, month=None)`
  — the last because `resolve_period` would silently resolve it to previous-month
  while the selector reads "Specific month" — and non-`None` for all three month
  modes properly populated, against one seeded vault.

- **INV-5** — insufficient or absent data yields `None`, never a guess. Each of
  §4.8's five conditions independently returns `None`.
  *Breaks when:* a vault two months old produces "your usual month"; or a future
  month, or an un-imported gap month, reports that the user spent much less than
  usual.
  *Test:* one leg per §4.8 condition asserting `summarise_month(...) is None`,
  and each with the blocking condition relaxed to assert a non-`None` result — so
  no leg can pass against a detector that returns `None` unconditionally.
  **Each fixture must clear the other four conditions independently**, or it
  passes for the wrong reason. The condition-4 (`not started`) fixture is the one
  that needs building deliberately, and the constraint that matters is
  **`spend_minor > 0`** — not because condition 5 would pre-empt condition 4
  (it is *after* it in §4.8's order) but because the leg's **relaxed counterpart**
  sets `started = True` and must then return non-`None`; with `spend_minor == 0`
  it returns `None` via condition 5 and the leg asserts nothing. §4.7 leaves
  `spend_minor` computed rather than forced for a future `M` precisely so this is
  constructible — a future month can hold post-dated rows.
  `partial = False` (§4.7) is prescribed for consistency with a month that has
  not started; with `days = len(M)` it is not load-bearing here, since condition 3
  (`partial and days < _MIN_ELAPSED_DAYS`) cannot fire at 28–31 days either way.

- **INV-6** — `NORMAL` unless the movement is material. A movement clearing only
  the absolute gate yields `NORMAL`.
  *Breaks when:* the relative gate is dropped, and the strip starts announcing a
  R150 movement against a R20,000 baseline as news.
  *Test:* **three** legs — neither gate, absolute only, both — asserting
  `NORMAL, NORMAL, HIGHER`. Each fixture must clear §4.8 first, or the leg tests
  the silence ladder instead. There is deliberately **no "relative only" leg**:
  §4.5 shows that above the §4.8 floor relative-pass implies absolute-pass at
  every exponent, so that cell is empty and a fixture written for it would fail
  the relative gate too, silently duplicating the "neither" leg and passing green
  against an implementation with no relative gate at all. The floor's derivation
  is asserted directly instead, by the leg named in §11 — a comparison of the
  constants, not a fixture.

- **INV-7** — a cause is a family's **excess**, never a raw row. The candidate is
  the merchant family with the greatest `spend_in_M − baseline_mean`, and the
  gate tests that excess.
  *Breaks when:* the largest single row is nominated instead — then a recurring
  rent payment present in every baseline month is named as the cause of a
  movement it did not contribute to, and slot 3 removes it from one side of a
  comparison whose other side still contains it. §2.2 works the case.
  *Test:* **at service level**, because the detector is handed `candidate`
  already chosen — a detector-level leg cannot test "the candidate is the family
  with the greatest excess", which is the invariant's actual claim. Three legs,
  and the third is the one that catches the §4.5 regression:
  (a) the §2.2 vault — "Landlord" R7,000 in all four months, one grocer at
  R5,000 in each baseline month and R6,500 in `M` — yields `cause.merchant_key`
  = the grocer, **not** the landlord, with `excess_minor == 150000` and
  `residual_minor is None` (the residual is 0, below the slot-3 floor), so slot 3
  is omitted and slot 2 takes the `excess == movement` template. (Rent's excess
  is 0, so it is not a candidate;
  the grocer's R1,500 excess is 100% of the R1,500 movement and clears
  `0.6 × 1500 = 900` comfortably.)
  (b) a `cause is None` fixture built to fail the gate honestly: movement R1,500
  spread across three unrelated merchants at R500 excess each, so the greatest
  excess is 500 and `100 × 50000 < 60 × 150000`.
  (c) **a cause family with non-zero baseline spend** — vet R400 in every
  baseline month, R1,900 in `M`, movement R2,340 — yielding
  `cause.excess_minor == 150000`, not `190000`. This is the only fixture shape
  that fails when the baseline windows are read with `rows_in_range` (no
  `description`, so every family's baseline is 0 and `excess` collapses to gross
  spend); a suite whose cause families all have zero baseline spend stays green
  against exactly that regression.

- **INV-8** — a cause is attached only to a `HIGHER` verdict. `MonthSummary.cause`
  is `None` whenever `verdict` is `LOWER` or `NORMAL`, whatever the transaction
  set.
  *Breaks when:* a month that came in under baseline is captioned "most of it was
  one thing", which reads as an explanation and is a non sequitur.
  *Test:* a `LOWER` month containing a family whose excess exceeds
  `_CAUSE_NUM/_CAUSE_DEN` of `abs(movement)` still yields `cause is None`.

- **INV-9** — the correction template is selected by the sign of `residual`, not
  by the sign of `movement`.
  *Breaks when:* §2.1's error ships — a month still over budget after removing
  its biggest excess is described as "better than normal".
  *Test:* in minor units at exponent 2, and both fixtures must clear the
  materiality gates or they test nothing. The fixtures are `MonthSummaryInput`s,
  which carry `prior_minor`, not a `baseline_minor` — so the R10,000 baseline is
  `prior_minor = (1_000_000, 1_000_000, 1_000_000)`, which the detector averages
  to `1_000_000`. With that baseline: `spend_minor = 1_234_000` →
  `movement_minor = 234_000`, cause excess
  `190_000` → `residual_minor == 44_000` (positive → "even without it"). With
  `spend_minor = 1_146_000` → `movement_minor = 146_000`, cause excess `190_000`
  → `residual_minor == -44_000` (negative → "better than normal"). The two must
  select different templates.
  *Note the second fixture is also §4.6's `excess > movement` case* — 190,000 is
  130% of 146,000 — so it must render slot 2's "All of it and more was one thing"
  variant. `residual < 0` and `excess > movement` are the same condition, which
  is why the "Most of it" wording could not be left unconditional: it would have
  described a quantity larger than the movement it was apportioning.

- **INV-10** — the strip's spend agrees with the tile below it. For **every**
  complete `M`, and the same `account_ids` and `today`,
  `spend_minor == to_minor(ReportingService.summary(...).expenditure, exponent)`.
  The equality is unconditional in the complete state because §4.4 gives a
  complete `M` the whole calendar month — the same bounds `resolve_period` hands
  the tile.
  *Breaks when:* §4.5's independent definition of expenditure drifts from
  `summary`'s, and the sentence describes a different number than the figure
  directly beneath it — the on-screen contradiction §3 decision 4 exists to
  prevent. Also when `refresh()` computes `date.today()` twice across a midnight
  boundary (§4.9).
  *Test:* seed a vault, `M` = a complete month with three baseline months, and
  assert `summary.spend_minor == to_minor(ReportingService(vault).summary(prefs,
  account_ids, today).expenditure, exponent)` for the same `prefs`,
  `account_ids` and `today`. Add a second leg with **`M` = March and a February
  in its baselines**, carrying spend on 29–31 March. That is the shape that pins
  §4.4's complete-state half: `L_min = 28 < len(M) = 31`, so a build that still
  truncated to a common day count would report days 1–28 against a full-month
  tile and go red. **`M` = February is the one month that cannot pin it** — with
  `L_min = min(28, 30, 31, 31) = 28 = len(M)`, February's own window is the whole
  of February under either rule, and only the baselines (which this leg does not
  read) would move.
  Include one `amount_minor == 0` row, the only value the two definitions bucket
  differently. **That row documents the agreement; it cannot make the leg red** —
  §4.5 shows both definitions contribute `0` — and §11 records it as documented
  rather than covered.
  *Scope, stated so the leg is not read as covering more:* the equality is
  asserted only for a **complete** `M`. For a partial `M` the two legitimately
  differ — `resolve_period` gives the tile the full month bounds while §4.4 stops
  the strip at `head`. §6.7 records it.

- **INV-11** — the summary is scoped to the same accounts as the tiles. The strip
  and `ReportingService.summary` receive the identical `account_ids`.
  *Breaks when:* selecting one account leaves a whole-vault sentence above
  single-account tiles.
  *Test:* with two accounts, `spend_minor` for a single-account selection equals
  that account's expenditure alone and differs from the "All accounts" value.
  This asserts *scoping*, not numeric equality with the tile — INV-10 owns that,
  for a complete `M`.

- **INV-12** — the service emits no user-facing string. `MonthSummary` carries an
  enum, integers and booleans; the only prose is `MonthCause.name`, **derived
  from** the user's own transaction text by `merchant_name` and carried at full
  length (the 40-character truncation is the strip's, §4.6).
  *Breaks when:* a sentence is assembled in the service, where `tr()` is
  unavailable, silently making the feature untranslatable.
  *Test:* three legs, and **the grep is the weakest of them** — the named breach
  is a sentence assembled *without* `tr()`, which no search for `tr(` can see.
  (a) **the structural leg, and the catcher**: for a returned `MonthSummary`, the
  only `str`-typed values are `month`, matching `^\d{4}-\d{2}$`, and
  `cause.name` when `cause` is not `None`. A sentence then has no field to travel
  in, whether or not it was translated.
  (b) `grep -nE "(^|[^A-Za-z0-9])_?tr\(|QCoreApplication" src/finbreak/services/month_summary.py`
  returns nothing. **Executed 2026-08-06** against a scratch module: it matches
  `tr("…")`, `_tr("…")` and `self._tr("…")`, and does not match `str(`, `attr(`
  or `mystr(`. The optional `_` matters because §8 alternative 1 names a `_tr`
  seam as the *precedented* design (`pdf_export.py`) — so it is the likeliest
  breach, and `\btr\(` misses it (`_` is a word character, so there is no
  boundary before the `t`).
  (c) the strip renders a full three-sentence summary from a hand-constructed
  `MonthSummary` with no service involved.

- **INV-13** — a mid-render lock leaves no stale sentence and adds no failure
  mode. `MonthSummaryService.summary` lets `VaultLockedError` propagate rather
  than catching it, and `HomeView.refresh()` **clears the strip as its first
  statement** (§4.9), so no path through it can leave one standing.
  *Breaks when:* (i) the service catches `VaultLockedError` itself and returns a
  partial summary computed from rows it did manage to read — a sentence about a
  fraction of the month, presented as the month; or (ii) the strip is hidden only
  in the two guarded slots, so the six unguarded call sites keep it asserting
  "September cost you R2,340 more than your usual month" while the selector now
  reads October. A stale *figure* in a tile is ambiguous; a stale *sentence*
  naming a month is a positive false claim, which §1 property 3 exists to
  prevent.
  *Test:* three legs. (a) a stand-in that raises `VaultLockedError` **only on the
  month-summary read** — not on the first vault call — so `refresh()` actually
  reaches it; `transaction_count()` runs before the service read, so a stand-in
  raising on any read makes the leg pass against an implementation that never
  calls the service at all. (b) after that raise the strip is hidden, asserted on
  **both** a guarded slot (`_on_period_changed`, which must also return cleanly)
  and an **unguarded** one (`set_amount_prefs`, `home.py:374`, which propagates)
  — the unguarded leg is what fails against a fix that only touched the two
  `except` blocks. **Each leg must first drive a successful `refresh()` and
  assert the strip is showing a sentence**, then swap in the raising stand-in: a
  fresh `HomeView` has the strip hidden already, so without that precondition the
  assertion passes against exactly the implementation it exists to fail.
  (b′) a **third** lock site, added 2026-08-06: `_on_period_changed`'s
  `set_report_prefs` **write**, which precedes `refresh()` and so is the one path
  `refresh()`'s own clear cannot cover (§4.9). Driven with an `AuthService` proxy
  that raises only on the write; the slot must return cleanly with the strip
  hidden.
  (c) `MonthSummaryService.summary` propagates `VaultLockedError` rather
  than returning a partial `MonthSummary`, asserted directly on the service.

- **INV-14** — every reachable combination has a template, across **all three
  slots**, and no rendered amount carries a sign. Slot 1 is exhaustive over
  `MonthVerdict × {partial, complete}` (6), slot 2 over
  `{excess < movement, excess == movement, excess > movement} × {partial,
  complete}` (6), slot 3 over `{residual < 0, residual > 0} × {partial,
  complete}` (4), plus the two `{month}` forms — **18 template strings**.
  *Breaks when:* an implementer writes three templates and interpolates "so far"
  ad hoc, so a mid-month cause or correction sentence is unqualified past tense
  about a month that is a third over — the mitigation §6.2 explicitly relies on;
  or the signed `movement_minor` / `residual_minor` reach `_format_amount`
  unmodified, rendering "cost you -R500 less than your usual month".
  *Test:* two legs.
  (a) for each of the 18, assert the rendered label **contains that template's
  expected substring** — not merely that the 18 labels are pairwise distinct.
  §4.6 joins the slots into **one** `QLabel`, so a pairwise-distinctness
  assertion reads only the whole block, and an implementation that prefixes the
  joined block with a single `"So far, "` still produces 18 distinct labels while
  leaving slots 2 and 3 in unqualified past tense — precisely this invariant's
  *Breaks when*. The 18 are a **union of three per-slot sets plus the month
  forms, not a product**: slot 2's and slot 3's conditions are the same quantity
  (`residual = movement − excess`), so a product sweep over independent axes would
  construct `excess == movement` together with `residual < 0`, which is
  unreachable, and go red against a correct build. Each slot's templates are
  rendered from hand-constructed values chosen for that slot: for slot 2's `==`
  cell pin `residual_minor is None`, so slot 3 is absent by construction (§4.6).
  (b) **no rendered amount carries a sign**, asserted positively rather than by
  character search: for a slot rendering value `v`, build
  `expected = _format_amount(to_display_decimal(abs(v), exponent), symbol)` and
  assert the slot contains `expected` and contains neither `f"-{expected}"` nor
  `f"({expected})"`. A search for "`-` or `(` before a digit" **cannot fire** —
  `_format_amount` composes `body = f"{sym} {magnitude}"` and returns
  `f"-{body}"` or `f"({body})"`, so a signed amount reads `-R 500,00`, whose
  character after the sign is the currency symbol (verified against
  `ui/_amount.py`). Nor is the leg run "under both `NegativeStyle` settings":
  `set_summary` takes no style parameter (§4.7), so there is nothing to vary —
  the positive assertion covers both notations at once, since neither wrapper
  form may appear.

## 6. Failure modes

Stated, not hidden. Each is a consequence the design accepts.

1. **A complete February reads low for a household that spends daily.** §4.4
   compares whole calendar months, so a month shorter than its baselines carries
   fewer days of flow spend. The worst case in the calendar is February against a
   Nov/Dec/Jan baseline, at **8.70%** for perfectly uniform daily spend — under
   the 10% relative gate, so it never renders a verdict on its own, but it can
   tip a genuine −1.5% month to `LOWER`. It is a **standing bias, not an invented
   narrative**: February really did cost less. Accepted as the far smaller of the
   two errors available (§4.4 works the alternative). What is *not* handled at
   all is a bank moving a debit off a weekend by a day or two — that shifts a
   fixed payment between windows for reasons no window rule can see, and it can
   move a payment in or out of a partial month's head.
2. **A partial month's verdict can flip day to day, and jumps at month end.** In
   a small early window a single grocery run swings the ratio past the relative
   gate, and the §4.8 floor can flip the strip from silent to speaking as the
   truncated baseline crosses `minor(_MIN_MONTH_BASELINE_MAJOR)`. Separately,
   §4.4 freezes the partial head at `L_min − 1`, so a month's final days are
   invisible until `M` turns complete — at which point the window jumps from
   ~27 days to the whole month and the month-end debits land at once, which can
   change the verdict overnight. Accepted rather than pro-rated: the constants
   are full-month figures applied unscaled, and the "so far" phrasing is what
   tells the reader the figure is provisional.
3. **A month whose spending moved for a good reason still reads as a warning.**
   Moving house, a deliberate annual insurance payment, a planned holiday. The
   strip has no notion of intent; the cause clause is the mitigation, since
   naming the family lets the reader dismiss it instantly.
4. **`MonthCause.name` is derived from raw bank text.** It may be cryptic
   ("POS 4455 \*\*\*\*1234"). `merchant_name` cleans it, but cleaning is
   best-effort. An ugly true description beats a tidy wrong one. §4.6 pins
   `PlainText` and 40-character truncation so it cannot inject markup or break
   the layout.
5. **Three baseline months is a short memory.** A user with genuinely seasonal
   spending will see December called expensive every year. Accepted: a 12-month
   baseline needs a year of history before the feature works at all.
6. **The merchant grouper is fuzzy, and here it is arithmetic-bearing.**
   `text.py::merchant_name` documents itself as "fuzzy by design and refined per
   release", and distinguishes its two existing consumers: a mis-grouping is
   "cosmetic **in the drill-down**" but "*not* cosmetic in `services.recurring`,
   where the same key is a **filter**". **This feature is the second filter
   case**, and the document that says so does not yet know it (§12 records the
   new consumer). Both directions bite: a merchant split across two keys halves
   its excess and can drop it under the 60% gate, and two shops folding to one
   key manufacture an excess and can name the wrong payee. It also means the same
   vault can gain, lose or change its cause sentence after an upgrade with no
   data change. A split payment across *different* merchants still defeats the
   clause entirely — that one degrades to the verdict alone, which is the correct
   direction.
7. **The strip's window and the Net tile's differ for a partial month.**
   `resolve_period` gives the tile the full month bounds
   (`_month_bounds(today.year, today.month)` for `MODE_CURRENT_MONTH`); §4.4
   stops the strip at `head`, which is capped below `today.day` near month end.
   The `partial` flag drives the "so far" phrasing, and INV-10 is scoped to the
   complete state, where the two now agree exactly.
8. **The thresholds go soft for exponent-0 currencies.** `minor(1000)` is 1000
   for JPY or KRW — about US$6.50 a month for ¥1,000, and about US$0.70 for
   ₩1,000 — so the §4.8 floor admits vaults the
   strip should stay silent on, and the relative gate then characterises a
   month's worth of trivial movement. (The failure is the *floor* scaling, not
   the absolute gate going soft: §4.5 shows the relative gate binds at every
   exponent.) The thresholds are tuned for exponent-2 currencies;
   `base_currency()` is user-settable, so this is reachable rather than
   hypothetical. Accepted for v1 and recorded rather than silently carried.
9. **A partly imported month renders a confident, false verdict.** §4.8's
   condition 5 catches only a month with *no spend rows at all*. A month where one of two
   accounts was imported, or the first ten days of a statement period, has rows
   and low spend and renders "October cost you R8,000 less than your usual
   month" out of absent data. Partial import is the normal state of a vault
   between statement downloads, so this is **more reachable than either case
   condition 5 covers**, and the mirror case — a baseline month with one imported
   row — drags the baseline down and inflates `HIGHER`. Accepted for v1 and
   stated rather than left implied-covered; the honest gate needs a month's
   expected coverage, which is FIBR-0038's subject (§9).
10. **A fully reversed purchase can still be named as a cause.** §4.5 does not
   net positive rows against a family's spend, so a R2,000 charge refunded in the
   same window contributes R2,000 of excess. Not netting is deliberate — it is
   what keeps INV-10's agreement with the Net tile — but it means the sentence
   can name a merchant whose net contribution to the month was nil.

## 7. Tests

New feature directory `tests/features/month_summary/` (`spec.md` + tests), per
`docs/standards/testing.md`. No such directory exists today (`ls tests/features/`).

Four files. **The split is by capability, and which invariant goes where is a
contract, not a preference** — an earlier draft filed vault-dependent and
Qt-dependent invariants in the hermetic detector file, where the legs are either
unwritable or vacuous. Two rules decide it: an invariant about *window
construction* or *candidate selection* is a service test, because the detector is
handed both already computed; an invariant about *period modes* or *slot
rendering* is a UI test.

- **`test_month_summary.py`** — the detector, hermetic, no vault and no Qt.
  INV-1 (**all three legs**, including (c)'s `ast.Div` walk — the only one that
  catches the invariant's own *Breaks when*), INV-5, INV-6, INV-8, INV-9, the
  §4.5 `_MIN_MONTH_BASELINE_MAJOR` derivation leg, and the §4.6 slot-3 floor leg.
- **`test_month_summary_service.py`** — the service against a real vault fixture.
  INV-2, INV-3 (all three legs), INV-4, INV-7 (all three legs), INV-10, INV-11,
  INV-12's grep leg, INV-13 leg (c), and the §4.6 **tie-break** leg. The tie-break
  belongs here for the same reason INV-7 does: `MonthSummaryInput.candidate` is a
  *single, already-chosen* `MonthCause`, so a two-equal-families fixture cannot be
  expressed at the detector boundary at all.
  **Plus the three fields the service derives from the clock** — `month`,
  `show_year` and `started` — which the detector and the strip are both *handed*,
  so a leg in either of those files asserts only that a hand-supplied value
  travelled. Added 2026-08-06: a mutation emitting the wrong `month` passed the
  whole suite. `MonthCause.name`'s earliest-row rule belongs here too, and needs
  a Unicode-decomposed/precomposed pair — within a family two rows otherwise
  yield the *same* `merchant_name`, so which one supplies the label is
  unobservable.
- **`test_month_summary_strip.py`** — the strip under `qtbot`, fed
  hand-constructed `MonthSummary` values. INV-12's render leg, INV-14's 18
  templates and its no-signed-amount leg, **INV-9's template-selection leg** (the
  two hand-constructed residual values INV-9 specifies, asserting the two select
  *different* slot-3 templates — the detector cannot select a template, so a
  detector-only INV-9 would assert nothing but the sign of `residual_minor` and
  a strip keying slot 3 off `movement` would pass it), a leg feeding `residual_minor = None` asserting no third sentence renders,
  `isHidden()` after `clear()` and on `None`, a leg feeding a `name` containing `<b>markup</b>`
  asserting the literal text survives, and a leg feeding a 60-character `name`
  asserting it renders as 39 characters plus `…`.
- **`test_month_summary_home.py`** — `HomeView`-level, seeded vault. The strip
  appears and hides as the period selector moves across all five modes, and
  INV-13 legs (a), (b) and (b′) — which drive `_on_period_changed` (guarded),
  `set_amount_prefs` (`home.py:374`, unguarded) and the `set_report_prefs`
  **write** that precedes `refresh()`; all three are `HomeView` slots needing
  `qtbot`, so none can live in the service or strip file. Every site is
  `HomeView`'s own, so this file needs no `MainWindow`.
  **It also owns the `HomeView` halves of INV-10 and INV-11**, added 2026-08-06:
  the service suite proves the *service* reads one clock and scopes to the
  accounts it is given, and can say nothing about whether the view hands it the
  right arguments. Both legs use recording proxies over `MonthSummaryService`
  and `ReportingService` and assert the two received the identical `today` and
  the identical `account_ids`. The clock leg additionally needs a **ticking**
  `date` stand-in whose `today()` advances per call: two real reads on the same
  day are equal, so an equality assertion over them is vacuous.

Ripple into existing suites: every file constructing `HomeView` gains the sixth
service argument. The set is whatever `grep -rln "HomeView(" tests/` returns at
implementation time — six files across five directories as of 2026-08-05
(`spending_alerts/`, `table_state/`, `dashboard/` ×2, `dashboard_drilldown/`,
`dashboard_focus/`). `tests/features/app_shell/` is **not** among them; its own
comment records that the Home page assertions moved to `tests/features/dashboard/`.

## 8. Alternatives considered (and rejected)

1. **Generate the sentence in the service via a `_tr` seam** (the
   `pdf_export.py` precedent). Rejected: it puts grammar in a layer that cannot
   see the user's locale conventions and makes every template untestable without
   a translation context. §4.7.
2. **Nominate the largest single transaction as the cause.** Rejected on
   evidence — §2.2 works the counterexample. It is the design an earlier draft
   carried, and it produced a false and reassuring sentence on an ordinary vault.
3. **Reuse `AlertService`'s category spikes as the cause.** Rejected: a spike
   names a *category* over a 3-month window with its own thresholds; the cause
   clause needs the merchant family inside this month. Bending the alert detector
   to serve both would couple two thresholds that must move independently.
4. **A 12-month baseline, seasonally aware.** Rejected for now — see §6.5. It is
   the natural v2 once vaults have the history, and it changes only
   `_BASELINE_MONTHS` plus the §4.8 gate.
5. **Project the current month to a full-month estimate.** Rejected: it is the
   invention property 1 forbids. A common head window (§4.4) answers the same
   question without asserting anything about days that have not happened.
6. **Truncate every window — complete months included — to a common day count.**
   Rejected on evidence: it is the design an earlier draft carried, and it
   manufactures a false verdict *and* a false named cause every February for any
   user with a month-end debit order. §4.4 works the counterexample and states
   what it was bought with (a sub-threshold February bias, §6.1).
7. **Rescale each baseline month's spend to `M`'s length.** Rejected: it removes
   the §6.1 bias for flow spend but silently rescales fixed monthly payments too
   — a R7,000 rent in a 31-day baseline month becomes R6,322 against a February —
   so it trades a true bias for a small invented one, and it cannot help the
   partial state at all, where a full baseline month pro-rated against a
   part-elapsed `M` reads the month-end debits as already spent.
8. **Align every window to both month start *and* month end** — a head of `h`
   days from day 1 plus a tail of `t` days ending on the last day, with
   `h + t = L_min`. Rejected, and it is the **near miss worth recording**,
   because it looks strictly better than either rule §4.4 chose between: it is
   exact for uniform daily flow *and* exact for a last-day debit, since a
   month-end payment falls in every window's tail whatever the month's length.
   What kills it is the **hole between the two bands**. For a 31-day month
   against a February baseline `L_min = 28`, so days `(29 − t) … (31 − t)` fall
   in neither band — with `t = 4`, days 25–27. A debit order on the 26th is then
   inside February's tail (days 25–28) and inside no 30/31-day month's window at
   all, which reproduces the fabricated-verdict-with-a-named-payee failure §4.4
   exists to remove, three days earlier in the month. Changing `t` only *moves*
   the hole: its width is `len(M) − L_min` and no choice of `t` closes it.
   Whole calendar months have no hole, which is why they win despite §6.1.

9. **Put the strip in a dialog, or on its own tab.** Rejected: a feature whose
   entire purpose is to save the reader effort cannot be behind a click.
10. **Let the strip speak for year modes with year-over-year phrasing.** Rejected
   by the user (§3 decision 1); it is FIBR-0175's shape, not this one's.

## 9. Out of scope

- **Comparing two arbitrary periods side by side** — FIBR-0175.
- **"Safe to spend"** — FIBR-0232, which is forward-looking where this is
  backward-looking.
- **Including the summary in the PDF export** (FIBR-0013). The export's section
  set is fixed and adding to it is its own contract change.
- **A settings surface for the thresholds.** They are module constants with a
  documented home, matching `alerts.py`'s D10 position.
- **Income narration.** The strip characterises spending only. "You earned more
  than usual" needs a different materiality rule (a salary is near-constant, so
  any movement is either noise or a life event) and would double §4.6.
- **Currency-aware threshold derivation** (§6.8). The exponent-0 degradation is
  recorded, not fixed.
- **Gating on statement coverage** (§6.9). Silencing the strip when `M` is only
  partly imported needs a notion of a month's *expected* coverage, which is
  **FIBR-0038**'s subject (statement coverage tracking + gap detection). This
  spec records the dependency rather than inventing a coverage heuristic in
  passing; when FIBR-0038 lands, the natural §4.8 condition is "`M`'s window is
  not fully covered by an imported statement for every selected account".

## 10. Resource cost

**Six vault reads** are added per `HomeView.refresh()`:

- **four `drill_rows_in_range`** — `M`'s window and each of the three baseline
  windows. All four carry `description`, because §4.6's `excess` needs per-family
  sums on both sides of the subtraction (§4.5).
- **one** `TransferDetectionService.confirmed_transfer_txn_ids()` for the INV-2
  exclusion set, the same read every sibling service issues.
- **one** `read_minor_unit_exponent`.

The range scans are indexed on `occurred_on`, the same shape `summary`,
`monthly_trend` and `drill_down` already issue — five existing call sites in
`services/`, four `rows_in_range` and one `drill_rows_in_range`.

The merchant grouping runs `normalise_text(merchant_name(...))` over the rows of
**all four** windows. That is the cost §2.2's fix adds over the per-row design:
descriptions and grouping for four windows rather than one.

No timing figure is stated here, because none has been measured — per the
authoring rule that a number arrives with the command that produced it. If the
added reads prove material, the three baseline months are exactly the months
`monthly_trend` already fetches and the two could share one query. That is
deliberately **not** done in v1 for two reasons, either sufficient: the trend
chart reads `rows_in_range`, which carries no `description`, so it cannot feed
§4.6's per-family sums; and §4.4's partial-state head makes the two sets of
windows differ whenever `M` is partial.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_month_summary.py` — leg (c), the `ast.Div` walk, is the catcher for the named breach; leg (a) catches a leaked float, leg (b) is the grep tripwire |
| INV-2 | `test_month_summary_service.py` |
| INV-3 | `test_month_summary_service.py` — three legs: a last-day debit against a complete February, the same against a partial March at the capped head, and the leap-year `days` |
| INV-4 | `test_month_summary_service.py` |
| INV-5 | `test_month_summary.py` (five conditions × relaxed counterpart) |
| INV-6 | `test_month_summary.py` (three-leg gate matrix: neither / absolute-only / both) |
| INV-7 | `test_month_summary_service.py` — three legs, incl. (c) the non-zero-baseline cause family |
| INV-8 | `test_month_summary.py` |
| INV-9 | `test_month_summary.py` (the residual sign) + `test_month_summary_strip.py`'s template-selection leg (§7) — the detector cannot select a template, so the strip leg is what catches a slot 3 keyed off `movement` |
| INV-10 | `test_month_summary_service.py` — two legs, the second with `M` = February — **plus** `test_month_summary_home.py`'s ticking-clock leg, which is the only thing covering the invariant's *second* `Breaks when` (a `date.today()` read twice inside `refresh()`). The service legs cannot see the view's clock discipline; added 2026-08-06 |
| INV-11 | `test_month_summary_service.py` for the service's scoping, **plus** `test_month_summary_home.py`'s recording-proxy leg for the wiring — the named breach ("selecting one account leaves a whole-vault sentence above single-account tiles") is a `HomeView` failure and the service leg is blind to it. Added 2026-08-06 |
| INV-12 | grep leg (service file) + the strip test's hand-constructed `MonthSummary` |
| INV-13 | `test_month_summary_home.py` legs (a)(b)(b′) — a guarded call site, an unguarded one, **and** the `set_report_prefs` write that precedes `refresh()` — + `test_month_summary_service.py` leg (c) |
| The three fields the service derives from the clock — `month`, `show_year`, `started` | `test_month_summary_service.py`. Nothing covered these until 2026-08-06: the detector and the strip are both *handed* them, so their legs assert only that a hand-supplied value travelled. A mutation emitting the wrong `month` — the field every sentence names — passed all 81 tests. The `started` leg reads from the **15th**, not the 5th: forcing `started` true also makes the month partial, and from the 5th condition 3 would silence it and the leg would pass against its own mutation |
| §4.6's `MonthCause.name` = the family's **earliest** row in `M` | `test_month_summary_service.py`, via a Unicode-decomposed/precomposed pair. This is the only fixture shape that can see it: within one family two rows normally yield the *same* `merchant_name`, so the earliest-row rule is unobservable — `merchant_name` preserves the composition form while `normalise_text`'s NFC fold collapses both to one key. Added 2026-08-06 |
| §4.9's clear **before** the prefs write (the path `refresh()`'s own clear cannot reach) | INV-13 leg (b′) |
| INV-14 | `test_month_summary_strip.py` (18 distinct templates + the positive no-signed-amount leg) |
| §4.4's whole-month rule for a complete `M` | INV-3 leg 1 (a common-day-count implementation returns `+700000` there) + INV-10's February leg |
| §4.4's partial head cap at `L_min − 1` | INV-3 leg 2 — `days == 27` for a partial March with February in its baseline |
| §4.5's "all four windows use `drill_rows_in_range`" | INV-7 leg (c) — the **only** fixture shape that goes red when a baseline window is read without `description`; every zero-baseline cause fixture stays green against that regression |
| §4.5's derived `_MIN_MONTH_BASELINE_MAJOR` | `test_month_summary.py` — a leg asserting `_MIN_MONTH_BASELINE_MAJOR == _MIN_MOVE_MAJOR * _MATERIAL_DEN // _MATERIAL_NUM`, computed from the constants. It is asserted directly because the behavioural leg that would have covered it does not exist: above the floor relative-pass implies absolute-pass, so there is no "relative only" fixture (§4.5, INV-6) |
| §4.6's slot-3 materiality floor (the detector nulls `residual_minor` below it) | `test_month_summary.py` — two legs at `abs(residual)` one minor unit under and one over `minor(_MIN_MOVE_MAJOR)`, asserting `residual_minor is None` then not-`None`; plus `test_month_summary_strip.py` asserting a `None` `residual_minor` renders no third sentence |
| §4.6's tie-break (equal excesses resolve to the smaller `merchant_key`) | `test_month_summary_service.py` — asserted on `cause.merchant_key`. **The fixture needs a third, *falling* family or the tie is unreachable**: two new families at excess `E` and nothing else changing make `movement = 2E`, and `100·E ≥ 60·2E` is false, so `cause is None`. Worked — baselines Grocer R5,000 + Fuel R3,000; `M` has Grocer R4,000, Fuel R3,000, AAA R1,000, ZZZ R1,000 → movement R1,000, AAA and ZZZ tie at excess R1,000, the gate clears (`100 000 ≥ 60 000`) and the smaller key wins. It cannot live in the detector file: `MonthSummaryInput.candidate` is a single already-chosen `MonthCause` |
| §4.6's `PlainText` and 40-character truncation | `test_month_summary_strip.py` — the `<b>markup</b>` leg covers `PlainText`, the 60-character-name leg covers the truncation. Truncation is assertable **because** §4.6 specifies characters rather than `QFontMetrics.elidedText`, which would have made it a pixel property no assertion here could read |
| §4.9's clear-at-the-top of `refresh()` | INV-13 leg (b)'s unguarded call site — a fix confined to the two `except VaultLockedError` blocks fails it |
| §4.6's family-mean divisor (`_BASELINE_MONTHS`, absent months counting 0) | INV-7 leg (c) — a family present in all three baseline windows; **nothing** covers a family present in only *some*, which is where the two candidate divisors diverge most |
| §4.5/§4.6's specific threshold *values* (10%, 100, 60%, 7 days) | **nothing** — the tests assert behaviour either side of each constant by reading it, so changing a constant moves the test with it. Deliberate: these are tuning values, not contract. What is pinned is that the relative gate exists (INV-6), that the cause gate tests an excess (INV-7), and that each silence condition fires (INV-5). The baseline floor is exempt: it is derived, and the row above covers it |
| §4.5's zero-amount-row agreement with `ReportingService.summary` | **nothing** — INV-10's fixture carries such a row so the agreement is documented where it matters, but both definitions contribute `0`, so no assertion over it can go red. Recorded rather than claimed as coverage |
| §6.1's February bias staying under the relative gate | **nothing** — no leg asserts the 8.70% bound. §4.4 derives it for uniform spend; a real vault's mixture is not bounded by that derivation |
| §6.2's day-to-day verdict instability, and the month-end jump | **nothing** — no leg drives the same vault across successive `today` values |
| §6.6's fuzzy-grouper risk (a merchant split across two keys, or two shops folded into one) | **nothing** — and it is not closable by this suite: `merchant_name` is documented as refined per release, so the failure is a future upstream change, not a defect in this code |
| §6.9's partly-imported month | **nothing** — accepted for v1; the honest gate needs FIBR-0038 (§9) |
| §6.10's un-netted refund | **nothing** — no leg builds a charge-and-refund family |
| Whether the sentence is *useful* — that a real user reads it and understands their month | **nothing**, and nothing can. This is the honest limit of the feature: the tests pin that the arithmetic is right and the phrasing is selected correctly, not that the result communicates |
| §4.2's decision to keep `_BASELINE_MONTHS` and `_MIN_MONTH_BASELINE_MAJOR` separate from `alerts.py`'s | **nothing** — a future edit could import either and every test would stay green. The distinct *name* of the floor is the only mechanical defence; the rationale is recorded in §4.2 and the constants' own comments |
| §6.8's exponent-0 degradation | **nothing** — no leg runs a zero-exponent vault |

The tally is emitted, never counted by hand:

```
awk '/^## 11\./,/^## 12\./' docs/specs/FIBR-0231-plain-english-month-summary.md \
  | awk '/^\| /{n++; if ($0 ~ /\*\*nothing\*\*/) k++} END{print n-1, k}'
```

→ **`36 11`**: thirty-six rows, eleven with a bolded `nothing`. (Was `33 11`.
The implementation review of 2026-08-06 added **three** rows — the three
clock-derived fields, the earliest-row name rule, and the pre-write clear — and
*amended* two more in place, INV-10's and INV-11's, each of which gained a
`HomeView` half. None of the three is a `nothing`, so the uncovered count is
unchanged.) The eleven are the family-mean
divisor's partial-presence case, the threshold values, the zero-row agreement,
the February bias, the verdict instability, the fuzzy grouper, the
partly-imported month, the un-netted refund, whether the sentence communicates,
the constant-independence decision, and the exponent-0 degradation. Of the
eleven:

- **Two are closable and deliberately not closed in v1** — a zero-exponent-vault
  leg and a partial-presence family-mean leg are both writable.
- **Five are design limits this spec states rather than tests it declined to
  write**: the February bias, the accepted verdict instability, the
  partly-imported month (which needs FIBR-0038), the un-netted refund, and the
  zero-row agreement that no implementation change can move.
- **One is not closable here at all** — the fuzzy grouper's risk is a future
  upstream change to `merchant_name`, not a property of this code.
- **Three are the honest floor**: tuning values that are deliberately not
  contract, a design decision no test can defend, and the fact that no automated
  check can tell whether prose helps a human.

## 12. Cross-doc impact

Every bullet is a **state claim** about the tree, not an instruction, and carries
its status.

- `ROADMAP.md` — **pending.** FIBR-0231 flips 📋 → 🚧 when implementation starts
  and → ✅ on close.
- `CHANGELOG.md` — **pending.** One `### Added` entry; this is user-facing.
- `CLAUDE.md` module map — **pending.** The `src/finbreak/` bullet lists the
  package's shape; two new modules land under it.
- `docs/design.md` — **pending.** The layered-architecture section lists the
  services; `month_summary` joins them. No layering change: it is a read-only
  vault-scoped service exactly like `ReportingService`.
- `src/finbreak/models.py` — **pending.** Gains `MonthVerdict`, `MonthCause` and
  `MonthSummary` (§4.1).
- `docs/specs/FIBR-0012.md` — **no change needed.** The dashboard spec's INV-7
  (getting-started iff zero transactions) governs the strip too and is cited
  rather than amended (§4.8).
- `docs/specs/FIBR-0142.md` — **no change needed.** §4.6 reuses
  `merchant_name`/`normalise_text` as a grouping key without altering
  `RecurringService`.
- `src/finbreak/text.py` docstring — **pending, and it is a contract change, not
  a comment tidy.** `merchant_name`'s docstring names its two consumers and
  draws the line that matters: a mis-grouping is "cosmetic **in the
  drill-down**" but "*not* cosmetic in `services.recurring`, where the same key
  is a **filter**". This feature is the **third** consumer and the **second**
  filter case — the cause gate's arithmetic depends on the grouping — so the
  docstring must name it. Without that line, a future session tuning
  `merchant_name` sees two consumers where there are three, and the one it
  cannot see is the one that turns a mis-group into a false sentence.
- `docs/specs/FIBR-0038.md` — **no change needed, dependency recorded one-way.**
  §9 names it as the item that would let §4.8 gate on statement coverage; this
  spec ships without it and FIBR-0038 is not blocked by anything here.
- `docs/specs/FIBR-0172.md` — **no change needed.** §4.2 deliberately does not
  import its constants, so its D10 "one home" position is untouched.
- `docs/specs/FIBR-0138.md` — **no change needed.** §4.7 extends its
  translation-seam pattern without altering `DrillLabels`.
- `docs/audit-allowlist.md` — **no change expected.** The design introduces no
  known false-positive class; revisit if `/audit` flags the grep-based invariant
  legs.
- `docs/standards/coding.md` — **deviation, stated not taken silently.** The
  standard requires widgets to re-translate on `QEvent.LanguageChange` via a
  `retranslateUi()`. No such handling exists anywhere in `src/finbreak` today
  (`grep -rn "retranslateUi\|LanguageChange" src/` returns nothing), so this
  widget follows the project's actual practice rather than introducing the
  project's only conforming widget. Surfaced to the user; if the answer is that
  the gap should be closed, it is its own item across every widget, not this one.
- `docs/standards/naming.md` spec-doc row — **stale, amendment pending under
  FIBR-0196.** Line 85 still mandates `<ID>.md` and line 207 rejects variants,
  but the user decided 2026-08-05 in favour of `<ID>-<topic>.md`. This spec is
  the first file written under the new rule. FIBR-0196 carries the amendment and
  the 54-file back-migration.

## 13. Cold-eyes loop log

Fresh log — this document has not been reviewed under any other id.

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-08-05 | 3, strong, cold, shared byte-identical packet (dims: 5×9, 15×6, 6×6, 4×5, 13×4, 2×4, 10×4, 1×3, 7×2, 12×1) | 3 | 6 | 12 | 8 | 29 verified, 1 unverified. All fixed. **The CRITICAL rewrote the design's core rule, and it was the same defect §2.1 was written to prevent, one layer deeper.** All three lanes independently constructed the case: the cause clause selected *the largest single expenditure row* in the month and gated it only from below (≥60% of the movement), so on an ordinary vault the largest row is rent — present identically in every baseline month, explaining nothing. Executed against this spec's own constants: baseline R12,000, spend R13,500, movement +R1,500 → HIGHER; rent R7,000 clears the gate by **7.8×**; residual −R5,500 selects the *reassuring* template. Emitted: "Most of it was one thing — a R7,000 rent payment. Take that out and you were R5,500 better than normal", on a month that was R1,500 over. INV-8 (now INV-9) stayed green throughout, because it pins the sentence's *grammar* and the evidence was never required to be evidence. Fixing the gate alone was insufficient — in that vault the vet bill of §2.1 would not even be *selected*, rent being larger — so the unit changed from a row to a **merchant family** and the quantity from magnitude to **excess over that family's own baseline**, reusing `RecurringService`'s `merchant_key`. New §2.2 works the case; INV-7 pins both vaults. Second CRITICAL, all three lanes: **the feature's actual deliverable was absent** — only slot 3's two templates were specified, so the verdict (×3 verdicts ×2 states) and cause strings, and the "so far" phrasing §6 relied on as its whole mitigation, existed nowhere; §7 asked for tests against them. A nine-row template table now lives in §4.6 and INV-14 pins exhaustiveness. Third, lanes B and C: **`M` itself was never guarded** — only the baseline was. `home.py:255` is `setRange(1970, 9999)`, so a future month is two clicks away, and with three months of prior data `movement = −baseline` clears both gates by construction, announcing that a month which has not happened was much cheaper than usual; an un-imported gap month does the same. §4.8 gained conditions 4 and 5. HIGHs: §4.9 claimed "both slots that reach `refresh()`" and carried a **verified** stamp — measured, there are **8** call sites and **6** are unguarded (`home.py:117,352`, `main_window.py:797,828,1497,1506`), so the sentence is replaced by the inventory and the claim narrowed to the true, weaker one (the exposure is pre-existing; the read adds no new type); the complete-month branch was **not** truncated, leaving a uniform-spend February at **−8.70%** against a 10% gate on the *default* period mode, three times the partial bias the doc did record — the two branches collapse into one common-day-count rule (INV-3); §4.8 condition 1 was **inexpressible** through `MonthSummaryInput`, a tuple of totals being unable to distinguish "no rows" from "rows summing to zero", now `prior_months_with_data` with the income-only case ruled on explicitly; INV-9's worked values were **major units in `_minor` fields** — `movement=2340` at exponent 2 is R23.40, below `minor(100)`, so the verdict is NORMAL, cause None, and the leg asserts `440` against `None` — restated with a baseline so both fixtures clear the gates; INV-1's grep could not see its own stated breach (`movement / baseline` contains neither token), now a `type(v) is int` assertion with the grep demoted to leg (b); §7 assigned vault- and Qt-dependent invariants to a hermetic detector file, and INV-4 to a strip file with no `HomeView` — four files now, split by capability. MEDIUMs fixed: `_MIN_BASELINE_MAJOR` collided with `alerts.py` on **name and value** while §4.2 argued only against the *other* import — renamed `_MIN_MONTH_BASELINE_MAJOR` and the rationale extended to both; the strip could not format anything, `read_minor_unit_exponent` not being imported in `home.py`, so `exponent` moved onto `MonthSummary`; `MonthSummaryService`'s signature was never given and the mode gate had no stated home — both now in §4.7, the allow-list inside `summary()` so INV-4 is testable without Qt; the output dataclasses moved to `models.py`, where all 30+ cross-layer shapes and every `StrEnum` already live; `QLabel`'s default `AutoText` would render `<b>`/`<img>` in raw bank text — `PlainText` + elision pinned; §4.5's "6 call sites" counted a `def` and a docstring (4 real); §7's ripple list was 2-of-5 with a false `app_shell/` entry; the partial-month verdict instability, the tile/strip window divergence, and the zero-amount-row bucketing became §6 entries and INV-10. LOWs: §1 property 1 contradicted slot 1 always rendering; `floor()` renamed `minor()`; `elapsed_days` undefined when complete (now `days`, defined in both states); the allow-list-vs-deny-list ambiguity for an unrecognised mode; 60% cannot be called "almost all" (template says "most of it"); exponent-0 currencies; the `today.day` off-by-one and its comment. **One finding dismissed as unverified:** two lanes reported a dangling "§13" reference — an artefact of the orchestrator's own scrubbed packet, which replaced `## 13. Cold-eyes loop log` with an unnumbered heading. The real document was always correct; the scrubber was fixed for loop 2. **Every prescribed grep was executed before landing (4b-x), and two of the fixes were wrong.** (i) The replacement INV-1 leg `\bDecimal\b|\bfloat\(` **fired on correct code** — `\b` matches the word "Decimal" in the module's own docstring, which will say why the module holds none; narrowed to the constructor form `\bDecimal\(|\bfloat\(`, whose two blind spots (a bare import, a bare annotation) are now stated with leg (a) named as the real catcher. (ii) The justification written for INV-12's anchor was false: `\btr\(` does **not** match `str(` — the word boundary fails against the preceding `s`. The lanes' claim was about the *unanchored* `tr(` the earlier draft specified, which does match (`label = str(month)`); the sentence now cites the pattern that actually misfires. Both corrections came from running the greps, not from reading them. 4c then caught one more piece of this loop's own collateral before the commit: the rewrite left **INV-10 with no `*Test:*` clause at all** (a `*Scope:*` clause had displaced it), which `spec_lint` reported as `invariant_no_test` — added, with the `amount_minor == 0` row that is the only value the two expenditure definitions bucket differently. INV count 12 → 14; §11 18 rows / 5 `nothing`s → **22 / 7** (this figure was written as "20 / 7" at the time and corrected in loop 2 — the third hand-miscount of this one table, which is why §11 now states the command that produces it); 603 → 922 lines. Not converged — loop 2 owed. |
| 2 | 2026-08-05 | 3, strong, cold, same shared packet shape, scrubber defect fixed (dims: 5×8, 13×7, 4×6, 6×6, 15×6, 10×4, 2×3, 1×2, 9×1, 7×1, 11×1) | 3 | 8 | 12 | 8 | 31 verified, 0 unverified. All fixed. **Origin split: ~6 draft defects, ~25 fix collateral** — a decisive first-split margin, which licenses the harder 4b sweep rather than a stop; loop 1 was a structural rewrite (row → merchant family) and this loop is overwhelmingly its ripples. **All three CRITICALs are loop 1's own.** (1) §4.5 still prescribed `rows_in_range` for the baseline windows while §4.6's new `excess` needs per-family sums on *both* sides — and `rows_in_range` returns no `description`. §10 then contradicted §4.5 *and itself* between its own two paragraphs. Following §4.5 makes every family's baseline 0, which collapses `excess(f)` to `spend_in_M(f)` — **silently restoring the largest-row rule §2.2 exists to reject**, with every fixture whose cause family has zero baseline spend staying green. All four windows now read `drill_rows_in_range`, and INV-7 gained leg (c) — a cause family with *non-zero* baseline spend — as the only fixture shape that can catch the regression. (2) INV-7's own worked expectation was **arithmetically false**: it asserted `cause is None` for the §2.2 vault "because living's R1,500 excess does not clear `0.6 × 1500`" — but 0.6 × 1500 = 900 and 1500 clears it by 1.67×. The leg would have gone **red against a correct implementation**, and the natural repair is to weaken the cause gate §2.2 spent a section establishing. Restated: the candidate *is* the grocer, with `residual == 0` so slot 3 is correctly omitted; a separate honest `cause is None` fixture spreads the movement across three merchants. (3) §4.8's condition 5 tested a fact `MonthSummaryInput` does not carry — the identical "a tuple of totals cannot distinguish no-rows from rows-summing-to-zero" argument loop 1 made for the *baseline* and did not apply to `M`; added `month_has_rows`, and dropped `prior_months_with_data` as a second representation of `len(prior_minor)`. HIGHs: the templates interpolate the two **signed** fields with no `abs` rule, so `LOWER` renders "cost you -R500 less than your usual month" and slot 3 "you were (R440) better than normal" under the bracket style — `{amount}` is now always a magnitude, pinned by an INV-14 leg run under both `NegativeStyle` settings; `excess > movement` is **the same condition as** `residual < 0`, so slot 2's unconditional "Most of it" described a quantity larger than the movement it apportioned — INV-9's own second fixture (excess 130% of movement) demonstrates it, and slot 2 gained an "All of it and more" variant; the family mean's **divisor and rounding were unspecified**, a R600 swing on a family seen once in three windows, with §4.8 condition 1 actively teaching the opposite convention — now `_BASELINE_MONTHS` with absent windows contributing 0, §4.2's rounding idiom, and the distinction from condition 1 stated; INV-3 and INV-7 were filed against a hermetic detector that is *handed* the windows and the candidate already computed, making both legs vacuous — moved to service level, and §7's split is now stated as a contract with the rule that decides it; INV-10's fixture asked for four consecutive 31-day months, which **do not exist** (longest Gregorian run is two, measured); a *partly* imported month passes all five silence conditions and renders the same false reassurance condition 5 exists to prevent, now §6.9 with FIBR-0038 named in §9 as the dependency; and `_MIN_MONTH_BASELINE_MAJOR = 50`, inherited from `alerts.py`'s per-category floor, left the relative gate **dead** below a R1,000 baseline — measured, a R60 baseline with R159 spend is a **+165% swing rendering "looked like a normal month"** — so the floor is now *derived* (`_MIN_MOVE_MAJOR * _MATERIAL_DEN // _MATERIAL_NUM`) and the two gates coincide exactly at it. MEDIUMs: the strip had no source for the currency symbol (the same argument loop 1 made for `exponent` and did not finish) — `set_summary(summary, symbol)` is now the stated seam; `{month}`'s year suffix had no template, no clock and would have been built by concatenation against `coding.md` — two `month` templates plus a service-computed `show_year`; INV-13's stand-in raised on the *first* vault read, so the leg passed against an implementation that never calls the service, and its `_refresh_tab` leg could not distinguish the wrong implementation at all — three scoped legs now, and the invariant additionally requires the guards to **hide** the strip rather than leave a stale sentence naming last month; `MODE_SPECIFIC_MONTH` with a missing year/month passed the allow-list and summarised a different month than the selector shows; slot 3 had no materiality floor, so a R0.40 residual rendered; slots 2 and 3 had no partial variants, so §6.2's whole mitigation covered one sentence of three; `MonthCause.name` had three mutually exclusive definitions across §4.6/§4.7/§6/INV-12 and no rule for *which* row supplies it; `MonthCause.spend_minor` was consumed by nothing and invited the sentence to print the gross figure — dropped; refunds are never netted, now stated in §4.5 and §6.10; `merchant_name` is documented as a **filter** for `services.recurring` and this is the second such case, now §6.6 and a §12 docstring amendment. LOWs: `days`/`partial`/`started` undefined for the future state, with the specific trap that `partial=True` would make INV-5's condition-4 leg vacuous; INV-3's `days == 28` leg is wrong in a leap year; INV-1 leg (a)'s field sweep reds on `bool` (`type(True) is int` is `False`, measured) and on a legitimate `None`; §4.9's cited grep returns 18 lines, not the 8 its table shows; INV-12 cited a measurement "against" a module that does not exist; INV-10's scope clause named a divergence unreachable under its own scope; §4.4's "three times larger" compared against a figure no longer in the document; §10 undercounted the added reads by two. **4b-x:** every prescribed command was executed — the derived floor was checked to remove the dead zone at every baseline from R1,000 up, the four-consecutive-31-day-months impossibility was computed rather than asserted, and §11's tally is now emitted by a stated `awk` rather than counted. INV count 14 → 14; §11 22 rows / 7 `nothing`s → **28 / 11**, the rise being four newly-named failure modes and two new covered rows; 922 → 1203 lines. Not converged — loop 3 owed as the confirming pass. |
| 3 | 2026-08-06 | 3, strong, cold, same shared packet shape (dims: 15×7, 4×7, 13×6, 6×5, 5×4, 10×4, 2×2, 12×2, 9×1, 1×1) | 2 | 3 | 9 | 9 | 24 verified, 0 unverified. **STOPPED UNCONVERGED — nothing fixed this loop.** Origin split: ~1 draft defect vs ~23 fix collateral, which is collateral dominating for the **second consecutive loop** and fires `/cold-eyes`' stop-and-consolidate trigger; the project's `--max-loops 7` funds more loops but the trigger is independent of the cap, and past this point a growing share of each loop's findings are defects the previous loop's fixes introduced. **The whole tail is written up at lane-level detail in [`docs/reviews/FIBR-0231-loop3-tail.md`](../reviews/FIBR-0231-loop3-tail.md)** — it is not lost, and re-running the review to rediscover it would cost a full three-lane dispatch to regenerate what is already on disk. Headline findings, both of which change what gets built: (1) **§4.4's common-day-count rule is neutral only for *uniform* spend** — a fixed-day-of-month debit order occupies a different day *number* in February than in a 30/31-day month, so truncation includes it on one side of the comparison and excludes it from the other. Worked by lane C against this spec's own constants: rent R7,000 on the 30th (Feb: the 28th) plus R5,000 of other spend, behaviour never changing, renders *"February cost you R7,000 more than your usual month. All of it and more was one thing — Landlord, R7,000 more than usual"* — every clause false, annually, and §2.2's merchant-family fix does not save it because §4.7 truncates the family baseline windows too, so the landlord's own baseline reads 0. The March mirror renders the reassuring inverse. §6.1 asserts the bias is symmetric and "understates both sides"; it is neither. (2) **The derived floor killed the absolute materiality gate** — all three lanes independently: condition 2 guarantees `baseline >= minor(1000)`, so the relative gate's threshold `baseline/10 >= minor(100)` *is* the absolute one, and relative-pass implies absolute-pass at every exponent. INV-6's "relative only" leg is therefore **empty**, the fixture loop 2 prescribed for it fails the relative gate too (`100 × 9999 < 10 × 100000`), so the leg silently duplicates "neither gate" and **passes green against an implementation with no relative gate at all** — while §11 records it as the sole defence of the derived floor. §4.6's "Both, because either alone misfires", §6.2's day-8/day-15 mechanism and §6.8's exponent-0 analysis are all downstream of the same collapse. HIGHs: INV-14's sign check asserts "no `-` or `(` **before a digit**", but `_format_amount` puts the currency symbol between the sign and the first digit (`-R 500,00`), so the leg passes against precisely the defect its own *Breaks when* names — and its "under both `NegativeStyle` settings" sweep is unrunnable, `set_summary` having no style parameter; INV-1's stated breach (`movement / baseline`) is invisible to **both** its legs, the float never leaving the comparison. MEDIUMs: "All of it and more" is false at `excess == movement`, which is exactly where INV-7 leg (a) — the §2.2 flagship vault — lands; the tie-break test is filed in the hermetic detector file where `candidate` is a single pre-chosen input, the one place loop 2's own routing correction did not reach; INV-5's condition-4 fixture is blocked by conditions 4 and 5 at once (§4.7 sets `month_has_rows = False`), the identical vacuity the paragraph catches for `partial`; INV-9's strip leg is allocated in §11 and in no §7 file, so a strip selecting the correction template on the sign of `movement` — §2.1's exact error — passes the invariant as filed; `set_summary`'s required `symbol` cannot be supplied from the `except VaultLockedError` block that INV-13 requires to hide the strip; clearing the strip at the **top** of `refresh()` would close all eight call sites for one line; an income-only baseline month is admitted as real data when in practice it is always a partial import; INV-10's zero-row clause cannot go red. LOWs incl. `home.py` being the **third**-largest UI module (main_window 1785, import_wizard 1058) not the second; INV-12's grep rationale refuting itself (`\btr\(` *does* exclude `str(`, so `\b` **is** a fix and `\.tr\(` is the weaker choice); §4.4 calling an 8.70% bias "an invented narrative" when it does not clear the 10% gate. **Split judgement: 2 of 3 lanes said do not split** — §2.1/§2.2 are what make §4.6 legible — but **all three independently named the same trim**: ~80–100 lines of review archaeology ("an earlier draft set it to 50", §11's commentary about its own tally, the parenthetical grep justifications) addressed to a reviewer rather than to the implementer §14 names as the audience. That belongs here in §13. **Next session: fold the tail in, do the trim, then one confirming loop — not a fresh review.** |
| fold | 2026-08-06 | none — `/apply-fixes` over the loop-3 tail, no review dispatched | — | — | — | — | **All 24 findings folded in; 0 deferred, 0 dismissed.** Two changed the design rather than the prose. (1) **§4.4's common-day-count rule is gone.** A complete `M` is now compared **whole calendar month against whole calendar months**, and only a partial `M` truncates — to a head capped at `L_min − 1`, below every window month's last day. That is the tail's option (c), taken over (a)/(b) because the defect fabricates a verdict *and* a named payee annually. The cost it buys back is §6.1's February bias, which is sub-threshold (8.70% against a 10% gate), *true* rather than invented, and now argued on the merits in §4.4 with the rejected alternatives recorded in §8 (items 6 and 7) so the collapse cannot be re-proposed as new. Consequences swept: §3 decision 3, §4.3, §4.7's `days`, INV-3 (restated from "every window shares one day count" to "a payment recurring on the same nominal day contributes nothing to `movement`" — a claim about the failure, not about the mechanism), **INV-10 became unconditional for a complete `M`** (the strip and the tile now read the same bounds, which is a strengthening, not a rewording), §6.1, §6.7, §8.5, §10 and two §11 rows. (2) **The absolute materiality gate is stated as belt-and-braces.** Above the §4.8 floor, relative-pass implies absolute-pass at every exponent, so INV-6 dropped to three legs (neither / absolute-only / both) and the "relative only" leg — which would have duplicated "neither" and passed green against an implementation with no relative gate — is gone; §11's floor row is now a direct assertion over the constants, and §4.6, §6.2 and §6.8 are rewritten to the same fact. Also folded: `month_has_rows` **dropped** (the has-data test is now ≥1 non-transfer *spend* row, which makes the field exactly `spend_minor > 0` — an income-only baseline month is a partial import, not a real zero); `MonthSummaryStrip.clear()` added, because the `except VaultLockedError` block that must hide the strip has no `symbol` in scope; `refresh()` clears the strip as its **first** statement, closing all eight call sites for one line instead of guarding six; slot 2 split three ways (`<` / `==` / `>`) because "All of it and more" was false at `excess == movement`, which is where §2.2's own flagship vault lands — 16 templates → **18**; INV-14's sign check rewritten as a positive assertion (the specified `[-(]\d` search cannot fire — `_format_amount` puts the currency symbol between the sign and the first digit) and its unrunnable `NegativeStyle` sweep dropped; INV-1 gained an `ast.Div` leg, the only one that sees its own stated breach; INV-9's strip leg allocated to a real §7 file; the tie-break test moved to the service file, where a two-family fixture is expressible; INV-5's condition-4 fixture unblocked; `home.py` re-ranked third-largest (measured); INV-12's grep anchored `\btr\(`; `name` truncation specified in characters, which also **closed** a `nothing` row; sentence joining and the single `QLabel` specified; `today` computed once in `refresh()`. **The trim ran too:** ~90 lines of review archaeology moved to §13.1 below, and §11's tally is now emitted by its stated `awk` (`32 11`, re-derived rather than carried forward) with its three paragraphs of self-commentary cut to one. 1214 → the current length. **One confirming loop owed** — not a fresh review. |
| 4 | 2026-08-06 | 3, strong, cold, shared byte-identical packet, loop log scrubbed (dims: 15×6, 4×6, 2×6, 5×3, 7×3, 12×3, 13×2, 1×1, 6×1, 10×1, 11×1) | 0 | 6 | 6 | 14 | 26 verified, 1 unverified. All fixed. **The confirming pass: zero CRITICAL, and no design-level defect.** Neither loop-3 blocker was re-raised, and one lane independently re-derived §4.4's window arithmetic (the 8.70% February figure, February as the calendar worst case, `L_min ≤ 30`, all three INV-3 legs), §4.5's relative-pass-implies-absolute-pass proof, and the slot partition (`excess {<,==,>} movement` maps one-to-one onto `residual {>0,==0,<0}`; 6+6+4+2 = 18) and found them correct. **Every HIGH was a test leg that could not fail, or a rationale that argued from the wrong case** — the class this document has produced repeatedly, and the reason the confirming loop was worth running. (1) **Slot 3's materiality floor had no owner**, all three lanes: §4.6 gated the sentence on `abs(residual) >= minor(_MIN_MOVE_MAJOR)` while §4.7 pinned `residual_minor` as `None` *iff cause is None*, so the service could not encode it and the strip would have had to import a private service threshold against the facts-out seam. The detector now nulls `residual_minor` whenever no correction is warranted, exactly as it nulls `cause` for slot 2, so `residual_minor is not None` **is** the render condition; INV-7(a), INV-14 and a new §11 row follow it. (2) **INV-10's second leg used `M` = February**, which is the one month that cannot distinguish the whole-month rule from the rejected common-day-count rule — `L_min = 28 = len(M)`, so February's own window is identical under both and only the baselines (which the leg does not read) move. Now `M` = March with a February baseline and spend on 29–31. (3) **INV-12's grep was green exactly when its invariant was broken** — the named breach is a sentence assembled *without* `tr()`, which no search for `tr(` can see; a structural leg (the only `str` fields are `month` matching `^\d{4}-\d{2}$` and `cause.name`) is now the catcher, and the grep additionally missed `_tr(` (`_` is a word character, so `\btr\(` has no boundary) — the very form §8 item 1 names as the *precedented* design. Executed against a scratch module before landing: the new pattern catches `tr(`, `_tr(`, `self._tr(` and still excludes `str(`, `attr(`, `mystr(`. (4) **§7's detector-file manifest omitted INV-1 leg (c)**, the `ast.Div` walk the invariant itself calls its catcher, and the derived-floor leg — while §7 declares the split "a contract, not a preference". (5) **§4.3 justified condition 4 from a case condition 5 already covers** (a future month with no rows is silenced by `spend_minor == 0`), so an implementer could read condition 4 as redundant and drop the only guard against a post-dated-row future month. (6) **§4.9 cited a comment in `home.py` that does not exist** — the positional-`amount_prefs` trap is real (it is the sixth slot) but no comment warns of it, and the claimed binding target was wrong. MEDIUMs: INV-1's legs were all blind to a **float literal** (`baseline * 0.1` has no `ast.Div`, no `float(`, and returns `bool` — executed and confirmed), so leg (c) gained the constant check; INV-13 leg (b) asserted the strip is hidden with no precondition that it was ever **visible**, passing against a fresh `HomeView`; INV-14 asserted 18 *pairwise-distinct* labels, which a single `"So far, "` prefix on the joined block satisfies while leaving slots 2 and 3 past tense — now per-slot substring containment; §11's tie-break fixture (two equal families, no baseline spend) yields `cause is None`, since `movement = 2E` fails `100·E ≥ 60·2E` — a *falling* third family is needed and is now worked; INV-5's stated reason for `partial = False` was false once §4.4 set `days = len(M)` (condition 3 cannot fire at 28–31 days) — the real constraint is that the **relaxed** counterpart needs `spend_minor > 0`; INV-9's fixture named `baseline_minor`, not a `MonthSummaryInput` field. LOWs: "any four consecutive months contain at most two 31-day months" is **false** (Jul–Oct has three) though `L_min ≤ 30` survives on the true fact that no three consecutive months are all 31 days; the partial cap is 28, not 27, in a leap year; §8's list was numbered 1,2,3,4,5,8,9,6,7 after the fold appended two items; `k` was undefined in §4.2's rounding idiom; `{name}` meant both a merchant and a month (the month forms are now `{month_name}`); a full partial render stacked **three** "So far"s, so slots 2 and 3 now mark themselves provisional by tense instead; §1's property ranking was misquoted in two places (property 3 is *last*, not "above everything but non-invention"); ₩1,000 is ~US$0.70, not US$6.50; the status header narrated review process, which briefs a cold reader on prior-loop fixes. **One dismissed as unverified:** a lane called for a table of contents — `doc_integrity`'s `toc_gap` check returns 0 and no sibling spec carries one. **Origin split: ~12 collateral vs ~14 draft defects** — collateral did not dominate, so no stop-and-consolidate trigger. §11 32 rows / 11 `nothing`s → **33 / 11** (the new slot-3 floor row), re-derived by the stated `awk`. 1437 → 1508 lines. **CLEARED FOR CODE.** |

### 13.1 Superseded draft decisions and their evidence

Moved here from §§4–11 on 2026-08-06, when all three loop-3 lanes independently
named the same trim: roughly ninety lines of *review archaeology* — the record of
what an earlier draft got wrong, and of which greps were run to check a claim —
sitting in a document §14 addresses to an implementer. It is kept, because the
evidence is what stops a rule being re-proposed as new; it is kept *here*, because
none of it tells anyone what to build.

**The baseline floor was 50 before it was derived.** The value was inherited from
`alerts.py`'s `_MIN_BASELINE_MAJOR`, which floors *one category's* three-month
average where this one floors a *whole month's* spend (§4.2). Measured against 50
at exponent 2: a baseline of R60 clears the floor, a spend of R159 clears the
relative gate (`100 × 9900 ≥ 10 × 6000`) and **fails** the absolute one
(`9900 < 10000`), so a **+165% swing renders "looked like a normal month"** — the
reassuring verdict on arithmetic that does not support it, which is what §1
property 3 forbids. The derived value closes that dead zone by making the two
gates coincide exactly at the floor. What loop 3 then found is the other side of
the same coin, and it is in §4.5: making them coincide at the floor makes the
absolute gate redundant *above* it.

**INV-7 leg (a) once asserted `cause is None`** for the §2.2 vault, on the claim
that the grocer's R1,500 excess "does not clear `0.6 × 1500`". It clears it by
1.67×. The leg would have gone **red against a correct implementation**, and the
natural repair — weakening the cause gate — is exactly the rule §2.2 exists to
establish.

**INV-10's fixture once asked for four consecutive 31-day months.** The longest
run in the Gregorian calendar is two, so the fixture was unconstructible;
computed rather than asserted, 2026-08-05.

**INV-12's anchor was justified backwards once.** The claim that `\btr\(` matches
`str(` is false — the word boundary fails between the `s` and the `t`. What does
match is the *unanchored* `tr(` an earlier draft specified. Verified 2026-08-05
against a scratch module holding a `str(...)` call.

**INV-1's grep was `\bDecimal\b|\bfloat\(` for one loop, and fired on correct
code**: `\b` matches the word "Decimal" in the module's own docstring, which will
say why the module holds none. Narrowed to the constructor form.

**Grep counts whose bare form disagrees with the figure in the text.** Each was
stated inline for a loop, which is the archaeology this section absorbs:

- `grep -rn "confirmed_transfer_txn_ids" src/ | wc -l` → **6**, against the four
  call sites §4.5 names. The extra two are the `def` in
  `transfer_detection.py` and a mention in that module's docstring.
- `grep -n "refresh()" src/finbreak/ui/{home,main_window}.py` → **18**, against
  the eight `refresh()` call sites §4.9 tabulates. The rest are the nine other
  tabs' refreshes and a docstring mention at `home.py:73`. The filtered form is
  `grep -n "self\.refresh()\|_home_tab\.refresh()"`.
- `grep -rn "rows_in_range" src/finbreak/services/` → **5**, of which
  `drill_rows_in_range(` is **1**; the plain pattern matches both names, which is
  why §10 states the split.
- `grep -n read_minor_unit_exponent src/finbreak/ui/home.py` → nothing, which is
  why `exponent` is a `MonthSummary` field (§4.7).

**§11's tally was miscounted by hand three times**, twice in the same direction,
before the `awk` that emits it was written into the section. That is why §11
states a command rather than a number reached by counting.

**`month_has_rows` existed for one loop.** It was added because a tuple of totals
cannot distinguish "no rows" from "rows summing to zero" — true while the has-data
test was *any* non-transfer row. Once the test became a *spend* row (§4.8
condition 1), the fact it carried was exactly `spend_minor > 0`, so it became a
second representation of a derivable value and was dropped.
