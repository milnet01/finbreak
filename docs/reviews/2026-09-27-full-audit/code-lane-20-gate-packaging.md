Lane 20: the quality gate, pre-push hook, CI workflow and Linux packaging (Flatpak, OBS rpm/deb). Depth pass.

**Subject files and line counts as I read them:**
- `scripts/ci-local.sh`: 108
- `scripts/ci-setup.sh`: 134
- `scripts/ci-docker.sh`: 32
- `.githooks/pre-push`: 100
- `.github/workflows/ci.yml`: 64
- `packaging/flatpak/flatpak-build.sh`: 80
- `packaging/flatpak/generate-pip-sources.sh`: 127
- `packaging/flatpak/io.github.milnet01.finbreak.yaml`: 106
- `packaging/obs/finbreak.spec`: 210
- `packaging/obs/debian/rules`: 95
- `packaging/obs/debian/control`: 53
- `packaging/obs/finbreak.sh`: 10
- `packaging/obs/_service`: 37
- `packaging/obs/obs-setup.sh`: 61
- `packaging/obs/obs-status.sh`: 52
- `packaging/obs/obs-submit.sh`: 89
- `packaging/obs/vendor-wheels.sh`: 35

**Context I arrived holding** (disclosed before reading the subject):
- the global `~/.claude/CLAUDE.md` and `/mnt/Games/CLAUDE.md`;
- the whole finbreak `CLAUDE.md`, every section, preloaded by the harness — I did not read it myself, but I saw more than the two sections the lane allows;
- the finbreak memory index;
- a git snapshot (HEAD 52e5162, clean tree);
- the shared-context file, which includes the CLAUDE.md module map and the false-positive ledger.

**Contracts I read:**
- FIBR-0001 § Invariants (INV-1 to INV-6).
- FIBR-0155 § 3.4 to § 4.
- FIBR-0159 § 3.6 to § 4.
- **Not read:** ADR-0007 (turn budget) and FIBR-0159 § 3.4 (its INV-2 covers `finish-args`).

**Test tree:** never opened. Every search excluded `tests/**`.

**Where the brief and FIBR-0001 disagree:** the brief says FIBR-0001 INV-5 is the tag-only skip. On disk, FIBR-0001 INV-5 is "Security stage is non-bypassable". The tag-only lock that CLAUDE.md cites is `tests/features/harness/` INV-5, which is a test-tree spec. I went with the spec as written and did not open the test-tree one.

## Critical (0)

## High (1)
- [dim 2] `packaging/obs/finbreak.spec:65` — `BuildRequires:  libxkbcommon0` (Fedora `:80` `libxkbcommon`; `debian/control:29` ` libxkbcommon0,`)
  - **Problem:** libxkbcommon is installed in the freeze build root, so PyInstaller bundles it. `libxkbcommon-x11` is neither installed nor declared in `Requires:`/`Depends:`.
  - **Effect:** on X11 sessions, Qt's xcb plugin pairs the bundled libxkbcommon with the host's libxkbcommon-x11. That is the mismatched pair `_build-smoke-in-container.sh:31-38` records as a segfault (FIBR-0208). On a minimal host the plugin cannot load at all.
  - **Which side is wrong:** the code. FIBR-0155 § 3.5 itself says these recipes are wrong and tracks the fix as FIBR-0346. It is reported here because the shipped rpm/deb carry the defect today.
  - **Fix:** remove it from BuildRequires/Build-Depends. Add `libxkbcommon0` + `libxkbcommon-x11-0` (and the per-distro rpm names) to runtime `Requires:`/`Depends:`.

## Medium (6)
- [dim 2] `.githooks/pre-push:91` — `if ! git diff --quiet HEAD -- 2>/dev/null; then`
  - **Problem:** the hook's own comment (`:89-90`) and CLAUDE.md say untracked files "cannot make one look different". That is false. An untracked `src/finbreak/newmod.py` imported by a committed file, i.e. a forgotten `git add`, makes ruff, mypy and pytest pass on disk. The pushed commit then fails on import.
  - **Why it matters:** this is the same "fix present in the tree but not in the commit" direction FIBR-0327 set out to close.
  - **Which side is wrong:** both. The code does what the doc says, and the doc's premise is false.
  - **Fix:** also refuse when `git ls-files --others --exclude-standard -- src tests` is non-empty.
- [dim 2] `.githooks/pre-push:45-71`, then `:100` `exec ./scripts/ci-local.sh`
  - **Problem:** the gate always checks the working tree of HEAD, but the pushed ref may not be HEAD. Examples: `git push origin feature` while on `main`, or `git push origin HEAD~2:main`. Nothing compares each pushed branch's `local_sha` with `git rev-parse HEAD`, so a green verdict about HEAD lets a different, ungated commit through.
  - **Fix:** in the stdin loop, refuse when a non-deletion branch ref's `local_sha` differs from `HEAD`.
- [dim 3] `scripts/ci-setup.sh:42` — `git config --global --add safe.directory '*'`
  - **Problem:** CLAUDE.md tells apt-host developers to run this script. On such a host it permanently writes a wildcard into the user's `~/.gitconfig`, and a new duplicate entry on every run. That switches off git's repository-ownership protection (the CVE-2022-24765 class) for every repository the user touches.
  - **Why the comment is wrong:** it says "harmless on a developer's own repo", but the setting is global, not per-repo.
  - **Fix:** set it only when `id -u` is 0 or `$CI`/a container is detected; otherwise use `git config --global --add safe.directory "$PWD"` once, or `GIT_CONFIG_*` env vars for the run.
- [dim 3] `scripts/ci-setup.sh:76-78, 90-92` — `tar -xJ -C /tmp -f /tmp/shellcheck.tar.xz "shellcheck-v${SHELLCHECK_VERSION}/shellcheck"` … `$SUDO install -m 0755 "/tmp/shellcheck-v…/shellcheck" /usr/local/bin/shellcheck`
  - **Problem:** download and extract paths in `/tmp` are fixed and predictable. On a multi-user dev host (the sudo path), another user can pre-create `/tmp/shellcheck-v0.11.0/`. tar then extracts into a directory that user owns, and they can swap the binary after the checksum check and before the root `install`. `/tmp/gitleaks.tar.gz` and the other fixed files have a similar race, depending on `fs.protected_regular`. The files are also never cleaned up.
  - **Scope:** a CI container is unaffected.
  - **Fix:** `tmp=$(mktemp -d)` plus a `trap 'rm -rf "$tmp"' EXIT`, and use `$tmp` for every path.
- [dim 3] `packaging/flatpak/generate-pip-sources.sh:37,59,113` — `GEN_URL=".../flatpak-builder-tools/master/pip/flatpak-pip-generator.py"`, then `curl -sSL -o "$GENERATOR" "$GEN_URL"`, then `"$PYGEN" "$GENERATOR"`
  - **Problem:** the script runs an unpinned, unverified script from a moving `master` branch on the host. That script writes every sha256 pin the offline Flathub build then trusts, so a compromised upstream produces malicious pins that look legitimate.
  - **Diverged duplicate logic:** `ci-setup.sh:46-54` argues "A VERSION PIN IS NOT AN INTEGRITY PIN" and verifies every fetch. This fetch verifies nothing.
  - **Second defect:** without `-f`, an HTTP error page is saved as the generator and cached for good (`REFETCH` defaults to 0).
  - **Fix:** pin to a commit SHA URL, add a sha256 check through a `fetch_verified`-style helper, and use `curl -fsSL`.
- [dim 2] `packaging/obs/_service:15` — `<param name="revision">main</param>`
  - **Problem:** the vX.Y.Z packages are built from the tip of `main`, not the release. FIBR-0155 § 3.6 says the service fetches "the tagged source tarball (obs_scm/tar_scm on `v{VERSION}`)", and `obs-submit.sh:66` says "obs_scm pulls the tagged source". Neither is true.
  - **How the version drifts:** the version comes from `@PARENT_TAG@`, the latest tag. So a package labelled 0.1.23 contains any unreleased commits that sit on `main` after that tag.
  - **Version skew inside one submission:**
    - the source comes from GitHub `main`;
    - the recipes are copied from the local working tree, which may hold uncommitted edits (`obs-submit.sh:44-46`);
    - `vendor.tar.gz` is reused even when it was built from an older `pyproject.toml` (`:24`);
    - the commit message takes its version from local `__init__.py` (`:86`).
  - **Which side is wrong:** the code, against the spec's contract. The `_service` comment does admit "during bring-up".
  - **Fix:** have `obs-submit.sh` rewrite `revision` to `v$VER` (and refuse on a dirty tree or one ahead of origin) before `service manualrun`.
- [dim 2] `scripts/ci-docker.sh:11` — `#   scripts/ci-docker.sh --build      # also run the FIBR-0003 build smoke-test`
  - **Problem:** the script's own usage line advertises a mode that silently does not run. `ci-setup.sh` installs no container runtime, so inside the container the build test skips. CLAUDE.md § Build and test says exactly this: "Do not pass `--build` to it".
  - **Which side is wrong:** the code/comment.
  - **Fix:** make `ci-docker.sh` refuse `--build` with a message pointing to `ci-local.sh --build` on the host, and drop the example line.

## Low / Info
- [dim 7] `packaging/obs/obs-submit.sh:63,82-84`: `osc rm … || true`, `osc add … 2>/dev/null || true`, `osc addremove 2>/dev/null || true`. Errors are thrown away, so `osc commit` can commit a revision missing the new tarball or `debian.tar.gz`, and nothing says so. Fix: drop the stderr redirect and `|| true`, and tolerate only the specific "already under version control" case.
- [dim 7] `packaging/obs/obs-status.sh:23-51`: exits 0 even when builds failed or `MAX_POLLS` ran out, and never says it timed out. Fix: track a failure flag and exit non-zero; echo a timeout notice.
- [dim 4] `packaging/flatpak/flatpak-build.sh:53-54` vs `:59`: the first `flatpak-builder` call passes `--disable-rofiles-fuse`, the install call does not. On a host that needs the flag, the second call fails, and it rebuilds from scratch rather than installing the artefact just exported. Fix: one invocation with `--install --repo=…`, or the same flags on both.
- [dim 16] `packaging/flatpak/flatpak-build.sh:37`: `git rev-parse --abbrev-ref HEAD` returns `HEAD` on a detached checkout, and the LOCAL manifest then asks for a branch named `HEAD`. Fix: use `git rev-parse HEAD` and a `commit:` key.
- [dim 16] `.githooks/pre-push:45`: when the hook is run by hand from a terminal, `while read` blocks on the tty until Ctrl-D. The comment at `:39-40` ("with no stdin … the gate runs") assumes EOF. Fix: `[ -t 0 ] && skip the loop`.
- [dim 3] `.githooks/pre-push:67`: `git branch -r --contains` treats "reachable from any remote-tracking branch of any remote" as "already gated". A commit pushed with a sanctioned `--no-verify` (the pip-audit-flake bypass) is then skipped again at tag time. This matches the CLAUDE.md wording, so the contract's premise is what is weak. Fix: restrict the check to `refs/remotes/$1/`, and accept the remaining gap knowingly.
- [dim 2] `scripts/ci-local.sh:4-5,18`: two header comments are stale.
  - "ci.yml installs the dev dependency group and gitleaks" — ci.yml delegates that to `ci-setup.sh`.
  - "FIBR-0003 later appends a build smoke-test stage" — FIBR-0001 INV-1 says it is "not a stage of its own".
  - Fix: reword both. The comments are wrong, not the code.
- [dim 2, doc side, for review-contract] FIBR-0155 § 3.6 says the vendoring produces "both cp312 and cp313" and that Fedora is on 3.13. `vendor-wheels.sh:30` vendors 3.12, 3.13 and 3.14, with Fedora 44 on cp314. FIBR-0159 already notes the prose is stale. The spec is wrong, not the code.
- [dim 11] `scripts/ci-setup.sh:75,89,…`: it downloads x86_64-only binaries with no arch check. On an arm64 apt host it installs binaries that cannot run, and the first failure is only at `gitleaks version`. Fix: check `uname -m` first.
- **Coverage notes (INFO):**
  - Every packaging finding is static. None was executed (no Bash).
  - I did not verify the `.gitleaks.toml` allowlist beyond `.venv/`.
  - I did not check `finbreak.dsc` or `finbreak-rpmlintrc`, which `obs-submit` copies but which are outside my lane list.

## Covered by spec and looks correct
- **Gate stages:** `ci-local.sh` runs exactly the 11 stages in FIBR-0001 INV-1's table, with the contractual `gitleaks --redact --config` flags, `git ls-files '*.sh'` plus `.githooks/pre-push` as shellcheck targets, `set -euo pipefail`, and the repo-root `cd`.
- **CI workflow:** `ci.yml` matches INV-2 — container pinned by digest, only git-install / checkout / setup / gate steps, no setup-python and no pip step, `persist-credentials: false`, `contents: read`.
- **Local CI image:** `ci-docker.sh` uses the same digest, and its args pass through correctly (`_ "$@"`).
- **Tag-only skip:** the hook handles tag deletions (zero sha), annotated-tag peeling, any branch ref in the push, and the no-refs case, all as CLAUDE.md states.
- **Pinned binaries:** `ci-setup.sh` downloads to a file, checks the sha256, then extracts. Versions match the CLAUDE.md table.
- **Flatpak manifest:**
  - `finish-args` is exactly FIBR-0159 INV-2's allowlist;
  - freedesktop runtime/sdk with a pinned `25.08` (INV-1);
  - the git source has a 40-hex `commit`, and `tag v0.1.23` matches `__version__`;
  - `command: finbreak`.
- **OBS recipes:**
  - both `%if suse`/`%if fedora` branches are present;
  - `Requires`/`Depends` hold libGL/libEGL (+ hicolor);
  - every build-phase `pip install` carries `--no-index`;
  - the self-test runs the staged buildroot path under `QT_QPA_PLATFORM=offscreen` (INV-1, INV-2, INV-7);
  - the PyInstaller flag lists in the `.spec`, `debian/rules` and `_build-smoke-in-container.sh` are identical.
- **Launcher:** `finbreak.sh` does exec plus `"$@"` (INV-2).

## Open questions
- Does `osc results PROJ PKG` print a package column? `obs-status.sh` reads status from `$4`. If osc prints only repo/arch/status, every row reads as pending until `MAX_POLLS`, and the failure-log loop misreads the columns. Unexecuted — needs one real `osc results` output.
- The Flatpak `finbreak` module runs `pip3 install --no-build-isolation --no-index .`, and `pyproject.toml` needs `setuptools>=77`. setuptools is not in the generated prefer-wheels list. Does Sdk 25.08 ship setuptools ≥ 77? Unexecuted — needs a `flatpak-builder` run. FIBR-0159 INV-3 names this as the only check.
- `ci-docker.sh:27` cites "harness INV-6" for digest parity, but FIBR-0001 INV-6 is single-test ergonomics. It presumably means the test-tree spec, which I did not open. If it means FIBR-0001, the citation is wrong.

## 3 items to fix first
1. **The libxkbcommon bundling in the OBS rpm/deb (High).** It is a known segfault class shipping in packages today, and every X11 user of those packages is exposed.
2. **The pre-push hook: untracked files, plus a pushed ref that is not HEAD (two Mediums).** Both let the one mandatory local gate report green about code that is not what leaves the machine. The fixes are two small checks in `.githooks/pre-push`.
3. **`ci-setup.sh`'s global `safe.directory '*'` and its fixed `/tmp` paths (two Mediums).** The script runs with root rights on developers' machines. One setting quietly weakens git's security for every repository the user touches, and the other opens a local binary-swap race.