# Feature test contract — bundling smoke-test (FIBR-0003)

Governs `test_bundling.py`. Enforces `docs/specs/FIBR-0003.md`
INV-1 (the `--self-test` entry point) and INV-6 (the fast guard), plus
INV-2/INV-3 (the build + clean-room launch) via one gated integration test.

## Fast guard (dev venv — runs in the everyday gate, `features` marker)

Exercises the entry-point modes of `python -m finbreak` (INV-1 table):

| Mode | Expected | Exit |
|------|----------|------|
| `--self-test`, all stacks load | `FINBREAK_SELFTEST_OK` (Qt + SQLCipher + qpdf + Argon2 + ofxparse) | 0 |
| `--self-test`, a stack fails | `FINBREAK_SELFTEST_FAIL: <stack>` | non-zero |
| no args | routes to the GUI launcher (`finbreak.app.run`) | — |

- **OK** runs the real CLI as a subprocess (`python -m finbreak --self-test`
  with `QT_QPA_PLATFORM=offscreen`), so it needs the runtime deps installed; it
  asserts the **exact** sentinel line and exit 0 — now covering the fifth
  (ofxparse) native leg added by FIBR-0008, after the fourth (Argon2, FIBR-0004).
- **FAIL** is a unit test of `finbreak._selftest.run_self_test`: it monkeypatches
  the earlier checks to pass and one check to raise, asserting the emitted line
  names that ordered `<stack>` token (`sqlcipher`, `argon2`, and `ofxparse`
  cases) with a non-zero return — independent of whether the heavy native deps
  are installed.
- **no args** — the FIBR-0003 `FINBREAK_NOT_BUILT` placeholder is retired
  (superseded by FIBR-0004). `main([])` now routes to the GUI: the test asserts
  it calls `finbreak.app.run` (in-process, no event loop). The GUI screens
  themselves are covered by the `qtbot` tests in `tests/features/vault/`.

## Build + clean-room (integration — `integration` marker, opt-in)

`test_INV2_INV3_build_smoke_clean_room` runs `scripts/build-smoke.sh` and asserts exit 0
(both artifacts print `FINBREAK_SELFTEST_OK` in the Python-free container,
INV-2/INV-3). It **skips** unless ALL hold, so the everyday gate never blocks
on a multi-minute build (INV-5/INV-6):

- `FINBREAK_BUILD_SMOKE=1` is set (the same opt-in switch as the build stage);
- `scripts/build-smoke.sh` exists;
- a container runtime (`podman` or `docker`) is on `PATH`.

## Build-tool pin lockstep (dev venv — `features` marker)

**INV-7** — every hard-coded `<tool>==<version>` in a **tracked** file matches
the pin in `pyproject.toml`'s PEP 735 dependency group, for each of:

| Tool | Authoritative group | Inline call-sites |
|------|--------------------|-------------------|
| `pyinstaller` | `build` | `scripts/_build-smoke-in-container.sh` (×2), `scripts/build-windows-exe.py`, `packaging/obs/vendor-wheels.sh`, `packaging/obs/debian/rules`, `packaging/obs/finbreak.spec` |
| `pip-audit` | `dev` | `.github/workflows/windows-build.yml` (the SBOM step) |

No build path installs either tool via `--group build` / `--group dev` — each
names the version inline — so a bump to the pyproject pin would otherwise leave
all of them silently behind (the drift class `docs/specs/FIBR-0155.md` § 805-808
flagged). The test scans `git ls-files`, so a **new** call-site is covered
automatically; a per-tool `min_sites` floor stops the scan passing vacuously if
a build path drops or moves its pin. Adding a third tool is one row in
`_LOCKSTEP_PINS`.

## The libxkbcommon pair stays on the host (dev venv — `features` marker)

**FIBR-0208** — two guards, one per side of the same fix. They are cheap static
reads of the build scripts, because the defect they lock is a *package list*,
not behaviour the suite can exercise: the real proof is the clean-room launch
above, which is opt-in and does not run in the everyday gate.

Qt's xcb platform plugin links **both** `libxkbcommon.so.0` and
`libxkbcommon-x11.so.0`. They are one upstream project, released together, and
only guaranteed to work as a matched pair. Nothing collects the `-x11` half —
PyInstaller's own build log reports it unresolved — so collecting the base half
shipped one half of a pair, and every X11 launch linked the host's current
`-x11` against the build container's older `libxkbcommon`. That combination
segfaults inside `libxkbcommon`, measured on 0.1.19 and again on 0.1.23.

| Guard | Reads | Asserts |
|-------|-------|---------|
| `test_FIBR0208_the_freeze_container_does_not_provide_libxkbcommon` | `scripts/_build-smoke-in-container.sh` | the library is not in the `apt-get install` list — PyInstaller collects what it can see, so absence from the container is the control |
| `test_FIBR0208_the_clean_room_supplies_libxkbcommon_from_the_host` | `scripts/build-smoke.sh` | the clean-room baseline installs it — without it the INV-3 self-test cannot load QtGui, and the proof would fail for a reason unrelated to the bundle |

Both read the `apt-get install` command and its continuations rather than the
whole file, because the freeze script **names** the package in a comment in
order to say it must not be installed — a whole-file `in` test would read that
comment as an install and pass while the fix was reverted. Each guard asserts a
precondition first (that it is looking at the right command) so a mis-parse
cannot make it vacuous. Both were proved by mutation: re-adding the package to
the freeze list reds the first, removing it from the baseline reds the second.

`scripts/ci-setup.sh` is a **different** list and must keep the library — that
is the gate's own environment, where `--self-test` genuinely loads Qt from a
venv. Neither guard reads it.
