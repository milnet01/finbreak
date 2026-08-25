"""FIBR-0019 INV-7/INV-8/INV-13 — the v1 → v2 migration. Enforces spec.md.

Headless -- vault-level, no UI (§ 7). Every vault lives under ``tmp_path``.

Why this exists: § 13 rewrites the key schedule of a vault holding a
household's financial history, on the user's machine, at the next unlock. There
is exactly one acceptable failure mode -- the vault still opens.
"""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    create_v1_vault,
    kek_for,
    open_after_restart,
    opens_with,
    read_sidecar,
    read_v2_sidecar,
    row_digests,
    unwrap_slot,
)
from sqlcipher3.dbapi2 import DatabaseError

from finbreak.errors import RollbackAvailableError, VaultStateError
from finbreak.keywrap import SLOT_MASTER
from finbreak.services import auth as auth_module
from finbreak.services import vault_migration
from finbreak.services.auth import AuthService
from finbreak.services.vault_migration import (
    MIGRATING_SUFFIX,
    STEPS,
    _suffixed,
    migrate_to_v2,
    rollback_copy_paths,
    verify_rollback_copy,
    write_rollback_copy,
)
from finbreak.vault import Vault

pytestmark = pytest.mark.features

# SQLCipher's page size for this project's vaults, measured rather than assumed
# (``PRAGMA page_size`` on a freshly created v1 vault, 2026-08-24). Only the
# damaged-copy leg below depends on it, and only to land its byte flip in a
# page that holds rows rather than schema.
_PAGE_SIZE = 4096


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


# --------------------------------------------------------------------------- #
# FP02 finding 3 — S6 is bookkeeping, and it may not lock the user out
# --------------------------------------------------------------------------- #
def test_a_failing_s6_does_not_lock_the_user_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-7 past the swap: S5 is done, so the post-migration pair opens.

    § 13.2's S6 clears ``migration_pending`` and removes the ``.pre-v2`` pair —
    bookkeeping over a vault that already opens. § 6 names disk-full at S1–S6
    and hands it to § 13's resume rules, whose contract is INV-7: there is no
    instant at which neither pair opens. So an ENOSPC at S6 leaves the vault
    resumable rather than unopenable, and the unlock it interrupts must still
    succeed — a failure here is raised out of a Qt slot, where the user meets
    it as a crash on a vault that was never damaged.
    """
    vault_path, sidecar_path, key, digests = _fresh_v1_vault(tmp_path, "enospc-at-s6")

    def abort_before_s6(step: str) -> None:
        if step == "S6":
            raise _Abort("injected crash before S6")

    with pytest.raises(_Abort):
        migrate_to_v2(vault_path, sidecar_path, bytearray(key), on_step=abort_before_s6)

    # Precondition: the migration really is PAST the swap with only its
    # bookkeeping outstanding. Without this the leg could pass against a vault
    # that never migrated at all, where S6 is not the thing being tested.
    stalled = read_sidecar(sidecar_path)
    assert stalled.get("migration_pending") is True, (
        "precondition: S5 must have completed, leaving a migration-pending v2 "
        "sidecar over the swapped database.\n"
        "  expected: migration_pending == True\n"
        f"  actual:   {stalled}"
    )

    def no_space(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(vault_migration, "write_sidecar_v2", no_space)

    try:
        reopened = open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD)
    except Exception as exc:
        pytest.fail(
            "INV-7: S6 could not write its sidecar, and the user was locked out "
            "of a vault that had already migrated and opens on demand. S6 is "
            "bookkeeping; a failure in it leaves the state resumable and must "
            "not reach the caller.\n"
            "  expected: the vault opens with the original master password\n"
            f"  actual:   {type(exc).__name__}: {exc}"
        )

    after = row_digests(reopened.connection)
    reopened.close()
    assert after == digests, (
        "INV-7: the vault opened after a failed S6, but its contents moved.\n"
        f"  expected: {digests}\n  actual:   {after}"
    )

    # And nothing pretended S6 ran: the vault stays resumable, so the next
    # unlock finishes the bookkeeping once there is room for it.
    still = read_sidecar(sidecar_path)
    assert still.get("migration_pending") is True, (
        "a failed S6 must leave the sidecar untouched, so the next unlock "
        "re-enters § 13.3 branch 1 and finishes the job.\n"
        "  expected: migration_pending still True\n"
        f"  actual:   {still}"
    )


# --------------------------------------------------------------------------- #
# FP02 finding 4 — security-model INV-3: the minted DEK is wiped
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("convert_fails", [False, True])
def test_the_minted_dek_is_wiped_whatever_happens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, convert_fails: bool
) -> None:
    """``migrate_to_v2`` mints the DEK, so it owns wiping it.

    Nothing downstream can wipe a buffer it was only lent. The failure leg is
    the one that bites: only a ``try``/``finally`` survives S1–S6 raising, and
    a migration that aborts is exactly when key material is left behind.
    """
    vault_path, sidecar_path, key, _digests = _fresh_v1_vault(
        tmp_path, f"dek-wipe-{convert_fails}"
    )

    real_convert = vault_migration._convert
    handed: list[bytearray] = []
    at_handover: list[bytes] = []

    def spy(
        vault_path_: Path,
        sidecar_path_: Path,
        kek_master: bytearray,
        dek: bytearray,
        params: Any,
        step: Any,
    ) -> None:
        handed.append(dek)
        at_handover.append(bytes(dek))
        if convert_fails:
            raise _Abort("injected failure inside S1..S6")
        real_convert(vault_path_, sidecar_path_, kek_master, dek, params, step)

    monkeypatch.setattr(vault_migration, "_convert", spy)

    if convert_fails:
        with pytest.raises(_Abort):
            migrate_to_v2(vault_path, sidecar_path, bytearray(key))
    else:
        migrate_to_v2(vault_path, sidecar_path, bytearray(key))

    # Preconditions: a DEK really was minted and handed over, and it was real
    # key material at that moment. Without both, the all-zero assertion below
    # would be satisfied by a buffer that never held anything.
    assert len(handed) == 1, (
        "precondition: migrate_to_v2 must mint exactly one DEK and hand it to "
        "_convert.\n"
        f"  expected: 1 handover\n  actual:   {len(handed)}"
    )
    assert at_handover[0] != bytes(len(at_handover[0])), (
        "precondition: the DEK must be real key material when it is handed "
        "over, or wiping it proves nothing.\n"
        "  expected: a non-zero buffer\n"
        f"  actual:   {len(at_handover[0])} zero bytes"
    )

    assert handed[0] == bytearray(len(handed[0])), (
        "security-model INV-3: migrate_to_v2 minted the DEK and left it in the "
        "heap. It owns that buffer and must wipe it in a finally, so an "
        "aborted migration leaves no database key behind.\n"
        f"  expected: {len(handed[0])} zero bytes\n"
        f"  actual:   a buffer still holding key material"
    )


# --------------------------------------------------------------------------- #
# FP02 finding 5 — the unlock path wipes the DEK when the ladder raises
# --------------------------------------------------------------------------- #
def test_a_failed_resume_does_not_leak_the_dek(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_unlock_through_slot`` wipes ``kek`` in its ``finally`` and must wipe
    the DEK it unwrapped on the same terms.

    § 13.3's terminal branch is a ROUTINE outcome, not a crash — it is what the
    ladder does when every route is exhausted — so the leak it causes is on the
    ordinary path, not an exotic one (security-model INV-3).
    """
    vault_path, sidecar_path, key, _digests = _stalled_before_s5(tmp_path, "dek-leak")

    data = read_sidecar(sidecar_path)
    kek = kek_for(MASTER_PASSWORD, data, "master")

    real_unwrap = auth_module.unwrap_dek
    unwrapped: list[bytearray] = []
    at_unwrap: list[bytes] = []

    def spy(*args: Any, **kwargs: Any) -> bytearray:
        dek = real_unwrap(*args, **kwargs)
        unwrapped.append(dek)
        at_unwrap.append(bytes(dek))
        return dek

    def terminal(*_args: object, **_kwargs: object) -> None:
        raise VaultStateError(
            "the vault and its key record disagree: no database this sidecar "
            "names can be opened with the key it holds"
        )

    monkeypatch.setattr(auth_module, "unwrap_dek", spy)
    monkeypatch.setattr(vault_migration, "resume", terminal)

    service = AuthService(vault_path, sidecar_path)
    with pytest.raises(VaultStateError):
        service.complete_unlock(bytes(kek))

    # Preconditions: the slot really unwrapped, and to real key material — the
    # ladder is entered only after that (§ 13.3 step 0), so a leg where the
    # unwrap never happened would be testing nothing.
    assert len(unwrapped) == 1, (
        "precondition: the master slot must unwrap exactly once before the "
        "ladder is entered.\n"
        f"  expected: 1 unwrap\n  actual:   {len(unwrapped)}"
    )
    assert at_unwrap[0] != bytes(len(at_unwrap[0])), (
        "precondition: the unwrapped DEK must be real key material.\n"
        "  expected: a non-zero buffer\n"
        f"  actual:   {len(at_unwrap[0])} zero bytes"
    )

    assert unwrapped[0] == bytearray(len(unwrapped[0])), (
        "security-model INV-3: resume() raised and the DEK it was handed was "
        "left in the heap. kek is wiped in the same method's finally; the DEK "
        "unwrapped from it must be too, on every route out that does not hand "
        "it to _open_with.\n"
        f"  expected: {len(unwrapped[0])} zero bytes\n"
        f"  actual:   a buffer still holding the database key"
    )


# --------------------------------------------------------------------------- #
# FP02 finding 6 — INV-13 is unconditional, and § 13.3 branch 3 swaps the pair
# --------------------------------------------------------------------------- #
def _stalled_before_s5(root: Path, name: str) -> tuple[Path, Path, bytearray, dict]:
    """A vault stalled between S4 and S5 with the replacement removed.

    That is § 13.3's branch 3: the sidecar is the pending v2 one, the database
    is still the v1 one, no ``vault.db.migrating`` exists for branch 2 to find,
    and KEK-master opens the live database — so the ladder restarts from S1,
    re-entering ``_convert``, which replaces the live sidecar at S4.
    """
    vault_path, sidecar_path, key, digests = _fresh_v1_vault(root, name)

    def abort_before_s5(step: str) -> None:
        if step == "S5":
            raise _Abort("injected crash before S5")

    with pytest.raises(_Abort):
        migrate_to_v2(vault_path, sidecar_path, bytearray(key), on_step=abort_before_s5)

    migrating = vault_path.with_name(vault_path.name + MIGRATING_SUFFIX)
    migrating.unlink()
    return vault_path, sidecar_path, key, digests


@pytest.mark.parametrize("copy_state", ["absent", "unreadable", "stale_v2", "intact"])
def test_the_ladder_never_restarts_without_a_verified_rollback_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, copy_state: str
) -> None:
    """INV-13 does not carve out the resume path.

    § 13.3 branch 3 says only "restart from S1", and ``_convert``'s S4 replaces
    the live sidecar — a byte of the live pair. So the same gate S0 applies has
    to hold here: a rollback copy that exists, is complete, and opens with the
    key in hand. The ``intact`` leg is the other half of it — the ``.pre-v2``
    pair left by the original S0 is the GENUINE pre-upgrade vault, a v1 database
    beside a v1 sidecar, and re-copying the live pair over it would leave a
    "rollback" that is the same stalled state the user is trying to escape.
    """
    vault_path, sidecar_path, key, digests = _stalled_before_s5(
        tmp_path, f"restart-{copy_state}"
    )
    copy_vault, copy_sidecar = rollback_copy_paths(vault_path, sidecar_path)

    assert copy_vault.exists() and copy_sidecar.exists(), (
        "precondition: S0 took a rollback copy and S6 never ran, so the pair "
        "is on disk — which is the state § 13.3 says is the only one it "
        "exists in.\n"
        f"  expected: both of {copy_vault.name}, {copy_sidecar.name}\n"
        f"  actual:   {copy_vault.exists()}, {copy_sidecar.exists()}"
    )
    if copy_state == "absent":
        copy_vault.unlink()
        copy_sidecar.unlink()
    elif copy_state == "unreadable":
        copy_sidecar.write_text("not a sidecar", encoding="utf-8")
    elif copy_state == "stale_v2":
        # What an earlier buggy retake left behind: a v1 database beside the
        # MIGRATION-PENDING v2 sidecar. Every check short of reading the shape
        # passes it -- the pair exists, `load_and_validate_params` accepts both
        # shapes, and KEK-master opens the database, because the database half
        # is genuinely the v1 one. So it must be rejected on the sidecar's
        # version and retaken, or the fix repairs new machines only and leaves
        # every machine already carrying one still restoring the stalled state
        # (FIBR-0310 R4).
        shutil.copyfile(sidecar_path, copy_sidecar)

    real_convert = vault_migration._convert
    entered: list[str] = []

    def guard(
        vault_path_: Path,
        sidecar_path_: Path,
        kek_master: bytearray,
        dek: bytearray,
        params: Any,
        step: Any,
    ) -> None:
        entered.append("yes")
        guard_vault, guard_sidecar = rollback_copy_paths(vault_path_, sidecar_path_)
        assert guard_vault.exists() and guard_sidecar.exists(), (
            "INV-13: the ladder re-entered S1 with no rollback copy on disk. "
            "S4 replaces the live sidecar, so this is the live pair being "
            "modified with no safety net — the exact thing INV-13 forbids, and "
            "§ 6 says never to proceed without.\n"
            f"  expected: both of {guard_vault.name}, {guard_sidecar.name}\n"
            f"  actual:   {guard_vault.exists()}, {guard_sidecar.exists()}"
        )
        assert opens_with(guard_vault, guard_sidecar, bytearray(kek_master)), (
            "INV-13: a rollback copy is on disk but does not open with the key "
            "in hand, so it is not a rollback route — which is worse than "
            "none, being the thing the user would be told to fall back on.\n"
            "  expected: the copy opens with KEK-master\n"
            "  actual:   it does not"
        )
        try:
            preserved = read_sidecar(guard_sidecar)
        except Exception as exc:
            pytest.fail(
                "INV-13: the rollback pair's sidecar does not parse, so the "
                "pair is not a vault and cannot be restored. A copy that "
                "exists but cannot be read is exactly the 'worse than none' "
                "case INV-13 is about.\n"
                "  expected: a readable sidecar beside the copy\n"
                f"  actual:   {type(exc).__name__}: {exc}"
            )
        assert "sidecar_version" not in preserved, (
            "D8: a PRE-upgrade pair is v1 on both halves. Where S0's copy "
            "survived, that means not overwriting its v1 sidecar; where the "
            "copy had to be RETAKEN, it means rebuilding one rather than "
            "byte-copying the live pair, whose sidecar S4 has already replaced "
            "with the migration-pending v2 one. Either way a v2 sidecar here "
            "makes the 'rollback' a copy of the stalled state: restoring it "
            "puts KEK-master over a v2 sidecar, the next unlock re-enters "
            "branch 3, and the migration the user asked to undo restarts "
            "(FIBR-0310 R4).\n"
            "  expected: a v1 sidecar beside the copy\n"
            f"  actual:   {preserved}"
        )
        real_convert(vault_path_, sidecar_path_, kek_master, dek, params, step)

    monkeypatch.setattr(vault_migration, "_convert", guard)

    reopened = open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD)
    after = row_digests(reopened.connection)
    reopened.close()

    assert entered == ["yes"], (
        "precondition: § 13.3 branch 3 must have restarted from S1 — that is "
        "the branch this leg is about.\n"
        f"  expected: ['yes']\n  actual:   {entered}"
    )
    assert after == digests, (
        "the ladder finished, but the vault's contents moved.\n"
        f"  expected: {digests}\n  actual:   {after}"
    )


# --------------------------------------------------------------------------- #
# FP02 finding 8 — verifying the copy means reading it, not reading its schema
# --------------------------------------------------------------------------- #
def test_a_damaged_rollback_copy_does_not_verify(tmp_path: Path) -> None:
    """INV-13's Breaks-when clause, on the artefact rather than on the timing.

    S2 gives the REPLACEMENT ``PRAGMA integrity_check``. The copy the user
    would actually fall back on got a ``sqlite_master`` read — and SQLCipher
    checks each page's HMAC only as that page is read, so damage anywhere past
    the schema is invisible to it.

    **A truncated copy is NOT the shape**, though the finding this test closes
    said it was: measured 2026-08-24, SQLite refuses a file shorter than its
    own header claims, at ``open``, at every truncation from 2% to 50%. The
    shape that gets through is a copy of the RIGHT length whose pages did not
    all survive — a torn write, a bad sector, a half-flushed page cache.
    """
    directory = tmp_path / "damaged-copy"
    directory.mkdir()
    vault_path = directory / "vault.db"
    sidecar_path = directory / "vault.kdf.json"
    vault, _params, key = create_v1_vault(vault_path, sidecar_path)
    _seed(vault.connection)

    # Enough rows that the data lives well past the schema pages — the whole
    # point is a truncation that removes ROWS and leaves the schema readable.
    account_id = vault.connection.execute(
        "SELECT id FROM accounts ORDER BY id"
    ).fetchall()[0][0]
    vault.connection.executemany(
        "INSERT INTO transactions(occurred_on, amount_minor, description, "
        "created_at, account_id) VALUES (?, ?, ?, ?, ?)",
        [
            (
                "2026-03-01",
                -100 - n,
                f"filler row {n}",
                "2026-01-01T00:00:00+00:00",
                account_id,
            )
            for n in range(2000)
        ],
    )
    vault.connection.commit()
    vault.close()

    copy_vault, copy_sidecar = write_rollback_copy(vault_path, sidecar_path)

    pages = copy_vault.stat().st_size // _PAGE_SIZE
    assert pages > 12, (
        "precondition: the seeded vault must span enough pages that page 11 "
        "holds rows rather than schema.\n"
        f"  expected: > 12 pages\n  actual:   {pages}"
    )

    # Flip one byte in a page well past the schema. The copy keeps its length,
    # so SQLite's own short-file refusal never fires, and page 1 still decrypts
    # perfectly -- which is the whole reason a schema read cannot see this.
    damaged = 10 * _PAGE_SIZE + 100
    with copy_vault.open("r+b") as handle:
        handle.seek(damaged)
        byte = handle.read(1)
        handle.seek(damaged)
        handle.write(bytes([byte[0] ^ 0xFF]))

    # Precondition: the damaged copy still passes the check this replaces --
    # it opens, and its schema reads. A leg that is green because SQLCipher
    # refused the file outright would prove nothing about the finding.
    probe = Vault(copy_vault, copy_sidecar)
    probe.open(bytearray(key), in_memory_temp=True)
    try:
        schema_rows = probe.connection.execute(
            "SELECT count(*) FROM sqlite_master"
        ).fetchone()[0]
    finally:
        probe.close()
    assert schema_rows > 0, (
        "precondition: the damaged copy must still open and read its schema, "
        "which is exactly what the old verification did -- and is why that "
        "verification could not see the damage.\n"
        "  expected: sqlite_master readable, > 0 rows\n"
        f"  actual:   {schema_rows}"
    )

    with pytest.raises(VaultStateError):
        verify_rollback_copy(copy_vault, copy_sidecar, bytearray(key))


# --------------------------------------------------------------------------- #
# FP02 finding 7 — D8's rollback offer, which nothing ever made
# --------------------------------------------------------------------------- #
def _every_route_exhausted(root: Path, name: str) -> tuple[Path, Path, bytearray, dict]:
    """§ 13.3's LAST bullet: the password is right and no database will open.

    Built from the stalled-before-S5 state — a v2 migration-pending sidecar
    beside the v1 database, with S0's ``.pre-v2`` pair intact — by making the
    LIVE database unopenable. Neither the DEK (branch 1) nor KEK-master
    (branch 3) answers to it, and there is no ``.migrating`` (branch 2), so the
    ladder runs out of routes with the credential already proven.

    Bytes are written over the live database only. The ``.pre-v2`` pair is
    untouched, which is the whole point: the user's pre-upgrade vault is sitting
    right there, and until finding 7 nothing offered it to them.
    """
    vault_path, sidecar_path, key, digests = _stalled_before_s5(root, name)
    vault_path.write_bytes(b"not a database, not any more" * 512)
    _drop = vault_path.with_name(vault_path.name + "-wal")
    _drop.unlink(missing_ok=True)
    return vault_path, sidecar_path, key, digests


def _credential_for(sidecar_path: Path) -> tuple[bytearray, bytearray]:
    """KEK-master and the DEK it unwraps — § 13.3 step 0, already done."""
    data = read_v2_sidecar(sidecar_path)
    return (
        kek_for(MASTER_PASSWORD, data, SLOT_MASTER),
        unwrap_slot(MASTER_PASSWORD, data, SLOT_MASTER),
    )


@pytest.mark.parametrize("copy_state", ["intact", "absent", "unusable"])
def test_the_terminal_branch_offers_the_pre_upgrade_copy(
    tmp_path: Path, copy_state: str
) -> None:
    """§ 13.3: "the app says a pre-upgrade copy exists and offers to restore it".

    The distinction has to be MADE by the ladder, because the ladder is the only
    frame holding both the key and the paths. A caller cannot tell § 6's broken
    pairing — where nothing is recoverable and the message is all there is —
    from this state, where the user's pre-upgrade vault is on disk and opens.

    ``absent`` and ``unusable`` are what stop the offer being made on a copy
    that is not there or would not open: INV-13 says a copy that merely exists
    is worse than none, and offering one is exactly how that goes wrong.
    """
    vault_path, sidecar_path, _key, _digests = _every_route_exhausted(
        tmp_path, f"terminal-{copy_state}"
    )
    copy_vault, copy_sidecar = rollback_copy_paths(vault_path, sidecar_path)
    assert copy_vault.exists() and copy_sidecar.exists(), (
        "precondition: S0 took the copy and S6 never ran, so the pair is on "
        "disk — the only state § 13.3 says it exists in.\n"
        f"  expected: both of {copy_vault.name}, {copy_sidecar.name}\n"
        f"  actual:   {copy_vault.exists()}, {copy_sidecar.exists()}"
    )
    if copy_state == "absent":
        copy_vault.unlink()
        copy_sidecar.unlink()
    elif copy_state == "unusable":
        copy_sidecar.write_text("not a sidecar", encoding="utf-8")

    kek, dek = _credential_for(sidecar_path)
    with pytest.raises(VaultStateError) as raised:
        vault_migration.resume(vault_path, sidecar_path, kek, dek)

    offered = isinstance(raised.value, RollbackAvailableError)
    assert offered == (copy_state == "intact"), (
        "§ 13.3's terminal branch: the offer is made when — and only when — a "
        "pre-upgrade pair is beside the vault AND opens with the key the user "
        "just proved. Not making it leaves the user the bare 'vault and key "
        "record disagree' refusal with their own vault sitting next to it; "
        "making it on a copy that will not open points them at a rollback "
        "route that is not one (INV-13).\n"
        f"  expected: offered == {copy_state == 'intact'} for a {copy_state} copy\n"
        f"  actual:   {type(raised.value).__name__}"
    )


def test_restoring_the_pre_upgrade_copy_gives_back_the_v1_vault(
    tmp_path: Path,
) -> None:
    """The offer has to lead somewhere — restoring is what makes it an offer.

    After it, the pair on disk is the v1 one the user had before the update:
    the sidecar is v1 again, the database opens with their password's Argon2id
    output directly (§ 13.1), and every row is back. The ``.pre-v2`` pair is
    consumed, because it IS the live pair now.
    """
    vault_path, sidecar_path, key, digests = _every_route_exhausted(tmp_path, "restore")
    copy_vault, copy_sidecar = rollback_copy_paths(vault_path, sidecar_path)

    vault_migration.restore_rollback_copy(vault_path, sidecar_path)

    restored = read_sidecar(sidecar_path)
    assert "sidecar_version" not in restored, (
        "D8: the copy is a PRE-UPGRADE pair, so restoring it must leave a v1 "
        "sidecar. A v2 one here means the migration-pending sidecar survived "
        "and the vault is still in the state the user is escaping.\n"
        "  expected: the flat v1 sidecar\n"
        f"  actual:   {sorted(restored)}"
    )
    assert opens_with(vault_path, sidecar_path, bytearray(key)), (
        "§ 13.1: the v1 database key IS the Argon2id output, so the restored "
        "pair must open with the key the user already had.\n"
        "  expected: it opens\n  actual:   it does not"
    )
    assert not copy_vault.exists() and not copy_sidecar.exists(), (
        "the copy was moved onto the live pair, not duplicated onto it — "
        "leaving a second plaintext-adjacent copy of the vault behind is what "
        "S6 exists to prevent (D8).\n"
        f"  expected: neither of {copy_vault.name}, {copy_sidecar.name}\n"
        f"  actual:   {copy_vault.exists()}, {copy_sidecar.exists()}"
    )

    reopened = open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD)
    after = row_digests(reopened.connection)
    reopened.close()
    assert after == digests, (
        "the restored vault must hold what it held before the update — that is "
        "the only thing a rollback is for.\n"
        f"  expected: {digests}\n  actual:   {after}"
    )


def test_an_interrupted_restore_leaves_a_resumable_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-7's shape, applied to the way back out.

    ``restore_rollback_copy`` replaces two files, and a crash between them is
    the state that decides whether the order was right. Database first leaves
    the v1 database under the still-migration-pending v2 sidecar — § 13.3
    branch 3, where KEK-master opens it and the ladder simply restarts. The
    other order leaves a v1 sidecar over a database no v1 key opens, which
    reads to the user as a wrong password (§ 6).
    """
    vault_path, sidecar_path, key, digests = _every_route_exhausted(
        tmp_path, "interrupted-restore"
    )

    real_replace = os.replace
    calls: list[int] = []

    def fail_on_the_second(src: Any, dst: Any) -> None:
        calls.append(1)
        if len(calls) > 1:
            raise OSError(errno.ENOSPC, "no space left on device")
        real_replace(src, dst)

    monkeypatch.setattr(vault_migration.os, "replace", fail_on_the_second)
    with pytest.raises(OSError):
        vault_migration.restore_rollback_copy(vault_path, sidecar_path)
    monkeypatch.undo()

    assert read_sidecar(sidecar_path).get("sidecar_version") is not None, (
        "precondition: the crash landed BEFORE the sidecar was replaced — "
        "otherwise this leg proves nothing about the order.\n"
        "  expected: the migration-pending v2 sidecar still in place\n"
        f"  actual:   {sorted(read_sidecar(sidecar_path))}"
    )

    reopened = open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD)
    after = row_digests(reopened.connection)
    reopened.close()
    assert after == digests, (
        "a half-finished restore must still leave a pair that opens and holds "
        "what it held — § 13.3 branch 3 is what picks it up.\n"
        f"  expected: {digests}\n  actual:   {after}"
    )


# --------------------------------------------------------------------------- #
# FIBR-0310 R8 — an interrupted S6 must not strand the pre-upgrade copy
# --------------------------------------------------------------------------- #
def test_a_failed_s6_unlink_does_not_strand_the_pre_upgrade_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S6's two halves are ordered, and the removal is the one that goes first.

    ``migration_pending`` is the only thing that brings anything back to S6.
    Clearing it and THEN failing to unlink -- the disk-full and held-file class
    § 6 names, which ``_finish_quietly`` absorbs -- leaves the ``.pre-v2`` pair
    on disk with no bookkeeping left to remove it. Nothing ever tries again.

    That artefact is an encrypted copy of the whole vault that still opens
    under the master password of the day it was taken, sitting beside the live
    one and surviving every later password change. So the leg that matters is
    not "does the vault open" but "is the copy gone once there is room".
    """
    vault_path, sidecar_path, key, _digests = _fresh_v1_vault(tmp_path, "s6-unlink")

    def abort_before_s6(step: str) -> None:
        if step == "S6":
            raise _Abort("injected crash before S6")

    with pytest.raises(_Abort):
        migrate_to_v2(vault_path, sidecar_path, bytearray(key), on_step=abort_before_s6)

    copy_vault, copy_sidecar = rollback_copy_paths(vault_path, sidecar_path)
    assert copy_vault.exists() and copy_sidecar.exists(), (
        "precondition: S0's copy is on disk and S6 has not removed it -- that "
        "is the state this leg is about.\n"
        f"  expected: both of {copy_vault.name}, {copy_sidecar.name}\n"
        f"  actual:   {copy_vault.exists()}, {copy_sidecar.exists()}"
    )

    real_unlink = Path.unlink
    refuse = {"on": True}

    def no_space(self: Path, *args: Any, **kwargs: Any) -> None:
        if refuse["on"] and self.name.endswith(vault_migration.ROLLBACK_SUFFIX):
            raise OSError(errno.ENOSPC, "No space left on device")
        real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", no_space)

    open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD).close()

    stalled = read_sidecar(sidecar_path)
    assert stalled.get("migration_pending") is True, (
        "S6 could not remove the copy, and cleared the flag anyway. Nothing "
        "re-enters the ladder now, so the pre-upgrade copy stays beside the "
        "vault forever -- openable with the master password of the day it was "
        "taken, whatever the user changes it to later (FIBR-0310 R8).\n"
        "  expected: migration_pending still True\n"
        f"  actual:   {stalled}"
    )

    # And it really does finish once the disk has room, rather than merely
    # deferring: the flag being set is only worth anything if something acts
    # on it.
    refuse["on"] = False
    open_after_restart(vault_path, sidecar_path, MASTER_PASSWORD).close()

    assert not copy_vault.exists() and not copy_sidecar.exists(), (
        "the next unlock re-entered S6 and still left the copy behind.\n"
        "  expected: neither file\n"
        f"  actual:   {copy_vault.exists()}, {copy_sidecar.exists()}"
    )
    finished = read_sidecar(sidecar_path)
    assert finished.get("migration_pending") is not True, (
        "S6 removed the copy but never cleared the flag, so every later unlock "
        "re-enters the resume ladder for nothing.\n"
        "  expected: migration_pending absent or False\n"
        f"  actual:   {finished}"
    )


# --------------------------------------------------------------------------- #
# FIBR-0310 R9 — the copy is ONE file by the time it is restored
# --------------------------------------------------------------------------- #
def test_verifying_the_copy_leaves_it_with_no_wal(tmp_path: Path) -> None:
    """``restore_rollback_copy`` moves the database and its ``-wal`` separately,
    so a crash between them drops the tail -- a rollback quietly missing the
    user's most recent rows. Verification checkpoints the copy so there is only
    one file to move, and this leg is what makes that a guarantee rather than
    a side effect of closing the probe (FIBR-0310 R9).

    The rows in that tail are the assertion that matters. A copy checkpointed
    by DISCARDING its WAL would also leave no ``-wal``, and would be the very
    data loss this is about -- so the leg reads the tail back out of the copy
    afterwards.

    "Absent or empty" rather than absent, because the guarantee is about what
    the WAL still CARRIES. Measured 2026-08-25: the explicit
    ``wal_checkpoint(TRUNCATE)`` leaves a 0-byte ``-wal`` while the probe is
    open, and closing the probe removes the file. The first of those is the one
    that makes the tail safe; the second is SQLite tidying up, and a leg pinned
    to it would go red on a harmless change of that behaviour.
    """
    vault_path, sidecar_path, key, _digests = _fresh_v1_vault(tmp_path, "wal-free")

    # Reopen and write with the connection LEFT OPEN, so the copy is taken with
    # an outstanding WAL -- the case write_rollback_copy carries the WAL for.
    live = Vault(vault_path, sidecar_path)
    live.open(bytearray(key))
    live.connection.execute(
        "INSERT INTO accounts(name, type, created_at) VALUES (?, ?, ?)",
        ("in the tail", "current", "2026-02-01T00:00:00+00:00"),
    )
    live.connection.commit()
    assert _suffixed(vault_path, "-wal").exists(), (
        "precondition: the live vault must have an outstanding WAL, or the "
        "copy this leg is about has no tail to lose."
    )

    copy_vault, copy_sidecar = write_rollback_copy(vault_path, sidecar_path)
    live.close()
    assert _suffixed(copy_vault, "-wal").exists(), (
        "precondition: write_rollback_copy carries the live WAL to the copy, "
        "which is the file the restore would then have to move separately.\n"
        f"  expected: {_suffixed(copy_vault, '-wal').name}\n"
        "  actual:   absent"
    )

    verify_rollback_copy(copy_vault, copy_sidecar, bytearray(key))

    for suffix in ("-wal", "-shm"):
        sibling = _suffixed(copy_vault, suffix)
        size = sibling.stat().st_size if sibling.exists() else 0
        assert size == 0, (
            f"the verified copy's {suffix} still carries data, so restoring it "
            "is two os.replace calls with a tail riding on the second, and a "
            "crash between them drops it.\n"
            f"  expected: {suffix} absent or empty\n"
            f"  actual:   {size} bytes"
        )

    probe = Vault(copy_vault, copy_sidecar)
    probe.open(bytearray(key))
    names = [
        row[0]
        for row in probe.connection.execute("SELECT name FROM accounts").fetchall()
    ]
    probe.close()
    assert "in the tail" in names, (
        "the WAL is gone but its rows went with it -- the copy was truncated "
        "rather than checkpointed, which is the data loss this leg exists to "
        "prevent, arrived at from the other side.\n"
        "  expected: the row committed to the WAL, folded into the copy\n"
        f"  actual:   accounts = {names}"
    )


# --------------------------------------------------------------------------- #
# FIBR-0310 P3 — the rollback copy is owner-only, and cannot be redirected
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(os.name != "posix", reason="file modes are a POSIX question")
def test_the_rollback_copy_is_never_world_readable(tmp_path: Path) -> None:
    """A byte-for-byte copy of the whole vault, at the process umask.

    ``shutil.copyfile`` creates at the umask and the ``chmod`` came AFTER, so
    the copy sat world-readable for as long as the copy took -- which on a real
    vault is the whole exposure, not an instant. ``vault.py`` pre-creates
    ``0o600`` in two places for exactly this reason (FIBR-0310 P3).

    The WAL sibling is checked too, and it is the leg that actually bites.
    P3 described a window -- world-readable for the length of the copy, closed
    by the chmod afterwards -- and that is true of the database and the sidecar.
    The WAL copy had no chmod at ALL, so it was world-readable permanently,
    holding the same rows as the database beside it. Measured 2026-08-25 by
    running this leg against the pre-P3 code.
    """
    vault_path, sidecar_path, key, _digests = _fresh_v1_vault(tmp_path, "copy-mode")

    live = Vault(vault_path, sidecar_path)
    live.open(bytearray(key))
    live.connection.execute(
        "INSERT INTO accounts(name, type, created_at) VALUES (?, ?, ?)",
        ("wal row", "current", "2026-02-01T00:00:00+00:00"),
    )
    live.connection.commit()
    copy_vault, copy_sidecar = write_rollback_copy(vault_path, sidecar_path)
    live.close()

    copied_wal = _suffixed(copy_vault, "-wal")
    assert copied_wal.exists(), (
        "precondition: the live WAL must have been carried to the copy, or "
        "this leg checks the mode of a file that is not there."
    )
    for path in (copy_vault, copy_sidecar, copied_wal):
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, (
            f"{path.name} is readable by other accounts on this machine. It is "
            "a copy of the user's whole vault, sitting beside the original.\n"
            "  expected: 0o600\n"
            f"  actual:   {mode:#o}"
        )


@pytest.mark.skipif(os.name != "posix", reason="symlinks are a POSIX question here")
def test_a_symlink_at_the_copy_path_does_not_redirect_the_vault(
    tmp_path: Path,
) -> None:
    """The copy path is unlinked and then written, and a symlink planted in
    between was FOLLOWED -- writing a copy of the vault wherever it pointed.

    ``O_EXCL`` refuses a path that exists at all by the time the open happens,
    which includes a symlink, and ``O_NOFOLLOW`` says so outright. The old
    ``shutil.copyfile`` had neither (FIBR-0310 P3).
    """
    vault_path, sidecar_path, key, _digests = _fresh_v1_vault(tmp_path, "symlink")
    elsewhere = tmp_path / "elsewhere.bin"
    elsewhere.write_bytes(b"not the vault")

    # The race, made deterministic: the symlink is already in place when the
    # copy runs, which is the state the unlink/copy window can produce.
    copy_vault, _copy_sidecar = rollback_copy_paths(vault_path, sidecar_path)

    real_unlink = Path.unlink

    def relink(self: Path, *args: Any, **kwargs: Any) -> None:
        real_unlink(self, *args, **kwargs)
        if self == copy_vault:
            self.symlink_to(elsewhere)  # planted in the window

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "unlink", relink)
        with pytest.raises(OSError):
            write_rollback_copy(vault_path, sidecar_path)

    assert elsewhere.read_bytes() == b"not the vault", (
        "the vault was copied THROUGH a symlink planted at the rollback path, "
        "so a copy of the user's whole vault was written to a location an "
        "attacker chose.\n"
        "  expected: the target untouched\n"
        f"  actual:   {len(elsewhere.read_bytes())} bytes"
    )
