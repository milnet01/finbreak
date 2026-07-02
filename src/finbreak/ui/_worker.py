"""Off-GUI-thread Argon2id derivation (design.md "Concurrency").

The worker only *computes* the raw key from the password + KDF params and hands
the 32 bytes back via a signal; the main thread copies them into its own
zeroable buffer (FIBR-0004 thread model), so the UI never freezes on the ~tens
of ms derivation and every wipe stays on the owning thread.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from finbreak.models import KdfParams
from finbreak.services.auth import derive_raw


class DeriveWorker(QThread):
    done = Signal(bytes)
    failed = Signal(object)

    def __init__(self, password: bytearray, params: KdfParams, parent=None):
        super().__init__(parent)
        self._password = password
        self._params = params

    def run(self) -> None:
        try:
            self.done.emit(derive_raw(self._password, self._params))
        except Exception as exc:  # derivation failure is unexpected — surface it
            self.failed.emit(exc)
