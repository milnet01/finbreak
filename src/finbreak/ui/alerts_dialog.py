"""AlertsDialog — the spending-alerts list, behind Home's Alerts button (FIBR-0185).

Alerts used to render as an inline card at the top of the Home dashboard, so every
alert that appeared (or was dismissed) shoved the whole dashboard up or down the
page. They now live here: one row per open alert with its per-alert dismiss
control — the same FIBR-0172 alerts, detectors and dismissal store, moved from
``HomeView`` unchanged. Home keeps only the count, so its layout is fixed-height
whatever the alert count.

Opened through the shell's tracked ``_open_dialog`` path (an idle auto-lock tears
open dialogs down, FIBR-0051 INV-4b) — never ``exec()``. Every service call is
``VaultLockedError``-guarded for the same reason the card's were.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from finbreak.errors import VaultLockedError
from finbreak.models import AlertKind, SpendingAlert
from finbreak.services.alerts import AlertService
from finbreak.services.transactions import to_display_decimal
from finbreak.ui._amount import _format_amount


class AlertsDialog(QDialog):
    """The open alerts, one row per alert. ``changed`` fires after a successful
    dismiss, carrying the number of alerts still open, so the shell can update
    Home's Alerts button behind the dialog.

    It carries the COUNT rather than being a bare notification (FIBR-0216): a
    dismiss re-renders these rows, which computes the alert set, and Home's
    ``refresh_alerts`` then computed the very same set again — two full unfiltered
    transaction scans plus two recurring-detection passes per click, for one number
    the dialog was already holding."""

    changed = Signal(int)

    def __init__(
        self,
        alerts: AlertService,
        symbol: str,
        exponent: int,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Alerts"))
        self._alerts = alerts
        self._symbol = symbol
        self._exponent = exponent

        self._rows = QVBoxLayout()
        # Shown in place of the rows once the last alert is dismissed — the dialog
        # stays open (the user dismissed them; closing under them would be abrupt).
        self._empty = QLabel(self.tr("Nothing needs your attention."))
        self._empty.setObjectName("alerts_empty")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(self._rows)
        layout.addWidget(self._empty)
        layout.addStretch()
        layout.addWidget(buttons)

        self._render()

    # --- render ------------------------------------------------------------- #
    def _render(self) -> int:
        """Rebuild the rows in place: a translated summary label + a Dismiss (``✕``)
        button carrying the alert key. Rebuilt rather than refreshed so the dismiss
        path can re-run it without reopening the dialog. Returns the number of open
        alerts, so the dismiss path can pass it on instead of recomputing it."""
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)  # detach now so findChild can't see a stale row
        try:
            alerts = self._alerts.alerts(date.today())
        except VaultLockedError:
            alerts = []  # auto-lock mid-render; the dialog is being torn down
        for alert in alerts:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QLabel(self._summary(alert)))
            row_layout.addStretch()
            # The glyph is DATA, not a translatable string — there is nothing in
            # "✕" for a translator to work with, and a bare glyph left a screen
            # reader announcing N identically-unnamed buttons (WCAG 4.1.2). The
            # accessible name is the translated part, and it names WHICH alert it
            # dismisses (FIBR-0216). Same treatment for the tooltip, so the meaning
            # is available to a sighted user hovering, too.
            dismiss = QPushButton("✕")
            dismiss.setObjectName("alert_dismiss")
            label = self.tr("Dismiss: {alert}").format(alert=self._summary(alert))
            dismiss.setAccessibleName(label)
            dismiss.setToolTip(label)
            dismiss.setProperty("alert_key", alert.key)
            dismiss.clicked.connect(self._on_dismiss)
            row_layout.addWidget(dismiss)
            self._rows.addWidget(row)
        self._empty.setVisible(not alerts)
        return len(alerts)

    def _summary(self, alert: SpendingAlert) -> str:
        """The translated one-line summary for an alert, by kind (FIBR-0172 INV-18).
        Money is scaled from the alert's positive minor magnitude to a display Decimal
        here (the service carries integers, INV-15)."""
        amount = _format_amount(
            to_display_decimal(alert.amount_minor, self._exponent), self._symbol
        )
        if alert.kind is AlertKind.NEW_RECURRING:
            return self.tr("New recurring charge: {name} ({amount})").format(
                name=alert.label, amount=amount
            )
        if alert.kind is AlertKind.CATEGORY_SPIKE:
            baseline = _format_amount(
                to_display_decimal(alert.baseline_minor, self._exponent), self._symbol
            )
            return self.tr(
                "{name} spending is up: {amount} vs usual {baseline}"
            ).format(name=alert.label, amount=amount, baseline=baseline)
        # AlertKind.MISSED_DEBIT — ``on`` is the due date that was missed.
        due = alert.on.isoformat() if alert.on is not None else ""
        return self.tr("Missed payment: {name} ({amount}) due {due}").format(
            name=alert.label, amount=amount, due=due
        )

    def _on_dismiss(self) -> None:
        """Dismiss the clicked alert, rebuild the rows, and tell the shell so Home's
        button re-counts. The write is guarded against a mid-interaction auto-lock,
        like every other mutating slot in the app."""
        button = self.sender()
        key = button.property("alert_key") if button is not None else None
        if key is None:
            return
        try:
            self._alerts.dismiss(key)
        except VaultLockedError:
            return  # auto-lock fired mid-click; the workspace is being torn down
        self.changed.emit(self._render())
