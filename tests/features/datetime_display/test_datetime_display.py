"""FIBR-0083 — display wiring (D5/D6/D7/INV-1). See spec.md.

The Statements Period/Imported + Home Date cells render through the pure
formatter under a held ``DateTimePrefs``; formatting never mutates stored data;
a Settings Save pushes new prefs to the open tabs live. Vault under ``tmp_path``.
"""

import pytest
from PySide6.QtWidgets import QComboBox

from conftest import _PW, _acct
from finbreak.datetime_format import format_date, format_timestamp
from finbreak.services.auth import AuthService, DateTimePrefs
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService
from finbreak.ui.home import HomeView
from finbreak.ui.main_window import MainWindow
from finbreak.ui.statements import StatementsWidget

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


# ---- D6: Home Date ----------------------------------------------------------


def test_home_date_uses_prefs(qtbot, service):
    TransactionService(service.vault).add_transaction(
        _acct(service), "2026-06-19", "-1.00", "coffee"
    )
    home = HomeView(
        TransactionService(service.vault),
        CategorizationService(service.vault),
        DateTimePrefs("system", "yyyy/MM/dd", "system"),
    )
    qtbot.addWidget(home)
    assert home._table.item(0, 0).text() == "2026/06/19"


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
    hv = HomeView(
        TransactionService(service.vault),
        CategorizationService(service.vault),
        _JHB,
    )
    qtbot.addWidget(hv)

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
    assert (
        window._home_tab._table.item(0, 0).text()
        == format_date("2026-06-19", "yyyy/MM/dd")
        == "2026/06/19"
    )
    assert window._statements_tab._table.item(0, _COL_PERIOD).text() == (
        "2026/06/01 – 2026/06/30"
    )
