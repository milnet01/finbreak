"""Tests for the marketing helper scripts (FIBR-0399). See spec.md."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts"


def _python(code: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=tmp_path,
        env={**base, "TMPDIR": str(tmp_path), **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_INV1_seed_demo_vault_imports_the_checkout(tmp_path):
    seed = str(_SCRIPTS / "seed_demo_vault.py")
    result = _python(
        f"""
        import runpy, sys
        sys.argv = ["seed_demo_vault.py"]
        try:
            runpy.run_path({seed!r}, run_name="__main__")
        except SystemExit:
            pass
        import finbreak
        print(finbreak.__file__)
        """,
        tmp_path,
        QT_QPA_PLATFORM="offscreen",
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).is_relative_to(_REPO_ROOT / "src"), result.stdout


_IMPORT_CAPTURE = (
    f"import os, sys\nsys.path.insert(0, {str(_SCRIPTS)!r})\n"
    "import capture_screenshots\n"
)


def test_INV2_capture_screenshots_forces_offscreen(tmp_path):
    result = _python(
        _IMPORT_CAPTURE + "print(os.environ['QT_QPA_PLATFORM'])",
        tmp_path,
        QT_QPA_PLATFORM="xcb",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "offscreen"


def test_INV3_a_missing_site_shot_is_reported(tmp_path):
    out = tmp_path / "shots"
    (out / "midnight").mkdir(parents=True)
    for screen in ("dashboard", "categories", "transfers"):
        (out / "midnight" / f"{screen}.png").write_bytes(b"png")
    target = f"__import__('pathlib').Path({str(out)!r})"
    call = f"capture_screenshots._assemble_site({target})"
    result = _python(
        _IMPORT_CAPTURE + f"print({call})",
        tmp_path,
        QT_QPA_PLATFORM="offscreen",
    )
    assert result.returncode == 0, result.stderr
    assert "transactions.png" in result.stderr and "ledger" in result.stderr
    assert (out / "site" / "dashboard.png").exists()
