"""v1 → v2 vault migration — the § 13 S0..S6 sequence (FIBR-0019).

**STUB — FIBR-0019 is not implemented.** Every function raises
``NotImplementedError`` so ``tests/features/recovery_key/test_migration.py``
executes against a real call rather than dying at import (``testing.md`` § 1).

The spec names no module for this sequence; ``services/vault_migration.py`` is
this suite's choice, recorded in ``tests/features/recovery_key/spec.md``. Move
it if implementation prefers another home — the three seams below are what the
tests bind to, not the path.

``slots.master`` inherits the v1 vault's OWN salt and OWN recorded cost
parameters (§ 13.1), so the key the unlock path has already derived *is*
KEK-master: nothing has to carry the plaintext master password past derivation,
and a later-raised Argon2 pin cannot strand an existing vault.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

# The § 13.2 step names, in order. ``on_step`` is called with each one.
STEPS = ("S0", "S1", "S2", "S3", "S4", "S5", "S6")

# Suffixes § 13.2 fixes: the D8 rollback copy (S0, removed at S6) and the
# replacement database being built (S1, unlinked first so a stale one from an
# interrupted run cannot wedge every retry with FileExistsError).
ROLLBACK_SUFFIX = ".pre-v2"
MIGRATING_SUFFIX = ".migrating"


def write_rollback_copy(vault_path: Path, sidecar_path: Path) -> tuple[Path, Path]:
    """S0, first half — byte-copy the live pair to ``*.pre-v2`` and fsync both.

    A byte copy of an already-encrypted pair, deliberately NOT a ``.fbk``: it
    needs no new backup password, so nothing is prompted for at the first unlock
    after an update (D8).
    """
    raise NotImplementedError("FIBR-0019")


def verify_rollback_copy(
    copy_vault_path: Path, copy_sidecar_path: Path, key: bytearray
) -> None:
    """S0, second half — OPEN the copy with the key already in hand and read
    from it. Verifying it by opening it is the whole of INV-13: a truncated copy
    that merely exists reads as a rollback route and is worse than none."""
    raise NotImplementedError("FIBR-0019")


def migrate_to_v2(
    vault_path: Path,
    sidecar_path: Path,
    key: bytearray,
    *,
    on_step: Callable[[str], None] | None = None,
) -> None:
    """Run § 13.2's S0..S6 against an open-able v1 vault.

    ``key`` is the v1 database key the unlock path already derived — which
    § 13.1 makes KEK-master unchanged.

    ``on_step`` is called with each step name **immediately before that step
    runs**, so a caller (or a test) that raises from ``on_step("S2")`` aborts
    the migration with S1 complete and S2 not started.
    """
    raise NotImplementedError("FIBR-0019")
