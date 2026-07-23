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
```

The **build phase is network-free** (every source is sha256/commit-pinned) — the
same constraint as Flathub's builders, so a dependency that slips to an
offline-unbuildable sdist fails locally, before submission (§ 3.6). After it
builds, run the **manual § 5 smoke checks** the build script prints (portal
open/save, updater disabled, Center-window disabled under Flatpak+KDE-Wayland,
zero app-initiated network).

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
3. Fork `flathub/flathub`, branch from `new-pr`, add **at the repo root**:
   `io.github.milnet01.finbreak.yaml` + `python3-deps.yaml` + `flathub.json`
   (copies of these three, with the reused-asset install commands reaching the
   assets through the git clone — no `packaging/obs/` sits beside a submitted
   manifest, § 3.2). `flathub.json` restricts the buildbot to `x86_64` — the arch
   the pinned wheel closure covers (INV-9); without it the default aarch64 build
   fails on the x86_64-only wheels.
4. Open a PR titled `Add io.github.milnet01.finbreak`. The reviewer checks it
   builds entirely from pinned source, passes the linter, and has valid metainfo.
   Be ready to justify the binary (manylinux) wheels as upstream-published,
   pinned, SBOM-disclosed versions (§ 5 — Flathub tolerates but scrutinises them).
5. On merge, Flathub creates the app's repo and builds/hosts it.

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
