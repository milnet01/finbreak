## Chunk T01 — 4 files read

**What I read:**
- `tests/features/recovery_key/test_migration.py`: 2719 lines
- `tests/features/recovery_key/test_sidecar_v2.py`: 775 lines
- `tests/features/recovery_key/test_envelope.py`: 411 lines
- `tests/features/recovery_key/_recovery_helpers.py`: 375 lines

**What I had in context before starting:** the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, finbreak's `CLAUDE.md`, the finbreak memory index `MEMORY.md`, and a git snapshot (clean `main`, HEAD 52e5162). I read the shared context once, as the brief said.

**How I read:**
- I read `test_migration.py` in four ranges, and each range starts and ends at a `def` boundary (1–581, 582–1162, 1163–1876, 1877–2719). I did this because the brief asked for reading by test function, not by arbitrary line range.
- One `workspace_search` was rate-limited. I used `Grep` for that search instead.
- I went one hop into the code under test: `vault_migration.py` STEPS / `step(...)` calls at 523–627 and `resume()` at 914–1014, and `crypto.py`'s reader definitions.
- My brief and the review-lane file did not disagree anywhere, so there was nothing to resolve.

### Findings

**[MEDIUM] [dim 1] tests/features/recovery_key/test_migration.py:130** (runs to :135)
> `try: migrate_to_v2(..., on_step=abort_before)` … `except _Abort: pass`

Consequence: nothing checks that the injected crash actually happened. If a step name in `STEPS` drifts from what `migrate_to_v2` passes to `step(...)`, or a step stops calling it, that leg runs a full migration without crashing. Its assertions still pass, because the vault opens and the rows match. The legs meant to cover crashes after S1 through S5 would then all be full-run tests, and nothing would say so. Today every step does fire (`vault_migration.py:523–627`), so the legs currently reach their states. The guard against drift is what is missing. Every other abort in this file uses `pytest.raises(_Abort)`, which does catch this.
Fix: record that the abort fired, and assert it did whenever `target is not None`. Use `pytest.raises(_Abort)` for those legs.

**[MEDIUM] [dim 1] tests/features/recovery_key/test_migration.py:1247**
> `assert seen_before_copy == [], (`

Consequence: `seen_before_copy` is only filled inside `watch_ensure`. Nothing asserts that `watch_ensure` ever ran. If branch 3 stopped calling `_ensure_rollback_copy`, the list stays `[]` and the test passes. Removing that call (today at `vault_migration.py:989`) is exactly the INV-13 regression this test is meant to catch. The sibling test at :1840 avoids this: `at_swap == [["ensure"]]` also proves the swap was reached.
Fix: record each `watch_ensure` call and assert it happened once, before checking `seen_before_copy`.

**[MEDIUM] [dim 1] tests/features/recovery_key/test_envelope.py:135** (leg 3, runs to :143)
> `assert not opens_with(migrated_vault, migrated_sidecar, bytearray(v1_key)), (`

Consequence: this is a negative check with no positive control. Two ways it passes wrongly:
- If `migrate_to_v2` left a database nothing can open, "the v1 key does not open it" is still true.
- `opens_with` calls `vault.open(key)` without the migrated sidecar's `cipher_compatibility`. The helper's own docstring (`_recovery_helpers.py:325–328`) says export and create agree on that level today and are expected to stop agreeing after a `sqlcipher3-wheels` bump. Once they differ, every key fails to open the migrated vault through this helper, and the leg passes for every key.

Fix: first assert that the migrated vault opens with its unwrapped DEK through `open_after_restart`, which passes `cipher_compat`. Then assert the v1 key does not open it.

**[LOW] [dim 1] tests/features/recovery_key/test_sidecar_v2.py:506**
> `with pytest.raises(KdfPolicyError): AuthService(vault_path, sidecar_path).complete_recovery_unlock(bytes(kek))`

Consequence: this negative test has no control. Nothing shows that `complete_recovery_unlock` with this KEK succeeds on the intact sidecar. If a regression made the recovery route raise `KdfPolicyError` for any v2 sidecar, the test stays green while the route is broken for every user. This is the shared context's § D trap ("a mutation or negative test only proves what it breaks").
Fix: unlock with the same KEK on the intact file first, then lock, then damage the slot and assert the refusal.

**[LOW] [dim 1] tests/features/recovery_key/test_envelope.py:262** (leg 3)
> `with pytest.raises(KdfPolicyError): load_and_validate_params(weakened_path)`

Consequence: same shape as above. No check that `load_and_validate_params` accepts the un-weakened v2 file first. If the loader refused every v2 sidecar, this leg would still pass, even though it claims to test the memory floor.
Fix: first write the pristine sidecar to `weakened_path` and assert it loads, then halve `memory_kib`.

**[LOW] [dim 1] tests/features/recovery_key/test_migration.py:1107**
> `with pytest.raises(OSError): write_rollback_copy(vault_path, sidecar_path)`

Consequence: `OSError` is broad, and nothing asserts that the symlink was actually planted at `copy_vault`. Any `OSError` raised before the copy is opened satisfies `raises`, and `elsewhere` is untouched either way. The test cannot tell "O_EXCL refused the symlink" from "the copy failed for an unrelated reason".
Fix: assert `copy_vault.is_symlink()` after the call. Narrow the expected error to `FileExistsError`, or check the errno.

**[LOW] [dim 1] tests/features/recovery_key/test_migration.py:1070**
> `mode = path.stat().st_mode & 0o777` / `assert mode == 0o600`

Consequence: whether this test can catch the defect depends on the process umask. The pre-fix code created files at the umask (docstring :1040). Under a umask of `077` it would produce `0o600` and pass, so the test only catches the regression where the umask is looser. The test never sets one.
Fix: set `os.umask(0o022)` for the test, restoring it in a `finally` or fixture, so a regression is visible whatever the runner's umask.

**[LOW] [dim 1] tests/features/recovery_key/test_migration.py:2545** (also :2596)
> `assert not any(ch.isdigit() for ch in message), (`

Consequence: the claim is that the row counts (`4242`, `1234`, `11`, `7`) stay out of the message. The assertion bans every digit instead. A correct message citing "S2" or "§ 13.3" would turn it red with no leak present. This errs toward a false red, not a false green.
Fix: assert that the specific counts the test injected (and the real counts) are absent.

**[LOW] [dim 1] tests/features/recovery_key/test_envelope.py:291**
> `if not isinstance(node.func, ast.Name) or node.func.id not in _WRAPPERS:`

Consequence: the static guard only matches bare-name calls. A future `keywrap.wrap_dek(bytes(kek), ...)` would pass leg 2, and `seen >= 8` would not notice. No such attribute call exists in `src/finbreak` today (I grepped for `\.(un)?wrap_dek\(` and found none), so this is a blind spot, not a current miss.
Fix: also match `ast.Attribute` nodes whose `attr` is in `_WRAPPERS`.

### Pre-pass verdicts
- None were supplied for this chunk.

### Dimensions scanned
- 1: 9 findings, above.
- 4: settled by the orchestrator (every `test_*` is collected, no shadowing). I did not re-derive it.
- 5: clean. No sleeps, no network, no threads. The byte flips at `10 * _PAGE_SIZE + 100` rest on the `pages > 12` checks.
- 6: clean. Every patch goes through `monkeypatch` or `MonkeyPatch.context()`, including the explicit `monkeypatch.undo()` calls at :861, :2382, :2710 and `test_sidecar_v2.py:583`. Every vault lives under its own `tmp_path` subdirectory.
- 7: clean. Random codes and DEKs reach an assertion only through `dek_one != dek_two` (collision chance about 2^-256). `code_with_check_symbol` and the synthetic decode pairs make the transcription leg deterministic.
- 8: clean. Two `skipif(os.name != "posix", reason=...)` markers, both with live conditions.
- 9: N/A. No external endpoints.
- 11: clean. No empty bodies.
- 12: N/A. No test in this chunk is in the slowest 20 (all ≤ 1.0 s).
- 14: clean. Each stubbed collaborator is outside the claim its test states: `_reads_end_to_end` at :1288, :1490, :2569; `_row_counts_or_none` at :1776, :2576; `resume` at :411; `migrate_to_v2` and `sidecar_version` at :2441–2444. Each docstring says the stub is deliberate.
- 15: none failing in this chunk (per the tail).

### Noted, not mine
- None.

### Possibly wider
- A negative assertion (`pytest.raises(KdfPolicyError)`, "does not open") with no positive control on the same input probably appears in other FIBR-0019 / FIBR-0310 suites outside this chunk.
- The blanket `not any(ch.isdigit() ...)` pattern may be reused in other INV-9 log-leak tests.
- File-mode tests elsewhere, such as the backup `_write_owner_only` tests, may share the umask dependence.

### Open questions
- Findings 1 and 2 would be confirmed by mutation, which I cannot run. Rename one `step("S3")` call in `vault_migration.py`, then remove the `_ensure_rollback_copy` call at `vault_migration.py:989`, and run `pytest tests/features/recovery_key/test_migration.py -k "every_crash_point or branch_3_does_not_write"`. I expect both to stay green. Unexecuted.
- `test_migration.py:1070`: the umask at CI time needs checking inside `python:3.12-slim-bookworm`, e.g. `umask` in `ci-docker.sh`. If it is `077` anywhere the suite runs, the test cannot catch the regression there.
- `test_migration.py:816` (`test_restore_rollback_copy_fsyncs_the_directory`) reads `/proc/self/fd`, which exists only on Linux, and has no skip. This matters only if the suite ever runs on macOS or Windows; I cannot tell from here whether it does.