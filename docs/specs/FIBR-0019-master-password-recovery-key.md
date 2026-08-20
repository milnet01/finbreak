# FIBR-0019 — Master-password recovery via a recovery key

**Status:** spec draft (2026-08-20).
**Kind:** security.
**Source:** ROADMAP FIBR-0019 (user-request-2026-07-01); confirmed for the
1.0 release 2026-08-20 (user decision recorded on FIBR-0304).

**Blocker for:** FIBR-0304 (the v1.0 gate — condition 1).
**Pairs with:** FIBR-0018 (the encrypted `.fbk` backup *feature*; its
implementation contract is `docs/specs/FIBR-0014.md`), FIBR-0030 (destructive
reset), FIBR-0029 (password hint), FIBR-0095 (unlock throttling).

**Layman:** When you create a vault, finbreak gives you a long recovery code
to write down and keep somewhere safe. If you ever forget your master
password, that code — and only that code — gets you back into your own data.
Nobody else has a copy, and there is no way in without one of the two.

---

## 1. Goal

After this ships, a finbreak vault is unlocked by **either** the master
password **or** a recovery code the user was given when the vault was created,
and both routes reach the same data. Neither the app, the maintainer, nor
anyone holding the vault file can open it without one of the two.

Today the master password is the only key that exists, and forgetting it
destroys the data — `docs/decisions/0003-sqlcipher-local-only-storage.md`
records that as an accepted consequence, and
`src/finbreak/ui/first_run.py::FirstRunDialog` tells the user so in as many
words. This spec reverses that decision deliberately, and §11 lists every
document that has to change with it.

The mechanism is **envelope encryption**: the database stops being encrypted
directly by a password-derived key, and is encrypted instead by a random
**data key (DEK)** that is itself stored twice over, wrapped once under a key
derived from the master password and once under a key derived from the
recovery code.

## 2. Problem

### 2.1 There is exactly one key, and it is the password

`src/finbreak/crypto.py::derive_key` stretches the master password with
Argon2id and returns 32 bytes. `src/finbreak/vault.py::Vault._connect` hands
those bytes straight to SQLCipher as its raw key:

```python
conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
```

There is no indirection. The Argon2id output **is** the database key, so the
set of credentials that can open a vault has exactly one member and cannot be
extended without changing what SQLCipher is keyed with.

*Verified by grep, 2026-08-20:*

```
$ grep -rEl 'wrapped_dek|unwrap_dek|recovery_code' src/ | wc -l
0
```

No key-wrapping, DEK/KEK or envelope machinery exists anywhere in the package
today.

### 2.2 The one existing recovery route requires foresight the user may not have had

`src/finbreak/services/backup.py::BackupService` already provides a
second credential — a `.fbk` backup is a **complete second copy** of the vault,
re-encrypted under a key derived from a separate backup password, and
`restore_backup` opens it and re-keys it to a freshly chosen master password.

That works, and it stays. But it recovers **the data as of the last export**,
and only if the user made one. A user who never exported has nothing. The
mechanism is also structurally different from what this spec needs: two
independently-keyed copies of the same plaintext, rather than one key wrapped
twice — so it cannot be extended into a recovery slot.

### 2.3 The consequence is unrecoverable and permanent

`AuthService.reset_vault` (surfaced by
`src/finbreak/ui/start_over.py::StartOverDialog`, FIBR-0030) is the only other
answer the app has for a forgotten password, and it is destructive by design:
it deletes `vault.db`, `vault.kdf.json` and the SQLite `-wal`/`-shm` siblings
and returns the app to first-run state.

So the live answer to "I forgot my password" is *lose everything*, which for a
tool holding a household's financial history is the failure users least
forgive.

### 2.4 Why now rather than later

`FIBR-0019`'s own roadmap entry states the sequencing constraint, and it is
the reason this is a 1.0 blocker rather than a 1.1 feature: **the key envelope
has to exist at vault creation.** Retrofitting it onto vaults created without
it means re-encrypting real financial data during an update on a user's
machine — §13 specifies exactly that migration for the vaults already in the
field, and every release after 1.0 that does not have this spec's format adds
more of them.

`docs/standards/versioning.md` § 5 condition 1 makes an open item that would
render an existing artifact unusable by the next release a bar to 1.0, and
names FIBR-0019 as the live case.

## 3. Scope decisions (agreed with the user)

Preference calls, not deductions. Each is recorded so the same argument is not
had twice.

**D1 — The recovery key ships inside 1.0** rather than freezing the vault
format without it. *User, 2026-08-20*, on the trade stated in FIBR-0304: the
key envelope must exist at vault creation, so building it now is cheap and
retrofitting it later is a full re-encrypt over real financial data. The
alternatives offered and declined were freezing without it, and cutting 0.9.0
as versioning.md § 5's named interim.

**D2 — Every existing vault is migrated to the envelope format, automatically,
at the next successful unlock** — not lazily when a recovery key is first
requested. *Author's call, 2026-08-20.* The reason is that two key schedules
in the field is the thing this spec exists to avoid: after 1.0 there must be
exactly one way a vault is keyed, or every later change has to reason about
both. §13 owns the mechanism; §6 owns what happens when it is interrupted.

**D3 — A recovery key is generated for every new vault, and the user may
decline to keep it** rather than being forced to store one. *Author's call.*
Declining leaves the recovery slot empty; the envelope is still built, so
adding a recovery key later is a re-wrap of 32 bytes and never a re-encrypt.
This is the property that makes D3 cheap and D2 necessary.

**D4 — The recovery code is 135 bits, Crockford base32, 28 symbols in seven
groups of four.** *Author's call*, from the format survey in § 8.3. A reviewer
may change the presentation without changing anything else in this document —
§ 4.3 is self-contained.

**D5 — A used recovery code stays valid.** *Author's call*, matching
1Password's recovery codes, which are reusable and remain valid after use
(`Source:` https://support.1password.com/recovery-codes/). A code the user
wrote down a year ago and files away should still be the correct code. The UI
offers regeneration after a recovery unlock for the user who thinks their copy
was exposed; it does not impose it.

**D6 — Recovery unlock forces a new master password before the vault is
usable.** *Author's call.* A user arriving by this route has, by construction,
no working password; leaving them unlocked with no way back in tomorrow
reproduces the problem one day later.

**D7 — A migrated vault is offered a recovery key immediately after the
migration completes, on the same terms as a new one.** *Author's call,
2026-08-20.* §13's S1–S6 mint the DEK and the master slot only; the recovery
slot is empty when they finish, and every vault in the field is exactly the
population this feature exists for — so leaving them to discover §4.7's *Add*
would ship the feature to nobody who already has data. After S6 the app shows
the §4.5 step 8 display once, with the same Keep / Decline and the same step-9
write on Keep. It is offered **after** the migration rather than before, so a
declined offer or a closed window costs nothing already done.

## 4. Design

### 4.1 The envelope

Three key roles replace today's single one:

| Role | What it is | Where it lives |
|---|---|---|
| **DEK** — data key | 32 random bytes, `bytearray(secrets.token_bytes(KEY_LEN))` | Never on disk unwrapped. It is SQLCipher's raw key. |
| **KEK-master** | `derive_key(master_password, salt_master, params)` | Never on disk. Derived on demand. |
| **KEK-recovery** | `derive_key(recovery_code, salt_recovery, params)` | Never on disk. Derived on demand. |

Each KEK wraps the **same** DEK into its own slot. Unlocking is: derive the
KEK for whichever credential the user supplied, unwrap that slot, and open
SQLCipher with the resulting DEK. `Vault._connect` is unchanged — it still
receives 32 bytes and still issues `PRAGMA key`. What changes is where those
bytes come from.

Two consequences worth stating, because later work depends on both:

- **Changing a credential re-wraps 32 bytes.** It never re-encrypts the
  database. `PRAGMA rekey` is not on the credential-change path at all.
- **Adding a third credential is adding a slot.** FIBR-0020 (biometric
  unlock) becomes a slot rather than a redesign. It is out of scope here (§9)
  and this spec fixes no part of it beyond leaving `slots` an open map.

### 4.2 Wrapping primitive

`AESGCM` from `cryptography` — a pinned runtime dependency, so no new
dependency is introduced.

*Verified 2026-08-20:*

```
$ python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; import cryptography; print('AESGCM ok', cryptography.__version__)"
AESGCM ok 50.0.0
```

A slot is produced as:

```python
nonce = secrets.token_bytes(12)
wrapped = AESGCM(kek).encrypt(nonce, dek, aad)
```

`aad` is the **additional authenticated data**, and it is what stops a slot
being tampered with in ways the ciphertext alone would not notice. It is the
UTF-8 encoding of a canonical string binding the things that must not be
swapped underneath a slot:

```
finbreak-kdf-v2|<slot_name>|<memory_kib>|<time_cost>|<parallelism>|<key_len>
```

So a `recovery` slot cannot be renamed to `master`, and the Argon2id cost
parameters recorded beside it cannot be weakened without the unwrap failing
closed. Both are cheap edits to a plaintext file, and neither is detectable
from the ciphertext.

New module `src/finbreak/keywrap.py`, Qt-free and dependency-light, so it is
testable headless:

```python
SLOT_MASTER = "master"
SLOT_RECOVERY = "recovery"

def wrap_dek(kek: bytes, dek: bytes, slot: str, params: KdfParams) -> Slot: ...
def unwrap_dek(kek: bytes, slot_data: Slot, slot: str, params: KdfParams) -> bytearray: ...
```

`unwrap_dek` raises `KeyUnwrapError` (new, in `finbreak.errors`) on any
authentication failure. It never distinguishes "wrong credential" from
"tampered slot" in what it raises — the caller cannot act differently on the
two, and a distinguishing error is an oracle.

### 4.3 The recovery code

**Entropy.** 135 bits, from `secrets.randbits(135)`. That is above the 128-bit
symmetric floor with no padding waste: 135 is exactly 27 base32 symbols.

**Encoding.** Crockford base32 — the **data** alphabet excludes `I`, `L`,
`O` and `U`, decoding is case-insensitive, `i`/`l` decode as `1` and `o` as `0`, and
hyphens are ignored on input. It is designed for exactly this job: a secret a
human transcribes from paper.
(`Source:` https://www.crockford.com/base32.html,
https://github.com/jbittel/base32-crockford)

**Check symbol.** One mod-37 check symbol is appended, giving 28 symbols. It
detects a single mistyped character and most transpositions **locally, before
the KDF runs**, so an obvious typo produces an immediate "that code has a typo
in it" instead of a ~0.1 s Argon2id derivation followed by an indistinguishable
failure. It is a **usability** device and carries no security weight — §5
INV-6 states that as a contract, because treating it as authentication is the
plausible mistake.

**Its alphabet is 37 symbols, not 32, and that is the detail a builder gets
wrong.** Crockford's check alphabet is the 32 data symbols plus `*`, `~`,
`$`, `=` and `U` — so `U`, excluded from the data alphabet for accidental
obscenity, returns as a legal **final** symbol, and so do four punctuation
marks. The 37 is load-bearing: it is the least prime above 32, which is what
gives the check its detection properties, so a mod-32 check over the data
alphabet alone is a different and weaker construction and is **not** what
this spec means. Two consequences the implementation must honour: a code's
last group may read `RST$` or `RSTU`, and **Input normalisation removes
hyphens, spaces and case only — it must not strip `*~$=`**, which would
destroy the very symbol it is there to read.

**Display.** Seven hyphen-separated groups of four:

```
A1B2-C3D4-E5F6-G7H8-J9K0-MNPQ-RSTV
```

That example ends in a data symbol; one ending `RST$` or `RSTU` is equally
valid, per the check-symbol alphabet above.

**Input.** Hyphens, spaces and case are normalised away before decoding, so a
user may type it as shown, in one run, or in lower case.

**No new dependency.** Crockford base32 is roughly thirty lines and no
maintained wheel is pinned for it here; it lives in
`src/finbreak/services/recovery_code.py` alongside generation, formatting,
normalisation and check-symbol verification, all pure and Qt-free.

### 4.4 The sidecar, format version 2

Today `vault.kdf.json` is a flat object of seven fields.

*Verified 2026-08-20:*

```
$ PYTHONPATH=src python -c "from finbreak.crypto import _REQUIRED_SIDECAR_FIELDS as F; print(len(F), sorted(F))"
7 ['format_version', 'key_len', 'memory_kib', 'parallelism', 'salt_hex', 'salt_len', 'time_cost']
```

Version 2 names its version field **`sidecar_version`**, not `format_version`,
and moves the rest into two
groups — the Argon2id cost parameters, which are shared by every slot, and the
slots themselves, each carrying its own salt and its own wrapped copy of the
DEK:

```json
{
  "sidecar_version": 2,
  "kdf": {
    "memory_kib": 47104,
    "time_cost": 1,
    "parallelism": 1,
    "key_len": 32,
    "salt_len": 16
  },
  "slots": {
    "master": {
      "salt_hex": "…32 hex chars…",
      "nonce_hex": "…24 hex chars…",
      "wrapped_dek_hex": "…96 hex chars…"
    },
    "recovery": {
      "salt_hex": "…", "nonce_hex": "…", "wrapped_dek_hex": "…"
    }
  }
}
```

- **`sidecar_version` is deliberately NOT `format_version`, and the rename is
  the fix for a real trap.** `validate_params`' *first* check is
  `params.format_version != FORMAT_VERSION`, so a per-slot `KdfParams` built
  with the file's `2` would make every v2 vault refuse to open — surfaced to
  the user as the security-settings file being missing or damaged, over an
  intact vault. With two distinct names there is nothing to conflate: a
  per-slot `KdfParams` always carries `format_version = FORMAT_VERSION` (`1`,
  the params-record version, shared with the `.fbk`), and the loader
  dispatches on `sidecar_version` before it constructs one.
- **Each slot has its own salt.** Reusing one salt across slots would make the
  two KEKs derivable from one another's work factor and is a pointless
  saving — a salt is 16 bytes.
- **`slots.recovery` is absent, not null, when the user declined** (D3).
- **One further field is legal, and only while a migration is in flight** —
  `migration_pending: true`, written at §13.2's S3 and removed at S6. It is an
  optional member of the v2 shape, not a foreign key: a loader that rejects an
  unrecognised v2 key would refuse the resume sidecar on the next open and take
  §13.3's resume down with it. A migrated vault also carries
  `cipher_compatibility` permanently (§13.2).
- **`wrapped_dek_hex` is 48 bytes** — 32 of ciphertext plus GCM's 16-byte tag.
- **`kdf` records the parameters the slots were actually derived under — not
  necessarily today's pin.** For a new vault they are the same thing. For a
  **migrated** vault they are the v1 vault's own recorded parameters, carried
  forward unchanged (§13.1), which is what lets `validate_params`' floor do
  the job its own source comment describes: accept an existing vault whose
  recorded `memory_kib` sits below a later-raised pin. A migrated vault is
  therefore exactly as strong as it was, and no stronger — stated plainly
  rather than implied.
- **The Argon2id parameters are shared by both slots.** Both routes use the
  same cost, so neither is cheaper to attack than the other. `validate_params`
  keeps enforcing the directional memory floor and the exact-length format
  match, **per slot**: the cost parameters come from `kdf`, and the
  salt-length legs are checked against *that slot's* salt — so `salt_len: 16`
  beside a 4-byte `slots.master.salt_hex` is rejected. Reading `kdf` alone
  would silently drop the real-salt-length leg that `security-model.md`
  INV-2's exact-format match requires.
- **The file remains plaintext and `0o600`.** It holds no unwrapped key
  material and no password. §5 INV-4 is the contract. What it now *does* hold
  is a wrapped DEK, and that falsifies a named invariant. INV-7 of
  `docs/specs/FIBR-0004.md` says "the sidecar contains only the salt (hex) +
  non-secret KDF parameters + format version" — a wrapped key is none of those
  three. §11 carries the amendment. The honest replacement claim is *no
  unwrapped key material*, which is strictly weaker than *no secret*, and the
  weakening must be written down rather than glossed.

**`models.FORMAT_VERSION` does not move, and a new constant carries the
sidecar version.** That constant is shared: `KdfParams.to_sidecar_dict()`
stamps it, and `BackupService` writes the same record as a `.fbk`'s
`params.json` and reads it back through this same loader. Bumping
`FORMAT_VERSION` to 2 would therefore stamp `format_version: 2` on a **flat**
params record, which the version-dispatching loader reads as a slots record
and rejects — every `.fbk` written after the change would fail to restore.
So `FORMAT_VERSION` stays `1` and belongs to the `.fbk` params record; the
v2 sidecar carries its own `SIDECAR_VERSION = 2` under its own field name.

**A version-1 sidecar is the on-disk shape of every vault in the field, so
the shipped loader reads BOTH.** `load_and_validate_params` dispatches on the
presence of `sidecar_version`: absent means today's flat v1 shape, which is
the only migration source; `2` means the slots shape. A v2-only loader would reject every vault
in the field, and §13's migration could then never run, because it needs the
v1 vault *open* in order to copy it.

**An older build meeting a v2 file fails closed — but on the required-fields
gate, not the version check, and the difference is what the user sees.** In
`src/finbreak/crypto.py`, `load_and_validate_params` tests
`_REQUIRED_SIDECAR_FIELDS <= data.keys()` before anything reads
`format_version`; a v2 file carries none of the six flat fields, so that gate
raises first and the version check is never reached. `ui/unlock.py` renders
the resulting `KdfPolicyError` as the security-settings file being *missing or
damaged*, with a suggestion to restore from a backup — over an intact vault.
Verified 2026-08-20 by feeding a v2-shaped sidecar to the real loader.
§13.4 and §15.3 both rest on this being stated accurately.

### 4.5 Vault creation

`FirstRunDialog` gains one step after the existing password/preferences form,
and `AuthService.complete_first_run` grows the envelope:

1. Validate as today (`validate_first_run`).
2. Mint `params`, and a fresh salt per slot.
3. `dek = bytearray(secrets.token_bytes(KEY_LEN))`. **A `bytearray`, not
   `bytes`** — `security-model.md` INV-3 requires a mutable buffer because an
   immutable one cannot be wiped, and `Vault.create` / `open` / `rekey` /
   `export_to` are all annotated `bytearray` already, so `bytes` here is both
   an un-wipeable database key and a red `mypy` stage.
4. Generate the recovery code; derive both KEKs — **two Argon2id
   derivations**, so first-run cost roughly doubles (§14). They run as **two
   sequential `DeriveWorker` runs**, not one widened run: that class takes a
   single password and emits a single key (`done = Signal(bytes)`), and
   widening its signal would drag every existing call site along with it.
5. Wrap the DEK into both slots.
6. `Vault.create(dek, …)`, **with its sidecar write removed.** `create`
   today ends by calling `_write_sidecar(params)`, which serialises the flat
   v1 object — so leaving it alone writes a v1 file that step 7 overwrites,
   or leaves one standing if creation stops in between. Writing the sidecar
   becomes step 7's alone.
7. Write the v2 sidecar, carrying **`slots.master` only**, preserving the
   existing vault-before-sidecar create order (FIBR-0004 INV-5).
8. **Then** show the recovery code, once, with copy and "save to a file"
   affordances, and **Keep** / **Decline** as the two ways out.
9. On **Keep**, add `slots.recovery` and rewrite the sidecar atomically. On
   **Decline** nothing further is written, and the slot never existed.

The code is shown **after** the vault exists, never before: a code displayed
for a vault whose creation then failed is a code the user has carefully stored
for nothing.

**Declining happens at step 8, after the code has been shown** — the only
point at which the user knows what they are declining. The code is generated
and wrapped either way; what Decline skips is step 9, so `slots.recovery`
never reaches disk. The DEK, the master slot and the v2 sidecar are written
either way, at step 7.

**That order is not arbitrary.** Writing the recovery slot at step 7 and
deleting it on Decline would put a declined code's slot on disk, in a file
INV-12 asserts does not carry one; asking before step 4 would ask the user to
decide about something they have not seen. Deferring the one write to step 9
avoids both, at the cost of a second atomic sidecar write on the Keep path.

### 4.6 Unlock

`UnlockDialog` gains a second route. The password path is unchanged from the
user's side:

1. Read the sidecar; a v1 sidecar branches to §13.
2. Derive KEK-master from the entered password and `slots.master.salt_hex`.
3. `unwrap_dek` → DEK, or `KeyUnwrapError` → a failed attempt.
4. `Vault.open(dek)`.

The recovery route ("I've forgotten my password") differs only in which slot
it reads, plus the forced password reset afterwards (D6):

1. Normalise and check-symbol-verify the entered code; a bad check symbol is
   reported immediately and **is not counted as an unlock attempt**, because
   it proves a typo rather than a guess.
2. Derive KEK-recovery from `slots.recovery.salt_hex`; unwrap.
3. Open the vault.
4. **Before the main window is usable**, require a new master password,
   re-derive KEK-master against a fresh salt, and re-wrap the same DEK into
   `slots.master`. The DEK does not change, so no re-encryption happens.

**Both routes are throttled by the same mechanism.** FIBR-0095's
`src/finbreak/ui/_unlock_throttle.py::UnlockThrottle` currently backs off
failed master-password attempts; a recovery route that did not share the
counter would be a way around it. §5 INV-10 makes that a contract rather than
an implementation detail, because it is the kind of thing a later refactor
quietly drops.

### 4.7 Managing the recovery key

A Settings page — `src/finbreak/ui/settings.py` — gains:

- **Add** a recovery key, when `slots.recovery` is absent.
- **Replace** it, invalidating the previous code.
- **Remove** it, behind an explicit confirmation that says plainly what is
  being given up.

All three are gated on the current master password (matching how FIBR-0029's
hint dialog gates on it), and all three are re-wraps: derive a KEK, write or
delete one slot, rewrite the sidecar atomically. The database is untouched.

## 5. Invariants

- **INV-1** — **The installed vault's** SQLCipher raw key is a random DEK,
  never a value derived directly from a credential. **Scope: `vault.db` in
  the application data directory.** It does not fire on the `vault.db`
  *inside* a `.fbk` container, which `BackupService.export_backup` keys with
  `derive_key(backup_password, …)` and which keeps that schedule unchanged
  (§9).
  *Test:* `tests/features/recovery_key/test_envelope.py::test_dek_is_not_derived_from_any_credential`
  — two legs. First, derive KEK-master from the master password and
  `slots.master.salt_hex`, attempt `PRAGMA key` with those bytes, assert the
  vault does **not** open. Second, and this is the one that bites: create two
  vaults with the **same** master password and assert their unwrapped DEKs
  **differ**. Without the second leg the test passes under §8.1's rejected
  design — where the legacy Argon2id output *is* the DEK, wrapped under a
  freshly salted KEK — because KEK-master ≠ DEK there too. The first leg
  alone can only fail in the degenerate case where the KEK is itself the
  database key, so the implementation this spec most wants to exclude would
  ship green against the invariant meant to exclude it.
  *Breaks when:* a code path passes a `derive_key` result to `Vault.create`,
  `Vault.open` or `Vault.rekey` as the database key — which is exactly what
  every such call site does today, so this invariant fails against pre-change
  code.

- **INV-2** — Both slots unwrap to the same DEK, and either alone opens the
  vault.
  *Test:* `tests/features/recovery_key/test_envelope.py::test_both_slots_yield_the_same_dek`
  — unwraps each slot independently, asserts the two byte strings are equal,
  and opens the vault twice, once per route.
  *Breaks when:* the two slots are wrapped over different DEKs — for
  instance if §4.5's step 3 is re-run on a retry after step 5 has already
  written one slot.

- **INV-3** — Wrapping is authenticated: any modification to a slot fails
  closed.
  *Test:* `tests/features/recovery_key/test_envelope.py::test_tampered_slot_fails_closed`
  — four legs. Flip one bit in `wrapped_dek_hex`; flip one in `nonce_hex`;
  lower `kdf.memory_kib` and assert **`KdfPolicyError`**; and **rename
  `recovery` to `master`, then unwrap it with KEK-recovery**, asserting
  `KeyUnwrapError`. No vault opens in any case.
  **Only the fourth leg tests the AAD, and the obvious way to write it does
  not.** Unwrapping a renamed slot with KEK-*master* fails whether or not the
  AAD names the slot, because the slot still carries the recovery salt and the
  key is therefore simply wrong — so that version passes against an
  implementation whose AAD is `b""`. Unwrapping with KEK-recovery supplies the
  correct key, correct salt and correct ciphertext, leaving the slot name as
  the only thing that differs.
  **The cost parameters are bound by the derivation, not by the AAD.**
  `KEK = derive_key(credential, salt, params)`, so changing any of them
  changes the KEK and the unwrap fails for that reason alone; naming them in
  the AAD is defence in depth and is not something a test can demonstrate.
  Separately, `ARGON2_MEMORY_FLOOR_KIB` equals the pinned `ARGON2_MEMORY_KIB`
  (both 47104), so any lowering is refused by `validate_params` before
  `unwrap_dek` is reached — which is why that leg asserts `KdfPolicyError`. A
  leg asserting `KeyUnwrapError` there could never pass, and the plausible
  "fix" is to loosen the floor.
  *Breaks when:* an unauthenticated mode is used, or the AAD of §4.2 omits
  the slot name — which the fourth leg above exists to catch, and which
  nothing else in the design would.

- **INV-4** — The sidecar holds no unwrapped key material, no password and no
  recovery code.
  *Test:* `tests/features/recovery_key/test_sidecar_v2.py::test_sidecar_holds_no_unwrapped_secret`
  — asserts the parsed JSON's shape matches the v2 field set exactly **for a
  vault not mid-migration** (a pending one legally carries the extra field
  §4.4 names), and that no value anywhere in it contains the DEK,
  either KEK, the master password or the recovery code in any of hex, base32
  or raw form.
  *Breaks when:* a debug field, a cached derived key or the plaintext code is
  written into the file. This replaces today's
  `test_INV7_sidecar_holds_no_secret`, whose exact-key-set assertion this
  format necessarily breaks (§11).

- **INV-5** — The recovery code is never persisted by the application **of
  its own accord**, in any form, to any plaintext surface. The single
  exception is the file the user explicitly names at the moment of display
  (§4.5 step 8) — that is the user storing their own credential, not the app
  retaining it, and it is the difference between the two that this invariant
  is about.
  *Test:* `tests/features/recovery_key/test_recovery_code.py::test_code_never_reaches_a_plaintext_surface`
  — creates a vault with a known code, then asserts the code appears in no
  byte of `vault.kdf.json`, `window.ini`, the log file, or any other file the
  app wrote under its data directory, in Crockford, hyphenated, normalised or
  raw-bytes form — **excepting a file at a path the test itself supplied as
  the user's choice**, which is the §4.5 step 8 carve-out and the one write
  this invariant permits.
  *Breaks when:* the code is cached to make a "show it again" affordance work,
  or written to `window.ini` beside the password hint — `window.ini` is
  plaintext by design (FIBR-0052 INV-5), so that is the specific mistake with
  a plausible motive behind it.
  **`vault.db` is deliberately excluded from the scan**, and the exclusion is
  the point: the vault is encrypted, so a plaintext search of it cannot fail
  and a leg that cannot fail is not evidence. If the code must be kept out of
  the vault's *contents* too, that is a different invariant needing a
  different fixture — one that opens the vault and searches its tables — and
  this spec does not claim it.

- **INV-6** — The check symbol is a typo detector and carries no security
  weight.
  *Test:* `tests/features/recovery_key/test_recovery_code.py::test_valid_check_symbol_does_not_authenticate`
  — constructs a code with a **correct** check symbol but wrong payload,
  asserts it passes the local check and still fails to unwrap and still fails
  to open the vault.
  *Breaks when:* the check symbol is used to short-circuit the unwrap, making
  a locally well-formed code look accepted.

- **INV-7** — Migration is atomic: at every instant, either the pre-migration
  pair or the post-migration pair opens with the user's password. There is no
  window where neither does.
  *Test:* `tests/features/recovery_key/test_migration.py::test_every_crash_point_still_opens`
  — runs the §13 sequence against a real vault, aborting after each of steps
  S1 to S6, and asserts that a fresh app start opens the vault with the
  original password in every case, with every row intact.
  *Breaks when:* the sidecar is replaced before the new database has been
  written and verified, or the legacy salt is dropped from the pending sidecar
  — either one produces a state where the recorded key schedule and the file
  on disk disagree and nothing on disk can reconcile them.

- **INV-8** — Migration preserves every row of every table.
  *Test:* `tests/features/recovery_key/test_migration.py::test_migration_preserves_every_row`
  — seeds a vault across every table, records per-table row counts and an
  ordered digest of each table's contents, migrates, and asserts both are
  unchanged.
  *Breaks when:* `export_to` is given a table filter, or the migration runs
  against a connection with an open write transaction whose contents are not
  yet committed.

- **INV-9** — A recovery unlock leaves the vault with a working master
  password before the main window is reachable.
  *Test:* `tests/features/recovery_key/test_recovery_unlock.py::test_recovery_unlock_forces_a_new_master_password`
  — unlocks by code, asserts the main window is not shown until a new password
  is set, then closes and re-opens the vault with the new password and asserts
  the old one no longer works.
  *Breaks when:* the reset step is made skippable, or the re-wrap writes the
  sidecar before the new password is confirmed.

- **INV-10** — The recovery route is throttled by the same counter as the
  password route.
  *Test:* `tests/features/recovery_key/test_recovery_unlock.py::test_recovery_attempts_share_the_password_backoff`
  — exhausts the password allowance, then asserts a recovery attempt is
  refused by the same backoff; and the reverse, that failed recovery attempts
  advance the counter the password route reads.
  *Breaks when:* the recovery path does not consult the backoff before
  deriving, or does not record a failed unwrap as a failed attempt.
  **Not** when it constructs its own `UnlockThrottle` — that class is
  stateless beyond `window.ini`, opening a fresh `QSettings` per method, so
  two instances share the counter by construction and an invariant written
  against instance identity would test nothing.

- **INV-11** — A stored password hint may contain neither the master password
  nor the recovery code.
  **The check must work without the code, and that constraint decides its
  shape.** INV-5 forbids retaining the code, and the hint is set from
  Settings long after the one-time display, so nothing in memory holds it.
  Instead: **normalise the hint first** — strip hyphens, spaces and case,
  exactly as §4.3's Input rule does — then scan for any 28-symbol Crockford
  candidate, verify its check symbol locally, and where one passes, attempt
  `unwrap_dek` against `slots.recovery`. A successful unwrap proves the hint
  carries the live code. No candidate, or no successful unwrap, and the hint
  is accepted — so the common case costs no key derivation at all.
  **Normalising first is load-bearing**: the user holds the code in its
  display form, `A1B2-C3D4-…`, whose longest unbroken symbol run is four, so
  a scan of the raw hint text finds no 28-symbol candidate and cheerfully
  accepts a hint that is the recovery code.
  **The trial-unwrap lives in `ui/_password_hint.py`, not in
  `services/password_hint.py`.** That module's own contract is to be pure —
  no Qt, no I/O — and the only sidecar locator, `paths.sidecar_path()`, sits
  in a module that imports PySide6. Reaching it from the policy module would
  buy a Qt import, file I/O and a ~46 MiB derivation inside the one piece of
  this feature that is meant to be testable headless.
  *Test:* `tests/features/recovery_key/test_recovery_code.py::test_hint_rejects_the_recovery_code`
  — asserts a hint containing the real code is rejected, a hint containing a
  well-formed but *wrong* code is accepted, and a hint containing no
  candidate performs no derivation.
  *Breaks when:* the check is implemented by retaining the plaintext code,
  which breaches INV-5 while appearing to satisfy this one; or by scanning
  the hint before normalising it, which accepts the display form. Note that
  `validate_hint(hint, password)` keeps its two-argument signature (verified
  2026-08-20) — the recovery-slot leg is the caller's, per the seam above.

- **INV-12** — Declining a recovery key still builds the envelope.
  *Test:* `tests/features/recovery_key/test_sidecar_v2.py::test_declining_still_writes_the_envelope`
  — creates a vault while declining, asserts `format_version == 2`, asserts
  `slots.master` is present and `slots.recovery` is absent, then adds a
  recovery key afterwards and asserts **the DEK is byte-identical across the
  add** — unwrap `slots.master` before and after, compare the bytes — which
  is what re-wrap-rather-than-re-encrypt actually means. **Not a hash of
  `vault.db`**: vaults are opened `journal_mode = WAL`, so pages sit in
  `vault.db-wal` until a checkpoint and the main file's bytes move on open
  and close with no logical write at all. A file hash would be flaky in one
  direction and vacuous in the other; an mtime assertion is worse on both
  counts.
  *Breaks when:* declining short-circuits to the v1 format, which is the
  cheap-looking implementation and the one that reintroduces two key
  schedules (D2).

## 6. Failure modes

| Assumption | When it breaks | Behaviour required |
|---|---|---|
| The sidecar parses and is v1 or v2 | Truncated, hand-edited or from a newer build | `KdfPolicyError`, as today. Refuse to open. Never rewrite or delete the file — a user with a corrupt sidecar and an intact database still has recoverable data, and overwriting it is what makes the loss permanent. |
| The supplied credential unwraps its slot | Wrong password, wrong code, tampered slot | `KeyUnwrapError`, reported to the user as a failed attempt with no distinction between the causes (§4.2). Advance the shared throttle. |
| The DEK opens the database | Slot unwrapped but SQLCipher refuses | The pairing is broken — sidecar and database are from different vaults, or the database is damaged. Refuse, and point the user at restore-from-backup. Do **not** offer the destructive reset from this state; it is indistinguishable to the user from a wrong password, and the consequences differ absolutely. |
| Migration completes | Power loss, kill, disk-full at any of S1–S6 | §13's resume rules. INV-7 is the contract. |
| The vault is two files | It is four: vaults are opened `journal_mode = WAL`, so `vault.db-wal` and `vault.db-shm` exist alongside | A `-wal` written under the OLD key surviving S5 would have SQLite recover the NEW database from it. S5 closes both connections and removes the siblings before the swap. `security-model.md` INV-12 already counts those two as part of the vault's on-disk footprint. |
| Disk has room for a second copy | Disk full during S1 | The original pair is untouched, so the vault still opens. But `export_to` pre-creates its target `O_EXCL` and unlinks nothing on failure, so a partial `vault.db.migrating` survives — which is why S1 unlinks any existing one before it starts. Without that, every later attempt raises `FileExistsError` and the migration wedges permanently. |
| The recovery slot exists | User declined, or removed it | The recovery route is not offered. The "forgot password" affordance shows the backup-restore and start-over routes only, exactly as today. |
| The user still has the code | They lost it too | Nothing changes: FIBR-0018 restore and FIBR-0030 reset remain, unchanged and still the last resorts. This spec adds a route; it removes none. |

## 7. Tests

New suite `tests/features/recovery_key/`, with `spec.md` beside it per
`docs/standards/testing.md`. Five files, one per concern:

| File | Locks | Runs headless |
|---|---|---|
| `test_envelope.py` | INV-1, INV-2, INV-3 | yes — `keywrap` and `crypto` are Qt-free |
| `test_sidecar_v2.py` | INV-4, INV-12 | yes |
| `test_recovery_code.py` | INV-5, INV-6, INV-11 | INV-5 and INV-6 yes — `recovery_code` is pure. **INV-11 no**: its trial-unwrap seam lives in `ui/_password_hint.py`, which imports Qt, so that test needs `qtbot`. |
| `test_migration.py` | INV-7, INV-8 | yes — vault-level, no UI |
| `test_recovery_unlock.py` | INV-9, INV-10 | needs `qtbot` |

**Every one of these must be seen to fail before the change exists**
(`testing.md` § 1). Four of the twelve invariants fail against today's code for
reasons already established rather than assumed: INV-1 because every current
call site passes a derived key as the database key (§2.1); INV-11 because
nothing today can reach `slots.recovery` to trial-unwrap a candidate, there
being no such slot (§5); INV-4 because the current sidecar has seven flat
fields (§4.4); INV-12 because `format_version` is 1
(`src/finbreak/models.py`).

**Registration.** `recovery_key` must be added to `_NO_PROSE` in
`tests/features/prose_checks/test_prose_checks.py` — that suite fails if any
directory under `tests/features/` is in neither ledger. It reads no tracked
document, so `_NO_PROSE` is the correct half.

**Not claimed.** These tests do not establish that the construction is
cryptographically sound; they establish that the implementation matches this
document. Soundness rests on AES-256-GCM and Argon2id as used, and § 10 says
so rather than naming a test that would imply otherwise.

## 8. Alternatives considered (and rejected)

### 8.1 Keep the derived key as the DEK for migrated vaults

Declare the existing Argon2id output to *be* the DEK and wrap it under a
freshly salted KEK. No re-encryption, so §13 disappears entirely and INV-7 and
INV-8 with it — by far the cheapest option.

**Rejected** because it leaves two key schedules in the field permanently: a
migrated vault's DEK is password-derived and reproducible without the
envelope, a new vault's is random. Every later change — FIBR-0020's slot, a
credential rotation, an audit — then has to reason about both, and 1.0 is
where that fork becomes permanent. The saving is real; the cost is paid
forever.

### 8.2 In-place `PRAGMA rekey` for the migration

`Vault.rekey` exists, is proven (FIBR-0014 D4) and is already used by
`BackupService.restore_backup`. One call would migrate a vault.

**Rejected** because it mutates the only copy. A crash mid-rekey leaves a
partially re-encrypted database and no route back, which is the one outcome
this whole spec exists to prevent. §13's copy-verify-swap costs one temporary
file and makes INV-7 achievable.

### 8.3 Other recovery-code formats

**Hex or base64** — shorter to implement, and both include characters that are
routinely mistranscribed from paper (`0`/`O`, `1`/`l`, and base64's
case-sensitivity and `+`/`/`).

**Words from a wordlist** (BIP-39 style) — the most transcribable option and
genuinely good. Rejected for two reasons: 135 bits is twelve or thirteen
words, which is long to display and long to type; and a wordlist is a
localisation surface this project would then own forever.

**A shorter code, 64 or 80 bits** — Rejected: the code is a full-strength
credential to a financial vault, protected by nothing but its own entropy. The
saving is four characters.

### 8.4 An OS-keychain-held data key

Rejected already in `docs/decisions/0003-sqlcipher-local-only-storage.md`, as
"convenient but ties data to the keychain and weakens the 'your password is
the only key' guarantee".

**Still rejected**, and the ADR's reasoning is untouched by this spec — but
its *conclusion* is not. This spec does weaken "your password is the only
key", deliberately, to "your password or your recovery code, both held by
you". The difference from the keychain option is that the second credential
never leaves the user's hands and is not tied to a platform service. §11
records the new ADR this requires; that reversal must be written down, not
inferred from this section.

## 9. Out of scope

- **Changing the master password as an ordinary settings action.** This spec
  makes it a 32-byte re-wrap rather than a re-encrypt, so it becomes nearly
  free — but it is a separate user-visible capability. **No roadmap id tracks
  it today** (checked 2026-08-20 by `roadmap_query query:"master password"`,
  which returns seven bullets, none of them this). It needs filing.
- **Biometric unlock** — FIBR-0020. It becomes a third slot; this spec fixes
  nothing about it beyond leaving `slots` an open map.
- **Rotating the DEK itself.** That is a re-encrypt, and nothing here requires
  one.
- **Re-shaping the `.fbk` container.** Its inner `vault.db` stays keyed
  directly by `derive_key(backup_password, …)` — it is a transport format
  opened once by `restore_backup`, not an installed vault with credentials to
  add, so an envelope would buy it nothing. What *does* change is where a
  restore lands: §11 requires `restore_backup` to install a v2 vault.
- **Recovering a vault whose sidecar is lost.** Out of scope permanently: the
  wrapped DEK lives only there, which is what makes the design sound.
- **Multi-device or escrow recovery.** Contradicts the local-only posture of
  ADR-0003, which this spec does not otherwise disturb.
- **Cross-version `.fbk` restore coverage** — FIBR-0302, already filed, and
  made more pressing by this change (§11).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/features/recovery_key/test_envelope.py::test_dek_is_not_derived_from_any_credential` |
| INV-2 | `tests/features/recovery_key/test_envelope.py::test_both_slots_yield_the_same_dek` |
| INV-3 | `tests/features/recovery_key/test_envelope.py::test_tampered_slot_fails_closed` |
| INV-4 | `tests/features/recovery_key/test_sidecar_v2.py::test_sidecar_holds_no_unwrapped_secret` |
| INV-5 | `tests/features/recovery_key/test_recovery_code.py::test_code_never_reaches_a_plaintext_surface` |
| INV-6 | `tests/features/recovery_key/test_recovery_code.py::test_valid_check_symbol_does_not_authenticate` |
| INV-7 | `tests/features/recovery_key/test_migration.py::test_every_crash_point_still_opens` |
| INV-8 | `tests/features/recovery_key/test_migration.py::test_migration_preserves_every_row` |
| INV-9 | `tests/features/recovery_key/test_recovery_unlock.py::test_recovery_unlock_forces_a_new_master_password` |
| INV-10 | `tests/features/recovery_key/test_recovery_unlock.py::test_recovery_attempts_share_the_password_backoff` |
| INV-11 | `tests/features/recovery_key/test_recovery_code.py::test_hint_rejects_the_recovery_code` |
| INV-12 | `tests/features/recovery_key/test_sidecar_v2.py::test_declining_still_writes_the_envelope` |
| The construction is cryptographically sound | **nothing** — no test in this project can establish that. It rests on AES-256-GCM and Argon2id as used, and on §4.2's AAD binding being complete. The mitigations are that no primitive is hand-rolled and that `bandit` and `pip-audit` run in the gate; neither reads a design. |
| The user actually stored the recovery code | **nothing** — unknowable to the app. §4.5's acknowledgement step records only that a screen was dismissed. This is a real limit, not a defect, and the honest mitigation is copy that says what is being given up rather than a checkbox that implies proof. |
| The recovery code is not written down somewhere insecure | **nothing** — outside the trust boundary (`docs/security-model.md` § 4). |
| The user has not lost both credentials | **nothing** — FIBR-0018 restore and FIBR-0030 reset remain the last resorts, unchanged. |
| The migration ran at all on a given user's machine | **nothing** at the time of writing — the app has no telemetry and will not gain any. A vault that never gets unlocked never migrates, which is harmless but means "every field vault is v2" is not a statement anyone can make. §15 raises what, if anything, 1.0 should do about it. |

Five of seventeen rows say `nothing`. **Three** of the five are limits of
what software can know about a human — whether the user stored the code,
stored it safely, and has not lost both credentials — and are recorded rather
than fixed. A fourth, whether a given user's vault migrated at all, is a
telemetry limit this project will not close. The fifth — that the
construction is cryptographically sound — is the one a reviewer should press
on.

## 11. Cross-doc impact

Everything here changes **in the same release as the code**, because each one
currently asserts the opposite.

| Document | Change |
|---|---|
| `docs/decisions/0003-sqlcipher-local-only-storage.md` | **A new ADR is required** (next free number, ADR-0011). ADR-0003 records under Negative that "a forgotten master password means unrecoverable data", mitigated by backup export and first-run warning copy. This spec reverses that. The new ADR states the grounds and the new guarantee; ADR-0003 gets a `Superseded in part by` line. FIBR-0019's roadmap entry requires an ADR at spec time. |
| `docs/specs/FIBR-0004.md` | INV-7 says "the sidecar contains only the salt (hex) + non-secret KDF parameters + format version", and §5 of that spec records the exact seven-field shape. Both become false. Amend to *no unwrapped key material*; do not delete the invariant, the property still holds in its weaker form. |
| `docs/specs/FIBR-0014.md` | D4 prescribes the restore path this change replaces — mint fresh `KdfParams`, derive the new master key from that salt, rekey, and "persist **that same** `KdfParams` as the new sidecar". After this, restore mints a DEK and persists a v2 slots sidecar. Left standing, D4 remains the canonical contract for exactly the code the row below changes, and the next reader of `docs/specs/FIBR-0014.md` rebuilds the v1 path. |
| `docs/security-model.md` § 5 INV-11 | It reads "A stored password hint never contains the master password verbatim", and names `services/password_hint.validate_hint` as the falsifying surface. This spec widens the guarantee to the recovery code and moves the new leg into the hint pair's I/O half. Both halves of that row need amending in `docs/security-model.md`. |
| `docs/security-model.md` § 5 | INV-2 says Argon2id derives a 32-byte output — "SQLCipher's raw-key size; these two lengths are finbreak's own choices". After this it derives a KEK and SQLCipher's key is the DEK. INV-3's key-lifetime clause must cover the DEK and both KEKs. New invariants for the envelope and for the recovery code. |
| `docs/security-model.md` § 1 | A2 reads "Unlocks everything. Never stored anywhere." — still true of the password, but no longer the whole story. A3 describes the derived key as what "Decrypts the vault; lives only in memory while unlocked" — it now decrypts a *slot*, not the vault. A new asset row for the recovery code. |
| `docs/glossary.md` | The Master password entry ends "Never stored; no recovery if forgotten." — the last clause is reversed. Add "recovery key", "data key (DEK)", "key-encryption key (KEK)". |
| `src/finbreak/ui/first_run.py` | The warning reads "There is no password recovery — if you forget this password," and continues "your data cannot be recovered." It becomes false the moment this ships. User-facing and load-bearing; it changes in the same commit. |
| `CLAUDE.md` | § Module map gains `keywrap.py` and `services/recovery_code.py`. |
| `README.md` | The security section must not still say the password is the only key. |
| `CHANGELOG.md` | A user-facing entry saying plainly what the recovery code is, and that existing vaults upgrade automatically on next unlock. |
| `tests/features/vault/test_vault.py` | `test_INV7_sidecar_holds_no_secret` asserts the exact seven-field key set and necessarily fails. Replaced by INV-4's test, not deleted — the property still matters, the shape changed. |
| `tests/features/prose_checks/test_prose_checks.py` | `recovery_key` added to `_NO_PROSE` (§7). |
| `src/finbreak/models.py` | `FORMAT_VERSION` stays `1` and keeps belonging to the `.fbk` params record; a separate `SIDECAR_VERSION = 2` carries the vault sidecar's version, under its own `sidecar_version` field, and `KdfParams.to_sidecar_dict()` must not start stamping the new one (§4.4). Bumping the shared constant breaks every `.fbk` restore. |
| `src/finbreak/ui/_password_hint.py` | Gains the recovery-slot trial-unwrap for INV-11 — it is the I/O half of the hint pair, and `services/password_hint.py` stays pure. |
| `src/finbreak/vault.py` | `create` ends by calling `_write_sidecar(params)`, serialising the flat v1 object — §4.5 step 6 removes that write, leaving the sidecar to step 7. `close` also needs the WAL siblings dealt with at §13's S5. |
| `src/finbreak/services/backup.py` | `restore_backup` re-keys a restored copy with `rekey(master_key)`. It must instead mint a DEK and write a v2 sidecar, or a restore silently produces a v1 vault — reintroducing exactly the second key schedule D2 exists to prevent. **This is the interaction most likely to be missed.** |
| ROADMAP | FIBR-0302 (no test restores a `.fbk` from an earlier release) becomes materially more urgent: this change alters what a restored vault looks like. |

## 12. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-20 | 3, cold — genre spec, packet 138 KB / 45 windows, zero-check clean | 5 | 3 | 2 | 1 | **Eleven verified, eleven fixed; none dismissed.** **Two findings came back from all three lanes independently**, the strongest signal the loop produced. First: INV-11 requires the plaintext recovery code to check a hint against it, while INV-5 forbids retaining it and the hint is set from Settings long after the one-time display — so the check had no input at all. Rewritten to need no stored code: scan the hint for a check-symbol-valid Crockford candidate and trial-unwrap it against `slots.recovery`. Second: §4.3 excluded `U` from the alphabet while specifying a **mod-37** check symbol, whose alphabet is the 32 data symbols plus `*~$=U` — so two builders emit different codes and a code written on paper under one is rejected by the other, permanently, since D5 makes it valid forever. **The best single finding was a false claim about the tree**: §4.5 called `Vault.create` *unchanged apart from what it is handed*, and `create` ends by calling `_write_sidecar(params)`, which serialises the flat v1 object — a conformer would have shipped first-run writing a v1 sidecar, the exact second key schedule D2 exists to prevent. **Two more were migration defects that would have wedged a user's vault**: `export_to` pre-creates `O_EXCL` and unlinks nothing, so an interrupted S1 leaves debris that makes every retry raise `FileExistsError` (S1 now unlinks first); and a vault is four files, not two — `journal_mode = WAL` means a `-wal` written under the OLD key would survive S5 and have SQLite recover the new database from it (S5 now closes both connections and removes the siblings). Also fixed: INV-10's *Breaks when* named instance identity, but `UnlockThrottle` is stateless beyond `window.ini` so two instances share the counter by construction and the invariant would have tested nothing; §4.4's "moves to reading `kdf`" read as a v2-only loader, which would reject every vault in the field and leave §13's migration unable to run; INV-1 was unqualified and false of the `.fbk` container's credential-derived key; §15's release arithmetic said `0.2.0` where versioning.md § 4.2 sends a § 3.2 MINOR shifted down one place to PATCH; and INV-12's SHA-256-of-`vault.db` witness is flaky under WAL, replaced by comparing the unwrapped DEK. Three collateral items swept and fixed. **One defect was mine, in the brief**: the packet asserted `roadmap_query` returns ten bullets where it returns seven — two lanes flagged it and correctly declined to file it; corrected before loop 2, per *a lane finding that contradicts the brief is evidence against the brief first*. |
| 2 | 2026-08-20 | 3, cold — identical brief, packet rebuilt from disk | 1 | 4 | 4 | 2 | **Eleven verified, eleven fixed; none dismissed. Five of the eleven landed on text loop 1 wrote** — the collateral pattern, at 45%. **All three lanes found the same defect again**: INV-11's trial-unwrap was placed inside `services/password_hint.py`, whose own contract is to be pure — no Qt, no I/O — while the only sidecar locator sits in a module importing PySide6. The seam moved to `ui/_password_hint.py`, which is the I/O half of that pair. **The two best findings were test clauses that could not fail.** INV-1's test derived KEK-master and asserted the vault does not open — which is equally true under §8.1's *rejected* design, so the implementation this spec most wants to exclude would have shipped green against the invariant meant to exclude it; a second leg now creates two vaults under the same password and asserts their DEKs differ. And INV-3's tamper leg lowered `kdf.memory_kib` to test the AAD binding, but `ARGON2_MEMORY_FLOOR_KIB` equals the pinned `ARGON2_MEMORY_KIB` (both 47104), so any lowering is refused by `validate_params` before `unwrap_dek` is reached — the leg could never pass, and the plausible fix is to loosen the floor, weakening the guard the leg was testing. **One Q1, verified by running it**: §4.4 and §13.4 claimed an older build meets a v2 sidecar on the version check. It does not — the required-fields gate fires first, so the user is told the file is *missing or damaged* and pointed at a restore over an intact vault, which is the premise §15.3 was deciding on. Fed a v2-shaped sidecar to the real loader to confirm. **The largest gap was a whole population**: §13 migrated a vault and never said whether it gets a recovery slot, so the feature would have shipped to nobody who already had data (now D7). Also fixed: `secrets.token_bytes` is immutable where every key parameter is annotated `bytearray` and security-model INV-3 requires a wipeable buffer; `models.FORMAT_VERSION` is shared with the `.fbk` params record, so bumping it to 2 would break every backup restore (a separate `SIDECAR_FORMAT_VERSION` now carries the sidecar); INV-4's *exactly* contradicted S3's two migration-only fields; §13.4 settled a limb §15.1 calls open; INV-11 scanned for a 28-symbol run in a code displayed with hyphens every four; and `DeriveWorker` emits one key per run, so two KEKs are two sequential runs. Four mechanical corrections rode along, including a sidecar-growth estimate of "under 300 bytes" replaced by a measured 480. Four collateral items swept; two more were introduced by this loop's own fixes and caught by 4c before the commit. |
| 3 | 2026-08-20 | 3, cold — identical brief, packet rebuilt from disk | 0 | 4 | 4 | 1 | **Nine verified, nine fixed; none dismissed. CAP REACHED** (3, this project's override for every genre). **A CALM cap: 3 of the 9 landed on text this run wrote (33%)**, measured by `git log -S` on each finding's anchor — down from 45% at loop 2, so the document held more defects than the cap held loops and shipping is the right exit. Not one Q1: every defect this loop was a contradiction, an unspecified decision, or a test that could not fail. **All three lanes found the same defect**: `validate_params`' FIRST check is `format_version != FORMAT_VERSION`, and §4.4's v2 file also carried a `format_version`, so a per-slot `KdfParams` built from the file would refuse every v2 vault — shown to the user as a damaged file over an intact vault. The field is renamed `sidecar_version` rather than documented around, which removes the collision instead of warning about it. **The deepest finding took two lanes and a settled disagreement.** INV-3's tamper test claimed to lock the AAD binding; it could not. Renaming a slot and unwrapping with KEK-master fails because the slot keeps the recovery salt, so the key is simply wrong — green against an implementation whose AAD is `b""`. And the cost parameters are bound by the derivation, not the AAD, since they are inputs to `derive_key`. One lane read the memory floor as blocking the leg and another read it as reaching `unwrap_dek`; both were right about the mechanism and only the second finding was the defect. The rename leg now unwraps with KEK-**recovery**, leaving the slot name as the only difference, and the spec says outright that the cost binding is defence in depth a test cannot demonstrate. **Two lanes each found the two migration defects.** §13 never said where the migration gets the plaintext master password — and it cannot: `_on_derived` hands `complete_unlock` the derived key only. And S3 preserved the v1 salt but not the v1 COST parameters, which `crypto.py`'s own comment says an existing vault records below a later-raised pin; after any pin raise the resume path would derive the wrong key and refuse an intact vault, the exact loss INV-7 forbids. Both are answered by one decision, now §13.1: `slots.master` inherits the v1 salt AND costs, so the key already derived at unlock IS KEK-master — no re-derivation, no password plumbing, no pin hazard, and `legacy_salt_hex` deleted as the same fact written twice. Also fixed: a mistyped password on a migration-pending vault fell through the whole resume ladder and told the user their vault was corrupt (§13.3 gains a step 0); §11 omitted `docs/specs/FIBR-0014.md`, whose D4 is the canonical restore contract this change falsifies, and security-model INV-11, which this spec widens; the decline point was contradictory between D3, D7 and §4.5 (now one write at step 9, on Keep); and `export_to` pins `cipher_compatibility` where `create` does not, so a migrated vault would become unopenable the moment a wheel bump moves the default. §13 renumbered to four subsections; four collateral items swept, two more caught by 4c before the commit. |

## 13. Migration / compatibility

Every vault in the field is `format_version: 1`. D2 migrates them at the next
successful unlock.

### 13.1 The master slot inherits the v1 schedule

**`slots.master` carries the v1 vault's own salt and its own recorded cost
parameters, unchanged.** Not fresh ones. This is the decision the rest of §13
rests on, and it removes three problems at once:

1. **No re-derivation, and no plumbing.** The key the unlock path has already
   derived *is* KEK-master, because it is the same password, the same salt and
   the same costs. Nothing has to carry the plaintext master password past
   derivation — which matters, because it does not survive today:
   `ui/unlock.py::_on_derived` hands `AuthService.complete_unlock` the derived
   key only, and widening that seam would lengthen the lifetime of a buffer
   `security-model.md` INV-3 governs. §14's migration cost stays as written
   because there is no extra derivation to count.
2. **The legacy key stays reproducible.** `derive_key(password,
   slots.master.salt, kdf)` reproduces the v1 database key exactly, which is
   what makes §13.3's resume ladder work with **no** separate `legacy_salt_hex`
   field. An earlier draft carried one; it was the same fact written twice.
3. **A raised pin cannot strand a vault.** `crypto.py` keeps
   `ARGON2_MEMORY_FLOOR_KIB` distinct from `ARGON2_MEMORY_KIB` precisely so
   that raising the pin does not lock out an existing vault recording the
   older value. Had `kdf` been written with today's pin while the master slot
   was derived under yesterday's, every post-raise migration would derive the
   wrong key and land on §13.3's terminal branch — refusing an intact vault,
   which is the exact loss INV-7 exists to prevent.

The cost is stated plainly in §4.4: a migrated vault is as strong as it was
and no stronger, and a recovery slot added to it later inherits the same
costs.

### 13.2 The sequence

Given a v1 sidecar and a password that opens the vault:

| Step | Action |
|---|---|
| **S1** | Unlink any existing `vault.db.migrating` — `export_to` pre-creates `O_EXCL`, so a stale one from an interrupted run wedges every retry. Generate the DEK. Write `vault.db.migrating` via `Vault.export_to(dek)`. `fsync`. |
| **S2** | Open `vault.db.migrating` with the DEK. Run `PRAGMA integrity_check` and compare per-table row counts against the live vault. Abort on any mismatch, deleting the temporary file. |
| **S3** | Build the v2 sidecar. `slots.master` takes the v1 salt and the v1 cost parameters (§13.1), and `kdf` records those same costs. One field is present **only** while migrating: `migration_pending: true`. Write to `vault.kdf.json.migrating`. `fsync`. |
| **S4** | `os.replace` the sidecar. |
| **S5** | Close both connections first — the live vault's and the verified migrating one's — so each checkpoints and drops its `-wal` / `-shm` siblings, then remove any that remain. **Then** `os.replace` the database. |
| **S6** | Rewrite the sidecar without `migration_pending`. `os.replace`. |

The original pair is not modified until S4, and by then the replacement has
been built and verified.

**One property of S1's product needs recording: it is written at an explicit
cipher level.** `Vault.export_to` issues
`PRAGMA backup.cipher_compatibility = SQLCIPHER_COMPAT` (4), where a `create`d
vault issues no such PRAGMA and takes the library default, and a normal
`Vault.open` passes `cipher_compat=None`. They agree today. They stop agreeing
the moment a `sqlcipher3-wheels` bump moves the default — which is the reason
`vault.py` pins the constant at all — and a migrated vault would then be
unopenable by the very build that migrated it. **So S3 records the level in
the v2 sidecar and every later open passes it**, exactly as
`BackupService._open_backup_vault` already does from a `.fbk` manifest. The
precedent exists; this only extends it to the installed vault.

### 13.3 Resume, which is what makes INV-7 true

**§13.1's inheritance is the whole safety net**, and it costs nothing —
the v1 salt and costs were already public in the plaintext sidecar. It means
that in the window between S4 and S5, where the sidecar describes the new
schedule and the database is still on the old one, the old schedule is still
fully recorded: KEK-master *is* the v1 database key.

On open, with a v2 sidecar carrying `migration_pending`:

0. Derive KEK-master and unwrap `slots.master`.
   - **The unwrap fails** → this is an ordinary wrong password, not a broken
     migration. Report it as a failed attempt, advance the shared throttle
     (§6, INV-10), and **do not enter the ladder at all**. Without this
     branch a single typo on a migration-pending vault falls through every
     step below to the terminal bullet, and the user is told their vault is
     corrupt for mistyping.
   - **The unwrap succeeds** → continue with the DEK.
1. Try the DEK against `vault.db`.
   - **Opens** → the crash was after S5. Run S6. Done.
   - **Does not open** → continue.
2. If `vault.db.migrating` exists, try the DEK against it.
   - **Opens** → the crash was between S4 and S5. Run S5, then S6.
   - **Does not open** → delete it as unusable and continue.
3. Try KEK-master itself against `vault.db` — under §13.1 it is the v1
   database key, so no separate derivation is needed.
   - **Opens** → the crash was at or before S4. Restart from S1.
   - **Does not open** → every route is exhausted, **and the password was
     right**, which is what makes this branch meaningful. Refuse, change
     nothing, and tell the user the vault and its key record disagree. Do not
     offer the destructive reset from here.

A v1 sidecar means the vault has not migrated — open as today, then run
S1–S6. **A stray `vault.db.migrating` beside a v1 sidecar is debris from an
interrupted S1, never a usable vault**: nothing was swapped, so S1 unlinks it
and starts again.

### 13.4 Compatibility

- **Forward** — automatic, and asks nothing of the user at the moment it
  runs. Whether that nonetheless counts as § 3.1 "user action" is **§15.1's
  question, not settled here**; this section states the mechanism only.
- **Backward** — a v2 vault cannot be opened by a build that predates this
  change. It fails **closed**, never misreading the file — but not with a
  helpful error: §4.4 records that the required-fields gate fires first, so
  the user is told the security-settings file is *missing or damaged* and
  pointed at a backup restore, over an intact vault. That is a real one-way
  door **presented as data loss**, which is what makes §15.3's question
  sharper than a release note.
- **`.fbk` backups** — a backup exported before this change restores into a
  vault that must end up v2 (§11). A backup exported after it likewise. §9
  defers the cross-version test itself to FIBR-0302.

## 14. Resource cost

- **Disk, transient:** one full copy of the vault during S1–S5, released at
  S6. Peak usage is roughly twice the vault size, once, at migration.
- **Disk, permanent:** the sidecar grows by two slots — **~480 bytes**,
  measured by rendering the JSON at the field widths §4.4 fixes (240 bytes a
  slot). An earlier draft said "under 300", which was an estimate rather than
  a measurement.
- **Memory:** one extra 32-byte DEK and, briefly, one extra 32-byte KEK. The
  Argon2id working set is unchanged at 46 MiB per derivation and is not held
  concurrently for both slots.
- **Time, first run:** two Argon2id derivations instead of one, so roughly
  double. It is a one-time cost on a background worker (`DeriveWorker`).
- **Time, unlock:** unchanged — one derivation, then an AES-GCM unwrap of 32
  bytes, which is negligible beside it.
- **Time, migration:** one full SQLCipher export plus an integrity check,
  once. Proportional to vault size.
- **New dependencies:** none. `cryptography` and `argon2-cffi` are already
  pinned runtime dependencies, and the Crockford codec is written here (§4.3).

## 15. Open questions

1. **Does this force user action, in § 3.1's sense?** That is the whole
   question; the arithmetic under it is not in doubt.
   `docs/standards/versioning.md` § 4.2 reserves the MINOR bump for a
   § 3.1-class change — a § 2 break **or** a change requiring user action —
   and sends everything else to PATCH. A new capability is § 3.2 MINOR, and
   MINOR shifted down one place is PATCH: `0.1.23`. So `0.2.0` is owed only
   if showing the user a recovery code to write down, or migrating their
   vault, counts as requiring user action. Settle it before the release
   rather than at it.

2. **Should 1.0 refuse to ship while any supported path can still produce a v1
   vault?** §10 records that nothing can tell us a given user's vault migrated.
   If a v1 vault can still be *created* by any route after this ships — an old
   build, a restore path missed in §11 — then "one key schedule" is an
   intention rather than a fact.

3. **How loudly should the one-way door be announced?** §13.4 makes
   downgrade impossible after migration. A user who upgrades, migrates, and
   then wants to go back to the previous AppImage cannot open their vault. The
   options are a release note, a pre-migration prompt, or an automatic `.fbk`
   export before S1. The third is the safest and the most intrusive.

4. **Should the recovery code be shown again on demand?** D5 makes it
   permanently valid, but INV-5 forbids storing it, so the app cannot show it
   twice — only replace it. Whether the Settings affordance should therefore
   read "Replace" rather than "View" is a UX call with a security consequence,
   and users will look for "View".
