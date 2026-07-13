# Architecture Decision Records (ADRs)

This folder holds architecture decision records — short markdown
files capturing **why** a significant architectural choice was
made, what alternatives were considered, and what the trade-offs
were.

The format is Michael Nygard's lightweight pattern (see
[ADR-0001](0001-record-architecture-decisions.md)): one file per
decision, numbered sequentially, never edited after acceptance
(superseded decisions get a new ADR that references the prior
one).

## When to write an ADR

Write one when a decision:

- Has long-term consequences (months or years).
- Closes off alternatives that future contributors might propose.
- Reflects a trade-off that isn't obvious from the code alone.
- Required real research / debate to settle.

Don't write one for:

- Small refactors that anyone might revisit on a Tuesday.
- Choices forced by external constraints (compiler version, OS
  API surface) — the constraint *is* the rationale; mention it
  in code comments instead.
- Decisions captured fully in `CLAUDE.md` or one of the
  standards docs — those are the right home for repeatable
  rules.

## Numbering

Sequential, zero-padded to 4 digits:
`0001-record-architecture-decisions.md`,
`0002-pyside6-over-pyqt6.md`, …

Append-only — once an ADR has a number, it keeps it forever,
even if superseded.

## Lifecycle

Status values are defined canonically in ADR-0001's template block;
this table is the at-a-glance gloss.

| Status | Meaning |
|--------|---------|
| Proposed | Drafted; under discussion. |
| Accepted | Decision made; in effect. |
| Deprecated | No longer applies; new code shouldn't follow it. |
| Superseded by ADR-NNNN | Replaced by a later decision. |

A status change is an edit to the ADR's `Status:` field; the
body of an accepted ADR isn't rewritten — supersession is
captured in a new ADR.

## Index

| ADR | Decision |
|-----|----------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions (this process) |
| [0002](0002-pyside6-over-pyqt6.md) | PySide6 over PyQt6 (LGPL vs GPL) |
| [0003](0003-sqlcipher-local-only-storage.md) | SQLCipher + Argon2id, local-only, per-OS-user storage |
| [0004](0004-qt-native-pdf-over-weasyprint.md) | Qt-native PDF engine over WeasyPrint |
| [0005](0005-csv-mapping-profiles.md) | Per-bank CSV column-mapping profiles |
| [0006](0006-transfer-detection-suggest-confirm.md) | Transfer detection: suggest-then-confirm |
| [0007](0007-self-contained-bundled-releases.md) | Self-contained bundled releases |
| [0008](0008-qtcharts-for-reporting.md) | QtCharts for the reporting dashboard charts |
| [0009](0009-sqlcipher-binding-package.md) | SQLCipher binding package — `sqlcipher3-wheels` (cross-platform fork) |

## Template

See [ADR-0001](0001-record-architecture-decisions.md) — both the
canonical first ADR and a worked example of the format.
