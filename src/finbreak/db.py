"""Shared low-level database helpers.

``owned_transaction`` is the single owned-transaction wrapper used by every
service write **and** every migration step (FIBR-0066), so the atomicity
contract lives in exactly one place — the explicit ``BEGIN`` as the block's
first statement, ``COMMIT`` on success, ``ROLLBACK`` + re-raise on any
exception (leaving the vault re-openable). The vault runs at
``isolation_level=""`` (manual-commit), so DDL and multi-statement writes need
this explicit boundary; centralising it removes the risk a new call site copies
the boilerplate with a subtly wrong exception class.

Deliberately a free function taking a bare ``Connection`` (not a ``Vault``
method): ``migrations.py`` runs before/independently of ``Vault`` and imports
this, while ``vault.py`` imports ``migrations`` — a ``Vault`` method would make
that a cycle.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlcipher3 import dbapi2


@contextmanager
def owned_transaction(conn: dbapi2.Connection) -> Iterator[dbapi2.Connection]:
    """Run the ``with`` body as one owned ``BEGIN … COMMIT``; ``ROLLBACK`` and
    re-raise on any exception. The ``BEGIN`` is the block's first statement, so
    the caller must not ``execute`` on ``conn`` before entering the block."""
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
