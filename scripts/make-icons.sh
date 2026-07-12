#!/usr/bin/env bash
# Regenerate the finbreak icon set from the single master (FIBR-0037).
#
# One source of truth: assets/icon/finbreak.png (1024x1024). Everything else is
# derived, so the platform icons can never drift from the master — rerun this
# after replacing the master. Needs ImageMagick (`magick`) on PATH.
#
# Outputs:
#   assets/icon/finbreak-<size>.png        Linux hicolor PNGs (16..512)
#   assets/icon/finbreak.ico               Windows (multi-size embedded)
#   assets/icon/finbreak.iconset/          macOS iconutil input (named PNGs)
#   src/finbreak/ui/icons/app.png          the runtime window icon (512, package data)
#
# macOS .icns: generated at mac build time from finbreak.iconset via `iconutil -c
# icns finbreak.iconset` (or `png2icns` on Linux). Not produced here because this
# repo's build box has neither, and no macOS build exists yet (FIBR-0015).
set -euo pipefail

cd "$(dirname "$0")/.."
MASTER="assets/icon/finbreak.png"
OUT="assets/icon"
[ -f "$MASTER" ] || { echo "master $MASTER missing" >&2; exit 1; }

# Rounded corners (FIBR-0118): the committed master is a hard square; round its
# corners so the app/window icon shows transparent corners instead of a solid
# tile. Do it ONCE at master resolution into a temp, then derive every size from
# the rounded temp — the master stays a pristine square source. Radius is 18% of
# the master edge (a modest rounded-rectangle, matching platform icon convention).
ROUNDED="$(mktemp --suffix=.png)"
MASK="$(mktemp --suffix=.png)"
trap 'rm -f "$ROUNDED" "$MASK"' EXIT
EDGE=$(magick identify -format '%w' "$MASTER")
RADIUS=$(( EDGE * 18 / 100 ))
magick -size "${EDGE}x${EDGE}" xc:black -fill white \
  -draw "roundrectangle 0,0,$((EDGE-1)),$((EDGE-1)),$RADIUS,$RADIUS" "$MASK"
magick "$MASTER" "$MASK" -alpha off -compose CopyOpacity -composite "$ROUNDED"
SRC="$ROUNDED"   # every derived output rounds via this; the master stays square

png() { magick "$SRC" -resize "${1}x${1}" -strip "$2"; }

# Linux hicolor PNGs.
for s in 16 24 32 48 64 128 256 512; do
  png "$s" "$OUT/finbreak-$s.png"
done

# Windows .ico — embed the common sizes in one file.
magick "$SRC" -define icon:auto-resize=256,128,64,48,32,24,16 "$OUT/finbreak.ico"

# macOS .iconset — the named PNGs `iconutil` consumes (@2x = double the base).
ICONSET="$OUT/finbreak.iconset"
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
png 16   "$ICONSET/icon_16x16.png"
png 32   "$ICONSET/icon_16x16@2x.png"
png 32   "$ICONSET/icon_32x32.png"
png 64   "$ICONSET/icon_32x32@2x.png"
png 128  "$ICONSET/icon_128x128.png"
png 256  "$ICONSET/icon_128x128@2x.png"
png 256  "$ICONSET/icon_256x256.png"
png 512  "$ICONSET/icon_256x256@2x.png"
png 512  "$ICONSET/icon_512x512.png"
cp "$SRC" "$ICONSET/icon_512x512@2x.png"   # 1024, the rounded master

# The runtime window icon travels as package data (ui/icons/ ships in the wheel +
# the PyInstaller bundle). 512 gives Qt a crisp source to scale to any title-bar/
# taskbar size.
png 512 "src/finbreak/ui/icons/app.png"

echo "icons regenerated from $MASTER"
