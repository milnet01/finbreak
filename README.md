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

Current version: **0.1.22** (early preview). **[⬇ Download the latest
release](https://github.com/milnet01/finbreak/releases/latest)**, or see
[CHANGELOG](CHANGELOG.md) for what's shipped and [ROADMAP](ROADMAP.md) for
what's coming.

**Code signing.** Windows builds are **not yet code-signed**, so Windows
SmartScreen may warn about an "unknown publisher" the first time you run finbreak
(see [Install](#install) for how to proceed). We applied to the
[SignPath Foundation](https://signpath.org)'s free code-signing programme for
open-source projects in July 2026 and were **declined**; the plan is to build up
more of a public track record and reapply. This section will say so once signing
is in place. (Linux AppImages and the Windows `.exe` are already Ed25519-signed for
the in-app updater — a separate thing from an OS "publisher" certificate.)

## Status

finbreak is in **early development** — an early preview that already does a
lot, with more polish and features to come. What works today:

- a private, password-protected place to keep your finances (an encrypted
  vault),
- importing statements from **CSV, OFX, and PDF** files (including
  password-protected PDFs) — **several at once** if you like, so a year of
  monthly statements or a mixed pile of CSV, OFX and PDF goes in one pass;
  finbreak asks up front for anything it genuinely can't get past (a locked
  PDF's password, the column layout of a spreadsheet it hasn't seen), then
  works through the rest on its own and shows you one screen listing every
  file — where each is going, how many transactions are new, how many are
  duplicates you already have, and how many lines it couldn't read — with
  nothing written until you press Import all,
- **statements that file themselves** — finbreak reads the account number
  printed on a statement and pre-selects the matching account, saying why it
  chose it, and offers to create the account if it's one it hasn't seen; where
  it can't be sure it doesn't guess, it says so and leaves the choice to you,
- organising them into **accounts** — shown in a sortable table of Name, Type,
  Account number, Note and Status, whose column widths and order finbreak
  remembers; each account can keep a reference **account number** (shown as dots
  plus the last four digits, so a glance or a screenshot never gives it away —
  tick **Show account numbers** when you need the full one to pay someone, and
  it hides itself again after half a minute) and a free-text **note**,
- ...and into **categories** you can group and rename — now up to three levels
  deep (Type › Category › Sub-category),
- **automatically sorting** transactions into categories — with built-in
  guesses for common shops and services (so a fresh import is sorted straight
  away; each guess is tagged so you can override it), plus your own rules you
  can edit and corrections it learns from,
- **spotting transfers between your own accounts** — money you move from,
  say, your current account to savings is flagged so it isn't mistaken for
  spending or income (you confirm each one),
- **spotting your recurring money** — the subscriptions, debit orders, and
  regular income (like your salary) that repeat every week, fortnight, month,
  or year; finbreak suggests them on a new **Recurring** tab so you can
  confirm what's real and see at a glance what's on autopilot each month,
- a **Forecast tab** that projects your balance forward — it starts from a
  real, current figure (your latest statement's closing balance, brought up to
  date with everything imported since) and draws where you're heading to the end
  of the month, or 30, 60 or 90 days out, using the recurring money you've
  confirmed; only current and savings balances count as spendable cash, and it
  names any account it left out and why,
- **checking your balances add up** — the Accounts tab marks each current or
  savings account ✓ when the transactions you've imported bridge one statement's
  closing balance to the next, or ⚠ with the amount it's off by, so a missing or
  duplicated import doesn't go unnoticed,
- a **dashboard** on the Home screen that opens by telling you, in a sentence,
  what your month actually did — "September cost you R2,340 more than your usual
  month. Most of it was one thing — Vet, R1,900 more than usual." — instead of
  leaving you to work it out from the charts; it stays quiet when the month is
  ordinary, says "so far" while a month is still running, and says nothing at all
  rather than guessing when there isn't enough history to know what usual means.
  Below that the breakdown is the star: three
  side-by-side columns for **Spending**, **Income**, and **Transfers**, each
  with its own pie of where the money went, the big total up top, and an
  openable list beneath it (click into a category, down to a single one, then
  see your transactions grouped by shop with a count like "Woolworths ×3", and
  open a shop to see each purchase); a slim **Net** line shows the period's
  surplus or shortfall, a **recurring-money** card sums what's on autopilot each
  month, an **Alerts button** lights up when something is worth a look — a new
  recurring charge that just appeared, a category well above its usual spend, or
  an expected debit that didn't post (open it for the list; dismiss any alert and
  it stays dismissed) —
  and a month-by-month trend chart sits at the bottom; you choose the
  period (it defaults to last month and remembers your choice), and money moved
  between your own accounts never counts as spending or income (make the window
  small and the page scrolls, rather than squashing the three columns into
  unreadable slivers), and
- a searchable, filterable **Transactions tab** — find rows by description
  and filter by date range, account, and category (any or all at once), with
  columns you can drag to reorder and resize (it remembers your layout),
- **exporting a PDF report** — choose the sections (summary, charts,
  transactions), the accounts and period, and a light or dark theme, and
  optionally lock the file with a password so only you can open it, and
- **encrypted backups** — save a portable, password-protected backup of your
  whole vault, check it's readable before you rely on it, and restore it later —
  even onto a new master password if you've forgotten the old one,
- **six colour themes** — three light (Ledger, Parchment, Mint) and three dark
  (Midnight, Graphite, Emerald), or **"Follow system"** to match your computer's
  light/dark setting automatically and switch the instant it changes; your
  choice applies the moment the app opens, even before you unlock, and
- **a layout that stays how you left it** — every table in the app remembers the
  column widths and the column order you dragged them into, including the
  Forecast tab and the Home dashboard's breakdown lists; if you'd rather start
  fresh, **Window → Reset layout** puts the window size *and* every table's
  columns back the way they looked on a new install, in one click, and
- a **recovery code** — a second way in, given to you once when your vault is
  created. Forgetting your master password used to mean losing everything;
  now the code unlocks the vault and asks you to choose a new password. You
  can decline it, replace it, or remove it later from **Settings**, and an
  existing vault is upgraded automatically the next time you unlock it,
- everyday **conveniences and safety** — an optional password hint on the unlock
  screen, amounts and descriptions you copy are cleared from the clipboard after a
  short while, repeated wrong unlock attempts are slowed down, you can set
  auto-lock to "Never" if you'd rather it didn't lock while idle, you can
  forget a bank-statement password the app remembered (per account) whenever you
  want, and starting finbreak when it's already open simply brings the window you
  have to the front instead of opening a second copy.

finbreak now also runs on **Windows** as a self-contained `.exe`, and on **Linux**
installs as a native **RPM** on openSUSE Tumbleweed and Fedora 44 (from the
[openSUSE Build Service](https://download.opensuse.org/repositories/home:/milnet:/finbreak/))
alongside the existing AppImage. Still to come: **deb** packages for Debian and
Ubuntu (the recipe exists but those targets don't build yet), a **Flatpak** on
Flathub, and a packaged macOS app. See the [ROADMAP](ROADMAP.md) for the full
plan.

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

If you want finbreak in your applications menu or pinned to your panel, you
need to make that shortcut yourself — the AppImage doesn't install one. **Name
the file `io.github.milnet01.finbreak.desktop`** (put it in
`~/.local/share/applications/`), *not* `finbreak.desktop`, and point its
`Icon=` line at `io.github.milnet01.finbreak`. On Wayland, KDE and GNOME match
a running window to its pinned shortcut by that exact filename, so a
differently-named shortcut leaves you with **two** finbreak icons in the panel
at once — the shortcut and the running window, side by side. (`StartupWMClass`
looks like the setting that controls this, and it is the right one on X11, but
Wayland ignores it.)

Each release also ships a `.sig` file next to the AppImage — that's the
signature finbreak uses to check updates are genuine; you don't need to do
anything with it yourself.

**Linux (openSUSE Tumbleweed / Fedora 44)** — finbreak is also packaged as a
native RPM, so your usual updater keeps it current. Add the repository once,
then install:

```bash
# openSUSE Tumbleweed
sudo zypper addrepo https://download.opensuse.org/repositories/home:/milnet:/finbreak/openSUSE_Tumbleweed/home:milnet:finbreak.repo
sudo zypper refresh && sudo zypper install finbreak

# Fedora 44
sudo dnf config-manager addrepo --from-repofile=https://download.opensuse.org/repositories/home:/milnet:/finbreak/Fedora_44/home:milnet:finbreak.repo
sudo dnf install finbreak
```

Debian/Ubuntu `.deb` packages and a Flathub Flatpak are still being worked on —
use the AppImage above on those systems for now.

**Windows** — a self-contained `finbreak.exe` (no Python needed) ships as a
release asset on each
**[release](https://github.com/milnet01/finbreak/releases/latest)**, next to an
Ed25519 `finbreak-*.exe.sig` the updater verifies (the `windows-build` CI workflow
also builds it on demand for testers). It is **not code-signed** for Windows (no
Authenticode "publisher" certificate yet), so SmartScreen shows an "unknown
publisher" warning the first time you run it — choose **More info → Run anyway**.
We applied to the SignPath Foundation's free certificate programme for
open-source projects in July 2026 and were declined; the plan is to build up more
of a public track record and reapply.
Automatic updates work the same as on Linux — opt-in and off by default (see
[Staying up to date](#staying-up-to-date-optional)).

**macOS** — a packaged `.dmg` is still on the way (see [ROADMAP](ROADMAP.md)). Until
then, you can run from source with Python 3.12+ (see
[CLAUDE.md](CLAUDE.md) "Build and test").

## Quickstart

1. **Launch finbreak.** The first time, you'll create your vault by
   choosing a **master password**. finbreak then shows you a **recovery
   code** — one line of letters and numbers, shown once. Write it down or
   save it somewhere away from this computer: it can unlock your vault if
   you ever forget your password. finbreak keeps no copy, so if you lose
   **both** your password and your recovery code, your data cannot be
   recovered.
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
installed. The prompt shows what changed in every release you skipped, not
just the newest one, and the download bar shows real progress. Leave it off
and finbreak makes no network connections at all.

## For maintainers

**To resume work:** open a terminal in this directory and run `claude`,
then type `continue`. Claude will summarise current state back to you
before doing any work — confirm or correct that summary; never let Claude
resume work without it.

## Documentation

- [SECURITY](SECURITY.md) — how to report a vulnerability
  privately, which versions get fixes, and how to verify a
  signed release.
- [CODE_OF_CONDUCT](CODE_OF_CONDUCT.md) — Contributor Covenant
  2.1.
- [CONTRIBUTING](CONTRIBUTING.md) — how to file an issue or
  propose a change.
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
  `/code-quality-review`.
- [docs/ideas.md](docs/ideas.md) — mid-flight ideas pending a
  user-decision on placement (created on first use).
- [docs/standards/](docs/standards/) — coding, naming, dependencies,
  documentation, testing, commits, versioning (+ roadmap-format).
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
