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
| `io.github.milnet01.finbreak.desktop` | desktop entry (menu + launcher association) |
| `io.github.milnet01.finbreak.metainfo.xml` | AppStream component (software-centre listing) |
| `finbreak.sh` | the `/usr/bin/finbreak` launcher wrapper |
| `_service` | OBS source tarball + version injection (+ the documented wheel-vendoring command) |

## Target matrix

Four confirmed-buildable targets; openSUSE Leap 15.6 is a likely fifth, gated on
one glibc check (below). The **glibc ≥ 2.34** floor — not the Python version — is
the gating constraint (a build root below 2.34 cannot install the PySide6 wheel).

| Family | Target | Notes |
|--------|--------|-------|
| openSUSE | Tumbleweed | primary listing; OBS home turf |
| Fedora | latest stable | second RPM family |
| Debian | 13 (trixie) | matches the CI clean-room image |
| Ubuntu | 24.04 LTS | largest desktop base; default python3 = 3.12 |
| openSUSE | **Leap 15.6** | **contingent** — see the glibc check |

## First-cut submit (manual `osc` flow)

Version flows **one way**: the git tag `v{VERSION}` drives everything via the
`_service` `set_version` — never hand-edit a `Version:` (obs_packaging INV-6).

1. **Tag + release** the version on GitHub (the normal `/bump` + release flow),
   so `v{VERSION}` exists.
2. **Vendor the wheels** on a Linux x86_64 host with **glibc ≥ 2.34** (§ 3.6) —
   run the `pip download` block documented in `_service` (both `cp312` + `cp313`
   ABIs, **no** single `--platform` tag, includes `pyinstaller==6.21.0` and its
   recursive closure), producing `vendor.tar.gz`.
3. **Check it out + populate sources:**
   ```
   osc checkout home:milnet01 finbreak && cd home:milnet01/finbreak
   cp /path/to/packaging/obs/* .          # spec, debian/, desktop, metainfo, _service
   cp /path/to/vendor.tar.gz .
   osc service manualrun                  # obs_scm + tar + set_version
   osc add finbreak-*.tar.gz vendor.tar.gz *.spec *.desktop *.metainfo.xml debian _service
   osc commit -m "finbreak {VERSION}"
   ```
4. **Watch the build** (`osc results`) for each enabled target/arch.

## Pre-submit checklist (things CI cannot prove — FIBR-0155 § 5)

Run these **once** before locking the recipes in (all are recalled distro facts,
global rule 13):

- [ ] **Leap 15.6 go/no-go:** `zypper info glibc` in an `openSUSE:Leap:15.6` build
      root. **≥ 2.34** → add it as a fifth target *and* add a third,
      `%if 0%{?sle_version}` branch to `finbreak.spec` overriding the unversioned
      `python3` with `python313` (Leap's default `python3` is the legacy 3.6).
      **< 2.34** → defer Leap 15.6 (Leap users fall back to the AppImage).
- [ ] **Per-distro package names** in `finbreak.spec` `%if` branches + `debian/control`
      (`Mesa-libGL1` vs `mesa-libGL`, `libglib-2_0-0` vs `glib2`, …) confirmed
      against each target's real package index.
- [ ] **`%post`/`%postun` macro spellings** (`%icon_theme_cache_post`,
      `%desktop_database_post`) confirmed for openSUSE + Fedora.
- [ ] **The onedir freeze runs** — a local `pyinstaller --onedir` smoke of the app
      once, so its first real exercise isn't inside an OBS build root.
- [ ] **The wheel vendoring** resolves offline: `pip install --no-index
      --find-links vendor/ -r deps.txt pyinstaller==6.21.0` in a clean venv for
      **both** ABIs, confirming the recursive PyInstaller closure landed.
- [ ] **Each target's `python3 --version` + `ldd --version`** — default `python3`
      minor in `{3.12, 3.13}` and glibc ≥ 2.34.
- [ ] **`appstreamcli validate io.github.milnet01.finbreak.metainfo.xml`** passes
      (INV-4 is skip-if-absent in CI).
- [ ] **Live `xprop WM_CLASS`** on the built app equals the `.desktop`'s
      `StartupWMClass=finbreak` (guards a Qt-version quirk, § 3.3).
- [ ] **Upload real screenshots** to the homepage and confirm the metainfo
      `<screenshot>` URLs resolve.

## Ongoing releases

Each new finbreak version is a new package revision in the OBS repo (pulled by
`zypper up` / `apt upgrade`). The `/bump` recipe keeps the metainfo `<release>`
and `debian/changelog` in lockstep with `CHANGELOG.md`; then repeat the
tag → vendor → `osc service manualrun` → `osc commit` flow above.
