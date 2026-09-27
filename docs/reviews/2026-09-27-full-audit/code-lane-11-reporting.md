## Lane 11: reporting, month summary, forecast, recurring, alerts, categorisation, category library

**Subject files, line counts as read** (all under `/mnt/Games/Scripts/Linux/finbreak/src/finbreak/`):
- `services/reporting.py` 545
- `services/month_summary.py` 381
- `services/forecast.py` 258
- `services/recurring.py` 317
- `services/alerts.py` 283
- `services/categorization.py` 399
- `category_library.py` 144

**Already in my context when I arrived:** `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, the finbreak `CLAUDE.md` (which includes the module map), the finbreak `MEMORY.md` index, and a git snapshot (clean `main` at `52e5162`, recent FIBR-0331 commits). All of that is project context, and I list it here as the brief asks.

**Contract actually read:**
- FIBR-0231 §3–§6 in full.
- FIBR-0142: at-a-glance invariants, Design decisions, New symbols.
- FIBR-0139: at-a-glance invariants, Design decisions, New-symbols table.
- FIBR-0143: at-a-glance invariants.
- FIBR-0154 §5.
- FIBR-0123: at-a-glance invariants, D1–D5.
- FIBR-0177 §1 and D1–D5.
- FIBR-0219, FIBR-0192 and ADR-0008: outline only (see Info).

**Tools:** one `workspace_search` was rate-limited, so I used `Grep` for that search and one other. No test file was opened or searched.

## Critical (0)

## High (0)

## Medium (2)

- **[dim 2] `services/forecast.py:254` — `anchor=item.last_seen,`** — the docstring at `:93-96` is wrong: *"for a clamped one it is the true month-end."*
  - That only holds when `last_seen` fell in a 31-day month. When it fell in Feb/Apr/Jun/Sep/Nov, the bank itself already clamped it (a debit order meant for the 31st lands on Feb 28 or Apr 30).
  - `_add_cadence_n(date(…,2,28), MONTHLY, n)` then yields Mar 28, Apr 28, May 28… for the whole projection. That is exactly the ratchet `recurring.py:98-104` and `forecast.py:79-91` say this design avoids.
  - This affects 5 of 12 months for every month-end debit order. The docstring itself admits the wrong dates move the projected end balance at a horizon boundary.
  - `next_expected` (`recurring.py:218`, used by missed-debit alerts) has the same flaw, but the 3-day grace absorbs it.
  - Fix: carry the group's intended day of month (the maximum `.day` across member dates) on `RecurringItem`, and clamp `min(intended_day, month length)` per step, instead of taking the day from `last_seen`.

- **[dim 4] `services/alerts.py:279` — `prior_minor=tuple(totals[ym].get(cid, 0) for ym in priors),`** — two copies of the "3-prior-month round-half-up baseline" have diverged on missing data.
  - `month_summary.py:279-283` treats a baseline month with no spend rows as a gap and stays silent (FIBR-0231 §4.8 condition 1: "missing data, not a zero-spend month").
  - `alerts.py` feeds a missing month in as `0`. So a vault with only two imported months gives average = X/3, and every category with `current ≥ 2X/3` (and average ≥ R50) fires a "spike".
  - That is the false-positive shape FIBR-0231 worked through and rejected.
  - The "Empty `prior_minor` ⇒ no alert" guard at `:121` can never fire, because `_spike_inputs` always builds three entries.
  - Uncertain: FIBR-0172 (the alerts spec) was not in my packet, so I cannot tell whether zero-filling is specified there. Fix, if not: apply the same has-data rule — skip a category/window whose month held no spend rows vault-wide.

## Low / Info

- **[dim 2] `services/reporting.py:397-399` — `if cat is None or cat.parent_id is None: return category_id`.** A row whose `category_id` is a Type root makes `category_node(root)` include every non-empty Level-2 subtree of that root. Those subtrees are also emitted as their own top items at `:468`, so they are counted twice and the branch total exceeds the tile.
  - That breaks INV-1, which the docstring (`:395-396`) claims holds "even on data the write path rejects."
  - Reachable only through corrupt or restored data: `_require_leaf` and `_validate` block the write paths.
  - Fix: treat a root id like `None`, or place root-assigned rows as merchant nodes directly under the branch.

- **[dim 13] `services/reporting.py:533` — `f"{from_account} → {to_account}",`** — a display label built with an f-string in the service. The design.md §i18n commitment forbids concatenated display strings and asks for RTL-agnostic layout. A fixed `→` does not mirror, and this bypasses the `DrillLabels` injection the same method already uses.
  - Fix: add a `tr()`-ed `"{from} → {to}"` template to `DrillLabels`.

- **[dim 13] `services/reporting.py:183, 217, 267, 319` — `today = today or date.today()  # noqa: DTZ011`.** These fallbacks read the naive OS clock, the FIBR-0342 wrong-month trap.
  - My search found no live path: every src caller passes the app-clock `today` (`home.py:402`, `export_dialog.py:112`, `ui/forecast.py:169`, `ui/recurring.py:145`, `alerts_dialog.py:99`). The one indirect caller, `pdf_export.py`, has its own `date.today()` fallback at `:131`, outside my lane.
  - The risk is latent: a future caller that omits `today` gets it silently.
  - Fix: make `today` required, as `MonthSummaryService.summary` already does (FIBR-0231 §4.7).

- **[dim 2, document is wrong] `services/categorization.py:91-139, 168-185` against FIBR-0139 D2/D5 and the New-symbols table.**
  - The spec says `_match_inputs` returns `(list[CategorizationRule], list[LibraryEntry], …)` and duplicate names resolve first-wins by `list_all()`.
  - The code returns folded tuples (FIBR-0213) and breaks duplicate names by the seed root. It cites an "INV-6a" that FIBR-0139 does not define (grep: the only INV-6a hits are in FIBR-0050/0051/0052/0033).
  - The code looks intentional; FIBR-0139 is stale. This is for `review-contract`.

- **Info — ReDoS check (the external-spec item):** not applicable. User rules and library patterns are matched as plain substrings (`categorization.py:75-77`, `category_library.py:139-140`). No `re` call on a user-authored pattern exists in these modules.

- **Info — specs I did not read past the outline:** FIBR-0219 (locale amount parsing), FIBR-0192 (column state) and ADR-0008 (QtCharts). None of my seven modules implements them as far as I can see (`to_minor` lives in `services/transactions.py`), so I did not open them. This is a gap in my coverage, not a finding.

- **One line per remaining dimension:**
  - dim 3: nothing else found. No logging of transaction content; `category_library` logs only the file path.
  - dim 5: nothing found that is a bug. `snapshot` runs several times per refresh, which is slower, not wrong.
  - dim 7: the library load and parse swallows are the INV-8 contract; nothing else found.
  - dim 8: N/A, no threading here.
  - dim 9: rule swap and apply use `owned_transaction`; nothing found.
  - dim 10: nothing found against design.md § Observability.
  - dim 11: nothing found.
  - dim 12: N/A, no standard named.
  - dim 15: nothing leaves the machine.
  - dim 16: a clock moving backwards only affects activeness filtering; nothing found.
  - dim 17: no schema here. The loss of recurring decisions when `merchant_name` changes is documented in FIBR-0142 D9.

## Covered by spec and looks correct

- **`month_summary.py` against FIBR-0231 §4.2–§4.8 and INV-1–9/12/13:**
  - the allow-list plus the specific-month field check;
  - the future/partial/complete state fields;
  - `head = min(today.day, L_min−1)`;
  - whole-month windows when the month is complete;
  - `drill_rows_in_range` on all four windows;
  - spend-only families;
  - divisor always 3;
  - earliest-row name;
  - sorted-key strict `>` tie-break;
  - the silence-ladder order;
  - cause only on `HIGHER`;
  - the slot-3 floor owned by the detector;
  - no Decimal, float or true division;
  - `VaultLockedError` not caught.
- **`recurring.py` against FIBR-0142 INV-1–9 and D3–D10:** the bands, the integer ±10% test, zero-gap discard, activeness, `ROUND_HALF_EVEN` D8, the D10 sort, and the partition.
- **`forecast.py` `CASH_TYPES`** matches FIBR-0177 D1.
- **`categorization.py`:** `leaf_categories_grouped` matches FIBR-0123 D3/INV-2, and `sub_category_parent_names` matches FIBR-0154 INV-4.
- **`category_library.py`** `parse_library`/`load_library` match FIBR-0139 D8.

## Open questions

1. Does FIBR-0172 specify zero-filling missing prior months for category spikes? This decides whether the alerts Medium is a code defect or a documented choice.
2. Drill leaf labels are raw ISO `occurred_on` strings (`reporting.py:425`, `:527`). I could not check whether the UI re-formats them per locale; the FIBR-0138 spec was not in my packet.
3. Does anything guarantee a transaction can never carry a root `category_id` (a trigger, or restore validation)? I found no trigger in `src/`, so I rated the double-count Low only because the write paths block it.

## 3 items to fix first

1. **Forecast month-end anchor (`forecast.py:254`).** It is the project's most serious bug class, wrong-day money, on the common path of month-end debit orders, and the code's own docstring claims the opposite.
2. **Alerts missing-data baseline (`alerts.py:279`).** Every user with under four months imported sees false spike alerts, and the fix is to reuse the rule FIBR-0231 already reasoned out.
3. **Make `today` required in `ReportingService` (`reporting.py:183` and the other three).** It is cheap and removes the latent path to the known FIBR-0342 wrong-month failure.