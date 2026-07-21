"""CategoryPickerDialog (FIBR-0010 D10).

A small ``QDialog`` (one dialog per file, like ``ui/account_picker``): pick a
**leaf** category for a transaction, with an explicit *Uncategorised* choice, +
OK/Cancel. The dialog is "dumb" — it takes the already-grouped category list, not
a service; callers get that from ``CategorizationService.leaf_categories_grouped()``
(FIBR-0123 D4 — the leaves can't re-derive their Type, so grouping is done once in
the service). All strings go through ``tr()`` and every widget sits in a layout
manager (coding.md § 5.2).
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
from finbreak.ui._widgets import add_grouped_categories, select_combo_data


class CategoryPickerDialog(QDialog):
    def __init__(
        self,
        grouped: list[tuple[str, list[Category]]],
        current_category_id: int | None,
        parent: QWidget | None = None,
        parent_names: dict[int, str] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Set category"))

        self._combo = QComboBox()
        self._combo.addItem(self.tr("Uncategorised"), None)  # index 0 — the default
        add_grouped_categories(self._combo, grouped, parent_names)
        if current_category_id is not None:
            select_combo_data(self._combo, current_category_id)

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
