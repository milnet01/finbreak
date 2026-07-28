# FIBR-0193 — Store an optional account number and note on each account

**Status:** spec draft (2026-07-28).
**Kind:** feature.
**Source:** ROADMAP FIBR-0193, split out of FIBR-0113 on 2026-07-28 executing
`/cold-eyes` loop 5's recommendation (`docs/reviews/FIBR-0113-cold-eyes-loop5.md`).
**Blocker for:** FIBR-0113 (the Accounts table renders and edits these two
columns, so it cannot start until they exist).
**Pairs with:** FIBR-0086 (§9 — its account-number *storage* half lands here;
its detection + matching half does not), FIBR-0005 (§12 — this widens the
`Account` shape and the repository signatures that spec pins).

**Layman:** Each account gets two new optional boxes in the encrypted vault — a
reference account number and a free-text note. This item only builds the
storage; the screen that shows and edits them is FIBR-0113.

## 1. Goal

`models.Account` carries an optional `account_number` and `note`, stored in two
new nullable `accounts` columns behind schema migration v13, and readable and
writable through `AccountRepository` and `AccountService` on both the add and
the update path. A blank field is stored as SQL `NULL`, not as an empty string.
No new user-visible behaviour arrives: nothing displays or edits either field
until FIBR-0113 ships. One existing surface does change, invisibly —
`ui/accounts.py::AccountsWidget._on_update` must pass the two new arguments or
it stops compiling against the new signature, so it reads the selected
account's current values and passes them straight back (§3 decision 5).

## 2. Problem

`models.py::Account` carries `id`, `name`, `type`, `created_at` and nothing
else. Two consequences — the first raised while dogfooding v0.1.0 (FIBR-0086,
`Source: user-request-2026-07-11`), the second by user request on 2026-07-12
(FIBR-0113):

1. **There is nowhere to put an account number.** A user with two "Cheque"
   accounts at different banks has no way to tell them apart, and FIBR-0086's
   import auto-detect has no column to match a statement's account number
   against.
2. **There is nowhere to put a note.** Same cause — the row has no free-text
   field of any kind.

The gap is purely at the storage layer: `AccountRepository.list_all()` and
`.get()` select four columns, `.add()` and `.update()` write two, and
`AccountService.add_account` / `.update_account` pass exactly those through.

## 3. Scope decisions

Settled with the user on 2026-07-28 (1), or by the author from §2 (2–4):

1. **Both fields live in the encrypted vault, not the plaintext window INI**
   (user). An account number is financial reference data. The vault is
   SQLCipher, so both columns are encrypted at rest by the master key with no
   redundant second layer — the same posture `accounts.statement_pdf_password`
   already takes (FIBR-0009 D5).
2. **`AccountService.update_account`'s two new parameters are REQUIRED, not
   defaulted** (author). `AccountRepository.update` issues an unconditional
   `UPDATE … SET`, so a defaulted `None` would make every existing
   three-argument call silently erase a stored account number and note. There
   are six such call sites today, listed in §4.2. Required parameters turn each
   into a loud failure instead of silent data loss in a money app — the same
   loud-refusal posture the rest of the codebase takes. §11 records that this is
   only *partly* mechanically caught.
3. **`add_account`'s two parameters are optional keyword arguments** (author).
   Its callers create an account that genuinely has neither field, and `add`
   issues an `INSERT`, where a default is harmless — an omitted column is
   written `NULL`, which is the value the caller meant. The asymmetry with
   decision 2 is deliberate and is the whole point: the danger is the
   unconditional overwrite, not the insert.
4. **Neither field is validated for format, and neither participates in the
   duplicate-name check** (author). An account number is a reference the user
   types, not a matching key — FIBR-0086 owns normalisation and matching, and
   normalising here would store a value the user did not type while that item
   is still unbuilt.
5. **`ui/accounts.py::AccountsWidget._on_update` is updated *in this item*, to
   read the selected account's current `account_number` / `note` and pass them
   back unchanged** (author). It is the only production caller of
   `update_account`, and decision 2 makes the two parameters required — so
   leaving it three-argument raises `TypeError` on every "Update selected"
   click (its `except (ValueError, FinbreakError)` does not catch that) and
   fails the existing FIBR-0005 INV-7f `qtbot` leg. Passing `None, None`
   instead is the exact unconditional-overwrite erasure decision 2 exists to
   prevent — harmless *today* only because no surface can set either field yet,
   which is precisely the kind of "safe for now" landmine this spec refuses.
   Read-and-pass-back is the shortest change that is correct at every point in
   the sequence. This is the **one** UI edit in scope here; the Accounts tab
   itself remains FIBR-0113's (§9), which replaces this passthrough with real
   form fields. INV-7 locks it.

## 4. Design

### 4.1 Schema — migration v13

`migrations.py::LATEST_SCHEMA_VERSION` becomes 13 and `_MIGRATIONS` gains a
`13:` entry. Two existing steps are *pure* nullable `ADD COLUMN`s with no
backfill — `_migrate_to_v5` (which is also the precedent for adding a nullable
`TEXT` column to `accounts` specifically) and `_migrate_to_v11`. The closest
**shape** match is `_migrate_to_v7`, the only step issuing two `ADD COLUMN`s
inside one `owned_transaction`, though it additionally creates a table.
(`_migrate_to_v6` is *not* a precedent here: it backfills.) The step carries the
same explanatory docstring every existing step does (all eleven have one):

```python
def _migrate_to_v13(conn: dbapi2.Connection) -> None:
    """v12->v13: add the nullable ``accounts.account_number`` and
    ``accounts.note`` columns for FIBR-0193. ..."""
    with owned_transaction(conn):
        conn.execute("ALTER TABLE accounts ADD COLUMN account_number TEXT")
        conn.execute("ALTER TABLE accounts ADD COLUMN note TEXT")
        conn.execute("UPDATE schema_version SET version = 13")
```

Both columns are nullable with no default, so SQLite backfills existing rows
with `NULL` in place — no table rebuild, no FK churn. No backfill is possible
or wanted: the data has never been collected. Idempotency is version-gating, as
for every other step: `run_migrations` calls this only for a vault at exactly
v12, so the bare `ALTER`s never replay.

`vault.py::SCHEMA_VERSION` is a **different constant** and stays at 1. It is
the baseline version `create()` stamps on a brand-new vault, which
`run_migrations` then walks up to `LATEST_SCHEMA_VERSION`. Bumping it would
skip every migration step on a fresh vault.

Neither column is length-capped, deliberately. `TEXT` is unbounded, and the
reason is not row count — a single pasted 10 MB note would be unbounded however
few accounts exist. It is that nothing downstream parses, indexes, matches or
aggregates either field: both are inert reference strings. The cost of a
pathological value is therefore a wide table cell FIBR-0113's user can resize,
not a slow query or a broken import. This is a deliberate departure from
spec-format §4 ("no unbounded growth ships without a named cap"), recorded here
rather than left implicit: the growth is bounded by what a user types into one
field on one row per account.

### 4.2 Model, repository and service

`models.py::Account` gains two optional fields **appended after `created_at`**,
and gains the field-order docstring its sibling `Transaction` already carries
for exactly this reason (`Transaction`'s says "the ``list_all`` SELECT names all
eight columns in this order so ``Transaction(*row)`` stays aligned"):

```python
@dataclass
class Account:
    """One row of the ``accounts`` table. ``account_number`` / ``note``
    (appended after ``created_at`` at v13, FIBR-0193) are optional reference
    fields; both read paths name all six columns in this order so
    ``Account(*row)`` stays aligned."""

    id: int
    name: str
    type: str
    created_at: str
    account_number: str | None = None
    note: str | None = None
```

**The two defaults are required, and they cost something.** They are needed
because `Account` is constructed positionally with four arguments outside the
repository — `tests/features/pdf_export/test_export_dialog.py` builds
`Account(1, "Current", "current", "2026-01-01T00:00:00Z")` at module scope —
and defaultless fields would break every such literal. The cost is that they
also absorb a mistake: the sibling `Transaction` dataclass has **no** defaults,
so a SELECT that was never widened raises `TypeError` on arity there, loudly.
Here it would construct silently and yield `None` for both fields. INV-3 is
written to fail on that state rather than rely on an arity error that no longer
happens.

`repositories/accounts.py::AccountRepository` builds `Account(*row)`
positionally in both `list_all()` and `get()`, so both SELECTs grow the two
columns **in dataclass field order** — `id, name, type, created_at,
account_number, note`. `list_all()`'s `ORDER BY name COLLATE NOCASE, id` is
unchanged. `statement_pdf_password` stays out of every listing SELECT, as
today: it is reached only through the dedicated `get_pdf_password` /
`set_pdf_password` / `ids_with_pdf_password` accessors (FIBR-0128 INV-1).

`AccountRepository`'s own writers grow the columns, both with the parameters
**required** — `update` is the layer that issues the unconditional
`UPDATE … SET`, so a default there would defeat §3 decision 2 one layer below
the service, and `add` matches for symmetry rather than because an `INSERT`
default would be dangerous:

```python
def add(self, name: str, type: str,
        account_number: str | None, note: str | None) -> int: ...

def update(self, account_id: int, name: str, type: str,
           account_number: str | None, note: str | None) -> None: ...
```

`update`'s `SET` clause grows both columns — `UPDATE accounts SET name = ?,
type = ?, account_number = ?, note = ? WHERE id = ?`. Accepting the two
parameters without adding them to the `SET` clause is the failure INV-6 exists
to catch (§5).

`services/accounts.py::AccountService` grows the fields on both write paths,
asymmetrically per §3 decisions 2 and 3:

```python
def add_account(self, name: str, type: str, *,
                account_number: str | None = None,
                note: str | None = None) -> Account: ...

def update_account(self, account_id: int, name: str, type: str, *,
                   account_number: str | None,
                   note: str | None) -> None: ...
```

The **six** existing three-argument `update_account` call sites, all of which
must be updated (measured 2026-07-28 with
`grep -rn 'update_account(' src tests scripts`):

| Call site | Caught by |
|---|---|
| `ui/accounts.py::AccountsWidget._on_update` | mypy (the one annotated caller), plus the FIBR-0005 INV-7f `qtbot` Update round-trip in `tests/features/accounts/test_accounts.py`. **Changed here, not deferred** — §3 decision 5, locked by INV-7 |
| `tests/features/accounts/test_accounts.py` — four calls | the test run |
| `scripts/seed_demo_vault.py` | **nothing** — see §11 |

Plus one **direct repository** call — `AccountRepository.update` in
`tests/features/accounts/test_accounts.py`'s missing-id no-op test — which the
repository signature change above also breaks, and which is easy to miss
because it does not go through the service.

`_validate` keeps its signature and its single `-> str` return. Optional-field
normalisation is a **separate** module-level helper in the same module, called
by `add_account` **and** `update_account` **inside the service**, so INV-5 holds
for every service caller rather than only for a future UI:

```python
def _normalise_optional(value: str | None) -> str | None:
    """Strip, and collapse an empty result to None — so a blank form field is
    stored as SQL NULL rather than "" (INV-5)."""
    return (value or "").strip() or None
```

## 5. Invariants

- **INV-1** — A vault at v12 upgrades to v13 in place, gaining exactly
  `accounts.account_number` and `accounts.note`, **both nullable**, with every
  pre-existing account row still present and its other columns unchanged.
  *Test:* `tests/features/accounts/test_migration_v13.py` — legs 1 and 2 (§7).
  Nullability needs a **wider reader than the precedent's**: `_cols()` in
  `test_migration_v11.py` returns `{r[1] …}`, i.e. column *names* only, so the
  leg reads whole `PRAGMA table_info(accounts)` rows and asserts each new
  column's `notnull` field is `0` (§7 leg 1). Leg 2 additionally asserts the
  seeded `transactions` rows survive and `PRAGMA foreign_key_check` returns
  empty — the FK half of this claim, which a check on `accounts` alone cannot
  see.
  *Breaks when:* the step rebuilds `accounts` (CREATE / COPY / DROP / RENAME)
  instead of issuing two `ADD COLUMN`s, dropping rows or breaking the
  `transactions.account_id` and `statement_periods` FK targets. The nullability
  half breaks on `ADD COLUMN … NOT NULL DEFAULT ''`, which SQLite **accepts** —
  so every existing row silently gains `""` where the design says `NULL`, and
  INV-5's blank-is-`NULL` contract is defeated at the schema level with no
  error anywhere. (Bare `NOT NULL` with no default is rejected by SQLite and
  fails loudly on its own; it is the `DEFAULT ''` variant this flag catches.)

- **INV-2** — `LATEST_SCHEMA_VERSION == 13` and `13 in _MIGRATIONS` — the
  constant and the dispatch table agree.
  *Test:* `.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from
  finbreak.migrations import LATEST_SCHEMA_VERSION, _MIGRATIONS;
  print(LATEST_SCHEMA_VERSION, 13 in _MIGRATIONS)"` → `13 True`.
  (Run 2026-07-28 against pre-implementation source: `12 False` — red, as it
  must be before the work.) Also leg 3 of `test_migration_v13.py`.
  *Breaks when:* the constant is bumped without registering the step —
  `run_migrations`'s `for target in range(current + 1, LATEST + 1)` then
  indexes `_MIGRATIONS[13]` and raises `KeyError` on **every** vault open and
  every vault create, so the app cannot start at all. The reverse — a step
  registered without bumping the constant — would let the columns never appear,
  but it is **not** silent: `tests/features/reconciliation/test_no_schema_change.py::test_INV8_no_unregistered_next_migration`
  asserts `LATEST_SCHEMA_VERSION + 1 not in _MIGRATIONS`, which fails loudly in
  exactly that state (and leg 3 catches it too).

- **INV-3** — `Account`'s field order and the SELECT column order in both
  `AccountRepository.list_all()` and `.get()` agree, so positional
  `Account(*row)` construction assigns each column to the field of that name.
  *Test:* `tests/features/accounts/test_accounts.py`, asserting a saved
  account reads back with `account_number` and `note` equal to what was
  written — by field name, on **both** read paths.
  *Breaks when:* a column is appended to one SELECT but not the other, or
  inserted before `created_at` in one of them — e.g. `SELECT id, name, type,
  account_number, created_at, note`, which lands `created_at`'s timestamp in
  the `account_number` field and raises nothing. **The dataclass defaults make
  the un-widened case silent too:** a SELECT left at four columns would, without
  defaults, raise `TypeError` on arity — with them it constructs happily and
  yields `None` for both fields, so a read path nobody widened looks exactly
  like an account that has no number. That is the specific state this invariant
  must fail on, and it is why the leg asserts round-tripped *values* rather than
  merely that construction succeeds.

- **INV-4** — Within `repositories/accounts.py`, `statement_pdf_password` is
  named only inside the three dedicated accessors — no listing query in that
  file selects it (re-asserts FIBR-0128 INV-1 at source level, where it has no
  test today). Scoped to that file deliberately: the test walks one module, so
  claiming "no listing query anywhere" would assert more than it exercises.
  *Test:* `tests/features/accounts/test_accounts.py`, walking
  `repositories/accounts.py` with `ast.parse` and asserting the column name
  appears only inside the `get_pdf_password` / `set_pdf_password` /
  `ids_with_pdf_password` function bodies — an AST walk, because a substring
  scan cannot attribute a hit to its enclosing function. The test locates the
  module through the imported symbol
  (`Path(finbreak.repositories.accounts.__file__)`), not a path relative to the
  test file, so it keeps working if either tree moves.
  *Breaks when:* someone widens the `list_all` SELECT to carry the saved-password
  flag directly instead of calling `ids_with_pdf_password()`, putting every
  stored statement password into every account listing.

INV-5 and INV-6 divide one surface and the split is deliberate: **INV-5 owns
`""` → `NULL` conversion, INV-6 owns whether a written value lands at all.**
The blank-`update_account` case would satisfy either, so it is stated once, in
INV-6, and INV-5's test does not repeat it.

- **INV-5** — A blank account number or note passed through
  `AccountService.add_account` is stored as SQL `NULL`, not as an empty string;
  and `_normalise_optional` is applied on **both** service write paths, so
  `update_account` converts identically. Scoped to service callers deliberately:
  normalisation lives in `services/accounts.py`, so a caller going straight to
  `AccountRepository` bypasses it (§6).
  *Test:* `tests/features/accounts/test_accounts.py` — assert
  `account_number IS NULL` and `note IS NULL` after `add_account` with both
  fields empty, and assert `_normalise_optional` is called from both
  `add_account` and `update_account` (an `ast.parse` of `services/accounts.py`
  asserting the call appears in both function bodies — the same technique
  INV-4 uses, and the only way to observe the *update* path's normalisation
  without duplicating INV-6's write leg).
  *Breaks when:* the service passes the raw string to the repository without
  `_normalise_optional`, so `""` is stored and any later `IS NOT NULL` check
  counts a blank field as filled. Normalising in `add_account` only is the
  specific asymmetry the AST leg exists to catch — a behavioural leg on the
  update path cannot distinguish it from INV-6's failure.

- **INV-6** — `AccountService.update_account` **persists** both new fields:
  editing a stored account number writes the new value, and clearing a filled
  field to blank writes SQL `NULL` back over it.
  *Test:* `tests/features/accounts/test_accounts.py` — add an account with both
  fields set; `update_account` with **new** values for both and assert both
  changed, re-read through `get()`; then `update_account` passing `"   "` for
  **both** fields and assert both are now `NULL`.
  *Breaks when:* `AccountRepository.update` accepts the two new parameters but
  never adds them to its `SET` clause. INV-3 does not catch this — it covers the
  read paths, and a round-trip through `add` alone stays green. INV-5 does not —
  its behavioural leg is on `add_account`, and its AST leg observes that
  `_normalise_optional` is *called*, not that the normalised value reaches the
  database. In that state an edited account number is silently dropped and a
  cleared field silently keeps its old value. §3 decision 2 defends against
  *callers omitting* the arguments; this defends against the *repository
  ignoring* them.

- **INV-7** — `ui/accounts.py::AccountsWidget._on_update` passes the selected
  account's existing `account_number` and `note` through unchanged, so an
  Update that edits only the name or type leaves both stored fields intact
  (§3 decision 5).
  *Test:* `tests/features/accounts/test_accounts.py` — a `qtbot` leg: seed an
  account with both fields set, select it in the widget, change the name, press
  Update, and assert the reloaded account still carries both original values
  **and** the new name.
  *Breaks when:* `_on_update` passes `None, None` to satisfy the new required
  parameters. Every other invariant here stays green — the repository writes
  exactly what it was given, and no other test drives that handler with a
  populated account — while the unconditional `UPDATE … SET` erases both fields
  on any edit. That is precisely the silent data loss §3 decision 2 exists to
  prevent, arriving through the one caller the decision cannot protect by making
  the parameters required. It is unreachable *today* (nothing can set either
  field yet) and reachable the moment FIBR-0113 ships, which is why it is
  locked now rather than left to that item.

## 6. Failure modes

- **The schema bump breaks unrelated tests — 14 files.** The version is pinned
  three distinct ways, and a grep for one misses the others. Measured
  2026-07-28 with
  `grep -rlE 'LATEST_SCHEMA_VERSION|SELECT version FROM schema_version|manifest\["schema_version"\]' tests/ --include='*.py' | sort -u | wc -l`
  → `14`. The three shapes, each counted by its own command:
  (a) the constant pinned to the literal — `grep -rlE 'LATEST_SCHEMA_VERSION *== *12' tests/ --include='*.py' | wc -l`
  → **10**. Three *further* files reference `LATEST_SCHEMA_VERSION` without
  pinning it to `12` and need **no** shape-(a) edit: `accounts/test_accounts.py`
  and `backup/test_backup.py` use it symbolically (`+ 1`, or
  `== LATEST_SCHEMA_VERSION`), and `vault/test_vault.py` names it in a comment
  only. Those three are why the union grep returns 13 for this shape and the
  pin count is 10 — the distinction matters, because an implementer using this
  as a checklist would otherwise hunt `== 12` in three files that do not contain
  it.
  (b) a `SELECT version FROM schema_version` read compared to `12` — 12 files.
  (c) a backup **manifest dict** key, `manifest["schema_version"] == 12` — the
  only *pin* in `tests/features/backup/test_backup.py` (that file also
  references the constant symbolically, per (a)). The per-shape counts overlap,
  so they do not sum to 14; the union is the stable figure. Expected churn rather
  than breakage — the guards keep their meaning — and exactly the cost FIBR-0144
  exists to remove.
- **Six test functions encode the version in their *names*** and must be
  renamed, not just re-numbered. Measured 2026-07-28 with
  `grep -rnoE 'def test_[A-Za-z0-9_]*(v1[0-9]|_1[0-9])[A-Za-z0-9_]*' tests/ --include='*.py'`,
  then read — because the grep alone cannot tell a name that pins the *latest*
  version (churns) from one that names a *step* (does not).
  Five name the latest version: `spending_alerts::test_INV14_latest_schema_version_is_12`
  and `::test_INV14_fresh_vault_is_v12_with_alert_dismissals` (the second of
  which a constant-only grep never finds),
  `db_performance::test_INV1_latest_schema_version_is_12`,
  `forecast::test_INV9_latest_schema_version_is_12`, and
  `reconciliation::test_INV8_schema_version_at_current_latest_v12`.
  The sixth is `spending_alerts::test_INV14_v11_vault_upgrades_to_v12_cleanly`,
  and it reads like a step name but is not: its body hand-builds a v11 vault,
  then calls **`run_migrations`** — which walks to *latest*, not to v12 — and
  asserts `== 12`. At v13 that assertion churns to 13 and the name's stated
  destination is wrong, so it is renamed with the rest (e.g.
  `..._v11_vault_upgrades_to_latest_cleanly`).
  Two names the grep returns are genuinely step names and are **left alone**:
  `db_performance::test_INV1_v9_upgrades_to_v10_adding_indexes` and
  `forecast::test_INV9_v10_upgrades_to_v11_adding_closing_balance_column` both
  drive a specific private step and assert that step's own destination.
  Comments naming `v12` need the same sweep and no assertion-shape grep finds
  them.
- **Five *further* names are already stale and stay that way** — `categorisation`,
  `import_`, `pdf_import`, `recurring` and `transfers` each carry a
  `test_..._latest_schema_version_is_10` whose body already asserts `== 12`.
  Recorded so the rename sweep is not mistaken for a full reconciliation: they
  are pre-existing drift, out of scope here, and the standing evidence for why
  FIBR-0144 exists.
- **`reconciliation`'s *unregistered-next* guard stays green; its sibling and
  its prose do not.** `test_no_schema_change.py` holds two tests, and they
  behave differently: `test_INV8_no_unregistered_next_migration` asserts
  `LATEST_SCHEMA_VERSION + 1 not in _MIGRATIONS` — symbolic, so it needs no edit
  at v13 — while `test_INV8_schema_version_at_current_latest_v12` both churns its
  `== 12` assertion and is in the rename set above. The file's `spec.md` INV-8
  row says the guard pins "that no *unregistered next* version (**v13**)
  exists", which names the version this item registers, and the module docstring
  names v12 as well; both are prose fixes (§12) and both fall under the comment
  sweep. FIBR-0172's INV-14a is the precedent: it advanced the same guard's
  documented next-version from v12 to v13.
- **A vault newer than the app.** Unchanged behaviour: `run_migrations` already
  refuses a vault whose version exceeds `LATEST_SCHEMA_VERSION` with an
  upgrade-finbreak message.
- **Migration interrupted mid-step.** `owned_transaction` makes the two
  `ALTER`s and the version stamp one atomic unit, so a crash leaves a
  re-openable v12 with **neither** column added — SQLite DDL is transactional,
  so the rollback is genuine rather than best-effort.
- **A backup restored from an older vault.** `services/backup.py` compares
  against `LATEST_SCHEMA_VERSION` and migrates on open, so a v12 backup
  restores and upgrades; a backup taken at v13 refuses to restore into an older
  build, as it already does.
- **A pathologically long note or account number.** §4.1 imposes no cap. Nothing
  downstream parses or indexes either field, so the cost is a wide cell in
  FIBR-0113's table — layout, not correctness. No storage-side failure mode.
- **A caller reaching `AccountRepository` directly.** `_normalise_optional` lives
  in the service, so a direct repository write can store `""`. The hazard is
  **structural, not currently realised**: the only direct writer today is
  `test_accounts.py`'s missing-id no-op (`repo.update(999_999, …)`), which
  matches no row and therefore stores nothing. INV-5 is scoped to service
  callers for exactly this reason rather than claiming more than it exercises.

## 7. Tests

New file `tests/features/accounts/test_migration_v13.py`, mirroring
`tests/features/forecast/test_migration_v11.py` — the nearest precedent, same
nullable-`ADD COLUMN` shape. That file holds **12** test functions, of which
**five** concern the migration (the other seven cover the
`StatementPeriodRepository`); this file takes all five migration legs, not
three:

1. a fresh first-run vault is v13 and has both columns (precedent:
   `test_INV2a_first_run_vault_carries_the_column`), **and both are nullable** —
   this leg reads whole `PRAGMA table_info(accounts)` rows and asserts each new
   column's `notnull` field is `0`. The precedent's `_cols()` helper returns
   column names only, so it must be widened or a second reader added; copying it
   verbatim leaves INV-1's nullability clause with no observable;
2. a vault at exactly v12 upgrades cleanly with its rows intact — **accounts
   rows and the FK targets**: assert the seeded `transactions` rows survive and
   `PRAGMA foreign_key_check` returns empty, which is the half of INV-1 a check
   on `accounts` alone cannot see (`build_v9_vault` already seeds transaction
   rows, so the fixture costs nothing extra). The precedent
   does not hand-write DDL for its starting vault — it calls the shared
   `conftest.build_v9_vault` and then runs **one** intervening private step
   (`_migrate_to_v10`) before `run_migrations`. Reaching v12 needs three:
   `_migrate_to_v10`, `_migrate_to_v11` and `_migrate_to_v12`, chained off that
   same builder;
3. `LATEST_SCHEMA_VERSION == 13` **and** `13 in _MIGRATIONS`. The membership
   half is not in the v11 file, which asserts the constant only — take it from
   `tests/features/spending_alerts/test_migration_v12.py`, which does assert
   `12 in _MIGRATIONS`;
4. **atomicity** — wedge the *second* `ALTER` with
   `conftest.raising_conn(conn, "ADD COLUMN note", "injected ALTER failure")`
   (an unambiguous trigger: no other statement in the step contains that
   substring) and assert the vault is still a re-openable **v12 with neither
   `account_number` nor `note` present**. The precedent
   (`test_INV9_migration_is_atomic`) asserts both the version *and* the column's
   absence; asserting the version alone would pass against a step that added the
   first column and left it there. §6 asserts this rollback as fact, so it needs
   a leg;
5. **idempotency at latest** — `run_migrations` on an already-v13 vault is a
   no-op (precedent: `test_INV9_migration_is_idempotent_at_latest`). §4.1
   asserts this as fact, so it needs a leg.

Locks INV-1, INV-2.

Extensions to `tests/features/accounts/test_accounts.py` for INV-3 to INV-7 —
repository/service round-trips on both read paths, two AST scans (over
`repositories/accounts.py` for INV-4 and `services/accounts.py` for INV-5's
both-paths clause), a blank-to-`NULL` leg on `add_account`, an
update-persistence leg for INV-6, and **one `qtbot` leg** for INV-7's
`_on_update` passthrough — the only widget-level test this item carries, and it
exists because §3 decision 5 puts one UI line in scope.

**The test-side naming convention matters as much as the `spec.md` one.**
`test_accounts.py` already holds a `test_INV1_`…`test_INV8_` set for FIBR-0005
*and* a second `test_INV1_` / `test_INV3_` / `test_INV4_` / `test_INV5_` set for
FIBR-0128, separated by a `# FIBR-0128 — …` banner comment and a
`(FIBR-0128 INV-N)` docstring line. This item's INV-3 to INV-7 land in the same
module, so they take the same treatment plus a distinct name suffix. A duplicate
function name in one pytest module **silently shadows** the earlier definition —
the test disappears with no error, which is the one failure mode this file's
existing convention is built to avoid.

`tests/features/accounts/spec.md` already carries two `INV-N` blocks that each
restart at INV-1 — FIBR-0005's under a plain `## Invariants` heading and
FIBR-0128's under `## FIBR-0128 — …`, disambiguated by per-invariant
`Source: FIBR-0128 INV-N` lines. This spec's invariants follow that same
existing convention: a third block under a `## FIBR-0193 — …` heading with
`Source:` lines, rather than inventing a third id style for one file.
FIBR-0113 adds a fourth block the same way; the two must not collide, which the
per-block headings and `Source:` lines already prevent. Note that those headings
are **unnumbered**, so `testing.md` §2.3's citation form (`# INV-3 from
spec.md § 2.1`) resolves here by heading *name*, not section number.

Per `docs/standards/testing.md`, every one of these is run against
pre-implementation source and seen to fail before the implementation is
written. INV-2's clause has already been run red (`12 False`) and is recorded
in §5; the rest are red trivially until `test_migration_v13.py` exists, so the
meaningful red evidence is per-leg once the file is created.

## 8. Alternatives considered (and rejected)

- **Defaulting `update_account`'s new parameters to `None`.** Rejected — see
  §3 decision 2; it turns the six existing call sites into silent data loss.
- **A sentinel default (`_UNSET`) that means "leave this column alone", or a
  read-modify-write inside `update_account`.** Either would keep all six
  existing call sites compiling untouched, and would close §11's bolded
  `nothing` for `scripts/seed_demo_vault.py` — which is a real advantage, so the
  option deserves stating rather than passing over. Rejected because it moves
  the decision from the caller to the callee: a caller that *means* to clear a
  field and one that simply forgot to mention it become indistinguishable at the
  signature, which is exactly the ambiguity decision 2 removes. It also adds a
  third state (`None` vs `_UNSET` vs a value) to a method whose whole contract is
  "this is the account's new content", and read-modify-write turns one `UPDATE`
  into a `SELECT` + `UPDATE` with no transaction around the pair. The loud
  failure at six call sites is a one-time cost paid at compile/test time; the
  sentinel's ambiguity is permanent. §3 decision 5 handles the one caller that
  genuinely wants passthrough, explicitly, at that call site.
- **Defaulting `AccountRepository.update`'s parameters too.** Rejected: it
  defeats decision 2 one layer below the service, where the unconditional
  `UPDATE … SET` actually lives.
- **Normalising and storing account numbers stripped of spaces and dashes.**
  Rejected: FIBR-0086 owns normalisation *for matching*, and normalising at
  storage time would show the user a value they did not type while that item is
  still unbuilt. Store verbatim; normalise at match time.
- **Putting normalisation in the repository rather than the service.**
  Rejected: the repository is the persistence seam and the service is where
  every other validation rule already lives (`_validate`). Splitting them would
  put two validation homes in one feature.
- **A `CHECK` constraint or length cap on either column.** Rejected — see §4.1;
  nothing downstream parses either field, so a cap buys nothing and a migration
  that adds one cannot be applied in place.
- **Carrying the Accounts-table UI here too.** Rejected: that fold-in is what
  took FIBR-0113 to 985 lines and five non-converging review loops. FIBR-0113
  owns it and depends on this.

## 9. Out of scope

- **The Accounts tab UI** — the 5-column table, the masked account-number cell
  and form field, the reveal toggle and its auto-hide timer. Tracked by
  **FIBR-0113**, which this item unblocks.
- **Detecting** an account number on an imported statement and matching it to an
  account — tracked by FIBR-0086. That bullet currently also claims the
  *storage* half ("Store an account number on each account — a new column in the
  ENCRYPTED vault … schema migration, currently v7 -> v8"), which this spec
  delivers instead and at v13, not v8; FIBR-0086's bullet is amended to say so
  (§12), or a later implementer re-adds an existing column at a stale version.
- Per-account currency, which would add a third new column — tracked by
  FIBR-0087. (FIBR-0087's body carries an equivalently stale migration note —
  its wording is `Schema migration (currently v7 -> v8).`, not FIBR-0086's
  phrasing — and it is left alone here because this spec does not deliver any
  part of FIBR-0087.)
- Removing the per-bump `LATEST_SCHEMA_VERSION` test churn described in §6 —
  tracked by FIBR-0144. The five already-stale `_is_10` names are part of that
  item's evidence, not of this one's work.
- Finishing FIBR-0084 — unrelated to storage, and blocked on FIBR-0192.
  FIBR-0084 stays 📋 when this ships **and** when FIBR-0113 ships.

## 10. Resource cost

Two nullable `TEXT` columns on a table that holds one row per account. No cap is
imposed, for the reason §4.1 gives — nothing downstream parses, indexes, matches
or aggregates either field, so a pathological value costs layout rather than
correctness. (Row count is *not* the argument: §4.1 is explicit that one pasted
10 MB note is unbounded however few accounts exist. The low row count is a
separate, non-load-bearing observation.) No new external dependency, no new
module, no new build target.

One knock-on: `AccountService._validate` calls `list_all()` on every add and
update, which now pulls two extra `TEXT` columns per account. Measured against a
real vault this is one row per account — `scripts/seed_demo_vault.py` builds
**three** (the seeded default, renamed, plus Savings and Credit card) — so the
added read is two short strings per row on a query that already runs. Noted
rather than optimised; no timing figure is quoted because none was measured, and
an invented one would be worse than none.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/features/accounts/test_migration_v13.py` legs 1–2 |
| INV-2 | `tests/features/accounts/test_migration_v13.py` leg 3, plus the §5 command |
| INV-3 | `tests/features/accounts/test_accounts.py` |
| INV-4 | `tests/features/accounts/test_accounts.py` AST scan |
| INV-5 | `tests/features/accounts/test_accounts.py` (a behavioural leg on `add_account` + an AST scan over `services/accounts.py`) |
| INV-6 | `tests/features/accounts/test_accounts.py` |
| INV-7 | `tests/features/accounts/test_accounts.py` `qtbot` leg |
| §4.1 the migration is atomic (a wedged second `ALTER` rolls back) | `tests/features/accounts/test_migration_v13.py` leg 4 |
| §4.1 the migration is idempotent at latest | `tests/features/accounts/test_migration_v13.py` leg 5 |
| §4.1 `vault.py::SCHEMA_VERSION` stays at 1 (bumping it would skip every step on a fresh vault) | `tests/features/accounts/test_migration_v13.py` leg 1 — a fresh vault reaching v13 with both columns is only possible if the steps ran |
| §3 decision 2, the six non-seeder `update_account` call sites | the **test run** for the four test callers (they raise `TypeError`) and for the direct `AccountRepository.update` caller; `ui/accounts.py::_on_update` is not pytest-collected as a *caller* but is driven by the FIBR-0005 INV-7f `qtbot` leg, and mypy flags it besides — it is the one annotated caller, since `[tool.mypy]` sets no `check_untyped_defs` and the four test callers are unannotated, so their bodies are not checked |
| §3 decision 2, the `scripts/seed_demo_vault.py` call site | **nothing** — `scripts/` is outside pytest collection *and* outside mypy's configured `files`, so it fails only when the demo seeder is run |
| §4.1 neither column is length-capped | **nothing** — a deliberate departure from spec-format §4; no query, index or import reads either field, so there is nothing to degrade |
| §6 the `v12` comment sweep across the 14 pinning test files | **nothing** — no assertion-shape grep finds a comment, and the gate does not read prose |

Fourteen rows, **three** with a bolded `nothing` — this spec's error budget. All
three are real rather than presentational: the seeder sits outside both gates
(which is why §4.2 lists it explicitly rather than leaving it to a grep), the
missing length cap is an accepted departure, and comment drift has no mechanical
catcher anywhere in this project.

## 12. Cross-doc impact

- `CHANGELOG.md` — one `### Added` entry for FIBR-0193 alone.
- `ROADMAP.md` — **only FIBR-0193 flips ✅.** FIBR-0113 stays 🚧 (it depends on
  this and ships after); FIBR-0084 stays 📋 until FIBR-0192 ships. **FIBR-0086's
  bullet is amended** to drop its account-number storage half and its stale
  "v7 -> v8" migration note, keeping detection + matching (§9).
- `src/finbreak/ui/accounts.py` — `AccountsWidget._on_update` gains the two new
  arguments, reading them off the selected account and passing them back
  unchanged (§3 decision 5, INV-7). The **only** UI edit in this item, and the
  only production caller of `update_account`.
- `scripts/seed_demo_vault.py` — its `update_account` call gains the two new
  arguments. Outside both gates (§11), so it is listed here rather than left to
  be discovered.
- `tests/features/accounts/spec.md` — a third `## FIBR-0193` INV block (§7).
- `docs/specs/FIBR-0113.md` — **no edit needed, listed because it pins this
  spec's invariant numbering.** Its *Withdrawn invariants* block redirects its
  own INV-1→FIBR-0193 INV-1, INV-2→INV-2, INV-3→INV-3, INV-4→INV-4 and
  INV-10→**FIBR-0193 INV-5**, and its §4.3 cites "FIBR-0193 §4.2". Those
  pointers are why INV-1..INV-5 here may never be renumbered (spec-format §3.7);
  INV-6 and INV-7 are new to this spec and are not cited from there.
- The 14 test files that pin the schema version — **§6 owns the shape list, the
  rename set and the comment sweep**; it is not restated here.
- `tests/features/reconciliation/spec.md` — its INV-8 row names **v13** as the
  unregistered next version; prose fix only, its test stays green (§6).
- The feature `spec.md` files that also pin `LATEST_SCHEMA_VERSION == 12` —
  `db_performance`, `categorisation`, `recurring`, `reconciliation`,
  `transfers`.
- `docs/specs/FIBR-0172.md` — its **INV-14 row** pins `LATEST_SCHEMA_VERSION ==
  12` and its **INV-14a row** pins "its version pin to `12`"; both go stale and
  are updated. Its `### D5 — Dismissal persistence (schema v12)` and
  `### D6 — Migration v12` headings are **left alone**: they name the version
  *that* item added, which stays true forever — the same treatment FIBR-0005's
  "Data model (v2)" DDL block gets below. Editing them would falsify a correct
  historical heading.
- `docs/specs/FIBR-0005.md` — states `Account(id, name, type, created_at)` and
  the `.add` / `.update` signatures as INV-1's contract; both are widened here.
  Its INV-1 is **annotated** `INV-1 amended by FIBR-0193` rather than rewritten
  or renumbered, per spec-format §3.7. Two sites state the field list and both
  are annotated: the INV-1 bullet and the Deliverables entry for `models.py`.
  Its "At a glance" row says only "reads back field-for-field" and needs no
  change; its "Data model (v2)" DDL block is a historical v1→v2 snapshot and is
  deliberately left alone.
- `docs/specs/FIBR-0013.md` — pins `Account`'s field list **twice**: in its
  `## Verified code basis` section and in the body's `- **Accounts.**` bullet
  ("`Account` carries `id`, `name`, `type`, `created_at`"). Both go stale after
  §4.2; both are annotated `amended by FIBR-0193`.
- `CLAUDE.md` module map — no change; no new module is added (the migration
  lands in the existing `migrations.py`, the helper in the existing
  `services/accounts.py`).
- `docs/security-model.md` — **no change, and the existing defences that cover
  the new columns are named rather than assumed** (spec-format §5.5). The two
  columns are new *contents of the vault*, not a new boundary: A1's asset row
  already scopes the vault's contents, INV-9's "no transaction contents,
  passwords, keys, or decrypted data in logs" already covers a decrypted account
  number (neither `AccountRepository` nor `AccountService` logs field values —
  `log.info("account updated")` carries no payload), and A4 is the dedicated row
  for the *other* optional sensitive account column,
  `statement_pdf_password`, whose posture §3 decision 1 matches. No new egress
  and no new UI surface arrives here. **FIBR-0113 amends T13**, because revealing
  an account number on screen is what crosses that boundary.
- **No build plan.** spec-format §2 makes a plan mandatory "once the build order
  matters (a migration, …)", **and this spec has a migration, so the rule
  bites**. `docs/plans/` does not exist anywhere in this project and none of its
  49 specs has a plan, so this item is not an outlier — but prior non-compliance
  is not a waiver, and the gap is now tracked by **FIBR-0195** (adopt
  `docs/plans/` or record the departure once, project-wide, instead of in every
  spec). The build order that would have lived here is §4.1 → §4.2 → the one
  `ui/accounts.py` line (§3 decision 5), with the §6 schema-churn sweep landing
  alongside §4.1.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-07-28 | 3 (schema/migration · model-repo-service · cross-doc) + a deterministic pre-pass; strong depth only, no breadth pass (loop 1 of a never-reviewed doc) | 1 | 3 | 13 | 12 | 29 verified, 0 unverified. All fixed. The critical was corroborated independently by two lanes: making `update_account`'s new parameters required breaks `ui/accounts.py::_on_update`, the only production caller, and the draft attributed it to a catcher that ships **later** ("rewritten by FIBR-0113 anyway") — so the app would raise `TypeError` on every Update between the two items, and the obvious patch (`None, None`) is exactly the erasure decision 2 exists to prevent. Added §3 decision 5 (read-and-pass-back) and INV-7 to lock it. INV-6's stated division of labour with INV-5 was false — INV-5's own update leg would have caught the state INV-6 claimed was invisible to it — so the two were re-split: INV-5 owns `""`→`NULL`, INV-6 owns whether a written value lands. §6's "a sixth name stays accurate and must not be renamed" was wrong: that test calls `run_migrations` (which walks to *latest*), so its `== 12` assertion churns to 13 — six names to rename, not five, and two genuine step-names identified as the ones to leave. Shape (a)'s count was a mention-count not a pin-count (13 vs **10**). INV-2's "the reverse is silent" was falsified by a test the same document cites two bullets later. The dataclass defaults turned out to be load-bearing (four-argument `Account(...)` literals in `test_export_dialog.py`) and to silently absorb an un-widened SELECT — now stated, with INV-3 rewritten to fail on it. §10 cited §4.1 while giving the rationale §4.1 explicitly rejects. Two leaked tool-call closing tags were found at EOF and stripped from this file **and** from `FIBR-0113.md` (an authoring artifact; the tag text is deliberately not reproduced here, so no spec carries a literal close-tag). Surfaced not fixed: the project-wide `docs/plans/` gap, filed as FIBR-0195. |
