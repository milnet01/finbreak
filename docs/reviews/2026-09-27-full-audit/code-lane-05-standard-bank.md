**Subject files, line counts as I read them:**
- `src/finbreak/importers/standard_bank.py`: 1327 lines
- `src/finbreak/importers/pdf_importer.py`: 211 lines

Both were read in full.

**Already in my context when I arrived:**
- the global `~/.claude/CLAUDE.md`
- `/mnt/Games/CLAUDE.md`
- finbreak's `CLAUDE.md`, which includes the module-map note on the `_draft` trap
- the finbreak memory index (`MEMORY.md`)
- a git snapshot at HEAD 52e5162

**Cross-references I read:**
- FIBR-0050: D8, D9, D10, D11, D12, D13, the sub-invariants and Deliverable 1
- FIBR-0255: §4.1 through §5

I did not open FIBR-0252, 0086, 0190, 0171 or 0146 beyond what FIBR-0050 and the code cite. No test files were opened, and the test tree was excluded from my searches.

## Critical (0)

## High (0)

## Medium (4)

- [dim 2] `standard_bank.py:899-902` (the same pattern is at :951-954, :986-989 and :1046-1049) — `if bf is not None: prev_balance = bf  # brought-forward anchor (dated page-1 or undated repeat)` — **a page's re-anchor is never checked against the running balance.**
  - D12 rests on the continuation page's brought-forward "equal[ling] the prior page's closing". D10 claims the per-row gate catches "a mid-statement drop". The code checks neither: it overwrites `prev_balance` unconditionally.
  - So if rows are lost at the end of a page, the next page's anchor restarts the chain and every surviving row still reconciles. A lost row could be one folded as a continuation or boilerplate (see the next two findings), or a page whose `_table_region` found no header and returned `slice(0,0)`.
  - On Savings (Family A, no closing) and on E without both totals, no gate remains, so the import is silently short by those rows. On families that print a closing, the completeness gate still catches it.
  - The code is the wrong side here. **Fix:** when `prev_balance is not None` and `bf != prev_balance`, raise `_MISPARSE`, or a dedicated "didn't add up" message.

- [dim 2] `standard_bank.py:243-245` with `:298-301` — `return any(t in low for t in _TERMINATORS)` — **the region terminator is a substring match tested on every line, row lines included.**
  - A transaction whose description contains "closing balance", "balance as at", "account summary", "interest calculation", "fee structure" or "the standard bank of south africa" ends that page's region. Every later row on the page is then silently discarded.
  - One plausible trigger is a transfer from a closed account described as "CLOSING BALANCE TRANSFER".
  - This is caught where a closing prints. It is silent on Savings and on E without totals, especially when combined with the previous finding.
  - The code follows D11 literally; D11's premise that no description ever contains a terminator phrase is the weak side. **Fix:** skip the terminator test on lines where `_looks_like_row(line)` is true, or anchor terminators to the start of the line.

- [dim 2] `standard_bank.py:755-757` — `if _is_boilerplate(line): continue` runs **before** `if _looks_like_row(line, ...)` — **a real transaction row whose description matches `_SB_LETTERHEAD` is dropped as page furniture.**
  - The patterns that can match a description are `\bp\s?o\s+box\b`, `\bfax\b` and `registration\s+(?:no|number)`. Examples: "PO BOX 123 MERCHANT", or a vehicle-licence "REGISTRATION NO" payment.
  - Mid-page, the next row's delta then mismatches and a valid statement is refused.
  - At a page end, or as the last row on Savings or E-without-totals, the loss is silent (see the first finding). **Fix:** test `_looks_like_row` first and apply `_is_boilerplate` only to non-row lines.

- [dim 11] `pdf_importer.py:208-211` (`pdf.save(out)`), `standard_bank.py:1174` (`page.extract_text()`) and `pdf_importer.py:171` (`page.extract_tables()`) — **there is no bound on decompressed size.**
  - The only size caps are the 16 MiB input cap (`services/import_.py:46`) and the 500-page cap.
  - A Flate-bomb content stream within 16 MiB expands to gigabytes. My understanding is that qpdf's default decode level on save re-inflates Flate streams, and that pdfminer inflates each content stream fully in memory with `zlib.decompress` during text extraction.
  - A hostile "statement" would therefore exhaust memory or CPU before any cap fires.
  - **Unexecuted.** It needs a probe with a single-page PDF carrying a ~10 MiB Flate stream that decodes to more than 5 GiB, run through `StandardBankImporter().parse`. I could not verify the pikepdf/qpdf default `stream_decode_level` from the tree.
  - **Fix:** pass `stream_decode_level=pikepdf.StreamDecodeLevel.none` on save, and pre-check each page's `/Contents` `/Length` × a ratio bound, or decode with a capped `zlib.decompressobj` before handing the file to pdfplumber.

## Low / Info

- [dim 7] `pdf_importer.py:172-173` and `standard_bank.py:1175-1176` — `except ValueError: raise  # our own friendly guards (e.g. the page cap) pass through`.
  - This also passes through any `ValueError` raised *inside* pdfminer or pdfplumber, such as a bad `int()` literal in a malformed object. The user then sees an internal message rather than "couldn't read this PDF".
  - **Fix:** raise the page-cap error outside the `try`, or use a private `ValueError` subclass and re-raise only that.

- [dim 2] `standard_bank.py:518` and `:1296` — `raise ValueError("couldn't find the opening balance on this statement")`.
  - D10 says every refusal directs the user to the CSV/OFX export. These two, `_parse_amount` at :196 and `_dmy_iso` at :1140 omit that tail, while every sibling message carries it.
  - The code is the wrong side. **Fix:** append the standard tail.

- [dim 13] `standard_bank.py:419-436` (`_infer_years`) — the rollover rule means that **a single back-dated row** puts every later row one year late. A back-dated row here means one whose month is lower than the previous row's within the same statement.
  - Nothing checks that an inferred date lies inside the printed period.
  - The code matches D8; D8's premise that SB prints strictly in order is unverified by me. **Fix:** refuse (`_MISPARSE`) when any inferred date falls outside `[period_start − slack, period_end]`.

- [dim 13] All refusal strings in `standard_bank.py` are plain English literals: `_MISPARSE`, `_UNREADABLE_MONEY_ROW`, `_E_TOTALS_MISMATCH`, and the messages at :176, :559, :580, :612, :876 and :881. The same is true of `pdf_importer.py` at :165, :176, :183 and :188.
  - `design.md` § i18n commits to routing every user-facing string through `tr()`, and these strings are shown to the user.
  - It is LOW only if the UI does not translate them at the display site, which I could not see.

- [dim 3] Nothing found on secrets. The password is used only in `pikepdf.open` and never logged or echoed, and the decrypted bytes stay in `BytesIO`.
- [dim 3] The regexes have no nested unbounded quantifier that can fail catastrophically. `_MONEY`'s look-behind prevents mid-run restarts, and the Family A `re.search` fails in linear time on the lines `_TRAILING_TAIL` admits. Nothing found beyond the dim 11 item.
- [dim 5] Nothing found beyond dim 11. The region-line cap (:1198) bounds the parse work as FIBR-0078 requires.
- [dim 2b] No zombies. Every contract-named entry point has a non-test caller:
  - `decrypt_to_plaintext`: `import_wizard.py:826`
  - `default_table_index`: `import_wizard.py:925`, `batch_import.py:401`
  - `candidate_tables` / `table_to_text`: wizard and batch
  - `StandardBankImporter().parse`: wizard :904, batch :382
  - `extract_account_number`: `parse` :1267
- Dims 4, 8, 9, 10, 15, 16, 17: nothing found. There is no persistence, no threads, no logging, no network, and no state schema in these files.
- Dim 12: N/A.
- INFO: I could not determine whether `pikepdf.open` or `save` can raise anything other than `PasswordError` or `PdfError` on hostile bytes. Only those two are documented to escape `parse` unwrapped.

## Covered by spec and looks correct

- `_draft` (:817-857) is byte-for-byte FIBR-0255 §4.1. It degrades on `signed == 0` and never on the reason, so a `0.00` row with a bad date still degrades. Family C's `-printed` gives `Decimal('-0')`, which compares equal to 0 and degrades correctly.
- `parse_transaction(` is called only inside `_draft` (INV-4).
- The per-row `_verify_row` sign rule is skipped only for B.
- The `_verify_checksum` comparison is signed for A, C, D and E, with only B compared by magnitude (INV-11 exemption). The closing is required for B, D and C and skipped for A and E, as D10 and D13 say.
- The storable bound is applied to both opening and closing before comparison, and also on E's path.
- `RowError`s propagate into the returned `ParseResult` (FIBR-0252).
- The page cap is re-checked on the SB path, and there is a pre-parse region-line cap and a post-parse draft cap (Deliverable 1).
- The E-before-else dispatch and the C→D→E→B→A detection order match D4 and INV-2a.
- The account-number hint excludes Family C both in the extractor and at the call site (FIBR-0086).

## Open questions

- Does the wizard or batch UI translate these `ValueError` texts at display time? This decides whether the dim 13 LOW is real.
- Do Standard Bank ever issue C or E statements with Afrikaans month abbreviations ("Mei", "Okt", "Des")?
  - `_MON_RE` is English-only, so such a row would fold into the previous description rather than parse.
  - On C, the mandatory gate refuses the statement. On E without totals, a tail row would be lost silently.
- Is D12's "equals the prior page's closing" a claim the code was meant to enforce, or only a description of the document? The first Medium assumes it should be enforced, since D10 claims mid-statement drops are caught.
- Is the parse run off the GUI thread? This decides whether the dim 11 item is a hang or an out-of-memory kill.

## 3 items to fix first

1. **Verify each brought-forward re-anchor** (first Medium). It is a one-line guard, and it turns every silent-loss path in the next two items from silent into a refusal on all families, including Savings and E.
2. **Test row-shape before the terminator and letterhead filters** (second and third Mediums). These are the concrete ways rows vanish from real descriptions. Item 1 makes most of them loud, but a valid statement is then still refused.
3. **Bound decompression** (fourth Medium). It is the only resource-exhaustion path on untrusted input that the existing caps don't reach. It is unexecuted, so the orchestrator should probe it first.