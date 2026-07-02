"""FIBR-0004 — the security-spine vertical slice. Enforces tests/features/vault/spec.md.

The crypto/vault/service/repository layers are unit- and feature-tested
headless; the two UI round-trips (INV-5 first-run widget, INV-6 unlock widget +
main window) use the pytest-qt `qtbot` fixture. Every on-disk vault lives under
`tmp_path`; no test touches the network or real financial data (testing.md § 6).
"""

import ast
import json
import logging
from decimal import Decimal
from pathlib import Path

import pytest
from sqlcipher3.dbapi2 import DatabaseError

import finbreak
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
from finbreak.models import FORMAT_VERSION, KdfParams
from finbreak.services.auth import AuthService
from finbreak.services.transactions import (
    TransactionService,
    parse_transaction,
    to_display_decimal,
)
from finbreak.vault import Vault

# A throwaway, obviously-fake password used only in-process by the tests. Not a
# secret and guards nothing (security-model INV-6). bytes so each use can build
# a fresh wipeable bytearray.
_PW = b"correct horse battery staple"


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
def paths(tmp_path) -> tuple[Path, Path]:
    return tmp_path / "vault.db", tmp_path / "vault.kdf.json"


@pytest.fixture
def service(paths) -> AuthService:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


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


def test_INV3_exit_handler_wipes_and_is_noop_when_locked(service):
    service.first_run(bytearray(_PW), "ZAR")
    key_buffer = service._key
    service.on_about_to_quit()
    assert bytes(key_buffer) == bytes(len(key_buffer))
    service.on_about_to_quit()  # already locked — must be a no-op, not a crash


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
        raise RuntimeError("simulated failure after INSERT, before commit")

    monkeypatch.setattr(TransactionRepository, "_commit", boom)
    with pytest.raises(RuntimeError):
        TransactionService(service._vault).add_transaction(
            "2026-07-01", "-12.34", "coffee"
        )

    service.lock()
    service.unlock(bytearray(_PW))
    rows = TransactionService(service._vault).list_transactions()
    assert len(rows) == 0, f"a rolled-back INSERT must be invisible; found {len(rows)}"


def test_INV4a_money_round_trips_exactly(service):
    service.first_run(bytearray(_PW), "ZAR")
    txs = TransactionService(service._vault)
    txs.add_transaction("2026-07-01", "-12.34", "coffee")

    rows = txs.list_transactions()
    assert len(rows) == 1
    transaction, display = rows[0]
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
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 1
    assert vault_path.exists() and sidecar_path.exists()


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
    TransactionService(service._vault).add_transaction("2026-07-01", "-12.34", "coffee")
    service.lock()

    assert service.unlock(bytearray(b"the wrong password")) is False
    assert service._key is None, "a wrong password retains no key"

    assert service.unlock(bytearray(_PW)) is True
    assert len(TransactionService(service._vault).list_transactions()) == 1
    service.lock()
    assert service._key is None


def test_INV6_unlock_widget_roundtrip(qtbot, service):
    from finbreak.ui.unlock import UnlockWidget

    service.first_run(bytearray(_PW), "ZAR")
    TransactionService(service._vault).add_transaction("2026-07-01", "-12.34", "coffee")
    service.lock()

    widget = UnlockWidget(service)
    qtbot.addWidget(widget)

    widget._password.setText("the wrong password")
    with qtbot.waitSignal(widget.unlock_failed, timeout=5000):
        widget._unlock_button.click()
    assert service._key is None
    assert widget._error.text() != "", "a failed unlock shows a message"

    widget._password.setText(_PW.decode())
    with qtbot.waitSignal(widget.unlocked, timeout=5000):
        widget._unlock_button.click()
    assert service._key is not None


def test_INV6_main_window_lists_saved_transaction(qtbot, service):
    from finbreak.ui.main_window import MainWindow

    service.first_run(bytearray(_PW), "ZAR")
    TransactionService(service._vault).add_transaction("2026-07-01", "-12.34", "coffee")

    window = MainWindow(service)
    qtbot.addWidget(window)
    assert window._table.rowCount() == 1, "the saved transaction appears in the table"


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
            "2026-07-01", "-12.34", "coffee"
        )
        service.lock()
        service.unlock(bytearray(_PW))
        service.lock()
        service.unlock(bytearray(b"the wrong password"))

    messages = [record.getMessage() for record in caplog.records]
    joined = "\n".join(messages)
    assert password not in joined, "the master password must never be logged"
    assert "12.34" not in joined, "transaction amounts must not be logged"
    assert messages, "the cycle must emit at least one non-secret lifecycle line"


@pytest.mark.skipif(
    not hasattr(__import__("os"), "getuid"), reason="POSIX mode bits only"
)
def test_INV7_vault_and_sidecar_are_owner_only(service, paths):
    vault_path, sidecar_path = paths
    service.first_run(bytearray(_PW), "ZAR")
    assert vault_path.stat().st_mode & 0o777 == 0o600
    assert sidecar_path.stat().st_mode & 0o777 == 0o600


# --------------------------------------------------------------------------- #
# INV-8 — no network dependency introduced
# --------------------------------------------------------------------------- #
def test_INV8_no_network_imports_under_src():
    banned = {"socket", "http", "urllib", "requests", "ftplib"}
    package_root = Path(finbreak.__file__).parent
    offenders: list[str] = []
    for py in package_root.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [
                    f"{py.name}: import {alias.name}"
                    for alias in node.names
                    if alias.name.split(".")[0] in banned
                ]
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in banned:
                    offenders.append(f"{py.name}: from {node.module}")
    assert not offenders, f"network imports found under src/finbreak/: {offenders}"
