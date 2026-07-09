# Feature test contract — statements (FIBR-0052 P07.6)

Enforces the FIBR-0052 spec: the tabbed workspace shell, window geometry, and the
Statements tab (statement provenance stamp v5→v6 + delete). The design doc is
[`docs/specs/FIBR-0052.md`](../../../docs/specs/FIBR-0052.md); this file is the
per-feature test contract (the small companion the app-workflow keeps beside the
tests, not a design doc).

## What is covered here

`tests/features/statements/test_statements.py` — the FIBR-0052 invariants whose
subject is new in this phase:

- **INV-1 / INV-2 / INV-2a** — the workspace `QTabWidget` has four fixed tabs
  (`tab_home` · `tab_statements` · `tab_accounts` · `tab_categories`) in order;
  the View/toolbar nav actions switch the *same* tab instance (never rebuild).
- **INV-3a** — a lock while the import wizard occupies the content slot destroys
  the wizard (no live import survives a lock).
- **INV-5 / INV-5a** — window geometry + last tab round-trip through a plain INI
  at `paths.window_settings_path()`, outside the vault, holding no transaction
  data.
- **INV-6 / INV-6a / INV-6b / INV-6c** — the `Window` menu: Center window, Reset
  layout (to `_DEFAULT_WINDOW_SIZE`), both enabled while locked.
- **INV-7 / INV-7a / INV-7b** — the Statements tab lists imports with an exact
  linked-transaction count; a zero-linked statement still lists (count `0`).
- **INV-8 / INV-8a / INV-8b / INV-8c** — `commit_import` stamps every imported
  row with its statement; manual entry stays `NULL`; a span-reuse import stamps
  with the existing period id.
- **INV-9 / INV-9a / INV-9b / INV-9c / INV-9d** — `delete_statement` atomically
  removes only the target's stamped rows + its record; the FK blocks an unsafe
  direct period delete; the v5→v6 backfill links unambiguous rows only.
- **INV-10 / INV-10a / INV-10b** — the Delete action confirms (naming the count)
  then deletes + refreshes; Cancel does nothing.
- **INV-11 / INV-11a** — a mutation reflects on the Home tab on next activation.
- **INV-12 / INV-12a** — Accounts/Categories built with `show_done=False` have no
  Done button; a default-constructed one still does.

The v5→v6 schema-version ripple (INV-13/INV-13a) and the v4-through-v6 upgrade
test live with the migration suites (`pdf_import`, `import_`, etc.); the FIBR-0051
`app_shell` test ripple (D14) is edited in `tests/features/app_shell/`.

## Fixtures

100 % synthetic: tiny in-repo CSV strings imported through the real
`ImportService.commit_import` on a `tmp_path` vault (real Argon2id on the vault
fixture, as the FIBR-0007 import tests do). No network, no real financial data;
the user's real credit-card PDF is for manual end-to-end validation only — never
committed, its password never written. Backfill tests build a raw v5 vault via
`conftest.build_v5_vault` and run the real `_migrate_to_v6`.
