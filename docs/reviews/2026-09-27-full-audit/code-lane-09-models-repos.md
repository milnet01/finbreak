## Lane 09: domain models and the repository (SQL) layer. Depth pass.

**Subject files as read (line counts):** `models.py` 643, `errors.py` 93, `repositories/__init__.py` 16, `accounts.py` 100, `alert_dismissals.py` 44, `categories.py` 81, `categorization_rules.py` 100, `import_profiles.py` 106, `recurring.py` 73, `reporting.py` 69, `settings.py` 35, `statement_periods.py` 195, `transactions.py` 369, `transfers.py` 153. All are under `/mnt/Games/Scripts/Linux/finbreak/src/finbreak/`.

**What was already in my context when I arrived:**
- `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md` and finbreak's `CLAUDE.md`, which includes the module map, the release and push policy, and the rule that a `.corpus-numbers` file is never printed.
- The finbreak `MEMORY.md` index, which carries project history such as FIBR-0327 and "roadmap_log notes land mid-bullet".
- A git snapshot: HEAD `52e5162`, recent commits for FIBR-0331.

I read the subject from disk.

**How I searched:**
- `read_regions` spilled and `read_spill` went over the token cap, so I read the lane files with plain `Read`.
- `workspace_search` was rate-limited once, so I used `Grep` from then on. Every search was scoped to `src/` or `docs/`, so the test tree was never searched. I opened no test file and did not use either of the test-count cases the brief allows.

**Brief versus lane file:** they did not disagree on anything.

## Critical (0)

## High (1)
- **[dim 2]** `repositories/statement_periods.py:91-94`: `# No handler is configured anywhere in the app, so this falls through to logging.lastResort -- which emits WARNING and above to stderr`.
  - `design.md` § Observability promises "a local **rotating log file** in the user data directory … The log path is shown in Settings".
  - Searching `src/` for `RotatingFileHandler|basicConfig|addHandler|dictConfig` found nothing. Searching for `log_path|log file` found only `update_installer.py`'s `update-relaunch.log`.
  - So the log feature the design promises does not exist. Every `log.info`/`log.warning` in the services and repositories goes nowhere, or to stderr. This is outside my lane's files; I found it through a code comment in my lane that admits it.
  - Which side is wrong: I cannot tell (see Open questions). Either the code is missing the handler or `design.md` over-promises.
  - Fix: install a `RotatingFileHandler` under `data_dir()` at startup and show its path in Settings. Otherwise, hand `design.md` § Observability to `review-contract`.

## Medium (1)
- **[dim 7]** `repositories/statement_periods.py:88-99`: `elif current != balance_minor: … log.warning("closing balance disagreement for statement period %d …`.
  - When a statement is re-imported, the new closing balance can disagree with the stored one. The code keeps the stored value, and a log line is the only signal. FIBR-0171 D4/INV-12 prescribes exactly that.
  - But because no log sink exists (the High finding above), the warning goes to stderr. On a GUI launch nobody sees stderr. On a windowed PyInstaller build `sys.stderr` may be `None`, so it goes nowhere at all (unexecuted: needs confirming that `windows-build.yml` freezes with `--windowed`).
  - `design.md` § Error handling says "errors surface to the user; nothing is silently swallowed". A money-integrity disagreement is therefore dropped without the user ever knowing.
  - Fix: return a flag from `update_closing_balance` so `ImportService.commit_import` can put the disagreement in `ImportResult` and show it. Keep the id-only log line.

## Low / Info
- **INFO:** I checked the lane contract specs only by targeted grep and slices, not read in full: FIBR-0012 D4 (the inclusive date range in `rows_in_range`), FIBR-0201 (the predicate shared by `hand_off_covered` and `delete_split_counts`, and its host-parameter note at :699), and FIBR-0231 § 4.7 (the `MonthSummary`/`MonthCause` fields). I did not open FIBR-0010, 0052, 0059, 0007 or 0192 beyond the clauses the code's docstrings cite.
- **dim 3 (SQL injection):** nothing found. Every value is a bound parameter. The only f-string interpolation is placeholder text: `?` runs at `transactions.py:147` and `reporting.py:40/65`, and `:delN` names at `transactions.py:46-52/83`. That matches the false-positive ledger.
  - The PDF password is read only by dedicated accessors and never selected into `Account` (`accounts.py:79-100`).
- **dim 4 (duplicated logic that has diverged):** nothing found.
  - `rows_in_range` and `drill_rows_in_range` differ only in the extra column.
  - The coverage predicate has one source (`_coverage_where_sql`), and the migration-v6 backfill uses the same `BETWEEN q.period_start AND q.period_end`.
  - The confirmed-pair checks agree across `CANDIDATE_PAIRS_SQL`, `is_confirmed` and `confirmed_txn_ids`.
- **dim 9 (data integrity):** nothing found.
  - Commit discipline holds. The commit-free methods (`set_category`, `set_priority`, `clear_category_for`, `delete_for_category`, `hand_off_covered`, `delete_for_statement`, `reassign_account`, `set_account`, `add_batch`, `add`/`update_closing_balance` on `StatementPeriodRepository`) are all called only inside `owned_transaction` blocks (I grepped their call sites). No method that commits for itself is called inside an owned block.
  - `transfer_pairs` rows cascade when a transaction is deleted (`migrations.py:282-283`), and `PRAGMA foreign_keys = ON` (`vault.py:337`).
- **dim 13 (timezones and dates):** nothing found.
  - The only clock calls in the lane are `datetime.now(UTC).isoformat()`, used for timestamps.
  - No month or period boundaries are computed in this layer.
  - `occurred_on` is canonicalised through `date.fromisoformat(...).isoformat()` on the manual path (`services/transactions.py:69`), so the text `BETWEEN` and SQLite's `date()` (`transfers.py:53-54`) compare dates with no time or zone part.
- **[money] trap:** no mixing found in this layer. Repositories carry only signed integer `amount_minor`. The `models.py` records split cleanly between integer-minor types (`Forecast*`, `SpendingAlert`, `Month*`, `AccountReconciliation`) and display `Decimal` types (`Summary`, `CategorySpend`, `RecurringItem`, `Transfer*`). Whether a service mixes the two is not in my lane.
- **dim 5, 8, 11, 16, 17:** nothing found in these files. dim 10: see the High finding. dim 12: N/A. dim 15: nothing leaves the machine from this layer.

## Covered by spec and looks correct
- `transactions.py`:
  - The coverage fragment, used twice in each of `_hand_off_sql` and `_split_counts_sql` (FIBR-0201 INV-9).
  - The `statement_period_id in deleting` guard.
  - The NULL-safe `auto_rows` and `set_category` predicates (`IS NULL OR <>`, `IS NOT`).
  - `sum_after`'s half-open `(after, up_to]` window (FIBR-0171 INV-13 / FIBR-0177 INV-2).
  - The `max_id` boundary.
  - `by_ids` chunking. Its one caller keys the result into a dict, so duplicate ids are harmless.
- `statement_periods.py`: the fill-only `update_closing_balance`, and `latest_closing_balances` choosing the greatest `period_end`, ties broken by id (FIBR-0171 INV-6).
- `reporting.py`: inclusive `BETWEEN`, and an empty account set short-circuits to no rows (FIBR-0012 D4 / FIBR-0013 D4).
- `models.py`: `MonthSummary` and `MonthCause` match FIBR-0231 § 4.7 field for field. Every `X(*row)` dataclass matches its repository's SELECT column order.

## Open questions
1. **Observability: which side is wrong?** Is § Observability's rotating log still intended, or superseded? The comment at `statement_periods.py:91-94` was written knowing the handler is absent, which suggests the design document may be stale rather than the code.
2. **`reassign_account` and confirmed transfers.** `TransactionRepository.reassign_account` / `StatementPeriodRepository.set_account` (FIBR-0059) can move one leg of a confirmed transfer pair into the other leg's account. The pair would then be a same-account "transfer" that is still excluded from totals. I did not read FIBR-0059 in full to see whether it addresses this; it is a service-level question.
3. **`StatementPeriodRepository.delete` has no caller.** Its docstring (`statement_periods.py:192`) names `StatementService.delete_statement`, but the grep of call sites shows `delete_statements` never calls it. This lane cannot see how the batch delete (FIBR-0201) removes the statement row.

## 3 items to fix first
1. **The missing log sink (High).** It makes every `log.*` across the app, including the INV-9-compliant money warnings, useless, and it contradicts a design promise the user can check (a log path shown in Settings).
2. **Surface the closing-balance disagreement to the user (Medium).** It is a money-integrity signal on a correctness-critical app, and today it reaches nobody.
3. **Settle open question 2 (reassign versus confirmed transfer pairs).** If it is real, totals silently exclude a same-account pair after a reassign. That is the wrong-total class this project treats as most serious.