# tests/features/recovery_key — FIBR-0019 master-password recovery key

Conformance tests for
[`docs/specs/FIBR-0019-master-password-recovery-key.md`](../../../docs/specs/FIBR-0019-master-password-recovery-key.md).
Each `INV-N` below is that design spec's invariant of the same number; the
`Test:` clause names the function that enforces it, exactly as § 10 of the
design spec maps them. Five files, one per concern (§ 7).

**Theme:** the vault stops being encrypted by a password-derived key and is
encrypted instead by a random **data key (DEK)**, stored twice over — wrapped
once under a key derived from the master password and once under a key derived
from a recovery code the user was given at vault creation. Either credential
opens the same data; neither the app nor anyone holding the vault file can open
it without one of the two.

Every on-disk vault lives under `tmp_path`. No test touches the network, and
every credential, account and transaction here is synthetic
([`testing.md`](../../../docs/standards/testing.md) § 6, security-model INV-6).

## Invariants

- **INV-1** — The installed vault's SQLCipher raw key is a random DEK, never a
  value derived directly from a credential. **Scope: `vault.db` in the
  application data directory** — it does not fire on the `vault.db` *inside* a
  `.fbk`, which keeps its `derive_key(backup_password, …)` schedule.
  *Test:* `test_envelope.py::test_dek_is_not_derived_from_any_credential` —
  two legs. First, derive KEK-master and assert the vault does **not** open with
  it. Second, and this is the one that bites: two vaults created with the
  **same** master password must hold **different** DEKs. Without the second leg
  the test passes under § 8.1's rejected design, where the legacy Argon2id
  output *is* the DEK wrapped under a freshly salted KEK — so the implementation
  the design most wants to exclude would ship green.
  Source: FIBR-0019 INV-1.

- **INV-2** — Both slots unwrap to the same DEK, and either alone opens the
  vault.
  *Test:* `test_envelope.py::test_both_slots_yield_the_same_dek` — unwraps each
  slot independently, asserts the bytes are equal, and opens the vault once per
  route. A third leg re-types the code in lower case with `I`/`O` substituted
  for `1`/`0` and asserts it still opens — the transcription property § 4.3
  chose Crockford for, and the leg that fails if the KDF is fed the normalised
  **text** instead of the decoded 17 big-endian bytes.
  Source: FIBR-0019 INV-2.

- **INV-3** — Wrapping is authenticated: any modification to a slot fails
  closed.
  *Test:* `test_envelope.py::test_tampered_slot_fails_closed` — four legs. Flip
  one bit in `wrapped_dek_hex`; flip one in `nonce_hex`; lower `kdf.memory_kib`
  and assert **`KdfPolicyError`** (not `KeyUnwrapError` — `ARGON2_MEMORY_FLOOR_KIB`
  equals the pinned `ARGON2_MEMORY_KIB`, so `validate_params` refuses any
  lowering before `unwrap_dek` is reached); and rename `recovery` to `master`,
  then unwrap it with KEK-**recovery**, asserting `KeyUnwrapError`. Only the
  fourth leg tests the AAD, and unwrapping with KEK-*master* would not: the slot
  keeps the recovery salt, so the key is simply wrong and the leg would pass
  against an implementation whose AAD is `b""`.
  Source: FIBR-0019 INV-3.

- **INV-4** — The sidecar holds no unwrapped key material, no password and no
  recovery code.
  *Test:* `test_sidecar_v2.py::test_sidecar_holds_no_unwrapped_secret` — pins
  the v2 field set exactly **for a vault created fresh** (a mid-migration one
  legally carries `migration_pending`, any migrated one carries
  `cipher_compatibility`), then asserts no value anywhere in the file contains
  the DEK, either KEK, the master password or the recovery code, in hex, base32
  or raw-bytes form. `wrapped_dek_hex` is ciphertext and belongs there.
  Source: FIBR-0019 INV-4.

- **INV-5** — The recovery code is never persisted by the application **of its
  own accord**, in any form, to any plaintext surface. The single exception is
  the file the user explicitly names at the moment of display.
  *Test:* `test_recovery_code.py::test_code_never_reaches_a_plaintext_surface` —
  creates a vault, writes the code to a path the **test itself** supplies as the
  user's choice, then walks every file under the data directory and asserts
  exactly that one file holds it. `vault.db` and its WAL siblings are excluded
  deliberately: the vault is encrypted, so a plaintext search of it cannot fail,
  and a leg that cannot fail is not evidence.
  Source: FIBR-0019 INV-5.

- **INV-6** — The check symbol is a typo detector and carries no security
  weight.
  *Test:* `test_recovery_code.py::test_valid_check_symbol_does_not_authenticate`
  — constructs a code with a **correct** check symbol over a **wrong** payload,
  asserts it passes the local check (the precondition, or the legs below are
  vacuous), and that it still fails to unwrap and still fails to open the vault.
  Source: FIBR-0019 INV-6.

- **INV-7** — Migration is atomic: at every instant, either the pre-migration
  pair or the post-migration pair opens with the user's password. There is no
  window where neither does.
  *Test:* `test_migration.py::test_every_crash_point_still_opens` — runs the
  § 13 sequence against a real vault, aborting after each of S1..S6 in turn, and
  asserts a fresh app start opens it with the original password every time, with
  every row intact.
  Source: FIBR-0019 INV-7.

- **INV-8** — Migration preserves every row of every table.
  *Test:* `test_migration.py::test_migration_preserves_every_row` — seeds a
  vault, records per-table row counts and an ordered digest of each table's
  contents, migrates, and asserts both are unchanged. The digests are taken over
  **every** table enumerated from `sqlite_master`, not only the seeded ones, so
  a migration that drops a table nothing seeded is still caught.
  Source: FIBR-0019 INV-8.

- **INV-9** — A recovery unlock leaves the vault with a working master password
  before the main window is reachable.
  *Test:* `test_recovery_unlock.py::test_recovery_unlock_forces_a_new_master_password`
  — unlocks by code, asserts `unlocked` is not emitted until a new password is
  set, then re-opens the vault with the new password and asserts the old one no
  longer unwraps `slots.master`.
  Source: FIBR-0019 INV-9.

- **INV-10** — The recovery route is throttled by the same counter as the
  password route.
  *Test:* `test_recovery_unlock.py::test_recovery_attempts_share_the_password_backoff`
  — exhausts the password allowance and asserts a recovery attempt is refused by
  the same backoff (no worker spawned, a countdown shown); and the reverse, that
  a failed recovery attempt advances the counter the password route reads. **Not**
  an assertion about instance identity: `UnlockThrottle` is stateless beyond
  `window.ini` and opens a fresh `QSettings` per method, so two instances share
  the counter by construction and such an invariant would test nothing.
  Source: FIBR-0019 INV-10.

- **INV-11** — A stored password hint may contain neither the master password
  nor the recovery code.
  *Test:* `test_recovery_code.py::test_hint_rejects_the_recovery_code` — asserts
  a hint containing the real code is rejected, a hint containing a well-formed
  but *wrong* code is accepted, and a hint containing no candidate performs no
  derivation at all. The hint must be **normalised before** the 28-symbol scan:
  the user holds the code as `A1B2-C3D4-…`, whose longest unbroken symbol run is
  four, so scanning the raw text finds no candidate and cheerfully accepts a hint
  that *is* the recovery code. Also asserts `validate_hint(hint, password)` keeps
  its two-argument signature — the trial-unwrap is the caller's, in
  `ui/_password_hint.py`, because `services/password_hint.py`'s contract is to be
  pure.
  Source: FIBR-0019 INV-11.

- **INV-12** — Declining a recovery key still builds the envelope.
  *Test:* `test_sidecar_v2.py::test_declining_still_writes_the_envelope` —
  creates a vault while declining, asserts `sidecar_version == 2` with
  `slots.master` present and `slots.recovery` absent, then adds a recovery key
  afterwards and asserts the DEK is byte-identical across the add. **Not a hash
  of `vault.db`**: vaults run `journal_mode = WAL`, so pages sit in
  `vault.db-wal` until a checkpoint and the main file's bytes move on open and
  close with no logical write at all — flaky in one direction and vacuous in the
  other. An mtime assertion is worse on both counts.
  Source: FIBR-0019 INV-12.

- **INV-13** — No byte of the live pair is modified until a rollback copy
  exists, is complete, and opens with the user's current key.
  *Test:* `test_migration.py::test_no_swap_without_a_verified_rollback_copy` —
  injects a failure into the copy step, then into its verification, and asserts
  in both cases that the live sidecar is still the v1 one, that the vault still
  opens with the original password, and that every table's row digest is
  unchanged. **Not a hash of `vault.db`**, for the reason INV-12 gives.
  Source: FIBR-0019 INV-13.

- **INV-14** — `resume()`'s branch 1 (the DEK opens the live database) offers
  the pre-upgrade copy on the same terms as the terminal branch: where the
  database opens but does not read end to end **and** a verified `.pre-v2`
  pair is beside it, `resume()` raises `RollbackAvailableError` rather than
  returning. INV-7's "the vault still opens" is not satisfied by a database
  whose rows are unreachable, and a silent return leaves `migration_pending`
  set forever — every later unlock re-enters branch 1 and the offer is never
  made.
  *Test:* `test_migration.py::test_branch_1_offers_the_pre_upgrade_copy_when_unreadable`
  — migrates a vault to the point S5 has swapped the database and stalls
  before S6, so a verified `.pre-v2` pair is still on disk; damages a page of
  the LIVE database well past its schema (SQLCipher HMACs pages
  independently, so page 1 and the schema stay intact while the row data does
  not); asserts as preconditions that the DEK opens the damaged database, that
  it does not read end to end, and that the `.pre-v2` pair is present and
  usable; then calls `resume()` directly and asserts `RollbackAvailableError`.
  Source: FIBR-0313 C1.

## Rationale

`AuthService.reset_vault` — "start over" — is the live answer to *I forgot my
password*, and it deletes the vault. For a tool holding a household's financial
history that is the failure users least forgive, and
`docs/decisions/0003-sqlcipher-local-only-storage.md` records it as an accepted
consequence. FIBR-0019 reverses that decision.

The sequencing is why this is a 1.0 blocker rather than a 1.1 feature: **the key
envelope has to exist at vault creation.** Every release shipped without it adds
more vaults that must later be re-encrypted during an update, on a user's
machine, over real financial data — which is what § 13's migration is, and what
INV-7, INV-8 and INV-13 exist to make survivable.

Three of the thirteen are here because the *obvious* way to write the test does
not test the thing, and each was found by a cold review lane rather than by
inspection: INV-1's second leg (loop 2), INV-3's fourth leg and its
`KdfPolicyError` third leg (loops 2 and 3), and INV-2's transcription leg
(loop 4). They are the assertions to be most careful with when this suite is
edited.

## Seams

§ 4 of the design spec fixes module paths and the two `keywrap` signatures. It
does **not** fix every name these tests must bind to. The ones chosen here are
recorded so implementation can reconcile them deliberately rather than
discovering them:

| Seam | Where | Why it is not in the design spec |
|---|---|---|
| `AuthService.first_run(...) -> str` | `services/auth.py` | § 4.5 steps 4/8 have first-run *generate* the code and show it once. Nothing else can learn it — INV-5 forbids retaining it — so the return widens from `None` to the display-form code. |
| `AuthService.add_recovery_key(code)` | `services/auth.py` | § 4.5 step 9 (Keep) and § 4.7 (Add). Declining is never calling it, which is what keeps a declined code's slot off disk. |
| `AuthService.set_master_password(password)` | `services/auth.py` | § 4.6 step 4's forced reset. |
| `services/vault_migration.py` | new module | § 13 names no module for S0..S6. `write_rollback_copy` / `verify_rollback_copy` are separate so INV-13 can break each half; `on_step(step)` fires immediately **before** each step so INV-7 can abort at a known point. |
| `UnlockDialog._recovery_code`, `._on_recovery_unlock()`, `.recovery_unlocked` | `ui/unlock.py` | § 4.6 fixes the route's behaviour, not its attribute names. `recovery_unlocked` must be distinct from `unlocked` so the shell can route to the forced new-password step (D6). |
| `_password_hint.validate_hint_with_recovery(hint, password)` | `ui/_password_hint.py` | § 11 says that module gains INV-11's trial-unwrap; it does not name the function. |

`require_seam` in `_recovery_helpers.py` reports a miss as *seam absent*, naming
the attribute and what it is for, so a rename never reads as a behaviour failure.

`_recovery_helpers.py` is a plain sibling module rather than a `conftest.py`:
the root `tests/conftest.py` is imported as the module `conftest` and several
suites do `from conftest import _PW`, so a second `conftest` on `sys.path` is a
collision waiting to happen.

## Out of scope

- **Cryptographic soundness.** These tests establish that the implementation
  matches the design document. Soundness rests on AES-256-GCM and Argon2id as
  used, and § 10 of the design spec records that **nothing** in this project
  checks it.
- **Whether the user actually stored the code**, stored it safely, or has not
  lost both credentials — all outside what software can know
  (`docs/security-model.md` § 4).
- **The code inside the vault's *contents*.** INV-5 scans plaintext surfaces
  and excludes `vault.db` on purpose; a claim about the vault's tables is a
  different invariant needing a fixture that opens it.
- **Changing the master password as an ordinary settings action**, the `.fbk`
  container's shape, biometric unlock (FIBR-0020), and cross-version `.fbk`
  restore (FIBR-0302) — all § 9 of the design spec.
- **Replace / Remove from Settings** (§ 4.7). Only *Add* is exercised, by
  INV-12; the other two carry no invariant in § 5 and adding tests for them
  would be scope creep.

## Status — this suite is expected to FAIL

FIBR-0019 is **not implemented**. `keywrap.py`, `services/recovery_code.py`,
`services/vault_migration.py` and the two `AuthService` methods above exist only
as stubs raising `NotImplementedError("FIBR-0019")`, so these tests *execute*
rather than dying at collection (`testing.md` § 1 — the test is seen to fail
before the code exists). Five of the thirteen fail against today's code for
reasons already established rather than assumed: INV-1 because every current
call site passes a derived key as the database key; INV-4 because the current
sidecar has seven flat fields; INV-11 because nothing today can reach
`slots.recovery`; INV-12 because no `sidecar_version` field exists at all; and
INV-13 because no migration exists to take a rollback copy before.

**Do not adjust an assertion to make one pass.** Under a live defect that is
how a test ends up asserting the bug.

## Registration

`recovery_key` is registered in `_NO_PROSE` in
`tests/features/prose_checks/test_prose_checks.py` (§ 7): this suite reads no
tracked document, so it need not run on a doc-only push.
