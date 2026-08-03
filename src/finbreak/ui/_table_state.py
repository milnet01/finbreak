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

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QWidget,
)

from finbreak import paths

# The insertion-index tag on each row's column-0 item — survives a sort because Qt
# moves an item's data with the item. UserRole+1 holds a SortableItem's sort key.
_ROW_INDEX_ROLE = Qt.ItemDataRole.UserRole
_SORT_KEY_ROLE = Qt.ItemDataRole.UserRole + 1

# The dynamic Qt property holding each remembered view's build-time header state,
# so Reset layout can put it back (FIBR-0192). On the VIEW, not in a module-level
# registry: a registry keyed by objectName would outlive the widget that owns it
# and leak across a workspace rebuild, two windows, or two tests in one session.
_DEFAULT_STATE_PROP = "finbreak_default_header_state"


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
    """Repopulate ``table`` without Qt re-sorting mid-fill, and without carrying a
    stale selection across the refill.

    Two things happen on entry: sorting is disabled for the body (restored after,
    so the current sort is applied once), and the table is **cleared**.

    The clear is load-bearing, not tidiness. Every caller does a full refill, and
    four of the five did it *in place* — ``setRowCount(len(rows))`` over the
    existing rows. Under a non-identity sort that silently retargets the user's
    action: the selection is held by VISUAL row, the restore re-sorts, and the
    row the user picked now holds a different item, so ``selected_index`` returns
    a different tag. Measured: select ``T3-fuel``, refill, and the action target
    becomes ``T2-RENT``. It needs nothing exotic to reach — ``SettingsDialog`` is
    non-modal, and a Save pushes new prefs into every tab, each of which refills.
    A wrong row-to-action map in a money app is unacceptable, so this belongs in
    the one seam rather than in five call sites (``AccountsWidget`` was the only
    one that had it right, and it got there by hand).

    After a refill nothing is selected, which is the honest state; a caller that
    wants to restore the user's row calls ``select_by_index``.

    Safe on a table that never enabled sorting (``setSortingEnabled(False)`` is
    then a no-op restore).
    """
    was_sorting = table.isSortingEnabled()
    table.setSortingEnabled(False)
    table.setRowCount(0)
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


def selected_indexes(table: QTableWidget) -> list[int]:
    """The parallel-list indexes of every selected row, sorted ascending **by index
    value** (i.e. in the order the rows were inserted, NOT their current visual
    order — the two differ after a sort). An untagged row contributes nothing
    (where ``selected_index`` returns None for one). Empty when nothing is selected.

    The plural sibling of ``selected_index``, which is deliberately single-row and
    is used in five files. The ordering is normative, not incidental: it is the
    order ``confirm_many`` consumes, so it decides which of two conflicting pairs
    wins (FIBR-0201 INV-4)."""
    found: list[int] = []
    for row in {i.row() for i in table.selectedItems()}:
        item = table.item(row, 0)
        key = None if item is None else item.data(_ROW_INDEX_ROLE)
        if key is not None:
            found.append(int(key))
    return sorted(found)


def select_by_index(table: QTableWidget, index: int) -> None:
    """Select the row whose tag == ``index`` (post-sort safe), and **only** it.

    The leading ``clearSelection`` is load-bearing, not hygiene: ``selectRow``
    *replaces* the selection under ``SingleSelection`` but *adds* to it under
    ``MultiSelection`` (measured 2026-08-02), so without it this helper silently
    becomes "also select this row" on a widened table — turning the shipped
    ``StatementsWidget._select_period`` into a different function (FIBR-0201
    INV-15). A no-op on the two tables that stay single-select."""
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.data(_ROW_INDEX_ROLE) == index:
            table.clearSelection()
            table.selectRow(row)
            return


def _settings() -> QSettings:
    return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)


def _header_of(view: QTableWidget | QTreeWidget) -> QHeaderView:
    """The column header of either view kind — QTableWidget names it
    ``horizontalHeader``, QTreeWidget just ``header``."""
    return view.horizontalHeader() if isinstance(view, QTableWidget) else view.header()


def remember_columns(view: QTableWidget | QTreeWidget) -> None:
    """Restore ``view``'s saved column layout (widths / order / sort) and re-save it
    on every resize, reorder, or sort. Keyed by ``objectName`` in the window INI —
    call once, as the **last** line of the view's header setup (see below).

    Columns are made **drag-reorderable** (``setSectionsMovable``); the new visual
    order is persisted via the same ``saveState`` restored here (the header state
    carries section positions as well as widths, FIBR-0012 user request). Reordering
    is visual-only — the parallel-list row tag lives on **logical** column 0, so
    ``selected_index`` / sorting stay correct whatever the column order (INV-9).

    **Call this last**, after every other header call — the rule is that literal,
    and it is not a style preference. ``saveState()`` serialises far more than
    widths and positions: the sections-movable flag, the sort indicator (including
    whether it is *shown*), ``stretchLastSection``, the section resize mode,
    ``sectionsClickable``, ``defaultSectionSize`` and per-section hidden flags.
    The build-time snapshot taken here is what ``reset_columns`` restores, so any
    header call made *after* this one has its pre-call value baked into the
    snapshot and silently reverted by the first Reset layout — drag-reorder turned
    off, the sort arrow hidden, a stretch undone, a hidden column revealed
    (FIBR-0192; measured set in FIBR-0192-qt-facts.md QT-3/QT-10/QT-11)."""
    key = f"columns/{view.objectName()}"
    header = _header_of(view)
    header.setSectionsMovable(True)
    # After the movable flag, before the restore: this is the FIRST-RUN layout that
    # Reset layout returns to, not whatever the user last left behind.
    view.setProperty(_DEFAULT_STATE_PROP, header.saveState())
    state = _settings().value(key)
    if isinstance(state, (QByteArray, bytes, bytearray)):
        # Only a byte blob is a saved layout. A damaged INI hands back a plain
        # string, which raises TypeError inside Qt and takes down the tab being
        # built — the sibling of the startup brick fixed in FIBR-0210. A layout we
        # cannot decode is simply the build-time default, never a crash.
        header.restoreState(QByteArray(state))

    def _save(*_: object) -> None:
        settings = _settings()
        settings.setValue(key, header.saveState())
        settings.sync()  # flush now, so a same-process rebuild reads it back (INV-5)

    header.sectionResized.connect(_save)
    header.sectionMoved.connect(_save)
    header.sortIndicatorChanged.connect(_save)


def reset_columns(root: QWidget) -> None:
    """Put every remembered header under ``root`` back to the default captured by
    ``remember_columns``. Views built without it are skipped.

    ``findChildren`` is recursive, so this reaches the Home trees through the
    dashboard's ``QScrollArea`` and the tab pages through the workspace's
    ``QTabWidget``.

    **The restore is deliberately NOT wrapped in ``blockSignals``.** Blocking looks
    like hygiene here and silently breaks a shipped behaviour: ``restoreState``
    emits no ``sectionResized`` / ``sectionMoved``, so nothing re-saves — but it
    *does* emit ``sortIndicatorChanged``, and a table view's own re-sort rides on
    that signal. Block it and the header shows the restored default's sort arrow
    while the rows keep the user's old order, on all five click-sortable tables
    (FIBR-0192; the same arrow-vs-rows split spec.md row 4b already calls a defect).

    ``remember_columns``' ``_save`` also listens to that signal, and **it does
    run** — once per restored view, with the ``Qt::SortOrder`` argument marshalling
    cleanly (measured on PySide6 6.11.1; FIBR-0192-qt-facts.md QT-5, corrected
    2026-08-02). So this function writes the just-restored *default* back to the
    INI and ``sync()``s it, once per view.

    That is harmless from ``_reset_layout`` **only** because its trailing
    ``settings.remove("columns")`` erases those writes (§4.4). Any other caller
    must either clear afterwards or accept that the default is now persisted."""
    views: list[QTableWidget | QTreeWidget] = [
        *root.findChildren(QTableWidget),
        *root.findChildren(QTreeWidget),
    ]
    for view in views:
        state = view.property(_DEFAULT_STATE_PROP)
        if state is not None:
            _header_of(view).restoreState(state)
