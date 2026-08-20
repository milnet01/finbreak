# Contributing to finbreak

Thanks for considering a contribution. This project follows a
disciplined, document-driven workflow — please read this file
before opening an issue or PR so we're on the same page.

## Quick orientation

- **`ROADMAP.md`** — what's planned, with stable IDs.
- **`CHANGELOG.md`** — what's shipped (Keep-a-Changelog).
- **`docs/standards/`** — coding, naming, dependencies,
  documentation, testing, commits, versioning, plus the
  `roadmap-format` sub-spec. The shareable v1 contracts the
  project follows.
- **`docs/specs/`** — per-feature specs.
- **`docs/decisions/`** — Architecture Decision Records.
- **`.claude/workflow.md`** — live workflow state and rules.

## Reporting bugs

**A security bug is the exception — do not open a public issue
for one.** If the bug could leak, corrupt or destroy someone's
vault, or let a malicious statement file do something it should
not, report it privately instead:
[`SECURITY.md`](SECURITY.md) says how and what to expect.

For everything else, open an issue using the **Bug report**
template. Please include:

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

[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Contributor Covenant
2.1 — is the one that governs, and it applies to issues, PRs and
every other project space. The short version has not changed:
disagreements are fine, personal attacks are not, and the
maintainer will close anything that crosses that line.

Report a problem privately through the
[advisory form](https://github.com/milnet01/finbreak/security/advisories/new),
not in a public thread.

## Questions

Open a `Question` issue (use the feature-request template and
prefix the title with `[question]`).
