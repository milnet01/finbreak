# FIBR-0231 — cold-eyes loop 3 deferred tail

**Status:** verified and **unfixed**. Written 2026-08-06 when the run stopped at
loop 3 on `/cold-eyes`' collateral trigger (see `docs/specs/FIBR-0231-plain-english-month-summary.md`
§13 loop 3 for why it stopped rather than looping again).

> These are verified and unfixed. Do **not** re-review to rediscover them — a
> fresh loop costs a full three-lane dispatch to regenerate what is already
> written here. Fold them in directly.

Three lanes, cold, on the 1203-line loop-2 document. **CRITICAL 2 · HIGH 3 ·
MEDIUM 9 · LOW 9 · INFO 1** (verified 24, unverified 0). Every arithmetic
example in the spec was independently re-checked by two lanes and found correct;
every code claim (line counts, the 8 `refresh()` sites, the 4-vs-6
`confirmed_transfer_txn_ids` split, `recurring.py`'s earliest-row-ties-by-id
convention, `merchant_name`'s two-consumer docstring, §11's `28 11` tally) was
verified accurate. **The defects below are in the rules and the test clauses, not
in the sums.**

Origin: nearly all are collateral from loop 2's own fixes. Finding 1 is the
exception — a draft defect against loop 1's common-day-count rule.

---

## 1. CRITICAL — the common-day-count rule manufactures a false verdict *and* a false cause, annually, on an ordinary vault

**Lane C. §4.4 / §6.1.** §4.4 proves the rule neutral only for **uniform** spend.
§6.1 names the exact non-uniformity that breaks it ("month-end debit orders
cluster on days 28–31") and then mischaracterises the consequence as a symmetric
understatement confined to the tile mismatch. It is neither symmetric nor
confined: a fixed-day-of-month debit occupies a *different day number* in
February than in a 30/31-day month, so truncation includes it on one side of the
comparison and excludes it from the other.

Worked, exponent 2. Rent R7,000 by debit order on the 30th (February: the 28th);
R5,000 of other spend over days 1–20. **Behaviour never changes.**

```
M = February (28d); baselines Nov(30) Dec(31) Jan(31)
days = min(28, 30, 31, 31) = 28
  Nov/Dec/Jan windows [1..28] = R5,000 each   (rent on the 30th — OUTSIDE)
  baseline = 500000
  M window [1..28]        = R12,000           (rent on the 28th — INSIDE)
  movement = +700000
  floor ✓  relative ✓  absolute ✓            -> HIGHER
  Landlord baseline_mean = 0 -> excess = 700000
  cause gate 100x700000 >= 60x700000 ✓ ; residual = 0
```

Renders: *"February cost you R7,000 more than your usual month. All of it and
more was one thing — Landlord, R7,000 more than usual."* **Every clause false.**
It is the exact sentence shape §2.2 exists to eliminate, arriving through a
different door — and §2.2's merchant-family fix does not save it, because §4.7
truncates the family baseline windows too, so the landlord's own baseline reads 0.

The mirror fires next month: M = March(31) with Feb(28) in the baseline sets
`days = 28`, dropping March's day-30 rent while keeping February's day-28 rent →
baseline inflated → *"March cost you R2,333 less than your usual month"* — the
reassuring direction §1 property 3 ranks hardest against. **Both fire every year
for any user with a last-day-of-month debit order.** No test in §7 goes red.

**Fix options:** (a) correct §6.1 — the bias is not symmetric and can invert the
sign of `movement`; (b) add the worked case to §6 with a §11 `nothing` row; or
(c) close it — align windows to month *end* as well as month start, or silence
when a window's dropped tail holds spend. (c) is preferable; this is the
feature's core promise.

## 2. CRITICAL/HIGH — the absolute materiality gate is provably dead, and INV-6's "relative only" leg has no solution

**All three lanes, independently.** §4.8 condition 2 guarantees
`baseline >= minor(1000)` for anything that renders. The relative gate then needs
`abs(movement) >= baseline/10 >= minor(100)` — which *is* the absolute threshold.
So **relative-pass ⟹ absolute-pass, at every exponent**. The absolute gate never
changes an outcome above the floor, and below the floor the strip is silent.

Consequences, all of them in the document:

- **INV-6's "relative only" cell is empty.** The prescribed fixture
  (`baseline == minor(1000)`, `abs(movement)` one unit under `minor(100)`) fails
  the relative gate too: `100 × 9999 = 999900 < 10 × 100000 = 1000000`. So the leg
  duplicates the "neither gate" leg, asserts `NORMAL`, and **passes green against
  an implementation with no relative gate at all**.
- **§11's row names that leg as the sole mechanical defence of the derived
  floor** — so the floor is in fact unchecked.
- **§4.6's "Both, because either alone misfires"** is false: the first hazard is
  handled by condition 2's floor, the second is the relative gate's job.
- **§6.2's day-8/day-15 mechanism is unreachable** for the same reason. The real
  instability is *silence → speech* as the truncated baseline crosses the floor.
- **§6.8 misdiagnoses exponent-0**: "only the relative gate binds" is true at
  every exponent. The genuine degradation is that the *floor* scales too —
  `minor(1000)` is ~US$6.50/month for JPY, so the strip characterises vaults it
  should be silent on.

**Fix:** state plainly that with the derived floor the relative gate binds
everywhere and the absolute gate is belt-and-braces, load-bearing only if the
floor is lowered; reduce INV-6 to three legs (neither / absolute-only / both →
`NORMAL, NORMAL, HIGHER`); replace §11's row with a leg asserting
`_MIN_MONTH_BASELINE_MAJOR == _MIN_MOVE_MAJOR * _MATERIAL_DEN // _MATERIAL_NUM`
computed from the constants; rewrite §4.6's "Both, because…", §6.2 and §6.8.

## 3. HIGH — INV-14's no-signed-amount leg cannot fire against the bug it names

**All three lanes.** `_format_amount` builds `body = f"{sym} {magnitude}"` then
returns `f"-{body}"` / `f"({body})"`. A signed amount renders `-R 500,00` or
`(R 500,00)` — the character after `-`/`(` is the **currency symbol**, never a
digit. The specified assertion ("no `-` or `(` **before a digit**", i.e.
`[-(]\d`) matches neither, and passes against exactly the defect INV-14's
*Breaks when* describes. Compounding: §4.7 says `negative_style` "is not needed
at all" and `set_summary` takes no style, so "run under both `NegativeStyle`
settings" is **unrunnable**.

**Fix:** drop "before a digit" and the two-style sweep. Slot 1/3 templates carry
no hyphen and no parenthesis (the cause clause's dash is an em dash, U+2014), so
assert the rendered string contains neither `-` nor `(` **at all**. Better still,
assert positively: build `expected = _format_amount(to_display_decimal(abs(v),
exponent), symbol)` and assert the slot contains `expected` and neither
`f"-{expected}"` nor `f"({expected})"`.

## 4. HIGH — INV-1's stated breach is caught by neither of its legs

**Lane A.** `if movement / baseline >= 0.10:` keeps the float inside the
comparison — every returned field stays `int`, so leg (a) is green; and leg (b)'s
`\bDecimal\(|\bfloat\(` matches neither `movement / baseline` nor `0.10`. The
invariant's own named failure mode is invisible to both legs, and the sentence
calling leg (a) "the catcher" is wrong for that case.

**Fix:** add a third leg — an AST walk over `ast.parse(source)` for any `ast.Div`
node (cleaner than a `/` grep, which fights docstrings), and retitle leg (a) as
covering *leaked* floats only.

## 5. MEDIUM — "All of it and more" is false at `excess == movement`, which is the spec's own flagship fixture

**All three lanes.** Slot 2 splits at `excess >= movement` while slot 3 splits at
`residual < 0`; §4.6 itself notes those are the same condition — but with the
**strict** inequality. At equality the sentence claims "and more" about a quantity
that is exactly equal. INV-7 leg (a) — the §2.2 vault the whole argument rests on
— lands precisely there (grocer excess R1,500, movement R1,500, `residual == 0`).

**Fix:** three-way split — `<` → "Most of it was one thing"; `==` → "All of it was
one thing"; `>` → "All of it and more was one thing". Slot 2 goes 4 → 6 templates;
INV-14's matrix 16 → 18; update §11's row.

## 6. MEDIUM — the tie-break test is filed where it cannot be written

**All three lanes.** §11 files it in `test_month_summary.py` (hermetic detector),
but `MonthSummaryInput.candidate` is a *single pre-chosen* `MonthCause` — a
"two-equal-families fixture" cannot be expressed at that boundary. §7 states the
rule that settles it ("candidate selection is a service test") and calls the split
"a contract, not a preference". This is the one place loop 2's own correction did
not reach.

**Fix:** move to `test_month_summary_service.py`; fixture = two families with
identical `excess` and no baseline spend, asserting the lexicographically smaller
`merchant_key`.

## 7. MEDIUM — INV-5's condition-4 fixture is vacuous under §4.7's own field values

**Lanes A and B.** The spec catches the `partial` trap and misses its twin: §4.7
prescribes `month_has_rows = False` for a future `M`, so the condition-4 fixture
is blocked by conditions 4 **and** 5 at once, and its relaxed counterpart still
returns `None`. A detector ignoring `started` entirely passes. Lane B adds that
`month_has_rows = False` is itself unverified — no future-date guard exists in
`services/transactions.py` and no `setMaximumDate` on any date editor, so a
post-dated row makes it genuinely `True`.

**Fix:** set `month_has_rows = True` in §4.7's future-`M` list (it is what the
service actually computes) and carry the same vacuity argument the paragraph
already makes for `partial`.

## 8. MEDIUM — INV-9's strip leg is allocated nowhere

**Lanes A, B, C.** §11 cites "the strip's template-selection leg"; §7's strip-file
inventory does not list one, and §7 files INV-9 wholly in the detector file. It
matters: the detector cannot select a template, so a detector-only INV-9 asserts
only that `residual_minor` has the right sign — **a strip that picks the
correction template on the sign of `movement` (§2.1's exact error, the thing this
whole spec is organised around) passes INV-9 as filed.**

**Fix:** add the template-selection leg to §7's `test_month_summary_strip.py`
bullet, fed the two hand-constructed values INV-9 already specifies.

## 9. MEDIUM — `set_summary`'s required `symbol` cannot be supplied from the guard that must hide the strip

**Lanes B and C.** INV-13 requires the two `except VaultLockedError` blocks to
hide the strip, but `symbol` comes from `base_currency()` — itself a vault read
that would raise the same exception. No `symbol` is in scope in the except block.

**Fix:** add `clear() -> None` to `MonthSummaryStrip` (or default `symbol: str =
""` and state it is unread when `summary is None`), and name it in INV-13 and in
§4.9's call-site table.

## 10. MEDIUM — hide the strip at the *top* of `refresh()`, closing all eight paths

**Lanes A and B.** §4.9's "the exposure is pre-existing and unchanged" is true of
the *exception* and false of the *harm*: before this item the residue was a stale
figure; after it, six unguarded paths leave a stale **sentence** naming a month,
which INV-13 itself ranks as strictly worse. The mitigation is one line and closes
all eight sites.

**Fix:** `refresh()`'s first statement clears the strip, before
`transaction_count()`. Restate §4.9 and extend INV-13 leg (b) to an unguarded path.

## 11. MEDIUM — an income-only baseline month is admitted as real data

**Lane C.** §4.8 condition 1 says a month holding only income rows "counts as
*having data* … a real zero-spend month, not a gap". In a personal-finance vault
that shape is, in practice, always a partial import (salary account imported, card
account not). Worked: baselines Dec R12,000, Jan R12,000, Nov income-only →
`baseline = R8,000`; unchanged R12,000 spend → `movement = +R4,000` → `HIGHER`,
and every family's mean is deflated by a third so the 60% cause gate becomes easy.
Unlike §6.9's other cases this one is **cheaply closable**.

**Fix:** make the has-data test "held ≥ 1 non-transfer **spend** row
(`amount_minor < 0`) in its window", for both `prior_minor` and `month_has_rows`.

## 12. MEDIUM — INV-10's zero-row clause is vacuous and contradicts §4.5

**Lane A.** A zero-amount row contributes `0` under §4.5's rule and `-0 == 0`
under `summary`'s `else:` branch. No implementation change can move either total,
so the leg cannot go red — while §4.5 already says the two agree.

**Fix:** keep the row but replace the rationale (it *documents* the agreement), or
assert instead that adding a zero row leaves `spend_minor` unchanged, which is at
least a live check on `summary` changing to `amount_minor >= 0`.

## 13. LOW — nine smaller items

1. **§4.1 ranking wrong.** `home.py` is the **third**-largest UI module, not the
   second: `main_window.py` 1785, `import_wizard.py` 1058, `home.py` 615
   (measured by lane B, 2026-08-06). The line count is right; the ranking is not.
2. **INV-12's grep rationale refutes itself.** It demonstrates that `\btr\(` does
   **not** match `str(` and then concludes `\b` "is not the fix". Both anchors
   work; `\.tr\(` is additionally *weaker* (misses a bare `tr("…")` call).
   Prefer `\btr\(|QCoreApplication` and rewrite the parenthetical.
3. **§4.4 overstates its own example.** 8.70% does not clear the 10% relative
   gate, so the two-rule design renders `NORMAL` — no narrative, invented or
   otherwise. It is a standing *bias* (enough to tip a genuine −1.5% month to
   `LOWER`), not an invented narrative.
4. **`today` is unspecified at the call site.** `MonthSummaryService.summary`
   requires it; `refresh()` should compute `date.today()` **once** and pass it, or
   the strip and the tile can straddle midnight — which INV-10's equality rests on.
5. **Family membership for positive rows undefined.** §4.5 defines *spend* over
   `amount_minor < 0` but never says whether positive rows are family *members*,
   which changes which row is "earliest" and so changes `MonthCause.name`. Also:
   `recurring.py:184` groups by `(direction, key)`, not `key` alone, so "the same
   grouping `RecurringService` uses" is approximate.
6. **§4.8 and §6.9 duplicate ~6 lines** of the partly-imported argument, same
   example figure and same FIBR-0038 pointer — and already differ in one detail.
   Keep §6.9, cut §4.8 to a pointer.
7. **Elision unspecified.** "elides `name` to 40 characters" names neither
   mechanism nor ellipsis; Qt's idiom is `QFontMetrics.elidedText` in *pixels*.
   State plain truncation with a trailing `…` if that is what is meant.
8. **Sentence joining unspecified.** Nothing says the three slots join with a
   space into one wrapping `QLabel` (the `forecast.py` precedent) versus three
   labels. INV-13's and INV-14's assertions both read the answer.
9. **INV-14's "no two produce the same string" can go red** against a correct
   build: the slot-2 `excess >= movement` cell and the slot-3 `residual < 0` cell
   are the same branch. Pin the disambiguating construction (`residual == 0` for
   the slot-2 cells) and say the sixteen are `6+4+4+2` union cells, not a product.

## 14. INFO — the last calendar day of a month classifies as "complete"

On the morning of 31 August the strip renders "August looked like a normal month"
hours before month-end debits land. One-day window; arithmetically honest, but the
phrasing is not provisional in the case that most needs it.

---

## Split judgement

**Two lanes of three said do not split; one said split.** The majority reasoning:
§2.1/§2.2's rejected-design evidence is what makes §4.6's merchant-family rule
legible, and separating a rule from the vault that proves it necessary is how
§2.2's rejected design comes back.

**All three lanes independently identified the same trim**, which is worth doing
regardless: roughly 80–100 lines of *review archaeology* addressed to a reviewer
rather than to the implementer §14 names as the audience — "an earlier draft set
it to 50", "an earlier draft of this clause asserted `cause is None`", "this tally
has been miscounted by hand three times", §11's three paragraphs of commentary
about its own tally, and the parenthetical grep-count justifications in §4.5, §4.9
and §10. **That belongs in §13's loop log.** Doing that trim is the cheapest way
to bring the document back under its siblings' size without losing contract.

The dissenting lane's seam, recorded for completeness: split along the project's
own `docs/specs/` ÷ `docs/plans/` line (`documentation.md` §10), with the plan
taking §5's *Test:* clauses, §7, §10 and §11 — on the argument that three of the
highest findings above are contradictions between an invariant's test clause and
§7/§11, today separated by 300 lines.
