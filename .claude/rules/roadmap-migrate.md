---
paths:
  - "ROADMAP.md"
---

# `roadmap_migrate` on this project

Part of this project's instructions, kept out of `CLAUDE.md` so it loads
only when needed. `CLAUDE.md` says when to read it.

**`roadmap_migrate` re-ingests the file into the store, and on this project
you should almost never need it.** It only reads `ROADMAP.md`, so a byte-
identical file afterwards is the verb working, not a failure. **Run it only
when you KNOW something other than `roadmap_log` wrote the file** — an
external merge, a restore from git. **Never on the strength of its
counters**, which do not measure staleness: measured 2026-08-19 on a tree
where every `ROADMAP.md` change had come through `roadmap_log`, a `dry_run`
still reported **10 items updated** (`body`, `layman`, `source`, `extras`).
The cause is that the render → parse round trip is not lossless — **a
property of the round trip, so it applies to EVERY run, the sanctioned ones
included.** `updated_items[]` is the verb's plan to write those re-parsed
bodies over correct ones, in a store shared by every project on this
machine. **So always `dry_run` first and read `updated_items[]` item by
item**; anything you cannot account for as a real edit to the file is the
round trip, and a real run would clobber it.
