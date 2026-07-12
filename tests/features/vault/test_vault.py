"""FIBR-0004 — the security-spine vertical slice. Enforces tests/features/vault/spec.md.

The crypto/vault/service/repository layers are unit- and feature-tested
headless; the two UI round-trips (INV-5 first-run widget, INV-6 unlock widget +
main window) use the pytest-qt `qtbot` fixture. Every on-disk vault lives under
`tmp_path`; no test touches the network or real financial data (testing.md § 6).
"""

import ast
import json
import logging
import os
import re
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlcipher3.dbapi2 import DatabaseError

import finbreak
from conftest import _PW
from finbreak.crypto import (
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    KEY_LEN,
    SALT_LEN,
    derive_key,
    load_and_validate_params,
    validate_params,
)
from finbreak.errors import KdfPolicyError, VaultLockedError, VaultStateError
from finbreak.migrations import DEFAULT_ACCOUNT_NAME
from finbreak.models import FORMAT_VERSION, KdfParams
from finbreak.repositories.accounts import AccountRepository
from finbreak.services.auth import AuthService
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import (
    TransactionService,
    parse_transaction,
    to_display_decimal,
)
from finbreak.vault import Vault

# These enforce tests/features/vault/spec.md, so the whole module is a
# feature-conformance suite — without the marker `pytest -m features` would
# silently run zero security-spine tests (testing.md § 3.2).
pytestmark = pytest.mark.features


def _params(salt: bytes) -> KdfParams:
    """A valid, at-floor KdfParams for the given salt."""
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
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def _default_id(service: AuthService) -> int:
    """The seeded Default account's id (resolved by name), for the account_id
    every transaction now requires (FIBR-0005). Call after first_run/unlock."""
    accounts = AccountRepository(service._vault.connection).list_all()
    return next(a.id for a in accounts if a.name == DEFAULT_ACCOUNT_NAME)


# --------------------------------------------------------------------------- #
# INV-1 — encrypted at rest, integrity-checked
# --------------------------------------------------------------------------- #
def test_INV1_encrypted_at_rest_hmac_and_tamper_detection(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    params = _params(salt)

    vault = Vault(vault_path, sidecar_path)
    vault.create(derive_key(bytearray(_PW), salt, params), params, "ZAR", 2)
    vault.close()

    magic = vault_path.read_bytes()[:16]
    assert magic != b"SQLite format 3\x00", (
        "vault must be ciphertext, not SQLite plaintext"
    )

    # Correct raw key re-opens and reports the HMAC defaults.
    reopened = Vault(vault_path, sidecar_path)
    reopened.open(derive_key(bytearray(_PW), salt, params))
    conn = reopened.connection
    assert conn.execute("PRAGMA cipher_use_hmac").fetchone()[0] == "1"
    assert conn.execute("PRAGMA cipher_hmac_algorithm").fetchone()[0] == "HMAC_SHA512"
    reopened.close()

    # Wrong key raises DatabaseError on first read.
    wrong = derive_key(bytearray(b"the wrong password"), salt, params)
    with pytest.raises(DatabaseError):
        Vault(vault_path, sidecar_path).open(wrong)

    # A flipped body byte fails the HMAC → DatabaseError even with the right key.
    # Flip inside page 1 (past the 16-byte plaintext salt) — the page the schema
    # read below checks, per INV-1's stated first-read mechanism.
    raw = bytearray(vault_path.read_bytes())
    raw[100] ^= 0xFF
    vault_path.write_bytes(raw)
    with pytest.raises(DatabaseError):
        Vault(vault_path, sidecar_path).open(derive_key(bytearray(_PW), salt, params))


def test_connection_pins_hmac_and_busy_timeout(paths):
    """Every connection pins the defense-in-depth PRAGMAs: HMAC integrity is set
    explicitly ON (FIBR-0077, not left resting on the SQLCipher-4 default a dep
    bump could flip) and a 5s busy_timeout is applied so a transient lock (a
    second instance, a slow backup/AV) waits instead of raising a raw
    OperationalError (FIBR-0076)."""
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    params = _params(salt)

    v = Vault(vault_path, sidecar_path)
    v.create(derive_key(bytearray(_PW), salt, params), params, "ZAR", 2)
    v.close()

    reopened = Vault(vault_path, sidecar_path)
    reopened.open(derive_key(bytearray(_PW), salt, params))
    conn = reopened.connection
    assert conn.execute("PRAGMA cipher_use_hmac").fetchone()[0] == "1"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    reopened.close()


# --------------------------------------------------------------------------- #
# INV-2 — strong, pinned, non-downgradeable KDF
# --------------------------------------------------------------------------- #
def test_INV2a_derivation_length_deterministic_salt_sensitive():
    salt = bytes(SALT_LEN)
    key1 = derive_key(bytearray(_PW), salt, _params(salt))
    key2 = derive_key(bytearray(_PW), salt, _params(salt))
    assert isinstance(key1, bytearray) and len(key1) == KEY_LEN
    assert bytes(key1) == bytes(key2), "same inputs must derive the same key"

    other_salt = bytes([7]) * SALT_LEN
    key3 = derive_key(bytearray(_PW), other_salt, _params(other_salt))
    assert bytes(key3) != bytes(key1), "a different salt must give a different key"


def test_INV2b_memory_floor_is_directional():
    below = _params(bytes(SALT_LEN))
    below.memory_kib = ARGON2_MEMORY_KIB - 1
    with pytest.raises(KdfPolicyError):
        validate_params(below)

    validate_params(_params(bytes(SALT_LEN)))  # exactly at the floor — allowed

    above = _params(bytes(SALT_LEN))
    above.memory_kib = ARGON2_MEMORY_KIB + 1024
    validate_params(above)  # above the floor — allowed (creation pin can rise)


def test_INV2c_exact_format_rejects_wrong_lengths():
    wrong_key_len = _params(bytes(SALT_LEN))
    wrong_key_len.key_len = KEY_LEN * 2
    with pytest.raises(KdfPolicyError):
        validate_params(wrong_key_len)

    long_salt = _params(bytes(SALT_LEN + 1))
    with pytest.raises(KdfPolicyError):
        validate_params(long_salt)

    lying_salt_len = _params(bytes(SALT_LEN))
    lying_salt_len.salt_len = SALT_LEN + 1  # field disagrees with the real salt
    with pytest.raises(KdfPolicyError):
        validate_params(lying_salt_len)


@pytest.mark.parametrize(
    "content",
    [
        "this is not json{",
        "",
        json.dumps({"format_version": 1}),  # missing the other six fields
        json.dumps({"format_version": 1, "memory_kib": ARGON2_MEMORY_KIB}),
        json.dumps(  # all fields present, but one has the wrong type
            {
                "format_version": 1,
                "memory_kib": "not-an-int",
                "time_cost": ARGON2_TIME_COST,
                "parallelism": ARGON2_PARALLELISM,
                "key_len": KEY_LEN,
                "salt_len": SALT_LEN,
                "salt_hex": "00" * SALT_LEN,
            }
        ),
        json.dumps(  # salt_hex is not valid hexadecimal
            {
                "format_version": 1,
                "memory_kib": ARGON2_MEMORY_KIB,
                "time_cost": ARGON2_TIME_COST,
                "parallelism": ARGON2_PARALLELISM,
                "key_len": KEY_LEN,
                "salt_len": SALT_LEN,
                "salt_hex": "zz" * SALT_LEN,
            }
        ),
        json.dumps(  # an unknown/future format_version is refused, not reinterpreted
            {
                "format_version": FORMAT_VERSION + 1,
                "memory_kib": ARGON2_MEMORY_KIB,
                "time_cost": ARGON2_TIME_COST,
                "parallelism": ARGON2_PARALLELISM,
                "key_len": KEY_LEN,
                "salt_len": SALT_LEN,
                "salt_hex": "00" * SALT_LEN,
            }
        ),
    ],
)
def test_INV2c_malformed_sidecar_raises_kdf_policy_error(tmp_path, content):
    sidecar = tmp_path / "vault.kdf.json"
    sidecar.write_text(content)
    with pytest.raises(KdfPolicyError):
        load_and_validate_params(sidecar)


# --------------------------------------------------------------------------- #
# INV-3 — key lifetime and wipe
# --------------------------------------------------------------------------- #
def test_INV3_lock_wipes_key_and_locks_out_queries(service):
    service.first_run(bytearray(_PW), "ZAR")
    key_buffer = service._key
    assert key_buffer is not None and any(key_buffer), "an unlocked service holds a key"

    service.lock()
    assert bytes(key_buffer) == bytes(len(key_buffer)), "lock must zero the key buffer"
    assert service._key is None

    with pytest.raises(VaultLockedError):
        TransactionService(service._vault).list_transactions()


def test_INV3_idle_autolock_wipes_key(service):
    service.first_run(bytearray(_PW), "ZAR")
    key_buffer = service._key
    service._on_idle_timeout()
    assert bytes(key_buffer) == bytes(len(key_buffer))
    assert service._key is None


def test_INV3_idle_timeout_noop_when_already_locked(service):
    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    fired = []
    service.on_auto_lock = lambda: fired.append(True)
    service._on_idle_timeout()  # a stale queued fire when already locked
    assert fired == [], "must not route/notify the UI when there is no key held"


class _SpyTimer:
    """A stand-in QTimer that records start() calls (FIBR-0114)."""

    def __init__(self) -> None:
        self.starts = 0

    def start(self, *args: object) -> None:
        self.starts += 1

    def stop(self) -> None:
        pass


def test_FIBR0114_notify_activity_restarts_running_idle_timer(service):
    # The auto-lock is an INACTIVITY timer: user activity must RESET the countdown so
    # the timeout is measured from the last interaction, not from unlock (FIBR-0114).
    service.first_run(bytearray(_PW), "ZAR")  # unlock -> _key held
    service._timer = _SpyTimer()  # stand in for the armed timer (headless has none)
    service.notify_activity()
    assert service._timer.starts == 1, "activity must re-arm the idle countdown"


def test_FIBR0114_notify_activity_noop_when_locked(service):
    # A stray input event after the vault locks must not touch a (non-existent) timer.
    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    service._timer = _SpyTimer()
    service.notify_activity()
    assert service._timer.starts == 0, "no key held -> no re-arm"


def test_INV3_exit_handler_wipes_and_is_noop_when_locked(service):
    service.first_run(bytearray(_PW), "ZAR")
    key_buffer = service._key
    service.on_about_to_quit()
    assert bytes(key_buffer) == bytes(len(key_buffer))
    service.on_about_to_quit()  # already locked — must be a no-op, not a crash
    assert service._key is None, "the exit handler leaves no key behind"


def test_INV3_password_buffer_is_wiped_on_every_entry_point(service, paths):
    first_run_pw = bytearray(_PW)
    service.first_run(first_run_pw, "ZAR")
    assert bytes(first_run_pw) == bytes(len(first_run_pw)), (
        "first_run must wipe the password"
    )
    service.lock()

    good_pw = bytearray(_PW)
    assert service.unlock(good_pw) is True
    assert bytes(good_pw) == bytes(len(good_pw)), "unlock must wipe on success"
    service.lock()

    bad_pw = bytearray(b"the wrong password")
    assert service.unlock(bad_pw) is False
    assert bytes(bad_pw) == bytes(len(bad_pw)), (
        "unlock must wipe on the wrong-password path"
    )
    assert service._key is None

    other = AuthService(*paths)
    pw, confirm = bytearray(b"aaa"), bytearray(b"bbb")
    with pytest.raises(ValueError):
        other.validate_first_run(pw, confirm, "ZAR")
    assert bytes(pw) == bytes(len(pw)) and bytes(confirm) == bytes(len(confirm))


# --------------------------------------------------------------------------- #
# INV-4 — one transaction, one DB transaction, exact money
# --------------------------------------------------------------------------- #
def test_INV4a_failed_write_rolls_back(service, monkeypatch):
    service.first_run(bytearray(_PW), "ZAR")
    from finbreak.repositories.transactions import TransactionRepository

    def boom(self):
        # The INSERT has run on this connection but is not committed. Prove it's
        # live HERE, so the post-reopen absence proves a real rollback — not that
        # the INSERT never happened (which would also yield 0 rows).
        live = self._conn.execute("SELECT count(*) FROM transactions").fetchone()[0]
        assert live == 1, "the INSERT must be visible on the connection pre-commit"
        raise RuntimeError("simulated failure after INSERT, before commit")

    monkeypatch.setattr(TransactionRepository, "_commit", boom)
    with pytest.raises(RuntimeError):
        TransactionService(service._vault).add_transaction(
            _default_id(service), "2026-07-01", "-12.34", "coffee"
        )

    service.lock()
    service.unlock(bytearray(_PW))
    rows = TransactionService(service._vault).list_transactions()
    assert len(rows) == 0, f"a rolled-back INSERT must be invisible; found {len(rows)}"


def test_INV4a_money_round_trips_exactly(service):
    service.first_run(bytearray(_PW), "ZAR")
    txs = TransactionService(service._vault)
    txs.add_transaction(_default_id(service), "2026-07-01", "-12.34", "coffee")

    rows = txs.list_transactions()
    assert len(rows) == 1
    transaction, display, _account, _category = rows[0]
    assert transaction.amount_minor == -1234, (
        "money is stored as signed integer minor units"
    )
    assert display == Decimal("-12.34"), (
        "and reconstructs exactly, with no float round-trip"
    )


@pytest.mark.parametrize(
    "occurred_on, amount, description",
    [
        ("2026-07-01", "1.005", "too many fractional digits"),
        ("2026-07-01", "0", "zero"),
        ("2026-07-01", "0.00", "zero"),
        ("2026-07-01", "abc", "not a number"),
        ("2026-07-01", "nan", "not finite"),
        ("2026-07-01", "inf", "not finite"),
        ("2026-07-01", "-12.34", ""),
        ("2026-07-01", "-12.34", "   "),
        ("not-a-date", "-12.34", "bad date"),
    ],
)
def test_INV4b_rejects_bad_money_input(occurred_on, amount, description):
    with pytest.raises(ValueError):
        parse_transaction(occurred_on, amount, description, exponent=2)


def test_INV4b_accepts_either_sign_and_large_magnitude():
    assert parse_transaction("2026-07-01", "-12.34", "out", 2)[1] == -1234
    assert parse_transaction("2026-07-01", "50.00", "in", 2)[1] == 5000
    # trailing zeros beyond the exponent are the same value — accepted, not
    # rejected as "too many fractional digits" (12.340 == 12.34).
    assert parse_transaction("2026-07-01", "12.340", "trailing zero", 2)[1] == 1234
    assert parse_transaction("2099-01-01", "10.00", "future date allowed", 2)[1] == 1000
    big = parse_transaction("2026-07-01", "90000000000000.00", "big", 2)[1]
    assert big == 9_000_000_000_000_000


def test_INV4b_to_display_decimal_inverts_scaling():
    assert to_display_decimal(-1234, 2) == Decimal("-12.34")
    assert to_display_decimal(5000, 2) == Decimal("50.00")


# --------------------------------------------------------------------------- #
# INV-5 — first-run vs unlock routing, with mixed-state guard
# --------------------------------------------------------------------------- #
def test_INV5_routes_first_run_when_neither_file_present(service):
    assert service.state() == "first_run"


def test_INV5_routes_unlock_when_both_present(service):
    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    assert service.state() == "unlock"


def test_INV5_sidecar_without_vault_is_mixed_state(paths):
    _, sidecar_path = paths
    sidecar_path.write_text("{}")
    with pytest.raises(VaultStateError):
        AuthService(*paths).state()


def test_INV5_vault_without_sidecar_is_mixed_state(paths):
    vault_path, _ = paths
    vault_path.write_bytes(b"not empty")
    with pytest.raises(VaultStateError):
        AuthService(*paths).state()


def test_INV5_first_run_validation_rejects_and_writes_nothing(service, paths):
    vault_path, sidecar_path = paths
    with pytest.raises(ValueError):
        service.validate_first_run(bytearray(_PW), bytearray(b"different"), "ZAR")
    with pytest.raises(ValueError):
        service.validate_first_run(bytearray(_PW), bytearray(_PW), "XYZ")
    with pytest.raises(ValueError):
        service.validate_first_run(bytearray(b""), bytearray(b""), "ZAR")
    assert not vault_path.exists() and not sidecar_path.exists()


def test_INV5_first_run_creates_settings_and_both_files(service, paths):
    vault_path, sidecar_path = paths
    service.first_run(bytearray(_PW), "ZAR")
    conn = service._vault.connection
    assert (
        conn.execute("SELECT value FROM settings WHERE key='base_currency'").fetchone()[
            0
        ]
        == "ZAR"
    )
    assert (
        conn.execute(
            "SELECT value FROM settings WHERE key='minor_unit_exponent'"
        ).fetchone()[0]
        == "2"
    )
    # First-run now migrates the fresh v1 baseline straight to the latest
    # schema (FIBR-0005 D1), so a new vault lands at v8 (FIBR-0011 transfer_pairs
    # table), not v1.
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
    assert vault_path.exists() and sidecar_path.exists()


def test_create_failure_after_conn_live_resets_lock_state(paths, monkeypatch):
    """A failure in run_migrations / _write_sidecar — after the connection is
    live — must close it and reset the vault to locked, never leak an open,
    unlocked connection (which silently defeats the VaultLockedError guard).
    Mirrors open()'s existing close-and-reset. (indie-review H-A)"""
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    params = _params(salt)

    def boom(self, _params):
        raise RuntimeError("simulated failure after the connection is live")

    monkeypatch.setattr(Vault, "_write_sidecar", boom)
    vault = Vault(vault_path, sidecar_path)
    with pytest.raises(RuntimeError):
        vault.create(derive_key(bytearray(_PW), salt, params), params, "ZAR", 2)

    with pytest.raises(VaultLockedError):
        _ = vault.connection  # the leaked connection must be gone → locked


def test_INV5_first_run_writes_vault_before_sidecar(service, paths, monkeypatch):
    vault_path, sidecar_path = paths

    def boom(self, params):
        raise RuntimeError("simulated crash before the sidecar is written")

    monkeypatch.setattr(Vault, "_write_sidecar", boom)
    with pytest.raises(RuntimeError):
        service.first_run(bytearray(_PW), "ZAR")

    assert vault_path.exists(), "the vault is created first"
    assert not sidecar_path.exists(), (
        "the sidecar is written last — absent after a mid-write crash"
    )
    with pytest.raises(VaultStateError):
        AuthService(*paths).state()  # the next launch catches the mixed state


# --------------------------------------------------------------------------- #
# INV-6 — unlock/lock round-trip (headless core + UI)
# --------------------------------------------------------------------------- #
def test_INV6_unlock_lock_roundtrip_headless(service):
    service.first_run(bytearray(_PW), "ZAR")
    TransactionService(service._vault).add_transaction(
        _default_id(service), "2026-07-01", "-12.34", "coffee"
    )
    service.lock()

    assert service.unlock(bytearray(b"the wrong password")) is False
    assert service._key is None, "a wrong password retains no key"

    assert service.unlock(bytearray(_PW)) is True
    assert len(TransactionService(service._vault).list_transactions()) == 1
    service.lock()
    assert service._key is None


def test_INV6_unlock_widget_roundtrip(qtbot, service):
    # Re-homed FIBR-0051: UnlockWidget(QWidget) → UnlockDialog(QDialog); the
    # signals + fields (._password/._unlock_button/.unlocked/.unlock_failed) are
    # unchanged, so this round-trip is a mechanical rename.
    from finbreak.ui.unlock import UnlockDialog

    service.first_run(bytearray(_PW), "ZAR")
    TransactionService(service._vault).add_transaction(
        _default_id(service), "2026-07-01", "-12.34", "coffee"
    )
    service.lock()

    widget = UnlockDialog(service)
    qtbot.addWidget(widget)

    # 15 s, not 5 s: each click runs a real 47 MiB Argon2id derivation on a
    # worker thread; a loaded/constrained CI runner can approach 5 s (flake).
    widget._password.setText("the wrong password")
    with qtbot.waitSignal(widget.unlock_failed, timeout=15000):
        widget._unlock_button.click()
    assert service._key is None
    assert widget._error.text() != "", "a failed unlock shows a message"

    widget._password.setText(_PW.decode())
    with qtbot.waitSignal(widget.unlocked, timeout=15000):
        widget._unlock_button.click()
    assert service._key is not None


def test_INV6_unlock_ignores_reentrant_submit_while_deriving(qtbot, service):
    # A second submit while a derivation is in flight must be ignored — else it
    # would spawn a second worker and orphan the first (guard: unlock.py).
    from finbreak.ui.unlock import UnlockDialog

    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    widget = UnlockDialog(service)
    qtbot.addWidget(widget)

    widget._password.setText(_PW.decode())
    sentinel = object()
    widget._worker = sentinel  # simulate a derivation already running
    widget._on_unlock()
    assert widget._worker is sentinel, "a re-entrant submit must not replace the worker"
    assert widget._password.text() == _PW.decode(), "the password field is untouched"


def test_INV6_main_window_lists_saved_transaction(qtbot, service):
    # Re-homed FIBR-0051 into HomeView, then relocated to the Transactions tab when
    # Home became the dashboard (FIBR-0012 D7); the assertion re-points there.
    from finbreak.ui.transactions import TransactionsView

    service.first_run(bytearray(_PW), "ZAR")
    TransactionService(service._vault).add_transaction(
        _default_id(service), "2026-07-01", "-12.34", "coffee"
    )

    view = TransactionsView(
        TransactionService(service._vault), CategorizationService(service._vault)
    )
    qtbot.addWidget(view)
    assert view._table.rowCount() == 1, "the saved transaction appears in the table"


def test_main_window_date_field_renders_unambiguous_iso(qtbot, service):
    # The date picker shows YYYY/MM/DD, not the locale's ambiguous M/D/YY — a
    # 2026-07-04 date must read "2026/07/04" to any user regardless of locale.
    # Re-homed FIBR-0051: the manual-entry form (incl. the date field) moved from
    # MainWindow into ManualEntryDialog (D3).
    from PySide6.QtCore import QDate

    from finbreak.ui.manual_entry import ManualEntryDialog

    service.first_run(bytearray(_PW), "ZAR")
    dialog = ManualEntryDialog(service)
    qtbot.addWidget(dialog)
    dialog._date.setDate(QDate(2026, 7, 4))
    assert dialog._date.text() == "2026/07/04"


def test_INV6_idle_autolock_routes_ui_back_to_unlock(qtbot, service):
    # An idle auto-lock wipes the key + closes the vault; the shell must return
    # to the locked shell, else the next action hits a locked vault and crashes.
    # Rewritten FIBR-0051 (INV-4a) / reshaped FIBR-0052 (INV-3): AppShell/whole-
    # window-swap → a persistent MainWindow(QMainWindow) whose *content widget*
    # (now the tabbed workspace) is destroyed and swapped for the 🔒 Locked
    # placeholder + a re-opened UnlockDialog (same window instance).
    from finbreak.ui.main_window import MainWindow
    from finbreak.ui.unlock import UnlockDialog

    service.first_run(bytearray(_PW), "ZAR")  # leaves the service unlocked
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()  # drive past locked-file routing to a live workspace
    workspace = window.centralWidget().currentWidget()
    assert workspace.objectName() == "workspace"
    assert workspace.currentWidget().objectName() == "tab_home"

    service._on_idle_timeout()  # the 10-minute idle timer fires
    assert service._key is None, "idle auto-lock wipes the key"
    assert window.centralWidget().currentWidget().objectName() == "placeholder_locked"
    assert isinstance(window._dialog, UnlockDialog), (
        "the UI returns to the locked shell so no action reaches the locked vault"
    )


# --------------------------------------------------------------------------- #
# INV-7 — no plaintext secret on disk or in logs; 0o600 perms
# --------------------------------------------------------------------------- #
def test_INV7_sidecar_holds_no_secret(service, paths):
    _, sidecar_path = paths
    service.first_run(bytearray(_PW), "ZAR")
    text = sidecar_path.read_text()
    assert _PW.decode() not in text
    assert set(json.loads(text)) == {
        "format_version",
        "memory_kib",
        "time_cost",
        "parallelism",
        "key_len",
        "salt_len",
        "salt_hex",
    }


def test_INV7_lifecycle_logs_carry_no_secret(service, caplog):
    password = _PW.decode()
    with caplog.at_level(logging.INFO, logger="finbreak"):
        service.first_run(bytearray(_PW), "ZAR")
        TransactionService(service._vault).add_transaction(
            _default_id(service), "2026-07-01", "-12.34", "coffee"
        )
        service.lock()
        service.unlock(bytearray(_PW))
        service.lock()
        service.unlock(bytearray(b"the wrong password"))

    messages = [record.getMessage() for record in caplog.records]
    joined = "\n".join(messages)
    assert password not in joined, "the master password must never be logged"
    assert "12.34" not in joined, "transaction amounts must not be logged"
    # The derived key — and its 64-char hex form (a plausible leak is logging
    # the `PRAGMA key = "x'<hex>'"` statement at DEBUG) — must never appear.
    params = service.load_params()
    key = derive_key(bytearray(_PW), params.salt, params)
    assert bytes(key).hex() not in joined, "the derived key (hex) must never be logged"
    assert bytes(key) not in joined.encode(), "the derived key bytes must not be logged"
    assert messages, "the cycle must emit at least one non-secret lifecycle line"


@pytest.mark.skipif(
    not hasattr(__import__("os"), "getuid"), reason="POSIX mode bits only"
)
def test_INV7_vault_and_sidecar_are_owner_only(service, paths):
    vault_path, sidecar_path = paths
    service.first_run(bytearray(_PW), "ZAR")
    assert vault_path.stat().st_mode & 0o777 == 0o600
    assert sidecar_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX mode bits only")
def test_INV7_data_dir_is_owner_only(tmp_path, monkeypatch):
    """The app-data directory itself is owner-only, not just the two files
    inside it — else another local user can stat the dir and read file
    existence/size/mtime metadata. (indie-review M-crypto2)"""
    from PySide6.QtCore import QStandardPaths

    from finbreak import paths as paths_mod

    target = tmp_path / "appdata" / "finbreak"
    monkeypatch.setattr(
        QStandardPaths, "writableLocation", staticmethod(lambda _loc: str(target))
    )
    created = paths_mod.data_dir()
    assert created == target
    assert created.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(
    not (hasattr(os, "symlink") and hasattr(os, "O_NOFOLLOW")),
    reason="POSIX symlink + O_NOFOLLOW",
)
def test_INV7_sidecar_write_refuses_to_follow_symlink(paths, tmp_path):
    """The sidecar's temp-file write refuses to follow a pre-planted symlink at
    its .tmp path, rather than truncating/writing through it. (indie-review
    M-crypto3)"""
    vault_path, sidecar_path = paths
    target = tmp_path / "evil-target"
    tmp_link = sidecar_path.with_name(sidecar_path.name + ".tmp")
    os.symlink(target, tmp_link)

    vault = Vault(vault_path, sidecar_path)
    with pytest.raises(OSError):
        vault._write_sidecar(_params(bytes(SALT_LEN)))
    assert not target.exists(), "the write must not follow the symlink to its target"


# --------------------------------------------------------------------------- #
# INV-8 — no network dependency introduced
# --------------------------------------------------------------------------- #
_BANNED_NETWORK = {"socket", "http", "urllib", "requests", "ftplib"}


def _banned_string_arg(node: ast.Call) -> str | None:
    """The banned top-level module named by a dynamic-import call, if any.

    Catches ``__import__("socket")`` and ``importlib.import_module("urllib.x")``
    with a string-literal first argument — the forms a plain Import/ImportFrom
    walk misses.
    """
    func = node.func
    # __import__("x"), importlib.import_module("x"), or a bare import_module("x")
    # after `from importlib import import_module`.
    is_dunder = isinstance(func, ast.Name) and func.id == "__import__"
    is_attr_module = isinstance(func, ast.Attribute) and func.attr == "import_module"
    is_bare_module = isinstance(func, ast.Name) and func.id == "import_module"
    if not (is_dunder or is_attr_module or is_bare_module) or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        top = first.value.split(".")[0]
        return top if top in _BANNED_NETWORK else None
    return None


# The ONE file allowed to import `urllib` — the opt-in update check's sole
# networked module (FIBR-0054 INV-12/D12). Keyed on the package-relative POSIX
# path, NOT the basename, so a stray `update_fetch.py` elsewhere is not waved
# through. Every OTHER banned name stays banned here; `urllib` stays banned in
# every other file.
_URLLIB_ALLOWLISTED_REL_PATH = "services/update_fetch.py"


def _allowed(rel_path: str, banned_top: str) -> bool:
    """Whether importing *banned_top* is the single consented exception (INV-12):
    `urllib`, and only in `services/update_fetch.py`."""
    return banned_top == "urllib" and rel_path == _URLLIB_ALLOWLISTED_REL_PATH


def _network_offenders(rel_path: str, source: str) -> list[str]:
    """Banned network imports in one file's *source*, honouring the single
    `urllib`-in-update_fetch allowlist (FIBR-0054 INV-12). *rel_path* is the file's
    path relative to the package root, POSIX-separated. Covers static
    `import`/`from` and the dynamic `__import__`/`import_module(...)` forms."""
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BANNED_NETWORK and not _allowed(rel_path, top):
                    offenders.append(f"{rel_path}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in _BANNED_NETWORK and not _allowed(rel_path, top):
                offenders.append(f"{rel_path}: from {node.module}")
        elif isinstance(node, ast.Call):
            banned = _banned_string_arg(node)
            if banned and not _allowed(rel_path, banned):
                offenders.append(f"{rel_path}: dynamic import {banned}")
    return offenders


def test_INV8_no_network_imports_under_src() -> None:
    package_root = Path(finbreak.__file__).parent
    offenders: list[str] = []
    for py in package_root.rglob("*.py"):
        rel_path = py.relative_to(package_root).as_posix()
        offenders += _network_offenders(rel_path, py.read_text())
    assert not offenders, f"network imports found under src/finbreak/: {offenders}"


def test_INV12_urllib_allowed_only_in_update_fetch() -> None:
    """The amended allowlist waves `urllib` through ONLY at the exact relative
    path `services/update_fetch.py` — not by basename, not elsewhere (INV-12)."""
    # the one allowed case: urllib, in update_fetch.py
    fetch = "services/update_fetch.py"
    assert _network_offenders(fetch, "import urllib.request") == []
    assert _network_offenders(fetch, 'import_module("urllib.request")') == []
    # still banned there: every other network module
    assert _network_offenders("services/update_fetch.py", "import socket")
    # still banned everywhere else: urllib itself (static, from, and dynamic)
    assert _network_offenders("services/other.py", "import urllib.request")
    assert _network_offenders("services/other.py", "from urllib import request")
    assert _network_offenders("services/other.py", 'import_module("socket")')
    # a same-basename file at a DIFFERENT path is NOT waved through
    assert _network_offenders("ui/update_fetch.py", "import urllib.request")


def test_INV8_no_network_package_in_runtime_deps():
    """The static scan can't see a banned package imported dynamically — so also
    assert none is declared as a runtime dependency (FIBR-0004 INV-8)."""
    import tomllib

    pyproject = Path(finbreak.__file__).parent.parent.parent / "pyproject.toml"
    deps = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
    # The distribution name at the head of each requirement (before any version
    # specifier / extra / marker).
    names = {
        re.split(r"[<>=!~ \[;]", dep, maxsplit=1)[0].strip().lower() for dep in deps
    }
    intruders = names & _BANNED_NETWORK
    assert not intruders, f"network package in runtime deps: {intruders}"


def test_complete_first_run_over_existing_vault_wipes_key(paths):
    """A first-run attempted over an existing vault (two instances racing) must
    still wipe the derived-key copy, not leave it for GC. (indie-review M-auth2)"""
    import finbreak.services.auth as auth_mod

    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # the vault now exists
    svc.lock()

    wiped: list[int] = []
    real = auth_mod._wipe

    def spy(buf):
        if buf:
            wiped.append(len(buf))
        real(buf)

    auth_mod._wipe = spy
    try:
        other = AuthService(*paths)
        with pytest.raises(VaultStateError):
            other.complete_first_run(b"\x01" * KEY_LEN, other.new_params(), "ZAR")
    finally:
        auth_mod._wipe = real
    assert KEY_LEN in wiped, "the derived key copy is wiped even when the guard fires"


def test_INV6_unlock_distinct_message_for_malformed_sidecar(qtbot, service, paths):
    """A malformed / below-floor KDF sidecar (KdfPolicyError) gets its own
    message, not the generic 'check your password' — a user with the correct
    password must be able to tell the difference. (indie-review M-auth1)"""
    from finbreak.ui.unlock import UnlockDialog

    _, sidecar_path = paths
    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    sidecar_path.write_text("{ not valid json")  # KdfPolicyError on load_params

    widget = UnlockDialog(service)
    qtbot.addWidget(widget)
    widget._password.setText(_PW.decode())
    with qtbot.waitSignal(widget.unlock_failed, timeout=5000):
        widget._unlock_button.click()
    message = widget._error.text()
    assert message != "", "a malformed sidecar shows a diagnostic message"
    assert "password" not in message.lower(), (
        "a malformed sidecar must not be reported as a wrong password"
    )


def test_unlock_wipes_password_on_load_failure(paths):
    """AuthService.unlock zeroes the password bytearray when load_params fails (a
    corrupt sidecar), so a failed unlock leaves no plaintext password in memory
    (FIBR-0064 / security-model INV-3)."""
    vault_path, sidecar_path = paths
    svc = AuthService(vault_path, sidecar_path)
    svc.first_run(bytearray(_PW), "ZAR")
    svc.lock()
    sidecar_path.write_text("not valid json{", encoding="utf-8")  # corrupt the sidecar
    pw = bytearray(_PW)
    with pytest.raises(KdfPolicyError):
        svc.unlock(pw)
    assert pw == bytearray(len(pw)), "the password buffer is zeroed on failure"


def test_INV6_unlock_shows_schema_message_on_newer_vault(qtbot, service, monkeypatch):
    """A vault written by a NEWER build raises SchemaVersionError on unlock; the
    dialog shows its own 'newer version' message (distinct from the wrong-password
    one) and emits unlock_failed. Driven via _on_derived to skip the real Argon2
    worker (FIBR-0064)."""
    from finbreak.errors import SchemaVersionError
    from finbreak.ui.unlock import UnlockDialog

    service.first_run(bytearray(_PW), "ZAR")
    service.lock()
    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)

    def _raise_newer(_raw):
        raise SchemaVersionError("vault schema version 99 is newer than this build")

    monkeypatch.setattr(service, "complete_unlock", _raise_newer)
    failed: list[int] = []
    dialog.unlock_failed.connect(lambda: failed.append(1))
    dialog._on_derived(b"\x00" * 32)  # simulate the worker delivering a derived key

    assert "newer version" in dialog._error.text().lower()
    assert failed == [1], "unlock_failed emitted, not unlocked"


def test_INV5_first_run_shows_message_on_create_failure(qtbot, service, monkeypatch):
    """If vault creation fails, FirstRunDialog surfaces a 'Could not create the
    vault' message instead of crashing the slot (FIBR-0064). State is seeded
    directly so the real Argon2 worker never spins."""
    from finbreak.ui.first_run import FirstRunDialog

    dialog = FirstRunDialog(service)
    qtbot.addWidget(dialog)
    dialog._pending_params = _params(bytes(SALT_LEN))  # what _on_submit would set
    dialog._pending_currency = "ZAR"

    def _boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(service, "complete_first_run", _boom)
    completed: list[int] = []
    dialog.completed.connect(lambda: completed.append(1))
    dialog._on_derived(b"\x00" * 32)  # worker delivers the key → complete_first_run

    assert "could not create the vault" in dialog._error.text().lower()
    assert completed == [], "completed is not emitted when creation fails"
