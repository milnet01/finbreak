# tests/features/backup — FIBR-0014 Encrypted backup export / restore

Conformance tests for [`docs/specs/FIBR-0014.md`](../../../docs/specs/FIBR-0014.md).
The `.fbk` is a portable, self-contained encrypted backup (a zip of
`manifest.json` + `params.json` + `vault.db`) keyed by a **separate backup
password**, so a forgotten master password is recoverable with the backup
password + a new master password — never the old master (ADR-0003 / T11).

The D2 SQLCipher mechanics (`sqlcipher_export`, `PRAGMA rekey`,
`cipher_compatibility`, HMAC-on, no-plaintext-temp) were validated by a throwaway
spike on `sqlcipher3-binary==0.6.0` (SQLCipher 4.12.0 community / openssl) before
any production code; the spike is not shipped. Notable spike finding: the
`cipher_compatibility` / `cipher_default_compatibility` pragmas are **write-only**
(reads return `None`), so restore *applies* the recorded level and never reads it
back.

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-1 | The `.fbk` is a 3-entry zip (`manifest.json`, `params.json`, `vault.db`); a distinctive seeded sentinel account/description never appears in the raw `.fbk` bytes. |
| INV-1b | No plaintext (the sentinel) spills to any temp/journal file during export **or** restore (`temp_store=MEMORY`). |
| INV-2 | Round-trip fidelity — restoring reproduces every application table's rows (enumerated dynamically from `sqlite_master`), including the `schema_version` row. |
| INV-3 | Separate backup password: export under `B`, restore with `B` + new master `M2` (old master never supplied) → vault opens under `M2`, the old master fails. |
| INV-4 | Fail-closed: wrong backup password / truncated / non-zip / entry-missing / `format_version = MANIFEST_FORMAT_VERSION + 1` → `BackupError`, on-disk vault byte-identical. |
| INV-5 | Overwrite safety: an existing vault + sidecar move aside to timestamped `*.old` before install; a post-move-aside failure (via the `on_key` seam) leaves the vault recoverable from `*.old`. |
| INV-6 | Version guard, both layers: `manifest.schema_version > LATEST_SCHEMA_VERSION` refused before any disk change; a backup DB whose `schema_version` table exceeds `LATEST` refused on open even if the manifest lies. |
| INV-7 | Atomic export (temp → `os.replace`, temp unlinked on failure, no partial `.fbk`); every backup file `0o600`; the backup + new-master key buffers and the password buffer wiped in `finally` (asserted zeroed via the `on_key` seam). |
| INV-9 | Export is synchronous on the main thread (no worker); the auto-lock `QTimer` cannot fire mid-export (a `qtbot` leg arms a 1 ms timer during a slow export and asserts it did not fire until export returned). |
| INV-11 | Restore re-validates the backup's `params.json` against the pinned Argon2 floor **before** deriving any key; a below-floor `memory_kib` → `BackupError`, no key derived, no disk change. |
| INV-12 | Safe-zip: a `../`-traversal entry name, an extra entry, and a `params.json` whose `ZipInfo.file_size` exceeds `MAX_MANIFEST_BYTES` are each refused; a large-but-legitimate `vault.db` restores. |
| INV-13 | Cipher-compat portability: a `.fbk` restores when the process default `cipher_compatibility` is forced to a different level (`PRAGMA cipher_default_compatibility`); a recorded level other than `SQLCIPHER_COMPAT` is refused. |

## Reuse helpers (Deliverable 2 — `vault.py`)

| Helper | What it pins |
|--------|--------------|
| `Vault.export_to(dest_db, backup_key)` | ATTACH-and-`sqlcipher_export` a backup DB onto the live master-keyed connection: pre-creates the target `0o600`, sets `temp_store=MEMORY`, writes at `SQLCIPHER_COMPAT` with HMAC on, DETACHes, and restores the connection's prior `temp_store`. Reopening the target with the backup key reproduces the tables + `schema_version`; a wrong key fails page-1. A locked vault raises `VaultLockedError`. |
| `Vault.rekey(new_key)` | `PRAGMA rekey` in place — after it, the old key fails and the new key opens with data intact. |
| `Vault.open(key, *, in_memory_temp, cipher_compat)` | `in_memory_temp=True` sets `temp_store=MEMORY` before `run_migrations` (INV-1b); `cipher_compat` applies the recorded level **before** `cipher_use_hmac=ON` (INV-13). |

`SQLCIPHER_COMPAT = 4` lives in `vault.py` (where the PRAGMA is issued) and is
imported by `services/backup.py` for the manifest — the spec placed it in
`backup.py`, but `Vault.export_to` needs it and `vault.py` cannot import upward
from `services/` (circular import). Noted as a spec refinement.

INV-8 (pre-login reachability) and INV-10 (i18n / geometry) are UI-layer; INV-10's
no-fixed-geometry glob (`test_INV10_no_fixed_geometry_in_new_ui`) covers the new
UI modules automatically.
