# ADR-0011: A key envelope — the vault is encrypted by a random data key, wrapped once per credential

- **Status:** Accepted (FIBR-0019's spec cleared `review-contract` — the run
  stopped at its cap, 2026-08-20, four loops, with the design in this ADR
  unchanged)
- **Date:** 2026-08-21
- **Deciders:** Project lead, Claude
- **Related:**
  [docs/specs/FIBR-0019-master-password-recovery-key.md](../specs/FIBR-0019-master-password-recovery-key.md)
  (the design this ADR backs),
  [ADR-0003](0003-sqlcipher-local-only-storage.md) (the storage decision whose
  "no password recovery" consequence this reverses in part),
  [docs/security-model.md](../security-model.md) (the invariants that move with
  it), [docs/specs/FIBR-0014.md](../specs/FIBR-0014.md) (backup/restore, whose
  D4 restore path this changes)

## Context

Until 1.0 there was exactly **one key**, and it was the master password.
`derive_key(password, salt, params)` produced 32 bytes and those bytes were
SQLCipher's raw key — so the set of credentials that could open a vault had one
member and could not be extended. ADR-0003 recorded the consequence honestly
under *Negative*: "a forgotten master password means unrecoverable data",
mitigated by an encrypted backup export and by first-run warning copy.

Both mitigations require foresight the user may not have had. A backup only
helps someone who took one *and* remembers its password, and the warning copy
only helps someone who read it. For a tool holding a household's financial
history, "you have lost everything" is the failure users least forgive, and the
live answer to *I forgot my password* was `AuthService.reset_vault` — which
deletes the vault.

The sequencing is what made this a 1.0 blocker rather than a 1.1 feature: **the
envelope has to exist at vault creation.** Every release shipped without it adds
more vaults that must later be re-encrypted during an update, on a user's
machine, over real financial data.

## Decision

**Three key roles replace the single one.** A random 32-byte **data key (DEK)**
is SQLCipher's raw key and never appears on disk unwrapped. A
**key-encryption key (KEK)** is derived from a credential — the master password,
or a recovery code — and wraps a copy of that same DEK into its own **slot** in
the plaintext sidecar, under AES-256-GCM with the slot name and the Argon2id
cost parameters as additional authenticated data.

Four consequences follow directly, and they are the reason for the shape:

- **Changing a credential re-wraps 32 bytes.** It never re-encrypts the
  database. `PRAGMA rekey` leaves the credential-change path entirely.
- **Adding a credential is adding a slot.** Biometric unlock (FIBR-0020) becomes
  a slot rather than a redesign; `slots` is deliberately an open map.
- **A recovery code can exist at all.** 135 bits, Crockford base32, 28 symbols —
  a full-strength second credential the user is given once and the app never
  retains.
- **Every existing vault must be converted**, automatically, at its next
  successful unlock. Two key schedules in the field is the thing this decision
  exists to avoid: after 1.0 there must be exactly one way a vault is keyed, or
  every later change has to reason about both.

The spec owns the mechanism. What belongs here is the trade, and it is a real
one: this ADR *widens* what a plaintext file beside the vault holds. The sidecar
used to carry only a salt and non-secret parameters. It now carries a wrapped
DEK per slot. That is ciphertext and opens nothing without a credential, but
FIBR-0004 INV-7's claim of *no secret* is genuinely weaker now — the honest
replacement is *no **unwrapped** key material*, and it is written down rather
than glossed.

## Consequences

**Positive:**

- A forgotten master password stops being unrecoverable data loss. The
  destructive reset remains, as a last resort rather than the answer.
- Credential changes become cheap and instant at any vault size.
- A third credential is now an additive change rather than a re-encrypt.

**Negative:**

- **The plaintext sidecar carries a wrapped key.** Strictly weaker than what it
  carried before; the attacker's target is now a file whose contents are worth
  running Argon2id against. The mitigation is that the cost parameters are
  bound into the AAD and enforced by a directional floor, so they cannot be
  weakened by editing the file.
- **A one-way door on downgrade.** A vault converted to the envelope cannot be
  opened by a build predating it, and it fails on the required-fields gate
  rather than the version check — so the user is told the security-settings file
  is *missing or damaged*, over an intact vault. A byte copy of the pre-upgrade
  pair exists for the conversion window and is removed once it succeeds; after
  that the answer is a `.fbk` taken before upgrading.
- **The user can lose the recovery code too**, and nothing in the app can know
  whether they stored it. The acknowledgement step records only that a screen
  was dismissed. Copy that says plainly what is being given up is the honest
  mitigation; a checkbox implying proof is not.
- **First-run costs two Argon2id derivations** where it cost one, and a vault
  migrated from v1 is exactly as strong as it was and no stronger — it inherits
  its own recorded cost parameters rather than today's pin, which is what stops
  a later-raised pin from stranding it.

**Neutral:**

- The `.fbk` backup container keeps its own schedule: its inner `vault.db` is
  keyed directly by `derive_key(backup_password, …)` and is out of scope here.
