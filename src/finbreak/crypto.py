"""CryptoService — the one auditable crypto path (design.md "Components").

Argon2id key derivation with pinned parameters, plus the on-open validation
that refuses a downgraded or malformed KDF record (FIBR-0004 INV-2). Parameters
are frozen from security-model.md INV-2 (a dated OWASP snapshot); do not tune.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from argon2.low_level import Type, hash_secret_raw

from finbreak.errors import KdfPolicyError
from finbreak.keywrap import (
    NONCE_LEN,
    SLOT_MASTER,
    WRAPPED_DEK_LEN,
    Slot,
)
from finbreak.models import FORMAT_VERSION, SIDECAR_VERSION, KdfParams

log = logging.getLogger(__name__)

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


# The malformed-sidecar failures that are NOT OSError or JSONDecodeError, and
# were escaping the normalisation both readers below promise (FIBR-0310 P2).
# Measured 2026-08-25 against a real file each: non-UTF-8 bytes raise
# UnicodeDecodeError out of `read_text` — BEFORE json sees them, so being a
# ValueError subclass does not help — and 200k nested brackets raise
# RecursionError out of `json.loads`, which is not a ValueError at all.
# MemoryError joins them for the same reason backup.py already catches it: a
# huge file on a small machine is a refused sidecar, not an unhandled
# exception out of a Qt slot (FIBR-0212).
#
# It matters beyond a tidy error type: this path is reachable from an IMPORTED
# .fbk, so the bytes are not necessarily the user's own.
_MALFORMED_SIDECAR = (
    OSError,
    json.JSONDecodeError,
    UnicodeDecodeError,
    RecursionError,
    MemoryError,
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

    Every malformed-input path — unreadable, non-UTF-8, non-JSON, nested past
    the recursion limit, too large for this machine, wrong shape, missing
    field, bad hex — is normalised to ``KdfPolicyError`` so callers assert one
    failure type, never a bare ``JSONDecodeError`` / ``KeyError`` (INV-2c). The
    set is ``_MALFORMED_SIDECAR``; three of those were escaping it until
    FIBR-0310 P2, and this file is reachable from an imported ``.fbk``.

    Dispatches on the sidecar's shape (FIBR-0019 § 4.4). A **v2** file yields
    the ``master`` slot's params — the KDF record the password route derives
    under, which is what every existing caller means by "this vault's params".
    A **v1** file takes the flat path below, unchanged: it is the on-disk shape
    of every vault in the field and § 13's only migration source.
    """
    if sidecar_version(sidecar_path) == SIDECAR_VERSION:
        return read_sidecar_v2(sidecar_path).params_for(SLOT_MASTER)

    try:
        data = json.loads(sidecar_path.read_text())
    except _MALFORMED_SIDECAR as exc:
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


# --------------------------------------------------------------------------- #
# The version-2 slots sidecar (FIBR-0019 § 4.4)
# --------------------------------------------------------------------------- #
# The `kdf` group's fields — the Argon2id cost parameters SHARED by every slot,
# so neither route is cheaper to attack than the other — and the per-slot
# record's, each slot carrying its own salt and its own wrapped copy of the DEK.
_V2_KDF_FIELDS = frozenset(
    {"memory_kib", "time_cost", "parallelism", "key_len", "salt_len"}
)
_V2_SLOT_FIELDS = frozenset({"salt_hex", "nonce_hex", "wrapped_dek_hex"})

# The two optional top-level fields, and they have different lifetimes:
# `migration_pending` is written at § 13.2's S3 and removed at S6, while
# `cipher_compatibility` is written at S3 and STAYS. It is carried by every
# vault whose database was written at an EXPLICIT cipher level — a migrated one
# (§ 13.2) and a restored one, whose database comes from `export_to` — and never
# by one created fresh, which takes the library default. Neither may be rejected as
# a foreign key: a loader that refused an unrecognised v2 field would refuse the
# resume sidecar on the next open and take § 13.3's resume down with it.
MIGRATION_PENDING_FIELD = "migration_pending"
CIPHER_COMPATIBILITY_FIELD = "cipher_compatibility"

# The top-level keys this version RECOGNISES — never the ones it allows. An
# unrecognised key, at this level or inside `kdf` or a slot, is carried back out
# verbatim on the next write. Tolerating one on read was never enough on its
# own: every writer is read-modify-write, so a field this build does not know
# about was being deleted the first time an older build touched the sidecar
# (FIBR-0313 M9). § 4.1 expects the format to grow.
_V2_TOP_FIELDS = frozenset(
    {
        "sidecar_version",
        "kdf",
        "slots",
        MIGRATION_PENDING_FIELD,
        CIPHER_COMPATIBILITY_FIELD,
    }
)


@dataclass(frozen=True)
class SlotRecord:
    """One slot as it sits on disk: its own salt, plus the wrapped DEK."""

    salt: bytes
    nonce: bytes
    wrapped_dek: bytes
    #: Fields of this slot that this build does not recognise, kept verbatim so
    #: a write does not delete them. Empty for every slot this build creates.
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def wrapped(self) -> Slot:
        """The ciphertext half, in the shape ``keywrap.unwrap_dek`` consumes."""
        return Slot(nonce=self.nonce, wrapped_dek=self.wrapped_dek)

    @classmethod
    def from_wrap(cls, salt: bytes, slot: Slot) -> SlotRecord:
        return cls(salt=salt, nonce=slot.nonce, wrapped_dek=slot.wrapped_dek)

    def to_dict(self) -> dict[str, object]:
        # Unrecognised fields first, so a stray key colliding with one this
        # build owns loses to the real value rather than overwriting it.
        return {
            **self.extra,
            "salt_hex": self.salt.hex(),
            "nonce_hex": self.nonce.hex(),
            "wrapped_dek_hex": self.wrapped_dek.hex(),
        }


@dataclass(frozen=True)
class VaultSidecar:
    """A parsed v2 sidecar — the cost parameters, the slots, and the two
    migration-only fields (§ 4.4).

    ``memory_kib`` and friends record the parameters the slots were actually
    derived under, **not necessarily today's pin**: a migrated vault carries the
    v1 vault's own recorded costs (§ 13.1), which is what lets
    ``validate_params``' directional floor keep opening it after the pin is
    raised. A migrated vault is exactly as strong as it was, and no stronger.
    """

    memory_kib: int
    time_cost: int
    parallelism: int
    key_len: int
    salt_len: int
    slots: dict[str, SlotRecord]
    migration_pending: bool = False
    cipher_compatibility: int | None = None
    #: Top-level and `kdf`-group keys this build does not recognise, kept
    #: verbatim across a read-modify-write. Both are empty for a vault this
    #: build creates, which is what keeps INV-4's exact field-set pin true.
    extra: dict[str, object] = field(default_factory=dict)
    kdf_extra: dict[str, object] = field(default_factory=dict)

    def params_for(self, slot: str) -> KdfParams:
        """The per-slot ``KdfParams`` — the shared costs plus THAT slot's salt.

        ``format_version`` is always ``FORMAT_VERSION`` (1), the params-record
        version, and never the sidecar's 2: ``validate_params``' first check is
        ``format_version != FORMAT_VERSION``, so building one from the file's
        own version would refuse every v2 vault — which is exactly why § 4.4
        gives the sidecar its own ``sidecar_version`` field name.
        """
        return self.params_with_salt(self.slots[slot].salt)

    def params_with_salt(self, salt: bytes) -> KdfParams:
        """The shared costs against an arbitrary salt — what a NEW slot derives
        under, so an added slot inherits this vault's schedule exactly."""
        return KdfParams(
            format_version=FORMAT_VERSION,
            memory_kib=self.memory_kib,
            time_cost=self.time_cost,
            parallelism=self.parallelism,
            key_len=self.key_len,
            salt_len=self.salt_len,
            salt=salt,
        )

    def with_slot(self, name: str, record: SlotRecord) -> VaultSidecar:
        """A copy carrying ``record`` at ``name`` — add or replace, never mutate."""
        return replace(self, slots={**self.slots, name: record})

    def without_slot(self, name: str) -> VaultSidecar:
        return replace(self, slots={k: v for k, v in self.slots.items() if k != name})

    def to_dict(self) -> dict[str, object]:
        # Unrecognised keys first at both levels, so one colliding with a name
        # this build owns loses to the real value rather than overwriting it.
        payload: dict[str, object] = dict(self.extra)
        payload.update(
            {
                "sidecar_version": SIDECAR_VERSION,
                "kdf": {
                    **self.kdf_extra,
                    "memory_kib": self.memory_kib,
                    "time_cost": self.time_cost,
                    "parallelism": self.parallelism,
                    "key_len": self.key_len,
                    "salt_len": self.salt_len,
                },
                "slots": {name: rec.to_dict() for name, rec in self.slots.items()},
            }
        )
        # Written only when true / set, so a freshly created vault carries
        # exactly the three top-level keys INV-4 pins.
        if self.migration_pending:
            payload[MIGRATION_PENDING_FIELD] = True
        if self.cipher_compatibility is not None:
            payload[CIPHER_COMPATIBILITY_FIELD] = self.cipher_compatibility
        return payload


def new_sidecar(params: KdfParams, slots: dict[str, SlotRecord]) -> VaultSidecar:
    """A v2 sidecar taking its shared costs from ``params`` (whose own salt is
    ignored — a salt belongs to a slot, never to the ``kdf`` group)."""
    return VaultSidecar(
        memory_kib=params.memory_kib,
        time_cost=params.time_cost,
        parallelism=params.parallelism,
        key_len=params.key_len,
        salt_len=params.salt_len,
        slots=slots,
    )


def write_sidecar_json(sidecar_path: Path, payload: Mapping[str, object]) -> None:
    """Atomically write the plaintext sidecar as owner-only (coding.md § 7).

    The one writer for both shapes — ``Vault._write_sidecar``'s flat v1 record
    and the v2 slots object — so the durability and permission posture cannot
    drift between them.
    """
    text = json.dumps(payload, indent=2)
    tmp_path = sidecar_path.with_name(sidecar_path.name + ".tmp")
    # O_NOFOLLOW refuses to open through a symlink planted at the .tmp path, so
    # the write can't be redirected to truncate/overwrite an attacker's target
    # (0 on Windows, where the flag is absent — a no-op there).
    fd = os.open(
        tmp_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, sidecar_path)


def write_sidecar_v2(sidecar_path: Path, sidecar: VaultSidecar) -> None:
    write_sidecar_json(sidecar_path, sidecar.to_dict())


def _read_json(sidecar_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(sidecar_path.read_text())
    except _MALFORMED_SIDECAR as exc:
        raise KdfPolicyError(f"sidecar unreadable or not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise KdfPolicyError("sidecar is not a JSON object")
    return data


def sidecar_version(sidecar_path: Path) -> int:
    """``2`` for the slots shape, ``1`` for today's flat one.

    Dispatch is on the PRESENCE of ``sidecar_version``: absent means the v1
    shape every vault in the field is written in, which is § 13's only
    migration source. A v2-only loader would reject all of them, and the
    migration could then never run — it needs the v1 vault *open* to copy it.
    """
    data = _read_json(sidecar_path)
    if "sidecar_version" not in data:
        return 1
    try:
        version = int(data["sidecar_version"])
    except (TypeError, ValueError) as exc:
        raise KdfPolicyError(f"sidecar_version is not an integer: {exc}") from exc
    if version != SIDECAR_VERSION:
        raise KdfPolicyError(
            f"unsupported sidecar_version {version} (expected {SIDECAR_VERSION})"
        )
    return version


def _validate_slot_lengths(name: str, record: SlotRecord) -> None:
    """§ 4.4's fixed sizes for the ciphertext half — the salt is validate_params'.

    Without this the loader hands a malformed record to ``unwrap_dek``, which
    fails closed with the one undifferentiated error it gives everything — and
    the unlock path reports that as an ordinary failed attempt. So a damaged
    key record told the user to check a password that was right, and charged
    the § 6 throttle for it (FIBR-0307 finding 9).

    **A length is not an oracle**, which is why the check belongs here and not
    beside the unwrap. It is public: the sidecar is plaintext, so anyone who
    can read the file can measure both fields without any credential. And this
    runs before a password is derived at all. ``unwrap_dek`` still answers
    everything it sees with one error, because the causes it can distinguish
    ARE secret-dependent.
    """
    if len(record.nonce) != NONCE_LEN:
        raise KdfPolicyError(
            f"slot {name!r} has a {len(record.nonce)}-byte nonce, expected {NONCE_LEN}"
        )
    if len(record.wrapped_dek) != WRAPPED_DEK_LEN:
        raise KdfPolicyError(
            f"slot {name!r} has a {len(record.wrapped_dek)}-byte wrapped DEK, "
            f"expected {WRAPPED_DEK_LEN}"
        )


def validate_slot(sidecar: VaultSidecar, name: str) -> None:
    """§ 4.4's per-slot checks for one slot: its ciphertext lengths and the
    cost record its own salt gives.

    Public because the route that uses an OPTIONAL slot has to run it itself:
    :func:`read_sidecar_v2` hard-fails on `master` alone, so a damaged
    `recovery` slot loads (FIBR-0310 R5) and the recovery route is what has to
    refuse it — with FIBR-0307 finding 9's distinct "the record is damaged"
    rather than the throttled "wrong credential" an unwrap would give.
    """
    _validate_slot_lengths(name, sidecar.slots[name])
    validate_params(sidecar.params_for(name))


def read_sidecar_v2(sidecar_path: Path) -> VaultSidecar:
    """Parse and validate the v2 slots sidecar, else ``KdfPolicyError``.

    Every slot is validated **individually**: the cost parameters come from the
    shared ``kdf`` group but the salt-length legs are checked against *that
    slot's* salt, so ``salt_len: 16`` beside a 4-byte ``slots.master.salt_hex``
    is rejected. Reading ``kdf`` alone would silently drop the real-salt-length
    leg ``security-model.md`` INV-2's exact-format match requires.

    The nonce and wrapped DEK are the same class of check and are
    :func:`_validate_slot_lengths`'.
    """
    data = _read_json(sidecar_path)
    if sidecar_version(sidecar_path) != SIDECAR_VERSION:
        raise KdfPolicyError("not a version-2 sidecar")

    kdf = data.get("kdf")
    slots_raw = data.get("slots")
    if not isinstance(kdf, dict) or not _V2_KDF_FIELDS <= kdf.keys():
        raise KdfPolicyError("v2 sidecar is missing one or more `kdf` fields")
    if not isinstance(slots_raw, dict) or not slots_raw:
        raise KdfPolicyError("v2 sidecar carries no `slots`")

    slots: dict[str, SlotRecord] = {}
    try:
        for name, record in slots_raw.items():
            if not isinstance(record, dict) or not _V2_SLOT_FIELDS <= record.keys():
                raise KdfPolicyError(f"slot {name!r} is missing a required field")
            slots[name] = SlotRecord(
                salt=bytes.fromhex(record["salt_hex"]),
                nonce=bytes.fromhex(record["nonce_hex"]),
                wrapped_dek=bytes.fromhex(record["wrapped_dek_hex"]),
                extra={k: v for k, v in record.items() if k not in _V2_SLOT_FIELDS},
            )
        compat_raw = data.get(CIPHER_COMPATIBILITY_FIELD)
        sidecar = VaultSidecar(
            memory_kib=int(kdf["memory_kib"]),
            time_cost=int(kdf["time_cost"]),
            parallelism=int(kdf["parallelism"]),
            key_len=int(kdf["key_len"]),
            salt_len=int(kdf["salt_len"]),
            slots=slots,
            migration_pending=bool(data.get(MIGRATION_PENDING_FIELD, False)),
            cipher_compatibility=None if compat_raw is None else int(compat_raw),
            extra={k: v for k, v in data.items() if k not in _V2_TOP_FIELDS},
            kdf_extra={k: v for k, v in kdf.items() if k not in _V2_KDF_FIELDS},
        )
    except (TypeError, ValueError) as exc:
        raise KdfPolicyError(f"sidecar field has a bad value: {exc}") from exc

    if SLOT_MASTER not in sidecar.slots:
        raise KdfPolicyError("v2 sidecar carries no `master` slot")
    for name in sidecar.slots:
        try:
            validate_slot(sidecar, name)
        except KdfPolicyError:
            # Damage in an OPTIONAL slot must not bar the routes that still
            # work. `master` is the one slot every vault has and the one every
            # other route depends on, so it hard-fails here; a damaged
            # `recovery` slot would otherwise lock a user out of their own
            # correct password because a credential they may never have used is
            # corrupt (FIBR-0310 R5).
            #
            # The record is KEPT rather than pruned. `AuthService` reads this
            # object, edits it and writes it back, so dropping the slot here
            # would silently delete the damaged one from disk the next time
            # anything touched the sidecar — turning a recoverable file into an
            # unrecoverable one. The route that USES the slot validates it
            # first, which is where FIBR-0307 finding 9's distinct error
            # belongs for an optional credential.
            if name == SLOT_MASTER:
                raise
            log.warning("sidecar slot %r is malformed; its route will refuse", name)
    return sidecar
