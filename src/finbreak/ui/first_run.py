"""First-run dialog — set the master password + base currency (FIBR-0004 INV-5).

The password is entered twice; a mismatch, an empty password, or an unsupported
currency is a form-boundary error that creates no vault and derives no key. On
success the vault is created, the app is left unlocked, and ``completed`` fires.

Re-homed from a full-screen ``QWidget`` into a non-blocking application-modal
``QDialog`` shown over the window (FIBR-0051 D2). Cancel / window-close fires
``reject()`` (the shell then quits — no vault can exist). While a derivation is in
flight (``self._worker is not None``) **all three dismissal routes no-op** — Cancel
is disabled and ``reject()`` / ``closeEvent`` return early — so the parented
``DeriveWorker`` ``QThread`` is never deleted mid-run (INV-2f).
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.datetime_format import system_timezone_id
from finbreak.models import KdfParams
from finbreak.services.auth import (
    CURRENCY_EXPONENTS,
    DATETIME_SYSTEM,
    AmountPrefs,
    AuthService,
    DateTimePrefs,
)
from finbreak.ui._datetime_prefs import (
    populate_datetime_combos,
    read_datetime_prefs,
    system_date_sample_label,
    system_time_sample_label,
)
from finbreak.ui._worker import DeriveWorker


class FirstRunDialog(QDialog):
    completed = Signal()
    # "Restore from a backup instead" — a user with an existing `.fbk` restores it
    # rather than creating a fresh vault (FIBR-0014 INV-8/D5). The shell owns it.
    restore_requested = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._worker: DeriveWorker | None = None
        self._pending_params: KdfParams | None = None
        self._pending_currency = ""
        self.setWindowTitle(self.tr("Create your vault"))

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._currency = QComboBox()
        self._currency.addItems(list(CURRENCY_EXPONENTS))

        # The FIBR-0083 timezone / date / time controls, pre-filled with the
        # detected "system" defaults (there is no vault to read yet — D6). The
        # System-default label is the only tr()-wrapped text (INV-7).
        self._timezone = QComboBox()
        self._timezone.setObjectName("first_run_timezone")
        self._date_format = QComboBox()
        self._date_format.setObjectName("first_run_date_format")
        self._time_format = QComboBox()
        self._time_format.setObjectName("first_run_time_format")
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
            current=DateTimePrefs(DATETIME_SYSTEM, DATETIME_SYSTEM, DATETIME_SYSTEM),
        )

        # The FIBR-0105 amount-display controls, pre-filled with the defaults (no
        # vault to read yet — INV-7): minus + colour on. Same idiom as Settings.
        self._amount_negative = QComboBox()
        self._amount_negative.setObjectName("first_run_amount_negative")
        self._amount_negative.addItem(self.tr("Minus (-)"), "minus")
        self._amount_negative.addItem(self.tr("Brackets ( )"), "brackets")
        self._amount_colour = QCheckBox(self.tr("Colour amounts red/green"))
        self._amount_colour.setObjectName("first_run_amount_colour")
        self._amount_colour.setChecked(True)

        self._submit = QPushButton(self.tr("Create vault"))
        self._error = QLabel()
        self._restore_button = QPushButton(self.tr("Restore from a backup instead…"))
        self._restore_button.setObjectName("first_run_restore")
        self._restore_button.setFlat(True)

        form = QFormLayout()
        form.addRow(self.tr("Master password"), self._password)
        form.addRow(self.tr("Confirm password"), self._confirm)
        form.addRow(self.tr("Base currency"), self._currency)
        form.addRow(self.tr("Time zone"), self._timezone)
        form.addRow(self.tr("Date format"), self._date_format)
        form.addRow(self.tr("Time format"), self._time_format)
        form.addRow(self.tr("Negative amounts"), self._amount_negative)
        form.addRow("", self._amount_colour)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                self.tr(
                    "There is no password recovery — if you forget this password, "
                    "your data cannot be recovered."
                )
            )
        )
        layout.addLayout(form)
        layout.addWidget(self._submit)
        layout.addWidget(self._error)
        layout.addWidget(self._restore_button)
        layout.addWidget(buttons)

        self._submit.clicked.connect(self._on_submit)
        self._restore_button.clicked.connect(self.restore_requested)

    def _set_busy(self, busy: bool) -> None:
        # Disabling Cancel (with the reject()/closeEvent guards below) is what
        # keeps a dismissal from deleting the parented worker mid-run (INV-2f).
        self._submit.setEnabled(not busy)
        self._cancel.setEnabled(not busy)
        self._restore_button.setEnabled(not busy)  # dismissal-like route (INV-2f)

    def reject(self) -> None:
        if self._worker is not None:
            return  # a derivation is in flight — Escape / Cancel no-op (INV-2f)
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None:
            event.ignore()  # the window [X] mid-derivation is a no-op too (INV-2f)
            return
        super().closeEvent(event)

    @Slot()
    def _on_submit(self) -> None:
        if self._worker is not None:
            return  # a derivation is already in flight — ignore repeat submits
        self._error.clear()
        currency = self._currency.currentText()
        password = bytearray(self._password.text().encode("utf-8"))
        confirm = bytearray(self._confirm.text().encode("utf-8"))
        try:
            self._service.validate_first_run(password, confirm, currency)
        except ValueError as exc:
            self._error.setText(str(exc))
            return

        # validate_first_run wiped the buffers above; re-encode a fresh one for
        # the derivation (the QLineEdit str is the unavoidable best-effort leak).
        self._pending_params = self._service.new_params()
        self._pending_currency = currency
        derive_password = bytearray(self._password.text().encode("utf-8"))
        self._password.clear()
        self._confirm.clear()
        self._set_busy(True)

        worker = DeriveWorker(derive_password, self._pending_params, self)  # Qt owns it
        worker.done.connect(self._on_derived)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(worker.deleteLater)  # no leaked QThread per attempt
        self._worker = worker
        worker.start()

    @Slot(bytes)
    def _on_derived(self, raw: bytes) -> None:
        self._worker = None
        self._set_busy(False)  # every worker-clearing path re-enables Cancel (D2)
        params = self._pending_params
        currency = self._pending_currency
        self._pending_params = None  # consumed — don't leave stale state on a retry
        self._pending_currency = ""
        if params is None:  # _on_submit always sets it before start — defensive
            return
        try:
            self._service.complete_first_run(raw, params, currency)
            # The vault now exists — persist the datetime prefs at this post-create
            # site (D6), on the same guarded path as vault creation.
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
        except Exception as exc:  # vault creation failed — surface, don't crash
            self._error.setText(
                self.tr("Could not create the vault: {error}").format(error=exc)
            )
            return
        self.completed.emit()

    @Slot(object)
    def _on_failure(self, exc: object) -> None:
        self._worker = None
        self._set_busy(False)
        self._error.setText(
            self.tr("Could not create the vault: {error}").format(error=exc)
        )
