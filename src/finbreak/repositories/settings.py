"""SettingsRepository — a generic key→value accessor over the vault ``settings``
table (FIBR-0055 D3).

The ``settings`` table (``key TEXT PRIMARY KEY, value TEXT NOT NULL``) has existed
since v1 (FIBR-0004) and already holds ``base_currency`` + ``minor_unit_exponent``.
This repository is the seam FIBR-0055's ``auto_lock_minutes`` setting reads/writes
through; ``set`` owns its own commit (a settings change is a standalone write, not
part of a larger transaction).
"""

from __future__ import annotations

from sqlcipher3 import dbapi2


class SettingsRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def get(self, key: str) -> str | None:
        """The stored value for ``key``, or ``None`` when the key is absent."""
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row is not None else None

    def set(self, key: str, value: str) -> None:
        """Upsert ``key`` → ``value`` and commit (standalone write). Uses SQLite's
        ``ON CONFLICT`` upsert so an existing key is updated in place."""
        self._conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()
