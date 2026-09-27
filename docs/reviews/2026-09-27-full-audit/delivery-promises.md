# verify-delivery promises — finbreak CHANGELOG [0.1.23] (window: the released section at tag v0.1.23)
Source for every promise: CHANGELOG.md section [0.1.23]; the bold headline is quoted verbatim, the falsifiable sentence follows.

## Group A — vault, recovery, backup, lock, unlock
A1 "A recovery code — a second way into your vault if you forget your master password" (FIBR-0019): a fresh vault offers a recovery code; after keeping it, unlocking via the recovery route with that code (typed with I/L/O substitutions, lowercase, extra hyphens/spaces) opens the vault and forces a new master password; a wrong code does not open it.
A2 "Two copies of finbreak can no longer open the same vault after a crash." : with a stale single-instance socket/claim left from a crashed process, a second launch while one instance runs does not proceed to open the vault.
A3 "A blocked recovery from an interrupted restore explains itself": when an interrupted restore cannot be recovered, the user sees a message saying why rather than nothing / a generic error.
A4 "A failed first run no longer leaves the vault open": if first-run vault creation fails part-way, the app does not hold an unlocked vault afterwards.
A5 "A damaged settings file is now reported as a damaged settings file, not as a wrong password.": an unlock against a vault whose KDF sidecar (vault.kdf.json) is corrupt shows a "security-settings file" message, not "check your password", and is not counted by the throttle.
A6 "Backups written by one version stay restorable by later ones.": a .fbk fixture written by an older release restores in the current code.
A7 "Backup export no longer fails for anyone whose home folder contains an apostrophe.": exporting a backup to a destination under a directory whose name contains ' succeeds and the result verifies.
A8 "Recovering from an interrupted backup restore now puts back the whole database, and no longer offers to create a new vault over a recoverable one.": after an interrupted restore (DB moved aside, WAL siblings present), the next start reconciles to the original vault with its -wal/-shm, and does not show first-run.
A9 "Locking the vault now clears more of what was on screen" (FIBR-0322): after a lock, no tab widget still holds decrypted rows (tables, trees, parallel Python lists).
A10 "A backup file crafted to attack finbreak can no longer exhaust your machine before you have typed a password.": a .fbk with a deflate-bomb / oversize entry is refused before the password prompt / key derivation, bounded in memory.
A11 "A screen reader can now name every password and recovery-code box.": every password QLineEdit and recovery-code box in unlock, first run, recovery key, password dialog, settings has a non-empty accessibleName.
A12 "The time zone you pick in Settings now decides what "today" means, not just how dates look.": with a pinned zone whose date differs from the OS zone, "today"-dependent values (current month on Home, manual-entry default date, forecast start) follow the pinned zone.
A13 "A typed-in time zone is the one that gets saved": typing a valid IANA zone id into the Settings time-zone box and saving persists that id.

## Group B — import
B1 "CSV import now guesses the column mapping from the file's own headers" (FIBR-0297): a CSV with headers like Date/Description/Amount opens the mapping step with those columns pre-selected.
B2 "The import wizard no longer crashes if the vault locks itself while you are partway through.": an auto-lock during any wizard step does not raise out of a slot.
B3 "The account picker no longer arrives with an account already chosen for a statement that has none.": for a statement with no detected account, the picker's current selection is the placeholder, and OK is disabled until the user picks.
B4 "The batch import review's Account column can be used without a mouse.": keyboard focus on the Account cell + a key (Enter/F2/Space) opens the account picker.
B5 "Cancelling a locked-PDF import no longer leaves the password on the wrong account" (FIBR-0321): cancelling after typing a PDF password with Remember ticked stores no password on any account.
B6 "Importing several statements with the same layout now asks about the columns once" (FIBR-0319): a batch of N unmatched CSVs sharing one header asks the mapping question once.
B7 "The import preview shows amounts the way the rest of the app does": preview amount cells use the same formatter/negative style as the Transactions tab.
B8 "An enormous amount in a spreadsheet cell is reported as one bad row instead of aborting the import.": a CSV row with a 40-digit amount yields one RowError and the other rows still preview.
B9 "An OFX statement carrying a transaction with no date no longer closes the app.": parsing such an OFX returns a result/refusal, no uncaught exception.
B10 "Standard Bank import: a truncated statement on an overdrawn account is now refused instead of silently importing short.": a Standard Bank statement whose rows end early on a negative running balance is refused.
B11 "You can no longer end up with two categories or accounts whose names look identical." (FIBR-0328): creating a category/account whose name equals an existing one after normalisation (case, NFC, whitespace/confusable per spec) is refused.

## Group C — views, export, update, shell
C1 "Your date format now reaches the Transfers, Recurring, Forecast and Alerts screens.": with a non-default date format pref, dates on those four screens render in it.
C2 "Adding or deleting a category no longer leaves the buttons active with nothing selected": after add/delete, Update/Delete buttons are disabled when nothing is selected.
C3 "Closing during an update check is safer": closing the main window while an update-check worker runs exits cleanly (no QThread-destroyed abort).
C4 "A startup failure now says what went wrong instead of nothing at all": an exception during startup produces a visible message / logged message with the cause.
C5 "A dropped download says so instead of raising the tamper alarm": a download cut short (Content-Length shortfall) reports a download error, not a signature/tamper error.
C6 "Self-update works from a folder whose name contains an apostrophe": the relaunch command built for an AppImage/exe path containing ' is correctly quoted.
C7 "Ticking "Date range" on Transactions no longer empties the table": enabling the date-range filter with its default range still shows the rows in range.
C8 "Very large amounts display the digits that are stored": an amount_minor near the storable max renders every stored digit (no float rounding).
C9 "Deleting a rule no longer leaves the next one selected": after deleting a rule, no rule is selected.
C10 "Exported PDFs name the month in the app's language": PDF month names come from the app locale (QLocale), not the C locale.
C11 "Account names render as text on the Forecast tab": an account named "<b>x</b>" shows literally on Forecast.
C12 "An update that cannot be installed now explains itself instead of failing silently.": an install-time UpdateError shows a message.
C13 "Choosing Check for updates twice in a row no longer risks a crash on exit.": a second manual check while one runs is refused/ignored and exit is clean.
C14 "Quit and Ctrl+Q now save your window layout and shut background work down cleanly.": Quit via action/Ctrl+Q triggers closeEvent (geometry saved, workers drained).
C15 "The app no longer closes when the vault auto-locks while the Statements reassign picker or the Categories move-under list is opening.": auto-lock during those pickers raises nothing out of a slot.
C16 "Dates in an exported PDF's transactions table now follow your chosen date format.": PDF transaction dates use the date-format pref.
C17 "The trend chart's month and value labels are now readable on the dark theme and in a dark PDF export.": trend chart label colours contrast with the background on the dark theme. (Note: the dark PDF export was later withdrawn by FIBR-0217 — check the PDF half against what ships.)
C18 "The Forecast chart's value axis now reads in the same units as the figures beside it.": the forecast axis values are in major currency units, matching the table.
C19 "Statement closing balances are no longer written to the log." — DROPPED (internal; no log sink exists, see review-code lane 09).
