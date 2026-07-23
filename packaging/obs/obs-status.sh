#!/bin/sh
# obs-status.sh (FIBR-0155) — poll the OBS build results until every repo reaches
# a terminal state, then print the tail of any build log that did not succeed.
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
        scheduled|building|dispatching|blocked|signing|finished|""|unknown) return 0 ;;
        *) return 1 ;;
    esac
}

i=0
while [ "$i" -lt "$MAX_POLLS" ]; do
    i=$((i + 1))
    res="$(osc -A "$API" results "$PROJ" "$PKG" 2>/dev/null || true)"
    pending=0
    printf '[poll %s] ' "$i"
    # Each line: <repo> <arch> <package> <status>
    echo "$res" | while read -r repo arch _pkg status _rest; do
        [ -n "${repo:-}" ] || continue
        printf '%s=%s ' "$repo" "$status"
    done
    echo
    echo "$res" | awk '{print $4}' | while read -r st; do
        is_pending "$st" && echo pending
    done | grep -q pending && pending=1 || pending=0
    [ "$pending" -eq 0 ] && break
    sleep "$POLL_SECS"
done

echo "=== final ==="
osc -A "$API" results "$PROJ" "$PKG" || true

# Dump the log tail for any repo that did not succeed.
osc -A "$API" results "$PROJ" "$PKG" 2>/dev/null | while read -r repo arch _pkg status _rest; do
    [ -n "${repo:-}" ] || continue
    if [ "$status" != "succeeded" ] && [ "$status" != "excluded" ] && [ "$status" != "disabled" ]; then
        echo "########## $repo ($status) ##########"
        osc -A "$API" buildlog "$PROJ" "$PKG" "$repo" "$arch" 2>&1 | tail -40
    fi
done
