# ADR-0003: SQLCipher + Argon2id, local-only, per-OS-user storage

- **Status:** Accepted (superseded in part by FIBR-0054 — see banner)
- **Date:** 2026-06-30
- **Deciders:** Project lead, Claude
- **Related:** [docs/discovery.md](../discovery.md), [docs/design.md](../design.md) (Security)

> **Superseded in part by [FIBR-0054](../specs/FIBR-0054.md).** This ADR's
> "no network surface" / "no network connections" absolutes (below) predate the
> opt-in, off-by-default update check FIBR-0054 adds. The **storage** decision
> here is unchanged, and the threat model's **confidentiality** guarantee holds
> unchanged — the update flow pulls a signed release *in* and never sends
> financial data *out*, so "no third party ever holds the data" still holds. The
> one new **integrity** concern — a tampered release — is not excluded but
> **mitigated**: a download is installed only if its Ed25519 signature verifies
> (FIBR-0054 INV-4). Read the two no-network phrases as "no network access other
> than that one consented, signature-gated update check."

## Context

The app holds a person's complete financial history — among the most sensitive
data a consumer app can store. The threat model is **a lost or stolen device, a
shared computer, or a leaked backup file**, not a network attacker (the app has
no network surface). Requirements: data unreadable at rest without the user's
secret; no plaintext secrets anywhere; separation between people who share a
machine; no third party ever holds the data.

Alternatives considered:

- **Plaintext SQLite** — simplest, but the file is readable by anyone with disk
  access. Rejected.
- **App-level field encryption over plaintext SQLite** — encrypts values but
  leaks structure/metadata, is easy to implement wrongly, and complicates
  queries. Rejected.
- **OS keychain for a data key** — convenient but ties data to the keychain and
  weakens the "your password is the only key" guarantee. Rejected as the primary
  mechanism.
- **SQLCipher (whole-file AES-256) keyed by an Argon2id-derived key** — the
  whole database is opaque at rest; one well-tested mechanism.

## Decision

Store all data in a single **SQLCipher** database (AES-256, whole-file) per OS
user, in `QStandardPaths.AppDataLocation`. Derive the database key from the
user's **master password via Argon2id**. The Argon2id output is passed as
SQLCipher's **raw** key (the `x'…'` raw-key pragma), so **Argon2id — not
SQLCipher's built-in PBKDF2 — is the key-derivation function**. Never persist
the password or key; hold the key in memory only while unlocked and clear it on
lock/auto-lock. The app makes **no network connections**.

## Consequences

**Positive:**

- A stolen DB file is useless without the master password.
- Per-OS-user directories give multi-profile separation for free.
- One auditable crypto path (CryptoService); no bespoke field crypto.

**Negative:**

- **No password recovery** — a forgotten master password means unrecoverable
  data. Mitigated by an explicit encrypted backup-export feature, and clear
  first-run warning copy.
- SQLCipher bindings add a native dependency that each platform's packaging must
  bundle correctly (validated in P01).
- Argon2id parameters are pinned in security-model.md INV-2 (chosen
  2026-06-30 from a dated
  [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
  snapshot, frozen — see INV-2) and recorded with the vault so they
  can't be silently weakened.

**Neutral:**

- Encryption is transparent to the repository layer once the key is set
  (`PRAGMA key`), so application code is largely unaware of it.
