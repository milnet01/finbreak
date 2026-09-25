"""Regenerate the FIBR-0302 older-release ``.fbk`` fixtures.

This is a **skipped-by-default manual helper**, NOT part of the test suite —
it has no ``test_`` functions and is never collected by pytest. It exists so
the two opaque ``.fbk`` blobs have documented provenance and can be
regenerated rather than trusted as unauditable binaries.

**Why it must run against an OLD WORKTREE's source, not this one.** FIBR-0302
wants a backup written by an *old release's own code* — its own
``BackupService.export_backup``, its own ``AuthService.first_run``, its own
Argon2 params — so the fixture proves what an old build actually wrote, not
what today's build would write if asked to imitate one. That means running
this script with an old tag's ``src/`` FIRST on ``sys.path``, via
``PYTHONPATH``, so every ``finbreak.*`` import below resolves to the old
tag's module rather than this checkout's. ``sqlcipher3-wheels==0.5.7`` is
pinned identically at every tag used here (checked 2026-09-25 across
v0.1.12, v0.1.22 and today), so — unlike the FIBR-0015 fixture beside this
one — no dependency swap is needed, only the source swap.

To regenerate (only needed if the fixture shape or the wanted tag changes):

    git worktree add /tmp/fbk-v0.1.22 v0.1.22
    PYTHONPATH=/tmp/fbk-v0.1.22/src .venv/bin/python \\
        tests/fixtures/backup_restore/_generate_fibr0302_fixture.py \\
        --tag v0.1.22 --schema 13 \\
        --out tests/fixtures/backup_restore/v0.1.22-schema13.fbk
    git worktree remove --force /tmp/fbk-v0.1.22

    git worktree add /tmp/fbk-v0.1.12 v0.1.12
    PYTHONPATH=/tmp/fbk-v0.1.12/src .venv/bin/python \\
        tests/fixtures/backup_restore/_generate_fibr0302_fixture.py \\
        --tag v0.1.12 --schema 8 \\
        --out tests/fixtures/backup_restore/v0.1.12-schema8.fbk
    git worktree remove --force /tmp/fbk-v0.1.12

The data is fully synthetic (an invented account + two invented transactions)
and the passwords below are documented test passwords — there is no real
financial data and no real secret here (testing.md § 6,
real-bank-data-never-in-prose).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The one master/backup password pair shared by both fixtures and by the
# regression test that restores them (tests/features/backup/test_backup.py).
MASTER_PASSWORD = "fibr0302-old-release-master-pw"
BACKUP_PASSWORD = "fibr0302-old-release-backup-pw"
BASE_CURRENCY = "ZAR"
SENTINEL_ACCOUNT_NAME = "FIBR0302 Old-Release Savings"
SENTINEL_ACCOUNT_TYPE = "savings"
SENTINEL_TXN_1_DESCRIPTION = "FIBR0302-OLD-RELEASE-SENTINEL-1"
SENTINEL_TXN_1_AMOUNT_MINOR = -515050
SENTINEL_TXN_2_DESCRIPTION = "FIBR0302-OLD-RELEASE-SENTINEL-2"
SENTINEL_TXN_2_AMOUNT_MINOR = 250000


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tag",
        required=True,
        help="the git tag this run must be sourced from (recorded in the output, "
        "not itself checked)",
    )
    ap.add_argument(
        "--schema",
        required=True,
        type=int,
        help="the LATEST_SCHEMA_VERSION this tag's own migrations module "
        "reports, asserted before writing anything",
    )
    ap.add_argument("--out", required=True, type=Path, help="destination .fbk path")
    args = ap.parse_args()

    import finbreak
    from finbreak.migrations import LATEST_SCHEMA_VERSION
    from finbreak.services.accounts import AccountService
    from finbreak.services.auth import AuthService
    from finbreak.services.backup import BackupService

    if LATEST_SCHEMA_VERSION != args.schema:
        raise SystemExit(
            f"refusing to regenerate: imported finbreak.migrations reports "
            f"LATEST_SCHEMA_VERSION={LATEST_SCHEMA_VERSION}, expected {args.schema} "
            f"for {args.tag}. Is PYTHONPATH pointed at the {args.tag} worktree's "
            "src/, ahead of any installed finbreak?"
        )

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        db = tmp / "vault.db"
        sidecar = tmp / "vault.kdf.json"
        fbk = tmp / "out.fbk"

        auth = AuthService(db, sidecar)
        auth.first_run(bytearray(MASTER_PASSWORD, "utf-8"), BASE_CURRENCY)
        acct = AccountService(auth.vault).add_account(
            SENTINEL_ACCOUNT_NAME, SENTINEL_ACCOUNT_TYPE
        )
        conn = auth.vault.connection
        conn.execute(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                acct.id,
                "2026-06-01",
                SENTINEL_TXN_1_AMOUNT_MINOR,
                SENTINEL_TXN_1_DESCRIPTION,
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.execute(
            "INSERT INTO transactions"
            "(account_id, occurred_on, amount_minor, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                acct.id,
                "2026-06-15",
                SENTINEL_TXN_2_AMOUNT_MINOR,
                SENTINEL_TXN_2_DESCRIPTION,
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()

        BackupService(auth.vault, auth).export_backup(fbk, BACKUP_PASSWORD)
        auth.lock()

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(fbk.read_bytes())

    app_version = getattr(finbreak, "__version__", "?")
    print(
        f"regenerated {args.out} from {args.tag} (finbreak.__version__={app_version}, "
        f"schema {LATEST_SCHEMA_VERSION})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
