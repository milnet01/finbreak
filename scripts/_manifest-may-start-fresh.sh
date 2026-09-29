#!/usr/bin/env bash
# May a release script start a FRESH SHA256SUMS for a release that exists but
# lists none? Called by release-linux.sh and release-windows.sh on that branch.
#
#   scripts/_manifest-may-start-fresh.sh <asset-list-file> <other-platform-glob>
#
# Exit 0: nothing says a manifest was ever published -- start fresh.
# Exit 1: something does, and a fresh manifest would carry this platform's line
#         only, dropping the other's (full audit 2026-09-27 row 42):
#   - SHA256SUMS.sig is listed without SHA256SUMS -- the half-state a failed
#     --clobber left on 0.1.21;
#   - the OTHER platform's artifact is listed, so its line belongs in the
#     manifest and only the published one carries it.
# This platform's own leftovers do not block: the upload replaces them.
set -euo pipefail

assets="$1"
other="$2"

refuse() {
    echo "release: $1 -- a fresh SHA256SUMS would drop the other platform's line." >&2
    echo "release: re-upload the missing SHA256SUMS first (CLAUDE.md § Cutting a release, the one-file-per-call loop), then re-run." >&2
    exit 1
}

grep -qx SHA256SUMS.sig "$assets" && refuse "the release carries SHA256SUMS.sig but no SHA256SUMS"
while IFS= read -r name; do
    # shellcheck disable=SC2254  # $other is a glob on purpose
    case "$name" in
        $other) refuse "the release already carries $name" ;;
    esac
done <"$assets"
exit 0
