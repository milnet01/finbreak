# tests/features/datetime_format — FIBR-0083 the pure formatter

Conformance tests for the pure formatter in
[`docs/specs/FIBR-0083.md`](../../../docs/specs/FIBR-0083.md) Deliverable 1 —
`src/finbreak/datetime_format.py`. Qt-core only (no Widgets), so no `qtbot`.

The module turns stored UTC/ISO strings into display strings under three user
prefs (`timezone`, `date_format`, `time_format`), each either a concrete value
or the `"system"` sentinel (resolve dynamically at display time). The
Settings/first-run UI and shell wiring are covered by later slices' suites
(`settings`, `first_run`, `app_shell`).

## Coverage

| INV / D | What it pins |
|---------|--------------|
| INV-2 | `format_date` reformats a calendar date and takes **no** timezone argument: `2025-06-19` → `2025/06/19` (`yyyy/MM/dd`), `19/06/2025` (`dd/MM/yyyy`) — same day, format only. |
| INV-3 | `format_timestamp` converts UTC → the pinned zone, then formats: `2026-07-11T06:49:15.506928+00:00` in `Africa/Johannesburg` + `yyyy/MM/dd`+`HH:mm` → `2026/07/11 08:49`. Also parses a fractional-second-less instant (`…:15+00:00`). |
| INV-4 | The `"system"` legs assert **by delegation** to `QLocale.system()` / `systemTimeZoneId()`, never a pinned string, so they hold on any runner locale/zone. |
| INV-6 | Fail-safe: a bogus zone id / bogus format token resolves to the `"system"` result (`format_date(iso,"bogus") == format_date(iso,"system")`); an unparseable input string is returned **raw**, never raised. |
| D1/D5 | `DATE_PRESETS`/`TIME_PRESETS` are `list[tuple[str,str]]` of concrete `(token, sample_label)` rows — **no** `"system"` row — and each `token.toString`s the D5 sample instant to its advertised `sample_label`. |
| D5 | `format_timestamp` composes the two halves **independently**: a `"system"` date half + a known time token (and vice-versa) each format on their own, joined by a single space. |
| Deliverable 1 | `system_timezone_id()` returns Qt's system zone id decoded to `str` (`QTimeZone.systemTimeZoneId().data().decode()`). |
