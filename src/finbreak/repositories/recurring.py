"""RecurringRepository — the detector's transaction feed + the ``recurring_decisions``
decision store (FIBR-0142).

``_RecurRow`` (the detector's lean per-transaction input) is defined **here**, its
producer, rather than in ``services/recurring.py`` where the spec's signature block
sketched it: ``RecurringService`` imports this repository, so defining the row type
in the service would make the repository import the service back — a circular
import. ``services.recurring`` re-exports ``_RecurRow``, so its public path is
unchanged. Each decision write is one per-commit upsert keyed on ``(direction,
merchant_key)`` so a confirm/dismiss survives re-imports (INV-8) — the row is about
a payee *stream*, not specific txns, hence no FK and nothing to cascade.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

from sqlcipher3 import dbapi2


class _RecurRow(NamedTuple):
    """The lean per-transaction input the detector consumes (FIBR-0142 D2)."""

    id: int
    occurred_on: str
    amount_minor: int
    description: str


class RecurringRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def recurring_rows(self) -> list[_RecurRow]:
        """Every transaction as a detector row — full history, all accounts, no
        account/window filter (D2/INV-13). The read stays dumb; the detector groups,
        qualifies, and filters."""
        rows = self._conn.execute(
            "SELECT id, occurred_on, amount_minor, description FROM transactions"
        ).fetchall()
        return [_RecurRow(*row) for row in rows]

    def decisions(self) -> dict[tuple[str, str], str]:
        """Every stored decision as ``(direction, merchant_key) -> status``."""
        rows = self._conn.execute(
            "SELECT direction, merchant_key, status FROM recurring_decisions"
        ).fetchall()
        return {(row[0], row[1]): row[2] for row in rows}

    def set_decision(self, direction: str, merchant_key: str, status: str) -> None:
        """Upsert one decision on ``(direction, merchant_key)`` (INV-8) — a fresh
        confirm/dismiss, or a status flip on the existing row (``UNIQUE`` is the
        conflict target). One INSERT-or-UPDATE + commit. On a flip only ``status``
        changes — ``created_at`` keeps its original insert stamp (provenance,
        unchanged on conflict-update per the spec data model)."""
        self._conn.execute(
            "INSERT INTO recurring_decisions"
            "(direction, merchant_key, status, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(direction, merchant_key) "
            "DO UPDATE SET status = excluded.status",
            (direction, merchant_key, status, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    def clear_decision(self, direction: str, merchant_key: str) -> None:
        """Delete the decision for a key (reset → back to suggested, INV-8). A silent
        no-op on an absent key."""
        self._conn.execute(
            "DELETE FROM recurring_decisions WHERE direction = ? AND merchant_key = ?",
            (direction, merchant_key),
        )
        self._conn.commit()
