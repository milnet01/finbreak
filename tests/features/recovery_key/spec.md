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

- **INV-15** — `resume()`'s branch 2 (the DEK opens `vault.db.migrating`, so
  the crash was between S4 and S5) must not replace the live database with
  the `.migrating` one unless the `.migrating` file reads end to end.
  Branch 2 today calls `_swap_database` on `_opens` alone — the same weak
  check INV-14 names — with neither S2's `integrity_check` + row compare nor
  `_ensure_rollback_copy` gating it. A `.migrating` file damaged past page 1
  (SQLCipher HMACs pages independently, so the schema and page 1 survive
  while a later page's rows do not) opens but does not read, and today that
  is enough to destroy the still-intact live v1 database in its favour.
  *Test:*
  `test_migration.py::test_branch_2_does_not_swap_the_live_vault_for_a_damaged_replacement`
  — stalls a migration between S4 and S5 (`.migrating` exists, the live
  database is still v1), damages a page of `vault.db.migrating` well past
  its schema, asserts as preconditions that the DEK opens the damaged
  `.migrating` file, that it does not read end to end, and that the live
  `vault.db` still reads end to end with KEK-master; then calls `resume()`
  directly and asserts the live vault still opens with KEK-master and still
  holds every row.
  Source: FIBR-0313 H1.

- **INV-16** — `verify_rollback_copy` must not MODIFY the `.pre-v2` copy it
  exists to certify. Its own `probe.open(..., in_memory_temp=True)` omits
  `migrate=False` — unlike `_opens`/`_reads_end_to_end` in the same module,
  which both pass it for exactly this reason ("this is a question, not a
  use") — so `Vault.open`'s default `migrate=True` runs `run_migrations` and
  commits schema writes into the artefact S0 exists to leave untouched.
  *Test:* `test_migration.py::test_verify_rollback_copy_does_not_modify_the_copy`
  — builds a copy genuinely behind `LATEST_SCHEMA_VERSION` (suppressing
  `run_migrations` for one `Vault.create()` call, since every fixture built
  the ordinary way is already fully migrated by the time this function ever
  sees it — confirmed by reading `Vault.create()` and `_unlock_v1`), asserts
  as preconditions that it is behind and carries no `-wal` sibling of its own
  (so the checkpoint this function performs ON SUCCESS, which is deliberate
  and unrelated, cannot be mistaken for the defect), asserts verification
  itself succeeds, then asserts the copy's sha256 and schema_version are
  unchanged across the call.
  Source: FIBR-0313 H2.

- **INV-17** — `rollback_copy_is_usable` is typed `-> bool` and is asked on
  `resume()`'s last-resort terminal branch, where the user is offered their
  pre-upgrade copy. **Nothing may propagate out of it.** Today it catches
  `(VaultStateError, KdfPolicyError, DatabaseError, OSError)`, and
  `SchemaVersionError`'s MRO is `SchemaVersionError -> FinbreakError`, so a
  copy whose recorded schema is newer than this build supports throws straight
  out of the predicate. INV-16's `migrate=False` is what closes it:
  `run_migrations` is the only place that error is raised, and `Vault.open`
  returns before it when migrations are skipped.
  **The verdict on such a copy is `True`, and that is a decision rather than a
  side effect.** It READS — `integrity_check` passes and every row is there —
  and `verify_rollback_copy` exists to refuse a copy that cannot be read; a
  recorded schema number is not damage. Refusing it would leave the user the
  bare "vault and key record disagree" with their intact vault beside them and
  nothing saying so, where offering it restores the pair and the next unlock
  says "update finbreak" — the answer that gets their data back. So adding
  `SchemaVersionError` to the caught tuple, which is the remedy the finding
  implies, is the one thing this invariant rules out.
  *Test:*
  `test_migration.py::test_rollback_copy_is_usable_does_not_raise_on_a_too_new_copy`
  — writes a `.pre-v2` copy whose `schema_version` is one past
  `LATEST_SCHEMA_VERSION`, asserts that as a precondition via a
  `migrate=False` probe, then calls `rollback_copy_is_usable` and asserts it
  neither raises nor withholds the offer. Reachable in production as a genuine
  app downgrade mid-migration: `_ensure_rollback_copy`'s retake copies the
  live database byte-for-byte with no migration run first (its own check,
  `_opens`, passes `migrate=False`), so a copy taken or retaken by a build
  with a higher `LATEST_SCHEMA_VERSION` and later read by a build with a
  lower one carries exactly this shape.
  Source: FIBR-0313 H2.

- **INV-18** — `restore_rollback_copy` must leave the directory holding the
  restored pair fsynced, not only the pair's own bytes. `write_rollback_copy`
  already fsyncs each copy as a file when S0 takes it (INV-13's `_fsync`), so
  the source halves are already durable by the time this function runs; what
  its three `os.replace` calls (the database, an optional WAL sibling, the
  sidecar) leave undone is the directory ENTRY a rename creates, which POSIX
  does not guarantee survives a crash. This is § 13.3's last-resort route: the
  user has just been told their pre-upgrade vault is restored, and a power
  loss immediately after can still leave the directory listing pointing
  nowhere durable, on the one path that exists to get their data back.
  *Test:* `test_migration.py::test_restore_rollback_copy_fsyncs_the_directory`
  — builds a `.pre-v2` pair via the terminal-branch fixture, monkeypatches
  `vault_migration.os.fsync` to record every directory-mode fsync's resolved
  path, calls `restore_rollback_copy` directly, and asserts the pair's parent
  directory appears among them.
  Source: FIBR-0313 M3.

- **INV-19** — `finbreak.services.vault_migration` hands `Vault.open` the
  buffer its caller owns and mints no copy. This is the project's settled
  rule, not a new one: `backup.py`'s `restore_backup` helper says so in as
  many words — "Pass the derived key itself, NOT a copy: open() only reads
  key.hex() (never mutates), so a copy would be an un-wiped second reference
  to live key material outside the finally wipe" (backup.py:465-467, and the
  matching `rekey(dek)  # not a copy` at backup.py:291) — and
  `docs/specs/FIBR-0019-master-password-recovery-key.md` names the failure
  mode by number: a `bytes(kek)` copy "lands in the *caller's* frame, out of
  reach of the `finally` that wipes the bytearray — an INV-3 breach at eight
  sites" (security-model INV-3 is the wipe-key-material-in-finally rule
  itself). `vault_migration` is the one module that does not follow it:
  each of its six call sites mints a fresh, unnamed `bytearray(key)` copy
  instead of passing `key` through — `_opens`, `_reads_end_to_end`,
  `_row_counts_or_none`, `verify_rollback_copy`, and `_convert`'s two opens
  (`live.open(bytearray(kek_master))`, `replacement.open(bytearray(dek),
  ...)`). Every copy is a second, un-wiped reference to live key material
  sitting outside the owning frame's `finally`-wipe — orphaned the moment
  `Vault.open` returns, since `Vault.open` only reads `key.hex()` inside
  `_connect` and never mutates or wipes the argument it is given. One
  `resume()` through branch 3 mints up to eight such copies.
  *Test:*
  `test_migration.py::test_migrate_to_v2_passes_its_callers_key_through_without_copying`
  and
  `test_migration.py::test_resume_branch_2_passes_its_callers_keys_through_without_copying`
  — monkeypatch `vault_migration.Vault` with a subclass that records the exact
  buffer OBJECT (never a copy) handed to every `.open()` call, labelled by
  caller and line number. For every site handed a buffer the test itself
  owns (both legs' KEK-master, and the resume leg's DEK — resume() mints
  nothing and wipes nothing itself, unlike migrate_to_v2), assert the
  recorded object IS that owned buffer by identity: a call-site copy fails
  this, a pass-through passes it. The one exception is `_convert`'s
  `replacement.open(bytearray(dek), ...)` site in the migrate leg — the DEK
  there is minted INSIDE `migrate_to_v2` and wiped by its own `finally`, so
  the test cannot hold it by identity ahead of time; that site is instead
  checked for being zeroed once `migrate_to_v2` has returned, which it would
  be if the site passed the real DEK through rather than copying it. The two
  legs together reach all six call sites: the migrate leg covers
  `verify_rollback_copy` and both `_convert` opens on a fresh, uninterrupted
  `migrate_to_v2`; the resume leg covers `_opens`, `_reads_end_to_end` and
  `_row_counts_or_none` (each of the latter two called twice) via
  `resume()`'s branch 2. Neither leg prints a buffer's contents — only
  identity and whether it is still live.
  Source: FIBR-0313 M4.

- **INV-20** — A failed RECOVERY-CODE attempt must not tell the user to check
  their password. `_show_failure` is shared between both routes and its
  no-countdown branch hardcodes "Check your password and try again" — reached
  only when `UnlockThrottle.remaining()` reports 0 immediately after
  `record_failure`. **Reachable only in that corner**: on a working install
  `BASE_DELAY_SECONDS == 1.0` makes `remaining` > 0 right after any recorded
  failure, so the countdown branch (a credential-neutral "Try again in Ns")
  fires first every time; the generic message is live only if the persisted
  throttle state fails to survive (e.g. an unwritable `window.ini`).
  *Test:*
  `test_recovery_unlock.py::test_recovery_failure_message_does_not_mention_password`
  — drives a real failed recovery attempt (a forged code with a valid check
  symbol) through the dialog's worker path, with `UnlockThrottle.remaining`
  monkeypatched to always report 0 so the no-countdown branch is reached
  without needing to break `window.ini` on disk, and asserts "password" does
  not appear in the resulting message.
  `test_recovery_unlock.py::test_recovery_derivation_failure_message_does_not_mention_password`
  — the second route into the same message, where the KDF itself fails rather
  than the code being wrong, so the worker's `failed` signal is what reaches
  `_show_failure`. It is a separate test because a single shared failure slot
  satisfies the first one and not this one: `mutation_probe` re-pointed that
  connection back at the password slot and the suite stayed green until this
  test existed.
  Source: FIBR-0313 M5.

- **INV-21** — `RecoveryCodeDialog`'s clipboard-clear guard must outlive the
  dialog even when the caller injects no guard of its own. The constructor's
  `clipboard is None` branch owns the guard from the dialog's parent — from the
  application object where there is none, as `build_recovery_offer` does it —
  and never from the dialog. A guard the dialog owns has its single-shot clear
  timer destroyed the moment the dialog is, so a copied recovery code, the one
  credential that opens the vault on its own, stays on the clipboard for good.
  That is FIBR-0310 R1 **verbatim**: R1 fixed the injected arm and left this
  one (FP04 finding M6).
  *Test:*
  `test_settings_flows.py::test_the_constructor_default_clipboard_guard_survives_the_dialog`
  — builds `RecoveryCodeDialog(code)` directly with no `clipboard=` argument,
  so the constructor's own default is what is under test; copies the code and
  asserts as a precondition that it reached the clipboard; destroys the
  dialog and asserts as a precondition that it is actually gone
  (`shiboken6.isValid`); drops the last Python reference and collects, without
  which a guard owned by *nothing* survives on that reference alone and the leg
  passes; then waits for the clipboard to clear on its own.
  Asserts the OUTCOME the user sees — the clipboard ends up empty after the
  dialog is gone — never the parent pointer, so the leg cannot pass against a
  guard that is merely re-parented some other way but still tied to the
  dialog's lifetime.
  Source: FIBR-0310 R1 (FP04 finding M6).

- **INV-22** — `NewMasterPasswordDialog._on_submit` fails closed and silently on
  a locked vault, matching its three § 4.7 siblings (`keep_recovery_code`,
  `_confirm_master_password`, `remove_recovery_key`). The vault is open while
  this D6 dialog is shown, so the idle auto-lock timer is live; `MainWindow._lock`
  closes the dialog before it locks the vault and shows the unlock screen, so a
  queued submit can still reach `_on_submit` after the service has locked. Its
  broad `except Exception` arm rendered the resulting `VaultLockedError`'s own
  wording onto a dialog already being torn down (FIBR-0310 P12, FP04 finding
  M7).
  *Test:*
  `test_settings_flows.py::test_an_auto_lock_before_new_master_password_is_refused_silently`
  — sets matching new passwords, locks the vault to force the route
  `set_master_password` takes on an auto-lock, calls `_on_submit` directly, and
  asserts the error label stays empty and the dialog does not report success by
  closing. A second leg monkeypatches `set_master_password` to raise a generic
  `RuntimeError` and asserts the label is **not** empty, so the fix's narrowed
  arm cannot be a blanket silence that swallows a genuine re-wrap failure too.
  Source: FIBR-0310 P12 (FP04 finding M7).

- **INV-23** — A damaged (not merely unreadable) `recovery` slot makes the
  password-hint check fail OPEN with a warning, never raise.
  `validate_hint_with_recovery` goes straight from a successful
  `read_sidecar_v2` to `sidecar.params_for(SLOT_RECOVERY)` and `derive_key`,
  never calling `crypto.validate_slot` — the check that function's own
  docstring says the slot's CONSUMER must run, because `read_sidecar_v2`
  hard-fails on `master` only and loads a damaged `recovery` slot without
  complaint (FIBR-0310 R5). Three damage shapes must land in the same place,
  and they are chosen so that neither half of the guard can be dropped. A salt
  too short for `validate_params`, and a `time_cost` of zero that
  `validate_params` never checks, both reach Argon2id inside `derive_key` and
  raise `argon2.exceptions.HashingError` — which propagates straight out of
  `MainWindow._on_set_hint_requested`, whose `except HintPolicyError` does not
  catch it. A nonce too short for `_validate_slot_lengths` never reaches
  Argon2id at all: it reaches `unwrap_dek`, which answers every failure with
  the one undifferentiated `KeyUnwrapError` (FIBR-0307 finding 9), so the loop
  continues past it and the route returns SILENTLY — a fail-open that reads
  exactly like a hint that passed the check. That third shape is the one only
  `validate_slot` can catch.
  *Test:*
  `test_recovery_code.py::test_a_damaged_recovery_slot_fails_open_with_a_warning`
  — parametrized over the three damage shapes. Builds a real vault with both
  slots, damages ONLY the `recovery` slot on disk, feeds a hint holding a
  well-formed but unrelated candidate code, and asserts `validate_hint_with_recovery`
  returns without raising and that a WARNING was logged **by
  `finbreak.ui._password_hint` itself** — never that `validate_slot` was
  called, since a fix that reaches the same outcome by another route must still
  pass. The logger filter is load-bearing rather than tidiness:
  `crypto.read_sidecar_v2` logs its own warning when it keeps a damaged
  optional slot, so an unfiltered `caplog.records` is satisfied by that line
  and passes against a route that stayed silent. Measured with
  `mutation_probe`, which could not kill a dropped `validate_slot` call until
  the assertion named its own logger.
  Source: FIBR-0313 M8.

- **INV-24** — A read-modify-write through the v2 sidecar preserves every field
  it does not itself define, at all three levels a v2 sidecar carries them: an
  unrecognised top-level key, an unrecognised key inside the shared `kdf`
  group, and an unrecognised key inside a slot record. `VaultSidecar.to_dict()`
  re-emits only the fields the dataclass names, and every writer round-trips
  through it (`read_sidecar_v2` → mutate → `write_sidecar_v2`), so a field a
  newer build wrote and an older one does not know about is silently deleted
  on the very next write reachable from an ordinary user action
  (`AuthService.add_recovery_key`, `remove_recovery_key`, `set_master_password`;
  `vault_migration._finish`). `read_sidecar_v2`'s own subset checks already
  tolerate such a field **on read** — the comment above
  `MIGRATION_PENDING_FIELD` reasons about exactly this case for the resume
  sidecar — but tolerating it on read and then deleting it on the next write is
  the same loss one step later. § 4.1 of the design spec anticipates FIBR-0020
  (biometric unlock) arriving as a new slot; a build that has not yet learned
  about it must not destroy what a build that has already written. **An
  unrecognised SLOT NAME is not this defect** — `slots` is a plain dict keyed by
  name and every writer copies it wholesale, so an unknown slot already
  survives a re-wrap untouched.
  *Test:* `test_sidecar_v2.py::test_read_modify_write_preserves_unknown_v2_fields`
  — plants a distinct, recognisable string at all three levels directly on
  disk, then drives a REAL read-modify-write through
  `AuthService.add_recovery_key` (§ 4.7's Keep/Add route) rather than only
  `read_sidecar_v2`/`write_sidecar_v2` directly, and asserts all three survive
  with their original values, alongside the untouched master slot's own known
  fields.
  Deliberately NOT covered, and recorded so the gap is not mistaken for
  coverage: `to_dict()` emits unrecognised keys BEFORE the ones it owns, so a
  stray key sharing a name loses to the real value rather than overwriting it.
  No test reaches that, and none can from this route — `read_sidecar_v2`
  filters the known names out of both unrecognised bags by construction, so the
  collision exists only for a hand-built `VaultSidecar`. `mutation_probe`
  confirms it is unmeasured: reversing the order leaves the suite green. The
  ordering is kept as insurance against a future construction path, not because
  anything today can produce the collision.
  Source: FIBR-0313 M9.

- **INV-25** — After a RECOVERY unlock, once D6's forced new master password
  is set and the workspace is reachable, the UI offers the user the chance to
  replace their recovery code — the D5 offer (spec line 139): "The UI offers
  regeneration after a recovery unlock for the user who thinks their copy was
  exposed; it does not impose it." `MainWindow._show_recovery_offer` (called
  from the end of `_enter_unlocked`) fires in exactly two cases today: a held
  `_pending_recovery_code` (first run) or `_service.consume_migration_notice()`
  (D7, a just-converted vault). A recovery unlock is neither, so
  `_on_recovery_unlocked`'s chain into `_enter_unlocked` reaches the end of
  `_show_recovery_offer`, which returns `False`, and no offer ever appears —
  the workspace comes up directly.
  *Test:*
  `test_recovery_unlock.py::test_recovery_unlock_offers_recovery_code_regeneration`
  — drives a REAL recovery unlock through `MainWindow` (not a standalone
  `UnlockDialog`, since the offer is wired — or, today, not wired — at the
  shell level): submits the recovery code, waits for D6's forced
  `NewMasterPasswordDialog`, sets a new password, and asserts a
  `RecoveryCodeDialog` is up and VISIBLE in the shell's single `_dialog` slot
  once that completes — the on-screen outcome, never that
  `_show_recovery_offer` was called or a private flag was set. A third leg
  declines the offer and asserts the ORIGINAL recovery code still unwraps the
  vault's real DEK afterwards, locking D5's "it does not impose it." A fourth
  leg locks and unlocks ORDINARILY on the same window, asserting the offer does
  not come back: it is owed once, by the recovery unlock that earned it. The
  control test below cannot reach that case — it builds a fresh window that
  never had a recovery unlock — so an offer left permanently owed would fire on
  every login of a window that had one, and nothing would notice.
  `mutation_probe` found exactly that: removing the consume-on-read left the
  suite green until this leg existed. Its `window._unlocked` precondition is
  load-bearing, because a failed unlock also leaves something that is "not a
  `RecoveryCodeDialog`" in the slot.
  `test_recovery_unlock.py::test_ordinary_unlock_does_not_offer_recovery_code_regeneration`
  — the control: an ORDINARY password unlock must show no such offer.
  Without it, an implementation that offers regeneration after every unlock
  — not just a recovery one — would pass the first test and still be wrong.
  Source: FIBR-0313 M10.

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
