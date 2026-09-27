Lane 02: authentication, unlock throttle, password hint and strength, and the single-instance guard. Depth pass.

**Subject line counts as read:** `services/auth.py` 1002 · `services/unlock_throttle.py` 68 · `services/password_hint.py` 54 · `services/password_strength.py` 87 · `single_instance.py` 215.

**What was already in my context on arrival:**
- `~/.claude/CLAUDE.md`
- `/mnt/Games/CLAUDE.md`
- finbreak's `CLAUDE.md`, whose module map names the recovery-route trap
- finbreak's `MEMORY.md` index
- a git snapshot (HEAD `52e5162`, clean tree)
- the shared context file

I read the subject from disk. I opened no test files. I did read `tests/features/single_instance/spec.md`, which is a contract document, as the brief allows. `workspace_search` hit a rate limit once; after that I used `Grep`, scoped to `src/` and `docs/`.

## Critical (0)

## High (0)

## Medium (3)

- **[dim 8] `single_instance.py:193-199`** with `app.py:146-147`
  - Quote: `if not claimed: ... return None` in `listen`, then `if guard is None and single_instance.another_instance_is_running(guard_name): return 0` in `app.py`.
  - Defect: INV-3b says a launch that loses the recovery claim stands down, but it doesn't. It returns `None`, and `app.py` then probes again straight away. The launch holding the claim may still be between its own re-probe, `removeServer` and `listen()`, so it is not bound yet. The loser's probe then fails (connection refused on the stale file, or no file at all) and the loser runs "fail-open".
  - Result: two instances on one SQLCipher file. That is the INV-3a hazard, reached exactly in the scenario INV-3b was written for (two launches meeting one crash leftover).
  - Timing-dependent. Not executed — it needs a two-process race harness.
  - Fix: return three states from `listen` (owner / stand down / fail-open) and have `app.py` exit on stand down. Or make the loser wait on the claim (blocking `flock` with a timeout) and probe again after that.

- **[dim 7] `auth.py:580-592`**
  - Quote: `except Exception: log.exception("key-envelope migration failed")`, then `return self._open_with(key, None)`.
  - Defect: a failed v1→v2 migration is swallowed. The user gets an ordinary unlocked session and no signal. `_just_migrated` stays False and the method returns only `True`.
  - FIBR-0019 § 6 (rollback-copy row) requires: "Abort before S1 … **report it** and let the user free space and retry". `design.md` § Error handling says nothing is silently swallowed, and `python.md` says catch what you can name.
  - On a full disk, every later unlock silently repeats S0: a whole-vault copy plus an integrity check, failing each time, with the recovery key never offered.
  - The code is the wrong side here.
  - Fix: catch the migration's named errors and return the failure to the caller (a flag or a result the shell reads, like `consume_migration_notice`) so the UI can say it.

- **[dim 16] `unlock_throttle.py:67-68`**
  - Quote: `elapsed = (now - last_fail).total_seconds()` / `return max(0.0, delay - elapsed)`.
  - Defect: if `last_fail` is in the future (clock moved back, or a stamp edited far forward), the wait grows with the skew and has no upper limit. Because the UI refuses to derive while `remaining > 0` (FIBR-0095 INV-6), even the correct password cannot be tried until the clock catches up.
  - This breaks security-model INV-10: "The delay is capped … the legitimate owner is never permanently locked out."
  - The code does exactly what FIBR-0095 INV-3/D5 say ("`now < last_fail` → result `> delay(n)`"), so the two documents disagree. See Open questions.
  - Fix: treat a future `last_fail` as `now`. That owes the full `delay(n)`, which is at most 30 s and still fail-safe. It needs a matching amendment to FIBR-0095 INV-3.

## Low / Info

- **[dim 3] `auth.py:596`**
  - Quote: `sidecar = read_sidecar_v2(self._sidecar_path)` sits before the `try/finally: _wipe(key)` at 597-605.
  - `key` is the v1 database key, which § 13.1 makes KEK-master. If this read raises after a successful migration, the key is never wiped. That is an INV-3 breach on an error path; every other exit from `_unlock_v1` wipes.
  - Fix: move the read inside the `try`.

- **[dim 16] `auth.py:667-668`** (same shape at `314-315`)
  - Quote: `self._key = key` / `self._arm_timer()`.
  - `_arm_timer` reads `settings` through the database. If that read raises (for example a damaged settings page), the service holds the key and an open connection, but its caller sees an exception and the idle timer is never armed.
  - Not executed.
  - Fix: arm inside a `try` that locks on failure, or arm before taking ownership.

- **[dim 7] `auth.py:714-719`, `785-790`**
  - Quote: `self._vault.close()` runs before `_wipe(self._key)`.
  - If `close()` raises (`vault.py:295-298` is a bare `self._conn.close()`), the key is neither wiped nor cleared. Rare. Not executed.
  - Fix: wipe in a `finally`.

- **[dim 3] `single_instance.py:136`**
  - Quote: `os.open(_claim_path(name), os.O_CREAT | os.O_RDWR, 0o600)`.
  - On the fallback path (`XDG_RUNTIME_DIR` unset) the file is a predictable name in `/tmp`, opened without `O_NOFOLLOW`. Another local account can pre-create it or hold its `flock`. That denies the claim and feeds the Medium race above.
  - The kernel settings `fs.protected_symlinks` and `protected_regular` reduce the impact where they are on.
  - Fix: add `O_NOFOLLOW`, and check the file's owner after `fstat`.

- **[dim 11] `single_instance.py:76-77, 95-96`**
  - Quote: "Windows named pipes are already per-session, so the bare base name is correct there."
  - As far as I know, the named-pipe namespace on Windows is machine-wide, not per-session. `uid` is `None` on Windows, so every signed-in user uses `finbreak`.
  - With fast user switching or Remote Desktop, a second user either runs unguarded, or, depending on the default pipe permissions, their probe connects and they exit 0. That is the INV-4 denial-of-service shape.
  - Not executed — it needs two Windows sessions. Fix: add the user's SID or name to the pipe name.

- **[dim 2] `auth.py:91-95`**
  - The comment says "the INV-1 fallback resolves to index 0 (the 1-minute floor)". FIBR-0055 INV-1, and the code at `833-837`, fall back to `DEFAULT_AUTO_LOCK_MINUTES` (10).
  - Behaviour is correct; the comment is wrong. Fix: reword it.

- **The remaining dimensions:**
  - dim 4: no diverged duplication found.
  - dim 5: none. The backoff exponent is clamped at `CAP_N`.
  - dim 9: sidecar writes all go through `write_sidecar_v2` (atomic; not in this lane).
  - dim 10: log lines carry no secrets (INV-9 holds for the lines in these files).
  - dim 12: N/A.
  - dim 13: these files hold no user-facing strings apart from `HintPolicyError` and `password_strength`'s advice. Those are not `tr()`-wrapped at source, so whether they reach the UI untranslated is the UI lane's to check.
  - dim 15: nothing leaves the machine.
  - dim 17: v1→v2 migration is covered above.
  - dim 2b: no zombies. Every contract-named entry point has a non-test caller in `src/finbreak/ui/` or `app.py`: `consume_migration_notice`, `suspend/resume_idle_lock`, `recovery_params`, `complete_recovery_unlock`, `set_master_password`, `remove_recovery_key`, `restore_pre_upgrade_copy`, `notify_activity`, `assess`, `has_recovery_key`, `verify_password`, `add_recovery_key`, `validate_hint`, and the `single_instance` functions.

- **INFO:** I did not read `vault_migration`, `crypto` or `keywrap` beyond `wrap_dek`'s body. `wrap_dek`'s `bytes(dek)` is the accepted fourth residual under security-model INV-3.

## Covered by spec and looks correct

- **Known trap, confirmed:** Argon2id is fed the decoded 17-byte payload, never the text. `add_recovery_key` does `bytearray(decode(normalise(code)))` at `auth.py:379`; the unlock route does `bytearray(decode(normalised))` in `ui/unlock.py`. The check symbol is verified before the throttle counts an attempt, per § 4.6 step 1.
- `complete_first_run` follows § 4.5's order: vault create without the sidecar, then the v2 sidecar with `slots.master` only, and the recovery slot deferred to Keep. The key is wiped on every failure path, including the guard for an existing vault.
- `_unlock_through_slot` does not tell `KeyUnwrapError` causes apart, keeps `validate_slot` as a separate error, and runs `resume` only from the master slot.
- `_open_with` checks the cipher-compatibility value against an allowlist and raises `VaultStateError` rather than reporting a wrong password (§ 6).
- `verify_password` unwraps before comparing on v2 and uses `hmac.compare_digest` (FIBR-0029 INV-5).
- `password_hint.validate_hint` matches FIBR-0029 § 3.4 line for line: length, then equality, then unconditional containment, all after NFC plus casefold.
- `backoff_delay_seconds` matches FIBR-0095 INV-1, including the exponent clamp.
- `password_strength` is advisory only, and its callers are first-run and the forced reset (T2).
- `reset_vault` removes the WAL siblings before the database and also removes migration artefacts, `.old` sets and assembly directories (INV-12).
- `listen`'s stale-socket recovery keeps a live owner's socket (INV-3/3a) on the single-launch path.

## Open questions

1. The throttle under a clock that moved back: security-model INV-10 ("capped", "never permanently locked out") and FIBR-0095 INV-3 ("result > delay(n)") contradict each other. The code follows FIBR-0095. Which document governs is for `review-contract`; I am not picking.
2. Is the Windows pipe name per-user in practice? That depends on the default permissions Qt's `QLocalServer` gives the pipe on Windows. I could not settle it without running it.
3. `has_recovery_key` catches only `VaultStateError` and `KdfPolicyError`. I did not check whether `sidecar_version` or `read_sidecar_v2` can raise anything else, such as `OSError` on a missing or unreadable sidecar.
4. The idle timer stays live during the forced new-password dialog after a recovery unlock (`ui/recovery_key.py` handles the resulting `VaultLockedError`). An idle lock there leaves the old, forgotten password in `slots.master`. The recovery code still works, but INV-9's intent is arguably weakened. This is outside my lane.

## 3 items to fix first

1. **The single-instance claim-loser race** (`single_instance.py:193-199` / `app.py:147`). It produces the exact outcome the guard exists to prevent — two writers on the money vault — and it needs no attacker, only a double-click after a crash.
2. **Silent migration failure** (`auth.py:580-592`). The user is never told their vault did not convert and has no recovery key. On a full disk every unlock quietly repeats a full-vault copy, against § 6's explicit "report it".
3. **Unbounded throttle wait on a clock skew** (`unlock_throttle.py:67-68`). The legitimate owner can be locked out for as long as the clock is wrong, breaking INV-10's promise. The fix is small, but it has to land together with the FIBR-0095 amendment.