# tests/features/first_run — FIBR-0083 first-run datetime prefs (INV-8)

Conformance tests for the first-run half of
[`docs/specs/FIBR-0083.md`](../../../docs/specs/FIBR-0083.md) (Deliverable 4 /
INV-8): the create-vault wizard presents the same three timezone / date / time
controls pre-filled with the detected `"system"` defaults, and on a **successful**
vault creation writes the selections via `AuthService.set_datetime_prefs` at its
`_on_derived` site (D6). A cancelled first-run creates no vault and persists
nothing.

The happy path drives `FirstRunDialog` to `_on_derived` through a **synchronous
`DeriveWorker` stand-in** (monkeypatched in): it runs the real Argon2 derivation
inline and emits `done` from `start()`, so the test exercises the dialog's persist
site without waiting on the worker **thread** (only the QThread event-loop wait is
skipped). No network, vault under `tmp_path`.

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-8 (persist) | A first-run happy path with the three combos set to concrete values writes exactly those via `set_datetime_prefs` — asserted through `AuthService.datetime_prefs()` on the just-created vault; `completed` fires. |
| INV-8 (cancel) | A cancelled first-run (`reject()` with no derivation in flight) calls `set_datetime_prefs` **never** (a class-level spy) — there is no vault to inspect. |
| Deliverable 4 | The wizard's three combos exist (`first_run_timezone` / `first_run_date_format` / `first_run_time_format`), pre-filled with the `"system"` sentinel (no vault read at construction — the wizard runs before the vault exists). |
