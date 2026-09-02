"""FIBR-0177 — reconciliation adds no schema change of its own (INV-8).

Reconciliation is read-only analytics over FIBR-0171's v11 `closing_balance_minor`
column + the existing `sum_after` primitive; it registers no migration of its own.
The schema has since advanced to **v14** — via FIBR-0172 (`alert_dismissals`),
FIBR-0193 (the `accounts.account_number` / `note` columns) and FIBR-0327 (the
transfer-candidate index), none of them reconciliation's — so this guard can no
longer be an absolute "unchanged at 11" pin. It asserts the current latest and
that no *unregistered next* version exists — the same "reconciliation introduced
no migration of its own" intent, expressed against a moving latest.
"""

import pytest

from finbreak.migrations import _MIGRATIONS, LATEST_SCHEMA_VERSION

pytestmark = pytest.mark.features


def test_INV8_schema_version_at_current_latest_v14() -> None:
    assert LATEST_SCHEMA_VERSION == 14


def test_INV8_no_unregistered_next_migration() -> None:
    assert LATEST_SCHEMA_VERSION + 1 not in _MIGRATIONS
