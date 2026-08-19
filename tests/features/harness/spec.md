# Feature spec — harness conformance (`FIBR-0001` INV-1 / INV-2)

The gate is the thing that judges every other change, and until now nothing
judged **it**. `FIBR-0001` INV-1 holds an authoritative table of the stages
`scripts/ci-local.sh` runs, and that table's whole purpose is to stop the gate
quietly losing a stage — but the guarantee was prose discipline in a document,
not a check. Both halves drifted in one day (2026-08-05): the spec's stage list
went stale twice, and the `shellcheck` stage shipped globbing `scripts/*.sh`
while claiming to cover a publish path it did not reach.

This suite is the mechanical half. It reads the script and the spec and
compares them, so a dropped stage reddens the gate instead of passing silently.

Enforces `docs/specs/FIBR-0001.md` INV-1/INV-2. No network, no vault, no Qt —
it reads two files in the repo.

| INV | Statement |
|---|---|
| INV-1 | Every tool named in `FIBR-0001` INV-1's stage table is actually invoked by `scripts/ci-local.sh`, and every tool the script invokes appears in the table — compared as an **unordered set**, because INV-1 states order is not contractual. |
| INV-2 | The `gitleaks` invocation keeps `--redact`. On a public repo, CI logs are world-readable: without it a finding prints the matched secret verbatim, so the stage meant to catch a leak would publish it. Regression-locks the defect found in this spec's cold-eyes loop 2. |
| INV-3 | The `shellcheck` stage selects its targets via `git ls-files`, not a directory glob — a glob silently skipped the seven `packaging/` release recipes it claimed to cover, and its staleness is invisible. |
| INV-4 | `.github/workflows/ci.yml` invokes `scripts/ci-local.sh` rather than restating any stage, so CI and local cannot drift (INV-2 of the spec). |
| INV-5 | `.githooks/pre-push` skips the gate for a push whose refs are **all** tags **and** whose tagged commits are already reachable from a remote-tracking branch — and runs it in every other case: a branch ref anywhere in the push, a tag whose commit is not yet on the remote, or an empty ref list. Exercised by running the hook, not by reading it. |

**Why a set and not a sequence:** `FIBR-0001` INV-1 says explicitly that order is
cheapest-first by convention and *not* part of the contract, so asserting a
sequence would fail a reordering the spec permits. The assertion is "all of
these ran", which is the shape the spec names.
