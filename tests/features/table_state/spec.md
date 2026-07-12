# Feature test contract — table state (FIBR-0117)

Enforces the reusable `ui/_table_state.py` behaviour shared by the list tables:
click-a-header to sort (second click toggles ascending/descending), and remembered
column widths across sessions.

| # | Assertion |
|---|-----------|
| 1 | **Numeric sort key.** `SortableItem("112", 112)` sorts *after* `SortableItem("69", 69)` — numerically, not lexically ("112" < "69" as text would be wrong). |
| 2 | **Tag survives reorder.** After `tag_row`, `selected_index` returns the tagged parallel-list index of the selected row — so a row's action target is correct even when the visual order differs from insertion order. |
| 3 | **Action targets the sorted row.** In the Transfers tab, seeding two pairs (100.00, 500.00) then sorting Amount **descending** and confirming the top visual row confirms the **500.00** pair (the sorted row), not the insertion-order first row. This is the correctness guard: a wrong row→action map in a money app is unacceptable. |
| 4 | **Widths remembered.** Resizing a column then rebuilding the widget restores that column's width (persisted to the window settings INI, keyed by the table's objectName — never the vault). |
| 4b | **Sort remembered.** The chosen sort column + direction also persist across a rebuild — the restored header re-sorts the rows (not just the indicator arrow), since header `saveState/restoreState` carries the sort indicator and `fill_guard`'s re-enable re-applies it. |
| 5 | **Sorting is off where order is semantic.** The Rules table (priority-ordered, Move up/down) is **not** click-sortable, but still remembers its column widths. |

Every on-disk vault uses `tmp_path`; the column-state INI is redirected to `tmp`
by the autouse `window_ini` fixture, so no test writes the real per-user settings.
