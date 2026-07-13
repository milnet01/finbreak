"""Repository layer — the only code that speaks SQL to the vault connection."""

from __future__ import annotations

from sqlcipher3 import dbapi2


def last_insert_id(cursor: dbapi2.Cursor) -> int:
    """The rowid of the just-executed INSERT. ``Cursor.lastrowid`` is typed
    ``int | None`` (None before any INSERT), but immediately after an INSERT on a
    rowid table it is always set — narrow it once here instead of at every
    ``add``-style call site. The ``None`` branch is unreachable in that use."""
    row_id = cursor.lastrowid
    if row_id is None:  # pragma: no cover - unreachable right after an INSERT
        raise RuntimeError("INSERT did not set a rowid")
    return row_id
