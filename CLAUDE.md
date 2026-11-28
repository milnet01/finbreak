# finbreak — Project instructions for Claude Code

Follows `~/.claude/workflow.md`: its states, its gates, and § 6's conditions
for finishing an item. No phase tags (`<ID>-complete`) are made any more.

## Where state lives

**Read 1–3 at session start; 4–6 when you need them.** § Resumption flow is
the procedure.

1. **This file.**
2. **The roadmap DB — the source of truth on current state.** `ROADMAP.md` is
   generated from it and committed. **Never hand-edit `ROADMAP.md`**: every
   `roadmap_log` write re-renders the whole file over your edit.
   - Query with `roadmap_query`, never by reading the file. One call over
     every open item spills, so narrow it: `status:"active"` plus `section:`
     or `kind:`, with `bullet_fields: ["id","status","kind","headline_oneline"]`.
     `mode:"section_index" status:"active" slugs_only:true` lists the
     sections holding open work. `mode:"headline_only"` cannot carry `kind`.
   - A filtered call withholds bodies; an `id` / `ids` fetch returns them.
   - Keep a bold headline on **one line**: a wrapped one renders as a new
     list item.
   - **Before a write and after every flip or annotate, read the item back**
     with `roadmap_query id`: a write reports success without its body, and
     a note can land mid-bullet.
   - **There is no delete verb.** A git revert leaves the item in the store
     and the next render puts it back. Get an `append` right first time.
   - Before `roadmap_migrate`, read
     [`.claude/rules/roadmap-migrate.md`](.claude/rules/roadmap-migrate.md):
     a real run can write over correct items.
3. **Which item is active.** Exactly one 🚧 → that one. Several → ask the
   user. None → say so and ask which planned item to take. **Flip an item to
   🚧 with `roadmap_log` when you start it**; nothing else records it.
4. **The one `docs/standards/` file the active item's `Kind` maps to** in
   [`docs/standards/README.md`](docs/standards/README.md), plus
   `versioning.md` for `Kind: release`.
5. **`docs/specs/<active-id>-<topic>.md`**, where the item has one.
6. **`docs/audit-allowlist.md`** — read before `check-code` or `review-code`,
   so confirmed false positives are not re-flagged. `close-findings` writes
   new entries.

## Tech stack

Python 3.12+, PySide6, SQLCipher keyed by Argon2id, pikepdf, pytest
(+ pytest-qt), ruff, mypy. The full table and ADRs:
[`docs/discovery.md`](docs/discovery.md). **The app is local-only** apart from
an opt-in, off-by-default update check confined to `src/finbreak/services/update_fetch.py`
(FIBR-0054). Flathub is dropped (FIBR-0159).

## Build and test

Setup, pinned binaries, and what to do when `./scripts/ci-local.sh` exits 127:
[`.claude/rules/gate.md`](.claude/rules/gate.md).

```bash
./scripts/ci-local.sh            # the full gate CI runs; a green pytest alone is not green (mypy)
pytest -k package_imports        # one test by keyword, or by node id
python -m finbreak --self-test   # Qt, SQLCipher and qpdf load in-process
./scripts/ci-local.sh --build    # gate plus freeze + clean-room container test (needs podman/docker)
```

The gate runs `pytest -m "not perf"` on up to 6 workers
(`FINBREAK_TEST_WORKERS` overrides), with a 300s limit per test.

**Real numbers: `.corpus-numbers`.** The leak guard for real account, card and
ID numbers needs a gitignored `.corpus-numbers` that only the user writes, in
an editor. **Never print, echo or quote its contents, type the numbers on a
command line, redirect them to a tracked file, or put them in a commit
message, spec or ROADMAP entry.** Without the file the guard's test skips.
The recipe and the one sanctioned read:
[`.claude/rules/corpus-numbers.md`](.claude/rules/corpus-numbers.md).

**The pre-push hook runs the gate on every push.** A fresh clone enables it
once with `git config core.hooksPath .githooks`. The hook:

- refuses a tree with uncommitted or untracked files, or a pushed commit that
  is not the one checked out. Commit, stash or remove them first;
- scans each pushed commit for secrets with `gitleaks git`, and for the real
  numbers where `.corpus-numbers` exists;
- skips a tag-only push, and runs only the documentation checks on a push
  that changes only `.md` files. Neither needs `--no-verify`.

A `pip-audit` timeout (pypi or osv.dev) can fail it on a non-finding: retry,
or `git push --no-verify` for that transient case. **Any other `--no-verify`
needs the user's say-so.** Read `gate.md` before a tag push, or
before pushing a dependency or CI change.

## Commits and push

Commit subject: `<ID>: <description>`, with `<ID>` a `FIBR-NNNN`
([`docs/standards/commits.md`](docs/standards/commits.md) § 1.1).

**This repo is public: push freely, tags included.** Use `--follow-tags`,
never `--tags`, which publishes every local tag.

### Doc-only pushes skip the FULL gate, never the prose checks

This section is the standing authorisation `commits.md` § 2.3 requires for the
hook to skip the rest of the gate on a doc-only push (user directives
2026-08-05, 2026-08-18). GitHub CI skips such a push too. To run the same
checks by hand:

```bash
./scripts/ci-local.sh --docs     # DOCS_SUITES + gitleaks --redact; the hook runs the same
```

- The suite list lives in `scripts/ci-local.sh`'s `DOCS_SUITES` alone. Its
  `gitleaks` line keeps `--redact`, or a hit prints the secret.
- **A suite belongs in it if it reads a tracked doc's contents or requires one
  to exist.** Do not re-derive the list by grep, and do not claim no Python
  stage reads prose.
- Add a new such suite to both `DOCS_SUITES` and the `_READS_PROSE` ledger in
  `tests/features/prose_checks/`, which fails when they disagree.
- How the hook decides a push is doc-only, and what each suite reads:
  [`gate.md`](.claude/rules/gate.md). Read it before changing
  `.githooks/pre-push`.
- **A code change never skips the full gate, however small.**

## Cutting a release

**Before any release step — `cut-release`, `scripts/release-linux.sh`,
`scripts/release-windows.sh` or a version bump — read
[`.claude/rules/release.md`](.claude/rules/release.md).** A release tag
`v<X.Y.Z>` is pushed as part of the release, without asking.

## Spec filenames

Name a new spec `docs/specs/<ID>-<topic>.md` (user decision 2026-08-05).
`naming.md` still says `docs/specs/<ID>.md`; that rule is superseded. Why it is
not amended yet: [`.claude/rules/spec-filenames.md`](.claude/rules/spec-filenames.md).

## Resumption flow — MANDATORY summarise-back

1. **`roadmap_query` for the open items**, narrowed per § Where state lives
   item 2. Item 3 says which is active.
2. Read the standard item 4 maps its `Kind` to.
3. **Summarise back:** "We're on `<ID>`, last did `<X>`, next is `<Y>`."
   `<X>` from `git log --oneline -5`; `<Y>` from the latest note in the active
   item's body.
4. Wait for confirm or redirect, **unless the user pasted a hand-off note**:
   that note is the go-ahead, so summarise and start its next step (user,
   2026-11-11). Nothing checks this.

**Never skip step 3.**

The story behind these rules is in
[`docs/history/claude-md.md`](docs/history/claude-md.md); read it before
changing one. This file's review log:
[`docs/reviews/CLAUDE-md-review-log.md`](docs/reviews/CLAUDE-md-review-log.md).
