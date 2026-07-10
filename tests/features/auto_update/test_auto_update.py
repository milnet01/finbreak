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
from finbreak.services.update_installer import (
    AppImageInstaller,
    detect_installer,
    is_update_supported,
)
from finbreak.services.update import (
    _parse_version,
    _select_assets,
    _version_gt,
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

    def __exit__(self, *exc) -> bool:
        return False


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
