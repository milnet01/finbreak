#!/usr/bin/env python3
"""Render finbreak marketing screenshots from a throwaway demo vault (FIBR-0082).

Seeds a synthetic vault (scripts/seed_demo_vault.py) entirely in a temp dir, then
grabs the main window on each tab, in each requested theme, straight to PNG — no
display, no real data, fully reproducible. The charts render offscreen exactly as
the PDF export already does (services/pdf_export.py).

    python scripts/capture_screenshots.py                       # dark + light
    python scripts/capture_screenshots.py --themes midnight     # one theme
    python scripts/capture_screenshots.py --out /tmp/shots

Output: <out>/<theme>/<screen>.png (screens: dashboard, transactions, accounts,
categories, rules, transfers, recurring) plus a curated mixed-theme <out>/site/
set for the metainfo + website. The demo vault is kept (git-ignored) for reuse;
all other app state lives in a throwaway temp dir, so the real config is untouched.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Isolate ALL app state to a throwaway dir and force offscreen rendering BEFORE
# anything imports Qt (QStandardPaths / the platform plugin read these at import).
_TMP = Path(tempfile.mkdtemp(prefix="finbreak-shots-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
for _var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
    os.environ[_var] = str(_TMP / _var.lower())

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))  # `import finbreak` from a checkout
sys.path.insert(0, str(Path(__file__).resolve().parent))  # `import seed_demo_vault`

from datetime import date  # noqa: E402 — must follow the env setup above

import seed_demo_vault  # noqa: E402
from PySide6.QtCharts import QChart, QChartView  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from finbreak.services.auth import AuthService  # noqa: E402
from finbreak.ui.main_window import MainWindow  # noqa: E402
from finbreak.ui.theme import DEFAULT_DARK, DEFAULT_LIGHT, ThemeController  # noqa: E402

# (filename, workspace tab index) — the tab order is fixed (main_window INV-1).
# Statements (index 2) is omitted: it only populates via statement import, which
# this direct-repository seed doesn't drive, so its shot would be empty (a
# populated Statements shot is a FIBR-0082 follow-up via the import path).
_SCREENS = [
    ("dashboard", 0),
    ("transactions", 1),
    ("accounts", 3),
    ("categories", 4),
    ("rules", 5),
    ("transfers", 6),
    ("recurring", 7),
]

# The curated set that ships to Flathub metainfo + the website: a deliberate MIX
# of dark (midnight) and light (ledger) to show off the theming, one shot per
# headline feature. Copied to <out>/site/<hosted-name> with the exact filenames
# the metainfo <image> URLs reference (antsprojectshub.co.za/img/finbreak/…).
_SITE_SET = [
    ("dashboard.png", "midnight", "dashboard"),
    ("transactions.png", "ledger", "transactions"),
    ("categories.png", "midnight", "categories"),
    ("recurring.png", "ledger", "recurring"),
    ("transfers.png", "midnight", "transfers"),
    ("rules.png", "ledger", "rules"),
]


def _settle(app: QApplication) -> None:
    """Pump the event loop so offscreen layout + a final (non-animated) paint land."""
    for _ in range(8):
        app.processEvents()


def _freeze_charts(window: MainWindow) -> None:
    """Kill Qt Charts' entry animation so a grab catches the final frame, not a
    mid-animation one (the charts are rebuilt on each tab refresh)."""
    for view in window.findChildren(QChartView):
        chart = view.chart()
        if chart is not None:
            chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(_ROOT / "assets" / "screenshots"))
    parser.add_argument("--themes", default=f"{DEFAULT_DARK},{DEFAULT_LIGHT}")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument(
        "--vault-dir",
        default=str(_ROOT / ".demo-vault"),
        help="where to keep the synthetic demo vault (git-ignored; kept after the "
        "run so it can be reused; re-seeded fresh each time).",
    )
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    theme = ThemeController(app)

    # Keep the demo vault at a stable, git-ignored path (not a throwaway temp dir)
    # so it survives for a future re-capture. first_run needs a clean slate, so
    # clear any prior vault files first (the whole set: db + sidecar + SQLite WAL).
    vault_dir = Path(args.vault_dir)
    vault_dir.mkdir(parents=True, exist_ok=True)
    vault = vault_dir / "vault.db"
    sidecar = vault_dir / "vault.kdf.json"
    for stale in (sidecar, *vault_dir.glob("vault.db*")):
        stale.unlink(missing_ok=True)
    auth = AuthService(vault, sidecar)
    auth.first_run(bytearray(b"demo-passphrase"), "ZAR")
    seed_demo_vault.seed(auth, today=date.today())

    window = MainWindow(auth, theme_controller=theme)
    window.resize(args.width, args.height)
    window._enter_unlocked()  # builds the tabbed workspace (as a real unlock does)
    window.show()
    _settle(app)

    out_root = Path(args.out)
    for theme_id in (t.strip() for t in args.themes.split(",") if t.strip()):
        theme.set_theme(theme_id, persist=False)
        _settle(app)
        theme_dir = out_root / theme_id
        theme_dir.mkdir(parents=True, exist_ok=True)
        for name, index in _SCREENS:
            window._workspace.setCurrentIndex(index)
            _settle(app)
            _freeze_charts(window)
            _settle(app)
            pixmap = window.grab()
            pixmap.save(str(theme_dir / f"{name}.png"))
            print(f"  {theme_id}/{name}.png  ({pixmap.width()}x{pixmap.height()})")

    # Assemble the curated mixed-theme set the metainfo + website reference.
    site_dir = out_root / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    for hosted_name, theme_id, screen in _SITE_SET:
        source = out_root / theme_id / f"{screen}.png"
        if source.exists():
            shutil.copyfile(source, site_dir / hosted_name)
            print(f"  site/{hosted_name}  <- {theme_id}/{screen}.png")

    auth.lock()
    print(f"\nWrote screenshots under {out_root}")
    print(f"Kept the demo vault at {vault_dir} (master password: demo-passphrase)")


if __name__ == "__main__":
    main()
