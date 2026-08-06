# finbreak — Audit allowlist

> **Status:** Empty until first confirmed false positive.
> **Bar for entry:** high — every entry requires written
> reasoning. Future audits re-verify the suppression is still
> warranted.
> **Scope:** project-specific. Each project develops its own
> list. There is no global allowlist.

This file is the **closed-loop memory** for `/audit` and
`/code-quality-review` false positives. Without it, the same false
positive gets surfaced and dismissed every audit run, burning
tokens and tempting "skip without thinking" reflexes.

> **Naming note (2026-08-05).** The review skill was renamed
> `/indie-review` → `/code-quality-review`; the old command no
> longer exists. Prose in this file now says the new name.
> **Existing entries keep their original `indie-review:R-N` source
> tokens** — those are recorded provenance for a finding that really
> was raised by the skill under its old name, and rewriting history
> to match a rename would make the record less true, not more.
> Write new entries with `code-quality-review:R-N`. Decided rather
> than left ambiguous, so a future session does not "tidy" the old
> tokens.

The `app-workflow` skill
(`~/.claude/skills/app-workflow/SKILL.md`, machine-local)
reads this file **before** triaging audit findings, so
already-confirmed false positives are discarded without
re-evaluating.


## How entries are added

When `/audit` or `/code-quality-review` produces a finding F that
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
code-quality-review finding with no rule ID), the allowlist entry
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
  code-quality-review:R-7
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


## allowlist-002 — debt-sweep:missing_inv_test fires on this project's hyphen-less test-tag convention

- **Status:** active
- **Tool / rule:** `debt_sweep_scan` (Ants MCP) —
  `test_coverage` / `missing_inv_test`
- **Location:** class-level — 65 of 67 findings across
  `tests/features/*/spec.md` (every feature dir).
- **Why this is a false positive:** the detector greps the literal
  hyphenated token `INV-N` in `test_*.py` **in the same directory**.
  This project tags invariants four other ways, all of which that grep
  misses: (1) inside the test function name with the hyphen dropped —
  `test_INV8a_...`, `test_INV2c_...`, which is the *dominant*
  convention; (2) in section-banner comments — `# Bounds (INV-14)`;
  (3) with sub-letters in inline comments — `# INV-12(a)`; (4) by
  ticket id, where the invariant's title names it —
  `test_FIBR0151_...`. Separately, several specs deliberately
  **relocate** an invariant to a sibling suite and say so in prose
  (`reporting` INV-2 → the settings suite; `statements` INV-13/13a →
  the migration suites; `settings` INV-10 / `theme` INV-13 /
  `transfers` INV-11 / `category_library` INV-11 / `categorisation`
  INV-16 → the shared source-scans). And `db_performance` "INV-5" is
  not a declaration at all — that spec's table is INV-1..4; the string
  is a cross-reference to *FIBR-0005* INV-5 inside INV-3's prose.
  Two independent verification lanes classified all 67 findings: 65
  covered-or-by-design, **2 genuine gaps** (`dialog_lifecycle` INV-4,
  `recurring` INV-2), both closed with real tests in this sweep.
- **Suppression applied:** none available (the detector is
  server-side and has no inline-suppression syntax). Recorded here so
  the next sweep discards the class without re-litigating it. If the
  Ants MCP detector later normalises `INV<N><letter>` in identifiers
  and honours the specs' "covered in X" prose (reported upstream),
  revoke this entry and re-run clean.
- **Logged:** 2026-07-26
- **Confirmed by phase:** DS01 (debt sweep)


## allowlist-003 — ROADMAP bullet headlines record the work as *proposed*, not as *delivered*

- **Status:** active
- **Tool / rule:** `debt-sweep:doc_drift` (and any reviewer reading
  ROADMAP headlines in isolation)
- **Location:** finding signature — a ✅ bullet whose **headline**
  names a symbol that does not exist. Seen at `ROADMAP.md:2011`
  (FIBR-0069, `_signed_balance_from_tokens`) and `ROADMAP.md:2006`
  (FIBR-0068, `_set_combo` "promoted to a shared UI util").
- **Why this is a false positive:** in this project's ants-v1 roadmap
  format the headline records the work **as originally proposed**; the
  `Resolved:` body records what actually shipped, including any
  deviation. In both cited cases the body documents the deviation
  explicitly and correctly. FIBR-0069's body: *"Named `_signed_balance`
  (a single token) rather than the tentative
  `_signed_balance_from_tokens`, since every site passes one token"* —
  and `src/finbreak/importers/standard_bank.py:191` defines
  `_signed_balance`. FIBR-0068's body: *"IMPORTANT distinction
  surfaced, not forced: kept DISTINCT from
  `ImportWizardWidget._set_combo`, which is UNGUARDED by design …
  Merging them would have been a silent behavior change"* — and
  `src/finbreak/ui/_widgets.py:6-9` repeats that rationale in the
  module docstring, with `select_combo_data` at `:27`. Rewriting the
  headlines to match the delivered names would **destroy** the
  proposed-vs-delivered contrast that makes each deviation legible.
  Rule for future sweeps: judge a shipped bullet's accuracy against
  its body, not its headline.
- **Suppression applied:** none — documentary convention, no rule id.
- **Logged:** 2026-07-26
- **Confirmed by phase:** DS01 (debt sweep)


## allowlist-004 — coding.md § 5.2: the FIBR-0219 ambiguity message is untranslated

- **Status:** active
- **Tool / rule:** `coding.md § 5.2` (every user-facing string in `ui/` goes
  through `tr()` / `QCoreApplication.translate`) — fires for `/audit` and
  `/code-quality-review` alike, no tool rule id.
- **Location:** `src/finbreak/ui/_amount.py`, `_ambiguous()` — the
  `"amount is ambiguous: … (grouped) … (decimal) — retype it using the format
  the app displays"` string, plus the `"amount is not a valid number"` reraise in
  `parse_amount_input`.
- **Why this is a false positive:** it is a **parser** rejection message, not UI
  chrome, and it joins an existing family that is untranslated by established
  convention: every `parse_transaction` rejection (`"amount is not a valid
  number"`, `"amount must be non-zero"`, `"amount is too large to store"`,
  `"description must not be empty"`) is plain English today, and
  `ManualEntryDialog._on_add` renders whichever one it catches **verbatim** via
  `self._error.setText(str(exc))`. Translating this one string alone would give
  the same error label a mixed-language voice depending on which rejection fired.
  The deviation is that the precedent is a *services*-layer one while this
  message is authored in `ui/`, which is what § 5.2 governs — recorded here
  knowingly rather than discovered mid-audit. Scoped to these strings only; the
  standard is **not** amended, and translating the parser layer app-wide remains
  a separate item. Full reasoning: `docs/specs/FIBR-0219.md` § 9 decision 3.
- **Suppression applied:** none — no rule id to suppress; this entry is the
  record.
- **Logged:** 2026-08-05
- **Confirmed by phase:** FIBR-0219 (implementation)


## allowlist-005 — cppcheck is auto-detected on this Python project and reports every file as a syntax error

- **Status:** active
- **Tool / rule:** `cppcheck:syntaxError` (via `audit_run`'s auto-detection)
- **Location:** class-level — **every** `.py` file cppcheck is handed. Seen as 6
  findings at SARIF level `error` (rendered `severity: CRITICAL`) over
  `models.py`, `text.py`, `services/month_summary.py`, `ui/home.py`,
  `ui/main_window.py`, `ui/month_summary.py`.
- **Why this is a false positive:** cppcheck is a **C/C++** static analyser and
  finbreak is pure Python. `audit_run`'s tool auto-detection hands it whatever
  paths the sweep is scoped to, and its C++ frontend then fails to tokenise
  Python — every finding is the identical `No pair for character ("). Can't
  process file. File is either invalid or unicode, which is currently not
  supported.` at line 1. The message is a **parser** failure, not an analysis
  result: cppcheck examined nothing, so the finding carries no information about
  the file at all. It also surfaces in `parse_failures[]` / `parse_failures_detail[]`
  on the same envelope, which is the honest signal — the SARIF `error` rows are
  the same event double-counted at CRITICAL severity. Note the shape: **zero
  findings plus zero confidence looks identical to a clean pass**, which is why
  this is recorded rather than ignored.
- **Suppression applied:** none inline (there is no Python-side syntax to
  suppress a C++ analyser). The durable fix is to pass an explicit `tools:` list
  to `audit_run` on this project — cppcheck and clazy should never be in it.
  Recorded here so a sweep that forgets discards the class without re-litigating
  six CRITICALs.
- **Logged:** 2026-08-06
- **Confirmed by phase:** FIBR-0231 (close)


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
