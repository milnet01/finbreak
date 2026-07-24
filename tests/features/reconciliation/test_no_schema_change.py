"""FIBR-0177 — no schema change (INV-8).

Reconciliation is read-only analytics over FIBR-0171's v11 `closing_balance_minor`
column + the existing `sum_after` primitive. It must NOT bump the schema: the
latest version stays 11 and there is no `_migrate_to_v12` registered. This guard
mirrors FIBR-0171's `test_migration_v11.py::test_INV9_latest_schema_version_is_11`
so a stray migration for this feature is caught.
"""

import pytest

from finbreak.migrations import _MIGRATIONS, LATEST_SCHEMA_VERSION

pytestmark = pytest.mark.features


def test_INV8_schema_version_unchanged_at_11() -> None:
    assert LATEST_SCHEMA_VERSION == 11


def test_INV8_no_v12_migration_registered() -> None:
    assert 12 not in _MIGRATIONS
