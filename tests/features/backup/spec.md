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
| INV-7 | Atomic export (temp → `os.replace`, temp unlinked on failure, no partial `.fbk`); every backup file `0o600`; the backup + new-master key buffers and the password buffer wiped in `finally` (asserted zeroed via the `on_key` seam). **FIBR-0212** adds two legs: the temp is created `O_EXCL` (a pre-planted mode-0666 `dest.fbk.tmp` cannot be filled and renamed into place — `O_NOFOLLOW` stopped only the symlink), and the destination **directory** is fsynced after the rename, so a power loss after "Backup saved" cannot leave no dest at all. |
| INV-9 | Export is synchronous on the main thread (no worker); the auto-lock `QTimer` cannot fire mid-export (a `qtbot` leg arms a 1 ms timer during a slow export and asserts it did not fire until export returned). |
| INV-11 | Restore re-validates the backup's `params.json` against the pinned Argon2 floor **before** deriving any key; a below-floor `memory_kib` → `BackupError`, no key derived, no disk change. |
| INV-12 | Safe-zip: a `../`-traversal entry name, an extra entry, and a `params.json` whose `ZipInfo.file_size` exceeds `MAX_MANIFEST_BYTES` are each refused; a large-but-legitimate `vault.db` restores. **FIBR-0212** implements INV-12's ratio clause, which the caps alone never covered: a small hostile `.fbk` whose `vault.db` is deflated zeros sized to land exactly ON `MAX_BACKUP_DB_BYTES` passes every size gate and inflates the full 512 MiB in RAM, pre-login. The refusal is matched on its message, since without the ratio check the restore raises `BackupError` anyway from the downstream "this isn't a vault" failure — a green that proves nothing. |
| INV-13 | Cipher-compat portability: a `.fbk` restores when the process default `cipher_compatibility` is forced to a different level (`PRAGMA cipher_default_compatibility`); a recorded level other than `SQLCIPHER_COMPAT` is refused. |
| INV-14 | **FIBR-0313 M1.** `export_backup` refuses to write a `.fbk` whose intermediate `vault.db` exceeds `MAX_BACKUP_DB_BYTES` — the same cap `_read_capped` already enforces on the restore side — raising `BackupError` with no `.fbk` and no `<dest>.tmp` left on disk. The boundary is symmetric with restore: exactly-at-cap exports, one byte over is refused. The export dialog (`MainWindow._on_backup_export_requested`) catches `BackupError` with its own message rather than letting it escape the Qt slot, and does not tell the user to "choose another location" — no other location makes an over-cap vault fit. Before this invariant, a vault over 512 MiB exported successfully, reported "Backup saved", and could never be restored on any machine. |
| INV-15 | **FIBR-0313 M2.** `_install`'s final `os.replace` calls for the installed database and sidecar, and the `*.old` move-aside pair created above them, are all made durable: the installed database and sidecar are fsynced as files, and EACH of their parent directories is fsynced too — `vault_path` and `sidecar_path` are injected independently on `Vault`, so a fix may not assume they share a parent. The `*.old` pair's directory fsync happens *before* the `on_key("post_move_aside", ...)` seam fires, so INV-5's premise — "the old pair is already safely aside" at that seam — holds across a crash there, not only across a clean run. Before this invariant, a power loss right after a restore (or right after the move-aside) could leave the vault in a state POSIX gives no durability guarantee for, on the one path whose whole purpose is recovering a vault. |
| INV-16 | `restore_backup`, called while the live vault (`self._vault`) is OPEN, refuses with `BackupError` before touching disk — no `*.old` move-aside, no change to the live `vault.db`/sidecar bytes, and the live vault still opens under its original password with its original rows. INV-8 says restore is pre-login only, and `_install`'s `os.replace(new_db, real_db)` depends on that: on Windows an open `vault.db` makes the rename raise loudly, but on POSIX the rename **succeeds** while the still-open connection goes on reading/writing the now-detached inode — silent divergence, no error. The one production caller (`ui/main_window.py :: _on_restore_requested`) is genuinely pre-login, so today the invariant is caller-held rather than local; this makes it local. |

| INV-17 | **FIBR-0318 Q4.** A SUCCESSFUL restore prunes older `*.old` sets, keeping only the most recent one — it does not touch the set it just created, which is the user's own "I restored the wrong backup" undo window (INV-5's crash-window prose, stretched to human timescale). Before this invariant nothing in `src/` ever unlinked a `*.old` set, so repeated restores accumulated full encrypted vault copies indefinitely. | `test_INV17_second_restore_prunes_older_old_set_keeps_newest` |

## FIBR-0033 — read-only verify (`verify_backup`)

`BackupService.verify_backup(src, backup_password, *, on_key=None) -> VerifyResult`
is a **read-only** "does this backup actually open?" probe: it reuses restore's
read → guard → open sequence (extracted into the shared `_open_backup_vault`
helper) but stops after the open, running `PRAGMA cipher_integrity_check` and
reporting schema + per-table counts without ever touching the live vault. Each
expected failure returns `ok=False` with a **stable `reason` code**, not an
exception. INV-1..7 below are FIBR-0033's **own local numbering** (distinct from
FIBR-0014's INV-1..13 above) — see [`docs/specs/FIBR-0033.md`](../../../docs/specs/FIBR-0033.md).

| INV | What it pins | Test |
|-----|--------------|------|
| INV-1 | Verify never mutates / opens the live vault: its dir stays byte-identical and gains no files. | `test_INV1_verify_leaves_live_vault_untouched` |
| INV-2 | A valid `.fbk` + correct password (with `cipher_integrity_check` clean) → `ok=True`, `schema_version == LATEST_SCHEMA_VERSION` (as-migrated), `table_counts` equal to the temp's actual per-table counts. | `test_INV2_verify_valid_backup_ok_with_counts` |
| INV-3 | A wrong backup password → `ok=False`, `reason="wrong_password"` (from the caught `DatabaseError`); no exception escapes. | `test_INV3_verify_wrong_password_reason` |
| INV-4 | Each bad-backup class maps to its reason code: a body/overflow-page corruption `count(*)` misses but `cipher_integrity_check` catches → `corrupt`; a manifest-under-states `.fbk` (embedded schema > LATEST) → `too_new`; below-floor/malformed KDF params → `bad_kdf_params`; a non-zip / guard failure → `invalid`; a temp-write `OSError` → `io_error`. | `test_INV4_verify_corrupt_overflow_page_reason`, `test_INV4_verify_too_new_embedded_schema_reason`, `test_INV4_verify_bad_kdf_params_reason`, `test_INV4_verify_invalid_non_zip_reason`, `test_INV4_verify_io_error_reason` |
| INV-5 | Verify leaves no temp files behind — the system `TemporaryDirectory` (spied via monkeypatch) is removed after every path. | `test_INV5_verify_leaves_no_temp` |
| INV-6 | The `_open_backup_vault` extraction leaves `restore_backup`'s observable behaviour unchanged — the whole FIBR-0014 restore suite above passes untouched. | (the Slice 1-4 restore tests) |
| INV-7 | Verify leaves no live key material: the backup key + password buffer are wiped on every path (owned by `_open_backup_vault`), observed via the `on_key` seam; verify derives **only** the backup key (no master). | `test_INV7_verify_wipes_backup_key_via_on_key_seam` |

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
