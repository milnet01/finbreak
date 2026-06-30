# Fin_Break — Project instructions for Claude Code

Scaffolded from the **Ants App-Build** template; follows the
[`app-workflow`](~/.claude/skills/app-workflow/SKILL.md)
skill.

## Where state lives

Read these in order on every session start:

1. **This file** — stable rules and conventions.
2. **`.claude/workflow.md`** — live status header (current
   phase, active item, step number, blockers, last-update
   timestamp). After reading, **summarise back to the user**
   before doing any work.
3. **`docs/standards/{coding,documentation,testing,commits}.md`**
   — the four shareable v1 standards.
4. **`docs/specs/<active-id>.md`** — the contract for the
   currently-active roadmap item.
5. **`docs/audit-allowlist.md`** — read **additionally** before
   invoking `/audit` or `/indie-review` so already-confirmed
   project-specific false positives aren't re-flagged. The
   allowlist is the closed-loop memory for this project — see
   the [app-workflow skill](~/.claude/skills/app-workflow/SKILL.md)
   "False-positive learning" section.

## Closing a phase

Run **`/close-phase`** once steps 1–4 of the per-phase loop
are done — see SKILL.md for the full description.

## Tech stack

Chosen in Phase A (see [`docs/discovery.md`](docs/discovery.md)
for the full table and reasoning):

- **Language:** Python 3.12+
- **GUI:** PySide6 (LGPL) — dark-themed Qt desktop (ADR-0002)
- **Encrypted storage:** SQLCipher (SQLite + AES-256), keyed by an
  **Argon2id**-derived key (`argon2-cffi`) (ADR-0003)
- **PDF:** Qt engine (`QTextDocument` + `QPdfWriter`) for export;
  `pikepdf` for AES-256 export-locking and in-memory decrypt of
  locked input statements (ADR-0004)
- **Import parsers:** stdlib `csv` + per-bank mapping profiles
  (ADR-0005), `ofxparse` (OFX), `pdfplumber` (PDF)
- **Tests / lint:** pytest (+ pytest-qt), ruff
- **Security gate:** bandit, pip-audit, gitleaks (see
  [`docs/security-model.md`](docs/security-model.md))
- **Packaging:** PyInstaller (Windows `.exe`, macOS `.app`/`.dmg`),
  AppImage + Flatpak/Flathub (Linux) (ADR-0007)
- **License:** MIT; local-only, no network.

## Build and test

(Filled in at P01 — Bootstrap, once `pyproject.toml` +
`scripts/ci-local.sh` exist. The harness contract is specified in
[`docs/specs/FIBR-0001.md`](docs/specs/FIBR-0001.md).)

## Commit conventions

Per [`docs/standards/commits.md § 1.1`](docs/standards/commits.md):
every commit subject is `<ID>: <description>`, where `<ID>` is
either a phase ID (`P##`, `FP##`, `DS##`, `DOC##`, `R##`) or a
stable per-bullet ID for ROADMAP_FORMAT v1 projects
(`FIBR-NNNN`).

Every implementation phase ends with `git tag -a <ID>-complete`
on the closing commit. Tags are local until the user explicitly
authorises a push.

## Push policy

Inherits from the user's global `~/.claude/CLAUDE.md` § 6
(public repos: push freely; private: batch + ask). Detect repo
visibility once per session via
`gh repo view --json visibility -q .visibility` and cache;
the result is recorded in `.claude/workflow.md` § 1 status
header.

## Module map

(Filled in at P01 — Bootstrap, once `src/` is non-empty.)

## Resumption flow — MANDATORY summarise-back

Per the app-workflow skill:

1. **Parallel batch:** read this file + `.claude/workflow.md`
   status header + active-item details (one tool-call batch).
2. Once `Kind` is known from the active item, read the
   matching `docs/standards/<which>.md` (single read).
3. **Summarise back to the user:** "We're on `<ID>` step
   `<N>`, last did `<X>`, next is `<Y>`."
4. Wait for confirm or redirect.

**Never skip step 3.** Catching state-recovery errors before
working is cheaper than corrective rounds later.

## Standards reference

The four standards (`coding`, `documentation`, `testing`,
`commits`) plus `roadmap-format` live in
[`docs/standards/`](docs/standards/) — see its
[README](docs/standards/README.md) for the index, the
closed-loop diagram, and which kinds each governs.
