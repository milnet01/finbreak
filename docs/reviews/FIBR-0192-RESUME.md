# FIBR-0192 — /cold-eyes run state (loops owed)

**Stopped after loop 2 of a `--max-loops 7` run** (project cap, CLAUDE.md).
Not converged: loop 2 returned build-changing findings. **Loop 3 is owed.**

## How to resume

```
/cold-eyes docs/specs/FIBR-0192.md --max-loops 7
```

Start at **loop 3**. Everything below is run state, not findings — there is no
deferred tail, because every verified finding from loops 1 and 2 was fixed.

## Where it stands

| | |
|---|---|
| Document | `docs/specs/FIBR-0192.md`, 717 lines (median sibling 561, p75 707) |
| Status | draft — **not** accepted; do not implement yet |
| Commits | `bd1ce5d` draft · `36a060b` loop 1 fixes · `e78e6c5` loop 2 fixes |
| Loop 1 | CRIT 1 · HIGH 3 · MED 8 · LOW 6 — 18 verified / 1 unverified, all fixed |
| Loop 2 | CRIT 0 · HIGH 2 · MED 6 · LOW 9 — 17 verified / 3 unverified, all fixed |
| Origin split | loop 1: 18 draft / 0 collateral · loop 2: ~8 draft / ~9 collateral |
| Stop triggers | **neither fired** — collateral has not outnumbered draft two loops running, and no structural defect has appeared |

## Rebuild before dispatching loop 3

Both artefacts are rebuilt as the **last** action before dispatch:

1. **Scrubbed copy** — `/tmp/.../ce-0192/FIBR-0192.md`: the spec with §13's body
   replaced by the "withheld on purpose" placeholder. Lanes read this path;
   findings cite the original.
2. **Shared context packet** — `/tmp/.../ce-0192/shared-context.md`:
   `references/review-brief.md` verbatim + bounded code windows + cross-doc
   passages + the `/doc-lint` buckets. ~60 KB; lanes measured 30–42k input
   tokens against the 60k budget.

**One packet defect must be fixed first.** Part B's FIBR-0084 excerpt is
truncated at 2600 characters, which cuts the sentence *"So: do NOT flip this
bullet when FIBR-0113 ships. Flip it when FIBR-0192 ships."* Three lanes across
two loops reported §12 as mis-attributing that instruction; the spec is right and
the packet was wrong. Widen that excerpt (or quote the sentence directly) or loop
3 will spend a fourth lane-finding on it.

## Settled facts — do not re-derive (safe to carry; source unchanged)

All measured against the pinned PySide6 6.11.1, `QT_QPA_PLATFORM=offscreen`.
These live in the spec's §2.1 and are reproduced by its §7 probes:

- `QTableWidget` header `sectionsMovable` **False** by default; `QTreeWidget`
  header **True**. (So a movability clause on a tree is vacuous.)
- `saveState()` **serialises** the sections-movable flag.
- `restoreState()` emits neither `sectionResized` nor `sectionMoved`.
- `restoreState()` emits `sortIndicatorChanged`; PySide6 often cannot marshal its
  `Qt::SortOrder`, so the slot raises `TypeError` to stderr rather than running.
- **A sortable view re-sorts its rows on that signal — blocking it desynchronises
  the arrow from the rows.** This is the fact that forbids `blockSignals`.
- `stretchLastSection`: `QTableWidget` **False**, `QTreeWidget` **True** by default.
- `QTreeWidget.clear()` preserves column count, widths, header labels and the
  view's dynamic property.
- All **seven** existing `remember_columns` call sites set columns + objectName
  before calling.

## Carry-over rules

- **Brief loop 3 exactly like loops 1–2.** No list of prior fixes, no "already
  resolved". The cold re-read is the verification.
- The only "already logged" items in the brief are `/doc-lint`'s buckets
  (currently: zero findings; one candidate judged not-a-defect; 717 lines).
