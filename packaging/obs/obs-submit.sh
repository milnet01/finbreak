#!/bin/sh
# obs-submit.sh (FIBR-0155) — vendor the wheels, populate the OBS checkout with
# the recipe files, run the source services, and commit a new revision.
#
# Repeatable per-release flow. Run from anywhere; paths resolve relative to this
# script. Assumes obs-setup.sh has created the project + package once.
#
# Needs: osc (authenticated), obs-service-tar + obs-service-obs_scm, and a
# glibc >= 2.34 host for the wheel vendoring. Override via env: OBS_API,
# OBS_PROJECT, OBS_PACKAGE, OBS_WORKDIR, OBS_MSG. vendor.tar.gz is rebuilt when
# pyproject.toml is newer than it; set REVENDOR=1 to force a fresh one anyway.
# Refuses when the recipe files or pyproject.toml differ from the release tag
# _service builds (FIBR-0385).
set -eu

API="${OBS_API:-https://api.opensuse.org}"
PROJ="${OBS_PROJECT:-home:milnet:finbreak}"
PKG="${OBS_PACKAGE:-finbreak}"

HERE="$(cd "$(dirname "$0")" && pwd)"     # packaging/obs
ROOT="$(cd "$HERE/../.." && pwd)"         # repo root
WORKDIR="${OBS_WORKDIR:-$ROOT/build-obs}" # osc checkout lives here (gitignored)
VENDOR="$ROOT/vendor.tar.gz"

# 0. One submission, one moment (FIBR-0385). obs_scm takes the source from the
#    release tag _service names, but the recipes below are copied from this
#    working tree and the wheel closure is built from its pyproject.toml. Refuse
#    unless both match that tag, so an edit made since the release never ships
#    under the release's name.
TAG="$(sed -n 's:.*<param name="revision">\(.*\)</param>.*:\1:p' "$HERE/_service")"
SHIPPED="packaging/obs/_service packaging/obs/finbreak.spec
packaging/obs/finbreak-rpmlintrc packaging/obs/finbreak.dsc
packaging/obs/debian pyproject.toml"
if ! git -C "$ROOT" rev-parse -q --verify "$TAG^{commit}" >/dev/null; then
    echo "obs-submit: _service builds '$TAG', which is not a tag in this repo" >&2
    exit 1
fi
# shellcheck disable=SC2086 # SHIPPED is a list of paths without spaces
DRIFT="$(git -C "$ROOT" diff --name-only "$TAG" -- $SHIPPED;
         git -C "$ROOT" ls-files --others --exclude-standard -- $SHIPPED)"
if [ -n "$DRIFT" ]; then
    echo "obs-submit: these differ from $TAG, the source OBS will build:" >&2
    echo "$DRIFT" >&2
    echo "Commit them in a release, or run from 'git checkout $TAG'." >&2
    exit 1
fi

# 1. Offline wheel closure: rebuilt when missing, when REVENDOR=1, or when
#    pyproject.toml or the vendoring script is newer than it (FIBR-0385).
if [ "${REVENDOR:-0}" = "1" ] || [ ! -f "$VENDOR" ] \
   || [ "$ROOT/pyproject.toml" -nt "$VENDOR" ] \
   || [ "$HERE/vendor-wheels.sh" -nt "$VENDOR" ]; then
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
cp "$HERE/_service" "$HERE/finbreak.spec" "$HERE/finbreak-rpmlintrc" \
   "$HERE/finbreak.dsc" "$CO/"
cp "$VENDOR" "$CO/vendor.tar.gz"

# The deb recipe travels as debian.tar.gz, NOT as a debian/ directory: OBS's
# debtransform only reads a `debian.tar[.gz|.bz2|.xz]` or loose `debian.*`
# files, and never a directory (nor the debian.obscpio an `osc add debian`
# produces). finbreak.dsc names this archive AND vendor.tar.gz in its
# DEBTRANSFORM-FILES-TAR, which is how the wheel closure reaches the deb build
# tree at vendor/ -- deb builds have no RPM-style Source1. Verified 2026-08-31
# by running debtransform and dpkg-source -x on the result (FIBR-0158).
echo ">>> packing debian.tar.gz"
tar -C "$HERE" -czf "$CO/debian.tar.gz" debian

# Retire the directory form an earlier revision committed. `osc add debian`
# stores a directory as debian.obscpio, which debtransform cannot read, so it
# only ever looked like a deb recipe. Harmless to re-run once it is gone.
rm -rf "$CO/debian"
if [ -e "$CO/debian.obscpio" ]; then
    ( cd "$CO" && osc -A "$API" rm --force debian.obscpio )
fi

# 4. Run the source services (obs_scm pulls the tagged source; set_version
#    stamps the Version of finbreak.spec and finbreak.dsc), stage everything,
#    and commit. set_version no longer reaches debian/changelog -- that file is
#    inside debian.tar.gz now -- and does not need to: debtransform reconciles
#    the changelog to the .dsc Version, adding an entry when they disagree.
cd "$CO"

# Drop any previously-committed source tarball before the services mint the new
# one. Two of them is fatal to the deb build and silent on the RPM side: the RPM
# takes Source0 by exact name, while debtransform discovers its source archive
# and refuses when more than one candidate is present (FIBR-0158).
rm -f finbreak-*.tar.gz

echo ">>> running source services (obs_scm + tar + set_version)"
osc -A "$API" service manualrun

# No `|| true`: an already-tracked file is only a warning to `osc add` (exit 0),
# so an error here is real -- a new source tarball that would otherwise be
# missing from the commit (FIBR-0400).
osc -A "$API" add _service finbreak.spec finbreak.dsc finbreak-rpmlintrc \
    finbreak-*.tar.gz vendor.tar.gz debian.tar.gz
osc -A "$API" addremove

VER="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/finbreak/__init__.py")"
osc -A "$API" commit -m "${OBS_MSG:-finbreak $VER}"

echo "OK — committed. Watch the builds with: packaging/obs/obs-status.sh"
