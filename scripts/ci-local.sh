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

# `--docs`: the checks a push that changes only .md files still owes (FIBR-0373;
# CLAUDE.md § Doc-only pushes). .githooks/pre-push picks it for such a push.
# DOCS_SUITES is every suite that reads a tracked doc's contents or requires
# one to exist; tests/features/prose_checks/ holds the ledger it must match,
# and fails if a new suite is sorted into neither list.
DOCS_SUITES=(
    tests/features/account_detect/
    tests/features/harness/
    tests/features/release_integrity/
    tests/features/flatpak_packaging/
    tests/features/prose_checks/
)
if [ "${1:-}" = "--docs" ]; then
    echo "== [docs] pytest: the suites that read prose =="
    pytest -q "${DOCS_SUITES[@]}"
    echo "== [docs] gitleaks =="
    gitleaks dir . --no-banner --redact --config .gitleaks.toml
    echo "Documentation checks passed."
    exit 0
fi

# The two pip-audit stages spend their time waiting on the network (~57s here,
# one after the other), so they start now and run alongside every other stage;
# their results are read at the end, where each still fails the gate on its own
# (FIBR-0373). The EXIT trap stops them if an earlier stage fails first.
AUDIT_DIR=$(mktemp -d)
# Nothing in here may fail: a failing command in an EXIT trap replaces the
# gate's own exit status (a finished job leaves `kill` nothing to kill).
PYPI_PID=""
OSV_PID=""
stop_audits() {
    for pid in "$PYPI_PID" "$OSV_PID"; do
        if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; fi
    done
    rm -rf "$AUDIT_DIR"
}
trap stop_audits EXIT
# Audit the installed set WITHOUT finbreak itself (FIBR-0372). finbreak is not
# on PyPI, so pip-audit's lookup of it can only answer "not found" -- or fail:
# a PyPI "503 Backend is unhealthy" on that one URL failed CI and three pushes
# on 2026-09-28. The frozen list is exactly the environment minus finbreak
# (compared package by package: 72 of 73, the one missing being finbreak), and
# --no-deps --disable-pip audits it as pinned, with no resolver run.
pip freeze --all --exclude finbreak > "$AUDIT_DIR/requirements.txt"
pip-audit -r "$AUDIT_DIR/requirements.txt" --no-deps --disable-pip > "$AUDIT_DIR/pypi" 2>&1 &
PYPI_PID=$!
pip-audit -s osv -r "$AUDIT_DIR/requirements.txt" --no-deps --disable-pip > "$AUDIT_DIR/osv" 2>&1 &
OSV_PID=$!

# `src tests`, not the whole tree, and that is a decision rather than an
# oversight. The one tracked .py outside it is a captured reproduction script
# under docs/reviews/ — evidence of a defect, kept exactly as it was run. It is
# imported by nothing and shipped in nothing, and linting it would invite
# tidying edits that destroy the thing it is kept for (FIBR-0328).
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
# runs on every push (~28s, overlapped with the other stages since FIBR-0373);
# if the flake rate becomes annoying, dropping the
# osv stage again is a legitimate outcome, not a regression.
# Started at the top of the script; their results are read at the end.

echo "== gitleaks =="
gitleaks dir . --no-banner --redact --config .gitleaks.toml

echo "== mypy =="
mypy

# Tests run on several processes (pytest-xdist, FIBR-0373): 193s -> ~45s here.
# The worker count is sized from MEMORY, not CPUs (local-gate.md § 9): a worker
# peaks near 0.7 GB, so one per free GiB, never more than the CPUs, and at most
# 6 so a push leaves the rest of this shared desktop usable. A GitHub runner
# (4 CPUs, 16 GB) gets 4. FINBREAK_TEST_WORKERS overrides it; 0 runs in one
# process. Anything unreadable falls back to 1 worker, never to skipping tests.
if [ -n "${FINBREAK_TEST_WORKERS:-}" ]; then
    WORKERS=$FINBREAK_TEST_WORKERS
else
    CPUS=$(nproc 2>/dev/null || echo 1)
    MEM_GIB=$(awk '/^MemAvailable:/ { print int($2 / 1048576) }' /proc/meminfo 2>/dev/null || true)
    WORKERS=${MEM_GIB:-1}
    [ "$WORKERS" -gt "$CPUS" ] && WORKERS=$CPUS
    [ "$WORKERS" -gt 6 ] && WORKERS=6
    [ "$WORKERS" -lt 1 ] && WORKERS=1
fi
case "$WORKERS" in
    '' | *[!0-9]*) echo "FINBREAK_TEST_WORKERS must be a whole number, got '$WORKERS'" >&2; exit 2 ;;
esac

if [ "${FINBREAK_BUILD_SMOKE:-}" = "1" ]; then
    echo "== pytest (excluding perf; +build smoke-test; $WORKERS workers) =="
else
    echo "== pytest (excluding perf; $WORKERS workers) =="
fi
# -rs lists every skip with its reason, so a local log and a GitHub log can be
# compared test by test rather than by a count.
pytest -m "not perf" -n "$WORKERS" -rs

# A non-zero `wait` would end the script under `set -e` before the output
# printed, so the status is captured first and the output shown either way.
echo "== pip-audit (pypi) =="
rc=0; wait "$PYPI_PID" || rc=$?
cat "$AUDIT_DIR/pypi"
[ "$rc" -eq 0 ] || exit "$rc"

echo "== pip-audit (osv) =="
rc=0; wait "$OSV_PID" || rc=$?
cat "$AUDIT_DIR/osv"
[ "$rc" -eq 0 ] || exit "$rc"

echo "All gates passed."
