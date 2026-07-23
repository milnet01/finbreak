"""CryptoService — the one auditable crypto path (design.md "Components").

Argon2id key derivation with pinned parameters, plus the on-open validation
that refuses a downgraded or malformed KDF record (FIBR-0004 INV-2). Parameters
are frozen from security-model.md INV-2 (a dated OWASP snapshot); do not tune.
"""

from __future__ import annotations

import json
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw

from finbreak.errors import KdfPolicyError
from finbreak.models import FORMAT_VERSION, KdfParams

# Pinned Argon2id parameters (security-model.md INV-2). memory_cost is in KiB —
# 47104 KiB is the "46 MiB" human gloss; the API argument is 47104, not 46.
ARGON2_MEMORY_KIB = 47104
# The on-open acceptance floor, kept DISTINCT from the creation pin above so the
# pin can be raised (following an updated OWASP snapshot) to strengthen NEW
# vaults WITHOUT locking every EXISTING vault out — an existing vault records the
# older, now-below-pin memory_kib, and validate_params must still open it. Hold
# this at the minimum ever shipped; only raise it behind a re-derive migration.
# Equal to the pin today, so nothing changes until the pin is bumped.
ARGON2_MEMORY_FLOOR_KIB = 47104
ARGON2_TIME_COST = 1
ARGON2_PARALLELISM = 1
KEY_LEN = 32
SALT_LEN = 16

# The seven flat fields a valid sidecar must carry (models.KdfParams, with
# salt → salt_hex). A sidecar missing any of them is malformed (INV-2c).
_REQUIRED_SIDECAR_FIELDS = frozenset(
    {
        "format_version",
        "memory_kib",
        "time_cost",
        "parallelism",
        "key_len",
        "salt_len",
        "salt_hex",
    }
)


def derive_key(password: bytearray, salt: bytes, params: KdfParams) -> bytearray:
    """Derive the vault's 32-byte raw key with Argon2id.

    Always passed by keyword: the low-level signature puts ``time_cost`` before
    ``memory_cost``, so positional args would silently transpose them. The
    immutable ``bytes`` result is copied into a wipeable ``bytearray``.

    ``bytes(password)`` makes an immutable copy the C binding requires; it can't
    be wiped and lingers until GC — an accepted best-effort gap (D5), the same
    one flagged on the raw-key hex ``str`` in ``vault._connect``.
    """
    raw = hash_secret_raw(
        secret=bytes(password),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_kib,
        parallelism=params.parallelism,
        hash_len=params.key_len,
        type=Type.ID,
    )
    return bytearray(raw)


def validate_params(params: KdfParams) -> None:
    """Enforce the strength floor and exact on-disk format, else ``KdfPolicyError``.

    The floor (memory) is directional — below is refused, at-or-above passes —
    checked against ``ARGON2_MEMORY_FLOOR_KIB``, which is deliberately SEPARATE
    from the creation pin (``ARGON2_MEMORY_KIB``) so the pin can be raised later
    to strengthen new vaults without locking out existing ones (their recorded
    ``memory_kib`` stays at-or-above the unchanged floor).
    The salt exists on disk, so both its real length and the recorded
    ``salt_len`` must equal ``SALT_LEN``; the key is never on disk, so only its
    recorded ``key_len`` is checked against the constant.

    An unknown ``format_version`` is refused up front: a future/foreign layout
    must not be silently reinterpreted against this version's field meanings.
    """
    if params.format_version != FORMAT_VERSION:
        raise KdfPolicyError(
            f"unsupported sidecar format_version {params.format_version} "
            f"(expected {FORMAT_VERSION})"
        )
    if params.key_len != KEY_LEN:
        raise KdfPolicyError(f"key_len must be {KEY_LEN}, got {params.key_len}")
    if len(params.salt) != SALT_LEN or params.salt_len != len(params.salt):
        raise KdfPolicyError(
            f"salt must be {SALT_LEN} bytes with a matching salt_len; "
            f"got len={len(params.salt)} salt_len={params.salt_len}"
        )
    if params.memory_kib < ARGON2_MEMORY_FLOOR_KIB:
        raise KdfPolicyError(
            f"memory_kib {params.memory_kib} is below the floor "
            f"{ARGON2_MEMORY_FLOOR_KIB}"
        )


def load_and_validate_params(sidecar_path: Path) -> KdfParams:
    """Read the plaintext sidecar into a validated ``KdfParams``.

    Every malformed-input path (unreadable, non-JSON, wrong shape, missing
    field, bad hex) is normalised to ``KdfPolicyError`` so callers assert one
    failure type, never a bare ``JSONDecodeError`` / ``KeyError`` (INV-2c).
    """
    try:
        data = json.loads(sidecar_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise KdfPolicyError(f"sidecar unreadable or not JSON: {exc}") from exc

    if not isinstance(data, dict) or not _REQUIRED_SIDECAR_FIELDS <= data.keys():
        raise KdfPolicyError("sidecar is missing one or more required KDF fields")

    try:
        params = KdfParams(
            format_version=int(data["format_version"]),
            memory_kib=int(data["memory_kib"]),
            time_cost=int(data["time_cost"]),
            parallelism=int(data["parallelism"]),
            key_len=int(data["key_len"]),
            salt_len=int(data["salt_len"]),
            salt=bytes.fromhex(data["salt_hex"]),
        )
    except (TypeError, ValueError) as exc:
        raise KdfPolicyError(f"sidecar field has a bad value: {exc}") from exc

    validate_params(params)
    return params
