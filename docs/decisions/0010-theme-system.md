# ADR-0010: App-wide theme system — Fusion style + token-driven palettes & stylesheet, non-vault theme preference

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Project lead, Claude
- **Related:** [docs/specs/FIBR-0127.md](../specs/FIBR-0127.md) (the theme
  system this ADR backs), [ADR-0002](0002-pyside6-over-pyqt6.md) (PySide6/LGPL —
  the ADR the theme code **wrongly** cited for its dark default before this one
  existed), [ADR-0007](0007-self-contained-bundled-releases.md) (self-contained
  bundles, minimise dependencies), [ADR-0008](0008-qtcharts-for-reporting.md)
  (the dashboard charts that theme themselves from the live `QPalette`).

## Context

Before FIBR-0127 the app installed **no palette and no stylesheet** — `app.py`
built the `QApplication` and set the app name, desktop file, window icon and
layout direction, but **no palette / style / stylesheet**, so the app rode
whatever the platform / Qt default handed it (dark by convention on the
developer's desktop). Several widgets already **read** the live palette:
`ui/icons.py` tints toolbar glyphs by `_is_dark_theme()` (window-background
lightness `< 0.5`); `ui/charts.py`/`ui/home.py` derive `ChartTheme` colours from
`palette().text()`. There was no `theme` setting, no toggle, and no ADR recording
"the app is dark" — `ui/icons.py`'s comment *"Defaults to dark (ADR-0002)"*
mis-cited ADR-0002, which is actually **PySide6-vs-PyQt6**, not a theme decision.

FIBR-0127 introduces a real theme system with concrete requirements:

- **Multiple named themes** (six, finance-flavoured — three light, three dark),
  not merely a light/dark switch.
- A **"follow system"** mode that tracks the OS light/dark setting and switches
  **live**.
- A **sleek, modern look** — gradient/glow accent borders, row highlighting in
  the grid views.
- **Cross-platform consistency** — the app looks the same on Windows, macOS and
  Linux (ADR-0007 ships it to all three).
- Applied **before unlock** — the very first (still-locked) window is themed.

Options for the mechanism:

- **Native colour-scheme request** — Qt 6.8's
  `QApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark/Light)`. One call,
  no palette to maintain. But it delivers **only light/dark**, not six named
  themes; the exact colours are whatever each OS/style produces (no brand, no
  "dark-theme polish"), and on Linux the result depends on the desktop's theme
  plugin — so it can't meet the requirements.
- **Fusion style + token-driven `QPalette` + `QSS`** — set the built-in **Fusion**
  style (identical rendering on every OS), install a per-theme `QPalette` built
  from a small set of semantic colour **tokens**, plus one token-driven stylesheet
  for the modern polish. Full colour control; a new theme costs ~10 tokens, not a
  wall of code; applicable pre-unlock; live-switchable.
- **Hand-written per-theme QSS files** — maximum control, but every theme is a
  large hand-maintained stylesheet: heavy, error-prone, no shared structure
  (fights the DRY / "shortest correct" house rules).

Where the preference lives:

- **In the encrypted vault `settings` table** (as FIBR-0055's auto-lock timeout
  is) — but the theme must apply on the **first, still-locked** window, before any
  key exists to decrypt the vault. The theme is also **not sensitive**.
- **In the non-vault window INI** (`paths.window_settings_path()`, the same
  plaintext store that already holds window geometry / last-tab / table state) —
  loads before unlock, correct home for non-sensitive UI state.

## Decision

Use **Fusion style + a token-driven `QPalette` and stylesheet**, with a registry
of **six named themes** (Ledger · Parchment · Mint / Midnight · Graphite ·
Emerald). "Follow system" resolves to a default light (**Ledger**) or dark
(**Midnight**) theme via `styleHints().colorScheme()` and re-applies live on the
`colorSchemeChanged` signal. Store the `theme` preference in the **non-vault
window INI**, applied at the `app.py` entry point before the main window is built.
Replace the mis-citation in `ui/icons.py` with a reference to **this** ADR.

Fusion is the only option that keeps the look **identical across Windows / macOS /
Linux** while giving us the colour control the "dark-theme polish" and the named
finance themes require, and the token model keeps each theme cheap enough that six
of them is not a maintenance burden.

## Consequences

**Positive:**

- One consistent look on every OS (ADR-0007's three targets).
- A new theme is ~10 semantic colours; six themes stay maintainable.
- Live theme switching and live follow-system, with no relaunch.
- Applied pre-unlock, so even the locked first-run / unlock window is themed.
- No new runtime dependency — Fusion and `QSS` are built into the bundled Qt.

**Negative:**

- The app now **owns** its palettes + one stylesheet (a real, if small,
  maintenance surface) and **overrides the native OS look** — a deliberate
  trade for cross-platform consistency (some users prefer native chrome).
- Qt has **no CSS `box-shadow`**, so a literal *blurred* glow is not achievable in
  the stylesheet and cannot be applied to individual table rows at all. The
  gradient/glow aesthetic is delivered with **accent gradients** (`qlineargradient`
  fills/borders that intensify on focus/selection); a true blurred halo, if ever
  wanted, is a separate follow-up (`QGraphicsDropShadowEffect` on discrete
  widgets).

**Neutral:**

- Toolbar glyphs re-tint on a theme change via the existing FIBR-0116 tinting
  seam (`toolbar_icon` reads `_is_dark_theme()`); FIBR-0127 wires the live
  re-tint so icons never show stale-theme tones.
- Charts already adapt (they read the live palette), so they follow theme changes
  for free.
- `_amount.py`'s fixed red/green mid-tones (readable on both light and dark) are
  **kept**; per-theme amount re-tinting is deferred (FIBR-0116-adjacent), out of
  this ADR's scope.
