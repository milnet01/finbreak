"""FIBR-0177 — reconciliation adds no schema change of its own (INV-8).

Reconciliation is read-only analytics over FIBR-0171's v11 `closing_balance_minor`
column + the existing `sum_after` primitive; it registers no migration of its own.
The schema has since advanced to **v12** via FIBR-0172 (the `alert_dismissals`
table — unrelated to reconciliation), so this guard can no longer be an absolute
"unchanged at 11" pin. It now asserts the current latest (v12) and that no
*unregistered next* version (v13) exists — the same "reconciliation introduced no
migration of its own" intent, expressed against a moving latest.
"""

import pytest

from finbreak.migrations import _MIGRATIONS, LATEST_SCHEMA_VERSION

pytestmark = pytest.mark.features


def test_INV8_schema_version_at_current_latest_v12() -> None:
    assert LATEST_SCHEMA_VERSION == 12


def test_INV8_no_unregistered_next_migration() -> None:
    assert LATEST_SCHEMA_VERSION + 1 not in _MIGRATIONS
