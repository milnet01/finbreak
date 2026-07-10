"""Category-manager screen — the two Type roots + their categories in a
``QTreeWidget``, with a shared add / edit form (FIBR-0006 INV-7).

All strings go through ``tr()`` and every widget sits in a Qt layout manager, so
the screen is translation-ready and RTL-safe (coding.md § 5.2). The Type picker
carries each root's **id** as item data behind a ``tr()`` label keyed on the
root's ``kind`` token, so the DB stays language-neutral. A Type root is a
structural header: selecting one disables Update + Delete (roots can't be edited
or deleted, INV-6/INV-7f). The UI exposes two levels (Type → Category); a third
(sub-category) level is a later enhancement (D9).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
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
from finbreak.models import CategoryKind
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService

# Per-item data roles: the category id, its parent_id, and its kind token (set
# on the two roots only — a non-None kind marks a structural Type header).
_ID_ROLE = Qt.ItemDataRole.UserRole
_PARENT_ROLE = Qt.ItemDataRole.UserRole + 1
_KIND_ROLE = Qt.ItemDataRole.UserRole + 2


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
        # structural identifier, never translated).
        self._type_labels = {
            CategoryKind.INCOME.value: self.tr("Income"),
            CategoryKind.EXPENDITURE.value: self.tr("Expenditure"),
        }

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._name = QLineEdit()
        self._name.setPlaceholderText(self.tr("Category name"))
        # An explicit accessible name so a screen reader announces the field even
        # after the placeholder vanishes (WCAG 1.3.1/3.3.2). (indie-review M-dlg3)
        self._name.setAccessibleName(self.tr("Category name"))
        self._type = QComboBox()  # (re)filled in _refresh — needs the roots' ids
        self._type.setAccessibleName(self.tr("Category type"))
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
        add_row.addWidget(self._type)
        add_row.addWidget(self._add_button)
        add_row.addWidget(self._update_button)

        actions = QHBoxLayout()
        actions.addWidget(self._delete_button)
        actions.addStretch()
        if self._done_button is not None:
            actions.addWidget(self._done_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tree)
        layout.addLayout(add_row)
        layout.addWidget(self._error)
        layout.addLayout(actions)

        self._add_button.clicked.connect(self._on_add)
        self._update_button.clicked.connect(self._on_update)
        self._delete_button.clicked.connect(self._on_delete)
        if self._done_button is not None:
            self._done_button.clicked.connect(self.done)
        # Selecting a category loads it into the form; selecting a root disables
        # the edit / delete actions (a root is a structural header, INV-7f).
        self._tree.currentItemChanged.connect(self._on_selection_changed)

        self._refresh()

    def _kind_of_item(self, item: QTreeWidgetItem) -> str | None:
        """The kind token of a Type root item (``None`` for a category)."""
        return item.data(0, _KIND_ROLE)

    @Slot()
    def _on_add(self) -> None:
        self._error.clear()
        try:
            self._categories.add_category(self._type.currentData(), self._name.text())
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
        try:
            self._categories.update_category(
                item.data(0, _ID_ROLE), self._name.text(), self._type.currentData()
            )
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
        item = self._tree.currentItem()
        is_root = item is not None and self._kind_of_item(item) is not None
        self._update_button.setEnabled(item is not None and not is_root)
        self._delete_button.setEnabled(item is not None and not is_root)
        if item is None or is_root:
            return
        # Load the selected category into the shared form for an in-place edit.
        self._name.setText(item.text(0))
        index = self._type.findData(item.data(0, _PARENT_ROLE))
        if index != -1:
            self._type.setCurrentIndex(index)

    def _select_category(self, category_id: int) -> None:
        """Select the tree item (root or child) for ``category_id`` (UI tests)."""
        for i in range(self._tree.topLevelItemCount()):
            root = self._tree.topLevelItem(i)
            if root is None:
                continue
            if root.data(0, _ID_ROLE) == category_id:
                self._tree.setCurrentItem(root)
                return
            for j in range(root.childCount()):
                child = root.child(j)
                if child is not None and child.data(0, _ID_ROLE) == category_id:
                    self._tree.setCurrentItem(child)
                    return

    def _refresh(self) -> None:
        self._tree.clear()
        self._type.clear()
        for root in self._categories.children_of(None):
            label = self._type_labels.get(root.kind or "", root.name)
            root_item = QTreeWidgetItem([label])
            root_item.setData(0, _ID_ROLE, root.id)
            root_item.setData(0, _PARENT_ROLE, root.parent_id)  # None
            root_item.setData(0, _KIND_ROLE, root.kind)
            self._tree.addTopLevelItem(root_item)
            self._type.addItem(label, root.id)
            for child in self._categories.children_of(root.id):
                child_item = QTreeWidgetItem([child.name])
                child_item.setData(0, _ID_ROLE, child.id)
                child_item.setData(0, _PARENT_ROLE, child.parent_id)
                child_item.setData(0, _KIND_ROLE, child.kind)  # None
                root_item.addChild(child_item)
        self._tree.expandAll()
