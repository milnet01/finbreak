# FIBR-0231 — Plain-English monthly summary: the app does the reading

**Status:** 🚧 **DRAFT** (2026-08-05) — `/cold-eyes` gate in progress (§13).
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
3. **The current (incomplete) month is included, and every window is truncated to
   a common day count.** *(Author.)* The user's chosen option keeps
   `MODE_CURRENT_MONTH`, so the strip must appear mid-month — which makes a
   full-month baseline wrong by construction. §4.4 truncates rather than
   projecting; projection is the invention property 1 forbids.
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

`home.py` is 615 lines (`wc -l src/finbreak/ui/home.py`), the largest UI module
after `main_window.py`; the strip gets its own module rather than growing it
further, which is also what lets the templates be tested without a `HomeView`.

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
average = (sum(prior) + k // 2) // k
```

### 4.3 Which month, and when there is no month

Let `M` be the summarised month — `(end.year, end.month)` from
`resolve_period(prefs, today)`, which is well-defined for the three month modes
(§3 decision 1 excludes the year modes, where `end.month` carries no meaning).

`M` falls into exactly one of three states:

| State | Test | Treatment |
|---|---|---|
| **future** | `M`'s first day > `today` | render nothing (§4.8 condition 4) |
| **partial** | `M` contains `today`, and `today` is before `M`'s last day | truncated windows, "so far" phrasing |
| **complete** | otherwise | truncated windows, plain phrasing |

**The future state is reachable in two clicks and must be handled explicitly.**
`home.py:255` is `self._year_picker.setRange(1970, 9999)` and `home.py:250` adds
all twelve months, so on 5 August 2026 a user can select "Specific month / 2026 /
09". Without condition 4, `M`'s spend is 0, the three preceding months have data,
`movement = −baseline` clears both materiality gates by construction, and the
strip confidently announces that a month which has not happened was much cheaper
than usual — the most reassuring possible sentence, invented entirely out of
absent data.

### 4.4 Like-for-like windows — one rule, not two

Every window — `M`'s and all `_BASELINE_MONTHS` baseline months' — runs from day 1
to a **common day count**:

```
days = min(elapsed, len(M), len(b₁), len(b₂), … )
```

where `elapsed` is `today.day` when `M` is partial and `len(M)` when it is
complete, and `len(x)` is that month's length from `calendar.monthrange`.

**One rule, applied to both states, because the two-rule version was wrong.** An
earlier draft truncated only in the partial branch and gave complete months their
full `[first, last]` bounds. That leaves the *default* mode — `MODE_PREVIOUS_MONTH`,
always complete — comparing months of unequal length. Worked, for perfectly
uniform daily spend `d`:

```
M = February (28d), baseline Nov(30) Dec(31) Jan(31), mean 30.667d
  movement / baseline = (28 − 30.667) / 30.667 = −8.70%
```

A user whose spending never changed would see February pushed 8.70 points toward
`LOWER` every year — 87% of the way to the 10% relative gate — on a calendar
artefact alone. That is an invented narrative, and it was three times larger than
the partial-month bias the document did record. The common-day-count rule removes
it: with `days = 28` for all four windows, uniform spend yields `movement = 0`.

`elapsed` is `today.day`, which **includes the partly-elapsed current day**. The
alternative (`today.day - 1`) is equally defensible; `today.day` is chosen so the
strip's window matches the Transactions tab's notion of "up to today", and the
resulting bias is recorded in §6.

The residual cost of truncation is real and stated in §6: when a short month is
in the baseline, the last days of the longer months are excluded from every
window, and month-end debit orders cluster exactly there.

### 4.5 What counts as spend

Spend is the sum of magnitudes of rows with `amount_minor < 0` in the window,
excluding confirmed transfers — the same exclusion every reporting figure applies
via `TransferDetectionService.confirmed_transfer_txn_ids()` (4 call sites in
`src/`: `reporting.py`, `alerts.py`, `recurring.py`, `pdf_export.py`. The bare
`grep -rn "confirmed_transfer_txn_ids" src/ | wc -l` returns 6, because it also
matches the `def` in `transfer_detection.py` and a mention in that module's
docstring — the count is stated as call sites, so the two non-calls are named
rather than folded in).

Uncategorised rows **are** included. A spike alert excludes them because it must
name a category; a month total must not, or the sentence would describe a
different number than the tile below it.

`ReportingService.summary` buckets `amount_minor == 0` into expenditure (`else:
expenditure_minor += -amount_minor`) where the rule above excludes it. The two
agree — a zero row contributes zero either way — and INV-10 pins the agreement so
they cannot drift apart silently.

Rows come from `ReportingRepository.rows_in_range(start_iso, end_iso,
account_ids)` for the baseline months, and `drill_rows_in_range(...)` for `M`,
which additionally carries `description` — needed for the merchant grouping.

Thresholds. All arithmetic is integer minor units; `exponent` comes from
`read_minor_unit_exponent`, and `minor(n) = n * 10**exponent` converts a
major-unit constant. (It is *not* named `floor` — it scales, it does not round.
`services/transactions.py::to_minor` does the same job for a `Decimal`; it is not
reused because INV-1 forbids `Decimal` in this module.)

```python
_MATERIAL_NUM, _MATERIAL_DEN = 10, 100   # a move must be >= 10% of baseline
_MIN_MOVE_MAJOR = 100        # ...and >= 100 major units in absolute terms
_MIN_MONTH_BASELINE_MAJOR = 50   # ...over a baseline of at least 50 major units
_CAUSE_NUM, _CAUSE_DEN = 60, 100  # one family "explains" a move at >= 60% of it
_MIN_ELAPSED_DAYS = 7        # a partial month says nothing until day 7
```

### 4.6 The three slots

Let `spend` be `M`'s window spend, `baseline` the §4.2 average, and
`movement = spend − baseline` (signed; positive means spent more).

**Slot 1 — verdict.** Always present when the strip renders at all.

`movement` is **material** iff *both* gates pass:

```
_MATERIAL_DEN * abs(movement) >= _MATERIAL_NUM * baseline     # relative
abs(movement) >= minor(_MIN_MOVE_MAJOR)                        # absolute
```

Both, because either alone misfires: 10% of a small baseline is noise, and a
fixed absolute move against a large baseline is unremarkable. Material and
positive → `HIGHER`; material and negative → `LOWER`; otherwise → `NORMAL`.

**Slot 2 — cause.** The unit is a **merchant family**, not a row (§2.2). For
each family in `M` — keyed by `normalise_text(merchant_name(description))`, the
same grouping `RecurringService` uses — compute

```
excess(f) = spend_in_M(f) − mean(spend_in_each_baseline_window(f))
```

The candidate is the family with the greatest `excess`. The clause renders only
when *all* hold:

- the verdict is `HIGHER`. A single large *expense* cannot explain spending
  *less*, and the transaction that would explain a `LOWER` month is the one that
  is absent — unobservable by construction. INV-8 pins it.
- a candidate family exists with `excess > 0`.
- `_CAUSE_DEN * excess >= _CAUSE_NUM * movement`.

`MonthCause` carries the family's **excess** (the quantity the gate tested and
the quantity slot 3 removes) alongside the family's total spend in `M` and its
display name. Ties resolve to the lexicographically smaller `merchant_key`, so
the sentence is stable across refreshes.

Re-run against §2.2's vault: rent's `excess` is `7000 − 7000 = 0`, so it is not a
candidate at all; against §2.1's, the vet family's `excess` is `1900 − 0 = 1900`,
which clears `0.6 × 2340 = 1404`. The rule selects the right object in both.

**Slot 3 — correction.** Rendered only when slot 2 rendered *and*
`residual = movement − excess` is non-zero. The template is chosen by the **sign
of `residual`** (§2.1).

**The templates.** These are the feature's actual deliverable; `MonthSummaryStrip`
owns them and calls `tr()` on each. Named placeholders per `coding.md`.
`{month}` is `QLocale().standaloneMonthName(m)`, plus the year when it differs
from `today`'s.

| Slot | State | Template |
|---|---|---|
| 1 | `HIGHER`, complete | `"{month} cost you {amount} more than your usual month."` |
| 1 | `HIGHER`, partial | `"So far, {month} has cost you {amount} more than usual by this point."` |
| 1 | `LOWER`, complete | `"{month} cost you {amount} less than your usual month."` |
| 1 | `LOWER`, partial | `"So far, {month} has cost you {amount} less than usual by this point."` |
| 1 | `NORMAL`, complete | `"{month} looked like a normal month."` |
| 1 | `NORMAL`, partial | `"So far, {month} looks like a normal month."` |
| 2 | any | `"Most of it was one thing — {name}, {amount} more than usual."` |
| 3 | `residual < 0` | `"Take that out and you were {amount} better than normal."` |
| 3 | `residual > 0` | `"Even without it you were {amount} above normal."` |

Slot 3 is omitted when `residual == 0` — it would say "and then you were exactly
normal". Slot 2 says **"most of it"**, not "almost all of it": at the 60%
threshold the clause must still be true, and 60% is a majority rather than almost
all. The constant and the wording are chosen together and move together.

No template needs Qt's `%n` numerus form — every one interpolates an amount or a
name, never a count.

`MonthCause.name` is raw bank text (§6.3), so the label sets
`Qt.TextFormat.PlainText` — a description containing `<b>` or `<img src=…>` would
otherwise be rendered as rich text by `QLabel`'s default `AutoText` sniffing,
showing something other than the user's transaction and attempting a local
resource load. The label word-wraps and elides `name` to 40 characters so a long
description cannot force the dashboard's minimum width.

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
    name: str                  # display name; raw bank text
    excess_minor: int          # positive; spend in M minus the family's baseline mean
    spend_minor: int           # positive; the family's total spend in M

@dataclass(frozen=True)
class MonthSummary:
    month: str                 # "YYYY-MM"
    partial: bool
    days: int                  # the §4.4 common day count, both states
    exponent: int              # so the strip can format without a vault handle
    verdict: MonthVerdict
    spend_minor: int           # positive magnitude
    baseline_minor: int        # positive magnitude
    movement_minor: int        # signed
    cause: MonthCause | None
    residual_minor: int | None # signed; None iff cause is None

# --- services/month_summary.py ---------------------------------------------
@dataclass(frozen=True)
class MonthSummaryInput:
    month: str
    partial: bool
    days: int
    spend_minor: int
    prior_minor: tuple[int, ...]        # one per baseline month WITH data
    prior_months_with_data: int         # how many of _BASELINE_MONTHS had any row
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
```

**`MonthSummaryService.summary` owns the §3 decision 1 mode allow-list** and
returns `None` for any other mode, so INV-4 is testable without Qt and
`HomeView` does nothing but hide the strip on `None`. `today` is required, not
defaulted — unlike `ReportingService`, whose `today: date | None = None` predates
this contract.

`summarise_month` takes no clock: `partial`, `days` and `started` are everything
it needs from it, and the service computes them. `exponent` is carried on
`MonthSummary` so the strip can call `to_display_decimal` without a vault handle
— `read_minor_unit_exponent` is **not** imported in `home.py` today
(`grep -n read_minor_unit_exponent src/finbreak/ui/home.py` returns nothing), so
without this field the strip could not format anything.

`days` is defined in both states (§4.4), never sentinel.

### 4.8 The silence ladder

`summarise_month` returns `None` — the strip hides entirely — when any holds, in
this order:

1. `prior_months_with_data < _BASELINE_MONTHS`. "Your usual month" is a claim
   about three months. **A baseline month with no non-transfer rows at all is
   missing data, not a zero-spend month**, and the service is what knows the
   difference: it omits such months from `prior_minor` and reports the count
   separately, because a tuple of totals cannot distinguish "no rows" from "rows
   summing to zero". A month holding only income rows counts as *having data*
   and contributes a genuine `0` — it is a real zero-spend month, not a gap.
2. `baseline < minor(_MIN_MONTH_BASELINE_MAJOR)`. Too little money moving to
   characterise.
3. `partial and days < _MIN_ELAPSED_DAYS`. Six days pro-rated against six days is
   arithmetically fine and epistemically worthless — one grocery run swings it
   past every threshold. The comparison is `<`, so the strip first speaks on the
   7th.
4. `not started` — `M`'s first day is after `today` (§4.3).
5. `spend == 0` **and** `M` contributed no non-transfer rows at all. An
   un-imported month between two imported ones would otherwise report the most
   reassuring possible sentence out of absent data, exactly as a future month
   would. A month that genuinely had rows and zero spend is not silenced.

The strip is also absent, without consulting the detector, when `HomeView` is
showing its getting-started page (`transaction_count() == 0`, FIBR-0012 INV-7).

### 4.9 Wiring

`HomeView.__init__` gains a `month_summary: MonthSummaryService` parameter.
`main_window._build_workspace` constructs it alongside the other five services.

**The parameter is added last, before `amount_prefs`, and `amount_prefs` must
stay keyword-passed** — `home.py` already carries a standing comment that a
positional `amount_prefs` binds to `recurring`; a sixth service parameter widens
that trap rather than creating it.

`HomeView.refresh()` calls the service and passes the result to the strip, at the
point where `_render_net` is called today.

**Error handling — stated correctly, because an earlier draft stated it wrongly.**
`HomeView.refresh()` has **8** call sites, of which **6 are unguarded**:

| Site | Guarded by `except VaultLockedError` |
|---|---|
| `home.py:117` (`__init__`) | no |
| `home.py:328` (`_on_period_changed`) | yes |
| `home.py:336` (`_on_account_changed`) | yes |
| `home.py:352` (`set_amount_prefs`) | no |
| `main_window.py:797` (`_refresh_tab`) | no |
| `main_window.py:828` (`_show_home`) | no |
| `main_window.py:1497` (`_on_import_done`) | no |
| `main_window.py:1506` (`_refresh_after_statement_change`) | no |

(`grep -n "refresh()" src/finbreak/ui/home.py src/finbreak/ui/main_window.py`,
2026-08-05.)

The exposure is **pre-existing and unchanged by this item**: `refresh()` already
issues `transaction_count()`, `base_currency()` and `summary()` against the vault
before this feature adds a fourth read, so every one of those six sites can
already raise `VaultLockedError` today. This spec therefore adds no new failure
mode — which is a different and weaker claim than "both slots are guarded", and
it is the true one. INV-13 pins the weaker claim and tests one `main_window` path
as well as the two guarded slots.

## 5. Invariants

- **INV-1** — integer-only arithmetic. No `Decimal` or `float` appears in
  `services/month_summary.py`, and no true division is performed on money.
  *Breaks when:* a percentage is computed as `movement / baseline` instead of by
  cross-multiplication — which silently returns a `float` and defeats the whole
  minor-unit discipline.
  *Test:* two legs, because a grep alone cannot see the stated breach —
  `movement / baseline` contains neither `Decimal` nor `float(`. (a) every
  numeric field of a returned `MonthSummary` satisfies `type(v) is int`;
  (b) `grep -nE "\bDecimal\(|\bfloat\(" src/finbreak/services/month_summary.py`
  returns nothing.
  **Leg (a) is the catcher; leg (b) is a cheap tripwire with two stated
  limits**, both measured 2026-08-05 rather than assumed. It matches the
  *constructor* form deliberately: the bare-word pattern `\bDecimal\b` also
  matches the word "Decimal" in a module docstring, and this module's docstring
  will say why it holds no `Decimal` — so the bare-word leg goes red on correct
  code. In exchange, leg (b) does **not** see `from decimal import Decimal` or a
  bare `x: Decimal` annotation. Neither reaches a wrong figure on its own, and
  leg (a) plus the gate's `mypy` stage catch what does.

- **INV-2** — confirmed transfers are excluded from every figure. From `M`'s
  spend, from every baseline month's spend, and from the cause candidate set.
  *Breaks when:* a transfer between two of the user's own accounts is counted as
  spending, which would make every month with a transfer look expensive.
  *Test:* a vault with one confirmed transfer pair produces the identical
  `MonthSummary` to the same vault with those two rows deleted.

- **INV-3** — every window shares one day count. `M`'s window and every baseline
  window run from day 1 to the same `days` (§4.4), in both the partial and the
  complete state.
  *Breaks when:* only the partial branch truncates — then a uniform-spend February
  reads 8.70% below baseline against a 10% gate, every year, on the default
  period mode.
  *Test:* with identical daily spend in every month and `M` = February,
  `movement_minor == 0`; the same fixture against full-month windows yields a
  strongly negative movement. Plus a leg asserting `days == 28` when a February
  is among the four windows.

- **INV-4** — the strip is absent for every mode outside the three month modes.
  `MODE_YEAR_TO_DATE`, `MODE_SPECIFIC_YEAR` and any unrecognised token all yield
  `None` from `MonthSummaryService.summary`, which is where the allow-list lives.
  *Breaks when:* a deny-list check ("not a year mode") lets year-to-date or a
  garbage mode through, summarising a 7-month window as though it were a month.
  *Test:* `summary()` returns `None` for both year modes and for the token
  `"nonsense"`, and non-`None` for all three month modes, against one seeded
  vault.

- **INV-5** — insufficient or absent data yields `None`, never a guess. Each of
  §4.8's five conditions independently returns `None`.
  *Breaks when:* a vault two months old produces "your usual month"; or a future
  month, or an un-imported gap month, reports that the user spent much less than
  usual.
  *Test:* one leg per §4.8 condition asserting `summarise_month(...) is None`,
  and each with the blocking condition relaxed to assert a non-`None` result — so
  no leg can pass against a detector that returns `None` unconditionally.

- **INV-6** — `NORMAL` unless both materiality gates pass. A movement clearing
  only the relative gate, or only the absolute one, yields `NORMAL`.
  *Breaks when:* one gate is dropped, and the strip starts announcing R30
  movements as news.
  *Test:* four legs — neither gate, relative only, absolute only, both —
  asserting `NORMAL, NORMAL, NORMAL, HIGHER`. Each fixture must clear §4.8 first,
  or the leg tests the silence ladder instead.

- **INV-7** — a cause is a family's **excess**, never a raw row. The candidate is
  the merchant family with the greatest `spend_in_M − baseline_mean`, and the
  gate tests that excess.
  *Breaks when:* the largest single row is nominated instead — then a recurring
  rent payment present in every baseline month is named as the cause of a
  movement it did not contribute to, and slot 3 removes it from one side of a
  comparison whose other side still contains it. §2.2 works the case.
  *Test:* the §2.2 vault — R7,000 rent in all four months, living costs up
  R1,500 — yields `cause is None`, because rent's excess is 0 and living's
  R1,500 excess does not clear `0.6 × 1500`. And the §2.1 vault — a R1,900 vet
  charge with no vet spend in any baseline month, movement R2,340 — yields
  `cause.excess_minor == 190000`.

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
  materiality gates or they test nothing. With `baseline_minor = 1_000_000`
  (R10,000): `spend_minor = 1_234_000` → `movement_minor = 234_000`, cause excess
  `190_000` → `residual_minor == 44_000` (positive → "even without it"). With
  `spend_minor = 1_146_000` → `movement_minor = 146_000`, cause excess `190_000`
  → `residual_minor == -44_000` (negative → "better than normal"). The two must
  select different templates.

- **INV-10** — the strip's spend agrees with the tile below it. For a **complete**
  `M` whose `days` equals `len(M)`, and the same `account_ids`,
  `spend_minor == to_minor(ReportingService.summary(...).expenditure, exponent)`.
  *Breaks when:* §4.5's independent definition of expenditure drifts from
  `summary`'s, and the sentence describes a different number than the figure
  directly beneath it — the on-screen contradiction §3 decision 4 exists to
  prevent.
  *Test:* seed a vault whose `M` is a complete 31-day month with 31-day baseline
  months (so `days == len(M)` and no truncation applies), then assert
  `summary.spend_minor == to_minor(ReportingService(vault).summary(prefs,
  account_ids, today).expenditure, exponent)` for the same `prefs` and
  `account_ids`. Include one `amount_minor == 0` row — the only value the two
  definitions bucket differently — so the leg goes red if either side changes how
  it treats it.
  *Scope, stated so the leg is not read as covering more:* the equality is
  asserted only for a complete `M` with no short month in its baseline. For a
  partial `M` the two legitimately differ — `resolve_period` gives the tile the
  **full** month bounds while §4.4 stops the strip at `days` — and a future-dated
  row makes them differ even on the last day of the month. §6 records both.

- **INV-11** — the summary is scoped to the same accounts as the tiles. The strip
  and `ReportingService.summary` receive the identical `account_ids`.
  *Breaks when:* selecting one account leaves a whole-vault sentence above
  single-account tiles.
  *Test:* with two accounts, `spend_minor` for a single-account selection equals
  that account's expenditure alone and differs from the "All accounts" value.
  This asserts *scoping*, not numeric equality with the tile — INV-10 owns that,
  under its narrower conditions.

- **INV-12** — the service emits no user-facing string. `MonthSummary` carries an
  enum and integers; the only prose is `MonthCause.name`, the user's own
  transaction text passed through unmodified.
  *Breaks when:* a sentence is assembled in the service, where `tr()` is
  unavailable, silently making the feature untranslatable.
  *Test:* `grep -nE "\.tr\(|QCoreApplication" src/finbreak/services/month_summary.py`
  returns nothing — anchored on `.tr(` because the **unanchored** `tr(` an
  earlier draft specified also matches `str(`, which the module uses to build
  `"YYYY-MM"` (measured 2026-08-05: `grep -n "tr(\|QCoreApplication"` hits
  `label = str(month)`). Plus: the strip renders a full
  three-sentence summary from a hand-constructed `MonthSummary` with no service
  involved.

- **INV-13** — a mid-render lock adds no failure mode. The summary read raises no
  exception type `refresh()`'s existing vault reads do not already raise, and
  `VaultLockedError` propagates to the caller rather than being caught inside the
  service.
  *Breaks when:* the service catches `VaultLockedError` itself and returns a
  partial summary computed from rows it did manage to read — a sentence about a
  fraction of the month, presented as the month.
  *Test:* a stand-in raising `VaultLockedError` from the repository leaves
  `_on_period_changed` returning cleanly and the strip showing its prior content;
  plus one leg through `MainWindow._refresh_tab` (an unguarded site per §4.9)
  asserting the exception surfaces there exactly as it does today without the
  strip.

- **INV-14** — every reachable verdict × state combination has a template. The
  six slot-1 templates of §4.6 are exhaustive over `MonthVerdict × {partial,
  complete}`.
  *Breaks when:* an implementer writes three templates and interpolates "so far"
  ad hoc, or omits the `NORMAL`-partial case, and a mid-month unremarkable month
  renders an empty strip.
  *Test:* a leg iterating all six combinations against a hand-constructed
  `MonthSummary` and asserting each renders a non-empty string, with no two
  combinations producing the same string.

## 6. Failure modes

Stated, not hidden. Each is a consequence the design accepts.

1. **Truncation drops the end of long months when a short one is in the
   baseline.** §4.4: summarising a 31-day March whose baseline includes February
   sets `days = 28`, so 3 of March's days (~9.7% of that month) are excluded from
   every window. Because the exclusion is applied to *all four* windows the
   comparison stays like-for-like, but the figure is no longer the whole month's
   spend, and it will not match the Net tile (INV-10 is scoped around this).
   **The bias is not bounded by day count alone**: month-end debit orders cluster
   on days 28–31, so a single R2,000 insurance debit on the 29th is dropped
   entirely. The direction is toward understating both sides.
2. **A partial month's verdict can flip day to day.** The relative gate scales
   with the window but the absolute gate is a fixed `minor(_MIN_MOVE_MAJOR)`
   regardless of whether `days` is 7 or 28. So the same proportional overspend
   reads `NORMAL` on the 8th and `HIGHER` on the 15th. Accepted rather than
   pro-rated: the constants are full-month figures applied unscaled, and the "so
   far" phrasing is what tells the reader the figure is provisional.
3. **A month whose spending moved for a good reason still reads as a warning.**
   Moving house, a deliberate annual insurance payment, a planned holiday. The
   strip has no notion of intent; the cause clause is the mitigation, since
   naming the family lets the reader dismiss it instantly.
4. **`MonthCause.name` is raw bank text.** It may be cryptic
   ("POS 4455 \*\*\*\*1234"). `merchant_name` cleans it for grouping, and the
   display name is the cleaned form, but cleaning is best-effort. An ugly true
   description beats a tidy wrong one. §4.6 pins `PlainText` and elision so it
   cannot inject markup or break the layout.
5. **Three baseline months is a short memory.** A user with genuinely seasonal
   spending will see December called expensive every year. Accepted: a 12-month
   baseline needs a year of history before the feature works at all.
6. **A split payment still defeats the cause clause** — but less often than a
   per-row rule would. Two R1,000 charges from the *same* merchant now sum into
   one family and can clear the gate; two charges from *different* merchants do
   not. It degrades to the verdict alone, the correct direction.
7. **The strip's window and the Net tile's differ for a partial month.**
   `resolve_period(MODE_CURRENT_MONTH)` returns the full month bounds, so the
   tile counts future-dated rows the strip's `days` window excludes. The
   `partial` flag drives the "so far" phrasing so the two are not read as the
   same number. INV-10 is scoped to complete months for this reason.
8. **The absolute gates go soft for exponent-0 currencies.** `minor(100)` is 100
   for JPY or KRW — well under a dollar — so for such a vault only the relative
   gate binds and the misfire the absolute gate exists to prevent can occur. The
   thresholds are tuned for exponent-2 currencies; `base_currency()` is
   user-settable, so this is reachable rather than hypothetical. Accepted for v1
   and recorded rather than silently carried.

## 7. Tests

New feature directory `tests/features/month_summary/` (`spec.md` + tests), per
`docs/standards/testing.md`. No such directory exists today (`ls tests/features/`).

Four files, because the invariants need three different capabilities and an
earlier draft assigned vault-dependent and Qt-dependent invariants to a hermetic
detector file that could host neither:

- **`test_month_summary.py`** — the detector, hermetic, no vault and no Qt.
  INV-1(a), INV-3, INV-5, INV-6, INV-7, INV-8, INV-9, and the §4.6 tie-break.
- **`test_month_summary_service.py`** — the service against a real vault fixture.
  INV-2, INV-4, INV-10, INV-11, and INV-13's service leg.
- **`test_month_summary_strip.py`** — the strip under `qtbot`, fed
  hand-constructed `MonthSummary` values. INV-12's second leg, INV-14, the three
  slot combinations, both slot-3 templates, `isHidden()` on `None`, and a leg
  feeding a `name` containing `<b>markup</b>` asserting the literal text survives.
- **`test_month_summary_home.py`** — `HomeView`-level, seeded vault. The strip
  appears and hides as the period selector moves across all five modes, and
  INV-13's `MainWindow._refresh_tab` leg.

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
   invention property 1 forbids. A common day count (§4.4) answers the same
   question without asserting anything about days that have not happened.
6. **Put the strip in a dialog, or on its own tab.** Rejected: a feature whose
   entire purpose is to save the reader effort cannot be behind a click.
7. **Let the strip speak for year modes with year-over-year phrasing.** Rejected
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

## 10. Resource cost

Four repository reads are added per `HomeView.refresh()`: one
`drill_rows_in_range` over `M`'s window (descriptions are needed for the merchant
grouping) and three `rows_in_range` over the baseline windows. Both are indexed
range scans over `occurred_on`, the same shape `summary`, `monthly_trend` and
`drill_down` already issue — five existing call sites in `services/`, four
`rows_in_range` and one `drill_rows_in_range`
(`grep -rn "rows_in_range" src/finbreak/services/ | wc -l` → 5, of which
`grep -rn "drill_rows_in_range(" src/finbreak/services/ | wc -l` → 1; the plain
grep matches both names, which is why the split is stated rather than the bare
total).

The merchant grouping adds a `normalise_text(merchant_name(...))` per row of `M`
only — the baseline windows need per-family sums too, so the three baseline reads
also become `drill_rows_in_range`. That is the one cost §2.2's fix adds over the
per-row design: descriptions for four windows rather than one.

No timing figure is stated here, because none has been measured — per the
authoring rule that a number arrives with the command that produced it. If the
added reads prove material, the three baseline months are exactly the months
`monthly_trend` already fetches and the two could share one query. That is
deliberately **not** done in v1, because the sharing would couple the strip's
window arithmetic to the trend chart's, and §4.4's common day count makes those
windows differ whenever a short month is involved.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_month_summary.py` — leg (a), the `type(v) is int` assertion; the grep is leg (b) |
| INV-2 | `test_month_summary_service.py` |
| INV-3 | `test_month_summary.py` (uniform-spend February) |
| INV-4 | `test_month_summary_service.py` |
| INV-5 | `test_month_summary.py` (five conditions × relaxed counterpart) |
| INV-6 | `test_month_summary.py` (four-leg gate matrix) |
| INV-7 | `test_month_summary.py` (the §2.2 rent vault and the §2.1 vet vault) |
| INV-8 | `test_month_summary.py` |
| INV-9 | `test_month_summary.py` + the strip's two-template leg |
| INV-10 | `test_month_summary_service.py` |
| INV-11 | `test_month_summary_service.py` |
| INV-12 | grep leg + the strip test's hand-constructed `MonthSummary` |
| INV-13 | `test_month_summary_service.py` + `test_month_summary_home.py` |
| INV-14 | `test_month_summary_strip.py` (six-combination matrix) |
| §4.6's tie-break (equal excesses resolve to the smaller `merchant_key`) | `test_month_summary.py` — a two-equal-families fixture asserted on `cause.merchant_key` |
| §4.6's `PlainText` and elision | `test_month_summary_strip.py` — the `<b>markup</b>` leg covers `PlainText`; **nothing** covers elision, which is a layout property no assertion in this suite reads |
| §4.5/§4.6's specific threshold *values* (10%, 100, 50, 60%, 7 days) | **nothing** — the tests assert behaviour either side of each constant by reading it, so changing a constant moves the test with it. Deliberate: these are tuning values, not contract. What is pinned is that *both* materiality gates exist (INV-6), that the cause gate tests an excess (INV-7), and that each silence condition fires (INV-5) |
| §6.1's truncation bias staying tolerable | **nothing** — no leg asserts a bound, and unlike the earlier draft this spec does not claim one. The bias is not bounded by day count, because month-end debits cluster in exactly the dropped days |
| §6.2's day-to-day verdict instability | **nothing** — no leg drives the same vault across successive `today` values |
| Whether the sentence is *useful* — that a real user reads it and understands their month | **nothing**, and nothing can. This is the honest limit of the feature: the tests pin that the arithmetic is right and the phrasing is selected correctly, not that the result communicates |
| §4.2's decision to keep `_BASELINE_MONTHS` and `_MIN_MONTH_BASELINE_MAJOR` separate from `alerts.py`'s | **nothing** — a future edit could import either and every test would stay green. The distinct *name* of the floor is the only mechanical defence; the rationale is recorded in §4.2 and the constants' own comments |
| §6.8's exponent-0 degradation | **nothing** — no leg runs a zero-exponent vault |

Twenty rows, **seven** with a bolded `nothing`: elision, the threshold values,
the truncation bias, the verdict instability, whether the sentence communicates,
the constant-independence decision, and the exponent-0 degradation.

Two of those seven are closable and are not being closed in v1 — an elision leg
and a zero-exponent-vault leg are both writable. Two more are design limits this
spec states rather than tests it declined to write (the unbounded truncation
bias, the accepted instability). The remaining three are honest limits: tuning
values that are deliberately not contract, a design decision no test can defend,
and the fact that no automated check can tell whether prose helps a human.

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
| 1 | 2026-08-05 | 3, strong, cold, shared byte-identical packet (dims: 5×9, 15×6, 6×6, 4×5, 13×4, 2×4, 10×4, 1×3, 7×2, 12×1) | 3 | 6 | 12 | 8 | 29 verified, 1 unverified. All fixed. **The CRITICAL rewrote the design's core rule, and it was the same defect §2.1 was written to prevent, one layer deeper.** All three lanes independently constructed the case: the cause clause selected *the largest single expenditure row* in the month and gated it only from below (≥60% of the movement), so on an ordinary vault the largest row is rent — present identically in every baseline month, explaining nothing. Executed against this spec's own constants: baseline R12,000, spend R13,500, movement +R1,500 → HIGHER; rent R7,000 clears the gate by **7.8×**; residual −R5,500 selects the *reassuring* template. Emitted: "Most of it was one thing — a R7,000 rent payment. Take that out and you were R5,500 better than normal", on a month that was R1,500 over. INV-8 (now INV-9) stayed green throughout, because it pins the sentence's *grammar* and the evidence was never required to be evidence. Fixing the gate alone was insufficient — in that vault the vet bill of §2.1 would not even be *selected*, rent being larger — so the unit changed from a row to a **merchant family** and the quantity from magnitude to **excess over that family's own baseline**, reusing `RecurringService`'s `merchant_key`. New §2.2 works the case; INV-7 pins both vaults. Second CRITICAL, all three lanes: **the feature's actual deliverable was absent** — only slot 3's two templates were specified, so the verdict (×3 verdicts ×2 states) and cause strings, and the "so far" phrasing §6 relied on as its whole mitigation, existed nowhere; §7 asked for tests against them. A nine-row template table now lives in §4.6 and INV-14 pins exhaustiveness. Third, lanes B and C: **`M` itself was never guarded** — only the baseline was. `home.py:255` is `setRange(1970, 9999)`, so a future month is two clicks away, and with three months of prior data `movement = −baseline` clears both gates by construction, announcing that a month which has not happened was much cheaper than usual; an un-imported gap month does the same. §4.8 gained conditions 4 and 5. HIGHs: §4.9 claimed "both slots that reach `refresh()`" and carried a **verified** stamp — measured, there are **8** call sites and **6** are unguarded (`home.py:117,352`, `main_window.py:797,828,1497,1506`), so the sentence is replaced by the inventory and the claim narrowed to the true, weaker one (the exposure is pre-existing; the read adds no new type); the complete-month branch was **not** truncated, leaving a uniform-spend February at **−8.70%** against a 10% gate on the *default* period mode, three times the partial bias the doc did record — the two branches collapse into one common-day-count rule (INV-3); §4.8 condition 1 was **inexpressible** through `MonthSummaryInput`, a tuple of totals being unable to distinguish "no rows" from "rows summing to zero", now `prior_months_with_data` with the income-only case ruled on explicitly; INV-9's worked values were **major units in `_minor` fields** — `movement=2340` at exponent 2 is R23.40, below `minor(100)`, so the verdict is NORMAL, cause None, and the leg asserts `440` against `None` — restated with a baseline so both fixtures clear the gates; INV-1's grep could not see its own stated breach (`movement / baseline` contains neither token), now a `type(v) is int` assertion with the grep demoted to leg (b); §7 assigned vault- and Qt-dependent invariants to a hermetic detector file, and INV-4 to a strip file with no `HomeView` — four files now, split by capability. MEDIUMs fixed: `_MIN_BASELINE_MAJOR` collided with `alerts.py` on **name and value** while §4.2 argued only against the *other* import — renamed `_MIN_MONTH_BASELINE_MAJOR` and the rationale extended to both; the strip could not format anything, `read_minor_unit_exponent` not being imported in `home.py`, so `exponent` moved onto `MonthSummary`; `MonthSummaryService`'s signature was never given and the mode gate had no stated home — both now in §4.7, the allow-list inside `summary()` so INV-4 is testable without Qt; the output dataclasses moved to `models.py`, where all 30+ cross-layer shapes and every `StrEnum` already live; `QLabel`'s default `AutoText` would render `<b>`/`<img>` in raw bank text — `PlainText` + elision pinned; §4.5's "6 call sites" counted a `def` and a docstring (4 real); §7's ripple list was 2-of-5 with a false `app_shell/` entry; the partial-month verdict instability, the tile/strip window divergence, and the zero-amount-row bucketing became §6 entries and INV-10. LOWs: §1 property 1 contradicted slot 1 always rendering; `floor()` renamed `minor()`; `elapsed_days` undefined when complete (now `days`, defined in both states); the allow-list-vs-deny-list ambiguity for an unrecognised mode; 60% cannot be called "almost all" (template says "most of it"); exponent-0 currencies; the `today.day` off-by-one and its comment. **One finding dismissed as unverified:** two lanes reported a dangling "§13" reference — an artefact of the orchestrator's own scrubbed packet, which replaced `## 13. Cold-eyes loop log` with an unnumbered heading. The real document was always correct; the scrubber was fixed for loop 2. **Every prescribed grep was executed before landing (4b-x), and two of the fixes were wrong.** (i) The replacement INV-1 leg `\bDecimal\b|\bfloat\(` **fired on correct code** — `\b` matches the word "Decimal" in the module's own docstring, which will say why the module holds none; narrowed to the constructor form `\bDecimal\(|\bfloat\(`, whose two blind spots (a bare import, a bare annotation) are now stated with leg (a) named as the real catcher. (ii) The justification written for INV-12's anchor was false: `\btr\(` does **not** match `str(` — the word boundary fails against the preceding `s`. The lanes' claim was about the *unanchored* `tr(` the earlier draft specified, which does match (`label = str(month)`); the sentence now cites the pattern that actually misfires. Both corrections came from running the greps, not from reading them. 4c then caught one more piece of this loop's own collateral before the commit: the rewrite left **INV-10 with no `*Test:*` clause at all** (a `*Scope:*` clause had displaced it), which `spec_lint` reported as `invariant_no_test` — added, with the `amount_minor == 0` row that is the only value the two expenditure definitions bucket differently. INV count 12 → 14; §11 18 rows / 5 `nothing`s → 20 / 7; 603 → 922 lines. Not converged — loop 2 owed. |
