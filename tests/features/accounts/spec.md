# accounts (P03) — feature test contract

**Theme:** money lives in accounts. Several accounts per profile, each with a
type; every transaction belongs to one; and the first forward-only schema
migration (v1→v2) that adds the account link.

This is the test-side contract for [`docs/specs/FIBR-0005.md`](../../../docs/specs/FIBR-0005.md);
each `INV-N` maps to that spec's invariant of the same number. `test_accounts.py`
enforces them, except FIBR-0193's INV-1 / INV-2, which live in
`test_migration_v13.py` in this directory. Every on-disk vault uses `tmp_path`;
no test touches the network or real financial data (testing.md § 6).

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
  the seven types (labels map back to tokens); Add shows the account in the list
  and in the main window's account picker; a transaction shows its account name;
  deleting an in-use account shows a message and removes nothing; an empty
  non-last account deletes; selecting an account loads it into the form and
  Update selected renames/retypes it in place (the add/edit form). Source:
  FIBR-0005 INV-7 (a–f). (`amended by FIBR-0193`: the Update-selected round-trip
  now also passes the account's stored `account_number` / `note` back unchanged,
  locked by that item's INV-7.)
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
  text/tooltip/item-data. Source: FIBR-0128 INV-1.
- **INV-2** — A per-account marker (the phrase "statement password saved") shows on
  exactly the rows whose account has a saved password. Source: FIBR-0128 INV-2.
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
