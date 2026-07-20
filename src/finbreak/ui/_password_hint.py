"""``QSettings`` adapter for the optional password hint (FIBR-0029 § 3.1).

Persists the user-authored hint in the plaintext ``window.ini`` — the same
pre-unlock store ``ui/_unlock_throttle.py`` uses — under ``hint/text``. It lives
in plaintext (not the vault) because it must be readable **before** the vault is
decrypted (that is exactly when the password is forgotten); ``services/
password_hint.validate_hint`` is what keeps it from being/containing the password.

The I/O is split into this ui adapter (Qt ``QSettings``) so ``AuthService``
(services layer) never imports Qt-ui, mirroring the throttle adapter: the unlock
dialog reads the hint pre-unlock and Settings writes it, so QSettings I/O belongs
in ui. ``.sync()`` after every write so a same-process read-back sees it (matching
``ui/_unlock_throttle.py``). ``read_hint`` needs no key and returns ``""`` when
unset.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from finbreak import paths

_HINT_KEY = "hint/text"


def _settings() -> QSettings:
    return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)


def read_hint() -> str:
    """The stored hint, or ``""`` when unset (callable pre-unlock, no key)."""
    value = _settings().value(_HINT_KEY)
    return value if isinstance(value, str) else ""


def write_hint(text: str) -> None:
    settings = _settings()
    settings.setValue(_HINT_KEY, text)
    settings.sync()


def clear_hint() -> None:
    settings = _settings()
    settings.remove(_HINT_KEY)
    settings.sync()
