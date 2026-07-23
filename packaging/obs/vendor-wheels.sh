#!/bin/sh
# Vendor the offline wheel closure for the OBS build (FIBR-0155 § 3.6).
#
# OBS build roots are network-isolated, so finbreak's full dependency closure is
# vendored into vendor.tar.gz (the .spec/debian Source1) and installed at build
# time with `pip --no-index --find-links vendor/`. Run this on a Linux x86_64
# host with glibc >= 2.34, from the repo root, then `osc add vendor.tar.gz`.
#
# One wheel set per CPython ABI our build targets default to:
#   cp312 -> Ubuntu 24.04
#   cp313 -> openSUSE Tumbleweed, Debian 13
#   cp314 -> Fedora 44
# Extend the PY list below whenever a target ships a newer default python3.
# NO single --platform tag, so host resolution infers the full manylinux cascade
# (the correctness-critical wheels are tagged lower than manylinux_2_34). The
# freezer + its recursive closure come too (not --no-deps).
#
# ofxparse ships as an sdist ONLY (no wheel on PyPI), so --only-binary=:all:
# cannot resolve it and would abort the whole download (taking its own deps
# lxml + six down with it). It is pre-built into a universal py3 wheel first,
# then offered via --find-links so the binary-only closure resolves cleanly.
set -eu

DEPS="$(mktemp)"
trap 'rm -f "$DEPS"' EXIT
python3 -c "import tomllib; print(chr(10).join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > "$DEPS"

rm -rf vendor && mkdir vendor
python3 -m pip wheel --no-deps ofxparse==0.21 -w vendor
for PY in 3.12 3.13 3.14; do
    python3 -m pip download --only-binary=:all: --python-version "$PY" \
        --find-links vendor -d vendor -r "$DEPS" pyinstaller==6.21.0
done
tar caf vendor.tar.gz vendor/
echo "vendor.tar.gz written ($(find vendor -name '*.whl' | wc -l) wheels)"
