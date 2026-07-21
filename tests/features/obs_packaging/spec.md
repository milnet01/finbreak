# obs_packaging — feature-conformance test contract (FIBR-0155)

Enforces `docs/specs/FIBR-0155.md` (OBS / openSUSE Build Service native
RPM/deb publishing). This is the tiny per-feature test contract; the
multi-file design doc is the cold-eyes-gated spec above. Every invariant
maps to a test in `test_obs_packaging.py`.

The packaging assets live in `packaging/obs/`: an RPM `finbreak.spec`
(openSUSE + Fedora), a `debian/` recipe (Debian + Ubuntu), the reverse-DNS
`io.github.milnet01.finbreak.desktop` + `.metainfo.xml`, the
`/usr/bin/finbreak` shell wrapper (`finbreak.sh`), the OBS `_service`
(source + vendored-wheel fetch + `set_version`), and a maintainer `README.md`.
The payload is a PyInstaller `--onedir` frozen runtime under
`/usr/lib/finbreak/` — the security-critical native stack (SQLCipher, qpdf,
pdfium, Qt) stays **bundled**, never distro-shared (§ 3.2).

App-ID (fixed at this packaging step, `naming.md`): **`io.github.milnet01.finbreak`**.

| INV | Test | Guarantee |
|-----|------|-----------|
| INV-1 | `test_INV1_frozen_payload_minimal_runtime_deps` | neither the `.spec` `Requires:` nor `debian/control` `Depends:` names a bundled-stack package (enumerated blocklist below); the runtime dep set is the host-left libGL/libEGL pair only; the `.spec` has both a `%if 0%{?suse_version}` and a `%if 0%{?fedora}` branch |
| INV-2 | `test_INV2_launcher_and_buildroot_selftest` | both recipes install the `/usr/bin/finbreak` wrapper and run the FIBR-0003 self-test against the **staged buildroot path** (not a bare `finbreak` on `$PATH`) with `QT_QPA_PLATFORM=offscreen` |
| INV-3 | `test_INV3_identity_wayland_and_x11` | `.desktop` basename, `Icon=`, metainfo `<id>`, and `<launchable>` are all the app-ID; `Exec=finbreak`; a non-empty `Name=`; `StartupWMClass=` equals `app.py`'s `setApplicationName` arg **verbatim** (X11); `app.py`'s `setDesktopFileName` arg equals the `.desktop` basename (Wayland) |
| INV-4 | `test_INV4_metainfo_validates` | the metainfo passes `appstreamcli validate` — **skip-if-absent** (validator not in the CI image; manual/pre-submit) |
| INV-5 | `test_INV5_updater_inert_without_appimage` | with `$APPIMAGE` unset on Linux, `detect_installer()` is `None` and `is_update_supported()` is `False` — the distro build's outbound surface is empty |
| INV-6 | `test_INV6_version_single_source` | the `.spec` `Version:` is the service placeholder (no hard-coded semver); the metainfo's newest `<release version>` **and** the top `debian/changelog` stanza both equal `__version__` |
| INV-7 | `test_INV7_offline_build` | the build installs deps with `pip install --no-index --find-links vendor/`; no build-phase `pip install` omits `--no-index`; the `_service` fetches the wheel closure + `set_version` |
| INV-8 | `test_INV8_console_entry_point` | `pyproject.toml` `[project.scripts]` maps `finbreak` → `finbreak.__main__:main`, and that attribute imports + is callable (this spec's INV-8, distinct from `security-model.md`'s INV-8) |

**Bundled-stack blocklist (INV-1, enumerated here so the coverage boundary is
explicit):** `sqlcipher`, `qpdf`, `pdfium`, `pypdfium`, `pyside`, `pikepdf`,
`python3-pyside6`, `python3-pikepdf`, `python3-sqlcipher`, `python3-pdfplumber`.
These travel inside the frozen payload; a distro `Requires:`/`Depends:` on any
of them would contradict the § 3.2 bundling decision.

**Coverage limits (from the spec § 4 / § 5, not gate-covered):** INV-4 is
skip-if-absent; the exact per-distro RPM/deb package names + `%post` macros, the
onedir freeze itself, the `_service` `pip download` cascade, each target's
build-root glibc/`python3`, and the live `xprop WM_CLASS` string are
**manual pre-OBS-submit** checks (spec § 5), not asserted here. These tests
script-scrape structure + two runtime assertions (INV-5, INV-8); **no real OBS
build, no network, no financial data.**
