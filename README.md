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

Current version: **0.1.10** (early preview). **[⬇ Download the latest
release](https://github.com/milnet01/finbreak/releases/latest)**, or see
[CHANGELOG](CHANGELOG.md) for what's shipped and [ROADMAP](ROADMAP.md) for
what's coming.

**Code signing.** finbreak takes part in the
[SignPath Foundation](https://signpath.org)'s free code-signing program for
open-source projects; Windows release builds are signed with a certificate
provided by the SignPath Foundation. Free code signing provided by
[SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

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
  can edit and corrections it learns from,
- **spotting transfers between your own accounts** — money you move from,
  say, your current account to savings is flagged so it isn't mistaken for
  spending or income (you confirm each one),
- a **dashboard** on the Home screen — an income-vs-spending summary for a
  period you choose (it defaults to last month and remembers your choice), a
  pie chart of where your money went by category, and a month-by-month trend
  chart; money moved between your own accounts never counts as spending or
  income, and
- a searchable, filterable **Transactions tab** — find rows by description
  and filter by date range, account, and category (any or all at once), with
  columns you can drag to reorder and resize (it remembers your layout),
- **exporting a PDF report** — choose the sections (summary, charts,
  transactions), the accounts and period, and a light or dark theme, and
  optionally lock the file with a password so only you can open it, and
- **encrypted backups** — save a portable, password-protected backup of your
  whole vault and restore it later, even onto a new master password if you've
  forgotten the old one,
- **six colour themes** — three light (Ledger, Parchment, Mint) and three dark
  (Midnight, Graphite, Emerald), or **"Follow system"** to match your computer's
  light/dark setting automatically and switch the instant it changes; your
  choice applies the moment the app opens, even before you unlock, and
- everyday **conveniences** — set auto-lock to "Never" if you'd rather it didn't
  lock while idle, and forget a bank-statement password the app remembered
  (per account) whenever you want.

finbreak now also runs on **Windows** as a self-contained `.exe`. Still to come:
a packaged macOS app. See the [ROADMAP](ROADMAP.md) for the full plan.

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

**Windows (testing)** — a self-contained `finbreak.exe` (no Python needed) is
built on demand by the `windows-build` CI workflow and shared with testers as a
build artifact. It is **not code-signed yet**, so Windows SmartScreen will show an
"unknown publisher" warning the first time you run it — choose **More info → Run
anyway**. There is **no auto-update on Windows** (that's Linux/AppImage-only for
now); to update, just replace the old `.exe` with the newer one.

**macOS** — a packaged `.dmg` is still on the way (see [ROADMAP](ROADMAP.md)). Until
then, you can run from source with Python 3.12+ (see
[CLAUDE.md](CLAUDE.md) "Build and test").

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
