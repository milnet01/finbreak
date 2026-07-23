#!/usr/bin/env bash
# flatpak-build.sh — build + install + smoke-test the finbreak Flatpak locally
# (FIBR-0159 § 5). Mirrors what the Flathub CI does, so a green local run is the
# strongest pre-submission signal.
#
#   packaging/flatpak/flatpak-build.sh            # build + install --user + self-test
#   packaging/flatpak/flatpak-build.sh --run      # ...then launch the GUI
#   NO_SELFTEST=1 packaging/flatpak/flatpak-build.sh
#
# The build phase runs with NO network (all sources are sha256/commit pinned) — the
# same offline constraint as Flathub's builders, so a dep that slips to an
# offline-unbuildable sdist fails HERE, before submission (§ 3.6).
#
# Requires: flatpak-builder, the freedesktop 25.08 Platform + Sdk from Flathub:
#   flatpak install flathub org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
APP_ID="io.github.milnet01.finbreak"
MANIFEST="$HERE/${APP_ID}.yaml"
BUILDDIR="${BUILDDIR:-$HERE/.build}"
REPODIR="${REPODIR:-$HERE/.repo}"

if [[ ! -f "$HERE/python3-deps.yaml" ]]; then
    echo "!! python3-deps.yaml missing — run generate-pip-sources.sh first" >&2
    exit 1
fi

# LOCAL=1 (the default for dev iteration) builds the CURRENT local checkout: it
# rewrites the finbreak module's git source to file://$REPO at the current branch
# HEAD, so you validate committed-but-unpushed work (e.g. the _in_flatpak gate)
# without pushing + re-pinning. The committed manifest stays github+release-pinned
# for submission (§ 3.8); LOCAL=0 builds it verbatim to reproduce Flathub exactly.
# NOTE: a git source builds COMMITTED state — commit your work before a LOCAL build.
if [[ "${LOCAL:-1}" == "1" ]]; then
    BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
    MANIFEST="$HERE/.local-manifest.yaml"
    REPO="$REPO" BRANCH="$BRANCH" SRC="$HERE/${APP_ID}.yaml" OUT="$MANIFEST" \
        python3 - <<'PY'
import os, yaml
m = yaml.safe_load(open(os.environ["SRC"]))
repo, branch = os.environ["REPO"], os.environ["BRANCH"]
for mod in m["modules"]:
    if isinstance(mod, dict) and mod.get("name") == "finbreak":
        mod["sources"] = [{"type": "git", "url": f"file://{repo}", "branch": branch}]
yaml.safe_dump(m, open(os.environ["OUT"], "w"), sort_keys=False)
PY
    echo ">> LOCAL build: finbreak source = file://$REPO @ $BRANCH (HEAD)"
fi

echo ">> flatpak-builder: build (offline; all sources pinned)"
flatpak-builder \
    --user --force-clean --disable-rofiles-fuse \
    --repo="$REPODIR" \
    "$BUILDDIR" "$MANIFEST"

echo ">> install --user from the local repo"
flatpak-builder --user --force-clean --install \
    "$BUILDDIR" "$MANIFEST"

if [[ "${NO_SELFTEST:-0}" != "1" ]]; then
    echo ">> --self-test (FIBR-0003 native-stack sentinel: Qt + SQLCipher + qpdf)"
    flatpak run --command=finbreak "$APP_ID" --self-test
fi

if [[ "${1:-}" == "--run" ]]; then
    echo ">> launching the GUI"
    flatpak run "$APP_ID"
fi

cat <<EOF
>> done. Manual § 5 smoke checks (a real host, KDE-Wayland for the last two):
   * import a CSV/OFX/PDF via the file chooser -> a file opens (portal routing)
   * export a PDF report + an encrypted .fbk backup -> each written complete
   * Settings -> "check for updates" is DISABLED (updater inert under Flatpak)
   * "Center window" menu action is DISABLED (not a dead click); Reset-Layout
     does not attempt the org.kde.KWin D-Bus call
   * a network capture shows zero app-initiated outbound requests
EOF
