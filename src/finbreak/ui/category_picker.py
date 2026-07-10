"""CategoryPickerDialog + the shared ``leaf_categories`` helper (FIBR-0010 D10/D13).

A small ``QDialog`` (one dialog per file, like ``ui/account_picker``): pick a
**leaf** category for a transaction, with an explicit *Uncategorised* choice, +
OK/Cancel. The dialog is "dumb" — it takes the already-fetched leaf list, not a
service. ``leaf_categories`` is the one place the assignable (non-root) list is
built from a ``CategoryService`` — shared by this picker and the Rules tab's rule
editor, so there is a single leaf-list definition. All strings go through
``tr()`` and every widget sits in a layout manager (coding.md § 5.2).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

from finbreak.models import Category
from finbreak.services.categories import CategoryService


def leaf_categories(categories: CategoryService) -> list[Category]:
    """The assignable (non-root) categories — every category with a parent. The two
    Type roots (Income / Expenditure) are structural and never assignable (INV-9)."""
    return [c for c in categories.list_all() if c.parent_id is not None]


class CategoryPickerDialog(QDialog):
    def __init__(
        self,
        leaves: list[Category],
        current_category_id: int | None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Set category"))

        self._combo = QComboBox()
        self._combo.addItem(self.tr("Uncategorised"), None)  # index 0 — the default
        for leaf in leaves:
            self._combo.addItem(leaf.name, leaf.id)
        if current_category_id is not None:
            index = self._combo.findData(current_category_id)
            if index >= 0:
                self._combo.setCurrentIndex(index)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(self.tr("Category"), self._combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def selected_category_id(self) -> int | None:
        """The chosen leaf's id, or ``None`` for the *Uncategorised* choice."""
        return self._combo.currentData()
