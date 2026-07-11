#!/usr/bin/env bash
# FIBR-0054 Phase 1, Deliverable 5 — build + sign the REAL release AppImage.
#
# A thin, ergonomic entry point over the FIBR-0003 build-smoke machinery in
# `--release` mode: it freezes the GUI entry (the same frozen binary the
# self-test smoke uses — `--self-test` is only a runtime arg), names it
# finbreak-<version>-x86_64.AppImage with real desktop metadata + the app icon,
# proves it launches in a Python-free clean-room container (INV-15), then signs
# it with the release key (INV-14).
#
# Prerequisites:
#   - podman or docker on PATH (the container build/clean-room);
#   - the project venv ACTIVE (`. .venv/bin/activate`) so the signing step can
#     import cryptography;
#   - a signing key at release/finbreak-signing.key (run scripts/gen-signing-key.py
#     once first) or $FINBREAK_SIGNING_KEY — without it the AppImage builds but is
#     left unsigned, with a warning.
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/build-smoke.sh" --release "$@"
