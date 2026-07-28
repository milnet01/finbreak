# Loop 5 — verified findings, NOT YET FIXED (deferred tail)

Run: `/cold-eyes docs/specs/FIBR-0113.md`, loop 5, 2026-07-28.
Status: **verified, unfixed.** The run stopped after Phase 3 on the user's standing
instruction ("if it's still substantive, stop and report before looping again").

> **Do NOT re-review to rediscover these.** A fresh loop costs a full three-lane
> multi-agent dispatch to regenerate what is already written here, with cites and
> proposed fixes. Fold them in directly.

Severities below are the **orchestrator's** re-grade against the brief's definitions
(one grader, one standard). Each entry records the lane's original label where it
differed. Cites are by symbol / section — the project forbids `path:line`.

Origin tags: **[D]** = draft defect (present as written, survived 4 cold loops).
**[C]** = collateral from an earlier loop's own fixes.

---

## CRITICAL (3)

### CR-1 [C] — §4.5's selection premise is false, and the surviving selection points at a different account
*Lane B, labelled CRITICAL. Reproduced empirically — see `repro_b1b.py` beside this file.*

§4.5 opens: *"Toggling reveal repopulates the table and therefore drops the current
selection, so `_on_reveal_toggled` is specified as an ordered sequence…"* — the whole
six-step list rests on this.

It is false under the fill shape §4.4 specifies (`fill_guard` + `setRowCount(len(rows))`
+ `setItem` + `tag_row` — the `StatementsWidget.refresh` precedent §4.4 names). Measured
against the real `_table_state` helpers and real Qt, three accounts (`Alpha`, `Mid`,
`Zed`), Name-descending sort:

| selected visual row | `selected_index` before | after refill | verdict |
|---|---|---|---|
| 0 | `Zed` | `Alpha` | **drift** |
| 1 | `Mid` | `Mid` | same (the sort's fixed point) |
| 2 | `Alpha` | `Zed` | **drift** |

Mechanism: `setRowCount(len)` does not clear rows, so the selection survives; the
selection then rides the *item* through the re-sort that `fill_guard`'s exit triggers,
landing on whichever account's **insertion index** equals the previously-selected
**visual row**.

Consequence chain: step 4's `_refresh()` ends (per §4.4) with `self._on_selection_changed()`,
which loads the **wrong** account's name / type / number / note into the form; step 5
re-selects the captured id with signals blocked, so the form keeps account B's values
while the selection points at account A; the next Update writes B's data onto A.
**Silent cross-account write in a money app.**

A `setRowCount(0)` / `clearContents()` before the fill *does* clear the selection
(verified) — but §4.4 never says which shape `_refresh()` uses.

**fix:** pin the clear-then-fill shape in §4.4 as the mechanism steps 1/5/6 depend on;
rewrite §4.5's premise to match; add an invariant that a `_refresh()` under an active
sort never leaves the selection resolving to a different account.

**Code-side observation (not a doc finding, surface separately):** `StatementsWidget.refresh`
has this same latent drift today. It is harmless there only because its
`_on_selection_changed` toggles two buttons and touches no form.

### CR-2 [C] — §4.4's trailing `_on_selection_changed()` imports a form-overwrite the precedent never had
*Lane B, labelled CRITICAL.*

§4.4: *"— like `StatementsWidget.refresh` — **ending with an explicit
`self._on_selection_changed()`** so the Forget button's enabled state cannot be left
stale…"*

The precedent is *nearly* what the spec says. `StatementsWidget._on_selection_changed`
sets two button enabled-states and nothing else. `AccountsWidget._on_selection_changed`
also writes `_name` / `_type` (and now `_account_number` / `_note`) from storage. The
trailing call therefore repopulates the form on **every** `_refresh()` — `_on_add`,
`_on_update`, `_on_delete`, `_on_forget_password`, and `MainWindow._refresh_tab`'s
refresh on every Accounts-tab activation.

It directly defeats §4.5's *"`_refresh()` itself does **not** re-select — doing so would
make `_on_add`'s field-clearing useless"*: it reaches that outcome by another route.
(With CR-1, a selection does survive `_on_add`'s refresh, so the clear is genuinely undone.)

**fix:** the trailing call re-applies only the Forget gating (the helper §4.5 step 6
alludes to — see HI-6), not the whole handler.

### CR-3 [C] — INV-12's cell assertion contradicts the masking decision
*Corroborated: lane B (HIGH) and lane C (CRITICAL) independently.*

INV-12's *Test:* — *"…re-selecting the row, and asserting **both the cells** and both
form fields carry the typed values."*

With reveal off (the constructed default INV-6 pins), §4.3 puts
`_mask_account_number(...)` in the Account-number **cell** — `"•••• 7890"`, or `"••••"`
for a value of ≤4 characters — never the typed value. So the leg as written fails
against a *correct* implementation, and an implementer satisfies it by rendering the raw
number in the cell. That ships §3 decision 2 — the spec's central security decision —
broken, with every other invariant green. It also contradicts INV-12's own body
(*"the **normalised stored value** … not verbatim what was typed"*).

**fix:** assert the Note cell and both form fields carry the normalised value, and state
the Account-number cell's expected value explicitly per reveal state.

---

## HIGH (6)

### HI-1 [D] — no invariant, and no §11 row, for the table cell's mask/reveal rendering
*Lane C, HIGH.* INV-5 covers the pure helper; INV-16 covers the *form field*; INV-6
covers the checkbox. **Nothing pins that `_refresh()` renders `_mask_account_number(...)`
in the Account-number column while reveal is off and the raw value while on.** INV-16's
own falsifier (*"only the table cell is masked and the form is left plain"*) assumes cell
masking is guaranteed elsewhere — it is not. §3 decision 2 is the spec's central decision
and is the one surface with neither an invariant nor a bolded `nothing` row.
**fix:** add an invariant asserting the column's rendered text per reveal state, plus its §11 row.

### HI-2 [D] — nothing pins that the table is click-sortable
*Lane C, HIGH.* §1 promises "five sortable columns" and §2 consequence 1 is the headline
motivation, yet INV-17 exists only for `remember_columns`. INV-7 / INV-15 / INV-18's
tests "sort descending by Name" — and `QTableWidget.sortItems()` works whether or not
`setSortingEnabled` was ever called. So omitting §4.4's `enable_sorting(self._table)`
line passes all 17 invariants while the user cannot click a header. This is exactly the
gap INV-17 was written to close for the sibling `remember_columns` call.
**fix:** add an invariant (or a leg on INV-9) asserting `isSortingEnabled()` / that a header click reorders.

### HI-3 [D] — no invariant locks the `update` write path for the two new columns
*Lane A, HIGH.* §4.2 says "`add()` / `update()` grow the two parameters", and
`AccountRepository.update` today is `UPDATE accounts SET name = ?, type = ? WHERE id = ?`.
INV-12 covers only *Add*; INV-3 covers read-path field order; INV-10 covers blank→NULL
"after saving"; §11 has no update-round-trip row. An implementer can accept the two new
parameters on `AccountRepository.update` and never add them to the `SET` clause, and
**all 17 live invariants still pass** — an edited account number is silently dropped, and
clearing a stored number to blank silently keeps the old value. §3 decision 6 defends
against *callers omitting* the arguments; nothing defends against the *repository
ignoring* them.
**fix:** widen INV-12 (or add an invariant) to cover the update path including clearing a filled field to `NULL`, and give it a §11 row.

### HI-4 [D] — INV-7's test cannot fail in the state its *Breaks when* describes
*Lane B, HIGH.* *Test:* — *"select a row, assert the resolved account is the one displayed
there"* — exercises `_table_state.selected_index` (already covered by
`test_selected_index_reads_the_tag` and
`test_transfers_confirm_targets_sorted_row_not_insertion_order`), not Update / Delete /
Forget. A handler reading `self._table.currentRow()` — the stated *Breaks when* — is
never called, so the leg passes in the broken state. This is the invariant the spec
itself calls "the money-adjacent one".
**fix:** drive each of the three handlers on a sorted table and assert the *stored effect* landed on the selected account.

### HI-5 [D] — INV-9's ordering assertion is not falsifying
*Lane B, HIGH.* *"sorting ascending puts every `OFF` account above every `RECONCILED` one"*
— under the *Breaks when* (a plain `QTableWidgetItem`, lexical sort) the OFF text starts
`⚠` (U+26A0 = 9888) and RECONCILED starts `✓` (U+2713 = 10003), so **a lexical sort
already orders OFF above RECONCILED**. The assertion passes in the broken state. Only the
middle rank is discriminating: an empty cell (`""`, rank 1) sorts *first* lexically but
*between* by rank; a 🔑-only cell (U+1F511) sorts *last* lexically but *middle* by rank.
**fix:** restate as the three-way OFF < quiet < RECONCILED, requiring quiet rows both with and without the key marker.

### HI-6 [C] — §4.5 step 6 names a shared helper no section defines
*Lane B, HIGH.* *"It shares the helper `_on_selection_changed` uses rather than
duplicating the rule"* — no section defines that helper. §4.4 specifies
`_on_selection_changed` as one method doing **both** gating and form population; §11's
Forget-gating row names none either. An implementer most likely just calls
`_on_selection_changed()`, re-clobbering the form step 5 just protected (and, with CR-1,
from the wrong account).
**fix:** name and specify it (e.g. `_apply_forget_gating()`), called from both sites. Resolves CR-2 as well.

---

## MEDIUM (13)

- **ME-1 [D]** — **INV-10 is scoped to one write path where §4.2 specifies two.** §4.2:
  `_normalise_optional` is "called by `add_account` **and** `update_account` **inside the
  service**, so INV-10 holds for every caller". INV-10's *Test* is only "asserting
  `account_number IS NULL` after saving with the field left empty" — singular. Compare
  INV-3, which says "on **both** read paths". An implementer can normalise in
  `add_account` only and pass. *fix:* add "on both `add_account` and `update_account`".
- **ME-2 [D]** — **INV-11's test cannot falsify its own first *Breaks when*.** "driving
  the widget's timer directly" does not observe "the timer is left repeating instead of
  single-shot", and the third clause ("leaves the pending interval untouched") has no
  named observable. *fix:* assert `isSingleShot()`, `isActive()` False after a manual
  uncheck, and `remainingTime()` non-increasing across an unrelated `_refresh()`.
- **ME-3 [D]** — **the `UserRole` collision is an implementation hazard, not only a test
  hazard.** `_ACCOUNT_ID_ROLE` is `Qt.ItemDataRole.UserRole`; so is
  `_table_state._ROW_INDEX_ROLE`. §6 raises this only as a *test* hazard. If any
  `_ACCOUNT_ID_ROLE` `setData` survives the rewrite, one overwrites the other and
  `selected_index` can return a database id used as a `self._rows` index. §4.4 mandates
  deleting the constants, but nothing catches a leftover. *fix:* state it in §4.4 and add
  a §11 row.
- **ME-4 [D]** — **`_on_add`'s clear and the clear-selection behaviour are locked by
  nothing.** §4.5's "clears the three `QLineEdit`s … leaves the Type picker on its current
  selection" and `_on_selection_changed`'s "leaves them untouched when the selection
  clears" have no invariant; INV-12 adds then re-selects, so it passes either way, and
  §11 counts neither. *fix:* extend INV-12's leg to assert the post-Add state; add a §11
  row for clear-selection.
- **ME-5 [D]** — **§4.4's `VaultLockedError` bullet does not say where the guard sits.**
  If it wraps the whole body, `self._rows` / `self._with_pw` / the table can be left
  half-updated while §4.5 steps 5–6 run against them — and §11 already records that no leg
  drives a timeout into a locked vault. *fix:* state that the guard wraps the service
  reads *before* any mutation, leaving the previous render intact.
- **ME-6 [D]** — **INV-6 leg (b) excludes a whole group.** "no key outside the `columns/`
  group changed" — a flag persisted as `columns/accounts_reveal` is invisible to the leg
  meant to fail on it. *fix:* exclude exactly `columns/accounts_table`.
- **ME-7 [C]** — **§12's screenshot bullet is wrong on all three named consumers.**
  Verified: `README.md` embeds **no screenshots** (its only two `![` are shields.io
  badges) and has **no `## Features` heading** (the feature list lives under `## Status`);
  `assets/screenshots/site/` has **no `accounts.png`**; and the AppStream metainfo
  (`packaging/obs/io.github.milnet01.finbreak.metainfo.xml`) lists six screenshots, **none
  of them Accounts**. Only `{midnight,ledger}/accounts.png` exist. *fix:* restate as
  "regenerate `assets/screenshots/{midnight,ledger}/accounts.png` with reveal off; update
  the README's feature bullets under `## Status`" and drop the site/metainfo claims (or
  say those sets carry no Accounts shot).
- **ME-8 [C]** — **FIBR-0128's INV-2 is left stale.** Verified: INV-2 reads "the **exact
  D4 marker literal** appended to its **row label** … the marked row's `item.text()`
  **contains** the stable phrase". This spec moves the 🔑 marker into a Status cell,
  *second*, and deletes the row label. §12 annotates INV-1 only. *fix:* annotate INV-2
  `amended by FIBR-0113` too.
- **ME-9 [C]** — **§12's FIBR-0177 claim is inaccurate.** Verified: FIBR-0177's INV-9 row
  pins **three** reconciliation literals (`✓`, `⚠ off by {money}`, `⚠ {n} periods don't
  reconcile`) and never mentions 🔑; the 🔑 literal appears in D6 *prose* only. So "pins the
  four marker literals … in its D6 list **and** its INV-9 row" is false for INV-9. (The
  🔑-then-reconciliation order claim **is** correct.) *fix:* "FIBR-0177 pins the three
  reconciliation literals in its D6 list and its INV-9 row; the 🔑 literal is pinned in D6's
  prose only."
- **ME-10 [C]** — **INV-6 claims a §7 scoping that §7 does not carry.** INV-6 says
  "(§7 and §11's 'constructed standalone' notes are scoped to exclude it)". §11's row
  *does* carry the exception; §7's closing sentence flatly states the `qtbot` legs "do
  **not** prove the tab renders correctly inside `MainWindow`" with no exception.
  *fix:* add the INV-6 leg (c) exception to §7.
- **ME-11 [C]** — **the T13 "ships false" argument cites the wrong surface.** The T13
  quote is exact and the "no mention of masking / shoulder-surfing / screenshots" negative
  is verified. But T13's clause is about **copyability**, and a `QTableWidgetItem` is not
  copyable — a revealed table cell alone does not falsify it. The `QLineEdit` in `Normal`
  echo mode **is** (Ctrl+C works; `Password` suppresses it). The conclusion is right, the
  justification is wrong. *fix:* ground the T13 amendment in the revealed **form field**.
- **ME-12 [C]** — **the header's `Source:` line is stale.** It reads "with FIBR-0084
  folded in", but §3 decision 7 splits that work out and ROADMAP FIBR-0113's body states
  "The 'FIBR-0084 folded in' plan above is **WITHDRAWN**". *fix:* reword to "FIBR-0084
  scope-checked; its remaining surfaces split to FIBR-0192".
- **ME-13 [D]** — **ROADMAP FIBR-0113's own headline and Layman card still say four
  columns.** Verified: `**Accounts tab: show accounts in columns (Name / Type / Account
  number / Note) instead of one line.**` and the Layman line both omit Status; only the
  body's "User decisions (2026-07-28)" carries five. §12 says only "**only FIBR-0113 flips
  ✅**". *fix:* add "FIBR-0113's headline + Layman card are reconciled to five columns".

---

## LOW (13)

- **LO-1 [D]** §7 "That precedent has **five** legs" — `test_migration_v11.py` has **12**
  test functions; five concern the migration. *fix:* "its **five migration legs** (the
  other seven cover the repository)".
- **LO-2 [D]** §7 leg 4's atomicity assertion is weaker than its precedent's:
  `test_INV9_migration_is_atomic` asserts **both** the version *and* column absence; the
  spec's leg says only "still a re-openable v12". *fix:* "…still v12 **with neither
  `account_number` nor `note` present**". (Lane A framed the consequence as a permanently
  unopenable vault — that is **overstated**: SQLite DDL is transactional, so
  `owned_transaction` rolls the `ALTER` back. The strengthening is still right.)
- **LO-3 [D]** §7 leg 2 misstates the precedent's fixture chain: "runs the intervening
  private **steps** in order" — the v11 file runs exactly **one** (`_migrate_to_v10`) then
  `run_migrations`. The extrapolation to three steps for v13 is right; the description of
  the precedent is not.
- **LO-4 [D]** INV-1 asserts "both nullable" but no leg observes nullability — the
  precedent's `_cols` helper returns column *names* only. *fix:* drop the claim, or have
  leg 1 read `PRAGMA table_info`'s `notnull` column.
- **LO-5 [D]** §4.2's "both with the parameters **required**" is justified by "the
  repository is the layer that issues the unconditional `UPDATE … SET`" — true of
  `update`, but `add` issues an `INSERT`, where a default is harmless. *fix:* add "and
  `add` matches for symmetry".
- **LO-6 [D]** §10's "widget memory is unchanged in shape" overstates: today's `setData`
  stores four scalars; `self._rows: list[Account]` retains full `Account` objects
  (additionally `created_at`, `account_number`, `note`).
- **LO-7 [D]** §7 cites `test_migration_v12.py` by bare filename where every other test
  reference is a full path; it lives under `tests/features/spending_alerts/`, which is
  non-obvious for an *accounts* migration precedent.
- **LO-8 [D]** §4.3 claims the `QTimer` block is "the same shape as `ClipboardAutoClear`",
  which calls `stop()` then `start(seconds * 1000)` per use where the spec sets
  `setInterval` in `__init__`. The quoted docstring reason argues for wiring `timeout`
  directly to the re-mask; the spec wires it to `_on_reveal_timeout` and repurposes the
  quote to support "named method, not a lambda", which the docstring does not say.
- **LO-9 [D]** §4.5 never gives `_on_reveal_toggled`'s signature. `ui/accounts.py`'s
  convention is `@Slot()` on zero-arg handlers; `QCheckBox.toggled` carries a `bool`, and
  `@Slot()` on a one-arg handler is a runtime `TypeError` under PySide6. *fix:* state
  `@Slot(bool)`, or read `self._reveal.isChecked()`.
- **LO-10 [C]** §6 understates the `test_reconciliation_marker.py` breakage. Verified: its
  module docstring ("The suffix is asserted on the QListWidgetItem text") and its
  `_row_text` helper — which finds a row by matching the account name inside the *same
  string* as the marker — both die when name and status become separate cells. §12's
  "re-pointed off `widget._list`" reads like a mechanical swap. *fix:* say the helper needs
  re-deriving.
- **LO-11 [C]** §9's departure count is wrong — "its other two (spec-format §4 …,
  `testing.md` …)" omits the third that §12 records (spec-format §2's mandatory plan).
  *fix:* "its other three". *(Standing-pair class SP1: a count in prose vs the set it counts.)*
- **LO-12 [C]** §12's "No build plan" bullet is self-contradictory: "spec-format §2 makes a
  plan mandatory 'once the build order matters (a migration, …)', **and this spec carries
  one**" — "one" means *a migration*, but under a bolded "No build plan." it reads as
  "carries a plan". *fix:* "…and this spec has a migration, so the rule bites."
- **LO-13 [C]** §12's cross-spec bullets are under-specified in three places: FIBR-0005's
  `ui/accounts.py` Deliverables entry ("a **list** of the user's accounts … an add/edit
  form (**name field** + a type `QComboBox`)") also goes stale and is not listed;
  FIBR-0013's bullet states a problem with **no action** where every sibling bullet says
  "annotated `amended by FIBR-0113`", pins the field list **twice** (the "Verified code
  basis" list *and* the body's "**Accounts.**" bullet), and the section is titled
  "Verified **code** basis", not "verified-API-basis"; and `security-model.md` carries a
  numbered §5 "Security invariants" checklist that §12 neither adds to nor explains away.
  Also: §7's `testing.md` §2.3 argument cites the form `# INV-3 from spec.md § 2.1`, but
  `tests/features/accounts/spec.md`'s headings are **unnumbered**, so the disambiguator is
  the heading *name*; §11 attributes `ui/accounts.py::_on_update` to two different catchers
  (§4.2's table says "rewritten by this spec anyway", §11 folds it into "the test run") and
  has no row for the direct `AccountRepository.update` call §4.2 flags; and §12 omits
  `tests/features/accounts/test_accounts.py` from its touched-file list.

---

## Dismissed (verified, NOT a defect)

- **INV-2's *Test:* being a `.venv/bin/python -c …` shell command** (lane A, LOW). This is
  the project's deliberate evidence-of-red form, §11 accounts for it explicitly ("plus the
  §5 command"), and `spec-format` encourages shipping the command that prints the figure.
  Not a finding.

## INFO (surfaced, not actioned)

- INV-4's AST test is name-based and would miss `SELECT *` (it would break loudly on
  `Account(*row)` arity, so not a live hole — worth one clause).
- §7's "run against pre-implementation source and seen to fail" is trivially true for a
  test file that does not yet exist; only INV-2's clause has real red evidence.
- `test_INV1_widget_never_renders_or_reads_the_secret` iterates `UserRole+1..+3`; once
  those roles are deleted the FIBR-0128 defence-in-depth legs pass vacuously.
- `_reconciliation_suffix()` keeps its name after §4.4 makes its output part of a cell.
- `docs/specs/FIBR-0117.md` does not exist (FIBR-0117 is ROADMAP-only); nothing links to
  it, so nothing is broken.
- `**Pairs with:**` omits FIBR-0005 / FIBR-0128 / FIBR-0177, whose invariants §12 amends.
- §8 says `coding.md` §1.3 "**forbids**" the duplication; §1.3 is "Reuse before rewriting",
  which *prefers* reuse and permits justified duplication.
- §9 presents FIBR-0087's note as the "same" quoted string FIBR-0086 carries; FIBR-0087's
  actual wording is `Schema migration (currently v7 -> v8).`

## Open questions for the user (decisions, not defects)

1. Which fill shape is canonical for `_refresh()` — clear-then-fill (which makes §4.5's
   premise true) or the `StatementsWidget` reuse-rows precedent §4.4 currently names?
2. Should the trailing `_on_selection_changed()` be narrowed to gating-only for *all*
   callers, or only on the reveal path?
3. Nothing in §5 covers "switch away from Accounts mid-edit and back", which
   `MainWindow._refresh_tab` makes reachable. In scope?
4. Does `_on_update` writing the two new fields need its own invariant (see HI-3)?

---

# The split plan (loop 5's recommendation, not yet executed)

`/cold-eyes` was stopped after loop 5 rather than looping again. The reasoning,
and the proposed next step, recorded here so it survives the session.

## Why not loop 6

- Loop 5's findings split roughly evenly between **draft defects** and
  **collateral** from loops 3–4's own fixes; loop 4 was already
  collateral-dominant.
- Loop 5 surfaced **three new structural draft defects** (HI-1, HI-2, HI-3) that
  four prior cold reads all missed. Draft defects are not falling monotonically,
  so the reads are not converging on the document.
- The spec is **985 lines** — 4th largest of 48 specs against a ~567-line median.
  The two specs in this repo that needed **nine and eleven** loops were both
  >1000 lines.

## Proposed seam

Two independently-gateable specs. The storage half ships first; the UI half
depends on it.

**Half 1 — storage (new id).** The quietest lane in loop 5: zero CRITICAL, one
HIGH, and its findings are all local.
- §4.1 (migration v13), §4.2 (model / repository / service)
- INV-1, INV-2, INV-3, INV-4, INV-10 (+ the new update-path invariant, HI-3)
- §6's schema-churn / backup bullets; §7's `test_migration_v13.py` legs
- §10's storage paragraph; §12's `seed_demo_vault.py`, FIBR-0005, FIBR-0013,
  FIBR-0086 and schema-pin entries
- Findings that move here: **HI-3, ME-1, LO-1..LO-7**

**Half 2 — the Accounts table UI (keeps FIBR-0113).** Where all three CRITICALs
landed. Its ROADMAP bullet already describes the UI, so the id stays put.
- §2, §4.3 (masking), §4.4 (table), §4.5 (form)
- INV-5..9, INV-11, INV-12, INV-15..19 (+ new invariants for HI-1 and HI-2)
- §6's widget / timer / lock / sorting bullets; §7's `qtbot` legs
- §12's security-model, FIBR-0128, FIBR-0177, README/screenshot entries
- Findings that move here: **CR-1, CR-2, CR-3, HI-1, HI-2, HI-4, HI-5, HI-6,
  ME-2..ME-13, LO-8..LO-13**

## Ordering note

CR-1 and CR-2 are the ones to resolve **first and together** — both hinge on one
undecided question (open question 1: which fill shape `_refresh()` uses), and
CR-2's fix depends on HI-6's helper being named. Resolve the fill shape, then
HI-6, then CR-1/CR-2 fall out.

## What must NOT be lost in the split

- **INV-13 and INV-14 are WITHDRAWN, not deleted**, and must not be reused or
  renumbered — `spec-format` §3.7, and the frozen §13 loop-1 row cites both ids.
- **FIBR-0084 stays 📋** when either half ships; FIBR-0192 is its blocker.
- **FIBR-0086's bullet amendment** (dropping its stale account-number storage
  half and its "v7 -> v8" note) belongs to the **storage** half.
- The §13 loop log is a frozen record of loops 1–5 — carry it into whichever
  half keeps FIBR-0113, and start the new spec's log fresh.
