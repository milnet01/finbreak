# Lane 06: CSV and OFX importers, format sniffing, date and column detection, import service, account matching

**Line counts of the subject files, as read:**

| File (under `src/finbreak/`) | Lines |
|---|---|
| `importers/base.py` | 71 |
| `importers/column_detect.py` | 82 |
| `importers/csv_importer.py` | 192 |
| `importers/date_detect.py` | 114 |
| `importers/ofx_importer.py` | 219 |
| `importers/sniff.py` | 60 |
| `services/import_.py` | 471 |
| `services/account_match.py` | 116 |
| `datetime_format.py` | 134 |
| `text.py` | 120 |

**Already in my context when I started:**
- `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md` and finbreak's `CLAUDE.md`.
- The finbreak memory index `MEMORY.md`.
- A git snapshot (main, clean, HEAD `52e5162`, FIBR-0331 commits).
- The shared-context packet.

**How I read:**
- I read all subject files from disk. I did not open any test file, and made no test-tree searches.
- To check specific claims I opened these cross-references: `services/transactions.py` (`parse_transaction`, `to_minor`, `to_minor_storable`), `repositories/statement_periods.py:30-60`, and slices of `ui/import_wizard.py`.
- I also opened the installed `ofxparse` source under `.venv` (`parseOfxDateTime`, `parseStmtrs`, `toDecimal`, the soup builder).
- `workspace_search` hit its rate limit once. I used `Grep` from then on, only on `docs/`, `src/` and `.venv`, so no exclusion was lost.
- I ran no code; nothing here was executed.
- There was no disagreement between my brief and the review-lane file.

## Critical (0)

## High (0)

## Medium (3)

- **[dim 3] `importers/ofx_importer.py:189`**
  - Line: `None if balance is None else to_minor_storable(balance, exponent)`
  - Problem: a non-finite `<BALAMT>` escapes as an exception type nobody catches.
    - `ofxparse.toDecimal` (`ofxparse.py:1093-1108`) ends in a bare `decimal.Decimal(d)`, so `Infinity`, `NaN` and `sNaN` all parse.
    - `to_minor` (`transactions.py:123`) does `int(amount.scaleb(exponent).to_integral_value())`.
    - For `Infinity` that `int()` raises `OverflowError`. For `sNaN`, `scaleb` signals `decimal.InvalidOperation`. Neither is a `ValueError`, and `to_minor_storable` catches only `decimal.Overflow`.
  - Where it escapes: the `except ValueError` at `:191`, then `parse()`'s boundary catch (which wraps only `OfxParser.parse`), then the wizard's `(ValueError, FinbreakError)` net. That is a crash of the Qt slot, and per the file's own comments a destroyed batch run.
  - The comment at `:178-186` claims this path is fully covered. It covers `1e999999` and `1e30`, not the non-finite values. The code is wrong, not the comment's intent.
  - Transaction amounts are safe, because `parse_transaction` checks `is_finite()` first.
  - Unexecuted. To confirm: `int(Decimal('Infinity').scaleb(2).to_integral_value())`, and an OFX file with `<LEDGERBAL><BALAMT>Infinity`.
  - Fix: put `if not amount.is_finite(): raise ValueError("amount is too large to store")` at the top of `to_minor_storable` (`transactions.py:135`), which also covers the other importers that call it.

- **[dim 16] `importers/csv_importer.py:77`** (used by `parse` at `:102`)
  - Line: `return list(csv.DictReader(io.StringIO(text)))`
  - Problem: an unterminated quote silently swallows every row after it.
    - The reader runs non-strict (RFC 4180 quoting). A field that opens with `"` and is never closed runs on across newlines until end of file, or until the next quote character.
    - Non-strict `_csv` returns the partial field at end of file instead of raising.
    - The one merged record produces a single `RowError` ("row has fewer columns…" or a date/amount error). Every physical row it swallowed disappears with no `RowError` of its own.
  - Effect:
    - This breaks INV-4 / `base.py`'s "every failure shows in the preview".
    - The default coverage span, the drafts' min/max, quietly shrinks to match.
    - `csv.Error` only fires when the swallowed tail is over `field_size_limit`, about 128 KiB, so a typical statement loses rows silently.
  - Unexecuted. To confirm: `list(csv.DictReader(io.StringIO('Date,Desc,Amount\n2026-07-01,"Cash,10\n2026-07-02,Shop,5\n')))`.
  - Fix: build the reader with `strict=True`, so an unclosed quote at end of file becomes `csv.Error`, which is already translated to `ValueError`. Also add a `RowError` ("a quote in this row is never closed…") for any mapped date or amount cell containing `\n` or `\r`, which catches the mid-file case where a later quote closes the field.

- **[dim 16] `datetime_format.py:62` and `:95`**
  - Lines: `return QTimeZone(QTimeZone.systemTimeZoneId())` and `return date(local.year(), local.month(), local.day())`
  - Problem: `_resolve_zone` never checks that the system zone it builds is valid.
    - Suppose `systemTimeZoneId()` gives an id that `QTimeZone(id)` cannot build: an empty id, a Windows id with no mapping, or a container or Flatpak with no `/etc/localtime`.
    - I believe, from Qt 6 docs recalled and not checked here, that `toTimeZone(invalid)` returns an invalid `QDateTime`. Then `.date()` is invalid and `date(0, 0, 0)` raises `ValueError`.
    - That would crash every "today" consumer: month totals, the alert grace window, the forecast horizon. It contradicts FIBR-0083's "never an exception to the UI".
  - Unexecuted. This depends on Qt behaviour, and needs a run with `TZ` pointing at an unknown zone and `/etc/localtime` absent.
  - Fix: use `QTimeZone.systemTimeZone()`. If the result is not `isValid()`, fall back to `QDateTime.currentDateTime()` (local time), or to `QDate.currentDate()` in `today_in`.

## Low / Info

- **[dim 4] `services/import_.py:466-467`**
  - Line: `start = date.fromisoformat(period_start)`
  - `_validate_span` checks the span dates but does not canonicalise them. `commit_import` then stores the raw strings (`:312`, `:316-318`).
  - `parse_transaction` was fixed for exactly this in FIBR-0216 (`"20260715"` and `"2026-W29-3"` both pass `fromisoformat`, and dates are compared as strings). The two copies of the logic have diverged.
  - Latent for now: the wizard passes `QDate.toString(ISODate)` and the batch passes values that are already ISO.
  - Fix: return `start.isoformat()` and `end.isoformat()` from `_validate_span` and use those.
- **[dim 7] `services/import_.py:170`**
  - Line: `return self._read_capped(path).decode("utf-8-sig")`
  - Refusing a non-UTF-8 file is correct under FIBR-0007 D11. But the `UnicodeDecodeError` surfaces its raw codec text ("'utf-8' codec can't decode byte 0xe9 in position …") in the wizard's error label.
  - Fix: catch it and raise `ValueError("this file is not UTF-8 text …")`.
- **[dim 13] User-facing text built as English f-strings in Qt-free code, then shown with `setText(str(exc))` (`ui/import_wizard.py:1308-1311`).**
  - Examples: `csv_importer.py:129` `f'could not read the date "{raw_date}"'`, `:172`, and `import_.py:451` `f"mapped column(s) not in the file header: {missing}"`, which also shows a Python list repr.
  - This conflicts with design.md § i18n: everything goes through `tr()`, with no concatenation.
  - Fix: return structured error codes plus values, and translate in the UI.
- **[dim 13] `datetime_format.py:103`**
  - Line: `return qdate.toString(date_pref)`
  - The pinned `MMM`/`MMMM` tokens render English month names whatever the UI language, which conflicts with § i18n "dates are formatted through `QLocale`".
  - Fix: `QLocale().toString(qdate, date_pref)`.
- **INFO:** I could not execute any of the three Medium findings.
- **INFO:** Dimension scan:
  - 2b: nothing found. Every declared entry point has non-test callers in `src` (`match_account`, `guess_columns`, `detect_date_format`, `today`, `set_app_timezone`).
  - 5 and 11: the byte cap is `_MAX_IMPORT_BYTES` with a bounded `cap+1` read, and the OFX transaction cap exists; nothing found.
  - 8: nothing found.
  - 10: no logging of row contents in these files; nothing found.
  - 12: not applicable.
  - 15: nothing leaves the machine from these files; nothing found.
  - 17: nothing found.

## Covered by spec and looks correct

- **OFX parsing:**
  - The installed `ofxparse` uses `BeautifulSoup(fh, 'html.parser')` (`ofxparse.py:30`). No DTD or external-entity processing, so no XXE or entity-expansion risk.
  - The timezone neutraliser (`ofx_importer.py:44`) matches `ofxparse`'s own regex. The colon-less `[-5]` form is `tz=0` in both, so there is no wrong-day path there.
  - Also correct: the null-date guard (`:157`), the investment-account filter, the empty-span falsiness check, and the count cap.
- **CSV importer (FIBR-0007 D5):**
  - The ragged-row guard, the debit/credit sign and magnitude rules, and `_to_decimal`'s wording.
  - NaN, sNaN, `-0` and over-precise values all reach `RowError`s, either through the caught `InvalidOperation` or through `parse_transaction`.
  - `csv.Error` is translated in both readers.
- **Import service:**
  - `commit_import` does the dedup, the period, the inserts and the recategorisation inside one `owned_transaction`. That matches design § Persistence, "no partial rows".
  - The multiset-delta dedup, and identity-based `duplicate_row_numbers`.
  - `_has_year_token`, including `%%Y`.
  - Distinct-column and exactly-one-amount-style validation.
  - The duplicate-header guard is reached before `preview` on both wizard paths (`import_wizard.py:577`, `:984`).
- **Date detection:** the tie and ambiguity logic, and determinism.
- **Account matching:** the mask guard is applied to both the statement side and the stored side, and an empty number matches nothing.
- **Column guessing:** exact matching on normalised names, and one role per column.
- **Sniffing:** reads a bounded 512-byte head.
- **`text.normalise_text`:** NFC before casefold, so dedup is deterministic.

## Open questions

- **OFX DTEND semantics.** In the OFX spec, a `BANKTRANLIST`'s `DTEND` is the value the client should send as the next `DTSTART`, often midnight of the day *after* coverage ends. FIBR-0008 D4 stores it as the period end as-is, which would make consecutive statement spans overlap by a day. I cannot tell whether the spec or the code should change.
- **Month names and locale.** `%b`/`%B` read the ambient `LC_TIME`. I believe, from memory and not checked, that Qt on Unix calls `setlocale(LC_ALL, "")`. If so, English statements on an `af_ZA` or `de_DE` machine fail to parse Mar, May, Oct and Dec. FIBR-0146 defers this to FIBR-0017, which has no spec file in `docs/specs/`. The "never a wrong month" claim is unchecked across locales.
- **"0.00" in the unused debit/credit cell.** FIBR-0007 D5 makes any both-populated row a `RowError`. A bank that prints `0.00` in the unused column therefore gets every row refused. Is that intended by the contract?

## 3 items to fix first

1. **The OFX non-finite balance crash** (`ofx_importer.py:189` / `to_minor_storable`). One hostile or malformed file crashes the wizard slot or wipes out a batch run, and the fix is one line in the function every importer shares.
2. **The CSV unclosed-quote row swallowing** (`csv_importer.py:77`). It loses transactions with no per-row error, the worst kind of failure for a money app, and the coverage span shrinks to hide it.
3. **The `today_in` invalid-zone guard** (`datetime_format.py:62`/`:95`). If the Qt behaviour is as I believe, every "today" figure crashes on machines with an unusual zone setup, and the guard is cheap.