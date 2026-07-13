# ADR-0009: SQLCipher binding package — `sqlcipher3-wheels`

- **Status:** Accepted
- **Date:** 2026-07-13
- **Deciders:** Project lead, Claude
- **Related:** [ADR-0003](0003-sqlcipher-local-only-storage.md) (the storage
  engine this binding supplies), [ADR-0007](0007-self-contained-bundled-releases.md)
  (the bundling requirement that motivates it),
  [FIBR-0015](../specs/FIBR-0015.md) (the item that made the swap)

## Context

ADR-0003 stores all data in a SQLCipher database keyed by an Argon2id-derived raw
key. SQLCipher reaches Python through a binding package, and ADR-0007 requires
every release to be a self-contained bundle — the binding must ship the SQLCipher
engine *inside its wheel* (no system `libsqlcipher`) on every target OS.

The package pinned at FIBR-0003, `sqlcipher3-binary==0.6.0`, publishes Linux/macOS
wheels only — no Windows wheel on any version (PyPI JSON, 2026-07-13). PyInstaller
cannot cross-compile, so a Windows `.exe` appeared to need a hand-compiled
SQLCipher (Wine + MSVC, or a vendored DLL). That premise was stale: a sister
distribution, **`sqlcipher3-wheels`**, publishes the same project (a fork,
`github.com/laggykiller/sqlcipher3`, of `coleifer/sqlcipher3`) with a CI matrix
that builds Windows, macOS, and Linux wheels, including `cp312-cp312-win_amd64`. It
exposes the identical `sqlcipher3` import package and bundles the identical
SQLCipher 4.12.0 community engine.

This is also the binding-package decision FIBR-0003 anticipated but never wrote:
FIBR-0003 pinned `sqlcipher3-binary` provisionally as "the maintained package" and
pointed a future ADR (expected via FIBR-0004) at formalising it. This is that ADR.

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

The swap was validated **empirically before adoption** (FIBR-0015):

- Both packages report `PRAGMA cipher_version` = `4.12.0 community`.
- A raw-hex-keyed, `cipher_compatibility=4`, HMAC-on vault created under one
  **opens and reads correctly under the other, both directions**.
- `sqlcipher_export` + `PRAGMA rekey` (the FIBR-0014 backup binding surface)
  round-trip under `sqlcipher3-wheels`.

A committed old-package fixture regression-locks the upgrade path — the test lives
in `tests/features/windows_build/`, the `-binary`-written fixture data in
`tests/fixtures/windows_build/`.

## Decision

Depend on **`sqlcipher3-wheels`** (pinned `==0.5.7`, its latest stable) on every
OS. It is a drop-in for `sqlcipher3-binary` on the identical `sqlcipher3` import,
so **no application code changes** — every DB-touching module keeps its
`sqlcipher3` import unchanged. The two packages carry independent version lineages
(0.6.0 for `-binary`, 0.5.7 for `-wheels`); the lower `-wheels` number is **not** a
downgrade of a shared package. The Windows `.exe` is then a dependency swap plus a
PyInstaller job on a `windows-latest` runner — no crypto compilation.

|            | Package             | Pin   | Bundled engine             | Wheels                |
|------------|---------------------|-------|----------------------------|-----------------------|
| **Before** | `sqlcipher3-binary` | 0.6.0 | SQLCipher 4.12.0 community  | Linux, macOS          |
| **After**  | `sqlcipher3-wheels` | 0.5.7 | SQLCipher 4.12.0 community  | Linux, macOS, Windows |

## Consequences

**Positive:**

- The Windows `.exe` (and a future macOS `.dmg`) is unblocked with no vendored
  DLL and no cross-compile — the same wheel supplies the engine on all three OSes.
- A vault is now **portable across OSes by construction** (the same 4.12.0 build
  everywhere) — a guarantee the two-package alternative could not make.

**Negative:**

- The binding is now a **community fork** rather than the upstream `-binary`
  package. Per `dependencies.md` §2, `pip-audit` cannot see a CVE inside a
  vendored native lib (SQLCipher + SQLite + OpenSSL) — the advisory only clears
  when the *wheel maintainer* re-releases, and that maintainer is now the fork
  author. The vendored-native advisory watch therefore moves to the fork's release
  cadence. If the fork lags a SQLCipher/OpenSSL CVE, the fallback is to build the
  wheel from the fork's source (its README documents a conan-based OpenSSL build)
  or revert Windows to a compile path — filed in `docs/known-issues.md` per the
  `dependencies.md` §2 vendored-native policy (which forwards to §5) until it ships.
- The fork is **single-maintainer** (`laggykiller`), so abandonment is a
  bus-factor risk. Its mitigation is the same build-from-source / revert-to-compile
  fallback; because the swap changes no application code, reverting is a one-line
  pin change.
- A future Python-runtime bump past the fork's wheel matrix (currently cp38–cp314)
  would need a wheel refresh first — a non-issue for the cp312-pinned build.

**Neutral:**

- The import name is unchanged, so the swap is invisible to the repository/service
  layers and to the mypy overrides (which target `sqlcipher3` / `sqlcipher3.*`).

## Cold-eyes loop log

Reviewed per global rule §14 (this ADR is a design document); filling this log is
part of reaching **Accepted** (see the ADR-0001 template note).

**Loop 1 (2026-07-13) — 3 lanes (accuracy / cross-doc / internal-structure).**
`CRITICAL 0 · HIGH 2 · MEDIUM 3 · LOW 2 · INFO ~3` (all verified). Fixed: the
broken `docs/known-issues.md (§5)` cross-reference — that file has no numbered
sections, so it now cites the `dependencies.md §5` "Sweep posture" policy; the
FIBR-0003-anticipated provenance folded from an orphan pre-`Context` preamble into
`## Context` (restoring Nygard shape + satisfying FIBR-0015 Deliverable 8); the
empirical-validation paragraph broken into a bullet list and its two >40-word
sentences split; the fixture citation now names both the test dir
(`tests/features/windows_build/`) and the `-binary` fixture-data dir
(`tests/fixtures/windows_build/`); the positive-consequence bullet trimmed of its
overlap with the selection rationale; and `ADR-0001`'s template updated to define
the `## Cold-eyes loop log` section + the one post-acceptance edit it permits.

**Loop 2 (2026-07-13) — same 3 lanes, cold. CONVERGED (polish).**
`CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW ~5 · INFO ~4` — no structural / mechanical /
architectural finding, and no loop-1 fix resurfaced (the `§5` repoint, the
Context fold, and the sentence splits all held; accuracy + cross-doc lanes
re-verified every pin / link / cite clean). Polish folded: reworded the
"every module keeps its `from sqlcipher3 import dbapi2`" line to "keeps its
`sqlcipher3` import unchanged" (3 modules use `from sqlcipher3.dbapi2 import
DatabaseError`); repointed the known-issues cite to `dependencies.md` §2 (the
primary vendored-native policy, which forwards to §5); reordered `## Context` to
open with the technical forces and trail the FIBR-0003 provenance; trimmed the
over-bolding; added a single-sourced before/after pins table; named the
single-maintainer fork-abandonment risk as its own Negative bullet; and aligned
the `decisions/README.md` Index gloss with this ADR's title. The two lanes that
raised a HIGH/MEDIUM did so only for the *missing* converged-pass log entry — this
entry closes it (EC7). **CLEARED — converged at loop 2** (of the project cap 7).
