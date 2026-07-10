"""FIBR-0054 optional in-app auto-update — conformance tests.

See ``spec.md`` in this directory. Pure service/version/asset/installer legs need
no ``qtbot``; the dialog + shell legs use it. No network (injected fake fetcher),
no real signing key (a throwaway test key is monkeypatched in).
"""

from __future__ import annotations

import pytest

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
