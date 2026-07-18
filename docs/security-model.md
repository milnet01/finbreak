# finbreak — Security model & threat model

> **Status:** Live — the project's authoritative security & threat
> model; amended through FIBR-0095 (2026-07-18 — INV-10: interactive
> unlock throttling). This line names the **most-recent** material
> amendment, not a full history. Re-run through `/cold-eyes` on each
> material edit.
> **Why this exists:** finbreak holds **personal financial
> data**. Security is the load-bearing concern, so it gets its
> own document — a single place that names what we protect, what
> could go wrong, and exactly how each risk is stopped.
> **How it's used:** every `implement`-Kind spec must state how
> it upholds the **security invariants** in § 5; every `/audit`,
> `/indie-review`, and `/cold-eyes` pass checks against them.
> See [ADR-0003](decisions/0003-sqlcipher-local-only-storage.md)
> (storage/crypto) and
> [ADR-0007](decisions/0007-self-contained-bundled-releases.md) (bundling).

This is a deliberately plain-English document. Where a term is
unavoidable it is glossed on first use.

## 1. What we are protecting (assets)

| # | Asset | Why it matters |
|---|-------|----------------|
| A1 | **The vault** — the SQLCipher database file holding every transaction, account, rule, and financial setting (base currency, minor-unit exponent, stored PDF passwords). *Non-sensitive UI state — window geometry / toolbar state / last-active tab, plus the opt-in update-check flag and any skipped-update version (FIBR-0054) — deliberately lives in a plaintext `window.ini` sibling, not the vault (FIBR-0052 INV-5, FIBR-0054 D4); it holds no financial data, so it is not an A1 asset.* | The whole financial picture. Its disclosure is the worst case. |
| A2 | **The master password** | Unlocks everything. Never stored anywhere. |
| A3 | **The derived key** — the key Argon2id produces from the master password, passed to SQLCipher as its **raw** key (so Argon2id, not SQLCipher's built-in PBKDF2, is the KDF) | Decrypts the vault; lives only in memory while unlocked. |
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
  absence of network code keeps the attack surface minimal. (Dev/CI tooling
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
| T2 | **Weak master password brute-forced** | **Argon2id** memory-hard key derivation with pinned parameters (§ 5 INV-2) makes offline guessing slow and GPU-resistant; the interactive unlock dialog additionally throttles repeated wrong attempts on a capped backoff (§ 5 INV-10). Password strength is also surfaced at first-run (advisory, not an enforced INV). |
| T3 | **Key or password recovered from memory / swap / a crash dump** | Key held only while unlocked; **wiped on lock and on exit**; auto-lock drops it after idle (INV-3). The plaintext password reference is cleared before the unlock routine returns. (Defending against the OS paging memory to swap is out of scope — see § 4.) The idle timeout is **user-configurable** (FIBR-0055) and may be set to **"Never"** (FIBR-0135), which disables *only* the idle drop — the key is still wiped on manual lock and on exit, and the password is still required on open. An unattended, unlocked session then stays unlocked: an accepted user choice, not a silent default. |
| T4 | **Decrypted bank statement leaks to disk** | Locked input PDFs are decrypted **in memory only**; no decrypted content is *deliberately* written to disk or temp files (A5, INV-4). (Defending against the OS paging memory to swap is out of scope — § 4.) |
| T5 | **Malicious import file** (crafted CSV/OFX/PDF — parser crash, path traversal, zip-bomb-style resource exhaustion, formula injection) **or a crafted restore `.fbk`** (a zip parsed **pre-login**) | Parsers run defensively: bounded resource use (file/page/row caps), no `eval`, no shell-out; CSV cells are treated as data, never spreadsheet formulas; per-row errors are reported, not fatal (INV-5a/5b/5c). The restore `.fbk` — parsed before any authentication — reads only the three fixed entry names with per-entry caps checked **before** inflating (never `extractall`), rejects traversal/extra/duplicate entries, and re-validates the embedded KDF params against the pinned floor before deriving any key (FIBR-0014 INV-11/INV-12). **One documented residual:** the PDF **decompressed-page-size** vector is assessed + accepted, not bounded — see INV-5b / FIBR-0075. |
| T6 | **Secret accidentally committed to the public repo** | `gitleaks` in CI **and** the local pre-push script; `.gitignore` excludes `*.db`/vault/build output; no real financial data in tests — only synthetic fixtures (INV-6, A7). |
| T7 | **Vulnerable third-party dependency (known CVE)** | `pip-audit` in CI + local script fails the build on a known-vulnerable dependency; Dependabot raises bumps; latest-stable policy (global rule § 5). |
| T8 | **Insecure code pattern introduced** (hardcoded secret, weak hash, `subprocess(shell=True)`, etc.) | `bandit` security linter in CI + local script. |
| T9 | **Tampered vault / downgrade of crypto settings** | SQLCipher authenticates **each page with a per-page HMAC** (HMAC-SHA512 by default) — tamper-evident. AES gives confidentiality, **not** integrity, so the HMAC must stay enabled; a tampered page fails to open (INV-1). The recorded KDF parameters can't be downgraded **below the pinned floor** on open (INV-2). Both are asserted by the FIBR-0004 (P02) spec's tests. |
| T10 | **Exported report shared, then read by the wrong person** | Export is password-locked with AES-256 (`pikepdf`) using a password the user sets at export time (A6, INV-7). The user is reminded the password is theirs to share safely. |
| T11 | **Forgotten master password** | By design there is **no backdoor** (a backdoor is a vulnerability). The mitigation is the **encrypted backup** (FIBR-0014), keyed by a **separate backup password** the user keeps safe: restoring needs the backup password + a **new** master password, **never** the forgotten one, so the backup **does** recover a forgotten master password. It is "only as recoverable as its own secret" — if **both** the master **and** the backup password are lost, the data is unrecoverable (the deliberate confidentiality-over-availability trade). The backup's own KDF params are re-validated against the pinned floor on restore (INV-2), so a tampered `.fbk` can't force a weak KDF. *The recovery path is testable (FIBR-0014 INV-3); the no-backdoor stance is not.* |
| T12 | **Sensitive data leaked via the log file** | The local rotating log never records transaction contents, passwords, keys, or decrypted data (INV-9). |

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
  INV-2, INV-3, INV-4, INV-5b, INV-5c, INV-7, INV-9, INV-10 — asserted by
  tests that land alongside the vault, crypto, import, export, and
  logging paths (none of which exist yet at P01).
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
  From a unique **16-byte random salt per vault** Argon2id derives
  a **32-byte (256-bit) output** — SQLCipher's raw-key size; these
  two lengths are finbreak's own choices (OWASP pins only memory /
  time / parallelism). The parameters and salt are recorded with
  the vault. On open the app derives the key from the parameters
  **recorded with the vault** and **must refuse to proceed** unless
  the record passes two checks — a directional **strength floor**
  on memory and an **exact-format** match on the lengths. The
  strength floor: recorded **memory ≥ 47104 KiB** (a vault with
  *stronger* memory still opens, so the pin can be raised later
  without locking out existing vaults). The exact-format match:
  recorded **output length = 32 bytes** and **salt length = 16
  bytes** — the raw key's required size; a *longer* output or salt
  is rejected, not accepted. Iterations and parallelism get no
  on-open check — Argon2id's own minimum of 1 already pins them, so
  no recorded value can fall below the pin and there is no app-level
  downgrade test for those two axes. So a tampered or downgraded
  vault cannot force a weaker KDF. The
  FIBR-0004 (P02) spec implements and *tests* these values, and
  asserts the Argon2id output is passed as SQLCipher's **raw** key
  (raw-key pragma), so the "Argon2id is the KDF" claim (A3) is
  testable, not merely stated.
- **INV-3 — Key lifetime.** The derived key and the plaintext
  password exist in memory only while unlocked, are wiped on
  lock/exit, and are dropped by auto-lock after the configured
  idle period. (A true wipe needs a *mutable* buffer — `bytearray`,
  not an immutable `str` — so the FIBR-0004 spec holds the password
  in a zeroable buffer; this is what makes "wiped" testable.)
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
- **INV-7 — Exports are user-locked.** Every exported PDF is
  written AES-256 encrypted with the user's chosen password (no
  unencrypted report file is ever produced — the FIBR-0013 spec
  must assert the render-then-encrypt path never stages a plaintext
  PDF in a temp file, reconciling with INV-4).
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

## 6. Tooling that enforces this (harness wired in P01; per-INV tests land with each phase)

| Tool | Catches | Runs in |
|------|---------|---------|
| **bandit** | insecure Python patterns (T8) | CI + `scripts/ci-local.sh` |
| **pip-audit** | dependencies with known CVEs (T7) | CI + `scripts/ci-local.sh` |
| **gitleaks** | secrets staged for commit (T6) | CI + `scripts/ci-local.sh` |
| **ruff** | general correctness/lint (defence in depth) | CI + `scripts/ci-local.sh` |
| **pytest** | the INV-* assertions, **added per phase** as the code each invariant governs lands | CI + `scripts/ci-local.sh` |

The four scanners (bandit, pip-audit, gitleaks, ruff) and the test
harness are wired in P01 (FIBR-0001); the per-INV pytest assertions
(INV-1/2/3/4/5b/5c/7/9/10) arrive with the later phases that build the
vault, crypto, import, export, and logging paths. The CI workflow
and the local script run the **same** gate list (one source of
truth) so a security regression fails *before* a push, not after.

Notes: `pip-audit` fetches its CVE database over the network, but it
runs only in CI and the **dev-time** local gate — outside the
shipped-app boundary, so it does not violate INV-8 (which constrains
the *shipped application*). `semgrep` is intentionally **not** in the
gate — `bandit` covers Python security patterns for this codebase.
