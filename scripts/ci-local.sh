#!/usr/bin/env bash
# finbreak local quality + security gate (FIBR-0001 INV-1).
#
# One command, all gates, cheapest-first. .github/workflows/ci.yml installs the
# dev dependency group and gitleaks, then invokes THIS script rather than
# re-listing the stages — so the gate list has a single source of truth and CI
# and local runs cannot drift (INV-2).
#
# Assumes the environment scripts/ci-setup.sh builds (CLAUDE.md "Build and
# test" documents it for humans): the `dev` dependency group AND the runtime
# deps (pip install .) — mypy type-checks tests/ without ignoring PySide6, and
# conftest imports PySide6 at collection time, so the mypy and pytest stages are
# red with the dev group alone (named, not numbered: this comment used to say
# "stages 8 and 9" and the numbers rotted the moment a stage was inserted above
# them). gitleaks, shellcheck, actionlint and zizmor are separate
# binaries, not pip packages, and must be on PATH; ci-setup.sh pins all four.
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

# The gate's own delivery machinery was the one part of the repo nothing checked:
# every shell script plus 3 workflows, none linted. A bug in release-linux.sh or
# packaging/obs/obs-submit.sh ships a broken release, and the Python stages above
# cannot see it (ruff/bandit/mypy/pytest all scope to src/tests). All clean as of
# adding this, so it is a regression guard, not a backlog.
#
# Selected via `git ls-files`, NOT a fixed glob: the first cut of this stage used
# `scripts/*.sh` and silently missed the 7 packaging recipes under packaging/obs/
# and packaging/flatpak/ — i.e. exactly the publish path it claimed to cover. A
# directory glob has to be widened by hand every time scripts appear somewhere
# new, and nothing tells you it went stale. The hook has no .sh suffix, so it is
# named separately.
echo "== shellcheck =="
mapfile -t SH_FILES < <(git ls-files '*.sh')
shellcheck "${SH_FILES[@]}" .githooks/pre-push

# Also pipes every workflow `run:` block through shellcheck (installed above) —
# shell bugs inside YAML that the stage above never sees, because it is not
# looking at .yml. Auto-discovers .github/workflows/.
echo "== actionlint =="
actionlint

# The supply-chain half actionlint does not cover: a `uses:` pinned to a mutable
# tag, `${{ }}` interpolation reaching a `run:` block, over-broad `permissions:`,
# a checkout persisting its token. The tree was made clean first (FIBR-0226 pinned
# all 6 `uses:` to commit SHAs and set persist-credentials: false) and the stage
# added after — a stage that is red on day one is a broken build, not a gate.
# Default persona, and offline by default: no network, so it cannot flake.
echo "== zizmor =="
zizmor .github/workflows/

echo "== bandit =="
bandit -c pyproject.toml -r src -q

# Two pip-audit stages, and the second is not redundant: the default `-s pypi`
# reads the PyPI Advisory Database, `-s osv` queries OSV.dev. Different
# databases, neither a superset — only OSV.dev imports the OpenSSF Malicious
# Packages feed, i.e. the hijacked or typosquatted release that carries no CVE
# and that a CVE-only view structurally cannot see. Worth a second stage for a
# project that ships signed desktop binaries. Both were verified green on this
# tree, and `-s osv` verified red against a known-vulnerable pin, before this
# landed. The accepted cost is a SECOND network-dependent stage on a gate that
# runs on every push (~28s); if the flake rate becomes annoying, dropping the
# osv stage again is a legitimate outcome, not a regression.
echo "== pip-audit (pypi) =="
pip-audit

echo "== pip-audit (osv) =="
pip-audit -s osv

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
