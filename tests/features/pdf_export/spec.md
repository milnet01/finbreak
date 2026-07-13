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
- **Theme (INV-9).** Explicit Light (default) / Dark colours, independent of any
  live widget palette.
- **Empty period (INV-13).** A no-rows selection still produces a valid PDF.
- **Atomic + safe (INV-2/INV-12).** `export(options, out_path)` is the sole writer:
  temp file → `os.replace`; on any failure the temp is unlinked and no partial or
  unencrypted file is left.
