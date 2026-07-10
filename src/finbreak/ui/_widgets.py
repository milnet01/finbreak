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

from PySide6.QtWidgets import QComboBox


def select_combo_data(combo: QComboBox, value: object) -> None:
    """Select the item whose ``userData`` equals ``value``; if none matches
    (``findData`` returns -1) leave the current selection unchanged."""
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
