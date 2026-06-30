# finbreak — Workflow state

## §1. Status header

| Field | Value |
|-------|-------|
| **Project phase** | Phase D — Documentation audit loop |
| **Active item ID** | (none — pre-code phases) |
| **Active step** | (see "Step progress" below) |
| **Blocked on** | — |
| **Last update** | 2026-07-01 (Phase D — two deferred items resolved: Argon2id params pinned in security-model INV-2 + naming unified to `finbreak` (repo renamed); resolving cold-eyes loop ran 5 passes to clean. Awaiting user sign-off) |
| **Next gate** | User signs off "docs ready to code from" → P01 (FIBR-0001) implementation |
| **Convergence checkpoint** | 5 (consecutive `FP##` items immediately preceding any ✅-`implement`-Kind close in the active release block — see `~/.claude/commands/close-phase.md § 5a-6`) |
| **Debt-sweep phase threshold** | 5 (auto-prompt for `/debt-sweep` after this many phases without one) |
| **Last debt sweep** | (none yet) |
| **Repo visibility** | PUBLIC (cached 2026-06-30; push freely per global rule § 6) |

### Step progress

While an item is active, Claude marks the current step 🚧;
completed steps flip to ✅. Resets to all ⬜ when a new item
becomes active.

1. ⬜ Verify spec (research first if non-trivial)
2. ⬜ Verify dependencies on the roadmap DAG
3. ⬜ Write failing tests
4. ⬜ Implement until tests pass
5. ⬜ Run `/audit` (read `docs/audit-allowlist.md` first)
6. ⬜ Run `/indie-review` (same allowlist read)
7. ⬜ Fold actionable findings → new FP## roadmap item
8. ⬜ Update CHANGELOG / ROADMAP / journal
9. ⬜ Commit, tag `<ID>-complete`, ask user about push

### Active item details

(filled in once Phase A → P01 hands over an active item)

```
Item: <ID>
Spec: docs/specs/<ID>.md
Branch: main (no feature branch yet)
Sub-findings:
  - 📋 ...
  - 📋 ...
Tests: <count> passing, <count> failing
```

## §2. Workflow rules

The canonical rules — phases A–D, the per-phase 9-step loop,
ID scheme, triage table, fold-into-roadmap pattern,
false-positive learning loop, drift handling, Definition of
Done — live in
`~/.claude/skills/app-workflow/SKILL.md`.
Skills don't auto-load from filesystem presence — they fire
on description-match against your message. To engage the
workflow in a session, mention any of: phase / audit / drift
/ fix-pass / "where were we" / "resume" / "continue work" /
this `workflow.md` file by name. The project's `CLAUDE.md`
(loaded automatically on session start) reminds you of this
on every resume.

**Hard rule kept inline (most-load-bearing):** never silently
drift. If code being written diverges from the spec, stop and
surface. Either the spec was wrong (update spec → re-audit
affected sections → resume) or the code was wrong (fix code,
no spec change). Never both papered-over.

To refresh this file from the (upgraded) skill template, copy
`~/.claude/skills/app-workflow/templates/.claude/workflow.md`
over this file — preserve §1 (status header) and §3 (session
journal); §2 is the only part that changes.

## §3. Session journal

Append-only. Newest at the top.

### 2026-07-01 — Phase D deferred items resolved (Argon2id pin + finbreak rename)

Closed the two items deferred at the end of the Phase D doc audit, before P01
sign-off.

1. **Argon2id parameters pinned.** Researched the current OWASP Password Storage
   Cheat Sheet (retrieved 2026-06-30) and pinned the highest-memory of its five
   equal-strength Argon2id configs — **memory 47104 KiB (46 MiB), iterations 1,
   parallelism 1**, plus a 16-byte per-vault salt and 32-byte (256-bit) raw-key
   output (the last two are finbreak choices; OWASP is silent on them). Values
   now live in **one place** — `security-model.md` INV-2 — with an explicit,
   testable open-path refusal rule (memory ≥ floor; output and salt exact-format;
   iterations/parallelism uncheckable since 1 is Argon2id's own minimum).
   ADR-0003, T9, T2 and the ROADMAP FIBR-0004 bullet now reference INV-2 instead
   of restating numbers or promising a future just-in-time pin.

2. **Naming unified to `finbreak`.** Per user decision, dropped the deliberate
   Fin_Break / FinBreak / finbreak three-way split; brand, repo, on-disk data
   dir, and Python package are now all `finbreak` (byte-for-byte). Swept 15
   doc/config files; historical journal lines left intact. Data-dir path is now
   `~/.local/share/finbreak/` etc. **GitHub repo renamed** milnet01/Fin_Break →
   milnet01/finbreak (old URL auto-redirects; local remote updated). **Local
   checkout dir not yet renamed** — still `…/Fin_Break`; recommend
   `mv Fin_Break finbreak` from a fresh session to match (deferred to avoid
   breaking this session's absolute paths).

**Cold-eyes (global rule §14):** the edited security/ADR/design docs ran through
`/cold-eyes` — 2 lanes (crypto-accuracy, naming). Naming clean on loop 1. Crypto
lane looped 5 passes: loop 1 MED+LOW (params not concrete / single-source) →
loop 2 HIGH ("top-recommended" mischaracterised OWASP's equal-strength configs)
+ MEDs → loops 3–4 (floor-predicate prose-vs-predicate precision) → **loop 5
clean** (zero verified findings, all dimensions). Every value independently
re-verified against the live OWASP page each loop.

Next: still awaiting user sign-off "docs ready to code from" → P01 (FIBR-0001).

### 2026-06-30 — Phase D `/cold-eyes` doc-audit loop (5 loops)

Ran the `/cold-eyes` skill over the full Phase A–C doc set (discovery, design,
7 ADRs + README, security-model, the 4 standards + roadmap-format sub-spec,
FIBR-0001 spec, ROADMAP) partitioned into 8 topic lanes. Each loop dispatched
independent cold reviewers; every finding was verified against the files before
fixing (several agent claims were dismissed as false positives on verification —
e.g. a hallucinated CONTRIBUTING clone URL, a "discovery has no Tech-stack
section" claim, a "§5.2 doesn't show Signal/@Slot" claim).

Convergence: ~50 → ~39 → ~20 → ~18 verified findings → loop 5 (fine precision
only). **Zero CRITICAL across all loops.** Loop 1 fixed the big template residue
(coding.md/testing.md/commits.md C++→Python conversion, PROJ→FIBR IDs, stale
Claude-4.7→4.8 trailer) + security-model testability gaps (T9 AES-vs-HMAC
crypto fix, INV-5 split into 5a/5b/5c, INV-2 dangling-spec ref, INV-8 enforcement
honesty). Loops 2–5 fixed second-order issues (4 wrong §-anchors in ROADMAP, a
dashboard→transfer-detection DAG edge for correct SC1 totals, INV citation
precision, str-wipe / raw-key / export-temp-file security gotchas captured for
the P02/P11 specs). Lanes 2/6/7/8 reached cosmetic-clean at loop 4.

Two items deliberately deferred (not doc defects): the exact Argon2id parameters
(pinned in the FIBR-0004/P02 spec with researched OWASP values, per no-guessing
rule) and the data-dir naming (documented the deliberate Fin_Break / FinBreak /
finbreak split rather than renaming).

Awaiting user sign-off "docs ready to code from" before P01 (FIBR-0001).

### 2026-06-30 — Phase C signed off; entering Phase D

User approved the Phase C doc set: `ROADMAP.md` build order (P01–P13,
FIBR-NNNN IDs, counter=16), `docs/security-model.md` (threat model + 9
enforceable invariants), the Python/pytest conversion of
`docs/standards/testing.md`, the `docs/specs/FIBR-0001.md` bootstrap spec,
and the empty `CHANGELOG.md`. Committed `a5162d3`, pushed to public origin.

Next: Phase D — `/cold-eyes` doc-audit loop over the full Phase A–C doc set
until a pass returns zero verified actionable findings (global rule § 14).
Loop 2+ runs cold (no briefing on prior findings). Then user signs off
"docs ready to code from" and P01 (FIBR-0001) implementation begins.

### 2026-06-30 — Phase B design approved

`docs/design.md` (layered UI→Services→Repos→SQLCipher architecture, components,
import→insight data flow, cross-cutting concerns incl. the Security and
Packaging/self-contained-delivery sections) approved by the user, together with
ADRs 0002–0007. ADR-0007 (self-contained bundled releases — bundle the CPython
runtime + all native deps; clean-machine no-Python launch gates every release)
was the last addition before sign-off.

Next: Phase C — write/tweak the four `docs/standards/*.md`, populate `ROADMAP.md`
with the build order (P01 Bootstrap → P02 vertical slice → features →
packaging/release), keep CHANGELOG `[Unreleased]` empty, and write specs for the
first 1–3 roadmap items. Then Phase D — `/cold-eyes` doc-audit loop until clean.

### 2026-06-30 — Phase A discovery approved

`docs/discovery.md` written from the brainstorming conversation and approved by
the user. Public repo created + pushed (`milnet01/Fin_Break`); layout declared
in `.ants/project.json`; public-GitHub optionals activated.

Key decisions: PySide6 (LGPL) GUI; SQLCipher encrypted-at-rest storage; Qt-native
PDF engine (WeasyPrint dropped for cross-platform bundling); local-only/no-network;
per-OS-user data. Cross-platform delivery: Windows `.exe`, unsigned macOS
`.app`/`.dmg`, Linux AppImage + Flathub Flatpak, driven by a specced
`scripts/publish-release.sh`. Local CI emulation (`scripts/ci-local.sh`) +
`.github/workflows/ci.yml` are P01 deliverables.

Next: Phase B — Design (`docs/design.md` + ADRs).

### 2026-06-30 — P00 scaffold

Project scaffolded from `~/.claude/skills/app-workflow/templates/`
via `/start-app`. Initial commit `chore: scaffold project from
template (P00)`.

Next: Phase A — Discovery. User says "let's start discovery"
in a fresh Claude Code session in this directory.
