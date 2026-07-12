"""Reusable ``QTableWidget`` behaviour: click-to-sort + remembered column layout
(FIBR-0117).

Two behaviours the list tables share:

- **Click-to-sort.** ``enable_sorting`` turns on Qt's header-click sort (a second
  click on the same header toggles ascending/descending). Numeric and date columns
  must carry an explicit sort key (a formatted "500.00" or "13/09/2025" would sort
  lexically, wrong) — build those cells with ``SortableItem(text, key)``.

- **Remembered column widths.** ``remember_columns`` restores the table's saved
  header layout on construction and re-saves it whenever the user resizes, reorders,
  or re-sorts a column. State lives in the **window settings INI** (the same
  non-secret store as window geometry — ``paths.window_settings_path``), **never**
  the vault, keyed by the table's ``objectName``.

**Sorting + a parallel row list.** A table whose Python side keeps a parallel list
(``self._rows[visual_row]``) breaks once the user sorts — the visual row no longer
matches the insertion index. The fix: tag each row (via ``tag_row`` on fill, while
sorting is disabled) with its insertion index; ``selected_index`` reads that tag
back from the selected row so the action still lands on the right object. Wrap the
repopulate in ``setSortingEnabled(False)`` … fill … ``setSortingEnabled(True)`` so
Qt doesn't re-sort mid-fill (``fill_guard``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from finbreak import paths

# The insertion-index tag on each row's column-0 item — survives a sort because Qt
# moves an item's data with the item. UserRole+1 holds a SortableItem's sort key.
_ROW_INDEX_ROLE = Qt.ItemDataRole.UserRole
_SORT_KEY_ROLE = Qt.ItemDataRole.UserRole + 1


class SortableItem(QTableWidgetItem):
    """A cell that displays ``text`` but sorts by ``sort_key`` — so an Amount cell
    ("500.00") sorts numerically and a formatted date sorts chronologically, not by
    the display string. ``sort_key`` is any orderable value (int, Decimal, an ISO
    date string). Falls back to the default text compare against a plain item."""

    def __init__(self, text: str, sort_key: object):
        super().__init__(text)
        self.setData(_SORT_KEY_ROLE, sort_key)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine = self.data(_SORT_KEY_ROLE)
        theirs = other.data(_SORT_KEY_ROLE)
        if mine is not None and theirs is not None:
            return bool(mine < theirs)
        return super().__lt__(other)


def enable_sorting(table: QTableWidget) -> None:
    """Turn on header-click sorting (asc/desc toggle) with a visible indicator."""
    table.setSortingEnabled(True)
    table.horizontalHeader().setSortIndicatorShown(True)


@contextmanager
def fill_guard(table: QTableWidget) -> Iterator[None]:
    """Repopulate ``table`` without Qt re-sorting mid-fill: disable sorting for the
    body, restore it after so the current sort is applied once. Safe on a table
    that never enabled sorting (setSortingEnabled(False) is then a no-op restore)."""
    was_sorting = table.isSortingEnabled()
    table.setSortingEnabled(False)
    try:
        yield
    finally:
        table.setSortingEnabled(was_sorting)


def tag_row(table: QTableWidget, row: int, index: int) -> None:
    """Tag ``row``'s column-0 item with its parallel-list ``index`` (call during a
    ``fill_guard`` fill, where ``row == index``). ``selected_index`` reads it back."""
    item = table.item(row, 0)
    if item is not None:
        item.setData(_ROW_INDEX_ROLE, index)


def selected_index(table: QTableWidget) -> int | None:
    """The parallel-list index of the single selected row — read from the row's tag,
    so it stays correct after the user re-sorts. ``None`` when the selection isn't a
    single row (or the row is untagged)."""
    rows = {i.row() for i in table.selectedItems()}
    if len(rows) != 1:
        return None
    item = table.item(next(iter(rows)), 0)
    key = None if item is None else item.data(_ROW_INDEX_ROLE)
    return int(key) if key is not None else None


def select_by_index(table: QTableWidget, index: int) -> None:
    """Select the row whose tag == ``index`` (post-sort safe)."""
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.data(_ROW_INDEX_ROLE) == index:
            table.selectRow(row)
            return


def _settings() -> QSettings:
    return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)


def remember_columns(table: QTableWidget) -> None:
    """Restore ``table``'s saved column layout (widths / order / sort) and re-save it
    on every resize, reorder, or sort. Keyed by ``objectName`` in the window INI —
    call once, after the table has its ``objectName`` and columns."""
    key = f"columns/{table.objectName()}"
    header = table.horizontalHeader()
    state = _settings().value(key)
    if state is not None:
        header.restoreState(state)

    def _save(*_: object) -> None:
        settings = _settings()
        settings.setValue(key, header.saveState())
        settings.sync()  # flush now, so a same-process rebuild reads it back (INV-5)

    header.sectionResized.connect(_save)
    header.sectionMoved.connect(_save)
    header.sortIndicatorChanged.connect(_save)
