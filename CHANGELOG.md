# Changelog

All notable changes to finbreak are documented in this
file.

The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Sections use the standard categories — **Added** for new
features, **Changed** for changes in existing behavior,
**Deprecated** for soon-to-be-removed features, **Removed**
for now-removed features, **Fixed** for bug fixes, and
**Security** for security-relevant changes.

The `[Unreleased]` block is required at the top, always —
even if empty. The Roadmap dialog reads it for current-work
signaling per
[`docs/standards/roadmap-format.md § 3.6.2`](docs/standards/roadmap-format.md).

## [Unreleased]

### Added

- **Delete several statements at once, and a Delete all button** (FIBR-0202)
  The Statements tab takes a plural selection too, and a new Delete all clears every recorded import. The warning message states truthfully what the batch will destroy: the obvious way to build it would have said nothing is permanently removed while in fact destroying transactions. Change account still works on one statement at a time, and deleting a single statement reads exactly as it did before.

- **Confirm or reject several suggested transfers at once** (FIBR-0201)
  The Transfers tab's suggested list now takes a plural selection — click rows to tick them in or out, then Confirm or Reject the lot. Trusting eight of twelve suggestions is one click, not eight. If two of the rows you picked share a transaction only one can be confirmed, and the status line now says so rather than quietly reporting a smaller number.

### Changed

- **Importing a statement no longer re-sorts your whole history** (FIBR-0213)
  An import now only categorises the transactions it just added.
  Before, it quietly re-sorted every automatically-categorised transaction in
  the vault — slow on a long history, and it could move numbers you were not
  expecting to change. To re-sort everything on purpose, use "Apply rules now"
  on the Rules tab. Matching itself is also about six times faster.

- **Accented shop names are matched consistently across import and categorisation** (FIBR-0204)
  The same shop name can be spelled two ways behind the scenes depending on
  where a statement came from. finbreak now treats those spellings as
  identical, which mainly matters for spotting duplicate imports and for
  grouping recurring payments. Only affects descriptions with accented
  characters.

### Fixed

- **The Transactions, Statements and Export toolbar buttons now light up on hover** (FIBR-0215)
  Three of the thirteen toolbar buttons were stuck in neutral grey: they
  never brightened under the cursor and never changed shade when you switched
  theme, unlike the other ten.

- **Faint grey text and Ledger's focus outline are easier to see** (FIBR-0214)
  Column headers and unselected tabs were slightly too pale to meet the
  accessibility guideline on three themes, and Ledger's gold focus outline was
  too faint. All four are nudged just enough to pass — you would not spot the
  difference side by side. Links in the release-notes panel now use the theme's
  full accent colour instead of a washed-out tint.

- **The vault locking itself mid-action no longer closes the app** (FIBR-0211)
  Five places read your data a moment after an auto-lock could have
  fired — on the Forecast tab, when deleting a category, and three times on the
  Rules tab. Each now stops quietly, like every other handler, instead of
  letting the error escape.

- **A damaged window settings file no longer stops finbreak from starting** (FIBR-0210)
  Every value read from `window.ini` now falls back to its default
  instead of raising: an empty or non-numeric `last_tab`, and a truncated
  `geometry` / `window_state` / `window_size`. Previously any of these made the
  app unlaunchable until the file was deleted by hand. The same guard was added
  to the saved table-column layouts, where a corrupt entry took down the tab
  being built.

- **Update and Delete on the Accounts tab now grey out when no account is selected** (FIBR-0204)
  They used to stay clickable after the list refreshed, and clicking them
  did nothing at all — no change, no message. Because the form still showed
  the account's details, it looked as though your edit simply had not
  worked. They now grey out, so it is clear you need to pick the account
  again.

- **The import preview now shows which rows are duplicates** (FIBR-0204)
  The preview marked every row "OK" even when the summary said some were
  duplicates, so you could not tell which transactions were about to be
  skipped. Duplicate rows are now labelled as such.

- **Your chosen timezone is no longer reset by saving an unrelated setting** (FIBR-0204)
  If your pinned timezone was one this computer did not list — which can
  happen after moving a vault between machines, since timezone names get
  renamed over the years — opening Settings and saving anything at all
  silently switched you back to the system default, shifting timestamps
  near midnight onto the wrong day.

- **Closing finbreak while it checks for updates no longer crashes it** (FIBR-0204)
  Quitting shortly after startup, or while an update was downloading, could
  end in a crash dialog instead of a clean exit.

- **Refreshing a tab no longer moves which row a button acts on** (FIBR-0204)
  With a table sorted and a row selected, anything that refreshed it — such
  as saving a change in Settings — could quietly move the selection to a
  different row, so a Confirm or Delete acted on something you had not
  chosen. Refreshing now clears the selection instead.

- **A duplicate category name no longer misfiles your spending** (FIBR-0204)
  If you created a category on the Income side with the same name as a
  built-in spending one — an "Insurance" for payouts received, say — the
  built-in shop list started filing your actual insurance payments under
  Income. Your totals stayed right, but the categories did not.

- **A damaged statement file no longer closes the app when you pick it** (FIBR-0204)
  A stray quotation mark in a CSV could make finbreak vanish the moment you
  chose the file, with no message. It now tells you the file cannot be
  read, like any other bad import.

- **A month-end debit order no longer drifts to the 28th in the forecast** (FIBR-0204)
  A payment due on the 31st was projected onto 28 February and then stayed
  on the 28th for every following month — the 29th in a leap year. The
  forecast now returns to month-end the way the bank does: 31st, 28th or
  29th in February, then 31st and 30th again.

- **Selected-row text is now readable on every theme** (FIBR-0204)
  On Ledger, Parchment, Mint and Emerald the highlighted row used near-white
  text on a light accent colour, well below the readable-contrast standard.
  Emerald was the worst. The colour is now chosen by measuring the actual
  contrast, so all six themes pass — no palette had to be redesigned.

- **The Forecast tab no longer says "no known balance" when it has your credit-card statement** (FIBR-0204)
  If the only balance finbreak had was from a credit card, it told you
  there was no balance yet and never mentioned the card — so you would go
  looking for a statement you had already imported. It now names the
  account and explains that only current and savings balances count as
  spendable cash.

- **Two copies of finbreak can no longer open the same vault at once** (FIBR-0204)
  Launching finbreak twice in quick succession — a double-clicked icon, or
  an update relaunch racing a manual start — could leave both copies
  running against the same encrypted file, which nothing else in the app
  guards against. The second copy now steps aside properly.

### Security

- **Backups are harder to attack, and survive a power cut** (FIBR-0212)
  Restoring a maliciously-crafted backup file can no longer make
  finbreak allocate half a gigabyte of memory before you have even logged in.
  Saving a backup now flushes the folder entry to disk, so a power cut straight
  after "Backup saved" cannot leave you with no file at all. And a backup written
  into a shared folder can no longer be hijacked by a file planted there in
  advance.

- **Another user on the same computer can no longer stop finbreak starting** (FIBR-0204)
  finbreak's single-instance marker lived in a shared system folder, so any
  other account could take the name and make finbreak exit silently with no
  window. It now lives in your own private runtime folder.

- **Exported PDF reports are written private to you, and can no longer overwrite another file** (FIBR-0204)
  An exported report — which lists your dates, shops and amounts, and is
  unencrypted unless you set a password — was written readable by other
  accounts on the same computer. It is now owner-only. The temporary file
  it is built through also refuses to follow a symbolic link, so it cannot
  be used to overwrite something else.

## [0.1.19] - 2026-08-02

### Added

- **Forecast and Home dashboard columns are now resizable and remembered** (FIBR-0192)
  The Forecast tab's upcoming-events table can be resized and drag-reordered, and the three Home breakdown lists remember their column widths, like every other table in the app.

- **A "Show account numbers" tick-box on the Accounts tab, with a 30-second auto-hide** (FIBR-0198)
  Account numbers stay masked by default, but you can now read one in
  full when you need it to pay someone — the tick-box reveals every
  account number in the table and in the edit form at once. It hides
  itself again after half a minute, so a number can't be left sitting on
  screen, and the tick never survives a lock or a restart. Note that a
  number you COPY while it's revealed stays on your clipboard until
  something else replaces it.

- **The Accounts tab is now a sortable table of Name, Type, Account number, Note and Status** (FIBR-0113)
  Instead of one cramped line per account, accounts appear as rows you can
  sort, resize and reorder — and finbreak remembers the layout. Clicking
  Status brings the accounts that don't reconcile to the top. The account
  number and note FIBR-0193 added can now be entered and edited on the tab;
  the account number always shows as dots plus its last four digits, on
  screen and in the form, so a glance or a screenshot never gives it away.

- **Each account can now store an optional account number and a free-text note** (FIBR-0193)
  Storage only — both fields live in the encrypted vault behind schema
  migration v13, and nothing displays or edits them yet (the Accounts
  screen that does is FIBR-0113). A blank field is stored as SQL NULL
  rather than an empty string, and an existing vault upgrades in place
  with every account row untouched.

### Changed

- **The dashboard scrolls instead of squashing when the window is too small** (FIBR-0186)
  The dashboard content now has a minimum readable size. Shrink the window
  below it and the page scrolls; the three breakdown columns keep a width you
  can actually read rather than compressing into slivers. It is a minimum, not
  a fixed size, so a larger system font or display scaling still grows the
  layout rather than clipping text.

- **Alerts moved off the dashboard into an Alerts button + dialog** (FIBR-0185)
  The Home dashboard no longer carries an alerts card whose height grew and
  shrank with the number of open alerts, shoving everything below it up and
  down the page. Alerts now live behind an "Alerts (4)" button on the
  dashboard's top row, which opens a dialog listing each one with its own
  dismiss control. The button fills with the active theme's attention colour
  while something is outstanding and sits quiet and disabled when nothing is —
  each of the six themes carries its own attention colour, so it stays legible
  in all of them. Dismissals persist exactly as before.

- **Only one copy of finbreak runs at a time — launching it again brings the open window to the front.** (FIBR-0189)
  Starting finbreak when it's already running no longer opens a second
  copy; it raises the window you already have, restoring it if it was
  minimised. This also keeps two copies from writing to your vault at once.

### Fixed

- **Reset layout now resets column widths and order too** (FIBR-0192)
  Window → Reset layout put the window back to its default size but left every table's columns exactly as you had dragged them. It now returns them to how they looked on a fresh install, in the same click, without needing a restart.

- **Running the AppImage no longer puts a duplicate finbreak icon in the taskbar.** (FIBR-0188)
  The AppImage's launcher had a different name from the one the window
  announces, so your desktop treated them as two separate things. Takes
  effect from the next release's AppImage — an already-downloaded copy keeps
  the old launcher.

- **The import preview table now remembers your column widths between imports.** (FIBR-0187)
  Widen a column while checking an import and it stays that way next time,
  like every other table in the app. You can also drag its columns into the
  order you prefer.

## [0.1.18] - 2026-07-28

### Added

- **Spending alerts — flag unusual spend, a newly-appeared recurring charge, or a missed expected debit.** (FIBR-0172)
  A quiet, dismissable alerts card on the Home dashboard: a new recurring
  charge that just appeared, a spending category well above its recent
  average, or an expected debit that didn't post. Each alert is
  dismissable and the dismissal sticks. Computed from data the app already
  holds (recurring detection + reporting); one small new dismissals table.

- **Account-level balance reconciliation — verify imported transactions sum to the bank's stated balance for every account.** (FIBR-0177)
  Per-account reconciliation marker on the Accounts tab (✓ balances
  reconcile / ⚠ off by …) for current & savings accounts, checking that
  imported transactions bridge each statement's closing balance to the
  next. Bank-agnostic, no new stored data, no schema change.

- **A new Forecast tab projects your balance forward from confirmed recurring income and expenses.** (FIBR-0171)
  The forecast starts from a real, current balance — each imported
  statement's closing balance, brought up to date with the transactions
  imported since — and draws a projected-balance line to a chosen horizon
  (end of this month, 30, 60 or 90 days). When no statement has recorded a
  balance yet, it honestly shows the projected net change from zero instead
  of a made-up balance. A provenance line names each account and statement
  the starting figure came from.

### Changed

- **The update prompt now shows what changed in every release you skipped, not just the newest one.** (FIBR-0152)
  If you were three versions behind, "What's new" only described the
  newest release. It now lists each release between your version and the
  one on offer, newest first. The check reads the release list from the
  same GitHub endpoint it already used — no new network surface — and if
  that read fails you simply get the single set of notes as before.

- **The update download now shows real progress instead of a permanently-full striped bar** (FIBR-0108)
  The "Downloading…" bar fills up as the update arrives. If the server
  doesn't say how big the file is, the bar keeps its old busy look rather
  than guessing.

- **The Forecast tab's "excluded accounts" note now states the rule positively — "only current and savings balances are spendable cash".**
  It used to list "credit, loan and investment", which quietly left out
  accounts of type "other" — they were excluded from the forecast anchor
  too, but the note never said why. (Debt sweep DS02.)

### Fixed

- **Forecast starting balance no longer counts credit-card and loan debt as cash** (FIBR-0179)
  A statement for a credit card or loan prints its closing balance as
  the amount you OWE, the opposite sign to the way finbreak stores
  transactions. The Forecast tab was adding that owed figure into your
  projected balance as though it were money you have, and any card
  purchase since the statement moved it the wrong way. The forecast now
  anchors on cash accounts only (current and savings); every other
  account type — debt, investment, and "other" — is listed as
  excluded, with the reason. If a
  debt account is the only one with a recorded balance, the forecast
  honestly shows a projected change from zero instead.

- **The Recurring and Transfers tabs now show amounts with the currency symbol and thousands grouping (e.g. “R 1,234.50”), matching the rest of the app.** (FIBR-0168)

- **CSV import no longer crashes on a corrupt or truncated file — it now reports a friendly “not valid CSV” message.** (FIBR-0165)

### Security

- **Updates install the exact bytes that passed the signature check** (FIBR-0170)
  The verified download is now re-written from memory immediately before
  install, instead of handing over the file it had been read from — closing
  a window in which the payload could have been swapped on disk.

- **The Argon2id acceptance floor is now separate from the vault-creation parameter, so a future increase in password-hashing strength cannot lock existing vaults out.** (FIBR-0166)

- **The auto-update check now enforces HTTPS on redirects, not just the first request, so it cannot be silently downgraded to plaintext.** (FIBR-0167)

## [0.1.17] - 2026-07-23

### Added

- **Flatpak packaging for Flathub — the cross-distro Linux app store** (FIBR-0159)
  finbreak can now be built as a Flatpak and submitted to Flathub — the
  app store that shows up in GNOME Software and KDE Discover on every
  Linux distro — so you'll be able to search "finbreak" and install it
  with one click, whichever distro you run. The Flatpak runs strongly
  sandboxed for the finance-security story: it has no network access at
  all, and can only touch a file after you pick it in the open/save
  dialog (nothing else on your computer is visible to it). This adds the
  build manifest and recipe; the live Flathub listing follows once the
  submission is merged.

- **Native Linux packaging (RPM + deb) via the openSUSE Build Service** (FIBR-0155)
  finbreak can now be published as a proper native package for openSUSE, Fedora, Debian and Ubuntu — installed and updated the normal way for your distro (zypper/dnf/apt) and listed with its icon in the software centre, alongside the existing AppImage. The package bundles its own tested runtime, so it runs the exact same encryption stack regardless of what your distro ships. (This adds the build recipes and desktop/store metadata; the first live build is published from the maintainer's OBS account.)

- **A "Report an Issue" item in the menu bar (right of Donate) that opens the project's issue page in your browser** (FIBR-0156)
  One click opens finbreak's GitHub issue form so you can quickly report a bug or request a feature — no data leaves the app (it just hands the page to your browser, exactly like the Donate links).

- **Categories can now be organised three levels deep (Type › Category › Sub-category)** (FIBR-0154)
  Add a sub-category under an existing category (e.g. Expenditure › Groceries › Spar) directly in the Categories tab: select the parent, type the name, click Add. Renaming, moving (via "Move under…"), and deleting work at every level. Where two sub-categories share a name (Groceries › Spar and Fuel › Spar), the category pickers now show the parent so you can tell them apart. The app keeps the depth at three levels.

- **Per-release signed `SHA256SUMS` checksum manifest + per-platform CycloneDX SBOM** (FIBR-0096)
  Each release now publishes a signed SHA256SUMS manifest (verify manually with `sha256sum -c --ignore-missing SHA256SUMS`, its `.sig` Ed25519-signed by the release key) and a per-platform CycloneDX SBOM of the bundled runtime dependencies — a second, independently-verifiable integrity signal and a supply-chain parts-list, complementary to the per-artifact signature the in-app updater already checks.

- **"Forgot password? Start over" — a last-resort, double-confirmed destructive vault reset on the unlock screen** (FIBR-0030)
  For a genuinely forgotten master password with no usable backup, the unlock screen now offers "Start over": after a clear irreversible-warning and a second step where you type DELETE, it permanently erases the vault and returns you to first-run setup so you can begin fresh. The old data was already unrecoverable without the password; nothing that could be recovered is lost. The reset removes the vault's complete on-disk footprint (database, key file, and SQLite's working sidecars), and clears the old lockout/hint state, leaving your app preferences untouched.

- **Verify a backup is restorable, from Settings** (FIBR-0033)
  A new "Verify backup…" button in Settings opens a backup file (.fbk) and
  checks it read-only — confirming the password is right, the data isn't
  corrupted, and the version is one this app can restore — and shows a short
  summary (schema version and how many transactions, etc.). It never touches
  your live data. Now you can confirm a backup is good *before* you ever have
  to rely on it.

### Fixed

- **Amounts now show the currency symbol ("R 1,234.49"), with a tidy Currency column** (FIBR-0153)
  Money used to display as "ZAR1,234.49" — the currency code jammed onto
  the number with no space. It now shows the proper symbol and a space,
  like "R 1,234.49", and the "ZAR" code moves into its own dedicated
  Currency column on the Transactions table. The grouping and decimal
  style still follow your system's locale. This applies everywhere amounts
  appear — the transactions list, the Home dashboard, and PDF exports.

- **Confirmed transfers now show on the Transactions tab** (FIBR-0151)
  A transfer you've confirmed now appears in the Transactions tab's
  Category column as a directional label naming the other account — the
  money-out leg reads "Transfer to <account>" and the money-in leg reads
  "Transfer from <account>". Previously a confirmed transfer left both
  rows blank there.

### Security

- **Optional password hint on the unlock screen** (FIBR-0029)
  You can now set an optional hint to jog your memory, shown behind a
  "Show hint" button on the unlock screen. You set it in Settings and must
  confirm your current password to do so. The app refuses a hint that is,
  or contains, your password — so it can't become a plaintext copy of your
  secret. Note the hint is stored unencrypted (it has to be readable before
  you unlock), so anyone with access to your device can read it — keep it
  vague. It's a memory aid, not a way to recover a truly forgotten
  password.

- **Copy a transaction's amount or description — and it auto-clears from the clipboard** (FIBR-0032)
  Right-click a transaction and pick "Copy amount" or "Copy description" to
  put it on the clipboard. finbreak then wipes it after a short timeout
  (default 30 seconds, adjustable in Settings — or "Never" if you prefer) so
  it doesn't linger for other apps to read. It only clears the value if the
  clipboard still holds what finbreak put there, so anything you copied since
  is left alone. Your saved statement-PDF password and account numbers stay
  non-copyable by design.

- **Unlock throttling — repeated wrong master-password attempts are now slowed. (FIBR-0095)**
  After a wrong password on the unlock screen, finbreak now waits a
  growing moment before accepting the next try (1s, then 2s, 4s, … up to
  30s), and remembers the count so closing and reopening the app doesn't
  reset it. This is extra protection against someone repeatedly guessing
  your master password through the app; a correct password always clears
  it, so you're never locked out of your own vault.

## [0.1.16] - 2026-07-18

### Fixed

- **OFX import now files each transaction under the date the bank printed.** (FIBR-0042)
  A timezone-stamped OFX date (e.g. an evening transaction in a UTC-5 zone)
  was being shifted to UTC, which could file it under the next day — and, at
  a month boundary, under the wrong statement. Dates are now kept exactly as
  posted on the statement.

- **Delete-statement confirmation no longer over-states the loss on an overlap.** (FIBR-0149)
  When you delete a statement that shares transactions with another one you keep,
  the confirm dialog previously counted all of the statement's transactions and
  warned "this cannot be undone" — even though the shared ones now survive under
  the overlapping statement. It now names the actual number that will be removed
  (often 0) and reassures that the shared rows stay.

- **Deleting a statement no longer loses transactions another overlapping statement still covers** (FIBR-0148)
  If two of your statements' periods overlapped (say a monthly statement and a
  quarterly one covering the same weeks), deleting one used to silently delete the
  transactions they shared — even though the statement you kept still covered them.
  Now those shared transactions are handed over to the statement you keep, and only
  transactions nothing else accounts for are removed.

## [0.1.15] - 2026-07-17

### Changed

- **finbreak stays fast and responsive as your transaction history grows (FIBR-0098/0071/0026/0025)**
  The vault now keeps quick-lookup indexes on the columns finbreak searches
  most (dates, accounts, categories, statement periods, and the duplicate-check
  key), so listing, filtering, importing, and de-duplicating stay fast even on a
  multi-year vault instead of slowing down as rows pile up. The database also
  switches to a faster write mode (WAL) so the screen stays responsive while a
  large statement imports. Existing vaults gain the speed-ups automatically the
  next time you unlock them; your data is untouched.

### Fixed

- **Category tree can no longer loop back on itself.** (FIBR-0141)
  Editing a category to sit under itself or one of its own sub-categories
  is now refused with a clear message, instead of silently creating a loop
  that could confuse the parts of the app that walk the category tree.

- **PDF/CSV statement import no longer fails every row when the bank's date layout isn't ISO (FIBR-0146)**
  The import wizard used to ask for the date layout as a raw programmer code
  (%Y-%m-%d), so a statement printed day-first (or any other layout) failed every
  row with a wall of cryptic "time data … does not match format" text. finbreak
  now reads the actual dates, guesses the layout, and offers a plain-English
  picker (with a "Custom…" escape hatch) plus a live "Dates read as: …" preview —
  so the common case just works and a wrong guess is caught before import, never a
  silent wrong-day. When a row still can't be read it shows a friendly message
  naming the value, and a whole-import banner points you at the date control when
  nothing lands. Reported by an external Windows tester (165-row all-error import).

## [0.1.14] - 2026-07-16

### Changed

- **Reworked the Home dashboard so the breakdown is the primary surface (FIBR-0143)**
  The Income / Spending / Transfers breakdown is now the hero: three
  side-by-side columns, each with its own pie, a coloured heading with the
  big total, and an expandable drill-down. A slim Net strip sits above; a
  recurring-money card and the monthly-trend chart (demoted to a bottom
  strip) sit below. No money figure changes — the same integer-exact
  aggregations, only rearranged on screen.

## [0.1.13] - 2026-07-15

### Added

- **Recurring-money detection (FIBR-0142) — a new Recurring tab that spots subscriptions and regular income** (FIBR-0142)
  finbreak now scans your history and suggests recurring charges and
  income (weekly / fortnightly / monthly / yearly), which you Confirm or
  Dismiss. Confirmed transfers are excluded, and one merchant's charges
  across several accounts group into a single item. Amounts stay
  exact-integer (money-safe); the per-month equivalents feed a summary the
  upcoming dashboard card will show.

## [0.1.12] - 2026-07-14

### Added

- **Expandable dashboard drill-down — open the Income / Spending / Transfers totals into categories, shops, and individual transactions (FIBR-0138).**
  The Home dashboard's three headline numbers are now openable, in a tree
  below the donut and trend charts. Click Spending to break it into your
  categories, open a category down to a single one, then see the
  transactions grouped by shop with a count (e.g. "Woolworths ×3"), and
  open a shop to see each purchase (date + amount). Income opens the same
  way; Transfers opens by account pair (e.g. "Current → Savings ×2"). Every
  figure is still summed from the real stored amounts — the shop grouping
  only decides which line a transaction sits under, never how much it is.

## [0.1.11] - 2026-07-14

### Added

- **Built-in category library — common merchants are now auto-categorised out of the box (FIBR-0139).**
  A bundled, per-release merchant library guesses categories for new transactions, so a fresh vault no longer imports everything Uncategorised. It runs after your own rules and only on rows you haven't set by hand, so your rules and manual picks always win. Guessed rows show a small "~ guess" tag you can override with a click, and a Settings toggle (on by default) turns the whole thing off.

## [0.1.10] - 2026-07-14

### Added

- **Forget a remembered bank-statement password, per account.** (FIBR-0128)
  The Accounts screen now marks each account whose locked-PDF statement
  password the app remembered while importing, and adds a "Forget statement
  password" button to clear it. The password itself is never shown — you only
  see which accounts have one saved.

- **Themes — six finance-flavoured looks plus "Follow system", with a sleeker design.** (FIBR-0127)
  Settings → Theme now offers six looks (three light — Ledger, Parchment, Mint;
  three dark — Midnight, Graphite, Emerald) or "Follow system", which tracks your
  computer's light/dark setting and switches instantly when it changes. Picking a
  theme applies it straight away — no Save needed. The whole app got a modern
  polish pass: soft gradient/glow accents on buttons and fields, and highlighted
  rows (hover, selection, and alternating stripes) in the tables. The toolbar icons
  re-colour themselves to suit the chosen theme. Your choice is remembered and
  applies from the moment the app opens, even before you unlock.

- **Windows in-app auto-update — the Windows app now offers, verifies, and installs a new version, then reopens itself, matching the Linux AppImage.** (FIBR-0131)
  Opt-in and off by default, like on Linux. Each download is checked against
  finbreak's own signature before anything runs. Because a running Windows program
  can't overwrite its own file, a tiny helper waits for finbreak to close, swaps in
  the new version, and reopens it. (Windows may still show a one-time "unknown
  publisher" notice until the separate code-signing step lands.)

- **Auto-lock can now be set to "Never" — the app won't lock itself while idle.**
  Settings → Auto-lock after → Never disables the idle timer. The password is still required when you open the app, and you can still lock any time with the Lock button (FIBR-0135).

### Changed

- **The About box shows the version on its own line, above the tagline.**
  A small readability tweak — "finbreak 0.1.10" on the first line, then
  "A private, offline personal-finance vault." beneath it.

### Fixed

- **Statements now has a toolbar button with an icon (was reachable only from the View menu).**
  Added a Statements glyph to the toolbar, placed after Transactions to match the tab order (FIBR-0136).

- **Auto-update: a download that fails after an idle auto-lock no longer disrupts the lock screen.**
  If the vault auto-locked while an update was downloading and the download then failed, the app would close the re-opened unlock prompt and show a stray "Update failed" box over the lock screen. The failure handler now stays silent once its prompt is gone (FIBR-0054 close).

- **Embed the finbreak icon in the Windows .exe (was PyInstaller's default console-stub icon).** (FIBR-0134)
  Make the Windows app file show finbreak's donut icon in Explorer instead of a generic black terminal icon.

- **Windows: the app no longer flashes a console (command-prompt) window on launch.** (FIBR-0132)
  The Windows `.exe` is now frozen as a GUI app (`--windowed`) instead of a
  console app, so no black cmd window appears before the window opens.

## [0.1.9] - 2026-07-13

### Added

- **Windows build (testing) — a self-contained `finbreak.exe`.** (FIBR-0015)
  finbreak can now be packaged into a single Windows `.exe` (no Python needed) by
  the on-demand `windows-build` CI workflow, so friends can test it on Windows.
  The SQLCipher vault engine moved to a cross-platform wheel (`sqlcipher3-wheels`,
  the same SQLCipher 4.12.0), so your existing vaults and backups open unchanged.
  The `.exe` is **unsigned** for now — Windows SmartScreen may warn ("More info →
  Run anyway") — and there is **no auto-update on Windows** yet (replace the old
  `.exe` to update).

- **Encrypted backup export & restore — save a portable, password-protected `.fbk` backup of your vault and restore it later.** (FIBR-0014)
  Export a `.fbk` from Settings, keyed by a **separate backup password** you
  choose. If you ever forget your master password, restore the backup from the
  unlock or first-run screen with the backup password plus a **new** master
  password — you never need the old one. The backup is fully encrypted (AES-256);
  restoring an existing vault moves the old one safely aside rather than deleting
  it.

- **Export a password-protected PDF report (FIBR-0013).** (FIBR-0013)
  File → Export report as PDF… (and the toolbar) opens a dialog to choose which
  sections to include (summary / charts / transactions), the period, and which
  accounts (all or a chosen subset — with combined totals plus a per-account
  summary line). Optionally set a password to AES-256-lock the file so only you can
  open it; leave it blank for a normal unencrypted PDF. Pick a Light or Dark theme.
  Confirmed internal transfers are excluded from the summary and charts but shown
  and marked in the transaction list.

### Changed

- **Category pickers now group by Income / Expenditure type.** (FIBR-0123)
  The Set-category and Rule dialogs and the Transactions category
  filter now list categories under non-selectable Income /
  Expenditure headers and tag every row "Name (Type)", so two
  same-named categories under different Types (e.g. an income vs an
  expenditure "Lottery") are distinguishable both in the open
  dropdown and the collapsed box.

## [0.1.8] - 2026-07-13

### Added

- **Reporting dashboard + Transactions tab (P10, FIBR-0012).**
  The Home screen is now a dashboard: an income-vs-spending summary for a chosen
  period (defaults to last month and remembers your choice — current/previous month,
  a specific month, year-to-date, or a specific year), a donut of where your money
  went by category, and a 12-month income-vs-spending trend chart. Money moved between
  your own accounts (confirmed transfers) never counts as income or spending. The
  transaction list moves to its own Transactions tab where you can search by
  description and filter by date range, account, and category — any or all at once.

- **Data tables: drag-to-reorder columns, with the order persisted across sessions.** (FIBR-0120)
  You can now drag a table's column headings to rearrange them (e.g. put Amount before Date), and the app remembers your arrangement next time — on the Transactions, Statements, Rules and Transfers tables.

### Fixed

- **Auto-update now reliably reopens the app after installing (FIBR-0122).**
  The helper that relaunches finbreak after an update was inheriting the packaged
  app's private library path, so the system shell tried to load the app's bundled
  libraries, failed, and never reopened the app. It now runs with the system
  libraries. (The version performing the relaunch is the one you're updating *from*,
  so one more manual reopen is expected on the very next update; the update after
  that reopens on its own.)

- **Home Loan statement import no longer glues the page footer (bank address, phone/fax, column headers) onto a transaction's description.** (FIBR-0119)

## [0.1.7] - 2026-07-12

### Added

- **Data tables now sort on a column click and remember your column widths.** (FIBR-0117)
  Click a column heading (Statements, Transfers, Home) to sort by it; click the same heading again to flip between ascending and descending. Amounts and dates sort by their real value, not as text (so 112 no longer sorts before 69). Each table also remembers how wide you've dragged its columns and which column you last sorted by, restoring them next time you open the app. The Rules table stays in its priority order (that order is what it means) but likewise remembers its column widths.

- **Transfers tab — finbreak now spots money you move between your own accounts and asks you to confirm it.** (FIBR-0011)
  Moving money between your own accounts — paying a credit card from your current account, shifting cash to savings — shows up as two lines: money out of one account and the same amount into another. finbreak now finds these matched pairs and lists them under a new **Transfers** tab, where you Confirm or Reject each one. Only pairs you confirm stop counting as spending or income; nothing is hidden without your say-so, and rejected pairs are remembered so they aren't offered again. (This is the foundation the upcoming spending dashboard needs so a transfer to savings isn't double-counted as both income and expenditure.)

### Changed

- **The toolbar icons now have gentle colour that brightens when you hover over them.** (FIBR-0116)
  Each toolbar button used to be a flat grey glyph. Every icon now has its own soft, muted colour at rest and lights up to a vibrant version when you move the mouse over it, dimming back when you move away. The colours are chosen to suit your current light or dark theme.

- **The app icon now has softly rounded, transparent corners instead of a hard square tile.** (FIBR-0118)
  In the About box, taskbar, and app launcher the icon showed as a solid square block. Its corners are now transparent (a gently rounded tile), so it sits cleanly on any background.

### Fixed

- **Auto-lock now resets on activity (inactivity timer), so it no longer locks mid-use.** (FIBR-0114)
  The screen auto-lock counted a fixed time from unlock, ignoring whether you were actively using the app — so it could lock while you were mid-task. It is now an inactivity timer: the countdown restarts on every mouse/keyboard interaction and only fires after that many minutes of genuine idleness.

- **Credit-card statements whose transactions continue onto a page without a repeated column header no longer fail to import.** (FIBR-0112)
  A multi-page Standard Bank credit-card statement can carry its transaction table onto a final page that does not reprint the "Date Description Amount" column header. Those rows were silently dropped, so the statement failed its completeness check ("this statement didn't add up") and was refused. The importer now recognises a header-less continuation page and captures its transactions.

## [0.1.6] - 2026-07-12

### Fixed

- **After installing an update, finbreak now reliably reopens itself.** (FIBR-0054)
  Previously the app could close after updating without coming back — it tried to
  start the new version before the old one had fully shut down, and the new copy
  died in the collision. It now waits for the old version to exit completely, then
  launches the new one, and records a small diagnostic log so any future hiccup
  leaves a trace. (Note: because the fix lives in the update machinery, it only
  takes effect from the NEXT update after this one — the update into this version
  may still need one manual reopen.)

- **Credit-card statements that open in credit now import correctly.** (FIBR-0106)
  Some Standard Bank credit-card statements print a plain-English sentence
  mentioning the "balance brought forward" before the real opening-balance row.
  finbreak was reading the figure from that sentence (which is actually the
  closing amount), so the statement failed to import with "this statement didn't
  add up." It now reads the true opening balance and imports as expected.

## [0.1.5] - 2026-07-11

### Added

- **You can now choose how negative amounts look.** (FIBR-0105)
  In **Settings** (and when first creating your vault) there are two new
  options for the Home amount column: show money-out either with a **minus
  sign** (`-25,000.00`) or in **accounting brackets** (`(25,000.00)`), and
  turn **red/green colouring** on or off (money out in red, money in green).
  The friendly default is minus with colour on; brackets are there so anyone
  used to accounting statements keeps the familiar look. It's display-only —
  your stored amounts never change — and switching either option updates the
  open Home tab straight away.

### Changed

- **The update prompt now shows "what's new" inline.** (FIBR-0054)
  The "a new version is available" box now shows the release notes right
  there in the window (a short, scrollable panel), instead of a "What's new"
  button that opened the release page in your browser. No extra internet
  access — the notes already come with the update information finbreak
  downloads.

## [0.1.4] - 2026-07-11

### Fixed

- **The app now reopens itself after installing an update.** (FIBR-0054)
  Previously, after an update installed, finbreak closed but did not
  relaunch — you had to reopen it manually. The relaunch now spawns a fresh,
  detached copy of the updated app (with the PyInstaller restart signal set)
  and exits the old one, instead of re-executing in place, which could not
  replace the still-mounted AppImage. Note: because the *old* running version
  performs the relaunch, this fix takes effect from the first updated build
  onward — the update that installs this fix is the last one that won't
  auto-reopen.

## [0.1.3] - 2026-07-11

### Added

- **Choose your time zone and date/time format (Settings + first-run).** (FIBR-0083)
  Statement timestamps (the "Imported" column) now show in your own time
  zone instead of a raw UTC value, and you can pick how dates and times are
  written (e.g. 2026/07/11 vs 11 July 2026, 24-hour vs 2:30 PM). Set it in
  Settings or when first creating your vault; leave it on "System default" and
  finbreak follows your computer's settings automatically. Changes apply
  immediately — no restart. (Subsumes FIBR-0048.)

## [0.1.2] - 2026-07-11

### Fixed

- **The update check now works on every Linux distribution.** On v0.1.0/v0.1.1
  the "check for updates" step could silently do nothing — no prompt ever
  appeared — on any distro whose system security-certificate location differs
  from the one the app was built on. finbreak now ships its own trusted
  certificate set and uses it directly, so checking for and installing updates
  works regardless of where your distro keeps its certificates.
- **The Rules button on the toolbar now has an icon** (it was text-only).

### Added

- **Help → Check for updates…** — check for a new version on demand, with a
  clear result every time (an update is offered, you're up to date, or it
  couldn't reach the internet). Works even if automatic update checks are turned
  off — clicking it is your go-ahead for that one check.

## [0.1.1] - 2026-07-11

### Changed

- **The About box now shows the running version** (e.g. "finbreak 0.1.1 — …"),
  so you can tell at a glance which build you're on — and confirm an update
  actually took effect.

## [0.1.0] - 2026-07-11

First public release — an early preview. Establishes the signed update
channel (opt-in, off by default) and ships the working core: an encrypted
vault, CSV/OFX/PDF statement import, accounts, a category tree, and
auto-categorisation.

### Added

- **Automatic categorising — finbreak sorts your transactions into categories for you.** (FIBR-0010)
  Rules run on import and on an explicit "Apply rules now". Correct an
  auto-filed transaction and finbreak offers to make a rule. A new Rules
  tab manages the rule list; the Home table gains a Category column and a
  right-click "Set category…". Deleting a category re-files its
  transactions and removes the rules that pointed at it, after a
  confirmation that names the blast radius. Encrypted-vault schema v6 → v7.

- **Change a logged statement's account — the Statements tab can now move a statement (and all its transactions) to the correct account, fixing an import mistake without deleting and re-importing (FIBR-0059).**
  Select a statement, click "Change account", pick the right account, and the
  statement plus every transaction it contains move there together — all-or-
  nothing. If the target account already has a statement for the same period, the
  move is refused with an explanation (rather than silently duplicating rows). This
  is also the tool for fixing anything mis-linked before the import-time fix
  (FIBR-0057) shipped.

- **A proper branded app icon.** (FIBR-0037)
  finbreak now has a real app icon — a colourful "spending by category" donut chart with a gold coin in the middle — instead of no icon. You'll see it on the window, in your taskbar, and (once installers are built) as the app's icon on Windows, macOS and Linux.

- **Settings screen — a Settings menu item whose first control is a user-configurable auto-lock timeout, plus core preferences.** (FIBR-0055)
  A new File → Settings… screen. Its first control lets you choose how long finbreak waits before it auto-locks when you step away (1, 5, 10, 15 or 30 minutes — it used to be a fixed 10). The choice takes effect immediately and is remembered (stored inside your encrypted vault). The screen also shows your vault's base currency. No database change.

- **A tabbed main window, and a Statements tab that lists your imports and lets you delete one (with all its transactions).** (FIBR-0052)
  The main window is now tabs — Home · Statements · Accounts ·
  Categories — with a Home button on the toolbar, and it remembers its
  size, position and last tab between runs (plus Center-window and
  Reset-layout actions). The new Statements tab shows every statement
  you've imported with an exact transaction count, and lets you delete a
  statement and all of its transactions in one step (with a confirmation;
  your manually-added transactions are left untouched). To count and
  delete safely, finbreak now tags each imported transaction with the
  statement it came from — a small automatic database upgrade, including a
  one-time tidy-up for statements imported before this version.

- **A proper app window — menus, a toolbar, and a status bar.** (FIBR-0051)
  finbreak went from a bare password box and form to a real desktop-app window: a menu bar, a toolbar of shortcuts, a status bar, and a friendly first-run setup pop-up — so it looks and feels like a real desktop app.

- **Import your Standard Bank statements directly — cheque, savings, home loan, personal loan, credit card and money-market.** (FIBR-0050)
  Standard Bank's real statements don't survive the generic PDF
  table-reader — a cheque statement collapses into a single cell, and
  the credit card's two-columns-per-page layout is unreadable. finbreak
  now recognises a Standard Bank statement and reads the printed lines
  the way you do, so all six of your account types import cleanly and
  skip straight to the preview (no column-mapping needed, like OFX).
  Money out shows negative, money in positive; it copes with both the
  1,427.41 and the 239.206,04 number styles, works out the year from
  the statement period, and every statement is cross-checked against its
  own running balance and printed closing figure — if the numbers don't
  add up it declines the whole import and points you to your bank's CSV
  or OFX export rather than importing something wrong. Locked statements
  are unlocked in memory only (never written to disk), and nothing about
  your statement leaves your computer.

- **Import transactions from a PDF bank statement — including password-locked ones.** (FIBR-0009)
  Many banks only give you a PDF. finbreak now reads the transaction
  table straight off the page: pick a `.pdf` and it lifts the rows out,
  then hands you the same familiar column-mapping and preview screens as a
  CSV import (so a bank layout you map once is remembered for next time).
  If the statement is **password-protected**, finbreak asks for the
  password and unlocks it **entirely in memory — the unlocked file is
  never written to your disk** — and you can tick "remember this password
  for this account" (off by default) so it's stored, encrypted, inside
  your vault; a wrong password just asks again instead of giving up. If a
  statement holds more than one table (say a summary and the transactions),
  you're shown a small chooser to pick the right one. It flows through the
  exact same machinery as CSV and OFX, so re-importing a statement adds no
  duplicates and the money stays exact to the cent. Statements printed as
  free-flowing text (no ruled table) or scanned images aren't supported yet
  — finbreak tells you to try your bank's CSV or OFX export instead.

- **Import transactions from an OFX bank file.** OFX (Open Financial Exchange)
  is the standard format almost every bank offers as a download. Because it
  describes itself — the dates, amounts, descriptions, and the statement's date
  range are all built into the format — finbreak needs **no column-mapping step**
  for it: pick an `.ofx`/`.qfx` file and you go straight to the same **preview**
  (every row, the "N new · M duplicate · K error" tally, the statement dates
  filled in for you) as a CSV import, then Import. It flows through the exact
  same machinery as CSV, so re-importing a statement you already loaded adds **no
  duplicates**, an OFX row that matches one you typed by hand is recognised as
  the same, and a row it can't read is listed rather than dropped. A file that
  covers **more than one account** (say a bank account plus a credit card) shows
  a small chooser so you pick which one to import; a "quiet month" with a real
  date range but no transactions still records its coverage. Money stays exact
  whole-cent amounts throughout (never a lossy decimal), and an over-large or
  over-long file is refused up front. No change to your existing data — OFX
  reuses the same storage the CSV import added. (FIBR-0008)

- **Import transactions from a bank-statement CSV file.** Instead of typing
  every transaction by hand, point finbreak at a CSV your bank gives you and it
  reads the transactions in. Because every bank lays its CSV out differently,
  you tell finbreak once which columns are the date, the description, and the
  amount (or separate "money out" / "money in" columns) — it remembers that as
  a named layout and recognises the same bank's file automatically next time.
  Before anything is saved you see a **preview**: every row, a
  "N new · M duplicate · K error" tally, and the statement's date range (filled
  in for you). Re-importing a statement you already loaded — even an overlapping
  one — adds **no duplicates**, while genuinely identical repeats (two of the
  same coffee on the same day) are kept the first time. Rows it can't read (a
  bad date, a non-number amount) are listed, not silently dropped, and the good
  rows still import. Opening a vault from before this release upgrades it in one
  all-or-nothing step that adds the import bookkeeping, rolling back cleanly on
  a power-cut. (FIBR-0007)

- **Categories — sort your money into Income and Expenditure buckets.**
  finbreak now has a two-level category list: two fixed types — Income and
  Expenditure — each holding a set of ready-made categories (Salary, Sales,
  Bills & utilities, Groceries, Medical, and more; sixteen come built in). A new
  "Manage categories…" screen lets you add your own, rename them, move one to
  the other type, or delete the ones you don't use. The list is stored so a
  future "sub-category" level can be added later without rebuilding your data.
  (Actually tagging each transaction with a category comes in a later release —
  this release builds the list itself.) Opening a vault from before this release
  upgrades it in one all-or-nothing step that adds the category list, and a
  power-cut mid-upgrade rolls back cleanly to the old shape. (FIBR-0006)

- **Multiple accounts — keep each account's money separate.** Create as many
  accounts as you like, each tagged with a type (current, savings, credit card,
  personal loan, home loan, investment, or other); rename or retype them on a
  new "Manage accounts…" screen; and choose which account each transaction
  belongs to (shown as its own column in the table). Deleting is guarded so you
  can't lose data: an account that still holds transactions can't be removed
  (it asks you to clear them first), and you can never delete your last
  account. Opening a vault from before this release upgrades it in one
  all-or-nothing step — it creates a "Default" account and moves every existing
  transaction into it, and a power-cut mid-upgrade rolls back cleanly to the
  old shape rather than leaving a half-changed file. (FIBR-0005)

- **The security spine — set a master password, keep encrypted transactions,
  lock it away.** First run sets a master password + base currency and creates
  an encrypted vault; you can add a transaction (kept as exact whole-cent
  amounts, never a lossy decimal) and see it in a table, then Lock to wipe the
  key and return to the unlock screen. A wrong password or a tampered file is
  refused cleanly. Amounts show in your base currency; the slow password-to-key
  work runs off the UI thread so the window never freezes; the vault
  auto-locks after 10 minutes idle. (FIBR-0004)

- Development quality + security gate: a single command,
  `scripts/ci-local.sh`, runs ruff (lint + format-check), bandit,
  pip-audit, gitleaks, and pytest, cheapest-first, failing on the first
  bad stage. `.github/workflows/ci.yml` runs the identical stages by
  invoking that same script (one source of truth), so local and CI runs
  cannot drift. Ships the `pyproject.toml` toolchain (exact-pinned dev
  group), the `.gitleaks.toml` scan config, and a placeholder `finbreak`
  package with a smoke test. (FIBR-0001)

- **Bundling smoke-test — proves the native stacks travel into a
  Python-free download.** A permanent `python -m finbreak --self-test`
  diagnostic loads all three native stacks (Qt via PySide6, the SQLCipher
  encrypted DB, and qpdf behind pikepdf) and prints a sentinel;
  `scripts/build-smoke.sh` freezes it into a PyInstaller onefile **and** an
  AppImage inside a `python:3.12-slim-bookworm` container (glibc floor
  ~2.36) and launches each in a Python-free `debian:13-slim` clean-room,
  proving ADR-0007's clean-machine exit criterion in miniature. Adds the
  first pinned runtime deps (`PySide6`, `sqlcipher3-binary`, `pikepdf`) and
  a `build` group (`pyinstaller`); the slow build is opt-in
  (`ci-local.sh --build`) with a dedicated weekly CI job, so the everyday
  gate stays fast. (FIBR-0003)

### Changed

- **Standard Bank PDF import now also reads amounts printed without thousands separators (e.g. 1234.56), not just grouped ones (1,234.56) — validated against all six real statement families with no change to their results.** (FIBR-0067)

- **An oversized Standard Bank PDF is now rejected before the heavy parsing runs, not after, so a deliberately huge file can't burn work before being turned away.** (FIBR-0078)

- **Behind the scenes: tidied up repeated code in the Standard Bank statement reader** so the balance-reading logic lives in one place — less room for a future bug. (FIBR-0069)

- **Behind the scenes: merged the duplicated drop-down selection code** used by the account, category and type pickers into one shared piece. (FIBR-0068)

- **Behind the scenes: unified how the app saves to its database** (13 near-identical blocks became one shared routine), so a future change can't accidentally use a wrong save/undo path. (FIBR-0066)

- **Behind the scenes: an internal type-safety tidy-up** on the rule Move up/down code, plus a documentation correction. (FIBR-0081)

- **Behind the scenes: settings values (currency, decimal places) now go through one shared accessor** instead of hand-written database queries, so a typo can't read the wrong value. (FIBR-0080)

- **Behind the scenes: the build now type-checks the code automatically** (mypy), catching a class of mistakes before release instead of relying on manual checks. (FIBR-0061)

- **Silenced ~107 noisy third-party deprecation warnings from the OFX importer and pinned its parser dependency to keep OFX import working on future releases (FIBR-0058).**
  The OFX-file importer relies on ofxparse, which uses an old-style call into
  BeautifulSoup that prints a deprecation warning many times per run. The
  warnings are now suppressed (only that specific message), and the underlying
  library is version-capped so a future BeautifulSoup release that removes the
  old call can't silently break OFX import.

- **Date pickers show unambiguous ISO YYYY/MM/DD, not the locale's M/D/YY.** (FIBR-0047)
  Dates now always read year/month/day (e.g. 2026/07/04) so there's no US-vs-rest-of-world confusion.

### Fixed

- **Importing a corrupt or unreadable PDF now shows a clear "couldn't read this PDF — try your bank's CSV or OFX export" message instead of a raw internal error.** (FIBR-0064)

- **Adding a categorisation rule when no categories exist now shows a clear "create a category first" message instead of opening a dialog that dead-ends on a confusing error.** (FIBR-0079)

- **A second app instance or a slow backup holding a brief database lock no longer crashes with a raw error — connections now wait up to 5 seconds for the lock to clear.** (FIBR-0076)

- **Auto-locking while a pop-up is open no longer crashes the app (FIBR-0065).**
  If the app auto-locked itself while a small pop-up was open (pick a
  category, add/edit a rule, change a statement's account, or type a
  PDF password), it could crash instead of locking cleanly. Those
  pop-ups are now non-blocking, so the app always returns to the
  locked screen safely.

- **More import and account-management crash-safety (loop-2 review fold)**
  A Standard Bank statement with a non-English or garbled month name no longer crashes on import; deleting an account that has a quiet-month/all-duplicate imported statement (a period with no transactions) is now blocked with a clear message instead of crashing; and the Settings and Manual-entry dialogs (plus account/category add/edit) no longer error if the app auto-locks while they're open.

- **Categorization and account-management correctness/UX fixes**
  Manual category picks are validated to a leaf category at the service boundary (not just the UI); the rule reorder (Move up/down) is now one atomic transaction; deleting an account now asks for confirmation like the other destructive actions; and the unlock screen gives a malformed KDF sidecar its own message instead of 'check your password'.

- **Import now fails gracefully on malformed/unsupported statement files instead of crashing**
  An OFX investment/brokerage statement, a PDF pdfplumber can't parse, a missing/permission-denied file, and an over-large CSV all now surface a friendly message rather than an unhandled crash. The CSV path gained the same size cap the OFX/PDF paths already had, and a column mapping can no longer assign two roles to one column.

- **The window now remembers its size, and Window → Center window works on Linux Wayland (KDE), not only X11 (FIBR-0060).**
  On modern Linux desktops (Wayland) the system controls window placement, so
  the previous X11-only code silently did nothing: the window size was forgotten
  between runs and Center window had no effect. finbreak now restores the saved
  size on Wayland and centers via KDE's KWin on demand (X11, Windows and macOS
  are unchanged). On a non-KDE Wayland desktop, Center window is greyed out with
  a note that the desktop positions windows itself.

- **Import wizard: the destination account is now shown and correctable on the preview step, so a statement can no longer be silently imported into the wrong account (FIBR-0057).**
  Previously the target account was fixed the moment you chose the file, with
  no way to see or change it before the final Import — so a statement could
  land on the default account (e.g. "Current") instead of the one you meant.
  You can now confirm or change the account on the preview screen; a remembered
  locked-PDF password follows the corrected account.

### Security

- **Extra tamper-detection is now turned on explicitly for the encrypted vault** (rather than relying on the encryption library's default) — a belt-and-braces safeguard. (FIBR-0077)

- **Safer file handling on import, and a complete clean-up if vault creation fails**
  The import size cap is now enforced by a bounded read, so a symlink to an endless source (e.g. /dev/zero) or a file that grows after the size check can't be read unbounded into memory. Vault creation now closes and resets on any failure across the whole build (not just the final steps), and the app-data directory is created owner-only from the outset.

- **Hardened crypto/vault storage after a full-codebase review**
  Vault.create() no longer leaks an open, unlocked SQLCipher connection if a migration or sidecar write fails (it now mirrors open()'s close-and-reset); the app-data directory is created owner-only (0o700), not just the vault/sidecar files; the KDF sidecar's temp write refuses to follow a symlink (O_NOFOLLOW); and a first-run attempted over an existing vault now wipes the derived key on every exit path.

- **Opening a vault from a newer version fails safely (FIBR-0005).** If a
  future build upgrades your vault's format and you then open it with an older
  build, the app refuses cleanly with a clear "created by a newer version"
  message and wipes the derived key from memory — instead of leaving the key in
  memory and surfacing an opaque error.

- **Vault encryption, key derivation, and in-memory key wiping (FIBR-0004).**
  The master password is stretched into a 256-bit key with **Argon2id** (pinned
  parameters), which unlocks a **SQLCipher (AES-256)** database — the on-disk
  file is unreadable and integrity-checked (a wrong key or a flipped byte is
  refused, not silently accepted). The plaintext parameters live in a non-secret
  sidecar written owner-only and created owner-only from the start (no
  world-readable window). The derived key lives only while unlocked and is wiped
  from memory on lock, idle auto-lock, and app exit. There is no password
  recovery in this slice (a forgotten password means the data is unrecoverable —
  stated on the first-run screen), and the app makes no network calls
  (enforced by a test). (FIBR-0004)

- **`.gitignore` blocks financial data and build output from the public repo.** (FIBR-0002)
  Extends the ignore set so a local vault (`*.db` / `*.sqlite` /
  `*.sqlite3` and its SQLite `-wal` / `-shm` / `-journal` sidecars) and
  all build/packaging output (PyInstaller `build/` / `dist/`,
  `*.egg-info/`, `*.dmg`, `*.AppImage`, `*.flatpak`, `.flatpak-builder/`,
  and tool caches) can never be staged; `gitleaks` remains the content
  backstop. Regression-locked by `tests/features/gitignore/`. (FIBR-0002)
