# finbreak — Known issues

> **Status:** Empty until first deferral.
> **Bar for entry:** high — only items genuinely blocked by
> an unbuilt dependency, with the dependency named
> explicitly. The
> [app-workflow skill](~/.claude/skills/app-workflow/SKILL.md)'s
> default disposition is to fold every actionable finding
> into a fix-pass; this file is the exception case.


## Format

```markdown
## known-issue-NNN — One-line summary

- **Found by:** <audit / indie-review / debt-sweep / user>
  during <phase / context>
- **Why deferred:** depends on roadmap item <ID> "<title>"
  (status: 📋 not started / 🚧 in progress)
- **Will be addressed in:** <ID>
- **Logged:** YYYY-MM-DD
```

When the named dependency lands, the corresponding
known-issue is folded back into the roadmap automatically as
a new fix-pass (per the workflow skill's drift-handling
rules).


## Entries

(none yet — the project just scaffolded)


## What does NOT belong here

- Findings that *could* be fixed today but feel like work
  for "later". Those go into a fix-pass roadmap item, not
  here.
- Findings that turned out to be false positives. Those go
  in [`docs/audit-allowlist.md`](audit-allowlist.md) (the
  closed-loop memory used by `/audit` and `/indie-review` to
  pre-discard), with a short note in the active phase's
  `docs/journal/<ID>.md`.
- Findings that the user decided to accept as-is. Those go
  into a permanent ADR explaining the trade-off, not a
  known-issue.

The bar is deliberately high. If you're tempted to defer
something here, ask: "Could I write a fix-pass roadmap item
for this right now?" If yes, do that. If no — and only if no
— file it here with the named dependency.
