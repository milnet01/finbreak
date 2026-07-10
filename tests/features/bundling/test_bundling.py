"""FIBR-0003 INV-1/INV-6 (+ INV-2/INV-3) — bundling smoke-test.

Enforces docs/specs/FIBR-0003.md. The fast guards run the real
`python -m finbreak` CLI in a subprocess (offscreen Qt) and unit-test the
`_selftest` FAIL path; the integration test drives `scripts/build-smoke.sh`
and is opt-in so the everyday gate never blocks on a multi-minute build.
See tests/features/bundling/spec.md.
"""

import io
import os
import shutil
import subprocess
import sys
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


@pytest.mark.features
def test_INV1_selftest_fail_names_the_broken_stack(monkeypatch):
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
def test_INV1_selftest_fail_names_argon2(monkeypatch):
    """The FIBR-0004 argon2 leg names itself on failure (all earlier stacks pass)."""
    from finbreak import _selftest

    monkeypatch.setattr(_selftest, "_check_qt", lambda: None)
    monkeypatch.setattr(_selftest, "_check_sqlcipher", lambda: None)
    monkeypatch.setattr(_selftest, "_check_pikepdf", lambda: None)

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
def test_INV1_selftest_fail_names_ofxparse(monkeypatch):
    """The FIBR-0008 ofxparse leg names itself on failure (all earlier stacks pass)."""
    from finbreak import _selftest

    monkeypatch.setattr(_selftest, "_check_qt", lambda: None)
    monkeypatch.setattr(_selftest, "_check_sqlcipher", lambda: None)
    monkeypatch.setattr(_selftest, "_check_pikepdf", lambda: None)
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
