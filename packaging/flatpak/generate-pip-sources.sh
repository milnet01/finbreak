#!/usr/bin/env bash
# generate-pip-sources.sh — regenerate packaging/flatpak/python3-deps.yaml.
#
# The Flatpak analogue of packaging/obs/vendor-wheels.sh (FIBR-0159 § 3.6): emit a
# sha256-pinned pip-source module so the network-free Flathub build resolves the
# exact pinned closure offline. Re-run on the SAME trigger as the OBS vendor — a
# dependency-closure change (a new/bumped runtime dep in pyproject.toml).
#
#   packaging/flatpak/generate-pip-sources.sh
#
# What it does, and WHY each choice (rule 13 — verified against the real generator
# `--help`, not recalled):
#   * Deps are read from pyproject.toml's [project.dependencies] — the SINGLE
#     source of truth — and passed as the generator's positional packages, so the
#     resolved closure is exactly finbreak's runtime deps + their transitives.
#     finbreak ITSELF is not included (it is pip-installed separately in the
#     manifest's second module, § 3.2).
#   * --prefer-wheels is COMPUTED from the resolved closure, never hand-listed — a
#     silently-dropped native (pypdfium2, lxml) falling to an offline-unbuildable
#     sdist is the recurring failure mode this kills (§ 3.6). Preferring a wheel
#     for a package that only ships an sdist (ofxparse) is a no-op — it falls
#     through — so "prefer wheels for the whole closure" is the safe derived rule.
#   * --runtime runs pip INSIDE org.freedesktop.Sdk//25.08 so the wheels match the
#     Sdk's python (3.13 → cp313), a single ABI (§ 3.6).
#   * --wheel-arches=x86_64 only, for the first cut (matching OBS's x86_64-only
#     posture); aarch64 is a Flathub follow-up (README "Follow-ups").
#
# Requires: flatpak (with org.freedesktop.Sdk//25.08 installed), python3 with the
# `requirements-parser` module, network (generation only — the BUILD is offline).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
RUNTIME_BRANCH="${RUNTIME_BRANCH:-25.08}"
SDK="org.freedesktop.Sdk//${RUNTIME_BRANCH}"
GENERATOR="${GENERATOR:-$HERE/.flatpak-pip-generator.py}"
GEN_URL="https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator.py"
# The generator runs on the HOST interpreter (it only queries the Sdk for platform
# tags) and imports `requirements-parser`. Prefer an active venv, else python3 —
# override with PYGEN=. A distro python3 is often PEP-668 externally-managed, so
# install requirements-parser into the project venv, not system-wide.
PYGEN="${PYGEN:-${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}}"
PYGEN="${PYGEN:-$REPO/.venv/bin/python}"
[[ -x "$PYGEN" ]] || PYGEN="python3"

cd "$REPO"

if ! "$PYGEN" -c "import requirements" 2>/dev/null; then
    echo "!! '$PYGEN' lacks requirements-parser — the flatpak-pip-generator dep." >&2
    echo "   Install it into the interpreter running this script, e.g.:" >&2
    echo "     . .venv/bin/activate && python -m pip install requirements-parser" >&2
    echo "   (a system python3 is usually PEP-668 externally-managed)." >&2
    exit 1
fi

# --- The generator itself (cached next to this script; refetch with REFETCH=1).
if [[ "${REFETCH:-0}" == "1" || ! -f "$GENERATOR" ]]; then
    echo ">> fetching flatpak-pip-generator"
    curl -sSL -o "$GENERATOR" "$GEN_URL"
fi

# --- Sanity: the Sdk must be installed (it runs pip for python-version parity).
if ! flatpak info "$SDK" >/dev/null 2>&1; then
    echo "!! $SDK is not installed — flatpak install flathub $SDK" >&2
    exit 1
fi

# --- Runtime deps from pyproject (single source of truth). Each dep spec becomes
#     a positional package for the generator to resolve.
mapfile -t DEPS < <(python3 -c "
import tomllib
with open('pyproject.toml','rb') as f:
    for d in tomllib.load(f)['project']['dependencies']:
        print(d)
")
echo ">> ${#DEPS[@]} runtime deps from pyproject.toml"

# --- Derive --prefer-wheels from a pip dry-run resolve of the closure, never
#     hand-enumerated (§ 3.6). Include a package ONLY if the resolver picks a wheel
#     for it (download URL ends .whl) — an sdist-only package (ofxparse) resolves to
#     a .tar.gz and is EXCLUDED: flatpak-pip-generator ERRORS on a --prefer-wheels
#     package with no compatible wheel (it does NOT silently fall through to the
#     sdist), so the derived list must be the has-a-wheel subset. This split is read
#     from the resolver report itself, so a new sdist-only dep is handled with no
#     code change. (The resolve runs on this host's python 3.13 = the Sdk's cp313.)
echo ">> resolving closure to derive --prefer-wheels (has-a-wheel subset)"
PREFER="$("$PYGEN" -m pip install --dry-run --ignore-installed --quiet \
    --report /dev/stdout "${DEPS[@]}" \
    | "$PYGEN" -c "
import json, sys
report = json.load(sys.stdin)
wheels, sdists = [], []
for p in report['install']:
    name = p['metadata']['name']
    url = p.get('download_info', {}).get('url', '')
    (wheels if url.endswith('.whl') else sdists).append(name)
print(','.join(sorted(wheels)))
print('SDIST-ONLY:', ','.join(sorted(sdists)), file=sys.stderr)
")"
echo ">> prefer-wheels (has a wheel): $PREFER"

# --- Generate. -o writes python3-deps.yaml (base name + --yaml extension).
# flatpak-pip-generator refuses PySide6 by default, printing "use the baseapp"
# (io.qt.PySide.BaseApp) and exiting 0 without writing. finbreak DELIBERATELY does
# not use the BaseApp — it tops out at Qt 6.10 and forks the correctness-critical
# stack away from the pinned PySide6==6.11.1 the gate tests (FIBR-0159 § 3.1/§ 7).
# This env var is the generator's sanctioned override to pin the PySide6 wheels
# directly on the freedesktop runtime — exactly the chosen design.
export FLATPAK_PIP_GENERATOR_ALLOW_RESTRICTED_MODULES=1

echo ">> running flatpak-pip-generator inside $SDK (PySide6 baseapp override on)"
rm -f "$HERE/python3-deps.yaml"
"$PYGEN" "$GENERATOR" \
    --runtime="$SDK" \
    --prefer-wheels="$PREFER" \
    --wheel-arches=x86_64 \
    --yaml \
    -o "$HERE/python3-deps" \
    "${DEPS[@]}"

# The generator can exit 0 without writing (the baseapp refusal path), so verify.
if [[ ! -f "$HERE/python3-deps.yaml" ]]; then
    echo "!! generator produced no python3-deps.yaml — see its output above" >&2
    exit 1
fi
echo ">> wrote $HERE/python3-deps.yaml ($(grep -c 'sha256' "$HERE/python3-deps.yaml") pinned sources)"
echo ">> review the diff, then rebuild: packaging/flatpak/flatpak-build.sh"
