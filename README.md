# finbreak

> A private, offline desktop app that breaks down where your money
> goes — from your own bank statements, with no bank linking and
> nothing ever leaving your machine.

[![Status](https://img.shields.io/badge/status-pre--alpha-orange)]()
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Current version: **0.0.0** — see [CHANGELOG](CHANGELOG.md) for shipped
work, [ROADMAP](ROADMAP.md) for what's coming, and
[docs/standards/](docs/standards/) for the six shareable v1
standards (coding · naming · dependencies · documentation · testing ·
commits) the project follows.

## Status

In active development (pre-alpha — nothing released yet). The encrypted
security spine (**P02**) and the accounts + category-tree + forward-migration
layers (**P03–P04**) have shipped; **P05 — CSV import** is underway (its
spec is `/cold-eyes`-converged and the test-first build is starting). See
[ROADMAP.md](ROADMAP.md) for the full P01–P13 build order,
[CHANGELOG.md](CHANGELOG.md) for what's shipped, and
[.claude/workflow.md](.claude/workflow.md) for live state.

**To resume work:** open a terminal in this directory and run `claude`,
then type `continue`. Claude will summarise current state back to you
before doing any work — confirm or correct that summary; never let Claude
resume work without it.

## Features

(filled out once features ship; reflects shipped capability, not
intent — nothing has shipped at v0.0.0)

## Install

(filled out once there's an installable artifact — P13 packaging)

## Quickstart

(filled out at P02 — Vertical slice)

## Documentation

- [ROADMAP](ROADMAP.md) — what's planned, with stable IDs.
- [CHANGELOG](CHANGELOG.md) — what's shipped, Keep-a-Changelog
  format with an `[Unreleased]` block at the top.
- [docs/discovery.md](docs/discovery.md) — Phase A output:
  problem, users, success criteria, tech stack, out of scope.
- [docs/design.md](docs/design.md) — Phase B output: architecture
  diagram, components, data flow.
- [docs/decisions/](docs/decisions/) — Architecture Decision
  Records. Why we chose X over Y.
- [docs/glossary.md](docs/glossary.md) — domain terms used in
  code and docs.
- [docs/known-issues.md](docs/known-issues.md) — findings
  deferred because they're blocked by an unbuilt feature.
- [docs/audit-allowlist.md](docs/audit-allowlist.md) —
  project-specific false-positive memory for `/audit` and
  `/indie-review`.
- [docs/ideas.md](docs/ideas.md) — mid-flight ideas pending a
  user-decision on placement (created on first use).
- [docs/standards/](docs/standards/) — coding, naming, dependencies,
  documentation, testing, commits (+ roadmap-format).
- [.claude/workflow.md](.claude/workflow.md) — live workflow
  state and rules.

## Disclaimer

finbreak is provided **as-is**, with no warranty of any kind (see
[LICENSE](LICENSE)). It reads and summarises your bank statements locally
on your own machine — it does **not** give financial advice, and it is
**not** connected to your bank.

The author is **not responsible for any incorrect information the app may
display** — for example a mis-read amount, a wrong category, or an
inaccurate total. Always check important figures against your original
statements before relying on them.

If you spot something wrong, **please
[log an issue](https://github.com/milnet01/finbreak/issues)** so it can be
investigated and fixed. Bug reports genuinely help make the app more
accurate for everyone.

## License

[MIT](LICENSE).
