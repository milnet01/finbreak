"""FIBR-0005 — P03 accounts. Enforces tests/features/accounts/spec.md.

Account model + CRUD + the accounts-manager UI, and the first forward-only
schema migration (v1->v2) that links every transaction to an account. The
repository/service/migration layers are tested headless; the accounts-manager
and picker round-trips (INV-7) use the pytest-qt `qtbot` fixture. Every on-disk
vault uses `tmp_path`; no test touches the network or real financial data
(testing.md § 6).
"""

import logging
from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlcipher3 import dbapi2
from sqlcipher3.dbapi2 import IntegrityError

from conftest import _PW, _params, build_v1_vault, raising_conn
from finbreak.crypto import SALT_LEN, derive_key
from finbreak.errors import (
    AccountInUseError,
    LastAccountError,
    SchemaVersionError,
)
from finbreak.migrations import (
    DEFAULT_ACCOUNT_NAME,
    LATEST_SCHEMA_VERSION,
    run_migrations,
)
from finbreak.models import AccountType
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _default_id(vault) -> int:
    """Resolve the seeded Default account's id by NAME (not list position)."""
    accounts = AccountRepository(vault.connection).list_all()
    return next(a.id for a in accounts if a.name == DEFAULT_ACCOUNT_NAME)


# --------------------------------------------------------------------------- #
# INV-1 — account model & CRUD round-trip
# --------------------------------------------------------------------------- #
def test_INV1_crud_roundtrip_and_order(service):
    svc = AccountService(service.vault)
    # The Default account already exists (seeded by migration).
    savings = svc.add_account("Savings", "savings")
    current = svc.add_account("cheque", "current")

    names = [a.name for a in svc.list_accounts()]
    assert names == ["cheque", "Default", "Savings"], "ordered by name, ci"

    repo = AccountRepository(service.vault.connection)
    got = repo.get(savings.id)
    assert got is not None and got.name == "Savings" and got.type == "savings"
    # created_at is a well-formed ISO-8601 timestamp (fromisoformat raises if not).
    datetime.fromisoformat(got.created_at)

    svc.update_account(current.id, "Cheque", "current")
    assert repo.get(current.id).name == "Cheque"

    repo.delete(current.id)
    assert repo.get(current.id) is None


def test_INV1_missing_id_update_and_delete_are_noops(service):
    repo = AccountRepository(service.vault.connection)
    repo.delete(999_999)  # no row, no raise
    repo.update(999_999, "ghost", "other")  # no row, no raise
    assert repo.get(999_999) is None


# --------------------------------------------------------------------------- #
# INV-2 — closed, non-translated type set
# --------------------------------------------------------------------------- #
def test_INV2_all_seven_types_store_verbatim(service):
    svc = AccountService(service.vault)
    tokens = [t.value for t in AccountType]
    assert tokens == [
        "current",
        "savings",
        "credit_card",
        "personal_loan",
        "home_loan",
        "investment",
        "other",
    ]
    for i, token in enumerate(tokens):
        acct = svc.add_account(f"acct{i}", token)
        assert acct.type == token, "the token is stored verbatim"


def test_INV2_unknown_type_rejected(service):
    svc = AccountService(service.vault)
    with pytest.raises(ValueError):
        svc.add_account("bad", "crypto_wallet")
    with pytest.raises(ValueError):
        svc.add_account("bad2", "Current")  # label-cased, not the token


# --------------------------------------------------------------------------- #
# INV-3 — name validation & uniqueness
# --------------------------------------------------------------------------- #
def test_INV3_rejects_empty_and_duplicate_names(service):
    svc = AccountService(service.vault)
    with pytest.raises(ValueError):
        svc.add_account("   ", "current")
    with pytest.raises(ValueError):
        svc.add_account("", "current")
    # "Default" already exists — a case-insensitive duplicate is refused.
    with pytest.raises(ValueError):
        svc.add_account("default", "current")


def test_INV3_name_stored_trimmed_and_update_allows_own_name(service):
    svc = AccountService(service.vault)
    acct = svc.add_account("  Savings  ", "savings")
    assert acct.name == "Savings", "stored trimmed"
    # Re-saving the same account with its own (unchanged) name is allowed.
    svc.update_account(acct.id, "Savings", "current")
    # But colliding with a *different* account's name is refused.
    with pytest.raises(ValueError):
        svc.update_account(acct.id, "Default", "current")


# --------------------------------------------------------------------------- #
# INV-4 — v1->v2 migration: forward-only, atomic, idempotent, backfill
# --------------------------------------------------------------------------- #
def test_INV4_v1_vault_upgrades_and_backfills(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v1_vault(
        vault_path,
        sidecar_path,
        salt,
        [("2026-01-01", -100, "a"), ("2026-02-01", 200, "b")],
    )

    svc = AuthService(vault_path, sidecar_path)
    assert svc.unlock(bytearray(_PW)) is True  # unlock runs the migration
    conn = svc.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8

    accounts = AccountRepository(conn).list_all()
    assert [a.name for a in accounts] == [DEFAULT_ACCOUNT_NAME]
    default_id = accounts[0].id

    txs = TransactionRepository(conn).list_all()
    assert len(txs) == 2, "every prior row is preserved"
    assert all(t.account_id == default_id for t in txs), "backfilled to Default"
    assert {(t.amount_minor, t.description) for t in txs} == {(-100, "a"), (200, "b")}
    svc.lock()


def test_INV4_first_run_vault_is_v8_with_one_default(service):
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
    accounts = AccountRepository(conn).list_all()
    assert [a.name for a in accounts] == [DEFAULT_ACCOUNT_NAME]
    assert accounts[0].type == "current"


def test_INV4_idempotent_at_latest(service):
    # Re-running migrations on an already-latest vault changes nothing.
    conn = service.vault.connection
    run_migrations(conn)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
    assert len(AccountRepository(conn).list_all()) == 1, "Default not duplicated"


def test_INV4_rolls_back_on_failure(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    rows = [("2026-01-01", -100, "a"), ("2026-02-01", 200, "b")]
    build_v1_vault(vault_path, sidecar_path, salt, rows)

    key = derive_key(bytearray(_PW), salt, _params(salt))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")

    with pytest.raises(RuntimeError):
        run_migrations(raising_conn(conn, "RENAME", "injected failure at RENAME"))

    # Prove the ROLLBACK, not just recoverability: on the SAME connection —
    # before any reopen re-runs the migration — the failed v1->v2 step must have
    # left no trace. Still v1, the accounts table never created, and the original
    # transactions table + rows intact (the DROP was undone). A silent
    # no-rollback (DDL autocommit — the Cold-eyes Loop-2 CRITICAL) would surface
    # here as a half-migrated wreck.
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 1
    assert (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
        ).fetchone()
        is None
    ), "the accounts table's CREATE was rolled back"
    surviving = conn.execute(
        "SELECT amount_minor, description FROM transactions"
    ).fetchall()
    assert {tuple(r) for r in surviving} == {(-100, "a"), (200, "b")}, (
        "the original account-less rows survive; the DROP was undone"
    )
    conn.close()

    # And, having rolled back cleanly, the vault is still openable — a
    # subsequent unlock re-runs and completes the migration to v2 with the rows
    # carried through.
    svc = AuthService(vault_path, sidecar_path)
    assert svc.unlock(bytearray(_PW)) is True
    reopened = svc.vault.connection
    txs = TransactionRepository(reopened).list_all()
    assert {(t.amount_minor, t.description) for t in txs} == {(-100, "a"), (200, "b")}
    svc.lock()


def test_INV4_refuses_newer_than_latest(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v1_vault(vault_path, sidecar_path, salt, [])
    key = derive_key(bytearray(_PW), salt, _params(salt))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")
    conn.execute("UPDATE schema_version SET version = ?", (LATEST_SCHEMA_VERSION + 1,))
    conn.commit()
    with pytest.raises(SchemaVersionError):
        run_migrations(conn)
    conn.close()


def test_INV4_unlock_of_newer_vault_raises_and_retains_no_key(paths):
    # Opening a newer-than-supported vault must PROPAGATE SchemaVersionError
    # (not report a wrong-password False) and leave no derived key on the
    # service — the migration runner's refusal wipes and re-raises (INV-3/INV-4).
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v1_vault(vault_path, sidecar_path, salt, [])
    key = derive_key(bytearray(_PW), salt, _params(salt))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")
    conn.execute("UPDATE schema_version SET version = ?", (LATEST_SCHEMA_VERSION + 1,))
    conn.commit()
    conn.close()

    svc = AuthService(vault_path, sidecar_path)
    with pytest.raises(SchemaVersionError):
        svc.unlock(bytearray(_PW))
    assert svc._key is None, "no derived key retained after a refused open"


# --------------------------------------------------------------------------- #
# INV-5 — every transaction belongs to an account
# --------------------------------------------------------------------------- #
def test_INV5_transaction_carries_account_and_name(service):
    default_id = _default_id(service.vault)
    txs = TransactionService(service.vault)
    txs.add_transaction(default_id, "2026-07-01", "-12.34", "coffee")

    rows = txs.list_transactions()
    assert len(rows) == 1
    transaction, display, account_name, _category = rows[0]
    assert transaction.account_id == default_id
    assert account_name == DEFAULT_ACCOUNT_NAME, "the id->name join is correct"


def test_INV5_insert_against_missing_account_raises_integrity_error(service):
    repo = TransactionRepository(service.vault.connection)
    with pytest.raises(IntegrityError):
        repo.add(999_999, "2026-07-01", -1234, "orphan")


def test_INV5_account_id_and_row_id_are_independent(service):
    # A transposition of id/account_id would compile; arrange the two to differ
    # (a second account) so the columns are provably distinct.
    svc = AccountService(service.vault)
    savings = svc.add_account("Savings", "savings")
    txs = TransactionService(service.vault)
    txs.add_transaction(savings.id, "2026-07-01", "-5.00", "under savings")
    transaction, _display, name, _category = txs.list_transactions()[0]
    assert transaction.account_id == savings.id
    assert transaction.id != transaction.account_id, "id and account_id are distinct"
    assert name == "Savings"


# --------------------------------------------------------------------------- #
# INV-6 — delete guard (block-in-use + keep >= 1)
# --------------------------------------------------------------------------- #
def test_INV6_delete_in_use_account_is_blocked(service):
    default_id = _default_id(service.vault)
    TransactionService(service.vault).add_transaction(
        default_id, "2026-07-01", "-1.00", "x"
    )
    # add a second account so "in use", not "last", is what fires
    svc = AccountService(service.vault)
    svc.add_account("Spare", "other")
    with pytest.raises(AccountInUseError):
        svc.delete_account(default_id)
    assert any(a.id == default_id for a in svc.list_accounts()), "nothing removed"


def test_INV6_cannot_delete_last_account(service):
    svc = AccountService(service.vault)
    default_id = _default_id(service.vault)
    with pytest.raises(LastAccountError):
        svc.delete_account(default_id)  # the only account, even though empty


def test_INV6_delete_empty_nonlast_succeeds(service):
    svc = AccountService(service.vault)
    spare = svc.add_account("Spare", "other")
    svc.delete_account(spare.id)
    assert all(a.id != spare.id for a in svc.list_accounts())


def test_INV6_delete_missing_id_falls_through(service):
    svc = AccountService(service.vault)
    svc.add_account("Spare", "other")  # so the target isn't "the last account"
    before = len(svc.list_accounts())
    svc.delete_account(999_999)  # missing id: neither guard fires, no-op
    assert len(svc.list_accounts()) == before


# --------------------------------------------------------------------------- #
# INV-7 — accounts-manager UI round-trip (qtbot)
# --------------------------------------------------------------------------- #
def test_INV7a_type_picker_offers_seven_mapped_types(qtbot, service):
    from finbreak.ui.accounts import AccountsWidget

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    combo = widget._type
    assert combo.count() == 7
    tokens = {combo.itemData(i) for i in range(combo.count())}
    assert tokens == {t.value for t in AccountType}, "each label maps to a token"


def test_INV7bc_add_appears_in_list_and_main_picker(qtbot, service):
    # Re-homed FIBR-0051: the transaction account picker moved from MainWindow
    # into ManualEntryDialog (D3), so the "selectable in the picker" assertion
    # re-points there.
    from finbreak.ui.accounts import AccountsWidget
    from finbreak.ui.manual_entry import ManualEntryDialog

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._name.setText("Holiday")
    widget._type.setCurrentIndex(widget._type.findData("savings"))
    widget._add_button.click()
    listed = [widget._list.item(i).text() for i in range(widget._list.count())]
    assert any("Holiday" in text for text in listed), "added account shows in the list"

    dialog = ManualEntryDialog(service)
    qtbot.addWidget(dialog)
    picker_names = [dialog._account.itemText(i) for i in range(dialog._account.count())]
    assert any("Holiday" in n for n in picker_names), "selectable in the tx picker"


def test_INV7c_transaction_shows_account_name_in_table(qtbot, service):
    # Re-homed FIBR-0051 into HomeView, then relocated to the Transactions tab when
    # Home became the dashboard (FIBR-0012 D7).
    from finbreak.ui.transactions import TransactionsView

    default_id = _default_id(service.vault)
    TransactionService(service.vault).add_transaction(
        default_id, "2026-07-01", "-12.34", "coffee"
    )
    view = TransactionsView(
        TransactionService(service.vault), CategorizationService(service.vault)
    )
    qtbot.addWidget(view)
    assert view._table.rowCount() == 1
    cells = [view._table.item(0, c).text() for c in range(view._table.columnCount())]
    assert any(DEFAULT_ACCOUNT_NAME in c for c in cells), "the account name is shown"


def test_INV7d_delete_in_use_shows_message_and_removes_nothing(
    qtbot, service, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.accounts import AccountsWidget

    monkeypatch.setattr(  # H-E: delete now confirms first — auto-confirm here
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    default_id = _default_id(service.vault)
    TransactionService(service.vault).add_transaction(
        default_id, "2026-07-01", "-1.00", "x"
    )
    svc = AccountService(service.vault)
    svc.add_account("Spare", "other")  # so it's in-use, not last

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(default_id)
    widget._delete_button.click()
    assert "still has transactions" in widget._error.text(), (
        "an in-use delete shows the specific 'still has transactions' message"
    )
    assert any(a.id == default_id for a in svc.list_accounts()), "nothing removed"


def test_INV7e_delete_empty_nonlast_removes_from_list(qtbot, service, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.accounts import AccountsWidget

    monkeypatch.setattr(  # H-E: auto-confirm the delete
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    svc = AccountService(service.vault)
    spare = svc.add_account("Spare", "other")
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(spare.id)
    widget._delete_button.click()
    listed = [widget._list.item(i).text() for i in range(widget._list.count())]
    assert not any("Spare" in text for text in listed), "empty non-last account gone"


def test_delete_confirmation_no_keeps_the_account(qtbot, service, monkeypatch):
    """Declining the delete confirmation removes nothing — the confirm actually
    gates the destructive action. (indie-review H-E)"""
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.accounts import AccountsWidget

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    svc = AccountService(service.vault)
    spare = svc.add_account("Spare", "other")
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(spare.id)
    widget._delete_button.click()
    assert any(a.id == spare.id for a in svc.list_accounts()), (
        "declining the confirm keeps the account"
    )


def test_add_fields_have_accessible_names(qtbot, service):
    """The name field + type combo carry accessible names for screen readers,
    not just a vanishing placeholder. (indie-review M-dlg3)"""
    from finbreak.ui.accounts import AccountsWidget

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    assert widget._name.accessibleName() != ""
    assert widget._type.accessibleName() != ""


def test_INV7f_edit_selected_account_updates_it(qtbot, service):
    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    spare = svc.add_account("Spair", "other")  # a typo to correct via the form

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    # Selecting loads the account into the form; correct the name + type and
    # press Update selected — the account changes in place (INV-7 add/edit form).
    widget._select_account(spare.id)
    widget._name.setText("Spare")
    widget._type.setCurrentIndex(widget._type.findData("savings"))
    widget._update_button.click()

    assert widget._error.text() == "", "a valid edit shows no error"
    listed = [widget._list.item(i).text() for i in range(widget._list.count())]
    assert any("Spare — " in text for text in listed), "the rename shows in the list"
    assert not any("Spair" in text for text in listed), "the old name is gone"
    edited = next(a for a in svc.list_accounts() if a.id == spare.id)
    assert edited.name == "Spare" and edited.type == "savings"


# --------------------------------------------------------------------------- #
# INV-8 — no secret logged across an account add->delete cycle
# --------------------------------------------------------------------------- #
def test_INV8_account_cycle_logs_no_secret(service, caplog):
    password = _PW.decode()
    with caplog.at_level(logging.INFO, logger="finbreak"):
        svc = AccountService(service.vault)
        spare = svc.add_account("Spare", "other")
        svc.update_account(spare.id, "Spare2", "savings")
        svc.delete_account(spare.id)

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert password not in joined, "the master password must never be logged"
    params = service.load_params()
    key = derive_key(bytearray(_PW), params.salt, params)
    assert bytes(key).hex() not in joined, "the derived key (hex) must never be logged"


def test_delete_account_with_statement_but_no_txns_is_blocked(service):
    """An account with a recorded statement period but ZERO transactions (a
    quiet-month / all-duplicate import) is blocked with AccountInUseError, not a
    raw IntegrityError FK crash. (indie-review data H-1)"""
    from finbreak.repositories.statement_periods import StatementPeriodRepository

    svc = AccountService(service.vault)
    spare = svc.add_account("Spare", "other")
    conn = service.vault.connection
    conn.execute("BEGIN")
    StatementPeriodRepository(conn).add(spare.id, "2026-01-01", "2026-01-31", "s.pdf")
    conn.commit()

    with pytest.raises(AccountInUseError):
        svc.delete_account(spare.id)
    assert any(a.id == spare.id for a in svc.list_accounts()), "nothing removed"


def test_add_account_swallows_vault_locked_silently(qtbot, service, monkeypatch):
    """An auto-lock mid-add returns silently, not a raw 'the vault is locked'
    label — parity with the delete handler. (indie-review UI-dialogs M1)"""
    from finbreak.errors import VaultLockedError
    from finbreak.ui.accounts import AccountsWidget

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._name.setText("New")

    def locked(*a, **k):
        raise VaultLockedError("the vault is locked")

    monkeypatch.setattr(widget._accounts, "add_account", locked)
    widget._on_add()  # must not raise
    assert widget._error.text() == "", "VaultLockedError is swallowed silently"


def test_manual_entry_add_swallows_vault_locked_silently(qtbot, service, monkeypatch):
    """An auto-lock while Manual entry is open must not crash Add. (UI-dialogs H2)"""
    from finbreak.errors import VaultLockedError
    from finbreak.ui.manual_entry import ManualEntryDialog

    dialog = ManualEntryDialog(service)
    qtbot.addWidget(dialog)
    dialog._amount.setText("-1.00")
    dialog._description.setText("x")
    committed = []
    dialog.committed.connect(lambda: committed.append(True))

    def locked(*a, **k):
        raise VaultLockedError("the vault is locked")

    monkeypatch.setattr(dialog._transactions, "add_transaction", locked)
    dialog._on_add()  # must not raise
    assert committed == [] and dialog._error.text() == ""


# --------------------------------------------------------------------------- #
# FIBR-0128 — forget remembered statement passwords (Accounts screen)
# --------------------------------------------------------------------------- #
_SENTINEL_PW = "SENTINEL-PW-123"
_PW_MARKER_PHRASE = "statement password saved"


def test_INV1_repo_ids_with_pdf_password_presence_only(service):
    """The repo exposes WHICH accounts have a saved password as an id-set, never
    the secret; empty by default (FIBR-0128 INV-1)."""
    repo = AccountRepository(service.vault.connection)
    default_id = _default_id(service.vault)
    assert repo.ids_with_pdf_password() == set(), "empty by default"
    repo.set_pdf_password(default_id, _SENTINEL_PW)
    assert repo.ids_with_pdf_password() == {default_id}


def test_INV1_service_presence_is_ids_only_and_empty_default(service):
    """account_ids_with_pdf_password returns the id-set and set() when none —
    the plaintext never leaves the service layer (FIBR-0128 INV-1)."""
    svc = AccountService(service.vault)
    assert svc.account_ids_with_pdf_password() == set()
    default_id = _default_id(service.vault)
    svc.set_pdf_password(default_id, _SENTINEL_PW)
    assert svc.account_ids_with_pdf_password() == {default_id}


def test_INV1_widget_never_renders_or_reads_the_secret(qtbot, service, monkeypatch):
    """The saved password never crosses into the UI: the widget never calls
    get_pdf_password during render, and the sentinel is in no row text/tooltip/
    item-data (FIBR-0128 INV-1)."""
    from PySide6.QtCore import Qt

    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    default_id = _default_id(service.vault)
    svc.set_pdf_password(default_id, _SENTINEL_PW)

    # Primary falsifier (a): the listing path must not read the plaintext — spy at
    # the CLASS level BEFORE constructing, so the construction-time _refresh (the
    # shipping render path) is observed too, not just the manual one below.
    calls: list = []
    orig = AccountService.get_pdf_password

    def _spy(self, *a, **k):
        calls.append(a)
        return orig(self, *a, **k)

    monkeypatch.setattr(AccountService, "get_pdf_password", _spy)

    widget = AccountsWidget(service)  # __init__ runs _refresh
    qtbot.addWidget(widget)
    widget._refresh()  # and an explicit re-render
    assert calls == [], "the listing path must not read the plaintext password"

    # Primary falsifier (b) + defense-in-depth: the sentinel is nowhere in the UI.
    roles = [
        Qt.ItemDataRole.AccessibleTextRole,
        Qt.ItemDataRole.UserRole,
        Qt.ItemDataRole.UserRole + 1,
        Qt.ItemDataRole.UserRole + 2,
        Qt.ItemDataRole.UserRole + 3,
    ]
    for i in range(widget._list.count()):
        item = widget._list.item(i)
        assert _SENTINEL_PW not in item.text()
        assert _SENTINEL_PW not in (item.toolTip() or "")
        for role in roles:
            assert _SENTINEL_PW != str(item.data(role))


def test_INV2_marker_flags_exactly_accounts_with_a_saved_password(qtbot, service):
    """The marker shows only for accounts with a saved password (FIBR-0128 INV-2)."""
    from PySide6.QtCore import Qt

    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    default_id = _default_id(service.vault)
    spare = svc.add_account("Spare", "other")
    svc.set_pdf_password(default_id, _SENTINEL_PW)  # only default has one

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)

    marked = {
        widget._list.item(i).data(Qt.ItemDataRole.UserRole): (
            _PW_MARKER_PHRASE in widget._list.item(i).text()
        )
        for i in range(widget._list.count())
    }
    assert marked[default_id] is True, "the account with a saved password is marked"
    assert marked[spare.id] is False, "the account without one is not marked"


def test_INV3_forget_enabled_only_for_saved_password(qtbot, service, monkeypatch):
    """Forget is disabled with no selection / no saved password, enabled only for a
    selected account that has one, and disabled again after a Forget clears the
    selection (FIBR-0128 INV-3)."""
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    default_id = _default_id(service.vault)
    spare = svc.add_account("Spare", "other")
    svc.set_pdf_password(spare.id, _SENTINEL_PW)

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    assert not widget._forget_pw_button.isEnabled(), "starts disabled (no selection)"

    widget._select_account(default_id)  # no saved password
    assert not widget._forget_pw_button.isEnabled(), "no saved password -> disabled"

    widget._select_account(spare.id)  # has one
    assert widget._forget_pw_button.isEnabled(), "saved password -> enabled"

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    widget._forget_pw_button.click()
    assert not widget._forget_pw_button.isEnabled(), "disabled again after Forget"


def test_INV4_forget_clears_only_selected_when_confirmed(qtbot, service, monkeypatch):
    """Confirming Forget clears only the selected account's password; the marker
    drops; other accounts are untouched (FIBR-0128 INV-4)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    a = _default_id(service.vault)
    b = svc.add_account("Spare", "other").id
    svc.set_pdf_password(a, "PW-A")
    svc.set_pdf_password(b, "PW-B")

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **k: QMessageBox.StandardButton.Yes
    )
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(a)
    widget._forget_pw_button.click()

    assert svc.get_pdf_password(a) is None, "the selected account's password is cleared"
    assert svc.get_pdf_password(b) == "PW-B", "other account's password untouched"
    marks = {
        widget._list.item(i).data(Qt.ItemDataRole.UserRole): (
            _PW_MARKER_PHRASE in widget._list.item(i).text()
        )
        for i in range(widget._list.count())
    }
    assert marks[a] is False and marks[b] is True, "only cleared row loses its marker"


def test_INV4_forget_declined_keeps_the_password(qtbot, service, monkeypatch):
    """Declining the Forget confirm leaves the password stored (FIBR-0128 INV-4)."""
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    a = _default_id(service.vault)
    svc.set_pdf_password(a, "PW-A")

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **k: QMessageBox.StandardButton.No
    )
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(a)
    widget._forget_pw_button.click()
    assert svc.get_pdf_password(a) == "PW-A", "declining the confirm keeps the password"
    marked = any(
        _PW_MARKER_PHRASE in widget._list.item(i).text()
        for i in range(widget._list.count())
    )
    assert marked, "declining leaves the marker in place"


def test_INV5_forget_swallows_vault_locked_silently(qtbot, service, monkeypatch):
    """An auto-lock during the clear returns silently, not a raw error label —
    parity with the add/delete handlers (FIBR-0128 INV-5)."""
    from PySide6.QtWidgets import QMessageBox

    from finbreak.errors import VaultLockedError
    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    a = _default_id(service.vault)
    svc.set_pdf_password(a, "PW-A")

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(a)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **k: QMessageBox.StandardButton.Yes
    )

    def locked(*a, **k):
        raise VaultLockedError("the vault is locked")

    monkeypatch.setattr(widget._accounts, "set_pdf_password", locked)
    widget._on_forget_password()  # must not raise
    assert widget._error.text() == "", "VaultLockedError is swallowed silently"
