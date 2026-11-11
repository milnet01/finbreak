#!/bin/sh
# obs-status.sh (FIBR-0155) — poll the OBS build results until every repo reaches
# a terminal state built from the committed source, then say why each repo that
# did not succeed failed: its build-log tail, or OBS's reason for one that never
# built.
#
# Run standalone after obs-submit.sh. Override via env: OBS_API, OBS_PROJECT,
# OBS_PACKAGE, POLL_SECS (default 45), MAX_POLLS (default 80), SETTLE_POLLS
# (default 3).
set -eu

API="${OBS_API:-https://api.opensuse.org}"
PROJ="${OBS_PROJECT:-home:milnet:finbreak}"
PKG="${OBS_PACKAGE:-finbreak}"
POLL_SECS="${POLL_SECS:-45}"
MAX_POLLS="${MAX_POLLS:-80}"
SETTLE_POLLS="${SETTLE_POLLS:-3}"
# A non-number fails `[ -lt ]` inside an `elif` without tripping `set -e`, which
# would silently switch the settle period off.
whole_number() {
    case "$2" in
        ''|*[!0-9]*) echo "!!! $1 must be a whole number, got '$2'" >&2; exit 2 ;;
    esac
}
whole_number POLL_SECS "$POLL_SECS"
whole_number MAX_POLLS "$MAX_POLLS"
whole_number SETTLE_POLLS "$SETTLE_POLLS"

# A repo row is "done" once it is no longer scheduled/building/etc.
is_pending() {
    case "$1" in
        scheduled|building|dispatching|blocked|signing|finished|locked|deleting|""|unknown) return 0 ;;
        # osc stars a result that is not current: built from the previous
        # source with the rebuild queued (FIBR-0317), or not yet published.
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
pending=1
while [ "$i" -lt "$MAX_POLLS" ]; do
    i=$((i + 1))
    printf '[poll %s] ' "$i"
    pending=0
    # osc's error, if any, reaches stderr: a run that cannot reach OBS says why.
    res="$(osc -A "$API" results --show-excluded "$PROJ" "$PKG")" || res=""
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
        elif { [ "$status" = unresolvable ] || [ "$status" = broken ] ||
            [ "$status" = excluded ]; } && [ "$i" -lt "$SETTLE_POLLS" ]; then
            # No build job dates these, so one shown straight after a commit
            # may be the previous source's. Believe it only from poll
            # SETTLE_POLLS, after SETTLE_POLLS-1 waits (FIBR-0464).
            status="$status(settling)"
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
final="$(osc -A "$API" results --show-excluded "$PROJ" "$PKG")" || { echo "!!! could not read the build results" >&2; exit 1; }
echo "$final"

# Say why each repo that did not succeed failed. osc hides an excluded repo
# unless asked, and excluded means no package at all, so it fails here
# (FIBR-0463). A here-document, not a pipe, so `failed` is set in this shell
# rather than in a subshell.
while read -r repo arch _pkg status _rest; do
    [ -n "${repo:-}" ] || continue
    if [ "$status" != "succeeded" ] && [ "$status" != "disabled" ]; then
        failed=1
        echo "########## $repo ($status) ##########"
        # osc stars a row that is not current, and always stars a blocked one.
        case "${status%\*}" in
            # These never built from this source, so there is no log of it;
            # OBS keeps the reason (a missing BuildRequires, say) in the row's
            # details (FIBR-0466).
            unresolvable|broken|excluded|blocked|scheduled)
                if why="$(osc -A "$API" results --show-excluded -r "$repo" -a "$arch" \
                    --format '%(details)s' "$PROJ" "$PKG" 2>&1)"; then
                    # osc prints None for a row with no details.
                    case "$why" in
                        ""|None) echo "(OBS gave no reason)" ;;
                        *) echo "$why" ;;
                    esac
                else
                    echo "(could not read the reason from OBS)"
                fi ;;
            *) osc -A "$API" buildlog "$PROJ" "$PKG" "$repo" "$arch" 2>&1 | tail -40 ;;
        esac
    fi
done <<RESULTS
$final
RESULTS

if [ "$failed" -ne 0 ]; then
    echo "!!! at least one build failed or did not finish" >&2
    exit 1
fi
