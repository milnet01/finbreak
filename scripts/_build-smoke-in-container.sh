#!/usr/bin/env bash
# Runs INSIDE the build container (invoked by scripts/build-smoke.sh). Freezes
# `python -m finbreak --self-test` to a PyInstaller --onefile and wraps that same
# binary in an AppImage, proving every native stack travels: Qt (PySide6),
# SQLCipher, qpdf (pikepdf), Argon2 (argon2-cffi), and ofxparse's tree incl.
# native lxml. The image is python:3.12-slim-bookworm: it ships a
# SHARED libpython (PyInstaller needs one — manylinux's is static) and an
# older-than-host glibc (~2.36), which bounds the artifact's floor below the
# debian:13-slim test target (FIBR-0003 INV-2/INV-4).
#
# Reads ONEFILE / APPIMAGE from the environment; writes both artifacts to /out
# (a host bind-mount). /src is the read-only project root; /cache persists the
# fetched appimagetool between runs.
set -euo pipefail

VENV=/tmp/benv
APPDIR=/tmp/AppDir

echo "-- installing build prerequisites + Qt runtime libs --"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# Two groups:
#  - build tools: binutils (objdump/objcopy for PyInstaller + appimagetool),
#    file (appimagetool needs it), ca-certificates (HTTPS appimagetool fetch).
#  - Qt's system-library dependencies: PySide6 bundles Qt itself but Qt links
#    these OS libs. They must be PRESENT here so PyInstaller's dependency
#    analysis collects them INTO the bundle (ADR-0007 "collect native libs");
#    otherwise the artifact fails on a bare target. apt pulls their transitive
#    deps (libpng, libbrotlicommon, …) too, which PyInstaller then also bundles.
apt-get install -y -qq --no-install-recommends \
    binutils file ca-certificates \
    libglib2.0-0 libgl1 libegl1 libdbus-1-3 libx11-6 libxkbcommon0 \
    libfreetype6 libfontconfig1 libbrotli1 libharfbuzz0b >/dev/null

echo "-- provisioning the build venv from pyproject --"
# Persist pip's download cache in /cache (a host bind-mount) so re-runs reuse
# the ~250 MB PySide6 wheel instead of re-fetching it every build.
export PIP_CACHE_DIR=/cache/pip
python3 -m venv "$VENV"
# shellcheck disable=SC1091
. "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip
# Install the project's REAL runtime deps, read straight from pyproject (single
# source of truth), NOT a hand-maintained list — that drift silently dropped
# argon2-cffi from the bundle after FIBR-0004 and would have dropped ofxparse
# (FIBR-0008). We read `[project].dependencies` and install exactly those
# (PySide6, sqlcipher3-wheels, pikepdf, argon2-cffi, ofxparse + its bs4/lxml/six
# tree). We do NOT `pip install /src` (the finbreak package itself): PyInstaller
# freezes the source directly via --paths /src/src, and building the sdist would
# fail writing egg-info into the read-only /src mount. PyInstaller is a build
# tool (pyproject `build` group), installed separately.
mapfile -t RUNTIME_DEPS < <(python -c "import tomllib; [print(d) for d in tomllib.load(open('/src/pyproject.toml','rb'))['project']['dependencies']]")
if [ -n "${VERSION:-}" ]; then
    # RELEASE MODE (FIBR-0096 § 3.4) — generate a CycloneDX SBOM of the bundled
    # runtime closure. Split the combined install so the SBOM reflects the runtime
    # deps AS INSTALLED, captured BEFORE any build tool enters the venv.
    python -m pip install --quiet "${RUNTIME_DEPS[@]}"
    # This pip freeze IS the runtime closure PyInstaller then collects from — no
    # build tools, no re-resolution of the ranged/transitive versions. Honest
    # scope (§ 2 out-of-scope residuals): NOT a byte-level proof every listed
    # package landed in the one-file; installing PyInstaller after this snapshot
    # can bump a SHARED transitive (e.g. packaging) by a patch; and a plain freeze
    # also lists base tooling (pip/setuptools/wheel) PyInstaller does not bundle.
    FROZEN="$(mktemp)"
    python -m pip freeze > "$FROZEN"
    # pip-audit is NOT in the freeze venv (it's a dev-group tool the gate installs
    # on the HOST), so install the SAME pin (pyproject) into the venv now — AFTER
    # the snapshot, so it never pollutes it; it only READS the frozen file.
    python -m pip install --quiet pip-audit==2.10.0
    OUT="/out/finbreak-$VERSION-linux.cdx.json"
    # Remove any stale SBOM from a same-version re-cut first (/out is persistent —
    # build-smoke.sh only mkdir -p's it), so the guard below can't false-pass on it.
    rm -f "$OUT"
    # --no-deps audits the fully-pinned freeze AS-IS: without it `pip-audit -r`
    # RE-RESOLVES against PyPI, reintroducing the drift the freeze exists to avoid.
    # The `|| true` is deliberate: pip-audit exits NON-ZERO when it finds any
    # advisory but STILL writes the SBOM, and this runs under `set -euo pipefail` —
    # the SBOM is a TRANSPARENCY artifact, not the vuln gate (that still fails the
    # build on the host, T7). An un-tolerated call would abort the release build
    # the moment a pinned dep ages into a CVE.
    pip-audit -r "$FROZEN" --no-deps --format cyclonedx-json --output "$OUT" || true
    # Existence guard — a swallowed ADVISORY is fine, a swallowed CRASH is not: a
    # resolver/network failure writes NO file, which `|| true` would hide until the
    # § 3.5 upload of a mandatory asset. Assert the output exists now.
    [ -f "$OUT" ] || { echo "SBOM: pip-audit produced no output — a real failure, not a tolerated advisory" >&2; exit 1; }
    python -m pip install --quiet pyinstaller==6.21.0
else
    python -m pip install --quiet "${RUNTIME_DEPS[@]}" pyinstaller==6.21.0
fi

# INV-2: exactly one Qt binding must be present before freezing (PyInstaller
# 6.x refuses to collect more than one).
qt_count="$(python -m pip list --format=freeze \
    | grep -icE '^(PySide2|PySide6|PyQt5|PyQt6)==' || true)"
if [ "$qt_count" != "1" ]; then
    echo "build-smoke: expected exactly one Qt binding, found $qt_count" >&2
    exit 1
fi

echo "-- freezing --onefile --"
# The self-test imports every native stack LAZILY (inside its _check_* fn), so
# each needs help travelling into the frozen bundle. sqlcipher3/pikepdf use the
# hidden-import + collect-binaries pair; argon2-cffi (native lib in the separate
# _argon2_cffi_bindings package) and ofxparse's tree (bs4 + native lxml) use
# --collect-all to pull submodules + data + binaries wholesale. pdfplumber
# (FIBR-0009) is likewise lazily imported and its tree is native-heavy: PDFium's
# libpdfium.so ships in the SEPARATE top-level pypdfium2_raw package (a plain
# --collect-all pypdfium2 would miss the binary — the exact DoD #2 failure), and
# Pillow (PIL) + cryptography (via pdfminer.six) carry native/data payloads
# PyInstaller does not follow by import alone. Without these, the clean-room
# launch fails with ModuleNotFoundError (FIBR-0004 argon2 gap; FIBR-0008 adds
# ofxparse/lxml; FIBR-0009 adds pdfplumber's tree).
# The ui/icons/ package data (FIBR-0051 SVG toolbar glyphs + the FIBR-0037 app.png
# window icon) is data, not an import, so PyInstaller does not follow it — the
# directory-level --add-data below places the WHOLE dir at the same package-relative
# path ui/icons.py resolves via Path(__file__).parent / "icons" (the DoD #2
# non-null-pixmap self-test legs fail the bundle if the SVG glyph OR app.png don't
# travel). The Qt SVG plugins (imageformats/qsvg + iconengines/qsvgicon) that RENDER
# the SVGs are collected by PyInstaller's PySide6 hook by default; PNG decoding is
# built into Qt Gui, so app.png needs no extra plugin.
pyinstaller --onefile --name "$ONEFILE" \
    --paths /src/src \
    --add-data "/src/src/finbreak/ui/icons:finbreak/ui/icons" \
    --add-data "/src/src/finbreak/data:finbreak/data" \
    --hidden-import sqlcipher3 \
    --hidden-import pikepdf \
    --hidden-import PySide6.QtWidgets \
    --collect-binaries pikepdf \
    --collect-binaries sqlcipher3 \
    --collect-all argon2 \
    --collect-all _argon2_cffi_bindings \
    --collect-all ofxparse \
    --collect-all bs4 \
    --collect-all lxml \
    --collect-all pdfplumber \
    --collect-all pdfminer \
    --collect-all pypdfium2 \
    --collect-all pypdfium2_raw \
    --collect-all PIL \
    --collect-all cryptography \
    --collect-all certifi \
    --distpath /out --workpath /tmp/build --specpath /tmp \
    /src/src/finbreak/__main__.py

echo "-- fetching appimagetool --"
TOOL=/cache/appimagetool-x86_64.AppImage
if [ ! -x "$TOOL" ]; then
    python -c 'import urllib.request,sys; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" \
        "$TOOL"
    chmod +x "$TOOL"
fi

echo "-- assembling AppDir --"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp "/out/$ONEFILE" "$APPDIR/usr/bin/$ONEFILE"
cat > "$APPDIR/AppRun" <<EOF
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\$HERE/usr/bin/$ONEFILE" "\$@"
EOF
chmod +x "$APPDIR/AppRun"
# Desktop metadata is env-driven so the same freeze serves both the self-test
# smoke stub (defaults below) and the real release build (build-smoke.sh
# --release exports APP_DISPLAY_NAME=finbreak, APP_TERMINAL=false, a real icon).
APP_DISPLAY_NAME="${APP_DISPLAY_NAME:-finbreak-selftest}"
APP_TERMINAL="${APP_TERMINAL:-true}"
APP_CATEGORIES="${APP_CATEGORIES:-Utility;}"
cat > "$APPDIR/$ONEFILE.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_DISPLAY_NAME
Exec=$ONEFILE
Icon=$ONEFILE
Categories=$APP_CATEGORIES
Terminal=$APP_TERMINAL
EOF
# appimagetool requires an icon. A release build points APP_ICON_SRC at the real
# app.png (FIBR-0037); the smoke stub has none, so generate a placeholder square
# (Pillow is present — a pikepdf dependency).
if [ -n "${APP_ICON_SRC:-}" ] && [ -f "$APP_ICON_SRC" ]; then
    cp "$APP_ICON_SRC" "$APPDIR/$ONEFILE.png"
else
    python -c "from PIL import Image; Image.new('RGBA', (64, 64), (30, 120, 80, 255)).save('$APPDIR/$ONEFILE.png')"
fi

echo "-- building AppImage --"
# Containers lack /dev/fuse, so extract-and-run instead of mounting; skip the
# optional AppStream metadata check (no metainfo in this smoke stub).
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "/out/$APPIMAGE"

echo "-- in-container build done --"
