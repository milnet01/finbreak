<!-- ants-roadmap-format: 1 -->
# finbreak — Roadmap

> See [CHANGELOG.md](CHANGELOG.md) for what's shipped and the current
> version; this file covers what's **planned**.
>
> *No version line here on purpose: this file is rendered from the
> roadmap DB and is absent from `.claude/bump.json`, so a copy of the
> version kept here would go stale — and did, for five releases
> (FIBR-0289).*
>
> **Format:** v1 — see
> [docs/standards/roadmap-format.md](docs/standards/roadmap-format.md).
> Every actionable bullet carries a stable
> `FIBR-NNNN` ID alongside its phase ID
> (`P##`, `FP##`, `DS##`, `DOC##`, `R##`); the phase ID
> categorises blocks while the stable ID identifies individual
> bullets within them. ID is identity, position is priority,
> items are tackled top-to-bottom. `Dependencies:` lines list
> **direct** predecessors only; transitive prerequisites are
> implied by walking the chain.
>
> **Build order rationale:** the layers are built bottom-up so
> each phase rests on a tested one below it. The encrypted
> **security spine** (key derivation → vault → unlock) is the
> *vertical slice* (P02), built first and on purpose — it is the
> load-bearing concern (personal financial data), so it is
> proven end-to-end before any feature sits on top of it. Each
> phase is then a thin, demonstrable increment.

**Legend** (per `docs/standards/roadmap-format.md § 3.3`)

- 📋 Planned (next up for this phase)
- 🚧 In progress (being tackled now)
- ✅ Done (shipped)
- 💭 Considered (research phase; scope or feasibility uncertain)

**Themes** (per `docs/standards/roadmap-format.md § 3.4`)

- 🎨 Features · ⚡ Performance · 🔌 Plugins · 🖥 Platform
- 🔒 Security · 🧰 Dev experience · 📚 Documentation
- 📦 Packaging · 🐛 Bug fixes · 🔍 Findings fold-in
- 🧹 Cleanup / debt

> **Security is a standing concern, not a phase.** Every
> `implement`-Kind item below must satisfy
> [docs/security-model.md](docs/security-model.md); the security
> static-analysis gate wired up in P01 (bandit + pip-audit +
> gitleaks) runs on every phase's audit and every push.

---

## P01 — Bootstrap (target: next)

**Theme:** wire up the build, lint, format, test, **security
scan**, and CI plumbing chosen in Phase A. Zero user-facing
features. Forces the audit + security harness to be
known-working before any business code lands, and de-risks the
scariest unknown (native-library bundling) up front.

### 🧰 Dev experience

- ✅ [FIBR-0001] **P01: project skeleton + lint + format + test + security-scan harness.**
  `pyproject.toml` (Python
  3.12+), `pip`+`venv` dev env, `ruff check` and `ruff format
  --check` clean on placeholder source, `pytest` exits 0 on an
  empty suite, **`bandit`, `pip-audit`, and `gitleaks` exit 0**.
  `.github/workflows/ci.yml` runs the same gates, and
  `scripts/ci-local.sh` mirrors them one-for-one (single source
  of truth for the gate list) so issues are caught before
  pushing. Dependencies: none. Lanes: build, ci, tests,
  security. Kind: chore. Source: planned.
  Resolved (2026-07-01): closed by /close-phase. Local gate exits 0; CI green in 23s; INV-1..INV-6 all demonstrated (INV-5 secret-injection demo flipped gitleaks + bandit red, then green on removal). /audit + /indie-review both returned zero actionable findings on the same pass. Impl commit 6b6ac64; tag FIBR-0001-complete.
  Kind: chore.
  Source: planned.
  Lanes: build, ci, tests, security.

- ✅ [FIBR-0002] **P01: `.gitignore` + secret-leak guard.**
  Standard Python ignore set (build artefacts,
  `.venv`, `__pycache__`, dep caches, IDE/OS files) plus
  explicit ignores for any local vault/`*.db`/`*.dmg`/AppImage
  build output, so **no financial data or build secret can ever
  be staged**. `gitleaks` (from FIBR-0001) is the backstop.
  Dependencies: FIBR-0001. Lanes: build, security. Kind: chore.
  Source: planned.
  Resolved 2026-07-01: .gitignore extended to block financial data (*.db/*.sqlite/*.sqlite3 + SQLite -wal/-shm/-journal sidecars) and build/packaging/tooling output; regression-locked by tests/features/gitignore/ (INV-1..INV-3 via git check-ignore --no-index). Spec cold-eyes-clean (4 loops); /audit + /indie-review zero actionable on the close pass (one indie-review LOW — global-git-excludes coupling — fixed inline). Full ci-local.sh gate green. Tag FIBR-0002-complete.
  Kind: chore.
  Lanes: build, security.

- ✅ [FIBR-0053] **Pre-push git hook runs the CI gate locally before every push.**
  Prompted by a CI failure email (commit a0cc895: gitleaks flagged the
  `shiboken6.isValid` false-positive in the FIBR-0051 spec prose; fixed in the
  next commit via `.gitleaks.toml`, so main was already green). Root cause was
  process, not drift: `ci.yml` already calls `scripts/ci-setup.sh` +
  `scripts/ci-local.sh` (the identical gate a dev runs), so green-locally ==
  green-in-CI — but that docs-only cold-eyes commit was pushed without running
  the gate. `.githooks/pre-push` runs `scripts/ci-local.sh` on every push (venv
  auto-activated), enabled via `git config core.hooksPath .githooks` (documented
  in CLAUDE.md; a fresh clone enables it once). Faithful full-gate match; a rare
  pypi timeout can flake pip-audit (retry / `--no-verify` for that transient
  case).
  **Layman:** Automatically checks your work before it leaves your machine, so a broken commit can't reach GitHub and trigger a failure email.
  Kind: chore.
  Lanes: ci, build.
  Source: user-request-2026-07-09 (CI failure email on a0cc895).

- ✅ [FIBR-0055] **Settings screen — a Settings menu item whose first control is a user-configurable auto-lock timeout, plus core preferences.**
  User request 2026-07-09: add a Settings menu item; the first thing to
  include is a user-set timeout for the auto-lock (lockout) feature. Pulls the
  Settings-screen + auto-lock-timeout portion of FIBR-0014 (P12) FORWARD as its
  own near-term item (it only depends on what is already built — the FIBR-0004
  auth/idle-lock spine and the FIBR-0052 shell); FIBR-0014 keeps the heavier
  encrypted-backup export/import + dark-theme polish pass, and hosts the
  FIBR-0017 language switcher.
  Resolved 2026-07-09 (FIBR-0055-complete): Settings screen shipped — File → Settings… opens a modal SettingsDialog with a user-configurable auto-lock timeout (1/5/10/15/30 min, default 10, persisted in the vault settings table, applied live to the idle timer) + a read-only base-currency display. No schema change. Spec /cold-eyes-converged (4 loops); TDD (19-leg tests/features/settings/); /audit 0, /indie-review 3 cold lanes clean (2 test-fidelity LOWs folded). Gate green 343 passed/1 skipped, mypy 0. Theme toggle + stored-PDF-password management remain in FIBR-0014.

  Scope (settle exact list at spec time -> /cold-eyes before TDD):
  - A **Settings** entry in the menubar (and/or a toolbar/Window-menu action)
  opening a Settings screen — a tab or a modal dialog (decide at design;
  a modal keeps it out of the tab rotation, a tab matches the workspace).
  - **Auto-lock timeout (the priority):** the FIBR-0004 idle auto-lock currently
  uses a FIXED inactivity timeout; make it user-configurable (e.g. 1/5/10/15/30
  min, with a sensible floor; a "never" option only behind an explicit warning
  since it defeats the security spine). Applied live to the running idle timer;
  persisted so it survives a restart. Persistence home to settle: the vault
  settings table (it is only needed while unlocked) vs the plaintext settings
  sibling used for window geometry (non-sensitive) — likely the vault settings
  table, read on unlock.
  - **Other settings suggested (cheap, tie into what exists; trim at design):**
  - Base / display currency (already a vault setting from FIBR-0004 — surface it).
  - Theme: dark / light / follow-system toggle (deferred to FIBR-0014 at spec
  time — the toggle needs the theme system that phase's polish pass builds).
  - Manage stored PDF passwords (FIBR-0009 stores per-account PDF passwords) —
  view which accounts have one remembered + a "forget" button.
  - "Confirm before deleting a statement" toggle (for the FIBR-0052 delete).
  - Startup tab preference (which workspace tab opens on launch — ties to the
  FIBR-0052 last-tab persistence).
  - "Check for updates" on/off (the opt-in switch FIBR-0054 auto-update needs;
  off by default — the update check is the one deliberate, consented egress).
  - Number / date format override (deferred at spec time: locale *number*
  formatting → FIBR-0017 i18n; user-chosen *date* format → FIBR-0048).
  - Every new string tr()-wrapped, layouts (no fixed geometry) for RTL, amounts
  via QLocale (coding.md §5.2), consistent with the rest of the UI.

  Dependencies: FIBR-0004 (auth + idle auto-lock), FIBR-0052 (shell). Relates to
  FIBR-0014 (P12 settings — narrowed to backup + theme polish + i18n host),
  FIBR-0009 (stored PDF passwords), FIBR-0054 (update-check opt-in).
  **Layman:** Adds a Settings menu where you can change how the app behaves — first and foremost, how long it waits before locking itself when you step away (right now that time is fixed). Also a home for a few other handy toggles.
  Kind: feature.
  Source: user-request-2026-07-09.

- ✅ [FIBR-0244] **Redact the real account number published in docs/specs/FIBR-0050.md.**
  `docs/specs/FIBR-0050.md` line 180 contains the user's REAL Standard Bank
  RCP Loan account number, twice, inside a quoted parser example. It was
  committed in `507a5f7` on 2026-07-05 and is an ancestor of `origin/main`,
  so it has been PUBLIC on GitHub since then. Found 2026-08-06 while
  writing FIBR-0086, whose INV-8 establishes that the no-real-data rule
  binds prose (specs, ROADMAP, CHANGELOG, commit messages) and not only
  test fixtures.
  Note the gate does NOT cover this: `gitleaks` matches credential and key
  patterns, and a bare 9-digit account number is not one — so the leak
  passed every CI run since it landed.
  Decision required from the user, because the options differ in cost and
  none fully undoes publication: (a) redact the line in HEAD so the current
  tree is clean — cheap, honest, leaves history intact; (b) additionally
  rewrite published history (filter-repo + force-push) — messy, breaks
  clones, and does not remove the value from forks, caches or anyone who
  already pulled; (c) accept it. Recommendation: (a), plus rotating nothing
  since an account number is not a credential — it is a privacy exposure,
  not an access one.
  When fixing, replace with a synthetic stand-in the way
  `docs/specs/FIBR-0086-account-number-auto-detect.md` §2.2 does, so the
  parser example still demonstrates what it was written to demonstrate.
  Sweep the rest of `docs/` in the same pass: this was found by a targeted
  grep for six known numbers, which is not a general check.
  **Layman:** One of our design documents accidentally contains a real bank account number and has been public on GitHub for a month; decide whether to just clean it up going forward or also rewrite the published history.
  Kind: security.
  Source: in-session-2026-08-06 (found during FIBR-0086 cold-eyes).
  Resolved (2026-08-06): option (a) — redacted in HEAD, history left
  intact (user decision 2026-08-06). The sweep found FOUR real values, not
  the one this bullet filed, across six sites; each replaced by a
  length-preserving synthetic stand-in per FIBR-0086 §2.2:
  (1) the RCP Loan reference number, twice in docs/specs/FIBR-0050.md
  § Family A; (2) the real card PAN mask and the real Investment account
  number, both published by FIBR-0050's own "fixtures must never use
  these" sentence — the prohibition was the leak, so the sentence now
  names no values at all; (3) an unlabelled 10-digit number in the
  letterhead/footer examples on ROADMAP.md FIBR-0115 + FIBR-0119 and
  .claude/workflow.md §3; (4) the same number as a live TEST FIXTURE line
  in tests/features/standard_bank_pdf/test_standard_bank.py — a real
  number inside the suite the no-real-data rule most directly binds.
  Characterised against the corpus before redacting, so a stand-in was not
  swapped in for bank boilerplate: the RCP number appears in one folder
  (that account's own) and the Investment number in one; the 10-digit one
  appears across Credit Card, Home Loan and Investment, so it identifies
  the customer or the print batch rather than any single account — not a
  public bank registration number, and redacted on that basis.
  _is_boilerplate() matches any all-digit line, so the fixture swap is
  behaviour-neutral; tests/features/standard_bank_pdf/ 106 passed.
  Verified zero residual occurrences repo-wide. The user's ID number was
  never in the repo. Nothing rotated: these are privacy exposures, not
  credentials.
  Still open: the general check does not exist. This was found by grepping
  long digit-runs, which would miss a real merchant, address or date-of-
  birth. Filed as FIBR-0246.

- 📋 [FIBR-0246] **A real-personal-data check the gate actually runs — gitleaks does not cover it.**
  FIBR-0244 found four real values published across six sites, by grepping
  for long digit-runs. That is a one-off, not a check: it would miss a real
  merchant name, a real address, a real date of birth, or an account number
  written with spaces or in a shorter grouping. gitleaks matches credential
  and key patterns only, so every one of those passed CI since 2026-07-05.
  Wanted: a gate stage that fails on real personal/financial data in
  tracked files. Sketch — a deny-list file, gitignored and never committed,
  holding the user's real values (account numbers in every grouping the
  statements print, the card PAN and its mask, the ID number), plus a
  committed rule set for the structural patterns (a bare 9-13 digit run
  outside a fenced block known to be synthetic; a PAN-shaped group). Runs
  over tracked files in ci-local.sh; absent deny-list degrades to the
  structural rules alone so CI still works without the secret half.
  Note the awkward part, which is why this is a spec and not a chore: the
  deny-list is itself the most sensitive file in the project, and a check
  that greps for real numbers must never print the match. Report path:line
  and the rule that fired, never the value.
  Scope also covers prose, not just fixtures — FIBR-0244's worst site was a
  spec sentence forbidding the values by quoting them.
  **Layman:** Add an automatic check that stops real bank details from ever being committed — the current security scanner only looks for passwords and keys, so it has never checked for these.
  Kind: security.
  Source: in-session-2026-08-06 (gap found while closing FIBR-0244).

- 📋 [FIBR-0247] **The INV-8 leak scanner cannot see git history, so a redaction reads as a fix.**
  tests/features/account_detect/test_no_real_data.py walks `git ls-files`,
  which is the working tree only. A real number published in an earlier
  commit is invisible to it.
  This is live, not hypothetical: FIBR-0244 redacted 4 real values in
  `0664d55` and, per the user's decision, left history intact. Those
  values remain reachable in this PUBLIC repo via `git log -p` and the
  GitHub commit view, while the guard reports green.
  The hazard is the false assurance, not the leak itself (which the user
  accepted knowingly): a future developer pastes a number, notices,
  commits a redaction, sees the test pass, and concludes it is closed.
  Wanted: either scan history too (`git rev-list --all` + `git grep` per
  commit is O(history) but runs once pre-push), or — cheaper and probably
  better — have the test SAY what it does not cover, and add the same
  sentence to the spec's §11 table. A guard whose blind spot is documented
  is honest; one that looks total is worse than none.
  **Layman:** Our check for leaked bank numbers only looks at the current files, not at older versions — so a number we cleaned up still sits in the published history while the check says all clear.
  Kind: test.
  Source: in-session-2026-08-06 (FIBR-0086 review lane 3).

- ✅ [FIBR-0248] **FINBREAK_CORPUS_NUMBERS is wired nowhere, so INV-8 skips on every run.**
  The variable appears only in the test that reads it and in two spec
  documents. It is absent from `scripts/ci-local.sh`, `.githooks/pre-push`
  and CLAUDE.md's "Run the full gate" and push-policy sections.
  So the pre-push hook runs INV-8's test as a SKIP every time, and the
  invariant's only enforcement is a developer remembering an undocumented
  environment variable. CI genuinely cannot hold the values, and that part
  is by design — but the local half was never wired up.
  Wanted: read the keys from a gitignored file (e.g. `.corpus-numbers`,
  already outside the repo) with the env var as an override, and name it
  in CLAUDE.md's gate section so it is discoverable. Then the pre-push hook
  enforces it for whoever has the file, and still skips cleanly for whoever
  does not.
  **Layman:** The leaked-bank-number check needs a setting that nothing sets, so in practice it never actually runs.
  Kind: chore.
  Source: in-session-2026-08-06 (FIBR-0086 review lane 3).
  Resolved (2026-08-14): built exactly what the bullet asked for — the keys
  now come from a gitignored `.corpus-numbers` at the repo root (one per
  line), with `FINBREAK_CORPUS_NUMBERS` kept as a one-off override, and
  CLAUDE.md's gate section names it so it is discoverable. Whoever holds
  the file gets INV-8 enforced by the pre-push hook from then on; whoever
  does not — CI, always and by design — still gets a clean skip rather
  than an error. Gate green (1910 passed, the corpus test still skipping
  here because this machine has no file yet).

  Two traps found while building it, neither in the bullet. The
  `.gitignore` entry is verified by actually creating the file and
  confirming `git check-ignore` refuses it, because committing that file
  would plant in a PUBLIC repo precisely what the guard exists to catch —
  asserting the rule rather than trusting the pattern. And a `#` comment is
  stripped rather than merely tolerated: a hand-maintained file invites
  labels, and "# account 1 of 3" would otherwise contribute `13` as a key,
  which matches most of the tree and would get the guard switched off as
  noise within a day.

  Five loader tests cover file-when-env-unset, env-overrides-file,
  absent-both-still-skips, comment digits, and both separators. Every
  number in them is invented; the real values are never printed, never
  written to a tracked file and never passed on a command line, and
  CLAUDE.md now says so where a developer will read it.

  Still true and unchanged: CI cannot hold the values, so this check is
  local-only. FIBR-0246 and FIBR-0247 remain open and are the other two
  halves of this guard.

- ✅ [FIBR-0249] **A remembered statement password is stored against the pick-step account, which auto-detect now routinely changes.**
  `_begin_decrypt` / `_after_decrypt` look up and persist the remembered
  PDF password against `_target_account_id()` at decrypt time. That is
  necessarily the PICK-STEP account, because auto-detect cannot run until
  the PDF has been decrypted and parsed.
  Pre-existing FIBR-0057 behaviour, but FIBR-0086 changes its frequency:
  "the destination moves after decrypt" went from rare to routine.
  Consequence: the password is written against whichever account sorts
  first alphabetically; `_carry_stored_pw_to_committed_account` COPIES it
  to the committed account rather than moving it, so a statement password
  ends up permanently on an unrelated account. And next month the
  stored-password auto-try consults the pick-step account again, so the
  user is re-prompted anyway — the feature silently stops working for them.
  Wanted: move rather than copy on commit, and re-key the stored password
  once the destination is settled.
  **Layman:** When you tick "remember this password" for a locked PDF, it gets saved against whichever account was selected before the app worked out the right one — so it lands on an unrelated account and you get asked again next month.
  Kind: fix.
  Source: in-session-2026-08-06 (FIBR-0086 review lane 2).
  Resolved (2026-08-14): moves rather than copies, as the bullet asked.
  Gate green (1912 passed).

  The copy had a real reason, which the bullet did not mention and a plain
  move would have broken: the provisional account's password MIGHT be its
  own, because a stored-password auto-try that failed is exactly what leads
  to the manual prompt. The old code protected that by never removing
  anything — which is what left this statement's password on an unrelated
  account. Fix: `_after_decrypt` now records what was there BEFORE it
  writes, and the carry restores that value — the account's own password if
  it had one, nothing if it did not. So it knows instead of guessing. Both
  halves are tested, the restore case being the one that would otherwise
  have silently destroyed a user's own remembered password.

  The prior value rides inside the `_stored_pw` tuple deliberately:
  FIBR-0009 INV-11 greps the wizard source for any `self._*password`
  attribute, so a separate field would have tripped a credential-hygiene
  backstop.

  The bullet's second half — "re-key once the destination is settled" — is
  what the move does. But the bullet's re-prompt claim needs correcting for
  the record: under the OLD copy the user was NOT re-prompted, because the
  pick-step account held a copy and the auto-try succeeded off it. That
  convenience was a side-effect of the wrong-account credential. Removing
  the defect removes the accident, so the re-prompt is now real, and the
  actual cause is that `_begin_decrypt` looks up only the pick-step
  account. Filed as FIBR-0274 rather than fixed here: the obvious remedy
  weakens FIBR-0009 INV-4's structural "attempted at most once", which
  wants a decision and a test rather than a quiet widening.

- 📋 [FIBR-0250] **normalise_account_number's zero-strip is ASCII-only while its digit filter is not.**
  `re.sub(r"\D", "", raw)` is Unicode-aware and keeps Arabic-Indic or
  fullwidth digits; `.lstrip("0")` then does nothing to them, so the key
  never equals its ASCII counterpart.
  Verified: a fullwidth spelling returns unchanged rather than normalising.
  Bounded — it can only fail to match, never mis-match, so the outcome is
  `no_match` (offer to create a duplicate), not a wrong filing. No
  collision could be constructed.
  Not worth fixing on its own; fix it when something else touches this
  function. `unicodedata.digit()` per character, or restricting the filter
  to `[0-9]`, would close it — the latter also makes the function's
  contract match its docstring.
  **Layman:** An account number written in non-Western digits would not be recognised as the same number, so the app would offer to create a duplicate account.
  Kind: fix.
  Source: in-session-2026-08-06 (FIBR-0086 review lane 1).
  Considered and deliberately left open (2026-08-12), on this bullet's own instruction: "fix it when something else touches this function". It was picked up alongside FIBR-0253/0254, then put back — nothing in that run touches `normalise_account_number`, and fixing it standalone is not the cheap change it looks like. `docs/specs/FIBR-0086` §4.4 quotes the implementation verbatim (line ~397), so the fix is a spec amendment plus its rule-14 cold-read gate; and `tests/features/account_detect/spec.md` INV-8's leak scanner normalises the haystack "the way `normalise_account_number` does", so its helper has to move in step or the scanner starts missing the spelling it guards against. That is three surfaces for a bug that, as recorded above, can only fail to match — never mis-match. The precondition for fixing it is unchanged: the next change that opens this function.

- ✅ [FIBR-0252] **StandardBankImporter.parse discards its per-row errors, so a dropped row is invisible.**
  `standard_bank.py`'s `parse` returns `ParseResult(result.drafts, [],
  start, end, ...)` — an empty error list, discarding the errors `_split`
  had just separated out. So `ImportPreview.errors` is empty for every
  Standard Bank statement, and FIBR-0085's new Errors column
  (`BatchFile.error_count`, set from `len(parsed.errors)`) reads 0 for
  all five SB families — which are exactly the layouts this user's own
  corpus is made of.

  FIBR-0085 § 4.2 carries `error_count` precisely because "a file where
  40 of 50 rows failed commits 10 and would report '10 added' with no
  hint that 40 vanished — in a money app a silently dropped row is the
  defect". That argument is defeated on the SB path. `_draft`'s own
  docstring names a reachable case (a printed `0.00` fee line).

  PRE-EXISTING, not introduced by FIBR-0085 — last touched by FIBR-0086.
  Filed rather than fixed in passing because it needs its own regression
  test against a synthetic SB fixture with a deliberately unreadable row,
  and because propagating the errors changes what the single-file preview
  table shows too (it interleaves errors into the row list), which is a
  visible behaviour change deserving its own pass.

  Fix: return `result.errors` instead of `[]`, and add a test asserting a
  malformed SB row reaches `ImportPreview.errors` rather than vanishing.
  **Layman:** If a line on a Standard Bank statement cannot be read, the app throws that fact away — so you are told "53 added" with no hint that anything was skipped.
  Kind: fix.
  Source: code-quality-review-2026-08-06 (FIBR-0085 close, service lane).
  Progress (2026-08-06): step 3/4 done — TDD green. The one-line fix is in
  (`parse` now returns `result.errors`), with the five specced tests and the
  new synthetic fixture `family_a_zero_fee.pdf`. Four were seen red against
  pre-fix code for the reason under test; INV-6's is green by design (§7).
  The fixture makes the globbed `_PRE_E_FIXTURES` 15, so the SB suite's count
  assertion moved 14 -> 15 and its hand-written detection list gained an entry.
  Both test-suite contracts amended per §12. Gate green: 1867 passed /
  3 skipped. Next: steps 5-6 (/audit + /code-quality-review).
  Resolved (2026-08-07): `parse` now returns `result.errors`. Five new tests
  (INV-1..INV-6) plus the synthetic fixture `family_a_zero_fee.pdf`; four seen
  red for the reason under test, INV-6's green by design. Both test-suite
  contracts amended (§12); the SB suite's globbed fixture count moved 14 -> 15
  and its detection list gained an entry. Closed by /close-phase: static layer
  green, two independent cold review lanes — correctness returned NO defects
  (traced `.errors` through all six consumers; dedup, commit-writes, both
  balance gates, the row cap and the coverage span stay drafts-only, so no
  money figure moves), test-validity returned 1 LOW + 2 INFO, all fixed inline
  per the standing directive. The LOW was worth the lane: INV-5's leg asserted
  an order-INSENSITIVE mapping while claiming "in file order", verified by
  mutation; it is now an ordered sequence and the spec's §5/§11 were amended to
  match what was built. Gate green 1867 passed / 3 skipped. Journal
  `docs/journal/FIBR-0252.md`. FIBR-0253/0254/0255 stay out of scope (§9).

- ✅ [FIBR-0253] **The all-rows-failed preview banner gives CSV-only advice on a PDF or OFX import.**
  `ui/import_wizard.py`'s FIBR-0146 D7 banner reads "None of the rows
  could be imported. Go back and check the column mapping and the Date
  format match your statement." Its visibility test in
  `_apply_preview_counts` is purely count-based — `new_count == 0 and
  duplicate_count == 0 and len(preview.errors) > 0` — so it fires on any
  source, but its remedy names the CSV mapping step, which no PDF or OFX
  import ever visits.

  PRE-EXISTING and reachable today via OFX (`ofx_importer` collects
  per-row errors). FIBR-0252 widens the reach to Standard Bank PDFs: a
  Family A or E statement prints no closing balance, so `_verify_checksum`
  returns early and a statement whose every row is unimportable reaches
  the preview as 0 new / 0 duplicate / N error instead of raising.

  Fix: either gate the banner on the CSV path (the only one with a
  mapping step), or reword it to name a remedy that holds for every
  source. Deliberately NOT bundled into FIBR-0252, which is confined to
  the error channel itself.
  **Layman:** If no row of a PDF statement can be read, the app tells you to check the column mapping — a screen that only exists for spreadsheet files, so the advice cannot be followed.
  Kind: fix.
  Source: in-session-2026-08-06 (FIBR-0252 spec, blast-radius scan).
  Rationale corrected (2026-08-06, FIBR-0252 cold-eyes loop 3): the
  reason given above — "a Family A or E statement prints no closing
  balance, so `_verify_checksum` returns early" — is the WRONG reason and
  understates the reach. When every row errors on a zero amount, the
  drafts sum to zero, so the printed opening and closing are equal by
  construction and the gate reconciles on EVERY family, not only the
  closing-less ones. Measured on A and E; B/C/D follow from
  `_verify_checksum` comparing `opening ± 0` against an equal `closing`.
  Family E rejects only when a printed Payments/Deposits total is
  non-zero. See FIBR-0252 §6.
  Resolved (2026-08-12). The count-based trigger is unchanged — it is right for every source — and only the sentence moves: `_banner_text()` returns the CSV wording when `_csv_source` is set and otherwise "None of the rows could be imported. Each row below says what went wrong with it.", which points at the per-row reasons the preview table already renders. `_csv_source` is cleared on every pick in `_select_file` and set only on the CSV fall-through past the OFX and PDF sniffs, so a PDF picked after a CSV cannot inherit the mapping remedy. Covered by `test_FIBR0253_banner_remedy_matches_the_source`, which drives the real `_select_file` dispatch for both legs rather than setting the flag by hand. FIBR-0146 D7 and INV-3 amended in the same commit.
  Corrected same day (2026-08-12) by the rule-14 `review-contract` gate on FIBR-0146, before the first fix had been out of the tree an hour. Both cold lanes independently found the discriminator wrong: `_csv_source` treated every PDF as unmapped, but only a RECOGNISED Standard Bank statement skips the map step — a generic non-SB PDF is extracted to a CSV-text table and mapped exactly like a CSV. FIBR-0146's own bug report is a PDF with 165 error rows, so the first fix removed the mapping remedy from the very user D7 was written for: a regression, not merely an incomplete fix. Now keyed on `_has_mapping_step`, set on the CSV fall-through in `_select_file` AND past the SB reader in `_continue_after_decrypt`. The test gained a `non_sb.pdf` leg proven red against the previous code and green after — same file extension as the SB leg, opposite answer, which is why no filename or sniff test can stand in for it. D7, INV-3, the Test plan and the CHANGELOG entry were all corrected to match.

- ✅ [FIBR-0254] **The batch report line contradicts the Errors column, and mis-pluralises "1 rows".**
  Two defects in `ui/import_batch.py::report_line`, both pre-existing and
  both made reachable on Standard Bank files by FIBR-0252.

  1. The `", {n} rows couldn't be read"` clause is appended ONLY on the
  `committed` branch. An `already_imported` record (a span exists and
  zero rows are new) returns "Already imported — nothing new in this
  file" while the Errors column beside it reads N — the Status and
  Errors cells of one row contradicting each other.
  2. `"{n} rows couldn't be read"` has no singular form, so one
  unreadable row reads "1 rows couldn't be read".

  Reachable via CSV and OFX today (both collect per-row errors);
  FIBR-0252 makes Standard Bank PDFs a third source, which is the
  user's own corpus.

  Fix: append the error clause on every outcome that can carry one, not
  just `committed`, and give the count a singular form. Deliberately NOT
  bundled into FIBR-0252, which is confined to the parse-side error
  channel.
  **Layman:** In the multi-file import table, a file that was already imported says "nothing new in this file" while the Errors column next to it shows unreadable rows — and a single bad row reads "1 rows couldn't be read".
  Kind: fix.
  Source: in-session-2026-08-06 (FIBR-0252 cold-eyes loop 2, blast-radius scan).
  Precondition pinned (2026-08-06, FIBR-0252 cold-eyes loop 5): defect 1
  is **re-import only**. `BatchImportService.review` reads the span from
  `StatementPeriodRepository.id_for_span`, i.e. a `statement_periods` row
  already in the vault — not the span the parse just produced. So a FIRST
  import of a file with unreadable rows lands `ready` -> `committed` and
  DOES append ", N rows couldn't be read" correctly. The contradiction
  appears only on a second run of the same file, when the span exists and
  the cumulative new count is zero. Defect 2 (the "1 rows" plural) is
  unconditional.
  Resolved (2026-08-12). Both defects fixed in `BatchReviewWidget`: the unreadable-row clause moved out of the `committed` branch into `_with_unreadable_rows`, which `committed` and `already_imported` both call — so a re-imported file with unreadable rows no longer contradicts its own Errors cell — and the count has a singular form. The plural is two `tr` strings rather than Qt's `%n`, because no translation is loaded yet (FIBR-0017) and an untranslated `%n` renders its source text, which would have given "1 row(s)" — the same defect in a new spelling. Covered by `test_FIBR0254_report_line_owns_its_unreadable_rows` (tests/features/batch_import/test_batch_import_ui.py), each leg asserting its own precondition so a line that appended nothing could not pass. FIBR-0085 §4.8's outcome table amended in the same commit; its §11 coverage row in FIBR-0252 is left as that spec's own record of what it deferred here.

- ✅ [FIBR-0255] **A closing-less Savings statement can import a wrong total with no gate firing.**
  `_verify_checksum` takes its `closing is None` early return for
  Family A and Family E, and `_verify_e_totals` degrades to nothing when
  neither printed total is present. So on those layouts a row that
  `_draft` rejects — one that DID move money — is dropped from the
  drafts with no completeness gate left to notice the shortfall.

  Reproduced end-to-end this session on a synthetic closing-less Savings
  page whose middle row moves 100.00 under the invalid date `05 32`:

  bad date, NO closing (Savings)   drafts=2 sum=15000 errors=[]
  bad date, WITH closing           RAISES "this statement didn't add up …"

  The page really moves -100 -100 +250 = +50; the import takes +150. A
  transaction worth 100.00 vanishes and the totals are wrong by exactly
  that, silently.

  PRE-EXISTING and NOT introduced by FIBR-0252 — which is the mitigation,
  not the cause: it makes the dropped row visible in the preview and the
  Errors column instead of discarding the only trace. The remaining gap
  is parser-side (these layouts have no completeness gate to fail), which
  is why it is its own item rather than part of FIBR-0252.

  Fix: give the closing-less layouts a completeness check they currently
  lack, or refuse to import when a money-moving row was dropped and no
  gate could verify the remainder. Both need their own design pass —
  Family A Savings legitimately prints no closing, so this cannot simply
  become an all-or-nothing refusal.
  **Layman:** On a savings statement that prints no closing balance, a line the app cannot read is dropped and the totals come out wrong — with nothing to tell you it happened.
  Kind: fix.
  Source: in-session-2026-08-06 (FIBR-0252 cold-eyes loop 3, reproduced; filed at loop 4).
  Progress (2026-08-12): specced as docs/specs/FIBR-0255-money-moving-row-refusal.md and gated with review-contract — 3 loops, 13 verified findings, all fixed, none filed. Design chosen: refuse at the row rather than build a completeness gate for the closing-less layouts. _draft degrades a rejected row ONLY when it moved no money (signed == 0, FIBR-0216's own safety premise); a non-zero row raises a new refusal distinct from the four "didn't add up" messages, on every family. Loop 1 rewrote the central argument: a zero-amount row CAN be rejected for its date or description, so the rejection reason is not a proxy for the amount and the guard must key on the amount alone.
  Resolved (2026-08-12): _draft now degrades a rejected row ONLY when it moved no money (signed == 0) and raises a new refusal otherwise, on every family — the all-or-nothing contract applied where FIBR-0216's own safety premise ("it contributes 0 to both") actually holds. The message is distinct from the four "didn't add up" ones because the statement's arithmetic IS fine; only storing one row failed. Spec: docs/specs/FIBR-0255-money-moving-row-refusal.md (review-contract, 3 loops + 1 implementation row, 14 findings, all fixed). Tests: 4 new legs in tests/features/standard_bank_pdf/, the two behavioural ones seen red pre-fix. The key subtlety, which cost the review its largest finding: the discriminator is the AMOUNT, never the rejection reason — parse_transaction checks description and date before the amount, so a printed 0.00 line with a garbled date arrives with signed == 0 and an ISO-date reason and must still degrade. No committed fixture moved (the 23-fixture sweep is byte-identical before and after). FIBR-0050 INV-11 and two neighbouring clauses were corrected in the same commit: they said the reader raises on ANY parse_transaction rejection, which FIBR-0216 had already made false. Gate green: 1875 passed, 3 skipped.

- ✅ [FIBR-0260] **CLAUDE.md § Build and test omits the `ci-setup.sh` step and the `git` requirement.**
  Found by EXECUTING the section literally in a fresh
  `python:3.12-slim-bookworm` container (the image `ci.yml` runs) on
  2026-08-11. (a) The "One-time dev setup" block's four steps all
  succeed, then `./scripts/ci-local.sh` exits 127 — `git: command not
  found`, `shellcheck: command not found` — because `scripts/ci-setup.sh`
  is never named as the reader's own step, only as the pin list and as
  something `ci.yml`/`ci-docker.sh` call. (b) `git` is a RUNTIME
  dependency of the gate (the gitignore + bundling feature tests shell
  out to `git check-ignore` / `git rev-parse` / `git ls-files`) and is
  absent from the Requirements table a reader provisions from; the fact
  appears only as background in the "Reproduce GitHub CI EXACTLY"
  paragraph. Ordering is not the defect — the steps run in the order
  given, they just cannot reach a green gate.
  **Layman:** Following our own setup instructions on a clean machine did not actually get you to a working test run — two steps were missing from the list.
  Kind: doc-fix.
  Source: runbook-execution-2026-08-11.
  Resolved 2026-08-11 (b9baf16): `scripts/ci-setup.sh` is now the third
  line of the "One-time dev setup" block, with the apt/Debian assumption
  stated and the manual Python half kept for other distros; `git` has a
  row in the Requirements table naming it a RUN-time dependency of the
  gate. Confirmed the way the defect was found — a fresh clone in a
  fresh `python:3.12-slim-bookworm` container, the section followed
  literally with nothing added: venv 0, ci-setup 0, self-test 0,
  ci-local 0, "All gates passed" (1869 passed, 5 skipped).

- ✅ [FIBR-0264] **The day/month ambiguity nudge fires on a May statement, where the tie is not about day order.**
  `detect_date_format` returns `ambiguous=True` for a May-only
  named-month column, because English spells the abbreviated and full
  month name identically, so `%d %b %Y` and `%d %B %Y` both parse every
  row and tie on count. Verified: `["20 May 2026", "21 May 2026",
  "22 May 2026"]` -> ambiguous=True, while the same call over
  `"20 Jun 2026"` or `"20 January 2026"` -> ambiguous=False. Note the day
  numbers are 20-22, so FIBR-0146 D2's stated precondition for a tie
  (every sampled day-number <= 12) does not hold either; D2 was amended
  in the same pass to state this second tie axis.

  The parse is unaffected -- both candidates render May identically, so
  whichever wins reads the column correctly. The defect is only the D6
  nudge text: `_date_ambiguous` drives "the day and month might be the
  other way around", which is not the axis this tie is on. A monthly
  statement is normal input, so this is not a corner case.

  Fix: make the nudge conditional on the tied candidates actually
  differing in day/month order, or use a neutral "check these dates are
  right" sentence when they do not. Left open deliberately: the review
  that found it was a documentation gate, and changing user-facing
  wording is a code decision that wants its own test.
  **Layman:** On a statement dated in May, the app warns that the day and month might be swapped — but the dates are being read correctly and the warning describes a problem that isn't there.
  Kind: fix.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0146, loop 1).
  Resolved (2026-08-14): took the bullet's first option — make the nudge
  conditional on the tied candidates actually differing — rather than the
  neutral-sentence fallback, because it makes the flag and the sentence
  mean the same thing instead of adding a second sentence to keep in sync.
  `ambiguous` now requires a parse-count tie AND that the tied candidates
  read some row to a DIFFERENT date. Over one column of dates the only way
  that happens is a day/month transposition, which is precisely what "the
  day and month might be the other way around" says.

  May now reads unambiguous; the parse was never affected, so nothing about
  which format wins changed. Gate green (1904 passed).

  Three May columns asserted, two proven red first. One of them uses day
  numbers <= 12 deliberately, so the fix cannot be confused with D2's
  day-number precondition — the axis the bullet pointed out does not hold
  here. The opposite leg is guarded as well: a transposed column stays
  ambiguous, with a precondition asserting `%d/%m/%Y` and `%m/%d/%Y` really
  do read the same cell as different days, so that leg cannot pass
  vacuously. Covered by INV-9 in tests/features/import_date_detect/spec.md.

  No spec amendment needed: FIBR-0146 D2 already states the %b/%B tie axis,
  having been amended when this bullet was filed.

- 📋 [FIBR-0265] **FIBR-0085 gives Cancel-during-SCAN two contradictory behaviours.**
  §4.3 says "Cancel during SCAN behaves the same way as during RUN:
  every record not yet reached becomes `not_attempted` with the cancelled
  wording" -- which implies the table stays on screen to show them.
  §4.6 says Cancel "before RUN ... drops the whole batch ... and returns
  to the pick step". SCAN is before RUN, so the two prescribe opposite
  responses to the same press: on §4.6's reading §4.3's `not_attempted`
  marking is unobservable and its stated purpose (not stranding rows
  reading "Waiting...") is moot.

  Not fixed in the gate that found it: settling it needs a decision about
  what the button should do in three distinct phases (during SCAN, after
  SCAN but before RUN, during RUN), not a wording repair. Check the
  shipped behaviour first -- the code may already have picked one, in
  which case this is a doc-only correction.
  **Layman:** Two parts of the batch-import design describe what the Cancel button does mid-scan in ways that cannot both be true.
  Kind: doc-fix.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0085, loop 1).

- 📋 [FIBR-0266] **FIBR-0085 leaves the draft-cap outcome undefined when it trips during ASK.**
  §4.3 has ASK's resume path run "the rest of the ladder, INCLUDING the
  draft-cap check", but the only stated consequence of tripping that cap
  is SCAN's: "this and every later record become `not_attempted`; stop".
  That is written for SCAN's path-ordered loop and has no meaning over
  ASK's question queue -- "every later record" is undefined there.

  An implementer must invent one of two behaviours: mark only the resumed
  record `not_attempted` and carry on asking, or mark every remaining
  unscanned record and abort ASK. The two produce different batches from
  the same input. Left open because it is a behaviour decision, not a
  wording repair.
  **Layman:** The batch-import design says what happens when a run hits its size limit while scanning files, but not when it hits the same limit after the user answers a question.
  Kind: doc-fix.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0085, loop 1).

- ✅ [FIBR-0267] **FIBR-0085 has five more verified doc-vs-code defects, and at 1357 lines wants splitting rather than another loop.**
  Loop 2 confirmed loop 1's four fixes held and that the FIBR-0254
  amendment is correct, then found five NEW defects in sections neither
  loop-1 lane had reached. That pattern -- a fresh cold read finding
  fresh regions each pass -- is the size signal, not a document that
  keeps regressing. 1357 lines against siblings of ~400-650.

  All five verified against the tree, none touching FIBR-0254:

  1. §4.5 says the vault baseline is "read through ImportService (the
  same reads _dedup performs)". The shipped `cumulative_counts` does
  NO vault read: its only use of `imports` is `imports._key(draft)`,
  and the vault half arrives already applied in
  `preview.duplicate_row_numbers`. Building to the spec subtracts the
  vault half twice and under-reports New (breaks INV-4).
  2. §4.6 states account-cell clickability as "exactly" two tests;
  `_choose_account` applies a third the spec states nowhere --
  `self._finished or self._running`. Building the "exactly" rule
  leaves the cell live DURING the run, so a user can retarget a row
  the chain is about to reach.
  3. §4.6 does not say whether Close appears after a CANCELLED run. A
  cancelled RUN is neither "before RUN" nor plainly "finished", and
  Close is the only emitter of `done` (INV-14) -- so an implementer
  can strand the user on a screen with no exit.
  4. §4.6's account-change route says "the row becomes `ready`" and names
  only `cumulative_counts` as the follow-up, where §4.3's REVIEW block
  requires outcomes re-derived in BOTH directions. Wiring §4.6 alone
  means a retargeted `already_imported` row never returns to `ready`
  (INV-10's third leg).
  5. INV-6's *Breaks when* clause names an omission ("created and not
  added to `_FILES`") that its own test cannot observe, because the
  test greps only the members of `_FILES`. Unfalsifiable as written.

  Do the split first, then fix these in the parts they land in. The
  review instrument is fine; the document is too big for one cold read.
  **Layman:** The batch-import design document describes the shipped code wrongly in five more places; it is also long enough that each review pass reaches different parts of it, so it should be split before it is reviewed again.
  Kind: doc-fix.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0085, loop 2).
  Progress (2026-08-14): scoped but NOT split — deliberately stopped short.
  FIBR-0272 has now done the same job on FIBR-0146 (746 → 422 + 413), so
  there is a worked precedent to copy; what follows is this document's map,
  so the next session does not re-derive it.

  Structure differs from FIBR-0146's: numbered `## 1..14` sections, no
  D-items. 1376 lines, of which §4 Design is 622 (lines 171-793) and §5
  Invariants 210 (794-1004). §4 has eight subsections and they align with a
  REAL module boundary rather than a judgement call — CLAUDE.md's module
  map already splits this feature three ways, and §4.2 (per-file record),
  4.3 (four passes), 4.4 (PDF password with no pick-step account) and 4.5
  (cumulative dedup) are the Qt-free `services/batch_import.py` decisions,
  while 4.6 (review step), 4.7 (driving passes with no nested event loop)
  and 4.8 (outcomes) are `ui/import_batch.py`. §4.1 "Where the work lands"
  is shared orientation and belongs with whichever half keeps the id.

  The promising part: each invariant in §5 is a self-contained bullet
  carrying its own `*Test:*` line, and those name either
  `test_batch_import.py` (service) or `test_batch_import_ui.py` (UI). So
  the invariant allocation can be driven by an objective signal instead of
  a reading — which is exactly what made FIBR-0146's invariant table the
  hard part. A first pass suggested roughly 7 service / 5 UI / 1 spanning
  (INV-15, 92 lines) / 6 unclassified.

  Do NOT trust those counts. The classifier matched `- **INV-N**` outside
  §5 as well (§7 and §11 refer back to them), which double-counted four ids
  and produced one negative block size. The seam signal is real; that
  measurement of it is not. Re-run it bounded strictly to lines 794-1004
  before cutting anything.

  Still unread and needing allocation: §6 failure modes, §7 tests, §9 out
  of scope, §10 resource cost, §11 what checks this, §12 cross-doc impact.
  §13 loop log and §14 as-built deviations are frozen records and stay with
  the id, per the FIBR-0192 precedent that a split is recorded as a
  loop-log row with no reviewer dispatched.

  Method that worked on FIBR-0146 and should be reused: assert every
  section boundary in a script BEFORE writing, move text verbatim rather
  than retyping, then check that no substantive line of the original is
  absent from both halves, then doc_integrity over the union. Keep the same
  id with a `-<topic>.md` suffix so existing citations resolve untouched —
  that is what made the last one cheap.

  Resolved (2026-08-18): split THREE ways, not two — measured, the service
  half of §4 is 352 lines against the review step's 190, so moving only the
  widget out would have left the file near 1130. 1376 → 705
  (`FIBR-0085-batch-statement-import.md`, the shared contract and every
  frozen record) + 535 (`FIBR-0085-batch-import-service.md`, §§ 4.2–4.5 and
  INV-1, 2, 4, 9, 10, 11, 13, 15) + 375
  (`FIBR-0085-batch-import-review-step.md`, §§ 4.6–4.8 and INV-3, 5, 6, 7,
  8, 14). The invariant allocation was driven by the test file each INV
  already names, re-run bounded strictly to §5 as this bullet required; the
  earlier count was wrong as warned. Same id, no renumbering, every moved
  line verbatim — a script asserted all 27 section and 15 invariant
  boundaries before writing, then checked no substantive line of the 1376
  was absent from the union. All five defects re-verified still live against
  the tree, then fixed in the parts they landed in. INV-6's real gap (a
  guard that cannot observe its own omission) is filed as FIBR-0277.

- ✅ [FIBR-0268] **A malformed CSV body crashes out of the date-column slot, which catches nothing.**
  `_date_samples` reads through `read_rows`, which translates a
  `csv.Error` from a structurally-broken body (an unterminated quote, a
  stray NUL, a field over `csv.field_size_limit`) into the friendly
  `ValueError` this module's boundary uses. The translation is right; the
  catching is missing on two of the three entry points.

  - D5(a), the CSV pick, runs inside `_select_file`'s try -> the message
  is shown, picker left at its ISO default. Correct.
  - D5(b) `_continue_after_decrypt` and D5(c) `_on_date_column_changed`
  both call `_autodetect_date_format()` with no guard, and it calls
  `_date_samples` directly. The `ValueError` escapes the Qt slot.

  The header parses fine in this case, so `read_header` does not refuse
  the file first -- the user reaches the map step normally and then
  changes the Date column, which is the documented way to use the screen.

  Found because FIBR-0146 D8 was amended to claim "on a raise the map
  step shows the friendly message", and that claim turned out to be true
  only on the CSV path. D8 now states the real coverage and points here
  rather than describing behaviour the code does not have.

  Fix: wrap the two unguarded call sites (or `_autodetect_date_format`
  itself) and surface on the map-step error label, samples `[]`, picker
  unchanged -- which is what D8 originally claimed for all three.
  **Layman:** If a spreadsheet file is damaged part-way down, changing the Date column on the import screen can make the app fall over instead of showing a message.
  Kind: fix.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0146, loop 3).
  Resolved (2026-08-12): the guard is one owner, `_refresh_date_ui(detect=)`, not two wrapped call sites — the bullet named D5(b) and D5(c), and the tree had six unguarded sites, because `_update_date_preview` reads `_date_samples` too and runs on every one of them. So `_on_date_format_changed`, `_on_pdf_table_changed` and the batch ask step were open as well. `_select_file` deliberately keeps its own catch: D5(a) must refuse the file, not show the map step over it. The reachable route is the batch (SCAN -> ASK re-shows the map step with a broken body loaded), which is what the regression test drives; the CSV pick cannot reach it. FIBR-0146 D8 amended in the same commit. c3fc050, gate green (1879 passed).

- ✅ [FIBR-0269] **The map step re-reads the whole statement on every date keystroke.**
  `_date_samples` stops COLLECTING at `_MAX_DATE_SAMPLES` (50), but the
  read it collects from does not stop: `read_rows` is
  `list(csv.DictReader(...))`, so the whole file is materialised first.
  And `_date_samples` runs twice per refresh (once in
  `_autodetect_date_format`, once in `_update_date_preview`), on every
  detect, every date-column change, and every keystroke in the Custom
  format field via `_on_date_format_changed`.

  So detection cost is constant in the row count (the 750-strptime
  bound holds) while REFRESH cost is linear in it. FIBR-0146 D8 claimed
  both were constant and concluded "no separate perf test needed"; the
  D8 text is now corrected, and this is the code half.

  Cheapest fix: cache the sampled rows against `self._text` (it only
  changes when a file or PDF table is loaded), or give `read_rows` a
  `limit` so the reader stops early. Neither changes any behaviour.
  Measure before fixing — a 50k-row statement is the case that would
  feel it, and no one has reported slowness.
  **Layman:** On the import screen, typing in the date-format box makes the app re-read the entire file for every character — fine for a small statement, slow for a big one.
  Kind: perf.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0146, loop 2).
  Resolved (2026-08-14): measured first, as the bullet asked. One
  `_date_samples` call costs 0.17 ms at 100 rows, 6.96 ms at 5k, 30.3 ms at
  20k and 81.1 ms at 50k — linear, confirming the read is unbounded while
  the 50-sample collection bound is not. Typing the eight characters of
  `%d/%m/%Y` read the file NINE times (8 keystrokes + the combo change), so
  ~0.7 s of frozen UI on a 50k-row statement and about 60 ms on the
  few-hundred-row one a bank actually issues. Real, but only felt well past
  the size of a real statement — recorded here so the next reader does not
  re-derive it. Took the bullet's first fix: samples cached per column
  against `self._text`, dropped whenever the text is replaced. Identity, not
  equality — every assignment to `self._text` is a fresh object. No
  behaviour change, including on a broken body: nothing is cached when the
  read raises, so the next call raises again. Covered by INV-7 in
  tests/features/import_date_detect/spec.md, which counts reads rather than
  seconds and asserts the counter is wired to the reader the wizard really
  calls, so a passing zero cannot mean "never patched".

- ✅ [FIBR-0270] **The all-rows-failed banner says "Go back" and the wizard has no way back.**
  `_banner_text`'s mapped-source sentence is "None of the rows could be
  imported. Go back and check the column mapping and the Date format
  match your statement." The import wizard has no back control: the
  only `_goto_step(_STEP_PICK)` calls are the initial build and the
  finish/reset, and there is no `_goto_step(_STEP_MAP)` reachable from
  the preview step.

  So the remedy names a screen the user cannot return to. Re-picking
  the file is the actual route, and for a CSV whose profile MATCHED it
  does not even reach the map step — it jumps straight back to the same
  failed preview, because the saved profile is what is wrong.

  Two candidate fixes, not decided: add a Back button on the preview
  step (returns to the map step where one exists), or reword the
  banner to name the action that actually works. The first is better
  for the matched-profile case only if it can also unstick the profile.

  Found while gating FIBR-0146; the spec quotes the shipped string
  correctly, so this is a code/UX item, not a doc one.
  **Layman:** When nothing in a statement could be imported, the app tells you to go back and check the column mapping — but there is no back button to get there.
  Kind: ux.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0146, loop 2).
  Resolved (2026-08-13): took the Back button, not the reword. The
  banner sentence was right and the wizard was wrong, so the control
  is what changed — and leaving D7's strings alone keeps
  `docs/specs/FIBR-0146.md` unamended and its rule-14 gate unarmed
  (FIBR-0272 wants that spec split before it is reviewed again).

  `_back_button` on the preview step, beside Import, shown only when
  `_has_mapping_step` — the same flag FIBR-0253 keyed the banner text
  on, so the advice and the way to follow it cannot disagree. OFX and
  a recognised SB statement still get no Back and still get the other
  sentence.

  The matched-profile half the bullet flagged as hard: `_select_file`
  now calls `_apply_profile_to_combos(matched)` before jumping past
  the map step, so Back lands on the mapping actually in force rather
  than combo defaults. The generic-PDF matched jump already did this;
  the CSV one was the only gap. `_on_preview_back` refreshes the date
  UI with `detect=False` (a stored format is a decision, not a guess)
  and defers that read to the one path that shows the page — which is
  also the cheapest place for it, given FIBR-0269.

  Tests: `tests/features/import_back_step/` (spec.md + 4 tests,
  INV-1..4), red on all four before the fix. INV-4's fixture puts the
  date column at header[1] on purpose, so a form left at its defaults
  fails instead of passing by coincidence. Gate green: 1885 passed,
  3 skipped.

- ✅ [FIBR-0271] **A bad amount cell showed the user `[&lt;class 'decimal.ConversionSyntax'&gt;]`.**
  FIBR-0146 INV-3 is "no raw parser internals reach the UI", and D3
  said the amount branch already had human messages so only the date
  branch needed re-wording. False. `CsvImporter` builds the amount with
  `Decimal(cell)` BEFORE `parse_transaction`, so a non-numeric cell
  raises `decimal.InvalidOperation`, whose `str()` is the literal
  `[&lt;class 'decimal.ConversionSyntax'&gt;]` — appended verbatim as the
  `RowError` reason and rendered in the preview's Status column.

  `parse_transaction`'s friendly "amount is not a valid number" is
  unreachable from CSV: it receives an already-built `Decimal` and takes
  its `isinstance(raw_amount, Decimal)` short-circuit.

  Reproduced before fixing: a one-row CSV with `not-a-number` in the
  amount column returned exactly that string.

  The test that should have caught it asserted only that the reason was
  non-empty and did not mention dates — which the gibberish satisfies.
  It now asserts the message.

  Fixed by a shared `CsvImporter._to_decimal` used by both amount
  styles, mirroring the date branch: `could not read the amount "&lt;raw&gt;"`,
  and `the amount cell is empty` for a blank cell.
  **Layman:** If an amount on a statement could not be read, the import screen showed a line of programmer gibberish instead of saying which value it could not read.
  Kind: fix.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0146, loop 3).

- ✅ [FIBR-0272] **FIBR-0146 keeps yielding fresh-region findings; consider splitting before the next gate.**
  Three loops, 11 verified findings, every one fixed, tail empty. The
  pattern is the point: loop 12 found three defects in regions loop 11
  never reached, and loop 13 found two more in regions neither had. Only
  three of the eleven were a previous loop's own collateral.

  That is the same shape FIBR-0267 recorded for FIBR-0085 — a cold read
  reaching fresh parts each pass rather than a document that regresses —
  and the cause is size. FIBR-0146 is 700+ lines against siblings of
  ~400-650.

  Not urgent: the spec is implemented, shipped and now accurate as far
  as three cold reads could reach. But the next amendment to it re-arms
  the rule-14 gate, and that gate will keep costing a loop per unread
  region until the document is split.

  Candidate split: the detector contract (D2, INV-2, the 15-format table)
  is self-contained and is the half other specs cite; the wizard wiring
  (D4-D8, the map-step behaviour) is the half that keeps drifting against
  the code.
  **Layman:** The date-detection design document is long enough that each review pass reads different parts of it, so it should probably be split before it is reviewed again.
  Kind: doc-fix.
  Source: in-session-2026-08-12 (review-contract gate on FIBR-0146, loop 3, at the run cap).
  Resolved (2026-08-14): split, but NOT at the seam this bullet proposed.
  `spec-format.md` §5.4 turned out to govern it — a spec that outruns the
  review's cap is larger than the review's design point, and the remedy is
  to split along §3.6's by-concern seams rather than loop again. Measuring
  the two candidate halves inverted the choice: the detector half is only
  ~140 lines, so extracting it would have left FIBR-0146 near 600 and
  barely moved the gate cost. The wizard half is ~300 lines AND is the half
  this bullet itself names as the one that keeps drifting, so that is what
  moved. 746 → 422 + 413 lines, both inside the ~400-650 range of sibling
  specs. The wizard half is now
  docs/specs/FIBR-0146-wizard-date-step.md (D4-D8, INV-1/4/5, the
  ui/import_wizard.py symbols, the wizard test plan); the parent keeps the
  detector and importer contract, the shared Context and every frozen
  record. Both files carry the SAME id, following the FIBR-0192 /
  FIBR-0192-qt-facts precedent — that is what made it cheap, since all ~66
  existing `FIBR-0146 D<n>` citations in code, tests and the ROADMAP
  resolve unchanged and none was touched. Ids are permanent, so the
  companion's decisions start at D4 and its invariants skip INV-2/3/6.
  Every moved line is verbatim: no invariant re-cut, no decision reworded,
  no renumbering. A script asserted all 27 section boundaries before
  writing and then re-checked that no substantive line of the 746 was
  missing from both halves; doc_integrity clean. Recorded as a `13-split`
  loop-log row with no reviewer dispatched, following FIBR-0192's precedent
  that a split is not a review loop; rule 14 was checked and no line
  changes for a conformer. FIBR-0267 (the same diagnosis on FIBR-0085, 1357
  lines) is still open and now has a worked precedent to copy.

- ✅ [FIBR-0273] **A year-less Custom date format silently dates every row 1900, and Python 3.15 changes what it does.**
  `_validate_mapping` rejects an EMPTY date format (FIBR-0146 INV-6, the
  1900-01-01 trap) but not a year-LESS one. `%d/%m` passes validation, and
  `strptime("20/07", "%d/%m")` returns 1900-07-20 — so a whole statement
  imports into 1900 with the preview showing "Dates read as: 1900-07-20"
  and no other complaint. That is the same trap the empty format was
  closed for, reached by a different route.

  Surfaced 2026-08-14 by the FIBR-0269 read-count test, which types the
  prefixes of `%d/%m/%Y` into the Custom field: CPython emits
  `DeprecationWarning: Parsing dates involving a day of month without a
  year specified is ambiguious` from `_strptime.pattern()` — at format
  COMPILE time, so it fires whether or not a sample then parses. The
  message says 3.15 "will either always raise an exception or use a
  different default year (TBD)". So today's failure is a silent wrong
  year; tomorrow's is a `ValueError` out of `_update_date_preview` and
  `CsvImporter.parse` on a format that validated.

  Both halves want the same fix: reject a date format that carries no year
  token at `_validate_mapping`, next to the empty check, with a message in
  the same plain register ("this format has no year in it"). That closes
  the 1900 import and makes the 3.15 change a no-op for us rather than a
  new crash. Check `%y` as well as `%Y`, and the named-month formats.

  Note the four DeprecationWarnings the gate now prints against
  `test_FIBR0269_map_step_reads_the_statement_once_per_load` are this, not
  a defect in that test — they are the warning doing its job.
  **Layman:** If you type a date format with no year in it (like "%d/%m"), every imported transaction is filed in the year 1900 with no warning — and a future Python may change that to something else again.
  Kind: fix.
  Source: in-session-2026-08-14 (surfaced by the FIBR-0269 test run).
  Resolved (2026-08-14): `_validate_mapping` now rejects a date format with
  no year directive — "this date format has no year in it — add %Y (or %y),
  or every row will be dated 1900" — next to the existing empty-format
  check, as the bullet proposed. Gate green (1900 passed).

  Two details the bullet did not anticipate, both test-locked. The check
  scans `%`-directives instead of substring-matching, because `"%%Y"` is a
  literal percent followed by a literal `Y` and is genuinely year-less,
  where `"%Y" in fmt` would accept it. And the year set is deliberately
  GENEROUS — `%y`, `%G`, `%x` and `%c` all read a year, not just `%Y` —
  because the asymmetry runs the other way from the bug: a format wrongly
  called year-less is REFUSED, which silently removes a layout the
  "Custom…" escape hatch exists to preserve (FIBR-0146 INV-4). Seven
  year-bearing formats are asserted still accepted for exactly that reason.

  Covered by INV-8 in tests/features/import_date_detect/spec.md: six
  refusal cases (all proven red first), seven acceptance cases, and a
  precondition test proving `strptime("20/07", "%d/%m")` really does return
  1900-07-20 rather than assuming it.

  The live preview needed no change and deliberately got none: showing
  "Dates read as: 1900-07-20" is INV-1 working — the user sees the wrong
  year before any write — and Next now refuses. Under Python 3.15 the
  preview degrades to its existing "couldn't be read" fallback rather than
  crashing, since `_update_date_preview` already catches ValueError.

  Recorded as an after-the-fact amendment in
  docs/specs/FIBR-0146-wizard-date-step.md D4 — the first amendment to land
  in the split halves, and it landed in a 400-line document instead of a
  746-line one (FIBR-0272).

- 📋 [FIBR-0274] **The stored-password auto-try consults only the pick-step account, so a re-targeted statement re-prompts next month.**
  `_begin_decrypt` looks the remembered password up with
  `get_pdf_password(self._target_account_id())` — necessarily the PICK-STEP
  account, because the destination is not known until the PDF has been
  decrypted and parsed. FIBR-0249 moved the stored password onto the
  account the rows actually land on, which is where it belongs. So when
  those two differ, next month's auto-try looks in the wrong place and the
  user is prompted again.

  This gap is not new, but FIBR-0249 made it VISIBLE. Before it, the carry
  COPIED, so the pick-step account also held a copy and the auto-try
  happened to succeed — the convenience was a side-effect of the
  wrong-account credential FIBR-0249 removed. Removing the defect removed
  the accident; the lookup was always the real problem.

  Not fixed with FIBR-0249 deliberately: the obvious remedy — fall back to
  trying every stored PDF password when the pick-step account has none —
  weakens the guarantee FIBR-0009 INV-4 states structurally in
  `_begin_decrypt`'s docstring ("the stored password is attempted at most
  once", which holds today because there is exactly one candidate and one
  call site). Every password involved is the same user's, so this is a
  usability and invariant question, not a privilege one — but it wants a
  decision and a test, not a quiet widening.

  Options, cheapest first: (a) try each distinct stored password once, in a
  fixed order, and restate INV-4 as "each stored password at most once per
  import"; (b) key remembered statement passwords by something stable about
  the FILE (issuing bank, or the detected account number) rather than by
  account; (c) accept the re-prompt and say so in the UI. (b) is the most
  correct and the most work.
  **Layman:** After the app learns that a locked statement belongs to a different account than the one first selected, it still looks for the remembered password under the first one next month — so you get asked for the password again.
  Kind: enhancement.
  Source: in-session-2026-08-14 (found while fixing FIBR-0249).

- ✅ [FIBR-0276] **The documented .corpus-numbers setup types real account numbers onto a command line.**
  CLAUDE.md § Build and test prescribes:

  printf '%s\n' '1234 567 890 1' '9876543210' &gt; .corpus-numbers

  Two lines below it says "**Never print the values, redirect them to a
  tracked file, or paste them into a commit message, spec or ROADMAP
  entry**". A shell command line is none of those literally, so the
  prohibition does not cover it — but `~/.bash_history` is a plaintext
  file in `$HOME` that survives reboots, is not gitignored (it is not in
  the repo at all), and is exactly the kind of place nobody thinks to
  check. If an agent runs the command, the values also land in that
  session's transcript.

  So the prescribed setup leaks the values into the one channel the
  surrounding paragraph forgot to name, while reading as the safe route
  because it is the documented one.

  Fix: prescribe an editor instead, which touches no history at all —

  kate .corpus-numbers        # or nano / gedit / vim

  and state plainly that this is a step the USER performs, never an
  agent: the values are the secret the guard exists to protect, and a
  transcript is a durable copy.

  Worth adding at the same time, because it is the question that follows:
  an agent cannot create this file at all. Inventing plausible numbers
  makes the guard PASS while searching for numbers that exist nowhere —
  strictly worse than the current skip, because a skip is visibly absent
  coverage and a fake pass is not. That is the FIBR-0248 failure wearing
  a green tick.

  Verified 2026-08-18: with numbers supplied the file runs 13 tests; with
  none it runs 12 and skips 1. The mechanism is fine — only the
  documented way of feeding it is not.

  Filed rather than fixed in place because amending CLAUDE.md's setup
  command changes what a conformer types, so it trips the rule-14 gate on
  its own (3 cold lanes). Not worth that mid-session; it is a two-line
  edit for whoever next opens that file for another reason.
  **Layman:** The instructions for saving your real account numbers locally tell you to type them into the terminal, where they get saved into your command history.
  Kind: doc-fix.
  Source: in-session-2026-08-18 (raised by a review-contract lane on CLAUDE.md, then by the user asking what the file is).

  Resolved (2026-08-18): fixed. The bullet deferred this because amending the
  setup command changes what a conformer types and so trips rule 14's gate on
  its own (3 cold lanes) — "not worth that mid-session". That gate then ran on
  CLAUDE.md for FIBR-0244, three cold lanes, and a loop-3 lane re-raised this
  exact recipe. The deferral's condition was satisfied, so it was fixed inside
  the gate that was already paid for rather than deferred a second time.
  CLAUDE.md now prescribes an editor, states that the guard normalises so
  spacing does not matter, says it is a step the user performs and an agent
  cannot, and adds "type them onto a shell command line" to the never-list.

- ✅ [FIBR-0277] **The dialog-lifecycle guard cannot see a UI module nobody added to its `_FILES` tuple.**
  `tests/features/dialog_lifecycle/test_dialog_lifecycle.py` iterates a
  hand-maintained `_FILES` tuple. A UI module created and never added to it
  is not a failing case but an absent one: the test passes while covering
  nothing, and no run reports the omission.

  Found while fixing FIBR-0085 INV-6, whose *Breaks when* clause named
  exactly this omission — a clause its own named test cannot observe, so it
  was unfalsifiable as written. The spec now states the gap rather than
  implying the guard closes it.

  Fix: assert `_FILES` covers every `*.py` in `src/finbreak/ui/` bar a named
  allowlist, so adding a UI module without listing it turns the guard red
  instead of silently shrinking its coverage. The allowlist is what keeps it
  honest — an unexplained exclusion has to be written down.
  **Layman:** A safety check that scans the app's screens for a known freeze-the-window mistake only looks at a hand-written list of files, so a new screen nobody remembered to add is silently not checked at all.
  Kind: test.
  Source: in-session-2026-08-18 (found while splitting FIBR-0085 for FIBR-0267).

  Resolved (2026-08-18): fixed as filed. `test_dialog_lifecycle.py` gains INV-7
  and a `_NOT_CONTENT_WIDGETS` mapping of 38 written reasons; together with the
  five `_FILES` members it must account for every one of the 43 `ui/*.py`
  modules, so a new screen in neither list turns the guard red. `_FILES`,
  `_EXEC` and the INV-1 / INV-4 tests are unchanged — this is additive, and
  INV-1's subject is still the converted content widgets.

  Proven red by construction, not by a live defect: a scratch
  `src/finbreak/ui/_fibr0277_probe.py` made INV-7 fail naming that file, and it
  was deleted immediately after.

  What the allowlist surfaced, now written down instead of invisible:
  `main_window.py:1147` carries a genuinely blocking `StartOverDialog.exec()`.
  It is out of the FIBR-0065 crash class because `_on_start_over` is reachable
  only from `UnlockDialog.start_over_requested` — the vault is locked, so
  auto-lock cannot fire mid-`exec()`. Verified against the call graph (the three
  `_show_unlock` call sites) rather than assumed. `transactions.py:384` is a
  `QMenu` context menu, the same shape as the existing `home.py` exemption.

- ✅ [FIBR-0278] **Nothing binds CLAUDE.md's prose-check suite list to the tree, and it silently went stale.**
  § Doc-only pushes prescribes an ENUMERATED list of test suites that read
  tracked prose. On 2026-08-18 that list was two suites and the real answer
  was four: `tests/features/release_integrity/` reads
  `docs/security-model.md`, and `tests/features/flatpak_packaging/` requires
  `packaging/flatpak/README.md` to exist. All three review lanes found it
  independently, which is what a hand-maintained list with no binding looks
  like from outside.

  The same shape as FIBR-0277: a guard whose coverage is a list nobody
  checks. A new doc-scraping suite lands and the section does not notice, so
  a doc-only push skips the very check that would have caught it.

  Fix: a test asserting that the suite list CLAUDE.md prescribes matches the
  suites that actually read a tracked doc — parse the fenced `pytest` command
  out of the section, derive the real set, and fail on a difference. The
  derivation cannot be a path grep alone: `account_detect` walks
  `git ls-files` and names no file, so it must be an explicit member of
  whatever the test compares against.
  **Layman:** The instructions list which quick checks to run before pushing a documentation change, and nothing keeps that list up to date — it was already missing half the checks.
  Kind: test.
  Source: in-session-2026-08-18 (review-contract loop 1 on CLAUDE.md, all 3 lanes).

  Resolved (2026-08-18): fixed, but NOT as filed. "Derive the real set" cannot
  be built: CLAUDE.md's own § Doc-only pushes says "No grep re-derives this
  list, so do not try to", and measuring it confirms why — a grep for `.md` /
  `docs/` / `git ls-files` over `tests/features/*/*.py` matches 44 of the 50
  suites, so a derived set would be noise. Built instead as the same shape
  FIBR-0277 takes, which the bullet already predicted: classify everything and
  fail on the unclassified.

  New suite `tests/features/prose_checks/`, two invariants. INV-1 parses the
  fenced `pytest` command out of § Doc-only pushes and asserts it equals a
  `_READS_PROSE` ledger of five; INV-2 asserts every directory under
  `tests/features/` is in that ledger or in `_NO_PROSE` (46), so a new suite in
  neither goes red and somebody has to decide. It is a member of its own list —
  it reads CLAUDE.md — so editing the fenced command without the ledger, or the
  reverse, is what turns it red.

  Proven red at `13400f8`, where the fenced command still named two suites: the
  run failed naming `flatpak_packaging`, `release_integrity` and `prose_checks`
  as present in the ledger and missing from CLAUDE.md.

  CLAUDE.md updated with it: the fenced command gains the new suite, "four
  suites" becomes five, and the timing line is re-measured (1.01s / 63 tests for
  the old two-suite list against 1.36s / 93 for these five, both warm). The
  earlier "maintained by hand and nothing binds it" paragraph now points at this
  guard.

- ✅ [FIBR-0279] **commits.md calls `--no-verify` an anti-pattern; CLAUDE.md now makes it the normal doc-only route.**
  `docs/standards/commits.md` § 132 says `--no-verify` "bypasses project
  safety nets" and § 277 lists "Skipping hooks (`--no-verify`) without
  explicit authorisation" as a ❌. The 2026-08-18 doc-only push rule makes
  `git push --no-verify` the prescribed route for every documentation
  commit, after running the prose checks by hand.

  These are reconcilable — the CLAUDE.md rule IS the explicit authorisation
  — but neither document points at the other, so a session reading only the
  standard sees the project's normal doc-push route listed as a defect.

  Filed rather than fixed in passing: adding the exception changes what a
  conformer does, so it trips commits.md's own rule-14 gate and wants three
  cold lanes rather than a drive-by edit.
  **Layman:** Two of the project's own rule documents disagree about whether a shortcut used on every documentation change is allowed.
  Kind: doc-fix.
  Source: in-session-2026-08-18 (review-contract loop 1 on CLAUDE.md, blast-radius sweep).
  Resolved (2026-08-19): `commits.md` § 2.3 now names the standing
  authorisation and defers the enumeration to `CLAUDE.md`; § 7's bullet
  points at § 2.3; `CLAUDE.md` § Doc-only pushes points back. Gated with
  `review-contract --genre standard`, 3 loops (the cap), 9 cold lanes,
  19 verified findings all fixed, 2 dismissed. Loop-log rows 1-3 are
  inline in the document.

  The gate found far more than the trigger: § 6 claimed CI attaches
  release assets on a tag push (no workflow here has a `tags:` trigger --
  the v0.1.20 zero-asset failure exactly), § 5 routed the bump to the
  deleted `/bump` skill and a drift script that does not exist, § 4.2
  prescribed the `--tags` the global rules forbid by name, and § 6's
  release-notes block piped a command that exists nowhere in the tree.

  Cap was violent: 3 of loop 3's 5 findings landed on text the run itself
  wrote. Deferred tail filed as FIBR-0289, FIBR-0290, FIBR-0291;
  collateral in neighbouring documents as FIBR-0286, FIBR-0287,
  FIBR-0288.

- ✅ [FIBR-0280] **Doc-only pushes run the prose checks unconditionally, and CLAUDE.md was gated for it.**
  User directive 2026-08-18, settling the caveat raised 2026-08-17 and left
  UNRESOLVED in § Doc-only pushes. The old rule asked whether a commit added
  "digits or key-shaped strings" and demanded the two prose-reading checks
  only then; measured, they cost about two seconds against ~1m45s for the full
  gate, so the branch traded a silent unrecoverable failure against two
  seconds — and the judgement fell to whoever had just written the prose.

  Resolved (2026-08-18): every doc-only push now runs the four prose-reading
  suites plus `gitleaks`, then pushes with `--no-verify`. The full gate is
  still skipped; a code change still never skips. The `docs/specs/FIBR-0001.md`
  carve-out is gone because the suite enforcing it now runs every time, and the
  test's unit is pinned to `git diff --name-only @{u}..HEAD` rather than the
  last commit.

  Gated under rule 14: `review-contract --genre standard`, 3 cold lanes ×
  3 loops, cap reached. 19 verified findings, all fixed, 1 dismissed. Loop log
  in `docs/reviews/CLAUDE-md-review-log.md`. The gate also retired the
  `<ID>-complete` phase-tag rule (never enforceable — `cut-release` Phase 5 and
  `/close-phase` Step 6 both run `--follow-tags` on a public repo, which is how
  all 54 tags reached the remote) and settled `--max-loops 7` to specs and
  plans only. Both were user decisions on stop conditions the gate surfaced.

  **Commit-ID note, recorded rather than rewritten:** the six commits
  `13400f8`, `dc64b34`, `2d30ec3`, `1c510d8`, `eb6cda9` and this one's
  predecessors carry `FIBR-0244:` subjects. FIBR-0244 is the ✅ account-number
  redaction item and is NOT this work — it was reached for because it is the
  leak this section's guard exists to catch. The commits were already pushed
  to a public repo, so they are left as written rather than history-rewritten;
  this bullet is the true owner. A ledger audit finding those subjects should
  come here.
  **Layman:** Pushing a documentation-only change now always runs a two-second safety check instead of asking you to judge whether the text looked risky.
  Kind: doc.
  Source: user-directive-2026-08-18.

- ✅ [FIBR-0281] **CLAUDE.md still points sessions at hand-editing ROADMAP.md, and the roadmap DB is now the write path.**
  User decision 2026-08-18: this project uses the roadmap DB (`roadmap_query` /
  `roadmap_log`), not hand edits to ROADMAP.md. It enforces the format, is much
  cheaper to query than reading a 616 KB file, and updates items in place.
  Clarified by the user the same day: the DB is the SOURCE OF TRUTH and
  ROADMAP.md is GENERATED from it, and the generated file is what gets committed
  and pushed. So the full-file rewrite on every write is the design working, not
  a fault.

  What blocked that until today, and how it was cleared: every `roadmap_log` op
  refused `render_gate_unmet`, so sessions hand-edited instead. That refusal is
  gone, but the store had drifted behind the file — it still reported FIBR-0277
  and FIBR-0278 as planned, with their pre-resolution bodies, after both were
  flipped and committed. `roadmap_migrate` is the ingest, not a workaround:
  a dry run reported 2 updated / 272 unchanged / 0 inserted / 0 orphaned, the
  real run matched, and ROADMAP.md was byte-identical afterwards because the
  verb only reads the file into the store.

  Fix: amend CLAUDE.md § Where state lives so it prescribes the DB, and record
  that a session must confirm the store is current before writing — a targeted
  `roadmap_query` on an id edited this session is the check. Note the trap that
  made this hard to see: `items_rendered` matching the file's bullet count reads
  as an all-clear and is not, because it counts items rather than their contents,
  so a stale-bodied store passes it exactly as a fresh one does.
  **Layman:** The project's instructions tell Claude to edit the roadmap file by hand; it should be using the roadmap database instead, which enforces the format, is far cheaper to search, and can update items in place.
  Kind: doc.
  Source: user-decision-2026-08-18.
  Progress (2026-08-18): the store is now in sync and this file is generated from it. Two renderer defects were found and one is fixed at source: a bullet whose bold headline wrapped across lines rendered its continuation at column 0, which markdown reads as a new list item — 18 such headlines were un-wrapped before the first render, and the fix is durable because the store now holds each headline on one line. The second is open and belongs to the MCP: there is no way to remove an item from the store, and re-ingesting a file without it marks it orphaned WITHOUT dropping it, so it is re-injected on the next render — an accidental append is permanent and self-resurrecting, and clearing one needs a direct DELETE on the shared roadmap.sqlite. Both are logged in the Ants MCP feedback file. Still to do here: amend § Where state lives so it names the DB as the source of truth rather than this file, and state the freshness check a session owes before writing.
  Resolved (2026-08-19): CLAUDE.md § Where state lives item 2 now names the roadmap DB as the source of truth, with ROADMAP.md as generated output that is never hand-edited, and § Resumption flow and `.claude/workflow.md` § 1 reworded to match. Gated with `review-contract --genre standard`, 3 loops (the cap for a standard here), 7 cold lanes, 15 verified findings all fixed, 4 dismissed on verification.

  The freshness check this item asked for is NOT the one it proposed. `roadmap_migrate`'s dry-run counters do not measure staleness: measured on a tree where every ROADMAP.md change had come through `roadmap_log`, a dry run still reported 10 items updated (`body`, `layman`, `source`, `extras`), because the render → parse round trip is not lossless. That is a property of the round trip, so it applies to every run — and `updated_items[]` is the verb's plan to write those re-parsed bodies over correct ones in a store shared by every project on this machine. The rule written instead: `roadmap_query` on the id you are about to touch, read the body back, read it back again after every flip; plus a write `dry_run` for the file-side half, which resolves the locator and echoes `from_status` but returns no body. Both the finding and a clarification request are logged in the Ants MCP feedback file.

  Two things the gate corrected that would otherwise have shipped: a hazard attached to the wrong condition (a non-dry migrate called destructive on "a clean tree", when the sanctioned external-merge case clobbers the same items), and a rule costing every session a needless call (that `status:"active"` cannot yield `Kind` — the envelope returns `kind` as a field even with `bodies_omitted: true`).

  Filed, not fixed: FIBR-0285.

- ✅ [FIBR-0285] **The audit allowlist still keys its entries to `/code-quality-review`, a skill that no longer exists.**
  `review-code` replaced `/code-quality-review` on 2026-08-18. CLAUDE.md item 6
  was corrected in this gate, which exposed the copies:

  - `docs/audit-allowlist.md` — 7 occurrences, and one of them is the ENTRY KEY
    FORMAT: "Write new entries with `code-quality-review:R-N`" (line 22), with
    a worked example at line 76. Existing entries already use that prefix, so
    renaming it is a migration of the file's own data, not a word swap.
  - `.claude/workflow.md` line 61 — step 6 of the nine-step loop, "Run
    `/code-quality-review` — in parallel with 5". That list is a COPY; the
    canonical nine steps live in `~/.claude/skills/app-workflow/SKILL.md`, so
    editing it here alone makes the copy diverge from its source.

  Filed rather than fixed in the gate that found it: neither is a sentence.
  The allowlist half is a policy choice about existing entry keys, and the
  workflow.md half needs the app-workflow skill changed first or it diverges.

  Why it matters: the allowlist is this project's closed-loop memory for
  confirmed false positives, and CLAUDE.md item 6 says to read it before
  invoking `review-code`. A session that does read it finds entries keyed to a
  skill it is not running.
  Resolved (2026-08-19, commit 032d273): both halves fixed, and both of the reasons this was filed rather than fixed had resolved. The entry-key format was not an open policy choice -- the file settled it on 2026-08-05 for the /indie-review rename (prose takes the current name; existing source tokens keep their original provenance) and this rename simply follows that precedent, so the naming note is now generalised to all three renames. Nothing machine-reads the key. The .claude/workflow.md half no longer diverges from its source: ~/.claude/skills/app-workflow/SKILL.md already says check-code / review-code, so the edit makes the copy match. Also corrected /audit -> check-code in the same prose, same defect class. Left alone deliberately: the indie-review:R-N and code-quality-review:R-7 source tokens on existing entries, and every /audit in .claude/workflow.md section 3, which is append-only session history -- both are dated records of what really ran under the old name.
  **Layman:** Two project documents still name a review tool that was renamed, including the format of the allowlist's own entries — so the memory that stops repeat false positives is filed under a name nothing will look up.
  Kind: doc-fix.
  Source: in-session-2026-08-19 (review-contract loop 2 on CLAUDE.md, blast-radius sweep).

- ✅ [FIBR-0286] **`coding.md` and `testing.md` carry the stale peer count and the frozen model literal `commits.md` just shed.**
  `docs/standards/coding.md:5` and `docs/standards/testing.md:5` both say
  this standard "Pairs with the other **three** standards in this folder"
  when the folder holds six shareable standards plus a sub-spec and the
  index. `docs/standards/testing.md:254` freezes
  `Co-Authored-By: Claude Opus 4.8 (1M context)` in an example; the last 30
  commits all carry `Claude Opus 5`, so a conformer copying the literal
  mis-attributes the commit.

  `commits.md`'s own gate fixed both in that file on 2026-08-19 by deleting
  the count and replacing the frozen literal with a pointer. Not carried
  into the neighbours in passing: each is a contract document with its own
  rule-14 gate ahead of it, which is the same call `documentation.md`'s
  loop 1 made when it first surfaced the peer-count drift.
  Resolved (2026-08-19, commit 473dd78). Both headers now enumerate all five
  siblings and name no count, matching `naming.md`, `dependencies.md` and
  `documentation.md`. `testing.md` § 8's frozen `Claude Opus 4.8` literal is
  replaced by the placeholder-plus-pointer form `commits.md` § 1.5 owns.

  Gated: no. The bullet said both files owed their own rule-14 gate; applying
  that rule's own test says otherwise. A corrected count, a completed link
  list and a stale example literal replaced by the pointer it should have been
  change no line a conformer writes — the trailer they produce is the one
  § 1.5 already prescribed. Recorded in the commit body per rule 14's No
  branch, which also says not to gate in the grey zone.
  **Layman:** Two rule documents still say there are three sibling standards when there are six, and both show an out-of-date AI name that gets copied into commits.
  Kind: doc-fix.
  Source: in-session-2026-08-19 (review-contract loop 1 on commits.md, blast-radius sweep).

- ✅ [FIBR-0287] **Four live references under `packaging/` still route the version bump to the deleted `/bump` skill.**
  `cut-release` replaced both `/release` and `/bump` on 2026-08-13, and
  nothing named `/bump` can be invoked. Still naming it:
  `packaging/flatpak/README.md:134`, `packaging/obs/README.md:122`,
  `packaging/obs/io.github.milnet01.finbreak.metainfo.xml:4` and
  `packaging/obs/debian/rules:5` — each claiming the `/bump` recipe keeps
  the metainfo `<release>` block or the debian version in lockstep with
  `__version__`.

  `commits.md` § 5 carried the same dead route and was fixed on 2026-08-19
  by its own gate. These four were left rather than swept in: they are
  packaging docs and source comments with their own subject, and the
  correct replacement text differs per file (`cut-release --bump-only` for
  the standalone bump, `cut-release <X.Y.Z>` for the full path).

  The underlying lockstep behaviour is unchanged — `.claude/bump.json` is
  still the recipe; only the skill that reads it was renamed.
  Resolved (2026-08-19, commit aa76a3d): every `/bump` reference now names
  `cut-release`, or `.claude/bump.json` where the sentence is about the
  recipe rather than the skill.

  Scope was wider than the four filed here. A tree-wide grep found ten more
  live sites — `.claude/bump.json` itself (×2, one of them pointing at the
  deleted `~/.claude/skills/bump` directory), `docs/specs/FIBR-0155.md` (×3),
  `docs/specs/FIBR-0159.md` (×3), `tests/features/flatpak_packaging/spec.md`
  and its test comment. All fourteen are fixed, so the class is closed rather
  than half-renamed; no follow-up item is owed.

  Left alone deliberately: `docs/standards/commits.md` loop-log row 1, a dated
  record of what that gate found, which must not be back-dated.

  Full gate run (code files changed, so no doc-only route): 1916 passed,
  2 skipped, all stages green.
  **Layman:** Four packaging files tell you to use a release tool that no longer exists.
  Kind: doc-fix.
  Source: in-session-2026-08-19 (review-contract loop 1 on commits.md, blast-radius sweep).

- ✅ [FIBR-0288] **`roadmap-format.md` § 3.5.1 describes `.roadmap-counter` as the ID allocator; it is a gitignored cache three IDs behind.**
  `docs/standards/roadmap-format.md` § 3.5.1 says "The high-water mark
  lives in `.roadmap-counter` at the project root", that "New IDs
  increment this counter atomically", and that "The counter file is
  checked into git so the next session starts from the right number".

  Two of those are false here. The file is **gitignored** — commit
  `0b5c995` (2026-07-14) put it there deliberately, "re-derived from
  ROADMAP.md when absent" — so it is not checked in. And it is not what
  allocates: `roadmap_log` allocates from the roadmap DB and reconciles
  the counter afterwards. Measured 2026-08-19 it read `285` while `FIBR-0286` and
  `FIBR-0287` were already on the roadmap, both allocated minutes earlier.

  A session following § 3.5.1 to back-fill a hotfix ID reads `285`, writes
  `Refs: FIBR-0286`, and names an ID already belonging to something else —
  permanently, since IDs are append-only and a pushed commit cannot be
  rewritten.

  Found by `commits.md`'s own gate: its loop-2 fix cited § 3.5.1 as the
  allocation route and the claim failed when executed. `commits.md` now
  routes allocation to the DB and warns off the counter by name.
  `roadmap-format.md` is a contract document with its own rule-14 gate, so
  the correction was not carried across in passing.
  Blast-radius sweep (same session): `docs/standards/documentation.md:179`
  carries the same claim in one line — it names `.roadmap-counter` as
  where stable IDs come from. Fix both, or fix `roadmap-format.md` and
  leave a pointer there.
  Resolved (2026-08-19, commits 7b2c180, d779f28, ce2d6b1, 0528ac5).

  § 3.5.1 now says what is true: `roadmap_log` allocates from the store,
  `.roadmap-counter` is a gitignored cache that lags (measured at 288 while
  FIBR-0291 existed), and the bash recipe is scoped to projects with no store
  behind `ROADMAP.md`. `documentation.md`'s one-line copy points here instead
  of restating it.

  Gated: `review-contract --genre standard --max-loops 3`, 9 cold lanes over
  3 loops. 26 verified findings, 26 fixed, 1 dismissed. Loop log is inline at
  the end of the document.

  **Reached the cap, and it was a violent one** — all 8 of loop 3's findings
  trace to text this run wrote, so the run was repairing its own repairs and
  nothing suggested a fourth loop would stop. That is a fact about the
  document, and it is filed as FIBR-0293 rather than papered over: the
  standard describes a hand-maintained roadmap, this project's is
  store-backed, and the run kept finding another place the two-branch
  carve-out had not reached.

  Worth knowing beyond the ID question: the machine-wide standard numbers
  § 3.9 *Archive rotation* while this copy's § 3.9 is the anti-patterns, and
  `cut-release` cites "§ 3.9" three times for rotation — so at a minor bump
  those citations land on the wrong section here. Recorded in the header.
  **Layman:** A rule document says IDs come from a small counter file, but that file is out of date and is not what actually issues them.
  Kind: doc-fix.
  Source: in-session-2026-08-19 (review-contract loop 2 on commits.md, 4a step 3).

- ✅ [FIBR-0289] **`ROADMAP.md`'s "Current version" header reads 0.1.7 on a tree past 0.1.21, and nothing bumps it.**
  `ROADMAP.md:3` reads "**Current version:** 0.1.7 (released 2026-07-12)".
  The tree is past **0.1.21**. This is a public repo, so the stale line is
  visible to anyone reading the roadmap.

  It is not a hand-edit that got missed — nothing bumps it by design.
  `ROADMAP.md` is rendered from the roadmap DB, and it does not appear in
  `.claude/bump.json`'s `files[]` or its `post_check` drift gate, so no
  release step touches it. Hand-editing the file is explicitly forbidden
  (the next render reverts it), which means the fix has to be either a
  render-side change or removing the line.

  Removing it is the cheaper answer and the one this session leans to: the
  header already links to `CHANGELOG.md`, which is bumped by the recipe
  and always current, so the roadmap does not need to carry a second copy
  of the version at all.

  Found by `commits.md`'s gate: two lanes opened `bump.json` to check
  whether § 5 was right to list `ROADMAP.md` as version-bearing, found it
  absent, and noticed the header was stale as the proof.
  Progress (2026-08-19): diagnosed, and BLOCKED on tooling rather than on a
  decision. Still 📋.

  Located: the header is `section.intro` on the project's level-0 root section
  (`roadmap.sqlite`, project 10, section 290, slug ''). It is stored, not
  derived — which is why no release step bumps it and why a hand-edit to
  `ROADMAP.md` is reverted by the next render.

  Checked before choosing the fix: no standard requires the line.
  `documentation.md` § 2.1 item 2 mandates a `Current version:` line in
  **README.md** only, and README carries it correctly at 0.1.21, bumped
  mechanically and drift-gated by `.claude/bump.json` + `release-linux.sh`.
  `roadmap-format.md` says nothing about it. So deleting it is sound.

  Both routes to actually delete it are closed:

  - No `roadmap_log` op writes `intro`. `create_section` takes `intro_body`
    only when creating a NEW heading; there is no amend-intro form.
  - Writing `roadmap.sqlite` by hand was refused by the permission
    classifier — correctly, it is a machine-global store shared by every
    project on this machine.
  - `roadmap_migrate` is the sanctioned re-ingest route for a hand-edited
    file, but CLAUDE.md § Where state lives forbids it here on measured
    grounds: the render → parse round trip is lossy and a dry run on a clean
    tree plans ~10 item-body rewrites. Risking ten bodies to fix one
    paragraph is the wrong trade.

  Filed upstream as an Ants MCP finding (2026-08-19,
  `finbreak_Ants_MCP_Feedback.md`): add `op:"amend_intro"` taking an existing
  section — the empty slug for the root preamble — with `amend_body`'s
  unique-match, `dry_run` and read-back guards.

  Unblocks on either of: that verb shipping, or the user authorising a single
  targeted `UPDATE section SET intro=…` against the one row (backup first).
  Nothing else in this item is open — the replacement text is decided.
  Resolved (2026-08-19, user authorised the store write). The version line is
  gone; the header now points at `CHANGELOG.md` for the current version and
  says in one italic line why no copy is kept here, so nobody re-adds it.

  How, since no verb writes a section intro: a single targeted
  `UPDATE section SET intro=… WHERE section_id=290 AND project_id=10` against
  `~/.local/share/ants-terminal/roadmap.sqlite`, after a full
  `sqlite3.backup()` copy to the session scratchpad. The match was asserted
  unique before the write and the write reported exactly 1 row changed.

  Verified by forcing a re-render rather than by reading the store back: an
  idempotent flip re-rendered all 285 items, and `git diff ROADMAP.md` shows
  3 lines removed and 7 added in the header and nothing else. The write
  envelope reported `discarded_external_edits: true` with 10 edit lines —
  that is the same header delta counted from the store's side, not a loss.

  Still true, and still the reason this needed a hand write: no `roadmap_log`
  op can edit a section intro. Filed upstream as an Ants MCP finding asking
  for `op:"amend_intro"`. Until that ships, any further preamble change takes
  the same route and the same backup.
  **Layman:** The roadmap page tells a visitor the app is on a version from five releases ago.
  Kind: doc-fix.
  Source: in-session-2026-08-19 (review-contract loop 3 on commits.md, deferred tail at the cap).

- ✅ [FIBR-0290] **The tag-push `--no-verify` habit is real practice written down in no project document.**
  `.githooks/pre-push` runs the full gate on **every** push, so pushing a
  branch and then its tag runs it twice on the same already-gated commit
  — roughly three minutes of pure duplication, and long enough to have
  caused a Bash timeout. The practice that grew up around this is to push
  the branch gated and then the tag with `--no-verify`.

  That is recorded only in this machine's agent memory. No project
  document sanctions it: `CLAUDE.md` § Build and test names the
  `pip-audit` network flake, § Doc-only pushes names the all-`.md` route,
  and neither covers a tag push. `commits.md` § 2.3 defers to `CLAUDE.md`
  for the enumeration, so it does not cover it either.

  So it is currently either an unsanctioned habit or an authorisation
  nobody wrote down. Decide which and record it — the safe reading is
  that it IS legitimate (the commit the tag points at was gated seconds
  earlier by the branch push, so the second run can only re-prove the
  same result), which would make it a third standing authorisation for
  `CLAUDE.md` § Build and test to state.

  Raised by a lane as an open question against § 2.3's "live as of" list;
  that list has since been deleted, so nothing in `commits.md` is wrong
  today — the gap is on the `CLAUDE.md` side.
  Resolved (2026-08-19, commit 1aa16d5) — but NOT the way the bullet framed it.

  The bullet asked whether the habit is legitimate and said to decide and
  record it. Both offered answers were wrong: sanctioning the bypass documents
  a workaround, which `coding.md` § 1.2 and `commits.md` § 2.3 both forbid, and
  calling it unsanctioned leaves a 3-minute duplicate gate that guarantees
  someone keeps reaching for the flag. So the cause was fixed and the habit has
  nothing left to do.

  The premise did check out first: `.githooks/pre-push` read nothing from stdin
  and unconditionally `exec`ed the gate, so a branch push followed by its tag
  ran the same gate twice on one already-gated commit — which is what
  `cut-release` Phase 5 and `/close-phase` Step 6 do on every run.

  The hook now reads the ref updates git supplies on stdin and exits early only
  when **every** ref is a tag **and** every tagged commit is already reachable
  from a remote-tracking branch. Both conditions are load-bearing: a tag whose
  commit is not yet on the remote would publish ungated code, so it takes the
  gate, as does a branch ref anywhere in the push and a hand-run hook with no
  stdin.

  Locked by `tests/features/harness/` INV-5 — five tests that RUN the hook in a
  throwaway repo with a real origin and a stub gate dropping a sentinel, because
  this hook reads as obviously right whichever way it behaves. Proven red
  against the old hook: exactly one test fails (the skip) and the four guard
  tests pass on both sides, which is what shows the skip is not too wide; a
  fifth asserts the sentinel can appear at all, so none of the others can pass
  vacuously.

  `CLAUDE.md` § Build and test now says a tag push needs no `--no-verify`, and
  that a gate running on one means the commit is not on the remote yet.
  `commits.md` § 2.3 needed no edit — it defers here and enumerates nothing.

  Full gate green: 1921 passed, 2 skipped (up 5 tests).
  **Layman:** There is a shortcut we actually use when pushing a tag, and no project file says it is allowed.
  Kind: doc-fix.
  Source: in-session-2026-08-19 (review-contract loop 3 on commits.md, deferred tail at the cap).

- ✅ [FIBR-0291] **`commits.md` gives the release-commit subject as `X.Y.Z: theme — summary` and both its examples omit the summary.**
  § 1.2's Release row gives `X.Y.Z: theme — short summary` and § 5 gives
  `X.Y.Z: theme — summary`, but both worked examples read
  `0.2.0: CSV/OFX import + duplicate detection` — no em-dash segment at
  all.

  A conformer cannot tell whether the summary half is required, optional,
  or dead text left over from an earlier format. Settle it against what
  `cut-release` actually writes, then make the examples match the stated
  format or the format match the examples.

  Lowest-value finding of the run and filed rather than fixed for that
  reason: the run had reached its cap of 3 loops for a standard, where
  the skill files the tail rather than looping again.
  Resolved (2026-08-19, commit 84fa6c1). Settled against what writes the
  subject rather than by picking a side: `cut-release` SKILL.md § Phase 3
  writes `<X.Y.Z>: <one-line theme>`, and no release commit here (0.1.13
  through 0.1.21) carries an em-dash segment. The examples were right; the
  stated format was wrong, and both statements of it now read `X.Y.Z: theme`.

  § 5 also now names where the em-dash form DOES belong — the GitHub release
  title, `X.Y.Z — <theme>` in § 6's own block. That is almost certainly where
  the drift came from, and naming it is what stops it coming back.

  No new gate: this is FIBR-0279's own deferred tail, filed at the cap rather
  than fixed, so the fix pass belongs to that run.
  **Layman:** A rule shows a commit title format with three parts, then every example it gives has only two.
  Kind: doc-fix.
  Source: in-session-2026-08-19 (review-contract loop 3 on commits.md, deferred tail at the cap).

- ✅ [FIBR-0293] **`roadmap-format.md` states the store-backed carve-out five times and keeps missing one.**
  `review-contract` reached its cap of 3 loops on this document
  (FIBR-0288) and the cap was **violent**: all 8 of loop 3's findings traced
  to text the run itself had written. Per the skill, a binding cap on a
  standard is evidence about the document. This is the diagnosis.

  The document describes a **hand-maintained** `ROADMAP.md` — the author
  chooses a bullet's position, moves it, deletes it, retitles its release
  block. This project's roadmap is **store-backed and rendered**, where none
  of those are available. So nearly every rule needs a two-branch carve-out,
  and the run kept finding another place the branch had not reached:
  § 3.5.2, § 3.5.4, § 3.8, § 3.9, § 3.5.2's own closing paragraph, § 3.7,
  § 4.3. Each fix was correct and each left another site.

  **The fix is structural, not another carve-out.** State the branch once —
  a short § 3.0 saying which mode a project is in and what is unavailable in
  the store-backed one — and delete the per-rule repetitions. Five copies of
  one rule is five things to keep true, which is what produced this pattern.

  Size is a secondary factor and probably not the main one: 624 lines against
  a 364-line largest sibling (`commits.md`), but still inside the ~800-line
  range a cold read handles. Splitting § 4 (CHANGELOG) out from § 3 (ROADMAP)
  is the obvious cut if a split is wanted anyway.

  Not urgent, and NOT a re-gate of the same document: this is one edit with a
  clear shape, and rule 14's test would send the result through a fresh gate
  on its own merits.
  Resolved (2026-08-19, commits ed2e1d5, 57fae24, 0b5c575, 07ff5b1).

  The branch is now stated once, in a new § 3.0: the two modes, which one
  this project is in, and a table of the four operations the rest of the
  document teaches that are unavailable store-backed. Fourteen repetition
  sites became pointers -- including § 3.8's "Position by priority" bullet,
  a site this bullet's own diagnosis had not listed, found by re-grepping
  rather than working from the list.

  Gated: `review-contract --genre standard --max-loops 3`, 9 cold lanes over
  3 loops. 19 verified findings, 19 fixed, 1 dismissed, no deferred tail.
  Loop log rows 4-6 are inline at the end of the document.

  **A CALM cap this time** -- 2 of loop 3's 5 findings landed on text the run
  wrote, against 8 of 8 at the previous run's cap. So the restructure did what
  this bullet predicted: the document stopped repairing its own repairs.

  What centralising exposed, and no per-rule carve-out ever could: § 3.0 named
  § 3.8's severity prefix as the store-backed priority carrier, and the prefix
  is mandated nowhere outside a findings fold-in -- zero of 285 bullets carry
  one. The document was promising a mechanism that does not exist. The
  over-claim is fixed; whether to ADD a carrier is a user decision, filed as
  FIBR-0294 rather than decided by the gate.
  **Layman:** A rule document was written for a hand-edited roadmap, but ours is generated — so almost every rule needs an exception, and the exception keeps getting left out of one place.
  Kind: doc-fix.
  Source: in-session-2026-08-19 (review-contract cap report on roadmap-format.md).

- ✅ [FIBR-0294] **Store-backed, the roadmap has no way to express priority at all — decide whether it needs one.**
  Store-backed (roadmap-format.md § 3.0), `roadmap_log` appends to the
  end of a section and takes no positional locator, so position carries
  no priority. The only other carrier the format has is § 3.8's severity
  prefix in the bold headline — and it is required ONLY inside a findings
  fold-in. Measured 2026-08-19: **zero of 285 bullets carry one**, and
  this roadmap has no fold-in sections at all.

  So § 3.5.4 step 4's ranker has nothing to sort on, and priority is
  currently not expressed anywhere on this roadmap.

  All three cold lanes of the gate proposed making the prefix REQUIRED on
  every actionable bullet. That was refused and filed here instead: it
  puts 285 bullets in breach at a stroke, which is exactly what the
  previous gate declined to do for `Kind:` (still at 257/285 and carrying
  its own backfill).

  Three options, and this is a user decision rather than a review finding:
  1. Leave it. Priority is set by conversation and by section order; the
     format simply does not model it, and § 3.0 now says so plainly.
  2. Require the prefix on new bullets only, no backfill.
  3. Require it everywhere and take the backfill, alongside `Kind:`.

  The document is accurate either way -- it no longer claims a carrier
  that does not exist. This item is only about whether to add one.
  Resolved (2026-08-19): user decision -- option 1, leave it. The format does not model priority and § 3.0 says so plainly; the severity prefix stays required only inside a § 3.8 findings fold-in. No backfill, no new mandate, no document change. Priority is set by conversation and by section order.
  **Layman:** Our roadmap is generated, so you cannot drag an urgent item to the top; the one marking that could show urgency is optional and nobody uses it, so nothing on the list says what is urgent.
  Kind: doc.
  Source: in-session-2026-08-19 (review-contract loop 2 on roadmap-format.md, surfaced not decided).

- ✅ [FIBR-0295] **`act` is installed but unconfigured, so cut-release's mandatory pipeline phase cannot run.**
  `cut-release` Phase 2b requires EXECUTING `.github/workflows/*.yml`
  locally before the release commit, and explicitly forbids substituting
  a hand-written mirror. It runs that phase when `act` is present.

  `act` IS present (`/usr/bin/act`) and has never been configured. Its
  first run wants an interactive choice of runner image and writes
  `~/.config/act/actrc`; with no TTY it prints the menu and dies
  `level=fatal msg=EOF`. Measured 2026-08-19: `act push -W
  .github/workflows/ci.yml -n` fails this way even as a dry run, so the
  failure is configuration, not the workflow.

  So the phase is neither "act present" nor "act absent" -- it looks
  available and is not, which is the shape that costs a detour rather
  than a decision.

  What v0.1.22 did instead: ran `scripts/ci-docker.sh`. That is defensible
  and not a hand-written mirror -- `ci.yml` is checkout -> `ci-setup.sh`
  -> `ci-local.sh` inside `python:3.12-slim-bookworm`, and `ci-docker.sh`
  runs the same image and the same two scripts, which FIBR-0001 INV-2
  locks and the harness suite enforces. UNCOVERED by that substitution:
  `actions/checkout` and the `apt-get install git` step before it.
  Nothing else in the job.

  Two ways to close it, and it is a decision rather than a bug:
  1. Configure `act` once (write `~/.config/act/actrc` pinning a runner
  image for `ubuntu-24.04`) and let Phase 2b run as designed. Costs a
  one-off image pull; a machine-level change outside this repo.
  2. Record `ci-docker.sh` as this project's sanctioned Phase 2b, with
  the two uncovered steps named, so no future release re-derives the
  argument. Cheaper, and honest, but it is a local override of a skill
  rule and belongs in CLAUDE.md rather than in a session's head.

  Whichever is chosen, write it down -- the cost this time was working
  out from scratch that the phase could not run and why the substitute
  was acceptable.
  Resolved (2026-08-19): option 2, the user's decision — record `ci-docker.sh`
  as this project's sanctioned Phase 2b rather than configure `act`. Written
  into CLAUDE.md § Cutting a release, and it names all three things the
  substitute does not reach rather than the two this bullet guessed: the
  `actions/checkout` step EXECUTING (its pin and `persist-credentials: false`
  are still checked, because `zizmor` is a `ci-local.sh` stage and this run
  executes `ci-local.sh` — measured, `zizmor .github/workflows/` exits 0 on the
  real tree and 14 with the pin reverted to `@v7`); the `apt-get install git
  ca-certificates` step, whose effect `ci-setup.sh` covers; and the TREE ITSELF,
  which this bullet did not anticipate — `ci-docker.sh` does `cp -a` of the
  working directory, so gitignored files travel into the container where
  `actions/checkout` gives CI tracked files only. Measured by running that copy:
  `.corpus-numbers` reaches the container. The section also pins a test for the
  lapse condition, since "configured" settles nothing on its own — `actrc`
  present AND `act push -W .github/workflows/ci.yml -n </dev/null` exiting 0;
  today that dry run exits 1 on `level=fatal msg=EOF`, so the override stands.
  Gated under rule 14 (`review-contract --genre standard --max-loops 3`): three
  loops, 18 verified findings, all fixed, rows 7-9 of
  docs/reviews/CLAUDE-md-review-log.md. The gate reached its cap with the
  collateral share not falling, which is filed separately as FIBR-0296 —
  CLAUDE.md is 899 lines and wants splitting.
  **Layman:** The tool that runs our GitHub checks on this machine has never been set up, so every release quietly falls back to a different check and someone has to work out why all over again.
  Kind: chore.
  Source: in-session-2026-08-19 (hit while cutting v0.1.22).

- 📋 [FIBR-0296] **CLAUDE.md is 899 lines and its review no longer converges — split it.**
  Filed by `review-contract`'s own cap note, not by a reader's impression.

  The 2026-08-19 run (rows 7-9 of docs/reviews/CLAUDE-md-review-log.md)
  reached its cap with verified findings falling 6 -> 7 -> 5 while the
  share landing on text THAT RUN had written did not: 0/6, then 4/7, then
  3/5. Each loop was substantially repairing the one before. Per the
  skill's § At the cap that is a violent cap rather than a calm one, and
  the prescribed response is NOT to re-run the gate -- a fresh run starts
  at loop 1 against a document whose last two loops were each repairing
  its predecessor.

  The size signal is what to act on. CLAUDE.md is **899 lines**, past the
  ~800-line range in which two cold reads can be expected to reach all of
  it. And the failure mode the run kept producing is exactly what that
  size causes: a rule stated in two or three places and corrected in one.
  Three separate instances in one run --
  - "ci-docker.sh reproduces CI exactly" in three places against the new
    Phase 2b section saying it does not (loop 7, all three lanes);
  - the no-drift caveat added to the ci-docker.sh module-map bullet and
    not to its ci.yml neighbour four lines away (loop 9);
  - the FIBR-0275 guard recorded as landed in one paragraph and as not
    landed 65 lines below (loop 9, both lanes).

  The 2026-08-18 run hit the same shape (rows 1-3): an absolute headline
  with its exception twenty lines down, three times over.

  What a split would have to preserve, and why this is not a five-minute
  job: the file is loaded in full every session, so a split trades one
  long read for several reads plus a routing decision, and a rule that
  moves out of the always-loaded file is a rule some session will not
  read. The candidates are the self-contained procedural blocks -- §
  Cutting a release (~110 lines), § Build and test (~200), § Doc-only
  pushes (~110) -- each of which is a runbook consulted at a moment, not
  a standing rule needed on every turn. § Where state lives, § Push
  policy, § Commit conventions and § Resumption flow are the part that
  genuinely must stay resident.

  Decide the split before writing it: a document that grows back is worse
  than one that was never split.
  Second piece of evidence, recorded because it is a REVIEW COST rather
  than a defect and would otherwise not be written anywhere. Across all
  three loops of the 2026-08-19 gate, lanes spent an open question on the
  same thing: this file cites `FIBR-0001 INV-1`, `tests/features/harness/
  INV-5` and a bare `(INV-7)` without saying which are SPEC invariants and
  which are SUITE invariants — and the two numberings genuinely diverge
  (the harness suite's own INV-4 is what enforces the spec's INV-2). Every
  citation checked out correct, so each one correctly failed the
  materiality gate and none was fixed. But three lanes each had to stop
  and say they could not settle it, in three consecutive loops, and any
  future gate on this file pays the same toll. If the split happens, give
  the moved sections a convention — spell suite invariants as
  `<suite>/spec.md INV-n` and spec invariants as `<ID> INV-n` — rather
  than leaving a bare `INV-7` to be resolved by whoever is reading.
  **Layman:** Our main instructions file has grown big enough that a careful reader can no longer hold all of it, so fixing one rule keeps breaking another one somewhere else in the file.
  Kind: doc.
  Source: review-contract-2026-08-19 loop 3 cap note (FIBR-0295 gate).

- ✅ [FIBR-0299] **No versioning standard: we pledge semver in CHANGELOG.md but nowhere says what our numbers MEAN.**
  releases.md 1 governs version LOCKSTEP -- every version-bearing file
  moves together -- and says nothing about what the number means.
  CHANGELOG.md's header pledges Semantic Versioning. Between them,
  nothing states the 0.x -> 1.0 criteria, so the number has drifted from
  reality: 196 shipped roadmap items and all thirteen planned phases
  delivered, still published as 0.1.22.

  Write docs/standards/versioning.md: what MAJOR/MINOR/PATCH mean for a
  desktop app whose real compatibility surface is the encrypted vault
  format, the backup/export format and the update mechanism -- not a code
  API. State the 1.0 gate explicitly.

  Gate it with review-contract --genre standard (rule 14: a new standard
  changes what a conformer writes). A global versioning standard is being
  written in parallel; compare the two once both exist.
  Resolved (2026-08-20): docs/standards/versioning.md written and gated
  under rule 14 (review-contract --genre standard, this project's cap of
  3). It owns what the number MEANS; releases.md 1 and .claude/bump.json
  keep owning where it lives.

  Shape: a six-row compatibility surface (vault, backup, export, update
  path, saved import profiles, launcher command); MAJOR/MINOR/PATCH keyed
  to that surface plus a required-user-action limb; below 1.0 the mapping
  shifts down one place; a five-condition 1.0 gate that deliberately
  excludes any third party's queue, so Flathub (FIBR-0159) and code
  signing (FIBR-0133) cannot hold the version back.

  Gate: 3 loops, 3 cold lanes each, 23 verified findings all fixed
  (7 / 9 / 7), 1 dismissed as inert. Loop 3 was a VIOLENT cap -- five of
  seven findings landed on text the run itself wrote -- but at 238 lines
  this is the smallest standard in the folder, so the cause was
  duplication rather than size: one rule restated in four places, each
  copy drifting. Fixed by consolidation (3.2 and 3.3 now defer to 3.1
  instead of restating its test). Per the violent-cap rule the gate is
  not re-run on this document.

  Two real product gaps the review surfaced, filed not fixed: FIBR-0301
  (nothing catches a signing-key rotation that strands installed
  updaters) and FIBR-0302 (no test restores a .fbk from an earlier
  release).

  Collateral fixed: CONTRIBUTING.md, docs/standards/README.md, README.md
  and CLAUDE.md all enumerate the standards and needed the seventh added;
  the new file was missing the first-line v1 marker its siblings carry.

  Sibling FIBR-0300 (the stale pre-alpha badge) stays open -- its wording
  should be picked against this standard.
  **Layman:** Nothing written down says when the app stops being a 0.x preview and becomes version 1.0.
  Kind: doc.
  Source: in-session-2026-08-20 (user question: what gets us to v1.0?).

- 📋 [FIBR-0300] **README.md's status badge still reads pre-alpha after 196 shipped items and 22 releases.**
  README.md line 13 carries
  `[![Status](https://img.shields.io/badge/status-pre--alpha-orange)]()`.
  It is the first thing a visitor to a public repo sees, and it has been
  false for a long time: every planned phase P01-P13 has delivered its
  headline work, P02 through P11 have zero open items, and the project
  publishes signed releases with eight assets.

  Fix is one line, but pick the wording against the versioning standard
  (sibling item) rather than in isolation -- badge and version number
  should tell the same story.
  **Layman:** The front page of the project still calls it pre-alpha, which puts people off something far more finished than that.
  Kind: doc-fix.
  Source: in-session-2026-08-20 (found answering the v1.0 question).

- 📋 [FIBR-0301] **Nothing catches a signing-key rotation that strands every installed copy's updater.**
  docs/standards/versioning.md 2 names the update path as a
  compatibility surface whose break includes "a signing-key rotation".
  Neither existing catcher covers that:

  - `scripts/release-linux.sh`'s hard gate verifies the signature against
    the `RELEASE_PUBLIC_KEY_B64` committed in the SAME tree, so rotating
    the key and the constant together passes green.
  - Every test in `tests/features/auto_update/` is same-build; none
    verifies a release against a PREVIOUSLY SHIPPED key.

  So a rotation ships, the gate is green, and every installed copy is
  permanently unable to verify an update -- the exact break the surface
  row exists to name. CLAUDE.md already warns not to run
  `gen-signing-key.py` to "fix" a missing key for this reason; nothing
  enforces it.

  Wanted: a test that verifies a release artifact against a pinned
  historical public key, so changing the committed constant turns
  something red.
  **Layman:** If the release signing key is ever changed, every already-installed copy would silently stop being able to update, and no test would notice.
  Kind: test.
  Source: review-contract-2026-08-20 (FIBR-0299 loop 3, lane finding).

- 📋 [FIBR-0302] **No test restores a .fbk backup written by an earlier release.**
  `tests/features/backup/test_backup.py`'s round-trip is same-build: it
  exports from a seed and verifies with one version, asserting
  `res.schema_version == LATEST_SCHEMA_VERSION`. It never crosses a
  version boundary.

  `services/backup.py:376-381` guards the OTHER direction (refusing a
  backup from a NEWER schema), and `:354` opens and migrates an older
  backup forward -- so the product does support the older direction, and
  nothing pins it.

  docs/standards/versioning.md 2 makes "a backup taken on any earlier
  release cannot be restored" a MAJOR break, so this is the surface's
  primary failure mode with no catcher.

  Wanted: a fixture .fbk written at an older schema version, restored by
  the current build. The same shape would cover saved import profiles,
  whose round-trip is same-build for the same reason.
  Progress (2026-08-21): materially more urgent now that FIBR-0019 has
  shipped, which its section 11 predicted. A restore no longer writes
  the flat v1 sidecar -- BackupService.restore_backup mints a random DEK,
  re-keys the restored copy to it and writes the v2 slots sidecar, so
  what a restored vault LOOKS like has changed under this untested
  surface. The .fbk container itself is unchanged (its inner vault.db
  keeps its derive_key(backup_password, ...) schedule), so a backup taken
  before the change still restores; nothing pins that, which is the whole
  of this item.

  The fixture wanted is now two, not one: a .fbk at an older SCHEMA
  version, and a .fbk taken by a pre-envelope build. Both restore through
  the same path and neither is covered.
  **Layman:** Backups are only ever tested by writing and reading them with the same version, so a change that made old backups unrestorable would not be caught.
  Kind: test.
  Source: review-contract-2026-08-20 (FIBR-0299 loop 3, lane finding).

- 📋 [FIBR-0303] **Amend versioning.md with the two rules the fleet survey found missing: pre-release suffixes and schema-vs-app independence.**
  A survey of every other project on this machine found two rules worth
  adopting and a list worth NOT adopting. Hold this until the global
  versioning standard lands, then make ONE amendment and gate it once --
  docs/standards/versioning.md hit a VIOLENT cap on 2026-08-20 (five of
  loop 3's seven findings landed on text the run itself wrote), so it
  must not be re-gated casually.

  1. PRE-RELEASE / RC SUFFIX -- versioning.md says nothing, and the
     tooling cannot express one: `.claude/bump.json`'s version_pattern is
     suffix-free `([0-9]+\.[0-9]+\.[0-9]+)`, as is `cut-release`.
     Ants_Terminal's rule is the one to take: the `-rcN` suffix lives
     ONLY at the git tag, the GitHub-release title and the asset
     filename, never in a version-bearing source file -- which is exactly
     why a suffix-free bump pattern is correct rather than a limitation.
     Three projects spell it three ways (`-rc1`, `-rc.1`, `-pre.1`); take
     whatever the global standard settles on rather than inventing a
     fourth.

     The finbreak-specific half nobody else has: `_parse_version`
     (services/update.py:64) returns None for any segment that is not a
     plain ASCII decimal, so a `0.2.0-rc.1` tag is UNUSABLE to the
     updater and is silently skipped. That is the right behaviour --
     Ants_Terminal buys the same safety with a separate zsync channel --
     but here it is incidental, undocumented, and one "fix" to accept
     suffixes away from pushing an RC to every stable user. Write it down
     as load-bearing.

  2. SCHEMA VERSION IS INDEPENDENT OF THE APP VERSION -- perch states the
     general rule ("Two version lines are independent of the app version
     and never move with it"). finbreak has `LATEST_SCHEMA_VERSION = 13`
     against `__version__ = "0.1.22"` and versioning.md never says they
     are unrelated, though its 2 vault row leans on the schema.
     DOOM_Ants carries the same warning for an internal engine constant.

  DO NOT LIFT, and the reasons matter:
  - Vestige's derived/computed version numbers (a weekly train, numbers
    from git tags). A computed number makes "is this breaking?"
    unanswerable by construction, which is the opposite of this
    standard's whole premise.
  - OneUp's "MAJOR because the engine is replaced" -- it grades an
    internal rewrite with no user-visible change, contradicting 1.1.
  - Any project's own list of breaking surfaces ( 2 is finbreak's).
  - Any "where the version lives" list -- releases.md 1 owns lockstep.
  - Rolodex's two "when unsure" decision questions. Useful, but they
    restate 3's test in a second place, and a rule restated in several
    places drifting apart is precisely what caused this document's
    violent cap. If wanted, replace 3's prose rather than adding beside
    it.

  VALIDATION worth recording: the global roadmap's own survey (CFG-0173)
  names the central unanswered question as "SemVer is written for things
  other code imports; most projects here are not that". versioning.md
  1.2 already answers it for finbreak. On three axes -- 1.0 criteria,
  security-fix versioning, and deprecation -- finbreak's is now the most
  complete document on the machine; only DOOM_Ants states any 1.0 exit
  condition, only Rolodex states a security-fix rule, and nothing anywhere
  handles deprecation.
  **Layman:** Two gaps the new versioning rules do not cover yet: what a release-candidate version looks like, and that the vault's internal format number is separate from the app's version number.
  Kind: doc.
  Source: fleet-survey-2026-08-20 (other projects' versioning standards, after FIBR-0299).

- 📋 [FIBR-0330] **CLAUDE.md runs the two roadmap_query survey calls together, so a session skips a call it owes.**
  Where state lives item 2 names `mode:"headline_only"` as the cheap survey, then
  says a filtered call withholds bodies "but still returns `kind` as a field --
  so the survey answers Resumption flow step 2 on its own; no second call is
  owed."

  Both halves are true of a DIFFERENT call. A status-filtered query in the
  default bullets mode does return `kind`. `mode:"headline_only"` does not, and
  cannot: ANTS-4699 fixed its contract to exactly {id, status,
  headline_oneline, section_slug}, so `kind` is unobtainable there by any
  argument. Because the preceding sentence calls headline_only "a cheap survey",
  "the survey" reads as that mode, and a session then believes step 2 is already
  answered when it has no `kind` at all.

  Confirmed live 2026-09-02: a `headline_only` call at session start returned no
  `kind`, and step 2 needed a second query. The Ants schema note for ANTS-4699
  says the wider claim was recorded by "a project doc" -- this is that doc.

  The fix is one or two sentences: say which call returns `kind`, and drop the
  "no second call is owed" clause or attach it to the bullets-mode call. It
  changes what a conformer does, so it trips global rule 14's gate on a file
  FIBR-0296 already says no longer converges under review -- which is why this
  is filed rather than fixed in passing.
  **Layman:** A note in our own instructions is ambiguous enough that Claude can skip a lookup it actually needs at the start of a session.
  Kind: doc-fix.
  Source: in-session-2026-09-02.

- 📋 [FIBR-0331] **Turn check_untyped_defs on for the test suite, where mypy still skips most bodies.**
  Split out of FIBR-0313 L14 rather than done with it. The app package half
  is DONE and pinned: pyproject now sets check_untyped_defs for finbreak.*,
  src was already clean under it, and a deliberate error in an unannotated
  src function was confirmed caught where it was previously invisible.

  The tests half is the work. mypy skips the bodies of unannotated
  functions, and most of this suite is unannotated -- so the gate does not
  read the code that decides whether the gate means anything. Measured
  2026-09-03: 345 errors across 25 files, the heaviest being categories,
  theme, categorisation, table_state and app_shell.

  Mechanical but not free: most are Optional narrowing on Qt accessors
  (widget() / item() returning None), which is the same class the annotated
  Qt tests already carry asserts for. The risk to watch is a fix that
  weakens what a test asserts to satisfy the checker.

  Deliberately NOT closed by silencing: an override that turns it on for
  finbreak.* and off for tests would close the gate gap on paper while the
  suite stays unread.
  **Layman:** The type checker currently reads the app's code closely but skims the tests, so a broken test can look fine.
  Kind: test.
  Source: in-session-2026-09-03 (FIBR-0313 L14, split).

### 📦 Packaging

- ✅ [FIBR-0003] **P01: bundling smoke-test (de-risk native libs early).**
  Freeze the trivial placeholder app into
  a one-file **AppImage** *and* a PyInstaller bundle, then launch
  each on a clean target with **no Python installed**, confirming
  the CPython runtime + a stub load of all three native stacks —
  SQLCipher, Qt, and qpdf/`pikepdf` (scope broadened to the third
  stack per the FIBR-0003 spec, 2026-07-01). This surfaces
  the native-lib collection risk named in ADR-0007 *now*, not
  after ten phases are built on top. Full multi-platform
  packaging + publish pipeline is deferred to P13. Dependencies:
  FIBR-0001. Lanes: build, ci. Kind: chore. Source: planned.
  Resolved 2026-07-01: closed by /close-phase. `--self-test` loads all three native stacks; `build-smoke.sh` freezes a PyInstaller onefile + AppImage in a `python:3.12-slim-bookworm` container (glibc floor ~2.36; wheels' own floor 2.34) and both print `FINBREAK_SELFTEST_OK` in the Python-free `debian:13-slim` clean-room — ADR-0007's clean-machine criterion proven at P01. The de-risk empirically caught 5 real portability traps (host-glibc mismatch, static manylinux Python, missing Qt system libs, missing harfbuzz, missing libGL). Toolchain pinned (INV-4); opt-in build stage + weekly CI job keep the everyday gate fast. Impl commit 49e87b6; /audit + /indie-review zero actionable on the close pass (3 doc/comment drifts fixed inline). Tag FIBR-0003-complete.
  Kind: chore.
  Source: planned.
  Lanes: build, ci.

---

- ✅ [FIBR-0054] **Optional in-app auto-update (check → prompt Later/Skip/Update now → download, install, relaunch).**
  User request 2026-07-09: the app must offer (never force) updates. Flow:
  on a new version, prompt the user with three choices — **Later** (re-ask next
  launch), **Skip** (this version, don't re-prompt for it), **Update now**. On
  "Update now": download the latest build, close the app, install the update, and
  relaunch automatically.
  Progress (2026-07-10): brainstormed + design approved. Scope = full in-app auto-update, Linux/AppImage first (Windows seam only, not built). Two phases: (1) real release infra — version 0.1.0, signed release AppImage, published v0.1.0 GitHub Release; (2) the updater — opt-in launch check → Later/Skip/Update-now prompt → download + Ed25519-signature-verify → atomic AppImage swap → relaunch. Integrity gate = Ed25519 signature verified via the already-bundled `cryptography` lib (no new runtime dep/tool). Next: write docs/specs/FIBR-0054.md → /cold-eyes.
  Resolved (2026-07-14) by /close-phase. Code-complete since v0.1.0 and field-proven through v0.1.9; the live auto-relaunch confirmed v0.1.8->v0.1.9 (commit 8e4a298) was the last gate before close. Close ran a full audit (semgrep/ruff/bandit/gitleaks) + 2 cold indie-review lanes over the auto-update surface: 1 MEDIUM (_on_download_failed missing the auto-lock guard its ready-sibling has) + 3 LOW (temp-staging outside the try; 2 test-fidelity) all fixed inline (commit 67132c1); 2 semgrep dynamic-urllib FPs allowlisted (allowlist-001). Gate green 856/1. Tag FIBR-0054-complete. Windows in-app auto-update is FIBR-0131 (separate).

  Design notes (to settle when picked — needs its own brainstorm + spec →
  /cold-eyes):
  - **Per-platform mechanism** (no single cross-platform updater). *FIBR-0054
  has since settled the **Linux AppImage** slice: full-file download + atomic
  replace + Ed25519 verify (D2 rejected zsync/delta; D1 chose Ed25519 via the
  bundled `cryptography`, not AppImageUpdate). The other platforms below remain
  to-settle.* Linux AppImage → AppImageUpdate / zsync + delta; Flatpak/Flathub
  → the platform updates it
  (an in-app updater would be redundant/blocked there — likely just deep-link to
  the store or no-op); Windows .exe → a bundled updater (e.g. WinSparkle) or a
  small helper that swaps the install after exit; macOS .app → Sparkle. The
  "close → install → relaunch" hand-off is the platform-specific hard part.
  - **Update source + integrity:** check GitHub Releases (the repo already
  publishes there); verify a signature / checksum before installing (security —
  never run an unverified downloaded binary). Respect the no-network default
  elsewhere: the update check + signed download are the one deliberate outbound
  flow, opt-in via a setting, off by default until the user consents.
  - **UX:** a non-blocking prompt (not a modal that traps them); "Skip this
  version" persists the skipped version (in the plaintext settings sibling, like
  window geometry — not the vault); works while locked (no vault needed to
  update). Show current vs available version + changelog link.
  - **Depends on** the release pipeline (ADR-0007 / FIBR-0003 bundling) being able
  to publish signed artifacts. Sequence after the core app is feature-complete;
  not blocking FIBR-0052/P08/P09.
  **Layman:** The app checks for a newer version and, if you choose, downloads and installs it for you and reopens — you're always in control (Later, Skip this version, or Update now).
  Kind: feature.
  Lanes: packaging, ui, services.
  Source: user-request-2026-07-09.

- ✅ [FIBR-0132] **Windows `.exe` launches with a console window — build `--windowed` to suppress it.**
  FIBR-0015 froze the .exe with `--onefile` but not `--windowed`, so PyInstaller attaches a console (the black cmd window the user saw before the GUI). Fix: add `--windowed` in build-windows-exe.py. Wrinkle: `--windowed` sets sys.stdout/stderr to None on Windows (PyInstaller docs), so the windows-build.yml `--self-test` sentinel read (FINBREAK_SELFTEST_OK) goes blind — reroute the sentinel to a file via a FINBREAK_SELFTEST_OUT env var (run_self_test already takes an `out` stream) and have the workflow read the file + Start-Process -Wait for the now-GUI process. Regression-lock with a windows_build feature test asserting the driver builds --windowed.
  **Layman:** Stops the black command-prompt window from flashing up before the app opens on Windows.
  Kind: fix.
  Source: user-report-2026-07-14.
  Resolved 2026-07-14: `build-windows-exe.py` now freezes `--windowed`; self-test sentinel rerouted to FINBREAK_SELFTEST_OUT file so the clean-room read survives the None stdout; windows-build.yml reads the file via Start-Process -Wait. Regression-locked (test_driver_freezes_windowed_gui_exe + test_selftest_can_redirect_sentinel_to_a_file). Gate green 853/1. Ships in the next Windows release build.

- 🚧 [FIBR-0133] **Free Windows code signing via SignPath Foundation (OSS program).**
  User applying to SignPath Foundation's free code-signing program for OSS. Prep done this session: PRIVACY.md added (finbreak collects no data; local-only); README gained the required SignPath attribution ("Free code signing provided by SignPath.io, certificate by SignPath Foundation") which the hub site renders onto the download page (antsprojectshub.co.za/p/fin-break.html) — NOTE (2026-07-26 debt sweep): that attribution string is no longer in README.md, having been removed after the decline; it must be restored before any reapplication; Google Search Console verification + indexing done so the app is discoverable (a SignPath requirement — see [[finbreak-public-site-and-signing]]). Also fixed the stale milnet01/Fin_Break->finbreak repo slug in the hub data. REMAINING once approved: wire the SignPath signing step into .github/workflows/windows-build.yml so release .exe artifacts are signed; promote the .exe to a signed release asset. Requirements met: MIT license, public repo, GitHub 2FA (user to confirm), discoverable (in progress). Windows-only (macOS = Apple $99/yr; Linux AppImage GPG-signed already).
  **Layman:** Get finbreak's Windows app officially signed for free so Windows stops showing "unknown publisher" warnings.
  Kind: package.
  Source: user-request-2026-07-14.
  Scope boundary (2026-07-14): "promote the .exe to a signed release asset" above means the AUTHENTICODE/publisher signature only. The Ed25519-signed .exe release asset (the sidecar the in-app updater verifies) is FIBR-0131's D5, not this item. FIBR-0133 adds the Authenticode signature to that already-attached .exe once SignPath approves.
  Progress (2026-07-14): the SignPath "discoverable" requirement is now MET — the Fin Break page (antsprojectshub.co.za/p/fin-break.html) is live and INDEXED on Google (confirmed via a Google search result, ~3h after publish). Requirements now: MIT ✓, public repo ✓, PRIVACY.md + SignPath attribution ✓, discoverable ✓; REMAINING = SignPath's own approval ONLY (external, awaited); GitHub 2FA confirmed ON (2026-07-14, GitHub-mandated). All contributor-side SignPath requirements (MIT, public repo, PRIVACY + attribution, discoverable, 2FA) are now MET. No code work outstanding; FIBR-0131's Windows updater is already merged and waiting for the v0.1.10 release that will bundle both the Authenticode signature (this item) and the Ed25519 .exe.sig.
  Update (2026-07-16): SignPath Foundation DECLINED the application. Plan per the user: build more of a public presence first, then reapply and hope for approval next time. Stays 🚧 (blocked on the reapplication + their approval, not on any contributor-side prep — MIT/public/2FA/discoverable are all still met). Windows .exe remains un-Authenticode-signed meanwhile → SmartScreen "unknown publisher" persists; the Ed25519 updater sidecar sig is unaffected.

- ✅ [FIBR-0134] **Embed the finbreak icon in the Windows .exe (was PyInstaller's default console-stub icon).**
  The published v0.1.9 finbreak-0.1.9-x86_64.exe showed PyInstaller's default console-stub icon in Explorer/taskbar because scripts/build-windows-exe.py never passed --icon to the freeze. Fixed by adding `--icon assets/icon/finbreak.ico` (the committed multi-size 16..256 Windows icon from FIBR-0037) to the PyInstaller command, plus a fail-loud guard that the .ico exists and a windows_build regression test asserting the driver passes --icon and the .ico is a real MS icon. Driver flag only (like --windowed/FIBR-0132), so the Linux parity guard is untouched; the Linux AppImage icon travels separately via appimagetool. The icon-bearing .exe appears on the NEXT Windows build/release — the already-published v0.1.9 asset is not rewritten.
  **Layman:** Make the Windows app file show finbreak's donut icon in Explorer instead of a generic black terminal icon.
  Kind: fix.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14): added --icon assets/icon/finbreak.ico to scripts/build-windows-exe.py + a fail-loud .ico-exists guard + a windows_build regression test (test_driver_embeds_the_app_icon). Gate-relevant tests green (windows_build 13 passed). Icon lands on the next Windows build.

- ✅ [FIBR-0152] **Update prompt shows only the latest release's notes — accumulate all changes since the user's version.**
  Gap (verified 2026-07-19): the UpdateDialog "What's new" panel is filled
  from GitHub's /releases/latest — a SINGLE release's body
  (services/update.py:224 `notes = release.get("body") or ""`;
  fetch_latest_release hits /repos/{owner}/{repo}/releases/latest,
  update_fetch.py:22). So a user N versions behind sees ONLY the newest
  release's notes; the intervening releases' notes are never shown. There is
  no in-app changelog viewer either (zero `changelog` refs under src/), and
  the notes panel deliberately has link-opening OFF (offline/no-egress
  posture, INV-12) so there is no "view full changelog online" fallback.
  Resolved (2026-07-28): SHIPPED by TDD, but NOT via Option A — a bundled
  CHANGELOG.md stops at the running version, so it cannot describe the
  releases the user has yet to install. Took the item's own alternative B,
  narrowed: the OFFER still rests solely on /releases/latest (D11 prerelease
  exclusion intact); a second, best-effort read of the same host's
  /releases list (new update_fetch.fetch_releases, sharing a new _get_json
  with fetch_latest_release, same cap + timeout) feeds only the notes;
  pure _accumulated_notes keeps every non-draft, non-prerelease body newer
  than the running version and no newer than the offered one, newest first,
  each headed by its version. Any failure of the second read degrades to the
  single body — it never costs the user the update. No new module and no new
  host, so INV-12 (one networked file) is unchanged; notes stay verbatim
  non-tr() release data. 6 new tests (list parse + URL, 3-behind accumulate,
  1-behind latest-only, draft/prerelease excluded, list-failure fallback,
  qtbot dialog renders the accumulated body). Gate: 1398 passed, 2 skipped.

  Recommended fix (Option A — best fit for the offline posture): ship
  CHANGELOG.md inside the bundle and have the update prompt show every entry
  BETWEEN the user's current __version__ and the latest available version. No
  new network surface; reuses the Keep-a-Changelog structure already
  maintained. A small version-range slicer over the local file feeds the same
  `notes` string the dialog already renders as markdown.

  Alternatives considered: (B) fetch /releases (all, not /latest) and
  concatenate each body newer than current — more network + a bigger response
  cap + prerelease filtering; (C) leave latest-only. Prefer A.

  Reproduce-first when built: a service-level test that, given current=0.3.0
  and a CHANGELOG containing 0.4.0/0.5.0/0.6.0 sections, returns the
  concatenated 0.4.0..0.6.0 notes (and latest-only when exactly one behind);
  plus a qtbot assertion that the dialog renders the accumulated body. Must
  preserve FIBR-0054 INV-12 (no new egress) and the lupdate/tr() posture
  (release notes stay non-tr() verbatim data).
  **Layman:** If you skip a couple of updates, the "What's new" box only tells you about the newest one — it should show everything that changed since your version.
  Kind: enhancement.
  Lanes: ui, services, packaging.
  Source: user-request-2026-07-19.

- ✅ [FIBR-0158] **Un-exclude the Debian 13 + Ubuntu 24.04 deb builds on OBS (home:milnet:finbreak).**
  Both RPM families (openSUSE Tumbleweed + Fedora 44) build, publish and install
  from OBS (FIBR-0155). The two deb targets (Debian 13, Ubuntu 24.04) are
  currently "excluded" — OBS finds no Debian source package to build. Two gaps to
  close, both verified-design work (rule 13 — confirm against OBS debtransform
  docs, don't recall):

  1. Author a `.dsc` at the OBS package root — OBS's debtransform only builds a
  deb when a `.dsc` is present. It needs the debtransform headers
  (Debtransform-Tar: the finbreak orig tarball; the debian/ dir). set_version
  must stamp its Version (add it to the lockstep, obs_packaging INV-6).

  2. Deliver vendor.tar.gz INTO the deb build tree. RPM gets it as Source1, but a
  deb build only unpacks the orig tarball — which does not contain vendor/.
  Cleanest: switch debian/source/format from "3.0 (native)" to "3.0 (quilt)"
  and ship the wheels as a component orig tarball
  (finbreak_<ver>.orig-vendor.tar.gz), which dpkg-source unpacks to vendor/ at
  the source root, where debian/rules already looks (--find-links vendor/).

  Then expect the same class of per-distro fixes the RPM bring-up surfaced, found
  empirically from the OBS build logs:
  - Debian/Ubuntu apt names for the freeze-time libs (libgthread-2.0.so.0 is in
  libglib2.0-0 on Debian; the krb5 lib is libgssapi-krb5-2; collect-set is
  libgl1/libegl1/libxcb*/...).
  - python3 default per target: Ubuntu 24.04 = 3.12, Debian 13 = 3.13 — both
  already vendored (cp312 + cp313), no extra ABI.
  - lintian is far more lenient than openSUSE rpmlint on a bundled tree; watch
  dpkg-shlibdeps on the private /usr/lib/finbreak (debian/rules already
  excludes it via -Xusr/lib/finbreak).

  Driver: iterate with packaging/obs/obs-submit.sh + obs-status.sh, reading each
  deb build log, exactly as the RPM targets were brought up. See
  packaging/obs/README.md "Still open".
  **Layman:** Get the .deb version of finbreak building on the build service too, so Debian and Ubuntu users get a native package (right now only the openSUSE/Fedora RPMs build; the .deb targets are skipped).
  Kind: package.
  Source: user-request-2026-07-23.
  Progress (2026-08-06): user asked when Debian/xUbuntu would be
  supported, from the OBS Build Results page showing Debian_13 and
  xUbuntu_24.04 both "excluded: 1" while Fedora_44 and
  openSUSE_Tumbleweed succeed. No new information — the two gaps above
  are still exactly right, and packaging/obs/README.md's "Still open"
  already names them. Recorded here only so the question is not
  re-investigated from scratch a third time.

  Sequencing recommendation, NOT yet a user decision: do FIBR-0159
  (Flathub, already 🚧) BEFORE this item. Flathub reaches Debian,
  Ubuntu, Mint, Fedora and openSUSE users through GNOME Software and KDE
  Discover in ONE package, where this item buys two distros for two
  distros' worth of debtransform work plus the per-distro library-name
  shakeout the RPM bring-up needed. Native .deb is still worth having
  for apt users, but it is the narrower win and nothing is blocked on
  it: the AppImage already runs on any modern Linux, so no Debian or
  Ubuntu user is currently without a way to install finbreak.
  Progress (2026-08-31): both deb targets are OFF "excluded" -- Debian_13 and
  xUbuntu_24.04 are building at OBS revision 9. Recipe: packaging/obs/finbreak.dsc
  plus a debian.tar.gz in place of the debian/ directory.

  Gap 2's remedy on this bullet is SUPERSEDED, and measuring is what showed it.
  A `3.0 (quilt)` component orig tarball (finbreak_<ver>.orig-vendor.tar.gz)
  cannot work: debtransform emits exactly one .orig tarball and one .debian.tar
  and REGENERATES the Files/Checksums fields, so a component tarball has no route
  into the source package. What does work is naming vendor.tar.gz in
  DEBTRANSFORM-FILES-TAR beside debian.tar.gz -- dotar_quilt concatenates each
  archive verbatim into the debian tar, and the wheels keep their own vendor/
  prefix. Verified before submitting, by running OBS's own debtransform on a
  dummy tree and then dpkg-source -x on its output inside debian:13-slim:
  exit 0, and vendor/ lands at the source root where debian/rules already looks.
  So debian/rules needed no change at all, and the 321 MB closure is uploaded
  once rather than twice.

  Three things the source settles that recall would not have:
  - debtransform reads a debian.tar[.gz|.bz2|.xz] or loose debian.* files, never
    a directory -- so the debian.obscpio an `osc add debian` produced could never
    have been read. Retired in this revision.
  - DEBTRANSFORM-TAR can be omitted: the FILES-TAR entries are excluded from the
    source-archive candidates, leaving exactly one. So the .dsc carries no
    version-bearing filename.
  - set_version does stamp a .dsc, so Version can be the same `0` placeholder
    finbreak.spec uses. No bump.json entry is owed.

  Also fixed while there: the stale finbreak-0.1.16.tar.gz. Two source tarballs
  are fatal to the deb build (debtransform refuses to choose) and silent on the
  RPM side, which takes Source0 by exact name.

  Not done yet: the per-distro shakeout this bullet predicts is still ahead --
  the builds have not finished.
  Resolved (2026-08-31): all four OBS targets build and publish at revision 15.
  Debian_13 and xUbuntu_24.04 each carry finbreak_0.1.22-1_amd64.deb; Tumbleweed
  and Fedora_44 carry finbreak-0.1.22-7.1.x86_64.rpm. Both deb targets had been
  "excluded" since the project was created.

  Six defects, each hidden behind the one before it. Two were mine from today;
  four were latent from FIBR-0155 and unreachable while the deb targets never
  built:

  1. No .dsc -- the whole reason for "excluded".
  2. vendor/ rejected by 3.0 (quilt): dpkg-buildpackage rebuilds the source
     package first, and the wheels sit outside debian/ and cannot be a patch.
     include-binaries is NOT enough (still "unexpected upstream changes");
     debian/source/options extend-diff-ignore is.
  3. --add-data resolves against --specpath, not the working directory, so
     debian/rules looked under debian/src/. The .spec passes `--specpath .`,
     which is why it never hit this.
  4. dh_dwz rejects the foreign closure outright.
  5. dh_strip on Ubuntu 24.04: its older binutils refuses Pillow's bundled
     libfreetype and pypdfium2's libpdfium where Debian 13's accepts both, so
     Debian went green a revision before Ubuntu.
  6. Mine, twice: a comment placed after a line ending in `&& \` truncates the
     command. The second time INV-10 caught it in 0.10s, where the first had cost
     a 3.5-minute OBS round trip.

  What made this tractable was reproducing the build root locally instead of
  iterating on OBS: debtransform plus dpkg-source in debian:13-slim for the
  source-package half, and a full dpkg-buildpackage in debian:13-slim and
  ubuntu:24.04 for the rest. An ldd sweep over the frozen tree lists ~50 missing
  libraries and is a poor guide -- almost all are optional Qt plugin dependencies
  nothing imports. Running the real freeze named the one that mattered,
  libgssapi-krb5-2, which the .spec's openSUSE branch had carried as `krb5` all
  along.

  Verified beyond "it builds": each .deb installed into a bare container of its
  own distro pulls in only libgl1 and libegl1 -- the host-left pair INV-1
  requires -- and the installed launcher prints FINBREAK_SELFTEST_OK.

  Covered by obs_packaging INV-9 (the .dsc against its siblings, since Format and
  Build-Depends are each stored twice because OBS reads one file and the build
  reads the other) and INV-10 (every debian/rules command parses as make runs
  it). Each leg was verified to go red by breaking its input.

  Not fixed here, filed instead: FIBR-0317 -- nothing re-submits to OBS on
  release, which is why the published packages were six versions behind and why
  the stale wheel closure went unnoticed.

- 🚧 [FIBR-0159] **Publish finbreak to Flathub — the cross-distro app store (GNOME Software / KDE Discover).**
  Flathub is the de-facto cross-distro app store: one submission surfaces finbreak
  in GNOME Software + KDE Discover on openSUSE, Fedora, Ubuntu, Debian, Mint, etc.
  Unlike the official distro archives (which forbid bundling and need a maintainer
  sponsor — impractical for finbreak's deliberately-bundled runtime), Flathub is
  self-publish and embraces the self-contained/sandboxed model, so it fits.
  Design (chosen, docs/specs/FIBR-0159.md — /cold-eyes CONVERGED loop 8, signed off
  2026-07-23; a SEPARATE build pipeline from OBS — flatpak-builder + a manifest, not
  rpm/deb):
  - Build on the freedesktop 25.08 runtime + the pinned pip-wheel closure
  (PySide6==6.11.1 carries its own Qt6) — NOT the PySide6 BaseApp (tops out at
  6.10, forks the pinned stack) and NOT the KDE runtime (no 6.11 branch). The
  manifest io.github.milnet01.finbreak.yaml pip-installs the sha256-pinned
  closure (packaging/flatpak/python3-deps.yaml, generated by
  generate-pip-sources.sh — --prefer-wheels DERIVED from the closure, never
  hand-listed) into /app, then pip-installs finbreak from its git clone.
  - Reuse the existing AppStream metainfo + .desktop + icons shipped under
  packaging/obs/ (single source of truth — installed from the finbreak module's
  own git clone so a standalone-submitted manifest still finds them, ADR-0007).
  - Minimal, network-free, portal-only sandbox: NO --share=network (app networking
  unreachable at the OS level), NO --filesystem=* (import/export go through the
  xdg-desktop-portal chooser, granting only the file the user picks), NO
  --talk-name=*. The updater is inert under Flatpak by construction (no $APPIMAGE
  / not a frozen exe → detect_installer() is None) — no build-time gating needed.
  One small src change: gate _kde_wayland() off under Flatpak so the unreachable
  org.kde.KWin window-centering call is honestly disabled (INV-8).
  - Submit to github.com/flathub/flathub (PR on the new-pr base branch), pass the
  reviewer round, then Flathub builds + hosts it.
  Progress (2026-07-23): spec CONVERGED (cold-eyes loop 8) + signed off; implementation landed — packaging/flatpak/ (manifest, generate-pip-sources.sh, python3-deps.yaml, flatpak-build.sh, README), the _kde_wayland() Flatpak gate (main_window.py, INV-8), security-model.md INV-8 note, and tests/features/flatpak_packaging/ (INV-1..8). Local flatpak-builder build + portal smoke next, then the Flathub new-pr submission.
  Local build VALIDATED (2026-07-23): flatpak-builder builds green offline from the sha256-pinned closure (24 sources, ofxparse the one sdist); `flatpak run --command=finbreak … --self-test` → FINBREAK_SELFTEST_OK (Qt+SQLCipher+qpdf travelled); sandbox network-isolated (in-sandbox connect → OSError, proving no --share=network); full gate green (1258 passed). Two gate fixes folded in: types-PyYAML mypy stubs + a .gitleaks.toml allowlist for the flatpak-builder artifacts (.build/.repo/.flatpak-builder). REMAINING before Flathub submit: (1) manual live-host §5 smoke on KDE-Wayland — portal file open + PDF/.fbk export, Center-window disabled, real screenshot URLs; (2) re-pin the manifest to a release tag/commit (currently v0.1.16); (3) open the flathub/flathub new-pr PR — an outward-facing action, awaiting user go-ahead.
  Decision (2026-07-28, user): KEEP the app id io.github.milnet01.finbreak for
  the Flathub submission — do not switch to the user's own domain
  (antsprojectshub.co.za). Flathub accepts a reverse-DNS id based on a
  code-hosting account you control, 0.1.18 already shipped with this id, and a
  rename would churn the desktop file, icon filenames, metainfo id, the Flatpak
  manifest and the OBS spec while making existing RPM installs look like a
  different app. The domain is still the right HOMEPAGE value in the manifest and
  metainfo — that field is independent of the id. (User data is unaffected either
  way: paths.py keys AppDataLocation on applicationName "finbreak", not the id.)

  Follow-up (optional, lower priority): the Snap Store (Ubuntu-led, also
  self-publish, also appears in the software centres) — a snapcraft.yaml. Do after
  Flathub. Official distro archives are out of scope (bundling policy).
  **Layman:** Get finbreak into the main Linux app store (Flathub), so users on any distro can find and install it from their graphical Software centre with one click — the single biggest reach-the-most-people step.
  Kind: package.
  Lanes: packaging, release.
  Source: user-request-2026-07-23.
  Pre-submit audit (2026-08-07), run against Flathub's CURRENT published
  requirements rather than the spec's 2026-07-23 reading of them. Two
  blockers, two quality nits, one spec gap:

  BLOCKER (RESOLVED same day — see FIBR-0206) — all six metainfo
  `<screenshot>` URLs 404. Flathub's own check fails:
  `flatpak-builder-lint appstream` exits 3 with six
  `screenshot-image-not-found`, and `appstreamcli validate` agrees.
  Docs list invalid screenshots as a submission-blocking error.

  CORRECTION to this note as first written: it blamed an unfinished
  FIBR-0155 "upload real PNGs" TODO and said the images "were never
  uploaded". That was wrong, and FIBR-0206 had already established
  the real cause on 2026-08-02 — the images have been published the
  whole time; the metainfo simply guessed the hosted path from the
  in-repo basenames. The site serves `/assets/img/shots/` with a
  `finbreak-` prefix, so both the directory and the name differ. A
  six-line URL correction fixed it; nothing needed uploading. Filing
  a finding without first checking whether the roadmap already
  carried its diagnosis is what produced the wrong cause here.

  BLOCKER (RESOLVED same day — see FIBR-0256) — the cryptography
  closure drift.

  NIT — screenshots are 1600x1000. The quality guidelines want
  <=1000x700, or 2000x1400 for HiDPI; 1600x1000 is neither. Re-capture
  at 2000x1400 while uploading.

  NIT — `<summary>` is 55 chars ("Understand your personal finances,
  privately and offline"). Guideline: <=35, ideally 10-25. `<name>`
  "finbreak" is all-lowercase, which the guidelines also discourage,
  but it is the brand and is defensible as-is.

  SPEC GAP — neither § 5's checklist nor packaging/flatpak/README.md
  mentions `flatpak-builder-lint`, which Flathub docs tell submitters
  to run locally and whose failures block the PR. The manifest check
  passes today (exit 0); the appstream check is what fails. § 5 also
  says to build with the host `flatpak-builder` (flatpak-build.sh line
  53), where Flathub asks for the `org.flatpak.Builder` flatpak —
  already installed on this host. Fold both into the checklist.

  VERIFIED GOOD — runtime branch `25.08` is still current and
  installable (freedesktop-sdk-25.08.15); the manifest is correctly
  re-pinned to v0.1.19 / f4de4c4 (the roadmap's older "currently
  v0.1.16" remark is stale); the app id decision stands unchanged.

  STILL OPEN, unchanged — the binary-wheel reviewer risk § 5 already
  records. Research found no published Flathub policy blessing
  pre-built manylinux wheels, and the one on-point Flathub Discourse
  thread about a PySide6 app had a maintainer recommending a
  from-source PySide6 build instead. That is a data point, not a
  ruling, and the same thread's advice was "just create the submit PR,
  it will be reviewed there".
  Re-validated (2026-08-07) after the FIBR-0256 closure regenerate, on a
  real KDE-Wayland host. This supersedes the 2026-07-23 "local build
  VALIDATED" note, which predated the cryptography bump.

  * `flatpak-builder` builds green OFFLINE from the regenerated
  sha256-pinned closure, and `--self-test` prints FINBREAK_SELFTEST_OK
  (Qt + SQLCipher + qpdf travelled).
  * The CVE fix actually reaches the bundle, not just the manifest:
  `python3 -c "import cryptography; print(cryptography.__version__)"`
  INSIDE the built flatpak prints **50.0.0**.
  * Sandbox is network-isolated — an in-sandbox `socket.create_connection`
  to 1.1.1.1:443 raises `OSError: [Errno 101] Network is unreachable`,
  proving no `--share=network`.
  * Updater inert at runtime, not merely under a monkeypatched test:
  `/.flatpak-info` exists, `FLATPAK_ID` is set, and
  `detect_installer()` returns `None` (INV-6).
  * INV-8 verified where it actually matters: `_kde_wayland()` returns
  **False** inside the flatpak on a session that genuinely IS KDE
  Wayland (`XDG_SESSION_TYPE=wayland`, `XDG_CURRENT_DESKTOP=KDE`), so
  the unreachable org.kde.KWin call is honestly suppressed.
  * `flatpak-builder-lint manifest` exits 0; `... appstream` exits 0
  after the FIBR-0206 URL fix.

  `flatpak-builder-lint repo` reports two errors —
  `appstream-screenshots-not-mirrored-in-ostree` and
  `appstream-external-screenshot-url`. Checked against Flathub's linter
  docs rather than assumed: both are EXPECTED on a local build, because
  mirroring happens when the builder is invoked with
  `--mirror-screenshots-url=https://dl.flathub.org/media`, which
  Flathub's own infrastructure supplies. They would only be the
  submitter's problem for an externally-uploaded app, which this is not.

  STILL NEEDS A HUMAN — the two portal checks in § 5, which are the
  gate for § 3.5's two risks and cannot be driven headlessly: (i) import
  a file through the chooser, and (ii) export a PDF report and an
  encrypted .fbk to a chosen location. The app is installed
  (`flatpak run io.github.milnet01.finbreak`) and ready for that pass.
  Progress (2026-08-12): the launch blocker is CLEARED — FIBR-0259 is ✅. Between the 2026-08-07 re-validation above and today the app could not start at all under Flatpak (missing Kerberos library, ImportError before any window), which is what the user's § 5 portal attempt actually hit. The krb5 manifest module fixed it and the user confirmed a real launch today: window, full toolbar, "Ready", unlock dialog. So this bullet's closing line — "the app is installed and ready for that pass" — is true again, but it was NOT true for the five days in between; do not read that line as continuously verified. Two corrections to the notes above, both checked in the tree rather than recalled: the manifest is now pinned to tag v0.1.20 / commit 6c9cf8c (line 104-106), superseding both the "currently v0.1.16" and the "v0.1.19 / f4de4c4" remarks; and the FIBR-0259 fix also widened `--self-test` to import PySide6.QtNetwork and construct a QLocalServer, closing the gate hole that let a non-starting build pass every automated check. REMAINING, unchanged: (1) the two human portal checks in § 5 — import through the chooser, and export a PDF report + an encrypted .fbk to a chosen location; (2) re-pin to the newest release if one is cut before submission; (3) open the flathub/flathub new-pr PR, an outward-facing action still awaiting the user's explicit go-ahead.
  Progress (2026-08-12): the manifest now builds green AS SUBMITTED. `LOCAL=0 packaging/flatpak/flatpak-build.sh` — no source substitution, so the finbreak module is built from the pinned v0.1.20 / 6c9cf8c clone, offline — installs the whole closure (cryptography-50.0.0) plus finbreak-0.1.20 and ends FINBREAK_SELFTEST_OK. That clears the last two automated blockers this bullet inherited: FIBR-0257 (the CVE fix had never shipped) and FIBR-0256 (the closure still offered cryptography 49.0.0) were both already fixed by the v0.1.20 release and are now flipped ✅ on evidence rather than on inference. FIBR-0258 is closed with them: `LOCAL=0` is documented as the pre-submit path in packaging/flatpak/README.md, and `test_FIBR0258_closure_satisfies_the_pinned_commit` now checks the closure against the pyproject of the commit the MANIFEST pins, not the working tree's. REMAINING is unchanged and is all human or outward-facing: (1) the two § 5 portal checks — import through the chooser, and export a PDF report + an encrypted .fbk to a chosen location; (2) re-pin if a newer release is cut first; (3) open the flathub/flathub new-pr PR, still awaiting explicit go-ahead.
  Progress (2026-08-20): the manual § 5 live-host smoke is DONE and all five
  checks pass, on KDE-Wayland, against a LOCAL=0 build -- the manifest as
  submitted, from the pinned v0.1.22 commit (624722d, verified equal to the
  tag), built offline. Self-test printed FINBREAK_SELFTEST_OK, so Qt +
  SQLCipher + qpdf all travelled into the sandbox.

  (1) Portal open: a CSV in $HOME -- which the sandbox has no filesystem
  right to read -- was chosen through the xdg-desktop-portal chooser and
  fully parsed: 10 rows, ISO dates read correctly, coverage period inferred
  (2026/07/02..2026/07/28), dedup ran (0 duplicate). One row errored, and
  correctly: a 0.00 opening-balance line the tester had put in the sample,
  refused by transactions.py:92 "amount must be non-zero" and surfaced as a
  per-row error while the other 9 imported (the FIBR-0252 model).

  (2) Portal save, both output types, each to a chosen location. The PDF is
  73,665 bytes, valid PDF 1.4, 2 pages, correct %PDF- header and %%EOF
  trailer -- complete, not truncated. The .fbk is 90,698 bytes and grepping
  it for the transaction descriptions returns ZERO hits, so the payload is
  genuinely encrypted rather than a zip of readable data.

  (3) Updater inert: Help -> Check for updates shows "Automatic updates
  aren't available for this build of finbreak." That is the
  _installer is None early return at main_window.py:1342, which returns
  BEFORE any worker starts -- so no network attempt is made at all, rather
  than one being made and failing. Screenshot-confirmed wording.

  (4) INV-8 holds: Window -> Center window is greyed out (the unreachable
  org.kde.KWin call honestly disabled, not a dead click) and Reset layout
  works normally.

  (5) Network isolation proven at the OS level, and proven properly: a
  hostname connect fails with gaierror, which alone would only show there is
  no resolver, so it was re-tested by raw IP -- 1.1.1.1:443 and
  140.82.121.6:443 both return OSError [Errno 101] Network is unreachable.
  No --share=network, confirmed empirically.

  REMAINING is now exactly one thing, and it is outward-facing: open the
  flathub/flathub new-pr PR. The re-pin blocker is closed (the manifest
  already points at v0.1.22, the current release) and the § 5 blocker is
  closed by this run. Awaiting explicit user go-ahead for the submission.
  CORRECTION (2026-08-20): "open the flathub/flathub new-pr PR" has been
  stale since 2026-08-07. The PR EXISTS -- flathub/flathub#9662, "Add
  io.github.milnet01.finbreak", base new-pr -- and it is CLOSED, not merged.
  Every REMAINING list on this bullet above still describes it as un-opened;
  they are wrong from this date.

  What happened: the submission-checker bot auto-closed it 27 SECONDS after
  it opened (13:14:46Z -> 13:15:13Z), diagnostics "Checklist(s) not completed
  or missing" -- the PR body had replaced the submission template instead of
  filling it in. At 15:20:56Z the submitter posted a comment completing the
  full checklist (description, showcase video, sandbox justification, the
  manylinux-wheel rationale) and asked for a reopen, which is precisely what
  the bot's own message instructs: "please post a comment below instead of
  opening or reopening (new) PRs". Since then: 13 days, two comments total,
  no labels, no maintainer response, still closed.

  So the next action is NOT to open a PR. Doing so contradicts the bot's
  stated process and reads as PR-spam to the reviewers. The sanctioned route
  is a follow-up comment on 9662.

  Also live: the fork branch milnet01/flathub add-io.github.milnet01.finbreak
  (head 0b42569, 2 commits -- the add plus "Bundle MIT krb5 -- Qt6Network
  needs libgssapi_krb5") still pins tag v0.1.20 / 6c9cf8c. Current release is
  v0.1.22 / 624722d, so a reopened 9662 would build a two-release-old
  finbreak. Re-pinning that branch is a prerequisite to any bump comment.

  Pre-submit checks re-run today and all green against v0.1.22:
  flatpak-builder-lint manifest exit 0 (also exit 0 standalone, i.e. with the
  manifest at a repo root and no packaging/obs beside it), flatpak-builder-lint
  appstream exit 0 (that one really does fetch the <screenshot> URLs),
  org.freedesktop.Platform//25.08 current at freedesktop-sdk-25.08.16
  (2026-08-16), tests/features/flatpak_packaging 17/17 including the
  FIBR-0258 closure-vs-pinned-commit check.

  One deliberate NON-change: regenerating python3-deps.yaml today pulls
  lxml 6.1.1->6.1.2, charset_normalizer 3.4.9->3.5.1 and pypdfium2
  5.12.1->5.13.0. That is upstream drift, NOT a pyproject mismatch -- the
  committed closure still satisfies the pinned commit. It was reverted rather
  than submitted, because those three wheels have never been built here and
  "builds entirely from pinned source" is the first thing a Flathub reviewer
  checks. The bump belongs in the ongoing-releases flow, not inside a
  submission.
  Progress (2026-08-20, user go-ahead): both sanctioned steps DONE. The
  submission is now waiting on Flathub, not on us.

  (1) Fork branch milnet01/flathub add-io.github.milnet01.finbreak re-pinned
  to v0.1.22 / 624722d, pushed as a FAST-FORWARD on top of the existing head
  (0b42569 -> 278759c) rather than a force-push -- so the branch's second
  commit, "Bundle MIT krb5 -- Qt6Network needs libgssapi_krb5", is preserved.
  Verified that fix is already present in this repo's own manifest, so the
  re-pin is a 2-line diff (tag + commit) and regresses nothing. Remote head
  confirmed 278759c after the push.

  (2) Follow-up comment posted on flathub/flathub#9662
  (issuecomment-5352889722) -- a comment, per the submission-checker bot's own
  instruction not to open or reopen a PR. It notes the checklist was completed
  in the 2026-08-07 comment, states the new pin, lists today's green checks
  (both linters exit 0, runtime 25.08 current, offline build ending
  FINBREAK_SELFTEST_OK), and repeats the standing offer to build any manylinux
  wheel from source. Confirmed as the thread's third comment.

  PR state is still CLOSED and only a Flathub maintainer can change that. So
  the next action on this bullet is NOT ours: it is waiting for a reopen. Do
  not open a new PR while 9662 stands -- that is what the bot forbids and it
  reads as PR-spam to the reviewers.

  If the silence continues, the escalation is Flathub's Matrix room or
  Discourse rather than a second PR. Give the bump a reasonable window first;
  the previous wait was 13 days with no response.

- 📋 [FIBR-0160] **Add openSUSE Leap 15.6 as an OBS target (deferred — Leap ships no python 3.12+).**
  Attempted 2026-07-23: added the Leap 15.6 target + a %if 0%{?sle_version}
  python313 build branch, but the build went "unresolvable" — osc buildinfo:
  "nothing provides python313, python313-devel, python313-pip". Leap 15.6 (SLE 15
  SP6) has no python313 (nor 3.12/3.14); we vendor only cp312/cp313/cp314. The Leap
  target was removed to keep the project clean; the spec keeps the %{py3}/%{py3pkg}
  abstraction (harmless — resolves to python3 on every active target).

  To enable later:
  1. Confirm Leap 15.6's newest python3XX module (`osc buildinfo` against
  openSUSE:Leap:15.6, or the Leap package index) — likely python311 (3.11).
  2. Vendor that ABI (add it to vendor-wheels.sh's PY loop) — all deps must
  publish that cpXX wheel (PySide6/cryptography are abi3 so fine; check
  sqlcipher3-wheels, lxml, pikepdf, Pillow, cffi, charset-normalizer).
  3. Set the sle_version branch's %{py3pkg} to that module (e.g. python311) and
  %{py3} to its interpreter (python3.11).
  4. Re-add the openSUSE_Leap_15.6 repo (obs-setup.sh) + rebuild.

  Lower priority than FIBR-0159 (Flathub), which serves Leap users through GNOME
  Software / KDE Discover regardless.
  **Layman:** Offer a native openSUSE Leap package too. Parked for now: Leap's software repos don't carry a new-enough Python to match our bundled parts, and Flathub will reach Leap users in the meantime.
  Kind: package.
  Source: user-request-2026-07-23.

- 📋 [FIBR-0161] **Fold the Flathub `flathub.json` arch-restriction into the FIBR-0159 spec §5 checklist.**
  During FIBR-0159 submission prep we found the pinned wheel closure is
  x86_64-only, but Flathub's buildbot builds every arch by default — so the
  submission needs a `flathub.json` with `only-arches: [x86_64]` or the aarch64
  build fails. Implemented in packaging (packaging/flatpak/flathub.json + INV-9
  test locking only-arches to the closure's wheel arches), but the signed-off
  FIBR-0159 spec §3.4/§5 pre-submit checklist never mentions it. Fold in an arch
  line — but the spec is a design doc, so the edit runs through /cold-eyes
  (--max-loops 7, CLAUDE.md rule 14) rather than an inline patch.
  **Layman:** The Flathub packaging now ships a small config that tells Flathub to build only for the PC (x86_64) chip we have the parts for; the design document should mention it.
  Kind: doc-fix.
  Source: in-session-2026-07-23.
  Scope grew (2026-08-07): three more items to fold into § 5 in the same
  edit, all verified against Flathub's live docs and by running the tools.
  Batching them is deliberate — editing a spec trips the rule-14
  `/cold-eyes` gate, so one amendment plus one review beats four.

  1. `flatpak-builder-lint`. Flathub's docs tell submitters to run it
  locally and its failures block the PR, yet neither § 5 nor
  packaging/flatpak/README.md mentioned it. Two build-free checks:
  `flatpak run --command=flatpak-builder-lint org.flatpak.Builder
  manifest <manifest>` and `... appstream <metainfo>`; `... repo repo`
  after a build. The manifest check already passes clean (exit 0).
  Its `appstream` check is `appstreamcli` plus Flathub's own
  overrides, so it outranks a bare `appstreamcli validate`.
  2. Build via the `org.flatpak.Builder` flatpak, which is what Flathub's
  infra runs; flatpak-build.sh line 53 uses a host `flatpak-builder`.
  Fine for local iteration, worth naming as a difference.
  3. The closure-vs-pyproject comparison is in § 5 as a MANUAL step and
  that is exactly what failed (FIBR-0256). It now has a gate-runnable
  test, so § 5 should cite the test rather than ask for the manual
  diff.

  Also for § 5: the exit criteria say `appstreamcli validate`, but the
  gate's own INV-4/INV-5 invoke it with `--no-net`, which skips the
  `<screenshot>` fetch entirely — the flag that let six dead URLs sit
  under a green gate for months. § 5 should say plainly that the
  pre-submit run is the networked one.

  Already recorded on the FIBR-0159 bullet, no § 5 change needed: the
  runtime branch 25.08 is current (freedesktop-sdk-25.08.15) and the
  manifest is correctly pinned to v0.1.19.

- 📋 [FIBR-0184] **bump.json's Flatpak re-pin todo names a tagging step the release path doesn't use, so `git rev-parse v<NEW>` fails locally.**
  Hit during the v0.1.18 release. The `.claude/bump.json` todo for the
  Flatpak `commit:` pin says to set it "AFTER `git tag -a v{NEW}`" — but
  nothing in the release path runs `git tag -a`. `scripts/release-linux.sh`
  creates the tag through `gh release create`, which creates it on the
  REMOTE only. So the local clone has no such ref and the todo's own
  follow-up command fails:

  $ git rev-parse v0.1.18^{commit}
  fatal: ambiguous argument 'v0.1.18^{commit}': unknown revision ...

  The fix is a `git fetch --tags origin` before the rev-parse (that is what
  unblocked it here). Two candidate homes, either is fine:
  (a) reword the bump.json todo to name the real sequence — run
  release-linux.sh, `git fetch --tags`, then rev-parse; or
  (b) better, fold the whole step into release-linux.sh after the release is
  created, since the sha is known there and the manual step exists only
  because the tag does not exist at bump time. (b) removes the todo
  entirely rather than correcting it.

  Low severity — it costs one confusing failure per release, and the
  flatpak_packaging tests (INV-4 40-hex sha, INV-10 tag == __version__)
  still pass either way because they cannot tell whether the tag and the
  commit point at the same object. That blind spot is the reason this is a
  manual step at all, so a wrong instruction here is worth fixing.
  **Layman:** A release checklist step tells you to look up something that isn't on your computer yet, so it fails until you fetch it first.
  Kind: doc-fix.
  Source: in-session-2026-07-28 (v0.1.18 release).

- ✅ [FIBR-0188] **The AppImage's embedded .desktop name doesn't match the app id, so the panel shows a second icon.**
  Verified 2026-07-28 by source read (user screenshot shows the duplicate).
  Resolved (2026-07-28): SHIPPED. Two new build vars — APP_ID (the .desktop basename AND the bundled icon name, which appimagetool requires to match Icon=) and APP_WM_CLASS (the X11 half, from applicationName(), the bare "finbreak") — both defaulting to $ONEFILE so the self-test stub is byte-identical. Also corrected the app.py comment that ASSERTED the AppImage already shipped a reverse-DNS .desktop; it never did, and that unverified claim is why the mismatch survived. Tests derive expectations FROM app.py, so a future app_id change fails the test rather than silently desyncing the launcher. Source-scan only — the grouping is empirical and proves out on the NEXT release's AppImage, not the published 0.1.18 one. Gate: 1403 passed.

  The mismatch, exactly:
  - src/finbreak/app.py:48 calls
  QGuiApplication.setDesktopFileName("io.github.milnet01.finbreak"), so the
  window announces that app id (Wayland app_id / the desktop-entry association
  key).
  - scripts/_build-smoke-in-container.sh:169 writes the AppImage's embedded
  launcher as "$ONEFILE.desktop" = finbreak.desktop, with Icon=$ONEFILE and NO
  StartupWMClass line at all.

  So a compositor/panel resolving the window's app id looks for
  io.github.milnet01.finbreak.desktop and finds finbreak.desktop instead. No
  match, so the running window cannot be grouped with its launcher and appears as
  a second, separate panel entry. On X11 the same gap shows up differently: the
  xcb backend derives WM_CLASS from applicationName() ("finbreak"), and with no
  StartupWMClass key the association rests on the basename coincidence alone.

  NOT a bug in the RPM/deb path: packaging/obs/io.github.milnet01.finbreak.desktop
  is already named for the app id AND carries StartupWMClass=finbreak, which is
  the pairing this item brings to the AppImage.

  Fix: name the embedded file for the app id and add the X11 key — i.e. an APP_ID
  variable (defaulting to $ONEFILE so the self-test smoke stub is unchanged, with
  the release build exporting io.github.milnet01.finbreak), write
  "$APP_ID.desktop", add StartupWMClass=$ONEFILE, and rename the bundled icon to
  $APP_ID.png with Icon=$APP_ID so it keeps matching (appimagetool requires the
  icon to match the Icon= key). Mirrors the obs/ launcher exactly.

  Verify: this cannot be proven by a source-scan alone. Build the AppImage
  (scripts/build-release-appimage.sh), run it, and confirm with
  `xprop WM_CLASS` (X11) or the panel grouping (Wayland) that one icon appears.
  A test can pin the generated .desktop's basename + keys; the grouping itself is
  empirical, like the FIBR-0131 PowerShell legs.
  **Layman:** Running the AppImage puts a duplicate finbreak icon in the taskbar instead of lighting up the one you pinned.
  Kind: fix.
  Source: user-request-2026-07-28 (screenshot: duplicate panel icon).

- ✅ [FIBR-0206] **AppStream metainfo points at six screenshots that 404 — appstreamcli validate fails.**
  Found while validating the metainfo during the v0.1.19 bump.
  `appstreamcli validate packaging/obs/io.github.milnet01.finbreak.metainfo.xml`
  exits non-zero: `✘ Validation failed: warnings: 6`, all six
  `screenshot-image-not-found`.

  Verified live 2026-08-02, not inferred from the validator — every URL was
  fetched and all six return **HTTP 404**:
  `https://antsprojectshub.co.za/img/finbreak/{dashboard,transactions,categories,recurring,transfers,rules}.png`

  Pre-existing, and NOT caused by the v0.1.19 metainfo edit (that only
  prepended a `<release>` block; the warnings are all on `<screenshot>`
  elements). The file's own header comment at `:5` names `appstreamcli
  validate` as the check, so the intended gate exists and is red.

  Why it matters rather than being cosmetic: this is the file GNOME
  Software and KDE Discover read. A listing whose screenshot URLs 404
  renders with **no screenshots at all** — the single biggest thing a
  store page uses to sell an app. It also bears on **FIBR-0159** (Flathub,
  🚧): Flathub's submission CI runs `appstreamcli validate`, so this is
  plausibly a submission blocker, not just a wart. Worth confirming what
  severity Flathub gates on before assuming it passes.

  The assets themselves exist in-repo (`assets/` holds the README
  screenshots, refreshed for FIBR-0113 on 2026-07-30) — so this is a
  publish-and-point problem, not a capture problem. Two candidate fixes:
  upload the six PNGs to the antsprojectshub.co.za path already
  referenced (the download page repo is `milnet01/antsprojectshub`,
  `build.mjs` → `dist`), or re-point `<screenshot>` at raw
  `github.com/milnet01/finbreak` URLs, which need no second repo to stay
  in sync. Note the two surfaces have drifted before, so whichever is
  chosen wants a check that keeps them together.
  **Layman:** The Linux app-store listing links six screenshots that aren't actually online, so the listing would show none.
  Kind: fix.
  Lanes: release, docs.
  Source: in-session-2026-08-02 v0.1.19 release.
  Progress (2026-08-02): root cause narrowed, and it is NOT a missing
  upload — the images are published and live. The metainfo simply has the
  wrong path shape.

  The site repo (`milnet01/antsprojectshub`) holds all six at
  `src/assets/img/shots/finbreak-<name>.png`, and its build serves them at
  `/assets/img/shots/`, not `/img/finbreak/`. All six verified live
  2026-08-02 — `https://antsprojectshub.co.za/assets/img/shots/finbreak-{dashboard,transactions,categories,recurring,transfers,rules}.png`
  each return **HTTP 200**, while the two shapes the metainfo could have
  meant (`/img/finbreak/<name>.png` and `/img/shots/finbreak-<name>.png`)
  both 404.

  So the fix is a six-line URL correction in
  `packaging/obs/io.github.milnet01.finbreak.metainfo.xml`, mapping
  `/img/finbreak/<name>.png` → `/assets/img/shots/finbreak-<name>.png`.
  Note the basename gains the `finbreak-` prefix as well as the path
  change, so a path-only sed will still 404.

  Deliberately NOT fixed in this session: it is outside the v0.1.19 release
  scope this session was asked for, and the release does not depend on it.
  The remaining open question is unchanged — whether to point at the site
  (one more place to keep in sync when screenshots are refreshed) or at raw
  `github.com/milnet01/finbreak` URLs, which need no second repo. Whichever
  is chosen, verify with `appstreamcli validate` afterwards; that is the
  check that is currently red.
  Resolved (2026-08-07): took the second of the two candidate fixes this
  bullet already identified — the six-line URL correction, mapping
  `/img/finbreak/<name>.png` → `/assets/img/shots/finbreak-<name>.png`.
  No upload was needed; the 2026-08-02 progress note had the diagnosis
  exactly right.

  Verified three ways: `appstreamcli validate` exits 0 (it fetches every
  URL), Flathub's own `flatpak-builder-lint appstream` exits 0 where it
  previously exited 3, and all six URLs were fetched directly — HTTP 200,
  1600x1000 each.

  This bullet asked for "a check that keeps them together", so one was
  added: `test_FIBR0206_metainfo_screenshot_urls_use_the_hosted_path_shape`
  in tests/features/obs_packaging/. It pins the URL *shape* rather than
  reachability, deliberately — the gate must not depend on the network.
  Proven non-vacuous by restoring one old URL and watching it redden.

  Root cause worth keeping: INV-4 already ran `appstreamcli validate`, but
  with `--no-net`, and that flag is exactly what hid this. Without the
  network the validator never fetches an `<image>`, so six dead URLs sat
  under a green gate for months. The lesson generalises past screenshots —
  a validator invoked with its expensive checks disabled is a gate that
  reports on something narrower than its name suggests.

  Two docs asserting a 1:1 in-repo → hosted name mapping (which was never
  true — the hosted names carry a `finbreak-` prefix) corrected in the same
  commit: scripts/capture_screenshots.py and assets/screenshots/README.md.

- 📋 [FIBR-0208] **The AppImage's bundled libxkbcommon segfaults on X11 keymap data it can't parse.**
  Found 2026-08-02 while probing FIBR-0200 in a throwaway environment; it
  is the app-side finding of that probe, not the probe's own fault.

  `dist/finbreak-0.1.19-x86_64.AppImage` SIGSEGVs against a plain X server
  (Xvfb), coredump frame #0 inside the BUNDLED `libxkbcommon.so.0`
  (`+0x1d9b8`). It dies at startup or on the first keystroke, and loading a
  keymap first (`setxkbmap us`) does not help. Forcing the system copy —
  `LD_PRELOAD=/usr/lib64/libxkbcommon.so.0` — makes the SAME AppImage run
  to completion: unlock, every tab, clean quit. So the bundled library is
  what fails, not the app.

  Not exotic-display-only. On the maintainer's own desktop the same bundled
  copy logs, on every launch,
  `xkbcommon: ERROR: /usr/share/X11/locale/en_US.UTF-8/Compose:1661:1:
  unrecognized keysym "dead_hamza"` (repeated down the Compose file)
  against the system's newer `xkeyboard-config` data — the same version
  skew, milder symptom, already visible in the journal today.

  Risk: this library ships to every Linux user of the AppImage, and a
  distro whose X11 locale data is newer than the bundled parser expects
  gets a noisy log at best and the reproduced segfault at worst.

  Provenance not yet pinned: the copy is either PySide6's wheel bundle or
  the `python:3.12-slim-bookworm` build container's system library (Debian
  12 is older than most target desktops). Establishing which comes first —
  the fix is then to exclude it from the freeze so the host copy is used,
  or to build against newer keyboard data.
  **Layman:** The app carries its own copy of a keyboard-layout library that is older than the system's keyboard data — it crashed in testing.
  Kind: fix.
  Source: in-session-2026-08-02 FIBR-0200 pre-check.

- ✅ [FIBR-0256] **Flatpak dependency closure drifted off pyproject.toml and still carries the pre-CVE cryptography.**
  `pyproject.toml` pins `cryptography==50.0.0` — bumped by FIBR-0221 for
  CVE-2026-69247 — but `packaging/flatpak/python3-deps.yaml` still pins
  `cryptography-49.0.0`. The closure was generated once at `dab5fe4`
  (2026-07-23) and never regenerated, though
  `generate-pip-sources.sh`'s own header says to re-run it on exactly
  this trigger ("a new/bumped runtime dep in pyproject.toml").

  Not yet user-affecting: the Flatpak is unpublished. But it blocks the
  Flathub submission, and it fails closed rather than silently — the
  manifest's finbreak module runs `pip3 install --no-index` (offline), so
  a closure providing 49.0.0 against a `==50.0.0` requirement cannot
  resolve. The 2026-07-23 "local build VALIDATED" note predates the bump
  and no longer describes a build that would pass.

  Every other pyproject pin still matches the closure; cryptography is
  the only drift.

  Fix has two halves:
  1. Re-run `packaging/flatpak/generate-pip-sources.sh` and commit the
  regenerated `python3-deps.yaml`, then re-validate the offline
  build.
  2. Close the gap that let it drift. FIBR-0159 § 5 lists "the
  generated sha256 pins match the current pyproject.toml pins" as a
  MANUAL pre-submit step and its own § 4 calls this an INV-3/INV-7
  coverage gap — a manual step is what failed here. A cheap
  gate-runnable test comparing the `[project.dependencies]` pins
  against the versions in `python3-deps.yaml` would have caught it
  the moment FIBR-0221 landed. `tests/features/flatpak_packaging/`
  already exists to host it.
  **Layman:** The Linux app-store build was still set to use an old version of a security library that we already replaced everywhere else — found before it ever shipped.
  Kind: security.
  Lanes: packaging, security.
  Source: in-session-2026-08-07 (FIBR-0159 pre-submit audit).
  Resolved (2026-08-12) — verified already fixed, not newly fixed. `python3-deps.yaml` now pins cryptography 50.0.0, matching `pyproject.toml`; the closure was regenerated when v0.1.20 was cut. Proof is an offline LOCAL=0 build of the submission manifest: `Successfully installed ... cryptography-50.0.0`, then `finbreak-0.1.20`, ending FINBREAK_SELFTEST_OK. The gate-runnable check this bullet asked for (half 2) exists as `test_FIBR0256_every_pinned_dep_matches_the_closure`. The bullet was stale, not open.

- ✅ [FIBR-0258] **flatpak-build.sh never builds what gets submitted, so the submission config goes unvalidated.**
  `flatpak-build.sh` rewrites the finbreak module's source to
  `file://$REPO @ HEAD` before building (its "LOCAL build" branch). Handy
  for iterating, but it means a green local build says nothing about the
  manifest that would be submitted, which pins a release tag.

  That is precisely how FIBR-0257 hid: the local build was green all
  along because HEAD's pyproject matches the regenerated closure, while
  the same manifest built unsubstituted fails outright at the pinned tag.
  The gap is invisible — both runs print the same success lines.

  Two halves:
  1. Give the script a mode that builds the manifest AS SUBMITTED (no
  source substitution) and make that the pre-submit path. The
  § 5 checklist should name it, since "flatpak-builder builds green"
  currently passes without exercising the submitted config at all.
  2. `test_FIBR0256_every_pinned_dep_matches_the_closure` compares the
  closure against HEAD's pyproject, which is right for the local
  build and wrong for the submission. The invariant that actually
  matters is that the closure satisfies the pyproject of the commit
  the manifest PINS. Extend it to read that commit's pyproject via
  git, skipping when the checkout is not a git repo — HEAD and the
  pinned tag agreeing is the real precondition for submitting.
  **Layman:** Our local test of the Linux app-store package quietly tests a different version than the one we would actually submit, so a broken submission can look fine.
  Kind: test.
  Lanes: packaging, testing.
  Source: in-session-2026-08-07 (FIBR-0159 submission-manifest build).
  Resolved (2026-08-12), and the headline overstated the defect: `flatpak-build.sh` could always build the submission manifest — `LOCAL=0` skips the source substitution (lines 30-50) — but nothing outside a code comment named it, so the pre-submit path in practice was the LOCAL=1 build that proves nothing. Half 1: `packaging/flatpak/README.md` now documents `LOCAL=0` in the build section and as pre-submit step 2, with the FIBR-0257 example of why a green default build is not evidence. Half 2: `test_FIBR0258_closure_satisfies_the_pinned_commit` reads the pyproject of the commit the MANIFEST pins (`git cat-file`) and checks the closure satisfies it — skipping when git or the object is absent, and asserting it read a real pyproject first so it cannot pass vacuously.

- ✅ [FIBR-0259] **The Flatpak build cannot launch — libQt6Network needs a Kerberos library the freedesktop runtime does not ship.**
  `flatpak run io.github.milnet01.finbreak` dies before any window:
  `ImportError: libgssapi_krb5.so.2: cannot open shared object file`,
  raised from `app.py`'s `from PySide6.QtNetwork import QLocalServer`.

  Verified, not inferred: `ldd` on the bundled
  `PySide6/Qt/lib/libQt6Network.so.6` reports `libgssapi_krb5.so.2 => not
  found`, and a `find /` inside the sandbox returns nothing for
  `libgssapi*` or `libkrb5*`. Neither `org.freedesktop.Platform//25.08`
  nor its Sdk ships it. A known PySide6-on-freedesktop-runtime problem;
  the accepted fix is to build MIT krb5 as a manifest module.

  **Why every gate missed it — the real lesson.** The FIBR-0003
  `--self-test` sentinel is what "the native stack travelled" rests on,
  and it loads QtWidgets, QtCharts, QtCore, QtGui, sqlcipher3 and pikepdf
  — but NOT QtNetwork. So it printed FINBREAK_SELFTEST_OK against a build
  that could not start. Every automated check agreed the Flatpak was
  good: gate green, manifest lint 0, appstream lint 0, offline build
  clean, standalone build clean. A human launching the app found it in
  one command. The self-test's import list is a hand-maintained subset of
  what the app actually imports, and nothing keeps the two in step.

  Scope note: finbreak uses QtNetwork ONLY for the single-instance guard
  (`QLocalServer`/`QLocalSocket` in `single_instance.py` and `app.py`) —
  never for networking, which the sandbox blocks outright. So Kerberos is
  pulled in for a library the app never functionally uses. Bundling krb5
  is the standard, low-risk route and is what is being done; dropping the
  QtNetwork dependency by reimplementing the guard on a lock file is the
  smaller-surface alternative, worth considering separately rather than
  under submission pressure.

  Blocks FIBR-0159 — do not submit until the app launches.
  **Layman:** The Linux app-store build was missing a system library and would not start at all; the self-check we relied on could not see the problem.
  Kind: fix.
  Lanes: packaging, testing.
  Source: in-session-2026-08-07 (user ran the FIBR-0159 § 5 portal smoke test).
  Progress (2026-08-12): the fix is BUILT and gated; what remains is a human launching it. Verified in the tree, not recalled: packaging/flatpak/io.github.milnet01.finbreak.yaml carries a `krb5` module (line 59, krb5-1.22.2 from kerberos.org), and src/finbreak/_selftest.py now imports PySide6.QtNetwork and constructs a QLocalServer — so the gate hole that let this ship (the self-test loaded QtWidgets/QtCharts/QtCore/QtGui/sqlcipher3/pikepdf but never QtNetwork) is closed and would now fail on a build that cannot start. Landed in 51fd6a8 + baf48b8; FIBR-0261 then made that self-test run headless instead of aborting. Deliberately left 🚧 rather than ✅: every automated check agreed the build was good LAST time too, and only a human running `flatpak run io.github.milnet01.finbreak` found it. The single remaining step is that command producing a window. Still blocks FIBR-0159 — do not submit until it does.
  Resolved (2026-08-12): the user ran `flatpak run io.github.milnet01.finbreak` and the app launched — window titled "finbreak" with the full toolbar (Home … Lock), status bar reading "Ready", and the "Unlock finbreak" master-password dialog. Screenshot supplied in-session. That is the exact exit condition this bullet held itself to, and it is the one check no automated gate could stand in for: the old failure was an ImportError raised before any window existed, so a window at all disproves it. The krb5 manifest module (packaging/flatpak/io.github.milnet01.finbreak.yaml) and the widened `--self-test` (now importing PySide6.QtNetwork and constructing a QLocalServer) are both confirmed good by a real launch rather than by the checks that agreed last time. No longer blocks FIBR-0159 — Flathub submission is clear to proceed.

- 📋 [FIBR-0298] **Nothing owns refreshing the Flatpak pip closure, so its transitive wheels age silently between releases.**
  packaging/flatpak/python3-deps.yaml is a sha256-pinned closure regenerated
  only by a human running generate-pip-sources.sh. `pyproject.toml` pins the
  DIRECT deps, and test_FIBR0258_closure_satisfies_the_pinned_commit checks the
  closure against the pinned commit's pyproject -- so a direct-dep drift is
  caught. Nothing watches the TRANSITIVE wheels, which the generator resolves to
  whatever is latest at generation time and then freezes.

  Measured 2026-08-20: regenerating moved lxml 6.1.1 -> 6.1.2,
  charset_normalizer 3.4.9 -> 3.5.1 and pypdfium2 5.12.1 -> 5.13.0. The gate was
  green before and after, because no check looks at this. The closure was last
  generated 2026-08-07, so that is 13 days of drift on three packages, none of
  them named in pyproject.toml.

  Why it matters rather than being tidiness: FIBR-0256 is the same class one
  level up -- a cryptography CVE bump landed in pyproject.toml and the closure
  kept the old pin for two weeks. That one was caught only because someone
  looked. lxml and pypdfium2 are both C-extension parsers fed untrusted input
  (OFX and PDF statements), which is the worst place to carry a stale library.

  NOT the same as check-dependencies' job, which reads manifests -- these
  versions appear in no manifest. The closure is the only record.

  Cheapest guard, and it needs no new tooling: a gate stage (or a scheduled CI
  job, since it needs network and the gate's offline stages must stay offline)
  that runs generate-pip-sources.sh into a temp file and fails on a non-empty
  diff against the committed closure. The README already calls an empty diff
  "the confirmation" -- this just makes something other than a human perform it.
  A scheduled job is probably the better shape: a hard gate failure on upstream
  publishing a wheel would block unrelated work.

  Deliberately NOT done on 2026-08-20: the three bumps above were reverted
  rather than taken, because they had never been built here and the tree was
  minutes from a Flathub submission whose reviewers check that it builds from
  pinned source. Taking them needs a LOCAL=0 rebuild to prove the offline build
  still ends FINBREAK_SELFTEST_OK. Do that first; do not bump and push.
  **Layman:** The Linux app-store build freezes an exact list of code libraries. Nothing checks whether newer, possibly security-fixed versions of them have come out, so the build can quietly ship old ones.
  Kind: security.
  Source: in-session-2026-08-20 (found during the FIBR-0159 pre-submit checks).
  Lanes: packaging, security.

- 📋 [FIBR-0317] **Nothing re-submits to OBS on release, so the published RPMs sat six versions behind.**
  Measured 2026-08-31: the OBS package still held finbreak-0.1.16.tar.gz, from
  2026-07-23, while __version__ was 0.1.22. The Tumbleweed and Fedora builds were
  green the whole time -- green on the old source, which is why nothing looked
  wrong.

  Cause: no step in the release path runs packaging/obs/obs-submit.sh.
  .claude/bump.json's todos cover the README, the AppStream metainfo, the Flatpak
  commit re-pin and the deb changelog, and CLAUDE.md's release section names
  cut-release plus the two release scripts. OBS appears in neither.

  Second, sharper half: the vendored wheel closure goes stale with the source.
  Advancing the tarball to 0.1.22 turned BOTH RPM targets red on
  `cryptography==50.0.0` not being in a closure vendored for 0.1.16 -- so a
  re-submit that forgets REVENDOR=1 fails, and one that never happens hides it.
  Fixed in passing today by re-vendoring; the recurrence is what this bullet is
  for.

  Remedy is a decision, not a fix: either add an obs-submit step (with the
  re-vendor) to the release path and gate it the way the other version-bearing
  files are gated, or state that OBS is manually cut and give it a read-back like
  the eight-asset one CLAUDE.md prescribes for a GitHub release. Same class as
  FIBR-0275, where a release published with zero assets went unnoticed for ten
  days.
  **Layman:** The openSUSE/Fedora packages on the build service were still the version from late July, because publishing a new release never updates them. Anyone installing from there got old software.
  Kind: package.
  Source: in-session-2026-08-31 (found while working FIBR-0158).

## P02 — Vertical slice: the security spine (target: after P01)

**Theme:** the smallest end-to-end feature that touches every
layer — and deliberately the **encrypted-storage spine**, since
security is the load-bearing concern. Proves UI → service →
repository → encrypted vault → output → test before any feature
lands on top.

### 🔒 Security

- ✅ [FIBR-0004] **P02: master password → encrypted vault → one manual transaction → table → lock.**
  First-run sets the
  master password + base currency; `CryptoService` derives the
  key with **Argon2id** (parameters pinned in security-model.md
  INV-2) and
  opens the **SQLCipher** (AES-256) vault; `AuthService`
  unlocks/locks and wipes the key from memory on lock; the user
  manually enters one transaction (through a repository, in a
  single DB transaction) and sees it in a table; locking returns
  to the unlock screen and the on-disk file is unreadable
  without the password. Verifies the whole security model
  (ADR-0003 + docs/security-model.md) concretely. Dependencies:
  FIBR-0001. (FIBR-0002 and FIBR-0003 also complete P01 first by
  phase-ordering, but are not direct code prerequisites of the
  vault.) Lanes: ui, services, repo, security, tests. Kind:
  implement. Source: planned.
  Shipped 2026-07-02. Security spine implemented TDD-first; audit (ruff/bandit/gitleaks/semgrep/mypy) clean and three cold 4-lane indie-review rounds converged (all findings fixed inline). Gate green 74 passed/1 skipped. Live language switching (retranslateUi) deferred to FIBR-0017 per user decision (spec deliverable shipped: tr() strings + RTL + QLocale amounts).
  Kind: implement.
  Source: planned.
  Lanes: ui, services, repo, security, tests.

---

## P03 — Accounts

### 🎨 Features

- ✅ [FIBR-0005] **P03: multiple accounts per profile.**
  Account model + CRUD + accounts-manager UI; each account
  tagged with a type (current, savings, credit card, personal
  loan, home loan, investment, other). Transactions belong to an
  account — this must exist before any import. Dependencies:
  FIBR-0004. Lanes: ui, services, repo, tests. Kind: implement.
  Source: planned.
  Resolved (2026-07-02): shipped P03. Account model + CRUD, AccountService (validation + delete guard), AccountsWidget (add/edit/delete), the account picker + Account column + id→name join, and the first forward-only schema-migration runner (v1→v2: seed Default, backfill, atomic BEGIN…COMMIT/ROLLBACK). Migration transaction mechanism verified empirically vs sqlcipher3 0.6.0. Closed via 2 audit + indie-review rounds (all findings fixed inline — key-wipe on newer-vault open, wired the edit form, strengthened the INV-4 rollback test to a true atomicity test); gate green 100 passed/1 skipped, mypy 0, audit 0.
  Kind: implement.
  Lanes: ui, services, repo, tests.

---

- 📋 [FIBR-0157] **Guided first-run wizard walks new users through the natural workflow: create accounts → import statements → categorise transactions → confirm/reject transfers.**
  A sequenced onboarding wizard (and, ideally, smaller task-level wizards) that
  guides a new user through finbreak's natural order of operations rather than
  leaving them to discover it:

  1. Create one or more accounts first (nothing else works without an account
  to attach transactions to).
  2. Import statements (CSV / OFX / PDF) into an account.
  3. Categorise the imported transactions (Type → Category).
  4. Confirm or reject the auto-detected transfers between accounts.

  Design intent / open questions to settle at spec time:
  - Trigger on first run (empty vault) automatically, and make it re-invokable
  later from a Help/menu entry — never a forced modal a returning user can't
  dismiss.
  - Each step should deep-link into the real UI (open the Accounts dialog, the
  Import flow, the Transactions tab filtered to Uncategorised, the Transfers
  review) rather than reimplementing those screens — reuse over rebuild.
  - Show progress ("step 2 of 4") and let the user skip ahead / come back; a
  step is "done" when its underlying data condition is met (≥1 account
  exists, ≥1 statement imported, no uncategorised rows, no pending transfers).
  - Correctness guard: the wizard only navigates and prompts — it must never
  itself write to the transactions table or bypass the transfer-confirmation
  step (transfers stay a user decision, per the transfers invariant).
  - Consider a lightweight "what next?" nudge on the dashboard once onboarding
  is complete but a natural next action exists (e.g. a new statement import
  left uncategorised).
  **Layman:** A step-by-step helper for newcomers that walks them through setting up the app in the right order, so a first-time user is never staring at an empty screen wondering what to do.
  Kind: feature.
  Source: user-request-2026-07-23.

## P04 — Category tree

### 🎨 Features

- ✅ [FIBR-0006] **P04: Type → Category tree (3rd level ready).**
  Self-referential `categories` table (`parent_id`),
  seeded Income/Expenditure types with sensible default
  categories (salary, sales / fast food, bills, medical,
  lottery…), and a category-management UI exposing two levels.
  Data model supports a future Sub-category level without
  migration. Dependencies: FIBR-0004, FIBR-0005. Lanes: services, repo, ui,
  tests. Kind: implement. Source: planned.
  Resolved (2026-07-02): shipped the categories aggregate (self-referential table + 2 seeded Type roots + 16 defaults), the QTreeWidget manager, and the v2→v3 migration. Spec cold-eyes-converged (7 loops); TDD; /audit + /indie-review 0 actionable on the closing pass. Gate green (122 passed/1 skipped, mypy 0). Transaction→category link deferred to P08 (FIBR-0010) by design. Journal: docs/journal/FIBR-0006.md. Tag FIBR-0006-complete.
  Kind: implement.
  Source: planned.
  Lanes: services, repo, ui, tests.

---

## P05 — CSV import + mapping profiles

### 🎨 Features

- ✅ [FIBR-0007] **P05: CSV import with per-bank mapping profiles + dedup + import wizard.**
  `ImportService`
  orchestration + `CsvImporter` + saved per-bank column-mapping
  profiles (ADR-0005); de-duplication so re-importing an
  overlapping statement adds **zero** duplicates (success
  criterion 2); import wizard with a preview that shows per-row
  parse errors *before* anything is written. The first real
  import path; establishes the pipeline P06/P07 reuse.
  Dependencies: FIBR-0005, FIBR-0006. Lanes: services, importers, ui,
  repo, tests. Kind: implement. Source: planned.
  Design-ahead (user-request-2026-07-02): capture each imported
  statement's coverage period (start/end date) per account as
  first-class data AT IMPORT TIME — the reliable input for statement-gap
  detection (FIBR-0038). Bank PDFs print the period; for CSV (no period
  metadata) confirm it in the wizard. Cheap to add now, expensive to
  retrofit (would need re-import to learn periods). Establish the
  data-model hook here (the first importer) so OFX (FIBR-0008) and PDF
  (FIBR-0009) populate it too.
  Resolved (2026-07-03): shipped via /close-phase. CsvImporter + ImportService (exact-signature profiles, multiset-delta dedup, atomic write + coverage-period), v3->v4 migration (import_profiles + statement_periods), non-modal wizard. 43 tests (INV-1..11); gate green 165 passed/1 skipped, mypy 0; audit 0 + indie-review 0 CRIT/HIGH/MED (one LOW fixed inline: preview renders decimals not minor units). Tag FIBR-0007-complete.
  Kind: implement.
  Source: planned.
  Lanes: services, importers, ui, repo, tests.

---

## P06 — OFX import

### 🎨 Features

- ✅ [FIBR-0008] **P06: OFX import.**
  `OfxImporter` via
  `ofxparse`, feeding the same `ImportService` pipeline (dedup,
  categorisation, transfer detection) built in P05. OFX is a
  worldwide standard needing no mapping profile. Dependencies:
  FIBR-0007. Lanes: importers, services, tests. Kind: implement.
  Source: planned.
  Resolved (2026-07-04): P06 OFX import shipped. Pure OfxImporter -> the same ParseResult/ImportService pipeline as CSV (D2 _preview_from_result seam); embedded DTSTART/DTEND period (D4); payee-else-memo (D5); all-or-nothing-per-statement error model (D15); resource caps (D13); wizard OFX branch skips mapping + a multi-account chooser (D8/D10); no schema change (D9). Spec cold-eyes-converged (8 loops). Gate green 199 passed / 1 skipped, mypy 0; /audit 0, /indie-review fixed inline (deferred the tz-DTPOSTED day-shift -> FIBR-0042). FIBR-0003 build smoke re-run green (all five native stacks travel, incl. ofxparse/lxml; fixed a latent argon2 dep-drift in the build script en route). Tag FIBR-0008-complete.
  Kind: implement.
  Lanes: importers, services, tests.

---

## P07 — PDF statement import (incl. locked PDFs)

### 🎨 Features · 🔒 Security

- ✅ [FIBR-0009] **P07: PDF statement import with in-memory decrypt.**
  `PdfImporter` (`pdfplumber` table
  extraction) on the P05 pipeline; password-protected statements
  are decrypted **in memory only** (`pikepdf`, never written
  decrypted to disk); opt-in "remember this password" stores it
  **encrypted in the vault** against the account (default:
  prompt each time, store nothing). A wrong PDF password
  re-prompts rather than aborting the import. Dependencies: FIBR-0007.
  Lanes: importers, services, security, ui, tests. Kind:
  implement. Source: planned.
  Resolved (2026-07-04): PdfImporter (extract-then-CSV-adapter) + in-memory pikepdf decrypt + opt-in remembered password (v5 column) + wizard PDF branch. TDD; gate green 240 passed/1 skipped, mypy 0; FIBR-0003 build smoke PASS (native PDF tree travels). /close-phase: /audit 0, /indie-review 3 lanes (2 clean, 1 LOW coverage gap fixed inline). Free-text/OCR PDFs deferred (§ Out of scope). See docs/journal/FIBR-0009.md.
  Kind: implement.
  Source: planned.

---

## P07.5 — App shell & first-run wizard (UX redesign)

### 🎨 Features · 🖥️ UX

---

- ✅ [FIBR-0051] **P07.5: app-shell UX redesign — real app window (QMainWindow) with menubar / icon toolbar / status bar; first-run & unlock as popups.**
  Replace the full-screen QStackedWidget swap model with a QMainWindow
  shell: menubar (File / View / Help / Donate), an icon toolbar
  (Manual entry / Import / Accounts / Categories / Lock, icon-above-
  label), a central swappable content stack, and a status bar that
  reports current activity (Ready / Importing… / Added transaction /
  Vault locked) plus a persistent transaction count. First-run and
  unlock become popup dialogs shown OVER the window (chrome greyed,
  content shows a Welcome / 🔒 Locked placeholder); idle auto-lock
  returns to the locked-shell state. Manual entry becomes a popup
  Add-Transaction dialog. Home = getting-started panel when empty,
  transaction table once populated (the P10 dashboard later replaces
  Home's body). Donate menu opens the .github/FUNDING.yml links
  (GitHub Sponsors / Patreon / PayBru) via QDesktopServices — a
  user-initiated hand-off to the OS browser; the app itself made no
  network calls at the time of this bullet (FIBR-0054 later added the
  one opt-in, off-by-default update check — your financial data still
  never leaves the machine). Reuses the existing
  accounts / categories / import screens as content views. Preserves
  FIBR-0004 security invariants: key wiped on quit, auto-lock fires,
  NO transaction data shown while locked, corrupt/incomplete-install
  guard at startup. Build order: this ships FIRST, then P08 rules +
  category link, P09 transfer detection, P10 dashboard drop into the
  ready-made content area. Out of scope (own phases): dashboard
  charts (FIBR-0012), rules screen (FIBR-0010), transfer prompts
  (FIBR-0011), branded app icon (FIBR-0037).
  Dependencies: FIBR-0004, FIBR-0005, FIBR-0006, FIBR-0007, FIBR-0008, FIBR-0009.
  **Layman:** Turn the bare password-box-then-form startup into a proper app window — menus, a toolbar of shortcuts, a status bar, and a first-run popup wizard — so it looks and feels like a real desktop app.
  Kind: implement.
  Lanes: ui, app, tests.
  Source: user-request-2026-07-05.
  Resolved (2026-07-09): shipped by /close-phase. QMainWindow shell + popup first-run/unlock/manual-entry dialogs + status bar + Donate menu; content destroyed-on-lock (no decrypted rows survive). TDD: 22 tests/features/app_shell/ + D10 ripple re-home; gate green 299 passed/1 skipped, mypy 0; FIBR-0003 build smoke PASS (icons travel into the frozen bundle, DoD #2). /audit clean; /indie-review 2 cold lanes — no CRIT/HIGH/MED, 2 LOW (status-bar Ready restore, locale-hermetic amount test) + 1 INFO (QIcon-absent rationale) folded inline. Tag FIBR-0051-complete.

- ✅ [FIBR-0052] **P07.6: tabbed main window + statement provenance & delete (shell v2).**
  Tabbed-workspace evolution the user approved 2026-07-09 (design brainstormed + approved this session), EXPANDED the same day by two follow-ups — exact per-statement transaction count + delete-a-statement-and-its-transactions — which pull the statement-provenance data model (planned as "Round 2") into this phase (user chose "all in one phase", 2026-07-09). Builds on the FIBR-0051 shell. Full contract: docs/specs/FIBR-0052.md.
  Resolved (2026-07-09): shipped by /close-phase. Tabbed QTabWidget workspace (Home · Statements · Accounts · Categories) + Home toolbar button + vault-independent Window menu (Center/Reset) + window geometry/last-tab persisted to a plain INI outside the vault; Statements tab (StatementService + StatementsWidget) with an exact linked-transaction count + atomic delete-statement-and-its-transactions; v5→v6 nullable transactions.statement_period_id FK + commit_import stamp (reordered period-first) + one-time ambiguity-guarded backfill; AccountsWidget/CategoriesWidget show_done flag; home.svg. TDD: 27 tests/features/statements/ + the FIBR-0051 app_shell ripple (nav/lock/manual-entry re-homed to the tab model) + the v5→v6 schema ripple across vault/accounts/categories/import_/ofx_import/pdf_import. Gate green 324 passed/1 skipped, mypy 0; home.svg travels via the existing ui/icons/*.svg glob (DoD #2). Real Standard Bank credit-card PDF validated end-to-end in a throwaway vault (53 txns, exact count, clean delete). /audit 0; /indie-review 3 cold lanes — no CRIT/HIGH/MED, security spine verified; 1 production LOW (locked-vault delete guard) + 1 test-fidelity + 4 coverage findings folded inline. Tag FIBR-0052-complete. P08/FIBR-0010 rules follows.

  Scope:
  - Central content area becomes a QTabWidget "workspace" with FIXED tabs: Home · Statements · Accounts · Categories. Mirrored under the View menu (both navigate); the tab widgets are PERSISTENT (a switch, not a rebuild). Reuses AccountsWidget/CategoriesWidget as tab pages via a `show_done` flag that retires their now-redundant "back to Home" button in tab mode.
  - Add a Home QAction to the toolbar (new house SVG glyph). Toolbar order: Home · Manual entry · Import · Accounts · Categories · Lock. Toolbar buttons switch tabs; Manual entry / Import still open their dialog / wizard (Import is a flow that replaces the workspace and returns to it, NOT a tab).
  - **Statement provenance (v5→v6 migration):** add a nullable `transactions.statement_period_id` FK; `commit_import` stamps every imported row with its source statement; manual entries stay NULL. A one-time ambiguity-guarded backfill links statements imported before the column existed (stamp account+in-span rows, skip dates covered by >1 period). Every importer already writes statement_periods via the single commit_import path, so no backfill of the record itself is needed.
  - **Statements tab (read + delete):** lists every imported statement (account · period · source file · imported-at · transaction count = rows linked via statement_period_id — exact for v6 imports, backfill-linked for pre-v6 imports; a statement with no linked rows shows 0, not an em-dash). A Delete action removes the statement record AND its imported transactions in one atomic service transaction (manual/other-statement rows untouched), after a confirmation naming the count; refreshes Home + the status count. New StatementService (services/statements.py) + StatementsWidget (ui/statements.py).
  - Home tab: unchanged from FIBR-0051 (getting-started ↔ table). Full categorised income/expenditure breakdown is still FIBR-0012.
  - Window geometry: remember size + position + toolbar state + last-active tab via QSettings in a plain INI (paths.window_settings_path()) OUTSIDE the encrypted vault (non-sensitive; restored before unlock). Add Center-window + Reset-layout actions in a vault-independent Window menu.
  - Security preserved: lock tears down the whole tabbed workspace (and any open import wizard) and shows the Locked placeholder (rebuilt on unlock) — FIBR-0051 INV-3 (nothing decrypted survives a lock). The delete is a service-owned atomic transaction leaving a re-openable vault on failure; the plain FK (no cascade) blocks an unsafe period-only delete.

  Staging (the rest, approved but separate items):
  - Follow-up (cheap now the stamp exists, not requested yet): a dedicated per-statement transaction VIEW (double-click a statement → its transactions read-only). Undo-of-delete also deferred.
  - Later (post-FIBR-0052): Home dashboard — income/expenditure summary + category breakdown; BLOCKED on P08 (FIBR-0010 category link) + P09 (FIBR-0011 transfer detection) for correct totals (self-transfers must not double-count). This is FIBR-0012's dashboard, pulled onto Home.

  Progress (2026-07-09): spec docs/specs/FIBR-0052.md written from the approved+expanded design; next /cold-eyes to convergence (rule §14) before TDD.

  Dependencies: FIBR-0051 (shell). Independent of P08/P09; runs before them.
  **Layman:** Turn the single content area into tabs (Home · Statements · Accounts · Categories), add a Home button to the toolbar, and make the window remember its size and position (plus a Center-window action). The Statements tab shows what you've imported with an exact transaction count and lets you delete a statement and all its transactions — which needs a small database change to tag each transaction with the statement it came from.
  Kind: implement.
  Lanes: ui, app, tests.
  Source: user-request-2026-07-09.

## P08 — Auto-categorisation rules

### 🎨 Features

- ✅ [FIBR-0010] **P08: rules engine + manual override.**
  `CategorizationService` applies a user-editable rule set to
  auto-assign categories; a manual override is the
  highest-priority signal and is never clobbered by re-import or
  a later rule. Rules-manager UI to view/add/edit. Dependencies:
  FIBR-0005, FIBR-0006, FIBR-0007, FIBR-0051, FIBR-0052. Lanes: services, ui, repo, tests. Kind: implement.
  Source: planned.
  Scope note (2026-07-09, spec drafted): the spec (docs/specs/FIBR-0010.md) grows this bullet's "rules-manager (view/add/edit)" summary to the full P08 slice — the transaction→category link (v6→v7), first-match-by-priority rules run on import + an explicit "Apply rules now", a manual per-transaction override that is frozen (never clobbered by re-import or a rule run), a Home Category column + "Set category…", the rules-manager tab (add/edit/delete/move/apply), an atomic delete-category cascade with a blast-radius confirm, and the learn-from-corrections offer pulled forward from FIBR-0035 (see that bullet). Deps widened to FIBR-0005/0006/0007/0051/0052.
  Resolved (2026-07-10): shipped. Rules engine + manual override + learning + delete-category cascade; schema v6->v7. TDD 45 tests; /audit 0, /indie-review 3 cold lanes + confirming pass (1 HIGH auto-lock + 3 MED test-coverage/naming + 1 LOW dedup-helper folded inline). Gate green 411/1, mypy 0. Tag FIBR-0010-complete; journal docs/journal/FIBR-0010.md.
  Kind: implement.
  Lanes: services, ui, repo, tests.

---

## P09 — Transfer detection

### 🎨 Features

- ✅ [FIBR-0011] **P09: transfer detection (suggest-then-confirm).**
  `TransferDetectionService` matches a
  debit in one account against a credit in another (same amount,
  short date window) and **proposes** the pair; only
  user-confirmed pairs are linked as transfers and excluded from
  income/expenditure totals (success criterion 3, ADR-0006).
  Rejected pairs are remembered so they don't re-surface. Never
  auto-hides a real expense. Dependencies: FIBR-0005, FIBR-0007. Lanes:
  services, ui, repo, tests. Kind: implement. Source: planned.
  Progress (2026-07-12): design brainstormed + approved by user. Chose ±3-day match window, a dedicated Transfers tab (no post-import pop-up), and a single decision table (v7→v8) recording confirmed/rejected pairs (pending candidates recomputed live). Next: write docs/specs/FIBR-0011.md → /cold-eyes (7-loop cap) → TDD.
  Resolved (2026-07-12): shipped by TDD. Schema v7→v8 (transfer_pairs decision table, dual ON DELETE CASCADE, canonical UNIQUE); TransferRepository (candidate self-join — equal-magnitude/opposite-sign/different-account/±TRANSFER_WINDOW_DAYS=3, per-decision commits); TransferDetectionService (candidates/confirm/reject/unlink/confirmed_transfers/confirmed_transfer_txn_ids [the FIBR-0012 exclusion primitive]/confirm_all); the 6th Transfers tab (suggested+confirmed tables, Confirm/Reject/Confirm all/Unlink, VaultLockedError-guarded). tests/features/transfers/ one case per INV-1..12 + edges (window 0/3/4, off-by-one, two-debits, same-account, Cartesian, empty-vault); schema-version + tab-count ripple across 9 suites. Spec /cold-eyes-converged loop 4. Close: /audit 0 in the new code (3 pre-existing FIBR-0054 updater semgrep warnings out of scope); /indie-review 2 cold lanes — data/logic CLEAN, UI/shell 2 LOW (auto-lock test parametrized over all 4 slots; stale tab-count docstrings) folded inline. Gate green 645/1, mypy 0. Unblocks FIBR-0012 (dashboard).
  Kind: implement.
  Source: planned.
  Lanes: services, ui, repo, tests.

---

## P10 — Reporting + dashboard

### 🎨 Features

- ✅ [FIBR-0012] **P10: dashboard — summary, pie/donut, trends, filterable table.**
  `ReportingService` aggregates by
  category / account / period; the dashboard shows the
  income-vs-expenditure summary, a category pie/donut, and
  month-to-month trends, per account or consolidated; the
  transaction table gains full search + filters (success
  criterion 1). **Charts library is chosen at spec time**
  (QtCharts vs matplotlib vs pyqtgraph — must be dark-themeable
  *and* render into the PDF) and recorded as an ADR. Dependencies:
  FIBR-0008, FIBR-0009, FIBR-0010, FIBR-0011 (OFX, PDF, rule-based
  categorisation, and **transfer detection** — so the consolidated
  income/expenditure totals correctly exclude transfers, SC3; CSV via
  FIBR-0007 is pulled in transitively, so all of CSV/OFX/PDF are
  consolidated — SC1 names all three). Lanes: services, ui, tests. Kind: implement.
  Source: planned.
  UX (user, 2026-07-11, dogfooding v0.1.2): the Home tab currently shows the raw transaction table (interim from FIBR-0051). The user confirms Home should be the income/expenditure SUMMARY (this dashboard), NOT the transaction list. So this item also owns relocating the transaction table off Home into its own view/tab (e.g. a "Transactions" tab) — carrying the full search + filters this item already promises — leaving Home for the summary + charts.
  **Layman:** The Home screen becomes a proper dashboard — a plain income-vs-spending summary, a pie chart of where your money goes, and month-by-month trends — while the transaction list moves to its own searchable, filterable tab.
  Design approved 2026-07-12 (brainstorming). Scope locked: QtCharts (ADR-0008, no new dep); ReportingService (period model default=previous month, persisted ReportPrefs; transfers never counted as income/expenditure anywhere); Home dashboard (period+account selectors, income/expenditure/net tiles, spending-by-category donut, monthly income-vs-expenditure grouped-bar trend); new Transactions tab absorbing FIBR-0109 (search + date-range + account + category filters, all combinable) with the transaction table relocated off Home. Tab order → Home·Transactions·Statements·Accounts·Categories·Rules·Transfers. Next: ADR-0008 + spec → /cold-eyes.
  Resolved 2026-07-13: shipped by TDD across 11 slices. ReportingService (pure period model + summary/spending_by_category/monthly_trend, transfers excluded, integer-exact) + ReportPrefs persistence; Home reworked into the QtCharts dashboard (donut + 12-month trend, ≤8-wedge collapse, empty-state placeholder); new Transactions tab with search+date+account+category filters (absorbs FIBR-0109); 7-tab shell, count live from Home's ReportingService, QtCharts self-test leg. Close: /audit 0 actionable; /indie-review 2 cold lanes → 3 findings all fixed inline (report_prefs year bound INV-2; per-table column-key objectNames; VaultLockedError-specific slot guards) + 2 regression tests. Gate green 712/1, mypy 0. Tag FIBR-0012-complete.
  Kind: implement.
  Lanes: services, ui, tests.

---

## P11 — Password-protected PDF export

### 🎨 Features · 🔒 Security

- ✅ [FIBR-0013] **P11: locked PDF export with section selection.**
  `PdfExportService` renders chosen sections
  (summary / charts / transactions) for a chosen period via the
  Qt PDF engine, then encrypts with a password set at export
  time (`pikepdf`, AES-256). Export dialog ticks sections + picks
  period + sets password (success criterion 5). Dependencies:
  FIBR-0012. Lanes: services, ui, security, tests. Kind: implement.
  Source: planned.
  **Layman:** Save a password-protected PDF report of your finances — pick which parts to include (summary, charts, transactions) and the date range, and set a password so only you can open it.
  UX (user, 2026-07-12): the export password must be OPTIONAL — the user can choose to add one, but an unprotected PDF export is a first-class supported outcome (not forced). So the "locked" in the headline is opt-in: the section-selection export flow offers an optional password field; empty → a normal unencrypted PDF, non-empty → the pikepdf AES-256 export-lock (ADR-0004). Design the dialog around that choice.
  In-progress 2026-07-13: spec docs/specs/FIBR-0013.md drafted (brainstorm-approved) and in /cold-eyes (project cap 7). Export password OPTIONAL per user; SC5 relaxed accordingly (discovery.md updated).
  Resolved 2026-07-13: P11 locked-PDF export SHIPPED by TDD (7 slices). PdfExportService (in-memory render → optional pikepdf AES-256, atomic export); ui/charts.py shared builders; ReportingService widened to an account set; ExportDialog (INV-14 gating + master-toggle state machine); File-menu + toolbar entry; --self-test encrypt leg. Close: /audit 0 in-scope; /indie-review 2 cold lanes → no CRIT/HIGH/MED, 3 LOW fixed inline (empty-donut placeholder, currency-symbol escaping, narrowed export except). Gate green 779/1. Tag FIBR-0013-complete.
  Kind: implement.
  Lanes: services, ui, security, tests.

---

## P12 — Settings, auto-lock, backup, theme polish

### 🔒 Security · 🎨 Features

- ✅ [FIBR-0014] **P12: settings, inactivity auto-lock, encrypted backup.**
  Settings screen (base currency display,
  auto-lock timeout, manage stored PDF passwords, theme);
  inactivity **auto-lock** drops the key and returns to unlock;
  **encrypted backup export/restore** (the only mitigation for a
  forgotten master password, per ADR-0003); dark-theme polish
  pass. Dependencies: FIBR-0004. Lanes: ui, services, security, tests.
  Kind: implement. Source: planned.
  **Layman:** A full Settings screen plus an encrypted backup you can export and restore — your one safety net if you ever forget your master password — and a light/dark theme choice.
  Note (2026-07-09): the Settings-screen scaffold + the user-configurable auto-lock timeout (+ base-currency read-only display) are pulled FORWARD into FIBR-0055 (near-term, user-requested); FIBR-0055's first cut delivers the scaffold + configurable auto-lock timeout + read-only currency only. This phase narrows to what remains: the encrypted-backup export/import (the only mitigation for a forgotten master password, ADR-0003), the dark-theme polish pass and its dark/light/follow-system theme toggle (a toggle needs the theme system this pass builds), stored-PDF-password management, and hosting the FIBR-0017 language switcher. If FIBR-0055 ships first, this becomes an extension of that Settings screen rather than a fresh one.
  Split (2026-07-13, in-session, user-approved): P12 bundled four independent pieces. Auto-lock is already shipped (mechanism FIBR-0114; user-configurable timeout + Settings scaffold + read-only currency via FIBR-0055). This item is now NARROWED to the encrypted backup export/restore only — the ADR-0003 forgotten-master-password mitigation, keyed by a SEPARATE backup password so it can actually recover a forgotten master password. The other three pieces are split into their own items: app-wide theme system -> FIBR-0127; stored-PDF-password management UI -> FIBR-0128; language-switcher hosting -> FIBR-0129 (note: overlaps FIBR-0017, which already owns the i18n picker — reconcile when either is specced). Build order: backup (this) first, then 0127, 0128, 0129. Spec: docs/specs/FIBR-0014.md (encrypted backup).
  Resolved 2026-07-13 (/close-phase). Shipped by TDD in 7 red→green slices + a fold-in of 6 cold-review findings. D2 SQLCipher mechanics (sqlcipher_export / PRAGMA rekey / cipher_compatibility / HMAC-on / no-plaintext-temp) validated by a throwaway spike on sqlcipher3-binary 0.6.0 (SQLCipher 4.12.0) before any code. BackupService(vault, auth) export/restore over a stdlib-zip .fbk (manifest.json + params.json + vault.db); separate backup password (fresh salt), INV-1..13. UI: Settings Export + pre-login Restore on unlock & first-run; synchronous main-thread export (INV-9); interrupted-restore reconciliation (INV-5). /audit 0 actionable (1 bandit B608 FP suppressed on a test); 2 cold review lanes → 6 findings (2 HIGH crypto/UI, 2 HIGH/MED, LOW) all fixed inline with regression tests. security-model.md T11 hedge dropped + .fbk untrusted surface added (cold-eyes clean). Gate green 841/1, mypy 0. Tag FIBR-0014-complete.
  Source: planned.
  Lanes: ui, services, security, tests.

---

- 📋 [FIBR-0017] **P12: multi-language UI (i18n) — 6 bundled locales incl. RTL + language switcher.**
  Qt translation pipeline: every user-facing string is wrapped in `tr()` from the first UI onward (P02), `lupdate` extracts them to `.ts` catalogs, translations are compiled to `.qm` and loaded via `QTranslator` at startup and on live switch. Ships **6 locales**: English (base), Spanish, Simplified Chinese, Hindi, French, and **Arabic** (right-to-left). A language picker in the FIBR-0014 Settings screen switches locale. Numbers, currency, and dates render through `QLocale` (matters for a finance app — ties into the base-currency display), not hardcoded formats. The UI is built **RTL-ready** (layout mirroring) from P02 per design.md "Internationalization (i18n) & localisation", so Arabic is translate-and-ship; further RTL scripts (Hebrew, Urdu) are then a translation-only follow-up. NOTE: this stays cheap only if the string-externalization and RTL-safe-layout conventions are followed from P02 — retrofitting hardcoded English (and left-to-right-only layouts) across the whole feature stack is far more expensive. Dependencies: FIBR-0014 (settings screen hosts the switcher; transitively pulls the feature-complete UI so all strings exist to translate).
  **Layman:** Lets people use finbreak in their own language — ships in 6 languages to start (including Arabic, which reads right-to-left), with more addable later.
  Kind: implement.
  Lanes: ui, i18n, services, tests.
  Source: user-request-2026-07-01.
  Deferred from FIBR-0004 (P02) per user decision 2026-07-02: the three P02 screens (first_run, unlock, main_window) build their strings once in __init__ and do NOT implement live language switching (changeEvent → retranslateUi). coding.md §5.2 asks for this "from P02"; the FIBR-0004 spec deliverable required only tr() strings + RTL layouts + QLocale amounts (all shipped), and there are no translations to switch yet. When this phase lands, add changeEvent/retranslateUi to those three screens (and every screen built between P02 and here) so the language switcher takes effect without a relaunch.
  Scope note (2026-08-03, user request): loading the right catalog **at
  startup from the system language** is FIBR-0209, not this bullet. This
  item's "loaded via QTranslator at startup and on live switch" says the
  mechanism exists but never says which locale is chosen on a first run
  with no stored preference — FIBR-0209 pins that (system locale, full
  `pt_BR` then bare `pt`, else English) and the silent-fallback rule.
  Fold FIBR-0209 in if this is specced first; otherwise ship it after.

- ✅ [FIBR-0127] **App-wide six-theme (finance-flavoured) + follow-system theme system & modern polish.**
  Split from FIBR-0014 (P12). Nothing exists today: the app rides the system/Qt default palette (dark by convention) with NO stylesheet, no QPalette install, no theme setting key, no toggle (app.py sets no palette). This builds the theme system from scratch (Fusion + token-driven QPalette/QSS — ADR-0010): a non-vault `theme` pref with 7 values (`system` + six named themes Ledger/Parchment/Mint · Midnight/Graphite/Emerald), palette+stylesheet application at the app entry point, and live follow-system detection, plus the sleek modern polish (gradient/glow accents + grid row-highlighting). Widgets already READ the live palette (ui/icons.py _is_dark_theme, home.py ChartTheme from palette().text(), _amount.py fixed mid-tones) so they adapt once a palette is installed. Delivers FIBR-0116's live icon re-tint on theme switch (toolbar glyphs re-tint on the ThemeController themeChanged signal); the _amount.py palette-adaptive re-tinting stays deferred here. Hosted in the FIBR-0055 Settings dialog. (The old note that the code mis-cites ADR-0002 for the dark theme and "write a real theme ADR when specced" is done — ADR-0010 is that theme ADR; the icons.py citation is corrected in the spec.)
  **Layman:** A proper set of light and dark themes (six finance-flavoured looks) you can choose — or have the app follow your operating system's light/dark setting — instead of the app being dark-only.
  Kind: implement.
  Lanes: ui.
  Source: split-from-FIBR-0014-2026-07-13.
  Spec docs/specs/FIBR-0127.md + ADR-0010 written 2026-07-14 from the user-approved brainstorm (designed look, 6 finance themes Ledger/Parchment/Mint + Midnight/Graphite/Emerald, live follow-system, sleek modern polish: gradient/glow accents + grid row-highlighting, theme-aware toolbar icons). Cold-eyes next.
  Resolved (2026-07-14): SHIPPED by /close-phase (code). TDD 30-leg tests/features/theme/ (INV-1..13 + D3/D4) → ui/theme.py (six-theme token registry → build_palette/build_stylesheet, ThemeController with live colorSchemeChanged follow-system, non-vault pref) + app.py/main_window.py/settings.py wiring + D11 ADR-0002→ADR-0010 citation fixes. /audit 0 actionable (semgrep full + ruff/bandit/gitleaks via gate); /indie-review 2 cold lanes → no CRIT/HIGH/MED, 1 LOW (INV-10 pixmap-content re-tint falsifier) folded inline. Gate green 907/1, mypy 0. Tag FIBR-0127-complete; journal docs/journal/FIBR-0127.md.

- ✅ [FIBR-0128] **Forget remembered PDF statement passwords (per-account, Accounts screen).**
  Split from FIBR-0014 (P12). The store already EXISTS (FIBR-0009, schema v5): accounts.statement_pdf_password (nullable, vault-encrypted at rest, deliberately not selected into the Account dataclass for credential hygiene), with AccountsRepository.get_pdf_password / set_pdf_password. It is written implicitly during import and auto-tried; there is NO management UI. This item adds an Accounts-screen, per-account control to list accounts with a remembered statement password and forget (clear) it (placement + forget-only per spec FIBR-0128 D1/D5). (Distinct from the FIBR-0013 export password, which is ephemeral and never stored.)
  **Layman:** A per-account button to see which accounts have a remembered bank-statement password and forget (clear) it — the password itself is never shown.
  Kind: implement.
  Lanes: ui, security.
  Source: split-from-FIBR-0014-2026-07-13.
  Placement decided (spec FIBR-0128 D1, user directive 2026-07-14): the presence/forget controls live on the **Accounts screen** (per-account, selection-driven), NOT Settings — different accounts can have different statement passwords, so the per-account surface is the natural home. Forget-only (no reveal, no manual set); the secret never crosses into the UI. Spec written; /cold-eyes next.
  Resolved (2026-07-14): SHIPPED by /close-phase (code). TDD 8-leg tests/features/accounts/ (INV-1..5) → repo ids_with_pdf_password + service account_ids_with_pdf_password + ui/accounts.py Forget button/marker/handler. Presence is an id-set (never selects the secret column); the plaintext never crosses into the UI (INV-1). Forget-only, per-account, confirm-gated, VaultLockedError-silent; enable/disable recomputed before the None early-return so a post-Forget refresh disables the button. semgrep+bandit 0 on the changed surface; 1 cold review lane → production CLEAN, 2 LOW test-precision folded inline. Gate green 915/1, mypy 0. Tag FIBR-0128-complete; journal docs/journal/FIBR-0128.md.

- 📋 [FIBR-0129] **Host the language switcher in Settings (picker widget + language setting key).**
  Split from FIBR-0014 (P12). Strings are tr()-wrapped throughout and RTL-ready (app.setLayoutDirection), but there is NO QTranslator, no .ts/.qm, no language setting key, no picker. This provides the language-picker widget in the FIBR-0055 Settings dialog + a `language` settings key. The translation pipeline itself (lupdate -> .ts -> .qm -> QTranslator at startup + live retranslateUi) is FIBR-0017; gate the picker's usefulness on that, or ship the widget writing the key now and wire it when FIBR-0017 lands.
  **Layman:** A place in Settings to pick your language. The actual translations arrive with FIBR-0017; this just provides the chooser and remembers your pick.
  Kind: implement.
  Lanes: ui, i18n.
  Source: split-from-FIBR-0014-2026-07-13.
  Scope note (2026-08-03, user request): the `language` key this bullet
  adds must default to a `"system"` sentinel, not to `"en"` — FIBR-0209
  makes "follow the operating system's language" the out-of-the-box
  behaviour, so the picker's first entry is "System default" and an
  explicit pick is what overrides detection. Same shape as the timezone
  / date / time combos (`DATETIME_SYSTEM`, `ui/_datetime_prefs.py`),
  which this dialog already hosts.

- ✅ [FIBR-0135] **Auto-lock "Never" option — let the user disable the idle timer entirely.**
  User lives alone / rarely has visitors and doesn't want the idle auto-lock. Added 0="Never" to ALLOWED_AUTO_LOCK_MINUTES (listed LAST so a corrupt/absent value still falls back to the 1-minute floor, never to "Never" — the INV-1 safe-fail is preserved). _arm_timer stops the timer instead of starting it when Never; notify_activity gains an isActive() guard so user activity can't silently re-arm a disabled timer. Settings combo gains a "Never" label. Password-on-open and manual Lock button are unchanged; the key is still wiped on lock and exit. security-model.md T3 amended to record the accepted residual risk (an unattended unlocked session stays unlocked — a user choice, not a silent default). Reverses the FIBR-0055 D6 "no never option" decision by explicit user request. Kind: enhancement.
  **Layman:** Add a "Never" choice to the auto-lock setting so the app won't lock itself while you're away — you still type your password when you open it and can lock it any time with the Lock button.
  Kind: enhancement.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14) — commit b915254. Auto-lock "Never" (0) added; _arm_timer stops on it, notify_activity isActive()-guarded, combo label + security-model T3 note. Gate green 862/1.

- 📋 [FIBR-0209] **Launch in the system language automatically, falling back to English.**
  User request 2026-08-03. On startup, detect the operating system's
  language and load that locale's translation automatically — the user
  should not have to find a setting to be understood.

  Resolution order (first hit wins):
  1. An explicit language the user picked, if one is stored (FIBR-0129's
  `language` key). An explicit choice always beats detection.
  2. The system language, via `QLocale.system()` — match on the full
  locale first (e.g. `pt_BR`), then fall back to the bare language
  (`pt`), so a regional variant still finds its base translation.
  3. English, if the system language is absent, unreadable, or has no
  bundled `.qm` catalog.

  Follow the project's existing sentinel shape: the stored `language`
  key should default to a `"system"` token exactly like
  `DATETIME_SYSTEM` in `ui/_datetime_prefs.py`, so "follow the system"
  is a real stored state and not merely the absence of a value. That
  also makes the Settings picker's first entry ("System default")
  consistent with the timezone / date / time combos already there.

  Two traps worth pinning in the spec:
  - The fallback must be **silent and total** — an unsupported language
  is the normal case for most of the world until more locales ship,
  so it must never surface an error or an empty UI, just English.
  - Detection runs BEFORE the first window is built, like the theme
  pref (`app.py` applies the theme before `MainWindow`), so the
  locked first window is already in the right language. The theme
  system's `load_theme_pref` allowlist-against-known-ids is the
  pattern to copy for validating a stored/detected language token.

  Depends on FIBR-0017 (the QTranslator pipeline + the bundled `.qm`
  catalogs must exist before there is anything to detect INTO) and
  FIBR-0129 (owns the `language` settings key this reads). Ship after
  both, or fold into FIBR-0017 if that is specced first.
  **Layman:** finbreak should open in whatever language your computer is set to, without you having to pick it. If it does not know your language, or does not have a translation for it yet, it opens in English.
  Kind: feature.
  Lanes: ui, i18n.
  Source: user-request-2026-08-03.

- ✅ [FIBR-0210] **Startup is bricked by a corrupt window.ini (int('') on last_tab).**
  From the FIBR-0204 sweep (MEDIUM, verified). `MainWindow._restore_geometry`
  reads `int(raw_tab) if raw_tab is not None else _TAB_HOME`. MEASURED: an INI
  containing `last_tab=` makes QSettings return `''` (NOT None), and `int('')`
  raises ValueError. It runs inside `MainWindow.__init__`, so it escapes past
  `app.py`'s `except VaultStateError` guard and the app never starts again until
  the user finds and deletes ~/.config/finbreak/window.ini.

  Reachable from a truncated sync after power loss, a hand-edit, or a downgrade
  from a future version that stores a tab NAME. Fix: `except (TypeError,
  ValueError): return _TAB_HOME` — the same defensive posture `auth.py`'s
  `auto_lock_minutes` already takes for a corrupt stored value, and the same
  allowlist-the-known-good shape as `theme.load_theme_pref`.

  While there, audit the other `window.ini` reads for the same shape.
  **Layman:** If the settings file that remembers your window size gets damaged, finbreak refuses to open at all until you find and delete it by hand. It should just fall back to the default.
  Kind: fix.
  Lanes: ui.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): `_restore_geometry` is fail-safe on every
  read. The audit the bullet asked for found three MORE brick shapes in the
  same function, not just `int('')` — `geometry` and `window_state` are handed
  to `restoreGeometry`/`restoreState`, and a plain string where a `@ByteArray`
  was written raises TypeError (measured, PySide6 6.9). New `_restore_blob`
  helper type-checks the blob and reports whether Qt actually applied it, so an
  undecodable geometry now falls back to `_DEFAULT_WINDOW_SIZE` instead of
  leaving the window unsized. `last_tab` is a try/except returning `_TAB_HOME`.
  Same shape found and fixed in `_table_state.remember_columns` (a corrupt
  `columns/*` key took down the tab being built). Tests: five parametrised legs
  in `test_INV5b_corrupt_window_ini_does_not_brick_startup` + one in
  table_state; four of five and the table_state leg verified red first.

- ✅ [FIBR-0211] **Two vault reads sit outside their VaultLockedError guards.**
  From the FIBR-0204 sweep (MEDIUM, verified by reading). Two sites call into the
  vault OUTSIDE the try/except that was written to protect them:

  1. `ui/forecast.py` — `_headline_text` -> `_coverage_suffix` and
  `_provenance_text` -> `_excluded_names` each construct an AccountService and
  call `list_accounts()`, but `refresh()`'s `except VaultLockedError` closes
  before those two setText calls. The module docstring claims "every slot
  catches VaultLockedError and returns". NOTE: FIBR-0204 WIDENED this exposure
  — `_excluded_names` is now called in both forecast modes, not just ANCHORED
  — so this is worth closing promptly.
  2. `ui/categories.py:198` — `delete_blast_radius(category_id)` is one line
  ABOVE a try/except that carefully documents the auto-lock-while-the-confirm-
  box-is-open case. Same shape at `ui/rules.py` `_refresh` and the
  `leaf_categories_grouped` call before the dialog.

  No sys.excepthook is installed anywhere in src/, so these escape a Qt slot.
  Fold the reads into the guarded block in each case.
  **Layman:** In two places the app reads your data a moment after the vault may have locked itself, which can make it close unexpectedly instead of just stopping.
  Kind: fix.
  Lanes: ui.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): five unguarded reads folded into their
  guards, not the two reported. forecast.py — `refresh` now BUILDS both strings
  inside the try and only renders after it, so `_coverage_suffix` and
  `_excluded_names` are covered (the module docstring's "every slot catches
  VaultLockedError" is now true). categories.py — `delete_blast_radius` moved
  into a try. rules.py — `_refresh`'s pair (`list_rules` + `list_all`) and the
  `leaf_categories_grouped`/`sub_category_parent_names` reads that build the
  dialog in BOTH `_on_add` and `_on_edit`; the bullet named `_on_add`'s, the
  `_on_edit` twin was found by reading the sibling. Tests: one forecast leg, one
  categories leg, three parametrised rules legs — all five verified red first.

- ✅ [FIBR-0212] **Backup restore accepts a DEFLATE bomb and skips the directory fsync.**
  From the FIBR-0204 sweep (MEDIUM x3, verified by reading). Three separate
  things in services/backup.py:

  1. **DEFLATE bomb on the READ path.** The comment says "vault.db is ZIP_STORED
  — AES ciphertext is incompressible, so DEFLATE can't bomb it", which is true
  of files finbreak WRITES and irrelevant to files it READS: `_read_capped`
  never inspects `compress_type`. A ~500 KB hostile .fbk whose vault.db is
  deflated zeros inflates to the 512 MiB cap in RAM, pre-login, on the restore
  path. FIBR-0014 INV-12 explicitly requires a file_size/compress_size ratio
  check; it is not implemented. Also add MemoryError to restore_backup's
  normalisation tuple — today it escapes as an unhandled exception.
  2. **No directory fsync after the rename.** `_write_fbk` fsyncs the FILE then
  os.replace's it, but POSIX does not guarantee the directory entry reaches
  stable storage. A power loss after "Backup saved" can leave no dest at all —
  on the one artifact whose entire purpose is surviving a disaster.
  3. **The .fbk temp is O_TRUNC, not O_EXCL.** O_NOFOLLOW stops the symlink case,
  but an attacker who pre-creates a regular dest.fbk.tmp (mode 0666) in a
  shared export dir has it filled and renamed into place — the user's backup
  is then attacker-owned and world-readable. `_write_owner_only` in the same
  file gets this right with O_EXCL; the two writers differ for no stated
  reason. (pdf_export was given the O_EXCL|O_NOFOLLOW|0600 treatment in
  FIBR-0204; this is its sibling.)
  **Layman:** A malicious backup file could be crafted to eat a lot of memory when you restore it, and a power cut right after a backup could leave no file at all.
  Kind: security.
  Lanes: services.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): all three closed. (1) INV-12's ratio clause
  is implemented — new `MAX_COMPRESSION_RATIO = 100`, and `_read_capped` now
  bounds BOTH the declared-size gate and the bounded read by
  `min(cap, compress_size * ratio)`, so a lying `file_size` cannot inflate past
  what its own compressed bytes could honestly produce. MEASURED: a bomb sized
  to land exactly ON the 512 MiB cap passed every existing gate, and the test
  had to match the message — without the ratio check the restore inflates all
  512 MiB and STILL raises BackupError from the downstream "this isn't a vault"
  failure, a green that proves nothing. MemoryError normalised at `_read_entries`
  (so verify_backup gets it too, as reason "invalid") AND in restore_backup's
  tuple. (2) New `_fsync_dir` after the export's `os.replace`, best-effort since
  a directory fsync is not portable. (3) `_write_fbk` is now
  unlink-then-O_EXCL|O_NOFOLLOW|0600, the pdf_export shape; verified the
  pre-planted 0666 temp used to survive into the final backup.
  Tests: three legs in tests/features/backup, all verified red first.

- ✅ [FIBR-0213] **recategorize_auto_rows rescans the whole vault inside the import transaction.**
  From the FIBR-0204 sweep (MEDIUM, verified by reading). `commit_import`'s
  comment says it will "categorise the just-inserted rows (auto/NULL)", but
  `recategorize_auto_rows` iterates `tx_repo.auto_rows()` — EVERY auto row in the
  vault, all accounts, all statements.

  Two consequences. Cost: importing a 20-row CSV into a 50k-row vault runs 50k
  `categorize_with_library` calls plus their UPDATEs inside the write transaction
  holding the DB lock, on the GUI thread. Surprise: if the built-in library
  changed between releases, importing one small statement silently re-files
  hundreds of unrelated historical rows, moving every chart and report.

  At minimum correct the comment. Better: scope the recompute to the rows this
  import inserted (or to the period), and make a full re-file an explicit user
  action. A separate measured finding: rule and library patterns are re-folded
  once PER TRANSACTION ROW inside the loop (`categorization.py` and
  `category_library.py`), measured 0.397s -> 0.120s for 20k rows x 113 patterns
  when folded once up front — fold them in `_match_inputs`.
  **Layman:** Importing a small statement quietly re-sorts every transaction you have ever imported, inside the same operation — slow on a big history, and it can move numbers you were not expecting to change.
  Kind: fix.
  Lanes: services.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): both halves done, and the comment did not
  need correcting — the CODE was changed to match what it always claimed.
  Scoping: `recategorize_auto_rows(conn, *, min_txn_id=0)` + `auto_rows(min_txn_id
  =)` + a new `TransactionRepository.max_id()`. `commit_import` reads max_id()
  INSIDE its transaction just before the inserts; SQLite gives a new INTEGER
  PRIMARY KEY row max(rowid)+1, so the boundary is exact with no per-row id
  round-trip. A whole-vault re-file is now only the Rules tab's "Apply now" — leg
  (b) of FIBR-0010 INV-4, which was already an explicit user action, so no new UI.
  INV-4 + D9 updated in docs/specs/FIBR-0010.md; the feature spec's "or the next
  import" clause no longer holds and says so. Folding: new `fold_rules` /
  `fold_entries`, and `_match_inputs` returns folded pairs. Both one-shot matchers
  now delegate to the same `*_folded` loop the recompute path uses, so folding
  once cannot diverge from folding per call. MEASURED here 0.429s -> 0.067s over
  20k rows x 113 patterns (load avg 0.35; both runs identical to 3dp). Tests:
  counted, not timed — 12 rows x 8 patterns went 120 folds -> 20. Both legs red
  first.

- ✅ [FIBR-0214] **Theme palettes miss WCAG on borders, stripes, muted text and one focus ring.**
  From the FIBR-0204 sweep (MEDIUM x3, ratios COMPUTED with the real WCAG
  formula, not estimated). The selected-row text was CRITICAL and is already
  fixed in FIBR-0204; these are the remainder, and each needs a palette decision
  rather than a code fix:

  - **1.4.11 non-text contrast (needs 3:1) — control borders fail on every
  theme.** `border` is the 1px edge on QLineEdit/QComboBox/QPushButton/
  QGroupBox, i.e. the only thing identifying an input's bounds: ledger 1.36,
  parchment 1.42, mint 1.27, midnight 1.41, graphite 1.43, emerald 1.61
  (against `window`). Ledger's FOCUS RING is also short at 2.87 — accent
  #b8892b on #f5f4ef — and the same value is the selected-tab underline. The
  other five focus rings pass (3.22-8.25).
  - **Alternating row stripes are invisible.** alt_base vs base: 1.16-1.27
  across the six. `polish_item_views`' docstring claims it makes stripes
  "visible"; at these ratios they are not. Decorative, so not a WCAG failure —
  but the stated purpose is not met.
  - **1.4.3 (needs 4.5:1) — muted_text where it is LIVE, not disabled.**
  `muted_text` is the QHeaderView::section and unselected QTabBar::tab colour:
  ledger 4.39, parchment 3.36, mint 4.30. Its Disabled-palette use IS exempt;
  these are not. Related: `Link` is `accent_soft` at 1.25-2.86 and links do
  render (update_dialog sets setOpenExternalLinks(False) on a notes widget).

  The theme suite now has INV-4a computing ratios per theme (FIBR-0204) — extend
  that harness to these pairs rather than writing a second one. Open question the
  reviewer raised and I could not answer from the docs: is there a contrast
  budget for the palettes at all? Neither FIBR-0127 nor ADR-0010 states one.
  **Layman:** Some of the colours in the themes are too faint to see easily — input outlines, the alternating row shading, and some grey text. Needs a design pass with the contrast numbers checked.
  Kind: accessibility.
  Lanes: ui.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): the open question the bullet raised — is there a contrast budget at all? — is answered and written down as FIBR-0127 INV-4b. User chose the low-visual-cost set over a full AA restyle (2026-08-03). Verified every ratio in the bullet against source first; all six border figures, ledger's 2.87 focus ring, the 1.16-1.27 stripes, muted 4.39/3.36/4.30 and the 1.36-2.86 links all reproduced exactly. FIXED (invisible side by side): muted_text ledger #6b7280->#69707d, parchment #8a7a63->#726552, mint #5f7a6f->#5c766b (all now >=4.5:1 on window); ledger accent #b8892b->#b2842a (focus ring 2.87->3.06); Link role accent_soft->accent (1.36-2.86 -> 3.16-8.83 on base — accent_soft stays live as the QSS button gradient, so INV-4's no-unused-token half still holds). DELIBERATELY UNMET, recorded rather than ignored: input borders at 1.27-1.61 (reaching 3:1 means #d8d3c4->#998c65 on ledger — a visible restyle of all six); Link under 4.5:1 on the light themes (4.5 would make a link indistinguishable from body text, and every link in the app is non-clickable by design); alt_base stripes at 1.16-1.27 (decorative, outside SC 1.4.11 — and polish_item_views' "visible" claim is corrected). Three legs added to the INV-4a harness as the bullet asked, not a second one. All three red first.

- ✅ [FIBR-0215] **Three toolbar glyphs are unmapped, so they never hover-brighten or re-tint.**
  From the FIBR-0204 sweep (MEDIUM, verified by reading). `icons._ICON_HUES`
  omits `transactions`, `statements` and `export` — all three ARE toolbar action
  icon names with SVGs on disk. `toolbar_icon` returns a plain `icon(name)` for
  them, which adds no Active/Selected pixmap, so the module docstring's "vibrant
  one on hover" and "tuned to the active light/dark theme" simply do not happen
  there, and `_retint_toolbar_icons` re-installs an identical icon.

  Theme INV-10 is phrased as "a MAPPED action's icon cacheKey() changes", so the
  test is shaped around the gap rather than catching it. Contrast is fine
  (#808080 scores 3.18-4.39 on all six windows) — this is consistency, not
  accessibility. Decide whether the omission was deliberate visual hierarchy; the
  docstring's "any glyph not listed stays neutral grey" reads as a fallback for
  UNUSED glyphs, not for three live toolbar buttons.
  **Layman:** Three of the toolbar buttons do not light up when you hover over them, and do not change shade when you switch theme, unlike the other ten.
  Kind: fix.
  Lanes: ui.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): user decided the omission was an oversight, not hierarchy — all three mapped. `transactions` 237 (blue-violet), `statements` 69 (olive-gold), `export` 357 (coral), placed in the three widest gaps in the existing wheel (38-100, 210-265, 330-25 wrapping) so no pair sits closer than the 13 degrees `lock` and `categories` already do. The bullet's read of the test was right: INV-10 asserted the re-tint for ONE action, which proves the mechanism and not the coverage, so it stayed green for as long as the gap existed. Now asserted over the whole `_icon_actions` set — nothing in it missing from `_ICON_HUES`, every glyph's pixmap changes light->dark, and every mapped glyph's Active pixmap differs from its Normal one — so a future toolbar action that forgets its hue is caught the day it lands. Red first, naming exactly the three.

- ✅ [FIBR-0216] **Assorted MEDIUM/LOW findings from the FIBR-0204 sweep, batched.**
  From the FIBR-0204 sweep. Each verified against source; none reached CRITICAL
  or HIGH, so they were deferred by user decision rather than fixed in that pass.

  **Correctness / robustness**
  - `parse_transaction` has no upper bound; a pasted `1E19` reaches SQLite and
  raises OverflowError (NOT ValueError), escaping ManualEntryDialog's slot.
  Exact bound: 9223372036854775807 minor units. Range-check and raise
  ValueError like every other rejection.
  - `standard_bank._draft` is called from bare loops with no per-row try, so a
  legitimate 0.00 statement line (a zero fee, "interest capitalised 0.00")
  aborts the WHOLE statement import with "amount must be non-zero" — which
  reads as an app bug. csv_importer degrades per row; this should too.
  - `services/transactions.py` validates the date but does not canonicalise it:
  `date.fromisoformat` accepts "20260715" and "2026-W29-3" and stores them
  verbatim, and everything downstream compares dates as STRINGS. No current
  caller reaches it (all paths go through strptime().isoformat() or a
  QDateEdit) — latent, one-line fix.
  - `_coverage_suffix` (ui/forecast.py) counts ALL accounts as its denominator,
  so a vault holding any debt/investment account always shows the partial-total
  suffix even when every CASH account contributed. Compare against the cash
  count instead.
  - Two same-day charges from one merchant collapse into a single recurring item
  (grouping is `(direction, merchant_key)` and the amount is a median), so the
  forecast projects R199/month against a true R398. Also inflates the "Seen"
  count, which can push occurrences past the new-recurring alert threshold and
  silently suppress that alert. Document at minimum.

  **Amount / locale**
  - Display is locale-aware (QLocale) but input is C-locale only, so a de_DE user
  cannot type back the number the app just showed them (`1.234,56` is
  rejected). The manual-entry placeholder is tr()-able while the parser is not,
  which makes the translation actively misleading.
  - `negative_style` is a magic string (`== "brackets"`) in a codebase that uses
  StrEnum for all nine other closed token sets.

  **UI polish**
  - Alerts dialog dismiss buttons are a bare tr("✕") with no accessibleName — a
  screen reader announces N identically-unnamed buttons (WCAG 4.1.2), and the
  bare glyph gives translators no context.
  - Every dismiss recomputes the whole alert set TWICE (the dialog re-renders,
  then the shell's `changed` signal re-runs it), each a full unfiltered
  transaction scan plus a recurring-detection pass.
  - File -> Quit is disabled while locked (the whole File menu is), so on the
  app's default startup surface there is no menu route to exit — and there are
  no keyboard shortcuts or menu mnemonics anywhere in the app
  (`grep setShortcut|QKeySequence` returns nothing), so no Ctrl+Q either.
  - A manual update check returning after a lock pops a QMessageBox over the
  lock screen; every sibling guards on `self._dialog is prompt`.
  - An auto-lock during a nested modal loop (Help->About, a QFileDialog) defers
  the workspace's deleteLater indefinitely, so decrypted rows survive in the
  hidden widget until the user dismisses the box — the unattended case
  auto-lock exists for.
  - StartOverDialog's confirm word is inside a tr() string, so a translated build
  tells the user to type a word the comparison will never accept, permanently
  disabling OK. The module docstring claims the opposite.
  - PDF export can leave a stuck wait cursor (no `finally`, unlike the two backup
  handlers).
  - Dark-theme PDF page numbers render black on the dark page background.

  **Docs / dead code**
  - FIBR-0172 still specifies an `AlertsCard` in HomeView; FIBR-0185 replaced it
  with a dialog and grep finds zero hits for `dashboard_alerts`/`AlertsCard`.
  - FIBR-0006 describes a Type combo on the category Add form that does not
  exist, claims two-level depth (the UI renders unbounded), and says the
  service does NOT guard re-parent cycles (it does).
  - `select_by_index` has almost no production caller — both wrappers
  (`StatementsWidget._select_period`, `TransactionsView._select_txn`) are
  documented as test/shell accessors with zero non-definition hits in src/.
  - `ExportDialog._export_button()` has zero callers in src/.
  - The `.old` restore stamp is second-resolution, so two restores inside one
  second silently discard the first recoverable copy.
  **Layman:** A collection of smaller issues found in the big code review — none of them break anything today, but each is worth tidying.
  Kind: fix.
  Lanes: ui, services.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): worked the batch in four commits. Fixed:
  StartOverDialog's tr()'d confirm word (a translated build could never confirm);
  standard_bank's 0.00 row aborting a whole statement; parse_transaction's missing
  upper bound (OverflowError, not ValueError, escaping the slot); the PDF export
  wait cursor's missing finally; decrypted rows surviving an auto-lock through a
  nested modal loop; two update-check boxes over the lock screen;
  _coverage_suffix's all-accounts denominator; date canonicalisation; the .old
  stamp's second resolution; the alerts dismiss buttons' accessibleName; the
  double alert-set recompute per dismiss; Quit unreachable while locked (+ the
  app's first shortcut, Ctrl+Q); negative_style -> NegativeStyle StrEnum; the
  misleading tr()'d amount placeholder. Documented: the same-day recurring
  collapse (both plausible fixes break a real case, so it needs evidence);
  FIBR-0172's AlertsCard section and FIBR-0006's D9 + cycle-guard claims;
  _export_button as a test accessor.

  THREE corrections to the bullet, each verified against source:
  (1) `select_by_index` is NOT near-dead — it has three production call sites
  (transactions.py, statements.py, accounts.py). Dropped, not silently filtered.
  (2) `ExportDialog._export_button()` has zero src/ callers but IS a live test
  accessor, so it is labelled rather than removed.
  (3) The dark-theme PDF page numbers and the locale amount input each turned out
  too large for a batch and are split out as FIBR-0217 and FIBR-0219. FIBR-0219
  in particular: the obvious locale fix MEASURED as a silent 100x error (de_DE
  turns a typed -12.34 into -1234), strictly worse than today's rejection — a
  hazard the original finding did not name.

- 📋 [FIBR-0217] **Dark-theme PDF page numbers render black on the dark page.**
  Split out of FIBR-0216 after an implementation attempt showed it is not a
  batched-polish-sized fix. MEASURED with pdfplumber: the footer page number
  comes out `non_stroking_color == (0, 0, 0)` while the body text is `0.902`,
  and the dark theme's page background genuinely renders (a filled rect
  `(10,10)-(585,832)` in `#242830`, confirmed by rasterising — corner pixel
  RGB(36,40,48)). The number sits inside that rect, so it is black on
  near-black, about 1.3:1.

  `QTextDocument::print_` draws that number itself using the painter's default
  pen, and the painter is created inside `print_` — unreachable. Qt suppresses
  its own numbering only when the document is ALREADY paginated, so the fix
  shape is to paginate + paint the pages ourselves and draw the footer in the
  theme's ink.

  **Attempted and reverted 2026-08-03.** Reproducing what `print_` does
  internally is version-sensitive and it regressed pagination twice against a
  direct A/B harness: without Qt's DPI transform the whole report rendered at
  about 1/12 scale in the page corner (1 page instead of 8); with the transform
  applied it still came out 7 pages instead of 8 and the body glyphs landed at
  x=10 rather than x=66, because `print_` also reserves the page-layout margins.
  Getting this right needs its own pass with page-by-page visual verification —
  the wrong risk to take inside a batch of small fixes, on a money report.

  The A/B harness is the asset to keep: render the same HTML through
  `doc.print_` and through the replacement, then compare page count and every
  body glyph's (text, x0, top) via pdfplumber. Identical body glyphs + a
  theme-coloured footer is the acceptance gate, and it makes the regression risk
  measurable rather than hoped-at.
  **Layman:** On a dark-themed PDF report the little page number at the bottom is black on a nearly-black background, so you cannot read it.
  Kind: fix.
  Source: in-session-2026-08-03 (split out of FIBR-0216).

- 📋 [FIBR-0218] **The AppImage installs no launcher, so a hand-made one shows a second panel icon.**
  Reported by the user 2026-08-03 with screenshots: two finbreak icons in the
  KDE panel while running 0.1.19 (the latest). DIAGNOSED on their machine, not
  inferred.

  Root cause is an app-ID mismatch, and finbreak's own side is correct. On
  Wayland KDE associates a window with a pinned launcher by matching the window's
  `app_id` to the launcher's desktop-file BASENAME. `app.py` sets
  `QGuiApplication.setDesktopFileName("io.github.milnet01.finbreak")` and the
  AppImage bundles `io.github.milnet01.finbreak.desktop` — consistent. But the
  user's panel pinned `~/.local/share/applications/finbreak.desktop`, a
  hand-rolled launcher whose basename id is `finbreak`, so KDE saw a pinned
  launcher and an unrelated window. (`StartupWMClass=finbreak` in that file is
  the X11 key and is ignored on Wayland — a trap, since it LOOKS like the
  association key.)

  Resolved for the reporter by renaming their launcher to
  `io.github.milnet01.finbreak.desktop` and pointing `Icon=` at the installed
  `io.github.milnet01.finbreak` hicolor PNGs.

  The product gap: the AppImage installs no desktop entry of its own, so a user
  who wants a menu/panel entry hand-writes one and will usually name it
  `finbreak.desktop` — reproducing this. Options to weigh: (a) document the
  required basename in the README's AppImage install section (cheapest, and the
  README is refreshed every release anyway); (b) have the AppImage offer to
  install a correct launcher on first run, the way many AppImages do; (c) rely on
  AppImageLauncher, which does it correctly but is not installed by default on
  openSUSE. (a) is the minimum and should ship regardless of the rest.

  Also observed on the reporter's machine, and NOT part of this item: three
  concurrent installs — the AppImage 0.1.19, an RPM/deb providing
  `/usr/share/applications/io.github.milnet01.finbreak.desktop`, and a Flatpak
  `io.github.milnet01.finbreak` still on 0.1.16. Worth asking whether the docs
  should warn that the three can shadow each other's launchers.
  **Layman:** If you make your own shortcut for the AppImage, finbreak shows up twice in the taskbar — once for the shortcut and once for the running window.
  Kind: fix.
  Source: user-report-2026-08-03.
  Progress (2026-08-19): option (a) SHIPPED -- the README's AppImage install section now tells you to name a hand-made shortcut io.github.milnet01.finbreak.desktop rather than finbreak.desktop, points Icon= at the installed hicolor id, and says outright that a differently-named one gives you two panel icons. It also names the StartupWMClass trap: right on X11, ignored on Wayland, which is what makes the wrong file look correct. The bullet called (a) "the minimum and should ship regardless of the rest", so this is that. STAYS OPEN for (b) and (c): the AppImage still installs no launcher of its own, so this is guidance a user has to find rather than a product that does the right thing unaided. (b) offering to install a correct launcher on first run remains the real fix. Also still unanswered, and recorded here so it is not lost: whether the docs should warn that a concurrent AppImage, RPM/deb and Flatpak install can shadow each other's launchers -- observed on the reporter's machine with three versions live at once.

- ✅ [FIBR-0219] **Amount input is C-locale only, and the obvious fix silently multiplies by 100.**
  Split out of FIBR-0216 because implementing it turned up a hazard the original
  finding did not name, which changes what the fix has to be.

  The gap is real: display goes through `QLocale().toString()` (grouped,
  locale-correct separators — `_amount.py`), while input goes straight to
  `parse_transaction`, which does `Decimal(str(raw).strip())` — C locale only. So
  a de_DE user is shown `R 1.234,56` and cannot type it back.

  **The naive fix is worse than the bug, and this is the reason to be careful.**
  "Strip the locale group separator, swap its decimal point for a dot" is the
  obvious normalisation, and MEASURED under de_DE (group `.`, point `,`) it turns
  a typed `-12.34` into `-1234` — a silent 100x error, on a money field, with no
  rejection anywhere. Today that same input is simply refused, which is safe. A
  fix that trades a refusal for a silent 100x error is a regression however good
  the intent. The full measured matrix (en_US / de_DE / fr_FR, four input forms
  each) was taken 2026-08-03; fr_FR is a third shape again, grouping with U+202F.

  So the design question this needs answered first is what happens to an AMBIGUOUS
  input, not how to parse an unambiguous one. Sketch worth evaluating: normalise
  via the locale AND via the C rules, and accept only when the two agree on a
  value; when they disagree, refuse with a message naming the format the app
  displays. That keeps every unambiguous input working in both conventions and
  turns the dangerous case into a visible refusal rather than a wrong number.
  Whatever is chosen needs a per-locale test matrix, since the failure mode is
  silent and off by a factor of 100.

  Done already under FIBR-0216: the manual-entry placeholder was a tr()-able
  `"e.g. -12.34"` while the parser is C-locale only, so a translated build asked
  for `-12,34` and then rejected it — actively misleading. It is now a
  non-translatable `-12.34`, an example of a machine format (coding.md § 5.2),
  so the hint cannot disagree with the parser. That removed the harm ahead of
  the locale gap; the gap itself is now closed here, and the placeholder stays
  exactly as FIBR-0216 left it — INV-3 makes the C form valid under every
  locale, so hint and parser still cannot disagree.
  **Layman:** If your computer is set to a language that writes numbers as 1.234,56 you cannot type an amount back the way finbreak just showed it to you.
  Kind: fix.
  Source: code-quality-review-2026-08-03 (split out of FIBR-0216).
  Spec written and gated (2026-08-04): docs/specs/FIBR-0219.md, ACCEPTED
  after 5 cold-eyes loops (§13 is the ledger). The design call this bullet
  left open is made: validate with QLocale (which checks group PLACEMENT, so
  de_DE rejects "-12.34" instead of reading it as -1234), rebuild the Decimal
  exactly from the string, accept when both conventions agree, refuse when
  they disagree — and, the part the bullet did not anticipate, refuse by
  SHAPE when only one convention parses at all.

  That last rule exists because the review found the two-parser test is blind
  to the real hazard: en_ZA (the base-currency locale) reads "1,500" as 1.5
  while the C convention simply rejects it, so one candidate survives and is
  stored as 150 minor units where the user meant 150 000. Silent 1000x, and
  a regression against today's refusal. Two further variants of the same hole
  were found and closed in later loops (a bounded head let "1234,500"
  through; a hardcoded separator set let de_CH's "1'234.500" through).

  Also surfaced and filed separately: FIBR-0222, a pre-existing
  decimal.Overflow from to_minor's scaleb that escapes _on_add as a non-
  ValueError and crashes the dialog — reachable today, independent of this
  item.

  Next: TDD implementation against INV-1..INV-9.
  Resolved (2026-08-05): `parse_amount_input` + `_locale_decimal` in
  `src/finbreak/ui/_amount.py`, wired at the one typed-amount seam
  (`ManualEntryDialog._on_add`). QLocale validates group PLACEMENT, the Decimal is
  rebuilt exactly from the string (never Qt's float), the two conventions must
  agree, and a `^[+-]?\d+(?:[.,]\d+)*[.,]\d{3}$` shape guard refuses the
  one-surviving-candidate case AFTER the agreement test — so en_US keeps the
  `.`-tail forms it stores today. `parse_transaction` and the three importers are
  untouched and stay C-locale only (INV-1).

  75 legs in `tests/features/amount_input/` cover INV-1..INV-9 across
  en_US / en_ZA / de_DE / fr_FR / sv_SE. TDD: the suite went red on exactly one
  leg — the positive dialog leg the spec names as the only one that fails when the
  call site is omitted — and green on wiring it.

  Accepted trade recorded in the spec's § 6: under the comma-decimal locales
  `1.500`, `1.250`, `2.000`, `0.100`, `12.500` and `1234.500` are stored today and
  are refused after this, because the same shape is how `1,500` → 1.5 arrives.
  `1,50`, `1.50` and `1500` all work. The mirror hazard under a `.`-decimal locale
  (a European pasting `1.500`) is deliberately retained — the app does the same
  today and refusing it would cost every en_US user.

- 📋 [FIBR-0220] **Agreeing with a "~ guess" cannot teach the app — the no-nag gate has no escape hatch.**
  Reported by the user 2026-08-03. VERIFIED against source; the current
  behaviour is deliberate and documented, and the gap is a missing action rather
  than a defect.

  What happens today. Right-click a `~ guess` row -> Set category -> the picker
  opens with the guessed category ALREADY selected (`_on_set_category` passes
  `txn.category_id`). Accepting it calls `set_manual_category`, which writes
  `(same_id, 'manual')` — the source differs from `'library'`, so the row really
  is written and the `~` marker clears (`transactions.py:354` renders the marker
  only for `category_source == 'library'`). So the row IS confirmed and frozen.

  But `_maybe_offer_rule` returns early when `chosen == would_categorize(desc)`
  (`transactions.py:427`), and `would_categorize` includes the LIBRARY layer
  (`categorization.py:293-301`, FIBR-0139 D4 — which explicitly supersedes
  FIBR-0010 INV-5's rules-only phrasing: "confirming a library guess raises no
  learning nag; overriding one still offers the rule"). Agreeing with a guess is
  therefore, by construction, the one case that can never produce a rule.

  Consequence: confirming a guess fixes exactly one row. The next import of the
  same merchant is a `~ guess` again, and the user repeats the work per
  statement. The only two routes to a persistent rule are to pick a DIFFERENT
  category (tripping the "differs" check) or to hand-write one on the Rules tab —
  neither discoverable from the row being looked at.

  The no-nag rule itself is right and should stay: a modal offer on every
  agreement would be intolerable. What is missing is an explicit, opt-in action.
  Candidates, cheapest first: (a) a second context-menu item on a guessed row —
  "Always file <merchant> here" — that skips the differs-check and opens the
  existing `RuleEditDialog` pre-filled exactly as the learn offer does, reusing
  `_maybe_offer_rule`'s dialog and `_apply_learned_rule` wholesale; (b) a
  "remember this" checkbox in the CategoryPickerDialog; (c) a bulk "turn my
  confirmed guesses into rules" pass. (a) is the smallest and is the one route
  that starts where the user already is.

  Whichever ships, the merchant-key question needs deciding: the learn offer
  pre-fills the rule with the FULL description and tells the user to trim it to a
  keyword. For a guess-derived rule the library's own matched pattern is the
  better default, since it is already the generalised merchant token — but that
  means surfacing which library pattern matched, which `match_library` currently
  discards (it returns only the category id).
  **Layman:** When the app guesses a category correctly, saying "yes, that's right" only fixes that one row — the next statement guesses again. There is no way to say "always file this shop here".
  Kind: enhancement.
  Source: user-report-2026-08-03.

- ✅ [FIBR-0222] **A huge exponent crashes the Add-transaction slot before the 64-bit bound is reached.**
  Surfaced by the FIBR-0219 spec review; VERIFIED against source, and
  independent of that item (it reproduces on today's shipping code).

  MEASURED 2026-08-04:
  `parse_transaction("2026-07-01", "1e999999", "x", 2)` raises
  `decimal.Overflow`, not `ValueError`. The value is a finite Decimal, so
  the `is_finite()` check passes; the fractional-digit check passes; then
  `to_minor` does `amount.scaleb(exponent).to_integral_value()` and
  `scaleb` overflows the Decimal context BEFORE `_MAX_AMOUNT_MINOR` is
  ever compared.

  `decimal.Overflow` is an `ArithmeticError`, so `ManualEntryDialog._on_add`'s
  `except ValueError` does not catch it and the Qt slot dies. Reachable by
  typing `1e999999` into the Amount field today.

  This is exactly the class FIBR-0216 closed when it added the 64-bit
  `_MAX_AMOUNT_MINOR` guard ("a class no caller catches, unlike the
  ValueError every other rejection here raises") — the guard just sits one
  step too late to catch an exponent this large.

  Fix shape: bound the exponent before scaling (or wrap `to_minor`'s call
  and re-raise as `ValueError`), so every rejection out of
  `parse_transaction` remains a `ValueError` as its docstring promises.
  Needs a regression leg driving the dialog, not just the parser.
  **Layman:** Typing a a number like 1e999999 into the Add-transaction box closes the dialog instead of showing "that's too big".
  Kind: fix.
  Source: cold-eyes-FIBR-0219-loop2-2026-08-04.
  Resolved (2026-08-05): reproduced first — `parse_transaction("2026-07-01",
  "1e999999", "x", 2)` raised `decimal.Overflow` from `to_minor`'s `scaleb`,
  and the dialog leg died in `_on_add` rather than showing an error.
  `parse_transaction` now wraps the `to_minor` call and re-raises `Overflow`
  as `ValueError("amount is too large to store")` — deliberately the same
  message as the 64-bit bound below it, since it is the same rejection. Guard
  placement: after the scaling rather than a second magnitude bound before it,
  so `_MAX_AMOUNT_MINOR` stays the ONE stated bound and cannot drift from a
  duplicate expressed as an exponent. `Overflow` is caught narrowly, not
  `DecimalException`: with a finite operand and a currency exponent of 0-3 it
  is the only trapped signal reachable there (a huge NEGATIVE exponent is
  already rejected one check earlier, verified).
  Regression legs in tests/features/vault/: two rows on the INV-4b reject
  table (both signs) plus `test_INV4b_dialog_refuses_a_huge_exponent_instead_of_dying`,
  which drives ManualEntryDialog — the class distinction is invisible from the
  parser's side. All three verified RED before the fix. spec.md INV-4b now
  states that ValueError is the class for every rejection, magnitude included.

- ✅ [FIBR-0223] **The OFX closing-balance scaling is the one to_minor call site with no ValueError guard.**
  Surfaced while sweeping to_minor's call sites for FIBR-0222. PARTLY
  verified — read the code, did NOT reach it with an input.

  `src/finbreak/importers/ofx_importer.py:153` scales the `<LEDGERBAL>`
  straight through: `closing_balance_minor = None if balance is None else
  to_minor(balance, exponent)`. Every OTHER amount in that file goes
  through `parse_transaction`, whose ValueError the row loop catches into
  `RowError`; this one has no guard, and its own neighbouring comment
  records that this line runs OUTSIDE the wizard's boundary try/except
  (the reason `getattr(statement, "balance", None)` is there at all).

  So a `<BALAMT>` large enough to overflow `scaleb` raises
  `decimal.Overflow` — an ArithmeticError, uncaught — exactly the class
  FIBR-0222 just closed inside `parse_transaction`. FIBR-0222's fix does
  NOT cover this path.

  NOT YET VERIFIED: whether ofxparse admits exponent notation in
  `<BALAMT>` at all. Three attempts to build a driving fixture failed for
  unrelated reasons (the hand-rolled OFX would not parse, and reusing
  `tests/features/ofx_import`'s own `_stmt`/`_txn` helpers outside pytest
  did not either) — so the reachability is open, not disproven. Start
  there: if ofxparse rejects the token first, this is unreachable and the
  bullet closes as a note; if it does not, the fix is a try/except around
  the one call, mirroring FIBR-0222.

  Also worth a look in the same pass: `standard_bank.py:492/493/560/567`
  and `1102` scale PDF-derived amounts through the same helper.
  `_parse_amount` strips separators and never yields an `e`, so plain
  digit runs cannot overflow the context — believed safe, unverified.
  **Layman:** A corrupt bank file could crash the import wizard instead of reporting the bad line.
  Kind: fix.
  Source: in-session-2026-08-05 (FIBR-0222 call-site sweep).
  Resolved (2026-08-05): REACHABLE — the open question is answered no.
  ofxparse's `toDecimal` hands `<BALAMT>` straight to `Decimal(...)` and
  catches only InvalidOperation, so exponent notation survives the parse;
  a real OFX document carrying `1e999999` drove `decimal.Overflow` out of
  `OfxImporter.parse` end to end (confirmed RED before the fix).

  The pass also found a SECOND crash on the same line, not in the bullet:
  `1e30` scales cleanly to 10**32 and dies far away at the INSERT as an
  `OverflowError` past SQLite's 64-bit INTEGER. `_select_ofx` catches
  ValueError at parse time and `_on_import` catches it at commit time, so
  each was a dead Qt slot at a different moment.

  Fix: extracted `to_minor_storable` in services/transactions.py — the
  scaling plus BOTH magnitude rejections, raised as the ValueError every
  caller already renders. `parse_transaction` now calls it too, so
  `_MAX_AMOUNT_MINOR` stays the ONE stated bound rather than being copied
  into the importer (FIBR-0222's design call, preserved). The OFX site
  re-raises in this file's INV-4 voice ("this OFX file's closing balance
  is not a usable amount").

  Covered by tests/features/forecast/spec.md INV-7a — three legs in
  test_importer_capture.py (huge exponent, ±1e30), all confirmed RED
  first. Gate green: 1691 passed, 2 skipped.

  The standard_bank.py sites named above did NOT close with this one; the
  residue is filed separately (see the bullet below).

- ✅ [FIBR-0224] **The Standard Bank closing balance can still exceed what SQLite can store.**
  Split out of FIBR-0223 rather than fixed with it — the reachability
  story is different and the test cost is much higher (it needs crafted
  PDF fixtures, not a 6-line SGML string).

  `standard_bank.py:1102` is the same shape FIBR-0223 just closed:
  `closing_minor = None if closing is None else to_minor(closing,
  exponent)`, with no bound. Two halves, and only the first is closed:

  - **Exponent overflow: NOT reachable, verified.** `_parse_amount`
  strips `R`, spaces, `-` and separators and parses what is left, and
  `_money_tokens` never yields a token containing an `e`, so `scaleb`
  cannot overflow the Decimal context there. FIBR-0223's first failure
  mode does not exist on this path.
  - **The 64-bit bound: reachable, unverified by an input.** A plain
  digit run of 20+ digits parses fine, scales fine, and only dies at
  the INSERT as `OverflowError` — the class `_on_import` does not
  catch. `_verify_checksum` (line 1095) runs FIRST and is a strong
  gate: it requires `opening_m + Σ drafts == closing_m`, and every
  draft is already bounded by `parse_transaction`. But `opening` is
  NOT bounded (`to_minor` at 492/493), so a statement printing a huge
  opening AND a matching huge closing reconciles and reaches 1102.
  Narrow, but a crafted file, and this is untrusted input.

  Fix shape is one line plus a wrap, mirroring FIBR-0223: route 1102
  (and 492/493) through `to_minor_storable` and re-raise in this file's
  own voice. The work is the fixtures: a Family B/D statement whose
  opening and closing both exceed int64 and still reconcile.

  Also unswept: `services/forecast.py:227` and `services/alerts.py:211`
  and `228` scale a recurring item's amount through bare `to_minor`.
  Those read values that already round-tripped through the DB (so they
  are bounded by construction), but that has not been checked.
  **Layman:** A crafted PDF statement could crash the import at the last step instead of reporting a bad figure.
  Kind: fix.
  Source: in-session-2026-08-05 (FIBR-0223 call-site sweep).
  Resolved (2026-08-05): both halves closed, plus a THIRD site the
  analysis missed. `_storable` (standard_bank.py) wraps
  `to_minor_storable` and re-raises in this file's voice; all four
  balance conversions now route through it — `_verify_checksum`
  492/493, `_verify_e_totals`, and `parse`'s closing_minor.

  The missed site is `_verify_e_totals`. Family E prints no closing,
  so `_verify_checksum` takes its `closing is None` early return and
  never converts the opening — which `_verify_e_totals` then scales
  into `opening + Σ` and persists as the forecast anchor. Same defect
  class, different family, and it was not in the original analysis.

  Regression cover: `family_b_unstorable_balances.pdf` — opening
  99,999,999,999,999,999.00 + 69.00 == closing, both past 2**63-1,
  so it RECONCILES and clears every pre-existing gate (reproduced
  before the fix: parse returned 10000000000000006800 and the INSERT
  died with OverflowError). Plus direct legs on both gates, on
  deliberately non-reconciling pairs so the bound must win over the
  "didn't add up" message. Filed as INV-11b in the test contract;
  pre-E fixture count 13 → 14 in the two guard assertions.

  The unswept tail is CLEAN, not fixed: forecast.py:227 and
  alerts.py:211/228 each scale a `RecurringItem.amount`, which is
  `to_display_decimal(stored_minor)` — a round-trip of a value the
  DB already holds, so bounded by construction. Verified, no change.

- ✅ [FIBR-0225] **Lint the gate's own delivery machinery: shellcheck + actionlint stages.**
  The gate checked `src/` and `tests/` thoroughly and never looked at the
  11 shell scripts and 3 workflows that BUILD, TEST and PUBLISH every
  release. A bug in `release-linux.sh` ships a broken release and no
  Python stage can see it.

  Both tools are CLEAN on the current tree (0 findings each), so this is a
  regression guard rather than a backlog — the cheapest kind of stage to
  add, and it was simply never wired up. `actionlint` additionally pipes
  each workflow `run:` block through `shellcheck`, covering shell bugs
  embedded in YAML that the plain `shellcheck` stage cannot see (it is not
  looking at .yml).

  Pinned in `ci-setup.sh` (shellcheck 0.11.0, actionlint 1.7.12 — both the
  current upstream latest, both matching the versions installed locally)
  for exactly the reason gitleaks is pinned: a different release runs a
  different rule set over the same files, so an unpinned build passes
  locally and fails in CI. Both release URLs verified 200.

  Amends FIBR-0001 INV-1, which enumerated the P01 stage list and had also
  drifted: it never recorded the `mypy` stage FIBR-0061 added. Both gaps
  closed in one edit; INV-1 now carries a "stages added after P01" list.
  **Layman:** The scripts that build and publish releases are now checked by the same gate that checks the app.
  Kind: security.
  Source: user-request-2026-08-05 (scan the system for audit tools we could add to the gate).
  Resolved (2026-08-05): both stages live in ci-local.sh, pinned in
  ci-setup.sh (shellcheck 0.11.0, actionlint 1.7.12), verified in the CI
  image via ci-docker.sh — not just on the desktop, since the change
  touches ci-setup.sh and a green local run cannot prove the clean-runner
  install path. Container run exit 0; gate green 1691 passed, 2 skipped.
  FIBR-0001 INV-1 amended (also picking up the undocumented mypy stage
  from FIBR-0061). Commit e3959e2.
  Cold-eyes on FIBR-0001 (2026-08-05, 3 loops, 2 cold lanes each):
  32 verified findings, all fixed. Converged at loop 3 — findings
  halved each loop (14 → 12 → 6).

  It found a real gap in THIS item as shipped: the shellcheck stage
  globbed `scripts/*.sh` and so skipped the seven packaging recipes
  under packaging/obs/ and packaging/flatpak/ — the OBS/Flathub publish
  path the stage's own rationale claimed to cover. Now selected via
  `git ls-files '*.sh'`, which cannot go stale; all seven were already
  clean. Also caught loop 1 abbreviating the gitleaks row to
  `gitleaks dir .`, dropping --redact — on a public repo that is the
  difference between catching a leaked credential and printing it into
  a world-readable CI log.

  The durable outcome is tests/features/harness/: INV-1's "one list"
  guarantee was prose discipline with no check behind it, which is why
  the gate list drifted twice in one day undetected. The suite now
  compares the spec's stage table against ci-local.sh as an unordered
  set and regression-locks --redact and the git ls-files selector.
  Gate green 1698 passed, 2 skipped. Commits 0441d4c, fef5867, e48d16d.

- ✅ [FIBR-0226] **Harden the workflows against zizmor's supply-chain findings.**
  `zizmor 1.29.0` (installed, NOT yet in the gate) reports **14 findings
  on .github/workflows: 6 high, 3 low, 5 suppressed**. Measured today, not
  recalled. Unlike shellcheck/actionlint (both clean, added as FIBR-0225),
  this one has real work behind it, so it is filed rather than wired in —
  a stage that fails on day one is not a gate, it is a broken build.

  - **6 × `unpinned-uses` (high).** `actions/checkout@v7`,
  `actions/setup-python@v6`, `actions/upload-artifact@v7` are pinned to
  a TAG, not a commit hash. A tag is mutable: whoever controls the
  action repo can repoint it, and it lands in a finbreak release build.
  This matters more here than on a typical repo because those workflows
  produce the SIGNED artifacts users download.
  - **3 × `artipacked` (low).** `actions/checkout` leaves the credential
  in `.git/config` unless `persist-credentials: false`. Auto-fixable.

  TENSION TO RESOLVE FIRST — this needs a user call, not just a fix. Hash
  pinning conflicts with the standing "dependencies stay latest" policy:
  a hash pin is invisible to the eye and does not tell you it is stale, so
  it needs Dependabot (which understands hash pins and rewrites them with
  the tag in a comment) or it silently rots. Recommend: adopt hash pins
  AND enable Dependabot for `github-actions` in the same change, or
  consciously accept tag pinning and add a `zizmor.yml` that suppresses
  `unpinned-uses` with the reason written down. Do not half-do it.

  Add the `zizmor` stage to `ci-local.sh` only once the tree is clean,
  alongside the FIBR-0225 stages.
  **Layman:** Pin the build robots to exact versions so a hijacked one can't slip into a release.
  Kind: security.
  Source: user-request-2026-08-05 (audit-tool scan; measured, not recalled).
  DECIDED (user, 2026-08-05): take the hash pins AND Dependabot
  TOGETHER — the "not half of either" option. The tension flagged above
  is settled; do not re-open it or re-present it as a choice.

  What that means concretely when this is built:
  - Pin every `uses:` in all 3 workflows to a full commit SHA, with the
  human-readable tag in a trailing comment (`# v7.0.1`) — that is the
  form Dependabot writes and reads back.
  - Add `.github/dependabot.yml` with a `package-ecosystem:
  "github-actions"` entry so the pins are maintained rather than
  frozen. Without it the pins rot silently and the standing
  "dependencies stay latest" policy is quietly violated — that
  coupling is the whole reason the two were made one decision.
  - Then fix the 3 `artipacked` LOWs (`persist-credentials: false` on
  each checkout) and add the `zizmor` stage to `ci-local.sh` +
  `ci-setup.sh` (pin 1.29.0, same shape as shellcheck/actionlint).
  Add the stage LAST, once the tree is clean — a stage that fails on
  day one is a broken build, not a gate.
  - The stage must also be added to FIBR-0001 INV-1's table, or
  `tests/features/harness/` fails: that suite now asserts the spec
  table and `ci-local.sh` agree as an unordered set. That is the
  guard working as designed, not an obstacle.
  Resolved (2026-08-05): all three parts landed, in the decided order.
  (1) All 6 `uses:` across ci.yml / build-smoke.yml / windows-build.yml
  pinned to full commit SHAs with the tag in a trailing comment —
  actions/checkout v7.0.1 (3d3c42e), actions/upload-artifact v7.0.1
  (043fb46), actions/setup-python **v7.0.0** (5fda3b9). setup-python was
  bumped v6 → v7 rather than pinning a stale v6 SHA: v7's only removal is
  the `pip-install` input, which no workflow uses, and pinning below
  latest would have violated the standing deps-stay-latest policy on day
  one. (2) `.github/dependabot.yml` already carried a `github-actions`
  entry, but its header claimed the file was an inactive template
  ("activate by renaming this file") — corrected, and the entry now
  states in-file that it is half of this decision, because removing it
  turns the pins from maintained into frozen. A `pip` entry was
  deliberately NOT added; the reason is recorded in the file. (3)
  `persist-credentials: false` on all 3 checkouts. Then, and only then,
  the `zizmor` stage: pinned 1.29.0 in ci-setup.sh (same shape as
  shellcheck/actionlint), invoked as `zizmor .github/workflows/` in
  ci-local.sh, and added as row 5 of FIBR-0001 INV-1's table with
  tests/features/harness/'s bounds moved 9→10 rows / 8→9 names in the
  same commit.

  Verified, not assumed: `zizmor .github/workflows/` went 14 findings
  (6 high, 3 low) → "No findings to report" (5 suppressed at the default
  persona). The stage was then proven to actually FAIL — reverting one
  pin to a tag exits 14, dropping a persist-credentials exits 13 — so it
  is a gate, not decoration. Full gate green: 1698 passed, 2 skipped,
  1m45s. zizmor runs OFFLINE by default, so it adds no network dependency
  and pip-audit stays the only stage that can flake on a timeout.

  Doc blast radius swept: FIBR-0001 (INV-1 table + stages 3–5 prose + the
  "stage added last" rationale), CLAUDE.md (binary table + gate stage
  list + 2 ci-setup descriptions), security-model.md § 6 (tool/threat row
  + the offline note), CHANGELOG Security. The "three pinned binaries"
  counts were rewritten as SELECTORS rather than bumped to four —
  FIBR-0001's own cold-eyes convergence lesson is that a copied count
  goes stale silently, so no count is now stated anywhere.
  Runner verification (2026-08-05, AFTER the note above was written — that
  note predates these runs). The `setup-python` v6 → v7.0.0 bump needed
  proof, because NEITHER workflow that uses setup-python runs on push:
  `build-smoke.yml` is dispatch+weekly and `windows-build.yml` is
  dispatch-only. So a green CI push proves the checkout pin and nothing
  else. Both were dispatched deliberately and both passed: build-smoke ✅,
  windows-build ✅ 8m9s (freeze + clean-room `.exe`, i.e. the pinned
  `upload-artifact@043fb46` exercised too). Push CI ✅ 3m30s. Do not
  re-litigate whether v7.0.0 works on a real runner — it has been run.

  Dependabot verification: the push triggered a Dependabot Updates run
  that completed **success and opened ZERO PRs**, including a dedicated
  `for actions/setup-python` check. Zero PRs is the positive result here,
  not a null one — it means Dependabot parsed the `<sha> # vX.Y.Z` form,
  resolved each pin, and found all three already at latest. That is the
  hash-pin/Dependabot coupling demonstrated end to end rather than
  assumed, which was the one part of this decision that could have been
  quietly wrong.

- ✅ [FIBR-0227] **Audit tools measured and REJECTED for the gate — the evidence, so nobody re-runs this.**
  Every tool below is INSTALLED on this machine and was run against the
  real tree today. Recording the counts so this scan is not repeated from
  scratch — a rejected tool looks identical to an unconsidered one.

  - **deptry** — 501 "issues", ~all bogus: it flags first-party
  `finbreak` imports and `PySide6` (which IS in dependencies) as
  missing, i.e. it has not been told about the `src/` layout. Would need
  real config before it says anything true. Revisit only with config.
  - **vulture** (`--min-confidence 80`) — dominated by false positives:
  pytest fixtures requested for their side effects (`theme_isolation`
  ×14) read as "unused variable". Useful ad-hoc after a refactor, wrong
  as a blocking stage.
  - **typos** — 261 hits, sampled and mostly wrong for this codebase:
  `mis` (from hyphenated "mis-assigns"), `Flate` (PDF **FlateDecode**, a
  real term), `unparseable` (valid variant), plus sentinel strings in
  `_selftest.py`. Would need a `_typos.toml` allowlist first; the real
  win would be user-visible strings only.
  - **semgrep** (`p/python`, `p/secrets`) — 2 findings, BOTH wrong here:
  it calls `os.chmod(dir, 0o700)` "widely permissive" and suggests
  `0o644`, which for the private vault directory is the opposite of
  correct; the other already carries a `# nosec`. Adds nothing over
  bandit on this codebase.
  - **yamllint** — line-length noise at its 80-col default; actionlint
  already covers the workflow issues that matter.
  - **shfmt** — 997 diff lines of pure indentation churn (it wants 2-space,
  the scripts use 4). Formatting-only, no correctness signal.
  - **pyright** — mypy already runs and is green. Two type checkers is
  double the suppression maintenance for overlapping signal.
  - **trivy** — container/image scanning; finbreak ships no container.

  CORRECTION (verified after the note below was first written): installing
  osv-scanner is NOT the cheapest way to get OSV coverage. `pip-audit`
  already takes `-s/--vulnerability-service {osv,pypi,esms}` and defaults
  to `pypi`; `pip-audit -s osv` queries api.osv.dev directly and runs
  clean on this tree today. OSV.dev's own data-source list confirms it
  imports the **OpenSSF Malicious Packages** feed (verified against
  google.github.io/osv.dev/data/, not recalled). So the gap closes with a
  flag on the existing stage, not a new binary.

  DECIDED (user, 2026-08-05): add `pip-audit -s osv` as a SECOND
  pip-audit stage, accepting the extra network dependency. Flipped
  considered → planned; the recommendation in the CORRECTION block
  above is now the agreed plan, not an option to re-weigh.

  Rationale, so it is not re-litigated: the two services are different
  databases (PyPI Advisory DB vs OSV.dev), neither a superset, and only
  OSV.dev carries the OpenSSF Malicious Packages feed — the hijacked or
  typosquatted package with no CVE, which the CVE-only view structurally
  cannot see. That matters for a project shipping signed desktop
  binaries. Verified clean on this tree today.

  Build notes:
  - Keep BOTH stages: the existing default (`pypi`) plus `-s osv`. One
  is not a replacement for the other.
  - The accepted cost is a second network-dependent stage on a gate that
  runs on every push; CLAUDE.md already records that a rare pip-audit
  timeout flakes the pre-push hook. Revert this stage if the flake
  rate becomes annoying — that is a legitimate outcome, not a failure.
  - Adding it changes the gate's stage set, so FIBR-0001 INV-1's table
  must gain the row in the SAME commit or `tests/features/harness/`
  goes red by design.

  The REJECTED-tool evidence above (deptry / vulture / typos / semgrep /
  yamllint / shfmt / pyright / trivy, each run against the real tree with
  counts) stands as-is — do not re-run that scan from scratch.
  Resolved (2026-08-05): `pip-audit -s osv` shipped as gate stage 8,
  alongside the existing `-s pypi` stage 7 — both kept, as decided.

  VERIFIED BOTH DIRECTIONS before it landed, per the FIBR-0226 ordering
  rule that a stage must be green on the current tree first:
  - Green: `pip-audit -s osv` → "No known vulnerabilities found",
  exit 0, 27.8s. That ~28s is the real, measured cost added to a
  ~1m45s gate; it is recorded in CLAUDE.md so the slowdown is not a
  mystery later.
  - Red: the same command against a `jinja2==2.11.2` pin found 10
  vulnerabilities and exited 1 — so the stage can actually fail, which
  a green-only check does not establish.

  Landed in ONE commit, as the guard requires: the gate stage, the
  FIBR-0001 INV-1 table row (7 rows renumbered, now 11), and the
  `tests/features/harness/` bound (10 → 11 rows; the NAME count stays 9,
  because both parsers key on the tool name and `pip-audit` was already
  in the set — the same shape as `ruff` running twice).

  Two pre-existing rot spots fixed on the way past, both made worse by
  the renumber: `docs/specs/FIBR-0001.md` and `scripts/ci-local.sh` each
  claimed "stages 8 and 9 are red with the dev group alone", which meant
  mypy/pytest before `zizmor` was inserted as stage 5 and had been
  silently wrong since. Both now name the tools instead of numbering
  them — FIBR-0001's own cold-eyes lesson about copied counts.

  Blast radius swept: `docs/security-model.md` T7 (now names the no-CVE
  hijacked/typosquatted case the OSV feed is what covers) and its § 6
  tool table + notes (which also record why `osv-scanner` is NOT in the
  gate: a flag on an installed tool reaches the same data), plus
  CLAUDE.md's gate-stage list and its pip-audit flake note.

  The REJECTED-tool evidence in this bullet stands untouched — it is
  still the record that stops that scan being re-run.

  SETTLED, so it is not re-opened: **osv-scanner** (google, v2.4.0) was
  the candidate that started this — it queries OSV.dev, which carries the
  OpenSSF Malicious Packages feed, and that gap was real. The CORRECTION
  above is what closed it: the same data is a FLAG on a tool the gate
  already installs, so the second binary buys nothing and is not being
  added. `docs/security-model.md § 6` records that reasoning where a
  future reader of the gate will actually meet it.

  STILL DEFERRED (not installed, from the same online research): SBOM
  generation (syft / CycloneDX) attached to releases. Untouched by this
  item — no decision taken either way.

  **Layman:** A record of which code-checking tools we tried and why they weren't worth adding.
  Kind: investigate.
  Source: user-request-2026-08-05 (system scan + online research).

- ✅ [FIBR-0228] **Three docs link to a ~/ path that resolves nowhere.**
  Surfaced by `doc_integrity` during the FIBR-0001 cold-eyes run and
  deliberately NOT fixed there — pre-existing, and in three files that
  review did not cover (stay-in-lane). Recorded so it is not
  re-discovered.

  `docs/audit-allowlist.md:27`, `docs/ideas.md:10` and
  `docs/known-issues.md:7` each render a markdown link whose target is
  `~/.claude/skills/app-workflow/SKILL.md`. The skill genuinely exists
  on this machine, so the reference is not *wrong* — but `~` is a shell
  expansion, not a URL, so the link resolves for no reader: not on
  GitHub, not in a markdown previewer, not in an editor. It is the only
  `broken_link` class left in `docs/` (verified: 3 findings, 0 dead
  anchors, across 122 checked docs).

  Fix is a judgement call, hence planned rather than done: either drop
  the link and leave the path as inline code (honest — it is a
  machine-local file, not a project doc), or point at whatever
  in-project doc describes the workflow. Prefer the first; a link that
  cannot resolve is worse than plain text naming the same file.

  Cheap to verify after: `doc_integrity` over `docs/` should come back
  with `broken_link: 0`.
  **Layman:** Three "see this document" links in the docs are broken for anyone reading them.
  Kind: doc-fix.
  Source: in-session-2026-08-05 (cold-eyes FIBR-0001, doc_integrity sweep).
  Correction (2026-08-05, found while closing FIBR-0229): it is
  **six** sites, not three. `doc_integrity` only walks `docs/`, so the
  three it reported are the three it can see. `grep -rn ']( *~/'
  --include=*.md .` finds three more the checker never reads:
  `CLAUDE.md:4`, `CLAUDE.md:30` and `ROADMAP.md:4889` — same link,
  same defect, same fix.

  This matters for the verify step this bullet already specifies:
  `doc_integrity` returning `broken_link: 0` will NOT prove the fix
  complete, because it never looked at half the sites. Verify with the
  grep as well.

  Not fixed while here — FIBR-0229 was a workflow-header change and
  two of the six sites are in `CLAUDE.md`, which it did touch;
  drive-by-fixing them would have buried this correction in an
  unrelated diff. Left whole for one deliberate pass.
  Resolved (2026-08-05): all six sites take the preferred fix — the
  markdown link is dropped and the path stays as inline code, with
  "machine-local" naming why it is not a project doc. Sites:
  `CLAUDE.md:4`, `CLAUDE.md:30`, `docs/ideas.md:10`,
  `docs/known-issues.md:7`, `docs/audit-allowlist.md:27`,
  `ROADMAP.md` (the § 3.8 pointer near the phase-loop diagram).

  Verified BOTH ways, per this bullet's own correction: `doc_integrity`
  over `docs/` returns `broken_link: 0` and `dead_anchor: 0` across 122
  checked docs, AND `grep -rn ']( *~/' --include=*.md .` returns zero.
  Widened the grep past `--include=*.md` as well — no `~/` markdown link
  survives anywhere in the tree.

  Doc-only, and it does not touch `docs/specs/FIBR-0001.md`, so the gate
  was correctly skipped per the project's doc-only push rule.

- ✅ [FIBR-0229] **`.claude/workflow.md`'s status header is four items stale.**
  §1's status header is dated **2026-08-02** and describes the v0.1.19
  release as the current state. Four items have landed since and none of
  them updated it: `FIBR-0223` (OFX unstorable balance), `FIBR-0225`
  (shellcheck + actionlint stages), `FIBR-0228` (filed), `FIBR-0226`
  (hash pins + zizmor). Its gate figure is also stale — it records
  **1455 passed**, the gate now runs **1698 passed, 2 skipped**.

  Why this matters more than an ordinary stale doc: `CLAUDE.md`'s
  "Resumption flow" makes reading this header a MANDATORY session-start
  step and requires summarising it back to the user before doing any
  work. So the one file a fresh session is told to trust for "where are
  we" is the one that has been drifting — a session that follows the
  rule correctly gets a confidently-wrong answer about the current
  state, which is worse than having no header at all.

  Not fixed inline when found (2026-08-05) deliberately: rewriting a
  70 KB status header is its own piece of work, and doing it as a
  drive-by inside a security change would have buried it in an unrelated
  diff. Surfaced to the user in the same breath.

  Worth deciding as part of this, not just re-writing the header once:
  whether `/close-phase` should update §1, or whether the header should
  shrink to a pointer at the ROADMAP (which is never stale, because the
  verbs write it). A header that must be hand-maintained will drift
  again; that is the pattern this bullet is evidence of, not the
  exception.
  **Layman:** The project's "where are we right now" note still describes work from three days ago.
  Kind: doc-fix.
  Source: in-session-2026-08-05 (surfaced while closing FIBR-0226).
  Resolved (2026-08-05): §1 rebuilt as a thin pointer, not a
  rewritten narrative — the user's call when asked. It was worse than
  this bullet recorded: §1 was **128 KB of the file's 216 KB**, and
  the drift ran weeks, not four items (`Active item ID` still named
  FIBR-0004, closed 2026-07-02; `Last update` 2026-07-18; `Last debt
  sweep` said "(none yet)" though DS02 completed 2026-07-26).

  The bullet's open question resolved differently than it was framed.
  It asked whether `/close-phase` should maintain §1 — but
  `/close-phase` **already does** (its steps 5a and 9 set the active
  item, reset the checkboxes and bump the date). The header did not
  drift for want of a maintainer; it drifted because most recent work
  is self-directed and never enters the phase loop. So "make
  /close-phase do it" would have fixed nothing.

  What §1 now holds is only what lives nowhere else: repo visibility,
  convergence checkpoint, debt-sweep threshold, active item + the nine
  step checkboxes. Everything derivable now points at ROADMAP.md,
  which the `roadmap_log` verb writes on every status change and so
  cannot rot. The duplicated FIBR-0004/FIBR-0009 close records were
  dropped — both exist in full at `docs/journal/<ID>.md`.

  §3 (the session journal) deliberately untouched: append-only history
  cannot be stale, and it was not the thing that was lying.

  `CLAUDE.md` updated in the same commit or the fix would have created
  fresh drift — its "Where state lives" list described §1 as holding
  "current phase", and its resumption flow told a session to recover
  state from it. Both now name ROADMAP.md as the authority.

  Result: 216 KB → 91 KB (-58%); §1 146 lines → 73.

- ✅ [FIBR-0230] **Nothing stops the ~/ link defect recurring — the standard has no rule about link targets.**
  FIBR-0228 removed six markdown links to
  `~/.claude/skills/app-workflow/SKILL.md` — a shell path that
  resolves for no reader (not GitHub, not a previewer, not an
  editor). The sites are fixed; the *cause* is not.

  `docs/standards/documentation.md § 7` ("Markdown style") has a
  Links bullet at line 176, but it governs link **form** only —
  `[text](url)` not `<url>`. Nothing there says a link target must
  resolve for a reader who is not on this machine. So the next
  session that writes a doc referencing the app-workflow skill can
  re-add the exact link FIBR-0228 removed, in good faith, and
  nothing catches it.

  Fix: one bullet under § 7, roughly — "Link targets must resolve
  for a reader outside this machine. A machine-local path
  (`~/...`) goes in inline code with a note that it is
  machine-local, never in a link target." The wording is the whole
  job; the check already exists.

  Note the review cost, which is why this is a separate item and
  not a drive-by: editing any `docs/standards/` file trips the
  rule-14 `/cold-eyes` gate. That is a deliberate pass, not a
  one-line commit — budget for it rather than being surprised.

  Verify after: `grep -rn ']( *~/' --include=*.md .` returns zero
  (it does today), and the new bullet exists in § 7. Note that
  `doc_integrity` alone does NOT cover this — it only walks
  `docs/`, so it never reads `CLAUDE.md` or `ROADMAP.md`, which is
  exactly how FIBR-0228 undercounted itself as three sites when it
  was six.
  **Layman:** The docs rulebook doesn't yet say "don't link to a file on your own computer", so the broken links just fixed could come back.
  Kind: doc-fix.
  Source: in-session-2026-08-05 (FIBR-0228 close).
  Resolved (2026-08-05): the § 7 bullet is in, and the rule-14
  /cold-eyes gate ran to 3 loops (45 verified findings, all fixed;
  loop rows in the doc). The bullet's own suggested wording turned
  out to be under-scoped — it bound only `~/…`, so an absolute path
  or a `file://` URL complied with the letter and broke for the same
  reader. Shipped wording covers any path outside the repository,
  with a ❌/✅ pair. Verify step passes: `grep -rn ']( *~/'` returns
  zero and the bullet exists in § 7.

  The gate cost was the item, as predicted here — and it earned its
  keep: it found the new rule's hole, and a stale "four standards
  docs" count in § 2.6 that `CONTRIBUTING.md` had already been built
  from (both fixed). § 2.6 now states no count at all, so it cannot
  rot again. Two findings were surfaced rather than swept and are
  filed as FIBR-0236 (three sibling standards carry the same stale
  peer count) and FIBR-0237 (no SECURITY.md / CODE_OF_CONDUCT.md
  though § 2.4/§ 2.5 require both here).

- ✅ [FIBR-0236] **Three standards still say "the other three standards" and list three.**
  `coding.md:4-5`, `commits.md:4-5` and `testing.md:4-5` each open
  "Pairs with the other **three** standards in this folder" and then
  name three. There are five others. All three lines date from the P00
  scaffold commit `3783608` (2026-06-30), when three was correct;
  `naming.md` and `dependencies.md` landed in `90085bf` (2026-07-03)
  and none of the three mastheads followed.

  `dependencies.md` and `naming.md` — written after the split — say
  "the other standards" with no count and list all five correctly, so
  the fix is to match them: drop the numeral rather than correct it, or
  it rots again on the next standard added.

  Found by the FIBR-0230 cold-eyes run while sweeping the blast radius
  of the same defect in `documentation.md` (fixed there, along with the
  same stale count in `CONTRIBUTING.md`). Surfaced rather than swept
  because each of the three is a `docs/standards/` edit that trips the
  rule-14 `/cold-eyes` gate on its own — that review cost, not the
  wording, is the whole item.

  Verify after: `grep -rn 'other three standards' docs/standards/`
  returns zero, and each masthead names all five peers.
  **Layman:** Three of the rulebooks still describe a smaller set of rulebooks than the project actually has.
  Kind: doc-fix.
  Source: cold-eyes-2026-08-05 (FIBR-0230 loop 1, surfaced not fixed).
  Resolved (2026-08-19) — by two other items, neither of which knew this one
  existed. Closed on its own stated verification, run today.

  `commits.md` was fixed on 2026-08-19 by its own `review-contract` gate
  (FIBR-0279), which dropped the list as well as the count. `coding.md` and
  `testing.md` were fixed the same day by FIBR-0286, which enumerated all five
  peers and named no count — the route this bullet asked for ("drop the numeral
  rather than correct it, or it rots again on the next standard added").

  Verification as written here: `grep -rn 'other three standards'
  docs/standards/` returns **0**, and all six mastheads name their peers
  correctly.

  Worth recording, because it cost real duplicated work: this bullet and
  FIBR-0286 are the same defect found twice, fourteen days apart, by two cold
  reads that each swept the blast radius of a neighbouring document. Neither
  found the other's roadmap entry. A `roadmap_query` on the defect's own words
  before filing would have caught it.

- ✅ [FIBR-0237] **No SECURITY.md and no CODE_OF_CONDUCT.md, though the standard requires both here.**
  `documentation.md § 2.4` requires `SECURITY.md` for a project that
  **accepts issues**, and § 2.5 requires `CODE_OF_CONDUCT.md` for one
  that **accepts patches**. finbreak is a public repo whose
  `CONTRIBUTING.md` documents both filing issues and proposing changes,
  so both preconditions are met and neither file exists at the repo
  root.

  Both lanes of the FIBR-0230 cold-eyes run raised this independently,
  across two loops. It is a *project-side* gap, not a defect in the
  rule — which is why that run surfaced it rather than editing it away.
  The rule itself was verified as correctly scoped in loop 3.

  § 2.4 names the contents: disclosure policy, contact email, GPG key
  (if used), supported-version table. § 2.5's default is Contributor
  Covenant 2.1 verbatim.

  Note the interaction with FIBR-0133 (Windows code signing, blocked):
  a `SECURITY.md` that names a disclosure contact is also the thing
  most open-source-programme applications look for, so this is cheap
  and may unblock more than it costs.

  Verify after: both files exist at the repo root, `SECURITY.md`
  carries all four items § 2.4 lists, and `CODE_OF_CONDUCT.md` is
  Covenant 2.1 verbatim.
  **Layman:** The project's own rulebook says a public project taking bug reports needs a security-contact file and a code of conduct; neither exists yet.
  Kind: doc.
  Source: cold-eyes-2026-08-05 (FIBR-0230 loops 1-2, surfaced not fixed).
  Resolved (2026-08-20): both files exist at the repo root.

  SECURITY.md carries all four things documentation.md 2.4 names.
  Disclosure policy, supported-version table (latest release only,
  no backports -- which follows from versioning.md 3.4) and a
  scope section that defers to security-model.md 4 and 5 rather
  than restating them. The CONTACT is GitHub's private advisory
  form, enabled on the repo in this change; it was disabled, so
  there was no private channel at all before today. No email
  address is published and no GPG key -- both are stated, with the
  reason, rather than left as a silent omission against 2.4's
  "contact email, GPG key (if used)". User decision 2026-08-20:
  publishing a solo maintainer's personal address on a public repo
  buys spam, and the advisory form is already an encrypted private
  channel.

  CODE_OF_CONDUCT.md is Contributor Covenant 2.1 verbatim, fetched
  from the canonical EthicalSource source rather than typed from
  memory, with only the [INSERT CONTACT METHOD] placeholder filled.

  Rode along, because each was a copy of a rule these files now
  own: CONTRIBUTING.md's inline conduct paragraph became a pointer
  and its bug section grew the "not a public issue for a security
  bug" carve-out it lacked; README's documentation list gained all
  three files; versioning.md 3.4's parenthetical "once that file
  exists, which it does not today" was true when written this week
  and is not now.

  Closes condition 4 of the FIBR-0304 v1.0 gate. Three blockers
  remain: FIBR-0019, FIBR-0208, FIBR-0217.

## P13 — Packaging & release

### 📦 Packaging

- ✅ [FIBR-0015] **P13: Windows self-contained `.exe` build.**
  PyInstaller freezes `finbreak.exe` (bundled CPython + all native
  deps — SQLCipher, the needed Qt plugins, qpdf) on a
  `windows-latest` runner via `.github/workflows/windows-build.yml`
  (`workflow_dispatch`), clean-roomed with Python off `PATH`
  (`--self-test` → `FINBREAK_SELFTEST_OK`) and uploaded as a CI
  artifact for testers. Unsigned, manual-update, no installer.
  Builds on the P01 smoke-test.
  Dependencies: FIBR-0013, FIBR-0014, FIBR-0003 (direct
  predecessors). Walking the dependency edges, FIBR-0013 and
  FIBR-0014 transitively pull in the entire P02–P12 feature stack
  (FIBR-0004 through FIBR-0012), so P13 cannot start until the app
  is feature-complete. Lanes: build, ci, packaging.
  Kind: chore. Source: planned.
  Resolved 2026-07-13 (FIBR-0015-complete): the Windows `.exe` shipped by TDD (fixture-first cross-package regression + the INV-3 parity guard + the freeze driver). The one-time blocker — `sqlcipher3-binary` shipped Linux/macOS wheels only — was dissolved by swapping to `sqlcipher3-wheels` (the cross-platform fork, same SQLCipher 4.12.0 engine; ADR-0009), proven vault-portable both directions before the swap. `/audit` 0 actionable; `/indie-review` 2 cold lanes 0 defects; gate green 851/1. See docs/journal/FIBR-0015.md.
  Scope: this item delivered **only the Windows `.exe`**. The **Linux AppImage** already shipped under FIBR-0054 (`scripts/build-release-appimage.sh`); **macOS `.app`/`.dmg` + Flatpak/Flathub** are split to **FIBR-0130** (packaging-only — the `sqlcipher3-wheels` swap already cleared their SQLCipher blocker too). Superseded: the 2026-07-13 "compile SQLCipher on Windows" readiness-scan blocker and the "Wine + MSVC" local-build note — the Windows wheel makes both moot.
  Source: planned.
  Lanes: build, ci, packaging.

- 📋 [FIBR-0130] **P13: macOS `.dmg` packaging**
  (Flatpak/Flathub → FIBR-0159).
  The macOS `.app`-in-`.dmg` — the packaging remainder split out of FIBR-0015 when its Windows `.exe` slice closed (2026-07-13). The Flatpak/Flathub half moved to FIBR-0159 (see the scope update below). The SQLCipher crypto blocker is already cleared (the `sqlcipher3-wheels` fork ships macOS + Linux wheels of the same 4.12.0 engine, ADR-0009), so this is packaging-only: freeze the macOS app on a `macos-latest` runner (reusing the FIBR-0015 `windows_freeze_flags.py` collection list + `--self-test` clean-room); the artifact still meets ADR-0007's "no Python installed" launch bar. (The Flatpak manifest is FIBR-0159's, not this item's — see the scope update below.) Dependencies: FIBR-0015 (freeze tooling), FIBR-0037 (icon → `.icns`). Lanes: build, ci, packaging. Kind: chore. Source: split-from-FIBR-0015-2026-07-13.
  Scope update (2026-07-23): the Flatpak/Flathub half is now owned end-to-end by FIBR-0159 (docs/specs/FIBR-0159.md — freedesktop 25.08 runtime + pinned-wheel closure, portal-only sandbox). FIBR-0130 is left to deliver the macOS `.app`/`.dmg` only; do NOT re-author a Flatpak manifest here.
  **Layman:** A proper macOS download you open and drag to Applications, like any other Mac app.
  Kind: chore.
  Source: split-from-FIBR-0015-2026-07-13.
  Lanes: build, ci, packaging.

- ✅ [FIBR-0131] **Windows in-app auto-update.**
  Extend the FIBR-0054 self-update stack (check GitHub → Ed25519-verify the download → the Later/Skip/Update-now dialog — all already cross-platform) to actually *install* the update on Windows, which `detect_installer()` currently returns `None` for (inert, INV-7). A running Windows `.exe` locks itself, so the Linux "os.replace the file then relaunch" trick can't be copied. **Design (user-approved 2026-07-13): a separate helper process does the swap** — the app writes the verified new `.exe` beside the old one and spawns a detached waiter (cmd/PowerShell) that waits for finbreak to exit, moves the new file over the old one, and relaunches it (the Windows analogue of the FIBR-0122 `/bin/sh` waiter; watch the same PyInstaller-onefile `_MEI`-teardown race). Adds a `WindowsInstaller` + `detect_installer()` returning it on a frozen Windows build, and an asset-picker that selects the `.exe` release asset on Windows. Also promote the Windows `.exe` from a CI artifact to a signed release asset (attach + an Ed25519 `.sig` for the updater to verify; FIBR-0015 D6 deferred this) and evaluate Authenticode code-signing (an unsigned self-swapping-and-relaunching `.exe` is what Defender/SmartScreen distrusts most; free-ish for OSS via Azure Trusted Signing / SignPath). Same two-cycle caveat as Linux — the relaunch only proves out on the update *after* it ships. Dependencies: FIBR-0054 (update infra), FIBR-0015 (Windows build). Lanes: services, ui, ci, security. Kind: feature. Source: user-request-2026-07-13.
  Sequencing (2026-07-14): the "evaluate Authenticode code-signing" clause above is split out to FIBR-0133 (SignPath, blocked on approval). FIBR-0131 ships the Ed25519-signed .exe release asset + the in-app Windows updater ONLY; publisher (Authenticode/SmartScreen) trust is FIBR-0133 and does not block this. Spec: docs/specs/FIBR-0131.md.
  Spec refinements (docs/specs/FIBR-0131.md, cold-eyes-converged): (1) the waiter is PowerShell (the "cmd/" option was dropped); it waits by exe IMAGE PATH, not a PID (tree-agnostic + PID-recycling-proof). (2) The .exe is ALREADY a published release asset (v0.1.9 ships finbreak-0.1.9-x86_64.exe); the only missing piece for the updater is the Ed25519 .exe.sig sidecar, which D5 adds — so "promote from a CI artifact" is really "add the .sig".
  Closed 2026-07-14 by /close-phase (code-complete). Spec cold-eyes-converged (6 loops x 3 lanes); TDD (WindowsInstaller image-path swap+relaunch behind the existing Installer seam; installer-driven asset-picker; UpdateInfo.appimage_url->asset_url). /audit 0 actionable (3 bandit assert-in-tests FPs, out of gate scope). /indie-review 2 cold lanes -> crypto/PowerShell/ordering verified sound, 1 MEDIUM fixed inline (spawn-before-wipe so a Popen failure can't strand a wiped key; Linux twin guarded too). Gate green 877/1; tag FIBR-0131-complete. CAVEAT (like Linux FIBR-0054): the live Windows swap+relaunch is a two-cycle manual verification on the user's Windows box, and needs a release that first attaches the Ed25519 .exe.sig (v0.1.9 shipped the .exe but no .sig). Journal docs/journal/FIBR-0131.md.
  Kind: feature.
  Source: user-request-2026-07-13.
  Lanes: services, ui, ci, security.

- 📋 [FIBR-0016] **P13: `scripts/publish-release.sh` + release automation.**
  One committed script builds every
  artifact above, publishes the GitHub Release, and drives the
  Flathub submission/update — consuming the Flathub manifest
  produced by FIBR-0015. It is itself a specced item (its own
  `docs/specs/`, cold-eyes-reviewed) — a publish script can't
  predate the thing it publishes. Dependencies: FIBR-0015. Lanes:
  build, ci, packaging. Kind: chore. Source: planned.
  Note (2026-07-10): FIBR-0054 pulls a **Linux-only** slice of release automation forward — a thin `scripts/publish-release.sh` (or `gh release create`) that publishes the signed AppImage + `.sig` as GitHub Release `v0.1.0`, so the in-app updater has a real release to check/download. FIBR-0016 remains owner of the full multi-artifact publish + the Flathub submission/update flow; extend the Linux slice rather than replacing it.
  Note (2026-07-12, user request — "automate the release as much as possible"): the version-bump half is now automated — `.claude/bump.json` (added 2026-07-12) drives /bump and /release: source of truth src/finbreak/__init__.py, mechanical edits to pyproject.toml + tests/test_smoke.py + a dated CHANGELOG cut from [Unreleased], a post_check version-lockstep gate, and tag template v{NEW}. What remains MANUAL (the Linux-slice glue this item should close): after the bump, a human still runs scripts/build-release-appimage.sh (freeze + clean-room + sign), verifies the .sig against the committed RELEASE_PUBLIC_KEY_B64, extracts the CHANGELOG [X.Y.Z] section for notes, and runs `gh release create v<NEW> <appimage> <sig> --notes-file … --latest` (non-prerelease). Deliverable: a single `scripts/publish-release.sh` that chains bump (via the recipe) → full gate (ci-local.sh) → build+clean-room+sign → **verify .sig vs RELEASE_PUBLIC_KEY_B64 (hard gate — never publish an unverifiable release the in-app updater would reject)** → gh release create with the AppImage + .sig attached, notes from the changelog, non-prerelease so /releases/latest resolves. Idempotency + preconditions (clean tree, tag not already present, signing key available) checked up front. Keep it the Linux slice under FIBR-0016; the multi-artifact + Flathub publish stays the full-item scope. Spec-first per the item's own note (docs/specs/, cold-eyes) before coding.
  **Layman:** One command builds every download, publishes the release and updates the store listings, instead of a person running several scripts by hand and hoping none was skipped.
  Kind: chore.
  Source: planned.
  Lanes: build, ci, packaging.

- ✅ [FIBR-0037] **P13: a proper branded app icon (not a flat glyph).**
  Design a polished, richly-shaded application icon —
  the working concept is **money + an upward chart** (e.g. a
  banknote or coins fronting a rising line/bar graph), on a
  **transparent** background, reading clearly from a taskbar 16px
  up to a store 1024px. Ship the full asset set every artifact
  needs: master (≥1024px PNG/SVG source), multi-size `.ico`
  (Windows), `.icns` (macOS), the freedesktop hicolor PNG set +
  `.desktop` reference (Linux/AppImage), and the Flathub icon.
  **Licensing is a hard gate, not a nicety:** because the app
  ships on Flathub / GitHub Releases under MIT, every source
  element must be **original or CC0/public-domain** — no scraped
  copyrighted or attribution-encumbered art, even when combining
  pieces (record provenance + license of each source in
  `docs/` alongside the asset). Until this lands, the FIBR-0003
  smoke-test AppImage and dev builds use a throwaway placeholder
  icon. Dependencies: none (asset work); **blocks FIBR-0015**
  (packaging embeds it) and should harmonise with the FIBR-0023
  theme accent colour. Lanes: design, packaging. Kind: ux.
  Source: user-request-2026-07-01.
  Resolved 2026-07-09 (FIBR-0037-complete): branded app icon shipped — a "spending by category" donut (green/blue/teal/orange segments) with a gold coin centre on a dark navy tile, chosen with the user after shrink-testing candidates for small-size legibility (holds at 24px). Single 1024 master assets/icon/finbreak.png; scripts/make-icons.sh derives the platform set (Linux PNGs 16-512, 7-size Windows .ico, macOS .iconset) so they can't drift. Runtime window icon travels as ui/icons/app.png package data, set via QApplication.setWindowIcon (every window/dialog + taskbar); --self-test renders it (bundle-travel proof). macOS .icns is a mac-build-time step from the .iconset (FIBR-0015). /audit 0, indie-review clean (1 stale-comment LOW folded). Gate green 344 passed/1 skipped, mypy 0. Unblocks FIBR-0015 (the builds need the icon).
  Kind: ux.
  Lanes: design, packaging.

---

- 📋 [FIBR-0044] **Broaden Linux store reach: Snap Store + AUR + native distro packages.**
  Flathub (FIBR-0015) already surfaces the app in GNOME Software + KDE Discover across most distros, so this item adds the remaining self-publishable Linux channels: (a) Snap Store — a snapcraft.yaml (Ubuntu App Centre's default backend); (b) AUR — a PKGBUILD pointing at the GitHub release/AppImage (community-maintained, low overhead); (c) native RPM + DEB packages for Fedora/openSUSE/Debian/Ubuntu built via the openSUSE Build Service (OBS) and/or Fedora COPR, published to a project repo. (Getting INTO official distro repos is maintainer-driven and slow — tracked separately if pursued.) All free, all self-publish. Depends on FIBR-0015 (the built artifacts) and FIBR-0016 (release automation extends to push each channel).
  **Layman:** Beyond Flathub (which already puts us in most Linux app stores), also publish to Ubuntu's Snap Store and Arch's AUR, plus ready-to-install packages for Fedora/openSUSE/Debian — so almost any Linux user can install us in one click.
  Kind: package.
  Source: user-request-2026-07-04.
  Clarified (2026-07-04): this is the item that delivers the user's "each distro's built-in app store / software centre" request. Those centres (GNOME Software, KDE Discover, Ubuntu App Center, Pop!_Shop, Mint Software Manager, elementary AppCenter) are front-ends that read Flathub / Snap / distro repos — there is no per-store submission. So FIBR-0015 (Flathub → GNOME Software + KDE Discover, the majority of distros) + this item (Snap → Ubuntu App Center; native RPM/DEB → repo-based centres) together cover essentially every distro software centre. No separate work per store.

- 📋 [FIBR-0045] **Free Windows/macOS package managers: winget, Chocolatey, Homebrew Cask.**
  Free, self-publishable manager listings that just reference the GitHub Release artifact: (a) winget — a manifest PR to microsoft/winget-pkgs (`winget install finbreak`); (b) Chocolatey — a community nuspec package; (c) Homebrew Cask — a Ruby cask pointing at the macOS .dmg (`brew install --cask finbreak`). No paid account and no signing rework beyond what FIBR-0015 already does. Reaches the more technical slice of Windows/Mac users and gives them auto-update. Depends on FIBR-0015/FIBR-0016.
  **Layman:** Also list the app in the free 'app installers' many Windows and Mac users already use, so they can install and auto-update it with one command — no store account needed from us.
  Kind: package.
  Source: user-request-2026-07-04.

- ✅ [FIBR-0056] **Desktop-launcher integration — running window groups under its launcher (single taskbar icon) + branded icon.**
  Shipped 2026-07-09. A down-payment on FIBR-0015 desktop integration, done now at
  the user's request. app.py sets applicationName + QGuiApplication.setDesktopFileName
  = "finbreak", so the running window's Wayland app_id (X11 WM_CLASS) matches
  finbreak.desktop (StartupWMClass=finbreak) — KDE/GNOME then group the window under
  its launcher instead of showing a second, generic icon. On the user's machine: the
  branded PNGs were installed into ~/.local/share/icons/hicolor/*/apps/finbreak.png and
  the pinned finbreak.desktop's Icon= was pointed from wallet-open to finbreak (caches
  rebuilt). Repo change is app.py only; the .desktop + icon-theme install are
  per-machine (the canonical packaged .desktop + hicolor install belong to FIBR-0015).
  Verified: gate green 344 passed/1 skipped, mypy 0; desktop-file-validate clean; app
  launches with app_id/desktopFileName = finbreak.
  **Layman:** Fixes the app showing a second, generic icon in the taskbar when open, and puts the new icon on the panel launcher.
  Kind: implement.
  Source: user-request-2026-07-09.

- ✅ [FIBR-0082] **Generate app screenshots from synthetic dummy data for the GitHub README + antsprojectshub.co.za.**
  A reproducible way to populate a THROWAWAY vault with realistic-but-fake dummy data (a spread of accounts, a month or two of categorised transactions, a couple of imported statements, a few rules) and capture screenshots of the key screens for the GitHub README and https://antsprojectshub.co.za/.
  Resolved (2026-07-23): scripts/seed_demo_vault.py seeds a throwaway ZAR
  demo vault (3 accounts, ~13 months of categorised transactions, 3-level
  nested categories, auto-rules, confirmed transfers + recurring), and
  scripts/capture_screenshots.py renders every main tab offscreen in both
  the Midnight (dark) and Ledger (light) themes, plus a curated mixed-theme
  site/ set matching the metainfo <image> URLs. 20 PNGs under
  assets/screenshots/; metainfo now lists 6 captioned shots. Demo vault kept
  at .demo-vault/ (git-ignored) for reuse. Statements shot deferred (see
  FIBR-0162). Still user's: upload assets/screenshots/site/* to
  antsprojectshub.co.za/img/finbreak/ before the Flathub/OBS submit.

  Scope: a scripted seeder (e.g. scripts/seed-demo-vault.py) that first-runs a vault and inserts synthetic transactions/categories/accounts/rules, plus a documented capture flow for the main views — first-run, unlock, Home, Statements tab, Categories, Rules, the import wizard, and (once P10/FIBR-0012 lands) the spending-by-category dashboard, which is the most compelling shot.

  HARD constraint (security-model INV-6 / testing.md §6): screenshots use ONLY synthetic dummy data — never real financial data, never a real statement, never a committed vault. The seeded vault + captured PNGs are throwaway artifacts (or committed only as marketing PNGs under a docs/ or assets/ path, never the vault/data itself).

  Not blocked: the current shell (Home/Statements/Accounts/Categories/Rules tabs, import wizard) can already be captured now; re-run after the dashboard (FIBR-0012) ships to add the headline dashboard shot. Pairs naturally with a P13 release.
  **Layman:** Create polished screenshots of the app filled with realistic fake sample data — for the GitHub page and the portfolio site — so people can see what it looks like without installing it.
  Kind: marketing.
  Lanes: docs, ui, marketing.
  Source: user-request-2026-07-10.

- ✅ [FIBR-0155] **Publish finbreak via the openSUSE Build Service (OBS) — native RPM/deb + the openSUSE software portal.**
  User has an OBS account (build.opensuse.org) and wants finbreak on the openSUSE store + other Linux distro channels. OBS builds native packages for many distros from one recipe and publishes to software.opensuse.org + downloadable repos — complementary to the existing AppImage (FIBR-0054) and the deferred Flatpak/Flathub (FIBR-0130).
  Resolved (2026-07-21): OBS native-from-source packaging SHIPPED (code + recipes; gate green 1244/2). Spec docs/specs/FIBR-0155.md cold-eyes-CONVERGED loop 6. Decisions: (1) native-from-source, PyInstaller --onedir frozen runtime under /usr/lib/finbreak/ (security-critical stack — SQLCipher/qpdf/pdfium/Qt — stays BUNDLED, not distro-shared, § 3.2); (2) four confirmed targets (Tumbleweed, Fedora, Debian 13, Ubuntu 24.04) + Leap 15.6 pending one glibc check (§5, likely a 5th); (3) version flows tag → _service set_version → recipes; (4) metainfo <release> + debian/changelog mirror CHANGELOG via 2 new bump.json todos + post_check. Ships packaging/obs/ (finbreak.spec, debian/, io.github.milnet01.finbreak.desktop + .metainfo.xml [validates via appstreamcli], finbreak.sh launcher, _service, README runbook). Edits: pyproject [project.scripts], app.py Wayland app_id → reverse-DNS app-ID (X11 WM_CLASS stays 'finbreak'), security-model INV-8 distro note, naming.md app-ID resolved, bump.json sync. Reproduce-first TDD: tests/features/obs_packaging/ INV-1..8 (RED pre-recipes → green). CAVEAT: the "real OBS build green" exit criterion is a MANUAL maintainer step on the user's build.opensuse.org account (documented osc flow in packaging/obs/README.md + the §5 pre-submit checklist: Leap glibc go/no-go, per-distro package names, wheel vendoring, live xprop WM_CLASS, screenshots) — like FIBR-0131's live-swap caveat, not automatable in this repo's CI.
  Progress (2026-07-23): during OBS manual bring-up, the _service wheel-vendoring command was found broken — it used pip download --only-binary=:all:, but ofxparse ships as an sdist only (no PyPI wheel), so pip resolved nothing and aborted the whole closure (0 wheels), taking ofxparse's own deps lxml + six with it; the offline %build would have failed. Fixed: pre-build ofxparse into a universal wheel, then --find-links vendor/ so it satisfies the binary-only constraint and pip pulls lxml (dual-ABI) + six normally. Verified by an offline --no-index install into a clean cp313 venv importing the full stack (34 wheels, vendor.tar.gz ~300M). Build recipes (finbreak.spec/debian/rules) needed no change — they only pip install --no-index --find-links vendor/. Also corrected the runbook home:milnet01 -> home:milnet (OBS username).

  Scope to decide in the spec: (1) native-from-source packaging (an RPM `.spec` + a `debian/` recipe that pip-installs the PySide6 app + its native deps — SQLCipher, pikepdf/qpdf — into a distro package, .desktop + icon + AppStream metainfo) vs. wrapping the frozen AppImage; native is the "app store" experience OBS is built for. (2) Which targets to enable (openSUSE Tumbleweed/Leap, Fedora, Debian, Ubuntu). (3) How versioning/signing/release automation ties to the existing bump + release pipeline. (4) The AppStream metainfo `<release>` notes must mirror CHANGELOG (see changelog-writer). Needs: spec → /cold-eyes → implement (OBS project config + recipes + a submit/tag step) → verify a real OBS build. Dependencies: the app is feature-complete + already ships an AppImage, so no code blockers.
  **Layman:** Get finbreak into Linux "app stores": one OBS setup builds native openSUSE/Fedora (RPM) and Debian/Ubuntu (deb) packages and lists it on software.opensuse.org, so users install + auto-update it the normal way for their distro.
  Kind: package.
  Lanes: packaging, release.
  Source: user-request-2026-07-21.

- 📋 [FIBR-0163] **Add a populated Statements-tab screenshot via a synthetic statement import.**
  FIBR-0082's capture omits the Statements tab: the demo seeder inserts
  transactions straight through the repository, so no StatementPeriod rows
  exist and the Statements list renders empty. To capture it, drive a
  synthetic CSV/OFX through the real import path (ImportService / the import
  wizard) in scripts/seed_demo_vault.py, then re-add "statements" to
  scripts/capture_screenshots.py's _SCREENS. Low priority — the other 7 tabs
  already cover the headline features.
  **Layman:** One screenshot (the "Statements" list) is still blank because the demo data is added directly rather than by importing a bank file; this adds that missing shot.
  Kind: marketing.
  Source: in-session-2026-07-23.

- ✅ [FIBR-0164] **Keep README.md current every release; fix stale Windows signing + auto-update status.**
  User directive (2026-07-23): ensure README.md is up to date on every
  release. Fixed two stale claims: the "Code signing" section said Windows
  builds were SignPath-signed (SignPath DECLINED — FIBR-0133), and the
  Windows install section said "no auto-update on Windows" (FIBR-0131 shipped
  Windows in-app auto-update + the signed .exe release asset, confirmed on the
  v0.1.16 release assets). Also refreshed the feature list for 0.1.17's
  password-safety additions (hint, clipboard auto-clear, unlock throttle,
  verify-backup). Broadened .claude/bump.json's README todo to sweep the
  standing status sections (code signing, per-platform install/auto-update,
  distribution) against reality each release, not just the feature list; also
  recorded as a [[readme-update-every-release]] memory.
  **Layman:** Fixed the README so it no longer wrongly says the Windows app is officially signed or that it can't auto-update, and set things up so the README is checked on every release.
  Kind: doc-fix.
  Source: user-request-2026-07-23.

- 📋 [FIBR-0275] **A release can publish with no assets, and nothing notices — the README sends users to an empty page.**
  `cut-release` / the bump recipe carry the version bump, the tag and
  `gh release create`, but the AppImage and Windows `.exe` are built by a
  SEPARATE manual step (`.claude/bump.json` `_comment` says so). Nothing
  asserts the two ever meet. Cutting 0.1.21 published the release with
  **0 assets**, and the only thing that caught it was reading
  `gh release view --json assets` by hand.

  That matters more than it looks, because three things point users at
  those assets:
  - `README.md` § Install step 1 — "Download the `finbreak-*-x86_64.AppImage`
  from the latest release";
  - the in-app updater, which resolves the newest release and looks for an
  asset matching `AppImage`/`WindowsInstaller.asset_suffix()`;
  - `FIBR-0203`, already ✅, which was the same class of failure once
  removed — a release that existed but was invisible to the updater.

  So the gap has bitten before and was closed as a one-off rather than
  guarded.

  Cheapest guard, and it needs no new machinery: a post-publish assertion
  in the release path that `gh release view v<NEW> --json assets` returns at
  least the AppImage plus its `.sig`, and fails loudly otherwise. A
  stronger version also checks each asset name against the pattern the
  updater actually greps for, which is the specific trap `.claude/bump.json`
  already warns about in prose for the Windows `.exe` ("the name MUST match
  `WindowsInstaller.asset_suffix()` '-x86_64.exe' or the updater won't find
  it — no automated guard").

  Note the ordering constraint: the assets cannot exist before the tag, so
  this is a check that runs after `gh release create`, not a pre-flight.
  **Layman:** If the person cutting a release forgets the separate build step, the download page is published empty and the app's own "download the latest release" link leads nowhere.
  Kind: fix.
  Source: in-session-2026-08-17 (found while cutting 0.1.21).
  Progress (2026-08-17): still open — but the case is now stronger than
  when this was filed, and the guard should check MORE than presence.

  Cutting 0.1.21 hit the failure a second time, in a worse shape. The
  final `gh release upload --clobber` in `release-windows.sh` took an
  HTTP 503 part-way down its file list. `--clobber` deletes each existing
  asset before replacing it, so the release was left carrying
  `SHA256SUMS.sig` but NOT `SHA256SUMS`, and `.exe.sig` but NOT the
  `.exe` — a signed release whose signed manifest had been deleted.
  Nothing errored loudly: the script had already printed its signing and
  verification successes, and the failure was the last line.

  So presence-of-any-asset is too weak a guard. Three checks, cheapest
  first:
  1. the asset COUNT is 8;
  2. every `.sig` has its subject present (a `.sig` without its artifact
  is the partial-upload signature, and it is silent);
  3. each name matches what the updater greps for — `AppImage` and
  `WindowsInstaller.asset_suffix()`'s `-x86_64.exe`.

  Also worth folding in: upload one file per call rather than batching,
  so a partial failure is visible in the exit status.

  Repaired by hand for 0.1.21; `/releases/latest` now resolves to
  v0.1.21 with all 8 assets, and the published SHA256SUMS verifies
  against the committed RELEASE_PUBLIC_KEY_B64.

  v0.1.20 remains at ZERO assets and is NOT repaired — it is no longer
  `latest`, so nothing resolves to it, but anyone holding that tag's URL
  still gets an empty page. Decide separately whether to back-fill it
  (FIBR-0203 is the precedent for doing so).
  Progress (2026-08-19, commits d482545 + e49285e): the three-check guard is IMPLEMENTED and green, locked by a new INV-8 in tests/features/release_integrity/. Both release scripts now read their asset list back after publishing and refuse to report success on an incomplete set -- count (phase-correct: 5 after release-linux.sh, 8 after release-windows.sh), every .sig having its subject, and each name matching the updater's asset_suffix(). A fourth check reports a read-back that could not COMPLETE as its own failure and retries 3x, so the API's transient 503s do not cry wolf. Exercised against real data, not just source-scraped: the real v0.1.21 asset set passes, and zero assets / a dangling SHA256SUMS.sig at count 5 / a misnamed AppImage / a misnamed .exe each fail the check they should, with the dangling-sig case passing check 1 first -- which is the proof that check 2 is not redundant. STAYS OPEN, because the headline scenario is NOT fully closed. v0.1.20 published empty because cut-release created the release and release-linux.sh was never run at all; a guard living INSIDE release-linux.sh cannot fire when nobody runs release-linux.sh. What is covered now is "the asset step ran and the result is wrong". What is still uncovered is "the asset step never ran" -- which needs a check at the end of the whole release recipe, not inside one of its scripts. Also not done: the bullet's "upload one file per call". INV-4 asserts each upload block carries the whole asset list, so splitting it would redden that test, and the read-back already covers the partial state that change was meant to make visible. Recorded as a decision rather than an oversight.
  Progress (2026-08-19): v0.1.20 is BACK-FILLED and the "remains at ZERO
  assets and is NOT repaired" paragraph above is now historical. User
  decision 2026-08-19, given the choice between leaving it, back-filling
  and deleting the release. Built from a detached worktree at the v0.1.20
  tag using THAT tag's own release scripts (not HEAD's), so the artifacts
  are what 0.1.20 should have shipped. The tag's committed
  RELEASE_PUBLIC_KEY_B64 is byte-identical to HEAD's, so the signatures
  are the ones every installed copy's updater checks. v0.1.20 now carries
  all EIGHT assets and the PUBLISHED SHA256SUMS verifies against that key
  and names both platforms. /releases/latest still resolves to v0.1.22 --
  release-linux.sh took its `gh release upload --clobber` branch, and
  `--latest` appears only on the `gh release create` branch it did not
  take. This closes the FIBR-0203-precedent half of this item and nothing
  else: the item STAYS OPEN for the reason recorded above, that a guard
  living inside release-linux.sh cannot fire when nobody runs
  release-linux.sh.

- 📋 [FIBR-0304] **Cut v1.0.0 — the gate is five conditions and four named blockers.**
  User-approved 2026-08-20 on the question "what gets us to v1.0?".
  docs/standards/versioning.md 5 owns the CRITERIA; this item owns the
  current blocker list, because a standard naming today's roadmap ids
  goes stale and a roadmap bullet does not.

  Why now: 196 shipped items across all thirteen planned phases, P02-P11
  with zero open items, 23 published releases -- all still numbered
  0.1.22 because nothing said when to stop.

  BLOCKERS, and only these four:
  - FIBR-0019 (recovery key) -- 5 condition 1. Its own body says the key
    envelope must exist at vault creation and retrofitting needs a full
    re-encrypt migration, so doing it before 1.0 is cheap and after is a
    migration over real financial data.
  - FIBR-0208 (AppImage libxkbcommon segfault) -- 5 condition 3, a crash
    on a mainstream Linux configuration.
  - FIBR-0237 (no SECURITY.md / CODE_OF_CONDUCT.md) -- 5 condition 4.
  - FIBR-0217 (dark-theme PDF page numbers black on dark) -- a visible
    defect in a headline feature; 5 condition 5.
  Plus FIBR-0300, the stale pre-alpha badge, whose wording should be
  picked against this standard rather than in isolation.

  EXPLICITLY NOT BLOCKERS, decided rather than overlooked:
  - FIBR-0159 (Flathub) and FIBR-0133 (SignPath code signing). Both are
    stuck on a third party, and versioning.md 5 rules out any third
    party's queue as a gate by name -- a version number that waits on
    somebody else's inbox never arrives.
  - The 48-item features backlog, i18n, macOS, Snap/AUR/winget and the
    performance items. Those are 1.1 and 1.2.

  OPEN QUESTION FOR THE USER, not yet answered: does FIBR-0019 ship IN
  1.0, or do we freeze the vault format without it? Freezing without it
  means either living with "forget your password, lose everything"
  permanently, or paying a full re-encrypt migration later. If it is too
  big to take now, versioning.md 5's named interim applies: cut 0.9.0
  ("we believe this is it; the format is not frozen yet"), which is the
  one judgement-based exception to 4.2 and 6.2.
  Answered (2026-08-20, user): FIBR-0019 SHIPS IN 1.0. The open
  question above is closed -- we do not freeze the vault format
  without a recovery key, and we do not cut 0.9.0 as an interim.
  The reasoning the user accepted: the key envelope has to exist at
  vault-creation time, so building it now is cheap, while
  retrofitting it later is a full re-encrypt migration over real
  financial data. So the blocker list stands at four, unchanged,
  with FIBR-0019 as the long pole and the only one needing a spec.
  Blocker status (2026-08-25): THREE remain, not four. FIBR-0237
  (SECURITY.md + CODE_OF_CONDUCT.md) is ✅ — both files are in the tree —
  so the list above is stale on that one line and is not re-edited here,
  because the bullet records the decision as it was taken.

  Still blocking: FIBR-0019 (recovery key), FIBR-0208 (AppImage
  libxkbcommon segfault), FIBR-0217 (dark-theme PDF page numbers). Plus
  FIBR-0300's badge wording, to be picked against versioning.md § 5.

  FIBR-0019 is further from done than its 🚧 suggests. FP02 closed all
  thirteen of its review findings, then its own close attempt was BLOCKED:
  review-code found nine defects FP02 itself introduced, now FP03
  (FIBR-0310). FIBR-0019 returns to ✅ only when that chain closes clean.
  The other two blockers are small self-contained defects.
  **Layman:** The plan for calling the app finished: what has to be true first, and which four jobs are standing in the way.
  Kind: release.
  Source: user-decision-2026-08-20 ("what gets us to v1.0?").

## Enhancements & performance backlog

Ideas captured 2026-07-01 from a product / performance review
(user-requested). Not yet slotted into the P0x phase order — each
carries a **Target phase** and `Dependencies:`; it is promoted into that
phase when its dependencies land. Two are **foundational** (marked
*Sequencing*) and must be designed at the noted phase, not deferred,
because retrofitting them is a data migration.

- ✅ [FIBR-0297] **CSV import maps no column automatically — every dropdown defaults to the first column even when the headers say what they are.**
  `_set_header` (src/finbreak/ui/import_wizard.py:1013-1017) fills all five
  column combos with the same header list and calls no setCurrentIndex, so
  each lands on index 0. Observed on a CSV headed `Date,Description,Amount`:
  Date column, Description column, Amount column, Debit column and Credit
  column ALL read "Date" on arrival at the map step.

  Nothing is wrong -- the mapping is correct once set, and the date-format
  detector (FIBR-0146) and the saved-profile auto-match (FIBR-0007 INV-10a)
  both work. The gap is that those two are the ONLY automatic help: a file
  with no saved profile gets no column guess at all, however obvious its
  headers.

  Proposed: a header-name guess for the unmatched case only -- match each
  role against a small set of conventional spellings, case- and
  punctuation-insensitive (date / transaction date / posting date;
  description / details / narrative / reference; amount / value; debit /
  withdrawal; credit / deposit). Leave the combo on index 0 where nothing
  matches, so the current behaviour is the fallback rather than a
  regression.

  Constraints worth stating before anyone builds it: the guess must not
  fire when a profile matched (that path is already correct and INV-10a
  jumps straight to preview), it must be visible and overridable rather
  than silent, and it must not touch the date-format detector's
  single-owner wiring (FIBR-0146 D5/D6), which re-detects on a date-COLUMN
  change -- a guess that sets the date column has to go through the same
  path or the format detection goes stale.

  Not a Flatpak issue: reproduced through the sandbox but identical on a
  host build; the code path has no platform branch.
  Resolved (2026-08-20): new pure module importers/column_detect.py
  (guess_columns -> ColumnGuess) matches each role against the
  conventional spellings, case- and punctuation-insensitively, and
  returns the original header string. Wired at the four D5 fire points
  that reach the map step unmatched -- the unmatched CSV, both
  generic-PDF no-match branches, and the batch ask step -- signal-blocked
  and BEFORE the existing date detect, so the FIBR-0146 single-owner
  wiring reads the guessed date column. Not wired at D5(c), the user's
  own column change. A role the header does not name is left alone, so
  the first-column default stays the fallback. Contract:
  tests/features/import_column_detect/ (INV-1..INV-7), 21 tests. No spec
  under spec-format.md 1 -- one subsystem, obvious shape. Matcher check:
  13 real header shapes, every verdict read, no wrong-role claims.
  Follow-up noted, not filed: "Merchant" and "Effective Date" are common
  real columns the synonym set does not cover. Commit cddb78f.
  **Layman:** When you import a spreadsheet for the first time, the app makes you tell it which column is the date, which is the description and which is the amount — even when the file already labels them exactly that.
  Kind: enhancement.
  Source: in-session-2026-08-20 (found during the FIBR-0159 Flatpak § 5 portal smoke).
  Lanes: importers, ui.

### 🔒 Security & account recovery

- ✅ [FIBR-0018] **Encrypted vault backup & restore.**
  Export the whole vault to a single encrypted backup file the user
  keeps off-device (external drive / cloud), and restore from it — the
  mitigation design.md names for the no-recovery-backdoor rule, so a disk
  failure or lost laptop doesn't mean lost data. Target phase: P12 (its
  heading already lists "backup"). Dependencies: FIBR-0004. Lanes:
  crypto, ux. Kind: feature. Source: user-request-2026-07-01.
  Merged into FIBR-0014 (2026-07-13): FIBR-0018 and the narrowed FIBR-0014 both describe the encrypted vault backup & restore. FIBR-0014 (docs/specs/FIBR-0014.md) is the IMPLEMENTATION spec; track the work there. The backup safety nudge is FIBR-0089; restore-verification is FIBR-0033. This item stays as the original provenance record — flip it ✅ alongside FIBR-0014 when the backup ships.
  Resolved (2026-07-28): closed as covered by its merge target. FIBR-0014
  (P12 settings / auto-lock / encrypted backup) is ✅ and the encrypted
  vault backup & restore it absorbed is live — services/backup.py plus the
  backup_export / backup_restore / backup_verify dialogs. This bullet was
  kept only as the original provenance record per the 2026-07-13 merge
  note, which said to flip it alongside FIBR-0014; doing that now.
  Kind: feature.
  Source: user-request-2026-07-01.
  Lanes: crypto, ux.

- 🚧 [FIBR-0019] **Master-password recovery via recovery key (key-wrapping).**
  At vault creation, generate a high-entropy recovery
  code the user stores safely; wrap the vault data-key under **both** the
  master password and the recovery code (envelope encryption) so a
  forgotten password is recoverable via the code with **no** backdoor.
  *Sequencing:* foundational — the key envelope must exist at FIBR-0004
  (vault creation); retrofitting needs a full re-encrypt migration.
  Requires an ADR + a security-model.md update at spec time. Target
  phase: P02. Dependencies: FIBR-0004. Lanes: crypto, security.
  Kind: security.
  **Layman:** If you forget your master password, a recovery code you saved when the vault was created gets you back in — with no backdoor anyone else could use.
  Spec accepted (2026-08-20):
  docs/specs/FIBR-0019-master-password-recovery-key.md, 1027 lines.
  review-contract reached its cap at loop 3 -- three loops, nine cold
  lanes, 31 verified findings, all fixed, none dismissed. A CALM cap
  (33% of the final loop landed on the run's own text, down from 45%),
  so the spec ships and the build is the next reviewer.

  The design: the database stops being encrypted directly by a
  password-derived key. A random data key (DEK) encrypts it and is
  wrapped twice in the sidecar -- once under a key from the master
  password, once under a key from a 135-bit Crockford base32 recovery
  code. Either credential unwraps the same DEK, so adding or changing a
  credential re-wraps 32 bytes and never re-encrypts the database.

  Twelve invariants, five test files, and a six-step migration for the
  vaults already in the field with a resume rule per crash window.

  NOT yet built. Next is write-test (the suite must be seen RED first),
  then write-code. Two things implementation must not lose:

  - The migration's master slot inherits the v1 salt AND the v1 cost
    parameters. That is what makes the key already derived at unlock
    BE the wrapping key -- no re-derivation, no carrying the plaintext
    password past derivation, and no stranding a vault whose recorded
    memory_kib sits below a later-raised pin.
  - BackupService.restore_backup and FIBR-0014 D4 both still prescribe
    the v1 restore path. Left alone they keep minting v1 vaults after
    this ships. Section 11 lists all fourteen documents that change.

  Also filed by the run, not fixed here: no roadmap item exists for
  "change the master password" as a settings action, which this design
  makes nearly free. Worth queueing.
  Progress (2026-08-21): picked up for the build. Correcting this
  bullet's own record above -- the gate ran FOUR loops, not three. The
  accepted spec is 1108 lines with THIRTEEN invariants, and the run
  totalled twelve cold lanes and 37 verified findings, all fixed, none
  dismissed. Loop 4 was violent (five of its six findings landed on text
  the same session had written), which is what stopped the run there;
  implementation is the next reviewer and the spec is not to be re-gated.

  Now at write-test. The suite is tests/features/recovery_key/ per the
  spec's sections 7 and 10 -- five files, thirteen tests, one per
  invariant -- and it must be seen RED before write-code starts. Route 1:
  none of the code exists yet, so there is nothing to revert.
  write-test done (2026-08-21). tests/features/recovery_key/ holds
  spec.md, the five files section 7 names, a shared _recovery_helpers.py,
  and thirteen tests under section 10's exact names. Registered in
  _NO_PROSE. Stubs added so the suite EXECUTES rather than dying at
  collection: keywrap.py, services/recovery_code.py,
  services/vault_migration.py, KeyUnwrapError, SIDECAR_VERSION = 2, and
  two AuthService stubs. Every stub body raises NotImplementedError;
  nothing is implemented. FORMAT_VERSION stays 1.

  Run: 14 failed, 0 collection errors (INV-13 is parametrised over its
  two injection points). ruff, ruff format and mypy all clean. Full gate:
  16 failed, 1951 passed -- the 14 by design plus two pre-existing reds
  now filed as FIBR-0306. No regression from the stubs.

  One test was strengthened after the authoring pass. INV-3 leg 3
  originally called validate_params on a hand-built KdfParams, which only
  re-proves that crypto.py's floor rejects a halved memory_kib -- already
  true today, and still true if the v2 load path never consults it. It
  now writes the weakened sidecar to disk and calls
  load_and_validate_params, the path AuthService.load_params actually
  takes.

  THE GAP, and write-code owes it. This is greenfield, so all thirteen
  fail at the first absent surface -- first_run not returning a code,
  migrate_to_v2 raising, or a named seam missing -- and NOT on their own
  invariant assertion. So no invariant assertion here has yet been
  observed to fail. Going green is therefore not sufficient evidence.
  As each invariant is implemented, break its specific property on
  purpose and watch THAT assertion fail before accepting the green.
  The legs most worth this: INV-1 leg 2, INV-2 leg 3, INV-3 leg 4 and
  INV-11 leg 1, each of which the spec says the obvious implementation
  passes for the wrong reason.

  Six naming seams were chosen that section 4 does not fix; spec.md
  lists them with reasons. The load-bearing one is AuthService.first_run
  widening from returning nothing to returning the display-form code --
  INV-5 forbids retaining it, so there is no other route by which
  anything can learn it.

  Not pushed: the gate is red by design until write-code lands.
  write-code done (2026-08-21). All thirteen invariants green; full
  gate 1965 passed with only the two pre-existing FIBR-0306 harness
  reds. Built: keywrap.py (AES-256-GCM slot wrap, slot name + costs as
  AAD), services/recovery_code.py (Crockford base32, mod-37 check
  symbol), the v2 slots sidecar in crypto.py with
  load_and_validate_params dispatching on sidecar_version,
  services/vault_migration.py (S0..S6 + the section 13.3 resume
  ladder), AuthService's envelope first-run / slot re-wraps / unlock
  dispatch / D2 auto-migration, the UnlockDialog recovery route, and
  ui/recovery_key.py for the one-time display, the forced new password
  and Settings' Add / Replace / Remove.

  GREEN WAS NOT ACCEPTED ON ITS OWN, per the gap this bullet recorded.
  Seven mutants were run against the implementation and every one was
  watched to fail on its own assertion: INV-1 leg 1 (DEK = KEK-master)
  and leg 2 (a credential-derived DEK under a non-fresh salt, which is
  section 8.1's rejected design), INV-2 leg 3 (decode stops folding
  I/L/O), INV-3 leg 4 (the AAD stops naming the slot), INV-7 (the
  resume ladder removed), INV-11 leg 1 (the hint scanned raw rather
  than normalised), INV-12 (the declined code's slot written anyway).
  Three mutants survived a first attempt and each was a defective
  mutation rather than a vacuous test -- worth knowing: INV-1 leg 2
  does NOT fire on a DEK derived under a FRESH salt, because that is
  random per vault; it fires on a non-fresh one, which is what section
  8.1 actually is.

  Two deliberate reconciliations against section 4, both recorded in
  the spec's own amendment: the recovery KEK is derived at step 9
  rather than step 4 (nothing observable differs, and Decline now
  costs one derivation instead of two), and Vault.create keeps its v1
  sidecar write behind a write_sidecar flag that first-run passes
  False -- removing it outright would break the v1 fixtures every
  migration test builds from.

  One test-harness repair, and it was a real gap: _recovery_helpers'
  open_after_restart claimed to open "the way a FRESH APP START would"
  and did not run section 13.3's resume, so INV-7's S4-complete case
  could not pass by any implementation -- between S4 and S5 the
  sidecar names a DEK no database on disk answers to yet. It now calls
  the production resume. No assertion was changed.
  Re-opened (2026-08-21) by /close-phase: the close is BLOCKED and the ✅
  above was premature. The code is built, pushed (7e6c11f) and green, but
  check-code plus three review-code lanes found thirteen actionable
  defects in it, batched into FP02 / FIBR-0307. Two are severe enough
  that calling this shipped overstates it:

  - verify_check_symbol compares the check symbol UNFOLDED, so roughly
    2 of 37 issued codes are refused when the user transcribes 1 as I or
    0 as O -- the exact confusion Crockford was chosen to remove -- and
    the same call gates INV-11's hint scan, so the substituted form is
    accepted into plaintext window.ini.
  - A broken vault/sidecar pairing is reported as a wrong password with
    the destructive reset on screen, which section 6 forbids by name.
    The _PAIRING_BROKEN message written for it is unreachable.

  Reverting to 🚧 rather than leaving ✅ is also the interlock that stops
  a release going out over this: cut-release refuses when a CHANGELOG
  section claims an id that is not ✅, and the FIBR-0019 entry is already
  in [Unreleased]. It goes back to ✅ when FP02 closes and /close-phase
  runs clean.

  Worth recording for the next reviewer of this item: the thirteen
  tests all passed, and the mutation checks all fired. Neither caught any
  of the thirteen. INV-2 leg 3 in particular CANNOT catch the check-symbol
  defect -- it substitutes inside `payload` and re-appends `check`
  untouched, so the one position that is broken is the one position the
  test holds fixed.
  Source: user-request-2026-07-01.
  Lanes: crypto, security.

- 📋 [FIBR-0020] **Biometric unlock (fingerprint / face) with capability detection.**
  Store a key-wrapped copy of the vault key in the OS secure
  keystore, released by the platform biometric (Windows Hello, macOS
  Touch ID, Linux fprintd where present). **Detect** availability per-OS
  and offer it only when present; always keep the password as fallback. A
  convenience unlock, **not** a recovery method — Linux biometric support
  is uneven, so degrade gracefully. Target phase: P12. Dependencies:
  FIBR-0004, FIBR-0019 (shares the key-wrapping envelope). Lanes: crypto,
  platform, ux. Kind: feature. Source: user-request-2026-07-01.
  **Layman:** Unlock the vault with your fingerprint or face where your computer supports it, with the password always still available as a fallback.
  Kind: feature.
  Source: user-request-2026-07-01.
  Lanes: crypto, platform, ux.

- ✅ [FIBR-0029] **Password reminder / hint (shown before unlock).**
  An optional user-set hint on the unlock screen to jog memory —
  enforced to **not be the password** (and not to contain it). *Security
  note:* the hint must render **before** the vault is decrypted, so it
  lives **outside** the encrypted DB and is readable by anyone with
  device access — warn the user, keep it short, and record the new
  plaintext artefact in security-model.md at spec time. A memory aid, not
  a recovery method. Target phase: P02. Dependencies: FIBR-0004. Lanes:
  crypto, ux. Kind: feature. Source: user-request-2026-07-01.
  Design resolved by user 2026-07-20 (autonomous run): (1) SET the hint via a "Set password hint…" button in Settings that prompts for the CURRENT master password, verifies it, then enforces hint ≠ password AND hint does-not-contain password (needs plaintext in hand — hence the confirm), and saves to the plaintext window.ini (readable pre-unlock, outside the encrypted vault). (2) SHOW the hint on the unlock screen behind a "Show hint" button (hidden by default, reveal-on-click — reduces shoulder-surf exposure). Defaults decided: ~100-char cap; a plaintext-storage warning shown when setting; empty/unset hint means no "Show hint" affordance appears. security-model.md gains the new plaintext artefact (hint) as an asset + an enforcement invariant (hint never equals/contains the password) — that doc edit runs through /cold-eyes per §14. Ready to spec.
  Resolved (2026-07-20, autonomous run): shipped. Optional plaintext password hint shown on the unlock screen behind a reveal-on-click "Show hint" button; SET from Settings ("Set password hint…" → confirm current password via new AuthService.verify_password, constant-time hmac.compare_digest against the session key). Enforced never to equal/contain the master password (pure services/password_hint.validate_hint: NFC-normalize + casefold both sides, unconditional containment — a short password can't be embedded verbatim; obfuscation out of scope). Stored in plaintext window.ini (key hint/text, readable pre-unlock). security-model.md gains A1 plaintext-artefact note + INV-11; that doc edit cold-eyes converged loop 1. Spec docs/specs/FIBR-0029.md cold-eyes converged loop 2 (loop 1 caught a short-password leak: dropped a len>=4 carve-out). 24 hint tests (INV-1..9); full gate green (1197 passed, 2 skipped). commit 4ddf725; tag FIBR-0029-complete.
  Kind: feature.
  Source: user-request-2026-07-01.
  Lanes: crypto, ux.

- ✅ [FIBR-0030] **"Forgotten password → start over" (destructive vault reset, double-confirmed).**
  Last resort on the unlock screen once the
  hint (FIBR-0029) and recovery key (FIBR-0019) are exhausted:
  irreversibly delete the vault and its sidecars and return to first-run
  setup so the user can begin fresh. **Double confirmation required** — a
  clear "this erases everything, permanently and unrecoverably" warning
  **and** a second explicit step (e.g. type DELETE) before anything is
  removed. By design nothing survives (the old data can't be decrypted
  without the key anyway). Target phase: P02. Dependencies: FIBR-0004.
  Lanes: crypto, ux. Kind: feature. Source: user-request-2026-07-01.
  Design confirmed by user 2026-07-20 + recon done (autonomous run). Affordance: new flat "Forgotten password? Start over…" button on UnlockDialog, modelled on _restore_button (ui/unlock.py:67-71 create, :103 layout, :108 click) + a new `start_over_requested` signal; the SHELL owns the flow (mirror restore_requested → main_window `_open_restore`). Double-confirm: Step 1 = QMessageBox.question with "cannot be undone" prose (model ui/statements.py:220-237); Step 2 = a small purpose-built QDialog whose OK is gated on a text field == "DELETE" (textChanged→_sync_ok→setEnabled, model ui/backup_export.py:79-106; the type-a-word gate is net-new). New primitive `AuthService.reset_vault()` (net-new; mirrors first_run/lock): call service.lock() first (idempotent, Windows-safe), then unlink BOTH paths.vault_path() AND paths.sidecar_path() (both must go or Vault.presence_state() raises VaultStateError on a mixed state) — reuse the unlink idiom at main_window.py:1020-1021. CRITICAL non-obvious: also unlink the SQLite WAL sidecars vault.db-wal / vault.db-shm (WAL mode is on, vault.py:104/174; NO path helper exists and nothing unlinks them today → they'd orphan). Clear the vault-coupled window.ini keys: UnlockThrottle().reset() (ui/_unlock_throttle.py:73-79) + clear_hint() (ui/_password_hint.py:42-45); LEAVE benign UI state (geometry/window_state/last_tab/theme/update-opt-in). Return to first-run: after delete call main_window `_route_pre_login()` (:1025-1031) → state() now "first_run" (both files gone) → _show_first_run(). Tests: new tests/features/vault_reset/; mirror test_backup_ui.py:67-75 (button fires signal) + :151-181 (shell flow builds MainWindow, invoke reset handler, assert both files gone + window._dialog is FirstRunDialog + throttle/hint keys absent in window_ini); conftest `paths`(:48-52) + autouse `window_ini`(:107-120) fixtures. NEXT: write docs/specs/FIBR-0030.md → /cold-eyes --max-loops 7 → reproduce-first TDD → close. (Note: FIBR-0019 recovery key referenced in the headline prose is context only — the hard dep is FIBR-0004, shipped; do not block on FIBR-0019.)
  Resolved (2026-07-21): shipped. AuthService.reset_vault() deletes the complete on-disk footprint (vault.db + KDF sidecar + both SQLite WAL sidecars vault.db-wal/-shm); UnlockDialog "Forgot password? Start over…" button + start_over_requested; StartOverDialog type-DELETE gate (exec()-driven, wires accepted->accept itself); shell _on_start_over does Step-1 warning -> Step-2 dialog -> try reset_vault (OSError->critical box) -> clear throttle+hint keys -> teardown -> first-run. security-model.md INV-12 (deletion-completeness hygiene) + T11 note. Spec docs/specs/FIBR-0030.md cold-eyes CONVERGED loop 6 (7-loop cap); reproduce-first TDD, 12 vault_reset tests, gate green 1209 passed. Tag FIBR-0030-complete.
  Kind: feature.
  Source: user-request-2026-07-01.

- ✅ [FIBR-0031] **Failed-unlock throttling (exponential backoff).**
  Slow down brute-force guessing of the master password: after each wrong
  attempt on the unlock screen, impose a growing delay (e.g. 1s → 2s → 4s
  …, capped) before the next try is accepted. A one-off typo is barely
  noticeable; bulk guessing becomes infeasible. Pure client-side timing —
  no lockout that could deny the legitimate owner access, and no counter
  that weakens the crypto. Record the backoff schedule in security-model.md
  at spec time. Target phase: P04 (lands with the unlock flow).
  Dependencies: FIBR-0004. Lanes: security, ux. Kind: security.
  Source: user-request-2026-07-01.
  Duplicate of FIBR-0095 (2026-07-15): both describe failed-unlock exponential backoff on the master-password unlock screen. FIBR-0095 is the newer, verified record (confirmed 2026-07-11 that services/auth.py applies no backoff) and is the tracking item for the implementation. This bullet stays as the original provenance record — flip it ✅ alongside FIBR-0095 when the throttling ships.
  Resolved 2026-07-18 as the duplicate of FIBR-0095 (shipped) — failed-unlock exponential backoff is implemented and tested there (services/unlock_throttle.py + ui/_unlock_throttle.py, security-model INV-10).
  Kind: security.
  Lanes: security, ux.

- ✅ [FIBR-0032] **Clipboard auto-clear for copied sensitive values.**
  When the user copies a sensitive value (account number, amount, a stored
  PDF password), clear it from the system clipboard after a short timeout
  (~30s, configurable in the FIBR-0014 Settings screen) so it doesn't
  linger for other apps to read. Only clear if the clipboard still holds
  the value we put there (don't wipe something the user copied since).
  Target phase: P12. Dependencies: FIBR-0012, FIBR-0014. Lanes: ui,
  security. Kind: security. Source: user-request-2026-07-01.
  Scope check 2026-07-18 (autonomous run): DEFERRED pending a product/scope decision. Recon found the app has NO app-wired clipboard "Copy" affordances anywhere (no QClipboard/setText into clipboard in src/), so auto-clear is greenfield — it has nothing to clear until copy points are added first. Deciding what becomes copyable is a real fork: amount/description in the transactions context menu are natural + safe, but a "copy the stored statement PDF password" affordance would be a NEW exposure that regresses FIBR-0128 INV-1 (that secret currently never crosses into the UI). Needs a user call on (a) which values become copyable and (b) whether the PDF password is copyable at all, before writing the spec. Not silently guessing a UX+security scope. Kept 📋.
  Scope RESOLVED by user 2026-07-18: copyable values = transaction AMOUNT + DESCRIPTION only (add "Copy amount"/"Copy description" to the transactions list context menu), auto-clear after ~30s (configurable). The stored statement PDF password stays NON-copyable (no regression of FIBR-0128 INV-1); account number NOT copyable in this pass. Unblocked — ready to spec when its turn comes (currently queued behind FIBR-0033).
  Resolved (2026-07-20, autonomous run): shipped. "Copy amount"/"Copy description" added to the transactions context menu (rendered cell text + in-memory description — no vault read, lock-safe INV-8); PDF password + account numbers stay NON-copyable (FIBR-0128 INV-1 preserved). New ClipboardAutoClear(QObject) helper: single owned single-shot QTimer wired directly to clear_if_ours; live per-copy timeout; clears only if the clipboard still holds our value. AuthService clipboard_clear_seconds getter/setter, ALLOWED=(10,30,60,0), DEFAULT=30; Settings combo; 0="Never" honoured. security-model.md T13 threat row added + cold-eyes converged (loop 1, polish-only). Spec docs/specs/FIBR-0032.md cold-eyes converged loop 9. 23 clipboard tests (INV-1..8); full gate green (1164 passed, 2 skipped). commit 0b45573; tag FIBR-0032-complete.
  Kind: security.
  Source: user-request-2026-07-01.
  Lanes: ui, security.

- ✅ [FIBR-0033] **Backup restore-verification ("does my backup work?").**
  A one-click check that opens an encrypted backup (FIBR-0018) into a
  throwaway in-memory / temp copy, confirms it decrypts and its schema +
  row counts are intact, then discards it — proving the backup is
  genuinely restorable **without** touching the live vault. A backup never
  test-restored is a guess, not a safety net. Target phase: P12.
  Dependencies: FIBR-0018. Lanes: crypto, ux. Kind: feature.
  Source: user-request-2026-07-01.
  Dependency re-points: FIBR-0018 (the backup mechanism) is merged into and implemented by FIBR-0014, so this restore-verification builds on FIBR-0014's .fbk export/restore (docs/specs/FIBR-0014.md), not a separate FIBR-0018 deliverable.
  Started 2026-07-18 (autonomous run, after deferring FIBR-0032 on scope). One-click "does my backup work?" — open a .fbk (FIBR-0014) into a throwaway temp/in-memory copy, confirm it decrypts + schema/row-counts intact, discard it, WITHOUT touching the live vault. Spec -> /cold-eyes -> TDD -> close.
  Resolved (2026-07-19): shipped read-only backup verification. Service verify_backup(src, backup_password, *, on_key=None) -> VerifyResult + shared _open_backup_vault helper (caller owns work_dir; backup key+password wiped on every path incl. exceptions — INV-7); runs cipher_integrity_check (early-return corrupt), as-migrated schema == LATEST_SCHEMA_VERSION (INV-2), display-only counts; reason-code table (wrong_password/corrupt/bad_kdf_params/too_new/invalid/io_error). UI: BackupVerifyDialog + Settings "Verify backup…" button (settings_verify_backup) + main_window wiring (synchronous under wait cursor; no auto-lock, verify never touches the live vault — D7/INV-1). security-model.md T5 note (post-login read-only reuse of FIBR-0014 guards; no new pre-login surface). All 7 deliverables done. Reproduce-first TDD: 14 new tests. Full gate green (1142 passed, 1 skipped). One cold code-review lane: clean, no findings. Commit 42bca98, tag FIBR-0033-complete. (Retires duplicate scope none; distinct from FIBR-0014 restore.)
  Kind: feature.
  Lanes: crypto, ux.

- ✅ [FIBR-0041] **Back-fill the CSV import path with the INV-5b resource-size cap.**
  security-model.md INV-5b binds an import resource budget (max file size / row count / parse time) to the import specs — naming FIBR-0007 (CSV) and FIBR-0008 (OFX) by id. FIBR-0008 pins the cap for the OFX path (D13: read_file_bytes stat-checks against _MAX_OFX_BYTES before read; a transaction-count cap). But FIBR-0007's CSV path (ImportService.read_file -> str) shipped WITHOUT a size cap, so security-model INV-5b's FIBR-0007 claim is currently unmet. Back-fill: apply the same size stat-check to read_file (or a shared bounded reader), pick a _MAX_CSV_BYTES constant, add a test (monkeypatch the cap down). Surfaced by the FIBR-0008 /cold-eyes (lane C, 2026-07-03).
  **Layman:** Add the same "reject a suspiciously huge file" safety limit to the CSV import that OFX import gets, so no oversized statement file can hog memory.
  Kind: security.
  Lanes: importers, services, tests.
  Source: cold-eyes-2026-07-03 FIBR-0008 lane-C.
  Resolved (2026-07-15): already shipped — verified stale bullet. ImportService.read_file (services/import_.py) routes through the shared _read_capped helper, refusing a file over _MAX_IMPORT_BYTES (16 MiB) BEFORE loading it, so security-model INV-5b's FIBR-0007 (CSV) claim is now met. Hardened beyond the original ask during a later indie-review (H-F/H-G): reads cap+1 bytes rather than trusting stat().st_size, so an endless-symlink (/dev/zero) or a file that grows post-stat can't slip an unbounded read past the cap. Tests: test_read_file_refuses_oversized_csv (monkeypatches the cap to 100) + test_read_capped_bounds_read_against_endless_symlink, both in tests/features/import_/test_import.py. No code change this session — flip only.

- ✅ [FIBR-0095] **Unlock throttling — backoff after repeated failed master-password attempts.**
  Verified 2026-07-11: services/auth.py applies NO delay/backoff on a failed unlock. Add an increasing backoff (spec finalized backoff-only — no lockout) after consecutive failed unlock attempts — defence-in-depth against bulk interactive guessing through the app's own unlock screen (the offline-crack path on a stolen vault is defended by Argon2id's slow KDF, security-model INV-2, not by this UI backoff). Track the attempt count / last-fail time in the plaintext window.ini (pre-unlock, non-sensitive; spec finalized persisted-not-in-memory so a relaunch can't reset the backoff); UX = a friendly 'try again in N seconds'. Deps: FIBR-0004 (unlock path).
  **Layman:** After several wrong master-password tries, finbreak briefly slows further attempts — extra protection if someone gets hold of your vault file.
  Kind: security.
  Source: claude-suggestion-2026-07-11.
  Started 2026-07-18 (self-directed, "build it all" autonomous run). Adding exponential backoff after repeated failed master-password unlock attempts; attempt count/last-fail persisted in plaintext window.ini so a relaunch doesn't reset the backoff. Spec -> /cold-eyes -> TDD -> /close-phase.
  Shipped 2026-07-18 (self-directed autonomous 'build it all' run). Capped exponential backoff (1s,2s,4s,…,30s) after a wrong master password in the unlock dialog; attempt count + last-fail persisted in plaintext window.ini so a relaunch can't reset it. Pure core services/unlock_throttle.py (exponent clamped BEFORE the power — tampered fail_count can't build a giant int) + QSettings adapter ui/_unlock_throttle.py (defensive int()/fromisoformat() coercion + tz-naive rejection) + UnlockDialog wiring (authoritative entry gate re-read every submit, 1-Hz countdown, reset-on-success, submit-only disable preserving FIBR-0004 INV-2f). security-model INV-10 (defence-in-depth, not a boundary). Spec /cold-eyes 4 loops → polish-converged; reproduce-first TDD 19 tests INV-1..7; /audit semgrep+bandit 0 on the changed surface; cold code-review caught 1 CRITICAL (tz-naive last_fail → aware/naive subtraction crash = owner lockout) folded reproduce-first + 1 LOW test tidy. Gate green 1126/1, mypy 0. Commits 7564234→7c8778d; tag FIBR-0095-complete.

- ✅ [FIBR-0096] **Per-release SHA256SUMS + generated SBOM alongside the signed AppImage.**
  The release AppImage is already Ed25519-signed (FIBR-0054 INV-14). Add, per release: a SHA256SUMS file (artifact checksums) and a generated SBOM (CycloneDX via cyclonedx-py, or pip-audit output) listing the bundled dependency versions — supply-chain transparency + a second integrity signal for users who verify manually rather than via the in-app updater. Wire into build-release-appimage.sh / the publish step. Deps: FIBR-0054 (release pipeline).
  **Layman:** Each download comes with a checksum file and a parts-list, so anyone can verify what's inside and that it wasn't tampered with.
  Kind: security.
  Source: claude-suggestion-2026-07-11.
  Resolved (2026-07-21): spec cold-eyes-converged over 8 loops (security/cross-ref lane clean 6–8; release-shell hardened), then reproduce-first TDD (10 tests, INV-1..7). Ships gen-checksums.sh (merge-aware manifest helper), two-phase signed SHA256SUMS with an anti-laundering fetch-verify gate + release-view fail-closed fetch, per-platform CycloneDX SBOM (freeze-before-PyInstaller, pip-audit -r --no-deps), and security-model INV-13. Gate green (1219 passed).

- 📋 [FIBR-0305] **Change the master password from Settings — nearly free once FIBR-0019 lands.**
  Surfaced by the FIBR-0019 review gate and verified as untracked:
  `roadmap_query query:"master password" status:all` returns seven
  bullets and none of them is this.

  Today there is no user-facing change-password flow at all. `Vault.rekey`
  exists but is called only by `BackupService.restore_backup`, which
  re-keys a restored COPY to a password chosen at restore time — never the
  live vault's own password.

  FIBR-0019 changes the economics completely. Under envelope encryption
  the master password only ever wraps a 32-byte data key, so changing it
  is: derive a KEK from the new password against a fresh salt, re-wrap the
  same DEK, rewrite the sidecar. The database is not touched. Before
  FIBR-0019 the same feature meant `PRAGMA rekey` over every page.

  Blocked by FIBR-0019 — the envelope has to exist first. Small once it
  does, and it shares the Settings surface and the current-password gate
  that FIBR-0019 section 4.7 already specifies for managing the recovery
  key.

  Deliberately NOT added to the FIBR-0304 v1.0 gate: it is a new
  user-visible capability, not a condition of freezing the format.
  **Layman:** Once the recovery-key work is in, changing your master password becomes a quick, safe operation instead of re-encrypting the whole vault — but nothing yet tracks actually adding the button.
  Kind: feature.
  Source: review-contract-2026-08-20 (FIBR-0019 gate, surfaced not fixed).

- 🚧 [FIBR-0307] **FP02 — fix-pass after FIBR-0019: thirteen findings from check-code and review-code.**
  Every one is a defect FIBR-0019 introduced; pre-existing findings are filed separately. Verified independently before filing.

  TWO ARE SEVERE.

  1. The check symbol is compared UNFOLDED, so a correctly transcribed code is refused. recovery_code.verify_check_symbol compares the 28th character raw while the 27-symbol payload is folded through I/L to 1 and O to 0. Check symbols 0 and 1 are both reachable, so a user who writes 1 as I is told their code has a typo, before any derivation -- and decode() proves it is the SAME code. Roughly 2 of 37 issued codes carry it. Worse, the same call gates INV-11's hint scan, so a hint holding the substituted form yields zero candidates and is accepted into plaintext window.ini: an INV-11 bypass by one character. Measured: verify_check_symbol False, decode equal True, candidates 0. Fix by comparing the DECODED check value, not the character.

  2. A broken vault/sidecar pairing is reported as a wrong password, with the destructive reset on screen. auth._open_with catches DatabaseError and returns False, so 'slot unwrapped but SQLCipher refused' is indistinguishable from a wrong credential. The _PAIRING_BROKEN message written for exactly this is unreachable dead code -- unlock.py keys it on VaultStateError, which this path never raises. Section 6 forbids it in as many words: do NOT offer the destructive reset from this state, the consequences differ absolutely. Found independently by two lanes.

  THE REST.

  3. resume() runs S6 bookkeeping BEFORE opening the vault, so an ENOSPC or a held file at _finish locks the user out of a fully migrated, provably openable vault -- and it escapes unhandled from a Qt slot. Section 6 names disk-full at S1-S6 by name.
  4. migrate_to_v2 never wipes the DEK it mints -- no try/finally at all. security-model INV-3 covers the DEK explicitly.
  5. _unlock_through_slot wipes kek in its finally but leaks dek whenever resume() raises -- including resume's routine terminal branch.
  6. resume branch 3 re-enters _convert, which swaps the live pair, with no rollback copy taken or verified. INV-13 is unconditional; section 13.3 step 3 says only 'restart from S1'.
  7. D8's rollback offer is never made. rollback_copy_paths has no caller anywhere and no UI path names the .pre-v2 pair, so the terminal branch is still terminal -- which section 13.3 calls 'the whole return on D8'. Found by two lanes.
  8. verify_rollback_copy reads sqlite_master only, so a copy truncated after the schema pages verifies. The replacement gets integrity_check plus row counts; the artefact the user falls back on gets a schema read. INV-13's own Breaks-when clause is about this.
  9. No length validation on slot fields. read_sidecar_v2 accepts an 8-byte or 200-byte wrapped_dek and a 2-byte nonce (measured); WRAPPED_DEK_LEN = 48 is dead. It fails closed, but as KeyUnwrapError, so a corrupt key record reads to the user as a wrong password -- finding 2's confusion by a second route.
  10. _on_change_recovery_key and _on_remove_recovery_key do not tear down the Settings dialog first, unlike every sibling handler. Two app-modals, an untracked dialog auto-lock cannot close, settings writes silently dropped on the next Save, and a stale 'No recovery code is set' on screen.
  11. restore_backup writes no cipher_compatibility, while the .fbk database it installs was written at an explicit level and the migration records it. A wheels bump that moves the default makes a restored vault unopenable.
  12. The section 4.7 helpers do not guard VaultLockedError. QInputDialog spins a nested loop; an idle auto-lock inside it makes verify_password raise out of the slot. Six other UI modules guard it.
  13. Two smaller ones: 'Recovery code saved' is shown even after keep_recovery_code has reported a failure, and a copied recovery code is never cleared from the clipboard though ClipboardAutoClear exists and is used for transaction descriptions.
  Open question, not one of the thirteen (2026-08-21, review-code lane 1).
  Both wrap paths materialise the DEK as an un-wipeable `bytes`:
  keywrap.wrap_dek does `bytes(dek)` for AESGCM.encrypt, and
  AESGCM.decrypt RETURNS immutable bytes which unwrap_dek then copies into
  the wipeable bytearray, leaving the original in the heap. One such copy
  per wrap and per unwrap, never zeroed, surviving lock and auto-lock.
  security-model INV-3 names the DEK explicitly.

  It is NOT obviously a defect: crypto.derive_key's own docstring calls
  the identical gap on `bytes(password)` "an accepted best-effort gap
  (D5)". Two things make it worth deciding rather than inheriting -- the
  accepted one is the PASSWORD and this is the database key, and an
  in-place API exists here (Cipher + GCM with update_into on a caller-
  owned buffer), so it is not API-forced the way hash_secret_raw's
  `secret=` argument is.

  DECIDE FIRST, then either fix it under FP02 or write the D5 reasoning
  into keywrap.py so the next reviewer does not re-raise it. Reading
  FIBR-0004 D5's actual wording is the missing input; the lane could not,
  it was outside its packet.
  Progress (2026-08-21): findings 1 and 2 -- both severe -- are fixed,
  pushed and gate-green (61ac651). Eleven remain.

  Finding 1 (d2e11ef): verify_check_symbol now compares the check VALUE
  through a fold-aware table, so a printed 1 written as I is accepted.
  Three new legs cover the fold, one locks that it does not widen to a
  wrong check value, five cover the non-data check symbols a naive fold
  would drop, and one reproduces the INV-11 hint bypass end to end -- it
  failed DID NOT RAISE before the fix.

  Finding 2 (6c73120): _open_with raises VaultStateError instead of
  returning False. No caller reaches it with an unproven credential, so
  the False was always a broken pairing. Measured before the fix: a
  correct password against a mispaired vault rendered "Could not unlock.
  Try again in 1s.", charging the throttle too. Both dialog routes already
  caught VaultStateError, so _PAIRING_BROKEN is now reachable. The blast
  radius a lane flagged as unmeasured is measured: _unlock_v1's
  post-migration fallback re-opens a database that key opened moments
  earlier, so a failure there is a real anomaly and the pairing message is
  correct. Full suite 1980 passed, mypy clean.

  New suite tests/features/recovery_key/test_failure_modes.py reaches the
  broken-pairing state without corrupting a byte -- it leaves the vault's
  own sidecar beside a different vault's database.

  The open question on un-wipeable DEK copies is decided (user, 2026-08-21):
  it sits inside FIBR-0004 D5's accepted best-effort gap, whose wording
  describes this exact shape -- an API returns immutable bytes, they are
  copied into a wipeable buffer and the original reference dropped. To be
  documented in keywrap.py under FP02 rather than fixed.
  Progress (2026-08-24): the migration failure path is closed --
  findings 3, 4, 5, 6 and 8 fixed, pushed, gate-green (ff25718).
  Seven of thirteen done; six remain.

  3: new _finish_quietly absorbs OSError only, so an ENOSPC in S6's
  bookkeeping leaves the vault resumable instead of raising out of a Qt
  slot. It closes the same hole on the FIRST-migration path too --
  _unlock_v1 recovers from a failed migrate_to_v2 by re-entering the
  ladder, which raised again.
  4: migrate_to_v2 wipes the DEK it mints, in a finally.
  5: _unlock_through_slot wipes the DEK on every route out that is not
  _open_with, including 13.3's routine terminal branch.
  6: new _ensure_rollback_copy applies INV-13's gate to branch 3, and
  REUSES S0's copy where it still verifies -- past S4 the live pair is
  no longer the pre-upgrade pair, so re-copying it would leave a
  "rollback" restoring the state the user is stuck in (D8).

  8's REPRO DOES NOT HOLD, and the fix's docstring records why so nobody
  re-derives it. A truncated copy is refused by SQLite at open, measured
  at every truncation from 2% to 50%. The real shape is a copy of the
  RIGHT LENGTH whose pages did not all survive: one flipped byte in page
  11, 41, 81 or 93 of a 93-page vault each gave an openable copy with a
  readable schema, and PRAGMA integrity_check caught all four. Row counts
  are deliberately not repeated at S0 -- S2 compares them against the live
  vault, which is what proves INV-8, and at S0 there is nothing to
  compare against.

  Eight new legs, each proved red before its fix and each mutation-checked
  alone: dropping the copy-reuse reddens only the "intact" leg, removing
  the gate reddens "absent" and "unreadable", reverting the verifier to a
  schema read reddens the damaged-copy leg. 1988 passed, 2 skipped.

  Next is 7 -- rollback_copy_paths still has no caller, so the copy this
  pass made trustworthy is still unreachable. Then 9-13, plus the decided
  D5 note for keywrap.py.
  Progress (2026-08-25): finding 7 is closed — D8's rollback offer is
  made (dd6a95e).

  resume's terminal branch raises RollbackAvailableError where a .pre-v2
  pair is beside the vault AND opens with the key just proven; the
  distinction is drawn there because that is the only frame holding both
  the key and the paths. It subclasses VaultStateError, so every existing
  handler still fails closed with § 6's broken-pairing message, and
  ui/unlock.py catches it first to offer the restore.

  restore_rollback_copy moves the pair back, database first. An
  interruption between the two files lands in § 13.3 branch 3, where
  KEK-master opens the v1 database and the ladder restarts; the other
  order would leave a v1 sidecar over a database no v1 key opens, which
  reads as a wrong password. Declining changes nothing — only S6 removes
  the copy, so the offer stands at the next unlock.

  Password route only, and not by omission: a migration-pending sidecar
  carries slots.master alone, so the recovery route never enters the
  ladder.

  Seven new legs, each proved red first and each mutation-checked alone.
  Full gate green.

  Remaining: 9-13, plus the decided D5 note for keywrap.py.
  Progress (2026-08-25): finding 9 is closed (44a965f).

  read_sidecar_v2 refuses a slot whose nonce or wrapped DEK is the wrong
  length, per slot, as KdfPolicyError. Measured before the fix: a 2-byte
  and a 64-byte nonce, and an 8-byte and a 200-byte wrapped DEK, all
  parsed — and unlock() returned False for each, so a damaged key record
  read as a wrong password and charged the § 6 throttle. That is finding
  2's confusion by a second route. § 4.4 already fixes both sizes, so the
  contract was written and only the enforcement was missing;
  WRAPPED_DEK_LEN is no longer dead.

  Not the oracle unwrap_dek refuses to be: a length is public in the
  plaintext sidecar and this gate runs before any password is derived.
  unwrap_dek keeps its one undifferentiated error, because the causes it
  can tell apart are secret-dependent. The route already existed —
  load_params runs first, and ui/unlock.py renders KdfPolicyError as the
  security-settings file being damaged.

  Refusing the whole record when a non-master slot is damaged is existing
  behaviour, not new strictness: validate_params already runs over every
  slot, so a damaged recovery salt blocks a master unlock today.

  Five new legs, each proved red first and each mutation-checked alone.
  Full gate green.

  Remaining: 10-13, plus the decided D5 note for keywrap.py.
  Progress (2026-08-25): findings 10, 11, 12 and 13 are closed, and with
  them the whole list. The decided D5 note is written into keywrap.py
  (80d354f). Every finding fixed, pushed and gate-green; steps 5-9 of the
  phase loop are what remains for FP02 itself.

  10 (00d259e): the two recovery handlers now tear Settings down first,
  alone among the Settings-launched handlers in not having. _open_dialog
  overwrites the single _dialog slot, so Settings was left shown and
  UNTRACKED — a second app-modal, an idle auto-lock unable to close it, a
  Save from it dropped by _on_settings_saved's isinstance guard, and a
  label built once from has_recovery_key() still offering to remove a code
  that was gone. Cancelling either flow now returns to the main window,
  which is what Export backup and Set password hint already do.

  11 (c7e7efe): restore_backup records cipher_compatibility. Its database
  comes from export_to, which writes at an EXPLICIT level, while a created
  vault takes the library default — so a sqlcipher3-wheels bump moving the
  default would leave every restored vault unopenable, _open_with having
  nothing to pass. The migration records it for exactly this reason. § 4.4
  enumerated two lifetimes for the field and a restored vault fell outside
  both, so the line is amended to say it is carried by every vault whose
  database was written at an explicit level; that records what was built,
  so no gate.

  12 and 13 (074a8ec): the § 4.7 helpers guard VaultLockedError —
  QInputDialog and QMessageBox both spin a nested loop, so the auto-lock
  fires inside them and the vault call after it raised out of a Qt slot.
  Both fail closed and silently, as settings.py does. "Recovery code
  saved" now hangs off a new saved signal emitted only after the write,
  not off accepted, which fires on the button — a failed re-wrap warned
  and claimed success in the same breath, over the only copy INV-5 allows.
  And a copied recovery code goes through ClipboardAutoClear, which
  already covered transaction descriptions.

  Fourteen new legs across the four, each proved red first and each
  mutation-checked alone. Two measured repros worth not re-deriving: 9's
  held exactly as filed, and 8's did not.
  Close ATTEMPTED and BLOCKED (2026-08-25). check-code was clean over
  2689463..HEAD; review-code's four lanes found nine defects FP02 itself
  introduced plus twelve pre-existing, folded into FP03 (FIBR-0310). FP02
  stays in progress and FIBR-0019 stays behind it. Record:
  docs/journal/FIBR-0307.md.

  The one to know without reading it: FP02's clipboard fix does not work.
  The auto-clear guard is parented to the dialog, so its timer dies when
  the dialog is torn down — which both callers do the moment the user
  answers. Measured, not argued. Its test passed only because it called
  clear_if_ours() directly instead of letting the timer fire, which is the
  second vacuous leg this pass produced after finding 8's stated repro did
  not hold.

  Nothing was added to docs/audit-allowlist.md; there were no confirmed
  false positives. FIBR-0309 and FIBR-0308 were independently re-found by
  this sweep and are not re-filed.
  **Layman:** The recovery-key feature works, but a careful review found thirteen problems in it — two of which could cost a user their data.
  Kind: review-fix.
  Source: close-phase-2026-08-21 (check-code + 3 review-code lanes over f704605..HEAD).
  Lanes: crypto, security, ux.

- 📋 [FIBR-0308] **INV-11's hint scan misses the 27-symbol payload, which is the whole credential.**
  A SPEC question, not an implementation defect -- ui/_password_hint._code_candidates implements section 5 INV-11 faithfully. INV-11 says to scan for a 28-symbol Crockford candidate and verify its check symbol. But the check symbol is a pure function of the 27-symbol payload (CHECK_ALPHABET[_payload_int(payload) % 37]), so the payload ALONE is the entire credential, and Argon2id is fed exactly those 27 symbols decoded. A hint holding the payload without its check symbol -- or with a mistyped one -- therefore passes the guard and is written to plaintext window.ini.

  FP02 finding 1 is the narrow instance of this and is fixed there. This is the general case and needs INV-11's own wording changed: scan 27-symbol windows too, COMPUTING the check symbol rather than reading it, then trial-unwrap. Filed rather than fixed because amending an invariant is a spec change, and section 5 is what a conformer builds from.
  **Layman:** The check that stops you putting your recovery code in your password hint only looks for the full code, not the part of it that actually matters.
  Kind: security.
  Source: close-phase-2026-08-21 (review-code lane 3, UI edges).
  Lanes: security.

- 🚧 [FIBR-0310] **FP03 — fix-pass after FP02: nine regressions from the fix-pass itself, plus twelve pre-existing.**
  check-code was clean on this scope. Every item below is a review-code
  finding. NOT re-filed because they are already filed: FIBR-0309 covers the
  .tmp O_EXCL gap, the missing directory fsync after os.replace (including
  S4/S5) and validate_params' unbounded time_cost / parallelism / memory_kib;
  FIBR-0308 covers INV-11's wording, of which lane 4's "a separator other
  than a hyphen defeats the scan" is a second instance.

  REGRESSIONS FROM FP02 — these are defects the fix-pass introduced.

  R1. The clipboard auto-clear never fires. recovery_key.py __init__ calls
  setParent(self) on the INJECTED guard, so its timer is a child of the
  dialog, and both callers deleteLater() the dialog as soon as the user
  answers. MEASURED 2026-08-25: guard parented to the dialog, timer active
  after Copy, both destroyed together. So finding 13b is inert and a
  vault-opening credential stays on the clipboard. The test passed only
  because it called clear_if_ours() directly instead of letting the timer
  fire -- a vacuous leg, and the second one this pass has produced.
  R2. The Settings teardown has no return path. Every sibling flow that
  tears Settings down replaces it; _on_change_recovery_key and
  _on_remove_recovery_key can tear it down and open nothing, so Cancel at
  the password gate makes Settings vanish. Re-open it when the gate
  resolves, guarded on _dialog being empty and the vault still unlocked.
  R3. Four new user-facing strings can never be translated. tr() takes a
  module constant, and coding.md says lupdate extracts only literals. Three
  pre-existing sites and recovery_key's _tr wrapper have the same defect.
  R4. _ensure_rollback_copy's fallback writes the migration-pending v2
  sidecar as the .pre-v2 sidecar, which its own docstring says would leave a
  rollback restoring the stalled state. Falsifies restore_pre_upgrade_copy's
  "the pair on disk is v1 again": the next unlock re-enters branch 3 and
  restarts the migration the user asked to undo. Section 13.1 makes the fix
  available -- rebuild a v1-shaped sidecar from slots.master's own params.
  R5. _validate_slot_lengths widens a pre-existing lockout: one damaged
  OPTIONAL slot now fails the whole sidecar by two more legs, so a corrupt
  recovery slot bars the intact master route. Hard-fail on master only.
  Do not prune -- auth round-trips the loaded object back to disk.
  R6. The D5 docstring in keywrap is incomplete. It omits the KEK copy INV-3
  names explicitly, and bytes(dek) is a no-op because every caller already
  passes bytes(), so the copy it describes lives in the caller's frame.
  R7. rollback_copy_paths' docstring says the UI's offer needs to name the
  path. The offer shipped and names no path.
  R8. _finish_quietly's "a failure leaves the sidecar as it was, so the
  state stays resumable" is false when the OSError lands AFTER
  write_sidecar_v2: migration_pending is cleared, nothing re-enters the
  ladder, and the .pre-v2 pair persists forever -- an encrypted copy that
  still opens under the OLD master password, surviving a later change.
  R9. restore_rollback_copy moves the database then its -wal; a crash
  between them drops the WAL tail. Currently masked only because
  verify_rollback_copy's open checkpoints the copy first, so the guarantee
  rests on a side effect rather than the ordering.

  PRE-EXISTING.

  P1. UNVERIFIED and the highest-severity item here: _fsync opens O_RDONLY
  and fsyncs, which may fail on Windows, aborting every migration silently
  via _unlock_v1's broad except -- so no Windows user would ever get a
  recovery key. The lane cited backup.py's note as corroboration and that
  note is about a DIRECTORY fsync, a different case, so the evidence does
  not hold. The Windows box has no Python. MEASURE IT FIRST.
  P2. UnicodeDecodeError, RecursionError and MemoryError escape
  load_and_validate_params' documented "everything normalises to
  KdfPolicyError", and the path is reachable from an imported .fbk, whose
  BackupError tuple omits them too.
  P3. write_rollback_copy copies at the process umask and chmods after, so
  both files are world-readable during the copy; and unlink-then-copyfile
  with no O_NOFOLLOW is a symlink trap. vault.py mounts both defences twice.
  P4. The "Save to a file" affordance writes the recovery code 0644. Every
  other secret-bearing write in the app is owner-only.
  P5. backup._install moves neither the incumbent vault's -wal nor its -shm,
  so a restore installs over a foreign-keyed WAL and the .old copy loses its
  journal. Two other modules solve this and say why. Move, do not unlink.
  P6. Resume branches 1 and 2 delete the .pre-v2 pair having proved only
  that the database OPENS -- the weaker check verify_rollback_copy's own
  measured docstring says is insufficient.
  P7. _opens claims to be "a question, not a use" while Vault.open commits
  run_migrations, so branch 3 writes to the live v1 database before any
  rollback copy is secured.
  P8. keywrap's kek: bytes annotation forces an un-wipeable KEK copy at
  seven call sites, several beside a finally that wipes the bytearray and
  misses the copy. Not the D5 gap -- AESGCM takes a bytearray, MEASURED on
  the pinned cryptography 50.0.0. INV-3 names every KEK.
  P9. security-model T13 is stale: it says ClipboardAutoClear is built in
  exactly two places for the transactions list. There are four in three
  files and the recovery code is copyable by design. Spec change.
  P10. unlock_failed is a zombie: ten emit sites, no non-test consumer,
  while unlock.py and FIBR-0051 both say the shell connects it.
  P11. backup's on_key gained a "dek" role that its own comment and
  FIBR-0014 Deliverable 1 do not list. Spec change; the code is right.
  P12. Smaller: the hint trial-unwrap loop is uncapped and un-deduplicated,
  so a 100-char hint can force dozens of 46 MiB Argon2 derivations on the UI
  thread; keep_recovery_code is the one section 4.7 member with no
  VaultLockedError arm; verify_backup does not catch the MemoryError
  restore_backup does, off the same helper; _password_hint fails open on an
  unreadable sidecar with no log line; check_symbol validates nothing;
  set_hint.py's docstring names the pre-INV-11 call chain; _open_dialog
  could enforce the one-modal invariant itself instead of trusting eleven
  callers to remember, which is exactly what FP02 finding 10 was.
  Work this from a FRESH context, and dispatch the review from one too.

  The reason is measured rather than cautious. The session that wrote FP02
  also reviewed it, twice — it ran the lanes that produced this list, and
  nine of the findings are its own regressions. A reviewer sharing the
  author's mental model is exactly what review-code's own rule about
  same-session authorship warns of, and this pass is the evidence. Two of
  the nine are tests that passed while the fix they covered was inert.

  So: read the findings from this bullet rather than from a session that
  remembers writing them, and when FP03 itself is reviewed, use a fresh
  session or /code-review ultra (user-triggered — an agent cannot launch
  it). If the same context both fixes and reviews a third time, expect the
  same class of miss.

  Order matters for two items. P1 is UNVERIFIED — measure the Windows
  os.fsync behaviour before building anything on it; the Windows box at
  `ssh wintest` has no Python installed, so that is not the route.
  R1 is the opposite: measured and confirmed, so it needs no repro, only
  a fix and a test that lets the timer fire.
  Progress (2026-08-25): R1, R2 and R3 are fixed, each with a test proved
  to discriminate and each pushed on a green gate.

  R1 -- the injected clipboard guard keeps its caller's owner;
  build_recovery_offer parents it to the window. Its test was rewritten to
  run the real factory, the real teardown and a real wait, because calling
  clear_if_ours() by hand is the guard's own implementation and passed
  against inert code.

  R2 -- _reopen_settings_if_idle(), guarded on an empty slot and an
  unlocked shell. Its third leg caught a defect in the fix's first draft:
  locking the service alone leaves _unlocked True, which is why the leg now
  uses _on_idle_timeout(), the production entry.

  R3 -- widened by measurement. pyside6-lupdate drops a constant CONTEXT
  and a wrapper call as well as a constant message, so the count was 16
  strings across four modules, not four. Fixed in unlock.py, recovery_key,
  _widgets and categories; verified against the real tree before and after.
  tests/features/i18n/ is the new guard. services/pdf_export.py is excluded
  BY NAME and filed as FIBR-0311 -- 30 sites, a third in f-strings, so
  conforming it is a renderer refactor rather than this plumbing fix. Also
  filed FIBR-0312 for the stale "expected to FAIL" status in
  tests/features/recovery_key/spec.md.

  Next: R4.
  Progress (2026-08-25): R4 to R9 done, so ALL NINE regressions are fixed
  and pushed, each on a green gate.

  R4 -- _ensure_rollback_copy's retake now REBUILDS a v1 sidecar from
  slots.master's params (write_rollback_copy grew a sidecar_payload
  argument) instead of byte-copying the live v2 one. Second half, and it is
  what makes this repair rather than only prevent: verify_rollback_copy now
  rejects a copy whose sidecar is v2, so a copy left by an earlier run is
  not kept and offered. The existing test's assertion was guarded by
  `if copy_state == "intact"` -- the one leg where the retake never fires --
  and is now unconditional, with a fourth leg, stale_v2, pinning the gate.

  R5 -- read_sidecar_v2 hard-fails on master only; other slots are logged
  and KEPT, never pruned, because AuthService round-trips the object back
  to disk. Finding 9's distinct error moves to the route that uses the
  slot (crypto.validate_slot, public for that, called by recovery_params
  and _unlock_through_slot). That put a damaged slot and an absent one
  through one UI handler saying "This vault has no recovery code set", so
  they are now separate sentences and the damaged one points at the master
  password -- which by this fix still works.

  R6, R7 -- docstring accuracy. keywrap's D5 note omitted the KEK copy and
  claimed a bytes(dek) that is a measured no-op; rollback_copy_paths
  claimed a UI caller that does not exist.

  R8 -- an ORDERING fix, not a docstring one. S6 cleared migration_pending
  before unlinking, so an absorbed OSError stranded the .pre-v2 pair
  forever: an encrypted copy openable with the master password of the day
  it was taken. The removal goes first now.

  R9 -- verify_rollback_copy asks for the checkpoint (PRAGMA
  wal_checkpoint(TRUNCATE), after integrity_check so a damaged copy is
  never written to) instead of getting it from the probe's close. Measured:
  that truncates the WAL to 0 bytes with the probe still open.

  Also filed off this work: FIBR-0311 (pdf_export's 30 untranslatable
  strings) and FIBR-0312 (the stale "expected to FAIL" status in
  tests/features/recovery_key/spec.md).

  Next: P1, which is UNVERIFIED. Measuring the broad-except half of the
  claim first, since that half is answerable on Linux and if it is false
  the severity collapses regardless of the Windows answer.
  P1 is CONFIRMED and fixed (2026-08-25). Measured on windows-latest /
  CPython 3.12.10, via a probe step added to windows-build.yml -- the only
  Windows job in the repo, and `ssh wintest` carries only the Microsoft
  Store stub, not a real interpreter:

    FSYNC_PROBE O_RDONLY: FAILED OSError(9, 'Bad file descriptor')
    FSYNC_PROBE O_RDWR:   OK

  So _fsync's O_RDONLY raised on Windows, S0 aborted, _unlock_v1's broad
  except swallowed it and opened the v1 vault. No Windows vault would ever
  have reached the v2 envelope and no Windows user would ever have been
  offered a recovery key -- silently, on every unlock, with the app
  working. _fsync now opens O_RDWR and the probe step is a GATE on that
  idiom. The lane's cited corroboration was wrong as flagged, and
  backup.py's _fsync_directory correctly KEEPS O_RDONLY: a directory
  cannot be opened for writing, which is why it degrades instead of
  raising.

  P3 fixed, and it was worse than filed. The database and sidecar copies
  were world-readable for the LENGTH of the copy (copyfile at the umask,
  chmod after), which is what P3 said. The WAL sibling had no chmod at
  all, so that copy -- holding the same rows -- was world-readable
  permanently. Measured by running the new leg against the pre-P3 code.
  _copy_owner_only pre-creates 0o600 with O_EXCL | O_NOFOLLOW, which also
  closes the unlink-then-copy symlink window.

  P4 fixed: "Save to a file" wrote the recovery code at the umask. Now
  0o600, with a chmod for the overwrite case a mode argument cannot reach.

  Next: P2, then P5, P6, P7, P10, P12. P8, P9 and P11 are spec work --
  P9 (security-model T13) and P11 (FIBR-0014's on_key roles) go to
  review-contract.
  Progress (2026-08-25): P2, P5, P6 and P7 done and pushed. Seven of the
  twelve pre-existing findings are now closed (P1 to P7), on top of all
  nine regressions. Full gate green at each push; the last was 2036 passed
  / 2 skipped.

  P2 -- crypto._MALFORMED_SIDECAR is the shared tuple both readers use.
  Measured: non-UTF-8 bytes raise UnicodeDecodeError out of read_text
  BEFORE json sees them (so being a ValueError subclass does not help) and
  200k nested brackets raise RecursionError, which is not a ValueError at
  all. backup.py's two tuples gained what they lacked -- the manifest half
  already caught UnicodeDecodeError while the params half, the same file
  through a different reader, did not.

  P5 -- backup._install now moves the incumbent's -wal / -shm aside with
  its database, stamp BEFORE suffix so the .old set is a coherent SQLite
  triple (vault.db.<stamp>.old-wal is the name SQLite looks for). Moved,
  never unlinked.

  P6 -- _finish_if_readable gates S6's deletion of the .pre-v2 pair on
  _reads_end_to_end (open + PRAGMA integrity_check) rather than on _opens.
  A vault that opens but does not read keeps BOTH the copy and the pending
  flag. The full read is paid only while migration_pending is set.

  P7 -- Vault.open takes migrate=False, and _opens passes it. The probe was
  running run_migrations, which COMMITS, so branch 3 wrote schema changes
  to the live v1 database before any rollback copy existed.

  REMAINING: P8, P10, P12 are code. P9 and P11 are spec changes and go to
  review-contract, not to a code fix. Then FP03's own close, steps 5 to 9 --
  and the fresh-context rule above applies to that review.
  Progress (2026-08-25): P8 to P12 done and pushed, so ALL 21 findings
  are closed -- nine regressions and twelve pre-existing. Full gate green
  at each push; the last was 2043 passed / 2 skipped.

  P8 -- keywrap's kek widens to `bytes | bytearray` and the eight
  production sites pass their buffer through. `bytes(kek)` made an
  immutable copy in the CALLER's frame, out of reach of the `finally` that
  wipes the bytearray beside several of them: an INV-3 breach at eight
  sites. Measured on the pinned cryptography 50.0.0 -- an AESGCM built
  from a bytearray still decrypts after that bytearray is zeroed, so the
  residual copy is OpenSSL's and unreachable from Python. `dek` stays
  `bytes`: FIBR-0004 D5's accepted gap, and the new guard must not fire on
  it. Two of the guard's three legs discriminate; a runtime-only test
  cannot, since Python does not enforce an annotation.

  P10 -- the finding was half wrong. Nothing connects unlock_failed, but
  of the two documents said to claim otherwise only FIBR-0051 does;
  unlock.py's docstring is accurate as written. The signal is KEPT: eleven
  emit sites, eleven distinct failure branches, no double-emit, and a
  failed unlock is the dialog's own business, so a shell slot would have
  no work. Deleting it would only push six test sites onto reading label
  text.

  P12 -- six fixed, one DECLINED on measurement. The trial-unwrap
  de-duplicates; the cap does not exist, because a derivation is 26 ms,
  20 000 random 100-char hints averaged 2.0 candidates and peaked at 10,
  and hill-climbing reached 24 -- a ~0.6 s worst case, and no cap value
  both bounds that and never refuses an honest hint. My first draft capped
  at 8 and its test was VACUOUS: validate_hint refused the 300-char probe
  on length before the cap was reached, so mutating the cap out left the
  leg green. That is the fourth vacuous leg this pass has produced.
  Also: keep_recovery_code gained the VaultLockedError arm its three
  siblings have (its broad arm warned "the vault is locked" on a dying
  widget); verify_backup answers a MemoryError the way restore_backup
  does; the unreadable-sidecar fail-open logs; check_symbol refuses a
  payload that is not 27 symbols; set_hint's docstring names the live
  chain; _open_dialog enforces the one-modal slot itself.

  P9 and P11 did NOT go to review-contract, against this bullet's earlier
  plan. Both are amendments recording what was built -- rule 14 says that
  does not re-arm the gate, and the only one of the four questions that
  could bite is Q1, which IS the finding. T13 now names the two copyable
  surfaces and states no count, which is how it went stale.

  NEXT: FP03's own close, steps 5 to 9. The fresh-context rule at the top
  of this bullet applies to that review -- this session did the fixing.
  **Layman:** The recovery-key fixes were reviewed again, and the review found nine places where those very fixes fell short — plus a dozen older problems around them.
  Kind: review-fix.
  Source: close-phase-2026-08-25 (check-code + 4 review-code lanes over 2689463..HEAD).

- 🚧 [FIBR-0313] **FP04 — fix-pass after FP03: one critical migration dead-end, four high, and a long tail.**
  check-code was clean on this scope: semgrep clean on both rulesets, bandit
  clean in src/ below the gate's threshold, no typo on an FP03-authored line.
  Its one finding (pyright reportOptionalSubscript,
  tests/features/backup/test_backup.py:835) does not survive -- the line is
  pre-existing (FIBR-0033, 42bca98) and the assert above it fails first on
  None, so it is unreachable with None. Verified by running the equivalent.

  NOT re-filed, already filed: FIBR-0309 covers write_sidecar_json's missing
  O_EXCL and its stale .tmp (its own fix text names the unlink) and the
  missing directory fsync in write_sidecar_json and at S4/S5. It does NOT
  reach backup.py's restore install or restore_rollback_copy -- those are M2
  and M3 here.

  THE PATTERN, found independently by three lanes: an FP03 fix that reached
  some call sites and not all. R5's validate_slot rule skips its third
  consumer; P7's migrate=False reached two probes of three; P5's .old-wal is
  carried aside and never restored. FP03 was itself cleaning up nine
  regressions of that class and produced three more. Second pattern, four
  instances across three lanes: a docstring certifying behaviour the code does
  not have -- the cost of writing prose beside the fix with nothing checking
  it against the code.

  C1. vault_migration.py:644-649 + :713-716 -- _finish_if_readable returns on
      the not-readable path, so RollbackAvailableError is never raised. Branch
      1 matches on every later unlock, so the user is unlocked forever into a
      vault with unreachable rows while a verified .pre-v2 pair sits beside it
      unmentioned. The docstring says "the rollback is still offered".
      Verified: that error is raised only from resume's terminal branch, which
      branch 1 makes unreachable. Fix: pass kek_master down and raise when
      rollback_copy_is_usable; correct the docstring.
  H1. vault_migration.py:719-724 -- branch 2 replaces the live v1 database on
      _opens alone, with neither S2's integrity_check + row compare nor
      _ensure_rollback_copy. _opens is this module's own weak check that "a
      file damaged in the middle" passes. Main road into C1.
  H2. vault_migration.py:316 + :541 -- verify_rollback_copy omits
      migrate=False, so run_migrations commits schema writes into the artefact
      it certifies; Vault.open's docstring (P7) states the rule it breaks.
      SchemaVersionError is not in rollback_copy_is_usable's except tuple (MRO
      is SchemaVersionError -> FinbreakError), so a function typed -> bool
      propagates on the last-resort path. Both verified.
  H3. auth.py:652-665 -- reset_vault unlinks four paths and leaves the
      vault.db.<stamp>.old triple with its sidecar (written on every restore,
      deleted by nothing) and the .pre-v2 pair. security-model.md INV-12 says
      "no file of a deleted vault remains" and rests its accepted residual on
      fragments being "useless without the (now-gone) key" -- an .old pair
      opens under the password the user had before the restore. Either the
      code or INV-12 moves.
  H4. backup.py:485-491 vs main_window.py:1353-1354 -- _install carries the
      incumbent's -wal aside (P5); _reconcile_interrupted_restore restores two
      files and stops, so the recovery path drops committed frames. Filed
      MEDIUM by the lane, raised here on the threat model: silent loss of the
      user's most recent transactions.

  M1. backup.py:62 -- MAX_BACKUP_DB_BYTES is enforced on restore only, so a
      vault over 512 MiB exports, reports success, and can never be restored
      on any machine. Deliberately not raised above MEDIUM: total consequence,
      low reachability. Fix at export time, where the user still has the
      vault.
  M2. backup.py:498-499 -- the restore install is neither fsynced nor
      directory-fsynced, while export_backup and vault_migration._fsync both
      are.
  M3. vault_migration restore_rollback_copy -- its two os.replace calls have
      the same missing-fsync exposure, on the user's last-resort path.
  M4. vault_migration.py:170,202,316,408,419 -- Vault.open never wipes the
      bytearray handed to it, so each defensive copy is an orphaned 32-byte
      live KEK/DEK; one resume through branch 3 mints up to eight.
  M5. unlock.py:503-505 -- _show_failure is shared, so a recovery-code user is
      told to check their password, on a screen offering a destructive reset.
  M6. recovery_key.py:87-92 -- the clipboard-is-None branch parents the guard
      to the dialog, which is R1 verbatim, endorsed by its own docstring. No
      live caller today, but it is the constructor default and a test that
      builds the dialog plainly exercises the broken shape as coverage.
  M7. recovery_key.py:255 -- NewMasterPasswordDialog._on_submit has no
      VaultLockedError arm, unlike its three siblings (:282, :379, :441, all
      P12). The vault is open so the idle timer is live; the broad arm renders
      an internal exception onto a dialog already being destroyed.
  M8. crypto.py:404-415 vs ui/_password_hint.py:137 -- validate_slot's stated
      contract has a third consumer that skips it; a damaged recovery slot
      raises argon2 HashingError, which is not caught by the surrounding
      except (KdfPolicyError, OSError) -- unhandled out of a Qt slot.
  M9. crypto.py:283-301 -- VaultSidecar.to_dict() drops unknown v2 fields, and
      the writers are read-modify-write, so an older build deletes what a
      newer one wrote. 4.1 anticipates FIBR-0020 arriving as a slot.
  M10. FIBR-0019 D5 (spec line 139) vs main_window.py:671-683 -- D5 says the
      UI offers regeneration after a recovery unlock; no such prompt exists.
      Decide which side moves.

  L1.  crypto.py:82 -- derive_key states no ownership of its buffer; auth
       wipes it, ui/_password_hint.py:141 does not.
  L2.  auth.py:529 -- sidecar_version can raise inside _unlock_v1's handler,
       leaving the derived key un-wiped; every sibling path wipes.
  L3.  vault_migration.py:262-268 -- the -wal rollback copy is not fsynced
       while the database half is.
  L4.  recovery_key.py:169-171 -- chmod by path after the fd is open
       (CWE-367); os.fchmod meets the comment's stated purpose.
  L5.  backup.py:187,608 -- <dest>.tmp is unlinked unconditionally without
       checking this process created it.
  L6.  ui/_password_hint.py:149 -- a user-facing string in ui/ outside both
       coding.md 5.2 and allowlist-004, which is scoped to ui/_amount.py.
  L7.  ui/_widgets.py:25 -- _LABEL_CONTEXT is dead, and three docstrings plus
       FIBR-0154 still describe the form that would re-introduce R3.
  L8.  unlock.py:126-127 -- P10's comment says unlock_failed fires on every
       failure branch; the check-symbol typo branch returns without it.
  L9.  recovery_key.py:334-342 -- each Settings Add/Replace leaves a QObject +
       QTimer for the session.
  L10. recovery_key.py:233-242 -- if set_master_password can never succeed the
       modal blocks File > Quit, so _save_geometry never runs.
  L11. backup.py:294-299 -- the comment asserts an exception route
       crypto._MALFORMED_SIDECAR now normalises away.
  L12. vault_migration.py:430-432 -- the row-count mismatch reaches
       log.exception, putting per-table row counts in the plaintext log.
  L13. main_window.py:1341-1342 -- FIBR-0014 D4's first-run reconciliation
       branch does not exist; the app hard-errors on the mixed state.
  L14. pyproject [tool.mypy] has no check-untyped-defs, so mypy skips the
       bodies of unannotated tests -- most of this suite. Gate gap, found by
       pyright seeing what mypy structurally cannot.
  L15. 13.3's debris enumeration omits the stray vault.kdf.json.migrating an
       S2/S3 abort leaves. Spec side, review-contract's.
  L16. crypto.py:430-431 -- the sidecar is read and parsed twice per
       read_sidecar_v2, three times via auth.read_sidecar. INFO, fails closed.

  Coverage: 4 lanes over the 14 source files FP03 changed, ~7000 LoC, no
  merges. NOT reviewed -- the rest of the tree (importers, reporting,
  categorisation, pdf_export, update_fetch, packaging), main_window.py outside
  five named regions, and the test suite (review-tests was not run, and two of
  FP03's regressions were tests passing against inert code). Lane 3's packet
  omitted FIBR-0014, backup.py's actual contract; the lane read it anyway and
  said so.
  Open questions (2026-08-25): five the four lanes raised that are NOT folded
  into the findings above, recorded so they do not die with the review
  session. Two are finding-shaped and were left unfiled by their lane for a
  stated reason; three need a decision rather than a fix.

  Q1. crypto.py read_sidecar_v2:459 reads migration_pending as
      bool(data.get(...)), so ANY truthy JSON value sets it -- including the
      string "false" -- and it drives vault_migration.resume via
      auth.py:468. Lane 1 did not file it because an attacker with sidecar
      write access can write literal true anyway, and whether a spurious
      resume on an already-migrated vault is destructive was outside its
      lane. C1 and H1 above are what make that worth answering now.
  Q2. ui/categories.py:174 -- `name = self._name.text().strip() or
      item.text(0)` on an _on_update reached with a Type root selected would
      pass the root's TRANSLATED label as a category name. The button is
      disabled for roots (:248) and _on_add guards the equivalent case
      explicitly (:153), so the asymmetry may be deliberate. Lane 4 could not
      settle it without update_category's contract, outside its slice.
  Q3. keywrap.slot_aad binds the slot name plus memory_kib, time_cost,
      parallelism and key_len, and omits salt_len. security-model INV-3d says
      "the Argon2id cost parameters are bound"; the salt is bound through the
      derivation itself, and no document enumerates the AAD fields. Lane 1
      constructed no attack and could not tell whether the omission is
      deliberate. Decide, and write the answer down either way.
  Q4. Are the vault.db.<stamp>.old pairs meant to be permanent? Nothing
      removes them, so repeated restores accumulate full encrypted vault
      copies indefinitely. FIBR-0014 INV-5 requires them to exist; no
      document says for how long. H3 above fixes the reset half only -- the
      retention policy is a separate decision.
  Q5. backup.restore_backup asserts nothing about the vault being locked,
      though FIBR-0014 INV-8 says restore is pre-login only and _install
      depends on it (os.replace over an open vault.db fails on Windows). The
      single caller is on the pre-login route, so the invariant is
      caller-held rather than local. A presence check would make it local.
  Progress (2026-08-27): C1 and H1 fixed and pushed; gate green at
  2048 passed / 2 skipped. C1 -- _finish_if_readable takes kek_master and
  raises RollbackAvailableError on the not-readable path where a verified
  .pre-v2 pair is beside the vault; with no usable copy it opens as before,
  that state being INV-7 already broken with no route back. H1 -- branch 2
  gates the swap on S2's two checks asked again (integrity, and the row
  compare against the still-v1 live vault) and on _ensure_rollback_copy per
  INV-13, and discards an unsound replacement by falling through to branch 3
  rather than raising. Commits 00a2e18, 604a6f5.

  mutation_probe is why H1 has three legs rather than one: on the first draft
  "row compare dropped" and "INV-13 gate dropped" both SURVIVED -- integrity
  alone catches a damaged page, so nothing pinned the short-export case the
  row compare exists for, and nothing pinned the gate at all. Both killed now.

  FIBR-0019 § 13.3 branches 1 and 2 amended to match, recording what was
  built; tests/features/recovery_key/spec.md gained INV-14 and INV-15.
  Progress (2026-08-27, cont.): H2 fixed and pushed (f492e9f); gate
  green at 2050 passed / 2 skipped. verify_rollback_copy now passes
  migrate=False, so it stops committing schema writes into the .pre-v2 copy it
  certifies -- measured, sha256 changed and schema_version went 1 to 13 across
  a call whose job is to read. That one argument closes H2's second half too:
  run_migrations is the ONLY raiser of SchemaVersionError, and Vault.open
  returns before it when migrations are skipped, so nothing propagates out of
  rollback_copy_is_usable any more.

  DECLINED on measurement, and recorded rather than dropped: adding
  SchemaVersionError to that except tuple, which is the remedy H2 implies. It
  would return False for a copy that READS -- integrity_check passes, every row
  is there -- when verify_rollback_copy exists to refuse a copy that CANNOT be
  read; a recorded schema number is not damage. Refusing it leaves the user the
  bare "vault and key record disagree" with their intact vault beside them and
  nothing saying so, where offering it restores the pair and the next unlock
  says "update finbreak". tests/features/recovery_key/spec.md INV-17 now states
  that verdict as a decision so the next reader does not re-derive it as a bug.
  Reopen only with a case where a too-new copy is genuinely unrestorable.

  C1, H1 and H2 are closed. M1-M10 and L1-L16 remain, plus Q1-Q5 and M10's
  decision. Spec INV-14 to INV-17 added across the three.
  Windows verification routing (2026-08-27, user raised the wintest
  box mid-session): worth a run on M2, M3, H4 and Q5 and on nothing else in
  this bullet. All four turn on os.replace over an open vault.db, which is the
  operation that behaves differently on Windows -- Q5 says so outright, since
  FIBR-0014 INV-8 makes restore pre-login only BECAUSE of it. C1, H1 and H2
  were platform-neutral (SQLCipher page HMACs, a probe flag, file-level moves
  already covered by the Linux gate), so no Windows run was spent on them and
  none is owed retrospectively.
  Progress (2026-08-27, cont.): M1 fixed and pushed (641dacb); gate
  green at 2053 passed / 2 skipped. export_backup measures the intermediate
  vault.db and refuses it over MAX_BACKUP_DB_BYTES on the same `>` edge
  _read_capped uses -- vault.db is ZIP_STORED, so that file's size IS the
  file_size restore will measure, and the two ends cannot disagree.

  M1 had a second half nothing had named, found by measuring rather than
  assumed: BackupError is a sibling FinbreakError, and the export handler
  caught (VaultLockedError, OSError, ValueError, DatabaseError), so the new
  refusal would have escaped a Qt slot uncaught -- the M7/M8 class. It has its
  own arm now, naming the condition, deliberately NOT the generic "choose
  another location" copy, which for this failure sends the user round a loop
  that cannot succeed.

  mutation_probe on every part rather than the feature: `>` to `>=` killed,
  guard disabled killed, UI arm removed killed, message swapped for the
  generic copy killed. The refusal string itself SURVIVED, which is correct --
  nothing asserts it and nothing should.

  Where else the rule binds, measured rather than assumed: the cap has one
  read-side enforcement point (_read_capped, shared by restore and verify) and
  now one write-side point, so the surface is closed. MAX_MANIFEST_BYTES
  carries the same read-only asymmetry but is unreachable -- the manifest is
  four scalars and params.json a fixed sidecar dict, both far under 64 KiB.
  Named, not fixed.

  FIBR-0014 INV-12 amended to record that the cap binds export too;
  tests/features/backup/spec.md gained INV-14.
  Progress (2026-08-27, cont.): M2 and M3 fixed and pushed (0a17d2c);
  gate green at 2056 passed / 2 skipped. One rule at two sites. M2 -- _install
  fsynced neither the sources nor the directories; it now fsyncs the database
  and each distinct parent, and the *.old move-aside pair is directory-fsynced
  BEFORE the post_move_aside seam rather than at the end, because INV-5's
  premise is that the old pair is already safely aside AT that seam and a fsync
  landing after it leaves that false for exactly the crash the seam models.
  M3 -- restore_rollback_copy's renames had no directory fsync; its sources were
  already durable, since write_rollback_copy fsyncs each copy when S0 takes it,
  so only that half was missing.

  Vault takes vault_path and sidecar_path independently, so both fixes fsync
  both parents, deduped. A fix assuming one shared directory leaves the other
  undone; the M2 test pins that by installing into two different directories.

  mutation_probe found a redundancy the suite could not see: _fsync_file on the
  sidecar SURVIVED, because write_sidecar_json already flushes before its own
  os.replace. Dropped rather than kept as decoration -- INV-15 still pins the
  sidecar's durability as an OUTCOME, so if that writer ever stops flushing the
  test reddens. Five probes killed. One SURVIVOR reported rather than chased:
  collapsing M3's dedupe to the vault directory alone, which that test's fixture
  cannot see because it puts both files in one directory. The code is right --
  the renames land in both parents -- and pinning it needs fixture surgery for a
  branch no real call site exercises.

  Where else the rule binds, measured: S4/S5 and write_sidecar_json are
  FIBR-0309's, as this bullet already records. A THIRD site was found and filed
  as FIBR-0314 -- main_window._reconcile_interrupted_restore unlinks the live
  pair, then os.replace()s the *.old pair back with no fsync of either kind, and
  the unlink comes FIRST, so a crash there can leave no vault at all. Not folded
  in: UI layer with no fsync helper, and H4 rewrites that same function.

  tests/features/backup/spec.md gained INV-15 and
  tests/features/recovery_key/spec.md gained INV-18. A stale docstring citation
  was corrected with them: vault_migration._fsync named backup.py's helper
  _fsync_directory, which is _fsync_dir.
  Known limitation of the M2/M3 tests, recorded so it is not rediscovered or
  "fixed" wrongly: INV-15's and INV-18's directory-fsync assertions resolve the
  fsync'd fd via /proc/self/fd, which is Linux-only. macOS is a packaging target
  and has no /proc, so those three tests would error there rather than fail
  honestly.

  Left as-is deliberately. CI is ubuntu-24.04 and windows-build.yml runs no
  pytest, so nothing exercises it today; and the behaviour under test is itself
  POSIX-only -- _fsync_dir degrades on Windows by design, so a portable test
  could not pass there anyway. Swapping /proc for os.fstat (dev, ino) identity
  WOULD be portable and is what the file-half assertions already do, but it
  makes the failure messages markedly worse, and rewriting a working test's
  recorder does not trace to M2 or M3. If the suite is ever run on macOS, that
  swap is the fix -- not a skipif, which would read as coverage.
  Progress (2026-08-27, cont.): M4 fixed and pushed (f39d6a9); gate
  green at 2058 passed / 2 skipped. The remedy is the opposite of the one
  the finding implies -- DELETE the six defensive copies rather than wipe
  them -- and that is the project's own settled rule rather than a
  judgement call. backup.py's _open_backup_vault carries it as a comment
  ("Pass the derived key itself, NOT a copy"), backup.py repeats it on
  rekey, auth.py passes its owned buffer through at create() and at both
  open() sites, and FIBR-0019 names the failure mode by number: a copy
  "lands in the caller's frame, out of reach of the finally that wipes the
  bytearray -- an INV-3 breach at eight sites". vault_migration was the one
  module that had not followed it.

  The finding named five sites; there are six -- _opens,
  _reads_end_to_end, _row_counts_or_none, verify_rollback_copy, and
  _convert's two opens.

  Where else the rule binds, measured rather than assumed: every other
  Vault.open / create / rekey site in the tree already passes through, so
  unlike M2/M3 there is no third site to file.

  mutation_probe on every PART rather than the feature: re-introducing the
  copy at each of the six sites independently was killed at all six, so a
  fix that reached five of them would be caught. No mutant survived.

  tests/features/recovery_key/spec.md gains INV-19. Its call-site labels
  key on the database each open() targets, never on line numbers -- the
  first draft used line numbers and this fix's own comment shifted them,
  which is a test failing for the wrong reason.
  Progress (2026-08-27, cont.): M5 fixed and pushed (451cfe1); gate green
  at 2060 passed / 2 skipped. _show_failure now takes which credential was
  tried, so a failed recovery attempt stops naming the password. The
  countdown message is credential-neutral and is shared unchanged.

  TWO routes reach it, not one, and the second needed its own slot. The
  wrong-code route comes through _on_recovery_derived; a failed DERIVATION
  comes through the worker's `failed` signal, which BOTH workers had
  connected to the same _on_failure. _on_recovery_failure is that
  counterpart -- a separate connection rather than a remembered flag,
  since the worker knows which credential it derived.

  Reachability, measured, and it changes what the finding is worth:
  BASE_DELAY_SECONDS is 1.0, so record_failure always leaves a positive
  delay owing and the countdown branch fires first. On a working install
  the user sees the neutral "Try again in 1s" and the sentence M5 names is
  never rendered. It is live only where the persisted throttle state does
  not survive its write -- an unwritable window.ini. So M5's stated harm
  does not occur on a healthy machine. The message was still wrong and the
  fix is cheap; the invariant states the corner rather than implying the
  common path.

  mutation_probe on every PART, and part 3 is why a second test exists:
  re-pointing the recovery worker's `failed` connection back at the shared
  password slot SURVIVED against the first test alone. All four parts are
  killed now.

  Filed and then RETRACTED in the same session: FIBR-0315, which began as
  "the recovery route swallows the rollback offer C1 made reachable". It
  does not. _unlock_through_slot passes the KEK of whichever slot was used
  into resume's kek_master parameter, so on the recovery route that is the
  RECOVERY KEK; both routes to RollbackAvailableError gate on
  rollback_copy_is_usable with that key, and the .pre-v2 pair is v1, which
  only KEK-master opens. The error is never raised there.
  _offer_rollback's docstring already said so by a second, independent
  gate. FIBR-0315 is re-scoped to what the measurement DID find: on that
  route _finish_if_readable asks the same question with the wrong key,
  gets False, and returns -- so C1's fix degrades back to admitting the
  user silently. Narrow, and its own bullet carries the reachability.

  Two invariants authored for the retracted framing were removed rather
  than re-aimed: they asserted a contract that should not exist and passed
  only because the raise they needed was monkeypatched.
  Progress (2026-08-31): M6 fixed and pushed (07a2f60); gate green at
  2061 passed / 2 skipped. RecoveryCodeDialog's clipboard-is-None branch now
  owns its guard from the dialog's parent, or from the application object where
  there is none, as build_recovery_offer already did -- so the clear timer no
  longer dies with the dialog it was parented to. The comment that certified the
  broken shape as deliberate is corrected; spec INV-21 states the rule.

  mutation_probe found the test's hole rather than the fix's. Reverting to
  parent=self was killed at once, but dropping the fallback so the guard is left
  UNPARENTED survived: the leg held the only Python reference keeping an
  ownerless guard alive, which production does not. The leg now drops that
  reference and collects, and the mutant is killed. Dropping the parent
  preference survives and should -- the leg's dialog has no parent, so both
  expressions name the same owner.

  A trap worth naming: mutation_probe's expect_occurrences refused two mutations
  because `owner: QObject | None = ...` is a SUBSTRING of `clipboard_owner:
  QObject | None = ...` further down the file. Without that guard both would
  have reported killed against a site the label did not name.

  Filed FIBR-0316 while measuring: TransactionsView setParent(self)s its own
  guard, and MainWindow._clear_live deletes the workspace on lock -- the same
  rule at a third site, on a much less sensitive value. Not folded in;
  ui/transactions.py is outside the FP03 scope FP04 reviews.
  Progress (2026-08-31, cont.): M7 fixed and pushed (5f51451); gate green at
  2064 passed / 2 skipped. NewMasterPasswordDialog._on_submit now has the
  VaultLockedError arm its three siblings gained in P12, failing closed and
  silently. The vault is open while that D6 dialog is shown, so the idle timer is
  live, and MainWindow._lock closes the dialog with deleteLater() before locking
  -- so a queued submit still arrives with the service locked and the broad arm
  rendered "the vault is locked" onto a dialog already being torn down. The
  finally still covers the new arm, so the password buffer is wiped on this path
  too.

  The test carries a second leg asserting a plain RuntimeError still shows a
  message, which is what stops the narrowed arm over-correcting into swallowing a
  genuine re-wrap failure. mutation_probe on each part: arm removed, killed; arm
  stops returning so a locked vault falls through to accept(), killed; arm
  widened back to `except Exception`, killed by that second leg.

  Where else the rule binds, measured rather than assumed: six broad
  `except Exception` handlers under ui/, and only two sit where a vault is open
  and the idle timer is live -- keep_recovery_code (P12 fixed it) and this one.
  The other four run before any vault exists: key derivation, vault creation, and
  the two update workers. Surface closed.

  spec INV-22 added. C1, H1, H2 and M1-M7 are now closed; M8-M10, L1-L16, Q1-Q5
  and M10's decision remain.
  Progress (2026-09-02): M8 done, and probing it found two more.

  crypto.validate_slot's third consumer (ui/_password_hint.py) now runs it, and
  a slot it cannot test -- KdfPolicyError or argon2 HashingError -- takes the
  fail-open-with-a-warning path the unreadable-sidecar arm above it already
  established. Locked by recovery_key INV-23 over three damage shapes, chosen so
  neither half of the guard can be dropped: a short salt and a zero time_cost
  both reach argon2, while a short nonce reaches unwrap_dek instead, whose single
  undifferentiated KeyUnwrapError makes the loop continue and the route return
  SILENTLY. Only validate_slot catches that third one.

  mutation_probe on every part rather than the feature exposed two defects the
  suite could not see. An explicit return at the end of the new arm that nothing
  measured, since the function ends there -- removed. And an unfiltered
  caplog.records assertion that crypto.read_sidecar_v2's own warning satisfied,
  so a dropped validate_slot survived even after the nonce leg was added; the
  assertion now names its own logger. All four mutants killed after that.

  Scope held deliberately: validate_params still bounds only the low side, so
  time_cost and parallelism stay argon2's to refuse. That general gap is
  FIBR-0327's first MEDIUM bullet, which names the UI's except tuple as one of
  three escapes. This closes that one; restore_backup and verify_backup remain
  FIBR-0327's.

  Gate green, 2086 passed / 2 skipped. Pushed as c39561d.
  Progress (2026-09-02): M9 done.

  Unknown v2 sidecar fields now survive a read-modify-write, at the three levels
  one can carry them: top-level, inside the shared kdf group, and inside a slot
  record. read_sidecar_v2 already tolerated them -- both gates are subset checks
  -- but to_dict re-emitted only the fields the dataclasses name, and every
  writer round-trips through it, so an older build deleted them on the next
  ordinary user action. An unknown SLOT NAME already survived, slots being a dict
  copied wholesale, so that was never part of it.

  No call site changed. replace() carries every field through, and with_slot,
  without_slot and _finish all build on it, so the preservation reaches every
  existing writer for free. new_sidecar builds from params alone, so a fresh
  vault carries no extras and INV-4's exact field-set pin -- scoped to a freshly
  created vault -- is untouched. Locked by recovery_key INV-24, which drives a
  REAL read-modify-write through add_recovery_key rather than a direct round trip.

  mutation_probe on every part: the three reader captures and the three to_dict
  emissions all killed. One survivor, reported rather than papered over -- the
  extras-first ordering that stops a stray key shadowing a real one is
  unmeasured, and unreachable rather than merely untested, since the reader
  filters the known names out of both bags by construction. INV-24 records that
  gap and its reason instead of implying coverage.

  Gate green, 2087 passed / 2 skipped. Pushed as 85ac9f1.

  M10 is next and is a DECISION rather than a fix: FIBR-0019 D5 promises a
  regeneration offer after a recovery unlock and none exists, so either the code
  or the promise has to move.
  Progress (2026-09-02, cont.): the open questions are worked. M10, Q1, Q2,
  Q3, Q5 and H3 are closed, with Q4's policy decided.

  Q1 and Q2 closed as NO DEFECT, each verified rather than assumed. A spurious
  migration_pending on a healthy v2 vault is a self-healing no-op: it takes
  branch 1, finds nothing to unlink and clears the flag, and _finish's own
  docstring anticipates the re-entry. And ui/categories.py's _on_update cannot
  reach update_category with a root selected -- and could do no harm if it did,
  since that call refuses a root subject before it reads the name. The _on_add
  asymmetry is the depth cap, a UI-only rule, not root protection.

  Q5 was a real defect and worse on POSIX than on Windows: restore_backup
  asserted nothing about the vault being locked, so os.replace succeeded over an
  open connection and the app went on writing the moved-aside inode. Silent, no
  error. Vault gained is_open; the guard false-positives on nothing.

  M10: the user chose to implement D5's offer rather than amend the spec -- it
  needed no spec change, so it avoided re-arming a gate already at its cap.

  Q4 + H3: user chose keep-newest-and-prune, plus fixing the reset. H3 was NOT
  previously fixed -- FIBR-0318 removed the migration artefacts, a different
  item -- so "start over" was leaving a complete vault openable under a
  superseded password.

  BOOKKEEPING, worth stating: H3 and H4 had dropped out of this bullet's own
  remaining-work list. Every progress note read "C1, H1 and H2 are closed;
  M1-M10 and L1-L16 remain" and named neither. H3 is now closed. H4 IS STILL
  OPEN and is the next HIGH: _install carries the incumbent's -wal aside while
  _reconcile_interrupted_restore restores only the pair, so the crash-recovery
  path drops committed frames -- silent loss of the user's most recent
  transactions.

  Q3 needed no code change and could not have one: the AAD is an AEAD input, so
  adding salt_len would stop every existing slot unwrapping. It is also safe --
  validate_params pins salt_len exactly, unlike memory_kib. Documented in
  security-model INV-3d, which tripped rule 14's gate.

  That gate ran three loops to its cap and was worth far more than the edit that
  armed it. It found T11 still routing a forgotten password to the destructive
  reset without mentioning the recovery code -- FIBR-0019's whole purpose; INV-2
  documenting one number for the creation pin and the validation floor, under a
  promise that following it would not lock anyone out; INV-2 contradicting its
  own FIBR-0019 amendment about what reaches SQLCipher's raw key; and INV-6
  crediting gitleaks with catching account numbers, which it does not. Loop 2
  caught my own edit stating a per-route obligation as structural -- the M8 bug,
  which FIBR-0020's slot would have inherited. Log: docs/reviews/
  security-model-review-log.md.

  Remaining on this item: H4, L1-L16.
  Progress (2026-09-02, cont.): H4 closed. Only L1-L16 remain.

  H4 was not the job it was filed as. Its FIX already existed -- it landed in
  0a83b0a under FIBR-0318, a different item, and was never recorded as closed
  here, which is the same tally gap that lost H3 and H4 from the remaining-work
  list. What was missing was a test, and mutation_probe proved it: removing the
  _WAL_SIBLINGS half of the reconcile loop left the whole backup suite green. A
  HIGH about silent loss of the user's most recent transactions was one refactor
  from regressing invisibly.

  Locked as backup INV-18, both branches. The second exists only because the
  probe found it: the first leg plants an original journal AND an aborted one, so
  it never exercises the case where the original was already checkpointed and the
  aborted restore's orphan must be REMOVED -- that journal belongs to a different
  database under a different key, and SQLite would replay it against the
  recovered vault. Both mutants now die. Gate green, 2094 passed / 2 skipped,
  pushed as 6e33a3c.

  So FP04's CRITICAL, HIGH and MEDIUM work is done. L1-L16 is what stands between
  here and closing the FP02 -> FP03 -> FP04 chain, which is what returns
  FIBR-0019 to shipped and clears the largest of v1.0.0's three blockers
  (FIBR-0304).
  Progress (2026-09-03): L1 and L2 fixed and pushed (e1006df); gate green
  at 2153 passed / 2 skipped. One rule at two sites -- derive_key copies
  its argument in and never writes to it, so the caller owns wiping it.
  Its docstring now says so, both defects being a caller reading the old
  silence as "handled".

  L1 -- the hint's trial-unwrap built its argument inline, so the decoded
  recovery code had no name to wipe it by, on a path that runs while the
  vault is open. The wipe sits on the way OUT of the call: an
  out-of-range time_cost reaches argon2 and returns HashingError, which
  INV-23 catches and fails open, and that is the likeliest early exit.
  mutation_probe found it -- moving the wipe off the finally survived the
  first draft, so a second leg pins the raising path.

  L2 -- _unlock_v1's failure handler asks sidecar_version which side of
  S4 the failure landed on; that call parses the sidecar, so it raises on
  one the failed migration left unreadable and propagated with the key
  still set. Every other exit from _unlock_v1 wipes first.

  Five mutants, all killed: each wipe removed, the wipe moved off the
  finally, the refactored branch inverted, and the probe guard reverted
  to its pre-fix shape.
  Progress (2026-09-03, cont.): L3, L4 and L5 fixed and pushed (ac411ce);
  gate green at 2157 passed / 2 skipped. Three filesystem-safety items.

  L3 -- S0 fsynced the .pre-v2 copy's database and sidecar halves and left
  the -wal beside them unflushed, so a crash between S0 and S4 could leave
  a rollback copy that opens and is missing the user's most recent rows.
  Every copied sibling is flushed now; the test asserts the -wal only,
  since SQLite rebuilds -shm and its durability buys nothing.

  L4 -- the save-your-code overwrite leg chmod'd by PATH after the
  descriptor was open, so the name could come to mean a different file and
  that file's mode was the one changed. os.fchmod names the descriptor,
  guarded by hasattr because it is POSIX-only and the comment beside it
  already places the exposure there.

  L5 -- the export's failure handler unlinked <dest>.tmp unconditionally,
  including when it raised before _write_fbk had written a byte. That name
  comes from the destination the user picked, so it can be someone else's
  file. Only the cleanup is gated. _write_fbk's own unlink stays
  unconditional and DELIBERATELY so: clearing the path is what lets O_EXCL
  win against a planted symlink, and no ownership check ahead of it is not
  itself a race. Recorded in the code so it is not re-filed.

  Seven mutants, all killed. One was a survivor first: nothing pinned that
  the cleanup still RUNS once the temp is ours, so a guard that disabled
  it entirely would have passed. That leg exists now.

  Remaining on this bullet: L6-L16.
  Progress (2026-09-03, cont.): L8, L11 and L12 fixed and pushed
  (669339f); gate green at 2160 passed / 2 skipped.

  L12 is the one with teeth. A row-count mismatch put the PER-TABLE counts
  into the message at both sites -- S2's refusal, which reaches
  _unlock_v1's log.exception, and branch 2's warning, which logs directly.
  That is how many accounts and transactions the household has, in the
  clear beside the encrypted vault; INV-9 says the log records no
  decrypted data. Both now name the disagreeing tables and nothing else.
  mutation_probe is why the second site is covered at all: reverting it
  alone survived, so the S2 leg was not reaching it. mypy then found
  replacement_counts can be None, which the old message rendered as "got
  None"; it has its own arm now, mirroring the live side above it.

  L8 -- the COMMENT was wrong, not the code. unlock_failed said it fires
  on every failure branch while the check-symbol branch returns without
  it, and § 4.6 does not count a typo as an attempt. The comment names the
  exclusion and a test locks the decision, so the opposite repair is not
  made later by someone reading the code against the old sentence.

  L11 -- the comment called UnicodeDecodeError / RecursionError the
  sidecar reader's route. Since crypto._MALFORMED_SIDECAR the params read
  normalises both to KdfPolicyError, already caught in that tuple. They
  stay as a backstop; only the claim changed.

  Five mutants, all killed. Remaining: L6, L7, L9, L10, L13-L16.
  Progress (2026-09-03, cont.): L6, L7, L9, L10, L13 and L14 closed.

  L6 and L7 pushed as 7ac60de. L6 -- the hint refusal the user reads was a
  bare literal in ui/, covered by neither coding.md § 5.2 nor
  allowlist-004, which is scoped to ui/_amount.py. It goes through
  QCoreApplication.translate with an explicit context, the module having
  no QObject for self.tr. Its three siblings live in the Qt-free
  services/password_hint.py and cannot translate their own; that stays
  FIBR-0017's and the comment says so, so this does not read as the family
  being done. The test drives a real QTranslator, so the marker returns
  only if the context AND the source literal are what a catalog will carry.
  L7 -- _LABEL_CONTEXT was read by nothing; every call site passes the
  literal, because lupdate extracts only literal arguments and a named
  context yields an empty entry, which is the R3 shape. Constant deleted,
  the three docstrings corrected. No test: it removes a dead name and
  corrects prose, so there is nothing to mutate.

  L9 and L10 pushed as 9cf103c. L9 -- the recovery-offer clipboard guard
  must outlive its dialog (R1) so it is parented to the window, and nothing
  retired it: every Settings Add / Replace left a QObject + QTimer for the
  session. ClipboardAutoClear gains retire(), delete-now-if-idle and
  after-the-pending-clear otherwise; the long-lived transactions-list owner
  never calls it. mutation_probe confirms R1 still holds -- making retire()
  eager is killed by an existing leg. L10 -- D6 refuses Escape and [X] on
  purpose, but set_master_password can fail persistently, and the dialog is
  application-modal, so File > Quit is unreachable too: an app that cannot
  be closed. It carries its own Quit shortcut now, releasing the modal grab
  and closing through the window's close() so the geometry save and the
  worker drain still run. Not a way PAST the forced password: done(Rejected),
  nothing is connected to rejected, and a mutant that accepts is killed.

  L13 -- CLOSED BY LATER WORK, no change owed here, verified rather than
  assumed. Both halves are gone: FIBR-0318 (0a83b0a) added the first_run
  reconciliation branch this finding says does not exist, and FIBR-0327
  (c79dc75) guarded the recovery so a blocked one routes to run()'s named
  VaultStateError branch instead of hard-erroring during __init__.

  L14 -- SPLIT, and the half that is closed is the half that mattered.
  pyproject now sets check_untyped_defs for finbreak.*; src was already
  clean under it (109 files, zero errors), and a deliberate error inside an
  unannotated src function was confirmed caught where it had been
  invisible. The tests half is NOT done and is FIBR-0331: measured
  2026-09-03, 345 errors across 25 files. Turning it on for the app and
  silencing it for tests would close the gate gap on paper while the suite
  that decides whether the gate means anything stays unread.

  Remaining on this bullet: L15 and L16.
  Progress (2026-09-03, cont.): L15 and L16 closed (722d404); gate green
  at 2165 passed / 2 skipped. L1-L16 are now all closed, so every finding
  on this bullet -- C1, H1-H4, M1-M10, Q1-Q5 and L1-L16 -- is disposed of.

  L16 -- read_sidecar_v2 parsed the file, then asked sidecar_version for
  its version, which re-read and re-parsed the same path: every v2 sidecar
  read twice, three times through auth.read_sidecar. The version now comes
  from the dict in hand, via a _version_of helper both entry points share.
  mutation_probe surfaced a SECOND thing, pre-existing and not introduced
  here: dropping the version gate survived, because a v1 sidecar has no
  kdf group and the next check refuses it anyway -- the refusal rested on
  that accident. It has its own leg now.

  L15 -- § 13.3 enumerated two kinds of debris and there are three: a run
  aborting between S3's write and S4's rename leaves
  vault.kdf.json.migrating. Measured rather than assumed -- the sidecar
  writer renames a fresh .tmp over its destination, so the next S3
  overwrites a stray one rather than refusing it, which is why this never
  wedged a retry the way the S1 debris once did. The count is dropped
  rather than corrected, since the count is what went stale. FIBR-0154's
  translate(_LABEL_CONTEXT, ...) references went with it, the constant
  having been deleted with L7.

  Rule 14: no gate on either spec, recorded in the commit body. Both
  amendments record what was already built, which is the rule's named
  instance for an amendment that does not re-arm.

  NOT flipped to shipped here. This bullet is FP04, and its close is
  /close-phase's -- check-code plus review-code lanes from a fresh
  context, which is what FP03's close did and what produced this bullet.
  The findings being disposed of is the precondition for that run, not a
  substitute for it.
  **Layman:** The recovery-key work was reviewed again with fresh eyes; one serious problem can strand a half-upgraded vault with no way back, and several smaller fixes from last time only reached some of the places they needed to.
  Kind: review-fix.
  Source: close-phase-2026-08-25 (check-code + review-code x4 lanes, FP03 close, fresh context).
  Lanes: crypto, security, migration, backup, ui.

- 📋 [FIBR-0314] **The interrupted-restore recovery puts the old pair back without making it durable.**
  main_window._reconcile_interrupted_restore unlinks the live vault and
  sidecar, then os.replace()s the most recent complete `*.old` pair back over
  them. Neither the sources nor the containing directory is fsynced, so none of
  it is guaranteed to survive a power loss -- and the unlink comes FIRST, so a
  crash inside that window can leave no vault at all, on the one path that
  exists to recover from an interrupted restore.

  Same rule as FIBR-0313 M2 (backup._install) and M3
  (vault_migration.restore_rollback_copy). Found while measuring where else
  that rule binds, and deliberately NOT folded into them: this site is in the
  UI layer with no fsync helper of its own, and FIBR-0313 H4 rewrites this
  same function for a different reason -- it restores two files and drops the
  incumbent's committed -wal frames. Whoever takes H4 should take this with
  it rather than touching the function twice.

  Distinct from FIBR-0309, which covers write_sidecar_json's directory fsync
  and the S4/S5 ones, and reaches neither this site nor M2/M3.
  **Layman:** If the machine loses power while the app is putting your old data back after a failed restore, the recovery itself may not survive -- and could leave no data file at all.
  Kind: fix.
  Source: in-session-2026-08-27 (FP04 M2/M3 blast-radius measurement).
  Lanes: backup, ui.

- 📋 [FIBR-0315] **On the recovery route C1's rollback check is asked with the wrong key, so it silently degrades.**
  C1's defect, one route over, and live today.

  RollbackAvailableError subclasses VaultStateError (errors.py). The UI has
  exactly ONE handler for it -- unlock.py's _on_derived, the PASSWORD route,
  whose own comment says the arm must come "BEFORE the VaultStateError arm
  below, which is its base class". _on_recovery_derived has no such arm: its
  arms are KdfPolicyError, SchemaVersionError, VaultStateError. So the base
  arm catches the subclass and renders _pairing_broken() -- "the two do not
  belong together, or the vault file is damaged. If you have a backup,
  restore it."

  The route is real, not theoretical. complete_recovery_unlock and
  complete_unlock share _unlock_through_slot, which calls
  vault_migration.resume when the sidecar is migration_pending. resume's
  terminal branch raises RollbackAvailableError from two sites in
  _finish_if_readable. FIBR-0313 C1 is what made branch 1 raise rather than
  return, so C1 WIDENED the set of unlocks that reach this and the recovery
  handler was never updated -- the FP04 pattern its own bullet names, a fix
  that reached some call sites and not all.

  Consequence: a user holding a correct recovery code, on a vault with a
  verified .pre-v2 pair beside it, is told their vault is unopenable and
  pointed at a backup they may not have. The rollback offer -- "the whole
  return on D8" -- is never made. That is the same dead end C1 closed for
  the password route.

  Fix: give _on_recovery_derived a RollbackAvailableError arm ahead of its
  VaultStateError arm, routing to _offer_rollback, exactly as _on_derived
  does. Check while there whether the follow-up copy still reads correctly
  for a user who arrived by recovery code -- _rollback_restored() says
  "Enter your password again to open it", which is right (the restored pair
  is v1 and takes the password route) but was written for a password-route
  arrival.
  Measured 2026-08-27, and it SPLITS the fix in two. The bullet above says
  to route the recovery arrival to _offer_rollback "exactly as _on_derived
  does". Doing only that would introduce a new harm, so do not.

  restore_rollback_copy ends with os.replace(copy_sidecar, sidecar_path).
  The v2 sidecar is overwritten and NO .old is kept -- and the v2 sidecar is
  the only thing holding the recovery slot, because a .pre-v2 sidecar is v1
  and has no slots at all. So accepting the offer DESTROYS the recovery
  code. For a user who arrived by recovery code -- who by definition has no
  working password -- that turns "recovery code works, data unreachable"
  into "nothing opens this vault".

  And _rollback_offer() reads "...and your password opens that copy" and
  "finbreak will ask for your password again to open them", which is a
  promise that user cannot cash.

  So the fix is two halves. (1) The routing: a RollbackAvailableError arm on
  _on_recovery_derived ahead of its VaultStateError arm. (2) The copy: a
  recovery-specific offer stating the two facts that differ for that user --
  the restored copy is opened by the master password, and restoring replaces
  the key record so the recovery code stops working. Declining is still free
  and still leaves the copy in place, so an honest offer preserves the user's
  choice rather than removing it.

  Offering it remains right despite the one-way door: the alternative today
  is _pairing_broken()'s "if you have a backup, restore it" while a verified
  copy sits in the same folder, and only the user knows whether they can
  still produce the password.
  RETRACTION (2026-08-27, same session, before any fix was written). The
  two notes above are WRONG in their framing and are kept rather than
  deleted because the measurement that refutes them is the useful part.

  The recovery route cannot swallow the offer, because the offer is never
  made to it. _unlock_through_slot passes the KEK of WHICHEVER SLOT WAS
  USED into resume's parameter named kek_master -- on the recovery route
  that is the RECOVERY KEK. Both routes to RollbackAvailableError gate on
  rollback_copy_is_usable(vault_path, sidecar_path, kek_master), and the
  .pre-v2 pair is v1, so only KEK-master opens it. The recovery KEK does
  not, the check is False, and the error is not raised. _offer_rollback's
  docstring reaches the same conclusion by a different gate (a
  migration-pending sidecar carries slots.master alone, so the recovery
  route normally never enters the ladder). Both gates hold; the docstring
  is right and naming only the first one is what made it look defeasible.

  What IS real, and is what this item now carries: on that route
  _finish_if_readable asks rollback_copy_is_usable with the recovery KEK,
  gets False, and RETURNS. So a vault that opens but does not read end to
  end admits the user silently -- exactly the pre-C1 behaviour C1 was
  filed to remove, degraded back on one route by a key that cannot answer
  the question being asked.

  Reachability is narrow and should be stated rather than assumed. It needs
  a sidecar that is BOTH migration_pending and carrying a recovery slot,
  which S3 never writes (it writes slots.master alone). The route there:
  _finish_quietly absorbs an OSError, leaving migration_pending set on a
  vault the user is now unlocked into, and the user then adds a recovery
  code in Settings. Narrow, but it is the disk-full class § 6 already
  plans for.

  Not fixable by offering the rollback: that user has no KEK-master, so
  the copy is not openable by them either. The honest remedy is to tell
  them their rows are unreachable and that a pre-upgrade copy exists which
  only their master password opens -- rather than admitting them silently.

  Tests: none. INV-20 and INV-21 were authored for the retracted framing
  and were removed rather than re-aimed; they asserted a contract this
  measurement says should not exist, and they passed only because the raise
  they depended on was monkeypatched. Whoever takes this writes the test
  for the contract in the paragraph above, and the precondition to assert
  first is that the state is reachable at all.
  **Layman:** If you unlock with your recovery code while an interrupted upgrade is half-done, finbreak tells you the vault is broken instead of offering to put back the copy it saved before the upgrade — which is sitting right beside it.
  Kind: fix.
  Source: in-session-2026-08-27 (found while scoping FIBR-0313 M5).
  Lanes: ui, migration.

- 📋 [FIBR-0316] **A copied transaction stays on the clipboard when the vault locks before the clear is due.**
  Third site of the FIBR-0310 R1 rule, found while fixing FIBR-0313 M6 (the
  RecoveryCodeDialog site).

  TransactionsView calls setParent(self) on its ClipboardAutoClear -- injected
  or self-built -- so the guard's single-shot clear timer is a child of the
  view. MainWindow._clear_live deleteLater()s the whole workspace on lock and on
  rebuild, destroying the view and the pending timer with it. A copy made inside
  the clear window before an idle auto-lock is therefore never cleared.

  The comment above that setParent states the destruction as the intended
  effect. It is the wrong way round: what the user copied is exactly what a lock
  should clear.

  Lower severity than the two sites before it -- a rendered cell amount or
  description, which the recovery-code test calls the least sensitive thing the
  app copies, against a code that opens the vault on its own. Deliberately NOT
  folded into the M6 commit: ui/transactions.py was outside the FP03 scope FP04
  reviews, and the remedy is a decision rather than a move -- own the guard from
  the application object as build_recovery_offer does, or clear on lock
  explicitly.
  **Layman:** If you copy something from the transactions list and the app locks itself before the clipboard auto-clear runs, the copied text is left on the clipboard for good.
  Kind: fix.
  Source: in-session-2026-08-31 (found while fixing FIBR-0313 M6).

### 🎨 Features & accessibility

- ✅ [FIBR-0021] **Multi-currency decision (ADR).**
  Decide single- vs
  multi-currency for v1 **before** accounts are built. If multi: a
  currency column on accounts/transactions, QLocale-formatted display,
  and a rule that the dashboard never sums across currencies without
  conversion. *Sequencing:* decide before FIBR-0005 (accounts) — adding a
  currency column afterwards is a schema migration. Target phase: P03
  (the decision precedes it). Dependencies: none. Lanes: data.
  Kind: investigate. Source: user-request-2026-07-01.
  Resolved 2026-07-02 (user decision): SINGLE-currency for v1 — every
  account shares the vault's one base_currency, set at first-run. Rationale:
  matches the shipped FIBR-0004 model, and because FIBR-0005 introduces the
  forward-migration runner, adding per-account/per-transaction currency
  later is a routine forward migration, not a painful retrofit — so the
  "decide before accounts" gate is satisfied by choosing single-currency now
  and revisiting only when a real multi-currency need arises. If revisited:
  currency column on accounts/transactions, QLocale-formatted display, and a
  rule that the dashboard never sums across currencies without conversion.
  Source: user-request-2026-07-01.
  Lanes: data.

- 📋 [FIBR-0022] **Budgets + recurring / subscription detection.**
  Per-category monthly spending limits with progress + over-budget
  signalling on the dashboard, plus automatic detection of repeating
  charges (same payee / amount cadence) so subscriptions surface. Target
  phase: P10. Dependencies: FIBR-0006 (category tree), FIBR-0010 (rules).
  Lanes: reporting, ux. Kind: feature. Source: user-request-2026-07-01.
  Split 2026-07-15: the recurring/subscription-detection half is now FIBR-0142 (active, being built first per user pick). This bullet stays as the budgets tracking item (per-category monthly limits + over-budget dashboard signalling) — the follow-up after FIBR-0142 ships.
  **Layman:** Set a monthly spending limit per category and see when you go over it, and have repeating charges like subscriptions spotted for you automatically.
  Kind: feature.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0023] **Theming: separate theme sets for normal and colourblind vision + picker.**
  Ship **two families** of themes — a set
  for normal colour vision **and** a set designed for colourblind users
  (protanopia / deuteranopia / tritanopia-friendly palettes) — selectable
  from the FIBR-0014 Settings screen (beside the FIBR-0017 language
  picker). The normal-vision family goes beyond plain light/dark: ship a
  small curated set of named themes — at minimum **Light**, **Dark**,
  **Midnight** (near-black OLED-friendly), **Solarized Light**,
  **Solarized Dark**, **Sepia** (warm, low-eyestrain), and a
  **High-contrast** pairing — plus a **"follow the OS"** option that
  tracks the system light/dark setting. Each theme is a named palette
  (window / surface / text / accent / chart-series roles), defined in one
  place so adding a theme is data, not code — no per-widget hardcoded
  colours (coding.md § 8 bars magic constants without a named source; a
  QSS stylesheet + palette tokens keeps colours in one table). Dashboard
  charts (FIBR-0012) draw series colours from the
  active theme's chart-series role, so whichever theme is chosen keeps the
  chart series distinguishable. Target phase: P12. Dependencies:
  FIBR-0012, FIBR-0014. Lanes: ui, accessibility. Kind: ux.
  Source: user-request-2026-07-01.
  **Layman:** Pick from a set of colour schemes, including a family designed to stay readable if you are colourblind.
  Kind: ux.
  Lanes: ui, accessibility.

- 📋 [FIBR-0024] **Accessibility: keyboard navigation + screen-reader support.**
  Full keyboard control (focus order, shortcuts, no mouse-only
  actions) and screen-reader labels/roles via Qt accessibility
  (`QAccessible`) on widgets and charts. Pairs with the i18n/RTL
  (FIBR-0017) and theming (FIBR-0023) work. Target phase: P12.
  Dependencies: FIBR-0014. Lanes: ui, accessibility. Kind: accessibility.
  Source: user-request-2026-07-01.
  **Layman:** Use the whole app with the keyboard alone, and have a screen reader announce what is on screen.
  Kind: accessibility.
  Lanes: ui, accessibility.

- 📋 [FIBR-0034] **Import preview + undo (rollback a whole import batch).**
  Before an import lands, show a preview — "about to add 214 transactions
  from 3 May–2 Jun across 1 account" — so a wrong file can be cancelled
  before it touches the ledger. Each committed import is tagged as a batch
  so it can be undone in one action if it was the wrong statement.
  Preserves manual category overrides on re-import per FIBR-0010's rule.
  Target phase: P06 (lands with the first import UI). Dependencies:
  FIBR-0007. Lanes: services, ui, repo, tests. Kind: feature.
  Source: user-request-2026-07-01.
  **Layman:** See exactly what an import is about to add before it lands, and undo a whole import in one action if it turns out to be the wrong file.
  Kind: feature.
  Lanes: services, ui, repo, tests.

- ✅ [FIBR-0035] **Auto-categorisation that learns from corrections.**
  Extends the FIBR-0010 rules engine: when the user manually re-files a
  transaction (e.g. "TESCO" → Groceries), offer to create or update a rule
  so similar future transactions self-categorise — the tedious part gets
  quieter the more the app is used. Always a **suggestion** the user
  confirms (never a silent auto-rule), and a manual override still wins
  over any learned rule (FIBR-0010's invariant). Target phase: P08
  (extends the rules engine). Dependencies: FIBR-0010. Lanes: services,
  ui, tests. Kind: feature. Source: user-request-2026-07-01.
  Note (2026-07-09): the core learn-from-corrections behaviour (offer to *create* a rule from a manual correction; suggestion-only; manual override still wins) is pulled forward into FIBR-0010 (spec INV-5 / D11), per the 2026-07-09 user request. FIBR-0035's "*update* an existing rule" variant is subsumed by FIBR-0010 D6 (a learned rule inserts at top priority, beating the rule it corrects — no in-place update needed). Re-evaluate / close this bullet when FIBR-0010 ships.
  Resolved (2026-07-10): fully delivered by FIBR-0010. The create-a-rule-from-a-correction learning is FIBR-0010 INV-5/D11; the update-an-existing-rule variant is subsumed by D6 (a learned correction inserts at top priority, beating the rule it corrects — no in-place update needed). Suggestion-only + manual-override-wins guarantees both hold. No separate work remains.
  Kind: feature.
  Source: user-request-2026-07-01.
  Lanes: services, ui, tests.

- 📋 [FIBR-0036] **Net-worth-over-time trend.**
  A dashboard line showing
  the running total across all accounts month to month — is the overall
  picture trending up or down — distinct from FIBR-0012's
  income-vs-expenditure bars (this is the cumulative balance, not per-month
  flow). Draws its series colour from the active theme (FIBR-0023) like the
  other charts. Target phase: P10. Dependencies: FIBR-0012. Lanes:
  reporting, ui, tests. Kind: feature. Source: user-request-2026-07-01.
  **Layman:** A dashboard line showing whether your overall money position is trending up or down month by month.
  Kind: feature.
  Source: user-request-2026-07-01.
  Lanes: reporting, ui, tests.

- 📋 [FIBR-0038] **Statement coverage tracking + gap detection.**
  Record each imported statement's coverage period (start/end date) per
  account as first-class data, then a gap-detection pass reports
  uncovered date ranges between covered ranges, per account (e.g.
  Jan–Mar + May-onwards -> flags April missing). Range-based, so it is
  reliable where a transaction-date heuristic is not: a quiet month with
  zero transactions is still "covered" if its statement was imported, and
  it handles non-monthly cycles (quarterly) and overlapping imports
  (merge coverage). "Up to date" (latest statement -> today) is not a
  gap; only holes between covered ranges are. Surfaces as a per-account
  completeness report + a dashboard warning badge. Depends on the
  coverage-period capture hook added at first import (FIBR-0007) — without
  recorded periods, gaps can only be guessed from transaction dates
  (false alarms on quiet months). Dependencies: FIBR-0005 (accounts —
  gaps are per-account), FIBR-0007 (import captures the periods).
  **Layman:** Warns you when you've skipped a statement — e.g. you loaded January–March and then May onwards, and it spots that April is missing for that account.
  Kind: feature.
  Lanes: services, repo, ui, tests.
  Source: user-request-2026-07-02.

- 📋 [FIBR-0039] **In-app liability disclaimer + issue reporting.**
  A plain-language liability disclaimer — the app is provided as-is and is not responsible for incorrect information it may display (mis-parsed amounts, wrong totals); it is local-only and not financial advice. Shown at first run (acknowledged once, persisted) and always available from an About/Help dialog. Alongside it, a "Report an issue" link opening the GitHub Issues page (https://github.com/milnet01/finbreak/issues) so users can log problems for resolution. Complements the MIT LICENSE's warranty disclaimer with a user-facing, plain-English one. Shares the About/Help screen with the donate-links item — whichever ships first builds the screen.
  **Layman:** A clear notice that the app isn't responsible for any incorrect figures it shows, with an easy button to report problems so they get fixed.
  Note (FIBR-0054): when this disclaimer copy is written, phrase "local-only" as **data-locality** ("your financial data stays on your machine"), not "never connects" — the opt-in updater is a consented outbound exception, so a bare "local-only" shown on-screen would mislead.
  Kind: feature.
  Source: user-request-2026-07-03.
  Coordination note update: FIBR-0051 (P07.5) ships only a minimal About (QMessageBox.about) and puts donate links in their own Donate menu — it does NOT build the shared About/Help screen. So this bullet still owns building that screen (disclaimer + "Report an issue" link); the old "whichever of FIBR-0039/0040 ships first builds the screen" pact no longer applies.

- ✅ [FIBR-0040] **In-app donate / support links.**
  Clickable support links that open each FUNDING.yml sponsor page in the user's browser — GitHub Sponsors (milnet01), Patreon (AntsProjectsHub), and the Paybru tip URL (https://paybru.co.za/tip/ants-projects-hub). Surfaced in the About/Help dialog and a Help-menu entry. Keep the URLs in one place in sync with .github/FUNDING.yml (a small constants module or read at build time) so they never drift. Shares the About/Help screen with the disclaimer item.
  **Layman:** Buttons in the app that open the pages where people can support the project financially.
  Kind: feature.
  Source: user-request-2026-07-03.
  Being delivered by FIBR-0051 (P07.5 app-shell, spec in cold-eyes): its Donate menu ships all three FUNDING.yml links + the sync check (FIBR-0051 INV-8a). Flips ✅ when FIBR-0051 ships (FIBR-0051 DoD #6). Note the placement differs from this bullet's "About/Help dialog + Help menu" — FIBR-0051 uses a dedicated Donate menu.
  Resolved (2026-07-09): delivered by FIBR-0051's Donate menu — the three .github/FUNDING.yml links (GitHub Sponsors/Patreon/PayBru) via QDesktopServices.openUrl + the INV-8a sync check that fails on drift. Placement is a dedicated Donate menu rather than the About/Help dialog; same substance.

- ✅ [FIBR-0042] **Preserve the as-posted local date for a timezone-bearing OFX <DTPOSTED>.**
  Surfaced by the FIBR-0008 /indie-review (lane 1, 2026-07-04). `OfxImporter` uses `tx.date.date().isoformat()`; ofxparse normalises a timestamped `<DTPOSTED>` to UTC (`local - offset`), so a transaction posted in the evening of a negative-offset zone rolls to the next calendar day (verified: `20260105230000[-5:EST]` -> "2026-01-06"). Two consequences: (a) mis-assignment to the wrong day and, at a month boundary, the wrong statement period; (b) it can defeat INV-6 cross-source dedup (an OFX row keyed on occurred_on won't match a manually-entered copy if the OFX date shifted). Out of the FIBR-0008 contract (D4/INV-1b specify date-only DTPOSTED, and the fixtures use date-only, so nothing shipped is wrong). Blocked-ish: ofxparse discards the original tz offset, so the fix needs either raw-DTPOSTED reparsing or a product decision on whether local or UTC date is authoritative. Fix: decide the authoritative date, recover the local calendar date (or document UTC), add a tz-bearing DTPOSTED test.
  **Layman:** Some bank OFX files stamp each transaction with a time and timezone; today an evening transaction can be filed under the wrong day, which can also stop it matching a manually-typed copy.
  Kind: fix.
  Source: indie-review-2026-07-04 FIBR-0008 lane-1.
  Progress (2026-07-18): self-directed pick. Root cause confirmed — ofxparse 0.21 `parseOfxDateTime` returns `local_date - timeZoneOffset` (UTC), so a tz-bearing `<DTPOSTED>`/`<DTEND>` shifts the calendar day. Fix: a small `_LocalDateOfxParser(OfxParser)` subclass neutralises the printed `[offset:tz]` bracket to `[0:GMT]` and delegates to super, preserving the as-posted local date (the roadmap's decided semantic) for BOTH transaction dates and the DTSTART/DTEND span. Reuses ofxparse's own parsing (msec/null-date/custom-format). Reproduce-first TDD.
  Resolved (2026-07-18): SHIPPED. `_LocalDateOfxParser(OfxParser)` in `ofx_importer.py` overrides `parseOfxDateTime` to rewrite the printed `[offset:tz]` suffix to `[0:GMT]` before delegating to super, so ofxparse's UTC normalisation is a no-op and the as-posted local date is preserved for transaction dates AND the DTSTART/DTEND span (reuses the base parser's msec/null-date/custom-format handling; date-only values untouched). Reproduce-first TDD in `tests/features/ofx_import/` INV-11/11a/11b (negative-offset evening stays same day, month-boundary DTEND not extended into next month, positive-offset morning does not roll backward) — all fail pre-fix, green after. Self-review + full gate green 1107/1, mypy 0 (small fix; FIBR-0141/FIBR-0149 precedent — no full /indie-review). This also restores INV-6 cross-source dedup for shifted evening rows.

- ✅ [FIBR-0047] **Date pickers show unambiguous ISO YYYY/MM/DD, not the locale's M/D/YY.**
  Shipped 2026-07-04: setDisplayFormat("yyyy/MM/dd") on the main-window date field + the import wizard's period pickers; regression test in the vault suite. A user-CHOSEN format is the separate item below.
  **Layman:** Dates now always read year/month/day (e.g. 2026/07/04) so there's no US-vs-rest-of-world confusion.
  Kind: ux.
  Source: user-request-2026-07-04.

- ✅ [FIBR-0048] **User-configurable date-display format (Settings).**
  Belongs with FIBR-0014 (P12 Settings). The ISO yyyy/MM/dd default already shipped; this promotes it to a user choice persisted in the vault settings.
  **Layman:** Let the user pick how dates are shown (e.g. DD/MM/YYYY, YYYY-MM-DD) instead of the fixed ISO default.
  Kind: feature.
  Source: user-request-2026-07-04.
  Resolved (2026-07-11): subsumed by FIBR-0083, which shipped the user-configurable date-display format (plus timezone + time format) as its date half. No separate work remains.

- 📋 [FIBR-0049] **First-run onboarding / empty-state guidance on the home screen.**
  The home screen opens on the manual add-transaction form with cryptic fields (Amount, Description) and no guidance, which confused a real non-technical tester. Add empty-state help + inline field hints (Amount = money in/out, negative = out; Description = what it was for).
  **Layman:** A friendly welcome for a brand-new user — 'import a statement, or add a transaction by hand' — instead of a bare form.
  Kind: ux.
  Source: user-request-2026-07-04.
  Empty-state half delivered by FIBR-0051 (P07.5): the HomeView getting-started page is this bullet's "friendly welcome — import a statement or add a transaction". Remaining scope: the inline Amount/Description field hints on the manual-entry form (not in FIBR-0051). Stays open for those hints.

- ✅ [FIBR-0050] **Standard Bank (SA) statement text-parser — one reader for all account types.**
  Extends P07 (FIBR-0009). The generic ruled-table extractor
  mangles or misses several real Standard Bank layouts (the
  Current account collapses into one cell; the credit card's
  two-columns-per-line + gridline-less layout is unreadable). Add
  ONE Standard Bank text-layer reader (not per-account-type
  files) that parses the printed transaction lines and feeds the
  existing preview -> dedup -> commit pipeline; a recognised
  statement skips column-mapping (like OFX). Covers current,
  savings, home-loan, revolving-credit-loan, credit-card, and money-market/investment
  statements. Signed amount = the printed figure signed by the running-balance delta
  (unifies the families incl. the home loan, which prints no
  per-amount sign); credit card uses the Debit/Credits section
  rule (flip to purchases-negative budget view). Handles both
  number formats (US 1,427.41 and European 239.206,04 — the RCP
  loan), MM-DD dates with year inferred from the statement
  period, full-ISO dates (home loan), multi-line descriptions,
  per-page brought-forward continuation, and non-transaction row
  skipping. Correctness check: per-row balance-delta == printed amount (primary); additive opening balance + sum of parsed
  amounts == printed closing balance where the statement prints one (Savings has none). Loan-sign note: on a loan a
  fee shows positive (debt up) under the balance-delta rule — a
  user-facing loan-sign toggle is a possible follow-up. Fixtures
  100% SYNTHETIC (no real PII/ID/statements committed).
  Dependencies: FIBR-0009.
  Lanes: importers, ui, tests.
  **Layman:** Makes all your real Standard Bank statements — cheque, savings, home loan, personal loan, credit card and money-market — import cleanly, by teaching the app to read the printed statement lines the way you do.
  Kind: feature.
  Source: user-request-2026-07-05.
  Resolved (2026-07-05): shipped one Standard Bank text-layer reader (StandardBankImporter) for all six account types — current, savings, home loan, revolving-credit, credit card, money-market — family-dispatched inside one module. Validated end-to-end on all six real statements (checksums pass) + 13 synthetic fixtures. Spec cold-eyes-converged (9 loops); TDD (36 tests). Close: /audit clean; /indie-review (2 rounds, cold) — code findings (credit-card de-interleave HIGH, decrypt-crash net, INV-7b sign gate) + a confirming re-review round (1 HIGH corrupt-PDF Qt-slot crash, region-scoped number detection, Family-C continuation fold, _cc_opening sign, INV-12 test correction) all fixed inline; final cold pair clean. Gate green (277 passed/1 skipped, mypy 0). Fixtures 100% synthetic. Journal: docs/journal/FIBR-0050.md. Tag FIBR-0050-complete.</note>

  <invoke name="mcp__ants__changelog_log">
  /mnt/Games/Scripts/Linux/finbreak

- ✅ [FIBR-0059] **Edit a logged statement — re-assign its account (and its transactions) to fix an import mistake.**
  User request 2026-07-09: after importing an SBSA credit-card statement that got
  linked to "Current", the user wants to correct an already-logged statement's account
  in place. Scope: a "Change account" action on the Statements tab (FIBR-0052) that
  opens an account picker and atomically re-points BOTH statement_periods.account_id
  AND every linked transactions.account_id (WHERE statement_period_id = id) to the
  chosen account — one service-owned BEGIN…COMMIT (mirrors delete_statement's atomic
  pattern), leaving manual + other statements' rows untouched, ROLLBACK on failure.
  Refreshes the Statements list + Home + the status count (changed signal). The target
  account must exist (the user creates "Credit Card" in the Accounts tab first if
  needed). Also the tool that lets the user fix any statement mis-linked by FIBR-0057
  (the import account-snapshot bug). Deps: FIBR-0052 (Statements tab + provenance
  column). Next: spec -> /cold-eyes -> TDD -> /close-phase.
  **Layman:** Lets you correct a statement you already imported — e.g. change it from Current to Credit Card — without deleting and re-importing. It moves the statement and all of its transactions to the account you pick.
  Kind: feature.
  Source: user-request-2026-07-09.
  Resolved (2026-07-09): a "Change account" action on the Statements tab. StatementService.reassign_account(period_id, new_account_id) atomically re-points statement_periods.account_id AND every transaction stamped with it (one owned BEGIN…COMMIT mirroring delete_statement; ROLLBACK to a re-openable vault). A span-collision guard runs BEFORE BEGIN (pure read + refuse) with a period_id self-exclusion, so a same-account pick is the INV-5 no-op, not a false refusal; a real collision (target already has that span) raises ValueError → a tr() warning. A DISTINCT reassigned signal (the changed handler hard-codes "Statement deleted") drives a "Statement account changed" status via a shared refresh helper. New AccountPickerDialog (preselects the current account, deleteLater'd). StatementRow += account_id; repos get()/set_account()/reassign_account() (commit-free); no schema change (reuses the v6 provenance stamp). Spec /cold-eyes-converged in 6 cold loops (2 lanes = 12 reviews; design stable since loop 2). TDD 14 tests. Close: /audit 0; /indie-review 2 cold lanes — data/service CLEAN, UI/shell 1 LOW (undisposed picker dialog) folded inline. Gate green 366 passed/1 skipped; FIBR-0059 src mypy-clean. Also filed FIBR-0061 (mypy not enforced in the gate + 4 pre-existing test-file type errors, found during this close). Commits 2fc5a42 + review fold.

- 📋 [FIBR-0072] **Warn (or disable chrome) when navigating away from an in-progress import.**
  main_window._open_import() never disables the toolbar/menu, so clicking Home/Statements/Accounts/Categories/Rules mid-import silently rebuilds the workspace and destroys the in-progress wizard (chosen file, column mapping, unsaved preview) with no confirmation. Either confirm before discarding, or disable navigation chrome during an import (as locked states do).
  Kind: ux.
  Source: indie-review-2026-07-10 (M-shell1).
  **Layman:** Clicking away mid-import warns you first, instead of silently throwing away the file and column choices you just made.

- 📋 [FIBR-0073] **Add keyboard mnemonics to menus + dialog labels (a11y sweep).**
  Menu titles (File/View/Window/Help/Donate) have no '&' Alt-accelerators; no dialog uses label mnemonics. Weakens keyboard-only navigation vs a typical desktop app (WCAG-adjacent). One focused sweep across main_window + the dialogs.
  Kind: accessibility.
  Source: indie-review-2026-07-10 (shell L1 + dialog INFO).
  **Layman:** Menus and dialog fields get Alt-key shortcuts, so the app can be driven from the keyboard like any other desktop program.

- 📋 [FIBR-0074] **Dedicated per-bank PDF readers for ABSA / Nedbank / FNB (needs real anonymised sample statements).**
  Today ABSA/Nedbank/FNB statements CAN already be imported two ways: (1) their CSV/OFX exports (most reliable), and (2) the generic PDF table-extractor (pdf_importer.py) for any PDF with ruled transaction tables, via the column-mapping step. A DEDICATED zero-config text-layer reader like standard_bank.py (auto-detect + no mapping) needs REAL anonymised sample statements per bank to build and validate — the SB reader (FIBR-0050) required 6 real statements to catch layout edge cases; synthetic dummy PDFs exercise code paths but don't validate real-world layouts. Blocked on the user providing (or the project sourcing) a few real anonymised statements per bank. Until then, the generic extractor + CSV/OFX cover these banks.
  **Layman:** Zero-config PDF import for the other big SA banks, the way Standard Bank statements already import without mapping columns.
  Kind: feature.
  Source: user-request-2026-07-10.

- ✅ [FIBR-0083] **User-configurable timezone + date/time display format (Settings).**
  Motivated by dogfooding v0.1.0: the Statements tab 'Imported' column shows a raw ISO UTC timestamp (e.g. 2026-07-11T06:49:15.506928+00:00). Extends FIBR-0048 (user-chosen DATE-display format) to also cover the user's TIME ZONE and TIME-of-day format, so any timestamp renders in the user's zone + preferred format. Belongs with FIBR-0014 / FIBR-0055 Settings; the prefs persist in the vault settings (like the auto-lock timeout). Render via QDateTime + QTimeZone + QLocale (coding.md 5.2), consistent with FIBR-0017 QLocale formatting. Ships together with / absorbs FIBR-0048 (date half).
  **Layman:** Let a person pick their time zone and how dates and times are shown, so timestamps (like a statement's 'Imported' time) read in their local time and chosen format instead of a raw UTC value.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Resolved (2026-07-11): shipped via TDD in 4 slices — pure datetime_format formatter (format_date/format_timestamp, presets, "system" sentinel + INV-6 fallbacks); DateTimePrefs + AuthService persistence (vault settings, no schema change); Settings + first-run combos (shared ui/_datetime_prefs.py); display wiring (Statements Period/Imported, Home Date) + live push on Settings Save. 8 cold-eyes loops on the spec; full gate green.

- ✅ [FIBR-0084] **User-customisable table columns — resize, reorder, and remember per tab.**
  Motivated by dogfooding v0.1.0. Extends FIBR-0052 (which already remembers window geometry + last-active tab in the plaintext window.ini sibling) to per-table column state. Make each QTableView/QTreeView header user-resizable AND movable (QHeaderView.setSectionsMovable(True)); persist each table's full header state (column widths + order) via QHeaderView.saveState()/restoreState(), keyed per tab, in the plaintext window.ini (non-sensitive UI state, like geometry — FIBR-0052 INV-5; NOT the vault). Covers every relevant table: Statements, Home transactions, Accounts, Categories, Rules. A Reset-layout action (FIBR-0052) should also clear saved column state.
  **Layman:** Let a person drag columns wider or narrower and drag them into a different order on any table (Statements, Home, Accounts, Categories, Rules), and have finbreak remember that layout next time.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Scope re-checked 2026-07-28 — mostly already shipped, folded into
  FIBR-0113. Everything this bullet asks for exists: ui/_table_state.py's
  remember_columns() sets setSectionsMovable(True), restores
  QHeaderView.saveState()/restoreState() from the plaintext window INI
  (paths.window_settings_path, NOT the vault — the FIBR-0052 INV-5 rule
  this bullet names), keyed per table by objectName, and re-saves on
  resize / reorder / re-sort. The Reset-layout action this bullet also
  asks for is main_window._reset_layout (menu action
  "action_reset_layout"), but it does NOT clear saved column state — see the 2026-07-28 correction below. Shipped as
  FIBR-0117 with the reorder half added by FIBR-0012, and most recently
  extended to the import-wizard preview table.
  Correction + re-scope (2026-07-28, /cold-eyes on docs/specs/FIBR-0113.md).
  The 2026-07-28 note above was written from recall and was WRONG twice; both
  claims are now corrected against source:

  - "The Reset-layout action this bullet also asks for is
  main_window._reset_layout": the action exists, but _reset_layout removes
  exactly _KEY_GEOMETRY, _KEY_STATE and _KEY_SIZE. It never touches the
  "columns/<objectName>" entries remember_columns writes, so saved column
  state survives a Reset layout. What this bullet asks for is NOT done.
  - "this bullet's residue is exactly FIBR-0113's table conversion": false.
  Two further surfaces have no column persistence at all —
  ui/forecast.py's 4-column events table (objectName already
  "forecast_events"; forecast.py imports nothing from _table_state) and
  ui/home.py's dashboard breakdown trees (QTreeWidget, setColumnCount(2),
  a VISIBLE Name/Amount header, objectName "dashboard_breakdown_<key>";
  home.py likewise imports nothing from _table_state). This bullet's own
  text names both classes — "each QTableView/QTreeView header" and "Home
  transactions" — so they are in scope by its own wording (user confirmed
  2026-07-28).

  Re-scoped accordingly: FIBR-0113 delivers ONLY the Accounts table (it was
  carrying the rest, and a cold-eyes loop showed that fold-in was the largest
  single source of defects in that spec). The remaining three gaps are now
  FIBR-0192, which is the blocker for this bullet's ✅.

  So: do NOT flip this bullet when FIBR-0113 ships. Flip it when FIBR-0192
  ships. Categories stays deliberately out of scope (single column under
  setHeaderHidden(True) — nothing to resize or reorder).

  Call sites today: statements, transactions, rules, recurring, transfers,
  import_wizard. Accounts is genuinely missing (still a QListWidget with no
  header at all) and making it a table is FIBR-0113; Categories is
  deliberately out of scope, not an omission. But those two are NOT the
  whole residue — see the correction above: Forecast, the Home dashboard
  trees and Reset layout remain, and they are FIBR-0192's.
  Resolved (2026-08-02): unblocked by FIBR-0192, which was this bullet's stated blocker. Every table and tree the app shows now resizes, drag-reorders and remembers its layout per tab — the Forecast events table and the three Home breakdown trees were the last two unwired surfaces, and Window → Reset layout now returns them all to their build-time defaults in the same click.

- ✅ [FIBR-0085] **Batch statement import — import several statement files in one go.**
  Motivated by dogfooding v0.1.0. Today the import wizard handles ONE file per run (FIBR-0007 CSV / FIBR-0008 OFX / FIBR-0009 PDF). Add multi-file selection that runs each file through the existing preview -> dedup -> commit pipeline, with per-file semantics (a bad/duplicate file is reported and skipped, never aborting the batch) and a summary dialog listing each file's outcome (imported N / skipped-duplicate / failed-why) + transaction counts. Mixed formats (CSV/OFX/PDF) allowed in one batch; per-file mapping where the format needs it (CSV mapping profile selection, PDF password prompt). Reuses the existing importers + FIBR-0052 statement provenance; the new work is the multi-file wizard flow + aggregate reporting. Deps: FIBR-0007/0008/0009 (importers), FIBR-0052 (per-statement provenance so each imported file is a distinct statement row).
  **Layman:** Let a person select and import many statement files at once (e.g. a whole folder of monthly PDFs) instead of importing them one at a time.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Priority (2026-08-05, user): named as the most useful feature to
  build after FIBR-0231 — take this next unless redirected.
  Priority (2026-08-06, user directive): this is the NEXT item after
  FIBR-0231 closes. Named by the user in the FIBR-0231 handoff session;
  recorded here because it lived only in that conversation.
  Sequencing DECIDED (2026-08-06, user directive): FIBR-0086
  (account-number auto-detect) is built FIRST, and this item follows it.
  Claude recommended the reverse (batch import with one user-picked
  account for the whole batch, auto-detect as a follow-up); the user
  chose to build the enabler first so batch import can auto-file each
  file from the moment it ships. This bullet is therefore BLOCKED on
  FIBR-0086, not merely helped by it.
  Design DECIDED (2026-08-06, user): per-file extra input (PDF password,
  CSV mapping choice) is collected UP FRONT — scan the selected files,
  ask for everything needed in one pass, then run the batch unattended
  to the end. Rejected: pausing at each file as it is reached (forces
  the user to babysit a 30-file import, defeating the purpose), and
  skipping files that need input (a folder of password-locked bank PDFs
  is the common case, not an edge case).
  Spec written and gated (2026-08-06):
  `docs/specs/FIBR-0085-batch-statement-import.md`, status accepted.
  Cold-eyes: 3 loops x 3 lanes = 9 reviews. 95 findings verified and
  fixed, 2 dismissed. Severity by loop: C3/H8/M13/L11, C2/H8/M10/L8,
  C1/H8/M14/L10.
  STOPPED AT LOOP 3 by user decision, NOT converged clean. Loops 2 and 3
  were both dominated by collateral from the previous loop's own fixes,
  which is the documented signal to stop dispatching. The spec is
  implementable and internally consistent; it has not had a zero-finding
  cold pass.
  Five defects found that no reading caught, all silent-data-loss:
  (1) the review table's Duplicate column stayed non-cumulative while New
  went cumulative, so the approval screen's numbers would not account for
  a file's rows; (2) `already_imported` was a declared outcome no pass
  ever assigned; (3) a multi-statement OFX had no place in a
  one-record-per-file model, so every statement after the first would be
  discarded without a word; (4) the ready/already_imported flip was
  one-directional, so a retargeted record could never be committed; and
  (5) reusing the wizard's map step inherits a Cancel wired to `done`, so
  declining one mapping would have torn down a thirty-file batch.
  Two user decisions recorded in the spec's §3: one combined review
  screen before anything commits, and `already imported` reported from
  the existing period-span match rather than a content hash (FIBR-0088
  keeps that upgrade and its migration).
  Design decisions taken during review: ASK carries only passwords and
  mappings (they block the parse) while the account question is settled
  on the review screen, per the mock-up the user approved; one file
  selected still routes to the unchanged single-file flow; the batch runs
  as a QTimer.singleShot(0, self, ...) chain rather than a QThread,
  because import stays on the GUI thread per design.md.
  Next: step 3, TDD against `tests/features/batch_import/`.
  Resolved (2026-08-06): shipped. `services/batch_import.py` (headless:
  the scan ladder, the stored-password ladder, `cumulative_counts`, the
  two caps, the per-file run step), `ui/import_batch.py` (the review
  table), `importers/sniff.py` (format detection lifted off the wizard so
  the service could stay Qt-free), a fourth wizard step + the
  scan/ask/run chain, and a Create affordance on the account picker.
  TDD, 20 tests across a headless and a qtbot file, 13 mutation checks.
  Close ran three cold review lanes: static layer clean (gate + semgrep
  0), but the lanes found a CRITICAL two of them raised independently —
  `Import all` went live mid-SCAN, so a RUN chain could be armed
  alongside the SCAN chain and files were silently skipped by both — plus
  a HIGH (the 200-file cap was decorative: refused files were read
  anyway), a sign-flipping money bug in the reused mapping form, and a
  VACUOUS INV-3 test of my own that passed against the exact
  implementation the spec names as the break. All fixed with regression
  tests. FIBR-0252 filed for a pre-existing Standard Bank defect the new
  Errors column surfaced. As-built deviations recorded in the spec's new
  §14.

- ✅ [FIBR-0086] **Account numbers + import auto-detect — match a statement to its account (prompt to create if new).**
  Motivated by dogfooding v0.1.0. The account-number STORAGE half shipped separately as FIBR-0193 (2026-07-30): `accounts.account_number` is a nullable column in the ENCRYPTED vault, added by schema migration **v12 -> v13** — so this bullet is now DETECTION + MATCHING only, and no new column is needed. On import, extract the statement's account number and match it to a configured account (normalised: strip spaces/dashes; match on TRAILING digits when the statement masks it, e.g. "xxxx1234"), auto-selecting the account instead of today's manual pick. Availability varies by format: OFX <ACCTID> (reliable), PDF printed number (the Standard Bank / generic parsers can surface it), CSV often carries none — so auto-detect is a SMART DEFAULT with a manual fallback whenever the number is absent or matches zero/multiple accounts (never silently import to the wrong account — cf. FIBR-0059). When the detected number matches no account, prompt to create one, pre-filled from statement metadata (number, bank name if printed, type/currency where available) and asking the user for the rest. ENABLER for FIBR-0085 (batch import) — auto-detect is what makes multi-file import usable (you cannot hand-map a folder of files); reduces reliance on FIBR-0059 (change-account fix). Deps: FIBR-0005 (accounts), FIBR-0007/0008/0009 (importers must surface the statement's number), FIBR-0052 (statement provenance).
  **Layman:** Give each account its account number so importing a statement automatically files it under the right account — and if it's an account finbreak hasn't seen, it offers to create it, pre-filled from the statement.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Promoted to ACTIVE ITEM (2026-08-06, user directive): built BEFORE
  FIBR-0085 (batch statement import), which is now blocked on it. The
  user chose to build this enabler first so batch import can auto-file
  each statement to its account from the moment it ships, rather than
  shipping batch import with a single user-picked account for the whole
  batch and retrofitting detection later.
  Spec written and gated (2026-08-06):
  `docs/specs/FIBR-0086-account-number-auto-detect.md`. Grounded in the
  user's real 48-statement SBSA corpus, measured in scratchpad only —
  every number in the spec is a synthetic stand-in preserving the
  structural relationships (INV-8).
  Cold-eyes: 3 loops x 3 lanes = 9 reviews. 62 findings verified and
  fixed, 3 dismissed. Severity by loop: C3/H5/M6/L7, C3/H6/M5/L10,
  C2/H4/M3/L8. Two design bugs found that no reading caught: (1) the
  draft's UI ordering would have COMMITTED the import to the old account
  while displaying the matched one (QSignalBlocker suppresses the only
  caller of ImportService.retarget); (2) normalise_account_number
  ("xxxx1234") -> "1234", so masked ids could match a real account,
  silently implementing the trailing-digit matching the spec had
  explicitly declined. Two lane CRITICALs were REFUTED by running them
  rather than reading them.
  STOPPED AT LOOP 3, not converged-clean: loops 2 and 3 were both
  dominated by collateral from the previous loop's own fixes (9 and 15
  vs 2 draft defects each), which is the signal to stop dispatching and
  sweep instead. The spec is implementable and internally consistent;
  it has not had a zero-finding cold pass. Deferred: FIBR-0240 (card
  auto-detect), FIBR-0241 (masked matching), FIBR-0242 (Family E),
  FIBR-0243 (OFX account type).
  Progress (2026-08-06): TDD done and pushed (`73f3e71`). Extraction,
  normalisation, the matching ladder, the wizard wiring and the
  create-from-statement dialog all land; 32 new tests, gate green
  1823 passed / 3 skipped against a 1791 baseline, so no existing test
  moved (INV-6 holds).
  Three spec claims were verified rather than taken on trust. The
  family-C guard sits in the extractor, and its red state was constructed
  per §7 — the generic extractor was written first and watched to read the
  debit-order account. The capture class was likewise built greedy first
  and watched to swallow the following date column. And the §4.5 ordering
  was checked by reversing it: INV-7a goes red while INV-7 stays green,
  confirming INV-7a is the only thing standing between the design and a
  wrong-account commit.
  One thing the spec did not anticipate: §4.6's create path needed a NEW
  dialog. There was no reusable account-create UI — accounts could only be
  made from the Accounts tab's inline form — so `ui/account_create.py` is a
  small addition beyond the spec's file list. It takes the mirror of §4.5's
  rule: the preview already exists when Create is pressed, so the combo
  update is deliberately NOT blocked, because the signal is what retargets
  the preview.
  INV-8's test now exists and normalises the haystack, so it catches a
  spaced spelling a substring grep would miss. Run against the real corpus
  over all 506 tracked files: clean.
  Next: steps 5-9 via `/close-phase`.
  Resolved (2026-08-06): shipped. Journal: docs/journal/FIBR-0086.md.
  Closed after three cold review lanes over the code. No CRITICALs — the
  §4.5 ordering and the family-C guard both survived mutation — but one
  real wrong-account bug and four unlocked test paths, all fixed in
  `fe8e872`. The bug: a multi-statement OFX inherited the previous
  statement's match, because on a non-matched outcome "leave the combo
  alone" only equals "the pick step's account" on the FIRST statement.
  Worst on no_number, where the blank label made an app-made guess look
  like the user's own pick. Also fixed: a manual override left the
  "Matched account number …" label live on the final irreversible screen;
  the mask guard was one-sided (statement checked, stored number not) and
  a three-character denylist that #### and "ending 1234" walked straight
  through; and the post-create label promised auto-filing for an account
  stored with no number.
  The unlocked paths matter as much. INV-2's own named test could not
  fail — its foreign number sat in a row with no label, and the extractor
  is label-anchored. INV-7a was locked on OFX only, though families A/B/D
  are PDF-only. Nothing asserted the explanation is ever shown. Family D,
  the only family printing the "Account number:" spelling, had no test.
  Every fix was mutation-tested: revert it, exactly one test reddens.
  Gate green 1840 passed / 3 skipped against a 1791 baseline.
  Deferred with evidence: FIBR-0247 (the INV-8 scanner cannot see git
  history, so a redaction reads as a fix), FIBR-0248 (its env var is wired
  nowhere, so it skips every run), FIBR-0249 (remembered PDF password
  keyed to the pick-step account), FIBR-0250 (ASCII-only zero-strip).
  Unblocks FIBR-0085 (batch import).

- 📋 [FIBR-0087] **Per-account currency — support offshore/foreign-currency accounts in the portfolio (revisits FIBR-0021).**
  The user wants to include an offshore account in their portfolio — the "real multi-currency need" FIBR-0021 deferred to (it chose single base_currency for v1, set at first-run, and said revisit when this arises). Per FIBR-0021's own "if revisited" note: add a currency column on accounts (default = the vault base currency), CHOOSE the currency when ADDING an account (the user's ask), QLocale-format each amount in its account's currency, and enforce that the dashboard NEVER sums across currencies without explicit conversion. Needs its OWN design/spec — the hard decisions: (a) consolidated totals across currencies — NO live FX rates (that would widen the network surface beyond the one FIBR-0054 update egress), so either per-currency subtotals or a user-entered/stored conversion rate; (b) how the dashboard presents mixed currencies (per-currency subtotals vs one converted total). Schema migration (currently v7 -> v8). Deps: FIBR-0005 (accounts), FIBR-0012 (dashboard totals). Kept SEPARATE from FIBR-0083 (date/time formatting).
  **Layman:** Let each account have its own currency (e.g. a USD offshore account alongside your ZAR accounts), chosen when you create the account, so foreign accounts show and total correctly.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Consolidation design (proposed direction, user Q 2026-07-11 "how do mixed-currency statements consolidate into graphs/summaries?"): NO live FX rates (offline posture — only the FIBR-0054 updater egress). Default = per-currency subtotals: the dashboard shows each currency separately (ZAR panel, USD panel), NEVER summing across currencies (upholds FIBR-0021's rule). PLUS an optional USER-ENTERED exchange rate (stored in the vault) that converts everything to the base currency for a single consolidated total + unified graphs, always LABELLED "converted at your rate, entered <date>" so it's never mistaken for a live figure; user updates it at will. Warrants a small ADR ("how finbreak handles FX") when built. Rejected: live-rate fetch (breaks offline).

- 📋 [FIBR-0088] **Detect an already-imported statement up front (content hash) — warn before re-importing.**
  User wants an early 'already imported?' check that short-circuits BEFORE the per-transaction dedup (saving redundant work). Partly plumbed already: statements store source_filename and statement_periods has id_for_span (account+period existence check). Robust key = a CONTENT HASH (SHA-256 of the file bytes): detects a re-import of the IDENTICAL file regardless of filename — filename alone is unreliable (same file renamed; or two different files both named 'statement.pdf'). Add a file_hash column (schema migration, currently v7), compute it at import start, and if it matches a prior import WARN the user with an import-anyway option (a corrected re-issue is a legit re-import) rather than silently skipping. The existing account+period match (id_for_span) is a softer secondary signal. COMPLEMENTS, not replaces, transaction dedup (INV-6), which still catches overlapping-but-different files. Primarily a UX safeguard against accidental re-import; the CPU saving is a bonus. Also gives FIBR-0085 (batch import) its per-file 'already imported -> skipped' outcome. Deps: FIBR-0007/0008/0009 (importers), FIBR-0052 (statement provenance).
  **Layman:** When you import a statement finbreak has already seen, it tells you up front ('looks like you already imported this') instead of silently re-processing it.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).

- 📋 [FIBR-0089] **Backup safety nudge — first-run emphasis + a 'last backup was N days ago' reminder.**
  The encrypted-backup MECHANISM is planned in FIBR-0014; this is the SAFETY UX around it. ADR-0003: no password recovery = permanent data loss, so a backup is the only mitigation. Add (a) first-run copy stressing 'back this up somewhere safe', and (b) a gentle, non-blocking reminder when the last backup (tracked via a vault-settings timestamp) is older than a threshold. Depends on / complements FIBR-0014 (the export itself). Highest-value safety improvement per the 2026-07-11 review.
  **Layman:** Because a forgotten master password means your data is gone for good, finbreak reminds you to keep a backup — stressed at first run and gently nudged if it's been a while.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0090] **Split a transaction across multiple categories.**
  A personal-finance staple. One transaction carries N category allocations summing to its amount. Affects the categorization model (per-transaction allocations, not a single category_id) and the dashboard totals (aggregate by allocation, not whole-transaction). Schema change (an allocations/splits table). Deps: FIBR-0006 (categories), FIBR-0010 (categorization), FIBR-0012 (dashboard totals must respect splits). Own spec.
  **Layman:** Split one purchase across categories — e.g. a R1,200 shop = R900 groceries + R300 household — so your breakdowns are accurate.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0091] **Free-text notes + tags on transactions.**
  A free-text note and/or tags (labels) per transaction, orthogonal to the category tree. Enables richer filtering/reporting in the dashboard's filterable table (FIBR-0012). Schema: a note column + a tags table (many-to-many). Deps: FIBR-0012 (filters), FIBR-0052 (transactions). Own spec.
  **Layman:** Attach a note or tag ('reimbursable', 'holiday 2026') to a transaction for context the category tree can't hold, and to filter/report on.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0092] **Rule preview (what will it match?) + bulk re-categorize selected transactions.**
  Enhances FIBR-0010's rules engine + the categorization UX. (a) Rule preview: on rule create/edit, show the matching transactions (the would_categorize primitive already exists, FIBR-0010) before commit. (b) Bulk action: multi-select rows in the Home/transactions table -> set category (and optionally offer to make a rule). Pairs with FIBR-0084 (column/row UX) and FIBR-0012 (filterable table). Deps: FIBR-0010. Mostly UI + reuse of existing services.
  **Layman:** When you write a categorisation rule, see which transactions it'll catch before saving; and select many rows to set their category at once.
  Kind: enhancement.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0093] **Plain data export — CSV / spreadsheet of your categorised transactions.**
  A 'File -> Export data' that writes the (filtered) transactions — date, amount, description, account, category, notes/tags — to CSV (and optionally XLSX). Complements the report-style PDF export (FIBR-0013): this is RAW DATA for spreadsheets, not a formatted report. Local file write, no network (offline posture holds). Deps: FIBR-0007/0008/0009 (the data), FIBR-0012 (filters define the export scope). Own small spec.
  **Layman:** Export your categorised transactions to a CSV/spreadsheet for your own analysis or your accountant.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0094] **Account balances + net-worth over time (opening balance + running balance).**
  Today finbreak tracks TRANSACTIONS, not balances. Add a per-account opening balance (+ as-of date); derive a running balance per transaction; surface an account-balance and consolidated net-worth trend on the dashboard. Interacts with FIBR-0011 (transfers — moving money between your own accounts must not change net worth) and FIBR-0087 (multi-currency net worth needs the FX decision). Schema: opening_balance on accounts. Deps: FIBR-0011, FIBR-0012, FIBR-0087. Bigger; own spec + likely an ADR on balance derivation.
  **Layman:** Track each account's balance over time — set an opening balance and finbreak shows running balances and your overall net-worth trend, beyond just spending-by-category.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0100] **Undo for destructive actions (delete statement / delete category).**
  Today destructive actions are confirm-only (Statements delete with its transactions, FIBR-0052; category delete-cascade, FIBR-0010). Add a short-lived undo — a status-bar 'Deleted — Undo' for a few seconds, or Edit -> Undo — that restores the deleted rows within the same session. Friendlier than confirm-only; reduces fear of the delete buttons. Design: soft-delete or an in-memory undo stack + a re-insert. Deps: FIBR-0052, FIBR-0010.
  **Layman:** An 'undo' right after deleting a statement or category, so a misclick isn't permanent.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0101] **Keyboard-first categorising — shortcuts for fast triage of a big import.**
  Add keyboard shortcuts to the transaction table: set-category (opens the picker), jump-to-next-uncategorised, and quick-assign recent categories. Speeds triaging a large import. Pairs with FIBR-0092 (bulk re-categorize) and FIBR-0010 (rules); cleaner once FIBR-0097 (model/view) lands. Mostly UI. Deps: FIBR-0010.
  **Layman:** Categorise a large import quickly with the keyboard — set a category and jump to the next one without reaching for the mouse.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- ✅ [FIBR-0105] **User-configurable amount display: negative sign style + colour (Settings).**
  Two independent prefs persisted in the vault settings (mirrors FIBR-0083
  DateTimePrefs / FIBR-0055 auto-lock): (1) negative-amount style — "minus"
  (−ZAR25,000.00) vs "brackets" ((ZAR25,000.00), today's QLocale default); (2)
  colour amounts on/off — money-out red, money-in green. Settings + first-run
  controls; applied at the Home transactions table's Amount column (the only
  amount display today). Default: minus + colour ON. Display-only (never mutates
  stored data). Ships in v0.1.5 alongside the inline update notes.
  **Layman:** Let a person choose how money amounts look — negatives as a minus sign (−R25) or in brackets (R25), and turn on/off colouring money-out red and money-in green — so the transaction list reads the way they prefer.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.4: "why are some values in brackets?" → make it a Settings choice).
  Resolved (2026-07-11): TDD-built in 4 slices — AmountPrefs + AuthService.amount_prefs/set_amount_prefs (INV-2/5); _format_amount explicit sign (- / ()) locale-independent + _NEGATIVE_TEXT/_POSITIVE_TEXT colour in HomeView (INV-1/3/4); Settings combo + colour checkbox and first-run mirror (INV-6/7); shell reads/passes/re-pushes on Save. 19 new tests; full gate green (598 passed). Lands on main; publishes in v0.1.5 (bundled with the inline update notes).

- ✅ [FIBR-0106] **Credit-card (Family C) import: opening balance mis-read from a prose "brought forward" decoy line.**
  Root-caused (verified against a real SBSA CC statement, synthetic fixture to
  follow — real file/password never committed). `_cc_opening` (standard_bank.py
  :812) returns the LAST money token on the FIRST line containing "balance
  brought forward". A credit-in-hand statement prints a prose summary line
  "...has a credit balance. Balance brought forward on this statement -251.85"
  BEFORE the real opening line "21 Jul 25 Balance Brought Forward 6,849.68", so
  it grabs -251.85 (which is actually the CLOSING balance carried to the next
  statement). Checksum then fails: reconciled = opening - Σ = -251.85 - 7101.53
  vs closing -251.85. With the correct opening 6,849.68 it reconciles exactly
  (6849.68 - 7101.53 = -251.85 = closing). Fix: anchor the match so the phrase
  is at line start (optionally after a `DD Mon YY` date) with the amount
  immediately after — the prose sentence won't match. TDD with a synthetic
  fixture carrying the decoy line + a real opening + a reconciling body.
  **Layman:** A real Standard Bank credit-card statement refused to import ("didn't add up") because the importer read the wrong opening balance.
  Kind: fix.
  Source: dogfooding-2026-07-11.
  Resolved (2026-07-11): anchored _cc_opening on a new _CC_BROUGHT_FORWARD regex requiring a money amount to IMMEDIATELY follow the "balance brought forward" phrase (optional -/R sign), and take the first money token in the tail from the phrase onward. The prose decoy ("...credit balance. Balance brought forward on this statement -251.85") has narrative text between phrase and figure, so it no longer matches; the real anchor "21 Jul 25 Balance Brought Forward 6,849.68" does. TDD: 2 pure unit tests (decoy-rejection + printed-negative-sign preservation) in tests/features/standard_bank_pdf; full SB suite (50) green, no regression on the 6 validated real statements. Gate green (600 passed/1 skipped). Synthetic figures only — real file/password never touched disk.

- ✅ [FIBR-0107] **Self-update relaunch: wait for the old AppImage to exit before launching the new one.**
  The 0.1.4→0.1.5 relaunch (detached Popen + PYINSTALLER_RESET_ENVIRONMENT, then immediate os._exit) still raced the old AppImage's teardown: the fresh onefile bootloader started while the old image's FUSE mount + _MEI extraction dir were still live and died ("closed but didn't reopen"). Fix (update_installer.py): spawn a detached /bin/sh WAITER (new session) that polls `kill -0 <old-pid>` until this process has fully exited — FUSE unmounted, _MEI cleaned — and only THEN execs the swapped image with the reset env. Hard ~60s cap (600 × 0.1s) so a wedged old process can never hang the relaunch. Same pattern robust self-relaunching Qt AppImages (RPCS3, PCSX2) use. Added a diagnostic relaunch log (data-dir sibling of the vault) capturing the waiter's + relaunched image's output so a future silent failure leaves evidence. TDD: pure _relaunch_command builder test (waits on pid, quoted exec after the loop), detached-session/env test updated to the waiter contract, log-write test; plus a real-process smoke proving the waiter blocks until the old pid dies then execs. Gate green (602 passed/1 skipped). NOTE (two-cycle trap): this code ships in 0.1.6 but only RUNS on the 0.1.6→next update — 0.1.5→0.1.6 still relaunches via the old 0.1.5 logic, so one manual reopen is still expected for that hop.
  **Layman:** After an update the app closed but didn't reopen; now it reliably restarts itself.
  Kind: fix.
  Source: dogfooding-2026-07-11.

- ✅ [FIBR-0108] **Update download: show real progress instead of a permanently-full indeterminate bar.**
  The "Downloading…" bar in the update dialog is hardcoded to indeterminate (busy) mode — ui/update_dialog.py:79 `self._busy.setRange(0, 0)` — so it shows a moving/striped full bar the entire download rather than actual percent-complete. The fix is feasible without new deps: services/update_fetch.py `download()` already streams the body in 64 KiB chunks (`_DOWNLOAD_CHUNK_BYTES`, line 89), so it can (a) read the total from the response `Content-Length` header and (b) accept an optional progress callback invoked per chunk with (received, total). Then the DownloadWorker (ui/_update_worker.py) emits a progress signal and the dialog switches the bar to determinate (`setRange(0, total)` + `setValue(received)`), falling back to indeterminate only when Content-Length is absent/zero. Keep the byte-cap (max_bytes) guard intact. TDD: unit-test the callback fires with monotonic received ≤ total and a missing-Content-Length fallback; a qtbot test that the bar goes determinate on a known-size download. Kind: enhancement.
  **Layman:** While an update downloads, the progress bar looks full/striped the whole time instead of filling up as it downloads.
  Kind: enhancement.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-28): update_fetch.download takes an optional per-chunk on_progress callback reporting (received, total) with total from Content-Length (0 when absent/malformed); UpdateService passes it to the asset download only, DownloadWorker relays it as a Qt signal, and UpdateDialog.set_progress switches the bar to determinate — an unsized download keeps the indeterminate look. INV-10 byte cap untouched. Tests: test_FIBR0108_download_reports_progress_against_content_length, _absent_or_malformed_content_length_reports_unknown_total, _download_worker_relays_progress, _prompt_bar_goes_determinate_on_a_known_size, _prompt_bar_stays_indeterminate_when_size_unknown.

- ✅ [FIBR-0109] **Move the Home transaction list to a dedicated Transactions tab with account / date-range / amount-range filters.**
  User request 2026-07-12. Today Home is the transaction table (HomeView). Move that table to its own Transactions tab and add filters: by account, by date range (from/to), and/or by amount range (min/max), combinable. This dovetails with FIBR-0012 (the dashboard's "filterable table" + Home-as-summary vision) and complements FIBR-0011 (a confirmed-transfer marker could later show here). Reuses the existing list_transactions read; the filter is a query/where layer. Dates in the filter follow the typed-or-picker rule below.
  **Layman:** Give the transaction list its own tab with filters for account, date range and amount, so the Home tab is freed to become a summary/dashboard.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Absorbed into FIBR-0012 (P10 dashboard) 2026-07-12: the Transactions tab is built there with search + date-range + account + category filters (all combinable). The amount-range (min/max) filter this bullet originally named was NOT chosen in the FIBR-0012 brainstorm and is DEFERRED (recorded in docs/specs/FIBR-0012.md Out-of-scope) — a clean future follow-up. Close this bullet when FIBR-0012 ships; re-open a fresh item only if the amount-range filter is still wanted.
  Resolved (2026-07-28): closed as covered by its absorb target. FIBR-0012
  (P10 dashboard) is ✅ and shipped the dedicated Transactions tab
  (src/finbreak/ui/transactions.py) with search + date-range + account +
  category filters, all combinable — which is what this bullet asked for
  minus one piece. The amount-range (min/max) filter the 2026-07-12 absorb
  note explicitly DEFERRED is still wanted, and is re-filed as its own
  item rather than kept alive here.

- 📋 [FIBR-0110] **Every date input accepts typed entry (validated) or a date picker.**
  User request 2026-07-12. Cross-cutting UX: wherever a date is entered — the manual-entry dialog, the future Transactions filters (above), any settings/import date field — offer both a typed field (ISO-validated, the existing parse_transaction date check) and a QDateEdit-style calendar picker, so neither typists nor mouse users are forced. A shared date-input widget/helper so the two modes stay consistent (Rule-of-Three: extract on the third site).
  **Layman:** Anywhere you enter a date in the app, you can either type it (with a check that it's a real date) or pick it from a small calendar.
  Kind: ux.
  Lanes: ui.
  Source: user-request-2026-07-12.

- 📋 [FIBR-0111] **Show the currency in its own column, separate from the amount value.**
  User request 2026-07-12 (screenshot): the Home Amount column renders "ZAR69.00" / "-ZAR25,000.00" with the currency crammed against the number, hard to read. Give the currency its own column (or right-align the bare number and show the currency code separately), so the value column holds just the formatted number + sign. Touches HomeView._format_amount / the Amount column layout (FIBR-0105 amount-display work) and should carry through to the future dedicated Transactions tab (FIBR-0109). Keep the negative-style (minus/brackets) + red/green colour prefs (FIBR-0105) working on the value column.
  **Layman:** Put the currency code (e.g. ZAR) in its own column so the number is easy to read, instead of "ZAR69.00" crammed together.
  Kind: ux.
  Lanes: ui.
  Source: user-request-2026-07-12.

- ✅ [FIBR-0112] **Credit-card (Family C) import: continuation page without a column header drops its transactions.**
  Root-caused against a real SBSA CC statement (2025-10-20; real file/password never committed, synthetic fixture/tests to follow). A 3-page statement: page 1 = summary, page 2 = transaction table WITH the "Date Description Amount" column header, page 3 = continuation transactions with NO column header (opens straight into a "Debit Debit" section). _table_region (standard_bank.py:229) locates the Family-C region only by that column header, so page 3's region is empty and its 3 transactions (Checkers 514.21 + Cash Finance Charge 23.05 + Tips 10.00 = 547.26) are silently dropped. The completeness checksum then fails (opening 1348.95 - Σ = 1421.51 vs closing 1968.77; the 547.26 gap is exactly the dropped rows) and the whole statement is refused. Fix: when a Family-C page has no column header, fall back to starting the region at the first real transaction row (a CC segment ending in a 2-decimal amount) — which excludes summary-page date spans like "Statement Period 20 Sep 25 to 20 Oct 25" that carry no 2-decimal tail. TDD: pure _table_region unit tests (header-less continuation page captured; header-less summary page stays empty) + reconciliation; validated end-to-end against the real statement in a throwaway scratchpad.
  **Layman:** Another real Standard Bank credit-card statement refused to import ("didn't add up") because the last page's transactions were being skipped.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): _table_region now falls back, on a Family-C page with no "Date Description Amount" column header, to starting the region at the first real transaction row (a CC segment ending in a 2-decimal amount — which excludes summary-page date spans like "Statement Period 20 Sep 25 to 20 Oct 25"). TDD: 2 pure _table_region unit tests (header-less continuation page captured; header-less summary page stays empty). Validated end-to-end on the real SBSA 2025-10-20 statement in a throwaway scratchpad: now 72 drafts, reconciles exactly (1348.95 - (-619.82) = 1968.77 = closing); the 3 previously-dropped page-3 rows (Checkers 514.21, Cash Finance Charge 23.05, Tips 10.00 = 547.26) are captured. Full SB suite + gate green (604 passed/1 skipped). Real file/password never committed; tests are synthetic. Note: a pre-existing cosmetic issue remains (a "Continued on next page......" line folds into the last page-N transaction's description) — filed separately, not this fix.

- ✅ [FIBR-0113] **Accounts tab: show accounts in a sortable 5-column table (Name / Type / Account number / Note / Status) instead of one line.**
  User request 2026-07-12 (screenshot): the Accounts tab lists each account as one line "Credit Card — Credit card" (name — type). Move to a columnar QTableWidget with columns: Name, Type of account, Account number, Note (optional), Status. Requires two NEW nullable account fields — account_number and note (schema bump) — plus the add/edit form growing those inputs and the AccountsWidget becoming a table (mirrors the Rules/Statements tab table shape). Account number is display/reference only (not used for matching). Dovetails with the columnar direction of FIBR-0109 (Transactions tab) and the account credential accessors already on the accounts repo (FIBR-0009).
  **Layman:** Show accounts in a proper table (Name, Type, Account number, an optional Note, and a Status column you can sort by) instead of a single cramped "Name — Type" line each.
  Kind: feature.
  Lanes: ui, repo.
  Source: user-request-2026-07-12.
  Started 2026-07-28, with FIBR-0084 folded in. Scope check first: the
  column machinery FIBR-0084 asks for ALREADY SHIPPED under FIBR-0117 /
  FIBR-0012 — _table_state.remember_columns does widths + drag-reorder +
  per-table persistence in the window INI keyed by objectName, and
  main_window._reset_layout does NOT clear it (corrected 2026-07-28, see below). It is already called by Statements,
  Transactions, Rules, Recurring, Transfers and the import-wizard preview.
  The only two screens without it are Categories (a single-column
  QTreeWidget with setHeaderHidden(True) — column customisation is
  meaningless there) and Accounts (still a QListWidget). So FIBR-0084's
  residue IS this item, and it closes alongside.
  Re-scoped 2026-07-28 (/cold-eyes loop 2 on docs/specs/FIBR-0113.md).
  The "FIBR-0084 folded in" plan above is WITHDRAWN, and one claim in it was
  wrong: main_window._reset_layout does not clear saved column state (it
  removes geometry / window_state / window_size only), so FIBR-0084 was never
  as close to done as that note said. Two more surfaces also lack column
  persistence entirely — ui/forecast.py's events table and ui/home.py's
  2-column dashboard breakdown trees.
  Progress (2026-07-28): /cold-eyes loop 5 ran and did NOT converge —
  CRITICAL 3 · HIGH 6 · MEDIUM 13 · LOW 13 · INFO 8, all verified, none
  fixed. Full write-up with cites and proposed fixes:
  docs/reviews/FIBR-0113-cold-eyes-loop5.md (do NOT re-dispatch review
  lanes to rediscover them — fold them in from that file).
  The three CRITICALs: (1) §4.5's premise that redrawing the table drops
  the selection is FALSE — with a sort active the selection survives and
  resolves to a DIFFERENT account, so the form loads account B while the
  selection points at account A and the next Update writes B onto A
  (reproduced against real Qt: docs/reviews/FIBR-0113-selection-drift-repro.py);
  (2) §4.4's trailing _on_selection_changed() copies a StatementsWidget
  line whose handler there only toggles buttons — on Accounts it also
  rewrites the form, so every _refresh() clobbers in-progress input and
  defeats _on_add's field-clearing; (3) INV-12 requires the test to
  assert the table cells "carry the typed values", which contradicts
  §4.3's masked cell — satisfying it literally ships the account number
  UNMASKED with every other invariant green.
  Three HIGHs are the same shape — the spec promises something no
  invariant locks: the account-number column's masking, the table's
  click-sortability, and the update write path for the two new columns.
  SPLIT EXECUTED (2026-07-28): loop 5's recommendation was to SPLIT rather than run
  loop 6 — draft defects are not falling (three NEW structural gaps
  appeared at loop 5 after four cold reads missed them), and the spec is
  985 lines vs a ~567 median. Proposed seam and per-finding assignment
  are in the review file. FIBR-0113 keeps the UI half; the schema +
  model/repo/service half became FIBR-0193.
  Also note: the /cold-eyes cheap breadth pass returned ZERO suspects on
  all three lanes this loop; the strong pass then found 3 CRITICAL. The
  skill has been amended so a breadth pass can no longer certify a lane
  clean after a loop that produced CRITICAL/HIGH.
  Split executed (2026-07-28), and split again on 2026-07-30. This item
  now delivers the TABLE half ONLY: the 5-column sortable Accounts table,
  the account-number cell and form field with the number ALWAYS masked, and
  the two-row edit form. The reveal toggle and its auto-hide timer moved to
  FIBR-0198, which ships AFTER this. The storage half — migration v13, models.Account, the accounts
  repository and service — moved to FIBR-0193, which SHIPS FIRST: this
  table reads and writes columns FIBR-0193 creates.

  Loop 5's 35 verified findings were routed to whichever half owns them per
  the assignment in docs/reviews/FIBR-0113-cold-eyes-loop5.md, and folded in
  directly rather than re-reviewed. The two open decisions that gated the
  three CRITICALs were resolved against current source, not by preference:
  (1) _refresh() uses CLEAR-then-fill, because AccountsWidget._refresh
  already opens with self._list.clear() — clear-then-fill preserves today's
  behaviour, where the StatementsWidget reuse-rows shape would newly
  introduce the cross-account write CR-1 reproduced; (2) the Forget-button
  rule moves into a gating-only helper _apply_forget_gating(), called from
  _on_selection_changed and _refresh()'s tail here, plus FIBR-0198's reveal
  handler once that ships, so a refresh can no longer repopulate the form
  (CR-2 + HI-6 in one fix).

  Headline + Layman card reconciled to five columns in this same edit (both
  still said four; the Status column was the user's 2026-07-28 decision).

  Spec rewritten as the UI half; cold-eyes gate re-run from loop 6 against
  the reduced document — §13's loop log for loops 1-5 is a frozen record and
  travels with this id.

  Folding that work in here made this spec the largest source of its own
  review defects (4 of 5 criticals in cold-eyes loop 2 traced to the
  fold-in). Split on the user's call: the FIBR-0084 completion work moved
  to FIBR-0192, which is what unblocks FIBR-0084's ✅. Two further splits
  followed — the storage half to FIBR-0193 (2026-07-28) and the reveal to
  FIBR-0198 (2026-07-30) — so this item's scope is the paragraph above,
  not this one.

  Consequence for the close: flip ONLY this bullet when the work ships.
  FIBR-0084 stays 📋 until FIBR-0192 lands.

  User decisions (2026-07-28):
  - FIVE columns: Name | Type | Account number | Note | Status. The Status
  column absorbs the suffixes _refresh currently concatenates onto the
  row text (the 🔑 saved-statement-password marker and the FIBR-0177
  reconciliation ✓ / ⚠ off by {money} / ⚠ {n} periods marker), so the
  user can click-sort to bring non-reconciling accounts to the top.
  - Account number is MASKED wherever it is displayed (last 4 shown) — it
  is shoulder-surf / screenshot exposure, not storage exposure (the vault
  is already encrypted). The mask is display-only; the stored value is
  verbatim. The way to SEE the full number is FIBR-0198's, not this
  item's.
  - The add/edit form stays INLINE on the tab, relaid as a two-row grid
  rather than moving to a dialog.

  Work (this item only, after the two splits): AccountsWidget moves
  QListWidget -> QTableWidget using the existing _table_state seam
  (SortableItem for the sortable columns, fill_guard, tag_row/selected_index
  so an action still targets the right account after a re-sort,
  enable_sorting, remember_columns with a distinct objectName), plus the
  two-row edit form and the always-masked account-number cell. The
  migration, the Account model and the repo/service changes are FIBR-0193's
  and ship first; the reveal toggle and its timer are FIBR-0198's and ship
  after. Spec cold-eyes-gated; TDD next.
  Cold-eyes gate 2026-07-30: 5 loops run jointly with FIBR-0198 (3
  strong cold lanes each, no breadth pass). 132 findings verified, 1
  unverified, all fixed — 3 CRITICAL / 30 HIGH / 50 MEDIUM / 54 LOW.
  Draft defects fell 30 -> 17 -> 11 -> 10 -> 8; fix collateral ran
  0 -> 9 -> 7 -> 5 -> 9. Stopped at loop 5 on the
  collateral-outnumbers-draft trigger, with implementation next.

  Highest-value catches: the reveal's clipboard copy escapes the
  auto-hide entirely (ClipboardAutoClear is wired only to the
  transactions list), so FIBR-0198's T13 amendment had to say the copy is
  NOT auto-cleared; three invariant legs were unbuildable or vacuous
  against a correct implementation; and this bullet's own body
  contradicted the split in seven places, including FIBR-0084's closing
  paragraph, which would have flipped that item green with three
  surfaces unbuilt.

  Nothing is owed on either spec. Both are gated and ready to build.
  Order: FIBR-0193 (storage) -> FIBR-0113 (table) -> FIBR-0198 (reveal).
  Resolved (2026-07-30): shipped by TDD, on top of FIBR-0193's storage.
  `AccountsWidget._list` (QListWidget) became `_table` (QTableWidget) with five
  sortable columns — Name, Type, Account number, Note, Status — built like
  `StatementsWidget`'s (NoEditTriggers / SelectRows / SingleSelection /
  `enable_sorting` / `remember_columns` on a new `accounts_table` objectName), so
  Accounts joins the shared remembered-column scheme (FIBR-0084's Accounts
  surface; the other three stay FIBR-0192's). The add/edit form relaid into a
  two-row grid with Account-number and Note fields. The number is masked on BOTH
  surfaces by two different mechanisms — the cell via the new
  `_mask_account_number` (a QTableWidgetItem has no echo mode), the form field via
  `Password` echo mode; the form always holds the RAW value, or an Update would
  write "•••• 7890" back as the account number. Row identity moved to the
  `_table_state` contract (tag on fill, `selected_index` in every handler), and
  the six `_ACCOUNT_*_ROLE` constants were deleted as a correctness requirement:
  `_ACCOUNT_ID_ROLE` and `_ROW_INDEX_ROLE` are both `Qt.ItemDataRole.UserRole`, so
  a survivor would make `selected_index` return a database id used as an index.
  The fill is clear-then-fill (a leading `setRowCount(0)` inside `fill_guard`) —
  the sibling's reuse-rows shape lets a selection ride its item through a re-sort
  onto a different account (reproduced against real Qt; the Statements twin is
  FIBR-0194, not fixed here). Status is a `SortableItem` keyed on a severity rank,
  composing the reconciliation marker first and the 🔑 second — the reverse of the
  old list line, since the column sorts by severity — and the four `tr()` literals
  dropped their leading "  ·  ". Reproduce-first TDD: 19 red before the rewrite
  (INV-5/7/9/12/15/18/20/21/22 in `test_accounts.py`, INV-8/17 in
  `test_table_state.py`), with four existing legs RE-DERIVED rather than
  re-pointed because a mechanical `_list`→`_table` swap would have left them
  passing while checking less — the FIBR-0128 sentinel sweep above all. Cross-doc
  per spec §12: FIBR-0005, FIBR-0128 and FIBR-0177 annotated, README + both
  Accounts screenshots refreshed (the demo seeder now carries numbers and notes so
  the masking is visible), CHANGELOG. FIBR-0198 (the reveal toggle) is next;
  FIBR-0084 stays 📋 until FIBR-0192.

- ✅ [FIBR-0114] **Auto-lock should be an inactivity timer (reset on user activity), not an absolute timer from unlock.**
  User report 2026-07-12. AuthService._arm_timer (auth.py:241) starts a single-shot QTimer at unlock (and only re-arms on a settings change), so the auto-lock fires a fixed duration after UNLOCK regardless of activity — locking mid-use. Fix: make it an inactivity timer. Add AuthService.notify_activity() that restarts the running timer with its existing interval (no settings re-read, since it fires on every input event; no-op when locked/headless), and have MainWindow install an application-level event filter that calls notify_activity() on user-input events (MouseButtonPress/MouseMove/KeyPress/Wheel). TDD: service-level (notify_activity restarts the running timer when unlocked, no-op when locked) + shell-level (eventFilter calls notify_activity on an input event).
  **Layman:** The screen-lock countdown ignored whether you were actively using the app — it locked a fixed time after unlocking even mid-use. It should count from your last interaction.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): added AuthService.notify_activity() — restarts the running idle timer with its armed interval (no settings re-read; no-op when locked/headless) — and MainWindow now installs an application-wide event filter that calls it on MouseButtonPress/MouseMove/KeyPress/Wheel. The auto-lock now counts from the last interaction, not from unlock. TDD: 2 service-level tests (restart-when-unlocked via a spy timer; no-op-when-locked) + 1 shell-level test (a KeyPress through the app filter calls notify_activity). Gate green (607 passed/1 skipped), mypy/ruff/bandit/gitleaks clean.

- ✅ [FIBR-0115] **Credit-card import: strip the "Continued on next page" footer from the last transaction's description.**
  Surfaced while fixing FIBR-0112 (not that bug — amounts/checksum are unaffected). On a multi-page Family-C statement, the in-region "NNNN Continued on next page......" line has no transaction date, so _fold/_parse_family_c folds it into the PRECEDING transaction's description (e.g. "# International Txn Fee 0400111222 Continued on next page......", number synthetic). Cosmetic data-quality issue affecting one row per page break. Fix: treat a line matching a "Continued on next page" / bare account-number footer as a skip line (like the "Debit"/"Credits" section headers in _is_cc_skip_line), not a description continuation. TDD with a synthetic fixture line.
  **Layman:** On multi-page credit-card statements, one transaction's description gets a stray "Continued on next page..." tacked onto it. Cosmetic only — the amounts are correct.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-08-19, commit c1d8a9d): _is_cc_skip_line now recognises the "Continued on next page" page-break footer, matched as a substring because the account number precedes the phrase. Test-first; the regression test went red naming the glued-on footer, and carries a real zero-date continuation beside it so a fix that skipped every zero-date line could not pass. INV-10 amended in the same commit per CLAUDE.md -- and its claim that the region bound means "footer prose can never fold into a description" was corrected: that holds for POST-table prose only, and Family C prints an IN-REGION footer the bound never covered. The bullet also mentioned a bare account-number footer; that was NOT added, because an all-digits zero-date line can legitimately be a reference number on a real continuation, and skipping it would drop data rather than tidy it. Full gate green, 1932 passed.

- ✅ [FIBR-0116] **Toolbar icons: muted theme-aware colour that brightens to vibrant on hover.**
  User request 2026-07-12: the toolbar glyphs are currently a single flat mid-grey (#808080, hand-authored monochrome SVGs loaded by ui/icons.py `icon()`; the toolbar is ToolButtonTextUnderIcon). Wanted: (1) each icon a MUTED colour by default, (2) the icon brightening to a VIBRANT version of that same hue while the mouse hovers, reverting on leave, and (3) colours chosen per the active theme (light/dark). Approach sketch: give each glyph a semantic accent colour, then re-tint at load time — either recolour the SVG per state (parse `stroke="#808080"` → muted/vibrant/theme variants and build a QIcon with Normal/Active pixmaps so Qt swaps to the Active pixmap on hover automatically), or drive it via a QProxyStyle / event-filter on the toolbar buttons. Theme-awareness ties into the theme system FIBR-0014 builds (dark/light/follow-system) — coordinate so the muted/vibrant palettes have a light AND dark variant. Related: FIBR-0014 (palette-adaptive re-tinting / dark-theme polish) — this is the specific hover-brighten behaviour, keep them cross-referenced. Icons live in src/finbreak/ui/icons/*.svg; loader is src/finbreak/ui/icons.py.
  **Layman:** Give the toolbar buttons gentle colour that lights up brightly when you point at one, and dims back when you move away — and pick colours that suit the current light or dark theme.
  Kind: enhancement.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): toolbar_icon() recolours each hand-authored SVG at load — a per-icon muted semantic hue at rest (QIcon Normal) + a vibrant one on hover/focus (QIcon Active/Selected, Qt's built-in hover swap, no event filter), tuned to the active light/dark theme via the app palette. 8 glyphs each get a calm distinct hue; _make_action uses it for toolbar + menus. Tests: Normal≠Active, theme-aware + hover more saturated, unmapped-glyph fallback. Ships in v0.1.7. Live theme-switch re-tint stays with FIBR-0014 (icons read the palette at build time).
  Live theme-switch re-tint is delivered by FIBR-0127 (the theme system): MainWindow re-runs toolbar_icon() for each icon'd action on the ThemeController's themeChanged signal, so the muted/vibrant glyphs re-tint to the new light/dark palette without a relaunch. The FIBR-0116 muted/vibrant seam (v0.1.7) is the mechanism; FIBR-0127 wires the live-on-switch trigger. (2026-07-14)

- ✅ [FIBR-0117] **Data tables: remember column widths + click-header-to-sort (toggle order on re-click).**
  User request 2026-07-12 (screenshot, Statements tab): the QTableWidget-based data tables should (1) REMEMBER column widths across sessions, and (2) allow clicking a column header to sort by that column, with a second click on the same header toggling ascending/descending. Applies to the Statements table and the other list tables (Rules, the FIBR-0011 Transfers tables, the FIBR-0113 Accounts table, Home). Approach: QTableWidget.setSortingEnabled(True) gives click-to-sort with the asc/desc toggle for free (note: with sorting on, populate rows then enable, and key numeric/date columns with a sortable value — e.g. QTableWidgetItem data role or zero-padded/ISO text — so "112" doesn't sort before "69" and dates sort chronologically). Persist column widths via QHeaderView.saveState()/restoreState() into the window INI (paths.window_settings_path, same store as geometry, NOT the vault — it is non-secret view state), keyed per-table by objectName. Requested for inclusion in the v0.1.7 release alongside FIBR-0011. Related: the columnar tables in FIBR-0111/FIBR-0113.
  **Layman:** Let the tables (Statements, and the other lists) remember how wide you've dragged each column, and let you click a column heading to sort by it — click again to flip between ascending and descending.
  Kind: enhancement.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): new ui/_table_state.py — SortableItem (numeric/date sort keys), enable_sorting, remember_columns (header saveState/restoreState → window INI keyed by objectName, not the vault), and a row-tag scheme (tag_row/selected_index/select_by_index) so an action maps to the correct row after a re-sort (the money-critical guard). Applied to Statements, Transfers, Home (click-sort + widths + persisted sort/direction; Home moved off all-Stretch to interactive+stretch-last). Rules keeps priority order (not sortable) but persists widths, per user choice. tests/features/table_state/ covers numeric sort, tag-survives-reorder, action-targets-sorted-row, and width+sort persistence across rebuild. Ships in v0.1.7.

- ✅ [FIBR-0118] **App icon: transparent (rounded) corners instead of a hard square tile.**
  User request 2026-07-12 (About-box screenshot): the app/window icon (the donut-on-dark-navy tile) has hard square corners that read as a solid block against the dialog background. Make the corners transparent — a rounded-rectangle alpha mask so the four corners are see-through. Regenerate the whole icon set from the 1024 master: apply the rounded-corner alpha to assets/icon/finbreak.png (or add the mask step in scripts/make-icons.sh), then re-run make-icons.sh to rebuild the Linux PNGs (16-512), the Windows .ico, the macOS .iconset, and the runtime src/finbreak/ui/icons/app.png. Keep the corner radius modest (~15-20% of the tile) so it matches platform icon conventions. Verify the About box + taskbar show transparent corners (QIcon/PNG alpha travels). Requested alongside the v0.1.7 polish batch. Related: FIBR-0037 (the branded app icon) + FIBR-0116 (toolbar-glyph colour).
  **Layman:** Round off the corners of the app icon so it doesn't show as a solid square block — the corners become see-through and blend into whatever's behind it.
  Kind: ux.
  Lanes: ui, packaging.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): make-icons.sh applies an 18%-radius rounded-rectangle alpha mask to the master once, deriving every size (Linux hicolor PNGs, Windows .ico, macOS .iconset, runtime app.png) from the rounded temp; master stays square. Regenerated the set; regression test asserts transparent corners + opaque centre. Refreshed the dogfood install's hicolor icons so the launcher shows it now; the About-box (embedded app.png) rounds on the v0.1.7 install. Ships in v0.1.7.

- ✅ [FIBR-0119] **Home Loan (Family B) import: page-break footer/letterhead folds into the previous transaction's description.**
  Root-caused against a real SBSA Home Loan statement (2026-02-28; real file/password never committed, synthetic fixture/tests to follow). On a multi-page Family-B statement, a page break prints the registered-office letterhead (bare account number, "Standard Bank Centre …", "P O Box …", "Tel. Switchboard: … Fax: …") plus a repeated column header ("Debit Credit Balance" / "Date Date Fee") BETWEEN two transactions. None of those lines carries a date+amount, so _fold (standard_bank.py:489) — which appends every non-row in-region line to the preceding transaction as a description continuation — glued the whole block onto the last transaction before it (e.g. "Insurance Premium 0400111222 Standard Bank Centre … Debit Credit Balance Date Date Fee"; number synthetic). Amounts/dates/counts are unaffected (54 drafts still reconcile), so it imported "successfully" with a corrupt description; it also makes dedup fragile across statements where the same transaction appears with different page-break pollution. Fix: a shared _is_boilerplate() predicate (bare account/reference number; SB registered-office/contact markers; a repeated column-header line whose tokens are all table-header words) that _fold drops instead of folding — generalising the existing _is_cc_skip_line Family-C rule. TDD: pure synthetic _parse_family_b test (footer+header block between two rows → clean descriptions) + re-validated the two real Home Loan statements (27 / 54 drafts, clean descriptions) and the full synthetic A/B/C/D suite. NOTE: the "27 new · 27 duplicate" the user saw importing the 2026-02 statement after the 2025-08 one is CORRECT — the 2026-02 statement restarts at 2025-03-01 (54 drafts = the 27 overlapping the first statement, deduped, + 27 new); no dedup bug.
  **Layman:** On a multi-page home-loan statement, one transaction's description got the whole page footer (bank address, phone/fax, column headers) glued onto the end — making it a paragraph long instead of a few words.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): added a shared `_is_boilerplate()` predicate (bare account/reference number; SB registered-office/contact markers — "standard bank centre"/"standardbank.co.za"/"P O Box"/"switchboard"/"fax"/registration/FSP; a repeated column-header line whose tokens are ALL table-header words) that `_fold` drops instead of folding into the preceding transaction — generalising the Family-C `_is_cc_skip_line` rule; the header-token set deliberately excludes ambiguous words (service/details/description/amount/reference) so a genuine wrapped description isn't mistaken for a header. TDD: pure synthetic `_parse_family_b` test (footer+letterhead+repeated-header block between two rows → clean descriptions). Re-validated the two real Home Loan statements (27 / 54 drafts, all descriptions clean incl. the formerly-polluted 2025-11-03 "Insurance Premium") + the full synthetic A/B/C/D suite. Gate green 656/1. The "27 new · 27 duplicate" the user saw was CORRECT (the 2026-02 statement restarts at 2025-03-01: 54 drafts = 27 overlapping the first import (deduped) + 27 new) — no dedup change.

- ✅ [FIBR-0120] **Data tables: drag-to-reorder columns, with the order persisted across sessions.**
  Extends the shared _table_state.remember_columns seam (FIBR-0117, which already
  saved/restored full header state incl. section order): enables setSectionsMovable
  on every table that calls it, so drag-reorder + persistence light up across all
  four data tables at once. Reordering is visual-only — the parallel-list row tag
  lives on logical column 0, so selection + sorting stay correct whatever the order.
  **Layman:** You can now drag a table's column headings to rearrange them (e.g. put Amount before Date), and the app remembers your arrangement next time — on the Transactions, Statements, Rules and Transfers tables.
  Kind: enhancement.
  Source: user-request-2026-07-12.

- 📋 [FIBR-0121] **Loan-account sign display: show debt-reducing amounts as positive on loan-type accounts.**
  Approach APPROVED by user (2026-07-13): DISPLAY-ONLY, display-time inversion for
  loan-type accounts (AccountType.HOME_LOAN / PERSONAL_LOAN). Keep amount_minor
  stored canonical (FIBR-0007: debit negative / credit positive) so the exact-money
  math, transfer detection, and the FIBR-0012 dashboard totals are all undisturbed;
  only the on-screen sign + direction colour flip for loan accounts. Scope is
  display-only for now (NOT changing how loan flows count in dashboard totals) — a
  deeper "interest-as-expense / repayment-as-transfer" semantic is a possible later
  follow-up.
  Needs its own spec + the project's 7-loop cold-eyes (correctness-critical money
  display). OPEN QUESTION to verify during that spec (do NOT assume): how the
  importer currently signs loan-statement debit/credit columns, and whether transfers
  INTO a loan are being detected at all (the loan-payment leg and its current-account
  leg may currently share a sign, which opposite-sign transfer matching would miss).
  If a real detection gap exists, split it out as a bug-fix. Touches ui/_amount.py +
  the Transactions table render; the account type is on models.Account.type.
  **Layman:** On home-loan / personal-loan accounts, your payments (which reduce what you owe) will read as positive/green and interest &amp; fees (which increase what you owe) as negative/red — the natural way round, instead of the current back-to-front look.
  Kind: feature.
  Source: user-request-2026-07-12 (approved 2026-07-13).

- ✅ [FIBR-0122] **Auto-update relaunch: stop the /bin/sh waiter inheriting the frozen app's bundled-library path.**
  Root cause (from update-relaunch.log): the relaunch /bin/sh waiter inherited the
  PyInstaller onefile app's LD_LIBRARY_PATH pointing at its private _MEI extraction
  dir, so the SYSTEM /bin/sh loaded the app's bundled libreadline.so.8 and died on a
  symbol lookup (rl_completion_rewrite_hook) BEFORE it could relaunch — the real cause
  of "closed but didn't reopen". Fix: _relaunch_env restores LD_LIBRARY_PATH / LD_PRELOAD
  to the pre-launch value PyInstaller preserves in <VAR>_ORIG (or drops them when there
  was none), so the waiter runs against system libraries; the exec'd AppImage sets up
  its own loader path. TDD: 2 unit tests (restore-from-ORIG + drop-when-absent). Ships
  in the next release. TWO-CYCLE CAVEAT: the *running* (old) version performs each
  relaunch, so 0.1.7→(this release) still needs one manual reopen; the update AFTER it
  is the true auto-relaunch test — same caveat as the earlier relaunch fixes (FIBR-0054).
  **Layman:** After an update the app should reopen itself; it was silently failing to. Fixed so the little helper that reopens it runs with the system's own libraries instead of the app's bundled ones.
  Kind: fix.
  Source: user-report-2026-07-13 (0.1.6→0.1.7 did not auto-relaunch).

- ✅ [FIBR-0123] **Group category pickers by Income/Expenditure type (disambiguate same-named categories).**
  The category pickers (Set-category dialog `ui/category_picker.py`, the Rules editor `ui/rules.py`, and the Transactions category filter) flatten the two-root Income/Expenditure category tree (FIBR-0006) into one flat combo, so: (1) you can't tell an income category from an expenditure one at pick time, and (2) two categories that share a name under different Type roots are indistinguishable — real dogfooding case 2026-07-13: the seeded income "Lottery" plus a user-added expenditure "Lottery" render as two identical rows. Fix: group each combo under non-selectable "Income" / "Expenditure" section headers (or an equivalent grouped/indented presentation) so the Type is obvious and same-named siblings are unambiguous. The category *manager* already shows the tree grouped; this is only the flat picker combos. Known-deferred shortcut, recorded at the FIBR-0010 close ("category selectors are flat combos, grouping deferred").
  **Layman:** When you pick a category, show which options are income and which are expenditure — and make two categories that share a name (e.g. an income "Lottery" for winnings and an expenditure "Lottery" for tickets) tell-apart-able instead of two identical rows.
  Kind: ux.
  Source: dogfooding-2026-07-13.
  Resolved (2026-07-13): shipped by TDD (6 slices) + 1 indie-review LOW fixed inline (parent-cycle guard). Grouped pickers/filter under Income/Expenditure headers, Name (Type) tag; audit 0, gate green. Tag FIBR-0123-complete.

- ✅ [FIBR-0136] **Add the missing Statements toolbar icon + button.**
  Statements shipped (FIBR-0052) text-only and absent from the toolbar — reachable only via the View menu, where it also lacked a glyph unlike its neighbours. Added ui/icons/statements.svg (Feather file-text style matching the icon set), wired it into _action_statements (was icon=None), and added the action to the toolbar after Transactions to mirror the workspace tab order. Reverses the FIBR-0052 "Statements not on the toolbar" test assertion by explicit user request; the statements/app_shell tests were updated (toolbar order now includes action_statements; a rendering-icon + toolbar-membership test added). Kind: fix.
  **Layman:** Give the Statements screen its own button with an icon in the toolbar (it was only reachable from the View menu before, and even there it had no icon).
  Kind: fix.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14) — commit eb52443. statements.svg added, wired into _action_statements + the toolbar after Transactions; tests updated. Gate green 862/1.

- 💭 [FIBR-0137] **Business / Personal account grouping — separate views within one profile.**
  Today the model is one profile per logged-in user with a single, flat account list; every view (Home dashboard, Transactions, Accounts) spans all accounts at once. An external tester runs both business and personal accounts and wants to view each set separately WITHOUT a second profile/login.

  Investigate: (a) an account "group" attribute — fixed Business/Personal, or user-defined groups — as a nullable column on accounts (no migration pain, defaults ungrouped); (b) a group filter/toggle shared across Home, Transactions and Accounts (reuse the existing account-selector pattern in HomeView); (c) whether dashboard totals should roll up per-group; (d) how this interacts with the (planned) expandable dashboard and with transfer-detection across groups. Keep the single-profile design — this is a view/grouping concern, not multi-user.

  Source: user-request-2026-07-14 (friend / external tester).
  **Layman:** Let someone tag each account as Business or Personal (or custom groups) and view the two separately, so a person with both kinds of accounts keeps them apart while still staying under one login.
  Kind: investigate.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0138] **Expandable dashboard drill-down (Income / Spending / Transfers → categories → merchant → transactions).**
  Designed in-session 2026-07-14 (three user-approved brainstorm decisions). Enhances the FIBR-0012 dashboard: keep the donut + 12-month trend charts as the snapshot, add an expanding tree below them that drills the numbers.
  Spec written (docs/specs/FIBR-0138.md) 2026-07-14; /cold-eyes next.
  Spec CLEARED FOR CODE 2026-07-14 — /cold-eyes converged loop 5 (5 loops × 3 cold lanes = 15 reviews; accuracy lane clean from loop 4). Next: TDD tests/features/dashboard_drilldown/ (INV-1..9) → /close-phase.
  Resolved (2026-07-14): SHIPPED (code) via /close-phase. TDD 41-leg tests/features/dashboard_drilldown/ (INV-1..9) → DrillNode/DrillLabels (models), merchant_name (text.py, pure+total), drill_rows_in_range (5-tuple sibling read), ReportingService.drill_down (one "group by top-of-chain" category algorithm + account-pair transfers, INV-7 uniform-string sort; branch totals sum from integer amount_minor so they equal the tiles, INV-1), HomeView QScrollArea+QTreeWidget wiring. Close: /audit semgrep 0 + gate 0; /indie-review 2 cold lanes → production money-correct, folded inline a top_of_chain/category_node corrupt-data cycle guard + 5 test-strength adds (real INV-7 mixed-type sort-key falsifier, INV-9 sentinel-label proof, cycle regression, count==1 bare label, punctuation merchant_name). Gate green 975/1, mypy 0. Commits 810283f (impl) + ebbcced (fold) + close; tag FIBR-0138-complete; journal docs/journal/FIBR-0138.md. README "what works today" refresh deferred to next bump per Deliverable 7.

  D1 Presentation: an expanding tree (QTreeWidget-style), NOT a click-to-drill donut. The three totals (Income / Spending / Transfers) are the top rows.
  D2 Spending/Income drill follows the existing category tree (parent->child, any depth) to a leaf category; at a leaf, group its transactions by merchant with a x count, then expand a merchant to the individual transactions (date + amount).
  D3 Merchant = "smart cleanup" of the free-text description (strip card numbers, branch/ref codes, trailing digits) to a best-guess shop name, grouped + counted. There is NO merchant field today (only transactions.description) - this is a new derivation. Fuzzy by nature; refine rules over time. Candidate reuse: the FIBR-0010 rule-engine description matching.
  D4 Transfers drill by account pair (from->to, x count), then the individual moves. Transfers have no categories (money between own accounts, excluded from income/spend totals).

  INV (correctness-critical): the merchant cleanup only affects DISPLAY GROUPING - every total/subtotal is summed from real amount_minor; cleanup can never change a number, only which line it sits under.

  Details: biggest-amount-first sort at every level (matches the donut); the period + account selectors drive the tree; magnitudes shown like the tiles. Needs a new ReportingService drill API + a merchant-normalisation helper. Spec -> /cold-eyes (--max-loops 7) -> TDD when scheduled; after the v0.1.10 release per the current plan.
  **Layman:** Click a total on the Home dashboard to open it up — Spending breaks into categories, each category into shops (with a count like "McDonald's ×3"), and each shop into the actual purchases; Transfers break down by which accounts the money moved between.
  Kind: enhancement.
  Lanes: reporting, ui.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0139] **Built-in category library — smarter auto-categorise out of the box.**
  Fixes the cold-start: today auto-categorise only matches USER-written rules (FIBR-0010), so a fresh vault imports everything Uncategorised. Design (brainstorm-approved 2026-07-14):
  D1 Ship a bundled, per-release-updateable data file src/finbreak/data/category_library.json — list of {pattern, category} entries, SA-first (Pick n Pay/Checkers/Woolworths/Shoprite/Shell/Engen/Dis-Chem/Vodacom/MTN/Eskom...) + universal (Netflix/Spotify/Uber/Steam/Apple...), mapping to the v3-seeded default categories (Groceries/Transport/Bills & utilities/Entertainment/Medical/Salary/...). Travels like ui/icons (pyproject glob + PyInstaller --add-data). Missing/malformed file => empty library, app runs (fail-safe).
  D2 Matching order: user rules FIRST, then library. categorize() already substring-matches (contains, normalise_text-folded) — no wildcards. Manual pick always wins (golden rule INV-1 untouched).
  D3 New CategorySource.LIBRARY = 'library' — NO schema migration (category_source is free-text TEXT; auto_rows predicate 'IS NULL OR <> manual' already recomputes library rows). categorize/recategorize_auto_rows extended to return WHICH source matched so set_category stamps 'rule' vs 'library'.
  D4 Runs on the EXISTING paths — import auto-categorise + Rules-tab Apply — both now include the library. NO new button.
  D5 Settings toggle (default ON), reuse SettingsRepository (non-schema). Off => library not consulted; next apply/import reverts library rows to uncategorised.
  D6 Small '~ guess' tag beside library-guessed category in the Transactions table (Home is now the FIBR-0012/0138 dashboard with no per-row cell — superseded by spec D7); overridable.
  D7 Library binds category by NAME; a renamed default category => entries fall through to Uncategorised (never mis-filed). Structural binding is a future enhancement (out of scope).
  INV money-safety: only sets category, never reads/alters an amount; grand-book total + amount_minor multiset identical before+after (per-category sums change by design — see spec INV-1). Deps: FIBR-0010. Lanes: services, ui, repo, tests. Next: spec docs/specs/<id>.md -> /cold-eyes (max-loops 7) -> TDD.
  **Layman:** finbreak ships with a built-in list of common shops so imported transactions get sensible categories automatically, without you writing a rule for every merchant.
  Kind: feature.
  Source: user-request-2026-07-14.
  Active 2026-07-14 — brainstorm complete + user-approved (all decisions D1-D7 locked: bundled JSON library, user-rules-first, CategorySource.LIBRARY no-migration, existing import+Apply paths, Settings toggle default-ON, '~ guess' tag, rename falls through safely). NEXT: write spec docs/specs/FIBR-0139.md -> /cold-eyes (max-loops 7) -> TDD.
  Resolved (2026-07-14): SHIPPED by TDD. category_library.py (LibraryEntry, pure+total parse_library, fail-safe cached load_library, match_library) + data/category_library.json seed (every entry bound by name to a v3 DEFAULT_CATEGORIES leaf). CategorySource.LIBRARY (free-text column, no migration); categorize_with_library (rule beats library), _match_inputs (toggle-gated), _leaf_name_to_id (first-wins), library_enabled; recategorize_auto_rows + would_categorize rerouted. Settings toggle (default ON) wired through the shell; Transactions "~ guess" marker with every Category cell a bare-name SortableItem. data/*.json package-data + second --add-data pair in all three freeze sites; parity guard set-checks both targets. tests/features/category_library/ (INV-1..11) + autouse neutralise fixture + real_library marker. /audit (semgrep full) 0 actionable; /indie-review 2 cold lanes 0 CRIT/HIGH/MED, only LOW substring-precision (accepted D2 substring-only tradeoff, marked overridable guesses, money never touched). Gate green 934/1, mypy 0. Commit 24e7a91; tag FIBR-0139-complete; journal docs/journal/FIBR-0139.md. FIBR-0140 (learn-from-history) remains the deferred "later" half.
  Lanes: services, ui, repo, tests.

- 📋 [FIBR-0140] **Auto-categorise learns from your own history (statistical, no hand-written rule).**
  The 'later' half of the 2026-07-14 'both' decision (library now, learning later). Distinct from FIBR-0035 (offer-to-MAKE-a-rule, shipped) and FIBR-0092 (bulk re-categorize + rule preview): this auto-applies a category learned from the user's OWN past manual picks (merchant-keyed), ranked with/near the library, still overridable, manual always wins. Deps: the built-in category library item + FIBR-0010. Design TBD in its own brainstorm.
  **Layman:** Once you've categorised a shop by hand a few times, finbreak remembers and auto-applies that to future transactions from the same shop — without you writing a rule.
  Kind: enhancement.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0142] **Recurring money detection (subscriptions + standing income).**
  Split from FIBR-0022 (the recurring half; budgets stay on FIBR-0022 as the follow-up). Auto-detect repeating money movements — recurring OUT (subscriptions, debit orders, insurance) and recurring IN (salary, standing deposits) — surface for confirm/dismiss. User-chosen scope (2026-07-15 brainstorm): both directions; "Balanced" sensitivity (seen 3+ times, amount within ~10% of the group median, gaps consistently in one cadence bucket — weekly/fortnightly/monthly/yearly with slack). Pure deterministic detect_recurring(rows, today) grouping on normalise_text(merchant_name(description)) x direction (reuses FIBR-0138 cleanup); excludes confirmed transfers; integer amount_minor throughout (INV-13). Persistence: new schema v9 recurring_decisions table keyed on (direction, merchant_key) — not txn ids — mirroring transfer_pairs. RecurringService shaped like TransferDetectionService (candidates/confirmed/confirm/dismiss/reset/summary). SURFACES: dedicated Recurring tab (Suggested/Confirmed tables mirroring Transfers) built now; the read-only Home dashboard card is DEFERRED until the dashboard-focus rework so it isn't added to a layout being decluttered. Deps: FIBR-0138 (merchant_name), FIBR-0011 (transfer exclusion), FIBR-0012 (dashboard).
  **Layman:** finbreak spots your regular payments and deposits — subscriptions, debit orders, salary — so you can see what's on autopilot and what it costs you each month.
  Kind: feature.
  Source: user-request-2026-07-01 (FIBR-0022 split) + brainstorm-2026-07-15.
  Resolved (2026-07-15): shipped by TDD (4 slices) — pure detect_recurring + schema v9 recurring_decisions + RecurringRepository/RecurringService + the Recurring tab (after Transfers). Closed by /close-phase: semgrep+bandit 0; 2 cold code-review lanes → 1 HIGH (fortnightly monthly-equivalent pre-divided factor defeated ROUND_HALF_EVEN) + 1 LOW (created_at reset on flip) + 3 test-strength adds, all folded inline. Gate green. Tag FIBR-0142-complete. Home dashboard card deferred to FIBR-0143.

- ✅ [FIBR-0143] **Rework the Home dashboard so the income/expenditure/transfers breakdown is the hero, charts secondary.**
  User feedback 2026-07-15 (with a screenshot): the current Home leads visually with the donut and the income-vs-spending BAR graph, while the FIBR-0138 drill-down breakdown (Income / Spending / Transfers -> category -> merchant -> txn) sits at the very bottom. The user's intended hero of the dashboard is that BREAKDOWN, not the graphs -- valuable information but the BIG feature is the breakdown. Especially de-emphasise the bar graph. Invert the layout: promote the expandable breakdown to the primary surface; keep the charts as smaller/secondary supporting detail. BLOCKED pending the user's own HTML mockup of the envisioned layout (they said they'll make one) -- do NOT redesign the layout before that lands. When it does: brainstorm-confirm against the mockup -> spec -> cold-eyes -> TDD. The deferred FIBR-0142 recurring Home-card slots into this reworked layout. Deps: FIBR-0012 (dashboard), FIBR-0138 (drill-down breakdown).
  **Layman:** Redesign the main screen so the plain-language breakdown of where your money went (and came from) is the star, with the pie and bar charts moved to a supporting role.
  Kind: ux.
  Evidence: /home/ants/Pictures/ClaudePaste/paste_20260715_085635_284_5e11f9ac.png
  Source: user-feedback-2026-07-15 (dashboard focus).
  UNBLOCKED 2026-07-15: user delivered the HTML mockup `/home/ants/Documents/dashboard_2.html` (+ annotated screenshot). Envisioned layout: three side-by-side columns — Expenditure / Income / Transfers — each with the existing pie chart on top, a bold coloured header + big total, then the expandable breakdown list (categories → merchant sub-rows, e.g. Groceries → Checkers/Sixty60, Spar); the monthly bar chart demoted to a full-width strip at the bottom ("2026 Monthly Trend Breakdown"). User notes: NO borders (those were alignment guides only), CONSISTENT row heights, reuse the existing pie chart (not the mockup's CSS one), add polish/flair. Next: brainstorm-confirm against the mockup → spec → cold-eyes → TDD. Also lands the deferred FIBR-0142 Home recurring card (consumes RecurringService.summary()). User gated this behind "if my weekly limit hasn't finished yet" (2026-07-15).
  Started 2026-07-16: design brainstormed + user-approved against the mockup (dashboard_2.html). Decisions: pies in all 3 columns (fed from the existing drill_down branch children — pie mirrors each column's breakdown list); keep Net as a slim full-width strip; include the deferred FIBR-0142 recurring Home card now. Layout: 3 side-by-side columns (Expenditure/Income/Transfers) each = pie → coloured header+total → expandable breakdown tree; Net strip; full-width Recurring card; monthly-trend bar demoted to a bottom strip. No schema/service-data change — all reuse (drill_down + summary + monthly_trend + RecurringService.summary). Spec docs/specs/FIBR-0143.md next → /cold-eyes (cap 7) → TDD.
  Spec CLEARED FOR CODE 2026-07-16 — /cold-eyes converged loop 7 (7 loops × 3 cold lanes = 21 reviews; loop 7 all-polish, 0 CRIT/HIGH/MED). Spec docs/specs/FIBR-0143.md written + 7-loop log. Key contract details settled across the loops: build_breakdown_donut does its own cap loop (no _donut_wedges extraction — donut stays byte-for-byte unchanged for the PDF export); each column's header+pie+list all source from the one drill_down branch node (summary feeds only the Net strip); explicit node→column map (Expenditure←nodes[1]/Spending, Income←nodes[0], Transfers←nodes[2]) so a naive zip can't mis-colour; recurring card is UNSCOPED by the Home selectors (summary(today) takes only today — shows all confirmed recurring money vault-wide); branch colour on header+tree only (pie is palette-coloured), gated on amount_prefs.colour; monthly_out is a positive magnitude so In/Out colours are forced-by-role. Commits d132c18→7238685, all pushed, gate green. NEXT: TDD tests/features/dashboard_focus/.
  Resolved (2026-07-16): shipped by TDD. build_breakdown_donut (own cap loop, palette, empty-safe; PDF donut byte-for-byte unchanged) + HomeView reworked into three columns (Expenditure/Income/Transfers, each pie+coloured header+drill tree) + slim Net strip + unscoped Recurring card + demoted trend strip; explicit node→column map; RecurringService wired into main_window (amount_prefs by keyword). New tests/features/dashboard_focus/ (INV-1..9, 20 legs) + rippled FIBR-0138/FIBR-0012 tests onto the new surfaces. Closed by /close-phase: semgrep 0; 2 cold review lanes → production clean (0 CRIT/HIGH/MED), 3 LOW test-strength adds folded inline. Gate green (1040 pytest, mypy 0). Commits 070cd76→6719de5. Tag FIBR-0143-complete.

- 📋 [FIBR-0144] **Centralise the schema-version drift guard to remove per-bump test churn.**
  Surfaced during the FIBR-0142 close. Every feature that ever added a migration hard-asserts `LATEST_SCHEMA_VERSION == N` (and encodes the version in test function names + spec.md INV lines), so each schema bump forces ~24 assertion edits + ~15 renames across ~9 feature suites (v8→v9 did exactly this). Replace the scattered per-feature guards with ONE canonical "latest schema version" test (assert the constant + that a fresh vault reaches it) and have each feature's migration test assert only its OWN delta (the intermediate step it introduced), never the moving global latest. Removes the churn and the drift risk. Low priority, no user-facing effect.
  **Layman:** A cleanup: right now every time the database format is upgraded, a bunch of unrelated tests have to be hand-edited. This would make that a one-line change instead.
  Kind: refactor.
  Source: in-session-2026-07-15 (FIBR-0142 review observation).

- 📋 [FIBR-0145] **Transfer detection learns from confirmed/rejected transfer pairs.**
  User feedback 2026-07-16 (general use of the shipped Transfers tab): confirming/rejecting a transfer should TEACH the detector, not just decide the one pair. Today FIBR-0011's `transfer_pairs` records a decision keyed on the two specific transaction ids, so an equivalent pair next month (same two accounts, same kind of description, same equal-magnitude/opposite-sign shape) is presented cold again. Enhancement: derive a reusable signal from each confirm/reject — keyed on something like (account_pair, direction, normalised description/merchant pattern) — so future candidate pairs that match a CONFIRMED pattern are auto-suggested or pre-confirmed, and pairs that match a REJECTED pattern are suppressed. Mirror the FIBR-0010 categorization-rules learning-from-manual-overrides design (a learned-rule table + a manual decision always winning + an overridable marker), applied to the transfer surface. Correctness guard: a learned auto-confirm must never merge money that isn't genuinely a transfer, so the learned pattern should stay conservative (exact account pair + tight amount/description match) and remain user-overridable. Deps: FIBR-0011 (transfer detection), pattern-reuse from FIBR-0010 (rules engine).
  **Layman:** When you confirm or reject that two transactions are the same money moving between your own accounts, the app should remember the pattern and get better at spotting (or ignoring) similar transfers next time — instead of re-asking about the same kind of pair every import.
  Kind: enhancement.
  Source: user-feedback-2026-07-16 (general use).

- ✅ [FIBR-0146] **PDF statement import fails every row with a raw "time data ... does not match format" date error.**
  Reported 2026-07-16 (external Windows tester, screenshot). Import preview: all 165 rows red, Status "Error", the Description column filled with the raw Python message "time data '20 ...' does not match format ...", Date/Amount blank, footer "0 new · 0 duplicate · 165 error". Root cause: the generic PDF importer (importers/pdf_importer.py) extracts the table then parses each date via the shared CSV path importers/csv_importer.py:74 datetime.strptime(row[date_column], mapping.date_format); on failure it appends RowError(row_number, str(exc)) (csv_importer.py:88-89), so the raw strptime message becomes the shown text. The applied mapping.date_format does not match this bank's date format — the failing values step through days 20,21,22,26,27,28,31,02,03 (a DD-first statement rolling over a month boundary), so a wrong/guessed format was applied (wrong profile matched, or the wizard's date-format guess/selection was wrong for an unrecognised bank). TWO fixes: (1) correctness — parse this bank's actual date format (needs the sample to know the exact string; may need a new mapping profile or a smarter date-format auto-detect / a clearer wizard affordance to pick it); (2) UX — a row-level failure should show a friendly "couldn't read the date in this row" not the raw str(ValueError), and a 100%-failure import should surface a "the date format didn't match — pick the right one / this bank isn't recognised yet" banner instead of 165 identical raw errors. Needs from the user: which bank, and the exact date format as printed (e.g. "20/07/2026" vs "20 Jul 2026" vs "2026-07-20"), ideally a redacted sample PDF, to reproduce-first then fix.
  **Layman:** A friend's Windows PDF statement imported with every single row marked "Error" (165 errors, 0 imported) — the app couldn't read the dates and showed a raw programmer error message instead of a helpful one.
  Kind: fix.
  Source: external-tester-2026-07-16.
  Progress (2026-07-16): started. Approach confirmed with user — auto-detect the statement's date format from the extracted date column, pre-select a plain-English format in a friendly picker (replacing the raw %-code box) with a live sample-date preview so a wrong guess is caught before import (never a silent wrong-day); fall back to the picker when genuinely ambiguous. Plus a friendly per-row date error and a whole-import \"date format didn't match\" banner. Spec → /cold-eyes (7-loop) → TDD next; reproducible via a synthetic day-first (DD/MM/YYYY, month-rollover) fixture without the tester's sample.
  Progress (2026-07-16, EOD): spec docs/specs/FIBR-0146.md written + run through /cold-eyes to the full project cap (7 loops × 3 cold lanes = 21 reviews). Core converged — accuracy lane clean loops 5–7, no remaining silent-wrong-day path loops 5–7; every CRITICAL/HIGH/MEDIUM/LOW fixed in-loop (notably: removed a plausible-year guard built on a false strptime claim, added dotted %m.%d.%Y to close a silent day-first read, and rejected the empty-format strptime(\"\",\"\")→1900-01-01 phantom-date trap at _validate_mapping). Spec Status = CLEARED FOR CODE. Paused for the night; NEXT = TDD (tests/features/import_date_detect/) per the spec's Deliverables + Test plan. 8 commits on main, all pushed.
  Resolved (2026-07-17): shipped by TDD. New pure importers/date_detect.py (detect_date_format + 15 ordered KNOWN_DATE_FORMATS, clock-free, no year guard — strptime separates 2/4-digit widths); friendly per-row RowError in csv_importer (D3); wizard date-format QComboBox + Custom… reveal + auto-detect + live preview + whole-import banner (D4-D8); _validate_mapping rejects the empty-format strptime("","")→1900-01-01 trap (D4). New tests/features/import_date_detect/ (spec.md + 39 tests, 4 layers). Close: /audit semgrep 0; 2 cold review lanes — Lane A (date/money) no reachable defects, Lane B 2 MEDIUM (unblocked matched-profile date-combo re-detect; missing PDF-path tests) + 2 LOW, all folded inline + re-verified. Gate green 1080/1, mypy 0. Tag FIBR-0146-complete.

- ✅ [FIBR-0148] **Deleting a statement silently loses transactions a still-present overlapping statement also covered.**
  Import dedup (services/import_.py `_dedup`, D6/INV-5) is a multiset delta:
  duplicates are DROPPED at import, never stored — the single stored copy is
  stamped to whichever statement imported it FIRST (`statement_period_id`, a
  single-valued column). `StatementService.delete_statement`
  (services/statements.py) deletes exactly that statement's stamped rows and does
  NO re-evaluation of other statements.
  Started 2026-07-17. Chose fix direction (a) ownership hand-off on delete: reassign transactions covered by a remaining overlapping statement to that statement, delete only truly-orphaned rows. Spec docs/specs/FIBR-0148.md.
  Resolved 2026-07-17. Fix direction (a) ownership hand-off shipped: delete_statement now hand_off_covered → delete-orphans → delete-period in one owned transaction; covered rows re-stamped to a remaining same-account statement (ORDER BY period_start,id), never NULL. Spec docs/specs/FIBR-0148.md cold-eyes-converged loop 3 (polish). TDD tests/features/statements/ INV-1..9 (reproduce-first). /audit semgrep 0; cold code-review no correctness defects, 1 LOW test-strength folded inline. Filed FIBR-0149 (confirm-dialog count overstatement, spec D5 follow-up). Gate green 1103/1. Commit d3f113b.

  Concrete data loss: statement A (Jan) imported, then overlapping statement B
  (Jan-Feb) imported — B's January rows are deduped away, only February inserted.
  Delete A -> the January transactions vanish, even though B is still present and
  legitimately covered January. B is not re-imported, so its rows are not
  restored; B now shows a coverage span with a silent hole. For a money app this
  is the unforgivable class (surfaced by a user question 2026-07-17).

  Fix directions (needs a decision — likely a spec + cold-eyes, correctness-
  critical):
  (a) Ownership hand-off on delete: before deleting a row, check whether another
  remaining statement of the same account covers its date (the span+NOT EXISTS
  logic the v6 backfill already uses); if so, REASSIGN its statement_period_id
  to that statement instead of deleting. Cheapest; delete only removes rows no
  remaining statement covers. Caveat: span-overlap is a proxy for "the other
  statement listed it" (true in practice — a statement lists all its period's
  rows).
  (b) Model change: store every imported row linked to its statement (many-to-many
  transaction<->statement), dedup at display/aggregation time. Most correct,
  biggest change.
  (c) Minimum viable: warn on delete when rows would be lost that another
  statement's span also covers, prompting a re-import.
  Kind: fix (data integrity).
  **Layman:** If two statements overlap and you delete one, the shared transactions vanish instead of staying under the statement you kept.
  Kind: fix.
  Source: user-question-2026-07-17.

- ✅ [FIBR-0149] **Delete-statement confirm dialog overstates the count when a statement overlaps another.**
  Surfaced by the FIBR-0148 cold code-review. After FIBR-0148, delete_statement
  hands off transactions a remaining overlapping statement also covers (they
  survive), but ui/statements.py's confirm dialog still says "Delete this
  statement and its %n transaction(s)? This cannot be undone." with %n =
  statement.transaction_count (the FULL linked count). In an overlap delete the
  true deleted count is lower (often 0), so "cannot be undone" + an inflated
  count could scare a user into cancelling a delete they wanted. FIBR-0148 D5
  deliberately deferred this as a follow-up (revisit if users find the count
  confusing). Fix direction: compute the would-orphan count up front (a dry-run
  of the hand-off's NOT-covered set) and word the dialog as "delete this
  statement (N of M transactions will be removed; the rest stay under an
  overlapping statement)"; add the overlap-path confirmation test the review
  noted is currently missing (test_INV10a only covers the non-overlap case).
  **Layman:** When you delete a statement that shares transactions with another one you keep, the "delete its N transactions? This cannot be undone" prompt still counts all N — even though the shared ones now survive under the other statement. The warning should reflect how many actually go.
  Kind: ux.
  Source: indie-review-2026-07-17 (FIBR-0148 close, lane finding LOW).
  Progress (2026-07-18): starting — reproduce-first TDD. Fix: add TransactionRepository.delete_split_counts + StatementService.delete_preview (mirrors CategoryService.delete_blast_radius; UI calls service not repo), branch the confirm dialog so the overlap case names the ACTUAL removed count + reassures the shared rows stay. New overlap-path confirm test (INV-10a only covers non-overlap).
  Resolved (2026-07-18): the confirm dialog now names the ACTUAL removed count on an overlap delete. New TransactionRepository.delete_split_counts -> (removed, kept) reuses hand_off_covered's EXISTS coverage guard byte-for-byte (preview can never disagree with the delete); surfaced via StatementService.delete_preview (UI→service, never repo, mirroring CategoryService.delete_blast_radius). ui/statements.py _on_delete branches: overlap (kept>0) → "%n of its transaction(s) will be permanently removed — the rest are shared with an overlapping statement and will stay"; non-overlap keeps the original wording (now from the fresh count). VaultLockedError-guarded. Reproduce-first TDD: INV-10c (full-overlap A/B, removed==0) fails pre-fix ("its 2 transactions… cannot be undone"), green after. Self-review (too small for /indie-review, per the FIBR-0141 precedent) + gate green 1104/1, mypy 0. Commit 10ee1db.
  Extended, not replaced, by FIBR-0201 (2026-08-03): the preview-wording
  contract now covers the BATCH form. `delete_preview` is the batch-of-one
  case of a new `delete_preview_many`, with its signature and result
  unchanged. The invariant that the preview and the delete share their
  coverage predicate byte-for-byte survives, and is now MECHANICAL rather
  than eye-checked: four inline literals could be compared by reading, but
  once each carries an N-placeholder run they cannot, so all four sites
  interpolate one `_coverage_where_sql` and a test asserts the fragment
  appears twice in each emitted statement. The batch's own trap is that
  SUMMING per-statement previews reports 0 removed for a delete that
  destroys transactions (measured) — one batch-aware call answers it.

- ✅ [FIBR-0151] **Confirmed transfers are not reflected on the Transactions tab.**
  Reported 2026-07-18 with screenshots. In the Transfers tab, the "Confirmed
  transfers" list shows approved transfers (status bar: "Confirmed 1 transfer(s).").
  But on the Transactions tab those same legs (e.g. "Ib transfer to *****9000740
  16H26 *****5235" on Market Link, and the paired Credit Card leg) still appear as
  normal transactions with no transfer marker and (in the shots) a blank Category —
  i.e. confirming a transfer in FIBR-0011's suggest-then-confirm flow does not
  propagate to how the Transactions view renders/labels those rows.
  Root-cause (2026-07-18, subagent-verified): MISSING-WIRING gap, not a
  regression. Confirm correctly records ONE `transfer_pairs` row
  (status='confirmed') via TransferRepository.add_decision
  (repositories/transfers.py:76-80); the `transfer_pairs` table is separate
  (migrations.py:270-277, v7->v8) with NO is_transfer/transfer_id column on
  `transactions`. FIBR-0011 INV-12 ("Transactions untouched",
  docs/specs/FIBR-0011.md:66) DELIBERATELY leaves the transaction rows
  byte-identical on confirm. The Transactions tab
  (TransactionService.list_transactions services/transactions.py:111-125;
  ui/transactions.py refresh:166 + render 223-311) reads only
  transactions/categories/accounts and has ZERO lookup against transfer_pairs or
  the existing `confirmed_transfer_txn_ids()` primitive (FIBR-0011 INV-5) -> the
  two legs keep their blank category and no marker.
  Resolved (2026-07-19): read-time fix. TransactionsView now composes a TransferDetectionService over the same vault and, in refresh(), builds a {txn_id: label} map from confirmed_transfers(); _category_cell shows the directional counterparty label ("Transfer to <credit account>" for the debit leg, "Transfer from <debit account>" for the credit leg). list_transactions() untouched (no tuple-shape change); INV-12 preserved (no transactions row read/mutated). Design chosen by user: directional counterparty naming (not a flat "Transfer" label). Reproduce-first: 2 qtbot tests in tests/features/transfers/test_transfers.py; new contract = transfers spec INV-13. Gate green 1128 passed. Commit 5af8ee6.

  DESIGN DECISION NEEDED before coding (no spec defines how a confirmed transfer
  should render on the tab): options = (a) a "Transfer" pseudo-category / label
  surfaced at READ time by threading confirmed_transfer_txn_ids() into
  list_transactions (must NOT mutate transaction rows -> preserves FIBR-0011
  INV-12); (b) a separate badge/indicator column; (c) exclude transfer legs from
  the tab. Recommend (a) read-time label. Fix stays read/render-side only.

  Reproduce-first: service-level test in tests/features/transfers/test_transfers.py
  -> confirm a transfer, call TransactionService.list_transactions(), assert each
  leg is marked/labelled as a transfer (fails today). Prefer over a GUI test.

  Note: the "Transactions tab" is specced as FIBR-0012 / FIBR-0139, not FIBR-0109.

  Depends-on / relates to FIBR-0011 (transfer detection, shipped) and FIBR-0109
  (dedicated Transactions tab). Reproduce-first: confirm a suggested transfer, then
  assert the two legs are shown as a linked/marked transfer (or excluded/annotated)
  on the Transactions tab. Investigate whether confirm writes the transfer link in
  the DB but the Transactions query/view ignores it, or whether the view needs a
  refresh/signal after confirm.
  **Layman:** When you approve a transfer in the Transfers screen, the two matching transactions still show up as ordinary, uncategorised entries on the Transactions list instead of being marked as a transfer.
  Kind: fix.
  Source: user-report-2026-07-18 (screenshots).

- ✅ [FIBR-0153] **Amount column: show the currency symbol ("R 1,234.49"), not the ISO code, plus a separate Currency column.**
  Current display renders "ZAR1,234.49" — the ISO code is passed as the currency *symbol* to QLocale().toCurrencyString in _format_amount (ui/_amount.py:24; symbol = base_currency() returns the ISO code "ZAR", ui/transactions.py:253), and there is no space. User request (2026-07-19): (a) show the amount with the proper symbol + a space — "R 1,234.49" for ZAR; (b) move the ISO code into its own dedicated "Currency" column on the transactions table. Work: map ISO code -> symbol (ZAR->R) with a space in _format_amount (decide symbol source — a small ISO->symbol table or a QLocale currency-symbol lookup for the base currency); add a Currency column (shifts the _COL_* constants). Also audit the Home tab / charts / PDF export for the same ISO-as-symbol rendering so the fix is consistent app-wide. Interaction: FIBR-0032's "Copy amount" reads the rendered Amount cell text, so it auto-follows the new format (no rework). Needs its own spec -> /cold-eyes -> reproduce-first TDD. Relates to FIBR-0105 (amount display prefs).
  **Layman:** Money currently shows as "ZAR1,234.49", which is hard to read — this makes it show as "R 1,234.49" and puts the "ZAR" code in its own tidy Currency column.
  Kind: fix.
  Lanes: ui.
  Source: user-request-2026-07-19.
  Resolved (2026-07-20, autonomous run): shipped. _format_amount now maps the base-currency ISO code to a symbol via a single-homed CURRENCY_SYMBOLS map (beside CURRENCY_EXPONENTS in services/auth.py) and composes "<symbol> <magnitude>" with one space — "R 1,234.49" not "ZAR1,234.49" — fixing every money site app-wide (Transactions, Home tiles, PDF export) through the one formatter. Magnitude uses QLocale().toString(x,"f",decimals) (symbol-free/grouped/locale-correct), NOT toCurrencyString(v,"") which leaks the ISO code in non-C locales (caught empirically in cold-eyes loop 2). Transactions table gains a dedicated Currency column (_COL_CURRENCY=2, shifting Description/Account/Category to 3/4/5); Copy amount auto-follows. Spec docs/specs/FIBR-0153.md cold-eyes converged loop 5 (CRITICAL mechanism bug caught + fixed). INV-1..9 tested (en_US + en_ZA locale legs; stale 5-col saved-layout safe). Full gate green (1173 passed, 2 skipped). commit 4132649; tag FIBR-0153-complete.

- ✅ [FIBR-0154] **Category UI: expose a 3rd tier (sub-categories) — Type → Category → Sub-category.**
  User asked for 3-tier categories (e.g. Expenditure > Groceries > Spar). Today the app is capped at TWO levels (Type > Category).
  Resolved (2026-07-21): 3rd category tier UI shipped. Spec cold-eyes CONVERGED loop 8 (verify, both cold lanes clean). Reproduce-first TDD: 17 RED INV-1..7 tests → implemented 6 source files (recursive 3-deep render; Add anchored to tree selection with UI depth cap; subject-aware "Move under…" re-parent; breadcrumb pickers via new sub_category_parent_names() map). Service & schema unchanged (cap is UI-only). Gate green 1235 passed; tag FIBR-0154-complete, commit 35131cd.

  Already supported (no work): the data model is a self-referencing tree with no depth cap — `parent_id INTEGER REFERENCES categories(id)` (migrations.py:117-120), `Category.parent_id: int | None` (models.py:230-242); FIBR-0006 shipped it "3rd level ready, no migration needed". `CategoryService.add_category` -> `_require_parent` only checks the parent EXISTS (not that it is a root), with `_reject_cycle` guarding acyclicity (services/categories.py:41-48, 106-116, 118-139) — so the service layer already permits a grandchild. Renaming a leaf (Spar -> Pick 'n Pay) also works today via `update_category` (services/categories.py:50-65) + the Update button (ui/categories.py:125-140).

  The gap is UI-only, deliberately deferred as "D9": the module docstring says "The UI exposes two levels (Type -> Category); a third (sub-category) level is a later enhancement (D9)" (ui/categories.py:9-10). `CategoriesWidget._refresh` renders only root -> one level of children and Add always parents onto the root Type combo (ui/categories.py:212-229, :116) — no control to pick a leaf as parent.

  Scope for this item: (1) CategoriesWidget — allow picking an existing Category as parent and render a 3-deep tree; (2) the category pickers that flatten the tree (Set-category dialog ui/category_picker.py, Rules editor ui/rules.py, Transactions category filter) must render/resolve the deeper level — note the existing flat-combo ambiguity already roadmapped separately; (3) spec -> cold-eyes -> TDD. Decide a max depth (2 vs 3 vs arbitrary) — the model allows arbitrary, but a UI/UX cap keeps the tree legible.
  **Layman:** Let you add a third level under a category (e.g. Expenditure › Groceries › Spar) and pick it when tagging transactions. Note: renaming a category (e.g. correcting "Spar" to "Pick 'n Pay") already works today — this item is only about adding the deeper third level.
  Kind: feature.
  Lanes: ui, services.
  Source: user-request-2026-07-19.

- ✅ [FIBR-0156] **Menu bar: add a "Report an Issue" item to the right of Donate that lets users log an app issue.**
  User wants a menu-bar entry to the RIGHT of Donate for logging an issue with the app. Anchor: the menu bar is File · View · Window · Help · Donate (main_window.py:4); Donate's actions open URLs via self._open_url(...) + QDesktopServices (main_window.py:32, :360-376), mirroring the .github/FUNDING.yml donate-URL pattern.
  Resolved (2026-07-21): shipped a single top-level "Report an Issue" menu-bar action to the right of Donate, opening REPORT_ISSUE_URL (https://github.com/milnet01/finbreak/issues/new) in the OS browser via _open_url — a user-initiated egress, not an app fetch (security-model INV-8), mirroring the Donate pattern. Chose the single-action form (no submenu, no version/OS pre-fill) per shortest-correct; pre-fill remains an easy follow-up. Covered by INV-8b (test_INV8b_report_issue_opens_url); action_report_issue added to the INV-1 canonical set. Gate green (1236 passed). Tagged FIBR-0156-complete.

  Design (for the spec): a new top-level "Report an Issue" menu-bar item positioned after Donate, opening the public repo's issue page (https://github.com/milnet01/finbreak/issues/new) in the user's browser via self._open_url — privacy-preserving and consistent with the local-only model + security-model INV-8 (opening a URL in the browser is NOT app network access, exactly like Donate). Decide: single top-level action vs a small menu ("Report a bug" / "Request a feature" → issues/new?template=...); optionally pre-fill the issue body with __version__ + OS via URL query (?title=&body=&labels=) — no sensitive data. Keep the URL as a module constant near the DONATE_* constants. Needs: spec (tiny) → cold-eyes (self-read; a one-menu-item feature test, not a multi-file design doc) → reproduce-first TDD (mirror the Donate action tests) → close.
  **Layman:** Add a "Report an Issue" button next to "Donate" in the top menu so users can quickly report a bug or request a feature — it opens the project's issue page in their browser (no data leaves the app).
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-07-21.

- ✅ [FIBR-0171] **Cash-flow forecast — project account balances forward from detected recurring income and expenses.**
  Turns finbreak from backward-looking (what did I spend?) into forward-looking (can I afford this?). Reuses the shipped recurring-money detection (FIBR-0142): take the confirmed recurring income + expenses, roll them forward from today's balance, and draw a projected-balance line to a chosen horizon (month-end / N days). Highest value-per-line-of-code of this batch because the detection engine already exists.
  **Layman:** Shows where your balance is heading — e.g. "you'll have about R X left by month-end" — based on your regular income and bills.
  Kind: feature.
  Source: in-session-2026-07-23.
  Started 2026-07-24 (self-directed, user delegated the pick). Design: vault-wide cash-flow forecast reusing RecurringService.confirmed() — net-flow projection by default, upgrades to an absolute projected-balance line when the user enters an optional 'current balance as of today' anchor (stored as a vault setting, shown with its as-of date so a stale anchor is never mistaken for fact). New Forecast tab: projected line chart + upcoming-events list + horizon picker. Pure integer-minor projection core. Spec next → /cold-eyes (max-loops 7) → TDD.
  Shipped 2026-07-24 (TDD). Schema v11 persists each statement's closing balance (statement_periods.closing_balance_minor); the forecast anchors to the sum of per-account balances brought current to today with real post-statement transactions (sum_after, half-open (period_end, today]), then projects the confirmed recurring set forward to a chosen horizon (End-of-month/30/60/90) via the pure Decimal-free project_forecast (reuses _add_cadence). NET_FLOW fallback (line from 0) when no account has a recorded balance. New Forecast tab after Recurring. INV-1..13 green; gate green.

- ✅ [FIBR-0172] **Spending alerts — flag unusual spend, a newly-appeared recurring charge, or a missed expected debit.**
  A notice layer on top of recurring detection (FIBR-0142) + category history: (a) new recurring charge detected this period, (b) a category's spend is N× its rolling average, (c) an expected recurring debit did not post. Non-intrusive surfacing (dashboard banner / list), user-dismissable. Pairs naturally with the cash-flow forecast.
  **Layman:** Quiet nudges when something changes: a new subscription starts, one category spikes well above normal, or an expected payment didn't arrive.
  Kind: feature.
  Source: in-session-2026-07-23.
  Resolved 2026-07-24 (self-directed autonomous run). Three dismissable Home-dashboard alerts: (a) new recurring OUT charge (suggested stream, occurrences<=4 — cadence-agnostic "just detected"); (b) category spike (last COMPLETE month >= 2x prior-3-month integer average, confirmed-transfer + None-bucket excluded so totals match the donut); (c) missed expected debit (confirmed OUT overdue past next_expected+3d). Pure integer-only detectors + AlertService (sole Decimal->minor in input prep); new v12 alert_dismissals table (recurring_decisions idiom), persisted per-scope dismissal keys; non-intrusive AlertsCard (hidden when empty, VaultLockedError-silent dismiss, card-local rebuild). Spec docs/specs/FIBR-0172.md cold-eyes CONVERGED loop 3 (caught + fixed a monthly-detector-dead boundary hole, a snapshot.confirmed AttributeError, an INV-15 Decimal leak, and a cross-feature v12 drift-guard conflict). Reproduce-first TDD tests/features/spending_alerts/ (32 tests +1 folded, INV-1..19); /audit semgrep 0 + cold code-review 0 defects; gate green 1360 passed. Schema 11->12 rippled 12 feature guard files + reworked the FIBR-0177 reconciliation guard. Journal docs/journal/FIBR-0172.md.

- 📋 [FIBR-0173] **Savings goals — track progress toward a target amount, distinct from spending budgets.**
  Budgets cap spending; goals build toward a target — a separate concept from the planned Budgets item (FIBR-0022). Per-goal: name, target amount, optional target date, current progress (linked account balance or manual contributions), and an on-track / behind indicator.
  **Layman:** Set a target like "R10,000 holiday fund" and watch a progress bar fill as you save toward it.
  Kind: feature.
  Source: in-session-2026-07-23.

- 📋 [FIBR-0174] **Tax-year summary — per-category totals for a chosen tax year with a tax-deductible flag, exportable to PDF/CSV.**
  Adds a "tax-deductible" flag to categories and a tax-year report view (configurable year boundary for the SA Mar–Feb tax year). Reuses the existing PDF (services/pdf_export.py) and the planned plain-data CSV export (FIBR-0093). Locally useful given the SA bank focus.
  **Layman:** A one-click annual report of what you earned and spent per category for a tax year, with deductible categories flagged — ready for filing.
  Kind: feature.
  Source: in-session-2026-07-23.

- 📋 [FIBR-0175] **Compare periods on the dashboard — this month vs last, this year vs last year, side by side.**
  The dashboard shows one period at a time (FIBR-0143). Add a compare toggle that renders a second period alongside the current one with per-category deltas (up/down arrows + amount/percent). Small addition to the existing reporting aggregation for a big 'aha'.
  **Layman:** See two periods next to each other so you can spot what went up or down.
  Kind: feature.
  Source: in-session-2026-07-23.

- 📋 [FIBR-0176] **Receipt attachments — attach a photo/PDF of a receipt to a transaction, stored inside the encrypted vault.**
  Store attachment blobs inside the SQLCipher vault (not on disk) so they inherit the same at-rest encryption as transactions. Needs a size cap (reuse the INV-5b resource-size cap pattern) and a schema/migration for an attachments table. Fits the privacy-first, everything-encrypted design.
  **Layman:** Keep a picture of a receipt with its transaction, encrypted like everything else.
  Kind: feature.
  Source: in-session-2026-07-23.

- ✅ [FIBR-0177] **Account-level balance reconciliation — verify imported transactions sum to the bank's stated balance for every account.**
  Generalises the Standard Bank import-time reconciliation (importers/standard_bank.py: opening ± total vs closing) into a visible, ongoing account-level check: opening balance + running sum of transactions vs the latest known statement balance, surfaced as ✓ / off-by-R-X. Catches import gaps for every account and every bank, complementing the planned statement coverage/gap detection (FIBR-0038) and running-balance work (FIBR-0094).
  **Layman:** A tick that confirms your imported transactions add up to the balance your bank states — or flags the gap — for any account, not just at import time.
  Kind: feature.
  Source: in-session-2026-07-23.
  Started 2026-07-24 (self-directed autonomous run). Spec docs/specs/FIBR-0177.md drafted: v1 reconciles current+savings cash accounts only (debt/investment/other deferred — persisted closing sign convention is canonical only for asset accounts); cross-statement telescoping over persisted closing balances (C_prev + sum_after(P_prev,P_curr] == C_curr, exact), reusing FIBR-0171 primitives; Accounts-tab per-account marker; no schema change. Next: /cold-eyes.
  Resolved 2026-07-24 (self-directed autonomous run). v1 reconciles current+savings cash accounts via cross-statement telescoping over persisted closing balances (C_prev + sum_after(P_prev,P_curr] == C_curr, exact integer minor units); debt/investment/other quietly NOT_SUPPORTED (deferred v2 — their persisted closing sign convention differs). Accounts-tab per-account marker. No schema change. Spec docs/specs/FIBR-0177.md cold-eyes CONVERGED loop 3; reproduce-first TDD tests/features/reconciliation/ (20 tests, INV-1..12); /audit semgrep 0 + cold code-review 0 defects; gate green 1327 passed. Surfaced + filed FIBR-0179 (forecast anchor debt-account sign bug). Journal docs/journal/FIBR-0177.md.

- 📋 [FIBR-0178] **Cash-flow forecast v2 follow-ups (FIBR-0171 D12, logged not dropped).**
  Deferred out of the FIBR-0171 v1 cash-flow forecast (spec D12),
  logged so they are not lost: (a) a user-typed manual balance
  override for balance-less accounts (CSV-only), so those accounts can
  contribute to the anchor without waiting for a balance-bearing
  statement; (b) per-account (rather than vault-wide) forecasts;
  (c) scenario / what-if one-off inputs (a known future cost the
  recurring engine won't model); (d) a CSV balance-column mapping so a
  CSV import can persist a closing balance too. Multi-currency forecasts
  stay out of scope and are tracked by FIBR-0087.
  **Layman:** Optional extras for the new Forecast tab, deferred from v1.
  Kind: feature.
  Source: FIBR-0171 spec D12 (in-session 2026-07-24).

- ✅ [FIBR-0179] **Forecast anchor mishandles debt-account (credit-card / loan) closing balances — wrong-sign roll-forward + an owed figure folded into the vault-wide cash total.**
  ForecastService._anchor (services/forecast.py) sums
  latest_closing_balances() across ALL account types with
  `current = balance_minor + roll_minor` (a plain `+`, no type dispatch).
  But a debt product's persisted closing_balance_minor is stored in the
  "owed" convention (positive = debt, as the statement prints it), the
  OPPOSITE sign to the canonical amount_minor (debit −/credit +). So for a
  credit-card / home-loan / personal-loan account the `+ roll_minor`
  brings the balance current in the WRONG direction, AND the owed figure
  is folded into a vault-wide "cash" total as if it were an asset (doubly
  wrong). Reachable: Family C credit-card statements always persist a
  closing (the SB checksum raises on a missing closing for non-savings
  families), so a credit-card account contributes to the anchor. Verify
  first (write a failing forecast test with a credit_card account + a
  post-statement transaction) then fix — likely by canonicalising the
  closing per AccountType, or by excluding debt/investment accounts from
  the anchor. Related: FIBR-0177 sidesteps this by scoping reconciliation
  to current+savings; the loan display-inversion roadmap note keeps
  amount_minor canonical while inverting only at display.
  **Layman:** The new Forecast's starting balance can be wrong for credit-card and loan accounts — it needs a per-account-type sign fix (or to leave debt accounts out of the total).
  Kind: fix.
  Source: in-session-2026-07-24 (surfaced by FIBR-0177 cold-eyes, spec D9).
  Resolved (2026-07-25): verified first — a RED test proved a
  credit-card account with a persisted closing balance (R1200 owed)
  was anchored as +R1200 of *cash*, and a post-statement purchase
  rolled it the wrong way. Fixed by narrowing the anchor to CASH_TYPES
  (current + savings) in ForecastService._anchor — the same gate
  FIBR-0177 D1 applies, for the same sign-convention reason. Debt /
  investment / other accounts now contribute nothing; a vault whose
  only balance-bearing account is a debt account falls back to
  NET_FLOW. The Forecast tab's provenance line gained a second
  exclusion clause so a type-excluded account is no longer mislabelled
  "no recorded balance yet". Contract: tests/features/forecast/spec.md
  INV-14 (3 new tests); FIBR-0171 §D1 carries an amendment note. Gate
  green 1363 passed, 2 skipped.

- ✅ [FIBR-0185] **Move the Home alerts card behind an Alerts button + dialog, so alerts never reflow the dashboard.**
  Verified 2026-07-28 from a user screenshot: the alerts card renders inline at
  the TOP of the Home dashboard, above the period picker. With 4 alerts it
  occupies ~120px and pushes the whole dashboard (period picker, Net line, the
  three donut columns, Spending/Income/Transfers panes, the recurring card, the
  trend chart) down the page. Dismissing one alert pulls everything back up. So
  the dashboard's vertical layout is a function of how many alerts happen to be
  open — the thing the user is reading moves under them as they read it.
  Resolved 2026-07-28. The inline alerts card is gone from the Home
  dashboard; alerts now sit behind an "Alerts (N)" button on the selector
  row, which opens a new AlertsDialog (src/finbreak/ui/alerts_dialog.py)
  listing every open alert with its per-alert dismiss control. The FIBR-0172
  alert model, detectors and dismissal store are untouched — the rows and the
  VaultLockedError-silent dismiss handler moved out of HomeView verbatim.
  Button states are theme-driven, not hard-coded: ThemeTokens grew a ninth
  `attention` token (dark on the three light themes, light on the three dark
  ones, so it reads against each window), and build_stylesheet fills
  QPushButton#alerts_button with it — with a separate :disabled rule so "no
  alerts" sits quietly. The dialog opens through the shell's tracked
  _open_dialog(defer=False) path (auto-lock tears it down) and emits `changed`
  after each dismiss, which the shell routes to HomeView.refresh_alerts() so
  the count stays live. Net effect: the dashboard's top row is fixed-height
  whatever the alert count. Tests: tests/features/spending_alerts/
  test_alerts_ui.py (9 legs, replacing test_alerts_card.py) + a theme leg
  pinning the attention token's light/dark posture and the button's QSS.

  User's chosen design (they weighed the alternative and rejected it): NOT a
  separate Alerts tab — a tab is easy to never open, and would need its own
  attention-drawing mechanism anyway. Instead an **Alerts button** on the Home
  header row that opens an **Alerts dialog** listing every open alert with its
  per-alert dismiss control (the same dismissals that already persist, FIBR-0172).

  Button states:
  - alerts outstanding → an attention colour DRAWN FROM THE ACTIVE THEME (six
  themes ship; no hard-coded red — each theme needs a legible attention/danger
  role, and the light themes need a different value from the dark ones).
  - none outstanding → disabled, styled to sit quietly in the theme.
  A count on the face ("Alerts (4)") is the cheap way to make the state readable
  without opening it.

  Net effect: the dashboard's top row becomes fixed-height whatever the alert
  count, which is the actual complaint. Pairs with the fixed-size work below,
  and largely subsumes it — alerts are the only element on Home whose height
  varies with data.

  Reuse: the alert model, detectors and dismissal persistence all shipped with
  FIBR-0172; this is a presentation change, not new alert logic. The dialog
  should go through the shell's tracked _open_dialog path (auto-lock tears
  dialogs down — INV-9), not exec().
  **Layman:** Alerts move into a button that opens a list. The button lights up when something needs attention, so the dashboard below it stops jumping around every time an alert appears or is dismissed.
  Kind: ux.
  Source: user-request-2026-07-28 (screenshot).

- ✅ [FIBR-0186] **Give the Home dashboard a fixed layout that scrolls when the window is too small, instead of reflowing.**
  User request 2026-07-28, alongside the Alerts-button item above: "Set a fixed
  size for everything on the dashboard so that if someone makes the window too
  small, it means they will have to scroll to see everything."
  Decision (2026-07-28, user): take the MINIMUM-size + QScrollArea route, not
  literal per-widget fixed pixel sizes. Same user-visible behaviour (the layout
  stops squashing; a too-small window scrolls) without clipping text for anyone
  running larger system fonts or display scaling. This closes the design note
  above — build it that way.
  Resolved 2026-07-28. As decided, the minimum-size + QScrollArea route, not
  literal per-widget fixed sizes. The scroll area already existed (FIBR-0012
  D1) with no floor under it, so the only change was a floor:
  `dashboard_content` (the scrolled content widget) now carries
  setMinimumSize(880, 620). Below that the viewport scrolls instead of
  squashing the three donut columns into slivers; above it the layout is still
  free to grow, so larger system fonts / display scaling widen rather than
  clip. The floor is on the content only — HomeView's own minimumSizeHint
  stays small, so the window is never pinned open. Tests:
  tests/features/dashboard/test_min_size.py (3 legs; verified
  discriminating — two fail with the setMinimumSize line removed).

  DESIGN NOTE — recommend implementing this as a MINIMUM size plus a scroll area,
  not as hard-coded pixel sizes on each widget. Same user-visible behaviour (the
  layout stops squashing; a too-small window scrolls), but:
  - setFixedSize on text-bearing widgets CLIPS rather than scrolls when the user
  runs a larger system font or a HiDPI scale factor — an accessibility
  regression, and finbreak already ships "Follow system" theming, so honouring
  system display settings is the established posture;
  - a minimum size is one property per pane instead of a width AND height per
  widget, and it cannot drift out of sync with the content it wraps.
  The concrete shape: wrap Home's content in a QScrollArea with
  setWidgetResizable(True), give the content widget a sensible minimum width and
  height, and let the existing layouts do the rest. Scrollbars appear only when
  the window is smaller than that minimum.

  Sequencing: land the Alerts button FIRST. Alerts are the only Home element whose
  height varies with data, so that change removes most of the observed movement
  on its own, and it will be clearer afterwards how much of this item is still
  needed — possibly only the scroll area.

  Test posture: qtbot legs asserting the content keeps its minimum size when the
  window is shrunk below it, and that the scroll area becomes scrollable rather
  than the panes shrinking. Per qtbot-visibility notes, probe with isHidden()
  rather than isVisible() for widgets on a non-current page.
  **Layman:** The dashboard keeps its shape no matter the window size — make the window small and you scroll to see the rest, rather than everything squashing and rearranging.
  Kind: ux.
  Source: user-request-2026-07-28 (screenshot).

- ✅ [FIBR-0187] **The Import-statement preview table forgets its column widths between imports.**
  Verified 2026-07-28 (user screenshot + source read). The import preview table is
  built at src/finbreak/ui/import_wizard.py:272 as a plain QTableWidget(0, 5) with
  setHorizontalHeaderLabels — and never calls remember_columns(), the helper in
  src/finbreak/ui/_table_state.py that every other table uses (transactions.py,
  recurring.py, statements.py, transfers.py, rules.py all import it). It also has
  no objectName, which remember_columns needs as its settings key
  ("columns/<objectName>").
  Resolved (2026-07-28): SHIPPED by TDD. The preview table was the one table built without remember_columns. Gave it objectName "import_preview_table" (the helper keys saved state on it; unnamed would share the empty "columns/" key and cross-corrupt the other tables) and called the existing helper — no new code. Columns are now drag-reorderable too, from the same call. 2 new tests, both failing before. Gate: 1401 passed.

  So this is a missed call-site, not missing capability: remember_columns already
  restores widths + column order + sort on construction and re-saves on every
  resize/reorder/sort, keyed by objectName in the window INI. The fix is to give
  the preview table an objectName and call remember_columns on it — rule-of-reuse
  case (a), call the existing helper directly, no new code.

  Side benefit, worth noting because it is the same one line: remember_columns
  also sets setSectionsMovable(True), so the preview's columns become
  drag-reorderable like the rest of the app's tables.

  Reproduce-first: a qtbot leg that widens a preview column, rebuilds the wizard,
  and asserts the width survived — mirroring whatever the existing table_state
  suite (tests/features/table_state/) already does for the shipped tables, which
  is the pattern to copy rather than invent.
  **Layman:** Widen a column while checking an import and it snaps back to the default next time you import — unlike every other table in the app, which remembers.
  Kind: fix.
  Source: user-request-2026-07-28 (screenshot).

- ✅ [FIBR-0189] **Allow only one running finbreak instance; a second launch raises the existing window.**
  User request 2026-07-28: "ensure that the app can only have one running
  instance (if we need to change this in future we can revisit this)" — so
  single-instance is the intended behaviour, not a configurable one for now.
  Resolved (2026-07-28): SHIPPED by TDD. src/finbreak/single_instance.py — QLocalSocket probe then QLocalServer listen, wired in app.py::run before any window is built. Handles all three traps: a kill -9 stale socket (removeServer before listen, safe only because the probe ran first) that would otherwise make the app permanently unlaunchable; the update relaunch (_release_for_relaunch frees the socket before the key wipe, since apply() ends in os._exit and runs no cleanup — else the replacement would probe a live owner and silently exit); and per-user scoping (the socket lives in a shared temp dir on Unix). Fails OPEN. 8 tests + spec.md. auto_update INV-6 re-pointed from callback IDENTITY to behaviour. Gate: 1411 passed.

  Two reasons this is worth more than tidiness:
  1. It is a likely contributor to the duplicate panel icon in FIBR-0188 —
  a second process is a second window, and no launcher association can
  merge those. Fix both; neither subsumes the other (0188 is a launcher
  NAMING mismatch that bites even with a single process).
  2. VAULT SAFETY. The vault is one SQLCipher file. Two instances with it
  open are two writers against the same database — at best the second
  one's writes race the first's, at worst a torn write during an import
  or migration. The app has no cross-process locking today. Worth
  verifying whether concurrent open is already possible before assuming
  it is: if SQLite's own locking already refuses the second opener, the
  symptom is a confusing error rather than corruption, but either way
  one instance is the answer.

  Implementation — Qt's canonical single-instance pattern, no new dependency:
  QLocalServer / QLocalSocket. On start, try to connect to a named socket keyed
  per USER (not a fixed global name — a multi-user machine must not have one
  user's launch bounce off another's, and the socket must live in the user's
  runtime dir). Connect succeeds => an instance is live: send a "raise" message,
  then exit(0) without building a window. Connect fails => become the owner,
  listen, and on each incoming connection raise + activate the existing window
  (show(), raise_(), activateWindow(), and un-minimise if needed).

  Care needed, and these are the parts that actually bite:
  - STALE SOCKET after a crash or SIGKILL: a leftover socket file makes every
  later launch think an instance is live and silently exit — the app becomes
  unlaunchable. QLocalServer.removeServer(name) before listen() is the
  standard guard; the connect-first ordering means a LIVE owner still wins.
  - The AppImage relaunch path (FIBR-0054/0131 self-update) spawns the new
  binary from the old one. The old process must have released the socket
  before the new one listens, or the update relaunch turns into a silent
  no-op — exactly the class of bug the 0.1.2->0.1.3 "closed but didn't
  reopen" relaunch fix was. Sequence this against os._exit in the installer.
  - The --self-test entry point (_selftest.py builds its own QApplication)
  must NOT take the lock, or a self-test while the app is open would exit 0
  having tested nothing.

  Test posture: the socket layer is testable headlessly — a first "instance"
  listens, a second attempt detects it and reports "already running" without
  building a MainWindow; a removed/stale socket still allows a fresh start. The
  window-raising itself is a qtbot leg on the handler, not on real cross-process
  focus (which is compositor policy and empirical, like the FIBR-0131 legs).
  **Layman:** Clicking finbreak when it's already open brings up the window you already have, instead of starting a second copy.
  Kind: feature.
  Source: user-request-2026-07-28.

- ✅ [FIBR-0190] **A current Standard Bank Current-account statement imports ZERO of its 183 rows — the "Payments / Deposits" column layout matches no Family signature, and the generic fallback can't split the columns.**
  Verified 2026-07-28 against a real 12-page, 3-month SBSA Current-account
  statement (2026-02-28 -> 2026-05-27, 183 transaction rows; NOT committed —
  personal data, see "needs a sample" below).
  Sample located (2026-07-28): the user supplied the path to the real
  statement this diagnosis was made against —
  /mnt/Emulators/storage_backup_2026-05-08/Statements/Current/SBSA_Statement_2026-05-28_3-months.pdf
  (LOCAL ONLY — real payees and balances; it must NEVER be committed, and
  nothing derived from it may enter tests/fixtures/ un-anonymised). So the
  blocker is no longer "no access to the layout" but "no committable
  fixture": the work is to hand-build an anonymised copy in the same layout
  (fictional payees, made-up amounts, recomputed running balance so the
  existing balance checksum still passes) the way the current
  standard_bank fixtures were produced, then fix detect_standard_bank
  against it and re-verify once against the real file locally.

  BOTH import paths fail, so the user sees no importable rows at all:

  1. The dedicated reader returns None (unrecognised -> generic fallback).
  `_LEGAL_MARKER` IS present, so it is definitely an SB statement, but every
  family signature misses. The statement's transaction header line is:
  `Date Description Payments Deposits Balance`
  Family A wants debits+credits+date+balance (window 3) — "credits" appears
  NOWHERE in the document. Family D wants withdrawals+deposits+balance —
  "deposits" is present but "withdrawals" is not. C and B miss outright.
  So this is a FIFTH transactional layout: the money-out column is headed
  **Payments** (not Debits) and money-in **Deposits** (not Credits).

  2. The generic PDF fallback finds a table but cannot use it. `candidate_tables`
  returns 2 candidates; candidate 1 has the correct 5-cell header
  ['Date','Description','Payments','Deposits','Balance'] and 183 data rows —
  but the DATA rows are not column-split: the whole row lands in cell 0
  (e.g. "28 Feb 26 &lt;desc&gt; -250.00 4,278.15\n&lt;continuation&gt;"), because the
  page has no ruling lines for pdfplumber to split on. Result: CsvImporter
  with a Payments/Deposits debit/credit ColumnMapping yields
  **drafts=0, errors=183** under every date format tried
  (%d %b, %b %d, %d %m, %m %d, %d/%m/%Y, %m/%d/%Y, %d %m %Y).

  Observed row shape (useful for the grammar): `DD Mon YY  &lt;description&gt;
  &lt;signed amount&gt;  &lt;running balance&gt;`, with a wrapped continuation line
  carrying the rest of the description — i.e. date-first with an already-SIGNED
  single amount plus a balance tail, which is closer to the existing Family-C /
  fold-based row parsing than to Family A's column pair. The region opens with
  `STATEMENT OPENING BALANCE &lt;amount&gt;` and terminates on the existing
  "please verify" terminator, both already handled.

  Suggested shape: add this as a new Family (or a Family-A variant) —
  `detect_standard_bank` needs a signature on `date`+`description`+`payments`+
  `deposits`+`balance`, and a row grammar for the date-first signed-amount +
  balance form, reusing `_fold` / `_anchor_balance` / `_verify_row` and the
  existing running-balance checksum (which this layout CAN satisfy — it prints a
  balance on every row plus an opening balance). Note "Payments" is a money-OUT
  column here, which inverts the usual reading of that word — worth a comment.

  Needs a sample: the verification file is a real statement with real balances
  and payees, so it cannot go in `tests/fixtures/`. Blocked on a hand-anonymised
  copy (same layout, fictional payees/amounts, recomputed running balance) the
  way the existing standard_bank fixtures were produced. Same blocker class as
  FIBR-0074, but this one is Standard Bank — a bank the app already claims to
  support — so it is a REGRESSION-grade gap, not a new-bank feature.
  **Layman:** A real Standard Bank statement won't import at all right now — the reader doesn't recognise this newer page layout, and the manual fallback can't tell the columns apart either.
  Kind: fix.
  Lanes: importers, tests.
  Source: user-request-2026-07-28 (real statement checked in-session).
  Spec ACCEPTED (2026-08-03): docs/specs/FIBR-0190.md, converged after 4
  cold-eyes loops (2 cold lanes each). Not yet implemented — next step is TDD,
  red first.

  Corrections to this bullet, all measured against the real statement:
  - 182 transaction rows, not 183. The generic fallback's "183 data rows"
  counted the STATEMENT OPENING BALANCE line as a row.
  - The statement prints NO closing balance anywhere in 12 pages, and no
  "Statement from ... to ..." period line (it prints From:/To:). So Family E
  must NOT join Family A's period-is-None refusal, or every E statement
  bricks.
  - The balance's minus is LEADING (-730.55), the opposite of Family A's
  trailing convention. 0 of 182 rows carry a trailing-minus balance.
  - Row dates are Title-case on all 182 rows, so _MON_RE needs no re.I.
  - The last page prints Payments / Deposits column totals and both are EXACT
  column sums, so Family E gets a real completeness gate where Savings has
  none — it catches a truncated tail, which the per-row running-balance chain
  is blind to.

  The spec's design point the reviews kept returning to: parse()'s family chain
  ends in a bare `else: _parse_family_c(...)`, so omitting an explicit
  `elif family is Family.E` routes every E statement into the credit-card
  parser, which does not fail cleanly — it matches with the balance captured as
  the amount, sign-flipped. Wrong money, no exception.
  Resolved (2026-08-04): Family E shipped per docs/specs/FIBR-0190.md.
  detect_standard_bank gains the five-token "Date Description Payments
  Deposits Balance" signature in the slot C->D->E->B->A; _E_ROW parses
  `D[D] Mon YY desc [-]amount [-]balance` (both minuses LEADING, the
  opposite of Family A); _looks_like_row/_fold gained an OPT-IN dmy_lead
  keyword so no other family's fold changed; _anchor_balance and
  _capture_opening learned "statement opening balance"; _cc_iso became the
  shared _dmy_iso. E prints no closing figure, so its completeness gate is
  _verify_e_totals against the printed Payments/Deposits column totals,
  each verified independently on magnitudes in minor units — and
  closing_balance_minor is supplied only when BOTH printed and verified.
  8 synthetic reportlab fixtures + 46 test legs; 8 mutations of the new
  code were each caught by at least one leg. Suite 1610 passed / 2 skipped.
  Cross-doc: FIBR-0050 (5 enumerations that said "A/B/D" or named Savings
  as the sole closing-less family), the test contract, CHANGELOG.

- 📋 [FIBR-0191] **Amount-range (min/max) filter on the Transactions tab.**
  Split out of FIBR-0109 (2026-07-28) as the one piece its absorb target
  did not build. FIBR-0012 shipped the Transactions tab
  (src/finbreak/ui/transactions.py) with search + date-range + account +
  category filters, all combinable; the amount-range (min/max) filter
  FIBR-0109 originally named was deliberately NOT chosen in the FIBR-0012
  brainstorm and is recorded under Out-of-scope in
  docs/specs/FIBR-0012.md. The user confirmed on 2026-07-28 that it is
  still wanted, so it is re-filed here rather than left implicit in a
  closed bullet.

  Scope: two optional amount inputs (min, max) in the existing Transactions
  filter bar, combinable with every filter already present, pushed into the
  same query/where layer the other filters use — not a post-filter in
  Python. Decisions the spec must settle, none of them obvious:

  - Whether the comparison is on the SIGNED amount or its magnitude. The
  app stores money-out as negative, so "over 1000" most likely means
  |amount| >= 1000 to a user, but a signed reading is defensible and the
  two disagree on every debit. Getting this wrong is a wrong-total class
  bug, so it needs an explicit invariant either way.
  - Whether a blank input means unbounded on that side (expected) and how
  min &gt; max is handled — refuse, swap, or return empty.
  - Currency: FIBR-0087 (per-account currency) and FIBR-0111 (currency in
  its own column) are both open, so a mixed-currency vault would compare
  unlike amounts. Either scope this to the single-currency case with a
  note, or gate it on those items.
  - Whether the range participates in the saved per-tab filter state the
  other Transactions filters use.

  Reuses the existing list_transactions read path and the tab's current
  filter plumbing; no new repository. Dependencies: FIBR-0012 (✅).
  **Layman:** Let people narrow the transaction list to amounts between two figures — e.g. "show me everything over R1 000" — alongside the search, date, account and category filters already there.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-07-28.

- ✅ [FIBR-0192] **Finish FIBR-0084: the shared column scheme on the last unwired headers, and make Reset layout actually reset columns.**
  Split out of FIBR-0113 on 2026-07-28 after a /cold-eyes loop-2 pass found
  that FIBR-0113's fold-in of this work was the single largest source of
  defects in that spec (4 of 5 criticals). Splitting keeps each item inside
  the review's design point; nothing is dropped. FIBR-0084 stays OPEN until
  this ships — FIBR-0113 alone does not close it.

  Three gaps, each verified against source on 2026-07-28, not recalled:

  1. ui/forecast.py::ForecastWidget._make_table builds a 4-column
  QTableWidget, already named "forecast_events" and otherwise configured
  like its siblings, but forecast.py imports nothing from _table_state — so
  its columns are neither reorderable nor remembered. CAUTION: its filler
  _fill_events uses a bare setRowCount + setItem loop with NO fill_guard,
  unlike every other sorted table (statements / transactions / transfers /
  recurring). So add remember_columns ONLY — adding enable_sorting without
  first wrapping the fill in fill_guard lets Qt re-sort mid-fill and render
  a running balance against another event's date. Wrap the fill first if
  click-sorting is wanted.

  2. ui/home.py's dashboard breakdown trees: QTreeWidget with
  setColumnCount(2), a VISIBLE header (setHeaderLabels Name / Amount) and
  objectName "dashboard_breakdown_<key>". home.py imports nothing from
  _table_state. FIBR-0084's own text names this surface — "Make each
  QTableView/QTreeView header user-resizable AND movable ... Covers every
  relevant table: Statements, Home transactions, Accounts, Categories,
  Rules" — so it is in scope by that bullet's wording (user confirmed
  2026-07-28). Note _table_state.remember_columns is typed
  `(table: QTableWidget)`; a QTreeWidget is not one, so the helper needs its
  parameter widened to the common base (both expose horizontalHeader /
  header via QAbstractItemView + QHeaderView) or a sibling overload. That
  signature widening is the only non-trivial piece of this item.

  3. main_window.py::MainWindow._reset_layout removes exactly _KEY_GEOMETRY,
  _KEY_STATE and _KEY_SIZE. It never touches the "columns/<objectName>"
  entries remember_columns writes, so Reset layout silently leaves every
  table's saved column layout in place — which is what FIBR-0084's bullet
  asks for and does not have. QSettings.remove("columns") drops the whole
  group. Two cautions found in review: the action does NOT rebuild the
  workspace, so live headers keep their restored state until restart unless
  they are also reset in place; and the existing self.resize(...) runs AFTER
  settings.sync(), which can emit sectionResized on a live table and write
  "columns/<name>" straight back. Order the clear accordingly and assert the
  user-visible outcome, not just an empty INI.

  Deps: FIBR-0117 (the _table_state seam), FIBR-0113 (lands the Accounts
  table; independent of this). Blocker for: FIBR-0084's ✅ flip.
  **Layman:** Let people resize and reorder the columns on the Forecast tab and the Home dashboard's category breakdown lists — the last two places that still can't — and make the "Reset layout" menu item put columns back to their defaults, which it currently doesn't do.
  Kind: feature.
  Lanes: ui.
  Source: cold-eyes-2026-07-28 (FIBR-0113 loop 2).
  Spec ACCEPTED 2026-07-31 (docs/specs/FIBR-0192.md) — /cold-eyes
  converged after 4 loops plus a mid-run split. Totals: 1 CRIT, 10 HIGH,
  29 MED, 34 LOW verified and ALL fixed; 9 unverified/dismissed. No
  deferred tail — nothing was left open.

  The split (loop 3->4): the ratio stop-trigger fired twice (collateral
  outnumbering draft defects two loops running), so the ten measured Qt
  facts and their probe scripts moved to docs/specs/FIBR-0192-qt-facts.md
  with permanent ids QT-1..QT-10, and all citations were retargeted off
  the position-dependent "2.1 row N" form. That doc is a REFERENCE —
  /doc-lint checks it, not /cold-eyes.

  Three findings that would have shipped bugs: (1) saveState() serialises
  the sections-movable flag, so a capture one line early would have
  turned drag-reorder off app-wide; (2) it ALSO serialises the sort
  indicator, so a capture before enable_sorting would make the sort arrow
  vanish; (3) a sortable view's re-sort rides on sortIndicatorChanged, so
  the blockSignals guard an earlier draft specified would have
  desynchronised the arrow from the rows on five shipped tables. All
  three were found by RUNNING Qt, not by reading it.

  Next: TDD the implementation (8 invariants, 7 test functions in
  tests/features/table_state/ plus the mypy gate stage).
  Resolved (2026-08-02): implemented TDD off the accepted spec. `remember_columns` widened to `QTableWidget | QTreeWidget` via `_header_of`, capturing the build-time header state into a `finbreak_default_header_state` dynamic property after `setSectionsMovable(True)` and before the restore; new `reset_columns(root)` sweeps `findChildren` and restores it (NOT under `blockSignals`); `_reset_layout` reordered to resize -> centre -> reset_columns -> clear -> sync. Two new call sites: `forecast.py::_make_table`, `home.py::_build_column`. Seven legs in tests/features/table_state/ (INV-1,2,3,5,6,7,8) plus mypy for INV-4; suite 1455 passed / 2 skipped.

  Three spec claims measured NARROWER than written, and the spec was amended rather than the tests bent to fit: (1) INV-6 needed a fourth precondition — the Transactions tab must be the CURRENT tab, or a QTabWidget gives its page no layout pass and the reset's resize emits no `sectionResized` at all, leaving the leg vacuous; (2) INV-6 does NOT discriminate the clear-first/clear-last ordering — `reset_columns` and `settings.remove("columns")` are redundant in-process, so the INI holds the default state under either ordering; (3) consequently nothing covers the clear itself. §4.4's ordering is kept on correctness grounds (it does not depend on which Qt emission timing occurs), and §11 now carries six `nothing` rows instead of four plus a `partly`.

  Verified by mutation, not by reading: capture-before-movable, capture-after-restore, drop-reset_columns, drop-home-call, drop-forecast-call and the narrowed mypy type each turn the expected leg red.

- ✅ [FIBR-0193] **Account storage: migration v13 adds nullable accounts.account_number + accounts.note, carried through model / repo / service.**
  Split out of FIBR-0113 on 2026-07-28, executing the recommendation
  /cold-eyes loop 5 made when that spec did not converge (35 verified
  findings; docs/reviews/FIBR-0113-cold-eyes-loop5.md). FIBR-0113 was 985
  lines against a ~567-line median, and three NEW structural draft defects
  appeared at loop 5 after four cold reads missed them — the size trigger in
  /cold-eyes Phase 5. This half was the quietest lane in that loop: zero
  CRITICAL, one HIGH, all findings local.

  SHIPS FIRST. FIBR-0113 (the 5-column Accounts table and the masking)
  reads and writes these two columns, so it cannot start until they exist.
  FIBR-0198 (the reveal toggle) follows FIBR-0113.

  Scope — the storage half of FIBR-0113's original design:
  - migrations.py: LATEST_SCHEMA_VERSION 12 -> 13 and a _migrate_to_v13 step
  issuing two nullable ADD COLUMNs inside one owned_transaction.
  - models.Account gains account_number + note, appended after created_at.
  - repositories/accounts.AccountRepository: both listing SELECTs grow the
  two columns in dataclass field order (Account(*row) is positional), and
  add() / update() grow the two parameters, REQUIRED not defaulted.
  - services/accounts.AccountService: add_account's are optional keyword
  args, update_account's are REQUIRED — an unconditional UPDATE ... SET
  means a defaulted None silently erases a stored value at every one of
  the six existing three-argument call sites.
  - A module-level _normalise_optional in services/accounts.py, called by
  BOTH write paths, so a blank field stores SQL NULL rather than "".

  Also carries FIBR-0086's bullet amendment: FIBR-0086 currently claims the
  account-number STORAGE half ("a new column in the ENCRYPTED vault ...
  schema migration, currently v7 -> v8"), which this item delivers instead,
  at v13 not v8. Amend it to keep detection + matching only when this ships,
  or a later implementer re-adds an existing column at a stale version.

  FIBR-0084 stays 📋 when this ships, and stays 📋 when FIBR-0113 ships —
  FIBR-0192 is its blocker, not either half of this split.

  Spec next (docs/specs/FIBR-0193.md), then cold-eyes,
  then TDD.
  **Layman:** Give each account somewhere to keep an account number and a free-text note — the storage side only; the Accounts screen that shows and edits them is FIBR-0113.
  Kind: feature.
  Lanes: repo.
  Source: split-from-FIBR-0113-2026-07-28 (/cold-eyes loop 5).
  Resolved (2026-07-30): shipped by TDD. Schema **v13** — `_migrate_to_v13`
  issues two nullable `ADD COLUMN`s (`accounts.account_number`,
  `accounts.note`) inside one `owned_transaction`; `models.Account` gains both
  fields appended after `created_at` (defaulted, so the four-argument
  positional literals outside the repository keep working); both
  `AccountRepository` read paths SELECT all six columns in dataclass field
  order; `add`/`update` take the two parameters REQUIRED; `AccountService`
  routes both write paths through the new module-level `_normalise_optional`,
  so a blank field stores SQL `NULL` rather than `""`. `add_account`'s two are
  optional keyword args, `update_account`'s are required (D2/D3) — an
  unconditional `UPDATE ... SET` means a defaulted `None` would silently erase
  a stored value. `ui/accounts.py::_on_update` reads the account's current
  values off two new item-data roles (`UserRole + 4`/`+ 5`) and passes them
  back unchanged, so a name/type-only edit leaves both stored fields intact
  (D5, INV-7); FIBR-0113 replaces that passthrough with real form fields.
  Reproduce-first TDD: new `tests/features/accounts/test_migration_v13.py`
  (5 legs, INV-1/INV-2) run RED before the migration existed, plus INV-3..INV-7
  in `test_accounts.py`. Schema-churn sweep: 14 test files re-pinned, 6 test
  functions renamed, the `v12`-as-latest comment sweep across 5 files, and 6
  feature `spec.md` prose fixes. FIBR-0086's bullet amended above (its storage
  half landed here, at v13 not v8). FIBR-0113 stays 🚧 — it ships next.

- ✅ [FIBR-0194] **StatementsWidget.refresh leaves a stale selection that resolves to a different statement under an active sort.**
  Found while reviewing FIBR-0113's spec, which took StatementsWidget.refresh
  as its fill precedent. Verified against source and reproduced against real Qt
  (docs/reviews/FIBR-0113-selection-drift-repro.py).

  ui/statements.py::StatementsWidget.refresh fills with
  `setRowCount(len(self._rows))` + setItem inside fill_guard, with NO
  preceding clear. setRowCount(len) does not clear rows, so an existing
  selection SURVIVES the repopulate; fill_guard's exit then re-applies the
  active sort, and the selection rides its item through that re-sort. It
  lands on whichever row's INSERTION index equals the previously-selected
  VISUAL row — i.e. `_table_state.selected_index` can return a different
  object than the user selected.

  Measured with three rows under a descending sort: the first and last rows
  drift; the MIDDLE row is the sort's fixed point and does not, which is why
  a single-row test can pass in the broken state.

  HARMLESS TODAY, which is why this is 📋 and not urgent:
  StatementsWidget._on_selection_changed only sets two button enabled-states
  (_reassign_button, _delete_button) and touches no form, so the worst
  current outcome is a correctly-enabled button. But _on_reassign and
  _on_delete both resolve through _selected_row() — so a user who sorts,
  selects, and triggers a refresh (any add/import) before clicking could
  reassign or delete a DIFFERENT statement than the one highlighted. Worth
  confirming whether any refresh can interleave with a live selection that
  way before deciding the severity.

  Fix: add a leading `self._table.setRowCount(0)` inside the fill_guard, as
  FIBR-0113 §3 decision 6 does for the Accounts table, and add a regression
  test that drives EVERY row (not one) under a descending sort and asserts
  selected_index is None after refresh.

  Check the other tables built on the same _table_state seam for the same
  pattern before fixing — transactions, transfers, recurring, rules and the
  import-wizard preview all use fill_guard, and any of them that loads a
  form from the selection has the FIBR-0113 CR-1 hazard for real.
  **Layman:** On the Statements tab, redrawing the list while it is sorted can leave the highlighted row pointing at a different statement than the one shown. Harmless today because the two buttons it drives are only enabled/disabled — but the same pattern would corrupt data on any tab that loads a form from the selection.
  Kind: fix.
  Lanes: ui.
  Source: cold-eyes-2026-07-28 loop 5 on docs/specs/FIBR-0113.md (code-side observation, surfaced not fixed).
  Resolved (2026-08-19): ALREADY FIXED by FIBR-0204, which took the better of the two routes this bullet offered. The bullet proposed a leading setRowCount(0) in StatementsWidget.refresh and said to check the other four tables on the same seam first; FIBR-0204 did check them, found four of five refilled in place, and put the clear inside fill_guard itself rather than in five call sites -- src/finbreak/ui/_table_state.py, whose docstring now states this defect and its reasoning in the same terms ("a wrong row-to-action map in a money app is unacceptable"). Verified 2026-08-19: no ui/*.py carries a local setRowCount(0) any more except main_window's unrelated one, and accounts.py carries a comment saying its own was removed for this reason. Covered by tests/features/table_state/ row 16 (sort-then-refill) and by the every-row assertion in tests/features/accounts/test_accounts.py. Closed on verification, not on recall.

- 📋 [FIBR-0195] **Resolve the docs/plans/ gap once, project-wide, instead of re-arguing it in every spec.**
  spec-format §2 makes a plan mandatory "once the build order matters (a
  migration, a change that must land in a specific sequence, or anything a
  second person will execute)". Verified 2026-07-28: docs/plans/ does not
  exist anywhere in this tree, and none of the 49 files in docs/specs/ has
  one — including every spec that ships a schema migration.

  The cost is not the missing files, it is that each affected spec now spends
  a paragraph explaining why it has no plan, and a cold reviewer correctly
  re-raises it every time. Prior non-compliance is not a waiver, so the
  paragraph cannot just say "nobody else does it either".

  Decide one of:
  (a) adopt docs/plans/ for specs that carry a migration or an ordered build,
  starting with the next one, and backfill nothing; or
  (b) record the departure ONCE — in docs/standards/documentation.md or a
  project spec-format override — and have every spec point at that single
  statement instead of restating it.

  (b) is the cheaper answer if the build order genuinely lives fine inside
  the spec's design section, which is what the existing 49 specs suggest in
  practice. Either way the per-spec paragraph goes away.

  Surfaced by /cold-eyes rather than fixed inline: choosing between (a) and
  (b) is a project-convention decision, not a docs defect.
  **Layman:** Every spec that involves a database change is supposed to ship a short build-order file. None of them do, and each spec currently explains that omission again. Decide once: either start writing them, or record the exemption in one place.
  Kind: doc.
  Source: cold-eyes-2026-07-28 loop 1 on docs/specs/FIBR-0193.md.

- 📋 [FIBR-0196] **Reconcile the spec-filename rule: naming.md says `<ID>.md`, the shared spec-format says `<ID>-<topic>.md`.**
  Two standards claim authority over the same filename and give
  different answers:

  - docs/standards/naming.md: "**Spec doc** | `<ID>.md` (the stable
  roadmap ID)", repeated under *ID-named docs* ("using the **stable ID
  verbatim**"). Its §9 *Project overrides* says "(None yet.)"
  - ~/.claude/skills/_shared/spec-format.md §2 (the governing format
  standard, since this project has no docs/standards/spec-format.md):
  `docs/specs/<ID>-<topic>.md`.

  Measured 2026-07-28: 48 of the 49 files in docs/specs/ use the bare-ID
  form. The single exception was FIBR-0193, written topic-suffixed during
  the FIBR-0113 split; it has been renamed to docs/specs/FIBR-0193.md so
  the tree is uniform again, and every reference repointed.

  That fixes the instance, not the conflict. The next spec written from
  the shared format standard will depart again, and a cold reviewer will
  correctly flag it again.

  Decide one of:
  (a) keep the bare-ID form (matches all 49 specs and naming.md) and
  record it as a project override in naming.md §9, so the departure from
  the shared standard is stated once and deliberately; or
  (b) adopt `<ID>-<topic>.md`, update naming.md's table and its ID-named
  docs paragraph, and accept that the existing 49 are grandfathered.

  (a) is the cheaper answer — it is what the tree already does, and the
  topic suffix buys nothing that the spec's own title line does not.

  Surfaced by /cold-eyes rather than decided inline: which standard wins
  is a project-convention call, not a docs defect.
  **Layman:** Two rulebooks disagree about what to call a spec file. Pick one so the next spec doesn't get named wrong.
  Kind: doc.
  Source: cold-eyes-2026-07-28 loop 2 on docs/specs/FIBR-0193.md.
  DECIDED (2026-08-05, user): `<ID>-<topic>.md` wins — a filename a
  human can read and parse without opening it. So `naming.md` line 85
  (`<ID>.md`) and its line-207 counter-example are the side that changes,
  not the shared spec-format.
  Two pieces of work, deliberately separated: (a) amend `naming.md` —
  a `docs/standards/` edit, so it trips the rule-14 /cold-eyes gate on
  its own; (b) back-migrate the existing corpus. Measured 2026-08-05:
  54 specs match `FIBR-NNNN.md` (`ls docs/specs/*.md | grep -cE
  '/FIBR-[0-9]+\.md$'`) and 374 inbound citations name those filenames
  (`grep -rnoE 'FIBR-[0-9]{4}\.md' --include=*.md --include=*.py
  --include=*.sh . | wc -l`), so (b) is a scripted rename plus a
  citation sweep, not a hand edit.
  First file written under the new rule:
  `docs/specs/FIBR-0231-plain-english-month-summary.md`.

- 📋 [FIBR-0197] **Two feature spec.md files still pin LATEST_SCHEMA_VERSION == 5.**
  `tests/features/pdf_import/spec.md` INV-8 pins `LATEST_SCHEMA_VERSION == 5`
  and `tests/features/import_/spec.md` INV-8 says the version "is now 5".
  Both are prose-only staleness in test-contract files: the *tests* those
  specs describe are green, so nothing fails. Surfaced by a cold-eyes lane
  while reviewing FIBR-0193 and deliberately NOT folded into that item —
  these two files are outside its blast radius (they are not in the
  `== 12` pin set FIBR-0193 §6/§12 own), and widening a review run into
  unrelated documents is how a review silently becomes an edit run.
  Fix: advance both to whatever `LATEST_SCHEMA_VERSION` is when this is
  picked up, or reword them to cite the constant instead of a literal so
  they stop churning on every migration.
  **Layman:** Two old test-contract files still say the database format is at version 5, when it is really at 12 (and about to be 13) — harmless today, but confusing to read.
  Kind: doc-fix.
  Source: in-session-2026-07-30 (FIBR-0193 cold-eyes loop 4, deferred finding).

- ✅ [FIBR-0198] **Accounts tab: reveal the masked account number, with an auto re-mask after 30s.**
  Split out of FIBR-0113 on 2026-07-30. FIBR-0113 ships the sortable
  5-column Accounts table with the account number ALWAYS masked; this item
  adds the way to see it. Blocked by FIBR-0113 (it needs the table, the
  mask helper and the account-number form field that item creates).

  Scope: a "Show account numbers" QCheckBox between the table and the
  form; a single-shot QTimer (_REVEAL_SECONDS = 30, matching the existing
  clipboard_clear_seconds default) that re-masks unattended; reveal
  governs BOTH surfaces — the table cell text AND the form field's echo
  mode (Password -> Normal), because the form fills on every row selection;
  session-scoped, never persisted, and gone after a lock cycle. The
  toggle handler must re-select the previously-selected account with the
  table's signals blocked, or it clobbers a half-typed edit.

  Also amends docs/security-model.md T13, whose mitigation currently
  asserts account numbers are "not copyable" — true only while the form
  field stays in Password echo mode, i.e. only until this ships.

  The split reason: shipping the table alone renders the account number
  masked and nothing regresses; shipping the reveal alone is impossible.
  FIBR-0113 §8 records why "mask with no reveal" is not the end state —
  a user who needs the full number to pay someone would otherwise have to
  open the vault file to get it back.
  **Layman:** Add a "Show account numbers" tick-box to the Accounts tab so you can read a full account number when you need to pay someone — and have it hide itself again after half a minute so it can't be left on screen.
  Kind: feature.
  Lanes: ui.
  Source: in-session-2026-07-30 (FIBR-0113 split, UI half).
  Resolved (2026-07-30): shipped by TDD, closing the
  FIBR-0193 → FIBR-0113 → FIBR-0198 chain. A "Show account numbers" checkbox
  between the table and the form switches the account number from masked to raw
  on BOTH surfaces FIBR-0113 masks — the table cell (a conditional write in the
  fill) and the form field (echo mode `Normal`/`Password`, the
  `ExportDialog._on_show_toggled` idiom). Session-scoped and written to no store;
  a lock needs no extra code, since `MainWindow._lock()` destroys the workspace
  and the next unlock builds a fresh widget. A parented single-shot `QTimer`
  re-masks after `_REVEAL_SECONDS` (a COPIED literal 30, not an import of
  `DEFAULT_CLIPBOARD_CLEAR_SECONDS` — importing it would make this window track
  that user-settable default, the coupling D3 forbids); the interval restarts
  rather than extends on each fresh reveal, and no `_refresh()` from any other
  cause touches it. `_on_reveal_toggled` runs six ordered steps, re-selecting
  under `blockSignals` (with the unblock in a `finally`) so a re-mask cannot
  repopulate four form inputs from storage over a half-typed edit — the reveal is
  the one control a user reaches for mid-edit. `_refresh()` gained a
  `VaultLockedError` guard around all five pre-fill reads, because a queued
  timeout can land between the vault locking and the deferred `deleteLater()`.
  Reproduce-first TDD, 5 legs red first: INV-2 leads by EMITTING the timeout,
  because the configuration-observing legs all pass against an implementation
  that never connects it, and its no-restart leg leads with `isActive()` because
  `QTimer` returns -1 from `remainingTime()` when inactive. `security-model.md`
  T13 amended and **T14** added: the reveal makes an account number copyable from
  the form field, and that copy is NOT auto-cleared — `ClipboardAutoClear` is
  wired only to the transactions list, so a Ctrl+C during a 30-second reveal
  outlives it indefinitely. A deliberate gap (clearing it mid-payment would defeat
  the reason the reveal exists), now stated rather than implied. Screenshots +
  README refreshed. FIBR-0084 still stays 📋 until FIBR-0192.

- ✅ [FIBR-0199] **Cover Reset layout's settings clear — no leg discriminates it today.**
  Found by mutation-testing during the FIBR-0192 build (2026-08-02).
  `reset_columns(self)` and `settings.remove("columns")` in
  `MainWindow._reset_layout` are redundant while both run in the same
  call: each alone leaves a rebuilt view on the default columns, so
  dropping either one keeps INV-6 green and only dropping BOTH turns it
  red. The clear is defence-in-depth for a view `reset_columns` cannot
  reach (built without `remember_columns`, or destroyed before the
  reset), and that path has no live instance.
  The same redundancy is why no leg discriminates the clear-first vs
  clear-last ordering that FIBR-0192 §4.4 turns on — under either, the
  INI ends up holding the default state, immediately as well as after a
  deferred layout pass. Closing this needs a genuinely fresh process, or
  a fixture that builds a remembered view and destroys it before the
  reset. FIBR-0192 §11 records both as `nothing` rows.
  **Layman:** A safety net in the Reset-layout code has no test proving it works.
  Kind: test.
  Source: in-session-2026-08-02 FIBR-0192 build.
  Progress (2026-08-02): one fixture input verified while pre-checking
  FIBR-0200. A leg that needs a remembered view DESTROYED before the reset
  must use `deleteLater()` plus a real event-loop spin (or
  `shiboken6.delete`) — `QApplication.processEvents()` does NOT process
  DeferredDelete, so the widget is still alive and the leg silently proves
  nothing (measured: `shiboken6.isValid(holder)` is still True after
  `deleteLater()` + `processEvents()`; False after a `QTimer`-quit
  `app.exec()` spin). FIBR-0200 itself closed as not reproducible, so this
  bullet no longer shares a scenario with it.
  Resolved (2026-08-02): closed by the fixture this bullet called for — a
  remembered view DESTROYED before the reset, which is the one shape
  `reset_columns(self)` cannot reach. `tests/features/table_state/` row 13
  + `test_FIBR0199_reset_clear_discriminates_a_destroyed_remembered_view`
  widens and persists `transactions_table`'s column 0, destroys the table
  (`deleteLater()` + `_pump_deferred_delete()`, asserted with
  `shiboken6.isValid`), runs `_reset_layout()`, and requires a freshly
  built view to come up on the default width.
  Discrimination verified by mutating BOTH lines independently, not just
  the one: dropping `settings.remove("columns")` turns it RED
  (`assert 197 == 100` — the stale width survives), while dropping
  `reset_columns(self)` leaves it GREEN. That is the property INV-6 could
  not provide, which only went red when both were dropped.
  NOT closed: the clear-first vs clear-last ORDERING that FIBR-0192 §4.4
  turns on still has no discriminating leg — this fixture destroys the
  view, so both orderings end with the group erased. Still a `nothing` row.

- ✅ [FIBR-0200] **remember_columns' _save can outlive its header and raise at teardown.**
  Observed 2026-08-02 while probing FIBR-0192: a standalone script exits
  with `RuntimeError: libshiboken: Internal C++ object
  (PySide6.QtWidgets.QHeaderView) already deleted` raised from `_save` in
  `ui/_table_state.py`. The closure captures `header` and stays connected
  to the header's own signals, so a late emission during interpreter /
  widget teardown calls `header.saveState()` on a destroyed C++ object.
  Pre-existing (FIBR-0117), not introduced by FIBR-0192 — surfaced only
  because the probe ran outside pytest, where teardown ordering differs.
  Harmless today (stderr noise at exit, nothing is lost), but it is the
  same class as the shiboken lifetime issues the UI already guards. (This
  line originally cited "the QT-5 `TypeError` §4.3 documents"; FP01
  re-measured QT-5 on 2026-08-02 and no `TypeError` occurs — that citation
  is withdrawn, but this teardown `RuntimeError` is independently real and
  was reproduced again by the close-phase code lane.) Likely fix:
  guard `_save` with `shiboken6.isValid(header)`, matching the pattern
  `main_window.py::_ensure_workspace` already uses. Confirm it can fire
  in the packaged app before spending much on it.
  **Layman:** A harmless-looking error can print when the app shuts down.
  Kind: fix.
  Source: in-session-2026-08-02 FIBR-0192 build.
  Resolved (2026-08-02): NOT REPRODUCIBLE AS SHIPPED. The pre-check this
  bullet itself asked for came back negative on every path tried, so the
  `shiboken6.isValid` guard is not worth adding — it would be a defensive
  branch for a state the current stack forbids. Evidence, all against
  v0.1.19 / PySide6 6.11.1:
  (a) The packaged AppImage driven end to end against a seeded throwaway
  vault on an isolated X display: unlock, five tabs built, then File ▸
  Quit — exits 0 with EMPTY stderr. File ▸ Lock, which destroys all 13
  remembered views while the process keeps running, is equally silent.
  (b) The same flow from source: exit 0, silent.
  (c) Direct probe: after a GENUINE destruction (`shiboken6.isValid(header)`
  == False, verified), `_save` is never called again. Qt drops the
  connection with the header, and emitting on the dead header raises
  "Signal source has been deleted" at the EMIT site, so `_save` never runs
  to reach `header.saveState()`. NOTE a first attempt at this probe was
  invalid: `QApplication.processEvents()` does NOT process DeferredDelete,
  so the widget was still alive and the silence proved nothing.
  (d) 30 days of real maintainer runs — 30 distinct `app-finbreak@*.service`
  scopes, whose stderr does reach the journal (its fontconfig / xkbcommon
  lines prove the capture works) — contain zero "already deleted" /
  "Internal C++ object" lines.
  The one gap: the 2026-08-02 probe script that produced the original
  observation was never committed, so its exact shape could not be
  replayed verbatim. Re-open if it resurfaces on a newer PySide6.

- ✅ [FIBR-0201] **Bulk-confirm transfers — tick several suggested pairs and confirm them in one click.**
  The Transfers tab today offers exactly two speeds and nothing in
  between: `_on_confirm` (`ui/transfers.py:174`) confirms the ONE
  selected candidate, and `_on_confirm_all` (`:200`) confirms every
  candidate the detector produced. A user who trusts eight of twelve
  suggestions has to click through eight times or accept all twelve.

  Verified against source 2026-08-02, not recalled:

  1. `ui/transfers.py:119` sets the suggested table to
  `QAbstractItemView.SelectionMode.SingleSelection`, so multi-select is
  not merely unwired — the table refuses it. Widening it is the first
  change, and it is the one with blast radius: `_selected_row()` returns
  a single index and is used by `_on_confirm`, `_on_reject` and the
  enable/disable recompute, so each needs a decision about what "the
  selection" means once it can be plural.

  2. `remember_columns` + `enable_sorting` are both live on this table
  (`:120-121`), so a confirm that rebuilds via `_refresh()` re-sorts.
  The FIBR-0113 finding applies: a selection held across a re-sort can
  ride its item onto a DIFFERENT row. A bulk confirm must resolve every
  ticked row to its `(debit.id, credit.id)` BEFORE it starts confirming,
  not index into `self._candidates` as it goes.

  3. The status line uses `tr("Confirmed %n transfer(s).", "", n)`, which
  already pluralises — so the count is free once the loop exists.

  Open design question for the spec: whether the service grows a
  `confirm_many(pairs)` that owns one transaction, or the widget loops
  over `confirm()`. A partial failure mid-loop leaves some pairs
  confirmed and some not, with no record of where it stopped, so the
  transaction boundary is a correctness question, not a tidiness one.
  Kind: feature.
  **Layman:** Confirm a handful of suggested transfers at once instead of one at a time.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-08-02.
  Progress (2026-08-02): specced jointly with FIBR-0202 in
  `docs/specs/FIBR-0201.md` (umbrella spec, ACCEPTED after 4 cold-eyes
  loops with 2 cold lanes each, 18 invariants).
  **This bullet's open design question is answered: neither a widget loop
  nor a new batch transaction.** `TransferDetectionService` grows
  `confirm_many(pairs)`, and `confirm_all()` becomes `confirm_many(
  candidate_pairs())` — the consumed-set logic MOVES rather than being
  copied, because the hazard it guards (two selected suggestions sharing a
  transaction) is not specific to "all". It keeps `confirm_all`'s shipped
  per-decision-commit boundary (FIBR-0011 D6) rather than inventing a new
  one, since changing that is a behaviour change this item did not ask
  for. It calls `add_decision` directly, not `_record`, so a consumed pair
  is skipped instead of raising `ValueError` at the user; verified that
  this is safe — `add_decision` canonicalises the pair internally
  (`min`/`max`), so bypassing `_record` changes what is rejected, never
  what is written.
  The selection mode is `MultiSelection`, not `ExtendedSelection` (plain
  click toggles; no Ctrl/Shift knowledge needed for this app's audience),
  and only the SUGGESTED table widens — `_make_table` builds both transfer
  tables from one line, so it takes a parameter.
  Resolved (2026-08-03): shipped by TDD off docs/specs/FIBR-0201.md.
  The open design question (service `confirm_many` vs a widget loop) is
  answered by D4/§4.3 in favour of the service: `confirm_many(pairs)`
  confirms in the GIVEN order and the consumed-set logic MOVED there rather
  than being copied, so `confirm_all()` is literally its caller (INV-5) and
  the two cannot drift. `reject_many` sits alongside it (D3) — rejection
  consumes nothing, so two selected suggestions sharing a transaction are
  both recorded. Both record via `add_decision`, not `_record`, whose two
  guards RAISE where a skip is wanted; `add_decision` canonicalises the pair
  internally, so nothing about what is written changes. A skipped pair is
  named on the status line, and `tr("Rejected.")` stays byte-for-byte at
  n == 1 (INV-14).

- ✅ [FIBR-0202] **Bulk-delete statements — tick several, plus a Delete all button.**
  The Statements tab deletes exactly one statement per click
  (`ui/statements.py:205`, single-select at `:94`), and there is no way
  to clear the list. Clearing out a bad import run means N confirm
  dialogs.

  Verified against source 2026-08-02, not recalled:

  1. `ui/statements.py:94` is `SelectionMode.SingleSelection` — same
  first change as the transfers item, and the same re-sort hazard
  (`enable_sorting` at `:95`): resolve ticked rows to statement ids
  before deleting, never index as you go.

  2. **The confirm text cannot simply be repeated N times.** `_on_delete`
  calls `StatementService.delete_preview` (`services/statements.py:82`)
  per statement and branches on whether any transactions are shared with
  an overlapping statement — the FIBR-0149 wording fix. A bulk delete
  needs ONE aggregate message, so `delete_preview` needs a batch form or
  the caller has to sum the pairs itself.

  3. **The batch is order-sensitive, and this is the real hazard.**
  `delete_statement` (`services/statements.py:57`) runs FIBR-0148's
  hand-off: each stamped row a REMAINING same-account statement also
  covers is re-stamped to that statement rather than deleted. "Remaining"
  is evaluated per call, so deleting A then B is not the same as deleting
  {A,B} as a set — rows handed to B in step one are then deleted in step
  two, and a preview computed up-front over-states what survives. The
  spec has to decide whether a bulk delete is one transaction that
  evaluates coverage against the post-batch survivor set, or a
  documented sequence of independent deletes.

  4. A **Delete all** button is the same operation with the selection
  implied, and inherits point 3 exactly: with every statement going, no
  statement remains to hand rows off to, so every stamped row is deleted.
  Worth stating in the confirm text, since that is the case where the
  loss is total.
  Kind: feature.
  **Layman:** Remove several imported statements at once, or clear the lot, instead of deleting them one by one.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-08-02.
  Progress (2026-08-02): specced jointly with FIBR-0201 in
  `docs/specs/FIBR-0201.md` (umbrella, ACCEPTED after 4 cold-eyes loops).
  **This bullet's point 3 is CORRECTED by measurement.** It called the
  per-call FIBR-0148 hand-off "order-sensitive, and this is the real
  hazard". Measured against the real services: the SURVIVING DATA is not
  order-sensitive — deleting A-then-B and B-then-A end identically, and
  identically to batch semantics — because the hand-off re-evaluates on
  every call, so coverage by a statement that is itself being deleted
  never persists. What DOES break is the PREVIEW: summing per-statement
  `delete_preview` calls over a batch reports `removed=0, kept=3` where
  the batch-aware query reports `removed=2, kept=1`, so the confirm dialog
  would promise nothing is permanently removed and then destroy two
  transactions. That is the money-critical defect, and atomicity — not
  data correctness — is what one transaction buys (spec D5/§2.1).
  Also found while specing: the exclusion predicate `q.id <> :pid` lives
  at FOUR sites, not two — `hand_off_covered`'s `SET` correlated picker as
  well as its `EXISTS` guard, plus both of `delete_split_counts`' arms.
  Widening only the guard would let a row be handed to a statement inside
  the batch, which the same batch then deletes.
  Resolved (2026-08-03): shipped by TDD off the shared spec.
  Point 3's premise was already corrected by §2.1 and the build confirms it:
  loop ORDER does not change what survives — INV-13 measured batch against a
  per-call loop in BOTH orders over three seeds. The real hazard was the
  CONFIRM MESSAGE: summing per-statement previews reported removed=0 for a
  delete that destroys two transactions. One batch-aware preview now answers
  it. The exclusion predicate lives at FOUR sites, not two (the SET picker is
  not EXISTS-shaped and is the easy one to miss); all four interpolate one
  `_coverage_where_sql`, proven on the emitted SQL. The batch is one owned
  transaction — for atomicity, not data correctness.

- ✅ [FIBR-0203] **Back-fill the missing v0.1.17 GitHub release — its notes are invisible to the in-app updater.**
  `gh release list` jumps 0.1.18 → 0.1.16: there is no GitHub **release**
  for v0.1.17, though the tag exists locally AND on origin
  (`21bebf7`, 2026-07-23) and `CHANGELOG.md` carries the full section.

  Verified against source 2026-08-02, not recalled — this is not
  cosmetic. FIBR-0152 (✅, shipped) accumulates the notes shown in the
  update prompt from the **GitHub release objects**, not from tags or
  from CHANGELOG.md: `services/update.py:280` calls `fetch_releases`,
  which GETs `/releases?per_page=30`
  (`services/update_fetch.py:28`), and `:286` feeds that list to
  `_accumulated_notes(releases, current, offered)`. A release absent
  from the list contributes nothing.

  Consequence: a user still on **0.1.16** who is offered 0.1.18 sees
  0.1.18's body only. Everything 0.1.17 delivered — Flathub Flatpak
  packaging (FIBR-0159), native RPM/deb via OBS (FIBR-0155), 3-level
  categories (FIBR-0154), the "Forgot password? Start over" vault reset
  (FIBR-0030), signed SHA256SUMS + SBOM (FIBR-0096), Report an Issue
  (FIBR-0156) — is silently missing from the prompt. The offer itself is
  unaffected (`_notes_since` is best-effort and the decision is already
  made), so this degrades the notes only.

  Open decision for whoever picks this up: whether to publish notes-only
  (cheap, fixes the accumulation immediately) or to also build and sign
  the v0.1.17 artifacts to match every other release (the tag is 10 days
  old; v0.1.18 supersedes it for actual downloads, and every other
  release carries AppImage + exe + both `.sig`s + SHA256SUMS + SBOM).
  Notes-only leaves an asset-less release page, which is a visible
  inconsistency but harms nobody, since `/releases/latest` — the offer
  endpoint — is unaffected either way.
  Kind: fix.
  **Layman:** A whole version's release notes are missing from the update prompt inside the app.
  Kind: fix.
  Lanes: release.
  Source: in-session-2026-08-02 housekeeping.
  Resolved (2026-08-02): published the v0.1.17 GitHub release
  **notes-only**, per the open decision in this bullet — the notes body is
  CHANGELOG.md's `[0.1.17]` section verbatim, prefaced by a short italic
  line stating the notes were published retrospectively and that no
  artifacts are attached because v0.1.18+ supersede it.
  Created with `--latest=false`, which was the one real hazard: GitHub's
  default "latest" selection is date-based, so a release object created
  today for an older tag would have become `/releases/latest` — the exact
  endpoint `check_for_update` reads to decide what to OFFER. Verified after
  publishing: `/releases/latest` still returns **v0.1.18**, and v0.1.17
  carries 0 assets, `draft: false`, `prerelease: false`.
  Fix verified end-to-end against the LIVE API rather than by inspection:
  called the real `fetch_releases` + `_accumulated_notes` for a user on
  0.1.16 offered 0.1.18 — 19 releases fetched, the prompt now contains
  both `## 0.1.18` and `## 0.1.17` headings (11,032 chars) and the 0.1.17
  body's own content (FIBR-0154, Flathub). Before the back-fill that call
  returned 0.1.18's body alone. The non-empty-`body` and
  not-draft/not-prerelease conditions `_accumulated_notes` gates on are
  all satisfied.
  No CHANGELOG entry and no code change: the defect was a missing release
  object on GitHub, not app behaviour — nothing in the shipped software
  differs. Notes-only leaves an asset-less release page, the accepted
  cost recorded in this bullet's own decision.

- ✅ [FIBR-0204] **FP01 — fix-pass after FIBR-0192: two wrong Qt measurements, and the docs that still say it never shipped.**
  Raised by `/close-phase` on FIBR-0192 — one static-analysis sweep
  (semgrep/ruff/bandit, **0 findings**) plus two cold review lanes. Every
  finding below was re-verified in this session against PySide6 6.11.1 or
  against the file itself; nothing is taken on the reviewer's word.

  **The two measurement defects (latent, no user-visible bug today):**

  1. **QT-10's negative half is backwards.**
  `docs/specs/FIBR-0192-qt-facts.md:38` and `:176-179` conclude that
  `stretchLastSection` and the section resize mode are NOT carried in
  `QHeaderView.saveState()`. Re-measured: **stretch, resize mode,
  `sectionsClickable`, `defaultSectionSize` and per-section hidden flags
  all restore to their captured values.** Probe C's own recorded output
  refutes the conclusion drawn from it. Consequence: `_table_state.py`
  `remember_columns`' docstring (`:141-146`) enumerates only the movable
  flag and the sort indicator as ordering constraints, so a contributor
  who adds `setStretchLastSection(True)` or `hideColumn(n)` AFTER
  `remember_columns` gets it silently reverted by the first Reset layout
  — QT-3's exact failure shape on a flag the contract calls safe. No
  current call site violates it (`transactions.py:181-184` precedes
  `:189`), which is why nothing is broken today.
  Also of record: `docs/specs/FIBR-0192.md:776` shows cold-eyes loop 3
  citing this measurement to DISMISS a lane that had reported it
  correctly.

  2. **QT-5 is a probe artifact.** `_table_state.py:183-188` and
  `main_window.py:1558-1559` state that `_save` never runs on a restore
  because `Qt::SortOrder` fails to marshal and raises `TypeError`, and
  therefore that `reset_columns` "never writes to the INI". Re-measured:
  `restoreState` emits `sortIndicatorChanged` **whenever the restored
  indicator differs from the current one**, and the argument marshals
  cleanly — a proper `SortOrder` enum, no `TypeError`, nothing on
  stderr. So `reset_columns` DOES `setValue` + `sync()` per affected
  view. Harmless today only because `_reset_layout`'s trailing
  `settings.remove("columns")` erases the writes; the docstring's
  rationale rests on a false premise, and any future caller of
  `reset_columns` without a trailing clear persists the default.
  Measured additionally: on a **QTreeWidget**, `restoreState` also emits
  `sectionResized` once, which the same docstring (`:177`) denies.

  **The documentation-truth half** — the item shipped in 70f0e15, and
  these still describe it as pending:

  - `docs/specs/FIBR-0192.md:3-4` — **Status still "ready to
  implement"**; its three siblings (FIBR-0113/0193/0198 `:3`) read
  `✅ SHIPPED`. And `:11-12` still instructs "do NOT flip FIBR-0084 until
  this ships", which the same commit did.
  - `docs/specs/FIBR-0052.md:71` (INV-6) and `:325-326` (INV-6b) — never
  widened to name the `columns/*` group, though FIBR-0192 §12 called this
  out by name as the one existing contract this item widens.
  - `docs/specs/FIBR-0113.md:653-654` — **actively wrong advice**: "no
  escape hatch today ... must delete the `columns/accounts_table` key by
  hand." The escape hatch now exists.
  - `docs/specs/FIBR-0113.md:594-597` (§5 INV-13/INV-14) and `:773-780`
  (§9) — the two places FIBR-0192 §12 said would be "annotated as
  discharged here"; neither was.
  - `docs/specs/FIBR-0113.md:18, :39, :67, :110, :863`;
  `docs/specs/FIBR-0193.md:891-892, :978`;
  `tests/features/accounts/spec.md:227-229` — present-tense pending.
  - `FIBR-0192.md:597` and `:657` — the remembered-view count is **13**,
  not 11 (`recurring.py` and `transfers.py` each build two tables); §10's
  resource figures inherit it.

  **Test-suite verdict: clean.** 15 mutations against the shipped source;
  no vacuous leg, and all four of §11's "nothing checks this" admissions
  are literally accurate. Two LOWs to fold: INV-6's precondition (b) is
  asserted more weakly than §5 states
  (`tests/features/table_state/test_table_state.py:544` accepts a key
  holding the DEFAULT state), and §11 credits INV-6 with catching nothing
  when it does catch the both-mechanisms-dropped case.

  FIBR-0200 was independently confirmed real by the code lane (the `_save`
  teardown `RuntimeError`), and this change takes the connected-closure
  count from 8 to 12 — evidence for that bullet, not new work here.
  Kind: review-fix.
  **Layman:** Corrections found while closing the column-layout work: two measured facts were recorded backwards, and a pile of documents still say the feature is unbuilt.
  Kind: review-fix.
  Lanes: ui, docs.
  Source: in-session-2026-08-02 /close-phase FIBR-0192.
  Resolved (2026-08-02): applied via `/apply-fixes`, commit `5cd057f`.
  Every finding re-measured before fixing rather than taken on the
  reviewer's word — which paid twice. **QT-11 added** and QT-10's negative
  clause withdrawn: `saveState()` does serialise `stretchLastSection`, the
  resize mode, `sectionsClickable`, `defaultSectionSize` and hidden flags.
  **QT-5 rewritten**: `restoreState` emits `sortIndicatorChanged` once per
  view, the `SortOrder` marshals cleanly, and `reset_columns` therefore
  writes + `sync()`s per view — proved against the real functions by
  watching the INI's bytes change across the call. The review's own
  explanation for the original QT-5 reading (Probe A missing a
  `QtCore.Qt` import) was **tested and disproved**; the handler runs
  either way, and that is recorded in the doc so the next reader does not
  re-derive it. Both source comments corrected, plus §4.2/§4.3/§4.4/§8/§10.
  Doc-truth half closed: FIBR-0192's own Status line, its FIBR-0084
  blocker instruction, FIBR-0052 INV-6/INV-6b (widened to the `columns/*`
  group at last), FIBR-0113's wrong "delete the key by hand" advice and
  its two §5/§9 discharge annotations, FIBR-0193 and the accounts test
  spec. Cold-eyes loop-log rows left **frozen** — they record what each
  loop believed at the time, and rewriting them would destroy the audit
  trail that made the QT-10 dismissal findable. View count corrected
  11 → 13. **A test fix that needed fixing twice:** INV-6's precondition
  (b) asserted only that the settings key existed; the first replacement
  compared stored bytes against the build-time default, and mutation
  testing showed that ALSO passes with the widening removed, because the
  preceding `window.resize` already provokes a save. It now snapshots
  either side of the widening and goes red when the widening is dropped.
  Gate green **1455 passed, 2 skipped**; `/doc-lint` clean on all six
  edited docs.

- 📋 [FIBR-0205] **tests/features/bundling cannot be run on its own — it SIGABRTs with a coredump.**
  Found while running a subset of the suite during the v0.1.19 bump.
  `pytest tests/features/bundling` aborts the interpreter — SIGABRT,
  `Fatal Python error: Aborted`, a 12 MB coredump per run. The whole suite
  is green (1455 passed), so this is invisible to the gate and to CI.

  Verified against source 2026-08-02, and reproduced with the release bump
  stashed so it is not caused by the version edits:

  1. `test_INV1_selftest_fail_names_the_broken_stack`
  (`tests/features/bundling/test_bundling.py:86`) monkeypatches
  `_selftest._check_qt` to `lambda: None` and `_check_sqlcipher` to raise,
  then calls `run_self_test`.

  2. `run_self_test` (`src/finbreak/_selftest.py:266`) runs its checks in
  the order `qt → qtcharts → icons → sqlcipher → …`. So `_check_icons`
  runs for real, BEFORE the stubbed-out sqlcipher failure it is testing
  for — and `_check_icons` (`:63`) renders a pixmap
  (`icon("lock").pixmap(QSize(16, 16))`).

  3. `_check_qt` is what constructs the QApplication — its own docstring at
  `:72` says `_check_icons` "Runs after `_check_qt` (needs the
  QApplication)". Stubbing `_check_qt` removes it, so `QIcon::pixmap`
  reaches Qt's `qFatal` in `libqsvgicon.so` and calls `abort()`.
  `run_self_test`'s `except Exception` cannot catch it — `qFatal` is not a
  Python exception.

  4. It passes in the full suite only because an EARLIER test file leaks a
  process-wide QApplication. Proven both ways:
  `pytest tests/features/bundling` → SIGABRT;
  `pytest tests/features/theme tests/features/bundling` → 42 passed.
  So the test's docstring claim that it unit-tests the FAIL contract
  "independent of installed native deps" is false — it depends on a
  QApplication it does not create.

  Consequence beyond the noise: `docs/specs/FIBR-0001.md` INV-6 and
  CLAUDE.md both document running a single test / a single file as a
  supported workflow, and for this file it is not — it dumps core.

  Likely fix: stub `_check_qtcharts` and `_check_icons` alongside the other
  two (the test only asserts the ordered-token contract, so the real
  renderers are incidental), or take pytest-qt's `qapp` fixture so the
  QApplication is created explicitly rather than inherited. Prefer the
  stub — it makes the test's stated independence true.
  **Layman:** One test file crashes hard unless other tests run first, so you can't run it by itself.
  Kind: test.
  Lanes: tests.
  Source: in-session-2026-08-02 v0.1.19 release.

- ✅ [FIBR-0207] **The theme INV-1 test failed whenever a real finbreak was open on the same machine.**
  Caught by the pre-push gate while pushing the v0.1.19 release record:
  `test_INV1_theme_applied_before_window` failed `DID NOT RAISE
  _Sentinel`, breaking a push whose only content was `.claude/workflow.md`
  and `ROADMAP.md`. The same test had passed twice earlier in the session
  (1455 passed, twice), so the trigger was environmental, not a code change.

  Cause, verified against source and reproduced live rather than inferred:

  1. The test patches `app_mod.MainWindow` with a recorder that raises, then
  asserts `run()` raises it — i.e. that the theme is applied BEFORE the
  window is built (FIBR-0127 INV-1).

  2. `app.run()` (`src/finbreak/app.py:64-66`) probes the FIBR-0189
  single-instance guard and `return 0`s *before* constructing `MainWindow`.
  So with another instance live, the recorder is never reached and the
  `pytest.raises` fails.

  3. `single_instance.socket_name()` carries the **uid**, so it is the same
  OS user's running app that collides — and a real finbreak was open on the
  desktop (5 processes; `/home/ants/Applications/finbreak-x86_64.AppImage`,
  already on 0.1.19 — i.e. exactly what a maintainer does right after
  cutting a release: run it).

  4. The suite's `theme_isolation` fixture snapshots only palette / style /
  stylesheet, so it never covered this.

  The product was behaving CORRECTLY throughout — this was only ever a
  test-isolation gap, invisible in CI (no desktop instance) and invisible
  locally until someone had the app open during a gate run.

  Fixed by stubbing the probe alongside the `MainWindow` / `AuthService`
  patches the test already applies — the same class of external dependency
  it had already decided to isolate. No coverage lost: the guard has its own
  8-test suite at `tests/features/single_instance/`. `listen()` needs no
  stub, since the recorder raises before `run()` reaches it.
  Verified the fix under the failing condition rather than after closing the
  app: with 5 finbreak processes still live, `tests/features/theme/` goes
  **32 passed** (was 1 failed / 31 passed).

  Only ONE test drives `finbreak.app.run()`, so this is a local stub rather
  than an autouse fixture; a second such test should factor it out.
  **Layman:** A test broke just because the app happened to be running — fixed, so it no longer depends on that.
  Kind: test.
  Lanes: tests.
  Source: in-session-2026-08-02 v0.1.19 release.

- ✅ [FIBR-0231] **Plain-English monthly summary — the app says what happened, in a sentence.**
  Tiles, a donut, a trend line, a drill-down, a forecast and alerts all
  ask the reader to work out what the numbers MEAN. Many people can't,
  don't, or get it wrong — and then conclude they are bad with money.
  This is the one feature that does the reading for them:

  "September cost you R2,340 more than your usual month. Almost all
  of it was one thing — a R1,900 vet bill. Take that out and you
  were R440 better than normal."

  Every input already exists: category totals (`ReportingService`),
  recurring medians (`RecurringService`), and the spike detection that
  already powers the alerts (`AlertService`). This is a presentation
  layer over existing services, not a new subsystem.

  Deliberately NOT FIBR-0175 (compare periods side by side) — that
  puts two columns next to each other and still leaves the reading to
  the user. The value here is the interpretation, not the comparison.

  The hard part is honest phrasing: the sentence must not overclaim on
  thin data, and must degrade to something shorter and vaguer rather
  than inventing a narrative when the month is unremarkable.
  **Layman:** The app tells you in plain words what happened to your money this month, instead of leaving you to read a chart.
  Kind: feature.
  Source: user-request-2026-08-05 (layman-comprehension suggestions).
  Spec DRAFTED but NOT ready to implement (2026-08-06).
  `docs/specs/FIBR-0231-plain-english-month-summary.md` (1213 lines) —
  first file under the FIBR-0196 `<ID>-<topic>.md` rule.
  /cold-eyes ran 3 loops x 3 cold lanes (9 reviews): loop 1 fixed 29
  findings, loop 2 fixed 31, loop 3 found 24 more and STOPPED
  UNCONVERGED on the skill's collateral trigger (collateral dominating
  draft defects two loops running). Nothing was fixed in loop 3.
  The 24 remaining findings are written up transferably at
  `docs/reviews/FIBR-0231-loop3-tail.md` — fold them in directly; do NOT
  re-run the review to rediscover them.
  Two blockers: (1) the common-day-count rule is neutral only for
  uniform spend, so a month-end debit order manufactures a false verdict
  AND a false named cause every February; (2) the derived baseline floor
  makes the absolute materiality gate dead, leaving INV-6's "relative
  only" leg with no solution and its §11 row naming a defence that
  cannot exist.
  Design that DID hold across all three loops: the cause is a merchant
  family's excess over its own baseline (not the largest row) — loop 1's
  correction, re-verified by loop 2 and loop 3 and never re-raised.
  Next: fold the tail in, trim ~80-100 lines of review archaeology into
  the loop log (all three lanes named the same trim), then ONE confirming
  loop — not a fresh review.
  Progress (2026-08-06): the loop-3 tail is FOLDED IN — all 24 findings,
  0 deferred, 0 dismissed, via /apply-fixes. Both blockers are closed by
  DESIGN changes, not prose. (1) The common-day-count rule is GONE: a
  complete month is now compared whole calendar month against whole
  calendar months, and only a partial month truncates — to a head capped
  below every window month's last day, so a fixed monthly debit is inside
  all four windows or none. The February bias that rule was introduced to
  remove is back, argued on the merits: 8.70% against a 10% gate, so it
  never renders a verdict alone, and it is TRUE rather than invented.
  (2) The absolute materiality gate is now stated as belt-and-braces —
  above the baseline floor, relative-pass implies absolute-pass, so INV-6
  dropped to three legs and the floor is asserted directly over the
  constants. Also: month_has_rows dropped (has-data is now a SPEND row,
  so an income-only baseline month reads as the partial import it almost
  always is); strip clear() added and called as refresh()'s first
  statement, closing all eight call sites; slot 2 split three ways
  because "All of it and more" was false at excess == movement; INV-14's
  sign check rewritten (the specified search could not fire — the
  currency symbol sits between the sign and the first digit); INV-1
  gained the AST leg that sees its own stated breach. The ~90 lines of
  review archaeology moved to the spec's new §13.1; §11 is 32 rows /
  11 nothings, re-derived by its stated awk. Spec is 1437 lines,
  spec_lint + doc_integrity clean, 14/14 invariants parse.
  Next: ONE confirming /cold-eyes loop — not a fresh review — then TDD.
  Progress (2026-08-06, later): confirming /cold-eyes loop 4 RAN — 3 cold
  lanes, zero CRITICAL, no design-level defect, and neither loop-3 blocker
  re-raised. One lane independently re-derived the new §4.4 window
  arithmetic, the §4.5 relative-implies-absolute proof and the slot
  partition and found them correct — that is the confirmation the loop
  was for. It still returned 26 verified findings (6 HIGH, 6 MEDIUM, 14
  LOW), all fixed: every HIGH was a test leg that could not fail or a
  rationale arguing from the wrong case. Biggest: slot 3's materiality
  floor had no owner (the service could not encode it, the strip could
  not reach the constant) — the detector now nulls residual_minor when no
  correction is warranted; INV-10's second leg used February, the one
  month that cannot distinguish the new rule from the rejected one;
  INV-12's grep was green exactly when its invariant was broken. Two
  prescribed predicates were executed before landing (the new _tr regex,
  the float-literal AST walk). Spec is 1508 lines, spec_lint +
  doc_integrity + doc_citations clean, 14/14 invariants parse, §11
  re-derived to 33 rows / 11 nothings.
  SPEC IS CLEARED FOR CODE. Next: step 3, TDD via /write-code —
  tests/features/month_summary/ (4 files per §7).
  Progress (2026-08-06): TDD complete — implementation green. New
  tests/features/month_summary/ (spec.md + 4 files, 81 tests, the § 7
  capability split honoured); src/finbreak/services/month_summary.py (the
  pure summarise_month detector + MonthSummaryService),
  src/finbreak/ui/month_summary.py (MonthSummaryStrip, all 18 templates),
  models.py gains MonthVerdict / MonthCause / MonthSummary. Wired into
  HomeView (month_summary is the sixth positional parameter, before
  amount_prefs) + main_window; refresh() now clears the strip as its first
  statement and reads date.today() once for the strip and the tiles alike.
  Six existing HomeView call-sites in tests updated. Whole suite 1785
  passed / 2 skipped; ruff + mypy clean. Docs: text.py's merchant_name
  docstring now names this as its third consumer and second filter case;
  design.md's service list gains MonthSummaryService. Next: /close-phase
  (steps 5-9).
  Resolved (2026-08-06): SHIPPED. Steps 5-9 closed by /close-phase.
  /audit + /code-quality-review (3 independent cold lanes) returned 0
  CRITICAL and 0 HIGH in the CODE; the arithmetic lane found nothing at
  any severity, verified by EXECUTION (the L_min-1 head cap, leap-February
  and year-boundary windows, the family-mean divisor, the ladder's order,
  every threshold operator, and a 144-month brute force confirming §6.1's
  February bias never reaches the gate). The adversarial test lane, which
  applied 45 mutations rather than reading, found 2 HIGH + 6 MEDIUM — all
  of them TESTS that could not fail, not defects in behaviour. Notably a
  mutation emitting the WRONG MONTH passed all 81 tests, and the
  round-half-up mean leg was vacuous twice over (expected value a verbatim
  copy of the line under test; fixture sum 1 mod 3, where truncation gives
  the same answer). All 17 actionable findings fixed inline and
  mutation-proved; no FP## spawned, nothing deferred. Three code fixes in
  ui/home.py, chief of them _on_period_changed clearing the strip BEFORE
  its prefs write — the one path refresh()'s own clear cannot reach.
  Spec corrected in two places rather than left to drift: §4.9's
  "whatever raises, and wherever" claim, and §4.8's false gloss that the
  strip first speaks on the 7th (condition 2's whole-month floor over a
  truncated baseline binds first; a R100/day vault speaks on day 10).
  §11 re-derived mechanically 33 -> 36 rows, 11 nothings unchanged.
  allowlist-005 added (cppcheck fed .py files). Gate green 1791/2, mypy
  clean, spec_lint + doc_integrity 0, 18/18 citations resolve. Journal
  docs/journal/FIBR-0231.md; tag FIBR-0231-complete.

- 📋 [FIBR-0232] **"Safe to spend" — one number for what's left after everything still due this month.**
  The cash-flow forecast (FIBR-0171) already projects a balance forward
  through every known recurring payment to a horizon. This derives ONE
  figure from it and puts it where a nervous user will actually look:

  "After everything still due this month, you have R1,240 left."

  That is the question a layman actually asks. Today the app answers it
  with a line graph they have to interpret first.

  Must degrade honestly, and this is the whole risk of the item: the
  number is only meaningful in `ForecastMode.ANCHORED`. In `NET_FLOW`
  (no account has a persisted closing balance) there IS no safe-to-spend
  figure, and the card must say so — showing a projected CHANGE as
  though it were money in hand is exactly the harm to avoid.

  Pairs with the forecast-uncertainty item: a number the app cannot
  stand behind should not be printed at all.
  **Layman:** One number telling you what you can still spend this month, after the bills that haven't gone off yet.
  Kind: feature.
  Source: user-request-2026-08-05 (layman-comprehension suggestions).

- 📋 [FIBR-0233] **Committed vs free income — show what share of income is spoken for before the month starts.**
  Not a budget — no targets, no envelopes, no discipline required. That
  is FIBR-0022, and this is deliberately the opposite: a mirror, not a
  tool. One line and one bar:

  "71% of your income is spoken for before the month starts — rent,
  debit orders, subscriptions. R4,100 is yours to decide about."

  The recurring detector (FIBR-0142) already identifies the committed
  OUT streams and carries `monthly_equivalent` for each; income is
  already separated from spending on the dashboard.

  People systematically misjudge this ratio. Seeing it reframes "I am
  hopeless with money" into "I have less room than I thought" — which
  is true, actionable, and considerably kinder.

  Open question for the spec: what counts as committed. Confirmed
  recurring OUT items are the obvious core; whether suggested-but-
  undecided streams are included changes the headline percentage, so
  the rule must be stated on the card, not just in code.
  **Layman:** Shows how much of your pay is already promised to bills before you spend anything.
  Kind: feature.
  Source: user-request-2026-08-05 (layman-comprehension suggestions).

- 📋 [FIBR-0234] **Show the yearly equivalent beside every recurring amount.**
  A presentation change rather than a feature: anywhere a recurring
  amount is shown, show its yearly equivalent beside it.

  "R85/week → R4,420/year"

  `RecurringItem.monthly_equivalent` already exists (FIBR-0142 D8), so
  the cadence normalisation is done and this is a formatting change on
  top of it.

  Small repeated amounts are the single thing laymen underestimate most
  badly, and this is the cheapest correction to that error the app can
  make — which is what earns it a place despite being cosmetic.

  Two cares: rounding (a yearly figure derived from a weekly median
  should not imply false precision), and phrasing that does not read as
  a promise — it is an equivalent at today's rate, not a prediction.
  **Layman:** Shows what a small regular payment adds up to over a year, which is usually far more than people expect.
  Kind: enhancement.
  Source: user-request-2026-08-05 (layman-comprehension suggestions).

- 📋 [FIBR-0235] **Show the forecast's uncertainty — a band and a data-basis label, not a confident line.**
  The app forecasts and detects patterns. A layman who trusts a
  confident-looking WRONG forecast is a real harm — this is money, and
  a crisp single line reads as certainty the data does not support.

  Two changes:

  - Draw the projection as a band rather than one line.
  - Label the basis on its face ("based on 3 months of data").

  `ForecastMode` already distinguishes ANCHORED from NET_FLOW, so the
  weaker case is known to the code — it is just not visible enough at a
  glance to change how the number is read.

  Pairs with the "safe to spend" item, which must not print a figure it
  cannot stand behind. Consider these together: the same honesty rule
  drives both, and shipping the number without the caveat is worse than
  shipping neither.
  **Layman:** Makes it obvious how sure (or unsure) the app is about a prediction, so nobody leans on a guess.
  Kind: ux.
  Source: user-request-2026-08-05 (layman-comprehension suggestions).

- 📋 [FIBR-0238] **Add a deterministic "What checks this" tally check so the row count stops being hand-counted.**
  Every spec carrying a §11-style "What checks this" table closes it with a
  prose tally ("Eighteen rows, five with a bolded `nothing`"). That tally
  was miscounted by hand THREE times in a single FIBR-0231 session — 19
  for 18, 20 for 22, and 26/10 for 28/11 — twice in the same direction,
  and each time it was a cold reviewer who caught it, at review prices.

  The rule this trips is documentation.md § 8.2 / spec-format.md § 5.7:
  the same class caught twice becomes a mechanical check. It is trivially
  deterministic — count table rows under the heading, count rows matching
  `**nothing**`, compare against the two numbers in the following
  paragraph.

  FIBR-0231 works around it locally by stating the awk command beside the
  figure, which is the right shape but the wrong home: every spec with
  such a table needs it, not one. The check belongs in `/doc-lint`
  (a new finding kind, e.g. `tally_mismatch`), which already owns the
  deterministic half and is already run at /write-spec write time, before
  a /cold-eyes dispatch, and in /debt-sweep.

  Note `/doc-lint` is a machine-local global skill
  (`~/.claude/skills/doc-lint/`), not part of this repo — so this item is
  a pointer to work that lands there, and the verify step is that a spec
  with a deliberately wrong tally comes back with the new finding.
  **Layman:** Specs end with a little "here is what tests each rule" table and a sentence counting its rows. I keep miscounting that sentence by hand; this makes the computer count it instead.
  Kind: doc.
  Source: in-session-2026-08-06 (FIBR-0231 cold-eyes run, 3 miscounts of one table).

- 📋 [FIBR-0240] **Credit-card statement account auto-detect — needs a stable card identifier.**
  Deferred from FIBR-0086 (§9). Standard Bank credit-card statements (importer Family C) are EXCLUDED from import auto-detect because neither number on the page is usable as a matching key. The text after the statement's `account number` label is the DEBIT-ORDER account (the current account that pays the card) — measured 2026-08-06 across 13 real statements, where it normalises to exactly the user's current-account number, so matching on it would file every card statement under the current account. The card's own identifier is a masked PAN (printed as `Account NNNN **** **** NNNN`) which is NOT stable: the same corpus shows it changing mid-sequence on a card reissue — four statements carry one PAN, the following nine carry another. Revisit if SB starts printing a non-PAN account number on the statement, or if the user accepts re-entering the last four digits after each reissue. Until then credit-card imports keep the manual account pick.
  **Layman:** Credit-card statements still need you to pick the account by hand — the number printed on them belongs to the account that pays the card, not to the card itself.
  Kind: feature.
  Source: spec-FIBR-0086-2026-08-06 (measured against 13 real SBSA credit-card statements).

- 📋 [FIBR-0241] **Masked / trailing-digit account matching on import.**
  Deferred from FIBR-0086 (§3 decision 3, §9). The FIBR-0086 bullet originally asked to match on TRAILING digits when a statement masks its account number (e.g. "xxxx1234"). Measured 2026-08-06 across 48 real Standard Bank statements: NO statement presents a masked number as its OWN identifier. The only masked self-identifier is the credit-card PAN, which FIBR-0232 excludes for separate reasons; every other masked string in the corpus (printed as `*****NNNNNNN`) is a COUNTERPARTY inside a transaction row, which must never be matched on. So the loosened matching path had nothing to exercise it and was left unbuilt rather than shipped untested. Revisit trigger: the first real statement or OFX file whose own identifier is masked.
  **Layman:** If a bank ever prints only the last few digits of its own account number, finbreak will need a looser matching rule — no statement we have does that today.
  Kind: feature.
  Source: spec-FIBR-0086-2026-08-06 (48-statement corpus measurement).

- 📋 [FIBR-0242] **Account auto-detect for statement Family E.**
  Deferred from FIBR-0086 (§4.2, §9). FIBR-0086 enables header account-number extraction for importer families A, B and D. Family E (the Current-account "Payments / Deposits" layout added by FIBR-0190) is omitted because no Family E statement exists in the user's 48-file corpus — it would be expected to print a Family-A-style `Account Number` label, but including it would ship an untested claim about a layout nobody has seen. Add `Family.E` to `_ACCOUNT_NUMBER_FAMILIES` in `importers/standard_bank.py` and add a synthetic extraction test once a real Family E statement is available to measure against.
  **Layman:** One statement layout is left out of automatic account-filing because we have no real example of it to check against.
  Kind: feature.
  Source: spec-FIBR-0086-2026-08-06.

- 📋 [FIBR-0243] **OFX account-type prefill — map &lt;ACCTTYPE&gt; onto finbreak's account types.**
  Deferred from FIBR-0086 (§4.1, §9). `models.OfxAccountInfo` already carries
  `account_type` straight from ofxparse, and the FIBR-0086 roadmap bullet asks
  for "type/currency where available" — but FIBR-0086 deliberately leaves the
  create-account type prefill empty for OFX imports. Reason: the OFX
  `&lt;ACCTTYPE&gt;` vocabulary (CHECKING, SAVINGS, MONEYMRKT, CREDITLINE, ...)
  does not map onto this app's account types without a translation table nobody
  has validated against real files, and a WRONG prefilled type is worse than an
  empty one the user fills in — it looks authoritative. Build the mapping when
  there are real OFX files to validate it against; the corpus that grounded
  FIBR-0086 is 48 PDFs and contains none.
  **Layman:** When importing an OFX file, finbreak could guess whether an account is a cheque or savings account — it doesn't yet, because guessing wrong is worse than leaving it blank.
  Kind: feature.
  Source: spec-FIBR-0086-2026-08-06 cold-eyes loop 2.

- 📋 [FIBR-0283] **Accounts have no bank field, so a multi-bank vault distinguishes them only by account number.**
  The Accounts screen carries Name, Type, Account number, Note and
  Status, and nothing else. A vault holding accounts at two banks
  therefore records the owning bank nowhere at all: the only signal is
  the account number itself, which is masked in the table by default
  and is not something a person recognises on sight. Reported by the
  user 2026-08-19 against a real vault of six accounts at one bank
  plus one at another.

  Scope:
  - A `bank` field on the account record: schema migration, repository
    and domain model.
  - An input on the Accounts screen's add / update row, and a Bank
    column in the accounts table.
  - Carried through everywhere an account is named to the user - the
    account picker, the import wizard's pick step, and account
    headings in reports and PDF export.

  Two design calls to settle when this is picked up, deliberately NOT
  decided here:
  - Free text with a suggestion list, versus a closed enum. A closed
    list refuses a bank whose statements we cannot yet parse, and the
    importer families are Standard Bank only today (FIBR-0050), with
    other banks tracked as FIBR-0074 - so free text with suggestions
    is the likely answer.
  - Whether the field is optional. Existing accounts must migrate to
    an empty bank rather than a guessed one; inferring it from an
    account number is exactly the fragile guess this item removes.

  Adjacent and out of scope: FIBR-0086's import auto-detect and
  FIBR-0241's masked / trailing-digit matching both compare account
  numbers alone. Now filed as FIBR-0284: a bank on the account gives
  FIBR-0086's create-prompt somewhere to store the bank name it
  already extracts, and is the precondition that makes FIBR-0241's
  looser trailing-digit key safe to build.
  **Layman:** Add a "Bank" field to each account, so you can see at a glance which accounts are at which bank instead of having to match account numbers.
  Kind: feature.
  Source: user-request-2026-08-19.
  Lanes: ui, repositories, services.

- 📋 [FIBR-0284] **Import auto-detect should use the account's bank as a matching signal, not the account number alone.**
  BLOCKED ON FIBR-0283 (the `bank` field itself). File this now so the
  dependency is visible; there is nothing to build until that field
  exists.

  FIBR-0086 shipped auto-detect matching on the FULL normalised account
  number, and falls back to a manual pick whenever the number matches
  zero or multiple accounts. Four places a bank on the account earns
  its keep, in descending order of how real they are today:

  1. It makes FIBR-0086's own create-prompt promise storable. That
     bullet already says the prompt to create an unrecognised account
     is "pre-filled from statement metadata (number, BANK NAME IF
     PRINTED, type/currency where available)" - and there has never
     been a field to put the bank name in. This is the one part that
     is live the moment FIBR-0283 lands.

  2. It is the precondition that makes FIBR-0241 safe. That item
     loosens matching to trailing digits, which is a genuinely weaker
     key; bank + last-four is materially safer than last-four alone.
     Worth having in place BEFORE FIBR-0241 is built, not after.

  3. Multi-match disambiguation. FIBR-0086's "matches multiple
     accounts" branch currently falls back to a manual pick; a
     detected bank narrows it to one. Theoretical against today's
     single-bank corpus, and live the moment a second bank's account
     is added.

  4. A wrong-bank refusal signal. A statement clearly from bank X
     whose only number match is an account at bank Y is evidence of a
     collision rather than a match, and should refuse rather than
     auto-file - cf. FIBR-0059, never silently import to the wrong
     account.

  Design note: detecting the bank FROM the statement is the limiting
  factor, not storing it. The only dedicated reader today is Standard
  Bank (FIBR-0050); other banks are FIBR-0074. So scope this to a
  best-effort bank hint with a manual fallback, in the same
  smart-default-never-silent shape FIBR-0086 already uses. Where no
  bank can be read off the statement, behaviour must be exactly what
  it is today.

  Do NOT infer a bank from an account number's shape or prefix. That
  is the fragile guess FIBR-0283 exists to remove, reintroduced one
  layer down.
  **Layman:** Once accounts know which bank they belong to, statement auto-filing can use that too - so it picks the right account when two accounts look alike, and refuses rather than guessing when the statement is clearly from a different bank.
  Kind: feature.
  Source: user-request-2026-08-19 (adjacency raised while filing FIBR-0283).
  Lanes: services, importers, ui.

### ⚡ Performance

- ✅ [FIBR-0025] **Enable SQLite WAL mode.**
  Set
  `PRAGMA journal_mode=WAL` on the SQLCipher DB for better write
  throughput and UI responsiveness during import. *Sequencing:* set at DB
  creation (FIBR-0004). WAL adds `-wal` / `-shm` sidecars (already
  ignored by FIBR-0002; SQLCipher encrypts them too). Target phase: P02.
  Dependencies: FIBR-0004. Lanes: persistence, perf. Kind: perf.
  Source: user-request-2026-07-01.
  Resolved 2026-07-17 (commit 6c74966): journal_mode=WAL on the LIVE vault connection (set at create, converted on open) — readers no longer block the import writer. synchronous stays at the default FULL so per-commit fsync preserves the create() DB-durable-before-sidecar ordering (FIBR-0005 INV-5). The transient restore/backup-assembly connection (in_memory_temp) keeps the rollback journal, since backup._install moves vault.db at the file level without its -wal sidecar (FIBR-0014 INV-1 preserved).
  Kind: perf.
  Lanes: persistence, perf.

- ✅ [FIBR-0026] **Index the import de-duplication lookup.**
  Add a DB
  index on `(account_id, date, amount)` (and/or a normalised-description
  hash column) so import dedup (design.md data-flow step 5) is an indexed
  lookup, not an O(n·m) scan of existing rows for every imported row.
  Target phase: post-MVP perf (after P05 — FIBR-0007 ships the un-indexed
  MVP dedup by design; index it when a large account measures slow).
  Dependencies: FIBR-0007. Lanes: data, perf. Kind: perf.
  Source: user-request-2026-07-01.
  Resolved 2026-07-17 (commit 6c74966): the dedup lookup is now an indexed probe via the composite transactions(account_id, occurred_on, amount_minor) index (shipped under FIBR-0098). design.md's un-indexed MVP dedup is now index-backed.
  Kind: perf.
  Lanes: data, perf.

- 📋 [FIBR-0027] **SQL-side dashboard aggregation + incremental refresh.**
  Compute dashboard summaries / charts with SQL `GROUP BY` rather than
  Python loops, and refresh incrementally on a single-row edit instead of
  a full recompute; add supporting indexes (`date`, `category_id`). Keeps
  the dashboard fast at tens of thousands of transactions. Target phase:
  P10. Dependencies: FIBR-0012. Lanes: reporting, perf. Kind: perf.
  Source: user-request-2026-07-01.
  **Layman:** The dashboard stays fast once you have tens of thousands of transactions, and editing one row no longer recalculates everything.
  Kind: perf.
  Lanes: reporting, perf.

- 📋 [FIBR-0028] **Virtual table model for the transaction list.**
  Back
  the transaction table with a `QAbstractTableModel` (lazy / virtual
  rows) rather than per-row widgets, so a large history scrolls smoothly.
  Target phase: P10. Dependencies: FIBR-0012. Lanes: ui, perf.
  Kind: perf. Source: user-request-2026-07-01.
  **Layman:** A long transaction history scrolls smoothly instead of slowing down as it grows.
  Source: user-request-2026-07-01.
  Lanes: ui, perf.

---

- ✅ [FIBR-0071] **Add DB indexes for the import-dedup + count lookups (full-table scans today).**
  No CREATE INDEX anywhere in migrations.py. TransactionRepository.existing_for() (WHERE account_id, occurred_on, amount_minor) runs once per distinct (date, amount) bucket inside every import — N full scans; same for count_for_account / count_for_category / rules count_for_category. Fine at today's personal scale (design.md accepts it) but a multi-year vault degrades. A composite index on transactions(account_id, occurred_on, amount_minor) plus single-column indexes on account_id/category_id/statement_period_id would flatten it. Overlaps FIBR-0026 (indexed dedup lookup).
  Kind: perf.
  Source: indie-review-2026-07-10 (M-data3).
  Resolved 2026-07-17 (commit 6c74966): shipped together with FIBR-0098. The composite transactions(account_id, occurred_on, amount_minor) flattens existing_for() import-dedup + count_for_account; categorization_rules(category_id) covers the rules count_for_category. EXPLAIN QUERY PLAN test proves the dedup probe is an indexed search, not a scan.

- 📋 [FIBR-0097] **Virtualize the transaction tables — QTableWidget → QTableView + QAbstractTableModel.**
  Verified 2026-07-11: Home, Statements, and Rules use QTableWidget (ui/home.py, ui/statements.py, ui/rules.py), which builds a widget for EVERY cell — fine at 50 rows, sluggish at thousands. Migrate to QTableView + a QAbstractTableModel so rendering is virtualized (only visible rows built). Also a cleaner data/view separation that FIBR-0012 (sort/filter) and FIBR-0084 (movable/resizable columns) build on naturally. Sizeable refactor; own spec. Deps: FIBR-0051/0052 (the current widgets).
  **Layman:** Keep the transaction lists fast even with thousands of rows by only drawing the rows you can actually see.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.

- ✅ [FIBR-0098] **Add database indexes on the hot query columns.**
  Verified 2026-07-11: the schema (migrations.py) declares NO indexes. Add them on the frequently-queried columns — transactions(occurred_on), transactions(account_id), transactions(category_id), transactions(statement_period_id) (+ any dedup/lookup key). A forward migration (current v7 -> v8). Speeds listing, filtering (FIBR-0012), cross-source dedup, and delete-cascade. Cheap, high-value. Deps: FIBR-0005/0006/0010/0052 (the columns).
  **Layman:** Add quick-lookup indexes so finbreak finds and filters transactions fast as your history grows.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.
  Resolved 2026-07-17 (commit 6c74966): v9->v10 forward migration adds five indexes on the hot columns — transactions(account_id, occurred_on, amount_minor) [composite; its account_id prefix also serves count_for_account, so no redundant standalone account_id index], transactions(occurred_on), transactions(category_id), transactions(statement_period_id), and categorization_rules(category_id) [the rules half of the category-delete blast radius]. Pure-DDL, atomic (one owned transaction; a wedged build rolls back to a re-openable v9). Subsumes FIBR-0071 + FIBR-0026. New tests/features/db_performance/ suite; full gate green.

- 📋 [FIBR-0099] **Faster cold start — PyInstaller --onedir inside the AppImage (skip per-launch extraction).**
  Verified 2026-07-11: the release build uses PyInstaller --onefile (scripts/_build-smoke-in-container.sh:85), which re-extracts the whole bundle to /tmp on EVERY launch (adds seconds of cold-start latency). Since the AppImage is ITSELF a self-contained mounted container, freeze with --onedir and place the dir inside the AppDir — the app then runs directly, no per-launch extraction. Transparent to the user; measure before/after start time and confirm the FIBR-0003 clean-room bundling proof still passes. Deps: FIBR-0003/FIBR-0054 (build pipeline).
  **Layman:** Make the app open faster by not unpacking itself every single time you launch it.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0104] **Move slow statement import onto a worker thread (responsive UI + native overlap).**
  User idea (multi-threading for performance). Honest framing: Python's GIL means threading helps RESPONSIVENESS + native-code overlap, NOT pure-Python CPU parallelism. The app already threads its two slow blocking ops correctly (Argon2 key derivation via DeriveWorker; network via UpdateCheck/DownloadWorker — both native/GIL-releasing). Best next win: move IMPORT (pdfplumber text extraction, in-memory pikepdf decrypt, CSV/OFX parse, dedup + commit) onto a QThread worker (reuse the ui/_worker.py DeriveWorker pattern) with a progress indicator — today it runs ON THE UI THREAD (security-model / FIBR-0075 note: pdfplumber extract runs on the UI thread), so a large statement freezes the window. These ops are native-heavy (pdfplumber/pikepdf C++, SQLCipher C) so they RELEASE the GIL → genuine overlap with the GUI. CAVEAT: SQLite/SQLCipher connections are NOT shareable across threads — the worker needs its OWN connection to the vault (or marshal results back via signals). Pure-Python CPU hotspots (rule matching) won't benefit (GIL) — indexes (FIBR-0098) + virtualized tables (FIBR-0097) are the levers there. Deps: FIBR-0007/0008/0009 (import), reuses the QThread worker pattern; pairs with FIBR-0065 (non-blocking dialog discipline)."
  **Layman:** When importing a big statement, do the heavy reading on a background thread with a progress bar so the window stays responsive instead of freezing.
  Kind: perf.
  Source: user-suggestion-2026-07-11.

- 📋 [FIBR-0147] **Index the transfer_pairs cascade-delete FK columns.**
  Surfaced while shipping FIBR-0098. `transfer_pairs` (FIBR-0011) has two
  `ON DELETE CASCADE` FKs — `txn_a_id` / `txn_b_id` REFERENCES transactions(id) —
  but SQLite does NOT auto-index FK columns, so each transaction delete scans
  `transfer_pairs` for a match. `delete_for_statement` deletes many transactions
  at once (one statement), so a bulk statement delete is O(deleted × pairs). The
  table is small today (only confirmed/rejected pairs), so it was left OUT of the
  FIBR-0098 index set to stay in-lane. Add `CREATE INDEX` on
  `transfer_pairs(txn_a_id)` and `transfer_pairs(txn_b_id)` (a v10->v11 forward
  migration) if a large multi-year vault with many detected transfers measures a
  slow statement delete. Kind: perf.
  **Layman:** Make deleting a big statement fast even when transfers have been detected.
  Kind: perf.
  Source: claude-suggestion-2026-07-17 (deferred from FIBR-0098).

### 🧹 Warnings & tech debt

Every warning or error found during any work — tests, gate, build, tooling,
dependencies, review — is filed here (or the most fitting section) for later
investigation/resolution, even when third-party or non-blocking. A warning today
is a future error tomorrow.

- ✅ [FIBR-0043] **Silence/resolve ofxparse's bs4 findAll DeprecationWarning noise in the test run.**
  Surfaced by FIBR-0008 (2026-07-04). Running `tests/features/ofx_import/` emits ~100 `DeprecationWarning: Call to deprecated method findAll. (Replaced by find_all)` — raised INSIDE `ofxparse` 0.21 (`ofxparse.py` calling BeautifulSoup's deprecated `findAll`), not our code. Harmless today (tests pass), but: (a) it's log noise that masks real warnings, and (b) a future bs4 major could turn `findAll` into a hard error, breaking OFX import. ofxparse 0.21 is the current latest (lightly maintained), so there's no newer release to bump to. Options: a scoped pytest `filterwarnings` ignore for ofxparse's DeprecationWarning (documented, so it doesn't hide OUR deprecations); upstream a PR to ofxparse (findAll -> find_all); or, if bs4 ever breaks it, migrate to a maintained parser (ofxtools) — the escape hatch already noted in FIBR-0008 § Dependencies. Decide + apply.
  **Layman:** The OFX-import library prints ~100 harmless "this method is old" warnings whenever we run our tests; the app works fine, but the noisy warnings should be quietened or fixed at the source.
  Kind: investigate.
  Source: in-session-2026-07-04 FIBR-0008 build/test warnings.
  Resolved (2026-07-10): already delivered by FIBR-0058 — the scoped pytest `filterwarnings` ignore for "Call to deprecated method findAll.*" plus the `beautifulsoup4>=4.9,<5` pin are both live in pyproject.toml. This was the investigate twin of the FIBR-0058 chore; no additional code needed. Closing as superseded.

- ✅ [FIBR-0057] **Import wizard snapshots the target account at file-select — a later dropdown change is ignored.**
  ui/import_wizard.py `_select_file` (line ~255) does `self._account_id = self._account_combo.currentData()` and bakes it into the preview; the account combo lives on step 0 only and changing it after a file is chosen does not re-read or re-preview. Combined with the combo defaulting to the first account, a user who doesn't set the account BEFORE choosing the file (or wants to change it after) silently imports under the wrong account. Fix options: (a) read the account at commit time (decouple from the snapshot); (b) keep the account picker editable through the flow and re-run dedup/preview on change; (c) at minimum, disable the combo once a file is picked + surface the chosen account on the preview step so it's visible before commit. Prefer (a)+(c). Needs a reproduction test. Related to the FIBR-00xx edit-statement-account feature (which lets a user fix a mis-link post-import).
  **Layman:** When importing a statement, if you change which account it goes into AFTER picking the file, the app ignores the change and uses the first account (e.g. "Current"). This is how a credit-card statement can land on the wrong account.
  Kind: fix.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): the preview step now carries a destination-account picker that is the single source of truth for the committed account — seeded from the pick step at file-select, read live via _target_account_id() by every preview + the per-account PDF-password lookup, and user-correctable before the irreversible Import (changing it re-runs the dedup via ImportService.retarget). Cold-review fold: a remembered PDF password now follows a re-target onto the committed account. Tests: import_ FIBR0057 x3 (retarget re-dedups; preview exposes the destination; changing it re-targets the whole commit) + pdf_import FIBR0057 x1 (remembered password follows the corrected account). Gate green 348 passed/1 skipped, mypy 0, audit 0. Commits 4be777c + ba6d912.

- ✅ [FIBR-0058] **ofxparse emits BeautifulSoup findAll DeprecationWarnings (107 per test run).**
  The gate run shows 107 `DeprecationWarning: Call to deprecated method findAll. (Replaced by find_all) -- Deprecated since version 4.0.0` from ofxparse (ofxparse.py:445/449/454/949), which calls BeautifulSoup's long-deprecated `findAll`. It is inside the ofxparse dependency, not our code, so we can't fix the call directly. Options: (a) pin/track ofxparse for an upstream fix or a maintained fork; (b) filterwarnings in pytest config to quiet the known-3rd-party warning (documented, not a blanket ignore); (c) evaluate replacing ofxparse if it stays unmaintained. BeautifulSoup will eventually remove `findAll`, which would then break OFX import — so this is a latent breakage, not just noise. Investigate + decide.
  **Layman:** A dependency the app uses for one import format prints lots of "deprecated" warnings during tests. Harmless today, but noisy and a sign the dependency is aging.
  Kind: chore.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): investigated — ofxparse 0.21 is the latest PyPI release (unmaintained since 2023; no find_all fix to track), and bs4 4.15 still ships findAll as a deprecated alias (removal slated for bs4 5.0). Two-part root-cause fix, not a blanket silence: (a) scoped pytest filterwarnings ignoring ONLY "Call to deprecated method findAll..." (our own future deprecations still surface); (b) beautifulsoup4>=4.9,<5 pin in [project].dependencies — the latent-breakage guard, since an unpinned bs4 5.0 (findAll removed) would break OFX import; bs4 is only reached transitively via ofxparse. Gate 352 passed, 0 warnings (was 107); pip check clean. Option (c) — replacing ofxparse — deferred (large; FIBR-0008 built OFX import around it); revisit if ofxparse stays unmaintained when bs4 5.0 becomes necessary. Audit 0 (ruff/bandit skipped — pyproject-only). Config-only chore, no multi-agent review warranted. Commit below.

- ✅ [FIBR-0060] **Window geometry restore + Center Window don't work on Wayland (FIBR-0052 was X11-assumed).**
  Reported on KDE Wayland. Root cause: FIBR-0052 (INV-5 geometry persistence, INV-6
  Center window) assumed X11 semantics. On Wayland the compositor owns window
  placement — an app cannot set/restore its own POSITION, and move()/setGeometry-pos
  is a no-op — so Center Window can never work and position-restore is impossible;
  size-restore via restoreGeometry is also unreliable before first map. Verified:
  saving works (~/.local/share/finbreak/window.ini has a geometry key), and
  _restore_geometry calls restoreGeometry before show — but Wayland ignores the
  position, and the FIBR-0052 tests only asserted the QSettings round-trip (offscreen
  platform), never real WM behaviour, so they passed while the feature is broken for
  the user. Fix plan: (a) restore SIZE explicitly via resize() (Wayland allows size
  requests) and confirm it sticks; (b) on Wayland, disable/grey Center window +
  position-restore with a tooltip (or drop them there) since the compositor centres
  windows itself — keep them on X11 where they work; (c) detect the platform
  (QGuiApplication.platformName()); (d) add a test that exercises the real behaviour,
  not just the settings round-trip. My code (FIBR-0052) — own it. Related to the
  sole-author no-Wayland-coverage gap.
  **Layman:** The app doesn't remember its window size/position between runs, and Window → Center Window does nothing. On modern Linux (Wayland), apps aren't allowed to position their own windows, so parts of this can't work the way they were built.
  Kind: fix.
  Source: user-report-2026-07-09.
  Resolved (2026-07-09): platform-aware geometry. _is_wayland()/_kde_wayland()/_center_supported() gate behaviour. On Wayland the SIZE is restored via resize() from a bare window_size key (the compositor honours a size request; restoreGeometry's size is unreliable pre-map) — matching the SystemManager reference. Center window is IMPLEMENTED on KDE Wayland via KWin's scripting D-Bus API (QtDBus loadScript/start/unloadScript of a PID-matched centring script — the SystemManager technique, ported to QtDBus so no dbus-send subprocess); disabled with a tooltip on other Wayland compositors (no app-usable placement API); X11/Windows/macOS keep move(). Position-restore on launch stays compositor-owned on Wayland (as SystemManager also accepts). LIVE-VERIFIED on the user's KDE Wayland: window centres exactly (work-area offset dcx=0 dcy=0). Tests: FIBR0060 x4 (size restore; KWin dispatch on KDE; disabled+no-op on non-KDE; enabled off Wayland) via monkeypatched _is_wayland/XDG_CURRENT_DESKTOP. Cold-review fold: temp-file-leak-on-write-failure + Plasma-version doc accuracy. Gate green 352 passed/1 skipped, mypy 0, audit 0. Commits 36e0ea1 + review fold. Note: the FIBR-0052 INV-5/INV-6 tests only asserted the QSettings round-trip (offscreen), never real WM behaviour — now both platform branches are exercised.

- ✅ [FIBR-0061] **mypy is not enforced by the gate, and `mypy src tests` reports 4 pre-existing type errors in test files.**
  Found while closing FIBR-0059. `scripts/ci-local.sh` (the gate, run by the
  pre-push hook + ci.yml) runs ruff / format / bandit / pip-audit / gitleaks /
  pytest but NOT mypy — so the journal's repeated "mypy 0" claims came from ad-hoc
  manual runs (often `mypy src`, not the config's `files = ["src", "tests"]`), and
  type errors in the test tree were never gated. `mypy src tests` (mypy 2.1.0)
  currently reports 4: tests/features/settings/test_settings.py:70/75/80 (a
  findChild helper returning QComboBox|None / QDialogButtonBox|None dereferenced
  without a None-guard — FIBR-0055 code) and tests/features/app_shell/
  test_app_shell.py:83 (a fake QThread subclass whose start() override signature is
  incompatible). None are runtime bugs (test-only typing), but they hide real
  regressions. Fix: (a) add a mypy stage to ci-local.sh so it's actually enforced;
  (b) fix the 4 (cast/assert the findChild Optionals; align the fake start()
  signature). My code (sole author). NB FIBR-0059's own new src is mypy-clean.
  **Layman:** The type-checker (mypy) that catches whole classes of bugs isn't actually run by the automated quality gate, and running it by hand turns up 4 small type issues in the test code that have gone unnoticed.
  Kind: chore.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): added a `mypy` stage to `scripts/ci-local.sh` (after gitleaks, before pytest — bare `mypy` uses the config's `files = ["src","tests"]`), so CI (which invokes ci-local.sh) now enforces it too; the dev group already pins `mypy==2.1.0`. Fixed the 4 test-tree errors: `assert ... is not None` guards on `_combo`/`_click_save`/`_click_cancel` in `tests/features/settings/test_settings.py`, and aligned `_StubWorker.start` to the `QThread.start(self, priority=...)` signature in `tests/features/app_shell/test_app_shell.py`. Gate green: 366 passed / 1 skipped, mypy clean (59 files), shellcheck 0.

- ✅ [FIBR-0062] **Test-audit: hoist duplicated paths/service/_PW fixtures + connection-proxy helpers to shared conftest.**
  All 4 /test-audit chunks flagged this. The identical `paths` fixture, `_PW` literal, `_FailAt*`/`_StandInVault` connection-proxy classes, and `_acct`/`_wizard`/`_default_id`/`_pump_deferred_delete`/`_two_accounts` helpers are copy-pasted across ~9 tests/features/* files (Rule-of-Three well exceeded). Extract to tests/conftest.py (paths + _PW import + a raising_proxy(real, trigger, message) factory). The window_ini autouse fixture was already hoisted 2026-07-10 as part of the CRITICAL isolation fix.
  **Layman:** Lots of test files copy-paste the same setup code; move it to one shared place so a change only needs editing once.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): hoisted the copy-pasted test infrastructure to tests/conftest.py — the `paths` fixture (was duplicated in 11 feature suites), the `_PW` literal (3 remaining local copies → imported from conftest, joining the 8 that already did), a generic `raising_conn(real, trigger, message, on=)` factory + a `StandInVault` class replacing 7 bespoke `_FailAt*`/`_StandInVault` wedge classes across 5 suites (the migration + service atomicity-rollback tests), and the `_acct` (5 copies) + `_pump_deferred_delete` (3 copies) helpers. Deliberately NOT hoisted (Rule-of-Three not met / not identical): the `service` fixture (varies — some suites first_run, some don't), `_default_id` (varying signature: service vs vault), `_two_accounts` (single-site). Gate green 440 passed/1 skipped, mypy 0 (fresh cache), ruff clean.

- ✅ [FIBR-0063] **Test-audit: parametrize repeated single-assert tests + split multi-claim tests.**
  Convert the four standard_bank INV11 checksum/completeness tests and the three INV2a per-family detection asserts to @pytest.mark.parametrize(ids=...) so one failure doesn't mask siblings; same for the import_ bad-mapping-config loop (test_import.py:263). Consider splitting statements INV5a's 7-claim test (esp. the plaintext-leak security checks).
  **Layman:** Some tests bundle several checks in one; splitting/parametrizing them makes a failure point at the exact broken case.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): parametrized the genuine bundled-assert/loop tests so one failure can't mask siblings — standard_bank test_INV2a_each_family_detected_by_its_own_signature (3 bundled asserts → @pytest.mark.parametrize ids=family_b/d/c) and import_ test_service_rejects_bad_mapping_config (the `for bad in (...)` loop → parametrized test_service_preview_rejects_bad_mapping_config ids=no_amount_style/missing_column/both_styles; the distinct save_profile path split into its own test). Split the statements INV5a omnibus: the plaintext-leak SECURITY checks (no txn description/amount in the geometry INI) now live in a dedicated test_INV5a_no_transaction_data_leaks_to_plaintext_ini so a geometry-persistence regression can't mask a data leak. The four standard_bank INV11 checksum/completeness tests were left as-is — they are already SEPARATE test functions (independent failure points), so parametrizing would only DRY, not fix masking. Gate green, ruff clean.

- ✅ [FIBR-0064] **Test-audit: add tests for untested error branches surfaced by the audit.**
  Untested branches: UnlockDialog SchemaVersionError (HIGH); FirstRunDialog create-failure except; AuthService.unlock() password-wipe-on-failure; CategoryService._require_parent ValueError; categorization.move_rule unknown rule_id; import_wizard _decrypt_pdf/_extract_pdf_tables friendly-error paths (wizard-level); StatementService.list_statements ordering contract; standard_bank corrupt-PDF wizard message (assert substring, not != ''); and the 5 auto-lock 'must not raise' tests should gain a concrete post-click state assertion.
  **Layman:** A few error-handling paths in the app have no test; add regression tests so a future change can't silently break them.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): added regression tests for the untested error branches + strengthened the weak ones. New tests: move_rule unknown-id no-op (categorisation); _require_parent bad-parent-id ValueError (categories — the None-parent branch was already covered); list_statements import-recency ordering (statements); AuthService.unlock password-wipe on load_params failure (vault/security-INV-3); UnlockDialog SchemaVersionError 'newer version' message (vault, driven via _on_derived to skip Argon2); FirstRunDialog 'Could not create the vault' create-failure (vault). Strengthened: the standard_bank corrupt-PDF test now asserts the friendly-message SUBSTRING (not != '') — which REVEALED + FIXED a real UX bug: the wizard caught PdfError but showed str(exc) (raw pikepdf 'unable to find trailer dictionary...') rather than the friendly message; added _show_pdf_read_error() mapping PdfError→friendly at the 3 PDF catch sites (import_wizard). The 5 auto-lock 'must not raise' tests (4 categorisation INV14 + statements reassign) each gained a concrete post-click state assertion (row unchanged / rule-created / error-empty / txn-stayed-on-account). Gate green 452 passed/1 skipped, mypy 0, ruff clean.

- ✅ [FIBR-0065] **Fix the auto-lock-during-modal-dialog crash (reproduced HIGH).**
  REPRODUCED (Qt DeferredDelete is processed inside a nested exec() loop): an idle auto-lock fires while a content-widget dialog is exec()-blocking; MainWindow._lock() -> _clear_live() -> workspace.deleteLater() destroys the dialog's parent chain during that nested loop, so the post-exec() call (home.py CategoryPickerDialog.selected_category_id(); import_wizard.py PasswordDialog.password()/remember(); also statements.py, rules.py) hits a deleted C++ object -> RuntimeError, which the VaultLockedError guards do NOT catch. The existing guards only cover 'dialog closes BEFORE lock', not 'lock DURING exec()'. Needs its own spec+cold-eyes+TDD cycle (lifecycle-critical security code). Proposed approach: either convert content-widget dialogs to the shell's non-blocking setModal(True)+show() pattern (FIBR-0051 D2 rejected exec() for exactly this), OR a MainWindow modal-registry that wipes the key immediately (security preserved) but defers the UI teardown until the nested loop unwinds. Recommend prioritising ABOVE FIBR-0054.
  **Layman:** If the app auto-locks itself while a small pop-up (pick a category, edit a rule, enter a PDF password) is open, it can crash instead of locking cleanly.
  Kind: fix.
  Source: indie-review-2026-07-10 (full-codebase sweep, H-B).
  Started 2026-07-10. Approach chosen with the user: convert the remaining blocking exec() content-dialogs to the shell's non-blocking setModal(True)+show()+signal pattern (matches FIBR-0051 D2). Spec → cold-eyes → TDD next.
  Resolved 2026-07-10. Converted the 6 blocking exec() content-widget pop-ups (home set-category + learning offer, rules add/edit, statements reassign, import-wizard PDF password) to the non-blocking show_modal (setModal+show()+signal) pattern; PDF password loop → the _try_decrypt state machine. Spec /cold-eyes-converged (5 loops); TDD: dialog_lifecycle INV-1 grep + a real _lock()-during-open-PDF-prompt regression (INV-2 guard-less path) + parity ripple. Gate green 437 passed/1 skipped, mypy 0; /audit 0; a cold code-review lane confirmed the D5 semantics faithful (doc-nits only, folded). Tag FIBR-0065-complete.

- ✅ [FIBR-0066] **Refactor the 6x duplicated BEGIN/COMMIT/ROLLBACK transaction boilerplate into one owned-transaction helper.**
  Identical BEGIN / try:...commit() / except: rollback(); raise appears 6x in services (categorization apply_rules/set_manual_category/move_rule, categories delete_category, import_ commit_import, statements delete/reassign) and 6x in migrations.py. A vault.owned_transaction() context manager would collapse both and remove the risk a 7th call site copies it with a subtly wrong exception class. Load-bearing atomicity code — do carefully with tests.
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-C3, corroborated x2: crypto-vault migrations.py + core-services).
  Resolved (2026-07-10): extracted owned_transaction(conn) context manager into new src/finbreak/db.py — the single BEGIN…COMMIT / ROLLBACK-and-reraise boundary. Replaced all 13 hand-rolled sites: 7 services (categorization move_rule/apply_rules/set_manual_category, categories delete_category, import_ commit_import, statements delete_statement/reassign_account) + 6 migrations (v2→v7). Deliberately a free function on a bare Connection, not a Vault method, so migrations.py (which vault.py imports) can use it without an import cycle. No behavior change — all atomicity tests (import INV-7 rollback, migration atomicity, delete-cascade INV-7, move_rule two-row swap) stay green. mypy 0, 248 affected tests pass.

- ✅ [FIBR-0067] **Widen the Standard Bank _MONEY regex to accept ungrouped 4+-digit amounts, then re-validate against the real statements.**
  standard_bank.py _MONEY = r'(?<![\d.,])\d{1,3}(?:[.,]\d{3})*[.,]\d{2}(?!\d)' fails to match an amount >= 1000 printed WITHOUT a thousands separator (e.g. '1500.00' -> no match), so a statement with an ungrouped opening/closing balance fails with the generic mis-parse. Degrades SAFELY (friendly error, no corruption); none of the 6 validated real statements exhibit it. NOT folded in the audit sweep: the naive fix (\d{1,3}->\d+) risks a NEW false positive (a dotted date like 2026.07.15 -> spurious '2026.07' token), and this parser was validated end-to-end on a real-statement corpus not available in-session. Fix + re-validate against all 6 real statements as its own item.
  Kind: fix.
  Source: indie-review-2026-07-10 (M-imp1).
  Blocked (2026-07-10): deliberately NOT fixed in the audit-fix sweep — the SB _MONEY regex is a validated parser and there is no real-statement corpus in-session to re-validate against. A naive widening to accept ungrouped 4+-digit amounts risks a dotted-date false positive (e.g. matching a date fragment as money), which would silently mis-parse. Needs real anonymised sample statements (same blocker as FIBR-0074's dedicated ABSA/Nedbank/FNB readers) to widen + re-run the six-statement checksum corpus. Keep planned; revisit when sample statements are available.
  Resolved (2026-07-10): UNBLOCKED — the user provided the six real Standard Bank statements (one per family: Credit Card/Current/Home Loan/Money Market/RCP/Savings) + the password. Reproduced first: all six PASS with the current regex, and ZERO ungrouped 4+-digit tokens appear (SB always groups thousands). Widened _MONEY to also accept an ungrouped run: `(?:\d{1,3}(?:[.,]\d{3})*|\d{4,})[.,]\d{2}`, with a `(?![.,]?\d)` tail guard against the dotted-date false positive the earlier defer flagged (2025.07.21 rejected; 3-decimal rates still rejected). Re-validated against all six real statements in a throwaway harness — EXACT same txn counts (53/82/27/20/30/3), zero regression. Added a synthetic parametrized _MONEY unit test (grouped/small/ungrouped-4/7-digit/reject-3dp-rate/reject-dotted-date/iso-date). The real statements + password were NEVER committed (validated in scratchpad, since deleted; the committed test uses synthetic strings only — testing.md §6). Gate green 460 passed/1 skipped, mypy 0, ruff clean.

- ✅ [FIBR-0068] **Promote the _set_combo(combo, value) helper to a shared UI util and dedup the 7x findData+setCurrentIndex idiom.**
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-dlg4).
  Resolved (2026-07-10): extracted the guarded combo-preselect idiom (index = combo.findData(v); if index >= 0: combo.setCurrentIndex(index)) into select_combo_data() in new src/finbreak/ui/_widgets.py, and converted the 6 sites (settings/accounts/categories type combos + rules/category_picker/account_picker id combos). IMPORTANT distinction surfaced, not forced: kept DISTINCT from ImportWizardWidget._set_combo, which is UNGUARDED by design — the wizard wants a saved-profile column absent from the current file to CLEAR the combo (force a re-pick), whereas the picker/dialog sites keep the current selection when a value isn't found. Merging them would have been a silent behavior change. mypy 0, 165 UI tests pass.

- ✅ [FIBR-0069] **Extract a _signed_balance_from_tokens helper for the 4x duplicated Standard Bank balance-token parse.**
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-imp3).
  Resolved (2026-07-10): extracted _signed_balance(token, fmt) in standard_bank.py — the single home of the '-parse if _is_negative else parse' idiom. Replaced 7 occurrences (the reviewer's 'x4' undercounted): the brought-forward/opening captures (_capture_opening x2, credit-card opening, _anchor_balance) + the per-row balance in Families A/B/D. Named _signed_balance (a single token) rather than the tentative _signed_balance_from_tokens, since every site passes one token. No behavior change — all family checksums + per-row sign gates stay green (83 SB/PDF tests). ruff/mypy 0.

- ✅ [FIBR-0070] **Decide the fate of the unwired ImportProfileRepository.list_all() (build a manage-saved-profiles screen, or remove it).**
  list_all() has zero callers in src/ — the wizard only auto-matches by signature and saves. Either an intended 'manage saved import profiles' feature was never wired up, or it is dead weight. Decide feature-vs-delete.
  Kind: chore.
  Source: indie-review-2026-07-10 (M-data1).
  Loop-2 review (2026-07-10): ImportProfileRepository.get() is also unwired in src/ (only test callers) — the other half of the never-built manage-profiles screen. Fold get() into this decision (wire both up, or remove both).
  Resolved (2026-07-10): KEEP (user rule: 'if we'll use it later, leave it'). No roadmap item commits to a manage-profiles screen, but the saved-import-profiles feature is shipped (FIBR-0007) and a 'manage saved profiles' view (see/rename/delete accumulated bank layouts) is its natural completion — a plausible later use, not a far-fetched hypothetical. list_all/get (+ update) are the read/edit API that view needs; removing tested working methods only to re-add them is negative-value churn (and would force rewriting a legitimate upsert test's observation). Neutralised the audit's 'dead weight?' concern by DOCUMENTING intent in the ImportProfileRepository module docstring (kept-not-deleted, remove only if the view is dropped from the roadmap). No behavior change.

- ✅ [FIBR-0075] **Bound PDF per-page decompressed content size (decompression-bomb / zip-bomb vector).**
  Caps today are whole-file bytes (16 MiB), page count (500), and extracted row count (100k) — none bound the DECOMPRESSED size of a page's Flate-compressed content stream, so a small in-cap PDF can expand to GBs before extract_tables()/extract_text() returns (on the UI thread). security-model.md §5 explicitly names FIBR-0009 as responsible for THIS vector, but the code doesn't implement it — a real spec-vs-code gap. Non-trivial: pdfplumber/pdfminer don't easily expose a streaming size bound; likely needs a pdfminer-level limit or a subprocess with rlimits. Investigate + implement, or document the residual risk explicitly.
  **Layman:** A small, valid PDF whose page decompresses to gigabytes could hang or OOM the app when imported.
  Kind: security.
  Source: indie-review-2026-07-10 loop-2 (statement H2).
  Resolved (2026-07-10): assessed + documented as accepted residual risk (the roadmap-sanctioned option; user deferred the call to me). security-model.md INV-5b previously implied FIBR-0009 bounds the decompression/zip-bomb vector — the code does NOT (caps are file-size 16 MiB / 500 pages / 100k rows; none bound a page's DECOMPRESSED Flate stream). INV-5b now states this honestly: the decompressed-size residual is ACCEPTED for a local single-user app (threat = the user opening a file they chose, not a server ingesting untrusted uploads); the robust fix (extraction in a memory-capped subprocess — POSIX RLIMIT_AS / Windows Job Objects) is disproportionate + cross-platform-heavy, and pdfplumber/pdfminer expose no cheap in-process streaming bound. T5 row annotated with the residual + pointer. Revisit if PDFs ever arrive from an untrusted channel. No code change — a spec-vs-code gap closed by making the claim honest.

- ✅ [FIBR-0076] **Single-instance / busy_timeout handling so two app copies don't crash with a raw OperationalError.**
  _connect sets PRAGMA key + foreign_keys only; SQLite default busy_timeout is 0. Two instances (or a slow backup/AV holding a read lock) make the second write raise sqlite3.OperationalError uncaught -> unhandled traceback. Add PRAGMA busy_timeout and/or an explicit single-instance guard (QLocalServer / lockfile) at the app layer.
  Kind: fix.
  Source: indie-review-2026-07-10 loop-2 (crypto M2).
  Resolved (2026-07-10): _connect now issues `PRAGMA busy_timeout = 5000` (vault.py) — a second instance or a slow backup/AV holding a transient lock now serialises via SQLite's locking (waiting up to 5s) instead of the second write raising a raw sqlite3.OperationalError. This fixes the reported crash symptom; SQLite's file locking already guarantees no corruption under concurrent access, so the busy_timeout is sufficient. A QLocalServer/lockfile single-instance guard (preventing two windows at all) was considered but is a UX nicety, not required for crash-safety — deliberately NOT built (simplicity-first). Regression test asserts the PRAGMA value.

- ✅ [FIBR-0077] **Explicitly pin PRAGMA cipher_use_hmac = ON in _connect (defense-in-depth for INV-1 tamper-evidence).**
  security-model.md INV-1 states tamper-detection as a code guarantee, but _connect never sets cipher_use_hmac — it rests entirely on sqlcipher3-binary==0.6.0's SQLCipher-4 default. A future dep bump changing the default would silently weaken it (global rule §5). NOTE: FIBR-0004 D4 deliberately chose to ASSERT the default rather than re-configure it (test-covered), so this is a spec-level decision to reconsider, not a drive-by — needs a D4 revisit before changing.
  Kind: security.
  Source: indie-review-2026-07-10 loop-2 (crypto M4, flagged x2).
  Resolved (2026-07-10): D4 revisit conclusion — pin it. _connect now issues `PRAGMA cipher_use_hmac = ON` explicitly right after `PRAGMA key` (vault.py), so INV-1 tamper-evidence is correct-by-construction rather than resting on sqlcipher3-binary's SQLCipher-4 default (which a future dep bump could flip, global rule §5). Every vault is created with the default ON, so pinning ON can never mismatch an existing file. FIBR-0004 D4 spec text updated with the revisit note; the existing INV-1 assert stays as the regression check. New test_connection_pins_hmac_and_busy_timeout covers it. Gate green.

- ✅ [FIBR-0078] **Move the Standard Bank row cap before the per-family parse (bounds computation, not just the result).**
  standard_bank.parse checks len(result.drafts) > _MAX_PDF_ROWS only AFTER _parse_family_* has run full regex + Decimal parsing over every region line — a crafted PDF with millions of transaction-shaped lines does all that work before rejection. pdf_importer.py checks its cap earlier (cheaper). Add a cheap pre-parse region-line count guard. NOTE: the current ordering is spec-consistent (FIBR-0050 Deliverable 1), so changing it needs a FIBR-0050 spec update.
  Kind: perf.
  Source: indie-review-2026-07-10 loop-2 (statement H3).
  Resolved (2026-07-10): standard_bank.parse now rejects len(region_lines) > _MAX_PDF_ROWS immediately after building region_lines — before _detect_number_format and the per-family regex/Decimal pass — so a crafted PDF with millions of transaction-shaped region lines is refused before that expensive work (bounds the computation, not just the result). The exact post-parse len(result.drafts) > _MAX_PDF_ROWS cap (FIBR-0050 Deliverable 1 / INV-14) is retained for precision (Family C de-interleaves ~2 drafts/line). FIBR-0050 spec Deliverable updated. The existing over-cap monkeypatch test (INV-14) now exercises the early guard with the same friendly ValueError; 83 SB/PDF tests green, ruff clean.

- ✅ [FIBR-0079] **Gate RuleEditDialog OK on a selectable category (zero-leaf-categories edge) + honest selected_category_id return type.**
  If a user deletes every leaf category, RuleEditDialog's combo is empty, selected_category_id() returns None (despite its -> int hint), and OK stays enabled -> add_rule(pattern, None) surfaces the confusing 'a category must be a leaf, not a Type' instead of 'create a category first'. Gate OK on combo.count() > 0 (or block Add/Edit when leaf_categories() is empty) and type selected_category_id() as int | None. FIBR-0010 D13's 'no ValueError reaches a caller through the dialog' silently fails to cover zero-leaves.
  Kind: ux.
  Source: indie-review-2026-07-10 loop-2 (core-services + ui-dialogs M2).
  Resolved (2026-07-10): RuleEditDialog._sync_ok now also requires self._category.count() > 0, so OK stays disabled with zero leaf categories; selected_category_id() typed int | None (honest). RulesWidget._on_add blocks up front with a "Create a category first, then add a rule." message when leaf_categories() is empty — the reachable path (the _on_edit + learning paths can't hit zero-leaves, since an existing rule / a manual pick both imply a live category). _apply_add/_apply_edit/_apply_learned_rule add a defensive None guard (narrows for the int-typed add_rule/update_rule). FIBR-0010 D13 spec updated to cover the edge. TDD: 2 red→green tests (dialog OK disabled with empty leaves + selected_category_id None; Add blocked + message shown). mypy 0, 74 tests pass.

- ✅ [FIBR-0080] **Route the two hand-rolled settings reads through SettingsRepository.get.**
  services/transactions.py read_minor_unit_exponent + TransactionService.base_currency hand-roll SELECT value FROM settings WHERE key=... instead of SettingsRepository(conn).get(key) (already used by auth.py). Reuse-before-rewrite (CLAUDE.md §3); a typo'd key in one copy has no lint signal. read_minor_unit_exponent needs None/int-cast handling.
  Kind: refactor.
  Source: indie-review-2026-07-10 loop-2 (data M-1).
  Resolved (2026-07-10): read_minor_unit_exponent + TransactionService.base_currency now route through SettingsRepository(conn).get(key) (services/transactions.py) instead of hand-rolling the SELECT — one seam for the key strings (reuse, CLAUDE.md §3). cast(str, value) preserves the v1-invariant 'always present' assumption per the repo's assert-over-can't-happen convention. mypy 0, 171 affected tests pass.

- ✅ [FIBR-0081] **Small type/doc debt: _on_move Literal typing, _selected_row dedup, FIBR-0007 stale INV-7 insert-order narrative.**
  (1) ui/rules.py _on_move takes direction:str + a type:ignore against move_rule's Literal['up','down'] — type the param as Literal to drop the workaround (global rule §1). (2) _selected_row is byte-identical in rules.py + statements.py (2 sites — extract on the 3rd). (3) FIBR-0007 spec's INV-7 test narrative describes the OLD insert order (transactions-before-period); FIBR-0052's statement_period_id FK reversed it (period-first) — update the spec text (or a FIBR-0052 addendum) so a reader doesn't reason about a stale order.
  Kind: doc-fix.
  Source: indie-review-2026-07-10 loop-2 (misc LOW).
  Resolved (2026-07-10): (1) ui/rules.py _on_move now types direction as Literal['up','down'], dropping the # type: ignore[arg-type] against move_rule. (3) FIBR-0007 spec INV-7 narrative corrected with a FIBR-0052 addendum — commit_import inserts the period row first (statement_period_id FK) then the transactions batch, and the wedge test raises on the transactions INSERT. (2) _selected_row dedup deliberately NOT done — only 2 sites, Rule-of-Three defers extraction to the 3rd (CLAUDE.md §3).

- 📋 [FIBR-0102] **Tighten mypy toward strict.**
  Verified 2026-07-11: [tool.mypy] sets only python_version + per-module stub-ignores — NOT strict. Enable strict (or stage it: disallow_untyped_defs, warn_return_any, disallow_any_generics, no_implicit_optional) to catch a class of bugs at the type layer — valuable for a money app. Incremental: turn flags on one at a time, fix the fallout, keep the gate green each step. Deps: none (gate/CI config).
  **Layman:** Turn on stricter automatic type-checking to catch more bugs before they ship.
  Kind: refactor.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0103] **Consolidate presentation formatting into one module.**
  FIBR-0083 introduces src/finbreak/datetime_format.py (date/time display). Fold the existing amount/currency QLocale formatting (ui/_amount.py::_format_amount -> QLocale.toCurrencyString; already lifted out of ui/home.py and now imported by 8 modules, so the remaining work is the fold into a shared formatting package) into a shared formatting package alongside it, so all presentation logic is centralised + unit-tested in one place (Rule of Three: date + currency + future). Deps: FIBR-0083 (lands the first formatter). Small refactor; do AFTER FIBR-0083 ships.
  **Layman:** Keep all the 'how numbers and dates look' code in one tidy, tested place.
  Kind: refactor.
  Source: claude-suggestion-2026-07-11.

- ✅ [FIBR-0141] **CategoryService.update_category has no descendant-cycle guard — re-parenting a category under its own child creates a cycle.**
  Found during the FIBR-0138 close (indie-review). `update_category`
  (`src/finbreak/services/categories.py`) blocks re-parenting a *root* and
  requires an existing parent, but does NOT reject moving a category under
  one of its own descendants — so X→Y→X cycles are reachable via the UI.
  `categorization.type_of` already fails loud (ValueError) on such a cycle,
  and FIBR-0138's `drill_down` was hardened to stay total against it, but
  the ROOT CAUSE is the missing guard here. Fix: in `update_category`,
  reject a `parent_id` that is the subject itself or any of its
  descendants (ascend the prospective parent's chain; if the subject is
  encountered, raise ValueError). Add a reproduce-first test. Small,
  self-contained.
  **Layman:** You can accidentally make the category tree loop back on itself (put a group inside one of its own sub-groups), which confuses the parts of the app that walk the tree; the app should refuse that move.
  Kind: fix.
  Source: indie-review-2026-07-14 (FIBR-0138 close).
  Resolved 2026-07-17: added a `_reject_cycle` guard to `CategoryService.update_category` (mirrors the depth-safe ascend-with-`seen` idiom in `categorization.leaf_categories_grouped`) — ascends from the prospective parent to the root and raises ValueError if the subject appears in that chain, so re-parenting a category under itself or one of its own descendants is refused; the `seen` set keeps the walk total against a pre-existing corrupt cycle. Reproduce-first TDD in `tests/features/categories/` (INV-5: self-parent, direct child, deep descendant all rejected; legitimate cross-branch move still succeeds). Adapted the pre-existing `categorisation` corrupt-cycle test to inject the cycle at the repository layer (below the guard) since the service now refuses to build one. Note: today's category-manager parent picker only offers the two Type roots, so the cycle was reachable via a direct service call, not that UI — the guard is the service-layer contract boundary. Gate green 1083/1, mypy 0.

- ✅ [FIBR-0150] **security-model.md header provenance line is stale (skips FIBR-0054/0131/0133).**
  The header (docs/security-model.md L3-5) reads "amended through FIBR-0014 (2026-07-13 — T11: separate-password backup recovery)" yet the body already carries FIBR-0054 (update-flow / INV-8 egress) and FIBR-0131/FIBR-0133 (Windows update / SignPath) content added since, without a header bump. Treat the line as a "most-recent material amendment" marker and either (a) document that semantics in the header itself, or (b) backfill the missed provenance. Surfaced by the FIBR-0095 /cold-eyes lane B (loop 4). Low-priority doc hygiene; FIBR-0095 bumps the line to itself as part of its own edit.
  **Layman:** The security document's "last updated by" note names an old change and skips several newer ones — a quick tidy so it reflects reality.
  Kind: doc-fix.
  Source: cold-eyes-2026-07-18 FIBR-0095 lane-B.
  Resolved (2026-07-26, debt sweep): both halves are now in place. The
  header (docs/security-model.md L3-8) reads "amended through FIBR-0096
  (2026-07-21 — INV-13: signed SHA256SUMS + CycloneDX SBOM)", so the
  FIBR-0014 staleness is gone; and remedy option (a) is documented
  verbatim in the header itself — "This line names the most-recent
  material amendment, not a full history." Landed incidentally via the
  FIBR-0095/FIBR-0096 edits rather than as its own change, which is why
  the bullet was never flipped. Verified against source, not recalled.

- ✅ [FIBR-0165] **CSV import no longer crashes on a structurally-broken file — csv.Error is translated to a friendly ValueError.**
  indie-review (importers lane), MEDIUM. csv.DictReader parses lazily during iteration, so a field over csv.field_size_limit (e.g. an unterminated quote) raised csv.Error from the `for` line — outside the per-row try — and csv.Error is not a ValueError, so the wizard's (ValueError, FinbreakError) net missed it and the import crashed (violates INV-4 'malformed file must never crash'). Fixed in csv_importer.py: parse() materialises rows under one csv.Error->ValueError guard; read_header() guards the .fieldnames access. Regression: test_INV4_malformed_csv_surfaces_valueerror_not_csv_error.
  **Layman:** A corrupt or truncated CSV now shows a friendly 'not valid CSV' message instead of crashing the import.
  Kind: review-fix.
  Source: indie-review-2026-07-23.

- ✅ [FIBR-0166] **Argon2id acceptance floor decoupled from the creation pin so a future KDF-strength bump can't lock out existing vaults.**
  indie-review (crypto lane), LOW (data-loss footgun). validate_params checked memory_kib against the SAME ARGON2_MEMORY_KIB used to create vaults, while the docstring claimed the pin could be raised without locking out existing vaults — false. Raising the constant (per global rule §5 / an OWASP bump) would push every existing vault below the floor -> KdfPolicyError on open = permanent lockout. Fixed by adding ARGON2_MEMORY_FLOOR_KIB (= the pin today, held at the minimum ever shipped); validate_params now checks the floor, so the pin can rise independently. Zero behaviour change today; all floor tests stay green.
  **Layman:** Made it safe to strengthen password protection later without locking anyone out of their existing data.
  Kind: review-fix.
  Source: indie-review-2026-07-23.

- ✅ [FIBR-0167] **Auto-update enforces https on redirects, not just the initial URL (FIBR-0054 INV-10).**
  indie-review (update/signature lane), LOW (defence-in-depth). _require_https guarded only the first URL; urllib's default opener follows 3xx redirects to http/ftp transparently, so an https URL redirecting to http:// was followed. Integrity was still guaranteed by the Ed25519 check on the asset, but the unsigned API JSON could be read over plaintext. Fixed with _HttpsOnlyRedirectHandler on a process-wide opener (install_opener), re-asserting _require_https on every hop; urlopen keeps its call shape so the test seam survives. Regression: test_INV10_redirect_to_non_https_is_refused.
  **Layman:** The update check can no longer be silently downgraded to an insecure connection via a redirect.
  Kind: review-fix.
  Source: indie-review-2026-07-23.

- ✅ [FIBR-0168] **Recurring & Transfers tabs render amounts with the currency symbol + locale grouping via _format_amount.**
  indie-review (UI lane), LOW. Both tabs rendered raw str(Decimal) instead of the shared _format_amount, so a large figure showed with no currency glyph and no thousands grouping — easy to misread by an order of magnitude in a finance app. Values/signs were correct. Both amounts are positive magnitudes, so no negative-style/colour prefs plumbing was needed: the base-currency symbol is read fresh (TransactionService.base_currency()) like the Transactions/Home tabs and passed to _format_amount; the SortableItem numeric sort key is unchanged.
  **Layman:** Money on the Recurring and Transfers tabs now shows as 'R 1,234.50' like the rest of the app, instead of a bare '1234.5'.
  Kind: review-fix.
  Source: indie-review-2026-07-23.

- 📋 [FIBR-0169] **Auto-update anti-rollback: bind the offered version into the signed artifact to prevent a signed-but-older downgrade.**
  indie-review (update/signature lane), LOW — deferred (design + release-pipeline change, needs a spec). The Ed25519 signature binds only the artifact BYTES, not the version; the offered version comes verbatim from the untrusted GitHub tag_name. A GitHub-release-WRITE attacker (no signing key — the residual security-model §2 already acknowledges) could re-publish an old, still-validly-signed AppImage under a higher tag; check_for_update sees it as newer, download_and_verify passes (authentic bytes), and the user is silently downgraded to a version with known bugs. Fix options: sign a manifest naming version+hash, or refuse to install a payload whose embedded __version__ <= current. At minimum document the downgrade case alongside the existing 'no rollback' accepted-risk in FIBR-0054 Out-of-scope.
  **Layman:** Stop a would-be attacker (who can write GitHub releases but holds no signing key) from tricking the app into installing an older, still-signed version.
  Kind: security.
  Source: indie-review-2026-07-23.

- ✅ [FIBR-0170] **Install the verified update from the in-memory buffer to close the verify-in-memory / install-from-disk TOCTOU.**
  indie-review (update/signature lane), INFO — out of the current threat model (needs a same-user/root attacker able to rewrite the 0600 mkstemp temp in the target dir, explicitly out of scope per security-model §4), so deferred. download_and_verify verifies data read into memory (asset_tmp.read_bytes()) but the installer later os.replace()s the on-disk temp — the file could differ from the verified bytes in the window. Hardening: write the verified `data` buffer to a fresh temp and install THAT, rather than trusting the re-read file. Low priority; noted for completeness.
  **Layman:** Extra hardening so the exact bytes we checked are the exact bytes installed.
  Kind: security.
  Source: indie-review-2026-07-23.
  Resolved (2026-07-28): download_and_verify now writes the verified in-memory buffer to a fresh mkstemp (0600, O_EXCL) and deletes the download temp it re-read those bytes from, so the file the installer swaps in is the file the signature check passed. Shrinks the swap window from the whole transfer to the moment before os.replace(). Test: test_FIBR0170_installs_the_verified_buffer_not_the_re_read_download.

- 📋 [FIBR-0180] **Decide deliberately whether to move the CI/build base image off Debian 12 (bookworm, now oldstable).**
  ci.yml, ci-docker.sh and build-smoke.sh all pin python:3.12-slim-bookworm. Debian 13 (trixie) has been stable since Aug 2025, so bookworm is oldstable and a python:3.12-slim-trixie image exists. This is NOT a routine bump: the build image's glibc (~2.36) is the EFFECTIVE floor of every frozen artifact (libpython links it - see the pyproject.toml dependencies comment), so moving to trixie raises the minimum glibc an AppImage/.exe user needs. The debt sweep added that rationale as a comment on ci.yml's container line rather than bumping. Decide: (a) hold on bookworm until the AppImage's target-distro floor justifies moving, or (b) bump all three call-sites together and re-run build-smoke to confirm the clean-room launch still passes on the oldest distro we claim to support. Either way, record the decision so the next sweep does not re-raise it.
  **Layman:** Our build machine runs an older Debian. Moving to the newer one is a trade-off: it may stop finbreak running on older Linux systems, so it needs a decision rather than a routine update.
  Kind: chore.
  Source: debt-sweep-2026-07-26.

- ✅ [FIBR-0181] **Consolidate the five hand-rolled Decimal to minor-units conversions behind one to_minor() helper.**
  Five independent implementations of the same Decimal->minor-units conversion: services/alerts.py:167 (_to_minor), services/forecast.py:215, importers/standard_bank.py:445 (_minor), importers/ofx_importer.py:157 (inline), services/transactions.py:73 (a scaleb variant). The duplication is already self-admitted in two places: alerts.py's docstring says it is 'the exact idiom ForecastService._to_input uses', and ofx_importer.py's comment points at a _minor that lives in a different module it does not import. The REVERSE direction already has a single home (transactions.to_display_decimal) - add the forward to_minor(amount, exponent) beside it and route all five through it. Well past Rule of Three. Deliberately NOT done in the debt sweep: this is money code in a correctness-critical app, so it wants its own reproduce-first cycle with a test pinning rounding behaviour (esp. the scaleb variant, which may not round identically) rather than a drive-by edit. Related watch item: services/forecast.py CASH_TYPES and services/reconciliation.py _RECONCILABLE_TYPES are the identical frozenset kept in manual sync by comment - only 2 sites, so below Rule of Three; extract on the third caller.
  **Layman:** The code that turns a money amount into whole cents is written out five separate times. One shared version would make a rounding mistake impossible to introduce in just one of them.
  Kind: refactor.
  Source: debt-sweep-2026-07-26.
  Resolved (2026-07-28): `to_minor(amount, exponent)` now lives beside
  `to_display_decimal` in services/transactions.py as its exact inverse
  (`int(amount.scaleb(exponent).to_integral_value())`), and all five sites
  route through it — alerts._to_minor and standard_bank._minor deleted,
  forecast._to_input and ofx_importer's inline scaling replaced,
  parse_transaction now calls it. TDD: 16 new cases in
  tests/features/vault/test_vault.py pin exact scaling at exponent 0/2/3,
  the to_display_decimal round-trip, half-even rounding below the minor
  unit, and — the risk the bullet flagged — that the two replaced
  spellings (`* 10**exp` and `.scaleb(exp)`) agree, so no stored value
  changed. Doc drift swept: FIBR-0171 §D7 + the OFX bullet, FIBR-0172 §D7
  + INV-15, and the alerts.py docstring now name the shared helper.
  NOT done (deliberate, unchanged): forecast.CASH_TYPES /
  reconciliation._RECONCILABLE_TYPES remain 2 duplicate frozensets —
  still below Rule of Three; extract on the third caller.
  Verified: ruff + mypy clean, 1385 passed, 2 skipped (was 1369).

- ✅ [FIBR-0182] **Four dead-code sites surfaced by the debt sweep (not removed - each needs an owner decision).**
  Surfaced rather than deleted (global rule 11 - do not remove pre-existing dead code unasked). Each verified with a repo-wide grep over src/tests/scripts/docs: (1) importers/standard_bank.py:42 re-exports PasswordError from pdf_importer behind a '# noqa: F401 (re-export)'; nothing imports it from standard_bank (the wizard takes it from pdf_importer), so the noqa keeps a dead name alive - drop it, or declare __all__ if the re-export is intended public API. (2) ui/transfers.py:221 candidate_count() sits under a 'test / shell accessors' banner with zero callers anywhere. (3) ui/statements.py:265 selected_period_id() has zero callers; its only mention is prose at docs/specs/FIBR-0059.md:356 - so either the test that spec implies is missing, or the accessor is. (4) importers/standard_bank.py:919 _span()'s `family` parameter is never read (the body branches only on `period is not None`); dropping it touches two call-sites (:893) and two tests. NOTE: main_window.py:237/239 _update_check_worker / _download_worker are assigned-never-read but are defensible QThread lifetime anchors - left alone.
  **Layman:** Four small pieces of code that nothing uses. Removing them is tidy-up, but each one needs a quick check that it was not left there on purpose.
  Kind: chore.
  Source: debt-sweep-2026-07-26.
  Resolved (2026-07-28): all four removed after re-verifying each has zero
  callers. (1) the PasswordError re-export + its noqa F401 dropped from
  standard_bank.py (the wizard imports it from pdf_importer). (2)
  ui/transfers.py candidate_count() removed. (3) ui/statements.py
  selected_period_id() removed, and the FIBR-0059 §"code reused" survey
  line updated so no doc points at it. (4) _span()'s unread `family`
  parameter dropped (call-site :893 + two asserts in
  test_standard_bank.py), docstring reworded to state the actual rule (a
  printed period wins; A/C are simply the families that supply one).
  Verified: ruff + mypy clean, 1369 passed, 2 skipped.

- ✅ [FIBR-0183] **bandit prints 31 'Test in comment' warnings because prose follows the # nosec test id.**
  bandit parses everything after '# nosec' as a comma/space-separated list of test IDs, so a marker written '# nosec B603 - fixed /bin/sh waiter, our own argv' makes it try to resolve 'fixed', 'waiter', 'our', 'own', 'argv' as test names and emit 'WARNING Test in comment: X is not a test name or id, ignoring' for each. 31 such warnings across the tree. Verified pre-existing and NOT caused by the debt sweep's noqa cleanup (identical count before and after, and bandit still exits 0 with the suppressions honoured). Low severity, but it is 31 lines of noise in every gate run, which is exactly the condition under which a real bandit warning gets skimmed past. Fix: put the rationale on its own line above, or after a separator bandit stops parsing at, keeping the marker itself bare ('# nosec B603').
  **Layman:** Our security scanner prints 31 confusing warnings every run, caused purely by how a comment is written. Harmless now, but the noise could hide a real warning.
  Kind: chore.
  Source: debt-sweep-2026-07-26.
  Resolved (2026-07-28): moved every rationale off the `# nosec` line (own
  comment line above, marker left bare) in update_installer.py x3,
  backup.py and tests/features/backup/test_backup.py. Verified: bandit
  "Test in comment" warnings 31 -> 0, `bandit -c pyproject.toml -r src -q`
  still exits 0 with the 7 suppressions honoured; ruff + 1369 passed,
  2 skipped.

- ✅ [FIBR-0221] **cryptography 49.0.0 carries CVE-2026-69247; the pinned version failed the pip-audit gate.**
  Surfaced by ./scripts/ci-local.sh's pip-audit stage while closing
  FIBR-0190 — unrelated to that work, but a red gate and a real advisory
  on a dep we pin ourselves. cryptography is an EXPLICIT runtime dep, not
  just transitive: services/update.py and services/update_key.py import it
  directly for Ed25519 verification of downloaded updates (FIBR-0054 D1),
  so this is our signature-checking library.

  Resolved (2026-08-04): pinned cryptography==50.0.0 (the advisory's fix
  version). No caller change needed — the Ed25519PublicKey /
  InvalidSignature API the two call sites use is unchanged across the
  major. Full gate re-run green: 1610 passed / 2 skipped, pip-audit clean.
  **Layman:** A security library finbreak uses had a published flaw; it is now on the fixed version.
  Kind: security.
  Lanes: dependencies, security.
  Source: in-session-2026-08-04.

- 📋 [FIBR-0239] **design.md's service list and architecture diagram are two services behind.**
  Noticed while adding MonthSummaryService to `docs/design.md`'s
  "Service layer — one service per concern" list (FIBR-0231 § 12). The
  list, and the mermaid `subgraph Svc` diagram above it, both name
  Auth / Import / Categorization / TransferDetection / Reporting /
  PdfExport / Update / Crypto — but NOT `RecurringService` (FIBR-0142)
  or `AlertService` (FIBR-0172), both of which shipped and both of
  which HomeView constructs today. So the list was already incomplete
  before this item touched it.

  Left as-is rather than fixed in passing: repairing pre-existing doc
  debt inside a feature commit is out of that commit's lane, and the
  mermaid diagram needs the same two nodes plus their edges, which is a
  second decision (the diagram is deliberately not exhaustive — it omits
  the repositories layer's members too, so "add every service" may be
  the wrong answer for the picture even where it is right for the list).

  Fix: add RecurringService and AlertService to the prose list; decide
  separately whether the diagram tracks the list or stays a sketch, and
  say which in the diagram's caption so the next session does not have
  to re-derive the answer.
  **Layman:** An internal architecture document lists most of the app's parts but has quietly fallen behind by two.
  Kind: doc-fix.
  Source: in-session-2026-08-06 (surfaced while landing FIBR-0231).

- 📋 [FIBR-0251] **ci-docker.sh cannot run during a GitHub outage — ci-setup.sh downloads its pinned binaries from GitHub releases.**
  Surfaced 2026-08-06 while proving the tree green during a GitHub
  Actions major outage. `scripts/ci-setup.sh` fetches the four pinned
  non-pip binaries (gitleaks, shellcheck, actionlint, zizmor) from
  GitHub release URLs, so `scripts/ci-docker.sh` inherits a hard
  dependency on GitHub being up. Observed: gitleaks 8.30.1 installed,
  then shellcheck's download returned `curl: (22) ... error: 504` and
  the run died in `tar`.

  Consequence: during a GitHub incident BOTH the CI run and the
  containerised local reproduction are unavailable at once, leaving only
  `scripts/ci-local.sh` on a desktop that already has the binaries on
  PATH. That is the pre-push hook's path, so the gate itself still
  works — this is a loss of the *reproduction* tool, not of the gate.

  Options, cheapest first: (a) cache the four binaries in a local
  directory and have ci-setup.sh reuse a present, version-matching copy
  before reaching for the network; (b) let ci-docker.sh mount the host's
  already-downloaded binaries; (c) accept it and document the fallback.
  Note (a) must still verify the pinned version, or the cache becomes a
  way to silently run an older rule set — the exact drift the pins in
  CLAUDE.md exist to prevent.

  Not urgent: the pre-push gate is unaffected.
  **Layman:** The "reproduce CI exactly on my own machine" check stops working when GitHub itself is down, which is exactly when you most want it.
  Kind: chore.
  Source: in-session-2026-08-06 (GitHub Actions major outage, 15:22 UTC).
  Context for a later session reading red CI on main: the two failed
  runs on `983559e` (2026-08-06, 15:53 and 16:23 UTC) were THIS outage,
  not a code defect. Both died before any gate stage ran — the first
  never acquired a runner, the second failed to download
  `actions/checkout` ("Service Unavailable"). The tree was green
  throughout: `./scripts/ci-local.sh` passed all 11 stages, 1840 passed /
  3 skipped, mypy clean over 178 files. Do not re-investigate those two
  runs; re-run them once Actions is healthy.

- ✅ [FIBR-0257] **The CVE-2026-69247 fix is committed but unreleased — every downloadable build still ships cryptography 49.0.0.**
  FIBR-0221 pinned `cryptography==50.0.0` on 2026-08-04 and is marked ✅ —
  but the newest release, v0.1.19, was tagged 2026-08-02. The fix has
  never shipped. Verified per tag: v0.1.17, v0.1.18 and v0.1.19 all pin
  `cryptography==49.0.0`.

  This is not a transitive dep. `services/update.py` and
  `services/update_key.py` import cryptography directly for the Ed25519
  verification of downloaded updates (FIBR-0054 D1) — it is finbreak's
  signature-checking library, and the flawed version is the one in every
  build a user can currently download.

  Found by building the Flathub SUBMISSION manifest, which pins finbreak
  at v0.1.19: the offline build fails with `Could not find a version that
  satisfies the requirement cryptography==49.0.0`, because the
  regenerated closure now offers 50.0.0. The failure is the tag's
  pyproject disagreeing with the closure — a real signal, not a
  packaging wart.

  Consequence for FIBR-0159: submitting the manifest as it stands would
  either fail Flathub's build or, if the closure were reverted to match,
  publish the vulnerable library to a much wider audience than the
  current download page.

  Fix: cut a release containing c98908b, then re-pin the Flatpak manifest
  to that tag. `/release` owns the version bump and tagging; this bullet
  just records that a release is now the blocking step for FIBR-0159 and
  that the security fix is the reason, not a feature.
  **Layman:** The security fix we made is sitting on our side and has never gone out to users; the version people can download today still has the flaw.
  Kind: security.
  Lanes: release, security.
  Source: in-session-2026-08-07 (FIBR-0159 submission-manifest build).
  Resolved (2026-08-12) — the release this bullet was waiting for is v0.1.20. `git show v0.1.20:pyproject.toml` pins `cryptography==50.0.0`, so the CVE-2026-69247 fix has shipped and the manifest is re-pinned to v0.1.20 / 6c9cf8c. The exact failure recorded here — an offline build that cannot satisfy `cryptography==49.0.0` — no longer reproduces: a LOCAL=0 build of the submission manifest installs cryptography-50.0.0 and finbreak-0.1.20 and ends FINBREAK_SELFTEST_OK. FIBR-0159 is no longer blocked on a release.

- ✅ [FIBR-0261] **`--self-test` aborts on a headless machine instead of running.**
  `python -m finbreak --self-test` on a box with no display dies before
  any check runs: "no Qt platform plugin could be initialized. Aborted
  (core dumped)". Every caller sets `QT_QPA_PLATFORM=offscreen` for it —
  `tests/conftest.py:17`, `build-smoke.sh`, `finbreak.spec`,
  `debian/rules` — so no gate can ever catch this, yet FIBR-0003 INV-1
  calls `--self-test` a PERMANENT diagnostic for a broken install on a
  user's machine, and `_check_qt`'s own docstring says it constructs the
  QApplication "offscreen". The one caller that never sets it is the
  human following CLAUDE.md, and a headless server over SSH is precisely
  where the diagnostic is needed. Fix in `__main__` (not the doc): when
  `--self-test` is passed on a non-Windows/macOS host with no `DISPLAY`
  and no `WAYLAND_DISPLAY`, default `QT_QPA_PLATFORM` to `offscreen`; an
  explicit value still wins. Regression-locked by a test that runs the
  CLI with those three variables stripped from the environment.
  **Layman:** The built-in "is my install OK?" check crashed on a machine with no screen — exactly the machine you would run it on.
  Kind: fix.
  Source: runbook-execution-2026-08-11.
  Resolved 2026-08-11 (220aefc): `__main__` defaults `QT_QPA_PLATFORM` to
  `offscreen` when `--self-test` is passed on a non-Windows/macOS host
  with no `DISPLAY` and no `WAYLAND_DISPLAY`; an explicit value still
  wins, so conftest, build-smoke.sh and the OBS recipes are unchanged.
  The regression test also repoints `XDG_RUNTIME_DIR` at an empty
  directory — dropping the two display variables alone is NOT enough on
  a Wayland desktop, where libwayland still finds the `wayland-0`
  socket and the test passes vacuously. Confirmed red (exit -6, SIGABRT)
  before the fix; the documented bare `python -m finbreak --self-test`
  now prints FINBREAK_SELFTEST_OK in a display-less container.

- 📋 [FIBR-0262] **`pytest tests/features/bundling/` alone aborts the interpreter.**
  Pre-existing (reproduced on baf48b8, before the FIBR-0261 fix), found
  while running that directory on its own. The three `..._selftest_fail_...`
  tests monkeypatch `_check_qt` to a no-op, so no `QApplication` is
  constructed, and the unpatched `_check_icons` then renders a `QPixmap`
  — which aborts the process (SIGABRT) when no QApplication exists. In a
  full-suite run an earlier test has already built one, so the whole gate
  stays green and only the directory-alone / `-k` invocation dies; both
  are invocations CLAUDE.md § "Run tests / a single test" documents.
  Fix: patch `_check_icons` alongside `_check_qt` in those tests, or give
  them the shared `qapp` fixture, so they stop depending on global state
  another test happens to leave behind.
  **Layman:** One folder of tests crashes if you run just that folder; run the whole suite and it passes, which is why nobody noticed.
  Kind: test.
  Source: in-session-2026-08-11.

- ✅ [FIBR-0263] **A batch-import UI test raced the report and turned CI red at random.**
  `test_INV14_done_waits_for_the_report` waited only for every file's
  outcome to reach `committed`, then asserted the report's Close button
  was visible. `_run_next` sets that last outcome in one event-loop turn
  and only reaches `finish()` — which shows Close — in the NEXT turn,
  armed by `singleShot(0)`. So the wait's condition goes true one whole
  turn before Close exists, and whether `waitUntil` returns there or
  after the queued turn is scheduler luck.

  Measured, not inferred: interposing on `run_step` shows that at the
  instant the last file commits the state is `phase='run',
  _finished=False` — Close still hidden — while the old predicate is
  already true.

  It won on every developer desktop and lost once on a loaded CI runner:
  run 31622538238 red, the identical test green on the very next push
  (1 failure in the last 40 CI runs). Fixed by waiting for
  `_batch_phase == "report"` as well, which `_run_next` sets in the same
  slot invocation as `finish()` with no event loop between them. This
  also strengthens the neighbouring `emissions == []` assertion, which
  could previously be checked before the run had finished at all.
  Product behaviour is correct and unchanged — the defect was purely the
  test's synchronisation.
  **Layman:** A test was checking for the "Close" button a split second before the app had drawn it, so the build failed at random rather than because anything was broken.
  Kind: test.
  Source: in-session-2026-08-12 (CI failure triage, run 31622538238).

- ✅ [FIBR-0306] **Harness INV-5 sandbox inherits the machine-wide core.hooksPath and fails.**
  Both `tests/features/harness/test_gate_stages.py::test_INV5_*`
  tests fail on this machine at clean HEAD (f704605) -- confirmed in a
  throwaway worktree, so nothing uncommitted causes it. They pass in
  CI, which is why nothing caught it.

  Cause, diagnosed 2026-08-21. A machine-wide pre-push hook was
  installed that morning at `~/.claude/githooks/pre-push` and wired up
  with `git config --global core.hooksPath ~/.claude/githooks`.
  `_hook_sandbox` builds its miniature repo with a plain `git init`,
  which inherits that global value -- the sandbox sets no
  `core.hooksPath` of its own. So the sandbox's own SETUP push
  (`git push -q origin main`, before the test has done anything) fires
  the machine-wide hook, which auto-discovers a gate command, finds the
  sandbox's stub `scripts/ci-local.sh`, and runs it. That stub's whole
  job is to touch the `gate-ran` sentinel. So the sentinel exists
  before the assertions start, and
  `test_INV5_the_sandbox_is_not_vacuous` fails on its very first line,
  `assert not sentinel.exists()`.

  This is a test-ISOLATION defect, not a defect in
  `.githooks/pre-push`. The tag-skip behaviour FIBR-0290 shipped is
  fine; the harness around it is not hermetic. The fix is to neutralise
  inherited git configuration in the sandbox -- run the subprocesses
  with `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_SYSTEM=/dev/null`,
  or set `core.hooksPath` explicitly in the sandbox right after
  `git init`. The first is broader and catches the next global setting
  someone adds.

  Worth noting for its own sake: the machine-wide hook auto-discovers
  `scripts/ci-local.sh` in ANY repository it is enabled for. finbreak
  sets its own local `core.hooksPath=.githooks`, so this project is
  unaffected in normal use -- git reads the local value first.

  Found while running the full gate before committing FIBR-0019's
  write-test suite; unrelated to that work.
  Resolved (2026-08-21), commit 95056bb. Took the broader of the two
  fixes this bullet named: every sandbox subprocess now runs with
  GIT_CONFIG_GLOBAL=/dev/null and GIT_CONFIG_SYSTEM=/dev/null, rather
  than pinning core.hooksPath alone, so the next global setting someone
  adds cannot leak the same way.

  Confirmed rather than assumed: `git config --global core.hooksPath`
  still returns ~/.claude/githooks on this machine, and with it in place
  the harness suite went from 2 failed to 12 passed. The full gate is
  now 1967 passed, 2 skipped, 0 failed -- the first fully green gate on
  this desktop since the machine-wide hook was installed. The sandbox is
  not inert either: the sibling
  test_INV5_tag_push_of_an_unpushed_commit_runs_the_gate still sees the
  stub create its sentinel, so the hermetic env did not simply stop the
  hook from ever running.

  Picked up because it blocked the FIBR-0019 push: the pre-push hook
  runs the gate, so a pre-existing red on this desktop meant a green
  code change could not be pushed without --no-verify, which CLAUDE.md
  sanctions only for a doc-only push or a pip-audit network flake.
  Fixing it was the cheaper of the two, and it is a one-file change in
  its own commit.
  **Layman:** Two of our own tests now fail on this desktop because a new machine-wide git setting leaks into the miniature test repository they build.
  Kind: test.
  Source: in-session-2026-08-21.
  Lanes: tests, ci.

- 📋 [FIBR-0309] **The sidecar write and its parameter validation have three pre-existing gaps.**
  Surfaced rather than fixed in passing (coding.md 1.7). All three predate
  FIBR-0019 -- confirmed against f704605: the atomic-write code came verbatim
  from vault.py:292-302 when it moved to crypto.write_sidecar_json, and
  validate_params' checks are untouched by that commit. FIBR-0019 widened the
  blast radius of two of them, which is why they are filed now.

  1. write_sidecar_json opens the temp file O_CREAT without O_EXCL, so the 0o600
     mode argument is not applied when the file already exists. O_NOFOLLOW closes
     the symlink case the comment names and nothing closes the ordinary-file case:
     a pre-created vault.kdf.json.tmp keeps its own owner and mode and is renamed
     over the sidecar. Precondition is write access to the data directory, so it
     is a small hole in a defence the module deliberately mounts. Fix with O_EXCL
     plus an unlink of any stale .tmp, or fchmod after opening.

  2. No directory fsync after os.replace, in either write_sidecar_json or the
     migration's S4/S5 renames -- so the docstring's word 'atomically' covers the
     contents and not the rename. FIBR-0019 makes this bite harder: a user who
     presses Keep, is told the code is live and files the paper copy can lose the
     slot to a power cut, and INV-5 means the app can never show that code again.
     ext4 and btrfs journal directory ops in order, so this is filesystem-
     dependent rather than absent everywhere.

  3. validate_params bounds neither time_cost nor parallelism nor the UPPER end of
     memory_kib. A hand-edited time_cost of 0 surfaces as an argon2 exception
     rather than the KdfPolicyError ui/unlock.py renders, against
     load_and_validate_params' own stated posture that every malformed input is
     normalised to one failure type. memory_kib 2147483647 passes the directional
     floor and is attempted before any authentication can reject it, because the
     AAD binds the value only after the derivation it sizes.
  **Layman:** Three long-standing weaknesses in how the vault's security-settings file is written and checked — none introduced by the recovery key, but it made two of them matter more.
  Kind: security.
  Source: close-phase-2026-08-21 (review-code lane 1 + lane 2, FIBR-0019 close).
  Lanes: crypto, security.

- 📋 [FIBR-0311] **services/pdf_export.py's translated strings extract to an empty catalog.**
  The module routes 30 user-facing strings through a one-argument `_tr(text)`
  wrapper, and pyside6-lupdate extracts nothing through a wrapper -- measured
  2026-08-25 on a probe file. Its own docstring claims the opposite: "keeps every
  user-facing string translatable".

  Not fixed with the rest of FIBR-0310 R3 because the mechanical inline makes the
  file worse: a third of the sites sit inside f-strings, where
  `QCoreApplication.translate("PdfExport", "Income")` blows the 88-column limit
  and the HTML becomes unreadable. The fix is to hoist the labels to locals
  before each f-string, which is a readability refactor of the PDF renderer
  rather than the plumbing change R3 was.

  tests/features/i18n/ excludes this file BY NAME and carries a leg that goes RED
  once it conforms, so the exclusion cannot outlive the work. Closing this item
  means deleting `_KNOWN_OFFENDER`, its use, and that leg.
  **Layman:** The PDF report's labels look translated in the code but would come out in English in every language.
  Kind: refactor.
  Source: in-session-2026-08-25 (FIBR-0310 R3).

- 📋 [FIBR-0312] **tests/features/recovery_key/spec.md still says the suite is expected to fail.**
  The spec carries a "## Status -- this suite is expected to FAIL" section
  stating that FIBR-0019 is not implemented and that keywrap.py,
  services/recovery_code.py, services/vault_migration.py and the two AuthService
  methods "exist only as stubs raising NotImplementedError". All of them are
  implemented and the suite is green.

  The section's advice is still worth keeping in some form -- "do not adjust an
  assertion to make one pass" -- but its premise is false, and a reader checking
  whether the feature exists gets the wrong answer from the document written to
  tell them.

  Also stale in the same file: "Only Add is exercised, by INV-12; the other two
  carry no invariant in section 5 and adding tests for them would be scope
  creep". FP02 and FP03 both added Replace / Remove tests.
  **Layman:** A test document still says the recovery-key feature is not built yet. It is.
  Kind: doc-fix.
  Source: in-session-2026-08-25 (noticed during FIBR-0310).

- 🚧 [FIBR-0318] **Close the 2026-08-31 whole-tree audit: check-code + a 15-lane review-code sweep.**
  check-code --tree came back clean apart from two trivia. review-code ran 15
  lanes over src/, scripts/ and the workflows, partitioned by cohesion after
  indie_review_partition returned src/ and tests/ as single too_coarse lanes.

  Findings: 2 CRITICAL, 26 HIGH, 54 MEDIUM, ~110 LOW/INFO. Every finding was
  verified against current source before action; the confirmed false positives
  are in .ants_review_falsepos.jsonl.

  The strongest cross-lane signal was the fixed-one-copy shape: a repair applied
  to one of two siblings and not the other. Five instances, found by five
  independent lanes.
  Progress (2026-08-31): both CRITICALs and the bulk of the HIGH set are fixed,
  tested and pushed — the release-artefact replay, the signed completeness gate,
  the OFX null-date crash, the Decimal Overflow escape, the forecast month-end
  anchor, the two chart defects, the four app-shell lifecycle defects, the reset
  footprint, the recovery-display auto-lock, the clipboard Never case, the
  Windows self-test silence, the zombie protocol method, the supply-chain
  verification, and the batch password ladder. Gate green throughout.

  Four HIGH are deliberately NOT fixed and carry their own items: FIBR-0319
  (mapping ladder), FIBR-0320 (Linux relaunch PID — needs runtime evidence),
  FIBR-0321 (Remember-password write — a design decision, an attempted fix was
  reverted), FIBR-0322 (parallel row lists, calibrated to MEDIUM). The MEDIUM and
  LOW tails are FIBR-0327 and FIBR-0328.

  Two spec consequences carry items rather than being amended silently: FIBR-0323
  (Family B's exemption from INV-11) and FIBR-0324 (the INV-4 amendment owes its
  gate).
  **Layman:** A full sweep of the code found a batch of real bugs; this tracks fixing them.
  Kind: review-fix.
  Source: check-code --tree + review-code 2026-08-31.

- ✅ [FIBR-0319] **The batch mapping ladder never fires for files 2..N, the twin of the password defect.**
  Same ordering as the password half fixed under FIBR-0318: SCAN runs over the
  whole list before the first question, so every file is already needs_mapping
  when a profile is saved, and `answer` re-scans only the record it was handed.
  `match_profile` is consulted once per file at scan time and never again.

  Not fixed with its twin because the fix depends on WHEN the wizard saves the
  profile relative to `answer` -- `_on_map_next` saves only if the name field is
  filled. That ordering needs checking rather than assuming. The password half's
  `_retry_blocked_on_password` is the shape to copy once it is settled.
  Resolved (2026-09-03): fixed and pushed (92ed2e8); gate green at 2170
  passed / 2 skipped.

  The ordering this bullet said to check rather than assume: _on_map_next
  saves the profile BEFORE calling answer, so match_profile does resolve
  for the other same-header files by the time the retry runs.
  _retry_blocked_on_mapping mirrors its password sibling exactly.

  The answered mapping is NOT applied to the others -- each re-scanned
  record consults match_profile with its OWN header, so a different layout
  returns to needs_mapping and is asked about as before, and a mapping
  answered with no profile NAME saved nothing and changes nothing.

  mutation_probe earned two extra legs, and the second is not about this
  change. Dropping the "still blocked on a mapping" guard survived, because
  the headline leg uses three files in the SAME state -- and the hazard is
  real: _settle_parse re-runs match_account, which knows nothing of an
  account the user chose on the review screen, so a re-scan drops that
  record back to needs_account. The identical guard in the PASSWORD twin
  (FIBR-0318) then turned out to be unmeasured for the same reason. Both
  have a leg now.

  Five mutants, four killed. The fifth -- dropping `other is answered` --
  survives and is NOT a defect: after the re-scan the answered record can
  no longer be needs_mapping, so the outcome test already excludes it. Kept
  for symmetry with the password sibling.

  Left deliberately: a batch answered with the profile-name field BLANK
  still asks per file, because the saved profile is the spec's own
  mechanism for remembering an answer (§ 4.3). Filed separately rather than
  widened into here.
  **Layman:** Thirty spreadsheets sharing one unknown layout still ask you to describe it thirty times.
  Kind: fix.
  Source: review-code 2026-08-31 lane=import-orchestration.

- 📋 [FIBR-0320] **The Linux relaunch waits on the PyInstaller child, where Windows was redesigned to wait on the image.**
  FIBR-0131 D3 states that onefile is a two-process tree and that the bootloader
  parent holds the write-lock and does the _MEI cleanup, then concludes waiting on
  a single PID is fragile. Windows was redesigned to poll the exe image path; the
  Linux waiter still polls os.getpid().

  Deliberately NOT fixed blind. The finding rests on os.getpid() being the child
  rather than the bootloader, which needs confirming inside a live AppImage
  (ps -o pid,ppid,comm); if it is the bootloader the finding collapses to INFO.
  And per the known trap, a relaunch change only proves out on the update AFTER
  it ships, so guessing here is the worst option available.
  **Layman:** After a self-update the app might fail to reopen -- and it cannot be tested until the next update ships.
  Kind: investigate.
  Source: review-code 2026-08-31 lane=update-installer.

- 📋 [FIBR-0321] **A remembered PDF password is written to the provisional account before the destination is known.**
  FIBR-0249 added a prior/restore pair, but the restore runs only after a
  SUCCESSFUL commit -- so cancel, an idle auto-lock, a raising commit, or picking
  another file (which drops the restore data) each leave the wrong account
  holding the password with its own gone.

  A deferred write was attempted and REVERTED: it makes Remember do nothing when
  the user then cancels, which INV-7f pins deliberately and three contract tests
  encode. The two properties conflict, so this needs a decision -- either accept
  that Remember requires a completed import, or resolve the destination before
  the write. BatchImportService._settle_password is the sibling design.
  **Layman:** Ticking Remember, then cancelling, can leave the password filed against the wrong account and lose that account's own.
  Kind: fix.
  Source: review-code 2026-08-31 lane=ui-import-wizard.

- ✅ [FIBR-0322] **The lock-time wipe clears table models but not the parallel row lists holding account numbers.**
  _clear_decrypted_rows clears every QTableWidget, and its docstring says this
  makes the wipe happen at lock time rather than at destruction time. The
  _table_state tagging design obliges each tab to keep a parallel Python list;
  AccountsWidget's holds Account objects including the raw account number, and
  those survive until deleteLater actually runs.

  Calibrated HIGH -> MEDIUM: security-model section 4 puts a memory-reading
  attacker out of scope, so this is FIBR-0052 INV-3's absolute wording being
  overstated as much as the code being short. Fix is a clear_rows() per tab,
  called alongside the model clear.
  Resolved (2026-09-03): fixed and pushed (16d9fa2); gate green at 2167
  passed / 2 skipped.

  Each tab keeping a parallel row list now offers clear_rows(), asked for
  by duck type from _clear_decrypted_rows -- so main_window imports no tab,
  and a tab added later is covered by writing the method rather than by
  editing a list in the shell.

  One thing this bullet did not name, found while fixing it:
  TransactionsView derives its visible _rows from an unfiltered _master, so
  _master holds every decrypted transaction whether or not a filter is
  showing it. Clearing the visible half alone would have left the larger
  one behind. Both are cleared and the test sweeps both attributes.

  Four mutants, all killed. One survived first -- nothing measured that the
  sweep clears the ROOT it is handed rather than only that root's children.
  Today _live is always the workspace container so it changes nothing, but
  the breadth is deliberate (_live was a single HomeView before FIBR-0052),
  so it has its own leg rather than going unmeasured.
  **Layman:** After the vault locks, some decrypted details stay in memory longer than intended.
  Kind: security.
  Source: review-code 2026-08-31 lane=ui-views-admin.

- 📋 [FIBR-0323] **FIBR-0050 INV-11 states a signed reconciliation Family B cannot satisfy.**
  INV-11 gives the completeness gate as opening + sum(signed) == printed closing
  for the balance families. FIBR-0318 made the code match that -- except Family B,
  whose running-balance column prints unsigned magnitudes while its CLOSING
  BALANCE row prints a sign, so the two endpoints cannot be compared signed. That
  is the same asymmetry that makes _verify_row pass check_sign=False for B alone.

  The exemption is now explicit in code and absent from the spec. Surfaced rather
  than amended: it is a contract change and owes a review-contract gate.
  **Layman:** A spec rule is right for most statement types and cannot be met by one of them.
  Kind: doc-fix.
  Source: review-code 2026-08-31 lane=importers.

- ✅ [FIBR-0324] **FIBR-0171 INV-4 was amended under FIBR-0318 and owes its review-contract gate.**
  INV-4 prescribed the chained stepping that produced the month-end forecast
  defect, contradicting D6 and the implementation's own docstring, which both
  argue for anchored stepping. It was amended to state the anchored form.

  That changes what a conformer builds, so rule 14's gate applies:
  review-contract docs/specs/FIBR-0171.md. The amendment says so in place rather
  than relying on this bullet.
  Resolved (2026-09-02): gate run, three loops, three cold lanes each.
  Eighteen verified findings, all fixed. Loop 1 found that D6 still
  prescribed the chained form the INV-4 amendment forbids, so the spec's
  two normative sections gave an implementer two different stepping
  algorithms — the amendment note itself claimed D6 agreed with it. Loop
  2 found FIBR-0179's cash-only narrowing had been applied to D1 and
  never carried to D2, D10, INV-6, INV-13 or D9. Loop 3 hit the cap, and
  it was a VIOLENT cap: three of its five findings landed on text loop 2
  wrote. The document routes to implementation rather than a fourth cold
  read. Collateral corrected in tests/features/forecast/spec.md and in
  update_closing_balance's docstring, which contradicted its own body
  about logging decrypted balances.
  **Layman:** A corrected spec rule got its independent read; it found eighteen more problems, all fixed.
  Kind: doc.
  Source: review-code 2026-08-31 lane=money-reporting.

- ✅ [FIBR-0325] **The bundling suite aborts fatally when run on its own, and passes inside the full suite.**
  `pytest tests/features/bundling/` dies with Fatal Python error: Aborted after a
  few tests; the same tests pass as part of the whole run, so it is an ordering or
  fixture interaction rather than a defect in what they assert.

  Found while verifying an unrelated fix and reproduced on a CLEAN tree, so it
  predates FIBR-0318. It matters because it makes the suite that guards the frozen
  bundle unrunnable in isolation, which is exactly how someone would debug a
  bundling failure. review-tests is the owner.
  Resolved (2026-09-03): fixed and pushed (327a06f); gate green at 2174 passed / 2 skipped, and the suite runs alone at 18 passed / 1 skipped with no abort.

  Diagnosed by hitting it while writing FIBR-0326's leg, so the cause is measured rather than guessed. Every leg driving run_self_test stubs _check_qt to a no-op; run_self_test then reaches _check_icons, which renders a QPixmap, and with no QApplication in the process Qt does not raise -- it ABORTS, taking the pytest run with it. Inside the full suite an earlier test has already created one, which is why it passed there and died in isolation.

  Those legs now take pytest-qt's qapp, so the application exists whatever ran before. The _check_qt stub stays: it is what proves run_self_test resolves its checks at call time.

  Not an ordering or fixture interaction in the tests' own assertions, as the bullet supposed -- a missing precondition in the tests themselves.
  **Layman:** One group of tests crashes if you run just that group.
  Kind: test.
  Source: review-code 2026-08-31 out-of-scope finding.

- ✅ [FIBR-0326] **The self-test has no check for cryptography, the stack guarding every vault unlock.**
  CHECK_NAMES covers Qt, QtNetwork, QtCharts, icons, SQLCipher, pikepdf, PDF
  encryption, Argon2, ofxparse and pdfplumber. cryptography is a promoted runtime
  dependency used directly by keywrap (AES-GCM) and update_key (Ed25519), and it
  loads today only because pdfminer imports it at module scope -- pulled in
  transitively by the pdfplumber check.

  If pdfminer ever defers that import, the OK sentinel goes green on a bundle that
  cannot open any v2 vault. That is the FIBR-0259 shape the file's own comment
  warns about. Fix is an AES-GCM round trip plus one Ed25519 verify.
  Resolved (2026-09-03): fixed and pushed (327a06f); gate green at 2174 passed / 2 skipped.

  _check_cryptography does an AES-GCM round trip and an Ed25519 sign+verify, and sits AHEAD of pdfplumber deliberately -- pdfplumber's tree is what pulls cryptography in today, so a check placed after it could pass on that import alone.

  Falsifiable rather than merely present: a broken round trip and a bad signature each have their own leg, plus a baseline so those two cannot pass against a check that always raises. Five mutants, all killed -- including the check reduced to a no-op.

  One measured correction: patching an attribute on Ed25519PrivateKey does nothing, since it is Rust-backed and generate() returns a concrete type whose sign is not the one replaced. The first draft of that leg passed a bad signature straight through and reported success. It is substituted where the check RESOLVES the name instead.
  **Layman:** The bundled-app health check does not test the library that opens your vault.
  Kind: test.
  Source: review-code 2026-08-31 lane=ui-app-shell.

- 🚧 [FIBR-0327] **Work the MEDIUM tail of the 2026-08-31 audit — 54 findings across 15 lanes.**
  The findings are recorded in docs/reviews/2026-08-31-audit-findings.md; the
  classes worth naming:

  - Untrusted `.fbk` numerics are unbounded on the pre-login surface (Argon2 cost
    parameters, the embedded schema_version), each ending in an exception type no
    caller catches.
  - Missing parent-directory fsync before os.replace at several sites, where four
    siblings already do it.
  - `ATTACH DATABASE '{path}'` interpolates the path unescaped — an apostrophe in
    the user's home breaks backup export and the v2 migration permanently. Found
    independently by two lanes.
  - Which clock defines "today" is undecided: services use the OS-local day while
    a user-pinnable timezone exists. At a month boundary this moves a whole
    month's totals.
  - SQLCIPHER_COMPAT is both what is written and what is accepted, so bumping it
    makes every existing backup unrestorable.
  - Two O(N^2)-shaped costs on interactive paths: the transfer-candidate self-join
    has no usable index, and the batch review's file labels are quadratic per
    refresh.
  - Several i18n and PlainText gaps where a sibling was already fixed.
  Scope note (2026-09-02), from the security-model review-contract gate: the
  first MEDIUM bullet covers EVERY Argon2 cost axis, not memory alone. Two cold
  lanes reached this independently.

  validate_params refuses a memory_kib below the floor and imposes no ceiling,
  and it does not check time_cost or parallelism in EITHER direction. So a
  crafted .fbk can force an arbitrarily large allocation, or -- through
  time_cost -- an arbitrarily long derivation needing no memory at all. Both
  pre-login, on the restore path, before any authentication.

  Bounding memory_kib alone therefore closes none of it, and would ship as "the
  pre-login residual is bounded" while the identical time_cost vector stays open.
  docs/security-model.md T5 and INV-2 now state this, including that INV-2's
  "iterations and parallelism need no on-open check" covers DOWNGRADE only and is
  silent on an inflated recorded cost.

  One decision this needs when it is worked: whether the ceiling belongs in
  validate_params, where it binds every caller including an existing vault whose
  sidecar was edited locally, or only on the pre-login restore path. The two
  behave differently for that vault and no document gives direction.

  Separately, the UI leg of this bullet is already closed: FIBR-0313 M8 put
  HashingError into the except tuple in ui/_password_hint.py. restore_backup and
  verify_backup remain.
  Progress (2026-09-02): the crypto/vault/migration class is worked, plus the clock decision. Landed and pushed: the pre-login .fbk numerics are bounded (a new crypto.validate_untrusted_params at the trust boundary, and migrations.run_migrations refuses a schema version below 1); the ATTACH DATABASE path is bound rather than interpolated, so an apostrophe in the user's home no longer breaks backup export and the v2 migration; SQLCIPHER_COMPAT is split into what an export WRITES and what a restore ACCEPTS, with the restore now opening at the level the manifest records; and cipher_compatibility is validated in auth._open_with, where the plaintext sidecar value enters. Every fix carries a regression test proven red by reverting it.

  The open decision this bullet named is settled: the ceiling belongs at the restore path, NOT in validate_params. security-model INV-2 states the floor is deliberately one-sided and T5 already puts the residual on the restore path, so bounding there closes the attack, binds no existing vault, and needs no spec amendment.

  Which clock defines "today" is also settled (user, 2026-09-02): the pinned time zone wins. datetime_format gained the app clock and thirteen UI sites now read it. The four service-level date.today() defaults are left, because every date-bearing UI call passes today explicitly and importing datetime_format there would pull QtCore into the Qt-free service layer.

  Still open in this bullet: the missing parent-directory fsync at the migration commit points and in write_sidecar_json; auth.complete_first_run not closing the vault on failure; the two O(N^2) interactive costs (the transfer-candidate self-join, the batch review's file labels); and the i18n / PlainText gaps.
  Progress (2026-09-02, second batch): the durability, O(N^2), i18n and
  release-path classes are worked. Landed and pushed, each with a regression
  test proven by mutation_probe. Durability: every rename that commits a vault
  now flushes its directory (crypto.write_sidecar_json, and the migration's S4
  and S5, where S4 landing after S5 left a v1 sidecar over a converted database
  and read as a wrong password); the byte-equivalent private _fsync_dir helpers
  in backup.py and vault_migration.py consolidated into crypto.fsync_dir rather
  than becoming a third copy. auth.complete_first_run closes the vault when the
  sidecar write fails, so the service and Vault.connection no longer disagree
  about being locked.

  O(N^2): TransferDetectionService resolves transfer legs through a new
  TransactionRepository.by_ids instead of loading the whole table on every Home
  refresh; schema v14 indexes transactions(amount_minor, occurred_on) and the
  candidate self-join drops julianday(), which had hidden the date column from
  any index -- measured, SQLite was building a transient automatic index over
  the whole table per call. Batch import labels every row's file in one pass.

  The bump went red in nine test files, and the pins are recast: where the
  assertion meant "the walk reached latest" it now says so, and three
  cross-feature pins on the constant became "this feature's own step is
  registered and reachable". Two of them named 10 in their own test name while
  asserting 13.

  i18n / display: forecast.py's headline and provenance labels set PlainText
  (both interpolate account names the user typed); pdf_export names the month
  through QLocale rather than calendar.month_name; _amount renders money exactly
  instead of through float, which lost four digits and the cents at the app's
  own maximum. The Rules table refills through fill_guard -- it was the last one
  refilling in place, so a delete left the next rule selected with Edit and
  Delete live against it. The Transactions date range seeds from the rows on
  screen instead of Qt's 2000-01-01, which emptied the table on first tick.

  Update and release: the AppImage relaunch waiter takes the image path as an
  argv positional -- shlex-quoted and spliced into a double-quoted echo, an
  apostrophe in the path swallowed the exec, so the app closed and never
  reopened; a download ending short of its Content-Length now says so instead of
  failing the signature check and raising the tamper alarm; both release scripts
  capture the publish exit status so a mid-list 503 reaches the read-back gate
  rather than killing the script before it (the 0.1.21 failure); and
  release-linux.sh refuses an unpushed bump, which used to tag the pre-bump
  commit on the remote.

  Still open in this bullet: categories._refresh not re-running its gating slot;
  _datetime_prefs._read_timezone's unreachable recovery branch; the batch
  review's keyboard-inaccessible Account cell and its inert picker sentinel; the
  import preview's Amount column bypassing the shared money formatter; two
  unguarded vault reads in import_wizard; and the app-shell set (detached worker
  GC, the drain's missing disconnect, the discarded update-check exception, the
  unguarded interrupted-restore os.replace, and app.py having no sys.excepthook).
  .githooks/pre-push gating the working tree rather than the pushed commits is
  also still open.
  Progress (2026-09-02, third batch) — this supersedes the "still open" list in
  the note above, which the work below has cut down. Landed and pushed, each with
  a regression test proven by mutation_probe:

  - The drain's detached update worker survives GC (setParent(None) handed
    ownership back to Python and the next line dropped the only reference) and is
    silenced first, so a download finishing after the window is gone no longer
    reaches the slot that swaps the binary and hard-exits.
  - app.py installs a chained sys.excepthook. Only VaultStateError was caught, and
    a windowed build has no console, so any other startup failure produced an app
    that does nothing when double-clicked. Its two user-facing strings are now
    translated, with the literal at each call site rather than through a _tr()
    wrapper lupdate cannot read through.
  - _datetime_prefs._read_timezone reads the field rather than the selected item.
    Typing a zone the host does not enumerate leaves currentData() on the previous
    one, so the old guard was dead code and Save wrote back the zone the user had
    just replaced -- a wrong-day render now that the pinned zone decides "today".
  - The interrupted-restore recovery is guarded: an OSError inside MainWindow's
    constructor made the app unlaunchable, and it now routes to run()'s
    VaultStateError branch with the *.old copies intact for a retry. The module
    gained a logger, so _on_manual_check_error no longer drops its exception.
  - The import preview's Amount column goes through the shared money formatter.

  Still open, and all lower severity than the above: categories._refresh not
  re-running its gating slot; the batch review's keyboard-inaccessible Account
  cell and its inert picker sentinel; two unguarded vault reads in import_wizard
  (the lane named no site, so this one needs re-deriving against current source);
  single_instance's narrowed-but-open stale-socket race; .githooks/pre-push gating
  the working tree rather than the pushed commits; and FIBR-0096's claim that the
  per-artifact .sig is the primary integrity gate, which is false for a
  rename-replay.
  Status corrected 2026-09-03: this sat at 📋 while three batches of its
  work had already landed and been pushed. Its own body records them; only
  the marker was stale.
  **Layman:** A batch of smaller real defects the full sweep found; most are now fixed, with a lower-severity tail left.
  Kind: review-fix.
  Source: review-code 2026-08-31.

- 📋 [FIBR-0328] **Work the LOW/INFO tail of the 2026-08-31 audit — roughly 110 findings.**
  Recorded in docs/reviews/2026-08-31-audit-findings.md.

  Mostly stale comments and docstrings that assert something no longer true,
  unreachable defensive branches, missing accessible names on password fields,
  raw ISO dates on tabs the date preference does not reach, and error paths that
  collapse two distinguishable causes into one message.

  Also two check-code observations: tracked Python under docs/reviews is outside
  the gate's `ruff check src tests` scope by design and nothing records that
  decision; and there is no .yamllint config, so that tool runs on defaults the
  project never adopted (80 columns against its own 88).
  **Layman:** Minor issues and observations from the full sweep, recorded so they are not lost.
  Kind: review-fix.
  Source: review-code 2026-08-31.

- 📋 [FIBR-0329] **check-code has no tool that reads shell for supply-chain fetches.**
  FIBR-0318 fixed five unverified `curl | tar` fetches in ci-setup.sh and
  _build-smoke-in-container.sh. No tool in check-code's set decides that class:
  zizmor reads workflows only and covers `uses:` pins, actionlint checks workflow
  correctness, and shellcheck reads syntax rather than provenance.

  So the fix holds only while someone remembers. A semgrep rule matching a fetch
  piped into an extractor, or one reaching `install`, would make it mechanical --
  and check-code already runs semgrep.
  **Layman:** Nothing automatically catches a build script downloading a tool without verifying it.
  Kind: chore.
  Source: check-code 2026-08-31 tool-gap.

- 📋 [FIBR-0332] **A batch mapping answered with the profile-name field blank is still asked once per file.**
  Surfaced while fixing FIBR-0319 and deliberately NOT widened into it.

  FIBR-0319 makes an answered mapping settle every other file sharing that
  header -- but only through the SAVED PROFILE, because that is the
  mechanism § 4.3 gives for remembering an answer. _on_map_next saves only
  when the profile-name field is non-empty, so a user who leaves it blank
  still answers the same question per file.

  The password half has no such condition: a typed password joins
  _run_passwords for the run whether or not anything is persisted. The
  mapping analogue would be a per-run map from header signature to
  ColumnMapping, consulted by the ladder ahead of match_profile.

  Whether that is a defect or the design is the question to settle first.
  Declining to name a profile is arguably declining to remember it -- but
  § 4.3 decision 1 says re-asking an answered question is babysitting, and
  thirty identical questions is what that decision exists to prevent. The
  spec should say which, and the code follow.
  **Layman:** Import thirty spreadsheets of the same layout without naming a saved layout, and it still asks you thirty times.
  Kind: ux.
  Source: in-session-2026-09-03 (observed while fixing FIBR-0319).

## How to add an item

1. Allocate the next ID:
   ```bash
   echo $(($(cat .roadmap-counter) + 1)) > .roadmap-counter
   printf "FIBR-%04d\n" $(cat .roadmap-counter)
   ```
2. Insert at the **position** where it should be tackled (not
   blindly at the end).
3. Set the status emoji (📋 Planned, 💭 Considered).
4. Add `Lanes:` line declaring ownership.
5. Add `Kind:` (required on every bullet, per
   `roadmap-format.md § 3.5`) and `Source:` (omit only when it's
   `planned`).

See `docs/standards/roadmap-format.md § 3.5` for the full bullet
contract.

## How findings get folded

After every `/audit` + `/indie-review` (and `/debt-sweep`):

```
Phase closes
  → Run /audit + /indie-review
  → Triage findings
  → If clean: phase fully closed.
  → If actionable: batch into one new fix-pass FP## (next-up),
    add [Unreleased] entry, run that fix-pass through the
    9-step loop; its own closing audits may produce another.
```

See `docs/standards/roadmap-format.md § 3.8` and the
`app-workflow` skill (`~/.claude/skills/app-workflow/SKILL.md`,
machine-local) for the full pattern.
