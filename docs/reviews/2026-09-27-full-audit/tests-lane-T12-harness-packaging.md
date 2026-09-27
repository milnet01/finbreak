## Chunk T12: 8 files read

**Line counts as read:**
- `tests/features/harness/test_gate_stages.py`: 457
- `tests/features/prose_checks/test_prose_checks.py`: 230
- `tests/features/release_integrity/test_release_integrity.py`: 660
- `tests/features/bundling/test_bundling.py`: 658
- `tests/features/flatpak_packaging/test_flatpak_packaging.py`: 537
- `tests/features/obs_packaging/test_obs_packaging.py`: 630
- `tests/features/windows_build/test_windows_build.py`: 273
- `tests/features/gitignore/test_gitignore.py`: 129

None of the eight directories contains a `conftest.py` or any other `.py` file.

**Already in my context before I read anything:**
- global `~/.claude/CLAUDE.md`
- `/mnt/Games/CLAUDE.md`
- the finbreak project `CLAUDE.md`
- the finbreak `MEMORY.md` index
- a git snapshot (main, clean, HEAD `52e5162`)

I read the shared context file once, as instructed.

**Which tool ran:** `workspace_search` was rate-limited on one batch of four calls. Those four searches ran on `Grep` instead, and none was left unrun.

**Code opened one hop, for Q1 only (no findings filed against it):**
- `.githooks/pre-push`
- `main_window._kde_wayland` and `main_window._center_supported`
- grep hits in `scripts/build-windows-exe.py` and `scripts/release-{linux,windows}.sh`
- a tree-wide grep for `pyinstaller==` and `pip-audit==`
- a grep for `FINBREAK_BUILD_SMOKE` and `python3-deps` across `scripts/`, `.github/workflows/` and `.gitignore`

### Findings

**[HIGH] [dim 1] tests/features/release_integrity/test_release_integrity.py:270** (runs to :275)
> "SHA256SUMS.sig" in before_merge and "RELEASE_PUBLIC_KEY_B64" in before_merge

Consequence: this check is meant to prove the fetched manifest is verified before the merge. Its own comment says *"deleting it strips the only SHA256SUMS.sig verify before merge"*. That is false. Text before the merge also contains other matches:
- `release-linux.sh:116` `rm -f "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig"`
- the AppImage-signature verify at `:81`–`:88`, which names `RELEASE_PUBLIC_KEY_B64`

The Windows script has the same pair at `:128` and `:103`–`:110`. So you can delete the whole fetched-manifest verify block (linux `:136`–`:144`, windows `:147`–`:155`) and the test stays green. That block is the anti-laundering check.

Fix: anchor to the verify block itself — for example, require `SHA256SUMS.sig` and `RELEASE_PUBLIC_KEY_B64` inside one `python3 - "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig"` heredoc located before the merge.

**[MEDIUM] [dim 1] tests/features/bundling/test_bundling.py:361** (the scan runs to :382; the bound is set at :331–:332)
> for rel in tracked: … sites += 1 … assert sites >= min_sites

Consequence: the `min_sites` bound is meant to catch *"did a build path stop pinning it"*. But the scan counts matches in every tracked file, prose included:
- `docs/journal/FIBR-0003.md:21`
- `docs/specs/FIBR-0155.md:479` and `:869`
- `FIBR-0096.md`
- `FIBR-0015.md` (three matches)
- `.claude/workflow.md:1338`
- `tests/features/release_integrity/spec.md:52` and the release-integrity test file itself

That is about 15 `pyinstaller==` sites against a bound of 6, and about 8 `pip-audit==` sites against 2. Dropping the pin from `debian/rules` or `windows-build.yml` leaves the count above the bound, and the test stays green.

The same scope makes a legitimate pin bump fail until the dated records are rewritten, and `docs/journal/FIBR-0003.md` is one of them.

Fix: restrict the scan to build paths (exclude `docs/`, `*.md` and `.claude/`), then bound on the named build files.

**[MEDIUM] [dim 1] tests/features/release_integrity/test_release_integrity.py:582**
> assert re.search(r"\bexit\s+[1-9]\d*\b", guard)

Consequence: the "guard region" runs from the read-back to the end of the file. It therefore contains unrelated exits, such as the *"could not read … assets back after 3 attempts"* exit at `release-linux.sh:245` (windows `:251`) and the PUBLISH SUSPECT exit at `:318` (windows `:306`). Turn the incomplete-set exits (linux `:277`, `:295`, `:308`) into warnings and the test still passes. The test claims *"an incomplete-set finding must abort"*.

Fix: bind the `exit` to the incomplete-set branch, for example the block following the count or subject comparison.

**[MEDIUM] [dim 8] tests/features/flatpak_packaging/test_flatpak_packaging.py:110**
> if not _DEPS.exists(): pytest.skip("python3-deps.yaml not generated yet (generate-pip-sources.sh)")

Consequence: the condition has expired. `python3-deps.yaml` is now generated and committed:
- `.gitignore` does not name it
- FIBR0256's own message says "commit the result"
- the skip did not fire on this machine

Yet `test_recipe_files_present` (:528) does not list it. So deleting or renaming the file turns six guards into skips instead of failures: INV3a, INV3b, INV3c, INV7, FIBR0256 and FIBR0258, plus INV9 after its first assertion. A skip reads as coverage.

Fix: add `_DEPS` to `test_recipe_files_present` and drop the skip, or make it fail.

**[MEDIUM] [dim 8] tests/features/bundling/test_bundling.py:310**
> if _container_runtime() is None: pytest.skip("no container runtime (podman/docker) on PATH")

Consequence: this skip fires after the user has explicitly opted in with `FINBREAK_BUILD_SMOKE=1`. The project `CLAUDE.md` documents the exact route: `ci-docker.sh --build` sets the variable inside a container with no runtime, and the build+clean-room proof *"silently does not run"*. An opted-in run should never report the build as covered.

Fix: once opted in, `pytest.fail` on a missing runtime rather than skip.

**[LOW] [dim 8] tests/features/bundling/test_bundling.py:308**
> if not script.exists(): pytest.skip("scripts/build-smoke.sh not present yet")

Consequence: the condition has expired. The script exists, and other tests read it unconditionally (`:399`, and release_integrity `:364`). If it were deleted, an opted-in run would skip instead of failing.

Fix: remove the branch.

**[LOW] [dim 1] tests/features/release_integrity/test_release_integrity.py:332**
> assert "freeze" in driver

Consequence: this is always true. `build-windows-exe.py:26` has `import windows_freeze_flags as flags`, and `test_driver_uses_canonical_flag_list` requires that import. So removing the `pip freeze` call at `:87` leaves this check green. Only the `runtime-frozen.txt` substring remains, and that check survives any other content being written there.

Fix: assert on `"pip", "freeze"` or on the argv literal.

**[LOW] [dim 1] tests/features/windows_build/test_windows_build.py:234** (the same shape at :223, :229 and :260)
> assert re.search(r"PySide2|PySide6|PyQt5|PyQt6", src)  # single-Qt guard (INV-2)

Consequence: this matches the `_QT_BINDINGS` tuple at `build-windows-exe.py:38` and the docstring. Delete the guard logic that refuses more than one binding and the test stays green. The same applies to three other checks, each satisfied by a docstring or comment line:
- `"os.pathsep"` (:223), satisfied by the docstring at `build-windows-exe.py:9`
- `"tomllib" and "dependencies"` (:229)
- `"FINBREAK_SELFTEST_OUT"` in `__main__.py` (:260)

Fix: import the driver and exercise the guard function, or strip comments and docstrings before matching.

**[LOW] [dim 1] tests/features/harness/test_gate_stages.py:185**
> assert f"run: {stage}" not in ci

Consequence: this catches only a single-line `run: ruff`. A stage restated inside a `run: |` block (such as `ruff check .` on its own line) passes, which is exactly the second definition of the gate that INV-2 forbids.

Fix: parse `ci.yml` with `yaml` and scan every step's `run` body for stage names.

**[LOW] [dim 1] tests/features/gitignore/test_gitignore.py:40**
> subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

Consequence: `git init` inherits the user's global and system config, including `init.templateDir`, whose `info/exclude` is honoured by `check-ignore`. The `core.excludesFile=/dev/null` at :56 does not neutralise it. A template excluding `*.db` would keep INV-1 green after the project `.gitignore` lost that rule. This is the FIBR-0306 shape that `harness/test_gate_stages.py:214` already fixed.

Fix: run both git calls with `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM=os.devnull`, as `_HERMETIC_GIT` does.

**[LOW] [dim 6] tests/features/bundling/test_bundling.py:21** (the same at gitignore/test_gitignore.py:23)
> subprocess.run(["git", "rev-parse", "--show-toplevel"], … check=True)

Consequence: the project root is taken from the process's working directory, not the test file. Run pytest from outside a repo and both modules error at collection. Run it from inside another repo and the gitignore suite tests that repo's `.gitignore`, which could pass. Every other file in this chunk uses `Path(__file__).resolve().parents[3]`.

Fix: use `parents[3]`.

**[LOW] [dim 6] tests/features/windows_build/test_windows_build.py:51**
> td = Path(tempfile.mkdtemp())

Consequence: each run of `test_binary_created_vault_opens_cross_package` leaves an encrypted vault pair in `/tmp` and never removes it. On this machine `/tmp` is RAM-backed.

Fix: pass `tmp_path` into `_open_vault`.

**[LOW] [dim 5] tests/features/bundling/test_bundling.py:313**
> result = subprocess.run([str(script)], cwd=_PROJECT_ROOT)

Consequence: there is no timeout, and the file itself notes (:44–:46) that no pytest-timeout plugin is configured. A hung container build blocks an opted-in `ci-local.sh --build` indefinitely.

Fix: add a generous `timeout=`.

### Pre-pass verdicts
- `test_flatpak_packaging.py:480` setenv_call: **false positive**. It is `monkeypatch.setenv`, which reverts automatically. The variable is load-bearing: `_kde_wayland` reads `XDG_CURRENT_DESKTOP` at `main_window.py:284`.
- `test_flatpak_packaging.py:495` setenv_call: **false positive**, for the same reason.

### Dimensions scanned
- 1: 7 findings
- 4: settled by the orchestrator, and my files agree
- 5: 1 finding. No sleeps or network. The hook-sandbox git runs are local `file://` pushes. `_run_cli` has a timeout.
- 6: 2 findings. `monkeypatch` everywhere else, and `tmp_path` sandboxes.
- 7: nothing found. Sets are compared as sets, and the manifest order is sorted by the code under test.
- 8: 3 findings. The `FINBREAK_BUILD_SMOKE` opt-in reason is live: `ci-local.sh:31` sets it and `:101` reads it. The `appstreamcli` skips carry a reason and a live condition.
- 9: nothing found. Every write goes to `tmp_path`, a `mkdtemp`, or (opt-in only) the gitignored `dist/`. No real remote: the INV-5 hook tests push to a bare repo under `tmp_path`.
- 11: nothing found. `test_FIBR0326_the_cryptography_check_passes_on_a_working_stack` has no assert, but the call is the check: this is the does-not-raise carve-out.
- 12: N/A. No per-test timing was supplied.
- 14: nothing found. The one `except (OSError, UnicodeDecodeError): continue` at bundling :367 skips binary files and does not wrap an assertion.
- 15: N/A. Nothing in this chunk is failing.

### Noted, not mine
- None.

### Possibly wider
- The ambient `git rev-parse --show-toplevel` root may appear in other suites outside this chunk.
- Unhermetic `git init` (global config inherited) may appear in other suites that build a throwaway repo.

### Open questions
- `test_flatpak_packaging.py:452` (FIBR0258) skips when the pinned commit is not in the clone. `actions/checkout` fetches one commit by default, so this guard may always skip in CI. This needs a check of `ci.yml`'s checkout `fetch-depth` or a CI log. The skip has a reason and a live condition, so I have not filed it.
- The INV-5 hook tests pass `os.environ` through (`test_gate_stages.py:218`). When the gate itself runs under a real `git push`, any git-exported hook variables would reach the sandbox git calls. Unexecuted: it needs the suite run from inside `.githooks/pre-push`, compared with a bare `pytest tests/features/harness/`.
