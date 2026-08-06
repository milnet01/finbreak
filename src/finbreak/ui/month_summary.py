"""MonthSummaryStrip — the plain-English month summary at the top of Home
(FIBR-0231 § 4.6).

This module owns **every template** in the feature. ``MonthSummaryService``
returns facts — an enum verdict and integer minor units — and the phrasing lives
here, in a ``QObject`` that can translate (§ 4.7). That is the FIBR-0138
``DrillLabels`` pattern reversed: injecting translated *labels* into a service
works for drill nodes, which carry a ``label`` field, but a sentence has
grammar — clause order, sign-selected templates — which cannot be expressed as
injected nouns.

**The rendered slots are ONE label, joined by a single space**, following
``ui/forecast.py``'s clause assembly — not three labels in a layout. One label
is what makes the block wrap as prose rather than breaking at slot boundaries.

The strip is the first thing on the dashboard, because a reader who stops after
one line must have read the most useful line.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from finbreak.models import MonthCause, MonthSummary, MonthVerdict
from finbreak.services.transactions import to_display_decimal
from finbreak.ui._amount import _format_amount

# A merchant name is derived from raw bank text and can be arbitrarily long, so
# it is shortened before interpolation: the first _NAME_MAX - 1 characters plus
# an ellipsis. Plain CHARACTER truncation, deliberately not
# QFontMetrics.elidedText, which measures pixels and would make the rendered
# sentence depend on the widget's width.
_NAME_MAX = 40
_ELLIPSIS = "…"


class MonthSummaryStrip(QWidget):
    """One word-wrapping label that states what happened to the user's money.

    ``set_summary(None, symbol)`` and ``clear()`` both hide it entirely — silence
    is a valid and frequently correct output, and the strip is **absent, not
    vague**, when the vault cannot support a comparison.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("month_summary_strip")

        self._label = QLabel("")
        self._label.setObjectName("month_summary_text")
        self._label.setWordWrap(True)
        # PlainText, never the default AutoText: a merchant name is derived from
        # the user's own bank description, and one containing <b> or
        # <img src=…> would otherwise be rendered as rich text — showing
        # something other than the user's transaction, and attempting a local
        # resource load.
        self._label.setTextFormat(Qt.TextFormat.PlainText)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.setVisible(False)

    # --- public API -------------------------------------------------------- #
    def clear(self) -> None:
        """Hide the strip. Needs no ``symbol``, which is why it exists separately
        from ``set_summary(None, …)``: ``HomeView``'s ``except VaultLockedError``
        blocks must hide the strip and have none in scope — ``base_currency()``
        is itself a vault read that would raise the same exception."""
        self._label.setText("")
        self.setVisible(False)

    def set_summary(self, summary: MonthSummary | None, symbol: str) -> None:
        """Render up to three sentences from one ``MonthSummary``, or hide.

        Each slot's render condition is a field being present, never a threshold:
        the detector nulls ``residual_minor`` when no correction is warranted, so
        this method evaluates no threshold of its own (§ 4.6)."""
        if summary is None:
            self.clear()
            return

        slots = [self._verdict_text(summary, symbol)]
        if summary.cause is not None:
            slots.append(self._cause_text(summary, summary.cause, symbol))
        if summary.residual_minor is not None:
            slots.append(self._correction_text(summary, summary.residual_minor, symbol))
        self._label.setText(" ".join(slots))
        self.setVisible(True)

    # --- text builders ----------------------------------------------------- #
    def _amount(self, value_minor: int, exponent: int, symbol: str) -> str:
        """Always a MAGNITUDE: the sign is carried by the chosen template and
        never by the figure. Without the ``abs`` the LOWER and "better than
        normal" rows render "cost you -R500 less than your usual month"."""
        return _format_amount(to_display_decimal(abs(value_minor), exponent), symbol)

    def _month_text(self, summary: MonthSummary) -> str:
        """The month, composed with its year through a template rather than by
        concatenation — month/year order is precisely what some locales reorder,
        and ``coding.md`` forbids building display strings with ``+``. Which form
        applies is decided by ``show_year``, computed by the service, which
        already has the clock; the strip needs none."""
        year, month = summary.month.split("-")
        name = QLocale().standaloneMonthName(int(month))
        if summary.show_year:
            return self.tr("{month_name} {year}").format(month_name=name, year=year)
        return self.tr("{month_name}").format(month_name=name)

    def _verdict_text(self, summary: MonthSummary, symbol: str) -> str:
        """Slot 1 — always present when the strip renders at all. "Unremarkable"
        is one of the three verdicts, so an ordinary month collapses to one short
        sentence rather than to a separate "brief mode"."""
        month = self._month_text(summary)
        amount = self._amount(summary.movement_minor, summary.exponent, symbol)
        if summary.verdict is MonthVerdict.HIGHER:
            if summary.partial:
                template = self.tr(
                    "So far, {month} has cost you {amount} more than usual "
                    "by this point."
                )
            else:
                template = self.tr(
                    "{month} cost you {amount} more than your usual month."
                )
        elif summary.verdict is MonthVerdict.LOWER:
            if summary.partial:
                template = self.tr(
                    "So far, {month} has cost you {amount} less than usual "
                    "by this point."
                )
            else:
                template = self.tr(
                    "{month} cost you {amount} less than your usual month."
                )
        else:
            if summary.partial:
                return self.tr("So far, {month} looks like a normal month.").format(
                    month=month
                )
            return self.tr("{month} looked like a normal month.").format(month=month)
        return template.format(month=month, amount=amount)

    def _cause_text(self, summary: MonthSummary, cause: MonthCause, symbol: str) -> str:
        """Slot 2 — the merchant family whose excess explains the movement.

        It splits THREE ways, not two. The equality case is not a corner: it is
        where § 2.2's flagship vault lands, and folding it into the ``>`` branch
        would claim "and more" about a quantity that is exactly equal.

        Slots 2 and 3 mark themselves provisional by **tense**, not by a second
        "So far," — all three slots render into one joined sentence, and three of
        them in a row is not prose anyone wants to read."""
        name = cause.name
        if len(name) > _NAME_MAX:
            name = name[: _NAME_MAX - 1] + _ELLIPSIS
        amount = self._amount(cause.excess_minor, summary.exponent, symbol)
        if cause.excess_minor < summary.movement_minor:
            template = (
                self.tr(
                    "Most of it has been one thing — {name}, {amount} more than usual."
                )
                if summary.partial
                else self.tr(
                    "Most of it was one thing — {name}, {amount} more than usual."
                )
            )
        elif cause.excess_minor == summary.movement_minor:
            template = (
                self.tr(
                    "All of it has been one thing — {name}, {amount} more than usual."
                )
                if summary.partial
                else self.tr(
                    "All of it was one thing — {name}, {amount} more than usual."
                )
            )
        else:
            template = (
                self.tr(
                    "All of it and more has been one thing — {name}, {amount} "
                    "more than usual."
                )
                if summary.partial
                else self.tr(
                    "All of it and more was one thing — {name}, {amount} "
                    "more than usual."
                )
            )
        return template.format(name=name, amount=amount)

    def _correction_text(
        self, summary: MonthSummary, residual_minor: int, symbol: str
    ) -> str:
        """Slot 3 — selected by the sign of the **residual**, never by the sign of
        the movement. The roadmap bullet's own illustration got this wrong in the
        one direction this feature must not: it stated a reassuring conclusion
        (R440 better than normal) that its own arithmetic did not support."""
        amount = self._amount(residual_minor, summary.exponent, symbol)
        if residual_minor < 0:
            template = (
                self.tr("Take that out and you are {amount} better than normal so far.")
                if summary.partial
                else self.tr("Take that out and you were {amount} better than normal.")
            )
        else:
            template = (
                self.tr("Even without it you are {amount} above normal so far.")
                if summary.partial
                else self.tr("Even without it you were {amount} above normal.")
            )
        return template.format(amount=amount)
