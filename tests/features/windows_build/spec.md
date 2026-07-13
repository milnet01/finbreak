# windows_build — test contract (FIBR-0015)

Enforces the FIBR-0015 spec (`docs/specs/FIBR-0015.md`). The Windows `.exe` itself
is produced only on a `windows-latest` runner (PyInstaller can't cross-compile), so
these Linux-gate tests cover the parts that *can* be checked on the gate: the
SQLCipher-package swap is vault-safe (INV-1), the Windows freeze reuses the exact
Linux collection flags (INV-3), and the freeze driver is shaped correctly (INV-2,
INV-5, INV-6). The runner-only behaviour (EC2/EC3 — `.exe` builds green,
`--self-test` prints `FINBREAK_SELFTEST_OK` with Python off `PATH`) is proven by
`windows-build.yml`, not here.

## INV-1 — vault portability across the package swap

- **Engine parity:** `sqlcipher3` imports and `PRAGMA cipher_version` reports
  `4.12.0 community` — the same engine `-binary` shipped.
- **Same-package round-trip:** a raw-hex-keyed, `cipher_compatibility=4`, HMAC-on
  vault created under the installed package round-trips a seeded row after a
  close/reopen (the direction CI creates *and* reads, once `-binary` is gone).
- **Binding surface (FIBR-0014 backup path):** `sqlcipher_export` into a
  separately-keyed, HMAC-on target and `PRAGMA rekey` both round-trip.
- **Cross-package upgrade path:** the committed `tests/fixtures/windows_build/`
  vault + `.fbk` (written by `sqlcipher3-binary==0.6.0`, before the swap) open
  under the installed package and read the sentinel — regression-locking the
  upgrade direction CI can no longer reproduce.

## INV-3 — no native-stack drift between OS builds

- The canonical collection-flag list (`scripts/windows_freeze_flags.py`) and the
  flags actually passed to `pyinstaller` in the Linux freeze
  (`scripts/_build-smoke-in-container.sh`) are **equal** as sets:
  `--hidden-import`, `--collect-binaries`, `--collect-all`, and the `--add-data`
  package-relative **target**. The scrape is scoped to the `pyinstaller … \`
  invocation block, matches flags anywhere on a continued line, ignores `#`
  comments, and strips the trailing quote off the `--add-data` target (per D3).

## INV-2 / INV-5 / INV-6 — Windows freeze driver shape

- `scripts/build-windows-exe.py` joins the `--add-data` source→target with
  `os.pathsep` (not a hard-coded `:` — INV-5, `;` on Windows).
- It reads `[project].dependencies` from `pyproject.toml` (manifest-driven —
  INV-6), not a hand-listed set.
- It carries the single-Qt-binding guard (INV-2), mirroring the Linux freeze.
- It builds its PyInstaller flags from `windows_freeze_flags.py` (the single
  canonical list — so the parity guard actually governs the Windows freeze).

## Out of scope for the Linux gate

Producing/launching `finbreak.exe` (a `windows-latest` job), Windows code-signing,
installers, and Windows auto-update (all deferred per the spec).
