"""The updater's sole networked module (FIBR-0054 D9/D12 — INV-10/INV-12).

This is the **one** file under ``src/finbreak/`` permitted to import ``urllib``;
``test_INV8_no_network_imports_under_src`` allowlists exactly this relative path.
It exposes only two functions — read the GitHub Releases API, and stream one asset
to disk — both over the default-TLS ``https://`` endpoint, both bounded by a byte
cap and a socket timeout (INV-10) so a hostile or broken server cannot exhaust
disk or hang the launch check. All higher-level policy (opt-in gate, version
compare, signature verify) lives in ``update.py``; this module just moves bytes.
"""

from __future__ import annotations

import functools
import json
import ssl
import urllib.request
from pathlib import Path

import certifi

_API_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
_USER_AGENT = "finbreak-updater"
_ACCEPT_GITHUB_JSON = "application/vnd.github+json"
_DOWNLOAD_CHUNK_BYTES = 64 * 1024


@functools.lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    """A TLS context that verifies against the **bundled** certifi CA set rather
    than the host's system store.

    The frozen AppImage runs on any Linux distro, whose CA bundle may sit at a
    path the frozen OpenSSL was not built for — the v0.1.0 no-update-prompt bug:
    built on Debian (certs at ``/usr/lib/ssl/…``), run on openSUSE (certs at
    ``/var/lib/ca-certificates/…``), so the default context found no CAs, the
    HTTPS check raised ``SSLCertVerificationError``, and INV-11 swallowed it
    silently. Shipping our own CA set (certifi) makes verification independent of
    the host's cert layout, so the check works on every distro.
    """
    return ssl.create_default_context(cafile=certifi.where())


def _require_https(url: str) -> None:
    """Refuse any non-``https://`` URL (INV-10). A defence in depth: even if the
    API response were tampered to point an asset at ``http://`` or ``file://``,
    we never open it — and it closes bandit's B310 permitted-scheme concern."""
    if not url.startswith("https://"):
        raise ValueError(f"refusing a non-https update URL: {url!r}")


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-assert the https-only invariant (INV-10) on EVERY redirect hop.

    ``_require_https`` only guards the *first* URL we open; urllib's default
    redirect handler would otherwise transparently follow a 3xx to ``http://``
    (or ``ftp://``), silently downgrading the fetch to plaintext. We reject any
    non-https redirect target. Integrity is still guaranteed by the Ed25519 check
    on the asset; this closes the confidentiality gap for the *unsigned* API JSON.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_https(newurl)  # raises before the redirect is followed
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@functools.lru_cache(maxsize=1)
def _install_opener() -> None:
    """Install a process-wide opener that verifies TLS against the bundled
    certifi CA set AND enforces https on redirects (``_HttpsOnlyRedirectHandler``).

    Installed globally rather than passed per call because
    ``urllib.request.urlopen(..., context=...)`` builds a throwaway opener with
    the DEFAULT redirect handler — there is no per-call hook to inject our
    https-only guard. ``update_fetch`` is the app's sole network surface (INV-12),
    so a process-wide opener is contained. Callers then use plain
    ``urlopen(request, timeout=...)`` (no ``context=``) so this opener is used.
    Idempotent via ``lru_cache``.
    """
    urllib.request.install_opener(
        urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_ssl_context()),
            _HttpsOnlyRedirectHandler(),
        )
    )


def fetch_latest_release(
    owner: str, repo: str, *, timeout: float, max_bytes: int
) -> dict:
    """GET ``/repos/{owner}/{repo}/releases/latest`` and return the parsed JSON.

    The body is read under *max_bytes* (a response exceeding it raises
    ``ValueError`` rather than being parsed) with a *timeout*-second socket
    deadline. ``/releases/latest`` excludes prereleases (D11)."""
    url = _API_URL_TEMPLATE.format(owner=owner, repo=repo)
    _require_https(url)
    _install_opener()  # https-only redirects + bundled-certifi TLS (INV-10)
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": _ACCEPT_GITHUB_JSON}
    )
    with urllib.request.urlopen(  # nosec B310  # nosemgrep: dynamic-urllib-use-detected
        request, timeout=timeout
    ) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("release API response exceeds the size cap")
    return json.loads(raw.decode("utf-8"))


def download(url: str, dest: Path, *, max_bytes: int, timeout: float) -> None:
    """Stream *url* to *dest*, aborting (temp deleted, ``ValueError``) once the
    running total exceeds *max_bytes* (INV-10). Any failure deletes the partial
    temp so a broken download never orphans bytes on the ``$APPIMAGE`` fs."""
    _require_https(url)
    _install_opener()  # https-only redirects + bundled-certifi TLS (INV-10)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    total = 0
    try:
        with (
            urllib.request.urlopen(  # nosec B310  # nosemgrep: dynamic-urllib-use-detected
                request, timeout=timeout
            ) as response,
            open(dest, "wb") as handle,
        ):
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("download exceeds the size cap")
                handle.write(chunk)
    except BaseException:
        Path(dest).unlink(missing_ok=True)
        raise
