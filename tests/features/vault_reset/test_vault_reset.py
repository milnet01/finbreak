"""FIBR-0030 — destructive "start over" vault reset. Service-level footprint /
clean-slate / locked-safe / key-wipe tests (INV-1/2/3/8) plus GUI/shell tests for
the affordance, the double confirmation, state hygiene, routing, and the contained
failure path (INV-4/5/6/7/9/10). Uses pytest-qt's ``qtbot``; every vault lives
under ``tmp_path`` (the ``paths`` fixture) and every INI write hits the autouse
``window_ini`` tmp file. Enforces tests/features/vault_reset/spec.md.
"""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QMessageBox

from conftest import _PW
from finbreak.services.auth import AuthService
from finbreak.services.transactions import TransactionService
from finbreak.ui.start_over import CONFIRM_WORD, StartOverDialog
from finbreak.ui.unlock import UnlockDialog

pytestmark = pytest.mark.features

_NEW_PW = b"a brand new password"


def _exec_accepted(self) -> QDialog.DialogCode:
    return QDialog.DialogCode.Accepted


def _exec_rejected(self) -> QDialog.DialogCode:
    return QDialog.DialogCode.Rejected


def _seeded(paths) -> AuthService:
    auth = AuthService(*paths)
    auth.first_run(bytearray(_PW), "ZAR")
    return auth


# --------------------------------------------------------------------------- #
# INV-1 — complete on-disk footprint deletion (incl. orphaned WAL sidecars)
# --------------------------------------------------------------------------- #
def test_INV1_complete_footprint_deletion(paths):
    vault_p, sidecar_p = paths
    auth = _seeded(paths)
    auth.lock()  # close the connection — SQLite checkpoints+deletes the real -wal/-shm
    # Hardcode the literal sidecar names (do NOT derive from the code's own suffix):
    # a wrong-suffix derivation in reset_vault would leave these present.
    wal = vault_p.parent / "vault.db-wal"
    shm = vault_p.parent / "vault.db-shm"
    wal.write_bytes(b"orphan wal fragment")
    shm.write_bytes(b"orphan shm fragment")
    assert vault_p.exists() and sidecar_p.exists()

    auth.reset_vault()

    assert not vault_p.exists(), "vault.db removed"
    assert not sidecar_p.exists(), "kdf sidecar removed"
    assert not wal.exists(), "orphaned -wal removed"
    assert not shm.exists(), "orphaned -shm removed"


# --------------------------------------------------------------------------- #
# INV-2 — reset leaves a creatable clean slate (smoke)
# --------------------------------------------------------------------------- #
def test_INV2_clean_slate_for_next_vault(paths):
    vault_p, sidecar_p = paths
    auth = _seeded(paths)
    auth.reset_vault()
    assert AuthService(vault_p, sidecar_p).state() == "first_run", "both files gone"

    fresh = AuthService(vault_p, sidecar_p)
    fresh.first_run(bytearray(_NEW_PW), "USD")
    assert TransactionService(fresh.vault).list_transactions() == [], "new vault empty"
    fresh.lock()

    # The old master no longer opens the freshly-created vault.
    assert AuthService(vault_p, sidecar_p).unlock(bytearray(_PW)) is False


# --------------------------------------------------------------------------- #
# INV-3 — safe while locked (never-unlocked service)
# --------------------------------------------------------------------------- #
def test_INV3_safe_while_locked(paths):
    vault_p, sidecar_p = paths
    _seeded(paths).lock()  # a vault exists on disk
    locked = AuthService(vault_p, sidecar_p)  # never unlocked: _key None, conn unopened
    assert locked._key is None

    locked.reset_vault()  # must raise nothing

    assert not vault_p.exists() and not sidecar_p.exists()


# --------------------------------------------------------------------------- #
# INV-8 — key wiped via lock(); old data unrecoverable
# --------------------------------------------------------------------------- #
def test_INV8_key_wiped(paths):
    auth = _seeded(paths)
    auth.lock()
    auth.unlock(bytearray(_PW))
    key_buf = auth._key
    assert key_buf is not None and any(key_buf), "the unlocked key holds real bytes"

    auth.reset_vault()

    assert key_buf == bytearray(len(key_buf)), "the captured key buffer is zeroed"
    assert auth._key is None, "the service holds no key after reset"


# --------------------------------------------------------------------------- #
# INV-9 — affordance is unlock-screen-only and derivation-aware
# --------------------------------------------------------------------------- #
def test_INV9_affordance_unlock_only_and_busy_aware(qtbot, paths):
    auth = _seeded(paths)
    auth.lock()
    dialog = UnlockDialog(auth)
    qtbot.addWidget(dialog)
    assert dialog._start_over_button.objectName() == "unlock_start_over"

    fired: list[int] = []
    dialog.start_over_requested.connect(lambda: fired.append(1))
    dialog._start_over_button.click()
    assert fired == [1], "clicking fires start_over_requested"

    dialog._set_busy(True)
    assert not dialog._start_over_button.isEnabled(), "disabled during derivation"
    dialog._set_busy(False)
    assert dialog._start_over_button.isEnabled(), "re-enabled after derivation"


# --------------------------------------------------------------------------- #
# INV-5 — Step-2 OK gated on the exact CONFIRM_WORD
# --------------------------------------------------------------------------- #
def test_INV5_ok_gated_on_exact_confirm_word(qtbot):
    dialog = StartOverDialog()
    qtbot.addWidget(dialog)
    assert not dialog._ok.isEnabled(), "OK starts disabled"
    for bad in ("delete", "DELETE ", "DEL", ""):
        dialog._field.setText(bad)
        assert not dialog._ok.isEnabled(), f"{bad!r} keeps OK disabled"
    dialog._field.setText(CONFIRM_WORD)
    assert dialog._ok.isEnabled(), "exact DELETE enables OK"


# --------------------------------------------------------------------------- #
# INV-4 — double confirmation gates the delete
# --------------------------------------------------------------------------- #
def test_INV4_dialog_cancel_fires_rejected(qtbot):
    # Real-widget leg: the rejected->reject wiring must be live, else Cancel is dead
    # and exec() would hang headless. result()==Rejected is 0 from construction, so
    # the fired signal / isHidden() is the discriminating check.
    dialog = StartOverDialog()
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.rejected, timeout=1000):
        dialog._cancel.click()
    assert dialog.isHidden(), "Cancel aborts the dialog (rejected wiring live)"


def _build_window(auth, qtbot):
    from finbreak.ui.main_window import MainWindow

    window = MainWindow(auth)
    qtbot.addWidget(window)
    return window


def test_INV4_cancel_step1_no_delete(qtbot, paths, monkeypatch):
    auth = _seeded(paths)
    auth.lock()
    window = _build_window(auth, qtbot)
    called: list[int] = []
    monkeypatch.setattr(AuthService, "reset_vault", lambda self: called.append(1))
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel),
    )
    window._on_start_over()
    assert called == [], "Step-1 cancel does not reset"
    assert paths[0].exists() and paths[1].exists(), "vault files intact"


def test_INV4_cancel_step2_no_delete(qtbot, paths, monkeypatch):
    auth = _seeded(paths)
    auth.lock()
    window = _build_window(auth, qtbot)
    called: list[int] = []
    monkeypatch.setattr(AuthService, "reset_vault", lambda self: called.append(1))
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(StartOverDialog, "exec", _exec_rejected)
    window._on_start_over()
    assert called == [], "Step-2 cancel does not reset"
    assert paths[0].exists() and paths[1].exists(), "vault files intact"


# --------------------------------------------------------------------------- #
# INV-6 — vault-coupled window.ini keys cleared; benign state kept
# --------------------------------------------------------------------------- #
def test_INV6_coupled_keys_cleared_benign_kept(qtbot, paths, monkeypatch, window_ini):
    auth = _seeded(paths)
    auth.lock()
    window = _build_window(auth, qtbot)

    seed = QSettings(str(window_ini), QSettings.Format.IniFormat)
    seed.setValue("unlock/fail_count", 3)
    seed.setValue("unlock/last_fail", "2026-07-21T00:00:00+00:00")
    seed.setValue("hint/text", "the old hint")
    seed.setValue("benign/keep", "keep-me")
    seed.sync()

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(StartOverDialog, "exec", _exec_accepted)
    window._on_start_over()

    after = QSettings(str(window_ini), QSettings.Format.IniFormat)
    assert after.value("unlock/fail_count") is None, "throttle count cleared"
    assert after.value("unlock/last_fail") is None, "throttle stamp cleared"
    assert after.value("hint/text") is None, "old hint cleared"
    assert after.value("benign/keep") == "keep-me", "benign UI state retained"


# --------------------------------------------------------------------------- #
# INV-7 — returns to first-run after a successful reset
# --------------------------------------------------------------------------- #
def test_INV7_returns_to_first_run(qtbot, paths, monkeypatch):
    from finbreak.ui.first_run import FirstRunDialog

    auth = _seeded(paths)
    auth.lock()
    window = _build_window(auth, qtbot)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(StartOverDialog, "exec", _exec_accepted)
    window._on_start_over()

    assert not paths[0].exists() and not paths[1].exists(), "vault footprint gone"
    assert isinstance(window._dialog, FirstRunDialog), "routed to first-run"


# --------------------------------------------------------------------------- #
# INV-10 — a failed reset is contained (no crash, no partial state hygiene)
# --------------------------------------------------------------------------- #
def test_INV10_failed_reset_is_contained(qtbot, paths, monkeypatch, window_ini):
    auth = _seeded(paths)
    auth.lock()
    window = _build_window(auth, qtbot)

    seed = QSettings(str(window_ini), QSettings.Format.IniFormat)
    seed.setValue("unlock/fail_count", 4)
    seed.setValue("hint/text", "old hint")
    seed.sync()

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(StartOverDialog, "exec", _exec_accepted)

    def boom(self):
        raise OSError("vault held open by a second instance")

    monkeypatch.setattr(AuthService, "reset_vault", boom)
    critical: list[int] = []
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *a, **k: critical.append(1))
    )

    window._on_start_over()  # must not raise

    assert critical == [1], "the error box fired"
    after = QSettings(str(window_ini), QSettings.Format.IniFormat)
    assert after.value("unlock/fail_count") is not None, "coupled key intact on failure"
    assert after.value("hint/text") is not None, "hint intact on failure"
    assert isinstance(window._dialog, UnlockDialog), "stays on unlock, no first-run"
    auth.lock()
