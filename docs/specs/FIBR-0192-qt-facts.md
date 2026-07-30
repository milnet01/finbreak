# FIBR-0192 — measured Qt header behaviour (reference)

**Genre: reference.** This is a table of measurements and the two scripts that
reproduce them. Nothing is built *from* it — `docs/specs/FIBR-0192.md` is the
contract, and this file is the evidence it cites. So it is checked by
`/doc-lint`, **not** by `/cold-eyes`; a cold-eyes gate on a measurement table
spends a lane on eleven N/A dimensions.

**Split out of `FIBR-0192.md` on 2026-07-31**, at the end of that spec's third
cold-eyes loop, because the cross-references between these facts and the design
citing them had become the run's largest single source of findings. One home,
one copy.

**Provenance.** All measurements run against the pinned **PySide6 6.11.1** under
`QT_QPA_PLATFORM=offscreen` on 2026-07-30, except **QT-10**, added 2026-07-31.
The source files they concern were last modified at `b676863` (2026-07-28) and
are unmodified since. Re-run both probes on any PySide6 bump — §5's invariants
rest on these, and none of them is inferable from the Qt documentation.

## 1. The facts

**Ids are permanent.** A new fact is **appended** as the next `QT-N`, never
inserted, because `FIBR-0192.md` §4 and §5 cite these ids directly. Do not
renumber, and do not reorder the table to "group related facts" — the ids are
the contract, the order is not.

| Id | Fact | Measured | Why it matters |
|---|---|---|---|
| **QT-1** | `QTableWidget.horizontalHeader().sectionsMovable()` | **False** by default | Asserting `True` on the Forecast table proves `remember_columns` ran. |
| **QT-2** | `QTreeWidget.header().sectionsMovable()` | **True** by default | Asserting `True` on a Home tree proves **nothing** — it passes against a build that never calls `remember_columns`. INV-3 asserts persistence instead. |
| **QT-3** | **`saveState()` serialises the sections-movable flag** | **Yes** | The single most dangerous fact here. A default captured *before* `setSectionsMovable(True)` stores `movable = False`, and restoring it on a reset turns drag-reorder **off** for good. FIBR-0192 §4.2 pins the capture point because of this. |
| **QT-4** | `QHeaderView.restoreState()` emits `sectionResized` / `sectionMoved` | **No** | Restoring a default does not re-trigger the width/order save. |
| **QT-5** | `QHeaderView.restoreState()` and `sortIndicatorChanged` | **Emitted, but the connected slot does not run** — PySide6 raises `TypeError: … parameter 1 of type "Qt::SortOrder" cannot be converted` to stderr instead. Measured identically on `QTableWidget` with sorting off, with sorting on, and on `QTreeWidget`. | So on the pinned PySide6 `remember_columns`' own `_save` **does not run** on a restore — deterministically, not sometimes. The design still does not depend on that, because a future PySide6 that marshals the argument successfully would only write the default state, which is harmless. The `TypeError` on stderr is accepted noise (FIBR-0192 §4.3); the one thing that must **not** be done about it is blocking the signal — see QT-6. |
| **QT-6** | **A sortable view re-sorts its rows on `restoreState` — via `sortIndicatorChanged`, and only if that signal is not blocked** | Unblocked: an ascending default restored over a user's descending sort returns the rows to `['apple','banana','cherry']`. Blocked: the indicator reads Ascending while the rows stay `['cherry','banana','apple']`. | The reason FIBR-0192 §4.3 **forbids** `blockSignals` around the restore. Blocking looks like hygiene and silently desynchronises the sort arrow from the rows on all **five** click-sortable tables. Reproduced by Probe B. |
| **QT-7** | `QTableWidget.horizontalHeader().stretchLastSection()` / `QTreeWidget.header()…` | **False** / **True** by default | Only `transactions_table` sets it explicitly, but every `QTreeWidget` header has it on — so the three new Home trees also re-lay-out on a window resize (FIBR-0192 §4.4 reason 1 applies to them too, and §10's write-amplification note follows from it). |
| **QT-8** | `QTreeWidget.clear()` vs header state | Column count, section widths, header labels **and** the view's dynamic property all survive | `_render_column` calls `col.tree.clear()` on every dashboard refresh. Had it reset the header, INV-3 would fail after any refresh and the whole design would need a different home for the default. |
| **QT-9** | `setProperty` / `property` round-trip of a `QByteArray`; `saveState()` size on an unshown 2-column tree; `findChildren` through one nesting level | equal; **127 bytes**, default section size 100; finds it | FIBR-0192 §4.2's storage mechanism, §10's figure, and §4.3's reach into the dashboard's `QScrollArea`. |
| **QT-10** | **`saveState()` also serialises the SORT INDICATOR** — its section, its order, and whether it is shown | Restoring a capture taken **before** `setSortingEnabled(True)` leaves `isSortIndicatorShown()` **False** — the arrow disappears. Restoring one taken after brings the indicator's section and order back with it. `stretchLastSection` and the section resize mode, by contrast, are **not** in the state — restoring a capture taken before either was changed leaves both as they are. | The **second** flag with QT-3's shape, and the reason FIBR-0192 §4.2's capture must also follow `enable_sorting`. QT-3 and QT-10 together are the whole precondition: capture after every call that configures the header, not merely after the columns exist. |

## 2. Three of these killed a defect that had survived a careful read

**QT-2** would have shipped a vacuous invariant — a "columns are movable" clause
on the trees reads exactly like the Forecast one and tests nothing. **QT-3**
would have shipped a silent, app-wide regression. **QT-6** refuted a
`blockSignals` guard argued for on hygiene grounds; it would have desynchronised
the sort arrow from the rows on five shipped tables. None of the three is
inferable from the Qt documentation, and all three read as reasonable until run.

**QT-10** is the same story a fourth time, found one loop later: the design had
pinned the capture point against QT-3's flag and assumed no other flag was in
the state.

## 3. Probe B — the sort-restoration fact (QT-6)

The one that forbids `blockSignals`. Kept separate because it needs seeded rows:

```
QT_QPA_PLATFORM=offscreen python - <<'PY'
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
app = QApplication([])
def rows(t): return [t.item(r,0).text() for r in range(t.rowCount())]
def build():
    t = QTableWidget(0, 2); t.setRowCount(3)
    for r, n in enumerate(["banana","apple","cherry"]):
        t.setItem(r,0,QTableWidgetItem(n)); t.setItem(r,1,QTableWidgetItem("x"))
    t.setSortingEnabled(True); t.sortByColumn(0, Qt.SortOrder.AscendingOrder); return t
for label, block in (("BLOCKED", True), ("UNBLOCKED", False)):
    t = build(); h = t.horizontalHeader(); default = h.saveState()
    t.sortByColumn(0, Qt.SortOrder.DescendingOrder)      # the user re-sorts
    if block:
        h.blockSignals(True)
        try: h.restoreState(default)
        finally: h.blockSignals(False)
    else:
        h.restoreState(default)
    print(label, rows(t), "| indicator:", h.sortIndicatorOrder().name)
PY
# BLOCKED   ['cherry', 'banana', 'apple'] | indicator: AscendingOrder   <- arrow lies
# UNBLOCKED ['apple', 'banana', 'cherry'] | indicator: AscendingOrder   <- rows follow
```

**The seeding is what makes this probe able to fail.** An earlier version built
its default state with a Descending indicator already set, so blocked and
unblocked produced identical rows and the probe reported "no difference" against
a real difference. The rows must be seeded so that the *default* sort order and
the *user's* sort order disagree, or the probe proves nothing.

## 4. Probe A — QT-1..QT-5, QT-7, QT-9

```
QT_QPA_PLATFORM=offscreen python - <<'PY'
from PySide6.QtWidgets import QApplication, QTableWidget, QTreeWidget, QWidget, QVBoxLayout
app = QApplication([])
t = QTableWidget(0, 4); tr = QTreeWidget(); tr.setColumnCount(2)
print("movable   :", t.horizontalHeader().sectionsMovable(), tr.header().sectionsMovable())
print("stretch   :", t.horizontalHeader().stretchLastSection(), tr.header().stretchLastSection())
# movable flag is IN the serialised state:
pre = t.horizontalHeader().saveState()
t.horizontalHeader().setSectionsMovable(True)
t.horizontalHeader().restoreState(pre)
print("movable after restoring a pre-flag capture:", t.horizontalHeader().sectionsMovable())
d = tr.header().saveState(); calls = []
tr.header().sectionResized.connect(lambda *a: calls.append("resized"))
tr.header().sectionMoved.connect(lambda *a: calls.append("moved"))
tr.header().sortIndicatorChanged.connect(lambda *a: calls.append("sort"))
tr.header().resizeSection(0, 321); tr.header().moveSection(0, 1)
calls.clear()
tr.header().restoreState(d)          # <- the only action measured below
print("handler calls on restore:", calls)
print("width0 back to:", tr.header().sectionSize(0), "| state bytes:", len(bytes(d)))
tr.setProperty("p", d); print("property round-trip:", bytes(tr.property("p")) == bytes(d))
root = QWidget(); lay = QVBoxLayout(root); inner = QWidget()
il = QVBoxLayout(inner); il.addWidget(tr); lay.addWidget(inner)
print("findChildren through nesting:", len(root.findChildren(QTreeWidget)))
PY
# TypeError: Cannot call meta function "slot(int, Qt::SortOrder)" because
#   parameter 1 of type "Qt::SortOrder" cannot be converted.     <- on stderr
# movable   : False True
# stretch   : False True
# movable after restoring a pre-flag capture: False
# handler calls on restore: []
# width0 back to: 100 | state bytes: 127
# property round-trip: True
# findChildren through nesting: 1
```

Read that output carefully, because the interesting part is on **stderr**. The
restore re-applies the width (100) while invoking **no** handler —
`sectionResized` and `sectionMoved` are genuinely not emitted, and
`sortIndicatorChanged` *is* emitted but its slot dies in PySide6's argument
conversion. Blocking the header's signals removes that `TypeError` — and Probe B
shows what else it removes, which is why FIBR-0192 §4.3 forbids it.

## 5. Probe C — QT-10, and what is *not* in the state

```
QT_QPA_PLATFORM=offscreen python - <<'PY'
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QHeaderView
app = QApplication([])
def build():
    t = QTableWidget(0, 3); t.setRowCount(3)
    for r, n in enumerate(["banana","apple","cherry"]):
        for c in range(3): t.setItem(r,c,QTableWidgetItem(n if c==0 else "x"))
    return t
# the sort INDICATOR (section + order) is in the state:
t = build(); h = t.horizontalHeader()
t.setSortingEnabled(True); t.sortByColumn(0, Qt.SortOrder.AscendingOrder)
default = h.saveState()
t.sortByColumn(2, Qt.SortOrder.DescendingOrder)
h.restoreState(default)
print("indicator after restore:", h.sortIndicatorSection(), h.sortIndicatorOrder().name)
# ...and so is whether it is SHOWN — capture before enable_sorting and it hides:
t2 = build(); h2 = t2.horizontalHeader()
pre = h2.saveState()                      # captured with sorting OFF
t2.setSortingEnabled(True)
print("indicatorShown with sorting on            :", h2.isSortIndicatorShown())
h2.restoreState(pre)
print("indicatorShown after restoring pre-sorting:", h2.isSortIndicatorShown())
# resize mode and stretchLastSection are NOT in the state:
t3 = build(); h3 = t3.horizontalHeader()
h3.setSectionResizeMode(QHeaderView.ResizeMode.Interactive); h3.setStretchLastSection(False)
pre3 = h3.saveState()
h3.setStretchLastSection(True); h3.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
h3.restoreState(pre3)
print("stretch after restoring pre-stretch capture:", h3.stretchLastSection(),
      "| resizeMode(0):", h3.sectionResizeMode(0).name)
PY
# indicator after restore: 0 AscendingOrder
# indicatorShown with sorting on            : True
# indicatorShown after restoring pre-sorting: False      <- the arrow vanishes
# stretch after restoring pre-stretch capture: False | resizeMode(0): Interactive
```

The last line is the negative half and it matters as much as the positive one:
`stretchLastSection` and the resize mode are **not** restored, so the capture
point does not have to follow those calls. Only the two flags — movable (QT-3)
and the sort indicator (QT-10) — impose the ordering FIBR-0192 §4.2 requires.
