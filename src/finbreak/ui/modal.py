"""Non-blocking modal helper (FIBR-0065 D1).

``show_modal`` replaces ``dialog.exec()`` at the content-widget call sites so an
idle auto-lock that destroys the parent widget mid-flow can never crash a
post-``exec()`` read of a deleted C++ object (the H-B crash class). The dialog is
shown application-modal but **without** a nested event loop; the caller reacts in
an ``on_accept`` slot instead of reading a return value.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QDialog


def show_modal(dialog: QDialog, on_accept: Callable[[], None]) -> None:
    """Show *dialog* modal + non-blocking; run *on_accept* when the user confirms;
    free the dialog on close.

    The caller MUST construct *dialog* with a parent widget: the parent keeps it
    alive between ``show()`` and the user's click (a parented ``QObject`` is not
    Python-GC'd while its C++ parent lives), and destroys it on lock — so a lock
    while the dialog is open tears it down before ``on_accept`` can fire (INV-2),
    and no deleted object is ever read.

    ``finished`` fires on both accept and reject (Qt emits it from ``done()``
    before ``accepted``/``rejected``); because ``deleteLater`` is deferred, the
    synchronous ``on_accept`` slot still sees a live dialog.
    """
    dialog.setModal(True)
    dialog.accepted.connect(on_accept)
    dialog.finished.connect(dialog.deleteLater)
    dialog.show()
