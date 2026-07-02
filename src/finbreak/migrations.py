"""Forward-only schema migrations, run on vault open/create (FIBR-0005 INV-4).

The runner **owns its transaction**: with the vault's ``isolation_level=""`` the
DBAPI driver does not implicitly ``BEGIN`` around DDL, so an un-wrapped
``DROP``/``RENAME`` would autocommit and a mid-migration failure could not roll
back. Each step therefore wraps itself in an explicit ``BEGIN … COMMIT`` with a
``ROLLBACK`` on any exception — the explicit ``BEGIN`` as the step's first
statement (verified against sqlcipher3-binary 0.6.0). Forward-only: no
downgrade; a vault newer than this build is refused, not silently downgraded.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlcipher3 import dbapi2

from finbreak.errors import SchemaVersionError

log = logging.getLogger(__name__)

LATEST_SCHEMA_VERSION = 3

# Seed data written by the v1->v2 migration (D8) — NOT a UI string, so never
# run through tr(); the user renames it in the Accounts manager.
DEFAULT_ACCOUNT_NAME = "Default"
DEFAULT_ACCOUNT_TYPE = "current"

# Seed data written by the v2->v3 migration (FIBR-0006 D8) — the two Type roots
# and their default categories. Names are DATA, not UI strings: written to the
# DB, never run through tr(); the user renames them in the category manager.
# The root NAME is keyed by its stored CategoryKind token; the token identifies
# the root structurally (rename-/locale-safe), the name is a plain seed value.
CATEGORY_ROOT_NAMES = {"income": "Income", "expenditure": "Expenditure"}
DEFAULT_CATEGORIES = {
    "income": ["Salary", "Sales", "Interest", "Gifts", "Lottery", "Other income"],
    "expenditure": [
        "Groceries",
        "Fast food",
        "Bills & utilities",
        "Rent / Mortgage",
        "Transport",
        "Medical",
        "Entertainment",
        "Clothing",
        "Insurance",
        "Other expenditure",
    ],
}


def run_migrations(conn: dbapi2.Connection) -> None:
    """Bring ``conn`` up to ``LATEST_SCHEMA_VERSION``; a no-op when current."""
    current = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    if current > LATEST_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"vault schema version {current} is newer than this build supports "
            f"({LATEST_SCHEMA_VERSION}); upgrade finbreak"
        )
    for target in range(current + 1, LATEST_SCHEMA_VERSION + 1):
        _MIGRATIONS[target](conn)
        log.info("migrated schema to version %d", target)


def _migrate_to_v2(conn: dbapi2.Connection) -> None:
    """v1->v2: add ``accounts``, seed one Default, and rebuild ``transactions``
    with a required ``account_id`` foreign key, backfilling every existing row
    to the Default account. One atomic unit (INV-4)."""
    conn.execute("BEGIN")  # first statement — own the transaction (D2)
    try:
        conn.execute(
            "CREATE TABLE accounts("
            "id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "type TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        default_id = conn.execute(
            "INSERT INTO accounts(name, type, created_at) VALUES (?, ?, ?)",
            (DEFAULT_ACCOUNT_NAME, DEFAULT_ACCOUNT_TYPE, datetime.now(UTC).isoformat()),
        ).lastrowid
        # NOT NULL + REFERENCES can't be added by ALTER … ADD COLUMN, so rebuild
        # (SQLite docs "Making Other Kinds Of Table Schema Changes"), stamping
        # every prior row with the Default account's id.
        conn.execute(
            "CREATE TABLE transactions_new("
            "id INTEGER PRIMARY KEY, "
            "account_id INTEGER NOT NULL REFERENCES accounts(id), "
            "occurred_on TEXT NOT NULL, amount_minor INTEGER NOT NULL, "
            "description TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO transactions_new"
            "(id, account_id, occurred_on, amount_minor, description, created_at) "
            "SELECT id, ?, occurred_on, amount_minor, description, created_at "
            "FROM transactions",
            (default_id,),
        )
        conn.execute("DROP TABLE transactions")
        conn.execute("ALTER TABLE transactions_new RENAME TO transactions")
        conn.execute("UPDATE schema_version SET version = 2")
        conn.commit()
    except Exception:
        conn.rollback()  # undoes the DROP — leaves a re-openable v1 vault
        raise


def _migrate_to_v3(conn: dbapi2.Connection) -> None:
    """v2->v3: add the self-referential ``categories`` table and seed the two
    Type roots (Income/Expenditure) + their default categories. A ``CREATE`` +
    seed ``INSERT``s only — no table rebuild — but still one atomic unit
    (INV-4): with the vault's ``isolation_level=""`` the driver does not
    implicitly ``BEGIN`` around the ``CREATE`` (DDL), so a failure mid-seed
    could otherwise leave an empty ``categories`` table (a half-migrated
    v2.5). The explicit ``BEGIN`` — the step's first statement, discrete
    ``execute`` calls throughout so the runner owns the transaction (D2) —
    makes it all-or-nothing: either v3 with the tree fully seeded, or still v2
    with no ``categories`` table."""
    now = datetime.now(UTC).isoformat()
    conn.execute("BEGIN")  # first statement — own the transaction (D2)
    try:
        conn.execute(
            "CREATE TABLE categories("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER REFERENCES categories(id), "
            "name TEXT NOT NULL, kind TEXT, created_at TEXT NOT NULL)"
        )
        for kind, root_name in CATEGORY_ROOT_NAMES.items():
            root_id = conn.execute(
                "INSERT INTO categories(parent_id, name, kind, created_at) "
                "VALUES (NULL, ?, ?, ?)",
                (root_name, kind, now),
            ).lastrowid
            for child_name in DEFAULT_CATEGORIES[kind]:
                conn.execute(
                    "INSERT INTO categories(parent_id, name, kind, created_at) "
                    "VALUES (?, ?, NULL, ?)",
                    (root_id, child_name, now),
                )
        conn.execute("UPDATE schema_version SET version = 3")
        conn.commit()
    except Exception:
        conn.rollback()  # undoes the CREATE — leaves a re-openable v2 vault
        raise


_MIGRATIONS = {2: _migrate_to_v2, 3: _migrate_to_v3}
