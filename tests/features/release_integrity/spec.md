# release_integrity — test contract (FIBR-0096)

Enforces the FIBR-0096 spec ([`docs/specs/FIBR-0096.md`](../../../docs/specs/FIBR-0096.md)):
per-release **signed `SHA256SUMS`** manifest + per-platform **CycloneDX SBOM**. No
real release build is needed — INV-1/2/3a run the checksum + signing helpers on
throwaway fixtures; INV-3b/4/5/6/7 are source/doc **scrapes** of the release
scripts, the freeze definitions, and `security-model.md`, mirroring
`tests/features/windows_build/test_windows_build.py`'s scrape pattern.

## INV-1 — Manifest is `sha256sum -c`-valid, incl. the single-platform download

`scripts/gen-checksums.sh <sumsfile> <artA> <artB>` writes lines
`<64-lowercase-hex>␠␠<basename>` (two spaces, basename only, sorted). With both
fixtures present `sha256sum -c SHA256SUMS` **passes** and **fails** after a byte
flip; with only **one** fixture present `sha256sum -c --ignore-missing` **passes**
while plain `sha256sum -c` **fails** — proving the documented `--ignore-missing`
is required, not incidental.

## INV-2 — Merge preserves prior lines

Running the helper for the exe against a manifest that already lists the AppImage
(the AppImage file itself removed, as on the Windows-release host) yields **both**
lines, the AppImage hash byte-identical — merge, not clobber (§ 3.2).

## INV-3 — Manifest signed over its final bytes, publish gated on verification

- **(a) roundtrip (helper-unit):** a throwaway keypair (`gen-signing-key.py`)
  signs a helper-produced `SHA256SUMS` via `sign-release.py` → `SHA256SUMS.sig`
  (raw 64-byte Ed25519); it verifies, and a 1-byte edit fails verification —
  mirroring `test_auto_update.py::test_INV14_signing_scripts_roundtrip`.
- **(b) double gate (source-scrape):** each `release-<platform>.sh` verifies
  against `RELEASE_PUBLIC_KEY_B64` at **both** gates — the *fetched*
  `SHA256SUMS.sig` **before** the `gen-checksums.sh` merge (§ 3.3 step 3, the
  anti-laundering gate) **and** the *re-signed* `SHA256SUMS.sig` **before** the
  `gh release … SHA256SUMS` upload (§ 3.3 step 6). Each gate is bound to its
  `SHA256SUMS.sig` subject **and** its position, so deleting **either** fails.

## INV-4 — Both release scripts publish the new artifacts

`release-linux.sh` uploads `SHA256SUMS` + `.sig` + the `-linux.cdx.json` SBOM (in
both the `gh release create` and `upload --clobber` branches); `release-windows.sh`
re-uploads `SHA256SUMS` + `.sig` + the `-windows.cdx.json` SBOM (§ 3.5).

## INV-5 — SBOM generated in-build, per platform, over the installed closure

Each freeze builds the SBOM from a **`pip freeze` of the runtime deps as
installed** (captured before PyInstaller enters the venv) and runs
`pip-audit -r <frozen> --no-deps --format cyclonedx-json … || true` behind an
**output-existence guard**. The Linux surface is `_build-smoke-in-container.sh`;
the **Windows** surface is **two files** — the `pip freeze` → `runtime-frozen.txt`
write in `build-windows-exe.py` and the `shell: bash` `pip-audit … cyclonedx-json`
step in `windows-build.yml`. Assert the pinned `pip-audit==2.10.0` install, the
`pip-audit -r … --no-deps … cyclonedx-json` invocation, the existence guard, and
the `-linux.cdx.json` / `-windows.cdx.json` output names (§ 3.4).

## INV-6 — Version-stamped off the single source, never hardcoded

The Linux SBOM name is built from the `$VERSION` env passed into the container by
`build-smoke.sh` (`-e "VERSION=${VERSION:-}"`); `release-windows.sh` renames the
unversioned `finbreak-windows.cdx.json` to `finbreak-$VERSION-windows.cdx.json` on
download. Neither name embeds a literal `X.Y.Z` (§ 3.4 / INV-6).

## INV-7 — Signed manifest ⇒ security-model INV recorded

`docs/security-model.md` carries the signed-`SHA256SUMS` trust-boundary note **and**
a numbered **INV-13** definition whose text names the signed manifest (§ 3.6). It
is **not** filed into the § 5/§ 6 curated per-phase enumerations. The doc's
`/cold-eyes` pass is an exit gate (spec § 5 criterion 5), not a pytest assertion.

## Out of scope for these tests

The real release build (opt-in behind `FINBREAK_BUILD_SMOKE=1`), reproducible
builds, and SLSA/in-toto attestation (all § 2 out-of-scope). These tests are
source-scrape + helper-unit only.
