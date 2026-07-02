"""AuthService — master password ↔ vault key, and the key's whole lifetime.

The derived key lives in a zeroable ``bytearray`` held only while unlocked and
wiped in place on lock, the auto-lock timeout, and application exit (FIBR-0004
INV-3).
The expensive Argon2id derivation is a pure function (``derive_raw``) so the UI
can run it on a worker thread and hand the raw 32 bytes back for the main thread
to own — every wipe then runs on the one owning thread, no cross-thread race.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
from sqlcipher3.dbapi2 import DatabaseError

from finbreak.crypto import (
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    KEY_LEN,
    SALT_LEN,
    derive_key,
    load_and_validate_params,
)
from finbreak.errors import VaultStateError
from finbreak.models import FORMAT_VERSION, KdfParams
from finbreak.vault import Vault

log = logging.getLogger(__name__)

# The offered first-run base currencies, each 2-decimal (D1). ZAR leads so it is
# the default. Extended (incl. 0-/3-decimal currencies) in a later phase.
CURRENCY_EXPONENTS = {"ZAR": 2, "USD": 2, "EUR": 2, "GBP": 2, "AUD": 2, "CAD": 2}

# Fixed lock-out timeout measured from unlock — NOT reset on user activity.
# True idle-detection (activity-reset) + user configurability land with
# FIBR-0014's Settings screen.
AUTO_LOCK_MINUTES = 10


def _wipe(buffer: bytearray | None) -> None:
    """Overwrite a secret buffer in place (best-effort; str/bytes can't be wiped)."""
    if buffer:
        buffer[:] = bytes(len(buffer))


def derive_raw(password: bytearray, params: KdfParams) -> bytes:
    """Derive the raw key, wiping both the password and the intermediate buffer.

    Returns immutable ``bytes`` (the transient key crossing back from a worker
    thread); the caller copies it into its own zeroable buffer, per the thread
    model above.
    """
    try:
        derived = derive_key(password, params.salt, params)
        try:
            return bytes(derived)
        finally:
            _wipe(derived)
    finally:
        _wipe(password)


class AuthService:
    def __init__(self, vault_path: Path, sidecar_path: Path):
        self._vault = Vault(vault_path, sidecar_path)
        self._sidecar_path = sidecar_path
        self._key: bytearray | None = None
        self._timer: QTimer | None = None
        # Invoked after an idle auto-lock so the UI can route away from the now
        # -locked vault (else the next action hits a closed connection). Set by
        # the UI shell; None in headless use.
        self.on_auto_lock: Callable[[], None] | None = None

    @property
    def vault(self) -> Vault:
        return self._vault

    def state(self) -> str:
        return self._vault.presence_state()

    # --- first run --------------------------------------------------------- #
    def validate_first_run(
        self, password: bytearray, confirm: bytearray, base_currency: str
    ) -> None:
        """Form-boundary validation; wipes both password buffers before returning."""
        try:
            if base_currency not in CURRENCY_EXPONENTS:
                raise ValueError(f"unsupported base currency: {base_currency!r}")
            if len(password) == 0:
                raise ValueError("password must not be empty")
            if password != confirm:
                raise ValueError("passwords do not match")
        finally:
            _wipe(password)
            _wipe(confirm)

    def new_params(self) -> KdfParams:
        return KdfParams(
            format_version=FORMAT_VERSION,
            memory_kib=ARGON2_MEMORY_KIB,
            time_cost=ARGON2_TIME_COST,
            parallelism=ARGON2_PARALLELISM,
            key_len=KEY_LEN,
            salt_len=SALT_LEN,
            salt=secrets.token_bytes(SALT_LEN),
        )

    def first_run(self, password: bytearray, base_currency: str) -> None:
        """Headless convenience: derive then create, in one call (assumes validated)."""
        params = self.new_params()
        raw = derive_raw(password, params)
        self.complete_first_run(raw, params, base_currency)

    def complete_first_run(
        self, raw: bytes, params: KdfParams, base_currency: str
    ) -> None:
        """Main-thread step: create the vault and take ownership of the key."""
        if self._vault.presence_state() != "first_run":
            raise VaultStateError("cannot first-run over an existing vault")
        key = bytearray(raw)
        try:
            self._vault.create(
                key, params, base_currency, CURRENCY_EXPONENTS[base_currency]
            )
        except Exception:
            _wipe(key)  # don't leave the key in memory if creation failed
            raise
        self._key = key
        self._arm_timer()
        log.info("first-run: vault created")

    # --- unlock ------------------------------------------------------------ #
    def load_params(self) -> KdfParams:
        return load_and_validate_params(self._sidecar_path)

    def unlock(self, password: bytearray) -> bool:
        """Headless convenience: validate sidecar → derive → open, in one call."""
        try:
            params = self.load_params()
        except Exception:
            _wipe(password)
            raise
        raw = derive_raw(password, params)
        return self.complete_unlock(raw)

    def complete_unlock(self, raw: bytes) -> bool:
        """Main-thread step: open the vault; ``False`` (no key) on a wrong key."""
        key = bytearray(raw)
        try:
            self._vault.open(key)
        except DatabaseError:
            _wipe(key)
            log.info("unlock failed")
            return False
        except Exception:
            # Any other open failure (e.g. a newer-than-supported vault raising
            # SchemaVersionError from the migration runner) must still wipe the
            # derived key before propagating — never leave it in memory (INV-3).
            _wipe(key)
            raise
        self._key = key
        self._arm_timer()
        log.info("unlocked")
        return True

    # --- lock / idle / exit ------------------------------------------------ #
    def lock(self) -> None:
        self._stop_timer()
        self._vault.close()
        _wipe(self._key)
        self._key = None
        log.info("locked")

    def _on_idle_timeout(self) -> None:
        if self._key is None:
            return  # already locked — a stale queued fire must not disturb the UI
        self.lock()
        if self.on_auto_lock is not None:
            self.on_auto_lock()

    def on_about_to_quit(self) -> None:
        """Wipe on shutdown; a no-op when already locked (no key held)."""
        self._stop_timer()
        self._vault.close()
        _wipe(self._key)
        self._key = None

    def _arm_timer(self) -> None:
        # Only meaningful with a running event loop; headless tests invoke the
        # timeout handler directly instead of waiting on the clock.
        if QCoreApplication.instance() is None:
            return
        if self._timer is None:
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._on_idle_timeout)
        self._timer.start(AUTO_LOCK_MINUTES * 60 * 1000)

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
