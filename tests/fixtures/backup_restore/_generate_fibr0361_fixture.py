"""Regenerate the FIBR-0361 older-release saved-import-profile fixture.

A **skipped-by-default manual helper**, NOT part of the test suite — it has no
``test_`` functions and is never collected by pytest. It gives the opaque
``.fbk`` blob a documented provenance, the same way
``_generate_fibr0302_fixture.py`` does for the backup fixtures beside it.

It must run against an OLD WORKTREE's source, so the saved profile is what that
release's own ``ImportService.save_profile`` wrote — its own ``signature_for``,
its own column layout — and not today's code imitating it. See this
directory's ``README.md`` for why a worktree and not a pip swap.

To regenerate:

    git worktree add /tmp/fbk-v0.1.12 v0.1.12
    PYTHONPATH=/tmp/fbk-v0.1.12/src .venv/bin/python \\
        tests/fixtures/backup_restore/_generate_fibr0361_fixture.py \\
        --tag v0.1.12 --schema 8 \\
        --out tests/fixtures/backup_restore/v0.1.12-schema8-import-profile.fbk
    git worktree remove --force /tmp/fbk-v0.1.12

The bank, header, mapping and passwords are invented — no real financial data
and no real secret (testing.md § 6, real-bank-data-never-in-prose).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MASTER_PASSWORD = "fibr0361-old-release-master-pw"
BACKUP_PASSWORD = "fibr0361-old-release-backup-pw"
BASE_CURRENCY = "ZAR"

# One saved bank layout. The debit/credit pair and a day-first date format
# exercise more of the stored mapping than a single signed amount column would.
PROFILE_NAME = "FIBR0361 Old-Release Bank"
HEADER = ["Posting Date", "Narrative", "Money Out", "Money In", "Balance"]
DATE_COLUMN = "Posting Date"
DESCRIPTION_COLUMN = "Narrative"
DEBIT_COLUMN = "Money Out"
CREDIT_COLUMN = "Money In"
DATE_FORMAT = "%d/%m/%Y"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", required=True, help="the git tag this run is sourced from")
    ap.add_argument(
        "--schema",
        required=True,
        type=int,
        help="the LATEST_SCHEMA_VERSION this tag's own migrations module reports, "
        "asserted before writing anything",
    )
    ap.add_argument("--out", required=True, type=Path, help="destination .fbk path")
    args = ap.parse_args()

    import finbreak
    from finbreak.migrations import LATEST_SCHEMA_VERSION
    from finbreak.models import ColumnMapping
    from finbreak.services.auth import AuthService
    from finbreak.services.backup import BackupService
    from finbreak.services.import_ import ImportService

    if LATEST_SCHEMA_VERSION != args.schema:
        raise SystemExit(
            f"refusing to regenerate: imported finbreak.migrations reports "
            f"LATEST_SCHEMA_VERSION={LATEST_SCHEMA_VERSION}, expected {args.schema} "
            f"for {args.tag}. Is PYTHONPATH pointed at the {args.tag} worktree's "
            "src/, ahead of any installed finbreak?"
        )

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fbk = tmp / "out.fbk"

        auth = AuthService(tmp / "vault.db", tmp / "vault.kdf.json")
        auth.first_run(bytearray(MASTER_PASSWORD, "utf-8"), BASE_CURRENCY)
        ImportService(auth.vault).save_profile(
            PROFILE_NAME,
            HEADER,
            ColumnMapping(
                date_column=DATE_COLUMN,
                description_column=DESCRIPTION_COLUMN,
                amount_column=None,
                debit_column=DEBIT_COLUMN,
                credit_column=CREDIT_COLUMN,
                date_format=DATE_FORMAT,
                invert_amount=False,
            ),
        )
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
