# finbreak — Audit allowlist

> **Status:** Empty until first confirmed false positive.
> **Bar for entry:** high — every entry requires written
> reasoning. Future audits re-verify the suppression is still
> warranted.
> **Scope:** project-specific. Each project develops its own
> list. There is no global allowlist.

This file is the **closed-loop memory** for `/audit` and
`/indie-review` false positives. Without it, the same false
positive gets surfaced and dismissed every audit run, burning
tokens and tempting "skip without thinking" reflexes.

The
[app-workflow skill](~/.claude/skills/app-workflow/SKILL.md)
reads this file **before** triaging audit findings, so
already-confirmed false positives are discarded without
re-evaluating.


## How entries are added

When `/audit` or `/indie-review` produces a finding F that
triage classifies as a tool false positive (verified, not just
dismissed), Claude **must**:

1. Add an entry to this file with the rule, location,
   reasoning, date, and confirming phase.
2. Apply a tool-level suppression where the toolchain supports
   it — `# noqa: <RULE>` for ruff, `// NOLINT(<rule>)` for
   clang-tidy, `eslint-disable-next-line <rule>` for ESLint,
   `# pylint: disable=<rule>` for pylint, etc. — and cite this
   allowlist entry by number in the suppression comment.
3. Log the false positive inline in the active phase's
   `docs/journal/<ID>.md`.

If a tool-level suppression isn't possible (e.g. semantic
indie-review finding with no rule ID), the allowlist entry
alone is enough — triage subagents read it before flagging.


## How entries are revoked

If a previously-allowlisted finding turns out to be a real
issue (e.g. the surrounding code shape changed and the
suppression is now hiding a genuine bug):

1. Update the entry's `Status:` to `revoked YYYY-MM-DD` with
   reasoning.
2. Remove the tool-level suppression in code.
3. Fold the finding into the next fix-pass like any actionable
   issue.

Do not delete revoked entries — the history is the value.


## Format

```markdown
## allowlist-NNN — <rule>:<location> short summary

- **Status:** active | revoked YYYY-MM-DD (<reason>)
- **Tool / rule:** e.g. cppcheck:nullPointer, ruff:B902,
  indie-review:R-7
- **Location:** file:line, or finding signature for
  non-line-bound findings
- **Why this is a false positive:** one paragraph. Be specific.
  Future audits may re-verify.
- **Suppression applied:** none | inline (cite suppression
  syntax used)
- **Logged:** YYYY-MM-DD
- **Confirmed by phase:** P##/FP##/etc.
```


## Entries

## allowlist-001 — semgrep:dynamic-urllib-use-detected in the sole allowlisted network module

- **Status:** active
- **Tool / rule:**
  semgrep:python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
- **Location:** `src/finbreak/services/update_fetch.py` — the two
  `urllib.request.urlopen(...)` calls (`fetch_latest_release` and `download`).
- **Why this is a false positive:** the rule warns that a `urllib` call may use
  an attacker-controlled (dynamic) URL. `update_fetch.py` is the **one** module
  the FIBR-0054 design *deliberately* allows to import `urllib` (INV-12 / D9 /
  D12) — the entire network surface of the app. The two URLs are not arbitrary:
  the API URL is built from a hard-coded owner/repo template
  (`_API_URL_TEMPLATE.format(...)`), the download URLs come from the GitHub
  Releases JSON, and **every** call is gated by `_require_https()` (https-only),
  a byte cap + socket timeout (INV-10), and — for the downloaded AppImage — an
  Ed25519 signature verified over the exact bytes against the committed public
  key *before anything is installed* (INV-4). The SSRF concern the rule models is
  structurally answered by the design, not by luck. The companion bandit B310 on
  the same lines is already suppressed for the same reason (`# nosec B310`).
- **Suppression applied:** inline —
  `# nosemgrep: dynamic-urllib-use-detected` appended on both `urlopen` lines
  (alongside the existing `# nosec B310`).
- **Logged:** 2026-07-14
- **Confirmed by phase:** FIBR-0054 (close)


## What does NOT belong here

- **Findings that are real but blocked by a missing feature.**
  Those go in `docs/known-issues.md` with the named dependency.
- **Findings that should be fixed but the user wants to
  defer.** No deferral disposition exists outside of "blocked
  by dependency" — every actionable finding becomes a fix-pass.
- **Findings the user accepts as a permanent trade-off.**
  Those become an ADR in `docs/decisions/`, not a suppression.

The bar is deliberately high. If you're tempted to allowlist
something, ask: "Have I verified, with a specific argument,
that this finding cannot be acted on?" If yes — file. If
"probably not relevant" — file as a fix-pass instead and let
the implementation prove the point.
