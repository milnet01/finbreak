"""AlertDismissalRepository — the ``alert_dismissals`` dismissal store (FIBR-0172 D5).

Persistence only; ``AlertService`` is the sole producer of keys. Mirrors the
``recurring_decisions`` / ``transfer_pairs`` decision-table idiom (ADR-0006): a small
table, ``UNIQUE`` on the identity, one insert per dismissal. Each write is one
own-commit, matching ``RecurringRepository.set_decision``. The column list is written
literally in each query (never interpolated) so the SQL is fixed text (bandit B608).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlcipher3 import dbapi2


class AlertDismissalRepository:
    def __init__(self, connection: dbapi2.Connection):
        self._conn = connection

    def dismissed_keys(self) -> set[str]:
        """Every dismissed alert key — the set ``AlertService.alerts`` filters by."""
        rows = self._conn.execute("SELECT alert_key FROM alert_dismissals").fetchall()
        return {row[0] for row in rows}

    def dismiss(self, alert_key: str) -> None:
        """Record a dismissal, idempotently (INV-12): ``INSERT … ON CONFLICT DO
        NOTHING`` so a double-dismiss is one row and never raises. One INSERT +
        commit, mirroring ``RecurringRepository.set_decision``. ``created_at`` keeps
        the first insert's stamp on a repeat (the ``DO NOTHING`` leaves the row)."""
        self._conn.execute(
            "INSERT INTO alert_dismissals(alert_key, created_at) VALUES (?, ?) "
            "ON CONFLICT(alert_key) DO NOTHING",
            (alert_key, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    def clear(self, alert_key: str) -> None:
        """Un-dismiss a key (for un-dismiss / tests). A silent no-op on an absent
        key. One DELETE + commit."""
        self._conn.execute(
            "DELETE FROM alert_dismissals WHERE alert_key = ?", (alert_key,)
        )
        self._conn.commit()
