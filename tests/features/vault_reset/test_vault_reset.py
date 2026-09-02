"""FIBR-0030 — destructive "start over" vault reset. Service-level footprint /
clean-slate / locked-safe / key-wipe tests (INV-1/2/3/8) plus GUI/shell tests for
the affordance, the double confirmation, state hygiene, routing, and the contained
failure path (INV-4/5/6/7/9/10). Uses pytest-qt's ``qtbot``; every vault lives
under ``tmp_path`` (the ``paths`` fixture) and every INI write hits the autouse
``window_ini`` tmp file. Enforces tests/features/vault_reset/spec.md.
"""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox

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


def test_INV5_confirm_word_is_interpolated_not_inside_the_tr_literal(qtbot):
    """FIBR-0216 — the module docstring says the label "keeps DELETE un-translated
    so a localized label can never disable the OK gate forever". It did not: the
    word sat INSIDE `tr("Type DELETE to confirm")`, and a translator reading the
    .ts file sees only that string. Translate it and the dialog tells the user to
    type a word the comparison will never accept, permanently disabling OK on the
    app's one irreversible action.

    The code comment above the line said "keep DELETE un-translated", which is a
    note to the developer, not something the extraction can enforce. Interpolating
    it makes the guarantee structural — the same idiom `_about_text` uses for the
    version (coding.md § 5.2)."""
    import inspect

    from finbreak.ui import start_over

    source = inspect.getsource(start_over)
    assert f'tr("Type {CONFIRM_WORD}' not in source, (
        "the confirm word is inside the translatable literal — a translator can "
        "render it away and disable OK forever"
    )

    dialog = StartOverDialog()
    qtbot.addWidget(dialog)
    labels = [w.text() for w in dialog.findChildren(QLabel)]
    assert any(CONFIRM_WORD in text for text in labels), (
        "the rendered label still names the word to type"
    )


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


def test_INV1_footprint_includes_the_migration_artefacts(paths):
    """FIBR-0019's on-disk artefacts are part of the footprint.

    The rollback pair (`vault.db.pre-v2`, `vault.kdf.json.pre-v2`) is deleted
    only by a COMPLETED migration, so the reachable sequence -- migration
    interrupted, user declines the section 13.3 rollback offer and chooses
    Start over -- otherwise left a complete, intact, encrypted copy of the old
    vault sitting beside the newly created one. security-model INV-12 promises
    the reset removes the vault's complete on-disk footprint and distinguishes
    that from residual sectors; a whole surviving file is not that residual.

    Names are hardcoded rather than derived from the code's own suffixes, for
    the reason the sibling leg above gives.
    """
    vault_p, sidecar_p = paths
    auth = _seeded(paths)
    auth.lock()
    d = vault_p.parent
    artefacts = [
        d / "vault.db.pre-v2",
        d / "vault.db.pre-v2-wal",
        d / "vault.db.pre-v2-shm",
        d / "vault.kdf.json.pre-v2",
        d / "vault.db.migrating",
        d / "vault.db.migrating-wal",
        d / "vault.db.migrating-shm",
        d / "vault.kdf.json.migrating",
    ]
    for p in artefacts:
        p.write_bytes(b"an encrypted copy of the user's old vault")

    auth.reset_vault()

    left = [p.name for p in artefacts if p.exists()]
    assert not left, f"start over left the old vault behind: {left}"


# --------------------------------------------------------------------------- #
# INV-11 — a restore's *.old triple is part of the footprint too (FIBR-0318 H3)
# --------------------------------------------------------------------------- #
def test_INV11_old_backup_copies_removed(paths):
    """``BackupService._install`` (services/backup.py) moves any existing vault
    aside to a timestamped ``*.old`` triple on every restore
    (``vault.db.<stamp>.old`` + its ``-wal``/``-shm`` siblings, and
    ``vault.kdf.json.<stamp>.old``), and nothing in ``src/`` ever unlinks one.
    ``reset_vault`` builds its own ``extra`` list of migration artefacts
    (the leg above) but the ``.old`` set is absent from it.

    security-model.md INV-12 promises reset removes the vault's *complete*
    on-disk footprint, and rests its accepted residual sectors on being
    "useless without the (now-gone) key" -- a ``.old`` pair is not that
    residual: it opens under the password the user had *before* the restore
    that created it, key and all. Either the code or INV-12 moves; this locks
    the code moving (FIBR-0318 H3).

    Planted rather than produced by a real ``BackupService.restore_backup()``
    call, matching the sibling artefact-injection leg immediately above
    (and INV-1's orphaned-WAL leg) rather than pulling the backup suite's
    fixtures into this one. The names are hardcoded from
    ``services/backup.py``'s ``_install`` (a literal stamp stands in for the
    real microsecond one -- the exact stamp format is that method's business,
    not this test's), not derived from the code, for the reason the sibling
    legs give.
    """
    vault_p, sidecar_p = paths
    auth = _seeded(paths)
    auth.lock()
    d = vault_p.parent
    stamp = "20260101T000000000000"
    artefacts = [
        d / f"vault.db.{stamp}.old",
        d / f"vault.db.{stamp}.old-wal",
        d / f"vault.db.{stamp}.old-shm",
        d / f"vault.kdf.json.{stamp}.old",
    ]
    for p in artefacts:
        p.write_bytes(b"an encrypted copy of the user's pre-restore vault")

    # A neighbour whose suffix is NOT one of ours. Both callers of the shared
    # enumeration DELETE, and the glob that finds a `.old` set would match this
    # too, so the suffix guard is what stops an irreversible over-broad delete.
    # mutation_probe found it unmeasured: removing the guard left the suite
    # green until this file existed.
    stranger = d / f"vault.db.{stamp}.oldish"
    stranger.write_bytes(b"not written by finbreak")

    auth.reset_vault()

    left = [p.name for p in artefacts if p.exists()]
    assert not left, f"start over left a restore's *.old copy behind: {left}"
    assert stranger.exists(), (
        "start over deleted a file finbreak did not write. The `.old` sweep "
        "matches by glob, so it must refuse a suffix it does not recognise -- "
        "deleting the user's own file is worse than leaving a stale copy.\n"
        f"  expected: {stranger.name} still present\n"
        "  actual:   removed"
    )
