"""FIBR-0013 D7 — ExportDialog: the INV-14 gating + account master-toggle state
machine + `options()` shape + pre-fill mapping.

Pure widget logic under the pytest-qt `qtbot`; the dialog holds no vault ref (it
is handed the account list + the pre-fill prefs), so no vault fixture is needed.
"""

import pytest
from PySide6.QtWidgets import QLineEdit

from finbreak.models import Account
from finbreak.services.pdf_export import ExportOptions
from finbreak.services.reporting import (
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    ReportPrefs,
)
from finbreak.ui.export_dialog import MIN_EXPORT_PASSWORD_LEN, ExportDialog

pytestmark = pytest.mark.features

_A = Account(1, "Current", "current", "2026-01-01T00:00:00Z")
_B = Account(2, "Savings", "savings", "2026-01-01T00:00:00Z")
_PREFS = ReportPrefs(MODE_SPECIFIC_MONTH, year=2026, month=1)


def _dialog(qtbot, accounts=(_A, _B), selected=None, prefs=_PREFS):
    d = ExportDialog(list(accounts), prefs, selected)
    qtbot.addWidget(d)
    return d


def _btn(d):
    return d._export_button()


# -- pre-fill --------------------------------------------------------------- #
def test_prefill_none_ticks_all_accounts(qtbot):
    d = _dialog(qtbot, selected=None)
    assert d._all_accounts_check.isChecked()
    assert d.options().account_ids is None


def test_prefill_specific_id_ticks_only_that_row(qtbot):
    d = _dialog(qtbot, selected=2)
    assert not d._all_accounts_check.isChecked()
    assert d.options().account_ids == frozenset({2})


def test_theme_defaults_to_light(qtbot):
    assert _dialog(qtbot).options().theme == "light"


def test_sections_default_all_on(qtbot):
    o = _dialog(qtbot).options()
    assert o.include_summary and o.include_charts and o.include_transactions


def test_options_is_export_options(qtbot):
    assert isinstance(_dialog(qtbot).options(), ExportOptions)


# -- INV-14 gating ---------------------------------------------------------- #
def test_export_disabled_with_no_section(qtbot):
    d = _dialog(qtbot)
    d._summary_check.setChecked(False)
    d._charts_check.setChecked(False)
    d._transactions_check.setChecked(False)
    assert not _btn(d).isEnabled()
    assert _btn(d).toolTip()  # the one-line reason


def test_export_disabled_with_no_account(qtbot):
    d = _dialog(qtbot, selected=None)
    d._all_accounts_check.setChecked(False)  # enables + ticks all rows
    for chk in d._account_checks.values():
        chk.setChecked(False)  # untick every row
    assert not _btn(d).isEnabled()


def test_password_too_short_disables(qtbot):
    d = _dialog(qtbot)
    d._password.setText("a" * (MIN_EXPORT_PASSWORD_LEN - 1))
    d._confirm.setText("a" * (MIN_EXPORT_PASSWORD_LEN - 1))
    assert not _btn(d).isEnabled()


def test_password_mismatch_disables(qtbot):
    d = _dialog(qtbot)
    d._password.setText("longenough")
    d._confirm.setText("different!!")
    assert not _btn(d).isEnabled()


def test_valid_password_enables_and_is_verbatim(qtbot):
    d = _dialog(qtbot)
    d._password.setText("longenough")
    d._confirm.setText("longenough")
    assert _btn(d).isEnabled()
    assert d.options().password == "longenough"


def test_blank_password_wins_over_typed_confirm(qtbot):
    d = _dialog(qtbot)
    d._confirm.setText("ignored12")  # blank password field wins (INV-1/INV-14)
    assert _btn(d).isEnabled()
    assert d.options().password is None


def test_whitespace_password_of_min_length_is_allowed(qtbot):
    d = _dialog(qtbot)
    spaces = " " * MIN_EXPORT_PASSWORD_LEN
    d._password.setText(spaces)
    d._confirm.setText(spaces)
    assert _btn(d).isEnabled()
    assert d.options().password == spaces  # not stripped


# -- account master-toggle state machine ------------------------------------ #
def test_all_accounts_disables_rows(qtbot):
    d = _dialog(qtbot, selected=None)
    assert all(not chk.isEnabled() for chk in d._account_checks.values())


def test_unticking_all_enables_and_pre_ticks_rows(qtbot):
    d = _dialog(qtbot, selected=None)
    d._all_accounts_check.setChecked(False)
    assert all(c.isEnabled() and c.isChecked() for c in d._account_checks.values())
    assert d.options().account_ids == frozenset({1, 2})  # a full set, not None


def test_reticking_every_row_stays_full_set_not_none(qtbot):
    d = _dialog(qtbot, selected=2)  # All off, only row 2 ticked
    for chk in d._account_checks.values():
        chk.setChecked(True)
    assert d.options().account_ids == frozenset({1, 2})  # only the master yields None


def test_show_toggle_unmasks_both_fields(qtbot):
    d = _dialog(qtbot)
    d._show_check.setChecked(True)
    assert d._password.echoMode() == QLineEdit.EchoMode.Normal
    assert d._confirm.echoMode() == QLineEdit.EchoMode.Normal
    d._show_check.setChecked(False)
    assert d._password.echoMode() == QLineEdit.EchoMode.Password


# -- period + helper text --------------------------------------------------- #
def test_options_prefs_come_from_the_selector(qtbot):
    d = _dialog(qtbot, prefs=ReportPrefs(MODE_SPECIFIC_YEAR, year=2025))
    prefs = d.options().prefs
    assert prefs.mode == MODE_SPECIFIC_YEAR
    assert prefs.year == 2025


def test_helper_text_mentions_blank_and_minimum(qtbot):
    d = _dialog(qtbot)  # hold a ref: a temporary is GC'd before `.text()` reads it
    text = d._helper.text().lower()
    assert "blank" in text
    assert str(MIN_EXPORT_PASSWORD_LEN) in text
