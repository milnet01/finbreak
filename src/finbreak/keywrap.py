"""Envelope key-wrapping — the DEK/KEK slot primitives (FIBR-0019 § 4.2).

Qt-free and dependency-light on purpose, so the envelope is testable headless.
``AESGCM`` from the already-pinned ``cryptography`` wheel is the wrapping
primitive; ``unwrap_dek`` raises ``KeyUnwrapError`` on ANY authentication
failure and never distinguishes "wrong credential" from "tampered slot" — a
distinguishing error is an oracle.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from finbreak.errors import KeyUnwrapError
from finbreak.models import KdfParams

# The two slot names the 1.0 envelope carries. FIBR-0020 (biometric unlock)
# would add a third; `slots` is deliberately an open map (§ 4.1).
SLOT_MASTER = "master"
SLOT_RECOVERY = "recovery"

# The additional-authenticated-data template (§ 4.2). The UTF-8 encoding of
#   finbreak-kdf-v2|<slot_name>|<memory_kib>|<time_cost>|<parallelism>|<key_len>
# binds the slot NAME into the ciphertext, so a `recovery` slot cannot be
# renamed to `master` without the unwrap failing closed. The cost parameters
# are bound by the derivation as well; naming them here is defence in depth.
AAD_PREFIX = "finbreak-kdf-v2"

# AES-GCM nonce, and the wrapped payload: 32 bytes of ciphertext + GCM's
# 16-byte tag (§ 4.4).
NONCE_LEN = 12
WRAPPED_DEK_LEN = 48


@dataclass(frozen=True)
class Slot:
    """One slot's ciphertext half — the nonce and the wrapped DEK.

    The slot's SALT is not carried here: it travels in the per-slot
    ``KdfParams`` (§ 4.4 — the cost parameters come from the sidecar's ``kdf``
    group, the salt from that slot's own record), which is what ``derive_key``
    consumes to produce the KEK.
    """

    nonce: bytes
    wrapped_dek: bytes


def slot_aad(slot: str, params: KdfParams) -> bytes:
    """The § 4.2 additional authenticated data for ``slot`` under ``params``."""
    return "|".join(
        (
            AAD_PREFIX,
            slot,
            str(params.memory_kib),
            str(params.time_cost),
            str(params.parallelism),
            str(params.key_len),
        )
    ).encode("utf-8")


def wrap_dek(kek: bytes | bytearray, dek: bytes, slot: str, params: KdfParams) -> Slot:
    """Wrap ``dek`` under ``kek`` into ``slot``, authenticated by ``slot_aad``.

    **The KEK is not copied here and callers must not copy it either.** It is
    annotated ``bytes | bytearray`` so a caller holding the wipeable buffer
    ``derive_key`` returns passes that buffer straight through; the old
    ``bytes`` annotation forced ``wrap_dek(bytes(kek), ...)`` at every site,
    and that copy landed in the *caller's* frame, out of reach of the
    ``finally`` that wipes the bytearray beside several of them. INV-3 names
    every KEK, so the copy was an INV-3 breach at eight sites (FIBR-0310 P8).
    ``AESGCM`` takes the buffer and copies the key into its own context —
    measured on the pinned ``cryptography`` 50.0.0: an ``AESGCM`` built from a
    bytearray still decrypts after that bytearray is zeroed. That residual copy
    is OpenSSL's and is not reachable from Python.

    **The DEK half is different and is left as it is.** ``dek`` stays ``bytes``,
    so every caller converts before the call and the ``bytes(dek)`` written
    below is a no-op: measured 2026-08-25, ``bytes(b) is b`` for a ``bytes``
    argument, so the copy was already made in the caller's frame (FIBR-0310 R6).

    :func:`unwrap_dek` has the mirror of it — AESGCM returns immutable
    ``bytes``, which is copied into the wipeable buffer it hands back, leaving
    the original in the heap. All of them survive lock and auto-lock.

    **That DEK copy is FIBR-0004 D5's accepted best-effort gap, and it is
    recorded here rather than fixed** (decided by the user 2026-08-21,
    FIBR-0307). D5's wording describes this exact shape: a primitive returns
    immutable ``bytes``, the value is copied into a ``bytearray`` and the
    original reference dropped. ``crypto.derive_key`` carries the identical
    note on ``bytes(password)``.

    Two things make it worth having decided rather than inherited, so the next
    reviewer does not re-raise it. The gap D5 accepted is the PASSWORD, and
    these are the database key and the keys that wrap it. And an in-place API
    does exist here — ``Cipher`` with ``GCM`` and ``update_into`` over a
    caller-owned buffer — so unlike ``hash_secret_raw``'s ``secret=`` argument
    it is not API-forced. It was weighed on those two points and accepted: swap
    is out of scope (``security-model.md`` § 4), so the residual is a heap copy
    on a machine an attacker already has, which is the same exposure D5 accepts
    for the password that derives the KEK.
    """
    nonce = secrets.token_bytes(NONCE_LEN)
    return Slot(
        nonce=nonce,
        wrapped_dek=AESGCM(kek).encrypt(nonce, bytes(dek), slot_aad(slot, params)),
    )


def unwrap_dek(
    kek: bytes | bytearray, slot_data: Slot, slot: str, params: KdfParams
) -> bytearray:
    """Unwrap ``slot_data`` with ``kek``, or ``KeyUnwrapError``.

    Returns a wipeable ``bytearray`` (``security-model.md`` INV-3 — an
    immutable ``bytes`` cannot be zeroed, and this value is SQLCipher's raw key).

    Every failure — a wrong credential, a flipped ciphertext or nonce bit, a
    renamed slot, a malformed key length — raises the SAME error with the same
    message. The caller cannot act differently on the causes, and an error that
    told them apart would be an oracle (§ 4.2).
    """
    try:
        return bytearray(
            AESGCM(kek).decrypt(
                slot_data.nonce, slot_data.wrapped_dek, slot_aad(slot, params)
            )
        )
    except (InvalidTag, ValueError) as exc:
        raise KeyUnwrapError(f"could not unwrap the {slot!r} slot") from exc
