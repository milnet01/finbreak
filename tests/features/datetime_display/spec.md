# tests/features/datetime_display — FIBR-0083 display wiring (D5/D6/D7/INV-1)

Conformance tests for the display half of
[`docs/specs/FIBR-0083.md`](../../../docs/specs/FIBR-0083.md): the Statements
**Period** + **Imported** columns and the Home **Date** column are rendered
through the pure formatter under the shell's held `DateTimePrefs`, formatting is
**display-only** (stored rows never mutate, INV-1), and a Settings **Save**
pushes the new prefs to the open tabs live (D7). Vault under `tmp_path`, no
network; statement rows are seeded via raw SQL so `imported_at` is a fixed,
known UTC instant.

## Coverage

| INV / D | What it pins |
|---------|--------------|
| D5 | Statements **Period** = `format_date` of each endpoint rejoined by ` – `; **Imported** = `format_timestamp(imported_at, tz, date, time)` — a UTC instant shown converted + formatted in the pinned zone. |
| D6 | Home **Date** = `format_date(occurred_on, date_format)`. |
| INV-1 | Rendering both widgets leaves the stored `statement_periods` + `transactions` rows byte-for-byte unchanged (display-only). |
| D7 (widget) | `set_datetime_prefs(new)` on a live widget re-renders its cells to the new prefs. |
| D7 (shell) | The shell reads prefs once post-unlock and passes them to Home/Statements; a Settings **Save** re-reads and pushes the new prefs so the open tabs reformat without a relaunch. |
