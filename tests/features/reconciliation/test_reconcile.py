"""FIBR-0177 — pure reconciliation core (`reconcile_account`).

Enforces tests/features/reconciliation/spec.md INV-1/4/6/7/12. No DB, no Qt —
synthetic closings + bridge sums only. Money is signed integer minor units
throughout (no ``Decimal``, exact comparison). These are the reproduce-first RED
tests: INV-1/INV-12 are written before ``services/reconciliation.py`` exists.
"""

import pytest

from finbreak.models import AccountReconciliation, ReconciliationStatus
from finbreak.services.reconciliation import reconcile_account

pytestmark = pytest.mark.features


def test_INV1_three_closings_bridged_exactly_reconcile() -> None:
    closings = [
        ("2026-01-31", 100_000),
        ("2026-02-28", 150_000),
        ("2026-03-31", 210_000),
    ]
    bridge_sums = [50_000, 60_000]  # each pair bridges exactly
    recon = reconcile_account(7, closings, bridge_sums)
    assert recon == AccountReconciliation(7, ReconciliationStatus.RECONCILED, 0, 0, 2)


def test_INV4_zero_and_one_closing_are_not_enough_data() -> None:
    # < 2 nodes → nothing to bridge; never raises; all three fields 0, not -1.
    for closings in ([], [("2026-01-31", 100_000)]):
        recon = reconcile_account(3, closings, [])
        assert recon == AccountReconciliation(
            3, ReconciliationStatus.NOT_ENOUGH_DATA, 0, 0, 0
        )
        assert recon.checked_pair_count == 0  # never a nonsensical -1


def test_INV6_one_minor_unit_gap_is_off() -> None:
    # Exact integer comparison — a single minor unit is not swallowed by tolerance.
    closings = [("2026-01-31", 100_000), ("2026-02-28", 150_001)]
    recon = reconcile_account(1, closings, [50_000])
    assert recon.status is ReconciliationStatus.OFF
    assert recon.discrepancy_minor == 1  # actual 150_001 - expected 150_000
    assert recon.off_pair_count == 1
    assert recon.checked_pair_count == 1


def test_INV7_rollup_fields_on_mixed_chain() -> None:
    # pair0 reconciles; pair1 off by +200; pair2 off by -50. Discrepancy is the
    # signed net; off_pair_count counts non-zero diffs; checked == nodes - 1.
    closings = [
        ("2026-01-31", 100_000),  # node0
        ("2026-02-28", 150_000),  # node1: expected 100_000+50_000 = 150_000, diff 0
        ("2026-03-31", 200_200),  # node2: expected 150_000+50_000 = 200_000, diff +200
        ("2026-04-30", 210_150),  # node3: expected 200_200+10_000 = 210_200, diff -50
    ]
    bridge_sums = [50_000, 50_000, 10_000]
    recon = reconcile_account(9, closings, bridge_sums)
    assert recon.status is ReconciliationStatus.OFF
    assert recon.discrepancy_minor == 150  # +200 + (-50)
    assert recon.off_pair_count == 2
    assert recon.checked_pair_count == 3


def test_INV12_offsetting_gaps_net_zero_still_off() -> None:
    # +100 gap then -100 gap → net 0 but two off pairs. Honesty rule: RECONCILED
    # iff EVERY diff is 0, not iff the net is 0.
    closings = [
        ("2026-01-31", 100_000),
        ("2026-02-28", 150_100),  # expected 150_000, diff +100
        ("2026-03-31", 200_000),  # expected 150_100+50_000 = 200_100, diff -100
    ]
    bridge_sums = [50_000, 50_000]
    recon = reconcile_account(5, closings, bridge_sums)
    assert recon.discrepancy_minor == 0
    assert recon.off_pair_count == 2
    assert recon.status is ReconciliationStatus.OFF
