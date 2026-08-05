# FIBR-0231 — Plain-English monthly summary: the app does the reading

**Status:** 🚧 **DRAFT** (2026-08-05) — `/cold-eyes` gate not yet run (§13).
**Kind:** feature.
**Source:** ROADMAP FIBR-0231 (user-request-2026-08-05, layman-comprehension
suggestions).
**Pairs with:** FIBR-0012 (the dashboard this strip sits at the top of),
FIBR-0172 (`AlertService` — whose spike detector this borrows its baseline shape
from without importing it, §4.2), FIBR-0138 (`drill_down`, the sibling pattern
for keeping a non-QObject service translation-free), FIBR-0175 (compare periods
side by side — deliberately *not* this item, §9).

**Layman:** The dashboard shows you numbers and charts, and leaves you to work
out what they mean. This adds one short line at the top that just says it:
"September cost you R2,340 more than your usual month. Almost all of it was one
thing — a R1,900 vet bill." When the month is ordinary it says so in four words,
and when there isn't enough history to know what "usual" means, it says nothing
at all rather than guessing.

---

## 1. Goal

One short block of prose at the top of the Home dashboard that states what
happened to the user's money this month, in words, with no chart-reading
required.

Three properties, in priority order. Where they conflict, the earlier wins:

1. **Never invent a narrative.** Every clause is either backed by a figure that
   clears an explicit threshold, or it is not rendered. Silence is a valid — and
   frequently correct — output.
2. **Never overclaim on thin data.** The strip is absent, not vague, when the
   vault cannot support a comparison.
3. **Be worth reading when it does speak.** A user who reads only this line
   should not be misled by having skipped the charts below it.

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
easier to reach for. §4.5 therefore selects the third sentence's template on the
sign of `movement − cause`, never on the sign of `movement`, and INV-8 pins it.

## 3. Scope decisions

Recorded with who made them. User decisions were taken 2026-08-05 in response to
a two-question batch.

1. **Month period modes only; the strip is absent for year modes.** *(User.)*
   `MODE_PREVIOUS_MONTH`, `MODE_CURRENT_MONTH` and `MODE_SPECIFIC_MONTH` get a
   summary; `MODE_YEAR_TO_DATE` and `MODE_SPECIFIC_YEAR` render nothing. A year
   needs a year-over-year comparison and 24 months of history; that is FIBR-0175's
   territory, and building it here would double the design for a case almost no
   vault can satisfy.
2. **Up to three short sentences, from fixed slots.** *(User.)* Verdict, then
   optionally cause, then optionally correction. Each slot has its own evidence
   test, so an unremarkable month collapses to one short sentence without a
   separate "brief mode".
3. **The current (incomplete) month is included, and is compared like-for-like.**
   *(Author.)* The user's chosen option keeps `MODE_CURRENT_MONTH`, so the strip
   must appear mid-month — which makes a full-month baseline wrong by
   construction. §4.3 truncates every window to the same elapsed day count rather
   than projecting the month forward. Projection is the invention property 1
   forbids.
4. **Account-scoped, following the Home account selector.** *(Author.)* The
   recurring card and the alert count are deliberately unscoped (FIBR-0012 D5,
   FIBR-0172 D8), but those sit *beside* figures rather than describing them. This
   strip characterises the very tiles rendered below it, so an unscoped sentence
   above scoped tiles would contradict them on screen. Scope follows the tiles.
5. **The service returns structured facts, not strings.** *(Author.)* See §4.6.
6. **No new dependency, no schema change, no settings key.** *(Author.)* Every
   figure comes from `ReportingRepository`; thresholds are module constants, in
   one home, exactly as `alerts.py` documents its own (D10 there).

## 4. Design

### 4.1 Shape and placement

Two new modules, mirroring the `services/alerts.py` + `ui/alerts_dialog.py` split:

| File | Contents |
|---|---|
| `src/finbreak/services/month_summary.py` | the pure detector `summarise_month`, its input/output dataclasses, the threshold constants, and the vault-scoped `MonthSummaryService` that prepares inputs |
| `src/finbreak/ui/month_summary.py` | `MonthSummaryStrip(QWidget)` — the translated templates and the label |

`home.py` is 615 lines (`wc -l src/finbreak/ui/home.py`), the largest UI module
after `main_window.py`; the strip gets its own module rather than growing it
further, which is also what lets the templates be tested without a `HomeView`.

Placement in `HomeView._build_dashboard`: between `self._build_selectors()` and
the Net strip. It is the first thing on the page because a reader who stops after
one line must have read the most useful line.

### 4.2 The baseline

The baseline is the `_BASELINE_MONTHS` calendar months immediately preceding the
summarised month, each measured over the same elapsed-day window (§4.3).

```python
_BASELINE_MONTHS = 3   # complete prior months averaged into "your usual month"
```

Three is the same figure `alerts.py::_SPIKE_WINDOW` uses, for the same reason —
long enough that one unusual month does not become "usual", short enough to track
a real change in circumstances. It is **deliberately a separate constant, not an
import.** `alerts.py` documents its thresholds as living in one home "so v2 can
lift them into Settings"; importing `_SPIKE_WINDOW` here would silently couple two
features' tuning, so that a user widening the spike window would also, invisibly,
change what "your usual month" means.

The baseline value is the integer round-half-up mean of the per-month spends,
computed with the same idiom `detect_category_spikes` uses so the two features
round identically:

```python
average = (sum(prior) + k // 2) // k
```

### 4.3 Like-for-like windows

Let `M` be the summarised month and `today` the injected clock.

`M` is **partial** iff `M` is the calendar month containing `today` *and* `today`
is before `M`'s last day. Note this makes partiality a property of the resolved
month, not of the mode: a `MODE_SPECIFIC_MONTH` pick of the current month is
partial too, and on the last day of a month `MODE_CURRENT_MONTH` is not.

- **Complete `M`:** each window is that month's full `[first, last]` bounds, via
  `reporting._month_bounds`.
- **Partial `M`:** `elapsed = today.day`. Every window — `M`'s and all three
  baseline months' — runs from day 1 to `min(elapsed, <that month's last day>)`.

The clamp matters: summarising 31 January against a 30-day November must not
silently compare 31 days to 30. Clamping shortens the *baseline* window, which
makes the baseline smaller, which makes the month look *worse* — a bias toward
alarming the user. It is accepted because the alternative (dropping the month
from the baseline) loses a quarter of the evidence, and the bias is bounded at
one day in ~30. §6 records it as a known bias rather than hiding it.

`resolve_period` is reused to resolve the mode to `[start, end]`; the summarised
month is `(end.year, end.month)`. This is well-defined for the three month modes
and is why §3 decision 1 excludes the year modes, where `end.month` carries no
meaning.

### 4.4 What counts as spend

Spend is the sum of magnitudes of rows with `amount_minor < 0` in the window,
excluding confirmed transfers — the same exclusion every reporting figure applies
via `TransferDetectionService.confirmed_transfer_txn_ids()` (6 call sites in
`src/`; `grep -rn "confirmed_transfer_txn_ids" src/ | wc -l`).

Uncategorised rows **are** included. A spike alert excludes them because it must
name a category; a month total must not, or the sentence would describe a
different number than the tile below it.

Rows come from `ReportingRepository.rows_in_range(start_iso, end_iso,
account_ids)` for the baseline months, and `drill_rows_in_range(...)` for `M`,
which additionally carries `description` — needed only for the cause clause.

### 4.5 The three slots

All arithmetic is integer minor units. `exponent` comes from
`read_minor_unit_exponent`; `floor(n) = n * 10**exponent`.

```python
_MATERIAL_NUM, _MATERIAL_DEN = 10, 100   # a move must be >= 10% of baseline
_MIN_MOVE_MAJOR   = 100   # ...and >= 100 major units in absolute terms
_MIN_BASELINE_MAJOR = 50  # ...over a baseline of at least 50 major units
_CAUSE_NUM, _CAUSE_DEN = 60, 100   # one txn "explains" a move at >= 60% of it
_MIN_ELAPSED_DAYS = 7     # a partial month says nothing before day 7
```

Let `spend` be `M`'s window spend, `baseline` the §4.2 average, and
`movement = spend − baseline` (signed; positive means spent more).

**Slot 1 — verdict.** Always present when the strip renders at all.

`movement` is **material** iff *both* gates pass:

```
_MATERIAL_DEN * abs(movement) >= _MATERIAL_NUM * baseline     # relative
abs(movement) >= floor(_MIN_MOVE_MAJOR)                        # absolute
```

Both, because either alone misfires: 10% of a small baseline is noise, and a
fixed absolute move against a large baseline is unremarkable. Material and
positive → `HIGHER`; material and negative → `LOWER`; otherwise → `NORMAL`.

**Slot 2 — cause.** Rendered only when *all* hold:

- the verdict is `HIGHER`. A single large *expense* cannot explain spending
  *less*, and the transaction that would explain a `LOWER` month is the one that
  is absent — unobservable by construction. This is the single most likely wrong
  turn in the design, and INV-7 pins it.
- a largest single non-transfer expenditure row exists in `M`'s window; call its
  magnitude `cause`.
- `_CAUSE_DEN * cause >= _CAUSE_NUM * movement`.

Ties (two rows of equal magnitude) resolve to the lower `id`, so the sentence is
stable across refreshes.

**Slot 3 — correction.** Rendered only when slot 2 rendered *and*
`residual = movement − cause` is non-zero. The template is chosen by the **sign
of `residual`** (§2.1):

| `residual` | Sentence |
|---|---|
| `< 0` | "Take that out and you were {abs} better than normal." |
| `> 0` | "Even without it you were {abs} above normal." |
| `== 0` | *(omitted — it would say "and then you were exactly normal")* |

### 4.6 The translation seam

`summarise_month` returns a `MonthSummary` of **facts** — an enum verdict and
integer amounts — and never a user-facing string. `MonthSummaryStrip`, a
`QObject`, owns every template and calls `tr()` on it.

This is the FIBR-0138 `DrillLabels` pattern taken one step further. `DrillLabels`
injects translated *labels* into the service because drill nodes carry a `label`
field; a sentence has grammar — clause order, sign-selected templates, the
number-agreement in "one thing" — which cannot be expressed as injected nouns. So
the direction is reversed: facts out, phrasing in the UI. This keeps
`services/month_summary.py` entirely translation-free, a stronger position than
`services/pdf_export.py`'s `_tr` seam, and it is what makes the detector testable
with no Qt translation context.

```python
class MonthVerdict(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"
    NORMAL = "normal"

@dataclass(frozen=True)
class MonthCause:
    txn_id: int
    description: str
    amount_minor: int          # positive magnitude

@dataclass(frozen=True)
class MonthSummary:
    month: str                 # "YYYY-MM"
    partial: bool
    elapsed_days: int
    verdict: MonthVerdict
    spend_minor: int           # positive magnitude
    baseline_minor: int        # positive magnitude
    movement_minor: int        # signed
    cause: MonthCause | None
    residual_minor: int | None # signed; None iff cause is None

@dataclass(frozen=True)
class MonthSummaryInput:
    month: str
    partial: bool
    elapsed_days: int
    spend_minor: int
    prior_minor: tuple[int, ...]
    largest: MonthCause | None

def summarise_month(
    item: MonthSummaryInput, exponent: int
) -> MonthSummary | None: ...
```

### 4.7 The silence ladder

`summarise_month` returns `None` — the strip hides entirely — when any holds, in
this order:

1. `len(prior_minor) < _BASELINE_MONTHS`, or any baseline month contributed **no**
   non-transfer rows at all. "Your usual month" is a claim about three months; two
   months of history cannot support it, and a month with no rows is missing data
   rather than a zero-spend month.
2. `baseline < floor(_MIN_BASELINE_MAJOR)`. Too little money moving to
   characterise.
3. `partial and elapsed_days < _MIN_ELAPSED_DAYS`. Six days pro-rated against six
   days is arithmetically fine and epistemically worthless — one grocery run
   swings it past every threshold.

The strip is also absent, without consulting the detector at all, for the two
year modes (§3 decision 1) and when `HomeView` is showing its getting-started
page (`transaction_count() == 0`, FIBR-0012 INV-7).

### 4.8 Wiring

`HomeView.__init__` gains a `month_summary: MonthSummaryService` parameter.
`main_window._build_workspace` constructs it alongside the other five services.

**The parameter is added last, before `amount_prefs`, and `amount_prefs` must
stay keyword-passed** — `home.py` already carries a standing comment that a
positional `amount_prefs` binds to `recurring`; a sixth service parameter widens
that trap rather than creating it.

`HomeView.refresh()` calls the service and passes the result to the strip, at the
point where `_render_net` is called today. No new error-handling surface: both
slots that reach `refresh()` (`_on_period_changed`, `_on_account_changed`) already
wrap it in `except VaultLockedError: return` (home.py, verified 2026-08-05), so a
vault that locks mid-render is caught by the existing guards.

## 5. Invariants

**INV-1 — integer-only arithmetic.** No `Decimal` or `float` appears in
`services/month_summary.py`. Every figure is integer minor units; the crossing to
`Decimal` happens once, in the strip, via `to_display_decimal`.
*Breaks when:* a percentage is computed as `movement / baseline` instead of by
cross-multiplication.
*Test:* `grep -nE "Decimal|float\(" src/finbreak/services/month_summary.py`
returns nothing.

**INV-2 — confirmed transfers are excluded from every figure.** From `M`'s spend,
from every baseline month's spend, and from the cause candidate set.
*Breaks when:* a transfer between two of the user's own accounts is counted as
spending, which would make every month with a transfer look expensive.
*Test:* a vault with one confirmed transfer pair produces the identical
`MonthSummary` to the same vault with those two rows deleted.

**INV-3 — the strip is absent for the two year modes.** `MODE_YEAR_TO_DATE` and
`MODE_SPECIFIC_YEAR` render nothing, and the detector is not called.
*Breaks when:* a mode check keys on "not a specific month" and lets year-to-date
through, summarising a 7-month window as though it were a month.
*Test:* the strip's `isHidden()` is true under both year modes and false under all
three month modes, given a vault with sufficient history.

**INV-4 — windows are like-for-like.** When `M` is partial, `M`'s window and all
three baseline windows cover day 1 to `min(today.day, <month length>)`.
*Breaks when:* a half-finished month is compared against three full ones, which
makes every month look ~50% cheaper than usual until it ends.
*Test:* on 14 March with identical daily spend in every month, `movement_minor ==
0`; with the baselines taken over full months it is strongly negative.

**INV-5 — insufficient history yields `None`, never a guess.** Each of §4.7's
three conditions independently returns `None`.
*Breaks when:* a vault two months old produces "your usual month".
*Test:* one leg per §4.7 condition, each asserting `summarise_month(...) is None`,
and each with the blocking condition relaxed to assert a non-`None` result — so
the leg cannot pass against a detector that returns `None` unconditionally.

**INV-6 — `NORMAL` unless both materiality gates pass.** A movement clearing only
the relative gate, or only the absolute one, yields `NORMAL`.
*Breaks when:* one gate is dropped, and the strip starts announcing R30 movements
as news.
*Test:* four legs — neither gate, relative only, absolute only, both — asserting
`NORMAL, NORMAL, NORMAL, HIGHER`.

**INV-7 — a cause is attached only to a `HIGHER` verdict.** `MonthSummary.cause`
is `None` whenever `verdict` is `LOWER` or `NORMAL`, whatever the transaction set.
*Breaks when:* a month that came in R2,000 *under* baseline is captioned "almost
all of it was one thing — a R1,900 vet bill", which reads as an explanation and
is a non sequitur.
*Test:* a `LOWER` month containing a transaction larger than `_CAUSE_NUM/_CAUSE_DEN`
of `abs(movement)` still yields `cause is None`.

**INV-8 — the correction template is selected by the sign of `residual`.** Not by
the sign of `movement`.
*Breaks when:* §2.1's error ships — a month that is still over budget after
removing its biggest expense is described as "better than normal".
*Test:* `movement=2340, cause=1900` yields `residual_minor == 440` (positive → the
"even without it" template); `movement=1460, cause=1900` yields `-440` (negative →
"better than normal"). The two must select different templates.

**INV-9 — the summary is scoped to the same accounts as the tiles.** The strip and
`ReportingService.summary` receive the identical `account_ids`.
*Breaks when:* selecting one account leaves a whole-vault sentence above
single-account tiles, so the strip contradicts the figures beneath it.
*Test:* with two accounts, selecting one produces a `spend_minor` equal to that
account's expenditure alone, and different from the "All accounts" value.

**INV-10 — the service emits no user-facing string.** `MonthSummary` carries an
enum and integers; no field holds prose beyond `MonthCause.description`, which is
the user's own transaction text passed through unmodified.
*Breaks when:* a sentence is assembled in the service, where `tr()` is
unavailable, silently making the feature untranslatable.
*Test:* `grep -n "tr(\|QCoreApplication" src/finbreak/services/month_summary.py`
returns nothing, **and** the strip renders a full three-sentence summary from a
hand-constructed `MonthSummary` with no service involved.

**INV-11 — the clock is injected.** `summarise_month` and
`MonthSummaryService.summary` take `today: date`; neither calls `date.today()`.
*Breaks when:* the suite passes in August and fails on 1 March, or a partial-month
test becomes unwritable.
*Test:* `grep -n "date.today()" src/finbreak/services/month_summary.py` returns
nothing.

**INV-12 — a mid-render lock does not crash the dashboard.** A `VaultLockedError`
raised by the summary read propagates to the existing slot guards rather than
being swallowed or escaping as a different type.
*Breaks when:* the service catches `VaultLockedError` itself and returns a
partial summary computed from rows it did manage to read — a sentence about a
fraction of the month, presented as the month.
*Test:* a stand-in raising `VaultLockedError` from the repository leaves
`_on_period_changed` returning cleanly and the strip showing its prior content.

## 6. Failure modes

Stated, not hidden. Each is a consequence the design accepts.

1. **The clamp biases partial months slightly alarming.** §4.3: summarising day 31
   against a 30-day baseline month shortens the baseline, inflating `movement`.
   Bounded at one day in ~30 (~3%), which is below the 10% relative gate, so it
   cannot on its own promote a `NORMAL` month to `HIGHER`.
2. **A month whose spending moved for a good reason still reads as a warning.**
   Moving house, a deliberate annual insurance payment, a planned holiday. The
   strip has no notion of intent, and the cause clause is the mitigation: naming
   the transaction lets the reader dismiss it instantly.
3. **`MonthCause.description` is raw bank text.** It may be cryptic
   ("POS 4455 \*\*\*\*1234"). Cleaning it is `text.merchant_name`'s job and is not
   applied here, because a wrong cleanup would misattribute a cause. An ugly true
   description beats a tidy wrong one.
4. **Three baseline months is a short memory.** A user with genuinely seasonal
   spending (December) will see December called expensive every year. Accepted:
   the alternative — a 12-month baseline — needs a year of history before the
   feature works at all, and §4.7 condition 1 already makes the feature quiet for
   new vaults.
5. **A single split payment defeats the cause clause.** A R2,000 expense paid as
   two R1,000 rows never reaches the 60% share, so a month with an obvious cause
   goes unexplained. It degrades to the verdict alone — the correct direction.
6. **The strip disagrees with the trend chart's month labels for a partial
   month.** The chart plots whole months; the strip's current-month figure is
   month-to-date. The `partial` flag drives distinct "so far" phrasing so the two
   are not read as the same number.

## 7. Tests

New feature directory `tests/features/month_summary/` (`spec.md` + tests), per
`docs/standards/testing.md`. No such directory exists today (`ls tests/features/`).

- **`test_month_summary.py`** — the detector, hermetic, no vault and no Qt. One
  case per INV-1 … INV-8 and INV-11, plus §4.7's three silence conditions with
  their relaxed counterparts.
- **`test_month_summary_strip.py`** — the strip under `qtbot`, fed
  hand-constructed `MonthSummary` values. Covers INV-10's second leg, the three
  slot combinations (verdict only / +cause / +correction), both correction
  templates, and `isHidden()` on `None`.
- **`test_month_summary_service.py`** — the service against a real vault fixture:
  INV-2 (transfer exclusion), INV-9 (account scoping), INV-12 (lock guard).

Ripple into existing suites, each a construction-signature change from §4.8:

- `tests/features/dashboard/` and `tests/features/dashboard_focus/` construct
  `HomeView` directly and gain the sixth service argument.
- `tests/features/app_shell/` asserts the dashboard's widget shape and gains the
  strip.

The exact set is *not* enumerated here as a count — it is whatever
`grep -rln "HomeView(" tests/` returns at implementation time, and that command is
the deliverable rather than a number that rots.

## 8. Alternatives considered (and rejected)

1. **Generate the sentence in the service via a `_tr` seam** (the
   `pdf_export.py` precedent). Rejected: it puts grammar in a layer that cannot
   see the user's locale conventions and makes every template untestable without a
   translation context. §4.6.
2. **Reuse `AlertService`'s category spikes as the cause.** Rejected: a spike
   names a *category* over a 3-month window with its own thresholds; the cause
   clause needs the *single transaction* inside this month. Bending the alert
   detector to serve both would couple two thresholds that must move
   independently.
3. **A 12-month baseline, seasonally aware.** Rejected for now — see §6.4. It is
   the natural v2 once vaults in the wild have the history, and it changes only
   `_BASELINE_MONTHS` plus the §4.7 gate.
4. **Project the current month to a full-month estimate.** Rejected: it is the
   invention property 1 forbids. Pro-rating both sides (§4.3) answers the same
   question without asserting anything about days that have not happened.
5. **Put the strip in a dialog, or on its own tab.** Rejected: a feature whose
   entire purpose is to save the reader effort cannot be behind a click.
6. **Let the strip speak for year modes with year-over-year phrasing.** Rejected
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
  any movement is either noise or a life event) and would double §4.5.

## 10. Resource cost

Four repository reads are added per `HomeView.refresh()`: one
`drill_rows_in_range` over `M`'s window and three `rows_in_range` over the
baseline months. Both are indexed range scans over `occurred_on`, the same shape
`summary`, `monthly_trend` and `drill_down` already issue (4 existing call sites
in `services/`; `grep -rn "rows_in_range" src/finbreak/services/`).

No timing figure is stated here, because none has been measured — per the
authoring rule that a number arrives with the command that produced it. If the
added reads prove material, the mitigation is already available: the three
baseline months are exactly the months `monthly_trend` already fetches, and the
two could share one query. That is deliberately **not** done in v1, because the
sharing would couple the strip's window arithmetic to the trend chart's, and §4.3's
day-clamping makes those windows differ whenever the month is partial.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/features/month_summary/test_month_summary.py` (grep leg) |
| INV-2 | `tests/features/month_summary/test_month_summary_service.py` |
| INV-3 | `tests/features/month_summary/test_month_summary_strip.py` |
| INV-4 | `tests/features/month_summary/test_month_summary.py` |
| INV-5 | `tests/features/month_summary/test_month_summary.py` (three conditions × relaxed counterpart) |
| INV-6 | `tests/features/month_summary/test_month_summary.py` (four-leg gate matrix) |
| INV-7 | `tests/features/month_summary/test_month_summary.py` |
| INV-8 | `tests/features/month_summary/test_month_summary.py` + the strip's two-template leg |
| INV-9 | `tests/features/month_summary/test_month_summary_service.py` |
| INV-10 | grep leg + the strip test's hand-constructed `MonthSummary` |
| INV-11 | `tests/features/month_summary/test_month_summary.py` (grep leg) |
| INV-12 | `tests/features/month_summary/test_month_summary_service.py` |
| §4.5's specific threshold *values* (10%, 100, 50, 60%, 7 days) | **nothing** — the tests assert behaviour either side of each constant by reading it, so changing a constant moves the test with it. Deliberate: these are tuning values, not contract. What is pinned is that *both* gates exist (INV-6) and that each silence condition fires (INV-5) |
| §4.3's clamp bias (§6.1) staying under the relative gate | **nothing** — no leg asserts the bound. It is arithmetic on stated constants (1/30 ≈ 3% < 10%), and it would need re-deriving if `_MATERIAL_NUM` fell below 4 |
| Whether the sentence is *useful* — that a real user reads it and understands their month | **nothing**, and nothing can. This is the honest limit of the feature: the tests pin that the arithmetic is right and the phrasing is selected correctly, not that the result communicates |
| §4.2's decision to keep `_BASELINE_MONTHS` separate from `_SPIKE_WINDOW` | **nothing** — a future edit could import the alerts constant and every test would stay green. The rationale is recorded in §4.2 and in the constant's own comment; that is the whole defence |
| §4.5's tie-break (equal-magnitude rows resolve to the lower `id`) | `tests/features/month_summary/test_month_summary.py` — a two-equal-rows fixture, asserted on `cause.txn_id` |
| Ties between the strip's phrasing and the trend chart's month labels (§6.6) | **nothing** — no test renders both surfaces together |

Eighteen rows, **five** with a bolded `nothing`: the threshold values, the clamp
bias bound, whether the sentence communicates, the constant-independence decision,
and the strip/chart consistency.

Two of those five are real gaps a future loop could close — the clamp bound could
be a computed assertion, and a strip/chart consistency leg is writable. The other
three are honest limits: tuning values that are deliberately not contract, a
design decision no test can defend, and the fact that no automated check can tell
whether prose helps a human.

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
- `docs/specs/FIBR-0012.md` — **no change needed.** The dashboard spec's INV-7
  (getting-started iff zero transactions) governs the strip too and is cited
  rather than amended (§4.7).
- `docs/specs/FIBR-0172.md` — **no change needed.** §4.2 deliberately does not
  import its constant, so its D10 "one home" position is untouched.
- `docs/specs/FIBR-0138.md` — **no change needed.** §4.6 extends its
  translation-seam pattern without altering `DrillLabels`.
- `docs/audit-allowlist.md` — **no change expected.** The design introduces no
  known false-positive class; revisit if `/audit` flags the two grep-based
  invariant legs.
- `docs/standards/naming.md` spec-doc row — **stale, amendment pending under
  FIBR-0196.** Line 85 still mandates `<ID>.md` and line 207 rejects variants,
  but the user decided 2026-08-05 in favour of `<ID>-<topic>.md` (a filename a
  human can read). This spec is the first file written under the new rule, so it
  is deliberately the one file in `docs/specs/` that its own standard does not
  yet describe. FIBR-0196 carries the amendment and the back-migration; the
  amendment is a `docs/standards/` edit and therefore trips the rule-14
  `/cold-eyes` gate on its own.

## 13. Cold-eyes loop log

Fresh log — this document has not been reviewed under any other id.

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| — | — | — | — | — | — | — | *(no loop has run; `/cold-eyes` gate pending)* |
