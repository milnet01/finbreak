# Feature test contract — db_performance (FIBR-0098 / FIBR-0025 / FIBR-0071 / FIBR-0026)

Two coupled database-performance changes shipped together:

1. **Hot-column indexes** (FIBR-0098 / FIBR-0071 / FIBR-0026) — the schema
   carried **no** indexes through v9, so every import-dedup probe, category /
   account count, and statement delete was a full table scan (fine at personal
   scale, degrades on a multi-year vault). A **v9 → v10** forward migration adds
   five indexes on the named hot columns.
2. **SQLite WAL journal mode** (FIBR-0025) — the **live** vault connection runs
   `PRAGMA journal_mode = WAL` so readers no longer block the import writer and
   the UI stays responsive during a long import.

Every on-disk vault uses `tmp_path`; no test touches the network or real
financial data (testing.md § 6). The layers are tested headless.

| INV | Assertion |
|-----|-----------|
| INV-1 | **v9 → v10 migration.** `LATEST_SCHEMA_VERSION == 10`; the step is forward-only, **atomic** (a wedged `CREATE INDEX` rolls back to a re-openable v9 with no partial indexes — the five `CREATE INDEX`es + `UPDATE schema_version` share one owned transaction), **idempotent** (re-run at v10 is a no-op, no duplicate indexes), **baseline-complete** (a fresh first-run vault ends at v10 with all five indexes), and leaves transaction / rule **data** unchanged (a pure-DDL step, no backfill). |
| INV-2 | **The five indexes exist on the named columns and are actually used.** `transactions(account_id, occurred_on, amount_minor)` — the import-dedup `existing_for` probe; its leftmost `account_id` prefix also serves `count_for_account`, so a standalone `account_id` index would be redundant (omitted). `transactions(occurred_on)` — the `list_all` `ORDER BY occurred_on` + date-range filters (**not** covered by the composite: `occurred_on` isn't its leftmost column). `transactions(category_id)` — `count_for_category` + `clear_category_for`. `transactions(statement_period_id)` — `delete_for_statement` / `reassign_account`. `categorization_rules(category_id)` — the rules half of the category-delete count + delete. `EXPLAIN QUERY PLAN` for the dedup probe reports the composite index (a search, not a scan). |
| INV-3 | **WAL on the live connection only.** A vault created via `Vault.create()` runs in `journal_mode = wal`, and opening a pre-WAL vault (created before FIBR-0025, or a just-restored backup DB) **converts** it to WAL. The **transient** restore / backup-assembly connection (`in_memory_temp=True`) keeps the default **rollback** journal — because `backup._install` moves `vault.db` at the file level **without** its `-wal` sidecar, so that connection must stay self-contained, and the security-model's "backup DB rollback journal" guarantee (FIBR-0014 INV-1) is preserved. `synchronous` is left at the default **FULL**, so each commit still fsyncs the WAL and the create() "DB durable before sidecar" ordering (FIBR-0005 INV-5) holds. |
| INV-4 | **WAL data-durability across close/reopen.** A live (WAL) vault's committed data survives a graceful `lock()` (close) + `unlock()` (reopen) — SQLite checkpoints the WAL into `vault.db` on the last-connection close, so `vault.db` is self-contained on disk (the property restore's file-level move relies on). The `-wal`/`-shm` sidecars are SQLCipher-encrypted and gitignored (`*.db-*`, FIBR-0002). |
