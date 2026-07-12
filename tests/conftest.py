"""Shared pytest setup + cross-suite vault fixtures.

Force Qt's offscreen platform before any QApplication is created, so the
GUI-touching tests run on a headless CI runner with no display. Set at import
time — pytest imports conftest before collecting tests or creating the
pytest-qt `qapp`.

Also hosts the raw **v1-vault** builder + keyed-reopen helper shared by the
accounts (FIBR-0005) and categories (FIBR-0006) migration suites: a v1 vault is
the upgrade-path fixture, and `Vault.create()` can no longer produce one (it now
migrates a fresh vault straight to the latest schema). Kept here as the single
copy (coding.md § 1.3 — a second call-site is the trigger).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402
from sqlcipher3 import dbapi2  # noqa: E402

from finbreak.crypto import KEY_LEN, SALT_LEN, derive_key  # noqa: E402
from finbreak.migrations import (  # noqa: E402
    _migrate_to_v2,
    _migrate_to_v3,
    _migrate_to_v4,
    _migrate_to_v5,
    _migrate_to_v6,
    _migrate_to_v7,
)
from finbreak.models import FORMAT_VERSION, KdfParams  # noqa: E402
from finbreak.services.auth import (  # noqa: E402
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
)

# The test master password, shared by every migration/vault fixture.
_PW = b"correct horse battery staple"


@pytest.fixture
def paths(tmp_path) -> tuple[Path, Path]:
    """The ``(vault, sidecar)`` path pair every suite builds an ``AuthService`` /
    ``Vault`` from — was copy-pasted into ~11 feature suites (FIBR-0062)."""
    return tmp_path / "vault.db", tmp_path / "vault.kdf.json"


class StandInVault:
    """A minimal ``Vault`` stand-in exposing only ``.connection``, so a service can
    be driven against a wedged connection in the atomicity/rollback tests — was
    re-declared in the import + statements suites (FIBR-0062)."""

    def __init__(self, connection: dbapi2.Connection):
        self._connection = connection

    @property
    def connection(self) -> dbapi2.Connection:
        return self._connection


def _acct(service) -> int:
    """The seeded/first account's id — the ``account_id`` the import + statement
    suites stamp fixtures onto. Was copy-pasted into 5 suites (FIBR-0062)."""
    from finbreak.services.accounts import AccountService

    return AccountService(service.vault).list_accounts()[0].id


def _pump_deferred_delete() -> None:
    """Flush a same-level ``deleteLater()``: a bare ``processEvents()`` does not
    reliably do it, but ``sendPostedEvents`` with ``DeferredDelete`` does (INV-4a).
    Was copy-pasted into 3 GUI suites (FIBR-0062)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def raising_conn(real, trigger: str, message: str, *, on: str = "execute"):
    """A connection proxy that raises ``RuntimeError(message)`` when ``trigger``
    appears in the SQL of an ``on`` call (``"execute"`` or ``"executemany"``) and
    delegates every other attribute to ``real``. The shared atomicity-rollback
    wedge — was a bespoke ``_FailAt*`` class per test (FIBR-0062)."""

    class _Raising:
        def __getattr__(self, name):
            return getattr(real, name)

    proxy = _Raising()

    def _guard(sql, *a, **k):
        if trigger in sql:
            raise RuntimeError(message)
        return getattr(real, on)(sql, *a, **k)

    setattr(proxy, on, _guard)
    return proxy


@pytest.fixture(autouse=True)
def window_ini(tmp_path, monkeypatch):
    """Redirect the window-geometry INI to tmp for EVERY test so no UI test writes
    to the real per-user data dir (``~/.local/share/finbreak/window.ini``).

    Autouse + suite-wide: ``MainWindow`` reads/writes ``paths.window_settings_path()``
    on construct + close, so any test that builds a ``MainWindow`` would otherwise
    pollute the real data dir (and read stale host geometry — a non-deterministic
    ``_initial_tab``). The settings + statements suites each carried a private copy
    of this fixture; app_shell + vault did not, and leaked. Promoted here so every
    suite is isolated automatically. Returns the path for tests that read the INI.
    """
    ini = tmp_path / "window.ini"
    monkeypatch.setattr("finbreak.paths.window_settings_path", lambda: ini)
    return ini


class PickerStub(QDialog):
    """Real QDialog stand-in for CategoryPickerDialog: auto-accepts (or rejects) on
    show() so the async ``_apply_category`` slot runs synchronously through
    ``show_modal``'s real setModal/accepted/finished wiring (FIBR-0065 INV-5). Shared
    by the categorisation + transactions_tab suites (FIBR-0012 relocated the
    set-category flow to the Transactions tab)."""

    def __init__(self, parent, selected_id, accept):
        super().__init__(parent)
        self._selected_id = selected_id
        self._accept = accept

    def show(self):
        super().show()
        self.accept() if self._accept else self.reject()

    def selected_category_id(self):
        return self._selected_id


class RuleStub(QDialog):
    """Real QDialog stand-in for RuleEditDialog (same auto-drive as ``PickerStub``).
    Shared by the categorisation (Rules tab) + transactions_tab (learn) suites."""

    def __init__(self, parent, pattern, category_id, accept):
        super().__init__(parent)
        self._pattern = pattern
        self._category_id = category_id
        self._accept = accept

    def show(self):
        super().show()
        self.accept() if self._accept else self.reject()

    def pattern(self):
        return self._pattern

    def selected_category_id(self):
        return self._category_id


def stub_picker(monkeypatch, ui_mod, selected_id, accept=True):
    """Patch ``ui_mod.CategoryPickerDialog`` with an auto-driven ``PickerStub``."""
    monkeypatch.setattr(
        ui_mod,
        "CategoryPickerDialog",
        lambda leaves, current, parent=None: PickerStub(parent, selected_id, accept),
    )


def spy_learning(monkeypatch, ui_mod, *, accept, ret_pattern="", ret_cat=None):
    """Patch ``ui_mod.RuleEditDialog`` with a ``RuleStub`` and return a call log, so a
    test can assert whether the learn-a-rule offer was shown."""
    calls: list[bool] = []

    def factory(leaves, description, category_id, parent=None):
        calls.append(True)
        return RuleStub(parent, ret_pattern, ret_cat, accept)

    monkeypatch.setattr(ui_mod, "RuleEditDialog", factory)
    return calls


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


def keyed_connection(vault_path: Path, salt: bytes) -> dbapi2.Connection:
    """Reopen a raw keyed SQLCipher connection on an existing vault file (the
    reopen a migration test needs after ``build_v1_vault`` closes its own)."""
    key = derive_key(bytearray(_PW), salt, _params(salt))
    conn = dbapi2.connect(str(vault_path))
    conn.execute(f"PRAGMA key = \"x'{bytes(key).hex()}'\"")
    return conn


def build_v1_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """Write a raw FIBR-0004-shape v1 vault (schema_version=1, account-less
    transactions) + its sidecar, WITHOUT Vault.create() (which now migrates to
    the latest schema). The migration-suite upgrade-path fixture. Closes its own
    connection — a caller needing one reopens via ``keyed_connection``."""
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


def build_v2_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """A raw v2 vault: the v1 baseline taken through the real ``_migrate_to_v2``
    (the shape ``Vault.create()`` can no longer produce — it now migrates to the
    latest schema). Closes its connection; callers reopen via ``keyed_connection``.
    Shared by the categories (FIBR-0006) and import (FIBR-0007) migration suites
    past the Rule-of-Three (coding.md § 1.3)."""
    build_v1_vault(vault_path, sidecar_path, salt, rows)
    conn = keyed_connection(vault_path, salt)
    _migrate_to_v2(conn)  # v1 -> v2 (accounts + account_id)
    conn.close()


def build_v3_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """A raw v3 vault: ``build_v2_vault`` taken one more step through the real
    ``_migrate_to_v3`` (categories tree seeded). The v3->v4 migration suite's
    upgrade-path fixture (FIBR-0007 D12)."""
    build_v2_vault(vault_path, sidecar_path, salt, rows)
    conn = keyed_connection(vault_path, salt)
    _migrate_to_v3(conn)  # v2 -> v3 (categories tree)
    conn.close()


def build_v4_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """A raw v4 vault: ``build_v3_vault`` taken one more step through the real
    ``_migrate_to_v4`` (the two import tables). The v4->v5 migration suite's
    upgrade-path fixture (FIBR-0009 INV-8)."""
    build_v3_vault(vault_path, sidecar_path, salt, rows)
    conn = keyed_connection(vault_path, salt)
    _migrate_to_v4(conn)  # v3 -> v4 (import_profiles + statement_periods)
    conn.close()


def build_v5_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """A raw v5 vault: ``build_v4_vault`` taken one more step through the real
    ``_migrate_to_v5`` (the nullable ``accounts.statement_pdf_password`` column).
    The v5->v6 migration suite's upgrade-path fixture (FIBR-0052 INV-13a)."""
    build_v4_vault(vault_path, sidecar_path, salt, rows)
    conn = keyed_connection(vault_path, salt)
    _migrate_to_v5(conn)  # v4 -> v5 (statement_pdf_password)
    conn.close()


def build_v6_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """A raw v6 vault: ``build_v5_vault`` taken one more step through the real
    ``_migrate_to_v6`` (the nullable ``transactions.statement_period_id`` stamp).
    The v6->v7 migration suite's upgrade-path fixture (FIBR-0010 INV-15)."""
    build_v5_vault(vault_path, sidecar_path, salt, rows)
    conn = keyed_connection(vault_path, salt)
    _migrate_to_v6(conn)  # v5 -> v6 (statement_period_id)
    conn.close()


def build_v7_vault(vault_path: Path, sidecar_path: Path, salt: bytes, rows) -> None:
    """A raw v7 vault: ``build_v6_vault`` taken one more step through the real
    ``_migrate_to_v7`` (the category link + ``categorization_rules`` table). The
    v7->v8 migration suite's upgrade-path fixture (FIBR-0011 INV-9)."""
    build_v6_vault(vault_path, sidecar_path, salt, rows)
    conn = keyed_connection(vault_path, salt)
    _migrate_to_v7(conn)  # v6 -> v7 (category_id + category_source + rules)
    conn.close()
