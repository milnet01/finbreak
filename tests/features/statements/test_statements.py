"""FIBR-0052 — P07.6 tabbed workspace + statement provenance & delete.

Enforces tests/features/statements/spec.md. The data layer (v6 migration +
backfill, the provenance stamp, the atomic delete) is tested headless; the tab
workspace, window geometry, the Window menu, and the Statements tab round-trip
through the pytest-qt ``qtbot``. Every vault lives under ``tmp_path`` and the
window INI is redirected to ``tmp_path`` (autouse) so no test touches the real
data dir; CSV fixtures are tiny in-repo strings — no real data, no network.
"""

import pytest
import shiboken6
from PySide6.QtCore import QSettings
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import QDialog, QMessageBox
from sqlcipher3 import dbapi2

from conftest import (
    _PW,
    StandInVault,
    _acct,
    _pump_deferred_delete,
    build_v5_vault,
    keyed_connection,
    raising_conn,
)
from finbreak.crypto import SALT_LEN
from finbreak.migrations import run_migrations
from finbreak.models import ColumnMapping
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService
from finbreak.services.statements import StatementService
from finbreak.services.transactions import TransactionService
from finbreak.ui import main_window
from finbreak.ui.accounts import AccountsWidget
from finbreak.ui.import_wizard import ImportWizardWidget
from finbreak.ui.main_window import MainWindow
from finbreak.ui.statements import StatementsWidget

pytestmark = pytest.mark.features

HEADER = ["Date", "Details", "Amount"]
SINGLE = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to latest (v7)
    yield svc
    svc.lock()


def _csv(header, rows):
    return "\n".join([",".join(header)] + [",".join(r) for r in rows]) + "\n"


def _do_import(imp, text, account_id, source="stmt.csv"):
    preview = imp.preview(text, SINGLE, account_id)
    assert preview.period_start is not None and preview.period_end is not None
    return imp.commit_import(preview, preview.period_start, preview.period_end, source)


def _shell(qtbot, service) -> MainWindow:
    """An unlocked MainWindow driven past routing (as a real unlock success does).
    ``first_run`` left the service unlocked; ``_enter_unlocked`` builds the live
    workspace exactly as an unlock does."""
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    return window


def _seed_raw_v5(paths, salt):
    """A raw v5 vault (pre-provenance-column) + a keyed connection, for the
    backfill tests (INV-9d) — they run the real ``_migrate_to_v6``."""
    vault_path, sidecar_path = paths
    build_v5_vault(vault_path, sidecar_path, salt, [])
    return keyed_connection(vault_path, salt)


def _raw_period(conn, account_id, start, end):
    return conn.execute(
        "INSERT INTO statement_periods("
        "account_id, period_start, period_end, source_filename, imported_at) "
        "VALUES (?, ?, ?, 's.csv', '2026-01-01T00:00:00+00:00')",
        (account_id, start, end),
    ).lastrowid


def _raw_txn(conn, account_id, occurred_on, amount_minor=-100, description="x"):
    conn.execute(
        "INSERT INTO transactions("
        "account_id, occurred_on, amount_minor, description, created_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01T00:00:00+00:00')",
        (account_id, occurred_on, amount_minor, description),
    )


# --------------------------------------------------------------------------- #
# INV-8 — each imported row is stamped; manual entry stays NULL
# --------------------------------------------------------------------------- #
def test_INV8a_import_stamps_all_rows_manual_stays_null(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-20", "b", "-2.00"]]),
        acct,
    )
    period_id = StatementPeriodRepository(conn).list_for_account(acct)[0].id
    stamped = conn.execute("SELECT statement_period_id FROM transactions").fetchall()
    assert [r[0] for r in stamped] == [period_id, period_id], (
        "every imported row stamped"
    )

    TransactionService(service.vault).add_transaction(
        acct, "2026-01-10", "-5.00", "manual"
    )
    manual = conn.execute(
        "SELECT statement_period_id FROM transactions WHERE description = 'manual'"
    ).fetchone()
    assert manual[0] is None, "a manually-entered row belongs to no statement (NULL)"


def test_INV8c_span_reuse_stamps_existing_period_id(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-01", "a", "-1.00"], ["2026-01-31", "b", "-2.00"]]),
        acct,
    )
    period_id = StatementPeriodRepository(conn).list_for_account(acct)[0].id

    # Same span [01-01, 01-31], one new row inside it (FIBR-0007 INV-6 reuse path).
    text2 = _csv(
        HEADER,
        [
            ["2026-01-01", "a", "-1.00"],
            ["2026-01-15", "c", "-3.00"],
            ["2026-01-31", "b", "-2.00"],
        ],
    )
    result = _do_import(imp, text2, acct)
    assert result.inserted_count == 1 and result.period_recorded is False
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1, (
        "no 2nd period"
    )
    new = conn.execute(
        "SELECT statement_period_id FROM transactions WHERE description = 'c'"
    ).fetchone()
    assert new[0] == period_id, "the reused span's new row carries the existing id"


# --------------------------------------------------------------------------- #
# INV-9 — delete is atomic, isolated, FK-guarded; backfill is unambiguous-only
# --------------------------------------------------------------------------- #
def test_INV9a_delete_removes_only_target_stamped_rows(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "a1", "-1.00"], ["2026-01-06", "a2", "-2.00"]]),
        acct,
    )
    _do_import(imp, _csv(HEADER, [["2026-02-05", "b1", "-1.00"]]), acct)
    TransactionService(service.vault).add_transaction(
        acct, "2026-03-01", "-9.00", "manual"
    )

    periods = StatementPeriodRepository(conn).list_for_account(acct)
    a = next(p for p in periods if p.period_start == "2026-01-05")
    b = next(p for p in periods if p.period_start == "2026-02-05")

    deleted = StatementService(service.vault).delete_statement(a.id)
    assert deleted == 2, "exactly A's two stamped rows removed"
    assert {t.description for t in TransactionRepository(conn).list_all()} == {
        "b1",
        "manual",
    }
    assert [p.id for p in StatementPeriodRepository(conn).list_for_account(acct)] == [
        b.id
    ]


def test_INV9b_delete_atomic_rollback_between_deletes(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(imp, _csv(HEADER, [["2026-01-05", "a1", "-1.00"]]), acct)
    period_id = StatementPeriodRepository(conn).list_for_account(acct)[0].id

    wedge = StatementService(
        StandInVault(
            raising_conn(
                conn,
                "DELETE FROM statement_periods",
                "injected failure between the two deletes",
            )
        )
    )
    with pytest.raises(RuntimeError):
        wedge.delete_statement(period_id)

    # SAME connection, before any reopen: BOTH the transaction and the record remain.
    assert TransactionRepository(conn).count_for_account(acct) == 1
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1


def test_INV9c_direct_period_delete_with_children_raises(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(imp, _csv(HEADER, [["2026-01-05", "a1", "-1.00"]]), acct)
    period_id = StatementPeriodRepository(conn).list_for_account(acct)[0].id

    # Deleting the period row directly (leaving stamped children) violates the FK —
    # the plain (non-cascade) FK guards the unsafe path; the service's ordered
    # two-step delete is the sanctioned route (INV-9).
    with pytest.raises(dbapi2.IntegrityError):
        StatementPeriodRepository(conn).delete(period_id)
    conn.rollback()


def test_INV9d_backfill_links_unambiguous_only(paths):
    salt = bytes(range(SALT_LEN))
    conn = _seed_raw_v5(paths, salt)
    acct = conn.execute("SELECT id FROM accounts").fetchone()[0]
    period_id = _raw_period(conn, acct, "2026-01-01", "2026-01-31")
    for day in ("2026-01-05", "2026-01-10", "2026-01-20"):  # in-span
        _raw_txn(conn, acct, day)
    _raw_txn(conn, acct, "2026-02-15")  # out-of-span
    _raw_txn(conn, acct, "2026-03-01")  # out-of-span ("manual"-like)
    conn.commit()

    run_migrations(conn)  # v5 -> v8 (walks to LATEST); backfill inside the atomic step

    for occurred_on, spid in conn.execute(
        "SELECT occurred_on, statement_period_id FROM transactions"
    ).fetchall():
        if "2026-01-01" <= occurred_on <= "2026-01-31":
            assert spid == period_id, f"{occurred_on} in-span should be linked"
        else:
            assert spid is None, f"{occurred_on} out-of-span stays NULL"
    conn.close()


def test_INV9d_backfill_overlap_stays_null(paths):
    salt = bytes(range(SALT_LEN))
    conn = _seed_raw_v5(paths, salt)
    acct = conn.execute("SELECT id FROM accounts").fetchone()[0]
    p1 = _raw_period(conn, acct, "2026-01-01", "2026-01-20")
    _raw_period(conn, acct, "2026-01-10", "2026-01-31")  # overlaps p1 on 01-10..01-20
    _raw_txn(conn, acct, "2026-01-15", description="shared")  # under BOTH periods
    _raw_txn(conn, acct, "2026-01-05", description="single")  # under p1 only
    conn.commit()

    run_migrations(conn)  # v5 -> v8 (walks to LATEST)

    shared = conn.execute(
        "SELECT statement_period_id FROM transactions WHERE description = 'shared'"
    ).fetchone()
    assert shared[0] is None, "a date covered by two periods stays NULL (overlap guard)"
    single = conn.execute(
        "SELECT statement_period_id FROM transactions WHERE description = 'single'"
    ).fetchone()
    assert single[0] == p1, "a date under only one period is linked"
    conn.close()


# --------------------------------------------------------------------------- #
# INV-1 / INV-2 / INV-2a — the four-tab workspace + tab-switching navigation
# --------------------------------------------------------------------------- #
def test_INV1_workspace_has_eight_tabs_in_order(qtbot, service):
    window = _shell(qtbot, service)
    workspace = window.centralWidget().currentWidget()
    assert workspace.objectName() == "workspace"
    names = [workspace.widget(i).objectName() for i in range(workspace.count())]
    # Rules (FIBR-0010) is 6th, Transfers (FIBR-0011) 7th, Recurring (FIBR-0142) 8th;
    # Transactions (FIBR-0012) is inserted 2nd, right after Home.
    assert names == [
        "tab_home",
        "tab_transactions",
        "tab_statements",
        "tab_accounts",
        "tab_categories",
        "tab_rules",
        "tab_transfers",
        "tab_recurring",
    ]


def test_INV2_nav_actions_switch_the_workspace_tab(qtbot, service):
    window = _shell(qtbot, service)
    workspace = window._workspace
    for attr, index in (
        ("_action_transactions", 1),
        ("_action_statements", 2),
        ("_action_accounts", 3),
        ("_action_categories", 4),
        ("_action_home", 0),
    ):
        getattr(window, attr).trigger()
        assert workspace.currentIndex() == index, attr


def test_INV2_toolbar_order_includes_statements(qtbot, service):
    # FIBR-0136 (user request 2026-07-14): Statements now has a toolbar button too,
    # placed after Transactions to mirror the workspace tab order. It was previously
    # reachable only from the View menu — that omission surfaced dogfooding.
    window = _shell(qtbot, service)
    names = [a.objectName() for a in window._toolbar.actions()]
    assert names == [
        "action_home",
        "action_transactions",
        "action_statements",  # FIBR-0136: after Transactions (tab order)
        "action_manual_entry",
        "action_import",
        "action_accounts",
        "action_categories",
        "action_rules",
        "action_transfers",
        "action_recurring",
        "action_export",  # FIBR-0013: before Lock (Lock stays last)
        "action_lock",
    ], (
        "toolbar order: Home, Transactions, Statements, Manual entry, Import, "
        "Accounts, Categories, Rules, Transfers, Recurring, Export, Lock"
    )


# --------------------------------------------------------------------------- #
# INV-3a — a lock while importing destroys the wizard (no live import survives)
# --------------------------------------------------------------------------- #
def test_INV3a_lock_during_import_destroys_wizard(qtbot, service):
    window = _shell(qtbot, service)
    window._action_import.trigger()
    wizard = window._live
    assert isinstance(wizard, ImportWizardWidget)
    assert window.centralWidget().currentWidget() is wizard

    service._on_idle_timeout()  # idle auto-lock while the wizard is showing
    _pump_deferred_delete()
    assert not shiboken6.isValid(wizard), "the import wizard is destroyed on lock"
    assert window.centralWidget().currentWidget().objectName() == "placeholder_locked"


# --------------------------------------------------------------------------- #
# INV-5 / INV-5a — geometry + last tab round-trip, outside the vault, no data
# --------------------------------------------------------------------------- #
def test_INV5a_no_transaction_data_leaks_to_plaintext_ini(qtbot, service, window_ini):
    """Split out of the geometry round-trip (FIBR-0063): the window-geometry INI
    lives OUTSIDE the encrypted vault, so it must never carry transaction data. In
    its own test so a geometry-persistence regression can't mask a data leak."""
    TransactionService(service.vault).add_transaction(
        _acct(service), "2026-07-01", "-42.42", "ZZTOPSECRETMEMO"
    )
    window = _shell(qtbot, service)
    window.closeEvent(QCloseEvent())  # persists the INI

    blob = window_ini.read_bytes()
    assert b"ZZTOPSECRETMEMO" not in blob, "no transaction description in the INI"
    assert b"4242" not in blob, "no transaction amount in the INI"


def test_INV5a_geometry_and_tab_roundtrip_outside_vault(
    qtbot, service, window_ini, paths
):
    window = _shell(qtbot, service)
    window.resize(820, 540)
    window.move(60, 70)
    window._workspace.setCurrentIndex(2)  # Accounts tab
    before_bytes = bytes(window.saveGeometry())
    window.closeEvent(QCloseEvent())  # persists geometry + state + last tab (D7)

    assert window_ini.exists(), "geometry is persisted to the injected INI"
    vault_path, _ = paths
    assert window_ini != vault_path, "the INI is outside the vault file"

    # The INI stored exactly the window's saveGeometry blob (persistence proven).
    settings = QSettings(str(window_ini), QSettings.Format.IniFormat)
    assert bytes(settings.value("geometry")) == before_bytes

    window2 = MainWindow(service)  # reconstruct — geometry applied before unlock
    qtbot.addWidget(window2)
    # restoreGeometry applied it: the set height round-trips under the offscreen QPA
    # (width/x are adjusted by frame margins on this headless platform, so height is
    # the portable witness that the saved geometry was restored, not defaulted).
    assert window2.height() == 540, "the saved geometry is restored on reconstruct"
    assert window2.height() != main_window._DEFAULT_WINDOW_SIZE.height(), "not default"
    window2._enter_unlocked()
    assert window2._workspace.currentIndex() == 2, "the last-active tab is restored"


# --------------------------------------------------------------------------- #
# INV-6 — the Window menu: Center, Reset, both enabled while locked
# --------------------------------------------------------------------------- #
def test_INV6a_center_window(qtbot, service):
    window = _shell(qtbot, service)
    window._action_center_window.trigger()
    screen = window.screen() or QGuiApplication.primaryScreen()
    center = screen.availableGeometry().center()
    frame_center = window.frameGeometry().center()
    assert abs(frame_center.x() - center.x()) <= 1
    assert abs(frame_center.y() - center.y()) <= 1


def test_INV6b_reset_layout(qtbot, service, window_ini):
    window = _shell(qtbot, service)
    window.resize(900, 650)
    window._action_reset_layout.trigger()
    settings = QSettings(str(window_ini), QSettings.Format.IniFormat)
    assert settings.value("geometry") is None, "reset clears the saved geometry key"
    assert window.size() == main_window._DEFAULT_WINDOW_SIZE


def test_INV6c_window_menu_enabled_while_locked(qtbot, service):
    window = _shell(qtbot, service)
    window._action_lock.trigger()
    assert not window._menu_view.isEnabled(), "vault chrome is disabled while locked"
    assert window._action_center_window.isEnabled(), "Center needs no vault"
    assert window._action_reset_layout.isEnabled(), "Reset needs no vault"


# --------------------------------------------------------------------------- #
# FIBR-0060 — Wayland: the compositor owns placement, so restore SIZE only (a
# resize it honours) and centre via KWin on KDE (the only Wayland compositor
# with an app-usable placement API); Center is disabled on other Wayland
# compositors. Everything works fully on X11 / Windows / macOS.
# --------------------------------------------------------------------------- #
def test_FIBR0060_wayland_restores_size_via_resize(qtbot, service, monkeypatch):
    monkeypatch.setattr(main_window, "_is_wayland", lambda: True)
    window = _shell(qtbot, service)
    window.resize(900, 650)
    window.closeEvent(QCloseEvent())  # persists the size to the INI

    window2 = MainWindow(service)  # reconstruct under Wayland
    qtbot.addWidget(window2)
    # Wayland ignores a restored POSITION, so the size is restored explicitly via
    # resize() — both dimensions land exactly (no frame-margin fudge).
    assert (window2.width(), window2.height()) == (900, 650), (
        "the saved size is restored on Wayland (not defaulted)"
    )


def test_FIBR0060_center_dispatches_to_kwin_on_kde_wayland(qtbot, service, monkeypatch):
    monkeypatch.setattr(main_window, "_is_wayland", lambda: True)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    window = _shell(qtbot, service)
    assert window._action_center_window.isEnabled(), (
        "Center window is enabled on KDE Wayland (KWin can place it)"
    )
    called: list[bool] = []
    monkeypatch.setattr(window, "_center_kwin", lambda: called.append(True))
    window._action_center_window.trigger()
    assert called == [True], "KDE Wayland routes Center through the KWin backend"


def test_FIBR0060_center_disabled_on_non_kde_wayland(qtbot, service, monkeypatch):
    monkeypatch.setattr(main_window, "_is_wayland", lambda: True)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    window = _shell(qtbot, service)
    assert not window._action_center_window.isEnabled(), (
        "no app-usable placement API on non-KDE Wayland -> Center disabled"
    )
    assert window._action_center_window.toolTip() != "", "disabled action explains why"
    assert window._action_reset_layout.isEnabled(), "Reset still works (resizes)"
    # _center_window is called by Reset, so it must be a safe no-op here.
    before = window.pos()
    window._center_window()
    assert window.pos() == before, "center does not move the window here"


def test_FIBR0060_center_window_enabled_off_wayland(qtbot, service, monkeypatch):
    monkeypatch.setattr(main_window, "_is_wayland", lambda: False)
    window = _shell(qtbot, service)
    assert window._action_center_window.isEnabled(), (
        "Center window works on X11 / Windows / macOS"
    )


# --------------------------------------------------------------------------- #
# INV-7 — the Statements tab lists imports with an exact linked-transaction count
# --------------------------------------------------------------------------- #
def test_INV7a_statements_tab_shows_exact_counts(qtbot, service):
    imp, acct = ImportService(service.vault), _acct(service)
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-06", "b", "-2.00"]]),
        acct,
    )
    _do_import(imp, _csv(HEADER, [["2026-02-05", "c", "-1.00"]]), acct)

    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    assert widget.statement_count() == 2
    assert sorted(r.transaction_count for r in widget._rows) == [1, 2]

    TransactionService(service.vault).add_transaction(
        acct, "2026-03-01", "-9.00", "manual"
    )
    widget.refresh()
    assert sorted(r.transaction_count for r in widget._rows) == [1, 2], (
        "a manual (NULL-stamped) row changes no statement's count"
    )


def test_INV7b_zero_linked_statement_lists_as_zero(qtbot, service):
    imp, acct = ImportService(service.vault), _acct(service)
    rows = [["2026-01-05", "a", "-1.00"], ["2026-01-20", "b", "-2.00"]]
    _do_import(imp, _csv(HEADER, rows), acct)  # records span [01-05, 01-20], 2 rows

    # A NEW span whose every parsed row already exists -> a period row is created
    # but zero rows are stamped (all dedup to zero) -> lists with count 0 (LEFT JOIN).
    preview = imp.preview(_csv(HEADER, rows), SINGLE, acct)
    assert preview.new_count == 0
    result = imp.commit_import(preview, "2026-01-01", "2026-01-31", "s.csv")
    assert result.inserted_count == 0 and result.period_recorded is True

    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    zero = [r for r in widget._rows if r.period_start == "2026-01-01"]
    assert len(zero) == 1 and zero[0].transaction_count == 0, (
        "zero-linked still lists, count 0"
    )


# --------------------------------------------------------------------------- #
# INV-10 — delete is confirmed and refreshes; disabled without a selection
# --------------------------------------------------------------------------- #
def test_INV10_delete_disabled_without_selection(qtbot, service):
    imp, acct = ImportService(service.vault), _acct(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "a", "-1.00"]]), acct)
    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    assert widget.statement_count() == 1
    assert not widget._delete_button.isEnabled(), "Delete is disabled with no selection"


def test_INV10a_confirmed_delete_removes_and_emits(qtbot, service, monkeypatch):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-06", "b", "-2.00"]]),
        acct,
    )
    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    widget._select_period(widget._rows[0].id)
    assert widget._delete_button.isEnabled()

    # Capture the confirmation text to prove it NAMES the exact count (INV-10).
    captured = {}

    def _confirm_yes(parent, title, text, *a, **k):
        captured["text"] = text
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", _confirm_yes)
    emitted = []
    widget.changed.connect(lambda: emitted.append(True))
    widget._delete_button.click()

    assert "2" in captured["text"], "the confirmation names the exact count (2 rows)"
    assert emitted == [True], "changed emitted after a successful delete"
    assert widget.statement_count() == 0, "the row is gone"
    assert TransactionRepository(conn).count_for_account(acct) == 0, (
        "its transactions gone"
    )


def test_INV10b_cancelled_delete_does_nothing(qtbot, service, monkeypatch):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(imp, _csv(HEADER, [["2026-01-05", "a", "-1.00"]]), acct)
    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    widget._select_period(widget._rows[0].id)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    widget._delete_button.click()

    assert widget.statement_count() == 1, "Cancel deletes nothing"
    assert TransactionRepository(conn).count_for_account(acct) == 1


# --------------------------------------------------------------------------- #
# INV-11a — a change reflects on the Home tab when it is next activated
# --------------------------------------------------------------------------- #
def test_INV11a_home_reflects_change_on_activation(qtbot, service):
    window = _shell(qtbot, service)
    before = window._home_tab.transaction_count()

    TransactionService(service.vault).add_transaction(
        _acct(service), "2026-01-01", "-5.00", "x"
    )
    window._workspace.setCurrentIndex(2)  # away to Accounts
    window._workspace.setCurrentIndex(0)  # back to Home -> currentChanged refreshes

    assert window._home_tab.transaction_count() == before + 1
    assert str(before + 1) in window._count.text(), (
        "the status count reflects the change"
    )


def test_INV11_statement_delete_refreshes_home_and_count(qtbot, service, monkeypatch):
    window = _shell(qtbot, service)
    imp, acct = ImportService(service.vault), _acct(service)
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-06", "b", "-2.00"]]),
        acct,
    )
    window._action_statements.trigger()  # activates + refreshes the Statements tab
    statements = window._statements_tab
    assert statements.statement_count() == 1

    statements._select_period(statements._rows[0].id)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    statements._delete_button.click()

    assert window._home_tab.transaction_count() == 0, "Home refreshed after the delete"
    assert "0" in window._count.text(), "the status count refreshed after the delete"
    assert window.statusBar().currentMessage() == "Statement deleted", (
        "the shell reports the delete in the status bar (INV-10)"
    )


def test_INV11_import_done_rebuilds_workspace_lands_on_statements(qtbot, service):
    # The import-flow done path (D5/INV-11): the wizard replaces the workspace,
    # and on `done` the shell rebuilds a fresh workspace, lands on Statements, and
    # refreshes Home + the count.
    window = _shell(qtbot, service)
    imp, acct = ImportService(service.vault), _acct(service)
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-06", "b", "-2.00"]]),
        acct,
    )

    window._action_import.trigger()  # the wizard replaces the workspace (INV-3/D5)
    assert isinstance(window._live, ImportWizardWidget)
    window._live.done.emit()  # the wizard signals completion

    workspace = window.centralWidget().currentWidget()
    assert workspace.objectName() == "workspace", "a fresh workspace is rebuilt"
    assert workspace.currentWidget().objectName() == "tab_statements", (
        "lands on the Statements tab"
    )
    assert window._statements_tab.statement_count() == 1, "the statement is listed"
    assert window._home_tab.transaction_count() == 2, (
        "Home refreshed to the imported rows"
    )
    assert "2" in window._count.text(), "the status count refreshed"


# --------------------------------------------------------------------------- #
# INV-12a — Accounts/Categories in tab mode have no Done button
# --------------------------------------------------------------------------- #
def test_INV12a_tab_widgets_have_no_done_button(qtbot, service):
    window = _shell(qtbot, service)
    assert window._accounts_tab._done_button is None, "no Done on the Accounts tab"
    assert window._categories_tab._done_button is None, "no Done on the Categories tab"

    standalone = AccountsWidget(service)  # default show_done=True
    qtbot.addWidget(standalone)
    assert standalone._done_button is not None, "a standalone AccountsWidget keeps Done"


# --------------------------------------------------------------------------- #
# FIBR-0059 — edit a logged statement's account (re-point the period + its
# transactions atomically); enforces docs/specs/FIBR-0059.md.
# --------------------------------------------------------------------------- #
def _second_account(service, name="Credit Card", type="credit_card") -> int:
    """A second account id (the fixture seeds only the migration's 'Default')."""
    return AccountService(service.vault).add_account(name, type).id


class _AccountPickerStub(QDialog):
    """Real QDialog stand-in for AccountPickerDialog: auto-accepts (or rejects) on
    show() so the async _apply_reassign slot runs synchronously through show_modal's
    real setModal/accepted/finished wiring (FIBR-0065 INV-5)."""

    def __init__(self, parent, account_id, accept):
        super().__init__(parent)
        self._account_id = account_id
        self._accept = accept

    def show(self):
        super().show()
        if self._accept:
            self.accept()
        else:
            self.reject()

    def selected_account_id(self):
        return self._account_id


def _stub_picker(monkeypatch, account_id, accept=True):
    """Replace ``statements.AccountPickerDialog`` with a real auto-driving QDialog
    stand-in returning ``account_id`` (the modal picker's stand-in)."""
    from finbreak.ui import statements as statements_mod

    monkeypatch.setattr(
        statements_mod,
        "AccountPickerDialog",
        lambda accounts, current, parent=None: _AccountPickerStub(
            parent, account_id, accept
        ),
    )


def _period_id(conn, account_id) -> int:
    return StatementPeriodRepository(conn).list_for_account(account_id)[0].id


# -- service: INV-1 atomic move + INV-4 count -------------------------------- #
def test_FIBR0059_reassign_moves_period_and_all_transactions(service):
    imp, a, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    b = _second_account(service)
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "x", "-1.00"], ["2026-01-06", "y", "-2.00"]]),
        a,
    )
    pid = _period_id(conn, a)

    moved = StatementService(service.vault).reassign_account(pid, b)

    assert moved == 2, "returns the number of transactions moved (INV-4)"
    assert StatementPeriodRepository(conn).get(pid).account_id == b, "period re-pointed"
    assert TransactionRepository(conn).count_for_account(b) == 2, (
        "all txns on the new account"
    )
    assert TransactionRepository(conn).count_for_account(a) == 0, "none left on the old"


def test_FIBR0059_reassign_atomic_rollback(service):
    imp, a, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    b = _second_account(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "x", "-1.00"]]), a)
    pid = _period_id(conn, a)

    wedge = StatementService(
        StandInVault(
            raising_conn(
                conn, "UPDATE transactions", "injected failure after the period update"
            )
        )
    )
    with pytest.raises(RuntimeError):
        wedge.reassign_account(pid, b)

    # SAME connection, before any reopen: NEITHER table changed.
    assert StatementPeriodRepository(conn).get(pid).account_id == a, (
        "period rolled back"
    )
    assert TransactionRepository(conn).count_for_account(a) == 1, "txn rolled back"
    assert TransactionRepository(conn).count_for_account(b) == 0


# -- service: INV-2 isolation ------------------------------------------------ #
def test_FIBR0059_reassign_leaves_manual_and_other_statements(service):
    imp, a, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    b = _second_account(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "s1", "-1.00"]]), a, source="s1.csv")
    _do_import(imp, _csv(HEADER, [["2026-02-05", "s2", "-3.00"]]), a, source="s2.csv")
    TransactionService(service.vault).add_transaction(
        a, "2026-03-01", "-9.00", "manual"
    )
    s1 = [
        p
        for p in StatementPeriodRepository(conn).list_for_account(a)
        if p.period_start == "2026-01-05"
    ][0].id

    StatementService(service.vault).reassign_account(s1, b)

    # Only s1's one row moved; the manual row and s2's row stay on account a.
    assert TransactionRepository(conn).count_for_account(b) == 1, "only s1 moved"
    assert TransactionRepository(conn).count_for_account(a) == 2, (
        "manual + s2 untouched"
    )
    rows = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT description, statement_period_id FROM transactions"
        ).fetchall()
    }
    assert rows["manual"] is None, "the manual (NULL-stamped) row is untouched"


# -- service: INV-3 span guard (+ self-exclusion) ---------------------------- #
def test_FIBR0059_reassign_refused_on_span_collision(service):
    imp, a, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    b = _second_account(service)
    span = [["2026-01-05", "x", "-1.00"]]
    _do_import(imp, _csv(HEADER, span), a)  # a's statement for the span
    _do_import(imp, _csv(HEADER, span), b)  # b ALREADY has one for the same span
    pid_a = [p for p in StatementPeriodRepository(conn).list_for_account(a)][0].id

    with pytest.raises(ValueError, match="already has a statement"):
        StatementService(service.vault).reassign_account(pid_a, b)

    # No change: a's statement + rows stay put.
    assert StatementPeriodRepository(conn).get(pid_a).account_id == a
    assert TransactionRepository(conn).count_for_account(a) == 1


def test_FIBR0059_reassign_same_account_is_noop_returning_count(service):
    imp, a, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(
        imp,
        _csv(HEADER, [["2026-01-05", "x", "-1.00"], ["2026-01-06", "y", "-2.00"]]),
        a,
    )
    pid = _period_id(conn, a)

    # Same account: the self-exclusion (existing == period_id) must NOT refuse; the
    # matched-row UPDATE returns the txn count, not 0 (INV-5).
    moved = StatementService(service.vault).reassign_account(pid, a)
    assert moved == 2
    assert StatementPeriodRepository(conn).get(pid).account_id == a


# -- service: INV-6 verbatim move (no dedup) + INV-4 zero -------------------- #
def test_FIBR0059_reassign_moves_verbatim_no_dedup(service):
    imp, a, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    b = _second_account(service)
    # b already has a manual row identical to the one in a's statement.
    TransactionService(service.vault).add_transaction(b, "2026-01-05", "-1.00", "x")
    _do_import(imp, _csv(HEADER, [["2026-01-05", "x", "-1.00"]]), a)
    pid = _period_id(conn, a)

    moved = StatementService(service.vault).reassign_account(pid, b)

    assert moved == 1, "the statement's row is moved, not deduped away"
    assert TransactionRepository(conn).count_for_account(b) == 2, (
        "both rows coexist on b"
    )


def test_FIBR0059_reassign_zero_txn_statement_returns_zero(service):
    conn = service.vault.connection
    a, b = _acct(service), _second_account(service)
    # A statement period with no linked transactions.
    pid = StatementPeriodRepository(conn).add(
        a, "2026-05-01", "2026-05-31", "empty.csv"
    )
    conn.commit()

    moved = StatementService(service.vault).reassign_account(pid, b)
    assert moved == 0, "no transactions to move"
    assert StatementPeriodRepository(conn).get(pid).account_id == b, (
        "period still re-pointed"
    )


# -- UI (widget) ------------------------------------------------------------- #
def test_FIBR0059_reassign_button_disabled_without_selection(qtbot, service):
    imp, a = ImportService(service.vault), _acct(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "x", "-1.00"]]), a)
    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    assert not widget._reassign_button.isEnabled(), (
        "Change account disabled with no selection"
    )


def test_FIBR0059_picker_preselects_current_account(qtbot, service):
    from finbreak.ui.account_picker import AccountPickerDialog

    _second_account(service)
    c = _second_account(service, "Savings", "savings")
    accounts = AccountService(service.vault).list_accounts()
    # Preselect the LAST account (c) — deliberately not index 0 — so a broken
    # findData (which would leave index 0) fails the assertion (INV-9, non-vacuous).
    assert accounts[0].id != c, "current is not at index 0"
    dialog = AccountPickerDialog(accounts, c, None)
    qtbot.addWidget(dialog)
    assert dialog.selected_account_id() == c, (
        "the picker preselects the current account"
    )


def test_FIBR0059_reassign_round_trip_changes_row_and_emits(
    qtbot, service, monkeypatch
):
    imp, a = ImportService(service.vault), _acct(service)
    b = _second_account(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "x", "-1.00"]]), a)
    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    widget._select_period(widget._rows[0].id)

    _stub_picker(monkeypatch, b)
    emitted = []
    widget.reassigned.connect(lambda: emitted.append(True))
    widget._reassign_button.click()

    assert emitted == [True], "reassigned emitted after a successful move"
    assert widget._table.item(0, 0).text() == "Credit Card", (
        "the row's Account column (col 0) shows the new account"
    )


def test_FIBR0059_same_account_pick_skips_service(qtbot, service, monkeypatch):
    imp, a = ImportService(service.vault), _acct(service)
    _second_account(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "x", "-1.00"]]), a)
    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    widget._select_period(widget._rows[0].id)

    # Pick the CURRENT account -> the widget must short-circuit (no service call).
    _stub_picker(monkeypatch, a)
    called = []
    monkeypatch.setattr(
        widget._statements, "reassign_account", lambda *a, **k: called.append(True)
    )
    emitted = []
    widget.reassigned.connect(lambda: emitted.append(True))
    widget._reassign_button.click()

    assert called == [], "a same-account pick does not call the service (INV-5)"
    assert emitted == [], "and does not emit reassigned"


def test_FIBR0059_span_collision_shows_warning(qtbot, service, monkeypatch):
    imp, a, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    b = _second_account(service)
    span = [["2026-01-05", "x", "-1.00"]]
    _do_import(imp, _csv(HEADER, span), a)
    _do_import(imp, _csv(HEADER, span), b)  # b already has the same span
    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    a_row = [r for r in widget._rows if r.account_id == a][0]  # move a's statement to b
    widget._select_period(a_row.id)

    _stub_picker(monkeypatch, b)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(True))
    widget._reassign_button.click()

    assert warned == [True], "a span collision surfaces a warning"
    assert TransactionRepository(conn).count_for_account(a) == 1, "no change on a"


def test_FIBR0059_reassign_autolock_caught(qtbot, service, monkeypatch):
    from finbreak.errors import VaultLockedError

    imp, a = ImportService(service.vault), _acct(service)
    b = _second_account(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "x", "-1.00"]]), a)
    widget = StatementsWidget(service)
    qtbot.addWidget(widget)
    widget._select_period(widget._rows[0].id)

    _stub_picker(monkeypatch, b)

    def _raise(*a, **k):
        raise VaultLockedError("auto-locked mid-move")

    monkeypatch.setattr(widget._statements, "reassign_account", _raise)
    widget._reassign_button.click()  # must not raise out of the slot
    assert TransactionRepository(service.vault.connection).count_for_account(a) == 1, (
        "the guarded reassign left the transaction on account a"
    )


# -- UI (shell): INV-8 status message ---------------------------------------- #
def test_FIBR0059_shell_reports_account_changed(qtbot, service, monkeypatch):
    window = _shell(qtbot, service)
    imp, a = ImportService(service.vault), _acct(service)
    b = _second_account(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "x", "-1.00"]]), a)
    window._action_statements.trigger()
    statements = window._statements_tab
    statements._select_period(statements._rows[0].id)

    _stub_picker(monkeypatch, b)
    statements._reassign_button.click()

    assert window.statusBar().currentMessage() == "Statement account changed", (
        "the shell reports the MOVE (not 'Statement deleted') in the status bar"
    )


def test_list_statements_ordered_by_import_recency(service):
    """list_statements orders by import recency then id (FIBR-0064): two imports
    surface in insertion order."""
    imp = ImportService(service.vault)
    acct = _acct(service)
    _do_import(imp, _csv(HEADER, [["2026-01-05", "a", "-1.00"]]), acct, "first.csv")
    _do_import(imp, _csv(HEADER, [["2026-02-05", "b", "-1.00"]]), acct, "second.csv")
    rows = StatementService(service.vault).list_statements()
    assert [r.source_filename for r in rows] == ["first.csv", "second.csv"]


# --------------------------------------------------------------------------- #
# FIBR-0148 — deleting a statement hands off transactions a REMAINING
# overlapping statement still covers, instead of silently losing them.
# --------------------------------------------------------------------------- #
def _import_span(imp, text, acct, start, end, source="stmt.csv"):
    """Import with an EXPLICIT coverage span (not the auto-detected row min/max),
    so the overlap fixtures pin exactly which statement's period covers which
    dates."""
    preview = imp.preview(text, SINGLE, acct)
    return imp.commit_import(preview, start, end, source)


def _pid_of(conn, desc):
    """The ``statement_period_id`` stamped on the row with this description."""
    return conn.execute(
        "SELECT statement_period_id FROM transactions WHERE description = ?", (desc,)
    ).fetchone()[0]


def _period_files(conn, acct):
    """The source filenames of every recorded period for ``acct``, in list order."""
    periods = StatementPeriodRepository(conn).list_for_account(acct)
    return [p.source_filename for p in periods]


def _build_full_overlap(service):
    """A(Jan) + B(Jan–Feb) where B's period covers **all** of A's January rows.
    A is imported first, so its two January rows are stamped to A; B's copies of
    them dedup away (only b1/Feb is inserted, stamped to B). Returns
    ``(acct, conn, a, b)`` with ``a``/``b`` the two ``StatementPeriod`` rows."""
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-10", "a1", "-1.00"], ["2026-01-20", "a2", "-2.00"]]),
        acct,
        "2026-01-10",
        "2026-01-20",
        "A.csv",
    )
    r = _import_span(
        imp,
        _csv(
            HEADER,
            [
                ["2026-01-10", "a1", "-1.00"],
                ["2026-01-20", "a2", "-2.00"],
                ["2026-02-15", "b1", "-3.00"],
            ],
        ),
        acct,
        "2026-01-01",
        "2026-02-28",
        "B.csv",
    )
    assert r.inserted_count == 1 and r.period_recorded is True
    periods = {
        p.source_filename: p
        for p in StatementPeriodRepository(conn).list_for_account(acct)
    }
    return acct, conn, periods["A.csv"], periods["B.csv"]


def test_INV1_overlap_delete_hands_off_not_loses(service):
    """The reproduce-first bug: deleting A must NOT lose the January rows B still
    covers — they are handed off to B, and the call reports 0 orphaned."""
    acct, conn, a, b = _build_full_overlap(service)

    deleted = StatementService(service.vault).delete_statement(a.id)

    survivors = {t.description for t in TransactionRepository(conn).list_all()}
    assert survivors == {"a1", "a2", "b1"}, "January rows survive B's coverage"
    assert _pid_of(conn, "a1") == b.id and _pid_of(conn, "a2") == b.id, "handed to B"
    assert deleted == 0, "B covered every A row, so nothing was orphaned"
    assert _period_files(conn, acct) == ["B.csv"], "only A's period row removed"


def test_INV2_orphans_deleted_when_nothing_remains_to_cover(service):
    """A transaction no remaining statement covers is still deleted (the return
    count equals the rows actually removed)."""
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-10", "a1", "-1.00"], ["2026-01-20", "a2", "-2.00"]]),
        acct,
        "2026-01-10",
        "2026-01-20",
        "A.csv",
    )
    a = StatementPeriodRepository(conn).list_for_account(acct)[0]
    deleted = StatementService(service.vault).delete_statement(a.id)
    assert deleted == 2, "both rows orphaned (no other statement) and deleted"
    assert TransactionRepository(conn).list_all() == []


def test_INV2_zero_linked_delete_returns_zero_and_touches_nothing(service):
    """Deleting a zero-linked statement (all rows deduped at import) hands off and
    deletes nothing, removes only its period row, and returns 0 — and never
    disturbs a row another statement owns."""
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-10", "a1", "-1.00"]]),
        acct,
        "2026-01-10",
        "2026-01-10",
        "A.csv",
    )
    # Same row (dedups to 0 inserted) but a DIFFERENT, wider span -> zero-linked B.
    r = _import_span(
        imp,
        _csv(HEADER, [["2026-01-10", "a1", "-1.00"]]),
        acct,
        "2026-01-01",
        "2026-02-28",
        "B.csv",
    )
    assert r.inserted_count == 0 and r.period_recorded is True
    b = next(
        p
        for p in StatementPeriodRepository(conn).list_for_account(acct)
        if p.source_filename == "B.csv"
    )
    deleted = StatementService(service.vault).delete_statement(b.id)
    assert deleted == 0
    assert {t.description for t in TransactionRepository(conn).list_all()} == {"a1"}
    assert _pid_of(conn, "a1") is not None, "a1 still owned by A (untouched)"
    assert _period_files(conn, acct) == ["A.csv"]


def test_INV3_delete_never_creates_a_null_stamped_row(service):
    """No row is silently turned into a manual (NULL-stamped) row by a delete."""
    acct, conn, a, _b = _build_full_overlap(service)

    def null_count():
        return conn.execute(
            "SELECT count(*) FROM transactions WHERE statement_period_id IS NULL"
        ).fetchone()[0]

    assert null_count() == 0
    StatementService(service.vault).delete_statement(a.id)
    assert null_count() == 0, "covered rows moved to B; none became manual"


def test_INV4_rollback_after_handoff_restores_everything(service):
    """Atomic: a failure AFTER the hand-off UPDATE rolls back the re-stamp too —
    the vault re-opens with A, B, and every row exactly as before."""
    acct, conn, a, _b = _build_full_overlap(service)

    # Wedge the orphan-delete (step 2), which runs after the hand-off (step 1).
    wedge = StatementService(
        StandInVault(
            raising_conn(
                conn, "DELETE FROM transactions", "injected failure after hand-off"
            )
        )
    )
    with pytest.raises(RuntimeError):
        wedge.delete_statement(a.id)

    # Same connection, before any reopen: the hand-off re-stamp is undone too.
    assert {t.description for t in TransactionRepository(conn).list_all()} == {
        "a1",
        "a2",
        "b1",
    }
    assert _pid_of(conn, "a1") == a.id and _pid_of(conn, "a2") == a.id, (
        "re-stamp rolled back"
    )
    assert any(
        p.id == a.id for p in StatementPeriodRepository(conn).list_for_account(acct)
    ), "A's period row survives the rollback"


def test_INV5_deterministic_owner_is_earliest_period(service):
    """When >=2 remaining statements cover a row's date, it is handed to the one
    ordered first by (period_start, id)."""
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-15", "x", "-1.00"]]),
        acct,
        "2026-01-15",
        "2026-01-15",
        "A.csv",
    )
    # B [01-01, 01-15] and C [01-10, 01-20] both cover 01-15; B starts earlier.
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-15", "x", "-1.00"], ["2026-01-01", "b0", "-5.00"]]),
        acct,
        "2026-01-01",
        "2026-01-15",
        "B.csv",
    )
    _import_span(
        imp,
        _csv(
            HEADER,
            [
                ["2026-01-15", "x", "-1.00"],
                ["2026-01-10", "c0", "-6.00"],
                ["2026-01-20", "c1", "-7.00"],
            ],
        ),
        acct,
        "2026-01-10",
        "2026-01-20",
        "C.csv",
    )
    periods = {
        p.source_filename: p
        for p in StatementPeriodRepository(conn).list_for_account(acct)
    }
    StatementService(service.vault).delete_statement(periods["A.csv"].id)
    assert _pid_of(conn, "x") == periods["B.csv"].id, "handed to the earliest-starting"


def test_INV6_handoff_is_account_scoped(service):
    """An overlapping period on a DIFFERENT account never adopts a row — the
    uncovered (same-account) row is orphaned and deleted; the other account is
    untouched."""
    imp, conn = ImportService(service.vault), service.vault.connection
    acct1 = _acct(service)
    acct2 = AccountService(service.vault).add_account("Savings", "savings").id
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-15", "x", "-1.00"]]),
        acct1,
        "2026-01-15",
        "2026-01-15",
        "A.csv",
    )
    # A statement on acct2 whose period covers 01-15 — but it is a different account.
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-15", "y", "-1.00"]]),
        acct2,
        "2026-01-01",
        "2026-02-28",
        "OTHER.csv",
    )
    a = StatementPeriodRepository(conn).list_for_account(acct1)[0]
    deleted = StatementService(service.vault).delete_statement(a.id)
    assert deleted == 1, "no SAME-account statement covers x -> orphaned + deleted"
    assert {t.description for t in TransactionRepository(conn).list_all()} == {"y"}


def test_INV7_handoff_changes_only_provenance(service):
    """Hand-off changes statement_period_id alone — every other column of the
    moved row is byte-identical."""
    acct, conn, a, b = _build_full_overlap(service)
    cols = "account_id, occurred_on, amount_minor, description, category_id"
    before = conn.execute(
        f"SELECT {cols} FROM transactions WHERE description = 'a1'"
    ).fetchone()
    StatementService(service.vault).delete_statement(a.id)
    after = conn.execute(
        f"SELECT {cols} FROM transactions WHERE description = 'a1'"
    ).fetchone()
    assert after == before, "only statement_period_id changed on the handed-off row"
    assert _pid_of(conn, "a1") == b.id


def test_INV8_partial_overlap_splits_handoff_and_delete(service):
    """A remaining statement covering only SOME of the deleted statement's dates
    both hands off the covered rows and deletes the uncovered ones in one call."""
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    # A covers 01-05 (e) + 01-20 (l).
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-05", "e", "-1.00"], ["2026-01-20", "l", "-2.00"]]),
        acct,
        "2026-01-05",
        "2026-01-20",
        "A.csv",
    )
    # B [01-15, 02-28] covers 01-20 (l) but NOT 01-05 (e).
    _import_span(
        imp,
        _csv(HEADER, [["2026-01-20", "l", "-2.00"], ["2026-02-10", "b1", "-3.00"]]),
        acct,
        "2026-01-15",
        "2026-02-28",
        "B.csv",
    )
    periods = {
        p.source_filename: p
        for p in StatementPeriodRepository(conn).list_for_account(acct)
    }
    deleted = StatementService(service.vault).delete_statement(periods["A.csv"].id)
    assert deleted == 1, "only the uncovered 01-05 row is orphaned"
    remaining = {t.description for t in TransactionRepository(conn).list_all()}
    assert remaining == {"l", "b1"}
    assert _pid_of(conn, "l") == periods["B.csv"].id, "the covered row handed to B"


def test_INV9_delete_preserves_shared_money(service):
    """Money-safety: a full-overlap delete lowers the vault total by exactly the
    orphaned rows' sum — zero here, since every row is handed off, not deleted."""
    acct, conn, a, _b = _build_full_overlap(service)

    def total():
        return conn.execute(
            "SELECT COALESCE(SUM(amount_minor), 0) FROM transactions"
        ).fetchone()[0]

    before = total()
    deleted = StatementService(service.vault).delete_statement(a.id)
    assert deleted == 0
    assert total() == before, "no money lost — shared rows handed off, not deleted"
