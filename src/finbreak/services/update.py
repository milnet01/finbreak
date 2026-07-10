"""UpdateService — the opt-in AppImage updater's orchestration (FIBR-0054).

Owns the plaintext-INI opt-in / skip prefs (D4), the launch check
(``check_for_update``, INV-1/2/3/8/11), and the signature-verified download
(``download_and_verify``, INV-4/5/10). All network access is delegated to the
injected ``update_fetch`` module (the sole networked file, D9/D12); the install
hand-off is delegated to the injected ``Installer`` (D6). The version grammar
(D13) and asset predicate (D14) are the small, dependency-free helpers below.
"""

from __future__ import annotations


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
