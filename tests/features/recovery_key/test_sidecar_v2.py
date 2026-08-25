"""FIBR-0019 INV-4/INV-12 — the version-2 sidecar. Enforces spec.md.

Headless. Why this exists: the sidecar stops being a flat seven-field object and
starts holding a WRAPPED DEK -- which falsifies FIBR-0004 INV-7's "only the salt
+ non-secret KDF parameters + format version". The honest replacement claim is
*no UNWRAPPED key material*, and INV-4 is what holds the app to it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    KDF_FIELDS,
    MASTER_PASSWORD,
    SIDECAR_TOP_LEVEL,
    SLOT_FIELDS,
    code_secret,
    create_vault,
    keep_recovery_key,
    kek_for,
    read_v2_sidecar,
    unwrap_slot,
)

from finbreak.errors import KdfPolicyError
from finbreak.keywrap import NONCE_LEN, SLOT_MASTER, SLOT_RECOVERY, WRAPPED_DEK_LEN
from finbreak.models import SIDECAR_VERSION
from finbreak.services.auth import AuthService
from finbreak.services.recovery_code import normalise

pytestmark = pytest.mark.features

# The sidecar's slot map, named once rather than spelled at every subscript.
SLOTS = "slots"


@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def _every_string(node: Any) -> Iterator[str]:
    """Every string anywhere in the parsed sidecar -- keys and values alike."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _every_string(value)
    elif isinstance(node, list):
        for item in node:
            yield from _every_string(item)


# --------------------------------------------------------------------------- #
# INV-4 — the sidecar holds no unwrapped key material, password or code
# --------------------------------------------------------------------------- #
def test_sidecar_holds_no_unwrapped_secret(
    paths: tuple[Path, Path], service: AuthService
) -> None:
    _vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    data = read_v2_sidecar(sidecar_path)

    # The shape, EXACTLY -- for a vault created FRESH. A mid-migration sidecar
    # legally also carries `migration_pending` (written at S3, removed at S6) and
    # any MIGRATED vault carries `cipher_compatibility` permanently (written at
    # S3 and kept). Neither belongs on a freshly created vault, which is why this
    # leg pins the fresh shape rather than asserting a set that would go red on
    # every vault in the field.
    assert set(data) == SIDECAR_TOP_LEVEL, (
        "INV-4: a freshly created v2 sidecar carries exactly three top-level "
        "keys. `migration_pending` / `cipher_compatibility` are migration-only "
        "(§ 4.4) and must not appear on a new vault.\n"
        f"  expected: {sorted(SIDECAR_TOP_LEVEL)}\n"
        f"  actual:   {sorted(data)}"
    )
    assert data["sidecar_version"] == SIDECAR_VERSION, (
        f"INV-4: expected sidecar_version == {SIDECAR_VERSION}\n"
        f"  actual:   {data['sidecar_version']!r}"
    )
    assert set(data["kdf"]) == KDF_FIELDS, (
        "INV-4: the `kdf` group holds the Argon2id cost parameters shared by "
        "every slot -- and nothing else.\n"
        f"  expected: {sorted(KDF_FIELDS)}\n  actual:   {sorted(data['kdf'])}"
    )
    assert set(data["slots"]) <= {SLOT_MASTER, SLOT_RECOVERY}, (
        "INV-4: the 1.0 envelope has two slot names.\n"
        f"  expected: a subset of {sorted({SLOT_MASTER, SLOT_RECOVERY})}\n"
        f"  actual:   {sorted(data['slots'])}"
    )
    for name, record in data["slots"].items():
        assert set(record) == SLOT_FIELDS, (
            f"INV-4: slot {name!r} carries its own salt, nonce and wrapped DEK "
            "-- and nothing else.\n"
            f"  expected: {sorted(SLOT_FIELDS)}\n  actual:   {sorted(record)}"
        )

    # No unwrapped secret anywhere in it, in ANY of the forms it could take.
    # `wrapped_dek_hex` is ciphertext and is meant to be there; what must not
    # appear is the DEK itself, either KEK, the password or the code.
    dek = bytes(unwrap_slot(MASTER_PASSWORD, data, SLOT_MASTER))
    kek_master = bytes(kek_for(MASTER_PASSWORD, data, SLOT_MASTER))
    kek_recovery = bytes(kek_for(code_secret(code), data, SLOT_RECOVERY))
    payload = code_secret(code)

    forbidden = {
        "the DEK (hex)": dek.hex(),
        "KEK-master (hex)": kek_master.hex(),
        "KEK-recovery (hex)": kek_recovery.hex(),
        "the master password": MASTER_PASSWORD.decode(),
        "the master password (hex)": MASTER_PASSWORD.hex(),
        "the recovery code (display form)": code,
        "the recovery code (normalised base32)": normalise(code),
        "the decoded recovery payload (hex)": payload.hex(),
    }
    haystack = sidecar_path.read_text()
    strings = list(_every_string(data))

    for label, needle in forbidden.items():
        assert needle.lower() not in haystack.lower(), (
            f"INV-4: {label} appears in vault.kdf.json. The sidecar is "
            "plaintext (§ 4.4), so anything in it is readable by anyone holding "
            "the file.\n"
            f"  expected: {label} absent from the sidecar\n"
            f"  actual:   found {needle[:16]}... in the file bytes"
        )
        offenders = [s for s in strings if needle.lower() in s.lower()]
        assert not offenders, (
            f"INV-4: {label} appears inside a sidecar value.\n"
            f"  expected: no value contains it\n  actual:   {offenders}"
        )

    # The raw-bytes forms too -- a secret written as bytes rather than hex.
    raw_haystack = sidecar_path.read_bytes()
    for label, needle_bytes in (
        ("the DEK (raw bytes)", dek),
        ("the master password (raw bytes)", MASTER_PASSWORD),
        ("the decoded recovery payload (raw bytes)", payload),
    ):
        assert needle_bytes not in raw_haystack, (
            f"INV-4: {label} appears in the sidecar's bytes.\n"
            f"  expected: absent\n  actual:   present"
        )


# --------------------------------------------------------------------------- #
# INV-12 — declining a recovery key still builds the envelope
# --------------------------------------------------------------------------- #
def test_declining_still_writes_the_envelope(
    paths: tuple[Path, Path], service: AuthService
) -> None:
    _vault_path, sidecar_path = paths

    # Decline is simply never reaching § 4.5 step 9: the code is generated and
    # wrapped either way, but `slots.recovery` never touches disk.
    code = create_vault(service)

    data = read_v2_sidecar(sidecar_path)
    assert data["sidecar_version"] == SIDECAR_VERSION, (
        "INV-12: declining must NOT short-circuit to the v1 format -- that is "
        "the cheap-looking implementation and the one that reintroduces the two "
        "key schedules D2 exists to prevent.\n"
        f"  expected: sidecar_version == {SIDECAR_VERSION}\n"
        f"  actual:   {data['sidecar_version']!r}"
    )
    assert SLOT_MASTER in data["slots"], (
        "INV-12: the envelope is built whether or not a recovery key is kept.\n"
        f"  expected: slots.{SLOT_MASTER} present\n"
        f"  actual:   slots={sorted(data['slots'])}"
    )
    assert SLOT_RECOVERY not in data["slots"], (
        "INV-12: a DECLINED code's slot must never reach disk -- § 4.5 defers "
        "the recovery-slot write to step 9 precisely so Decline writes nothing "
        "rather than writing then deleting.\n"
        f"  expected: slots.{SLOT_RECOVERY} absent\n"
        f"  actual:   slots={sorted(data['slots'])}"
    )

    dek_before = bytes(unwrap_slot(MASTER_PASSWORD, data, SLOT_MASTER))

    # Adding one later is a re-wrap of 32 bytes, never a re-encrypt (D3) -- the
    # property that makes D3 cheap and D2 possible.
    keep_recovery_key(service, code)

    after = read_v2_sidecar(sidecar_path)
    assert SLOT_RECOVERY in after["slots"], (
        "INV-12: adding a recovery key afterwards must write slots.recovery.\n"
        f"  expected: slots.{SLOT_RECOVERY} present\n"
        f"  actual:   slots={sorted(after['slots'])}"
    )
    dek_after = bytes(unwrap_slot(MASTER_PASSWORD, after, SLOT_MASTER))

    # The witness is the unwrapped DEK, NOT a hash or mtime of vault.db: vaults
    # run journal_mode = WAL, so pages sit in vault.db-wal until a checkpoint and
    # the main file's bytes move on open and close with no logical write at all.
    # A file hash would be flaky in one direction and vacuous in the other.
    assert dek_before == dek_after, (
        "INV-12: adding a recovery key changed the DEK, so the database was "
        "re-encrypted rather than the key re-wrapped.\n"
        f"  expected: the DEK is byte-identical across the add\n"
        f"  actual:   before={dek_before.hex()} after={dek_after.hex()}"
    )


# --------------------------------------------------------------------------- #
# FP02 finding 9 — a slot's field LENGTHS are part of the format
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("field", "value", "what"),
    [
        ("nonce_hex", "aabb", "a 2-byte nonce"),
        ("nonce_hex", "00" * 64, "a 64-byte nonce"),
        ("wrapped_dek_hex", "00" * 8, "an 8-byte wrapped DEK"),
        ("wrapped_dek_hex", "00" * 200, "a 200-byte wrapped DEK"),
    ],
    ids=["short-nonce", "long-nonce", "short-wrapped-dek", "long-wrapped-dek"],
)
def test_a_slot_of_the_wrong_length_is_not_a_wrong_password(
    paths: tuple[Path, Path],
    service: AuthService,
    field: str,
    value: str,
    what: str,
) -> None:
    """§ 4.4 fixes both lengths, and the loader has to be the one enforcing it.

    The nonce is 24 hex chars and ``wrapped_dek_hex`` is 48 bytes -- 32 of
    ciphertext plus GCM's 16-byte tag. Neither was checked, so a damaged key
    record reached ``unwrap_dek``, which fails closed as a ``KeyUnwrapError``
    and is reported as a failed attempt: the user is told to check a password
    that is correct, and the § 6 throttle is charged for it. That is finding
    2's confusion arriving by a second route (FIBR-0307 finding 9).

    A length is not an oracle. It sits in the plaintext sidecar and is
    readable without any credential, and this gate runs BEFORE a password is
    derived -- which is why ``unwrap_dek`` keeps one undifferentiated error for
    everything it sees, and this refusal is a format check rather than a
    distinction between two credentials.
    """
    vault_path, sidecar_path = paths
    create_vault(service)
    service.lock()

    pristine = read_v2_sidecar(sidecar_path)[SLOTS][SLOT_MASTER]
    assert len(bytes.fromhex(pristine["nonce_hex"])) == NONCE_LEN, (
        "precondition: a freshly written slot must carry the length § 4.4 "
        "states, or the values this leg calls malformed are not.\n"
        f"  expected: {NONCE_LEN}\n"
        f"  actual:   {len(bytes.fromhex(pristine['nonce_hex']))}"
    )
    assert len(bytes.fromhex(pristine["wrapped_dek_hex"])) == WRAPPED_DEK_LEN, (
        "precondition: § 4.4 fixes the wrapped DEK at 32 bytes of ciphertext "
        "plus GCM's 16-byte tag.\n"
        f"  expected: {WRAPPED_DEK_LEN}\n"
        f"  actual:   {len(bytes.fromhex(pristine['wrapped_dek_hex']))}"
    )

    damaged = read_v2_sidecar(sidecar_path)
    damaged[SLOTS][SLOT_MASTER][field] = value
    sidecar_path.write_text(json.dumps(damaged), encoding="utf-8")

    try:
        outcome: object = AuthService(vault_path, sidecar_path).unlock(
            bytearray(MASTER_PASSWORD)
        )
    except KdfPolicyError:
        return
    pytest.fail(
        f"the shipped loader accepted {what}, so the damaged key record was "
        "handed to unwrap_dek and came back as an ordinary failed unlock -- "
        "indistinguishable from a wrong password, and charging the throttle "
        "for a vault whose password was right.\n"
        "  expected: KdfPolicyError, which ui/unlock.py renders as the "
        "security-settings file being damaged\n"
        f"  actual:   unlock() returned {outcome!r}"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("wrapped_dek_hex", "00" * 8),
        ("nonce_hex", "00" * 4),
        ("salt_hex", "00" * 4),
    ],
    ids=["wrapped_dek", "nonce", "salt"],
)
def test_a_damaged_recovery_slot_does_not_bar_the_master_route(
    paths: tuple[Path, Path], service: AuthService, field: str, value: str
) -> None:
    """Damage in an OPTIONAL slot must not lock the user out of a working one.

    The gate is per slot, and so is the LOCKOUT it can cause. `master` is the
    one slot every vault has and every other route leans on, so a malformed one
    still refuses the whole record. `recovery` is a credential the user may
    never have used, and refusing the sidecar over it locks them out of their
    own correct password -- to protect them from a route they were not taking
    (FIBR-0310 R5).

    This leg previously asserted the opposite, on the grounds that refusing
    outright was "the existing behaviour rather than a new strictness" because
    `validate_params` already rejected a damaged recovery SALT. That was true
    of the salt and made the widening to the nonce and wrapped DEK look free.
    It was not: it added two more ways for an untouched credential to bar a
    working one. The salt leg here is the pre-existing case, fixed with them.
    """
    vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    damaged = read_v2_sidecar(sidecar_path)
    damaged[SLOTS][SLOT_RECOVERY][field] = value
    sidecar_path.write_text(json.dumps(damaged), encoding="utf-8")

    opened = AuthService(vault_path, sidecar_path)
    assert opened.unlock(bytearray(MASTER_PASSWORD)) is True, (
        f"a damaged recovery {field} barred the master password route. The "
        "password is right, the master slot is intact, and the vault opens -- "
        "the user is locked out by the corruption of a credential they may "
        "never have used.\n"
        "  expected: unlock() is True\n"
        "  actual:   it refused"
    )
    opened.lock()


def test_the_damaged_recovery_slot_survives_a_master_unlock(
    paths: tuple[Path, Path], service: AuthService
) -> None:
    """The malformed record is KEPT on disk, not pruned as it is read.

    ``AuthService`` reads the sidecar, edits it and writes it back, so a loader
    that dropped the bad slot would delete it the next time anything touched
    the file -- turning a file a user might still recover by hand into one
    nobody can. Unlocking is such a touch: § 13.3's resume and the auto-lock
    both rewrite the sidecar off a loaded object (FIBR-0310 R5).
    """
    vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    damaged = read_v2_sidecar(sidecar_path)
    damaged[SLOTS][SLOT_RECOVERY]["nonce_hex"] = "00" * 4
    sidecar_path.write_text(json.dumps(damaged), encoding="utf-8")

    opened = AuthService(vault_path, sidecar_path)
    assert opened.unlock(bytearray(MASTER_PASSWORD)) is True, (
        "precondition: the master route must open, or this leg is asserting "
        "about a file nothing wrote to."
    )
    opened.lock()

    after = read_v2_sidecar(sidecar_path)
    assert SLOT_RECOVERY in after[SLOTS], (
        "the damaged recovery slot was dropped from the sidecar. Pruning it "
        "makes the damage permanent on the first unlock after it happens, and "
        "the user is never told.\n"
        "  expected: the slot still on disk\n"
        f"  actual:   slots = {sorted(after[SLOTS])}"
    )
    assert after[SLOTS][SLOT_RECOVERY]["nonce_hex"] == "00" * 4, (
        "the damaged recovery slot was rewritten. Whatever replaced it, the "
        "bytes the user had are gone.\n"
        "  expected: the damaged record, byte for byte\n"
        f"  actual:   {after[SLOTS][SLOT_RECOVERY]['nonce_hex']!r}"
    )


def test_the_recovery_route_still_refuses_its_own_damaged_slot(
    paths: tuple[Path, Path], service: AuthService
) -> None:
    """Loosening the LOADER must not lose FIBR-0307 finding 9 for this route.

    A user unlocking WITH the recovery code, against a damaged recovery slot,
    still needs the distinct answer: the record is damaged. Handing it to
    ``unwrap_dek`` gives the one undifferentiated failure, which the unlock
    path reports as a wrong code and charges the § 6 throttle for -- telling
    the user their correct code is wrong. The route that uses a slot is what
    validates it now (FIBR-0310 R5).
    """
    vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    intact = read_v2_sidecar(sidecar_path)
    kek = kek_for(code_secret(code), intact, SLOT_RECOVERY)

    damaged = read_v2_sidecar(sidecar_path)
    damaged[SLOTS][SLOT_RECOVERY]["nonce_hex"] = "00" * 4
    sidecar_path.write_text(json.dumps(damaged), encoding="utf-8")

    with pytest.raises(KdfPolicyError):
        AuthService(vault_path, sidecar_path).complete_recovery_unlock(bytes(kek))
