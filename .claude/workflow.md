# finbreak — Workflow state

## §1. Status header

| Field | Value |
|-------|-------|
| **Project phase** | P02 — Vertical slice: the security spine |
| **Active item ID** | FIBR-0004 |
| **Active step** | (see "Step progress" below) |
| **Blocked on** | — |
| **Last update** | 2026-07-02 (FIBR-0004 steps 5–6 done — audit + 4-lane indie-review; 10 findings all fixed inline per user directive; gate green 68/1, mypy 0) |
| **Next gate** | FIBR-0004 final clean-close pass (re-run `/audit` + `/indie-review` on the fixed code; if zero actionable → flip ✅ + tag `FIBR-0004-complete`, user-approved) |
| **Convergence checkpoint** | 5 (consecutive `FP##` items immediately preceding any ✅-`implement`-Kind close in the active release block — see `~/.claude/commands/close-phase.md § 5a-6`) |
| **Debt-sweep phase threshold** | 5 (auto-prompt for `/debt-sweep` after this many phases without one) |
| **Last debt sweep** | (none yet) |
| **Repo visibility** | PUBLIC (cached 2026-06-30; push freely per global rule § 6) |

### Step progress

While an item is active, Claude marks the current step 🚧;
completed steps flip to ✅. Resets to all ⬜ when a new item
becomes active.

1. ✅ Verify spec (`docs/specs/FIBR-0004.md`; `/cold-eyes` 6 loops;
   user signed off 2026-07-01, ZAR added, 2 cross-doc fixes applied)
2. ✅ Verify dependencies on the roadmap DAG (FIBR-0001 ✅, FIBR-0003 ✅)
3. ✅ Write failing tests (`tests/features/vault/{spec.md,test_vault.py}`;
   confirmed failing on absent modules before implementing)
4. ✅ Implement until tests pass (crypto/vault/services/repositories/ui +
   argon2 self-test leg + no-args→GUI; `./scripts/ci-local.sh` exits 0,
   67 passed / 1 skipped, bandit clean incl. the raw-key pragma)
5. ✅ Run `/audit` (Ants MCP `audit_run` full scope) — clean bar mypy;
   allowlist empty (no false positives to skip)
6. ✅ Run `/indie-review` (4 cold lanes: crypto+vault, services+repo,
   UI+threading, tests+contract) — 10 actionable findings
7. ✅ Findings FIXED INLINE (user directive: don't defer to an FP## after
   audit/review). 2 HIGH (0o600-at-create, re-entrant-unlock crash) +
   1 HIGH test-marker gap + 3 MEDIUM + 4 LOW. Gate green 68/1; mypy 0
8. 🚧 Update CHANGELOG / ROADMAP / journal — at the clean close
9. ⬜ Commit, tag `<ID>-complete` (clean close only), push (public)

### Active item details

(filled in once Phase A → P01 hands over an active item)

```
Item: FIBR-0004 (P02 Vertical slice — master password → Argon2id → SQLCipher
      vault → one manual transaction → table → lock)
Spec: docs/specs/FIBR-0004.md (not yet written — Step 1 drafts it)
Depends: FIBR-0001 (✅ closed 2026-07-01). Phase-ordering also puts FIBR-0002
         (✅) and FIBR-0003 (✅) ahead, but they are not code prerequisites.
Branch: implement-Kind item — PR-based flow may apply (see global rule § 7);
        confirm branch at Step 1.
Next: Step 1 — write/expand the FIBR-0004 spec (security spine; cite
      security-model.md INV-2 Argon2id params), /cold-eyes it, then TDD loop
Tests: (harness green; 27 passing, 1 skipped after FIBR-0003 close)
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

### 2026-07-01 — FIBR-0004 steps 3–4 (TDD + implement, gate green)

Built the P02 security spine TDD-first. Re-verified the crypto APIs empirically
in the venv before citing them (§13): argon2-cffi 25.1.0 `hash_secret_raw` → 32
deterministic bytes; sqlcipher3 raw-key open reports `cipher_use_hmac=1` /
`HMAC_SHA512` / page 4096, `isolation_level=""` (manual-commit), wrong-key →
`DatabaseError`, on-disk header not SQLite magic. Wrote
`tests/features/vault/{spec.md,test_vault.py}` (INV-1..8, incl. two `qtbot` UI
round-trips), confirmed failing on absent modules, then implemented:
`errors`, `models`, `crypto`, `paths`, `vault`, `repositories/transactions`,
`services/{auth,transactions}`, `ui/{_worker,first_run,unlock,main_window}`,
`app`; extended `_selftest` with the argon2 leg; `__main__` no-args now launches
the GUI (retired `FINBREAK_NOT_BUILT`, with the FIBR-0003 spec + bundling-spec
cross-refs updated); added `argon2-cffi==25.1.0`, removed the `-p no:pytest-qt`
line. `./scripts/ci-local.sh` exits 0 — **67 passed / 1 skipped**, bandit clean
(the raw-key f-string pragma did not trip B608 — DoD #2), pip-audit clean.

One structural call surfaced to the user (not a silent drift): added
`services/transactions.py` (`TransactionService` + pure `parse_transaction` /
`to_display_decimal`) to honour the spec's INV-4a "the service layer
reconstructs the display Decimal" under design.md's UI→Service→Repository layering.
One test-mechanism fix: INV-1's tamper leg flips a byte in **page 1** (the page
the schema read checks), per INV-1's stated first-read mechanism.

Next: steps 5–6 — `/audit` + `/indie-review` in parallel (allowlist read first).

### 2026-07-01 — FIBR-0004 spec drafted + `/cold-eyes` (6 loops)

Opened P02. Confirmed no PR-workflow opt-in (no marker/CODEOWNERS, all
direct `<ID>:` commits) → FIBR-0004 lands directly on `main`. Researched +
pinned the crypto-stack idioms (argon2-cffi 25.1.0 `hash_secret_raw` raw-key
API; sqlcipher3-binary 0.6.0 raw-key pragma + HMAC-SHA512 defaults + wrong-key
`DatabaseError`; `bytearray` wipe limits) before drafting, so the contract
cites real APIs (global rule §13). Drafted `docs/specs/FIBR-0004.md` — the
security-spine vertical slice (CryptoService→AuthService→Vault→one repo→3 UI
screens; 8 INVs mapping to security-model INV-1/2/3/8/9).

**Cold-eyes (global rule §14):** 2 lanes (accuracy; implementability), **6
loops**, 12 independent cold reviewers, ~75 verified findings fixed, **zero
CRITICAL** throughout, no regression survived past one loop. Notable catches:
the coding.md §7 gaps (`0o600` perms, atomic sidecar write, key-wipe-on-exit
leg of INV-3) at loop 3; the loop caught **3 defects I introduced while
fixing loop 4** (loop 5) and **2 more from loop-5 edits** (loop 6, the
"confirming pass" the user authorised at the max-loops cap) — including a
fabricated FIBR-0003 quote and an INV-2c `len(key)` over-reach. Design
defaults baked in + flagged for sign-off: money as exact integer minor units
(reject sub-unit, never round); plaintext KDF sidecar; auto-lock 10 min
placeholder; tamper-and-wrong-password deliberately indistinguishable at
unlock. Two cross-doc follow-ups surfaced for the user: a one-line ADR-0003
raw-key note, and tightening security-model INV-2's "in the vault" → "with
the vault".

Next: **user signs off the spec**, then Step 2 (deps: FIBR-0001 ✅) → Step 3
(write failing tests) → Step 4 (implement).

### 2026-07-01 — FIBR-0003 closed by /close-phase (P01 Bootstrap complete)

Steps 3–4 (TDD + implement) landed in commit `49e87b6`; the bundling
smoke-test is proven green (both the onefile and AppImage print
`FINBREAK_SELFTEST_OK` in the Python-free `debian:13-slim` clean-room).

**Close (steps 5–9):** ran `/audit` + `/indie-review` in parallel over the
FIBR-0003-authored files. Audit (incl. `shellcheck` on all three shell
scripts): zero actionable. Indie-review: 3 actionable, **all doc/comment
drift, no code/security defect** — a stale "manylinux_2_34 container"
mislabel (the build image is `python:3.12-slim-bookworm`; manylinux is ruled
out because it ships a static Python) in `pyproject.toml` + `build-smoke.sh`,
a stale test-function name in `tests/features/bundling/spec.md`, and a
missing `pip install .` in CLAUDE.md's dev-setup. User authorised the
**fix-inline** path (deviation from the rigid FP## route, per the skill's
"deviations require explicit user instruction"). Fixed all three, then a
**cold re-audit + re-review pair** caught one straggler instance of the same
manylinux mislabel (`CLAUDE.md:143`, module map) the first review missed —
fixed, exhaustively `grep`-verified across the tree, then a final confirming
cold review returned **CLEAN, zero actionable**. Clean pair on the same
closing round → DoD #5 met.

Updated CHANGELOG (Added), flipped ROADMAP FIBR-0003 → ✅ with resolution
note, wrote `docs/journal/FIBR-0003.md`. Tag `FIBR-0003-complete`.

**P01 Bootstrap is now complete** (FIBR-0001/0002/0003 all ✅). Next: P02
FIBR-0004 — the encrypted security spine (the deliberate vertical slice).

### 2026-07-01 — FIBR-0003 spec drafted + /cold-eyes (6 loops)

Drafted `docs/specs/FIBR-0003.md` (P01 bundling smoke-test). Scope decided
with the user: de-risk **all three** native stacks (Qt + SQLCipher + qpdf),
and keep the bundle-build a **separate opt-in command** so the everyday
`ci-local.sh` gate stays fast. Pinned toolchain from parallel research:
`PySide6==6.11.1`, `sqlcipher3-binary==0.6.0` (bundles the native lib),
`pikepdf==10.9.1`, `pyinstaller==6.21.0`; clean-room = Python-free
`debian:13-slim` via podman `--env-clear`.

**Cold-eyes (global rule §14):** 2 lanes (accuracy + implementability), 6
loops, 12 independent cold reviewers, ~40 findings fixed — including one real
CRITICAL I introduced in loop 3 (a `debian:stable-slim` left in the DoD after
pinning the image) that both lanes caught in loop 4, plus two loop-2 citation
corrections (INV-9→INV-6 for the fake-key justification; testing §3.4→§3.3 for
the integration marker). Converged to polish + build-time-verification items
(PyPI pin resolution, PySide6 wheel tag, Debian glibc) which are folded into
the spec as explicit build steps. Both lanes verified all citations/contracts
clean twice. Also reconciled the ROADMAP FIBR-0003 bullet to name all three
native stacks (was "SQLCipher/Qt" only).

Next: step 3 — write failing tests (the `--self-test` guard + the
`integration`-marked build+clean-room test), then implement to green.

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
