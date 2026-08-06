"""FIBR-0231 — the strip inside ``HomeView``.

Two things live here and nowhere else: the **period-mode wiring** (the strip
follows the selector across all five modes) and **INV-13 legs (a) and (b)**,
which drive `HomeView`'s own slots — one ``except VaultLockedError``-guarded
(``_on_period_changed``) and one **unguarded** (``set_amount_prefs``,
`home.py`'s public re-render entry point). Both are `HomeView` slots needing
``qtbot``, so neither can live in the service or strip file; and both are
`HomeView`'s own, so this file needs no ``MainWindow``.

`HomeView.refresh()` reads the real clock, so every fixture here is seeded
**relative to ``date.today()``** rather than to a pinned date.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QLabel

from conftest import _PW
from finbreak.errors import VaultLockedError
from finbreak.models import NegativeStyle
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.alerts import AlertService
from finbreak.services.auth import AmountPrefs, AuthService
from finbreak.services.month_summary import MonthSummaryService
from finbreak.services.recurring import RecurringService
from finbreak.services.reporting import (
    MODE_CURRENT_MONTH,
    MODE_PREVIOUS_MONTH,
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    MODE_YEAR_TO_DATE,
    ReportingService,
    ReportPrefs,
    _prev_month,
)
from finbreak.ui.home import HomeView
from finbreak.ui.month_summary import MonthSummaryStrip

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _months_back(count: int) -> list[tuple[int, int]]:
    """``count`` calendar months ending at THIS month, oldest first."""
    year, month = date.today().year, date.today().month
    months: list[tuple[int, int]] = []
    for _ in range(count):
        months.append((year, month))
        year, month = _prev_month(year, month)
    months.reverse()
    return months


def _seed(svc: AuthService) -> None:
    """R5,000 of unchanging spend on the 3rd of each of the last five months — so
    the previous month has three complete baseline months behind it, and the
    current month's truncated head (which starts at day 1) contains its row."""
    account_id = AccountService(svc.vault).list_accounts()[0].id
    repo = TransactionRepository(svc.vault.connection)
    for year, month in _months_back(5):
        repo.add(account_id, f"{year:04d}-{month:02d}-03", -500_000, "Grocer")


def _home(svc: AuthService) -> HomeView:
    return HomeView(
        ReportingService(svc.vault),
        AccountService(svc.vault),
        svc,
        RecurringService(svc.vault),
        AlertService(svc.vault),
        MonthSummaryService(svc.vault),
    )


def _strip(home: HomeView) -> MonthSummaryStrip:
    strip = home.findChild(MonthSummaryStrip, "month_summary_strip")
    assert strip is not None
    return strip


def _text(home: HomeView) -> str:
    label = home.findChild(QLabel, "month_summary_text")
    assert label is not None
    return label.text()


def _select(home: HomeView, mode: str) -> None:
    home._period_selector.setCurrentIndex(home._period_selector.findData(mode))


class _RaisingSummary:
    """A stand-in that raises ``VaultLockedError`` **only on the month-summary
    read** — not on the first vault call. ``refresh()`` issues
    ``transaction_count()`` before it, so a stand-in raising on any read would
    make the leg pass against an implementation that never calls the service."""

    def summary(self, prefs, account_ids, today):
        raise VaultLockedError("the vault is locked")


class _RaisingPrefsWrite:
    """An ``AuthService`` proxy whose ``set_report_prefs`` raises — the auto-lock
    landing on the *persist*, which `_on_period_changed` performs **before**
    `refresh()`. Everything else delegates, so the view is otherwise live."""

    def __init__(self, real: AuthService) -> None:
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def set_report_prefs(self, prefs):
        raise VaultLockedError("the vault is locked")


class _RecordingSummary:
    """Records every ``(prefs, account_ids, today)`` the view hands the month
    summary, and delegates to the real service so the strip still renders."""

    def __init__(self, real: MonthSummaryService) -> None:
        self._real = real
        self.calls: list[tuple[object, object, date]] = []

    def summary(self, prefs, account_ids, today):
        self.calls.append((prefs, account_ids, today))
        return self._real.summary(prefs, account_ids, today)


class _RecordingReporting:
    """The same, for ``ReportingService.summary`` — the Net tile's source. The
    two argument sets are what INV-10 and INV-11 require to be identical."""

    def __init__(self, real: ReportingService) -> None:
        self._real = real
        self.calls: list[tuple[object, object, date]] = []

    def __getattr__(self, name):
        return getattr(self._real, name)

    def summary(self, prefs, account_ids, today=None):
        self.calls.append((prefs, account_ids, today))
        return self._real.summary(prefs, account_ids, today)


# --------------------------------------------------------------------------- #
# The period-mode wiring — the strip follows the selector across all five modes
# --------------------------------------------------------------------------- #
def test_the_previous_month_renders_a_sentence(qtbot, service) -> None:
    service.set_report_prefs(ReportPrefs(MODE_PREVIOUS_MONTH))
    _seed(service)
    home = _home(service)
    qtbot.addWidget(home)
    assert _strip(home).isHidden() is False
    assert _text(home) != ""


@pytest.mark.parametrize(
    "mode",
    [MODE_YEAR_TO_DATE, MODE_SPECIFIC_YEAR],
    ids=["year_to_date", "specific_year"],
)
def test_a_year_mode_hides_the_strip_entirely(qtbot, service, mode) -> None:
    """§ 3 decision 1: a year needs a year-over-year comparison and 24 months of
    history — FIBR-0175's territory, not this one's."""
    service.set_report_prefs(ReportPrefs(MODE_PREVIOUS_MONTH))
    _seed(service)
    home = _home(service)
    qtbot.addWidget(home)
    assert _strip(home).isHidden() is False  # showing before the switch

    _select(home, mode)
    assert _strip(home).isHidden() is True


def test_switching_back_to_a_month_mode_brings_the_strip_back(qtbot, service) -> None:
    service.set_report_prefs(ReportPrefs(MODE_PREVIOUS_MONTH))
    _seed(service)
    home = _home(service)
    qtbot.addWidget(home)

    _select(home, MODE_SPECIFIC_YEAR)
    assert _strip(home).isHidden() is True
    _select(home, MODE_PREVIOUS_MONTH)
    assert _strip(home).isHidden() is False


@pytest.mark.parametrize(
    "mode",
    [MODE_PREVIOUS_MONTH, MODE_CURRENT_MONTH, MODE_SPECIFIC_MONTH],
    ids=["previous_month", "current_month", "specific_month"],
)
def test_the_strip_shows_exactly_what_the_service_says(qtbot, service, mode) -> None:
    """The wiring contract: `HomeView` hides on ``None`` and shows otherwise, and
    decides nothing itself. Current month is the leg that varies with the real
    date — before the 7th its truncated head is under ``_MIN_ELAPSED_DAYS`` and
    the strip is correctly silent — so the expectation is read from the service
    rather than pinned."""
    service.set_report_prefs(ReportPrefs(MODE_PREVIOUS_MONTH))
    _seed(service)
    home = _home(service)
    qtbot.addWidget(home)
    if mode == MODE_SPECIFIC_MONTH:
        year, month = _prev_month(date.today().year, date.today().month)
        home._year_picker.setValue(year)
        home._month_picker.setCurrentIndex(home._month_picker.findData(month))
    _select(home, mode)

    expected = MonthSummaryService(service.vault).summary(
        home.current_prefs(), None, date.today()
    )
    assert _strip(home).isHidden() is (expected is None)


# --------------------------------------------------------------------------- #
# INV-13 (a) + (b) — a mid-render lock leaves no stale sentence
# --------------------------------------------------------------------------- #
def _home_showing(qtbot, service) -> HomeView:
    """Each INV-13 leg must FIRST drive a successful ``refresh()`` and assert the
    strip is showing a sentence: a fresh `HomeView` has the strip hidden already,
    so without that precondition the assertion passes against exactly the
    implementation it exists to fail."""
    service.set_report_prefs(ReportPrefs(MODE_PREVIOUS_MONTH))
    _seed(service)
    home = _home(service)
    qtbot.addWidget(home)
    assert _strip(home).isHidden() is False
    assert _text(home) != ""
    return home


def _home_showing_a_sentence(qtbot, service) -> HomeView:
    home = _home_showing(qtbot, service)
    home._month_summary = _RaisingSummary()  # type: ignore[assignment]
    return home


def test_INV13_a_lock_in_a_GUARDED_slot_leaves_no_stale_sentence(
    qtbot, service
) -> None:
    """``_on_period_changed`` catches ``VaultLockedError`` and must return
    cleanly — with the strip already cleared by ``refresh()``'s first statement."""
    home = _home_showing_a_sentence(qtbot, service)
    home._on_period_changed()  # must not raise
    assert _strip(home).isHidden() is True


def test_INV13_a_lock_in_an_UNGUARDED_slot_leaves_no_stale_sentence(
    qtbot, service
) -> None:
    """``set_amount_prefs`` (`home.py`, unguarded) propagates — and this is the
    leg that fails against a fix confined to the two ``except VaultLockedError``
    blocks. A stale *figure* in a tile is ambiguous; a stale *sentence* naming a
    month is a positive false claim."""
    home = _home_showing_a_sentence(qtbot, service)
    with pytest.raises(VaultLockedError):
        home.set_amount_prefs(AmountPrefs(NegativeStyle.BRACKETS, False))
    assert _strip(home).isHidden() is True


def test_INV13_a_lock_on_the_PREFS_WRITE_leaves_no_stale_sentence(
    qtbot, service
) -> None:
    """The third lock site, and the one `refresh()`'s own clear cannot reach:
    `_on_period_changed` **persists** the new period before it re-renders, so a
    lock landing on that write returns from the `except` without `refresh()` ever
    being entered. The selector has already moved by then, so the standing
    sentence names the wrong month — § 4.9's "whatever raises, and wherever, the
    strip is already empty" has to hold here too."""
    home = _home_showing(qtbot, service)
    home._auth = _RaisingPrefsWrite(service)  # type: ignore[assignment]
    home._on_period_changed()  # must not raise
    assert _strip(home).isHidden() is True


# --------------------------------------------------------------------------- #
# INV-10 / INV-11 — the HomeView halves: ONE clock, and the SAME account scope
#
# § 11 credits both invariants to the service suite, which proves the service
# behaves; neither can see whether `HomeView` hands it the right arguments.
# These two legs are what make those coverage claims true.
# --------------------------------------------------------------------------- #
class _TickingDate:
    """A ``date`` stand-in whose ``today()`` advances a day per call.

    An equality assertion over two real ``date.today()`` reads is vacuous — both
    return the same day except across a midnight boundary. Making every read
    differ is what turns "reads the clock once" into an observable property."""

    def __init__(self, start: date) -> None:
        self._start = start
        self.reads = 0

    def today(self) -> date:
        self.reads += 1
        return self._start + timedelta(days=self.reads - 1)


def _record(home: HomeView) -> tuple[_RecordingSummary, _RecordingReporting]:
    month = _RecordingSummary(home._month_summary)
    reporting = _RecordingReporting(home._reporting)
    home._month_summary = month  # type: ignore[assignment]
    home._reporting = reporting  # type: ignore[assignment]
    return month, reporting


def test_INV10_the_strip_and_the_net_tile_share_ONE_clock_reading(
    qtbot, service, monkeypatch
) -> None:
    """INV-10's second *Breaks when*: "`refresh()` computes `date.today()` twice
    across a midnight boundary". Under a ticking clock a second read is a
    different day, so the two services receive different values and this goes
    red — which a pair of real reads on the same day never would."""
    home = _home_showing(qtbot, service)
    month, reporting = _record(home)
    ticking = _TickingDate(date.today())
    monkeypatch.setattr("finbreak.ui.home.date", ticking)

    home.refresh()

    assert month.calls and reporting.calls
    assert month.calls[-1][2] == reporting.calls[-1][2]


def test_INV11_the_strip_and_the_net_tile_get_the_SAME_account_scope(
    qtbot, service
) -> None:
    """INV-11's *Breaks when*: "selecting one account leaves a whole-vault
    sentence above single-account tiles" — a `HomeView` wiring failure, invisible
    to the service suite. Passing `None` here instead of the selector's value
    goes red on both assertions."""
    second = AccountService(service.vault).add_account("Savings", "savings").id
    home = _home_showing(qtbot, service)
    month, reporting = _record(home)

    index = home._account_selector.findData(second)
    assert index > 0, "the second account must be in the selector"
    home._account_selector.setCurrentIndex(index)  # drives _on_account_changed

    assert month.calls and reporting.calls
    assert month.calls[-1][1] == reporting.calls[-1][1]
    assert month.calls[-1][1] == frozenset({second})
