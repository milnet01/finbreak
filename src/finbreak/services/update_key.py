"""The release-signing public key (FIBR-0054 INV-4/INV-14).

The updater verifies every downloaded AppImage against **this** Ed25519 public
key — the private half never enters the repo or Claude's context (it is generated
once by the user via ``scripts/gen-signing-key.py`` and kept off-tree). Until that
keygen runs, ``RELEASE_PUBLIC_KEY_B64`` holds a **valid** base64 of 32 zero bytes:
the module imports cleanly and ``public_key()`` loads, but no real signature
verifies against an all-zero key — so verification **fails closed** in the interim
(a Phase-2 test asserts exactly that).
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# PLACEHOLDER — 32 zero bytes. Phase 1's gen-signing-key.py prints the real
# 32-byte public key as the base64 to paste here (D1/Deliverable 3).
RELEASE_PUBLIC_KEY_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def public_key() -> Ed25519PublicKey:
    """The committed release public key as an ``Ed25519PublicKey`` (INV-4)."""
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(RELEASE_PUBLIC_KEY_B64))
