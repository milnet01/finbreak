# ADR-0004: Qt-native PDF engine over WeasyPrint

- **Status:** Accepted
- **Date:** 2026-06-30
- **Deciders:** Project lead, Claude
- **Related:** [docs/discovery.md](../discovery.md), [ADR-0002](0002-pyside6-over-pyqt6.md)

## Context

finbreak exports a shareable report as PDF, and must build cleanly into a
single bundle on Windows, macOS, and Linux (AppImage + Flatpak). The renderer
choice strongly affects packaging:

- **WeasyPrint** (HTML/CSS → PDF) produces beautiful output but depends on
  native graphics libraries (GTK, Pango, cairo, GDK-Pixbuf, HarfBuzz). On
  Windows and macOS these are painful to bundle and a frequent source of
  broken installs. It was the initial pick (matching Music_Production, a
  Linux-only app) before cross-platform distribution became a requirement.
- **ReportLab** — pure Python, trivially bundled, but a low-level imperative
  drawing API.
- **Qt's own PDF engine** (`QTextDocument` rendered through `QPdfWriter`, or
  `QPainter`) — Qt is already a dependency and already bundled cross-platform,
  so this adds **zero** new native dependencies. It accepts a rich-text/HTML
  subset for layout and renders charts (QtCharts/`QPixmap`) into the same
  document.

## Decision

Render the PDF report with the **Qt PDF engine** (`QTextDocument` +
`QPdfWriter`), then encrypt the result with `pikepdf` (AES-256). Drop WeasyPrint.

## Consequences

**Positive:**

- No extra native dependencies → clean PyInstaller/AppImage/Flatpak builds.
- One rendering toolkit (Qt) for both on-screen charts and the PDF, so the
  report looks like the app.

**Negative:**

- Qt's HTML/CSS subset is narrower than WeasyPrint's; complex layouts need more
  manual work (acceptable for a finance summary).
- Chart images must be rendered to a pixmap and embedded, rather than flowing as
  HTML.

**Neutral:**

- `pikepdf` remains the encryption/decryption layer regardless of renderer, so
  the password-protection path is unchanged.
