---
paths:
  - "scripts/ci-local.sh"
  - "scripts/ci-setup.sh"
  - "scripts/ci-docker.sh"
  - "scripts/build-smoke.sh"
  - ".githooks/**"
  - ".github/workflows/**"
  - "pyproject.toml"
---

# The gate: setup, tag pushes, CI's environment, the doc-only test

Part of this project's instructions, kept out of `CLAUDE.md` so it loads
only when needed. `CLAUDE.md` says when to read it.

## Requirements and one-time dev setup

**Requirements:** Python ≥ 3.12 and the standalone binaries below on `PATH` —
none of them pip packages. Every one carrying a version is pinned by
`scripts/ci-setup.sh` (that script is the list; no count is stated here, so
adding one cannot make this go stale):

| Binary | Pinned | Why the version matters |
|---|---|---|
| [`git`](https://git-scm.com/) | any | **a run-time dependency of the gate, not just of checkout** — the gitignore and bundling feature tests shell out to `git check-ignore` / `git rev-parse` / `git ls-files` |
| [`gitleaks`](https://github.com/gitleaks/gitleaks/releases) | 8.30.1 | a different build runs a different rule engine over the same `.gitleaks.toml` |
| [`shellcheck`](https://github.com/koalaman/shellcheck/releases) | 0.11.0 | rule set differs per release; distro builds lag badly |
| [`actionlint`](https://github.com/rhysd/actionlint/releases) | 1.7.12 | ships its own checks *and* shells out to `shellcheck` |
| [`zizmor`](https://github.com/zizmorcore/zizmor/releases) | 1.29.0 | audit set grows per release; a newer build fails a tree an older one passed |

Each **pinned** one is version-sensitive the same way: an older build runs a
**different rule set over the same files**, so a local gate can pass where CI
fails (or vice versa). Check with `gitleaks version`, `shellcheck --version`,
`actionlint --version`, `zizmor --version`.

**One-time dev setup** — an isolated env, then `scripts/ci-setup.sh`, which
installs *everything else the gate needs and does not itself provide*: the
system libraries PySide6 dlopens, `git`, the pinned binaries above, the dev
toolchain (ruff, bandit, pip-audit, pytest, pytest-qt, mypy + `types-PyYAML`)
**and the runtime deps** (PySide6, SQLCipher, pikepdf), which the FIBR-0003
self-test guard imports. It is the same script `ci.yml` and `ci-docker.sh` call,
so a local environment cannot drift from CI's:

```bash
python3 -m venv .venv
. .venv/bin/activate
./scripts/ci-setup.sh                    # ← the step that makes the gate runnable
```

**Do not skip that third line.** Without it `./scripts/ci-local.sh` (CLAUDE.md § Build and test) exits
**127** at the first tool it cannot find — the venv is fine, the gate simply has
no tools. *Which* tool depends on what you skipped: skip `ci-setup.sh`
entirely and it dies on `ruff: command not found`, because `ruff` is the
gate's very first stage and the script's Python half is what installs it.
Install the dev group by hand but not the pinned binaries (the openSUSE route
below) and it gets as far as `shellcheck`/`git: command not found` instead.
**The two fixes are NOT the same.** On an apt host, run `ci-setup.sh`. On this
desktop it cannot help you — the script is apt-only — so install the
Requirements binaries, `git` and the Qt libraries by hand per the openSUSE route
below. Verified by executing this section in a clean container 2026-08-11
(FIBR-0260).

`ci-setup.sh` assumes a **Debian/Ubuntu apt** host (the
`python:3.12-slim-bookworm` image CI runs; it falls back to `sudo` when not
root). On any other distro — this desktop is openSUSE — install the
Requirements binaries, `git` and the Qt system libraries `ci-setup.sh` names by
hand, then run its Python half yourself:

```bash
python -m pip install --upgrade pip      # PEP 735 --group needs pip >= 25.1
python -m pip install --group dev
python -m pip install .                  # runtime deps — the self-test test loads them
```

## Tag-only pushes and CI's environment

**A tag-only push needs no `--no-verify` and never did: the hook skips it by
itself.** The habit of reaching for the flag there came from a double gate that
no longer runs — a bypass no project document sanctioned (FIBR-0290;
[`docs/history/claude-md.md`](../../docs/history/claude-md.md)). The hook reads the ref
list git gives it and exits early when
**every** ref is a tag **and** every tagged commit is already reachable from a
branch of the remote being pushed to — not any remote, since a commit that
reached another one with `--no-verify` was never gated. Anything else still takes the gate: a branch ref
anywhere in the push, a tag whose commit is not yet on the remote (skipping
that would publish ungated code), or a hand-run hook with no refs on stdin (run from a terminal, it does not wait
for any).
Locked by `tests/features/harness/` INV-5, which runs the hook against a real
throwaway repo rather than reading it. **So do not type `--no-verify` for a
tag** — if the gate runs on one, that is the hook telling you the commit is not
on the remote yet.

**Reproduce GitHub CI's ENVIRONMENT when the diff could move it** — the local
gate runs on your desktop, which already has system libraries (Qt's
`libGL`/`libEGL`/fontconfig, `git`) that a clean CI runner lacks, so a green
local gate can still hide a red CI. That is the one gap the pre-push hook
cannot close, because the hook runs the same script in the same environment.

**It is not required before every push** — that would put a multi-minute
container rebuild in front of every commit. Run it when the diff could move
the environment: a dependency added, bumped or removed; a change to
`pyproject.toml`, `scripts/ci-setup.sh`, `ci.yml` or the Dockerfile-ish parts
of the build scripts; a new module that dlopens a system library; or the first
push after any of those. Otherwise `ci-local.sh` (or the hook) is enough. Run
the gate inside the **same container image CI uses**
(`python:3.12-slim-bookworm`, fresh installs):

```bash
./scripts/ci-docker.sh                # CI's own image + both CI scripts; needs podman/docker
```

**It runs CI's image and CI's two scripts — it is not the whole workflow.**
The two `ci.yml` steps it does not execute, and the tree it runs against, are
named in `release.md` § `cut-release` Phase 2b; do not report a green run here as a
full pipeline run.

**It refuses `--build`.** `ci-setup.sh` installs no container runtime, so
inside the container the smoke test would hit
`pytest.skip("no container runtime (podman/docker) on PATH")`
(`test_INV2_INV3_build_smoke_clean_room` in
`tests/features/bundling/test_bundling.py`) and **silently not run** — a skip
that reads as coverage. Run `./scripts/ci-local.sh --build` or
`./scripts/build-smoke.sh` on the host instead.

`ci.yml` and `ci-docker.sh` both run the same image and both call
`scripts/ci-setup.sh` (environment: system libs + the pinned non-pip binaries —
gitleaks, shellcheck, actionlint, zizmor — + deps) then
`scripts/ci-local.sh` (the gate) — one definition each, so local and CI cannot
drift. If a dependency bump needs a new system library, add it in **one place**
(`ci-setup.sh`).

## Doc-only pushes: how the hook decides

**The wider list costs a fraction of a second** against the old two — not a
saving worth reasoning about.

**What counts as "only documentation": every path the push changes ends in
`.md`.** The hook takes, for each ref, `git diff --name-only <remote tip>
<pushed commit>`. It fails closed: a new branch has no remote tip, so it takes
the full gate, as does a range git cannot resolve. That is the whole test, and
two things about it are deliberate.

**The unit is the PUSH, not the last commit** — every commit going up, which is
what that range gives you. Judge it by the commit you just made and an ungated
code commit already queued behind it rides through the gate on a ROADMAP line's
coat-tails, which breaches "a code change never skips the full gate" with
nothing to notice it.

**And the test is POSITIVE — a suffix, never a list of directories.** A closed
list of directories cannot express "not code": `.githooks/pre-push`,
`.gitleaks.toml`, `.gitignore` and any stray `.sh`, `.toml` or `.yml` all escape
one. `.githooks/pre-push` is the case that proved it, and it is shell that
`ci-local.sh`'s shellcheck stage names explicitly
(`shellcheck "${SH_FILES[@]}" .githooks/pre-push`) — so a deny-list would have
skipped the one stage reading what had just changed. Do not reinstate one
([`docs/history/claude-md.md`](../../docs/history/claude-md.md)).

**A `.md` anywhere counts** — `tests/features/<name>/spec.md` and
`packaging/flatpak/README.md` included. The suites and the `gitleaks`
scan in CLAUDE.md § Doc-only pushes are what cover those. Anything else takes the full gate.

**The checks are unconditional — there is no "only if it looks like a number"
branch.** An earlier version of this rule had one, and it asked the person least
able to answer it: you have just written the prose and know what you meant by it,
which is exactly when a pasted number does not read as one. Pedigree in
[`docs/history/claude-md.md`](../../docs/history/claude-md.md).
