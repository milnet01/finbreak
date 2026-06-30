# Contributing to finbreak

Thanks for considering a contribution. This project follows a
disciplined, document-driven workflow — please read this file
before opening an issue or PR so we're on the same page.

## Quick orientation

- **`ROADMAP.md`** — what's planned, with stable IDs.
- **`CHANGELOG.md`** — what's shipped (Keep-a-Changelog).
- **`docs/standards/`** — coding, documentation, testing,
  commits. The four shareable v1 contracts the project follows.
- **`docs/specs/`** — per-feature specs.
- **`docs/decisions/`** — Architecture Decision Records.
- **`.claude/workflow.md`** — live workflow state and rules.

## Reporting bugs

Open an issue using the **Bug report** template. Please
include:

- The project version (`grep version README.md` or the latest
  release tag).
- Steps to reproduce — minimal, deterministic.
- What you expected vs what happened.
- Logs, stack traces, or screenshots if relevant.

If the bug already has a corresponding `known-issue-NNN` in
`docs/known-issues.md`, mention it.

## Suggesting a feature

Open an issue using the **Feature request** template. Be
explicit about the user story ("a person who … wants to … so
that …"). Features that fit the existing roadmap are easier to
land than features that require a design refresh.

## Submitting a pull request

Before opening a PR:

1. Make sure the change is anchored in a roadmap item with a
   stable ID. If there isn't one, propose it as an issue first
   so we can agree on scope.
2. Follow `docs/standards/commits.md` for commit subjects:
   `<ID>: <description>`.
3. Follow `docs/standards/coding.md` for the project's coding
   conventions.
4. Follow `docs/standards/testing.md` for test discipline:
   tests fail before code that makes them pass.
5. Run the project's lint, format, and test commands locally —
   PR CI will reject otherwise.

PRs that don't follow the standards may be asked to update
before review.

## Code of conduct

Be respectful. Disagreements are fine; personal attacks are
not. The project maintainer reserves the right to close issues
or PRs that violate this.

## Questions

Open a `Question` issue (use the feature-request template and
prefix the title with `[question]`).
