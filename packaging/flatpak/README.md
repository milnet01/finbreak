# Flatpak / Flathub packaging — maintainer runbook (FIBR-0159)

Publishes finbreak to [**Flathub**](https://flathub.org) — the cross-distro app
store that surfaces in GNOME Software + KDE Discover on every Flatpak-enabled
distro. One submission covers openSUSE, Fedora, Ubuntu, Debian, Mint, … See
`docs/specs/FIBR-0159.md` for the full design and rationale.

Unlike the OBS RPM/deb (FIBR-0155, PyInstaller freeze under `/usr/lib`), the
Flatpak **pip-installs the exact pinned wheel closure into `/app`** on the
freedesktop runtime — the same closure the gate tests, in a **sandbox** (no
network, no filesystem beyond the file the user picks through the portal). The
sandbox is the finance-app security story.

## Files

| File | Role |
|------|------|
| `io.github.milnet01.finbreak.yaml` | the `flatpak-builder` manifest (runtime, modules, `finish-args`, reused assets) |
| `python3-deps.yaml` | **generated** — sha256-pinned pip sources for the dependency closure |
| `flathub.json` | Flathub build config — `only-arches: [x86_64]` (the closure is x86_64-only; INV-9) |
| `generate-pip-sources.sh` | regenerates `python3-deps.yaml` (derives `--prefer-wheels` from the resolved closure) |
| `flatpak-build.sh` | local build + install + `--self-test` smoke |
| `README.md` | this runbook |

The desktop entry, AppStream metainfo, and hicolor icons are **reused from
`packaging/obs/`** (the single source of truth, FIBR-0155 § 3.3) — the `finbreak`
module installs them from its own git clone, so no copies live here.

## One-time prerequisites

```sh
# The runtime + Sdk the manifest builds on (from Flathub).
flatpak install flathub org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08
# The generator needs this python module in the interpreter that runs it. Install
# it into the project venv (a system python3 is usually PEP-668 externally-managed);
# generate-pip-sources.sh auto-detects an active venv / ./.venv.
. .venv/bin/activate && python -m pip install requirements-parser
```

## Build + test locally

```sh
packaging/flatpak/generate-pip-sources.sh   # regenerate python3-deps.yaml (online)
packaging/flatpak/flatpak-build.sh          # build (OFFLINE) + install --user + self-test
packaging/flatpak/flatpak-build.sh --run    # ...and launch the GUI
LOCAL=0 packaging/flatpak/flatpak-build.sh  # build the manifest AS SUBMITTED
```

The **build phase is network-free** (every source is sha256/commit-pinned) — the
same constraint as Flathub's builders, so a dependency that slips to an
offline-unbuildable sdist fails locally, before submission (§ 3.6). After it
builds, run the **manual § 5 smoke checks** the build script prints (portal
open/save, updater disabled, Center-window disabled under Flatpak+KDE-Wayland,
zero app-initiated network).

**The default build is not the submission.** `LOCAL=1` (the default, for dev
iteration) rewrites the `finbreak` module's source to your local checkout at
branch HEAD; `LOCAL=0` builds the committed manifest verbatim, from the release
commit it pins — which is what Flathub builds. The two can disagree, and once
did: the FIBR-0257 CVE bump was in HEAD and in the closure while the pinned tag
still asked for the old `cryptography`, so every default build was green and the
submission build failed outright. **`LOCAL=0` is the pre-submit path** (step 2
below); the gate's `test_FIBR0258_closure_satisfies_the_pinned_commit` catches
the same drift without a build.

## Submitting to Flathub (first time)

New apps go on the **`new-pr` base branch** of `github.com/flathub/flathub`
(not `master`):

1. **Re-pin the release.** In the manifest, set the `finbreak` module's git
   `tag:`/`commit:` to the newest release (an immutable commit, § 3.8), and
   **regenerate `python3-deps.yaml`** if the closure changed since.
2. Confirm the § 5 pre-submit checklist (`docs/specs/FIBR-0159.md` § 5):
   `flatpak remote-info flathub org.freedesktop.Platform//25.08` still current;
   the Sdk's `python3 --version` matches the pinned wheel ABI; `appstreamcli
   validate packaging/obs/io.github.milnet01.finbreak.metainfo.xml` passes; the
   metainfo `<screenshot>` URLs resolve to real images.

   **Also confirm the closure still matches `pyproject.toml`.** Step 1's
   "regenerate if the closure changed" is a judgement call, and it has already
   been got wrong once: a `cryptography` CVE bump landed in `pyproject.toml` and
   the closure kept the old pin for two weeks (FIBR-0256). Cheapest check is to
   regenerate and `git diff` — an empty diff *is* the confirmation.

   **Then build the manifest as submitted** — `LOCAL=0
   packaging/flatpak/flatpak-build.sh` — and confirm it ends in
   `FINBREAK_SELFTEST_OK`. A default (`LOCAL=1`) build proves nothing about the
   submission: it swaps in your working tree. Last run green 2026-08-12 against
   the v0.1.20 pin.

3. **Run Flathub's own linter** — its docs tell submitters to, and a failure
   blocks the PR. Neither check needs a build:

   ```sh
   flatpak install flathub org.flatpak.Builder      # one-time
   flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
       manifest packaging/flatpak/io.github.milnet01.finbreak.yaml
   flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
       appstream packaging/obs/io.github.milnet01.finbreak.metainfo.xml
   ```

   Both must exit 0. The `appstream` check is a wrapper around `appstreamcli`
   *with Flathub's own overrides*, so it is the authority over a bare
   `appstreamcli validate` — and unlike the gate's `--no-net` run it really does
   fetch every `<screenshot>` URL. After a build, `... repo repo` lints the
   exported OSTree repo too; Flathub runs the manifest and repo checks on its
   own infrastructure regardless.

   Flathub also asks that the build itself go through `org.flatpak.Builder`
   rather than a host `flatpak-builder`; `flatpak-build.sh` still uses the host
   one, which is fine for local iteration but is not what their infra runs.

4. Fork `flathub/flathub`, branch from `new-pr`, add **at the repo root**:
   `io.github.milnet01.finbreak.yaml` + `python3-deps.yaml` + `flathub.json`
   (copies of these three, with the reused-asset install commands reaching the
   assets through the git clone — no `packaging/obs/` sits beside a submitted
   manifest, § 3.2). `flathub.json` restricts the buildbot to `x86_64` — the arch
   the pinned wheel closure covers (INV-9); without it the default aarch64 build
   fails on the x86_64-only wheels.
5. Open a PR titled `Add io.github.milnet01.finbreak`. The reviewer checks it
   builds entirely from pinned source, passes the linter, and has valid metainfo.
   Be ready to justify the binary (manylinux) wheels as upstream-published,
   pinned, SBOM-disclosed versions (§ 5 — Flathub tolerates but scrutinises them).
   You can ask their bot for a test build by commenting `bot, build`.
6. On merge, Flathub creates the app's repo and builds/hosts it. Accept the
   repo-write invitation **within one week**, with 2FA enabled on the GitHub
   account — both are Flathub requirements.

## Ongoing releases

Each new finbreak version is a PR to the app's Flathub repo bumping the `finbreak`
module's `tag:`/`commit:` and regenerating `python3-deps.yaml` **only if the
closure changed**. `/bump` already keeps the metainfo `<release>` in lockstep with
`CHANGELOG.md` (FIBR-0155 § 3.7).

## Follow-ups (not in the first cut)

- **aarch64.** `generate-pip-sources.sh` pins `--wheel-arches=x86_64` only (matching
  OBS's x86_64-only posture). Flathub also builds aarch64; enabling it needs every
  pinned native to publish an aarch64 manylinux wheel — verify per dep, then add
  `aarch64` to `--wheel-arches` and rebuild.
- **Auto-update PR** from CI on release (out of scope, § 2).
- **Hoist the shared desktop/metainfo/icon assets** to a common `packaging/`
  location once a second backend shares them (§ 7 — deferred, not rejected).
