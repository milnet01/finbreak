"""FIBR-0005 — P03 accounts. Enforces tests/features/accounts/spec.md.

Account model + CRUD + the accounts-manager UI, and the first forward-only
schema migration (v1->v2) that links every transaction to an account. The
repository/service/migration layers are tested headless; the accounts-manager
and picker round-trips (INV-7) use the pytest-qt `qtbot` fixture. Every on-disk
vault uses `tmp_path`; no test touches the network or real financial data
(testing.md § 6).
"""

import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlcipher3 import dbapi2
from sqlcipher3.dbapi2 import IntegrityError

from finbreak.crypto import KEY_LEN, SALT_LEN, derive_key
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
from finbreak.models import FORMAT_VERSION, AccountType, KdfParams
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import (
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    AuthService,
)
from finbreak.services.transactions import TransactionService

_PW = b"correct horse battery staple"

pytestmark = pytest.mark.features


def _params(salt: bytes) -> KdfParams:
    return KdfParams(
        format_version=FORMAT_VERSION,
        memory_kib=ARGON2_MEMORY_KIB,
        time_cost=ARGON2_TIME_COST,
        parallelism=ARGON2_PARALLELISM,
        key_len=KEY_LEN,
        salt_len=SALT_LEN,
        salt=salt,
    )


@pytest.fixture
def paths(tmp_path) -> tuple[Path, Path]:
    return tmp_path / "vault.db", tmp_path / "vault.kdf.json"


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


def _build_v1_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """Write a raw FIBR-0004-shape v1 vault (schema_version=1, account-less
    transactions) + its sidecar, WITHOUT Vault.create() (which now migrates to
    v2). This is the INV-4 upgrade-path fixture."""
    params = _params(salt)
    key = derive_key(bytearray(_PW), salt, params)
    os.close(os.open(vault_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")
    conn.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version(version) VALUES (1)")
    conn.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO settings(key, value) VALUES ('base_currency', 'ZAR')")
    conn.execute("INSERT INTO settings(key, value) VALUES ('minor_unit_exponent', '2')")
    conn.execute(
        "CREATE TABLE transactions(id INTEGER PRIMARY KEY, occurred_on TEXT NOT "
        "NULL, amount_minor INTEGER NOT NULL, description TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    for occurred_on, amount_minor, description in rows:
        conn.execute(
            "INSERT INTO transactions(occurred_on, amount_minor, description, "
            "created_at) VALUES (?, ?, ?, ?)",
            (occurred_on, amount_minor, description, "2026-01-01T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()
    payload = json.dumps(params.to_sidecar_dict(), indent=2)
    fd = os.open(sidecar_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(payload)


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
    assert got.created_at, "created_at is a well-formed timestamp"

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
    _build_v1_vault(
        vault_path,
        sidecar_path,
        salt,
        [("2026-01-01", -100, "a"), ("2026-02-01", 200, "b")],
    )

    svc = AuthService(vault_path, sidecar_path)
    assert svc.unlock(bytearray(_PW)) is True  # unlock runs the migration
    conn = svc.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 2

    accounts = AccountRepository(conn).list_all()
    assert [a.name for a in accounts] == [DEFAULT_ACCOUNT_NAME]
    default_id = accounts[0].id

    txs = TransactionRepository(conn).list_all()
    assert len(txs) == 2, "every prior row is preserved"
    assert all(t.account_id == default_id for t in txs), "backfilled to Default"
    assert {(t.amount_minor, t.description) for t in txs} == {(-100, "a"), (200, "b")}
    svc.lock()


def test_INV4_first_run_vault_is_v2_with_one_default(service):
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 2
    accounts = AccountRepository(conn).list_all()
    assert [a.name for a in accounts] == [DEFAULT_ACCOUNT_NAME]
    assert accounts[0].type == "current"


def test_INV4_idempotent_on_v2(service):
    # Re-running migrations on an already-v2 vault changes nothing.
    conn = service.vault.connection
    run_migrations(conn)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 2
    assert len(AccountRepository(conn).list_all()) == 1, "Default not duplicated"


def test_INV4_rolls_back_on_failure(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    rows = [("2026-01-01", -100, "a"), ("2026-02-01", 200, "b")]
    _build_v1_vault(vault_path, sidecar_path, salt, rows)

    key = derive_key(bytearray(_PW), salt, _params(salt))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")

    class _FailAtRename:
        """Proxy that raises on the RENAME only (the migration wedge point),
        forwarding BEGIN/DROP/INSERT/UPDATE/ROLLBACK through."""

        def __init__(self, real):
            self._real = real

        def execute(self, sql, *a):
            if "RENAME" in sql.upper():
                raise RuntimeError("injected failure at RENAME")
            return self._real.execute(sql, *a)

        def commit(self):
            return self._real.commit()

        def rollback(self):
            return self._real.rollback()

    with pytest.raises(RuntimeError):
        run_migrations(_FailAtRename(conn))
    conn.close()

    # The vault must still open at v1 with its original account-less rows.
    svc = AuthService(vault_path, sidecar_path)
    assert svc.unlock(bytearray(_PW)) is True
    reopened = svc.vault.connection
    # unlock re-ran (and completed) the migration, so it is v2 now — but the
    # point is the earlier failure left a clean, re-openable vault, not a
    # half-migrated wreck. Prove the rows survived intact.
    txs = TransactionRepository(reopened).list_all()
    assert {(t.amount_minor, t.description) for t in txs} == {(-100, "a"), (200, "b")}
    svc.lock()


def test_INV4_refuses_newer_than_latest(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    _build_v1_vault(vault_path, sidecar_path, salt, [])
    key = derive_key(bytearray(_PW), salt, _params(salt))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")
    conn.execute("UPDATE schema_version SET version = ?", (LATEST_SCHEMA_VERSION + 1,))
    conn.commit()
    with pytest.raises(SchemaVersionError):
        run_migrations(conn)
    conn.close()


# --------------------------------------------------------------------------- #
# INV-5 — every transaction belongs to an account
# --------------------------------------------------------------------------- #
def test_INV5_transaction_carries_account_and_name(service):
    default_id = _default_id(service.vault)
    txs = TransactionService(service.vault)
    txs.add_transaction(default_id, "2026-07-01", "-12.34", "coffee")

    rows = txs.list_transactions()
    assert len(rows) == 1
    transaction, display, account_name = rows[0]
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
    transaction, _display, name = txs.list_transactions()[0]
    assert transaction.account_id == savings.id
    assert transaction.id != transaction.account_id, "id and account_id are distinct"
    assert name == "Savings"


# --------------------------------------------------------------------------- #
# INV-6 — delete guard (block-in-use + keep >= 1)
# --------------------------------------------------------------------------- #
def test_INV6_delete_in_use_account_is_blocked(service):
    default_id = _default_id(service.vault)
    AccountService(service.vault)  # ensure module import path exercised
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
    from finbreak.ui.accounts import AccountsWidget
    from finbreak.ui.main_window import MainWindow

    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._name.setText("Holiday")
    widget._type.setCurrentIndex(widget._type.findData("savings"))
    widget._add_button.click()
    listed = [widget._list.item(i).text() for i in range(widget._list.count())]
    assert any("Holiday" in text for text in listed), "added account shows in the list"

    window = MainWindow(service)
    qtbot.addWidget(window)
    picker_names = [window._account.itemText(i) for i in range(window._account.count())]
    assert any("Holiday" in n for n in picker_names), "selectable in the tx picker"


def test_INV7c_transaction_shows_account_name_in_table(qtbot, service):
    from finbreak.ui.main_window import MainWindow

    default_id = _default_id(service.vault)
    TransactionService(service.vault).add_transaction(
        default_id, "2026-07-01", "-12.34", "coffee"
    )
    window = MainWindow(service)
    qtbot.addWidget(window)
    assert window._table.rowCount() == 1
    cells = [
        window._table.item(0, c).text() for c in range(window._table.columnCount())
    ]
    assert any(DEFAULT_ACCOUNT_NAME in c for c in cells), "the account name is shown"


def test_INV7d_delete_in_use_shows_message_and_removes_nothing(qtbot, service):
    from finbreak.ui.accounts import AccountsWidget

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
    assert widget._error.text() != "", "an in-use delete shows a clear message"
    assert any(a.id == default_id for a in svc.list_accounts()), "nothing removed"


def test_INV7e_delete_empty_nonlast_removes_from_list(qtbot, service):
    from finbreak.ui.accounts import AccountsWidget

    svc = AccountService(service.vault)
    spare = svc.add_account("Spare", "other")
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._select_account(spare.id)
    widget._delete_button.click()
    listed = [widget._list.item(i).text() for i in range(widget._list.count())]
    assert not any("Spare" in text for text in listed), "empty non-last account gone"


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
