# category_library — test contract (FIBR-0139)

Enforces `docs/specs/FIBR-0139.md` — the bundled, per-release **category library** that
auto-categorises common merchants out of the box. It runs **after** the user's own rules
and only on unclaimed (auto) rows, stamps guessed rows `'library'`, and is gated by a
default-ON settings toggle. No network, no real financial data; every on-disk vault uses
`tmp_path`.

The autouse `_neutralise_category_library` fixture (top-level `conftest.py`) replaces
`load_library` with `lambda: []` for the whole suite so nothing is coupled to the shipped
file — legs that need a library either inject a fixture list (in the test body, after the
autouse patch, last-write-wins) or carry `@pytest.mark.real_library` to drive the genuine
loader.

## INV-1 — money-safety

`recategorize_auto_rows` only ever writes `(category_id, category_source)`: the
`amount_minor` **multiset** and the **grand-book total** are identical before/after a
library apply (per-category sums shift by design). Covered by the end-to-end apply leg.

## INV-2 — your rules win; library is the fallback

`categorize_with_library`: a matching user **rule** beats a matching **library** entry;
library-only match → `(id, 'library')`; neither → `(None, None)`. `would_categorize` with
a user rule for a merchant returns the **rule's** category, not the library's.

## INV-3 — manual always wins

A **manual** row is never in the `auto_rows` read set, so a library apply never touches
it (asserted in the end-to-end apply + toggle legs).

## INV-4 — library rows stamped `'library'`; no migration

A guessed row carries `category_source == CategorySource.LIBRARY.value` (`"library"`); no
schema change (the free-text column already recomputes non-`'manual'` rows).

## INV-5 — runs on the existing paths

The library is consulted inside `recategorize_auto_rows` (import / Apply) **and** the
delete-category cascade, and folded into `would_categorize` (so confirming a guess raises
no learning nag, overriding one does). Covered by the apply, delete-cascade, and
would_categorize legs.

## INV-6 — bind by name; rename-safe

`match_library` returns an id only when the entry's `category` resolves in the leaf
`name_to_id` map; a renamed/deleted default drops the entry (fall-through to
Uncategorised, never mis-filed). `_leaf_name_to_id` is **first-wins** on a duplicate
name (`setdefault`) — a cross-parent "Misc" resolves to the `list_all`-first (Income)
leaf.

## INV-7 — off switch (default ON)

`library_enabled` defaults ON (absent key). `set_library_enabled(False)` → the next apply
reverts every `'library'` row to Uncategorised (user-rule + manual rows unaffected);
`set_library_enabled(True)` + apply **re-files** the guesses (off→on symmetric). The
setting round-trips.

## INV-8 — fail-safe load

`parse_library` is pure + **total** (never raises): unparseable / non-array JSON → `[]`;
a mixed array drops non-dict / malformed elements and keeps the valid ones; a
blank/whitespace `pattern` or blank `category` is skipped. `load_library`'s file layer
(`@pytest.mark.real_library`) returns `[]` for a missing, garbage, or **non-UTF-8** file
(the `UnicodeDecodeError` branch) with no raise, clearing the `lru_cache` before each and
trailing. **Shipped-file data guard** (`@pytest.mark.real_library`): the real
`category_library.json` parses to a non-empty list, maps a few known merchants as
expected, and **every** entry's `category` is a `DEFAULT_CATEGORIES` leaf (a typo like
`"Entertainmnet"` fails CI, not silently in a user's import).

## INV-9 — every guess marked, overridable

In the Transactions tab a `'library'` row's Category cell shows a `~ guess` marker + a
tooltip; a rule/manual row shows the plain name. **Every** cell is a `SortableItem` keyed
on the bare name, so a guessed row sorts **with** its plain-named siblings (sort-grouping
leg). Overriding via **Set category…** flips the row to `'manual'` and drops the marker.
The id-keyed filter is unaffected.

## INV-10 — idempotent

A second apply with unchanged rules + library changes **0** rows (the apply leg's
re-apply assertion).

## INV-11 — no network; i18n

Convention gate: the one new user string (`~ guess` + tooltip + the checkbox label) is
`tr()`-wrapped (manual review + `lupdate`), and no new `urllib` importer is added — not a
runtime case.

## Bundling parity (Deliverable 9)

The `finbreak/data` `--add-data` pair travels alongside `finbreak/ui/icons` in both freeze
sites; the Windows/Linux parity guard set-checks **both** targets. Enforced in the
`windows_build` suite, not duplicated here.

## Out of scope

Learn-from-history (FIBR-0140), structural id-binding, immediate re-file on toggle,
regex/wildcard entries, a user-editable/importable library.
