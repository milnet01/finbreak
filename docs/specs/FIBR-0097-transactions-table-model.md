<!-- ants-spec-format: 1 -->
# FIBR-0097 — Back the Transactions table with a model so it builds only the rows on screen

**Status:** accepted (2026-10-22).
**Kind:** perf.
**Source:** ROADMAP FIBR-0097 (claude-suggestion-2026-07-11); FIBR-0028
(user-request-2026-07-01) was dropped into it as a duplicate on 2026-10-19.

**Layman:** Opening the Transactions tab no longer freezes the window for a
second or more once you have years of history; the list looks and behaves
exactly as before.

## 1. Goal

After this ships, `TransactionsView` shows its rows through a `QTableView`
over a Python `QAbstractTableModel`. A refresh formats only the cells Qt asks
to paint, and a header-click sort reorders a Python list instead of comparing
`QTableWidgetItem`s. Every cell shows the same text, colour and tooltip it
shows today; sorting, selection, remembered columns, Reset layout, copy and
the lock wipe behave as they do now.

## 2. Problem

`TransactionsView._apply_filters` builds six `QTableWidgetItem`s per
transaction and formats every date and amount up front, then Qt re-sorts all
of them through `SortableItem.__lt__`, a Python call per comparison.

Measured 2026-10-19 (offscreen, one account, `TransactionsView.refresh()`
plus `processEvents()`, best of 3, a throwaway script over the project's own
`AuthService.first_run` vault):

| Transactions | refresh |
|---|---|
| 2,000 | 134 ms |
| 20,000 | 1,474 ms |
| 50,000 | 4,128 ms |

cProfile at 20,000 put about a third of it in `_amount._format_amount`, about
a quarter in the sort, and the rest in item construction and `setItem`.
`refresh()` runs on every activation of the tab (FIBR-0012 INV-10), so the
freeze recurs each time the user opens it.

It is the only table whose rows grow with the user's history. Statements,
Rules, Accounts, Transfers, Recurring and Forecast list dozens of rows.

## 3. Scope decisions (agreed with the user)

None — the user's priority list delegates the order and shape of open perf
work, and every choice below follows from § 2. Two were judgement, recorded
here so they are not re-argued:

- **The Transactions view only** (developer's call, 2026-10-19). The other
  tables keep `QTableWidget` and `_table_state`'s tag helpers.
- **No proxy model** (§ 8).

## 4. Design

### 4.1 The model

A new `TransactionsModel(QAbstractTableModel)` in `src/finbreak/ui/transactions.py`
beside the view — the view is its only user.

```python
class TransactionsModel(QAbstractTableModel):
    def set_rows(self, rows: list[tuple[Transaction, Decimal, str, str]],
                 render: _Render) -> None: ...   # beginResetModel/endResetModel
    def row_at(self, row: int) -> tuple[Transaction, Decimal, str, str]: ...
    def rowCount(self, parent=QModelIndex()) -> int: ...
    def columnCount(self, parent=QModelIndex()) -> int: ...   # 6
    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> object: ...
    def headerData(self, section, orientation, role=...) -> object: ...
    def sort(self, column: int, order: Qt.SortOrder = ...) -> None: ...
```

`_Render` is a frozen dataclass the view builds once per fill: the date
format, the `AmountPrefs`, the base-currency code (`base_currency()`), the transfer-label map, and
the translated strings (§ 4.4). The model holds no reference to a service or
the vault.

`data` answers, per column, exactly what `_apply_filters` and
`_category_cell` set today:

| Column | `DisplayRole` | Other roles | Sort key |
|---|---|---|---|
| `_COL_DATE` | `format_date(occurred_on, date_format)` | — | `occurred_on` (ISO string) |
| `_COL_AMOUNT` | `_format_amount(display, symbol, negative_style)` | `ForegroundRole`: `_NEGATIVE_TEXT` / `_POSITIVE_TEXT` when colour is on and the amount is non-zero, else `None` | `display` (`Decimal`) |
| `_COL_CURRENCY` | the base-currency code | — | display text |
| `_COL_DESCRIPTION` | `description` | — | display text |
| `_COL_ACCOUNT` | the account name | — | display text |
| `_COL_CATEGORY` | the transfer label, else the "~ guess" form for a `library` row with a name, else the name | `ToolTipRole`: the guess tooltip on a guess row | the transfer label, else the bare name |

Any other role returns `None`. An index outside the rows returns `None`.

### 4.2 Sorting

`QTableView.setSortingEnabled(True)` (through `enable_sorting`) calls
`model.sort(section, order)` on a header click, on `restoreState`'s
`sortIndicatorChanged` (FIBR-0192-qt-facts.md QT-5), and once when sorting is
enabled. `sort`:

1. emits `layoutAboutToBeChanged`;
2. sorts the shared row list in place with `list.sort(key=…,
   reverse=descending)`, which is stable in both directions, so tied rows keep
   their current relative order — as the current table's sort does;
3. remaps every persistent index from its old row to its new one
   (`changePersistentIndexList`), so the selection stays on the same
   transaction;
4. emits `layoutChanged`.

The default stays Date, newest first: the header's initial indicator is
section 0, descending, for `QTableWidget` and `QTableView` alike (measured
2026-10-19, PySide6 6.11.1).

`set_rows` resets the model and then sorts by the header's current indicator,
so a refill keeps the user's sort. A reset drops the selection, which is what
`fill_guard`'s clear gives the current table.

### 4.3 The view's seams

- `_build_table` returns a `QTableView` with the same `objectName`
  (`transactions_table`), edit triggers, selection behaviour, selection mode,
  stretch and resize mode, context-menu policy and the same call order, with
  `remember_columns` still last (FIBR-0192 § 4.2). `setModel` comes before
  every header call: a `QTableView` header has no sections until it has a
  model, so `remember_columns` would capture an empty default.
- `self._rows` stays the filtered list, and the model holds that same list
  object — sorted in place — so `_rows[i]` is the transaction on view row `i`.
  `_selected_txn` reads the selected row from the selection model; `_select_txn`
  clears the selection, then selects the row holding that id.
- `_on_copy_amount` copies the selected row's Amount `DisplayRole`, the text
  the column renders (FIBR-0032 INV-2 and INV-8: no vault read).
- `clear_rows` empties `_master` and `_rows` **and resets the model to no
  rows and no `_Render`**, as it empties `_transfer_labels` today: the
  transfer-label map names accounts. `main_window._clear_decrypted_rows` already calls it by duck type;
  its `QTableWidget` branch does not reach a `QTableView` and does not need to.
- `set_datetime_prefs` / `set_amount_prefs` refill as they do now.

### 4.4 Translated strings stay in the view

The headers, the `"{category} ~ guess"` template and the guess tooltip stay
literal `self.tr(...)` calls in `TransactionsView`, evaluated once per fill
into `_Render`. Moving them into the model would change their translation
context from `TransactionsView` to `TransactionsModel`, and
`tests/features/i18n/test_translatable_strings.py` requires the literal
argument shape they already have.

### 4.5 `_table_state`

`_header_of`, `remember_columns`, `enable_sorting` and `reset_columns` accept a
`QTableView`. `QTableWidget` subclasses `QTableView`, so `reset_columns`
switches `findChildren(QTableWidget)` to `findChildren(QTableView)` and still
reaches every table it reaches today. `SortableItem`, `fill_guard`, `tag_row`,
`selected_index` and `select_by_index` are unchanged; the other tables still
use them.

## 5. Invariants

- **INV-1 — Every cell reads as it does today.** For each column in § 4.1's
  table, the model's `DisplayRole`, `ForegroundRole` and `ToolTipRole` equal
  what the current table's item carries for the same row and preferences:
  date format, negative style, colour on and off, the "~ guess" marker and
  tooltip, a transfer leg's label.
  *Test:* the existing assertions on cell text, foreground and tooltip in the
  suites § 7 lists, migrated to read the model, with their expected values
  unchanged.
  *Breaks when:* a role is answered differently — a `ForegroundRole` returned
  with colour off (FIBR-0105 INV-4), a guess marker dropped, a date formatted
  without the user's preference.

- **INV-2 — A refresh formats only what is painted.** With 2,000 transactions
  in a shown 1200×800 view, `refresh()` followed by `processEvents()` calls
  `_format_amount` fewer than 200 times.
  *Test:* `tests/features/transactions_tab/test_transactions_tab.py::test_FIBR0097_refresh_formats_only_painted_rows`
  — counts calls through a wrapper on the view module's `_format_amount`. The
  current table makes 2,000, one per row, so it is red before the change.
  *Breaks when:* `set_rows` or `sort` formats every row, or the view asks the
  model for every row's text (a `ResizeToContents` mode on either header).

- **INV-3 — Sorting orders by the same keys.** A header sort on each column
  orders the rows by § 4.1's sort key; tied rows keep their current relative
  order in both directions; the default is Date, newest first.
  *Test:* `test_FIBR0097_each_column_sorts_by_its_key` — a fixture where text
  order and key order disagree in every keyed column (display amounts
  `-1000.00`, `200.00`, `30.00`; dates across a year boundary; one guess row and one plain row of the
  same category, plus a category whose name sorts between that name and its
  "~ guess" form; two rows on one day), sorted both ways per column.
  *Breaks when:* amounts sort as text, a guess row sorts apart from its plain
  siblings, or the sort is unstable.

- **INV-4 — The selection follows its transaction through a sort, and a refill
  clears it.** Select transaction T, sort by any column: `_selected_txn()` is
  T. Then change a display preference: `_selected_txn()` is `None`.
  *Test:* `test_FIBR0097_selection_survives_a_sort_and_not_a_refill`.
  *Breaks when:* `sort` reorders without remapping persistent indexes, so the
  selection stays on a row number and the next action lands on another
  transaction (the class `fill_guard`'s docstring measured).

- **INV-5 — A lock leaves no decrypted value in the model.** After
  `main_window._clear_decrypted_rows(tab)`, the model reports no rows and no
  Python attribute of it holds a decrypted value.
  *Test:* `tests/features/app_shell/test_lock_wipe.py`'s `_survivors` also
  scans the Python attributes of each item view's model;
  `test_row30_lock_leaves_no_decrypted_value_in_any_tab` then covers this tab.
  The widened scan is seen to fail against a `clear_rows` that makes the
  model report no rows but leaves it holding the old list or `_Render`.
  *Breaks when:* `clear_rows` drops the view's lists but leaves the model
  holding the old list or `_Render`, which `_model_texts` cannot see once `rowCount()` is 0
  — so a reset that only zeroes the count must also fail.

- **INV-6 — Remembered columns and Reset layout still reach this table.**
  Widths, order and sort persist under `columns/transactions_table`; Reset
  layout restores the build-time default and the rows re-sort to it; a saved
  5-section header still yields 6 columns without an error (FIBR-0153 INV-9).
  *Test:* `tests/features/table_state/test_table_state.py` and the FIBR-0153
  INV-9 test in `test_transactions_tab.py`, with their lookups changed from
  `QTableWidget` to `QTableView`. `test_table_state.py`'s `_sort_keys` reads
  each row's § 4.1 sort key from the view's `_rows`, in order.
  *Breaks when:* `reset_columns` still searches for `QTableWidget` only, which
  skips this table.

- **INV-7 — Copy amount copies the rendered text.** "Copy amount" puts the
  selected row's Amount `DisplayRole` on the clipboard, with no vault read,
  including after a lock.
  *Test:* `tests/features/clipboard/test_clipboard.py`, migrated.
  *Breaks when:* the handler re-formats from the `Decimal` with other
  preferences, or reads the vault.

## 6. Failure modes

- **Preferences change while the tab is open.** The setters refill, so `_Render`
  is rebuilt; no cached text outlives a preference.
- **`data` called for an index past the rows** — a view repainting between a
  reset and its layout. It returns `None`, never raises.
- **A lock while the context menu is open.** `clear_rows` resets the model;
  the selection is gone, so `_selected_txn()` is `None` and the copy handlers
  return without copying, as they do today on an empty table.
- **A saved header from the `QTableWidget` build.** `saveState` belongs to the
  header, not the view type, so the existing `columns/transactions_table` blob
  restores unchanged. Nothing migrates.
- **Mixed key types in one column.** Each column's key has one type for every
  row (§ 4.1); an uncategorised row's key is `""`, not `None`.

## 7. Tests

| Invariant | Test |
|---|---|
| INV-1 | the cell-text, foreground and tooltip assertions in `transactions_tab`, `datetime_display`, `category_library`, `transfers`, `accounts` and `clipboard`, migrated to the model |
| INV-2 | `test_transactions_tab.py::test_FIBR0097_refresh_formats_only_painted_rows` (new) |
| INV-3 | `test_transactions_tab.py::test_FIBR0097_each_column_sorts_by_its_key` (new) |
| INV-4 | `test_transactions_tab.py::test_FIBR0097_selection_survives_a_sort_and_not_a_refill` (new) |
| INV-5 | `test_lock_wipe.py::test_row30_lock_leaves_no_decrypted_value_in_any_tab`, with `_survivors` widened |
| INV-6 | `table_state/test_table_state.py`; `test_transactions_tab.py`'s FIBR-0153 INV-9 test |
| INV-7 | `clipboard/test_clipboard.py` |

INV-2 is written first and seen red: it counts 2,000 calls against the
current table. INV-5's widened scan finds no Python model to scan until the
model exists, so it is seen red after the build, against the `clear_rows`
INV-5 names. INV-3 and INV-4 pass against the current
table too, which sorts by the same keys, stably, and clears the selection on
a refill. They are written first as parity locks.

A `perf`-marked test (`test_FIBR0097_refresh_scales_with_painted_rows`) prints
the refresh time at 2,000 and 20,000 rows. At 20,000 it asserts the refresh
takes under 4 times as long as `list_transactions()` alone, timed in the same
test. Measured 2026-10-19 at 20,000: `list_transactions()` 41 ms, the current
refresh 1,499 ms, and a refresh whose fill builds no items 91 ms. The ratio
between the two sizes is no test: the vault read, the filter and the sort
still grow with the rows. The gate excludes `perf` (testing.md § 3.4).

Test call sites that read the table move from `item(r, c)` to
`model().index(r, c).data(role)`, from `rowCount()` to `model().rowCount()`,
and from `sortItems(c)` to `sortByColumn(c, Qt.SortOrder.AscendingOrder)`.
`conftest.cell_text` accepts a `QTableView` and still fails on a missing cell
(FIBR-0331).

## 8. Alternatives considered (and rejected)

- **`QSortFilterProxyModel` over the model.** Its `lessThan` compares the
  sort-key `QVariant`s; a `Decimal` key is a Python object, so every
  comparison calls back into Python — the cost § 2 measures. The filter is
  already a Python pass over `_master`, so the proxy would add a layer and
  remove nothing.
- **All ten tables.** The others hold dozens of rows; migrating them buys no
  measurable time and widens the change to every tab's tests.
- **Speeding up the current fill.** Caching `_locale_digits`' ten `toString`
  calls was measured on 2026-10-19 at about 6% and reverted. The rest is per-item
  cost no cache removes.
- **`fetchMore` / incremental loading.** A sort needs every row, so the list
  is loaded whole anyway; it is the formatting and item construction that cost.

## 9. Out of scope

- The other `QTableWidget` tables — deferred; not yet queued.
- The filter pass over `_master`, which stays O(n) per keystroke — deferred;
  not yet queued. It was not the measured cost.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | the migrated assertions § 7 lists |
| INV-2 | `test_FIBR0097_refresh_formats_only_painted_rows` |
| INV-3 | `test_FIBR0097_each_column_sorts_by_its_key` |
| INV-4 | `test_FIBR0097_selection_survives_a_sort_and_not_a_refill` |
| INV-5 | `test_row30_lock_leaves_no_decrypted_value_in_any_tab` with the widened `_survivors` |
| INV-6 | `table_state/test_table_state.py`; the FIBR-0153 INV-9 test |
| INV-7 | `clipboard/test_clipboard.py` |
| § 4.4 strings stay literal `tr()` calls in the view | **`Partial:`** `test_translatable_strings.py` catches a non-literal argument; nothing catches a literal moved into another class, which changes its context |
| § 2's measurements | **`Partial:`** the `perf` test reprints the 2,000 and 20,000 figures; the 50,000 figure and the cProfile split are not reprinted |

## 11. Cross-doc impact

- `docs/specs/FIBR-0153.md` INV-9 — names "`QTableWidget(0, 6)` construction";
  gains a pointer that the model's six columns now play that part (FIBR-0097
  INV-6).
- `docs/specs/FIBR-0032.md` INV-2 — names `item(row, _COL_AMOUNT).text()`;
  gains a pointer to INV-7 here.
- `tests/features/transactions_tab/spec.md` and
  `tests/features/table_state/spec.md` — any row naming the transactions
  `QTableWidget` gains the same pointer.
- `src/finbreak/ui/_table_state.py`'s module docstring — says
  "Reusable ``QTableWidget`` behaviour"; it now also serves one `QTableView`.
- `CHANGELOG.md` — a `Changed` entry at release.

## 12. Cold-eyes loop log

Rows live in `../reviews/FIBR-0097-transactions-table-model-loop-log.md`.

## 13. Resource cost

Less memory than today: six `QTableWidgetItem`s per row go, and the model
holds the filtered list the view already keeps (`_rows`), not a copy. No new
dependency.
