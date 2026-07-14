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
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.datetime_format import system_timezone_id
from finbreak.errors import VaultLockedError
from finbreak.services.auth import (
    ALLOWED_AUTO_LOCK_MINUTES,
    AmountPrefs,
    AuthService,
)
from finbreak.ui import theme
from finbreak.ui._datetime_prefs import (
    populate_datetime_combos,
    read_datetime_prefs,
    system_date_sample_label,
    system_time_sample_label,
)
from finbreak.ui._widgets import select_combo_data


class SettingsDialog(QDialog):
    saved = Signal()
    # "Export backup…" was clicked; the shell owns the password dialog + the
    # synchronous export (FIBR-0014 D3 — export lives only in Settings, INV-8).
    export_backup_requested = Signal()

    def __init__(
        self,
        service: AuthService,
        base_currency: str,
        parent: QWidget | None = None,
        *,
        update_enabled: bool = False,
        update_supported: bool = False,
        theme_controller: theme.ThemeController | None = None,
    ):
        super().__init__(parent)
        self._service = service
        self._theme_controller = theme_controller
        self.setWindowTitle(self.tr("Settings"))

        # Per-value tr() literals — never self.tr(variable), which lupdate cannot
        # extract (FIBR-0051 D8/INV-10). Keyed by minutes; each ALLOWED value has one.
        labels = {
            1: self.tr("1 minute"),
            5: self.tr("5 minutes"),
            10: self.tr("10 minutes"),
            15: self.tr("15 minutes"),
            30: self.tr("30 minutes"),
            0: self.tr("Never"),  # FIBR-0135 — idle auto-lock off (manual lock holds)
        }
        self._combo = QComboBox()
        self._combo.setObjectName("settings_auto_lock")
        for minutes in ALLOWED_AUTO_LOCK_MINUTES:
            self._combo.addItem(labels[minutes], minutes)  # userData is the int
        # auto_lock_minutes() always returns a member of ALLOWED (INV-1 normalises
        # absent/garbage/out-of-set to DEFAULT, which D6 pins in ALLOWED), so findData
        # resolves. The >= 0 guard is belt-and-braces: a miss would safe-fail to index
        # 0 (the most-aggressive lock), never a weaker one.
        select_combo_data(self._combo, service.auto_lock_minutes())

        # The FIBR-0083 timezone / date / time controls. The System-default label
        # is the only tr()-wrapped text (the detected value interpolated via a
        # placeholder, never self.tr(variable) — INV-7); every other item is data.
        self._timezone = QComboBox()
        self._timezone.setObjectName("settings_timezone")
        self._date_format = QComboBox()
        self._date_format.setObjectName("settings_date_format")
        self._time_format = QComboBox()
        self._time_format.setObjectName("settings_time_format")
        populate_datetime_combos(
            self._timezone,
            self._date_format,
            self._time_format,
            system_tz_label=self.tr("System default ({detected})").format(
                detected=system_timezone_id()
            ),
            system_date_label=self.tr("System default ({detected})").format(
                detected=system_date_sample_label()
            ),
            system_time_label=self.tr("System default ({detected})").format(
                detected=system_time_sample_label()
            ),
            current=service.datetime_prefs(),
        )

        # The FIBR-0105 amount-display controls: a 2-item combo for the negative
        # sign style (userData = the stored token, preselected to the current pref)
        # and a colour checkbox. The combo labels use the ASCII hyphen-minus, the
        # same glyph the formatter emits, so the advert matches the cell (D4).
        amount = service.amount_prefs()
        self._amount_negative = QComboBox()
        self._amount_negative.setObjectName("settings_amount_negative")
        self._amount_negative.addItem(self.tr("Minus (-)"), "minus")
        self._amount_negative.addItem(self.tr("Brackets ( )"), "brackets")
        select_combo_data(self._amount_negative, amount.negative_style)
        self._amount_colour = QCheckBox(self.tr("Colour amounts red/green"))
        self._amount_colour.setObjectName("settings_amount_colour")
        self._amount_colour.setChecked(amount.colour)

        # Read-only display of the vault's base currency (a plain QLabel).
        self._currency = QLabel(base_currency)
        self._currency.setObjectName("settings_currency")

        # The opt-in update check (FIBR-0054 D5). Disabled + explained off an
        # AppImage, where self-update can't run (INV-7). The dialog holds NO
        # UpdateService reference — it only reports the checkbox state on Save.
        self._update_checkbox = QCheckBox(self.tr("Check for updates on startup"))
        self._update_checkbox.setObjectName("settings_check_updates")
        self._update_checkbox.setChecked(update_enabled)
        if not update_supported:
            self._update_checkbox.setEnabled(False)
            self._update_checkbox.setToolTip(
                self.tr(
                    "Automatic updates are available only in the packaged "
                    "app (the Linux AppImage or the Windows build)."
                )
            )

        # The FIBR-0127 theme picker — an immediate-apply control (not Save/Cancel
        # data, D4): "Follow system" then the six themes grouped Light-then-Dark by
        # is_dark (INV-9), preselected to the current pref. Present only when the
        # shell handed us a controller (D10). The theme names are data (INV-13).
        self._theme_combo: QComboBox | None = None
        if theme_controller is not None:
            self._theme_combo = QComboBox()
            self._theme_combo.setObjectName("settings_theme")
            self._theme_combo.addItem(self.tr("Follow system"), "system")
            lights = [t for t in theme.THEMES.items() if not t[1].tokens.is_dark]
            darks = [t for t in theme.THEMES.items() if t[1].tokens.is_dark]
            for theme_id, theme_def in (*lights, *darks):
                self._theme_combo.addItem(theme_def.name, theme_id)
            select_combo_data(self._theme_combo, theme.load_theme_pref())
            # Connect AFTER populate + preselect: the index moves above would else
            # fire set_theme and clobber the pinned pref just by opening (INV-8).
            self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        form = QFormLayout()
        if self._theme_combo is not None:
            form.addRow(self.tr("Theme"), self._theme_combo)
        form.addRow(self.tr("Auto-lock after"), self._combo)
        form.addRow(self.tr("Time zone"), self._timezone)
        form.addRow(self.tr("Date format"), self._date_format)
        form.addRow(self.tr("Time format"), self._time_format)
        form.addRow(self.tr("Negative amounts"), self._amount_negative)
        form.addRow("", self._amount_colour)
        form.addRow(self.tr("Base currency"), self._currency)
        form.addRow("", self._update_checkbox)

        # Encrypted backup export (FIBR-0014 D3). The button only signals intent;
        # the shell collects the backup password and runs the export, so Settings
        # keeps no BackupService reference.
        self._export_backup = QPushButton(self.tr("Export backup…"))
        self._export_backup.setObjectName("settings_export_backup")
        self._export_backup.clicked.connect(self.export_backup_requested)
        form.addRow(self.tr("Encrypted backup"), self._export_backup)

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

    def update_enabled(self) -> bool:
        """The checkbox state — read by the shell on Save to persist the opt-in
        flag via ``UpdateService.set_enabled`` (D5). The dialog itself writes
        nothing networked."""
        return self._update_checkbox.isChecked()

    @Slot(int)
    def _on_theme_changed(self, _index: int) -> None:
        # Immediate apply + persist via the controller (D4), independent of
        # Save/Cancel. currentData() is the selected theme id (or "system").
        if self._theme_controller is None or self._theme_combo is None:
            return
        self._theme_controller.set_theme(self._theme_combo.currentData())

    @Slot()
    def _on_save(self) -> None:
        try:
            self._service.set_auto_lock_minutes(self._combo.currentData())
            self._service.set_datetime_prefs(
                read_datetime_prefs(
                    self._timezone, self._date_format, self._time_format
                )
            )
            self._service.set_amount_prefs(
                AmountPrefs(
                    self._amount_negative.currentData(),
                    self._amount_colour.isChecked(),
                )
            )
        except VaultLockedError:
            # An idle auto-lock can fire while this non-modal dialog is open; a
            # settings write then reads a locked vault. Return silently (the shell
            # tears the dialog down), matching every other handler instead of
            # crashing the slot. (indie-review UI-dialogs H1; FIBR-0083 D3)
            return
        self.saved.emit()
