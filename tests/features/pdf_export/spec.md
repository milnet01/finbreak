# Feature: PDF report export (FIBR-0013)

`PdfExportService(vault)` renders a period's report to a PDF and, when a password
is set, locks it with AES-256 — the money-clarity report a user can share.

## Contract

- **`render_pdf_bytes(options, today=None) -> bytes`** returns a valid PDF
  (`%PDF-` header, `pikepdf.open` succeeds). It takes **no path** — plaintext PDF
  bytes never reach disk (INV-2, structural).
- **Password is optional, the lock is real (INV-1).** A blank / `None` password
  yields an unencrypted PDF; a set password encrypts it (`pikepdf.Encryption(
  user=pw, owner=pw, R=6)`) so it opens **with** the password and raises
  `pikepdf.PasswordError` **without** it.
- **Sections are opt-in (INV-3).** The PDF contains exactly the ticked sections
  (Summary / Charts / Transactions), in that order. A charts-only export carries
  **no** transfer footnote (D6).
- **Account set (INV-4).** `account_ids` is `None` ⇒ all accounts, else the chosen
  subset; an empty `frozenset` yields an **empty** report (never "all" — D4).
- **Per-account lines (INV-5).** Multi-account Summary shows combined figures plus
  one line per account, **ordered by account name**; a single-account export omits
  the per-account block and the Account column.
- **Transfers (INV-6).** Summary + charts exclude confirmed transfers; the
  Transactions list is complete, **marks** transfer rows `⇄ Transfer`, and is
  ordered by `(occurred_on, id)` (stable), with an Account column only when > 1
  account is in scope.
- **One palette, always light (INV-9, FIBR-0217).** The report's colours are an
  explicit constant, independent of any live widget palette, so a dark-themed app
  still exports a light report. Two guards, one per side, because removing a
  feature can be done in the service and forgotten in the dialog: the rendered
  HTML carries the light colours and **not** the withdrawn dark ones, and
  `ExportOptions` has no `theme` field; separately the dialog builds **no**
  `QRadioButton` and no "Theme" group box. The dialog guard reads the widgets
  rather than the options object on purpose — a dialog that still built the radios
  but stopped reading them would pass an options-only check while showing the user
  a control that does nothing. Both proved by mutation.
- **Empty period (INV-13).** A no-rows selection still produces a valid PDF.
- **Atomic + safe (INV-2/INV-12).** `export(options, out_path)` is the sole writer:
  temp file → `os.replace`; on any failure the temp is unlinked and no partial or
  unencrypted file is left.
- **One clock (INV-7, FIBR-0342).** The report's period and its offered filename
  resolve from the **same** date, and it is the **app** clock — the zone the user
  pinned in Settings, which is what Home reads. The shell reads it **once** and
  passes it to both, so neither can straddle midnight. Driven through the real
  shell and asserted on the PDF's own period line against the offered filename:
  the defect was that the two artefacts disagreed, and only the pair shows it.
  A machine clock on a different calendar day must not move the output.
