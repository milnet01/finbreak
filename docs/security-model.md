# Fin_Break — Security model & threat model

> **Status:** Draft — part of the Phase C doc set; runs through
> the Phase D `/cold-eyes` loop with the rest.
> **Why this exists:** Fin_Break holds **personal financial
> data**. Security is the load-bearing concern, so it gets its
> own document — a single place that names what we protect, what
> could go wrong, and exactly how each risk is stopped.
> **How it's used:** every `implement`-Kind spec must state how
> it upholds the **security invariants** in § 5; every `/audit`,
> `/indie-review`, and `/cold-eyes` pass checks against them.
> See ADR-0003 (storage/crypto) and ADR-0007 (bundling).

This is a deliberately plain-English document. Where a term is
unavoidable it is glossed on first use.

## 1. What we are protecting (assets)

| # | Asset | Why it matters |
|---|-------|----------------|
| A1 | **The vault** — the SQLCipher database file holding every transaction, account, rule, and setting | The whole financial picture. Its disclosure is the worst case. |
| A2 | **The master password** | Unlocks everything. Never stored anywhere. |
| A3 | **The derived key** — the key Argon2id produces from the master password | Decrypts the vault; lives only in memory while unlocked. |
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
- **Everything off the machine is untrusted — and unreachable.**
  The app opens **no sockets and makes no outbound call of any
  kind** (success criterion 4). There is no network attack
  surface because there is no network code.
- **Imported files are untrusted input.** CSV/OFX/PDF files come
  from outside and are parsed defensively (§ 4, T5).

## 3. Threats and mitigations (STRIDE-lite)

"STRIDE" is just a checklist of the six classic ways software is
attacked. Each row: the threat → how Fin_Break stops it.

| # | Threat | Mitigation |
|---|--------|------------|
| T1 | **Lost/stolen laptop → someone reads the vault file** | Whole-file AES-256 encryption (SQLCipher). The file is meaningless without the key (A1, INV-1). |
| T2 | **Weak master password brute-forced** | **Argon2id** memory-hard key derivation with pinned, expensive parameters (§ 5 INV-2) makes guessing slow and GPU-resistant. We also surface password strength at first-run. |
| T3 | **Key or password recovered from memory / swap / a crash dump** | Key held only while unlocked; **wiped on lock and on exit**; auto-lock drops it after idle (INV-3). Plaintext password is never held longer than the unlock call. |
| T4 | **Decrypted bank statement leaks to disk** | Locked input PDFs are decrypted **in memory only**, never written out (A5, INV-4). Temp files are never used for decrypted content. |
| T5 | **Malicious import file** (crafted CSV/OFX/PDF — parser crash, path traversal, zip-bomb-style resource exhaustion, formula injection) | Parsers run defensively: bounded resource use, no `eval`, no shell-out; CSV cells are treated as data, never spreadsheet formulas; per-row errors are reported, not fatal (INV-5). |
| T6 | **Secret accidentally committed to the public repo** | `gitleaks` in CI **and** the local pre-push script; `.gitignore` excludes `*.db`/vault/build output; no real financial data in tests — only synthetic fixtures (INV-6, A7). |
| T7 | **Vulnerable third-party dependency (known CVE)** | `pip-audit` in CI + local script fails the build on a known-vulnerable dependency; Dependabot raises bumps; latest-stable policy (global rule § 5). |
| T8 | **Insecure code pattern introduced** (hardcoded secret, weak hash, `subprocess(shell=True)`, etc.) | `bandit` security linter in CI + local script. |
| T9 | **Tampered vault / downgrade of crypto settings** | SQLCipher authenticates pages (AES gives integrity per-page); the schema records the KDF parameters used so they can't be silently downgraded on open (INV-2). |
| T10 | **Exported report shared, then read by the wrong person** | Export is password-locked with AES-256 (`pikepdf`) using a password the user sets at export time (A6, INV-7). The user is reminded the password is theirs to share safely. |
| T11 | **Forgotten master password** | By design there is **no backdoor** (a backdoor is a vulnerability). Mitigation is a user-initiated **encrypted backup export** they can store safely (ADR-0003). This is a deliberate availability-for-confidentiality trade. |

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

Every spec and every review pass checks these. They are phrased
so a test can assert them.

- **INV-1 — Encrypted at rest.** No code path writes
  unencrypted vault contents to disk. Opening the file without
  the correct key fails.
- **INV-2 — Strong, pinned KDF.** The master password is
  stretched with Argon2id using parameters fixed in the P02 spec
  (memory, time, parallelism); the parameters are recorded with
  the vault and never silently weakened on open.
- **INV-3 — Key lifetime.** The derived key and the plaintext
  password exist in memory only while unlocked, are wiped on
  lock/exit, and are dropped by auto-lock after the configured
  idle period.
- **INV-4 — No plaintext spill.** Decrypted input PDFs and any
  decrypted statement bytes never touch disk, swap-backed temp
  files, or logs.
- **INV-5 — Untrusted input is bounded and inert.** Importers
  never `eval`, never shell out, treat CSV cells as data (no
  formula execution), and fail per-row rather than crashing.
- **INV-6 — No secret in the repo.** No key, password, vault, or
  real financial record is ever committed; tests use synthetic
  data only; `gitleaks` enforces it.
- **INV-7 — Exports are user-locked.** Every exported PDF is
  AES-256 encrypted with the user's chosen password before it
  leaves the app.
- **INV-8 — No network.** The shipped app opens no socket and
  makes no outbound request; there is no networking dependency in
  the runtime bundle.
- **INV-9 — Logs are clean.** The local log file never records
  transaction contents, passwords, keys, or decrypted data.

## 6. Tooling that enforces this (wired up in P01)

| Tool | Catches | Runs in |
|------|---------|---------|
| **bandit** | insecure Python patterns (T8) | CI + `scripts/ci-local.sh` |
| **pip-audit** | dependencies with known CVEs (T7) | CI + `scripts/ci-local.sh` |
| **gitleaks** | secrets staged for commit (T6) | CI + `scripts/ci-local.sh` |
| **ruff** | general correctness/lint (defence in depth) | CI + `scripts/ci-local.sh` |
| **pytest** | the INV-* assertions above as tests | CI + `scripts/ci-local.sh` |

The CI workflow and the local script run the **same** gate list
(one source of truth) so a security regression fails *before* a
push, not after.
