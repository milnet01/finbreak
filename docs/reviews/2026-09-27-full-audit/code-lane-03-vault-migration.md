**Subject line counts as read:** `src/finbreak/services/vault_migration.py` has 1017 lines and `src/finbreak/migrations.py` has 485.

**Already in my context before I read anything:**
- the global `~/.claude/CLAUDE.md` and `/mnt/Games/CLAUDE.md`;
- finbreak's `CLAUDE.md`, whose module map describes `vault_migration.py` / § 13 and the "decoded payload" rule;
- the finbreak `MEMORY.md` index;
- a git snapshot (HEAD 52e5162).

**What I read beyond the two subject files:**
- the shared-context packet;
- FIBR-0019 § 6 (Failure modes) and § 13 through § 13.5;
- design.md § Persistence;
- `crypto.fsync_dir`, `write_sidecar_json` and `write_sidecar_v2`;
- `db.owned_transaction`;
- `Vault.open`, `_connect`, `rekey` and `export_to`;
- the v1 schema in `Vault.create`, which I grepped;
- `AuthService._unlock_v1`;
- the `wrap_dek` signature.

I did not open any tests.

**Other notes:**
- One `workspace_search` was rate-limited, so I used `Grep` for that search.
- I did not read the other migration-citing specs (FIBR-0193/0172/0171/0154/0148/0143/0142/0139) in full. I checked the migrations against their own docstrings and SQLite semantics instead.

## Critical (0)

## High (0)

## Medium (1)

- [dim 9] `migrations.py:56` — `current = conn.execute("SELECT version FROM schema_version").fetchone()[0]`
  - **Problem:** the guard at lines 57–66 exists because the version is untrusted on the `.fbk` restore path. Its comment says a bad value otherwise raises `KeyError`/`TypeError` "and no caller catches either". But a `schema_version` table with **zero rows** makes `fetchone()` return `None`, so `None[0]` raises `TypeError` before the guard runs. That is exactly the uncaught class the comment says it removes. A crafted or damaged `.fbk` with an empty table still escapes as an unmapped `TypeError`.
  - **Fix:** fetch the row, and raise `SchemaVersionError` when it is `None`, before the `isinstance` test.

## Low / Info

- [dim 3] `vault_migration.py:601` — `wrapped = wrap_dek(kek_master, bytes(dek), SLOT_MASTER, params)`
  - **Problem:** `bytes(dek)` makes an immutable, unwipeable copy of the DEK. The comment at lines 527–531 says the `finally` wipe exists precisely so the DEK is not "left in the heap" (security-model INV-3), and this copy defeats that wipe.
  - **Cause:** `keywrap.wrap_dek(kek: bytes | bytearray, dek: bytes, …)` widened only the KEK parameter when FIBR-0310 P8 removed the KEK copies. The same pattern remains at `auth.py:426` and `backup.py:320`.
  - **Fix:** widen `dek` to `bytes | bytearray` in `wrap_dek` and pass the buffer straight through.

- [dim 16] `vault_migration.py:622` — `fsync_dir(sidecar_path.parent)`
  - **Problem:** § 13.2 S4 requires the S4 rename to be durable before S5. `crypto.fsync_dir` silently does nothing on Windows (its docstring: "Windows refuses it outright"), so on a shipped platform the S4→S5 ordering guarantee is not delivered.
  - **Consequence:** if the two renames reorder, the result is the state the spec says the ladder "has no branch for": a v1 sidecar over a DEK-keyed database.
  - **Uncertainty:** NTFS metadata journaling may keep the renames in order in practice. I have not verified this.
  - **Fix:** on Windows, do the S4/S5 renames with `MoveFileExW(MOVEFILE_WRITE_THROUGH)`, or record the gap in § 13.2 / § 6.

- [dim 9] `vault_migration.py:667-670` (`_finish`)
  - **Problem:** the `.pre-v2` unlinks happen in `vault_path.parent`, and only `sidecar_path.parent` is flushed (inside `write_sidecar_json`). Where the two parents differ, a case this module explicitly allows for at lines 404–407, the flag-clear can become durable while the unlink does not. That strands the copy with no bookkeeping, which is the R8 hazard S6's ordering exists to prevent.
  - **Fix:** call `fsync_dir(vault_path.parent)` after the unlinks and before `write_sidecar_v2`.

- [dim 9] `vault_migration.py:673-692` (`migration_artefacts`)
  - **Problem:** the list omits:
    - the `write_sidecar_json` temp files (`vault.kdf.json.migrating.tmp`, `vault.kdf.json.pre-v2.tmp`);
    - a rollback-journal sibling (`vault.db.migrating-journal`), which the ATTACHed export target plausibly leaves after a crash mid-S1 (the attached database is not in WAL mode).
  - **Consequence:** "start over" (INV-12) and the post-restore prune can leave these behind. They are encrypted or wrapped material whose key record is gone, so the blast radius is small.
  - **Uncertainty:** unexecuted. It needs a kill during S1 followed by a listing of the directory.

- [INFO] **Contract checks not run in full.** I did not check `_migrate_to_v6`'s `BETWEEN` backfill against FIBR-0052's date format, or any migration against its own spec's exact column list. I judged them against their docstrings and SQLite semantics only.

## Covered by spec and looks correct

- **`vault_migration.py` against FIBR-0019 § 13.2:**
  - S0: sibling order (stale siblings are cleared after the DB copy but before anything opens it), fsync of each copy and both parents, the `integrity_check` verification, and the rejection of a v2 sidecar.
  - S1: unlinks `.migrating` and its siblings, then exports and fsyncs.
  - S2: `integrity_check` plus a comparison of every table's row count, deleting the file on failure. The log carries table names only (INV-9).
  - S3: the pending sidecar with `cipher_compatibility`.
  - S4: replace, then fsync of the parent directory.
  - S5: siblings dropped before the replace.
  - S6: removal first, then the flag clear.
- **§ 13.3 ladder:**
  - Branch 1 does a full read before S6, and makes the rollback offer.
  - Branch 2 separates SOUND / UNSOUND / UNCOMPARABLE, keeps the file and refuses when counts are unavailable, and secures the rollback copy before the swap.
  - Branch 3 goes through `_ensure_rollback_copy`, which reuses the S0 copy or retakes it with the sidecar rebuilt from `slots.master`, and restarts with the step-0 DEK.
  - Terminal branch: `RollbackAvailableError` versus `VaultStateError`.
- **Probes:** every one (`_opens`, `_reads_end_to_end`, `_row_counts_or_none`, `verify_rollback_copy`) uses `migrate=False` and `in_memory_temp=True`.
- **Straight-through failure after S4:** I traced it through `AuthService._unlock_v1`. It is routed to `resume` because the sidecar version is checked, so an S5/S6 failure is recoverable.
- **Restore order:** `restore_rollback_copy` moves the database first and the sidecar second, as § 13.3 argues.
- **`migrations.py`:**
  - Each step runs inside `owned_transaction` (design.md § Persistence).
  - The version table is contiguous from 2 to 14, a newer version is refused, and there is no downgrade.
  - The v1→v2 rebuild matches the v1 schema in `Vault.create`.
  - That rebuild runs with `foreign_keys = ON`, which SQLite § 7 advises against. It is harmless here because no v1 table references `transactions`, and the rename has no triggers or views to rewrite.
  - The nullable `ADD COLUMN … REFERENCES` steps satisfy SQLite's rule that such a column must default to `NULL` when foreign keys are on.

**Other dimensions, one line each:**
- **dim 2b:** no zombie. `STEPS` has no use in `src/`, but no contract promises it, so it is a dead symbol.
- **dim 4:** no diverged duplicates found. `_WAL_SIBLINGS` is mirrored in `backup.py`, and the two copies are identical.
- **dim 5:** nothing found.
- **dim 7:** nothing found. `_finish_quietly` absorbs only `OSError`, and says so.
- **dim 8:** N/A — nothing is shared across threads.
- **dim 10:** nothing leaks counts or keys into the log.
- **dim 12:** N/A.
- **dim 13:** timestamps use `datetime.now(UTC)`.
- **dim 15:** nothing leaves the machine.
- **dim 17:** a newer schema is refused. The v2 downgrade door is stated in § 13.4.

## Open questions

- **Stale rollback offer.** A resume-path S6 that hits an `OSError` (for example a file held open on Windows) leaves `migration_pending` set indefinitely while the user keeps using the v2 vault. If branch 1 later finds the vault does not read end to end, it offers the `.pre-v2` copy, which may then be weeks old. Restoring it silently drops everything entered since the migration. Neither § 13.3 nor this code says the offered copy may be stale. I cannot tell whether the unlock UI's wording covers this, because I did not read it.
- **Possible restore/migrate loop.** After `restore_rollback_copy` the sidecar is v1 again, so the very next unlock re-runs `migrate_to_v2`. If the failure that led to the rollback is deterministic, the user may cycle between migrating and rolling back. Is that intended? § 13.3 is silent.

## 3 items to fix first

1. **The empty `schema_version` gap at `migrations.py:56`.** It is on an untrusted-input path, and the guard's own comment claims the case is already covered.
2. **`bytes(dek)` at `vault_migration.py:601` (and its siblings).** It defeats an INV-3 wipe that the module explicitly built, and the fix is to widen one annotation in `wrap_dek`.
3. **The silent Windows no-op of S4's directory fsync (`vault_migration.py:622`).** It is the one step § 13.2 says the ladder cannot recover from, on a platform the project ships.