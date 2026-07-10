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
from finbreak.services import update_fetch, update_key
from finbreak.services.update import (
    UpdateInfo,
    UpdateService,
    _parse_version,
    _select_assets,
    _version_gt,
)
from finbreak.services.update_installer import (
    AppImageInstaller,
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


def test_INV5_apply_swaps_bytes_and_marks_executable(monkeypatch, tmp_path):
    appimage = tmp_path / "app.AppImage"
    appimage.write_bytes(b"OLD-APP")
    new_file = tmp_path / "finbreak-update-xyz.AppImage"
    new_file.write_bytes(b"NEW-APP")
    monkeypatch.setattr(os, "execv", lambda *a: None)

    AppImageInstaller(appimage).apply(new_file, lambda: None)

    assert appimage.read_bytes() == b"NEW-APP"
    assert os.stat(appimage).st_mode & 0o111  # executable
    assert not new_file.exists()  # moved, not copied


def test_INV6_key_wiped_after_replace_before_execv(monkeypatch, tmp_path):
    appimage = tmp_path / "app.AppImage"
    appimage.write_bytes(b"OLD-APP")
    new_file = tmp_path / "new.AppImage"
    new_file.write_bytes(b"NEW-APP")
    order: list[str] = []
    monkeypatch.setattr(os, "execv", lambda *a: order.append("execv"))

    AppImageInstaller(appimage).apply(new_file, lambda: order.append("wipe"))

    assert order == ["wipe", "execv"]  # wipe strictly between replace and exec
    assert appimage.read_bytes() == b"NEW-APP"  # the replace happened first


def test_INV6_failed_replace_leaves_key_unwiped_and_original_intact(
    monkeypatch, tmp_path
):
    appimage = tmp_path / "app.AppImage"
    appimage.write_bytes(b"OLD-APP")
    new_file = tmp_path / "new.AppImage"
    new_file.write_bytes(b"NEW-APP")
    order: list[str] = []
    monkeypatch.setattr(os, "execv", lambda *a: order.append("execv"))

    def boom(src, dst):
        raise OSError("ENOSPC: no space left on device")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(UpdateError):
        AppImageInstaller(appimage).apply(new_file, lambda: order.append("wipe"))

    assert order == []  # neither the wipe nor the exec ran (INV-6/INV-11)
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
    def opener(request, timeout=None):
        return _FakeHTTPResponse(payload)

    return opener


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
    assert info.notes_url.endswith("/releases/tag/v0.1.1")


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
        notes_url="https://x",
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
        notes_url="https://x",
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

    dialog = UpdateDialog("0.1.0", "0.1.1", "https://notes", None)
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

    def check_for_update(self):
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
