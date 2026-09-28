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


def settle(worker: DeriveWorker | None) -> None:
    """Wait out a worker that has already reported, before letting it go.

    ``done`` and ``failed`` are emitted from inside ``run()``, so the thread is
    still alive when the slot handling them runs. Clearing ``self._worker`` there
    lifts the INV-2f guard, and a dialog deleted in that gap destroys a running
    ``QThread``, which Qt answers by aborting the process (FIBR-0374). ``run()``
    has nothing left to do but return, so the wait is momentary.
    """
    if worker is not None:
        worker.wait()
