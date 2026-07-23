#!/bin/sh
# obs-setup.sh (FIBR-0155) — create/update the OBS sub-project + package.
#
# One-time (idempotent) setup: writes the home:milnet:finbreak project meta with
# finbreak's build targets (x86_64 only), then creates the finbreak package.
# Re-running just re-applies the meta, so it doubles as "add/remove a target"
# (edit the repository list below, re-run).
#
# Needs: osc, and an authenticated OBS account (run any osc command once to log
# in). Override the defaults via env vars: OBS_API, OBS_PROJECT, OBS_PACKAGE,
# OBS_USER.
set -eu

API="${OBS_API:-https://api.opensuse.org}"
PROJ="${OBS_PROJECT:-home:milnet:finbreak}"
PKG="${OBS_PACKAGE:-finbreak}"
USER="${OBS_USER:-milnet}"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# Build targets — x86_64 only (the bundled wheels are 64-bit). Add Leap 15.6 /
# more Fedora versions here once their recipe branches exist.
cat > "$tmp/prj.xml" <<EOF
<project name="$PROJ">
  <title>finbreak</title>
  <description>Encrypted, offline-first personal-finance desktop app (SQLCipher-backed AES-256 vault). Native RPM/deb packaging from a pinned, bundled runtime.</description>
  <person userid="$USER" role="maintainer"/>
  <repository name="openSUSE_Tumbleweed">
    <path project="openSUSE:Factory" repository="snapshot"/>
    <arch>x86_64</arch>
  </repository>
  <!-- openSUSE Leap 15.6 deferred (FIBR-0160): it ships no python 3.12+, so the
       cp312/cp313/cp314 wheels can't resolve. Re-add once its python module +
       ABI are vendored. -->
  <repository name="Fedora_44">
    <path project="Fedora:44" repository="standard"/>
    <arch>x86_64</arch>
  </repository>
  <repository name="Debian_13">
    <path project="Debian:13" repository="standard"/>
    <arch>x86_64</arch>
  </repository>
  <repository name="xUbuntu_24.04">
    <path project="Ubuntu:24.04" repository="universe"/>
    <arch>x86_64</arch>
  </repository>
</project>
EOF
echo ">>> applying project meta: $PROJ"
osc -A "$API" meta prj "$PROJ" -F "$tmp/prj.xml"

cat > "$tmp/pkg.xml" <<EOF
<package name="$PKG" project="$PROJ">
  <title>finbreak</title>
  <description>Encrypted, offline-first personal-finance desktop app.</description>
</package>
EOF
echo ">>> applying package meta: $PROJ/$PKG"
osc -A "$API" meta pkg "$PROJ" "$PKG" -F "$tmp/pkg.xml"

echo "OK — $PROJ/$PKG ready. Next: packaging/obs/obs-submit.sh"
