# accounts (P03) — feature test contract

**Theme:** money lives in accounts. Several accounts per profile, each with a
type; every transaction belongs to one; and the first forward-only schema
migration (v1→v2) that adds the account link.

This is the test-side contract for [`docs/specs/FIBR-0005.md`](../../../docs/specs/FIBR-0005.md);
each `INV-N` maps to that spec's invariant of the same number. `test_accounts.py`
enforces them. Every on-disk vault uses `tmp_path`; no test touches the network
or real financial data (testing.md § 6).

## Invariants

- **INV-1** — Account CRUD round-trips: `AccountRepository.add` returns the new
  id; `list_all()` returns `Account` records ordered by name (case-insensitive)
  then id; `get` returns the row or `None`; `update` overwrites name+type;
  `delete` removes exactly that row; delete/update of a missing id is an
  idempotent no-op. Source: FIBR-0005 INV-1.
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
  FIBR-0005 INV-7 (a–f).
- **INV-8** — The new modules add no network import and log no secret across an
  account add→delete cycle (covered by the vault-suite whole-`src/` scan plus a
  `caplog` capture here). Source: FIBR-0005 INV-8.

## Out of scope

Editing an existing transaction's account; reassigning/bulk-moving transactions;
per-account currency/opening-balance/institution; import/categorisation/
dashboard/export. See FIBR-0005 § "Out of scope".
