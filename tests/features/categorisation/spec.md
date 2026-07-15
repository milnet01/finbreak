# Feature test contract — categorisation (FIBR-0010, P08)

Enforces `docs/specs/FIBR-0010.md`. The rules engine + manual override +
learning: a user-editable rule set that auto-files transactions into leaf
categories, a per-transaction **manual** override that is never clobbered, a
learning offer when a manual correction disagrees with the rules, and an atomic
delete-category cascade that unwinds and re-files. Schema **v6 → v7**.

Every on-disk vault uses `tmp_path`; no test touches the network or real
financial data (testing.md § 6). Headless layers (matcher, repos, services,
migration) are tested directly; the Home category column / context menu, the
Rules tab, and the blast-radius confirm use the pytest-qt `qtbot` fixture.

The code artifacts use American *categoriz*ation
(`CategorizationService`, `categorization_rules`); this test dir uses British
*categoris*ation per `testing.md`'s `<feature_name>` convention.

| INV | Assertion |
|-----|-----------|
| INV-1 | **Golden rule.** `apply_rules()` recomputes every **auto** row from the current rules and never touches a **manual** row — a manual row keeps its category across an apply that would otherwise match it elsewhere. |
| INV-2 | **First-match.** `categorize(desc, rules)` returns the first (ascending priority, then id) rule whose normalised pattern is a substring of the normalised description; no match / empty rule set → `None`. |
| INV-3 | **Manual survives.** A re-import (dedup keeps existing rows) and any rule run leave a manual row unchanged, including a manual **clear** (`NULL`/`'manual'`) which stays clear after Apply. |
| INV-4 | **When rules run.** Import categorises new rows in the same transaction; adding a rule does **not** re-file existing rows until `apply_rules()` (or the next import). |
| INV-5 | **Learning offer.** After a manual set, the offer fires iff the chosen leaf differs from what the rules would produce: (a) correcting a rule row to a different leaf → offer; (b) categorising a blank row no rule matches → offer; (c) choosing the leaf the rules already produce → no offer; (d) a manual clear → no offer. |
| INV-6 | **New rules win.** `add_rule` inserts at `min_priority() - 1` (top), so a rule added after a broad matching rule sorts first and `categorize` returns the new one; a learned correction outranks the rule it corrects. |
| INV-7 | **Delete cascade (atomic).** Deleting a leaf clears + resets its transactions to auto, deletes its rules, deletes the category, and re-applies — in one transaction; a wedged failure (recategorize raises) leaves everything unchanged and the vault re-openable. |
| INV-8 | **Blast radius.** `CategoryService.delete_blast_radius(id)` returns `(txn_count, rule_count)` over all rows/rules pointing at the category (manual + rule); the UI confirm names both counts and deletes only on Yes (net-new — today's delete has no dialog). |
| INV-9 | **Leaves only.** `add_rule` / `update_rule` reject a root `category_id` (`ValueError`); the `leaf_categories` list excludes the two roots. |
| INV-10 | **Home category column + set.** The Home table has a Category column; the context-menu *Set category…* sets a row **manual** and the cell updates. |
| INV-11 | **Rules tab.** `RulesWidget` lists rules in priority order; add / edit / delete / move up / move down round-trip the order; Apply reports a re-filed count. |
| INV-12 | **No re-dedup.** `apply_rules()` issues only `UPDATE`s — the transaction row count is identical before and after. |
| INV-13 | **Idempotent apply.** A second `apply_rules()` with unchanged rules returns 0 and changes no row. |
| INV-14 | **Auto-lock safety.** A `VaultLockedError` raised from the Home set / Apply / delete slot is caught — the slot returns, no crash. |
| INV-15 | **Schema v6 → v7** (this feature's delta). `LATEST_SCHEMA_VERSION == 9` now (later phases advanced it — v8 is FIBR-0011); a v6 vault walking to latest gains `transactions.category_id` + `category_source` + the `categorization_rules` table at the v6→v7 step, one atomic step (a wedged step leaves a re-openable v6). |
| INV-16 | **No network; i18n.** No network import under the new modules (the vault-suite static scan covers them); user strings via `tr()` (convention/ruff, not a unit test). |

**Edges** (beyond the INV table): `categorize(desc, [])` → `None`;
delete-all-rules-then-Apply blanks every rule-categorised auto row while manual
rows stay; an empty / whitespace description row is left uncategorised;
`normalise_text` collapses whitespace + casefolds and `ImportService._normalise`
delegates to it (byte-identical dedup).
