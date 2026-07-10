"""Rules tab — the auto-categorisation rule manager (FIBR-0010 D13).

A ``RulesWidget`` (mirroring ``CategoriesWidget``): a ``QTableWidget`` of rules in
priority order (Pattern · Category) + Add / Edit / Delete / Move up / Move down
(gated on a selection) + an **Apply rules now** button that re-files the auto rows
and reports the count. ``RuleEditDialog`` (same file) is the one dialog for both
the manager's Add/Edit and the Home learning offer; its OK is disabled while the
pattern is empty, so no empty pattern ever reaches ``add_rule`` through the dialog.
All strings go through ``tr()`` and every widget sits in a layout manager
(coding.md § 5.2).
"""

from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import FinbreakError, VaultLockedError
from finbreak.models import CategorizationRule, Category
from finbreak.services.auth import AuthService
from finbreak.services.categories import CategoryService
from finbreak.services.categorization import CategorizationService

_COL_PATTERN = 0
_COL_CATEGORY = 1


class RuleEditDialog(QDialog):
    """Add or edit one rule: a pattern field + a leaf-category selector. Built with
    an optional pre-filled pattern + preselected category (the learning offer
    pre-fills both). OK is disabled while the pattern is empty/whitespace."""

    def __init__(
        self,
        leaves: list[Category],
        pattern: str = "",
        category_id: int | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Rule"))

        self._pattern = QLineEdit(pattern)
        self._pattern.setPlaceholderText(self.tr("Text to look for in the description"))
        self._category = QComboBox()
        for leaf in leaves:
            self._category.addItem(leaf.name, leaf.id)
        if category_id is not None:
            index = self._category.findData(category_id)
            if index >= 0:
                self._category.setCurrentIndex(index)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._pattern.textChanged.connect(self._sync_ok)
        self._sync_ok()  # gate OK on the initial pattern

        form = QFormLayout()
        form.addRow(self.tr("When the description contains"), self._pattern)
        form.addRow(self.tr("File it as"), self._category)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._buttons)

    @Slot()
    def _sync_ok(self) -> None:
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(bool(self._pattern.text().strip()))

    def pattern(self) -> str:
        return self._pattern.text()

    def selected_category_id(self) -> int:
        return self._category.currentData()


class RulesWidget(QWidget):
    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tab_rules")
        self._categorization = CategorizationService(service.vault)
        self._categories = CategoryService(service.vault)
        self._rows: list[CategorizationRule] = []  # parallel to the table rows

        self.setWindowTitle(self.tr("Rules"))

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels([self.tr("Pattern"), self.tr("Category")])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self._add_button = QPushButton(self.tr("Add"))
        self._edit_button = QPushButton(self.tr("Edit"))
        self._delete_button = QPushButton(self.tr("Delete"))
        self._move_up_button = QPushButton(self.tr("Move up"))
        self._move_down_button = QPushButton(self.tr("Move down"))
        self._apply_button = QPushButton(self.tr("Apply rules now"))
        self._error = QLabel()
        self._status = QLabel()

        actions = QHBoxLayout()
        actions.addWidget(self._add_button)
        actions.addWidget(self._edit_button)
        actions.addWidget(self._delete_button)
        actions.addWidget(self._move_up_button)
        actions.addWidget(self._move_down_button)
        actions.addStretch()
        actions.addWidget(self._apply_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(actions)
        layout.addWidget(self._error)
        layout.addWidget(self._status)

        self._add_button.clicked.connect(self._on_add)
        self._edit_button.clicked.connect(self._on_edit)
        self._delete_button.clicked.connect(self._on_delete)
        self._move_up_button.clicked.connect(lambda: self._on_move("up"))
        self._move_down_button.clicked.connect(lambda: self._on_move("down"))
        self._apply_button.clicked.connect(self._on_apply)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        self._refresh()

    def _refresh(self) -> None:
        self._rows = self._categorization.list_rules()
        names = {c.id: c.name for c in self._categories.list_all()}
        self._table.setRowCount(len(self._rows))
        for row, rule in enumerate(self._rows):
            self._table.setItem(row, _COL_PATTERN, QTableWidgetItem(rule.pattern))
            self._table.setItem(
                row, _COL_CATEGORY, QTableWidgetItem(names.get(rule.category_id, ""))
            )
        self._on_selection_changed()

    @Slot()
    def _on_selection_changed(self) -> None:
        has_selection = self._selected_row() is not None
        for button in (
            self._edit_button,
            self._delete_button,
            self._move_up_button,
            self._move_down_button,
        ):
            button.setEnabled(has_selection)

    @Slot()
    def _on_add(self) -> None:
        self._error.clear()
        dialog = RuleEditDialog(self._categorization.leaf_categories(), parent=self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        pattern, category_id = dialog.pattern(), dialog.selected_category_id()
        dialog.deleteLater()
        if not accepted:
            return
        try:
            self._categorization.add_rule(pattern, category_id)
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._refresh()

    @Slot()
    def _on_edit(self) -> None:
        self._error.clear()
        index = self._selected_row()
        if index is None:
            return
        rule = self._rows[index]
        dialog = RuleEditDialog(
            self._categorization.leaf_categories(),
            rule.pattern,
            rule.category_id,
            self,
        )
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        pattern, category_id = dialog.pattern(), dialog.selected_category_id()
        dialog.deleteLater()
        if not accepted:
            return
        try:
            self._categorization.update_rule(rule.id, pattern, category_id)
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._refresh()

    @Slot()
    def _on_delete(self) -> None:
        self._error.clear()
        index = self._selected_row()
        if index is None:
            return
        try:
            self._categorization.delete_rule(self._rows[index].id)
        except VaultLockedError:
            return  # auto-lock fired; the workspace is being torn down (INV-14)
        self._refresh()

    def _on_move(self, direction: str) -> None:
        index = self._selected_row()
        if index is None:
            return
        rule_id = self._rows[index].id
        try:
            self._categorization.move_rule(rule_id, direction)  # type: ignore[arg-type]
        except VaultLockedError:
            return
        self._refresh()
        self._select_rule(rule_id)  # keep the moved rule selected

    @Slot()
    def _on_apply(self) -> None:
        self._error.clear()
        try:
            count = self._categorization.apply_rules()
        except VaultLockedError:
            return  # auto-lock fired mid-apply (INV-14)
        self._status.setText(self.tr("Re-filed %n transaction(s).", "", count))
        self._refresh()

    # --- test / shell accessors -------------------------------------------- #
    def rule_count(self) -> int:
        return len(self._rows)

    def _selected_row(self) -> int | None:
        rows = {i.row() for i in self._table.selectedItems()}
        return next(iter(rows)) if len(rows) == 1 else None

    def _select_rule(self, rule_id: int) -> None:
        for i, rule in enumerate(self._rows):
            if rule.id == rule_id:
                self._table.selectRow(i)
                return
