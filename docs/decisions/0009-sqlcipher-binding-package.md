# ADR-0009: SQLCipher binding package — `sqlcipher3-wheels`

- **Status:** Accepted
- **Date:** 2026-07-13
- **Deciders:** Project lead, Claude
- **Related:** [ADR-0003](0003-sqlcipher-local-only-storage.md) (the storage
  engine this binding supplies), [ADR-0007](0007-self-contained-bundled-releases.md)
  (the bundling requirement that motivates it),
  [FIBR-0015](../specs/FIBR-0015.md) (the item that made the swap)

This is the binding-package decision **FIBR-0003 anticipated but never wrote**.
FIBR-0003 pinned `sqlcipher3-binary` provisionally, recording it as "the
maintained package" and pointing a future ADR (expected via FIBR-0004) at
formalising the choice. That ADR is this one; it also records the swap to the
cross-platform fork.

## Context

ADR-0003 stores all data in a **SQLCipher** database keyed by an Argon2id-derived
raw key. SQLCipher reaches Python through a binding package, and ADR-0007 requires
every release to be a **self-contained bundle** — the binding must ship the
SQLCipher engine *inside its wheel* (no system `libsqlcipher`) on every target OS.

The package pinned at FIBR-0003, `sqlcipher3-binary==0.6.0`, publishes
**Linux/macOS wheels only** — no Windows wheel on any version (PyPI JSON,
2026-07-13). PyInstaller cannot cross-compile, so a Windows `.exe` appeared to
need a hand-compiled SQLCipher (Wine + MSVC, or a vendored DLL). That premise was
stale: a sister distribution — **`sqlcipher3-wheels`** — publishes the **same
project** (a fork, `github.com/laggykiller/sqlcipher3`, of `coleifer/sqlcipher3`)
with a CI matrix that builds **Windows, macOS, and Linux** wheels, including
`cp312-cp312-win_amd64`. It exposes the **identical `sqlcipher3` import package**
and bundles the **identical SQLCipher 4.12.0 community** engine.

Alternatives considered:

- **Keep `sqlcipher3-binary`, hand-compile SQLCipher for Windows (Wine + MSVC).**
  Large, fragile, per-release build surface for a problem an existing wheel
  already solves. Rejected.
- **`sqlcipher3-binary` on Linux/macOS, `sqlcipher3-wheels` on Windows (a
  per-OS marker).** Two packages providing the same `sqlcipher3` import add
  surface for no benefit once cross-package vault portability is proven, and
  would let the Windows crypto engine drift from Linux/macOS. Rejected.
- **`sqlcipher3-wheels` on every OS (a project-wide swap).** One package, one
  crypto engine everywhere, one pin to bump. Chosen.

The swap was validated **empirically before adoption** (FIBR-0015): both packages
report `PRAGMA cipher_version` = `4.12.0 community`; a raw-hex-keyed,
`cipher_compatibility=4`, HMAC-on vault created under one **opens and reads
correctly under the other, both directions**; and `sqlcipher_export` + `PRAGMA
rekey` (the FIBR-0014 backup binding surface) round-trip under `sqlcipher3-wheels`.
A committed old-package fixture regression-locks the upgrade path
(`tests/features/windows_build/`).

## Decision

Depend on **`sqlcipher3-wheels`** (pinned `==0.5.7`, its latest stable) on **every
OS**. It is a drop-in for `sqlcipher3-binary` on the identical `sqlcipher3` import,
so **no application code changes** — every DB-touching module keeps its
`from sqlcipher3 import dbapi2`. The two packages carry **independent version
lineages** (0.6.0 for `-binary`, 0.5.7 for `-wheels`); the lower `-wheels` number
is **not** a downgrade of a shared package. The Windows `.exe` is then a
dependency swap plus a PyInstaller job on a `windows-latest` runner — no crypto
compilation.

## Consequences

**Positive:**

- The Windows `.exe` (and a future macOS `.dmg`) is unblocked with no vendored
  DLL and no cross-compile — the same wheel supplies the engine on all three OSes.
- One crypto engine everywhere ⇒ a vault is portable across OSes by construction
  (same 4.12.0 build), and there is one pin to bump.

**Negative:**

- The binding is now a **community fork** rather than the upstream `-binary`
  package. Per `dependencies.md` §2, `pip-audit` cannot see a CVE inside a
  **vendored native lib** (SQLCipher + SQLite + OpenSSL) — the advisory only
  clears when the *wheel maintainer* re-releases, and that maintainer is now the
  fork author. The vendored-native advisory watch therefore moves to the fork's
  release cadence. If the fork lags a SQLCipher/OpenSSL CVE, the fallback is to
  build the wheel from the fork's source (its README documents a conan-based
  OpenSSL build) or revert Windows to a compile path — logged in
  `docs/known-issues.md` (§5) until it ships.
- A future Python-runtime bump past the fork's wheel matrix (currently cp38–cp314)
  would need a wheel refresh first — a non-issue for the cp312-pinned build.

**Neutral:**

- The import name is unchanged, so the swap is invisible to the repository/service
  layers and to the mypy overrides (which target `sqlcipher3` / `sqlcipher3.*`).

## Cold-eyes loop log

_Recorded per global rule §14 (this ADR is a design document). Filled in after the
`/cold-eyes` run below._
