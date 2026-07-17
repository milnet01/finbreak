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

import csv
import io
from datetime import datetime
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
from finbreak.importers.date_detect import KNOWN_DATE_FORMATS, detect_date_format
from finbreak.importers.ofx_importer import OfxImporter
from finbreak.importers.pdf_importer import (
    PasswordError,
    PdfError,
    PdfImporter,
    table_to_text,
)
from finbreak.importers.standard_bank import StandardBankImporter
from finbreak.models import ColumnMapping, ImportProfile, OfxAccountInfo
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportPreview, ImportService
from finbreak.services.transactions import read_minor_unit_exponent, to_display_decimal
from finbreak.ui.modal import show_modal
from finbreak.ui.password_dialog import PasswordDialog

_STEP_PICK, _STEP_MAP, _STEP_PREVIEW = 0, 1, 2
_ERROR_ROW_BRUSH = QBrush(QColor(122, 59, 59))  # muted red — flags a RowError row

_MAX_DATE_SAMPLES = 50  # detector sampling bound (FIBR-0146 D8)
_PREVIEW_SAMPLES = 3  # how many parsed dates the live preview shows (D6)
_CUSTOM_FORMAT = object()  # sentinel data for the "Custom…" combo entry (D4)


class _NeedPassword:
    """Sentinel type for ``_try_decrypt`` — returned when a password is needed. A
    distinct type (not ``object()``) so ``bytes | _NeedPassword | None`` resolves
    under mypy with ``from __future__ import annotations`` (FIBR-0065 D5)."""


_NEED_PASSWORD = _NeedPassword()


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
        # PDF only (FIBR-0009): the extracted candidate tables of the picked file,
        # so the table chooser can re-serialise a selected one. Empty off the PDF
        # path (reset on every pick).
        self._pdf_candidates: list[list[list[str | None]]] = []
        # FIBR-0146: True when auto-detect found two formats equally consistent
        # with the sampled dates (e.g. every day-number <= 12, so day-first and
        # month-first both parse) — drives the live-preview day/month nudge (D5/D6).
        # Set by _autodetect_date_format; cleared by any manual format change and
        # by a matched profile (authoritative, never "ambiguous").
        self._date_ambiguous: bool = False
        # PDF only (FIBR-0057): the (account_id, password) a "remember" persisted
        # during THIS import, under the provisional file-select account. If the
        # user then re-targets the import (preview step), the committed rows land
        # on a different account, so the password is carried there too on commit.
        self._stored_pw: tuple[int, str] | None = None

        self._stack = QStackedLayout()
        self._error = QLabel()
        self._stack.addWidget(self._build_pick_step())
        self._stack.addWidget(self._build_map_step())
        self._stack.addWidget(self._build_preview_step())

        outer = QVBoxLayout(self)
        outer.addLayout(self._stack)
        outer.addWidget(self._error)

        self._goto_step(_STEP_PICK)

    def _fill_account_combo(self, combo: QComboBox) -> None:
        """Populate an account picker (label = name, data = id). Shared by the
        pick step and the preview step's destination picker (FIBR-0057), so both
        list the same accounts in the same order."""
        for account in self._accounts.list_accounts():
            combo.addItem(account.name, account.id)

    # -- step 0: pick file + account -----------------------------------------
    def _build_pick_step(self) -> QWidget:
        page = QWidget()
        self._account_combo = QComboBox()
        self._fill_account_combo(self._account_combo)
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
        # PDF-only table chooser (FIBR-0009 D7) — shown only for a >1-table PDF,
        # above the mapping combos; selecting an entry re-serialises that table
        # into the preview text and re-runs profile matching.
        self._pdf_table_combo = QComboBox()
        self._pdf_table_combo.hide()
        self._pdf_table_combo.currentIndexChanged.connect(self._on_pdf_table_changed)
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
        # Date-format PICKER (FIBR-0146 D4) — a plain-English combo of example
        # dates, not a raw %-code box. Each entry's TEXT is the example string,
        # its DATA the strptime pattern (a language-neutral token, INV-5); a final
        # "Custom…" entry (data = the _CUSTOM_FORMAT sentinel) reveals a raw-pattern
        # field for an exotic bank (INV-4). Items are added BEFORE the signals are
        # connected so populating fires no slot.
        self._date_format = QComboBox()
        self._date_format.setObjectName("import_date_format")
        for example, fmt in KNOWN_DATE_FORMATS:
            self._date_format.addItem(example, fmt)
        self._date_format.addItem(self.tr("Custom…"), _CUSTOM_FORMAT)
        self._date_format_custom = QLineEdit()
        self._date_format_custom.setObjectName("import_date_format_custom")
        self._date_format_custom.setPlaceholderText(self.tr("e.g. %Y.%m.%d"))
        self._date_format_custom.hide()
        # Live "how the dates read" preview (D6) — the confirm affordance.
        self._date_preview = QLabel()
        self._date_preview.setObjectName("import_date_preview")
        self._date_preview.setWordWrap(True)
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
        form.addRow("", self._date_format_custom)
        form.addRow("", self._date_preview)
        form.addRow(self.tr("Profile name"), self._profile_name)

        buttons = QHBoxLayout()
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(self._map_next_button)

        layout = QVBoxLayout(page)
        layout.addWidget(self._pdf_table_combo)
        layout.addLayout(form)
        layout.addLayout(buttons)

        self._map_next_button.clicked.connect(self._on_map_next)
        cancel.clicked.connect(self.done)
        # FIBR-0146 D5/D6 single-owner wiring: a date-COLUMN change re-detects
        # (_on_date_column_changed); a FORMAT change (picker OR the custom field's
        # text) clears the ambiguity flag, shows/hides the custom field, then
        # refreshes the preview — both signals reach the ONE no-arg slot, so the
        # preview is refreshed by exactly one owner (never double).
        self._column_combos["date"].currentIndexChanged.connect(
            self._on_date_column_changed
        )
        self._date_format.currentIndexChanged.connect(self._on_date_format_changed)
        self._date_format_custom.textChanged.connect(self._on_date_format_changed)
        return page

    # -- step 2: preview ------------------------------------------------------
    def _build_preview_step(self) -> QWidget:
        page = QWidget()
        # Destination-account picker (FIBR-0057) — the import target, surfaced
        # + editable on the final step so a wrong default (snapshotted at
        # file-select) can be corrected before the irreversible Import; changing
        # it re-runs the dedup so the counts match the chosen account.
        self._confirm_account_combo = QComboBox()
        self._fill_account_combo(self._confirm_account_combo)
        self._confirm_account_combo.currentIndexChanged.connect(
            self._on_confirm_account_changed
        )
        # OFX-only statement chooser (FIBR-0008 D8) — shown only for a
        # multi-account file; selecting an entry re-previews that statement.
        self._ofx_statement_combo = QComboBox()
        self._ofx_statement_combo.hide()
        self._ofx_statement_combo.currentIndexChanged.connect(
            self._on_ofx_statement_changed
        )
        # Whole-import banner (FIBR-0146 D7) — shown only when nothing landed and
        # at least one row errored (the tester's 0 new · 0 dup · 165 error state),
        # turning N identical cryptic rows into one actionable sentence. Text set
        # once; visibility toggled in _apply_preview_counts.
        self._preview_banner = QLabel(
            self.tr(
                "None of the rows could be imported. Go back and check the column "
                "mapping and the Date format match your statement."
            )
        )
        self._preview_banner.setObjectName("import_preview_banner")
        self._preview_banner.setWordWrap(True)
        self._preview_banner.hide()
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
        # Unambiguous ISO-style YYYY/MM/DD in both period pickers. Date *input*
        # stays fixed here; the user-configurable *display* format shipped in
        # FIBR-0083 (Settings), which owns this now (not FIBR-0014).
        for _picker in (self._period_start, self._period_end):
            _picker.setDisplayFormat("yyyy/MM/dd")
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

        destination = QFormLayout()
        destination.addRow(self.tr("Import into account"), self._confirm_account_combo)

        layout = QVBoxLayout(page)
        layout.addLayout(destination)
        layout.addWidget(self._preview_banner)
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
            self.tr("Statement files (*.csv *.ofx *.qfx *.pdf);;All files (*)"),
        )
        if path:
            self._select_file(path)

    def _select_file(self, path: str) -> None:
        """Load the picked file and route by format. **OFX** (FIBR-0008 D10):
        parse and jump straight to the preview, **skipping** the mapping step
        (self-describing). **PDF** (FIBR-0009): extract candidate tables (locked
        PDFs decrypted in memory, prompting for a password), then show the map
        step with the table chooser. **CSV** (FIBR-0007): an exact-signature match
        auto-applies its profile and jumps to the preview (INV-10a); no match
        shows the mapping step (INV-10b)."""
        self._error.clear()
        self._source_path = path
        self._stored_pw = None  # a fresh file — drop any prior pick's remembered pw
        # Seed the preview step's destination picker from the pick-step choice
        # (FIBR-0057). The confirm combo is the single source of truth for the
        # committed account from here on — every preview + the PDF-password
        # lookup reads it via _target_account_id(), and the user can still
        # correct it on the preview step. Blocked so seeding fires no re-dedup.
        with QSignalBlocker(self._confirm_account_combo):
            self._confirm_account_combo.setCurrentIndex(
                self._confirm_account_combo.findData(self._account_combo.currentData())
            )
        # Reset BOTH choosers before the format dispatch (FIBR-0009 D7), so no
        # prior pick's chooser lingers on the shared map/preview steps — closing
        # both leak directions (OFX->PDF and PDF->CSV/OFX) a one-sided reset would
        # miss. Blocked clear() so the currentIndexChanged(-1) fires no slot.
        self._ofx_statements = []
        self._pdf_candidates = []
        for combo in (self._ofx_statement_combo, self._pdf_table_combo):
            with QSignalBlocker(combo):
                combo.clear()
            combo.hide()
        if self._looks_like_ofx(path):
            self._select_ofx(path)
            return
        if self._looks_like_pdf(path):
            self._select_pdf(path)
            return
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
            # FIBR-0146 D5(a): an unmatched CSV gets a date-format guess over the
            # (default) date column before the map step is shown.
            self._autodetect_date_format()
            self._update_date_preview()
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
            preview = self._imports.preview_result(result, self._target_account_id())
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

    @staticmethod
    def _looks_like_pdf(path: str) -> bool:
        """PDF detection (FIBR-0009 INV-7a): by ``.pdf`` extension, else a
        **bounded** content-sniff (the first 512 bytes, ``lstrip``ped, tested for
        the ``%PDF-`` magic — an ASCII literal, case-exact — never the whole file,
        so the size cap can't be bypassed by the sniff). A CSV/OFX extension is
        never PDF."""
        lower = path.lower()
        if lower.endswith(".pdf"):
            return True
        if lower.endswith((".csv", ".ofx", ".qfx")):
            return False
        try:
            with Path(path).open("rb") as fh:
                head = fh.read(512).lstrip()
        except OSError:
            return False  # a missing/unreadable file falls through to the CSV
            # path, which re-reads it and surfaces the OSError as a message.
        return head.startswith(b"%PDF-")

    def _select_pdf(self, path: str) -> None:
        """Read (size-capped, D10) + kick off the decrypt state machine (FIBR-0065
        D5). Locked PDFs prompt for a password **non-blocking**, so an idle
        auto-lock can never crash a post-prompt read; the flow continues in
        ``_continue_after_decrypt`` once plaintext is in hand."""
        try:
            data = self._imports.read_file_bytes(path)  # size-capped read (D10)
        except (ValueError, OSError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return
        self._begin_decrypt(data)

    def _show_pdf_read_error(self, exc: Exception) -> None:
        """A corrupt/unreadable PDF raises ``PdfError`` whose ``str`` is raw pikepdf
        internals (e.g. "unable to find trailer dictionary while recovering damaged
        file") — show OUR friendly message for it, not the library text (FIBR-0064).
        Our own ``ValueError`` / ``FinbreakError`` (size cap, format, …) already
        carry friendly messages, so those pass through unchanged."""
        if isinstance(exc, PdfError):
            self._error.setText(
                self.tr("Couldn't read this PDF — try your bank's CSV or OFX export.")
            )
        else:
            self._error.setText(str(exc))

    def _try_decrypt(
        self, data: bytes, password: str | None
    ) -> bytes | _NeedPassword | None:
        """One decrypt attempt — the single shared attempt+dispatch (FIBR-0065 D5).
        Returns the plaintext on success, the ``_NEED_PASSWORD`` sentinel on a
        bad/absent password, or ``None`` after surfacing a friendly message on any
        non-password error. The non-password-error catch lives **only** here, so
        every attempt (initial / stored / prompted) is covered by one test."""
        try:
            return PdfImporter.decrypt_to_plaintext(data, password)
        except PasswordError:
            return _NEED_PASSWORD
        except (PdfError, ValueError, OSError, FinbreakError) as exc:
            # A non-password decrypt failure (e.g. a corrupt file that passed the
            # %PDF- sniff — pikepdf.open raises PdfError, NOT a ValueError/OSError)
            # surfaces a friendly message instead of crashing the slot (coding.md
            # § 2; never crash the UI). PdfError's raw text is replaced (FIBR-0064).
            self._show_pdf_read_error(exc)
            return None

    def _begin_decrypt(self, data: bytes) -> None:
        """First decrypt attempt: no password, then the **stored** password once
        (FIBR-0009 INV-4), then prompt. Trying the stored password only here (entered
        once per import) structurally guarantees it is attempted at most once — never
        re-tried on a wrong-password re-prompt, which never re-enters this method."""
        result = self._try_decrypt(data, None)
        if isinstance(result, bytes):
            self._after_decrypt(result, None, remember=False)
        elif result is _NEED_PASSWORD:
            stored = self._accounts.get_pdf_password(self._target_account_id())
            if stored is None:
                self._prompt_pdf_password(data)
                return
            retry = self._try_decrypt(data, stored)
            if isinstance(retry, bytes):
                self._after_decrypt(retry, stored, remember=False)
            elif retry is _NEED_PASSWORD:
                self._prompt_pdf_password(data)
            # retry is None → a friendly message was already shown; stop
        # result is None → a friendly message was already shown; stop

    def _prompt_pdf_password(self, data: bytes) -> None:
        """Show the password dialog **non-blocking** (FIBR-0065). Cancel needs no
        slot — ``finished→deleteLater`` frees the dialog and the wizard stays on the
        pick step (the old 'cancel abandons the import cleanly'), storing nothing."""
        dialog = PasswordDialog(self._account_name(), self)
        show_modal(dialog, lambda: self._on_pdf_password(dialog, data))

    def _on_pdf_password(self, dialog: PasswordDialog, data: bytes) -> None:
        password, remember = dialog.password(), dialog.remember()
        result = self._try_decrypt(data, password)
        if isinstance(result, bytes):
            self._after_decrypt(result, password, remember)
        elif result is _NEED_PASSWORD:
            self._prompt_pdf_password(data)  # wrong password → re-prompt (INV-3)
        # result is None → a friendly message was already shown; stop

    def _after_decrypt(
        self, plaintext: bytes, password: str | None, remember: bool
    ) -> None:
        """Persist a **verified** password (decrypt just succeeded) iff the user
        asked to remember it — both writes inside the one ``remember and password``
        branch, so no ``(account_id, None)`` is ever stashed — then continue."""
        if remember and password:
            account_id = self._target_account_id()
            self._accounts.set_pdf_password(account_id, password)
            # Remember which account we stored it under (the provisional
            # file-select one), so a later re-target carries it across (FIBR-0057).
            self._stored_pw = (account_id, password)
        self._continue_after_decrypt(plaintext)

    def _continue_after_decrypt(self, plaintext: bytes) -> None:
        """Once plaintext is in hand: a recognised Standard Bank statement is parsed
        by the SB reader and jumps straight to preview (skipping the map step, like
        OFX); any other PDF falls through to the generic table extractor + the map
        step (D7)."""
        # FIBR-0050: a recognised SB statement skips mapping (self-describing, like
        # OFX). The checksum/format ValueError shows the friendly message, not crash.
        try:
            sb_result = StandardBankImporter().parse(plaintext, self._exponent)
            if sb_result is not None:
                self._show_preview(
                    self._imports.preview_result(sb_result, self._target_account_id())
                )
                return
        except (PdfError, ValueError, FinbreakError) as exc:
            self._show_pdf_read_error(exc)
            return
        candidates = self._extract_pdf_tables(plaintext)
        if candidates is None:
            return  # a friendly error was already surfaced
        self._pdf_candidates = candidates
        default = self._default_pdf_index(candidates)
        combo = self._pdf_table_combo
        with QSignalBlocker(combo):  # populate without firing _on_pdf_table_changed
            combo.clear()
            for index, candidate in enumerate(candidates):
                combo.addItem(
                    self.tr("Table {n} ({rows} rows)").format(
                        n=index + 1, rows=len(candidate) - 1
                    ),
                    index,
                )
            combo.setCurrentIndex(default)
        combo.setVisible(len(candidates) > 1)  # shown only for >1 (D7)
        matched = self._apply_pdf_table(default)
        if matched is not None:
            # A saved profile pre-fills the combos. A single candidate jumps to
            # preview (FIBR-0007 INV-10a reused); with >1 candidate the map step
            # is always shown so the user confirms the table (INV-6/INV-7d).
            self._apply_profile_to_combos(matched)
            if len(candidates) == 1:
                self._run_preview(matched.column_mapping())
                return
            self._update_date_preview()  # matched, >1 table: refresh for the map step
        else:
            # FIBR-0146 D5(b): a generic (non-SB) PDF gets a date-format guess.
            self._autodetect_date_format()
            self._update_date_preview()
        self._goto_step(_STEP_MAP)

    def _extract_pdf_tables(
        self, plaintext: bytes
    ) -> list[list[list[str | None]]] | None:
        """Extract the generic candidate tables from already-plaintext PDF bytes
        (FIBR-0050 D6 — the password loop lives in the ``_try_decrypt`` state
        machine, FIBR-0065). Returns the candidates, or ``None`` if a friendly "no
        usable table" error was surfaced."""
        try:
            return PdfImporter().candidate_tables(plaintext)
        except (PdfError, ValueError, OSError, FinbreakError) as exc:
            # candidate_tables re-runs the idempotent pikepdf normalise, which can
            # raise PdfError — catch it here too, matching the sibling ``_try_decrypt``
            # net, so it never crashes the slot. (indie-review L1)
            self._show_pdf_read_error(exc)
            return None

    @staticmethod
    def _default_pdf_index(candidates: list[list[list[str | None]]]) -> int:
        """The default table = the one with the most **data** rows (the
        transactions table dwarfs a summary table); ties break by first-occurrence
        order — page then table — which ``max`` keeps (D7)."""
        return max(range(len(candidates)), key=lambda i: len(candidates[i]) - 1)

    def _apply_pdf_table(self, index: int) -> ImportProfile | None:
        """Serialise candidate ``index`` to CSV text, re-fill the mapping combos
        from its header, and re-run profile matching (each candidate has its own
        signature) — so Preview always imports the *chosen* table (D7). The
        D13-uniquified header never trips ``match_profile``'s duplicate guard."""
        table = self._pdf_candidates[index]
        text = table_to_text(table)
        header = read_header(text)
        self._text = text
        self._header = header
        self._populate_mapping_combos(header)
        return self._imports.match_profile(header)

    @Slot(int)
    def _on_pdf_table_changed(self, index: int) -> None:
        if 0 <= index < len(self._pdf_candidates):
            self._error.clear()
            matched = self._apply_pdf_table(index)
            if matched is not None:
                self._apply_profile_to_combos(matched)
            else:
                # FIBR-0146 D5(b): a different unmatched table re-detects, so no
                # stale format/preview from the previous table survives.
                self._autodetect_date_format()
            self._update_date_preview()  # single owner refresh (both branches)

    def _apply_profile_to_combos(self, profile: ImportProfile) -> None:
        """Pre-fill the mapping combos from a matched profile (INV-7d), so a
        >1-table PDF shows the map step with the columns already mapped for the
        user to confirm."""
        mapping = profile.column_mapping()
        # The date combo is wired to _on_date_column_changed (re-detect); block it
        # so applying a matched profile does NOT re-run auto-detect over the data
        # (FIBR-0146 D5: _apply_profile_to_combos is signal-blocked; INV-4 a matched
        # profile's stored format is authoritative). Without this, a profile whose
        # date column isn't column 0 would fire a spurious re-detect + double preview
        # refresh. The other role combos carry no such connection.
        with QSignalBlocker(self._column_combos["date"]):
            self._set_combo(self._column_combos["date"], mapping.date_column)
        self._set_combo(self._column_combos["description"], mapping.description_column)
        if mapping.amount_column is not None:
            self._amount_style.setCurrentIndex(0)  # single
            self._set_combo(self._column_combos["amount"], mapping.amount_column)
        else:
            self._amount_style.setCurrentIndex(1)  # separate debit / credit
            self._set_combo(self._column_combos["debit"], mapping.debit_column)
            self._set_combo(self._column_combos["credit"], mapping.credit_column)
        self._select_date_format(mapping.date_format)
        # A matched profile is authoritative — never "ambiguous" (INV-4). Its
        # caller refreshes _update_date_preview, so a stale nudge is cleared.
        self._date_ambiguous = False
        self._invert_amount.setChecked(bool(mapping.invert_amount))

    def _select_date_format(self, fmt: str) -> None:
        """Point the picker at ``fmt`` (FIBR-0146 D4). A known format selects its
        entry; an exotic/saved format not in the list selects "Custom…", fills the
        raw field verbatim, and — because the programmatic select is signal-blocked
        so _on_date_format_changed's show/hide won't fire — **explicitly reveals**
        the custom field (INV-4 "shown, editable"; else the pattern is held but
        hidden). No silent rewrite to a near-match."""
        index = self._date_format.findData(fmt)
        with QSignalBlocker(self._date_format):
            if index >= 0:
                self._date_format.setCurrentIndex(index)
                self._date_format_custom.setVisible(False)
            else:
                self._date_format.setCurrentIndex(
                    self._date_format.findData(_CUSTOM_FORMAT)
                )
                with QSignalBlocker(self._date_format_custom):
                    self._date_format_custom.setText(fmt)
                self._date_format_custom.setVisible(True)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str | None) -> None:
        combo.setCurrentIndex(combo.findData(value))

    def _target_account_id(self) -> int:
        """The account the import will land on — the preview step's destination
        picker, seeded from the pick step and user-correctable (FIBR-0057). The
        single source of truth for every preview and the PDF-password lookup."""
        return self._confirm_account_combo.currentData()

    def _account_name(self) -> str:
        return self._confirm_account_combo.currentText()

    def _populate_mapping_combos(self, header: list[str]) -> None:
        # Signal-blocked so re-filling the date combo fires no _on_date_column_changed
        # (FIBR-0146 D5): a programmatic fill must not re-detect — the caller runs
        # auto-detect explicitly right after.
        for combo in self._column_combos.values():
            with QSignalBlocker(combo):
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
        date_format = self._selected_date_format()
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

    def _selected_date_format(self) -> str:
        """The strptime format the form currently holds (FIBR-0146 D4): a known
        combo entry's data (the fixed % pattern), or the custom field's stripped
        text when "Custom…" is active — the same ``.strip()`` the old QLineEdit
        did, so a stray-space custom pattern can't slip past validation."""
        data = self._date_format.currentData()
        if data is _CUSTOM_FORMAT:
            return self._date_format_custom.text().strip()
        return cast(str, data)

    def _date_samples(self, column: str) -> list[str]:
        """Up to ``_MAX_DATE_SAMPLES`` **stripped, non-blank** values of ``column``
        from the loaded text (FIBR-0146 D8) — the same ``self._text`` a PDF is
        serialised into. Stripping matches the importer (``csv_importer.py``) and
        the detector, so the preview strptimes the identical string the committed
        row uses (no false 'couldn't be read' on a padded cell). Bounded, so
        detection cost is constant in the row count."""
        if self._text is None:
            return []
        samples: list[str] = []
        for row in csv.DictReader(io.StringIO(self._text)):
            cell = row.get(column)
            if cell is None:
                continue
            cell = cell.strip()
            if not cell:
                continue
            samples.append(cell)
            if len(samples) >= _MAX_DATE_SAMPLES:
                break
        return samples

    def _autodetect_date_format(self) -> None:
        """Guess the date format for the currently-selected date column and seed
        the picker + ``_date_ambiguous`` (FIBR-0146 D5). Does **not** refresh the
        preview — the caller owns that call (one owner, no double refresh), so a
        ``None`` guess still shows the 'couldn't read' nudge. A programmatic combo
        set is signal-blocked so it fires no re-detect."""
        column = self._column_combos["date"].currentData()
        samples = self._date_samples(column) if column is not None else []
        guess = detect_date_format(samples)
        self._date_ambiguous = guess.ambiguous
        if guess.fmt is not None:
            index = self._date_format.findData(guess.fmt)
            if index >= 0:
                with QSignalBlocker(self._date_format):
                    self._date_format.setCurrentIndex(index)
                self._date_format_custom.setVisible(False)

    def _update_date_preview(self) -> None:
        """Refresh the live 'how the dates read' label (FIBR-0146 D6). Renders the
        first ``_PREVIEW_SAMPLES`` sampled dates as ISO **only when the selected
        format parses all of the shown ones** (a clean, trustworthy preview); two
        fallbacks cover the rest so the label is never a half-parsed tail. The
        ambiguity nudge is prepended iff ``_date_ambiguous`` is set."""
        column = self._column_combos["date"].currentData()
        samples = self._date_samples(column) if column is not None else []
        if not samples:
            self._date_preview.setText(self.tr("No dates found in this column."))
            return
        fmt = self._selected_date_format()
        parsed: list[str] = []
        for sample in samples[:_PREVIEW_SAMPLES]:
            try:
                parsed.append(datetime.strptime(sample, fmt).date().isoformat())
            except ValueError:
                self._date_preview.setText(
                    self.tr(
                        "These dates couldn't be read with this format — pick another."
                    )
                )
                return
        text = self.tr("Dates read as: {samples}").format(samples=", ".join(parsed))
        if self._date_ambiguous:
            text = (
                self.tr(
                    "Check these are right — the day and month might be the other "
                    "way around."
                )
                + " "
                + text
            )
        self._date_preview.setText(text)

    @Slot(int)
    def _on_date_column_changed(self, _index: int) -> None:
        """User picked a different date column (FIBR-0146 D5c): re-detect for it
        (overriding any prior manual format pick — the column changed) and refresh."""
        self._autodetect_date_format()
        self._update_date_preview()

    @Slot()
    def _on_date_format_changed(self) -> None:
        """User changed the picker OR edited the custom field (FIBR-0146 D6). No-arg
        so BOTH ``currentIndexChanged(int)`` and the custom field's ``textChanged(str)``
        connect here (the extra arg is dropped) — a single owner. Clears the stale
        ambiguity nudge (the format is now a hand-choice), shows/hides the custom
        field, then refreshes the preview."""
        self._date_ambiguous = False
        is_custom = self._date_format.currentData() is _CUSTOM_FORMAT
        self._date_format_custom.setVisible(is_custom)
        self._update_date_preview()

    def _run_preview(self, mapping: ColumnMapping) -> None:
        # _run_preview is only reached after _select_file loads the text (CSV).
        text = cast(str, self._text)
        try:
            preview = self._imports.preview(text, mapping, self._target_account_id())
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
        self._set_period_defaults(preview)
        self._apply_preview_counts(preview)
        self._goto_step(_STEP_PREVIEW)

    def _apply_preview_counts(self, preview: ImportPreview) -> None:
        """Refresh the dedup-dependent parts of the preview — the
        new/duplicate/error summary and the Import-enabled state. Shared by
        ``_show_preview`` and the preview-step account re-target
        (``_on_confirm_account_changed``, FIBR-0057), where the drafts, error
        rows and period are unchanged and only the counts move."""
        self._summary_label.setText(
            self.tr("{new} new · {dup} duplicate · {err} error").format(
                new=preview.new_count,
                dup=preview.duplicate_count,
                err=len(preview.errors),
            )
        )
        # Import stays enabled when there are drafts OR a coverage period to
        # record — so an all-duplicate CSV and a quiet-month OFX (zero drafts,
        # embedded span, FIBR-0008 D14) both keep Import live. Equivalent for CSV
        # (a CSV with zero drafts has period_start == None, INV-9).
        self._import_button.setEnabled(
            len(preview.drafts) > 0 or preview.period_start is not None
        )
        # FIBR-0146 D7: the whole-import banner fires only when NOTHING landed and
        # at least one row errored (0 new · 0 dup · N error). The trigger is
        # count-based (several faults land here — wrong date format/column, blank
        # date column, amount mis-map — so it names the general remedy, not one
        # cause). Any success/duplicate row, or a header-only 0·0·0 preview, hides it.
        self._preview_banner.setVisible(
            preview.new_count == 0
            and preview.duplicate_count == 0
            and len(preview.errors) > 0
        )

    @Slot(int)
    def _on_confirm_account_changed(self, _index: int) -> None:
        """Re-target the pending import to the account chosen on the preview step
        (FIBR-0057): re-run the dedup under the new account and refresh the counts
        so the committed account matches what is shown. Drafts, error rows and the
        period are account-independent, so the table + period pickers are left
        untouched (no reset of a hand-edited period)."""
        if self._preview is None:
            return
        account_id = self._confirm_account_combo.currentData()
        if account_id is None or account_id == self._preview.account_id:
            return
        self._error.clear()
        self._preview = self._imports.retarget(self._preview, account_id)
        self._apply_preview_counts(self._preview)

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
        self._carry_stored_pw_to_committed_account()
        self.done.emit()

    def _carry_stored_pw_to_committed_account(self) -> None:
        """If a PDF password was remembered during this import (persisted against
        the provisional file-select account) and the user then re-targeted the
        import to a different account (FIBR-0057), store it on the account the rows
        actually landed on too — so its auto-apply works next time. Only fills an
        empty slot (never clobbers a password already remembered for that account)
        and leaves the provisional account's password intact (it may be that
        account's own, since a stored-password auto-try that failed is exactly what
        led to the manual prompt)."""
        if self._stored_pw is None or self._preview is None:
            return
        stored_account, password = self._stored_pw
        final_account = self._preview.account_id
        if stored_account != final_account and (
            self._accounts.get_pdf_password(final_account) is None
        ):
            self._accounts.set_pdf_password(final_account, password)
