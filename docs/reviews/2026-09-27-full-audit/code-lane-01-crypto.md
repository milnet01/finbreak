I read the eight lane files in full: crypto.py (643 lines), keywrap.py (136), vault.py (409), db.py (38), loader_env.py (31), paths.py (55), services/recovery_code.py (173) and services/update_key.py (28). I found no Critical or High defects. The most serious finding is a Medium: a damaged recovery slot can lock the user out of their correct master password, which the code's own comment says must not happen.

**What I checked the code against:**
- FIBR-0019 § 4.1–4.7, § 5 INV-1–13, § 6, § 13.4 and § 13.5.
- `security-model.md` § 5.
- `docs/decisions/0009-sqlcipher-binding-package.md` lines 35–64.

**Not read:** ADR-0003, ADR-0011's body (outline only), and the other specs citing these modules (FIBR-0014, FIBR-0004, FIBR-0054, FIBR-0033, FIBR-0030).

**Not opened:** `~/.claude/standards/languages/python.md`, which the tail names as this lane's contract. So no finding here is judged against it.

**Search:** `workspace_search` hit its rate limit, so the last lookups ran through `Grep`. None of them touched `tests/`.

## Critical (0)

## High (0)

## Medium (3)

- **[dim 16] `crypto.py:594-602` — `slots[name] = SlotRecord(salt=bytes.fromhex(record["salt_hex"]), …)`, together with `:595-596` — `raise KdfPolicyError(f"slot {name!r} is missing a required field")`.**
  - A damaged optional slot refuses the whole sidecar, not just its own route. This happens when the recovery slot has bad or odd-length hex, a non-string value, a missing field, or is not a dict.
  - The error is raised inside the slot-parsing loop, or caught at `:616` and re-raised as `KdfPolicyError`. That happens before the "optional slot" tolerance at `:621-641` runs.
  - The user is then refused their correct master password. The comment at `:625-630` says that must never happen ("a damaged `recovery` slot would otherwise lock a user out of their own correct password").
  - The same path breaks the future-proofing. A later build adding a slot with a different field set (FIBR-0020 biometric, and `slots` is "an open map", § 4.1) makes every older build refuse the vault.
  - Which side is wrong: the code. § 6's "refusing that route only" row names only wrong lengths, but the code's own stated intent covers structural damage.
  - Fix: parse each slot other than `master` in its own `try`. Keep a slot that fails in its raw form in `extra`, or put it in a separate `damaged` map so it is still written back. Hard-fail only on `master`.

- **[dim 17] `vault.py:323-324` — `if cipher_compat is not None: conn.execute(f"PRAGMA cipher_compatibility = {int(cipher_compat)}")`.**
  - A vault created fresh never records a cipher level. § 4.4 says it "takes the library default", so every live connection opens at whatever defaults the installed SQLCipher has.
  - `vault.py:26-33` names exactly this risk for backups ("a sqlcipher3-wheels bump that changes the page/HMAC/KDF-iter defaults"), and pins it there. The live vault gets no such pin.
  - Only HMAC-on is pinned (`:333`). Page size and HMAC algorithm are not.
  - So a future library whose defaults move (SQLCipher 5) would make every freshly created vault fail to open, after an ordinary upgrade.
  - Which side is wrong: the code's exposure, though the spec documents the behaviour. See Open questions.
  - Fix: write `cipher_compatibility: SQLCIPHER_COMPAT` into the v2 sidecar at creation. Or have `_connect` apply `SQLCIPHER_COMPAT` whenever the sidecar carries no level.

- **[dim 16] `paths.py:25-28` — `location = QStandardPaths.writableLocation(...)` / `directory = Path(location)`.**
  - Qt documents that `writableLocation` returns an empty string when the location cannot be determined. `Path("")` is `.`, the working directory.
  - `data_dir()` would then run `os.chmod('.', 0o700)` on an arbitrary directory (`:37`) and put the vault and sidecar there.
  - Fix: raise if `location` is empty, and check that it is absolute.

## Low / Info

- **[dim 9] `crypto.py:232-237` and `:605-609` — `format_version=int(data["format_version"])`, `key_len=int(data["key_len"])`.**
  - `int()` quietly accepts `true`, `"32"` and `32.9`, so a hand-edited sidecar with `"key_len": 32.9` passes the "exact-format match" INV-2 requires.
  - Same leniency at `:611`: `bool(data.get(MIGRATION_PENDING_FIELD, False))` reads the string `"false"` as True.
  - Fix: require `type(v) is int` (and `is bool` for the flag).

- **[dim 16] `vault.py:309-346` — the `_connect` body.**
  - If any PRAGMA after `dbapi2.connect` raises (for example `cipher_compatibility`), `conn` is never closed.
  - On Windows the stray handle can block the later rename or delete during restore and reset.
  - Fix: wrap the PRAGMA block in `try/except: conn.close(); raise`.

- **[dim 3] `vault.py:355` — `f"PRAGMA rekey = \"x'{new_key.hex()}'\""` and `:384` — `f"ATTACH DATABASE ? AS backup KEY \"x'{backup_key.hex()}'\""`.**
  - Each builds a hex copy of a key as a Python string that cannot be wiped.
  - `security-model.md` INV-3's accepted-residual list names only `vault._connect`'s string. It says "Creating a new one is a breach, not a fifth residual".
  - Likely the document's side: add `rekey` and `export_to` to the residual list.
  - Unexecuted: whether sqlcipher3's statement cache keeps the SQL text (and so the key) for the connection's life, which would make "transient" (`:314`) inaccurate. Needs a check against the module's source.

- **[dim 2] `update_key.py:5-9` — "Until that keygen runs, `RELEASE_PUBLIC_KEY_B64` holds a **valid** base64 of 32 zero bytes …".**
  - Stale: `:22` now holds the real key.
  - The document (the docstring) is the wrong side. Fix: delete the interim paragraph.

- **INFO: zombie check (dim 2b).** Every entry point a contract names in this lane has at least one caller outside the tests, so there are no zombie features. Checked:
  - `validate_untrusted_params`, `validate_slot`, `restore_system_loader_env`, `public_key`
  - `generate_code`, `verify_check_symbol`, `decode_payload`, `PAYLOAD_INPUT_SYMBOLS`
  - `fsync_dir`, `old_copy_sets`, `restore_assembly_dirs`, `without_slot`, `SQLCIPHER_COMPAT_ACCEPTED`

  No test-tree counts were needed.
- **One-line answers for the rest:**
  - dim 4: nothing found.
  - dim 5: nothing found.
  - dim 7: nothing found. `fsync_dir`'s swallow is documented best-effort and logged.
  - dim 8: nothing found in this lane.
  - dim 10: nothing found. The only log line (`crypto.py:641`) logs a slot name, not a secret.
  - dim 11: nothing found beyond the Windows no-ops that are already documented (`O_NOFOLLOW`, `fchmod`, directory `chmod`).
  - dim 12: N/A.
  - dim 13: N/A, no user-facing strings in this lane.
  - dim 15: nothing found.
  - `db.py`: nothing found.

## Covered by spec and looks correct

- **`recovery_code.py` against § 4.3:**
  - 135-bit `randbits`, 27 × 5 bits.
  - Check alphabet of 37 symbols (`*~$=U` at values 32–36, matching Crockford), taken mod 37 of the payload integer.
  - `normalise` strips only whitespace, hyphens and case.
  - I/L/O fold in both the payload and the check value.
  - `decode` returns the 17-byte big-endian payload without the check symbol. The known trap holds: `auth.py:379` feeds `decode(normalise(code))`, not the text.
- **`keywrap.py` against § 4.2 and INV-3d:**
  - The AAD string is exact.
  - 12-byte random nonce per wrap, and a 48-byte wrapped value.
  - One undifferentiated `KeyUnwrapError`.
- **`crypto.py` against INV-2 and § 4.4:**
  - Separate floor and pin constants.
  - Floor of 1 on time and parallelism.
  - Both salt legs are checked.
  - `params_for` always sets `FORMAT_VERSION` (1), per the trap.
  - Dispatch is on whether `sidecar_version` is present.
  - Unknown keys survive a read-modify-write.
  - `write_sidecar_json` does `O_NOFOLLOW`, 0600 plus `fchmod`, fsync, `os.replace`, then a directory fsync.
- **`vault.py`:**
  - PRAGMA order in `_connect`: key, then compat, then HMAC.
  - `create` pre-creates the file `O_EXCL` 0600 and writes the database before the sidecar.
  - `open` does its guard read before switching to WAL, and `migrate=False` skips migrations.

## Open questions

- **What I arrived holding:**
  - The global, `/mnt/Games` and finbreak `CLAUDE.md` files. The finbreak one includes the key-envelope module-map note and the recovery-route trap.
  - finbreak's MEMORY.md index.
  - A git snapshot at HEAD 52e5162.
- **Is a fresh vault taking the library default intended (Medium 2)?** § 4.4 states it as fact. I cannot tell whether that was a deliberate trade-off or an unexamined consequence.
- **Does the Medium 1 fix need a spec change?** Should a structurally malformed optional slot count as § 6's "slot RECORD is well formed" case (refuse that route only)? § 6 names only lengths.
- **Does `loader_env.py:27-30` drop a user's own `LD_PRELOAD`?**
  - It deletes `LD_PRELOAD` whenever `LD_PRELOAD_ORIG` is absent.
  - If the PyInstaller bootloader never touches `LD_PRELOAD` (my understanding is it saves only `LD_LIBRARY_PATH_ORIG`), then a pre-launch `LD_PRELOAD` the user set is dropped from children. That contradicts the docstring's "back to its pre-launch value".
  - Unexecuted: needs checking against the bootloader's source.
- **Does a HashingError escape the backup path?** Could a crafted `.fbk` at the 1 GiB / t=16 ceiling raise Argon2's allocation `HashingError` in `backup.py`, whose except tuple I did not read? That is outside this lane's files.

## 3 items to fix first

1. **The recovery-slot parsing (Medium 1).** A corrupt optional recovery slot, or a slot a newer build adds, locks the user out of a correct password over an intact vault. That is exactly the outcome the code says it prevents.
2. **Pin the live vault's cipher level (Medium 2).** An ordinary library upgrade could make every freshly created vault unopenable. The same risk was already fixed for backups.
3. **Refuse an empty `writableLocation` (Medium 3).** It is a one-line guard, and it stops the vault landing in, and changing the permissions of, whatever directory the app was started from.