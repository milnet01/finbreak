"""Category-manager screen — the Type roots and their (sub-)categories in a
``QTreeWidget``, with an add / edit form (FIBR-0006 INV-7; FIBR-0154 3rd tier).

All strings go through ``tr()`` and every widget sits in a Qt layout manager, so
the screen is translation-ready and RTL-safe (coding.md § 5.2). The tree renders
three levels — Type → Category → Sub-category — with unbounded recursion (it
shows whatever depth exists). **Add** is anchored to the tree selection: it
creates a child of the *selected* node (a Level-2 under a Type, a Level-3 under a
Category) and is disabled when the selection is Level-3 or deeper — the UI-only
depth cap of 3 (the data model & service allow arbitrary depth; FIBR-0154 § 4.4).
**Update** renames and/or re-parents via a dedicated, subject-aware "Move
under…" selector; an empty name field keeps the current name (a pure re-parent).
A Type root is a structural header: selecting one disables Update + Delete (roots
can't be edited or deleted, INV-6/INV-7f).
"""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import QCoreApplication, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import FinbreakError, VaultLockedError
from finbreak.models import Category
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.ui._widgets import (
    _LABEL_CONTEXT,
    category_type_labels,
    select_combo_data,
)

# Per-item data roles: the category id, its parent_id, and its kind token (set
# on the two roots only — a non-None kind marks a structural Type header).
_ID_ROLE = Qt.ItemDataRole.UserRole
_PARENT_ROLE = Qt.ItemDataRole.UserRole + 1
_KIND_ROLE = Qt.ItemDataRole.UserRole + 2

# The UI-only depth cap (FIBR-0154 § 4.4): a node at this level can gain no
# child, and no re-parent may push a subtree's deepest node past it.
_MAX_DEPTH = 3


class CategoriesWidget(QWidget):
    done = Signal()

    def __init__(
        self,
        service: AuthService,
        parent: QWidget | None = None,
        *,
        show_done: bool = True,
    ):
        super().__init__(parent)
        self._categories = CategoryService(service.vault)

        self.setWindowTitle(self.tr("Categories"))

        # kind token -> translated Type label (display only; the token is the
        # structural identifier, never translated). Sourced from the one shared
        # helper so the manager and the pickers can't drift (FIBR-0123 INV-4).
        self._type_labels = category_type_labels()

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._name = QLineEdit()
        self._name.setPlaceholderText(self.tr("Category name"))
        # An explicit accessible name so a screen reader announces the field even
        # after the placeholder vanishes (WCAG 1.3.1/3.3.2). (indie-review M-dlg3)
        self._name.setAccessibleName(self.tr("Category name"))
        # Subject-aware re-parent target — rebuilt per selection in
        # _on_selection_changed; used by Update only, never by Add (FIBR-0154 § 4.2).
        self._move_under = QComboBox()
        self._move_under.setAccessibleName(self.tr("Move under"))
        self._add_button = QPushButton(self.tr("Add"))
        self._update_button = QPushButton(self.tr("Update selected"))
        self._delete_button = QPushButton(self.tr("Delete selected"))
        # The "back to Home" Done button is meaningless when this widget is a
        # permanent tab, so it is not built when show_done=False (FIBR-0052
        # INV-12); the `done` signal stays (unfired) so no caller/test breaks.
        self._done_button = QPushButton(self.tr("Done")) if show_done else None
        self._error = QLabel()

        add_row = QHBoxLayout()
        add_row.addWidget(self._name)
        add_row.addWidget(self._add_button)

        edit_row = QHBoxLayout()
        edit_row.addWidget(QLabel(self.tr("Move under")))
        edit_row.addWidget(self._move_under)
        edit_row.addWidget(self._update_button)

        actions = QHBoxLayout()
        actions.addWidget(self._delete_button)
        actions.addStretch()
        if self._done_button is not None:
            actions.addWidget(self._done_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tree)
        layout.addLayout(add_row)
        layout.addLayout(edit_row)
        layout.addWidget(self._error)
        layout.addLayout(actions)

        self._add_button.clicked.connect(self._on_add)
        self._update_button.clicked.connect(self._on_update)
        self._delete_button.clicked.connect(self._on_delete)
        if self._done_button is not None:
            self._done_button.clicked.connect(self.done)
        # Selecting a node updates the Add/Update/Delete enablement, rebuilds the
        # "Move under…" targets, and shows the current name as a placeholder.
        self._tree.currentItemChanged.connect(self._on_selection_changed)

        self._refresh()
        # No selection yet: sync the initial button/combo state (currentItemChanged
        # does not fire on an empty→populated tree with nothing selected).
        self._on_selection_changed()

    def _kind_of_item(self, item: QTreeWidgetItem) -> str | None:
        """The kind token of a Type root item (``None`` for a category)."""
        return item.data(0, _KIND_ROLE)

    @staticmethod
    def _depth_of_item(item: QTreeWidgetItem) -> int:
        """1 for a Type root, 2 for a Level-2 Category, 3 for a Level-3
        sub-category — the visible tree depth (ancestor count + 1)."""
        depth = 1
        parent = item.parent()
        while parent is not None:
            depth += 1
            parent = parent.parent()
        return depth

    @Slot()
    def _on_add(self) -> None:
        self._error.clear()
        item = self._tree.currentItem()
        # The cap is enforced at the anchor: no parent (nothing selected) or a
        # Level-3+ selection (a child would be Level 4) — the button is already
        # disabled in those states, this guards a direct call.
        if item is None or self._depth_of_item(item) >= _MAX_DEPTH:
            return
        try:
            self._categories.add_category(item.data(0, _ID_ROLE), self._name.text())
        except VaultLockedError:
            return  # auto-lock fired mid-edit — silent, like the delete handler
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._name.clear()
        self._refresh()

    @Slot()
    def _on_update(self) -> None:
        self._error.clear()
        item = self._tree.currentItem()
        if item is None:
            return
        # An empty name field keeps the current name (the field starts empty with
        # the current name as placeholder), so a pure re-parent never trips the
        # service's empty-name guard (FIBR-0154 § 4.2).
        name = self._name.text().strip() or item.text(0)
        try:
            self._categories.update_category(
                item.data(0, _ID_ROLE), name, self._move_under.currentData()
            )
        except VaultLockedError:
            return  # auto-lock fired mid-edit — silent, like the delete handler
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._refresh()

    @Slot()
    def _on_delete(self) -> None:
        self._error.clear()
        item = self._tree.currentItem()
        if item is None:
            return
        category_id = item.data(0, _ID_ROLE)
        # Name the blast radius BEFORE deleting so a non-technical user is never
        # surprised by a mass move (FIBR-0010 INV-8). Two tr() sentences — Qt allows
        # only one %n numerus per translated string. The counts are read pre-delete
        # (before the cascade's step-1 reset) via the service, never a repo.
        txn_count, rule_count = self._categories.delete_blast_radius(category_id)
        confirmed = QMessageBox.question(
            self,
            self.tr("Delete category"),
            self.tr(
                "Deleting this category will make %n transaction(s) automatic again.",
                "",
                txn_count,
            )
            + " "
            + self.tr(
                "It will also remove %n rule(s) that file into it. Continue?",
                "",
                rule_count,
            ),
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self._categories.delete_category(category_id)
        except VaultLockedError:
            # An idle auto-lock can fire while the confirm box is open — the vault is
            # then closed and this workspace is being torn down (INV-14). Nothing to
            # delete against a locked vault; the next unlock rebuilds fresh chrome.
            return
        except FinbreakError as exc:
            # ProtectedCategoryError / CategoryHasChildrenError — show the
            # message, remove nothing (INV-6 reflected through the UI).
            self._error.setText(str(exc))
            return
        self._refresh()

    @Slot()
    def _on_selection_changed(self) -> None:
        self._error.clear()
        item = self._tree.currentItem()
        is_root = item is not None and self._kind_of_item(item) is not None
        depth = self._depth_of_item(item) if item is not None else 0
        # Add is anchored to the selection: enabled for a Level-1 (Type) or Level-2
        # (Category) node — a child would be Level 2 or 3. Disabled with nothing
        # selected (no parent) or a Level-3+ node (the cap, FIBR-0154 § 4.2).
        self._add_button.setEnabled(item is not None and depth < _MAX_DEPTH)
        # A root is a structural header: it can't be renamed, re-parented, deleted.
        self._update_button.setEnabled(item is not None and not is_root)
        self._delete_button.setEnabled(item is not None and not is_root)
        if item is not None and depth >= _MAX_DEPTH:
            self._error.setText(
                self.tr("Sub-categories can't be nested deeper than three levels.")
            )
        self._rebuild_move_under(item, is_root)
        # The name field starts empty; the current name shows as placeholder only,
        # so Add never inherits the parent's name and a pure re-parent keeps it.
        self._name.clear()
        current_name = item.text(0) if item is not None and not is_root else None
        self._name.setPlaceholderText(current_name or self.tr("Category name"))

    def _rebuild_move_under(self, item: QTreeWidgetItem | None, is_root: bool) -> None:
        """Repopulate the subject-aware "Move under…" targets (FIBR-0154 § 4.2):
        the Types + Level-2 Categories, minus the subject and its descendants, minus
        any parent that would push the subject's deepest descendant past Level 3 (a
        childed Level-2 → Types only). Empty/disabled when no re-parentable subject
        is selected; preselects the subject's current parent."""
        self._move_under.clear()
        if item is None or is_root:
            self._move_under.setEnabled(False)
            return
        self._move_under.setEnabled(True)
        subject_id = item.data(0, _ID_ROLE)

        by_children: dict[int | None, list[Category]] = defaultdict(list)
        for category in self._categories.list_all():
            by_children[category.parent_id].append(category)
        excluded = self._subtree_ids(subject_id, by_children)
        subject_height = self._subtree_height(subject_id, by_children)

        roots = by_children[None]
        # A Type sits at depth 1 → the subject lands at depth 2 and its deepest
        # descendant at 2 + subject_height; a Level-2 sits at depth 2 → 3 + height.
        for root in roots:
            if 2 + subject_height <= _MAX_DEPTH:
                label = self._type_labels.get(root.kind or "", root.name)
                self._move_under.addItem(label, root.id)
        for root in roots:
            type_label = self._type_labels.get(root.kind or "", root.name)
            for cat in sorted(by_children[root.id], key=lambda c: c.name.casefold()):
                if cat.id in excluded:
                    continue  # never offer the subject itself or its descendants
                if 3 + subject_height <= _MAX_DEPTH:
                    self._move_under.addItem(
                        self._reparent_label(type_label, cat.name), cat.id
                    )
        select_combo_data(self._move_under, item.data(0, _PARENT_ROLE))

    @staticmethod
    def _subtree_ids(
        root_id: int, by_children: dict[int | None, list[Category]]
    ) -> set[int]:
        """``root_id`` plus every descendant id (the ids a re-parent must not offer,
        else it would create a cycle)."""
        ids: set[int] = set()
        stack = [root_id]
        while stack:
            current = stack.pop()
            ids.add(current)
            stack.extend(child.id for child in by_children[current])
        return ids

    @classmethod
    def _subtree_height(
        cls, node_id: int, by_children: dict[int | None, list[Category]]
    ) -> int:
        """The depth of the subtree below ``node_id`` — 0 for a leaf, 1 when it has
        children that are themselves leaves, etc."""
        children = by_children[node_id]
        if not children:
            return 0
        return 1 + max(cls._subtree_height(c.id, by_children) for c in children)

    @staticmethod
    def _reparent_label(type_label: str, name: str) -> str:
        """A ``"Type › Category"`` label for a Level-2 re-parent target, translatable
        via the one shared ``_LABEL_CONTEXT`` (never a hardcoded separator)."""
        return QCoreApplication.translate(_LABEL_CONTEXT, "{parent} › {row}").format(
            parent=type_label, row=name
        )

    def _select_category(self, category_id: int) -> None:
        """Select the tree item for ``category_id`` anywhere in the tree, walked
        recursively so it reaches a Level-3 node (UI tests)."""

        def walk(item: QTreeWidgetItem) -> bool:
            if item.data(0, _ID_ROLE) == category_id:
                self._tree.setCurrentItem(item)
                return True
            return any(walk(item.child(i)) for i in range(item.childCount()))

        for i in range(self._tree.topLevelItemCount()):
            root = self._tree.topLevelItem(i)
            if root is not None and walk(root):
                return

    def _refresh(self) -> None:
        self._tree.clear()
        for root in self._categories.children_of(None):
            label = self._type_labels.get(root.kind or "", root.name)
            root_item = self._make_item(label, root)
            self._tree.addTopLevelItem(root_item)
            self._add_children(root_item, root.id)
        self._tree.expandAll()

    def _add_children(self, parent_item: QTreeWidgetItem, parent_id: int) -> None:
        """Recursively attach every descendant of ``parent_id`` — unbounded, so a
        pre-existing node deeper than the UI cap still renders (FIBR-0154 § 4.2)."""
        for child in self._categories.children_of(parent_id):
            child_item = self._make_item(child.name, child)
            parent_item.addChild(child_item)
            self._add_children(child_item, child.id)

    @staticmethod
    def _make_item(label: str, category: Category) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        item.setData(0, _ID_ROLE, category.id)
        item.setData(0, _PARENT_ROLE, category.parent_id)
        item.setData(0, _KIND_ROLE, category.kind)
        return item
