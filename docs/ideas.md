# finbreak — Ideas

> **Status:** Empty until first new idea is captured.
> **Purpose:** mid-flight ideas the user proposes during an
> active phase. Captured here so they're never lost; sized
> against the current architecture; **only added to the
> roadmap on user say-so**.

The
[app-workflow skill](~/.claude/skills/app-workflow/SKILL.md)
"New ideas" section governs the flow: capture here →
recommend a placement → user decides → either insert into
ROADMAP.md as a new item, or leave here until later.

## Format

```markdown
## idea-NNN — One-line summary

- **Captured:** YYYY-MM-DD during <active phase ID>
- **From:** user request | observation during work | external
  prompt
- **Recommendation:** "Insert as <ID> after <ID>" |
  "Hold until <dependency>" | "Won't fit current architecture
  — needs design refresh"
- **Why:** one paragraph reasoning the recommendation
- **User decision:** pending | accepted YYYY-MM-DD (became
  <roadmap ID>) | declined YYYY-MM-DD (reason)
```

## Ideas

(none yet)

## What does NOT belong here

- **Already-decided roadmap items.** Those go straight into
  `ROADMAP.md` with the appropriate status emoji.
- **Audit findings.** Those go into a fix-pass — see the
  workflow's fold-into-roadmap pattern.
- **Bugs.** Those become roadmap items immediately, not
  "ideas" pending decision.

The bar for entry is "the user proposed something genuinely
new mid-flight that wasn't already planned." Everything else
has a more specific home.
