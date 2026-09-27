**Lane 04: encrypted backup (.fbk) export, verify, restore, and start-over (vault wipe)**

Lines as read: `services/backup.py` 782 · `ui/backup_export.py` 112 · `ui/backup_restore.py` 140 · `ui/backup_verify.py` 179 · `ui/start_over.py` 91.

**What was in my context before I read anything:**
- `~/.claude/CLAUDE.md`
- `/mnt/Games/CLAUDE.md`
- the finbreak `CLAUDE.md`
- the finbreak `MEMORY.md` index
- a git snapshot (main, clean, HEAD 52e5162)
- the shared-context packet

The finbreak `CLAUDE.md` names the models.FORMAT_VERSION trap and the key-envelope design, so I did not start fully cold. I read the subject from disk.

**Contracts I did read:**
- FIBR-0014: the invariants, design decisions, deliverables, data model and out-of-scope sections.
- FIBR-0033: the mechanism, design decisions and invariants.
- FIBR-0030: § 3.2.
- For cross-checks only: the three callers in `main_window.py` (1150–1245, 1535–1570), `vault.py` 38–110, `paths.data_dir`, and `crypto.load_and_validate_params`.

**Contracts I did not read:**
- FIBR-0019's backup section, security-model § 5, design.md § Persistence.
- FIBR-0177, 0193 and 0142 (outlined only).
- `python.md` and `qt.md`.

Nothing below is judged against those.

## Critical (0)

## High (0)

## Medium (4)

- **[dim 3] Crafted `.fbk` input escapes restore and verify as an unhandled exception.** `backup.py:522` — `if compat not in SQLCIPHER_COMPAT_ACCEPTED or not isinstance(compat, int):`
  - `SQLCIPHER_COMPAT_ACCEPTED` is a `frozenset` (`vault.py:42`). A manifest with `"sqlcipher_compat": []` or `{}` therefore raises `TypeError: unhashable type` before the `isinstance` check runs.
  - A second route: `_read_capped` → `zf.open(info)` (`backup.py:730`). A zip entry with the encryption flag set raises `RuntimeError`, and an unknown compression method raises `NotImplementedError`. Neither is in `_read_fbk`'s except tuple (`backup.py:690-707`).
  - None of these three is in `restore_backup`'s tuple (354-369). They are also not in the restore caller's `(BackupError, ValueError)` (`main_window.py:1554`), nor in verify's handlers (437-460). The verify caller catches nothing.
  - So a tampered or corrupt `.fbk` produces a traceback out of a Qt slot on the pre-login restore path, not INV-4's "fail-closed with a clear message". The same happens on verify, not FIBR-0033 D4's friendly answer. Unexecuted — needs a crafted zip to confirm.
  - Fix: put `isinstance(compat, int)` first. Add `RuntimeError` (which covers `NotImplementedError`) to `_read_fbk`'s normaliser.

- **[dim 9] A retried restore after a partial install can delete the original vault's recovery copy.** `backup.py:657-658` — `os.replace(new_db, real_db)` / `os.replace(new_sidecar, real_sidecar)`, together with `backup.py:550` — `for stamp in sorted(sets)[:-1]:`
  - Sequence: the first restore moves the original pair to `.old@T1`, installs `vault.db`, and then the sidecar replace fails.
  - The caller then says "on-disk vault unchanged" (it isn't) and keeps the dialog open for a retry.
  - The retry moves the orphan restored `vault.db` to `.old@T2` (with no sidecar), installs, and prunes. That keeps T2, a useless orphan, and deletes T1, the user's original vault plus its sidecar.
  - Uncommon, because it needs the second rename to fail, but the result is losing the one copy INV-5 promises is "always recoverable".
  - Fix: prune only after a clean install, and never delete a set that includes a sidecar in favour of one that does not. Or make `_install` return its stamp and scope the prune to it.

- **[dim 16] If the clock moves backwards, the prune deletes the copy it exists to keep.** `backup.py:550` — `sorted(sets)[:-1]`, with the stamp from `datetime.now(UTC)` (622).
  - The prune keeps the lexically newest stamp, not the set this restore just created.
  - If the system clock was set back between two restores, the vault just replaced gets an older stamp and is deleted. A stale set survives in its place.
  - That defeats the docstring's "I restored the wrong backup" copy.
  - Fix: `_install` returns the stamp it wrote, and the prune keeps exactly that stamp.

- **[dim 2] Export shows the wrong error when the destination is the vault itself.** `backup.py:181` — `raise BackupError("a backup cannot be written over the vault itself")`
  - The export caller (`main_window.py:1170-1175`) assumes BackupError comes "from exactly one place — the INV-14 size refusal". It shows "this vault is too large to back up".
  - So a user who picks the live vault file as the destination is told their vault is too big. Nothing is lost.
  - The caller is the stale side: its comment predates FIBR-0337 L6.
  - Fix: separate the two causes, either with a subclass or a code on `BackupError`.

## Low / Info

- **[dim 16] LOW, `backup.py:213`:** `with tempfile.TemporaryDirectory() as td:` — export stages the intermediate DB (up to 512 MiB) in the system temp directory.
  - On a tmpfs `/tmp` that is held in RAM.
  - If `/tmp` is full, the OSError reaches the caller's "choose another location" message (`main_window.py:1186`). That advice cannot help, because the failure is not at the destination.
  - Fix: stage beside `dest`.

- **[dim 16] LOW, `backup.py:437`:** a disk-full while migrating verify's temp copy raises an SQLite `OperationalError`, which is a `DatabaseError`. Verify then reports it as `wrong_password`, not `io_error`.

- **[dim 16] LOW, `backup.py:289-352`:** the post-install `TemporaryDirectory` cleanup still runs inside the normalising try. If removing `params.json` fails (for example a Windows antivirus lock), a restore that did install is reported as "Restore failed … unchanged". Unexecuted.

- **[dim 3] LOW, `backup.py:180`:** the dest guard compares only the live pair. A destination that resolves to the live `vault.db-wal` or `-shm` gets replaced under the open connection.

- **[dim 13] LOW, `backup_verify.py:117`:** `self.tr("{n} transactions.").format(n=…)` has no plural form, so it reads "1 transactions." Use `tr("%n transaction(s)", "", n)`.

- **[dim 2] LOW, doc side (for review-contract), FIBR-0014:**
  - Its Out-of-scope says "Pruning the `*.old` vault copies … manual for now", and INV-5 says "always recoverable". The code prunes under INV-17.
  - FIBR-0030 § 3.2 still says to keep DELETE inside the `tr()` string. The code interpolates it (FIBR-0216), which is the correct side.

- **INFO: dimensions with nothing found.** 2b: every promised entry point has a caller. 4, 5, 7 (beyond the above), 8, 10, 11, 15: nothing found. 12: N/A. 17: see the verified list below.

- **INFO: contracts not read.** FIBR-0019's backup section, security-model § 5, design.md § Persistence, and `python.md`/`qt.md` were not read. FIBR-0177, 0193 and 0142 were outlined only.

## Covered by spec and looks correct

These are the paths I opened and checked against the contract:
- **INV-12 zip handling:** the exact-three-names check (duplicates rejected by the sorted equality), the per-entry caps plus the ratio test before inflating, the bounded `read(allowed+1)`, and ZIP_STORED on `vault.db`.
- **INV-14:** export uses the same `>` edge as restore.
- **INV-11:** params are validated before the backup key is derived. The params temp is inside AppDataLocation on restore and in system temp on verify, per FIBR-0033 D6.
- **INV-7:** every key and password buffer is wiped in a `finally` (backup key, master key, DEK, password buffers). The export temp is O_EXCL/O_NOFOLLOW at 0o600, fsynced, then renamed, then the directory is fsynced.
- **INV-13:** the compat value recorded in the manifest is applied on open and written to the new sidecar.
- **INV-5:** the move-aside carries the `-wal`/`-shm` siblings and is fsynced before the seam.
- **D4 / FIBR-0019:** one params object for the slot and the KEK, with a v2 sidecar.
- **INV-16:** restore refuses to run on an open vault.
- **FIBR-0033:** the reason table and the teardown.
- **FIBR-0030 § 3.2:** `StartOverDialog` gating (exact, case-sensitive match) and its accept/reject wiring.
- **Dimension 17:** MANIFEST_FORMAT_VERSION is kept separate from models.FORMAT_VERSION. `params.json` stays the v1 flat shape, which `load_and_validate_params` reads. An older backup is migrated up; a newer one is refused at two layers.

## Open questions

- Should a crafted manifest's TypeError count as "truly unexpected" under FIBR-0033 ("propagate — a bug")? I read it as a tamper class under FIBR-0014 INV-4.
- Is it acceptable that verify reports a newer-version backup as `invalid` ("isn't a valid finbreak backup")? It is spec-sanctioned (FIBR-0033 table), but the copy is misleading.

## 3 items to fix first

1. **The unhandled TypeError / RuntimeError on crafted `.fbk` input.** A hostile file on the pre-login restore path should never produce a traceback, and the fix is two lines.
2. **The retry-after-partial-install prune.** It is the only path in this lane that can destroy the original vault's recovery copy.
3. **The clock-backwards prune.** It shares the fix with item 2 (return the stamp from `_install` and prune relative to it), so both close together.