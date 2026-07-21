#!/usr/bin/env bash
# FIBR-0096 — the single source of the SHA256SUMS manifest format. Both release
# scripts call this rather than each duplicating sha256sum plumbing (§ 3.2).
#
#   gen-checksums.sh <sumsfile> <artifact> [<artifact> …]
#
# For each <artifact>, compute its SHA-256 and write/replace a line
# `<64-lc-hex>␠␠<basename>` (TWO spaces, basename only) in <sumsfile> — the exact
# format `sha256sum -c --ignore-missing SHA256SUMS` consumes from the folder
# holding the downloads (--ignore-missing skips the other platform's line the
# user didn't download, § 1).
#
# MERGE, don't clobber: lines already in <sumsfile> for OTHER basenames are kept;
# only the passed artifacts' basenames are added/replaced. This is what lets the
# Windows phase add the exe to a manifest the Linux phase already published,
# without the AppImage being present on the Windows-release machine (§ 3.3).
#
# Lines are emitted sorted by basename (LC_ALL=C = codepoint order) so
# re-generation is byte-stable. Pure: no signing, no gh — signing is a separate
# explicit call in the release scripts (§ 3.2).
set -euo pipefail

[ "$#" -ge 2 ] || {
    echo "usage: gen-checksums.sh <sumsfile> <artifact> [<artifact> …]" >&2
    exit 2
}

SUMSFILE="$1"
shift

declare -A HASHES

# Carry forward any lines already in the manifest (other-platform basenames from
# a prior phase) — keyed by basename so a passed artifact replaces only its own.
if [ -f "$SUMSFILE" ]; then
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        HASHES["${line#*  }"]="${line%%  *}"   # basename -> hex, split on the two spaces
    done < "$SUMSFILE"
fi

# Add/replace each passed artifact's line — basename only, freshly hashed.
for artifact in "$@"; do
    [ -f "$artifact" ] || { echo "gen-checksums: artifact not found: $artifact" >&2; exit 1; }
    HASHES["$(basename "$artifact")"]="$(sha256sum "$artifact" | cut -d' ' -f1)"
done

# Emit sorted by basename (codepoint order), two-space separator.
while IFS= read -r b; do
    printf '%s  %s\n' "${HASHES[$b]}" "$b"
done < <(printf '%s\n' "${!HASHES[@]}" | LC_ALL=C sort) > "$SUMSFILE"
