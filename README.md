# finbreak

> A private desktop app that shows you where your money goes — read
> straight from your own bank statements. There's no bank linking, no
> account to sign up for, and none of your financial data ever leaves your
> computer.
>
> The one exception is an **opt-in, off-by-default** update check: switch
> it on and finbreak looks for a newer version and can install it for you
> (after confirming the download is genuinely signed). Leave it off — the
> default — and the app never touches the internet at all.

[![Status](https://img.shields.io/badge/status-pre--alpha-orange)]()
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Current version: **0.1.7** (early preview). **[⬇ Download the latest
release](https://github.com/milnet01/finbreak/releases/latest)**, or see
[CHANGELOG](CHANGELOG.md) for what's shipped and [ROADMAP](ROADMAP.md) for
what's coming.

## Status

finbreak is in **early development** — an early preview that already does a
lot, with more polish and features to come. What works today:

- a private, password-protected place to keep your finances (an encrypted
  vault),
- importing statements from **CSV, OFX, and PDF** files (including
  password-protected PDFs),
- organising them into **accounts** and into **categories** you can group
  and rename,
- **automatically sorting** transactions into categories, with rules you
  can edit and corrections it learns from, and
- **spotting transfers between your own accounts** — money you move from,
  say, your current account to savings is flagged so it isn't mistaken for
  spending or income (you confirm each one).

Still to come: a **dashboard** with charts and a spending summary, and
**password-protected PDF export**. See the [ROADMAP](ROADMAP.md) for the
full plan.

## Install

**Linux (x86_64)** — everything is bundled, so you don't need Python or any
libraries installed:

1. Download the `finbreak-*-x86_64.AppImage` from the
   **[latest release](https://github.com/milnet01/finbreak/releases/latest)**.
2. Make it runnable (once):
   ```bash
   chmod +x finbreak-*-x86_64.AppImage
   ```
3. Launch it — double-click in your file manager, or run
   `./finbreak-*-x86_64.AppImage`.

Each release also ships a `.sig` file next to the AppImage — that's the
signature finbreak uses to check updates are genuine; you don't need to do
anything with it yourself.

**Windows and macOS** — packaged installers are on the way (see
[ROADMAP](ROADMAP.md) → P13). Until then, you can run from source with
Python 3.12+ (see [CLAUDE.md](CLAUDE.md) "Build and test").

## Quickstart

1. **Launch finbreak.** The first time, you'll create your vault by
   choosing a **master password**. This password encrypts everything — keep
   it safe, because there is **no way to recover your data if you forget
   it**.
2. **Add an account** (for example, your current account).
3. **Import a statement** — point finbreak at a CSV, OFX, or PDF file from
   your bank. It reads the transactions and files them into categories.
4. **Fix anything it got wrong.** Change a transaction's category and
   finbreak can turn your correction into a rule, so it gets it right next
   time.
5. **Confirm any transfers.** If you move money between your own accounts,
   finbreak spots the matching pair and lists it under the **Transfers**
   tab — confirm it so it isn't counted as spending or income.
6. **Lock it when you're done.** finbreak also locks itself automatically
   after a period of inactivity (you can set how long in **Settings**).

### Staying up to date (optional)

Automatic updates are **off by default**. If you'd like finbreak to check
for new versions, turn on **"Check for updates on startup"** in
**Settings**. When it's on, finbreak checks GitHub at launch and, if there's
a newer release, offers to download and install it — but only after
verifying the download's signature, so a tampered update can never be
installed. Leave it off and finbreak makes no network connections at all.

## For maintainers

**To resume work:** open a terminal in this directory and run `claude`,
then type `continue`. Claude will summarise current state back to you
before doing any work — confirm or correct that summary; never let Claude
resume work without it.

## Documentation

- [ROADMAP](ROADMAP.md) — what's planned, with stable IDs.
- [CHANGELOG](CHANGELOG.md) — what's shipped, Keep-a-Changelog
  format with an `[Unreleased]` block at the top.
- [docs/discovery.md](docs/discovery.md) — Phase A output:
  problem, users, success criteria, tech stack, out of scope.
- [docs/design.md](docs/design.md) — Phase B output: architecture
  diagram, components, data flow.
- [docs/decisions/](docs/decisions/) — Architecture Decision
  Records. Why we chose X over Y.
- [docs/glossary.md](docs/glossary.md) — domain terms used in
  code and docs.
- [docs/known-issues.md](docs/known-issues.md) — findings
  deferred because they're blocked by an unbuilt feature.
- [docs/audit-allowlist.md](docs/audit-allowlist.md) —
  project-specific false-positive memory for `/audit` and
  `/indie-review`.
- [docs/ideas.md](docs/ideas.md) — mid-flight ideas pending a
  user-decision on placement (created on first use).
- [docs/standards/](docs/standards/) — coding, naming, dependencies,
  documentation, testing, commits (+ roadmap-format).
- [.claude/workflow.md](.claude/workflow.md) — live workflow
  state and rules.

## Disclaimer

finbreak is provided **as-is**, with no warranty of any kind (see
[LICENSE](LICENSE)). It reads and summarises your bank statements locally
on your own machine — it does **not** give financial advice, and it is
**not** connected to your bank.

The author is **not responsible for any incorrect information the app may
display** — for example a mis-read amount, a wrong category, or an
inaccurate total. Always check important figures against your original
statements before relying on them.

If you spot something wrong, **please
[log an issue](https://github.com/milnet01/finbreak/issues)** so it can be
investigated and fixed. Bug reports genuinely help make the app more
accurate for everyone.

## License

[MIT](LICENSE).
