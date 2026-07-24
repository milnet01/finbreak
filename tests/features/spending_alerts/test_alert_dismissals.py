"""FIBR-0172 — AlertDismissalRepository (schema v12 ``alert_dismissals``).

Enforces spec INV-12 on a real (tmp_path) v12 vault: ``dismiss`` is idempotent (a
double-dismiss is one row, no error), ``dismissed_keys()`` round-trips, and
``clear`` removes. No network, no real financial data (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import _PW
from finbreak.repositories.alert_dismissals import AlertDismissalRepository
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # migrates straight to latest (v12)
    yield svc
    svc.lock()


def _rows(conn) -> int:
    return conn.execute("SELECT count(*) FROM alert_dismissals").fetchone()[0]


def test_INV12_dismiss_round_trips_via_dismissed_keys(service) -> None:
    repo = AlertDismissalRepository(service.vault.connection)
    assert repo.dismissed_keys() == set()
    repo.dismiss("new_recurring:netflix")
    repo.dismiss("category_spike:7:2026-06")
    assert repo.dismissed_keys() == {
        "new_recurring:netflix",
        "category_spike:7:2026-06",
    }


def test_INV12_dismiss_is_idempotent(service) -> None:
    conn = service.vault.connection
    repo = AlertDismissalRepository(conn)
    repo.dismiss("missed_debit:gym:2026-06-01")
    repo.dismiss("missed_debit:gym:2026-06-01")  # double-dismiss: one row, no error
    assert _rows(conn) == 1
    assert repo.dismissed_keys() == {"missed_debit:gym:2026-06-01"}


def test_INV12_clear_removes_the_key(service) -> None:
    repo = AlertDismissalRepository(service.vault.connection)
    repo.dismiss("new_recurring:netflix")
    repo.dismiss("new_recurring:spotify")
    repo.clear("new_recurring:netflix")
    assert repo.dismissed_keys() == {"new_recurring:spotify"}
    repo.clear("new_recurring:absent")  # a silent no-op on an absent key
    assert repo.dismissed_keys() == {"new_recurring:spotify"}
