# Feature test contract — categories (FIBR-0006, P04)

Enforces `docs/specs/FIBR-0006.md`. The Type → Category tree: a
self-referential `categories` table (two seeded Income/Expenditure
**root** rows + ~16 default categories under them), its repository +
service (CRUD, sibling-name validation, delete/root guards), the
category-manager `QTreeWidget` screen, and the **v2→v3** forward
migration that creates + seeds the table.

Every on-disk vault uses `tmp_path`; no test touches the network or real
financial data (testing.md § 6). Headless layers are tested directly;
the manager round-trips (INV-7) use the pytest-qt `qtbot` fixture.

| INV | Assertion |
|-----|-----------|
| INV-1 | Category CRUD round-trips (repo → service); deterministic order (roots first, then name ci, then id); missing-id update/delete are no-ops. |
| INV-2 | `CategoryKind` = exactly `{income, expenditure}`; the two roots carry those tokens verbatim; every descendant carries `kind = NULL`. |
| INV-3 | Name is non-empty (trimmed) and unique **among siblings** (same parent, ci); update excludes the row's own name; the same name under a *different* Type is allowed. |
| INV-4 | v2→v3 migration is forward-only, **atomic** (a failure mid-seed rolls back to v2 with no `categories` table), **idempotent** (re-run is a no-op, no dup roots/defaults), **baseline-complete** (a fresh first-run vault ends at v3 with the tree seeded), and leaves `transactions`/`accounts` unchanged. |
| INV-5 | Exactly two roots (`parent_id IS NULL`, distinct kinds); every seeded default is a child of a root; a category under a non-existent parent raises `IntegrityError` (FK, on a `Vault`-opened connection); `add_category(None,…)`/`update_category(…,None)` raise `ValueError`; editing a **root** raises `ProtectedCategoryError` — so the root count can never change through the service. |
| INV-6 | Delete guard: a root → `ProtectedCategoryError`; a category with ≥1 child → `CategoryHasChildrenError` (nothing removed); a childless non-root deletes cleanly; a missing id is a no-op. |
| INV-7 | Manager UI (`qtbot`): the tree shows two Type nodes (translated labels ↔ `kind`) with the seeded categories; add under a Type appears in that branch; selecting a category loads it into the form; Update renames/re-parents it; delete a childless category removes it; selecting a **root** disables Update + Delete. |
| INV-8 | No network import under `src/finbreak/` (the existing vault-suite static scan covers the new modules); a category add → update → delete cycle logs no password/key bytes. |
