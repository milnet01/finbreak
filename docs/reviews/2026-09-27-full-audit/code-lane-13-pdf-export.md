**Lane 13 (PDF export, export dialog, charts, clipboard): one probable Critical on Windows, plus two Medium bugs on the default export path.**

This was a depth pass. The review-lane agent type ran. I made no edits and no test files were opened. I resolved no disagreements between the brief and my standing rules.

**Subject files, line counts as I read them** (all under `/mnt/Games/Scripts/Linux/finbreak/src/finbreak/`):
- `services/pdf_export.py`: 435
- `ui/export_dialog.py`: 284
- `ui/charts.py`: 251
- `ui/_clipboard.py`: 68

**Already in my context when I arrived:**
- Global `~/.claude/CLAUDE.md`
- `/mnt/Games/CLAUDE.md`
- finbreak `CLAUDE.md`
- finbreak `MEMORY.md` index
- A git snapshot (clean, HEAD 52e5162, FIBR-0331 commits)

**Contract read:**
- FIBR-0013 lines 1–540 (invariants, D1–D13, deliverables, exit criteria).
- ADR-0004 and ADR-0008 were requested in the same call, but that call spilled and I then read only the FIBR-0013 file directly. Neither ADR was actually read.
- `security-model.md` T13 and lines 270–419 (INV-4, INV-7).
- FIBR-0153 lines 34–161.
- FIBR-0143 lines 180–229.
- FIBR-0198, FIBR-0123, FIBR-0219 and FIBR-0231: requested, but that call also spilled and I did not re-read them. Search hits showed they only cite these modules as precedent.
- Cross-references opened: `ui/_amount.py` (the `_format_amount` signature) and `ui/main_window.py:1060-1135` (the only caller of `export()`).
- One `workspace_search` was rate-limited, so I used `Grep` for that search. It was over `src/`, so the test tree was not touched.

## Critical (1)
- [dim 11] `services/pdf_export.py:173-178` — `os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),` then `os.fdopen(fd, "wb")`.
  - **The problem:** there is no `os.O_BINARY`. On Windows, a file opened this way is in the C runtime's default text mode, so every `\n` byte written becomes `\r\n`. The `"wb"` passed to `fdopen` does not reset the mode already set on the file descriptor. That shifts every xref offset and corrupts compressed streams, so every exported PDF on the shipped Windows `.exe` would be damaged, locked or not.
  - **Evidence:** the stdlib's own `tempfile` adds `O_BINARY` explicitly for exactly this reason. A grep for `O_BINARY` across `src/` finds nothing, and CI runs Linux only.
  - **Unexecuted.** Confirm by exporting on the Windows box (`ssh wintest`) and opening the result with `pikepdf.open`.
  - **Same pattern outside this lane**, with the same risk to binary backups: `services/backup.py:742` and `:772`, `services/vault_migration.py:121`, and `crypto.py:458`.
  - **Fix:** OR in `getattr(os, "O_BINARY", 0)` at every guarded open.

## High (0)

## Medium (2)
- [dim 2] `services/pdf_export.py:318-320`, `:340-342`, `:417` — `escape(_format_amount(s.income, symbol))`.
  - **The problem:** `negative_style` is never passed, so it takes its default, `NegativeStyle.MINUS`. A user whose FIBR-0105 preference is brackets sees `(R 420.00)` on screen but `-R 420.00` in the PDF.
  - **Which side is wrong: the code.** FIBR-0013 D6 says amounts are "formatted with the reused amount + date display prefs (FIBR-0083/0105)", and the illustration note says the same. Only the date preference is honoured.
  - **Fix:** carry the user's amount preferences (`AmountPrefs`) into `ExportOptions`, or read them in the service, and pass `negative_style` at all three sites.
- [dim 2] `ui/export_dialog.py:121-123` together with `:193-194` — `form.addRow(self.tr("Month"), self._month_picker)` … `self._month_picker.setVisible(mode == MODE_SPECIFIC_MONTH)`.
  - **The problem:** `addRow(str, widget)` creates a separate label. Hiding the field leaves the label showing. In the default Previous-month mode, and in Current month and Year to date, the dialog therefore shows bare "Month" and "Year" labels with nothing beside them.
  - FIBR-0013 D7 and the illustration say the pickers are *enabled* only in the specific modes.
  - **Fix:** use `form.setRowVisible(row, visible)` (Qt ≥ 6.4), or `setEnabled` as the spec words it.

## Low / Info
- [dim 9] `pdf_export.py:178-180` — there is no `handle.flush(); os.fsync(fd)` before `os.replace`. On power loss, some filesystems can leave a zero-length file at `out_path`. That breaks D1's claim that the output is "either the whole finished file or untouched".
- [dim 9] `pdf_export.py:172` — `tmp.unlink(missing_ok=True)` silently deletes any existing user file named `<chosen name>.part`. Browsers use that name for in-progress downloads. The window is small.
- [dim 7] `pdf_export.py:134-143` — the return value of `buffer.open(...)` is ignored, and nothing checks that the bytes start with `%PDF`. If `QPdfWriter`/`print_` produced nothing, an unlocked export would write an empty file and report "Report exported". Fix: assert the bytes are non-empty and start with `%PDF`, and raise otherwise.
- [dim 13] Digits and numbers are not localised consistently:
  - `pdf_export.py:255` `return str(end.year)` and `:268` `year=end.year` print Python ASCII digits next to a `QLocale` month name. The dialog uses the locale's own digits (`export_dialog.py:106`).
  - `charts.py:210` and `:247` `QValueAxis()` never calls `chart.setLocalizeNumbers(True)`, so axis values use a C-locale decimal separator in both the PDF trend chart and on screen.
- [dim 3] `charts.py:131` and `:156` — `series.append(label, …)`. I believe QtCharts draws slice and legend labels as rich text (`QGraphicsTextItem::setHtml`). If so, a category or drill-node label containing markup such as `<img src=file:…>` would be interpreted rather than shown as text. **Unexecuted** — needs a probe with a label like `<b>x</b>`. The HTML report body itself is correctly escaped.
- [dim 2] Wording in the code is stale:
  - `charts.py:13` says the export "passes an explicit Light or Dark `ChartTheme` (D7)".
  - The comment at `charts.py:238-240` cites "the Dark PDF export".
  - Both are false since FIBR-0217 withdrew the dark theme.
  - `export_dialog.py:267` says "read after an accepted `exec()`", which contradicts the same file's lines 8-9 and D9. The dialog is never `exec()`-ed.
- [dim 2] **Which side is wrong: the document.** FIBR-0013 D1 describes `ExportOptions` with `sections: frozenset[str]` and a `today` field. The code has three booleans and takes `today` as a parameter of `render_pdf_bytes`/`export`, and it is coherent. This belongs to `review-contract`.
- [dim 2b] Nothing found. Every promised entry point has a caller in `src/`: `build_donut_chart` and `build_trend_chart` (export and Home), `build_breakdown_donut` (Home), `build_forecast_chart` (Forecast), `period_filename_slug`, `ClipboardAutoClear` (three sites) and `PdfExportService`.
- [dim 4] Nothing found diverged in this lane. The guarded open is duplicated across files, but every copy lacks `O_BINARY` the same way (see the Critical).
- [dim 5] Nothing found. INFO: the D11 budget (≲1 s, ≲5,000 rows) cannot be judged by reading.
- [dim 8] Nothing found. Everything here runs on the GUI thread, and `retire()`'s deferred `deleteLater` is sound.
- [dim 10] N/A. There is no logging in these files.
- [dim 12] N/A. No accessibility standard is named.
- [dim 15] Nothing found. A blank password producing a plaintext PDF is contract-sanctioned (INV-1, security-model INV-7). No title or author metadata is set.
- [dim 16] Nothing beyond the Critical. Disk-full and a file locked by a viewer both raise `OSError`, which the caller catches (`main_window.py:1111`), and the `.part` file is unlinked.
- [dim 17] N/A. There is no persisted state here.

## Covered by spec and looks correct
- **INV-1:** `pikepdf.Encryption(user=pw, owner=pw, R=6)` at `pdf_export.py:192`.
- **INV-2:** `render_pdf_bytes` takes no path, encryption is in-memory `BytesIO`, and `export()` is the only writer, using temp → `os.replace`, `O_EXCL|O_NOFOLLOW` and mode `0600`, matching security-model INV-7.
- **INV-3:** sections appear only if ticked, in fixed order.
- **INV-4 and D5:** a `None` account set means "all"; a stale id drops out via the live account list.
- **INV-5:** per-account block only when more than one account is in scope, sorted by name.
- **INV-6:** transfers sorted by `(occurred_on, id)`, marked by id set, footnote only with Transactions.
- **INV-9:** a single light theme constant.
- **INV-13:** the empty-donut placeholder.
- **D2:** the header rules, including the collapse beyond 3 accounts.
- **HTML injection:** every user-origin string (account names, description, category, dates, currency) goes through `html.escape` at `pdf_export.py:279-285`, `:339`, `:407` and `:412-417`.
- **INV-14 gating and blank-password-wins:** `export_dialog.py:210-235` and `:276-283`.
- **D7:** the "All accounts" toggle state machine.
- **T13:** the clipboard guard only clears a value it still owns, reads its timeout live on each copy, and `0` means never. The setting is bounded to the allowed values (`auth.py:105`), so `seconds * 1000` cannot overflow.

## Open questions
- **Wayland clipboard.** Does `ClipboardAutoClear.clear_if_ours` work when the app is unfocused? Qt may still report our value after another app has copied, and the compositor may ignore a clear sent by an unfocused client. Either would break T13's "only if ours" or its "auto-cleared" promise. Needs a live Wayland test.
- **Name sorting.** INV-5 says "ordered by account name", but `sorted(key=lambda a: a.name)` is case-sensitive, so "cheque" sorts after "Savings". Is that the intended order?
- **Non-ASCII passwords.** A password containing composed versus decomposed Unicode characters may open in qpdf/pikepdf but not in viewers that normalise R=6 passwords (SASLprep). Unexamined.
- **My starting context.** I arrived holding the project `CLAUDE.md` and memory index, as listed at the top. I did not use them as evidence.

## 3 items to fix first
1. **The missing `O_BINARY` on Windows.** If confirmed, every Windows export (and, by the same pattern, every Windows backup) is corrupted. It is a one-token fix per site.
2. **The ignored `negative_style`.** The printed money figures contradict the user's own display preference on the default path of a money report.
3. **The orphan Month/Year labels.** They are visible every time the dialog opens in its default mode, and the fix is small.