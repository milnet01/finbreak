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
#   4. gh release create vX.Y.Z (non-prerelease, --latest) with the AppImage + .sig
#      and notes lifted from the CHANGELOG [X.Y.Z] section.
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

# --- 4) publish (non-prerelease so /releases/latest resolves) -------------
if gh release view "$TAG" >/dev/null 2>&1; then
    echo "== release-linux: release $TAG already exists — uploading AppImage assets (clobber) =="
    gh release upload "$TAG" "$DIST/$APPIMAGE" "$DIST/$APPIMAGE.sig" --clobber
else
    echo "== release-linux: creating release $TAG =="
    gh release create "$TAG" "$DIST/$APPIMAGE" "$DIST/$APPIMAGE.sig" \
        --title "finbreak $TAG" --notes-file "$NOTES" --latest
fi

echo "== release-linux: DONE — $TAG published with the Linux AppImage + .sig =="
echo "   Next: run scripts/release-windows.sh to build, sign, and attach the Windows .exe."
