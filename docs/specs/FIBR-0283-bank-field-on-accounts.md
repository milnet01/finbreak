<!-- ants-spec-format: 1 -->
# FIBR-0283 — Record which bank each account is at

**Status:** spec draft (2026-11-15).
**Kind:** implement.
**Source:** ROADMAP FIBR-0283 (user-request-2026-08-19, a real vault of six
accounts at one bank and one at another).

**Blocker for:** FIBR-0284 (auto-detect uses the bank as a matching signal).
**Pairs with:** FIBR-0193 (the v13 `account_number` / `note` columns — the
precedent this spec follows step for step).

*Layman: each account gets an optional "Bank" box. You type the bank's name, or
pick one finbreak has seen before. The Accounts screen shows it in its own
column, and the places where you choose an account show it next to the name, so
two banks' accounts are easy to tell apart.*

## 1. Goal

An account can record the bank that holds it. The Accounts screen shows and
edits it. The account choosers in import, and the account names in a PDF
export, show it beside the account's name. Existing accounts upgrade with no
bank recorded, never a guessed one.

## 2. Problem

The `accounts` table holds `name`, `type`, `created_at`,
`statement_pdf_password`, `account_number` and `note`
(`migrations._migrate_to_v2`, `_migrate_to_v5`, `_migrate_to_v13`). Nothing
records the bank. So:

1. **A multi-bank vault is told apart only by account number**, which the
   Accounts screen masks by default (`ui/accounts.py::_mask_account_number`)
   and which nobody recognises on sight.
2. **The import pickers show the name alone**:
   `ui/account_picker.py::AccountPickerDialog.__init__`,
   `ui/import_wizard.py::_fill_account_combo` and
   `ui/import_batch.py`'s `_account_names` all use `account.name`. Choosing the
   right destination for a second bank's statement depends on how the user
   named the account.
3. **FIBR-0284 has nowhere to store** the bank name a statement prints.

## 3. Scope decisions (agreed with the user)

The user delegates spec design (2026-07-15), so the developer made both calls
the roadmap item left open. Each follows from a fact in the tree.

1. **Free text with suggestions, not a closed list.** Only Standard Bank
   statements can be read today (FIBR-0050; other banks are FIBR-0074), so a
   closed list would either name banks the importer cannot read or refuse
   the second bank in the very vault that prompted this item. The suggestions
   are the banks already in the vault plus `KNOWN_BANKS`, which holds
   `"Standard Bank"` alone.
2. **Optional, and existing accounts migrate to no bank.** A guess from the
   account number is the fragile signal this item exists to remove
   (roadmap body). Blank input is stored as NULL, as `note` is
   (`services/accounts.py::_normalise_optional`, FIBR-0193 INV-5).
3. **Where the bank is shown beside the name**: the three import pickers
   named in § 2 item 2, the account the import wizard adds to its combo after
   Create, and the PDF export's account header line and per-account summary
   row. These are where a user picks or reads one account among several.
   The other places that name an account are § 9.
4. **The bank is appended as the table's last logical column, and shown second
   by default.** A saved layout keys each column by its logical index, so
   inserting at index 1 would hand Type's saved width and sort to Bank
   (§ 4.4, measured).

## 4. Design

### 4.1 Schema — migration v18

```python
def _migrate_to_v18(conn: dbapi2.Connection) -> None:
    with owned_transaction(conn):
        conn.execute("ALTER TABLE accounts ADD COLUMN bank TEXT")
        conn.execute("UPDATE schema_version SET version = 18")
```

Registered as `_MIGRATIONS[18]`; `LATEST_SCHEMA_VERSION = 18`. Nullable, no
default, no backfill — the shape of `_migrate_to_v13`. A `.fbk` backup holds the
whole `vault.db` (`services/backup.py`'s `_DB_ENTRY`) and restore runs
`run_migrations`, so backups need no change.

### 4.2 Model, repository and service

`models.Account` gains `bank: str | None = None` **after `note`**, so
`Account(*row)` stays aligned and the four-argument positional literals in tests
keep working (the reason FIBR-0193 gave its two fields defaults).

`repositories/accounts.py`:

- `list_all` and `get` select `id, name, type, created_at, account_number,
  note, bank`, in that order.
- `add(name, type, account_number, note, bank)` and
  `update(account_id, name, type, account_number, note, bank)`. **`bank` is
  required on both, with no default**, as `account_number` and `note` already
  are on `update`: a caller that forgets it fails at once rather than erasing
  the stored bank.
- `banks() -> list[str]`: `SELECT DISTINCT bank FROM accounts WHERE bank IS NOT
  NULL`.

`services/accounts.py`:

- `add_account(..., bank: str | None = None)`; `update_account(..., bank: str |
  None)`, keyword-only and **required**, beside `account_number` and `note`.
  Both pass `bank` through `_normalise_optional`.
- `KNOWN_BANKS: tuple[str, ...] = ("Standard Bank",)`.
- `bank_suggestions() -> list[str]`: the stored banks, then `KNOWN_BANKS`, with
  duplicates removed by `text.fold_name` (the stored spelling wins), sorted by
  `fold_name`.

### 4.3 The label

`ui/_widgets.py` gains:

```python
def account_label(account: Account) -> str:
    if account.bank is None:
        return account.name
    return QCoreApplication.translate("AccountLabel", "{name} ({bank})").format(
        name=account.name, bank=account.bank
    )
```

With no bank the label is the name exactly, so every vault that records no
bank looks the same as today. `services/pdf_export.py` already imports from
`ui/` (`ui/_amount.py`), so it can use this too.

Sites switched from `account.name` to `account_label(account)`:

| Site | What it labels |
|---|---|
| `ui/account_picker.py::AccountPickerDialog.__init__` | the combo items, in the batch import and in the Statements tab's *Change account* |
| `ui/import_wizard.py::_fill_account_combo` | the pick step's and preview's combos |
| `ui/import_wizard.py`, the `addItem` after a Create | the new account's item |
| `ui/import_batch.py`, the `_account_names` map | the review table's Account cell |
| `services/pdf_export.py::_account_names` | the header line, for three or fewer accounts |
| `services/pdf_export.py`, the per-account summary row | the row's first cell |

Sorting is unchanged: every site that sorts still sorts by `name`.

### 4.4 Accounts screen

- **Form:** `self._bank`, a `QLineEdit` placed at grid row 0, column 2, beside
  Type, with a `QCompleter` over `bank_suggestions()`
  (`Qt.CaseSensitivity.CaseInsensitive`). `_on_add` passes it and clears it.
  `_on_update` passes it. `_on_selection_changed` fills it with
  `account.bank or ""`. The completer's list is rebuilt in `_refresh`, so a
  newly typed bank is suggested next time.
- **Table:** six columns. `_COL_BANK = 5`; the other five keep their indices,
  and Name stays logical column 0, which `tag_row` reads. The header text is
  `self.tr("Bank")`, and the cell is a plain `QTableWidgetItem(account.bank or
  "")`. Before `remember_columns`, `header.moveSection(5, 1)` puts Bank second.
  That makes "after Name" both the first-run layout and the one Reset layout
  restores.

**Why the bank goes in last, measured** (PySide6 6.11.1, offscreen, a 5-column
state with column 1 resized to 222, column 4 moved first and the sort on
column 3, restored onto 6 columns):

```text
A restore ok True visual of logical0..5 [1, 2, 3, 4, 0, 5] width1 222 sort 3 hidden5 False
```

`restoreState` accepts the shorter state. The five old columns keep their
widths, order and sort, and logical 5 is appended visibly at the end,
overriding the `moveSection` made before the restore. So a user with a saved
layout finds Bank at the right-hand end and can drag it. Had Bank been
inserted at logical 1, the same restore would have given it Type's width of
222, and the sort on 3 would have moved from Note to Account number.

### 4.5 Create-an-account dialog

`ui/account_create.py::CreateAccountDialog` gains a Bank row under Account
number, a keyword `banks: Sequence[str] = ()` that feeds its completer, and
`entered_bank() -> str`. Both callers, `ui/import_wizard.py` and
`ui/import_batch.py`, pass `banks=accounts.bank_suggestions()` and
`bank=dialog.entered_bank()` to `add_account`. The field starts empty.
Pre-filling it from the statement is FIBR-0284.

## 5. Invariants

**Trust boundary.** The bank is free text the user types. It reaches the user
again in two kinds of place: Qt widgets, which `account_label` and the
Accounts table feed as plain item text, and the PDF's HTML, where INV-9
holds. The existing `log.info` lines in `services/accounts.py` carry no field
values. Nothing here adds one, and security-model INV-9 still holds.

- **INV-1** — A v17 vault upgrades in place to v18. `accounts` gains exactly
  one column, `bank`, nullable, and every existing row reads `bank IS NULL`
  with its other values unchanged. `LATEST_SCHEMA_VERSION == 18` and
  `18 in _MIGRATIONS`.
  *Test:* `tests/features/accounts/test_migration_v18.py`, modelled on
  `test_migration_v13.py`: the exact column set `before | {"bank"}`,
  `notnull == 0`, and the rows unchanged.
  *Breaks when:* the column is `NOT NULL DEFAULT ''`, or a backfill writes a
  guessed bank.

- **INV-2** — A failure inside the v18 step leaves a v17 vault with no `bank`
  column, and a re-run then upgrades it.
  *Test:* the same file. `raising_conn` fails on `UPDATE schema_version SET
  version = 18`. The fixture is chosen because only the transaction can undo
  the `ALTER` that ran before it.
  *Breaks when:* the step runs outside `owned_transaction`, or commits between
  its two statements.

- **INV-3** — Both read paths return all seven fields in model order. A
  stored bank reads back as stored, from `get` and from `list_all`.
  *Test:* extend `tests/features/accounts/test_accounts.py`'s FIBR-0193 INV-3
  round-trip with a distinct `bank` value. Distinct values in each field are
  what catch a misordered `SELECT`.
  *Breaks when:* a `SELECT` omits `bank`. The model's default would then
  absorb it silently, which is why the test compares values, not just that
  construction succeeds.

- **INV-4** — `add_account` and `update_account` strip the bank, and store a
  blank one as NULL.
  *Test:* `add_account(..., bank="  ")` reads back `bank is None`, and
  `bank=" Nedbank "` reads back `"Nedbank"`.
  *Breaks when:* the bank skips `_normalise_optional`, so `""` is stored.

- **INV-5** — `update_account` sets and clears the bank, and a call that omits
  `bank` raises `TypeError` rather than leaving or erasing the stored value.
  *Test:* update to `"Nedbank"`, then to `None`, reading each back. Then call
  `update_account` without `bank`, and `AccountRepository.update` with five
  arguments, each under `pytest.raises(TypeError)`.
  *Breaks when:* `bank` is given a default on `update_account` or on
  `AccountRepository.update`.

- **INV-6** — `bank_suggestions()` holds each bank once, compared case-blind,
  and sorted. Where a stored bank matches a known bank, the stored spelling
  wins.
  *Test:* store `"standard bank"` and `"Nedbank"`. The result is `["Nedbank",
  "standard bank"]`. On an empty vault it is `["Standard Bank"]`.
  *Breaks when:* deduplication is case-sensitive (both Standard Bank
  spellings appear), or `KNOWN_BANKS` overrides the stored spelling.

- **INV-7** — `account_label` returns the name exactly when the bank is NULL,
  and `"{name} ({bank})"` otherwise.
  *Test:* `account_label(Account(1, "Cheque", "current", "t"))` is
  `"Cheque"`, and with `bank="Nedbank"` it is `"Cheque (Nedbank)"`.
  *Breaks when:* a NULL bank renders as `"Cheque ()"` or `"Cheque (None)"`.

- **INV-8** — Each site in § 4.3's table shows `account_label`. For an
  account with a bank, its text includes the bank.
  *Test:* one test per site, each with an account whose bank is `"Nedbank"`:
  the picker's and the wizard's combo `itemText`, the batch review's Account
  cell, the wizard's item after Create, and the PDF header and summary row
  read from `PdfExportService._build_html`, which the existing PDF tests
  already call.
  *Breaks when:* any one site still reads `account.name`.

- **INV-9** — A bank containing markup appears in the PDF as literal text.
  *Test:* the bank `"<b>X</b>"` appears escaped (`&lt;b&gt;`) in the export's
  HTML, in both the header and the summary row.
  *Breaks when:* the label is inserted into the HTML without `escape`. Both
  `_header_html` and `_per_account_row` escape today, so this guards existing
  behaviour against the switch to `account_label`.

- **INV-10** — The Accounts screen round-trips the bank. Selecting a row fills
  the Bank field. Add stores the typed bank and clears the field. Update
  stores an edited bank, and an emptied field stores NULL. The Bank column
  shows the stored bank.
  *Test:* `tests/features/accounts/test_accounts.py`, beside FIBR-0113 INV-12's
  number-and-note round trip.
  *Breaks when:* `_on_update` omits the field, so the edit is lost, or
  `_on_selection_changed` leaves the previous row's bank in place.

- **INV-11** — On first run the Bank column is logical 5 and visual 1, and Name
  is logical 0. A layout saved by the five-column screen restores with each old
  column keeping its width and position, and Bank last.
  *Test:* write a five-column `saveState` (column 1 width changed) under
  `columns/accounts_table` in the test INI, build the screen, and assert
  column 1's width and `visualIndex(5) == 5`. On a fresh INI, assert
  `visualIndex(5) == 1`.
  *Breaks when:* Bank is inserted at logical 1, so Type's saved width lands on
  Bank, or `moveSection` runs after `remember_columns`, so Reset layout does
  not return Bank to second place.

- **INV-12** — An account created from the import's Create-an-account dialog
  stores the bank typed there, and a blank one as NULL.
  *Test:* `tests/features/account_detect/test_wizard.py` and
  `tests/features/batch_import/test_batch_import_ui.py`, through each caller.
  The batch test's `_EnteredAccount` double gains `entered_bank`.
  *Breaks when:* a caller drops `bank=` from its `add_account` call.

## 6. Failure modes

- **A vault older than v17** runs every step to v18 in order (`run_migrations`).
  Nothing here is special to it.
- **A vault newer than this build** is refused by the existing
  `SchemaVersionError`, unchanged.
- **A backup from an earlier release** restores and migrates through v18. The
  backup suite's FIBR-0302 test (`tests/features/backup/spec.md` INV-20)
  restores real earlier-release `.fbk` files and asserts
  `LATEST_SCHEMA_VERSION`.
- **A saved layout from the five-column screen** is § 4.4's measured case.
  A damaged one is the existing byte-blob check in `remember_columns`.
- **A long bank name** widens the combos, like a long account name does today.
  No cap, matching `note`.

## 7. Tests

Each INV's test is named in § 5. Write each first and see it fail against the
unchanged code, except INV-9. It guards escaping that already holds, so it is
written once `account_label` exists and passes on its first run.

- INV-1, INV-2: `tests/features/accounts/test_migration_v18.py`.
- INV-3, INV-4, INV-5, INV-6, INV-10, INV-11: `tests/features/accounts/test_accounts.py`.
- INV-7, INV-8: beside each site's existing tests, with `account_label`'s
  unit test in `tests/features/accounts/test_accounts.py`.
- INV-9: `tests/features/pdf_export/test_pdf_export.py`.
- INV-12: `tests/features/account_detect/test_wizard.py` and
  `tests/features/batch_import/test_batch_import_ui.py`.

**Existing tests this change breaks, and the change each needs:**

- `tests/features/reconciliation/test_no_schema_change.py`: move the pin to
  18 and rename the test to `..._v18`. Its tripwire asks for this. Also move
  `tests/features/reconciliation/spec.md` INV-8's prose to v18, naming
  FIBR-0283's column.
- `tests/features/already_imported/test_migration_v17.py`: three asserts that
  `_version == 17` after a full `run_migrations` become `==
  LATEST_SCHEMA_VERSION`. The `v16` fixture also drops `accounts.bank`
  before setting version 16, or the re-run fails on a duplicate column
  (`ALTER TABLE ... DROP COLUMN` works on the bundled SQLite 3.51.1,
  measured).
- `tests/features/loan_sign/test_migration_v16.py::_back_to_v15`: drop
  `accounts.bank` for the same reason.
- A test that walks a vault to the latest version and asserts the exact
  `accounts` column set: its expected set gains `bank`.
  `grep -rn '_cols(conn, "accounts") ==' tests` finds each one.
- Every `update_account(` caller gains `bank=`. Counted by `grep -rn
  "update_account(" src tests --include=*.py`: one in `ui/accounts.py`, seven
  in `tests/features/accounts/test_accounts.py`, and one in
  `tests/features/forecast/test_forecast_tab.py`. The repository's `update`
  call in `test_accounts.py` (`repo.update(999_999, ...)`) gains a sixth
  argument.
- Accounts-screen tests that assume five columns (`range(5)`, column loops)
  are found by the first red run, and updated.

## 8. Alternatives considered (and rejected)

- **A closed list of banks.** It refuses a bank nobody has added yet, which is
  every bank but one today (§ 3 item 1).
- **Inferring the bank from the account number.** This is the guess the
  roadmap item exists to remove, and FIBR-0284 forbids it one layer down.
- **A separate `banks` table with a foreign key.** It adds a table, a
  migration and rename semantics, so that a typo fix reaches every
  account at once. Nothing reads a bank as an entity yet. Free text on the row
  is enough until something does, and moving to a table later is a
  data-preserving migration.
- **Bank as logical column 1.** It misapplies every saved layout (§ 4.4,
  measured).
- **Showing the bank everywhere an account is named, in this item.** The
  other sites (§ 9) are filters and lists where the user is not choosing
  between accounts, so the bank buys little there and widens this change.

## 9. Out of scope

- **Pre-filling the bank from a statement, and matching on it.** Tracked by
  FIBR-0284.
- **Showing the bank on the other surfaces that name an account**: the Home
  account filter, manual entry, the Transactions and Transfers views,
  the Statements table, Forecast, the export dialog's account checkboxes and
  the PDF transaction table's Account cell. Deferred; not yet queued.
- **Importers for other banks.** Tracked by FIBR-0074.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1, INV-2 | `tests/features/accounts/test_migration_v18.py` |
| INV-3 to INV-6 | `tests/features/accounts/test_accounts.py` |
| INV-7 | the `account_label` unit test in `test_accounts.py` |
| INV-8 | one test per site in § 4.3's table |
| INV-9 | `tests/features/pdf_export/test_pdf_export.py`, the markup-bank test |
| INV-10, INV-11 | `tests/features/accounts/test_accounts.py` |
| INV-12 | `test_wizard.py` and `test_batch_import_ui.py` |
| Sorting stays by name (§ 4.3) | **Partial:** the existing sort tests on each site, run with no bank. **nothing** checks the order with a bank set; low risk, since no site's sort key changes |
| No new log line carries the bank (trust boundary) | **nothing** — no test sweeps log output for account fields; review-code reads the diff |
| A new site named in § 4.3 but not switched | **Partial:** INV-8 covers the listed sites only; a site added later is unguarded |

## 11. Cross-doc impact

- `CHANGELOG.md`: an Added line under the next release.
- `tests/features/accounts/spec.md`: restates FIBR-0193's six-field order;
  becomes seven.
- `tests/features/reconciliation/spec.md` INV-8: v17 to v18 (§ 7).
- `docs/specs/FIBR-0193.md` INV-3 names six fields in order. It is a shipped
  spec; annotate it with a pointer here rather than rewrite it.
- `README.md`: the Accounts feature line, if it lists the fields.

## 12. Cold-eyes loop log

Rows live in `../reviews/FIBR-0283-bank-field-on-accounts-loop-log.md`.

## 13. Migration / compatibility

§ 4.1 is the whole of it: an in-place, nullable `ADD COLUMN` with no backfill.
A v18 vault opened by an older build is refused by that build's own
`SchemaVersionError`, as every earlier bump has been. That is why a bump ships
in a minor release (`versioning.md`).
