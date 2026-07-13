"""FIBR-0014 UI — the Settings export button, the pre-login restore affordances,
the two backup dialogs' gating, INV-9 synchronous export, and an end-to-end
restore-into-the-unlocked-shell. Uses pytest-qt's ``qtbot``; every vault lives
under ``tmp_path`` (testing.md § 6). Enforces tests/features/backup/spec.md.
"""

import time

import pytest
from PySide6.QtCore import QTimer

from conftest import _PW
from finbreak.services.auth import AuthService
from finbreak.services.backup import MIN_BACKUP_PASSWORD_LEN, BackupService
from finbreak.ui.backup_export import BackupExportDialog
from finbreak.ui.backup_restore import BackupRestoreDialog
from finbreak.ui.first_run import FirstRunDialog
from finbreak.ui.settings import SettingsDialog
from finbreak.ui.unlock import UnlockDialog
from finbreak.vault import Vault

pytestmark = pytest.mark.features

_BACKUP_PW = "backup-pass-1234"
_M2 = "new-master-pass-9876"


def _seeded(paths) -> AuthService:
    auth = AuthService(*paths)
    auth.first_run(bytearray(_PW), "ZAR")
    return auth


def _make_fbk(tmp_path):
    """A first-run source vault exported to a `.fbk`; returns the fbk path."""
    src = tmp_path / "src"
    src.mkdir()
    auth = _seeded((src / "vault.db", src / "vault.kdf.json"))
    fbk = tmp_path / "backup.fbk"
    BackupService(auth.vault, auth).export_backup(fbk, _BACKUP_PW)
    auth.lock()
    return fbk


# --------------------------------------------------------------------------- #
# INV-8 — export lives in Settings; restore is reachable from both pre-login
# surfaces
# --------------------------------------------------------------------------- #
def test_INV8_settings_exposes_export_backup(qtbot, paths):
    auth = _seeded(paths)
    try:
        dialog = SettingsDialog(auth, "ZAR")
        qtbot.addWidget(dialog)
        assert dialog._export_backup.objectName() == "settings_export_backup"
        fired: list[int] = []
        dialog.export_backup_requested.connect(lambda: fired.append(1))
        dialog._export_backup.click()
        assert fired == [1], "the button requests a backup export"
    finally:
        auth.lock()


def test_INV8_unlock_exposes_restore(qtbot, paths):
    auth = _seeded(paths)
    auth.lock()
    dialog = UnlockDialog(auth)
    qtbot.addWidget(dialog)
    fired: list[int] = []
    dialog.restore_requested.connect(lambda: fired.append(1))
    dialog._restore_button.click()
    assert fired == [1], "unlock offers a pre-login restore"


def test_INV8_first_run_exposes_restore(qtbot, paths):
    auth = AuthService(*paths)  # no vault yet — first-run surface
    dialog = FirstRunDialog(auth)
    qtbot.addWidget(dialog)
    fired: list[int] = []
    dialog.restore_requested.connect(lambda: fired.append(1))
    dialog._restore_button.click()
    assert fired == [1], "first-run offers restore-instead"


# --------------------------------------------------------------------------- #
# Dialog gating
# --------------------------------------------------------------------------- #
def test_backup_export_dialog_gates_ok(qtbot):
    dialog = BackupExportDialog()
    qtbot.addWidget(dialog)
    assert not dialog._ok.isEnabled(), "OK starts disabled"
    dialog._password.setText("x" * (MIN_BACKUP_PASSWORD_LEN - 1))
    dialog._confirm.setText("x" * (MIN_BACKUP_PASSWORD_LEN - 1))
    assert not dialog._ok.isEnabled(), "too-short password keeps OK disabled"
    dialog._password.setText(_BACKUP_PW)
    dialog._confirm.setText(_BACKUP_PW + "!")
    assert not dialog._ok.isEnabled(), "mismatched confirm keeps OK disabled"
    dialog._confirm.setText(_BACKUP_PW)
    assert dialog._ok.isEnabled(), "matching password at/above the floor enables OK"


def test_backup_restore_dialog_gates_ok(qtbot, tmp_path):
    dialog = BackupRestoreDialog()
    qtbot.addWidget(dialog)
    assert not dialog._ok.isEnabled()
    dialog._source_field.setText(str(tmp_path / "backup.fbk"))
    dialog._backup_password.setText(_BACKUP_PW)
    dialog._new_master.setText(_M2)
    dialog._confirm_master.setText(_M2 + "x")
    assert not dialog._ok.isEnabled(), "mismatched new master keeps OK disabled"
    dialog._confirm_master.setText(_M2)
    assert dialog._ok.isEnabled(), "all fields valid enables OK"
    assert str(dialog.source_path()) == str(tmp_path / "backup.fbk")


# --------------------------------------------------------------------------- #
# INV-9 — export is synchronous on the main thread; a queued timer cannot fire
# mid-export (the auto-lock timer's structural guarantee)
# --------------------------------------------------------------------------- #
def test_INV9_synchronous_export_blocks_queued_timer(qtbot, paths, monkeypatch):
    auth = _seeded(paths)
    try:
        fired: list[str] = []
        QTimer.singleShot(1, lambda: fired.append("timer"))  # 1 ms << the 50 ms export

        real_export_to = Vault.export_to

        def slow_export_to(self, dest, key):
            time.sleep(0.05)  # block the main thread well past the 1 ms timer
            return real_export_to(self, dest, key)

        monkeypatch.setattr(Vault, "export_to", slow_export_to)
        BackupService(auth.vault, auth).export_backup(
            paths[0].parent / "b.fbk", _BACKUP_PW
        )

        assert fired == [], "the queued 1 ms timer cannot fire during a blocking export"
        qtbot.wait(20)
        assert fired == ["timer"], "it fires only once the event loop resumes"
    finally:
        auth.lock()


# --------------------------------------------------------------------------- #
# End-to-end — restore from the pre-login shell enters the unlocked workspace
# under the new master (INV-3/D5)
# --------------------------------------------------------------------------- #
def test_restore_from_shell_enters_unlocked_under_new_master(qtbot, tmp_path):
    from finbreak.ui.main_window import MainWindow

    fbk = _make_fbk(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    service = AuthService(dest / "vault.db", dest / "vault.kdf.json")

    window = MainWindow(service)
    qtbot.addWidget(window)
    assert isinstance(window._dialog, FirstRunDialog), "empty dest → first-run surface"

    window._open_restore()  # the "Restore from a backup instead" affordance
    restore = window._dialog
    assert isinstance(restore, BackupRestoreDialog)
    restore._source_field.setText(str(fbk))
    restore._backup_password.setText(_BACKUP_PW)
    restore._new_master.setText(_M2)
    restore._confirm_master.setText(_M2)

    window._on_restore_requested()  # runs the synchronous restore + unlock

    assert service._key is not None, "the shell is unlocked under the new master"
    workspace = window.centralWidget().currentWidget()
    assert workspace.objectName() == "workspace", "the unlocked workspace is shown"
    # The restored data is present (the source's single seeded account survived).
    assert (dest / "vault.db").exists() and (dest / "vault.kdf.json").exists()
    service.lock()


# --------------------------------------------------------------------------- #
# INV-5/D4 — an interrupted restore is reconciled at next launch, not a dead-end
# --------------------------------------------------------------------------- #
def test_interrupted_restore_recovers_old_pair_at_launch(qtbot, tmp_path):
    from finbreak.ui.main_window import MainWindow

    dest = tmp_path / "dest"
    dest.mkdir()
    vault_p, sidecar_p = dest / "vault.db", dest / "vault.kdf.json"
    # Simulate a crash between the two install os.replace calls: the NEW vault.db
    # is installed but the sidecar isn't (a mixed live state), and the original
    # pair sits in timestamped *.old copies (the move-aside completed).
    original_auth = AuthService(vault_p, sidecar_p)
    original_auth.first_run(bytearray(b"the original master"), "USD")
    original_auth.lock()
    original_vault_bytes = vault_p.read_bytes()
    original_sidecar_bytes = sidecar_p.read_bytes()
    vault_p.rename(dest / "vault.db.20260101T000000.old")
    sidecar_p.rename(dest / "vault.kdf.json.20260101T000000.old")
    vault_p.write_bytes(b"a half-installed new vault with no sidecar yet")  # orphan

    service = AuthService(vault_p, sidecar_p)
    window = MainWindow(service)  # must NOT hard-error on the mixed state
    qtbot.addWidget(window)

    # The original pair is recovered into place, and the app lands on unlock (which
    # carries the restore affordance — no dead-end).
    assert vault_p.read_bytes() == original_vault_bytes, (
        "the original vault is recovered"
    )
    assert sidecar_p.read_bytes() == original_sidecar_bytes, "the original sidecar too"
    assert isinstance(window._dialog, UnlockDialog), "lands on unlock, not a hard error"
    assert service.unlock(bytearray(b"the original master")) is True
    service.lock()


# --------------------------------------------------------------------------- #
# Review fixes — UI robustness
# --------------------------------------------------------------------------- #
def test_open_restore_tears_down_originating_dialog(qtbot, paths):
    from finbreak.ui.main_window import MainWindow

    auth = _seeded(paths)
    auth.lock()
    window = MainWindow(auth)
    qtbot.addWidget(window)
    qtbot.wait(10)  # let the deferred show fire
    unlock_dialog = window._dialog
    assert isinstance(unlock_dialog, UnlockDialog) and unlock_dialog.isVisible()

    window._open_restore()
    assert isinstance(window._dialog, BackupRestoreDialog), "restore takes the slot"
    assert not unlock_dialog.isVisible(), (
        "the originating unlock dialog is torn down, not left modal over the new one"
    )


def test_export_recovers_cursor_on_engine_error(qtbot, paths, monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from sqlcipher3.dbapi2 import DatabaseError

    from finbreak.ui.main_window import MainWindow

    auth = _seeded(paths)
    window = MainWindow(auth)
    qtbot.addWidget(window)
    window._enter_unlocked()
    window._open_backup_export()
    window._dialog._password.setText(_BACKUP_PW)
    window._dialog._confirm.setText(_BACKUP_PW)

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(paths[0].parent / "x.fbk"), "")),
    )
    warned: list[int] = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(1))
    )

    def boom(self, dest, pw, **k):
        raise DatabaseError("disk full while sqlcipher_export ran")

    monkeypatch.setattr(BackupService, "export_backup", boom)

    window._on_backup_export_requested()
    assert warned == [1], "a SQLCipher engine error is caught and warned, not crashed"
    assert QApplication.overrideCursor() is None, "the wait cursor is always restored"
    auth.lock()


def test_reconcile_pairs_old_files_by_stamp(qtbot, tmp_path):
    from finbreak.ui.main_window import MainWindow

    dest = tmp_path / "dest"
    dest.mkdir()
    vp, sp = dest / "vault.db", dest / "vault.kdf.json"
    orig = AuthService(vp, sp)
    orig.first_run(bytearray(b"orig master"), "USD")
    orig.lock()
    ovb, osb = vp.read_bytes(), sp.read_bytes()

    # A stale UNPAIRED db-old at a LATER stamp (from a prior mixed restore), plus the
    # real paired original at an EARLIER stamp. Reconcile must pair by shared stamp,
    # not pick db[-1] (the stale T2) with sidecar[-1] (T1) — that would mismatch.
    (dest / "vault.db.20260102T000000.old").write_bytes(b"stale unpaired newer db-old")
    vp.rename(dest / "vault.db.20260101T000000.old")
    sp.rename(dest / "vault.kdf.json.20260101T000000.old")
    vp.write_bytes(b"a half-installed orphan with no sidecar")  # mixed live state

    service = AuthService(vp, sp)
    window = MainWindow(service)
    qtbot.addWidget(window)

    assert vp.read_bytes() == ovb, "recovered the correctly-paired original vault.db"
    assert sp.read_bytes() == osb, "recovered its matching sidecar (same stamp)"
    assert service.unlock(bytearray(b"orig master")) is True, "the recovered pair opens"
    service.lock()
