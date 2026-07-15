"""FIBR-0142 — recurring money detection (suggest-then-confirm).

Enforces tests/features/recurring/spec.md. The pure `detect_recurring` detector +
helpers are tested directly with synthetic `_RecurRow`s (no vault); the
`RecurringService`, the v8->v9 migration, and the Recurring tab arrive with their
slices. Every on-disk vault uses `tmp_path`; no test touches the network or real
financial data (testing.md § 6).
"""

from datetime import date
from decimal import Decimal

import pytest

from finbreak.models import Cadence, Direction
from finbreak.services.recurring import _RecurRow, detect_recurring

pytestmark = pytest.mark.features

_TODAY = date(2026, 7, 15)
_EXP = 2  # ZAR minor-unit exponent (cents)


def _row(
    row_id: int,
    occurred_on: str,
    amount_minor: int,
    description: str = "Netflix REF123",
) -> _RecurRow:
    return _RecurRow(row_id, occurred_on, amount_minor, description)


# --------------------------------------------------------------------------- #
# pure detector — empty / degenerate inputs
# --------------------------------------------------------------------------- #
def test_empty_rows_yield_no_items() -> None:
    assert detect_recurring([], _TODAY, _EXP, frozenset()) == []


# --------------------------------------------------------------------------- #
# pure detector — the clean qualifying case (drives grouping/median/cadence/sort)
# --------------------------------------------------------------------------- #
def test_clean_monthly_out_series_qualifies() -> None:
    rows = [
        _row(1, "2026-01-05", -19900),
        _row(2, "2026-02-05", -19900),
        _row(3, "2026-03-05", -19900),
        _row(4, "2026-04-05", -19900),
        _row(5, "2026-05-05", -19900),
    ]
    items = detect_recurring(rows, date(2026, 5, 20), _EXP, frozenset())
    assert len(items) == 1
    it = items[0]
    assert it.direction == Direction.OUT
    assert it.cadence == Cadence.MONTHLY
    assert it.occurrences == 5
    assert it.amount == Decimal("199.00")
    assert it.monthly_equivalent == Decimal("199.00")  # monthly factor == 1
    assert it.merchant == "Netflix"
    assert it.merchant_key == "netflix"  # normalise_text(merchant_name(...))
    assert it.first_seen == date(2026, 1, 5)
    assert it.last_seen == date(2026, 5, 5)
    assert it.next_expected == date(2026, 6, 5)
    assert it.txn_ids == (1, 2, 3, 4, 5)
