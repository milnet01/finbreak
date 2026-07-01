#!/usr/bin/env bash
# Reproduce the GitHub CI run EXACTLY, locally, in the same container image.
#
# CI (.github/workflows/ci.yml) runs inside `python:3.12-slim-bookworm` and calls
# scripts/ci-setup.sh then scripts/ci-local.sh. This script does the identical
# thing on your machine — same image, same setup script, same gate script — so
# `git push` can't surprise you with an environment failure a configured desktop
# masks (a missing Qt system lib, fresh-install breakage). Run it before pushing.
#
# Needs podman or docker. Extra args pass straight through to ci-local.sh, e.g.
#   scripts/ci-docker.sh --build      # also run the FIBR-0003 build smoke-test
set -euo pipefail
cd "$(dirname "$0")/.."

runtime="$(command -v podman || command -v docker || true)"
[ -n "$runtime" ] || { echo "ci-docker.sh: need podman or docker on PATH" >&2; exit 1; }

# Mount the checkout read-only and work on a copy inside the container, so the
# run never writes into your tree (build/, dist/, caches). --security-opt
# label=disable is required for bind-mount reads under SELinux/podman on this
# host (same as scripts/build-smoke.sh).
#
# `chown` the copy to a foreign uid so the gate (run as root) sees a repo owned
# by someone else — faithfully reproducing GitHub's container checkout, where
# git otherwise trips "dubious ownership". This is what makes ci-setup.sh's
# safe.directory line get exercised locally, not just on CI.
exec "$runtime" run --rm -t --security-opt label=disable \
    -v "$PWD":/repo:ro \
    docker.io/library/python:3.12-slim-bookworm \
    bash -c 'cp -a /repo /work && chown -R 1001:1001 /work && cd /work && ./scripts/ci-setup.sh && ./scripts/ci-local.sh "$@"' _ "$@"
