"""Off-GUI-thread work (design.md "Concurrency").

``DeriveWorker`` runs Argon2id derivation: it only *computes* the raw key from
the password + KDF params and hands the 32 bytes back via a signal; the main
thread copies them into its own zeroable buffer (FIBR-0004 thread model), so
the UI never freezes on the derivation and every wipe stays on the owning
thread.

``start_job`` runs any other slow call that needs no vault access, such as
reading a PDF statement (FIBR-0104), and ``_DETACHED_WORKERS`` is what keeps
such a thread alive until it ends.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import shiboken6
from PySide6.QtCore import QObject, QThread, Signal

from finbreak.models import KdfParams
from finbreak.services.auth import derive_raw

# Threads that run without a parent: update workers detached at shutdown because
# they outlasted the drain, and every `start_job` thread. The list is the PYTHON
# reference that keeps them alive: an unparented QThread is owned by Python, so
# without it a running one is garbage-collectable -- and destroying a running
# QThread aborts the process (FIBR-0327). Entries are pruned as new ones arrive,
# so the list holds only threads still running.
_DETACHED_WORKERS: list[QThread] = []


def _prune_detached() -> None:
    _DETACHED_WORKERS[:] = [
        w for w in _DETACHED_WORKERS if shiboken6.isValid(w) and w.isRunning()
    ]


def detach(worker: QThread) -> None:
    """Keep *worker* alive until it ends, with no parent to destroy it."""
    _prune_detached()
    _DETACHED_WORKERS.append(worker)


def settle_detached_workers(timeout_ms: int) -> bool:
    """Give the detached workers up to *timeout_ms*, shared, to finish; True
    when none is still running. The process must not reach interpreter
    teardown with one running (see ``app._finish``)."""
    deadline = time.monotonic() + timeout_ms / 1000
    for worker in _DETACHED_WORKERS:
        if shiboken6.isValid(worker) and worker.isRunning():
            left_ms = max(0, int((deadline - time.monotonic()) * 1000))
            worker.wait(left_ms)
    return not any(shiboken6.isValid(w) and w.isRunning() for w in _DETACHED_WORKERS)


class DeriveWorker(QThread):
    done = Signal(bytes)
    failed = Signal(object)

    def __init__(
        self, password: bytearray, params: KdfParams, parent: QObject | None = None
    ) -> None:
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


class JobWorker(QThread):
    """Run one callable and report its result (``done``) or exception
    (``failed``). Built by ``start_job``, never directly."""

    done = Signal(object)
    failed = Signal(object)

    def __init__(self, job: Callable[[], object]) -> None:
        super().__init__()  # no parent: see start_job
        self._job = job
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        job = self._job
        del self._job  # hold no input once it has run
        try:
            self.done.emit(job())
        except Exception as exc:  # the receiver decides what is expected
            self.failed.emit(exc)


def start_job(
    job: Callable[[], object],
    on_done: Callable[[object], None],
    on_failed: Callable[[object], None],
) -> JobWorker:
    """Run *job* on its own thread; its result reaches *on_done* or its
    exception *on_failed*, on the UI thread.

    The thread has no parent, so the widget that started it can be destroyed
    mid-run -- an idle auto-lock does exactly that -- without destroying a
    running QThread. It sits in ``_DETACHED_WORKERS`` until it ends, and
    ``app._finish`` gives it a short grace at exit. A result can already be
    queued when the receiver stops wanting it, so a receiver that may have to
    drop one checks ``sender()`` rather than blocking the worker's signals.

    *job* must not touch the vault: its connection belongs to the UI thread.
    *on_done* and *on_failed* must be methods of a QObject on the UI thread:
    that is what makes PySide queue the call there. A lambda or plain function
    would run on the worker thread.
    """
    worker = JobWorker(job)
    worker.done.connect(on_done)
    worker.failed.connect(on_failed)
    detach(worker)
    worker.start()
    return worker
