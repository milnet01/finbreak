"""Freeze `python -m finbreak --self-test` to a single Windows `finbreak.exe`
(FIBR-0015 D2). Runs on a `windows-latest` GitHub Actions runner — PyInstaller
cannot cross-compile, so the `.exe` must be produced on Windows.

This is the Windows analogue of `scripts/_build-smoke-in-container.sh`'s freeze:
same collection flags (imported from the canonical `windows_freeze_flags`, so the
parity guard governs both — INV-3), same manifest-driven dep install (INV-6), same
single-Qt-binding guard (INV-2). The only OS difference is the `--add-data`
separator, which uses `os.pathsep` (`;` on Windows, `:` on POSIX — INV-5).

Produces `dist/finbreak.exe` at the repo root. The workflow then launches it with
`--self-test` (Python off `PATH`) and asserts `FINBREAK_SELFTEST_OK` (INV-4).
"""

from __future__ import annotations

import importlib.metadata as im
import os
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import windows_freeze_flags as flags  # noqa: E402  (sibling script, not a package)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_SRC = _REPO_ROOT / "src"
_ICONS_SRC = _SRC / "finbreak" / "ui" / "icons"
_ENTRY = _SRC / "finbreak" / "__main__.py"

_QT_BINDINGS = ("PySide2", "PySide6", "PyQt5", "PyQt6")
PYINSTALLER_PIN = "pyinstaller==6.21.0"


def _runtime_deps() -> list[str]:
    """`[project].dependencies` read straight from pyproject — the SAME manifest the
    Linux freeze reads, so a dependency bump reaches the Windows bundle without
    editing this script (INV-6)."""
    with _PYPROJECT.open("rb") as handle:
        return list(tomllib.load(handle)["project"]["dependencies"])


def _assert_single_qt_binding() -> None:
    """Exactly one Qt binding must be installed before PyInstaller runs — 6.x
    refuses to collect more than one (INV-2, mirroring the Linux freeze)."""
    present = [name for name in _QT_BINDINGS if _installed(name)]
    if len(present) != 1:
        raise SystemExit(
            f"build-windows-exe: expected exactly one Qt binding, found {present}"
        )


def _installed(dist_name: str) -> bool:
    try:
        im.version(dist_name)
        return True
    except im.PackageNotFoundError:
        return False


def _pip(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", *args], check=True)


def main() -> None:
    _pip("--upgrade", "pip")
    # Manifest-driven: install exactly the runtime deps + the pinned PyInstaller,
    # so the frozen analysis sees the same packages the Linux freeze does (INV-6).
    _pip(*_runtime_deps(), PYINSTALLER_PIN)
    _assert_single_qt_binding()

    add_data = f"{_ICONS_SRC}{os.pathsep}{flags.ADD_DATA_TARGET}"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        # GUI app: /SUBSYSTEM:WINDOWS, no attached console (FIBR-0132). Without
        # this PyInstaller defaults to a console build and a cmd window flashes up
        # before the GUI. Windows-only — the Linux freeze stays console (its
        # clean-room reads the --self-test sentinel from stdout, and a headless
        # AppImage has no window nuisance). --windowed nulls sys.stdout/stderr on
        # Windows, so the clean-room reads the sentinel from FINBREAK_SELFTEST_OUT.
        "--windowed",
        "--name",
        "finbreak",
        "--paths",
        str(_SRC),
        "--add-data",
        add_data,
        *flags.pyinstaller_flags(),
        "--distpath",
        str(_REPO_ROOT / "dist"),
        "--workpath",
        str(_REPO_ROOT / "build" / "pyi"),
        "--specpath",
        str(_REPO_ROOT / "build"),
        str(_ENTRY),
    ]
    print("freezing:", " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)

    exe = _REPO_ROOT / "dist" / "finbreak.exe"
    if not exe.is_file():
        raise SystemExit(f"build-windows-exe: expected {exe}, not produced")
    print(f"built {exe}", file=sys.stderr)


if __name__ == "__main__":
    main()
