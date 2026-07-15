"""FIBR-0142 — recurring money detection (suggest-then-confirm).

Enforces tests/features/recurring/spec.md. The pure `detect_recurring` detector +
helpers are tested directly with synthetic `_RecurRow`s (no vault); the
`RecurringService`, the v8->v9 migration, and the Recurring tab arrive with their
slices. Every on-disk vault uses `tmp_path`; no test touches the network or real
financial data (testing.md § 6).
"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest

from conftest import _PW, build_v8_vault, keyed_connection, raising_conn
from finbreak.crypto import SALT_LEN
from finbreak.migrations import LATEST_SCHEMA_VERSION, run_migrations
from finbreak.models import Cadence, Direction, RecurringSummary
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.recurring import RecurringRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.recurring import (
    RecurringService,
    _add_cadence,
    _monthly_equivalent,
    _RecurRow,
    detect_recurring,
    nominal_interval_days,
)
from finbreak.services.transfer_detection import TransferDetectionService

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


# --------------------------------------------------------------------------- #
# pure detector — regression locks for the branches the clean case doesn't hit.
# The detector is already implemented (slice 1); these verify each spec INV
# branch and guard against regression. They are NOT red-first-driving new code.
# --------------------------------------------------------------------------- #
def _monthly(amounts: list[int]) -> list[_RecurRow]:
    """A monthly OUT series on the 10th, one row per amount (id = 1-based)."""
    return [_row(i + 1, f"2026-{i + 1:02d}-10", amt) for i, amt in enumerate(amounts)]


# INV-6 — below the ≥3 minimum: a 2× group never qualifies.
def test_rejects_below_min_occurrences() -> None:
    rows = [_row(1, "2026-01-10", -19900), _row(2, "2026-02-10", -19900)]
    assert detect_recurring(rows, date(2026, 2, 20), _EXP, frozenset()) == []


# INV-6 — ±10% integer-exact boundary: 110 accept / 111 reject, 90 / 89.
@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ([-10000, -10000, -11000], 1),  # +10% exactly → accept
        ([-10000, -10000, -11100], 0),  # +11% → reject
        ([-9000, -10000, -10000], 1),  # -10% exactly → accept
        ([-8900, -10000, -10000], 0),  # -11% → reject
    ],
)
def test_amount_tolerance_boundaries(amounts: list[int], expected: int) -> None:
    items = detect_recurring(_monthly(amounts), date(2026, 3, 20), _EXP, frozenset())
    assert len(items) == expected


# INV-6 — 3 members but only 2 distinct dates → 1 non-zero gap → rejected.
def test_rejects_two_distinct_dates() -> None:
    rows = [
        _row(1, "2026-01-10", -19900),
        _row(2, "2026-01-10", -19900),
        _row(3, "2026-02-10", -19900),
    ]
    assert detect_recurring(rows, date(2026, 2, 20), _EXP, frozenset()) == []


# INV-6 — a same-day duplicate is tolerated: the zero gap is discarded and the
# remaining gaps still classify (4 members, 3 distinct monthly dates).
def test_same_day_duplicate_tolerated() -> None:
    rows = [
        _row(1, "2026-01-10", -19900),
        _row(2, "2026-01-10", -19900),  # same-day duplicate
        _row(3, "2026-02-10", -19900),
        _row(4, "2026-03-10", -19900),
    ]
    items = detect_recurring(rows, date(2026, 3, 20), _EXP, frozenset())
    assert len(items) == 1
    assert items[0].cadence == Cadence.MONTHLY
    assert items[0].occurrences == 4


# INV-6 — gaps spanning two valid bands (7, 7, 30) are not one cadence → reject.
def test_rejects_mixed_valid_bands() -> None:
    rows = [
        _row(1, "2026-01-01", -19900),
        _row(2, "2026-01-08", -19900),  # +7
        _row(3, "2026-01-15", -19900),  # +7
        _row(4, "2026-02-14", -19900),  # +30
    ]
    assert detect_recurring(rows, date(2026, 2, 20), _EXP, frozenset()) == []


# INV-6 — a gap in no band (20 days, between fortnight and month) disqualifies.
def test_rejects_dead_zone_gap() -> None:
    rows = [
        _row(1, "2026-01-01", -19900),
        _row(2, "2026-01-21", -19900),  # +20 → dead zone
        _row(3, "2026-02-10", -19900),  # +20 → dead zone
    ]
    assert detect_recurring(rows, date(2026, 2, 20), _EXP, frozenset()) == []


# INV-7 — activeness: a monthly group stale by > 2·30 days drops; ≤ 60 keeps.
def test_activeness_drops_stale_keeps_recent() -> None:
    rows = _monthly([-19900, -19900, -19900])  # last_seen 2026-03-10
    assert detect_recurring(rows, date(2026, 7, 15), _EXP, frozenset()) == []  # 127d
    kept = detect_recurring(rows, date(2026, 5, 5), _EXP, frozenset())  # 56 days
    assert len(kept) == 1


# INV-4 — a payee that both bills and pays forms two direction-split groups.
def test_direction_split() -> None:
    rows = [
        _row(1, "2026-01-10", -19900),
        _row(2, "2026-02-10", -19900),
        _row(3, "2026-03-10", -19900),
        _row(4, "2026-01-15", 5000),
        _row(5, "2026-02-15", 5000),
        _row(6, "2026-03-15", 5000),
    ]
    items = detect_recurring(rows, date(2026, 3, 20), _EXP, frozenset())
    assert {it.direction for it in items} == {Direction.OUT, Direction.IN}
    assert len(items) == 2


# INV-3 — ids in excluded_ids (confirmed transfers) drop before grouping; here
# excluding one leaves only 2 members → the group no longer qualifies.
def test_excluded_ids_dropped() -> None:
    rows = _monthly([-19900, -19900, -19900])
    assert detect_recurring(rows, date(2026, 3, 20), _EXP, frozenset({2})) == []


# INV-4 — a zero-amount row is excluded before grouping (same 3→2 collapse).
def test_zero_amount_excluded() -> None:
    rows = [
        _row(1, "2026-01-10", -19900),
        _row(2, "2026-02-10", 0),  # excluded
        _row(3, "2026-03-10", -19900),
    ]
    assert detect_recurring(rows, date(2026, 3, 20), _EXP, frozenset()) == []


# INV-5 — an all-digits description keeps a non-blank grouping key.
def test_all_digits_description_keeps_nonblank_key() -> None:
    rows = _monthly([-19900, -19900, -19900])
    rows = [r._replace(description="12345") for r in rows]
    items = detect_recurring(rows, date(2026, 3, 20), _EXP, frozenset())
    assert len(items) == 1
    assert items[0].merchant_key == "12345"


# INV-11 — nominal_interval_days table.
def test_nominal_interval_days() -> None:
    assert nominal_interval_days(Cadence.WEEKLY) == 7
    assert nominal_interval_days(Cadence.FORTNIGHTLY) == 14
    assert nominal_interval_days(Cadence.MONTHLY) == 30
    assert nominal_interval_days(Cadence.YEARLY) == 365


# INV-11 — calendar clamp: Jan 31 +monthly → Feb 28; Feb 29 +yearly → Feb 28.
def test_add_cadence_clamps_month_end() -> None:
    assert _add_cadence(date(2026, 1, 31), Cadence.MONTHLY) == date(2026, 2, 28)
    assert _add_cadence(date(2024, 2, 29), Cadence.YEARLY) == date(2025, 2, 28)
    assert _add_cadence(date(2026, 1, 5), Cadence.WEEKLY) == date(2026, 1, 12)
    assert _add_cadence(date(2026, 1, 5), Cadence.FORTNIGHTLY) == date(2026, 1, 19)


# INV-11 — monthly-equivalent rounds ROUND_HALF_EVEN: a yearly R1.50 → R0.125/mo
# → R0.12 (2 is even; HALF_UP would give 0.13).
def test_monthly_equivalent_half_even() -> None:
    assert _monthly_equivalent(Decimal("1.50"), Cadence.YEARLY, _EXP) == Decimal("0.12")
    # weekly factor 52/12 on R50.00 → R216.666… → R216.67.
    assert _monthly_equivalent(Decimal("50.00"), Cadence.WEEKLY, _EXP) == Decimal(
        "216.67"
    )


# --------------------------------------------------------------------------- #
# INV-10 — schema v8 -> v9 (the recurring_decisions table)
# --------------------------------------------------------------------------- #
def _has_recurring_decisions(conn) -> bool:
    """Whether the ``recurring_decisions`` table exists (the v9 migration product)."""
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='recurring_decisions'"
        ).fetchone()
        is not None
    )


def test_INV10_latest_schema_version_is_9() -> None:
    assert LATEST_SCHEMA_VERSION == 9


def test_INV10_v8_upgrades_to_v9(paths) -> None:
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v8_vault(vault_path, sidecar, salt, [("2026-01-01", -100, "a")])

    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v8 -> v9 (walks to LATEST)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 9

    assert _has_recurring_decisions(conn)
    # A fresh table — no rows.
    assert conn.execute("SELECT count(*) FROM recurring_decisions").fetchone()[0] == 0
    conn.close()


def test_INV10_migration_is_atomic(paths) -> None:
    """A wedged v9 step leaves a re-openable v8 with no half-built table (the CREATE
    + UPDATE schema_version share one owned transaction)."""
    vault_path, sidecar = paths
    salt = bytes(range(SALT_LEN))
    build_v8_vault(vault_path, sidecar, salt, [])
    conn = keyed_connection(vault_path, salt)

    with pytest.raises(RuntimeError):
        run_migrations(
            raising_conn(
                conn,
                "CREATE TABLE recurring_decisions",
                "injected failure at the recurring_decisions CREATE",
            )
        )
    # Still v8, and no half-built table left behind.
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 8
    assert not _has_recurring_decisions(conn)
    conn.close()


# --------------------------------------------------------------------------- #
# RecurringService + RecurringRepository — a real (tmp_path) v9 vault. first_run
# migrates straight to v9; helpers seed raw transactions the detector reads.
# --------------------------------------------------------------------------- #
@pytest.fixture
def vault_service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # migrates straight to v9
    yield svc
    svc.lock()


def _default_account(svc: AuthService) -> int:
    return AccountRepository(svc.vault.connection).list_all()[0].id


def _add_txn(
    svc: AuthService, account_id: int, occurred_on: str, amount_minor: int, desc: str
) -> int:
    return TransactionRepository(svc.vault.connection).add(
        account_id, occurred_on, amount_minor, desc
    )


_MONTHLY_DAYS = ("2026-01-05", "2026-02-05", "2026-03-05", "2026-04-05", "2026-05-05")
_ACTIVE = date(2026, 5, 20)  # within grace of a series ending 2026-05-05


def _seed_monthly(
    svc: AuthService, account_id: int, amount_minor: int, desc: str
) -> list[int]:
    return [_add_txn(svc, account_id, d, amount_minor, desc) for d in _MONTHLY_DAYS]


# INV-9 — snapshot() partitions into (suggested, confirmed, summary) in one pass,
# and equals the three thin accessors called separately.
def test_INV9_snapshot_partitions_and_matches_accessors(vault_service) -> None:
    svc = vault_service
    _seed_monthly(svc, _default_account(svc), -19900, "Netflix")
    rec = RecurringService(svc.vault)
    suggested, confirmed, summary = rec.snapshot(_ACTIVE)
    assert [it.merchant_key for it in suggested] == ["netflix"]
    assert confirmed == []
    assert summary == RecurringSummary(Decimal("0"), Decimal("0"), Decimal("0"))
    assert rec.candidates(_ACTIVE) == suggested
    assert rec.confirmed(_ACTIVE) == confirmed
    assert rec.summary(_ACTIVE) == summary


# INV-9 (D9 perf) — snapshot runs detection exactly once.
def test_INV9_snapshot_runs_detection_once(vault_service, monkeypatch) -> None:
    import finbreak.services.recurring as rec_mod

    svc = vault_service
    _seed_monthly(svc, _default_account(svc), -19900, "Netflix")
    calls = {"n": 0}
    real = rec_mod.detect_recurring

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(rec_mod, "detect_recurring", counting)
    rec_mod.RecurringService(svc.vault).snapshot(_ACTIVE)
    assert calls["n"] == 1


# INV-8 — confirm moves an item from suggested to confirmed; summary sums it.
def test_INV8_confirm_moves_to_confirmed(vault_service) -> None:
    svc = vault_service
    _seed_monthly(svc, _default_account(svc), -19900, "Netflix")
    rec = RecurringService(svc.vault)
    rec.confirm(Direction.OUT, "netflix")
    suggested, confirmed, summary = rec.snapshot(_ACTIVE)
    assert suggested == []
    assert [it.merchant_key for it in confirmed] == ["netflix"]
    assert summary.monthly_out == Decimal("199.00")
    assert summary.monthly_in == Decimal("0")
    assert summary.net == Decimal("-199.00")


# INV-8 — a dismissed key appears in neither list.
def test_INV8_dismiss_hides_from_both(vault_service) -> None:
    svc = vault_service
    _seed_monthly(svc, _default_account(svc), -19900, "Netflix")
    rec = RecurringService(svc.vault)
    rec.dismiss(Direction.OUT, "netflix")
    suggested, confirmed, _ = rec.snapshot(_ACTIVE)
    assert suggested == []
    assert confirmed == []


# INV-8 — reset clears the decision, returning the item to suggested.
def test_INV8_reset_returns_to_suggested(vault_service) -> None:
    svc = vault_service
    _seed_monthly(svc, _default_account(svc), -19900, "Netflix")
    rec = RecurringService(svc.vault)
    rec.confirm(Direction.OUT, "netflix")
    rec.reset(Direction.OUT, "netflix")
    suggested, confirmed, _ = rec.snapshot(_ACTIVE)
    assert [it.merchant_key for it in suggested] == ["netflix"]
    assert confirmed == []


# INV-8 — decisions upsert on (direction, merchant_key): confirm then dismiss the
# same key leaves ONE row, dismissed winning.
def test_INV8_decision_upserts_by_key(vault_service) -> None:
    svc = vault_service
    _seed_monthly(svc, _default_account(svc), -19900, "Netflix")
    rec = RecurringService(svc.vault)
    rec.confirm(Direction.OUT, "netflix")
    rec.dismiss(Direction.OUT, "netflix")
    assert RecurringRepository(svc.vault.connection).decisions() == {
        ("out", "netflix"): "dismissed"
    }


# INV-9 — a confirmed decision survives a detection gap: it vanishes when the item
# stops detecting (stale) and returns when it detects again.
def test_INV9_confirmed_decision_survives_detection_gap(vault_service) -> None:
    svc = vault_service
    _seed_monthly(svc, _default_account(svc), -19900, "Netflix")
    rec = RecurringService(svc.vault)
    rec.confirm(Direction.OUT, "netflix")
    # Far future — the monthly series is now stale, so nothing detects.
    assert rec.confirmed(date(2027, 1, 1)) == []
    # Back in the active window — the confirmed item reappears (decision survived).
    assert [it.merchant_key for it in rec.confirmed(_ACTIVE)] == ["netflix"]


# INV-3 — the service excludes confirmed-transfer txn ids: excluding one member of
# a 3-member series drops it below the minimum, so it stops detecting.
def test_INV3_confirmed_transfer_txn_excluded(vault_service) -> None:
    svc = vault_service
    a = _default_account(svc)
    b = AccountService(svc.vault).add_account("Savings", "savings").id
    debit = _add_txn(svc, a, "2026-01-05", -19900, "Netflix")
    _add_txn(svc, a, "2026-02-05", -19900, "Netflix")
    _add_txn(svc, a, "2026-03-05", -19900, "Netflix")
    rec = RecurringService(svc.vault)
    today = date(2026, 3, 20)
    assert [it.merchant_key for it in rec.candidates(today)] == ["netflix"]
    # A matching credit on B, confirmed as a transfer → `debit` is now excluded.
    credit = _add_txn(svc, b, "2026-01-05", 19900, "from current")
    TransferDetectionService(svc.vault).confirm(debit, credit)
    assert rec.candidates(today) == []  # only 2 members remain un-excluded


# INV-13 — one merchant's charges across TWO accounts group into a single item
# (the detection read has no account or window filter).
def test_INV13_merchant_groups_across_accounts(vault_service) -> None:
    svc = vault_service
    a = _default_account(svc)
    b = AccountService(svc.vault).add_account("Savings", "savings").id
    _add_txn(svc, a, "2026-01-05", -19900, "Netflix")
    _add_txn(svc, b, "2026-02-05", -19900, "Netflix")
    _add_txn(svc, a, "2026-03-05", -19900, "Netflix")
    items = RecurringService(svc.vault).candidates(date(2026, 3, 20))
    assert len(items) == 1
    assert items[0].occurrences == 3


# D8 summary — confirmed weekly (52/12) + monthly items sum their per-month
# equivalents into monthly_in / monthly_out; net = in − out.
def test_summary_sums_confirmed_monthly_equivalents(vault_service) -> None:
    svc = vault_service
    acct = _default_account(svc)
    _seed_monthly(svc, acct, -19900, "Netflix")  # OUT R199/mo
    for d in ("2026-05-01", "2026-05-08", "2026-05-15", "2026-05-22"):
        _add_txn(svc, acct, d, 5000, "Gig Pay")  # weekly IN R50 → R216.67/mo
    rec = RecurringService(svc.vault)
    today = date(2026, 5, 25)
    rec.confirm(Direction.OUT, "netflix")
    rec.confirm(Direction.IN, "gig pay")
    summary = rec.summary(today)
    assert summary.monthly_out == Decimal("199.00")
    assert summary.monthly_in == Decimal("216.67")
    assert summary.net == Decimal("17.67")
