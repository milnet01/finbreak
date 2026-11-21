<!-- ants-spec-format: 1 -->
# FIBR-0087 — Give each account its own currency

**Status:** spec draft (2026-11-21).
**Kind:** feature.
**Source:** ROADMAP FIBR-0087 (user-request-2026-07-11, an offshore account
in the portfolio; revisits FIBR-0021).

**Blocker for:** FIBR-0487 (your own exchange rate and one combined total),
FIBR-0488 (checking an imported statement's currency).
**Pairs with:** FIBR-0283 (the v18 `accounts.bank` column — the precedent this
spec follows for the migration, the model and the Accounts screen).

*Layman: when you add an account you choose its currency, such as US dollars
for an offshore account. finbreak never adds rand and dollars together. Where
your accounts hold more than one currency, the dashboard lets you pick "All ZAR
accounts" or "All USD accounts", and every figure shows in that currency.*

## 1. Goal

Each account records its currency. It is chosen when the account is created,
and existing accounts take the vault's base currency. Every amount shows in its
own account's currency. No figure finbreak computes adds amounts from two
currencies together. A vault whose accounts all share one currency looks and
behaves exactly as it does today.

## 2. Problem

The vault has one currency. `vault.py::Vault.create` stores `base_currency` and
`minor_unit_exponent` in the `settings` table. No table has a currency column.
So:

1. **A foreign account's amounts are shown as base currency.** Every display
   site formats with `ui/_amount.py::_format_amount`, passing the code from
   `services/transactions.py::read_base_currency`. A USD account's $100 reads
   as R 100.
2. **Every figure computed across accounts adds them as one currency.**
   `services/reporting.py::ReportingService.summary`, `spending_by_category`,
   `monthly_trend` and `drill_down` take `account_ids`, where `None` means
   every account. The dashboard's "All accounts" passes `None`
   (`ui/home.py::HomeView`'s refresh). `services/month_summary.py::MonthSummaryService.summary`
   and the PDF export (`services/pdf_export.py::PdfExportService`) do the same.
3. **Four services read every account with no scope at all.**
   `services/recurring.py::RecurringService.snapshot` reads
   `repositories/recurring.py::RecurringRepository.recurring_rows`, which
   selects from `transactions` with no account filter.
   `services/alerts.py::AlertService.alerts` is vault-wide by design (its class
   docstring). `services/forecast.py::ForecastService._anchor` adds the latest
   balance of every `CASH_TYPES` account into one total.
   `services/transfer_detection.py::TransferDetectionService.candidates` pairs
   equal-and-opposite amounts in any two accounts.

## 3. Scope decisions (agreed with the user)

The user's decisions, 2026-11-21, recorded on the roadmap item:

1. **Separate figures per currency.** No live exchange rates, ever. The
   user also chose an optional typed-in rate that gives one combined total.
   The developer split that into **FIBR-0487** the same day, so each spec
   stays one review's size. Nothing in this spec converts.
2. **An account's currency can change only while the account is empty**, meaning
   it has no transactions and no imported statements. After that it is locked.

The developer's calls, under the user's standing delegation of spec design
(2026-07-15):

3. **Per-currency scopes, chosen in the dashboard's existing account
   selector**, rather than a panel per currency (§ 8). In a mixed vault the
   selector's "All accounts" item becomes one "All `<code>` accounts" item per
   currency. FIBR-0487 then adds its converted total as one more item.
4. **The check sits in the services, not the screens.** One function,
   `scope_currency`, either returns the single currency of an account set or
   refuses. Every service that adds amounts across accounts calls it. A screen
   that forgets to scope gets a refusal, not a wrong total.
5. **A recurring decision stays keyed on `(direction, merchant_key)`.**
   Confirming "Netflix" confirms it in every currency where it is detected.
   Splitting the key would need a migration of `recurring_decisions` for a
   case nobody has reported.

## 4. Design

### 4.1 Schema — migration v19

```python
def _migrate_to_v19(conn: dbapi2.Connection) -> None:
    with owned_transaction(conn):
        conn.execute("ALTER TABLE accounts ADD COLUMN currency TEXT")
        conn.execute(
            "UPDATE accounts SET currency = "
            "(SELECT value FROM settings WHERE key = 'base_currency')"
        )
        conn.execute("UPDATE schema_version SET version = 19")
```

Registered as `_MIGRATIONS[19]`; `LATEST_SCHEMA_VERSION = 19`. The column is
nullable because SQLite's `ADD COLUMN` cannot add `NOT NULL` without a constant
default, and the base currency is not a constant. Every existing row is
backfilled, so the stored value is explicit and does not depend on the base
currency staying fixed.

`Vault.create` writes `base_currency` into `settings` before it calls
`run_migrations`, so a new vault's seeded "Default" account is backfilled too.
A `.fbk` backup holds the whole `vault.db`, and restore runs `run_migrations`,
so backups need no change (as FIBR-0283 § 4.1 found).

### 4.2 Model and repository

`models.Account` gains `currency: str | None = None` **after `bank`**, so
`Account(*row)` stays aligned and the existing positional literals in tests
keep working. `repositories/accounts.py`:

- `list_all` and `get` select the eight columns in model order, `currency`
  last.
- `add(name, type, account_number, note, bank, currency)` and
  `update(account_id, name, type, account_number, note, bank, currency)`.
  **`currency` is required on both, with no default**, for FIBR-0283 § 4.2's
  reason: `update` issues an unconditional `SET`.

### 4.3 The currency rules — `services/currency.py` (new)

```python
class MixedCurrencyError(FinbreakError): ...   # in errors.py

def account_currency(account: Account, base: str) -> str:
    """account.currency, or base when it is NULL or blank."""

def account_currencies(conn) -> dict[int, str]:
    """Every account id -> its currency, through account_currency."""

def vault_currencies(conn) -> list[str]:
    """Each currency held by an account, once: the base currency first if any
    account holds it, then the rest in code order."""

def accounts_in(conn, currency: str) -> frozenset[int]:
    """The ids of the accounts in that currency."""

def scope_currency(conn, account_ids: frozenset[int] | None) -> str:
    """The one currency of the scope. None means every account. An empty set
    returns the base currency. Two or more currencies raise
    MixedCurrencyError, whose UserMessage asks for accounts in one currency."""

def account_currency_choices(conn) -> list[str]:
    """The codes in auth.CURRENCY_EXPONENTS whose exponent equals the vault's
    minor_unit_exponent: base first, then code order."""
```

`account_currency`'s fallback covers a NULL written outside the app and a
hand-built `Account` in a test. Nothing in the app writes NULL.

**Why the exponent filter.** Amounts are stored as integer minor units at the
vault's single `minor_unit_exponent` (`models.py` states it). A currency with a
different exponent would be stored at the wrong scale. All six codes in
`CURRENCY_EXPONENTS` have exponent 2 today, so the filter changes no choice.
It stops a later 0- or 3-decimal entry from being offered to an account (§ 9).

### 4.4 Account service

`services/accounts.py`:

- `add_account(..., currency: str | None = None)`. `None` stores the base
  currency.
- `update_account(..., currency: str)`, keyword-only and **required**, beside
  `bank`.
- Both refuse a code not in `account_currency_choices` with
  `ValueError(UserMessage("unsupported currency"))`.
- `update_account` refuses to **change** the currency of an account in use with
  `AccountInUseError`, and the message says the currency cannot change once
  the account holds transactions or statements. Passing the stored currency
  again is not a change.
- `is_in_use(account_id) -> bool`: the account has a transaction
  (`TransactionRepository.count_for_account`) or a statement period
  (`StatementPeriodRepository.list_for_account`). `delete_account`'s two
  guards use the same two checks. They keep their own two messages.

### 4.5 Where the scope is enforced

Each of these calls `scope_currency(conn, account_ids)` before reading rows,
and lets `MixedCurrencyError` propagate:

| Service | Methods |
|---|---|
| `ReportingService` | `summary`, `spending_by_category`, `monthly_trend`, `drill_down` |
| `MonthSummaryService` | `summary` |
| `PdfExportService` | `render_pdf_bytes`, so `export` too. The header's currency is the scope's |

These take a `currency` and read only that currency's accounts:

| Service | Change |
|---|---|
| `RecurringService` | `snapshot`, `candidates`, `confirmed` and `summary` run detection once per currency in `vault_currencies`. `RecurringRepository.recurring_rows(account_ids)` gains the filter. `RecurringItem` gains `currency: str`, last. `summary(today, currency)` sums only that currency's confirmed items |
| `AlertService` | `alerts(today)` runs each detector once per currency, over that currency's accounts. `SpendingAlert` gains `currency: str`, last. An alert in the base currency keeps today's `key`; any other appends `:<code>`, so existing dismissals still match |
| `ForecastService` | `forecast(today, horizon, currency)` and `has_confirmed(today, currency)`. The anchor adds only `CASH_TYPES` accounts in that currency; the inputs are that currency's confirmed recurring items |
| `TransferDetectionService` | `candidates` pairs a debit and a credit only when both accounts have the same currency. `TransferCandidate` carries that currency for display |

### 4.6 The dashboard (`ui/home.py`)

The account selector's items depend on `vault_currencies`:

- **One currency** (or none): "All accounts", then each account. This is
  today's list exactly.
- **Two or more**: one item per currency, in `vault_currencies` order, with the
  text `self.tr("All {currency} accounts").format(currency=code)`. Then each
  account.

An item's data is a scope: a currency and either `None` (all of it) or one
account id. The refresh passes `accounts_in(currency)` or `{id}` as
`account_ids`, except that the single-currency "All accounts" still passes
`None`. The symbol for every figure is the scope's currency. The recurring card
reads `summary(today, scope.currency)`. The Alerts button counts that
currency's alerts. A held selection is kept across refreshes as today. If its
currency item disappears, the selection falls back to the first item.

The export dialog (`ui/export_dialog.py`) is pre-filled from the scope's
account set instead of one selected id, so exporting from "All USD accounts"
starts with the USD accounts ticked. Its existing validation, which already
returns "Choose at least one account.", also returns
`self.tr("Choose accounts that share one currency.")` when the ticked accounts
hold two currencies. So the dialog never hands the service a mixed scope.

### 4.7 Per-row display

Each site below formats with the currency of the account its amount belongs
to, not `read_base_currency`:

| Site | Which currency |
|---|---|
| `ui/transactions.py` row amount and Currency column | the transaction's account |
| `ui/transfers.py` | the candidate's or pair's currency |
| `ui/recurring.py` | the item's `currency` |
| `ui/alerts_dialog.py` | the alert's `currency` |
| `ui/accounts.py` reconciliation "off by" | the selected account |
| `ui/import_wizard.py` preview | the target account |
| `ui/forecast.py` | the Forecast tab's chosen currency (below) |

The **Forecast tab** gains a currency combo listing `vault_currencies`. It is
hidden when that list has one entry or none, so a single-currency vault sees no
change.

The Settings dialog still shows "Base currency". It is now the default for new
accounts, and the text is unchanged.

### 4.8 Choosing a currency

- **Accounts screen** (`ui/accounts.py`): a `self._currency` `QComboBox` over
  `account_currency_choices`, beside Bank. Add starts at the base currency and
  goes back to it after an add. Selecting a row shows its currency, and
  disables the combo when `is_in_use(account.id)`, with a tooltip saying why.
  The table gains a Currency column as **logical column 6, appended last**,
  for the saved-layout reason FIBR-0283 § 4.4 measured.
- **Create-an-account dialog** (`ui/account_create.py::CreateAccountDialog`):
  a Currency row, a keyword `currencies: Sequence[str] = ()`, and
  `entered_currency() -> str`. It starts at the first entry, the base currency.
  Both callers, `ui/import_wizard.py` and `ui/import_batch.py`, pass
  `currencies=account_currency_choices(conn)` and
  `currency=dialog.entered_currency()`.

Every new user-visible string uses `self.tr` or `QCoreApplication.translate`
with a literal, and every refusal uses `UserMessage(QT_TRANSLATE_NOOP(...))`,
as `tests/features/i18n/test_translatable_strings.py` requires.

## 5. Invariants

**Trust boundary.** The currency is chosen from a fixed list, and the services
refuse anything else. A value written outside the app reaches the screen
through `_format_amount`, which falls back to printing the code. It reaches the
PDF header through `_header_html`, which escapes it. Nothing here adds a log
line carrying a field value.

- **INV-1** — A v18 vault upgrades in place to v19. `accounts` gains exactly
  one column, `currency`, and every existing row reads the vault's
  `base_currency`, with its other values unchanged. A new vault's Default
  account reads the base currency chosen at first run.
  *Test:* `tests/features/accounts/test_migration_v19.py`, modelled on
  `test_migration_v18.py`. A "USD" first-run vault is used for the new-vault
  leg, so a hard-coded "ZAR" fails it.
  *Breaks when:* the backfill is missing, so rows read NULL, or it writes a
  constant code.

- **INV-2** — A failure inside the v19 step leaves a v18 vault with no
  `currency` column, and a re-run then upgrades it.
  *Test:* the same file, with `raising_conn` failing on `UPDATE schema_version
  SET version = 19`, after the `ALTER` and the backfill have run.
  *Breaks when:* the step runs outside `owned_transaction`.

- **INV-3** — Both read paths return all eight fields in model order, and a
  stored currency reads back as stored.
  *Test:* extend `test_accounts.py`'s FIBR-0283 INV-3 round trip with
  `currency="USD"`.
  *Breaks when:* a `SELECT` omits `currency`, so the model's default absorbs it.

- **INV-4** — `add_account` stores the base currency when given none, and the
  given code otherwise. It refuses a code outside `account_currency_choices`.
  *Test:* a ZAR vault: no currency gives "ZAR", "USD" gives "USD", "XYZ"
  raises `ValueError`. A vault whose `minor_unit_exponent` is set to 3 offers no
  choices and refuses "USD". The exponent leg is the only fixture where
  membership of `CURRENCY_EXPONENTS` passes and the exponent rule alone refuses.
  *Breaks when:* the code is not checked, or only membership is checked.

- **INV-5** — `update_account` requires `currency`. It changes the currency of
  an empty account. It refuses a change on an account with a transaction, and
  on one with a statement period but no transactions. Passing the stored
  currency to an in-use account succeeds.
  *Test:* `test_accounts.py`: the four cases, plus `pytest.raises(TypeError)`
  for a call without `currency`. The statement-period-only case is what fails
  a lock that checks transactions alone.
  *Breaks when:* the lock checks transactions only, or refuses every update to
  an in-use account.

- **INV-6** — `scope_currency` returns the single currency of its scope.
  `None` in a single-currency vault returns the base currency. `None`, or a set
  holding two currencies, in a mixed vault raises `MixedCurrencyError`. An
  empty set returns the base currency.
  *Test:* `tests/features/currency/test_scope.py` (new), with one ZAR and one
  USD account.
  *Breaks when:* `None` is treated as "base currency" without looking at the
  accounts.

- **INV-7** — Each method in § 4.5's first table raises `MixedCurrencyError` for
  a mixed scope, and returns today's result for a single-currency one.
  *Test:* `tests/features/currency/test_scope.py`, one case per method, with a
  ZAR and a USD account each holding one transaction.
  *Breaks when:* a method reads rows without calling `scope_currency`.

- **INV-8** — Recurring detection never groups across currencies. The same
  merchant, monthly in a ZAR account and in a USD account, gives two items,
  one per currency. `summary(today, "USD")` counts only the USD one.
  *Test:* `tests/features/recurring/`, beside the existing detection tests.
  *Breaks when:* `recurring_rows` is not filtered, so the two streams merge into
  one item.

- **INV-9** — Alerts are computed per currency. A base-currency alert's key is
  unchanged from today. The same alert in USD has the key plus `:USD`. A
  dismissal stored before this change still hides its alert.
  *Test:* `tests/features/spending_alerts/`, with a category spiking in both currencies.
  *Breaks when:* the suffix is added to every key, so stored dismissals stop
  matching, or no suffix is added, so the two alerts collide.

- **INV-10** — The forecast anchor and inputs hold only the chosen currency.
  *Test:* `tests/features/forecast/`, with a ZAR and a USD cash account, each
  with a closing balance. `forecast(today, horizon, "USD")`'s anchor is the USD
  balance alone.
  *Breaks when:* `_anchor` sums every cash account.

- **INV-11** — Transfer detection never pairs accounts of different currencies.
  *Test:* `tests/features/transfers/`: −100.00 in a ZAR account and +100.00 in a
  USD account on the same day give no candidate. The same pair between two ZAR
  accounts gives one, which isolates the currency rule from the amount and
  date rules.
  *Breaks when:* `candidates` compares amounts only.

- **INV-12** — In a single-currency vault the dashboard selector's items are
  "All accounts" then each account, and the Forecast tab's currency combo is
  hidden. In a mixed vault the selector starts with "All ZAR accounts", "All USD
  accounts", and choosing the USD item renders every figure with the USD
  symbol from the USD account's transactions only.
  *Test:* `tests/features/dashboard/`, the two vaults.
  *Breaks when:* the single-currency list changes, or the USD scope passes
  `None`.

- **INV-13** — Each site in § 4.7's table shows the right currency's symbol.
  *Test:* one test per site, with a USD account, asserting "$" in the
  rendered text and "R" absent.
  *Breaks when:* any site still reads `read_base_currency`.

- **INV-14** — The Accounts screen round-trips the currency. Add stores the
  chosen code. Selecting an in-use account disables the combo. The Currency
  column is logical 6 and shows the stored code. A six-column saved layout
  restores with each old column unchanged and Currency last.
  *Test:* `tests/features/accounts/test_accounts.py`, beside FIBR-0283 INV-10
  and INV-11.
  *Breaks when:* the column is inserted before Bank, or the combo stays
  enabled on an account holding transactions.

- **INV-15** — An account created from the import's Create-an-account dialog
  stores the currency chosen there.
  *Test:* `tests/features/account_detect/test_wizard.py` and
  `tests/features/batch_import/test_batch_import_ui.py`, through each caller.
  *Breaks when:* a caller drops `currency=` from its `add_account` call, so the
  account silently takes the base currency.

- **INV-16** — The export dialog refuses a selection holding two currencies,
  with "Choose accounts that share one currency.", and accepts one holding a
  single currency. Opened from a USD scope, it starts with exactly the USD
  accounts ticked.
  *Test:* `tests/features/pdf_export/test_export_dialog.py`, in a vault with a ZAR and a USD account.
  *Breaks when:* the dialog validates only the count of ticked accounts, so
  "All accounts" in a mixed vault reaches the service.

## 6. Failure modes

- **A vault older than v18** runs every step to v19 in order.
- **A vault newer than this build** is refused by `SchemaVersionError`,
  unchanged.
- **A backup from an earlier release** restores and migrates through v19
  (`tests/features/backup/` INV-20's fixtures).
- **A NULL or blank currency**, written outside the app, reads as the base
  currency (`account_currency`).
- **An unknown code**, written outside the app, is treated as its own currency.
  It gets its own scope and shows as the code. The account cannot be edited to
  keep it, because the service refuses an unsupported code.
- **A screen that passes a mixed scope** gets `MixedCurrencyError`. No screen
  is meant to: the dashboard's selector offers only single-currency scopes
  (INV-12), and the export dialog refuses a mixed selection (INV-16). The
  dashboard's slots catch only `VaultLockedError` and the export slot in
  `ui/main_window.py` catches `VaultLockedError`, `OSError` and
  `pikepdf.PdfError`. So a mixed scope that gets through is an uncaught error,
  which shows the bug rather than a wrong total.
- **A held dashboard selection whose currency no longer exists** (its last
  account deleted) falls back to the first item.

## 7. Tests

Each INV's test is named in § 5. Write each first and see it fail against the
unchanged code.

`tests/features/currency/` is a new suite. It reads no doc, so it goes in
`tests/features/prose_checks/`'s `_NO_PROSE` ledger, or that guard fails.

**Existing tests this change breaks, found the way FIBR-0283 § 7 found them:**

- `tests/features/reconciliation/test_no_schema_change.py`: the pin moves to 19,
  and `tests/features/reconciliation/spec.md` INV-8's prose moves with it.
- Tests that assert `_version == 18` after a full `run_migrations` become
  `== LATEST_SCHEMA_VERSION`. Fixtures that rebuild an older vault also drop
  `accounts.currency`. The first red run finds each.
- Tests that assert the exact `accounts` column set gain `currency`:
  `grep -rn '_cols(conn, "accounts") ==' tests`.
- Every `update_account(` and `AccountRepository.update(` caller gains the
  currency: `grep -rn "update_account(\|\.update(" src tests --include=*.py`.
- Accounts-screen tests that assume six columns, and recurring, alert,
  forecast and transfer tests that construct `RecurringItem`, `SpendingAlert` or
  `TransferCandidate` positionally, are found by the first red run.

## 8. Alternatives considered (and rejected)

- **A currency on each transaction.** A statement belongs to one account, and
  an account holds one currency. A per-row currency would let one account mix
  currencies, which is the problem this spec removes.
- **A panel per currency on the dashboard.** It doubles every widget: tiles,
  columns, donut, trend and month summary. The selector reuses the whole
  dashboard for each currency, and gives FIBR-0487 an obvious place for a
  converted scope.
- **Enforcing the rule in the screens only.** Every screen would have to
  remember. A service-side check turns a forgotten scope into a refusal.
- **A nullable column with no backfill, NULL meaning "base".** Correct today,
  because the base currency cannot be edited. It becomes wrong silently the day
  it can. The backfill costs one statement.
- **A currency that can always be changed.** The user ruled it out
  (§ 3 item 2): it would relabel amounts already imported.

## 9. Out of scope

- **Your own exchange rate and one combined total.** Tracked by FIBR-0487.
- **Checking an imported statement's currency against its account.** Tracked by
  FIBR-0488.
- **Currencies with no or three decimal places.** They need a per-account
  scale. Deferred; not yet queued.
- **Changing the vault's base currency.** Deferred; not yet queued.
- **Showing the currency in account labels** (pickers, filters). Deferred; not
  yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1, INV-2 | `tests/features/accounts/test_migration_v19.py` |
| INV-3 to INV-5, INV-14 | `tests/features/accounts/test_accounts.py` |
| INV-6, INV-7 | `tests/features/currency/test_scope.py` |
| INV-8 | `tests/features/recurring/` |
| INV-9 | `tests/features/spending_alerts/` |
| INV-10 | `tests/features/forecast/` |
| INV-11 | `tests/features/transfers/` |
| INV-12 | `tests/features/dashboard/` |
| INV-13 | one test per site in § 4.7 |
| INV-15 | `test_wizard.py` and `test_batch_import_ui.py` |
| INV-16 | `tests/features/pdf_export/test_export_dialog.py` |
| A single-currency vault behaves as today | **Partial:** the existing suite, which runs single-currency vaults only, passes with only § 7's listed edits. **nothing** checks a figure computed by a service this spec does not name |
| A new cross-account sum added later calls `scope_currency` | **nothing** — no test finds new summing code; review-code reads the diff |

## 11. Cross-doc impact

- `CHANGELOG.md`: an Added line under the next release.
- `README.md`: the accounts feature line, and any line saying finbreak is
  single-currency.
- `tests/features/accounts/spec.md`: the account field order gains `currency`.
- `tests/features/reconciliation/spec.md` INV-8: v18 to v19.
- `docs/specs/FIBR-0283-bank-field-on-accounts.md` INV-3 names seven fields.
  It is a shipped spec; annotate it with a pointer here.
- The recurring, alerts and forecast feature specs under `tests/features/`
  that say "vault-wide" gain "per currency".
- `docs/decisions/`: the FX ADR the roadmap item names is written with
  FIBR-0487, where conversion is decided.

## 12. Cold-eyes loop log

Rows live in `../reviews/FIBR-0087-per-account-currency-loop-log.md`.

## 13. Migration / compatibility

§ 4.1 is the whole of it: an in-place `ADD COLUMN` with a backfill from the
vault's own setting. A v19 vault opened by an older build is refused by that
build's `SchemaVersionError`. `versioning.md` § 2's vault row makes an additive
migration that loses nothing a MINOR change.
