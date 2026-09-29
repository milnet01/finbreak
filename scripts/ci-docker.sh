#!/usr/bin/env bash
# Reproduce the GitHub CI run EXACTLY, locally, in the same container image.
#
# CI (.github/workflows/ci.yml) runs inside `python:3.12-slim-bookworm` and calls
# scripts/ci-setup.sh then scripts/ci-local.sh. This script does the identical
# thing on your machine — same image, same setup script, same gate script — so
# `git push` can't surprise you with an environment failure a configured desktop
# masks (a missing Qt system lib, fresh-install breakage). Run it before pushing.
#
# Needs podman or docker. Extra args pass straight through to ci-local.sh, except
# --build: the container has no container runtime, so the build smoke test would
# skip silently. Run `scripts/ci-local.sh --build` on the host for that.
set -euo pipefail
cd "$(dirname "$0")/.."

for arg in "$@"; do
    if [ "$arg" = "--build" ]; then
        echo "ci-docker.sh: --build cannot run in the container (no podman/docker inside), so the smoke test would skip silently. Run scripts/ci-local.sh --build on the host instead." >&2
        exit 2
    fi
done

runtime="$(command -v podman || command -v docker || true)"
[ -n "$runtime" ] || { echo "ci-docker.sh: need podman or docker on PATH" >&2; exit 1; }

# The container gets the TRACKED files, as they are in your working tree, plus
# .git — never untracked or gitignored ones. GitHub's checkout is a clean clone
# of tracked files with full history (ci.yml, fetch-depth: 0), so a gate stage
# that reads an untracked file (.corpus-numbers, a stray fixture) would pass
# here and meet a different tree there. Streamed in as a tar, so the run never
# writes into your tree (build/, dist/, caches).
#
# `chown` the copy to a foreign uid so the gate (run as root) sees a repo owned
# by someone else — faithfully reproducing GitHub's container checkout, where
# git otherwise trips "dubious ownership". This is what makes ci-setup.sh's
# safe.directory line get exercised locally, not just on CI.
#
# FINBREAK_TEST_WORKERS=4: a GitHub runner gets 4 (ci-local.sh sizes it from
# memory and CPUs, and this desktop would give 6). Which tests share a worker
# still depends on timing, so this narrows the gap rather than closing it; the
# conftest checks for leaked state are what close it. An explicit
# FINBREAK_TEST_WORKERS on the host still wins.
#
# The image is python:3.12-slim-bookworm, pinned by digest to match ci.yml
# (FIBR-0345; harness INV-6). podman refuses tag+digest together.
git ls-files -z | tar -c --null -T - .git | "$runtime" run --rm -i \
    -e FINBREAK_TEST_WORKERS="${FINBREAK_TEST_WORKERS:-4}" \
    docker.io/library/python@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e \
    bash -c 'mkdir /work && tar -x -C /work && chown -R 1001:1001 /work && cd /work && ./scripts/ci-setup.sh && ./scripts/ci-local.sh "$@"' _ "$@"
