---
paths:
  - "docs/specs/**"
  - "docs/standards/naming.md"
---

# Spec filenames: why `naming.md` is not amended yet

Part of this project's instructions, kept out of `CLAUDE.md` so it loads
only when needed. `CLAUDE.md` says when to read it.

`naming.md` is not amended yet on purpose. Amending *this* rule changes
what a conformer writes — the spec filename — so it trips rule 14's gate
(`review-contract <path> --genre standard`); and back-migrating the existing
`FIBR-NNNN.md` specs means repointing every inbound citation — so both halves
are tracked as **FIBR-0196** rather than done in passing.

**Not every `docs/standards/` edit owes that gate.** Rule 14's trigger is
a *change of direction*, not an edit: "would someone conforming to this
document now BUILD something different, or build, check or ship it a different
way? Name the line." A corrected date, a
fixed count, a dead link or a reworded example changes nothing anyone
writes — record the check in one line of the commit body and move on. In
the grey zone, do **not** gate. This note exists so a session that reads
`naming.md` and not that bullet does not name the next spec wrongly.
