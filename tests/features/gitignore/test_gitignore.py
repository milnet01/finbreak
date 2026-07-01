"""FIBR-0002 INV-1..INV-3 — `.gitignore` blocks financial data + build output.

Enforces docs/specs/FIBR-0002.md via `git check-ignore --no-index` (exit 0 =
ignored, exit 1 = not ignored). `--no-index` is mandatory — a bare
`git check-ignore` reports every *tracked* file as "not ignored" regardless of
the rules, which would make INV-3 pass vacuously. Directory patterns are
queried via a path *inside* the directory (e.g. `dist/app.exe`), since a bare
directory name with no trailing slash and no on-disk directory reports "not
ignored". See tests/features/gitignore/spec.md.

The checks run against a throwaway git repo carrying a *copy* of the project's
top-level `.gitignore`, so they test THAT file's rules in isolation — free of
tracked-state interference and of the nested `.gitignore` (containing `*`) that
tools like pytest/ruff drop inside their own cache dirs. Testing in-place would
let such a nested rule mask a typo in our pattern.
"""

import subprocess
from pathlib import Path

import pytest

_PROJECT_GITIGNORE = (
    Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    / ".gitignore"
)


@pytest.fixture(scope="module")
def ignore_repo(tmp_path_factory):
    """A fresh git repo whose only rules are a copy of the project `.gitignore`."""
    repo = tmp_path_factory.mktemp("ignore_repo")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(
        _PROJECT_GITIGNORE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return repo


def _is_ignored(repo: Path, path: str) -> bool:
    """True if `path` is excluded by the copied `.gitignore` rules."""
    result = subprocess.run(["git", "check-ignore", "--no-index", "-q", path], cwd=repo)
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"git check-ignore failed for {path!r} (exit {result.returncode})"
        )
    return result.returncode == 0


# INV-1 — vault / database files and their SQLite runtime sidecars.
IGNORED_FINANCIAL = [
    "finbreak.db",
    "sub/dir/myvault.sqlite",
    "vault.sqlite3",
    "finbreak.db-wal",
    "finbreak.db-shm",
    "finbreak.db-journal",
    "myvault.sqlite-wal",
    "vault.sqlite3-journal",
]

# INV-2 — build / packaging / tooling output (directories queried via an
# inside path).
IGNORED_BUILD = [
    "dist/finbreak.exe",
    "build/lib/finbreak/resources.dat",
    "finbreak.egg-info/PKG-INFO",
    ".flatpak-builder/cache/x",
    "finbreak-1.0.dmg",
    "finbreak-x86_64.AppImage",
    "finbreak.flatpak",
    ".pytest_cache/CACHEDIR.TAG",
    ".ruff_cache/0.1.0/entry",
    ".mypy_cache/3.12/finbreak.data.json",
]

# INV-3 — real source must NOT be ignored (over-broad-pattern guard).
NOT_IGNORED_SOURCE = [
    "src/finbreak/__init__.py",
    "docs/design.md",
    "pyproject.toml",
    "tests/test_smoke.py",
    "scripts/ci-local.sh",
]


@pytest.mark.features
@pytest.mark.parametrize("path", IGNORED_FINANCIAL)
def test_INV1_financial_data_is_ignored(ignore_repo, path):
    assert _is_ignored(ignore_repo, path), (
        f"{path} must be git-ignored — financial-data leak risk"
    )


@pytest.mark.features
@pytest.mark.parametrize("path", IGNORED_BUILD)
def test_INV2_build_output_is_ignored(ignore_repo, path):
    assert _is_ignored(ignore_repo, path), (
        f"{path} must be git-ignored — build/tooling output"
    )


@pytest.mark.features
@pytest.mark.parametrize("path", NOT_IGNORED_SOURCE)
def test_INV3_real_source_is_not_ignored(ignore_repo, path):
    assert not _is_ignored(ignore_repo, path), (
        f"{path} must NOT be ignored — over-broad .gitignore"
    )
