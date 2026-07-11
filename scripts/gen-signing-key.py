#!/usr/bin/env python3
"""FIBR-0054 Phase 1 — one-time release-signing keypair generator (Deliverable 2).

Run this **once**, by hand, to create the Ed25519 keypair that signs finbreak
releases:

    python scripts/gen-signing-key.py

It writes the **private** key (unencrypted PKCS#8 PEM) to a git-ignored path
(``release/finbreak-signing.key``, mode 0600) and prints the **public** key as
the base64 constant to paste into ``src/finbreak/services/update_key.py``. The
private key never enters the repo or Claude's context — guard it like a password;
losing it means you can no longer sign updates that the shipped app will accept.

The public key is 32 raw bytes, base64-encoded — exactly what
``services/update_key.py`` feeds to ``Ed25519PublicKey.from_public_bytes`` (INV-4),
and the signature ``scripts/sign-release.py`` writes is the raw 64-byte Ed25519
signature ``services/update.py`` verifies (INV-14).
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_DEFAULT_KEY_PATH = Path("release/finbreak-signing.key")


def generate_keypair(dest: Path) -> str:
    """Generate an Ed25519 keypair, write the private key (PKCS#8 PEM, mode 0600)
    to *dest*, and return the public key as base64 of its raw 32 bytes.

    Refuses to overwrite an existing key file — regenerating would invalidate
    every already-published signature.
    """
    if dest.exists():
        raise FileExistsError(
            f"{dest} already exists — refusing to overwrite an existing signing key"
        )

    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Create 0600 up front (never a readable window), then write.
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)

    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public_raw).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_KEY_PATH,
        help=f"private-key output path (default: {_DEFAULT_KEY_PATH})",
    )
    args = parser.parse_args(argv)

    try:
        public_b64 = generate_keypair(args.out)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Private key written to: {args.out}  (mode 0600, git-ignored)")
    print("  → Keep this file SAFE and SECRET. It is your release identity.")
    print("  → It is never committed; losing it means you cannot sign updates.\n")
    print("Paste this public key into src/finbreak/services/update_key.py:\n")
    print(f'    RELEASE_PUBLIC_KEY_B64 = "{public_b64}"\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
