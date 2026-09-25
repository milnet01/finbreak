# FIBR-0302 older-release `.fbk` fixtures

Two `.fbk` backups, each written by an **older release's own code** —
`BackupService.export_backup` as it existed at that tag, not a simulation of
it by today's code — so `tests/features/backup/test_backup.py`'s INV-20 can
prove the surface `docs/standards/versioning.md` § 2 calls a MAJOR break ("a
backup taken on any earlier release cannot be restored") actually still
works, rather than assuming it because every other backup test in the suite
round-trips within a single build.

| File | Tag | Schema at that tag | What it is |
|------|-----|----|------------|
| `v0.1.22-schema13.fbk` | `v0.1.22` | 13 | The last release **before** FIBR-0019's key envelope — a flat v1-sidecar-era build's backup. |
| `v0.1.12-schema8.fbk` | `v0.1.12` | 8 | Several migrations further back, well before the v1 sidecar shape stabilised. |

Both are the same shape as `tests/features/backup/spec.md` INV-1 describes: a
3-entry zip (`manifest.json` / `params.json` / `vault.db`), with one synthetic
account (`FIBR0302 Old-Release Savings`) and two synthetic transactions
(`FIBR0302-OLD-RELEASE-SENTINEL-1` / `-2`). **Nothing here is real financial
data** — the account name, amounts and dates are all invented
(testing.md § 6, `real-bank-data-never-in-prose`).

Both fixtures share the same test passwords, defined once in
`_generate_fibr0302_fixture.py` and imported by the regression test:

- Backup password: `fibr0302-old-release-backup-pw`
- Master password **at export time** (not what the test restores under —
  restore always sets up a NEW master password, per INV-3):
  `fibr0302-old-release-master-pw`

## Why the source has to be an old worktree, not a pip swap

`tests/fixtures/windows_build/` (FIBR-0015) has the same shape but swaps a
**dependency** (`sqlcipher3-binary` → `sqlcipher3-wheels`) while holding the
source fixed. FIBR-0302 is the opposite axis: `sqlcipher3-wheels==0.5.7` is
pinned identically at `v0.1.12`, `v0.1.22` and today (checked 2026-09-25), so
no dependency swap is needed — what has to vary is the **source**, because the
fixture must be what that release's own `export_backup`, `AuthService.first_run`
and Argon2 params actually wrote, not today's code imitating them.

## Provenance / regeneration

`_generate_fibr0302_fixture.py` is a skipped-by-default manual helper (no `test_`
functions, never collected by pytest). It refuses to run unless the imported
`finbreak.migrations.LATEST_SCHEMA_VERSION` matches the `--schema` it was told
to expect — a `PYTHONPATH` pointed at the wrong worktree (or none) fails loudly
instead of silently writing a fixture at the wrong schema.

```bash
git worktree add /tmp/fbk-v0.1.22 v0.1.22
PYTHONPATH=/tmp/fbk-v0.1.22/src .venv/bin/python \
    tests/fixtures/backup_restore/_generate_fibr0302_fixture.py \
    --tag v0.1.22 --schema 13 \
    --out tests/fixtures/backup_restore/v0.1.22-schema13.fbk
git worktree remove --force /tmp/fbk-v0.1.22

git worktree add /tmp/fbk-v0.1.12 v0.1.12
PYTHONPATH=/tmp/fbk-v0.1.12/src .venv/bin/python \
    tests/fixtures/backup_restore/_generate_fibr0302_fixture.py \
    --tag v0.1.12 --schema 8 \
    --out tests/fixtures/backup_restore/v0.1.12-schema8.fbk
git worktree remove --force /tmp/fbk-v0.1.12
```

Never check out an old tag in the live working tree to do this — always a
throwaway `git worktree`, removed afterwards.

## Saved import profiles — out of scope here

The ROADMAP item (FIBR-0302) that wanted these fixtures also notes saved
import profiles (FIBR-0007) round-trip same-build for the identical reason
backups did. That is **not** covered by these fixtures or by INV-20 — it
would need its own older-release fixture (a vault carrying a saved profile,
opened by today's build) and is left for a separate item.
