"""ExportDialog — choose what goes in the PDF report and (optionally) lock it.

FIBR-0013 D7. A vault-free ``QDialog`` (handed the account list + the Home
pre-fill, like ``SettingsDialog``): a period selector (Home's five modes), an
**Accounts** checkbox list under an **All accounts** master toggle, three
**section** checkboxes, a **Theme** Light/Dark pair, and a **password** + confirm
pair with a single Show toggle. ``options()`` returns the chosen ``ExportOptions``
after an accepted ``exec()``.

Gating (INV-14): **Export…** is enabled iff ≥ 1 section ∧ ≥ 1 account ∧ the
password field is empty **or** (≥ ``MIN_EXPORT_PASSWORD_LEN`` chars ∧ equals
Confirm). The password is used **verbatim** (never ``.strip()``-ed), so an
all-whitespace password of sufficient length is permitted; a **blank** field wins
— Confirm is ignored and the export is unencrypted (INV-1). The disabled button
carries the one-line reason as its tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from finbreak.models import Account
from finbreak.services.pdf_export import ExportOptions
from finbreak.services.reporting import (
    MODE_CURRENT_MONTH,
    MODE_PREVIOUS_MONTH,
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    MODE_YEAR_TO_DATE,
    ReportPrefs,
)

# The minimum length enforced when a password IS set (blank stays allowed, INV-14).
MIN_EXPORT_PASSWORD_LEN = 8


class ExportDialog(QDialog):
    # Emitted when Export… is clicked. The shell pops the save dialog and runs the
    # export; the dialog stays open until that succeeds (D9), so — like
    # SettingsDialog's `saved` — Ok does NOT auto-accept/close.
    export_requested = Signal()

    def __init__(
        self,
        accounts: list[Account],
        prefs: ReportPrefs,
        selected_account_id: int | None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export report as PDF"))
        self._accounts = accounts

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_period(prefs))
        layout.addWidget(self._build_accounts())
        layout.addWidget(self._build_sections())
        layout.addWidget(self._build_theme())
        layout.addWidget(self._build_password())

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._export_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._export_btn.setText(self.tr("Export…"))
        self._buttons.accepted.connect(self.export_requested)  # not accept() — D9
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        # Pre-fill accounts LAST — after every gated widget exists — because
        # ticking "All accounts" fires the toggle handler, which reads them all.
        self._apply_account_prefill(selected_account_id)

    # -- construction ---------------------------------------------------------

    def _build_period(self, prefs: ReportPrefs) -> QWidget:
        box = QGroupBox(self.tr("Period"))
        form = QFormLayout(box)
        self._period_selector = QComboBox()
        for label, mode in (
            (self.tr("Previous month"), MODE_PREVIOUS_MONTH),
            (self.tr("Current month"), MODE_CURRENT_MONTH),
            (self.tr("Specific month"), MODE_SPECIFIC_MONTH),
            (self.tr("Year to date"), MODE_YEAR_TO_DATE),
            (self.tr("Specific year"), MODE_SPECIFIC_YEAR),
        ):
            self._period_selector.addItem(label, mode)
        self._month_picker = QComboBox()
        for month in range(1, 13):
            self._month_picker.addItem(f"{month:02d}", month)
        self._year_picker = QSpinBox()
        self._year_picker.setRange(1970, 9999)
        # Pre-fill from Home's current selection (INV-7).
        from datetime import date

        today = date.today()
        self._period_selector.setCurrentIndex(
            max(0, self._period_selector.findData(prefs.mode))
        )
        self._year_picker.setValue(prefs.year or today.year)
        self._month_picker.setCurrentIndex(
            max(0, self._month_picker.findData(prefs.month or today.month))
        )
        self._period_selector.currentIndexChanged.connect(self._sync_period_pickers)
        form.addRow(self.tr("Period"), self._period_selector)
        form.addRow(self.tr("Month"), self._month_picker)
        form.addRow(self.tr("Year"), self._year_picker)
        self._sync_period_pickers()
        return box

    def _build_accounts(self) -> QWidget:
        box = QGroupBox(self.tr("Accounts"))
        col = QVBoxLayout(box)
        self._all_accounts_check = QCheckBox(self.tr("All accounts"))
        self._all_accounts_check.toggled.connect(self._on_all_accounts_toggled)
        col.addWidget(self._all_accounts_check)
        self._account_checks: dict[int, QCheckBox] = {}
        for account in sorted(self._accounts, key=lambda a: a.name):
            chk = QCheckBox(account.name)
            chk.toggled.connect(self._update_export_enabled)
            self._account_checks[account.id] = chk
            col.addWidget(chk)
        return box

    def _apply_account_prefill(self, selected_account_id: int | None) -> None:
        # None ⇒ All ticked (its handler disables the rows); a specific id ⇒ All
        # unticked, that one row ticked, the rest unticked (D7).
        if selected_account_id is None:
            self._all_accounts_check.setChecked(True)
        else:
            for aid, chk in self._account_checks.items():
                chk.setChecked(aid == selected_account_id)
        self._update_export_enabled()

    def _build_sections(self) -> QWidget:
        box = QGroupBox(self.tr("Sections"))
        col = QVBoxLayout(box)
        self._summary_check = QCheckBox(self.tr("Summary"))
        self._charts_check = QCheckBox(self.tr("Charts"))
        self._transactions_check = QCheckBox(self.tr("Transactions"))
        for chk in (self._summary_check, self._charts_check, self._transactions_check):
            chk.setChecked(True)
            chk.toggled.connect(self._update_export_enabled)
            col.addWidget(chk)
        return box

    def _build_theme(self) -> QWidget:
        box = QGroupBox(self.tr("Theme"))
        col = QVBoxLayout(box)
        self._light_radio = QRadioButton(self.tr("Light"))
        self._dark_radio = QRadioButton(self.tr("Dark"))
        self._light_radio.setChecked(True)  # Light default (D10)
        group = QButtonGroup(self)
        group.addButton(self._light_radio)
        group.addButton(self._dark_radio)
        col.addWidget(self._light_radio)
        col.addWidget(self._dark_radio)
        return box

    def _build_password(self) -> QWidget:
        box = QGroupBox(self.tr("Password (optional)"))
        outer = QVBoxLayout(box)
        form = QFormLayout()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.textChanged.connect(self._update_export_enabled)
        self._confirm.textChanged.connect(self._update_export_enabled)
        form.addRow(self.tr("Password"), self._password)
        form.addRow(self.tr("Confirm"), self._confirm)
        self._show_check = QCheckBox(self.tr("Show password"))
        self._show_check.toggled.connect(self._on_show_toggled)
        self._helper = QLabel(
            self.tr(
                "Leave blank for no password. A set password must be at least "
                "{n} characters and cannot be recovered."
            ).format(n=MIN_EXPORT_PASSWORD_LEN)
        )
        self._helper.setWordWrap(True)
        outer.addLayout(form)
        outer.addWidget(self._show_check)
        outer.addWidget(self._helper)
        return box

    # -- state machine --------------------------------------------------------

    def _sync_period_pickers(self) -> None:
        mode = self._period_selector.currentData()
        self._month_picker.setVisible(mode == MODE_SPECIFIC_MONTH)
        self._year_picker.setVisible(mode in (MODE_SPECIFIC_MONTH, MODE_SPECIFIC_YEAR))

    def _on_all_accounts_toggled(self, checked: bool) -> None:
        # All ticked ⇒ rows disabled (their state is not meaningful, options() is
        # None). Unticking ⇒ rows enabled and every row pre-ticked (D7).
        for chk in self._account_checks.values():
            chk.setEnabled(not checked)
            if not checked:
                chk.setChecked(True)
        self._update_export_enabled()

    def _on_show_toggled(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self._password.setEchoMode(mode)
        self._confirm.setEchoMode(mode)

    def _disabled_reason(self) -> str | None:
        if not any(
            c.isChecked()
            for c in (
                self._summary_check,
                self._charts_check,
                self._transactions_check,
            )
        ):
            return self.tr("Choose at least one section to include.")
        if self._account_ids_selection_count() < 1:
            return self.tr("Choose at least one account.")
        pw = self._password.text()  # verbatim — never stripped (INV-14)
        if pw:
            if len(pw) < MIN_EXPORT_PASSWORD_LEN:
                return self.tr("Password must be at least {n} characters.").format(
                    n=MIN_EXPORT_PASSWORD_LEN
                )
            if pw != self._confirm.text():
                return self.tr("The passwords don't match.")
        return None

    def _account_ids_selection_count(self) -> int:
        if self._all_accounts_check.isChecked():
            return len(self._account_checks)
        return sum(1 for c in self._account_checks.values() if c.isChecked())

    def _update_export_enabled(self) -> None:
        reason = self._disabled_reason()
        self._export_btn.setEnabled(reason is None)
        self._export_btn.setToolTip(reason or "")

    # -- results --------------------------------------------------------------

    def _export_button(self) -> QPushButton:
        return self._export_btn

    def _current_prefs(self) -> ReportPrefs:
        mode = self._period_selector.currentData()
        if mode == MODE_SPECIFIC_MONTH:
            return ReportPrefs(
                mode,
                year=self._year_picker.value(),
                month=self._month_picker.currentData(),
            )
        if mode == MODE_SPECIFIC_YEAR:
            return ReportPrefs(mode, year=self._year_picker.value())
        return ReportPrefs(mode)

    def options(self) -> ExportOptions:
        """The chosen options (read after an accepted ``exec()``). ``account_ids``
        is ``None`` only when **All accounts** is ticked (INV-4); a blank password
        field yields ``None`` — Confirm is ignored (INV-1)."""
        if self._all_accounts_check.isChecked():
            account_ids: frozenset[int] | None = None
        else:
            account_ids = frozenset(
                aid for aid, c in self._account_checks.items() if c.isChecked()
            )
        pw = self._password.text()
        return ExportOptions(
            prefs=self._current_prefs(),
            account_ids=account_ids,
            include_summary=self._summary_check.isChecked(),
            include_charts=self._charts_check.isChecked(),
            include_transactions=self._transactions_check.isChecked(),
            theme="dark" if self._dark_radio.isChecked() else "light",
            password=pw or None,
        )
