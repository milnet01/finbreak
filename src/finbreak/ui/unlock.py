"""Unlock dialog — password → (worker derives) → open vault (FIBR-0004 INV-6).

A wrong password and a tampered vault are deliberately indistinguishable here:
both surface as a failed unlock, because without the correct key the app cannot
tell them apart (the HMAC that would prove tamper is itself keyed).

Re-homed from a full-screen ``QWidget`` into a non-blocking application-modal
``QDialog`` shown over the window (FIBR-0051 D2). It keeps ``unlocked`` /
``unlock_failed``; the shell connects ``unlocked`` → the unlocked shell, and on
``unlock_failed`` the dialog stays open for a retry. Cancel / window-close fires
``reject()`` (the shell leaves the locked shell on screen). While a derivation is
in flight **all three dismissal routes no-op** (Cancel disabled, ``reject()`` /
``closeEvent`` return early) so the parented ``DeriveWorker`` ``QThread`` is never
deleted mid-run (INV-2f).
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from PySide6.QtCore import QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import (
    KdfPolicyError,
    RollbackAvailableError,
    SchemaVersionError,
    VaultStateError,
)
from finbreak.services.auth import AuthService
from finbreak.services.recovery_code import decode, normalise, verify_check_symbol
from finbreak.ui._password_hint import read_hint
from finbreak.ui._unlock_throttle import UnlockThrottle
from finbreak.ui._worker import DeriveWorker

log = logging.getLogger(__name__)

# Shown when a credential unwrapped its slot and the resulting key still did not
# open the database (§ 6). Single-homed: both routes render the same words.
_PAIRING_BROKEN = (
    "finbreak unlocked this vault's key record, but the vault file itself "
    "could not be opened — the two do not belong together, or the vault file "
    "is damaged. If you have a backup, restore it."
)

# § 13.3's terminal branch, where a verified pre-upgrade copy is beside the
# vault. Offering it is "the whole return on D8" — the alternative is the
# refusal above, with the user's own vault sitting in the same folder.
_ROLLBACK_TITLE = "Restore the copy from before the update?"
_ROLLBACK_OFFER = (
    "finbreak could not open this vault, but it kept a copy of it from "
    "before the last update finished — and your password opens that copy.\n\n"
    "Restore it? Your accounts and transactions come back as they were "
    "before the update, and finbreak will ask for your password again to "
    "open them.\n\n"
    "Nothing is deleted if you say No — you can do this next time instead."
)
_ROLLBACK_RESTORED = (
    "The copy from before the update has been restored. Enter your password "
    "again to open it."
)


class UnlockDialog(QDialog):
    unlocked = Signal()
    # A RECOVERY unlock — deliberately distinct from `unlocked` so the shell
    # routes to the forced new-password step instead of the main window
    # (FIBR-0019 § 4.6 step 4 / D6). A user arriving this way has, by
    # construction, no working password; leaving them unlocked with no way back
    # in tomorrow reproduces the problem one day later.
    recovery_unlocked = Signal()
    unlock_failed = Signal()
    # "Forgot password? Restore from a backup" — the shell owns the pre-login
    # restore flow (FIBR-0014 INV-8/D5).
    restore_requested = Signal()
    # "Forgot password? Start over…" — the shell owns the destructive reset flow
    # (FIBR-0030 § 3.1); like restore, the dialog only emits, holds no service ref.
    start_over_requested = Signal()

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self._worker: DeriveWorker | None = None
        # Failed-unlock backoff (FIBR-0095). The count/last-fail live in the
        # plaintext window.ini; the 1-Hz timer only drives the label — every real
        # submit re-reads remaining() from the file (D4, the file is authoritative).
        self._throttle = UnlockThrottle()
        self._remaining_seconds = 0
        self._countdown = QTimer(self)
        self._countdown.setInterval(1000)
        self._countdown.timeout.connect(self._tick_countdown)
        self.setWindowTitle(self.tr("Unlock finbreak"))

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText(self.tr("Master password"))
        self._unlock_button = QPushButton(self.tr("Unlock"))
        self._error = QLabel()
        self._restore_button = QPushButton(
            self.tr("Forgot password? Restore from a backup…")
        )
        self._restore_button.setObjectName("unlock_restore")
        self._restore_button.setFlat(True)
        # The more drastic option — always present (a user with no hint and no
        # password must still reach it), so it can't be gated on any stored state.
        self._start_over_button = QPushButton(self.tr("Forgot password? Start over…"))
        self._start_over_button.setObjectName("unlock_start_over")
        self._start_over_button.setFlat(True)

        # The recovery route (§ 4.6). Built unconditionally so the seam always
        # exists, and SHOWN only where `slots.recovery` is on disk: a vault whose
        # owner declined or removed the key must not be offered a route it does
        # not have (§ 6). Both routes share one throttle and one failure path —
        # a recovery route outside FIBR-0095's backoff would be a way around it.
        self._recovery_code = QLineEdit()
        self._recovery_code.setPlaceholderText(self.tr("Recovery code"))
        self._recovery_button = QPushButton(
            self.tr("Forgot password? Use your recovery code")
        )
        self._recovery_button.setObjectName("unlock_recovery")
        self._recovery_button.setFlat(True)
        offer_recovery = self._service.has_recovery_key()
        self._recovery_code.setVisible(offer_recovery)
        self._recovery_button.setVisible(offer_recovery)

        # Optional password hint (FIBR-0029 § 3.3). Read ONCE at build, pre-unlock,
        # needing no key (INV-3). Only add the reveal-on-click affordance when a
        # hint is actually set — no button when there is nothing to show (INV-1).
        # The hint is display-only: revealing it never touches the password field,
        # the throttle, or the unlock result (INV-9).
        hint = read_hint()
        self._hint_button: QPushButton | None = None
        self._hint_label: QLabel | None = None
        if hint.strip():
            self._hint_button = QPushButton(self.tr("Show hint"))
            self._hint_button.setObjectName("unlock_show_hint")
            self._hint_button.setFlat(True)
            self._hint_label = QLabel(hint)
            self._hint_label.setObjectName("unlock_hint_text")
            self._hint_label.setWordWrap(True)
            self._hint_label.hide()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Enter your master password to unlock.")))
        layout.addWidget(self._password)
        layout.addWidget(self._unlock_button)
        layout.addWidget(self._error)
        if self._hint_button is not None and self._hint_label is not None:
            layout.addWidget(self._hint_button)
            layout.addWidget(self._hint_label)
            self._hint_button.clicked.connect(self._reveal_hint)
        # Before restore: recovering with a code you kept costs nothing, where
        # restoring loses everything since the backup was taken.
        layout.addWidget(self._recovery_code)
        layout.addWidget(self._recovery_button)
        layout.addWidget(self._restore_button)
        # After (below) restore — it is the more drastic escape hatch (§ 3.1).
        layout.addWidget(self._start_over_button)
        layout.addWidget(buttons)

        self._unlock_button.clicked.connect(self._on_unlock)
        self._password.returnPressed.connect(self._on_unlock)
        self._recovery_button.clicked.connect(self._on_recovery_unlock)
        self._recovery_code.returnPressed.connect(self._on_recovery_unlock)
        self._restore_button.clicked.connect(self.restore_requested)
        self._start_over_button.clicked.connect(self.start_over_requested)

    @Slot()
    def _reveal_hint(self) -> None:
        # Display-only: show the pre-read hint and retire the button (INV-9).
        if self._hint_label is not None:
            self._hint_label.show()
        if self._hint_button is not None:
            self._hint_button.hide()

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
    def _on_unlock(self) -> None:
        if self._worker is not None:
            return  # a derivation is already in flight — ignore repeat submits
        # Authoritative backoff gate (FIBR-0095 D3): recomputed from window.ini on
        # every submit, so a backgrounded/unreliable timer can never grant an
        # attempt early. While a delay is owed, refuse without deriving.
        remaining = self._throttle.remaining(datetime.now(UTC))
        if remaining > 0:
            self._start_countdown(remaining)
            return
        self._error.clear()
        try:
            params = self._service.load_params()
        except KdfPolicyError:
            # NOT a wrong password — no password has been checked yet. The KDF
            # sidecar is missing / malformed / below the pinned strength floor.
            # Give it its own message (like SchemaVersionError) so a user with
            # the *correct* password isn't told to re-check it forever. Only the
            # HMAC-tamper case is meant to be indistinguishable from a wrong
            # password (security-model), not this. (indie-review M-auth1)
            self._error.setText(
                self.tr(
                    "finbreak can't read this vault's security-settings file "
                    "(it's missing or damaged), so it can't be unlocked. If you "
                    "have a backup of your vault folder, restore it."
                )
            )
            self.unlock_failed.emit()
            return

        password = bytearray(self._password.text().encode("utf-8"))
        self._password.clear()
        self._set_busy(True)

        worker = DeriveWorker(password, params, self)  # parented — Qt owns it
        worker.done.connect(self._on_derived)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(worker.deleteLater)  # no leaked QThread per attempt
        self._worker = worker
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        # Disable the field + Cancel too (not just the submit button): a second
        # Enter can't re-enter _on_unlock and orphan the running worker, and a
        # dismissal can't delete the parented worker mid-run (INV-2f).
        self._unlock_button.setEnabled(not busy)
        self._password.setEnabled(not busy)
        self._cancel.setEnabled(not busy)
        # Restore is a dismissal-like route (it tears down this dialog); disable it
        # mid-derivation too so the parented worker is never deleted under it.
        self._restore_button.setEnabled(not busy)
        # Start over is the same kind of dismissal-like route — no reset while a
        # derivation runs (FIBR-0030 § 3.1 / INV-9).
        self._start_over_button.setEnabled(not busy)
        # The recovery route submits into the same single-worker slot, so it is
        # locked out for exactly as long as the password route is.
        self._recovery_button.setEnabled(not busy)
        self._recovery_code.setEnabled(not busy)

    @Slot()
    def _on_recovery_unlock(self) -> None:
        """The § 4.6 recovery route — the counterpart of :meth:`_on_unlock`.

        Differs from the password route in exactly two places: which slot the
        derived key unwraps, and the local check-symbol test below. Everything
        else — the authoritative backoff gate, the single-worker guard, the
        failure recording — is shared, because a recovery route outside
        FIBR-0095's throttle would be an unthrottled guessing oracle (INV-10).
        """
        if self._worker is not None:
            return  # a derivation is already in flight — ignore repeat submits
        remaining = self._throttle.remaining(datetime.now(UTC))
        if remaining > 0:
            self._start_countdown(remaining)
            return

        # A bad check symbol proves a TYPO, not a guess, so it is reported at
        # once and is NOT counted as an unlock attempt (§ 4.6). It is a usability
        # device and carries no security weight — a code that passes it is still
        # decided by the unwrap, and by nothing else (INV-6).
        normalised = normalise(self._recovery_code.text())
        if not verify_check_symbol(normalised):
            self._error.setText(
                self.tr(
                    "That recovery code has a typo in it. Check it against the "
                    "copy you saved and try again."
                )
            )
            return
        self._error.clear()
        try:
            params = self._service.recovery_params()
        except (KdfPolicyError, VaultStateError):
            self._error.setText(
                self.tr(
                    "This vault has no recovery code set, so it can only be "
                    "unlocked with its master password."
                )
            )
            self.unlock_failed.emit()
            return

        # Argon2id eats the DECODED 17-byte payload, never the text (§ 4.3) —
        # the same input generation used, or a correctly transcribed code would
        # derive a different key and be refused.
        secret = bytearray(decode(normalised))
        self._recovery_code.clear()
        self._set_busy(True)

        worker = DeriveWorker(secret, params, self)  # parented — Qt owns it
        worker.done.connect(self._on_recovery_derived)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    @Slot(bytes)
    def _on_recovery_derived(self, raw: bytes) -> None:
        self._worker = None
        self._set_busy(False)
        try:
            unlocked = self._service.complete_recovery_unlock(raw)
        except SchemaVersionError:
            self._error.setText(
                self.tr(
                    "This vault was created by a newer version of finbreak. "
                    "Please update finbreak to open it."
                )
            )
            self.unlock_failed.emit()
            return
        except VaultStateError:
            self._error.setText(self.tr(_PAIRING_BROKEN))
            self.unlock_failed.emit()
            return
        if unlocked:
            self._throttle.reset()  # a correct code clears the counter (INV-5)
            # NOT `unlocked`: D6 requires a new master password before the main
            # window is reachable, and the shell routes on this signal.
            self.recovery_unlocked.emit()
        else:
            self._show_failure()

    @Slot(bytes)
    def _on_derived(self, raw: bytes) -> None:
        self._worker = None
        self._set_busy(False)
        try:
            unlocked = self._service.complete_unlock(raw)
        except RollbackAvailableError:
            # BEFORE the VaultStateError arm below, which is its base class:
            # this is the same broken pairing plus a pre-upgrade copy that
            # opens, and § 13.3 says the app offers it rather than hiding it.
            self._offer_rollback()
            return
        except VaultStateError:
            # The slot unwrapped but SQLCipher refused the DEK: the sidecar and
            # the database are from different vaults, or the database is damaged.
            # Give it its own message — it is indistinguishable to the user from
            # a wrong password, and the consequences differ absolutely, so the
            # destructive reset is never suggested from this state (§ 6).
            self._error.setText(self.tr(_PAIRING_BROKEN))
            self.unlock_failed.emit()
            return
        except SchemaVersionError:
            # A vault written by a newer build — distinct from a wrong password,
            # so it gets its own message rather than the generic failure.
            self._error.setText(
                self.tr(
                    "This vault was created by a newer version of finbreak. "
                    "Please update finbreak to open it."
                )
            )
            self.unlock_failed.emit()
            return
        if unlocked:
            self._throttle.reset()  # a correct password clears the counter (INV-5)
            self.unlocked.emit()
        else:
            self._show_failure()

    def _offer_rollback(self) -> None:
        """§ 13.3's terminal branch, made offerable (FIBR-0307 finding 7).

        Reachable from the PASSWORD route only, and not by omission: a
        migration-pending sidecar carries ``slots.master`` alone, so the
        recovery route never enters the ladder and its ``VaultStateError`` arm
        is the correct outcome there.

        The question blocks, which is safe for the same reason
        ``main_window``'s one surviving ``exec()`` is: this runs only from the
        unlock dialog, so the vault is LOCKED and FIBR-0065's auto-lock-under-
        a-nested-loop class cannot fire behind it.

        Declining changes nothing on disk. Only S6 removes the copy, so the
        offer is still there at the next unlock.
        """
        answer = QMessageBox.question(
            self,
            self.tr(_ROLLBACK_TITLE),
            self.tr(_ROLLBACK_OFFER),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._error.setText(self.tr(_PAIRING_BROKEN))
            self.unlock_failed.emit()
            return
        try:
            self._service.restore_pre_upgrade_copy()
        except OSError:
            # The copy could not be moved into place — a full or read-only
            # disk. Nothing partial is left that the ladder cannot pick up
            # (restore_rollback_copy's order is what guarantees that), so the
            # honest report is the refusal, not a claim that it worked.
            log.exception("restoring the pre-upgrade copy failed")
            self._error.setText(self.tr(_PAIRING_BROKEN))
            self.unlock_failed.emit()
            return
        self._error.setText(self.tr(_ROLLBACK_RESTORED))
        # Not `unlocked`: the vault is v1 again and still shut. The user types
        # their password once more and takes the ordinary v1 route (D2).
        self.unlock_failed.emit()

    @Slot(object)
    def _on_failure(self, _exc: object) -> None:
        self._worker = None
        self._set_busy(False)
        self._show_failure()

    def _show_failure(self) -> None:
        # Record the failure, then start the countdown to the freshly-owed delay
        # (FIBR-0095 D3). A recorded failure always owes a delay (>= 1 s), so the
        # countdown message replaces the generic one.
        now = datetime.now(UTC)
        self._throttle.record_failure(now)
        remaining = self._throttle.remaining(now)
        if remaining > 0:
            self._start_countdown(remaining)
        else:
            self._error.setText(
                self.tr("Could not unlock. Check your password and try again.")
            )
        self.unlock_failed.emit()

    def _set_submit_enabled(self, enabled: bool) -> None:
        # The countdown affordance toggles ONLY the submit controls — Cancel and
        # Restore stay usable so the owner can always leave the dialog. (Those two
        # are disabled *only* while a worker derives, via _set_busy — FIBR-0004
        # INV-2f; the cosmetic backoff countdown must not re-disable them.)
        self._unlock_button.setEnabled(enabled)
        self._password.setEnabled(enabled)

    def _start_countdown(self, remaining: float) -> None:
        """Show "Try again in N s", disable submit, and tick the label down to 0
        (D4 — cosmetic; the file is authoritative)."""
        self._remaining_seconds = math.ceil(remaining)
        self._set_submit_enabled(False)
        self._update_countdown_label()
        self._countdown.start()

    def _tick_countdown(self) -> None:
        self._remaining_seconds -= 1
        if self._remaining_seconds <= 0:
            self._countdown.stop()
            self._set_submit_enabled(True)  # re-enable submit; next submit re-checks
            return
        self._update_countdown_label()

    def _update_countdown_label(self) -> None:
        self._error.setText(
            self.tr("Could not unlock. Try again in {seconds}s.").format(
                seconds=self._remaining_seconds
            )
        )
