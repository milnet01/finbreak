"""FIBR-0019 INV-7/INV-8/INV-13 — the v1 → v2 migration. Enforces spec.md.

Headless -- vault-level, no UI (§ 7). Every vault lives under ``tmp_path``.

Why this exists: § 13 rewrites the key schedule of a vault holding a
household's financial history, on the user's machine, at the next unlock. There
is exactly one acceptable failure mode -- the vault still opens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    create_v1_vault,
    open_after_restart,
    read_sidecar,
    row_digests,
)
from sqlcipher3.dbapi2 import DatabaseError

from finbreak.services import vault_migration
from finbreak.services.vault_migration import STEPS, migrate_to_v2

pytestmark = pytest.mark.features


class _Abort(RuntimeError):
    """The injected crash. A distinct type so a genuine migration failure is
    never mistaken for the abort this test asked for."""


def _seed(conn: Any) -> None:
    """Put rows in the application tables a personal-finance vault carries.

    Synthetic throughout -- no real statement data and no real account number
    (``testing.md`` § 6, security-model INV-6). The row DIGESTS below are taken
    over EVERY table enumerated from ``sqlite_master``, not just these, so a
    migration that drops a table this helper never seeded is still caught.
    """
    conn.execute(
        "INSERT INTO accounts(name, type, created_at) VALUES (?, ?, ?)",
        ("Everyday", "current", "2026-01-01T00:00:00+00:00"),
    )
    account_id = conn.execute("SELECT id FROM accounts ORDER BY id").fetchall()[0][0]
    for day, minor, description in (
        ("2026-01-04", -12_34, "grocery run"),
        ("2026-01-09", 250_00, "salary"),
        ("2026-02-02", -99_99, "annual thing"),
    ):
        conn.execute(
            "INSERT INTO transactions(occurred_on, amount_minor, description, "
            "created_at, account_id) VALUES (?, ?, ?, ?, ?)",
            (day, minor, description, "2026-01-01T00:00:00+00:00", account_id),
        )
    conn.commit()


def _fresh_v1_vault(root: Path, name: str) -> tuple[Path, Path, bytearray, dict]:
    """A seeded v1 vault of its own, plus its key and its pre-migration digests."""
    directory = root / name
    directory.mkdir()
    vault_path = directory / "vault.db"
    sidecar_path = directory / "vault.kdf.json"
    vault, _params, key = create_v1_vault(vault_path, sidecar_path)
    _seed(vault.connection)
    digests = row_digests(vault.connection)
    vault.close()
    return vault_path, sidecar_path, key, digests


# --------------------------------------------------------------------------- #
# INV-7 — migration is atomic: at every instant, one of the two pairs opens
# --------------------------------------------------------------------------- #
def test_every_crash_point_still_opens(tmp_path: Path) -> None:
    # Abort after each of S1..S6 in turn. `on_step` fires immediately BEFORE the
    # named step, so raising at STEPS[i + 1] leaves STEPS[i] complete.
    for index, completed in enumerate(STEPS[1:], start=1):
        next_step = STEPS[index + 1] if index + 1 < len(STEPS) else None
        vault_path, sidecar_path, key, digests = _fresh_v1_vault(
            tmp_path, f"crash-after-{completed}"
        )

        def abort_before(step: str, target: str | None = next_step) -> None:
            if target is not None and step == target:
                raise _Abort(f"injected crash before {step}")

        try:
            migrate_to_v2(
                vault_path, sidecar_path, bytearray(key), on_step=abort_before
            )
        except _Abort:
            pass

        # A fresh app start: read the sidecar, dispatch on its shape, open.
        try:
            reopened = open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD)
        except Exception as exc:
            pytest.fail(
                "INV-7: after a crash immediately following "
                f"{completed}, a fresh app start could not open the vault with "
                "the original password. There must be no instant at which "
                "neither the pre-migration nor the post-migration pair opens.\n"
                "  expected: the vault opens with the original master password\n"
                f"  actual:   {type(exc).__name__}: {exc}\n"
                f"  sidecar on disk: {read_sidecar(sidecar_path)}"
            )

        after = row_digests(reopened.connection)
        reopened.close()
        assert after == digests, (
            f"INV-7: the vault opened after a crash following {completed}, but "
            "its contents moved.\n"
            f"  expected: {digests}\n  actual:   {after}"
        )


# --------------------------------------------------------------------------- #
# INV-8 — migration preserves every row of every table
# --------------------------------------------------------------------------- #
def test_migration_preserves_every_row(tmp_path: Path) -> None:
    vault_path, sidecar_path, key, before = _fresh_v1_vault(tmp_path, "full-run")

    migrate_to_v2(vault_path, sidecar_path, bytearray(key))

    reopened = open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD)
    after = row_digests(reopened.connection)
    reopened.close()

    assert set(after) == set(before), (
        "INV-8: the migrated vault does not carry the same TABLES.\n"
        f"  expected: {sorted(before)}\n  actual:   {sorted(after)}"
    )
    for table, expected in before.items():
        assert after[table] == expected, (
            f"INV-8: table {table!r} did not survive the migration intact. "
            "A table filter on export_to, or a migration run against a "
            "connection with an uncommitted write transaction, loses rows here.\n"
            f"  expected: (rows, digest) = {expected}\n"
            f"  actual:   {after[table]}"
        )


# --------------------------------------------------------------------------- #
# INV-13 — no byte of the live pair moves until a VERIFIED rollback copy exists
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("broken_step", ["write_rollback_copy", "verify_rollback_copy"])
def test_no_swap_without_a_verified_rollback_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken_step: str
) -> None:
    vault_path, sidecar_path, key, before = _fresh_v1_vault(tmp_path, broken_step)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise _Abort(f"injected failure in {broken_step}")

    monkeypatch.setattr(vault_migration, broken_step, explode)

    with pytest.raises(_Abort):
        migrate_to_v2(vault_path, sidecar_path, bytearray(key))

    # The copy is verified by OPENING it, and that is the whole of the
    # difference: a truncated or short-written copy that merely EXISTS reads as
    # a rollback route, which is worse than none -- it is the thing the user
    # would be told to fall back on.
    sidecar = read_sidecar(sidecar_path)
    assert "sidecar_version" not in sidecar, (
        f"INV-13: {broken_step} failed, so nothing may have been swapped -- yet "
        "the live sidecar has already been replaced with the v2 shape.\n"
        "  expected: the original v1 sidecar, untouched\n"
        f"  actual:   {sidecar}"
    )

    try:
        reopened = open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD)
    except DatabaseError as exc:
        pytest.fail(
            f"INV-13: after {broken_step} failed, the vault no longer opens with "
            "the original password -- so the live pair was touched before a "
            "verified rollback copy existed.\n"
            "  expected: the original password still opens the vault\n"
            f"  actual:   {type(exc).__name__}: {exc}"
        )

    # The witness is per-table row digests, NOT a hash of vault.db: under WAL the
    # main file's bytes move on open and close with no logical write, so a byte
    # comparison is flaky in one direction and vacuous in the other (the reason
    # INV-12 gives, applied here).
    after = row_digests(reopened.connection)
    reopened.close()
    assert after == before, (
        f"INV-13: {broken_step} failed and the vault's contents still moved.\n"
        f"  expected: {before}\n  actual:   {after}"
    )
