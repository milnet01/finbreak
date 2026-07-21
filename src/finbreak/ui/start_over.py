"""StartOverDialog — the Step-2 "type DELETE to confirm" gate for the destructive
vault reset (FIBR-0030 § 3.2).

Unlike every other dialog in the app this one is ``exec()``-driven (a nested modal
loop for the synchronous accept read-back) rather than the codebase's usual
``_open_dialog``+signal-read-back convention — an accepted, deliberate departure
for a one-shot confirm. It borrows only the validation-gating idiom from
``ui/backup_export.py``: the OK button is disabled until the field text equals
``CONFIRM_WORD`` exactly.

``CONFIRM_WORD`` is deliberately locale-independent (a plain non-``tr()`` literal):
the field label may be translated, but the word the user types must stay the
literal Latin ``DELETE`` — the label keeps ``DELETE`` un-translated so a localized
label can never disable the OK gate forever.
"""

from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

CONFIRM_WORD = "DELETE"


class StartOverDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Start over — erase everything"))

        warning = QLabel(
            self.tr(
                "This permanently erases your vault and everything in it. It "
                "cannot be undone, and the data cannot be recovered afterwards."
            )
        )
        warning.setWordWrap(True)
        font = warning.font()
        font.setBold(True)
        warning.setFont(font)

        self._field = QLineEdit()
        self._field.setObjectName("start_over_confirm")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok: QPushButton = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(self.tr("Erase everything"))
        # Capture Cancel too, so INV-4's real-widget leg can click it directly.
        self._cancel: QPushButton = buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        # exec()-driven, so accept itself (unlike backup_export, whose OK emits a
        # signal); wire reject too so Cancel actually aborts.
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._field.textChanged.connect(self._sync_ok)

        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        # Keep DELETE un-translated — it is the literal to type (CONFIRM_WORD).
        layout.addWidget(QLabel(self.tr("Type DELETE to confirm")))
        layout.addWidget(self._field)
        layout.addWidget(buttons)

        self._sync_ok()  # initial state: disabled

    @Slot()
    def _sync_ok(self) -> None:
        self._ok.setEnabled(self._field.text() == CONFIRM_WORD)
