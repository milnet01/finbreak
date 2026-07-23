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
| `debian/` | deb recipe (Debian + Ubuntu) |
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

| Family | Target | OBS path | Status (2026-07-23) |
|--------|--------|----------|---------------------|
| openSUSE | Tumbleweed | `openSUSE:Factory / snapshot` | ✅ built + published |
| Fedora | 44 | `Fedora:44 / standard` | ✅ built + published |
| Debian | 13 (trixie) | `Debian:13 / standard` | ⚠️ excluded — needs a `.dsc` + the vendor bundle as a deb component tarball |
| Ubuntu | 24.04 LTS | `Ubuntu:24.04 / universe` | ⚠️ excluded — same deb work as Debian 13 |
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

## Still open (§5 follow-ups)

- [ ] **Debian + Ubuntu** — un-exclude the deb builds: author a `.dsc` (the
      debtransform trigger) and deliver `vendor.tar.gz` into the deb build tree
      (a `3.0 (quilt)` component orig tarball → unpacks to `vendor/`), since deb
      builds have no RPM-style `Source1`.
- [ ] **Leap 15.6** — add the target + a `%if 0%{?sle_version}` branch pinning
      `python313` (Leap's default `python3` is 3.6).
- [ ] **Live `xprop WM_CLASS`** on the running app equals the `.desktop`'s
      `StartupWMClass=finbreak` (Qt-version quirk guard, § 3.3).
- [ ] **Real screenshots** uploaded to the homepage so the metainfo
      `<screenshot>` URLs resolve in the software centres.

## Ongoing releases

Each new finbreak version is a new package revision in the OBS repo (pulled by
`zypper up` / `apt upgrade`). The `/bump` recipe keeps the metainfo `<release>`
and `debian/changelog` in lockstep with `CHANGELOG.md`. Re-run
`vendor-wheels.sh` **only** when the dependency closure or a target's default
python changes; otherwise repeat `osc service manualrun` → `osc commit`.
