#!/usr/bin/env bash
# Build + sign + attach the WINDOWS .exe to the release for the CURRENT source
# version (the FIBR-0016 Windows slice).
#
# Run this AFTER scripts/release-linux.sh, which creates the vX.Y.Z tag + GitHub
# release this builds against. PyInstaller can't cross-compile, so the .exe is
# frozen on a windows-latest runner via .github/workflows/windows-build.yml.
#
# What it does:
#   1. Read VERSION; require the vX.Y.Z release to already exist.
#   2. Dispatch windows-build.yml on the vX.Y.Z tag and wait for it to finish.
#   3. Download the finbreak-windows-exe artifact and rename it to
#      finbreak-<V>-x86_64.exe (the exact name WindowsInstaller.asset_suffix()
#      looks for — the in-app updater won't find any other name).
#   4. Ed25519-sign it with the release key, verify the .sig against the committed
#      public key, and attach the .exe + .exe.sig to the vX.Y.Z release.
#
# Prerequisites: the project venv ACTIVE (cryptography), a signing key at
# release/finbreak-signing.key (or $FINBREAK_SIGNING_KEY), and an authenticated
# `gh` with workflow + repo scope.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^__version__ = "\([0-9.]*\)"/\1/p' src/finbreak/__init__.py)"
[ -n "$VERSION" ] || { echo "release-windows: could not read __version__ from src/finbreak/__init__.py" >&2; exit 1; }
TAG="v$VERSION"
DIST="$ROOT/dist"
EXE="finbreak-$VERSION-x86_64.exe"
WORKFLOW="windows-build.yml"
echo "== release-windows: version $VERSION (tag $TAG) =="

# --- preconditions --------------------------------------------------------
command -v gh >/dev/null 2>&1 || { echo "release-windows: gh CLI not on PATH" >&2; exit 1; }
python3 -c "import cryptography" 2>/dev/null || {
    echo "release-windows: activate the venv first (cryptography is needed to sign/verify)" >&2; exit 1; }
[ -f release/finbreak-signing.key ] || [ -n "${FINBREAK_SIGNING_KEY:-}" ] || {
    echo "release-windows: no signing key (release/finbreak-signing.key or \$FINBREAK_SIGNING_KEY)" >&2; exit 1; }
gh release view "$TAG" >/dev/null 2>&1 || {
    echo "release-windows: release $TAG not found — run scripts/release-linux.sh first" >&2; exit 1; }

# --- 1) dispatch the Windows build on the tag -----------------------------
# Record the newest existing run id so we can detect the one we trigger (the tag
# ref may not appear as headBranch, so match on "a newer run than before").
#
# NOT `|| echo ""`. That suppressed set -e, and an empty PREV_RUN makes the
# `!=` below true against the newest PRE-EXISTING run -- i.e. the PREVIOUS
# release's build, which is already complete and successful. Every downstream
# step then does exactly what it is meant to do to the wrong artifact: watch it,
# download it, rename it to THIS version, sign it with the real key and publish
# it. A `gh` 503 here is routine during a release (four endpoints returned one
# while cutting 0.1.21), so the failure this guards is not hypothetical.
PREV_RUN="$(gh run list --workflow="$WORKFLOW" --limit 1 --json databaseId -q '.[0].databaseId')"
echo "== release-windows: dispatching $WORKFLOW on $TAG =="
gh workflow run "$WORKFLOW" --ref "$TAG"

echo "== release-windows: waiting for the run to register =="
TAG_SHA="$(git rev-parse "$TAG^{commit}")"
RUN_ID=""
for _ in $(seq 1 30); do
    RUN_ID="$(gh run list --workflow="$WORKFLOW" --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || echo "")"
    [ -n "$RUN_ID" ] && [ "$RUN_ID" != "$PREV_RUN" ] && break
    RUN_ID=""
    sleep 5
done
[ -n "$RUN_ID" ] || { echo "release-windows: could not find the dispatched run — check 'gh run list --workflow=$WORKFLOW'" >&2; exit 1; }

# Bind the run to the tag before trusting anything it produced. "Newer than
# before" is an ordering heuristic; this is the identity check. Without it
# NOTHING in this script ever compares the downloaded .exe to $TAG -- check 3
# greps the FILENAME, which we ourselves chose. A validly-signed older binary
# published as the new version is invisible to every guard and auto-installs.
RUN_SHA="$(gh run view "$RUN_ID" --json headSha -q .headSha)"
[ "$RUN_SHA" = "$TAG_SHA" ] || {
    echo "release-windows: run $RUN_ID was built from $RUN_SHA, not $TAG ($TAG_SHA) —" >&2
    echo "  refusing to publish its artifact. Re-run once the dispatched build registers." >&2
    exit 1; }

echo "== release-windows: watching run $RUN_ID (the Windows freeze + clean-room takes several minutes) =="
gh run watch "$RUN_ID" --exit-status

# --- 2) download + rename the artifact ------------------------------------
echo "== release-windows: downloading the finbreak-windows-exe artifact =="
mkdir -p "$DIST"
rm -f "$DIST/finbreak.exe" "$DIST/$EXE" "$DIST/$EXE.sig" \
      "$DIST/finbreak-windows.cdx.json" "$DIST/finbreak-$VERSION-windows.cdx.json"
gh run download "$RUN_ID" -n finbreak-windows-exe -D "$DIST"
[ -f "$DIST/finbreak.exe" ] || { echo "release-windows: finbreak.exe not present in the artifact" >&2; exit 1; }
mv "$DIST/finbreak.exe" "$DIST/$EXE"

# Version-stamp the windows SBOM on arrival, exactly as the .exe is stamped above
# (INV-6). windows-build.yml writes an UNVERSIONED finbreak-windows.cdx.json
# ($VERSION isn't in scope in the workflow); release-windows.sh derives $VERSION.
[ -f "$DIST/finbreak-windows.cdx.json" ] || { echo "release-windows: finbreak-windows.cdx.json not present in the artifact" >&2; exit 1; }
mv "$DIST/finbreak-windows.cdx.json" "$DIST/finbreak-$VERSION-windows.cdx.json"

# --- 3) sign + verify -----------------------------------------------------
echo "== release-windows: signing $EXE with the release key =="
python3 scripts/sign-release.py "$DIST/$EXE"
[ -f "$DIST/$EXE.sig" ] || { echo "release-windows: $EXE.sig was not produced — signing failed?" >&2; exit 1; }

echo "== release-windows: verifying the signature against RELEASE_PUBLIC_KEY_B64 =="
PYTHONPATH="$ROOT/src" python3 - "$DIST/$EXE" "$DIST/$EXE.sig" <<'PY'
import base64, sys
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from finbreak.services.update_key import RELEASE_PUBLIC_KEY_B64

pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(RELEASE_PUBLIC_KEY_B64))
artifact, sig = sys.argv[1], sys.argv[2]
try:
    with open(artifact, "rb") as a, open(sig, "rb") as s:
        pub.verify(s.read(), a.read())
except InvalidSignature:
    sys.exit("release-windows: SIGNATURE VERIFICATION FAILED — refusing to attach")
print("release-windows: signature verified against the committed public key")
PY

# --- 4) SHA256SUMS manifest: clean → fetch → verify → merge → sign → verify ---
# (§ 3.3, phase 2 — adds the exe line to the manifest release-linux.sh published).
# Same shape as release-linux.sh so re-running either script in any order never
# regresses the manifest to a single platform.
echo "== release-windows: building the signed SHA256SUMS manifest =="

# Step 1 — start clean: a stale SHA256SUMS from a PREVIOUS version must not leak
# phantom basenames into this release's merge (INV-4).
rm -f "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig"

# Step 2 — fetch the current manifest, guided by the release and FAILING CLOSED
# on ambiguity. release-not-found → start fresh; ANY other gh failure must abort,
# never be read as "no prior manifest" — else the --clobber upload below would
# REGRESS the (AppImage-carrying) manifest to just this platform.
VIEW_ERR="$(mktemp)"
VIEW_ASSETS="$(mktemp)"
trap 'rm -f "$VIEW_ERR" "$VIEW_ASSETS"' EXIT
if gh release view "$TAG" --json assets --jq '.assets[].name' >"$VIEW_ASSETS" 2>"$VIEW_ERR"; then
    if grep -qx SHA256SUMS "$VIEW_ASSETS"; then
        echo "== release-windows: fetching the published SHA256SUMS to merge into =="
        gh release download "$TAG" -p SHA256SUMS -p SHA256SUMS.sig -D "$DIST" || {
            echo "release-windows: could not download the published SHA256SUMS — aborting (won't regress the manifest to one platform)" >&2; exit 1; }
        # Step 3 — VERIFY the fetched manifest against the committed key BEFORE
        # trusting its carried (AppImage) line: refuse on a missing .sig or a
        # signature mismatch — present-but-unverifiable is tampering, not a fresh
        # start. Without this the re-sign in step 5 would launder a tampered
        # carried line into a freshly-valid signature.
        [ -f "$DIST/SHA256SUMS.sig" ] || { echo "release-windows: published SHA256SUMS has no .sig — refusing to merge an unverifiable manifest" >&2; exit 1; }
        echo "== release-windows: verifying the fetched SHA256SUMS against RELEASE_PUBLIC_KEY_B64 =="
        PYTHONPATH="$ROOT/src" python3 - "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig" <<'PY'
import base64, sys
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from finbreak.services.update_key import RELEASE_PUBLIC_KEY_B64

pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(RELEASE_PUBLIC_KEY_B64))
manifest, sig = sys.argv[1], sys.argv[2]
try:
    with open(manifest, "rb") as m, open(sig, "rb") as s:
        pub.verify(s.read(), m.read())
except InvalidSignature:
    sys.exit("release-windows: FETCHED SHA256SUMS FAILED VERIFICATION — refusing to merge (won't launder a tampered manifest)")
print("release-windows: fetched SHA256SUMS verified against the committed public key")
PY
    fi
elif grep -qi "release not found" "$VIEW_ERR"; then
    echo "== release-windows: no existing release $TAG — starting a fresh SHA256SUMS =="
else
    echo "release-windows: 'gh release view' failed (not a release-not-found) — aborting rather than risk regressing SHA256SUMS:" >&2
    cat "$VIEW_ERR" >&2
    exit 1
fi

# Step 4 — merge this phase's line (the exe): the helper keeps the fetched
# AppImage line and adds/replaces only the exe basename (§ 3.2).
echo "== release-windows: adding the exe to SHA256SUMS =="
scripts/gen-checksums.sh "$DIST/SHA256SUMS" "$DIST/$EXE"

# Step 5 — sign the FINAL merged bytes (never reuse a fetched sig; INV-3).
echo "== release-windows: signing SHA256SUMS with the release key =="
python3 scripts/sign-release.py "$DIST/SHA256SUMS"
[ -f "$DIST/SHA256SUMS.sig" ] || { echo "release-windows: SHA256SUMS.sig was not produced — signing failed?" >&2; exit 1; }

# Step 6 — HARD GATE: verify the re-signed SHA256SUMS.sig against the committed
# key before publishing, exactly as the exe is gated above.
echo "== release-windows: verifying SHA256SUMS.sig against RELEASE_PUBLIC_KEY_B64 =="
PYTHONPATH="$ROOT/src" python3 - "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig" <<'PY'
import base64, sys
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from finbreak.services.update_key import RELEASE_PUBLIC_KEY_B64

pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(RELEASE_PUBLIC_KEY_B64))
manifest, sig = sys.argv[1], sys.argv[2]
try:
    with open(manifest, "rb") as m, open(sig, "rb") as s:
        pub.verify(s.read(), m.read())
except InvalidSignature:
    sys.exit("release-windows: SHA256SUMS SIGNATURE VERIFICATION FAILED — refusing to publish")
print("release-windows: SHA256SUMS signature verified against the committed public key")
PY

# --- 7) attach to the release ---------------------------------------------
# The merged SHA256SUMS + its re-signed sig + the version-stamped windows SBOM
# ride the SAME --clobber upload as the exe (§ 3.5).
echo "== release-windows: attaching $EXE + .exe.sig + SHA256SUMS + windows SBOM to $TAG =="
# Captured, not left to `set -e`. --clobber deletes each existing asset before
# replacing it, so a failure part-way down the list leaves the release SHORT —
# the state the read-back gate below exists to report, and the one this very
# upload produced on 0.1.21 (a 503 left SHA256SUMS.sig without SHA256SUMS).
# Dying here skipped the gate on its own motivating failure (FIBR-0327).
UPLOAD_RC=0
gh release upload "$TAG" "$DIST/$EXE" "$DIST/$EXE.sig" \
    "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig" \
    "$DIST/finbreak-$VERSION-windows.cdx.json" --clobber || UPLOAD_RC=$?
if [ "$UPLOAD_RC" -ne 0 ]; then
    echo "release-windows: the upload exited $UPLOAD_RC — running the read-back gate anyway to report what is actually on the release" >&2
fi

# --- 8) HARD GATE: read the published asset list back (FIBR-0275, INV-8) ---
# This is the phase that COMPLETES the release, so the expected total is EIGHT:
# the AppImage + .sig and the linux SBOM from release-linux.sh, plus the .exe +
# .sig, the windows SBOM, and the merged SHA256SUMS + .sig re-uploaded above.
#
# The upload this gate follows is the one that failed on 0.1.21: a 503
# part-way down the final --clobber upload, which DELETES each asset before
# replacing it. It left SHA256SUMS.sig without SHA256SUMS and .exe.sig without
# the .exe, and nothing errored loudly — the script had already printed its
# signing successes, and the upload was its last line.
#
# (Do not spell the publish command out in these comments. INV-4 and INV-8
# both scrape this file for that literal, and a mention in a comment reads to
# them as a real publish — which is how this guard first broke both.)
echo "== release-windows: reading the published asset list back from $TAG =="

ASSET_NAMES=""
READBACK_OK=0
for attempt in 1 2 3; do
    if ASSET_NAMES="$(gh release view "$TAG" --json assets -q '.assets[].name' | sort)"; then
        READBACK_OK=1
        break
    fi
    echo "release-windows: asset read-back attempt $attempt failed — retrying in 5s" >&2
    sleep 5
done

# A read-back that never completed is NOT the same finding as an incomplete
# release. Distinguishing them keeps the gate from crying wolf on the
# transient 503s this API hands out.
if [ "$READBACK_OK" -ne 1 ]; then
    echo "release-windows: could not read $TAG's assets back after 3 attempts. The release may well be complete — check with 'gh release view $TAG --json assets' before assuming otherwise." >&2
    exit 1
fi

if [ -n "$ASSET_NAMES" ]; then
    mapfile -t PUBLISHED <<< "$ASSET_NAMES"
else
    PUBLISHED=()
fi
ASSET_COUNT=${#PUBLISHED[@]}

# Check 1 — the count, for the COMPLETE release.
if [ "$ASSET_COUNT" -ne 8 ]; then
    {
        printf 'release-windows: PUBLISH INCOMPLETE — %s carries %d asset(s), expected 8.\n' \
            "$TAG" "$ASSET_COUNT"
        printf 'Published now: %s\n' "${ASSET_NAMES:-<none>}"
    } >&2
    exit 1
fi

# Check 2 — every .sig has the artifact it signs. A bare count would have
# accepted the 0.1.21 state outright; this is the check that names it.
for name in "${PUBLISHED[@]}"; do
    case "$name" in
    *.sig)
        subject="${name%.sig}"
        if ! printf '%s\n' "${PUBLISHED[@]}" | grep -Fxq -- "$subject"; then
            echo "release-windows: PUBLISH INCOMPLETE — $name is published but $subject, the artifact it signs, is not" >&2
            exit 1
        fi
        ;;
    esac
done

# Check 3 — both platform artifacts carry the exact names the in-app updater
# greps for: AppImageInstaller.asset_suffix() and WindowsInstaller
# .asset_suffix() (src/finbreak/services/update_installer.py). A correctly
# built, correctly signed artifact under any other name is invisible to every
# installed copy's updater — the trap .claude/bump.json warns about in prose
# with "no automated guard". This is that guard.
if ! printf '%s\n' "${PUBLISHED[@]}" | grep -q -- '-x86_64.AppImage$'; then
    echo "release-windows: PUBLISH INCOMPLETE — no asset matches the updater's AppImage suffix -x86_64.AppImage" >&2
    exit 1
fi
if ! printf '%s\n' "${PUBLISHED[@]}" | grep -q -- '-x86_64.exe$'; then
    echo "release-windows: PUBLISH INCOMPLETE — no asset matches the updater's Windows suffix -x86_64.exe" >&2
    exit 1
fi

echo "== release-windows: asset read-back OK — $ASSET_COUNT/8 assets, every .sig has its subject =="

# The gate passing means the NAMES are all there; it cannot tell whether a failed
# upload left stale bytes behind an existing name.
if [ "$UPLOAD_RC" -ne 0 ]; then
    echo "release-windows: PUBLISH SUSPECT — every expected asset name is present, but the upload exited $UPLOAD_RC. Verify the asset bytes before announcing $TAG." >&2
    exit 1
fi

echo "== release-windows: DONE — $TAG now carries the signed Windows .exe (+ .exe.sig that activates the updater) =="
