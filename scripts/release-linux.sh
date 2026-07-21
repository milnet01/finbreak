#!/usr/bin/env bash
# Cut + publish the LINUX release: build the signed AppImage and publish the
# GitHub release for the CURRENT source version (the FIBR-0016 Linux slice).
#
# Run this FIRST. It creates the vX.Y.Z tag + GitHub release; the companion
# scripts/release-windows.sh then builds the Windows .exe against that tag and
# attaches it to the SAME release.
#
# What it does:
#   1. Read VERSION from src/finbreak/__init__.py (the single source of truth),
#      check version lockstep across all version-bearing files, and require a
#      clean, pushed working tree.
#   2. scripts/build-release-appimage.sh → freeze + Python-free clean-room proof +
#      Ed25519-sign → dist/finbreak-<V>-x86_64.AppImage (+ .sig).
#   3. HARD GATE: verify the .sig against the committed RELEASE_PUBLIC_KEY_B64 (the
#      exact key the in-app updater checks) — never publish a release the updater
#      would reject.
#   4. Build the signed SHA256SUMS manifest + linux SBOM, then create the vX.Y.Z
#      GitHub release (non-prerelease, --latest) with the AppImage + .sig + those
#      supply-chain artifacts, and notes lifted from the CHANGELOG [X.Y.Z] section.
#
# Prerequisites: the project venv ACTIVE (`. .venv/bin/activate` — cryptography is
# needed to sign + verify), podman/docker on PATH (the build container), a signing
# key at release/finbreak-signing.key (or $FINBREAK_SIGNING_KEY), and an
# authenticated `gh`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^__version__ = "\([0-9.]*\)"/\1/p' src/finbreak/__init__.py)"
[ -n "$VERSION" ] || { echo "release-linux: could not read __version__ from src/finbreak/__init__.py" >&2; exit 1; }
TAG="v$VERSION"
DIST="$ROOT/dist"
APPIMAGE="finbreak-$VERSION-x86_64.AppImage"
echo "== release-linux: version $VERSION (tag $TAG) =="

# --- preconditions --------------------------------------------------------
command -v gh >/dev/null 2>&1 || { echo "release-linux: gh CLI not on PATH" >&2; exit 1; }
python3 -c "import cryptography" 2>/dev/null || {
    echo "release-linux: activate the venv first (. .venv/bin/activate) — cryptography is needed to sign/verify" >&2; exit 1; }
[ -f release/finbreak-signing.key ] || [ -n "${FINBREAK_SIGNING_KEY:-}" ] || {
    echo "release-linux: no signing key (release/finbreak-signing.key or \$FINBREAK_SIGNING_KEY)" >&2; exit 1; }

# Version lockstep (mirrors .claude/bump.json's post_check) — refuse a half-bumped tree.
if ! { grep -q "^version = \"$VERSION\"$" pyproject.toml \
    && grep -q "__version__ == \"$VERSION\"" tests/test_smoke.py \
    && grep -q "^## \[$VERSION\] - " CHANGELOG.md \
    && grep -qF "Current version: **$VERSION**" README.md; }; then
    echo "release-linux: VERSION DRIFT — bump every version-bearing file to $VERSION first (see .claude/bump.json)" >&2
    exit 1
fi

[ -z "$(git status --porcelain)" ] || { echo "release-linux: working tree is dirty — commit + push the bump first" >&2; exit 1; }

# --- 1) build + clean-room + sign the AppImage ----------------------------
echo "== release-linux: building + clean-rooming + signing the AppImage (a few minutes) =="
scripts/build-release-appimage.sh

[ -f "$DIST/$APPIMAGE" ]     || { echo "release-linux: $APPIMAGE was not produced" >&2; exit 1; }
[ -f "$DIST/$APPIMAGE.sig" ] || { echo "release-linux: $APPIMAGE.sig was not produced — signing failed?" >&2; exit 1; }

# --- 2) HARD GATE: verify the signature against the committed public key ---
echo "== release-linux: verifying the signature against RELEASE_PUBLIC_KEY_B64 =="
PYTHONPATH="$ROOT/src" python3 - "$DIST/$APPIMAGE" "$DIST/$APPIMAGE.sig" <<'PY'
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
    sys.exit("release-linux: SIGNATURE VERIFICATION FAILED — refusing to publish")
print("release-linux: signature verified against the committed public key")
PY

# --- 3) release notes from the CHANGELOG section --------------------------
NOTES="$(mktemp)"
trap 'rm -f "$NOTES"' EXIT
awk -v ver="$VERSION" '
    $0 ~ ("^## \\[" ver "\\]") { grab = 1; next }
    grab && /^## \[/           { exit }
    grab                       { print }
' CHANGELOG.md > "$NOTES"
[ -s "$NOTES" ] || echo "Release $VERSION." > "$NOTES"

# --- 4) SHA256SUMS manifest: clean → fetch → verify → merge → sign → verify ---
# (§ 3.3). Symmetric with release-windows.sh so re-running either script in any
# order re-derives the union of the published lines and never regresses the
# manifest to a single platform.
echo "== release-linux: building the signed SHA256SUMS manifest =="

# Step 1 — start clean (INV-4): a stale SHA256SUMS from a PREVIOUS version must
# not leak phantom basenames into this release's merge.
rm -f "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig"

# Step 2 — fetch the current manifest, guided by the release and FAILING CLOSED
# on ambiguity. release-not-found is the legitimate first-publish case (→ start
# fresh); ANY other gh failure (network/API flake on view OR download) must
# abort, never be read as "no prior manifest" — else the --clobber upload below
# would REGRESS a complete manifest back to a single platform.
VIEW_ERR="$(mktemp)"
VIEW_ASSETS="$(mktemp)"
trap 'rm -f "$NOTES" "$VIEW_ERR" "$VIEW_ASSETS"' EXIT
if gh release view "$TAG" --json assets --jq '.assets[].name' >"$VIEW_ASSETS" 2>"$VIEW_ERR"; then
    if grep -qx SHA256SUMS "$VIEW_ASSETS"; then
        echo "== release-linux: fetching the published SHA256SUMS to merge into =="
        gh release download "$TAG" -p SHA256SUMS -p SHA256SUMS.sig -D "$DIST" || {
            echo "release-linux: could not download the published SHA256SUMS — aborting (won't regress the manifest to one platform)" >&2; exit 1; }
        # Step 3 — VERIFY the fetched manifest against the committed key BEFORE
        # trusting its carried line (the anti-laundering gate). Refuse on a
        # missing .sig or a signature mismatch: present-but-unverifiable is
        # tampering, not a fresh start. Without this the re-sign in step 5 would
        # launder a tampered carried line into a freshly-valid signature.
        [ -f "$DIST/SHA256SUMS.sig" ] || { echo "release-linux: published SHA256SUMS has no .sig — refusing to merge an unverifiable manifest" >&2; exit 1; }
        echo "== release-linux: verifying the fetched SHA256SUMS against RELEASE_PUBLIC_KEY_B64 =="
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
    sys.exit("release-linux: FETCHED SHA256SUMS FAILED VERIFICATION — refusing to merge (won't launder a tampered manifest)")
print("release-linux: fetched SHA256SUMS verified against the committed public key")
PY
    fi
elif grep -qi "release not found" "$VIEW_ERR"; then
    echo "== release-linux: no existing release $TAG — starting a fresh SHA256SUMS =="
else
    echo "release-linux: 'gh release view' failed (not a release-not-found) — aborting rather than risk regressing SHA256SUMS:" >&2
    cat "$VIEW_ERR" >&2
    exit 1
fi

# Step 4 — merge this phase's line (the AppImage): the helper keeps the fetched
# other-platform line and adds/replaces only the AppImage basename (§ 3.2).
echo "== release-linux: adding the AppImage to SHA256SUMS =="
scripts/gen-checksums.sh "$DIST/SHA256SUMS" "$DIST/$APPIMAGE"

# Step 5 — sign the FINAL merged bytes (never reuse a fetched sig; INV-3).
echo "== release-linux: signing SHA256SUMS with the release key =="
python3 scripts/sign-release.py "$DIST/SHA256SUMS"
[ -f "$DIST/SHA256SUMS.sig" ] || { echo "release-linux: SHA256SUMS.sig was not produced — signing failed?" >&2; exit 1; }

# Step 6 — HARD GATE: verify the re-signed SHA256SUMS.sig against the committed
# key before publishing, exactly as the binary is gated above. A Kind: security
# item must not publish a signature its own committed key rejects.
echo "== release-linux: verifying SHA256SUMS.sig against RELEASE_PUBLIC_KEY_B64 =="
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
    sys.exit("release-linux: SHA256SUMS SIGNATURE VERIFICATION FAILED — refusing to publish")
print("release-linux: SHA256SUMS signature verified against the committed public key")
PY

# --- 7) publish (non-prerelease so /releases/latest resolves) -------------
# Step 7 — the manifest, its sig, and the linux SBOM ride the SAME asset list as
# the AppImage; --clobber replaces any prior manifest with this merged, re-signed one.
if gh release view "$TAG" >/dev/null 2>&1; then
    echo "== release-linux: release $TAG already exists — uploading AppImage assets (clobber) =="
    gh release upload "$TAG" "$DIST/$APPIMAGE" "$DIST/$APPIMAGE.sig" \
        "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig" "$DIST/finbreak-$VERSION-linux.cdx.json" --clobber
else
    echo "== release-linux: creating release $TAG =="
    gh release create "$TAG" "$DIST/$APPIMAGE" "$DIST/$APPIMAGE.sig" \
        "$DIST/SHA256SUMS" "$DIST/SHA256SUMS.sig" "$DIST/finbreak-$VERSION-linux.cdx.json" \
        --title "finbreak $TAG" --notes-file "$NOTES" --latest
fi

echo "== release-linux: DONE — $TAG published with the Linux AppImage + .sig =="
echo "   Next: run scripts/release-windows.sh to build, sign, and attach the Windows .exe."
