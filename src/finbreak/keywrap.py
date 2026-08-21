"""Envelope key-wrapping — the DEK/KEK slot primitives (FIBR-0019 § 4.2).

**STUB — FIBR-0019 is not implemented.** Every function here raises
``NotImplementedError`` so ``tests/features/recovery_key/`` can be *seen to
fail* against a real call rather than dying at import (``testing.md`` § 1 /
FIBR-0019 § 7). The constants below carry their real, spec-fixed values; the
behaviour does not exist yet.

Qt-free and dependency-light on purpose (§ 4.2), so the envelope is testable
headless. ``AESGCM`` from the already-pinned ``cryptography`` wheel is the
wrapping primitive; ``unwrap_dek`` must raise ``KeyUnwrapError`` on ANY
authentication failure and must never distinguish "wrong credential" from
"tampered slot" — a distinguishing error is an oracle.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    raise NotImplementedError("FIBR-0019")


def wrap_dek(kek: bytes, dek: bytes, slot: str, params: KdfParams) -> Slot:
    """Wrap ``dek`` under ``kek`` into ``slot``, authenticated by ``slot_aad``."""
    raise NotImplementedError("FIBR-0019")


def unwrap_dek(kek: bytes, slot_data: Slot, slot: str, params: KdfParams) -> bytearray:
    """Unwrap ``slot_data`` with ``kek``, or ``KeyUnwrapError``.

    Returns a wipeable ``bytearray`` (``security-model.md`` INV-3 — an
    immutable ``bytes`` cannot be zeroed, and this value is SQLCipher's raw key).
    """
    raise NotImplementedError("FIBR-0019")
