"""FIBR-0155 — OBS native RPM/deb packaging.

Enforces tests/features/obs_packaging/spec.md. Two families, no real OBS build:

  * source/recipe scrape (INV-1/2/3/4/6/7) — read packaging/obs/* + app.py and
    assert the FIBR-0155 structure + substrings, mirroring
    tests/features/release_integrity/test_release_integrity.py and
    tests/features/windows_build/test_windows_build.py.
  * runtime assertion (INV-5, INV-8) — the distro-launch updater-inert gate and
    the console entry-point resolve.

No network, no real OBS build, no financial data.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.features

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OBS = _REPO_ROOT / "packaging" / "obs"
_SPEC = _OBS / "finbreak.spec"
_SERVICE = _OBS / "_service"
_LAUNCHER = _OBS / "finbreak.sh"
_DEB = _OBS / "debian"
_DEB_CONTROL = _DEB / "control"
_DEB_RULES = _DEB / "rules"
_DEB_CHANGELOG = _DEB / "changelog"
_APP_PY = _REPO_ROOT / "src" / "finbreak" / "app.py"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

APP_ID = "io.github.milnet01.finbreak"
_DESKTOP = _OBS / f"{APP_ID}.desktop"
_METAINFO = _OBS / f"{APP_ID}.metainfo.xml"

# The security-critical native stack (§ 3.2) that stays BUNDLED — a distro
# Requires:/Depends: on any of these would contradict the bundling decision.
_BUNDLED_STACK_BLOCKLIST = (
    "sqlcipher",
    "qpdf",
    "pdfium",
    "pypdfium",
    "pyside",
    "pikepdf",
    "python3-pyside6",
    "python3-pikepdf",
    "python3-sqlcipher",
    "python3-pdfplumber",
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _read(path: Path) -> str:
    assert path.is_file(), f"missing packaging asset: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def _desktop_entries(text: str) -> dict[str, str]:
    """Parse a .desktop [Desktop Entry] group into key→value."""
    out: dict[str, str] = {}
    in_group = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_group = line == "[Desktop Entry]"
            continue
        if in_group and "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _control_field(control: str, field: str) -> str:
    """A deb control field's full value, joining RFC5322-style folded continuation
    lines (a Depends: can span several indented lines)."""
    lines = control.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.startswith(f"{field}:"):
            out.append(line[len(field) + 1 :])
            capturing = True
        elif capturing and line[:1] in (" ", "\t"):
            out.append(line)
        elif capturing:
            break
    return " ".join(out)


def _app_call_arg(func: str) -> str:
    """Extract the single string literal passed to ``func(...)`` in app.py — e.g.
    ``setApplicationName("finbreak")`` → ``finbreak``."""
    text = _APP_PY.read_text(encoding="utf-8")
    m = re.search(rf'{re.escape(func)}\(\s*["\']([^"\']+)["\']', text)
    assert m, f"could not find {func}(...) call in app.py"
    return m.group(1)


def _version() -> str:
    text = (_REPO_ROOT / "src" / "finbreak" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"', text)
    assert m, "could not read __version__"
    return m.group(1)


def _requires_lines(spec_text: str) -> list[str]:
    """The `Requires:` runtime-dep lines (NOT BuildRequires:)."""
    return [
        ln.strip() for ln in spec_text.splitlines() if re.match(r"\s*Requires:", ln)
    ]


# --------------------------------------------------------------------------- #
# INV-1 — frozen payload; minimal runtime deps; no distro-shared security stack
# --------------------------------------------------------------------------- #
def test_INV1_frozen_payload_minimal_runtime_deps() -> None:
    spec = _read(_SPEC)
    control = _read(_DEB_CONTROL)

    # (a) both %if branches for the two RPM families.
    assert "%if 0%{?suse_version}" in spec
    assert "%if 0%{?fedora}" in spec

    # (b) the runtime Requires: set is the host-left libGL/libEGL pair only — the
    # rest of the stack travels in-bundle. Assert GL + EGL are required...
    req_blob = "\n".join(_requires_lines(spec)).lower()
    assert "libgl" in req_blob, "runtime Requires: must name libGL"
    assert "libegl" in req_blob, "runtime Requires: must name libEGL"

    control_depends = _control_field(control, "Depends").lower()
    assert "libgl1" in control_depends and "libegl1" in control_depends

    # (c) ...and NO bundled-stack package appears in either runtime dep set.
    for name in _BUNDLED_STACK_BLOCKLIST:
        assert name.lower() not in req_blob, f"{name} must not be in .spec Requires:"
        assert name.lower() not in control_depends, (
            f"{name} must not be in debian/control Depends:"
        )


# --------------------------------------------------------------------------- #
# INV-2 — installed launcher works + self-tests against the staged buildroot
# --------------------------------------------------------------------------- #
def test_INV2_launcher_and_buildroot_selftest() -> None:
    spec = _read(_SPEC)
    rules = _read(_DEB_RULES)
    launcher = _read(_LAUNCHER)

    # The /usr/bin/finbreak wrapper exec's the frozen entry with "$@" passthrough.
    assert "/usr/lib/finbreak/finbreak" in launcher
    assert '"$@"' in launcher
    assert launcher.lstrip().startswith("#!")

    for name, text in (("finbreak.spec", spec), ("debian/rules", rules)):
        # (a) the self-test runs against the STAGED buildroot path, never a bare
        # `finbreak` on $PATH (the package isn't installed at build/%check time).
        assert "lib/finbreak/finbreak --self-test" in text, (
            f"{name}: self-test must invoke the staged buildroot freeze"
        )
        # (b) headless build roots require the offscreen platform.
        assert "QT_QPA_PLATFORM=offscreen" in text, (
            f"{name}: self-test must set QT_QPA_PLATFORM=offscreen"
        )


# --------------------------------------------------------------------------- #
# INV-3 — identity matches on BOTH Wayland and X11
# --------------------------------------------------------------------------- #
def test_INV3_identity_wayland_and_x11() -> None:
    entries = _desktop_entries(_read(_DESKTOP))
    metainfo = _read(_METAINFO)

    # .desktop basename IS the app-id (file exists — _read asserts it).
    assert _DESKTOP.name == f"{APP_ID}.desktop"
    assert entries.get("Icon") == APP_ID
    assert entries.get("Exec") == "finbreak"
    assert entries.get("Type") == "Application"
    assert entries.get("Name"), "a mandatory non-empty Name= is required"

    # metainfo identity fields.
    assert f"<id>{APP_ID}</id>" in metainfo
    assert f'<launchable type="desktop-id">{APP_ID}.desktop</launchable>' in metainfo

    # X11: StartupWMClass equals app.py's applicationName arg VERBATIM.
    app_name = _app_call_arg("setApplicationName")
    assert entries.get("StartupWMClass") == app_name, (
        "StartupWMClass must equal setApplicationName arg verbatim (X11 WM_CLASS)"
    )

    # Wayland: setDesktopFileName arg equals the .desktop basename (the app-id).
    desktop_file_name = _app_call_arg("setDesktopFileName")
    assert desktop_file_name == APP_ID, (
        "setDesktopFileName arg must equal the reverse-DNS .desktop basename "
        "(Wayland app_id)"
    )


# --------------------------------------------------------------------------- #
# INV-4 — metainfo validates (skip-if-absent; manual / pre-submit)
# --------------------------------------------------------------------------- #
def test_INV4_metainfo_validates() -> None:
    validator = shutil.which("appstreamcli")
    if validator is None:
        pytest.skip("appstreamcli not installed (manual / pre-OBS-submit check)")
    result = subprocess.run(  # noqa: S603
        [validator, "validate", "--no-net", str(_METAINFO)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# INV-5 — self-updater inert in a distro launch ($APPIMAGE unset)
# --------------------------------------------------------------------------- #
def test_INV5_updater_inert_without_appimage(monkeypatch: pytest.MonkeyPatch) -> None:
    from finbreak.services import update_installer

    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(update_installer.sys, "platform", "linux")
    # sys.frozen absent (running from source) — the Windows branch never fires.
    monkeypatch.delattr(update_installer.sys, "frozen", raising=False)

    assert update_installer.detect_installer() is None
    assert update_installer.is_update_supported() is False


# --------------------------------------------------------------------------- #
# INV-6 — version single-source (metainfo AND deb changelog)
# --------------------------------------------------------------------------- #
def test_INV6_version_single_source() -> None:
    version = _version()
    spec = _read(_SPEC)
    metainfo = _read(_METAINFO)
    changelog = _read(_DEB_CHANGELOG)

    # (a) the .spec Version: is the service placeholder, not a hard-coded semver.
    m = re.search(r"^\s*Version:\s*(\S+)", spec, re.MULTILINE)
    assert m, ".spec must carry a Version: tag"
    assert not re.fullmatch(r"\d+\.\d+\.\d+", m.group(1)), (
        f".spec Version: must be the OBS set_version placeholder, not {m.group(1)!r}"
    )

    # (b) the newest metainfo <release version> equals __version__.
    releases = re.findall(r'<release[^>]*\bversion="([0-9.]+)"', metainfo)
    assert releases, "metainfo must carry at least one <release version=...>"
    assert releases[0] == version, (
        f"newest metainfo <release> {releases[0]!r} != __version__ {version!r}"
    )

    # (c) the top debian/changelog stanza equals __version__.
    first = changelog.splitlines()[0]
    m = re.match(r"finbreak \(([0-9][^)]*)\)", first)
    assert m, f"debian/changelog first line malformed: {first!r}"
    assert m.group(1) == version, (
        f"debian/changelog stanza {m.group(1)!r} != __version__ {version!r}"
    )


# --------------------------------------------------------------------------- #
# INV-7 — offline build (vendored wheels, no network in the build phase)
# --------------------------------------------------------------------------- #
def test_INV7_offline_build() -> None:
    spec = _read(_SPEC)
    rules = _read(_DEB_RULES)
    service = _read(_SERVICE)

    for name, text in (("finbreak.spec", spec), ("debian/rules", rules)):
        installs = [
            ln for ln in text.splitlines() if re.search(r"\bpip\b.*\binstall\b", ln)
        ]
        assert installs, f"{name}: expected a build-phase pip install"
        for ln in installs:
            assert "--no-index" in ln, (
                f"{name}: build-phase pip install must be offline (--no-index): {ln!r}"
            )
        assert "--find-links" in text and "vendor" in text, (
            f"{name}: must install from the vendored wheel dir"
        )

    # The _service fetches the wheel closure and injects the version.
    assert "pip" in service and "download" in service, (
        "_service must vendor the wheel closure via pip download"
    )
    assert "set_version" in service or "tar_scm" in service or "obs_scm" in service, (
        "_service must inject the version from the tag"
    )


# --------------------------------------------------------------------------- #
# INV-8 — console entry point declared (this spec's INV-8)
# --------------------------------------------------------------------------- #
def test_INV8_console_entry_point() -> None:
    with _PYPROJECT.open("rb") as fh:
        meta = tomllib.load(fh)
    scripts = meta.get("project", {}).get("scripts", {})
    assert scripts.get("finbreak") == "finbreak.__main__:main", (
        "pyproject [project.scripts] must map finbreak -> finbreak.__main__:main"
    )

    from finbreak.__main__ import main

    assert callable(main)
