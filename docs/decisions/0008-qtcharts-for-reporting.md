# ADR-0008: QtCharts for the reporting dashboard charts

- **Status:** Accepted
- **Date:** 2026-07-12
- **Deciders:** Project lead, Claude
- **Related:** [docs/design.md](../design.md) (the Dashboard + ReportingService
  components and the explicit "chart library chosen at the dashboard spec"
  hand-off), [docs/specs/FIBR-0012.md](../specs/FIBR-0012.md) (this dashboard),
  [ADR-0002](0002-pyside6-over-pyqt6.md) (PySide6/LGPL), [ADR-0004](0004-qt-native-pdf-over-weasyprint.md)
  (the Qt-native PDF engine the charts must later render into),
  [ADR-0007](0007-self-contained-bundled-releases.md) (self-contained bundles,
  minimise dependencies).

## Context

The Home dashboard (FIBR-0012) draws two charts: a **spending-by-category
donut** and a **month-to-month income-vs-expenditure trend**. `design.md`
deferred the charting-library choice to this dashboard phase with three
candidates and two hard requirements: the library must be **dark-themeable** and
must be able to **render into the locked PDF export** (FIBR-0013), which uses the
Qt-native `QPdfWriter` engine (ADR-0004).

Options:

- **QtCharts** — a first-party Qt 6 module. Ships **inside PySide6** (verified:
  `PySide6.QtCharts` imports on the pinned 6.11.1), so it adds **no new runtime
  dependency**. Same LGPL licence as the rest of PySide6 (ADR-0002). Paints with
  `QPainter`, the identical engine that drives `QPdfWriter` — so a chart can be
  rendered onto the PDF page device directly, no second rasteriser. Themed via
  the app's own `QPalette` (ADR-0002 dark default). Embeds as a `QWidget`
  (`QChartView`) straight into the existing layouts.
- **matplotlib** — the richest static-charting library, but drags in heavy
  transitive dependencies (NumPy and friends), inflating every PyInstaller /
  AppImage / Flatpak bundle (against ADR-0007); its Qt canvas embedding is
  awkward and its own styling system fights the app's dark palette; PDF output is
  a separate backend, not the app's Qt engine.
- **pyqtgraph** — lightweight-ish and fast, but built for **real-time /
  scientific** plotting; weaker fit for static financial charts and for
  high-quality vector PDF output, and still a **new dependency**.

## Decision

Use **QtCharts** (`PySide6.QtCharts`) for the dashboard charts.

It is the only candidate that keeps the app's "self-contained, no new
dependency" promise (ADR-0007) — it is already present in the bundled PySide6 —
**and** shares the `QPainter`/`QPdfWriter` engine (ADR-0004), so the same chart
objects the dashboard shows on screen can later be painted into the locked PDF
export (FIBR-0013) with no additional charting stack.

## Consequences

**Positive:**

- Zero new runtime dependency; no new licence obligation (LGPL, same as PySide6).
- Native dark theming through the existing `QPalette`.
- One rendering engine for screen **and** PDF — FIBR-0013 reuses these chart
  objects instead of introducing a parallel renderer.
- GUI tests can assert against the live `QChart` model (series, slices, bar-set
  values) with the existing `qtbot` fixture.

**Negative:**

- QtCharts' built-in chart *themes* are a fixed set; matching the app's exact
  dark palette means setting colours from the `QPalette` explicitly rather than
  taking a canned theme (a small, contained styling cost, FIBR-0012 D9).
- Fewer exotic chart types than matplotlib — irrelevant here (a donut and a
  grouped bar chart are both first-class QtCharts series).

**Neutral:**

- The `QtCharts` module must travel into the Python-free frozen bundle. Importing
  it from application code makes the PySide6 PyInstaller hook include the
  `Qt6Charts` shared library; FIBR-0012 adds a `PySide6.QtCharts` import leg to
  the `--self-test` native-stack check (the FIBR-0003 bundle-travel proof) so a
  missing `Qt6Charts` fails the build smoke, not a user's launch.
