# Feature test contract — bundling smoke-test (FIBR-0003)

Governs `test_bundling.py`. Enforces `docs/specs/FIBR-0003.md`
INV-1 (the `--self-test` entry point) and INV-6 (the fast guard), plus
INV-2/INV-3 (the build + clean-room launch) via one gated integration test.

## Fast guard (dev venv — runs in the everyday gate, `features` marker)

Exercises the entry-point modes of `python -m finbreak` (INV-1 table):

| Mode | Expected | Exit |
|------|----------|------|
| `--self-test`, all stacks load | `FINBREAK_SELFTEST_OK` (Qt + SQLCipher + qpdf + Argon2) | 0 |
| `--self-test`, a stack fails | `FINBREAK_SELFTEST_FAIL: <stack>` | non-zero |
| no args | routes to the GUI launcher (`finbreak.app.run`) | — |

- **OK** runs the real CLI as a subprocess (`python -m finbreak --self-test`
  with `QT_QPA_PLATFORM=offscreen`), so it needs the runtime deps installed; it
  asserts the **exact** sentinel line and exit 0 — now covering the fourth
  (Argon2) native leg added by FIBR-0004.
- **FAIL** is a unit test of `finbreak._selftest.run_self_test`: it monkeypatches
  the earlier checks to pass and one check to raise, asserting the emitted line
  names that ordered `<stack>` token (`sqlcipher` and `argon2` cases) with a
  non-zero return — independent of whether the heavy native deps are installed.
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
