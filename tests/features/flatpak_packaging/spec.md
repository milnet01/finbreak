# Feature: Flatpak / Flathub packaging (FIBR-0159)

Test contract for the `flatpak-builder` manifest + pinned pip-source module that
publish finbreak to Flathub. Full design: `docs/specs/FIBR-0159.md`.

These are **script-scrape + monkeypatch** tests — they assert the manifest /
sandbox / pin invariants and the one `src/` change **without a real Flathub
build** (the live `flatpak-builder` build is the manual § 5 exit criterion). No
network, no financial data.

## Invariants under test

- **INV-1 — freedesktop runtime, pinned branch, no distro/KDE Qt.** The manifest
  `runtime` is `org.freedesktop.Platform`, `sdk` is `org.freedesktop.Sdk`, both on
  a pinned `runtime-version` matching `^\d+\.\d+$` (not `master`/`beta`/absent);
  neither `org.kde.` nor `BaseApp` appears anywhere.
- **INV-2 — network-free + filesystem-free sandbox.** Every `finish-args` entry is
  in the enumerated allowlist (`--socket=wayland`, `--socket=fallback-x11`,
  `--share=ipc`, `--device=dri`) — so any `--share=network`, `--filesystem=…`, or
  `--talk-name=…` (incl. `org.kde.KWin`) fails the test.
- **INV-3 — pip sources sha256-pinned, offline, single-ABI.** In
  `python3-deps.yaml`, recursing whatever structure the generator emits: (a) each
  `type: file`/`archive` `sources[]` entry has a 64-hex `sha256` and each
  `pip3 install` build-command carries `--no-index`; (b) no module
  `build-options.build-args` grants `--share=network`; (c) wheels whose **abitag**
  is `cp<minor>` target one distinct CPython minor (key off the abitag field, not a
  substring — an `abi3` wheel's `cp<minor>` pytag must not false-fail).
- **INV-4 — identity + version single-source (new Flatpak-side legs only).**
  Manifest `id` == app-ID; manifest filename is `{app-ID}.yaml`; `command` is the
  bare `finbreak` (NOT the app-ID); the `finbreak` module's git source carries a
  non-empty 40-hex `commit`; no manifest key value is a bare 3-segment semver.
  (The `.desktop`/metainfo/`app.py` == app-ID legs are the reused `obs_packaging`
  `test_INV3` — not re-asserted here, rule 3.)
- **INV-5 — metainfo validates for Flathub.** `appstreamcli validate` on the
  reused metainfo — **skip-if-absent / manual pre-submit** (not in the CI image).
- **INV-6 — self-updater inert under a Flatpak launch.** With `$APPIMAGE` unset on
  Linux, `detect_installer()` is `None` and `is_update_supported()` is `False`
  (reuses the obs_packaging updater-inert predicate).
- **INV-7 — PySide6 pin is the single Qt source.** The `PySide6` wheel pinned in
  `python3-deps.yaml` is `6.11.1`, equal to `pyproject.toml`'s `PySide6==6.11.1`.
- **INV-8 — window-centering disabled under Flatpak (the definite `src/` change).**
  Monkeypatch `_in_flatpak()`→True and `_is_wayland()`→True with
  `XDG_CURRENT_DESKTOP=KDE`; assert `_kde_wayland()` and `_center_supported()` are
  both `False`.
- **INV-9 — `flathub.json` restricts the build to exactly the closure's arches.**
  The pinned wheels are x86_64-only, but Flathub's buildbot builds every arch by
  default — so `packaging/flatpak/flathub.json` must exist and its `only-arches`
  list must equal the concrete arch set the `python3-deps.yaml` wheel filenames
  carry (skip-if-deps-absent, like INV-3/7). Locks the two against drift: widening
  the wheels forces widening `only-arches`, and vice versa.

## Coverage limits (see spec § 4 / § 5)

- `python3-deps.yaml` may not exist until `generate-pip-sources.sh` has been run
  against a resolved closure; scrape tests **skip** when it is absent, so the gate
  stays green before first generation. The live offline `flatpak-builder` run
  (§ 5) is the backstop for pin-vs-pyproject match and the `finbreak`-module
  `--no-index` command (which lives in the main manifest, outside INV-3's file).
- INV-5 is skip-if-absent (`appstreamcli` not in CI).
