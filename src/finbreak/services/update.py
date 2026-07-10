"""UpdateService — the opt-in AppImage updater's orchestration (FIBR-0054).

Owns the plaintext-INI opt-in / skip prefs (D4), the launch check
(``check_for_update``, INV-1/2/3/8/11), and the signature-verified download
(``download_and_verify``, INV-4/5/10). All network access is delegated to the
injected ``update_fetch`` module (the sole networked file, D9/D12); the install
hand-off is delegated to the injected ``Installer`` (D6). The version grammar
(D13) and asset predicate (D14) are the small, dependency-free helpers below.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from PySide6.QtCore import QSettings

from finbreak import __version__
from finbreak.errors import UpdateError, UpdateVerificationError
from finbreak.services import update_fetch, update_key
from finbreak.services.update_installer import Installer

log = logging.getLogger(__name__)

# The GitHub repo the check reads (D9/D11). /releases/latest excludes prereleases.
_GITHUB_OWNER = "milnet01"
_GITHUB_REPO = "finbreak"

# Resource caps (INV-10) — an AppImage is ~tens of MB; the API JSON is small; a
# raw Ed25519 signature is 64 bytes. A stalled connection times out, not hangs.
_MAX_UPDATE_BYTES = 200 * 1024 * 1024
_MAX_API_BYTES = 1024 * 1024
_MAX_SIG_BYTES = 4096
_TIMEOUT_S = 30

# The plaintext window.ini keys (D4) — non-sensitive, read before unlock.
_KEY_ENABLED = "check_for_updates"
_KEY_SKIPPED = "skipped_update_version"


@dataclass(frozen=True)
class UpdateInfo:
    """A newer, signed, non-skipped release the user may install (INV-3)."""

    version: str
    appimage_url: str
    sig_url: str
    notes_url: str


# --------------------------------------------------------------------------- #
# D13 — version grammar + comparison (fail-safe, dependency-free)
# --------------------------------------------------------------------------- #
def _parse_version(text: str) -> tuple[int, ...] | None:
    """Parse ``N(.N)*`` (optional leading ``v``/``V``) into an int tuple, or
    ``None`` if any segment is not a plain ASCII decimal integer (D13).

    ``segment.isdigit()`` — **not** ``int()`` — is the guard: ``int()`` quietly
    accepts ``"1_0"``, ``" 1"``, ``"+1"`` and unicode digits, all of which must
    make the parse fail so the caller treats the version as unusable (INV-3).
    """
    if text[:1] in ("v", "V"):
        text = text[1:]
    if not text:
        return None
    out: list[int] = []
    for segment in text.split("."):
        if not (segment.isascii() and segment.isdigit()):
            return None
        out.append(int(segment))
    return tuple(out)


def _version_gt(latest: tuple[int, ...], current: tuple[int, ...]) -> bool:
    """True iff *latest* is strictly greater than *current*, zero-padding the
    shorter tuple so ``(0, 1)`` and ``(0, 1, 0)`` compare **equal** (D13)."""
    width = max(len(latest), len(current))
    padded_latest = latest + (0,) * (width - len(latest))
    padded_current = current + (0,) * (width - len(current))
    return padded_latest > padded_current


# --------------------------------------------------------------------------- #
# D14 — asset-selection predicate
# --------------------------------------------------------------------------- #
_APPIMAGE_SUFFIX = "-x86_64.AppImage"


def _select_assets(assets: list[dict]) -> tuple[str, str] | None:
    """From a release's ``assets[]`` return ``(appimage_url, sig_url)`` — the
    lone asset whose name ends ``-x86_64.AppImage`` plus the asset named exactly
    that + ``.sig`` — or ``None`` if either is absent or the AppImage suffix
    matches more than one asset (fail safe, INV-3/D14)."""
    appimages = [a for a in assets if a.get("name", "").endswith(_APPIMAGE_SUFFIX)]
    if len(appimages) != 1:
        return None
    appimage = appimages[0]
    sig_name = appimage["name"] + ".sig"
    sigs = [a for a in assets if a.get("name") == sig_name]
    if len(sigs) != 1:
        return None
    appimage_url = appimage.get("browser_download_url")
    sig_url = sigs[0].get("browser_download_url")
    if not appimage_url or not sig_url:
        return None
    return appimage_url, sig_url


def _version_string(tag: str) -> str:
    """The bare version string of a tag — a single leading ``v``/``V`` stripped
    (the form stored as the skipped version + shown in the prompt)."""
    return tag[1:] if tag[:1] in ("v", "V") else tag


def _stage_temp(directory: Path, suffix: str) -> Path:
    """An empty temp file next to ``$APPIMAGE`` (same filesystem, so the eventual
    ``os.replace`` is atomic — INV-5). Named so a dropped download is greppable."""
    fd, name = tempfile.mkstemp(dir=directory, prefix="finbreak-update-", suffix=suffix)
    os.close(fd)
    return Path(name)


class UpdateService:
    """Orchestrates the opt-in check + the signature-verified download.

    Holds **no** vault/auth reference — the check runs on the plaintext INI +
    the injected fetcher alone, so it works while locked (INV-2). Network I/O is
    the injected *fetcher* (default ``update_fetch``); the install hand-off is the
    injected *installer* (``None`` off an AppImage — the shell then never calls in).
    """

    def __init__(
        self,
        settings_path: Path,
        installer: Installer | None,
        *,
        fetcher=update_fetch,
        current_version: str = __version__,
    ):
        self._settings_path = settings_path
        self._installer = installer
        self._fetcher = fetcher
        self._current_version = current_version

    # --- plaintext-INI prefs (D4) ------------------------------------------- #
    def _settings(self) -> QSettings:
        return QSettings(str(self._settings_path), QSettings.Format.IniFormat)

    def is_enabled(self) -> bool:
        value = self._settings().value(_KEY_ENABLED)
        # Off unless the flag is exactly "true": absent (fresh install) / "false" /
        # any malformed value all read as off (INV-1).
        return isinstance(value, str) and value.lower() == "true"

    def set_enabled(self, enabled: bool) -> None:
        settings = self._settings()
        settings.setValue(_KEY_ENABLED, "true" if enabled else "false")
        settings.sync()

    def is_skipped(self, version: str) -> bool:
        return self._settings().value(_KEY_SKIPPED) == version

    def skip_version(self, version: str) -> None:
        settings = self._settings()
        settings.setValue(_KEY_SKIPPED, version)
        settings.sync()

    # --- the launch check (INV-1/2/3/8/11) ---------------------------------- #
    def check_for_update(self) -> UpdateInfo | None:
        """Return a newer, signed, non-skipped release to offer, or ``None``.

        The opt-in gate is checked first, so a disabled service never calls the
        fetcher (INV-1). Every failure — disabled, malformed version, network
        error, missing asset, not-newer, skipped — yields ``None`` and never
        propagates (INV-3/INV-11)."""
        if not self.is_enabled():
            return None
        try:
            current = _parse_version(self._current_version)
            if current is None:
                return None
            release = self._fetcher.fetch_latest_release(
                _GITHUB_OWNER,
                _GITHUB_REPO,
                timeout=_TIMEOUT_S,
                max_bytes=_MAX_API_BYTES,
            )
            tag = release.get("tag_name") or ""
            latest = _parse_version(tag)
            if latest is None or not _version_gt(latest, current):
                return None
            version = _version_string(tag)
            if self.is_skipped(version):
                return None
            urls = _select_assets(release.get("assets") or [])
            if urls is None:
                return None
            appimage_url, sig_url = urls
            return UpdateInfo(
                version=version,
                appimage_url=appimage_url,
                sig_url=sig_url,
                notes_url=release.get("html_url") or "",
            )
        except Exception as exc:  # DNS/HTTP/JSON/anything — stay silent + safe
            log.debug("update check failed: %r", exc)
            return None

    # --- the signature-verified download (INV-4/5/10) ----------------------- #
    def download_and_verify(self, info: UpdateInfo) -> Path:
        """Download the AppImage + its ``.sig`` into the ``$APPIMAGE`` directory
        and verify the Ed25519 signature over the **exact** downloaded bytes
        against the committed public key. Return the verified temp path (the
        caller installs it); on **any** failure delete the temps and raise —
        ``UpdateVerificationError`` for a bad signature, ``UpdateError`` for an
        oversize / timed-out / dropped download (INV-4/INV-10/INV-11)."""
        if self._installer is None:
            raise UpdateError("self-update is not supported on this platform")
        directory = self._installer.target_path().parent
        appimage_tmp = _stage_temp(directory, ".AppImage")
        sig_tmp = _stage_temp(directory, ".sig")
        try:
            self._fetcher.download(
                info.appimage_url,
                appimage_tmp,
                max_bytes=_MAX_UPDATE_BYTES,
                timeout=_TIMEOUT_S,
            )
            self._fetcher.download(
                info.sig_url, sig_tmp, max_bytes=_MAX_SIG_BYTES, timeout=_TIMEOUT_S
            )
            data = appimage_tmp.read_bytes()
            signature = sig_tmp.read_bytes()
            try:
                update_key.public_key().verify(signature, data)
            except InvalidSignature as exc:
                raise UpdateVerificationError(
                    "the update's signature did not verify"
                ) from exc
        except UpdateVerificationError:
            appimage_tmp.unlink(missing_ok=True)
            sig_tmp.unlink(missing_ok=True)
            raise
        except Exception as exc:  # oversize / timeout / dropped / disk
            appimage_tmp.unlink(missing_ok=True)
            sig_tmp.unlink(missing_ok=True)
            raise UpdateError(f"could not download the update: {exc}") from exc
        sig_tmp.unlink(missing_ok=True)  # only the verified AppImage is installed
        return appimage_tmp
