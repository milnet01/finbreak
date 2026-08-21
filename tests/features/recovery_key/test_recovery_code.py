"""FIBR-0019 INV-5/INV-6/INV-11 — the recovery code itself. Enforces spec.md.

INV-5 and INV-6 are headless (``recovery_code`` is pure). INV-11 is NOT: its
trial-unwrap seam lives in ``ui/_password_hint.py``, the I/O half of the hint
pair, because ``services/password_hint.py``'s own contract is to be pure and the
only sidecar locator sits in a module that imports PySide6 (§ 7).

Why this exists: a "show it again" affordance, or a code written into
``window.ini`` beside the password hint, would turn a full-strength credential
into a plaintext file next to the vault it opens.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    code_secret,
    create_vault,
    forge_wrong_code_with_a_valid_check_symbol,
    keep_recovery_key,
    kek_for,
    opens_with,
    read_v2_sidecar,
    require_seam,
    unwrap_slot,
)

from finbreak import crypto
from finbreak.errors import KeyUnwrapError
from finbreak.keywrap import SLOT_RECOVERY
from finbreak.services.auth import AuthService
from finbreak.services.password_hint import HintPolicyError, validate_hint
from finbreak.services.recovery_code import decode, normalise, verify_check_symbol

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# INV-5 — the code is never persisted by the app of its own accord
# --------------------------------------------------------------------------- #
def test_code_never_reaches_a_plaintext_surface(
    tmp_path: Path, paths: tuple[Path, Path], service: AuthService
) -> None:
    _vault_path, _sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)

    # The § 4.5 step 8 carve-out, and the ONLY write this invariant permits: the
    # user chose a path and asked for the code to be saved there. That is the
    # user storing their own credential, not the app retaining it -- and the
    # difference between the two is what INV-5 is about. The test supplies the
    # path, so nothing about it is the app's doing.
    user_chosen_file = tmp_path / "my-recovery-code.txt"
    user_chosen_file.write_text(code)

    service.lock()

    needles = {
        "the display form": code.encode(),
        "the display form, lower case": code.lower().encode(),
        "the normalised base32": normalise(code).encode(),
        "the normalised base32, lower case": normalise(code).lower().encode(),
        "the decoded 17-byte payload": code_secret(code),
        "the decoded payload as hex": code_secret(code).hex().encode(),
    }

    offenders: dict[Path, list[str]] = {}
    for path in sorted(tmp_path.rglob("*")):
        if not path.is_file():
            continue
        # vault.db (and its WAL siblings) are EXCLUDED deliberately. The vault is
        # encrypted, so a plaintext search of it cannot fail -- and a leg that
        # cannot fail is not evidence. Keeping the code out of the vault's
        # CONTENTS is a different invariant needing a fixture that opens the
        # vault and searches its tables; this spec does not claim it.
        if path.name.startswith("vault.db"):
            continue
        blob = path.read_bytes()
        hits = [label for label, needle in needles.items() if needle in blob]
        if hits:
            offenders[path] = hits

    assert set(offenders) == {user_chosen_file}, (
        "INV-5: the recovery code must reach no plaintext surface the app wrote "
        "of its own accord -- not vault.kdf.json, not window.ini (plaintext by "
        "design, FIBR-0052 INV-5, and where the password hint already lives), "
        "not a log file, nothing under the data directory.\n"
        f"  expected: exactly one file holds it -- {user_chosen_file}, the path "
        "this test supplied as the user's choice\n"
        f"  actual:   {({str(p): hits for p, hits in offenders.items()}) or '{}'}"
    )


# --------------------------------------------------------------------------- #
# INV-6 — the check symbol is a typo detector, not authentication
# --------------------------------------------------------------------------- #
def test_valid_check_symbol_does_not_authenticate(
    paths: tuple[Path, Path], service: AuthService
) -> None:
    vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    data = read_v2_sidecar(sidecar_path)
    forged = forge_wrong_code_with_a_valid_check_symbol(code)

    assert verify_check_symbol(normalise(forged)), (
        "INV-6 precondition: the forged code must PASS the local check, or the "
        "legs below prove nothing -- a code rejected as a typo never reaches the "
        "unwrap and the test would be vacuous.\n"
        "  expected: verify_check_symbol(forged) is True\n"
        f"  actual:   False, for {forged!r}"
    )
    assert decode(normalise(forged)) != decode(normalise(code)), (
        "INV-6 precondition: the forgery must carry a DIFFERENT payload.\n"
        f"  expected: decode(forged) != decode(real)\n"
        f"  actual:   both decode to {decode(normalise(code)).hex()}"
    )

    with pytest.raises(KeyUnwrapError):
        unwrap_slot(code_secret(forged), data, SLOT_RECOVERY)

    forged_kek = kek_for(code_secret(forged), data, SLOT_RECOVERY)
    assert not opens_with(vault_path, sidecar_path, forged_kek), (
        "INV-6: a locally well-formed but wrong code must not open the vault by "
        "any route. The check symbol is a usability device and carries no "
        "security weight; using it to short-circuit the unwrap would make a "
        "typo-free guess look accepted.\n"
        "  expected: the vault stays closed\n"
        "  actual:   it opened"
    )


# --------------------------------------------------------------------------- #
# INV-11 — a stored hint may contain neither the password nor the code
# --------------------------------------------------------------------------- #
def test_hint_rejects_the_recovery_code(
    paths: tuple[Path, Path], service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _vault_path, sidecar_path = paths

    # The pure policy module keeps its two-argument signature: the recovery-slot
    # leg is the CALLER's, per the seam above (verified against the tree
    # 2026-08-20). A three-argument validate_hint would mean the trial-unwrap had
    # been pushed into the module whose contract is to be pure.
    assert list(inspect.signature(validate_hint).parameters) == ["hint", "password"], (
        "INV-11: services/password_hint.validate_hint stays pure and keeps its "
        "two-argument signature -- the trial-unwrap belongs in the I/O half.\n"
        "  expected: ['hint', 'password']\n"
        f"  actual:   {list(inspect.signature(validate_hint).parameters)}"
    )

    from finbreak.ui import _password_hint as hint_io

    check = require_seam(
        hint_io,
        "validate_hint_with_recovery",
        "INV-11's trial-unwrap lives in ui/_password_hint.py (§ 11): it needs "
        "paths.sidecar_path(), which sits in a module importing PySide6, so it "
        "cannot live in the pure services/password_hint.py.",
    )
    monkeypatch.setattr("finbreak.paths.sidecar_path", lambda: sidecar_path)

    code = create_vault(service)
    keep_recovery_key(service, code)

    # Leg 1 -- the real code, in the DISPLAY form the user holds. Normalising
    # first is load-bearing: `A1B2-C3D4-...`'s longest unbroken symbol run is
    # four, so a scan of the raw hint text finds no 28-symbol candidate and
    # cheerfully accepts a hint that IS the recovery code.
    with pytest.raises(HintPolicyError):
        check(f"same as the one on the card: {code}", MASTER_PASSWORD.decode())

    # Leg 2 -- a well-formed but WRONG code is accepted. The check symbol proves
    # only that it is not a typo; it is the trial-unwrap that decides, so a
    # candidate that does not unwrap is not the live code and the hint stands.
    forged = forge_wrong_code_with_a_valid_check_symbol(code)
    check(f"same as the one on the card: {forged}", MASTER_PASSWORD.decode())

    # Leg 3 -- no candidate, no key derivation at all. The common case must not
    # cost a ~46 MiB Argon2id run every time the user edits their hint.
    derivations: list[int] = []
    real_hash = crypto.hash_secret_raw

    def counting_hash(**kwargs: Any) -> bytes:
        derivations.append(1)
        return real_hash(**kwargs)

    monkeypatch.setattr("finbreak.crypto.hash_secret_raw", counting_hash)
    check("the one I always use", MASTER_PASSWORD.decode())
    assert derivations == [], (
        "INV-11: a hint holding no 28-symbol Crockford candidate must perform NO "
        "key derivation -- the trial-unwrap runs only where a candidate passes "
        "its check symbol locally.\n"
        "  expected: 0 Argon2id derivations\n"
        f"  actual:   {len(derivations)}"
    )
