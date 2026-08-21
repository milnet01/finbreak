"""Shared helpers for the FIBR-0019 recovery-key suite — see spec.md.

One module rather than five copies (``coding.md`` § 1.3). Deliberately NOT a
``conftest.py``: the root ``tests/conftest.py`` is imported as the module
``conftest`` and several suites do ``from conftest import _PW``, so a second
``conftest`` on ``sys.path`` is a collision waiting to happen. A uniquely-named
sibling module is imported by pytest's ``prepend`` import mode from the suite's
own directory with no such hazard.

Every helper that asserts prints EXPECTED and ACTUAL (``testing.md`` § 5), so a
CI log alone diagnoses which part of the envelope is missing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from finbreak.crypto import derive_key
from finbreak.keywrap import Slot, unwrap_dek
from finbreak.models import FORMAT_VERSION, SIDECAR_VERSION, KdfParams
from finbreak.services.auth import AuthService
from finbreak.services.recovery_code import (
    CODE_SYMBOLS,
    DATA_ALPHABET,
    PAYLOAD_SYMBOLS,
    check_symbol,
    decode,
    format_code,
    normalise,
)
from finbreak.vault import Vault

# The suite's credentials. Synthetic throughout — no real financial data, no
# real account numbers (``testing.md`` § 6 / security-model INV-6).
MASTER_PASSWORD = b"correct horse battery staple"
NEW_MASTER_PASSWORD = b"a brand new master password"
BASE_CURRENCY = "ZAR"

# The v2 sidecar's exact shape for a vault created FRESH (§ 4.4). A
# mid-migration sidecar legally also carries ``migration_pending``, and any
# MIGRATED vault carries ``cipher_compatibility`` permanently — neither appears
# on a fresh one, which is why INV-4 pins the fresh shape.
SIDECAR_TOP_LEVEL = frozenset({"sidecar_version", "kdf", "slots"})
KDF_FIELDS = frozenset(
    {"memory_kib", "time_cost", "parallelism", "key_len", "salt_len"}
)
SLOT_FIELDS = frozenset({"salt_hex", "nonce_hex", "wrapped_dek_hex"})


# --------------------------------------------------------------------------- #
# Vault creation
# --------------------------------------------------------------------------- #
def create_vault(service: AuthService, password: bytes = MASTER_PASSWORD) -> str:
    """Run § 4.5 steps 1-7 and return the display-form recovery code.

    Steps 1-7 mint the DEK, wrap it under KEK-master and write the v2 sidecar
    carrying ``slots.master`` ONLY. The recovery slot is step 9's, on Keep —
    call :func:`keep_recovery_key`. Not calling it is Decline (D3/INV-12).
    """
    # Called through `Any`: today `first_run` is annotated `-> None`, and the
    # seam FIBR-0019 § 4.5 needs is for it to hand the generated code back.
    # The assertion below is what reports the gap; this cast only keeps mypy
    # from refusing to type-check the file before the widening lands.
    first_run = cast(Any, service.first_run)
    code = first_run(bytearray(password), BASE_CURRENCY)
    assert isinstance(code, str) and code.strip(), (
        "FIBR-0019 § 4.5 steps 4/8: first-run must GENERATE a recovery code and "
        "hand it back for the one-time display -- there is no other way for the "
        "user (or this suite) to learn it, because INV-5 forbids retaining it.\n"
        f"  expected: a non-empty str, {CODE_SYMBOLS} Crockford symbols in "
        "7 hyphen-separated groups of 4\n"
        f"  actual:   {code!r}"
    )
    return code


def keep_recovery_key(service: AuthService, code: str) -> None:
    """§ 4.5 step 9 — the user pressed **Keep**, so ``slots.recovery`` is written."""
    service.add_recovery_key(code)


def create_v1_vault(
    vault_path: Path, sidecar_path: Path, password: bytes = MASTER_PASSWORD
) -> tuple[Vault, KdfParams, bytearray]:
    """A vault in TODAY's format — the only migration source (§ 4.4).

    Built through the shipped ``Vault`` + ``derive_key`` path, so it is the
    on-disk shape of every vault in the field: a flat seven-field sidecar and a
    database keyed DIRECTLY by the Argon2id output. Returns the open vault, its
    params and the raw key, all of which § 13 needs.
    """
    from finbreak.crypto import (
        ARGON2_MEMORY_KIB,
        ARGON2_PARALLELISM,
        ARGON2_TIME_COST,
        KEY_LEN,
        SALT_LEN,
    )

    params = KdfParams(
        format_version=FORMAT_VERSION,
        memory_kib=ARGON2_MEMORY_KIB,
        time_cost=ARGON2_TIME_COST,
        parallelism=ARGON2_PARALLELISM,
        key_len=KEY_LEN,
        salt_len=SALT_LEN,
        salt=bytes(range(SALT_LEN)),
    )
    key = derive_key(bytearray(password), params.salt, params)
    vault = Vault(vault_path, sidecar_path)
    vault.create(bytearray(key), params, BASE_CURRENCY, 2)
    return vault, params, key


# --------------------------------------------------------------------------- #
# Sidecar reading
# --------------------------------------------------------------------------- #
def read_sidecar(sidecar_path: Path) -> dict[str, Any]:
    data = json.loads(sidecar_path.read_text())
    assert isinstance(data, dict), (
        f"the sidecar must parse to a JSON object\n"
        f"  expected: dict\n  actual:   {type(data).__name__}"
    )
    return data


def read_v2_sidecar(sidecar_path: Path) -> dict[str, Any]:
    """The parsed sidecar, asserting it is the § 4.4 v2 slots shape."""
    data = read_sidecar(sidecar_path)
    assert data.get("sidecar_version") == SIDECAR_VERSION, (
        "FIBR-0019 § 4.4: the installed vault's sidecar must be format version "
        f"{SIDECAR_VERSION}, under its own `sidecar_version` field (NOT "
        "`format_version`, which stays 1 and belongs to the .fbk params record).\n"
        f"  expected: sidecar_version == {SIDECAR_VERSION}\n"
        f"  actual:   sidecar_version={data.get('sidecar_version')!r}, "
        f"top-level keys={sorted(data)}"
    )
    return data


def require_slot(data: dict[str, Any], slot_name: str) -> dict[str, Any]:
    slots = data.get("slots")
    assert isinstance(slots, dict), (
        "FIBR-0019 § 4.4: a v2 sidecar carries a `slots` object.\n"
        f"  expected: dict of slot name -> record\n  actual:   {slots!r}"
    )
    assert slot_name in slots, (
        f"FIBR-0019 § 4.4: slot {slot_name!r} is missing from the sidecar.\n"
        f"  expected: {slot_name!r} present\n"
        f"  actual:   slots={sorted(slots)}"
    )
    record = slots[slot_name]
    assert isinstance(record, dict), (
        f"slot {slot_name!r} must be an object of {sorted(SLOT_FIELDS)}\n"
        f"  expected: dict\n  actual:   {record!r}"
    )
    return record


def slot_params(data: dict[str, Any], slot_name: str) -> KdfParams:
    """The per-slot ``KdfParams``: the shared ``kdf`` costs + THAT slot's salt.

    ``format_version`` is always ``FORMAT_VERSION`` (1) — the params-record
    version — never the sidecar's 2. Building it from the file's ``2`` is the
    trap § 4.4's rename exists to remove: ``validate_params``' first check would
    then refuse every v2 vault.
    """
    kdf = data.get("kdf")
    assert isinstance(kdf, dict), (
        "FIBR-0019 § 4.4: a v2 sidecar carries a `kdf` group holding the "
        "Argon2id cost parameters shared by every slot.\n"
        f"  expected: dict of {sorted(KDF_FIELDS)}\n  actual:   {kdf!r}"
    )
    record = require_slot(data, slot_name)
    return KdfParams(
        format_version=FORMAT_VERSION,
        memory_kib=int(kdf["memory_kib"]),
        time_cost=int(kdf["time_cost"]),
        parallelism=int(kdf["parallelism"]),
        key_len=int(kdf["key_len"]),
        salt_len=int(kdf["salt_len"]),
        salt=bytes.fromhex(record["salt_hex"]),
    )


def slot_record(data: dict[str, Any], slot_name: str) -> Slot:
    record = require_slot(data, slot_name)
    return Slot(
        nonce=bytes.fromhex(record["nonce_hex"]),
        wrapped_dek=bytes.fromhex(record["wrapped_dek_hex"]),
    )


def kek_for(secret: bytes, data: dict[str, Any], slot_name: str) -> bytearray:
    """Derive the KEK for ``slot_name`` from ``secret`` and that slot's salt."""
    params = slot_params(data, slot_name)
    return derive_key(bytearray(secret), params.salt, params)


def unwrap_slot(secret: bytes, data: dict[str, Any], slot_name: str) -> bytearray:
    """Derive the KEK from ``secret`` and unwrap ``slot_name`` — the DEK."""
    params = slot_params(data, slot_name)
    kek = kek_for(secret, data, slot_name)
    return unwrap_dek(bytes(kek), slot_record(data, slot_name), slot_name, params)


def forge_wrong_code_with_a_valid_check_symbol(code: str) -> str:
    """A DIFFERENT payload carrying a CORRECT check symbol, in display form.

    One data symbol of the payload is advanced by one place in the alphabet and
    the mod-37 check symbol recomputed over the result -- so the forgery is
    locally well-formed and points at a different 135-bit value. What INV-6 and
    INV-11 both need: a code that passes the typo check and is not the real one.
    """
    payload = normalise(code)[:PAYLOAD_SYMBOLS]
    head = DATA_ALPHABET[(DATA_ALPHABET.index(payload[0]) + 1) % len(DATA_ALPHABET)]
    forged_payload = head + payload[1:]
    return format_code(forged_payload + check_symbol(forged_payload))


def code_secret(code: str) -> bytes:
    """What Argon2id is fed for the recovery route: the DECODED 17 big-endian
    bytes, check symbol excluded (§ 4.3) — never the text."""
    return decode(normalise(code))


# --------------------------------------------------------------------------- #
# Opening
# --------------------------------------------------------------------------- #
def opens_with(vault_path: Path, sidecar_path: Path, key: bytearray) -> bool:
    """``True`` iff ``key`` is the database's raw key. Closes what it opens."""
    from sqlcipher3.dbapi2 import DatabaseError

    vault = Vault(vault_path, sidecar_path)
    try:
        vault.open(bytearray(key))
    except DatabaseError:
        return False
    vault.close()
    return True


def table_names(conn: Any) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def row_digests(conn: Any) -> dict[str, tuple[int, str]]:
    """Per-table ``(row count, ordered content digest)`` for EVERY table.

    The witness INV-8 and INV-13 use. Deliberately NOT a hash or mtime of
    ``vault.db``: vaults run ``journal_mode = WAL``, so pages sit in
    ``vault.db-wal`` until a checkpoint and the main file's bytes move on open
    and close with no logical write at all — flaky in one direction and vacuous
    in the other (INV-12/INV-13 say so in as many words).
    """
    digests: dict[str, tuple[int, str]] = {}
    for name in table_names(conn):
        rows = conn.execute(f'SELECT * FROM "{name}"').fetchall()
        blob = repr(sorted(repr(row) for row in rows)).encode("utf-8")
        digests[name] = (len(rows), hashlib.sha256(blob).hexdigest())
    return digests


def open_after_restart(
    vault_path: Path, sidecar_path: Path, password: bytes = MASTER_PASSWORD
) -> Vault:
    """Open the pair the way a FRESH APP START would — dispatching on the
    sidecar's shape, exactly as § 4.4's loader must.

    A v1 sidecar means the Argon2id output IS the database key. A v2 sidecar
    means derive KEK-master from ``slots.master``'s salt, unwrap, and open with
    the resulting DEK. Raises whatever the real path would raise.

    A v2 sidecar carrying ``migration_pending`` runs § 13.3's resume ladder
    first, by calling the PRODUCTION one — because that is what a fresh app
    start does, and it is what makes INV-7 true (§ 13.3's own heading says so).
    Between S4 and S5 the sidecar describes the new schedule while the database
    is still on the old one; unwrapping and opening without the ladder finds a
    DEK that no database on disk answers to, which is a gap in this simulation
    rather than in the migration. The ladder is entered only AFTER the slot has
    unwrapped, which is § 13.3's step 0: a mistyped password must be a failed
    attempt, never a user told their vault is corrupt.

    ``cipher_compatibility`` is passed on every v2 open, as § 13.2 requires:
    ``export_to`` writes the migrated database at an explicit level where a
    ``create``d one takes the library default, and the two agreeing today is
    exactly what stops agreeing after a ``sqlcipher3-wheels`` bump.
    """
    from finbreak.services import vault_migration

    data = read_sidecar(sidecar_path)
    vault = Vault(vault_path, sidecar_path)
    if "sidecar_version" not in data:
        params = KdfParams(
            format_version=int(data["format_version"]),
            memory_kib=int(data["memory_kib"]),
            time_cost=int(data["time_cost"]),
            parallelism=int(data["parallelism"]),
            key_len=int(data["key_len"]),
            salt_len=int(data["salt_len"]),
            salt=bytes.fromhex(data["salt_hex"]),
        )
        vault.open(derive_key(bytearray(password), params.salt, params))
        return vault
    dek = unwrap_slot(password, data, "master")
    if data.get("migration_pending"):
        vault_migration.resume(
            vault_path, sidecar_path, kek_for(password, data, "master"), dek
        )
        data = read_sidecar(sidecar_path)
    vault.open(dek, cipher_compat=data.get("cipher_compatibility"))
    return vault


# --------------------------------------------------------------------------- #
# UI seams
# --------------------------------------------------------------------------- #
def require_seam(owner: Any, name: str, why: str) -> Any:
    """Fetch a seam FIBR-0019 requires, failing diagnosably when it is absent.

    § 4.6 fixes the recovery route's BEHAVIOUR and not its attribute names, so
    the names this suite binds to are recorded in spec.md § Seams. A miss here
    means the seam is absent or was named differently, never that the behaviour
    is wrong.
    """
    seam = getattr(owner, name, None)
    assert seam is not None, (
        f"FIBR-0019 seam missing: {owner!r} has no {name!r}.\n"
        f"  why it is needed: {why}\n"
        f"  expected: an attribute named {name!r}\n"
        f"  actual:   absent (public attributes: "
        f"{sorted(a for a in dir(owner) if not a.startswith('__'))})"
    )
    return seam
