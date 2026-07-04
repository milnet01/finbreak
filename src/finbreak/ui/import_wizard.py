"""Import-wizard screen — pick a file + account, map columns (or auto-match a
saved profile), preview, and import (FIBR-0007 D9/INV-10).

A **non-modal** stacked ``QWidget`` (not a ``QDialog``/``QWizard``), so the idle
auto-lock can swap it away like any other screen (app.py comments). Its three
steps live in an internal ``QStackedLayout``: (0) pick file + account; (1) map
columns — shown only when no saved profile matches; (2) preview + confirm-period
+ Import. All strings go through ``tr()`` and every widget sits in a Qt layout
manager, so the screen is translation-ready and RTL-safe (coding.md § 5.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QDate, QSignalBlocker, Qt, Signal, Slot
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import FinbreakError
from finbreak.importers.base import ParseResult
from finbreak.importers.csv_importer import read_header
from finbreak.importers.ofx_importer import OfxImporter
from finbreak.models import ColumnMapping, OfxAccountInfo
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportPreview, ImportService
from finbreak.services.transactions import read_minor_unit_exponent, to_display_decimal

_STEP_PICK, _STEP_MAP, _STEP_PREVIEW = 0, 1, 2
_ERROR_ROW_BRUSH = QBrush(QColor(122, 59, 59))  # muted red — flags a RowError row


class ImportWizardWidget(QWidget):
    done = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._imports = ImportService(service.vault)
        self._accounts = AccountService(service.vault)
        # The currency scale, for rendering preview amounts as decimals (not raw
        # minor units) — the same value the importer/service use (reuse, § 1.3).
        self._exponent = read_minor_unit_exponent(service.vault.connection)

        self.setWindowTitle(self.tr("Import transactions"))

        self._text: str | None = None
        self._header: list[str] = []
        self._source_path: str = ""
        self._preview: ImportPreview | None = None
        # OFX only (FIBR-0008): the parsed statements of the picked file, so the
        # chooser can re-preview a selected one without re-parsing. Empty on the
        # CSV path (reset on every CSV pick).
        self._ofx_statements: list[tuple[OfxAccountInfo, ParseResult]] = []

        self._stack = QStackedLayout()
        self._error = QLabel()
        self._stack.addWidget(self._build_pick_step())
        self._stack.addWidget(self._build_map_step())
        self._stack.addWidget(self._build_preview_step())

        outer = QVBoxLayout(self)
        outer.addLayout(self._stack)
        outer.addWidget(self._error)

        self._goto_step(_STEP_PICK)

    # -- step 0: pick file + account -----------------------------------------
    def _build_pick_step(self) -> QWidget:
        page = QWidget()
        self._account_combo = QComboBox()
        for account in self._accounts.list_accounts():
            self._account_combo.addItem(account.name, account.id)
        self._pick_button = QPushButton(self.tr("Choose a statement file…"))
        cancel = QPushButton(self.tr("Cancel"))

        form = QFormLayout()
        form.addRow(self.tr("Import into account"), self._account_combo)
        form.addRow(self.tr("Statement file"), self._pick_button)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)

        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addLayout(buttons)

        self._pick_button.clicked.connect(self._on_pick_file)
        cancel.clicked.connect(self.done)
        return page

    # -- step 1: map columns --------------------------------------------------
    def _build_map_step(self) -> QWidget:
        page = QWidget()
        self._column_combos: dict[str, QComboBox] = {
            role: QComboBox()
            for role in ("date", "description", "amount", "debit", "credit")
        }
        self._amount_style = QComboBox()
        self._amount_style.addItem(self.tr("Single amount column"), "single")
        self._amount_style.addItem(
            self.tr("Separate debit / credit columns"), "debit_credit"
        )
        self._invert_amount = QCheckBox(
            self.tr("Amounts are reversed (debits are positive)")
        )
        self._date_format = QLineEdit("%Y-%m-%d")
        self._profile_name = QLineEdit()
        self._profile_name.setPlaceholderText(
            self.tr("Save this layout as… (optional)")
        )
        self._map_next_button = QPushButton(self.tr("Preview"))
        cancel = QPushButton(self.tr("Cancel"))

        form = QFormLayout()
        form.addRow(self.tr("Date column"), self._column_combos["date"])
        form.addRow(self.tr("Description column"), self._column_combos["description"])
        form.addRow(self.tr("Amount style"), self._amount_style)
        form.addRow(self.tr("Amount column"), self._column_combos["amount"])
        form.addRow(self.tr("Debit column"), self._column_combos["debit"])
        form.addRow(self.tr("Credit column"), self._column_combos["credit"])
        form.addRow(self.tr("Invert"), self._invert_amount)
        form.addRow(self.tr("Date format"), self._date_format)
        form.addRow(self.tr("Profile name"), self._profile_name)

        buttons = QHBoxLayout()
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(self._map_next_button)

        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addLayout(buttons)

        self._map_next_button.clicked.connect(self._on_map_next)
        cancel.clicked.connect(self.done)
        return page

    # -- step 2: preview ------------------------------------------------------
    def _build_preview_step(self) -> QWidget:
        page = QWidget()
        # OFX-only statement chooser (FIBR-0008 D8) — shown only for a
        # multi-account file; selecting an entry re-previews that statement.
        self._ofx_statement_combo = QComboBox()
        self._ofx_statement_combo.hide()
        self._ofx_statement_combo.currentIndexChanged.connect(
            self._on_ofx_statement_changed
        )
        self._preview_table = QTableWidget(0, 5)
        self._preview_table.setHorizontalHeaderLabels(
            [
                self.tr("Row"),
                self.tr("Date"),
                self.tr("Amount"),
                self.tr("Description"),
                self.tr("Status"),
            ]
        )
        self._preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._summary_label = QLabel()
        self._period_start = QDateEdit()
        self._period_start.setCalendarPopup(True)
        self._period_end = QDateEdit()
        self._period_end.setCalendarPopup(True)
        self._import_button = QPushButton(self.tr("Import"))
        self._import_button.setEnabled(False)
        cancel = QPushButton(self.tr("Cancel"))

        period = QFormLayout()
        period.addRow(self.tr("Period start"), self._period_start)
        period.addRow(self.tr("Period end"), self._period_end)

        buttons = QHBoxLayout()
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(self._import_button)

        layout = QVBoxLayout(page)
        layout.addWidget(self._ofx_statement_combo)
        layout.addWidget(self._preview_table)
        layout.addWidget(self._summary_label)
        layout.addLayout(period)
        layout.addLayout(buttons)

        self._import_button.clicked.connect(self._on_import)
        cancel.clicked.connect(self.done)
        return page

    # -- navigation / actions -------------------------------------------------
    def _goto_step(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    @Slot()
    def _on_pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Choose a statement file"),
            "",
            self.tr("Statement files (*.csv *.ofx *.qfx);;All files (*)"),
        )
        if path:
            self._select_file(path)

    def _select_file(self, path: str) -> None:
        """Load the picked file and route by format. **OFX** (FIBR-0008 D10):
        parse and jump straight to the preview, **skipping** the mapping step
        (self-describing). **CSV** (FIBR-0007): an exact-signature match
        auto-applies its profile and jumps to the preview (INV-10a); no match
        shows the mapping step (INV-10b)."""
        self._error.clear()
        self._source_path = path
        self._account_id = self._account_combo.currentData()
        if self._looks_like_ofx(path):
            self._select_ofx(path)
            return
        # CSV path — reset any OFX chooser state so a prior OFX pick's chooser
        # never lingers when switching to a CSV file (FIBR-0008 wizard step 7).
        # Clear THEN hide: the empty _ofx_statements makes the clear()'s
        # currentIndexChanged(-1) a no-op in _on_ofx_statement_changed's guard.
        self._ofx_statements = []
        self._ofx_statement_combo.clear()
        self._ofx_statement_combo.hide()
        try:
            text = self._imports.read_file(path)
            header = read_header(text)  # raises ValueError on an empty file
            matched = self._imports.match_profile(header)  # raises on dup-named header
        except (ValueError, OSError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._text = text
        self._header = header
        self._populate_mapping_combos(header)
        if matched is not None:
            self._run_preview(matched.column_mapping())
        else:
            self._goto_step(_STEP_MAP)

    @staticmethod
    def _looks_like_ofx(path: str) -> bool:
        """OFX detection (FIBR-0008 D10): by extension (``.ofx``/``.qfx``), with a
        **bounded** content-sniff fallback (the first 512 bytes only — never the
        whole file, so the size cap can't be bypassed by the sniff) for a
        mis-named file. A ``.csv`` extension is always CSV."""
        lower = path.lower()
        if lower.endswith((".ofx", ".qfx")):
            return True
        if lower.endswith(".csv"):
            return False
        try:
            with Path(path).open("rb") as fh:
                head = fh.read(512).lstrip().upper()
        except OSError:
            return False  # a missing/unreadable file falls through to the CSV path,
            # which re-reads it and surfaces the OSError as a shown message.
        return head.startswith(b"OFXHEADER") or b"<OFX" in head

    def _select_ofx(self, path: str) -> None:
        """Read (size-capped, D13) + parse the OFX file, populate the statement
        chooser (shown only for a multi-account file, D8), and preview the first
        statement. A malformed / statement-less / oversized file surfaces its
        friendly ``ValueError`` as a shown message (INV-4/INV-10)."""
        try:
            data = self._imports.read_file_bytes(path)  # size-capped read (D13)
            statements = OfxImporter().parse(data, self._exponent)
        except (ValueError, OSError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        # Single reassignment displaces any prior file's list (the "reset").
        self._ofx_statements = statements
        combo = self._ofx_statement_combo
        with QSignalBlocker(combo):  # don't fire currentIndexChanged mid-populate
            combo.clear()
            for index, (info, _result) in enumerate(statements):
                label = (
                    f"{info.account_id} · {info.account_type}"
                    if info.account_type
                    else info.account_id
                )
                combo.addItem(label, index)
        # Shown for >1 statement, hidden for a single one — set explicitly on
        # every OFX pick, so a prior file's visibility never leaks (D8).
        combo.setVisible(len(statements) > 1)
        self._preview_ofx_statement(0)

    def _preview_ofx_statement(self, index: int) -> None:
        _info, result = self._ofx_statements[index]
        try:
            preview = self._imports.preview_ofx(result, self._account_id)
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._show_preview(preview)

    @Slot(int)
    def _on_ofx_statement_changed(self, index: int) -> None:
        # Re-preview the chosen statement (no separate "Next" button, INV-7e).
        if 0 <= index < len(self._ofx_statements):
            self._error.clear()
            self._preview_ofx_statement(index)

    def _populate_mapping_combos(self, header: list[str]) -> None:
        for combo in self._column_combos.values():
            combo.clear()
            for name in header:
                combo.addItem(name, name)

    @Slot()
    def _on_map_next(self) -> None:
        self._error.clear()
        mapping = self._mapping_from_form()
        name = self._profile_name.text().strip()
        if name:
            try:
                self._imports.save_profile(name, self._header, mapping)
            except (ValueError, FinbreakError) as exc:
                self._error.setText(str(exc))
                return
        self._run_preview(mapping)

    def _mapping_from_form(self) -> ColumnMapping:
        style = self._amount_style.currentData()
        date_col = self._column_combos["date"].currentData()
        desc_col = self._column_combos["description"].currentData()
        date_format = self._date_format.text().strip()
        invert = self._invert_amount.isChecked()
        if style == "single":
            return ColumnMapping(
                date_col,
                desc_col,
                self._column_combos["amount"].currentData(),
                None,
                None,
                date_format,
                invert,
            )
        return ColumnMapping(
            date_col,
            desc_col,
            None,
            self._column_combos["debit"].currentData(),
            self._column_combos["credit"].currentData(),
            date_format,
            invert,
        )

    def _run_preview(self, mapping: ColumnMapping) -> None:
        # _run_preview is only reached after _select_file loads the text (CSV).
        text = cast(str, self._text)
        try:
            preview = self._imports.preview(text, mapping, self._account_id)
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._show_preview(preview)

    def _show_preview(self, preview: ImportPreview) -> None:
        """Render a preview + go to the preview step — the shared step the CSV
        driver (``_run_preview``) and the OFX path (``_preview_ofx_statement``)
        both call (FIBR-0008 D2 wizard seam). Owns the ``self._preview`` stash
        ``_on_import`` reads (else an Import press would silently no-op)."""
        self._preview = preview
        self._fill_preview_table(preview)
        self._summary_label.setText(
            self.tr("{new} new · {dup} duplicate · {err} error").format(
                new=preview.new_count,
                dup=preview.duplicate_count,
                err=len(preview.errors),
            )
        )
        self._set_period_defaults(preview)
        # Import stays enabled when there are drafts OR a coverage period to
        # record — so an all-duplicate CSV and a quiet-month OFX (zero drafts,
        # embedded span, FIBR-0008 D14) both keep Import live. Equivalent for CSV
        # (a CSV with zero drafts has period_start == None, INV-9).
        self._import_button.setEnabled(
            len(preview.drafts) > 0 or preview.period_start is not None
        )
        self._goto_step(_STEP_PREVIEW)

    def _fill_preview_table(self, preview: ImportPreview) -> None:
        # Interleave drafts + errors back into file order by row_number, so the
        # preview shows every data row and flags the error rows (INV-10c).
        entries: list[tuple[int, bool, list[str]]] = []
        for draft in preview.drafts:
            entries.append(
                (
                    draft.row_number,
                    False,
                    [
                        str(draft.row_number),
                        draft.occurred_on,
                        # Render the decimal amount (e.g. -10.00), not the raw
                        # minor units (-1000) — this preview is read by a person
                        # checking a statement before import. No float (D1).
                        str(to_display_decimal(draft.amount_minor, self._exponent)),
                        draft.description,
                        self.tr("OK"),
                    ],
                )
            )
        for err in preview.errors:
            entries.append(
                (
                    err.row_number,
                    True,
                    [str(err.row_number), "", "", err.reason, self.tr("Error")],
                )
            )
        entries.sort(key=lambda entry: entry[0])
        self._preview_table.setRowCount(len(entries))
        for row, (_row_number, is_error, cells) in enumerate(entries):
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if is_error:
                    item.setBackground(_ERROR_ROW_BRUSH)
                self._preview_table.setItem(row, col, item)

    def _set_period_defaults(self, preview: ImportPreview) -> None:
        if preview.period_start is not None and preview.period_end is not None:
            self._period_start.setDate(
                QDate.fromString(preview.period_start, Qt.DateFormat.ISODate)
            )
            self._period_end.setDate(
                QDate.fromString(preview.period_end, Qt.DateFormat.ISODate)
            )
        else:  # zero drafts — unused, Import is disabled
            today = QDate.currentDate()
            self._period_start.setDate(today)
            self._period_end.setDate(today)

    @Slot()
    def _on_import(self) -> None:
        self._error.clear()
        if self._preview is None:
            return
        period_start = self._period_start.date().toString(Qt.DateFormat.ISODate)
        period_end = self._period_end.date().toString(Qt.DateFormat.ISODate)
        try:
            self._imports.commit_import(
                self._preview, period_start, period_end, self._source_path
            )
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self.done.emit()
