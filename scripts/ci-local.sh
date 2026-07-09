#!/usr/bin/env bash
# finbreak local quality + security gate (FIBR-0001 INV-1).
#
# One command, all gates, cheapest-first. .github/workflows/ci.yml installs the
# dev dependency group and gitleaks, then invokes THIS script rather than
# re-listing the stages — so the gate list has a single source of truth and CI
# and local runs cannot drift (INV-2).
#
# Assumes the `dev` dependency group is installed (see CLAUDE.md "Build and
# test": python -m pip install --group dev). gitleaks is a separate binary, not
# a pip package, and must be on PATH.
#
# FIBR-0003 later appends a build smoke-test stage to this same script.
#
# Exits non-zero on the first failing stage.
set -euo pipefail

cd "$(dirname "$0")/.."

# FIBR-0003: opt in the slow build + clean-room integration test. Off by default
# so the everyday gate stays fast; `--build` (or FINBREAK_BUILD_SMOKE=1 in the
# environment) turns it on, and the dedicated build-smoke CI job passes --build.
# The test lives in tests/features/bundling/ and self-skips unless the flag is
# set, so the normal `pytest` stage below runs it only when opted in.
if [ "${1:-}" = "--build" ]; then
    export FINBREAK_BUILD_SMOKE=1
fi

echo "== ruff check =="
ruff check src tests

echo "== ruff format --check =="
ruff format --check src tests

echo "== bandit =="
bandit -c pyproject.toml -r src -q

echo "== pip-audit =="
pip-audit

echo "== gitleaks =="
gitleaks dir . --no-banner --redact --config .gitleaks.toml

echo "== mypy =="
mypy

if [ "${FINBREAK_BUILD_SMOKE:-}" = "1" ]; then
    echo "== pytest (excluding perf; +build smoke-test) =="
else
    echo "== pytest (excluding perf) =="
fi
pytest -m "not perf"

echo "All gates passed."
