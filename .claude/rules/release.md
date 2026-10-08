---
paths:
  - "scripts/release-*.sh"
  - "scripts/build-release-appimage.sh"
  - "scripts/build-windows-exe.py"
  - "scripts/sign-release.py"
  - "scripts/gen-checksums.sh"
  - ".claude/bump.json"
  - "CHANGELOG.md"
  - "packaging/**"
---

# Cutting a release: `gh release create` is NOT the end

Part of this project's instructions, kept out of `CLAUDE.md` so it loads
only when needed. `CLAUDE.md` says when to read it.

`cut-release` carries the version bump and the tag. **Run it with
`--no-publish`** (FIBR-0275), so it creates no GitHub release: the release is
`release-linux.sh`'s to create, with its downloads attached. `.claude/bump.json` carries less still — its
`_comment` says "this recipe covers the version bump only -- the signed
AppImage build + publish is a separate manual step". The AppImage and
the Windows `.exe` are built and attached by `scripts/release-linux.sh`
and `scripts/release-windows.sh`, and **nothing invokes those for you**.
(`bump.json`'s note points at the same two scripts.)

**A release can publish with ZERO assets, and both the README's "download the
latest release" link and the in-app updater resolve to that page.** It has
happened twice — FIBR-0203, then again on v0.1.20. **The guard LANDED on
2026-08-19** (FIBR-0275, INV-8): both release scripts read the published asset
list back and refuse to report success on an incomplete set. **Since FIBR-0275
nobody running `release-linux.sh` publishes nothing at all**: with
`--no-publish` no release page exists until that script creates one with its
five assets, so the empty page both cases left cannot be published. The
eight-asset read-back at the end of this section is still yours to run, for the
Windows half. Pedigree in
[`docs/history/claude-md.md`](../../docs/history/claude-md.md).

So the release path is, in order — the bump comes first, and the
**push** is a step rather than a tidy-up:

```bash
cut-release <X.Y.Z> --no-publish  # a SKILL — invoke it; it is not on PATH. Bumps
                             #   every version-bearing file, commits, tags and
                             #   pushes; creates NO release (FIBR-0275)
. .venv/bin/activate         # both scripts need cryptography
./scripts/release-linux.sh   # creates the release (--latest, CHANGELOG notes)
                             #   with the AppImage + .sig + SHA256SUMS +
                             #   SHA256SUMS.sig + linux SBOM -> FIVE assets
./scripts/release-windows.sh # .exe + .sig + windows SBOM, and it RE-UPLOADS
                             #   SHA256SUMS + .sig having merged into them
# then re-pin the Flatpak commit: (below)
```

**No release candidates on this path.** `release-linux.sh` publishes
`v<__version__>` as the latest full release, and `cut-release --pre rc.N` leaves
`__version__` as `X.Y.Z`, so an RC run through this script would ship as
`vX.Y.Z`. Do not combine them.

**`cut-release` is what performs step 1**, including the commit, the tag
and the push, so do not hand-run those as well. If you bump by hand
instead, the bump must be committed **and pushed** before
`release-linux.sh` — see the first bullet below. Either way step 1 must
have happened: run `release-linux.sh` against an unbumped tree and it
reads the *old* `__version__` and finds that release's tag, then refuses unless
HEAD is that tagged commit; if it is, it `--clobber`s assets onto the
**previous** release.

Worth knowing before you run them:

- **The bump must be PUSHED, not merely committed — and since FIBR-0327
  `release-linux.sh` enforces it.** It fetches `origin` and refuses on an
  unpushed HEAD. Before that guard, a committed-but-unpushed bump passed and the
  script tagged the **remote's** HEAD — the pre-bump commit — publishing assets
  built from a version the tag does not point at
  ([`docs/history/claude-md.md`](../../docs/history/claude-md.md)).
  **Once the tag exists it also refuses unless HEAD is the tagged commit**, so
  commit nothing between `cut-release` and this script — or run it from
  `git checkout v<X.Y.Z>`, which it accepts (audit row 41).
  (`dist/` is gitignored, so a dirty tree here is
  your own ROADMAP or CHANGELOG edit.) Do not pipe either script
  through `grep`/`tail` while debugging — that masks its exit status and
  a refusal reads as success.
- **`release-linux.sh` is safe against a release that already exists** —
  step 7 branches to `gh release upload --clobber`. So a release created
  by hand first (as 0.1.21 was) gets its assets and is not duplicated, but
  **assets only**: that branch sets no notes, title or `--latest`, so check those
  with `gh release view` and correct them with `gh release edit`.
- **`release-windows.sh` needs no Windows machine**; it dispatches
  `windows-build.yml` on the tag and waits, so it needs `gh` with
  **workflow + repo** scope but **no container runtime** — the freeze
  happens on a GitHub runner. Public repo, so the minutes are free.
  Only `release-linux.sh` needs `podman`/`docker` (it builds and
  clean-rooms the AppImage locally). **Both** need the Ed25519 key at
  `release/finbreak-signing.key` — gitignored, local-only, and already
  present on this machine. **Do not run `scripts/gen-signing-key.py` to
  "fix" a missing key**: it mints a *new* one, which the hard gate
  against the committed `RELEASE_PUBLIC_KEY_B64` then rejects, and a
  release signed with it would be invisible to every installed copy's
  updater.
- **Re-pin the Flatpak `commit:` afterwards.** `bump.json` bumps the
  manifest's `tag:` mechanically, but its sibling `commit:` cannot be —
  the sha does not exist until the release is tagged. `release-linux.sh`
  prints the sha as its last line; set it in
  `packaging/flatpak/io.github.milnet01.finbreak.yaml`. Nothing verifies
  the two point at the same object — one of the two gaps left in the
  release path, the other being that nothing checks `release-linux.sh`
  was run at all (FIBR-0275).
- **A failed upload no longer skips the read-back gate (FIBR-0327).** Both
  scripts capture the publish command's exit status instead of letting
  `set -e` end the run there. `--clobber` deletes each asset before
  replacing it, so a failure part-way down the list leaves the release SHORT —
  the state the gate reports — and the script used to die before reaching
  it. The gate now runs either way, and a
  complete asset list after an errored upload still exits non-zero: the
  names being right does not prove the bytes are.

Finish by reading the result back yourself — **not** because the scripts skip
it. Since 2026-08-19 each one re-reads its own upload and refuses to report
success on an incomplete set, both doing so *before* they print "DONE". What
that leaves is the Windows half, which lands later or not at all, and the page's
text: with `--no-publish` nothing compares the notes with the CHANGELOG, and
`release-linux.sh` writes `Release X.Y.Z.` when the `[X.Y.Z]` section is missing.
The title is the fixed `finbreak vX.Y.Z`.

```bash
gh release view v<NEW> --json assets -q '[.assets[].name]|join(", ")'
gh release view v<NEW> --json body -q .body   # must be the CHANGELOG [X.Y.Z] section
```

**A complete release carries EIGHT assets**, and anything less is broken
rather than quiet: the AppImage, the `.exe`, a `.sig` for each,
`SHA256SUMS`, `SHA256SUMS.sig`, and **both** SBOMs
(`finbreak-<V>-linux.cdx.json` *and* `finbreak-<V>-windows.cdx.json`).
Compare against v0.1.18, v0.1.19 and v0.1.21, which all carry exactly
that set. A five-asset read-back means the Windows half has not landed —
still building, or failed — and `release-windows.sh` exits non-zero
*after* the Linux assets are already public, so a red Windows build
leaves a `--latest` release the README and the updater both resolve to
with no Windows download. Re-run it; do not walk away from a short list.

**Expect transient GitHub API failures, and retry before diagnosing.** One
release hit them on four different endpoints — `gh repo view`, the tag push, the
`windows-build.yml` dispatch and the asset upload — and every one cleared on a
retry ([`docs/history/claude-md.md`](../../docs/history/claude-md.md)).

**The upload failure is the dangerous one, because it half-succeeds.**
`release-windows.sh`'s final `gh release upload --clobber` deletes each existing
asset before replacing it, so a failure mid-list can leave a release carrying
`SHA256SUMS.sig` but **not** `SHA256SUMS`, and `.exe.sig` but **not** the `.exe`
— a signed release whose signed manifest is gone.

If you land there, the artifacts in `dist/` are already built, signed
and verified, so re-upload them rather than rebuilding — **one file per
call, so a partial failure is visible**:

```bash
for f in dist/finbreak-<V>-x86_64.exe dist/finbreak-<V>-x86_64.exe.sig \
         dist/SHA256SUMS dist/SHA256SUMS.sig dist/finbreak-<V>-windows.cdx.json; do
    gh release upload v<NEW> "$f" --clobber || echo "FAILED $f"
done
```

Then read the assets back again. A batched upload wrapped in a pipe is
how the half-state goes unnoticed twice.

If the *dispatch* is what is failing, **just re-run `release-windows.sh` until
it gets through** — the failure is intermittent rather than deterministic, and
has needed several attempts. Do **not** dispatch by hand as a workaround: the
script's `gh workflow run` is unguarded under `set -euo pipefail`, so it
dispatches its *own* run and waits for a run newer than the one it recorded on
entry. Your hand-dispatched build is discarded and a Windows freeze is burned for
nothing — which has happened
([`docs/history/claude-md.md`](../../docs/history/claude-md.md)).

If the script stops **after** the build was dispatched — a failed watch,
download or identity check — do not re-run it bare, which starts a second
freeze. Resume the same build with `scripts/release-windows.sh --run-id <id>`;
the script prints the id as soon as the run registers.

Finish the Windows half through the script, never by hand: the steps
you would be skipping are the Ed25519 signing and its verification
against the committed public key.

### `cut-release` Phase 2b on this project is `scripts/ci-docker.sh` (user decision 2026-08-19, FIBR-0295)

`cut-release` Phase 2b runs the CI pipeline locally *before* the release
commit, and the skill's own rule is to execute `.github/workflows/*.yml` with
`act` and **never** substitute anything — because a hand-written mirror
"returns green for a pipeline that will fail". **On this project the substitute
is sanctioned, and this section is that authorisation.** `act` is installed on
this machine (`/usr/bin/act`) and has never been configured: with no TTY its
first run prints a runner-image menu and dies `level=fatal msg=EOF`, so the
phase cannot run as designed. Filed as **FIBR-0295**; the decision is to adopt
the substitute rather than configure `act`.

**So Phase 2b here is `./scripts/ci-docker.sh`**, and the session's own
Phase 2b report names the three uncovered items below. **Not the published
release notes** — those are `release-linux.sh`'s, lifted from the
`CHANGELOG.md` `[X.Y.Z]` section when it creates the release (FIBR-0275), and
they are what end users read on the download page, so a CI-coverage caveat does
not belong there.

**Why the ban does not bite: `ci-docker.sh` is not a mirror of the pipeline, it
is the pipeline's own two scripts.** `ci.yml` has one job, four steps — install
`git`, `actions/checkout`, `./scripts/ci-setup.sh`, `./scripts/ci-local.sh` —
inside `container: python:3.12-slim-bookworm`. `ci-docker.sh` runs the **same
image** and calls the **same two scripts by name**. There is no second
definition of the gate that could drift from the first, which is exactly the
failure the skill's rule protects against, and FIBR-0001 INV-2 locks the
single definition with `tests/features/harness/` enforcing it.

**Three things it does NOT cover.** State them; do not report a full pipeline
run.

1. **`actions/checkout` running at all** — a bad SHA, a network failure, a
   revoked action. Its *static* properties are still checked here: `zizmor`
   is a `ci-local.sh` stage, so this run does read `ci.yml`'s pin and
   `persist-credentials: false` — measured by reverting the pin to a mutable tag
   and watching `zizmor` fail
   ([`docs/history/claude-md.md`](../../docs/history/claude-md.md)). So do not list the
   pin as uncovered; what is uncovered is the step executing.
2. **The `apt-get install git ca-certificates` step** before checkout. Its
   *effect* is covered — `ci-setup.sh` installs `git` as well — but the step
   itself never executes.
3. **The tree under test is your working copy, not the commit.**
   `ci-docker.sh` sends the container the tracked files and `.git` — never
   untracked or gitignored ones, so `.corpus-numbers` stays out, as it does on
   GitHub. What differs is that an uncommitted edit to a tracked file is
   tested here, while `actions/checkout` tests the commit. Commit first when
   the run is meant to stand for the push.

**If `act` is ever configured on this machine this override lapses.**
*Configured* means `~/.config/act/actrc` exists **and**
`act push -W .github/workflows/ci.yml -n </dev/null` exits 0. Check both at
Phase 2b — `act --version` succeeds on an unconfigured install and settles
nothing. Both were measured false on 2026-08-19, so the override stands
([`docs/history/claude-md.md`](../../docs/history/claude-md.md)). When it lapses, Phase 2b goes
back to executing the workflows themselves and this section is deleted rather
than left standing as a second answer.
