---
paths:
  - ".corpus-numbers"
  - "tests/features/account_detect/**"
  - ".githooks/**"
---

# `.corpus-numbers`: the real-account-number leak guard

**The guard needs a file only the user can supply (FIBR-0086 INV-8, wired by
FIBR-0248).** This repo is **public**, and a bank account number is not a
credential, so `gitleaks` does not match one — a real number reached a spec
once and sat there a month (FIBR-0244). The guard that catches that class needs
the real numbers to search for, and they are the secret, so they are never
committed. They go in a **gitignored `.corpus-numbers`** at the repo root, one
per line, as printed.

**Create it in an EDITOR, never on a command line** — open
`.corpus-numbers` in a text editor, one number per line, exactly as printed on
the statement. Any real number works, not only account numbers: a card number
or an ID number is caught the same way (FIBR-0246). Enter each number whole:
the guard looks for it inside every run of eight or more digits, so a short
fragment would match unrelated numbers. Spacing and dashes do not matter: the guard runs
`normalise_account_number` before comparing, and its search pattern allows any
run of separators between digits, so a number split by a line-wrap is still
found.

**Never a command line.** That lands in `~/.bash_history` and in an agent's
transcript — the defect **FIBR-0276** filed against the recipe that used to
stand in CLAUDE.md ([`docs/history/claude-md.md`](../../docs/history/claude-md.md)).
An editor writes to no history.

**This is a step the user performs and an agent cannot.** An agent must not
invent the values. Counting the file's lines is fine; showing one is not.

Without it `tests/features/account_detect/test_no_real_data.py` **skips**, and
a skipping test reads as coverage while providing none. `FINBREAK_CORPUS_NUMBERS`
(comma-separated) overrides **where the numbers come from** — for a machine
that keeps them elsewhere, or a run against a different set. **Its value comes
from a gitignored file written in an editor and substituted in, never typed**:
`FINBREAK_CORPUS_NUMBERS="$(paste -sd, <that-file>)" pytest …` puts no value on
the command line or into `~/.bash_history`. Substituting from `.corpus-numbers`
itself buys nothing — that is already the default. CI cannot hold the numbers
and never will, so this check is local-only by design.

**The file is per-machine.** Where it exists `test_no_real_data.py` runs, and
the pre-push hook also searches each pushed commit's message and added lines
for the numbers (FIBR-0439). Where it does not, that test skips and `gitleaks`
does not match an account number, so such a machine has no cover for this
class and should not push prose it has not read.
