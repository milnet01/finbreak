# finbreak — Security model & threat model

> **Status:** Live — the project's authoritative security & threat
> model. Every clause names the item that amended it, so this header
> keeps no amendment history of its own: one stated here goes stale
> the moment the body moves past it, and it did.
> Re-run `review-contract docs/security-model.md --genre standard` on
> each material edit; the review history is in
> [`docs/reviews/security-model-review-log.md`](reviews/security-model-review-log.md).
> **Why this exists:** finbreak holds **personal financial
> data**. Security is the load-bearing concern, so it gets its
> own document — a single place that names what we protect, what
> could go wrong, and exactly how each risk is stopped.
> **How it's used:** every `implement`-Kind spec must state how
> it upholds the **security invariants** in § 5; every `check-code`,
> `review-code` and `review-contract` pass checks against them.
> See [ADR-0003](decisions/0003-sqlcipher-local-only-storage.md)
> (storage/crypto) and
> [ADR-0007](decisions/0007-self-contained-bundled-releases.md) (bundling).

This is a deliberately plain-English document. Where a term is
unavoidable it is glossed on first use.

## 1. What we are protecting (assets)

| # | Asset | Why it matters |
|---|-------|----------------|
| A1 | **The vault** — the SQLCipher database file holding every transaction, account, rule, and financial setting (base currency, minor-unit exponent, stored PDF passwords). *Non-sensitive UI state — window geometry / toolbar state / last-active tab, plus the opt-in update-check flag and any skipped-update version (FIBR-0054), and the optional user-authored password hint (FIBR-0029) — deliberately lives in a plaintext `window.ini` sibling, not the vault (FIBR-0052 INV-5, FIBR-0054 D4); it holds no financial data, so it is not an A1 asset. The hint is readable by anyone with device access (it must be, to help before unlock), so it is enforced at set-time never to be, nor contain, the master password (INV-11).* | The whole financial picture. Its disclosure is the worst case. |
| A2 | **The master password** | Unlocks everything, by unwrapping a key slot — never by being the key. Never stored anywhere. *(Restated by FIBR-0019: it still unlocks everything, but no longer directly.)* |
| A3 | **The key-encryption key (KEK)** — what Argon2id produces from a credential (the master password, or the recovery code) and that credential's own salt. *(Was "the derived key", passed to SQLCipher as its raw key; FIBR-0019 made it a KEK.)* | Decrypts one **slot**, not the vault; lives only in memory while unlocked. |
| A3b | **The data key (DEK)** — 32 random bytes minted at vault creation, passed to SQLCipher as its **raw** key (so Argon2id, not SQLCipher's built-in PBKDF2, is still the KDF behind every credential) | Decrypts the vault. Never on disk unwrapped; lives only in memory while unlocked. |
| A8 | **The recovery code** (FIBR-0019) — 135 bits, shown once at vault creation and never retained by the app | A full-strength second credential: it opens the vault exactly as the master password does. The user stores it; the app cannot help them if they lose it. |
| A4 | **Stored statement-PDF passwords** (optional, opt-in) | Bank-document passwords; only ever live *inside* the encrypted vault. |
| A5 | **Decrypted statement data in memory during import** | A locked PDF is decrypted in RAM only; must never touch disk. |
| A6 | **Exported report PDFs** | Leave the app deliberately, password-locked by the user. |
| A7 | **The source repository (public)** | Must contain code + docs only — never a vault, a key, or real statement data. |

## 2. Trust boundaries

- **The machine the app runs on is trusted.** Data lives in the
  current OS user's app-data directory; different OS logins are
  separate by construction (ADR-0003). We do **not** defend
  against a root-level attacker on the same machine or a
  hardware key-logger — that is out of scope for a local
  desktop app and stated as such.
- **Everything off the machine is untrusted — and unreachable
  except for one opt-in, off-by-default flow.** The **shipped
  application** makes **exactly one** kind of outbound access — an
  **opt-in, off-by-default** update flow that reads the GitHub
  Releases API and, only on the user's explicit request, downloads the
  signed release assets — the platform binary (the Linux AppImage or the
  Windows `.exe`) and its `.sig` — all over `https://`, confined to
  `services/update_fetch.py` (FIBR-0054 INV-12) and never begun without
  explicit user consent (FIBR-0054 INV-1). No other network
  access exists; a downloaded update is installed only if its Ed25519
  signature verifies over the exact bytes (FIBR-0054 INV-4) — the **same**
  gate for both platforms, so the Windows self-swapping `.exe` (FIBR-0131)
  runs no unverified code. **Windows "unknown publisher" (Authenticode)
  trust is a separate, orthogonal concern (FIBR-0133) — its absence does
  not weaken this integrity gate.** The Windows install hand-off spawns a
  local helper process (a PowerShell waiter that swaps the `.exe` after
  finbreak exits); it opens no socket and touches no vault. The near-total
  absence of network code keeps the attack surface minimal. Each published
  release additionally carries a **signed `SHA256SUMS`** manifest
  (`SHA256SUMS.sig`, the same Ed25519 release key) plus a per-platform
  CycloneDX **SBOM** (`finbreak-<V>-<os>.cdx.json`) — a manual-verification
  integrity signal for users who download from the GitHub release page
  (complementary to the per-artifact `.sig` the in-app updater checks) and a
  bundled-dependency parts-list for auditing (FIBR-0096, INV-13). **Honest
  residual:** a GitHub-release-**write** attacker (no signing key) can
  *remove* the manifest signal but cannot *forge* it — the release scripts
  verify any carried other-platform line against the committed key before
  re-signing (the anti-laundering gate), so a tampered line is never
  laundered into a valid signature. The per-artifact `.sig` (FIBR-0054 INV-4)
  therefore stays the **primary** integrity gate; a user should confirm
  **their** artifact's basename actually appears in `SHA256SUMS`
  (verifying with `sha256sum -c --ignore-missing SHA256SUMS`) and treat a
  missing manifest/line as a red flag, not a bare `--ignore-missing` exit-0
  pass. (Dev/CI tooling
  such as `pip-audit` and Dependabot run in CI and the local dev gate,
  never in the shipped app — INV-8.)
- **Imported files are untrusted input.** CSV/OFX/PDF files come
  from outside and are parsed defensively (§ 4, T5).
- **A restore backup (`.fbk`) is untrusted input parsed _pre-login_.**
  The encrypted backup a user restores (FIBR-0014) is an off-device zip
  opened **before** any authentication — a distinct, higher-risk surface
  than the CSV/OFX/PDF importers. It is read with safe-zip handling (only
  the three fixed entry names, per-entry size caps checked **before**
  inflating, never `extractall`, traversal/extra/duplicate entries
  rejected), and its KDF params are re-validated against the pinned
  Argon2 floor **before any key is derived** (§ 4, T5; FIBR-0014
  INV-11/INV-12).

## 3. Threats and mitigations (STRIDE-lite)

"STRIDE" is just a checklist of the six classic ways software is
attacked. Each row: the threat → how finbreak stops it.

| # | Threat | Mitigation |
|---|--------|------------|
| T1 | **Lost/stolen laptop → someone reads the vault file** | Whole-file AES-256 encryption (SQLCipher). The file is meaningless without the key (A1, INV-1). |
| T2 | **Weak master password brute-forced** | **Argon2id** memory-hard key derivation with pinned parameters (§ 5 INV-2) makes offline guessing slow and GPU-resistant; the interactive unlock dialog additionally throttles repeated wrong attempts on a capped backoff (§ 5 INV-10). Password strength is also surfaced when a master password is CHOSEN — at first-run and at the forced reset after a recovery-code unlock — as an advisory nudge that never blocks (`services/password_strength.py`). It bands on length rather than character classes, which is what Argon2id leaves as the variable. Deliberately not an enforced INV: a minimum would lock out a vault created before it. |
| T3 | **Key or password recovered from memory / swap / a crash dump** | Key held only while unlocked; **wiped on lock and on exit**; auto-lock drops it after idle (INV-3). The plaintext password reference is cleared before the unlock routine returns. (Defending against the OS paging memory to swap is out of scope — see § 4.) The idle timeout is **user-configurable** (FIBR-0055) and may be set to **"Never"** (FIBR-0135), which disables *only* the idle drop — the key is still wiped on manual lock and on exit, and the password is still required on open. An unattended, unlocked session then stays unlocked: an accepted user choice, not a silent default. |
| T4 | **Decrypted bank statement leaks to disk** | Locked input PDFs are decrypted **in memory only**; no decrypted content is *deliberately* written to disk or temp files (A5, INV-4). (Defending against the OS paging memory to swap is out of scope — § 4.) |
| T5 | **Malicious import file** (crafted CSV/OFX/PDF — parser crash, path traversal, zip-bomb-style resource exhaustion, formula injection) **or a crafted restore `.fbk`** (a zip parsed **pre-login**) | Parsers run defensively: bounded resource use (file/page/row caps), no `eval`, no shell-out; CSV cells are treated as data, never spreadsheet formulas; per-row errors are reported, not fatal (INV-5a/5b/5c). The restore `.fbk` — parsed before any authentication — reads only the three fixed entry names with per-entry caps checked **before** inflating (never `extractall`), rejects traversal/extra/duplicate entries, and re-validates the embedded KDF params against the pinned floor before deriving any key (FIBR-0014 INV-11/INV-12). **One documented residual:** the PDF **decompressed-page-size** vector is assessed + accepted, not bounded — see INV-5b / FIBR-0075. A backup `.fbk` can now also be *verified* read-only (FIBR-0033) through the **same** FIBR-0014 guards, but **post-login** (from Settings, D5) — a lower-risk surface than restore's pre-login parse, adding **no new pre-login attack surface**. |
| T6 | **Secret accidentally committed to the public repo** | `gitleaks` in CI **and** the local pre-push script; `.gitignore` excludes `*.db`/vault/build output; no real financial data in tests — only synthetic fixtures (INV-6, A7). |
| T7 | **Vulnerable third-party dependency (known CVE), or a hijacked / typosquatted release that has no CVE at all** | `pip-audit` in CI + local script fails the build on a known-vulnerable dependency; Dependabot raises bumps; latest-stable policy (global rule § 5). The gate runs it **twice, against two different databases** — the default PyPI Advisory DB and OSV.dev (`-s osv`, `FIBR-0227`) — because neither is a superset and only OSV.dev imports the OpenSSF **Malicious Packages** feed, which is what covers the no-CVE half of this row. |
| T8 | **Insecure code pattern introduced** (hardcoded secret, weak hash, `subprocess(shell=True)`, etc.) | `bandit` security linter in CI + local script. |
| T9 | **Tampered vault / downgrade of crypto settings** | SQLCipher authenticates **each page with a per-page HMAC** (HMAC-SHA512 by default) — tamper-evident. AES gives confidentiality, **not** integrity, so the HMAC must stay enabled; a tampered page fails to open (INV-1). The recorded KDF parameters can't be downgraded **below the pinned floor** on open (INV-2). Both are asserted by the FIBR-0004 (P02) spec's tests. |
| T10 | **Exported report shared, then read by the wrong person** | Export **can be** password-locked with AES-256 (`pikepdf`) using a password the user sets at export time (A6, INV-7), and the user is reminded the password is theirs to share safely. **The password is optional** (`FIBR-0013 amends T10`): a blank field exports a plain PDF, which is the *default* path since the field starts empty. So this row's mitigation is **user-elected, not automatic** — an exported report carries dates, descriptions, counterparties, per-transaction amounts and per-account totals, and if the user leaves the password blank none of it is protected by the file. Two things narrow the residual: the file is written mode `0600` so it is not readable by other local users (FIBR-0204), and it carries **no account numbers or balances** (`_accounts_in_scope` reads only id/name). Sharing an unlocked export remains a deliberate user choice with a real disclosure cost. |
| T11 | **Forgotten master password** | By design there is **no backdoor** (a backdoor is a vulnerability). **The first mitigation is the recovery code** (FIBR-0019, A8): a full-strength second credential the user was given at vault creation, which opens the vault exactly as the master password does and then forces a new one (D6). Try it before anything below — this row predated the key envelope, and a reader who reached "start over" from here would destroy a vault the recovery code still opens. The second mitigation is the **encrypted backup** (FIBR-0014), keyed by a **separate backup password** the user keeps safe: restoring needs the backup password + a **new** master password, **never** the forgotten one, so the backup **does** recover a forgotten master password. It is "only as recoverable as its own secret" — if the recovery code, the master password **and** the backup password are all lost, the data is unrecoverable (the deliberate confidentiality-over-availability trade). The backup's own KDF params are re-validated against the pinned floor on restore (INV-2), so a tampered `.fbk` can't force a weak KDF. *The recovery path is testable (FIBR-0014 INV-3); the no-backdoor stance is not.* A user who has genuinely lost all three secrets and has no usable backup can, as a last resort, **start over** — a double-confirmed destructive reset (FIBR-0030, INV-12) that deletes the vault's complete on-disk footprint and returns to first-run. It introduces **no new attacker capability** (local-access destruction is already out of scope, § 4) and destroys only data that was already unrecoverable; the friction (a warning **and** a typed-`DELETE` confirm) guards against *accidental* triggering, not an adversary. |
| T12 | **Sensitive data leaked via the log file** | The local rotating log never records transaction contents, passwords, keys, or decrypted data (INV-9). |
| T13 | **A copied sensitive value lingers on the shared clipboard** | Copy is **user-initiated**, and covers a transaction's **amount / description** (FIBR-0032) and the **one-time recovery code** (FIBR-0019 § 4.5). The code is copyable by design — the user has to get it onto paper or into a password manager — and IS auto-cleared, by a guard the window owns rather than the dialog, so the clear outlives the dialog's teardown (FIBR-0310 R1). The statement PDF password is **not** copyable (no new secret crosses into the UI; FIBR-0128 INV-1 preserved). **An account number becomes copyable from the Accounts form field while reveal is on** (`FIBR-0198 amends T13`): FIBR-0113 masks both surfaces and leaves this row true, but FIBR-0198's toggle puts the raw value into a `QLineEdit` in `Normal` echo mode, which Ctrl+C reads (`Password` echo suppresses it). **That copy is NOT auto-cleared** — the auto-clear below is `ClipboardAutoClear`, which the transactions list and the recovery-code display each build (`ui/transactions.py`, `ui/main_window.py`, `ui/recovery_key.py`); a Ctrl+C out of a `Normal`-echo field goes to the system clipboard through Qt's built-in copy without passing through any of them, so an account number copied during a 30-second reveal outlives the reveal indefinitely. This is a deliberate gap, not an oversight: the user copies the number in order to paste it into a payment, and clearing it mid-payment would defeat the reason the reveal exists. A copied value is **auto-cleared** after a configurable timeout (default 30s), but **only if the clipboard still holds our value** — a value the user copied since is never clobbered. **Three residuals, stated honestly:** (a) a clipboard-history manager that snapshots on copy is outside auto-clear's reach; (b) on a **mid-timeout app exit or vault lock** the pending clear-timer dies unfired, so the value can outlive its timeout on platforms where the clipboard survives the app — auto-clear is best-effort, not guaranteed on process exit (lifecycle-clear is a deferred follow-up); and (c) **`0` ("Never")** is an accepted user choice that forgoes auto-clear (the parallel to T3's honestly-stated "Never"). |
| T14 | **A displayed account number is read off the screen** (shoulder-surfing, a screenshot, a shared screen) | The account number is **masked by default** on both surfaces that show it — the table cell renders `"•••• 7890"` and the form field is a `Password`-echo `QLineEdit` (FIBR-0113 D2). Revealing it is an explicit, deliberate user action (FIBR-0198's "Show account numbers" checkbox), and the reveal is **session-scoped** — written to no store, gone after a lock or a restart (FIBR-0198 INV-1) — and **bounded**: it re-masks itself after 30 seconds without the user doing anything (INV-2), so a reveal left on when someone walks away does not give the masking back. The value itself is already encrypted at rest inside the vault (A1), so this row is about *display* exposure only. **Two residuals:** the timer is a convenience bound on what is on screen, not a security boundary — a revealed number is visible for up to 30 seconds regardless, and anything that can read the process's memory can read the value whether it is masked or not; and a value copied during a reveal is T13's, where the un-auto-cleared clipboard gap is stated. |

## 4. Out of scope (stated honestly)

- A root/admin attacker or malware already running as the same
  OS user — a local app cannot defend its own memory against the
  OS it runs on.
- Hardware attacks (cold-boot, key-loggers, evil-maid).
- Side-channel/timing attacks against the crypto primitives — we
  rely on the vetted SQLCipher/Argon2 implementations rather than
  rolling our own.
- Multi-user *server* access control — separation is per-OS-user,
  not a login system (ADR-0003).

These are listed so a reviewer knows they were considered and
consciously excluded, not missed.

## 5. Security invariants (the enforceable checklist)

Every spec and every review pass checks these. Each is phrased to
be checkable. Enforcement arrives in step with the code:

- **From P01 on:** INV-6 and the no-`eval` / no-shell legs of
  INV-5a, via the static gate (§ 6). INV-5a's CSV-as-data and
  no-content-derived-path legs are unit-tested with the import
  specs (FIBR-0007+).
- **With the phase that builds the code each governs:** INV-1,
  INV-2, INV-3, INV-3b, INV-3c, INV-3d, INV-4, INV-5b, INV-5c, INV-7,
  INV-9, INV-10, INV-11, INV-12, INV-13 — asserted by tests that land
  alongside the vault, crypto, import, export, and logging paths (none
  of which exist yet at P01). **This is the only enumeration**; § 6
  points here rather than repeating it, because two lists schedule two
  different test sets and the shorter one silently drops an invariant.
- **INV-8 (single opt-in egress)** is enforced two ways: no networking
  dependency is declared in `pyproject.toml` (verifiable from P01),
  and a forbidden-import check (no `socket` / `http` / `requests` /
  `urllib` / `ftplib` in `src/finbreak/`) lands with the first runtime
  code. Since FIBR-0054 that check **allowlists `urllib` in exactly
  one file** — `services/update_fetch.py`, the opt-in updater's sole
  networked module — while every other banned name stays banned there
  and `urllib` stays banned everywhere else. The § 6 scanners do
  **not** detect network use, so INV-8 does not rely on them.

- **INV-1 — Encrypted at rest.** No code path writes
  unencrypted vault contents to disk. Opening the file without
  the correct key fails, and the vault is opened with per-page
  HMAC integrity enabled (`cipher_use_hmac = ON`, SQLCipher 4) so a
  tampered page fails to open rather than returning corrupt data.
  The **encrypted backup** (FIBR-0014) upholds this too: the exported
  `.fbk`'s `vault.db` is a SQLCipher AES-256 file with HMAC on; during
  export or restore no plaintext vault contents spill to any temp store
  (`temp_store=MEMORY`), and the backup DB's rollback journal is itself
  SQLCipher-encrypted (a distinct `journal_mode` guarantee, not governed
  by `temp_store`) — FIBR-0014 INV-1/INV-1b.
- **INV-2 — Strong, pinned KDF.** The master password is
  stretched with Argon2id using these pinned parameters:
  **memory = 47104 KiB (46 MiB), iterations (time cost) = 1,
  parallelism = 1** — one of the five equal-strength Argon2id
  configurations in the
  [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
  (the highest-memory one; OWASP states the five give equal
  defence, trading CPU for RAM), retrieved **2026-06-30** as a
  frozen dated snapshot, not a live "current guidance" target.
  From a unique **16-byte random salt per slot** Argon2id derives
  a **32-byte (256-bit) output** — these two lengths are finbreak's
  own choices (OWASP pins only memory / time / parallelism).
  **Amended by FIBR-0019:** that output is now a **KEK**, and
  SQLCipher's raw key is a random **DEK** the KEK wraps — so the
  32 bytes are AES-256-GCM's key size *and* SQLCipher's raw-key
  size, which are the same number for the same reason. The salt is
  per **slot** rather than per vault: reusing one across slots
  would make each KEK derivable from the other's work factor, for a
  saving of 16 bytes. Both slots share one set of cost parameters,
  so neither credential is cheaper to attack than the other. The parameters and salt are recorded with
  the vault. On open the app derives the key from the parameters
  **recorded with the vault** and **must refuse to proceed** unless
  the record passes every check below — a known **`format_version`**, a
  directional **strength floor** on memory, and an **exact-format**
  match on the lengths. An unknown `format_version` is refused first,
  so a future or foreign layout is never reinterpreted against this
  version's field meanings. The strength floor is a **second constant**
  (`ARGON2_MEMORY_FLOOR_KIB`), deliberately separate from the creation
  pin (`ARGON2_MEMORY_KIB`) even though the two hold the same value
  today: a vault with *stronger* memory still opens, so the pin can be
  raised to strengthen new vaults — and the floor **must not be raised
  with it**, or every vault recorded at the old value stops opening.
  Moving one number because the document showed one number is exactly
  the lockout this separation exists to prevent. The exact-format match:
  recorded **output length = 32 bytes** and **salt length = 16
  bytes** — the raw key's required size; a *longer* output or salt
  is rejected, not accepted. Iterations and parallelism get no
  on-open check — Argon2id's own minimum of 1 already pins them, so
  no recorded value can fall below the pin and there is no app-level
  downgrade test for those two axes. So a tampered or downgraded
  vault cannot force a weaker KDF. The
  FIBR-0004 (P02) spec implements and *tests* these values. Since
  FIBR-0019 what reaches SQLCipher's **raw**-key pragma is the **DEK**,
  and the Argon2id output is the **KEK** that wraps it — so the
  "Argon2id is the KDF" claim (A3) is testable through the wrap, not by
  handing the derived key to the database. Do not read this sentence as
  licence to key SQLCipher from a credential: ADR-0011 exists to leave
  exactly one way a vault is keyed.
- **INV-3 — Key lifetime.** The **DEK**, **every KEK** and the
  plaintext password exist in memory only while unlocked, are wiped
  on lock/exit, and are dropped by auto-lock after the configured
  idle period. (A true wipe needs a *mutable* buffer — `bytearray`,
  not an immutable `str` — so the FIBR-0004 spec holds the password
  in a zeroable buffer; this is what makes "wiped" testable.)
  Widened by FIBR-0019 from "the derived key" to all three: a KEK is
  shorter-lived than the DEK — it is wiped as soon as it has
  unwrapped or re-wrapped a slot — and the DEK is what the session
  holds for its whole unlocked life.
  **Residuals, stated honestly** (ADR-0011 D5), because a test written
  to an unqualified "wiped" asserts something the code deliberately
  does not do: `derive_key` must hand the C binding an
  immutable `bytes(password)` copy, which cannot be zeroed and lingers
  until GC; `vault._connect` builds the raw key as a hex `str` with the
  same property; and an `AESGCM` object keeps OpenSSL's own copy of the
  key, so it still decrypts after the `bytearray` it was built from is
  zeroed. What is wiped is every buffer the app owns. These are
  in-process copies, distinct from the swap residual T3 and INV-4 name.

- **INV-3b — The sidecar holds no UNWRAPPED key material** (FIBR-0019
  INV-4). The plaintext sidecar carries a wrapped DEK per slot, which
  is ciphertext under AES-256-GCM and opens nothing without a
  credential. It must never carry the DEK itself, either KEK, the
  master password or the recovery code, in hex, base32 or raw form.
  This **replaces** FIBR-0004 INV-7's "the sidecar contains only the
  salt + non-secret KDF parameters + format version", which the
  envelope falsifies; the replacement is strictly weaker and that is
  recorded rather than glossed (ADR-0011).

- **INV-3c — The recovery code is never persisted by the app of its
  own accord** (FIBR-0019 INV-5), in any form, to any plaintext
  surface. The single exception is a file the **user** explicitly
  names at the moment of display — that is the user storing their own
  credential, not the app retaining it, and the difference between
  the two is what this invariant is about. In particular it never
  reaches `window.ini`, which is plaintext by design and is where the
  password hint already lives.

- **INV-3d — Slot wrapping is authenticated and fails closed**
  (FIBR-0019 INV-3). Any modification to a slot — a flipped
  ciphertext or nonce bit, a renamed slot, a weakened cost parameter
  — refuses to unwrap. The AES-GCM additional authenticated data is
  exactly `finbreak-kdf-v2`, the slot name, `memory_kib`, `time_cost`,
  `parallelism` and `key_len`, so a `recovery` slot cannot be renamed
  to `master`; both are cheap edits to a plaintext file and neither is
  detectable from the ciphertext alone.
  `salt_len` is deliberately not among them, and the omission is safe
  rather than an oversight: `validate_params` pins it to `SALT_LEN`
  exactly and runs before every unwrap, so it carries none of the
  freedom `memory_kib` has — a migrated vault legitimately keeps its
  own cost schedule, which is what the AAD exists to bind. The salt
  itself is bound through the derivation. Nothing here may be added
  later either: the AAD is an input to the AEAD, so changing the field
  list would stop every slot written under the old one from
  unwrapping.
  The unwrap failure never distinguishes "wrong credential" from
  "tampered slot": the caller cannot act differently on the two, and
  an error that told them apart would be an oracle.
- **INV-4 — No plaintext spill.** Decrypted input PDFs and any
  decrypted statement bytes are never *deliberately* written to
  disk, temp files, or logs. (Defending against the OS paging
  process memory to swap is out of scope — see § 4; short of buffer
  pinning the app does not claim it.)
- **INV-5a — Untrusted input is inert.** Importers never `eval`,
  never shell out, never open a filesystem path derived from file
  *content* (no path traversal), and treat CSV cells as data (no
  spreadsheet-formula execution). The no-`eval` / no-shell legs are
  caught by `bandit` (T8) from P01; the CSV-as-data and
  no-content-derived-path legs are asserted by unit tests that land
  with the import specs (FIBR-0007+) — e.g. a fixture cell
  `=cmd|'/c calc'` must round-trip as literal text.
- **INV-5b — Untrusted input is bounded (one documented residual).**
  Importers cap resource use by **file size** (16 MiB,
  `_MAX_IMPORT_BYTES`), **PDF page count** (500), and **row count**
  (100 000); the concrete budget is pinned in the import specs —
  FIBR-0007 (CSV), FIBR-0008 (OFX), FIBR-0009 (PDF). These bound the
  *input* and *output* sizes and the testable form of T5's "no
  zip-bomb-style exhaustion" holds **for those bounds**.
  **Residual risk (FIBR-0075 — assessed + accepted 2026-07-10):** the
  caps do **not** bound the *decompressed* size of a PDF page's
  Flate-compressed content stream, so a small in-cap PDF whose page
  expands to gigabytes could exhaust memory / hang the UI thread during
  `extract_text`/`extract_tables`. This is **accepted, not fixed**: the
  threat is a local single user opening a file **they** chose (not a
  service ingesting untrusted uploads), and the only robust bound —
  running extraction in a separate memory-capped process (POSIX
  `RLIMIT_AS` / Windows Job Objects) — is disproportionate to that risk
  on a cross-platform desktop app. `pdfplumber`/`pdfminer` expose no
  streaming size limit to do it cheaply in-process. **Revisit if
  finbreak ever ingests PDFs from an untrusted channel** (a shared inbox,
  a sync folder, a server). The decompression bound is the documented
  residual, not a silently-unmet claim.
- **INV-5c — Per-row failure.** A malformed row is reported and
  skipped; the rest of the import proceeds. Owned by the import
  specs (FIBR-0007 / FIBR-0008 / FIBR-0009), **not** by P01.
- **INV-6 — No secret in the repo.** No key, password, vault, or
  real financial record is ever committed; tests use synthetic
  data only; `gitleaks` enforces it.
- **INV-7 — Exports are user-locked *when the user sets a password*,
  and never staged in plaintext on disk regardless.**
  (**`FIBR-0013 amends INV-7`**; corrected 2026-08-03.) As originally
  drafted this claimed every exported PDF is AES-256 encrypted and
  "no unencrypted report file is ever produced". FIBR-0013 INV-1
  reversed that by explicit user directive: the export password is
  **optional**, and a blank password produces a plain PDF — the
  Export dialog enables Export with an empty field, and
  `test_blank_password_is_unencrypted` asserts it. A security model
  that overstates a guarantee is worse than one that states the
  limitation, because it is what a reviewer or packager will cite.
  What *does* hold unconditionally is the disk half: the PDF is
  rendered and encrypted **in memory** (`render_pdf_bytes` takes no
  path) and the single write is the finished bytes, so no plaintext
  PDF is ever staged in a temp file even when a password is set,
  reconciling with INV-4. That temp is opened `O_EXCL|O_NOFOLLOW`
  mode `0600` and `os.replace`d into place (FIBR-0204), so the final
  report does not inherit a loose umask and the predictable `.part`
  name cannot be used to overwrite an unrelated file by symlink.
- **INV-8 — One opt-in outbound flow.** The shipped app makes
  **exactly one** kind of outbound request — an opt-in, off-by-default
  update flow that reads the GitHub Releases API and downloads the
  signed release assets, confined to `services/update_fetch.py`
  (FIBR-0054 INV-12) and never begun without explicit user consent
  (FIBR-0054 INV-1). That
  download is **signature-gated and resource-bounded**: a release is
  installed only if its Ed25519 signature verifies, and the fetch is
  abandoned if it exceeds its size cap or times out (FIBR-0054
  INV-4/INV-10/INV-11). No other network access exists; there is no
  networking *dependency* in the runtime bundle (the flow uses stdlib
  `urllib`).
  - *Distro (OBS) builds have an empty outbound surface (FIBR-0155).* A
    package launched from `/usr/bin/finbreak` has no `$APPIMAGE` env and is
    not a frozen Windows exe, so `detect_installer()` → `None`: the
    self-updater is inert and the Settings "check for updates" checkbox is
    disabled. The distro build therefore makes **zero** outbound requests by
    default — a strict subset of this invariant's "exactly one opt-in flow",
    covered without any source change by the existing runtime gating and
    asserted by `tests/features/obs_packaging/` INV-5.
  - *Flatpak (Flathub) builds are empty-outbound **and** sandbox-enforced
    (FIBR-0159).* A Flatpak launch has no `$APPIMAGE` and is not a frozen exe,
    so `detect_installer()` → `None` and the updater is inert — the same
    empty app-initiated outbound surface as the OBS build. The Flatpak goes
    further: its `finish-args` grant **no `--share=network`** (§ 3.4), so app
    networking is not merely off-by-default but **unreachable at the OS level**
    — the strongest form of this invariant. Asserted by
    `tests/features/flatpak_packaging/` INV-6.
- **INV-9 — Logs are clean.** The local log file never records
  transaction contents, passwords, keys, or decrypted data.
- **INV-10 — Interactive unlock is throttled.** After a wrong master
  password in the unlock dialog, the next attempt is delayed on a
  capped exponential schedule (1s, 2s, 4s, …, capped at 30s), with the
  attempt count and last-failure time persisted in the plaintext
  `window.ini` so an app restart does not reset the delay. This is
  best-effort friction against guessing **through the app UI**; it is
  **not** a security boundary — an attacker with filesystem access can
  reset it, and the copied-vault offline-cracking path is defended only
  by INV-2 (Argon2id). The delay is capped and a correct password
  always clears the counter, so the legitimate owner is never
  permanently locked out.
- **INV-11 — A stored password hint never contains the master password
  **nor the recovery code** verbatim.** The optional plaintext hint (FIBR-0029, in `window.ini`) is
  enforced at set-time never to be, nor contain, the master password —
  compared NFC-normalized + casefolded, with **no** password-length
  exemption (a short password embedded verbatim is still caught). The
  check is gated behind a mandatory `AuthService.verify_password` confirm,
  so the comparison is against the real password. The guarantee is scoped
  to **verbatim** inclusion: internal obfuscation of the user's own hint
  (inserted spaces, zero-width characters, homoglyphs) is out of scope —
  substring matching cannot catch a user defeating their own safety net,
  and the hint is plaintext-by-design regardless.
  **Widened by FIBR-0019 to the recovery code**, and the second leg
  works differently of necessity: the app does not hold the code
  (INV-3c forbids it) and the hint is set long after the one-time
  display, so there is nothing to compare against. Instead the hint is
  **normalised first** — the user holds the code as `A1B2-C3D4-…`,
  whose longest unbroken run is four symbols, so scanning the raw text
  finds no candidate and would cheerfully accept a hint that *is* the
  code — then scanned for a 28-symbol Crockford candidate whose check
  symbol verifies locally, and any candidate is trial-unwrapped against
  `slots.recovery`. A successful unwrap proves the hint carries the live
  code. A hint with no candidate — the common case — costs no key
  derivation at all. Falsifiable by test
  (`services/password_hint.validate_hint` for the password leg;
  `ui/_password_hint.validate_hint_with_recovery` for the recovery leg,
  which lives in the hint pair's I/O half because the policy module's
  own contract is to be pure).
- **INV-12 — The destructive reset leaves no vault fragment behind.** The
  double-confirmed "start over" reset (FIBR-0030) removes the vault's
  complete on-disk data footprint — the DB, the KDF sidecar, **both**
  SQLite WAL sidecars (`vault.db-wal` / `vault.db-shm`), the migration
  artefacts (`.pre-v2` and `.migrating`, with their own WAL siblings),
  and every `*.old` set a past restore left behind — so no file of a
  deleted vault remains to interfere with a subsequently created one.
  The last two are here because each is a **complete, still-openable
  copy**: a `.pre-v2` pair opens under the password of the moment the
  migration began, and a `.old` set under the password in force before
  that restore, so leaving either behind hands the old vault to anyone
  holding a password the user has since changed. The vault-coupled
  `window.ini` keys — the hint and the throttle's lockout state — are
  cleared on success too, by the shell rather than by `reset_vault`,
  since that file is shared with the app's own settings. This
  is **logical deletion** (`unlink` removes the directory entry), not a
  secure media wipe: residual sectors may hold old-key-encrypted ciphertext
  until overwritten. That is acceptable — the fragments are useless without
  the (now-gone) key, so this is deletion-completeness *hygiene*, not a
  confidentiality or anti-forensic guarantee. Falsifiable by test
  (`AuthService.reset_vault`; FIBR-0030 INV-1).
- **INV-13 — The published `SHA256SUMS` manifest is Ed25519-signed over its
  final bytes.** Each release publishes a `SHA256SUMS` checksum manifest
  signed with the release key (`SHA256SUMS.sig`) over its **final** merged
  bytes; each hash line was computed by `scripts/gen-checksums.sh` from the
  actual artifact at its platform's release phase, and every basename it
  lists is a genuine release asset. The other-platform line a phase *carries*
  is merged only **after** the prior manifest's own signature verifies
  against the committed release public key (the anti-laundering gate the two
  release scripts enforce before re-signing), so a re-sign can never launder
  a tampered line. This is an **integrity** (tamper-evidence) guarantee,
  **not** confidentiality: a release-write attacker can *delete* the manifest
  or a line but cannot *forge* a valid signature, and a missing manifest/line
  should be read as a red flag, not a pass — the per-artifact `.sig`
  (FIBR-0054 INV-4) remains the primary download-integrity gate. Falsifiable
  by the FIBR-0096 `release_integrity` suite (the `gen-checksums.sh` +
  sign/verify roundtrip and the source-scrape of the two verify gates).

## 6. Tooling that enforces this (harness wired in P01; per-INV tests land with each phase)

| Tool | Catches | Runs in |
|------|---------|---------|
| **bandit** | insecure Python patterns (T8) | CI + `scripts/ci-local.sh` |
| **pip-audit** | dependencies with known CVEs, **and** — via the second `-s osv` run (`FIBR-0227`) — hijacked or typosquatted releases carrying no CVE (T7) | CI + `scripts/ci-local.sh` |
| **gitleaks** | secrets staged for commit (T6) | CI + `scripts/ci-local.sh` |
| **ruff** | general correctness/lint (defence in depth) | CI + `scripts/ci-local.sh` |
| **mypy** | type errors (defence in depth; `FIBR-0061`) | CI + `scripts/ci-local.sh` |
| **shellcheck** | bugs in the release/build shell scripts (`FIBR-0225`) | CI + `scripts/ci-local.sh` |
| **actionlint** | workflow defects + shell bugs inside `run:` blocks (`FIBR-0225`) | CI + `scripts/ci-local.sh` |
| **zizmor** | workflow **supply-chain** risk — a `uses:` on a mutable tag, `${{ }}` injection into `run:`, over-broad `permissions:`, a checkout persisting its token (`FIBR-0226`) | CI + `scripts/ci-local.sh` |
| **pytest** | the INV-* assertions, **added per phase** as the code each invariant governs lands | CI + `scripts/ci-local.sh` |

> **This table maps tools to threats; it is not the gate's stage
> list.** `FIBR-0001` INV-1 holds the authoritative, ordered list of
> what `scripts/ci-local.sh` runs — where the two differ, that table
> governs. Stating the stage list in two places is what let this one
> sit at five tools while the gate ran nine.

The four original scanners (bandit, pip-audit, gitleaks, ruff) and the
test harness are wired in P01 (FIBR-0001) — `mypy`, `shellcheck`,
`actionlint` and `zizmor` joined later, per the table; the per-INV assertions
arrive with the later phases that build the vault, crypto, import, export, and
logging paths — § 5's third bullet enumerates which, and is the only list. The CI workflow
and the local script run the **same** gate list (one source of
truth) so a security regression fails *before* a push, not after.

Notes: `pip-audit` fetches its advisory data over the network, but it
runs only in CI and the **dev-time** local gate — outside the
shipped-app boundary, so it does not violate INV-8 (which constrains
the *shipped application*). `semgrep` is intentionally **not** in the
gate — `bandit` covers Python security patterns for this codebase.
`osv-scanner` is likewise not in the gate: `pip-audit -s osv` reaches the
same OSV.dev data with a flag on a tool already installed, so a second
binary would buy nothing (`FIBR-0227`).
`zizmor` runs **offline** (its default), so the two `pip-audit` stages
remain the only ones that can fail on a network timeout rather than a
real finding.
