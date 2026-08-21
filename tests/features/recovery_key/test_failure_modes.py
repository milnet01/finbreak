"""FIBR-0019 § 6 — the failure modes that must not read as a wrong password.

§ 6 separates two outcomes that look identical to a user and differ absolutely
in consequence: a **wrong credential**, where trying again is the answer, and a
**broken pairing**, where the key record unwrapped and the database still would
not open. The second is not a failed attempt at all -- the user's data is very
likely intact and mispaired -- so § 6 forbids offering the destructive reset
from it, and ``ui/unlock.py`` carries a message written for exactly this state.

Why this exists: ``auth._open_with`` reported the second as the first, which
left ``_PAIRING_BROKEN`` unreachable and put "Start over" in front of a user
whose vault was recoverable (FIBR-0307 finding 2).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    code_secret,
    create_vault,
    keep_recovery_key,
    kek_for,
    read_v2_sidecar,
    require_seam,
)

from finbreak.errors import VaultStateError
from finbreak.keywrap import SLOT_RECOVERY
from finbreak.services.auth import AuthService

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
    from finbreak.ui.unlock import _PAIRING_BROKEN, UnlockDialog

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

    assert error.text() == _PAIRING_BROKEN, (
        "§ 6: the slot unwrapped and SQLCipher still refused the DEK, so this "
        "is a broken pairing and not a wrong password. Telling the user to "
        "check their password sends them to the destructive reset with their "
        "data intact but mispaired -- which § 6 forbids in as many words.\n"
        f"  expected: {_PAIRING_BROKEN!r}\n"
        f"  actual:   {error.text()!r}"
    )
