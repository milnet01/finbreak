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
_VENDOR_SCRIPT = _OBS / "vendor-wheels.sh"
_RPMLINTRC = _OBS / "finbreak-rpmlintrc"
_LAUNCHER = _OBS / "finbreak.sh"
_DEB = _OBS / "debian"
_DEB_CONTROL = _DEB / "control"
_DEB_RULES = _DEB / "rules"
_DEB_CHANGELOG = _DEB / "changelog"
_DEB_SOURCE_FORMAT = _DEB / "source" / "format"
_DEB_SOURCE_OPTIONS = _DEB / "source" / "options"
_DSC = _OBS / "finbreak.dsc"
_OBS_SUBMIT = _OBS / "obs-submit.sh"
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


def _pkg_names(field_value: str) -> set[str]:
    """A Depends:/Build-Depends: field value -> the set of bare package names,
    with version constraints ("(= 13)"), "|" alternates, and trailing "#"
    comments stripped. Used to compare two copies of the same field (e.g.
    finbreak.dsc vs debian/control) as SETS rather than as literal text, so
    the comparison survives reformatting and only fails when the two actually
    name different packages."""
    names: set[str] = set()
    for raw in field_value.split(","):
        raw = raw.split("#", 1)[0].strip()
        if not raw:
            continue
        for alt in raw.split("|"):
            m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9+.-]*)", alt)
            if m:
                names.add(m.group(1))
    return names


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
    result = subprocess.run(
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

    # The offline wheel closure is vendored by packaging/obs/vendor-wheels.sh —
    # a real script, NOT an XML comment in _service, because shell flags contain
    # "--" which is illegal inside an XML comment and aborts `osc service`.
    vendor_script = _read(_VENDOR_SCRIPT)
    assert "pip" in vendor_script and (
        "download" in vendor_script or "wheel" in vendor_script
    ), "vendor-wheels.sh must build the offline wheel closure via pip download/wheel"
    assert "vendor.tar.gz" in vendor_script, (
        "vendor-wheels.sh must produce vendor.tar.gz (the offline Source1)"
    )

    # _service pulls the tagged source (obs_scm), injects the version
    # (set_version), and references the vendored closure.
    assert "obs_scm" in service or "tar_scm" in service, (
        "_service must fetch the tagged source via obs_scm"
    )
    assert "set_version" in service, (
        "_service must inject the version from the tag via set_version"
    )
    assert "vendor" in service, "_service must reference the vendored wheel closure"


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


# --------------------------------------------------------------------------- #
# INV-9 — deb source recipe (.dsc): un-excludes the Debian/Ubuntu OBS targets
# --------------------------------------------------------------------------- #
def test_INV9_deb_source_recipe() -> None:
    """FIBR-0158. Without a `.dsc` at the OBS package root, OBS marks every
    Debian/Ubuntu repository "excluded" and no .deb is ever attempted — this is
    the file whose mere presence turns the build on. Every assertion here
    compares the .dsc against its sibling file (debian/source/format,
    debian/control, obs-submit.sh) rather than against a hard-coded value, so a
    defect that returns via either side of the pair is still caught."""
    dsc = _read(_DSC)
    fmt_file = _read(_DEB_SOURCE_FORMAT)
    control = _read(_DEB_CONTROL)
    submit = _read(_OBS_SUBMIT)

    # (a) Format: lockstep. debtransform GENERATES debian/source/format from the
    # .dsc's Format: at submit time — if the checked-in files disagree, the
    # committed debian/source/format describes a source format the build does
    # not actually produce.
    m = re.search(r"^Format:\s*(.+)$", dsc, re.MULTILINE)
    assert m, "finbreak.dsc must carry a Format: tag"
    dsc_format = m.group(1).strip()
    assert dsc_format == fmt_file.strip(), (
        f"finbreak.dsc Format: {dsc_format!r} != debian/source/format "
        f"{fmt_file.strip()!r} — debtransform derives the latter from the "
        "former at submit time, so a mismatch means the file committed to git "
        "lies about the source format the build will actually use"
    )

    # (b) Version: is the OBS set_version placeholder, exactly like finbreak.spec
    # (INV-6) — set_version stamps the real version at submit time.
    m = re.search(r"^Version:\s*(\S+)", dsc, re.MULTILINE)
    assert m, "finbreak.dsc must carry a Version: tag"
    dsc_version = m.group(1)
    assert not re.fullmatch(r"\d+\.\d+\.\d+", dsc_version), (
        f"finbreak.dsc Version: must be the OBS set_version placeholder, not a "
        f"hard-coded semver like {dsc_version!r} — a hard-coded value is never "
        "restamped, so every future deb release would carry today's version"
    )

    # (c) DEBTRANSFORM-FILES-TAR: must name BOTH debian.tar.gz and vendor.tar.gz.
    # debtransform reads a debian/ recipe ONLY in the form debian.tar.gz — never
    # a bare directory — so dropping that name leaves OBS with no deb recipe at
    # all. vendor.tar.gz is the ONLY route the offline wheel closure reaches the
    # deb build tree at vendor/, where debian/rules' --find-links vendor/ looks
    # (deb builds have no RPM-style Source1); dropping that name silently
    # removes the vendored wheels from the build.
    m = re.search(r"^DEBTRANSFORM-FILES-TAR:\s*(.+)$", dsc, re.MULTILINE)
    assert m, "finbreak.dsc must carry a DEBTRANSFORM-FILES-TAR: tag"
    tar_names = m.group(1).split()
    assert "debian.tar.gz" in tar_names, (
        "finbreak.dsc DEBTRANSFORM-FILES-TAR: must name debian.tar.gz — "
        "debtransform reads a debian/ recipe only in this archive form, never a "
        f"bare directory; without it OBS builds with no deb recipe: {tar_names!r}"
    )
    assert "vendor.tar.gz" in tar_names, (
        "finbreak.dsc DEBTRANSFORM-FILES-TAR: must name vendor.tar.gz — this is "
        "the only route the offline wheel closure reaches vendor/ in the deb "
        "build tree; without it debian/rules' --find-links vendor/ finds "
        f"nothing and the build fails or reaches out to the network: {tar_names!r}"
    )

    # (d) Build-Depends: must agree with debian/control's, as SETS of package
    # names — OBS resolves deb build dependencies from the .dsc alone (it cannot
    # see inside debian.tar.gz), so a name present in one but not the other is a
    # dependency the real build either lacks at resolve time or never needed.
    dsc_deps = _pkg_names(_control_field(dsc, "Build-Depends"))
    control_deps = _pkg_names(_control_field(control, "Build-Depends"))
    assert dsc_deps, "finbreak.dsc Build-Depends: must be non-empty"
    assert dsc_deps == control_deps, (
        "finbreak.dsc Build-Depends: must match debian/control's Build-Depends: "
        "as sets of package names — OBS resolves deb build dependencies from "
        "the .dsc alone and cannot see inside debian.tar.gz, so a build "
        f"resolved from the .dsc would differ from what debian/control asks "
        f"for; only in .dsc: {sorted(dsc_deps - control_deps)}, only in "
        f"debian/control: {sorted(control_deps - dsc_deps)}"
    )

    # (e) obs-submit.sh must ship the recipe as a debian.tar.gz ARCHIVE, never a
    # bare debian/ directory — `osc add debian` stores a directory as
    # debian.obscpio, a form debtransform cannot read at all, so a package
    # carrying it silently has no working deb recipe (part (c) above depends on
    # this actually happening, not just being declared).
    tar_line = next(
        (
            ln
            for ln in submit.splitlines()
            if "debian.tar.gz" in ln and ln.strip().startswith("tar")
        ),
        None,
    )
    assert tar_line is not None, (
        "obs-submit.sh must pack the debian/ recipe into debian.tar.gz via a "
        "`tar ... debian.tar.gz ... debian` invocation — without it, the file "
        "DEBTRANSFORM-FILES-TAR: names is never actually produced"
    )
    assert tar_line.rstrip().endswith("debian"), (
        f"obs-submit.sh's debian.tar.gz tar invocation must target the debian "
        f"directory as its last argument, so the archive's top-level entry is "
        f"debian/ as debtransform expects: {tar_line!r}"
    )

    lines = submit.splitlines()
    osc_add_line = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("osc") and " add " in ln:
            # a shell line ending in "\" continues onto the next line(s) — the
            # osc add invocation here wraps, so join them before tokenising.
            joined = [ln]
            j = i
            while joined[-1].rstrip().endswith("\\"):
                j += 1
                joined.append(lines[j])
            osc_add_line = " ".join(part.rstrip("\\").strip() for part in joined)
            break
    assert osc_add_line is not None, "obs-submit.sh must osc add the recipe files"
    add_tokens = osc_add_line.split()
    assert "debian.tar.gz" in add_tokens, (
        f"obs-submit.sh's osc add line must stage debian.tar.gz: {osc_add_line!r}"
    )
    assert "debian" not in add_tokens, (
        "obs-submit.sh's osc add line must never stage a bare 'debian' "
        "directory — `osc add debian` stores it as debian.obscpio, a form "
        "debtransform cannot read, silently leaving the package with no "
        f"working deb recipe: {osc_add_line!r}"
    )

    # (f) debian/source/options must keep vendor/ out of the source-package
    # diff. dpkg-buildpackage rebuilds the source package before building the
    # binary, and 3.0 (quilt) aborts on vendor/ — present in the build tree via
    # (c), absent from the .orig tarball, and unrepresentable as a patch because
    # the wheels are binary. Measured 2026-08-31 against dpkg-source in
    # debian:13-slim: include-binaries alone still aborted with "unexpected
    # upstream changes"; extend-diff-ignore exits 0. Deleting this file turns
    # every deb target red again while nothing else in the recipe looks wrong.
    options = _read(_DEB_SOURCE_OPTIONS)
    ignore = [
        ln
        for ln in options.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    assert any("extend-diff-ignore" in ln and "vendor/" in ln for ln in ignore), (
        "debian/source/options must carry an extend-diff-ignore covering "
        "vendor/ — without it dpkg-source aborts the deb build with "
        "'unexpected upstream changes', because the vendored wheels sit "
        "outside debian/ and cannot be represented as a quilt patch.\n"
        f"  expected: a line matching extend-diff-ignore ... vendor/\n"
        f"  actual:   {ignore!r}"
    )


# --------------------------------------------------------------------------- #
# rpmlint filter — the bundled foreign tree under /usr/lib/finbreak trips checks
# that assume a native, system-linked distro package; openSUSE aborts the build
# on the accumulated badness without a filter file (FIBR-0155 §5).
# --------------------------------------------------------------------------- #
def test_FIBR0206_metainfo_screenshot_urls_use_the_hosted_path_shape() -> None:
    """Pin the screenshot URL shape the download site actually serves.

    INV-4 above runs `appstreamcli validate --no-net`, and `--no-net` is exactly
    what let this rot: without the network the validator never fetches an
    `<image>`, so all six URLs can 404 while the gate stays green. They did, for
    months — the metainfo guessed `/img/finbreak/<name>.png` from the in-repo
    basenames, while the site serves `/assets/img/shots/finbreak-<name>.png`
    (FIBR-0206). A store listing whose screenshots 404 renders with none, and
    Flathub's own appstream check fails on it.

    This test stays offline on purpose — reachability needs a network the gate
    must not depend on. It pins the *shape* verified live on 2026-08-07, which
    is what a careless re-edit would break. A genuine site-layout change should
    fail here and be re-verified against the live URLs, not silenced.
    """
    metainfo = _read(_METAINFO)
    urls = re.findall(r"<image[^>]*>([^<]+)</image>", metainfo)
    assert len(urls) == 6, f"expected the six curated screenshots, got {len(urls)}"

    pattern = re.compile(
        r"^https://antsprojectshub\.co\.za/assets/img/shots/finbreak-[a-z]+\.png$"
    )
    bad = [u for u in urls if not pattern.match(u)]
    assert not bad, (
        "screenshot URLs must use the site's hosted path shape "
        "(/assets/img/shots/ + a finbreak- basename prefix); these do not: "
        f"{bad}"
    )


def test_rpmlintrc_filters_bundled_tree_noise() -> None:
    rc = _read(_RPMLINTRC)
    assert "addFilter" in rc, "rpmlintrc must use addFilter() entries"
    # missing-hash-section on the bundled Qt .so's is the dominant badness; the
    # others are the recurring bundled-wheel noise. All must be filtered or the
    # openSUSE build aborts (badness far exceeds the threshold).
    for check in (
        "missing-hash-section",
        "devel-file-in-non-devel-package",
        "unstripped-binary-or-object",
    ):
        assert check in rc, f"rpmlintrc must filter {check} for the bundled payload"
