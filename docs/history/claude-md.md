# CLAUDE.md — rule history

Why the rules in [`CLAUDE.md`](../../CLAUDE.md) read the way they do: what each
one replaced, what went wrong to make it necessary, and the measurements behind
it.

**This file is not loaded at session start, and nothing is built from it.** It
is a record, kept because a rule whose reason is lost gets "simplified" back
into the defect it was written to stop. Read it when you are about to change a
rule, or when one looks arbitrary.

It exists because `CLAUDE.md` is read on every prompt, and pedigree woven into a
rule's own paragraph is paid for on every turn while being needed almost never
(FIBR-0296, and the user's 2026-09-21 directive to move history out). The same
split is already standard one level up: the global rules keep theirs in
`~/.claude/docs/history/claude-md.md`.

**Sections mirror `CLAUDE.md`'s headings**, so the pedigree for a rule is under
the heading that rule lives beneath.

**Dates and figures here are frozen at the moment they were recorded.** That is
the point of a record — do not refresh them, and do not read one as a claim
about today. Where a figure has since moved, the live number is in the tree, not
here.

---

## Cold-eyes review cadence

**The spec/plan cap was 7 until 2026-08-19.** Set by user directive 2026-07-11
and carried over unchanged when `review-contract` replaced `/cold-eyes`. It came
down to 3 because the extra loops stopped paying once the skills and the
app-workflow were redesigned.

The measurement was this file's own 2026-08-18 gate: three loops, nineteen
verified findings, and by loop 3 half of them were the review's own collateral —
so a fourth loop would mostly repair the third's repairs.

---

## Build and test

### The `.corpus-numbers` recipe was a command line until 2026-08-18

This section used to give a `printf … > .corpus-numbers` recipe. That was the
defect **FIBR-0276** filed: a shell command line lands in `~/.bash_history` —
and in an agent's transcript — which the never-list did not name at the time. An
editor writes to no history, which is why the rule is now "open it in an
editor".

### The leak guard was inert for four days longer than it looked

**FIBR-0248 wired the file route on 2026-08-14. The file itself was not created
until 2026-08-18**, so `tests/features/account_detect/test_no_real_data.py` went
on skipping for four more days. **Wiring a source is not the same as supplying
one**, and only the second date is when the tree was first actually scanned.

On the day it went live it passed on first run, so no real number was in the
tracked tree then. Before that date the guard was inert and the skip was safer
than it looked.

### Where the habit of `--no-verify` on a tag came from

Pushing a branch and then its tag used to run the same multi-minute gate twice
on one already-gated commit. That is where the habit came from — a bypass no
project document sanctioned (**FIBR-0290**). The hook now skips a tag-only push
of already-pushed commits by itself, so the flag has nothing left to do there.

---

## Doc-only pushes

### The prose-reading suite list was wrong twice in one day

The list is enumerated, so it can go stale — and it did, twice.

- The **first** justification for skipping the gate was "no Python stage reads
  prose". Simply false.
- The **second** was "those two commands are all three of them". Also false.

That is why the list is now bound to the tree by
`tests/features/prose_checks/` (**FIBR-0278**) rather than maintained by hand.
Before that guard existed nothing tied the list to reality, which is the failure
that produced two wrong lists in one day.

`tests/features/release_integrity/` was missing from the list until 2026-08-18,
and all three review lanes found it independently.

A grep recipe for re-deriving the list stood here for one review loop and was
deleted for being unreproducible: the plausible readings of it returned wildly
different file sets, none of them the right one. `account_detect` walks
`git ls-files` and names no path literal, so no search-based audit can find the
broadest member.

### The old `docs/specs/FIBR-0001.md` carve-out

"Doc-only" used to carve out that one spec, because editing it can turn
`tests/features/harness/` red. The carve-out is **gone rather than dropped**:
the check that enforced it now runs on every doc-only push, so the exception had
nothing left to do.

### The digit test it replaced

Until 2026-08-18 the rule asked whether the commit added "digits or key-shaped
strings", and demanded the prose checks only then. Two things retired it.

The judgement fell to the person least able to make it — you have just written
the prose and know what you meant by it, which is exactly when a pasted number
does not read as one. And the judgement was buying under two seconds. A branch
that trades a silent, unrecoverable failure against two seconds should not be a
branch.

### The deny-list version of "only documentation"

The rule once read: *no file under `src/`, `tests/`, `scripts/`, `.github/` or
`packaging/`*. It lasted one review loop. `.githooks/pre-push` is under none of
those, so a commit touching only that file passed the test word for word — and
it is shell, named explicitly by `ci-local.sh`'s shellcheck stage, so the
"doc-only" route would have skipped the one stage that reads what had just
changed. `.gitleaks.toml`, `.gitignore` and any stray `.sh`, `.toml` or `.yml`
fail a deny-list the same way.

**A closed list of directories cannot express "not code"; a suffix can.**

### When the guard actually went live

**2026-08-18**, when `.corpus-numbers` was created on this machine:
`test_no_real_data.py` began running instead of skipping. That is the change
that makes the positive test earn its keep — before it, the branch was guarding
nothing.

---

## Push policy

### The retired phase-tag ban

This repo used to hold that `<ID>-complete` phase tags stay local until the user
authorises a push. **That rule is retired, and the reason is worth keeping: it
was never enforceable.**

`cut-release` Phase 5 on a public repo pushes with `--follow-tags`, and
`/close-phase` Step 6 offers the same command in a prompt naming the tag it is
about to publish. Both take the push path every time on a public repo, so the
tags went up automatically regardless. Measured 2026-08-18: every local
`*-complete` tag was already on the remote.

A rule that the project's own two prescribed procedures break on every run is a
rule describing an intention rather than the repository.

**Three earlier drafts of the replacement each contradicted themselves** — one
banned the flag outright while `cut-release` ran it; one carved out *unless you
are cutting a release*, which is the exact command the sentence beside it
forbade; one claimed nothing here ever needed the flag. Hence the live rule's
standing warning not to reinstate the ban without changing the tooling first.

---

## Cutting a release

### v0.1.20 published with zero assets

It went unnoticed for ten days. Both the README's "download the latest release"
link and the in-app updater resolve to that page, so both were dead the whole
time. Found 2026-08-17 while cutting 0.1.21.

**The guard landed 2026-08-19** (FIBR-0275, INV-8): both release scripts now
read the published asset list back and refuse to report success on an incomplete
set. What it still cannot catch is nobody running `release-linux.sh` at all —
which is exactly how v0.1.20 shipped empty — so the asset read-back at the end
of that section remains a manual step.

Same class as **FIBR-0203**, which was closed as a one-off rather than guarded.
That is why it recurred, and why the live rule insists on the read-back.

### The transient GitHub API failures on 0.1.21

Cutting 0.1.21 hit them on four different endpoints: `gh repo view` (503),
`git push origin <tag>` (401), the `windows-build.yml` dispatch (503, three
times from inside the script while `gh release view` and `gh workflow list` both
worked and githubstatus reported Actions operational), and the asset upload.
Every one cleared on a retry. The dispatch took six attempts.

**The upload failure was the dangerous one, because it half-succeeded.** The
final `gh release upload --clobber` deletes each existing asset before replacing
it, so a 503 mid-list left v0.1.21 carrying `SHA256SUMS.sig` but **not**
`SHA256SUMS`, and `.exe.sig` but **not** the `.exe` — a signed release whose
signed manifest was gone. Nothing reported an error loudly; the script had
already printed its signing successes. That is why the live rule uploads one
file per call and reads the assets back.

Hand-dispatching the Windows build as a workaround was tried twice on 0.1.21 and
discarded both times: the script dispatches its own run and waits for one newer
than the run it recorded on entry, so a hand-dispatched build is ignored and a
Windows freeze is burned for nothing.

### Why `release-linux.sh` now checks for an unpushed HEAD

Until **FIBR-0327** it tested only `git status --porcelain`, so a
committed-but-unpushed bump passed and the script tagged the **remote's** HEAD —
the pre-bump commit — publishing assets built from a version the tag does not
point at.

### Why a failed upload no longer skips the read-back gate

**FIBR-0327.** Both scripts now capture the publish command's exit status
instead of letting `set -e` end the run there. `--clobber` deletes each asset
before replacing it, so a failure part-way down the list leaves the release
short — the state the gate reports — and the script used to die before reaching
it. That is what happened on 0.1.21.

---

## `cut-release` Phase 2b

**`act` was measured unconfigured on 2026-08-19**: `~/.config/act/actrc` was
absent and `act push -W .github/workflows/ci.yml -n </dev/null` exited 1 on
`level=fatal msg=EOF`. `act --version` succeeds on an unconfigured install and
settles nothing, which is why the live check tests both conditions.

**The `cp -a` caveat was verified the same day** by running that copy and
listing the result: `.corpus-numbers` reaches the container, where
`actions/checkout` would hand CI tracked files only.

**`zizmor` coverage of `ci.yml` was measured too**: it exits 0 on the real tree
and non-zero with the `actions/checkout` pin reverted to a mutable tag. So the
pin is covered by the local run; what is uncovered is the step executing.

---

## Module map

### Why FIBR-0050 INV-11 carries a same-commit rule

INV-11 was silently falsified twice. FIBR-0216 added the zero-amount degrade,
and FIBR-0252 made `parse` return per-row errors. Neither updated INV-11.

The CLAUDE.md note used to add that the drift was repaired and checked by cold
review lanes, and told readers not to look for it. That sentence moved here in
FIBR-0350. CLAUDE.md is loaded into every review lane before its brief, so it
steered each cold reviewer of FIBR-0050 away from that spec's most contested
area. Every lane of one review loop reported it unprompted.

---

## Standards reference

### The spec-filename reconciliation

`naming.md` says a spec is `docs/specs/<ID>.md`. The user decided 2026-08-05
that specs are `docs/specs/<ID>-<topic>.md`, because a filename a human can read
without opening it is worth the suffix. The first file under the new rule was
`docs/specs/FIBR-0231-plain-english-month-summary.md`.

`naming.md` is not amended yet on purpose: amending it changes what a conformer
writes, so it trips rule 14's gate, and back-migrating the existing `FIBR-NNNN.md`
specs means repointing every inbound citation. Both halves are tracked as
**FIBR-0196** rather than done in passing.
