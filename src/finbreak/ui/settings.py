"""SettingsDialog — app preferences (FIBR-0055).

A modal ``QDialog`` opened by the **File → Settings…** action. Its priority
control is the **auto-lock timeout**: a combo of the offered choices
(``ALLOWED_AUTO_LOCK_MINUTES``), preselected to the current value. On **Save** it
calls ``AuthService.set_auto_lock_minutes`` (which persists the value in the vault
``settings`` table and re-arms the running idle timer) and emits ``saved`` — the
shell owns the close, mirroring ``ManualEntryDialog``. The base currency is shown
**read-only** (its value is passed in by the shell; the dialog holds no vault
reference). Shown non-blocking (``setModal(True)`` + ``show()``) and tracked by the
shell so an idle auto-lock closes it before the vault shuts (INV-7).
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from finbreak.services.auth import ALLOWED_AUTO_LOCK_MINUTES, AuthService


class SettingsDialog(QDialog):
    saved = Signal()

    def __init__(
        self,
        service: AuthService,
        base_currency: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._service = service
        self.setWindowTitle(self.tr("Settings"))

        # Per-value tr() literals — never self.tr(variable), which lupdate cannot
        # extract (FIBR-0051 D8/INV-10). Keyed by minutes; each ALLOWED value has one.
        labels = {
            1: self.tr("1 minute"),
            5: self.tr("5 minutes"),
            10: self.tr("10 minutes"),
            15: self.tr("15 minutes"),
            30: self.tr("30 minutes"),
        }
        self._combo = QComboBox()
        self._combo.setObjectName("settings_auto_lock")
        for minutes in ALLOWED_AUTO_LOCK_MINUTES:
            self._combo.addItem(labels[minutes], minutes)  # userData is the int
        # auto_lock_minutes() always returns a member of ALLOWED (INV-1 normalises
        # absent/garbage/out-of-set to DEFAULT, which D6 pins in ALLOWED), so findData
        # resolves. The >= 0 guard is belt-and-braces: a miss would safe-fail to index
        # 0 (the most-aggressive lock), never a weaker one.
        current = self._combo.findData(service.auto_lock_minutes())
        if current >= 0:
            self._combo.setCurrentIndex(current)

        # Read-only display of the vault's base currency (a plain QLabel).
        self._currency = QLabel(base_currency)
        self._currency.setObjectName("settings_currency")

        form = QFormLayout()
        form.addRow(self.tr("Auto-lock after"), self._combo)
        form.addRow(self.tr("Base currency"), self._currency)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Save"))
        # Ok drives _on_save (which emits saved; the shell owns the close), NOT
        # accept() — mirrors the ManualEntryDialog pattern.
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @Slot()
    def _on_save(self) -> None:
        self._service.set_auto_lock_minutes(self._combo.currentData())
        self.saved.emit()
