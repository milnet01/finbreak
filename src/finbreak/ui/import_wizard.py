"""Import-wizard screen — pick a file + account, map columns (or auto-match a
saved profile), preview, and import (FIBR-0007 D9/INV-10).

A **non-modal** stacked ``QWidget`` (not a ``QDialog``/``QWizard``), so the idle
auto-lock can swap it away like any other screen (app.py comments). Its four
steps live in an internal ``QStackedLayout``: (0) pick file(s) + account; (1) map
columns — shown only when no saved profile matches; (2) preview + confirm-period
+ Import; (3) the batch review table. All strings go through ``tr()`` and every
widget sits in a Qt layout manager, so the screen is translation-ready and
RTL-safe (coding.md § 5.2).

Selecting **one** file routes to steps 0-2, entirely unchanged. Selecting **two
or more** starts a batch (FIBR-0085): step 3 plus the scan/ask/run chain at the
foot of this file, with every decision in ``services/batch_import.py``. Step 1 is
shared — the batch re-shows it to collect one file's mapping — which is why its
Next and Cancel are batch-aware rather than wired straight through.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

from PySide6.QtCore import QDate, QSignalBlocker, Qt, QTimer, Signal, Slot
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

from finbreak.errors import FinbreakError, VaultLockedError
from finbreak.importers.base import ParseResult, SourceAccountHint
from finbreak.importers.csv_importer import read_header, read_rows
from finbreak.importers.date_detect import KNOWN_DATE_FORMATS, detect_date_format
from finbreak.importers.ofx_importer import OfxImporter
from finbreak.importers.pdf_importer import (
    PasswordError,
    PdfError,
    PdfImporter,
    default_table_index,
    table_to_text,
)
from finbreak.importers.sniff import looks_like_ofx, looks_like_pdf
from finbreak.importers.standard_bank import StandardBankImporter
from finbreak.models import ColumnMapping, ImportProfile, OfxAccountInfo
from finbreak.services.account_match import match_account
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.batch_import import (
    CANCELLED,
    BatchFile,
    BatchImportService,
    next_question,
)
from finbreak.services.import_ import ImportPreview, ImportService
from finbreak.services.transactions import read_minor_unit_exponent, to_display_decimal
from finbreak.ui._table_state import remember_columns
from finbreak.ui.account_create import CreateAccountDialog
from finbreak.ui.import_batch import BatchReviewWidget
from finbreak.ui.modal import show_modal
from finbreak.ui.password_dialog import PasswordDialog

# `_STEP_BATCH` is APPENDED after the existing three, so indices 0-2 keep their
# meaning and the 24 absolute `_stack.currentIndex()` assertions across six
# suites stay true. Appending rather than inserting is what makes that so, and
# is the reason to append (FIBR-0085 § 7).
_STEP_PICK, _STEP_MAP, _STEP_PREVIEW, _STEP_BATCH = 0, 1, 2, 3

# INV-8. "Prompt", never "attempt": the automatic tries against stored passwords
# (§ 4.4) are attempts and are bounded separately by INV-9. The single-file
# path's `_on_pdf_password` re-prompts by recursion with no counter at all,
# which is exactly what a copy-paste of it into the batch would reproduce.
_MAX_PASSWORD_PROMPTS = 3
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
        # True while the picked file went through the MAP STEP — the CSV path and
        # a generic (non-SB) PDF, which is extracted to a CSV-text table and
        # mapped exactly like one. Only those two can be told to "go back and
        # check the column mapping" (FIBR-0146 D7 / FIBR-0253); OFX and a
        # recognised Standard Bank statement are self-describing and skip it.
        # Set per pick by `_select_file` / `_continue_after_decrypt`.
        self._has_mapping_step: bool = False
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
        # FIBR-0086: the statement's own account details, held only while the
        # preview shows a `no_match` — the Create button reads it. None in every
        # other outcome, which is what keeps creation unreachable from `no_number`.
        self._pending_hint: SourceAccountHint | None = None

        # -- batch state (FIBR-0085) -----------------------------------------
        # All of it inert until >= 2 files are selected: one file routes to the
        # single-file flow above, entirely unchanged (§ 4.1).
        self._batch = BatchImportService(service.vault)
        self._batch_files: list[BatchFile] = []
        self._batch_index = 0
        # Which pass the batch is in. It is a GUARD, not bookkeeping: § 4.7
        # returns to the event loop between every turn, so a click or a stale
        # queued callback can arrive at any moment, and each chain slot refuses
        # to run outside its own phase. Two chains armed at once step the same
        # index and skip files silently — which is exactly what happened when
        # `Import all` could be pressed mid-SCAN.
        self._batch_phase = "idle"
        # The record whose mapping `_STEP_MAP` is currently collecting, or None
        # when that page is being driven by the single-file flow. It is what
        # makes the page's Next/Cancel batch-aware without rewiring them.
        self._batch_asking: BatchFile | None = None
        # Prompts raised per record so far (INV-8), keyed by identity — two
        # records can share a path (an OFX fan-out) and `BatchFile` compares by
        # value, so neither the path nor a list index is a safe key.
        self._batch_prompts: dict[int, int] = {}

        self._stack = QStackedLayout()
        self._error = QLabel()
        self._stack.addWidget(self._build_pick_step())
        self._stack.addWidget(self._build_map_step())
        self._stack.addWidget(self._build_preview_step())
        self._stack.addWidget(self._build_batch_step())

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
        # NOT wired straight to `done` like the other two steps' Cancels. This
        # page is REUSED by the batch's ask pass, and `MainWindow._on_import_done`
        # answers `done` by rebuilding the workspace — so declining the mapping
        # for one file in a thirty-file batch would destroy the entire batch and
        # every answer already given (INV-14).
        cancel.clicked.connect(self._on_map_cancel)
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
        # turning N identical cryptic rows into one actionable sentence. Text AND
        # visibility are both set in _apply_preview_counts, because the remedy
        # depends on whether the file was mapped (FIBR-0253). No file is picked
        # yet here, so this seeds the no-map-step wording; it is never displayed
        # (the banner is hidden until a preview re-sets both).
        self._preview_banner = QLabel(self._banner_text())
        self._preview_banner.setObjectName("import_preview_banner")
        self._preview_banner.setWordWrap(True)
        self._preview_banner.hide()
        self._preview_table = QTableWidget(0, 5)
        # Named so remember_columns has a settings key of its own ("columns/
        # import_preview_table") — an unnamed table would share the empty key with
        # every other unnamed one and cross-corrupt their widths (FIBR-0187).
        self._preview_table.setObjectName("import_preview_table")
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
        # Widths / column order survive the wizard being rebuilt for the next
        # import, the way every other table in the app already behaves (FIBR-0187).
        remember_columns(self._preview_table)
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

        # Why the destination above is (or is not) the statement's own account
        # (FIBR-0086). Empty and hidden when the format carries no number — for
        # CSV and credit-card statements the step looks exactly as it did before.
        self._account_match_label = QLabel()
        self._account_match_label.setObjectName("import_account_match")
        self._account_match_label.setWordWrap(True)
        self._account_match_label.hide()
        # Offered ONLY on no_match (FIBR-0086 §4.6). Not on no_number: a masked or
        # absent number must never become a permanently-stored account number.
        self._create_account_button = QPushButton(self.tr("Create it"))
        self._create_account_button.setObjectName("import_create_account")
        self._create_account_button.clicked.connect(self._on_create_account)
        self._create_account_button.hide()

        destination = QFormLayout()
        destination.addRow(self.tr("Import into account"), self._confirm_account_combo)
        # The wrapped explanation goes in the FIELD column and the short button in
        # the label column: a QFormLayout gives the field column the width, and the
        # sentence is what needs it.
        destination.addRow(self._create_account_button, self._account_match_label)

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

    # -- step 3: batch review (FIBR-0085) -------------------------------------
    def _build_batch_step(self) -> QWidget:
        self._batch_review = BatchReviewWidget(self._batch, self._accounts, self)
        self._batch_review.import_requested.connect(self._on_batch_import)
        self._batch_review.cancelled.connect(self._on_batch_cancel)
        # The ONE control that emits `done` (INV-14) — never the end of RUN,
        # never either Cancel.
        self._batch_review.closed.connect(self.done)
        self._batch_review.accounts_changed.connect(self._refill_account_combos)
        return self._batch_review

    @Slot()
    def _refill_account_combos(self) -> None:
        """Re-list both account combos after the batch created an account.

        Both are filled once in ``__init__``; a pre-RUN Cancel returns the user
        to the pick step (§ 4.6), which would otherwise still be showing the
        account set as it was before they created one."""
        for combo in (self._account_combo, self._confirm_account_combo):
            with QSignalBlocker(combo):
                previous = combo.currentData()
                combo.clear()
                self._fill_account_combo(combo)
                if previous is not None:
                    combo.setCurrentIndex(combo.findData(previous))

    # -- navigation / actions -------------------------------------------------
    def _goto_step(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    @Slot()
    def _on_pick_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr("Choose statement files"),
            "",
            self.tr("Statement files (*.csv *.ofx *.qfx *.pdf);;All files (*)"),
        )
        if not paths:
            return  # cancelled — stay on the pick step, as today
        if len(paths) == 1:
            # One file routes to the existing single-file flow, ENTIRELY
            # unchanged (§ 4.1). It is also the better screen: a one-row review
            # table is worse than the preview it would replace.
            self._select_file(paths[0])
            return
        self._select_files(paths)

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
        # Cleared before the format dispatch below and set again only where the
        # map step is really reached, so an OFX pick after a CSV one cannot
        # inherit the previous file's mapping-step remedy (FIBR-0253).
        self._has_mapping_step = False
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
        # Clear the previous file's match explanation (FIBR-0086) — a CSV pick
        # never sets one, so without this a prior OFX/PDF import's label would
        # linger over a preview it does not describe.
        self._account_match_label.clear()
        self._account_match_label.hide()
        # The Create button and the hint behind it go with it — the CSV path never
        # calls _apply_account_match, so without this a prior file's no_match would
        # leave a live button offering to create an account for a statement that is
        # no longer on screen.
        self._pending_hint = None
        self._create_account_button.hide()
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
        if looks_like_ofx(path):
            self._select_ofx(path)
            return
        if looks_like_pdf(path):
            self._select_pdf(path)
            return
        # Past both sniffs is the CSV path, which always maps.
        self._has_mapping_step = True
        try:
            text = self._imports.read_file(path)
            header = read_header(text)  # raises ValueError on an empty file
            matched = self._imports.match_profile(header)  # raises on dup-named header
            self._text = text
            self._header = header
            self._populate_mapping_combos(header)
            if matched is not None:
                self._run_preview(matched.column_mapping())
            else:
                # FIBR-0146 D5(a): an unmatched CSV gets a date-format guess over
                # the (default) date column before the map step is shown. This is
                # INSIDE the guard: the header is line 1, so a file whose *rows*
                # are structurally broken parses its header fine and only trips
                # when the detector reads the body (INV-4).
                self._autodetect_date_format()
                self._update_date_preview()
                self._goto_step(_STEP_MAP)
        except (ValueError, OSError, FinbreakError) as exc:
            # Drop the rejected text: `_text` may already have been assigned above
            # before the failure, and leaving it set would let the map-step slots
            # re-enter `_date_samples` on a file we just refused. `None` is the
            # honest state — no usable file is loaded.
            self._text = None
            self._error.setText(str(exc))
            return

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

    def _apply_account_match(self, result: ParseResult) -> None:
        """Point the destination at the account the statement names (FIBR-0086).

        **Must run BEFORE ``preview_result``.** The combo's ``currentIndexChanged``
        is wired to ``_on_confirm_account_changed``, the only thing that re-points
        an already-built preview (via ``ImportService.retarget``), and the blocker
        below suppresses it. Seeding after the preview exists would therefore leave
        ``self._preview`` aimed at the previous account while the combo displayed
        the matched one — and ``commit_import`` persists ``self._preview``. The
        user would approve a screen reading "Matched account number …" and the
        transactions would land somewhere else.

        Only ``matched`` ever changes the selection. ``no_match`` and ``ambiguous``
        explain themselves and leave the pick step's choice alone; ``no_number``
        shows nothing at all, which is the whole of today's behaviour.
        """
        match = match_account(result.source_account, self._accounts.list_accounts())
        # As printed, never the normalised key: the number on screen is the one the
        # user can read off the paper statement in front of them.
        printed = result.source_account.number if result.source_account else ""

        # The destination this outcome implies. Every non-matched outcome returns
        # to the PICK STEP's account explicitly rather than leaving the combo
        # untouched — "untouched" is only the same thing on the first preview. On
        # the OFX statement chooser this method runs again for a second statement
        # in the same file, where the combo may still hold the account auto-matched
        # for the FIRST one; leaving it there would silently file this statement
        # under an account chosen from a different statement's number.
        destination = (
            match.account_id
            if match.outcome == "matched"
            else self._account_combo.currentData()
        )
        with QSignalBlocker(self._confirm_account_combo):
            self._confirm_account_combo.setCurrentIndex(
                self._confirm_account_combo.findData(destination)
            )

        if match.outcome == "matched":
            text = self.tr(
                "Matched account number {number} printed on this statement."
            ).format(number=printed)
        elif match.outcome == "ambiguous":
            text = self.tr(
                "This statement's account number matches more than one account — "
                "pick one."
            )
        elif match.outcome == "no_match":
            text = self.tr("No account has number {number}.").format(number=printed)
        else:
            text = ""

        self._account_match_label.setText(text)
        self._account_match_label.setVisible(bool(text))
        # Creation is reachable from no_match ONLY. no_number covers a masked or
        # unreadable number, which must never be stored as an account's number.
        self._pending_hint = (
            result.source_account if match.outcome == "no_match" else None
        )
        self._create_account_button.setVisible(self._pending_hint is not None)

    @Slot()
    def _on_create_account(self) -> None:
        """Create the account the statement names, then import into it (§4.6).

        Every prefilled field stays editable and nothing is written until the user
        accepts the dialog.
        """
        if self._pending_hint is None:  # defensive: the button is hidden otherwise
            return
        dialog = CreateAccountDialog(
            number=self._pending_hint.number,
            name=self._pending_hint.name,
            family=self._pending_hint.family,
            parent=self,
        )
        # Non-blocking + parented (FIBR-0065 D1): an idle auto-lock destroys the
        # dialog before the slot below can fire, rather than leaving a post-exec()
        # read of a deleted object.
        show_modal(dialog, lambda: self._create_account_from(dialog))

    def _create_account_from(self, dialog: CreateAccountDialog) -> None:
        """The accepted half of ``_on_create_account``, run as ``show_modal``'s
        ``on_accept`` slot."""
        if self._pending_hint is None:  # lock or a second accept — nothing pending
            return
        self._error.clear()
        try:
            account = self._accounts.add_account(
                dialog.entered_name(),
                dialog.entered_type(),
                account_number=dialog.entered_number(),
            )
        except VaultLockedError:
            return  # auto-lock fired mid-edit — silent, like the other handlers
        except (ValueError, FinbreakError) as exc:
            self._error.setText(str(exc))
            return

        # Both combos gain the new account, so the pick step lists it too.
        for combo in (self._account_combo, self._confirm_account_combo):
            combo.addItem(account.name, account.id)
        # Deliberately NOT under a QSignalBlocker — the mirror image of
        # _apply_account_match. The preview already exists by now, so we NEED
        # currentIndexChanged to reach _on_confirm_account_changed and retarget it;
        # blocking here would leave the preview aimed at the old account while the
        # combo showed the new one — the wrong-account commit INV-7a locks out.
        self._confirm_account_combo.setCurrentIndex(
            self._confirm_account_combo.findData(account.id)
        )
        # Report what was actually STORED, not what the statement printed — the
        # number box is editable, and clearing it stores NULL. Claiming a match on
        # the printed number there would promise auto-filing that cannot happen,
        # and every later import of this account would offer to create it again.
        if account.account_number:
            self._account_match_label.setText(
                self.tr(
                    "Matched account number {number} printed on this statement."
                ).format(number=account.account_number)
            )
        else:
            self._account_match_label.setText(
                self.tr(
                    "Created {name}. It has no account number, so future statements "
                    "will not file themselves."
                ).format(name=account.name)
            )
        self._pending_hint = None
        self._create_account_button.hide()

    def _preview_ofx_statement(self, index: int) -> None:
        _info, result = self._ofx_statements[index]
        # Before preview_result — see _apply_account_match's docstring.
        self._apply_account_match(result)
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
                # Before preview_result — see _apply_account_match's docstring.
                self._apply_account_match(sb_result)
                self._show_preview(
                    self._imports.preview_result(sb_result, self._target_account_id())
                )
                return
        except (PdfError, ValueError, FinbreakError) as exc:
            self._show_pdf_read_error(exc)
            return
        # Past the SB reader is the generic-PDF route: extracted to a CSV-text
        # table and mapped like a CSV, so the D7 banner's mapping remedy applies
        # here exactly as it does to a CSV (FIBR-0253). Set before the extract so
        # both endings below carry it — the map step, and the matched-profile
        # jump to preview, which leaves a mapping the user can still go back to.
        self._has_mapping_step = True
        candidates = self._extract_pdf_tables(plaintext)
        if candidates is None:
            return  # a friendly error was already surfaced
        self._pdf_candidates = candidates
        default = default_table_index(candidates)
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
            # matched, >1 table: refresh for the map step
            self._refresh_date_ui(detect=False)
        else:
            # FIBR-0146 D5(b): a generic (non-SB) PDF gets a date-format guess.
            self._refresh_date_ui(detect=True)
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
                self._refresh_date_ui(detect=False)
            else:
                # FIBR-0146 D5(b): a different unmatched table re-detects, so no
                # stale format/preview from the previous table survives.
                self._refresh_date_ui(detect=True)

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
        if self._batch_asking is not None:
            self._answer_batch_mapping(mapping)
            return
        self._run_preview(mapping)

    @Slot()
    def _on_map_cancel(self) -> None:
        """Cancel on the map step. For a single file that is "abandon the
        import", as it has always been; **while the batch is driving this page
        it declines ONE FILE** (§ 4.1/INV-14) and must not emit `done`."""
        if self._batch_asking is None:
            self.done.emit()
            return
        record, self._batch_asking = self._batch_asking, None
        self._batch.answer(self._batch_files, record, None)  # -> skipped
        self._resume_ask()

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
        # Via ``read_rows``, NOT a bare DictReader: it carries the ``csv.Error``
        # guard, and csv.Error is not a ValueError so an unguarded reader here
        # escapes this widget's slots entirely (INV-4).
        for row in read_rows(self._text):
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

    def _refresh_date_ui(self, *, detect: bool) -> None:
        """Run the map step's date pair — optional re-detect, then the preview —
        under ONE ``ValueError`` guard (FIBR-0268).

        Both halves read the loaded text through ``_date_samples``, so a
        structurally-broken body (D8) raises out of whichever fires first. On the
        file pick that raise is caught by ``_select_file``, which refuses the
        file; every other caller is a Qt slot or a batch step with no net of its
        own, and an escaping ``ValueError`` terminates the app. So they come
        through here instead: the message lands on the map-step error label, the
        picker keeps whatever it had, and the preview asserts nothing it can no
        longer read.

        ``_select_file`` deliberately does NOT use this — D5(a) must *refuse* a
        broken file, not show the map step over it.
        """
        try:
            if detect:
                self._autodetect_date_format()
            self._update_date_preview()
        except ValueError as exc:
            self._error.setText(str(exc))
            self._date_preview.clear()

    @Slot(int)
    def _on_date_column_changed(self, _index: int) -> None:
        """User picked a different date column (FIBR-0146 D5c): re-detect for it
        (overriding any prior manual format pick — the column changed) and refresh."""
        self._refresh_date_ui(detect=True)

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
        self._refresh_date_ui(detect=False)

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

    def _banner_text(self) -> str:
        """The D7 all-rows-failed sentence for the source in hand (FIBR-0253).

        D7's remedy — go back and check the column mapping and the Date format —
        names the map step, which only a mapped source reaches: a CSV, or a
        generic (non-SB) PDF, which is extracted to a CSV-text table and mapped
        the same way. The same banner is reachable from OFX and from a recognised
        Standard Bank statement, which are self-describing and skip mapping
        entirely, so there that advice points at a screen the user was never
        shown. The trigger stays count-based for every source; only the sentence
        moves.
        """
        if self._has_mapping_step:
            return self.tr(
                "None of the rows could be imported. Go back and check the column "
                "mapping and the Date format match your statement."
            )
        return self.tr(
            "None of the rows could be imported. Each row below says what went "
            "wrong with it."
        )

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
        # The trigger is source-neutral but the remedy is not, so the text is
        # re-chosen per preview (FIBR-0253) rather than fixed at construction.
        self._preview_banner.setText(self._banner_text())
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
        # The user has overridden the destination, so any FIBR-0086 explanation no
        # longer describes it — a stale "Matched account number …" on the final,
        # irreversible screen asserts a match that is no longer true, and a stale
        # Create button would discard the account they just picked.
        self._account_match_label.clear()
        self._account_match_label.hide()
        self._pending_hint = None
        self._create_account_button.hide()
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
                        # A row the dedup delta will drop is NOT "OK" — it is not
                        # going to be imported at all. Labelling every draft OK
                        # while the summary said "N duplicate" left the user with
                        # no way to see which of their transactions was being
                        # discarded (FIBR-0204).
                        self.tr("Duplicate")
                        if draft.row_number in preview.duplicate_row_numbers
                        else self.tr("OK"),
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

    # -- the batch (FIBR-0085) ------------------------------------------------
    #
    # SCAN -> ASK -> REVIEW -> RUN, driven one file per event-loop turn. Every
    # decision lives in `services/batch_import.py`; what is here is the chain,
    # the dialogs, and the wiring between them.

    def _select_files(self, paths: list[str]) -> None:
        """Start a batch over >= 2 selected files (§ 4.3)."""
        self._error.clear()
        self._batch_files = self._batch.build(paths)
        self._batch_index = 0
        self._batch_phase = "scan"
        self._batch_asking = None
        self._batch_prompts.clear()
        # The table goes on screen BEFORE the scan starts, so it fills in row by
        # row as each file is classified (§ 6). There is no separate progress
        # dialog: the table is the progress indicator.
        self._batch_review.set_files(self._batch_files)
        self._goto_step(_STEP_BATCH)
        self._arm(self._scan_next)

    def _arm(self, slot: Callable[[], None]) -> None:
        """Queue the next turn of the batch chain.

        The **three-argument** overload is required, not stylistic (§ 4.7):
        the context object is what makes a pending callback drop when the widget
        is destroyed — which is precisely what an idle auto-lock does to the
        wizard via ``MainWindow._set_live``. A two-argument
        ``QTimer.singleShot(0, callable)`` would keep a bound method alive past
        the widget's death and resume a batch into a locked vault (INV-7).
        Between turns the event loop runs, so the UI repaints and Cancel is live.
        """
        QTimer.singleShot(0, self, slot)

    @Slot()
    def _scan_next(self) -> None:
        if self._batch_phase != "scan":
            return
        if self._batch_index >= len(self._batch_files):
            self._begin_ask()
            return
        self._batch_index = self._batch.scan_step(self._batch_files, self._batch_index)
        self._batch_review.refresh()
        self._arm(self._scan_next)

    @Slot()
    def _begin_ask(self) -> None:
        """Hand out the next password or mapping question, or enter REVIEW.

        Only those two: they block the parse, so they genuinely cannot wait. The
        account question is settled on the review screen instead (§ 3 decision
        5) — a file-by-file account prompt is the babysitting decision 1
        rejects, under another name.
        """
        if self._batch_phase not in ("scan", "ask"):
            return
        self._batch_phase = "ask"
        record = next_question(self._batch_files)
        if record is None:
            try:
                self._batch.review(self._batch_files)
            except VaultLockedError:
                return  # auto-lock fired between turns — the shell takes over
            self._batch_phase = "review"
            self._batch_review.refresh()
            return
        if record.outcome == "needs_password":
            self._ask_password(record)
        else:
            self._ask_mapping(record)

    def _resume_ask(self) -> None:
        """Shared tail of every answered question: repaint, return to the table,
        and queue the next question on its own turn."""
        self._batch_review.refresh()
        self._goto_step(_STEP_BATCH)
        self._arm(self._begin_ask)

    def _ask_password(self, record: BatchFile) -> None:
        raised = self._batch_prompts.get(id(record), 0)
        if raised >= _MAX_PASSWORD_PROMPTS:
            # -> skipped; the batch carries on
            self._batch.answer(self._batch_files, record, None)
            self._resume_ask()
            return
        self._batch_prompts[id(record)] = raised + 1
        # The file name, so a batch says WHICH file it is unlocking — but the
        # remember label is overridden, because § 4.4 stores the password
        # against the account the file eventually lands on, and the default
        # label ("Remember this password for <name>") would promise it was
        # remembered for a file.
        dialog = PasswordDialog(
            Path(record.path).name,
            self,
            remember_text=self.tr(
                "Remember this password for the account this file lands in"
            ),
        )
        # `show_modal` wires only `accepted`, so a Cancel is otherwise
        # unobservable and this pass would wait forever on a dialog that has
        # already been freed (§ 4.4). Nothing else sets a `rejected` handler, so
        # adding one at the call site conflicts with nothing.
        dialog.rejected.connect(lambda: self._on_batch_password(record, None, False))
        show_modal(
            dialog,
            lambda: self._on_batch_password(
                record, dialog.password(), dialog.remember()
            ),
        )

    def _on_batch_password(
        self, record: BatchFile, password: str | None, remember: bool
    ) -> None:
        record.remember_password = remember
        # `None` declines -> skipped
        self._batch.answer(self._batch_files, record, password)
        self._resume_ask()

    def _ask_mapping(self, record: BatchFile) -> None:
        """Re-show the existing map step for one file (§ 4.1).

        That page is a large form — five column combos, amount style, invert,
        the date-format picker with live preview, the profile-name field — and
        an unfamiliar CSV in a batch needs exactly that form. Re-implementing it
        in a second widget would be the largest duplication in the codebase.
        """
        if record.source_text is None:  # defensive: SCAN sets it before asking
            self._batch.answer(self._batch_files, record, None)
            self._resume_ask()
            return
        self._batch_asking = record
        self._error.clear()
        self._text = record.source_text
        self._header = read_header(record.source_text)
        self._populate_mapping_combos(self._header)
        # Reset the parts of the form `_populate_mapping_combos` does NOT touch.
        # This page is reused per file, and a matched profile never refills it
        # here (the record is `needs_mapping` precisely because none matched) —
        # so without this, one file's "Amounts are reversed" tick silently
        # FLIPS EVERY SIGN on the next file, and a stale debit/credit style
        # reads the wrong columns. A money bug, and invisible unless the user
        # rereads the whole form each time.
        self._invert_amount.setChecked(False)
        self._amount_style.setCurrentIndex(0)  # single amount column
        with QSignalBlocker(self._date_format_custom):
            self._date_format_custom.clear()
        self._refresh_date_ui(detect=True)
        self._profile_name.clear()
        self._goto_step(_STEP_MAP)

    def _answer_batch_mapping(self, mapping: ColumnMapping) -> None:
        record, self._batch_asking = self._batch_asking, None
        if record is not None:
            self._batch.answer(self._batch_files, record, mapping)
        self._resume_ask()

    @Slot()
    def _on_batch_import(self) -> None:
        """Start RUN — from REVIEW, once, and never from anywhere else.

        The phase check is the second half of INV-3's gate. `can_import` stops
        the button going live while a record is unsettled; this stops a click
        that lands anyway (a second click during the run, a queued click) from
        rewinding the index and arming a SECOND `_run_next` chain alongside the
        first. Two chains stepping one index skip files silently.
        """
        if self._batch_phase != "review":
            return
        self._error.clear()
        self._batch_index = 0
        self._batch_phase = "run"
        self._batch_review.set_running(True)
        self._arm(self._run_next)

    @Slot()
    def _run_next(self) -> None:
        if self._batch_phase != "run":
            return
        if self._batch_index >= len(self._batch_files):
            self._batch_phase = "report"
            self._batch_review.set_running(False)
            # The report is shown BEFORE anything is torn down: emitting `done`
            # here would have `MainWindow._on_import_done` rebuild the workspace
            # and destroy the very table the report is written into (INV-14).
            self._batch_review.finish()
            return
        self._batch_index = self._batch.run_step(self._batch_files, self._batch_index)
        self._batch_review.refresh()
        self._arm(self._run_next)

    @Slot()
    def _on_batch_cancel(self) -> None:
        """Abandon the batch (§ 4.6). Before RUN it drops the whole thing and
        returns to the pick step; during RUN it stops the chain and leaves the
        report standing. Neither emits `done`."""
        was_running = self._batch_phase == "run"
        self._batch_phase = "report" if was_running else "idle"
        self._batch.stop_from(self._batch_files, self._batch_index, CANCELLED)
        if was_running:
            self._batch_review.set_running(False)
            self._batch_review.finish()
            return
        # Every held password is discarded unwritten: `_settle_password` only
        # writes once a destination settles, and none now will.
        self._batch_files = []
        self._batch_asking = None
        self._batch_prompts.clear()
        self._batch_review.set_files(self._batch_files)
        self._goto_step(_STEP_PICK)
