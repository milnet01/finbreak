## Chunk T03 — 4 files read

**Subject line counts as read:** `tests/features/backup/test_backup.py` 2000 (Read reported 2001 total, counting the trailing newline); `tests/features/backup/test_backup_ui.py` 695; `tests/features/vault/test_vault.py` 1259; `tests/features/vault_reset/test_vault_reset.py` 456.

**What I had in context before reading:**
- `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md` and the finbreak `CLAUDE.md`.
- The finbreak memory index.
- A git snapshot: clean `main`, HEAD 52e5162, with recent FIBR-0331 commits.
- The shared-context file, read once.

I read the subject files from disk.

**Tools:** I hit one `workspace_search` rate limit and did that search with `Grep` instead. No brief/review-lane disagreement came up.

**Code I opened (one hop):**
- `services/backup.py`: `export_backup`, `restore_backup`, `verify_backup`, `_open_backup_vault`, `_guard_manifest`, `_read_fbk`, `_read_capped`, `_write_fbk`
- `services/auth.py`: `complete_first_run`
- `crypto.py`: `load_and_validate_params`
- `ui/main_window.py`: the backup-export handler, `_save_geometry` and `closeEvent`
- `tests/conftest.py`: the autouse fixtures

### Findings

**[HIGH] [dim 6] tests/features/backup/test_backup_ui.py:601** (and the same pattern at :671)
> monkeypatch.undo()

Consequence: pytest's `monkeypatch` is one object per test, shared by every fixture that asks for it. Here that includes the autouse `window_ini` fixture (`conftest.py:129`, which points the window INI at a tmp file) and `_neutralise_category_library` (`conftest.py:150`). `undo()` removes both mid-test.
- **Line 601:** the `MainWindow` built at :608 then reads the real per-user INI: geometry, theme, unlock-throttle state and password hint. At qtbot teardown its `closeEvent` calls `_save_geometry` (main_window.py:1936), which writes geometry, state and size into the real per-user data directory. The conftest docstring names that as `~/.local/share/finbreak/window.ini`. `tests/conftest.py` has no `setTestModeEnabled`.
- **Line 671:** the window built before the `undo()` in the `finally` is closed at teardown after the redirect is gone, so it also writes to the real INI.

Fix: scope the `os.replace` / `os.fsync` patches in a `with pytest.MonkeyPatch.context() as mp:` block (or undo only those attributes) and never call `undo()` on the shared fixture.

**[HIGH] [dim 1] tests/features/vault/test_vault.py:1045**
> assert KEY_LEN in wiped, "the derived key copy is wiped even when the guard fires"

Consequence: on the guard path, `complete_first_run` wipes two 32-byte buffers — `_wipe(dek)` in its `except` and `_wipe(kek_master)` in its `finally` (auth.py, `complete_first_run`). The DEK wipe alone makes `KEY_LEN in wiped` true. So deleting the `_wipe(kek_master)` that this test exists to lock leaves it green.

Fix: have the spy record `bytes(buf)` before wiping, and assert that some entry equals `b"\x01" * KEY_LEN` (the raw key copy).

**[MEDIUM] [dim 1] tests/features/backup/test_backup.py:1093**
> zf.writestr(
>     "manifest.json", b"\xff\xfe not valid utf-8"
> )  # -> UnicodeDecodeError

Consequence:
- `b"\xff\xfe"` is the UTF-16-LE byte-order mark, so `json.detect_encoding` picks `utf-16`.
- The 16 bytes after it decode cleanly to 8 non-surrogate code units, so `json.loads` raises `JSONDecodeError`, not `UnicodeDecodeError`.
- Removing `UnicodeDecodeError` from `_read_fbk`'s except tuple leaves this test green; the non-UTF-8 branch its comment claims is never reached.

Fix: use invalid UTF-8 with no BOM (e.g. `b'{"a": "\xff"}'`), or assert that `__cause__` is a `UnicodeDecodeError`.

**[MEDIUM] [dim 1] tests/features/backup/test_backup.py:1050**
> with pytest.raises(BackupError):
>     BackupService(auth.vault, auth).restore_backup(bad, _BACKUP_PW, _M2)

(This is `test_INV13_wrong_cipher_compat_refused`, with the manifest set to `sqlcipher_compat: 3`.)

Consequence: without the `_guard_manifest` allowlist, `_open_backup_vault` passes `cipher_compat=3` to `Vault.open` on a compat-4 database. Page 1 then fails with `DatabaseError`, which `restore_backup` turns into `BackupError`. The live directory is untouched either way, because assembly happens in a temp dir. So the test passes with the INV-13 guard removed. This is the "a negative test only proves what it breaks" trap.

Fix: record `on_key` roles and assert that no `"backup"` key was derived, as `test_INV11_below_floor_params_refused_before_any_key` does, or `match="cipher-compatibility"`.

**[MEDIUM] [dim 1] tests/features/backup/test_backup_ui.py:141**
> assert fired == [], "the queued 1 ms timer cannot fire during a blocking export"

Consequence: no event loop runs during any plain Python call, so `fired == []` holds right after `export_backup` returns whether or not the export ran synchronously. An export moved to a worker thread would return at once, leave the timer unfired, fire it in `qtbot.wait(20)`, and pass both assertions. Only an export that calls `processEvents` fails this test. INV-9's "synchronous on the main thread" claim is not checked.

Fix: inside `slow_export_to`, assert `threading.current_thread() is threading.main_thread()`, and assert the `.fbk` exists and is complete when `export_backup` returns.

**[MEDIUM] [dim 1] tests/features/backup/test_backup_ui.py:177**
> # The restored data is present (the source's single seeded account survived).
> assert (dest / "vault.db").exists() and (dest / "vault.kdf.json").exists()

Consequence: the destination was empty, so any install creates both files. A restore that installed a fresh empty vault under the new master would pass this assertion and the `service._key is not None` one at :174. The data-survival claim in this end-to-end shell path is not checked.

Fix: query the unlocked vault for the source's seeded row (or compare a table snapshot), as `test_INV2_restore_reproduces_every_table` does.

**[MEDIUM] [dim 1] tests/features/vault_reset/test_vault_reset.py:436**
> wal.write_bytes(b"an outstanding write-ahead log")
> auth.lock()

Consequence: the orphan WAL is planted while the connection is open, then `lock()` closes it. This chunk's own files say a clean close removes the `-wal`: vault_reset:44 ("SQLite checkpoints+deletes the real -wal/-shm") and test_backup.py:1385–1401 ("let the clean close remove it"). If that happens here, `wal` is gone before `reset_vault()` runs, and `assert not wal.exists()` passes whatever the unlink order. No precondition asserts that the WAL is present at reset time.

Fix: plant the WAL after `auth.lock()`, as `test_INV1_complete_footprint_deletion` does, and assert `wal.exists()` before calling `reset_vault()`.

**[MEDIUM] [dim 12] tests/features/backup/test_backup.py:941**
> zf.writestr(
>     "vault.db", b"\0" * MAX_BACKUP_DB_BYTES, compress_type=zipfile.ZIP_DEFLATED
> )

Consequence: measured at 2.11 s. Sibling tests that do the same `_export_from_seed` + `_dest_with_vault` work run in ≤1.0 s, so the extra time is this line: a 512 MiB allocation in the test process, then deflating it. On a RAM-constrained machine that is also a large transient memory spike.

Fix: monkeypatch `backup_mod.MAX_BACKUP_DB_BYTES` down to a few MiB and build the bomb at that size. `_read_capped`'s caller reads the module global at call time (`_read_fbk`), and zeros still compress about 1000:1, so the ratio gate is still what fires.

**[LOW] [dim 1] tests/features/backup/test_backup.py:891**
> {"../evil.txt": b"traversal"},

Consequence: `_read_fbk` first compares the sorted entry names against the exact three-name set, so a fourth entry of any name is refused there. The `name != os.path.basename(name)` / `".."` check is never reached. Deleting the traversal check leaves the `traversal` case green; it proves the same thing as `extra-entry`.

Fix: drop the claim implied by the `traversal` id, or note that the entry-set gate is what refuses it.

### Pre-pass verdicts
- **test_backup_ui.py:133 `sleep_call` (dim 5): false positive for flakiness.** The sleep is the thing being blocked on, not a wait for a condition. No assertion races it, and `qtbot.wait(20)` processes an already-overdue 1 ms timer, which is deterministic. The sleep is also inert: removing it changes nothing, which is part of the dim 1 finding at :141.

### Dimensions scanned
- 1: 7 findings
- 4: clean — settled by the orchestrator; I saw no duplicate test names in these files
- 5: clean — the only fixed wait (ui:336 `qtbot.wait(10)`) drains a `QTimer.singleShot(0)` posted before it (main_window.py:2121); every other wait is `waitSignal`
- 6: 1 finding — `test_INV13_restore_under_forced_different_process_default` changes a process-global PRAGMA but resets it in `finally`; the direct `auth_mod._wipe` / `write_sidecar_v2` assignments are restored in `finally`
- 7: clean — the random `_SENTINEL` is only compared with itself
- 8: clean — all three `skipif`s carry a reason and a live POSIX condition
- 9: no separate hit; the real per-user INI write is filed under dim 6
- 11: clean
- 12: 1 finding, plus 1 open question
- 14: clean — mocked layers match what each test claims (UI tests fake the service; the service tests use real SQLCipher); no warning filters, no broad `except`
- 15: N/A — nothing failing in this chunk

### Noted, not mine
- In `services/backup.py` `_read_fbk`, the unsafe-name check (`name != os.path.basename(name) or ".." in ...`) cannot be reached by any input, because the exact entry-set check runs first. That is for review-code.

### Possibly wider
- `monkeypatch.undo()` on the shared fixture in other suites would also silently lift `window_ini` and the category-library neutraliser.
- Other negative restore/verify tests outside this chunk that only assert `pytest.raises(BackupError)` may pass through a downstream failure (wrong-key page-1) rather than the guard they name.

### Open questions
- **Dim 12, `test_backup_ui.py::test_INV9_synchronous_export_blocks_queued_timer`, 2.13 s.** The two waits in the test add about 70 ms, and structurally similar export tests run in ≤1.0 s, so I cannot say what the remaining time is from reading. Needs `pytest --durations=0 --setup-show tests/features/backup/test_backup_ui.py -k INV9` to split setup from call.
- **test_vault_reset.py:436.** Whether SQLite actually removes the overwritten WAL on `lock()` here is unconfirmed: a checkpoint failure on garbage frames could keep the file. Confirm by adding `assert wal.exists()` just before `reset_vault()` and running `pytest tests/features/vault_reset/test_vault_reset.py -k failed_database_unlink`.
- **Dim 6 finding: where the real INI lands.** Under pytest, is `paths.window_settings_path()` `~/.local/share/finbreak/window.ini` (the path the conftest docstring names) or a pytest-named AppData directory? Either way it is outside `tmp_path`. Confirm with a run that prints the path after `undo()`.