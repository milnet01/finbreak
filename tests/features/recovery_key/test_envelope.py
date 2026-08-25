"""FIBR-0019 INV-1/INV-2/INV-3 — the key envelope. Enforces spec.md.

Headless: ``keywrap`` and ``crypto`` are Qt-free (§ 7). Every vault lives under
``tmp_path``; no network, no real financial data (``testing.md`` § 6).

Why this exists: today the Argon2id output IS SQLCipher's raw key
(``vault.py::_connect``), so the set of credentials that can open a vault has
exactly one member and cannot be extended. These three lock the envelope that
replaces it.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from pathlib import Path
from typing import get_args, get_type_hints

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    code_secret,
    create_vault,
    keep_recovery_key,
    kek_for,
    opens_with,
    read_v2_sidecar,
    slot_params,
    slot_record,
    unwrap_slot,
)

from finbreak.crypto import KEY_LEN, load_and_validate_params
from finbreak.errors import KdfPolicyError, KeyUnwrapError
from finbreak.keywrap import SLOT_MASTER, SLOT_RECOVERY, unwrap_dek, wrap_dek
from finbreak.services.auth import AuthService
from finbreak.services.recovery_code import decode, normalise

pytestmark = pytest.mark.features

_SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "finbreak"
_WRAPPERS = frozenset({"wrap_dek", "unwrap_dek"})


@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def _flip_first_hex_nibble(hex_value: str) -> str:
    """One bit of the first byte, flipped — the minimal tamper."""
    first = int(hex_value[0], 16) ^ 0x1
    return f"{first:x}" + hex_value[1:]


# --------------------------------------------------------------------------- #
# INV-1 — the SQLCipher raw key is a random DEK, never a derived credential
# --------------------------------------------------------------------------- #
def test_dek_is_not_derived_from_any_credential(
    tmp_path: Path, paths: tuple[Path, Path], service: AuthService
) -> None:
    vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    data = read_v2_sidecar(sidecar_path)

    # Leg 1 -- KEK-master is not the database key. This leg ALONE only fails in
    # the degenerate case where the credential-derived key IS the raw key, which
    # is exactly today's code; leg 2 is what excludes § 8.1's rejected design.
    kek_master = kek_for(MASTER_PASSWORD, data, SLOT_MASTER)
    assert not opens_with(vault_path, sidecar_path, kek_master), (
        "INV-1 leg 1: the vault opened with derive_key(master_password, "
        "slots.master.salt) -- so the credential-derived key IS SQLCipher's raw "
        "key and there is no envelope.\n"
        "  expected: PRAGMA key with KEK-master FAILS to open vault.db\n"
        "  actual:   it opened"
    )

    # Leg 2 -- and this is the one that bites. Two vaults, the SAME master
    # password, must hold DIFFERENT DEKs. Under § 8.1's rejected design (the
    # legacy Argon2id output declared to BE the DEK, wrapped under a freshly
    # salted KEK) leg 1 still passes, because KEK-master != DEK there too.
    second_dir = tmp_path / "second-vault"
    second_dir.mkdir()
    second = AuthService(second_dir / "vault.db", second_dir / "vault.kdf.json")
    second_code = create_vault(second)
    keep_recovery_key(second, second_code)
    second.lock()

    dek_one = bytes(unwrap_slot(MASTER_PASSWORD, data, SLOT_MASTER))
    dek_two = bytes(
        unwrap_slot(
            MASTER_PASSWORD,
            read_v2_sidecar(second_dir / "vault.kdf.json"),
            SLOT_MASTER,
        )
    )

    assert len(dek_one) == KEY_LEN, (
        f"INV-1: the DEK is SQLCipher's raw key.\n"
        f"  expected: {KEY_LEN} bytes\n  actual:   {len(dek_one)} bytes"
    )
    assert dek_one != dek_two, (
        "INV-1 leg 2: two vaults created with the SAME master password hold the "
        "SAME DEK -- so the DEK is a function of the credential, not random. "
        "This is § 8.1's rejected design, which leaves two key schedules in the "
        "field permanently.\n"
        "  expected: the two unwrapped DEKs differ\n"
        f"  actual:   both are {dek_one.hex()}"
    )


# --------------------------------------------------------------------------- #
# INV-2 — both slots unwrap to the same DEK, and either alone opens the vault
# --------------------------------------------------------------------------- #
def test_both_slots_yield_the_same_dek(
    paths: tuple[Path, Path], service: AuthService
) -> None:
    vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    data = read_v2_sidecar(sidecar_path)
    dek_master = bytes(unwrap_slot(MASTER_PASSWORD, data, SLOT_MASTER))
    dek_recovery = bytes(unwrap_slot(code_secret(code), data, SLOT_RECOVERY))

    assert dek_master == dek_recovery, (
        "INV-2: the two slots wrap DIFFERENT DEKs, so one of the two credentials "
        "opens a database the other cannot.\n"
        f"  expected: slots.master and slots.recovery unwrap to the same bytes\n"
        f"  actual:   master={dek_master.hex()} recovery={dek_recovery.hex()}"
    )

    assert opens_with(vault_path, sidecar_path, bytearray(dek_master)), (
        "INV-2: the password route must open the vault.\n"
        "  expected: Vault.open(DEK from slots.master) succeeds\n"
        "  actual:   SQLCipher refused the key"
    )
    assert opens_with(vault_path, sidecar_path, bytearray(dek_recovery)), (
        "INV-2: the recovery route must open the same vault.\n"
        "  expected: Vault.open(DEK from slots.recovery) succeeds\n"
        "  actual:   SQLCipher refused the key"
    )

    # Leg 3 -- the transcription property § 4.3 chose Crockford FOR. The user
    # re-types the code in lower case having read `1`, `1` and `0` as `I`, `l`
    # and `O`. Crockford decodes those back, so it is the SAME code -- and this
    # leg is what fails if the KDF is fed the normalised TEXT instead of the
    # decoded 17 big-endian bytes.
    normalised = normalise(code)
    payload, check = normalised[:-1], normalised[-1]
    mistyped = (payload.replace("1", "I").replace("0", "O") + check).lower()
    dek_mistyped = bytes(unwrap_slot(code_secret(mistyped), data, SLOT_RECOVERY))

    assert dek_mistyped == dek_recovery, (
        "INV-2 leg 3: a correctly-transcribed code was refused. Crockford "
        "decodes I/L to 1 and O to 0, so `AIB2...` and the printed `A1B2...` are "
        "the SAME code -- deriving from the normalised text gives them different "
        "keys and throws away the whole reason § 4.3 chose this alphabet.\n"
        f"  expected: the mistyped form unwraps to {dek_recovery.hex()}\n"
        f"  actual:   {dek_mistyped.hex()} (re-typed as {mistyped!r})"
    )

    # A randomly generated code may happen to carry no `1` and no `0`, which
    # would leave the substitution above doing nothing and the leg proving only
    # case-insensitivity -- green while the transcription property is broken.
    # These two synthetic pairs cannot degenerate: they assert the decode itself
    # maps I/l/O onto 1/1/0, which IS the property. `decode` excludes the check
    # symbol without verifying it (verify_check_symbol is the separate step,
    # § 4.3), so the trailing symbol here need not be a valid one.
    assert decode("I" * 13 + "l" * 14 + "0") == decode("1" * 27 + "0"), (
        "INV-2 leg 3: Crockford decodes I and L to 1 (§ 4.3).\n"
        "  expected: decode('III...lll0') == decode('111...1110')\n"
        f"  actual:   {decode('I' * 13 + 'l' * 14 + '0').hex()} != "
        f"{decode('1' * 27 + '0').hex()}"
    )
    assert decode("O" * 27 + "0") == decode("0" * 28), (
        "INV-2 leg 3: Crockford decodes O to 0 (§ 4.3).\n"
        "  expected: decode('OOO...O0') == decode('000...00')\n"
        f"  actual:   {decode('O' * 27 + '0').hex()} != {decode('0' * 28).hex()}"
    )


# --------------------------------------------------------------------------- #
# INV-3 — wrapping is authenticated: any modification fails closed
# --------------------------------------------------------------------------- #
def test_tampered_slot_fails_closed(
    paths: tuple[Path, Path], service: AuthService
) -> None:
    _vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    pristine = read_v2_sidecar(sidecar_path)

    # Leg 1 -- one bit of the wrapped DEK.
    tampered = read_v2_sidecar(sidecar_path)
    record = tampered["slots"][SLOT_MASTER]
    record["wrapped_dek_hex"] = _flip_first_hex_nibble(record["wrapped_dek_hex"])
    with pytest.raises(KeyUnwrapError):
        unwrap_slot(MASTER_PASSWORD, tampered, SLOT_MASTER)

    # Leg 2 -- one bit of the nonce.
    tampered = read_v2_sidecar(sidecar_path)
    record = tampered["slots"][SLOT_MASTER]
    record["nonce_hex"] = _flip_first_hex_nibble(record["nonce_hex"])
    with pytest.raises(KeyUnwrapError):
        unwrap_slot(MASTER_PASSWORD, tampered, SLOT_MASTER)

    # Leg 3 -- a WEAKENED cost parameter, and it raises KdfPolicyError, NOT
    # KeyUnwrapError. ARGON2_MEMORY_FLOOR_KIB equals the pinned
    # ARGON2_MEMORY_KIB, so validate_params refuses any lowering before
    # unwrap_dek is ever reached. A leg asserting KeyUnwrapError here could
    # never pass, and the plausible "fix" would be to loosen the floor -- which
    # is the guard itself.
    #
    # Routed through the SHIPPED loader, not through validate_params directly.
    # Calling validate_params on a hand-built KdfParams only re-proves that
    # crypto.py's floor rejects a halved memory_kib, which is already true today
    # and stays true if the v2 load path never consults it -- so the weakening
    # this leg exists to catch could arrive by that route and leave the leg
    # green. load_and_validate_params IS the path AuthService.load_params takes.
    tampered = read_v2_sidecar(sidecar_path)
    tampered["kdf"]["memory_kib"] = int(tampered["kdf"]["memory_kib"]) // 2
    weakened_path = sidecar_path.parent / "weakened.kdf.json"
    weakened_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(KdfPolicyError):
        load_and_validate_params(weakened_path)

    # Leg 4 -- the AAD, and the ONLY leg that tests it. The recovery slot is
    # renamed to `master` and unwrapped with KEK-**recovery**: correct key,
    # correct salt, correct ciphertext, leaving the slot NAME as the only thing
    # that differs. Unwrapping it with KEK-master instead would fail whether or
    # not the AAD names the slot -- the salt is the recovery one, so the key is
    # simply wrong -- and would pass against an implementation whose AAD is b"".
    renamed = read_v2_sidecar(sidecar_path)
    renamed["slots"][SLOT_MASTER] = renamed["slots"][SLOT_RECOVERY]
    del renamed["slots"][SLOT_RECOVERY]
    kek_recovery = kek_for(code_secret(code), pristine, SLOT_RECOVERY)
    with pytest.raises(KeyUnwrapError):
        unwrap_dek(
            bytes(kek_recovery),
            slot_record(renamed, SLOT_MASTER),
            SLOT_MASTER,
            slot_params(renamed, SLOT_MASTER),
        )


# --------------------------------------------------------------------------- #
# INV-3 — no un-wipeable KEK copy at a call site (FIBR-0310 P8)
# --------------------------------------------------------------------------- #


def _kek_arg(node: ast.Call) -> tuple[str, ast.expr] | None:
    """A ``wrap_dek`` / ``unwrap_dek`` call as ``(name, kek argument)``, or None."""
    if not isinstance(node.func, ast.Name) or node.func.id not in _WRAPPERS:
        return None
    for keyword in node.keywords:
        if keyword.arg == "kek":
            return node.func.id, keyword.value
    return (node.func.id, node.args[0]) if node.args else None


def _is_bytes_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "bytes"
    )


def test_no_call_site_copies_the_kek_into_bytes(service: AuthService) -> None:
    """``security-model.md`` INV-3 — **every** KEK is wiped after use.

    ``bytes(kek)`` at a call site defeats that: it makes an immutable copy in
    the CALLER's frame, which the ``finally: _wipe(kek)`` beside several of
    these sites cannot reach. The copy outlives the wipe and sits in the heap
    until the allocator reuses it. Eight production sites did this, because
    ``keywrap``'s ``kek: bytes`` annotation left them no other conforming
    option (FIBR-0310 P8).

    Three legs, and only the first two discriminate -- Python does not enforce
    an annotation, so a ``bytearray`` reaches ``AESGCM`` either way and a purely
    functional test passes against the defect.

    SCOPE: the ``kek`` argument only. ``bytes(dek)`` is FIBR-0004 D5's accepted
    best-effort gap, decided by the user 2026-08-21 and recorded in
    ``wrap_dek``'s docstring; this guard must not fire on it.
    """
    # Leg 1 -- the annotation admits a bytearray, so a caller CAN pass one.
    for func in (wrap_dek, unwrap_dek):
        hints = get_type_hints(func)
        assert bytearray in get_args(hints["kek"]), (
            f"{func.__name__}'s kek annotation is {hints['kek']!r}: a caller "
            "holding a bytearray has to copy it to conform"
        )

    # Leg 2 -- and no production call site makes that copy anyway.
    offences: list[str] = []
    seen = 0
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call = _kek_arg(node)
            if call is None:
                continue
            name, kek_arg = call
            seen += 1
            if _is_bytes_call(kek_arg):
                rel = path.relative_to(_SRC_ROOT.parents[1])
                offences.append(f"{rel}:{kek_arg.lineno} {name}(bytes(...), ...)")
    assert seen >= 8, f"the walk found only {seen} call sites -- it has gone blind"
    assert not offences, "un-wipeable KEK copies:\n  " + "\n  ".join(offences)

    # Leg 3 -- not a discriminator, but it is what makes legs 1 and 2 safe: the
    # pinned cryptography wheel really does take a bytearray key, so widening
    # the annotation is not a promise the runtime breaks.
    params = service.new_params()
    kek = bytearray(range(KEY_LEN))
    dek = bytearray(b"\x5a" * KEY_LEN)
    slot = wrap_dek(kek, bytes(dek), SLOT_MASTER, params)
    kek[:] = bytes(KEY_LEN)  # the wipe the annotation used to defeat
    assert unwrap_dek(bytearray(range(KEY_LEN)), slot, SLOT_MASTER, params) == dek
