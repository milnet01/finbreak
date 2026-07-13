# FIBR-0015 cross-package upgrade-path fixtures

These three files are an **old-package** (`sqlcipher3-binary==0.6.0`, SQLCipher
`4.12.0 community`) vault + backup, committed so the FIBR-0015 regression test can
prove they still open under the **new** package (`sqlcipher3-wheels==0.5.7`) after
the swap — INV-1, the real upgrade an existing Linux user hits. Once the swap
lands, `-binary` is gone and CI can no longer *create* an old-package artifact, so
these bytes are captured here once, before the swap.

| File | What it is |
|------|------------|
| `vault.db` | A first-run vault (schema at generation time) with one synthetic sentinel transaction, written by `sqlcipher3-binary`. |
| `vault.kdf.json` | Its plaintext KDF sidecar (Argon2id salt/params) — needed to derive the key. |
| `backup.fbk` | A `.fbk` backup (FIBR-0014) of that vault — a zip of `manifest.json` / `params.json` / `vault.db`, the embedded DB re-keyed to the backup password via `sqlcipher_export`. |

**Nothing here is secret.** The data is synthetic and the keys are documented test
keys defined in `_generate_fixture.py` (`MASTER_PASSWORD`, `BACKUP_PASSWORD`) —
they key a throwaway vault that exists only to be decrypted by a test
(testing.md § 6, "no real financial data").

**Provenance / regeneration:** `_generate_fixture.py` is a skipped-by-default
manual helper (no `test_` functions, never collected). It refuses to run unless
only `sqlcipher3-binary` is installed. See its module docstring for the
regenerate steps.
