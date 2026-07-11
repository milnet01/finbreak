#!/usr/bin/env python3
"""FIBR-0054 Phase 1 — sign a release artifact with the private key (Deliverable 4).

    python scripts/sign-release.py dist/finbreak-0.1.0-x86_64.AppImage
    # or point at a non-default key:
    python scripts/sign-release.py --key path/to/finbreak-signing.key <artifact>
    # or via env:
    FINBREAK_SIGNING_KEY=path/to/key python scripts/sign-release.py <artifact>

Writes ``<artifact>.sig`` — the **raw 64-byte Ed25519 signature** over the exact
artifact bytes (our own minimal convention, D1). This is precisely what
``services/update.py``'s ``download_and_verify`` checks against the committed
public key (INV-4/INV-14), so a signed release round-trips through the app's gate;
a tampered artifact does not.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_DEFAULT_KEY_PATH = Path("release/finbreak-signing.key")


def sign_artifact(key_path: Path, artifact: Path) -> Path:
    """Sign *artifact* with the Ed25519 private key at *key_path*; write the raw
    64-byte signature to ``<artifact>.sig`` and return that path."""
    private_key = serialization.load_pem_private_key(
        key_path.read_bytes(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError(
            f"{key_path} is not an Ed25519 private key "
            f"(got {type(private_key).__name__})"
        )

    signature = private_key.sign(artifact.read_bytes())  # raw 64-byte Ed25519 sig
    sig_path = artifact.with_name(artifact.name + ".sig")
    sig_path.write_bytes(signature)
    return sig_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="the file to sign")
    parser.add_argument(
        "--key",
        type=Path,
        default=None,
        help=(
            "private-key path (default: $FINBREAK_SIGNING_KEY, "
            f"else {_DEFAULT_KEY_PATH})"
        ),
    )
    args = parser.parse_args(argv)

    key_path = args.key
    if key_path is None:
        env = os.environ.get("FINBREAK_SIGNING_KEY")
        key_path = Path(env) if env else _DEFAULT_KEY_PATH

    if not key_path.is_file():
        print(f"error: signing key not found: {key_path}", file=sys.stderr)
        return 1
    if not args.artifact.is_file():
        print(f"error: artifact not found: {args.artifact}", file=sys.stderr)
        return 1

    sig_path = sign_artifact(key_path, args.artifact)
    print(f"Wrote {sig_path} ({sig_path.stat().st_size} bytes, raw Ed25519 sig)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
