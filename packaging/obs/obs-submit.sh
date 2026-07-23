#!/bin/sh
# obs-submit.sh (FIBR-0155) — vendor the wheels, populate the OBS checkout with
# the recipe files, run the source services, and commit a new revision.
#
# Repeatable per-release flow. Run from anywhere; paths resolve relative to this
# script. Assumes obs-setup.sh has created the project + package once.
#
# Needs: osc (authenticated), obs-service-tar + obs-service-obs_scm, and a
# glibc >= 2.34 host for the wheel vendoring. Override via env: OBS_API,
# OBS_PROJECT, OBS_PACKAGE, OBS_WORKDIR, OBS_MSG. Set REVENDOR=1 to force a fresh
# vendor.tar.gz even if one already exists.
set -eu

API="${OBS_API:-https://api.opensuse.org}"
PROJ="${OBS_PROJECT:-home:milnet:finbreak}"
PKG="${OBS_PACKAGE:-finbreak}"

HERE="$(cd "$(dirname "$0")" && pwd)"     # packaging/obs
ROOT="$(cd "$HERE/../.." && pwd)"         # repo root
WORKDIR="${OBS_WORKDIR:-$ROOT/build-obs}" # osc checkout lives here (gitignored)
VENDOR="$ROOT/vendor.tar.gz"

# 1. Offline wheel closure (reuse unless missing or REVENDOR=1).
if [ "${REVENDOR:-0}" = "1" ] || [ ! -f "$VENDOR" ]; then
    echo ">>> vendoring wheels -> $VENDOR"
    ( cd "$ROOT" && sh "$HERE/vendor-wheels.sh" )
else
    echo ">>> reusing existing $VENDOR (REVENDOR=1 to rebuild)"
fi

# 2. Checkout or update the package working copy.
mkdir -p "$WORKDIR"
CO="$WORKDIR/$PROJ/$PKG"
if [ -d "$CO/.osc" ]; then
    echo ">>> updating checkout: $CO"
    ( cd "$CO" && osc -A "$API" update )
else
    echo ">>> checking out $PROJ/$PKG"
    ( cd "$WORKDIR" && osc -A "$API" checkout "$PROJ" "$PKG" )
fi

# 3. Populate with the recipe files + the vendored closure.
echo ">>> copying recipe files"
cp "$HERE/_service" "$HERE/finbreak.spec" "$HERE/finbreak-rpmlintrc" "$CO/"
rm -rf "$CO/debian"; cp -r "$HERE/debian" "$CO/"
cp "$VENDOR" "$CO/vendor.tar.gz"

# 4. Run the source services (obs_scm pulls the tagged source; set_version
#    stamps the .spec + debian/changelog), stage everything, and commit.
cd "$CO"
echo ">>> running source services (obs_scm + tar + set_version)"
osc -A "$API" service manualrun

osc -A "$API" add _service finbreak.spec finbreak-rpmlintrc finbreak-*.tar.gz vendor.tar.gz 2>/dev/null || true
[ -d "$CO/debian" ] && printf 'y\n' | osc -A "$API" add debian 2>/dev/null || true
osc -A "$API" addremove 2>/dev/null || true

VER="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/finbreak/__init__.py")"
osc -A "$API" commit -m "${OBS_MSG:-finbreak $VER}"

echo "OK — committed. Watch the builds with: packaging/obs/obs-status.sh"
