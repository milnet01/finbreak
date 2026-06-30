# ADR-0007: Self-contained bundled releases (no runtime prerequisites)

- **Status:** Accepted
- **Date:** 2026-06-30
- **Deciders:** Project lead, Claude
- **Related:** [docs/discovery.md](../discovery.md) (success criterion 6), [ADR-0002](0002-pyside6-over-pyqt6.md), [ADR-0003](0003-sqlcipher-local-only-storage.md), [ADR-0004](0004-qt-native-pdf-over-weasyprint.md)

## Context

The target users are non-technical and on any platform. A release that says
"install Python 3, then `pip install …`" is a non-starter — it would fail the
first user. The requirement: **download one file, run it, it works**, on a clean
machine with nothing pre-installed.

The app is Python (PySide6) with several **native** dependencies — SQLCipher
(encrypted DB), Qt's own libraries and plugins, and qpdf (behind `pikepdf`).
Bundling pure-Python code is easy; the risk is shipping a bundle that silently
omits a native library and only runs on the build machine.

Options for "self-contained":

- **System-Python + requirements** — rejected outright (prerequisites).
- **PyInstaller** (Windows/macOS) — freezes the interpreter + dependencies into
  a standalone `.exe` / `.app`.
- **AppImage** (Linux) — a portable single file embedding the interpreter and
  libraries; runs without installation.
- **Flatpak/Flathub** (Linux stores) — sandboxed, ships against the Freedesktop
  runtime; fully self-contained from the user's view.

## Decision

Every release is **fully self-contained**: PyInstaller for Windows/macOS,
AppImage for portable Linux, and Flatpak on Flathub. Each artifact bundles the
CPython runtime and **all** dependencies, including the native ones. The
packaging spec's **exit criterion** is a successful launch on a clean
VM/container with **no Python installed**; that check gates every release.

## Consequences

**Positive:**

- Users download and run — no toolchain, no prerequisites, no support burden
  from missing dependencies.

**Negative:**

- Larger artifacts (tens of MB) — acceptable for a desktop app.
- The build must explicitly collect native libs/plugins (SQLCipher, Qt
  platform/SQL/imageformat plugins, qpdf); these need PyInstaller hooks /
  AppImage recipe entries and are the main packaging risk.
- AppImage must be built on an **old base image** so its glibc stays compatible
  with older target distros.
- A real build matrix (one runner per OS) is required in CI.

**Neutral:**

- Reinforces ADR-0004 (Qt-native PDF avoids WeasyPrint's hard-to-bundle native
  stack) and constrains future dependency choices: a new dependency must be
  bundleable on all three platforms.
