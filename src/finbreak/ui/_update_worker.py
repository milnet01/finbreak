"""Off-GUI-thread update check + download (FIBR-0054 D7).

Two ``QThread`` workers, mirroring ``DeriveWorker``: the launch **check** and the
**download** both run off the GUI thread so a slow network never freezes the
shell. Each is parented + ``finished``→``deleteLater`` at its call site, and emits
plain ``object``-carrying signals the shell reacts to. ``UpdateService`` already
swallows every network error in the check (INV-11), so ``failed`` there is only for
an unexpected bug; the download surfaces its ``UpdateError`` /
``UpdateVerificationError`` via ``failed`` for the shell to show (INV-11).
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from finbreak.services.update import UpdateInfo, UpdateService


class UpdateCheckWorker(QThread):
    found = Signal(object)  # an UpdateInfo
    none = Signal()
    failed = Signal(object)  # an exception (unexpected — the check is fail-safe)

    def __init__(self, service: UpdateService, parent=None, *, force: bool = False):
        super().__init__(parent)
        self._service = service
        self._force = force  # a manual Help→Check check bypasses the opt-in gate

    def run(self) -> None:
        try:
            info = self._service.check_for_update(force=self._force)
        except Exception as exc:  # check_for_update is fail-safe; this is defensive
            self.failed.emit(exc)
            return
        if info is None:
            self.none.emit()
        else:
            self.found.emit(info)


class DownloadWorker(QThread):
    ready = Signal(object)  # the verified Path
    failed = Signal(object)  # an UpdateError / UpdateVerificationError

    def __init__(self, service: UpdateService, info: UpdateInfo, parent=None):
        super().__init__(parent)
        self._service = service
        self._info = info

    def run(self) -> None:
        try:
            path = self._service.download_and_verify(self._info)
        except Exception as exc:  # signature mismatch / oversize / timeout / disk
            self.failed.emit(exc)
            return
        self.ready.emit(path)
