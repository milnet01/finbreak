"""FIBR-0003 INV-1/INV-6 (+ INV-2/INV-3) — bundling smoke-test.

Enforces docs/specs/FIBR-0003.md. The fast guards run the real
`python -m finbreak` CLI in a subprocess (offscreen Qt) and unit-test the
`_selftest` FAIL path; the integration test drives `scripts/build-smoke.sh`
and is opt-in so the everyday gate never blocks on a multi-minute build.
See tests/features/bundling/spec.md.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m finbreak <args>` from the project root, offscreen Qt."""
    env = {
        **os.environ,
        "PYTHONPATH": str(_PROJECT_ROOT / "src"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    return subprocess.run(
        [sys.executable, "-m", "finbreak", *args],
        cwd=_PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        # Fail fast if the self-test subprocess hangs (e.g. a regression spins up
        # a real event loop instead of exiting) — no pytest-timeout plugin is
        # configured, so without this the whole gate blocks until the CI job cap.
        timeout=60,
    )


@pytest.mark.features
def test_INV1_selftest_ok_all_stacks():
    """--self-test loads Qt + SQLCipher + qpdf + Argon2 → exact OK line, exit 0."""
    result = _run_cli("--self-test")
    assert result.returncode == 0, (
        f"--self-test exited {result.returncode}; stderr:\n{result.stderr}"
    )
    assert "FINBREAK_SELFTEST_OK" in result.stdout.splitlines(), (
        f"missing exact FINBREAK_SELFTEST_OK line; stdout:\n{result.stdout}"
    )


@pytest.mark.features
@pytest.mark.skipif(
    sys.platform in ("win32", "darwin"),
    reason="Windows/macOS always have a window server; the headless default is "
    "deliberately Linux/BSD-only (a frozen bundle there may not carry the "
    "offscreen plugin)",
)
def test_FIBR0261_selftest_runs_headless_with_no_display_and_no_platform_var(tmp_path):
    """--self-test must run on a machine with no display, not abort on it.

    Every other caller exports ``QT_QPA_PLATFORM=offscreen`` for it —
    ``tests/conftest.py``, ``build-smoke.sh``, ``finbreak.spec``,
    ``debian/rules`` — so no other test can see this. The one caller that does
    not is the human following CLAUDE.md's documented ``python -m finbreak
    --self-test``, and FIBR-0003 INV-1 calls that a **permanent** diagnostic for
    a broken install on a user's machine: a headless server over SSH is exactly
    where it is needed, and exactly where Qt used to abort (SIGABRT, "no Qt
    platform plugin could be initialized") before the first check ran.

    Strips all three variables so the child is genuinely headless — with
    ``QT_QPA_PLATFORM`` left in place (conftest sets it) the test would be
    vacuous. ``XDG_RUNTIME_DIR`` is repointed at an empty directory as well,
    because dropping ``WAYLAND_DISPLAY`` alone is NOT enough on a Wayland
    desktop: libwayland falls back to the socket named ``wayland-0`` inside
    that directory, so the child would still find the developer's compositor
    and pass without the fix.
    """
    stripped = ("QT_QPA_PLATFORM", "DISPLAY", "WAYLAND_DISPLAY")
    env = {k: v for k, v in os.environ.items() if k not in stripped}
    env["PYTHONPATH"] = str(_PROJECT_ROOT / "src")
    env["XDG_RUNTIME_DIR"] = str(tmp_path)  # exists, holds no compositor socket
    assert not set(stripped) & env.keys(), (
        "precondition: the child must inherit no display and no platform "
        "override, or this test proves nothing"
    )
    assert not list(tmp_path.iterdir()), (
        "precondition: the stand-in XDG_RUNTIME_DIR must be empty, or Qt may "
        "still reach a display"
    )

    result = subprocess.run(
        [sys.executable, "-m", "finbreak", "--self-test"],
        cwd=_PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"--self-test exited {result.returncode} with no display "
        f"(negative = killed by a signal); stderr:\n{result.stderr}"
    )
    assert "FINBREAK_SELFTEST_OK" in result.stdout.splitlines(), (
        f"missing exact FINBREAK_SELFTEST_OK line; stdout:\n{result.stdout}"
    )


@pytest.mark.features
def test_INV1_noargs_routes_to_gui(monkeypatch) -> None:
    """No args now launches the GUI (FIBR-0004), not the retired NOT_BUILT stub.

    Asserts routing without spinning a real event loop: ``main([])`` must call
    ``finbreak.app.run``. The GUI screens themselves are covered by the qtbot
    tests in tests/features/vault/.
    """
    import finbreak.app
    from finbreak import __main__ as entry

    called: dict[str, bool] = {}

    def fake_run(argv=None) -> int:
        called["ran"] = True
        return 0

    monkeypatch.setattr(finbreak.app, "run", fake_run)
    assert entry.main([]) == 0
    assert called.get("ran") is True, "no-args must route to the GUI launcher"


# FIBR-0325 — every leg below that drives `run_self_test` takes `qapp`.
#
# They stub `_check_qt` to a no-op, and `run_self_test` then reaches
# `_check_icons`, which renders a QPixmap. With no QApplication in the process
# Qt does not raise, it ABORTS — `Fatal Python error: Aborted`, taking the whole
# pytest run with it. Inside the full suite an earlier test has already made
# one, so the suite passed there and died when run on its own: exactly the
# situation someone debugging a bundling failure would be in.
#
# `qapp` (pytest-qt) guarantees the application regardless of what ran before,
# which is what makes this file runnable in isolation. The stub stays: it is
# what proves `run_self_test` resolves its checks at call time.
@pytest.mark.features
def test_FIBR0259_selftest_fail_names_qtnetwork(qapp, monkeypatch):
    """A missing Qt6Network must FAIL the self-test, naming `qtnetwork`.

    This is the leg whose ABSENCE shipped a Flatpak that could not start.
    `libQt6Network.so.6` links against `libgssapi_krb5.so.2`, which the
    freedesktop runtime does not provide, so `app.py`'s first import died —
    while the self-test printed its OK sentinel, because its check list covered
    QtWidgets, QtCharts, QtGui, QtCore, SQLCipher and pikepdf but never
    QtNetwork. Every automated gate passed; a human launching the app found it
    immediately.

    Guards both halves: that `qtnetwork` is IN the ordered check list at all
    (a check that is never run cannot fail), and that its failure is reported
    under that name.
    """
    from finbreak import _selftest

    assert "qtnetwork" in _selftest.CHECK_NAMES, (
        "qtnetwork must be in the self-test's check list — it is the import "
        "that a runtime without krb5 breaks, and the one omission that let a "
        "non-starting bundle report success"
    )

    monkeypatch.setattr(_selftest, "_check_qt", lambda: None)

    def _boom() -> None:
        raise ImportError("libgssapi_krb5.so.2: cannot open shared object file")

    monkeypatch.setattr(_selftest, "_check_qtnetwork", _boom)

    out = io.StringIO()
    rc = _selftest.run_self_test(out)

    assert rc != 0, "a missing Qt6Network must exit non-zero"
    assert out.getvalue().splitlines() == ["FINBREAK_SELFTEST_FAIL: qtnetwork"], (
        f"expected the qtnetwork FAIL line only; got:\n{out.getvalue()}"
    )


@pytest.mark.features
def test_INV1_selftest_fail_names_the_broken_stack(qapp, monkeypatch):
    """A failing stack → 'FINBREAK_SELFTEST_FAIL: <stack>' + non-zero.

    Unit-tests the FAIL contract independent of installed native deps:
    Qt is patched to pass, SQLCipher to raise, so the ordered token is
    `sqlcipher`.
    """
    from finbreak import _selftest

    monkeypatch.setattr(_selftest, "_check_qt", lambda: None)

    def _boom() -> None:
        raise RuntimeError("simulated SQLCipher load failure")

    monkeypatch.setattr(_selftest, "_check_sqlcipher", _boom)

    out = io.StringIO()
    rc = _selftest.run_self_test(out)

    assert rc != 0, "a failing stack must exit non-zero"
    assert out.getvalue().splitlines() == ["FINBREAK_SELFTEST_FAIL: sqlcipher"], (
        f"expected the sqlcipher FAIL line only; got:\n{out.getvalue()}"
    )


@pytest.mark.features
def test_INV1_selftest_fail_names_argon2(qapp, monkeypatch):
    """The FIBR-0004 argon2 leg names itself on failure (all earlier stacks pass)."""
    from finbreak import _selftest

    monkeypatch.setattr(_selftest, "_check_qt", lambda: None)
    monkeypatch.setattr(_selftest, "_check_sqlcipher", lambda: None)
    monkeypatch.setattr(_selftest, "_check_pikepdf", lambda: None)
    monkeypatch.setattr(_selftest, "_check_pdf_encrypt", lambda: None)

    def _boom() -> None:
        raise RuntimeError("simulated Argon2 load failure")

    monkeypatch.setattr(_selftest, "_check_argon2", _boom)

    out = io.StringIO()
    rc = _selftest.run_self_test(out)

    assert rc != 0, "a failing stack must exit non-zero"
    assert out.getvalue().splitlines() == ["FINBREAK_SELFTEST_FAIL: argon2"], (
        f"expected the argon2 FAIL line only; got:\n{out.getvalue()}"
    )


@pytest.mark.features
def test_INV1_selftest_fail_names_pdf_encrypt(qapp, monkeypatch):
    """The FIBR-0013 encrypt-export leg (QPdfWriter + pikepdf.Encryption) names
    itself on failure (all earlier stacks pass)."""
    from finbreak import _selftest

    monkeypatch.setattr(_selftest, "_check_qt", lambda: None)
    monkeypatch.setattr(_selftest, "_check_sqlcipher", lambda: None)
    monkeypatch.setattr(_selftest, "_check_pikepdf", lambda: None)

    def _boom() -> None:
        raise RuntimeError("simulated encrypt-export failure")

    monkeypatch.setattr(_selftest, "_check_pdf_encrypt", _boom)

    out = io.StringIO()
    rc = _selftest.run_self_test(out)

    assert rc != 0, "a failing stack must exit non-zero"
    assert out.getvalue().splitlines() == ["FINBREAK_SELFTEST_FAIL: pdf_encrypt"], (
        f"expected the pdf_encrypt FAIL line only; got:\n{out.getvalue()}"
    )


@pytest.mark.features
def test_INV1_selftest_fail_names_ofxparse(qapp, monkeypatch):
    """The FIBR-0008 ofxparse leg names itself on failure (all earlier stacks pass)."""
    from finbreak import _selftest

    monkeypatch.setattr(_selftest, "_check_qt", lambda: None)
    monkeypatch.setattr(_selftest, "_check_sqlcipher", lambda: None)
    monkeypatch.setattr(_selftest, "_check_pikepdf", lambda: None)
    monkeypatch.setattr(_selftest, "_check_pdf_encrypt", lambda: None)
    monkeypatch.setattr(_selftest, "_check_argon2", lambda: None)

    def _boom() -> None:
        raise RuntimeError("simulated ofxparse load failure")

    monkeypatch.setattr(_selftest, "_check_ofxparse", _boom)

    out = io.StringIO()
    rc = _selftest.run_self_test(out)

    assert rc != 0, "a failing stack must exit non-zero"
    assert out.getvalue().splitlines() == ["FINBREAK_SELFTEST_FAIL: ofxparse"], (
        f"expected the ofxparse FAIL line only; got:\n{out.getvalue()}"
    )


def _container_runtime() -> str | None:
    return shutil.which("podman") or shutil.which("docker")


@pytest.mark.integration
def test_INV2_INV3_build_smoke_clean_room():
    """build-smoke.sh freezes both artifacts and runs them Python-free (exit 0).

    Opt-in: skips unless FINBREAK_BUILD_SMOKE=1 and the tooling is present, so
    the everyday gate never blocks on the multi-minute build (INV-5/INV-6).
    """
    if os.environ.get("FINBREAK_BUILD_SMOKE") != "1":
        pytest.skip("set FINBREAK_BUILD_SMOKE=1 to run the build+clean-room test")
    script = _PROJECT_ROOT / "scripts" / "build-smoke.sh"
    if not script.exists():
        pytest.skip("scripts/build-smoke.sh not present yet")
    if _container_runtime() is None:
        pytest.skip("no container runtime (podman/docker) on PATH")

    result = subprocess.run([str(script)], cwd=_PROJECT_ROOT)
    assert result.returncode == 0, "build-smoke.sh must exit 0 (both artifacts pass)"


# --------------------------------------------------------------------------- #
# INV-7 — build-tool pins are in lockstep between pyproject and every build path.
#
# Neither tool is ever installed via `--group build` / `--group dev` by the build
# paths: the container smoke build, the Windows freeze driver and the three OBS
# recipes each name `pyinstaller==` inline, and windows-build.yml names
# `pip-audit==` inline. Without this gate, bumping the pyproject pin silently
# leaves all of them behind — a class of drift docs/specs/FIBR-0155.md § 805-808
# already flagged. The scan walks tracked files, so a NEW call-site is covered
# automatically; `min_sites` guards against the scan passing vacuously if a build
# path stops pinning (or moves).
# --------------------------------------------------------------------------- #
_LOCKSTEP_PINS = (
    # (distribution, pyproject dependency-group, minimum expected inline sites)
    ("pyinstaller", "build", 6),  # pyproject + 5 build paths (one names it twice)
    ("pip-audit", "dev", 2),  # pyproject + windows-build.yml's SBOM step
)


def _group_pin(pattern: re.Pattern[str], group_name: str) -> str:
    """The authoritative pin: pyproject's PEP 735 ``<group_name>`` group."""
    with (_PROJECT_ROOT / "pyproject.toml").open("rb") as fh:
        group = tomllib.load(fh)["dependency-groups"][group_name]
    pins = [m.group(1) for dep in group if (m := pattern.fullmatch(dep))]
    assert len(pins) == 1, f"expected one pin in [{group_name}], got {pins}"
    return pins[0]


@pytest.mark.parametrize(("dist", "group", "min_sites"), _LOCKSTEP_PINS)
def test_INV7_build_tool_pins_are_in_lockstep(
    dist: str, group: str, min_sites: int
) -> None:
    pattern = re.compile(rf"{re.escape(dist)}==([0-9][0-9A-Za-z.\-+]*)")
    expected = _group_pin(pattern, group)
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")

    offenders: list[str] = []
    sites = 0
    for rel in tracked:
        if not rel or rel.startswith("tests/features/bundling/"):
            continue  # this file names the pattern itself
        path = _PROJECT_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in pattern.finditer(line):
                sites += 1
                if match.group(1) != expected:
                    offenders.append(f"{rel}:{lineno}: {match.group(0)}")

    assert not offenders, (
        f"{dist} pin drift — pyproject [dependency-groups] {group} says "
        f"{expected}, but:\n" + "\n".join(offenders)
    )
    assert sites >= min_sites, (
        f"expected >= {min_sites} inline {dist} pins, found {sites} — did a "
        f"build path stop pinning it, or move?"
    )


# --------------------------------------------------------------------------- #
# FIBR-0188 — the AppImage's launcher identity matches the window's
# --------------------------------------------------------------------------- #
def test_FIBR0188_appimage_desktop_basename_matches_the_apps_desktop_file_name():
    """A Wayland panel matches the window's app_id against a .desktop BASENAME.
    app.py sets that app_id via setDesktopFileName(); the AppImage build must write
    a .desktop of the same name, or the running window cannot be associated with
    its launcher and the panel shows a second icon."""
    root = Path(__file__).resolve().parents[3]
    app_py = (root / "src" / "finbreak" / "app.py").read_text()
    match = re.search(r'setDesktopFileName\(\s*"([^"]+)"', app_py)
    assert match, "app.py no longer calls setDesktopFileName — app_id is unset"
    app_id = match.group(1)

    build = (root / "scripts" / "build-smoke.sh").read_text()
    assert f'export APP_ID="{app_id}"' in build, (
        f"build-smoke.sh must export APP_ID={app_id} so the AppImage's .desktop "
        "basename equals the window's app_id (FIBR-0188)"
    )

    container = (root / "scripts" / "_build-smoke-in-container.sh").read_text()
    assert '"$APPDIR/$APP_ID.desktop"' in container, (
        "the AppImage .desktop must be named for APP_ID, not the versioned binary"
    )
    assert "Icon=$APP_ID" in container and '"$APPDIR/$APP_ID.png"' in container, (
        "appimagetool requires the bundled icon filename to match the Icon= key"
    )
    assert "StartupWMClass=$APP_WM_CLASS" in container, (
        "the X11 half of the association (WM_CLASS) is still missing"
    )


def test_FIBR0188_appimage_wm_class_matches_the_application_name():
    """X11 WM_CLASS comes from applicationName(), which is the bare "finbreak" —
    NOT the versioned binary name — and the RPM/deb launcher already says so."""
    root = Path(__file__).resolve().parents[3]
    app_py = (root / "src" / "finbreak" / "app.py").read_text()
    match = re.search(r'setApplicationName\(\s*"([^"]+)"', app_py)
    assert match, "app.py no longer sets applicationName — WM_CLASS is undefined"
    wm_class = match.group(1)

    build = (root / "scripts" / "build-smoke.sh").read_text()
    assert f'export APP_WM_CLASS="{wm_class}"' in build

    obs = (
        root / "packaging" / "obs" / "io.github.milnet01.finbreak.desktop"
    ).read_text()
    assert f"StartupWMClass={wm_class}" in obs, (
        "the AppImage and the RPM/deb launchers must claim the same WM_CLASS"
    )


def test_FIBR0132_windowed_build_still_emits_a_sentinel(monkeypatch, tmp_path):
    """`--self-test` has an observable result even with no console.

    PyInstaller's `--windowed` sets `sys.stdout` to None on Windows, and
    `print(..., file=None)` is a SILENT NO-OP -- so the shipped .exe emitted
    neither `FINBREAK_SELFTEST_OK` nor `FINBREAK_SELFTEST_FAIL: <stack>`,
    including the failing-stack token that is the whole reason FAIL carries a
    prefix. A user running the documented diagnostic on a broken install got an
    exit code and nothing else.

    The clean-room was fixed by giving the BUILD an env var (FIBR-0132); this
    covers the user, who has none.
    """
    import finbreak.__main__ as main_mod

    out_dir = tmp_path / "fallback"
    out_dir.mkdir()
    monkeypatch.setattr(main_mod.tempfile, "gettempdir", lambda: str(out_dir))
    monkeypatch.delenv("FINBREAK_SELFTEST_OUT", raising=False)
    monkeypatch.setattr(main_mod.sys, "argv", ["finbreak", "--self-test"])
    monkeypatch.setattr(main_mod.sys, "stdout", None)

    rc = main_mod.main()

    sentinel = out_dir / "finbreak-selftest.txt"
    assert sentinel.exists(), "a windowed build must still record its sentinel"
    assert sentinel.read_text(encoding="utf-8").strip() == "FINBREAK_SELFTEST_OK"
    assert rc == 0


def test_FIBR0132_run_self_test_falls_back_to_stderr_when_stdout_is_none(
    qapp, monkeypatch
):
    """The backstop for any caller that reaches `run_self_test` directly."""
    import io

    from finbreak import _selftest

    err = io.StringIO()
    monkeypatch.setattr(_selftest.sys, "stdout", None)
    monkeypatch.setattr(_selftest.sys, "stderr", err)

    assert _selftest.run_self_test() == 0
    assert err.getvalue().strip() == "FINBREAK_SELFTEST_OK"


@pytest.mark.features
def test_FIBR0326_selftest_covers_cryptography(qapp, monkeypatch):
    """`cryptography` guards every vault unlock and had no check of its own.

    It is a promoted runtime dependency used directly by `keywrap` (AES-GCM,
    the key envelope) and `update_key` (Ed25519, the release signature). It
    loads in the bundle today only because `pdfminer` imports it at module
    scope, pulled in transitively by the pdfplumber check. If pdfminer ever
    defers that import, the OK sentinel goes green on a bundle that cannot
    open any v2 vault — the FIBR-0259 shape exactly: a check list that covers
    the neighbours and misses the one thing the app cannot start without.

    Guards both halves, like the qtnetwork leg above: that `cryptography` is
    IN the ordered list at all, and that its failure is reported under that
    name.
    """
    from finbreak import _selftest

    assert "cryptography" in _selftest.CHECK_NAMES, (
        "cryptography must be in the self-test's check list — it is what "
        "unwraps the vault's data key, and a bundle without it opens nothing"
    )

    monkeypatch.setattr(_selftest, "_check_qt", lambda: None)

    def _boom() -> None:
        raise ImportError("no module named cryptography.hazmat.bindings._rust")

    monkeypatch.setattr(_selftest, "_check_cryptography", _boom)

    out = io.StringIO()
    rc = _selftest.run_self_test(out)

    assert rc != 0, "a missing cryptography must exit non-zero"
    assert out.getvalue().splitlines() == ["FINBREAK_SELFTEST_FAIL: cryptography"], (
        f"expected the cryptography FAIL line only; got:\n{out.getvalue()}"
    )


@pytest.mark.features
def test_FIBR0326_the_cryptography_check_passes_on_a_working_stack():
    """The baseline: on a healthy install the check must be silent. Without
    this, the two falsification legs below could pass against a check that
    always raises."""
    from finbreak import _selftest

    _selftest._check_cryptography()


@pytest.mark.features
def test_FIBR0326_the_cryptography_check_fails_on_a_broken_aes_gcm(monkeypatch):
    """The check must EXERCISE the primitive, not merely import the package —
    a check that cannot fail is the thing this item is about. `keywrap` unwraps
    the vault's data key with AES-GCM, so a round trip that does not round-trip
    must be reported rather than passed over."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from finbreak import _selftest

    monkeypatch.setattr(AESGCM, "decrypt", lambda *a, **k: b"not the plaintext")

    with pytest.raises(RuntimeError, match="round-trip"):
        _selftest._check_cryptography()


@pytest.mark.features
def test_FIBR0326_the_cryptography_check_fails_on_a_broken_ed25519(monkeypatch):
    """The other half: `update_key` verifies the release signature with
    Ed25519, so a verify that accepts a bad signature — or a sign that produces
    one — must reach the sentinel."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from finbreak import _selftest

    # Substituted where the check RESOLVES the name — it imports lazily inside
    # the function. Patching an attribute on Ed25519PrivateKey itself does
    # nothing: it is Rust-backed, and `generate()` hands back a concrete type
    # whose `sign` is not the one that would have been replaced (measured — the
    # first draft of this leg passed a bad signature straight through).
    real = Ed25519PrivateKey.generate()

    class _BadSigner:
        @staticmethod
        def generate():
            return _BadSigner()

        def public_key(self):
            return real.public_key()

        def sign(self, data):
            return b"\x00" * 64

    monkeypatch.setattr(
        "cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey",
        _BadSigner,
    )

    with pytest.raises(InvalidSignature):
        _selftest._check_cryptography()
