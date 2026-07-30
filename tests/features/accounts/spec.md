# accounts (P03) — feature test contract

**Theme:** money lives in accounts. Several accounts per profile, each with a
type; every transaction belongs to one; and the first forward-only schema
migration (v1→v2) that adds the account link.

This is the test-side contract for **five** specs, one block per spec below.
The `## Invariants` block belongs to
[`docs/specs/FIBR-0005.md`](../../../docs/specs/FIBR-0005.md); each later block
names its own spec in its heading. Numbering **restarts at INV-1 in each
block** and is not shared between them, so every invariant carries a `Source:`
line naming the spec it maps to. `test_accounts.py` enforces them all, except
FIBR-0193's INV-1 / INV-2, which live in `test_migration_v13.py` in this
directory, and FIBR-0113's INV-8 / INV-17, which extend
`tests/features/table_state/test_table_state.py`. Every on-disk vault uses
`tmp_path`; no test touches the network or real financial data (testing.md § 6).

## Invariants

- **INV-1** — Account CRUD round-trips: `AccountRepository.add` returns the new
  id; `list_all()` returns `Account` records ordered by name (case-insensitive)
  then id; `get` returns the row or `None`; `update` overwrites name+type;
  `delete` removes exactly that row; delete/update of a missing id is an
  idempotent no-op. Source: FIBR-0005 INV-1. (`amended by FIBR-0193`: at schema
  v13 `update` overwrites name+type **and** `account_number`+`note`, and both
  writers take the two extra parameters.)
- **INV-2** — `AccountType` is the seven tokens `current`, `savings`,
  `credit_card`, `personal_loan`, `home_loan`, `investment`, `other`; an unknown
  type raises `ValueError`; the token is stored verbatim. Source: FIBR-0005 INV-2.
- **INV-3** — Name validation: empty/whitespace or a case-insensitive duplicate
  raises `ValueError`; on update, the account's own name is excluded from the
  duplicate check; a valid name is stored trimmed. Source: FIBR-0005 INV-3.
- **INV-4** — The v1→v2 migration is forward-only, atomic, idempotent, with
  backfill: a hand-built v1 vault upgrades to v2 (accounts table + seeded
  Default + `account_id` on every prior row = the Default id); a forced failure
  mid-migration rolls back to a re-openable v1; re-running on v2 is a no-op; a
  first-run vault ends at v2; a version beyond latest raises `SchemaVersionError`.
  Source: FIBR-0005 INV-4.
- **INV-5** — Every transaction belongs to an account: `account_id` is required
  through repo + service; a transaction reads back with the right `account_id`
  and account name; an insert against a non-existent account raises
  `IntegrityError`. Source: FIBR-0005 INV-5.
- **INV-6** — Delete guard: an in-use account raises `AccountInUseError`
  (nothing removed); the only remaining account raises `LastAccountError`; an
  empty non-last account deletes; a missing id falls through to a no-op. Source:
  FIBR-0005 INV-6.
- **INV-7** — Accounts-manager UI round-trip (`qtbot`): the type picker offers
  the seven types (labels map back to tokens); Add shows the account in the
  **table** and in the main window's account picker; a transaction shows its account name;
  deleting an in-use account shows a message and removes nothing; an empty
  non-last account deletes; selecting an account loads it into the form and
  Update selected renames/retypes it in place (the add/edit form). Source:
  FIBR-0005 INV-7 (a–f). (`amended by FIBR-0193`: the Update-selected round-trip
  now also passes the account's stored `account_number` / `note` back unchanged,
  locked by that item's INV-7. `amended by FIBR-0113`: the on-screen list is a
  five-column table, so every leg asserts on cells rather than on a row-wide
  string, and selecting an account loads **four** inputs.)
- **INV-8** — The new modules add no network import and log no secret across an
  account add→delete cycle (covered by the vault-suite whole-`src/` scan plus a
  `caplog` capture here). Source: FIBR-0005 INV-8.

## FIBR-0128 — forget remembered statement passwords (Accounts screen)

Test-side contract for [`docs/specs/FIBR-0128.md`](../../../docs/specs/FIBR-0128.md);
each `INV-N` below maps to that spec's invariant of the same number (a separate
numbering from the FIBR-0005 invariants above). The remembered PDF password
(`accounts.statement_pdf_password`, FIBR-0009) is presented + cleared here, never
displayed.

- **INV-1** — The saved password never crosses into the UI: `AccountRepository
  .ids_with_pdf_password()` / `AccountService.account_ids_with_pdf_password()`
  return an **id-set** (empty by default), never the secret; the widget never calls
  `get_pdf_password` during render, and a stored sentinel appears in no row
  text/tooltip/item-data. Source: FIBR-0128 INV-1. (`amended by FIBR-0113`: the
  sweep is **re-derived**, not re-pointed — it walks every cell's `text()` and
  `toolTip()` across all five columns plus the two `_table_state` roles. The old
  literal role list re-pointed at the table would keep passing while sweeping
  strictly less: `UserRole` / `+1` are re-purposed into row mechanics that could
  never hold a password, and four columns would go unswept.)
- **INV-2** — A per-account marker (the phrase "statement password saved") shows on
  exactly the rows whose account has a saved password. Source: FIBR-0128 INV-2.
  (`amended by FIBR-0113`: the marker lives in the **Status cell**, second after
  the reconciliation text; the row is found by its Name cell.)
- **INV-3** — The **Forget statement password** button is disabled with no selection
  and for an account without a saved password, enabled only for a selected account
  that has one, and disabled again after a Forget clears the selection. Source:
  FIBR-0128 INV-3.
- **INV-4** — Confirming Forget clears only the selected account's password (marker
  drops; other accounts untouched); declining the confirm keeps it. Source:
  FIBR-0128 INV-4.
- **INV-5** — An auto-lock during the clear (`VaultLockedError`) returns silently —
  no crash, no error text — like the add/delete handlers. Source: FIBR-0128 INV-5.

## FIBR-0193 — optional account number + note (schema v13)

Test-side contract for [`docs/specs/FIBR-0193.md`](../../../docs/specs/FIBR-0193.md);
each `INV-N` below maps to that spec's invariant of the same number (a third
numbering, separate from the FIBR-0005 and FIBR-0128 blocks above). Storage
only — nothing displays or edits either field until FIBR-0113.

- **INV-1** — A vault at v12 upgrades to v13 in place, gaining exactly
  `accounts.account_number` and `accounts.note`, **both nullable**, with every
  pre-existing row still present and its other columns unchanged; the step is
  atomic (a wedged second `ALTER` leaves a re-openable v12 with neither column)
  and idempotent at latest. Enforced by `test_migration_v13.py`. Source:
  FIBR-0193 INV-1.
- **INV-2** — `LATEST_SCHEMA_VERSION == 13` and `13 in _MIGRATIONS` — the
  constant and the dispatch table agree. Enforced by `test_migration_v13.py`.
  Source: FIBR-0193 INV-2.
- **INV-3** — `Account`'s field order and the SELECT column order in both
  `AccountRepository.list_all()` and `.get()` agree, so positional
  `Account(*row)` construction assigns each column to the field of that name: a
  populated write reads back by field name on both read paths. Source:
  FIBR-0193 INV-3.
- **INV-4** — Within `repositories/accounts.py`, `statement_pdf_password` is
  named only inside the three dedicated accessors — no listing query in that
  file selects it (an AST walk; re-asserts FIBR-0128 INV-1 at source level).
  Source: FIBR-0193 INV-4.
- **INV-5** — A blank account number or note passed through
  `AccountService.add_account` is stored as SQL `NULL`, not `""` (covering `""`
  and whitespace-only separately); `_normalise_optional` applies on **both**
  service write paths. Source: FIBR-0193 INV-5.
- **INV-6** — `update_account` **persists** both fields: editing writes the new
  value, and clearing a filled field to blank writes SQL `NULL` back over it.
  Two legs, so the fault localises to the repository's `SET` clause or the
  service's normalisation. Source: FIBR-0193 INV-6.
- **INV-7** — `AccountsWidget._on_update` passes the selected account's existing
  `account_number` and `note` through unchanged, so an Update that edits only
  the name or type leaves both stored fields intact (`qtbot`). Source:
  FIBR-0193 INV-7.

## FIBR-0113 — the sortable 5-column table, account number masked

Test-side contract for [`docs/specs/FIBR-0113.md`](../../../docs/specs/FIBR-0113.md);
each `INV-N` below maps to that spec's invariant of the same number (a fourth
numbering). **The ids are non-contiguous by design** — eleven were withdrawn to
FIBR-0193, FIBR-0192 and FIBR-0198 when that spec was split, and spec-format
§3.7 forbids renumbering or reusing them, so the gaps are permanent handles
rather than omissions. INV-8 and INV-17 live in
`tests/features/table_state/test_table_state.py`; the rest in `test_accounts.py`.

- **INV-5** — `_mask_account_number` returns a mask plus the last 4 characters
  for a value longer than 4, a **bare** mask for a value of 1–4 characters, and
  an empty string for `None` or `""`. Source: FIBR-0113 INV-5.
- **INV-7** — After the user sorts by any column, Update, Delete and Forget act
  on the account the user **selected**, not on the parallel-list entry sitting
  at that visual row index. Source: FIBR-0113 INV-7.
- **INV-8** — The table's `objectName` is `accounts_table`, distinct from every
  other table passed to `remember_columns`. Source: FIBR-0113 INV-8.
- **INV-9** — The Status column orders by reconciliation **severity**, not by
  its rendered string (OFF → quiet → RECONCILED ascending); its text composes
  the reconciliation marker first and the 🔑 marker second, `" · "`-joined,
  absent parts omitted. Source: FIBR-0113 INV-9.
- **INV-12** — Typing an account number and a note and pressing Add stores both
  and clears the form; re-selecting repopulates both fields with the
  **normalised stored value**, the number field still in `Password` echo mode;
  a `_refresh()` with the selection cleared leaves the form untouched. Source:
  FIBR-0113 INV-12.
- **INV-15** — `_select_account(account_id)` selects the row displaying that
  account whatever the sort — it resolves the id to a **position** in
  `self._rows` rather than passing it to `select_by_index` — and leaves the
  selection unchanged for an unknown id. Source: FIBR-0113 INV-15.
- **INV-17** — The columns are user-reorderable and the layout survives a
  rebuild: a fresh widget restores the moved order and the set widths. Source:
  FIBR-0113 INV-17.
- **INV-18** — Repopulating while a sort is active never mis-pairs cells: every
  row's five cells belong to the same account after a refresh, in both sort
  directions. Source: FIBR-0113 INV-18.
- **INV-20** — The Account-number **column** renders
  `_mask_account_number(account.account_number)` for every row, whatever the
  sort order. Source: FIBR-0113 INV-20. (`amended by FIBR-0198`, which
  narrows this to the reveal-off state.)
- **INV-21** — The table is click-sortable: `isSortingEnabled()` is `True` and
  driving a header section reorders the rows. Source: FIBR-0113 INV-21.
- **INV-22** — `_refresh()` leaves the table with **no selection**, whatever
  sort is active, so no stale selection survives a repopulate and resolves to a
  different account. Source: FIBR-0113 INV-22.

## FIBR-0198 — reveal the masked account number, with an auto re-mask

Test-side contract for [`docs/specs/FIBR-0198.md`](../../../docs/specs/FIBR-0198.md);
each `INV-N` below maps to that spec's invariant of the same number (a fifth
numbering). All five legs are `qtbot` tests over a constructed `AccountsWidget`,
except INV-1 leg (c), which builds a `MainWindow` solely to drive a lock cycle.

- **INV-1** — A freshly constructed `AccountsWidget` has reveal **off**, the
  toggle state is written to no persistent store, and a lock cycle returns it to
  off. The non-persistence leg reads the window INI's **keys** through
  `QSettings` after `sync()` (not the file's bytes, which a buffered `setValue`
  never reaches during a test) and excludes only the single
  `columns/accounts_table` key, not the whole `columns/` group. Source:
  FIBR-0198 INV-1.
- **INV-2** — A reveal re-masks on its own after `_REVEAL_SECONDS`; a manual
  uncheck cancels the pending timer; and **nothing but a fresh reveal
  (re)starts** it — not a `_refresh()` from any other cause. Leg (a) emits the
  timeout and asserts the re-mask, because every other leg observes the timer's
  *configuration* and would pass against an implementation that never connects
  `timeout`. Source: FIBR-0198 INV-2.
- **INV-3** — The edit form's account-number field is `Password` echo with
  reveal off and `Normal` with it on, and stays editable in both states.
  Asserted on `displayText()`, never on `text()` — a `Password` field's `text()`
  is never masked. Source: FIBR-0198 INV-3.
- **INV-4** — Toggling reveal preserves an in-progress edit: the selection, all
  four form inputs and the Forget button's enabled state are unchanged. Driven
  for both the manual off-transition and the **unattended** one (the timer),
  which is the case that matters, since the spec has decided a re-mask may land
  mid-edit. Source: FIBR-0198 INV-4.
- **INV-5** — The Account-number **column** renders the raw stored value while
  reveal is on and returns to the mask when it goes off, for every row —
  including across a non-toggle `_refresh()`, the only leg that exercises the
  fill reading `self._reveal.isChecked()` rather than a toggle parameter.
  Source: FIBR-0198 INV-5.

## Out of scope

Editing an existing transaction's account; reassigning/bulk-moving transactions;
per-account currency/opening-balance/institution; import/categorisation/
dashboard/export. See FIBR-0005 § "Out of scope". **FIBR-0128:** revealing the
stored password; setting/changing it by hand (re-learned on the next locked
import); Settings-screen placement; Business/Personal grouping (FIBR-0137).
**FIBR-0193:** the Accounts tab UI for the two new fields — the 5-column table,
the masked cell and form field, the reveal toggle — all FIBR-0113/FIBR-0198;
detecting an account number on an imported statement and matching it
(FIBR-0086); per-account currency (FIBR-0087).
**FIBR-0113:** the reveal control — the "Show account numbers" checkbox, its
auto re-mask timer, and the echo-mode switch on the form field (FIBR-0198);
finishing FIBR-0084 (the Forecast table, the Home dashboard trees, and Reset
layout clearing saved column state — FIBR-0192); preserving the selection
across a tab switch, and column customisation on the Categories tree, both
permanent decisions rather than deferrals.
**FIBR-0198:** making `_REVEAL_SECONDS` user-configurable, and a reveal that
survives a lock or a restart — both decisions rather than deferrals, so
neither has a follow-up id.
