"""FIBR-0054 optional in-app auto-update — conformance tests.

See ``spec.md`` in this directory. Pure service/version/asset/installer legs need
no ``qtbot``; the dialog + shell legs use it. No network (injected fake fetcher),
no real signing key (a throwaway test key is monkeypatched in).
"""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from finbreak.errors import FinbreakError, UpdateError, UpdateVerificationError
from finbreak.services import update_fetch, update_installer, update_key
from finbreak.services.update import (
    UpdateInfo,
    UpdateService,
    _parse_version,
    _select_assets,
    _version_gt,
)
from finbreak.services.update_installer import (
    AppImageInstaller,
    _relaunch_command,
    _relaunch_env,
    detect_installer,
    is_update_supported,
)


# --------------------------------------------------------------------------- #
# Fakes shared by the UpdateService legs (no network, no real key)
# --------------------------------------------------------------------------- #
class _FakeFetcher:
    """Stands in for the ``update_fetch`` module: hands back a canned release
    dict and writes canned bytes per URL. Records fetch calls so INV-1 can assert
    the disabled service never phones home."""

    def __init__(self, release=None, blobs=None, fetch_error=None):
        self.release = release
        self.blobs = blobs or {}
        self.fetch_error = fetch_error
        self.fetch_calls = 0

    def fetch_latest_release(self, owner, repo, *, timeout, max_bytes):
        self.fetch_calls += 1
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.release

    def download(self, url, dest, *, max_bytes, timeout):
        from pathlib import Path

        Path(dest).write_bytes(self.blobs[url])


def _release(tag: str) -> dict:
    version = tag[1:] if tag[:1] in ("v", "V") else tag
    app = f"finbreak-{version}-x86_64.AppImage"
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/milnet01/finbreak/releases/tag/{tag}",
        "body": f"### Fixed\n- release notes for {tag}",
        "assets": [
            {"name": app, "browser_download_url": f"https://dl/{app}"},
            {"name": app + ".sig", "browser_download_url": f"https://dl/{app}.sig"},
        ],
    }


def _service(tmp_path, *, installer=None, fetcher=None, current="0.1.0"):
    return UpdateService(
        tmp_path / "window.ini",
        installer,
        fetcher=fetcher,
        current_version=current,
    )


# --------------------------------------------------------------------------- #
# D13 — version grammar + comparison (fail-safe, dependency-free)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0.1.0", (0, 1, 0)),
        ("v0.1.0", (0, 1, 0)),  # leading v stripped
        ("V2.3", (2, 3)),  # leading V stripped
        ("1", (1,)),
        ("10.20.30", (10, 20, 30)),
    ],
)
def test_INV3_parse_version_accepts_well_formed(text, expected):
    assert _parse_version(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",  # empty
        "v",  # just the prefix
        "latest",  # a word
        "v1.2-rc1",  # pre-release suffix
        "1_0.0",  # underscore — int() would accept, isdigit does not
        " 1.0",  # leading space
        "+1.0",  # sign
        "1..0",  # empty middle segment
        "1.0.",  # trailing dot -> empty segment
        "1.0.0-beta",  # suffix
        "١.0",  # arabic-indic digit -> isascii() rejects
    ],
)
def test_INV3_parse_version_rejects_malformed(text):
    assert _parse_version(text) is None


def test_INV3_version_gt_strictly_greater():
    assert _version_gt((0, 1, 1), (0, 1, 0)) is True
    assert _version_gt((1, 0, 0), (0, 9, 9)) is True


def test_INV3_version_gt_not_for_equal_or_older():
    assert _version_gt((0, 1, 0), (0, 1, 0)) is False
    assert _version_gt((0, 1, 0), (0, 1, 1)) is False


def test_INV3_version_gt_zero_pads_shorter_tuple():
    # (0, 1) and (0, 1, 0) are EQUAL after zero-padding — neither is greater.
    assert _version_gt((0, 1), (0, 1, 0)) is False
    assert _version_gt((0, 1, 0), (0, 1)) is False
    assert _version_gt((0, 1, 1), (0, 1)) is True


# --------------------------------------------------------------------------- #
# D14 — asset-selection predicate
# --------------------------------------------------------------------------- #


def _asset(name: str, url: str | None = None) -> dict:
    return {"name": name, "browser_download_url": url or f"https://dl/{name}"}


def test_INV3_select_assets_picks_appimage_and_matching_sig():
    assets = [
        _asset("finbreak-0.1.0-x86_64.AppImage"),
        _asset("finbreak-0.1.0-x86_64.AppImage.sig"),
        _asset("some-other-file.txt"),
    ]
    result = _select_assets(assets)
    assert result == (
        "https://dl/finbreak-0.1.0-x86_64.AppImage",
        "https://dl/finbreak-0.1.0-x86_64.AppImage.sig",
    )


def test_INV3_select_assets_none_when_sig_absent():
    assets = [_asset("finbreak-0.1.0-x86_64.AppImage")]
    assert _select_assets(assets) is None


def test_INV3_select_assets_none_when_appimage_absent():
    assets = [_asset("finbreak-0.1.0-x86_64.AppImage.sig")]
    assert _select_assets(assets) is None


def test_INV3_select_assets_none_when_two_appimages_match():
    assets = [
        _asset("finbreak-0.1.0-x86_64.AppImage"),
        _asset("finbreak-0.1.0-x86_64.AppImage.sig"),
        _asset("finbreak-0.2.0-x86_64.AppImage"),
        _asset("finbreak-0.2.0-x86_64.AppImage.sig"),
    ]
    assert _select_assets(assets) is None


def test_INV3_select_assets_none_on_empty():
    assert _select_assets([]) is None


# --------------------------------------------------------------------------- #
# INV-4 — the signature gate: the placeholder key + the error taxonomy
# --------------------------------------------------------------------------- #
def test_INV4_update_verification_error_is_a_finbreak_error():
    assert issubclass(UpdateVerificationError, FinbreakError)


def test_INV4_public_key_loads_an_ed25519_key():
    key = update_key.public_key()
    assert isinstance(key, Ed25519PublicKey)


def test_INV4_placeholder_key_fails_closed():
    """Until Phase 1's keygen fills the real key, the committed placeholder is
    all-zero bytes: the module imports + ``public_key()`` loads, but no real
    signature verifies against it (fail closed)."""
    from cryptography.exceptions import InvalidSignature

    priv = Ed25519PrivateKey.generate()
    sig = priv.sign(b"finbreak-0.1.0")
    with pytest.raises(InvalidSignature):
        update_key.public_key().verify(sig, b"finbreak-0.1.0")


# --------------------------------------------------------------------------- #
# INV-7 / INV-5 / INV-6 — the AppImage installer (platform seam, D6/D8)
# --------------------------------------------------------------------------- #
def test_INV7_no_appimage_env_means_feature_inert(monkeypatch):
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert detect_installer() is None
    assert is_update_supported() is False


def test_INV7_appimage_env_pointing_at_missing_file_is_inert(monkeypatch, tmp_path):
    monkeypatch.setenv("APPIMAGE", str(tmp_path / "does-not-exist.AppImage"))
    assert detect_installer() is None
    assert is_update_supported() is False


def test_INV7_real_appimage_env_yields_installer(monkeypatch, tmp_path):
    appimage = tmp_path / "finbreak-0.1.0-x86_64.AppImage"
    appimage.write_bytes(b"OLD-APP")
    monkeypatch.setenv("APPIMAGE", str(appimage))
    installer = detect_installer()
    assert isinstance(installer, AppImageInstaller)
    assert installer.target_path() == appimage
    assert installer.can_self_update() is True
    assert is_update_supported() is True


def _capture_relaunch(monkeypatch) -> dict:
    """Stub the detached relaunch (``subprocess.Popen``) + the hard exit
    (``os._exit``) so ``apply()``'s post-swap steps are observable without
    spawning a process or killing pytest. Records call order + the Popen args."""
    record: dict = {"order": []}

    def fake_popen(argv, **kwargs):
        record["argv"] = argv
        record["kwargs"] = kwargs
        record["order"].append("relaunch")
        return object()

    def fake_exit(code):
        record["exit_code"] = code
        record["order"].append("exit")

    monkeypatch.setattr(update_installer.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(os, "_exit", fake_exit)
    # Default: logless + hermetic — no write to the real per-user data dir. The
    # dedicated logging test overrides this with a tmp path.
    monkeypatch.setattr(update_installer, "_relaunch_log_path", lambda: None)
    return record


def test_INV5_apply_swaps_bytes_and_marks_executable(monkeypatch, tmp_path):
    appimage = tmp_path / "app.AppImage"
    appimage.write_bytes(b"OLD-APP")
    new_file = tmp_path / "finbreak-update-xyz.AppImage"
    new_file.write_bytes(b"NEW-APP")
    _capture_relaunch(monkeypatch)

    AppImageInstaller(appimage).apply(new_file, lambda: None)

    assert appimage.read_bytes() == b"NEW-APP"
    assert os.stat(appimage).st_mode & 0o111  # executable
    assert not new_file.exists()  # moved, not copied


def test_INV6_key_wiped_after_replace_before_relaunch(monkeypatch, tmp_path):
    appimage = tmp_path / "app.AppImage"
    appimage.write_bytes(b"OLD-APP")
    new_file = tmp_path / "new.AppImage"
    new_file.write_bytes(b"NEW-APP")
    record = _capture_relaunch(monkeypatch)

    AppImageInstaller(appimage).apply(new_file, lambda: record["order"].append("wipe"))

    # wipe strictly between the replace and the relaunch, then the hard exit.
    assert record["order"] == ["wipe", "relaunch", "exit"]
    assert appimage.read_bytes() == b"NEW-APP"  # the replace happened first


def test_relaunch_is_detached_new_session_with_pyinstaller_reset(monkeypatch, tmp_path):
    # The relaunch spawns a DETACHED WAITER (in a NEW SESSION) that blocks until
    # this process has fully exited, then execs the swapped $APPIMAGE with a reset
    # PyInstaller environment + the AppImage markers dropped, so the new onefile
    # re-extracts cleanly instead of dying as a "worker subprocess" against the
    # still-mounted old image (the closed-but-didn't-reopen bug).
    appimage = tmp_path / "app.AppImage"
    appimage.write_bytes(b"OLD-APP")
    new_file = tmp_path / "new.AppImage"
    new_file.write_bytes(b"NEW-APP")
    for stale in ("APPDIR", "APPIMAGE", "ARGV0"):
        monkeypatch.setenv(stale, "/old/mount/value")
    monkeypatch.setenv("HOME", "/home/keep")  # an unrelated var must pass through
    record = _capture_relaunch(monkeypatch)

    AppImageInstaller(appimage).apply(new_file, lambda: None)

    # A /bin/sh waiter, not the image directly — the script waits on THIS pid then
    # execs the swapped image (asserted in detail by the pure _relaunch_command test).
    argv = record["argv"]
    assert argv[:2] == ["/bin/sh", "-c"]
    assert str(appimage) in argv[2] and f"kill -0 {os.getpid()}" in argv[2]
    kwargs = record["kwargs"]
    assert kwargs["start_new_session"] is True  # survives this process's exit
    env = kwargs["env"]
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"  # official restart signal
    assert "APPDIR" not in env and "APPIMAGE" not in env and "ARGV0" not in env
    assert env["HOME"] == "/home/keep"  # unrelated vars are preserved
    assert record["exit_code"] == 0  # hard-exit this process after spawning


def test_relaunch_env_restores_leaked_loader_path_from_orig(monkeypatch):
    # The frozen onefile app runs with LD_LIBRARY_PATH pointing at its private _MEI
    # bundle dir; inherited by the /bin/sh waiter, the SYSTEM shell then loads the
    # app's bundled libs (an incompatible libreadline) and dies on a symbol lookup —
    # the real 0.1.6->0.1.7 "closed but didn't reopen" (relaunch log evidence).
    # PyInstaller saves the pre-launch value in LD_LIBRARY_PATH_ORIG; restore it so
    # the waiter runs against the SYSTEM libraries.
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIabc123")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib:/usr/local/lib")
    env = _relaunch_env()
    assert env["LD_LIBRARY_PATH"] == "/usr/lib:/usr/local/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in env


def test_relaunch_env_drops_leaked_loader_path_when_no_original(monkeypatch):
    # No <VAR>_ORIG (there was no LD_LIBRARY_PATH / LD_PRELOAD before the frozen app
    # set it) -> drop it entirely, so the system /bin/sh loads system libraries.
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIabc123")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setenv("LD_PRELOAD", "/tmp/_MEIabc123/libpreload.so")
    monkeypatch.delenv("LD_PRELOAD_ORIG", raising=False)
    env = _relaunch_env()
    assert "LD_LIBRARY_PATH" not in env
    assert "LD_PRELOAD" not in env


def test_relaunch_command_waits_for_old_pid_then_execs_quoted_image():
    # The waiter: poll `kill -0 <pid>` until the old process is gone (its FUSE
    # mount unmounted + PyInstaller _MEI dir cleaned), THEN exec the image. The
    # path is shell-quoted so a space in the AppImage path can't break the script.
    cmd = _relaunch_command("/opt/My Apps/finbreak.AppImage", 4242)
    assert cmd[:2] == ["/bin/sh", "-c"]
    script = cmd[2]
    assert "kill -0 4242" in script  # blocks on the OLD pid
    assert script.rstrip().count("exec ") == 1  # replaces sh with the image
    # exec target is quoted (space-bearing path survives) and comes AFTER the loop.
    assert "'/opt/My Apps/finbreak.AppImage'" in script
    assert script.index("kill -0 4242") < script.index("exec ")


def test_relaunch_writes_diagnostic_log(monkeypatch, tmp_path):
    # A future silent relaunch failure must leave evidence: apply() appends a
    # timestamped line to the relaunch log naming the pid it waits on and the image.
    appimage = tmp_path / "app.AppImage"
    appimage.write_bytes(b"OLD-APP")
    new_file = tmp_path / "new.AppImage"
    new_file.write_bytes(b"NEW-APP")
    log = tmp_path / "update-relaunch.log"
    record = _capture_relaunch(monkeypatch)
    monkeypatch.setattr(update_installer, "_relaunch_log_path", lambda: log)

    AppImageInstaller(appimage).apply(new_file, lambda: None)

    assert record["order"] == ["relaunch", "exit"]  # still relaunched + exited
    text = log.read_text()
    assert str(appimage) in text and str(os.getpid()) in text


def test_INV6_failed_replace_leaves_key_unwiped_and_original_intact(
    monkeypatch, tmp_path
):
    appimage = tmp_path / "app.AppImage"
    appimage.write_bytes(b"OLD-APP")
    new_file = tmp_path / "new.AppImage"
    new_file.write_bytes(b"NEW-APP")
    record = _capture_relaunch(monkeypatch)

    def boom(src, dst):
        raise OSError("ENOSPC: no space left on device")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(UpdateError):
        AppImageInstaller(appimage).apply(
            new_file, lambda: record["order"].append("wipe")
        )

    assert record["order"] == []  # neither wipe, relaunch, nor exit ran (INV-6/11)
    assert appimage.read_bytes() == b"OLD-APP"  # original byte-for-byte intact
    assert not new_file.exists()  # the temp was cleaned up (INV-5)


# --------------------------------------------------------------------------- #
# INV-10 — update_fetch (the sole networked module): resource-bounded, https-only
# --------------------------------------------------------------------------- #
class _FakeHTTPResponse:
    """A minimal urlopen() stand-in: a context manager whose read(n) yields the
    payload in <=n-byte slices (so the byte-cap logic sees a real stream)."""

    def __init__(self, payload: bytes):
        self._payload = payload
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._payload) - self._offset
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc) -> None:
        return None


def _fake_urlopen(payload: bytes):
    def opener(request, timeout=None, context=None):
        return _FakeHTTPResponse(payload)

    return opener


def test_ssl_context_uses_bundled_ca_regardless_of_system_paths(monkeypatch):
    """The frozen AppImage must verify TLS on ANY distro: the SSL context loads
    CAs from the BUNDLED certifi set, not the host's (possibly absent or
    differently-placed) store. Regression for the v0.1.0 no-update-prompt bug —
    the AppImage was frozen on Debian, whose OpenSSL cert path openSUSE lacks, so
    the HTTPS check failed cert verification and INV-11 silently swallowed it."""
    import ssl as _ssl

    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/nope.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent")
    ctx = update_fetch._ssl_context()
    assert isinstance(ctx, _ssl.SSLContext)
    # CAs are loaded despite the broken system paths (they came from certifi).
    assert ctx.cert_store_stats()["x509"] > 0


def test_download_writes_bytes_under_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(
        update_fetch.urllib.request, "urlopen", _fake_urlopen(b"HELLO-APPIMAGE")
    )
    dest = tmp_path / "out.AppImage"
    update_fetch.download(
        "https://dl/finbreak.AppImage", dest, max_bytes=1024, timeout=5
    )
    assert dest.read_bytes() == b"HELLO-APPIMAGE"


def test_INV10_download_aborts_over_cap_and_cleans_temp(monkeypatch, tmp_path):
    monkeypatch.setattr(
        update_fetch.urllib.request, "urlopen", _fake_urlopen(b"X" * 500)
    )
    dest = tmp_path / "out.AppImage"
    with pytest.raises(ValueError):
        update_fetch.download("https://dl/big", dest, max_bytes=200, timeout=5)
    assert not dest.exists()  # the partial temp is deleted on abort


def test_INV10_download_refuses_non_https(tmp_path):
    with pytest.raises(ValueError):
        update_fetch.download(
            "http://dl/insecure", tmp_path / "x", max_bytes=200, timeout=5
        )


def test_fetch_latest_release_parses_json(monkeypatch):
    payload = b'{"tag_name": "v0.1.0", "assets": []}'
    monkeypatch.setattr(update_fetch.urllib.request, "urlopen", _fake_urlopen(payload))
    result = update_fetch.fetch_latest_release(
        "milnet01", "finbreak", timeout=5, max_bytes=1024
    )
    assert result["tag_name"] == "v0.1.0"


def test_INV10_fetch_latest_release_aborts_over_cap(monkeypatch):
    payload = b'{"tag_name": "v0.1.0"}' + b" " * 500
    monkeypatch.setattr(update_fetch.urllib.request, "urlopen", _fake_urlopen(payload))
    with pytest.raises(ValueError):
        update_fetch.fetch_latest_release(
            "milnet01", "finbreak", timeout=5, max_bytes=50
        )


# --------------------------------------------------------------------------- #
# INV-1 / INV-2 — opt-in, no vault; the check is the only deliberate egress
# --------------------------------------------------------------------------- #
def test_INV1_disabled_service_never_calls_fetcher(tmp_path):
    fetcher = _FakeFetcher(release=_release("v0.1.1"))
    svc = _service(tmp_path, fetcher=fetcher)  # check_for_updates absent -> off
    assert svc.is_enabled() is False
    assert svc.check_for_update() is None
    assert fetcher.fetch_calls == 0  # a fresh install never phones home


def test_INV1_enabled_service_calls_fetcher_and_persists_flag(tmp_path):
    fetcher = _FakeFetcher(release=_release("v0.1.1"))
    svc = _service(tmp_path, fetcher=fetcher)
    svc.set_enabled(True)
    assert svc.is_enabled() is True
    assert svc.check_for_update() is not None
    assert fetcher.fetch_calls == 1
    # persisted to the plaintext INI — a fresh service over the same file agrees
    assert _service(tmp_path, fetcher=fetcher).is_enabled() is True


@pytest.mark.parametrize("bad", ["false", "yes", "1", ""])
def test_INV1_malformed_or_false_flag_is_off(tmp_path, bad):
    from PySide6.QtCore import QSettings

    settings = QSettings(str(tmp_path / "window.ini"), QSettings.Format.IniFormat)
    settings.setValue("check_for_updates", bad)
    settings.sync()
    assert _service(tmp_path, fetcher=_FakeFetcher()).is_enabled() is False


def test_INV2_check_needs_no_vault_reference(tmp_path):
    # UpdateService is constructed with NO AuthService/vault — the check runs on
    # the plaintext INI + injected fetcher alone (it can run while locked).
    fetcher = _FakeFetcher(release=_release("v0.1.1"))
    svc = _service(tmp_path, fetcher=fetcher)
    svc.set_enabled(True)
    assert svc.check_for_update() is not None
    assert not hasattr(svc, "vault")
    assert not hasattr(svc, "_vault")


# --------------------------------------------------------------------------- #
# INV-3 / INV-8 / INV-11 — the check's decision + skip persistence + safe failure
# --------------------------------------------------------------------------- #
def _enabled_service(tmp_path, release, current="0.1.0"):
    svc = _service(tmp_path, fetcher=_FakeFetcher(release=release), current=current)
    svc.set_enabled(True)
    return svc


def test_INV3_newer_release_is_offered(tmp_path):
    info = _enabled_service(tmp_path, _release("v0.1.1")).check_for_update()
    assert isinstance(info, UpdateInfo)
    assert info.version == "0.1.1"  # leading v stripped
    assert info.appimage_url == "https://dl/finbreak-0.1.1-x86_64.AppImage"
    assert info.sig_url == "https://dl/finbreak-0.1.1-x86_64.AppImage.sig"
    assert info.notes == "### Fixed\n- release notes for v0.1.1"  # the release body


def test_INV3_equal_and_older_are_not_offered(tmp_path):
    assert _enabled_service(tmp_path, _release("v0.1.0")).check_for_update() is None
    assert _enabled_service(tmp_path, _release("v0.0.9")).check_for_update() is None


def test_INV3_malformed_tag_is_not_offered(tmp_path):
    assert _enabled_service(tmp_path, _release("v1.2-rc1")).check_for_update() is None


def test_INV3_missing_sig_asset_is_not_offered(tmp_path):
    release = _release("v0.1.1")
    release["assets"] = [release["assets"][0]]  # drop the .sig
    assert _enabled_service(tmp_path, release).check_for_update() is None


def test_INV8_skip_persists_later_does_not(tmp_path):
    svc = _enabled_service(tmp_path, _release("v0.1.1"))
    assert svc.check_for_update() is not None  # offered before skipping
    svc.skip_version("0.1.1")
    assert svc.check_for_update() is None  # same version now suppressed
    # a fresh service over the same INI still suppresses it (persisted)
    assert _enabled_service(tmp_path, _release("v0.1.1")).check_for_update() is None
    # ...but a newer version is still offered
    assert _enabled_service(tmp_path, _release("v0.1.2")).check_for_update() is not None


def test_INV11_check_swallows_fetcher_errors(tmp_path):
    fetcher = _FakeFetcher(fetch_error=OSError("name resolution failed"))
    svc = _service(tmp_path, fetcher=fetcher)
    svc.set_enabled(True)
    assert svc.check_for_update() is None  # no propagation
    assert fetcher.fetch_calls == 1


# --------------------------------------------------------------------------- #
# INV-4 — download_and_verify: only an Ed25519-signed download is returned
# --------------------------------------------------------------------------- #
def _signing_setup(monkeypatch, blob: bytes, *, sign: bytes | None = None):
    """A throwaway keypair with its public half monkeypatched in; sign *blob*
    (or *sign* if given, to forge a mismatch)."""
    priv = Ed25519PrivateKey.generate()
    monkeypatch.setattr(update_key, "public_key", lambda: priv.public_key())
    return priv.sign(sign if sign is not None else blob)


def test_INV4_good_signature_returns_verified_path(monkeypatch, tmp_path):
    blob = b"REAL-APPIMAGE-BYTES"
    sig = _signing_setup(monkeypatch, blob)
    fetcher = _FakeFetcher(
        blobs={
            "https://dl/finbreak-0.1.1-x86_64.AppImage": blob,
            "https://dl/finbreak-0.1.1-x86_64.AppImage.sig": sig,
        }
    )
    installer = AppImageInstaller(tmp_path / "app.AppImage")
    svc = _service(tmp_path, installer=installer, fetcher=fetcher)
    update_info = UpdateInfo(
        version="0.1.1",
        appimage_url="https://dl/finbreak-0.1.1-x86_64.AppImage",
        sig_url="https://dl/finbreak-0.1.1-x86_64.AppImage.sig",
        notes="notes",
    )
    verified = svc.download_and_verify(update_info)
    assert verified.read_bytes() == blob
    assert verified.parent == tmp_path  # staged next to $APPIMAGE (same fs, INV-5)


def _dv_service(monkeypatch, tmp_path, blob, sig):
    fetcher = _FakeFetcher(
        blobs={
            "https://dl/app": blob,
            "https://dl/sig": sig,
        }
    )
    installer = AppImageInstaller(tmp_path / "app.AppImage")
    svc = _service(tmp_path, installer=installer, fetcher=fetcher)
    info = UpdateInfo(
        version="0.1.1",
        appimage_url="https://dl/app",
        sig_url="https://dl/sig",
        notes="notes",
    )
    return svc, info


def test_INV4_tampered_blob_rejected_and_temp_removed(monkeypatch, tmp_path):
    blob = b"REAL-APPIMAGE-BYTES"
    sig = _signing_setup(monkeypatch, blob)
    svc, info = _dv_service(monkeypatch, tmp_path, blob + b"!", sig)  # 1-byte tamper
    with pytest.raises(UpdateVerificationError):
        svc.download_and_verify(info)
    # no temp left behind in the $APPIMAGE directory
    assert list(tmp_path.glob("finbreak-update-*")) == []


def test_INV4_tampered_signature_rejected(monkeypatch, tmp_path):
    blob = b"REAL-APPIMAGE-BYTES"
    sig = _signing_setup(monkeypatch, blob)
    forged = bytes((sig[0] ^ 0x01,)) + sig[1:]  # flip one sig bit
    svc, info = _dv_service(monkeypatch, tmp_path, blob, forged)
    with pytest.raises(UpdateVerificationError):
        svc.download_and_verify(info)
    assert list(tmp_path.glob("finbreak-update-*")) == []


# --------------------------------------------------------------------------- #
# INV-9 / D7 — the prompt (non-blocking, three signals, busy state) + workers
# --------------------------------------------------------------------------- #
def test_INV9_update_dialog_never_uses_exec():
    """The FIBR-0065 grep leg: the prompt must never open a nested event loop."""
    from pathlib import Path

    import finbreak.ui.update_dialog as module

    source = Path(module.__file__).read_text()
    assert ".exec(" not in source


def _prompt(qtbot):
    from finbreak.ui.update_dialog import UpdateDialog

    dialog = UpdateDialog("0.1.0", "0.1.1", "notes", None)
    qtbot.addWidget(dialog)
    return dialog


def test_prompt_later_emits_and_does_not_persist(qtbot):
    dialog = _prompt(qtbot)
    with qtbot.waitSignal(dialog.later, timeout=1000):
        dialog._on_later()


def test_prompt_skip_emits(qtbot):
    dialog = _prompt(qtbot)
    with qtbot.waitSignal(dialog.skip, timeout=1000):
        dialog._on_skip()


def test_prompt_shows_release_notes_inline(qtbot):
    from PySide6.QtWidgets import QPushButton, QTextBrowser

    from finbreak.ui.update_dialog import UpdateDialog

    dialog = UpdateDialog("0.1.4", "0.1.5", "### Fixed\n- Reopens itself now", None)
    qtbot.addWidget(dialog)

    notes = dialog.findChild(QTextBrowser, "update_notes")
    assert notes is not None
    assert "Reopens itself now" in notes.toPlainText()  # the body is shown inline
    assert not notes.isHidden()
    assert notes.openExternalLinks() is False  # read-only, no egress on a link click
    # the old "What's new" browser button is gone
    assert all(b.text() != "What's new" for b in dialog.findChildren(QPushButton))


def test_prompt_hides_notes_when_body_empty(qtbot):
    from PySide6.QtWidgets import QTextBrowser

    from finbreak.ui.update_dialog import UpdateDialog

    dialog = UpdateDialog("0.1.4", "0.1.5", "   ", None)  # blank/whitespace body
    qtbot.addWidget(dialog)

    notes = dialog.findChild(QTextBrowser, "update_notes")
    assert notes is None or notes.isHidden()  # no empty panel


def test_INV9_prompt_update_now_emits_and_stays_open_busy(qtbot):
    dialog = _prompt(qtbot)
    with qtbot.waitSignal(dialog.update_now, timeout=1000):
        dialog._on_update_now()
    # it does NOT accept()/reject() — it stays open in the busy state (D15)
    assert dialog.result() == 0  # neither Accepted nor Rejected
    assert not dialog._later_button.isEnabled()  # buttons disabled while busy
    assert not dialog._update_button.isEnabled()


def test_prompt_shows_both_versions(qtbot):
    from PySide6.QtWidgets import QLabel

    dialog = _prompt(qtbot)
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "0.1.0" in texts and "0.1.1" in texts


class _StubCheckService:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def check_for_update(self, *, force=False):
        if self._error is not None:
            raise self._error
        return self._result


def test_D7_check_worker_emits_found(qtbot):
    from finbreak.ui._update_worker import UpdateCheckWorker

    info = UpdateInfo("0.1.1", "a", "b", "c")
    worker = UpdateCheckWorker(_StubCheckService(result=info))
    seen: list = []
    worker.found.connect(lambda i: seen.append(("found", i)))
    worker.none.connect(lambda: seen.append(("none",)))
    worker.run()
    assert seen == [("found", info)]


def test_D7_check_worker_emits_none(qtbot):
    from finbreak.ui._update_worker import UpdateCheckWorker

    worker = UpdateCheckWorker(_StubCheckService(result=None))
    seen: list = []
    worker.found.connect(lambda i: seen.append("found"))
    worker.none.connect(lambda: seen.append("none"))
    worker.run()
    assert seen == ["none"]


def test_D7_check_worker_emits_failed_on_unexpected_error(qtbot):
    from finbreak.ui._update_worker import UpdateCheckWorker

    worker = UpdateCheckWorker(_StubCheckService(error=RuntimeError("boom")))
    seen: list = []
    worker.failed.connect(lambda exc: seen.append(exc))
    worker.run()
    assert isinstance(seen[0], RuntimeError)


class _StubDownloadService:
    def __init__(self, path=None, error=None):
        self._path = path
        self._error = error

    def download_and_verify(self, info):
        if self._error is not None:
            raise self._error
        return self._path


def test_D7_download_worker_emits_ready(qtbot, tmp_path):
    from finbreak.ui._update_worker import DownloadWorker

    verified = tmp_path / "verified.AppImage"
    worker = DownloadWorker(
        _StubDownloadService(path=verified), UpdateInfo("0.1.1", "", "", "")
    )
    seen: list = []
    worker.ready.connect(lambda p: seen.append(p))
    worker.run()
    assert seen == [verified]


def test_D7_download_worker_emits_failed(qtbot):
    from finbreak.ui._update_worker import DownloadWorker

    worker = DownloadWorker(
        _StubDownloadService(error=UpdateVerificationError("bad")),
        UpdateInfo("0.1.1", "", "", ""),
    )
    seen: list = []
    worker.failed.connect(lambda exc: seen.append(exc))
    worker.run()
    assert isinstance(seen[0], UpdateVerificationError)


# --------------------------------------------------------------------------- #
# D15 / INV-9 — the shell's pending-offer lifecycle + Settings checkbox
# --------------------------------------------------------------------------- #
from PySide6.QtWidgets import QCheckBox  # noqa: E402

from conftest import _PW  # noqa: E402
from finbreak.services.auth import AuthService  # noqa: E402
from finbreak.ui.main_window import MainWindow  # noqa: E402
from finbreak.ui.settings import SettingsDialog  # noqa: E402
from finbreak.ui.update_dialog import UpdateDialog  # noqa: E402


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


class _FakeUpdateService:
    """A stand-in UpdateService the shell can be built with — no network, no
    QSettings — so the D15 lifecycle can be driven deterministically."""

    def __init__(self, info=None, enabled=True, verified_path=None):
        self._info = info
        self._enabled = enabled
        self._verified_path = verified_path
        self.skipped: list[str] = []

    def is_enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        self._enabled = enabled

    def check_for_update(self, *, force=False):
        return self._info

    def skip_version(self, version):
        self.skipped.append(version)

    def download_and_verify(self, info):
        return self._verified_path


class _FakeInstaller:
    def __init__(self, target):
        self._target = target
        self.applied: list = []

    def can_self_update(self):
        return True

    def target_path(self):
        return self._target

    def apply(self, new_file, on_before_exec):
        self.applied.append((new_file, on_before_exec))


def _updater_shell(qtbot, service, *, info=None, enabled=True, installer=None):
    updater = _FakeUpdateService(info=info, enabled=enabled)
    window = MainWindow(service, update_service=updater, installer=installer)
    qtbot.addWidget(window)
    return window, updater


def _sample_info():
    return UpdateInfo(
        version="0.1.1",
        appimage_url="https://dl/app",
        sig_url="https://dl/sig",
        notes="notes",
    )


def test_D15_found_while_locked_defers_offer_until_unlock(qtbot, service, tmp_path):
    info = _sample_info()
    installer = _FakeInstaller(tmp_path / "app.AppImage")
    window, _ = _updater_shell(qtbot, service, info=info, installer=installer)

    # a found result arrives while the shell is still locked (unlock dialog open)
    window._on_update_found(info)
    assert window._pending_update is info
    assert not isinstance(window._dialog, UpdateDialog)  # no prompt over the lock

    # unlocking releases the held offer
    window._enter_unlocked()
    assert isinstance(window._dialog, UpdateDialog)
    assert window._pending_update is None  # shown at most once


def test_D15_skip_persists_and_no_reprompt_after_relock(qtbot, service, tmp_path):
    info = _sample_info()
    installer = _FakeInstaller(tmp_path / "app.AppImage")
    window, updater = _updater_shell(qtbot, service, info=info, installer=installer)

    window._enter_unlocked()
    window._on_update_found(info)
    assert isinstance(window._dialog, UpdateDialog)
    window._on_update_skip()
    assert updater.skipped == ["0.1.1"]
    assert not isinstance(window._dialog, UpdateDialog)  # torn down

    # The offer was cleared on skip, so the next unlock's offer check (the tail of
    # _enter_unlocked) re-shows nothing this launch (D15 — shown at most once).
    assert window._pending_update is None
    window._maybe_show_pending_offer()
    assert not isinstance(window._dialog, UpdateDialog)


def test_INV9_download_ready_after_prompt_gone_does_not_apply(qtbot, service, tmp_path):
    info = _sample_info()
    installer = _FakeInstaller(tmp_path / "app.AppImage")
    verified = tmp_path / "finbreak-update-abc.AppImage"
    verified.write_bytes(b"NEW")
    window, _ = _updater_shell(qtbot, service, info=info, installer=installer)

    window._enter_unlocked()
    window._on_update_found(info)
    prompt = window._dialog
    window._teardown_dialog()  # an auto-lock tears the prompt down mid-download

    window._on_download_ready(verified, prompt)
    assert installer.applied == []  # INV-9: the stale result is dropped
    assert not verified.exists()  # ...and the orphan temp is unlinked


def test_INV6_download_ready_applies_with_key_wipe_callback(qtbot, service, tmp_path):
    info = _sample_info()
    installer = _FakeInstaller(tmp_path / "app.AppImage")
    verified = tmp_path / "finbreak-update-abc.AppImage"
    verified.write_bytes(b"NEW")
    window, _ = _updater_shell(qtbot, service, info=info, installer=installer)

    window._enter_unlocked()
    window._on_update_found(info)
    prompt = window._dialog

    window._on_download_ready(verified, prompt)
    assert len(installer.applied) == 1
    new_file, on_before_exec = installer.applied[0]
    assert new_file == verified
    assert on_before_exec == service.on_about_to_quit  # the key-wipe (INV-6)


def test_INV7_settings_checkbox_disabled_when_unsupported(qtbot, service):
    dialog = SettingsDialog(
        service, "ZAR", update_enabled=False, update_supported=False
    )
    qtbot.addWidget(dialog)
    checkbox = dialog.findChild(QCheckBox, "settings_check_updates")
    assert checkbox is not None
    assert not checkbox.isEnabled()
    assert checkbox.toolTip() != ""


def test_settings_checkbox_reflects_and_exposes_state(qtbot, service):
    dialog = SettingsDialog(service, "ZAR", update_enabled=True, update_supported=True)
    qtbot.addWidget(dialog)
    checkbox = dialog.findChild(QCheckBox, "settings_check_updates")
    assert checkbox.isEnabled()
    assert checkbox.isChecked()
    assert dialog.update_enabled() is True


def test_settings_save_persists_update_flag(qtbot, service, tmp_path):
    info = _sample_info()
    window, updater = _updater_shell(qtbot, service, info=info, enabled=False)
    window._enter_unlocked()
    window._open_settings()
    dialog = window._dialog
    checkbox = dialog.findChild(QCheckBox, "settings_check_updates")
    checkbox.setChecked(True)
    dialog._on_save()
    assert updater.is_enabled() is True  # the shell persisted the toggle


# --------------------------------------------------------------------------- #
# INV-14 (Phase 1) — the signing scripts round-trip through the app's gate,
# and no private-key material is ever tracked in the repo.
# --------------------------------------------------------------------------- #
import base64  # noqa: E402
import importlib.util  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

from cryptography.exceptions import InvalidSignature  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_script(filename: str):
    """Import a ``scripts/*.py`` helper by path (they aren't a package); their
    keygen/sign side effects live under ``if __name__ == '__main__'`` so import
    is pure."""
    path = _SCRIPTS_DIR / filename
    mod_name = "finbreak_script_" + filename.replace("-", "_").removesuffix(".py")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_INV14_signing_scripts_roundtrip(tmp_path):
    """gen-signing-key.py's public key + sign-release.py's ``.sig`` verify
    through the EXACT primitives the app uses (``update_key`` b64-decode +
    ``from_public_bytes``; ``.verify(sig, data)``) — a tamper is rejected."""
    gen = _load_script("gen-signing-key.py")
    sign = _load_script("sign-release.py")

    key_path = tmp_path / "finbreak-signing.key"
    pub_b64 = gen.generate_keypair(key_path)

    # The public key is exactly what services/update_key.py decodes + loads.
    pub_raw = base64.b64decode(pub_b64)
    assert len(pub_raw) == 32
    public_key = Ed25519PublicKey.from_public_bytes(pub_raw)

    artifact = tmp_path / "finbreak-0.1.0-x86_64.AppImage"
    artifact.write_bytes(b"pretend appimage bytes " * 100)
    sig_path = sign.sign_artifact(key_path, artifact)

    # D1/D14: the sig sits at <artifact>.sig and is the raw 64-byte Ed25519 sig.
    assert sig_path.name == artifact.name + ".sig"
    sig = sig_path.read_bytes()
    assert len(sig) == 64

    public_key.verify(sig, artifact.read_bytes())  # the app's gate accepts it
    with pytest.raises(InvalidSignature):
        public_key.verify(sig, b"tampered bytes")


def test_INV14_no_private_key_material_is_tracked():
    """No ``*.key`` file and no PEM private-key block is git-tracked (the private
    signing key must never enter the repo). Marker assembled at runtime so this
    test file itself doesn't trip the scan."""
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    pem_marker = ("-----BEGIN " + "PRIVATE KEY-----").encode()
    for rel in tracked:
        assert not rel.endswith(".key"), f"private-key file is tracked: {rel}"
        data = (_REPO_ROOT / rel).read_bytes()
        assert pem_marker not in data, f"PEM private-key block tracked in: {rel}"


# --------------------------------------------------------------------------- #
# Help → Check for updates — a manual, on-demand check that gives feedback on
# every outcome and runs even if the startup setting is off (the click is
# consent). Surfaced dogfooding v0.1.0.
# --------------------------------------------------------------------------- #
def test_manual_check_forces_past_the_disabled_gate(tmp_path):
    """A forced check queries even when the startup opt-in is off — an explicit
    Help → Check-for-updates click is its own consent (still no fetch on the
    silent startup path when disabled, INV-1)."""
    fetcher = _FakeFetcher(release=_release("v0.1.1"))
    svc = _service(tmp_path, fetcher=fetcher, current="0.1.0")
    assert svc.is_enabled() is False
    assert svc.check_for_update() is None  # startup path stays gated (INV-1)
    assert fetcher.fetch_calls == 0
    info = svc.check_for_update(force=True)  # manual path bypasses the gate
    assert info is not None and info.version == "0.1.1"
    assert fetcher.fetch_calls == 1


def test_manual_check_unsupported_build_tells_the_user(qtbot, service, monkeypatch):
    window, _ = _updater_shell(qtbot, service, installer=None)  # not an AppImage
    shown = []
    monkeypatch.setattr(
        "finbreak.ui.main_window.QMessageBox.information",
        lambda *a, **k: shown.append(a),
    )
    window._check_for_updates_now()
    assert shown, "an unsupported build should say updates aren't available"


def test_manual_check_supported_starts_a_worker(qtbot, service, tmp_path, monkeypatch):
    # Silence the async "up to date" info dialog (the fake returns no update) so
    # the worker thread's outcome doesn't block on a real modal.
    monkeypatch.setattr(
        "finbreak.ui.main_window.QMessageBox.information", lambda *a, **k: None
    )
    installer = _FakeInstaller(tmp_path / "app.AppImage")
    window, _ = _updater_shell(qtbot, service, info=None, installer=installer)
    window._check_for_updates_now()
    assert window._manual_check_worker is not None  # an off-thread check started
    window._manual_check_worker.wait(2000)  # let the thread finish cleanly


def test_manual_check_up_to_date_shows_info(qtbot, service, monkeypatch):
    window, _ = _updater_shell(qtbot, service)
    shown = []
    monkeypatch.setattr(
        "finbreak.ui.main_window.QMessageBox.information",
        lambda *a, **k: shown.append(a),
    )
    window._on_manual_check_up_to_date()
    assert shown, "an up-to-date result should be reported to the user"


def test_manual_check_error_warns(qtbot, service, monkeypatch):
    window, _ = _updater_shell(qtbot, service)
    warned = []
    monkeypatch.setattr(
        "finbreak.ui.main_window.QMessageBox.warning",
        lambda *a, **k: warned.append(a),
    )
    window._on_manual_check_error(RuntimeError("boom"))
    assert warned, "a failed manual check should warn the user"
