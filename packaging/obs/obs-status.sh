#!/bin/sh
# obs-status.sh (FIBR-0155) — poll the OBS build results until every repo reaches
# a terminal state built from the committed source, then print the tail of any
# build log that did not succeed.
#
# Run standalone after obs-submit.sh. Override via env: OBS_API, OBS_PROJECT,
# OBS_PACKAGE, POLL_SECS (default 45), MAX_POLLS (default 80).
set -eu

API="${OBS_API:-https://api.opensuse.org}"
PROJ="${OBS_PROJECT:-home:milnet:finbreak}"
PKG="${OBS_PACKAGE:-finbreak}"
POLL_SECS="${POLL_SECS:-45}"
MAX_POLLS="${MAX_POLLS:-80}"

# A repo row is "done" once it is no longer scheduled/building/etc.
is_pending() {
    case "$1" in
        scheduled|building|dispatching|blocked|signing|finished|locked|deleting|""|unknown) return 0 ;;
        # A trailing * marks a result from the previous source, with the
        # rebuild still queued (FIBR-0317).
        *\*) return 0 ;;
        *) return 1 ;;
    esac
}

# The checksum of the source just committed. Straight after a commit OBS can
# still show the last source's results without the `*`, so a build result is
# final only once OBS built it from this source (FIBR-0463).
src="$(osc -A "$API" api "/source/$PROJ/$PKG")" || { echo "!!! could not read the OBS source" >&2; exit 1; }
SRCMD5="$(printf '%s\n' "$src" | sed -n 's/^<directory .*srcmd5="\([^"]*\)".*/\1/p')"
[ -n "$SRCMD5" ] || { echo "!!! the OBS source listing carries no srcmd5" >&2; exit 1; }

# The source checksum of the newest build job for repo $1, arch $2.
built_from() {
    osc -A "$API" api "/build/$PROJ/$1/$2/_jobhistory?package=$PKG&limit=1" |
        sed -n 's/.*srcmd5="\([^"]*\)".*/\1/p' | tail -1
}

i=0
while [ "$i" -lt "$MAX_POLLS" ]; do
    i=$((i + 1))
    printf '[poll %s] ' "$i"
    pending=0
    # osc's error, if any, reaches stderr: a run that cannot reach OBS says why.
    res="$(osc -A "$API" results "$PROJ" "$PKG")" || res=""
    [ -n "$res" ] || pending=1
    # Each line: <repo> <arch> <package> <status>
    while read -r repo arch _pkg status _rest; do
        [ -n "${repo:-}" ] || continue
        if is_pending "$status"; then
            pending=1
        elif { [ "$status" = succeeded ] || [ "$status" = failed ]; } &&
            [ "$(built_from "$repo" "$arch")" != "$SRCMD5" ]; then
            status="$status(old-source)"
            pending=1
        fi
        printf '%s=%s ' "$repo" "$status"
    done <<RESULTS
$res
RESULTS
    echo
    [ "$pending" -eq 0 ] && break
    sleep "$POLL_SECS"
done

# Exit non-zero on a failed build or a timeout, so a caller cannot read either
# as success (FIBR-0400).
failed=0
if [ "$pending" -ne 0 ]; then
    echo "!!! timed out after $MAX_POLLS polls with builds still pending" >&2
    failed=1
fi

echo "=== final ==="
final="$(osc -A "$API" results "$PROJ" "$PKG")" || { echo "!!! could not read the build results" >&2; exit 1; }
echo "$final"

# Dump the log tail for any repo that did not succeed. A here-document, not a
# pipe, so `failed` is set in this shell rather than in a subshell.
while read -r repo arch _pkg status _rest; do
    [ -n "${repo:-}" ] || continue
    if [ "$status" != "succeeded" ] && [ "$status" != "excluded" ] && [ "$status" != "disabled" ]; then
        failed=1
        echo "########## $repo ($status) ##########"
        osc -A "$API" buildlog "$PROJ" "$PKG" "$repo" "$arch" 2>&1 | tail -40
    fi
done <<RESULTS
$final
RESULTS

if [ "$failed" -ne 0 ]; then
    echo "!!! at least one build failed or did not finish" >&2
    exit 1
fi
