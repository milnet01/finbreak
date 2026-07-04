#!/usr/bin/env bash
# finbreak CI environment preparation — single source of truth (FIBR-0001 INV-2).
#
# Installs everything the gate (scripts/ci-local.sh) needs but does NOT itself
# provide: the OS libraries PySide6 dlopens at runtime, the gitleaks binary, and
# the Python dependency groups. BOTH .github/workflows/ci.yml AND
# scripts/ci-docker.sh call this exact script, so a local containerised run and
# the GitHub run install an identical environment — they cannot drift. That
# closes the gap that let CI go red while the local gate stayed green: a desktop
# already has the Qt libraries; a clean CI runner does not.
#
# Assumes a Debian/Ubuntu apt system with python3.12 + pip present — the
# `python:3.12-slim-bookworm` image both CI and ci-docker.sh run in provides
# them. Runs as root in that container; falls back to sudo on a normal host.
set -euo pipefail

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"
export DEBIAN_FRONTEND=noninteractive

echo "== apt: system libraries + tooling =="
$SUDO apt-get update -qq
# PySide6's wheel bundles the Qt libraries but NOT their OS dependencies; Qt
# dlopens these even under QT_QPA_PLATFORM=offscreen. This is the empirically
# verified minimal set for `python -m finbreak --self-test` to load Qt (probed
# in the exact image): libgl/libegl (GL), libfontconfig (+freetype, pulled in),
# libglib (QtCore event loop), libxkbcommon (QtGui), libdbus (QtGui/QtDBus).
# Missing any one → `FINBREAK_SELFTEST_FAIL: qt`. If a future PySide6 bump needs
# another lib, add it here (and only here — CI and ci-docker.sh both read it).
# git is a RUNTIME dependency of the gate, not just of checkout: the gitignore
# and bundling feature tests shell out to `git check-ignore` / `git rev-parse`.
$SUDO apt-get install -y --no-install-recommends \
    curl ca-certificates git \
    libgl1 libegl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 libfontconfig1

# The gate's feature tests run `git` against the checkout. In a container the
# checkout is usually owned by a different uid than the user running the gate,
# so git 2.35.2+ refuses with "detected dubious ownership" (exit 128). Trust the
# workspace explicitly — standard for ephemeral CI containers, and harmless on a
# developer's own repo.
git config --global --add safe.directory '*'

echo "== gitleaks (a Go binary, not a pip package) =="
GITLEAKS_VERSION=8.30.1
curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
    | tar -xz -C /tmp gitleaks
$SUDO install -m 0755 /tmp/gitleaks /usr/local/bin/gitleaks
gitleaks version

echo "== python: dev group + runtime deps =="
# PEP 735 `--group` needs pip >= 25.1; the base image's pip may be older.
python -m pip install --quiet --root-user-action=ignore --upgrade pip
python -m pip install --quiet --root-user-action=ignore --group dev
# Runtime deps from pyproject (PySide6, sqlcipher3-binary, pikepdf, argon2-cffi,
# ofxparse) — installed via `pip install .` so this list can never drift; the
# self-test guard (FIBR-0003 INV-6) + the feature suites import them in the gate.
python -m pip install --quiet --root-user-action=ignore .

echo "CI environment ready."
