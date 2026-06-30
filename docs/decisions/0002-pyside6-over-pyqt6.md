# ADR-0002: PySide6 over PyQt6

- **Status:** Accepted
- **Date:** 2026-06-30
- **Deciders:** Project lead, Claude
- **Related:** [docs/discovery.md](../discovery.md) (tech stack), [ADR-0004](0004-qt-native-pdf-over-weasyprint.md) (also Qt-stack-dependent)

## Context

finbreak is a Qt-based desktop app distributed publicly — Windows `.exe`,
macOS `.app`, Linux AppImage, and a Flatpak on Flathub. Qt for Python ships in
two bindings:

- **PyQt6** (Riverbank) — **GPL v3** or a paid commercial licence. Linking it
  into a distributed binary makes the combined work GPL. The project's own
  licence is MIT; shipping MIT source whose binaries are effectively GPL is
  inconsistent and constrains downstream reuse.
- **PySide6** (the Qt Company, official) — **LGPL v3**. Permits distributing our
  binaries under our own MIT licence provided the (dynamically linked) Qt
  libraries remain replaceable, which bundlers like PyInstaller satisfy.

The user's other app (Music_Production) uses PyQt6, so there is muscle-memory
cost to switching. The APIs are nearly identical (enum scoping, a few signal
names, `Signal`/`Slot` vs `pyqtSignal`/`pyqtSlot`).

## Decision

Use **PySide6** (LGPL) for the GUI.

## Consequences

**Positive:**

- Binaries can be distributed under MIT on Flathub and the storefronts without
  copyleft entanglement.
- PySide6 is the Qt Company's official binding, tracking current Qt 6 idioms.

**Negative:**

- Minor divergence from the user's PyQt6 habit; a handful of API differences to
  watch (signal/slot decorators, `QtCharts` import path).
- LGPL imposes a relinking obligation — satisfied by the standard dynamic-link
  bundling our packagers already do, but it must not be defeated (no fully
  static, non-replaceable Qt link).

**Neutral:**

- Either binding would function technically; this is a licensing-driven choice,
  not a capability one.
