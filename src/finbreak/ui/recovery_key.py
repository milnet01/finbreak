"""The two dialogs the recovery key needs (FIBR-0019 § 4.5 step 8, § 4.6 step 4).

Both are here rather than in ``first_run.py`` because both have two callers:
the code display is shown at vault creation, after a migration (D7) and by
Settings' **Add** / **Replace** (§ 4.7); the new-password step is reached from a
recovery unlock (D6) and nowhere else yet.

``RecoveryCodeDialog`` shows the code **once**. Nothing retains it — INV-5
forbids the app persisting it of its own accord, and the single exception is the
file the user names here, at the moment of display. That is the user storing
their own credential, not the app keeping it, and the difference between the two
is what INV-5 is about.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.services.auth import AuthService
from finbreak.services.recovery_code import generate_code

_TR_CONTEXT = "RecoveryKey"


def _tr(text: str) -> str:
    """Translate a string from a module-level function.

    ``QObject.tr`` needs an instance; these helpers are functions, so the
    translation goes through ``QCoreApplication.translate`` with an explicit
    context — the standard Qt idiom for exactly this case.
    """
    return QCoreApplication.translate(_TR_CONTEXT, text)


class RecoveryCodeDialog(QDialog):
    """Show a freshly generated recovery code, with **Keep** and **Decline**.

    Emits ``accepted`` for Keep and ``rejected`` for Decline; the slot write
    hangs off the first, via :func:`build_recovery_offer`. Nothing is written on
    Decline — § 4.5 defers the recovery-slot write to step 9 precisely so
    declining writes nothing rather than writing and then deleting, which would
    put a declined code's slot on disk in a file INV-12 asserts does not carry
    one.

    Shown by the caller, never with ``exec()``: see :func:`build_recovery_offer`.
    """

    def __init__(self, code: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._code = code
        self.setWindowTitle(self.tr("Your recovery code"))

        explanation = QLabel(
            self.tr(
                "This code can unlock your vault if you ever forget your master "
                "password. It is shown once and finbreak does not keep a copy — "
                "write it down or save it somewhere safe, away from this "
                "computer.\n\nIf you lose both your password and this code, your "
                "data cannot be recovered."
            )
        )
        explanation.setWordWrap(True)

        self._display = QLineEdit(code)
        self._display.setObjectName("recovery_code_display")
        self._display.setReadOnly(True)
        self._display.setCursorPosition(0)

        copy_button = QPushButton(self.tr("Copy"))
        copy_button.setObjectName("recovery_code_copy")
        save_button = QPushButton(self.tr("Save to a file…"))
        save_button.setObjectName("recovery_code_save")
        row = QHBoxLayout()
        row.addWidget(copy_button)
        row.addWidget(save_button)

        buttons = QDialogButtonBox()
        keep = buttons.addButton(
            self.tr("I've saved it — Keep"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        keep.setObjectName("recovery_code_keep")
        decline = buttons.addButton(
            self.tr("Don't set up a recovery code"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        decline.setObjectName("recovery_code_decline")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addWidget(self._display)
        layout.addLayout(row)
        layout.addWidget(buttons)

        copy_button.clicked.connect(self._copy)
        save_button.clicked.connect(self._save)

    def _copy(self) -> None:
        self._display.selectAll()
        self._display.copy()

    def _save(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self,
            self.tr("Save your recovery code"),
            "finbreak-recovery-code.txt",
            self.tr("Text files (*.txt)"),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._code + "\n")
        except OSError as exc:
            QMessageBox.warning(
                self,
                self.tr("Could not save the file"),
                self.tr("finbreak could not write that file: {error}").format(
                    error=exc
                ),
            )


class NewMasterPasswordDialog(QDialog):
    """§ 4.6 step 4 / D6 — set a new master password after a recovery unlock.

    Not dismissable: a user who arrived by the recovery route has, by
    construction, no working password, and leaving them unlocked with no way
    back in tomorrow reproduces the problem one day later. The re-wrap is 32
    bytes — the DEK does not change and nothing is re-encrypted.
    """

    def __init__(self, service: AuthService, parent: QWidget | None = None):
        super().__init__(parent)
        self._service = service
        self.setWindowTitle(self.tr("Choose a new master password"))

        explanation = QLabel(
            self.tr(
                "You unlocked finbreak with your recovery code. Choose a new "
                "master password now — your old one no longer works."
            )
        )
        explanation.setWordWrap(True)

        self._password = QLineEdit()
        self._password.setObjectName("new_master_password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText(self.tr("New master password"))
        self._confirm = QLineEdit()
        self._confirm.setObjectName("new_master_password_confirm")
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm.setPlaceholderText(self.tr("Confirm new master password"))
        self._error = QLabel()
        self._submit = QPushButton(self.tr("Set password"))
        self._submit.setObjectName("new_master_password_submit")

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addWidget(self._password)
        layout.addWidget(self._confirm)
        layout.addWidget(self._submit)
        layout.addWidget(self._error)

        self._submit.clicked.connect(self._on_submit)
        self._confirm.returnPressed.connect(self._on_submit)

    def reject(self) -> None:
        # Escape and Cancel are no-ops: there is no working password to fall
        # back to, so there is nothing to dismiss TO (D6).
        return

    def closeEvent(self, event: QCloseEvent) -> None:
        # The window [X] too. QDialog's own closeEvent routes through reject(),
        # which is already a no-op above — this is belt and braces, and it is
        # the same posture UnlockDialog takes while a derivation is in flight.
        event.ignore()

    def _on_submit(self) -> None:
        password = self._password.text()
        if not password:
            self._error.setText(self.tr("The password must not be empty."))
            return
        if password != self._confirm.text():
            self._error.setText(self.tr("The two passwords do not match."))
            return
        buffer = bytearray(password.encode("utf-8"))
        try:
            self._service.set_master_password(buffer)
        except Exception as exc:  # a failed re-wrap must not close this dialog
            self._error.setText(
                self.tr("Could not set the password: {error}").format(error=exc)
            )
            return
        finally:
            buffer[:] = bytes(len(buffer))
        self._password.clear()
        self._confirm.clear()
        self.accept()


def keep_recovery_code(
    service: AuthService, code: str, parent: QWidget | None = None
) -> bool:
    """§ 4.5 step 9 — the user pressed **Keep**, so write ``slots.recovery``.

    Declining is simply never calling this. The envelope is built either way
    (INV-12), so adding a recovery key later is a re-wrap of 32 bytes and never
    a re-encrypt.

    ``parent`` is the window, not the dialog that raised this: that dialog is on
    its way out by the time Keep is acted on, and a warning parented to a dying
    widget goes nowhere.
    """
    try:
        service.add_recovery_key(code)
    except Exception as exc:  # a failed re-wrap must be visible, not silent
        QMessageBox.warning(
            parent,
            _tr("Could not save the recovery code"),
            _tr("finbreak could not store your recovery code: {error}").format(
                error=exc
            ),
        )
        return False
    return True


def build_recovery_offer(
    service: AuthService, code: str, parent: QWidget | None = None
) -> RecoveryCodeDialog:
    """The § 4.5 step 8 display, wired to step 9 and **not shown yet**.

    The caller shows it, through the shell's own non-blocking dialog slot, for a
    reason this module got wrong once: ``exec()`` spins a nested event loop
    inside whatever signal handler called it — which is what the shell's whole
    dialog posture exists to avoid (FIBR-0051 D2) — and headless there is nobody
    to dismiss it, so the first-run suite hung outright rather than failing.

    One implementation for all three callers: vault creation, the
    post-migration offer (D7), and Settings' Add / Replace (§ 4.7). The same
    display, the same two ways out, and the same one write.
    """
    dialog = RecoveryCodeDialog(code, parent)
    dialog.accepted.connect(lambda: keep_recovery_code(service, code, parent))
    return dialog


def _confirm_master_password(service: AuthService, parent: QWidget | None) -> bool:
    """Gate a slot change on the current master password (§ 4.7).

    Matches how FIBR-0029's hint dialog authorises a within-session change: the
    KDF buffer is wiped in a ``finally``, and the plaintext ``str`` the widget
    already produced is immutable and falls out of scope for GC — the same
    acknowledged residual, not a new one.
    """
    text, accepted = QInputDialog.getText(
        parent,
        _tr("Confirm your master password"),
        _tr("Enter your master password to change your recovery code."),
        QLineEdit.EchoMode.Password,
    )
    if not accepted:
        return False
    buffer = bytearray(text.encode("utf-8"))
    try:
        if service.verify_password(buffer):
            return True
    finally:
        buffer[:] = bytes(len(buffer))
    QMessageBox.warning(
        parent,
        _tr("Wrong password"),
        _tr("That password is not correct."),
    )
    return False


def build_add_or_replace_offer(
    service: AuthService, parent: QWidget | None = None
) -> RecoveryCodeDialog | None:
    """§ 4.7 **Add** and **Replace** — they are the same act.

    Replacing writes a new slot over the old one, which invalidates the previous
    code by destroying the only copy of the DEK it wrapped. Both are a re-wrap
    of 32 bytes: the database is never touched.

    ``None`` when the master-password gate was cancelled or failed; otherwise a
    dialog for the caller to show.
    """
    if not _confirm_master_password(service, parent):
        return None
    return build_recovery_offer(service, generate_code(), parent)


def remove_recovery_key(service: AuthService, parent: QWidget | None = None) -> bool:
    """§ 4.7 **Remove**, behind a confirmation that says what is given up.

    Plainly, because it is not recoverable by any other route: after this the
    master password is the only thing that opens the vault, and forgetting it
    means the backup-restore and start-over paths and nothing else.
    """
    answer = QMessageBox.question(
        parent,
        _tr("Remove your recovery code?"),
        _tr(
            "Your recovery code will stop working immediately, and the copy you "
            "saved will be useless.\n\nAfter this, your master password is the "
            "only thing that can open your vault. If you forget it, your data "
            "cannot be recovered — restoring a backup or starting over would be "
            "the only options left."
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return False
    if not _confirm_master_password(service, parent):
        return False
    service.remove_recovery_key()
    return True
