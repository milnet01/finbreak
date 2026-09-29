# FIBR-0169 — Install an update only if the signed manifest names it for this version and platform

**Status:** spec draft (2026-09-29).
**Kind:** security.
**Source:** ROADMAP FIBR-0169 (indie-review-2026-07-23); re-found as FIBR-0333
(2026-09-04) and by the 2026-09-27 full audit, code lane 12.

**Pairs with:** FIBR-0054 (the updater; its INV-4 per-file signature gate is
kept), FIBR-0096 (the signed `SHA256SUMS` this reads), FIBR-0131 (the Windows
installer and asset picker). **Covers:** FIBR-0333, the same defect.

**Layman:** Someone who can post to our GitHub releases page but does not hold
our signing key could hand the updater an older, genuine finbreak, or the
Windows file renamed for Linux, and it would install. After this, the updater
checks our signed list of release files and installs only the file that list
names for the exact version and system being offered.

---

## 1. Goal

After this ships, the updater installs a download only when three things
agree: the release's signed `SHA256SUMS` verifies against the committed release
key, it carries exactly one line naming `finbreak-<offered version><this
platform's suffix>`, and that line's SHA-256 equals the bytes downloaded. A
genuine but older artifact republished under a newer tag, or one platform's
artifact renamed as another's, is refused.

## 2. Problem

`UpdateService.check_for_update` takes the offered version from the release's
`tag_name`, and `_select_assets` picks the one asset whose name *ends with*
`installer.asset_suffix()` plus that name + `.sig`. `download_and_verify` then
checks the asset's detached Ed25519 signature (FIBR-0054 INV-4). The signature
covers the file's bytes and nothing else, so:

1. **Downgrade.** An attacker with release-write access and no signing key
   (the residual `docs/security-model.md` names) publishes tag `v9.9.9`
   carrying an older, genuinely signed AppImage and its real `.sig`. The tag is
   newer, the signature verifies, and the user is silently moved to a build
   whose fixed defects are back — and it is offered again on every check,
   because the installed version stays below the tag.
2. **Cross-platform swap.** The same attacker renames a signed `.exe` and its
   `.sig` to the `-x86_64.AppImage` names. Both verify, and `os.replace` puts a
   Windows binary at `$APPIMAGE`, so finbreak no longer starts.

The release already publishes what closes both. `scripts/release-linux.sh` and
`scripts/release-windows.sh` produce `SHA256SUMS` (FIBR-0096), one
`<sha256>  <name>` line per artifact, named `finbreak-$VERSION-x86_64.AppImage`
and `finbreak-$VERSION-x86_64.exe` — so the name carries both the version and
the platform — and sign it as `SHA256SUMS.sig` with the same key. Checked
2026-09-29: v0.1.23's `SHA256SUMS.sig` verifies against
`update_key.public_key()`, and v0.1.18, v0.1.19, v0.1.21 and v0.1.22 each carry
both files (`gh release view v<V> --json assets`). The updater never reads them.

## 3. Scope decisions (agreed with the user)

- **Bind through the existing manifest, not a new release format.** Decided by
  the developer (Claude) on 2026-09-29 under the user's standing delegation of
  design calls; the alternatives are in § 8.
- **Keep the per-file `.sig` check.** FIBR-0054 INV-4 is unchanged; this adds a
  gate, it does not replace one.

## 4. Design

### 4.1 Offer (`check_for_update`)

`UpdateInfo` gains `manifest_url` and `manifest_sig_url`. A release is offered
only if its assets carry exactly one `SHA256SUMS` and exactly one
`SHA256SUMS.sig`, each with a download URL, in addition to what
`_select_assets` already requires. Otherwise `check_for_update` returns `None`,
silently, like every other missing-asset case (FIBR-0054 INV-3/INV-11).

### 4.2 Verify (`download_and_verify`)

After the existing download and per-file signature check, and before the
verified bytes are staged for the installer:

1. Download `SHA256SUMS` under a new cap `_MAX_MANIFEST_BYTES = 64 * 1024` and
   `SHA256SUMS.sig` under the existing `_MAX_SIG_BYTES`, through the same
   `update_fetch.download` and inside the same fetch window, so a failure is an
   `UpdateDownloadError` exactly as for the asset.
2. Verify the manifest signature with `update_key.public_key()`. Failure →
   `UpdateVerificationError`.
3. Parse: a line counts only if it is 64 lowercase hex digits, two spaces, and
   a name. Any other line is ignored (§ 4.4).
4. Expected name: `f"finbreak-{info.version}{installer.asset_suffix()}"`.
   Exactly one counting line must carry that name. None, or more than one →
   `UpdateVerificationError`.
5. `hashlib.sha256(data).hexdigest()` of the bytes already read for the
   signature check must equal that line's hash. Otherwise
   `UpdateVerificationError`.

Every refusal removes the temps, as the existing `UpdateVerificationError` path
does, and reaches the shell's security-check message (FIBR-0367 row 38).

### 4.3 Publish order (`scripts/release-windows.sh`)

A Windows release adds its `.exe` to a release whose `SHA256SUMS` lists only
the AppImage. Uploaded together, the `.exe` can be public while the manifest
still lacks its line, and a client checking then is refused with the tamper
message. So `release-windows.sh` uploads `SHA256SUMS` and `SHA256SUMS.sig` in
one `gh release upload` call, and the `.exe`, its `.sig` and the SBOM in a
second call after the first succeeds. Between the two, the manifest names an
`.exe` the release does not carry yet, so § 4.1 offers nothing.
`release-linux.sh` needs no change: on the documented path its manifest and
AppImage are new together, and a release with no `SHA256SUMS` is not offered.

### 4.4 Forward compatibility

Ignoring non-matching lines (§ 4.2 step 3) keeps a later release free to add a
header or comment to `SHA256SUMS` without every installed copy refusing it for
good. Duplicates of the expected name are refused rather than ignored, because
two lines for one file can only mean an edited manifest.

## 5. Invariants

- **INV-1** — A release lacking exactly one `SHA256SUMS` or exactly one
  `SHA256SUMS.sig` asset is not offered.
  *Test:* `tests/features/auto_update/test_auto_update.py`, a release dict
  with the asset and its `.sig` but no `SHA256SUMS` (and one with two) →
  `check_for_update()` is `None`; the same dict with both present is offered.
  The fixture isolates the manifest rule: the asset and `.sig` are valid, so
  `_select_assets` alone would offer it.
  *Breaks when:* the offer checks only the asset and its `.sig`.

- **INV-2** — A manifest whose signature does not verify against
  `update_key.public_key()` is refused with `UpdateVerificationError`, and no
  temp file survives.
  *Test:* `test_auto_update.py`, a throwaway key signs asset and `.sig`
  correctly and the manifest signature is over different bytes →
  `UpdateVerificationError`; the staging directory holds nothing new.
  *Breaks when:* the manifest signature is not checked, or is checked with a
  key other than the committed one.

- **INV-3** — The install proceeds only if the verified manifest has exactly
  one counting line named `finbreak-<info.version><asset_suffix()>` and its hash
  equals SHA-256 of the downloaded bytes; otherwise `UpdateVerificationError`.
  *Test:* `test_auto_update.py`, three legs, each with a correctly signed
  asset, `.sig` and manifest, so only this rule can refuse: (a) the manifest
  names `finbreak-0.1.0-x86_64.AppImage` while `info.version` is `0.1.1` (the
  downgrade); (b) the Linux installer, a genuine manifest listing both
  platforms, and downloaded bytes that are the `.exe`'s, signed as the real
  `.exe` is — so the per-file `.sig` passes and only the hash differs (the
  swap); (c) the expected name on two lines. Each →
  `UpdateVerificationError`. A fourth leg with a matching line installs.
  *Breaks when:* the name check uses a suffix match, the version is taken from
  the manifest instead of `info.version`, or the hash is of other bytes.

- **INV-4** — A line not of the form 64-hex, two spaces, name, is ignored, not
  refused.
  *Test:* `test_auto_update.py`, the INV-3 passing leg with a
  `# finbreak release manifest` first line added → installs.
  *Breaks when:* the parser refuses any line it does not recognise.

- **INV-5** — `SHA256SUMS` is read under `_MAX_MANIFEST_BYTES`; a larger
  response is an `UpdateDownloadError` and nothing is installed.
  *Test:* `test_auto_update.py`, a fetcher recording the `max_bytes` passed
  for the manifest URL → `_MAX_MANIFEST_BYTES`.
  *Breaks when:* the manifest is fetched with the 200 MiB asset cap or none.

- **INV-6** — `release-windows.sh` uploads `SHA256SUMS` and its `.sig` in a
  `gh release upload` call that finishes before the call uploading the `.exe`.
  *Test:* `tests/features/release_integrity/test_release_integrity.py`, reading
  the script's publish commands in order: the first names `SHA256SUMS` and not
  the `.exe`; a later one names the `.exe`. Text-level, because running it
  publishes a release.
  *Breaks when:* the `.exe` and the manifest are uploaded in one call, or the
  `.exe` first.

The trust boundary is the GitHub release: its `tag_name` and every asset are
attacker-controlled under the release-write threat. The only trusted input is
the public key committed in `services/update_key.py`. INV-2 and INV-3 are the
defence; FIBR-0054 INV-4 and INV-10 stay as they are.

## 6. Failure modes

- **Manifest deleted from a release.** Not offered (INV-1): updates stop
  until a release carries one. This is a denial, not a downgrade, and the
  attacker already controls whether any release exists.
- **Manifest re-uploaded with different bytes on an already-published
  release** (a repair re-run building a different binary). For the seconds
  between the two uploads the manifest and the binary disagree, and a client
  checking then gets the security-check message. Accepted: it happens only on a
  deliberate repair, and the next check succeeds.
- **A release published by hand without `SHA256SUMS`.** Not offered.
  FIBR-0096 and the release scripts' read-back gate (FIBR-0275) already make
  it a required asset.
- **Installed copies older than this change** keep checking the per-file
  `.sig` only. They stay exposed until they update once.

## 7. Tests

INV-1, INV-2, INV-3, INV-4 and INV-5 live in
`tests/features/auto_update/test_auto_update.py` and
drive `UpdateService` through the `_FakeFetcher` seam with a throwaway key
monkeypatched into `update_key.public_key` (the existing `_signing_setup`
helper). INV-6 lives in
`tests/features/release_integrity/test_release_integrity.py`. Each is seen to
fail against the pre-change code before the change lands; INV-3's legs (a)
and (b) are the two attacks in § 2.

## 8. Alternatives considered (and rejected)

- **A signed release list with an explicit `version` line** (the Pressless
  design, PRESS-0023 §§ 4.3–4.4, offered as input on FIBR-0169). Explicit, and
  ready for dual-signing a key rotation. Rejected for now: it changes the
  release format and both release scripts, and finbreak's artifact names
  already carry the version and platform inside the signed manifest.
  Revisit with a key rotation.
- **Check the downloaded binary's own embedded version.** Needs a reader for
  a squashfs AppImage and a PE `.exe`, one per platform, before the bytes can
  be trusted. More code in the most exposed place, for what the manifest
  already says.
- **Refuse any offered version the user has installed before.** Needs a
  history the updater does not keep, and does not stop the cross-platform
  swap.

## 9. Out of scope

- A **freeze** attack — withholding every newer release — is not stopped by
  any check on what is offered. Deferred; not yet queued.
- **Key rotation** and dual signatures — deferred; not yet queued. § 8's first
  alternative is where it would start.
- The per-file `.sig`'s other residuals stay in FIBR-0054.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_auto_update.py` (INV-1 test, to be written) |
| INV-2 | `test_auto_update.py` (INV-2 test, to be written) |
| INV-3 | `test_auto_update.py` (INV-3 legs a–d, to be written) |
| INV-4 | `test_auto_update.py` (INV-4 test, to be written) |
| INV-5 | `test_auto_update.py` (INV-5 test, to be written) |
| INV-6 | `test_release_integrity.py` (INV-6 test, to be written) |
| Every release carries `SHA256SUMS` | the release scripts' eight-asset read-back (FIBR-0275); **Partial:** nothing checks a release published by hand |
| A freeze attack is not stopped | **nothing** — out of scope (§ 9) |

## 11. Cross-doc impact

- `docs/security-model.md` — the two passages calling the per-file `.sig` the
  primary gate and the manifest a manual signal: the updater now requires both.
- `docs/specs/FIBR-0096.md` — its Residual paragraph: a deleted manifest now
  also stops updates (INV-1).
- `docs/specs/FIBR-0054.md` — its Out-of-scope "Rollback" entry gains a
  pointer here, since the downgrade case is now covered.
- `CHANGELOG.md` `[Unreleased]` — a Security entry.
- FIBR-0131 INV-2 is unchanged: the picker still matches by suffix; the new
  check is a separate gate.

## 12. Cold-eyes loop log

Rows live in `../reviews/FIBR-0169-signed-manifest-binding-loop-log.md`.
