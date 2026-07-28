"""UpdateDialog — the "a newer version is available" prompt (FIBR-0054 D15).

A non-blocking dialog (opened by the shell's tracked ``_open_dialog`` path, never
``exec()`` — INV-9) offering **Later** / **Skip this version** / **Update now**,
with the release notes ("What's new") shown **inline** in a compact read-only
panel (no browser round-trip). On **Update now** it disables the buttons and
**stays open** in a "Downloading…" busy state — indeterminate until the fetcher
reports a size, then a real percentage (``set_progress``, FIBR-0108) — it does not
``accept()``/``reject()`` until the install relaunches the app or the shell
surfaces an error and tears it down. Its three custom signals + stay-open
lifecycle are why it can't use the vanilla ``show_modal`` single-accept contract
(D15). All fixed strings are ``tr()`` literals; version numbers ride in via
``str.format`` on a literal template so lupdate still extracts it (INV-13). The
release notes are release data, shown verbatim — never ``tr()``-wrapped.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class UpdateDialog(QDialog):
    later = Signal()
    skip = Signal()
    update_now = Signal()

    def __init__(
        self,
        current: str,
        available: str,
        notes: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Update available"))

        heading = QLabel(self.tr("A new version of finbreak is available."))
        heading.setObjectName("update_heading")
        # A literal template (extractable by lupdate) filled with the version
        # data at runtime — NOT self.tr(variable), which lupdate cannot see.
        versions = QLabel(
            self.tr(
                "You have version {current}. Version {available} is available."
            ).format(current=current, available=available)
        )
        versions.setObjectName("update_versions")

        # "What's new" — the release notes shown inline in a compact, read-only,
        # scrollable panel (markdown rendered). Hidden entirely when a release
        # ships no notes. Link-opening is OFF so a note that contains a URL can
        # never trigger a navigation/egress on click (offline posture, INV-12).
        self._notes_label = QLabel(self.tr("What's new"))
        self._notes_label.setObjectName("update_notes_label")
        self._notes = QTextBrowser()
        self._notes.setObjectName("update_notes")
        self._notes.setOpenExternalLinks(False)
        self._notes.setOpenLinks(False)
        self._notes.setMaximumHeight(120)  # compact; scrolls if notes are long
        body = notes.strip()
        if body:
            self._notes.setMarkdown(body)
        else:
            self._notes_label.setVisible(False)
            self._notes.setVisible(False)

        # Busy indicator — hidden until Update now. Starts indeterminate and
        # switches to a real percentage on the first sized progress report
        # (FIBR-0108); an unsized download keeps the striped look.
        self._busy = QProgressBar()
        self._busy.setObjectName("update_busy")
        self._busy.setRange(0, 0)  # indeterminate until a size is known
        self._busy.setVisible(False)
        self._busy_label = QLabel(self.tr("Downloading…"))
        self._busy_label.setObjectName("update_busy_label")
        self._busy_label.setVisible(False)

        self._later_button = QPushButton(self.tr("Later"))
        self._later_button.setObjectName("update_later")
        self._later_button.clicked.connect(self._on_later)
        self._skip_button = QPushButton(self.tr("Skip this version"))
        self._skip_button.setObjectName("update_skip")
        self._skip_button.clicked.connect(self._on_skip)
        self._update_button = QPushButton(self.tr("Update now"))
        self._update_button.setObjectName("update_now")
        self._update_button.setDefault(True)
        self._update_button.clicked.connect(self._on_update_now)

        buttons = QDialogButtonBox()
        buttons.addButton(self._later_button, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton(self._skip_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self._update_button, QDialogButtonBox.ButtonRole.AcceptRole)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(versions)
        layout.addWidget(self._notes_label)
        layout.addWidget(self._notes)
        layout.addWidget(self._busy_label)
        layout.addWidget(self._busy)
        layout.addWidget(buttons)

    def _on_later(self) -> None:
        self.later.emit()

    def _on_skip(self) -> None:
        self.skip.emit()

    def _on_update_now(self) -> None:
        # Enter the busy state and STAY OPEN — the shell drives the download; the
        # dialog closes only when the install relaunches or an error tears it down.
        self._enter_busy()
        self.update_now.emit()

    def set_progress(self, received: int, total: int) -> None:
        """Advance the download bar. A *total* of 0 means the server never said
        how big the asset is, so the bar stays indeterminate rather than showing a
        percentage of a guess (FIBR-0108)."""
        if total <= 0:
            return
        if self._busy.maximum() != total:
            self._busy.setRange(0, total)
        self._busy.setValue(received)

    def _enter_busy(self) -> None:
        for button in (self._later_button, self._skip_button, self._update_button):
            button.setEnabled(False)
        self._busy_label.setVisible(True)
        self._busy.setVisible(True)
