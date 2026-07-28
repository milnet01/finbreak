import sys
sys.path.insert(0, "src")
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt
from finbreak.ui._table_state import enable_sorting, fill_guard, tag_row, selected_index

app = QApplication([])
ROWS = ["Alpha", "Mid", "Zed"]   # list_all() ORDER BY name COLLATE NOCASE, id

def build():
    t = QTableWidget(0, 5)
    enable_sorting(t)
    return t

def refresh(t):
    with fill_guard(t):
        t.setRowCount(len(ROWS))
        for row, name in enumerate(ROWS):
            for col in range(5):
                t.setItem(row, col, QTableWidgetItem(name if col == 0 else ""))
            tag_row(t, row, row)

for sel_row in (0, 1, 2):
    t = build()
    refresh(t)
    t.sortItems(0, Qt.SortOrder.DescendingOrder)
    order_before = [t.item(r, 0).text() for r in range(3)]
    t.selectRow(sel_row)
    before = selected_index(t)
    refresh(t)
    after = selected_index(t)
    order_after = [t.item(r, 0).text() for r in range(3)]
    b = ROWS[before] if before is not None else "NONE"
    a = ROWS[after] if after is not None else "NONE (dropped)"
    verdict = "SAME" if before == after else ("DROPPED" if after is None else "*** DRIFT ***")
    print(f"visual row {sel_row} (order {order_before}) : {b} -> {a}   [{verdict}]")
    print(f"    order after refill: {order_after}")
