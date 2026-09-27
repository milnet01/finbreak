## Chunk T06: 4 files read

Line counts as read from disk:
- tests/features/accounts/test_accounts.py: 1704
- tests/features/accounts/test_migration_v13.py: 226
- tests/features/statements/test_statements.py: 1968
- tests/features/transactions_tab/test_transactions_tab.py: 567

`tests/features/accounts/` contains only those two `.py` files.

**What I had before reading the subject:** the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, finbreak's `CLAUDE.md`, the finbreak memory index (it includes the isVisible/waitUntil traps, which the shared context also gives), and a git snapshot at HEAD 52e5162. I read the subject from disk.

**Tools:** `workspace_search` hit its rate limit once, so I used `Grep` for the last two lookups.

**One-hop reads:** `tests/conftest.py` (the `paths` and `window_ini` fixtures), `ui/statements.py::_confirm_text`, `ui/accounts.py` (`_on_add`, `_on_forget_password`, the "off by" text), `ui/transactions.py` (`_select_txn`, `_selected_txn`, `_on_set_category`, `_apply_category`), `services/statements.py::list_statements`, and the `main_window` `_count` text.

### Findings

**[HIGH] [dim 1] tests/features/statements/test_statements.py:1879** (also :1852)
> assert "shared" in text.lower() and "staying" in text.lower(), (
>     f"states the loss is total, not that anything survives: {text!r}"

:1852 has the same problem:
> assert "shared" in total.lower(), (

Consequence: two branches of `ui/statements.py::_confirm_text` contain both words.
- The partial-share branch reads "…the rest are shared with a statement that is staying, and will survive with it."
- The total-loss branch reads "Nothing is shared with a statement that is staying…".

So both assertions pass when Delete all, or a `kept == 0` batch, shows the wording that says rows survive. That is exactly the case the assertion message says it rules out. For example, if the branch order is broken or `kept` is miscomputed as non-zero, the user is told shared transactions will survive a delete that destroys all of them, and both tests stay green.

Fix: assert on text only the total-loss branch carries ("every one of" / "Nothing is shared"), and assert "will survive" is absent.

**[MEDIUM] [dim 1] tests/features/accounts/test_accounts.py:1123** (the seeding runs to :1151; the assertion is at :1168)
> off = svc.add_account("AAoff", "current").id  …  "BBquiet" … "CCquietkey" … "DDgood" … "EEgoodkey"

Consequence: the names were chosen so that alphabetical order is the expected severity order, [0,1,1,2,2]. `list_all()` fills the table name-ascending, and Qt's item sort is stable. So a Status sort key that is constant or missing on every row leaves rows in name order, and `ranks == [0, 1, 1, 2, 2]` still passes. Only a sort on the literal display string fails. A broken severity key goes unnoticed.

Fix: name the accounts so that name order differs from rank order (for example, the reconciled accounts sort first by name).

**[MEDIUM] [dim 1] tests/features/transactions_tab/test_transactions_tab.py:434**
> view._select_txn(coffee)
> # The tag is over the FILTERED list, so the selection resolves to the right txn.
> assert view._selected_txn().id == coffee

Consequence: `_select_txn` (index into `_rows`, then `select_by_index`) and `_selected_txn` (`selected_index`, then `_rows`) are inverses through the same mapping. The round trip passes even if the mapping selects a visual row showing a different transaction. The user-visible failure is Set category acting on a row other than the highlighted one, and this test cannot see it. The accounts sibling does check this (test_accounts.py:1272, `_names(widget)[widget._table.currentRow()] == target`).

Fix: also assert that the Description cell of `currentRow()` is "Zzz late coffee".

**[MEDIUM] [dim 1] tests/features/transactions_tab/test_transactions_tab.py:250** (same shape at test_accounts.py:594)
> monkeypatch.setattr(view._categorization, "set_manual_category", _boom)
> …
> view._on_set_category()  # must not raise

Consequence: this test has no assertions at all, and nothing proves `_boom` ran. `_on_set_category` returns early when nothing is selected, and it reaches `set_manual_category` only through `show_modal` and the picker stub. If either step stops driving (lost selection, changed modal wiring), the test passes without exercising the `VaultLockedError` guard.

test_accounts.py:594 has the same weakness: if `_on_add` ever calls a different service method, the patch does nothing, a real add succeeds, `_error.text() == ""` still holds, and the test stays green.

Not affected: test_accounts.py:614 (its `committed == []` would catch a real add) and test_statements.py:1096 (a real move would make the count 0).

Fix: have each raising stub record that it was called, and assert it was.

**[LOW] [dim 1] tests/features/accounts/test_accounts.py:1183**
> assert "500" in off_text, "the discrepancy magnitude is rendered"

Consequence: the expected discrepancy is 50_000 minor units, which is 500.00. The substring also matches wrong magnitudes such as "1 500.00", "500.01" or "5500.00". A cents-level or off-by-thousands error in a money figure passes.

Fix: compare `off_text` exactly with "⚠ off by " followed by the shared money formatter's output for 50_000.

### Pre-pass verdicts
- test_statements.py:503 `setenv`: false positive. `monkeypatch.setenv` is function-scoped and restored at teardown, and `XDG_CURRENT_DESKTOP` is only read while the window is built inside the same test.
- test_statements.py:516 `setenv`: false positive, for the same reason.

### Dimensions scanned
- **1:** 5 findings (1 HIGH, 3 MEDIUM, 1 LOW).
- **4:** settled by the orchestrator. Nothing in these files contradicts it; no same-name test redefinitions seen.
- **5:** clean.
  - The one `qtbot.wait(50)` (test_accounts.py:1485) only has to let time pass. A longer wait under load cannot break any of the assertions after it.
  - No `waitUntil`, no network, no `isVisible` assertion in the chunk.
- **6:** clean.
  - The window INI goes to `tmp_path` through the autouse `window_ini` fixture, and that also covers the reveal test's `paths.window_settings_path()` read.
  - Vaults live under `tmp_path`, including INV-13's second `loop.db`.
  - QMessageBox and service patches go through `monkeypatch`.
  - Module-level constants are never mutated.
- **7:** clean. Fixed dates throughout; `list_statements` orders by `imported_at, id` ascending, which is deterministic for sequential imports.
- **8:** N/A. No skip or xfail markers in the chunk.
- **9:** N/A. No production resources.
- **11:** clean. No empty bodies. The tests with no assertion are `must not raise` checks, filed under dim 1 where their reach is unproven.
- **12:** one test over 1 s (test_INV11_import_done_rebuilds_workspace_lands_on_statements, 1.78 s). The baseline timing does not say which setup step costs the time, so there is no fix shape and no finding.
- **14:** clean. No `filterwarnings`, no swallowed assertions. The patched layers are dialogs and error injectors, not the subject under test.
- **15:** N/A. Nothing failing in this chunk.

### Noted, not mine
- Nothing in the code under test looked wrong.

### Possibly wider
- The pattern "a raising stub whose call is never asserted" (`VaultLockedError` swallow tests) probably also appears in other tabs' suites outside this chunk.
- The pattern "a select/selected round trip through one shared mapping, with no visible-row check" may exist in other tabs that use `_table_state.select_by_index` / `selected_index`.

### Open questions
- Dim 12: attributing test_INV11_import_done's 1.78 s (wizard construction vs. workspace rebuild) needs a profiled run, for example `pytest --durations=0` with `-p cProfile` on that node id.
- The INV-9 status-sort finding assumes Qt's `QTableWidget` sort is stable when keys are equal. Confirming it needs a run where every row's sort-key role is set to the same value, to check that the test stays green.