"""Shared Qt widget helpers (FIBR-0068).

``select_combo_data`` is the guarded combo-preselect idiom used by the account /
category / type pickers and dialogs: find the item whose ``userData`` equals a
value and select it, but leave the current selection untouched when nothing
matches. This is deliberately **distinct** from ``ImportWizardWidget._set_combo``,
which is *unguarded* — the wizard wants a saved profile column that is absent from
the current file to clear the combo (forcing a re-pick), not silently keep a
stale selection.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox

from finbreak.models import Category, CategoryKind

# One fixed translate context shared by the section headers, the ``Name (Type)``
# row tag, AND the category manager (FIBR-0123 INV-4/INV-6) — so the Income /
# Expenditure strings have a single translation home.
_LABEL_CONTEXT = "CategoryTypeLabels"


def select_combo_data(combo: QComboBox, value: object) -> None:
    """Select the item whose ``userData`` equals ``value``; if none matches
    (``findData`` returns -1) leave the current selection unchanged."""
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def category_type_labels() -> dict[str, str]:
    """The Income / Expenditure display labels keyed by the untranslated
    ``CategoryKind`` token (FIBR-0123 INV-4). The token is the structural key;
    only the value is translated, under the one fixed ``_LABEL_CONTEXT``."""
    return {
        CategoryKind.INCOME.value: QCoreApplication.translate(_LABEL_CONTEXT, "Income"),
        CategoryKind.EXPENDITURE.value: QCoreApplication.translate(
            _LABEL_CONTEXT, "Expenditure"
        ),
    }


def add_grouped_categories(
    combo: QComboBox, grouped: list[tuple[str, list[Category]]]
) -> None:
    """Append the grouped categories to ``combo`` (FIBR-0123 INV-1/INV-3): a
    disabled, bold section header per **non-empty** section (its text the plain
    ``category_type_labels()`` label), then a ``Name (Type)`` row per category
    carrying the category id as ``userData``. Rendered in the order given — the
    ordering / sort is the service's guarantee, not this helper's.

    Selection: a combo auto-rests on index 0, which may be a disabled header, so
    after populating, if the current row is not selectable the resting selection
    moves to the first enabled row; an already-selectable current (e.g. the
    picker's ``Uncategorised``) is left untouched."""
    labels = category_type_labels()
    row_tag = QCoreApplication.translate(_LABEL_CONTEXT, "{name} ({type})")
    for token, categories in grouped:
        if not categories:
            continue  # a section with no categories contributes no header
        type_label = labels[token]
        combo.addItem(type_label, None)
        header = _combo_item(combo, combo.count() - 1)
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        header.setFlags(Qt.ItemFlag.NoItemFlags)  # non-selectable, non-enabled
        for category in categories:
            combo.addItem(
                row_tag.format(name=category.name, type=type_label), category.id
            )
    _rest_on_first_selectable(combo)


def _combo_item(combo: QComboBox, index: int) -> QStandardItem:
    """The backing ``QStandardItem`` at ``index`` (just-added, so in-range).
    ``QComboBox.model()`` is typed ``QAbstractItemModel`` (no ``.item()``); the
    default model is a ``QStandardItemModel``, so both casts are safe and keep
    mypy green without a runtime guard (matching the no-assert-in-src idiom)."""
    return cast(QStandardItem, cast(QStandardItemModel, combo.model()).item(index))


def _rest_on_first_selectable(combo: QComboBox) -> None:
    """If the current row is not selectable (a header), move the selection to the
    first enabled row; leave an already-selectable current alone."""
    model = cast(QStandardItemModel, combo.model())
    current = model.item(combo.currentIndex())
    if current is not None and current.flags() & Qt.ItemFlag.ItemIsEnabled:
        return
    for i in range(combo.count()):
        item = model.item(i)
        if item is not None and item.flags() & Qt.ItemFlag.ItemIsEnabled:
            combo.setCurrentIndex(i)
            return
