<!-- ants-dependency-standards: 1 -->
# Dependency Version Standards — v1

A shareable contract for **which version of a dependency to use**. Pairs
with the other standards in this folder ([coding](coding.md),
[naming](naming.md), [documentation](documentation.md),
[testing](testing.md), [commits](commits.md)) — see the
[index](README.md) for the full set.

Like `naming.md`, this standard is **cross-cutting**: it governs every
dependency the project pulls in, whatever the Kind of work that added it.
It operationalises the global rule (`~/.claude/CLAUDE.md § 5`) — "use the
latest external-library version, with current idioms" — and adds the
project's break-tracking mechanism.


## 1. The rule

**Every dependency stays on its latest stable version — for security as
much as for features.** ("Latest stable" excludes pre-release/RC builds
and **yanked** releases — a yanked version is never "latest" even if a
naive check shows it.) This applies not only when adding a new dependency
but as an ongoing obligation: a dependency that has fallen behind is a
finding, whether or not anything has broken yet.

The **only** exception: a dependency may be held **below** its latest
release when a newer version **explicitly breaks** a named feature of this
project **and there is no reasonable workaround**. A below-latest pin is a
last resort, never a convenience — and when it happens it must be
documented on **both** ends (§3).


## 2. What counts as a dependency

Everything the project does not itself author, in every manifest:

- **Runtime libraries** — `pyproject.toml` `dependencies` (currently
  PySide6, sqlcipher3-binary, pikepdf, argon2-cffi; the OFX/PDF parsers
  `ofxparse`/`pdfplumber` join when P06/P07 add them, ADR-0005).
  **Transitive** dependencies count too: when `pip-audit` flags a
  vulnerable transitive package, fix it by bumping the direct dep that
  pulls it in, or — if none can — pin it as a **direct** dependency in
  `pyproject.toml` (or in a checked-in `constraints.txt` passed to pip with
  `-c`; plain pip does **not** read a constraints block from
  `pyproject.toml`), register-tracked (§4) only if that pin holds it
  *below* latest for a break.
- **Vendored native libraries** — a blind spot to track by hand. Several
  wheels bundle a C library *inside* the wheel: `sqlcipher3-binary`
  (SQLCipher + SQLite), `pikepdf` (qpdf), `argon2-cffi-bindings` (Argon2).
  `pip-audit` scans Python-package metadata, so it **cannot** see a CVE in
  a vendored native lib — the advisory only clears when the *wheel
  maintainer* re-releases. Because these are the app's security-critical
  crypto/storage stacks, watch their upstream projects' advisories
  directly; on a native CVE, bump to a re-released wheel if one exists, and
  if none does yet, log it in [`docs/known-issues.md`](../known-issues.md)
  (§5) until it ships.
- **Dev / gate tools** — the `dev` dependency group (ruff, bandit,
  pip-audit, pytest, pytest-qt, mypy) and standalone binaries the gate
  needs (gitleaks, pinned in `scripts/ci-setup.sh`).
- **CI actions & runner images** — `actions/checkout`, `actions/setup-*`,
  `runs-on:` images, the `container:` image in `.github/workflows/*`.
- **Language runtime & base images** — the Python version the project
  targets (3.12+) and the container images CI / builds run in
  (`python:3.12-slim-bookworm`, `debian:13-slim`).
- **Lockfiles / pinned digests** — treat a lock or a pinned image digest
  as a snapshot to refresh on cadence, not an archive.


## 3. Pins

An **exact-version pin** (`==`) for reproducibility is fine — and is the
project's default for runtime deps — **as long as the pinned version *is*
the latest stable release**. A reproducibility pin that has drifted behind
latest is bumped on the next sweep (§5); it does not need a break-register
entry, because nothing is broken — it's just stale.

A **below-latest pin** (held back because a newer version breaks something)
requires **both** of the following, or it is not allowed:

1. **An inline comment in the manifest**, next to the pin, naming the
   constraint. Illustrative only (the project holds nothing back today,
   §4) — note the **hypothetical** names/versions:
   ```toml
   # Held at 1.2.3: 1.3.0 breaks <named feature> (<PROJ-NNNN> INV-N).
   # No workaround. Re-test when > 1.3.0 ships. See dependencies.md § 4.
   "some-library==1.2.3",
   ```
   so the reason travels with the pin and can't be lost.
2. **An entry in the Break Register (§4)** so the re-test trigger is
   tracked in one place a sweep can scan.

This applies to **any** dependency in §2 — a dev/gate tool held below
latest (e.g. a ruff release that breaks a rule the project relies on)
needs the same comment + register row as a runtime library.


## 4. The Break Register

The living record of every below-latest pin. When a version **newer than
the recorded "last-broken" version** ships, the re-test trigger fires:
re-run the affected feature's tests against the new version. If it now
passes, **remove the pin and the register row** (and bump). If it still
breaks, update the row's "last-broken" to that newer version so the
trigger re-arms only above it (no point re-testing versions already known
to break).

Columns:

| Dependency | Held at | Last-broken version | What it breaks (feature / INV / test) | Why no workaround | Re-test when | Recorded (date) |
|------------|---------|----------------------|----------------------------------------|-------------------|--------------|-----------------|

**(Currently empty — the project holds no dependency below its latest
release. Every runtime pin in `pyproject.toml` is a reproducibility pin at
the then-latest version, §3.)**

Rules for the register:
- One row per below-latest pin. If a bump would clear it, clear it — the
  register only holds *active* constraints, not history (git holds
  history).
- "Last-broken version" is the **newest** version confirmed to break the
  feature — so any release **above** it is what's worth re-testing (you
  already know everything up to and including it breaks).
- "Re-test when" is a concrete trigger (a version number, "any release
  `> X`"), not "eventually".


## 5. Sweep posture — check, don't wait

Do not only bump when something breaks. Surface what's behind, on cadence:

- `python -m pip list --outdated` (runtime + dev deps).
- `gh api repos/<owner>/<action>/releases/latest` for each pinned CI
  action; check `runs-on:` / `container:` image tags against their latest.
- On a security advisory — `pip-audit` (already a gate stage,
  `scripts/ci-local.sh`), a Dependabot alert, or a distro CVE — **bump
  immediately**, ahead of any cadence. A security fix outranks a
  break-pin: if the only safe version also breaks a feature, take the safe
  version and log the breakage as a tracked entry in
  [`docs/known-issues.md`](../known-issues.md). That entry is **not** a
  Break Register row (you took the *latest* version, nothing is held
  back), but it carries the same re-test discipline: record the version
  that would need to ship to *both* stay safe **and** fix the feature, and
  clear the entry when it does. The security bump ships even though the
  feature is degraded — the gate stays green with the documented
  known-issue rather than blocking the security fix; the degraded feature
  is fixed as a follow-up.

Run the sweep at least at the start of each release cycle, and
opportunistically whenever you're editing a manifest (`pyproject.toml`, a
workflow, `ci-setup.sh`) for any other reason.


## 6. Bumping is not just a version number

When you bump a dependency, **update the code that calls it in the same
change** (global rule § 5b) — new idioms, renamed APIs, changed
signatures. The bump and the idiom-refresh ship together, or the codebase
rots into "compiles but nobody meant it." If the bump is a patch with no
API surface change, say so explicitly in the commit ("no caller changes —
patch only") rather than skipping the check.

A dependency bump that changes behaviour follows the normal gate
([`scripts/ci-local.sh`](../../scripts/ci-local.sh)) and, for a native
stack, the bundling smoke-test (FIBR-0003) — a new library version that
travels into the frozen bundle is only "done" once the clean-room launch
still passes.


## 7. Project overrides

Project-specific tweaks go here, appended as a new subsection, per the
[standards README](README.md) convention. (None yet.)
