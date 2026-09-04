"""FIBR-0019 § 6 — the failure modes that must not read as a wrong password.

§ 6 separates two outcomes that look identical to a user and differ absolutely
in consequence: a **wrong credential**, where trying again is the answer, and a
**broken pairing**, where the key record unwrapped and the database still would
not open. The second is not a failed attempt at all -- the user's data is very
likely intact and mispaired -- so § 6 forbids offering the destructive reset
from it, and ``ui/unlock.py`` carries a message written for exactly this state.

Why this exists: ``auth._open_with`` reported the second as the first, which
left ``_pairing_broken()`` unreachable and put "Start over" in front of a user
whose vault was recoverable (FIBR-0307 finding 2).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    code_secret,
    create_v1_vault,
    create_vault,
    keep_recovery_key,
    kek_for,
    read_sidecar,
    read_v2_sidecar,
    require_seam,
)

from finbreak.errors import VaultStateError
from finbreak.keywrap import SLOT_RECOVERY
from finbreak.services.auth import AuthService
from finbreak.services.vault_migration import (
    MIGRATING_SUFFIX,
    migrate_to_v2,
    rollback_copy_paths,
)

pytestmark = pytest.mark.features

OTHER_PASSWORD = b"a completely different master password"


@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def _break_the_pairing(tmp_path: Path, paths: tuple[Path, Path]) -> None:
    """Leave this vault's sidecar beside a DIFFERENT vault's database.

    The sidecar is untouched, so the master and recovery slots still unwrap
    normally and the credential is PROVEN correct -- and the DEK they yield is
    not the key the database on disk was written under. That is § 6's broken
    pairing, reached without corrupting a byte of either file.
    """
    vault_path, _sidecar_path = paths
    other_dir = tmp_path / "a-different-vault"
    other_dir.mkdir()
    other = AuthService(other_dir / "vault.db", other_dir / "vault.kdf.json")
    create_vault(other, OTHER_PASSWORD)
    other.lock()
    vault_path.write_bytes((other_dir / "vault.db").read_bytes())


def test_a_broken_pairing_is_not_reported_as_a_wrong_password(
    tmp_path: Path, paths: tuple[Path, Path], service: AuthService
) -> None:
    create_vault(service)
    service.lock()
    _break_the_pairing(tmp_path, paths)

    with pytest.raises(VaultStateError):
        service.unlock(bytearray(MASTER_PASSWORD))


def test_the_recovery_route_reports_a_broken_pairing_too(
    tmp_path: Path, paths: tuple[Path, Path], service: AuthService
) -> None:
    _vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    data = read_v2_sidecar(sidecar_path)
    kek = kek_for(code_secret(code), data, SLOT_RECOVERY)
    _break_the_pairing(tmp_path, paths)

    with pytest.raises(VaultStateError):
        service.complete_recovery_unlock(bytes(kek))


def test_the_unlock_dialog_names_the_broken_pairing(
    qtbot: Any, tmp_path: Path, paths: tuple[Path, Path], service: AuthService
) -> None:
    """The § 6 message must actually reach the screen.

    It was written, single-homed and correct, and nothing could raise the error
    it keys on -- so the words a mispaired user needed were dead code while the
    generic "check your password and try again" was what they got.
    """
    from finbreak.ui.unlock import UnlockDialog, _pairing_broken

    create_vault(service)
    service.lock()
    _break_the_pairing(tmp_path, paths)

    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    field = require_seam(dialog, "_password", "§ 4.6: the password route's input.")
    submit = require_seam(
        dialog, "_on_unlock", "§ 4.6: the password route's submit handler."
    )
    error = require_seam(dialog, "_error", "§ 6: the dialog's single error surface.")

    failed: list[int] = []
    dialog.unlock_failed.connect(lambda: failed.append(1))

    field.setText(MASTER_PASSWORD.decode())
    submit()

    # Both § 6 branches set the message BEFORE emitting, so the text is final at
    # emit time -- this waits on the signal and asserts the state it guarantees,
    # rather than on a proxy that could return a turn early.
    qtbot.waitUntil(lambda: bool(failed), timeout=30_000)

    assert error.text() == _pairing_broken(), (
        "§ 6: the slot unwrapped and SQLCipher still refused the DEK, so this "
        "is a broken pairing and not a wrong password. Telling the user to "
        "check their password sends them to the destructive reset with their "
        "data intact but mispaired -- which § 6 forbids in as many words.\n"
        f"  expected: {_pairing_broken()!r}\n"
        f"  actual:   {error.text()!r}"
    )


# --------------------------------------------------------------------------- #
# FP02 finding 7 — § 13.3's rollback offer has to reach a screen
# --------------------------------------------------------------------------- #
def _stall_with_every_route_exhausted(paths: tuple[Path, Path]) -> None:
    """Leave the pair in § 13.3's last bullet, with D8's copy intact beside it.

    A v1 vault is migrated with a crash injected before S5, so the sidecar is
    the migration-pending v2 one and S0's ``.pre-v2`` pair is on disk. The
    ``.migrating`` database is then removed and the live one overwritten, so
    neither the DEK nor KEK-master opens anything: every branch of the ladder
    is exhausted with the password already proven right.
    """
    vault_path, sidecar_path = paths
    vault, _params, key = create_v1_vault(vault_path, sidecar_path)
    vault.close()

    def abort_before_s5(step: str) -> None:
        if step == "S5":
            raise _Abort("injected crash before S5")

    with pytest.raises(_Abort):
        migrate_to_v2(vault_path, sidecar_path, bytearray(key), on_step=abort_before_s5)

    vault_path.with_name(vault_path.name + MIGRATING_SUFFIX).unlink()
    vault_path.write_bytes(b"not a database, not any more" * 512)
    vault_path.with_name(vault_path.name + "-wal").unlink(missing_ok=True)


class _Abort(RuntimeError):
    """The injected crash -- a distinct type, so a genuine migration failure is
    never mistaken for the one this test asked for."""


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_the_unlock_dialog_offers_the_pre_upgrade_copy(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
    paths: tuple[Path, Path],
    answer: str,
) -> None:
    """§ 13.3: "the app says a pre-upgrade copy exists and offers to restore it".

    The service could raise this state all it liked and no UI path named the
    ``.pre-v2`` pair, so the user got the bare broken-pairing refusal with their
    own pre-upgrade vault sitting in the same directory -- § 13.3 calls making
    the offer "the whole return on D8" (FIBR-0307 finding 7).

    Declining is a real answer: the user keeps the stalled pair and the copy is
    left where it is, so the offer can be taken at the next unlock.
    """
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.unlock import UnlockDialog

    vault_path, sidecar_path = paths
    _stall_with_every_route_exhausted(paths)
    copy_vault, copy_sidecar = rollback_copy_paths(vault_path, sidecar_path)

    asked: list[str] = []
    chosen = (
        QMessageBox.StandardButton.Yes
        if answer == "yes"
        else QMessageBox.StandardButton.No
    )

    def press(
        _parent: Any, _title: str, text: str, *_a: Any, **_k: Any
    ) -> QMessageBox.StandardButton:
        asked.append(text)
        return chosen

    monkeypatch.setattr(QMessageBox, "question", staticmethod(press))

    service = AuthService(vault_path, sidecar_path)
    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    field = require_seam(dialog, "_password", "§ 4.6: the password route's input.")
    submit = require_seam(
        dialog, "_on_unlock", "§ 4.6: the password route's submit handler."
    )

    failed: list[int] = []
    dialog.unlock_failed.connect(lambda: failed.append(1))
    field.setText(MASTER_PASSWORD.decode())
    submit()
    qtbot.waitUntil(lambda: bool(failed), timeout=30_000)

    assert len(asked) == 1, (
        "§ 13.3: with a verified pre-upgrade copy beside the vault the app "
        "must OFFER it rather than refuse. One question, once -- not none "
        "(the finding) and not one per branch.\n"
        f"  expected: 1 question asked\n  actual:   {len(asked)}"
    )
    assert ".pre-v2" in asked[0] or "before" in asked[0].lower(), (
        "the offer has to name what is being restored, or the user cannot "
        "tell it from the destructive reset § 6 forbids here.\n"
        "  expected: the copy described as pre-upgrade\n"
        f"  actual:   {asked[0]!r}"
    )

    restored_v1 = "sidecar_version" not in read_sidecar(sidecar_path)
    assert restored_v1 == (answer == "yes"), (
        "Yes restores the pre-upgrade pair, so the sidecar is v1 again; No "
        "changes nothing, so the stalled migration-pending pair is still "
        "there and the offer can be taken next time.\n"
        f"  expected: restored == {answer == 'yes'} after {answer}\n"
        f"  actual:   {restored_v1}"
    )
    assert copy_vault.exists() == (answer == "no"), (
        "Yes MOVES the copy onto the live pair -- a second copy of the vault "
        "left behind is what S6 exists to prevent. No leaves it untouched.\n"
        f"  expected: the copy present == {answer == 'no'}\n"
        f"  actual:   {copy_vault.exists()}, sidecar {copy_sidecar.exists()}"
    )


# --------------------------------------------------------------------------- #
# FIBR-0310 R5 — a damaged recovery slot is told apart from an absent one
# --------------------------------------------------------------------------- #
def test_a_damaged_recovery_slot_is_not_reported_as_an_absent_one(
    qtbot: Any, paths: tuple[Path, Path], service: AuthService
) -> None:
    """Two different things must not share one sentence.

    Loosening the loader (R5) means a damaged recovery slot now reaches
    ``recovery_params``, where an absent one already raised. Both arrived at
    the same handler, whose sentence is "This vault has no recovery code set" --
    which a user holding a code they wrote down would read as having imagined
    setting one, and which points them at no remedy. The master password DOES
    still open the vault, so the damaged case says that instead.
    """
    from finbreak.ui.unlock import UnlockDialog, _recovery_slot_damaged

    _vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    damaged = read_v2_sidecar(sidecar_path)
    damaged["slots"][SLOT_RECOVERY]["nonce_hex"] = "00" * 4
    sidecar_path.write_text(json.dumps(damaged), encoding="utf-8")

    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    field = require_seam(dialog, "_recovery_code", "§ 4.6: the recovery input.")
    submit = require_seam(
        dialog, "_on_recovery_unlock", "§ 4.6: the recovery route's submit handler."
    )
    error = require_seam(dialog, "_error", "§ 6: the dialog's single error surface.")

    field.setText(code)
    submit()

    assert error.text() == _recovery_slot_damaged(), (
        "the recovery route reported a DAMAGED slot with the message for an "
        "ABSENT one. The user's saved code is real and their record of it is "
        "broken; telling them no code is set denies the first and hides the "
        "second, and names no way forward (FIBR-0310 R5).\n"
        f"  expected: {_recovery_slot_damaged()!r}\n"
        f"  actual:   {error.text()!r}"
    )


def test_FIBR0328_an_unreadable_sidecar_is_not_silently_no_recovery_key(
    service: AuthService, monkeypatch: Any, caplog: Any
) -> None:
    """``has_recovery_key`` answers False for two different reasons, and only
    one of them is ordinary (2026-08-31 audit, LOW/INFO).

    A v1 vault has no envelope, so it has no recovery slot — expected, and
    nothing to report. A ``KdfPolicyError`` means the sidecar IS v2 and its KDF
    record is unacceptable, so the vault may well HAVE a recovery key nobody can
    read. Both collapsed to a bare False.

    False stays the answer either way — the § 4.6 route derives under those very
    params, so offering it would only fail later. What was missing is any trace
    of WHY the route vanished, on the one screen a locked-out user is looking at.

    Both legs are asserted: the anomaly must be reported, and the ordinary case
    must stay quiet, or the log says nothing by saying everything.
    """
    import logging

    from finbreak.errors import KdfPolicyError

    def _damaged() -> Any:
        raise KdfPolicyError("memory_kib is below the floor")

    monkeypatch.setattr(service, "read_sidecar", _damaged)
    with caplog.at_level(logging.WARNING, logger="finbreak.services.auth"):
        assert service.has_recovery_key() is False
    assert any("recovery slot" in record.message for record in caplog.records), (
        "a sidecar we cannot read must leave a trace, not just hide the route"
    )

    def _still_v1() -> Any:
        raise VaultStateError("this vault has not been migrated to the envelope")

    caplog.clear()
    monkeypatch.setattr(service, "read_sidecar", _still_v1)
    with caplog.at_level(logging.WARNING, logger="finbreak.services.auth"):
        assert service.has_recovery_key() is False
    assert not caplog.records, (
        "a v1 vault is the ordinary pre-migration state; warning about it would "
        "bury the case that matters"
    )
