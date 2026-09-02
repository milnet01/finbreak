"""FIBR-0083 — display wiring (D5/D6/D7/INV-1). See spec.md.

The Statements Period/Imported + Home Date cells render through the pure
formatter under a held ``DateTimePrefs``; formatting never mutates stored data;
a Settings Save pushes new prefs to the open tabs live. Vault under ``tmp_path``.
"""

import pytest
from PySide6.QtCore import QTimeZone
from PySide6.QtWidgets import QComboBox

from conftest import _PW, _acct
from finbreak.datetime_format import format_date, format_timestamp
from finbreak.services.auth import AuthService, DateTimePrefs
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService
from finbreak.ui._datetime_prefs import DATETIME_SYSTEM
from finbreak.ui.main_window import MainWindow
from finbreak.ui.statements import StatementsWidget
from finbreak.ui.transactions import TransactionsView

pytestmark = pytest.mark.features

_IMPORTED_AT = "2026-07-11T06:49:15.506928+00:00"
_JHB = DateTimePrefs("Africa/Johannesburg", "yyyy/MM/dd", "HH:mm")
_STMT_SQL = (
    "SELECT period_start, period_end, imported_at FROM statement_periods WHERE id=?"
)

# Statements table columns (mirror ui/statements.py).
_COL_PERIOD = 1
_COL_IMPORTED = 3


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _seed_statement(service) -> int:
    """A statement_periods row with a fixed period + UTC imported_at, so the
    formatted cells are deterministic. Returns the period id."""
    conn = service.vault.connection
    pid = conn.execute(
        "INSERT INTO statement_periods("
        "account_id, period_start, period_end, source_filename, imported_at) "
        "VALUES (?, '2026-06-01', '2026-06-30', 's.csv', ?)",
        (_acct(service), _IMPORTED_AT),
    ).lastrowid
    conn.commit()
    return pid


# ---- D5: Statements Period + Imported --------------------------------------


def test_statements_period_and_imported_use_prefs(qtbot, service):
    _seed_statement(service)
    widget = StatementsWidget(service, _JHB)
    qtbot.addWidget(widget)
    assert widget._table.item(0, _COL_PERIOD).text() == "2026/06/01 – 2026/06/30"
    assert widget._table.item(0, _COL_IMPORTED).text() == "2026/07/11 08:49"


# ---- D6: Transactions-tab Date (moved off Home when it became the dashboard) --


def test_transactions_date_uses_prefs(qtbot, service):
    TransactionService(service.vault).add_transaction(
        _acct(service), "2026-06-19", "-1.00", "coffee"
    )
    view = TransactionsView(
        TransactionService(service.vault),
        CategorizationService(service.vault),
        DateTimePrefs("system", "yyyy/MM/dd", "system"),
    )
    qtbot.addWidget(view)
    assert view._table.item(0, 0).text() == "2026/06/19"


# ---- INV-1: display-only, stored rows unchanged -----------------------------


def test_render_does_not_mutate_stored_rows(qtbot, service):
    pid = _seed_statement(service)
    TransactionService(service.vault).add_transaction(
        _acct(service), "2026-06-19", "-1.00", "coffee"
    )
    conn = service.vault.connection
    stmt_before = conn.execute(_STMT_SQL, (pid,)).fetchone()
    txn_before = conn.execute("SELECT occurred_on FROM transactions").fetchone()

    sw = StatementsWidget(service, _JHB)
    qtbot.addWidget(sw)
    tv = TransactionsView(
        TransactionService(service.vault),
        CategorizationService(service.vault),
        _JHB,
    )
    qtbot.addWidget(tv)

    assert (
        conn.execute(_STMT_SQL, (pid,)).fetchone()
        == stmt_before
        == ("2026-06-01", "2026-06-30", _IMPORTED_AT)
    )
    assert conn.execute("SELECT occurred_on FROM transactions").fetchone() == txn_before


# ---- D7 (widget): set_datetime_prefs re-renders -----------------------------


def test_widget_set_datetime_prefs_rerenders(qtbot, service):
    _seed_statement(service)
    widget = StatementsWidget(service, _JHB)
    qtbot.addWidget(widget)
    widget.set_datetime_prefs(DateTimePrefs("UTC", "yyyy-MM-dd", "HH:mm"))
    # Same instant, now in UTC with a dashed date.
    assert (
        widget._table.item(0, _COL_IMPORTED).text()
        == format_timestamp(_IMPORTED_AT, "UTC", "yyyy-MM-dd", "HH:mm")
        == "2026-07-11 06:49"
    )


# ---- D7 (shell): a Settings Save pushes new prefs to the open tabs ----------


def test_settings_save_pushes_prefs_to_open_tabs(qtbot, service):
    _seed_statement(service)
    TransactionService(service.vault).add_transaction(
        _acct(service), "2026-06-19", "-1.00", "coffee"
    )
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()

    # Fresh vault -> the shell holds all-"system" prefs; change the date format.
    window._action_settings.trigger()
    dialog = window._dialog
    date_combo = dialog.findChild(QComboBox, "settings_date_format")
    date_combo.setCurrentIndex(date_combo.findData("yyyy/MM/dd"))
    dialog._on_save()  # emits saved -> _on_settings_saved re-reads + pushes

    assert window._prefs.date_format == "yyyy/MM/dd"
    # The Date column lives on the Transactions tab now (Home is the dashboard).
    assert (
        window._transactions_tab._table.item(0, 0).text()
        == format_date("2026-06-19", "yyyy/MM/dd")
        == "2026/06/19"
    )
    assert window._statements_tab._table.item(0, _COL_PERIOD).text() == (
        "2026/06/01 – 2026/06/30"
    )


# --------------------------------------------------------------------------- #
# FIBR-0204 — a pinned timezone survives a Save even if the combo can't offer it
# --------------------------------------------------------------------------- #
def test_FIBR0204_unofferable_timezone_is_preserved_not_downgraded(qtbot, monkeypatch):
    """A stored timezone the combo cannot offer must round-trip, not silently
    become "system".

    `populate_datetime_combos` fills the combo from `QTimeZone.availableTimeZoneIds()`
    and preselects with `select_combo_data`, whose contract is to leave the
    selection UNCHANGED when `findData` misses — so the combo rests on item 0,
    `system`. `read_datetime_prefs` is unguarded and `SettingsDialog._on_save`
    writes it on EVERY save, touched or not. So opening Settings to change the
    auto-lock timeout and pressing Save silently repoints every timestamp at the
    machine's local zone: a wrong-day render for any transaction near midnight.

    The list follows the host's tzdata, and a vault is portable (backup/restore,
    or the same account on two machines). Zone ids really are renamed between
    releases — `Europe/Kiev` to `Europe/Kyiv`, `Asia/Rangoon` to `Asia/Yangon` —
    so a pref set on one machine can be unofferable on another. The monkeypatch
    below stands in for exactly that difference; the guard is what matters, not
    which id happens to be missing on today's box.
    """
    from finbreak.ui import _datetime_prefs

    pinned = "Africa/Johannesburg"
    assert QTimeZone(pinned.encode()).isValid(), "fixture must use a real zone"

    # Simulate a host whose tzdata does not enumerate the stored id.
    monkeypatch.setattr(
        _datetime_prefs,
        "_available_zone_ids",
        lambda: ["Europe/London", "America/New_York"],
    )

    tz, date, time = QComboBox(), QComboBox(), QComboBox()
    for combo in (tz, date, time):
        qtbot.addWidget(combo)
    _datetime_prefs.populate_datetime_combos(
        tz,
        date,
        time,
        system_tz_label="System",
        system_date_label="System",
        system_time_label="System",
        current=DateTimePrefs(
            timezone=pinned, date_format=DATETIME_SYSTEM, time_format=DATETIME_SYSTEM
        ),
    )

    read_back = _datetime_prefs.read_datetime_prefs(tz, date, time)
    assert read_back.timezone == pinned, (
        "an unrelated Save must not downgrade a pinned timezone to 'system' just "
        "because this host's tzdata does not enumerate it"
    )


# --------------------------------------------------------------------------- #
# FIBR-0327 — the pinned zone decides what "today" is, not just how a timestamp
# is displayed. Reporting, alerts and the forecast ran off `date.today()` (the
# machine's zone) while the Settings pin was display-only, so at a month
# boundary a whole month of totals moved with the traveller rather than with
# the vault.
# --------------------------------------------------------------------------- #
def test_FIBR0327_app_clock_follows_the_pinned_zone():
    """Two zones 25 hours apart disagree about the calendar day for one hour in
    every 24 — and always at a month boundary, which is where the totals move."""
    from finbreak.datetime_format import set_app_timezone, today, today_in

    east = today_in("Pacific/Kiritimati")  # UTC+14
    west = today_in("Pacific/Niue")  # UTC-11
    assert (east - west).days in (0, 1), "the two zones are at most a day apart"

    try:
        set_app_timezone("Pacific/Kiritimati")
        assert today() == east
        set_app_timezone("Pacific/Niue")
        assert today() == west
    finally:
        set_app_timezone(DATETIME_SYSTEM)


def test_FIBR0327_unknown_or_empty_zone_falls_back_to_the_system_day():
    """A stored pref can be a zone this build does not know (an OS update, a
    vault from another machine). It must not crash or return a wrong day."""
    from finbreak.datetime_format import set_app_timezone, today, today_in

    system_day = today_in(DATETIME_SYSTEM)
    assert today_in("Not/AZone") == system_day
    try:
        set_app_timezone("")
        assert today() == system_day
    finally:
        set_app_timezone(DATETIME_SYSTEM)


def test_FIBR0327_main_window_pushes_the_stored_pin_into_the_app_clock(qtbot, tmp_path):
    """The outcome, not the mechanism: after a Settings save the app clock is on
    the stored zone, so the next Home refresh computes its month there."""
    import finbreak.datetime_format as dtf
    from finbreak.datetime_format import today_in

    auth = AuthService(tmp_path / "vault.db", tmp_path / "vault.kdf.json")
    auth.first_run(bytearray(_PW), "ZAR")
    try:
        window = MainWindow(auth)
        qtbot.addWidget(window)
        auth.set_datetime_prefs(
            DateTimePrefs("Pacific/Kiritimati", DATETIME_SYSTEM, DATETIME_SYSTEM)
        )
        window._on_settings_saved()
        assert dtf.today() == today_in("Pacific/Kiritimati")
    finally:
        dtf.set_app_timezone(DATETIME_SYSTEM)
        auth.lock()


def test_FIBR0327_no_ui_module_reads_the_os_clock_directly():
    """FIBR-0327 replaced `date.today()` with the pinned-zone app clock at every
    UI site. Nothing stops the next one.

    A guard rather than a CLAUDE.md paragraph, because the failure is silent:
    one `date.today()` in a refresh path puts that widget on the machine's day
    while every sibling is on the user's, and at a month boundary the two
    disagree about which month's totals to show. There is no lint rule for it.

    Services are deliberately OUT of scope. `reporting.py` and `pdf_export.py`
    keep `today or date.today()` fallbacks: every date-bearing UI call passes
    `today` explicitly, so production never takes them, and importing
    `datetime_format` there would pull QtCore into the Qt-free service layer.
    """
    import re
    from pathlib import Path

    ui_dir = Path(__file__).resolve().parents[3] / "src" / "finbreak" / "ui"
    pattern = re.compile(r"\bdate\.today\(\)")
    offenders = [
        f"{path.name}:{n}"
        for path in sorted(ui_dir.glob("*.py"))
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == [], (
        "these UI sites read the OS clock instead of the pinned-zone app clock; "
        "use `from finbreak.datetime_format import today as app_today`:\n  "
        + "\n  ".join(offenders)
    )


def test_FIBR0327_a_free_typed_zone_is_what_gets_saved(qtbot, monkeypatch):
    """FIBR-0327 — the timezone combo is editable so a zone this host does not
    enumerate can still be pinned, and the guard for that could never fire.

    Typing text that matches no item leaves ``currentIndex`` — and so
    ``currentData()`` — on the PREVIOUS item, while the field shows what was
    typed. Measured: select Africa/Johannesburg, type Europe/Kyiv, and
    ``currentData()`` still reads Africa/Johannesburg. The old guard keyed on
    ``currentData()`` not being a ``str``, so it was dead code, and Save quietly
    wrote back the zone the user had just replaced.

    Since FIBR-0327 the pinned zone also decides what "today" is, so this is a
    wrong-day render from a preference the user believes they changed.
    """
    from finbreak.ui import _datetime_prefs

    typed = "Europe/Kyiv"
    assert QTimeZone(typed.encode()).isValid(), "fixture must use a real zone"

    # A host whose list offers neither the starting zone nor the typed one.
    monkeypatch.setattr(
        _datetime_prefs,
        "_available_zone_ids",
        lambda: ["Africa/Johannesburg", "Europe/London"],
    )
    tz, date, time = QComboBox(), QComboBox(), QComboBox()
    for combo in (tz, date, time):
        qtbot.addWidget(combo)
    _datetime_prefs.populate_datetime_combos(
        tz,
        date,
        time,
        system_tz_label="System",
        system_date_label="System",
        system_time_label="System",
        current=DateTimePrefs(
            timezone="Africa/Johannesburg",
            date_format=DATETIME_SYSTEM,
            time_format=DATETIME_SYSTEM,
        ),
    )

    tz.setCurrentText(typed)  # what free-typing into the field does

    assert tz.currentData() == "Africa/Johannesburg", (
        "precondition: the selected ITEM is still the old zone — that is the "
        "whole trap, and without it this test proves nothing"
    )
    read_back = _datetime_prefs.read_datetime_prefs(tz, date, time)
    assert read_back.timezone == typed, (
        "FIBR-0327: Save must write the zone the field is showing.\n"
        f"  expected: {typed}\n  actual:   {read_back.timezone}"
    )


def test_FIBR0327_free_typed_nonsense_still_degrades_to_system(qtbot):
    """Text that names no zone at all is not a pin — it degrades, so the field
    never persists something no clock can read."""
    from finbreak.ui import _datetime_prefs

    tz, date, time = QComboBox(), QComboBox(), QComboBox()
    for combo in (tz, date, time):
        qtbot.addWidget(combo)
    _datetime_prefs.populate_datetime_combos(
        tz,
        date,
        time,
        system_tz_label="System",
        system_date_label="System",
        system_time_label="System",
        current=DateTimePrefs(
            timezone=DATETIME_SYSTEM,
            date_format=DATETIME_SYSTEM,
            time_format=DATETIME_SYSTEM,
        ),
    )

    tz.setCurrentText("Narnia/Cair_Paravel")

    assert _datetime_prefs.read_datetime_prefs(tz, date, time).timezone == (
        DATETIME_SYSTEM
    )


def test_FIBR0327_selecting_the_system_item_still_reads_as_system(qtbot):
    """The System item's LABEL is translated prose and its data is the sentinel,
    so the text-decides rule must not mistake a plain selection for free text."""
    from finbreak.ui import _datetime_prefs

    tz, date, time = QComboBox(), QComboBox(), QComboBox()
    for combo in (tz, date, time):
        qtbot.addWidget(combo)
    _datetime_prefs.populate_datetime_combos(
        tz,
        date,
        time,
        system_tz_label="Use this computer's time zone",
        system_date_label="System",
        system_time_label="System",
        current=DateTimePrefs(
            timezone="Africa/Johannesburg",
            date_format=DATETIME_SYSTEM,
            time_format=DATETIME_SYSTEM,
        ),
    )
    tz.setCurrentIndex(0)

    assert _datetime_prefs.read_datetime_prefs(tz, date, time).timezone == (
        DATETIME_SYSTEM
    )
