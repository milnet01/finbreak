# vault (security spine) — feature test contract

**Theme:** the P02 vertical slice — master password → Argon2id → SQLCipher
vault → one manual transaction → table → lock — proven end-to-end.

This is the test-side contract for [`docs/specs/FIBR-0004.md`](../../../docs/specs/FIBR-0004.md);
each `INV-N` below maps to that design spec's invariant of the same number.
`test_vault.py` enforces them. Every on-disk vault uses `tmp_path`; no test
touches the network or real financial data (testing.md § 6).

## Invariants

- **INV-1** — The created vault is AES-256 ciphertext at rest (first 16 bytes
  are not the SQLite magic); re-opening with the correct raw key succeeds and
  reports `cipher_use_hmac` on + `HMAC_SHA512`; a wrong key or a flipped body
  byte raises `sqlcipher3.dbapi2.DatabaseError` on first read. Source:
  FIBR-0004 INV-1.
- **INV-2a** — `derive_key` returns exactly 32 bytes, is deterministic for
  fixed inputs, and salt-sensitive. Source: FIBR-0004 INV-2a.
- **INV-2b** — A recorded `memory_kib` below the pinned floor is refused with
  `KdfPolicyError`; at/above the floor validates. Source: FIBR-0004 INV-2b.
- **INV-2c** — Wrong `key_len`, wrong `salt` length, a `salt_len` field
  disagreeing with the real salt, and a malformed/missing-field sidecar all
  raise `KdfPolicyError` (never a bare `JSONDecodeError`/`KeyError`). Source:
  FIBR-0004 INV-2c.
- **INV-3** — After `lock()` / idle auto-lock / exit the key buffer is
  overwritten in place (all-zero) and the vault closed; a query while locked
  raises `VaultLockedError`; the plaintext-password buffer is wiped on
  `validate_first_run` / `first_run` / `unlock` (both success and
  wrong-password). Source: FIBR-0004 INV-3.
- **INV-4a** — One `add` is one DB transaction: a failure before commit leaves
  zero rows in a freshly re-opened vault; `Decimal("-12.34")` against a
  2-decimal currency round-trips as `amount_minor = -1234` ↔ `Decimal("-12.34")`.
  Source: FIBR-0004 INV-4a.
- **INV-4b** — Money input is validated, never silently mutated: more
  fractional digits than the exponent, a non-finite decimal, zero, an empty
  description, or a non-ISO date each raise `ValueError`; a non-zero value of
  either sign within the exponent is accepted. `ValueError` is the class for
  **every** rejection, magnitude included — past SQLite's signed 64-bit INTEGER
  (FIBR-0216) and an exponent large enough to overflow the scaling itself
  (FIBR-0222), which `ManualEntryDialog` must show rather than die on.
  Source: FIBR-0004 INV-4b.
- **INV-5** — Neither file present → first-run; both present → unlock; a
  mixed pair raises `VaultStateError`; a first-run password mismatch / empty
  password / bad currency raises `ValueError` and writes nothing; first-run
  creates the vault (settings + `schema_version`) before the sidecar. Source:
  FIBR-0004 INV-5.
- **INV-6** — Unlock/lock round-trip: the correct password opens the vault and
  the saved transaction is listable / shown in the main window's table; a wrong
  password returns `False` with no key retained and a UI error; lock wipes the
  key. Source: FIBR-0004 INV-6.
- **INV-7** — No password/key/raw-key-hex appears in the sidecar or in the
  captured `finbreak` INFO log across a first-run → unlock → lock cycle (and the
  cycle emits at least one non-secret lifecycle line); vault + sidecar are
  `0o600` on POSIX. Source: FIBR-0004 INV-7.
- **INV-8** — No `socket`/`http`/`urllib`/`requests`/`ftplib` import appears
  anywhere under `src/finbreak/`. Source: FIBR-0004 INV-8.

## Out of scope

Accounts, import, categorisation, dashboard, export; user-configurable
auto-lock; password-strength enforcement; cross-platform packaging of the
native deps. See FIBR-0004 § "Out of scope".
