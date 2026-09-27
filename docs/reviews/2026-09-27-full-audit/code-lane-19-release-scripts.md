## Lane 19: release path. Depth pass

**Subject files and their line counts as I read them.** All paths are under `/mnt/Games/Scripts/Linux/finbreak/`.
- `scripts/release-linux.sh`: 340
- `scripts/release-windows.sh`: 309
- `scripts/build-release-appimage.sh`: 19
- `scripts/build-windows-exe.py`: 147
- `scripts/windows_freeze_flags.py`: 77
- `scripts/sign-release.py`: 80
- `scripts/gen-signing-key.py`: 92
- `scripts/gen-checksums.sh`: 51
- `scripts/make-icons.sh`: 68
- `scripts/build-smoke.sh`: 181
- `scripts/_build-smoke-in-container.sh`: 241
- `scripts/seed_demo_vault.py`: 255
- `scripts/capture_screenshots.py`: 162
- `.github/workflows/windows-build.yml`: 148
- `.github/workflows/build-smoke.yml`: 47

**What I held before reading anything.** The harness preloaded the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, and the **whole** finbreak `CLAUDE.md`. That is more than the one section my brief allows: it includes § Build and test, § cut-release Phase 2b and § Push policy. It also preloaded the project MEMORY.md index, which has entries on tag-push, the signing key and pushing after each commit, and a git snapshot at HEAD 52e5162. I did not re-read CLAUDE.md.

**What I read outside the subject files.**
- The contract docs: security-model INV-13 and the passage above it at line 68, FIBR-0003 § Invariants and § Failure modes, the FIBR-0054 invariant table and Phase 1, FIBR-0155 § 3.9, and ADR-0007.
- Three files a claim put in play: `.claude/bump.json` (only its post_check-related lines), `update_installer.py` `asset_suffix`, and `theme.py` DEFAULT_*.

**Search tools.** `workspace_search` hit its rate limit, so I used `Grep`. No search touched `tests/`.

## Critical (0)

## High (0)

## Medium (3)

- **[dim 2] `scripts/release-linux.sh:69-71` and `:202-212`**
  - Quoted: `UNPUSHED="$(git rev-list --count '@{u}..HEAD')"` and `gh release view "$TAG" … gh release upload … --clobber`.
  - **What's wrong.** Nothing checks that the AppImage is built from the commit `$TAG` points at.
    - The FIBR-0327 guard only counts commits that are local but not pushed.
    - On the path CLAUDE.md documents, `cut-release` has already created the tag and the release, so the script takes the upload branch. That branch never compares `HEAD` with `$TAG^{commit}`.
    - Any commit pushed after `cut-release` therefore gets frozen into the AppImage for vX.
    - Meanwhile `release-windows.sh:74-78` builds the .exe from the tag itself, and it does have a headSha identity check.
  - **Second gap, on the create branch.** `gh release create` has no `--target`, so GitHub tags the default branch's HEAD.
    - The check only covers "local ahead of remote". If local is behind the remote, or on another branch, the tag lands on a commit that was not built.
  - **Fix.** If `$TAG` exists (check with `git ls-remote origin refs/tags/$TAG`), require `git rev-parse HEAD` to equal `$TAG^{commit}`. Otherwise pass `--target "$(git rev-parse HEAD)"` and also require `HEAD == @{u}`.

- **[dim 9] `scripts/release-linux.sh:126-127`, `scripts/release-windows.sh:137-138`**
  - Quoted: `if grep -qx SHA256SUMS "$VIEW_ASSETS"; then … fi`.
  - **What's wrong.** When the release exists but `SHA256SUMS` is not listed, both scripts silently start a new manifest.
    - That is exactly the 0.1.21 half-state: `SHA256SUMS.sig` present and `SHA256SUMS` missing after a failed `--clobber`.
    - Re-running either script to repair it publishes a manifest with only one platform's line. The other platform's line is lost.
    - The 8-asset read-back still passes, because it checks names only.
  - **This contradicts the scripts' own claim.** Both say re-running either script "never regresses the manifest to a single platform" (`release-linux.sh:109-111`, `release-windows.sh:122-123`). It also weakens the INV-13 signal: a missing line is supposed to be read as a red flag.
  - **Fix.** Refuse and exit when `SHA256SUMS` is absent but `SHA256SUMS.sig` is present, or when the other platform's artifact is present. Only an unambiguous empty release should start a new manifest.

- **[dim 2] `scripts/build-smoke.sh:177-180`**
  - Quoted: `echo "    gh release create v$VERSION \\"` … `--notes \"First public release.\""`
  - **What's wrong.** Every `release-linux.sh` run prints, part-way through, a publish command that attaches only the AppImage and its `.sig`.
    - That is 2 of the 8 assets, with no `SHA256SUMS` and no SBOM, and it carries stale notes.
    - It is the recipe for the short-release failure that FIBR-0203 and FIBR-0275 record.
    - An operator who follows it after a later gate refuses publishes a broken `--latest` release.
  - **Fix.** Replace it with "next: `scripts/release-linux.sh` publishes; do not publish by hand".

## Low / Info

- **[dim 16] `scripts/release-windows.sh:56-59`**: `gh workflow run …` is followed by `TAG_SHA="$(git rev-parse "$TAG^{commit}")"`.
  - If the local tag is missing, `set -e` stops the script *after* the build was dispatched, wasting a Windows freeze.
  - Fix: compute `TAG_SHA` before the dispatch.

- **[dim 16] `scripts/release-windows.sh:74,81,88`**: `gh run view`, `gh run watch --exit-status` and `gh run download` are unguarded after the dispatch.
  - This is the same set-e shape as the known trap. A transient 503 on any of them throws away a finished build.
  - There is no way to resume against an existing `RUN_ID` (for example a `--run-id` option). Fix: add one, or retry these three calls.

- **[dim 2] `scripts/release-windows.sh:262`**: `if [ "$ASSET_COUNT" -ne 8 ]` counts assets without naming them. The Linux side names its five (`:266-278`).
  - One stray extra asset makes a complete release fail every time.
  - Conversely, a stray asset standing in for a missing linux SBOM passes.
  - Fix: check the eight exact names, as `release-linux.sh` does for its five.

- **[dim 4] `scripts/release-linux.sh:49-53`**: the comment says `mirrors .claude/bump.json's post_check`, but the check covers four files.
  - `bump.json` post_check also gates the metainfo and the deb changelog (lines 40 and 42, FIBR-0155 § 3.9) and the Flatpak `tag:`.
  - The two copies have diverged. Fix: add the missing three, or call post_check itself.

- **[dim 16] `.github/workflows/windows-build.yml:121-122`**: `Start-Process … -Wait -PassThru` runs with no `timeout-minutes` on the job.
  - A hung self-test holds the runner for up to 6 h, and `gh run watch` waits the whole time. Fix: set `timeout-minutes`.

- **[dim 2] `.github/workflows/windows-build.yml:16`**: `runs-on: windows-latest`, while `build-smoke.yml:17` says "Pinned, not `-latest` — see ci.yml".
  - The .exe users download is built on a runner image that changes over time. See Open questions.

- **[dim 3] `scripts/_build-smoke-in-container.sh:178`**: `if [ ! -x "$TOOL" ]; then` skips the checksum for a cached appimagetool.
  - The comment at `:168-170` names exactly this persistence hazard. Fix: re-run `sha256sum -c` on every use.

- **[dim 7] `scripts/build-smoke.sh:117`**: `… | "$RUNNER" build … >/dev/null` makes a failed clean-room image build exit with no diagnostic. Fix: send the output to stderr.

- **[dim 8] Both release scripts** fetch, merge and upload `SHA256SUMS` without taking any lock.
  - Running both at once loses one platform's line. Only the documented order (Linux first, then Windows) prevents it.

- **[dim 7] `scripts/capture_screenshots.py:152`**: `if source.exists():` skips curated shots silently.
  - With `--themes midnight`, old `ledger` files stay in `site/`, giving a mixed-date set. Fix: warn, or clear `site/` first.

- **[dim 2] `scripts/capture_screenshots.py:31`**: `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`.
  - A `QT_QPA_PLATFORM` already set in the environment wins, which contradicts the docstring's "no display". Fix: assign it outright.

- **[dim 2] `scripts/seed_demo_vault.py:19,27`**: the CLI usage in the docstring imports `finbreak` without adding `src` to the path.
  - It resolves against whatever package is installed in the venv, which may be older than `src/`. Fix: add the same `sys.path` insert that `capture_screenshots.py:36` has.

- **One line for each remaining dimension:**
  - dim 5: nothing found (sign and verify read whole artifacts into memory, which is bounded).
  - dim 10: N/A for these scripts.
  - dim 11: `make-icons.sh` uses GNU `mktemp --suffix`, but it is a dev-host tool, so no finding.
  - dim 12: N/A.
  - dim 13: nothing found (the demo seed's `date.today()` is cosmetic).
  - dim 15: nothing found (only the key *path* is printed, never key material).
  - dim 17: N/A; the updater asset suffixes match `update_installer.py:264,340`.

- **INFO: nothing was executed.** No Bash was available. The M1/M2 scenarios are traced from the code only; confirming them needs a throwaway release run.

## Covered by spec and looks correct

- **`gen-signing-key.py`**: creates the key with `O_EXCL` at mode 0600 and refuses to overwrite an existing one.
- **`sign-release.py`**: writes a raw 64-byte Ed25519 signature and type-checks the key (FIBR-0054 INV-14).
- **Signature checks**: all six verification heredocs check against `RELEASE_PUBLIC_KEY_B64`, before publishing.
- **Anti-laundering (INV-13)**: each script verifies the fetched manifest before it merges and re-signs.
- **FIBR-0327**: the upload exit code is captured, the read-back always runs with 3 retries, and a failed upload still exits non-zero.
- **FIBR-0275 INV-8**: the Linux phase checks its five assets by name and the Windows phase checks the count of eight. Both confirm every `.sig` has its artifact.
- **Windows run identity**: the headSha check at `:74-78` binds the build run to the tag.
- **`gen-checksums.sh`**: merges lines, keeps basenames only, and sorts in C order.
- **FIBR-0003**: INV-2/INV-3 clean-room flags, podman-first selection, and the exact-line sentinel match.
- **FIBR-0054 INV-15**: the GUI entry point is frozen.
- **Freeze-flag parity**: `windows_freeze_flags.py` matches the in-container flags at lines 143-159 exactly.
- **Supply chain**: appimagetool is pinned to a release with a checksum, and a missing SBOM is caught (the `|| true` is guarded by an existence check).

## Open questions

- Does ci.yml's "pinned, not -latest" runner rule bind `windows-build.yml`? I did not read ci.yml, and nothing I read says whether it applies there.
- M1 assumes a commit can land between `cut-release` and `release-linux.sh`. The "push after each commit" memory makes that plausible, but I cannot tell whether `cut-release` itself blocks it.
- **Arrival context:** I held the whole finbreak CLAUDE.md, not just the one section my brief allows. My reading of "cut-release creates the release first" comes from the permitted § Cutting a release.

## 3 items to fix first

1. **M1 (the AppImage built from a commit other than the tag's).** It publishes signed binaries for vX whose code differs from both the tag and the .exe, and the in-app updater installs them. None of the existing gates can see it.
2. **M2 (a repair re-run shrinking SHA256SUMS to one platform).** The failure it triggers on is the one already recorded on 0.1.21, and its result passes the 8-asset read-back unnoticed.
3. **M3 (the misleading publish command printed during every release).** It is a one-line fix that removes a printed recipe for the zero- or short-asset release this project has already shipped twice.