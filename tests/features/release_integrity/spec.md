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

## INV-8 — Each release script reads its assets back after publishing and fails loudly on an incomplete set (FIBR-0275)

**Rationale:** cutting v0.1.20 published a GitHub release with **zero** assets and
nothing noticed for ten days — both `README.md` § Install and the in-app updater
resolve to that release page, so both were dead the whole time. Cutting v0.1.21
then hit a worse shape: `release-windows.sh`'s final `gh release upload
--clobber` took an HTTP 503 part-way down its file list, and `--clobber` deletes
each existing asset before replacing it, so the release was left carrying
`SHA256SUMS.sig` but not `SHA256SUMS`, and `.exe.sig` but not the `.exe` — a
signed release whose signed manifest had been deleted, with nothing erroring
loudly (the script had already printed its signing successes). Presence-of-any-
asset is too weak a guard; this invariant is the three-check guard the ROADMAP
bullet (FIBR-0275) specifies, cheapest first.

Each release script publishes assets in **two phases** — `release-linux.sh`
first (5 assets: the AppImage, its `.sig`, `SHA256SUMS`, its `.sig`, and the
linux SBOM), `release-windows.sh` second (completing the release to 8: adding
the `.exe`, its `.sig`, and the windows SBOM, and re-uploading the manifest
pair). **Each script's guard asserts the count correct for ITS OWN phase** — 5
after `release-linux.sh`, 8 after `release-windows.sh` — never 8 after the
Linux phase, which would make that phase permanently red before the Windows
half has ever run.

After its publish step (`gh release create` / `gh release upload`), each script:

1. **Reads the release's assets back** from GitHub (`gh release view <TAG>
   --json assets` or equivalent) — necessarily *after* publishing, since the
   assets cannot exist before the tag; this is not a pre-flight check.
2. **Asserts the asset COUNT** matches its own phase's expected total (5 for
   `release-linux.sh`, 8 for `release-windows.sh`).
3. **Asserts every `.sig` asset's subject is also present** — a `.sig` with no
   matching artifact is exactly the signature of the FIBR-0275 partial-upload
   failure (a `--clobber` that deleted an artifact but not its signature, or
   vice versa), and a bare count would not catch it: 5 signatures-only assets
   would still satisfy check 2 while missing every real artifact.
4. **Asserts each asset name matches what the in-app updater greps for** —
   `WindowsInstaller.asset_suffix()` / `AppImageInstaller.asset_suffix()`
   (`src/finbreak/services/update_installer.py`): `-x86_64.AppImage` and
   `-x86_64.exe`. `.claude/bump.json` already warns in prose that a
   mis-named `.exe` is invisible to the updater with "no automated guard" —
   this closes that gap mechanically.
5. **Fails loudly on any of the above** — the failure must actually abort the
   script (propagate a non-zero exit under `set -euo pipefail`), not be
   swallowed by a `|| true` or an unchecked pipe. A check that runs and is
   then discarded is indistinguishable from no check at all.

**Test surface (source-scrape, mirroring INV-3b/INV-4):** these tests do not
cut a real release. They scrape `scripts/release-linux.sh` and
`scripts/release-windows.sh` for a `gh release view … --json assets` call
positioned strictly *after* the script's publish command, then scrape the text
from that call to end-of-file for: the phase-correct count, a per-`.sig`
subject-presence construct, the platform-correct `asset_suffix()` literal(s),
and the absence of a swallowed-failure idiom (`|| true`) alongside the presence
of an actual abort (`exit <nonzero>`). A source scrape cannot execute the
guard against a real (or faked) GitHub API response, so it cannot prove the
count comparison or the `.sig`-subject check are *semantically* correct against
live data — only that the textual shape of all three checks, and of a
non-swallowed failure path, is present in the right position. That is the same
limit INV-3b/INV-4 already accept for the double-verify gate and the asset
list.

## Out of scope for these tests

The real release build (opt-in behind `FINBREAK_BUILD_SMOKE=1`), reproducible
builds, and SLSA/in-toto attestation (all § 2 out-of-scope). These tests are
source-scrape + helper-unit only.
