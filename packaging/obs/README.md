# OBS packaging — maintainer runbook (FIBR-0155)

Native RPM/deb publishing for finbreak via the
[openSUSE Build Service](https://build.opensuse.org). The package installs a
PyInstaller `--onedir` frozen runtime under `/usr/lib/finbreak/` — the same
pinned native closure the gate tests (SQLCipher, qpdf, pdfium, Qt bundled
in-tree), not distro-shared libraries. See `docs/specs/FIBR-0155.md` for the
full design and rationale.

## Files

| File | Role |
|------|------|
| `finbreak.spec` | RPM recipe (openSUSE + Fedora) |
| `debian/` | deb recipe (Debian + Ubuntu) — shipped to OBS as `debian.tar.gz`, never as a directory |
| `finbreak.dsc` | deb source-control file. Without it OBS marks every Debian/Ubuntu target "excluded" and builds no `.deb` at all |
| `obs-setup.sh` | create/update the OBS sub-project + package + build targets (one-time, idempotent) |
| `obs-submit.sh` | vendor → populate the checkout → run services → commit a revision (per-release) |
| `obs-status.sh` | poll the build results + tail any failing build log |
| `vendor-wheels.sh` | builds `vendor.tar.gz` — the offline wheel closure (run on a glibc ≥ 2.34 host) |
| `finbreak-rpmlintrc` | filters rpmlint noise inherent to the bundled foreign tree (openSUSE gate) |
| `io.github.milnet01.finbreak.desktop` | desktop entry (menu + launcher association) |
| `io.github.milnet01.finbreak.metainfo.xml` | AppStream component (software-centre listing) |
| `finbreak.sh` | the `/usr/bin/finbreak` launcher wrapper |
| `_service` | pulls the tagged source (obs_scm) + injects the version (set_version) |

## Where it lives

A dedicated **sub-project `home:milnet:finbreak`** (isolated from other packages
in `home:milnet`, with its own build targets), package `finbreak`. Public repo:
`https://download.opensuse.org/repositories/home:/milnet:/finbreak/`.

## Target matrix (all **x86_64-only** — the bundled wheels are 64-bit)

| Family | Target | OBS path | Status (2026-08-31) |
|--------|--------|----------|---------------------|
| openSUSE | Tumbleweed | `openSUSE:Factory / snapshot` | ✅ built + published |
| Fedora | 44 | `Fedora:44 / standard` | ✅ built + published |
| Debian | 13 (trixie) | `Debian:13 / standard` | ✅ built + published (FIBR-0158) |
| Ubuntu | 24.04 LTS | `Ubuntu:24.04 / universe` | ✅ built + published (FIBR-0158) |
| openSUSE | Leap 15.6 | `openSUSE:Leap:15.6 / standard` | ⏳ pending a `%if 0%{?sle_version}` python313 branch |

The **glibc ≥ 2.34** floor gates buildability (the PySide6/cryptography wheels
are tagged `manylinux_2_34`). Leap 15.6 (glibc 2.38) clears it; its blocker is
the legacy default `python3` (3.6), not glibc.

## Submit flow (scripted)

Version flows **one way**: the newest `v*` git tag drives `set_version`, which
writes the `.spec` + `debian/changelog` `Version:` — never hand-edited
(obs_packaging INV-6). Prerequisites: the `osc` CLI (logged in once), and
`obs-service-tar` + `obs-service-obs_scm` (`zypper in osc obs-service-tar
obs-service-obs_scm`). Vendoring needs a **glibc ≥ 2.34** x86_64 host.

```sh
packaging/obs/obs-setup.sh     # once: create the sub-project + package + targets
packaging/obs/obs-submit.sh    # vendor → populate → services → commit a revision
packaging/obs/obs-status.sh    # poll results; tail any failing build log
```

All three take defaults for `home:milnet:finbreak/finbreak` on
`api.opensuse.org`, overridable via env vars (`OBS_API`, `OBS_PROJECT`,
`OBS_PACKAGE`, …; see each script's header). `obs-submit.sh` reuses an existing
`vendor.tar.gz`; pass `REVENDOR=1` to rebuild it (do so when the dependency
closure or a target's default python changes). The spec's `%check` runs the
frozen `--self-test` with `FINBREAK_SELFTEST_DEBUG=1`, so a Qt/native failure
prints its real traceback in the build log.

`_service` tracks `revision=main` with `match-tag=v*` during bring-up (builds the
newest release code + derives the version from the latest `v*` tag). For a pinned
release, set `revision` to that tag.

**Doing it by hand** (what the scripts automate): `osc checkout
home:milnet:finbreak finbreak`, copy the recipe files + `vendor.tar.gz` in, `osc
service manualrun`, `osc add` the sources (`echo y | osc add debian` archives the
dir), `osc commit`, then `osc results` / `osc buildlog … <repo> x86_64`.

## Bugs bring-up surfaced (none catchable in CI — all fixed)

The build environment differs from every local/CI check, so these only appeared
on the real OBS builders:

1. **ofxparse sdist-only** — `--only-binary=:all:` fetched zero wheels; ofxparse
   is pre-built to a wheel and offered via `--find-links` (`vendor-wheels.sh`).
2. **`--` in an XML comment** — the vendoring command lived in an `_service`
   comment; shell `--flags` are illegal in XML comments and broke parsing. Moved
   to `vendor-wheels.sh`.
3. **Wrong version tag** — `@PARENT_TAG@` grabbed a `FIBR-*-complete` marker tag;
   fixed with `match-tag=v*`.
4. **Fedora 44 = Python 3.14** — vendored cp314 too (was 3.12/3.13 only).
5. **`libgthread-2_0-0`** — openSUSE splits it out of `libglib`; a Qt dep, so
   PyInstaller couldn't bundle it → `%check` failed loading Qt. Added to
   `BuildRequires`.
6. **`krb5`** — PySide6's freeze-time `_check_if_openssl_enabled()` imports
   QtNetwork → needs `libgssapi_krb5`. Added to `BuildRequires`.
7. **Fedora-only scriptlets + dir ownership** — the `%icon_theme_cache_post`
   macros are undefined on openSUSE (and, unbraced, bash reads them as job
   specs); wrapped in `%if 0%{?fedora}` (openSUSE uses file triggers). Added
   `hicolor-icon-theme` to Build+Requires so the icon dirs are owned.
8. **rpmlint badness** — the bundled foreign tree trips checks assuming a native
   package (missing-hash-section on Qt `.so`s dominated); filtered via
   `finbreak-rpmlintrc`.

The deb bring-up (FIBR-0158) surfaced five more, each hidden behind the one
before it. All but the first were latent from the start and unreachable while
the deb targets were excluded:

9. **No `.dsc`** — the reason both targets read "excluded". OBS needs a Debian
   source-control file before it attempts a `.deb` at all.
10. **`vendor/` rejected by `3.0 (quilt)`** — `dpkg-buildpackage` rebuilds the
    source package first, and the wheels sit outside `debian/` and cannot be a
    patch. `include-binaries` is NOT enough (still "unexpected upstream
    changes"); `debian/source/options` `extend-diff-ignore` is.
11. **`--add-data` resolved against `--specpath`** — not the working directory,
    so `debian/rules`' relative paths looked under `debian/`. Absolute now. The
    `.spec` passes `--specpath .`, which is why it never hit this.
12. **`dh_dwz`** — rejects the foreign closure outright (no `.debug_info`;
    allocatable sections after non-allocatable ones in Pillow's libraries).
    Overridden to nothing, on item 8's reasoning.
13. **`dh_strip` on Ubuntu 24.04** — its older `binutils` refuses Pillow's
    bundled libfreetype and pypdfium2's libpdfium where Debian 13's accepts
    both, so Debian went green a revision before Ubuntu. Excluded from the
    payload, like `dh_shlibdeps`.

**One class IS catchable locally now, and was not before**: a shell syntax
error in `debian/rules`. Nothing in the gate read that file — `shellcheck` does
not take a Makefile — so the first reader was an OBS build root. `obs_packaging`
INV-10 now parses every recipe command the way `make` runs them.

## Debugging a failing target: reproduce the build root, don't iterate on OBS

An OBS round trip is minutes per attempt and gives one failure at a time. Every
target's build root is reproducible locally with `podman`, and that is how the
FIBR-0158 bring-up was actually done. Use the target's own base image —
`debian:13-slim`, `ubuntu:24.04` — not this desktop, whose libraries mask the
failures.

- **The deb SOURCE package** ("unrepresentable changes", debtransform refusing a
  source archive): fetch `debtransform` from `openSUSE/obs-build`, run it over a
  directory holding the `.dsc` and the tarballs, then `dpkg-source -x` **and**
  `dpkg-source -b` the result in the target image. `-b` is the half that matters:
  `dpkg-buildpackage` rebuilds the source package before building the binary, and
  that is where `3.0 (quilt)` rejects things. A dummy `vendor.tar.gz` is enough.
- **The BUILD itself**: copy the tree plus `debian/` and `vendor/` into a scratch
  directory, mount it, install `debian/control`'s `Build-Depends` verbatim, and
  run `dpkg-buildpackage -b -us -uc`. This surfaces the debhelper steps that
  reject the bundled payload (`dh_dwz`, `dh_strip`) in one pass.
- **Then install the result** into a bare container of the same distro and run
  `finbreak --self-test`. Building is not evidence the package works; this also
  checks the dependency set stayed the host-left `libgl1`/`libegl1` pair.
- **Do NOT diagnose a missing library from `ldd`.** A sweep over the frozen tree
  reports ~50 not-found libraries, and almost all are optional Qt plugin
  dependencies (SQL drivers, the GTK platform theme, speech-dispatcher) plus
  intra-Qt references resolved by RPATH. Run the real freeze and read what it
  actually fails on.
- Mount scratch copies, not the repo: an SELinux relabel (`:z`) on a working
  tree under `/mnt/Games` is not something to do casually.

## Still open (§5 follow-ups)

- [x] **Debian + Ubuntu** — done 2026-08-31 (FIBR-0158). `finbreak.dsc` is the
      trigger; `vendor.tar.gz` reaches the build tree by being named in its
      `DEBTRANSFORM-FILES-TAR` beside `debian.tar.gz`, which debtransform
      concatenates verbatim so the wheels keep their `vendor/` prefix. A
      component orig tarball, which this list used to propose, cannot work:
      debtransform emits one `.orig` and one `.debian.tar` and regenerates the
      `Files`/checksum fields. `debian/source/options` then keeps `vendor/` out
      of the source-package diff, without which `dpkg-source` aborts on wheels
      it cannot represent as a patch. See § Bugs bring-up surfaced.
- [ ] **Leap 15.6** (FIBR-0160, deferred) — attempted; went *unresolvable*
      because Leap 15.6 ships **no python 3.12+** (`osc buildinfo`: "nothing
      provides python313"), and we vendor only cp312/cp313/cp314. Needs Leap's
      actual newest python3XX module + that ABI vendored. The spec keeps the
      `%{py3}`/`%{py3pkg}` abstraction ready for it.
- [ ] **Live `xprop WM_CLASS`** on the running app equals the `.desktop`'s
      `StartupWMClass=finbreak` (Qt-version quirk guard, § 3.3).
- [ ] **Real screenshots** uploaded to the homepage so the metainfo
      `<screenshot>` URLs resolve in the software centres.

## Ongoing releases

Each new finbreak version SHOULD become a new package revision in the OBS repo
(pulled by `zypper up` / `apt upgrade`), but **nothing performs that
automatically** — no step of the release path runs `obs-submit.sh`. Measured
2026-08-31: the package still held the 0.1.16 tarball while `__version__` was
0.1.22, with both RPM targets green the whole time, because they were green on
the old source. Tracked as FIBR-0317. Until it is closed, run `obs-submit.sh`
by hand after a release and read the target matrix back.

The `.claude/bump.json` recipe (run by `cut-release`) keeps the metainfo
`<release>` and `debian/changelog` in lockstep with `CHANGELOG.md`.

**Re-vendor whenever a dependency PIN moves**, not only when a package is added
or removed — `REVENDOR=1 ./obs-submit.sh`. A stale closure is invisible until
the source advances past it: advancing the tarball to 0.1.22 turned both RPM
targets red on `cryptography==50.0.0` missing from a closure vendored months
earlier. A target's default python changing needs one too.
