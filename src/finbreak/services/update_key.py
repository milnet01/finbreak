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

# The real release-signing public key (32 bytes, base64), generated
# 2026-07-11 by scripts/gen-signing-key.py. The matching private key lives only
# on the maintainer's machine (git-ignored release/finbreak-signing.key); the
# updater installs a download only if its .sig verifies against this key (INV-4).
RELEASE_PUBLIC_KEY_B64 = "h+YTi4bgziBOwwSSt4fcJLghYQ/zfp44WS2jbG/CQBw="


def public_key() -> Ed25519PublicKey:
    """The committed release public key as an ``Ed25519PublicKey`` (INV-4)."""
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(RELEASE_PUBLIC_KEY_B64))
