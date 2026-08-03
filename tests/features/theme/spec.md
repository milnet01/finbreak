# tests/features/theme — FIBR-0127 app-wide theme system

Conformance tests for [`docs/specs/FIBR-0127.md`](../../../docs/specs/FIBR-0127.md).
The app installs a real theme system: a registry of **six** finance-flavoured
themes (three light — Ledger · Parchment · Mint; three dark — Midnight ·
Graphite · Emerald), each defined by eight semantic colour **tokens** + an
`is_dark` flag that expand into a full Qt `QPalette` **and** a polish stylesheet
(gradient/glow accents, grid row-highlighting). A **"Follow system"** mode tracks
the OS light/dark scheme live. The choice is stored **outside the encrypted vault**
(the plaintext window INI, `paths.window_settings_path()`) so it applies to the
first, still-locked window. See [ADR-0010](../../../docs/decisions/0010-theme-system.md).

Pure legs run headless against `ui/theme.py`; the GUI legs drive the shell +
`SettingsDialog` via `qtbot`, under a `theme_isolation` fixture that snapshots &
restores the shared `qapp`'s palette / style / stylesheet (D12 — style restored by
**name**, never the borrowed `QStyle` pointer). No network, no real data.

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-1 | `app.py run()` applies the theme (`ThemeController` + `set_theme(load_theme_pref(), persist=False)`) **before** `MainWindow` is built — the first, still-locked window is themed. Seeds a pinned `"midnight"` pref, monkeypatches `MainWindow` to record the live palette + stylesheet then raise a sentinel; asserts the recorded palette is Midnight's + the stylesheet is non-empty. `run()` reuses the live `QApplication` (re-callable under the pytest-qt app). |
| INV-2 | `load_theme_pref()` / `save_theme_pref()` over the non-vault window INI: absent → `"system"`; a known id round-trips; unknown/garbage → `"system"`. Never the vault. |
| INV-3 | `THEMES` has exactly the six ids; every token set (no `None`); the three light ids are `is_dark=False`, the three dark `is_dark=True`; each theme's `window` lightness `< 0.5` **iff** `is_dark`; `DEFAULT_LIGHT="ledger"` / `DEFAULT_DARK="midnight"` are in the registry. |
| INV-4 | `build_palette(tokens)` maps every token to its Qt role (Window/Button, WindowText/Text/ButtonText/ToolTipText, Base/ToolTipBase, AlternateBase, PlaceholderText + Disabled Text/WindowText, Highlight, Link, Mid/Dark); `HighlightedText` is computed — whichever of near-white / near-black has the higher **WCAG 2.2 contrast ratio** against the accent — exercised on **both** branches via synthetic tokens at the extremes. |
| INV-4a | **The computed `HighlightedText` clears WCAG 2.2 SC 1.4.3 (4.5:1) against its accent on every shipped theme.** The rule was an `accent.lightnessF() < 0.5` branch until FIBR-0204; HSL lightness is not luminance, so a saturated mid-hue accent was classed "dark" and given near-white text it did not contrast — ledger 2.90, parchment 3.82, mint 3.21, emerald 2.63. The test computes the real ratio (linearised channels, luminance coefficients) per theme rather than trusting the branch. |
| INV-4b | **The palette contrast budget (FIBR-0214).** Three binding legs, each a per-theme ratio computed with the real WCAG 2.2 formula: live `muted_text` ≥ 4.5:1 on `window` (its Disabled-group use is exempt, the `QHeaderView::section` / `QTabBar::tab` uses are not — ledger 4.39, parchment 3.36, mint 4.30 before the fix); the `accent` ≥ 3:1 on `window`, since it is the focus ring and the selected-tab underline (ledger 2.87, the other five 3.22-8.25); and `Link` strictly better than the `accent_soft` it replaced (1.36-2.86 → 3.16-8.83 on `base`). The `Link` leg deliberately does **not** assert 4.5:1 — reaching it on the light themes means a link indistinguishable from body text, and every link in the app is non-clickable by design. Input borders (1.27-1.61) and row stripes (1.16-1.27) are knowingly unmet and recorded in FIBR-0127 INV-4b rather than asserted. |
| INV-5 | `build_stylesheet(tokens)` is a non-empty `str` that contains `accent`, `accent_soft`, and `alt_base` hex verbatim; two different themes yield different stylesheets. |
| INV-6 | `set_theme("ledger")` installs Fusion (via a `setStyle` spy — the QSS proxy masks `style().objectName()`), a light palette, a non-empty stylesheet, and emits `themeChanged`; `"midnight"` flips the palette dark. |
| INV-7 | `"system"` resolves `DEFAULT_DARK`/`DEFAULT_LIGHT` by `_current_scheme()` (`Unknown` → dark); the `colorSchemeChanged` slot re-applies live while keeping `current_mode() == "system"` (double-flip); a pinned theme's slot is a no-op. Scheme forced only via the `_current_scheme()` seam. |
| D3 | `set_theme(<unknown id>)` normalises the **mode** to `"system"` and resolves from there. |
| D4 | A failing `save_theme_pref` leaves the theme applied and does **not** raise (best-effort persist). |
| INV-8 | The `settings_theme` combo is immediate-apply: opening Settings with a pinned pref makes **zero** `save_theme_pref` writes and doesn't change the applied palette (connect-after-populate); selecting a theme applies live + persists with **no** Save click. |
| INV-9 | The picker offers `{system + six}` ids, light group before dark, preselected to the current pref; **no** picker without a controller. |
| INV-10 | The toolbar glyphs re-tint on `themeChanged` — a mapped action's icon `cacheKey()` changes light→dark (`_icon_actions` map + `_retint_toolbar_icons`). **Widened by FIBR-0215:** "a mapped action's" was phrased around the gap — it proved the mechanism on `home` while `transactions`, `statements` and `export` had no mapped hue at all, so `toolbar_icon` returned the neutral fallback for them (no `Active` pixmap → no hover-brighten, and a no-op re-tint). Now asserted over the **whole** `_icon_actions` set: nothing in it is missing from `_ICON_HUES`, every glyph's pixmap changes light→dark, and every mapped glyph's `Active` pixmap differs from its `Normal` one. |
| INV-11 | `polish_item_views` enables `alternatingRowColors` on the workspace's table views; a view-less root is a no-op; the stylesheet carries `::item:hover`/`::item:selected` + `accent_soft`. |
| INV-12 | The controller takes no vault/`AuthService` reference and applies cleanly with none in scope. |

INV-13 (i18n) is covered by the existing `ui/*.py` fixed-geometry source-scan
(`ui/settings.py` is in scope) + the review checklist per `coding.md § 5.2`; the
six theme names are data (not `tr()`-wrapped), like currency codes.
