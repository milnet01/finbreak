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
# FIBR-0113 table helpers — shared by the re-pointed FIBR-0005 / FIBR-0128 legs
# and by the FIBR-0113 block at the foot of this file.
# --------------------------------------------------------------------------- #
_COL_NAME, _COL_TYPE, _COL_NUMBER, _COL_NOTE, _COL_STATUS = range(5)


def _names(widget) -> list[str]:
    """Every row's Name cell, in current visual order."""
    return [
        widget._table.item(row, _COL_NAME).text()
        for row in range(widget._table.rowCount())
    ]


def _row_of(widget, name: str) -> int:
    """The visual row whose Name cell is `name`. A lookup by cell, never by a
    fixed index: a fill under an active sort puts a row at no predictable one."""
    for row in range(widget._table.rowCount()):
        item = widget._table.item(row, _COL_NAME)
        if item is not None and item.text() == name:
            return row
    raise AssertionError(f"no account row named {name!r} in {_names(widget)}")


def _cell(widget, name: str, column: int) -> str:
    """The text of `name`'s row in `column`."""
    item = widget._table.item(_row_of(widget, name), column)
    return "" if item is None else item.text()


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

    svc.update_account(current.id, "Cheque", "current", account_number=None, note=None)
    assert repo.get(current.id).name == "Cheque"

    repo.delete(current.id)
    assert repo.get(current.id) is None


def test_INV1_missing_id_update_and_delete_are_noops(service):
    repo = AccountRepository(service.vault.connection)
    repo.delete(999_999)  # no row, no raise
    repo.update(999_999, "ghost", "other", None, None)  # no row, no raise
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
    svc.update_account(acct.id, "Savings", "current", account_number=None, note=None)
    # But colliding with a *different* account's name is refused.
    with pytest.raises(ValueError):
        svc.update_account(
            acct.id, "Default", "current", account_number=None, note=None
        )


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
    assert (
        conn.execute("SELECT version FROM schema_version").fetchone()[0]
        == LATEST_SCHEMA_VERSION
    )

    accounts = AccountRepository(conn).list_all()
    assert [a.name for a in accounts] == [DEFAULT_ACCOUNT_NAME]
    default_id = accounts[0].id

    txs = TransactionRepository(conn).list_all()
    assert len(txs) == 2, "every prior row is preserved"
    assert all(t.account_id == default_id for t in txs), "backfilled to Default"
    assert {(t.amount_minor, t.description) for t in txs} == {(-100, "a"), (200, "b")}
    svc.lock()


def test_INV4_first_run_vault_is_v9_with_one_default(service):
    conn = service.vault.connection
    assert (
        conn.execute("SELECT version FROM schema_version").fetchone()[0]
        == LATEST_SCHEMA_VERSION
    )
    accounts = AccountRepository(conn).list_all()
    assert [a.name for a in accounts] == [DEFAULT_ACCOUNT_NAME]
    assert accounts[0].type == "current"


def test_INV4_idempotent_at_latest(service):
    # Re-running migrations on an already-latest vault changes nothing.
    conn = service.vault.connection
    run_migrations(conn)
    assert (
        conn.execute("SELECT version FROM schema_version").fetchone()[0]
        == LATEST_SCHEMA_VERSION
    )
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
    assert "Holiday" in _names(widget), "the added account shows in the table"

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
    assert "Spare" not in _names(widget), "empty non-last account gone"


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
    assert "Spare" in _names(widget), "the rename shows in the table"
    assert "Spair" not in _names(widget), "the old name is gone"
    assert _cell(widget, "Spare", _COL_TYPE) == "Savings", "and the retype too"
    edited = next(a for a in svc.list_accounts() if a.id == spare.id)
    assert edited.name == "Spare" and edited.type == "savings"


# --------------------------------------------------------------------------- #
# INV-8 — no secret logged across an account add->delete cycle
# --------------------------------------------------------------------------- #
def test_INV8_account_cycle_logs_no_secret(service, caplog):
    password = _PW.decode()
    # Sentinels for the two v13 reference fields (FIBR-0193 § 7): a leaked
    # account number or note would otherwise pass this sweep, which checks only
    # the master password and the derived key. Gives security-model INV-9's
    # wording ("the local log file never records … decrypted data") an
    # observable for these columns instead of leaving it as wording.
    account_number = "SENTINEL-ACCT-NUMBER-9911"
    note = "SENTINEL-NOTE-2277"
    with caplog.at_level(logging.INFO, logger="finbreak"):
        svc = AccountService(service.vault)
        spare = svc.add_account(
            "Spare", "other", account_number=account_number, note=note
        )
        svc.update_account(
            spare.id, "Spare2", "savings", account_number=account_number, note=note
        )
        svc.delete_account(spare.id)

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert password not in joined, "the master password must never be logged"
    assert account_number not in joined, "an account number must never be logged"
    assert note not in joined, "an account note must never be logged"
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
    # RE-DERIVED for the table, not re-pointed (FIBR-0113 § 6). The old literal
    # role list would keep passing while covering far less: `UserRole` / `+1` are
    # re-purposed by _table_state into row mechanics that could never hold a
    # password, `+2`..`+5` are no longer written at all, and a column-0-only
    # sweep would leave the four other cells — the Account-number one included —
    # unswept entirely. Sweep every cell of every column instead.
    roles = [
        Qt.ItemDataRole.AccessibleTextRole,
        Qt.ItemDataRole.UserRole,  # _table_state._ROW_INDEX_ROLE
        Qt.ItemDataRole.UserRole + 1,  # _table_state._SORT_KEY_ROLE
    ]
    assert widget._table.rowCount() > 0, "an empty table sweeps nothing"
    for row in range(widget._table.rowCount()):
        for col in range(widget._table.columnCount()):
            item = widget._table.item(row, col)
            assert item is not None, f"row {row} column {col} has no item to sweep"
            assert _SENTINEL_PW not in item.text()
            assert _SENTINEL_PW not in (item.toolTip() or "")
            for role in roles:
                assert _SENTINEL_PW != str(item.data(role))


def test_INV2_marker_flags_exactly_accounts_with_a_saved_password(qtbot, service):
    """The marker shows only for accounts with a saved password (FIBR-0128 INV-2)."""
    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    default_id = _default_id(service.vault)
    svc.add_account("Spare", "other")  # a second row, with no saved password
    svc.set_pdf_password(default_id, _SENTINEL_PW)  # only default has one

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)

    # Re-derived for the table (FIBR-0113 § 6): rows are located by their Name
    # cell and the marker read from the STATUS cell. Reading UserRole would now
    # return _table_state's row tag, not an account id, and the marker is no
    # longer part of any row-wide string.
    assert _PW_MARKER_PHRASE in _cell(widget, DEFAULT_ACCOUNT_NAME, _COL_STATUS), (
        "the account with a saved password is marked"
    )
    assert _PW_MARKER_PHRASE not in _cell(widget, "Spare", _COL_STATUS), (
        "the account without one is not marked"
    )


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
    # Re-derived for the table (FIBR-0113 § 6), as in INV-2 above.
    assert _PW_MARKER_PHRASE not in _cell(widget, DEFAULT_ACCOUNT_NAME, _COL_STATUS)
    assert _PW_MARKER_PHRASE in _cell(widget, "Spare", _COL_STATUS), (
        "only the cleared row loses its marker"
    )


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
    assert _PW_MARKER_PHRASE in _cell(widget, DEFAULT_ACCOUNT_NAME, _COL_STATUS), (
        "declining leaves the marker in place"
    )


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


# --------------------------------------------------------------------------- #
# FIBR-0193 — the optional account_number / note storage fields (schema v13)
# --------------------------------------------------------------------------- #
_PW_ACCESSORS = {"get_pdf_password", "set_pdf_password", "ids_with_pdf_password"}


def test_INV3_account_number_and_note_round_trip_on_both_read_paths(service):
    """A populated write reads back by FIELD NAME on `get()` AND `list_all()`
    (FIBR-0193 INV-3). Populated, not blank: a blank write can tell neither a
    mis-ordered SELECT from a correct one, nor a widened INSERT from one that
    silently omits both columns."""
    svc = AccountService(service.vault)
    acct = svc.add_account(
        "Holiday", "savings", account_number="62145530078", note="Ann's card"
    )
    assert acct.account_number == "62145530078"
    assert acct.note == "Ann's card"

    repo = AccountRepository(service.vault.connection)
    for label, got in (
        ("get", repo.get(acct.id)),
        ("list_all", next(a for a in repo.list_all() if a.id == acct.id)),
    ):
        assert got is not None, label
        assert got.account_number == "62145530078", label
        assert got.note == "Ann's card", label
        assert got.name == "Holiday" and got.type == "savings", label
        # The falsifier for a column inserted BEFORE created_at in one SELECT
        # (e.g. id, name, type, account_number, created_at, note): the timestamp
        # would land in account_number and this parse would raise.
        datetime.fromisoformat(got.created_at)


def test_INV4_statement_pdf_password_confined_to_its_accessors():
    """Within `repositories/accounts.py`, `statement_pdf_password` is named only
    inside the three dedicated accessors — no listing query in that file selects
    it (FIBR-0193 INV-4, re-asserting FIBR-0128 INV-1 at source level). An AST
    walk, because a substring scan cannot attribute a hit to its enclosing
    function."""
    import ast
    import sys
    from pathlib import Path

    def mentions(node) -> int:
        return sum(
            1
            for n in ast.walk(node)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and "statement_pdf_password" in n.value
        )

    # Located through the imported symbol, not a path relative to this file, so
    # it keeps working if either tree moves.
    module = Path(sys.modules[AccountRepository.__module__].__file__)
    tree = ast.parse(module.read_text(encoding="utf-8"))
    accessors = {
        fn.name: fn
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef) and fn.name in _PW_ACCESSORS
    }
    assert set(accessors) == _PW_ACCESSORS, "the three dedicated accessors still exist"

    inside = sum(mentions(fn) for fn in accessors.values())
    assert inside > 0, "the accessors must actually name the column"
    assert mentions(tree) == inside, (
        "the stored statement password is named outside its three accessors — a "
        "listing SELECT would carry every saved password into every account listing"
    )


def test_INV5_blank_account_number_and_note_are_stored_as_null(service):
    """A blank field passed through `add_account` is SQL NULL, not "" — covering
    the strip half and the collapse half separately (FIBR-0193 INV-5)."""
    svc = AccountService(service.vault)
    conn = service.vault.connection

    accounts = [
        svc.add_account("Empty", "other", account_number="", note=""),
        svc.add_account("Whitespace", "other", account_number="   ", note="  \t "),
        svc.add_account("Omitted", "other"),
    ]
    for account in accounts:
        row = conn.execute(
            "SELECT account_number IS NULL, note IS NULL FROM accounts WHERE id = ?",
            (account.id,),
        ).fetchone()
        assert tuple(row) == (1, 1), f"{account.name}: a blank field must be NULL"


def test_INV6_update_persists_account_number_and_note(service):
    """Editing a stored account number writes the new value (FIBR-0193 INV-6 leg
    1) — the only headless guard on `AccountRepository.update`'s SET clause and
    bind tuple. Every value is distinguishable from the others and from
    name/type, so a transposed pair reddens instead of passing."""
    svc = AccountService(service.vault)
    repo = AccountRepository(service.vault.connection)
    acct = svc.add_account(
        "Holiday", "savings", account_number="OLD-1111", note="old note"
    )

    svc.update_account(
        acct.id, "Holiday", "savings", account_number="NEW-2222", note="new note"
    )

    got = repo.get(acct.id)
    assert got is not None
    assert got.account_number == "NEW-2222", "the edited number is persisted"
    assert got.note == "new note", "the edited note is persisted"
    assert got.name == "Holiday" and got.type == "savings", "and nothing transposed"


def test_INV6_update_blanks_clear_both_fields_to_null(service):
    """Clearing a filled field to blank writes SQL NULL back over it — the
    catcher for `update_account` skipping `_normalise_optional` (INV-6 leg 2,
    which is also INV-5's both-paths falsifier)."""
    svc = AccountService(service.vault)
    conn = service.vault.connection
    acct = svc.add_account(
        "Holiday", "savings", account_number="62145530078", note="Ann's card"
    )

    svc.update_account(acct.id, "Holiday", "savings", account_number="   ", note="   ")

    row = conn.execute(
        "SELECT account_number IS NULL, note IS NULL FROM accounts WHERE id = ?",
        (acct.id,),
    ).fetchone()
    assert tuple(row) == (1, 1), "a cleared field is stored as NULL, not ''"


def test_INV7_on_update_passes_stored_account_number_and_note_through(qtbot, service):
    """An Update that edits only the name leaves both stored fields intact
    (FIBR-0193 INV-7). The seeds are mutually distinguishable AND already
    normalised — no outer whitespace: this leg is the only catcher for
    `_normalise_optional`'s idempotency, so a " 1234 " seed would be stored as
    "1234" and turn the leg red against a CORRECT build."""
    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    spare = svc.add_account(
        "Spair", "other", account_number="ACCT-4021-7788", note="joint, second card"
    )

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(spare.id)
    widget._name.setText("Spare")  # edit ONLY the name
    widget._update_button.click()

    assert widget._error.text() == "", "a valid edit shows no error"
    edited = next(a for a in svc.list_accounts() if a.id == spare.id)
    assert edited.name == "Spare", "the rename itself landed"
    assert edited.account_number == "ACCT-4021-7788", "the stored number survived"
    assert edited.note == "joint, second card", "the stored note survived"


# --------------------------------------------------------------------------- #
# FIBR-0113 — the sortable 5-column Accounts table, account number masked
# --------------------------------------------------------------------------- #
# The shared "sorted setup" (spec § 5): EXACTLY three accounts, each with a
# distinct name, type, account number AND note, viewed under a DESCENDING Name
# sort. `AccountRepository.list_all()` ends `ORDER BY name COLLATE NOCASE, id`,
# so `self._rows` is always name-ASCENDING — the descending sort is what makes
# every visual position differ from its index. The distinct types / numbers /
# notes are load-bearing: without them two accounts render identical cells in
# three of the five columns and INV-18's row-wise pairing check silently
# degrades to a Name-and-Status check.
_SORTED_ACCOUNTS = [
    # name,   type,          label,         account number, note
    ("Alpha", "savings", "Savings", "1111222233", "alpha note"),
    ("Mid", "current", "Current", "4444555566", "mid note"),
    ("Zed", "credit_card", "Credit card", "7777888899", "zed note"),
]


def _seed_sorted(service) -> dict[str, int]:
    """Build the sorted setup's three accounts; return {name: id}. The seeded
    Default is renamed into the set rather than left beside it, so the table
    holds exactly three rows."""
    svc = AccountService(service.vault)
    ids = {}
    for i, (name, type_, _label, number, note) in enumerate(_SORTED_ACCOUNTS):
        if i == 1:  # reuse the seeded Default as the middle account
            account_id = _default_id(service.vault)
            svc.update_account(
                account_id, name, type_, account_number=number, note=note
            )
        else:
            account_id = svc.add_account(
                name, type_, account_number=number, note=note
            ).id
        ids[name] = account_id
    return ids


def _sort_desc_by_name(widget) -> None:
    from PySide6.QtCore import Qt

    widget._table.sortItems(_COL_NAME, Qt.SortOrder.DescendingOrder)


def _statement(service, account_id, start, end, name, closing) -> None:
    from finbreak.repositories.statement_periods import StatementPeriodRepository

    StatementPeriodRepository(service.vault.connection).add(
        account_id, start, end, name, closing
    )
    service.vault.connection.commit()


# -- INV-5 — the mask helper ------------------------------------------------ #
def test_INV5_mask_account_number_shows_at_most_the_last_four():
    """A mask plus the last 4 for a value longer than 4; a BARE mask for 1-4
    characters (its "last 4" would be all of it); an empty cell for no number
    (FIBR-0113 INV-5)."""
    from finbreak.ui.accounts import _mask_account_number

    assert _mask_account_number("1234567890") == "•••• 7890"
    assert _mask_account_number("12345") == "•••• 2345", "the shortest last-4 value"
    assert _mask_account_number("1234") == "••••", "no digits leak at exactly 4"
    assert _mask_account_number("123") == "••••", "nor below it"
    assert _mask_account_number("") == ""
    assert _mask_account_number(None) == ""


# -- INV-7 — handlers act on the SELECTED account, not the visual row ------- #
def test_INV7_handlers_act_on_the_selected_account_under_a_sort(
    qtbot, service, monkeypatch
):
    """Update, Delete and Forget all act on the account the user selected, not
    on the parallel-list entry sitting at that visual row index (FIBR-0113
    INV-7). This is the money-adjacent one: it deletes the wrong account."""
    from PySide6.QtWidgets import QMessageBox

    from finbreak.ui.accounts import AccountsWidget

    monkeypatch.setattr(  # both Delete and Forget block on a confirm
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    svc = AccountService(service.vault)
    ids = _seed_sorted(service)
    # Two accounts carry a saved statement password; the THIRD is the Delete
    # target. Aiming all three drives at one account would delete it, and the
    # next _select_account would miss — red against a correct implementation.
    svc.set_pdf_password(ids["Alpha"], "PW-ALPHA")
    svc.set_pdf_password(ids["Zed"], "PW-ZED")

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    _sort_desc_by_name(widget)

    # (1) Update lands on Alpha. Each drive re-selects by id first: every handler
    # ends in _refresh(), which leaves no selection (INV-22), so handlers 2 and 3
    # would otherwise take their no-selection early return and do nothing.
    widget._select_account(ids["Alpha"])
    widget._name.setText("Alpha renamed")  # selection pre-populated the old name
    widget._update_button.click()
    by_id = {a.id: a for a in svc.list_accounts()}
    assert by_id[ids["Alpha"]].name == "Alpha renamed", "Update hit the selected one"
    assert by_id[ids["Mid"]].name == "Mid", "and no other"
    assert by_id[ids["Zed"]].name == "Zed"

    # (2) Delete lands on Mid.
    widget._select_account(ids["Mid"])
    widget._delete_button.click()
    remaining = {a.id for a in svc.list_accounts()}
    assert ids["Mid"] not in remaining, "Delete removed the selected account"
    assert remaining == {ids["Alpha"], ids["Zed"]}, "and left the rest"

    # (3) Forget lands on Zed.
    widget._select_account(ids["Zed"])
    widget._forget_pw_button.click()
    assert svc.get_pdf_password(ids["Zed"]) is None, "Forget cleared the selected one"
    assert svc.get_pdf_password(ids["Alpha"]) == "PW-ALPHA", "and left the other"


# -- INV-9 — Status sorts by reconciliation SEVERITY, not by its string ----- #
def test_INV9_status_column_sorts_by_severity_and_composes_its_text(qtbot, service):
    """Ascending: every OFF above every quiet above every RECONCILED. Both quiet
    shapes are required — an empty cell sorts FIRST lexically but BETWEEN by
    rank, and a key-only cell (U+1F511) sorts LAST lexically but MIDDLE
    (FIBR-0113 INV-9)."""
    from PySide6.QtCore import Qt

    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    # OFF — two statements, nothing bridging them.
    off = svc.add_account("AAoff", "current").id
    _statement(service, off, "2026-01-01", "2026-04-30", "apr.pdf", 100_000)
    _statement(service, off, "2026-05-01", "2026-05-31", "may.pdf", 150_000)
    # Quiet with NO marker at all — one statement only (NOT_ENOUGH_DATA).
    quiet = svc.add_account("BBquiet", "savings").id
    _statement(service, quiet, "2026-01-01", "2026-04-30", "s.ofx", 100_000)
    # Quiet with the key marker ONLY.
    quiet_key = svc.add_account("CCquietkey", "savings").id
    _statement(service, quiet_key, "2026-01-01", "2026-04-30", "s2.ofx", 100_000)
    svc.set_pdf_password(quiet_key, "PW-Q")
    # RECONCILED — two statements bridged exactly.
    good = svc.add_account("DDgood", "current").id
    _statement(service, good, "2026-01-01", "2026-04-30", "apr.pdf", 100_000)
    _statement(service, good, "2026-05-01", "2026-05-31", "may.pdf", 150_000)
    TransactionRepository(service.vault.connection).add(
        good, "2026-05-15", 50_000, "bridge"
    )
    # RECONCILED with a key.
    good_key = svc.add_account("EEgoodkey", "current").id
    _statement(service, good_key, "2026-01-01", "2026-04-30", "a.pdf", 100_000)
    _statement(service, good_key, "2026-05-01", "2026-05-31", "b.pdf", 150_000)
    TransactionRepository(service.vault.connection).add(
        good_key, "2026-05-15", 50_000, "bridge"
    )
    svc.set_pdf_password(good_key, "PW-G")
    # The seeded Default has no statements at all — delete it so the five ranks
    # under test are the whole table.
    svc.delete_account(_default_id(service.vault))

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._table.sortItems(_COL_STATUS, Qt.SortOrder.AscendingOrder)

    # Rank GROUPING, not an exact five-name sequence: intra-rank order among the
    # two quiet and the two reconciled rows is unspecified.
    order = _names(widget)
    rank = {
        "AAoff": 0,
        "BBquiet": 1,
        "CCquietkey": 1,
        "DDgood": 2,
        "EEgoodkey": 2,
    }
    ranks = [rank[name] for name in order]
    assert ranks == sorted(ranks), f"severity grouping broken: {order}"
    assert ranks == [0, 1, 1, 2, 2]

    # The composed cell text, by EXACT equality for every marker x key
    # combination — a substring check passes on a cell that still carries the
    # "  ·  " prefix § 4.2 removes from the four tr() literals.
    key_text = "🔑 statement password saved"
    assert _cell(widget, "BBquiet", _COL_STATUS) == ""
    assert _cell(widget, "CCquietkey", _COL_STATUS) == key_text
    assert _cell(widget, "DDgood", _COL_STATUS) == "✓ balances reconcile"
    assert (
        _cell(widget, "EEgoodkey", _COL_STATUS) == f"✓ balances reconcile · {key_text}"
    ), "reconciliation text FIRST, key second — a deliberate reversal of the list"
    off_text = _cell(widget, "AAoff", _COL_STATUS)
    assert off_text.startswith("⚠ off by "), f"no leading separator: {off_text!r}"
    assert "500" in off_text, "the discrepancy magnitude is rendered"


# -- INV-12 — the two new form fields --------------------------------------- #
def test_INV12_form_stores_and_repopulates_account_number_and_note(qtbot, service):
    """Typing an account number and a note and pressing Add stores both and
    clears the form; re-selecting repopulates both with the NORMALISED stored
    value, the number field still masked (FIBR-0113 INV-12)."""
    from PySide6.QtWidgets import QLineEdit

    from finbreak.ui.accounts import AccountsWidget, _mask_account_number

    svc = AccountService(service.vault)
    existing = svc.add_account("Existing", "savings", account_number="9999", note="x")

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    # Leg (d), construction-time half: the field is built in Password echo mode,
    # BEFORE any selection. The only leg that observes that.
    assert widget._account_number.echoMode() == QLineEdit.EchoMode.Password

    # Select an existing row FIRST, so the _refresh() after Add genuinely fires
    # the selection-cleared path rather than starting from no selection (where
    # no itemSelectionChanged is emitted at all).
    widget._select_account(existing.id)
    # A NEW, unused name: _on_add passes _name.text() straight to add_account,
    # which rejects a duplicate and returns BEFORE clearing the form — a leg
    # reusing the selected account's name would fail its own step (a).
    widget._name.setText("Holiday")
    widget._account_number.setText("  1234567890  ")  # outer whitespace -> stripped
    widget._note.setText("  holiday savings  ")
    type_before = widget._type.currentData()
    widget._add_button.click()

    # (a) the post-Add state, which the _refresh() that follows must not undo
    assert widget._name.text() == ""
    assert widget._account_number.text() == ""
    assert widget._note.text() == ""
    assert widget._type.currentData() == type_before, "the Type picker is not cleared"

    # (b) the new row's Note cell carries the normalised value
    assert _cell(widget, "Holiday", _COL_NOTE) == "holiday savings"
    # (c) ...and its Account-number cell the MASKED form, not the typed value
    assert _cell(widget, "Holiday", _COL_NUMBER) == _mask_account_number("1234567890")
    assert "1234567890" not in _cell(widget, "Holiday", _COL_NUMBER)

    # (d) re-selecting repopulates both fields with the normalised stored value,
    # the number field still masked by echo mode
    added = next(a for a in svc.list_accounts() if a.name == "Holiday")
    widget._select_account(added.id)
    assert widget._account_number.text() == "1234567890", "the RAW value, not the mask"
    assert widget._note.text() == "holiday savings"
    assert widget._account_number.echoMode() == QLineEdit.EchoMode.Password
    assert widget._account_number.displayText() != widget._account_number.text(), (
        "the echo character is platform-dependent, so only the difference is pinned"
    )

    # (e) a _refresh() with the selection cleared LEAVES the form untouched. The
    # only leg that falsifies that clause: (a) asserts the fields are empty at a
    # point where _on_add has already cleared them, so a handler that CLEARS the
    # form on a cleared selection passes (a) identically while wiping
    # in-progress input on every tab activation.
    widget._select_account(existing.id)
    widget._name.setText("typed but not saved")
    widget._refresh()
    assert widget._name.text() == "typed but not saved"


# -- INV-15 — _select_account maps id -> position --------------------------- #
def test_INV15_select_account_resolves_the_id_to_a_position(qtbot, service):
    """`_select_account` selects the row displaying that account whatever the
    sort, and selects nothing for an unknown id (FIBR-0113 INV-15)."""
    from finbreak.ui._table_state import selected_index
    from finbreak.ui.accounts import AccountsWidget

    ids = _seed_sorted(service)
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    _sort_desc_by_name(widget)

    # Pick an account whose id differs from its index in self._rows — the seeded
    # Default has id == 1 and can sit at index 1, where an id passed straight
    # through selects the same row and the leg passes green.
    target = "Zed"
    index = next(i for i, a in enumerate(widget._rows) if a.id == ids[target])
    assert ids[target] != index, "the id and the index must differ for this to bite"

    widget._select_account(ids[target])
    assert selected_index(widget._table) == index
    assert _names(widget)[widget._table.currentRow()] == target

    # An absent id leaves the selection UNCHANGED — not cleared (§ 4.2).
    widget._select_account(999_999)
    assert selected_index(widget._table) == index, "an unknown id changes nothing"


# -- INV-18 — a refresh under an active sort never mis-pairs cells ---------- #
def test_INV18_refresh_under_a_sort_never_mispairs_cells(qtbot, service):
    """Every row's five cells belong to the same account after a refresh, in
    both sort directions (FIBR-0113 INV-18). Without `fill_guard` Qt re-sorts on
    each setItem and a row acquires cells from whichever account occupied that
    visual position mid-fill."""
    from PySide6.QtCore import Qt

    from finbreak.ui.accounts import AccountsWidget, _mask_account_number

    _seed_sorted(service)
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)

    expected = {
        name: (label, _mask_account_number(number), note)
        for name, _type, label, number, note in _SORTED_ACCOUNTS
    }
    for order in (Qt.SortOrder.DescendingOrder, Qt.SortOrder.AscendingOrder):
        widget._table.sortItems(_COL_NAME, order)
        widget._refresh()
        assert widget._table.rowCount() == len(_SORTED_ACCOUNTS)
        for row in range(widget._table.rowCount()):
            name = widget._table.item(row, _COL_NAME).text()
            cells = (
                widget._table.item(row, _COL_TYPE).text(),
                widget._table.item(row, _COL_NUMBER).text(),
                widget._table.item(row, _COL_NOTE).text(),
            )
            assert cells == expected[name], f"row {row} ({order}) mixes accounts"


# -- INV-20 — the Account-number COLUMN is always masked -------------------- #
def test_INV20_account_number_column_is_masked_on_every_fill(qtbot, service):
    """The column renders `_mask_account_number(...)` for every row, whatever
    the sort order (FIBR-0113 INV-20). § 3 decision 2's primary surface — INV-5
    covers only the pure helper and INV-12 leg (d) only the form field."""
    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    svc.add_account("WithNumber", "savings", account_number="1234567890")
    svc.add_account("NoNumber", "current")

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    # Rows located by their NAME cell: an empty Account-number cell is otherwise
    # indistinguishable from a mis-filled one.
    assert _cell(widget, "WithNumber", _COL_NUMBER) == "•••• 7890"
    assert _cell(widget, "NoNumber", _COL_NUMBER) == ""

    # ...and again after a _refresh() driven by an Add.
    widget._name.setText("Third")
    widget._add_button.click()
    assert _cell(widget, "WithNumber", _COL_NUMBER) == "•••• 7890"
    assert _cell(widget, "NoNumber", _COL_NUMBER) == ""
    assert _cell(widget, "Third", _COL_NUMBER) == ""


# -- INV-21 — the table is click-sortable ----------------------------------- #
def test_INV21_table_is_click_sortable(qtbot, service):
    """`isSortingEnabled()` is True and driving the header reorders the rows
    (FIBR-0113 INV-21). NOT `sortByColumn` / `sortItems` — those sort whether or
    not sorting was ever enabled, so they pass in the exact broken state."""
    from PySide6.QtCore import Qt

    from finbreak.ui.accounts import AccountsWidget

    _seed_sorted(service)
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    assert widget._table.isSortingEnabled(), "enable_sorting was never called"

    header = widget._table.horizontalHeader()
    header.setSortIndicator(_COL_NAME, Qt.SortOrder.AscendingOrder)
    ascending = _names(widget)
    header.setSortIndicator(_COL_NAME, Qt.SortOrder.DescendingOrder)
    assert _names(widget) == list(reversed(ascending)), "a header click reorders"


# -- INV-22 — a refresh leaves NO selection --------------------------------- #
def test_INV22_refresh_leaves_no_selection_on_any_row(qtbot, service):
    """`_refresh()` leaves the table with no selection whatever sort is active,
    so no stale selection can survive a repopulate and resolve to a DIFFERENT
    account (FIBR-0113 INV-22). Every row is driven, mirroring § 8's
    reproduction."""
    from finbreak.ui._table_state import selected_index
    from finbreak.ui.accounts import AccountsWidget

    _seed_sorted(service)
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    _sort_desc_by_name(widget)
    assert widget._table.rowCount() == len(_SORTED_ACCOUNTS)

    for row in range(widget._table.rowCount()):
        widget._table.selectRow(row)
        assert selected_index(widget._table) is not None, f"row {row} did not select"
        widget._refresh()
        assert selected_index(widget._table) is None, f"row {row} survived the refresh"
        assert widget._table.selectedItems() == []


# --------------------------------------------------------------------------- #
# FIBR-0198 — the "Show account numbers" reveal + its 30s auto re-mask
# --------------------------------------------------------------------------- #
def test_INV1_reveal_is_off_by_default_and_never_persisted(qtbot, service):
    """Reveal starts off, is written to no persistent store, and a lock cycle
    returns it to off (FIBR-0198 INV-1)."""
    from PySide6.QtCore import QSettings

    from finbreak import paths
    from finbreak.ui.accounts import AccountsWidget

    # (a) unchecked on construction
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    assert widget._reveal.isChecked() is False

    # (b) toggling writes nothing to the window INI. Keys are read THROUGH
    # QSettings after sync(), not by parsing the file's bytes: a persisting
    # implementation whose setValue is still buffered would never reach the file
    # during the test. Only `columns/accounts_table` may legitimately change —
    # excluding the whole `columns/` GROUP would let a flag persisted as
    # `columns/accounts_reveal` pass the leg meant to fail on it.
    def _keys() -> set[str]:
        settings = QSettings(
            str(paths.window_settings_path()), QSettings.Format.IniFormat
        )
        settings.sync()
        return set(settings.allKeys())

    before = _keys()
    widget._reveal.setChecked(True)
    widget._reveal.setChecked(False)
    assert (_keys() - before) - {"columns/accounts_table"} == set(), (
        "the reveal state must not be written to the window INI"
    )

    # (c) a lock cycle rebuilds the tab with reveal off. Needs a real
    # MainWindow: what this uniquely catches is `_clear_live` ever being changed
    # to REUSE the Accounts tab rather than rebuild it.
    from finbreak.ui.main_window import MainWindow

    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    assert window._accounts_tab is not None
    window._accounts_tab._reveal.setChecked(True)
    window._lock()
    assert service.unlock(bytearray(_PW)) is True
    window._enter_unlocked()
    assert window._accounts_tab is not None
    assert window._accounts_tab._reveal.isChecked() is False, (
        "a rebuilt Accounts tab starts masked"
    )


def test_INV2_reveal_auto_remasks_and_only_a_fresh_reveal_arms_the_timer(
    qtbot, service
):
    """The reveal lapses on its own; a manual uncheck cancels the pending timer;
    and nothing but a fresh reveal (re)starts it (FIBR-0198 INV-2)."""
    from PySide6.QtWidgets import QLineEdit

    from finbreak.ui.accounts import _REVEAL_SECONDS, AccountsWidget

    svc = AccountService(service.vault)
    svc.add_account("WithNumber", "savings", account_number="1234567890")

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)

    # (b) the timer's configuration, read on a FRESH widget before any reveal —
    # the read moment is part of the assertion, because the precedent's
    # alternative shape (start(seconds * 1000) per use) leaves interval() at 0
    # until the first reveal.
    from PySide6.QtCore import Qt

    assert widget._reveal_timer.isSingleShot() is True
    assert widget._reveal_timer.interval() == _REVEAL_SECONDS * 1000
    # Precise, not Qt's DEFAULT Coarse. A coarse timer shifts its deadline by up
    # to 5% to coalesce wakeups, so the re-mask can land ~1.5s late and
    # remainingTime() reads ABOVE the interval — which made leg (d) below flake
    # (measured 12/25 reads once the event loop has registered the timer). This
    # clause is what stops that returning silently.
    assert widget._reveal_timer.timerType() == Qt.TimerType.PreciseTimer

    # (a) the re-mask actually HAPPENS. Legs (b)-(d) observe the timer's
    # configuration, so they all pass against an implementation that never
    # connects `timeout` — which is why this leg leads.
    widget._reveal.setChecked(True)
    assert _cell(widget, "WithNumber", _COL_NUMBER) == "1234567890"
    widget._reveal_timer.timeout.emit()
    assert widget._reveal.isChecked() is False
    assert widget._account_number.echoMode() == QLineEdit.EchoMode.Password
    assert _cell(widget, "WithNumber", _COL_NUMBER) == "•••• 7890"

    # (c) a manual uncheck cancels the pending timer, so it cannot fire across a
    # later reveal.
    widget._reveal.setChecked(True)
    assert widget._reveal_timer.isActive() is True
    widget._reveal.setChecked(False)
    assert widget._reveal_timer.isActive() is False

    # (d) an unrelated _refresh() neither restarts NOR stops the timer.
    widget._reveal.setChecked(True)
    qtbot.wait(50)  # so a restart is observable as a jump back up
    assert widget._reveal_timer.isActive() is True
    before = widget._reveal_timer.remainingTime()
    assert before < _REVEAL_SECONDS * 1000, "the wait must have consumed some time"

    rows_before = widget._table.rowCount()
    widget._name.setText("A brand new account")  # unused: _on_add returns BEFORE
    widget._add_button.click()  # _refresh() on a rejected name
    assert widget._table.rowCount() == rows_before + 1, "the Add really happened"

    # isActive() is what makes the numeric clauses mean anything: QTimer returns
    # -1 from remainingTime() on an INACTIVE timer, so against an implementation
    # that stops the timer in _refresh() both numbers hold while the reveal
    # never lapses at all.
    assert widget._reveal_timer.isActive() is True, "the reveal must still lapse"
    after = widget._reveal_timer.remainingTime()
    assert after <= before, "a _refresh() must not restart the timer"
    assert after < _REVEAL_SECONDS * 1000


def test_INV3_form_field_echo_mode_follows_the_reveal(qtbot, service):
    """The account-number field is `Password` with reveal off and `Normal` with
    it on, and stays editable in both states (FIBR-0198 INV-3)."""
    from PySide6.QtWidgets import QLineEdit

    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    acct = svc.add_account("WithNumber", "savings", account_number="1234567890")

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(acct.id)

    # Reveal off. A Password field's text() is NEVER masked — asserting on it
    # would fail and invite weakening the leg; displayText() is the masked one.
    assert widget._account_number.echoMode() == QLineEdit.EchoMode.Password
    assert widget._account_number.text() == "1234567890"
    assert widget._account_number.displayText() != "1234567890"

    widget._reveal.setChecked(True)
    assert widget._account_number.echoMode() == QLineEdit.EchoMode.Normal
    assert widget._account_number.displayText() == widget._account_number.text()

    # Editable in BOTH states, and the typed value reaches the service.
    widget._select_account(acct.id)
    widget._account_number.setText("5555666677")
    widget._update_button.click()
    assert next(a for a in svc.list_accounts() if a.id == acct.id).account_number == (
        "5555666677"
    ), "an edit made while revealed is stored"

    widget._reveal.setChecked(False)
    assert widget._account_number.echoMode() == QLineEdit.EchoMode.Password
    # Re-select first: the Update above ended in _refresh(), which leaves no
    # selection (FIBR-0113 INV-22), so _on_update would early-return.
    widget._select_account(acct.id)
    widget._account_number.setText("8888999900")
    widget._update_button.click()
    assert next(a for a in svc.list_accounts() if a.id == acct.id).account_number == (
        "8888999900"
    ), "an edit made while masked is stored too"


def test_INV4_toggling_reveal_preserves_an_in_progress_edit(qtbot, service):
    """Toggling reveal keeps the selection, the four form inputs and the Forget
    button exactly as they were (FIBR-0198 INV-4)."""
    from finbreak.ui._table_state import selected_index
    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    acct = svc.add_account(
        "WithNumber", "savings", account_number="1234567890", note="stored note"
    )
    svc.set_pdf_password(acct.id, _SENTINEL_PW)

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)

    def _typed_state():
        widget._select_account(acct.id)
        assert widget._forget_pw_button.isEnabled(), "the saved password gates it on"
        widget._name.setText("typed name")
        widget._note.setText("typed note")
        return (
            selected_index(widget._table),
            widget._name.text(),
            widget._type.currentData(),
            widget._account_number.text(),
            widget._note.text(),
            widget._forget_pw_button.isEnabled(),
        )

    def _current_state():
        return (
            selected_index(widget._table),
            widget._name.text(),
            widget._type.currentData(),
            widget._account_number.text(),
            widget._note.text(),
            widget._forget_pw_button.isEnabled(),
        )

    # The manual toggle, on and off.
    expected = _typed_state()
    widget._reveal.setChecked(True)
    assert _current_state() == expected, "reveal ON discarded the in-progress edit"
    widget._reveal.setChecked(False)
    assert _current_state() == expected, "reveal OFF discarded the in-progress edit"

    # And the UNATTENDED off-transition — the case that matters, since § 8
    # rejects extending the timer on activity, so the spec has DECIDED a re-mask
    # can land mid-edit.
    expected = _typed_state()
    widget._reveal.setChecked(True)
    widget._name.setText("typed name")  # re-type after the on-toggle's refresh
    widget._note.setText("typed note")
    widget._reveal_timer.timeout.emit()
    assert widget._reveal.isChecked() is False
    assert _current_state() == expected, "an auto re-mask discarded the typing"


def test_INV5_account_number_column_follows_the_reveal(qtbot, service):
    """The column renders the raw value while reveal is on and the mask when it
    goes off, for every row (FIBR-0198 INV-5, narrowing FIBR-0113 INV-20)."""
    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    svc.add_account("WithNumber", "savings", account_number="1234567890")
    svc.add_account("NoNumber", "current")

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    # Rows located by their Name cell throughout: remember_columns restores a
    # saved sort indicator, so positions are not this leg's to assume, and the
    # Add below changes the row set.
    assert _cell(widget, "WithNumber", _COL_NUMBER) == "•••• 7890"
    assert _cell(widget, "NoNumber", _COL_NUMBER) == ""

    widget._reveal.setChecked(True)
    assert _cell(widget, "WithNumber", _COL_NUMBER) == "1234567890"
    assert _cell(widget, "NoNumber", _COL_NUMBER) == "", "a number-less row stays empty"

    # Still revealed, drive a NON-toggle _refresh(). This is the only leg that
    # exercises § 4.2's `self._reveal.isChecked()` requirement: a fill reading
    # the toggle's bool parameter instead would re-mask on every Add, Update,
    # Delete and tab activation while the box stayed ticked.
    rows_before = widget._table.rowCount()
    widget._name.setText("A brand new account")  # unused: _on_add returns BEFORE
    widget._add_button.click()  # _refresh() on a rejected name
    assert widget._table.rowCount() == rows_before + 1, "the Add really happened"
    assert _cell(widget, "WithNumber", _COL_NUMBER) == "1234567890", (
        "a non-toggle refresh must not re-mask while the box is ticked"
    )

    widget._reveal.setChecked(False)
    assert _cell(widget, "WithNumber", _COL_NUMBER) == "•••• 7890"
    assert _cell(widget, "NoNumber", _COL_NUMBER) == ""


# --------------------------------------------------------------------------- #
# FIBR-0204 — Update / Delete must grey out when nothing is selected
# --------------------------------------------------------------------------- #
def test_FIBR0204_update_and_delete_disable_without_a_selection(qtbot, service):
    """A button that stays clickable with nothing selected is a dead button.

    `_refresh()` clears the selection (the table is repopulated inside
    `fill_guard`), but only Forget password was ever gated on the selection —
    Update and Delete were never `setEnabled`-ed at all. So after any refill they
    stayed clickable, and their handlers hit `if account is None: return` and did
    nothing, silently.

    The user-visible shape: rename an account, click Update (works), notice a typo
    in what you just typed. The form still shows the account's details on purpose
    — `_refresh` deliberately leaves the form alone so in-progress typing is not
    wiped — and Update is still enabled. Correct the typo, click Update, and
    nothing happens. No change, no error, no message; the only cue is a row that
    is no longer highlighted, which is easy to miss with a full form in front of
    you. The other four tabs all disable coherently; Accounts was the outlier.
    """
    from finbreak.ui.accounts import AccountsWidget

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    AccountService(service.vault).add_account("Savings", "savings")
    widget._refresh()

    widget._table.selectRow(0)
    assert widget._selected_account() is not None
    assert widget._update_button.isEnabled(), "a selected account can be updated"
    assert widget._delete_button.isEnabled(), "a selected account can be deleted"

    widget._refresh()  # any refresh — a tab switch, a Settings save

    assert widget._selected_account() is None, "the refill clears the selection"
    assert not widget._update_button.isEnabled(), (
        "Update must grey out with nothing selected — otherwise the click is a "
        "silent no-op and the user cannot tell why their edit did not apply"
    )
    assert not widget._delete_button.isEnabled(), (
        "Delete must grey out with nothing selected"
    )


def test_FIBR0328_visually_identical_account_names_are_refused(service):
    """The account name check has the same NFC gap as the category one
    (2026-08-31 audit, LOW/INFO) — two spellings of one name that render
    identically must not both be accepted.
    """
    import unicodedata

    svc = AccountService(service.vault)
    precomposed = "Café float"
    decomposed = unicodedata.normalize("NFD", precomposed)
    assert precomposed != decomposed, "the fixture is not testing two spellings"

    svc.add_account(precomposed, "current")
    with pytest.raises(ValueError):
        svc.add_account(decomposed, "current")
